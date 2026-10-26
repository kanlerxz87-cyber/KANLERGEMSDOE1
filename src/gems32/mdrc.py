"""MDRC (Multi-Domain Ridge-Crest Concordance) — Session arena/8a2ac062-gemsdoe32 (`A8A-H1`).

Single-lane implementation pre-registered in `docs/research/arena8a-preregistration-and-hypotheses.md`:
  - Reuses the shared 35-channel template feature stack (`src/gems32/features.py`), shared repaired
    visible-only holdout evaluator (`src/gems32/holdout.py`), exact 300 m submodular coverage emitter
    (`src/gems32/emitter.py`), and fail-closed GeoTIFF writer (`src/gems32/submission.py`).
  - Repairs two primary-data defects discovered in `GEMSDOE32`:
      1. `IR-32-BAND6-TC-01`: Band 6 (`tc`) is GeoDAWN Radiometric Total Count (r=0.9971), NOT magnetic
         tilt angle; true Miller & Singh (1994) RTP and TMI magnetic tilt zero-crossings and Salem et al.
         (2007) tilt-depth sharpness are computed here from Bands 2, 3, 9, 14.
      2. `IR-32-LIDAR-BANDS-01`: `external/lidar_scarp_features_u8.tif` has 12 bands (`12=valid`, 75.37%
         coverage); missing-tile cells (`valid == 0`) are kept as `NaN` for native tree missing-value
         routing and seamlessly quantile-imputed with 100 m DEM subtle-scarp ridges for domain composites.
  - Strictly excludes any catalogue-derived columns (`dist_known_fault_px` is explicitly dropped and
    asserted absent before computing GDR-1391 hydrothermal spring/geothermometer halos).
"""

from __future__ import annotations

import gc
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage
from scipy.ndimage import gaussian_filter

MDRC_EXTRA_CHANNELS: list[str] = [
    # Domain I: Tile-aware 1 m 3DEP LiDAR asymmetric tectonic scarp dipole (10 channels)
    "lidar_valid_flag",
    "lidar_step_max",
    "lidar_crest_toe_dipole",
    "lidar_onesided_polarity",
    "lidar_cross_tectonic",
    "lidar_coh100",
    "lidar_strike_cos2",
    "lidar_strike_sin2",
    "lidar_tectonic_scarp_score",
    "lidar_scarp_chain_500m",
    # Domain II: True Miller-Singh magnetic tilt-contact & Salem tilt-depth (4 channels)
    "mag_true_rtp_tilt_zero",
    "mag_true_tmi_tilt_zero",
    "mag_salem_tilt_depth_discord",
    "mag_up150_residual_ridge",
    # Domain III: Isostatic gravity inflection, basement step & concealment habitat (4 channels)
    "grav_vg_zero_hg_ridge",
    "grav_basement_step_align",
    "mt_cond_basement_edge",
    "piedmont_concealment_index",
    # Domain IV: GeoDAWN K/Th + magnetite-destruction + GDR-1391 hydrothermal conduits (4 channels)
    "rad_k_over_th_alteration_edge",
    "rad_uth_redox_anom",
    "hydrothermal_demag_claycap",
    "gdr_geotherm_transtension_halo",
]


def robust_unit(a: np.ndarray, valid: np.ndarray, pct: float = 99.5, clip_z: float = 6.0) -> np.ndarray:
    """Label-free median/IQR positive score mapped cleanly into [0, 1] over `valid` pixels."""
    out = np.zeros(a.shape, dtype=np.float32)
    v = valid & np.isfinite(a)
    if not v.any():
        return out
    vals = a[v].astype(np.float64)
    med = float(np.median(vals))
    q25, q75 = np.percentile(vals, [25.0, 75.0])
    scale = max(float(q75 - q25) / 1.349, 1e-6)
    z = (a.astype(np.float64) - med) / scale
    hi = max(float(np.percentile(z[v], pct)), 1e-6)
    out[v] = (np.clip(z[v] / hi, 0.0, clip_z / 6.0)).astype(np.float32)
    return np.clip(out, 0.0, 1.0)


def fill_median(a: np.ndarray, foot: np.ndarray, sigma: float = 0.0) -> np.ndarray:
    v = foot & np.isfinite(a)
    med = float(np.median(a[v])) if v.any() else 0.0
    out = np.where(v, a, med).astype(np.float32)
    if sigma > 0.0:
        out = gaussian_filter(out, sigma=sigma, mode="nearest").astype(np.float32)
    return out


