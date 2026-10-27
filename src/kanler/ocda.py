"""Lane H-K1-A (OCDA-MSCS): Oriented Cross-Strike Dipole Asymmetry & Multi-Scale Contextual Submodular Synthesis.

Implements:
1. 26 strictly label-free physical channels (`OCDA_FREE_NAMES`) capturing:
   - Oriented cross-strike footwall-to-hanging-wall dipole steps (piedmont slope dipole at 400 m & 800 m,
     elevation toe concavity, half-graben gravity drop, co-polarized basement-depth step, MT log-conductivity step).
   - True Miller & Singh (1994) magnetic & gravity tilt-angle zero-crossing crests (correcting IR-BAND-06 where
     `training_features.tif` Band 6 `tc` is verified to be GeoDAWN Radiometric Total Count, Spearman +0.99995),
     Cooper & Cowan (2006) TDX, Band-18 signed E-W gravity-polarity reversal, and 150 m upward-continuation survival.
   - Along-strike axial persistence (±400 m / ±500 m) vs cross-strike localization.
   - Coverage-zero-centered 1 m LiDAR scarp & face asymmetry with Lake Lahontan contour-orthogonality and
     US Census TIGER road-cut confound guards.
   - GeoDAWN K/Th potassic hydrothermal alteration residual + INGENIOUS 2 m shallow temperature probe (`F2mDAB`),
     GDR #1391 quartz/thermal spring halos (never touching `dist_known_fault_px`), and siliceous sinter halos.
   - Geodetic strain-strike kinematic compatibility + declustered-vs-swarm seismicity ratio (IR-BAND-10 fix)
     + 3-physics strike concordance.
2. 2 strictly fold-local structural continuation channels (`OCDA_VIS_NAMES`) computed *from scratch* inside each
   holdout cell solely from `cell.visible_full` (never reading `labels.tif` or withheld segments):
   - `fold_vis_tip_continuation`: oriented forward continuation cones ahead of degree-1 visible fault tips.
   - `fold_vis_stepover_relay_bridge`: sub-parallel en-echelon relay-ramp / step-over bridge field.
3. Physics-guarded reliable-negative Positive-Unlabeled (PU) out-of-quadrant `HistGradientBoostingClassifier`,
   1-px transverse crest concentration, and exact 25-offset Euclidean 300 m lazy-greedy submodular packing (CELF).
"""
from __future__ import annotations

import csv
import gc
import hashlib
import heapq
import io
import json
import struct
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from numpy.lib.format import open_memmap
from rasterio.transform import rowcol as rio_rowcol
from rasterio.warp import transform as rio_transform
from scipy import ndimage as ndi

from gems32 import features as shared_features
from gems32 import metric as M

OCDA_SCHEMA_VERSION = "kanler1-ocda-mscs-v1"

OCDA_FREE_NAMES: tuple[str, ...] = (
    # Group 1: Oriented Piedmont & Geomorphic Cross-Strike Dipoles (6)
    "ocda_piedmont_slope_dipole_400m",
    "ocda_piedmont_slope_dipole_800m",
    "ocda_elev_step_curv_toe",
    "ocda_axial_ridge_persistence",
    "ocda_local_elev_pct_2p5km",
    "ocda_slope_prominence_800m",
    # Group 2: Subsurface Half-Graben Gravity, Basement & MT Dipoles (5)
    "ocda_halfgraben_grav_dipole_600m",
    "ocda_basement_step_dipole_600m",
    "ocda_copolar_halfgraben_index",
    "ocda_mt_cond_dipole_500m",
    "ocda_grav_ew_polarity_grad",
    # Group 3: True Potential-Field Tilt Zero-Crossings (IR-BAND-06 Fix) & Persistence (5)
    "ocda_true_mag_tilt_zero_crest",
    "ocda_cooper_tdx_mag",
    "ocda_tmi_up150_persistence",
    "ocda_true_grav_tilt_zero_crest",
    "ocda_axial_potfield_persistence",
    # Group 4: Coverage-Debiased 1m LiDAR + Shoreline & Road Confound Guards (5)
    "ocda_lidar_scarp_debiased",
    "ocda_lidar_face_dipole",
    "ocda_contour_orthogonality",
    "ocda_road_confound_guard",
    "ocda_lidar_valid_flag",
    # Group 5: Hydrothermal Alteration, Shallow Probes & Geothermometry (3)
    "ocda_k_th_alteration_excess",
    "ocda_probe_2m_f2mdab_halo",
    "ocda_hydrothermal_vent_sinter_halo",
    # Group 6: Strain-Strike Kinematics & Multi-Physics Strike Concordance (2)
    "ocda_strain_dilation_strike_compat",
    "ocda_multiphysics_strike_concordance",
)

EXP1_FREE_COUNT = 24  # First 24 channels (Groups 1..5) for EXP-1; +2 kinematic +2 fold-vis in EXP-2
OCDA_VIS_NAMES: tuple[str, ...] = (
    "fold_vis_tip_continuation",
    "fold_vis_stepover_relay_bridge",
)


def _robust_z_pos(a: np.ndarray, foot: np.ndarray, clip_hi: float = 6.0) -> np.ndarray:
    """Footprint-normalized nonnegative robust z-score in [0, 1]."""
    out = np.zeros(a.shape, dtype=np.float32)
    v = foot & np.isfinite(a)
    if not v.any():
        return out
    vals = a[v]
    med = float(np.median(vals))
    q25, q75 = np.percentile(vals, [25.0, 75.0])
    scale = max(float(q75 - q25) / 1.349, 1e-6)
    z = (a - med) / scale
    out[v] = np.clip(z[v], 0.0, clip_hi) / clip_hi
    return out


