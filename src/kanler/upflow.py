"""Lane H-K1-B (GEOALIGN-UPFLOW): anisotropic geothermal-alignment channels.

Pre-registration: docs/research/hypotheses-upflow-20261028.md (H-K1B-1..H-K1B-3).

Thesis: OCDA consumed geothermal point data only as *isotropic gaussian halos*.
Faults are *linear* permeability structures, so this lane builds *strike-projected
anisotropic corridors* (hot springs, sinter/travertine, vents, QFaults) intersected
with potential-field edges, plus *thermal-plume-margin* gradient ridges (not blob
centers).  Every channel is label-free; NOTHING reads ``dist_known_fault_px``
(full-catalogue derived).  Catalogue interactions are per-fold from
``cell.visible_full`` only (see :func:`compute_fold_visible_upflow`).

Memory discipline: 3 GB box.  The (12, H, W) stack is disk-backed (memmap);
temporaries are float32 and freed aggressively.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import struct
import sys
import zipfile
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from gems32 import hypotheses as shared_hyp  # noqa: E402
from gems32 import features as shared_features  # noqa: E402

UPFLOW_SCHEMA_VERSION = "kanler1-upflow-geoalign-v1"

UPFLOW_FREE_NAMES = [
    "upflow_spring_hot_idw",      # 0 IDW excess-T field of T>=32C springs/wells
    "upflow_spring_hot_density",  # 1 gaussian density of hot-spring points
    "upflow_quartz_geotherm_idw",  # 2 IDW quartz-geothermometer excess (>=90C)
    "upflow_probe_dab_idw",       # 3 IDW 2m-probe F2mDAB excess
    "upflow_thermal_grad_ridge",  # 4 NMS crest of thermal-gradient magnitude (plume margins)
    "upflow_spring_corridor",     # 5 strike-projected hot-spring segments
    "upflow_sinter_corridor",     # 6 strike-projected paleo-deposit segments
    "upflow_vent_corridor",       # 7 vent strike projections + pairwise alignment links
    "upflow_qfault_corridor",     # 8 slip-rate-weighted QFaults oriented corridors
    "upflow_edge_concord",        # 9 max potential-field edge (tmi/rtp/grav/cond)
    "upflow_align_edge_inter",    # 10 corridor x edge intersection (key signature)
    "upflow_road_damp",           # 11 TIGER road-corridor damping multiplier
]

N_UPFLOW_FREE = len(UPFLOW_FREE_NAMES)

# Fixed, pre-registered, untuned priors (NOT tuned on holdout blocks).
IDW_K = 12
IDW_P = 2.0
IDW_MAX_DIST_PX = 50.0
REGIONAL_STRIKE_DYDX = (-0.9848, 0.1736)  # N10E in (row-down, col-right): Basin-and-Range
EXP1_W = (0.45, 0.25, 0.15, 0.15)  # (align_edge_inter, thermal_ridge, spring_idw, probe_idw)

__all__ = [
    "UPFLOW_SCHEMA_VERSION", "UPFLOW_FREE_NAMES", "N_UPFLOW_FREE",
    "build_or_load_upflow_stack", "compute_fold_visible_upflow",
    "build_alignment_surface", "upflow_stack_receipt",
]


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _robust_unit(a: np.ndarray, foot: np.ndarray, p_hi: float = 99.5) -> np.ndarray:
    v = np.asarray(a, dtype=np.float32)
    f = v[foot] if foot.any() else v.ravel()[:1]
    f = f[np.isfinite(f)]
    if f.size == 0:
        return np.zeros(v.shape, dtype=np.float32)
    lo = float(np.percentile(f, 0.5))
    hi = float(np.percentile(f, p_hi))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros(v.shape, dtype=np.float32)
    out = np.clip((v - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)
    return np.where(foot, out, 0.0).astype(np.float32)


def _parse_probes(ddir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """2m probe lon/lat (NAD83) + F2mDAB excess. Zone-agnostic (no raw UTM affine)."""
    with zipfile.ZipFile(ddir / "external" / "2m_temperature_probe_INGENIOUS_regional_data.zip") as zf:
        dbf = zf.read("2m_temperature_probe_INGENIOUS_regional_data/2m_temperature_probe_n83geo/"
                      "2m_temperature_probe_n83geo.dbf")
    _, _, _, _, nrec, hlen, rlen = struct.unpack("<BBBBIHH", dbf[:12])
    fields: list[tuple[str, int]] = []
    pos = 32
    while dbf[pos] != 0x0D:
        fields.append((dbf[pos:pos + 11].split(b"\x00")[0].decode("latin1"), dbf[pos + 16]))
        pos += 32
    lons, lats, vals = [], [], []
    for i in range(nrec):
        base = hlen + i * rlen
        if base + rlen > len(dbf) or dbf[base] == 0x2A:
            continue
        off = base + 1
        rec: dict[str, str] = {}
        for fname, flen in fields:
            if fname in ("F2mDAB", "LatDegreeN", "LongDegree"):
                rec[fname] = dbf[off:off + flen].decode("latin1", "ignore").strip()
            off += flen
        try:
            lon = float(rec["LongDegree"])
            lat = float(rec["LatDegreeN"])
            dab = float(rec.get("F2mDAB") or "nan")
        except (KeyError, ValueError):
            continue
        if np.isfinite(lon) and np.isfinite(lat) and np.isfinite(dab):
            lons.append(lon)
            lats.append(lat)
            vals.append(float(np.clip(dab, 0.0, 25.0)))
    return np.asarray(lons), np.asarray(lats), np.asarray(vals, dtype=np.float32)


def _parse_wellspring(ddir: Path):
    """Row/col + temp_c + quartz geothermometer. NEVER reads dist_known_fault_px."""
    rows_y, rows_x, temps, qtz = [], [], [], []
    with (ddir / "external" / "gdr_wellspring_in_footprint.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                r = int(float(row["row"]))
                c = int(float(row["col"]))
            except (KeyError, TypeError, ValueError):
                continue
            t = np.nan
            q = np.nan
            try:
                if row.get("temp_c"):
                    t = float(row["temp_c"])
            except ValueError:
                pass
            try:
                if row.get("geothermquartz_c"):
                    q = float(row["geothermquartz_c"])
            except ValueError:
                pass
            rows_y.append(r)
            rows_x.append(c)
            temps.append(t)
            qtz.append(q)
    return (np.asarray(rows_y, dtype=np.int32), np.asarray(rows_x, dtype=np.int32),
            np.asarray(temps, dtype=np.float32), np.asarray(qtz, dtype=np.float32))


def _parse_paleo(ddir: Path):
    with zipfile.ZipFile(ddir / "external" / "paleo_geothermal_regional.zip") as zf:
        raw = zf.read("Paleo_geothermal_final.csv").decode("utf-8", "replace")
    lons, lats, wts, half = [], [], [], []
    for rec in csv.DictReader(io.StringIO(raw)):
        try:
            lon = float(rec["Long_deg_NAD83"])
            lat = float(rec["Lat_deg_NAD83"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (np.isfinite(lon) and np.isfinite(lat)):
            continue
        dt = str(rec.get("Deposit_type", "")).lower()
        if "sinter" in dt or "silic" in dt:
            w, h = 2.5, 15.0
        elif "travertine" in dt:
            w, h = 1.6, 10.0
        elif "tufa" in dt:
            w, h = 0.8, 8.0
        elif "crater" in dt or "sulfur" in dt or "alteration" in dt:
            w, h = 1.2, 8.0
        else:
            w, h = 1.0, 6.0
        lons.append(lon)
        lats.append(lat)
        wts.append(w)
        half.append(h)
    return (np.asarray(lons), np.asarray(lats),
            np.asarray(wts, dtype=np.float32), np.asarray(half, dtype=np.float32))


def _parse_vents(ddir: Path):
    rows_y, rows_x = [], []
    with (ddir / "external" / "gdr_volcanic_vents_in_footprint.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                rows_y.append(int(float(row["row"])))
                rows_x.append(int(float(row["col"])))
            except (KeyError, TypeError, ValueError):
                continue
    return np.asarray(rows_y, dtype=np.int32), np.asarray(rows_x, dtype=np.int32)


def _parse_qfaults(ddir: Path):
    rows_y, rows_x, wts, half, sdy, sdx = [], [], [], [], [], []
    # dip direction -> strike unit vector (row-down, col-right); strike ⊥ dip.
    dip2strike = {
        "E": (1.0, 0.0), "W": (1.0, 0.0), "N": (0.0, 1.0), "S": (0.0, 1.0),
        "NE": (1.0, -1.0), "SW": (1.0, -1.0), "NW": (1.0, 1.0), "SE": (1.0, 1.0),
    }
    recency_gain = {"<150": 1.5, "<15,000": 1.25, "<130,000": 1.1, "<750,000": 1.05}
    with (ddir / "external" / "gdr_qfaults_traces.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("centroid_in_footprint") != "1":
                continue
            try:
                r = int(float(row["centroid_row"]))
                c = int(float(row["centroid_col"]))
                sr = float(row.get("slip_rate") or 0.1)
                ln = float(row.get("clipped_length_m") or 0.0)
            except (KeyError, TypeError, ValueError):
                continue
            sv = dip2strike.get(str(row.get("dip_direct", "")).strip(), None)
            if sv is None:
                sv = REGIONAL_STRIKE_DYDX
            n = float(np.hypot(sv[0], sv[1])) or 1.0
            g = recency_gain.get(str(row.get("recency", "")).strip(), 1.0)
            rows_y.append(r)
            rows_x.append(c)
            wts.append(float(np.clip(sr, 0.02, 2.0)) * g)
            half.append(float(np.clip(ln / 200.0, 5.0, 25.0)))
            sdy.append(sv[0] / n)
            sdx.append(sv[1] / n)
    return (np.asarray(rows_y, dtype=np.int32), np.asarray(rows_x, dtype=np.int32),
            np.asarray(wts, dtype=np.float32), np.asarray(half, dtype=np.float32),
            np.asarray(sdy, dtype=np.float32), np.asarray(sdx, dtype=np.float32))


def _lonlat_to_rowcol(lons: np.ndarray, lats: np.ndarray, transform) -> tuple[np.ndarray, np.ndarray]:
    from rasterio.warp import transform as rio_transform
    from rasterio.transform import rowcol as rio_rowcol
    east, north = rio_transform("EPSG:4269", "EPSG:32611", lons.tolist(), lats.tolist())
    rr, cc = rio_rowcol(transform, east, north)
    return np.asarray(rr, dtype=np.int32), np.asarray(cc, dtype=np.int32)


def _idw_grid(py: np.ndarray, px: np.ndarray, vals: np.ndarray, shape, foot: np.ndarray,
              k: int = IDW_K, p: float = IDW_P, max_dist: float = IDW_MAX_DIST_PX) -> np.ndarray:
    """Inverse-distance field with hard coverage cutoff (0 outside max_dist of data)."""
    H, W = shape
    out = np.zeros((H, W), dtype=np.float32)
    m = np.isfinite(vals) & (vals > 0)
    if int(m.sum()) < 3:
        return out
    sy = np.asarray(py[m], dtype=np.float64)
    sx = np.asarray(px[m], dtype=np.float64)
    sv = np.asarray(vals[m], dtype=np.float64)
    tree = cKDTree(np.column_stack([sy, sx]))
    kk = int(min(k, sy.size))
    blk = 256
    for r0 in range(0, H, blk):
        r1 = min(H, r0 + blk)
        cols = np.nonzero(foot[r0:r1].any(axis=0))[0]
        if cols.size == 0:
            continue
        gy, gx = np.mgrid[r0:r1, 0:W].astype(np.float64)
        q = np.column_stack([gy.ravel(), gx.ravel()])
        dd, ii = tree.query(q, k=kk)
        if kk == 1:
            dd = dd[:, None]
            ii = ii[:, None]
        w = 1.0 / np.maximum(dd, 1e-6) ** p
        v = (w * sv[ii]).sum(axis=1) / np.maximum(w.sum(axis=1), 1e-12)
        v = v.reshape(r1 - r0, W)
        dmin = dd[:, 0].reshape(r1 - r0, W)
        blk_f = foot[r0:r1] & (dmin <= max_dist)
        out[r0:r1][blk_f] = v[blk_f].astype(np.float32)
        del gy, gx, q, dd, ii, w, v, dmin
    return np.where(foot, out, 0.0).astype(np.float32)


def _potential_field_strike(ddir: Path, bands_dir: Path, foot: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Along-edge unit vector of RTP + isostatic-gravity, else regional N10E."""
    H, W = foot.shape
    acc_g = None
    for idx, name in ((2, "rtp"), (13, "iso_grav_anom")):
        raw = np.load(bands_dir / f"{idx:02d}_{name}.npy").astype(np.float32)
        valid = foot & np.isfinite(raw)
        filled, _ = shared_features._fill_nearest(raw, valid)
        z = (filled - float(np.median(filled[foot]))) / (float(np.percentile(filled[foot], 99.0)
            - np.percentile(filled[foot], 1.0)) + 1e-6)
        acc_g = z if acc_g is None else acc_g + z
        del raw, filled
    acc_g = ndi.gaussian_filter(acc_g.astype(np.float32), 2.0, mode="nearest")
    gy, gx = np.gradient(acc_g.astype(np.float64))
    mag = np.hypot(gy, gx)
    tiny = mag < 1e-9
    # strike = perpendicular to gradient (along-edge direction)
    sdy = np.where(tiny, REGIONAL_STRIKE_DYDX[0], -gy / np.maximum(mag, 1e-9))
    sdx = np.where(tiny, REGIONAL_STRIKE_DYDX[1], gx / np.maximum(mag, 1e-9))
    return sdy.astype(np.float32), sdx.astype(np.float32)