def hessian_line_both_polarities(a: np.ndarray, sigma: float) -> np.ndarray:
    """Curvilinear Hessian line strength accepting ridge or trough maxima."""
    axx = gaussian_filter(a, sigma, order=(0, 2), mode="nearest")
    ayy = gaussian_filter(a, sigma, order=(2, 0), mode="nearest")
    axy = gaussian_filter(a, sigma, order=(1, 1), mode="nearest")
    tmp = np.sqrt(np.maximum(((axx - ayy) * 0.5) ** 2 + axy * axy, 0.0))
    l1 = (axx + ayy) * 0.5 + tmp
    l2 = (axx + ayy) * 0.5 - tmp
    big_abs = np.maximum(np.abs(l1), np.abs(l2))
    small_abs = np.minimum(np.abs(l1), np.abs(l2))
    # True curvilinear line has high cross-strike curvature and low along-strike curvature
    return np.maximum(big_abs - 0.5 * small_abs, 0.0).astype(np.float32)


def directional_chain_max(score: np.ndarray, foot: np.ndarray, halflen: int = 2) -> np.ndarray:
    """5-pixel directional mean along 8 principal orientations (rewards collinear scarplets)."""
    s = np.where(foot & np.isfinite(score), score, 0.0).astype(np.float32)
    dirs = [(1, 0), (0, 1), (1, 1), (1, -1), (2, 1), (1, 2), (2, -1), (1, -2)]
    best = np.zeros_like(s)
    for dy, dx in dirs:
        acc = s.copy()
        cnt = 1
        for k in range(1, halflen + 1):
            acc += np.roll(np.roll(s, k * dy, axis=0), k * dx, axis=1)
            acc += np.roll(np.roll(s, -k * dy, axis=0), -k * dx, axis=1)
            cnt += 2
        np.maximum(best, acc / float(cnt), out=best)
    best[~foot] = 0.0
    return best


def fft_first_vertical_derivative(a_filled: np.ndarray, dx_m: float = 100.0, smooth_sigma: float = 1.0) -> np.ndarray:
    """Potential-field vertical derivative via wavenumber multiplication |k| (Blakely, 1995)."""
    src = gaussian_filter(a_filled, sigma=smooth_sigma, mode="nearest") if smooth_sigma > 0 else a_filled
    h, w = src.shape
    fy = np.fft.fftfreq(h, d=dx_m) * 2.0 * np.pi
    fx = np.fft.fftfreq(w, d=dx_m) * 2.0 * np.pi
    ky, kx = np.meshgrid(fy, fx, indexing="ij")
    k = np.sqrt(kx * kx + ky * ky)
    dz = np.fft.ifft2(np.fft.fft2(src.astype(np.float64)) * k).real
    return dz.astype(np.float32)


def _sample_bilinear(field: np.ndarray, yy: np.ndarray, xx: np.ndarray) -> np.ndarray:
    h, w = field.shape
    y = np.clip(yy, 0.0, h - 1.001)
    x = np.clip(xx, 0.0, w - 1.001)
    y0 = y.astype(np.int32)
    x0 = x.astype(np.int32)
    wy = (y - y0).astype(np.float32)
    wx = (x - x0).astype(np.float32)
    return (
        (1.0 - wy) * (1.0 - wx) * field[y0, x0]
        + (1.0 - wy) * wx * field[y0, x0 + 1]
        + wy * (1.0 - wx) * field[y0 + 1, x0]
        + wy * wx * field[y0 + 1, x0 + 1]
    ).astype(np.float32)


