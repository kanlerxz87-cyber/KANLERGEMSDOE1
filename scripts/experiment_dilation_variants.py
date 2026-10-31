#!/usr/bin/env python3
"""Experiment (budget 1 of 3, 2026-10-31): does modest dot dilation help under the official beta>alpha metric?

Hypothesis: the official distance-weighted Tversky index uses alpha=0.2 (false positive) and
beta=0.8 (false negative). Under-predicting faults is therefore the costlier error. Dilating the
recommended 37,647-dot file by 1 px should raise recall (TP) faster than it adds false positives.

Mechanism: 8-connected 1-px dilation of each emitted dot adds neighbouring pixels that fall inside
the 300 m (3 px) triangular kernel of off-catalogue truth. Named non-fault mimic: dilation also
thickens digitisation halos around mapped faults, which the organizer masks, so gains may be
illusory.

Scoring: the shared evaluator (`gems32.holdout.evaluate_sgmc_with_ci`, SGMC-CAL-v3.0) on binary masks.
Uniqueness: the shared audit (`gems32.registry_audit.audit_final_dots`) against all 23 local references.
Writes evidence/experiment_dilation_20261031.json. Variants are written to data/experiments/ (gitignored).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import binary_dilation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gems32 import holdout  # noqa: E402
from gems32.registry_audit import audit_final_dots  # noqa: E402
from audit_unique_candidates import build_manifest  # noqa: E402  (shared manifest builder)

BASE = ROOT / "docs/downloads/gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif"
TEMPLATE = ROOT / "data/sample_submission.tif"
OUT_DIR = ROOT / "data/experiments"
EVIDENCE = ROOT / "evidence/experiment_dilation_20261031.json"


def load_dots(path: Path):
    with rasterio.open(path) as ds:
        arr = ds.read(1)
        profile = ds.profile
    dots = np.isfinite(arr) & (arr > 0)
    return dots, profile


def write_variant(dots: np.ndarray, profile: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(TEMPLATE) as ds:
        foot = np.isfinite(ds.read(1))
    out = np.where(foot, dots.astype(np.float32), np.nan).astype(np.float32)
    prof = dict(profile)
    prof.update(dtype="float32", count=1, nodata=np.nan, compress="deflate")
    with rasterio.open(path, "w", **prof) as ds:
        ds.write(out, 1)


def main() -> int:
    with rasterio.open(TEMPLATE) as ds:
        foot = np.isfinite(ds.read(1))
    base_dots, profile = load_dots(BASE)
    ctx = holdout.load_holdout_context(ROOT / "data")

    cross = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)
    square = np.ones((3, 3), bool)
    variants = {
        "V0_base": base_dots,
        "V1_dilate_cross1px": binary_dilation(base_dots, structure=cross) & foot,
        "V2_dilate_square1px": binary_dilation(base_dots, structure=square) & foot,
    }

    manifest = build_manifest()
    results = {}
    for name, dots in variants.items():
        path = OUT_DIR / f"{name}.tif"
        write_variant(dots, profile, path)
        sg = holdout.evaluate_sgmc_with_ci(dots & foot, ctx, name=name)
        sg = {k: v for k, v in sg.items() if not k.startswith("_")}
        with rasterio.open(path) as ds:
            arr = ds.read(1)
        surface = np.where(np.isfinite(arr), arr, 0.0).astype(np.float32)
        aud = audit_final_dots(candidate_surface=surface, candidate_dots=dots & foot, footprint=foot,
                               manifest=manifest, root=ROOT, template_tif=TEMPLATE)
        non_sf = [c for c in aud["comparisons"] if c.get("within_3px_fraction") is not None
                  and (c.get("footprint_coverage_3px") or 0.0) < 0.70]
        worst = max(non_sf, key=lambda c: c["within_3px_fraction"]) if non_sf else None
        results[name] = {
            "file": str(path.relative_to(ROOT)),
            "emitted_pixels": int((dots & foot).sum()),
            "sgmc_cal": sg,
            "uniqueness_worst_non_space_filling_within_3px": round(worst["within_3px_fraction"], 6) if worst else None,
            "uniqueness_worst_reference": worst.get("local") if worst else None,
            "uniqueness_worst_abs_spearman": round(max(abs(c.get("spearman") or 0.0) for c in aud["comparisons"]), 6),
            "uniqueness_detector_only_passed": bool(worst is None or worst["within_3px_fraction"] <= 0.70),
        }
        r = results[name]
        print(f"{name:22s} emitted={r['emitted_pixels']:6d} SGMC-CAL={sg['sgmc_prevalence_calibrated_dti']:.6f} "
              f"raw={sg['sgmc_raw_pooled_dti']:.6f} n_pos={sg['n_withheld_positives']} "
              f"max3px(non-SF)={r['uniqueness_worst_non_space_filling_within_3px']} max|rho|={r['uniqueness_worst_abs_spearman']}",
              flush=True)

    EVIDENCE.write_text(json.dumps({
        "schema": "experiment-dilation/v1",
        "date_utc": "2026-10-31",
        "budget_index": 1,
        "hypothesis": "1-px dilation of the recommended dot set raises SGMC-CAL-v3.0 HOLDOUT-DTI under alpha=0.2, beta=0.8",
        "evaluator": "GEMSDOE32-SGMC-CAL-v3.0 (gems32.holdout.evaluate_sgmc_with_ci)",
        "label": "HOLDOUT-DTI (SGMC off-catalogue proxy; not organizer-confirmed)",
        "variants": results,
    }, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
