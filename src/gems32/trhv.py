"""H46-1: Two-Regime Hydrothermal-Vent & Geophysical Residual Allocation (TRHV).

Builds 8 strictly label-free physical channels (`TRHV_EXTRA_CHANNELS`) from:
  1. Official UNR / DOE GDR #1391 GREAT BASIN 2-m temperature probe survey (`2,782` in-footprint
     stations; Sladek & Coolbaugh depth/albedo-corrected `F2mDAB` + sanitized `T2m - T15m` gradient),
  2. Official UNR / DOE GDR #1391 paleo-geothermal sinter / travertine / silicified vent inventory
     (`281` in-footprint quaternary/neogene hydrothermal vent deposits, down-weighting lacustrine tufa),
  3. Official US Census TIGER/Line 2024 road-centerline distance raster (`tiger_road_distance_m.tif`,
     vetoing cut-and-fill highway/railroad grade mimics in 1 m 3DEP LiDAR & magnetic gradients),
  4. Upward-continued magnetic contact persistence & geodetic transtensional potential-field coupling,

and implements leak-free fold-local Regime A (`fit_predict_exposed63`), Regime B
(`fit_predict_vent_sarpu63`), and exact sequential residual-coverage CELF allocation
(`emit_two_regime_trhv`) via `gems32.emitter.emit(..., initial_mask=...)`.

Pure stdlib `zipfile + struct` + `pyproj` parses the `EPSG:4269` (`shape_type=1` Point) shapefiles
so CI (`requirements.txt`, without `geopandas`) executes 100% deterministically under `< 750 MB` RSS.
"""

from __future__ import annotations

import gc
import struct
import zipfile
from pathlib import Path

import numpy as np
import pyproj
import rasterio
from numpy.lib.format import open_memmap
from rasterio.transform import rowcol
from scipy.ndimage import binary_dilation, distance_transform_edt, gaussian_filter
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from . import emitter, mdrc, spcp

TRHV_EXTRA_CHANNELS: tuple[str, ...] = (
    "gdr_2m_dab_plume",            # 0: UNR/GDR 2-m probe depth/albedo-corrected thermal plume (F2mDAB)
    "gdr_2m_vert_grad",            # 1: Sanitized shallow convective thermal gradient (T2m - T1.5m + elev resid)
    "gdr_paleo_sinter_vent",       # 2: Hydrothermal sinter/travertine/silicified vent kernel (tufa-deweighted)
    "vent_conduit_coupling",       # 3: Thermal/paleo vent x geophysical PF/MT/demag fault-conduit coupling
    "tiger_road_clean_gate",       # 4: Census TIGER 2024 road/rail prism veto gate 1 - exp(-(d/180m)^2)
    "lidar_tiger_lahontan_clean",  # 5: Doubly de-confounded 1m LiDAR scarp (TIGER road + Lahontan shoreline veto)
    "mag_up150_contact_persist",   # 6: Strike-chained 150m upward-continued magnetic contact persistence
    "geod_strain_pf_obliquity",    # 7: Geodetic transtension x potential-field curvature concordance
)

# Observability covariates for Regime B propensity model `e(z)`:
# Base indices: B12 detrended elev (11), B15 depth_to_basement (14), B19 slope (18)
OBS_BASE_IDX: tuple[int, ...] = (11, 14, 18)
# SPCP indices: lidar_valid_mask (12), lahontan_contour_orthog (14), piedmont_burial_prior (16)
OBS_SPCP_IDX: tuple[int, ...] = (12, 14, 16)
# TRHV indices: tiger_road_clean_gate (4)
OBS_TRHV_IDX: tuple[int, ...] = (4,)


def _safe_float(val: object) -> float:
    try:
        s = str(val).strip()
        return float(s) if s else float("nan")
    except Exception:
        return float("nan")


