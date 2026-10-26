"""Multi-scale structural feature stack built from the 19 official bands (+ derived transforms).

Design notes (documented, not tuned on the held-out blocks):

* the 19 official bands are used as given (NaN -> 0, plus a footprint flag);
* the *derived* channels are all **line/structure transforms**, not raw fields: curvature,
  Hessian ridge response at three scales, white top-hat (scarp-step detector), local relief,
  gradient magnitudes of the potential-field and subsurface bands, and the structure-tensor
  coherence/orientation.  A per-pixel classifier on raw fields produces blobs, and a blob pays
  false-positive mass for every pixel it is wider than the hidden 1-px trace; a line-shaped
  response is the metric's own currency (see ``emission.py`` and the algebra in ``metric.py``).
* no distance-to-catalogue channel is included: the group measured that this single column makes
  a detector AUC 1.0 on the visible catalogue and transfers nothing off it
  (GEMSDOE29 README, "the published headline candidate was a distance-to-catalogue look-up").
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import ndimage

from . import grid

CHANNELS = [
    *[f"band{i:02d}" for i in range(1, 20)],
    "curv_s1", "curv_s2", "ridge_s1", "ridge_s2", "ridge_s3",
    "relief5", "tophat2", "tmi_edge", "rtp_edge", "grav_edge", "cond_edge",
    "depth_grad", "coherence_s2", "strike_cos", "strike_sin", "footprint",
]


def _sm(a, s):
    return ndimage.gaussian_filter(a, s, mode="nearest")


def _grad_mag(a):
    gy, gx = np.gradient(a)
    return np.hypot(gx, gy)


def _hessian_ridge(a, sigma):
    """Sato/Frangi-style ridge response: largest |eigenvalue| with the ridge sign convention."""
    axx = ndimage.gaussian_filter(a, sigma, order=(0, 2), mode="nearest")
    ayy = ndimage.gaussian_filter(a, sigma, order=(2, 0), mode="nearest")
    axy = ndimage.gaussian_filter(a, sigma, order=(1, 1), mode="nearest")
    tmp = np.sqrt(np.maximum(((axx - ayy) * 0.5) ** 2 + axy ** 2, 0.0))
    l1 = (axx + ayy) * 0.5 + tmp
    l2 = (axx + ayy) * 0.5 - tmp
    big = np.where(np.abs(l1) >= np.abs(l2), l1, l2)
    small = np.where(np.abs(l1) >= np.abs(l2), l2, l1)
    return -small * (big < 0).astype(np.float32)      # bright ridge on dark background


def _structure_tensor(a, sigma):
    gx = ndimage.gaussian_filter(a, sigma, order=(0, 1), mode="nearest")
    gy = ndimage.gaussian_filter(a, sigma, order=(1, 0), mode="nearest")
    jxx = _sm(gx * gx, sigma)
    jyy = _sm(gy * gy, sigma)
    jxy = _sm(gx * gy, sigma)
    tr = jxx + jyy + 1e-12
    coh = np.sqrt(np.maximum(((jxx - jyy) * 0.5) ** 2 + jxy ** 2, 0.0)) / tr
    theta = 0.5 * np.arctan2(2 * jxy, (jxx - jyy) + 1e-12)
    return coh.astype(np.float32), theta.astype(np.float32), np.sqrt(tr).astype(np.float32)


def _fill_nearest(raw: np.ndarray, valid: np.ndarray, base_valid: np.ndarray | None = None,
                  base_idx: tuple[np.ndarray, np.ndarray] | None = None) -> tuple[np.ndarray, tuple[np.ndarray, np.ndarray]]:
    """Fill non-valid cells with nearest valid neighbour so derivative filters have zero border cliffs."""
    if not np.any(valid):
        z = np.zeros(raw.shape, dtype=np.float32)
        zi = np.zeros(raw.shape, dtype=np.intp)
        return z, (zi, zi.copy())
    if base_idx is not None and base_valid is not None and np.array_equal(valid, base_valid):
        idx = base_idx
    else:
        _, idx = ndimage.distance_transform_edt(~valid, return_distances=True, return_indices=True)
    filled = raw.astype(np.float32, copy=True)
    bad = ~valid
    if bad.any():
        filled[bad] = filled[idx[0][bad], idx[1][bad]]
    return filled, idx


def build(features_path: str | Path, out_path: str | Path, log=print) -> dict:
    """Build the (H, W, F) float32 stack as a disk-backed array; returns a small receipt."""
    features_path = Path(features_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    need = {12, 14, 2, 13, 17, 15}                       # bands used by the derived channels
    kept = {}
    import rasterio
    sample_path = features_path.parent / "sample_submission.tif"
    sample_foot = None
    if sample_path.exists():
        with rasterio.open(sample_path) as ds_sub:
            sample_foot = np.isfinite(ds_sub.read(1))

    base_valid = None
    base_idx = None
    with rasterio.open(features_path) as s:
        h, w, nb = s.height, s.width, s.count
        stack = np.lib.format.open_memmap(out_path, mode="w+", dtype=np.float32,
                                          shape=(h, w, len(CHANNELS) + max(0, nb - 19)))
        for i in range(1, nb + 1):
            raw = s.read(i)
            valid = np.isfinite(raw) & (raw > grid.NODATA_F32 * np.float32(0.5))
            if i == 1:
                footprint = sample_foot if sample_foot is not None else valid
            filled, idx = _fill_nearest(raw, valid, base_valid, base_idx)
            if base_valid is None:
                base_valid, base_idx = valid, idx
            del raw
            stack[:, :, i - 1] = np.where(footprint, filled, np.float32(0.0))
            if i in need:
                kept[i] = filled
            else:
                del filled
            log(f"  band {i:2d}/{nb} read")

    dem = kept[12]
    fmask = footprint
    c = 19
    stack[:, :, c] = np.where(fmask, ndimage.gaussian_laplace(dem, 1.0, mode="nearest"), 0.0); c += 1
    stack[:, :, c] = np.where(fmask, ndimage.gaussian_laplace(dem, 2.5, mode="nearest"), 0.0); c += 1
    for sigma in (1.0, 2.0, 3.5):
        stack[:, :, c] = np.where(fmask, _hessian_ridge(dem, sigma), 0.0); c += 1
        log(f"  ridge s={sigma}")
    loc = ndimage.maximum_filter(dem, size=5) - ndimage.minimum_filter(dem, size=5)
    stack[:, :, c] = np.where(fmask, loc, 0.0); c += 1
    tophat = dem - ndimage.grey_opening(dem, size=(5, 5))
    stack[:, :, c] = np.where(fmask, tophat, 0.0); c += 1
    stack[:, :, c] = np.where(fmask, _sm(_grad_mag(kept[14]), 1.0), 0.0); c += 1
    stack[:, :, c] = np.where(fmask, _sm(_grad_mag(kept[2]), 1.0), 0.0); c += 1
    stack[:, :, c] = np.where(fmask, _sm(_grad_mag(kept[13]), 1.5), 0.0); c += 1
    stack[:, :, c] = np.where(fmask, _sm(_grad_mag(kept[17]), 1.5), 0.0); c += 1
    stack[:, :, c] = np.where(fmask, _sm(_grad_mag(kept[15]), 1.5), 0.0); c += 1
    coh, theta, energy = _structure_tensor(dem, 2.0)
    stack[:, :, c] = np.where(fmask, coh, 0.0); c += 1
    stack[:, :, c] = np.where(fmask, np.cos(2 * theta), 0.0); c += 1
    stack[:, :, c] = np.where(fmask, np.sin(2 * theta), 0.0); c += 1
    stack[:, :, c] = footprint.astype(np.float32); c += 1
    stack.flush()
    return dict(channels=CHANNELS, n_channels=len(CHANNELS), shape=[h, w],
                footprint_px=int(footprint.sum()), path=str(out_path))
