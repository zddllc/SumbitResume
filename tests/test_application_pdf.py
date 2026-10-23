import hashlib
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from pydantic import ValidationError
from pypdf import PdfReader

from resume_app.documents import DocumentError
from resume_app.errors import AppError
from resume_app.linkedin import LinkedInBrowser, RECOMMENDED_URL, clean_application_url
from resume_app.models import JobPost, ResumeProfile
from resume_app.pdf.storage import pdf_files, store_pdf
from resume_app.pdf.templates.simple import SimpleTemplate
from test_product import JOB, PLAN, SOURCE, ProductTestCase


class ApplicationExtractionTests(unittest.TestCase):
    def test_company_apply_url_is_stable_but_unknown_ats_parameters_are_retained(self):
        self.assertEqual(
            clean_application_url(
                "https://www.amazon.jobs/applicant/jobs/3193573/apply"
                "?cmpid=linkedin&utm_source=linkedin&ss=paid"
            ),
            "https://www.amazon.jobs/applicant/jobs/3193573/apply",
        )
        self.assertEqual(
            clean_application_url("https://ats.example.test/apply?jobId=42&token=needed&utm_source=test"),
            "https://ats.example.test/apply?jobId=42&token=needed",
        )

    def test_invalid_and_linkedin_external_urls_are_rejected(self):
        for url in (
            "javascript:alert(1)", "http://example.test/apply",
            "https://user:password@example.test/apply", "https://127.0.0.1/apply",
            "https://www.linkedin.com/jobs/view/123456/",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                clean_application_url(url)
        with self.assertRaises(ValidationError):
            JobPost.model_validate({**JOB.model_dump(), "application_kind": "external"})

    def test_easy_apply_is_not_clicked_and_has_no_fake_external_url(self):
        browser = LinkedInBrowser(Path("unused-test-profile"))
        driver, panel, button = Mock(), Mock(), Mock()
        panel.find_elements.return_value = [button]
        button.get_attribute.return_value = "Easy Apply to Sample Role"
        result = browser._read_application(driver, panel)
        self.assertEqual(result, {"application_kind": "easy_apply"})
        button.click.assert_not_called()

    def test_existing_external_anchor_does_not_need_a_click(self):
        browser = LinkedInBrowser(Path("unused-test-profile"))
        driver, panel, button = Mock(), Mock(), Mock()
        driver.current_url = RECOMMENDED_URL
        panel.find_elements.return_value = [button]
        button.get_attribute.side_effect = lambda attr: (
            "Apply on company website" if attr == "aria-label" else "https://ats.example.test/jobs/42"
        )
        result = browser._read_application(driver, panel)
        self.assertEqual(result["application_url"], "https://ats.example.test/jobs/42")
        button.click.assert_not_called()

    def test_external_popup_extracts_apply_link_and_only_closes_its_own_tab(self):
        browser = LinkedInBrowser(Path("unused-test-profile"))
        driver, button, anchor = Mock(), Mock(), Mock()
        driver.current_window_handle = "listing"
        driver.current_url = RECOMMENDED_URL
        driver.window_handles = ["listing", "existing-user-tab"]
        button.click.side_effect = lambda: driver.window_handles.append("application")

        def switch(handle):
            driver.current_window_handle = handle
            driver.current_url = (
                "https://www.amazon.jobs/en/jobs/3193573/sample" if handle == "application"
                else RECOMMENDED_URL
            )
        driver.switch_to.window.side_effect = switch
        driver.close.side_effect = lambda: driver.window_handles.remove(driver.current_window_handle)
        anchor.text = "Apply now"
        anchor.get_attribute.return_value = (
            "https://www.amazon.jobs/applicant/jobs/3193573/apply?utm_source=linkedin"
        )
        driver.find_elements.return_value = [anchor]
        result = browser._external_application(driver, button)
        self.assertEqual(result["application_url"], "https://www.amazon.jobs/applicant/jobs/3193573/apply")
        self.assertEqual(result["application_url_source"], "company_apply_link")
        self.assertEqual(driver.window_handles, ["listing", "existing-user-tab"])
        self.assertEqual(driver.current_window_handle, "listing")
        driver.close.assert_called_once()

    def test_unknown_company_page_keeps_verified_landing_url_as_start(self):
        browser = LinkedInBrowser(Path("unused-test-profile"))
        driver, button = Mock(), Mock()
        driver.current_window_handle = "listing"
        driver.current_url = RECOMMENDED_URL
        driver.window_handles = ["listing"]
        button.click.side_effect = lambda: setattr(driver, "current_url", "https://ats.example.test/jobs/42")
        driver.find_elements.side_effect = lambda _by, selector: (
            [] if selector == "a[href]" else [Mock()]
        )
        driver.back.side_effect = lambda: setattr(driver, "current_url", RECOMMENDED_URL)
        result = browser._external_application(driver, button)
        self.assertEqual(result["application_url"], "https://ats.example.test/jobs/42")
        self.assertEqual(result["application_url_source"], "external_redirect")
        driver.back.assert_called_once()
        driver.close.assert_not_called()

    def test_wrong_panel_identity_prevents_reading_or_applying_to_previous_job(self):
        browser = LinkedInBrowser(Path("unused-test-profile"))
        with (
            patch.object(browser, "_panel_job_id", return_value="999"),
            patch.object(browser, "_read_application") as apply,
        ):
            with self.assertRaisesRegex(AppError, "上一职位"):
                browser._read_panel(Mock(), JOB.linkedin_id)
        apply.assert_not_called()

    def test_select_job_clicks_left_card_and_waits_for_matching_right_panel(self):
        browser = LinkedInBrowser(Path("unused-test-profile"))
        driver, card = Mock(), Mock()
        driver.find_elements.return_value = [card]
        with (
            patch.object(browser, "_require_login"),
            patch.object(browser, "_panel_job_id", side_effect=["999", JOB.linkedin_id]),
            patch.object(browser, "_visible_text", return_value=JOB.description),
        ):
            browser._select_job(driver, JOB.linkedin_id)
        card.click.assert_called_once()
        driver.get.assert_not_called()


class ConfirmedPdfTests(ProductTestCase):
    def setUp(self):
        super().setUp()
        self.setup_user()
        self.settings()
        self.confirmed()
        with patch.object(self.workflow, "_complete", return_value=json.dumps(PLAN)):
            self.resume_id, _ = self.workflow.tailor(
                "local", JOB, SOURCE, self.workflow.llm_settings("local")
            )

    def detail(self):
        return self.client.get(f"/api/tailored/{self.resume_id}").get_json()

    def approve(self, record=None, profile=None):
        record = record or self.detail()
        return self.post(f"/api/tailored/{self.resume_id}/review", {
            "confirmed": True, "edit_token": record["edit_token"],
            "profile": profile or record["resume"],
            "template_id": "simple",
        })

    def test_edit_confirm_pdf_is_persisted_and_downloaded_without_model_or_base_changes(self):
        self.assertEqual(self.client.get(f"/api/tailored/{self.resume_id}/pdf").status_code, 409)
        record = self.detail()
        changed = record["resume"]
        changed["contact"]["name"] = "张三 Sample"
        changed["summary"] = "用户已确认的个性化简历。Python & SQL."
        changed["experience"][0]["bullets"] = ["Top edited point", "Second edited point"]
        with patch.object(self.workflow, "_complete") as model:
            response = self.approve(record, changed)
        self.assertEqual(response.status_code, 200, response.get_json())
        model.assert_not_called()
        stored = self.detail()
        self.assertTrue(stored["pdf_ready"])
        self.assertNotEqual(stored["edit_token"], record["edit_token"])
        first = self.client.get(f"/api/tailored/{self.resume_id}/pdf")
        second = self.client.get(f"/api/tailored/{self.resume_id}/pdf?download=1")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.mimetype, "application/pdf")
        self.assertIn("inline", first.headers["Content-Disposition"])
        self.assertIn("attachment", second.headers["Content-Disposition"])
        self.assertEqual(first.data, second.data)
        self.assertEqual(hashlib.sha256(first.data).hexdigest(), stored["pdf"]["sha256"])
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(first.data)).pages)
        self.assertIn("张三", text)
        self.assertIn("个性化简历", text)
        self.assertLess(text.index("Top edited point"), text.index("Second edited point"))
        self.assertEqual(
            self.database.resumes.find_one({"_id": "local"})["confirmed"],
            SOURCE.model_dump(),
        )
        file = pdf_files(self.database).get(stored["pdf"]["file_id"])
        self.assertEqual(file.read(), first.data)
        self.assertEqual(file.metadata["user_id"], "local")
        self.assertNotIn("data", stored["pdf"])

    def test_stale_confirmation_is_rejected_without_replacing_approved_pdf(self):
        record = self.detail()
        self.assertEqual(self.approve(record).status_code, 200)
        first = self.detail()
        self.assertEqual(self.approve(record).status_code, 409)
        self.assertEqual(self.detail()["pdf"]["file_id"], first["pdf"]["file_id"])
        self.assertEqual(self.database["resume_pdfs.files"].count_documents({}), 1)

    def test_pdf_failure_does_not_mark_reviewed_or_overwrite_resume(self):
        before = self.detail()
        with patch.object(SimpleTemplate, "render", side_effect=DocumentError("Synthetic font failure")):
            response = self.approve(before)
        self.assertEqual(response.status_code, 400)
        after = self.detail()
        self.assertEqual(after["resume"], before["resume"])
        self.assertEqual(after["review_status"], "pending")
        self.assertFalse(after["pdf_ready"])
        self.assertEqual(self.database["resume_pdfs.files"].count_documents({}), 0)

    def test_concurrent_change_removes_only_the_unclaimed_new_pdf(self):
        def race(db, user, resume_id, file_id, profile_hash, content, **kwargs):
            artifact = store_pdf(db, user, resume_id, file_id, profile_hash, content, **kwargs)
            db.tailored_resumes.update_one(
                {"_id": resume_id}, {"$set": {"edit_token": "changed-concurrently"}}
            )
            return artifact
        with patch("resume_app.web.store_pdf", side_effect=race):
            response = self.approve()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.database["resume_pdfs.files"].count_documents({}), 0)
        self.assertEqual(self.database["resume_pdfs.chunks"].count_documents({}), 0)
        self.assertEqual(self.detail()["review_status"], "pending")

    def test_legacy_review_does_not_pretend_to_have_a_pdf(self):
        self.database.tailored_resumes.update_one(
            {"_id": self.resume_id},
            {"$unset": {"edit_token": ""}, "$set": {"review_status": "reviewed"}},
        )
        stored = self.detail()
        self.assertTrue(stored["edit_token"])
        self.assertFalse(stored["pdf_ready"])
        self.assertEqual(self.client.get(f"/api/tailored/{self.resume_id}/pdf").status_code, 409)
        self.assertEqual(self.approve(stored).status_code, 200)
        self.assertTrue(self.detail()["pdf_ready"])

    def test_changed_profile_or_missing_file_cannot_download_a_stale_pdf(self):
        self.assertEqual(self.approve().status_code, 200)
        artifact = self.detail()["pdf"]
        self.database.tailored_resumes.update_one(
            {"_id": self.resume_id}, {"$set": {"resume.summary": "Modified without confirmation"}},
        )
        self.assertEqual(self.client.get(f"/api/tailored/{self.resume_id}/pdf").status_code, 409)
        pdf_files(self.database).delete(artifact["file_id"])
        self.assertFalse(self.detail()["pdf_ready"])

    def test_other_users_pdf_is_not_accessible(self):
        self.database.tailored_resumes.insert_one({"_id": "other-pdf", "user_id": "other"})
        self.assertEqual(self.client.get("/api/tailored/other-pdf/pdf").status_code, 404)

    def test_corrupted_pdf_bytes_are_not_returned_as_a_successful_download(self):
        self.assertEqual(self.approve().status_code, 200)
        file_id = self.detail()["pdf"]["file_id"]
        chunk = self.database["resume_pdfs.chunks"].find_one({"files_id": file_id, "n": 0})
        damaged = b"X" + bytes(chunk["data"])[1:]
        self.database["resume_pdfs.chunks"].update_one(
            {"_id": chunk["_id"]}, {"$set": {"data": damaged}},
        )
        response = self.client.get(f"/api/tailored/{self.resume_id}/pdf")
        self.assertEqual(response.status_code, 409)
        self.assertIn("完整性", response.get_json()["error"])

    def test_changed_application_url_is_saved_without_duplicate_llm_calls(self):
        settings = self.workflow.llm_settings("local")
        with patch.object(self.workflow, "_complete") as model:
            updated = JOB.model_copy(update={
                "application_kind": "external",
                "application_url": "https://ats.example.test/apply?job=42",
                "application_landing_url": "https://ats.example.test/jobs/42",
                "application_url_source": "company_apply_link",
            })
            resume_id, cached = self.workflow.tailor("local", updated, SOURCE, settings)
        self.assertTrue(cached)
        self.assertEqual(resume_id, self.resume_id)
        model.assert_not_called()
        self.assertEqual(self.detail()["application"]["url"], updated.application_url)

    def test_application_tokens_do_not_enter_the_model_prompt(self):
        job = JOB.model_copy(update={
            "linkedin_id": "771122", "url": "https://www.linkedin.com/jobs/view/771122/",
            "application_kind": "external",
            "application_url": "https://ats.example.test/apply?jobId=42&token=private-apply-token",
            "application_landing_url": "https://ats.example.test/jobs/42",
            "application_url_source": "company_apply_link",
        })
        with patch.object(self.workflow, "_complete", return_value=json.dumps(PLAN)) as model:
            self.workflow.tailor("local", job, SOURCE, self.workflow.llm_settings("local"))
        prompt = model.call_args.args[1]
        self.assertNotIn("private-apply-token", prompt)
        self.assertNotIn("application_url", json.loads(prompt)["job"])

    def test_saved_job_generation_reuses_user_edited_result_without_a_browser(self):
        before = self.database.jobs.find_one({"linkedin_id": JOB.linkedin_id})
        self.database.tailored_resumes.update_one(
            {"_id": self.resume_id}, {"$set": {"resume.summary": "Previously edited by user"}},
        )
        with (
            patch.object(self.workflow, "_complete") as model,
            patch.object(self.runner.browser, "jobs") as browse,
        ):
            response = self.post(f"/api/jobs/{JOB.linkedin_id}/generate", {"consent": True})
            self.assertEqual(response.status_code, 202)
            task = self.wait_task(response.get_json()["task_id"])
        self.assertEqual(task["status"], "succeeded")
        self.assertEqual(task["cached"], 1)
        model.assert_not_called()
        browse.assert_not_called()
        after = self.database.jobs.find_one({"linkedin_id": JOB.linkedin_id})
        self.assertEqual(after["last_seen_at"], before["last_seen_at"])
        self.assertEqual(after["application_captured_at"], before["application_captured_at"])
        self.assertEqual(self.detail()["resume"]["summary"], "Previously edited by user")

    def test_saved_description_can_generate_a_new_resume_without_a_fresh_observation(self):
        saved = JOB.model_copy(update={
            "linkedin_id": "887766", "url": "https://www.linkedin.com/jobs/view/887766/",
        })
        self.workflow.save_job("local", saved)
        observed = self.database.jobs.find_one({"linkedin_id": saved.linkedin_id})["last_seen_at"]
        with (
            patch.object(self.workflow, "_complete", return_value=json.dumps(PLAN)) as model,
            patch.object(self.workflow, "save_job", side_effect=AssertionError("No new crawl")),
        ):
            response = self.post(f"/api/jobs/{saved.linkedin_id}/generate", {"consent": True})
            self.assertEqual(response.status_code, 202)
            task = self.wait_task(response.get_json()["task_id"])
        self.assertEqual(task["status"], "succeeded")
        self.assertEqual(task["generated"], 1)
        model.assert_called_once()
        self.assertEqual(self.database.jobs.find_one({"linkedin_id": saved.linkedin_id})["last_seen_at"], observed)

    def test_saved_generation_requires_consent_and_owned_job(self):
        self.assertEqual(self.post(f"/api/jobs/{JOB.linkedin_id}/generate", {}).status_code, 400)
        self.database.jobs.insert_one({"_id": "other-job", "user_id": "other", "linkedin_id": "999"})
        self.assertEqual(self.post("/api/jobs/999/generate", {"consent": True}).status_code, 404)


