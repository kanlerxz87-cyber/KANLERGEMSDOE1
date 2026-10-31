#!/usr/bin/env python3
"""Fold-local learned hazard lane (HGB) scored with the shared hide-and-recover evaluator.

Lane: "HGB-FOLDLOCAL" -- a histogram gradient-boosted classifier trained ONLY on the
visible catalogue of each hide-and-recover cell, with a 1.5 km collar around the test
quadrant. Emission = top-K local maxima of the predicted hazard inside the active domain,
with the B=2 px collar gate (EDT(visible) > 2) applied BEFORE top-K so the budget is spent
on eligible pixels.

Protocol mapping (PARALLEL-RUN PROTOCOL):
  Rule 2  : uses gems32.holdout.load_holdout_context / evaluate_hide_and_recover /
            evaluate_sgmc_with_ci unchanged (no private evaluator fork).
  Rule 3  : every number is labelled HOLDOUT-DTI with evaluator version, N withheld
            positives and the 95% cluster-bootstrap CI emitted by the evaluator.
  Rule 4  : leakage canary = per-band single-feature AUC on hidden truth vs active
            background, per cell. AUC>0.90 would mean leakage until proven otherwise.
  Rule 6  : runs are capped by the caller (see evidence/ JSON for the experiment id).

Usage:
  python scripts/run_fold_hgb_lane.py --experiment E1 [--nms 0] [--b 2]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import binary_dilation, distance_transform_edt, maximum_filter
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gems32 import holdout  # noqa: E402
from gems32.paths import data_dir  # noqa: E402

# Seismic bands (10 deq_n100a15, 16 ieq_n100a15) are INGENIOUS earthquake-derived and are
# excluded from the MODEL but are still canary-tested. Band numbers are 1-based.
SEISMIC_BANDS = (10, 16)
N_BANDS = 19
# Budget matched to the 0.2778 incumbent: 37,654 emitted dots over a 5,167,373-px footprint.
BUDGET_FRAC = 37654 / 5167373
NEG_SAMPLE = 300_000
SEED = 20261031


def load_features(ddir: Path, foot: np.ndarray) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    """Footprint-restricted feature matrix (model bands only) + full-band copies for canaries."""
    model_cols = []
    per_band: dict[int, np.ndarray] = {}
    with rasterio.open(ddir / "training_features.tif") as ds:
        nodata = ds.nodata
        for j in range(1, N_BANDS + 1):
            a = ds.read(j).astype(np.float32)
            if nodata is not None:
                a[a == np.float32(nodata)] = np.nan
            a[~np.isfinite(a)] = np.nan
            v = a[foot]
            per_band[j] = v
            if j not in SEISMIC_BANDS:
                model_cols.append(v)
            del a
    X = np.stack(model_cols, axis=1).astype(np.float32)
    return X, per_band


def footprint_vec(full: np.ndarray, foot: np.ndarray) -> np.ndarray:
    return full[foot]


def to_full(vec: np.ndarray, foot: np.ndarray, fill: float = 0.0) -> np.ndarray:
    out = np.full(foot.shape, fill, dtype=np.float32)
    out[foot] = vec
    return out


def fold_model(X: np.ndarray, foot: np.ndarray, visible: np.ndarray, quad_fold: np.ndarray,
               collar_f: np.ndarray, rng: np.random.Generator) -> HistGradientBoostingClassifier:
    """Train on visible catalogue only, outside the test-quadrant collar."""
    train_area = foot & ~collar_f
    d_vis = distance_transform_edt(~visible).astype(np.float32)
    pos = visible & train_area
    neg = train_area & (d_vis > 3.0)
    pos_v = footprint_vec(pos, foot)
    neg_v = footprint_vec(neg, foot)
    pi = np.flatnonzero(pos_v)
    ni = np.flatnonzero(neg_v)
    if ni.size > NEG_SAMPLE:
        ni = rng.choice(ni, NEG_SAMPLE, replace=False)
    idx = np.concatenate([pi, ni])
    y = np.concatenate([np.ones(pi.size), np.zeros(ni.size)])
    clf = HistGradientBoostingClassifier(
        max_iter=150, learning_rate=0.08, max_leaf_nodes=31, l2_regularization=1.0,
        random_state=SEED,
    )
    clf.fit(X[idx], y)
    return clf


def select_dots(p_full: np.ndarray, cand: np.ndarray, budget_n: int, nms: int) -> np.ndarray:
    """Top-K by hazard among eligible pixels; optional local-maximum thinning (radius nms)."""
    score = np.where(cand, p_full, -np.inf).astype(np.float32)
    if nms > 0:
        size = 2 * nms + 1
        mf = maximum_filter(score, size=size, mode="constant", cval=-np.inf)
        cand = cand & (score >= mf)
        score = np.where(cand, score, -np.inf)
    flat = score.ravel()
    n_ok = int(np.isfinite(flat).sum())
    k = min(budget_n, n_ok)
    dots = np.zeros(score.shape, bool)
    if k <= 0:
        return dots
    top = np.argpartition(-flat, k - 1)[:k]
    dots.ravel()[top] = True
    return dots


def canary(ds_bands: dict[int, np.ndarray], foot: np.ndarray, ctx, rng) -> list[dict]:
    """Single-feature AUC of each band on hidden truth vs active background, per cell."""
    rows = []
    for j in range(1, N_BANDS + 1):
        v = ds_bands[j]
        v = np.where(np.isfinite(v), v, np.nanmedian(v[np.isfinite(v)]))
        aucs = []
        for cell in ctx.cells:
            act_full = np.zeros(foot.shape, bool)
            act_full[cell.bbox] = cell.active_sub
            truth_full = np.zeros(foot.shape, bool)
            tr, tc = cell.truth_coords
            truth_full[cell.bbox[0].start + tr, cell.bbox[1].start + tc] = True
            act_v = footprint_vec(act_full, foot)
            tru_v = footprint_vec(truth_full, foot)
            pos = np.flatnonzero(tru_v & act_v)
            neg = np.flatnonzero(act_v & ~tru_v)
            if pos.size < 5 or neg.size < 5:
                continue
            neg = rng.choice(neg, min(neg.size, 200_000), replace=False)
            y = np.r_[np.ones(pos.size), np.zeros(neg.size)]
            s = np.r_[v[pos], v[neg]]
            auc = roc_auc_score(y, s)
            aucs.append(max(auc, 1.0 - auc))  # sign-agnostic single-feature AUC
        rows.append({
            "band": j,
            "feature_seismic_excluded_from_model": j in SEISMIC_BANDS,
            "max_cell_auc": float(max(aucs)) if aucs else None,
            "mean_cell_auc": float(np.mean(aucs)) if aucs else None,
            "leakage_flag_over_0.90": bool(aucs and max(aucs) > 0.90),
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--nms", type=int, default=0, help="local-maximum radius in px (0 = off)")
    ap.add_argument("--b", type=float, default=2.0, help="visible-collar gate in px (EDT > b)")
    ap.add_argument("--skip-canary", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    t0 = time.time()
    ddir = data_dir()
    ctx = holdout.load_holdout_context(ddir)
    foot = ctx.foot
    rng = np.random.default_rng(SEED)

    X, per_band = load_features(ddir, foot)
    report: dict = {
        "schema": "fold-local-lane-run/v1",
        "experiment": args.experiment,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "lane": "HGB-FOLDLOCAL",
        "model_bands": [j for j in range(1, N_BANDS + 1) if j not in SEISMIC_BANDS],
        "budget_frac": BUDGET_FRAC,
        "params": {"nms_radius_px": args.nms, "b_visible_px": args.b, "neg_sample": NEG_SAMPLE, "seed": SEED},
        "evaluator": {"hide_recover": holdout.HIDE_RECOVER_EVALUATOR_VERSION,
                      "sgmc": holdout.SGMC_EVALUATOR_VERSION},
    }

    if not args.skip_canary:
        report["leakage_canary"] = canary(per_band, foot, ctx, rng)
        report["leakage_canary_max_auc"] = max(r["max_cell_auc"] or 0.0 for r in report["leakage_canary"])

    cell_maps: dict[str, np.ndarray] = {}
    full_draw20 = np.zeros(foot.shape, bool)
    per_cell_info = {}
    for cell in ctx.cells:
        visible = cell.visible_full
        quad_fold = ctx.quad == cell.fold
        collar_f = binary_dilation(quad_fold, structure=np.ones((3, 3), bool), iterations=holdout.COLLAR_PX) & foot
        clf = fold_model(X, foot, visible, quad_fold, collar_f, rng)
        d_vis = distance_transform_edt(~visible).astype(np.float32)
        # Full-grid active domain for this cell (exactly the evaluator's domain)
        act_full = np.zeros(foot.shape, bool)
        act_full[cell.bbox] = cell.active_sub
        cand = act_full & (d_vis > args.b)
        cand_v = footprint_vec(cand, foot)
        p_v = np.zeros(foot.sum(), dtype=np.float32)
        ci = np.flatnonzero(cand_v)
        p_v[ci] = clf.predict_proba(X[ci])[:, 1].astype(np.float32)
        p_full = to_full(p_v, foot)
        budget_n = int(round(BUDGET_FRAC * int(cand.sum())))
        dots = select_dots(p_full, cand, budget_n, args.nms)
        cell_maps[cell.key] = dots
        per_cell_info[cell.key] = {"eligible_px": int(cand.sum()), "budget_n": budget_n,
                                   "emitted": int(dots.sum())}
        if cell.seed == 20:
            full_draw20 |= dots
        print(f"{cell.key}: eligible={int(cand.sum())} budget={budget_n} emitted={int(dots.sum())}", flush=True)

    hr = holdout.evaluate_hide_and_recover(cell_maps, ctx, b_visible_px=args.b, name=args.experiment)
    sg = holdout.evaluate_sgmc_with_ci(full_draw20, ctx, name=args.experiment)
    report["cells"] = per_cell_info
    report["hide_and_recover"] = {k: v for k, v in hr.items() if not k.startswith("_") and k != "folds"}
    report["hide_and_recover"]["per_cell_dti"] = {k: round(v["dti"], 6) for k, v in hr["folds"].items()}
    report["sgmc_off_catalogue_draw20_composite"] = {k: v for k, v in sg.items() if not k.startswith("_")}
    report["score_labels"] = {
        "hide_recover": f"HOLDOUT-DTI ({holdout.HIDE_RECOVER_EVALUATOR_VERSION}, N={hr['n_withheld_positives']}, "
                        f"95% CI {hr['ci95_cluster_bootstrap']})",
        "sgmc": f"HOLDOUT-DTI ({holdout.SGMC_EVALUATOR_VERSION}, N={sg['n_withheld_positives']}, "
                f"95% CI {sg['sgmc_calibrated_ci95']} [calibrated])",
    }
    report["elapsed_seconds"] = round(time.time() - t0, 1)
    out = args.out or (ROOT / "evidence" / f"fold_hgb_{args.experiment}.json")
    out.write_text(json.dumps(report, indent=2, default=float) + "\n")
    # Keep the dots of the last run in the workspace cache (not committed) for later validation.
    cache = ROOT / "data" / "cache" / f"fold_hgb_{args.experiment}_draw20_union.npy"
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, full_draw20)
    print(json.dumps({k: report[k] for k in ("score_labels",)}, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
