"""Round-6 H36-1 (TDR-PDS): True Potential-Field Tilt-Phase, Depth-Persistent Magnetic
& Piedmont-Drainage Curvilinear Skeleton Detector.

Fixes repository-wide physical misidentifications:
- IR-32-BAND-02: Band 6 (`tc`) is radiometric Total Count (Spearman +0.9994 with GeoDAWN TC),
  not magnetic tilt angle. Computes true Miller & Singh (1994) potential-field tilt angles
  `arctan(tmi_vg / tmi_hg)` and `arctan(iso_grav_anom_vg / iso_grav_anom_slope)`, Cooper & Cowan
  (2006) horizontal tilt `TDX`, and 150 m upward-continuation magnetic survival (`TMI_up150`).
- IR-32-BAND-03: Band 18 (`iso_grav_anom_hg`) is signed d(g)/dx (Spearman +0.9438 with gx),
  encoding east- vs west-dipping half-graben polarity; its spatial gradient locates synthetic/
  antithetic accommodation zones and relay ramps.
- Combines 500 m fault-damage-halo-excluded Positive-Unlabeled (PU) spatial-CV HistGB with
  Steger (1998) transverse eigenvector Non-Maximum Suppression (1-px curvilinear crest
  extraction) prior to B=2 visible-fault gating and exact 300 m lazy-greedy submodular packing.

Strictly zero catalogue-derived features (`existing_faults.tif`, `labels.tif`,
`gdr_qfaults_traces.csv`, `derived_sgmc_faults_100m_u8.tif`, and CSV `dist_known_fault_px`
columns are never read by feature construction).
"""
from __future__ import annotations

import csv
import gc
import json
from pathlib import Path

import numpy as np
import rasterio
from numpy.lib.format import open_memmap
from scipy.ndimage import (
    convolve,
    distance_transform_edt,
    gaussian_filter,
    grey_closing,
    grey_opening,
    map_coordinates,
)
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score


H36_FEATURE_NAMES: tuple[str, ...] = (
    # Group A: True Miller-Singh Potential-Field Tilt & Upward Continuation (10)
    "tdr_mag_abs_inv",
    "tdr0_mag_crest",
    "tdx_mag",
    "tmi_up150_grad",
    "tmi_up150_survival",
    "rtp_line_s15",
    "rtp_line_s30",
    "tdr_grav_abs_inv",
    "tdr0_grav_crest",
    "grav_polarity_reversal",
    # Group B: Geomorphic Scarp, Drainage-Deflection & 1m LiDAR Piedmont (16)
    "elev_norm",
    "slope_raw",
    "slope_log",
    "dem_ridge_s10",
    "dem_ridge_s20",
    "dem_ridge_s35",
    "dem_break_pos",
    "dem_break_neg",
    "dem_tophat_w",
    "dem_tophat_b",
    "valley_chain_az16",
    "st_coherence_dem",
    "lidar_ex_step",
    "lidar_face_asym",
    "lidar_coh_cross",
    "lidar_relief",
    # Group C: Subsurface Basement, MT, Radiometric Alteration & Vent Corridors (14)
    "depth_base",
    "depth_base_grad",
    "piedmont_collar",
    "cond_log",
    "cond_grad",
    "cond_depth_coalign",
    "rad_tc",
    "rad_thk_resid",
    "rad_uth_grad",
    "rad_uk",
    "strain_dilat",
    "strain_shear",
    "strain_transtension",
    "vent_geotherm_corridor",
    # Group D: Regional Potential Field & Seismic Context (6)
    "grav_iso",
    "grav_slope",
    "grav_line_s25",
    "tmi_hg_log",
    "seis_deq_grad",
    "seis_ieq_geod2",
)


def _load_clean_band(work_dir: Path, idx: int, name: str, foot: np.ndarray) -> np.ndarray:
    arr = np.load(work_dir / "bands" / f"{idx:02d}_{name}.npy").astype(np.float32, copy=False)
    med = float(np.nanmedian(arr[foot]))
    out = np.where(np.isfinite(arr) & foot, arr, np.float32(med))
    return out.astype(np.float32, copy=False)


