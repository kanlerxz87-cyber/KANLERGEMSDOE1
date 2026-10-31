#!/usr/bin/env python3
"""Build a NaN-outside submission GeoTIFF with the fold-local HGB lane's exact emission rule.

Same procedure as scripts/run_fold_hgb_lane.py, but trained on the FULL visible catalogue
(all labels) instead of a hide-and-recover fold, so there is no holdout truth to leak.
Writes through the shared writer (gems32.submission via scripts/submission_writer.py), which
enforces EPSG:32611, 3730x3292, the template transform, [0,1] values and NaN-outside.

Usage: python scripts/build_hgb_submission.py --nms 3 --slug <slug> --note "<=140 chars>"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from gems32.paths import data_dir  # noqa: E402
import run_fold_hgb_lane as lane  # noqa: E402
import submission_writer  # noqa: E402
import rasterio  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nms", type=int, required=True)
    ap.add_argument("--b", type=float, default=2.0)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--candidate-id", required=True)
    ap.add_argument("--note", required=True)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "docs" / "downloads")
    ap.add_argument("--holdout-label", default="HOLDOUT-DTI: not measured for this run",
                    help="labelled holdout estimate copied from the matching evidence/fold_hgb_*.json")
    args = ap.parse_args()
    if len(args.note) > 140:
        raise SystemExit("note exceeds 140 characters")
    ddir = data_dir()
    with rasterio.open(ddir / "sample_submission.tif") as ds:
        foot = np.isfinite(ds.read(1))
    with rasterio.open(ddir / "labels.tif") as ds:
        labels = (ds.read(1) == 1) & foot
    X, _ = lane.load_features(ddir, foot)
    rng = np.random.default_rng(lane.SEED)
    d_lab = distance_transform_edt(~labels).astype(np.float32)
    # Model trained on all catalogue faults vs negatives > 3 px from any catalogue fault.
    pos_v = lane.footprint_vec(labels, foot)
    neg_v = lane.footprint_vec(foot & (d_lab > 3.0), foot)
    pi = np.flatnonzero(pos_v)
    ni = np.flatnonzero(neg_v)
    ni = rng.choice(ni, min(ni.size, lane.NEG_SAMPLE), replace=False)
    from sklearn.ensemble import HistGradientBoostingClassifier
    clf = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08, max_leaf_nodes=31,
                                         l2_regularization=1.0, random_state=lane.SEED)
    clf.fit(X[np.concatenate([pi, ni])], np.r_[np.ones(pi.size), np.zeros(ni.size)])
    cand = foot & (d_lab > args.b)
    cand_v = lane.footprint_vec(cand, foot)
    ci = np.flatnonzero(cand_v)
    p_v = np.zeros(int(foot.sum()), np.float32)
    p_v[ci] = clf.predict_proba(X[ci])[:, 1].astype(np.float32)
    p_full = lane.to_full(p_v, foot)
    budget_n = int(round(lane.BUDGET_FRAC * int(cand.sum())))
    dots = lane.select_dots(p_full, cand, budget_n, args.nms)
    arr = dots.astype(np.float32)  # binary 0/1 emission; zero off-dot inside footprint
    meta = {
        "candidate_id": args.candidate_id,
        "filename_prefix": "kanlergemsdoe1",
        "description": (f"HGB fold-local emission rule (full-catalogue fit), nms={args.nms}px, "
                        f"B={args.b}px gate, budget={budget_n} dots. "
                        f"{args.holdout_label}"),
        "submission_note_zeros": args.note,
        "submission_note_nan": args.note,
        "emitted_dots": int(dots.sum()),
        "budget_n": budget_n,
    }
    bundle = submission_writer.write_validated_submission(
        arr, slug=args.slug, candidate_meta=meta, ddir=ddir, out_dir=args.out_dir)
    print(json.dumps(bundle, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
