"""H44-1 (SPCP): SAR-PU Propensity-Debiased Potential-Field Curvature Tensor &
Hydrothermal-Conduit Breach Detector for the DOE GEMS Prize.

Pre-registered in ``docs/research/h44-spcp-preregistration-20261026.md`` before execution.
Memory-engineered (< 650 MB peak RSS) for 3.8 GiB zero-swap sandboxes.

Key scientific & engineering properties:
1. Reuses the shared 35-channel cached template stack (``.cache/gems_work/feature_stack.npy``),
   shared holdout engine (``gems32.holdout`` / ``scripts/evaluate_holdout.py``), exact 300 m
   lazy-greedy submodular emitter (``gems32.emitter.emit``), and canonical GeoTIFF writer
   (``scripts/submission_writer.py``).
2. Fixes ``IR-32-DOC-BAND05-01`` (uses actual Band 05 ``iso_grav_anom_slope``, Band 17
   ``cond_surf``, and Band 18 signed ``iso_grav_anom_hg``) and ``IR-A8A-PU-BIAS-01`` (replaces
   naive ``y=0`` binary suppression of unmapped faults with fold-local Bekker-Davis ``SAR-PU``
   observability-propensity debiasing + reliable-negative screening + cover-adaptive subsurface
   curvature/conduit transfer).
3. Computes zero catalogue-derived or SGMC-derived features: ``labels.tif``,
   ``existing_faults.tif``, ``derived_sgmc_faults_100m_u8.tif``, ``gdr_qfaults_traces.csv``, and
   CSV ``dist_known_fault_px`` columns are strictly excluded and asserted absent.
"""

from __future__ import annotations

import gc
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy.ndimage import binary_dilation, gaussian_filter
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from . import emitter, mdrc

SPCP_EXTRA_CHANNELS: tuple[str, ...] = (
    "grav_hgrad_kneg_s12",
    "grav_hgrad_kneg_s25",
    "rtp_hgrad_kneg_s12",
    "rtp_hgrad_kneg_s25",
    "pf_curv_strike_concord",
    "grav_saddle_polarity",
    "roest_as_shallow_basin",
    "mag_demag_trough",
    "k_th_potassic_excess",
    "cond_nuisance_resid_edge",
    "gdr_geotherm_upflow",
    "hydrothermal_breach_index",
    "lidar_valid_flag",
    "lidar_tectonic_dipole",
    "lahontan_contour_orthog",
    "lidar_lahontan_debiased",
    "piedmont_burial_index",
    "transtensional_obliquity",
    "up150_basement_persistence",
    "spcp_unsup_composite",
)

OBSERVABILITY_INDICES_IN_EXTRA: tuple[int, ...] = (12, 16)  # lidar_valid_flag, piedmont_burial_index
OBSERVABILITY_INDICES_IN_BASE: tuple[int, ...] = (14, 18, 24)  # B15 depth_to_base, B19 slope, relief5


def _sigmoid_f32(x: np.ndarray) -> np.ndarray:
    z = np.clip(x, -25.0, 25.0).astype(np.float32, copy=False)
    return (1.0 / (1.0 + np.exp(-z))).astype(np.float32)


def robust_unit_f32(a: np.ndarray, valid: np.ndarray, pct: float = 99.4) -> np.ndarray:
    """Fast float32-only median/IQR scaling mapped into [0, 1] inside `valid` (< 50 MB RAM)."""
    out = np.zeros(a.shape, dtype=np.float32)
    v = valid & np.isfinite(a)
    if not v.any():
        return out
    sub = a[v][::4]
    if sub.size == 0:
        sub = a[v]
    med = np.float32(np.median(sub))
    q25, q75 = np.percentile(sub, [25.0, 75.0])
    scale = np.float32(max(float(q75 - q25) / 1.349, 1e-6))
    z_sub = (sub - med) / scale
    hi = np.float32(max(float(np.percentile(z_sub, pct)), 1e-6))
    out[v] = np.clip(((a[v] - med) / scale) / hi, 0.0, 1.0)
    return out