def _zscore_1d(vals: np.ndarray, clip: float = 10.0) -> np.ndarray:
    med = float(np.median(vals))
    mad = float(np.median(np.abs(vals - np.float32(med)))) * 1.4826
    scale = np.float32(mad if mad > 1e-6 else (float(np.std(vals)) + 1e-6))
    return np.clip((vals - np.float32(med)) / scale, -clip, clip).astype(np.float32)


def _zscore_foot(arr: np.ndarray, foot: np.ndarray, clip: float = 10.0) -> np.ndarray:
    out = np.zeros_like(arr, dtype=np.float32)
    out[foot] = _zscore_1d(arr[foot], clip=clip)
    return out


def _grad_mag(arr: np.ndarray, sigma: float = 1.0) -> np.ndarray:
    s = gaussian_filter(arr.astype(np.float32, copy=False), sigma=sigma) if sigma > 0 else arr.astype(np.float32, copy=False)
    gy, gx = np.gradient(s)
    return np.hypot(gx, gy).astype(np.float32, copy=False)


def _hessian_eigs(arr: np.ndarray, sigma: float, mode: str) -> np.ndarray:
    g = gaussian_filter(arr.astype(np.float32, copy=False), sigma=sigma)
    gy, gx = np.gradient(g)
    del g
    gyy, gyx = np.gradient(gy)
    del gy
    gxy, gxx = np.gradient(gx)
    del gx
    hxy = np.float32(0.5) * (gyx + gxy)
    del gyx, gxy
    diff = gyy - gxx
    disc = np.sqrt(np.maximum(diff * diff + np.float32(4.0) * hxy * hxy, np.float32(0.0)))
    del diff, hxy
    tr = gyy + gxx
    del gyy, gxx
    if mode == "bright_ridge":
        lam_min = np.float32(0.5) * (tr - disc)
        del tr, disc
        return np.maximum(-lam_min, np.float32(0.0))
    lam_max = np.float32(0.5) * (tr + disc)
    del tr, disc
    return np.maximum(lam_max, np.float32(0.0))


def _hessian_bright_ridge(arr: np.ndarray, sigma: float) -> np.ndarray:
    return _hessian_eigs(arr, sigma, "bright_ridge")


def _hessian_valley_trough(arr: np.ndarray, sigma: float) -> np.ndarray:
    return _hessian_eigs(arr, sigma, "valley_trough")


def _valley_collinear_chain(elev: np.ndarray, foot: np.ndarray) -> np.ndarray:
    v = np.float32(0.45) * _hessian_valley_trough(elev, 1.5)
    v += np.float32(0.35) * _hessian_valley_trough(elev, 3.0)
    v += np.float32(0.20) * _hessian_valley_trough(elev, 5.0)
    v_z = np.maximum(_zscore_foot(v, foot), np.float32(0.0))
    del v
    best = np.zeros_like(v_z, dtype=np.float32)
    for deg in (0, 22.5, 45, 67.5, 90, 112.5, 135, 157.5):
        th = np.deg2rad(deg)
        dy, dx = np.sin(th), np.cos(th)
        ker = np.zeros((9, 9), dtype=np.float32)
        for t in np.linspace(-4.0, 4.0, 17):
            ry = int(round(4 + t * dy))
            rx = int(round(4 + t * dx))
            if 0 <= ry < 9 and 0 <= rx < 9:
                ker[ry, rx] += np.float32(np.exp(-0.5 * (t / 2.5) ** 2))
        ker /= np.float32(max(float(ker.sum()), 1e-6))
        resp = convolve(v_z, ker, mode="nearest")
        np.maximum(best, resp, out=best)
        del resp
    best *= v_z
    del v_z
    return best


