import logging
from datetime import timedelta
from pathlib import Path
from threading import Lock

from flask import Flask
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError
from werkzeug.exceptions import NotFound
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.middleware.proxy_fix import ProxyFix

from resume_app.config import ROOT, base_path, load_config
from resume_app.linkedin import LinkedInBrowser
from resume_app.documents import MAX_UPLOAD_BYTES
from resume_app.llm_workflow import ResumeWorkflow
from resume_app.storage import SecretStore, initialize_database
from resume_app.tasks import TaskRunner


def create_app(config: dict | None = None, database: Database | None = None) -> Flask:
    app = Flask(
        __name__, instance_path=str(ROOT / ".instance"),
        static_folder=None, template_folder=None,
    )
    app.config.update(load_config())
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES + 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    if config:
        app.config.update(config)
    prefix = base_path(app.config["APP_BASE_PATH"])
    app.config["APP_BASE_PATH"] = prefix
    app.config["APPLICATION_ROOT"] = prefix or "/"
    app.config["SESSION_COOKIE_PATH"] = prefix + "/" if prefix else "/"
    if database is None:
        client = MongoClient(
            app.config["MONGO_URI"], serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000, socketTimeoutMS=15000, tz_aware=True,
        )
        try:
            client.admin.command("ping")
        except PyMongoError:
            client.close()
            raise
        database = client[app.config["MONGO_DB"]]
        app.extensions["resume_mongo_client"] = client
    secret_path = Path(app.config["INSTANCE_DIR"]) / "secrets.json"
    try:
        encrypted_exists = (
            database.llm_settings.find_one({"key_encrypted": {"$exists": True}}, {"_id": 1})
            or database.credentials.find_one({"secret_encrypted": {"$exists": True}}, {"_id": 1})
            or database.users.find_one({"personal_encrypted": {"$exists": True}}, {"_id": 1})
        )
        if not secret_path.exists() and encrypted_exists:
            raise RuntimeError(
                "数据库已有加密信息，但本机密钥缺失。请先安全迁移原 secrets.json，禁止生成新密钥覆盖。"
            )
        secrets = SecretStore(secret_path)
        app.config["SECRET_KEY"] = secrets.session_key
        initialize_database(database)
    except Exception:
        client = app.extensions.get("resume_mongo_client")
        if client is not None:
            client.close()
        raise
    workflow = ResumeWorkflow(database, secrets)
    browser = LinkedInBrowser(
        Path(app.config["BROWSER_PROFILE_ROOT"]),
        app.config["CHROME_PATH"], app.config["CHROMEDRIVER_PATH"],
    )
    app.extensions.update(
        resume_db=database, resume_secrets=secrets, resume_workflow=workflow,
        resume_runner=TaskRunner(database, workflow, browser),
        resume_login_attempts={}, resume_login_lock=Lock(),
    )
    from resume_app.web import web
    app.register_blueprint(web)
    if app.config["TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_prefix=0)
    if prefix:
        app.wsgi_app = DispatcherMiddleware(NotFound(), {prefix: app.wsgi_app})
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    return app
