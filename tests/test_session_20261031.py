"""Consistency checks for the 2026-10-31 executive-summary evidence (no heavy compute).

These tests read the committed evidence and pin the numbers that the executive summary quotes,
so a later edit to one file cannot silently disagree with another.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "docs" / "evidence"
CANDIDATE_SHA = "2693c2daf87bd7948d3d57fc41fdcf40653ef42014c93d0e947bc2a8fc00a30c"


class SessionEvidenceTests(unittest.TestCase):
    def test_x1_reproduces_recorded_champion_exactly(self):
        x1 = json.loads((EV / "exp_x1_spacing_sweep_20261031.json").read_text())
        arms = {a["arm"]: a for a in x1["arms"]}
        hr = arms["owner_d28_exact"]["holdout_hide_recover"]
        self.assertEqual(round(hr["pooled_dti"], 6), 0.099202)
        self.assertEqual(round(hr["ci95"][0], 6), 0.085951)
        self.assertEqual(round(hr["ci95"][1], 6), 0.112668)
        self.assertEqual(arms["owner_d28_exact"]["dots_full_map_after_catalogue_gate"], 37654)
        self.assertEqual(round(arms["owner_d28_exact"]["sgmc_off_catalogue"]["prevalence_calibrated_dti"], 6), 0.064121)

    def test_x1_treatments_are_duplicates_of_champion_lineage(self):
        x1 = json.loads((EV / "exp_x1_spacing_sweep_20261031.json").read_text())
        for a in x1["arms"]:
            if a["role"] == "treatment":
                self.assertGreater(a["within3px_vs_champion_full_map"], 0.70, a["arm"])

    def test_x1_canary_is_recorded_not_assumed_near_zero(self):
        x1 = json.loads((EV / "exp_x1_spacing_sweep_20261031.json").read_text())
        canary = x1["canary"]["holdout_hide_recover"]["pooled_dti"]
        champ = next(a for a in x1["arms"] if a["arm"] == "owner_d28_exact")["holdout_hide_recover"]["pooled_dti"]
        self.assertLess(canary, champ)
        self.assertGreater(canary, 0.02, "canary expectation was wrong; the surrogate baseline is about 0.047")

    def test_run_card_is_negative_and_not_submittable(self):
        card = json.loads((EV / "run_card_x1_spacing_20261031.json").read_text())
        self.assertEqual(card["verdict"], "negative")
        self.assertFalse(card["ok_to_submit"])
        self.assertFalse(card["slot_used"])
        self.assertIsNone(card["submission_name"])
        self.assertLessEqual(card["max_experiments_budget"], 3)
        self.assertLessEqual(card["experiments_used"], card["max_experiments_budget"])

    def test_focus_table_covers_nine_sites_and_candidate_is_unique_to_all(self):
        table = json.loads((EV / "focus_site_table_20261031.json").read_text())
        self.assertEqual(len(table["rows"]), 9)
        self.assertEqual(table["candidate_sha256"], CANDIDATE_SHA)
        for r in table["rows"]:
            self.assertFalse(r["duplicate_under_literal_70pct_rule"], r["site"])
            self.assertLess(r["within3px_candidate_dots_vs_site"], 0.70, r["site"])
            self.assertEqual(len(r["sha256_pinned_and_verified"]), 64)

    def test_projection_is_labelled_and_brackets_its_point(self):
        proj = json.loads((EV / "organizer_projection_20261031.json").read_text())
        self.assertEqual(proj["label"], "PROJECTION - NOT A SCORE")
        c = proj["candidate_UWBP_projection"]
        self.assertLessEqual(c["pi95_low"], c["projected_organizer"])
        self.assertLessEqual(c["projected_organizer"], c["pi95_high"])
        self.assertFalse(proj["duplicate_check_GEMSDOE25_vs_GEMSDOE30"]["byte_identical"])

    def test_irregularity_log_is_complete(self):
        log = json.loads((EV / "irregularity_log_20261031.json").read_text())
        ids = [i["id"] for i in log["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        for item in log["items"]:
            self.assertTrue(item["evidence"], item["id"])
            self.assertTrue(item["status"], item["id"])
            self.assertIn(item["severity"], {"HIGH", "MEDIUM", "LOW"})

    def test_executive_summary_quotes_candidate_hash_and_label(self):
        html = (ROOT / "docs" / "executive-summary-20261031.html").read_text()
        self.assertIn(CANDIDATE_SHA, html)
        self.assertIn("PROJECTION", html)
        self.assertIn("NOT WITHOUT SELECTOR SIGN-OFF", html)
        self.assertIn("gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif", html)

    def test_candidate_file_hash_matches_claim(self):
        import hashlib
        p = ROOT / "docs" / "downloads" / "gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif"
        if not p.exists():
            self.skipTest("candidate file not present in this checkout")
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), CANDIDATE_SHA)


if __name__ == "__main__":
    unittest.main()
