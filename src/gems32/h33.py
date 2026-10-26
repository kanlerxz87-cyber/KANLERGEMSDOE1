"""H33 — five untried geological hypotheses, expressed as *label-free* physical surfaces.

Every surface in this module is computed from the 19 official bands, the USGS 3DEP 1 m LiDAR
scarp products and the GeoDAWN radiometric grids.  No surface reads ``labels.tif``,
``existing_faults.tif`` or any scored submission, so each one is safe to evaluate on a spatial
holdout without retrospective leakage.

The five hypotheses
-------------------
H33-A  **Multi-physics oriented-lineament consensus.**  A fault is a *curvilinear* feature, and a
       fault that experts can only find by eye is normally one that shows up in *more than one*
       physical field with the *same* strike.  Each physics (magnetics, gravity, topography,
       magnetotellurics, radiometrics, 1 m LiDAR scarps) is reduced to a scale-normalised
       Hessian *line* response plus a local orientation; the surface is the product of (i) the
       orientation order parameter of the ensemble (do the physics agree on a strike?) and
       (ii) the OR-fusion of the individual responses (does any physics respond at all?).
       NEW: the repository's 35 channels contain per-band ridge responses and *pixel-wise* products
       (H32-A/B/C), but no channel requires independent physics to agree on an *orientation*.

H33-B  **Aligned drainage-valley chains.**  Faults deflect and align channels; a single straight
       valley segment is a stream, a *chain of collinear valley segments across several drainages*
       is a structure.  The surface is a valley-skeleton (NMS ridge on ``-det_elev``) multiplied by
       a 9-pixel, 8-direction collinearity vote.  NEW: the repository's DEM channels are all local
       (curvature, ridge, relief, top-hat) and never aggregate evidence *along* a candidate line.

H33-C  **En-echelon scarplet chain vote (1 m LiDAR).**  A single scarplet in the 3DEP-derived
       product is noise; expert mappers accept a fault when scarplets are collinear over hundreds
       of metres.  Same collinearity vote, applied to the LiDAR scarp composite.
       NEW: the repository uses the LiDAR product only as a per-pixel corroboration weight.

H33-D  **Long-straight conductive/basement structural boundary.**  A fault in a conductivity or
       basement-depth volume is a *straight* gradient ridge: large gradient magnitude **and**
       orientation coherence over a long window.  NEW: the repository uses ``cond_surf`` and
       ``depth_to_base_surf`` as scalars / plain gradient magnitudes.

H33-E  **Sub-kilometre seismicity lineaments (data upgrade).**  The two supplied seismic bands are
       computed on a 100 km radius: measured here, ``ieq`` is 0.9935-correlated with itself at
       3 km lag, i.e. it carries no information at the fault scale the metric resolves (300 m).
       A raw epicentre catalogue (USGS ComSearch/FDSN, free and official) plus nodal-plane strikes
       would add the sub-kilometre structure the bands cannot carry.  The source is named and the
       sandbox reachability is recorded honestly in ``docs/research/h33-hypotheses.md``; no surface
       is fabricated for it here.

Provenance for every external input: ``registry/data_manifest.json`` (sha256-pinned).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import gaussian_filter, maximum_filter, minimum_filter

# --------------------------------------------------------------------------------------------
# shared primitives
# --------------------------------------------------------------------------------------------


def robust_unit(a: np.ndarray, foot: np.ndarray, pct: float = 99.5, clip: float = 6.0) -> np.ndarray:
    """Robust, footprint-normalised non-negative score in [0, 1] (median/IQR z, scaled at ``pct``)."""
    out = np.zeros(a.shape, dtype=np.float32)
    v = foot & np.isfinite(a)
    if not v.any():
        return out
    vals = a[v]
    med = float(np.median(vals))
    q25, q75 = np.percentile(vals, [25.0, 75.0])
    scale = max(float(q75 - q25) / 1.349, 1e-9)
    z = (a - med) / scale
    hi = float(np.percentile(z[v], pct))
    hi = max(hi, 1e-6)
    out[v] = np.clip(z[v] / hi, 0.0, clip) / clip
    return out


def _fill(a: np.ndarray, foot: np.ndarray, sigma: float | None) -> np.ndarray:
    v = foot & np.isfinite(a)
    med = float(np.median(a[v])) if v.any() else 0.0
    f = np.where(v, a, med).astype(np.float32)
    return gaussian_filter(f, sigma, mode="nearest") if sigma else f


def line_response(a: np.ndarray, sigma: float) -> np.ndarray:
    """Frangi/Sato-style curvilinear response: |smallest Hessian eigenvalue| with ridge/valley sign.

    Both polarities are accepted (``max`` of the bright-ridge and dark-valley responses) because a
    magnetic low and a magnetic high can equally well mark the same contact.
    """
    axx = gaussian_filter(a, sigma, order=(0, 2), mode="nearest")
    ayy = gaussian_filter(a, sigma, order=(2, 0), mode="nearest")
    axy = gaussian_filter(a, sigma, order=(1, 1), mode="nearest")
    tmp = np.sqrt(np.maximum(((axx - ayy) * 0.5) ** 2 + axy ** 2, 0.0))
    l1 = (axx + ayy) * 0.5 + tmp
    l2 = (axx + ayy) * 0.5 - tmp
    small = np.where(np.abs(l1) >= np.abs(l2), l2, l1)      # eigenvalue of least |.| : the ridge axis
    return -small                                            # > 0 on a line of either polarity


def structure_orientation(a: np.ndarray, sigma: float) -> tuple[np.ndarray, np.ndarray]:
    """Structure-tensor orientation ``theta`` (2*theta in the (cos, sin) convention) and coherence."""
    gx = gaussian_filter(a, sigma, order=(0, 1), mode="nearest")
    gy = gaussian_filter(a, sigma, order=(1, 0), mode="nearest")
    jxx = gaussian_filter(gx * gx, sigma, mode="nearest")
    jyy = gaussian_filter(gy * gy, sigma, mode="nearest")
    jxy = gaussian_filter(gx * gy, sigma, mode="nearest")
    tr = jxx + jyy + 1e-12
    coh = np.sqrt(np.maximum(((jxx - jyy) * 0.5) ** 2 + jxy ** 2, 0.0)) / tr
    theta = 0.5 * np.arctan2(2 * jxy, (jxx - jyy) + 1e-12)
    return theta.astype(np.float32), coh.astype(np.float32)


def collinearity_vote(skel: np.ndarray, foot: np.ndarray, halflen: int = 4) -> np.ndarray:
    """Maximum mean skeleton occupancy over the 16 straight lines of half-length ``halflen``.

    A per-pixel, orientation-free test of *collinearity*: a pixel scores 1 only if the skeleton is
    continuously present along at least one straight direction through it.  Implemented with
    shifted adds (no interpolation, no kernel library), so it is exact and cheap.
    """
    s = np.where(foot, skel, 0.0).astype(np.float32)
    up = [(-1, 0), (1, 0), (0, -1), (0, 1),
          (-1, -1), (-1, 1), (1, -1), (1, 1)]
    best = np.zeros_like(s)
    for dy, dx in up:
        acc = np.zeros_like(s)
        n = 0
        for k in range(-halflen, halflen + 1):
            acc += np.roll(np.roll(s, k * dy, axis=0), k * dx, axis=1)
            n += 1
        np.maximum(best, acc / n, out=best)
    return best


def _read_scored(path: Path) -> np.ndarray:
    with rasterio.open(path) as ds:
        return ds.read(1)


def _band(bands_dir: Path, idx: int, name: str, foot: np.ndarray) -> np.ndarray:
    a = np.load(bands_dir / f"{idx:02d}_{name}.npy").astype(np.float32)
    return np.where(foot & np.isfinite(a), a, np.nan)


def _external(ddir: Path, rel: str, band: int, foot: np.ndarray) -> np.ndarray:
    with rasterio.open(ddir / "external" / rel) as ds:
        a = ds.read(band).astype(np.float32)
    return np.where(foot, a, np.nan)


def lidar_scarp_composite(ddir: Path, foot: np.ndarray) -> np.ndarray:
    """0.45*ex_max + 0.35*step_max + 0.20*downface_max — the repository's H32 convention, reused."""
    with rasterio.open(ddir / "external" / "lidar_scarp_features_u8.tif") as ds:
        b1 = ds.read(1).astype(np.float32) / 255.0
        b2 = ds.read(2).astype(np.float32) / 255.0
        b5 = ds.read(5).astype(np.float32) / 255.0 if ds.count >= 5 else b1
    return np.where(foot, 0.45 * b1 + 0.35 * b2 + 0.20 * b5, np.nan)


