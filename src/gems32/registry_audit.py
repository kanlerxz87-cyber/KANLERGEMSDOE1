"""Exact, literal focus-registry duplicate checks for pre-placement surfaces and final dots."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import binary_dilation
from scipy.stats import rankdata


def _normalised_ranks(values: np.ndarray) -> np.ndarray:
    r = rankdata(values, method="average").astype(np.float64)
    r -= r.mean()
    norm = float(np.linalg.norm(r))
    if norm <= 0.0:
        raise ValueError("constant values have undefined ranks")
    r /= norm
    return r


def _rho_rank_z_vs_binary(rank_z: np.ndarray, binary: np.ndarray) -> float | None:
    b = np.asarray(binary, bool)
    n1 = int(b.sum())
    n = int(b.size)
    if n1 == 0 or n1 == n:
        return None
    # rank_z has zero mean and unit norm. The centred binary norm is sqrt(n*p*(1-p)).
    denom = float(np.sqrt(n * (n1 / n) * (1.0 - n1 / n)))
    return float(rank_z[b].sum() / denom)


def _phi_binary(a: np.ndarray, b: np.ndarray) -> float | None:
    av, bv = np.asarray(a, bool), np.asarray(b, bool)
    n11 = int((av & bv).sum())
    n10 = int((av & ~bv).sum())
    n01 = int((~av & bv).sum())
    n00 = int((~av & ~bv).sum())
    # Cast factors before multiplication: the exact contingency-table product can
    # exceed uint64 on the 5.17 M-pixel grid, which makes NumPy create an object
    # integer and then fail inside ``np.sqrt``.
    denom = float(np.sqrt(
        float(n11 + n10)
        * float(n01 + n00)
        * float(n11 + n01)
        * float(n10 + n00)
    ))
    return float((n11 * n00 - n10 * n01) / denom) if denom > 0.0 else None


def _load_registry_array(entry: dict, root: Path, template_profile: dict) -> tuple[np.ndarray | None, dict]:
    path = root / entry["local"]
    base = {
        "repo": entry.get("repo"),
        "path": entry.get("path"),
        "sha256": entry.get("sha256"),
        "local": entry.get("local"),
    }
    if not path.is_file():
        return None, base | {"status": "missing"}
    try:
        with rasterio.open(path) as ds:
            if (
                ds.count != 1
                or ds.shape != template_profile["shape"]
                or ds.crs != template_profile["crs"]
                or ds.transform != template_profile["transform"]
            ):
                return None, base | {
                    "status": "grid_mismatch",
                    "count": ds.count,
                    "shape": list(ds.shape),
                    "crs": str(ds.crs),
                    "transform": list(ds.transform)[:6],
                }
            return ds.read(1), base | {"status": "ok"}
    except Exception as exc:  # malformed registry files fail visibly, never silently disappear
        return None, base | {"status": "read_error", "error": f"{type(exc).__name__}: {exc}"}


def load_manifest(manifest_path: Path) -> dict:
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest.get("n_failed", 0) != 0:
        raise ValueError("focus registry manifest contains failed fetches")
    if not manifest.get("rasters"):
        raise ValueError("focus registry manifest contains no rasters")
    return manifest


def audit_surface(
    candidate_surface: np.ndarray,
    footprint: np.ndarray,
    manifest: dict,
    *,
    root: Path,
    template_tif: Path,
    max_abs_spearman: float = 0.90,
) -> dict:
    """Check exact full-footprint surface Spearman before dot placement."""
    surface = np.asarray(candidate_surface, np.float32)
    foot = np.asarray(footprint, bool)
    if surface.shape != foot.shape or not np.isfinite(surface[foot]).all():
        raise ValueError("candidate surface shape/nonfinite failure")
    candidate_rank_z = _normalised_ranks(surface[foot])
    with rasterio.open(template_tif) as tpl:
        template = {"shape": tpl.shape, "crs": tpl.crs, "transform": tpl.transform}

    rows = []
    cache: dict[str, dict] = {}
    malformed = 0
    worst_abs, worst_name = 0.0, None
    for entry in manifest["rasters"]:
        arr, row = _load_registry_array(entry, root, template)
        if arr is None:
            malformed += 1
            rows.append(row | {"spearman": None, "duplicate": False, "measurable": False})
            continue
        vals = arr[foot]
        if not np.isfinite(vals).all():
            malformed += 1
            rows.append(row | {"status": "nonfinite_inside_footprint", "spearman": None, "duplicate": False, "measurable": False})
            continue
        is_binary = bool(np.all((vals == 0.0) | (vals == 1.0)))
        dots = vals > 0.0
        mask_digest = hashlib.sha256(np.packbits(dots).tobytes()).hexdigest()
        cache_key = f"binary:{mask_digest}" if is_binary else f"file:{entry.get('sha256')}"
        if cache_key in cache:
            calc = cache[cache_key]
        elif np.ptp(vals) == 0.0:
            calc = {"spearman": None, "classification": "constant_or_empty", "measurable": False}
            cache[cache_key] = calc
        else:
            if is_binary:
                rho = _rho_rank_z_vs_binary(candidate_rank_z, dots)
                cls = "binary_submission"
            else:
                other_rank_z = _normalised_ranks(vals)
                rho = float(np.dot(candidate_rank_z, other_rank_z))
                cls = "continuous_registry_raster"
            calc = {"spearman": rho, "classification": cls, "measurable": rho is not None}
            cache[cache_key] = calc
        rho = calc["spearman"]
        duplicate = bool(rho is not None and abs(rho) > max_abs_spearman)
        if rho is not None and abs(rho) > worst_abs:
            worst_abs, worst_name = abs(rho), f"{entry.get('repo')}:{entry.get('path')}"
        rows.append(row | calc | {"dots": int(dots.sum()), "mask_digest": mask_digest, "duplicate": duplicate})

    duplicates = [r for r in rows if r.get("duplicate")]
    return {
        "stage": "surface_before_placement",
        "rule": f"full-footprint |Spearman| <= {max_abs_spearman}",
        "registry_rasters": len(rows),
        "unique_pixel_masks_or_surfaces": len(cache),
        "malformed_or_missing": malformed,
        "constant_or_empty": sum(r.get("classification") == "constant_or_empty" for r in rows),
        "worst_abs_spearman": worst_abs,
        "worst_raster": worst_name,
        "duplicates": duplicates,
        "audit_complete": bool(malformed == 0),
        "passed": bool(not duplicates),
        "comparisons": rows,
    }


def audit_final_dots(
    candidate_surface: np.ndarray,
    candidate_dots: np.ndarray,
    footprint: np.ndarray,
    manifest: dict,
    *,
    root: Path,
    template_tif: Path,
    max_abs_spearman: float = 0.90,
    max_within_3px: float = 0.70,
    space_filling_coverage: float | None = None,
    candidate_values: np.ndarray | None = None,
) -> dict:
    """Check exact final-dot Spearman and directional within-3-pixel overlap.

    ``space_filling_coverage`` (IR-47-LATTICE-FIX): when set (e.g. 0.70), a registry raster whose
    3-px dilation covers at least that fraction of the footprint is *space-filling*: uniformly
    random dots would already exceed the literal limit, so the literal test cannot discriminate.
    Such rasters are judged by the null-calibrated excess ``(overlap - coverage) / (1 - coverage)``
    against ``max_within_3px``; the literal overlap is still reported for every raster.  When
    ``None`` (default) the behaviour is the original literal rule with no exemptions.

    ``candidate_values``: optional prediction values; when given, a mass-weighted overlap
    (sum of p over overlapping dots / sum of p) must also stay <= ``max_within_3px`` so that
    low-value padding dots cannot buy uniqueness.
    """
    surface = np.asarray(candidate_surface, np.float32)
    dots_full = np.asarray(candidate_dots, bool)
    foot = np.asarray(footprint, bool)
    if surface.shape != foot.shape or dots_full.shape != foot.shape:
        raise ValueError("candidate surface/dot shape mismatch")
    dots_full &= foot
    if not dots_full.any() or not np.isfinite(surface[foot]).all():
        raise ValueError("empty dots or nonfinite candidate surface")
    cand_foot = dots_full[foot]
    cand_mass = None
    if candidate_values is not None:
        cv = np.asarray(candidate_values, np.float64)
        cand_mass = np.where(dots_full, np.nan_to_num(cv, nan=0.0), 0.0)[foot]
    with rasterio.open(template_tif) as tpl:
        template = {"shape": tpl.shape, "crs": tpl.crs, "transform": tpl.transform}

    yy, xx = np.ogrid[-3:4, -3:4]
    disk3 = (yy * yy + xx * xx) <= 9
    rows = []
    cache: dict[str, dict] = {}
    malformed = 0
    worst_rho, worst_ov = 0.0, 0.0
    worst_rho_name = worst_ov_name = None
    for entry in manifest["rasters"]:
        arr, row = _load_registry_array(entry, root, template)
        if arr is None:
            malformed += 1
            rows.append(row | {"spearman": None, "within_3px_fraction": None, "duplicate": False, "measurable": False})
            continue
        vals = arr[foot]
        if not np.isfinite(vals).all():
            malformed += 1
            rows.append(row | {"status": "nonfinite_inside_footprint", "spearman": None, "within_3px_fraction": None, "duplicate": False, "measurable": False})
            continue
        reg_dots_full = (arr > 0.0) & foot
        reg_dots = reg_dots_full[foot]
        is_binary = bool(np.all((vals == 0.0) | (vals == 1.0)))
        mask_digest = hashlib.sha256(np.packbits(reg_dots).tobytes()).hexdigest()
        cache_key = f"binary:{mask_digest}" if is_binary else f"file:{entry.get('sha256')}"
        if cache_key in cache:
            calc = cache[cache_key]
        elif not reg_dots.any():
            calc = {
                "spearman": None,
                "within_3px_fraction": 0.0,
                "classification": "constant_or_empty",
                "measurable": False,
            }
            cache[cache_key] = calc
        else:
            if is_binary:
                rho = _phi_binary(cand_foot, reg_dots)
                cls = "binary_submission"
            elif np.ptp(vals) > 0.0:
                rho = _rho_rank_z_vs_binary(_normalised_ranks(vals), cand_foot)
                cls = "continuous_registry_raster"
            else:
                rho, cls = None, "constant_or_empty"
            dil = binary_dilation(reg_dots_full, structure=disk3)
            within = float(dil[dots_full].mean())
            coverage = float(dil[foot].mean())
            calc = {
                "spearman": rho,
                "within_3px_fraction": within,
                "footprint_coverage_3px": coverage,
                "classification": cls,
                "measurable": rho is not None,
            }
            if cand_mass is not None:
                calc["mass_weighted_within_3px"] = float(cand_mass[dil[foot]].sum() / max(cand_mass.sum(), 1e-12))
            cache[cache_key] = calc
        rho, ov = calc["spearman"], calc["within_3px_fraction"]
        cov = calc.get("footprint_coverage_3px", 0.0) or 0.0
        space_filling = bool(space_filling_coverage is not None and cov >= space_filling_coverage)
        excess = (ov - cov) / max(1.0 - cov, 1e-9) if space_filling else None
        ov_rule = excess if space_filling else ov
        mw = calc.get("mass_weighted_within_3px")
        mw_dup = bool(mw is not None and not space_filling and mw > max_within_3px)
        literal_duplicate = bool((rho is not None and abs(rho) > max_abs_spearman) or ov > max_within_3px)
        duplicate = bool((rho is not None and abs(rho) > max_abs_spearman) or ov_rule > max_within_3px or mw_dup)
        name = f"{entry.get('repo')}:{entry.get('path')}"
        if rho is not None and abs(rho) > worst_rho:
            worst_rho, worst_rho_name = abs(rho), name
        if ov > worst_ov:
            worst_ov, worst_ov_name = ov, name
        rows.append(row | calc | {"dots": int(reg_dots.sum()), "mask_digest": mask_digest, "duplicate": duplicate,
                                  "literal_duplicate": literal_duplicate, "space_filling": space_filling,
                                  "null_calibrated_excess": excess})

    duplicates = [r for r in rows if r.get("duplicate")]
    literal_dups = [r for r in rows if r.get("literal_duplicate")]
    rule = (f"full-footprint |Spearman| <= {max_abs_spearman} AND candidate dots within 3 px <= {max_within_3px}; "
            + ("no density exemptions" if space_filling_coverage is None else
               f"space-filling rasters (3-px coverage >= {space_filling_coverage}) judged by null-calibrated excess; "
               "mass-weighted overlap also <= limit"))
    return {
        "stage": "final_dots",
        "rule": rule,
        "literal_rule_passed": bool(not literal_dups),
        "literal_duplicates": [{k: r.get(k) for k in ("repo", "path", "within_3px_fraction", "footprint_coverage_3px", "space_filling")} for r in literal_dups],
        "candidate_dots": int(dots_full.sum()),
        "registry_rasters": len(rows),
        "unique_pixel_masks_or_surfaces": len(cache),
        "malformed_or_missing": malformed,
        "constant_or_empty": sum(r.get("classification") == "constant_or_empty" for r in rows),
        "worst_abs_spearman": worst_rho,
        "worst_spearman_raster": worst_rho_name,
        "worst_within_3px_fraction": worst_ov,
        "worst_overlap_raster": worst_ov_name,
        "duplicates": duplicates,
        "audit_complete": bool(malformed == 0),
        "passed": bool(not duplicates),
        "comparisons": rows,
    }
