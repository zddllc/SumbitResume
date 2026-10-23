"""Fail-closed model auditing, independent of mutable resume records."""

import hashlib
import json
from collections.abc import Callable
from time import perf_counter
from types import TracebackType
from typing import Literal
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from gridfs import GridFS, NoFile
from pymongo.database import Database
from pymongo.errors import InvalidOperation, PyMongoError

from resume_app.errors import AppError
from resume_app.models import LLMSettings
from resume_app.storage import now


INLINE_BODY_LIMIT = 256 * 1024
MAX_HTTP_ATTEMPTS = 21


class AuditStorageError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "模型审计入库失败，本次操作已停止，业务结果未保存。"
            "请求可能已发送，请先检查数据库，避免重复调用计费。",
            503,
        )


def audit_files(db: Database) -> GridFS:
    return GridFS(db, collection="llm_audit_payloads")


class LLMCallAudit:
    def __init__(
        self, db: Database, user_id: str, operation: Literal["resume_parse", "job_tailor"],
        settings: LLMSettings, *, context: dict[str, str], task_id: str | None = None,
    ) -> None:
        self.db, self.user_id = db, user_id
        self.id = uuid4().hex
        self.secret = settings.api_key
        self.metadata = {
            "_id": self.id, "user_id": user_id, "operation": operation, "task_id": task_id,
            "context": {key: self.redact(value) for key, value in context.items()},
            "llm": {"provider": settings.provider, "model": self.redact(settings.model),
                    "api_version": self.redact(settings.api_version)},
        }
        self.failure: AuditStorageError | None = None
        self.stage = "setup"
        self.started = perf_counter()
        self.attempt_id = ""
        self.attempt_started = self.started
        self.attempt_count = 0

    def redact(self, value: str) -> str:
        if not self.secret:
            return value
        return value.replace(self.secret, "[REDACTED]").replace(
            json.dumps(self.secret)[1:-1], "[REDACTED]",
        )

    def _persist(self, work: Callable[[], None]) -> None:
        try:
            work()
        except PyMongoError as error:
            self.failure = AuditStorageError()
            raise self.failure from error

    def _update(self, values: dict, *, attempt: bool = False) -> None:
        query = {"_id": self.id, "user_id": self.user_id}
        if attempt:
            query["attempts.id"] = self.attempt_id
        result = self.db.llm_calls.update_one(query, values)
        if not result.acknowledged or result.matched_count != 1:
            raise InvalidOperation("LLM audit record is missing or unacknowledged")

    def __enter__(self) -> "LLMCallAudit":
        def insert() -> None:
            result = self.db.llm_calls.insert_one({
                **self.metadata, "created_at": now(), "status": "started", "attempts": [],
            })
            if not result.acknowledged:
                raise InvalidOperation("LLM audit insert is unacknowledged")
        self._persist(insert)
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.failure is not None:
            if exc_value is not self.failure:
                raise self.failure from exc_value
            return
        values: dict = {
            "status": "failed" if exc_value is not None else "response_validated",
            "finished_at": now(), "duration_ms": round((perf_counter() - self.started) * 1000),
        }
        if exc_value is not None:
            values["error"] = {"type": type(exc_value).__name__, "stage": self.stage}
        self._persist(lambda: self._update({"$set": values}))

    def _body(self, content: bytes, phase: str) -> dict:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        redacted = False
        if text is not None:
            safe = self.redact(text)
            redacted = safe != text
            text, content = safe, safe.encode("utf-8")
        else:
            secret = self.secret.encode("utf-8")
            if secret and secret in content:
                content = content.replace(secret, b"[REDACTED]")
                redacted = True
        info = {
            "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
            "redacted": redacted,
        }
        if text is not None and len(content) <= INLINE_BODY_LIMIT:
            return {**info, "storage": "inline", "text": text}
        file_id = uuid4().hex
        audit_files(self.db).put(
            content, _id=file_id, filename=f"{self.id}-{self.attempt_id}-{phase}",
            metadata={"user_id": self.user_id, "call_id": self.id,
                      "attempt_id": self.attempt_id, "phase": phase, **info},
        )
        return {**info, "storage": "gridfs", "file_id": file_id}

    def on_request(self, request: httpx.Request) -> None:
        self.stage = "request"
        self.attempt_count += 1
        if self.attempt_count > MAX_HTTP_ATTEMPTS:
            self.failure = AuditStorageError()
            raise self.failure
        self.attempt_id = uuid4().hex
        self.attempt_started = perf_counter()
        url = request.url.copy_with(userinfo=b"", fragment=None)
        params = []
        for key, value in url.params.multi_items():
            sensitive = any(word in key.lower() for word in ("key", "token", "secret", "password", "signature", "credential", "auth"))
            params.append((key, "[REDACTED]" if sensitive else self.redact(value)))
        safe_url = self.redact(str(url.copy_with(query=urlencode(params).encode("ascii") if params else None)))

        def save() -> None:
            attempt = {
                "id": self.attempt_id, "number": self.attempt_count, "started_at": now(),
                "request": {"method": request.method, "url": safe_url,
                            "content_type": self.redact(request.headers.get("content-type", "")),
                            "body": self._body(request.read(), "request")},
            }
            self._update({"$push": {"attempts": attempt}, "$set": {"status": "request_saved"}})
        self._persist(save)

    def on_response(self, response: httpx.Response) -> None:
        self.stage = "response"
        response.read()

        def save() -> None:
            self._update({"$set": {
                "status": "response_received",
                "attempts.$.response": {
                    "status_code": response.status_code,
                    "content_type": self.redact(response.headers.get("content-type", "")),
                    "request_id": self.redact(response.headers.get("x-request-id") or response.headers.get("apim-request-id") or response.headers.get("request-id") or ""),
                    "body": self._body(response.content, "response"),
                },
                "attempts.$.finished_at": now(),
                "attempts.$.duration_ms": round((perf_counter() - self.attempt_started) * 1000),
            }}, attempt=True)
        self._persist(save)


def read_audit_body(
    db: Database, user_id: str, call_id: str, phase: Literal["request", "response"],
    *, attempt_index: int = 0,
) -> bytes:
    stored = db.llm_calls.find_one({"_id": call_id, "user_id": user_id})
    if not stored:
        raise AppError("模型调用记录不存在", 404)
    attempts = stored["attempts"]
    if attempt_index < 0 or attempt_index >= len(attempts) or phase not in attempts[attempt_index]:
        raise AppError("该次模型请求或响应尚未保存", 409)
    attempt = attempts[attempt_index]
    body = attempt[phase]["body"]
    if body["storage"] == "inline":
        content = body["text"].encode("utf-8")
    elif body["storage"] == "gridfs":
        try:
            with audit_files(db).get(body["file_id"]) as file:
                metadata = file.metadata or {}
                if any(metadata.get(key) != value for key, value in {
                    "user_id": user_id, "call_id": call_id, "attempt_id": attempt["id"], "phase": phase,
                }.items()):
                    raise AppError("模型审计内容归属不匹配", 409)
                content = file.read()
        except NoFile as error:
            raise AppError("模型审计内容文件缺失", 409) from error
    else:
        raise AppError("模型审计内容存储格式无效", 409)
    if len(content) != body["size"] or hashlib.sha256(content).hexdigest() != body["sha256"]:
        raise AppError("模型审计内容完整性校验失败", 409)
    return content
