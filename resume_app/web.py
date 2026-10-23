import hmac
import re
import secrets
import time
from io import BytesIO
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import (
    Blueprint, current_app, g, jsonify, request,
    send_file, session, url_for,
)
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash

from resume_app.documents import MAX_UPLOAD_BYTES, DocumentError, extract_text
from resume_app.errors import AppError
from resume_app.models import (
    CredentialInput, LLMSettings, LoginInput, PersonalInfo, ResumeProfile, SetupInput, resume_cache_data,
)
from resume_app.pdf import (
    DEFAULT_TEMPLATE_ID, LEGACY_TEMPLATE_ID, template_catalog, template_docx, template_pdf,
)
from resume_app.pdf.storage import pdf_files, pdf_ready, read_confirmed_pdf, store_pdf
from resume_app.storage import fingerprint, now


web = Blueprint("web", __name__)


def db():
    return current_app.extensions["resume_db"]


def workflow():
    return current_app.extensions["resume_workflow"]


def runner():
    return current_app.extensions["resume_runner"]


def vault():
    return current_app.extensions["resume_secrets"]


def payload() -> dict:
    data = request.get_json()
    if not isinstance(data, dict):
        raise AppError("请求内容必须是 JSON 对象")
    return data


def public(value):
    if isinstance(value, dict):
        return {("id" if key == "_id" else key): public(item) for key, item in value.items()}
    if isinstance(value, list):
        return [public(item) for item in value]
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
    return value