def read_point_shapefile_zip(zip_path: Path) -> tuple[np.ndarray, np.ndarray, list[dict[str, str]]]:
    """Parse an ESRI `Point` (`shape_type=1`) `.shp` + `.dbf` inside `zip_path` using pure stdlib."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        shp_names = [n for n in zf.namelist() if n.lower().endswith(".shp")]
        dbf_names = [n for n in zf.namelist() if n.lower().endswith(".dbf")]
        prj_names = [n for n in zf.namelist() if n.lower().endswith(".prj")]
        if not shp_names or not dbf_names or not prj_names:
            raise ValueError(f"Missing .shp, .dbf, or .prj in {zip_path}")
        shp_bytes = zf.read(shp_names[0])
        dbf_bytes = zf.read(dbf_names[0])
        prj_text = zf.read(prj_names[0]).decode("utf-8", errors="strict")

    try:
        source_epsg = pyproj.CRS.from_wkt(prj_text).to_epsg()
    except Exception as exc:
        raise ValueError(f"Could not parse shapefile projection in {zip_path}: {exc}") from exc
    if source_epsg != 4269:
        raise ValueError(f"Expected shapefile EPSG:4269 (NAD83), got EPSG:{source_epsg} in {zip_path}")

    if len(shp_bytes) < 100:
        raise ValueError(f"Truncated .shp in {zip_path}")
    shape_type = struct.unpack("<i", shp_bytes[32:36])[0]
    if shape_type != 1:
        raise ValueError(f"Expected Point shapefile (shape_type=1), got {shape_type} in {zip_path}")

    nrec, hlen, rlen = struct.unpack("<IHH", dbf_bytes[4:12])
    fields: list[tuple[str, str, int]] = []
    pos = 32
    while pos + 32 <= hlen and dbf_bytes[pos] != 0x0D:
        fname = dbf_bytes[pos : pos + 11].split(b"\x00", 1)[0].decode("latin1").strip()
        ftype = chr(dbf_bytes[pos + 11])
        flen = int(dbf_bytes[pos + 16])
        fields.append((fname, ftype, flen))
        pos += 32

    attrs: list[dict[str, str]] = []
    deleted_flags: list[bool] = []
    p = hlen
    for _ in range(nrec):
        if p + rlen > len(dbf_bytes):
            break
        rec = dbf_bytes[p : p + rlen]
        p += rlen
        deleted_flags.append(rec[0] == 0x2A)
        off = 1
        row: dict[str, str] = {}
        for fname, _, flen in fields:
            row[fname] = rec[off : off + flen].decode("latin1", errors="replace").strip()
            off += flen
        attrs.append(row)

    xs: list[float] = []
    ys: list[float] = []
    sp = 100
    while sp + 8 <= len(shp_bytes):
        _, clen_words = struct.unpack(">II", shp_bytes[sp : sp + 8])
        cbytes = clen_words * 2
        content = shp_bytes[sp + 8 : sp + 8 + cbytes]
        sp += 8 + cbytes
        if len(content) < 4:
            xs.append(float("nan"))
            ys.append(float("nan"))
            continue
        rec_type = struct.unpack("<i", content[:4])[0]
        if rec_type == 1 and len(content) >= 20:
            x, y = struct.unpack("<dd", content[4:20])
            xs.append(float(x))
            ys.append(float(y))
        else:
            xs.append(float("nan"))
            ys.append(float("nan"))

    n = min(len(xs), len(attrs))
    keep_lons: list[float] = []
    keep_lats: list[float] = []
    keep_attrs: list[dict[str, str]] = []
    for i in range(n):
        if not deleted_flags[i] and np.isfinite(xs[i]) and np.isfinite(ys[i]):
            keep_lons.append(xs[i])
            keep_lats.append(ys[i])
            keep_attrs.append(attrs[i])
    return np.asarray(keep_lons, dtype=np.float64), np.asarray(keep_lats, dtype=np.float64), keep_attrs


def _project_points_to_grid(
    lons: np.ndarray,
    lats: np.ndarray,
    transform: rasterio.Affine,
    shape: tuple[int, int],
    src_crs: str = "EPSG:4269",
    dst_crs: str = "EPSG:32611",
    margin_px: int = 24,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project `(lon, lat)` to `(row, col)` on `shape` and return `(rows, cols, keep_mask)`."""
    if lons.size == 0:
        empty_i = np.zeros(0, dtype=np.int32)
        return empty_i, empty_i, np.zeros(0, dtype=bool)
    transformer = pyproj.Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    east, north = transformer.transform(lons, lats)
    rr, cc = rowcol(transform, east, north)
    rr_a = np.asarray(rr, dtype=np.int64)
    cc_a = np.asarray(cc, dtype=np.int64)
    h, w = shape
    keep = (
        np.isfinite(east)
        & np.isfinite(north)
        & (rr_a >= -margin_px)
        & (rr_a < h + margin_px)
        & (cc_a >= -margin_px)
        & (cc_a < w + margin_px)
    )
    rr_c = np.clip(rr_a[keep], 0, h - 1).astype(np.int32)
    cc_c = np.clip(cc_a[keep], 0, w - 1).astype(np.int32)
    return rr_c, cc_c, keep


def _nadaraya_watson_plume(
    shape: tuple[int, int],
    rows: np.ndarray,
    cols: np.ndarray,
    values: np.ndarray,
    sigmas: tuple[float, float] = (4.5, 11.0),
    weights: tuple[float, float] = (0.60, 0.40),
) -> np.ndarray:
    """Density-stabilized multi-scale Nadaraya-Watson anomaly interpolation onto `shape`."""
    num_grid = np.zeros(shape, dtype=np.float32)
    cnt_grid = np.zeros(shape, dtype=np.float32)
    if rows.size > 0:
        np.add.at(num_grid, (rows, cols), values.astype(np.float32))
        np.add.at(cnt_grid, (rows, cols), np.float32(1.0))

    out = np.zeros(shape, dtype=np.float32)
    for sig, wt in zip(sigmas, weights):
        sm_num = gaussian_filter(num_grid, sigma=sig, mode="constant")
        sm_cnt = gaussian_filter(cnt_grid, sigma=sig, mode="constant")
        # Prior pseudo-count prevents single isolated survey edge stations from blowing up
        prior_c = np.float32(1.0 / (2.0 * np.pi * sig * sig) * 0.35)
        plume = sm_num / (sm_cnt + prior_c)
        # Certainty taper so unsampled basins decay smoothly toward zero instead of Step artifacts
        cert = np.clip(sm_cnt / (prior_c * np.float32(2.5)), np.float32(0.0), np.float32(1.0))
        out += np.float32(wt) * plume * cert
        del sm_num, sm_cnt, plume, cert
    del num_grid, cnt_grid
    return out


def _deposit_hydrothermal_weight(dep_type: str) -> float:
    """Weight quaternary/neogene hydrothermal vent deposits; down-weight Lahontan shoreline tufa."""
    s = dep_type.lower().strip()
    if "sinter" in s or "silicif" in s or "geyser" in s:
        return 1.00
    if "silica" in s or "alteration" in s or "opaline" in s or "breccia" in s:
        return 0.85
    if "travertine" in s:
        return 0.80
    if "tufa" in s:
        # IR-32-PALEO-TUFA-01: Pleistocene Lake Lahontan shoreline tufa towers mix fault springs with
        # purely shoreline wave-degassing calcium carbonate; retain partial weight only.
        return 0.35
    return 0.65


