"""Submission desk consistency: the verdict must follow from the gates, and the page must match the verdict.

Reads only committed evidence JSON and the generated page; no raster work.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
EV = ROOT / "docs" / "evidence"


def _load(name):
    return json.loads((EV / name).read_text(encoding="utf-8"))


class SubmitDeskTests(unittest.TestCase):
    def setUp(self):
        self.v = _load("submit_verdict.json")
        self.g = self.v["gates"]

    def test_download_requires_format_uniqueness_and_note(self):
        expected = self.g["G1_format"] and self.g["G2_unique_vs_all_crawled_sites"] and self.g["G5_note_le_140"]
        self.assertEqual(self.v["download_ok"], bool(expected))

    def test_submit_requires_download_plus_canary_and_hr_ci(self):
        expected = (self.v["download_ok"] and self.g["G3_leakage_canary_sgmc_lift_le_1p5"]
                    and self.g["G4_beats_current_best_hr_ci_gt_0"])
        self.assertEqual(self.v["submit_ok"], bool(expected))
        if self.v["submit_ok"]:
            self.assertTrue(self.v["download_ok"])

    def test_organizer_receipt_is_never_claimed(self):
        # The sandbox cannot reach DrivenData, so no automated run may set G6 to True.
        self.assertFalse(self.g["G6_organizer_receipt"])

    def test_note_is_within_limit(self):
        import build_submit_desk as bsd
        self.assertLessEqual(len(bsd.NOTE), 140)

    def test_holds_are_explained(self):
        if not self.g["G2_unique_vs_all_crawled_sites"]:
            self.assertTrue(any("Within-3px" in r or "Pixel-identical" in r for r in self.v["hold_reasons"]))

    def test_page_matches_verdict(self):
        html = (ROOT / "docs" / "submit.html").read_text(encoding="utf-8")
        if self.v["download_ok"]:
            self.assertIn("DOWNLOAD: YES", html)
        else:
            self.assertIn("DOWNLOAD: NO", html)
        self.assertIn("SUBMIT: " + ("YES" if self.v["submit_ok"] else "HOLD"), html)

    def test_uniqueness_reports_other_sites_separately(self):
        u = _load("uniqueness_vs_all_sites.json")
        self.assertIn("n_dense_references_within3px_skipped", u)
        for r in u["candidates"]:
            self.assertIn("other_sites_max_within3px", r)
            if not r["uniqueness_gate_pass"]:
                self.assertTrue(r["pixel_identical_to"] or r["max_within3px"] > 0.70
                                or r["max_abs_phi"] > 0.90 or r["other_sites_max_within3px"] > 0.70)

    def test_candidate_gate_requires_other_sites_check(self):
        # A candidate that is only pixel-identical to this repo's own copy must still fail G2
        # if another site's dots are within 3 px above the gate.
        u = _load("uniqueness_vs_all_sites.json")
        for r in u["candidates"]:
            if r["other_sites_max_within3px"] > 0.70:
                self.assertFalse(r["uniqueness_gate_pass"], r["candidate"])


if __name__ == "__main__":
    unittest.main()
