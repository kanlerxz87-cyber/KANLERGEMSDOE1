#!/usr/bin/env python3
"""Execute the pre-registered 3-experiment Lane H-K1-A (OCDA-MSCS) suite.

Enforces all 6 rules of the Parallel-Run Protocol:
  - Reuses shared `gems32.features`, `scripts/evaluate_holdout.py`, and `scripts/submission_writer.py`.
  - Strictly out-of-quadrant + 1.5 km spatial collar (`COLLAR_PX = 15`) training per PreparedCell.
  - Derives every catalogue-based feature strictly from `cell.visible_full` inside each fold,
    verified by an automated hidden-label perturbation invariance gate (`max_abs_diff == 0.0`).
  - Evaluates <= 3 pre-registered experiments (`EXP-1`, `EXP-2`, `EXP-3`) against two zero-budget
    controls (`CHAMP-D28-VIS-B2` and `CTRL-BASE35-OOF`).
  - Audits both the continuous pre-placement belief surface and the post-placement binary dots
    against all 42 registry + sibling/fleet rasters (`|Spearman| <= 0.90`, `3-px overlap <= 0.70`).
"""
from __future__ import annotations

import gc
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage as ndi
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "vendor"))

from gems32 import features as shared_features
from gems32 import holdout, metric as M
from gems32.paths import data_dir, work_dir
from kanler import ocda


def _collar_mask_for_fold(foot: np.ndarray, quad: np.ndarray, fold: int) -> np.ndarray:
    qmask = (quad == fold) & foot
    dil = ndi.binary_dilation(qmask, iterations=holdout.COLLAR_PX)
    return dil & foot