def build_trhv_extra_stack(
    ddir: Path,
    base_stack_path: Path,
    spcp_stack_path: Path,
    out_path: Path | None = None,
    verbose: bool = True,
) -> tuple[np.ndarray, dict]:
    """Compute all 8 strictly label-free TRHV channels (`float32`, peak additional RAM < 320 MB)."""

    def log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    tmpl_tif = (ddir / "sample_submission.tif") if (ddir / "sample_submission.tif").exists() else (ddir / "example_submission.tif")
    with rasterio.open(tmpl_tif) as ds:
        ref = ds.read(1)
        transform = ds.transform
    foot = np.isfinite(ref)
    h, w = foot.shape
    del ref

    base = np.load(base_stack_path, mmap_mode="r")
    spcp_s = np.load(spcp_stack_path, mmap_mode="r")
    if base.shape[:2] != (h, w) or spcp_s.shape[:2] != (h, w):
        raise ValueError(f"Stack shape mismatch: base={base.shape}, spcp={spcp_s.shape}, expected {(h, w)}")

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        trhv = open_memmap(out_path, mode="w+", dtype=np.float32, shape=(h, w, len(TRHV_EXTRA_CHANNELS)))
    else:
        trhv = np.zeros((h, w, len(TRHV_EXTRA_CHANNELS)), dtype=np.float32)

    # --- Channels 0..1: UNR/DOE GDR #1391 2-m Temperature Probe Plume & Vertical Gradient ---
    probe_zip = ddir / "external" / "2m_temperature_probe_INGENIOUS_regional_data.zip"
    p_lons, p_lats, p_attrs = read_point_shapefile_zip(probe_zip)
    p_rr, p_cc, p_keep = _project_points_to_grid(p_lons, p_lats, transform, (h, w))
    mapped_idx = np.flatnonzero(p_keep)
    # Do not clip outside-footprint observations onto the raster boundary: doing so would create
    # artificial thermal/vent piles at the edges. The current 2-m probe/paleo products provide
    # their own coverage gaps; only stations truly inside the exact competition footprint enter.
    in_foot_mask = foot[p_rr, p_cc] if p_rr.size > 0 else np.zeros(0, dtype=bool)
    in_foot_probes = int(in_foot_mask.sum())
    kept_idx = mapped_idx[in_foot_mask]
    p_rr, p_cc = p_rr[in_foot_mask], p_cc[in_foot_mask]
    p_lats_kept = p_lats[kept_idx]

    f2m_dab = np.array([_safe_float(p_attrs[i].get("F2mDAB", "")) for i in kept_idx], dtype=np.float32)
    t2m = np.array([_safe_float(p_attrs[i].get("T2m", "")) for i in kept_idx], dtype=np.float32)
    # The GDR shapefile schema stores T15m as a string field (T1.5 m); filter documented outlier typos.
    t15m = np.array([_safe_float(p_attrs[i].get("T15m", "")) for i in kept_idx], dtype=np.float32)

    # Positive depth/albedo-corrected 2-m residual temperature anomaly (clipped cleanly to [0, 25] deg C)
    dab_pos = np.where(np.isfinite(f2m_dab) & (f2m_dab > 1.0), np.clip(f2m_dab, 0.0, 25.0), 0.0).astype(np.float32)
    raw_dab_plume = _nadaraya_watson_plume((h, w), p_rr, p_cc, dab_pos, sigmas=(4.0, 11.0), weights=(0.62, 0.38))
    dab_edge = spcp._grad_mag(raw_dab_plume, sigma=1.8)
    gdr_2m_dab = spcp.robust_unit_f32(
        np.float32(0.72) * raw_dab_plume + np.float32(0.28) * dab_edge, foot, pct=99.5
    )
    del raw_dab_plume, dab_edge
    trhv[:, :, 0] = gdr_2m_dab

    # Sanitized shallow vertical thermal gradient (T2m - T1.5m) + elevation-detrended T2m excess fallback
    valid_pair = (
        np.isfinite(t2m)
        & np.isfinite(t15m)
        & (t2m > 0.5)
        & (t2m <= 105.0)
        & (t15m > 0.5)
        & (t15m <= 105.0)
        & (np.abs(t2m - t15m) <= 20.0)
    )
    n_valid_grad_probes = int(valid_pair.sum())
    d_vert = np.zeros_like(t2m, dtype=np.float32)
    if valid_pair.any():
        med_dt = float(np.median((t2m - t15m)[valid_pair]))
        d_vert[valid_pair] = np.clip((t2m[valid_pair] - t15m[valid_pair]) - np.float32(med_dt), 0.0, 8.0)

    # Supplement stations lacking T1.5m with elevation-residualized T2m excess
    det_elev = np.asarray(base[:, :, 11], dtype=np.float32)
    valid_t2 = np.isfinite(t2m) & (t2m > 0.5) & (t2m <= 105.0)
    if valid_t2.sum() > 20:
        el_pts = det_elev[p_rr[valid_t2], p_cc[valid_t2]].astype(np.float64)
        lat_pts = p_lats_kept[valid_t2].astype(np.float64)
        X_t = np.column_stack([np.ones(el_pts.size), el_pts, lat_pts - lat_pts.mean()])
        beta_t, *_ = np.linalg.lstsq(X_t, t2m[valid_t2].astype(np.float64), rcond=None)
        t2_res = np.zeros_like(t2m, dtype=np.float32)
        t2_res[valid_t2] = np.clip(
            t2m[valid_t2] - (X_t @ beta_t).astype(np.float32), 0.0, 20.0
        ) * np.float32(0.25)
        vert_anom = np.where(valid_pair, d_vert + np.float32(0.35) * t2_res, t2_res)
        del X_t, t2_res
    else:
        vert_anom = d_vert
    del det_elev, f2m_dab, t2m, t15m, valid_pair, valid_t2, d_vert

    raw_vert_plume = _nadaraya_watson_plume(
        (h, w), p_rr, p_cc, vert_anom, sigmas=(4.5, 10.5), weights=(0.65, 0.35)
    )
    gdr_2m_vert = spcp.robust_unit_f32(
        np.float32(0.68) * raw_vert_plume + np.float32(0.32) * spcp._grad_mag(raw_vert_plume, sigma=1.8),
        foot,
        pct=99.5,
    )
    del raw_vert_plume, vert_anom, p_lons, p_lats, p_lats_kept, p_attrs, p_rr, p_cc, p_keep, kept_idx
    trhv[:, :, 1] = gdr_2m_vert
    gc.collect()
    log(f"  [TRHV] ch 0..1 (2-m thermal probes: {in_foot_probes} in-footprint, {n_valid_grad_probes} T2m-T1.5m pairs) built")

    # --- Channel 2: Paleo-Geothermal Sinter / Travertine / Silicified Vent Kernel ---
    paleo_zip = ddir / "external" / "paleo_geothermal_regional.zip"
    v_lons, v_lats, v_attrs = read_point_shapefile_zip(paleo_zip)
    v_rr, v_cc, v_keep = _project_points_to_grid(v_lons, v_lats, transform, (h, w))
    v_mapped_idx = np.flatnonzero(v_keep)
    v_in_foot = foot[v_rr, v_cc] if v_rr.size > 0 else np.zeros(0, dtype=bool)
    in_foot_paleo = int(v_in_foot.sum())
    v_kept_idx = v_mapped_idx[v_in_foot]
    v_rr, v_cc = v_rr[v_in_foot], v_cc[v_in_foot]

    v_wts = np.array(
        [_deposit_hydrothermal_weight(v_attrs[i].get("Deposit_ty", "")) for i in v_kept_idx],
        dtype=np.float32,
    )
    vent_grid = np.zeros((h, w), dtype=np.float32)
    if v_rr.size > 0:
        np.add.at(vent_grid, (v_rr, v_cc), v_wts)
    # Multi-scale anisotropic/isotropic hydrothermal vent corridor (450 m vent core + 1.2 km damage halo)
    vent_s4 = gaussian_filter(vent_grid, sigma=4.5, mode="constant")
    vent_s12 = gaussian_filter(vent_grid, sigma=12.0, mode="constant")
    del vent_grid, v_lons, v_lats, v_attrs, v_rr, v_cc, v_keep, v_wts, v_kept_idx, v_mapped_idx, v_in_foot
    gdr_paleo_vent = spcp.robust_unit_f32(
        np.float32(0.62) * np.log1p(vent_s4 * np.float32(35.0))
        + np.float32(0.38) * np.log1p(vent_s12 * np.float32(120.0)),
        foot,
        pct=99.6,
    )
    del vent_s4, vent_s12
    trhv[:, :, 2] = gdr_paleo_vent
    gc.collect()
    log(f"  [TRHV] ch 2 (paleo-geothermal sinter/travertine vents: {in_foot_paleo} in-footprint) built")

    # --- Channel 3: Subsurface-Coupled Hydrothermal Vent Conduit Index ---
    pf_concord = np.asarray(spcp_s[:, :, 4], dtype=np.float32)
    grav_saddle = np.asarray(spcp_s[:, :, 5], dtype=np.float32)
    mag_demag = np.asarray(spcp_s[:, :, 7], dtype=np.float32)
    mt_edge = np.asarray(spcp_s[:, :, 9], dtype=np.float32)
    gdr_reg = np.asarray(spcp_s[:, :, 10], dtype=np.float32)

    thermal_vent_union = np.clip(
        np.float32(0.46) * gdr_2m_dab
        + np.float32(0.18) * gdr_2m_vert
        + np.float32(0.36) * gdr_paleo_vent
        + np.float32(0.22) * gdr_reg,
        0.0,
        1.25,
    )
    conduit_struct = (
        np.float32(0.38) * pf_concord
        + np.float32(0.24) * mag_demag
        + np.float32(0.20) * mt_edge
        + np.float32(0.18) * grav_saddle
    )
    # Require BOTH thermal/vent expression AND subsurface geophysical structure to reject lateral outflow plumes!
    vent_conduit = spcp.robust_unit_f32(
        mdrc.directional_chain_max(
            conduit_struct * (np.float32(0.25) + np.float32(0.75) * thermal_vent_union),
            foot,
            halflen=2,
        ),
        foot,
        pct=99.5,
    )
    del gdr_2m_dab, gdr_2m_vert, gdr_paleo_vent, grav_saddle, mag_demag, mt_edge, gdr_reg, thermal_vent_union, conduit_struct
    trhv[:, :, 3] = vent_conduit
    gc.collect()

    # --- Channels 4..5: Census TIGER 2024 Road-Prism Veto & Doubly De-Confounded 1m LiDAR Scarp ---
    tiger_path = ddir / "external" / "tiger_road_distance_m.tif"
    with rasterio.open(tiger_path) as ds:
        d_road = ds.read(1).astype(np.float32)
    d_road = np.where(np.isfinite(d_road) & (d_road >= 0.0), d_road, np.float32(1000.0))
    # Smooth Gaussian notch at the preregistered ~150 m scale around mapped road/rail centerlines.
    tiger_gate = np.where(
        foot,
        np.float32(1.0) - np.exp(-((d_road / np.float32(150.0)) ** 2)).astype(np.float32),
        np.float32(0.0),
    )
    del d_road
    trhv[:, :, 4] = tiger_gate

    lidar_dipole = np.asarray(spcp_s[:, :, 13], dtype=np.float32)
    lahontan_orthog = np.asarray(spcp_s[:, :, 14], dtype=np.float32)
    # Doubly de-confounded scarp: suppresses BOTH road cut/fill prisms AND Lake Lahontan beach contours
    clean_scarp_raw = (
        lidar_dipole
        * (np.float32(0.15) + np.float32(0.85) * tiger_gate)
        * (np.float32(0.28) + np.float32(0.72) * lahontan_orthog)
    )
    del lidar_dipole, lahontan_orthog
    lidar_clean = spcp.robust_unit_f32(
        mdrc.directional_chain_max(clean_scarp_raw, foot, halflen=2),
        foot,
        pct=99.4,
    )
    del clean_scarp_raw
    trhv[:, :, 5] = lidar_clean
    gc.collect()

    # --- Channels 6..7: Strike-Chained Upward-150m Magnetic Contact & Strain-Obliquity Coupling ---
    up150_pers = np.asarray(spcp_s[:, :, 18], dtype=np.float32)
    mag_persist = spcp.robust_unit_f32(
        mdrc.directional_chain_max(
            up150_pers
            * np.sqrt(np.maximum(pf_concord, np.float32(0.02)))
            * (np.float32(0.40) + np.float32(0.60) * tiger_gate),
            foot,
            halflen=3,
        ),
        foot,
        pct=99.5,
    )
    del up150_pers, tiger_gate
    trhv[:, :, 6] = mag_persist
    del mag_persist

    grav_s12 = np.asarray(spcp_s[:, :, 0], dtype=np.float32)
    hydro_breach = np.asarray(spcp_s[:, :, 11], dtype=np.float32)
    transtens = np.asarray(spcp_s[:, :, 17], dtype=np.float32)
    strain_pf = spcp.robust_unit_f32(
        (np.float32(0.55) * pf_concord + np.float32(0.45) * grav_s12)
        * (np.float32(0.45) + np.float32(0.55) * transtens)
        * (np.float32(0.50) + np.float32(0.50) * np.maximum(hydro_breach, vent_conduit)),
        foot,
        pct=99.5,
    )
    del pf_concord, grav_s12, hydro_breach, transtens, vent_conduit
    trhv[:, :, 7] = strain_pf
    del strain_pf

    if hasattr(trhv, "flush"):
        trhv.flush()
    gc.collect()
    log("  [TRHV] ch 3..7 (vent-conduit coupling + TIGER road veto + mag_up150 + strain-PF) built")

    receipt = {
        "n_trhv_channels": len(TRHV_EXTRA_CHANNELS),
        "channel_names": list(TRHV_EXTRA_CHANNELS),
        "shape": [h, w, len(TRHV_EXTRA_CHANNELS)],
        "in_footprint_2m_probes": in_foot_probes,
        "valid_t2m_t15m_gradient_probes": n_valid_grad_probes,
        "in_footprint_paleo_vents": in_foot_paleo,
    }
    return trhv, receipt


