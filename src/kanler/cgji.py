"""Gallardo-Meju Structural Cross-Gradient Collinearity, Piedmont Scarp Dipole & Hydrothermal Upflow Breach (CGJI-HTB).

Lane: L-CGJI-HTB-2026-10-27
Physical hypothesis:
    Blind and range-front basin-margin normal/transtensional faults in the Great Basin
    produce a simultaneous boundary across independent subsurface and surface fields:
    1. Potential-field cross-gradient collinearity (Gallardo & Meju, 2003, GRL 30(13);
       2004, JGR 109(B3)): along a dipping fault contact juxtaposed across basement
       density (CBA / isostatic gravity) and magnetic susceptibility (RTP magnetics)
       or magnetotelluric resistivity (10 km / 20 km / 35 km conductivity), the
       normalized 2D cross-gradient magnitude
           |tau(u, v)| = |grad(u) x grad(v)| / (|grad(u)| |grad(v)| + eps)
       vanishes while both gradients exceed noise, yielding a dimensionless
       structural collinearity ridge J_CG(u, v) = (1 - |tau(u, v)|) * sqrt(|grad u| |grad v|).
    2. Piedmont break-in-slope scarp dipole: range-front and intrabasin fault scarps
       produce an asymmetric concave-up piedmont toe (_hessian_ridge(-dem)) paired
       with a steep scarp face (1 m LiDAR upslope/downslope/cross-contrast bands 6-8
       and principal curvature curv_s1/curv_s2), with road-corridor damping via
       TIGER road distance.
    3. Hydrothermal upflow breach & brittle dilatation gate: permeable fault relays
       localize convective thermal plumes (INGENIOUS 2 m temperature probe dataset +
       shallow heatflow + paleo-geothermal silica/travertine/tufa deposits) and
       potassium/thorium hydrothermal alteration edges where geodetic dilatational
       and second-invariant strain rates peak.
    4. Transverse Non-Maximum Suppressed (NMS) crest skeletonization: restricting
       candidate emission to the 1-px transverse crest of the multi-physics structural
       spine prevents 2D blob clustering and aligns dot packing with the 300 m
       linear fault trace geometry.
"""
from __future__ import annotations

import csv
import gc
import hashlib
import io
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform as warp_transform
from scipy.ndimage import binary_dilation, convolve, distance_transform_edt, gaussian_filter
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from gems32 import features, holdout
from gems32.paths import work_dir
from gemsdoe1.iedr import paleo_halo, ranked_poisson, unit_field


LANE_ID = "L-CGJI-HTB-2026-10-27"
HYPOTHESIS_ID = "H-CGJI-HTB"
TARGET_DOTS = 37654
MIN_DIST_PX = float(np.sqrt(8.0))  # 2.828427 px = 282.8 m spacing
COLLAR_PX = 2.0


def robust_z(arr: np.ndarray, foot: np.ndarray) -> np.ndarray:
    """Median/MAD robust z-score strictly within the active footprint."""
    v = np.asarray(arr[foot], dtype=np.float32)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return np.zeros_like(arr, dtype=np.float32)
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med))) * 1.4826 + 1e-6
    out = np.zeros_like(arr, dtype=np.float32)
    out[foot] = (np.nan_to_num(arr[foot], nan=med) - med) / mad
    return out