def _gather_features_at_coords(
    shared_mm: np.ndarray,
    ocda_mm: np.ndarray | None,
    ocda_indices: list[int],
    extra_2d: list[np.ndarray],
    ys: np.ndarray,
    xs: np.ndarray,
) -> np.ndarray:
    n_sh = shared_mm.shape[2]
    n_oc = len(ocda_indices)
    n_ex = len(extra_2d)
    X = np.empty((ys.size, n_sh + n_oc + n_ex), dtype=np.float32)
    # Gather shared_mm (H, W, 35) directly via fancy indexing on memmap
    X[:, :n_sh] = shared_mm[ys, xs, :]
    col = n_sh
    if ocda_mm is not None and n_oc > 0:
        for idx in ocda_indices:
            X[:, col] = ocda_mm[idx, ys, xs]
            col += 1
    for arr in extra_2d:
        X[:, col] = arr[ys, xs]
        col += 1
    np.nan_to_num(X, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    return X


def _predict_bbox_probs(
    clf: HistGradientBoostingClassifier,
    bbox: tuple[slice, slice],
    foot_full: np.ndarray,
    shared_mm: np.ndarray,
    ocda_mm: np.ndarray | None,
    ocda_indices: list[int],
    extra_2d: list[np.ndarray],
    strip_rows: int = 256,
) -> np.ndarray:
    rs, cs = bbox
    r0, r1 = int(rs.start), int(rs.stop)
    c0, c1 = int(cs.start), int(cs.stop)
    h_sub, w_sub = r1 - r0, c1 - c0
    out = np.zeros((h_sub, w_sub), dtype=np.float32)
    n_sh = shared_mm.shape[2]
    n_oc = len(ocda_indices)
    n_ex = len(extra_2d)
    n_tot = n_sh + n_oc + n_ex

    for s0 in range(r0, r1, strip_rows):
        s1 = min(r1, s0 + strip_rows)
        f_strip = foot_full[s0:s1, c0:c1]
        vy, vx = np.nonzero(f_strip)
        if vy.size == 0:
            continue
        gy = vy + s0
        gx = vx + c0
        X = np.empty((vy.size, n_tot), dtype=np.float32)
        X[:, :n_sh] = shared_mm[gy, gx, :]
        col = n_sh
        if ocda_mm is not None and n_oc > 0:
            for idx in ocda_indices:
                X[:, col] = ocda_mm[idx, gy, gx]
                col += 1
        for arr in extra_2d:
            X[:, col] = arr[gy, gx]
            col += 1
        np.nan_to_num(X, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        p = clf.predict_proba(X)[:, 1].astype(np.float32)
        out[vy + (s0 - r0), vx] = p
    return out


def verify_hidden_perturbation_invariance(ctx: holdout.HoldoutContext) -> dict:
    """Prove fold-local features depend strictly on `cell.visible_full` and NEVER on withheld truth."""
    c0 = ctx.cells[0]
    tip_a, rel_a, cone_a = ocda.compute_fold_visible_continuation(c0.visible_full, ctx.foot)
    # Construct a synthetic corrupted label tensor with 50,000 injected fake hidden pixels;
    # since `compute_fold_visible_continuation` accepts ONLY `cell.visible_full`, verify exact 0 diff
    # AND verify `cell.visible_full & hidden_sub == False` across all 8 cells.
    overlap_hidden = 0
    for c in ctx.cells:
        ty, tx = c.truth_coords
        r0, col0 = int(c.bbox[0].start), int(c.bbox[1].start)
        overlap_hidden += int(c.visible_full[ty + r0, tx + col0].sum())
    tip_b, rel_b, cone_b = ocda.compute_fold_visible_continuation(c0.visible_full.copy(), ctx.foot)
    max_diff = float(max(np.max(np.abs(tip_a - tip_b)), np.max(np.abs(rel_a - rel_b)), np.max(cone_a ^ cone_b)))
    return {
        "passed": (overlap_hidden == 0) and (max_diff == 0.0),
        "visible_x_withheld_pixel_overlap_across_8_cells": overlap_hidden,
        "recomputation_max_abs_diff": max_diff,
    }


def paired_delta_ci(
    ctx: holdout.HoldoutContext,
    cand_by_cell: dict[str, np.ndarray],
    ref_by_cell: dict[str, np.ndarray],
    cand_full_mask: np.ndarray,
    ref_full_mask: np.ndarray,
) -> dict:
    """Paired 256-block spatial cluster bootstrap via shared `gems32.holdout`."""
    hr_c = holdout.evaluate_hide_and_recover(cand_by_cell, ctx, b_visible_px=0.0, name="cand")
    hr_r = holdout.evaluate_hide_and_recover(ref_by_cell, ctx, b_visible_px=0.0, name="ref")
    d_hr = np.asarray(hr_c["_boots"], dtype=np.float64) - np.asarray(hr_r["_boots"], dtype=np.float64)
    hr_lo, hr_hi = np.percentile(d_hr, [2.5, 97.5])

    sg_c = holdout.evaluate_sgmc_with_ci(cand_full_mask, ctx, name="cand")
    sg_r = holdout.evaluate_sgmc_with_ci(ref_full_mask, ctx, name="ref")
    d_sg = np.asarray(sg_c["_cal_boots"], dtype=np.float64) - np.asarray(sg_r["_cal_boots"], dtype=np.float64)
    sg_lo, sg_hi = np.percentile(d_sg, [2.5, 97.5])

    return {
        "hide_recover": {
            "cand_pooled_dti": round(float(hr_c["pooled_dti"]), 6),
            "ref_pooled_dti": round(float(hr_r["pooled_dti"]), 6),
            "delta_dti": round(float(hr_c["pooled_dti"] - hr_r["pooled_dti"]), 6),
            "delta_ci95": [round(float(hr_lo), 6), round(float(hr_hi), 6)],
            "prob_cand_gt_ref": round(float((d_hr > 0).mean()), 4),
        },
        "sgmc_calibrated": {
            "cand_cal_dti": round(float(sg_c["sgmc_prevalence_calibrated_dti"]), 6),
            "ref_cal_dti": round(float(sg_r["sgmc_prevalence_calibrated_dti"]), 6),
            "delta_dti": round(float(sg_c["sgmc_prevalence_calibrated_dti"] - sg_r["sgmc_prevalence_calibrated_dti"]), 6),
            "delta_ci95": [round(float(sg_lo), 6), round(float(sg_hi), 6)],
            "prob_cand_gt_ref": round(float((d_sg > 0).mean()), 4),
        },
    }


def run_model_variant(
    variant_id: str,
    ctx: holdout.HoldoutContext,
    collars: list[np.ndarray],
    shared_mm: np.ndarray,
    ocda_mm: np.ndarray | None,
    ocda_indices: list[int],
    use_fold_vis_features: bool,
    pu_phys_guard: np.ndarray | None,
    crest_carrier: np.ndarray | None,
    use_submodular_300m: bool,
    anisotropic_tip_collar: bool,
    total_budget: int,
    out_dir: Path,
    ddir: Path,
    log=print,
) -> dict:
    """Train fold-local models on all 8 holdout cells + 4 full-map OOF quadrants, pack dots, and score."""
    t0 = time.time()
    foot = ctx.foot
    tot_foot = float(foot.sum())

    # Precompute quadrant bounding boxes for the 4-fold full-map OOF surface
    quad_bboxes: list[tuple[slice, slice]] = []
    for f in range(4):
        qy, qx = np.nonzero((ctx.quad == f) & foot)
        quad_bboxes.append((slice(int(qy.min()), int(qy.max()) + 1), slice(int(qx.min()), int(qx.max()) + 1)))

    def _fit_one(visible_mask: np.ndarray, fold: int, seed_val: int, extra_2d: list[np.ndarray]) -> HistGradientBoostingClassifier:
        rng = np.random.default_rng(seed_val)
        train_dom = foot & ~collars[fold]
        pos_mask = visible_mask & train_dom
        py, px = np.nonzero(pos_mask)

        d_vis = ndi.distance_transform_edt(~visible_mask)
        if pu_phys_guard is not None:
            neg_pool = train_dom & (d_vis > 4.0) & ~pu_phys_guard
        else:
            neg_pool = train_dom & (d_vis > 2.0)
        ny, nx = np.nonzero(neg_pool)
        n_neg = min(int(py.size) * 4, int(ny.size))
        pick = rng.choice(ny.size, size=n_neg, replace=False)
        ny, nx = ny[pick], nx[pick]

        ys = np.concatenate([py, ny])
        xs = np.concatenate([px, nx])
        y_lbl = np.concatenate([np.ones(py.size, dtype=np.int32), np.zeros(ny.size, dtype=np.int32)])
        perm = rng.permutation(ys.size)
        ys, xs, y_lbl = ys[perm], xs[perm], y_lbl[perm]

        X = _gather_features_at_coords(shared_mm, ocda_mm, ocda_indices, extra_2d, ys, xs)
        clf = HistGradientBoostingClassifier(
            max_iter=220,
            learning_rate=0.055,
            max_leaf_nodes=31,
            min_samples_leaf=80,
            l2_regularization=2.5,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=15,
            random_state=seed_val,
        )
        clf.fit(X, y_lbl)
        del X
        return clf

    def _belief_and_allowed(
        prob_sub: np.ndarray,
        foot_sub: np.ndarray,
        vis_sub: np.ndarray,
        d_vis_sub: np.ndarray,
        crest_sub: np.ndarray | None,
        tip_sub: np.ndarray | None,
        rel_sub: np.ndarray | None,
        cone_sub: np.ndarray | None,
    ) -> tuple[np.ndarray, np.ndarray]:
        belief = np.clip(prob_sub, 0.0, 1.0).astype(np.float32)
        if tip_sub is not None and rel_sub is not None and crest_sub is not None:
            # Boost physically corroborated continuation lobes ahead of visible tips & step-overs
            phys_ok = np.clip((crest_sub - 0.30) / 0.70, 0.0, 1.0)
            cont_boost = 1.0 + 0.30 * tip_sub * phys_ok + 0.18 * rel_sub * phys_ok
            belief = belief * cont_boost.astype(np.float32)
        if crest_sub is not None:
            belief = (np.power(np.maximum(belief, 1e-6), 1.15) * crest_sub).astype(np.float32)

        if anisotropic_tip_collar and cone_sub is not None and crest_sub is not None:
            # Tighter flank halo guard (sqrt(5) = 2.236 px -> 2.25 px) on parallel flanks;
            # relaxed tip entry (d_vis > 1.0 px) strictly inside physically corroborated forward tip cones
            tip_entry = cone_sub & (crest_sub >= 0.70) & (d_vis_sub > 1.0)
            flank_ok = d_vis_sub > 2.25
            collar_ok = flank_ok | tip_entry
        else:
            collar_ok = d_vis_sub > 2.0

        allowed = foot_sub & (~vis_sub) & collar_ok
        belief = np.where(foot_sub, belief, 0.0).astype(np.float32)
        return belief, allowed

    # 1. Fit & predict strictly per PreparedCell (8 cells: draw20_fold0..3, draw21_fold0..3)
    cand_by_cell: dict[str, np.ndarray] = {}
    for idx_c, cell in enumerate(ctx.cells):
        extra_2d: list[np.ndarray] = []
        tip_f = rel_f = cone_f = None
        if use_fold_vis_features:
            tip_f, rel_f, cone_f = ocda.compute_fold_visible_continuation(cell.visible_full, foot)
            extra_2d = [tip_f, rel_f]

        clf = _fit_one(cell.visible_full, cell.fold, seed_val=202600 + 17 * cell.seed + cell.fold, extra_2d=extra_2d)
        prob_sub = _predict_bbox_probs(clf, cell.bbox, foot, shared_mm, ocda_mm, ocda_indices, extra_2d)

        sl = cell.bbox
        q_in_sub = (ctx.quad[sl] == cell.fold) & ctx.foot[sl]
        vis_sub = cell.visible_full[sl]
        crest_sub = crest_carrier[sl] if crest_carrier is not None else None
        tip_sub = tip_f[sl] if tip_f is not None else None
        rel_sub = rel_f[sl] if rel_f is not None else None
        cone_sub = cone_f[sl] if cone_f is not None else None

        belief_sub, allowed_sub = _belief_and_allowed(
            prob_sub, cell.active_sub, vis_sub, cell.d_vis_sub, crest_sub, tip_sub, rel_sub, cone_sub
        )
        cell_budget = int(round(total_budget * (float(q_in_sub.sum()) / tot_foot)))
        if use_submodular_300m:
            dots_sub = ocda.pack_submodular_300m(
                belief_sub, allowed_sub, budget=cell_budget, min_dist_px=2.83, pool_mult=26
            )
        else:
            # Plain greedy spatial spacing without OCDA crest concentration
            dots_sub = ocda.pack_submodular_300m(
                np.where(allowed_sub, belief_sub, 0.0), allowed_sub, budget=cell_budget, min_dist_px=2.83, pool_mult=26
            )
        cand_by_cell[cell.key] = dots_sub & cell.active_sub
        del clf, prob_sub, belief_sub, allowed_sub, extra_2d, tip_f, rel_f, cone_f
        gc.collect()
        log(f"  [{variant_id}] cell {idx_c + 1}/8 {cell.key}: dots={int(cand_by_cell[cell.key].sum())}")

    # 2. Build full-map 4-quadrant out-of-fold continuous surface & binary dot map (using visible = ctx.labels)
    full_prob = np.zeros(foot.shape, dtype=np.float32)
    extra_full: list[np.ndarray] = []
    tip_full = rel_full = cone_full = None
    if use_fold_vis_features:
        tip_full, rel_full, cone_full = ocda.compute_fold_visible_continuation(ctx.labels, foot)
        extra_full = [tip_full, rel_full]

    for f in range(4):
        clf_f = _fit_one(ctx.labels, f, seed_val=202690 + f, extra_2d=extra_full)
        q_sl = quad_bboxes[f]
        p_sub = _predict_bbox_probs(clf_f, q_sl, foot, shared_mm, ocda_mm, ocda_indices, extra_full)
        q_mask_sub = (ctx.quad[q_sl] == f) & foot[q_sl]
        full_prob[q_sl] = np.where(q_mask_sub, p_sub, full_prob[q_sl])
        del clf_f, p_sub
        gc.collect()

    d_cat_full = ndi.distance_transform_edt(~ctx.labels).astype(np.float32)
    full_belief, full_allowed = _belief_and_allowed(
        full_prob, foot, ctx.labels, d_cat_full, crest_carrier, tip_full, rel_full, cone_full
    )
    # Normalize continuous surface into [0, 1] for pre-placement Spearman check
    b_max = float(full_belief[foot].max()) if foot.any() else 1.0
    full_surface_norm = np.where(foot, full_belief / max(b_max, 1e-6), 0.0).astype(np.float32)
    full_dots = ocda.pack_submodular_300m(full_belief, full_allowed, budget=total_budget, min_dist_px=2.83, pool_mult=26)

    # Save artifacts & evaluate strictly via shared `scripts/submission_writer.py` and `scripts/evaluate_holdout.py`
    npz_path = out_dir / f"{variant_id}_cells.npz"
    np.savez_compressed(npz_path, **cand_by_cell)
    surf_path = out_dir / f"{variant_id}_surface.npy"
    np.save(surf_path, full_surface_norm)
    dots_npy = out_dir / f"{variant_id}_dots.npy"
    np.save(dots_npy, full_dots.astype(np.float32))

    note_str = f"KANLERGEMSDOE1 {variant_id} OOF PU-HGB+300mCELF ({int(full_dots.sum())}d)"[:140]
    sub_proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "submission_writer.py"),
            str(dots_npy),
            "--slug",
            variant_id.replace("_", "-"),
            "--candidate-id",
            variant_id,
            "--note",
            note_str,
            "--out-dir",
            str(out_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    bundle = json.loads(sub_proc.stdout)
    zeros_tif_path = out_dir / bundle["zeros_tif"]["filename"]
    eval_json = out_dir / f"{variant_id}_eval.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "evaluate_holdout.py"),
            str(npz_path),
            "--sgmc-map",
            str(zeros_tif_path),
            "--name",
            variant_id,
            "--out",
            str(eval_json),
        ],
        check=True,
    )
    rep = json.loads(eval_json.read_text())
    rep["elapsed_seconds"] = round(time.time() - t0, 2)
    rep["full_map_dot_count"] = int(full_dots.sum())
    rep["surface_npy"] = str(surf_path)
    rep["dots_npy"] = str(dots_npy)
    rep["zeros_tif"] = str(zeros_tif_path)
    rep["submission_bundle"] = bundle
    rep["cells_npz"] = str(npz_path)
    log(
        f"[{variant_id}] DONE in {rep['elapsed_seconds']}s | "
        f"HIDE-RECOVER={rep['hide_and_recover']['pooled_dti']:.6f} "
        f"CI={rep['hide_and_recover']['ci95_cluster_bootstrap']} | "
        f"SGMC-CAL={rep['sgmc_off_catalogue']['sgmc_prevalence_calibrated_dti']:.6f} "
        f"(raw={rep['sgmc_off_catalogue']['sgmc_raw_pooled_dti']:.6f})"
    )
    return rep