def run_leakage_canary_63ch(
    base_stack: np.ndarray,
    spcp_stack: np.ndarray,
    trhv_stack: np.ndarray,
    base_names: list[str],
    ctx,
    max_auc: float = 0.90,
    stride: int = 4,
) -> dict:
    """Protocol Rule 4 single-feature two-polarity leakage canary across all 63 channels."""
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

    n_b = base_stack.shape[2]
    n_s = spcp_stack.shape[2]
    all_names = list(base_names) + list(spcp.SPCP_EXTRA_CHANNELS) + list(TRHV_EXTRA_CHANNELS)

    rows = []
    for i, name in enumerate(all_names):
        if i < n_b:
            plane = base_stack[:, :, i]
        elif i < n_b + n_s:
            plane = spcp_stack[:, :, i - n_b]
        else:
            plane = trhv_stack[:, :, i - n_b - n_s]
        vals = np.concatenate([plane[py, px], plane[ny, nx]]).astype(np.float64)
        vals = np.nan_to_num(vals, nan=0.0, posinf=0.0, neginf=0.0)
        if np.ptp(vals) <= 1e-12:
            auc_dir = 0.5
        else:
            raw_auc = float(roc_auc_score(y_true, vals))
            auc_dir = max(raw_auc, 1.0 - raw_auc)
        rows.append({"channel": name, "oriented_auc": round(auc_dir, 6), "passed": bool(auc_dir <= max_auc)})

    worst = max(rows, key=lambda r: r["oriented_auc"])
    return {
        "passed": all(r["passed"] for r in rows),
        "threshold_auc": max_auc,
        "n_features_tested": len(rows),
        "max_oriented_auc": worst["oriented_auc"],
        "worst_channel": worst["channel"],
        "n_withheld_pos_tested": int(py.size),
        "n_active_neg_sampled": int(ny.size),
        "per_channel": rows,
    }


