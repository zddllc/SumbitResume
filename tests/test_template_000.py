import builtins
import os
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
from pypdf import PdfReader
from reportlab.platypus import Paragraph, Table

from resume_app.models import ResumeProfile
from resume_app.pdf import DEFAULT_TEMPLATE_ID, get_template, template_catalog, template_docx, template_pdf
from resume_app.pdf.rendering import load_fonts, normalized_text
from resume_app.pdf.templates.serif_000 import Serif000Template
from test_product import ProductTestCase, SOURCE


def complete_profile():
    return ResumeProfile.model_validate({
        **SOURCE.model_dump(),
        "contact": {
            "name": "Sample Applicant", "email": "applicant@example.test", "phone": "+1 555 0100",
            "location": "Remote", "linkedin": "https://linkedin.example.test/sample",
            "website": "https://portfolio.example.test",
        },
        "education": [{
            "institution": "Sample University", "degree": "PhD", "field": "Computer Science",
            "start_date": "2016", "end_date": "2020", "details": ["Education detail"],
        }],
        "publications": [{
            "title": "Verified Publication", "authors": ["First Author", "Second Author"],
            "venue": "Sample Conference", "date": "2025", "doi": "10.1234/example",
            "url": "https://example.test/paper", "details": ["Volume 2, pages 1-8"],
        }],
        "projects": [{"name": "Sample Project", "url": "https://example.test/project", "bullets": ["Project result"]}],
        "certifications": [{"name": "Sample Certificate", "issuer": "Sample Issuer", "date": "2024"}],
        "languages": [{"name": "中文", "proficiency": "母语"}],
    })


