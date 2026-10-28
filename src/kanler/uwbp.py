"""Lane H-K1-B (UWBP-DRCS): Upward-Continued Worm Back-Projection & Deconfounded Dual-Regime Crustal-Hydrothermal Synthesis.

Pre-registered in `docs/research/hypotheses-20261028.md` prior to any holdout experiment.
Implements:
1. Exact 2D DCT-II (Neumann/mirror-boundary, zero wrap-around) Poisson upward continuation
   `U(k; h) = U(k; 0) * exp(-h * |k|)` across altitudes `h in {100, 300, 600, 1200} m` for
   isostatic gravity (`Band 13`) and Reduced-to-Pole magnetics (`Band 2`), tracking multi-scale
   Blakely horizontal-gradient "worms", down-dip worm crest migration, and Andersonian 55-deg
   up-dip surface back-projection (`Z_b * cot(55 deg)` along `+grad(g_iso)`).
2. Elevation-deconfounded tectonic geomorphology: longitudinal thalweg knickzone convexity inside
   convergent valleys (`-z_ss > 0` & `z_tt > 0`), along-strike multi-drainage knickpoint chains,
   hyperbolic spur-saddle notch chains (`K_gauss < 0`), planar triangular facet breaks, and
   800 m contour cross-cutting guard against Lake Lahontan/Bonneville paleoshorelines.
3. Strike-steered hydrothermal fracture-permeability conduit bridges: linear magnetite-bleaching +
   GeoDAWN potassic `K/Th` crests, Curewitz-Karson lateral smectite-clay-cap boundaries (using
   `Band 17 cond_surf` directly in decade `log10(rho)` units), anisotropic strike-steered thermal
   bridges (GDR #1391 thermal springs/quartz geothermometry + INGENIOUS 2m `F2mDAB` probes +
   paleo-sinter vents, strictly excluding `dist_known_fault_px`), and 4-physics strike consensus.
4. Cost-sensitive Dinkelbach marginal-DTI lazy-greedy (CELF) submodular packer (`pack_dinkelbach_dti_300m`).

100% Zero-SGMC in feature construction, training, negative guarding, and inference.
"""
from __future__ import annotations

import csv
import gc
import heapq
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from numpy.lib.format import open_memmap
from rasterio.transform import rowcol as rio_rowcol
from rasterio.warp import transform as rio_transform
from scipy import fft as sp_fft
from scipy import ndimage as ndi

from gems32 import features as shared_features
from gems32 import metric as M
from kanler import ocda

UWBP_SCHEMA_VERSION = "kanler1-uwbp-drcs-v1"
COT_55_DEG = np.float32(1.0 / np.tan(np.deg2rad(55.0)))  # 0.7002075

UWBP_FREE_NAMES: tuple[str, ...] = (
    # Group A: 2D DCT-II Poisson Upward-Continued Worms & 55-deg Up-Dip Back-Projection (6)
    "uwbp_grav_worm_persistence_100_1200m",
    "uwbp_grav_worm_downdip_migration",
    "uwbp_grav_updip55_backproj_crest",
    "uwbp_rtp_worm_persistence_100_1200m",
    "uwbp_rtp_updip55_backproj_crest",
    "uwbp_mt_updip55_boundary_crest",
    # Group B: Elevation-Deconfounded Canyon Knickzones, Spur Saddles & Facet Breaks (6)
    "uwbp_thalweg_knickzone_convexity",
    "uwbp_along_strike_knick_chain",
    "uwbp_spur_saddle_notch_chain",
    "uwbp_triangular_facet_planar_break",
    "uwbp_contour_cross_cut_index",
    "uwbp_multiscale_ridge_scarp_skeleton",
    # Group C: Strike-Steered Hydrothermal Conduit Bridges & 4-Physics Consensus (6)
    "uwbp_mag_bleach_potassic_crest",
    "uwbp_smectite_cap_lateral_margin",
    "uwbp_aniso_thermal_conduit_bridge",
    "uwbp_transtensional_dilation_worm_coupling",
    "uwbp_four_physics_axial_consensus",
    "uwbp_blind_basin_structural_prior",
)

# Deconfounded indices into shared_mm (35 ch) and ocda_mm (26 ch):
# Deliberately EXCLUDES raw geographic/elevation coordinate proxy bands (band01..band19 raw scalars
# and ocda[4] local_elev_pct_2p5km) that overfit training quadrants and suppress upland Cenozoic faults!
SHARED_DECONFOUNDED_INDICES: tuple[int, ...] = (
    19,  # curv_s1
    20,  # curv_s2
    21,  # ridge_s1
    22,  # ridge_s2
    23,  # ridge_s3
    24,  # relief5 (local 500 m roughness only)
    25,  # tophat2
    26,  # tmi_edge
    27,  # rtp_edge
    28,  # grav_edge
    29,  # cond_edge
    30,  # depth_grad
    31,  # coherence_s2
    32,  # strike_cos
    33,  # strike_sin
)

OCDA_DECONFOUNDED_INDICES: tuple[int, ...] = (
    0,   # piedmont_slope_dipole_400m
    1,   # piedmont_slope_dipole_800m
    2,   # elev_step_curv_toe
    3,   # axial_ridge_persistence
    5,   # slope_prominence_800m (excludes idx 4 = local_elev_pct_2p5km!)
    6,   # halfgraben_grav_dipole_600m
    7,   # basement_step_dipole_600m
    8,   # copolar_halfgraben_index
    9,   # mt_cond_dipole_500m
    10,  # grav_ew_polarity_grad
    11,  # true_mag_tilt_zero_crest
    12,  # cooper_tdx_mag
    13,  # tmi_up150_persistence
    14,  # true_grav_tilt_zero_crest
    15,  # axial_potfield_persistence
    16,  # lidar_scarp_debiased
    17,  # lidar_face_dipole
    18,  # contour_orthogonality
    19,  # road_confound_guard
    20,  # lidar_valid_flag
    21,  # k_th_alteration_excess
    22,  # probe_2m_f2mdab_halo
    23,  # hydrothermal_vent_sinter_halo
    24,  # strain_dilation_strike_compat
    25,  # multiphysics_strike_concordance
)