def _gather_63ch(
    base_stack: np.ndarray,
    spcp_stack: np.ndarray,
    trhv_stack: np.ndarray,
    ys: np.ndarray,
    xs: np.ndarray,
) -> np.ndarray:
    xb = np.asarray(base_stack[ys, xs, :], dtype=np.float32)
    xs_arr = np.asarray(spcp_stack[ys, xs, :], dtype=np.float32)
    xt = np.asarray(trhv_stack[ys, xs, :], dtype=np.float32)
    return np.hstack([xb, xs_arr, xt])


def _predict_chunked_63ch(
    clf: HistGradientBoostingClassifier,
    base_stack: np.ndarray,
    spcp_stack: np.ndarray,
    trhv_stack: np.ndarray,
    mask: np.ndarray,
    chunk_size: int = 200_000,
) -> np.ndarray:
    out = np.zeros(mask.shape, dtype=np.float32)
    ys, xs = np.nonzero(mask)
    for start in range(0, ys.size, chunk_size):
        sl = slice(start, min(start + chunk_size, ys.size))
        X = _gather_63ch(base_stack, spcp_stack, trhv_stack, ys[sl], xs[sl])
        out[ys[sl], xs[sl]] = clf.predict_proba(X)[:, 1].astype(np.float32)
        del X
    return out