def extracted(content):
    return normalized_text("\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages))


class Template000Tests(unittest.TestCase):
    def test_catalog_adds_000_without_replacing_existing_templates_or_default(self):
        catalog = template_catalog()
        self.assertEqual(DEFAULT_TEMPLATE_ID, "classic-044")
        self.assertEqual({item["id"] for item in catalog["items"]}, {"classic-044", "serif-000", "simple"})
        self.assertEqual(get_template("serif-000").reference_document, "references/000.docx")
        self.assertEqual(get_template("classic-044").version, "reportlab-044-v1")
        self.assertEqual(get_template("simple").template_hash, "reportlab-v1")

    def test_measured_source_geometry_and_typography_are_used(self):
        template = get_template("serif-000")
        story = template.story(complete_profile(), load_fonts(serif=True), "")
        self.assertIsInstance(story[0], Table)
        self.assertEqual(sum(isinstance(item, Table) for item in story), 1)
        sections = [item for item in story if isinstance(item, Paragraph) and item.style.name == "Section000"]
        self.assertEqual([item.getPlainText() for item in sections[:3]], ["Industry Experience", "Education", "Publications"])
        self.assertTrue(all(item.style.fontName == "Times-Bold" and item.style.fontSize == 15 and item.style.leading == 19 for item in sections))
        self.assertTrue(all(item.style.backColor is None for item in sections))
        self.assertTrue(all("<u>" in item.text for item in sections))
        self.assertEqual(template.body_size, 11.5)
        self.assertEqual(template.publication_size, 10)
        content, metadata = template_pdf(complete_profile(), "serif-000")
        page = PdfReader(BytesIO(content)).pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 595.28, delta=0.1)
        self.assertAlmostEqual(float(page.mediabox.height), 841.89, delta=0.1)
        self.assertEqual(metadata, {"template_id": "serif-000", "template_hash": template.template_hash})

    def test_pdf_and_docx_preserve_every_fact_and_order(self):
        profile = complete_profile()
        profile.experience[0].bullets = ["Most important edited point", "Earlier point"]
        content, _ = template_pdf(profile, "serif-000", job_title="Unused target label")
        text = extracted(content)
        for value in (
            *profile.contact.model_dump().values(), "PhD", "Computer Science", "Sample University",
            "2016", "2020", "Education detail", "First Author", "Second Author", "Verified Publication",
            "Sample Conference", "2025", "10.1234/example", "https://example.test/paper",
            "Volume 2, pages 1-8", "Sample Project", "Project result", "Sample Certificate",
            "Sample Issuer", "2024", "中文", "母语",
        ):
            self.assertIn(normalized_text(value), text)
        self.assertLess(text.index("Mostimportanteditedpoint"), text.index("Earlierpoint"))
        self.assertLess(text.index("FirstAuthor"), text.index("SecondAuthor"))
        self.assertNotIn("TARGET:", text)
        document = Document(BytesIO(template_docx(profile, "serif-000")))
        word = normalized_text("\n".join(node.text or "" for node in document.element.iter(qn("w:t"))))
        for value in ("Most important edited point", "First Author", "Volume 2, pages 1-8", "中文", "Sample Applicant"):
            self.assertIn(normalized_text(value), word)
        section = document.sections[0]
        self.assertEqual((section.top_margin.pt, section.bottom_margin.pt), (72, 72))
        self.assertEqual((section.left_margin.pt, section.right_margin.pt), (54, 54))
        self.assertEqual(document.styles["Resume000 Body"].font.name, "Garamond")
        self.assertEqual(document.styles["Resume000 Body"].font.size.pt, 11.5)
        self.assertEqual(document.styles["Resume000 Section"].font.name, "Times New Roman")
        self.assertTrue(document.styles["Resume000 Section"].font.underline)
        self.assertEqual(document.styles["Resume000 Citation"].font.size.pt, 10)

    def test_long_bullets_and_unicode_names_continue_without_clipping(self):
        profile = complete_profile()
        profile.contact.name = "张三 " + "A" * 490
        profile.experience[0].bullets = [
            f"Ordered point {index:02d}: " + "reliable services " * 20 for index in range(40)
        ] + ["Long continuous detail " * 400 + "Final sentinel"]
        content, _ = template_pdf(profile, "serif-000")
        self.assertGreater(len(PdfReader(BytesIO(content)).pages), 2)
        text = extracted(content)
        self.assertIn(normalized_text(profile.contact.name), text)
        self.assertIn("Finalsentinel", text)
        self.assertLess(text.index("Orderedpoint00"), text.index("Orderedpoint39"))

    def test_rendering_never_reads_reference_or_calls_office(self):
        original_open = builtins.open

        def no_reference(file, *args, **kwargs):
            if isinstance(file, (str, os.PathLike)) and str(file).lower().endswith(".docx"):
                raise AssertionError("Runtime must not open reference DOCX")
            return original_open(file, *args, **kwargs)

        with (
            patch("builtins.open", side_effect=no_reference),
            patch("subprocess.run", side_effect=AssertionError("Office must not run")),
            patch.object(Serif000Template, "reference_document", "missing.docx"),
        ):
            self.assertTrue(template_pdf(SOURCE, "serif-000")[0].startswith(b"%PDF-"))
        with (
            patch("subprocess.run", side_effect=AssertionError("Office must not run")),
            patch.object(Serif000Template, "reference_document", "missing.docx"),
            patch("resume_app.pdf.templates.serif_000.Document", wraps=Document) as blank_document,
        ):
            self.assertTrue(template_docx(SOURCE, "serif-000").startswith(b"PK"))
            blank_document.assert_called_once_with()

    def test_reference_is_synthetic_and_not_used_in_runtime_hash(self):
        reference = Path(__file__).resolve().parents[1] / "resume_app" / "pdf" / "references" / "000.docx"
        document = Document(reference)
        self.assertEqual(document.core_properties.author, "Sample Applicant")
        self.assertEqual(document.core_properties.last_modified_by, "")
        with ZipFile(reference) as archive:
            content = b"\n".join(archive.read(name) for name in archive.namelist() if name.endswith((".xml", ".rels")))
        self.assertIn(b"Sample Applicant", content)
        regenerated = Document(BytesIO(template_docx(complete_profile(), "serif-000")))
        self.assertEqual(
            [node.text for node in document.element.iter(qn("w:t"))],
            [node.text for node in regenerated.element.iter(qn("w:t"))],
        )
        for forbidden in (b"SynologyDrive", b"Resume_latest"):
            self.assertNotIn(forbidden, content)
        before = get_template("serif-000").template_hash
        with patch.object(Serif000Template, "reference_document", "other.docx"):
            self.assertEqual(get_template("serif-000").template_hash, before)


class Template000ApiTests(ProductTestCase):
    def test_template_can_be_selected_and_downloaded_without_an_llm_call(self):
        self.setup_user()
        self.database.tailored_resumes.insert_one({
            "_id": "template000", "user_id": "local", "job_id": "local:123",
            "job": {"linkedin_id": "123", "title": "Engineer"},
            "resume": complete_profile().model_dump(), "review_status": "pending", "edit_token": "000-token",
        })
        with patch.object(self.workflow, "_complete", side_effect=AssertionError("No model call")):
            response = self.post("/api/tailored/template000/review", {
                "confirmed": True, "edit_token": "000-token", "template_id": "serif-000",
            })
        self.assertEqual(response.status_code, 200, response.get_json())
        detail = self.client.get("/api/tailored/template000").get_json()
        self.assertTrue(detail["pdf_ready"])
        self.assertEqual(detail["template_id"], "serif-000")
        pdf = self.client.get("/api/tailored/template000/pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertIn("VerifiedPublication", extracted(pdf.data))
        word = self.client.get("/api/tailored/template000/download")
        self.assertEqual(word.status_code, 200)
        self.assertEqual(Document(BytesIO(word.data)).styles["Resume000 Body"].font.name, "Garamond")
