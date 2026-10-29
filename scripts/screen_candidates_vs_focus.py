#!/usr/bin/env python3
"""Screen every repo-held candidate raster against the nine focus-site GEMSDOE TIFs.

For each candidate (docs/downloads/*-zeros.tif, one per lineage) computes:
  - emitted dots; format checks vs sample_submission.tif
  - within-3px overlap: fraction of CANDIDATE dots within 3 px of ANY focus site's dots (max over sites)
  - binary Spearman (phi) vs each focus raster (max |phi|)
  - ZERO-SGMC proxy: HOLDOUT-DTI GEMSDOE32-SGMC-CAL-v3.0 (valid for full-map rasters)
Uniqueness gate (repo rule, Protocol Rule 1): max within-3px <= 0.70 AND max |phi| <= 0.90.
Writes docs/evidence/candidate_screen_vs_focus.json. Does not choose a submission.
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
MAX_WITHIN3 = 0.70
MAX_PHI = 0.90


def phi(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(float).ravel()
    b = b.astype(float).ravel()
    a -= a.mean()
    b -= b.mean()
    den = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / den) if den > 0 else float("nan")


def main() -> int:
    ddir = data_dir()
    ctx = holdout.load_holdout_context(ddir)
    foot = ctx.foot
    focus = {}
    for s in SITES:
        with rasterio.open(ROOT / "data" / "focus" / f"{s}.tif") as ds:
            a = np.nan_to_num(ds.read(1).astype(np.float64), nan=0.0)
        focus[s] = (a > 0) & foot
    focus_dt = {s: distance_transform_edt(~m) for s, m in focus.items()}

    cands = sorted(p for p in (ROOT / "docs" / "downloads").glob("*zeros.tif"))
    # Keep one zeros-file per candidate stem (the NaN twin has identical dots).
    rows = []
    for p in cands:
        with rasterio.open(p) as ds:
            arr = np.nan_to_num(ds.read(1).astype(np.float64), nan=0.0)
            crs_ok = ds.crs.to_epsg() == 32611
            shape_ok = ds.shape == (3730, 3292)
        if not (crs_ok and shape_ok):
            rows.append({"file": p.name, "error": "grid mismatch"})
            continue
        m = (arr > 0) & foot
        n = int(m.sum())
        if n == 0:
            rows.append({"file": p.name, "error": "no dots"})
            continue
        within = {s: float((focus_dt[s][m] <= 3.0).mean()) for s in SITES}
        phis = {s: phi(m, focus[s]) for s in SITES}
        max_w = max(within.values())
        max_phi = max(abs(v) for v in phis.values())
        sg = holdout.evaluate_sgmc_with_ci(m, ctx, name=p.stem)
        rows.append({
            "file": f"docs/downloads/{p.name}", "dots": n,
            "max_within3px_vs_focus": round(max_w, 4),
            "argmax_focus_site": max(within, key=within.get),
            "max_abs_phi_vs_focus": round(max_phi, 4),
            "uniqueness_gate_pass": bool(max_w <= MAX_WITHIN3 and max_phi <= MAX_PHI),
            "zero_sgmc_proxy": {
                "label": "HOLDOUT-DTI", "evaluator_version": sg["evaluator_version"],
                "n_withheld_positives": sg["n_withheld_positives"],
                "calibrated_dti": round(sg["sgmc_prevalence_calibrated_dti"], 6),
                "calibrated_ci95": [round(x, 6) for x in sg["sgmc_calibrated_ci95"]],
            },
        })
        print(f"{p.name[:70]:70s} dots={n:6d} maxW3={max_w:.3f} maxphi={max_phi:.3f} "
              f"gate={rows[-1]['uniqueness_gate_pass']} zSGMC={sg['sgmc_prevalence_calibrated_dti']:.4f}")
    out = {"rules": {"max_within3px": MAX_WITHIN3, "max_abs_phi": MAX_PHI},
           "reference_set": SITES, "candidates": rows}
    (ROOT / "docs" / "evidence" / "candidate_screen_vs_focus.json").write_text(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
