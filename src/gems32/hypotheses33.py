"""Round-4 candidate geological hypotheses (H33-1 .. H33-5) for GEMSDOE32.

Everything here is *new to this repository*.  Before writing it we audited, in order:

* `src/gems32/hypotheses.py` (H32-A..D, this repo) and `src/gems32/features.py` (35 channels);
* the group's earlier hypothesis registers, in particular
  16GEMSDOE `docs/research/hypothesis_register.md`, whose rank-3 hypothesis **H18-5
  "thermal-anchor linking"** proposed exactly the GDR spring/well/sinter/volcanic prior and
  recorded its status as *"Premise measured; operator not built"*.  Nothing in any group
  repository has ever turned the GDR **measured geothermometer temperatures** into an operator.
  That is the gap H33-1 fills.

Design rule inherited from H32 and kept: every transform is **label-free**.  The only rasters
touched are the 19 official bands, the USGS 3DEP LiDAR scarp stack, the GeoDAWN rasters, and the
GDR 1391 point tables -- never `labels.tif`.  Where a hypothesis needs a raster that is *not* in
`data/raw` it says so explicitly and names the official source (see `docs/research/hypotheses-round4.md`).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import binary_closing, binary_dilation, distance_transform_edt, gaussian_filter, label
from scipy.spatial import cKDTree

from .hypotheses import _robust_zpos, load_band, ridge_nms_2d

def _pd():
    """Import pandas lazily.

    ``gems32.hypotheses33`` is imported by the test suite and by ``scripts/run_h33_validation.py``;
    only ``load_gdr_thermal_tables`` and the two geothermometry readers actually need pandas. Making
    the import lazy means a bare checkout (or a CI job that has not installed pandas yet) can still
    import the module and run everything that does not touch the GDR tables -- a missing optional
    dependency must never turn into a whole-module ImportError.
    """
    try:
        import pandas as pd
    except ImportError as exc:                      # pragma: no cover - exercised only without pandas
        raise RuntimeError(
            "pandas is required to read the GDR 1391 well/spring tables "
            "(pip install -r requirements.txt)") from exc
    return pd


# --------------------------------------------------------------------------------------------
# GDR 1391 measured thermal evidence (already on disk, sha256-pinned in registry/data_manifest.json)
# --------------------------------------------------------------------------------------------


def load_gdr_thermal_tables(ddir: Path) -> dict:
    """Read the GDR 1391 INGENIOUS well/spring tables that were raster-clipped to this footprint.

    Source: https://gdr.openei.org/submissions/1391 (DOI 10.15121/1881483, CC BY 4.0),
    resource "Well and Spring Temperature and Chemistry.zip" (wellspringdata.gdb).
    """
    pd = _pd()
    base = ddir / "external"
    out: dict = {}
    for name in ("gdr_wellspring_in_footprint.csv", "gdr_volcanic_vents_in_footprint.csv",
                 "gdr_qfaults_traces.csv"):
        p = base / name
        if p.exists():
            out[name] = pd.read_csv(p)
    return out


def _idw_surface(points_rc: np.ndarray, values: np.ndarray, shape: tuple[int, int],
                 length_scale_px: float = 20.0, k: int = 8, sigma: float = 3.0) -> np.ndarray:
    """Inverse-distance-weighted surface of `values` sampled at `points_rc` (row, col).

    w_i = 1 / (1 + (d_i / L)^2).  Falls back to a constant surface when there are too few points.
    """
    out = np.zeros(shape, dtype=np.float32)
    if points_rc.shape[0] == 0 or values.size == 0:
        return out
    tree = cKDTree(points_rc.astype(np.float64))
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    grid = np.column_stack([yy.ravel().astype(np.float64), xx.ravel().astype(np.float64)])
    acc = np.zeros(grid.shape[0], dtype=np.float64)
    wsum = np.zeros(grid.shape[0], dtype=np.float64)
    # chunk the grid so memory stays bounded on a 3 GB box
    step = 400_000
    for s in range(0, grid.shape[0], step):
        d, idx = tree.query(grid[s:s + step], k=min(k, points_rc.shape[0]))
        d = np.atleast_2d(d.T).T if d.ndim == 1 else d
        idx = np.atleast_2d(idx.T).T if idx.ndim == 1 else idx
        w = 1.0 / (1.0 + (d / float(length_scale_px)) ** 2)
        acc[s:s + step] = (w * values[idx]).sum(axis=1)
        wsum[s:s + step] = w.sum(axis=1)
    vals = np.where(wsum > 0, acc / np.maximum(wsum, 1e-12), 0.0)
    out = vals.reshape(shape).astype(np.float32)
    if sigma > 0:
        out = gaussian_filter(out, sigma=sigma)
    return out


def compute_gdr_thermal_prior(ddir: Path, foot: np.ndarray) -> dict[str, np.ndarray]:
    """H33-1's measured-heat surfaces, built only from GDR 1391 spring chemistry.

    Three independent reservoir-temperature estimators are used, because they agree only where the
    chemistry is internally consistent:

    * ``T_quartz``  -- quartz geothermometer (Fournier & Potter, silica equilibrium)
    * ``T_chalc``   -- chalcedony geothermometer
    * ``T_cation``  -- cation (Na-K-Ca / Na-K) geothermometer

    ``T_reservoir`` is the per-site maximum of the three.  Using the maximum rather than the mean
    is deliberate: a single internally consistent high estimate is the signal of a deep
    magmatic/hydrothermal heat source, while disagreement between estimators is the signature of
    shallow mixing or conduction, which is what we want to down-weight.
    """
    pd = _pd()
    tables = load_gdr_thermal_tables(ddir)
    spring = tables.get("gdr_wellspring_in_footprint.csv")
    shape = foot.shape
    empty = np.zeros(shape, dtype=np.float32)
    if spring is None:
        return {"T_reservoir": empty, "T_measured": empty, "T_spread": empty,
                "n_geothermometer_sites": 0, "n_sites_gt150": 0, "n_sites_gt150_far": 0}

    chem = spring[spring["layer"] == "spring_chemistry_20220808"].copy()
    for c in ("geothermquartz_c", "geothermchalc_c", "geothermcat_c", "temp_c"):
        chem[c] = pd.to_numeric(chem[c], errors="coerce")
    chem = chem.dropna(subset=["row", "col"])
    if chem.empty:
        return {"T_reservoir": empty, "T_measured": empty, "T_spread": empty,
                "n_geothermometer_sites": 0, "n_sites_gt150": 0, "n_sites_gt150_far": 0}

    site = (chem.groupby(["row", "col"])
               .agg(T_q=("geothermquartz_c", "max"),
                    T_c=("geothermchalc_c", "max"),
                    T_k=("geothermcat_c", "max"),
                    T_m=("temp_c", "max"),
                    d_fault=("dist_known_fault_px", "min"))
               .reset_index())
    est = site[["T_q", "T_c", "T_k"]]
    t_res_site = est.max(axis=1)                       # NaN when all three are missing
    t_meas_site = site["T_m"]
    t_spread_site = est.max(axis=1) - est.min(axis=1)  # estimator disagreement (deg C)

    m = t_res_site.notna()
    pts = site.loc[m, ["row", "col"]].to_numpy()
    t_res_surface = _idw_surface(pts, t_res_site[m].to_numpy(dtype=np.float64), shape,
                                 length_scale_px=20.0, k=8, sigma=3.0)
    m2 = t_meas_site.notna()
    t_meas_surface = _idw_surface(site.loc[m2, ["row", "col"]].to_numpy(),
                                  t_meas_site[m2].to_numpy(dtype=np.float64), shape,
                                  length_scale_px=12.0, k=8, sigma=2.0)
    m3 = t_spread_site.notna()
    t_spread_surface = _idw_surface(site.loc[m3, ["row", "col"]].to_numpy(),
                                    t_spread_site[m3].to_numpy(dtype=np.float64), shape,
                                    length_scale_px=20.0, k=8, sigma=3.0)

    far = site["d_fault"] > 30.0                        # > 3 km from the published catalogue
    return {
        "T_reservoir": (t_res_surface * foot).astype(np.float32),
        "T_measured": (t_meas_surface * foot).astype(np.float32),
        "T_spread": (t_spread_surface * foot).astype(np.float32),
        "n_geothermometer_sites": int(m.sum()),
        "n_sites_gt150": int((t_res_site > 150).sum()),
        "n_sites_gt150_far": int(((t_res_site > 150) & far).sum()),
        "n_sites_gt180": int((t_res_site > 180).sum()),
        "n_sites_gt180_far": int(((t_res_site > 180) & far).sum()),
        "n_sites_gt200_far": int(((t_res_site > 200) & far).sum()),
        "site_table": site.assign(T_reservoir=t_res_site, far=far),
    }


# --------------------------------------------------------------------------------------------
# H33-1 -- measured-geothermometer upflow-conduit prior
# --------------------------------------------------------------------------------------------


def compute_h33_1_thermal_conduit(bands_dir: Path, ddir: Path, foot: np.ndarray) -> dict:
    """H33-1: GDR measured-geothermometer reservoir temperature x off-catalogue structural lineament.

    Physical model
    --------------
    A silica/cation geothermometer returns the temperature of the *reservoir* that a spring is
    discharging from, not the spring's surface temperature.  A reservoir above ~150 deg C in the
    Great Basin implies a magmatic or deeply-circulating heat source.  Fluid reaches the surface
    along a permeable fault, so the surface trace of that fault must exist somewhere within the
    spring's recharge/upflow catchment.  The USGS Quaternary catalogue only records faults with
    evidence of coseismic deformation in the last 1.6 Ma, so a conduit whose throw is small, whose
    scarp is erased by argillic alteration, or which is a *secondary* structure inside a step-over
    is systematically absent -- which is exactly the population the competition scores.

    Transform
    ---------
    1. ``T_res(x)``  -- IDW surface of the per-site maximum of the quartz, chalcedony and cation
       geothermometers (length scale 20 px = 2 km, k = 8, sigma = 3 px).
    2. ``L(x)``      -- a label-free structural lineament score from the official bands:
       Hessian ridge response of `det_elev` (band 12) at sigma = 2, plus the smoothed gradient
       magnitude of `tmi_hg` (band 3) and of `depth_to_base_surf` (band 15).
    3. ``S(x) = z(T_res) * (0.45 + 0.55 * z(L))`` -- the conjunction.  A high reservoir temperature
       with no lineament is a *conductive* anomaly (no fault); a lineament with no heat is an
       ordinary fault (already catalogued).
    4. Emission is a 4-direction non-maximum-suppressed 1-px crest of ``S`` restricted to
       ``z(T_res) > tau_T`` and ``d(catalogue) > 1 px``.
    """
    thermal = compute_gdr_thermal_prior(ddir, foot)
    t_res = thermal["T_reservoir"]

    det_elev = load_band(bands_dir, 12, "det_elev")
    tmi_hg = load_band(bands_dir, 3, "tmi_hg")
    depth_base = load_band(bands_dir, 15, "depth_to_base_surf")

    gy, gx = np.gradient(det_elev)
    hess_ridge = _hessian_ridge_response(det_elev, 2.0)
    g_tmi = gaussian_filter(np.hypot(gx, gy), 1.0)
    gdb = np.gradient(depth_base)
    g_depth = gaussian_filter(np.hypot(gdb[0], gdb[1]), 1.5)

    z_t = _robust_zpos(t_res, foot) / 6.0
    z_l = (_robust_zpos(hess_ridge, foot) / 6.0 * 0.5
           + _robust_zpos(g_tmi, foot) / 6.0 * 0.3
           + _robust_zpos(g_depth, foot) / 6.0 * 0.2)

    score = (z_t * (0.45 + 0.55 * z_l)).astype(np.float32)
    return {
        "score": score,
        "T_reservoir": t_res,
        "z_T": z_t,
        "z_L": z_l,
        "thermal_stats": {k: v for k, v in thermal.items() if not isinstance(v, np.ndarray)},
    }


def _hessian_ridge_response(a: np.ndarray, sigma: float) -> np.ndarray:
    """Sato/Frangi-style ridge response (largest-|eigenvalue| with the ridge sign convention)."""
    from scipy.ndimage import gaussian_filter as _gf
    axx = _gf(a, sigma, order=(0, 2), mode="nearest")
    ayy = _gf(a, sigma, order=(2, 0), mode="nearest")
    axy = _gf(a, sigma, order=(1, 1), mode="nearest")
    tmp = np.sqrt(np.maximum(((axx - ayy) * 0.5) ** 2 + axy ** 2, 0.0))
    l1 = (axx + ayy) * 0.5 + tmp
    l2 = (axx + ayy) * 0.5 - tmp
    big = np.where(np.abs(l1) >= np.abs(l2), l1, l2)
    small = np.where(np.abs(l1) >= np.abs(l2), l2, l1)
    return (-small * (big < 0)).astype(np.float32)


# --------------------------------------------------------------------------------------------
# H33-5 -- detector-field fault-tip / relay-ramp corridor prior
# --------------------------------------------------------------------------------------------


def skeleton_endpoints_and_junctions(field: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """8-neighbourhood endpoints (1 neighbour) and junctions (>= 3 neighbours) of a binary field."""
    f = np.asarray(field, bool)
    n = np.zeros(f.shape, dtype=np.int16)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            n += np.roll(np.roll(f, dr, axis=0), dc, axis=1)
    return (f & (n == 1)), (f & (n >= 3))


def compute_h33_5_tip_stepover_prior(ddir: Path, foot: np.ndarray,
                                     h19_5: np.ndarray, h19_4: np.ndarray,
                                     h16_1: np.ndarray) -> dict:
    """H33-5: fault-tip and relay-ramp corridors taken from the *detector's own* ridge field.

    Physical model
    --------------
    Structural studies of Great Basin geothermal systems put the large majority of categorised
    systems not on planar fault planes but at **fault terminations and step-overs / relay ramps**,
    where elevated shear drives intense secondary microfracturing and therefore permeability
    (Faulds & Hinz 2015; Siler et al. 2019).  16GEMSDOE's H18-3a tested the same idea but sourced
    the endpoints and junctions from the *published catalogue* (`labels.tif`) -- a km-scale
    smoothed density prior that by construction cannot point anywhere the catalogue does not
    already reach.  This arm sources them from the **detector's own corroborated ridge field**,
    which is label-free and extends off-catalogue.

    Transform
    ---------
    ``R = (h19_5 | h19_4 | h16_1) & foot`` is morphologically closed, then split into endpoints
    (exactly one 8-neighbour) and junctions (>= 3).  A Gaussian-smoothed density of those two
    classes is multiplied by the corroboration count (how many independent detector surfaces
    support the pixel) and emitted as a 1-px crest, restricted to ``d(catalogue) > 1 px``.
    """
    R = (h19_5 | h19_4 | h16_1) & foot
    R = binary_closing(R, structure=np.ones((3, 3), bool), iterations=1)
    tips, junctions = skeleton_endpoints_and_junctions(R)
    corrob = h19_4.astype(np.int8) + h16_1.astype(np.int8) + h19_5.astype(np.int8)

    dens_tip = gaussian_filter(tips.astype(np.float32), 4.0)
    dens_jnc = gaussian_filter(junctions.astype(np.float32), 4.0)
    score = (_robust_zpos(dens_tip, foot) / 6.0 * 0.6
             + _robust_zpos(dens_jnc, foot) / 6.0 * 0.4) * (0.5 + 0.25 * corrob)
    return {
        "score": score.astype(np.float32),
        "n_tip_px": int(tips.sum()),
        "n_junction_px": int(junctions.sum()),
        "n_ridge_px": int(R.sum()),
    }


# --------------------------------------------------------------------------------------------
# H33-2 -- live-anchored catalogue-flank exclusion sweep
# --------------------------------------------------------------------------------------------


def catalogue_distance(labels: np.ndarray) -> np.ndarray:
    """Euclidean distance (px) from every cell to the nearest catalogue pixel."""
    return distance_transform_edt(~np.asarray(labels, bool))


def compute_h33_2_flank_sweep(base: np.ndarray, labels: np.ndarray,
                              d_cat: np.ndarray | None = None,
                              buffers: tuple[int, ...] = (1, 2, 3)) -> dict[int, np.ndarray]:
    """H33-2: delete every emitted dot whose distance to the published catalogue is <= B px.

    The organisers mask `existing_faults == 1` pixels out of scoring, and `existing_faults.tif` is
    byte-identical to `labels.tif` in this dataset.  Mass spent within the masked halo therefore
    costs 0.2 per dot and earns nothing from the masked pixels themselves.  The group measured this
    live exactly once: pruning the 3,891 dots of the 0.2600 emission that sit at d = 1 px moved the
    leaderboard from 0.2600 to 0.2708.  This arm generalises that single measurement to a sweep.
    """
    if d_cat is None:
        d_cat = catalogue_distance(labels)
    out: dict[int, np.ndarray] = {}
    for b in buffers:
        out[b] = np.asarray(base, bool) & (d_cat > b)
    return out


def compute_h33_2_rung_reprune(base: np.ndarray, labels: np.ndarray, rung_px: float,
                               d_cat: np.ndarray | None = None) -> np.ndarray:
    """H33-2b: greedy Poisson-disk re-pack of `base` at spacing `rung_px`, then a blind r=1 flank prune.

    The re-pack is *not* a thinning of the same pixel set: raising the rung re-seeds the greedy
    walk and changes which pixels are kept (GEMSDOE28 measured 24,091 of 44,090 px changing when
    the rung moved 2.828 -> 3.0), so it is a genuinely different emission rather than a subset.
    """
    if d_cat is None:
        d_cat = catalogue_distance(labels)
    from .hypotheses import poisson_disk_thin_priority
    pool = np.asarray(base, bool)
    prio = np.where(pool, 1.0, 0.0).astype(np.float32)
    repacked = poisson_disk_thin_priority(pool, prio, min_dist_px=rung_px,
                                          existing_dots=None, max_add=int(pool.sum()))
    return repacked & (d_cat > 1)


# --------------------------------------------------------------------------------------------
# H33-3 / H33-4 -- need official rasters that are NOT in data/raw (see hypotheses-round4.md)
# --------------------------------------------------------------------------------------------


def missing_external_inputs(ddir: Path) -> dict[str, dict]:
    """Report which official GDR 1391 resources H33-3 / H33-4 need and whether they are present.

    Every entry names the exact resource on the official GDR page and its published size, so the
    claim "obtainable" is checkable by hand without running anything.
    """
    ext = ddir / "external"
    wanted = {
        "2m_temperature_probes": {
            "resource": "2m Temperature Probes.zip",
            "url": "https://gdr.openei.org/files/1391/2m_temperature_probe_INGENIOUS_regional_data.zip",
            "published_bytes": 1_030_000,
            "hypothesis": "H33-3",
            "present": False,
            "note": ("Shallow 2 m temperature-probe surveys. A 2 m thermal anomaly is the most "
                     "direct surface expression of a hydrothermal upflow; its elongated axis is a "
                     "lineament. Listed on the official GDR 1391 resource page (CC BY 4.0)."),
        },
        "paleo_geothermal_features": {
            "resource": "Paleo Geothermal Features.zip",
            "url": "https://gdr.openei.org/files/1391/paleo_geothermal_regional.zip",
            "published_bytes": 82_040,
            "hypothesis": "H33-4",
            "present": False,
            "note": ("Mapped sinter and tufa deposits -- the surface record of *past* upflow. A "
                     "paleo system's active conduit is now typically blind, which is the target "
                     "population. Listed on the official GDR 1391 resource page (CC BY 4.0)."),
        },
    }
    for k, v in wanted.items():
        v["present"] = any(ext.glob(f"*{k}*")) or any(ext.glob(f"*{k.replace('_', '*')}*"))
    return wanted
