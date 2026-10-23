"""One local worker serializes browser and model work with persistent progress."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Event, Lock
from uuid import uuid4

from openai import APIError
from pymongo.database import Database
from selenium.common.exceptions import WebDriverException

from resume_app.errors import AppError, TaskCancelled
from resume_app.linkedin import LinkedInBrowser, check_cancelled
from resume_app.llm_audit import AuditStorageError
from resume_app.llm_workflow import ResumeWorkflow
from resume_app.models import resume_cache_data
from resume_app.storage import fingerprint, now
from utils.llm_client import LLMResponseError


_LOGGER = logging.getLogger(__name__)
Work = Callable[[str, Event], None]


class TaskRunner:
    def __init__(
        self, db: Database, workflow: ResumeWorkflow, browser: LinkedInBrowser,
    ) -> None:
        self.db = db
        self.workflow = workflow
        self.browser = browser
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="resume-worker")
        self.events: dict[str, Event] = {}
        self.lock = Lock()
        self.closed = False

    def start(self, user_id: str, kind: str, work: Work) -> str:
        with self.lock:
            if self.closed:
                raise AppError("后台已关闭，请重启应用", 503)
            if self.events:
                raise AppError("已有任务正在执行，请等待完成或先取消", 409)
            task_id = uuid4().hex
            cancel = Event()
            self.db.tasks.insert_one({
                "_id": task_id, "user_id": user_id, "kind": kind,
                "status": "queued", "created_at": now(), "processed": 0,
                "generated": 0, "cached": 0, "failed": 0, "errors": [],
            })
            self.events[task_id] = cancel
            try:
                self.executor.submit(self._execute, task_id, cancel, work)
            except RuntimeError:
                self.events.pop(task_id)
                self.db.tasks.update_one(
                    {"_id": task_id},
                    {"$set": {"status": "failed", "error": "后台已关闭，请重启应用"}},
                )
                raise AppError("后台已关闭，请重启应用", 503)
        return task_id

    def _execute(self, task_id: str, cancel: Event, work: Work) -> None:
        status = "succeeded"
        message: str | None = None
        try:
            check_cancelled(cancel)
            self.db.tasks.update_one(
                {"_id": task_id}, {"$set": {"status": "running", "started_at": now()}}
            )
            work(task_id, cancel)
            check_cancelled(cancel)
        except TaskCancelled:
            status = "cancelled"
        except AppError as error:
            status, message = "failed", str(error)
            _LOGGER.warning("Task %s failed: %s", task_id, message)
        except (APIError, LLMResponseError) as error:
            status, message = "failed", "模型调用失败，请核对 API key、模型权限、额度和服务状态"
            _LOGGER.warning("Task %s provider failure: %s", task_id, type(error).__name__)
        except WebDriverException as error:
            status, message = "failed", "Chrome 操作失败，请检查浏览器或驱动后重试"
            _LOGGER.warning("Task %s browser failure: %s", task_id, type(error).__name__)
        except Exception:
            status, message = "failed", "后台发生异常，请查看服务日志；已保存的数据不会丢失"
            _LOGGER.exception("Unhandled task failure: %s", task_id)
        finally:
            with self.lock:
                try:
                    if cancel.is_set() and status == "succeeded":
                        status = "cancelled"
                    self.db.tasks.update_one(
                        {"_id": task_id},
                        {"$set": {"status": status, "error": message, "finished_at": now()}},
                    )
                finally:
                    self.events.pop(task_id, None)

    def cancel(self, user_id: str, task_id: str) -> None:
        if not self.db.tasks.find_one({"_id": task_id, "user_id": user_id}):
            raise AppError("任务不存在", 404)
        with self.lock:
            event = self.events.get(task_id)
            if event is None:
                raise AppError("任务已结束，不能取消", 409)
            event.set()
            self.db.tasks.update_one(
                {"_id": task_id}, {"$set": {"status": "cancelling"}}
            )

    def open_browser(self, user_id: str) -> str:
        return self.start(
            user_id, "browser", lambda _task, _cancel: self.browser.open(user_id)
        )

    def parse_resume(self, user_id: str, filename: str, text: str) -> str:
        settings = self.workflow.llm_settings(user_id)

        def work(task_id: str, cancel: Event) -> None:
            check_cancelled(cancel)
            self.workflow.parse_resume(user_id, filename, text, settings, task_id=task_id)

        return self.start(user_id, "parse", work)

    def scan(self, user_id: str, limit: int) -> str:
        source = self.workflow.confirmed_resume(user_id)
        settings = self.workflow.llm_settings(user_id)

        def work(task_id: str, cancel: Event) -> None:
            self.db.tasks.update_one(
                {"_id": task_id},
                {"$set": {"source_hash": fingerprint(resume_cache_data(source)), "limit": limit}},
            )
            with closing(self.browser.jobs(limit, cancel)) as candidates:
                for candidate in candidates:
                    check_cancelled(cancel)
                    increments = {"processed": 1}
                    message = candidate.error
                    if candidate.post is not None:
                        try:
                            _resume_id, cached = self.workflow.tailor(
                                user_id, candidate.post, source, settings, task_id=task_id,
                            )
                            increments["cached" if cached else "generated"] = 1
                        except LLMResponseError as error:
                            message = "模型未返回完整文本，请检查模型设置后重试"
                            _LOGGER.warning("Job %s provider error: %s", candidate.linkedin_id, type(error).__name__)
                        except AuditStorageError:
                            raise
                        except AppError as error:
                            message = str(error)
                    update: dict = {
                        "$inc": increments,
                        "$set": {"current_job": candidate.linkedin_id},
                    }
                    if message:
                        increments["failed"] = 1
                        update["$push"] = {"errors": {
                            "$each": [{"job_id": candidate.linkedin_id, "message": message}],
                            "$slice": -50,
                        }}
                    self.db.tasks.update_one({"_id": task_id}, update)
            task = self.db.tasks.find_one({"_id": task_id})
            if task and task["failed"]:
                raise AppError("部分职位处理失败。已成功的结果已保存；可查看错误并重新遍历")
            if not task or not task["processed"]:
                raise AppError("没有处理到可用的推荐职位，请检查登录状态和推荐页面")

        return self.start(user_id, "scan", work)

    def tailor_stored(self, user_id: str, linkedin_id: str) -> str:
        source = self.workflow.confirmed_resume(user_id)
        settings = self.workflow.llm_settings(user_id)
        if not self.db.jobs.find_one({"user_id": user_id, "linkedin_id": linkedin_id}):
            raise AppError("职位不存在", 404)

        def work(task_id: str, cancel: Event) -> None:
            check_cancelled(cancel)
            self.db.tasks.update_one(
                {"_id": task_id},
                {"$set": {
                    "source_hash": fingerprint(resume_cache_data(source)), "current_job": linkedin_id,
                }},
            )
            resume_id, cached = self.workflow.tailor_stored(
                user_id, linkedin_id, source, settings, task_id=task_id,
            )
            self.db.tasks.update_one(
                {"_id": task_id},
                {"$set": {
                    "processed": 1, "generated": 0 if cached else 1,
                    "cached": 1 if cached else 0, "current_job": linkedin_id,
                    "result_resume_id": resume_id,
                }},
            )

        return self.start(user_id, "tailor", work)

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for event in self.events.values():
                event.set()
        self.executor.submit(self.browser.close)
        self.executor.shutdown(wait=True)