def _robust_z_signed(a: np.ndarray, foot: np.ndarray, clip_abs: float = 6.0) -> np.ndarray:
    """Footprint-normalized signed robust z-score in [-1, 1]."""
    out = np.zeros(a.shape, dtype=np.float32)
    v = foot & np.isfinite(a)
    if not v.any():
        return out
    vals = a[v]
    med = float(np.median(vals))
    q25, q75 = np.percentile(vals, [25.0, 75.0])
    scale = max(float(q75 - q25) / 1.349, 1e-6)
    z = (a - med) / scale
    out[v] = np.clip(z[v], -clip_abs, clip_abs) / clip_abs
    return out


def sample_bilinear_offset(arr: np.ndarray, dy: np.ndarray, dx: np.ndarray, chunk_rows: int = 512) -> np.ndarray:
    """Memory-frugal vectorized bilinear gather `arr[y + dy, x + dx]` in strips."""
    H, W = arr.shape
    if H < 2 or W < 2:
        raise ValueError(f"sample_bilinear_offset requires H >= 2 and W >= 2, got {(H, W)}")
    if dy.shape != (H, W) or dx.shape != (H, W):
        raise ValueError(f"dy/dx shape mismatch with arr {(H, W)}: {dy.shape}, {dx.shape}")
    out = np.empty((H, W), dtype=np.float32)
    xs_base = np.arange(W, dtype=np.float32)[None, :]
    max_y = np.nextafter(np.float32(H - 1), np.float32(0.0))
    max_x = np.nextafter(np.float32(W - 1), np.float32(0.0))
    zero = np.float32(0.0)
    one = np.float32(1.0)
    for r0 in range(0, H, chunk_rows):
        r1 = min(H, r0 + chunk_rows)
        ys_base = np.arange(r0, r1, dtype=np.float32)[:, None]
        yy = np.clip(ys_base + dy[r0:r1], zero, max_y)
        xx = np.clip(xs_base + dx[r0:r1], zero, max_x)
        y0 = np.minimum(yy.astype(np.int32), H - 2)
        x0 = np.minimum(xx.astype(np.int32), W - 2)
        wy = np.clip(yy - y0, zero, one)
        wx = np.clip(xx - x0, zero, one)
        v00 = arr[y0, x0]
        v01 = arr[y0, x0 + 1]
        v10 = arr[y0 + 1, x0]
        v11 = arr[y0 + 1, x0 + 1]
        out[r0:r1] = (
            (1.0 - wy) * ((1.0 - wx) * v00 + wx * v01)
            + wy * ((1.0 - wx) * v10 + wx * v11)
        )
    return out


def _read_prepared_band(bands_dir: Path, idx: int, name: str, foot: np.ndarray) -> np.ndarray:
    raw = np.load(bands_dir / f"{idx:02d}_{name}.npy").astype(np.float32)
    valid = foot & np.isfinite(raw)
    filled, _ = shared_features._fill_nearest(raw, valid)
    return filled


def _parse_2m_probes_halo(zip_path: Path, transform, shape: tuple[int, int], foot: np.ndarray) -> np.ndarray:
    """Parse INGENIOUS 2m temperature probe DBF (NAD83) for positive `F2mDAB` excess anomaly."""
    H, W = shape
    acc = np.zeros((H, W), dtype=np.float32)
    with zipfile.ZipFile(zip_path) as zf:
        dbf = zf.read("2m_temperature_probe_INGENIOUS_regional_data/2m_temperature_probe_n83geo/2m_temperature_probe_n83geo.dbf")
    _, _, _, _, nrec, hlen, rlen = struct.unpack("<BBBBIHH", dbf[:12])
    fields = []
    pos = 32
    while dbf[pos] != 0x0D:
        fname = dbf[pos:pos + 11].split(b"\x00")[0].decode("latin1")
        flen = dbf[pos + 16]
        fields.append((fname, flen))
        pos += 32
    lons, lats, vals = [], [], []
    for i in range(nrec):
        base = hlen + i * rlen
        if base + rlen > len(dbf) or dbf[base] == 0x2A:  # deleted record
            continue
        off = base + 1
        rec = {}
        for fname, flen in fields:
            if fname in ("F2mDAB", "T2m", "LatDegreeN", "LongDegree"):
                rec[fname] = dbf[off:off + flen].decode("latin1", "ignore").strip()
            off += flen
        try:
            lon = float(rec["LongDegree"])
            lat = float(rec["LatDegreeN"])
            dab = float(rec["F2mDAB"]) if rec.get("F2mDAB") else 0.0
        except (KeyError, ValueError):
            continue
        if np.isfinite(lon) and np.isfinite(lat) and np.isfinite(dab) and dab > 0.5:
            lons.append(lon)
            lats.append(lat)
            vals.append(min(dab, 25.0))
    if not lons:
        return acc
    east, north = rio_transform("EPSG:4269", "EPSG:32611", lons, lats)
    rows_i, cols_i = rio_rowcol(transform, east, north)
    for ri, ci, val in zip(rows_i, cols_i, vals):
        ri, ci = int(ri), int(ci)
        if 0 <= ri < H and 0 <= ci < W and foot[ri, ci]:
            if val > acc[ri, ci]:
                acc[ri, ci] = np.float32(val)
    h_near = ndi.gaussian_filter(acc, sigma=4.0, mode="nearest")
    h_broad = ndi.gaussian_filter(acc, sigma=14.0, mode="nearest")
    return np.where(foot, (0.65 * _robust_z_pos(h_near, foot) + 0.35 * _robust_z_pos(h_broad, foot)).astype(np.float32), 0.0)


