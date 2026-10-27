"""Unit and regression tests for Lane H-K1-A (OCDA-MSCS), holdout CLI, and protocol artifacts."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gems32 import holdout
from kanler import ocda
import evaluate_holdout


class OcdaOperatorsTests(unittest.TestCase):
    def test_bilinear_offset_exact_on_linear_ramp_and_safe_at_borders(self):
        y, x = np.mgrid[0:20, 0:24].astype(np.float32)
        arr = 2.5 * y + 1.25 * x
        dy = np.full_like(arr, 1.4)
        dx = np.full_like(arr, -0.8)
        got = ocda.sample_bilinear_offset(arr, dy, dx, chunk_rows=7)
        # Interior points must match exact linear plane evaluation
        exp_inner = 2.5 * (y[3:15, 3:18] + 1.4) + 1.25 * (x[3:15, 3:18] - 0.8)
        np.testing.assert_allclose(got[3:15, 3:18], exp_inner, atol=1e-4)
        # Extreme offsets clamp cleanly to borders with finite output
        got_hi = ocda.sample_bilinear_offset(arr, np.full_like(arr, 999.0), np.full_like(arr, 999.0))
        self.assertTrue(np.isfinite(got_hi).all())
        self.assertAlmostEqual(float(got_hi[-1, -1]), float(arr[-1, -1]), places=3)
        with self.assertRaises(ValueError):
            ocda.sample_bilinear_offset(np.zeros((1, 5), dtype=np.float32), np.zeros((1, 5), dtype=np.float32), np.zeros((1, 5), dtype=np.float32))
        with self.assertRaises(ValueError):
            ocda.sample_bilinear_offset(arr, np.zeros((5, 5), dtype=np.float32), dx)

    def test_fold_visible_continuation_geometry_and_validation(self):
        shape = (48, 48)
        foot = np.ones(shape, dtype=bool)
        vis = np.zeros(shape, dtype=bool)
        # Vertical visible fault ending at y=20, x=24 -> forward tip cone must fire for y in [21..32], x~24
        vis[8:21, 24] = True
        tip, relay, cone = ocda.compute_fold_visible_continuation(vis, foot)
        self.assertEqual(float(tip[vis].max()), 0.0)
        self.assertEqual(float(relay[vis].max()), 0.0)
        self.assertGreater(float(tip[24, 24]), 0.45)
        self.assertTrue(bool(cone[23, 24]))
        self.assertLess(float(tip[24, 5]), 1e-5)

        # Reject NaN or nonbinary visible masks
        bad = vis.astype(np.float32)
        bad[0, 0] = np.nan
        with self.assertRaises(ValueError):
            ocda.compute_fold_visible_continuation(bad, foot)
        bad2 = vis.astype(np.float32)
        bad2[1, 1] = 0.5
        with self.assertRaises(ValueError):
            ocda.compute_fold_visible_continuation(bad2, foot)

    def test_submodular_packer_spacing_budget_and_zero_dist_safety(self):
        rng = np.random.default_rng(42)
        belief = rng.random((36, 40)).astype(np.float32)
        belief[0, 0] = np.nan
        belief[0, 1] = -5.0
        allowed = np.ones((36, 40), dtype=bool)
        allowed[:4, :] = False

        dots = ocda.pack_submodular_300m(belief, allowed, budget=18, min_dist_px=2.83)
        self.assertEqual(int(dots.sum()), 18)
        self.assertFalse((dots & ~allowed).any())
        ys, xs = np.nonzero(dots)
        for i in range(ys.size):
            for j in range(i + 1, ys.size):
                dist = float(np.hypot(ys[i] - ys[j], xs[i] - xs[j]))
                self.assertGreaterEqual(dist, 2.829)

        # min_dist_px = 0 still selects distinct pixels up to budget
        dots0 = ocda.pack_submodular_300m(belief, allowed, budget=10, min_dist_px=0.0)
        self.assertEqual(int(dots0.sum()), 10)


class EvaluateHoldoutSgmcCliTests(unittest.TestCase):
    def test_per_cell_npz_with_sgmc_map_and_outside_footprint_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "external").mkdir()
            shape = (40, 40)
            foot = np.ones(shape, dtype=bool)
            foot[:4, :] = False
            profile = dict(driver="GTiff", height=40, width=40, count=1, crs="EPSG:32611", transform=from_origin(0, 4000, 100, 100))
            with rasterio.open(root / "sample_submission.tif", "w", dtype="float32", nodata=np.nan, **profile) as ds:
                ds.write(np.where(foot, 0.0, np.nan).astype(np.float32), 1)
            lab = np.zeros(shape, dtype=np.uint8)
            lab[10:15, 10] = 1
            sg = np.zeros(shape, dtype=np.uint8)
            sg[26:31, 28] = 1
            with rasterio.open(root / "labels.tif", "w", dtype="uint8", **profile) as ds:
                ds.write(lab, 1)
            with rasterio.open(root / "external" / "derived_sgmc_faults_100m_u8.tif", "w", dtype="uint8", **profile) as ds:
                ds.write(sg, 1)

            with mock.patch.multiple(holdout, COLLAR_PX=1, DOMAIN_ERODE=1, NEAR_LABEL_PX=1):
                ctx = holdout.load_holdout_context(root, hide_frac=0.5)
                cells_npz = root / "cells.npz"
                np.savez(cells_npz, **{c.key: np.zeros_like(c.active_sub, dtype=np.uint8) for c in ctx.cells})
                sg_map = np.zeros(shape, dtype=np.float32)
                sg_map[27, 28] = 1.0
                sg_npy = root / "full_dots.npy"
                np.save(sg_npy, sg_map)

                rep = evaluate_holdout.evaluate_path(cells_npz, ddir=root, name="unit", sgmc_map=sg_npy)
                self.assertEqual(rep["mode"], "per_cell_oof_npz")
                self.assertIn("sgmc_off_catalogue", rep)
                self.assertGreater(rep["sgmc_off_catalogue"]["sgmc_raw_pooled_dti"], 0.0)

                # Nonzero outside footprint must fail closed
                bad_sg = sg_map.copy()
                bad_sg[0, 0] = 1.0
                np.save(sg_npy, bad_sg)
                with self.assertRaises(ValueError):
                    evaluate_holdout.evaluate_path(cells_npz, ddir=root, name="unit", sgmc_map=sg_npy)


class ProtocolReceiptsTests(unittest.TestCase):
    def test_ablation_canary_and_readme_prompt_contracts(self):
        ledger = json.loads((ROOT / "evidence" / "ocda_ablation_ledger.json").read_text())
        self.assertLessEqual(ledger["experiments_run"], 3)
        self.assertTrue(ledger["provenance_invariance"]["passed"])
        self.assertEqual(ledger["provenance_invariance"]["visible_x_withheld_pixel_overlap_across_8_cells"], 0)

        canaries = json.loads((ROOT / "evidence" / "ocda_leakage_canaries.json").read_text())
        self.assertTrue(canaries["passed"])
        self.assertEqual(canaries["n_flagged"], 0)
        self.assertLessEqual(canaries["max_symmetric_auc"], 0.90)
        self.assertEqual(canaries["total_features_tested"], 63)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("PARALLEL-RUN PROTOCOL", readme)
        self.assertIn("Maximize P(Win)", readme)
        self.assertIn("Own the Outcome", readme)


if __name__ == "__main__":
    unittest.main()