def _build_vent_geotherm_corridor(
    ddir: Path, shape: tuple[int, int], transform, rtp_ridge: np.ndarray, foot: np.ndarray
) -> np.ndarray:
    """H36-2: NNE-SSW anisotropic structural corridor around Quaternary volcanic vents and
    >=60 C geothermometer anomalies, modulated by RTP magnetic ridge strength.
    Strictly ignores `dist_known_fault_px`.
    """
    h, w = shape
    seed_w = np.zeros(shape, dtype=np.float32)
    inv_tf = ~transform

    vent_csv = ddir / "external" / "gdr_volcanic_vents_in_footprint.csv"
    if vent_csv.exists():
        with vent_csv.open(newline="") as f:
            for row in csv.DictReader(f):
                try:
                    x_utm = float(row["utm_e"])
                    y_utm = float(row["utm_n"])
                except (KeyError, ValueError):
                    continue
                col, rw = inv_tf * (x_utm, y_utm)
                iy, ix = int(round(rw)), int(round(col))
                if 0 <= iy < h and 0 <= ix < w and foot[iy, ix]:
                    seed_w[iy, ix] = max(seed_w[iy, ix], 2.0)

    ws_csv = ddir / "external" / "gdr_wellspring_in_footprint.csv"
    if ws_csv.exists():
        with ws_csv.open(newline="") as f:
            for row in csv.DictReader(f):
                temps = []
                for k in ("temp_c", "geothermquartz_c", "geothermchalc_c"):
                    val = row.get(k, "")
                    if val not in ("", None):
                        try:
                            fv = float(val)
                            if np.isfinite(fv) and 0.0 < fv < 400.0:
                                temps.append(fv)
                        except ValueError:
                            pass
                if not temps:
                    continue
                tmax = max(temps)
                if tmax < 60.0:
                    continue
                try:
                    x_utm = float(row["utm_e_nad83_11n"])
                    y_utm = float(row["utm_n_nad83_11n"])
                except (KeyError, ValueError):
                    continue
                col, rw = inv_tf * (x_utm, y_utm)
                iy, ix = int(round(rw)), int(round(col))
                if 0 <= iy < h and 0 <= ix < w and foot[iy, ix]:
                    wgt = float(np.clip((tmax - 50.0) / 120.0, 0.1, 1.8))
                    if wgt > seed_w[iy, ix]:
                        seed_w[iy, ix] = wgt

    corridor = np.float32(0.65) * gaussian_filter(seed_w, sigma=(12.0, 5.5))
    corridor += np.float32(0.35) * gaussian_filter(seed_w, sigma=(25.0, 10.0))
    del seed_w
    rtp_pos = np.maximum(_zscore_foot(rtp_ridge, foot), np.float32(0.0))
    corridor *= np.float32(0.4) + np.float32(0.6) * rtp_pos
    del rtp_pos
    return corridor


