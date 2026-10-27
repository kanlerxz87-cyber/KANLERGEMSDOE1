#!/usr/bin/env python3
"""Canonical Protocol Rule 2 holdout evaluator CLI & helper (`evaluate_holdout.py`).

Delegates strictly to `gems32.holdout` (no private fork) to evaluate a GeoTIFF or `.npy` mask/field
using BOTH:
  1. `HOLDOUT-DTI` (`GEMSDOE32-HIDE-RECOVER-v3.1`): whole-segment withheld faults with 1.5 km collar,
     visible-only masking + visible-only `B` gate, exact pooled DTI (alpha=0.2, beta=0.8, 300 m
     triangular kernel) and a spatial cluster-bootstrap 95% CI. Per-cell predictions do not by
     themselves prove fold-local provenance; full-map inputs require an explicit diagnostic flag.
  2. `HOLDOUT-DTI` (`GEMSDOE32-SGMC-CAL-v3.0`): off-catalogue USGS SGMC faults (>300 m from `labels.tif`)
     with 256-block spatial cluster-bootstrap 95% CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems32 import holdout  # noqa: E402
from gems32.paths import data_dir  # noqa: E402


def _strip_internal(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def evaluate_path(
    path: Path,
    b_visible_px: float = 0.0,
    ddir: Path | None = None,
    name: str | None = None,
    *,
    diagnostic_full_map: bool = False,
    sgmc_map: Path | None = None,
) -> dict:
    ddir = ddir or data_dir()
    ctx = holdout.load_holdout_context(ddir)
    cand_name = name or path.stem
    suf = path.suffix.lower()
    if suf == ".npz":
        with np.load(path) as zf:
            # Preserve dtype and values so the shared evaluator can reject NaN,
            # soft, or out-of-range arrays rather than silently casting them.
            cells = {k: np.asarray(zf[k]) for k in zf.files}
        hr = _strip_internal(holdout.evaluate_hide_and_recover(cells, ctx, b_visible_px=b_visible_px, name=cand_name))
        out = {
            "candidate_id": cand_name,
            "path": str(path),
            "mode": "per_cell_oof_npz",
            "hide_and_recover": hr,
        }
        if sgmc_map is not None:
            if sgmc_map.suffix.lower() == ".npy":
                s_arr = np.load(sgmc_map)
            else:
                with rasterio.open(sgmc_map) as ds:
                    s_arr = ds.read(1)
            if s_arr.shape != ctx.foot.shape:
                raise ValueError(f"Expected SGMC map shape {ctx.foot.shape}, got {s_arr.shape}")
            if not np.isfinite(s_arr).all() or not np.all((s_arr == 0) | (s_arr == 1)):
                raise ValueError("SGMC map must be finite and binary")
            if (s_arr[~ctx.foot] != 0).any():
                raise ValueError("SGMC map contains nonzero values outside valid footprint")
            s_mask = (s_arr > 0) & ctx.foot
            out["emitted_pixels"] = int(s_mask.sum())
            out["sgmc_off_catalogue"] = _strip_internal(holdout.evaluate_sgmc_with_ci(s_mask, ctx, name=cand_name))
        return out
    if not diagnostic_full_map:
        raise ValueError("A single full-map prediction is not fold-local; use an .npz or --diagnostic-full-map")
    if suf == ".npy":
        arr = np.load(path)
    else:
        with rasterio.open(path) as ds:
            arr = ds.read(1)
    if arr.shape != ctx.foot.shape:
        raise ValueError(f"Expected grid shape {ctx.foot.shape}, got {arr.shape}")
    if not np.isfinite(arr).all() or not np.all((arr == 0) | (arr == 1)):
        raise ValueError("Diagnostic map must be finite and binary; values are not silently repaired")
    mask = (arr > 0) & ctx.foot
    hr = _strip_internal(holdout.evaluate_hide_and_recover(mask, ctx, b_visible_px=b_visible_px, name=cand_name, diagnostic_allow_full_map=True))
    sg = _strip_internal(holdout.evaluate_sgmc_with_ci(mask, ctx, name=cand_name))
    legacy = holdout.evaluate_candidate_holdout(mask, ctx, name=cand_name)
    return {
        "candidate_id": cand_name,
        "path": str(path),
        "emitted_pixels": int(mask.sum()),
        "hide_and_recover": hr,
        "sgmc_off_catalogue": sg,
        "legacy_summary": {
            "catalogue_hidden_mean": legacy["catalogue_hidden_mean"],
            "sgmc_prevalence_calibrated_dti": legacy["sgmc_prevalence_calibrated_dti"],
            "drift_corrected_holdout_mean": legacy["drift_corrected_holdout_mean"],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("candidate", type=Path, help="GeoTIFF, .npy mask, or .npz per-cell fold predictions")
    ap.add_argument("--b-visible-px", type=float, default=0.0, help="Visible-only B exclusion radius in pixels")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--sgmc-map", type=Path, default=None, help="Optional full-map OOF binary .tif/.npy for off-catalogue SGMC evaluation alongside per-cell .npz")
    ap.add_argument("--diagnostic-full-map", action="store_true", help="Allow a non-fold-local binary map for diagnosis only, never promotion")
    args = ap.parse_args()

    res = evaluate_path(
        args.candidate,
        b_visible_px=args.b_visible_px,
        ddir=args.data_dir or data_dir(),
        name=args.name,
        diagnostic_full_map=args.diagnostic_full_map,
        sgmc_map=args.sgmc_map,
    )
    txt = json.dumps(res, indent=2)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(txt + "\n")
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