def sharpen_ridge_crest(prob: np.ndarray, foot: np.ndarray) -> np.ndarray:
    """Oriented 1-px cross-strike crest concentration (prevents double-row blob emission)."""
    p = np.where(foot & np.isfinite(prob), prob, 0.0).astype(np.float32)
    ps = gaussian_filter(p, sigma=1.0, mode="nearest")
    # Hessian eigenvector of largest negative curvature gives normal to the ridge crest
    axx = gaussian_filter(p, sigma=1.2, order=(0, 2), mode="nearest")
    ayy = gaussian_filter(p, sigma=1.2, order=(2, 0), mode="nearest")
    axy = gaussian_filter(p, sigma=1.2, order=(1, 1), mode="nearest")
    # Normal direction angle phi where curvature is most negative across the ridge
    phi = 0.5 * np.arctan2(2.0 * axy, (axx - ayy) + 1e-12)
    # Test both perpendicular candidates (phi and phi + pi/2) to pick true across-ridge axis
    nx1, ny1 = np.cos(phi).astype(np.float32), np.sin(phi).astype(np.float32)
    c1 = np.abs(axx * nx1 * nx1 + 2.0 * axy * nx1 * ny1 + ayy * ny1 * ny1)
    c2 = np.abs(axx * (-ny1) * (-ny1) + 2.0 * axy * (-ny1) * nx1 + ayy * nx1 * nx1)
    use_perp = c2 > c1
    nx = np.where(use_perp, -ny1, nx1).astype(np.float32)
    ny = np.where(use_perp, nx1, ny1).astype(np.float32)

    h, w = p.shape
    gy, gx = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32), indexing="ij")
    step = 1.35
    p_plus = _sample_bilinear(ps, gy + step * ny, gx + step * nx)
    p_minus = _sample_bilinear(ps, gy - step * ny, gx - step * nx)
    flank_mean = 0.5 * (p_plus + p_minus)
    crest_prom = np.clip((ps - flank_mean) / (ps + 1e-4), 0.0, 1.0)
    is_local_crest = ((ps >= p_plus - 1e-6) & (ps >= p_minus - 1e-6)).astype(np.float32)

    out = p * (0.30 + 0.45 * np.sqrt(crest_prom) + 0.25 * is_local_crest)
    out[~foot] = 0.0
    return out.astype(np.float32)


def multi_domain_corroboration_gate(
    d1_scarp: np.ndarray,
    d2_mag: np.ndarray,
    d3_grav_mt: np.ndarray,
    d4_hydro: np.ndarray,
    foot: np.ndarray,
) -> np.ndarray:
    """Smooth corroboration multiplier rewarding >=2 independent physical domain lines."""
    stacked = np.stack(
        [
            np.clip(d1_scarp, 0.0, 1.0),
            np.clip(d2_mag, 0.0, 1.0),
            np.clip(d3_grav_mt, 0.0, 1.0),
            np.clip(d4_hydro, 0.0, 1.0),
        ],
        axis=0,
    )
    stacked.sort(axis=0)  # ascending: [0]=min, [1]=3rd, [2]=2nd-best, [3]=best
    second_best = stacked[2]
    third_best = stacked[1]
    corrob = np.clip((second_best + 0.5 * third_best) / 0.45, 0.0, 1.0)
    gate = (0.55 + 0.45 * corrob).astype(np.float32)
    gate[~foot] = 0.0
    return gate


