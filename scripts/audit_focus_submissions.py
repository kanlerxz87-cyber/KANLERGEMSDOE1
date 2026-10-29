#!/usr/bin/env python3
"""Audit the nine focus-site GEMSDOE TIFs (data/focus/*.tif) against the competition grid.

Per file: format checks (single band, CRS/shape/transform vs sample_submission.tif, value range,
NaN/inf inside and outside footprint), dot count, pairwise within-3-px overlap, and the
zero-SGMC proxy `HOLDOUT-DTI (GEMSDOE32-SGMC-CAL-v3.0)` via the shared evaluator (gems32.holdout).
That proxy is valid for full-map rasters because it scores off-catalogue SGMC faults only.
The hide-and-recover metric is NOT reported here: a full-map raster is not fold-local, and the
evaluator marks it promotion_evidence=False.
Writes docs/evidence/focus_submission_audit.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems32 import holdout  # noqa: E402
from gems32.paths import data_dir  # noqa: E402

SITES = ["GEMSDOE24", "GEMSDOE25", "GEMSDOE27", "GEMSDOE28", "GEMSDOE30",
         "GEMSDOE31", "GEMSDOE32", "GEMSDOE33", "GEMSDOE36"]


def within3(a: np.ndarray, b: np.ndarray) -> float:
    if a.sum() == 0:
        return 0.0
    dist_b = distance_transform_edt(~b)
    return float((dist_b[a] <= 3.0).mean())


def main() -> int:
    ddir = data_dir()
    ctx = holdout.load_holdout_context(ddir)
    with rasterio.open(ddir / "sample_submission.tif") as t:
        tmpl = (t.crs, t.shape, t.transform)
    foot = ctx.foot
    rows, dots = [], {}
    receipt = json.loads((ROOT / "registry" / "focus_sites.json").read_text())["files"]
    reported = {e["site"]: e["reported_score"] for e in receipt}
    for site in SITES:
        p = ROOT / "data" / "focus" / f"{site}.tif"
        with rasterio.open(p) as ds:
            arr = ds.read(1).astype(np.float64)
            fmt = {
                "count": ds.count, "dtype": ds.dtypes[0], "nodata": ds.nodata,
                "crs_match": ds.crs == tmpl[0], "shape_match": ds.shape == tmpl[1],
                "transform_match": ds.transform == tmpl[2],
            }
        inside = arr[foot]
        outside = arr[~foot]
        fmt["nan_inside"] = int(np.isnan(inside).sum())
        fmt["inf_inside"] = int(np.isinf(inside).sum())
        fmt["nonnull_outside"] = int(np.isfinite(outside).sum())
        fmt["min_inside"] = float(np.nanmin(inside))
        fmt["max_inside"] = float(np.nanmax(inside))
        fmt["in_range_01_inside"] = bool(np.all((inside >= 0) & (inside <= 1)))
        fmt["unique_values_inside"] = int(np.unique(inside[np.isfinite(inside)]).size)
        m = np.zeros(foot.shape, bool)
        m[foot] = np.nan_to_num(inside, nan=0.0) > 0
        dots[site] = m
        sg = holdout.evaluate_sgmc_with_ci(m, ctx, name=site)
        rows.append({
            "site": site, "reported_score": reported[site], "score_evidence": "USER/OWNER-REPORT (no organizer receipt)",
            "file": f"data/focus/{site}.tif", "format": fmt, "emitted_dots": int(m.sum()),
            "zero_sgmc_proxy": {
                "label": "HOLDOUT-DTI", "evaluator_version": sg["evaluator_version"],
                "n_withheld_positives": sg["n_withheld_positives"],
                "calibrated_dti": sg["sgmc_prevalence_calibrated_dti"],
                "calibrated_ci95": sg["sgmc_calibrated_ci95"],
                "raw_dti": sg["sgmc_raw_pooled_dti"],
            },
        })
    overlap = {}
    for a in SITES:
        overlap[a] = {b: round(within3(dots[a], dots[b]), 4) for b in SITES if b != a}
    out = {"sites": rows, "pairwise_within3px_overlap_of_row_dots_on_column_dots": overlap,
           "grid": {"crs": str(tmpl[0]), "shape": list(tmpl[1])}}
    dst = ROOT / "docs" / "evidence" / "focus_submission_audit.json"
    dst.write_text(json.dumps(out, indent=2) + "\n")
    for r in rows:
        print(f"{r['site']:9s} rep={r['reported_score']:.4f} dots={r['emitted_dots']:6d} "
              f"range_ok={r['format']['in_range_01_inside']} nan_in={r['format']['nan_inside']} "
              f"nonnull_out={r['format']['nonnull_outside']} crs/shape/tf={r['format']['crs_match']}/"
              f"{r['format']['shape_match']}/{r['format']['transform_match']} "
              f"zSGMC={r['zero_sgmc_proxy']['calibrated_dti']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
