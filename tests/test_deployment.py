import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mongomock
from mongomock.gridfs import enable_gridfs_integration

from resume_app import create_app
from resume_app.config import base_path, load_config
from resume_app.models import ResumeProfile
from resume_app.pdf_export import _font_path
from resume_app.storage import SecretStore

enable_gridfs_integration()


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = mongomock.MongoClient(tz_aware=True).resume
        self.config = {
            "TESTING": True, "INSTANCE_DIR": Path(self.temp.name) / "instance",
            "BROWSER_PROFILE_ROOT": Path(self.temp.name) / "browser",
            "APP_BASE_PATH": "/resume", "TRUSTED_HOSTS": ["resume.example.test"],
            "TRUST_PROXY": True, "SESSION_COOKIE_SECURE": True,
        }
        self.app = create_app(self.config, database=self.db)
        self.addCleanup(self.app.extensions["resume_runner"].close)
        self.client = self.app.test_client()

    def request(self, method, path, **kwargs):
        headers = {
            "X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.7",
            **kwargs.pop("headers", {}),
        }
        return self.client.open(
            path, method=method, base_url="https://resume.example.test",
            headers=headers, **kwargs,
        )

    def test_prefix_authentication_cookie_scope_and_csrf_rotation(self):
        first = self.request("GET", "/resume/api/auth/session")
        self.assertEqual(first.status_code, 200)
        csrf = first.get_json()["csrf_token"]
        self.assertIn("Path=/resume/", first.headers["Set-Cookie"])
        self.assertIn("resume_session=", first.headers["Set-Cookie"])
        self.assertIn("Secure", first.headers["Set-Cookie"])
        response = self.request("POST", "/resume/api/auth/setup", json={
            "name": "Prefix User", "email": "prefix@example.test", "password": "password8",
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(response.status_code, 201, response.get_json())
        current = response.get_json()["csrf_token"]
        self.assertNotEqual(current, csrf)
        self.assertEqual(self.request("GET", "/resume/api/state").status_code, 200)
        self.assertEqual(self.request(
            "POST", "/resume/api/personal", json={}, headers={"X-CSRF-Token": csrf},
        ).status_code, 403)
        self.assertEqual(self.request(
            "POST", "/resume/api/personal", json={}, headers={"X-CSRF-Token": current},
        ).status_code, 200)
        self.assertEqual(self.request("GET", "/api/auth/session").status_code, 404)

    def test_pdf_url_includes_the_mount_prefix(self):
        first = self.request("GET", "/resume/api/auth/session").get_json()
        session = self.request("POST", "/resume/api/auth/setup", json={
            "name": "Prefix User", "email": "prefix@example.test", "password": "password8",
        }, headers={"X-CSRF-Token": first["csrf_token"]}).get_json()
        profile = ResumeProfile.model_validate({"contact": {"name": "Sample"}, "summary": "Sample resume."})
        self.db.tailored_resumes.insert_one({
            "_id": "prefix-resume", "user_id": "local", "job_id": "local:123",
            "job": {"linkedin_id": "123"}, "resume": profile.model_dump(),
            "review_status": "pending", "edit_token": "first-token",
        })
        response = self.request(
            "POST", "/resume/api/tailored/prefix-resume/review",
            json={"confirmed": True, "edit_token": "first-token", "profile": profile.model_dump()},
            headers={"X-CSRF-Token": session["csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["pdf_url"], "/resume/api/tailored/prefix-resume/pdf")
        self.assertEqual(self.request("GET", response.get_json()["pdf_url"]).mimetype, "application/pdf")

    def test_health_is_available_without_a_session_but_private_data_is_not(self):
        response = self.request("GET", "/resume/api/health")
        self.assertEqual(response.get_json(), {"status": "ok"})
        self.assertNotIn("Set-Cookie", response.headers)
        self.assertEqual(self.request("GET", "/resume/api/state").status_code, 401)

    def test_json_login_requires_csrf_even_before_initial_setup(self):
        initial = self.request("GET", "/resume/api/auth/session").get_json()
        self.assertEqual(self.request(
            "POST", "/resume/api/auth/login", json={"email": "unknown", "password": "password8"},
        ).status_code, 403)
        self.assertTrue(initial["setup_required"])

    def test_missing_migration_key_does_not_generate_a_replacement(self):
        self.db.llm_settings.insert_one({"_id": "local", "key_encrypted": "existing-ciphertext"})
        other = Path(self.temp.name) / "missing-instance"
        with self.assertRaisesRegex(RuntimeError, "密钥缺失"):
            create_app({**self.config, "INSTANCE_DIR": other}, database=self.db)
        self.assertFalse((other / "secrets.json").exists())

    def test_existing_key_is_retained_when_the_application_is_recreated(self):
        path = Path(self.config["INSTANCE_DIR"]) / "secrets.json"
        before = path.read_bytes()
        other = create_app(self.config, database=self.db)
        self.addCleanup(other.extensions["resume_runner"].close)
        self.assertEqual(path.read_bytes(), before)

    def test_prefix_validation_supports_root_and_nested_paths(self):
        self.assertEqual(base_path("/"), "")
        self.assertEqual(base_path("/tools/resume/"), "/tools/resume")
        for value in ("resume", "//resume", "/resume/../admin", "/resume?query=1", "/resume space"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                base_path(value)

    def test_linux_font_candidate_is_not_a_windows_path_dependency(self):
        with (
            patch("resume_app.pdf_export.sys.platform", "linux"),
            patch.object(Path, "is_file", lambda path: path.name == "wqy-zenhei.ttc"),
        ):
            self.assertEqual(_font_path(None).name, "wqy-zenhei.ttc")

    def test_private_environment_file_is_parsed_without_shell_execution(self):
        path = Path(self.temp.name) / "private.env"
        path.write_text(
            "APP_BASE_PATH=/tools/resume\n"
            "MONGO_URI=mongodb://example.invalid/resume?authSource=admin&tls=true\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"RESUME_ENV_FILE": str(path)}, clear=True):
            config = load_config()
        self.assertEqual(config["APP_BASE_PATH"], "/tools/resume")
        self.assertEqual(config["MONGO_URI"], "mongodb://example.invalid/resume?authSource=admin&tls=true")

    @unittest.skipUnless(os.name == "posix", "POSIX permissions require a POSIX filesystem")
    def test_secret_permissions_are_private_on_linux(self):
        path = Path(self.temp.name) / "private" / "secrets.json"
        SecretStore(path)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertIn("encryption_key", json.loads(path.read_text()))


if __name__ == "__main__":
    unittest.main()