# --------------------------------------------------------------------------------------------
# H33-A  multi-physics oriented-lineament consensus
# --------------------------------------------------------------------------------------------

H33A_PHYSICS = ("mag", "grav", "topo", "mt", "rad", "scarp")


def build_h33a(bands_dir: Path, ddir: Path, foot: np.ndarray) -> np.ndarray:
    grids: dict[str, np.ndarray] = {
        "mag": _band(bands_dir, 2, "rtp", foot) * 0.5
               + _band(bands_dir, 14, "tmi", foot) * 0.25
               + _band(bands_dir, 1, "mag_anom", foot) * 0.25,
        "grav": _band(bands_dir, 13, "iso_grav_anom", foot),
        "topo": _band(bands_dir, 12, "det_elev", foot),
        "mt": _band(bands_dir, 17, "cond_surf", foot) * 0.5
              + _band(bands_dir, 15, "depth_to_base_surf", foot) * 0.5,
        "rad": _external(ddir, "geodawn_rad_u8.tif", 4, foot) * 0.5
               + _external(ddir, "geodawn_rad_u8.tif", 1, foot) * 0.25
               + _external(ddir, "geodawn_rad_u8.tif", 2, foot) * 0.25,
        "scarp": lidar_scarp_composite(ddir, foot),
    }
    resp: dict[str, np.ndarray] = {}
    thetas: dict[str, np.ndarray] = {}
    for key, g in grids.items():
        f = _fill(g, foot, 1.0)
        # per-physics robust standardisation so the OR-fusion is scale-free
        v = foot & np.isfinite(g)
        mu = float(np.mean(f[v])); sd = float(np.std(f[v])) + 1e-9
        z = (f - mu) / sd
        r = np.maximum(line_response(z, 1.2), line_response(z, 2.5))
        resp[key] = robust_unit(r, foot)
        theta, _ = structure_orientation(z, 2.0)
        thetas[key] = theta

    # OR-fusion: any physics may nominate a line ...
    prod = np.ones(foot.shape, dtype=np.float32)
    for key in H33A_PHYSICS:
        w = np.clip(resp[key], 0.0, 1.0)
        prod *= (1.0 - w)
    fusion = 1.0 - prod
    # ... but the physics must agree on the strike (2nd-order orientation order parameter)
    cx = np.zeros(foot.shape, dtype=np.float32)
    cy = np.zeros(foot.shape, dtype=np.float32)
    cw = np.zeros(foot.shape, dtype=np.float32)
    for key in H33A_PHYSICS:
        w = np.clip(resp[key], 0.0, 1.0)
        cx += w * np.cos(2.0 * thetas[key])
        cy += w * np.sin(2.0 * thetas[key])
        cw += w
    order = np.sqrt(cx * cx + cy * cy) / np.maximum(cw, 1e-6)
    score = fusion * np.power(np.clip(order, 0.0, 1.0), 1.5)
    score[~foot] = 0.0
    return robust_unit(score, foot).astype(np.float32)