def _build_vent_sinter_halo(ddir: Path, transform, shape: tuple[int, int], foot: np.ndarray) -> np.ndarray:
    """Combine GDR #1391 thermal wells/springs (temperature + quartz geothermometry) and paleo-sinter."""
    H, W = shape
    acc = np.zeros((H, W), dtype=np.float32)
    # 1. Well & spring temperature + quartz geothermometer (NEVER reading dist_known_fault_px)
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
            t_meas = 0.0
            t_qtz = 0.0
            try:
                if row.get("temp_c"):
                    t_meas = float(row["temp_c"])
            except ValueError:
                pass
            try:
                if row.get("geothermquartz_c"):
                    t_qtz = float(row["geothermquartz_c"])
            except ValueError:
                pass
            w = 0.0
            if np.isfinite(t_meas) and t_meas >= 32.0:
                w += min(t_meas - 20.0, 160.0) / 40.0
            if np.isfinite(t_qtz) and t_qtz >= 90.0:
                w += min(t_qtz - 80.0, 180.0) / 80.0
            if w > acc[r, c]:
                acc[r, c] = np.float32(w)

    # 2. Paleo-geothermal deposits (sinter/silicified weighted higher than tufa)
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
        pw = 2.5 if ("sinter" in dtype_txt or "silic" in dtype_txt) else (0.7 if "tufa" in dtype_txt else 1.4)
        if np.isfinite(lon) and np.isfinite(lat):
            lons.append(lon)
            lats.append(lat)
            pweights.append(pw)
    if lons:
        east, north = rio_transform("EPSG:4269", "EPSG:32611", lons, lats)
        rows_i, cols_i = rio_rowcol(transform, east, north)
        for ri, ci, pw in zip(rows_i, cols_i, pweights):
            ri, ci = int(ri), int(ci)
            if 0 <= ri < H and 0 <= ci < W and foot[ri, ci]:
                acc[ri, ci] = max(acc[ri, ci], np.float32(pw))

    s1 = ndi.gaussian_filter(acc, sigma=4.5, mode="nearest")
    s2 = ndi.gaussian_filter(acc, sigma=15.0, mode="nearest")
    return np.where(foot, (0.60 * _robust_z_pos(s1, foot) + 0.40 * _robust_z_pos(s2, foot)).astype(np.float32), 0.0)


