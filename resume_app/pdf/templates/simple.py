"""The existing single-column layout, kept as an explicit template."""

from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable

from resume_app.documents import resume_entry_text, resume_sections
from resume_app.models import ResumeProfile
from resume_app.pdf.rendering import PdfFonts, paragraph
from resume_app.pdf.templates.base import ResumeTemplate


class SimpleTemplate(ResumeTemplate):
    id = "simple"
    name = "简洁单栏"
    description = "原有的单栏 PDF 版式。"
    version = "reportlab-v1"

    @property
    def template_hash(self) -> str:
        return self.version

    def story(self, profile: ResumeProfile, fonts: PdfFonts, job_title: str) -> list[Flowable]:
        font_name = fonts.regular.fontName
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
        story: list[Flowable] = [paragraph(profile.contact.name, name_style, fonts)]
        contact = " | ".join(
            value for key, value in profile.contact.model_dump().items()
            if key != "name" and value
        )
        if contact:
            story.append(paragraph(contact, body, fonts))
        if profile.summary:
            story.extend([
                paragraph("Summary", section_style, fonts),
                paragraph(profile.summary, body, fonts),
            ])
        if profile.skills:
            story.extend([
                paragraph("Skills", section_style, fonts),
                paragraph(", ".join(profile.skills), body, fonts),
            ])
        for title, entries in resume_sections(profile):
            if not entries:
                continue
            story.append(paragraph(title, section_style, fonts))
            for entry in entries:
                heading, detail, bullets = resume_entry_text(entry)
                if heading:
                    story.append(paragraph(heading, entry_style, fonts))
                if detail:
                    story.append(paragraph(detail, body, fonts))
                story.extend(
                    paragraph(bullet, bullet_style, fonts, bullet="-")
                    for bullet in bullets if bullet
                )
        return story
