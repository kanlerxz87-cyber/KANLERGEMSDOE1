"""Safety checks for the Pages artifact actually deployed by .github/workflows/pages.yml.

Intended state (2026-10-27):
- No contest raster is cleared for submission; the landing page says so in a STOP banner.
- Download links exist only for known 2026-10-27 research-hold lanes (OCDA-MSCS, H-UNQ-1,
  CONCORD), and every page that links a .tif/.zip carries explicit not-cleared labeling.
- All nine focus sites are covered in the executive summary with their duplication findings.
"""
import hashlib
import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import refresh_public_feed as feed


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.disabled = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "href" in a:
            self.hrefs.append(a["href"])
        if tag == "button" and "disabled" in a:
            self.disabled = True


class SiteSafetyTests(unittest.TestCase):
    def html(self, name):
        return (ROOT / "docs" / name).read_text(encoding="utf-8")

    def test_landing_blocks_submission_and_discloses_overlaps(self):
        html = self.html("index.html")
        self.assertIn("STOP — NO RASTER IS CLEARED FOR SUBMISSION", html)
        self.assertIn("99.39%", html)
        self.assertIn("99.59%", html)
        self.assertIn("99.19%", html)
        self.assertIn("not score-cleared", html.lower())
        self.assertIn("selector approval", html.lower())
        self.assertIn("gemsdoe32-kanler1-ocda-mscs-exp3-37654d-20261027T1842Z-1db32b55-zeros.tif", html)
        self.assertIn("h-unq1-blind-stepover-radiometric-conduit-dots-20261027T170959Z-339ac2dd-zeros.tif", html)
        self.assertIn("Not cleared to submit", html)

    def test_executive_covers_nine_sites_and_negative_findings(self):
        html = self.html("executive-summary.html")
        for site in ("GEMSDOE24", "GEMSDOE25", "GEMSDOE27", "GEMSDOE28", "GEMSDOE30", "GEMSDOE31", "GEMSDOE32", "GEMSDOE33", "GEMSDOE36"):
            with self.subTest(site=site):
                self.assertIn(site, html)
        self.assertIn("holdout dti diagnostic", html.lower())
        self.assertIn("0.0078", html)
        self.assertIn("0.105830", html)
        self.assertIn("not a leaderboard forecast", html.lower())
        self.assertIn("no organizer receipt", html.lower())
        self.assertIn("97.58%", html)

    def test_requested_site_scorecard_is_provenance_labeled_and_fail_closed(self):
        page = self.html("focus-sites-review-20261028.html")
        card = json.loads((ROOT / "docs/evidence/review_run_card_20261028.json").read_text())
        for site in ("GEMSDOE24", "GEMSDOE25", "GEMSDOE27", "GEMSDOE28", "GEMSDOE30", "GEMSDOE31", "GEMSDOE32", "GEMSDOE33", "GEMSDOE36"):
            with self.subTest(site=site):
                self.assertIn(site, page)
        for value in ("0.2477", "0.2600", "0.2449", "0.2710", "0.2708", "0.2778", "0.2632", "0.2750"):
            self.assertIn(value, page)
        self.assertIn("not organizer receipts", page.lower())
        self.assertIn("FAIL", page)
        self.assertIn("no file is cleared to download and submit", page.lower())
        self.assertFalse(card["ok_to_download_and_submit"])
        self.assertEqual(card["verdict"], "negative")
        self.assertEqual(card["holdout_dti"]["label"], "HOLDOUT-DTI (historical evidence; not freshly rerun and not a leaderboard estimate)")
        self.assertEqual(card["validator_output"]["shape"], [3730, 3292])
        self.assertFalse(card["validator_output"]["organizer_template_authenticated"])
        self.assertGreater(card["correlation_overlap_vs_registry"]["literal_lattice_overlap_within_3px"], .70)
        self.assertLessEqual(card["submission_note_characters"], 140)

    def test_download_links_only_known_research_lanes_with_negative_labeling(self):
        allowed = ("ocda-mscs", "h-unq1", "concord5", "h195field", "upflow")
        for page in ("index.html", "executive-summary.html", "how-to-submit.html"):
            html = self.html(page)
            parser = Links()
            parser.feed(html)
            local_tif_zip = [h for h in parser.hrefs
                             if not urlsplit(h).scheme and not urlsplit(h).netloc
                             and urlsplit(h).path.lower().endswith((".tif", ".tiff", ".zip"))]
            with self.subTest(page=page):
                for h in local_tif_zip:
                    self.assertTrue(any(a in h for a in allowed),
                                    f"{page} links an unexpected local raster: {h}")
                if local_tif_zip:
                    low = html.lower()
                    self.assertTrue("do not submit" in low or "not cleared" in low,
                                    f"{page} links local rasters without negative labeling")
                    self.assertIn("selector", low)

    def test_concord_lane_card_is_negative_and_unique(self):
        c = json.loads((ROOT / "docs/evidence/run_card_concord.json").read_text())
        self.assertEqual(c["verdict"], "negative")
        self.assertFalse(c["ok_to_submit"])
        self.assertIn("CONCORD", c["hypothesis"])
        self.assertLessEqual(len(c["submission_note"]), 140)
        self.assertEqual(c["holdout_dti"]["n_withheld_positives"], 22232)
        self.assertFalse(c["correlation_overlap_vs_registry"]["full_registry_checked"])

    def test_ocda_mscs_lane_card_is_negative_admissible_and_unique(self):
        c = json.loads((ROOT / "docs/evidence/run_card_ocda_mscs.json").read_text())
        self.assertEqual(c, json.loads((ROOT / "evidence/run_card_ocda_mscs.json").read_text()))
        self.assertEqual(c["verdict"], "negative")
        self.assertFalse(c["ok_to_submit"])
        self.assertFalse(c["slot_used"])
        self.assertEqual(c["holdout_dti"]["status"], "ADMISSIBLE_FOLD_LOCAL")
        self.assertEqual(c["holdout_dti"]["score_label"], "HOLDOUT-DTI")
        self.assertEqual(c["holdout_dti"]["n_withheld_positives"], 22232)
        val = c["holdout_dti"]["valid_value"]
        ci = c["holdout_dti"]["valid_ci95"]
        self.assertTrue(0.0 < ci[0] <= val <= ci[1] < 1.0)
        self.assertTrue(c["validator_output"]["all_checks_passed"])
        self.assertTrue(c["validator_output_nan"]["all_checks_passed"])
        self.assertEqual(hashlib.sha256((ROOT / c["raster_path_zeros"]).read_bytes()).hexdigest(), c["raster_sha256"])
        self.assertEqual(hashlib.sha256((ROOT / c["raster_path_nan"]).read_bytes()).hexdigest(), c["raster_sha256_nan"])
        self.assertTrue(c["correlation_overlap_vs_registry"]["discrete_detectors_surface_passed"])
        self.assertTrue(c["correlation_overlap_vs_registry"]["discrete_detectors_final_passed"])
        self.assertLessEqual(c["correlation_overlap_vs_registry"]["max_within_3px_vs_discrete_detectors"], 0.70)
        self.assertLessEqual(len(c["submission_note"]), 140)

    def test_all_local_html_links_resolve(self):
        for path in (ROOT / "docs").rglob("*.html"):
            p = Links()
            p.feed(path.read_text())
            for href in p.hrefs:
                parsed = urlsplit(href)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                with self.subTest(page=path.name, href=href):
                    self.assertTrue((path.parent / unquote(parsed.path)).is_file())

    def test_one_current_card_has_correction_and_hash(self):
        p = ROOT / "data" / "run-card.json"
        c = json.loads(p.read_text())
        self.assertEqual(c["verdict"], "negative")
        self.assertFalse(c["ok_to_submit"])
        self.assertEqual(c["holdout_dti"]["status"], "INADMISSIBLE")
        self.assertIsNone(c["holdout_dti"]["valid_value"])
        self.assertIsNone(c["holdout_dti"]["valid_ci95"])
        self.assertIn("ocda_mscs_valid_fold_local_oof", c["holdout_dti"])
        self.assertEqual(len(c["raster_sha256"]), 64)
        self.assertTrue(c["validator_output"]["all_checks_passed"])
        self.assertFalse(c["correlation_overlap_vs_registry"]["full_registry_checked"])
        self.assertGreater(c["correlation_overlap_vs_registry"]["final_dots_within_3px_of_lattice"], 0.70)
        self.assertLessEqual(len(c["submission_note"]), 140)
        self.assertEqual(c, json.loads((ROOT / "docs/evidence/current_run_card.json").read_text()))
        self.assertEqual(c, json.loads((ROOT / "evidence/run_card.json").read_text()))

    def test_hypothesis_page_discloses_untested_and_scope(self):
        text = self.html("hypotheses.html")
        self.assertIn("H-K1-A", text)
        self.assertIn("H-UNQ-1", text)
        self.assertIn("untested", text.lower())
        self.assertIn("swarm", text.lower())
        self.assertIn("conditional", text.lower())
        self.assertIn("selector approval", text.lower())

    def test_root_pages_redirect_to_actual_pages(self):
        for name in ("index", "executive-summary", "hypotheses", "sources", "research", "how-to-submit"):
            self.assertIn("docs/" + name + ".html", (ROOT / (name + ".html")).read_text())

    def test_parallel_archive_is_literal_duplicate(self):
        page = self.html("mplc/index.html")
        self.assertIn("NOT UNIQUE, DO NOT SUBMIT", page)
        self.assertIn("99.9522%", page)
        audit = json.loads((ROOT / "docs/evidence/protocol_audit_20261026.json").read_text())
        parallel = audit["prior_parallel_artifacts"]
        self.assertEqual(len(parallel), 1)
        self.assertTrue(parallel[0]["lattice_duplicate"])
        self.assertFalse(parallel[0]["ok_to_submit"])

    def test_historical_cards_carry_supersession(self):
        for path in (ROOT / "docs/evidence").glob("run_card_h*.json"):
            c = json.loads(path.read_text())
            with self.subTest(card=path.name):
                self.assertEqual(c["verdict"], "negative")
                self.assertFalse(c["ok_to_submit"])


