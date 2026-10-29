#!/usr/bin/env python3
"""Independent, rule-by-rule validator for a DrivenData GEMS submission file.

Checks the OFFICIAL requirements quoted from
https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/ (section "Submission format"):
  * single-layer GeoTIFF (a .zip is accepted only if it holds exactly one GeoTIFF)
  * float32; values in [0, 1] (the portal error "Predicted values must be in range [0, 1]")
  * same CRS (EPSG:32611), shape (3730 x 3292), 100 m transform and bounds as the training data
  * data outside the bounds is null or NaN (the NaN-outside form is required; zeros outside is diagnostic)
  * no NaN/Inf inside the footprint; footprint identical to sample_submission.tif

It does NOT reuse the writer's own checks, so it is a second, independent implementation.
Writes evidence/validation_<stem>.json and exits non-zero on any failure (fail-closed).
"""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "data" / "sample_submission.tif"
EXPECTED_SHAPE = (3730, 3292)
EXPECTED_TRANSFORM = (100.0, 0.0, 243350.0, 0.0, -100.0, 4508550.0)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(p.read_bytes())


def validate_tif(path: Path, foot: np.ndarray) -> dict:
    checks: dict[str, bool] = {}
    with rasterio.open(path) as ds:
        checks["driver_GTiff"] = ds.driver == "GTiff"
        checks["single_band"] = ds.count == 1
        checks["dtype_float32"] = ds.dtypes[0] == "float32"
        checks["crs_epsg_32611"] = ds.crs is not None and ds.crs.to_epsg() == 32611
        checks["shape_3730x3292"] = tuple(ds.shape) == EXPECTED_SHAPE
        checks["transform_matches_template"] = tuple(ds.transform)[:6] == EXPECTED_TRANSFORM
        arr = ds.read(1)
        nodata = ds.nodata
    fin = np.isfinite(arr)
    checks["no_nan_or_inf_inside_footprint"] = bool(fin[foot].all())
    inside = arr[foot]
    checks["values_in_0_1_inside_footprint"] = bool(((inside >= 0.0) & (inside <= 1.0)).all())
    checks["outside_footprint_is_nan"] = bool(np.isnan(arr[~foot]).all())
    checks["footprint_identical_to_template"] = bool(np.array_equal(fin, foot))
    dots = int(((inside > 0.0)).sum())
    return {
        "checks": checks,
        "all_passed": all(checks.values()),
        "nodata_tag": None if nodata is None else str(nodata),
        "positive_pixels_inside_footprint": dots,
        "min_inside": float(inside.min()),
        "max_inside": float(inside.max()),
        "distinct_values_inside": int(np.unique(inside).size),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_submission_file.py <file.tif|file.zip>", file=sys.stderr)
        return 2
    target = Path(sys.argv[1]).resolve()
    with rasterio.open(TEMPLATE) as ds:
        foot = np.isfinite(ds.read(1))
    report: dict = {"schema": "submission-file-validation/v1", "file": str(target.relative_to(ROOT))}
    tif_path = target
    tmp_dir = ROOT / "data" / "cache" / "validation"
    if target.suffix.lower() == ".zip":
        with zipfile.ZipFile(target) as zf:
            members = [m for m in zf.namelist() if not m.endswith("/")]
            report["zip_members"] = members
            zip_ok = len(members) == 1 and members[0].lower().endswith(".tif")
            report["zip_contains_exactly_one_tif"] = zip_ok
            if not zip_ok:
                report["all_passed"] = False
                print(json.dumps(report, indent=2))
                return 1
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tif_path = tmp_dir / Path(members[0]).name
            tif_path.write_bytes(zf.read(members[0]))
    res = validate_tif(tif_path, foot)
    report["tif_member"] = tif_path.name
    report["tif"] = res
    report["all_passed"] = bool(res["all_passed"] and report.get("zip_contains_exactly_one_tif", True))
    report["verdict"] = "PASS: automated official-format validation" if report["all_passed"] else "FAIL: do not download/submit"
    out = ROOT / "evidence" / f"validation_{target.stem}.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
