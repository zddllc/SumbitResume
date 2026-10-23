"""000: a compact serif resume with an identity rule and underlined headings."""

from collections.abc import Sequence
from io import BytesIO

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_UNDERLINE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips
from docx.styles.style import ParagraphStyle as WordParagraphStyle
from reportlab.lib.colors import black
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable, Paragraph, Table, TableStyle

from resume_app.documents import DocumentError, publication_details, resume_entry_text
from resume_app.models import Education, Experience, Model, Publication, ResumeProfile
from resume_app.pdf.rendering import PdfFonts, paragraph, validate_profile, validate_text
from resume_app.pdf.templates.base import ResumeTemplate


class Serif000Template(ResumeTemplate):
    id = "serif-000"
    name = "衬线履历 · 000"
    description = "Garamond 正文、下划线章节标题、顶部细横线及紧凑论文排版。"
    version = "reportlab-000-v1"
    reference_document = "references/000.docx"
    page_size = A4
    # Compensate for the shared ReportLab frame's six-point inner padding.
    left_margin = right_margin = 54 - 6
    top_margin = bottom_margin = 72 - 6
    serif = True
    name_size = 14
    body_size = 11.5
    section_size = 15
    publication_size = 10

    def sections(self, profile: ResumeProfile) -> tuple[tuple[str, str | Sequence[Model]], ...]:
        return (
            ("Industry Experience", profile.experience), ("Education", profile.education),
            ("Publications", profile.publications), ("Technical Skills", ", ".join(profile.skills)),
            ("Projects", profile.projects), ("Certifications", profile.certifications),
            ("Languages", profile.languages),
        )

    def entry_text(self, entry: Model) -> tuple[str, str, list[str]]:
        if isinstance(entry, Experience):
            dates = " - ".join(value for value in (entry.start_date, entry.end_date) if value)
            return entry.title, " | ".join(value for value in (entry.company, entry.location, dates) if value), entry.bullets
        if isinstance(entry, Education):
            return (
                " | ".join(value for value in (entry.degree, entry.field) if value),
                " | ".join(value for value in (entry.institution, entry.start_date, entry.end_date) if value),
                entry.details,
            )
        if isinstance(entry, Publication):
            citation = ". ".join(value for value in (", ".join(entry.authors), entry.title) if value)
            detail = publication_details(entry, include_authors=False)
            return "", " | ".join(value for value in (citation, detail) if value), entry.details
        return resume_entry_text(entry)

    def story(self, profile: ResumeProfile, fonts: PdfFonts, job_title: str) -> list[Flowable]:
        body = ParagraphStyle(
            "Body000", fontName=fonts.regular.fontName, fontSize=self.body_size,
            leading=14, textColor=black, spaceAfter=4, wordWrap="CJK",
        )
        name_style = ParagraphStyle(
            "Name000", parent=body, fontSize=self.name_size, leading=17,
            spaceAfter=3, keepWithNext=True,
        )
        contact_style = ParagraphStyle("Contact000", parent=body, fontSize=12, leading=14)
        right_contact = ParagraphStyle("RightContact000", parent=contact_style, alignment=TA_RIGHT)
        section_style = ParagraphStyle(
            "Section000", parent=body, fontName="Times-Bold",
            fontSize=self.section_size, leading=19,
            spaceBefore=9, spaceAfter=5, keepWithNext=True,
        )
        role_style = ParagraphStyle(
            "Role000", parent=body, fontSize=12, leading=15,
            spaceBefore=5, spaceAfter=2, keepWithNext=True,
        )
        detail_style = ParagraphStyle("Detail000", parent=body, keepWithNext=True)
        bullet_style = ParagraphStyle(
            "Bullet000", parent=body, leftIndent=14, bulletIndent=2,
            bulletFontName=fonts.regular.fontName, bulletFontSize=self.body_size,
        )
        citation_style = ParagraphStyle(
            "Citation000", parent=body, fontSize=self.publication_size, leading=12,
            spaceBefore=3, keepWithNext=False,
        )
        contact = profile.contact
        rows = [[paragraph(contact.name, name_style, fonts, bold=True),
                 paragraph(contact.email, right_contact, fonts)]]
        links = "\n".join(value for value in (contact.linkedin, contact.website) if value)
        location = " | ".join(value for value in (contact.phone, contact.location) if value)
        if links or location:
            rows.append([paragraph(links, contact_style, fonts), paragraph(location, right_contact, fonts)])
        header = Table(
            rows, colWidths=[self.content_width * 0.55, self.content_width * 0.45],
            hAlign="LEFT", splitInRow=1,
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, black),
            ]),
        )
        story: list[Flowable] = [header]
        if profile.summary:
            story.append(paragraph(profile.summary, body, fonts))
        for title, content in self.sections(profile):
            if not content:
                continue
            story.append(Paragraph(f"<u>{title}</u>", section_style))
            if isinstance(content, str):
                story.append(paragraph(content, body, fonts))
                continue
            for entry in content:
                heading, detail, bullets = self.entry_text(entry)
                is_publication = isinstance(entry, Publication)
                if heading:
                    story.append(paragraph(
                        heading, role_style, fonts,
                        italic=isinstance(entry, Experience), bold=not isinstance(entry, Experience),
                    ))
                if detail:
                    story.append(paragraph(detail, citation_style if is_publication else detail_style, fonts))
                for bullet in bullets:
                    if bullet:
                        story.append(paragraph(
                            bullet, citation_style if is_publication else bullet_style,
                            fonts, bullet=None if is_publication else "\u2022",
                        ))
        return story

    def render_docx(self, profile: ResumeProfile, *, job_title: str = "") -> bytes:
        validate_profile(profile)
        validate_text(job_title)
        document = Document()
        page = document.sections[0]
        page.page_width, page.page_height = Twips(11906), Twips(16838)
        page.left_margin = page.right_margin = Pt(54)
        page.top_margin = page.bottom_margin = Pt(72)

        def style(name: str, size: float, *, bold: bool = False, italic: bool = False) -> WordParagraphStyle:
            result = document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            if not isinstance(result, WordParagraphStyle):
                raise DocumentError("无法创建 Word 段落样式")
            result.font.name, result.font.size = "Garamond", Pt(size)
            result.font.bold, result.font.italic = bold, italic
            result.paragraph_format.space_after = Pt(4)
            result.paragraph_format.line_spacing = 1.05
            result.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
            fonts = result.element.find(".//" + qn("w:rFonts"))
            if fonts is not None:
                fonts.set(qn("w:eastAsia"), "SimSun")
            return result

        body = style("Resume000 Body", self.body_size)
        name_style = style("Resume000 Name", self.name_size, bold=True)
        name_style.font.small_caps = True
        contact_style = style("Resume000 Contact", 12)
        section_style = style("Resume000 Section", self.section_size, bold=True)
        section_style.font.name = "Times New Roman"
        section_style.font.underline = WD_UNDERLINE.SINGLE
        section_style.paragraph_format.line_spacing = Pt(19)
        section_style.paragraph_format.space_before = Pt(9)
        section_style.paragraph_format.keep_with_next = True
        role_style = style("Resume000 Role", 12, italic=True)
        role_style.paragraph_format.keep_with_next = True
        entry_style = style("Resume000 Entry", self.body_size, bold=True)
        entry_style.paragraph_format.keep_with_next = True
        detail_style = style("Resume000 Detail", self.body_size)
        detail_style.paragraph_format.keep_with_next = True
        bullet_style = style("Resume000 Bullet", self.body_size)
        bullet_style.base_style = document.styles["List Bullet"]
        bullet_style.paragraph_format.left_indent = Pt(14)
        bullet_style.paragraph_format.first_line_indent = Pt(-12)
        citation_style = style("Resume000 Citation", self.publication_size)

        contact = profile.contact
        table = document.add_table(rows=2, cols=2)
        table.autofit = False
        for index, ratio in enumerate((0.55, 0.45)):
            width = Pt((page.page_width.pt - 108) * ratio)
            table.columns[index].width = width
            for cell in table.columns[index].cells:
                cell.width = width
        table.cell(0, 0).paragraphs[0].text = contact.name
        table.cell(0, 0).paragraphs[0].style = name_style
        table.cell(0, 1).paragraphs[0].text = contact.email
        table.cell(1, 0).paragraphs[0].text = "\n".join(value for value in (contact.linkedin, contact.website) if value)
        table.cell(1, 1).paragraphs[0].text = " | ".join(value for value in (contact.phone, contact.location) if value)
        for row in table.rows:
            for index, cell in enumerate(row.cells):
                for item in cell.paragraphs:
                    if item.style != name_style:
                        item.style = contact_style
                if index == 1:
                    for item in cell.paragraphs:
                        item.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        borders = OxmlElement("w:tblBorders")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "4")
        bottom.set(qn("w:color"), "000000")
        borders.append(bottom)
        table._tbl.tblPr.append(borders)

        if profile.summary:
            document.add_paragraph(profile.summary, body)
        for title, content in self.sections(profile):
            if not content:
                continue
            document.add_paragraph(title, section_style)
            if isinstance(content, str):
                document.add_paragraph(content, body)
                continue
            for entry in content:
                heading, detail, bullets = self.entry_text(entry)
                is_publication = isinstance(entry, Publication)
                if heading:
                    document.add_paragraph(heading, role_style if isinstance(entry, Experience) else entry_style)
                if detail:
                    document.add_paragraph(detail, citation_style if is_publication else detail_style)
                for bullet in bullets:
                    if bullet:
                        document.add_paragraph(bullet, citation_style if is_publication else bullet_style)
        document.core_properties.title = ("Resume - " + contact.name)[:255]
        document.core_properties.author = contact.name[:255]
        document.core_properties.last_modified_by = ""
        result = BytesIO()
        document.save(result)
        return result.getvalue()