def _rank_unit_f32(a: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Fast quantile-interpolated rank normalization onto [0, 1] inside `valid` (< 50 MB RAM)."""
    out = np.zeros(a.shape, dtype=np.float32)
    v = valid & np.isfinite(a)
    if not v.any():
        return out
    sub = a[v][::4]
    if sub.size < 16:
        sub = a[v]
    qs = np.linspace(0.0, 100.0, 513)
    knots = np.percentile(sub, qs).astype(np.float32)
    probs = (qs / 100.0).astype(np.float32)
    # Deduplicate knots for monotone interpolation
    uk, idx = np.unique(knots, return_index=True)
    if uk.size < 2:
        return out
    out[v] = np.interp(a[v], uk, probs[idx]).astype(np.float32)
    return out


def principal_negative_curvature_and_strike(
    surface: np.ndarray, sigma: float
) -> tuple[np.ndarray, np.ndarray]:
    """Phillips et al. (2007) most-negative principal curvature -min(l1, l2, 0) and strike angle."""
    s = surface.astype(np.float32, copy=False)
    axx = gaussian_filter(s, sigma, order=(0, 2), mode="nearest")
    ayy = gaussian_filter(s, sigma, order=(2, 0), mode="nearest")
    axy = gaussian_filter(s, sigma, order=(1, 1), mode="nearest")
    half_diff = np.float32(0.5) * (axx - ayy)
    rad = np.sqrt(np.maximum(half_diff * half_diff + axy * axy, np.float32(0.0)))
    lam_min = np.float32(0.5) * (axx + ayy) - rad
    k_neg = np.maximum(-lam_min, np.float32(0.0))

    phi_norm = np.float32(0.5) * np.arctan2(np.float32(2.0) * axy, (axx - ayy) + np.float32(1e-12))
    c, sn = np.cos(phi_norm), np.sin(phi_norm)
    d1 = axx * c * c + np.float32(2.0) * axy * c * sn + ayy * sn * sn
    d2 = axx * sn * sn - np.float32(2.0) * axy * c * sn + ayy * c * c
    norm_angle = np.where(d1 <= d2, phi_norm, phi_norm + np.float32(0.5 * np.pi))
    strike_angle = (norm_angle + np.float32(0.5 * np.pi)).astype(np.float32)
    return k_neg.astype(np.float32), strike_angle


def principal_positive_trough_curvature(surface: np.ndarray, sigma: float) -> np.ndarray:
    """Most-positive principal curvature max(l1, l2, 0) isolating narrow demagnetization troughs."""
    s = surface.astype(np.float32, copy=False)
    axx = gaussian_filter(s, sigma, order=(0, 2), mode="nearest")
    ayy = gaussian_filter(s, sigma, order=(2, 0), mode="nearest")
    axy = gaussian_filter(s, sigma, order=(1, 1), mode="nearest")
    rad = np.sqrt(np.maximum((np.float32(0.5) * (axx - ayy)) ** 2 + axy * axy, np.float32(0.0)))
    lam_max = np.float32(0.5) * (axx + ayy) + rad
    return np.maximum(lam_max, np.float32(0.0)).astype(np.float32)


def _grad_mag(a: np.ndarray, sigma: float = 1.0) -> np.ndarray:
    src = gaussian_filter(a.astype(np.float32, copy=False), sigma, mode="nearest") if sigma > 0 else a
    gy = gaussian_filter(src, 0.8, order=(1, 0), mode="nearest") if sigma == 0 else np.gradient(src, axis=0)
    gx = gaussian_filter(src, 0.8, order=(0, 1), mode="nearest") if sigma == 0 else np.gradient(src, axis=1)
    return np.hypot(gx, gy).astype(np.float32)


def _disk_mask(radius_px: float) -> np.ndarray:
    r = int(np.ceil(radius_px))
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
    return (yy * yy + xx * xx) <= radius_px * radius_px


def _build_gdr_geotherm_upflow(ddir: Path, shape: tuple[int, int], foot: np.ndarray) -> np.ndarray:
    """Build label-free geothermal conduit halo from GDR #1391 well/spring & volcanic vent tables."""
    ws_path = ddir / "external" / "gdr_wellspring_in_footprint.csv"
    vv_path = ddir / "external" / "gdr_volcanic_vents_in_footprint.csv"
    src_grid = np.zeros(shape, dtype=np.float32)

    ws = pd.read_csv(ws_path)
    if "dist_known_fault_px" in ws.columns:
        ws = ws.drop(columns=["dist_known_fault_px"])
    assert "dist_known_fault_px" not in ws.columns

    t_cols = [c for c in ("temp_c", "geothermquartz_c", "geothermchalc_c", "geothermcat_c") if c in ws.columns]
    t_max = ws[t_cols].apply(pd.to_numeric, errors="coerce").max(axis=1).fillna(0.0).to_numpy(dtype=np.float32)
    excess = np.clip((t_max - 45.0) / 140.0, 0.0, 2.5).astype(np.float32)
    rows = np.clip(ws["row"].to_numpy(dtype=np.int32), 0, shape[0] - 1)
    cols = np.clip(ws["col"].to_numpy(dtype=np.int32), 0, shape[1] - 1)
    hot = excess > 0.0
    np.maximum.at(src_grid, (rows[hot], cols[hot]), excess[hot])

    if vv_path.exists():
        vv = pd.read_csv(vv_path)
        if "dist_known_fault_px" in vv.columns:
            vv = vv.drop(columns=["dist_known_fault_px"])
        assert "dist_known_fault_px" not in vv.columns
        vr = np.clip(vv["row"].to_numpy(dtype=np.int32), 0, shape[0] - 1)
        vc = np.clip(vv["col"].to_numpy(dtype=np.int32), 0, shape[1] - 1)
        np.maximum.at(src_grid, (vr, vc), np.float32(1.25))

    halo = np.float32(0.60) * gaussian_filter(src_grid, sigma=3.5, mode="nearest") + np.float32(
        0.40
    ) * gaussian_filter(src_grid, sigma=10.0, mode="nearest")
    return robust_unit_f32(halo, foot, pct=99.2)


def build_spcp_extra_stack(
    ddir: Path, base_stack_path: Path, out_path: Path | None = None, log=print
) -> tuple[np.ndarray, dict]:
    """Stream-build the 20 label-free SPCP channels into a disk-backed memmap (< 550 MB peak RAM)."""
    base = np.load(base_stack_path, mmap_mode="r")
    h, w, n_base = base.shape
    assert n_base == 35, f"Expected 35-channel template stack, got {n_base}"
    with rasterio.open(ddir / "sample_submission.tif") as ds:
        foot = np.isfinite(ds.read(1))

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        extra = np.lib.format.open_memmap(
            out_path, mode="w+", dtype=np.float32, shape=(h, w, len(SPCP_EXTRA_CHANNELS))
        )
    else:
        extra = np.zeros((h, w, len(SPCP_EXTRA_CHANNELS)), dtype=np.float32)

    # --- Group 1: Phillips (2007) Gravity & RTP Horizontal-Gradient Curvature Tensor (ch 0..4) ---
    grav_slope = np.array(base[:, :, 4], dtype=np.float32)   # B05: iso_grav_anom_slope
    rtp_edge = np.array(base[:, :, 27], dtype=np.float32)    # |grad_h(RTP)|
    gk12_raw, g_str12 = principal_negative_curvature_and_strike(grav_slope, sigma=1.2)
    gk25_raw, g_str25 = principal_negative_curvature_and_strike(grav_slope, sigma=2.5)
    del grav_slope
    mk12_raw, m_str12 = principal_negative_curvature_and_strike(rtp_edge, sigma=1.2)
    mk25_raw, m_str25 = principal_negative_curvature_and_strike(rtp_edge, sigma=2.5)
    del rtp_edge

    g12 = robust_unit_f32(gk12_raw, foot, pct=99.4); del gk12_raw
    g25 = robust_unit_f32(gk25_raw, foot, pct=99.4); del gk25_raw
    m12 = robust_unit_f32(mk12_raw, foot, pct=99.4); del mk12_raw
    m25 = robust_unit_f32(mk25_raw, foot, pct=99.4); del mk25_raw
    pf_concord = robust_unit_f32(
        0.55 * np.sqrt(g12 * m12) * (np.cos(g_str12 - m_str12) ** 2)
        + 0.45 * np.sqrt(g25 * m25) * (np.cos(g_str25 - m_str25) ** 2),
        foot,
        pct=99.5,
    )
    del g_str12, m_str12, g_str25, m_str25
    extra[:, :, 0] = g12
    extra[:, :, 1] = g25; del g25
    extra[:, :, 2] = m12
    extra[:, :, 3] = m25; del m25
    extra[:, :, 4] = pf_concord
    extra.flush() if hasattr(extra, "flush") else None
    gc.collect()
    log("  [SPCP] ch 0..4 (Phillips PF curvature tensor) built")

    # --- Group 2: Half-Graben Gravity Saddle + Roest 3D Analytic Signal (ch 5..6) ---
    grav_iso = np.array(base[:, :, 12], dtype=np.float32)    # B13
    grav_hg_x = np.array(base[:, :, 17], dtype=np.float32)   # B18 signed dg/dx
    gxx = gaussian_filter(grav_iso, 2.0, order=(0, 2), mode="nearest")
    gyy = gaussian_filter(grav_iso, 2.0, order=(2, 0), mode="nearest")
    gxy = gaussian_filter(grav_iso, 2.0, order=(1, 1), mode="nearest")
    del grav_iso
    saddle = np.sqrt(np.maximum(-(gxx * gyy - gxy * gxy), np.float32(0.0)))
    del gxx, gyy, gxy
    grav_saddle = robust_unit_f32(saddle * _grad_mag(grav_hg_x, sigma=1.5), foot, pct=99.5)
    del saddle, grav_hg_x
    extra[:, :, 5] = grav_saddle
    gc.collect()

    tmi_hg = np.array(base[:, :, 2], dtype=np.float32)       # B03
    tmi_vg = np.array(base[:, :, 8], dtype=np.float32)       # B09
    depth_base = np.array(base[:, :, 14], dtype=np.float32)  # B15
    as_amp = np.hypot(np.maximum(tmi_hg, np.float32(0.0)), tmi_vg * np.float32(100.0))
    del tmi_hg, tmi_vg
    z_as_m = np.float32(100.0) * as_amp / (_grad_mag(as_amp, sigma=1.2) + np.float32(1e-3))
    as_kneg, _ = principal_negative_curvature_and_strike(as_amp, sigma=1.3)
    del as_amp
    basin_gate = _sigmoid_f32((depth_base - np.float32(180.0)) / np.float32(140.0))
    shallow_gate = _sigmoid_f32((np.float32(0.65) * np.maximum(depth_base, np.float32(120.0)) - z_as_m) / np.float32(150.0))
    del z_as_m
    roest_as = robust_unit_f32(
        basin_gate * shallow_gate * robust_unit_f32(as_kneg, foot, pct=99.3), foot, pct=99.5
    )
    del as_kneg, basin_gate, shallow_gate
    extra[:, :, 6] = roest_as
    extra.flush() if hasattr(extra, "flush") else None
    gc.collect()
    log("  [SPCP] ch 5..6 (Gravity saddle + Roest 3D analytic signal) built")

    # --- Group 3: Hydrothermal Demagnetization, K/Th Excess, Nuisance-Resid MT & GDR Upflow (ch 7..11, 18) ---
    rtp = np.array(base[:, :, 1], dtype=np.float32)          # B02
    rtp_hp = rtp - gaussian_filter(rtp, sigma=6.0, mode="nearest")
    del rtp
    mag_demag = robust_unit_f32(
        np.maximum(-rtp_hp, np.float32(0.0)) * principal_positive_trough_curvature(rtp_hp, sigma=1.4),
        foot,
        pct=99.5,
    )
    del rtp_hp
    extra[:, :, 7] = mag_demag
    gc.collect()

    with rasterio.open(ddir / "external" / "geodawn_rad_u8.tif") as ds:
        rad_k = ds.read(1).astype(np.float32)
        rad_th = ds.read(2).astype(np.float32)
    rad_v = foot & (rad_k > 0) & (rad_th > 0)
    if rad_v.any():
        ks = rad_k[rad_v][::4].astype(np.float64)
        ths = rad_th[rad_v][::4].astype(np.float64)
        th_m, k_m = float(ths.mean()), float(ks.mean())
        slope_kt = float(np.dot(ths - th_m, ks - k_m) / (np.dot(ths - th_m, ths - th_m) + 1e-6))
        k_resid = np.where(rad_v, np.maximum(rad_k - (k_m + slope_kt * (rad_th - th_m)), 0.0), 0.0).astype(np.float32)
    else:
        k_resid = np.zeros((h, w), dtype=np.float32)
    del rad_k, rad_th, rad_v
    k_th_excess = robust_unit_f32(
        np.float32(0.55) * gaussian_filter(k_resid, 1.5, mode="nearest") + np.float32(0.45) * _grad_mag(k_resid, 1.5),
        foot,
        pct=99.4,
    )
    del k_resid
    extra[:, :, 8] = k_th_excess
    gc.collect()

    det_elev = np.array(base[:, :, 11], dtype=np.float32)    # B12
    cond_surf = np.array(base[:, :, 16], dtype=np.float32)   # B17
    elev_slope = np.array(base[:, :, 18], dtype=np.float32)  # B19
    # Fit nuisance regression on stride-8 subsample (< 8 MB!) and evaluate over footprint
    fy, fx = np.nonzero(foot)
    fys, fxs = fy[::8], fx[::8]
    e_mean, e_std = float(det_elev[fys, fxs].mean()), float(det_elev[fys, fxs].std()) + 1e-6
    X_sub = np.column_stack(
        [
            np.ones(fys.size, dtype=np.float64),
            (det_elev[fys, fxs] - e_mean) / e_std,
            (np.log1p(np.maximum(depth_base[fys, fxs], 0.0)) - 4.0) / 2.5,
            np.log1p(np.maximum(elev_slope[fys, fxs], 0.0)),
            ((det_elev[fys, fxs] - e_mean) / e_std) ** 2,
            ((np.log1p(np.maximum(depth_base[fys, fxs], 0.0)) - 4.0) / 2.5) ** 2,
        ]
    )
    coef, *_ = np.linalg.lstsq(X_sub, cond_surf[fys, fxs].astype(np.float64), rcond=None)
    del X_sub, fy, fx, fys, fxs
    x1 = (det_elev - np.float32(e_mean)) / np.float32(e_std)
    x2 = (np.log1p(np.maximum(depth_base, np.float32(0.0))) - np.float32(4.0)) / np.float32(2.5)
    x3 = np.log1p(np.maximum(elev_slope, np.float32(0.0)))
    pred_cond = (
        np.float32(coef[0])
        + np.float32(coef[1]) * x1
        + np.float32(coef[2]) * x2
        + np.float32(coef[3]) * x3
        + np.float32(coef[4]) * (x1 * x1)
        + np.float32(coef[5]) * (x2 * x2)
    )
    del x1, x2, x3
    cond_resid = np.where(foot, cond_surf - pred_cond, np.float32(0.0))
    del cond_surf, pred_cond
    cond_edge = robust_unit_f32(_grad_mag(cond_resid, sigma=1.5), foot, pct=99.4)
    del cond_resid
    extra[:, :, 9] = cond_edge

    gdr_upflow = _build_gdr_geotherm_upflow(ddir, (h, w), foot)
    extra[:, :, 10] = gdr_upflow
    hydro_breach = robust_unit_f32(
        (np.float32(0.45) * mag_demag + np.float32(0.55) * pf_concord + np.float32(0.25) * grav_saddle)
        * (np.float32(0.45) * k_th_excess + np.float32(0.55) * cond_edge)
        * (np.float32(0.40) + np.float32(0.60) * gdr_upflow),
        foot,
        pct=99.6,
    )
    del mag_demag, gdr_upflow
    extra[:, :, 11] = hydro_breach

    with rasterio.open(ddir / "external" / "geodawn_extensions_u8.tif") as ds:
        tmi_up150 = ds.read(4).astype(np.float32)
    up_v = foot & (tmi_up150 > 0)
    up_med = np.float32(np.median(tmi_up150[up_v][::4])) if up_v.any() else np.float32(0.0)
    tmi_up150 = np.where(up_v, tmi_up150, up_med)
    del up_v
    up150_grad = _grad_mag(tmi_up150, sigma=1.5)
    del tmi_up150
    tmi_grad = _grad_mag(np.array(base[:, :, 13], dtype=np.float32), sigma=1.5)
    tmi_p50 = np.float32(np.median(tmi_grad[foot][::4]))
    up150_pers = robust_unit_f32(up150_grad * (up150_grad / (tmi_grad + tmi_p50 + np.float32(1e-4))), foot, pct=99.4)
    del up150_grad, tmi_grad
    extra[:, :, 18] = up150_pers
    extra.flush() if hasattr(extra, "flush") else None
    gc.collect()
    log("  [SPCP] ch 7..11, 18 (Hydrothermal demag + K/Th + residualized MT + GDR + up150) built")

    # --- Group 4: Valid-tile 1 m LiDAR Dipole + Lahontan Contour-Parallelism Veto (ch 12..17) ---
    with rasterio.open(ddir / "external" / "lidar_scarp_features_u8.tif") as ds:
        li_step = ds.read(3).astype(np.float32)
        li_lapn = ds.read(4).astype(np.float32)
        li_lapp = ds.read(5).astype(np.float32)
        li_down = ds.read(6).astype(np.float32)
        li_up = ds.read(7).astype(np.float32)
        li_coh = ds.read(10).astype(np.float32) / np.float32(255.0)
        li_strike_u8 = ds.read(11).astype(np.float32)
        li_valid = (ds.read(12) > 0) & foot

    lidar_valid_Frac = float(li_valid.sum() / foot.sum())
    extra[:, :, 12] = li_valid.astype(np.float32)
    face_asym = np.abs(li_down - li_up) / (li_down + li_up + np.float32(6.0))
    del li_down, li_up
    li_raw = (
        li_step
        * np.sqrt(np.maximum(li_lapn * li_lapp, np.float32(0.0)))
        * (np.float32(0.35) + np.float32(0.65) * face_asym)
        * (np.float32(0.25) + np.float32(0.75) * li_coh)
    )
    del li_step, li_lapn, li_lapp, face_asym, li_coh
    li_unit = _rank_unit_f32(li_raw, li_valid)
    del li_raw

    dem_r1 = np.array(base[:, :, 21], dtype=np.float32)
    dem_r2 = np.array(base[:, :, 22], dtype=np.float32)
    dem_fb = _rank_unit_f32(np.float32(0.6) * np.maximum(dem_r1, 0.0) + np.float32(0.4) * np.maximum(dem_r2, 0.0), foot)
    del dem_r1, dem_r2
    lidar_dipole = np.where(li_valid, li_unit, np.float32(0.90) * dem_fb).astype(np.float32)
    lidar_dipole[~foot] = 0.0
    del li_unit, dem_fb
    extra[:, :, 13] = lidar_dipole

    ey = gaussian_filter(det_elev, sigma=2.2, order=(1, 0), mode="nearest")
    ex = gaussian_filter(det_elev, sigma=2.2, order=(0, 1), mode="nearest")
    theta_contour = np.arctan2(-ex, ey + np.float32(1e-12))
    del ey, ex
    _, dem_strike = principal_negative_curvature_and_strike(det_elev, sigma=1.5)
    del det_elev
    theta_scarp = np.where(li_valid, (li_strike_u8 / np.float32(255.0)) * np.float32(np.pi), dem_strike)
    del li_strike_u8, dem_strike, li_valid
    sin2_diff = (np.sin(theta_scarp - theta_contour) ** 2).astype(np.float32)
    del theta_scarp, theta_contour
    lahontan_orthog = np.where(
        foot, np.maximum(sin2_diff, np.float32(0.55) * np.clip(elev_slope / np.float32(10.0), 0.0, 1.0)), np.float32(0.0)
    )
    del sin2_diff
    extra[:, :, 14] = lahontan_orthog
    lidar_debiased = robust_unit_f32(
        mdrc.directional_chain_max(lidar_dipole * (np.float32(0.30) + np.float32(0.70) * lahontan_orthog), foot, halflen=2),
        foot,
        pct=99.4,
    )
    del lidar_dipole, lahontan_orthog
    extra[:, :, 15] = lidar_debiased

    piedmont_burial = (
        _sigmoid_f32((depth_base - np.float32(150.0)) / np.float32(220.0))
        * np.exp(-np.clip(elev_slope, np.float32(0.0), np.float32(60.0)) / np.float32(6.5))
    ).astype(np.float32)
    piedmont_burial[~foot] = 0.0
    del depth_base, elev_slope
    extra[:, :, 16] = piedmont_burial

    shear = np.array(base[:, :, 6], dtype=np.float32)
    dilat = np.array(base[:, :, 7], dtype=np.float32)
    transtension = robust_unit_f32(np.maximum(shear, 0.0) * np.maximum(dilat + np.float32(2.0), 0.0), foot, pct=99.2)
    del shear, dilat
    extra[:, :, 17] = transtension

    # --- Group 5: Label-Free Multi-Pillar Physical Composite (ch 19) ---
    pillar_pf = np.clip(
        np.float32(0.34) * pf_concord
        + np.float32(0.24) * g12
        + np.float32(0.18) * m12
        + np.float32(0.14) * roest_as
        + np.float32(0.10) * up150_pers,
        0.0,
        1.0,
    )
    pillar_hydro = np.clip(
        np.float32(0.42) * hydro_breach
        + np.float32(0.28) * cond_edge
        + np.float32(0.18) * k_th_excess
        + np.float32(0.12) * grav_saddle,
        0.0,
        1.0,
    )
    del pf_concord, g12, m12, roest_as, up150_pers, hydro_breach, cond_edge, k_th_excess, grav_saddle
    w_sub = np.float32(0.38) + np.float32(0.34) * piedmont_burial
    unsup_raw = w_sub * (np.float32(0.62) * pillar_pf + np.float32(0.38) * pillar_hydro) + (
        np.float32(1.0) - w_sub
    ) * lidar_debiased
    synergy = np.sqrt(
        np.maximum(lidar_debiased, np.float32(0.02))
        * np.maximum(np.float32(0.60) * pillar_pf + np.float32(0.40) * pillar_hydro, np.float32(0.02))
    )
    del pillar_pf, pillar_hydro, lidar_debiased, piedmont_burial, w_sub
    extra[:, :, 19] = robust_unit_f32(
        (np.float32(0.65) * unsup_raw + np.float32(0.35) * synergy)
        * (np.float32(0.85) + np.float32(0.15) * transtension),
        foot,
        pct=99.6,
    )
    del unsup_raw, synergy, transtension
    if hasattr(extra, "flush"):
        extra.flush()
    gc.collect()
    log("  [SPCP] ch 12..19 (LiDAR dipole + Lahontan veto + multi-pillar composite) built")

    receipt = {
        "n_extra_channels": len(SPCP_EXTRA_CHANNELS),
        "channel_names": list(SPCP_EXTRA_CHANNELS),
        "shape": [h, w, len(SPCP_EXTRA_CHANNELS)],
        "lidar_valid_fraction": lidar_valid_Frac,
    }
    return extra, receipt


def run_leakage_canary(
    base_stack: np.ndarray,
    extra_stack: np.ndarray,
    base_names: list[str],
    ctx,
    max_auc: float = 0.90,
    stride: int = 4,
) -> dict:
    """Protocol Rule 4 single-feature leakage canary on withheld holdout positives vs active negatives."""
    pos_mask = np.zeros(ctx.foot.shape, dtype=bool)
    neg_mask = np.zeros(ctx.foot.shape, dtype=bool)
    for cell in ctx.cells:
        if cell.seed != 20:
            continue
        sl = cell.bbox
        sub_t = np.zeros(cell.active_sub.shape, dtype=bool)
        sub_t[cell.truth_coords] = True
        pos_mask[sl] |= sub_t
        neg_mask[sl] |= cell.active_sub & ~sub_t

    py, px = np.nonzero(pos_mask)
    ny, nx = np.nonzero(neg_mask)
    ny, nx = ny[::stride], nx[::stride]
    y_true = np.concatenate([np.ones(py.size, dtype=np.int8), np.zeros(ny.size, dtype=np.int8)])

    rows = []
    all_names = list(base_names) + list(SPCP_EXTRA_CHANNELS)
    n_base = base_stack.shape[2]
    for i, name in enumerate(all_names):
        plane = base_stack[:, :, i] if i < n_base else extra_stack[:, :, i - n_base]
        vals = np.concatenate([plane[py, px], plane[ny, nx]]).astype(np.float64)
        vals = np.nan_to_num(vals, nan=0.0, posinf=0.0, neginf=0.0)
        if np.ptp(vals) <= 1e-12:
            auc_dir = 0.5
        else:
            raw_auc = float(roc_auc_score(y_true, vals))
            auc_dir = max(raw_auc, 1.0 - raw_auc)
        rows.append({"channel": name, "oriented_auc": round(auc_dir, 6), "passed": bool(auc_dir <= max_auc)})

    worst = max(rows, key=lambda r: r["oriented_auc"])
    passed_all = all(r["passed"] for r in rows)
    return {
        "passed": passed_all,
        "threshold_auc": max_auc,
        "n_features_tested": len(rows),
        "max_oriented_auc": worst["oriented_auc"],
        "worst_channel": worst["channel"],
        "n_withheld_pos_tested": int(py.size),
        "n_active_neg_sampled": int(ny.size),
        "per_channel": rows,
    }


def _gather_features(
    base_stack: np.ndarray, extra_stack: np.ndarray | None, ys: np.ndarray, xs: np.ndarray
) -> np.ndarray:
    xb = np.asarray(base_stack[ys, xs, :], dtype=np.float32)
    if extra_stack is None:
        return xb
    xe = np.asarray(extra_stack[ys, xs, :], dtype=np.float32)
    return np.hstack([xb, xe])


def _predict_chunked(
    clf: HistGradientBoostingClassifier,
    base_stack: np.ndarray,
    extra_stack: np.ndarray | None,
    mask: np.ndarray,
    chunk_size: int = 250_000,
) -> np.ndarray:
    out = np.zeros(mask.shape, dtype=np.float32)
    ys, xs = np.nonzero(mask)
    for start in range(0, ys.size, chunk_size):
        sl = slice(start, min(start + chunk_size, ys.size))
        X = _gather_features(base_stack, extra_stack, ys[sl], xs[sl])
        out[ys[sl], xs[sl]] = clf.predict_proba(X)[:, 1].astype(np.float32)
    return out


def fit_predict_naive_binary(
    base_stack: np.ndarray,
    extra_stack: np.ndarray | None,
    train_region: np.ndarray,
    visible_faults: np.ndarray,
    predict_region: np.ndarray,
    seed: int = 44,
    neg_halo_px: float = 5.0,
    max_pos: int = 40_000,
    neg_ratio: int = 4,
) -> np.ndarray:
    """Standard binary HistGB baseline (`y=1` visible faults, `y=0` `d_vis > 5 px` inside `train_region`)."""
    rng = np.random.default_rng(seed)
    near_vis = binary_dilation(visible_faults, structure=_disk_mask(neg_halo_px))
    pos_y, pos_x = np.nonzero(train_region & visible_faults)
    neg_y, neg_x = np.nonzero(train_region & ~near_vis)
    del near_vis

    if pos_y.size > max_pos:
        pick_p = rng.choice(pos_y.size, size=max_pos, replace=False)
        pos_y, pos_x = pos_y[pick_p], pos_x[pick_p]
    n_neg = min(neg_y.size, pos_y.size * neg_ratio)
    pick_n = rng.choice(neg_y.size, size=n_neg, replace=False)
    neg_y, neg_x = neg_y[pick_n], neg_x[pick_n]

    ys = np.concatenate([pos_y, neg_y])
    xs = np.concatenate([pos_x, neg_x])
    y = np.concatenate([np.ones(pos_y.size, dtype=np.int32), np.zeros(neg_y.size, dtype=np.int32)])

    X = _gather_features(base_stack, extra_stack, ys, xs)
    clf = HistGradientBoostingClassifier(
        max_iter=160,
        learning_rate=0.055,
        max_leaf_nodes=31,
        min_samples_leaf=80,
        l2_regularization=2.5,
        random_state=seed,
    )
    clf.fit(X, y)
    del X, y, ys, xs
    return _predict_chunked(clf, base_stack, extra_stack, predict_region)


def fit_predict_sarpu_spcp(
    base_stack: np.ndarray,
    extra_stack: np.ndarray,
    train_region: np.ndarray,
    visible_faults: np.ndarray,
    predict_region: np.ndarray,
    foot: np.ndarray,
    seed: int = 44,
    neg_halo_px: float = 5.0,
    max_pos: int = 40_000,
    neg_ratio: int = 4,
    return_propensity: bool = False,
) -> tuple[np.ndarray, ...]:
    """Fold-local SAR-PU propensity-debiased HistGB + cover-adaptive physical curvature transfer.

    Returns ``(blended, p_sarpu)``; with ``return_propensity=True`` returns
    ``(blended, p_sarpu, e_pred)`` where ``e_pred`` is the normalised observability propensity on
    ``predict_region`` (0 elsewhere). Default behaviour is unchanged for existing callers.
    """
    rng = np.random.default_rng(seed)
    near_vis = binary_dilation(visible_faults, structure=_disk_mask(neg_halo_px))
    pos_y, pos_x = np.nonzero(train_region & visible_faults)
    bg_y, bg_x = np.nonzero(train_region & ~near_vis)
    del near_vis

    if pos_y.size > max_pos:
        pp = rng.choice(pos_y.size, size=max_pos, replace=False)
        pos_y, pos_x = pos_y[pp], pos_x[pp]

    def _obs_cols(ys: np.ndarray, xs: np.ndarray) -> np.ndarray:
        b_obs = np.asarray(base_stack[ys, xs][:, OBSERVABILITY_INDICES_IN_BASE], dtype=np.float32)
        e_obs = np.asarray(extra_stack[ys, xs][:, OBSERVABILITY_INDICES_IN_EXTRA], dtype=np.float32)
        return np.hstack([b_obs, e_obs])

    n_bg_prop = min(bg_y.size, pos_y.size * 3)
    pb = rng.choice(bg_y.size, size=n_bg_prop, replace=False)
    Z_prop = np.vstack([_obs_cols(pos_y, pos_x), _obs_cols(bg_y[pb], bg_x[pb])])
    y_prop = np.concatenate([np.ones(pos_y.size, dtype=np.int32), np.zeros(n_bg_prop, dtype=np.int32)])
    prop_clf = HistGradientBoostingClassifier(
        max_iter=85,
        learning_rate=0.05,
        max_leaf_nodes=15,
        min_samples_leaf=200,
        l2_regularization=5.0,
        random_state=seed,
    )
    prop_clf.fit(Z_prop, y_prop)
    del Z_prop, y_prop

    unsup_surface = extra_stack[:, :, -1]  # memmap slice: spcp_unsup_composite
    ty_s, tx_s = bg_y[pb], bg_x[pb]
    unsup_q90 = float(np.percentile(np.asarray(unsup_surface[ty_s, tx_s], dtype=np.float32), 90.0))

    e_pos_raw = prop_clf.predict_proba(_obs_cols(pos_y, pos_x))[:, 1].astype(np.float32)
    e_bg_sample = prop_clf.predict_proba(_obs_cols(ty_s, tx_s))[:, 1].astype(np.float32)
    e_lo = float(np.percentile(e_bg_sample, 5.0))
    e_hi = max(float(np.percentile(e_pos_raw, 95.0)), e_lo + 1e-4)

    def _norm_e(raw_e: np.ndarray) -> np.ndarray:
        return np.clip((raw_e - e_lo) / (e_hi - e_lo), 0.0, 1.0).astype(np.float32)

    e_pos = _norm_e(e_pos_raw)

    n_pool = min(bg_y.size, pos_y.size * (neg_ratio + 2))
    pn_pool = rng.choice(bg_y.size, size=n_pool, replace=False)
    cand_ny, cand_nx = bg_y[pn_pool], bg_x[pn_pool]
    del bg_y, bg_x
    e_cand = _norm_e(prop_clf.predict_proba(_obs_cols(cand_ny, cand_nx))[:, 1].astype(np.float32))
    u_cand = np.asarray(unsup_surface[cand_ny, cand_nx], dtype=np.float32)
    reliable = ~((e_cand < 0.50) & (u_cand >= unsup_q90))
    if int(reliable.sum()) >= pos_y.size:
        cand_ny, cand_nx = cand_ny[reliable], cand_nx[reliable]
    n_neg = min(cand_ny.size, pos_y.size * neg_ratio)
    cand_ny, cand_nx = cand_ny[:n_neg], cand_nx[:n_neg]

    w_pos = np.clip((e_pos + 0.10) ** (-0.65), 0.55, 4.25).astype(np.float32)
    w_pos *= float(pos_y.size) / float(w_pos.sum())
    w_neg = np.ones(n_neg, dtype=np.float32)

    ys = np.concatenate([pos_y, cand_ny])
    xs = np.concatenate([pos_x, cand_nx])
    y_fit = np.concatenate([np.ones(pos_y.size, dtype=np.int32), np.zeros(n_neg, dtype=np.int32)])
    w_fit = np.concatenate([w_pos, w_neg])

    X_fit = _gather_features(base_stack, extra_stack, ys, xs)
    det_clf = HistGradientBoostingClassifier(
        max_iter=175,
        learning_rate=0.05,
        max_leaf_nodes=31,
        min_samples_leaf=80,
        l2_regularization=3.0,
        random_state=seed + 100,
    )
    det_clf.fit(X_fit, y_fit, sample_weight=w_fit)
    del X_fit, y_fit, w_fit, ys, xs

    raw_prob = _predict_chunked(det_clf, base_stack, extra_stack, predict_region)
    py, px = np.nonzero(predict_region)
    e_pred = np.zeros(predict_region.shape, dtype=np.float32)
    for start in range(0, py.size, 300_000):
        sl = slice(start, min(start + 300_000, py.size))
        e_pred[py[sl], px[sl]] = _norm_e(
            prop_clf.predict_proba(_obs_cols(py[sl], px[sl]))[:, 1].astype(np.float32)
        )

    p_sarpu = np.zeros(predict_region.shape, dtype=np.float32)
    p_sarpu[predict_region] = np.clip(
        raw_prob[predict_region] / ((e_pred[predict_region] + np.float32(0.18)) ** np.float32(0.38)),
        0.0,
        1.0,
    )
    del raw_prob

    p_rank = _rank_unit_f32(p_sarpu, predict_region)
    r_rank = _rank_unit_f32(np.asarray(unsup_surface, dtype=np.float32), predict_region)
    lam = np.where(predict_region, np.float32(0.22) + np.float32(0.34) * (np.float32(1.0) - e_pred), np.float32(0.0))
    e_pred_keep = e_pred if return_propensity else None
    del e_pred
    blended = np.where(
        predict_region,
        (np.maximum(p_rank, np.float32(1e-5)) ** (np.float32(1.0) - lam))
        * (np.maximum(r_rank, np.float32(1e-5)) ** lam),
        np.float32(0.0),
    ).astype(np.float32)
    del p_rank, r_rank, lam
    if return_propensity:
        return blended, p_sarpu, e_pred_keep
    return blended, p_sarpu


def emit_crest_submodular(
    surface: np.ndarray,
    eligible_mask: np.ndarray,
    foot: np.ndarray,
    budget: int,
    support_mult: int = 5,
) -> tuple[np.ndarray, np.ndarray]:
    """Sharpen onto 1-px oriented crests, confine to top candidate crests in `eligible_mask`, and emit."""
    crest = mdrc.sharpen_ridge_crest(surface, foot)
    elig = eligible_mask & foot & (crest > 0)
    n_elig = int(elig.sum())
    if n_elig == 0 or budget <= 0:
        return np.zeros(surface.shape, dtype=bool), crest

    max_sup = max(budget * support_mult, min(n_elig, 25_000))
    if n_elig > max_sup:
        vals = crest[elig]
        thresh = float(np.partition(vals, n_elig - max_sup)[n_elig - max_sup])
        sup_mask = elig & (crest >= thresh)
    else:
        sup_mask = elig

    field = np.where(sup_mask, crest, 0.0).astype(np.float64)
    dots, _ = emitter.emit(field, budget=int(budget), prior_dti=0.0, gain_floor=0.0)
    del field
    return dots, crest