def require_user(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if g.user is None:
            raise AppError("请先登录", 401)
        return function(*args, **kwargs)
    return wrapped


@web.before_app_request
def protect_request():
    g.user = None
    if request.endpoint == "web.health":
        return None
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("X-CSRF-Token", "")
        if not supplied or not hmac.compare_digest(
            session["csrf"].encode("utf-8"), supplied.encode("utf-8")
        ):
            raise AppError("页面校验已过期，请刷新页面后重试", 403)
    user_id = session.get("user_id")
    if user_id:
        g.user = db().users.find_one({"_id": user_id})
    public_endpoints = {"web.auth_session", "web.auth_login", "web.auth_setup"}
    if request.path.startswith("/api/") and g.user is None and request.endpoint not in public_endpoints:
        raise AppError("请先登录", 401)
    return None


@web.after_app_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@web.app_errorhandler(AppError)
def app_error(error):
    return jsonify(error=str(error)), error.status


@web.app_errorhandler(ValidationError)
def invalid_input(error):
    messages = [
        f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
        for item in error.errors(include_input=False, include_url=False)[:5]
    ]
    return jsonify(error="字段校验失败", details=messages), 400


@web.app_errorhandler(RequestEntityTooLarge)
def oversized_upload(_error):
    return jsonify(error="上传内容不能超过 10 MB"), 413


@web.app_errorhandler(PyMongoError)
def mongo_error(error):
    current_app.logger.error("Mongo operation failed: %s", type(error).__name__)
    return jsonify(error="MongoDB 暂时不可用，请检查连接；不会降级到本地存储"), 503


@web.app_errorhandler(Exception)
def unexpected_error(error):
    if isinstance(error, HTTPException):
        status = error.code if error.code is not None else 500
        return jsonify(error=error.description), status
    current_app.logger.exception("Unhandled web request error")
    return jsonify(error="后台发生异常，请查看服务日志"), 500


def session_payload():
    return {
        "user": (
            {"id": g.user["_id"], "name": g.user["name"], "email": g.user["email"]}
            if g.user else None
        ),
        "setup_required": not bool(db().users.find_one({"_id": "local"}, {"_id": 1})),
        "csrf_token": session["csrf"],
    }


def start_session(user: dict):
    session.clear()
    session["user_id"] = user["_id"]
    session["csrf"] = secrets.token_urlsafe(32)
    session.permanent = True
    g.user = user


@web.get("/api/health")
def health():
    return jsonify(status="ok")


@web.get("/api/auth/session")
def auth_session():
    return jsonify(session_payload())


@web.post("/api/auth/login")
def auth_login():
    data = LoginInput.model_validate(payload())
    user = db().users.find_one({"_id": "local"})
    if not user:
        raise AppError("请先设置本机账号", 409)
    identity = request.remote_addr or "local"
    attempts = current_app.extensions["resume_login_attempts"]
    with current_app.extensions["resume_login_lock"]:
        times = [item for item in attempts.get(identity, []) if time.monotonic() - item < 600]
        attempts[identity] = times
        if len(times) >= 5:
            raise AppError("登录失败次数过多，请 10 分钟后再试", 429)
        times.append(time.monotonic())
    valid = check_password_hash(user["password_hash"], data.password)
    if data.email != user["email"] or not valid:
        raise AppError("邮箱或密码不正确", 401)
    with current_app.extensions["resume_login_lock"]:
        attempts.pop(identity, None)
    start_session(user)
    return jsonify(session_payload())


@web.post("/api/auth/setup")
def auth_setup():
    if db().users.find_one({"_id": "local"}, {"_id": 1}):
        raise AppError("单用户账号已创建，不能重复注册", 403)
    data = SetupInput.model_validate(payload())
    if not re.fullmatch(r"[^@\s]{1,100}@[^@\s.]+(?:\.[^@\s.]+)+", data.email):
        raise AppError("请输入有效邮箱")
    user = {
        "_id": "local", "email": data.email, "name": data.name,
        "password_hash": generate_password_hash(data.password, method="scrypt"),
        "created_at": now(),
    }
    try:
        db().users.insert_one(user)
    except DuplicateKeyError as error:
        raise AppError("账号已创建，请使用登录界面", 409) from error
    start_session(user)
    return jsonify(session_payload()), 201


@web.post("/api/auth/logout")
@require_user
def auth_logout():
    session.clear()
    session["csrf"] = secrets.token_urlsafe(32)
    g.user = None
    return jsonify(session_payload())


@web.get("/api/state")
@require_user
def state():
    user_id = g.user["_id"]
    settings = db().llm_settings.find_one({"_id": user_id})
    llm = {
        key: value for key, value in (settings or {}).items()
        if key not in {"_id", "key_encrypted", "updated_at"}
    }
    llm["key_saved"] = settings is not None
    credentials = []
    for item in db().credentials.find({"user_id": user_id}).sort("created_at", -1):
        secret = vault().decrypt(item["secret_encrypted"])
        credentials.append({
            "id": item["_id"], "site": item["site"], "label": item["label"],
            "username_hint": secret["username"][:2] + "***",
        })
    personal = (
        vault().decrypt(g.user["personal_encrypted"])
        if g.user.get("personal_encrypted") else PersonalInfo().model_dump()
    )
    resume = db().resumes.find_one({"_id": user_id})
    if resume:
        for field in ("draft", "confirmed"):
            if resume.get(field) is not None:
                resume[field] = ResumeProfile.model_validate(resume[field]).model_dump()
        if resume.get("pending_import"):
            candidate = resume["pending_import"]
            candidate["profile"] = ResumeProfile.model_validate(candidate["profile"]).model_dump()
    return jsonify(public({
        "user": {"name": g.user["name"], "email": g.user["email"]},
        "resume": resume,
        "personal": personal, "llm": llm, "credentials": credentials,
        "tasks": list(db().tasks.find({"user_id": user_id}).sort("created_at", -1).limit(10)),
    }))


@web.post("/api/llm")
@require_user
def save_llm():
    workflow().save_llm_settings(g.user["_id"], LLMSettings.model_validate(payload()))
    return jsonify(ok=True)


@web.delete("/api/llm")
@require_user
def delete_llm():
    db().llm_settings.delete_one({"_id": g.user["_id"]})
    return jsonify(ok=True)


@web.post("/api/resume/upload")
@require_user
def upload_resume():
    if request.form.get("consent") != "yes":
        raise AppError("需要确认同意将简历文字发送至你配置的模型服务")
    workflow().require_no_pending_import(g.user["_id"])
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise AppError("请选择简历文件")
    filename = Path(upload.filename.replace("\\", "/")).name
    content = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise AppError("简历文件不能超过 10 MB", 413)
    try:
        text = extract_text(filename, content)
    except DocumentError as error:
        raise AppError(str(error)) from error
    task_id = runner().parse_resume(g.user["_id"], filename, text)
    return jsonify(task_id=task_id), 202


def import_tokens(data):
    token, import_id = data.get("edit_token"), data.get("import_id")
    if not isinstance(token, str) or not token or not isinstance(import_id, str) or not import_id:
        raise AppError("请重新加载页面后对比上传结果")
    return token, import_id


@web.post("/api/resume/import/apply")
@require_user
def apply_resume_import():
    data = payload()
    token, import_id = import_tokens(data)
    workflow().apply_import(
        g.user["_id"], token, import_id, ResumeProfile.model_validate(data.get("profile")),
    )
    return jsonify(ok=True)


@web.post("/api/resume/import/discard")
@require_user
def discard_resume_import():
    token, import_id = import_tokens(payload())
    workflow().discard_import(g.user["_id"], token, import_id)
    return jsonify(ok=True)


@web.post("/api/resume/confirm")
@require_user
def confirm_resume():
    data = payload()
    token = data.get("edit_token")
    if not isinstance(token, str) or not token:
        raise AppError("请先上传并解析简历，或重新加载页面")
    workflow().confirm_resume(
        g.user["_id"], token, ResumeProfile.model_validate(data.get("profile"))
    )
    return jsonify(ok=True)


@web.post("/api/personal")
@require_user
def save_personal():
    info = PersonalInfo.model_validate(payload())
    db().users.update_one(
        {"_id": g.user["_id"]},
        {"$set": {"personal_encrypted": vault().encrypt(info.model_dump())}},
    )
    return jsonify(ok=True)


@web.post("/api/credentials")
@require_user
def save_credential():
    credential = CredentialInput.model_validate(payload())
    db().credentials.insert_one({
        "_id": uuid4().hex, "user_id": g.user["_id"], "site": credential.site,
        "label": credential.label, "created_at": now(),
        "secret_encrypted": vault().encrypt({
            "username": credential.username, "password": credential.password,
        }),
    })
    return jsonify(ok=True), 201


@web.delete("/api/credentials/<credential_id>")
@require_user
def delete_credential(credential_id):
    result = db().credentials.delete_one({"_id": credential_id, "user_id": g.user["_id"]})
    if not result.deleted_count:
        raise AppError("外站账号不存在", 404)
    return jsonify(ok=True)


@web.post("/api/browser/open")
@require_user
def open_browser():
    return jsonify(task_id=runner().open_browser(g.user["_id"])), 202


@web.post("/api/jobs/scan")
@require_user
def scan_jobs():
    data = payload()
    limit = data.get("limit", 20)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise AppError("单次职位上限必须是 1–100 的整数")
    if data.get("consent") is not True:
        raise AppError("需要确认同意将已确认简历和职位描述发送至模型服务")
    return jsonify(task_id=runner().scan(g.user["_id"], limit)), 202


@web.post("/api/tasks/<task_id>/cancel")
@require_user
def cancel_task(task_id):
    runner().cancel(g.user["_id"], task_id)
    return jsonify(ok=True)


@web.get("/api/tasks")
@require_user
def list_tasks():
    return jsonify(public({"items": list(
        db().tasks.find({"user_id": g.user["_id"]}).sort("created_at", -1).limit(10)
    )}))


@web.get("/api/tasks/<task_id>")
@require_user
def task_detail(task_id):
    task = db().tasks.find_one({"_id": task_id, "user_id": g.user["_id"]})
    if not task:
        raise AppError("任务不存在", 404)
    return jsonify(public(task))


@web.get("/api/jobs")
@require_user
def list_jobs():
    try:
        page = int(request.args.get("page", "1"))
    except ValueError as error:
        raise AppError("页码必须是整数") from error
    if not 1 <= page <= 100000:
        raise AppError("页码超出范围")
    user_id = g.user["_id"]
    query = {"user_id": user_id}
    result = []
    source = db().resumes.find_one({"_id": user_id}) or {}
    for job in db().jobs.find(query, {"description": 0}).sort("last_seen_at", -1).skip((page - 1) * 25).limit(25):
        tailored = db().tailored_resumes.find_one(
            {"user_id": user_id, "job_id": job["_id"]},
            {"source_resume": 0, "job": 0, "plan": 0},
            sort=[("created_at", -1)],
        )
        if tailored:
            tailored["pdf_ready"] = pdf_ready(db(), user_id, tailored)
            tailored.pop("resume", None)
        job["tailored"] = tailored
        job["current_source"] = bool(
            tailored and tailored.get("source_hash") == source.get("confirmed_hash")
            and tailored.get("description_hash") == job.get("description_hash")
        )
        result.append(job)
    return jsonify(public({
        "items": result, "page": page, "total": db().jobs.count_documents(query),
    }))


@web.get("/api/jobs/<linkedin_id>")
@require_user
def job_detail(linkedin_id):
    user_id = g.user["_id"]
    job = db().jobs.find_one({"user_id": user_id, "linkedin_id": linkedin_id})
    if not job:
        raise AppError("职位不存在", 404)
    versions = list(db().tailored_resumes.find(
        {"user_id": user_id, "job_id": job["_id"]},
        {"resume": 0, "source_resume": 0, "job": 0, "plan": 0},
    ).sort("created_at", -1).limit(20))
    return jsonify(public({"job": job, "versions": versions}))


@web.post("/api/jobs/<linkedin_id>/generate")
@require_user
def generate_stored_job(linkedin_id):
    if payload().get("consent") is not True:
        raise AppError("需要确认同意将已保存的职位描述和已确认底板发送给模型")
    return jsonify(task_id=runner().tailor_stored(g.user["_id"], linkedin_id)), 202


def owned_tailored(resume_id: str) -> dict:
    stored = db().tailored_resumes.find_one({"_id": resume_id, "user_id": g.user["_id"]})
    if not stored:
        raise AppError("定制简历不存在", 404)
    if not stored.get("edit_token"):
        db().tailored_resumes.update_one(
            {"_id": resume_id, "user_id": g.user["_id"], "$or": [
                {"edit_token": {"$exists": False}}, {"edit_token": {"$in": [None, ""]}},
            ]},
            {"$set": {"edit_token": uuid4().hex}},
        )
        stored = db().tailored_resumes.find_one({"_id": resume_id, "user_id": g.user["_id"]})
        if not stored:
            raise AppError("定制简历不存在", 404)
    return stored


def latest_source(stored: dict) -> dict:
    base = db().resumes.find_one({"_id": g.user["_id"]}) or {}
    confirmed = base.get("confirmed")
    if confirmed is None:
        return {"status": "unavailable", "confirmed": None, "confirmed_hash": None,
                "confirmed_at": None, "has_pending_changes": bool(base.get("draft") or base.get("pending_import"))}
    profile = ResumeProfile.model_validate(confirmed)
    source_hash = fingerprint(resume_cache_data(profile))
    previous_hash = stored.get("source_hash")
    if not previous_hash and stored.get("source_resume") is not None:
        previous_hash = fingerprint(resume_cache_data(ResumeProfile.model_validate(stored["source_resume"])))
    return {
        "status": "unknown" if not previous_hash else "current" if previous_hash == source_hash else "changed",
        "confirmed": profile.model_dump(), "confirmed_hash": source_hash,
        "confirmed_at": base.get("confirmed_at"),
        "has_pending_changes": bool(base.get("draft") or base.get("pending_import")),
    }


@web.get("/api/tailored/<resume_id>/source")
@require_user
def tailored_source(resume_id):
    return jsonify(public(latest_source(owned_tailored(resume_id))))


@web.get("/api/tailored/<resume_id>")
@require_user
def get_tailored(resume_id):
    stored = owned_tailored(resume_id)
    current_job = db().jobs.find_one({
        "_id": stored["job_id"], "user_id": g.user["_id"],
    }) or {}
    stored["application"] = {
        "kind": current_job.get("application_kind", "unavailable"),
        "url": current_job.get("application_url"),
        "landing_url": current_job.get("application_landing_url"),
        "source": current_job.get("application_url_source"),
        "error": current_job.get("application_error"),
    }
    stored["pdf_ready"] = pdf_ready(db(), g.user["_id"], stored)
    stored["latest_source"] = latest_source(stored)
    # Validate the artifact against the original stored shape before adding defaults.
    stored["resume"] = ResumeProfile.model_validate(stored["resume"]).model_dump()
    if "source_resume" in stored:
        stored["source_resume"] = ResumeProfile.model_validate(stored["source_resume"]).model_dump()
    return jsonify(public(stored))


@web.get("/api/resume-templates")
@require_user
def get_resume_templates():
    return jsonify(template_catalog())


@web.post("/api/tailored/<resume_id>/review")
@require_user
def review_tailored(resume_id):
    stored = owned_tailored(resume_id)
    data = payload()
    if data.get("confirmed") is not True:
        raise AppError("请核对简历内容后再确认")
    if not data.get("edit_token") or data.get("edit_token") != stored["edit_token"]:
        raise AppError("这份定制简历已更新，请重新加载后核对，避免覆盖其他修改", 409)
    profile = ResumeProfile.model_validate(data.get("profile", stored["resume"]))
    try:
        content, template = template_pdf(
            profile, data.get("template_id", DEFAULT_TEMPLATE_ID),
            job_title=stored["job"].get("title", ""),
            font_path=current_app.config["PDF_FONT_PATH"],
        )
    except DocumentError as error:
        raise AppError(str(error)) from error
    file_id = uuid4().hex
    artifact = store_pdf(
        db(), g.user["_id"], resume_id, file_id,
        fingerprint(profile.model_dump()), content, template=template,
    )
    token = uuid4().hex
    reviewed_at = now()
    updated = db().tailored_resumes.update_one(
        {"_id": resume_id, "user_id": g.user["_id"], "edit_token": stored["edit_token"]},
        {"$set": {
            "resume": profile.model_dump(), "review_status": "reviewed",
            "reviewed_at": reviewed_at, "edit_token": token, "pdf": artifact,
            "template_id": template["template_id"],
        }},
    )
    if not updated.matched_count:
        pdf_files(db()).delete(file_id)
        raise AppError("确认过程中简历已被更新，请重新加载后再确认", 409)
    return jsonify(public({
        "ok": True, "edit_token": token, "pdf_url": url_for("web.download_pdf", resume_id=resume_id),
        "pdf": artifact, "pdf_ready": True, "reviewed_at": reviewed_at,
    }))


@web.get("/api/tailored/<resume_id>/pdf")
@require_user
def download_pdf(resume_id):
    stored = owned_tailored(resume_id)
    content = read_confirmed_pdf(db(), g.user["_id"], stored)
    return send_file(
        BytesIO(content), mimetype="application/pdf",
        as_attachment=request.args.get("download") == "1",
        download_name=f"resume-{stored['job']['linkedin_id']}.pdf",
    )


@web.get("/api/tailored/<resume_id>/download")
@require_user
def download_tailored(resume_id):
    stored = owned_tailored(resume_id)
    profile = ResumeProfile.model_validate(stored["resume"])
    try:
        document = BytesIO(template_docx(
            profile, stored.get(
                "template_id",
                LEGACY_TEMPLATE_ID if stored.get("review_status") == "reviewed" else DEFAULT_TEMPLATE_ID,
            ), job_title=stored["job"].get("title", ""),
        ))
    except DocumentError as error:
        raise AppError(str(error)) from error
    return send_file(
        document,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True, download_name=f"resume-{stored['job']['linkedin_id']}.docx",
    )