def build_mdrc_extra_stack(
    ddir: Path,
    base_stack_path: Path,
    out_path: Path,
    foot: np.ndarray,
    log=print,
) -> dict:
    """Build the 22 label-free MDRC physical channels as a disk-backed float32 memmap."""
    h, w = foot.shape
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base = np.lib.format.open_memmap(base_stack_path, mode="r")
    mm = np.lib.format.open_memmap(
        out_path, mode="w+", dtype=np.float32, shape=(h, w, len(MDRC_EXTRA_CHANNELS))
    )

    # ---- Domain I: Tile-aware 1 m 3DEP LiDAR tectonic scarp dipole (ch 0..9) ----
    log("[MDRC] Domain I: reading 12-band 1 m LiDAR scarp features (valid-tile aware)")
    with rasterio.open(ddir / "external" / "lidar_scarp_features_u8.tif") as src:
        b3_step = src.read(3).astype(np.float32)
        b4_lapn = src.read(4).astype(np.float32)
        b5_lapp = src.read(5).astype(np.float32)
        b6_down = src.read(6).astype(np.float32)
        b7_up = src.read(7).astype(np.float32)
        b8_cross = src.read(8).astype(np.float32)
        b10_coh = src.read(10).astype(np.float32)
        b11_strk = src.read(11).astype(np.float32)
        b12_val = src.read(12)

    has_lidar = (b12_val > 0) & foot
    mm[:, :, 0] = np.where(foot, has_lidar.astype(np.float32), 0.0)

    def _nan_outside_lidar(arr: np.ndarray) -> np.ndarray:
        out = np.full((h, w), np.nan, dtype=np.float32)
        out[has_lidar] = arr[has_lidar]
        return out

    step_u = b3_step / 255.0
    dipole_u = np.sqrt(np.maximum((b4_lapn / 255.0) * (b5_lapp / 255.0), 0.0))
    onesided_u = (np.abs(b6_down - b7_up) / (b6_down + b7_up + 8.0)) * (np.maximum(b6_down, b7_up) / 255.0)
    cross_u = b8_cross / 255.0
    coh_u = b10_coh / 255.0
    theta_l = np.pi * (b11_strk / 255.0)

    mm[:, :, 1] = _nan_outside_lidar(step_u)
    mm[:, :, 2] = _nan_outside_lidar(dipole_u)
    mm[:, :, 3] = _nan_outside_lidar(onesided_u)
    mm[:, :, 4] = _nan_outside_lidar(cross_u)
    mm[:, :, 5] = _nan_outside_lidar(coh_u)
    mm[:, :, 6] = _nan_outside_lidar(np.cos(2.0 * theta_l))
    mm[:, :, 7] = _nan_outside_lidar(np.sin(2.0 * theta_l))

    raw_scarp = (0.30 * step_u + 0.25 * dipole_u + 0.25 * onesided_u + 0.20 * cross_u) * (0.50 + 0.50 * coh_u)
    scarp_valid = robust_unit(raw_scarp, has_lidar)
    # Seamless fallback where valid == 0 (24.63% of footprint): 100 m DEM ridge + tophat scarp
    dem_ridge = np.asarray(base[:, :, 21], dtype=np.float32)   # ridge_s1
    dem_tophat = np.asarray(base[:, :, 25], dtype=np.float32)  # tophat2
    dem_slope = np.asarray(base[:, :, 18], dtype=np.float32)   # band19 det_elev_slope
    dem_fallback = robust_unit(
        0.55 * robust_unit(dem_ridge, foot) + 0.45 * robust_unit(dem_tophat, foot) * (1.0 - 0.35 * robust_unit(np.abs(dem_slope), foot)),
        foot,
    )
    scarp_seamless = np.where(has_lidar, scarp_valid, dem_fallback).astype(np.float32)
    scarp_seamless[~foot] = 0.0
    mm[:, :, 8] = scarp_seamless
    mm[:, :, 9] = robust_unit(directional_chain_max(scarp_seamless, foot, halflen=2), foot)

    del b3_step, b4_lapn, b5_lapp, b6_down, b7_up, b8_cross, b10_coh, b11_strk, b12_val
    del step_u, dipole_u, onesided_u, cross_u, coh_u, theta_l, raw_scarp, scarp_valid, dem_fallback
    gc.collect()

    # ---- Domain II: True Miller-Singh magnetic tilt & Salem tilt-depth (ch 10..13) ----
    log("[MDRC] Domain II: computing true RTP/TMI Miller-Singh tilt-angle zero-crossings & Salem depth")
    rtp = fill_median(np.asarray(base[:, :, 1], dtype=np.float32), foot, sigma=1.0)
    tmi_hg = fill_median(np.asarray(base[:, :, 2], dtype=np.float32), foot, sigma=0.8)
    tmi_vg = fill_median(np.asarray(base[:, :, 8], dtype=np.float32), foot, sigma=0.8)
    tmi = fill_median(np.asarray(base[:, :, 13], dtype=np.float32), foot, sigma=0.8)
    d_base = fill_median(np.asarray(base[:, :, 14], dtype=np.float32), foot, sigma=1.5)

    gy_r, gx_r = np.gradient(rtp, 100.0, 100.0)
    rtp_hg = np.hypot(gx_r, gy_r).astype(np.float32)
    rtp_vz = fft_first_vertical_derivative(rtp, dx_m=100.0, smooth_sigma=0.8)
    theta_rtp = np.arctan2(rtp_vz, np.maximum(rtp_hg, 1e-6)).astype(np.float32)
    rtp_tilt_zero = np.exp(-((theta_rtp / 0.35) ** 2)).astype(np.float32) * robust_unit(rtp_hg, foot)
    mm[:, :, 10] = robust_unit(rtp_tilt_zero, foot)

    # Note: tmi_hg and tmi_vg may differ in unit scaling, so standardize by median abs before arctan2
    s_vg = float(np.median(np.abs(tmi_vg[foot]))) + 1e-6
    s_hg = float(np.median(np.abs(tmi_hg[foot]))) + 1e-6
    theta_tmi = np.arctan2(tmi_vg / s_vg, np.maximum(np.abs(tmi_hg) / s_hg, 1e-6)).astype(np.float32)
    tmi_tilt_zero = np.exp(-((theta_tmi / 0.35) ** 2)).astype(np.float32) * robust_unit(np.abs(tmi_hg), foot)
    mm[:, :, 11] = robust_unit(tmi_tilt_zero, foot)

    # Salem et al. (2007) tilt-gradient contact sharpness * sediment cover thickness
    gy_th, gx_th = np.gradient(gaussian_filter(theta_rtp, sigma=1.0, mode="nearest"))
    salem_sharp = np.hypot(gx_th, gy_th) * (np.abs(theta_rtp) < (np.pi / 4.0)).astype(np.float32)
    cover_u = robust_unit(d_base, foot)
    mm[:, :, 12] = robust_unit(salem_sharp * (0.30 + 0.70 * cover_u), foot)

    with rasterio.open(ddir / "external" / "geodawn_extensions_u8.tif") as src:
        tmi_up150 = src.read(4).astype(np.float32)
    has_ext = (tmi_up150 > 0) & foot
    res_mag = robust_unit(tmi, has_ext) - robust_unit(tmi_up150, has_ext)
    res_line = hessian_line_both_polarities(fill_median(res_mag, foot, sigma=1.0), sigma=1.5)
    mm[:, :, 13] = robust_unit(res_line, foot)

    # Save RTP Laplacian for Domain IV magnetite destruction before freeing RTP
    rtp_lap = ndimage.gaussian_laplace(rtp, sigma=1.8, mode="nearest").astype(np.float32)
    del rtp, tmi_hg, tmi_vg, tmi, gy_r, gx_r, rtp_hg, rtp_vz, theta_rtp, theta_tmi, salem_sharp, tmi_up150, res_mag, res_line
    gc.collect()

    # ---- Domain III: Gravity VG zero-crossing, basement step & concealment habitat (ch 14..17) ----
    log("[MDRC] Domain III: computing gravity inflection, basement-step alignment & concealment index")
    grav_vg = fill_median(np.asarray(base[:, :, 10], dtype=np.float32), foot, sigma=1.0)
    grav = fill_median(np.asarray(base[:, :, 12], dtype=np.float32), foot, sigma=1.2)
    grav_hg = fill_median(np.asarray(base[:, :, 17], dtype=np.float32), foot, sigma=1.0)
    cond = fill_median(np.asarray(base[:, :, 16], dtype=np.float32), foot, sigma=1.2)
    slope = fill_median(np.asarray(base[:, :, 18], dtype=np.float32), foot, sigma=0.8)

    vg_med = float(np.median(grav_vg[foot]))
    vg_iqr = max(float(np.percentile(grav_vg[foot], 75) - np.percentile(grav_vg[foot], 25)) / 1.349, 1e-6)
    vg_z = (grav_vg - vg_med) / vg_iqr
    grav_inflect = np.exp(-((vg_z / 0.65) ** 2)).astype(np.float32) * robust_unit(np.abs(grav_hg), foot)
    mm[:, :, 14] = robust_unit(grav_inflect, foot)

    gy_g, gx_g = np.gradient(grav)
    gy_b, gx_b = np.gradient(d_base)
    align_gb = np.abs(gx_g * gx_b + gy_g * gy_b)
    mm[:, :, 15] = robust_unit(align_gb, foot)

    gy_c, gx_c = np.gradient(cond)
    align_cb = np.abs(gx_c * gx_b + gy_c * gy_b)
    cond_line = hessian_line_both_polarities(cond, sigma=2.0)
    mm[:, :, 16] = robust_unit(0.60 * robust_unit(align_cb, foot) + 0.40 * robust_unit(cond_line, foot), foot)

    slope_u = robust_unit(np.abs(slope), foot)
    mm[:, :, 17] = np.where(foot, cover_u * (1.0 - 0.80 * slope_u), 0.0).astype(np.float32)

    del grav_vg, grav, grav_hg, slope, gy_g, gx_g, gy_b, gx_b, gy_c, gx_c, align_gb, align_cb, cond_line, d_base
    gc.collect()

    # ---- Domain IV: GeoDAWN K/Th + magnetite destruction + GDR-1391 conduits (ch 18..21) ----
    log("[MDRC] Domain IV: computing K/Th alteration, magnetite destruction & label-free GDR-1391 halos")
    with rasterio.open(ddir / "external" / "geodawn_rad_u8.tif") as src:
        rad_k = src.read(1).astype(np.float32)
        rad_th = src.read(2).astype(np.float32)
    with rasterio.open(ddir / "external" / "geodawn_extensions_u8.tif") as src:
        ext_thk = src.read(1).astype(np.float32)
        ext_uk = src.read(2).astype(np.float32)
        ext_uth = src.read(3).astype(np.float32)

    has_rad = (rad_k > 0) & (rad_th > 0) & foot
    k_over_th = fill_median(np.where(has_rad, rad_k / (rad_th + 8.0), np.nan), foot, sigma=1.2)
    kth_grad = np.hypot(*np.gradient(k_over_th))
    kth_line = hessian_line_both_polarities(k_over_th, sigma=1.8)
    thk_grad = np.hypot(*np.gradient(fill_median(np.where(ext_thk > 0, ext_thk, np.nan), foot, sigma=1.2)))
    mm[:, :, 18] = robust_unit(
        0.45 * robust_unit(kth_grad, foot) + 0.35 * robust_unit(kth_line, foot) + 0.20 * robust_unit(thk_grad, foot),
        foot,
    )

    tc_band6 = fill_median(np.asarray(base[:, :, 5], dtype=np.float32), foot, sigma=1.0)
    uth_f = fill_median(np.where(ext_uth > 0, ext_uth, np.nan), foot, sigma=1.2)
    uk_f = fill_median(np.where(ext_uk > 0, ext_uk, np.nan), foot, sigma=1.2)
    redox_grad = 0.45 * robust_unit(np.hypot(*np.gradient(uth_f)), foot) + 0.35 * robust_unit(
        np.hypot(*np.gradient(uk_f)), foot
    ) + 0.20 * robust_unit(np.hypot(*np.gradient(tc_band6)), foot)
    mm[:, :, 19] = robust_unit(redox_grad, foot)

    # Magnetite destruction corresponds to local RTP trough (+Laplacian > 0) inside conductive clay cap
    demag = robust_unit(np.maximum(rtp_lap, 0.0), foot)
    cond_u = robust_unit(cond, foot)
    mm[:, :, 20] = robust_unit(demag * (0.35 + 0.65 * cond_u), foot)

    # Label-free GDR-1391 spring/well geothermometry + volcanic vents + Kostrov transtensional strain
    ws_df = pd.read_csv(ddir / "external" / "gdr_wellspring_in_footprint.csv", low_memory=False)
    if "dist_known_fault_px" in ws_df.columns:
        ws_df = ws_df.drop(columns=["dist_known_fault_px"])
    assert "dist_known_fault_px" not in ws_df.columns

    vent_df = pd.read_csv(ddir / "external" / "gdr_volcanic_vents_in_footprint.csv", low_memory=False)
    if "dist_known_fault_px" in vent_df.columns:
        vent_df = vent_df.drop(columns=["dist_known_fault_px"])
    assert "dist_known_fault_px" not in vent_df.columns

    impulse = np.zeros((h, w), dtype=np.float32)
    rows = pd.to_numeric(ws_df["row"], errors="coerce").to_numpy()
    cols = pd.to_numeric(ws_df["col"], errors="coerce").to_numpy()
    t_meas = np.nan_to_num(pd.to_numeric(ws_df["temp_c"], errors="coerce").to_numpy(), nan=0.0)
    t_qtz = np.nan_to_num(pd.to_numeric(ws_df["geothermquartz_c"], errors="coerce").to_numpy(), nan=0.0)
    t_cha = np.nan_to_num(pd.to_numeric(ws_df["geothermchalc_c"], errors="coerce").to_numpy(), nan=0.0)
    t_cat = np.nan_to_num(pd.to_numeric(ws_df["geothermcat_c"], errors="coerce").to_numpy(), nan=0.0)
    t_geo = np.maximum(np.maximum(t_qtz, t_cha), t_cat)
    w_therm = np.clip((t_meas - 25.0) / 60.0, 0.0, 2.0) + 0.6 * np.clip((t_geo - 90.0) / 100.0, 0.0, 2.0)

    ok = np.isfinite(rows) & np.isfinite(cols) & (w_therm > 0.0)
    rr = np.clip(np.round(rows[ok]).astype(int), 0, h - 1)
    cc = np.clip(np.round(cols[ok]).astype(int), 0, w - 1)
    np.add.at(impulse, (rr, cc), w_therm[ok].astype(np.float32))

    v_r = pd.to_numeric(vent_df["row"], errors="coerce").dropna().to_numpy().astype(int)
    v_c = pd.to_numeric(vent_df["col"], errors="coerce").dropna().to_numpy().astype(int)
    np.add.at(impulse, (np.clip(v_r, 0, h - 1), np.clip(v_c, 0, w - 1)), 1.5)

    halo = 0.65 * gaussian_filter(impulse, sigma=6.0, mode="constant") + 0.35 * gaussian_filter(
        impulse, sigma=18.0, mode="constant"
    )
    shear = fill_median(np.asarray(base[:, :, 6], dtype=np.float32), foot, sigma=1.0)
    dilat = fill_median(np.asarray(base[:, :, 7], dtype=np.float32), foot, sigma=1.0)
    transt = robust_unit(np.maximum(dilat, 0.0) * np.abs(shear), foot)
    mm[:, :, 21] = robust_unit(0.65 * robust_unit(halo, foot) + 0.35 * transt, foot)

    mm.flush()
    del rad_k, rad_th, ext_thk, ext_uk, ext_uth, rtp_lap, cond, impulse, halo, shear, dilat
    gc.collect()

    return {
        "extra_channels": MDRC_EXTRA_CHANNELS,
        "n_extra_channels": len(MDRC_EXTRA_CHANNELS),
        "shape": [h, w, len(MDRC_EXTRA_CHANNELS)],
        "lidar_valid_fraction_in_footprint": float(has_lidar.sum() / max(int(foot.sum()), 1)),
        "path": str(out_path),
    }