def poisson_upward_continue_dct(
    field: np.ndarray,
    foot: np.ndarray,
    heights_m: tuple[float, ...],
    dx_m: float = 100.0,
) -> dict[float, np.ndarray]:
    """Exact 2D DCT-II Neumann-boundary Poisson upward continuation for potential fields.

    Satisfies Laplace's equation `d^2 U / dz^2 = -(U_xx + U_yy)` with zero normal derivative
    on grid edges, eliminating wrap-around periodic boundary cliffs without padding memory.
    """
    H, W = field.shape
    v = foot & np.isfinite(field)
    med = float(np.median(field[v])) if v.any() else 0.0
    centered = (field - np.float32(med)).astype(np.float32, copy=False)
    spec = sp_fft.dctn(centered, type=2, norm="ortho", workers=2)

    ky = (np.pi * np.arange(H, dtype=np.float32)) / np.float32(H * dx_m)
    kx = (np.pi * np.arange(W, dtype=np.float32)) / np.float32(W * dx_m)
    k_rad = np.hypot(ky[:, None], kx[None, :])

    out: dict[float, np.ndarray] = {}
    for h in heights_m:
        atten = np.exp(-np.float32(h) * k_rad).astype(np.float32)
        u_h = sp_fft.idctn(spec * atten, type=2, norm="ortho", workers=2).astype(np.float32)
        out[float(h)] = u_h + np.float32(med)
        del atten
    del spec, k_rad
    return out