def build_h36_feature_matrix(
    work_dir: Path, ddir: Path, *, force_rebuild: bool = False
) -> tuple[np.ndarray, list[str], np.ndarray]:
    """Build or load cached 46-channel standardized physical feature matrix on the footprint
    as a memory-mapped float16 array `(5_167_373, 46)` (~475 MB on disk, minimal RSS).
    """
    foot = np.load(work_dir / "bands" / "_footprint.npy").astype(bool)
    n_foot = int(foot.sum())
    cache_npy = work_dir / "h36_tdr_pds_X_foot_f16.npy"
    cache_meta = work_dir / "h36_tdr_pds_meta.json"

    if cache_npy.exists() and cache_meta.exists() and not force_rebuild:
        meta = json.loads(cache_meta.read_text())
        if meta.get("names") == list(H36_FEATURE_NAMES) and meta.get("n_foot") == n_foot:
            mm = np.load(cache_npy, mmap_mode="r")
            return mm, list(H36_FEATURE_NAMES), foot

    with rasterio.open(ddir / "sample_submission.tif") as ds:
        transform = ds.transform
        shape = ds.shape

    mm = open_memmap(cache_npy, mode="w+", dtype=np.float16, shape=(n_foot, len(H36_FEATURE_NAMES)))
    idx_map = {n: i for i, n in enumerate(H36_FEATURE_NAMES)}

    def _write(name: str, arr2d: np.ndarray) -> None:
        j = idx_map[name]
        mm[:, j] = _zscore_1d(arr2d[foot], clip=10.0).astype(np.float16)

    # --- Group A + RTP ridge saved for Vent Corridor ---
    rtp = _load_clean_band(work_dir, 2, "rtp", foot)
    rtp_line_s15 = _hessian_bright_ridge(rtp, 1.5)
    _write("rtp_line_s15", rtp_line_s15)
    _write("rtp_line_s30", _hessian_bright_ridge(rtp, 3.0))
    del rtp
    gc.collect()

    tmi_hg = _load_clean_band(work_dir, 3, "tmi_hg", foot)
    tmi_vg = _load_clean_band(work_dir, 9, "tmi_vg", foot)
    hg_pos = np.maximum(tmi_hg, np.float32(0.0))
    del tmi_hg
    tdr_mag = np.arctan2(tmi_vg, hg_pos + np.float32(0.05))
    _write("tdr_mag_abs_inv", -np.abs(tdr_mag))
    as_mag = np.log1p(np.hypot(hg_pos, tmi_vg))
    _write("tdr0_mag_crest", np.exp(-np.abs(tdr_mag) / np.float32(0.35)) * as_mag)
    del tdr_mag, as_mag
    _write("tdx_mag", np.arctan2(hg_pos, np.abs(tmi_vg) + np.float32(0.05)))
    del tmi_vg
    tmi_hg_log = np.log1p(hg_pos)
    _write("tmi_hg_log", tmi_hg_log)
    del hg_pos

    with rasterio.open(ddir / "external" / "geodawn_extensions_u8.tif") as ds:
        tmi_up150 = ds.read(4).astype(np.float32)
    tmi_up150_grad = _grad_mag(tmi_up150, sigma=1.2)
    del tmi_up150
    _write("tmi_up150_grad", tmi_up150_grad)
    tmi_hg_zpos = np.maximum(_zscore_foot(tmi_hg_log, foot), np.float32(0.0))
    del tmi_hg_log
    up150_zpos = np.maximum(_zscore_foot(tmi_up150_grad, foot), np.float32(0.0))
    del tmi_up150_grad
    _write("tmi_up150_survival", up150_zpos / (tmi_hg_zpos + np.float32(0.35)))
    del tmi_hg_zpos, up150_zpos
    gc.collect()

    grav_slope = _load_clean_band(work_dir, 5, "iso_grav_anom_slope", foot)
    grav_vg = _load_clean_band(work_dir, 11, "iso_grav_anom_vg", foot)
    gsl_pos = np.maximum(grav_slope, np.float32(0.0))
    del grav_slope
    tdr_grav = np.arctan2(grav_vg, gsl_pos + np.float32(0.005))
    del grav_vg
    _write("tdr_grav_abs_inv", -np.abs(tdr_grav))
    _write("tdr0_grav_crest", np.exp(-np.abs(tdr_grav) / np.float32(0.35)) * gsl_pos)
    del tdr_grav
    _write("grav_slope", gsl_pos)
    _write("grav_line_s25", _hessian_bright_ridge(gsl_pos, 2.5))
    del gsl_pos

    grav_gx = _load_clean_band(work_dir, 18, "iso_grav_anom_hg", foot)
    _write("grav_polarity_reversal", _grad_mag(grav_gx, sigma=2.0))
    del grav_gx
    _write("grav_iso", _load_clean_band(work_dir, 13, "iso_grav_anom", foot))
    gc.collect()

    # --- Group B: Geomorphic Scarp, Drainage-Deflection & 1m LiDAR Piedmont ---
    elev = _load_clean_band(work_dir, 12, "det_elev", foot)
    slope = _load_clean_band(work_dir, 19, "det_elev_slope", foot)
    _write("elev_norm", elev)
    _write("slope_raw", slope)
    _write("slope_log", np.log1p(np.maximum(slope, np.float32(0.0))))
    _write("dem_ridge_s10", _hessian_bright_ridge(slope, 1.0))
    _write("dem_ridge_s20", _hessian_bright_ridge(slope, 2.0))
    _write("dem_ridge_s35", _hessian_bright_ridge(slope, 3.5))
    del slope
    _write("dem_break_pos", _hessian_bright_ridge(elev, 1.5))
    _write("dem_break_neg", _hessian_valley_trough(elev, 1.5))
    _write("dem_tophat_w", elev - grey_opening(elev, size=(7, 7)))
    _write("dem_tophat_b", grey_closing(elev, size=(7, 7)) - elev)
    _write("valley_chain_az16", _valley_collinear_chain(elev, foot))

    eg = gaussian_filter(elev, sigma=1.2)
    egy, egx = np.gradient(eg)
    del eg
    jxx = gaussian_filter(egx * egx, sigma=3.5)
    jyy = gaussian_filter(egy * egy, sigma=3.5)
    jxy = gaussian_filter(egx * egy, sigma=3.5)
    del egx, egy
    j_disc = np.sqrt(np.maximum((jxx - jyy) ** 2 + np.float32(4.0) * jxy * jxy, np.float32(0.0)))
    del jxy
    _write("st_coherence_dem", j_disc / (jxx + jyy + np.float32(1e-4)))
    del jxx, jyy, j_disc
    gc.collect()

    with rasterio.open(ddir / "external" / "lidar_scarp_features_u8.tif") as ds:
        lid_valid = (ds.read(12) > 0).astype(np.float32)
        _write("lidar_ex_step", (np.float32(0.5) * ds.read(1) + np.float32(0.5) * ds.read(3)) * lid_valid)
        _write("lidar_face_asym", np.abs(ds.read(6).astype(np.float32) - ds.read(7).astype(np.float32)) * lid_valid)
        _write("lidar_coh_cross", (ds.read(10).astype(np.float32) / np.float32(255.0)) * ds.read(8).astype(np.float32) * lid_valid)
        _write("lidar_relief", ds.read(9).astype(np.float32) * lid_valid)
        del lid_valid
    gc.collect()

    # --- Group C: Subsurface Basement, MT, Radiometric Alteration & Vent Corridors ---
    depth_pos = np.maximum(_load_clean_band(work_dir, 15, "depth_to_base_surf", foot), np.float32(0.0))
    dy_d, dx_d = np.gradient(gaussian_filter(depth_pos, sigma=1.5))
    depth_grad = np.hypot(dx_d, dy_d)
    _write("depth_base", depth_pos)
    _write("depth_base_grad", depth_grad)
    _write("piedmont_collar", np.exp(-((depth_pos - np.float32(250.0)) / np.float32(300.0)) ** 2) * depth_grad)
    del depth_pos

    cond_log = np.log1p(np.maximum(_load_clean_band(work_dir, 17, "cond_surf", foot), np.float32(0.0)))
    dy_c, dx_c = np.gradient(gaussian_filter(cond_log, sigma=1.5))
    _write("cond_log", cond_log)
    del cond_log
    _write("cond_grad", np.hypot(dx_c, dy_c))
    _write("cond_depth_coalign", np.abs(dx_d * dx_c + dy_d * dy_c) / (depth_grad + np.float32(1e-4)))
    del dx_d, dy_d, dx_c, dy_c, depth_grad
    gc.collect()

    _write("rad_tc", _load_clean_band(work_dir, 6, "tc", foot))
    with rasterio.open(ddir / "external" / "geodawn_extensions_u8.tif") as ds:
        thk = ds.read(1).astype(np.float32)
        uk = ds.read(2).astype(np.float32)
        uth = ds.read(3).astype(np.float32)
    el_f = elev[foot]
    thk_f = thk[foot]
    slope_reg = np.float32(np.cov(el_f, thk_f)[0, 1] / (np.var(el_f) + 1e-6))
    _write("rad_thk_resid", -(thk - slope_reg * (elev - np.float32(np.mean(el_f)))))
    del thk, el_f, thk_f, elev
    _write("rad_uth_grad", _grad_mag(uth, sigma=1.5))
    del uth
    _write("rad_uk", uk)
    del uk
    gc.collect()

    dilat = _load_clean_band(work_dir, 8, "geod_dilaterate", foot)
    shear = _load_clean_band(work_dir, 7, "geod_shearrate", foot)
    _write("strain_dilat", dilat)
    _write("strain_shear", shear)
    _write(
        "strain_transtension",
        np.maximum(_zscore_foot(dilat, foot), np.float32(0.0))
        * np.maximum(_zscore_foot(shear, foot), np.float32(0.0)),
    )
    del dilat, shear

    vent_corridor = _build_vent_geotherm_corridor(ddir, shape, transform, rtp_line_s15, foot)
    _write("vent_geotherm_corridor", vent_corridor)
    del vent_corridor, rtp_line_s15
    gc.collect()

    # --- Group D: Remaining Seismic & Strain Context ---
    deq = _load_clean_band(work_dir, 10, "deq_n100a15", foot)
    _write("seis_deq_grad", _grad_mag(np.log1p(np.maximum(deq, np.float32(0.0))), sigma=2.0))
    del deq
    ieq = _load_clean_band(work_dir, 16, "ieq_n100a15", foot)
    geod_2nd = _load_clean_band(work_dir, 4, "geod_2ndinv", foot)
    _write(
        "seis_ieq_geod2",
        np.float32(0.5) * _zscore_foot(ieq, foot) + np.float32(0.5) * _zscore_foot(geod_2nd, foot),
    )
    del ieq, geod_2nd
    mm.flush()
    del mm
    gc.collect()

    cache_meta.write_text(json.dumps({"n_foot": n_foot, "names": list(H36_FEATURE_NAMES)}, indent=2))
    mm_ro = np.load(cache_npy, mmap_mode="r")
    return mm_ro, list(H36_FEATURE_NAMES), foot


