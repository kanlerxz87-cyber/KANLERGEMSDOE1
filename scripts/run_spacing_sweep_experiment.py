#!/usr/bin/env python3
"""Experiment X1 (2026-10-31): Poisson-spacing sweep of the GEMSDOE32 champion rule.

Hypothesis (H-X1): the champion's emitted-dot spacing (raster-order thinning at 2.828 px on the
H19-5 support, then the B=2 collar) is not at the holdout optimum; a different spacing moves
the official-metric surrogate (HOLDOUT-DTI) without changing the rest of the rule. The arm that
wins is also tested for uniqueness against all 23 restored references.

Shared code only (no private fork):
  - gems32.emitter.dot_thin      raster-order Euclidean spacing thinning (the incumbent's rule)
  - gems32.holdout               hide-and-recover context, pooled exact DTI, cluster bootstrap CI
  - scripts/evaluate_holdout.py  evaluate_path(.npz) -> HOLDOUT-DTI + off-catalogue SGMC-CAL
  - scripts/submission_writer.py NOT run here; candidate files are written only if a arm passes gates

Leakage canary (protocol item 4): a random-placement null with the same dot count, evaluated
through the identical per-cell path, must score near zero. Failure means the harness leaks.

Outputs: docs/evidence/exp_x1_spacing_sweep_20261031.json (small, committed).
Large per-cell caches go to the gitignored work directory (.cache/gems_work), not Git.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gems32 import holdout  # noqa: E402
from gems32.emitter import dot_thin  # noqa: E402
from gems32.paths import data_dir, work_dir  # noqa: E402
from evaluate_holdout import evaluate_path  # noqa: E402

SUPPORT_TIF = "data/scored/gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif"
CONTROL_TIF = "data/scored/gems24-h25-1-dotted-h19-5-d2-8-20261002-e56ea318af89-nan.tif"  # owner d2.8 file (GEMSDOE25/30)
OWNER_D15_TIF = "data/scored/gems24-h25-1-dotted-h19-5-d1-5-20261002-989f59505db1-nan.tif"  # owner d1.5 file (GEMSDOE24)
CHAMPION_TIF = "docs/downloads/gemsdoe32-h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros.tif"
SPACINGS = [2.828, 3.0, 3.2, 3.6, 4.0]
COLLAR_PX = 2.0
SEED = 20261031


def within3(a: np.ndarray, b: np.ndarray) -> float:
    """Fraction of dots in `a` within 3 px (Euclidean) of any dot in `b`."""
    if a.sum() == 0:
        return 0.0
    if b.sum() == 0:
        return 0.0
    d = distance_transform_edt(~b)
    return float((d[a] <= 3.0).mean())


def main() -> int:
    t0 = time.time()
    ddir = data_dir()
    wdir = work_dir() / "x1_spacing_sweep"
    wdir.mkdir(parents=True, exist_ok=True)
    out_json = ROOT / "docs" / "evidence" / "exp_x1_spacing_sweep_20261031.json"

    ctx = holdout.load_holdout_context(ddir)
    foot = ctx.foot

    with rasterio.open(ROOT / "data" / "labels.tif") as ds:
        labels = (ds.read(1) == 1) & foot
    with rasterio.open(ddir / "sample_submission.tif") as ds:
        tmpl_foot = np.isfinite(ds.read(1))
    assert (tmpl_foot == foot).all(), "holdout footprint must equal the template footprint"

    with rasterio.open(ROOT / SUPPORT_TIF) as ds:
        raw = ds.read(1)
    support = np.isfinite(raw) & (raw > 0) & foot
    with rasterio.open(ROOT / CONTROL_TIF) as ds:
        owner_d28 = (ds.read(1) == 1) & foot
    with rasterio.open(ROOT / CHAMPION_TIF) as ds:
        champ_full = (ds.read(1) == 1) & foot
    catalogue_gate = distance_transform_edt(~labels) > COLLAR_PX

    # ---- Control A: re-derive the owner's d2.8 layout from the support with the shared rule ----
    ctrl_mask, _ = dot_thin(support, 2.828)
    ctrl_mask &= foot
    control_check = {
        "support_px": int(support.sum()),
        "owner_d28_px": int(owner_d28.sum()),
        "reimpl_d2828_px": int(ctrl_mask.sum()),
        "exact_match_with_owner_d28": bool((ctrl_mask == owner_d28).all()),
        "overlap_within3px_reimpl_vs_owner": within3(ctrl_mask, owner_d28),
        "note": "reimplementation is a faithful control, not a byte copy (see emitter.dot_thin docstring)",
    }

    rng = np.random.default_rng(SEED)
    arms = []

    def run_arm(name: str, full_thinned: np.ndarray, role: str, n_target: int | None = None) -> dict:
        # Fold-local champion rule: thinned dots & visible-only collar (d_vis > 2) & active (visible masked).
        cells = {c.key: (full_thinned[c.bbox] & (c.d_vis_sub > COLLAR_PX) & c.active_sub) for c in ctx.cells}
        npz = wdir / f"{name}_cells.npz"
        np.savez_compressed(npz, **cells)
        full_sub = full_thinned & catalogue_gate  # file-level catalogue gate, as submitted
        # evaluate_path(.npz, sgmc_map=...) reads a binary full-map raster for the off-catalogue SGMC score.
        tif = wdir / f"{name}_full.tif"
        with rasterio.open(ROOT / "data" / "sample_submission.tif") as tmpl:
            prof = tmpl.profile.copy()
        prof.update(dtype="uint8", count=1, nodata=0)
        with rasterio.open(tif, "w", **prof) as dst:
            dst.write(full_sub.astype(np.uint8), 1)
        rep = evaluate_path(npz, b_visible_px=0.0, ddir=ddir, name=name, sgmc_map=tif)
        hr = rep["hide_and_recover"]
        sg = rep["sgmc_off_catalogue"]
        return {
            "arm": name,
            "role": role,
            "dots_full_map_after_catalogue_gate": int(full_sub.sum()),
            "dots_cell_sum_visible_gated": int(sum(int(v.sum()) for v in cells.values())),
            "holdout_hide_recover": {
                "evaluator_version": "GEMSDOE32-HIDE-RECOVER-v3.1",
                "label": "HOLDOUT-DTI",
                "pooled_dti": hr.get("pooled_dti"),
                "ci95": hr.get("ci95_cluster_bootstrap"),
                "n_withheld_positives": hr.get("n_truth", hr.get("n_withheld_positives")),
            },
            "sgmc_off_catalogue": {
                "label": "HOLDOUT-DTI (off-catalogue SGMC-CAL)",
                "evaluator_version": "GEMSDOE32-SGMC-CAL-v3.0",
                "prevalence_calibrated_dti": sg.get("sgmc_prevalence_calibrated_dti"),
                "raw_pooled_dti": sg.get("sgmc_raw_pooled_dti"),
            },
            "within3px_vs_champion_full_map": within3(full_sub, champ_full),
            "within3px_vs_owner_d28_full_map": within3(full_sub, owner_d28),
            "cells_npz": str(npz),
        }

    # Arm A: the owner's exact d2.8 layout through the same harness (reconciles the recorded champion number)
    arms.append(run_arm("owner_d28_exact", owner_d28, "control-exact"))
    # Arm B: the owner's exact d1.5 layout (GEMSDOE24) through the same harness (direction test vs organizer)
    with rasterio.open(ROOT / OWNER_D15_TIF) as ds:
        owner_d15 = (ds.read(1) == 1) & foot
    arms.append(run_arm("owner_d15_exact", owner_d15, "owner-denser"))
    # Arm C: reimplementation of the 2.828 rule (differs from owner by 181 px; kept for transparency)
    arms.append(run_arm("ctrl_d2828_reimpl", ctrl_mask, "control-reimpl"))

    for d in SPACINGS[1:]:  # integer-squared-offset thinning: 3.2 and 3.6 select the same offsets
        m, _ = dot_thin(support, d)
        m &= foot
        arms.append(run_arm(f"d{str(d).replace('.', 'p')}", m, "treatment"))

    # Canary: random placement with the same count as the control, same pipeline
    n_ctrl = int(ctrl_mask.sum())
    idx = np.flatnonzero(foot.ravel())
    pick = rng.choice(idx, size=n_ctrl, replace=False)
    rnd = np.zeros(foot.size, bool)
    rnd[pick] = True
    rnd = rnd.reshape(foot.shape)
    canary = run_arm("canary_random_same_count", rnd, "null-canary")

    res = {
        "schema": "exp-x1-spacing-sweep/v1",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hypothesis": "H-X1: holdout DTI of the champion rule depends on Poisson spacing; sparse/dense arms change the score.",
        "budget_note": "one hypothesis, five arms incl. control and null canary; arms are a sweep (selection risk on the holdout)",
        "inputs": {
            "support": SUPPORT_TIF,
            "control_owner_d28": CONTROL_TIF,
            "champion_full_map": CHAMPION_TIF,
            "labels": "data/labels.tif",
            "template": "data/sample_submission.tif",
            "collar_px": COLLAR_PX,
        },
        "control_check": control_check,
        "arms": arms,
        "canary": canary,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(res, indent=2, default=float) + "\n")
    for a in arms + [canary]:
        h = a["holdout_hide_recover"]
        print(f"{a['arm']:28s} dots={a['dots_full_map_after_catalogue_gate']:7,d} "
              f"HOLDOUT-DTI={h['pooled_dti']} CI={h['ci95']} SGMC-CAL={a['sgmc_off_catalogue']['prevalence_calibrated_dti']}")
    print("wrote", out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
