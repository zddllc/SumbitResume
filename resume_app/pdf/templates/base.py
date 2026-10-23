"""A template owns its layout; rendering and persistence remain shared."""

from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.platypus import Flowable, SimpleDocTemplate
from reportlab.platypus.doctemplate import LayoutError

from resume_app.documents import DocumentError, resume_docx
from resume_app.models import ResumeProfile
from resume_app.pdf.rendering import PdfFonts, load_fonts, validate_profile, validate_text
from resume_app.storage import fingerprint


class ResumeTemplate(ABC):
    id: str
    name: str
    description: str
    version: str
    preview_url: str | None = None
    reference_document: str | None = None
    page_size: tuple[float, float] = letter
    left_margin = 42.0
    right_margin = 42.0
    top_margin = 36.0
    bottom_margin = 36.0
    serif = False
    uses_job_title = False

    @property
    def content_width(self) -> float:
        return self.page_size[0] - self.left_margin - self.right_margin - 12

    @property
    def template_hash(self) -> str:
        return fingerprint({"id": self.id, "version": self.version})

    @abstractmethod
    def story(self, profile: ResumeProfile, fonts: PdfFonts, job_title: str) -> list[Flowable]:
        ...

    def render(
        self, profile: ResumeProfile, *, job_title: str = "",
        font_path: str | Path | None = None,
    ) -> bytes:
        validate_profile(profile)
        validate_text(job_title)
        fonts = load_fonts(font_path, serif=self.serif)
        result = BytesIO()
        document = SimpleDocTemplate(
            result, pagesize=self.page_size,
            leftMargin=self.left_margin, rightMargin=self.right_margin,
            topMargin=self.top_margin, bottomMargin=self.bottom_margin,
            title="Resume - " + profile.contact.name, author=profile.contact.name,
        )
        try:
            document.build(self.story(profile, fonts, job_title))
        except LayoutError as error:
            raise DocumentError("PDF 排版失败，请缩短超长字段后重新确认") from error
        return result.getvalue()

    def render_docx(self, profile: ResumeProfile, *, job_title: str = "") -> bytes:
        return resume_docx(profile).getvalue()