def run_single_feature_leakage_canary(
    X_foot: np.ndarray, names: list[str], foot: np.ndarray, ctx, max_allowed_auc: float = 0.90
) -> dict:
    """Protocol Rule 3: test every single feature alone on withheld hidden fault positives across
    all 8 hide-and-recover cells. Any feature with oriented ROC-AUC > 0.90 fails closed as leakage.
    """
    flat_idx = np.full(foot.shape, -1, dtype=np.int32)
    flat_idx[foot] = np.arange(int(foot.sum()), dtype=np.int32)

    rng = np.random.default_rng(20261026)
    pos_rows = []
    neg_rows = []
    for cell in ctx.cells:
        sl = cell.bbox
        idx_sub = flat_idx[sl]
        ty, tx = cell.truth_coords
        p_idx = idx_sub[ty, tx]
        p_idx = p_idx[p_idx >= 0]
        pos_rows.append(p_idx)

        truth_mask = np.zeros_like(cell.active_sub)
        truth_mask[ty, tx] = True
        neg_cand = idx_sub[cell.active_sub & ~truth_mask]
        neg_cand = neg_cand[neg_cand >= 0]
        k = min(len(neg_cand), max(len(p_idx) * 4, 4000))
        neg_rows.append(rng.choice(neg_cand, size=k, replace=False))

    p_all = np.concatenate(pos_rows)
    n_all = np.concatenate(neg_rows)
    eval_idx = np.concatenate([p_all, n_all])
    y_eval = np.concatenate([np.ones(len(p_all), dtype=np.int8), np.zeros(len(n_all), dtype=np.int8)])

    per_feature = {}
    worst_name = ""
    worst_auc = 0.5
    for j, name in enumerate(names):
        col = X_foot[eval_idx, j].astype(np.float32)
        raw_auc = float(roc_auc_score(y_eval, col))
        oriented_auc = max(raw_auc, 1.0 - raw_auc)
        per_feature[name] = {
            "raw_auc": round(raw_auc, 5),
            "oriented_auc": round(oriented_auc, 5),
        }
        if oriented_auc > worst_auc:
            worst_auc = oriented_auc
            worst_name = name

    passed = worst_auc <= max_allowed_auc
    if not passed:
        raise RuntimeError(
            f"LEAKAGE CANARY FAILED: feature {worst_name!r} achieved holdout AUC={worst_auc:.4f} > {max_allowed_auc}"
        )
    return {
        "passed": passed,
        "threshold": max_allowed_auc,
        "n_features": len(names),
        "n_withheld_pos_eval": int(len(p_all)),
        "n_active_neg_eval": int(len(n_all)),
        "max_oriented_auc": round(worst_auc, 5),
        "max_feature": worst_name,
        "per_feature": per_feature,
    }


