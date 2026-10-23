"""Shared font handling, safe text, pagination and output validation."""

import hashlib
import os
import re
import sys
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from html import escape
from io import BytesIO
from itertools import groupby
from pathlib import Path
from threading import Lock

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.platypus import Paragraph

from resume_app.documents import MAX_TEXT_LENGTH, DocumentError
from resume_app.models import ResumeProfile


_FONT_LOCK = Lock()


def text_values(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from text_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from text_values(item)


def validate_text(text: str) -> None:
    if any(
        ord(character) < 32 and character not in "\r\n\t"
        or 0xD800 <= ord(character) <= 0xDFFF
        or ord(character) in {0xFFFE, 0xFFFF}
        for character in text
    ):
        raise DocumentError("简历或职位文字包含无效控制字符，请删除后重新确认")


def validate_profile(profile: ResumeProfile) -> list[str]:
    texts = list(text_values(profile.model_dump()))
    if not profile.contact.name or not any((
        profile.summary, profile.skills, profile.experience,
        profile.education, profile.projects,
    )):
        raise DocumentError("请至少填写姓名和一项简历内容，再确认生成 PDF")
    if sum(map(len, texts)) > MAX_TEXT_LENGTH:
        raise DocumentError("PDF 简历文字不能超过 80,000 字符")
    for text in texts:
        validate_text(text)
    return texts


def font_path(configured: str | Path | None) -> Path:
    if configured is not None:
        path = Path(configured).expanduser().resolve()
        if not path.is_file():
            raise DocumentError("PDF 字体不存在，请检查 PDF_FONT_PATH")
        return path
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    candidates = (
        [windows_fonts / name for name in ("msyh.ttc", "simsun.ttc")]
        if sys.platform == "win32" else [
            Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
            Path("/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    raise DocumentError("没有可用的中英文字体，请在 PDF_FONT_PATH 配置可嵌入的 TTF/TTC 字体")


@lru_cache(maxsize=12)
def registered_font(path: str) -> TTFont:
    name = "ResumeBody-" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
    with _FONT_LOCK:
        try:
            font = TTFont(name, path, subfontIndex=0)
            pdfmetrics.registerFont(font)
        except (TTFError, OSError) as error:
            raise DocumentError("PDF 字体无法加载，请检查 PDF_FONT_PATH") from error
    return font


@dataclass(frozen=True)
class PdfFonts:
    regular: TTFont
    bold: TTFont
    fallback: TTFont

    def markup(self, text: str, *, bold: bool = False) -> str:
        primary = self.bold if bold else self.regular
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")

        def choose(character: str) -> str:
            if character == "\n" or ord(character) in primary.face.charWidths:
                return primary.fontName
            if ord(character) in self.fallback.face.charWidths:
                return self.fallback.fontName
            raise DocumentError("当前 PDF 字体不支持部分字符，请更换 PDF_FONT_PATH 或修改特殊字符")

        return "".join(
            f'<font name="{name}">{escape("".join(characters)).replace(chr(10), "<br/>")}</font>'
            for name, characters in groupby(text, choose)
        )


def load_fonts(configured: str | Path | None = None, *, serif: bool = False) -> PdfFonts:
    fallback = registered_font(str(font_path(configured)))
    if serif:
        windows = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        candidates = (
            [(windows / regular, windows / bold) for regular, bold in (
                ("gara.ttf", "garabd.ttf"), ("times.ttf", "timesbd.ttf"),
            )] if sys.platform == "win32" else [
                (Path(root) / "LiberationSerif-Regular.ttf", Path(root) / "LiberationSerif-Bold.ttf")
                for root in (
                    "/usr/share/fonts/truetype/liberation2",
                    "/usr/share/fonts/truetype/liberation",
                )
            ]
        )
        for regular, bold in candidates:
            if regular.is_file() and bold.is_file():
                return PdfFonts(registered_font(str(regular)), registered_font(str(bold)), fallback)
    return PdfFonts(fallback, fallback, fallback)


def paragraph(
    text: str, style: ParagraphStyle, fonts: PdfFonts, *,
    bold: bool = False, bullet: str | None = None,
) -> Paragraph:
    return Paragraph(fonts.markup(text, bold=bold), style, bulletText=bullet)


def normalized_text(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).replace("\u00ad", ""))


def validate_pdf(content: bytes, texts: list[str]) -> None:
    if not content.startswith(b"%PDF-"):
        raise DocumentError("生成结果不是有效 PDF，未保存确认")
    try:
        reader = PdfReader(BytesIO(content))
        text = normalized_text("\n".join(page.extract_text() or "" for page in reader.pages))
    except (PdfReadError, ValueError) as error:
        raise DocumentError("无法校验生成的 PDF，未保存确认") from error
    if not text or any(normalized_text(value) not in text for value in texts if value):
        raise DocumentError("生成的 PDF 有文字缺失，请检查字体和模板后重新确认")
