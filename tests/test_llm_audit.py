import json
from io import BytesIO
from unittest.mock import Mock, patch

import httpx
from openai import APIConnectionError, AuthenticationError, DefaultHttpxClient
from pymongo.errors import AutoReconnect

from resume_app.errors import AppError
from resume_app.linkedin import Candidate
from resume_app.llm_audit import (
    INLINE_BODY_LIMIT, AuditStorageError, LLMCallAudit, audit_files, read_audit_body,
)
from resume_app.storage import initialize_database
from test_product import JOB, PLAN, SOURCE, ProductTestCase, candidate_stream, word_bytes


class LLMAuditTests(ProductTestCase):
    def setUp(self):
        super().setUp()
        self.setup_user()
        self.settings()
        self.requests = []
        self.status = 200
        self.network_failure = False
        self.raw = self.completion(SOURCE.model_dump_json())

        def handle(request):
            self.requests.append(request)
            if self.network_failure:
                raise httpx.ConnectError("Synthetic transport failure", request=request)
            return httpx.Response(
                self.status, content=self.raw,
                headers={"content-type": "application/json", "x-request-id": "provider-request",
                         "set-cookie": "do-not-store-this-cookie"},
            )

        def http_client(**kwargs):
            return DefaultHttpxClient(transport=httpx.MockTransport(handle), **kwargs)

        client = patch("resume_app.llm_workflow.DefaultHttpxClient", side_effect=http_client)
        client.start()
        self.addCleanup(client.stop)

    def completion(self, content):
        return (" \n" + json.dumps({
            "id": "chat-audit", "object": "chat.completion", "created": 0,
            "model": "provider-actual-model", "provider_extra": {"retained": True},
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": content, "reasoning_content": "Original reasoning",
            }}],
            "usage": {"prompt_tokens": 111, "completion_tokens": 22, "total_tokens": 133},
        }, ensure_ascii=False) + "\n").encode("utf-8")

    def parse(self, text="Synthetic source resume"):
        self.workflow.parse_resume(
            "local", "resume.docx", text, self.workflow.llm_settings("local"),
            task_id="synthetic-task",
        )

    def record(self):
        return self.database.llm_calls.find_one({"user_id": "local"})

    def body(self, phase, **kwargs):
        return read_audit_body(self.database, "local", self.record()["_id"], phase, **kwargs)

    def test_exact_wire_request_and_complete_raw_response_are_persisted(self):
        self.parse("简历原文\nKeep the entire source text.")
        record = self.record()
        self.assertEqual(record["status"], "response_validated")
        self.assertEqual(record["operation"], "resume_parse")
        self.assertEqual(record["task_id"], "synthetic-task")
        self.assertEqual(self.body("request"), self.requests[0].content)
        self.assertEqual(self.body("response"), self.raw)
        request = json.loads(self.body("request"))
        self.assertEqual(request["max_tokens"], 12000)
        self.assertEqual(request["thinking"], {"type": "disabled"})
        self.assertFalse(request["stream"])
        self.assertIn("authorship order", request["messages"][0]["content"])
        self.assertEqual(json.loads(request["messages"][1]["content"])["resume_text"],
                         "简历原文\nKeep the entire source text.")
        response = record["attempts"][0]["response"]
        self.assertEqual(response["request_id"], "provider-request")
        self.assertEqual(response["status_code"], 200)
        self.assertGreaterEqual(record["duration_ms"], 0)
        pending = self.database.resumes.find_one({"_id": "local"})["pending_import"]
        self.assertEqual(pending["llm_call_id"], record["_id"])
        self.assertEqual(pending["id"], record["context"]["import_id"])
        serialized = json.dumps(record, default=str)
        self.assertNotIn("synthetic-api-key", serialized)
        self.assertNotIn("headers", record["attempts"][0]["request"])
        self.assertNotIn("headers", record["attempts"][0]["response"])
        self.assertNotIn("do-not-store-this-cookie", serialized)

    def test_audit_outlives_discarded_or_merged_imports(self):
        for apply in (False, True):
            with self.subTest(apply=apply):
                self.parse()
                record = self.database.llm_calls.find_one(
                    {"context.import_id": self.database.resumes.find_one({"_id": "local"})["pending_import"]["id"]},
                )
                resume = self.database.resumes.find_one({"_id": "local"})
                body = {"edit_token": resume["edit_token"], "import_id": resume["pending_import"]["id"]}
                if apply:
                    body["profile"] = SOURCE.model_dump()
                endpoint = "apply" if apply else "discard"
                self.assertEqual(self.post(f"/api/resume/import/{endpoint}", body).status_code, 200)
                self.assertEqual(self.database.llm_calls.find_one({"_id": record["_id"]}), record)
                self.assertEqual(read_audit_body(self.database, "local", record["_id"], "response"), self.raw)
                if apply:
                    self.assertEqual(self.database.resumes.find_one({"_id": "local"})["last_import_call_id"], record["_id"])

    def test_job_tailoring_records_snapshots_and_cache_hit_does_not_add_a_call(self):
        self.raw = self.completion(json.dumps(PLAN))
        settings = self.workflow.llm_settings("local")
        resume_id, cached = self.workflow.tailor("local", JOB, SOURCE, settings, task_id="job-task")
        self.assertFalse(cached)
        record = self.record()
        payload = json.loads(json.loads(self.body("request"))["messages"][1]["content"])
        self.assertEqual(payload["confirmed_resume"], SOURCE.model_dump())
        self.assertEqual(payload["job"]["description"], JOB.description)
        self.assertNotIn("application_url", payload["job"])
        self.assertEqual(record["operation"], "job_tailor")
        self.assertEqual(record["context"]["cache_id"], resume_id)
        self.assertEqual(record["task_id"], "job-task")
        self.assertEqual(self.database.tailored_resumes.find_one({"_id": resume_id})["llm_call_id"], record["_id"])
        again, cached = self.workflow.tailor_stored("local", JOB.linkedin_id, SOURCE, settings)
        self.assertEqual(again, resume_id)
        self.assertTrue(cached)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.database.llm_calls.count_documents({}), 1)

    def test_invalid_json_and_semantically_invalid_plans_are_retained(self):
        for content in ("not JSON", json.dumps({**PLAN, "skills": ["Invented skill"]})):
            with self.subTest(content=content):
                self.raw = self.completion(content)
                with self.assertRaises(AppError):
                    self.workflow.tailor("local", JOB, SOURCE, self.workflow.llm_settings("local"))
                record = list(self.database.llm_calls.find({}).sort("created_at", -1))[0]
                self.assertEqual(record["status"], "failed")
                self.assertEqual(record["error"]["stage"], "validation")
                self.assertEqual(read_audit_body(self.database, "local", record["_id"], "response"), self.raw)
                self.assertEqual(self.database.tailored_resumes.count_documents({}), 0)

    def test_truncated_model_output_is_saved_before_client_rejects_it(self):
        payload = json.loads(self.raw)
        payload["choices"][0]["finish_reason"] = "length"
        self.raw = json.dumps(payload).encode()
        with self.assertRaisesRegex(RuntimeError, "complete text"):
            self.parse()
        self.assertEqual(self.body("response"), self.raw)
        self.assertEqual(self.record()["status"], "failed")
        self.assertEqual(self.record()["error"]["type"], "LLMResponseError")
        self.assertIsNone(self.database.resumes.find_one({"_id": "local"}))

    def test_http_error_body_is_saved_and_authorization_is_not(self):
        self.status = 401
        self.raw = b'{"error":{"message":"Bad synthetic-api-key","type":"invalid_api_key"}}'
        with self.assertRaises(AuthenticationError):
            self.parse()
        record = self.record()
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["attempts"][0]["response"]["status_code"], 401)
        self.assertTrue(record["attempts"][0]["response"]["body"]["redacted"])
        self.assertIn(b"[REDACTED]", self.body("response"))
        self.assertNotIn(b"synthetic-api-key", self.body("response"))
        self.assertEqual(len(self.requests), 1)

    def test_network_failure_retains_request_without_fabricating_a_response(self):
        self.network_failure = True
        with self.assertRaises(APIConnectionError):
            self.parse()
        self.assertEqual(self.body("request"), self.requests[0].content)
        self.assertNotIn("response", self.record()["attempts"][0])
        self.assertEqual(self.record()["error"]["type"], "APIConnectionError")
        with self.assertRaises(AppError):
            self.body("response")

    def test_initial_audit_failure_stops_before_network_request(self):
        with patch.object(self.database.llm_calls, "insert_one", side_effect=AutoReconnect("offline")):
            with self.assertRaises(AuditStorageError):
                self.parse()
        self.assertEqual(self.requests, [])
        self.assertIsNone(self.database.resumes.find_one({"_id": "local"}))

    def test_request_audit_failure_is_not_hidden_by_sdk_connection_error(self):
        with patch.object(self.database.llm_calls, "update_one", side_effect=AutoReconnect("offline")):
            with self.assertRaises(AuditStorageError):
                self.parse()
        self.assertEqual(self.requests, [])
        self.assertEqual(self.record()["status"], "started")
        self.assertIsNone(self.database.resumes.find_one({"_id": "local"}))

    def test_response_or_final_audit_failure_does_not_save_business_results(self):
        update = self.database.llm_calls.update_one
        for failing_status in ("response_received", "response_validated"):
            with self.subTest(status=failing_status):
                self.database.llm_calls.delete_many({})
                self.requests.clear()

                def fail_response(query, values, **kwargs):
                    if values.get("$set", {}).get("status") == failing_status:
                        raise AutoReconnect("offline")
                    return update(query, values, **kwargs)

                with patch.object(self.database.llm_calls, "update_one", side_effect=fail_response):
                    with self.assertRaises(AuditStorageError):
                        self.parse()
                self.assertEqual(len(self.requests), 1)
                self.assertIsNone(self.database.resumes.find_one({"_id": "local"}))
                if failing_status == "response_validated":
                    self.assertEqual(self.body("response"), self.raw)

    def test_large_request_and_response_round_trip_through_gridfs(self):
        self.raw = self.completion(SOURCE.model_dump_json() + " " * (INLINE_BODY_LIMIT + 1))
        self.parse("原" * INLINE_BODY_LIMIT)
        record = self.record()
        for phase in ("request", "response"):
            self.assertEqual(record["attempts"][0][phase]["body"]["storage"], "gridfs")
        self.assertEqual(self.body("request"), self.requests[0].content)
        self.assertEqual(self.body("response"), self.raw)
        self.assertEqual(self.database.llm_audit_payloads.files.count_documents({}), 2)

    def test_inline_size_boundary_and_binary_bodies_are_not_truncated(self):
        settings = self.workflow.llm_settings("local")
        for content, storage in (
            (b"x" * INLINE_BODY_LIMIT, "inline"),
            (b"x" * (INLINE_BODY_LIMIT + 1), "gridfs"),
            (b"\xff\x00\xfe", "gridfs"),
        ):
            with self.subTest(size=len(content)):
                with LLMCallAudit(self.database, "local", "resume_parse", settings, context={}) as audit:
                    audit.on_request(httpx.Request("POST", "https://example.test/chat", content=content))
                record = self.database.llm_calls.find_one({"_id": audit.id})
                self.assertEqual(record["attempts"][0]["request"]["body"]["storage"], storage)
                self.assertEqual(read_audit_body(self.database, "local", audit.id, "request"), content)

    def test_urls_redact_credentials_but_keep_non_secret_query_parameters(self):
        settings = self.workflow.llm_settings("local")
        with LLMCallAudit(self.database, "local", "resume_parse", settings, context={}) as audit:
            audit.on_request(httpx.Request(
                "POST", "https://username:password@example.test/chat?api-version=2024&api_key=hidden&token=hidden",
                content=b'{"safe":true}',
            ))
        url = self.database.llm_calls.find_one({"_id": audit.id})["attempts"][0]["request"]["url"]
        self.assertNotIn("username", url)
        self.assertNotIn("password", url)
        self.assertNotIn("hidden", url)
        self.assertIn("api-version=2024", url)

    def test_reading_audit_requires_owner_and_checks_integrity(self):
        self.parse()
        record = self.record()
        with self.assertRaises(AppError):
            read_audit_body(self.database, "other-user", record["_id"], "request")
        self.database.llm_calls.update_one(
            {"_id": record["_id"]}, {"$set": {"attempts.0.response.body.text": "tampered"}},
        )
        with self.assertRaisesRegex(AppError, "完整性"):
            self.body("response")

    def test_startup_marks_unfinished_calls_interrupted_without_deleting_payloads(self):
        self.parse()
        original = self.body("response")
        self.database.llm_calls.update_one({"_id": self.record()["_id"]}, {"$set": {"status": "response_received"}})
        initialize_database(self.database)
        self.assertEqual(self.record()["status"], "interrupted")
        self.assertEqual(self.body("response"), original)

    def test_background_upload_associates_audit_with_task_id(self):
        response = self.post("/api/resume/upload", data={
            "file": (BytesIO(word_bytes()), "resume.docx"), "consent": "yes",
        })
        self.assertEqual(response.status_code, 202)
        task_id = response.get_json()["task_id"]
        self.assertEqual(self.wait_task(task_id)["status"], "succeeded")
        self.assertEqual(self.record()["task_id"], task_id)
        self.assertEqual(self.body("response"), self.raw)

    def test_batch_stops_on_audit_failure_instead_of_attempting_more_jobs(self):
        self.confirmed()
        browser = Mock()
        browser.jobs.return_value = candidate_stream([
            Candidate(JOB.linkedin_id, post=JOB),
            Candidate("999", post=JOB.model_copy(update={"linkedin_id": "999"})),
        ])
        self.runner.browser = browser
        with patch.object(self.database.llm_calls, "insert_one", side_effect=AutoReconnect("offline")) as insert:
            task_id = self.runner.scan("local", 2)
            task = self.wait_task(task_id)
        self.assertEqual(task["status"], "failed")
        self.assertIn("审计入库失败", task["error"])
        self.assertEqual(insert.call_count, 1)
        self.assertEqual(self.requests, [])

    def test_redirects_preserve_each_http_exchange_in_order(self):
        requests = []

        def handle(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(307, content=b"Redirect body", headers={"location": "/forwarded"})
            return httpx.Response(200, content=self.raw, headers={"content-type": "application/json"})

        def client(**kwargs):
            return DefaultHttpxClient(transport=httpx.MockTransport(handle), **kwargs)

        with patch("resume_app.llm_workflow.DefaultHttpxClient", side_effect=client):
            self.parse()
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(self.record()["attempts"]), 2)
        self.assertEqual(self.body("request", attempt_index=0), requests[0].content)
        self.assertEqual(self.body("request", attempt_index=1), requests[1].content)
        self.assertEqual(self.body("response", attempt_index=0), b"Redirect body")
        self.assertEqual(self.body("response", attempt_index=1), self.raw)

    def test_invalid_provider_json_is_recorded_before_sdk_parsing(self):
        self.raw = b"not provider JSON"
        with self.assertRaises(json.JSONDecodeError):
            self.parse()
        self.assertEqual(self.body("response"), self.raw)
        self.assertEqual(self.record()["status"], "failed")

    def test_large_request_payload_storage_failure_stops_before_network(self):
        with patch("resume_app.llm_audit.audit_files") as files:
            files.return_value.put.side_effect = AutoReconnect("offline")
            with self.assertRaises(AuditStorageError):
                self.parse("x" * (INLINE_BODY_LIMIT + 1))
        self.assertEqual(self.requests, [])
        self.assertIsNone(self.database.resumes.find_one({"_id": "local"}))

    def test_gridfs_response_file_loss_and_wrong_owner_are_explicit_errors(self):
        self.raw = self.completion(SOURCE.model_dump_json() + " " * (INLINE_BODY_LIMIT + 1))
        self.parse()
        file_id = self.record()["attempts"][0]["response"]["body"]["file_id"]
        self.database.llm_audit_payloads.files.update_one(
            {"_id": file_id}, {"$set": {"metadata.user_id": "other-user"}},
        )
        with self.assertRaisesRegex(AppError, "归属"):
            self.body("response")
        audit_files(self.database).delete(file_id)
        with self.assertRaisesRegex(AppError, "缺失"):
            self.body("response")