def _rasterize_segments(cy, cx, sdy, sdx, half_len, weight, shape) -> np.ndarray:
    """Splat oriented segments (nearest-pixel walk, max-merge) onto a grid."""
    H, W = shape
    acc = np.zeros((H, W), dtype=np.float32)
    n = int(np.asarray(cy).size)
    for i in range(n):
        y0 = float(cy[i])
        x0 = float(cx[i])
        dy = float(sdy[i])
        dx = float(sdx[i])
        h = float(half_len[i])
        w = float(weight[i])
        if not (np.isfinite(y0) and np.isfinite(x0) and np.isfinite(dy) and np.isfinite(dx)
                and np.isfinite(h) and np.isfinite(w)) or h <= 0 or w <= 0:
            continue
        # Dense 0.5 px walk: linspace endpoint sampling can skip pixels
        # (notably the center for even step counts); caught by test_upflow_lane.
        for t in np.arange(-h, h + 0.25, 0.5):
            yy = int(round(y0 + dy * t))
            xx = int(round(x0 + dx * t))
            if 0 <= yy < H and 0 <= xx < W and w > acc[yy, xx]:
                acc[yy, xx] = np.float32(w)
    return acc

def _road_damp(ddir: Path, shape, foot: np.ndarray) -> np.ndarray:
    p = ddir / "external" / "tiger_road_distance_m.tif"
    if not p.exists():
        return np.ones(shape, dtype=np.float32)
    import rasterio
    with rasterio.open(p) as ds:
        d = ds.read(1).astype(np.float32) if ds.shape == shape else None
    if d is None:
        return np.ones(shape, dtype=np.float32)
    return np.where(foot, np.clip(d / 500.0, 0.0, 1.0).astype(np.float32), 1.0).astype(np.float32)