def unsupervised_domain_surfaces(extra_mm: np.ndarray, foot: np.ndarray) -> dict[str, np.ndarray]:
    """Compute the 4 standalone physical domain surfaces + label-free 4-domain concordance surface."""
    d1 = robust_unit(
        0.55 * np.asarray(extra_mm[:, :, 8], dtype=np.float32)
        + 0.45 * np.asarray(extra_mm[:, :, 9], dtype=np.float32),
        foot,
    )
    d2 = robust_unit(
        0.40 * np.asarray(extra_mm[:, :, 10], dtype=np.float32)
        + 0.25 * np.asarray(extra_mm[:, :, 11], dtype=np.float32)
        + 0.20 * np.asarray(extra_mm[:, :, 12], dtype=np.float32)
        + 0.15 * np.asarray(extra_mm[:, :, 13], dtype=np.float32),
        foot,
    )
    d3 = robust_unit(
        0.40 * np.asarray(extra_mm[:, :, 14], dtype=np.float32)
        + 0.35 * np.asarray(extra_mm[:, :, 15], dtype=np.float32)
        + 0.25 * np.asarray(extra_mm[:, :, 16], dtype=np.float32),
        foot,
    )
    d4 = robust_unit(
        0.35 * np.asarray(extra_mm[:, :, 18], dtype=np.float32)
        + 0.20 * np.asarray(extra_mm[:, :, 19], dtype=np.float32)
        + 0.20 * np.asarray(extra_mm[:, :, 20], dtype=np.float32)
        + 0.25 * np.asarray(extra_mm[:, :, 21], dtype=np.float32),
        foot,
    )
    gate = multi_domain_corroboration_gate(d1, d2, d3, d4, foot)
    unsup_4dom = robust_unit((0.42 * d1 + 0.22 * d2 + 0.20 * d3 + 0.16 * d4) * gate, foot)
    return {
        "D1_LiDAR_Dipole": d1,
        "D2_True_Mag_Tilt": d2,
        "D3_Grav_MT_Step": d3,
        "D4_Hydrothermal_Alt": d4,
        "MDRC_Unsup_4Domain": unsup_4dom,
        "_gate": gate,
    }