def visible_tip_stepover_cone(visible: np.ndarray, foot: np.ndarray) -> np.ndarray:
    """Strictly fold-visible fault-tip & relay-stepover stress field (`P_tip(visible)`).

    Uses ONLY `visible` catalogue pixels (`cell.visible_full` on OOF folds; `labels.tif` on live map).
    Zero withheld fault pixels ever enter.
    """
    vis = np.asarray(visible, bool) & foot
    if not vis.any():
        return np.zeros(foot.shape, dtype=np.float32)
    from scipy.ndimage import convolve

    nb = convolve(vis.astype(np.int16), np.ones((3, 3), dtype=np.int16), mode="constant") - vis.astype(np.int16)
    tips = vis & (nb >= 1) & (nb <= 2)
    del nb

    d_tips = distance_transform_edt(~tips)
    d_vis = distance_transform_edt(~vis)
    vis_blur = gaussian_filter(vis.astype(np.float32), sigma=2.5, mode="constant")

    outside = d_vis > 2.0
    tip_cone = np.exp(-((d_tips - 5.0) ** 2) / (2.0 * 7.0 * 7.0)).astype(np.float32) * outside
    relay_halo = np.exp(-((d_vis - 4.5) ** 2) / (2.0 * 4.5 * 4.5)).astype(np.float32) * outside
    stepover = np.clip(vis_blur * 14.0, 0.0, 1.5).astype(np.float32) * outside
    del d_tips, d_vis, vis_blur, outside
    out = (np.float32(0.55) * tip_cone + np.float32(0.25) * relay_halo + np.float32(0.20) * stepover) * foot
    return out.astype(np.float32)


def fit_predict_exposed63(
    base_stack: np.ndarray,
    spcp_stack: np.ndarray,
    trhv_stack: np.ndarray,
    train_region: np.ndarray,
    visible_train: np.ndarray,
    visible_context: np.ndarray,
    predict_region: np.ndarray,
    foot: np.ndarray,
    seed: int = 45,
    max_pos: int = 42_000,
    n_neg_hard: int = 84_000,
    n_neg_unif: int = 84_000,
    tip_weight: float = 0.35,
) -> np.ndarray:
    """Regime A (`EXP1_H46_EXPOSED63`): fold-local hard-negative 63-ch HistGB + visible tip/relay cones."""
    rng = np.random.default_rng(seed)
    tr_pos = train_region & visible_train
    d_tr = distance_transform_edt(~tr_pos)

    pos_y, pos_x = np.nonzero(tr_pos)
    if pos_y.size > max_pos:
        pp = rng.choice(pos_y.size, size=max_pos, replace=False)
        pos_y, pos_x = pos_y[pp], pos_x[pp]

    hard_y, hard_x = np.nonzero(train_region & (~visible_train) & (d_tr >= 5.0) & (d_tr <= 24.0))
    unif_y, unif_x = np.nonzero(train_region & (~visible_train) & (d_tr > 24.0))
    del d_tr

    nh = min(n_neg_hard, hard_y.size)
    nu = min(n_neg_unif, unif_y.size)
    ph = rng.choice(hard_y.size, size=nh, replace=False)
    pu = rng.choice(unif_y.size, size=nu, replace=False)

    ys = np.concatenate([pos_y, hard_y[ph], unif_y[pu]])
    xs = np.concatenate([pos_x, hard_x[ph], unif_x[pu]])
    y = np.concatenate([np.ones(pos_y.size, dtype=np.int8), np.zeros(nh + nu, dtype=np.int8)])
    del pos_y, pos_x, hard_y, hard_x, unif_y, unif_x

    order = np.argsort(ys * foot.shape[1] + xs)
    ys, xs, y = ys[order], xs[order], y[order]

    X = _gather_63ch(base_stack, spcp_stack, trhv_stack, ys, xs)
    clf = HistGradientBoostingClassifier(
        max_iter=165,
        learning_rate=0.055,
        max_leaf_nodes=47,
        min_samples_leaf=80,
        l2_regularization=2.5,
        early_stopping=False,
        random_state=seed,
    )
    clf.fit(X, y)
    del X, y, ys, xs

    prob = _predict_chunked_63ch(clf, base_stack, spcp_stack, trhv_stack, predict_region)
    del clf
    if tip_weight > 0.0:
        ptip = visible_tip_stepover_cone(visible_context, foot)
        prob[predict_region] = prob[predict_region] * (np.float32(1.0) + np.float32(tip_weight) * ptip[predict_region])
        del ptip
    return prob