class PdfRendererTests(unittest.TestCase):
    def test_unicode_and_literal_markup_are_text_not_html(self):
        profile = SOURCE.model_copy(deep=True)
        profile.contact.name = "张三 Example"
        profile.summary = "软件工程师 <script>not code</script> & Python"
        content = SimpleTemplate().render(profile)
        self.assertTrue(content.startswith(b"%PDF-"))
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)
        self.assertIn("张三", text)
        self.assertIn("软件工程师", text)
        self.assertIn("<script>not code</script>", text)

    def test_missing_font_blank_resume_and_unsupported_characters_are_explicit_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(DocumentError):
                SimpleTemplate().render(SOURCE, font_path=Path(temp) / "missing-font.ttf")
        with self.assertRaises(DocumentError):
            SimpleTemplate().render(ResumeProfile())
        unsupported = SOURCE.model_copy(deep=True)
        unsupported.summary = "\U0010ffff"
        with self.assertRaises(DocumentError):
            SimpleTemplate().render(unsupported)

    def test_pdf_text_size_boundary_is_exact(self):
        profile = ResumeProfile.model_validate({
            "contact": {"name": "A"},
            "experience": [{"bullets": ["x" * 10000] * 7 + ["x" * 9999]}],
        })
        self.assertTrue(SimpleTemplate().render(profile).startswith(b"%PDF-"))
        profile.experience[0].bullets[-1] += "x"
        with self.assertRaises(DocumentError):
            SimpleTemplate().render(profile)


if __name__ == "__main__":
    unittest.main()
