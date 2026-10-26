import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.disabled_download_button = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and "href" in attributes:
            self.hrefs.append(attributes["href"])
        if tag == "button" and "disabled" in attributes:
            # The visible label is tested separately in the page text.
            self.disabled_download_button = True


class SiteSafetyTests(unittest.TestCase):
    def read_html(self, name):
        return (ROOT / name).read_text(encoding="utf-8")

    def test_landing_page_has_prominent_negative_release_gate(self):
        html = self.read_html("index.html")
        self.assertIn("NO TIFF IS CLEARED FOR DOWNLOAD OR SUBMISSION", html)
        self.assertIn("Download unavailable", html)
        self.assertIn("no candidate raster", html)
        parser = Links()
        parser.feed(html)
        self.assertTrue(parser.disabled_download_button)

    def test_executive_summary_covers_all_nine_sites_and_blocks_download(self):
        html = self.read_html("executive-summary.html")
        for site in ("GEMSDOE24", "GEMSDOE25", "GEMSDOE27", "GEMSDOE28", "GEMSDOE30", "GEMSDOE31", "GEMSDOE32", "GEMSDOE33", "GEMSDOE36"):
            with self.subTest(site=site):
                self.assertIn(site, html)
        self.assertIn("Score estimate", html)
        self.assertIn("Unavailable — no admissible HOLDOUT-DTI", html)
        self.assertIn("DO NOT DOWNLOAD OR SUBMIT A FILE", html)

    def test_no_site_page_links_directly_to_a_historical_submission_tiff(self):
        for name in ("index.html", "executive-summary.html", "hypotheses.html", "sources.html"):
            parser = Links()
            parser.feed(self.read_html(name))
            with self.subTest(page=name):
                self.assertFalse(
                    any(
                        "/docs/downloads/" in href.lower()
                        and href.lower().split("?", 1)[0].endswith((".tif", ".tiff"))
                        for href in parser.hrefs
                    ),
                    "Historical submission TIFFs must not appear as download actions. User-supplied input/sample mirrors may be listed for provenance.",
                )

    def test_negative_run_card_is_well_formed_and_has_no_claimed_result(self):
        card = json.loads((ROOT / "data/run-card.json").read_text(encoding="utf-8"))
        self.assertEqual(card["verdict"], "negative")
        self.assertFalse(card["promotion_authorized"])
        self.assertEqual(card["holdout_dti"]["status"], "NOT_RUN")
        self.assertIsNone(card["holdout_dti"]["value"])
        self.assertIsNone(card["raster_sha256"])
        self.assertEqual(card["validator_output"]["status"], "NOT_RUN")
        self.assertIsNone(card["submission_name"])
        self.assertIsNone(card["submission_note"])

    def test_hypothesis_page_does_not_claim_validation_or_viability(self):
        html = self.read_html("hypotheses.html")
        self.assertIn("not yet viable", html)
        self.assertIn("Expected DTI improvement:</strong> not estimated", html)
        self.assertIn("No experiment has started", html)


if __name__ == "__main__":
    unittest.main()
