"""Mongo persistence and local authenticated encryption."""

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from pymongo.database import Database


def now() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SecretStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            path.parent.chmod(0o700)
        if not path.exists():
            values = {
                "session_key": secrets.token_hex(32),
                "encryption_key": Fernet.generate_key().decode("ascii"),
            }
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(values, stream)
            except FileExistsError:
                pass
        if os.name == "posix":
            path.chmod(0o600)
        with path.open(encoding="utf-8") as stream:
            stored = json.load(stream)
        self.session_key: str = stored["session_key"]
        if not isinstance(self.session_key, str) or len(self.session_key) < 32:
            raise ValueError("Local session key is invalid; do not replace existing keys")
        self.cipher = Fernet(stored["encryption_key"].encode("ascii"))

    def encrypt(self, value: object) -> str:
        return self.cipher.encrypt(
            json.dumps(value, ensure_ascii=False).encode("utf-8")
        ).decode("ascii")

    def decrypt(self, value: str) -> Any:
        try:
            return json.loads(self.cipher.decrypt(value.encode("ascii")))
        except InvalidToken as error:
            raise RuntimeError(
                "加密数据无法解密，请恢复原有 .instance/secrets.json；不要重新生成密钥"
            ) from error


def initialize_database(db: Database) -> None:
    existing = set(db.list_collection_names())
    for name in ("users", "resumes", "llm_settings", "jobs", "tailored_resumes",
                 "credentials", "tasks", "metadata", "llm_calls"):
        if name not in existing:
            db.create_collection(name)
    db.users.create_index("email", unique=True)
    db.jobs.create_index([("user_id", 1), ("linkedin_id", 1)], unique=True)
    db.jobs.create_index([("user_id", 1), ("last_seen_at", -1)])
    db.tailored_resumes.create_index([("user_id", 1), ("job_id", 1), ("created_at", -1)])
    db.credentials.create_index([("user_id", 1), ("site", 1)])
    db.tasks.create_index([("user_id", 1), ("created_at", -1)])
    db.llm_calls.create_index([("user_id", 1), ("created_at", -1)])
    db.llm_calls.create_index([("user_id", 1), ("task_id", 1)])
    db.llm_calls.create_index([("user_id", 1), ("context.job_id", 1), ("created_at", -1)])
    db.metadata.update_one(
        {"_id": "schema"},
        {"$setOnInsert": {"version": 1, "created_at": now()}},
        upsert=True,
    )
    db.tasks.update_many(
        {"status": {"$in": ["queued", "running", "cancelling"]}},
        {"$set": {
            "status": "interrupted", "finished_at": now(),
            "error": "后端已重启，任务中断。可重新操作，已保存的结果会复用。",
        }},
    )
    db.llm_calls.update_many(
        {"status": {"$in": ["started", "request_saved", "response_received"]}},
        {"$set": {
            "status": "interrupted", "finished_at": now(),
            "error": {"type": "BackendRestarted", "stage": "unknown"},
        }},
    )
