"""Synthetic regression tests for Lane H-K1-B (GEOALIGN-UPFLOW); no data, no slots."""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kanler import upflow


class UpflowSchemaTests(unittest.TestCase):
    def test_channel_schema(self):
        self.assertEqual(upflow.N_UPFLOW_FREE, 12)
        self.assertEqual(len(set(upflow.UPFLOW_FREE_NAMES)), 12)
        self.assertAlmostEqual(sum(upflow.EXP1_W), 1.0)
        self.assertTrue(all(w > 0 for w in upflow.EXP1_W))

    def test_idw_exact_near_data_zero_far(self):
        foot = np.ones((60, 60), bool)
        py = np.array([10, 50, 10])
        px = np.array([10, 50, 50])
        vals = np.array([4.0, 8.0, 6.0], np.float32)
        g = upflow._idw_grid(py, px, vals, (60, 60), foot, k=2, max_dist=5.0)
        self.assertAlmostEqual(float(g[10, 10]), 4.0, places=2)
        self.assertAlmostEqual(float(g[50, 50]), 8.0, places=2)
        self.assertEqual(float(g[30, 30]), 0.0)  # beyond coverage cutoff
        self.assertTrue(np.isfinite(g).all())

    def test_idw_needs_three_points(self):
        foot = np.ones((10, 10), bool)
        g = upflow._idw_grid(np.array([1]), np.array([1]),
                             np.array([1.0], np.float32), (10, 10), foot)
        self.assertEqual(float(g.sum()), 0.0)

    def test_rasterize_segments_axis_aligned(self):
        acc = upflow._rasterize_segments(
            np.array([5]), np.array([10]),
            np.array([0.0]), np.array([1.0]),
            np.array([4.0]), np.array([2.0]), (12, 24))
        self.assertEqual(float(acc[5, 10]), 2.0)
        self.assertEqual(float(acc[5, 6]), 2.0)
        self.assertEqual(float(acc[5, 14]), 2.0)
        self.assertEqual(float(acc[5, 15]), 0.0)
        self.assertEqual(float(acc[6, 10]), 0.0)
        # max-merge keeps the larger weight
        acc2 = upflow._rasterize_segments(
            np.array([5, 5]), np.array([10, 10]),
            np.array([0.0, 0.0]), np.array([1.0, 1.0]),
            np.array([4.0, 4.0]), np.array([2.0, 0.5]), (12, 24))
        self.assertEqual(float(acc2[5, 10]), 2.0)

    def test_fold_visible_uses_only_visible_mask(self):
        foot = np.ones((40, 40), bool)
        vis = np.zeros((40, 40), bool)
        vis[20, :] = True
        a = upflow.compute_fold_visible_upflow(vis, foot, None)
        b = upflow.compute_fold_visible_upflow(vis.copy(), foot, None)
        for k in a:
            np.testing.assert_array_equal(a[k], b[k])  # deterministic
        self.assertAlmostEqual(float(a["d_vis"][20, 5]), 0.0)
        self.assertAlmostEqual(float(a["d_vis"][23, 5]), 3.0, places=4)
        self.assertEqual(float(a["far_gate"][20, 5]), 0.0)
        self.assertEqual(float(a["far_gate"][21, 5]), 0.0)
        self.assertGreater(float(a["far_gate"][26, 5]), 0.9)
        # interactions vanish inside the collar
        self.assertEqual(float(a["align_far"][20, 5]), 0.0)
        self.assertGreater(float(a["align_far"][30, 5]), 0.0)
        for k in a:
            self.assertTrue(np.isfinite(a[k]).all())

    def test_release_gate_module_importable(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import audit_upflow_candidate  # noqa: F401


if __name__ == "__main__":
    unittest.main()