def steger_curvilinear_crest(
    prob_map: np.ndarray,
    foot: np.ndarray,
    gate_mask: np.ndarray,
    *,
    sigma: float = 0.90,
    max_support: int = 210_000,
    curv_boost: float = 0.25,
) -> np.ndarray:
    """Steger (1998) sub-pixel curvilinear ridge NMS:
    extracts 1-pixel structural centerlines perpendicular to the local Hessian minimum-curvature
    eigenvector, keeping at most `max_support` crest pixels inside `foot & gate_mask`.
    """
    sm = gaussian_filter(prob_map.astype(np.float32, copy=False), sigma=sigma)
    gy, gx = np.gradient(sm)
    gyy, gyx = np.gradient(gy)
    del gy
    gxy, gxx = np.gradient(gx)
    del gx
    hxy = np.float32(0.5) * (gyx + gxy)
    del gyx, gxy

    diff = gyy - gxx
    disc = np.sqrt(np.maximum(diff * diff + np.float32(4.0) * hxy * hxy, np.float32(1e-12)))
    del diff
    lam_min = np.float32(0.5) * (gyy + gxx - disc)
    del disc

    vy = lam_min - gxx
    vx = hxy
    del hxy
    norm = np.hypot(vy, vx)
    degenerate = norm < np.float32(1e-6)
    inv_norm = np.float32(1.0) / np.maximum(norm, np.float32(1e-6))
    del norm
    vy = np.where(degenerate, np.where(gyy <= gxx, np.float32(1.0), np.float32(0.0)), vy * inv_norm)
    vx = np.where(degenerate, np.where(gyy <= gxx, np.float32(0.0), np.float32(1.0)), vx * inv_norm)
    del gyy, gxx, degenerate, inv_norm

    h, w = sm.shape
    yy = np.arange(h, dtype=np.float32)[:, None]
    xx = np.arange(w, dtype=np.float32)[None, :]
    coords_plus = np.empty((2, h, w), dtype=np.float32)
    coords_plus[0] = yy + vy
    coords_plus[1] = xx + vx
    p_plus = map_coordinates(sm, coords_plus, order=1, mode="nearest")
    coords_plus[0] = yy - vy
    coords_plus[1] = xx - vx
    del vy, vx
    p_minus = map_coordinates(sm, coords_plus, order=1, mode="nearest")
    del coords_plus

    is_crest = (sm >= p_plus) & (sm >= p_minus) & (lam_min < np.float32(0.0)) & foot & gate_mask
    del p_plus, p_minus
    neg_curv = np.maximum(-lam_min, np.float32(0.0))
    del lam_min
    curv_scale = float(np.percentile(neg_curv[is_crest], 95)) if is_crest.any() else 1.0
    curv_term = np.clip(neg_curv / np.float32(max(curv_scale, 1e-6)), np.float32(0.0), np.float32(2.0))
    del neg_curv

    crest_score = np.zeros_like(sm, dtype=np.float32)
    crest_score[is_crest] = sm[is_crest] * (np.float32(1.0) + np.float32(curv_boost) * curv_term[is_crest])
    del sm, curv_term

    n_c = int(is_crest.sum())
    if n_c > max_support:
        vals = crest_score[is_crest]
        thresh = float(np.partition(vals, n_c - max_support)[n_c - max_support])
        crest_score = np.where(crest_score >= np.float32(thresh), crest_score, np.float32(0.0))

    pos = crest_score > 0.0
    if pos.any():
        vmin = float(crest_score[pos].min())
        vmax = float(crest_score[pos].max())
        if vmax > vmin:
            crest_score[pos] = np.float32(0.05) + np.float32(0.95) * (crest_score[pos] - np.float32(vmin)) / np.float32(vmax - vmin)
        else:
            crest_score[pos] = np.float32(1.0)
    return crest_score