class PublicFeedTests(unittest.TestCase):
    fixture = '''<table><tr><th>Rank</th><th>Participant</th><th>Best public DW-Tversky</th></tr>
    <tr><td>#1</td><td>example</td><td>0.4437</td></tr></table>'''

    def test_parses_only_unambiguous_public_table(self):
        self.assertEqual(feed.parse_rank_one(self.fixture), .4437)
        for bad in ('<table><tr><td>#1</td><td>0.9</td></tr></table>',
                    self.fixture.replace('0.4437', 'not a number'),
                    self.fixture.replace('0.4437', '1.12')):
            with self.assertRaises(ValueError):
                feed.parse_rank_one(bad)

    def test_successful_fetch_updates_snapshot(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'feed.json'
            p.write_text(json.dumps({'rank_one_public_dti': .1, 'observed_utc': '2026-01-01'}))
            class Response:
                status = 200

                def geturl(self):
                    return 'https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/'

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def read(self, n):
                    return PublicFeedTests.fixture.encode()

            with mock.patch.object(feed, 'urlopen', return_value=Response()):
                result = feed.refresh(p)
            self.assertEqual(result['status'], 'refreshed')
            self.assertEqual(result['rank_one_public_dti'], .4437)
            self.assertNotEqual(result['observed_utc'], '2026-01-01')

    def test_failed_fetch_keeps_dated_value_and_labels_stale(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'feed.json'
            p.write_text(json.dumps({'rank_one_public_dti': .4437, 'observed_utc': '2026-10-26'}))
            with mock.patch.object(feed, 'urlopen', side_effect=OSError('offline')):
                result = feed.refresh(p)
            self.assertEqual(result['status'], 'stale_snapshot')
            self.assertEqual(result['rank_one_public_dti'], .4437)
            self.assertEqual(result['observed_utc'], '2026-10-26')
            self.assertIsNotNone(result['last_refresh_attempt_utc'])


if __name__ == '__main__':
    unittest.main()

class SubmissionGuideRegressionTests(unittest.TestCase):
    def test_guide_does_not_infer_portal_acceptance_or_root_cause(self):
        html = (ROOT / "docs/how-to-submit.html").read_text(encoding="utf-8")
        self.assertIn("File to submit: <strong>NONE</strong>", html)
        self.assertIn("exact cause is <strong>unknown</strong>", html)
        self.assertIn("do not submit any historical research tiff", html.lower())
        self.assertNotIn("Always Upload the", html)
        self.assertNotIn("reveals why GeoTIFFs", html)
