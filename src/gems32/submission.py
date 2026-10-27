"""DrivenData GeoTIFF Submission Builder & Range-[0, 1] Validator Auditor.

Fail-closed submission writing and local range validation. Local validation does not
prove organizer acceptance or that the reported portal error had a specific cause.
Predictions must already be finite, in [0,1], zero outside the footprint and zero
on mapped faults. No clipping, binarization, or silent repair is performed.
The writer emits a zero-filled diagnostic GeoTIFF and an official-format candidate GeoTIFF:
   - `-zeros.tif`: `0.0` outside footprint (`nodata=None`), useful for local full-array range diagnostics but **not compliant** with the official requirement that outside-bounds pixels be null/NaN.
   - `-nan.tif`: `NaN` outside footprint (`nodata=np.nan`), with finite [0,1] predictions inside the footprint; this is the only file placed in the single-TIFF submission ZIP. Local checks still cannot guarantee portal acceptance.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import rasterio

EXPECTED_HEIGHT = 3730
EXPECTED_WIDTH = 3292
EXPECTED_TOTAL_PIXELS = EXPECTED_HEIGHT * EXPECTED_WIDTH
EXPECTED_FOOTPRINT_PIXELS = 5_167_373


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_geotiff(
    tif_path: Path,
    foot: np.ndarray,
    labels: np.ndarray,
    mode: str = "zeros",
    template_tif: Path | None = None,
) -> dict:
    """Strict 12-point DrivenData submission validator audit."""
    if mode not in {"zeros", "nan"}:
        raise ValueError("mode must be zeros or nan")
    # Legacy callers use the documented historical grid. Writers must use the actual template.
    expected_crs = rasterio.crs.CRS.from_epsg(32611)
    expected_shape = (EXPECTED_HEIGHT, EXPECTED_WIDTH)
    expected_transform = rasterio.transform.from_origin(243350, 4508550, 100, 100)
    if template_tif is not None:
        with rasterio.open(template_tif) as tpl:
            expected_crs, expected_shape, expected_transform = tpl.crs, tpl.shape, tpl.transform
    with rasterio.open(tif_path) as src:
        if (src.crs != expected_crs or src.shape != expected_shape
                or src.transform != expected_transform):
            raise ValueError("Submission CRS/shape/transform mismatch against reference grid")
        if foot.shape != src.shape or labels.shape != src.shape or not foot.any():
            raise ValueError("Invalid footprint or labels shape")
        arr = src.read(1)
        crs_str = str(src.crs)
        is_epsg_32611 = src.crs == rasterio.crs.CRS.from_epsg(32611)
        transform_tuple = tuple(float(x) for x in src.transform)[:6]
        dtypes = src.dtypes
        count = src.count
        height, width = src.height, src.width
        nodata_val = src.nodata

    in_foot = arr[foot]
    out_foot = arr[~foot]

    in_foot_finite = int(np.isfinite(in_foot).sum())
    in_foot_nan = int(np.isnan(in_foot).sum())
    in_foot_inf = int(np.isinf(in_foot).sum())
    in_foot_sentinel = int((in_foot < -1e30).sum())
    in_foot_min = float(np.nanmin(in_foot))
    in_foot_max = float(np.nanmax(in_foot))
    in_foot_in_01 = bool(
        (in_foot_finite == EXPECTED_FOOTPRINT_PIXELS)
        and np.all((in_foot >= 0.0) & (in_foot <= 1.0))
    )

    if mode == "zeros":
        full_grid_in_01 = bool(
            (int(np.isfinite(arr).sum()) == EXPECTED_TOTAL_PIXELS)
            and np.all((arr >= 0.0) & (arr <= 1.0))
        )
        out_foot_ok = bool(np.all(out_foot == 0.0))
    else:
        full_grid_in_01 = in_foot_in_01
        out_foot_ok = bool(np.all(np.isnan(out_foot)))

    emitted_dots = int((in_foot > 0).sum())
    on_catalogue_dots = int(((arr > 0) & labels).sum())

    checks = {
        "exact_reference_grid_match": True,
        "single_band": count == 1,
        "dtype_float32": dtypes[0] == "float32",
        "dimensions_3730x3292": (height == EXPECTED_HEIGHT and width == EXPECTED_WIDTH),
        "crs_epsg_32611": is_epsg_32611,
        "in_footprint_all_finite": in_foot_finite == EXPECTED_FOOTPRINT_PIXELS,
        "in_footprint_zero_nan": in_foot_nan == 0,
        "in_footprint_zero_inf": in_foot_inf == 0,
        "in_footprint_zero_sentinel": in_foot_sentinel == 0,
        "in_footprint_range_0_1": in_foot_in_01,
        "outside_footprint_compliant": out_foot_ok,
        "nodata_none_for_zeros": mode != "zeros" or nodata_val is None,
        "nodata_nan_for_nan": bool(mode != "nan" or (nodata_val is not None and np.isnan(nodata_val))),
        "zero_on_catalogue_leakage": on_catalogue_dots == 0,
        "local_range_check": full_grid_in_01,
    }
    all_passed = all(checks.values())
    if not all_passed:
        failed = [k for k, v in checks.items() if not v]
        raise ValueError(f"Submission audit failed for {tif_path.name}: {failed}")

    return {
        "filename": tif_path.name,
        "size_bytes": tif_path.stat().st_size,
        "sha256": sha256_file(tif_path),
        "mode": mode,
        "geometry_reference": str(template_tif) if template_tif else "documented historical grid (not freshly authenticated)",
        "crs": crs_str,
        "transform": list(transform_tuple),
        "shape": [height, width],
        "dtype": dtypes[0],
        "nodata": None if nodata_val is None or (isinstance(nodata_val, float) and np.isnan(nodata_val)) else float(nodata_val),
        "nodata_repr": str(nodata_val),
        "emitted_positive_pixels": emitted_dots,
        "footprint_fraction": round(emitted_dots / float(EXPECTED_FOOTPRINT_PIXELS), 6),
        "on_catalogue_positive_pixels": on_catalogue_dots,
        "in_footprint_finite_pixels": in_foot_finite,
        "in_footprint_min": in_foot_min,
        "in_footprint_max": in_foot_max,
        "full_grid_finite_pixels": int(np.isfinite(arr).sum()),
        "checks": checks,
        "all_checks_passed": all_passed,
    }


def write_submission_pair(
    mask: np.ndarray,
    foot: np.ndarray,
    labels: np.ndarray,
    template_tif: Path,
    out_dir: Path,
    slug: str,
    timestamp_tag: str,
    candidate_meta: dict,
) -> dict:
    """Write and audit both encodings, preserving normalized probabilities.

    Reject bad data instead of making out-of-range, NaN, off-footprint or
    catalogue values look like a valid binary submission.
    """
    raw = np.asarray(mask)
    foot_raw, labels_raw = np.asarray(foot), np.asarray(labels)
    for value, description in ((foot_raw, "footprint"), (labels_raw, "catalogue mask")):
        if not (np.issubdtype(value.dtype, np.number) or value.dtype == np.bool_):
            raise ValueError(f"{description} must be numeric or boolean")
        if not np.isfinite(value).all() or not np.isin(value, (0, 1)).all():
            raise ValueError(f"{description} must already be finite and binary")
    foot, labels = foot_raw.astype(bool, copy=False), labels_raw.astype(bool, copy=False)
    if raw.ndim != 2 or raw.shape != foot.shape or raw.shape != labels.shape or not foot.any():
        raise ValueError("predictions, footprint and labels must be matching nonempty 2-D grids")
    if not (np.issubdtype(raw.dtype, np.number) or raw.dtype == np.bool_):
        raise ValueError("predictions must be numeric")
    if not np.isfinite(raw).all() or (raw < 0).any() or (raw > 1).any():
        raise ValueError("predictions must already be finite in [0,1]; no silent repair")
    if (raw[~foot] != 0).any():
        raise ValueError("predictions must be zero outside the footprint")
    if (raw[labels] != 0).any():
        raise ValueError("predictions must be zero on the mapped catalogue")
    clean_mask = raw.astype(np.float32, copy=False)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Preserve the old binary content ID; soft fields hash their actual float32 values.
    if np.all((clean_mask == 0) | (clean_mask == 1)):
        digest8 = hashlib.sha256(np.packbits(clean_mask > 0)).hexdigest()[:8]
    else:
        digest8 = hashlib.sha256(np.ascontiguousarray(clean_mask, dtype='<f4').tobytes()).hexdigest()[:8]
    prefix = str(candidate_meta.get("filename_prefix", "gemsdoe32")).strip("-") or "gemsdoe32"

    zeros_name = f"{prefix}-{slug}-{timestamp_tag}-{digest8}-zeros.tif"
    nan_name = f"{prefix}-{slug}-{timestamp_tag}-{digest8}-nan.tif"
    zeros_path = out_dir / zeros_name
    nan_path = out_dir / nan_name
    sidecar_path = out_dir / f"{prefix}-{slug}-{timestamp_tag}-{digest8}-audit.json"
    if any(p.exists() for p in (zeros_path, nan_path, sidecar_path)):
        raise FileExistsError("refusing to overwrite an existing submission artifact")

    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in (prefix, slug, timestamp_tag)):
        raise ValueError("filename prefix, slug and timestamp must contain only letters, digits, _ or -")
    # The official format requires null/NaN outside the submission bounds. Keep
    # the zero-filled variant as a diagnostic only; the only submission ZIP
    # must contain the NaN-outside GeoTIFF.
    zip_path = nan_path.with_suffix(".zip")
    if zip_path.exists():
        raise FileExistsError("refusing to overwrite an existing submission ZIP")
    with rasterio.open(template_tif) as tpl:
        if tpl.shape != foot.shape:
            raise ValueError("reference template and footprint have different shapes")
        profile_base = tpl.profile.copy()
    profile_zeros = profile_base.copy()
    profile_zeros.update(driver="GTiff", dtype="float32", count=1, compress="deflate",
                         predictor=3, zlevel=9, tiled=True, blockxsize=256, blockysize=256, nodata=None)
    profile_nan = profile_zeros.copy()
    profile_nan.update(nodata=np.nan)
    # Stage everything in the output filesystem and publish only after all
    # validation and ZIP round-tripping have passed. Hard links are exclusive:
    # a concurrent writer cannot silently replace an existing artifact.
    with tempfile.TemporaryDirectory(prefix=".submission-", dir=out_dir) as temp:
        stage = Path(temp)
        tmp_zeros, tmp_nan = stage / zeros_name, stage / nan_name
        tmp_zip, tmp_sidecar = stage / zip_path.name, stage / sidecar_path.name
        with rasterio.open(tmp_zeros, "w", **profile_zeros) as dst:
            dst.write(np.where(foot, clean_mask, 0.0).astype(np.float32), 1)
        with rasterio.open(tmp_nan, "w", **profile_nan) as dst:
            dst.write(np.where(foot, clean_mask, np.nan).astype(np.float32), 1)
        audit_zeros = audit_geotiff(tmp_zeros, foot, labels, mode="zeros", template_tif=template_tif)
        audit_nan = audit_geotiff(tmp_nan, foot, labels, mode="nan", template_tif=template_tif)
        fmt_kwargs = dict(dots=audit_zeros["emitted_positive_pixels"],
            cat_hid=candidate_meta["catalogue_hidden_mean"],
            sgmc_cal=candidate_meta["sgmc_prevalence_calibrated_dti"],
            drift_cal=candidate_meta["drift_corrected_holdout_mean"], slot=candidate_meta["slot_decision"])
        note_zeros = candidate_meta["submission_note_zeros"].format(
            filename=zeros_name, sha8=audit_zeros["sha256"][:8], **fmt_kwargs)
        note_nan = candidate_meta["submission_note_nan"].format(
            filename=nan_name, sha8=audit_nan["sha256"][:8], **fmt_kwargs)
        if not note_zeros.strip() or not note_nan.strip() or len(note_zeros) > 140 or len(note_nan) > 140:
            raise ValueError("formatted submission notes must have 1..140 characters")
        with zipfile.ZipFile(tmp_zip, "w") as archive:
            info = zipfile.ZipInfo(nan_name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, tmp_nan.read_bytes(), compresslevel=9)
        with zipfile.ZipFile(tmp_zip) as archive:
            if archive.namelist() != [nan_name] or archive.read(nan_name) != tmp_nan.read_bytes():
                raise IOError("single-TIFF submission ZIP roundtrip failed")
        bundle = {
            "candidate_id": candidate_meta["candidate_id"], "slug": slug, "content_digest8": digest8,
            "description": candidate_meta["description"],
            "submission_note_zeros": note_zeros, "submission_note_nan": note_nan,
            "zeros_tif": audit_zeros, "nan_tif": audit_nan,
            "submission_zip": {"filename": zip_path.name, "path": str(zip_path),
                               "contains": nan_name,
                               "size_bytes": tmp_zip.stat().st_size, "sha256": sha256_file(tmp_zip)},
            "zeros_variant_warning": "Diagnostic only: zeros outside bounds do not meet the official null/NaN outside-bounds requirement.",
            "holdout_metrics": {key: candidate_meta[key] for key in (
                "catalogue_hidden_mean", "catalogue_hidden_per_quadrant",
                "sgmc_prevalence_calibrated_dti", "drift_corrected_holdout_mean",
                "drift_corrected_per_quadrant", "predicted_leaderboard_dti",
                "ei_drift_corrected", "slot_decision")},
            "publication_warning": "Local format validity does not establish uniqueness, holdout quality or organizer acceptance.",
        }
        tmp_sidecar.write_text(json.dumps(bundle, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        committed = []
        try:
            for source, final in ((tmp_zip, zip_path), (tmp_nan, nan_path),
                                  (tmp_sidecar, sidecar_path), (tmp_zeros, zeros_path)):
                os.link(source, final)
                committed.append(final)
        except Exception:
            for final in committed:
                final.unlink(missing_ok=True)
            raise
    return bundle
