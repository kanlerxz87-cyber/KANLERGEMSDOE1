#!/usr/bin/env python3
"""Reproduce the nine historical-raster audit and the literal lattice-capacity bound.

This is a read-only comparison, not the template's holdout evaluator, submission
writer, a prediction, or a submission-approval mechanism. Pixel distances are
Euclidean in the common 100 m raster grid.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import rasterio
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_focus_rasters import LATTICE, digest  # noqa: E402

SAMPLE_SHA = "2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc"
LABEL_SHA = "7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093"


def capacity(outside_cells: int, count: int) -> dict:
    """Conservative combinatorial lower bound on lattice overlap for distinct dots.

    A = all footprint cells within 3 px; outside_cells = |footprint \\ A|.
    At most outside_cells candidate dots can lie outside A. Empty predictions
    are not considered unique; the fraction is undefined for zero dots.
    """
    if type(outside_cells) is not int or type(count) is not int or outside_cells < 0 or count < 0:
        raise ValueError("counts must be nonnegative integers")
    return {
        "positive_dots": count,
        "min_overlap_fraction": max(0, count - outside_cells) / count if count else None,
        "can_pass_70pct_overlap_bound": bool(count and 10 * max(0, count - outside_cells) <= 7 * count),
        "largest_count_that_could_pass": 10 * outside_cells // 3,
        "first_impossible_count": 10 * outside_cells // 3 + 1,
    }


def load_binary(path: Path, grid, footprint: np.ndarray, expected_sha: str) -> tuple[np.ndarray, dict]:
    if not path.is_file() or digest(path) != expected_sha:
        raise ValueError(f"missing or hash-mismatched input: {path}")
    with rasterio.open(path) as ds:
        if ds.count != 1 or (ds.crs, ds.shape, ds.transform) != grid:
            raise ValueError(f"incompatible grid or band count: {path}")
        arr = ds.read(1)
        if ds.dtypes[0] != "float32":
            raise ValueError(f"unexpected historical dtype: {path}")
    values = arr[footprint]
    if not np.isfinite(values).all() or not np.isin(values, [0.0, 1.0]).all():
        raise ValueError(f"non-binary or invalid values inside footprint: {path}")
    dots = footprint & (arr > 0)
    # Hash binary support inside the same footprint, not compression, metadata,
    # NaN encoding, nor bytes outside it. All audited inputs are strictly binary.
    support_sha = hashlib.sha256(np.packbits(dots[footprint]).tobytes()).hexdigest()
    return dots, {
        "sha256": expected_sha,
        "binary_support_sha256": support_sha,
        "positive_pixels": int(dots.sum()),
        "finite_inside_footprint": bool(np.isfinite(values).all()),
        "all_finite_full_grid": bool(np.isfinite(arr).all()),
    }


def audit(data: Path, manifest: dict, current_manifest: dict) -> dict:
    sample_path, labels_path = data / "sample_submission.tif", data / "labels.tif"
    if not sample_path.is_file() or digest(sample_path) != SAMPLE_SHA:
        raise ValueError("missing or hash-mismatched owner-mirrored sample")
    if not labels_path.is_file() or digest(labels_path) != LABEL_SHA:
        raise ValueError("missing or hash-mismatched owner-mirrored labels")
    with rasterio.open(sample_path) as sample:
        if sample.count != 1 or sample.crs is None or sample.crs.to_epsg() != 32611:
            raise ValueError("unexpected template geometry")
        grid = sample.crs, sample.shape, sample.transform
        sample_values = sample.read(1)
        footprint = np.isfinite(sample_values)
    if not footprint.any():
        raise ValueError("empty footprint")
    with rasterio.open(labels_path) as src:
        if src.count != 1 or (src.crs, src.shape, src.transform) != grid:
            raise ValueError("label grid mismatch")
        label_values = src.read(1)
        if not np.isfinite(label_values[footprint]).all() or not np.isin(label_values[footprint], (0, 1)).all():
            raise ValueError("invalid mirrored label values inside footprint")
        labels = (label_values == 1) & footprint
    sample_is_labels = bool(np.array_equal((sample_values > 0) & footprint, labels))
    lattice, lattice_info = load_binary(data / "registry/13gems_r13_lattice.tif", grid, footprint, LATTICE["sha256"])
    if not labels.any() or not lattice.any():
        raise ValueError("empty mirrored label or lattice support")
    near_lattice = distance_transform_edt(~lattice) <= 3.0
    covered = int((near_lattice & footprint).sum())
    f = int(footprint.sum())
    outside = f - covered
    items = manifest["sites"]
    if len(items) != 9 or len({s['id'] for s in items}) != 9:
        raise ValueError("expected nine distinct focus sites")
    dots = {}
    result = {}
    for s in items:
        support, info = load_binary(data / "focus" / (s["id"] + ".tif"), grid, footprint, s["sha256"])
        if not support.any():
            raise ValueError(f"empty historical raster: {s['id']}")
        dots[s["id"]] = support
        info["overlap_with_r13_lattice"] = float((support & near_lattice).sum() / support.sum())
        result[s["id"]] = info
    # Every pair is directional: fraction of site A's dots near at least one B dot.
    near = {site: distance_transform_edt(~support) <= 3.0 for site, support in dots.items()}
    overlaps = {
        a: {b: float((support & near_b).sum() / support.sum()) for b, near_b in near.items() if b != a}
        for a, support in dots.items()
    }
    for a in result:
        others = overlaps[a]
        nearest = max(others, key=others.get)
        result[a]["max_focus_peer_overlap"] = others[nearest]
        result[a]["max_focus_peer"] = nearest
        result[a]["literal_peer_gate_pass"] = all(value <= 0.70 for value in others.values())
        result[a]["exact_support_peers"] = [b for b in result if b != a and result[b]["binary_support_sha256"] == result[a]["binary_support_sha256"]]
    current_reviews = {}
    for item in current_manifest["candidates"]:
        candidate, info = load_binary(
            data / "registry/current-reviews" / (item["id"] + ".tif"), grid, footprint, item["sha256"]
        )
        if not candidate.any():
            raise ValueError(f"empty reviewed raster: {item['id']}")
        info["overlap_with_r13_lattice"] = float((candidate & near_lattice).sum() / candidate.sum())
        info["literal_lattice_gate_pass"] = bool(info["overlap_with_r13_lattice"] <= 0.70)
        current_reviews[item["id"]] = info
    distances = distance_transform_edt(~labels)
    d28, h33 = dots["GEMSDOE25"], dots["GEMSDOE32"]
    h33_expected = d28 & (distances > 2.0) & footprint
    return {
        "schema_version": 1,
        "scope": "Pinned owner mirrors and nine historical files; not independently organizer authenticated, not a holdout or score.",
        "sample_sha256": SAMPLE_SHA,
        "labels_sha256": LABEL_SHA,
        "sample_positive_pixels": int(((sample_values > 0) & footprint).sum()),
        "labels_positive_pixels": int(labels.sum()),
        "sample_positive_mask_equals_labels": sample_is_labels,
        "footprint_pixels": f,
        "lattice": {
            **lattice_info,
            "within_3px_pixels": covered,
            "fraction_footprint_within_3px": covered / f,
            "outside_3px_pixels": outside,
            "capacity_at_h33_budget": capacity(outside, int(h33.sum())),
        },
        "h33_lineage": {
            "d28_dots": int(d28.sum()),
            "h33_dots": int(h33.sum()),
            "d28_inside_2px_of_catalogue": int((d28 & (distances <= 2)).sum()),
            "h33_xor_d28_beyond_2px": int((h33 ^ h33_expected).sum()),
            "meaning": "Geometric identity on the owner-mirrored inputs; this is not evidence of a score or causal improvement.",
        },
        "sites": result,
        "current_sibling_claim_reviews": current_reviews,
        "directional_overlap_within_3px": overlaps,
        "surface_comparisons": "not available; archived pre-placement surfaces not replayed",
    }


def main() -> int:
    manifest = json.loads((ROOT / "registry/focus_sites.json").read_text())
    current_manifest = json.loads((ROOT / "registry/current_site_claims.json").read_text())
    report = audit(ROOT / "data", manifest, current_manifest)
    out = ROOT / "evidence/focus-site-audit-20261026.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Read-only audit saved to {out.relative_to(ROOT)}")
    print(f"Lattice coverage {report['lattice']['fraction_footprint_within_3px']:.6%}; at H33 dot count minimum possible overlap {report['lattice']['capacity_at_h33_budget']['min_overlap_fraction']:.6%}.")
    print("No candidate was built or approved; this is not a leaderboard estimate.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(f"Audit failed closed: {exc}", file=sys.stderr)
        raise SystemExit(1)