# --------------------------------------------------------------------------------------------
# H33-B  aligned drainage-valley chains
# --------------------------------------------------------------------------------------------


def build_h33b(bands_dir: Path, ddir: Path, foot: np.ndarray) -> np.ndarray:
    elev = _fill(_band(bands_dir, 12, "det_elev", foot), foot, 1.0)
    slope = _band(bands_dir, 19, "det_elev_slope", foot)
    slope_n = robust_unit(np.abs(slope), foot)
    # valley = ridge of the negated surface
    vresp = np.maximum(line_response(-elev, 1.2), line_response(-elev, 2.5))
    vn = robust_unit(vresp, foot)
    # 1-px skeleton: non-maximum suppression across the 4 principal directions of the response
    mx = maximum_filter(vn, size=3)
    skel = (vn >= mx - 1e-9) & (vn > 0.02) & foot
    chain = collinearity_vote(skel.astype(np.float32), foot, halflen=4)
    # low-relief valleys are the informative ones: a fault-controlled valley is not a canyon
    score = vn * chain * (0.35 + 0.65 * (1.0 - slope_n))
    score[~foot] = 0.0
    return robust_unit(score, foot).astype(np.float32)


# --------------------------------------------------------------------------------------------
# H33-C  en-echelon scarplet chain vote on the 1 m LiDAR product
# --------------------------------------------------------------------------------------------


def build_h33c(bands_dir: Path, ddir: Path, foot: np.ndarray) -> np.ndarray:
    comp = lidar_scarp_composite(ddir, foot)
    cn = robust_unit(_fill(comp, foot, 0.8), foot)
    mx = maximum_filter(cn, size=3)
    mn = minimum_filter(cn, size=3)
    skel = (cn >= mx - 1e-9) & (cn > 0.05) & foot & (cn > 2.0 * mn)
    chain = collinearity_vote(skel.astype(np.float32), foot, halflen=5)
    score = cn * np.power(chain, 1.5)
    score[~foot] = 0.0
    return robust_unit(score, foot).astype(np.float32)


# --------------------------------------------------------------------------------------------
# H33-D  long-straight conductive / basement structural boundary
# --------------------------------------------------------------------------------------------


