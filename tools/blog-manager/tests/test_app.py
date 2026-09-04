from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from app import create_app


class AppSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        test_parent = Path(__file__).resolve().parents[1] / ".test-workspace"
        test_parent.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=test_parent)
        root = Path(self.temporary.name)
        (root / "package.json").write_text("{}", encoding="utf-8")
        (root / "src" / "content" / "posts").mkdir(parents=True)
        (root / "src" / "content.config.ts").write_text("// fixture", encoding="utf-8")
        (root / "src" / "content" / "posts" / "sample.md").write_text(
            "---\ntitle: Sample\ndescription: Example\npubDate: 2026-09-04\ndraft: false\n---\nBody\n", encoding="utf-8"
        )
        data_dir = root / "src" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "open-source.json").write_text(
            json.dumps([{"slug":"example","name":"Example","repository":"https://github.com/example/repo","description":"Example","tags":[],"contributions":[],"accent":"otel"}]),
            encoding="utf-8",
        )
        self.app = create_app(root)
        self.app.testing = True
        self.client = self.app.test_client()
        self.csrf_token = "test-csrf-token"
        with self.client.session_transaction() as client_session:
            client_session["csrf_token"] = self.csrf_token
        self.csrf_headers = {"X-CSRF-Token": self.csrf_token}

    def tearDown(self) -> None:
        self.app.config["PROCESSES"].stop_preview()
        self.temporary.cleanup()

    def test_pages_render(self) -> None:
        for path in ("/", "/articles", "/articles/sample/edit", "/import", "/open-source", "/open-source/example", "/relations", "/preview"):
            response = self.client.get(path)
            self.assertEqual(200, response.status_code, path)

    def test_import_api_complete_and_missing(self) -> None:
        complete = b"---\ntitle: Imported\ndescription: Complete\npubDate: 2026-09-04\n---\nBody\n"
        response = self.client.post("/api/import/inspect", data={"file": (io.BytesIO(complete), "complete.md")}, headers=self.csrf_headers)
        self.assertEqual([], response.get_json()["missing"])
        missing = self.client.post("/api/import/inspect", data={"file": (io.BytesIO(b"Body only"), "missing.md")}, headers=self.csrf_headers)
        self.assertEqual(["title", "description", "pubDate"], missing.get_json()["missing"])

    def test_overwrite_requires_server_side_confirmation(self) -> None:
        markdown = b"---\ntitle: Replacement\ndescription: Complete\npubDate: 2026-09-04\n---\nBody\n"
        fields = {
            "file": (io.BytesIO(markdown), "sample.md"),
            "title": "Replacement",
            "description": "Complete",
            "pubDate": "2026-09-04",
            "slug": "sample",
            "conflictAction": "overwrite",
        }
        rejected = self.client.post("/api/import/commit", data=fields, headers=self.csrf_headers)
        self.assertEqual(400, rejected.status_code)
        self.assertIn("explicit confirmation", rejected.get_json()["error"])

        confirmed_fields = dict(fields)
        confirmed_fields["file"] = (io.BytesIO(markdown), "sample.md")
        confirmed_fields["overwriteConfirmed"] = "1"
        accepted = self.client.post("/api/import/commit", data=confirmed_fields, headers=self.csrf_headers)
        self.assertEqual(200, accepted.status_code)

    def test_github_fetch_failure_keeps_manual_path(self) -> None:
        response = self.client.post("/api/github/fetch", json={"url": "not-a-github-url"}, headers=self.csrf_headers)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.get_json()["manual"])

    def test_write_endpoints_reject_missing_csrf_token(self) -> None:
        response = self.client.post("/api/preview/start")
        self.assertEqual(400, response.status_code)
        self.assertIn("CSRF", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