def sample_dual_rows(
    base_mm: np.ndarray,
    extra_mm: np.ndarray,
    pos_mask: np.ndarray,
    train_mask: np.ndarray,
    rng: np.random.Generator,
    sample_pos: int = 50_000,
    sample_neg: int = 200_000,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Memory-light sampler reading from both memmaps and returning (X, y, piedmont_weights)."""
    h, w, fb = base_mm.shape
    fe = extra_mm.shape[2]
    flat_pos = pos_mask.reshape(-1)
    flat_tr = train_mask.reshape(-1)

    pos_idx = np.flatnonzero(pos_mask & train_mask)
    if pos_idx.size > sample_pos:
        pos_idx = rng.choice(pos_idx, size=sample_pos, replace=False)

    neg_parts, got = [], 0
    while got < sample_neg:
        need = int((sample_neg - got) * 1.35) + 4096
        cand = rng.integers(0, h * w, size=need, dtype=np.int64)
        cand = cand[flat_tr[cand] & ~flat_pos[cand]]
        if cand.size:
            neg_parts.append(cand)
            got += cand.size
    neg_idx = np.concatenate(neg_parts)[:sample_neg]

    raw_idx = np.concatenate([pos_idx, neg_idx])
    raw_y = np.concatenate([np.ones(pos_idx.size, dtype=np.int8), np.zeros(neg_idx.size, dtype=np.int8)])
    order = np.argsort(raw_idx)
    idx = raw_idx[order]
    y = raw_y[order]

    Xb = np.asarray(base_mm.reshape(-1, fb)[idx], dtype=np.float32)
    Xe = np.asarray(extra_mm.reshape(-1, fe)[idx], dtype=np.float32)
    X = np.concatenate([Xb, Xe], axis=1)

    # Concealment propensity weight from ch 17 of extra_mm (`piedmont_concealment_index` in [0, 1])
    conc = np.nan_to_num(Xe[:, 17], nan=0.0)
    piedmont_w = (1.0 + 2.2 * conc).astype(np.float32)
    return X, y, piedmont_w


def fit_dual_mdrc_models(X: np.ndarray, y: np.ndarray, piedmont_w: np.ndarray, seed: int):
    """Fit general neotectonic HGB + piedmont/cover-conditioned HGB (preserving NaN routing!)."""
    from sklearn.ensemble import HistGradientBoostingClassifier

    m_gen = HistGradientBoostingClassifier(
        max_iter=120,
        learning_rate=0.08,
        max_leaf_nodes=31,
        min_samples_leaf=50,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=seed,
    )
    m_gen.fit(X, y)

    m_pied = HistGradientBoostingClassifier(
        max_iter=120,
        learning_rate=0.08,
        max_leaf_nodes=31,
        min_samples_leaf=50,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=seed + 100,
    )
    m_pied.fit(X, y, sample_weight=piedmont_w)
    return m_gen, m_pied


def predict_dual_mdrc_field(
    m_gen,
    m_pied,
    base_mm: np.ndarray,
    extra_mm: np.ndarray,
    row_start: int,
    row_end: int,
    block_rows: int = 250,
) -> np.ndarray:
    """Predict blended general + cover-adaptive probability surface for rows [row_start, row_end)."""
    h_tot, w, fb = base_mm.shape
    fe = extra_mm.shape[2]
    out = np.zeros((row_end - row_start, w), dtype=np.float32)
    for y0 in range(row_start, row_end, block_rows):
        y1 = min(y0 + block_rows, row_end)
        bh = y1 - y0
        Xb = np.asarray(base_mm[y0:y1], dtype=np.float32).reshape(-1, fb)
        Xe = np.asarray(extra_mm[y0:y1], dtype=np.float32).reshape(-1, fe)
        X = np.concatenate([Xb, Xe], axis=1)
        pg = m_gen.predict_proba(X)[:, 1].astype(np.float32)
        pp = m_pied.predict_proba(X)[:, 1].astype(np.float32)
        # Spatially adaptive weight: 35% piedmont head on range-fronts, up to 70% in deep flat basins
        conc = np.clip(np.nan_to_num(Xe[:, 17], nan=0.0), 0.0, 1.0)
        w_p = 0.35 + 0.35 * conc
        p_blend = (1.0 - w_p) * pg + w_p * pp
        out[y0 - row_start : y1 - row_start] = p_blend.reshape(bh, w)
    return out
