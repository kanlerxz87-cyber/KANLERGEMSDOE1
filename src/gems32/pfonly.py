"""PF-ONLY lane (Arena41): potential-field-only blind-basin fault detector.

Lane (single paragraph): train a gradient-boosted detector using ONLY subsurface
potential-field / basement layers (magnetics 1,2,3,9,14; gravity 5,11,13,18; magnetic
source-depth/tilt 6; basement depth 15; conductivity 17) and label-free transforms of
those layers (horizontal-gradient magnitude, FFT upward-continuation persistence,
Hessian ridges, gradient of basement/conductivity).  Deliberately EXCLUDED:
detrended elevation and its slope (12,19), 1 m LiDAR scarps, radiometrics, geodetic
strain (4,7,8) and the 100 km earthquake-density bands (10,16).  Rationale: catalogue
inclusion is caused by surface expression, so a DEM/LiDAR-trained detector learns the
catalogue's selection function P(catalogued|fault) rather than P(fault); faults missing
from USGS/INGENIOUS are preferentially the buried intra-basin/piedmont segments whose
scarps are concealed by basin fill but which still offset magnetic/gravity basement.
A non-fault process that can mimic the signature: basement lithologic contacts and
intrusion/volcanic margins produce the same persistent potential-field edges with no
fault at all.
"""
from __future__ import annotations
import numpy as np
from scipy import ndimage

def robust_unit(a: np.ndarray, foot: np.ndarray, pct: float = 99.5) -> np.ndarray:
    """Median/IQR robust score clipped to [0,1] at the pct-th percentile (label-free)."""
    out = np.zeros(a.shape, dtype=np.float32)
    v = foot & np.isfinite(a)
    if not v.any():
        return out
    vals = a[v].astype(np.float64)
    med = float(np.median(vals)); q25, q75 = np.percentile(vals, [25.0, 75.0])
    scale = max(float(q75 - q25) / 1.349, 1e-9)
    z = (a.astype(np.float64) - med) / scale
    hi = max(float(np.percentile(z[v], pct)), 1e-6)
    out[v] = np.clip(z[v] / hi, 0.0, 1.0).astype(np.float32)
    return out

def fill_median(a: np.ndarray, foot: np.ndarray) -> np.ndarray:
    v = foot & np.isfinite(a)
    med = float(np.median(a[v])) if v.any() else 0.0
    return np.where(v, a, med).astype(np.float32)

def grad_mag(a: np.ndarray, sigma: float = 0.0) -> np.ndarray:
    b = ndimage.gaussian_filter(a, sigma, mode="nearest") if sigma else a
    gy, gx = np.gradient(b)
    return np.hypot(gx, gy).astype(np.float32)

def upward_continue(a: np.ndarray, height_px: float, dx_m: float = 100.0) -> np.ndarray:
    """FFT upward continuation by height_px pixels: multiply spectrum by exp(-|k|*h).

    a is a filled (no NaN) 2-D field. This is the standard potential-field continuation
    operator (e.g. Blakely, Potential Theory in Gravity and Magnetic Applications):
    a harmonic field observed h higher has each wavenumber damped by exp(-|k| h), so
    deep/long-wavelength basement edges persist while shallow sources attenuate.
    """
    h, w = a.shape
    fy = np.fft.fftfreq(h, d=dx_m) * 2.0 * np.pi
    fx = np.fft.fftfreq(w, d=dx_m) * 2.0 * np.pi
    ky, kx = np.meshgrid(fy, fx, indexing="ij")
    k = np.sqrt(kx * kx + ky * ky)
    F = np.fft.fft2(a.astype(np.float64))
    out = np.fft.ifft2(F * np.exp(-k * (height_px * dx_m))).real
    return out.astype(np.float32)

def hessian_ridge(a: np.ndarray, sigma: float) -> np.ndarray:
    """Shared bright-ridge curvature; old PF-only caches used a defective eigenvalue."""
    from .features import _hessian_ridge
    return _hessian_ridge(a, sigma)

def dot_thin(field: np.ndarray, eligible: np.ndarray, budget: int, min_dist: float = 2.8,
             pool: int = 900_000) -> np.ndarray:
    """Greedy field-ordered thinning: accept highest-field pixels >= min_dist apart.

    This is the emission geometry the group's live ladder validated (d2.8); the lane's
    novelty is the field being thinned, not the packing. Cell-hash neighbour checks keep
    it O(pool) with a small constant.
    """
    idx = np.flatnonzero(eligible & np.isfinite(field))
    if idx.size == 0:
        return np.zeros(field.shape, bool)
    vals = field.ravel()[idx]
    if idx.size > pool:
        keep = np.argpartition(-vals, pool - 1)[:pool]
        idx, vals = idx[keep], vals[keep]
    order = np.argsort(-vals, kind="stable")
    idx = idx[order]
    W = field.shape[1]
    cell = max(1, int(np.ceil(min_dist)))
    grid: dict[tuple[int, int], list[tuple[int, int]]] = {}
    out = np.zeros(field.shape, bool)
    accepted = 0; md2 = float(min_dist) ** 2
    for flat in idx:
        y, x = divmod(int(flat), W)
        cy, cx = y // cell, x // cell
        ok = True
        for gy in (cy - 1, cy, cy + 1):
            for gx in (cx - 1, cx, cx + 1):
                for (yy, xx) in grid.get((gy, gx), ()):
                    if (yy - y) ** 2 + (xx - x) ** 2 < md2:
                        ok = False; break
                if not ok: break
            if not ok: break
        if ok:
            out[y, x] = True
            grid.setdefault((cy, cx), []).append((y, x))
            accepted += 1
            if accepted >= budget:
                break
    return out

def pooled_dti_from_folds(folds: dict) -> dict:
    """Pooled DTI from gems32.holdout per-cell components (alpha=0.2, beta=0.8)."""
    tp = sum(v["tp"] for v in folds.values()); fp = sum(v["fp"] for v in folds.values())
    fn = sum(v["n_truth"] - v["tp"] for v in folds.values()); n = sum(v["n_truth"] for v in folds.values())
    dti = tp / (tp + 0.2 * fp + 0.8 * fn + 1e-12)
    # cluster bootstrap over cells for a 95% CI (cells = 4 quadrants x 2 draws)
    cells = list(folds.values()); rng = np.random.default_rng(41); boots = []
    for _ in range(2000):
        pick = [cells[i] for i in rng.integers(0, len(cells), len(cells))]
        btp = sum(v["tp"] for v in pick); bfp = sum(v["fp"] for v in pick)
        bfn = sum(v["n_truth"] - v["tp"] for v in pick)
        boots.append(btp / (btp + 0.2 * bfp + 0.8 * bfn + 1e-12))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"pooled_dti": float(dti), "ci95_cluster_bootstrap": [float(lo), float(hi)],
            "tp": float(tp), "fp": float(fp), "fn": float(fn), "n_withheld_positives": int(n),
            "n_cells": len(cells)}
