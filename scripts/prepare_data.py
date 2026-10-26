#!/usr/bin/env python3
"""Prepare and audit the competition rasters for GEMSDOE32.

Reads training_features.tif (19 bands), labels.tif, and sample_submission.tif from data_dir(),
audits CRS (EPSG:32611), shape (3730x3292), 100 m geotransform, and sentinel pixels (-3.4028235e+38)
inside the 5,167,373-pixel footprint, writes fast per-band .npy arrays to work_dir()/bands, and saves
the full audit receipt to data/prepared_manifest.json.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gems32.paths import data_dir, work_dir  # noqa: E402

BASE_NAMES = [
    "mag_anom",
    "rtp",
    "tmi_hg",
    "geod_2ndinv",
    "iso_grav_anom_slope",
    "tc",
    "geod_shearrate",
    "geod_dilaterate",
    "tmi_vg",
    "deq_n100a15",
    "iso_grav_anom_vg",
    "det_elev",
    "iso_grav_anom",
    "tmi",
    "depth_to_base_surf",
    "ieq_n100a15",
    "cond_surf",
    "iso_grav_anom_hg",
    "det_elev_slope",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def prepare() -> dict:
    ddir = data_dir()
    wdir = work_dir()
    bands_dir = wdir / "bands"
    bands_dir.mkdir(parents=True, exist_ok=True)

    feat_path = ddir / "training_features.tif"
    lab_path = ddir / "labels.tif"
    tmpl_path = ddir / "sample_submission.tif"

    for p in (feat_path, lab_path, tmpl_path):
        if not p.exists():
            raise FileNotFoundError(
                f"Missing required competition file {p}. Run `bash scripts/download_competition_data.sh` first."
            )

    with rasterio.open(tmpl_path) as tmpl:
        epsg = tmpl.crs.to_epsg()
        if epsg != 32611:
            raise ValueError(f"Expected EPSG:32611, got {tmpl.crs}")
        shape_hw = (tmpl.height, tmpl.width)
        if shape_hw != (3730, 3292):
            raise ValueError(f"Expected shape (3730, 3292), got {shape_hw}")
        transform_tuple = tuple(float(v) for v in tmpl.transform)[:6]
        foot_arr = tmpl.read(1)
        foot = np.isfinite(foot_arr)

    with rasterio.open(lab_path) as lab_src:
        if (lab_src.height, lab_src.width) != shape_hw:
            raise ValueError("labels.tif shape mismatch")
        lab_raw = lab_src.read(1)
        lab = (lab_raw == 1) & foot

    np.save(bands_dir / "_footprint.npy", foot)
    np.save(bands_dir / "_labels.npy", lab)

    band_stats = []
    total_sentinel_in_foot = 0
    any_sentinel_in_foot = np.zeros(shape_hw, dtype=bool)

    with rasterio.open(feat_path) as feat_src:
        if (feat_src.height, feat_src.width) != shape_hw:
            raise ValueError("training_features.tif shape mismatch")
        names = [feat_src.tags(i).get("band_name", f"band_{i}") for i in range(1, feat_src.count + 1)]
        if names != BASE_NAMES:
            raise ValueError(f"Unexpected band order: {names}")
        nd = feat_src.nodata
        for idx, bname in enumerate(names, 1):
            arr = feat_src.read(idx).astype(np.float32)
            is_sentinel = (~np.isfinite(arr)) | (arr < -1e38)
            if nd is not None and not np.isnan(nd):
                is_sentinel |= arr == nd
            sentinel_in_foot = int(np.sum(is_sentinel & foot))
            total_sentinel_in_foot += sentinel_in_foot
            any_sentinel_in_foot |= is_sentinel & foot

            arr[is_sentinel] = np.nan
            arr[~foot] = np.nan
            np.save(bands_dir / f"{idx:02d}_{bname}.npy", arr)

            valid_vals = arr[foot & np.isfinite(arr)]
            band_stats.append(
                {
                    "index": idx,
                    "name": bname,
                    "finite_in_footprint": int(valid_vals.size),
                    "sentinel_in_footprint": sentinel_in_foot,
                    "min": float(np.min(valid_vals)),
                    "p05": float(np.percentile(valid_vals, 5)),
                    "median": float(np.median(valid_vals)),
                    "p95": float(np.percentile(valid_vals, 95)),
                    "max": float(np.max(valid_vals)),
                }
            )

    manifest = {
        "schema_version": 1,
        "prepared_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "grid": {
            "epsg": epsg,
            "height": shape_hw[0],
            "width": shape_hw[1],
            "total_cells": int(shape_hw[0] * shape_hw[1]),
            "transform": list(transform_tuple),
            "pixel_size_m": [100.0, 100.0],
        },
        "counts": {
            "footprint_valid_pixels": int(foot.sum()),
            "outside_footprint_pixels": int((~foot).sum()),
            "positive_catalogue_label_pixels": int(lab.sum()),
            "negative_in_footprint_pixels": int(foot.sum() - lab.sum()),
            "total_sentinel_band_pixels_inside_footprint": total_sentinel_in_foot,
            "unique_footprint_pixels_with_any_sentinel": int(any_sentinel_in_foot.sum()),
        },
        "source_hashes": {
            "training_features.tif": sha256_file(feat_path),
            "labels.tif": sha256_file(lab_path),
            "sample_submission.tif": sha256_file(tmpl_path),
        },
        "bands": band_stats,
    }

    out_path = ROOT / "data" / "prepared_manifest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    manifest = prepare()
    print(
        f"[GEMSDOE32] Prepared {len(manifest['bands'])} bands | "
        f"Footprint={manifest['counts']['footprint_valid_pixels']:,} px | "
        f"Catalogue positives={manifest['counts']['positive_catalogue_label_pixels']:,} px | "
        f"Sanitized {manifest['counts']['total_sentinel_band_pixels_inside_footprint']:,} sentinel band-pixels."
    )


if __name__ == "__main__":
    main()