def build_h33d(bands_dir: Path, ddir: Path, foot: np.ndarray) -> np.ndarray:
    out = np.zeros(foot.shape, dtype=np.float32)
    for idx, name in ((17, "cond_surf"), (15, "depth_to_base_surf")):
        g = _fill(_band(bands_dir, idx, name, foot), foot, 1.5)
        gy, gx = np.gradient(gaussian_filter(g, 1.5, mode="nearest"))
        mag = robust_unit(np.hypot(gy, gx), foot)
        # orientation coherence of the *gradient direction* over a long window
        nx, ny = gx / (np.hypot(gx, gy) + 1e-9), gy / (np.hypot(gx, gy) + 1e-9)
        c = np.zeros(foot.shape, dtype=np.float32)
        s = np.zeros(foot.shape, dtype=np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                c += np.roll(np.roll(nx, dy, 0), dx, 1) * nx + np.roll(np.roll(ny, dy, 0), dx, 1) * ny
                s += 1.0
        straight = np.clip((c / s - 0.5) / 0.5, 0.0, 1.0)
        out += mag * np.power(straight, 1.5)
    out /= 2.0
    out[~foot] = 0.0
    return robust_unit(out, foot).astype(np.float32)


H33_BUILDERS = {
    "H33-A": build_h33a,
    "H33-B": build_h33b,
    "H33-C": build_h33c,
    "H33-D": build_h33d,
}

H33_SPECS = {
    "H33-A": {
        "name": "Multi-physics oriented-lineament consensus",
        "layers": ["rtp(2)", "tmi(14)", "mag_anom(1)", "iso_grav_anom(13)", "det_elev(12)",
                   "cond_surf(17)", "depth_to_base_surf(15)", "geodawn_rad K/Th/TC",
                   "lidar_scarp_features (ex_max/step_max/downface_max)"],
        "signature": "scale-normalised Hessian line response per physics x 2nd-order orientation "
                     "order parameter (do independent physics agree on the strike?)",
        "why_off_catalogue": "the catalogue is dominated by faults that were mappable in one "
                             "dataset (usually topography or the existing maps); requiring "
                             "multi-physics strike agreement selects the class of curvilinear "
                             "structure an expert can only accept when several fields agree",
        "novelty": "no channel or H32 surface requires *independent* physics to agree on an "
                   "orientation; features.py has per-band ridges and H32-A/C have pixel products",
        "cost": "~40 s CPU",
    },
    "H33-B": {
        "name": "Aligned drainage-valley chains",
        "layers": ["det_elev(12)", "det_elev_slope(19)"],
        "signature": "valley skeleton (NMS ridge of -det_elev) x 9-px 16-direction collinearity vote, "
                     "de-emphasised where det_elev_slope is high",
        "why_off_catalogue": "faults that lack a preserved scarp still deflect and align drainage; a "
                             "collinear chain of valley segments across several drainages is "
                             "structural, which a single scarp-height map cannot see",
        "novelty": "the repo's DEM channels are all local; nothing aggregates evidence *along* a line",
        "cost": "~25 s CPU",
    },
    "H33-C": {
        "name": "En-echelon scarplet chain vote (1 m LiDAR)",
        "layers": ["lidar_scarp_features_u8 (ex_max, step_max, downface_max)"],
        "signature": "scarplet skeleton x 11-px collinearity vote requiring contrast vs the local "
                     "minimum (a scarp, not a slope break)",
        "why_off_catalogue": "a single 1 m scarplet is noise; en-echelon collinear scarplets are what "
                             "expert mappers accept as a fault, and they are below the 100 m grid",
        "novelty": "the repo uses the LiDAR product only as a per-pixel corroboration weight",
        "cost": "~20 s CPU",
    },
    "H33-D": {
        "name": "Long-straight conductive / basement structural boundary",
        "layers": ["cond_surf(17)", "depth_to_base_surf(15)"],
        "signature": "gradient magnitude x directional coherence of the gradient direction over a "
                     "3x3 window (a straight boundary, not a blobby anomaly)",
        "why_off_catalogue": "MT conductivity and basement depth image the *subsurface*; a straight "
                             "conductivity step locates a fault under cover, where a surface "
                             "catalogue has nothing",
        "novelty": "cond_surf/depth are used as scalars or plain gradient magnitudes in features.py",
        "cost": "~15 s CPU",
    },
}


def top_n_mask(surface: np.ndarray, foot: np.ndarray, n: int) -> np.ndarray:
    """Mask of the ``n`` highest-scoring footprint pixels of a surface (matched-budget control)."""
    s = np.where(foot, np.asarray(surface, dtype=np.float32), -np.inf)
    flat = s.ravel()
    idx = np.argpartition(flat, -n)[-n:]
    m = np.zeros(flat.shape, dtype=bool)
    m[idx] = True
    return m.reshape(s.shape)


def rank_surface(surface: np.ndarray, foot: np.ndarray) -> np.ndarray:
    """Dense rank (0..1) of the surface inside the footprint; used for union weighting."""
    s = np.where(foot, np.asarray(surface, dtype=np.float32), -np.inf)
    order = np.argsort(np.argsort(s.ravel(), kind="stable"), kind="stable").astype(np.float32)
    order = order / max(float(foot.sum() - 1), 1.0)
    out = order.reshape(s.shape)
    out[~foot] = 0.0
    return out
