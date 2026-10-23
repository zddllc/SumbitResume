"""Persist and verify confirmed PDF artifacts without re-rendering downloads."""

import hashlib

from gridfs import GridFS, NoFile
from pymongo.database import Database

from resume_app.errors import AppError
from resume_app.storage import fingerprint, now


def pdf_files(db: Database) -> GridFS:
    return GridFS(db, collection="resume_pdfs")


def pdf_ready(db: Database, user_id: str, stored: dict) -> bool:
    artifact = stored.get("pdf")
    return bool(
        stored.get("review_status") == "reviewed"
        and artifact
        and artifact.get("profile_hash") == fingerprint(stored["resume"])
        and artifact.get("template_id") == stored.get("template_id")
        and pdf_files(db).exists({
            "_id": artifact["file_id"], "metadata.user_id": user_id,
            "metadata.resume_id": stored["_id"],
            "metadata.profile_hash": artifact["profile_hash"],
            "metadata.template_id": artifact.get("template_id"),
            "metadata.template_hash": artifact.get("template_hash"),
        })
    )


def read_confirmed_pdf(db: Database, user_id: str, stored: dict) -> bytes:
    if not pdf_ready(db, user_id, stored):
        raise AppError("尚无匹配当前简历的已确认 PDF，请核对后确认生成", 409)
    artifact = stored["pdf"]
    try:
        with pdf_files(db).get(artifact["file_id"]) as file:
            metadata = file.metadata or {}
            if (
                metadata.get("user_id") != user_id
                or metadata.get("resume_id") != stored["_id"]
                or metadata.get("profile_hash") != artifact["profile_hash"]
                or metadata.get("template_id") != artifact.get("template_id")
                or metadata.get("template_hash") != artifact.get("template_hash")
            ):
                raise AppError("PDF 与当前简历不匹配，请重新确认生成", 409)
            content = file.read()
    except NoFile as error:
        raise AppError("已确认 PDF 文件丢失，请重新确认生成", 409) from error
    if (
        hashlib.sha256(content).hexdigest() != artifact["sha256"]
        or not content.startswith(b"%PDF-")
    ):
        raise AppError("PDF 文件完整性校验失败，请重新确认生成", 409)
    return content


def store_pdf(
    db: Database, user_id: str, resume_id: str, file_id: str,
    profile_hash: str, content: bytes,
    *, template: dict[str, str] | None = None,
) -> dict:
    digest = hashlib.sha256(content).hexdigest()
    created = now()
    pdf_files(db).put(
        content, _id=file_id, filename=f"resume-{resume_id}.pdf",
        contentType="application/pdf",
        metadata={
            "user_id": user_id, "resume_id": resume_id,
            "profile_hash": profile_hash, "sha256": digest, "created_at": created,
            **(template or {}),
        },
    )
    return {
        "file_id": file_id, "sha256": digest, "profile_hash": profile_hash,
        "size": len(content), "created_at": created,
        **(template or {}),
    }
