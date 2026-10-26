from __future__ import annotations

import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
EXPECTED_SCORES = {
    "GEMSDOE24": "0.2477",
    "GEMSDOE25": "0.2600",
    "GEMSDOE27": "0.2449",
    "GEMSDOE28": "0.2710",
    "GEMSDOE30": "0.2600",
    "GEMSDOE31": "0.2708",
    "GEMSDOE32": "0.2778",
    "GEMSDOE33": "0.2632",
    "GEMSDOE36": "0.2750",
}
EXPECTED_SITES = set(EXPECTED_SCORES)


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        for name in ("href", "src"):
            value = attrs_dict.get(name)
            if value:
                self.links.append(value)
        element_id = attrs_dict.get("id")
        if element_id:
            self.ids.add(element_id)


class SiteIntegrityTests(unittest.TestCase):
    def test_every_local_html_link_and_asset_exists(self) -> None:
        failures: list[str] = []
        for page in sorted(DOCS.rglob("*.html")):
            parser = LinkCollector()
            parser.feed(page.read_text(encoding="utf-8"))
            for link in parser.links:
                parsed = urlsplit(link)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                target = (page.parent / unquote(parsed.path)).resolve()
                if not target.exists():
                    failures.append(f"{page.relative_to(ROOT)} -> {link}")
                    continue
                if parsed.fragment and target.suffix == ".html":
                    target_parser = LinkCollector()
                    target_parser.feed(target.read_text(encoding="utf-8"))
                    if unquote(parsed.fragment) not in target_parser.ids:
                        failures.append(f"{page.relative_to(ROOT)} -> missing fragment {link}")
        self.assertEqual([], failures, "Broken local links:\n" + "\n".join(failures))

    def test_site_audit_covers_exact_requested_sites(self) -> None:
        audit = json.loads((DOCS / "data/site-audit.json").read_text(encoding="utf-8"))
        sites = audit["sites"]
        self.assertEqual(EXPECTED_SITES, {item["site"] for item in sites})
        self.assertEqual(len(EXPECTED_SITES), len(sites), "Each site should appear exactly once")
        self.assertEqual(EXPECTED_SCORES, {item["site"]: item["historical_claim"] for item in sites})
        self.assertEqual("0.4437", audit["current_public_leaderboard"]["value"])
        self.assertNotIn("ORGANIZER-CONFIRMED", audit["current_public_leaderboard"]["evidence_class"])
        for item in sites:
            self.assertRegex(item["historical_claim"], r"^\d+\.\d{4}$")
            self.assertIn("OWNER-REPORTED", item["historical_claim_class"])
            self.assertEqual("Not estimable", item["leaderboard_estimate"])
            self.assertFalse(item["unique_cleared_for_new_submission"])
            self.assertTrue(item["url"].startswith("https://"))
        self.assertIn("0.2683", audit["sites"][-1]["irregularity"])
        gems32 = next(item for item in sites if item["site"] == "GEMSDOE32")
        self.assertTrue(gems32["unique_under_protocol"].startswith("NO / NOT ESTABLISHED"))
        self.assertFalse(audit["project_decision"]["new_tiff_generated"])
        self.assertFalse(audit["project_decision"]["ok_to_submit"])
        self.assertEqual("negative", audit["project_decision"]["verdict"])

    def test_run_card_fails_closed_and_has_required_fields(self) -> None:
        card = json.loads((DOCS / "data/run-card.json").read_text(encoding="utf-8"))
        required = {
            "hypothesis",
            "mechanism",
            "named_non_fault_process_that_could_mimic_it",
            "holdout_dti",
            "correlation_overlap_vs_registry",
            "raster_sha256",
            "validator_output",
            "submission_name",
            "submission_note_max_140_characters",
            "verdict",
        }
        self.assertTrue(required.issubset(card))
        self.assertEqual("negative", card["verdict"])
        self.assertFalse(card["slot_approved"])
        self.assertFalse(card["new_tiff_generated"])
        self.assertIsNone(card["holdout_dti"]["value"])
        self.assertIsNone(card["raster_sha256"])

    def test_landing_page_makes_no_upload_decision_unambiguous(self) -> None:
        page = (DOCS / "index.html").read_text(encoding="utf-8")
        self.assertIn("NO TIFF TO DOWNLOAD", page)
        self.assertIn("DO NOT SUBMIT", page)
        self.assertIn("0.2778", page)
        self.assertIn("OWNER-REPORTED / UNVERIFIED", page)
        self.assertIn("Not estimable", page)

    def test_no_candidate_tiff_is_misrepresented_as_ready(self) -> None:
        tiffs = list(ROOT.rglob("*.tif")) + list(ROOT.rglob("*.tiff"))
        tiffs = [p for p in tiffs if ".git" not in p.parts]
        self.assertEqual([], tiffs, "This checkout is blocked and must not contain a candidate TIFF")

    def test_readme_requires_charter_at_session_start(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertRegex(readme, re.compile(r"read this README.*project-charter", re.IGNORECASE | re.DOTALL))
        self.assertTrue((DOCS / "project-charter.md").is_file())


if __name__ == "__main__":
    unittest.main()
