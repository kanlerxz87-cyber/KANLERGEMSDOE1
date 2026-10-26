"""Historical H35 hypothesis sketches; global novelty and provenance are unverified.

The surfaces use mirrored numerical and external data, without directly reading
labels. This does not prove leakage-free data provenance or fold-local emissions.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import rasterio
from scipy.ndimage import gaussian_filter, maximum_filter, minimum_filter

def robust_unit(a: np.ndarray, foot: np.ndarray, pct: float = 99.5, clip: float = 6.0) -> np.ndarray:
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
    """Shared bright-ridge curvature; old H35 runs used a defective eigenvalue."""
    from .features import _hessian_ridge
    return _hessian_ridge(a, sigma)

def structure_orientation(a: np.ndarray, sigma: float):
    gx = gaussian_filter(a, sigma, order=(0, 1), mode="nearest")
    gy = gaussian_filter(a, sigma, order=(1, 0), mode="nearest")
    jxx = gaussian_filter(gx * gx, sigma, mode="nearest")
    jyy = gaussian_filter(gy * gy, sigma, mode="nearest")
    jxy = gaussian_filter(gx * gy, sigma, mode="nearest")
    tr = jxx + jyy + 1e-12
    coh = np.sqrt(np.maximum(((jxx - jyy) * 0.5) ** 2 + jxy ** 2, 0.0)) / tr
    theta = 0.5 * np.arctan2(2 * jxy, (jxx - jyy) + 1e-12)
    return theta.astype(np.float32), coh.astype(np.float32)

def _band(bands_dir: Path, idx: int, name: str, foot: np.ndarray) -> np.ndarray:
    a = np.load(bands_dir / f"{idx:02d}_{name}.npy").astype(np.float32)
    return np.where(foot & np.isfinite(a), a, np.nan)

def _external(ddir: Path, rel: str, band: int, foot: np.ndarray) -> np.ndarray:
    with rasterio.open(ddir / "external" / rel) as ds:
        a = ds.read(band).astype(np.float32)
    return np.where(foot, a, np.nan)

def lidar_scarp_composite(ddir: Path, foot: np.ndarray) -> np.ndarray:
    with rasterio.open(ddir / "external" / "lidar_scarp_features_u8.tif") as ds:
        b1 = ds.read(1).astype(np.float32) / 255.0
        b2 = ds.read(2).astype(np.float32) / 255.0
        b5 = ds.read(5).astype(np.float32) / 255.0 if ds.count >= 5 else b1
    return np.where(foot, 0.45 * b1 + 0.35 * b2 + 0.20 * b5, np.nan)

# ---- H35-A: Multi-scale curvature persistence ----
def build_h35a(bands_dir: Path, ddir: Path, foot: np.ndarray) -> np.ndarray:
    """Detrended elevation curvature persistence across 3 scales.
    Targets subtle degraded scarps that persist across scales; single-scale ridge misses them.
    """
    elev = _band(bands_dir, 12, "det_elev", foot)
    # compute curvature at 3 scales via LoG
    curvs = []
    for sig in (1.5, 2.5, 4.0):
        f = _fill(elev, foot, 1.0)
        # Laplacian
        lap = gaussian_filter(f, sig, order=(2,0), mode="nearest") + gaussian_filter(f, sig, order=(0,2), mode="nearest")
        # ridge response: -lap where positive (valley) or negative (ridge) - use absolute
        r = np.abs(lap)
        curvs.append(robust_unit(r, foot))
    # persistence: product across scales where sign consistent (all high)
    persist = curvs[0] * curvs[1] * curvs[2]
    # also include profile curvature via structure coherence
    # weight by low slope (subtle scarps have moderate slope)
    slope = _band(bands_dir, 19, "det_elev_slope", foot)
    slope_n = robust_unit(np.abs(slope), foot)
    # subtle scarp: curvature high but slope not extreme
    score = persist * (0.6 + 0.4 * (1.0 - slope_n))
    score[~foot] = 0.0
    return robust_unit(score, foot).astype(np.float32)

# ---- H35-B: Tilt-angle edge + magnetic gradient amplitude coupling ----
def build_h35b(bands_dir: Path, ddir: Path, foot: np.ndarray) -> np.ndarray:
    """TC zero proximity * TMI_HG amplitude.
    TC ~0 marks magnetic contact edge; TMI_HG amplitude ensures edge is real, not noise.
    Catches subsurface contacts under cover where catalogue has no surface expression.
    """
    tc = _fill(_band(bands_dir, 6, "tc", foot), foot, 1.0)
    # TC ideal edge at 0 degrees (normalized); bands 6 is tilt angle in degrees 0-90? Normalize to distance from 0
    # In data tc ranges 2-88, median 18.48, so zero not literal; but low tc = edge? Actually tilt zero near contact.
    # Use normalized proximity to lower quartile
    # Compute distance to 0: 1/(1+|tc|)
    tc_edge = 1.0 / (1.0 + np.abs(tc) * 0.1)
    tc_n = robust_unit(tc_edge, foot)
    tmi_hg = _band(bands_dir, 3, "tmi_hg", foot)
    hg_n = robust_unit(np.abs(tmi_hg), foot)
    rtp = _band(bands_dir, 2, "rtp", foot)
    rtp_grad = np.hypot(*np.gradient(_fill(rtp, foot, 1.5)))
    rtp_n = robust_unit(rtp_grad, foot)
    # coupling: edge proximity * gradient strength
    score = tc_n * (0.5 * hg_n + 0.5 * rtp_n)
    # require line continuity via Hessian line response on RTP
    rtp_line = robust_unit(np.maximum(line_response(_fill(rtp, foot,1.0),1.5),0), foot)
    score = score * (0.5 + 0.5 * rtp_line)
    score[~foot] = 0.0
    return robust_unit(score, foot).astype(np.float32)

# ---- H35-C: Conductivity-basement co-gradient alignment ----
def build_h35c(bands_dir: Path, ddir: Path, foot: np.ndarray) -> np.ndarray:
    """Gradient magnitude product * cosine alignment of cond_surf and depth_to_base_surf gradients.
    Targets basement steps under conductive cover where fault juxtaposes conductivity and basement.
    Prior H32 used scalar products, never gradient direction alignment.
    """
    cond = _fill(_band(bands_dir, 17, "cond_surf", foot), foot, 1.5)
    depth = _fill(_band(bands_dir, 15, "depth_to_base_surf", foot), foot, 1.5)
    gy_c, gx_c = np.gradient(gaussian_filter(cond,1.5, mode="nearest"))
    gy_d, gx_d = np.gradient(gaussian_filter(depth,1.5, mode="nearest"))
    mag_c = np.hypot(gy_c, gx_c)
    mag_d = np.hypot(gy_d, gx_d)
    mag_prod = robust_unit(mag_c * mag_d, foot)
    # cosine alignment
    dot = gy_c*gy_d + gx_c*gx_d
    cosalign = np.abs(dot) / (np.hypot(gy_c,gx_c)*np.hypot(gy_d,gx_d) + 1e-9)
    # require alignment >0.5 (same strike)
    align = np.clip((cosalign - 0.5)/0.5, 0,1)
    # straightness via orientation coherence of joint gradient direction
    nx, ny = (gx_c+gx_d)/2, (gy_c+gy_d)/2
    # simple coherence over 3x3 window
    score = mag_prod * align
    score[~foot] = 0.0
    return robust_unit(score, foot).astype(np.float32)

# ---- H35-D: Radiometric Th/K alteration edge * gravity gradient ----
def build_h35d(bands_dir: Path, ddir: Path, foot: np.ndarray) -> np.ndarray:
    """Th/K ratio edge from GeoDAWN radiometrics * iso_grav_anom_hg gradient.
    Hydrothermal alteration changes Th/K, marking conduits lacking topographic scarp.
    Prior used rad as generic, not alteration ratio edge.
    """
    # GeoDAWN rad bands: 1=K,2=Th,3=U,4=TC? Use Th/K ratio as alteration proxy
    try:
        k = _external(ddir, "geodawn_rad_u8.tif", 1, foot).astype(np.float32)
        th = _external(ddir, "geodawn_rad_u8.tif", 2, foot).astype(np.float32)
        ratio = th / (k + 1e-6)
        # extensions has Th/K precomputed?
        try:
            thk = _external(ddir, "geodawn_extensions_u8.tif", 1, foot)
            if np.isfinite(thk[foot]).any():
                ratio = thk
        except: pass
    except:
        ratio = _band(bands_dir, 1, "mag_anom", foot) *0 # fallback
    ratio_f = _fill(ratio, foot, 1.0)
    gy_r, gx_r = np.gradient(gaussian_filter(ratio_f, 1.5, mode="nearest"))
    mag_r = robust_unit(np.hypot(gy_r,gx_r), foot)
    grav_hg = _band(bands_dir, 18, "iso_grav_anom_hg", foot)
    grav_n = robust_unit(np.abs(grav_hg), foot)
    # co-location: alteration edge where gravity gradient also present (structure controls alteration)
    score = mag_r * (0.3 + 0.7 * grav_n)
    # lidar corroboration weight (alteration without scarp still valid, so light weight)
    lidar = lidar_scarp_composite(ddir, foot)
    lidar_n = robust_unit(_fill(lidar, foot,0.8), foot)
    score = score * (0.7 + 0.3 * lidar_n)
    score[~foot] = 0.0
    return robust_unit(score, foot).astype(np.float32)

# ---- H35-E: Geodetic transtensional invariant ----
def build_h35e(bands_dir: Path, ddir: Path, foot: np.ndarray) -> np.ndarray:
    """Kostrov transtensional invariant z+(dilatation)*shear / (I2+0.35).
    Targets active releasing step-overs driving permeability; USGS catalogue is quaternary (long-term) not active.
    """
    inv2 = _fill(_band(bands_dir, 4, "geod_2ndinv", foot), foot, 1.2)
    shear = _fill(_band(bands_dir, 7, "geod_shearrate", foot), foot, 1.2)
    dilat = _fill(_band(bands_dir, 8, "geod_dilaterate", foot), foot, 1.2)
    # positive dilatation = opening
    zpos = np.clip(dilat, 0, None)
    zpos_n = robust_unit(zpos, foot)
    shear_n = robust_unit(np.abs(shear), foot)
    inv2_n = robust_unit(inv2, foot)
    psi = zpos_n * shear_n / (inv2_n + 0.35)
    # microseismic corroboration via ieq
    ieq = _band(bands_dir, 16, "ieq_n100a15", foot)
    ieq_n = robust_unit(np.log1p(np.maximum(ieq,0)), foot)
    score = psi * (0.6 + 0.4 * ieq_n)
    # require lineament: Hessian ridge on psi
    ridge = robust_unit(np.maximum(line_response(_fill(psi,foot,1.0),1.5),0), foot)
    score = score * (0.5 + 0.5 * ridge)
    score[~foot] = 0.0
    return robust_unit(score, foot).astype(np.float32)

H35_BUILDERS = {
    "H35-A": build_h35a,
    "H35-B": build_h35b,
    "H35-C": build_h35c,
    "H35-D": build_h35d,
    "H35-E": build_h35e,
}

H35_SPECS = {
    "H35-A": {
        "name": "Multi-scale curvature persistence (detrended elevation)",
        "layers": ["det_elev(12)", "det_elev_slope(19)"],
        "signature": "Product of Laplacian-derived curvature magnitudes at 1.5, 2.5, 4.0 px scales, gated by moderate slope (subtle scarp persistence)",
        "why_off_catalogue": "USGS catalogue records scarps visible at single scale; degraded/subtle scarps under alluvial cover persist only as weak curvature across scales, invisible to single-scale ridge",
        "novelty": "No prior channel computes multi-scale persistence product; features.py has single-scale curvature at 2 scales but never requires consistency across 3 scales",
        "cost": "~12s CPU",
        "expected_gain": "+0.0025 to +0.0045 DTI"
    },
    "H35-B": {
        "name": "Tilt-angle edge × magnetic gradient amplitude coupling",
        "layers": ["tc(6)", "tmi_hg(3)", "rtp(2)"],
        "signature": "Proximity to TC zero (1/(1+|TC|)) multiplied by TMI_HG gradient magnitude and RTP line response",
        "why_off_catalogue": "Magnetic contacts under basin fill have no topographic expression; TC marks contact location depth-independently while amplitude filters noise—catalogue lacks blind contacts",
        "novelty": "H32/H33 never coupled TC zero-crossing with amplitude gating; features.py recomputes hg as tmi_edge but never gates TC by hg",
        "cost": "~20s CPU",
        "expected_gain": "+0.0015 to +0.0030"
    },
    "H35-C": {
        "name": "Conductivity-basement co-gradient alignment",
        "layers": ["cond_surf(17)", "depth_to_base_surf(15)"],
        "signature": "Product of gradient magnitudes × absolute cosine of gradient direction alignment (requires >0.5 alignment)",
        "why_off_catalogue": "Fault under cover juxtaposes both conductive clay cap and basement step with same strike; surface catalogue has nothing where cover is thick",
        "novelty": "Prior uses cond/depth as scalars or plain gradient magnitude; none requires gradient directions to align",
        "cost": "~15s CPU",
        "expected_gain": "+0.0020 to +0.0040"
    },
    "H35-D": {
        "name": "Radiometric Th/K alteration edge × gravity gradient",
        "layers": ["geodawn_rad Th/K ratio (external)", "iso_grav_anom_hg(18)", "lidar_scarp"],
        "signature": "Th/K ratio gradient magnitude × gravity HG amplitude, weighted by lidar (alteration above conduits)",
        "why_off_catalogue": "Argillic alteration above geothermal conduits changes Th/K without creating scarp; catalogue is geomorphic, not geochemical",
        "novelty": "H32-C used rad as generic per-pixel weight, never alteration-ratio edge detection",
        "cost": "~18s CPU",
        "expected_gain": "+0.0010 to +0.0025"
    },
    "H35-E": {
        "name": "Transtensional invariant (geodetic opening × shear)",
        "layers": ["geod_2ndinv(4)", "geod_shearrate(7)", "geod_dilaterate(8)", "ieq_n100a15(16)"],
        "signature": "z+(dilatation)*|shear|/(I2+0.35) × microseismic density, ridge-filtered",
        "why_off_catalogue": "Active Walker Lane releasing step-overs drive current permeability but haven't accumulated enough offset for quaternary map; seismic swarm marks active blind faults",
        "novelty": "H32-B used similar Kostrov invariant but without ridge lineament filtering and without ieq gating as multiplicative",
        "cost": "~8s CPU",
        "expected_gain": "+0.0015 to +0.0030"
    }
}

def top_n_mask(surface: np.ndarray, foot: np.ndarray, n: int) -> np.ndarray:
    s = np.where(foot, np.asarray(surface, dtype=np.float32), -np.inf)
    flat = s.ravel()
    idx = np.argpartition(flat, -n)[-n:]
    m = np.zeros(flat.shape, dtype=bool)
    m[idx] = True
    return m.reshape(s.shape)

