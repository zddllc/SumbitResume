from io import BytesIO
from unittest.mock import patch

from resume_app.errors import AppError
from test_product import SOURCE, ProductTestCase, word_bytes


class ResumeImportTests(ProductTestCase):
    def setUp(self):
        super().setUp()
        self.setup_user()
        self.settings()
        self.confirmed()
        self.saved = SOURCE.model_copy(deep=True)
        self.saved.summary = "Hand-edited introduction to keep."
        self.saved.experience[0].bullets = ["Important manual point.", "Earlier point."]
        self.database.resumes.update_one({"_id": "local"}, {"$set": {
            "draft": self.saved.model_dump(), "edit_token": "saved-draft",
            "draft_filename": "original.docx", "source_text_hash": "original-hash",
        }})

    def parse(self):
        with patch.object(self.workflow, "_complete", return_value=SOURCE.model_dump_json()):
            self.workflow.parse_resume("local", "new.docx", "New upload", self.workflow.llm_settings("local"))
        return self.database.resumes.find_one({"_id": "local"})

    def apply(self, record, profile=None, **overrides):
        return self.post("/api/resume/import/apply", {
            "edit_token": record["edit_token"], "import_id": record["pending_import"]["id"],
            "profile": profile if profile is not None else self.saved.model_dump(), **overrides,
        })

    def test_parse_preserves_draft_confirmed_metadata_and_edit_token(self):
        before = self.database.resumes.find_one({"_id": "local"})
        after = self.parse()
        for field in before:
            self.assertEqual(after[field], before[field], field)
        self.assertEqual(after["pending_import"]["profile"], SOURCE.model_dump())
        self.assertEqual(after["pending_import"]["filename"], "new.docx")
        self.assertTrue(after["pending_import"]["id"])

    def test_first_upload_is_a_candidate_until_the_user_applies_it(self):
        self.database.resumes.delete_one({"_id": "local"})
        record = self.parse()
        self.assertNotIn("draft", record)
        self.assertNotIn("confirmed", record)
        self.assertTrue(record["edit_token"])
        self.assertEqual(self.apply(record, SOURCE.model_dump()).status_code, 200)
        stored = self.database.resumes.find_one({"_id": "local"})
        self.assertEqual(stored["draft"], SOURCE.model_dump())
        self.assertIsNone(stored["pending_import"])
        self.assertNotIn("confirmed", stored)

    def test_apply_saves_exact_selection_as_draft_without_confirming_it(self):
        record = self.parse()
        selected = self.saved.model_dump()
        selected["skills"].append("New selected skill")
        with patch.object(self.workflow, "_complete") as model:
            response = self.apply(record, selected)
        self.assertEqual(response.status_code, 200, response.get_json())
        model.assert_not_called()
        stored = self.database.resumes.find_one({"_id": "local"})
        self.assertEqual(stored["draft"], selected)
        self.assertEqual(stored["confirmed"], SOURCE.model_dump())
        self.assertEqual(stored["draft_filename"], "new.docx")
        self.assertNotEqual(stored["edit_token"], record["edit_token"])
        self.assertEqual(stored["source_text_hash"], record["pending_import"]["source_text_hash"])
        self.assertIsNone(stored["pending_import"])
        self.assertEqual(self.post("/api/resume/confirm", {
            "edit_token": stored["edit_token"], "profile": selected,
        }).status_code, 200)

    def test_discard_keeps_existing_data_and_cannot_be_replayed(self):
        record = self.parse()
        body = {"edit_token": record["edit_token"], "import_id": record["pending_import"]["id"]}
        self.assertEqual(self.post("/api/resume/import/discard", body).status_code, 200)
        stored = self.database.resumes.find_one({"_id": "local"})
        for field in ("draft", "confirmed", "edit_token", "draft_filename", "source_text_hash"):
            self.assertEqual(stored[field], record[field])
        self.assertIsNone(stored["pending_import"])
        self.assertEqual(self.post("/api/resume/import/discard", body).status_code, 409)

    def test_stale_tokens_or_wrong_import_cannot_apply_or_discard(self):
        record = self.parse()
        for overrides in ({"edit_token": "old-token"}, {"import_id": "different-import"}):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.apply(record, **overrides).status_code, 409)
                self.assertEqual(self.post("/api/resume/import/discard", {
                    "edit_token": record["edit_token"], "import_id": record["pending_import"]["id"],
                    **overrides,
                }).status_code, 409)
                self.assertEqual(self.database.resumes.find_one({"_id": "local"}), record)

    def test_invalid_or_nameless_selection_does_not_consume_candidate(self):
        record = self.parse()
        for profile in ({"unsupported": True}, {"contact": {"name": ""}}):
            with self.subTest(profile=profile):
                self.assertEqual(self.apply(record, profile).status_code, 400)
                self.assertEqual(self.database.resumes.find_one({"_id": "local"}), record)

    def test_confirmation_cannot_bypass_the_pending_comparison(self):
        record = self.parse()
        response = self.post("/api/resume/confirm", {
            "edit_token": record["edit_token"], "profile": SOURCE.model_dump(),
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.database.resumes.find_one({"_id": "local"}), record)

    def test_another_upload_is_rejected_before_spending_model_credits(self):
        record = self.parse()
        with patch.object(self.workflow, "_complete") as model:
            with self.assertRaises(AppError):
                self.workflow.parse_resume("local", "second.docx", "Another upload", self.workflow.llm_settings("local"))
            response = self.post("/api/resume/upload", data={
                "file": (BytesIO(word_bytes()), "second.docx"), "consent": "yes",
            })
        self.assertEqual(response.status_code, 409)
        model.assert_not_called()
        self.assertEqual(self.database.resumes.find_one({"_id": "local"}), record)

    def test_failed_parsing_does_not_change_existing_content(self):
        before = self.database.resumes.find_one({"_id": "local"})
        with patch.object(self.workflow, "_complete", return_value='{"contact": {"name": ""}}'):
            with self.assertRaises(AppError):
                self.workflow.parse_resume("local", "bad.docx", "Bad extraction", self.workflow.llm_settings("local"))
        self.assertEqual(self.database.resumes.find_one({"_id": "local"}), before)

    def test_edits_saved_during_model_call_are_preserved(self):
        def complete(*_args, **_kwargs):
            self.database.resumes.update_one({"_id": "local"}, {"$set": {
                "draft.summary": "Saved while the model was running.", "edit_token": "newer-edit",
            }})
            return SOURCE.model_dump_json()

        with patch.object(self.workflow, "_complete", side_effect=complete):
            self.workflow.parse_resume("local", "new.docx", "New upload", self.workflow.llm_settings("local"))
        stored = self.database.resumes.find_one({"_id": "local"})
        self.assertEqual(stored["draft"]["summary"], "Saved while the model was running.")
        self.assertEqual(stored["edit_token"], "newer-edit")
        self.assertEqual(stored["pending_import"]["profile"], SOURCE.model_dump())

    def test_state_normalizes_legacy_candidate_without_rewriting_it(self):
        record = self.parse()
        self.database.resumes.update_one({"_id": "local"}, {"$unset": {
            "pending_import.profile.publications": "",
        }})
        result = self.client.get("/api/state").get_json()["resume"]
        self.assertEqual(result["pending_import"]["id"], record["pending_import"]["id"])
        self.assertEqual(result["pending_import"]["profile"]["publications"], [])
        self.assertNotIn("publications", self.database.resumes.find_one({"_id": "local"})["pending_import"]["profile"])

    def test_candidate_created_during_model_call_cannot_be_overwritten(self):
        before = self.database.resumes.find_one({"_id": "local"})

        def complete(*_args, **_kwargs):
            self.database.resumes.update_one({"_id": "local"}, {"$set": {
                "pending_import": {"id": "another-upload", "profile": self.saved.model_dump()},
            }})
            return SOURCE.model_dump_json()

        with patch.object(self.workflow, "_complete", side_effect=complete):
            with self.assertRaises(AppError):
                self.workflow.parse_resume("local", "new.docx", "New upload", self.workflow.llm_settings("local"))
        stored = self.database.resumes.find_one({"_id": "local"})
        self.assertEqual(stored["pending_import"]["id"], "another-upload")
        for field in before:
            self.assertEqual(stored[field], before[field])

    def test_edit_between_reading_and_applying_import_is_not_overwritten(self):
        record = self.parse()
        update_one = self.database.resumes.update_one

        def concurrent_update(query, update, **kwargs):
            if "pending_import.id" in query:
                update_one({"_id": "local"}, {"$set": {"edit_token": "concurrent-edit"}})
            return update_one(query, update, **kwargs)

        with patch.object(self.database.resumes, "update_one", side_effect=concurrent_update):
            response = self.apply(record, SOURCE.model_dump())
        self.assertEqual(response.status_code, 409)
        stored = self.database.resumes.find_one({"_id": "local"})
        self.assertEqual(stored["edit_token"], "concurrent-edit")
        self.assertEqual(stored["draft"], record["draft"])
        self.assertEqual(stored["pending_import"], record["pending_import"])