def build_or_load_upflow_stack(ddir: Path, wdir: Path, shared_mm: np.ndarray,
                               foot: np.ndarray, transform, log=print) -> np.ndarray:
    """Build (or load hash-verified) the (12, H, W) label-free upflow stack."""
    out_path = wdir / "upflow_free_v1.npy"
    meta_path = wdir / "upflow_free_v1.npy.json"
    inputs = {
        "training_features.tif": _sha(ddir / "training_features.tif"),
        "wellspring_csv": _sha(ddir / "external" / "gdr_wellspring_in_footprint.csv"),
        "vents_csv": _sha(ddir / "external" / "gdr_volcanic_vents_in_footprint.csv"),
        "qfaults_csv": _sha(ddir / "external" / "gdr_qfaults_traces.csv"),
        "probes_zip": _sha(ddir / "external" / "2m_temperature_probe_INGENIOUS_regional_data.zip"),
        "paleo_zip": _sha(ddir / "external" / "paleo_geothermal_regional.zip"),
        "tiger_tif": _sha(ddir / "external" / "tiger_road_distance_m.tif"),
        "labels_tif": _sha(ddir / "labels.tif"),
    }
    if out_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            if (meta.get("schema") == UPFLOW_SCHEMA_VERSION
                    and meta.get("inputs") == inputs
                    and meta.get("names") == UPFLOW_FREE_NAMES
                    and Path(meta.get("path", "")).name == out_path.name):
                mm = np.load(out_path, mmap_mode="r")
                if tuple(mm.shape) == (N_UPFLOW_FREE, foot.shape[0], foot.shape[1]):
                    log("[upflow] cache hit (hash-verified)")
                    return mm
        except (OSError, ValueError, KeyError):
            pass
    H, W = foot.shape

    def _inb(rr, cc):
        rr = np.asarray(rr, dtype=np.int64)
        cc = np.asarray(cc, dtype=np.int64)
        m = (rr >= 0) & (rr < H) & (cc >= 0) & (cc < W)
        m = m & foot[np.clip(rr, 0, H - 1), np.clip(cc, 0, W - 1)]
        return m

    log("[upflow] parsing point sources ...")
    plon, plat, pdab = _parse_probes(ddir)
    pr, pc = _lonlat_to_rowcol(plon, plat, transform)
    keep = _inb(pr, pc)
    pr, pc, pdab = pr[keep], pc[keep], pdab[keep]
    log(f"[upflow] probes in-footprint: {pr.size}")
    wy, wx, wt, wq = _parse_wellspring(ddir)
    wkeep = _inb(wy, wx)
    wy, wx, wt, wq = wy[wkeep], wx[wkeep], wt[wkeep], wq[wkeep]
    hot = np.isfinite(wt) & (wt >= 32.0)
    log(f"[upflow] wellsprings in-footprint: {wy.size}, hot>=32C: {int(hot.sum())}")
    slon, slat, swt, shalf = _parse_paleo(ddir)
    sr, sc = _lonlat_to_rowcol(slon, slat, transform)
    skeep = _inb(sr, sc)
    sr, sc, swt, shalf = sr[skeep], sc[skeep], swt[skeep], shalf[skeep]
    log(f"[upflow] paleo deposits in-footprint: {sr.size}")
    vy, vx = _parse_vents(ddir)
    vkeep = _inb(vy, vx)
    vy, vx = vy[vkeep], vx[vkeep]
    qy, qx, qw, qhalf, qsdy, qsdx = _parse_qfaults(ddir)
    qkeep = _inb(qy, qx)
    qy, qx, qw, qhalf, qsdy, qsdx = qy[qkeep], qx[qkeep], qw[qkeep], qhalf[qkeep], qsdy[qkeep], qsdx[qkeep]
    log(f"[upflow] vents={vy.size} qfaults={qy.size}")

    bands_dir = wdir / "bands"
    log("[upflow] potential-field strike ...")
    sdy, sdx = _potential_field_strike(ddir, bands_dir, foot)

    stack = np.lib.format.open_memmap(out_path, mode="w+", dtype=np.float32,
                                      shape=(N_UPFLOW_FREE, H, W))
    log("[upflow] U00 spring IDW ...")
    stack[0] = _robust_unit(_idw_grid(wy[hot], wx[hot], np.clip(wt[hot] - 20.0, 0, 160), (H, W), foot), foot)
    log("[upflow] U01 spring density ...")
    dens = np.zeros((H, W), dtype=np.float32)
    np.add.at(dens, (wy[hot], wx[hot]), 1.0)
    stack[1] = _robust_unit(ndi.gaussian_filter(dens, 3.0, mode="nearest"), foot)
    del dens
    log("[upflow] U02 quartz IDW ...")
    qm = np.isfinite(wq) & (wq >= 90.0)
    stack[2] = _robust_unit(_idw_grid(wy[qm], wx[qm], np.clip(wq[qm] - 80.0, 0, 180), (H, W), foot), foot)
    log("[upflow] U03 probe IDW ...")
    stack[3] = _robust_unit(_idw_grid(pr, pc, pdab, (H, W), foot), foot)
    log("[upflow] U04 thermal gradient ridge ...")
    th = np.maximum(np.asarray(stack[0], dtype=np.float32), np.asarray(stack[3], dtype=np.float32))
    th = np.maximum(th, np.asarray(stack[2], dtype=np.float32))
    gy, gx = np.gradient(th.astype(np.float64))
    gm = np.hypot(gy, gx).astype(np.float32)
    del gy, gx, th
    crest = shared_hyp.ridge_nms_2d(gm, foot)
    stack[4] = _robust_unit(np.where(crest, gm, 0.0), foot)
    del gm, crest
    log("[upflow] U05 spring corridors ...")
    hsy, hsx = wy[hot], wx[hot]
    hw = np.clip(wt[hot] - 20.0, 0, 160) / 40.0 + 0.5
    qhot = np.clip(wq[hot], 0, 300)
    hw = hw + np.where(np.isfinite(wq[hot]) & (wq[hot] >= 90.0), (qhot - 80.0) / 80.0, 0.0)
    seg = _rasterize_segments(hsy, hsx, sdy[hsy, hsx], sdx[hsy, hsx],
                              np.full(hsy.shape, 10.0), hw, (H, W))
    stack[5] = _robust_unit(ndi.gaussian_filter(seg, 1.5, mode="nearest"), foot)
    del seg, hw
    log("[upflow] U06 sinter corridors ...")
    seg = _rasterize_segments(sr, sc, sdy[sr, sc], sdx[sr, sc], shalf, swt, (H, W))
    stack[6] = _robust_unit(ndi.gaussian_filter(seg, 1.5, mode="nearest"), foot)
    del seg
    log("[upflow] U07 vent corridors ...")
    seg = _rasterize_segments(vy, vx, sdy[vy, vx], sdx[vy, vx],
                              np.full(vy.shape, 20.0), np.full(vy.shape, 1.5), (H, W))
    if vy.size >= 2:
        for i in range(vy.size):
            ddy = vy - vy[i]
            ddx = vx - vx[i]
            near = (np.hypot(ddy, ddx) <= 30.0) & (np.hypot(ddy, ddx) > 0)
            for j in np.nonzero(near)[0]:
                if j <= i:
                    continue
                ln = float(np.hypot(ddy[j], ddx[j]))
                uy, ux = ddy[j] / ln, ddx[j] / ln
                steps = int(max(2.0, ln))
                for t in np.linspace(0, ln, steps):
                    yy = int(round(float(vy[i]) + uy * t))
                    xx = int(round(float(vx[i]) + ux * t))
                    if 0 <= yy < H and 0 <= xx < W and seg[yy, xx] < 2.0:
                        seg[yy, xx] = 2.0
    stack[7] = _robust_unit(ndi.gaussian_filter(seg, 2.0, mode="nearest"), foot)
    del seg
    log("[upflow] U08 qfault corridors ...")
    seg = _rasterize_segments(qy, qx, qsdy, qsdx, qhalf, qw, (H, W))
    stack[8] = _robust_unit(ndi.gaussian_filter(seg, 1.5, mode="nearest"), foot)
    del seg
    log("[upflow] U09 edge concord ...")
    edge = None
    for j in (26, 27, 28, 29):
        ch = np.asarray(shared_mm[:, :, j], dtype=np.float32)
        edge = ch if edge is None else np.maximum(edge, ch)
        del ch
    stack[9] = _robust_unit(edge, foot)
    del edge
    log("[upflow] U10 align x edge ...")
    amax = None
    for j in (5, 6, 7, 8):
        ch = np.asarray(stack[j], dtype=np.float32)
        amax = ch if amax is None else np.maximum(amax, ch)
        del ch
    stack[10] = (amax * np.asarray(stack[9], dtype=np.float32)).astype(np.float32)
    del amax
    gc_collect = __import__("gc").collect
    gc_collect()
    log("[upflow] U11 road damp ...")
    stack[11] = _road_damp(ddir, (H, W), foot)
    stack.flush()
    meta = {"schema": UPFLOW_SCHEMA_VERSION, "names": UPFLOW_FREE_NAMES,
            "shape": [N_UPFLOW_FREE, H, W], "inputs": inputs,
            "cache_sha256": _sha(out_path), "path": str(out_path)}
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    log("[upflow] stack built")
    del stack
    gc_collect()
    return np.load(out_path, mmap_mode="r")


