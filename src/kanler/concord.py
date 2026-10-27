"""KANLER-CONCORD lane (2026-10-27): 5-family soft-min concordance surface.

Pre-registration: docs/research/preregistration-20261027.md (written before
any fit). The surface uses NO catalogue-derived feature; labels enter only
through the shared holdout context (fold-local visible exclusion) and the
shared submission writer's on-catalogue check. Shared evaluator/writer are
imported, never forked (scripts/evaluate_holdout.py, scripts/submission_writer.py
-> gems32.holdout / gems32.submission).

Band semantics are taken from the restored files' own tags/descriptions
(verified 2026-10-27 by reading them back), NOT from legacy helper comments:
  lidar_scarp_features_u8: 1 ex_max, 2 ex_mean, 3 step_max, 4 lapneg_max,
    5 lappos_max, 6 downface_max, 7 upface_max, 8 cross_max, 9 relief,
    10 coh100, 11 strike, 12 valid
  geodawn_rad_u8: 1 K, 2 Th, 3 U, 4 TC ; geodawn_extensions_u8: 1 ThK, 4 TMI_up150
"""
from __future__ import annotations

import gc
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

FAMILIES = ("mag", "grav", "topo", "rad", "sub")
EPS_RANK = 1e-3


def rank01(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Percentile rank in [0,1] inside mask (average-rank ties via sorting)."""
    out = np.zeros(values.shape, dtype=np.float32)
    vals = np.asarray(values, dtype=np.float64)[mask]
    vals = np.where(np.isfinite(vals), vals, np.nan)
    finite = np.isfinite(vals)
    if finite.sum() < 2:
        return out
    v = vals[finite]
    order = np.argsort(v, kind="stable")
    ranks = np.empty(v.size, dtype=np.float64)
    ranks[order] = np.arange(v.size, dtype=np.float64)
    # average ranks for ties
    sv = v[order]
    i = 0
    r_sorted = ranks[order]
    while i < v.size:
        j = i + 1
        while j < v.size and sv[j] == sv[i]:
            j += 1
        if j - i > 1:
            r_sorted[i:j] = r_sorted[i:j].mean()
        i = j
    ranks[order] = r_sorted
    scaled = ranks / max(v.size - 1, 1)
    full = np.full(vals.shape, 0.5, dtype=np.float64)  # non-finite -> mid-rank
    full[finite] = scaled
    out[mask] = full.astype(np.float32)
    return out


def fill_nearest(raw: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Nearest-valid fill so derivative filters see no NaN cliffs."""
    if valid.all():
        return raw.astype(np.float32)
    _, idx = ndimage.distance_transform_edt(
        ~valid, return_distances=True, return_indices=True)
    filled = raw.astype(np.float32, copy=True)
    bad = ~valid
    filled[bad] = filled[idx[0][bad], idx[1][bad]]
    return filled


def _band(bands_dir: Path, fname: str) -> np.ndarray:
    return np.load(bands_dir / fname).astype(np.float32)


def _ridge(filled: np.ndarray, sigma: float) -> np.ndarray:
    from gems32.features import _hessian_both_polarities  # shared, v2-fixed
    return _hessian_both_polarities(filled, sigma)


def _grad_mag(filled: np.ndarray, sigma: float) -> np.ndarray:
    sm = ndimage.gaussian_filter(filled, sigma, mode="nearest")
    gy, gx = np.gradient(sm)
    return np.hypot(gx, gy).astype(np.float32)


def build_families(bands_dir: Path, ddir: Path, foot: np.ndarray,
                   log=print) -> dict[str, np.ndarray]:
    """Per-family percentile-rank fields in [0,1] on the footprint."""
    fam: dict[str, np.ndarray] = {}

    def prepared(fname):
        a = _band(bands_dir, fname)
        valid = np.isfinite(a)
        f = fill_nearest(np.where(valid, a, 0.0).astype(np.float32), valid)
        del a
        return f

    # MAG: RTP ridge (both polarities) + provided TMI horizontal gradient
    rtp = prepared("02_rtp.npy")
    mag = 0.6 * rank01(_ridge(rtp, 1.5), foot)
    del rtp; gc.collect()
    tmi_hg = prepared("03_tmi_hg.npy")
    mag += 0.4 * rank01(ndimage.gaussian_filter(tmi_hg, 1.0, mode="nearest"), foot)
    del tmi_hg; gc.collect()
    fam["mag"] = rank01(mag, foot); del mag; log("family mag done")

    # GRAV: isostatic gravity ridge + provided horizontal gradient
    grav = prepared("13_iso_grav_anom.npy")
    g = 0.6 * rank01(_ridge(grav, 2.0), foot)
    del grav; gc.collect()
    grav_hg = prepared("18_iso_grav_anom_hg.npy")
    g += 0.4 * rank01(ndimage.gaussian_filter(grav_hg, 1.0, mode="nearest"), foot)
    del grav_hg; gc.collect()
    fam["grav"] = rank01(g, foot); del g; log("family grav done")

    # TOPO: DEM ridge + tag-correct LiDAR scarp (valid-aware, DEM fallback)
    dem = prepared("12_det_elev.npy")
    dem_ridge = rank01(_ridge(dem, 1.5), foot)
    del dem; gc.collect()
    with rasterio.open(ddir / "external" / "lidar_scarp_features_u8.tif") as ds:
        assert [ds.descriptions[i] for i in (2, 3, 5, 9, 11)] == \
            ["step_max", "lapneg_max", "downface_max", "coh100", "valid"], \
            "lidar band tags changed; refusing to guess semantics"
        step = ds.read(3).astype(np.float32) / 255.0
        lapn = ds.read(4).astype(np.float32) / 255.0
        lapp = ds.read(5).astype(np.float32) / 255.0
        down = ds.read(6).astype(np.float32) / 255.0
        up = ds.read(7).astype(np.float32) / 255.0
        cross = ds.read(8).astype(np.float32) / 255.0
        coh = ds.read(10).astype(np.float32) / 255.0
        valid_l = (ds.read(12) > 0) & foot
    dipole = np.sqrt(np.maximum(lapn * lapp, 0.0)); del lapn, lapp
    scarp_raw = (0.35 * step + 0.25 * dipole + 0.20 * cross
                 + 0.20 * np.maximum(down, up)) * (0.5 + 0.5 * coh)
    del step, dipole, cross, down, up, coh; gc.collect()
    scarp_rank = rank01(scarp_raw, valid_l)
    del scarp_raw
    scarp_seamless = np.where(valid_l, scarp_rank, dem_ridge).astype(np.float32)
    del scarp_rank
    log(f"lidar valid fraction of footprint: {valid_l.mean():.4f} "
        f"({int(valid_l.sum())} px)")
    fam["topo"] = rank01(0.4 * dem_ridge + 0.6 * scarp_seamless, foot)
    del dem_ridge, scarp_seamless; gc.collect(); log("family topo done")

    # RAD: K/Th alteration-ratio edge + ThK edge (edges, not levels)
    with rasterio.open(ddir / "external" / "geodawn_rad_u8.tif") as ds:
        assert [ds.descriptions[0], ds.descriptions[1]] == ["K", "Th"]
        k_u8 = ds.read(1).astype(np.float32)
        th_u8 = ds.read(2).astype(np.float32)
    has_rad = (k_u8 > 0) & (th_u8 > 0) & foot
    ratio = np.where(has_rad, k_u8 / (th_u8 + 8.0), 0.0).astype(np.float32)
    del k_u8, th_u8
    ratio_f = fill_nearest(ratio, has_rad); del ratio
    rad = 0.6 * rank01(_grad_mag(ratio_f, 1.2), foot); del ratio_f; gc.collect()
    with rasterio.open(ddir / "external" / "geodawn_extensions_u8.tif") as ds:
        assert ds.descriptions[0] == "ThK"
        thk = ds.read(1).astype(np.float32)
    thk_f = fill_nearest(thk, (thk > 0) & foot); del thk
    rad += 0.4 * rank01(_grad_mag(thk_f, 1.2), foot); del thk_f; gc.collect()
    fam["rad"] = rank01(rad, foot); del rad; log("family rad done")

    # SUB: conductivity ridge + depth-to-basement step (gradient)
    cond = prepared("17_cond_surf.npy")
    sub = 0.5 * rank01(_ridge(cond, 2.0), foot); del cond; gc.collect()
    depth = prepared("15_depth_to_base_surf.npy")
    sub += 0.5 * rank01(_grad_mag(depth, 1.5), foot); del depth; gc.collect()
    fam["sub"] = rank01(sub, foot); del sub; log("family sub done")
    return fam


def build_surface(fam: dict[str, np.ndarray], ddir: Path,
                  foot: np.ndarray) -> np.ndarray:
    """S = rank01( (0.7*geomean + 0.3*mean of family ranks) * road_factor )."""
    stack = np.stack([fam[k] for k in FAMILIES])  # 5 x H x W float32
    geo = np.exp(np.log(stack + EPS_RANK).mean(axis=0)).astype(np.float32)
    blend = (0.7 * geo + 0.3 * stack.mean(axis=0)).astype(np.float32)
    del stack, geo; gc.collect()
    with rasterio.open(ddir / "external" / "tiger_road_distance_m.tif") as ds:
        road = ds.read(1).astype(np.float32)
    factor = np.where(np.isfinite(road), np.clip(road / 200.0, 0.3, 1.0), 1.0)
    del road
    surf = rank01(blend * factor.astype(np.float32), foot)
    del blend, factor; gc.collect()
    return surf


def score_ordered_thin(field: np.ndarray, allowed: np.ndarray, n_target: int,
                       min_dist: float = float(np.sqrt(8.0)),
                       candidate_mask: np.ndarray | None = None,
                       pool_mult: int = 4) -> tuple[np.ndarray, dict]:
    """Accept candidates in descending field order, >= min_dist apart.

    Deterministic: candidates enumerated in raster order, stable descending
    sort (ties keep raster order, so a binary field reproduces the raster
    order prefix of emission.dot_thin up to the budget cap).
    """
    field = np.asarray(field, dtype=np.float32)
    pool = allowed if candidate_mask is None else (allowed & candidate_mask)
    ys, xs = np.nonzero(pool)
    info = {"pool_px": int(ys.size), "n_target": int(n_target)}
    out = np.zeros(field.shape, bool)
    if ys.size == 0 or n_target <= 0:
        info["accepted"] = 0
        return out, info
    vals = field[ys, xs]
    # restrict to top pool_mult*n_target by value (expands if starved)
    mult = pool_mult
    while True:
        k = min(ys.size, max(n_target * mult, n_target))
        if k < ys.size:
            top = np.argpartition(-vals, k - 1)[:k]
            top = top[np.argsort(-vals[top], kind="stable")]
            # restore raster order among equal values: stable sort by -value
            # on a raster-sorted index array
            top = np.sort(top)
            top = top[np.argsort(-vals[top], kind="stable")]
            cand = top
        else:
            cand = np.argsort(-vals, kind="stable")
        r2 = min_dist * min_dist
        cell = max(1.0, float(min_dist))
        grid: dict[tuple[int, int], list[tuple[int, int]]] = {}
        accepted = 0
        out[:] = False
        for ci in cand:
            if accepted >= n_target:
                break
            y, x = int(ys[ci]), int(xs[ci])
            cy, cx = int(y // cell), int(x // cell)
            ok = True
            for gy in range(cy - 2, cy + 3):
                for gx in range(cx - 2, cx + 3):
                    for (ky, kx) in grid.get((gy, gx), ()):
                        dy, dx = y - ky, x - kx
                        if dy * dy + dx * dx < r2:
                            ok = False
                            break
                    if not ok:
                        break
                if not ok:
                    break
            if ok:
                out[y, x] = True
                grid.setdefault((cy, cx), []).append((y, x))
                accepted += 1
        info["accepted"] = int(accepted)
        info["pool_mult_used"] = int(mult)
        if accepted >= n_target or k >= ys.size:
            break
        mult *= 2
    return out, info