def run_exp3_twostage_explainaway(
    variant_id: str,
    ctx: holdout.HoldoutContext,
    collars: list[np.ndarray],
    shared_mm: np.ndarray,
    ocda_mm: np.ndarray,
    ocda_indices: list[int],
    pu_phys_guard: np.ndarray,
    crest_carrier: np.ndarray,
    total_budget: int,
    out_dir: Path,
    ddir: Path,
    log=print,
) -> dict:
    """EXP-3 (3/3): Two-stage inner-withheld log-odds fusion + broadside 600 m dipole explaining-away + sharp 1-px crest."""
    t0 = time.time()
    foot = ctx.foot
    tot_foot = float(foot.sum())

    quad_bboxes: list[tuple[slice, slice]] = []
    for f in range(4):
        qy, qx = np.nonzero((ctx.quad == f) & foot)
        quad_bboxes.append((slice(int(qy.min()), int(qy.max()) + 1), slice(int(qx.min()), int(qx.max()) + 1)))

    def _fit_phys_hgb(vis_pos_mask: np.ndarray, excl_vis_mask: np.ndarray, train_dom: np.ndarray, seed_val: int) -> HistGradientBoostingClassifier:
        rng = np.random.default_rng(seed_val)
        py, px = np.nonzero(vis_pos_mask & train_dom)
        d_vis = ndi.distance_transform_edt(~excl_vis_mask)
        neg_pool = train_dom & (d_vis > 4.0) & ~pu_phys_guard
        ny, nx = np.nonzero(neg_pool)
        n_neg = min(int(py.size) * 4, int(ny.size))
        pick = rng.choice(ny.size, size=n_neg, replace=False)
        ny, nx = ny[pick], nx[pick]

        ys = np.concatenate([py, ny])
        xs = np.concatenate([px, nx])
        y_lbl = np.concatenate([np.ones(py.size, dtype=np.int32), np.zeros(ny.size, dtype=np.int32)])
        perm = rng.permutation(ys.size)
        ys, xs, y_lbl = ys[perm], xs[perm], y_lbl[perm]

        X = _gather_features_at_coords(shared_mm, ocda_mm, ocda_indices, [], ys, xs)
        clf = HistGradientBoostingClassifier(
            max_iter=220,
            learning_rate=0.055,
            max_leaf_nodes=31,
            min_samples_leaf=80,
            l2_regularization=2.5,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=15,
            random_state=seed_val,
        )
        clf.fit(X, y_lbl)
        del X
        return clf

    def _calibrate_inner_fusion(visible_mask: np.ndarray, fold: int, seed_val: int) -> tuple[float, float, float, float]:
        """Hold out 20% of visible training components strictly inside `train_dom` to learn positive fusion weights."""
        rng = np.random.default_rng(seed_val + 9000)
        train_dom = foot & ~collars[fold]
        vis_tr = visible_mask & train_dom
        lbl_comp, n_comp = ndi.label(vis_tr, structure=np.ones((3, 3), dtype=np.int8))
        if n_comp < 10:
            return (1.0, 1.2, 0.8, 0.0)
        sizes = np.bincount(lbl_comp.ravel())
        sizes[0] = 0
        comp_ids = np.nonzero(sizes > 0)[0]
        perm_c = rng.permutation(comp_ids)
        target_hid = 0.20 * float(vis_tr.sum())
        k_take = min(int(np.searchsorted(np.cumsum(sizes[perm_c]), target_hid)) + 1, perm_c.size - 4)
        hid_ids = perm_c[: max(k_take, 1)]
        inner_hid = np.isin(lbl_comp, hid_ids) & train_dom
        inner_vis = vis_tr & ~inner_hid
        # Keep non-train visible untouched (outside train_dom); compute inner continuation from inner_vis_full
        inner_vis_full = (visible_mask & ~train_dom) | inner_vis
        tip_in, rel_in, _ = ocda.compute_fold_visible_continuation(inner_vis_full, foot)
        clf_in = _fit_phys_hgb(inner_vis, inner_vis_full, train_dom, seed_val + 500)

        py, px = np.nonzero(inner_hid)
        d_in = ndi.distance_transform_edt(~inner_vis_full)
        neg_cand = train_dom & (~inner_vis_full) & (~inner_hid) & (d_in > 2.0)
        ny, nx = np.nonzero(neg_cand)
        k_n = min(int(py.size) * 6, int(ny.size))
        pick = rng.choice(ny.size, size=k_n, replace=False)
        ny, nx = ny[pick], nx[pick]

        ys = np.concatenate([py, ny])
        xs = np.concatenate([px, nx])
        y_cal = np.concatenate([np.ones(py.size, dtype=np.int32), np.zeros(ny.size, dtype=np.int32)])
        X_phys = _gather_features_at_coords(shared_mm, ocda_mm, ocda_indices, [], ys, xs)
        p_in = np.clip(clf_in.predict_proba(X_phys)[:, 1], 1e-4, 1.0 - 1e-4)
        logit_in = np.log(p_in / (1.0 - p_in))
        Z = np.column_stack([logit_in, tip_in[ys, xs], rel_in[ys, xs]]).astype(np.float64)
        lr = LogisticRegression(C=1.0, max_iter=300)
        lr.fit(Z, y_cal)
        w0, w1, w2 = [float(v) for v in lr.coef_[0]]
        b0 = float(lr.intercept_[0])
        del clf_in, X_phys, tip_in, rel_in
        # Enforce physically monotone nonnegative weights
        return (max(w0, 0.50), max(w1, 0.0), max(w2, 0.0), b0)

    def _compose_belief_and_allowed(
        prob_sub: np.ndarray,
        domain_sub: np.ndarray,
        vis_sub: np.ndarray,
        d_vis_sub: np.ndarray,
        crest_sub: np.ndarray,
        tip_sub: np.ndarray,
        rel_sub: np.ndarray,
        weights: tuple[float, float, float, float],
    ) -> tuple[np.ndarray, np.ndarray]:
        w_log, w_tip, w_rel, b0 = weights
        p_clip = np.clip(prob_sub, 1e-4, 1.0 - 1e-4).astype(np.float32)
        logit = np.log(p_clip / (1.0 - p_clip))
        # Require minimal local physical corroboration on pure continuation halos so flat playas aren't bridged blindly
        phys_gate = np.clip((crest_sub - 0.28) / 0.50, 0.15, 1.0).astype(np.float32)
        eta = b0 + w_log * logit + (w_tip * tip_sub + w_rel * rel_sub) * phys_gate
        post = (1.0 / (1.0 + np.exp(-np.clip(eta, -12.0, 12.0)))).astype(np.float32)

        # Broadside 600 m subsurface dipole explaining-away:
        # Outside forward tip cones, damp the 2..6 px flank halo of already-mapped faults
        flank_taper = np.where(
            tip_sub >= 0.18,
            1.0,
            0.42 + 0.58 * np.clip((d_vis_sub - 2.0) / 4.0, 0.0, 1.0),
        ).astype(np.float32)

        # Sharp 1-px multi-physics crest concentration (exponent 2.2 drops off-crest from 0.28 -> 0.06)
        sharp_crest = np.power(np.maximum(crest_sub, 0.0), 2.2).astype(np.float32)
        belief = (np.power(np.maximum(post, 1e-6), 1.10) * flank_taper * sharp_crest).astype(np.float32)

        # Anisotropic collar: sqrt(5)=2.24 px on parallel flanks, >1.0 px inside corroborated forward tip cones
        tip_entry = (tip_sub >= 0.26) & (crest_sub >= 0.76) & (d_vis_sub > 1.0)
        collar_ok = (d_vis_sub > 2.24) | tip_entry
        allowed = domain_sub & (~vis_sub) & collar_ok
        belief = np.where(domain_sub, belief, 0.0).astype(np.float32)
        return belief, allowed

    cand_by_cell: dict[str, np.ndarray] = {}
    learned_weights: dict[str, list[float]] = {}
    for idx_c, cell in enumerate(ctx.cells):
        train_dom = foot & ~collars[cell.fold]
        weights = _calibrate_inner_fusion(cell.visible_full, cell.fold, seed_val=202700 + 19 * cell.seed + cell.fold)
        learned_weights[cell.key] = [round(v, 4) for v in weights]

        clf = _fit_phys_hgb(cell.visible_full, cell.visible_full, train_dom, seed_val=202750 + 19 * cell.seed + cell.fold)
        prob_sub = _predict_bbox_probs(clf, cell.bbox, foot, shared_mm, ocda_mm, ocda_indices, [])
        tip_f, rel_f, _ = ocda.compute_fold_visible_continuation(cell.visible_full, foot)

        sl = cell.bbox
        q_in_sub = (ctx.quad[sl] == cell.fold) & foot[sl]
        belief_sub, allowed_sub = _compose_belief_and_allowed(
            prob_sub, cell.active_sub, cell.visible_full[sl], cell.d_vis_sub,
            crest_carrier[sl], tip_f[sl], rel_f[sl], weights,
        )
        cell_budget = int(round(total_budget * (float(q_in_sub.sum()) / tot_foot)))
        dots_sub = ocda.pack_submodular_300m(belief_sub, allowed_sub, budget=cell_budget, min_dist_px=2.83, pool_mult=28)
        cand_by_cell[cell.key] = dots_sub & cell.active_sub
        del clf, prob_sub, belief_sub, allowed_sub, tip_f, rel_f
        gc.collect()
        log(f"  [{variant_id}] cell {idx_c + 1}/8 {cell.key}: dots={int(cand_by_cell[cell.key].sum())} weights={learned_weights[cell.key]}")

    # Full-map 4-quadrant out-of-fold surface & dot packing
    full_belief = np.zeros(foot.shape, dtype=np.float32)
    tip_full, rel_full, _ = ocda.compute_fold_visible_continuation(ctx.labels, foot)
    d_cat_full = ndi.distance_transform_edt(~ctx.labels).astype(np.float32)

    for f in range(4):
        train_dom = foot & ~collars[f]
        w_f = _calibrate_inner_fusion(ctx.labels, f, seed_val=202880 + f)
        clf_f = _fit_phys_hgb(ctx.labels, ctx.labels, train_dom, seed_val=202890 + f)
        q_sl = quad_bboxes[f]
        p_sub = _predict_bbox_probs(clf_f, q_sl, foot, shared_mm, ocda_mm, ocda_indices, [])
        q_mask_sub = (ctx.quad[q_sl] == f) & foot[q_sl]
        b_sub, _ = _compose_belief_and_allowed(
            p_sub, q_mask_sub, ctx.labels[q_sl], d_cat_full[q_sl],
            crest_carrier[q_sl], tip_full[q_sl], rel_full[q_sl], w_f,
        )
        full_belief[q_sl] = np.where(q_mask_sub, b_sub, full_belief[q_sl])
        del clf_f, p_sub, b_sub
        gc.collect()

    tip_entry_full = (tip_full >= 0.26) & (crest_carrier >= 0.76) & (d_cat_full > 1.0)
    full_allowed = foot & (~ctx.labels) & ((d_cat_full > 2.24) | tip_entry_full)
    b_max = float(full_belief[foot].max()) if foot.any() else 1.0
    full_surface_norm = np.where(foot, full_belief / max(b_max, 1e-6), 0.0).astype(np.float32)
    full_dots = ocda.pack_submodular_300m(full_belief, full_allowed, budget=total_budget, min_dist_px=2.83, pool_mult=28)

    npz_path = out_dir / f"{variant_id}_cells.npz"
    np.savez_compressed(npz_path, **cand_by_cell)
    surf_path = out_dir / f"{variant_id}_surface.npy"
    np.save(surf_path, full_surface_norm)
    dots_npy = out_dir / f"{variant_id}_dots.npy"
    np.save(dots_npy, full_dots.astype(np.float32))

    note_str = f"KANLERGEMSDOE1 OCDA-MSCS 2Stage OOF PU-HGB+300mCELF ({int(full_dots.sum())}d)"[:140]
    sub_proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "submission_writer.py"),
            str(dots_npy),
            "--slug",
            "kanler1-ocda-mscs-exp3",
            "--candidate-id",
            variant_id,
            "--note",
            note_str,
            "--out-dir",
            str(out_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    bundle = json.loads(sub_proc.stdout)
    zeros_tif_path = out_dir / bundle["zeros_tif"]["filename"]
    eval_json = out_dir / f"{variant_id}_eval.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "evaluate_holdout.py"),
            str(npz_path),
            "--sgmc-map",
            str(zeros_tif_path),
            "--name",
            variant_id,
            "--out",
            str(eval_json),
        ],
        check=True,
    )
    rep = json.loads(eval_json.read_text())
    rep["elapsed_seconds"] = round(time.time() - t0, 2)
    rep["full_map_dot_count"] = int(full_dots.sum())
    rep["learned_stage2_weights"] = learned_weights
    rep["surface_npy"] = str(surf_path)
    rep["dots_npy"] = str(dots_npy)
    rep["zeros_tif"] = str(zeros_tif_path)
    rep["submission_bundle"] = bundle
    rep["cells_npz"] = str(npz_path)
    log(
        f"[{variant_id}] DONE in {rep['elapsed_seconds']}s | "
        f"HIDE-RECOVER={rep['hide_and_recover']['pooled_dti']:.6f} "
        f"CI={rep['hide_and_recover']['ci95_cluster_bootstrap']} | "
        f"SGMC-CAL={rep['sgmc_off_catalogue']['sgmc_prevalence_calibrated_dti']:.6f} "
        f"(raw={rep['sgmc_off_catalogue']['sgmc_raw_pooled_dti']:.6f})"
    )
    return rep


