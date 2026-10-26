#!/usr/bin/env python3
"""Re-open previous TIFFs; enforce the literal registry STOP without a new experiment.

Only the nine pinned focus champions plus one registered lattice are audited.
That is enough to establish a duplicate, not enough to certify global novelty.
No geological surface is reconstructed, no predictions are emitted, and no
competition submission is made.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import binary_dilation, distance_transform_edt
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from gems32.paths import data_dir
from gems32.submission import audit_geotiff
from restore_data import GitBlobFetcher, restore_entry, sha256_file


def disk3():
    y, x = np.ogrid[-3:4, -3:4]
    return (y * y + x * x) <= 9


def binary_rho(a, b, footprint):
    """Exact tied-rank Spearman for binary fields, equal to binary Pearson/phi."""
    a = a & footprint
    b = b & footprint
    n = int(footprint.sum()); na = int(a.sum()); nb = int(b.sum()); both = int((a & b).sum())
    den = float(na * (n - na) * nb * (n - nb)) ** 0.5
    return float((n * both - na * nb) / den) if den else None


def read_dots(path, foot, expected_grid, expected_sha=None):
    if expected_sha and sha256_file(path) != expected_sha:
        raise ValueError(f"SHA-256 mismatch: {path}")
    with rasterio.open(path) as ds:
        if ds.count != 1 or (ds.shape, ds.crs, ds.transform) != expected_grid:
            raise ValueError(f"Grid/band mismatch: {path}")
        data = ds.read(1)
    vals = data[foot]
    if not np.isfinite(vals).all() or not np.all((vals == 0) | (vals == 1)):
        raise ValueError(f"Focus comparison expects binary finite footprint: {path}")
    return (data > 0) & foot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", action="store_true", help="Fetch pinned comparison bytes if missing")
    parser.add_argument("--data-dir", type=Path, default=data_dir())
    args = parser.parse_args()
    ddir = args.data_dir
    manifest = json.loads((ROOT / "registry/data_manifest.json").read_text())
    focus = json.loads((ROOT / "registry/focus_sites.json").read_text())["files"]
    witness = next(e for e in manifest["files"] if e["id"] == "calib_13gems_20261001_r13-lattice-s5_v2_nan-ou")
    parent = next(e for e in manifest["files"] if e["id"] == "scored_h19_5")
    needs = [next(e for e in manifest["files"] if e["id"] == key) for key in ("sample_submission", "labels")]
    if args.restore:
        fetcher = GitBlobFetcher(ROOT / ".cache/git_blob_cache")
        for entry in [*needs, witness, parent, *focus]:
            status = restore_entry(entry, ddir, fetcher)
            print(status["status"], entry["dest"], flush=True)
    for e in [*needs, witness, parent, *focus]:
        p = ddir / e["dest"]
        if not p.is_file() or sha256_file(p) != e["sha256"]:
            raise SystemExit(f"Missing or hash-mismatched input {p}; run with --restore")

    with rasterio.open(ddir / "sample_submission.tif") as ds:
        foot = np.isfinite(ds.read(1))
        grid = (ds.shape, ds.crs, ds.transform)
    with rasterio.open(ddir / "labels.tif") as ds:
        if (ds.shape, ds.crs, ds.transform) != grid:
            raise ValueError("Label grid differs from sample grid")
        labels = (ds.read(1) > 0) & foot
    w = read_dots(ddir / witness["dest"], foot, grid, witness["sha256"])
    near_witness = binary_dilation(w, structure=disk3())
    allowed = foot & ~labels
    uncovered = int((allowed & ~near_witness).sum())

    dots = {}
    for entry in focus:
        dots[entry["site"]] = read_dots(ddir / entry["dest"], foot, grid, entry["sha256"])
    near = {site: binary_dilation(a, structure=disk3()) for site, a in dots.items()}
    focus_rows = []
    for entry in focus:
        site = entry["site"]; a = dots[site]; n = int(a.sum())
        others = [(float(near[other][a].mean()), other) for other in dots if other != site]
        worst, peer = max(others)
        same_support = sorted(other for other, b in dots.items() if other != site and np.array_equal(a, b))
        focus_rows.append({**entry, "support_pixels": n,
                           "support_sha256": hashlib.sha256(np.packbits(a).tobytes()).hexdigest(),
                           "worst_peer_3px_overlap": worst, "worst_peer": peer,
                           "identical_support_peers": same_support,
                           "literal_unique_vs_other_focus_champions": worst <= 0.70})

    focus_matrix = {site: {
        other: {"within_3px_fraction": float(near[other][a].mean()),
                "spearman_final_dots": binary_rho(a, b, foot),
                "identical_support": bool(np.array_equal(a, b))}
        for other, b in dots.items()} for site, a in dots.items()}

    # Verify the lineage by decoded pixels, rather than relying on names or scores.
    d28 = dots["GEMSDOE25"]
    parent_dots = read_dots(ddir / parent["dest"], foot, grid, parent["sha256"])
    nearest = cKDTree(np.argwhere(d28)).query(np.argwhere(d28), k=2)[0][:, 1]
    dist = distance_transform_edt(~labels)
    predictions = {"B1": d28 & (dist > 1), "B2": d28 & (dist > 2)}
    nested = {"parent_file": parent["dest"], "parent_sha256": parent["sha256"],
              "parent_dots": int(parent_dots.sum()),
              "d28_child_dots_outside_parent": int((d28 & ~parent_dots).sum()),
              "d28_minimum_nearest_neighbor_distance_pixels": float(nearest.min()),
              "d28_to_b1_xor_pixels": int((predictions["B1"] ^ dots["GEMSDOE31"]).sum()),
              "d28_to_b2_xor_pixels": int((predictions["B2"] ^ dots["GEMSDOE32"]).sum()),
              "d28_dots": int(d28.sum()), "b1_dots": int(dots["GEMSDOE31"].sum()),
              "b2_dots": int(dots["GEMSDOE32"].sum()),
              "distance": "Euclidean distance in pixels to all positive mirrored catalogue pixels; threshold strictly greater than B"}
    del dist, predictions, parent_dots, nearest

    candidates = []
    for code in ("h1-iedr", "h2-htsi", "h3-condresid"):
        paths = sorted((ROOT / "docs/downloads").glob(f"kanlergemsdoe1-{code}-*-zeros.tif"))
        if len(paths) != 1:
            raise ValueError(f"Expected exactly one {code} research TIFF, found {len(paths)}")
        path = paths[0]
        own = read_dots(path, foot, grid)
        validation = audit_geotiff(path, foot, labels, mode="zeros", template_tif=ddir / "sample_submission.tif")
        count = int(own.sum())
        overlap = float(near_witness[own].mean()) if count else None
        pairs = [{"site":site, "within_3px_fraction":float(near[site][own].mean()),
                  "spearman_final_dots":binary_rho(own, other, foot),
                  "identical_support":bool(np.array_equal(own, other))} for site,other in dots.items()]
        candidates.append({"id":code.upper(), "file":path.name, "sha256":sha256_file(path),
            "dot_count":count, "validator":validation,
            "literal_lattice_overlap":overlap, "lattice_spearman_final_dots":binary_rho(own,w,foot),
            "lattice_duplicate":bool(overlap is not None and overlap > .70),
            "focus_comparisons":pairs,
            "focus_champions_scope_pass":bool(all(p["within_3px_fraction"] <= .70 and not p["identical_support"]
                                                  and p["spearman_final_dots"] is not None and p["spearman_final_dots"] <= .90 for p in pairs)),
            "surface_gate":"NOT RECORDED BEFORE PLACEMENT",
            "admissible_holdout":"NOT AVAILABLE: prior final maps were built with full-catalogue exclusion",
            "ok_to_submit":False})
    h1 = candidates[0]
    coverage = {"witness_file":witness["dest"], "witness_sha256":witness["sha256"],
                "allowed_footprint_cells":int(allowed.sum()), "uncovered_allowed_cells":uncovered,
                "fraction_allowed_within_3px":float(near_witness[allowed].mean()),
                "minimum_possible_overlap_at_h1_budget":max(0.0, 1.0 - uncovered / h1["dot_count"]),
                "note":"Pigeonhole lower bound applies only at the stated dot budget and allowed domain; it does not prove every nonempty map fails."}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    review = {"reviewed_utc":now, "scope":"Nine pinned focus champions and one registered lattice; not a complete site-wide registry",
              "slots_used":0, "new_experiments":0, "new_rasters":0,
              "lattice_certificate":coverage, "nested_family":nested,
              "focus_sites":focus_rows, "focus_matrix":focus_matrix, "candidates":candidates}
    out = ROOT / "evidence/protocol_audit_20261026.json"
    out.write_text(json.dumps(review,indent=2,allow_nan=False)+"\n")
    (ROOT/"docs/evidence").mkdir(parents=True,exist_ok=True)
    shutil.copyfile(out, ROOT/"docs/evidence/protocol_audit_20261026.json")
    old = json.loads((ROOT/"evidence/run_card_h1_iedr.json").read_text())
    card = {"hypothesis":"H1 IEDR — prior independent-earthquake-density / dilation / magnetic-gradient lane",
            "mechanism":"Historical raster ranked a seismicity-density, geodetic dilation and magnetic-gradient surface; spaced binary emission with a catalogue collar.",
            "named_non_fault_process":"Earthquake swarms induced by geothermal injection or mining; geological contacts can also create magnetic edges.",
            "holdout_dti":{"status":"INADMISSIBLE", "reason":"The archived full map was built with the complete catalogue; no fold-local emission provenance. Canary tested all labels, not withheld-only.",
                "archived_diagnostic":{"evidence_class":"HOLDOUT-DTI (invalid for promotion)","evaluator_version":old["holdout_dti"]["evaluator_version"],
                    "n_withheld_positives":old["holdout_dti"]["n_withheld_positives"],"value":old["holdout_dti"]["pooled_dti"],"ci95":old["holdout_dti"]["ci95"]},
                "valid_value":None,"valid_ci95":None},
            "correlation_overlap_vs_registry":{"scope":review["scope"],"surface_pre_placement":"NOT RECORDED; FAIL CLOSED",
                "final_dots_spearman_vs_lattice":h1["lattice_spearman_final_dots"],
                "final_dots_within_3px_of_lattice":h1["literal_lattice_overlap"],
                "duplicate_threshold":0.70,"literal_uniqueness":"FAIL; STOP",
                "all_focus_champions_pass_final_dot_comparisons":h1["focus_champions_scope_pass"],
                "full_registry_checked":False},
            "raster_sha256":h1["sha256"],
            "validator_output":{"all_checks_passed":h1["validator"]["all_checks_passed"],"checks":h1["validator"]["checks"],
                "shape":h1["validator"]["shape"],"crs":h1["validator"]["crs"],"transform":h1["validator"]["transform"],
                "in_footprint_min":h1["validator"]["in_footprint_min"],"in_footprint_max":h1["validator"]["in_footprint_max"],
                "organizer_template_authenticated":False},
            "submission_name":h1["file"],
            "submission_note":"Research only: IEDR prior artifact; literal registry duplicate; DO NOT SUBMIT.",
            "verdict":"negative", "ok_to_submit":False,"selector_required":True,
            "new_experiments":0,"new_rasters":0,"slots_used":0,"reviewed_utc":now}
    card_path=ROOT/"data/run-card.json"
    card_path.write_text(json.dumps(card,indent=2,allow_nan=False)+"\n")
    shutil.copyfile(card_path, ROOT/"docs/evidence/current_run_card.json")
    print(f"STOP: H1 literal overlap {h1['literal_lattice_overlap']:.6f}; {uncovered} allowed cells outside lattice halo; audit {out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
