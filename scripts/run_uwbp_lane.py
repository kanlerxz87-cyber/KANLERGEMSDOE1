#!/usr/bin/env python3
"""Execute the pre-registered 3-experiment UWBP-DRCS lane (`H-K1-B`, <= 3 experiments).

Pre-registered in `docs/research/hypotheses-20261028.md`:
  - EXP-B1 (`exp1_uwbp_deconf_pu`): 57 local/scale-free channels (18 UWBP + 24 deconfounded OCDA
    + 15 shared structural; raw geographic/elevation scalars excluded) + PU reliable-negative guard
    (`~pu_phys_guard`) + sharp 1-px crest carrier + 300 m CELF (`37,654` dots, `min_dist=2.83`).
  - EXP-B2 (`exp2_uwbp_drcs_dual`): Stage-2 inner-withheld log-odds continuation calibration
    (`0.0` hidden-label perturbation diff) + broadside flank explaining-away + Dual-Regime
    `M_struct` (`0.50 * h33a + 0.50 * uwbp_dual_prior`) synthesis + 300 m CELF (`37,654` dots).
  - EXP-B3 (`exp3_uwbp_drcs_dinkelbach`): Adds strike-steered hydrothermal conduit amplification
    (`H-K1-B3`: anisotropic thermal bridge x smectite clay-cap margin / magnetite-bleach+K/Th) +
    cost-sensitive Dinkelbach marginal-DTI submodular packing (`pack_dinkelbach_dti_300m`).

Reuses shared `scripts/submission_writer.py`, `scripts/evaluate_holdout.py`, and `gems32.holdout`
with 100% Zero-SGMC in feature construction, training, negative guarding, and inference.
"""
from __future__ import annotations

import gc
import json
import resource
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

from gems32 import features as shared_features  # noqa: E402
from gems32 import h33, holdout  # noqa: E402
from gems32.paths import data_dir, work_dir  # noqa: E402
from kanler import ocda, uwbp  # noqa: E402

TARGET_BUDGET = 37_654
TRAIN_POS_MAX = 45_000
TRAIN_NEG_MAX = 140_000

# Exclude index 20 (`ocda_lidar_valid_flag`) and index 4 (`ocda_local_elev_pct_2p5km`) from OCDA
OCDA_DECONF_MODEL_INDICES: tuple[int, ...] = tuple(
    idx for idx in uwbp.OCDA_DECONFOUNDED_INDICES if idx != 20
)


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def deconfounded_feature_names(include_vis_cont: bool) -> list[str]:
    names = list(uwbp.UWBP_FREE_NAMES)
    names.extend(ocda.OCDA_FREE_NAMES[i] for i in OCDA_DECONF_MODEL_INDICES)
    names.extend(f"shared_{shared_features.CHANNELS[i]}" for i in uwbp.SHARED_DECONFOUNDED_INDICES)
    if include_vis_cont:
        names.extend(ocda.OCDA_VIS_NAMES)
    return names


