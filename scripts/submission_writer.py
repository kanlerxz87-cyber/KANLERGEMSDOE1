#!/usr/bin/env python3
"""Canonical Protocol Rule 2 submission writer & automated 13-check GeoTIFF validator (`submission_writer.py`).

Delegates strictly to `gems32.submission` (zero private fork):
  - Enforces exact CRS (`EPSG:32611`), shape (`3730 x 3292`), and affine geotransform matching
    `sample_submission.tif`.
  - Rejects (never clips or binarizes) predictions outside `[0.0, 1.0]` or nonfinite input.
  - Requires zero on the catalogue; the input array uses zero outside the footprint as an internal sentinel.
  - Writes a zero-outside diagnostic TIFF and a NaN-outside candidate TIFF; the single-GeoTIFF `.zip` contains only the NaN-outside TIFF, matching the official outside-bounds requirement. Local validation does not prove portal acceptance.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems32 import submission  # noqa: E402
from gems32.paths import data_dir  # noqa: E402


def write_validated_submission(
    mask_or_probs: np.ndarray,
    slug: str,
    candidate_meta: dict,
    ddir: Path | None = None,
    out_dir: Path | None = None,
    timestamp_tag: str | None = None,
) -> dict:
    ddir = ddir or data_dir()
    out_dir = out_dir or (ROOT / "docs" / "downloads")
    sample_tif = ddir / "sample_submission.tif"
    labels_tif = ddir / "labels.tif"
    with rasterio.open(sample_tif) as ds:
        if ds.count != 1:
            raise ValueError("submission template must have one band")
        foot = np.isfinite(ds.read(1))
        sample_grid = (ds.shape, ds.crs, ds.transform)
    arr_in = np.asarray(mask_or_probs)
    if arr_in.shape != foot.shape:
        raise ValueError(f"Expected grid shape {foot.shape}, got {arr_in.shape}")
    for nk in ("submission_note_zeros", "submission_note_nan"):
        if nk in candidate_meta and len(str(candidate_meta[nk])) > 140:
            raise ValueError(f"{nk} exceeds 140 characters ({len(str(candidate_meta[nk]))} chars)")
    with rasterio.open(labels_tif) as ds:
        if ds.count != 1 or (ds.shape, ds.crs, ds.transform) != sample_grid:
            raise ValueError("label CRS/shape/transform/band count mismatch with template")
        raw_labels = ds.read(1)
        if not np.isfinite(raw_labels[foot]).all() or not np.isin(raw_labels[foot], (0, 1)).all():
            raise ValueError("label data must be finite and binary inside the footprint")
        labels = (raw_labels == 1) & foot
    ts = timestamp_tag or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    meta_full = {
        "catalogue_hidden_mean": None,
        "catalogue_hidden_per_quadrant": {},
        "sgmc_prevalence_calibrated_dti": None,
        "drift_corrected_holdout_mean": None,
        "drift_corrected_per_quadrant": {},
        "predicted_leaderboard_dti": None,
        "ei_drift_corrected": None,
        "slot_decision": "HOLD-DO-NOT-SUBMIT",
    }
    meta_full.update(candidate_meta)

    bundle = submission.write_submission_pair(
        mask=arr_in,
        foot=foot,
        labels=labels,
        template_tif=sample_tif,
        out_dir=out_dir,
        slug=slug,
        timestamp_tag=ts,
        candidate_meta=meta_full,
    )
    return bundle


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mask_npy", type=Path, help="Boolean or float .npy mask on the 3730x3292 grid")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--candidate-id", required=True)
    ap.add_argument("--note", required=True, help="Short DrivenData portal note (<= 140 chars)")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "docs" / "downloads")
    ap.add_argument("--data-dir", type=Path, default=None)
    args = ap.parse_args()

    if len(args.note) > 140:
        raise SystemExit(f"Submission note exceeds 140 characters ({len(args.note)} chars)")

    arr = np.load(args.mask_npy)
    meta = {
        "candidate_id": args.candidate_id,
        "description": f"Generated via scripts/submission_writer.py for {args.candidate_id}",
        "submission_note_zeros": args.note,
        "submission_note_nan": args.note,
    }
    bundle = write_validated_submission(
        arr, slug=args.slug, candidate_meta=meta, ddir=args.data_dir or data_dir(), out_dir=args.out_dir
    )
    print(json.dumps(bundle, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
