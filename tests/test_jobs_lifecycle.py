import json
from unittest.mock import patch

from resume_app.models import resume_cache_data
from resume_app.storage import fingerprint
from test_product import JOB, PLAN, SOURCE, ProductTestCase


class JobsLifecycleTests(ProductTestCase):
    def setUp(self):
        super().setUp()
        self.setup_user()
        self.settings()
        self.confirmed()
        with patch.object(self.workflow, "_complete", return_value=json.dumps(PLAN)):
            self.resume_id, _ = self.workflow.tailor("local", JOB, SOURCE, self.workflow.llm_settings("local"))

    def detail(self):
        return self.client.get(f"/api/tailored/{self.resume_id}").get_json()

    def approve(self):
        record = self.detail()
        return self.post(f"/api/tailored/{self.resume_id}/review", {
            "confirmed": True, "edit_token": record["edit_token"],
            "profile": record["resume"], "template_id": "simple",
        })

    def test_source_status_detects_confirmed_changes_but_not_unconfirmed_drafts(self):
        before = self.detail()
        self.assertEqual(before["latest_source"]["status"], "current")
        self.database.resumes.update_one({"_id": "local"}, {"$set": {"draft": {"summary": "Unconfirmed"}}})
        result = self.client.get(f"/api/tailored/{self.resume_id}/source").get_json()
        self.assertEqual(result["status"], "current")
        self.assertTrue(result["has_pending_changes"])
        self.assertEqual(result["confirmed"], SOURCE.model_dump())
        changed = SOURCE.model_copy(deep=True)
        changed.contact.phone = "+1 555 0100"
        self.database.resumes.update_one({"_id": "local"}, {"$set": {
            "confirmed": changed.model_dump(), "confirmed_hash": fingerprint(resume_cache_data(changed)),
        }})
        result = self.client.get(f"/api/tailored/{self.resume_id}/source").get_json()
        self.assertEqual(result["status"], "changed")
        self.assertEqual(result["confirmed"]["contact"]["phone"], "+1 555 0100")
        self.assertEqual(self.detail()["resume"], before["resume"])
        self.assertEqual(self.detail()["source_resume"], before["source_resume"])

    def test_missing_source_and_legacy_hashes_are_explicit_and_owner_checked(self):
        self.database.tailored_resumes.update_one({"_id": self.resume_id}, {"$unset": {"source_hash": ""}})
        self.assertEqual(self.detail()["latest_source"]["status"], "current")
        self.database.tailored_resumes.update_one({"_id": self.resume_id}, {"$unset": {"source_resume": ""}})
        self.assertEqual(self.detail()["latest_source"]["status"], "unknown")
        self.database.resumes.delete_one({"_id": "local"})
        source = self.client.get(f"/api/tailored/{self.resume_id}/source").get_json()
        self.assertEqual(source["status"], "unavailable")
        self.assertIsNone(source["confirmed"])
        self.database.tailored_resumes.insert_one({"_id": "other", "user_id": "other"})
        self.assertEqual(self.client.get("/api/tailored/other/source").status_code, 404)

    def test_same_template_and_content_can_generate_a_new_downloadable_pdf_repeatedly(self):
        with patch.object(self.workflow, "_complete") as model:
            self.assertEqual(self.approve().status_code, 200)
            first = self.detail()
            response = self.approve()
            self.assertEqual(response.status_code, 200)
            second = self.detail()
        model.assert_not_called()
        self.assertNotEqual(first["pdf"]["file_id"], second["pdf"]["file_id"])
        self.assertEqual(response.get_json()["pdf"]["file_id"], second["pdf"]["file_id"])
        self.assertTrue(response.get_json()["pdf_ready"])
        self.assertEqual(self.client.get(f"/api/tailored/{self.resume_id}/pdf?download=1").status_code, 200)
        self.assertTrue(self.client.get("/api/jobs").get_json()["items"][0]["tailored"]["pdf_ready"])
        self.database.resume_pdfs.files.delete_one({"_id": second["pdf"]["file_id"]})
        self.assertFalse(self.client.get("/api/jobs").get_json()["items"][0]["tailored"]["pdf_ready"])

    def test_generation_task_returns_exact_cached_or_new_version(self):
        task_id = self.runner.tailor_stored("local", JOB.linkedin_id)
        task = self.wait_task(task_id)
        self.assertEqual(task["status"], "succeeded")
        self.assertEqual(task["result_resume_id"], self.resume_id)
        self.assertEqual(task["cached"], 1)
        changed = SOURCE.model_copy(deep=True)
        changed.summary = "New confirmed base."
        self.database.resumes.update_one({"_id": "local"}, {"$set": {
            "confirmed": changed.model_dump(), "confirmed_hash": fingerprint(resume_cache_data(changed)),
        }})
        with patch.object(self.workflow, "_complete", return_value=json.dumps(PLAN)):
            task_id = self.runner.tailor_stored("local", JOB.linkedin_id)
            task = self.wait_task(task_id)
        self.assertEqual(task["status"], "succeeded")
        self.assertNotEqual(task["result_resume_id"], self.resume_id)
        self.assertEqual(task["generated"], 1)
        result = self.database.tailored_resumes.find_one({"_id": task["result_resume_id"]})
        self.assertEqual(result["source_resume"], changed.model_dump())