def fit_predict_vent_sarpu63(
    base_stack: np.ndarray,
    spcp_stack: np.ndarray,
    trhv_stack: np.ndarray,
    train_region: np.ndarray,
    visible_train: np.ndarray,
    predict_region: np.ndarray,
    seed: int = 45,
    neg_halo_px: float = 5.0,
    max_pos: int = 40_000,
    neg_ratio: int = 4,
) -> np.ndarray:
    """Regime B (`EXP2_H46_VENT_SARPU63`): fold-local 63-ch Vent-Coupled SAR-PU blind-basin transfer."""
    rng = np.random.default_rng(seed)
    near_vis = binary_dilation(visible_train, structure=spcp._disk_mask(neg_halo_px))
    pos_y, pos_x = np.nonzero(train_region & visible_train)
    bg_y, bg_x = np.nonzero(train_region & ~near_vis)
    del near_vis

    if pos_y.size > max_pos:
        pp = rng.choice(pos_y.size, size=max_pos, replace=False)
        pos_y, pos_x = pos_y[pp], pos_x[pp]

    def _obs_cols(ys: np.ndarray, xs: np.ndarray) -> np.ndarray:
        b_o = np.asarray(base_stack[ys, xs][:, OBS_BASE_IDX], dtype=np.float32)
        s_o = np.asarray(spcp_stack[ys, xs][:, OBS_SPCP_IDX], dtype=np.float32)
        t_o = np.asarray(trhv_stack[ys, xs][:, OBS_TRHV_IDX], dtype=np.float32)
        return np.hstack([b_o, s_o, t_o])

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

    # Label-free physical + hydrothermal-vent conduit composite for reliable-negative screening & transfer
    spcp_unsup = spcp_stack[:, :, 19]
    vent_cond = trhv_stack[:, :, 3]
    mag_pers = trhv_stack[:, :, 6]

    ty_s, tx_s = bg_y[pb], bg_x[pb]
    u_samp = (
        np.float32(0.50) * np.asarray(spcp_unsup[ty_s, tx_s], dtype=np.float32)
        + np.float32(0.32) * np.asarray(vent_cond[ty_s, tx_s], dtype=np.float32)
        + np.float32(0.18) * np.asarray(mag_pers[ty_s, tx_s], dtype=np.float32)
    )
    unsup_q90 = float(np.percentile(u_samp, 90.0))
    del u_samp

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
    u_cand = (
        np.float32(0.50) * np.asarray(spcp_unsup[cand_ny, cand_nx], dtype=np.float32)
        + np.float32(0.32) * np.asarray(vent_cond[cand_ny, cand_nx], dtype=np.float32)
        + np.float32(0.18) * np.asarray(mag_pers[cand_ny, cand_nx], dtype=np.float32)
    )
    # Protect low-observability piedmont/basin hydrothermal-vent & PF conduits from false-negative labeling
    reliable = ~((e_cand < 0.50) & (u_cand >= unsup_q90))
    if int(reliable.sum()) >= pos_y.size:
        cand_ny, cand_nx = cand_ny[reliable], cand_nx[reliable]
    n_neg = min(cand_ny.size, pos_y.size * neg_ratio)
    cand_ny, cand_nx = cand_ny[:n_neg], cand_nx[:n_neg]
    del e_cand, u_cand

    w_pos = np.clip((e_pos + 0.10) ** (-0.65), 0.55, 4.25).astype(np.float32)
    w_pos *= float(pos_y.size) / float(w_pos.sum())
    w_neg = np.ones(n_neg, dtype=np.float32)

    ys = np.concatenate([pos_y, cand_ny])
    xs = np.concatenate([pos_x, cand_nx])
    y_fit = np.concatenate([np.ones(pos_y.size, dtype=np.int32), np.zeros(n_neg, dtype=np.int32)])
    w_fit = np.concatenate([w_pos, w_neg])

    order = np.argsort(ys * train_region.shape[1] + xs)
    ys, xs, y_fit, w_fit = ys[order], xs[order], y_fit[order], w_fit[order]

    X_fit = _gather_63ch(base_stack, spcp_stack, trhv_stack, ys, xs)
    det_clf = HistGradientBoostingClassifier(
        max_iter=175,
        learning_rate=0.05,
        max_leaf_nodes=31,
        min_samples_leaf=80,
        l2_regularization=3.0,
        early_stopping=False,
        random_state=seed + 100,
    )
    det_clf.fit(X_fit, y_fit, sample_weight=w_fit)
    del X_fit, y_fit, w_fit, ys, xs

    raw_prob = _predict_chunked_63ch(det_clf, base_stack, spcp_stack, trhv_stack, predict_region)
    del det_clf

    py, px = np.nonzero(predict_region)
    e_pred = np.zeros(predict_region.shape, dtype=np.float32)
    for start in range(0, py.size, 250_000):
        sl = slice(start, min(start + 250_000, py.size))
        e_pred[py[sl], px[sl]] = _norm_e(
            prop_clf.predict_proba(_obs_cols(py[sl], px[sl]))[:, 1].astype(np.float32)
        )
    del prop_clf

    p_sarpu = np.zeros(predict_region.shape, dtype=np.float32)
    p_sarpu[predict_region] = np.clip(
        raw_prob[predict_region] / ((e_pred[predict_region] + np.float32(0.18)) ** np.float32(0.38)),
        0.0,
        1.0,
    )
    del raw_prob

    phys_prior = np.zeros(predict_region.shape, dtype=np.float32)
    phys_prior[py, px] = (
        np.float32(0.50) * np.asarray(spcp_unsup[py, px], dtype=np.float32)
        + np.float32(0.32) * np.asarray(vent_cond[py, px], dtype=np.float32)
        + np.float32(0.18) * np.asarray(mag_pers[py, px], dtype=np.float32)
    )
    p_rank = spcp._rank_unit_f32(p_sarpu, predict_region)
    r_rank = spcp._rank_unit_f32(phys_prior, predict_region)
    del p_sarpu, phys_prior
    lam = np.where(predict_region, np.float32(0.24) + np.float32(0.36) * (np.float32(1.0) - e_pred), np.float32(0.0))
    del e_pred

    blended = np.where(
        predict_region,
        (np.maximum(p_rank, np.float32(1e-5)) ** (np.float32(1.0) - lam))
        * (np.maximum(r_rank, np.float32(1e-5)) ** lam),
        np.float32(0.0),
    ).astype(np.float32)
    del p_rank, r_rank, lam
    return blended


