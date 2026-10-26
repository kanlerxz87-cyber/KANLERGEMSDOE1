"""Novel Geological Hypotheses (H32-A, H32-B, H32-C, H32-D) for GEMSDOE32.

All feature transforms are 100% label-free (computed strictly from the 19 geophysical/geodetic/seismic/
topographic bands of training_features.tif plus the USGS 3DEP 1 m LiDAR scarp and USGS GeoDAWN radiometric
rasters), guaranteeing zero retrospective catalogue leakage on spatial holdouts.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import binary_dilation, distance_transform_edt, gaussian_filter, maximum_filter


def _robust_zpos(arr: np.ndarray, foot: np.ndarray) -> np.ndarray:
    """Robust non-negative z-score inside the footprint using median and IQR, clipped to [0, 6]."""
    out = np.zeros(arr.shape, dtype=np.float32)
    valid = foot & np.isfinite(arr)
    if not valid.any():
        return out
    vals = arr[valid]
    med = float(np.median(vals))
    q25, q75 = np.percentile(vals, [25.0, 75.0])
    iqr = max(float(q75 - q25), 1e-6)
    z = (arr - med) / (iqr / 1.349)
    out[valid] = np.clip(z[valid], 0.0, 6.0)
    return out


def _fill_smooth(arr: np.ndarray, foot: np.ndarray, sigma: float = 1.5) -> np.ndarray:
    """Fill NaNs with footprint median and apply Gaussian smoothing."""
    valid = foot & np.isfinite(arr)
    med = float(np.median(arr[valid])) if valid.any() else 0.0
    filled = np.where(valid, arr, med).astype(np.float32)
    if sigma > 0:
        return gaussian_filter(filled, sigma=sigma)
    return filled


def _sample_bilinear(field: np.ndarray, yy: np.ndarray, xx: np.ndarray) -> np.ndarray:
    """Fast vectorized bilinear interpolation on a 2D grid."""
    H, W = field.shape
    y = np.clip(yy, 0.0, H - 1.001)
    x = np.clip(xx, 0.0, W - 1.001)
    y0 = y.astype(np.int32)
    x0 = x0 = x.astype(np.int32)
    y1 = y0 + 1
    x1 = x0 + 1
    wy = y - y0
    wx = x - x0
    return (
        (1.0 - wy) * (1.0 - wx) * field[y0, x0]
        + (1.0 - wy) * wx * field[y0, x1]
        + wy * (1.0 - wx) * field[y1, x0]
        + wy * wx * field[y1, x1]
    ).astype(np.float32)


def ridge_nms_2d(score: np.ndarray, foot: np.ndarray) -> np.ndarray:
    """1-pixel oriented ridge crest extraction via 4-direction non-maximum suppression."""
    s = np.where(foot, score, -1e9).astype(np.float32)
    gy, gx = np.gradient(s)
    theta = (np.rad2deg(np.arctan2(gy, gx)) + 180.0) % 180.0
    p0 = np.roll(s, 1, axis=1)
    n0 = np.roll(s, -1, axis=1)
    p90 = np.roll(s, 1, axis=0)
    n90 = np.roll(s, -1, axis=0)
    p45 = np.roll(np.roll(s, 1, axis=0), 1, axis=1)
    n45 = np.roll(np.roll(s, -1, axis=0), -1, axis=1)
    p135 = np.roll(np.roll(s, 1, axis=0), -1, axis=1)
    n135 = np.roll(np.roll(s, -1, axis=0), 1, axis=1)
    b0 = (theta < 22.5) | (theta >= 157.5)
    b45 = (theta >= 22.5) & (theta < 67.5)
    b90 = (theta >= 67.5) & (theta < 112.5)
    b135 = (theta >= 112.5) & (theta < 157.5)
    is_max = (
        (b0 & (s >= p0) & (s > n0))
        | (b45 & (s >= p45) & (s > n45))
        | (b90 & (s >= p90) & (s > n90))
        | (b135 & (s >= p135) & (s > n135))
    )
    return is_max & foot


def load_band(bands_dir: Path, idx: int, name: str) -> np.ndarray:
    return np.load(bands_dir / f"{idx:02d}_{name}.npy")


def load_lidar_scarp_ridge(ddir: Path, foot: np.ndarray) -> np.ndarray:
    """Load USGS 3DEP 1m DEM derived scarp amplitude & orientation coherence composite."""
    p = ddir / "external" / "lidar_scarp_features_u8.tif"
    if not p.exists():
        return np.zeros(foot.shape, dtype=np.float32)
    with rasterio.open(p) as src:
        b1 = src.read(1).astype(np.float32) / 255.0
        b2 = src.read(2).astype(np.float32) / 255.0
        b5 = src.read(5).astype(np.float32) / 255.0 if src.count >= 5 else b1
    comp = (0.45 * b1 + 0.35 * b2 + 0.20 * b5) * foot.astype(np.float32)
    return _robust_zpos(comp, foot) / 6.0


def compute_h32a_dip_projected_step(bands_dir: Path, ddir: Path, foot: np.ndarray) -> np.ndarray:
    """Hypothesis 1 (H32-A): Dip-Projected Subsurface-to-Surface Fault Trace De-Aliasing & Step Asymmetry.

    Targets concealed normal faults dipping at 45-60 deg beneath basin fill where the gravity/magnetic
    gradient peak (`iso_grav_anom_hg`, `tmi_hg`) is shifted down-dip (basin-ward) by 150-350 m relative
    to the surface fault trace. Decomposes cross-strike potential-field profiles into Odd (step) vs Even
    (symmetric intrusion/ridge) components and back-projects the odd step up-dip toward the footwall
    range front / MT conductive boundary.
    """
    iso_g = _fill_smooth(load_band(bands_dir, 13, "iso_grav_anom"), foot, sigma=1.5)
    iso_hg = _robust_zpos(load_band(bands_dir, 18, "iso_grav_anom_hg"), foot)
    rtp = _fill_smooth(load_band(bands_dir, 2, "rtp"), foot, sigma=1.5)
    tmi_hg = _robust_zpos(load_band(bands_dir, 3, "tmi_hg"), foot)
    d_base = _fill_smooth(load_band(bands_dir, 15, "depth_to_base_surf"), foot, sigma=2.0)
    cond = _robust_zpos(load_band(bands_dir, 17, "cond_surf"), foot)
    elev = _fill_smooth(load_band(bands_dir, 12, "det_elev"), foot, sigma=1.5)
    elev_sl = _robust_zpos(load_band(bands_dir, 19, "det_elev_slope"), foot)
    lidar = load_lidar_scarp_ridge(ddir, foot)

    gy_g, gx_g = np.gradient(gaussian_filter(iso_g, sigma=2.0))
    ng = np.hypot(gy_g, gx_g) + 1e-6
    gy_z, gx_z = np.gradient(gaussian_filter(elev, sigma=2.0))
    nz = np.hypot(gy_z, gx_z) + 1e-6
    gy_b, gx_b = np.gradient(gaussian_filter(d_base, sigma=2.5))
    nb = np.hypot(gy_b, gx_b) + 1e-6

    uy = 0.50 * (gy_g / ng) + 0.30 * (gy_z / nz) - 0.20 * (gy_b / nb)
    ux = 0.50 * (gx_g / ng) + 0.30 * (gx_z / nz) - 0.20 * (gx_b / nb)
    unorm = np.hypot(uy, ux) + 1e-6
    uy = (uy / unorm).astype(np.float32)
    ux = (ux / unorm).astype(np.float32)

    H, W = foot.shape
    grid_y, grid_x = np.meshgrid(np.arange(H, dtype=np.float32), np.arange(W, dtype=np.float32), indexing="ij")

    s = 2.5
    g_plus = _sample_bilinear(iso_g, grid_y + s * uy, grid_x + s * ux)
    g_minus = _sample_bilinear(iso_g, grid_y - s * uy, grid_x - s * ux)
    odd_g = 0.5 * np.abs(g_plus - g_minus)
    even_g = 0.5 * np.abs(g_plus + g_minus - 2.0 * iso_g)

    r_plus = _sample_bilinear(rtp, grid_y + s * uy, grid_x + s * ux)
    r_minus = _sample_bilinear(rtp, grid_y - s * uy, grid_x - s * ux)
    odd_r = 0.5 * np.abs(r_plus - r_minus)
    even_r = 0.5 * np.abs(r_plus + r_minus - 2.0 * rtp)

    parity_g = odd_g / (odd_g + even_g + 1e-4)
    parity_r = odd_r / (odd_r + even_r + 1e-4)
    step_purity = (0.60 * parity_g + 0.40 * parity_r).astype(np.float32)

    sub_step = step_purity * (0.55 * (iso_hg / 6.0) + 0.45 * (tmi_hg / 6.0))

    z_norm = _robust_zpos(d_base, foot) / 6.0
    delta_s = np.clip(1.2 + 1.8 * z_norm, 1.2, 3.0).astype(np.float32)
    advected_step = _sample_bilinear(sub_step, grid_y - delta_s * uy, grid_x - delta_s * ux)

    surf_corrob = 0.45 * lidar + 0.35 * (elev_sl / 6.0) + 0.20 * (cond / 6.0)
    score = (0.55 * advected_step + 0.25 * sub_step + 0.20 * surf_corrob) * (0.50 + 0.50 * surf_corrob)
    score[~foot] = 0.0
    return (_robust_zpos(score, foot) / 6.0).astype(np.float32)


def compute_h32b_transtensional_swarm_tensor(bands_dir: Path, ddir: Path, foot: np.ndarray) -> np.ndarray:
    """Hypothesis 2 (H32-B): Geodetic Kostrov Transtensional Coupling & Microseismic Swarm Permeability Tensor.

    Targets active Walker Lane / Great Basin releasing steps and unmapped transtensional fault splays where
    positive crust-thinning dilatation (`geod_dilaterate > 0`) couples with shear strain (`geod_shearrate`)
    and elevated swarm/dependent-to-independent microseismicity (`deq_n100a15` vs `ieq_n100a15`).
    """
    dil_raw = load_band(bands_dir, 8, "geod_dilaterate")
    valid = foot & np.isfinite(dil_raw)
    dil_pos = np.where(valid & (dil_raw > 0), dil_raw, 0.0).astype(np.float32)
    z_dil = _robust_zpos(dil_pos, foot) / 6.0
    z_shear = _robust_zpos(load_band(bands_dir, 7, "geod_shearrate"), foot) / 6.0
    z_inv2 = _robust_zpos(load_band(bands_dir, 4, "geod_2ndinv"), foot) / 6.0

    psi_transt = (z_dil * z_shear) / (z_inv2 + 0.35)

    deq = np.maximum(_fill_smooth(load_band(bands_dir, 10, "deq_n100a15"), foot, sigma=1.0), 0.0)
    ieq = np.maximum(_fill_smooth(load_band(bands_dir, 16, "ieq_n100a15"), foot, sigma=1.0), 0.0)
    swarm_diff = np.log1p(deq) - 0.75 * np.log1p(ieq)
    gy_ieq, gx_ieq = np.gradient(gaussian_filter(ieq, sigma=2.0))
    ieq_grad = _robust_zpos(np.hypot(gy_ieq, gx_ieq), foot) / 6.0
    r_swarm = 0.65 * (_robust_zpos(swarm_diff, foot) / 6.0) + 0.35 * ieq_grad

    elev_sl = _robust_zpos(load_band(bands_dir, 19, "det_elev_slope"), foot) / 6.0
    tmi_hg = _robust_zpos(load_band(bands_dir, 3, "tmi_hg"), foot) / 6.0
    lidar = load_lidar_scarp_ridge(ddir, foot)

    struct_edge = 0.45 * lidar + 0.30 * elev_sl + 0.25 * tmi_hg
    score = (0.45 * psi_transt + 0.35 * r_swarm + 0.20 * struct_edge) * (0.40 + 0.60 * struct_edge)
    score[~foot] = 0.0
    return (_robust_zpos(score, foot) / 6.0).astype(np.float32)


def compute_h32c_mt_claycap_breach(bands_dir: Path, ddir: Path, foot: np.ndarray) -> np.ndarray:
    """Hypothesis 3 (H32-C): Magnetotelluric (MT) Conductive Clay-Cap Breaching & Basal Relief Strike Alignment.

    Targets blind hydrothermal upflow fault conduits where a steep lateral step in `depth_to_base_surf`
    strikes parallel to the local structural/magnetic lineament and coincides with elevated surface
    electrical conductivity (`cond_surf`) and radiometric alteration gradients (`tc`, GeoDAWN Th/K & U/K).
    """
    d_base = _fill_smooth(load_band(bands_dir, 15, "depth_to_base_surf"), foot, sigma=2.0)
    cond = _robust_zpos(load_band(bands_dir, 17, "cond_surf"), foot) / 6.0
    tc = _fill_smooth(load_band(bands_dir, 6, "tc"), foot, sigma=1.5)
    rtp = _fill_smooth(load_band(bands_dir, 2, "rtp"), foot, sigma=1.5)
    elev = _fill_smooth(load_band(bands_dir, 12, "det_elev"), foot, sigma=1.5)
    lidar = load_lidar_scarp_ridge(ddir, foot)

    gy_b, gx_b = np.gradient(d_base)
    grad_b_mag = _robust_zpos(np.hypot(gy_b, gx_b), foot) / 6.0

    gy_s, gx_s = np.gradient(0.6 * elev + 0.4 * rtp)
    dot = gy_b * gy_s + gx_b * gx_s
    norms = (np.hypot(gy_b, gx_b) * np.hypot(gy_s, gx_s)) + 1e-6
    cos2_align = np.square(dot / norms).astype(np.float32)

    gy_tc, gx_tc = np.gradient(tc)
    tc_edge = _robust_zpos(np.hypot(gy_tc, gx_tc), foot) / 6.0

    rad_ext_path = ddir / "external" / "geodawn_extensions_u8.tif"
    if rad_ext_path.exists():
        with rasterio.open(rad_ext_path) as src:
            th_k = src.read(1).astype(np.float32)
            u_k = src.read(2).astype(np.float32)
        gy_tk, gx_tk = np.gradient(gaussian_filter(th_k, sigma=1.5))
        gy_uk, gx_uk = np.gradient(gaussian_filter(u_k, sigma=1.5))
        rad_ratio_edge = 0.5 * (_robust_zpos(np.hypot(gy_tk, gx_tk), foot) / 6.0) + 0.5 * (
            _robust_zpos(np.hypot(gy_uk, gx_uk), foot) / 6.0
        )
    else:
        rad_ratio_edge = tc_edge

    alteration = 0.50 * cond + 0.25 * tc_edge + 0.25 * rad_ratio_edge
    score = (0.45 * grad_b_mag * cos2_align + 0.35 * alteration + 0.20 * lidar) * (0.45 + 0.55 * lidar)
    score[~foot] = 0.0
    return (_robust_zpos(score, foot) / 6.0).astype(np.float32)


def poisson_disk_thin_priority(
    candidates_mask: np.ndarray,
    priority: np.ndarray,
    min_dist_px: float = 2.8,
    existing_dots: np.ndarray | None = None,
    max_add: int | None = None,
) -> np.ndarray:
    """Greedy priority-ordered Poisson-disk selector enforcing Euclidean distance >= min_dist_px."""
    H, W = candidates_mask.shape
    selected = np.zeros((H, W), dtype=bool)
    blocked = np.zeros((H, W), dtype=bool)

    r_int = int(np.ceil(min_dist_px))
    dy_grid, dx_grid = np.mgrid[-r_int : r_int + 1, -r_int : r_int + 1]
    disk_offs = np.argwhere((dy_grid * dy_grid + dx_grid * dx_grid) < (min_dist_px * min_dist_px - 1e-6)) - r_int

    if existing_dots is not None and existing_dots.any():
        dist_ex = distance_transform_edt(~existing_dots)
        blocked |= dist_ex < (min_dist_px - 1e-6)

    elig = candidates_mask & ~blocked
    yy, xx = np.nonzero(elig)
    if yy.size == 0:
        return selected

    scores = priority[yy, xx]
    order = np.argsort(-scores, kind="mergesort")
    yy = yy[order]
    xx = xx[order]

    added = 0
    dy_off = disk_offs[:, 0]
    dx_off = disk_offs[:, 1]
    for r, c in zip(yy, xx):
        if blocked[r, c]:
            continue
        selected[r, c] = True
        added += 1
        if max_add is not None and added >= max_add:
            break
        nr = r + dy_off
        nc = c + dx_off
        ok = (nr >= 0) & (nr < H) & (nc >= 0) & (nc < W)
        blocked[nr[ok], nc[ok]] = True

    return selected


def build_h32_suite(
    bands_dir: Path,
    ddir: Path,
    foot: np.ndarray,
    labels: np.ndarray,
    d28: np.ndarray,
    d15: np.ndarray,
    h19_5: np.ndarray,
    h19_4: np.ndarray,
    h16_1: np.ndarray,
    tgc: np.ndarray,
    ens12: np.ndarray,
) -> dict[str, dict]:
    """Compute all H32 surfaces and construct the candidate suite (both wholesale dotting ablations and
    surgical prune-and-augment candidates H32-A, H32-B, H32-C, H32-D-Eq44090, and H32-D)."""
    h32a = compute_h32a_dip_projected_step(bands_dir, ddir, foot)
    h32b = compute_h32b_transtensional_swarm_tensor(bands_dir, ddir, foot)
    h32c = compute_h32c_mt_claycap_breach(bands_dir, ddir, foot)
    lidar = load_lidar_scarp_ridge(ddir, foot)

    corrob_count = h19_4.astype(int) + h16_1.astype(int) + tgc.astype(int) + d15.astype(int) + ens12.astype(int)
    ridge_a = ridge_nms_2d(h32a, foot) & (h32a > np.quantile(h32a[foot], 0.90)) & foot & ~labels
    ridge_b = ridge_nms_2d(h32b, foot) & (h32b > np.quantile(h32b[foot], 0.90)) & foot & ~labels
    ridge_c = ridge_nms_2d(h32c, foot) & (h32c > np.quantile(h32c[foot], 0.90)) & foot & ~labels

    cand_base = (h19_5 | h19_4 | h16_1 | tgc | ens12 | (lidar > 0.35)) & foot & ~labels
    cand_ridges_only = (h19_5 | h19_4 | h16_1 | tgc) & foot & ~labels
    p_h32d = (0.35 * h32a + 0.40 * h32b + 0.25 * h32c).astype(np.float32)

    weak_d28 = d28 & (h19_4 == 0) & (h16_1 == 0) & (ens12 == 0) & (lidar < 0.05)
    wy, wx = np.nonzero(weak_d28)
    base_mult = (
        1.0
        + 0.45 * corrob_count.astype(np.float32)
        + 0.70 * ens12.astype(np.float32)
        + 0.50 * d15.astype(np.float32)
        + 0.35 * lidar
    )

    suite: dict[str, dict] = {}

    # 1. Wholesale dotting ablations on H19-5 (demonstrating why wholesale replacement loses multi-line recall)
    off_cat_halo = foot & ~binary_dilation(labels, iterations=1)
    for w_id, surf, desc in [
        ("H32-A-Wholesale", h32a, "Wholesale score-ordered dotting of H19-5 by H32-A (ablation: no D2.8 anchor)"),
        ("H32-B-Wholesale", h32b, "Wholesale score-ordered dotting of H19-5 by H32-B (ablation: no D2.8 anchor)"),
        ("H32-C-Wholesale", h32c, "Wholesale score-ordered dotting of H19-5 by H32-C (ablation: no D2.8 anchor)"),
    ]:
        m_w = poisson_disk_thin_priority(
            candidates_mask=(h19_5 | ridge_nms_2d(surf, foot)) & off_cat_halo,
            priority=surf + 0.35 * h19_5.astype(np.float32),
            min_dist_px=2.5,
            existing_dots=None,
            max_add=44850,
        )
        suite[w_id] = {
            "mask": m_w & foot & ~labels,
            "surface": surf,
            "description": desc,
            "prune_count": 44090,
            "add_count": int(m_w.sum()),
            "min_dist_px": 2.5,
        }

    # 2. H32-A: Dip-Projected Step Asymmetry Prune-and-Augment (p=500, a=2500 -> 46,090 dots)
    ret_a = d28.copy()
    ord_a = np.argsort(h32a[wy, wx])
    ret_a[wy[ord_a[:500]], wx[ord_a[:500]]] = False
    add_a = poisson_disk_thin_priority(
        (cand_base | ridge_a) & ~ret_a,
        h32a * base_mult,
        min_dist_px=2.35,
        existing_dots=ret_a,
        max_add=2500,
    )
    suite["H32-A"] = {
        "mask": (ret_a | add_a) & foot & ~labels,
        "surface": h32a,
        "description": "H32-A Dip-Projected Subsurface-to-Surface Fault Step Asymmetry (prune 500, add 2500)",
        "prune_count": 500,
        "add_count": int(add_a.sum()),
        "min_dist_px": 2.35,
    }

    # 3. H32-B: Geodetic Kostrov Transtensional & Microseismic Swarm Tensor (p=400, a=2200 -> 45,890 dots)
    ret_b = d28.copy()
    ord_b = np.argsort(h32b[wy, wx])
    ret_b[wy[ord_b[:400]], wx[ord_b[:400]]] = False
    corrob_r = h19_4.astype(int) + h16_1.astype(int) + tgc.astype(int) + d15.astype(int)
    prio_b1 = h32b * (1.0 + 0.45 * corrob_r.astype(np.float32) + 0.50 * d15.astype(np.float32) + 0.35 * lidar)
    add_b1 = poisson_disk_thin_priority(
        cand_ridges_only & ~ret_b, prio_b1, min_dist_px=2.35, existing_dots=ret_b, max_add=1400
    )
    ret_b2 = ret_b | add_b1
    add_b2 = poisson_disk_thin_priority(
        ((ens12 | ridge_b) & foot & ~labels) & ~ret_b2,
        h32b * (1.0 + 0.35 * lidar),
        min_dist_px=2.35,
        existing_dots=ret_b2,
        max_add=800,
    )
    suite["H32-B"] = {
        "mask": (ret_b2 | add_b2) & foot & ~labels,
        "surface": h32b,
        "description": "H32-B Kostrov Transtensional Strain & Microseismic Swarm Tensor (prune 400, add 2200)",
        "prune_count": 400,
        "add_count": int(add_b1.sum() + add_b2.sum()),
        "min_dist_px": 2.35,
    }

    # 4. H32-C: Magnetotelluric (MT) Conductive Clay-Cap Breach & Strike Alignment (p=400, a=2200 -> 45,890 dots)
    ret_c = d28.copy()
    ord_c = np.argsort(h32c[wy, wx])
    ret_c[wy[ord_c[:400]], wx[ord_c[:400]]] = False
    add_c = poisson_disk_thin_priority(
        (cand_base | ridge_c) & ~ret_c,
        h32c * base_mult,
        min_dist_px=2.35,
        existing_dots=ret_c,
        max_add=2200,
    )
    suite["H32-C"] = {
        "mask": (ret_c | add_c) & foot & ~labels,
        "surface": h32c,
        "description": "H32-C MT Conductive Clay-Cap Breach & Basal Relief Strike Alignment (prune 400, add 2200)",
        "prune_count": 400,
        "add_count": int(add_c.sum()),
        "min_dist_px": 2.35,
    }

    # 5. H32-D-Eq44090: Equal-Budget (44,090 dots) Stratified Submodular Prune-and-Augment (p=1200, a=1200)
    ord_d = np.argsort(p_h32d[wy, wx])
    ret_eq = d28.copy()
    ret_eq[wy[ord_d[:1200]], wx[ord_d[:1200]]] = False
    eq_b = poisson_disk_thin_priority(
        (cand_base | ridge_b) & ~ret_eq, h32b * base_mult, min_dist_px=2.35, existing_dots=ret_eq, max_add=500
    )
    ret_eq = ret_eq | eq_b
    eq_c = poisson_disk_thin_priority(
        (cand_base | ridge_c) & ~ret_eq, h32c * base_mult, min_dist_px=2.35, existing_dots=ret_eq, max_add=400
    )
    ret_eq = ret_eq | eq_c
    eq_a = poisson_disk_thin_priority(
        (cand_base | ridge_a) & ~ret_eq, h32a * base_mult, min_dist_px=2.35, existing_dots=ret_eq, max_add=300
    )
    suite["H32-D-Eq44090"] = {
        "mask": (ret_eq | eq_a) & foot & ~labels,
        "surface": p_h32d,
        "description": "H32-D Equal-Budget (44,090 dots) Submodular Prune-and-Augment (prune 1200, add 1200)",
        "prune_count": 1200,
        "add_count": int(eq_b.sum() + eq_c.sum() + eq_a.sum()),
        "min_dist_px": 2.35,
    }

    # 6. H32-D: Top-Ranked Stratified Submodular Multi-Physics Prune-and-Augment (p=500, a=2500 -> 46,090 dots)
    ret_d = d28.copy()
    ret_d[wy[ord_d[:500]], wx[ord_d[:500]]] = False
    d_b = poisson_disk_thin_priority(
        (cand_base | ridge_b) & ~ret_d, h32b * base_mult, min_dist_px=2.35, existing_dots=ret_d, max_add=1100
    )
    ret_d = ret_d | d_b
    d_c = poisson_disk_thin_priority(
        (cand_base | ridge_c) & ~ret_d, h32c * base_mult, min_dist_px=2.35, existing_dots=ret_d, max_add=800
    )
    ret_d = ret_d | d_c
    d_a = poisson_disk_thin_priority(
        (cand_base | ridge_a) & ~ret_d, h32a * base_mult, min_dist_px=2.35, existing_dots=ret_d, max_add=600
    )
    suite["H32-D"] = {
        "mask": (ret_d | d_a) & foot & ~labels,
        "surface": p_h32d,
        "description": "H32-D Submodular Multi-Physics Prune-and-Augment (prune 500, add 1100 H32-B + 800 H32-C + 600 H32-A)",
        "prune_count": 500,
        "add_count": int(d_b.sum() + d_c.sum() + d_a.sum()),
        "min_dist_px": 2.35,
    }

    return suite