def train_pu_quadrant_oof(
    X_foot: np.ndarray,
    foot: np.ndarray,
    visible_labels: np.ndarray,
    quad: np.ndarray,
    *,
    collar_px: int = 15,
    halo_exclude_px: float = 5.0,
    neg_ratio: int = 4,
    seed: int = 42,
) -> tuple[np.ndarray, list[HistGradientBoostingClassifier]]:
    """Train 4 spatially-blocked PU HistGB models out-of-fold using ONLY `visible_labels`
    outside `quad == q` dilated by `collar_px` (1.5 km), excluding the 500 m fault-damage halo
    from negative sampling.
    """
    from scipy.ndimage import binary_dilation

    flat_idx = np.full(foot.shape, -1, dtype=np.int32)
    flat_idx[foot] = np.arange(int(foot.sum()), dtype=np.int32)

    d_vis = distance_transform_edt(~(visible_labels & foot)).astype(np.float32)
    oof_foot = np.zeros(int(foot.sum()), dtype=np.float32)
    models: list[HistGradientBoostingClassifier] = []

    for q in range(4):
        q_mask = (quad == q) & foot
        collar = binary_dilation(q_mask, structure=np.ones((3, 3), dtype=bool), iterations=collar_px) & foot
        train_region = foot & ~collar

        pos_idx = flat_idx[train_region & visible_labels]
        neg_pool = flat_idx[train_region & (d_vis > halo_exclude_px)]

        rng = np.random.default_rng(seed * 100 + q)
        n_neg = min(len(neg_pool), len(pos_idx) * neg_ratio)
        neg_idx = rng.choice(neg_pool, size=n_neg, replace=False)

        tr_idx = np.concatenate([pos_idx, neg_idx])
        y_tr = np.concatenate(
            [np.ones(len(pos_idx), dtype=np.int8), np.zeros(len(neg_idx), dtype=np.int8)]
        )
        perm = rng.permutation(len(tr_idx))
        X_tr = X_foot[tr_idx[perm]].astype(np.float32)
        y_tr = y_tr[perm]

        clf = HistGradientBoostingClassifier(
            max_iter=200,
            learning_rate=0.055,
            max_leaf_nodes=63,
            min_samples_leaf=80,
            l2_regularization=2.0,
            random_state=seed * 100 + q,
        )
        clf.fit(X_tr, y_tr)
        models.append(clf)

        te_idx = flat_idx[q_mask]
        chunk = 400_000
        for s in range(0, len(te_idx), chunk):
            sub = te_idx[s : s + chunk]
            oof_foot[sub] = clf.predict_proba(X_foot[sub].astype(np.float32))[:, 1].astype(np.float32)

        del X_tr, y_tr
        gc.collect()

    oof_map = np.zeros(foot.shape, dtype=np.float32)
    oof_map[foot] = oof_foot
    return oof_map, models