def cross_gradient_collinearity(
    u: np.ndarray,
    v: np.ndarray,
    foot: np.ndarray,
    sigma: float = 1.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute Gallardo-Meju (2003, 2004) structural collinearity and cross-gradient."""
    u_s = gaussian_filter(np.nan_to_num(u, nan=0.0).astype(np.float32), sigma=sigma)
    v_s = gaussian_filter(np.nan_to_num(v, nan=0.0).astype(np.float32), sigma=sigma)
    uy, ux = np.gradient(u_s)
    vy, vx = np.gradient(v_s)
    mag_u = np.hypot(ux, uy)
    mag_v = np.hypot(vx, vy)
    cross = ux * vy - uy * vx
    dot = ux * vx + uy * vy
    denom = mag_u * mag_v + 1e-6
    sin_theta = np.clip(np.abs(cross) / denom, 0.0, 1.0)
    cos_2theta = np.clip((dot / denom) ** 2 - sin_theta ** 2, -1.0, 1.0)

    zu = np.clip(robust_z(mag_u, foot), 0.0, 6.0) / 6.0
    zv = np.clip(robust_z(mag_v, foot), 0.0, 6.0) / 6.0
    joint_amp = np.sqrt(zu * zv)

    collinear = unit_field(joint_amp * (1.0 - sin_theta) * (0.5 + 0.5 * np.maximum(cos_2theta, 0.0)), foot)
    discord = unit_field(joint_amp * sin_theta, foot)
    return collinear.astype(np.float32), discord.astype(np.float32)


def build_2m_probe_halo(
    zip_path: Path,
    ref_transform: Any,
    shape: tuple[int, int],
    foot: np.ndarray,
    sigma_px: float = 10.0,
) -> np.ndarray:
    """Project INGENIOUS regional 2 m temperature probe anomalies onto the 100 m grid."""
    if not zip_path.exists():
        return np.zeros(shape, dtype=np.float32)
    xs_raw: list[float] = []
    ys_raw: list[float] = []
    temps: list[float] = []
    src_epsg = 26911
    with zipfile.ZipFile(zip_path) as zf:
        prj_names = [n for n in zf.namelist() if n.endswith(".prj")]
        if prj_names:
            prj_txt = zf.read(prj_names[0]).decode("utf-8", errors="ignore")
            try:
                epsg = CRS.from_wkt(prj_txt).to_epsg()
                if epsg:
                    src_epsg = int(epsg)
            except Exception:
                src_epsg = 26911
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not csv_names:
            return np.zeros(shape, dtype=np.float32)
        raw_text = zf.read(csv_names[0]).decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(raw_text))
        for row in reader:
            try:
                e = float(row.get("Easting_m", "") or "nan")
                n = float(row.get("Northing_m", "") or "nan")
                t = float(row.get("Temp_C", "") or "nan")
            except ValueError:
                continue
            if np.isfinite(e) and np.isfinite(n) and np.isfinite(t) and -20.0 < t < 150.0:
                xs_raw.append(e)
                ys_raw.append(n)
                temps.append(t)
    if not xs_raw:
        return np.zeros(shape, dtype=np.float32)
    t_arr = np.asarray(temps, dtype=np.float32)
    t_med = float(np.median(t_arr))
    t_mad = float(np.median(np.abs(t_arr - t_med))) * 1.4826 + 1e-6
    t_weight = np.clip((t_arr - t_med) / t_mad, 0.25, 5.0)
    xs_utm, ys_utm = warp_transform(f"EPSG:{src_epsg}", "EPSG:32611", xs_raw, ys_raw)
    inv = ~ref_transform
    cols, rows = inv * (np.asarray(xs_utm, dtype=np.float64), np.asarray(ys_utm, dtype=np.float64))
    cols_i = np.floor(cols).astype(np.int32)
    rows_i = np.floor(rows).astype(np.int32)
    valid = (rows_i >= 0) & (rows_i < shape[0]) & (cols_i >= 0) & (cols_i < shape[1])
    impulse = np.zeros(shape, dtype=np.float32)
    np.add.at(impulse, (rows_i[valid], cols_i[valid]), t_weight[valid])
    if sigma_px > 0:
        impulse = gaussian_filter(impulse, sigma=sigma_px)
    return unit_field(impulse, foot)


def load_rad_alteration_edge(rad_path: Path, foot: np.ndarray) -> np.ndarray:
    """Compute hydrothermal K/Th alteration gradient edge from tertiary_rad_ratios_f32.tif."""
    if not rad_path.exists():
        return np.zeros(foot.shape, dtype=np.float32)
    with rasterio.open(rad_path) as ds:
        k_th = ds.read(1).astype(np.float32)
        u_th = ds.read(2).astype(np.float32)
        k_u = ds.read(3).astype(np.float32)
    k_th_s = gaussian_filter(np.nan_to_num(k_th, nan=0.0), sigma=1.8)
    u_th_s = gaussian_filter(np.nan_to_num(u_th, nan=0.0), sigma=1.8)
    k_u_s = gaussian_filter(np.nan_to_num(k_u, nan=0.0), sigma=1.8)
    g1 = np.hypot(*np.gradient(k_th_s))
    g2 = np.hypot(*np.gradient(u_th_s))
    g3 = np.hypot(*np.gradient(k_u_s))
    raw = 0.50 * unit_field(g1, foot) + 0.25 * unit_field(g2, foot) + 0.25 * unit_field(g3, foot)
    return unit_field(raw, foot)


def build_cgji_workspace(
    data_dir: Path,
    stack: np.ndarray,
    foot: np.ndarray,
) -> dict[str, Any]:
    """Build all CGJI-HTB channels, piedmont scarp dipole, and 1-px transverse NMS crest."""
    with rasterio.open(data_dir / "sample_submission.tif") as ds:
        ref_transform = ds.transform

    # Extract only required slices and immediately convert to compact float32
    cba_grav = np.array(stack[:, :, 1], dtype=np.float32)
    iso_grav = np.array(stack[:, :, 2], dtype=np.float32)
    mag_rtp = np.array(stack[:, :, 3], dtype=np.float32)
    heatflow = np.array(stack[:, :, 4], dtype=np.float32)
    cond_10 = np.array(stack[:, :, 5], dtype=np.float32)
    cond_20 = np.array(stack[:, :, 6], dtype=np.float32)
    cond_35 = np.array(stack[:, :, 7], dtype=np.float32)
    dem = np.array(stack[:, :, 11], dtype=np.float32)
    basement_grav = np.array(stack[:, :, 13], dtype=np.float32)
    dilatation = np.array(stack[:, :, 15], dtype=np.float32)
    sec_inv = np.array(stack[:, :, 16], dtype=np.float32)
    slope = np.array(stack[:, :, 18], dtype=np.float32)

    curv_s1 = unit_field(np.maximum(stack[:, :, 19], 0.0), foot)
    curv_s2 = unit_field(np.maximum(stack[:, :, 20], 0.0), foot)
    curv_s4 = unit_field(np.maximum(stack[:, :, 21], 0.0), foot)
    tpi_abs = unit_field(np.abs(stack[:, :, 22]), foot)
    grav_terr_grad = unit_field(stack[:, :, 25], foot)
    grav_base_grad = unit_field(stack[:, :, 26], foot)
    mag_grad = unit_field(stack[:, :, 27], foot)
    cond_grad = unit_field(stack[:, :, 29], foot)
    coherence_s2 = unit_field(stack[:, :, 31], foot)
    strike_cos = np.array(stack[:, :, 32], dtype=np.float32)
    strike_sin = np.array(stack[:, :, 33], dtype=np.float32)

    # 1. Gallardo-Meju Cross-Gradient Collinearity channels
    cgji_grav_rtp, _ = cross_gradient_collinearity(cba_grav, mag_rtp, foot, sigma=1.6)
    cgji_iso_rtp, _ = cross_gradient_collinearity(iso_grav, mag_rtp, foot, sigma=2.0)
    cgji_base_cond10, _ = cross_gradient_collinearity(basement_grav, cond_10, foot, sigma=2.0)
    cgji_cond_10_20, _ = cross_gradient_collinearity(cond_10, cond_20, foot, sigma=2.2)
    _, cond_relay_breach = cross_gradient_collinearity(cond_20, cond_35, foot, sigma=2.5)
    del cba_grav, iso_grav, mag_rtp, cond_10, cond_20, cond_35, basement_grav
    gc.collect()

    cgji_grav_rtp_comb = unit_field(0.55 * cgji_grav_rtp + 0.45 * cgji_iso_rtp, foot)
    cgji_base_cond = unit_field(0.60 * cgji_base_cond10 + 0.40 * cgji_cond_10_20, foot)
    del cgji_grav_rtp, cgji_iso_rtp, cgji_base_cond10, cgji_cond_10_20
    gc.collect()

    # 2. Piedmont break-in-slope scarp dipole + road-cleaned 1m LiDAR scarp face
    piedmont_toe1 = unit_field(features._hessian_ridge(-dem, 1.2), foot)
    piedmont_toe2 = unit_field(features._hessian_ridge(-dem, 2.2), foot)
    slope_crest = unit_field(features._hessian_ridge(slope, 1.4), foot)
    del dem, slope
    gc.collect()

    road_path = data_dir / "external" / "tiger_road_distance_m.tif"
    if road_path.exists():
        with rasterio.open(road_path) as ds:
            road_d = np.nan_to_num(ds.read(1).astype(np.float32), nan=500.0)
        road_gate = np.clip(1.0 - np.exp(-(road_d / 120.0) ** 2), 0.25, 1.0).astype(np.float32)
        del road_d
    else:
        road_gate = np.ones(foot.shape, dtype=np.float32)

    lidar_path = data_dir / "external" / "lidar_scarp_features_u8.tif"
    with rasterio.open(lidar_path) as ds:
        li_step = ds.read(3).astype(np.float32) / 255.0
        li_down = ds.read(6).astype(np.float32) / 255.0
        li_up = ds.read(7).astype(np.float32) / 255.0
        li_cross = ds.read(8).astype(np.float32) / 255.0
        li_coh = ds.read(10).astype(np.float32) / 255.0
        li_val = (ds.read(12) > 0) & foot

    li_dipole = unit_field(
        np.where(
            li_val,
            (0.30 * li_up + 0.25 * li_down + 0.25 * li_cross + 0.20 * li_step) * (0.40 + 0.60 * li_coh),
            0.0,
        ),
        foot,
    )
    del li_step, li_down, li_up, li_cross, li_coh
    gc.collect()

    scarp_dipole = unit_field(
        np.where(
            li_val,
            0.55 * li_dipole + 0.45 * (0.40 * curv_s2 + 0.30 * piedmont_toe1 + 0.30 * slope_crest),
            0.45 * curv_s2 + 0.30 * piedmont_toe2 + 0.25 * slope_crest,
        ).astype(np.float32),
        foot,
    )
    del piedmont_toe2
    gc.collect()

    # 3. Potential-field / scarp joint collinearity & Hessian ridge
    subsurface_edge = unit_field(
        0.35 * grav_terr_grad + 0.30 * grav_base_grad + 0.20 * mag_grad + 0.15 * cond_grad,
        foot,
    )
    cgji_scarp_pf = unit_field(
        scarp_dipole * (0.45 + 0.55 * np.sqrt(np.maximum(subsurface_edge * (0.5 * cgji_grav_rtp_comb + 0.5 * cgji_base_cond), 0.0))),
        foot,
    )
    cgji_joint_raw = (
        0.38 * cgji_grav_rtp_comb
        + 0.32 * cgji_base_cond
        + 0.30 * cgji_scarp_pf
    ).astype(np.float32)
    cgji_crest = unit_field(
        0.55 * features._hessian_ridge(cgji_joint_raw, 1.2)
        + 0.45 * features._hessian_ridge(cgji_joint_raw, 2.4),
        foot,
    )
    del cgji_joint_raw, grav_terr_grad, grav_base_grad, mag_grad, cond_grad
    gc.collect()

    # 4. Hydrothermal upflow breach & tectonic strain modulator
    z_dil = np.clip(robust_z( np.abs(dilatation), foot ), -2.0, 5.0)
    z_shr = np.clip(robust_z( sec_inv, foot ), -2.0, 5.0)
    strain_mod = unit_field(0.55 * z_shr + 0.45 * z_dil, foot)
    del dilatation, sec_inv, z_dil, z_shr
    gc.collect()

    paleo = paleo_halo(
        data_dir / "external" / "paleo_geothermal_regional.zip",
        ref_transform,
        foot.shape,
        foot,
        sigma=12.0,
    )
    probe2m = build_2m_probe_halo(
        data_dir / "external" / "2m_temperature_probe_INGENIOUS_regional_data.zip",
        ref_transform,
        foot.shape,
        foot,
        sigma_px=10.0,
    )
    rad_alt_edge = load_rad_alteration_edge(
        data_dir / "external" / "geodawn_rad_u8.tif",
        foot,
    )
    hf_unit = unit_field(heatflow, foot)
    del heatflow
    gc.collect()

    hydrothermal_upflow = unit_field(
        0.30 * hf_unit + 0.25 * paleo + 0.25 * probe2m + 0.20 * rad_alt_edge,
        foot,
    )

    # 5. Multi-physics spine and 1-px transverse Non-Maximum Suppressed (NMS) crest skeleton
    spine = unit_field(
        0.48 * scarp_dipole
        + 0.24 * cgji_crest
        + 0.16 * (0.50 * cgji_grav_rtp_comb + 0.50 * cgji_base_cond)
        + 0.12 * subsurface_edge,
        foot,
    )
    _, theta_s, _ = features._structure_tensor(spine, 1.2)
    dx = np.round(np.cos(theta_s)).astype(np.int32)
    dy = np.round(np.sin(theta_s)).astype(np.int32)
    del theta_s
    gc.collect()

    H, W = foot.shape
    yy, xx = np.mgrid[:H, :W]
    y1 = np.clip(yy + dy, 0, H - 1)
    x1 = np.clip(xx + dx, 0, W - 1)
    y2 = np.clip(yy - dy, 0, H - 1)
    x2 = np.clip(xx - dx, 0, W - 1)
    del yy, xx, dy, dx
    gc.collect()

    nms_mask = (
        (spine >= spine[y1, x1])
        & (spine > spine[y2, x2])
        & (spine > np.percentile(spine[foot], 50.0))
        & foot
    )
    del y1, x1, y2, x2
    gc.collect()

    phys_prior = unit_field(
        spine
        * (0.55 + 0.45 * strain_mod)
        * (0.60 + 0.40 * hydrothermal_upflow)
        * (0.55 + 0.45 * road_gate),
        foot,
    )

    derived_channels = {
        "cgji_spine": spine,
        "cgji_scarp_dipole": scarp_dipole,
        "cgji_lidar_dipole": li_dipole,
        "cgji_lidar_valid": li_val.astype(np.float32),
        "v2_curv_s1": curv_s1,
        "v2_curv_s2": curv_s2,
        "v2_coherence_s2": coherence_s2,
        "v2_strike_cos": strike_cos,
        "v2_strike_sin": strike_sin,
        "cgji_piedmont_toe1": piedmont_toe1,
        "cgji_slope_crest": slope_crest,
        "cgji_grav_rtp": cgji_grav_rtp_comb,
        "cgji_base_cond": cgji_base_cond,
        "cgji_scarp_pf": cgji_scarp_pf,
        "cgji_crest": cgji_crest,
        "cgji_subsurface_edge": subsurface_edge,
        "cgji_strain_mod": strain_mod,
        "cgji_hydrothermal_upflow": hydrothermal_upflow,
        "cgji_probe2m_halo": probe2m,
        "cgji_rad_alt_edge": rad_alt_edge,
        "cgji_road_gate": road_gate,
    }
    return {
        "nms_mask": nms_mask,
        "phys_prior": phys_prior,
        "derived_channels": derived_channels,
        "cond_relay_breach": cond_relay_breach,
        "curv_s4": curv_s4,
        "tpi_abs": tpi_abs,
    }


def list_band_files() -> list[Path]:
    bands_dir = work_dir() / "bands"
    files = sorted(bands_dir.glob("[0-9][0-9]_*.npy"))
    if len(files) != 19:
        raise FileNotFoundError(f"Expected 19 prepared band files in {bands_dir}, found {len(files)}")
    return files


def extract_feature_matrix(
    ys: np.ndarray,
    xs: np.ndarray,
    band_files: list[Path],
    derived_channels: dict[str, np.ndarray],
) -> tuple[np.ndarray, list[str]]:
    """Extract compact (N, 40) feature matrix at pixel coordinates (ys, xs)."""
    cols: list[np.ndarray] = []
    names: list[str] = []
    for bf in band_files:
        b_arr = np.load(bf, mmap_mode="r")
        val = np.nan_to_num(np.asarray(b_arr[ys, xs], dtype=np.float32), nan=0.0)
        cols.append(val)
        names.append(f"band_{bf.stem}")
    for k, g in derived_channels.items():
        cols.append(np.asarray(g[ys, xs], dtype=np.float32))
        names.append(k)
    return np.column_stack(cols), names


def compute_withheld_fold_canaries(
    ctx: holdout.HoldoutContext,
    band_files: list[Path],
    derived_channels: dict[str, np.ndarray],
    phys_prior: np.ndarray,
    max_neg_per_cell: int = 25000,
) -> dict[str, Any]:
    """Protocol Rule 4: Test every single model feature alone on withheld holdout folds."""
    rng = np.random.default_rng(20261027)
    pos_ys_list: list[np.ndarray] = []
    pos_xs_list: list[np.ndarray] = []
    neg_ys_list: list[np.ndarray] = []
    neg_xs_list: list[np.ndarray] = []

    for cell in ctx.cells:
        if cell.n_truth == 0:
            continue
        ty, tx = cell.truth_coords
        y0, x0 = cell.bbox[0].start, cell.bbox[1].start
        pos_ys_list.append(ty + y0)
        pos_xs_list.append(tx + x0)

        neg_sub = cell.active_sub & (cell.d_visible_sub > 2.0)
        neg_sub = neg_sub.copy()
        neg_sub[ty, tx] = False
        ny, nx = np.nonzero(neg_sub)
        if ny.size > max_neg_per_cell:
            idx = rng.choice(ny.size, size=max_neg_per_cell, replace=False)
            ny, nx = ny[idx], nx[idx]
        neg_ys_list.append(ny + y0)
        neg_xs_list.append(nx + x0)

    pos_y = np.concatenate(pos_ys_list)
    pos_x = np.concatenate(pos_xs_list)
    neg_y = np.concatenate(neg_ys_list)
    neg_x = np.concatenate(neg_xs_list)
    ys = np.concatenate([pos_y, neg_y])
    xs = np.concatenate([pos_x, neg_x])
    y_true = np.concatenate([
        np.ones(pos_y.size, dtype=np.int8),
        np.zeros(neg_y.size, dtype=np.int8),
    ])

    X_all, feat_names = extract_feature_matrix(ys, xs, band_files, derived_channels)
    canary_aucs: dict[str, float] = {}
    raw_aucs: dict[str, float] = {}
    for i, name in enumerate(feat_names):
        col = np.nan_to_num(X_all[:, i], nan=0.0)
        raw = float(roc_auc_score(y_true, col)) if np.ptp(col) > 0 else 0.5
        sym = max(raw, 1.0 - raw)
        raw_aucs[name] = round(raw, 6)
        canary_aucs[name] = round(sym, 6)

    p_col = np.nan_to_num(phys_prior[ys, xs], nan=0.0)
    p_raw = float(roc_auc_score(y_true, p_col)) if np.ptp(p_col) > 0 else 0.5
    p_sym = max(p_raw, 1.0 - p_raw)
    raw_aucs["cgji_phys_prior"] = round(p_raw, 6)
    canary_aucs["cgji_phys_prior"] = round(p_sym, 6)

    max_feat = max(canary_aucs, key=canary_aucs.get)
    max_auc = canary_aucs[max_feat]
    return {
        "evaluator_version": holdout.EVALUATOR_VERSION,
        "n_withheld_positives": int(pos_y.size),
        "n_sampled_negatives": int(neg_y.size),
        "feature_names": feat_names + ["cgji_phys_prior"],
        "canary_aucs": canary_aucs,
        "raw_aucs": raw_aucs,
        "max_feature": max_feat,
        "max_symmetric_auc": max_auc,
        "all_below_0_90": bool(max_auc <= 0.90),
    }


def run_cgji_suite(
    ctx: holdout.HoldoutContext,
    ws: dict[str, Any],
    band_files: list[Path],
    target_dots: int = TARGET_DOTS,
    min_dist: float = MIN_DIST_PX,
    collar_px: float = COLLAR_PX,
) -> dict[str, Any]:
    """Run all 3 CGJI-HTB experiments with strict fold-local out-of-quadrant training & emission."""
    nms = ws["nms_mask"]
    phys_prior = ws["phys_prior"]
    derived_channels = ws["derived_channels"]

    cy, cx = np.nonzero(nms)
    X_nms, feat_names = extract_feature_matrix(cy, cx, band_files, derived_channels)

    ky, kx = np.ogrid[-3:4, -3:4]
    k300 = np.maximum(0.0, 1.0 - np.hypot(ky, kx) / 3.0).astype(np.float32)

    surf1 = np.where(nms, phys_prior, 0.0).astype(np.float32)
    oof_prob_sum = np.zeros(ctx.foot.shape, dtype=np.float32)
    oof_prob_cnt = np.zeros(ctx.foot.shape, dtype=np.float32)

    preds_exp1: dict[str, np.ndarray] = {}
    preds_exp2: dict[str, np.ndarray] = {}
    preds_exp3: dict[str, np.ndarray] = {}
    replay_hasher_1 = hashlib.sha256()
    replay_hasher_2 = hashlib.sha256()
    replay_hasher_3 = hashlib.sha256()

    for cell in ctx.cells:
        rng_cell = np.random.default_rng(20261027 + cell.seed * 100 + cell.fold)
        vis = cell.visible_full
        # Strict spatial & catalogue isolation: train ONLY on quadrants != cell.fold
        # and ONLY on cell.visible_full (which already excludes cell.withheld).
        train_mask = ctx.foot & (ctx.quad != cell.fold)
        pos_y, pos_x = np.nonzero(vis & train_mask)
        neg_mask = train_mask & ~binary_dilation(vis, iterations=3)
        neg_y, neg_x = np.nonzero(neg_mask)

        n_pos = min(pos_y.size, 25000)
        n_neg = min(neg_y.size, n_pos * 3)
        p_idx = rng_cell.choice(pos_y.size, size=n_pos, replace=False)
        n_idx = rng_cell.choice(neg_y.size, size=n_neg, replace=False)
        ys = np.concatenate([pos_y[p_idx], neg_y[n_idx]])
        xs = np.concatenate([pos_x[p_idx], neg_x[n_idx]])
        y_tr = np.concatenate([np.ones(n_pos, dtype=np.int8), np.zeros(n_neg, dtype=np.int8)])
        X_tr, _ = extract_feature_matrix(ys, xs, band_files, derived_channels)

        clf = HistGradientBoostingClassifier(
            max_iter=150,
            learning_rate=0.07,
            max_leaf_nodes=31,
            min_samples_leaf=40,
            l2_regularization=1.5,
            random_state=42 + cell.seed * 10 + cell.fold,
        )
        clf.fit(X_tr, y_tr, sample_weight=np.where(y_tr == 1, 2.0, 1.0))
        p_nms = clf.predict_proba(X_nms)[:, 1].astype(np.float32)

        prob_map = np.zeros(ctx.foot.shape, dtype=np.float32)
        prob_map[cy, cx] = p_nms

        q_mask = (ctx.quad == cell.fold) & nms
        oof_prob_sum[q_mask] += prob_map[q_mask]
        oof_prob_cnt[q_mask] += 1.0

        # Fold-local visible-fault collar ONLY (withheld faults are never masked!)
        d_vis_full = distance_transform_edt(~vis)
        allow_vis = ctx.foot & (d_vis_full > collar_px)

        # Exp 1: Label-free CGJI-HTB physical NMS crest
        d1 = ranked_poisson(surf1, allow_vis, min_dist=min_dist, n_target=target_dots)
        sub1 = (d1[cell.bbox] & cell.active_sub).astype(np.uint8)
        preds_exp1[cell.key] = sub1
        replay_hasher_1.update(f"{cell.key}:{int(sub1.sum())}:".encode("utf-8"))
        replay_hasher_1.update(np.packbits(sub1).tobytes())

        # Exp 2: Quadrant-blocked fold-local OOF-HGB on 40-channel CGJI-HTB stack over NMS crest
        d2 = ranked_poisson(prob_map, allow_vis, min_dist=min_dist, n_target=target_dots)
        sub2 = (d2[cell.bbox] & cell.active_sub).astype(np.uint8)
        preds_exp2[cell.key] = sub2
        replay_hasher_2.update(f"{cell.key}:{int(sub2.sum())}:".encode("utf-8"))
        replay_hasher_2.update(np.packbits(sub2).tobytes())

        # Exp 3: Expected-300m-kernel-credit crest-coherent CGJI-HTB hybrid
        ek_prob = convolve(prob_map, k300, mode="constant", cval=0.0)
        hybrid_map = np.where(
            nms,
            (prob_map ** 0.55) * (ek_prob ** 0.25) * (phys_prior ** 0.20),
            0.0,
        ).astype(np.float32)
        d3 = ranked_poisson(hybrid_map, allow_vis, min_dist=min_dist, n_target=target_dots)
        sub3 = (d3[cell.bbox] & cell.active_sub).astype(np.uint8)
        preds_exp3[cell.key] = sub3
        replay_hasher_3.update(f"{cell.key}:{int(sub3.sum())}:".encode("utf-8"))
        replay_hasher_3.update(np.packbits(sub3).tobytes())

    oof_prob_full = np.where(oof_prob_cnt > 0, oof_prob_sum / np.maximum(oof_prob_cnt, 1.0), 0.0).astype(np.float32)
    ek_full = convolve(oof_prob_full, k300, mode="constant", cval=0.0)
    surf2_full = oof_prob_full
    surf3_full = np.where(
        nms,
        (oof_prob_full ** 0.55) * (ek_full ** 0.25) * (phys_prior ** 0.20),
        0.0,
    ).astype(np.float32)

    # Full-grid continuous surfaces for pre-placement Spearman audit across the footprint
    cont_surf1 = phys_prior
    cont_surf2 = unit_field(0.70 * oof_prob_full + 0.30 * phys_prior, ctx.foot)
    cont_surf3 = unit_field(0.70 * surf3_full + 0.30 * phys_prior, ctx.foot)

    d_full = distance_transform_edt(~ctx.labels)
    allow_b2 = ctx.foot & (d_full > collar_px)
    dots1_full = ranked_poisson(surf1, allow_b2, min_dist=min_dist, n_target=target_dots)
    dots2_full = ranked_poisson(surf2_full, allow_b2, min_dist=min_dist, n_target=target_dots)
    dots3_full = ranked_poisson(surf3_full, allow_b2, min_dist=min_dist, n_target=target_dots)

    return {
        "feature_names": feat_names,
        "EXP1_CGJI_PHYS_NMS": {
            "preds_oof": preds_exp1,
            "replay_sha256": replay_hasher_1.hexdigest(),
            "nms_surface": surf1,
            "continuous_surface": cont_surf1,
            "dots_full": dots1_full,
        },
        "EXP2_CGJI_OOF_HGB": {
            "preds_oof": preds_exp2,
            "replay_sha256": replay_hasher_2.hexdigest(),
            "nms_surface": surf2_full,
            "continuous_surface": cont_surf2,
            "dots_full": dots2_full,
        },
        "EXP3_CGJI_EK_HYBRID": {
            "preds_oof": preds_exp3,
            "replay_sha256": replay_hasher_3.hexdigest(),
            "nms_surface": surf3_full,
            "continuous_surface": cont_surf3,
            "dots_full": dots3_full,
        },
    }


def verify_cell_hidden_label_invariance(
    ctx: holdout.HoldoutContext,
    ws: dict[str, Any],
    band_files: list[Path],
    cell_index: int = 0,
    target_dots: int = TARGET_DOTS,
    min_dist: float = MIN_DIST_PX,
    collar_px: float = COLLAR_PX,
) -> dict[str, Any]:
    """Verify bit-for-bit invariance of fold-local HGB training & emission when withheld labels flip."""
    cell = ctx.cells[cell_index]
    nms = ws["nms_mask"]
    derived_channels = ws["derived_channels"]
    cy, cx = np.nonzero(nms)
    X_nms, _ = extract_feature_matrix(cy, cx, band_files, derived_channels)

    def _run_one(corrupt_withheld: bool) -> np.ndarray:
        rng_cell = np.random.default_rng(20261027 + cell.seed * 100 + cell.fold)
        labels_view = ctx.labels.copy()
        if corrupt_withheld:
            # Invert all non-visible pixels in the test quadrant including cell.truth_coords
            ty, tx = cell.truth_coords
            y0, x0 = cell.bbox[0].start, cell.bbox[1].start
            assert not bool(cell.visible_full[ty + y0, tx + x0].any())
            withheld_mask = (ctx.quad == cell.fold) & ~cell.visible_full
            labels_view[withheld_mask] = ~labels_view[withheld_mask]
        vis = cell.visible_full & labels_view
        train_mask = ctx.foot & (ctx.quad != cell.fold)
        pos_y, pos_x = np.nonzero(vis & train_mask)
        neg_mask = train_mask & ~binary_dilation(vis, iterations=3)
        neg_y, neg_x = np.nonzero(neg_mask)
        n_pos = min(pos_y.size, 25000)
        n_neg = min(neg_y.size, n_pos * 3)
        p_idx = rng_cell.choice(pos_y.size, size=n_pos, replace=False)
        n_idx = rng_cell.choice(neg_y.size, size=n_neg, replace=False)
        ys = np.concatenate([pos_y[p_idx], neg_y[n_idx]])
        xs = np.concatenate([pos_x[p_idx], neg_x[n_idx]])
        y_tr = np.concatenate([np.ones(n_pos, dtype=np.int8), np.zeros(n_neg, dtype=np.int8)])
        X_tr, _ = extract_feature_matrix(ys, xs, band_files, derived_channels)
        clf = HistGradientBoostingClassifier(
            max_iter=150,
            learning_rate=0.07,
            max_leaf_nodes=31,
            min_samples_leaf=40,
            l2_regularization=1.5,
            random_state=42 + cell.seed * 10 + cell.fold,
        )
        clf.fit(X_tr, y_tr, sample_weight=np.where(y_tr == 1, 2.0, 1.0))
        p_nms = clf.predict_proba(X_nms)[:, 1].astype(np.float32)
        prob_map = np.zeros(ctx.foot.shape, dtype=np.float32)
        prob_map[cy, cx] = p_nms
        d_vis_full = distance_transform_edt(~vis)
        allow_vis = ctx.foot & (d_vis_full > collar_px)
        d2 = ranked_poisson(prob_map, allow_vis, min_dist=min_dist, n_target=target_dots)
        return (d2[cell.bbox] & cell.active_sub).astype(np.uint8)

    out_clean = _run_one(False)
    out_perturbed = _run_one(True)
    max_diff = int(np.max(np.abs(out_clean.astype(np.int16) - out_perturbed.astype(np.int16))))
    return {
        "cell_key": cell.key,
        "invariance_verified": bool(max_diff == 0),
        "max_abs_diff": max_diff,
        "n_dots_emitted_in_cell": int(out_clean.sum()),
    }