def build_two_regime_belief_surface(
    surface_a: np.ndarray,
    surface_b: np.ndarray,
    burial_prior: np.ndarray,
    vent_conduit: np.ndarray,
    mask: np.ndarray,
) -> np.ndarray:
    """Continuous unified pre-placement belief surface for Protocol Rule 1 Spearman registry check."""
    ra = spcp._rank_unit_f32(surface_a, mask)
    rb = spcp._rank_unit_f32(surface_b, mask)
    gate_b = np.clip(
        np.float32(0.55) * np.asarray(burial_prior, dtype=np.float32)
        + np.float32(0.45) * np.asarray(vent_conduit, dtype=np.float32),
        0.0,
        1.0,
    )
    w_b = np.float32(0.22) + np.float32(0.28) * gate_b
    surf = np.where(mask, (np.float32(1.0) - w_b) * ra + w_b * rb, np.float32(0.0)).astype(np.float32)
    del ra, rb, gate_b, w_b
    return surf


def emit_two_regime_trhv(
    surface_a: np.ndarray,
    surface_b: np.ndarray,
    burial_prior: np.ndarray,
    vent_conduit: np.ndarray,
    eligible_mask: np.ndarray,
    foot: np.ndarray,
    budget: int,
    frac_a: float = 0.70,
    support_mult: int = 5,
) -> tuple[np.ndarray, dict]:
    """Sequential residual-coverage Two-Regime CELF allocation (`EXP3_H46_TRHV_TWOREGIME`).

    Stage 1 packs `K_A = round(frac_a * budget)` dots on Regime A crests (`surface_a`).
    Stage 2 packs the remaining `K_B = budget - K_A` dots on cover/vent-weighted Regime B crests
    using `emitter.emit(..., initial_mask=dots_a)`, guaranteeing zero redundant 300 m kernel overlap
    with Stage 1 while dedicating `(1 - frac_a)` of budget to blind-basin & hydrothermal-vent conduits.
    """
    if budget <= 0 or not (eligible_mask & foot).any():
        return np.zeros(surface_a.shape, dtype=bool), {"stage1_dots": 0, "stage2_added_dots": 0, "total_dots": 0}

    budget_a = max(1, min(budget, int(round(frac_a * budget))))
    dots_a, _ = spcp.emit_crest_submodular(
        surface_a, eligible_mask, foot, budget=budget_a, support_mult=support_mult
    )
    n_a = int(dots_a.sum())
    if n_a >= budget:
        return dots_a, {"stage1_dots": n_a, "stage2_added_dots": 0, "total_dots": n_a}

    # Weight Regime B toward sedimentary basins (`burial_prior`) and hydrothermal-vent conduits (`vent_conduit`)
    b_boost = np.float32(0.40) + np.float32(0.60) * np.clip(
        np.float32(0.55) * np.asarray(burial_prior, dtype=np.float32)
        + np.float32(0.45) * np.asarray(vent_conduit, dtype=np.float32),
        0.0,
        1.0,
    )
    surf_b_weighted = (surface_b * b_boost).astype(np.float32)
    del b_boost
    crest_b = mdrc.sharpen_ridge_crest(surf_b_weighted, foot)
    del surf_b_weighted

    elig_b = eligible_mask & foot & (~dots_a) & (crest_b > 0)
    n_elig_b = int(elig_b.sum())
    if n_elig_b == 0:
        return dots_a, {"stage1_dots": n_a, "stage2_added_dots": 0, "total_dots": n_a}

    rem_budget = budget - n_a
    max_sup_b = max(rem_budget * (support_mult + 1), min(n_elig_b, 25_000))
    if n_elig_b > max_sup_b:
        vals = crest_b[elig_b]
        thr = float(np.partition(vals, n_elig_b - max_sup_b)[n_elig_b - max_sup_b])
        sup_b = elig_b & (crest_b >= thr)
    else:
        sup_b = elig_b

    field_b = np.where(sup_b, crest_b, 0.0).astype(np.float64)
    del crest_b, elig_b, sup_b
    dots_b_new, _ = emitter.emit(
        field_b,
        budget=int(rem_budget),
        prior_dti=0.0,
        gain_floor=0.0,
        initial_mask=dots_a,
    )
    del field_b
    assert not bool((dots_a & dots_b_new).any()), "Stage-2 dots must be strictly disjoint from Stage-1 dots"
    dots_ab = dots_a | dots_b_new
    n_b = int(dots_b_new.sum())
    n_tot = int(dots_ab.sum())
    assert int((dots_ab & dots_a).sum()) == n_a
    return dots_ab, {
        "stage1_dots": n_a,
        "stage2_added_dots": n_b,
        "total_dots": n_tot,
    }
