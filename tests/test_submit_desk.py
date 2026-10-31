"""Gates for the one-file download desk (2026-10-29).

Evidence-level tests run on committed JSON and always execute. Raster-level tests need the
restored competition data (`data/sample_submission.tif`) and skip cleanly in CI without it.
"""
import hashlib
import json
import re
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

STEM = "gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan"
TIF = ROOT / "docs" / "downloads" / f"{STEM}.tif"
ZIP = ROOT / "docs" / "downloads" / f"{STEM}.zip"
TEMPLATE = ROOT / "data" / "sample_submission.tif"


def load(rel):
    return json.loads((ROOT / rel).read_text())


class EvidenceTests(unittest.TestCase):
    def test_recommended_file_and_zip_exist_and_hash_to_validator_record(self):
        val = load(f"evidence/validation_{STEM}.json")
        self.assertTrue(val["all_passed"])
        self.assertEqual(hashlib.sha256(TIF.read_bytes()).hexdigest(), val["tif"]["sha256"])
        with zipfile.ZipFile(ZIP) as zf:
            self.assertEqual(zf.namelist(), [f"{STEM}.tif"])
            self.assertEqual(hashlib.sha256(zf.read(f"{STEM}.tif")).hexdigest(), val["tif"]["sha256"])

    def test_uniqueness_is_detector_only_pass_with_literal_failure_disclosed(self):
        audit = load("evidence/uniqueness_audit_20261029.json")
        self.assertGreaterEqual(audit["reference_count"], 20)
        row = next(v for v in audit["candidates"].values() if v["file"].endswith(f"{STEM}.tif"))
        self.assertTrue(row["detector_only_rule_passed"])
        self.assertLess(row["worst_non_space_filling_within_3px"], 0.70)
        self.assertLess(row["worst_abs_spearman"], 0.90)
        # Disclosed, not hidden: the literal rule fails because of the saturating lattice.
        self.assertFalse(row["literal_rule_passed"])
        self.assertTrue(any("r13" in r for r in row["literal_failing_references"]))

    def test_projection_rows_are_labelled_and_never_called_scores(self):
        sb = load("evidence/candidate_scoreboard_20261029.json")
        for r in sb["rows"]:
            with self.subTest(candidate=r["candidate"]):
                self.assertIn("PROJECTION", r["organizer_projection"]["label"])
                self.assertIn("NOT a score", r["organizer_projection"]["label"])
                self.assertIn("HOLDOUT-DTI", r["sgmc_cal_holdout_dti"]["label"])
        card = load("evidence/run_card_20261029_submit.json")
        self.assertIsNone(card["organizer_estimate"]["value"])
        self.assertEqual(card["organizer_estimate"]["status"], "UNKNOWN")
        self.assertFalse(card["ok_to_download_and_submit"])
        self.assertIn("RESEARCH HOLD", card["verdict"])
        self.assertFalse(card["uploaded_by_agent"])
        self.assertLessEqual(card["submission_note_characters"], 140)

    def test_published_evidence_copies_match_canonical_files(self):
        for name in ("validation_" + STEM + ".json", "uniqueness_audit_20261029.json",
                     "candidate_scoreboard_20261029.json", "proxy_vs_organizer_calibration.json",
                     "leaderboard_snapshot_20261029.json", "run_card_20261029_submit.json"):
            with self.subTest(name=name):
                self.assertEqual((ROOT / "docs" / "evidence" / name).read_bytes(),
                                 (ROOT / "evidence" / name).read_bytes())

    def test_submit_page_is_generated_and_up_to_date(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_submit_page.py"), "--check"],
                             capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_portal_note_is_within_limit(self):
        html = (ROOT / "docs" / "submit-now.html").read_text()
        m = re.search(r"<tr><th>Note</th><td><code>([^<]+)</code>", html)
        self.assertIsNotNone(m)
        self.assertLessEqual(len(m.group(1)), 140)


class RasterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TEMPLATE.exists():
            raise unittest.SkipTest("competition data not restored (run scripts/download_competition_data.sh)")

    def test_recommended_tif_passes_independent_official_validator(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_submission_file.py"), str(TIF)],
                             capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn('"all_passed": true', out.stdout)

    def test_zeros_outside_diagnostic_is_rejected_by_official_outside_rule(self):
        zeros = ROOT / "docs" / "downloads" / f"{STEM.replace('-nan', '-zeros')}.tif"
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_submission_file.py"), str(zeros)],
                             capture_output=True, text=True, cwd=ROOT)
        self.assertNotEqual(out.returncode, 0)


if __name__ == "__main__":
    unittest.main()