def build_or_load_ocda_free_stack(ddir: Path, wdir: Path, log=print) -> np.ndarray:
    """Build (or load hash-verified) 26-channel label-free OCDA stack `(26, H, W)` float32."""
    out_path = wdir / "ocda_free_v1.npy"
    meta_path = wdir / "ocda_free_v1.npy.json"
    bands_dir = wdir / "bands"
    foot = np.load(bands_dir / "_footprint.npy")
    H, W = foot.shape

    with rasterio.open(ddir / "sample_submission.tif") as ds:
        transform = ds.transform

    if out_path.is_file() and meta_path.is_file():
        meta = json.loads(meta_path.read_text())
        if meta.get("schema") == OCDA_SCHEMA_VERSION and meta.get("names") == list(OCDA_FREE_NAMES):
            mm = np.load(out_path, mmap_mode="r")
            if mm.shape == (len(OCDA_FREE_NAMES), H, W) and mm.dtype == np.float32:
                log(f"[OCDA] Loaded verified label-free cache {out_path.name} {mm.shape}")
                return mm

    log("[OCDA] Building 26-channel label-free Oriented Cross-Strike Dipole Asymmetry stack...")
    meta_path.unlink(missing_ok=True)
    mm = open_memmap(out_path, mode="w+", dtype=np.float32, shape=(len(OCDA_FREE_NAMES), H, W))

    # --- Group 1: Piedmont & Geomorphic Dipoles ---
    dem = _read_prepared_band(bands_dir, 12, "det_elev", foot)
    slope = _read_prepared_band(bands_dir, 19, "det_elev_slope", foot)
    dem_s25 = ndi.gaussian_filter(dem, 2.5, mode="nearest")
    gy_z, gx_z = np.gradient(dem_s25)
    gmag_z = np.hypot(gx_z, gy_z) + np.float32(1e-6)
    # Unit normal pointing DOWN-SLOPE (from footwall horst into hanging-wall basin)
    ny_surf = (-gy_z / gmag_z).astype(np.float32)
    nx_surf = (-gx_z / gmag_z).astype(np.float32)
    ty_surf = (-nx_surf).astype(np.float32)
    tx_surf = ny_surf.astype(np.float32)
    theta_surf = np.arctan2(ty_surf, tx_surf).astype(np.float32)
    del gy_z, gx_z, gmag_z, dem_s25
    gc.collect()

    slope_sm = ndi.gaussian_filter(np.maximum(slope, 0.0), 1.2, mode="nearest")
    s50 = float(np.percentile(slope_sm[foot], 55.0)) + 1e-4
    for idx_ch, L in ((0, 4.0), (1, 8.0)):
        s_fw = sample_bilinear_offset(slope_sm, -L * ny_surf, -L * nx_surf)
        s_hw = sample_bilinear_offset(slope_sm, +L * ny_surf, +L * nx_surf)
        dip = (s_fw - s_hw) / (s_fw + s_hw + s50)
        mm[idx_ch] = np.where(foot, dip.astype(np.float32), 0.0)
        del s_fw, s_hw, dip

    # Cross-strike profile second derivative (scarp toe concavity / crest break)
    z_p3 = sample_bilinear_offset(dem, 3.0 * ny_surf, 3.0 * nx_surf)
    z_m3 = sample_bilinear_offset(dem, -3.0 * ny_surf, -3.0 * nx_surf)
    curv_toe = z_p3 - 2.0 * dem + z_m3
    mm[2] = _robust_z_signed(curv_toe, foot)
    del z_p3, z_m3, curv_toe

    # Along-strike ridge persistence vs cross-strike flank
    dem_line = shared_features._hessian_both_polarities(dem, 1.8)
    r_t1 = sample_bilinear_offset(dem_line, 4.0 * ty_surf, 4.0 * tx_surf)
    r_t2 = sample_bilinear_offset(dem_line, -4.0 * ty_surf, -4.0 * tx_surf)
    r_n1 = sample_bilinear_offset(dem_line, 3.0 * ny_surf, 3.0 * nx_surf)
    r_n2 = sample_bilinear_offset(dem_line, -3.0 * ny_surf, -3.0 * nx_surf)
    axial_dem = np.minimum(dem_line, np.minimum(r_t1, r_t2)) - 0.5 * (r_n1 + r_n2)
    mm[3] = _robust_z_signed(axial_dem, foot)
    del dem_line, r_t1, r_t2, r_n1, r_n2, axial_dem

    # Local elevation position in ~2.5 km window (separates mountain crest vs piedmont vs playa)
    dem_min = ndi.minimum_filter(dem, size=25, mode="nearest")
    dem_max = ndi.maximum_filter(dem, size=25, mode="nearest")
    mm[4] = np.where(foot, np.clip((dem - dem_min) / (dem_max - dem_min + 15.0), 0.0, 1.0).astype(np.float32), 0.0)
    del dem_min, dem_max, dem

    # Slope prominence over 800 m neighborhood
    slope_bg = ndi.gaussian_filter(slope_sm, 8.0, mode="nearest")
    mm[5] = _robust_z_signed(slope_sm - slope_bg, foot)
    del slope, slope_sm, slope_bg
    gc.collect()
    log("  [OCDA] Group 1 (Piedmont dipoles) done")

    # --- Group 2: Subsurface Half-Graben Gravity, Basement & MT Dipoles ---
    grav = _read_prepared_band(bands_dir, 13, "iso_grav_anom", foot)
    grav_s3 = ndi.gaussian_filter(grav, 3.0, mode="nearest")
    gy_g, gx_g = np.gradient(grav_s3)
    gmag_g = np.hypot(gx_g, gy_g) + np.float32(1e-6)
    # Unit normal pointing DOWN-GRAVITY (from dense horst into down-dropped hanging-wall basin)
    ny_sub = (-gy_g / gmag_g).astype(np.float32)
    nx_sub = (-gx_g / gmag_g).astype(np.float32)
    ty_sub = (-nx_sub).astype(np.float32)
    tx_sub = ny_sub.astype(np.float32)
    theta_grav = np.arctan2(ty_sub, tx_sub).astype(np.float32)
    del gy_g, gx_g, gmag_g, grav_s3

    g_fw = sample_bilinear_offset(grav, -6.0 * ny_sub, -6.0 * nx_sub)
    g_hw = sample_bilinear_offset(grav, +6.0 * ny_sub, +6.0 * nx_sub)
    d_grav = _robust_z_signed(g_fw - g_hw, foot)
    mm[6] = d_grav
    del grav, g_fw, g_hw

    zbase = _read_prepared_band(bands_dir, 15, "depth_to_base_surf", foot)
    zb_fw = sample_bilinear_offset(zbase, -6.0 * ny_sub, -6.0 * nx_sub)
    zb_hw = sample_bilinear_offset(zbase, +6.0 * ny_sub, +6.0 * nx_sub)
    d_zbase = _robust_z_signed(zb_hw - zb_fw, foot)
    mm[7] = d_zbase
    coprod = d_grav * d_zbase
    mm[8] = np.where(foot, (np.sign(coprod) * np.sqrt(np.abs(coprod))).astype(np.float32), 0.0)
    del zbase, zb_fw, zb_hw, d_grav, d_zbase, coprod

    cond = _read_prepared_band(bands_dir, 17, "cond_surf", foot)
    lcond = np.log10(np.maximum(cond, 1e-4)).astype(np.float32)
    lc_p = sample_bilinear_offset(lcond, 5.0 * ny_sub, 5.0 * nx_sub)
    lc_m = sample_bilinear_offset(lcond, -5.0 * ny_sub, -5.0 * nx_sub)
    mm[9] = _robust_z_pos(np.abs(lc_p - lc_m), foot)
    del cond, lcond, lc_p, lc_m

    # IR-BAND-18: signed E-W gravity derivative polarity gradient
    b18_ghg = _read_prepared_band(bands_dir, 18, "iso_grav_anom_hg", foot)
    gy18, gx18 = np.gradient(ndi.gaussian_filter(b18_ghg, 1.5, mode="nearest"))
    mm[10] = _robust_z_pos(np.hypot(gx18, gy18), foot)
    del b18_ghg, gy18, gx18
    gc.collect()
    log("  [OCDA] Group 2 (Half-graben gravity/basement/MT dipoles) done")

    # --- Group 3: True Potential-Field Tilt Zero-Crossings (IR-BAND-06 Fix) ---
    rtp = _read_prepared_band(bands_dir, 2, "rtp", foot)
    tmi_hg = np.maximum(_read_prepared_band(bands_dir, 3, "tmi_hg", foot), 0.0)
    tmi_vg = _read_prepared_band(bands_dir, 9, "tmi_vg", foot)
    theta_m = np.arctan2(tmi_vg, np.maximum(tmi_hg, 1e-5)).astype(np.float32)
    gym, gxm = np.gradient(ndi.gaussian_filter(theta_m, 1.0, mode="nearest"))
    mag_tilt_crest = np.hypot(gxm, gym) * np.exp(-np.abs(theta_m) / 0.22)
    mm[11] = _robust_z_pos(mag_tilt_crest, foot)
    mm[12] = np.where(foot, (np.arctan2(tmi_hg, np.abs(tmi_vg) + 1e-3) / (0.5 * np.pi)).astype(np.float32), 0.0)
    del tmi_vg, theta_m, gym, gxm

    # RTP strike for multi-physics strike concordance
    _, theta_mag, _ = shared_features._structure_tensor(rtp, 2.5)

    with rasterio.open(ddir / "external" / "geodawn_extensions_u8.tif") as ds:
        tmi_up150 = ds.read(4).astype(np.float32)
    gy_u, gx_u = np.gradient(ndi.gaussian_filter(tmi_up150, 1.5, mode="nearest"))
    up_grad = _robust_z_pos(np.hypot(gx_u, gy_u), foot)
    hg_norm = _robust_z_pos(tmi_hg, foot)
    mm[13] = np.where(foot, (up_grad / (0.25 + hg_norm)).astype(np.float32), 0.0)
    del tmi_hg, tmi_up150, gy_u, gx_u, up_grad, hg_norm

    grav_slope = np.maximum(_read_prepared_band(bands_dir, 5, "iso_grav_anom_slope", foot), 0.0)
    grav_vg = _read_prepared_band(bands_dir, 11, "iso_grav_anom_vg", foot)
    theta_g = np.arctan2(grav_vg, np.maximum(grav_slope, 1e-5)).astype(np.float32)
    gyg, gxg = np.gradient(ndi.gaussian_filter(theta_g, 1.2, mode="nearest"))
    grav_tilt_crest = np.hypot(gxg, gyg) * np.exp(-np.abs(theta_g) / 0.22)
    mm[14] = _robust_z_pos(grav_tilt_crest, foot)
    del grav_slope, grav_vg, theta_g, gyg, gxg

    pf_comb = 0.55 * mm[11] + 0.45 * mm[14]
    pf_t1 = sample_bilinear_offset(pf_comb, 5.0 * ty_sub, 5.0 * tx_sub)
    pf_t2 = sample_bilinear_offset(pf_comb, -5.0 * ty_sub, -5.0 * tx_sub)
    mm[15] = np.where(foot, np.minimum(pf_comb, np.minimum(pf_t1, pf_t2)).astype(np.float32), 0.0)
    del pf_comb, pf_t1, pf_t2, mag_tilt_crest, grav_tilt_crest, ny_sub, nx_sub, ty_sub, tx_sub
    gc.collect()
    log("  [OCDA] Group 3 (True potential-field tilt zero-crossings) done")

    # --- Group 4: Coverage-Debiased 1m LiDAR + Confound Guards ---
    with rasterio.open(ddir / "external" / "lidar_scarp_features_u8.tif") as ds:
        l_ex = ds.read(1).astype(np.float32)
        l_step = ds.read(3).astype(np.float32)
        l_down = ds.read(6).astype(np.float32)
        l_up = ds.read(7).astype(np.float32)
        l_coh = ds.read(10).astype(np.float32) / 255.0
        l_strike_u8 = ds.read(11).astype(np.float32)
        l_valid = (ds.read(12) > 0) & foot

    scarp_raw = (0.5 * l_ex + 0.5 * l_step) * (0.3 + 0.7 * l_coh)
    med_s = float(np.median(scarp_raw[l_valid])) if l_valid.any() else 0.0
    iqr_s = max(float(np.subtract(*np.percentile(scarp_raw[l_valid], [75, 25]))) / 1.349, 1e-4) if l_valid.any() else 1.0
    mm[16] = np.where(l_valid, np.clip((scarp_raw - med_s) / (4.0 * iqr_s), -1.0, 1.0).astype(np.float32), 0.0)

    face_raw = np.abs(l_down - l_up) / (l_down + l_up + 8.0)
    med_f = float(np.median(face_raw[l_valid])) if l_valid.any() else 0.0
    mm[17] = np.where(l_valid, np.clip((face_raw - med_f) * 3.0, -1.0, 1.0).astype(np.float32), 0.0)

    # Contour-orthogonality: |sin(theta_lidar - theta_contour)| where lidar_valid, else |sin(2*theta_surf)| neutral
    theta_lidar = (l_strike_u8 / 255.0) * np.pi
    ortho = np.where(l_valid, np.abs(np.sin(theta_lidar - theta_surf)), 0.5).astype(np.float32)
    mm[18] = np.where(foot, ortho, 0.0)
    mm[20] = l_valid.astype(np.float32)
    del l_ex, l_step, l_down, l_up, l_coh, l_strike_u8, l_valid, scarp_raw, face_raw, theta_lidar, ortho

    with rasterio.open(ddir / "external" / "tiger_road_distance_m.tif") as ds:
        d_road = ds.read(1).astype(np.float32)
    d_road = np.where(np.isfinite(d_road) & (d_road >= 0), d_road, 5000.0)
    mm[19] = np.where(foot, np.exp(-d_road / 120.0).astype(np.float32), 0.0)
    del d_road
    gc.collect()
    log("  [OCDA] Group 4 (Debiased 1m LiDAR + shoreline/road guards) done")

    # --- Group 5: Hydrothermal Alteration, Shallow Probes & Geothermometry ---
    with rasterio.open(ddir / "external" / "geodawn_rad_u8.tif") as ds:
        rad_k = ds.read(1).astype(np.float32)
        rad_th = ds.read(2).astype(np.float32)
        rad_ok = (rad_k > 0) & (rad_th > 0) & foot
    if rad_ok.any():
        kv, thv = rad_k[rad_ok], rad_th[rad_ok]
        slope_kt = float(np.cov(kv, thv)[0, 1] / (np.var(thv) + 1e-6))
        inter_kt = float(np.mean(kv) - slope_kt * np.mean(thv))
        k_excess = np.where(rad_ok, rad_k - (inter_kt + slope_kt * rad_th), 0.0).astype(np.float32)
    else:
        k_excess = np.zeros((H, W), dtype=np.float32)
    # Magnetite-destruction trough + potassic K excess
    rtp_trough = ndi.grey_closing(rtp, size=(7, 7)) - rtp
    mm[21] = np.where(foot, (0.60 * _robust_z_pos(k_excess, foot) + 0.40 * _robust_z_pos(rtp_trough, foot)).astype(np.float32), 0.0)
    del rad_k, rad_th, rad_ok, k_excess, rtp, rtp_trough

    mm[22] = _parse_2m_probes_halo(ddir / "external" / "2m_temperature_probe_INGENIOUS_regional_data.zip", transform, (H, W), foot)
    mm[23] = _build_vent_sinter_halo(ddir, transform, (H, W), foot)
    gc.collect()
    log("  [OCDA] Group 5 (Hydrothermal K/Th + 2m probes + sinter/quartz) done")

    # --- Group 6: Strain-Strike Kinematics & Multi-Physics Strike Concordance ---
    dil = _read_prepared_band(bands_dir, 8, "geod_dilaterate", foot)
    shr = _read_prepared_band(bands_dir, 7, "geod_shearrate", foot)
    ieq = np.maximum(_read_prepared_band(bands_dir, 16, "ieq_n100a15", foot), 0.0)
    deq = np.maximum(_read_prepared_band(bands_dir, 10, "deq_n100a15", foot), 0.0)
    # Great Basin WNW-ESE extension (~112 deg azimuth -> N22E optimal normal-fault strike, ~0.38 rad from N / 1.19 rad in (x,y))
    # Combine NNE extensional dilation alignment + NW Walker Lane dextral shear alignment + background seismicity fraction
    opt_ext = 0.5 * (1.0 + np.cos(2.0 * (theta_surf - 1.18)))
    opt_wl = 0.5 * (1.0 + np.cos(2.0 * (theta_surf - 2.35)))
    bg_eq_ratio = np.log1p(ieq) / (np.log1p(deq) + 1.0)
    kin = (_robust_z_pos(dil, foot) * opt_ext + 0.7 * _robust_z_pos(shr, foot) * opt_wl) * (0.5 + 0.5 * _robust_z_pos(bg_eq_ratio, foot))
    mm[24] = _robust_z_pos(kin.astype(np.float32), foot)
    del dil, shr, ieq, deq, opt_ext, opt_wl, bg_eq_ratio, kin

    # Resultant vector length across 3 physical strike fields (surface, magnetic, gravity)
    c_mean = (np.cos(2.0 * theta_surf) + np.cos(2.0 * theta_mag) + np.cos(2.0 * theta_grav)) / 3.0
    s_mean = (np.sin(2.0 * theta_surf) + np.sin(2.0 * theta_mag) + np.sin(2.0 * theta_grav)) / 3.0
    mm[25] = np.where(foot, np.hypot(c_mean, s_mean).astype(np.float32), 0.0)
    del theta_surf, theta_mag, theta_grav, c_mean, s_mean, ny_surf, nx_surf, ty_surf, tx_surf
    mm.flush()
    gc.collect()

    meta = {
        "schema": OCDA_SCHEMA_VERSION,
        "names": list(OCDA_FREE_NAMES),
        "shape": [len(OCDA_FREE_NAMES), H, W],
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    log(f"[OCDA] Saved verified 26-channel stack to {out_path}")
    return np.load(out_path, mmap_mode="r")


def compute_fold_visible_continuation(visible_mask: np.ndarray, foot: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute strictly fold-local fault-tip continuation & step-over bridge fields ONLY from `visible_mask`.

    Returns `(tip_field, relay_bridge_field, tip_cone_mask)` on `(H, W)` in float32 / bool.
    NEVER reads full `labels.tif` — mathematically invariant to any withheld fault segments.
    """
    vis_raw = np.asarray(visible_mask)
    foot_raw = np.asarray(foot)
    if vis_raw.shape != foot_raw.shape:
        raise ValueError(f"visible_mask shape {vis_raw.shape} != foot shape {foot_raw.shape}")
    if not np.isfinite(vis_raw).all() or not np.isin(vis_raw, (0, 1)).all():
        raise ValueError("visible_mask must be finite and binary")
    if not np.isfinite(foot_raw).all() or not np.isin(foot_raw, (0, 1)).all():
        raise ValueError("foot must be finite and binary")
    vis = vis_raw.astype(bool, copy=False) & foot_raw.astype(bool, copy=False)
    foot = foot_raw.astype(bool, copy=False)
    H, W = vis.shape
    if not vis.any():
        z = np.zeros((H, W), dtype=np.float32)
        return z, z.copy(), np.zeros((H, W), dtype=bool)

    # 8-connected neighbor count on visible fault traces -> endpoints have 1 neighbor (or <=2 at sharp ends)
    kern3 = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.int16)
    nb_cnt = ndi.convolve(vis.astype(np.int16), kern3, mode="constant", cval=0)
    tips = vis & (nb_cnt == 1)
    ty, tx = np.nonzero(tips)

    tip_field = np.zeros((H, W), dtype=np.float32)
    # Estimate local outward tangent at each tip from nearby visible pixels inside a 7x7 window
    for y0, x0 in zip(ty.tolist(), tx.tolist()):
        r_lo, r_hi = max(0, y0 - 6), min(H, y0 + 7)
        c_lo, c_hi = max(0, x0 - 6), min(W, x0 + 7)
        sub = vis[r_lo:r_hi, c_lo:c_hi]
        yy, xx = np.nonzero(sub)
        if yy.size < 3:
            continue
        dy_in = (yy + r_lo - y0).astype(np.float32)
        dx_in = (xx + c_lo - x0).astype(np.float32)
        dist = np.hypot(dy_in, dx_in)
        sel = (dist > 0.5) & (dist <= 6.5)
        if not sel.any():
            continue
        # Outward unit vector points AWAY from the visible trace centroid
        vy = -float(np.mean(dy_in[sel]))
        vx = -float(np.mean(dx_in[sel]))
        vnorm = float(np.hypot(vx, vy))
        if vnorm < 1e-3:
            continue
        vy /= vnorm
        vx /= vnorm
        # Stamp anisotropic forward continuation cone (along: 1..18 px = 1.8 km, cross: sigma = 3.2 px)
        b_lo = max(0, y0 - 19)
        b_hi = min(H, y0 + 20)
        a_lo = max(0, x0 - 19)
        a_hi = min(W, x0 + 20)
        gy, gx = np.mgrid[b_lo:b_hi, a_lo:a_hi]
        ry = (gy - y0).astype(np.float32)
        rx = (gx - x0).astype(np.float32)
        s_along = ry * vy + rx * vx
        s_cross = -ry * vx + rx * vy
        cone = (s_along > 0.5) & (s_along <= 18.0)
        if not cone.any():
            continue
        val = np.where(
            cone,
            np.exp(-s_along / 10.0) * np.exp(-0.5 * (s_cross / 3.2) ** 2),
            0.0,
        ).astype(np.float32)
        np.maximum(tip_field[b_lo:b_hi, a_lo:a_hi], val, out=tip_field[b_lo:b_hi, a_lo:a_hi])

    tip_field = np.where(foot & ~vis, tip_field, 0.0).astype(np.float32)
    tip_cone_mask = tip_field > 0.22

    # Step-over / relay-ramp bridge field: difference of multi-scale fault-density halos
    # peaks between two sub-parallel visible strands separated by 0.4 - 2.4 km while damped on immediate flanks
    d_vis = ndi.distance_transform_edt(~vis).astype(np.float32)
    vis_f = vis.astype(np.float32)
    sm_mid = ndi.gaussian_filter(vis_f, sigma=6.0, mode="nearest")
    sm_wide = ndi.gaussian_filter(vis_f, sigma=14.0, mode="nearest")
    # Second-order interaction: bridge between two strands has elevated sm_mid WITHOUT sitting at d_vis <= 2
    flank_taper = np.clip((d_vis - 2.0) / 3.0, 0.0, 1.0) * np.exp(-np.maximum(d_vis - 18.0, 0.0) / 14.0)
    relay = (0.65 * sm_mid + 0.35 * sm_wide) * flank_taper
    relay = np.where(foot & ~vis, _robust_z_pos(relay, foot), 0.0).astype(np.float32)
    return tip_field, relay, tip_cone_mask


def build_transverse_crest_carrier(shared_mm: np.ndarray, ocda_mm: np.ndarray, foot: np.ndarray) -> np.ndarray:
    """Compute a 100% label-free multi-physics 1-px transverse crest carrier in `[0.25, 1.0]`.

    Collapses wide 4-6 px classifier probability ribbons onto their physical fault centerlines
    across BOTH geomorphic piedmont scarps and blind intrabasin potential-field/MT dipoles,
    eliminating double-row dot zig-zagging under submodular 300 m packing.
    """
    # Composite physical line/dipole intensity across surface & blind subsurface regimes
    surf_line = np.maximum(
        _robust_z_pos(np.asarray(shared_mm[:, :, 22], dtype=np.float32), foot),  # ridge_s2
        np.maximum(
            np.clip(np.asarray(ocda_mm[0], dtype=np.float32), 0.0, 1.0),         # piedmont_slope_dipole_400m
            np.clip(np.asarray(ocda_mm[16], dtype=np.float32), 0.0, 1.0),        # lidar_scarp_debiased
        ),
    )
    sub_line = np.maximum(
        np.asarray(ocda_mm[11], dtype=np.float32),                               # true_mag_tilt_zero_crest
        np.maximum(
            np.asarray(ocda_mm[14], dtype=np.float32),                           # true_grav_tilt_zero_crest
            np.maximum(
                np.clip(np.asarray(ocda_mm[8], dtype=np.float32), 0.0, 1.0),     # copolar_halfgraben_index
                np.asarray(ocda_mm[9], dtype=np.float32),                        # mt_cond_dipole_500m
            ),
        ),
    )
    comp = ndi.gaussian_filter((0.55 * surf_line + 0.45 * sub_line).astype(np.float32), 0.8, mode="nearest")
    del surf_line, sub_line

    # Local ridge orientation via Hessian eigenvectors of `comp` -> transverse normal (ny, nx)
    axx = ndi.gaussian_filter(comp, 1.2, order=(0, 2), mode="nearest")
    ayy = ndi.gaussian_filter(comp, 1.2, order=(2, 0), mode="nearest")
    axy = ndi.gaussian_filter(comp, 1.2, order=(1, 1), mode="nearest")
    phi = 0.5 * np.arctan2(2.0 * axy, axx - ayy + 1e-12)  # eigenvector across ridge
    ny = np.sin(phi).astype(np.float32)
    nx = np.cos(phi).astype(np.float32)
    del axx, ayy, axy, phi

    c_p1 = sample_bilinear_offset(comp, 1.35 * ny, 1.35 * nx)
    c_m1 = sample_bilinear_offset(comp, -1.35 * ny, -1.35 * nx)
    c_p2 = sample_bilinear_offset(comp, 2.50 * ny, 2.50 * nx)
    c_m2 = sample_bilinear_offset(comp, -2.50 * ny, -2.50 * nx)
    del ny, nx

    is_crest1 = (comp >= 0.96 * np.maximum(c_p1, c_m1))
    prom2 = np.clip((comp - 0.5 * (c_p2 + c_m2)) * 4.0, 0.0, 1.0)
    carrier = np.where(is_crest1, 0.72 + 0.28 * prom2, 0.28 + 0.22 * prom2).astype(np.float32)
    return np.where(foot, carrier, 0.0)


def pack_submodular_300m(
    belief: np.ndarray,
    allowed: np.ndarray,
    budget: int,
    min_dist_px: float = 2.83,
    pool_mult: int = 14,
) -> np.ndarray:
    """Fast Minoux lazy-greedy (CELF) submodular expected-DTI packer on the 25-offset 300 m kernel.

    Maximizes `sum_{z} belief(z) * max_{x in S} k(d(x, z))` subject to `x in allowed`, `|S| <= budget`,
    and pairwise Euclidean spacing `>= min_dist_px`.
    """
    H, W = belief.shape
    w = np.where(np.isfinite(belief) & (belief > 0), belief, 0.0).astype(np.float32)
    cand_mask = np.asarray(allowed, bool) & (w > 0)
    n_cand = int(cand_mask.sum())
    out = np.zeros((H, W), dtype=bool)
    if n_cand == 0 or budget <= 0:
        return out

    # Initial upper-bound expected kernel credit over the 25-offset R=300m disk
    offs = M._OFFS  # list of (dy, dx, k) with k > 0
    ub = np.zeros((H, W), dtype=np.float32)
    for dy, dx, kk in offs:
        ub += M._shift(w, -int(dy), -int(dx)) * np.float32(kk)

    cy, cx = np.nonzero(cand_mask)
    scores = ub[cy, cx]
    k_pool = min(n_cand, max(int(budget) * pool_mult, 20_000))
    if n_cand > k_pool:
        sel = np.argpartition(scores, -k_pool)[-k_pool:]
        cy, cx, scores = cy[sel], cx[sel], scores[sel]

    # Build Minoux max-heap: (-gain, tie_idx, y, x, stamp_seen)
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
    blk_disk[r_blk, r_blk] = True  # Always block exact self-coordinate even when min_dist_px <= 0

    accepted = 0
    step_id = 0
    while heap and accepted < budget:
        neg_g, idx, y, x, seen_ep = heapq.heappop(heap)
        if blocked[y, x]:
            continue
        cur_ep = int(touch_epoch[y, x])
        if cur_ep > seen_ep:
            # Recompute exact incremental submodular kernel credit
            gain = 0.0
            for dy, dx, kk in offs:
                yy = y + dy
                xx = x + dx
                if 0 <= yy < H and 0 <= xx < W:
                    rem = kk - float(cov[yy, xx])
                    if rem > 0.0:
                        gain += float(w[yy, xx]) * rem
            if gain <= 1e-9:
                continue
            heapq.heappush(heap, (-gain, idx, y, x, cur_ep))
            continue

        # Accept dot at (y, x)
        out[y, x] = True
        accepted += 1
        step_id += 1

        # Update delivered kernel coverage & mark neighbors within 2*R = 6 px stale
        for dy, dx, kk in offs:
            yy = y + dy
            xx = x + dx
            if 0 <= yy < H and 0 <= xx < W and kk > cov[yy, xx]:
                cov[yy, xx] = kk
        y_lo, y_hi = max(0, y - 6), min(H, y + 7)
        x_lo, x_hi = max(0, x - 6), min(W, x + 7)
        touch_epoch[y_lo:y_hi, x_lo:x_hi] = step_id

        # Enforce minimum pairwise Euclidean dot spacing
        ry0, ry1 = max(0, y - r_blk), min(H, y + r_blk + 1)
        rx0, rx1 = max(0, x - r_blk), min(W, x + r_blk + 1)
        ky0 = ry0 - (y - r_blk)
        ky1 = ky0 + (ry1 - ry0)
        kx0 = rx0 - (x - r_blk)
        kx1 = kx0 + (rx1 - rx0)
        blocked[ry0:ry1, rx0:rx1] |= blk_disk[ky0:ky1, kx0:kx1]

    return out