def _grad_mag_f32(a: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(a.astype(np.float32, copy=False))
    return np.hypot(gx, gy).astype(np.float32)


def _blakely_crest_prominence(gmag: np.ndarray, sigma: float = 1.1) -> np.ndarray:
    """Normalized Blakely & Simpson (1986) ridge prominence on horizontal-gradient magnitude."""
    sm = ndi.gaussian_filter(gmag, sigma, mode="nearest")
    bg = ndi.gaussian_filter(sm, sigma * 3.0, mode="nearest")
    crest = shared_features._hessian_ridge(sm, sigma)
    return (0.60 * crest + 0.40 * np.maximum(sm - bg, 0.0)).astype(np.float32)


def _transverse_1px_centerline(comp: np.ndarray, foot: np.ndarray) -> np.ndarray:
    """Sharpen a positive multi-physics field onto its 1-px transverse Hessian centerline in `[0, 1]`."""
    sm = ndi.gaussian_filter(comp.astype(np.float32, copy=False), 0.9, mode="nearest")
    axx = ndi.gaussian_filter(sm, 1.2, order=(0, 2), mode="nearest")
    ayy = ndi.gaussian_filter(sm, 1.2, order=(2, 0), mode="nearest")
    axy = ndi.gaussian_filter(sm, 1.2, order=(1, 1), mode="nearest")
    phi = 0.5 * np.arctan2(2.0 * axy, axx - ayy + 1e-12)
    ny = np.sin(phi).astype(np.float32)
    nx = np.cos(phi).astype(np.float32)
    del axx, ayy, axy, phi

    c_p1 = ocda.sample_bilinear_offset(sm, 1.30 * ny, 1.30 * nx)
    c_m1 = ocda.sample_bilinear_offset(sm, -1.30 * ny, -1.30 * nx)
    c_p2 = ocda.sample_bilinear_offset(sm, 2.45 * ny, 2.45 * nx)
    c_m2 = ocda.sample_bilinear_offset(sm, -2.45 * ny, -2.45 * nx)
    del ny, nx

    is_peak = sm >= 0.965 * np.maximum(c_p1, c_m1)
    prom = np.clip((sm - 0.5 * (c_p2 + c_m2)) * 3.5, 0.0, 1.0)
    sharp = sm * np.where(is_peak, 0.78 + 0.22 * prom, 0.22 + 0.18 * prom)
    return ocda._robust_z_pos(sharp.astype(np.float32), foot)


def _build_aniso_thermal_conduit_bridge(
    ddir: Path,
    transform,
    shape: tuple[int, int],
    foot: np.ndarray,
    ty_strike: np.ndarray,
    tx_strike: np.ndarray,
) -> np.ndarray:
    """Build strike-steered anisotropic hydrothermal upflow conduit bridges (100% label-free)."""
    H, W = shape
    seed = np.zeros((H, W), dtype=np.float32)

    # 1. GDR #1391 thermal springs & wells (strictly temperature & quartz geothermometer; NEVER dist_known_fault_px)
    well_csv = ddir / "external" / "gdr_wellspring_in_footprint.csv"
    with well_csv.open(newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                r = int(float(row["row"]))
                c = int(float(row["col"]))
            except (KeyError, TypeError, ValueError):
                continue
            if not (0 <= r < H and 0 <= c < W and foot[r, c]):
                continue
            t_m = float(row["temp_c"]) if row.get("temp_c") not in (None, "") else 0.0
            t_q = float(row["geothermquartz_c"]) if row.get("geothermquartz_c") not in (None, "") else 0.0
            w = 0.0
            if np.isfinite(t_m) and t_m >= 30.0:
                w += min(t_m - 20.0, 150.0) / 38.0
            if np.isfinite(t_q) and t_q >= 85.0:
                w += min(t_q - 75.0, 180.0) / 75.0
            if w > seed[r, c]:
                seed[r, c] = np.float32(w)

    # 2. Paleo-geothermal sinter / silicified fault breccia deposits
    paleo_zip = ddir / "external" / "paleo_geothermal_regional.zip"
    with zipfile.ZipFile(paleo_zip) as zf:
        raw = zf.read("Paleo_geothermal_final.csv").decode("utf-8", "replace")
    lons, lats, pweights = [], [], []
    for rec in csv.DictReader(io.StringIO(raw)):
        try:
            lon = float(rec["Long_deg_NAD83"])
            lat = float(rec["Lat_deg_NAD83"])
        except (KeyError, TypeError, ValueError):
            continue
        dtype_txt = " ".join(str(v).lower() for k, v in rec.items() if "type" in k.lower() or "desc" in k.lower())
        pw = 2.8 if ("sinter" in dtype_txt or "silic" in dtype_txt) else (0.6 if "tufa" in dtype_txt else 1.5)
        if np.isfinite(lon) and np.isfinite(lat):
            lons.append(lon)
            lats.append(lat)
            pweights.append(pw)
    if lons:
        east, north = rio_transform("EPSG:4269", "EPSG:32611", lons, lats)
        rows_i, cols_i = rio_rowcol(transform, east, north)
        for ri, ci, pw in zip(rows_i, cols_i, pweights):
            ri, ci = int(ri), int(ci)
            if 0 <= ri < H and 0 <= ci < W and foot[ri, ci] and pw > seed[ri, ci]:
                seed[ri, ci] = np.float32(pw)

    # Narrow cross-strike kernel (sigma=2.2 px = 220 m), then steer anisotropically along local strike!
    narrow = ndi.gaussian_filter(seed, sigma=2.2, mode="nearest")
    del seed
    # Add narrow 2m temperature probe excess
    probe_halo = ocda._parse_2m_probes_halo(
        ddir / "external" / "2m_temperature_probe_INGENIOUS_regional_data.zip",
        transform,
        (H, W),
        foot,
    )
    base_th = (0.65 * ocda._robust_z_pos(narrow, foot) + 0.35 * probe_halo).astype(np.float32)
    del narrow, probe_halo

    acc = base_th.copy()
    w_tot = np.float32(1.0)
    for step_px, wt in ((4.0, 0.80), (8.0, 0.58), (12.0, 0.36)):
        p_pos = ocda.sample_bilinear_offset(base_th, step_px * ty_strike, step_px * tx_strike)
        p_neg = ocda.sample_bilinear_offset(base_th, -step_px * ty_strike, -step_px * tx_strike)
        # Bridge bonus when hydrothermal anomalies lie on BOTH sides or extend along strike
        bridge = 0.55 * (p_pos + p_neg) + 0.45 * np.sqrt(np.maximum(p_pos * p_neg, 0.0))
        acc += np.float32(wt) * bridge.astype(np.float32)
        w_tot += np.float32(wt)
        del p_pos, p_neg, bridge
    del base_th
    return ocda._robust_z_pos((acc / w_tot).astype(np.float32), foot)


def build_or_load_uwbp_free_stack(ddir: Path, wdir: Path, log=print) -> np.ndarray:
    """Build (or load schema-verified) 18-channel label-free UWBP-DRCS stack `(18, H, W)` float32."""
    out_path = wdir / "uwbp_free_v1.npy"
    meta_path = wdir / "uwbp_free_v1.npy.json"
    bands_dir = wdir / "bands"
    foot = np.load(bands_dir / "_footprint.npy")
    H, W = foot.shape

    with rasterio.open(ddir / "sample_submission.tif") as ds:
        transform = ds.transform

    if out_path.is_file() and meta_path.is_file():
        meta = json.loads(meta_path.read_text())
        if meta.get("schema") == UWBP_SCHEMA_VERSION and meta.get("names") == list(UWBP_FREE_NAMES):
            mm = np.load(out_path, mmap_mode="r")
            if mm.shape == (len(UWBP_FREE_NAMES), H, W) and mm.dtype == np.float32:
                log(f"[UWBP] Loaded verified 18-channel cache {out_path.name} {mm.shape}")
                return mm

    log("[UWBP] Building 18-channel label-free UWBP-DRCS geophysical worm & tectonic geomorphology stack...")
    meta_path.unlink(missing_ok=True)
    mm = open_memmap(out_path, mode="w+", dtype=np.float32, shape=(len(UWBP_FREE_NAMES), H, W))

    # =========================================================================
    # Group A: 2D DCT-II Poisson Upward-Continued Worms & 55-deg Back-Projection
    # =========================================================================
    grav = ocda._read_prepared_band(bands_dir, 13, "iso_grav_anom", foot)
    zbase = np.maximum(ocda._read_prepared_band(bands_dir, 15, "depth_to_base_surf", foot), 0.0)
    # Up-dip horizontal offset in pixels (100 m/px) for an Andersonian 55-deg normal fault
    dl_px = np.clip((zbase * COT_55_DEG) / np.float32(100.0), np.float32(1.5), np.float32(11.0)).astype(np.float32)
    zb_grad = ocda._robust_z_pos(_grad_mag_f32(ndi.gaussian_filter(zbase, 1.5, mode="nearest")), foot)
    del zbase

    grav_up = poisson_upward_continue_dct(grav, foot, (100.0, 300.0, 600.0, 1200.0))
    del grav

    # Basin-pointing unit normal from h=300 m gravity (-grad g_iso points from dense horst into basin)
    gy_g3, gx_g3 = np.gradient(grav_up[300.0])
    gm_g3 = np.hypot(gx_g3, gy_g3) + np.float32(1e-6)
    ny_basin = (-gy_g3 / gm_g3).astype(np.float32)
    nx_basin = (-gx_g3 / gm_g3).astype(np.float32)
    _, theta_grav_w, _ = shared_features._structure_tensor(grav_up[300.0], 2.2)
    del gy_g3, gx_g3, gm_g3

    wg_100 = ocda._robust_z_pos(_blakely_crest_prominence(_grad_mag_f32(grav_up[100.0]), 1.0), foot)
    wg_300 = ocda._robust_z_pos(_blakely_crest_prominence(_grad_mag_f32(grav_up[300.0]), 1.2), foot)
    wg_600 = ocda._robust_z_pos(_blakely_crest_prominence(_grad_mag_f32(grav_up[600.0]), 1.5), foot)
    wg_1200 = ocda._robust_z_pos(_blakely_crest_prominence(_grad_mag_f32(grav_up[1200.0]), 2.0), foot)
    del grav_up

    # Ch 0: Multi-scale gravity worm persistence (100 m -> 1200 m)
    g_worm_pers = np.power(
        np.maximum(wg_100, 1e-4) * np.maximum(wg_300, 1e-4) * np.maximum(wg_600, 1e-4) * np.maximum(wg_1200, 1e-4),
        0.25,
    ).astype(np.float32)
    mm[0] = np.where(foot, g_worm_pers, 0.0)

    # Ch 1: Signed down-dip worm migration (positive when h=1200 m crest shifts basinward vs footwall)
    w12_hw = ocda.sample_bilinear_offset(wg_1200, 5.5 * ny_basin, 5.5 * nx_basin)
    w12_fw = ocda.sample_bilinear_offset(wg_1200, -5.5 * ny_basin, -5.5 * nx_basin)
    mig_g = (w12_hw - w12_fw) * (0.35 + 0.65 * wg_100)
    mm[1] = ocda._robust_z_signed(mig_g.astype(np.float32), foot)
    del wg_100, wg_600, wg_1200, w12_hw, w12_fw, mig_g

    # Ch 2: 55-deg up-dip surface back-projection of subsurface gravity + basement-depth fault step
    sub_grav_zb = (0.60 * wg_300 + 0.40 * zb_grad).astype(np.float32)
    g_back = ocda.sample_bilinear_offset(sub_grav_zb, dl_px * ny_basin, dl_px * nx_basin)
    mm[2] = ocda._robust_z_pos((0.70 * g_back + 0.30 * sub_grav_zb).astype(np.float32), foot)
    del wg_300, zb_grad, sub_grav_zb, g_back
    gc.collect()

    # RTP magnetic worms & 55-deg up-dip back-projection
    rtp = ocda._read_prepared_band(bands_dir, 2, "rtp", foot)
    coh_rtp, theta_mag_w, _ = shared_features._structure_tensor(rtp, 2.2)
    rtp_up = poisson_upward_continue_dct(rtp, foot, (100.0, 300.0, 600.0, 1200.0))

    wm_100 = ocda._robust_z_pos(_blakely_crest_prominence(_grad_mag_f32(rtp_up[100.0]), 1.0), foot)
    wm_300 = ocda._robust_z_pos(_blakely_crest_prominence(_grad_mag_f32(rtp_up[300.0]), 1.2), foot)
    wm_600 = ocda._robust_z_pos(_blakely_crest_prominence(_grad_mag_f32(rtp_up[600.0]), 1.5), foot)
    wm_1200 = ocda._robust_z_pos(_blakely_crest_prominence(_grad_mag_f32(rtp_up[1200.0]), 2.0), foot)
    del rtp_up

    # Ch 3: Multi-scale RTP magnetic worm persistence
    m_worm_pers = np.power(
        np.maximum(wm_100, 1e-4) * np.maximum(wm_300, 1e-4) * np.maximum(wm_600, 1e-4) * np.maximum(wm_1200, 1e-4),
        0.25,
    ).astype(np.float32)
    mm[3] = np.where(foot, m_worm_pers, 0.0)

    # Ch 4: 55-deg up-dip surface back-projection of deep RTP magnetic contact
    m_back = ocda.sample_bilinear_offset(wm_300, dl_px * ny_basin, dl_px * nx_basin)
    mm[4] = ocda._robust_z_pos((0.70 * m_back + 0.30 * wm_100).astype(np.float32), foot)
    del wm_100, wm_300, wm_600, wm_1200, m_back

    # Ch 5: MT `cond_surf` (already in decade log10 units [0.19, 4.97]!) lateral crest + up-dip projection
    cond = ocda._read_prepared_band(bands_dir, 17, "cond_surf", foot)
    _, theta_mt_w, _ = shared_features._structure_tensor(cond, 2.2)
    cond_crest = ocda._robust_z_pos(_blakely_crest_prominence(_grad_mag_f32(ndi.gaussian_filter(cond, 1.3, mode="nearest")), 1.2), foot)
    cond_back = ocda.sample_bilinear_offset(cond_crest, np.float32(0.65) * dl_px * ny_basin, np.float32(0.65) * dl_px * nx_basin)
    mm[5] = ocda._robust_z_pos((0.60 * cond_back + 0.40 * cond_crest).astype(np.float32), foot)
    del cond_crest, cond_back, dl_px
    gc.collect()
    log("  [UWBP] Group A (2D DCT-II Poisson worms & 55-deg up-dip back-projection) done")

    # =========================================================================
    # Group B: Elevation-Deconfounded Canyon Knickzones, Spur Saddles & Facets
    # =========================================================================
    dem = ocda._read_prepared_band(bands_dir, 12, "det_elev", foot)
    slope = np.maximum(ocda._read_prepared_band(bands_dir, 19, "det_elev_slope", foot), 0.0)

    dem_s = ndi.gaussian_filter(dem, 1.5, mode="nearest")
    gy_z, gx_z = np.gradient(dem_s)
    gm_z = np.hypot(gx_z, gy_z) + np.float32(1e-5)
    # Unit downhill flow vector u = (uy, ux) and contour tangent t = (ty, tx)
    uy = (-gy_z / gm_z).astype(np.float32)
    ux = (-gx_z / gm_z).astype(np.float32)
    ty = (-ux).astype(np.float32)
    tx = uy.astype(np.float32)
    del gy_z, gx_z, gm_z

    z_yy = ndi.gaussian_filter(dem, 1.6, order=(2, 0), mode="nearest")
    z_xx = ndi.gaussian_filter(dem, 1.6, order=(0, 2), mode="nearest")
    z_yx = ndi.gaussian_filter(dem, 1.6, order=(1, 1), mode="nearest")

    # Longitudinal curvature along downhill flow (z_ss < 0 => convex-up knickpoint step!)
    z_ss = ux * ux * z_xx + np.float32(2.0) * ux * uy * z_yx + uy * uy * z_yy
    # Transverse valley curvature across flow (z_tt > 0 => convergent canyon/thalweg!)
    z_tt = tx * tx * z_xx + np.float32(2.0) * tx * ty * z_yx + ty * ty * z_yy
    knick_raw = np.sqrt(np.maximum(-z_ss, 0.0) * np.maximum(z_tt, 0.0)).astype(np.float32)
    knick = ocda._robust_z_pos(knick_raw, foot)
    mm[6] = knick
    del z_ss, z_tt, knick_raw

    # Ch 7: Along-strike (+/-300m, +/-600m) multi-drainage knickpoint chain minus cross-strike flank
    k_t3p = ocda.sample_bilinear_offset(knick, 3.0 * ty, 3.0 * tx)
    k_t3m = ocda.sample_bilinear_offset(knick, -3.0 * ty, -3.0 * tx)
    k_t6p = ocda.sample_bilinear_offset(knick, 6.0 * ty, 6.0 * tx)
    k_t6m = ocda.sample_bilinear_offset(knick, -6.0 * ty, -6.0 * tx)
    k_n4p = ocda.sample_bilinear_offset(knick, 4.0 * uy, 4.0 * ux)
    k_n4m = ocda.sample_bilinear_offset(knick, -4.0 * uy, -4.0 * ux)
    knick_chain = 0.36 * knick + 0.22 * (k_t3p + k_t3m) + 0.10 * (k_t6p + k_t6m) - 0.25 * (k_n4p + k_n4m)
    mm[7] = ocda._robust_z_pos(knick_chain.astype(np.float32), foot)
    del knick, k_t3p, k_t3m, k_t6p, k_t6m, k_n4p, k_n4m, knick_chain

    # Ch 8: Hyperbolic spur-saddle notch chain (`K_gauss = z_xx * z_yy - z_yx^2 < 0` on fault-notched cols)
    k_gauss = z_xx * z_yy - z_yx * z_yx
    del z_xx, z_yy, z_yx
    saddle = ocda._robust_z_pos(np.sqrt(np.maximum(-k_gauss, 0.0)).astype(np.float32), foot)
    del k_gauss
    s_t4p = ocda.sample_bilinear_offset(saddle, 4.0 * ty, 4.0 * tx)
    s_t4m = ocda.sample_bilinear_offset(saddle, -4.0 * ty, -4.0 * tx)
    mm[8] = ocda._robust_z_pos((0.40 * saddle + 0.30 * (s_t4p + s_t4m)).astype(np.float32), foot)
    del saddle, s_t4p, s_t4m

    # Ch 9: Planar triangular range-front facet break (invariant to raw elevation!)
    sl_mean = ndi.gaussian_filter(slope, 2.0, mode="nearest")
    sl_var = np.maximum(ndi.gaussian_filter(slope * slope, 2.0, mode="nearest") - sl_mean * sl_mean, 0.0)
    planar_steep = sl_mean / (np.sqrt(sl_var) + np.float32(2.5))
    ps_up = ocda.sample_bilinear_offset(planar_steep, -4.0 * uy, -4.0 * ux)
    sl_dn = ocda.sample_bilinear_offset(sl_mean, 4.0 * uy, 4.0 * ux)
    facet_break = ps_up * np.clip((sl_mean - sl_dn) / (sl_mean + sl_dn + np.float32(2.0)), 0.0, 1.0)
    mm[9] = ocda._robust_z_pos(facet_break.astype(np.float32), foot)
    del slope, sl_mean, sl_var, planar_steep, ps_up, sl_dn, facet_break, uy, ux, ty, tx, dem_s

    # Ch 10: 800 m contour cross-cutting index (suppresses contour-parallel Lake Lahontan/Bonneville benches & caprock)
    dem_broad = ndi.gaussian_filter(dem, 8.0, mode="nearest")
    gy_b, gx_b = np.gradient(dem_broad)
    theta_contour = np.arctan2(-gx_b, gy_b).astype(np.float32)
    del dem_broad, gy_b, gx_b

    dem_curv_line = np.maximum(
        shared_features._hessian_both_polarities(dem, 1.4),
        shared_features._hessian_both_polarities(dem, 2.8),
    )
    _, theta_topo_line, _ = shared_features._structure_tensor(dem_curv_line, 2.0)
    del dem
    cross_cut = np.abs(np.sin(theta_topo_line - theta_contour)).astype(np.float32)
    mm[10] = np.where(foot, cross_cut, 0.0)
    del theta_contour

    # Ch 11: Elevation-invariant multiscale geomorphic ridge-scarp-knick-saddle 1-px skeleton
    with rasterio.open(ddir / "external" / "lidar_scarp_features_u8.tif") as ds:
        l_ex = ds.read(1).astype(np.float32)
        l_step = ds.read(3).astype(np.float32)
        l_coh = ds.read(10).astype(np.float32) / np.float32(255.0)
        l_valid = (ds.read(12) > 0) & foot
    l_comp = (0.5 * l_ex + 0.5 * l_step) * (0.3 + 0.7 * l_coh)
    l_med = float(np.median(l_comp[l_valid])) if l_valid.any() else 0.0
    l_iqr = max(float(np.subtract(*np.percentile(l_comp[l_valid], [75, 25]))) / 1.349, 1e-4) if l_valid.any() else 1.0
    lidar_pos = np.where(l_valid, np.clip((l_comp - l_med) / (3.8 * l_iqr), 0.0, 1.0), 0.0).astype(np.float32)
    del l_ex, l_step, l_coh, l_comp

    with rasterio.open(ddir / "external" / "tiger_road_distance_m.tif") as ds:
        d_road = ds.read(1).astype(np.float32)
    d_road = np.where(np.isfinite(d_road) & (d_road >= 0), d_road, 5000.0)
    road_damp = (1.0 - 0.55 * np.exp(-d_road / 110.0)).astype(np.float32)
    del d_road

    dem_line_z = ocda._robust_z_pos(dem_curv_line, foot)
    del dem_curv_line
    shoreline_guard = (0.55 + 0.45 * cross_cut).astype(np.float32)
    geom_raw = (
        0.34 * dem_line_z
        + 0.24 * np.where(l_valid, lidar_pos, dem_line_z * 0.85)
        + 0.22 * mm[7]
        + 0.12 * mm[8]
        + 0.08 * mm[9]
    ) * road_damp * shoreline_guard
    mm[11] = _transverse_1px_centerline(geom_raw, foot)
    del lidar_pos, l_valid, dem_line_z, shoreline_guard, geom_raw
    gc.collect()
    log("  [UWBP] Group B (Elevation-deconfounded canyon knickzones, spur saddles & facets) done")

    # =========================================================================
    # Group C: Strike-Steered Hydrothermal Conduit Bridges & 4-Physics Consensus
    # =========================================================================
    # Ch 12: Linear RTP magnetite-bleaching trough x GeoDAWN K/Th potassic excess x RTP linear coherence
    with rasterio.open(ddir / "external" / "geodawn_rad_u8.tif") as ds:
        rad_k = ds.read(1).astype(np.float32)
        rad_th = ds.read(2).astype(np.float32)
        rad_ok = (rad_k > 0) & (rad_th > 0) & foot
    if rad_ok.any():
        kv, thv = rad_k[rad_ok], rad_th[rad_ok]
        slope_kt = float(np.cov(kv, thv)[0, 1] / (np.var(thv) + 1e-6))
        inter_kt = float(np.mean(kv) - slope_kt * np.mean(thv))
        k_ex = ocda._robust_z_pos(np.where(rad_ok, rad_k - (inter_kt + slope_kt * rad_th), 0.0).astype(np.float32), foot)
    else:
        k_ex = np.zeros((H, W), dtype=np.float32)
    del rad_k, rad_th, rad_ok

    rtp_bleach = ocda._robust_z_pos((ndi.grey_closing(rtp, size=(9, 9)) - rtp).astype(np.float32), foot)
    del rtp
    bleach_k_lin = np.sqrt(np.maximum(rtp_bleach * (0.30 + 0.70 * k_ex), 0.0)) * (0.25 + 0.75 * coh_rtp)
    mm[12] = ocda._robust_z_pos(bleach_k_lin.astype(np.float32), foot)
    del rtp_bleach, k_ex, coh_rtp, bleach_k_lin

    # Ch 13: Curewitz-Karson lateral smectite-clay-cap margin on `cond_surf` (decade log10 resistivity)
    c_hw = ocda.sample_bilinear_offset(cond, 4.0 * ny_basin, 4.0 * nx_basin)
    c_fw = ocda.sample_bilinear_offset(cond, -4.0 * ny_basin, -4.0 * nx_basin)
    c_lo = np.minimum(c_hw, c_fw)
    c_hi = np.maximum(c_hw, c_fw)
    # Conductive smectite side (< 2.55 decades) juxtaposed against resistive footwall (> 2.85 decades)
    clay_gate = (1.0 / (1.0 + np.exp((c_lo - 2.55) * 3.0))) * (1.0 / (1.0 + np.exp(-(c_hi - 2.85) * 3.0)))
    smectite_margin = np.abs(c_fw - c_hw) * clay_gate
    mm[13] = ocda._robust_z_pos(smectite_margin.astype(np.float32), foot)
    del cond, c_hw, c_fw, c_lo, c_hi, clay_gate, smectite_margin

    # Dominant crust-to-surface strike tangent (ty_st, tx_st) for anisotropic hydrothermal steering
    ty_st = (-nx_basin).astype(np.float32)
    tx_st = ny_basin.astype(np.float32)
    del ny_basin, nx_basin

    # Ch 14: Strike-steered anisotropic thermal conduit bridge (GDR springs + quartz + 2m F2mDAB + sinter)
    mm[14] = _build_aniso_thermal_conduit_bridge(ddir, transform, (H, W), foot, ty_st, tx_st)
    del ty_st, tx_st

    # Ch 15: Locally de-meaned kinematic slip compatibility x multi-physics worm persistence
    dil = ocda._read_prepared_band(bands_dir, 8, "geod_dilaterate", foot)
    shr = ocda._read_prepared_band(bands_dir, 7, "geod_shearrate", foot)
    opt_ext = 0.5 * (1.0 + np.cos(2.0 * (theta_grav_w - 1.18)))
    opt_wl = 0.5 * (1.0 + np.cos(2.0 * (theta_grav_w - 2.35)))
    kin_raw = (ocda._robust_z_pos(dil, foot) * opt_ext + 0.75 * ocda._robust_z_pos(shr, foot) * opt_wl).astype(np.float32)
    # Normalize relative to 3.5 km local neighborhood so trees CANNOT use it as a quadrant lookup!
    kin_rel = kin_raw / (ndi.gaussian_filter(kin_raw, 35.0, mode="nearest") + np.float32(0.15))
    worm_union = (0.55 * g_worm_pers + 0.45 * m_worm_pers).astype(np.float32)
    mm[15] = ocda._robust_z_pos((kin_rel * worm_union).astype(np.float32), foot)
    del dil, shr, opt_ext, opt_wl, kin_raw, kin_rel, worm_union, g_worm_pers, m_worm_pers

    # Ch 16: 4-physics strike orientation consensus order parameter (topography, RTP mag, gravity worm, MT)
    c4 = (
        np.cos(2.0 * theta_topo_line)
        + np.cos(2.0 * theta_mag_w)
        + np.cos(2.0 * theta_grav_w)
        + np.cos(2.0 * theta_mt_w)
    ) * np.float32(0.25)
    s4 = (
        np.sin(2.0 * theta_topo_line)
        + np.sin(2.0 * theta_mag_w)
        + np.sin(2.0 * theta_grav_w)
        + np.sin(2.0 * theta_mt_w)
    ) * np.float32(0.25)
    r4 = np.hypot(c4, s4).astype(np.float32)
    mm[16] = np.where(foot, r4, 0.0)
    del theta_topo_line, theta_mag_w, theta_grav_w, theta_mt_w, c4, s4

    # Ch 17: Dual-Regime 100% Label-Free Structural-Hydrothermal Prior (`M_struct`)
    # Fuses Regime I (elevation-invariant ridge/scarp/knick/saddle skeleton) +
    # Regime II (55-deg up-dip worm back-projected gravity/RTP/MT crests + hydrothermal boundary conduits)
    sub_updip = (
        0.34 * mm[2]
        + 0.24 * mm[4]
        + 0.16 * mm[5]
        + 0.14 * mm[13]
        + 0.12 * mm[12]
    ) * (1.0 + 0.28 * mm[14])
    dual_prior = (0.54 * mm[11] + 0.46 * ocda._robust_z_pos(sub_updip.astype(np.float32), foot)) * (0.65 + 0.35 * r4) * road_damp
    mm[17] = _transverse_1px_centerline(dual_prior.astype(np.float32), foot)
    del sub_updip, dual_prior, r4, road_damp, cross_cut

    mm.flush()
    gc.collect()

    meta = {
        "schema": UWBP_SCHEMA_VERSION,
        "names": list(UWBP_FREE_NAMES),
        "shape": [len(UWBP_FREE_NAMES), H, W],
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    log(f"[UWBP] Saved verified 18-channel UWBP-DRCS stack to {out_path}")
    return np.load(out_path, mmap_mode="r")


def build_uwbp_crest_carrier(uwbp_mm: np.ndarray, ocda_mm: np.ndarray, foot: np.ndarray) -> np.ndarray:
    """Compute 100% label-free 1-px transverse crest carrier combining surface scarps & up-dip worms."""
    surf_c = np.maximum(
        np.asarray(uwbp_mm[11], dtype=np.float32),
        np.clip(np.asarray(ocda_mm[0], dtype=np.float32), 0.0, 1.0),
    )
    sub_c = np.maximum(
        np.asarray(uwbp_mm[2], dtype=np.float32),
        np.maximum(
            np.asarray(uwbp_mm[4], dtype=np.float32),
            np.asarray(uwbp_mm[17], dtype=np.float32),
        ),
    )
    comp = ndi.gaussian_filter((0.52 * surf_c + 0.48 * sub_c).astype(np.float32), 0.8, mode="nearest")
    del surf_c, sub_c

    axx = ndi.gaussian_filter(comp, 1.2, order=(0, 2), mode="nearest")
    ayy = ndi.gaussian_filter(comp, 1.2, order=(2, 0), mode="nearest")
    axy = ndi.gaussian_filter(comp, 1.2, order=(1, 1), mode="nearest")
    phi = 0.5 * np.arctan2(2.0 * axy, axx - ayy + 1e-12)
    ny = np.sin(phi).astype(np.float32)
    nx = np.cos(phi).astype(np.float32)
    del axx, ayy, axy, phi

    c_p1 = ocda.sample_bilinear_offset(comp, 1.35 * ny, 1.35 * nx)
    c_m1 = ocda.sample_bilinear_offset(comp, -1.35 * ny, -1.35 * nx)
    c_p2 = ocda.sample_bilinear_offset(comp, 2.50 * ny, 2.50 * nx)
    c_m2 = ocda.sample_bilinear_offset(comp, -2.50 * ny, -2.50 * nx)
    del ny, nx

    is_crest1 = comp >= 0.96 * np.maximum(c_p1, c_m1)
    prom2 = np.clip((comp - 0.5 * (c_p2 + c_m2)) * 4.0, 0.0, 1.0)
    carrier = np.where(is_crest1, 0.74 + 0.26 * prom2, 0.24 + 0.20 * prom2).astype(np.float32)
    return np.where(foot, carrier, 0.0)


def pack_dinkelbach_dti_300m(
    belief: np.ndarray,
    allowed: np.ndarray,
    max_budget: int,
    min_dist_px: float = 3.05,
    fp_cost_lambda: float = 0.055,
    min_budget: int = 24_000,
    pool_mult: int = 18,
) -> np.ndarray:
    """Cost-sensitive Dinkelbach marginal-DTI lazy-greedy (CELF) submodular packer on the 300 m kernel.

    Maximizes `sum_z w(z) * max_{x in S} k(d(x, z)) - fp_cost_lambda * 0.2 * sum_{x in S} (1 - w_norm(x))`
    subject to `x in allowed`, `min_budget <= |S| <= max_budget`, and pairwise spacing `>= min_dist_px`.
    Stops automatically once marginal expected kernel gain falls below the false-positive denominator bar.
    """
    H, W = belief.shape
    w = np.where(np.isfinite(belief) & (belief > 0), belief, 0.0).astype(np.float32)
    cand_mask = np.asarray(allowed, bool) & (w > 0)
    n_cand = int(cand_mask.sum())
    out = np.zeros((H, W), dtype=bool)
    if n_cand == 0 or max_budget <= 0:
        return out

    # Scale w so p99.5 on allowed domain maps to unit local hit confidence for cost accounting
    p995 = float(np.percentile(w[cand_mask], 99.5)) if n_cand > 0 else 1.0
    w_unit = np.clip(w / max(p995, 1e-6), 0.0, 1.0).astype(np.float32)
    fp_pen = (np.float32(fp_cost_lambda * M.ALPHA) * (np.float32(1.0) - np.float32(0.5) * w_unit)).astype(np.float32)

    offs = M._OFFS
    ub = np.zeros((H, W), dtype=np.float32)
    for dy, dx, kk in offs:
        ub += M._shift(w_unit, -int(dy), -int(dx)) * np.float32(kk)
    net_ub = ub - fp_pen

    cy, cx = np.nonzero(cand_mask)
    scores = net_ub[cy, cx]
    k_pool = min(n_cand, max(int(max_budget) * pool_mult, 25_000))
    if n_cand > k_pool:
        sel = np.argpartition(scores, -k_pool)[-k_pool:]
        cy, cx, scores = cy[sel], cx[sel], scores[sel]

    order = np.argsort(-scores, kind="stable")
    cy, cx, scores = cy[order], cx[order], scores[order]
    heap: list[tuple[float, int, int, int, int]] = [
        (-float(s), idx, int(y), int(x), 0)
        for idx, (y, x, s) in enumerate(zip(cy.tolist(), cx.tolist(), scores.tolist()))
    ]
    heapq.heapify(heap)

    cov = np.zeros((H, W), dtype=np.float32)
    touch_epoch = np.zeros((H, W), dtype=np.int32)
    blocked = ~cand_mask.copy()

    r_blk = max(int(np.ceil(max(min_dist_px, 0.0))), 0)
    by_g, bx_g = np.ogrid[-r_blk:r_blk + 1, -r_blk:r_blk + 1]
    blk_disk = (by_g * by_g + bx_g * bx_g) < (max(min_dist_px, 0.0) ** 2 - 1e-6)
    blk_disk[r_blk, r_blk] = True

    accepted = 0
    step_id = 0
    while heap and accepted < max_budget:
        neg_net, idx, y, x, seen_ep = heapq.heappop(heap)
        if blocked[y, x]:
            continue
        cur_ep = int(touch_epoch[y, x])
        if cur_ep > seen_ep:
            gain = 0.0
            for dy, dx, kk in offs:
                yy = y + dy
                xx = x + dx
                if 0 <= yy < H and 0 <= xx < W:
                    rem = kk - float(cov[yy, xx])
                    if rem > 0.0:
                        gain += float(w_unit[yy, xx]) * rem
            net_gain = gain - float(fp_pen[y, x])
            if accepted >= min_budget and net_gain <= 0.0:
                continue
            if gain <= 1e-9:
                continue
            heapq.heappush(heap, (-net_gain, idx, y, x, cur_ep))
            continue

        if accepted >= min_budget and (-neg_net) <= 0.0:
            break

        out[y, x] = True
        accepted += 1
        step_id += 1

        for dy, dx, kk in offs:
            yy = y + dy
            xx = x + dx
            if 0 <= yy < H and 0 <= xx < W and kk > cov[yy, xx]:
                cov[yy, xx] = kk
        y_lo, y_hi = max(0, y - 6), min(H, y + 7)
        x_lo, x_hi = max(0, x - 6), min(W, x + 7)
        touch_epoch[y_lo:y_hi, x_lo:x_hi] = step_id

        ry0, ry1 = max(0, y - r_blk), min(H, y + r_blk + 1)
        rx0, rx1 = max(0, x - r_blk), min(W, x + r_blk + 1)
        ky0 = ry0 - (y - r_blk)
        ky1 = ky0 + (ry1 - ry0)
        kx0 = rx0 - (x - r_blk)
        kx1 = kx0 + (rx1 - rx0)
        blocked[ry0:ry1, rx0:rx1] |= blk_disk[ky0:ky1, kx0:kx1]

    return out