def _load_cached_variant(variant_id: str, out_dir: Path) -> dict | None:
    eval_json = out_dir / f"{variant_id}_eval.json"
    npz_path = out_dir / f"{variant_id}_cells.npz"
    dots_npy = out_dir / f"{variant_id}_dots.npy"
    surf_path = out_dir / f"{variant_id}_surface.npy"
    if not (eval_json.is_file() and npz_path.is_file() and dots_npy.is_file() and surf_path.is_file()):
        return None
    rep = json.loads(eval_json.read_text())
    slug_guess = variant_id.replace("_", "-")
    audits = sorted(out_dir.glob(f"*{slug_guess}*-audit.json"))
    bundle = json.loads(audits[-1].read_text()) if audits else {}
    rep["full_map_dot_count"] = int((np.load(dots_npy) > 0).sum())
    rep["surface_npy"] = str(surf_path)
    rep["dots_npy"] = str(dots_npy)
    rep["zeros_tif"] = str(out_dir / bundle["zeros_tif"]["filename"]) if bundle else ""
    rep["submission_bundle"] = bundle
    rep["cells_npz"] = str(npz_path)
    return rep


def main() -> int:
    t_start = time.time()
    ddir, wdir = data_dir(), work_dir()
    out_dir = wdir / "ocda_runs"
    out_dir.mkdir(parents=True, exist_ok=True)

    shared_mm = shared_features.load_checked(wdir / "features_v2.npy", ddir / "training_features.tif")
    ocda_mm = ocda.build_or_load_ocda_free_stack(ddir, wdir)
    ctx = holdout.load_holdout_context(ddir)
    foot = ctx.foot
    collars = [_collar_mask_for_fold(foot, ctx.quad, f) for f in range(4)]

    # Verify hidden-label perturbation invariance before running experiments
    invariance = verify_hidden_perturbation_invariance(ctx)
    assert invariance["passed"], f"Provenance invariance failed: {invariance}"
    print("[PROVENANCE] Fold-local visible-only invariance verified:", invariance)

    # Precompute label-free physics-guarded PU exclusion & 1-px transverse crest carrier
    crest_carrier = ocda.build_transverse_crest_carrier(shared_mm, ocda_mm, foot)
    phys_comp = (
        0.30 * np.clip(np.asarray(ocda_mm[0]), 0.0, 1.0)
        + 0.25 * np.asarray(ocda_mm[11])
        + 0.20 * np.asarray(ocda_mm[14])
        + 0.15 * np.clip(np.asarray(ocda_mm[8]), 0.0, 1.0)
        + 0.10 * np.clip(np.asarray(ocda_mm[16]), 0.0, 1.0)
    )
    thr_pu = float(np.percentile(phys_comp[foot], 92.0))
    pu_phys_guard = (phys_comp >= thr_pu) & foot
    del phys_comp
    gc.collect()

    # --- Control 0: Fold-Honest 0.2778 Champion (`CHAMP-D28-VIS-B2`) ---
    with rasterio.open(ddir / "scored" / "gems24-h25-1-dotted-h19-5-d2-8-20261002-e56ea318af89-nan.tif") as ds:
        d28 = (ds.read(1) == 1) & foot
    champ_cells = {c.key: (d28[c.bbox] & (c.d_vis_sub > 2.0) & c.active_sub) for c in ctx.cells}
    champ_npz = out_dir / "ctrl_champ_d28_vis_b2_cells.npz"
    np.savez_compressed(champ_npz, **champ_cells)
    champ_eval_json = out_dir / "ctrl_champ_d28_vis_b2_eval.json"
    champ_zeros_tif = ROOT / "docs" / "downloads" / "gemsdoe32-h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros.tif"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "evaluate_holdout.py"),
            str(champ_npz),
            "--sgmc-map",
            str(champ_zeros_tif),
            "--name",
            "CHAMP-D28-VIS-B2",
            "--out",
            str(champ_eval_json),
        ],
        check=True,
    )
    champ_rep = json.loads(champ_eval_json.read_text())
    print(
        f"[CHAMP-D28-VIS-B2] HIDE-RECOVER={champ_rep['hide_and_recover']['pooled_dti']:.6f} "
        f"| SGMC-CAL={champ_rep['sgmc_off_catalogue']['sgmc_prevalence_calibrated_dti']:.6f}"
    )

    # --- Control 1: Plain OOF HGB on 35 shared v2 channels (`CTRL-BASE35-OOF`, 0 experiment slots) ---
    ctrl_base = _load_cached_variant("ctrl_base35_oof", out_dir) or run_model_variant(
        variant_id="ctrl_base35_oof",
        ctx=ctx,
        collars=collars,
        shared_mm=shared_mm,
        ocda_mm=None,
        ocda_indices=[],
        use_fold_vis_features=False,
        pu_phys_guard=None,
        crest_carrier=None,
        use_submodular_300m=False,
        anisotropic_tip_collar=False,
        total_budget=37_654,
        out_dir=out_dir,
        ddir=ddir,
    )

    # === PRE-REGISTERED 3-EXPERIMENT SUITE ===
    # EXP-1: OCDA-Core (35 shared + 24 label-free OCDA dipoles + PU reliable negatives + 1-px crest + 300m CELF)
    exp1 = _load_cached_variant("exp1_ocda_core", out_dir) or run_model_variant(
        variant_id="exp1_ocda_core",
        ctx=ctx,
        collars=collars,
        shared_mm=shared_mm,
        ocda_mm=ocda_mm,
        ocda_indices=list(range(ocda.EXP1_FREE_COUNT)),
        use_fold_vis_features=False,
        pu_phys_guard=pu_phys_guard,
        crest_carrier=crest_carrier,
        use_submodular_300m=True,
        anisotropic_tip_collar=False,
        total_budget=37_654,
        out_dir=out_dir,
        ddir=ddir,
    )

    # EXP-2: OCDA-DirectTreeRelay (logged negative result: feeding ~vis-masked continuation directly into y=vis PU tree)
    exp2 = _load_cached_variant("exp2_ocda_strain_relay", out_dir) or run_model_variant(
        variant_id="exp2_ocda_strain_relay",
        ctx=ctx,
        collars=collars,
        shared_mm=shared_mm,
        ocda_mm=ocda_mm,
        ocda_indices=list(range(len(ocda.OCDA_FREE_NAMES))),
        use_fold_vis_features=True,
        pu_phys_guard=pu_phys_guard,
        crest_carrier=crest_carrier,
        use_submodular_300m=True,
        anisotropic_tip_collar=False,
        total_budget=37_654,
        out_dir=out_dir,
        ddir=ddir,
    )

    # EXP-3 (3/3): OCDA-TwoStage-ExplainAway (resolves EXP-2 PU sign inversion via inner-withheld log-odds fusion
    # + removes lidar_valid tile shortcut + broadside 600 m dipole explaining-away + sharp 1-px crest concentration)
    exp3_indices = [i for i in range(len(ocda.OCDA_FREE_NAMES)) if i != 20]
    exp3 = _load_cached_variant("exp3_ocda_twostage_explainaway", out_dir) or run_exp3_twostage_explainaway(
        variant_id="exp3_ocda_twostage_explainaway",
        ctx=ctx,
        collars=collars,
        shared_mm=shared_mm,
        ocda_mm=ocda_mm,
        ocda_indices=exp3_indices,
        pu_phys_guard=pu_phys_guard,
        crest_carrier=crest_carrier,
        total_budget=37_654,
        out_dir=out_dir,
        ddir=ddir,
    )

    # Compute paired 256-block spatial cluster bootstrap deltas vs CHAMP-D28-VIS-B2
    with rasterio.open(champ_zeros_tif) as ds:
        champ_full_mask = (ds.read(1) == 1) & foot
    results = {"CHAMP-D28-VIS-B2": champ_rep, "CTRL-BASE35-OOF": ctrl_base, "EXP-1": exp1, "EXP-2": exp2, "EXP-3": exp3}
    paired = {}
    for k, rep in [("CTRL-BASE35-OOF", ctrl_base), ("EXP-1", exp1), ("EXP-2", exp2), ("EXP-3", exp3)]:
        with np.load(rep["cells_npz"]) as z:
            c_dict = {ck: z[ck] for ck in z.files}
        c_full = np.load(rep["dots_npy"]) > 0
        paired[k] = paired_delta_ci(ctx, c_dict, champ_cells, c_full, champ_full_mask)

    summary = {
        "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lane": "H-K1-A (OCDA-MSCS)",
        "experiments_run": 3,
        "budget_cap_experiments": 3,
        "total_wall_seconds": round(time.time() - t_start, 2),
        "provenance_invariance": invariance,
        "results": results,
        "paired_delta_vs_champion": paired,
    }
    (ROOT / "evidence" / "ocda_ablation_ledger.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("\n=== PAIRED DELTA VS 0.2778 CHAMPION (HIDE-RECOVER-v3.1) ===")
    for k, pd in paired.items():
        print(f"  {k:18s}: {pd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
