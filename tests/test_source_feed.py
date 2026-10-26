from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.refresh_public_feed import probe_source, refresh


class FakeResponse:
    def __init__(self, body: bytes, final_url: str, status: int = 200) -> None:
        self._body = body
        self._final_url = final_url
        self.status = status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def geturl(self) -> str:
        return self._final_url

    def read(self, limit: int = -1) -> bytes:
        if limit < 0:
            return self._body
        return self._body[:limit]


class SourceFeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = {
            "id": "example",
            "label": "Example public page",
            "kind": "test fixture",
            "url": "https://example.org/",
        }

    @patch("scripts.refresh_public_feed.urlopen")
    def test_public_page_records_availability_but_does_not_scrape_scores(self, mock_urlopen) -> None:
        body = b"<html><head><title>Official leaderboard</title></head><body>0.4437</body></html>"
        mock_urlopen.return_value = FakeResponse(body, self.source["url"])
        result = probe_source(self.source)
        self.assertEqual("ok", result["status"])
        self.assertEqual("Official leaderboard", result["title"])
        self.assertNotIn("score", result)
        self.assertNotIn("leaderboard_value", result)
        self.assertIsNotNone(result["content_sha256"])

    @patch("scripts.refresh_public_feed.urlopen")
    def test_login_redirect_is_not_mislabeled_as_available_data(self, mock_urlopen) -> None:
        login_url = "https://www.drivendata.org/accounts/login/?next=%2Fdata%2F"
        body = b"<html><title>Login</title></html>"
        mock_urlopen.return_value = FakeResponse(body, login_url)
        result = probe_source(self.source)
        self.assertEqual("login_required", result["status"])
        self.assertIn("no authenticated content", result["note"])

    @patch("scripts.refresh_public_feed.urlopen")
    def test_refresh_writes_machine_readable_feed(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeResponse(b"<title>Source</title>", self.source["url"])
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            catalog = directory / "catalog.json"
            output = directory / "status.json"
            catalog.write_text(json.dumps([self.source]), encoding="utf-8")
            feed = refresh(catalog, output)
            saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(feed, saved)
        self.assertFalse(saved["scores_scraped"])
        self.assertFalse(saved["upload_or_submission_actions_performed"])
        self.assertEqual(1, len(saved["sources"]))
        self.assertEqual("ok", saved["sources"][0]["status"])

    @patch("scripts.refresh_public_feed.urlopen", side_effect=TimeoutError("test timeout"))
    def test_network_timeout_is_reported_without_crashing_the_feed(self, mock_urlopen) -> None:
        result = probe_source(self.source)
        self.assertEqual("network_error", result["status"])
        self.assertIn("timeout", result["note"])

    def test_catalog_rejects_non_https_urls(self) -> None:
        bad_source = {**self.source, "url": "http://example.org/"}
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            catalog = directory / "catalog.json"
            output = directory / "status.json"
            catalog.write_text(json.dumps([bad_source]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "absolute HTTPS"):
                refresh(catalog, output)

    def test_catalog_rejects_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            catalog = directory / "catalog.json"
            output = directory / "status.json"
            catalog.write_text(json.dumps([self.source, self.source]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate source id"):
                refresh(catalog, output)


if __name__ == "__main__":
    unittest.main()
