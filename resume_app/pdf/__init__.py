"""Public template catalog and export entry points."""

from pathlib import Path

from resume_app.documents import DocumentError
from resume_app.models import ResumeProfile
from resume_app.pdf.rendering import validate_pdf, validate_profile
from resume_app.pdf.templates.base import ResumeTemplate
from resume_app.pdf.templates.classic_044 import Classic044Template
from resume_app.pdf.templates.simple import SimpleTemplate
from resume_app.pdf.templates.serif_000 import Serif000Template


DEFAULT_TEMPLATE_ID = "classic-044"
LEGACY_TEMPLATE_ID = "simple"
TEMPLATES: tuple[ResumeTemplate, ...] = (Classic044Template(), Serif000Template(), SimpleTemplate())


def get_template(template_id: object) -> ResumeTemplate:
    for template in TEMPLATES:
        if template.id == template_id:
            return template
    raise DocumentError("未知简历模板，请重新选择")


def template_catalog() -> dict:
    return {
        "default_template_id": DEFAULT_TEMPLATE_ID,
        "items": [{
            "id": template.id, "name": template.name,
            "description": template.description, "preview_url": template.preview_url,
        } for template in TEMPLATES],
    }


def template_pdf(
    profile: ResumeProfile, template_id: object = DEFAULT_TEMPLATE_ID, *,
    job_title: str = "", font_path: str | Path | None = None,
) -> tuple[bytes, dict[str, str]]:
    template = get_template(template_id)
    content = template.render(profile, job_title=job_title, font_path=font_path)
    texts = validate_profile(profile)
    if template.uses_job_title and job_title:
        texts.append(job_title)
    validate_pdf(content, texts)
    return content, {"template_id": template.id, "template_hash": template.template_hash}


def template_docx(
    profile: ResumeProfile, template_id: object = DEFAULT_TEMPLATE_ID, *, job_title: str = "",
) -> bytes:
    return get_template(template_id).render_docx(profile, job_title=job_title)
