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
import json

import numpy as np
from scipy import ndimage

from . import grid

FEATURE_SCHEMA_VERSION = "gems32-structural-v2-principal-curvature"

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


def _principal_curvature(a, sigma):
    """Signed Hessian eigenvalue with largest absolute magnitude."""
    axx = ndimage.gaussian_filter(a, sigma, order=(0, 2), mode="nearest")
    ayy = ndimage.gaussian_filter(a, sigma, order=(2, 0), mode="nearest")
    axy = ndimage.gaussian_filter(a, sigma, order=(1, 1), mode="nearest")
    tmp = np.sqrt(np.maximum(((axx - ayy) * 0.5) ** 2 + axy ** 2, 0.0))
    l1 = (axx + ayy) * 0.5 + tmp
    l2 = (axx + ayy) * 0.5 - tmp
    return np.where(np.abs(l1) >= np.abs(l2), l1, l2)


def _hessian_ridge(a, sigma):
    """Bright-ridge principal curvature, not a full Sato/Frangi filter.

    Pre-v2 caches used the smaller-magnitude eigenvalue and must be rebuilt.
    Historical results remain attached to their original implementation.
    """
    principal = _principal_curvature(a, sigma)
    return np.maximum(-principal, 0.0).astype(np.float32)


def _hessian_both_polarities(a, sigma):
    """Principal curvature magnitude for both bright ridges and dark valleys."""
    return np.abs(_principal_curvature(a, sigma)).astype(np.float32)


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
    metadata_path = out_path.with_suffix(out_path.suffix + ".json")
    # Old or partial stacks have no trusted schema receipt. Remove any old
    # receipt before touching bytes so interruptions cannot make them valid.
    metadata_path.unlink(missing_ok=True)
    need = {12, 14, 2, 13, 17, 15}                       # bands used by the derived channels
    kept = {}
    import rasterio
    sample_path = features_path.parent / "sample_submission.tif"
    sample_foot = None
    sample_grid = None
    if sample_path.exists():
        with rasterio.open(sample_path) as ds_sub:
            if ds_sub.count != 1:
                raise ValueError("sample template must have one band")
            sample_grid = (ds_sub.shape, ds_sub.crs, ds_sub.transform)
            sample_foot = np.isfinite(ds_sub.read(1))

    base_valid = None
    base_idx = None
    with rasterio.open(features_path) as s:
        h, w, nb = s.height, s.width, s.count
        if nb != 19:
            raise ValueError(f"Expected exactly 19 input bands, got {nb}")
        if sample_grid is not None and sample_grid != (s.shape, s.crs, s.transform):
            raise ValueError("feature/sample CRS, shape or transform differs")
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
    from .submission import sha256_file
    receipt = dict(feature_schema_version=FEATURE_SCHEMA_VERSION,
                   source_sha256=sha256_file(features_path),
                   sample_sha256=sha256_file(sample_path) if sample_path.exists() else None,
                   cache_sha256=sha256_file(out_path),
                   channels=CHANNELS, n_channels=len(CHANNELS), shape=[h, w],
                   footprint_px=int(footprint.sum()), path=str(out_path),
                   cache_warning="Pre-v2 Hessian caches are incompatible with this builder.")
    metadata_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def load_checked(out_path: str | Path, features_path: str | Path):
    """Load a schema- and source-pinned feature cache, or fail pending rebuild."""
    from .submission import sha256_file
    out_path, features_path = Path(out_path), Path(features_path)
    metadata_path = out_path.with_suffix(out_path.suffix + ".json")
    if not out_path.is_file() or not metadata_path.is_file():
        raise ValueError("Derived feature cache/receipt missing; rebuild with features.build")
    receipt = json.loads(metadata_path.read_text(encoding="utf-8"))
    sample = features_path.parent / "sample_submission.tif"
    sample_sha = sha256_file(sample) if sample.exists() else None
    if (receipt.get("feature_schema_version") != FEATURE_SCHEMA_VERSION
            or receipt.get("source_sha256") != sha256_file(features_path)
            or receipt.get("sample_sha256") != sample_sha
            or receipt.get("cache_sha256") != sha256_file(out_path)
            or receipt.get("channels") != CHANNELS):
        raise ValueError("Derived feature cache is stale or from different inputs; rebuild")
    stack = np.load(out_path, mmap_mode="r", allow_pickle=False)
    expected = (*receipt.get("shape", []), len(CHANNELS))
    if stack.shape != expected or stack.dtype != np.float32:
        raise ValueError("Derived feature cache dimensions/dtype do not match its receipt")
    return stack