def extract_deconfounded_rows(
    rows: np.ndarray,
    cols: np.ndarray,
    uwbp_mm: np.ndarray,
    ocda_mm: np.ndarray,
    shared_mm: np.ndarray,
) -> np.ndarray:
    """Memory-frugal channel-by-channel point Gather -> `(len(rows), 57)` float32."""
    n_u = len(uwbp.UWBP_FREE_NAMES)
    n_o = len(OCDA_DECONF_MODEL_INDICES)
    n_s = len(uwbp.SHARED_DECONFOUNDED_INDICES)
    X = np.empty((rows.size, n_u + n_o + n_s), dtype=np.float32)

    col_idx = 0
    for i in range(n_u):
        X[:, col_idx] = uwbp_mm[i][rows, cols]
        col_idx += 1
    for i in OCDA_DECONF_MODEL_INDICES:
        X[:, col_idx] = ocda_mm[i][rows, cols]
        col_idx += 1
    for i in uwbp.SHARED_DECONFOUNDED_INDICES:
        X[:, col_idx] = shared_mm[rows, cols, i]
        col_idx += 1
    np.nan_to_num(X, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    return X


def fit_stage1_deconf_hgb(
    vis_pos_mask: np.ndarray,
    excl_vis_mask: np.ndarray,
    train_dom: np.ndarray,
    pu_phys_guard: np.ndarray,
    uwbp_mm: np.ndarray,
    ocda_mm: np.ndarray,
    shared_mm: np.ndarray,
    seed_val: int,
) -> HistGradientBoostingClassifier:
    rng = np.random.default_rng(seed_val)
    py, px = np.nonzero(vis_pos_mask & train_dom)
    if py.size > TRAIN_POS_MAX:
        sel = rng.choice(py.size, size=TRAIN_POS_MAX, replace=False)
        py, px = py[sel], px[sel]

    d_vis = ndi.distance_transform_edt(~excl_vis_mask)
    neg_pool = train_dom & (d_vis > 4.0) & (~pu_phys_guard)
    ny, nx = np.nonzero(neg_pool)
    n_neg = min(max(int(py.size) * 4, 60_000), TRAIN_NEG_MAX, int(ny.size))
    pick = rng.choice(ny.size, size=n_neg, replace=False)
    ny, nx = ny[pick], nx[pick]
    del d_vis, neg_pool

    ys = np.concatenate([py, ny])
    xs = np.concatenate([px, nx])
    y_lbl = np.concatenate([np.ones(py.size, dtype=np.int32), np.zeros(ny.size, dtype=np.int32)])
    perm = rng.permutation(ys.size)
    ys, xs, y_lbl = ys[perm], xs[perm], y_lbl[perm]

    X = extract_deconfounded_rows(ys, xs, uwbp_mm, ocda_mm, shared_mm)
    clf = HistGradientBoostingClassifier(
        max_iter=220,
        learning_rate=0.055,
        max_leaf_nodes=39,
        min_samples_leaf=80,
        l2_regularization=2.5,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=15,
        random_state=seed_val,
    )
    clf.fit(X, y_lbl)
    del X, y_lbl
    return clf


def predict_bbox_probs(
    clf: HistGradientBoostingClassifier,
    bbox: tuple[slice, slice],
    foot: np.ndarray,
    uwbp_mm: np.ndarray,
    ocda_mm: np.ndarray,
    shared_mm: np.ndarray,
    strip_rows: int = 384,
) -> np.ndarray:
    r0, r1 = int(bbox[0].start), int(bbox[0].stop)
    c0, c1 = int(bbox[1].start), int(bbox[1].stop)
    out = np.zeros((r1 - r0, c1 - c0), dtype=np.float32)
    for s0 in range(r0, r1, strip_rows):
        s1 = min(s0 + strip_rows, r1)
        vy, vx = np.nonzero(foot[s0:s1, c0:c1])
        if vy.size == 0:
            continue
        gy = vy + s0
        gx = vx + c0
        X = extract_deconfounded_rows(gy, gx, uwbp_mm, ocda_mm, shared_mm)
        out[vy + (s0 - r0), vx] = clf.predict_proba(X)[:, 1].astype(np.float32)
        del X
    return out


def calibrate_inner_stage2_weights(
    visible_mask: np.ndarray,
    train_dom: np.ndarray,
    foot: np.ndarray,
    pu_phys_guard: np.ndarray,
    uwbp_mm: np.ndarray,
    ocda_mm: np.ndarray,
    shared_mm: np.ndarray,
    seed_val: int,
) -> tuple[float, float, float, float]:
    """Hold out 20% of visible training components strictly inside `train_dom` to fit Stage-2 log-odds fusion."""
    rng = np.random.default_rng(seed_val + 9000)
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
    inner_vis = vis_tr & (~inner_hid)
    inner_vis_full = (visible_mask & (~train_dom)) | inner_vis

    tip_in, rel_in, _ = ocda.compute_fold_visible_continuation(inner_vis_full, foot)
    clf_in = fit_stage1_deconf_hgb(
        inner_vis, inner_vis_full, train_dom, pu_phys_guard,
        uwbp_mm, ocda_mm, shared_mm, seed_val + 500,
    )

    py, px = np.nonzero(inner_hid)
    d_in = ndi.distance_transform_edt(~inner_vis_full)
    neg_cand = train_dom & (~inner_vis_full) & (~inner_hid) & (d_in > 2.0)
    ny, nx = np.nonzero(neg_cand)
    k_n = min(int(py.size) * 6, int(ny.size))
    pick = rng.choice(ny.size, size=k_n, replace=False)
    ny, nx = ny[pick], nx[pick]
    del d_in, neg_cand

    ys = np.concatenate([py, ny])
    xs = np.concatenate([px, nx])
    y_cal = np.concatenate([np.ones(py.size, dtype=np.int32), np.zeros(ny.size, dtype=np.int32)])
    X_phys = extract_deconfounded_rows(ys, xs, uwbp_mm, ocda_mm, shared_mm)
    p_in = np.clip(clf_in.predict_proba(X_phys)[:, 1], 1e-4, 1.0 - 1e-4)
    logit_in = np.log(p_in / (1.0 - p_in))
    Z = np.column_stack([logit_in, tip_in[ys, xs], rel_in[ys, xs]]).astype(np.float64)
    lr = LogisticRegression(C=1.0, max_iter=300)
    lr.fit(Z, y_cal)
    w0, w1, w2 = [float(v) for v in lr.coef_[0]]
    b0 = float(lr.intercept_[0])
    del clf_in, X_phys, tip_in, rel_in
    return (max(w0, 0.50), max(w1, 0.0), max(w2, 0.0), b0)


def compose_dual_belief_and_allowed(
    prob_sub: np.ndarray,
    domain_sub: np.ndarray,
    vis_sub: np.ndarray,
    d_vis_sub: np.ndarray,
    crest_sub: np.ndarray,
    m_struct_sub: np.ndarray,
    tip_sub: np.ndarray,
    rel_sub: np.ndarray,
    weights: tuple[float, float, float, float],
    hydro_amp_sub: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Dual-Regime Stage-2 log-odds continuation + M_struct upland/blind-worm synthesis."""
    w_log, w_tip, w_rel, b0 = weights
    p_clip = np.clip(prob_sub, 1e-4, 1.0 - 1e-4).astype(np.float32)
    logit = np.log(p_clip / (1.0 - p_clip))
    phys_gate = np.clip((crest_sub - 0.28) / 0.50, 0.15, 1.0).astype(np.float32)
    eta = b0 + w_log * logit + (w_tip * tip_sub + w_rel * rel_sub) * phys_gate
    post = (1.0 / (1.0 + np.exp(-np.clip(eta, -12.0, 12.0)))).astype(np.float32)

    # Broadside subsurface dipole explaining-away outside forward tip cones
    flank_taper = np.where(
        tip_sub >= 0.18,
        1.0,
        0.42 + 0.58 * np.clip((d_vis_sub - 2.0) / 4.0, 0.0, 1.0),
    ).astype(np.float32)

    # Dual-Regime synthesis: combine calibrated PU+continuation posterior with label-free M_struct
    # so unmapped Cenozoic upland bedrock faults (`SGMC-CAL`) and deep 55-deg worms retain recall!
    dual_post = (0.76 * post + 0.24 * m_struct_sub * (0.36 + 0.64 * np.sqrt(np.maximum(post, 0.0)))).astype(np.float32)

    sharp_crest = np.power(np.maximum(crest_sub, 0.0), 2.15).astype(np.float32)
    belief = (np.power(np.maximum(dual_post, 1e-6), 1.08) * flank_taper * sharp_crest).astype(np.float32)
    if hydro_amp_sub is not None:
        belief = (belief * hydro_amp_sub).astype(np.float32)

    tip_entry = (tip_sub >= 0.26) & (crest_sub >= 0.76) & (d_vis_sub > 1.0)
    collar_ok = (d_vis_sub > 2.24) | tip_entry
    allowed = domain_sub & (~vis_sub) & collar_ok
    belief = np.where(domain_sub, belief, 0.0).astype(np.float32)
    return belief, allowed


def build_or_load_h33a_cached(bands_dir: Path, ddir: Path, wdir: Path, foot: np.ndarray) -> np.ndarray:
    cache_p = wdir / "h33a_v1.npy"
    if cache_p.is_file():
        arr = np.load(cache_p)
        if arr.shape == foot.shape and arr.dtype == np.float32:
            return arr
    arr = h33.build_h33a(bands_dir, ddir, foot).astype(np.float32)
    np.save(cache_p, arr)
    return arr


def robust_scale_01(arr: np.ndarray, foot: np.ndarray) -> np.ndarray:
    v = arr[foot & np.isfinite(arr) & (arr > 0)]
    if v.size == 0:
        return np.zeros_like(arr, dtype=np.float32)
    p995 = float(np.percentile(v, 99.5))
    return np.where(foot, np.clip(arr / max(p995, 1e-6), 0.0, 1.0), 0.0).astype(np.float32)


def load_cached_variant(variant_id: str, slug: str, out_dir: Path) -> dict | None:
    eval_json = out_dir / f"{variant_id}_eval.json"
    npz_path = out_dir / f"{variant_id}_cells.npz"
    dots_npy = out_dir / f"{variant_id}_dots.npy"
    surf_path = out_dir / f"{variant_id}_surface.npy"
    audits = sorted(out_dir.glob(f"*{slug}*-audit.json"))
    zeros_tifs = sorted(out_dir.glob(f"*{slug}*-zeros.tif"))
    if not (eval_json.is_file() and npz_path.is_file() and dots_npy.is_file() and surf_path.is_file() and audits and zeros_tifs):
        return None
    rep = json.loads(eval_json.read_text())
    rep["full_map_dot_count"] = int((np.load(dots_npy) > 0).sum())
    rep["surface_npy"] = str(surf_path)
    rep["dots_npy"] = str(dots_npy)
    rep["zeros_tif"] = str(zeros_tifs[-1])
    rep["submission_bundle"] = json.loads(audits[-1].read_text())
    rep["cells_npz"] = str(npz_path)
    return rep


def emit_and_evaluate(
    variant_id: str,
    slug: str,
    note_str: str,
    cand_by_cell: dict[str, np.ndarray],
    full_surface: np.ndarray,
    full_dots: np.ndarray,
    foot: np.ndarray,
    out_dir: Path,
    elapsed_s: float,
    extra_meta: dict | None = None,
) -> dict:
    s_max = float(full_surface[foot].max()) if foot.any() else 1.0
    surf_norm = np.where(foot, full_surface / max(s_max, 1e-6), 0.0).astype(np.float32)

    npz_path = out_dir / f"{variant_id}_cells.npz"
    np.savez_compressed(npz_path, **cand_by_cell)
    surf_path = out_dir / f"{variant_id}_surface.npy"
    np.save(surf_path, surf_norm)
    dots_npy = out_dir / f"{variant_id}_dots.npy"
    np.save(dots_npy, full_dots.astype(np.float32))

    sub_proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "submission_writer.py"),
            str(dots_npy),
            "--slug",
            slug,
            "--candidate-id",
            variant_id,
            "--note",
            note_str[:140],
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
    rep["elapsed_seconds"] = round(elapsed_s, 2)
    rep["full_map_dot_count"] = int(full_dots.sum())
    rep["surface_npy"] = str(surf_path)
    rep["dots_npy"] = str(dots_npy)
    rep["zeros_tif"] = str(zeros_tif_path)
    rep["submission_bundle"] = bundle
    rep["cells_npz"] = str(npz_path)
    if extra_meta:
        rep.update(extra_meta)
    print(
        f"[{variant_id}] HIDE-RECOVER={rep['hide_and_recover']['pooled_dti']:.6f} "
        f"CI={rep['hide_and_recover']['ci95_cluster_bootstrap']} | "
        f"SGMC-CAL={rep['sgmc_off_catalogue']['sgmc_prevalence_calibrated_dti']:.6f} "
        f"(raw={rep['sgmc_off_catalogue']['sgmc_raw_pooled_dti']:.6f}) | dots={rep['full_map_dot_count']:,}"
    )
    return rep


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


def main() -> int:
    t_start = time.time()
    ddir, wdir = data_dir(), work_dir()
    bands_dir = wdir / "bands"
    out_dir = wdir / "uwbp_lane_v1"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[UWBP-LANE] Loading holdout context & verified caches... (rss={rss_mb():.0f} MB)")
    ctx = holdout.load_holdout_context(ddir)
    foot = ctx.foot
    tot_foot = float(foot.sum())

    uwbp_mm = uwbp.build_or_load_uwbp_free_stack(ddir, wdir)
    ocda_mm = ocda.build_or_load_ocda_free_stack(ddir, wdir)
    shared_mm = shared_features.load_checked(wdir / "feature_stack.npy", ddir / "training_features.tif")

    print("[UWBP-LANE] Building 1-px crest carrier, Dual-Regime M_struct, PU guard, & Hydrothermal Amplifier...")
    crest_carrier = uwbp.build_uwbp_crest_carrier(uwbp_mm, ocda_mm, foot)
    h33a_arr = build_or_load_h33a_cached(bands_dir, ddir, wdir, foot)
    m_struct = robust_scale_01(
        (0.50 * h33a_arr + 0.50 * np.asarray(uwbp_mm[17], dtype=np.float32)).astype(np.float32),
        foot,
    )
    del h33a_arr

    # PU reliable-negative guard: exclude top 8% of multi-physics M_struct + piedmont/tilt crests
    phys_guard_score = (
        0.55 * m_struct
        + 0.25 * np.clip(np.asarray(ocda_mm[0], dtype=np.float32), 0.0, 1.0)
        + 0.20 * np.asarray(uwbp_mm[2], dtype=np.float32)
    )
    pu_phys_guard = (phys_guard_score >= float(np.percentile(phys_guard_score[foot], 92.0))) & foot
    del phys_guard_score

    # Strike-steered hydrothermal conduit amplifier (`H-K1-B3`, 100% label-free)
    hydro_amp = (
        1.0
        + 0.26
        * np.asarray(uwbp_mm[14], dtype=np.float32)
        * (
            0.35
            + 0.40 * np.asarray(uwbp_mm[13], dtype=np.float32)
            + 0.35 * np.asarray(uwbp_mm[12], dtype=np.float32)
            + 0.25 * np.asarray(uwbp_mm[5], dtype=np.float32)
        )
    ).astype(np.float32)
    gc.collect()

    collars = [
        ndi.binary_dilation(ctx.quad == f, structure=np.ones((3, 3), bool), iterations=holdout.COLLAR_PX) & foot
        for f in range(4)
    ]
    quad_bboxes: list[tuple[slice, slice]] = []
    for f in range(4):
        qy, qx = np.nonzero((ctx.quad == f) & foot)
        quad_bboxes.append((slice(int(qy.min()), int(qy.max()) + 1), slice(int(qx.min()), int(qx.max()) + 1)))

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
    with rasterio.open(champ_zeros_tif) as ds:
        champ_full_mask = (ds.read(1) == 1) & foot

    # =========================================================================
    # Controlled 3-Experiment Pass (`EXP-B1`, `EXP-B2`, `EXP-B3`)
    # Shares exact Stage-1 57-ch Deconfounded UWBP PU-HGB per cell/quadrant
    # =========================================================================
    cached_b1 = load_cached_variant("exp_b1_uwbp_deconf_pu", "kanler1-uwbp-drcs-exp-b1", out_dir)
    cached_b2 = load_cached_variant("exp_b2_uwbp_drcs_dual", "kanler1-uwbp-drcs-exp-b2", out_dir)
    cached_b3 = load_cached_variant("exp_b3_uwbp_drcs_dinkelbach", "kanler1-uwbp-drcs-exp-b3", out_dir)

    if cached_b1 and cached_b2 and cached_b3:
        print("[UWBP-LANE] Reusing verified on-disk EXP-B1..B3 bundles & evaluations...")
        rep_b1, rep_b2, rep_b3 = cached_b1, cached_b2, cached_b3
        with np.load(rep_b1["cells_npz"]) as zf:
            b1_by_cell = {k: zf[k] for k in zf.files}
        with np.load(rep_b2["cells_npz"]) as zf:
            b2_by_cell = {k: zf[k] for k in zf.files}
        with np.load(rep_b3["cells_npz"]) as zf:
            b3_by_cell = {k: zf[k] for k in zf.files}
        dots_b1 = np.load(rep_b1["dots_npy"]) > 0
        dots_b2 = np.load(rep_b2["dots_npy"]) > 0
        dots_b3 = np.load(rep_b3["dots_npy"]) > 0
    else:
        t_models = time.time()
        b1_by_cell: dict[str, np.ndarray] = {}
        b2_by_cell: dict[str, np.ndarray] = {}
        b3_by_cell: dict[str, np.ndarray] = {}
        stage2_weights: dict[str, list[float]] = {}

        print(f"\n[UWBP-LANE] Fitting 8 fold-local Stage-1/Stage-2 models for EXP-B1..B3... (rss={rss_mb():.0f} MB)")
        for idx_c, cell in enumerate(ctx.cells):
            train_dom = foot & (~collars[cell.fold])
            w_cell = calibrate_inner_stage2_weights(
                cell.visible_full, train_dom, foot, pu_phys_guard,
                uwbp_mm, ocda_mm, shared_mm, seed_val=202800 + 19 * cell.seed + cell.fold,
            )
            stage2_weights[cell.key] = [round(v, 4) for v in w_cell]

            clf = fit_stage1_deconf_hgb(
                cell.visible_full, cell.visible_full, train_dom, pu_phys_guard,
                uwbp_mm, ocda_mm, shared_mm, seed_val=202850 + 19 * cell.seed + cell.fold,
            )
            sl = cell.bbox
            prob_sub = predict_bbox_probs(clf, sl, foot, uwbp_mm, ocda_mm, shared_mm)
            del clf

            q_in_sub = (ctx.quad[sl] == cell.fold) & foot[sl]
            cell_budget = int(round(TARGET_BUDGET * (float(q_in_sub.sum()) / tot_foot)))
            cell_min_b = int(round(34_500 * (float(q_in_sub.sum()) / tot_foot)))

            b1_belief = np.where(
                cell.active_sub,
                prob_sub * np.power(np.maximum(crest_carrier[sl], 0.0), 2.15),
                0.0,
            ).astype(np.float32)
            b1_allowed = cell.active_sub & (~cell.visible_full[sl]) & (cell.d_vis_sub > 2.0)
            b1_dots = ocda.pack_submodular_300m(b1_belief, b1_allowed, budget=cell_budget, min_dist_px=2.83, pool_mult=26)
            b1_by_cell[cell.key] = b1_dots & cell.active_sub
            del b1_belief, b1_allowed, b1_dots

            tip_f, rel_f, _ = ocda.compute_fold_visible_continuation(cell.visible_full, foot)
            b2_belief, b2_allowed = compose_dual_belief_and_allowed(
                prob_sub, cell.active_sub, cell.visible_full[sl], cell.d_vis_sub,
                crest_carrier[sl], m_struct[sl], tip_f[sl], rel_f[sl], w_cell, hydro_amp_sub=None,
            )
            b2_dots = ocda.pack_submodular_300m(b2_belief, b2_allowed, budget=cell_budget, min_dist_px=2.83, pool_mult=28)
            b2_by_cell[cell.key] = b2_dots & cell.active_sub
            del b2_belief, b2_dots

            b3_belief, b3_allowed = compose_dual_belief_and_allowed(
                prob_sub, cell.active_sub, cell.visible_full[sl], cell.d_vis_sub,
                crest_carrier[sl], m_struct[sl], tip_f[sl], rel_f[sl], w_cell, hydro_amp_sub=hydro_amp[sl],
            )
            b3_dots = uwbp.pack_dinkelbach_dti_300m(
                b3_belief, b3_allowed,
                max_budget=cell_budget, min_dist_px=2.98, fp_cost_lambda=0.040, min_budget=cell_min_b, pool_mult=24,
            )
            b3_by_cell[cell.key] = b3_dots & cell.active_sub
            del prob_sub, tip_f, rel_f, b2_allowed, b3_belief, b3_allowed, b3_dots
            gc.collect()
            print(
                f"  cell {idx_c + 1}/8 {cell.key}: "
                f"B1={int(b1_by_cell[cell.key].sum())} B2={int(b2_by_cell[cell.key].sum())} B3={int(b3_by_cell[cell.key].sum())} "
                f"w={stage2_weights[cell.key]} (rss={rss_mb():.0f} MB)"
            )

        print("\n[UWBP-LANE] Fitting 4 full-map out-of-quadrant models for EXP-B1..B3...")
        surf_b1 = np.zeros(foot.shape, dtype=np.float32)
        surf_b2 = np.zeros(foot.shape, dtype=np.float32)
        surf_b3 = np.zeros(foot.shape, dtype=np.float32)

        tip_full, rel_full, _ = ocda.compute_fold_visible_continuation(ctx.labels, foot)
        d_cat_full = ndi.distance_transform_edt(~ctx.labels).astype(np.float32)

        for f in range(4):
            train_dom = foot & (~collars[f])
            w_f = calibrate_inner_stage2_weights(
                ctx.labels, train_dom, foot, pu_phys_guard,
                uwbp_mm, ocda_mm, shared_mm, seed_val=202980 + f,
            )
            clf_f = fit_stage1_deconf_hgb(
                ctx.labels, ctx.labels, train_dom, pu_phys_guard,
                uwbp_mm, ocda_mm, shared_mm, seed_val=202990 + f,
            )
            q_sl = quad_bboxes[f]
            p_sub = predict_bbox_probs(clf_f, q_sl, foot, uwbp_mm, ocda_mm, shared_mm)
            del clf_f
            q_mask_sub = (ctx.quad[q_sl] == f) & foot[q_sl]

            b1_sub = (p_sub * np.power(np.maximum(crest_carrier[q_sl], 0.0), 2.15)).astype(np.float32)
            surf_b1[q_sl] = np.where(q_mask_sub, b1_sub, surf_b1[q_sl])
            del b1_sub

            b2_sub, _ = compose_dual_belief_and_allowed(
                p_sub, q_mask_sub, ctx.labels[q_sl], d_cat_full[q_sl],
                crest_carrier[q_sl], m_struct[q_sl], tip_full[q_sl], rel_full[q_sl], w_f, hydro_amp_sub=None,
            )
            surf_b2[q_sl] = np.where(q_mask_sub, b2_sub, surf_b2[q_sl])
            del b2_sub

            b3_sub, _ = compose_dual_belief_and_allowed(
                p_sub, q_mask_sub, ctx.labels[q_sl], d_cat_full[q_sl],
                crest_carrier[q_sl], m_struct[q_sl], tip_full[q_sl], rel_full[q_sl], w_f, hydro_amp_sub=hydro_amp[q_sl],
            )
            surf_b3[q_sl] = np.where(q_mask_sub, b3_sub, surf_b3[q_sl])
            del p_sub, b3_sub
            gc.collect()

        allowed_b1 = foot & (~ctx.labels) & (d_cat_full > 2.0)
        tip_entry_full = (tip_full >= 0.26) & (crest_carrier >= 0.76) & (d_cat_full > 1.0)
        allowed_b23 = foot & (~ctx.labels) & ((d_cat_full > 2.24) | tip_entry_full)
        del tip_full, rel_full, d_cat_full, tip_entry_full

        dots_b1 = ocda.pack_submodular_300m(surf_b1, allowed_b1, budget=TARGET_BUDGET, min_dist_px=2.83, pool_mult=26)
        dots_b2 = ocda.pack_submodular_300m(surf_b2, allowed_b23, budget=TARGET_BUDGET, min_dist_px=2.83, pool_mult=28)
        dots_b3 = uwbp.pack_dinkelbach_dti_300m(
            surf_b3, allowed_b23,
            max_budget=TARGET_BUDGET, min_dist_px=2.98, fp_cost_lambda=0.040, min_budget=34_500, pool_mult=24,
        )
        elapsed_models = time.time() - t_models

        print("\n[UWBP-LANE] Emitting bundles via `submission_writer.py` & scoring via `evaluate_holdout.py`...")
        rep_b1 = emit_and_evaluate(
            "exp_b1_uwbp_deconf_pu",
            "kanler1-uwbp-drcs-exp-b1",
            f"KANLER1 UWBP-DRCS Exp-B1 Deconfounded 57ch PU+300mCELF ({int(dots_b1.sum())}d)",
            b1_by_cell, surf_b1, dots_b1, foot, out_dir, elapsed_models / 3.0,
        )
        rep_b2 = emit_and_evaluate(
            "exp_b2_uwbp_drcs_dual",
            "kanler1-uwbp-drcs-exp-b2",
            f"KANLER1 UWBP-DRCS Exp-B2 DualRegime Worm+Struct+300mCELF ({int(dots_b2.sum())}d)",
            b2_by_cell, surf_b2, dots_b2, foot, out_dir, elapsed_models / 3.0,
            extra_meta={"learned_stage2_weights": stage2_weights},
        )
        rep_b3 = emit_and_evaluate(
            "exp_b3_uwbp_drcs_dinkelbach",
            "kanler1-uwbp-drcs-exp-b3",
            f"KANLER1 UWBP-DRCS Exp-B3 DualRegime+HydroConduit+Dinkelbach ({int(dots_b3.sum())}d)",
            b3_by_cell, surf_b3, dots_b3, foot, out_dir, elapsed_models / 3.0,
            extra_meta={"learned_stage2_weights": stage2_weights},
        )

    # Paired 256-block spatial cluster bootstrap deltas vs CHAMP-D28-VIS-B2 AND vs prior OCDA EXP-3
    ocda_ledger = json.loads((ROOT / "evidence" / "ocda_ablation_ledger.json").read_text())
    ocda_exp3_rep = ocda_ledger["results"]["EXP-3"]
    ocda_cells_p = Path(ocda_exp3_rep["cells_npz"])
    ocda_zeros_p = ROOT / "docs" / "downloads" / "gemsdoe32-kanler1-ocda-mscs-exp3-37654d-20261027T1842Z-1db32b55-zeros.tif"
    with rasterio.open(ocda_zeros_p) as ds:
        ocda_full_mask = (ds.read(1) == 1) & foot

    paired_vs_champ = {
        "EXP-B1": paired_delta_ci(ctx, b1_by_cell, champ_cells, dots_b1, champ_full_mask),
        "EXP-B2": paired_delta_ci(ctx, b2_by_cell, champ_cells, dots_b2, champ_full_mask),
        "EXP-B3": paired_delta_ci(ctx, b3_by_cell, champ_cells, dots_b3, champ_full_mask),
    }

    paired_vs_ocda = {}
    if ocda_cells_p.is_file():
        with np.load(ocda_cells_p) as zf:
            ocda_cells = {k: zf[k] for k in zf.files}
        for nm, c_cells, c_dots in [("EXP-B1", b1_by_cell, dots_b1), ("EXP-B2", b2_by_cell, dots_b2), ("EXP-B3", b3_by_cell, dots_b3)]:
            paired_vs_ocda[nm] = paired_delta_ci(ctx, c_cells, ocda_cells, c_dots, ocda_full_mask)

    results = {
        "CHAMP-D28-VIS-B2": champ_rep,
        "OCDA-EXP3-PRIOR": ocda_exp3_rep,
        "EXP-B1": rep_b1,
        "EXP-B2": rep_b2,
        "EXP-B3": rep_b3,
    }
    best_exp = max(("EXP-B1", "EXP-B2", "EXP-B3"), key=lambda k: results[k]["hide_and_recover"]["pooled_dti"])

    summary = {
        "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lane": "H-K1-B (UWBP-DRCS)",
        "preregistration_doc": "docs/research/hypotheses-20261028.md",
        "experiments_run": 3,
        "budget_cap_experiments": 3,
        "zero_sgmc_in_training_and_inference": True,
        "total_wall_seconds": round(time.time() - t_start, 2),
        "peak_rss_mb": round(rss_mb(), 1),
        "best_experiment": best_exp,
        "deconfounded_stage1_features": deconfounded_feature_names(False),
        "all_features_b2_b3": deconfounded_feature_names(True),
        "results": results,
        "paired_delta_vs_champion": paired_vs_champ,
        "paired_delta_vs_ocda_exp3": paired_vs_ocda,
    }
    (ROOT / "evidence" / "uwbp_ablation_ledger.json").write_text(json.dumps(summary, indent=2) + "\n")
    (ROOT / "docs" / "evidence" / "uwbp_ablation_ledger.json").write_text(json.dumps(summary, indent=2) + "\n")

    print("\n================ UWBP-DRCS 3-EXPERIMENT ABLATION LEDGER ================")
    print(
        f"  CHAMP-D28-VIS-B2 (GEMSDOE32 0.2778): "
        f"HIDE-RECOVER={champ_rep['hide_and_recover']['pooled_dti']:.6f} | "
        f"SGMC-CAL={champ_rep['sgmc_off_catalogue']['sgmc_prevalence_calibrated_dti']:.6f}"
    )
    print(
        f"  OCDA-EXP3-PRIOR  (KANLER1 prior)   : "
        f"HIDE-RECOVER={ocda_exp3_rep['hide_and_recover']['pooled_dti']:.6f} | "
        f"SGMC-CAL={ocda_exp3_rep['sgmc_off_catalogue']['sgmc_prevalence_calibrated_dti']:.6f}"
    )
    for k in ("EXP-B1", "EXP-B2", "EXP-B3"):
        r = results[k]
        dc = paired_vs_champ[k]
        print(
            f"  {k:8s} ({r['full_map_dot_count']:,}d): "
            f"HIDE-RECOVER={r['hide_and_recover']['pooled_dti']:.6f} CI={r['hide_and_recover']['ci95_cluster_bootstrap']} "
            f"| d_HR_vs_G32={dc['hide_recover']['delta_dti']:+.6f} CI={dc['hide_recover']['delta_ci95']} (P>0={dc['hide_recover']['prob_cand_gt_ref']:.3f}) "
            f"| SGMC-CAL={r['sgmc_off_catalogue']['sgmc_prevalence_calibrated_dti']:.6f} (d_SG={dc['sgmc_calibrated']['delta_dti']:+.6f})"
        )
    print(f"Selected best candidate: {best_exp} | elapsed={summary['total_wall_seconds']}s | peak_rss={summary['peak_rss_mb']} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
