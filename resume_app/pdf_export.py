"""Unicode-safe, single-column PDFs built only from confirmed resume data."""

import hashlib
import os
import sys
from collections.abc import Iterator
from functools import lru_cache
from html import escape
from io import BytesIO
from pathlib import Path
from threading import Lock

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate
from reportlab.platypus.doctemplate import LayoutError

from resume_app.documents import (
    MAX_TEXT_LENGTH, DocumentError, resume_entry_text, resume_sections,
)
from resume_app.models import ResumeProfile


_FONT_LOCK = Lock()


def _text_values(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _text_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _text_values(item)


def _font_path(configured: str | Path | None) -> Path:
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


@lru_cache(maxsize=4)
def _registered_font(path: str) -> TTFont:
    name = "ResumeBody-" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
    with _FONT_LOCK:
        try:
            font = TTFont(name, path, subfontIndex=0)
            pdfmetrics.registerFont(font)
        except (TTFError, OSError) as error:
            raise DocumentError("PDF 字体无法加载，请检查 PDF_FONT_PATH") from error
    return font


def resume_pdf(
    profile: ResumeProfile, font_path: str | Path | None = None,
) -> bytes:
    texts = list(_text_values(profile.model_dump()))
    if not profile.contact.name or not any((
        profile.summary, profile.skills, profile.experience,
        profile.education, profile.projects,
    )):
        raise DocumentError("请至少填写姓名和一项简历内容，再确认生成 PDF")
    if sum(map(len, texts)) > MAX_TEXT_LENGTH:
        raise DocumentError("PDF 简历文字不能超过 80,000 字符")
    font = _registered_font(str(_font_path(font_path)))
    font_name = font.fontName
    unsupported = {
        character for text in texts for character in text
        if character not in "\r\n\t" and ord(character) not in font.face.charWidths
    }
    if unsupported:
        raise DocumentError("当前 PDF 字体不支持部分字符，请更换 PDF_FONT_PATH 或修改特殊字符")

    body = ParagraphStyle(
        "ResumeBody", fontName=font_name, fontSize=9.5, leading=13,
        spaceAfter=5, wordWrap="CJK",
    )
    name_style = ParagraphStyle(
        "ResumeName", parent=body, fontSize=21, leading=25, spaceAfter=9,
        keepWithNext=True,
    )
    section_style = ParagraphStyle(
        "ResumeSection", parent=body, fontSize=12.5, leading=16,
        spaceBefore=10, spaceAfter=5, keepWithNext=True,
    )
    entry_style = ParagraphStyle(
        "ResumeEntry", parent=body, fontSize=10.5, leading=14,
        spaceBefore=5, keepWithNext=True,
    )
    bullet_style = ParagraphStyle(
        "ResumeBullet", parent=body, leftIndent=10, bulletIndent=0,
        bulletFontName=font_name, bulletFontSize=9.5,
    )

    def paragraph(text: str, style: ParagraphStyle, bullet: str | None = None) -> Paragraph:
        markup = escape(text).replace("\t", "    ").replace("\n", "<br/>")
        return Paragraph(markup, style, bulletText=bullet)

    story: list[Flowable] = [paragraph(profile.contact.name, name_style)]
    contact = " | ".join(
        value for key, value in profile.contact.model_dump().items()
        if key != "name" and value
    )
    if contact:
        story.append(paragraph(contact, body))
    if profile.summary:
        story.extend([paragraph("Summary", section_style), paragraph(profile.summary, body)])
    if profile.skills:
        story.extend([paragraph("Skills", section_style), paragraph(", ".join(profile.skills), body)])
    for title, entries in resume_sections(profile):
        if not entries:
            continue
        story.append(paragraph(title, section_style))
        for entry in entries:
            heading, detail, bullets = resume_entry_text(entry)
            if heading:
                story.append(paragraph(heading, entry_style))
            if detail:
                story.append(paragraph(detail, body))
            story.extend(paragraph(bullet, bullet_style, "-") for bullet in bullets if bullet)
    result = BytesIO()
    document = SimpleDocTemplate(
        result, pagesize=letter, leftMargin=42, rightMargin=42,
        topMargin=36, bottomMargin=36,
        title="Resume - " + profile.contact.name, author=profile.contact.name,
    )
    try:
        document.build(story)
    except LayoutError as error:
        raise DocumentError("PDF 排版失败，请缩短超长字段后重新确认") from error
    return result.getvalue()