def compute_fold_visible_upflow(visible_mask: np.ndarray, foot: np.ndarray,
                                up_mm=None) -> dict:
    """Fold-local catalogue interactions from ``visible_mask`` ONLY.

    ``up_mm`` channels 10/4/0/3/2 supply the label-free alignment/thermal fields;
    when ``up_mm`` is None (invariance probe) unit fields are used so the call
    still exercises only the visible mask.
    """
    vis = np.asarray(visible_mask, bool) & np.asarray(foot, bool)
    d_vis = ndi.distance_transform_edt(~vis).astype(np.float32)
    far_gate = np.clip((d_vis - 2.0) / 4.0, 0.0, 1.0).astype(np.float32)
    far_gate = (far_gate * far_gate * (3.0 - 2.0 * far_gate)).astype(np.float32)
    if up_mm is None:
        align = np.ones(vis.shape, dtype=np.float32)
        thermal = np.ones(vis.shape, dtype=np.float32)
    else:
        align = np.asarray(up_mm[10], dtype=np.float32)
        t = np.asarray(up_mm[4], dtype=np.float32)
        t = np.maximum(t, np.asarray(up_mm[0], dtype=np.float32))
        t = np.maximum(t, np.asarray(up_mm[3], dtype=np.float32))
        thermal = np.maximum(t, np.asarray(up_mm[2], dtype=np.float32)).astype(np.float32)
        del t
    return {"d_vis": np.where(foot, d_vis, 0.0).astype(np.float32),
            "far_gate": np.where(foot, far_gate, 0.0).astype(np.float32),
            "align_far": np.where(foot, align * far_gate, 0.0).astype(np.float32),
            "thermal_far": np.where(foot, thermal * far_gate, 0.0).astype(np.float32)}


def build_alignment_surface(up_mm, foot: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unsupervised EXP-1 belief + 1px crest (fixed priors EXP1_W)."""
    a = np.asarray(up_mm[10], dtype=np.float32)
    t4 = np.asarray(up_mm[4], dtype=np.float32)
    s0 = np.asarray(up_mm[0], dtype=np.float32)
    p3 = np.asarray(up_mm[3], dtype=np.float32)
    road = np.asarray(up_mm[11], dtype=np.float32)
    w0, w1, w2, w3 = EXP1_W
    belief = (w0 * a + w1 * t4 + w2 * s0 + w3 * p3) * road
    belief = np.where(foot, belief, 0.0).astype(np.float32)
    crest = shared_hyp.ridge_nms_2d(belief, np.asarray(foot, bool)).astype(np.float32)
    del a, t4, s0, p3, road
    return belief, crest


def upflow_stack_receipt(wdir: Path) -> dict:
    return json.loads((wdir / "upflow_free_v1.npy.json").read_text())