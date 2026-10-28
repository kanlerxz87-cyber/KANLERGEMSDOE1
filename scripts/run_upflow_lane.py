#!/usr/bin/env python3
"""Execute the pre-registered 3-experiment Lane H-K1-B (GEOALIGN-UPFLOW) suite.

Pre-registration: docs/research/hypotheses-upflow-20261028.md.
Protocol: reuse shared gems32.features / evaluate_holdout / submission_writer;
fold-local training with 1.5 km collar; every catalogue-derived feature from
cell.visible_full only (perturbation-invariance gated); <=3 experiments;
paired 95% CIs vs the fold-honest champion control.

  EXP-1 (slot 1/3): unsupervised alignment surface (H-K1B-1), zero training.
  EXP-2 (slot 2/3): OOF PU-HGB on shared35 + 12 upflow + 3 fold-visible (H-K1B-2).
  EXP-3 (slot 3/3): fixed-weight fusion of cached EXP-2 posterior with an
          inner-withheld label-free logistic + flank/crest/collar (H-K1B-3).
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
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems32 import features as shared_features  # noqa: E402
from gems32 import holdout  # noqa: E402
from gems32.paths import data_dir, work_dir  # noqa: E402
from kanler import ocda as ocda_pack  # noqa: E402 (packer reuse, not a fork)
from kanler import upflow  # noqa: E402

TOTAL_BUDGET = 37_654
EXTRA_NAMES = ["fold_vis_d_vis", "fold_vis_align_far", "fold_vis_thermal_far"]


def _collar_mask_for_fold(foot: np.ndarray, quad: np.ndarray, fold: int) -> np.ndarray:
    return (ndi.binary_dilation((quad == fold) & foot, iterations=holdout.COLLAR_PX)) & foot


def _gather(shared_mm, up_mm, extra_2d, ys, xs) -> np.ndarray:
    n_sh = shared_mm.shape[2]
    n_up = up_mm.shape[0]
    n_ex = len(extra_2d)
    X = np.empty((ys.size, n_sh + n_up + n_ex), dtype=np.float32)
    X[:, :n_sh] = shared_mm[ys, xs, :]
    for j in range(n_up):
        X[:, n_sh + j] = up_mm[j, ys, xs]
    for k, arr in enumerate(extra_2d):
        X[:, n_sh + n_up + k] = arr[ys, xs]
    np.nan_to_num(X, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    return X


def _predict_bbox_probs(clf, bbox, foot_full, shared_mm, up_mm, extra_2d, strip_rows: int = 256):
    rs, cs = bbox
    r0, r1, c0, c1 = int(rs.start), int(rs.stop), int(cs.start), int(cs.stop)
    out = np.zeros((r1 - r0, c1 - c0), dtype=np.float32)
    n_sh = shared_mm.shape[2]
    n_up = up_mm.shape[0]
    n_tot = n_sh + n_up + len(extra_2d)
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
        for j in range(n_up):
            X[:, n_sh + j] = up_mm[j, gy, gx]
        for k, arr in enumerate(extra_2d):
            X[:, n_sh + n_up + k] = arr[gy, gx]
        np.nan_to_num(X, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        out[vy + (s0 - r0), vx] = clf.predict_proba(X)[:, 1].astype(np.float32)
        del X
    return out


def verify_upflow_invariance(ctx) -> dict:
    c0 = ctx.cells[0]
    a = upflow.compute_fold_visible_upflow(c0.visible_full, ctx.foot, None)
    b = upflow.compute_fold_visible_upflow(c0.visible_full.copy(), ctx.foot, None)
    overlap = 0
    for c in ctx.cells:
        ty, tx = c.truth_coords
        r0, c0o = int(c.bbox[0].start), int(c.bbox[1].start)
        overlap += int(c.visible_full[ty + r0, tx + c0o].sum())
    md = float(max(np.max(np.abs(a[k] - b[k])) for k in a))
    return {"passed": bool(overlap == 0 and md == 0.0),
            "visible_x_withheld_pixel_overlap_across_8_cells": overlap,
            "recomputation_max_abs_diff": md}


def run_canaries(ctx, shared_mm, up_mm, seed: int = 20261028) -> dict:
    """Single-feature withheld-fold AUCs: 35 shared + 12 upflow + 3 fold-visible."""
    rng = np.random.default_rng(seed)
    pos_scores: dict[str, list[np.ndarray]] = {}
    neg_scores: dict[str, list[np.ndarray]] = {}
    names = list(shared_features.CHANNELS) + list(upflow.UPFLOW_FREE_NAMES) + list(EXTRA_NAMES)
    for n in names:
        pos_scores[n] = []
        neg_scores[n] = []
    n_pos = 0
    n_neg = 0
    for cell in ctx.cells:
        sl = cell.bbox
        ty, tx = cell.truth_coords
        gy = ty + int(sl[0].start)
        gx = tx + int(sl[1].start)
        fv = upflow.compute_fold_visible_upflow(cell.visible_full, ctx.foot, None)
        neg_pool = cell.active_sub & ~cell.visible_sub if cell.visible_sub is not None else cell.active_sub
        # active negatives: inside domain, not visible, not withheld truth
        truth_sub = np.zeros(cell.active_sub.shape, bool)
        truth_sub[ty, tx] = True
        neg_pool = cell.active_sub & ~truth_sub
        if cell.visible_sub is not None:
            neg_pool = neg_pool & ~cell.visible_sub
        ny0, nx0 = np.nonzero(neg_pool)
        k_neg = min(int(ty.size) * 4, int(ny0.size))
        pick = rng.choice(ny0.size, size=k_neg, replace=False)
        ngy = ny0[pick] + int(sl[0].start)
        ngx = nx0[pick] + int(sl[1].start)
        n_pos += int(ty.size)
        n_neg += int(k_neg)
        for j, nm in enumerate(shared_features.CHANNELS):
            ch = np.asarray(shared_mm[:, :, j])
            pos_scores[nm].append(ch[gy, gx].astype(np.float64))
            neg_scores[nm].append(ch[ngy, ngx].astype(np.float64))
        for j, nm in enumerate(upflow.UPFLOW_FREE_NAMES):
            ch = np.asarray(up_mm[j])
            pos_scores[nm].append(ch[gy, gx].astype(np.float64))
            neg_scores[nm].append(ch[ngy, ngx].astype(np.float64))
        ex_map = {"fold_vis_d_vis": fv["d_vis"], "fold_vis_align_far": fv["align_far"],
                  "fold_vis_thermal_far": fv["thermal_far"]}
        for nm, arr in ex_map.items():
            pos_scores[nm].append(arr[gy, gx].astype(np.float64))
            neg_scores[nm].append(arr[ngy, ngx].astype(np.float64))
        del fv
        gc.collect()
    feats = []
    for nm in names:
        p = np.concatenate(pos_scores[nm])
        q = np.concatenate(neg_scores[nm])
        y = np.concatenate([np.ones(p.size), np.zeros(q.size)])
        s = np.concatenate([p, q])
        try:
            auc = float(roc_auc_score(y, s))
        except ValueError:
            auc = 0.5
        sym = max(auc, 1.0 - auc)
        grp = ("shared_v2" if nm in set(shared_features.CHANNELS)
               else ("upflow_free" if nm in set(upflow.UPFLOW_FREE_NAMES) else "upflow_fold_visible_only"))
        feats.append({"group": grp, "name": nm, "raw_auc": round(auc, 6),
                      "symmetric_auc": round(sym, 6), "leakage_flag_gt_0p90": bool(sym > 0.90)})
    feats.sort(key=lambda r: -r["symmetric_auc"])
    mx = feats[0]
    return {"evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scope": "Strict withheld-fold positives vs active negatives across all 8 PreparedCells (GEMSDOE32-HIDE-RECOVER-v3.1)",
            "n_withheld_positive_evaluations": n_pos, "n_active_negative_evaluations": n_neg,
            "total_features_tested": len(feats), "threshold_symmetric_auc": 0.90,
            "n_flagged": sum(1 for f in feats if f["leakage_flag_gt_0p90"]),
            "passed": bool(all(not f["leakage_flag_gt_0p90"] for f in feats)),
            "max_symmetric_auc": mx["symmetric_auc"], "max_feature": mx["name"],
            "top_12_features": feats[:12], "features": feats}


def _fit_hgb(visible_mask, fold, seed_val, collars, foot, shared_mm, up_mm, extra_2d, pu_guard) -> HistGradientBoostingClassifier:
    rng = np.random.default_rng(seed_val)
    train_dom = foot & ~collars[fold]
    py, px = np.nonzero(visible_mask & train_dom)
    d_vis = ndi.distance_transform_edt(~visible_mask)
    neg_pool = train_dom & (d_vis > 4.0) & ~pu_guard
    ny, nx = np.nonzero(neg_pool)
    n_neg = min(int(py.size) * 4, int(ny.size))
    pick = rng.choice(ny.size, size=n_neg, replace=False)
    ys = np.concatenate([py, ny[pick]])
    xs = np.concatenate([px, nx[pick]])
    y_lbl = np.concatenate([np.ones(py.size, np.int32), np.zeros(n_neg, np.int32)])
    perm = rng.permutation(ys.size)
    X = _gather(shared_mm, up_mm, extra_2d, ys[perm], xs[perm])
    clf = HistGradientBoostingClassifier(max_iter=220, learning_rate=0.055, max_leaf_nodes=31,
                                         min_samples_leaf=80, l2_regularization=2.5,
                                         early_stopping=True, validation_fraction=0.1,
                                         n_iter_no_change=15, random_state=seed_val)
    clf.fit(X, y_lbl[perm])
    del X
    return clf


def _emit_and_eval(variant_id, cand_by_cell, full_dots, full_surface_norm, out_dir, ddir, t0, log=print) -> dict:
    npz_path = out_dir / f"{variant_id}_cells.npz"
    np.savez_compressed(npz_path, **{k: np.asarray(v, dtype=bool) for k, v in cand_by_cell.items()})
    surf_path = out_dir / f"{variant_id}_surface.npy"
    np.save(surf_path, full_surface_norm.astype(np.float32))
    dots_npy = out_dir / f"{variant_id}_dots.npy"
    np.save(dots_npy, (np.asarray(full_dots, dtype=bool)).astype(np.float32))
    note = f"KANLERGEMSDOE1 {variant_id} GEOALIGN-UPFLOW ({int(np.asarray(full_dots).sum())}d)"[:140]
    sub = subprocess.run([sys.executable, str(ROOT / "scripts" / "submission_writer.py"), str(dots_npy),
                          "--slug", variant_id.replace("_", "-"), "--candidate-id", variant_id,
                          "--note", note, "--out-dir", str(out_dir)],
                         check=True, capture_output=True, text=True)
    bundle = json.loads(sub.stdout)
    zeros_tif = out_dir / bundle["zeros_tif"]["filename"]
    eval_json = out_dir / f"{variant_id}_eval.json"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate_holdout.py"), str(npz_path),
                    "--sgmc-map", str(zeros_tif), "--name", variant_id, "--out", str(eval_json)], check=True)
    rep = json.loads(eval_json.read_text())
    rep["elapsed_seconds"] = round(time.time() - t0, 2)
    rep["full_map_dot_count"] = int(np.asarray(full_dots).sum())
    rep["surface_npy"] = str(surf_path)
    rep["dots_npy"] = str(dots_npy)
    rep["zeros_tif"] = str(zeros_tif)
    rep["submission_bundle"] = bundle
    rep["cells_npz"] = str(npz_path)
    log(f"[{variant_id}] HIDE-RECOVER={rep['hide_and_recover']['pooled_dti']:.6f} "
        f"CI={rep['hide_and_recover']['ci95_cluster_bootstrap']} | "
        f"SGMC-CAL={rep['sgmc_off_catalogue']['sgmc_prevalence_calibrated_dti']:.6f}")
    return rep


def run_exp1(ctx, collars, belief, crest, belief_full, crest_full, out_dir, ddir, log=print) -> dict:
    t0 = time.time()
    tot_foot = float(ctx.foot.sum())
    cand = {}
    for i, cell in enumerate(ctx.cells):
        sl = cell.bbox
        b = np.asarray(belief[sl]).astype(np.float32) ** 1.15
        cr = np.asarray(crest[sl]).astype(np.float32)
        b = (b * (0.35 + 0.65 * cr)).astype(np.float32)
        allowed = cell.active_sub & (cell.d_vis_sub > 2.0)
        q_in = (ctx.quad[sl] == cell.fold) & ctx.foot[sl]
        budget = int(round(TOTAL_BUDGET * (float(q_in.sum()) / tot_foot)))
        dots = ocda_pack.pack_submodular_300m(np.where(allowed, b, 0.0), allowed,
                                              budget=budget, min_dist_px=2.83, pool_mult=26)
        cand[cell.key] = dots & cell.active_sub
        log(f"  [exp1] cell {i+1}/8 {cell.key}: dots={int(cand[cell.key].sum())}")
        del b, cr
        gc.collect()
    bf = (np.asarray(belief_full).astype(np.float32)) ** 1.15 * (
        0.35 + 0.65 * np.asarray(crest_full).astype(np.float32))
    d_cat = ndi.distance_transform_edt(~ctx.labels).astype(np.float32)
    allowed_full = ctx.foot & (~ctx.labels) & (d_cat > 2.0)
    full_dots = ocda_pack.pack_submodular_300m(np.where(allowed_full, bf, 0.0), allowed_full,
                                               budget=TOTAL_BUDGET, min_dist_px=2.83, pool_mult=26)
    mx = float(bf[ctx.foot].max()) or 1.0
    surf_n = np.where(ctx.foot, bf / mx, 0.0).astype(np.float32)
    del bf
    return _emit_and_eval("exp1_upflow_align", cand, full_dots, surf_n, out_dir, ddir, t0, log)


def run_exp2(ctx, collars, shared_mm, up_mm, belief_full, crest_full, pu_guard, out_dir, ddir, log=print) -> dict:
    t0 = time.time()
    tot_foot = float(ctx.foot.sum())
    quad_boxes = []
    for f in range(4):
        qy, qx = np.nonzero((ctx.quad == f) & ctx.foot)
        quad_boxes.append((slice(int(qy.min()), int(qy.max()) + 1), slice(int(qx.min()), int(qx.max()) + 1)))
    cand = {}
    prob_cache: dict[str, np.ndarray] = {}
    for i, cell in enumerate(ctx.cells):
        fv = upflow.compute_fold_visible_upflow(cell.visible_full, ctx.foot, up_mm)
        extra = [fv["d_vis"], fv["align_far"], fv["thermal_far"]]
        clf = _fit_hgb(cell.visible_full, cell.fold, 202610 + 17 * cell.seed + cell.fold,
                       collars, ctx.foot, shared_mm, up_mm, extra, pu_guard)
        prob = _predict_bbox_probs(clf, cell.bbox, ctx.foot, shared_mm, up_mm, extra)
        prob_cache[cell.key] = prob.copy()
        sl = cell.bbox
        cr = np.asarray(crest_full[sl]).astype(np.float32)
        b = (np.clip(prob, 0.0, 1.0).astype(np.float32) ** 1.15) * (0.35 + 0.65 * cr)
        allowed = cell.active_sub & (cell.d_vis_sub > 2.0)
        q_in = (ctx.quad[sl] == cell.fold) & ctx.foot[sl]
        budget = int(round(TOTAL_BUDGET * (float(q_in.sum()) / tot_foot)))
        dots = ocda_pack.pack_submodular_300m(np.where(allowed, b, 0.0), allowed,
                                              budget=budget, min_dist_px=2.83, pool_mult=26)
        cand[cell.key] = dots & cell.active_sub
        log(f"  [exp2] cell {i+1}/8 {cell.key}: dots={int(cand[cell.key].sum())}")
        del clf, prob, b, cr, fv, extra
        gc.collect()
    np.savez_compressed(out_dir / "exp2_upflow_oof_prob_cache.npz", **prob_cache)
    full_prob = np.zeros(ctx.foot.shape, dtype=np.float32)
    fv_full = upflow.compute_fold_visible_upflow(ctx.labels, ctx.foot, up_mm)
    extra_full = [fv_full["d_vis"], fv_full["align_far"], fv_full["thermal_far"]]
    for f in range(4):
        clf = _fit_hgb(ctx.labels, f, 202690 + f, collars, ctx.foot, shared_mm, up_mm, extra_full, pu_guard)
        p = _predict_bbox_probs(clf, quad_boxes[f], ctx.foot, shared_mm, up_mm, extra_full)
        qm = (ctx.quad[quad_boxes[f]] == f) & ctx.foot[quad_boxes[f]]
        full_prob[quad_boxes[f]] = np.where(qm, p, full_prob[quad_boxes[f]])
        del clf, p
        gc.collect()
    np.save(out_dir / "exp2_upflow_oof_full_prob.npy", full_prob)
    bf = (np.clip(full_prob, 0.0, 1.0) ** 1.15) * (0.35 + 0.65 * np.asarray(crest_full).astype(np.float32))
    d_cat = ndi.distance_transform_edt(~ctx.labels).astype(np.float32)
    allowed_full = ctx.foot & (~ctx.labels) & (d_cat > 2.0)
    full_dots = ocda_pack.pack_submodular_300m(np.where(allowed_full, bf, 0.0), allowed_full,
                                               budget=TOTAL_BUDGET, min_dist_px=2.83, pool_mult=26)
    mx = float(bf[ctx.foot].max()) or 1.0
    surf_n = np.where(ctx.foot, bf / mx, 0.0).astype(np.float32)
    del bf, full_prob
    return _emit_and_eval("exp2_upflow_oof", cand, full_dots, surf_n, out_dir, ddir, t0, log)


def _inner_label_free_calibration(visible_mask, fold, seed_val, collars, foot, up_mm) -> tuple:
    """Logistic weights on label-free surfaces; labels = inner 20% hidden components."""
    rng = np.random.default_rng(seed_val)
    train_dom = foot & ~collars[fold]
    vis_tr = np.asarray(visible_mask, bool) & train_dom
    lbl_comp, n_comp = ndi.label(vis_tr, structure=np.ones((3, 3), np.int8))
    if n_comp < 10:
        return (0.0, 0.5, 0.5, 0.5, 0.0)
    sizes = np.bincount(lbl_comp.ravel())
    sizes[0] = 0
    comp_ids = np.nonzero(sizes > 0)[0]
    perm_c = rng.permutation(comp_ids)
    target = 0.20 * float(vis_tr.sum())
    k_take = min(int(np.searchsorted(np.cumsum(sizes[perm_c]), target)) + 1, perm_c.size - 4)
    inner_hid = np.isin(lbl_comp, perm_c[:max(k_take, 1)]) & train_dom
    inner_vis_full = (np.asarray(visible_mask, bool) & ~train_dom) | (vis_tr & ~inner_hid)
    fv = upflow.compute_fold_visible_upflow(inner_vis_full, foot, up_mm)
    py, px = np.nonzero(inner_hid)
    d_in = ndi.distance_transform_edt(~inner_vis_full)
    neg_cand = train_dom & ~inner_vis_full & ~inner_hid & (d_in > 2.0)
    ny, nx = np.nonzero(neg_cand)
    k_n = min(int(py.size) * 6, int(ny.size))
    pick = rng.choice(ny.size, size=k_n, replace=False)
    ys = np.concatenate([py, ny[pick]])
    xs = np.concatenate([px, nx[pick]])
    y_cal = np.concatenate([np.ones(py.size, np.int32), np.zeros(k_n, np.int32)])
    Z = np.column_stack([fv["align_far"][ys, xs], fv["thermal_far"][ys, xs],
                         np.asarray(up_mm[9], dtype=np.float32)[ys, xs]]).astype(np.float64)
    lr = LogisticRegression(C=1.0, max_iter=300)
    lr.fit(Z, y_cal)
    w = [float(v) for v in lr.coef_[0]]
    return (0.0, max(w[0], 0.0), max(w[1], 0.0), max(w[2], 0.0), float(lr.intercept_[0]))

def run_exp3(ctx, collars, up_mm, crest_full, out_dir, ddir, log=print) -> dict:
    t0 = time.time()
    tot_foot = float(ctx.foot.sum())
    prob_cache = np.load(out_dir / "exp2_upflow_oof_prob_cache.npz")
    full_prob = np.load(out_dir / "exp2_upflow_oof_full_prob.npy").astype(np.float32)
    weights: dict[str, list[float]] = {}
    cand = {}
    for i, cell in enumerate(ctx.cells):
        sl = cell.bbox
        w = _inner_label_free_calibration(cell.visible_full, cell.fold,
                                          202780 + 19 * cell.seed + cell.fold, collars, ctx.foot, up_mm)
        weights[cell.key] = [round(v, 4) for v in w]
        _, wa, wt, we, b0 = w
        fv = upflow.compute_fold_visible_upflow(cell.visible_full, ctx.foot, up_mm)
        eta_free = (b0 + wa * fv["align_far"][sl] + wt * fv["thermal_far"][sl]
                    + we * np.asarray(up_mm[9], dtype=np.float32)[sl]).astype(np.float32)
        p2 = np.clip(np.asarray(prob_cache[cell.key], dtype=np.float32), 1e-4, 1 - 1e-4)
        eta = 0.5 * np.log(p2 / (1.0 - p2)) + 0.5 * eta_free
        post = (1.0 / (1.0 + np.exp(-np.clip(eta, -12, 12)))).astype(np.float32)
        tip_like = np.clip(fv["align_far"][sl].astype(np.float32), 0, 1)
        flank = np.where(tip_like >= 0.18, 1.0,
                         0.42 + 0.58 * np.clip((cell.d_vis_sub - 2.0) / 4.0, 0, 1)).astype(np.float32)
        cr = np.asarray(crest_full[sl]).astype(np.float32)
        belief = (np.power(np.maximum(post, 1e-6), 1.10) * flank
                  * np.power(np.maximum(cr, 0.0), 2.2)).astype(np.float32)
        tip_entry = (tip_like >= 0.26) & (cr >= 0.76) & (cell.d_vis_sub > 1.0)
        allowed = cell.active_sub & (cell.d_vis_sub > 2.24) | (cell.active_sub & tip_entry)
        q_in = (ctx.quad[sl] == cell.fold) & ctx.foot[sl]
        budget = int(round(TOTAL_BUDGET * (float(q_in.sum()) / tot_foot)))
        dots = ocda_pack.pack_submodular_300m(np.where(allowed, belief, 0.0), allowed,
                                              budget=budget, min_dist_px=2.83, pool_mult=28)
        cand[cell.key] = dots & cell.active_sub
        log(f"  [exp3] cell {i+1}/8 {cell.key}: dots={int(cand[cell.key].sum())} w={weights[cell.key]}")
        del fv, eta_free, p2, eta, post, tip_like, flank, cr, belief
        gc.collect()
    fv_full = upflow.compute_fold_visible_upflow(ctx.labels, ctx.foot, up_mm)
    d_cat = ndi.distance_transform_edt(~ctx.labels).astype(np.float32)
    wq = []
    for f in range(4):
        wq.append(_inner_label_free_calibration(ctx.labels, f, 202880 + f, collars, ctx.foot, up_mm))
    wa_m = float(np.mean([w[1] for w in wq]))
    wt_m = float(np.mean([w[2] for w in wq]))
    we_m = float(np.mean([w[3] for w in wq]))
    b0_m = float(np.mean([w[4] for w in wq]))
    eta_free = (b0_m + wa_m * fv_full["align_far"] + wt_m * fv_full["thermal_far"]
                + we_m * np.asarray(up_mm[9], dtype=np.float32)).astype(np.float32)
    p2 = np.clip(full_prob, 1e-4, 1 - 1e-4)
    post = (1.0 / (1.0 + np.exp(-np.clip(0.5 * np.log(p2 / (1.0 - p2)) + 0.5 * eta_free, -12, 12)))
            ).astype(np.float32)
    tip_like = np.clip(fv_full["align_far"], 0, 1).astype(np.float32)
    flank = np.where(tip_like >= 0.18, 1.0,
                     0.42 + 0.58 * np.clip((d_cat - 2.0) / 4.0, 0, 1)).astype(np.float32)
    crf = np.asarray(crest_full).astype(np.float32)
    bf = (np.power(np.maximum(post, 1e-6), 1.10) * flank * np.power(np.maximum(crf, 0.0), 2.2)
          ).astype(np.float32)
    tip_entry = (tip_like >= 0.26) & (crf >= 0.76) & (d_cat > 1.0)
    allowed_full = (ctx.foot & (d_cat > 2.24)) | (ctx.foot & tip_entry)
    allowed_full = allowed_full & (~ctx.labels)
    full_dots = ocda_pack.pack_submodular_300m(np.where(allowed_full, bf, 0.0), allowed_full,
                                               budget=TOTAL_BUDGET, min_dist_px=2.83, pool_mult=28)
    mx = float(bf[ctx.foot].max()) or 1.0
    surf_n = np.where(ctx.foot, bf / mx, 0.0).astype(np.float32)
    rep = _emit_and_eval("exp3_upflow_twostage", cand, full_dots, surf_n, out_dir, ddir, t0, log)
    rep["learned_stage2_weights"] = weights
    rep["full_map_mean_weights"] = [round(wa_m, 4), round(wt_m, 4), round(we_m, 4), round(b0_m, 4)]
    return rep


def paired_delta_ci(ctx, cand_by_cell, ref_by_cell, cand_full_mask, ref_full_mask) -> dict:
    hr_c = holdout.evaluate_hide_and_recover(cand_by_cell, ctx, b_visible_px=0.0, name="cand")
    hr_r = holdout.evaluate_hide_and_recover(ref_by_cell, ctx, b_visible_px=0.0, name="ref")
    d_hr = np.asarray(hr_c["_boots"], dtype=np.float64) - np.asarray(hr_r["_boots"], dtype=np.float64)
    hr_lo, hr_hi = np.percentile(d_hr, [2.5, 97.5])
    sg_c = holdout.evaluate_sgmc_with_ci(cand_full_mask, ctx, name="cand")
    sg_r = holdout.evaluate_sgmc_with_ci(ref_full_mask, ctx, name="ref")
    d_sg = (np.asarray(sg_c["_cal_boots"], dtype=np.float64)
            - np.asarray(sg_r["_cal_boots"], dtype=np.float64))
    sg_lo, sg_hi = np.percentile(d_sg, [2.5, 97.5])
    return {
        "hide_recover": {
            "cand_pooled_dti": round(float(hr_c["pooled_dti"]), 6),
            "ref_pooled_dti": round(float(hr_r["pooled_dti"]), 6),
            "delta_dti": round(float(hr_c["pooled_dti"] - hr_r["pooled_dti"]), 6),
            "delta_ci95": [round(float(hr_lo), 6), round(float(hr_hi), 6)],
            "prob_cand_gt_ref": round(float((d_hr > 0).mean()), 4)},
        "sgmc_calibrated": {
            "cand_cal_dti": round(float(sg_c["sgmc_prevalence_calibrated_dti"]), 6),
            "ref_cal_dti": round(float(sg_r["sgmc_prevalence_calibrated_dti"]), 6),
            "delta_dti": round(float(sg_c["sgmc_prevalence_calibrated_dti"]
                                     - sg_r["sgmc_prevalence_calibrated_dti"]), 6),
            "delta_ci95": [round(float(sg_lo), 6), round(float(sg_hi), 6)],
            "prob_cand_gt_ref": round(float((d_sg > 0).mean()), 4)}}


def main() -> int:
    t_start = time.time()
    ddir, wdir = data_dir(), work_dir()
    out_dir = wdir / "upflow_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    shared_mm = shared_features.load_checked(wdir / "features_v2.npy",
                                             ddir / "training_features.tif")
    ctx = holdout.load_holdout_context(ddir)
    foot = ctx.foot
    with rasterio.open(ddir / "sample_submission.tif") as ds:
        transform = ds.transform
    up_mm = upflow.build_or_load_upflow_stack(ddir, wdir, shared_mm, foot, transform)
    collars = [_collar_mask_for_fold(foot, ctx.quad, f) for f in range(4)]
    inv = verify_upflow_invariance(ctx)
    assert inv["passed"], f"Provenance invariance failed: {inv}"
    print("[PROVENANCE] Fold-local visible-only invariance verified:", inv, flush=True)
    can = run_canaries(ctx, shared_mm, up_mm)
    (ROOT / "evidence" / "upflow_leakage_canaries.json").write_text(
        json.dumps(can, indent=2) + "\n")
    print(f"[CANARY] {can['total_features_tested']} features, max_sym_AUC={can['max_symmetric_auc']} "
          f"({can['max_feature']}), flagged={can['n_flagged']}", flush=True)
    assert can["passed"], "STOP: leakage canary flagged (AUC>0.90)"
    belief, crest = upflow.build_alignment_surface(up_mm, foot)
    phys = (np.asarray(up_mm[10], dtype=np.float32)
            + np.asarray(up_mm[4], dtype=np.float32))
    thr = float(np.percentile(phys[foot], 92.0))
    pu_guard = (phys >= thr) & foot
    del phys
    gc.collect()
    with rasterio.open(ddir / "scored" / "gems24-h25-1-dotted-h19-5-d2-8-20261002-e56ea318af89-nan.tif") as ds:
        d28 = (ds.read(1) == 1) & foot
    champ_cells = {c.key: (d28[c.bbox] & (c.d_vis_sub > 2.0) & c.active_sub) for c in ctx.cells}
    champ_npz = out_dir / "ctrl_champ_d28_vis_b2_cells.npz"
    np.savez_compressed(champ_npz, **champ_cells)
    champ_eval_json = out_dir / "ctrl_champ_d28_vis_b2_eval.json"
    champ_zeros = ROOT / "docs" / "downloads" / "gemsdoe32-h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros.tif"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate_holdout.py"), str(champ_npz),
                    "--sgmc-map", str(champ_zeros), "--name", "CHAMP-D28-VIS-B2",
                    "--out", str(champ_eval_json)], check=True)
    champ_rep = json.loads(champ_eval_json.read_text())
    print(f"[CHAMP] HIDE-RECOVER={champ_rep['hide_and_recover']['pooled_dti']:.6f} | "
          f"SGMC-CAL={champ_rep['sgmc_off_catalogue']['sgmc_prevalence_calibrated_dti']:.6f}", flush=True)
    e1 = run_exp1(ctx, collars, belief, crest, belief, crest, out_dir, ddir)
    e2 = run_exp2(ctx, collars, shared_mm, up_mm, belief, crest, pu_guard, out_dir, ddir)
    e3 = run_exp3(ctx, collars, up_mm, crest, out_dir, ddir)
    with rasterio.open(champ_zeros) as ds:
        champ_full = (ds.read(1) == 1) & foot
    results = {"CHAMP-D28-VIS-B2": champ_rep, "EXP-1": e1, "EXP-2": e2, "EXP-3": e3}
    paired = {}
    for k, rep in [("EXP-1", e1), ("EXP-2", e2), ("EXP-3", e3)]:
        with np.load(rep["cells_npz"]) as z:
            c_dict = {ck: np.asarray(z[ck]) for ck in z.files}
        c_full = np.load(rep["dots_npy"]) > 0
        paired[k] = paired_delta_ci(ctx, c_dict, champ_cells, c_full, champ_full)
    summary = {"evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "lane": "H-K1-B (GEOALIGN-UPFLOW)", "experiments_run": 3,
               "budget_cap_experiments": 3,
               "total_wall_seconds": round(time.time() - t_start, 2),
               "provenance_invariance": inv,
               "canaries": {"max_symmetric_auc": can["max_symmetric_auc"],
                            "max_feature": can["max_feature"],
                            "n_flagged": can["n_flagged"], "passed": can["passed"]},
               "results": results, "paired_delta_vs_champion": paired}
    (ROOT / "evidence" / "upflow_ablation_ledger.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print("\n=== PAIRED DELTA VS 0.2778 CHAMPION (HIDE-RECOVER-v3.1) ===")
    for k, pd in paired.items():
        print(f"  {k}: HR Δ={pd['hide_recover']['delta_dti']} "
              f"CI={pd['hide_recover']['delta_ci95']} P={pd['hide_recover']['prob_cand_gt_ref']} | "
              f"SGMC Δ={pd['sgmc_calibrated']['delta_dti']} "
              f"CI={pd['sgmc_calibrated']['delta_ci95']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
