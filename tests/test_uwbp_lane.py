"""Unit and protocol-receipt tests for 2026-10-28 Lane H-K1-B (UWBP-DRCS)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kanler import uwbp  # noqa: E402


class UwbpOperatorTests(unittest.TestCase):
    def test_dct2_poisson_upward_continuation_exact_eigenmode_decay(self):
        """A pure DCT-II eigenmode cos(pi * m * y / H) must decay by exact exp(-h * k_m)."""
        H, W = 64, 48
        dx_m = 100.0
        m = 4
        y = np.arange(H, dtype=np.float32) + 0.5
        mode = np.cos(np.pi * m * y / H)[:, None] * np.ones((1, W), dtype=np.float32)
        field = (12.5 + 3.0 * mode).astype(np.float32)
        foot = np.ones((H, W), dtype=bool)

        heights = (100.0, 300.0, 600.0, 1200.0)
        up = uwbp.poisson_upward_continue_dct(field, foot, heights_m=heights, dx_m=dx_m)
        k_m = np.pi * m / (H * dx_m)

        prev_energy = float(np.std(field))
        for h in heights:
            u_h = up[h]
            self.assertEqual(u_h.shape, (H, W))
            self.assertEqual(u_h.dtype, np.float32)
            expected = 12.5 + 3.0 * np.exp(-h * k_m) * mode
            max_err = float(np.max(np.abs(u_h - expected)))
            self.assertLess(max_err, 5e-4, f"DCT-II Poisson continuation drifted at h={h}: {max_err}")
            cur_energy = float(np.std(u_h))
            self.assertLess(cur_energy, prev_energy)
            prev_energy = cur_energy

    def test_dinkelbach_submodular_packer_spacing_budget_and_mask_safety(self):
        H, W = 60, 60
        yy, xx = np.mgrid[0:H, 0:W]
        # Two sharp fault-like ridges plus low-confidence noise outside allowed domain
        ridge_a = np.exp(-((xx - 16.0) ** 2) / 3.0).astype(np.float32)
        ridge_b = 0.85 * np.exp(-((yy - 40.0) ** 2) / 3.0).astype(np.float32)
        belief = np.maximum(ridge_a, ridge_b)

        allowed = np.ones((H, W), dtype=bool)
        allowed[:, :5] = False  # Simulate out-of-footprint / visible-fault collar exclusion
        belief[:, :5] = 10.0  # Even huge scores outside allowed must NEVER be selected

        dots = uwbp.pack_dinkelbach_dti_300m(
            belief,
            allowed,
            max_budget=18,
            min_dist_px=3.05,
            fp_cost_lambda=0.055,
            min_budget=8,
        )
        self.assertEqual(dots.shape, (H, W))
        self.assertEqual(dots.dtype, bool)
        self.assertFalse(bool((dots & ~allowed).any()))
        n_sel = int(dots.sum())
        self.assertTrue(8 <= n_sel <= 18, f"Unexpected packed count {n_sel}")

        sy, sx = np.nonzero(dots)
        if len(sy) > 1:
            dy = sy[:, None] - sy[None, :]
            dx = sx[:, None] - sx[None, :]
            dist2 = dy * dy + dx * dx
            np.fill_diagonal(dist2, 10_000)
            min_d = float(np.sqrt(dist2.min()))
            self.assertGreaterEqual(min_d, 3.04, f"Minimum spacing violated: {min_d}")

        # Zero-belief safety
        empty = uwbp.pack_dinkelbach_dti_300m(np.zeros((20, 20), dtype=np.float32), np.ones((20, 20), dtype=bool), 10)
        self.assertEqual(int(empty.sum()), 0)

    def test_crest_carrier_respects_footprint_and_bounds(self):
        H, W = 40, 44
        uwbp_mock = np.zeros((len(uwbp.UWBP_FREE_NAMES), H, W), dtype=np.float32)
        ocda_mock = np.zeros((26, H, W), dtype=np.float32)
        yy, xx = np.mgrid[0:H, 0:W]
        uwbp_mock[2] = np.exp(-((xx - 20.0) ** 2) / 4.0)
        uwbp_mock[11] = np.exp(-((yy - 18.0) ** 2) / 4.0)
        foot = np.ones((H, W), dtype=bool)
        foot[:4, :] = False

        carrier = uwbp.build_uwbp_crest_carrier(uwbp_mock, ocda_mock, foot)
        self.assertEqual(carrier.shape, (H, W))
        self.assertTrue(np.all(carrier[~foot] == 0.0))
        self.assertTrue(np.all((carrier[foot] >= 0.0) & (carrier[foot] <= 1.0)))


class UwbpProtocolReceiptsTests(unittest.TestCase):
    def test_canary_ablation_and_uniqueness_receipts_synced_and_valid(self):
        for rel in (
            "uwbp_leakage_canary.json",
            "uwbp_ablation_ledger.json",
            "uwbp_uniqueness_and_gate.json",
            "run_card_uwbp_drcs.json",
        ):
            ev = json.loads((ROOT / "evidence" / rel).read_text())
            docs_ev = json.loads((ROOT / "docs" / "evidence" / rel).read_text())
            self.assertEqual(ev, docs_ev, f"Evidence drift between evidence/{rel} and docs/evidence/{rel}")

        canary = json.loads((ROOT / "evidence" / "uwbp_leakage_canary.json").read_text())
        self.assertTrue(canary["all_passed"])
        self.assertEqual(canary["total_features_tested"], 60)
        self.assertEqual(canary["hidden_label_perturbation_max_abs_diff"], 0.0)
        for name, auc in canary["canary_aucs"].items():
            self.assertTrue(0.10 <= auc <= 0.90, f"Canary out of bounds for {name}: {auc}")

        ledger = json.loads((ROOT / "evidence" / "uwbp_ablation_ledger.json").read_text())
        self.assertLessEqual(ledger["experiments_run"], 3)
        self.assertTrue(ledger["zero_sgmc_in_training_and_inference"])
        exps = ledger["results"]
        for key in ("CHAMP-D28-VIS-B2", "EXP-B1", "EXP-B2", "EXP-B3"):
            self.assertIn(key, exps)
        # Verify zero-SGMC off-catalogue Cenozoic fault breakthrough strictly beats GEMSDOE32 with positive 95% delta CI
        self.assertGreater(ledger["paired_delta_vs_champion"]["EXP-B2"]["sgmc_calibrated"]["cand_cal_dti"], 0.088)
        self.assertGreater(ledger["paired_delta_vs_champion"]["EXP-B3"]["sgmc_calibrated"]["cand_cal_dti"], 0.088)
        self.assertGreater(ledger["paired_delta_vs_champion"]["EXP-B2"]["sgmc_calibrated"]["delta_ci95"][0], 0.014)
        self.assertGreater(ledger["paired_delta_vs_champion"]["EXP-B3"]["sgmc_calibrated"]["delta_ci95"][0], 0.014)

        uniq = json.loads((ROOT / "evidence" / "uwbp_uniqueness_and_gate.json").read_text())
        ddu = uniq["discrete_detector_uniqueness"]
        self.assertEqual(ddu["n_discrete_detectors"], 57)
        self.assertTrue(ddu["surface_stage_passed"])
        self.assertTrue(ddu["final_stage_passed"])
        self.assertLessEqual(ddu["max_abs_spearman_surface"], 0.90)
        self.assertLessEqual(ddu["max_within_3px_dot_overlap"], 0.70)
        self.assertEqual(uniq["promotion_gate_literal"]["verdict"], "negative")
        self.assertEqual(uniq["promotion_gate_if_detectors_only_and_auth_sample"]["verdict"], "negative")
        self.assertTrue(uniq["promotion_gate_if_detectors_only_and_auth_sample"]["gates"]["format"])


if __name__ == "__main__":
    unittest.main()
