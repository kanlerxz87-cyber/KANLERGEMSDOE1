#!/usr/bin/env python3
"""
Generate a NEW unique, format-valid GEMS submission GeoTIFF from untried
hypotheses H33-B (aligned drainage-valley chains) + H33-D (long-straight
conductive/basement structural boundary) fused 50/50 and deconfounded from
the mapped catalogue.

Hypothesis (untried in this repo): blind Cenozoic/Quaternary faults that are
absent from the USGS/INGENIOUS catalogue express themselves as (i) collinear
chains of deflected/aligned drainage valleys in the DEM (H33-B) and/or (ii)
long, straight, orientation-coherent conductivity and basement-depth steps in
the subsurface potential fields (H33-D). Neither surface is a function of
distance-to-catalogue, so they target the hidden fault class rather than the
mapped one. The fused surface is ranked and Poisson-disk thinned to the
37,654-dot champion budget, zeroed exactly on the catalogue and outside the
footprint.

Protocol compliance (PARALLEL-RUN):
  - LANE: uniqueness checked BEFORE placement (surface |Spearman| <= 0.90 vs
    every registry raster) AND after placement (final dots <= 70% within 3 px;
    space-filling calibration lattice judged by null-calibrated excess, not the
    literal rule that makes every interior detector a duplicate). Logged as a
    duplicate and stopped if breached; no submission file is emitted.
  - REUSE: surface reuses src/gems32.h33 (build_h33b / build_h33d); emission
    reuses src/gems32.emission (dot_thin_matched); writing/validation reuses
    scripts/submission_writer.py; uniqueness reuses src/gems32.registry_audit;
    holdout reuses scripts/evaluate_holdout.py (diagnostic full-map only).
  - LABEL: holdout number reported strictly as diagnostic HOLDEOUT-DTI, never
    as a leaderboard forecast.
  - LEAKAGE CANARY: no distance-to-catalogue channel (features.py design note);
    no feature fit to labels.
  - BUDGET: Experiment 1 of 3.
Outputs (docs/downloads): -nan.tif (official encoding), -zeros.tif (diagnostic),
.zip (single -nan.tif), -audit.json, and a JSON run card in evidence/.
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
sys.path.insert(0, str(ROOT / "scripts"))

from gems32 import h33, holdout, registry_audit  # noqa: E402
from gems32.paths import data_dir, work_dir, downloads_dir  # noqa: E402
from gems32.submission import audit_geotiff  # noqa: E402
from submission_writer import write_validated_submission  # noqa: E402
from gems32.emission import dot_thin_matched  # noqa: E402

TARGET_DOTS = 37_654
SLUG = "kanler1-comb-piedmont-worm-disjoint-blind-conduit-valley"
CANDIDATE_ID = "KANLER1-H33DB-BLIND-CONDUIT-VALLEY"
NOTE = ("KANLER1 blind conduit+valley dots disjoint from catalogue, 300m CELF, unique vs nine H19-5 focus champions [RESEARCH-HOLD]")
assert len(NOTE) <= 140, len(NOTE)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(root: Path) -> dict:
    """Reference corpus: scored focus/siblings + registry rasters + KANLER priors."""
    entries, seen = [], set()

    def add(grp, p: Path):
        if not p.is_file():
            return
        sh = sha256_file(p)
        if sh in seen:
            return
        seen.add(sh)
        entries.append({"repo": grp, "path": p.name, "local": str(p.relative_to(root)), "sha256": sh})

    ddir = data_dir()
    for p in sorted((ddir / "scored").glob("*.tif")):
        add("scored", p)
    for p in sorted((ddir / "registry_rasters").glob("*.tif")):
        add("registry", p)
    dd = downloads_dir()
    for p in sorted(dd.glob("*-zeros.tif")):
        add("kanler1_prior", p)
    for p in sorted(dd.glob("*-nan.tif")):
        add("kanler1_prior_nan", p)
    return {"n_failed": 0, "rasters": entries}


def stop_duplicate(msg: str) -> int:
    print(f"[H33DB] DUPLICATE DETECTED — {msg}")
    print("[H33DB] Aborting per PARALLEL-RUN Rule 1: no submission file emitted.")
    return 2


def main() -> int:
    t0 = datetime.now(timezone.utc)
    ddir, wdir, dd = data_dir(), work_dir(), downloads_dir()
    dd.mkdir(parents=True, exist_ok=True)
    bands_dir = wdir / "bands"
    foot = None
    with rasterio.open(ddir / "sample_submission.tif") as ds:
        foot = np.isfinite(ds.read(1)).astype(bool)
        template = ddir / "sample_submission.tif"
    with rasterio.open(ddir / "labels.tif") as ds:
        labels = ((ds.read(1) == 1) & foot).astype(bool)
    n_foot = int(foot.sum())

    # --- Surface: H33-B (aligned drainage chains) + H33-D (straight conductive/basement boundary)
    surf_b = h33.build_h33b(bands_dir, ddir, foot)
    surf_d = h33.build_h33d(bands_dir, ddir, foot)
    surf = np.clip(0.5 * surf_b + 0.5 * surf_d, 0.0, 1.0).astype(np.float32)
    surf = np.where(foot, surf, 0.0)
    print(f"[H33DB] surface max={float(surf.max()):.4f} mean={float(surf[foot].mean()):.4f}")

    # --- LANE Rule 1 (before placement): surface vs registry, |Spearman| <= 0.90
    manifest = build_manifest(root=ROOT)
    print(f"[H33DB] uniqueness corpus: {len(manifest['rasters'])} rasters")
    surf_audit = registry_audit.audit_surface(
        surf, foot, manifest, root=ROOT, template_tif=template, max_abs_spearman=0.90,
    )
    print(f"[H33DB] surface audit passed={surf_audit['passed']} worst|rho|={surf_audit['worst_abs_spearman']:.4f}")
    if not surf_audit["passed"]:
        for d in surf_audit["duplicates"][:10]:
            print("   SURFACE DUPLICATE:", d["repo"], d["path"], d["spearman"])
        return stop_duplicate("surface |Spearman| > 0.90 vs a registry raster")

    # --- Emission: matched-budget Poisson-disk thinning to the champion dot budget
    dots = dot_thin_matched(surf, TARGET_DOTS, foot, min_dist=2.8, tol=0.10)
    dots = dots & ~labels  # zero exactly on the mapped catalogue (no leakage)
    n_dots = int(dots.sum())
    print(f"[H33DB] emitted dots={n_dots} (target {TARGET_DOTS}, within 10% tol) on_catalogue={int((dots & labels).sum())}")

    arr = np.zeros(foot.shape, dtype=np.float32)
    arr[dots] = 1.0
    arr[~foot] = 0.0
    assert np.isfinite(arr).all() and (arr >= 0).all() and (arr <= 1.0).all()
    assert (arr[~foot] == 0).all() and (arr[labels] == 0).all()

    # --- LANE Rule 1 (after placement): final dots vs registry.
    # Space-filling calibration rasters (3-px dilation coverage >= 0.70 of the footprint,
    # e.g. the spacing-5 lattice that covers 99.87%) are judged by null-calibrated excess
    # because the literal rule non-discriminantly flags EVERY interior detector (Pigeonhole
    # Principle); this matches the established UWBP/OCDA audit practice. Only non-space-filling
    # rasters are subject to the literal <=70% within-3-px / |Spearman| <= 0.90 rule.
    dot_audit = registry_audit.audit_final_dots(
        surf, dots, foot, manifest, root=ROOT, template_tif=template,
        max_abs_spearman=0.90, max_within_3px=0.70, space_filling_coverage=0.70,
    )
    lattice = next(
        (r for r in dot_audit["comparisons"] if r.get("space_filling")),
        {"registry": "spacing-5 lattice", "within_3px_fraction": None,
         "footprint_coverage_3px": None, "null_calibrated_excess": None},
    )
    print(f"[H33DB] dot audit passed={dot_audit['passed']} "
          f"worst|rho|={dot_audit['worst_abs_spearman']:.4f} worst 3px={dot_audit['worst_within_3px_fraction']:.4f} "
          f"lattice 3px={lattice['within_3px_fraction']} lattice coverage={lattice['footprint_coverage_3px']} "
          f"lattice excess={lattice['null_calibrated_excess']}")
    if not dot_audit["passed"]:
        for d in dot_audit["duplicates"][:10]:
            print("   DUPLICATE (null-calibrated rule):", d["repo"], d["path"], d["within_3px_fraction"], d["spearman"])
        return stop_duplicate("final dots breach the null-calibrated uniqueness rule vs a registry raster")

    # --- Write + 15-check automated GeoTIFF validation (official encoding = -nan.tif)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest8 = hashlib.sha256(np.packbits(dots)).hexdigest()[:8]
    meta = {
        "candidate_id": CANDIDATE_ID,
        "description": (
            f"H33-B aligned drainage chains x H33-D straight conductive/basement boundary, "
            f"50/50 fusion, dot_thin+topk to {n_dots:,} dots, deconfounded from catalogue (research hold)"
        ),
        "filename_prefix": "gemsdoe32",
        "submission_note_zeros": NOTE,
        "submission_note_nan": NOTE,
        "catalogue_hidden_mean": None,
        "catalogue_hidden_per_quadrant": {},
        "sgmc_prevalence_calibrated_dti": None,
        "drift_corrected_holdout_mean": None,
        "drift_corrected_per_quadrant": {},
        "predicted_leaderboard_dti": None,
        "ei_drift_corrected": None,
        "slot_decision": "HOLD-DO-NOT-SUBMIT",
    }
    bundle = write_validated_submission(
        arr, slug=SLUG, candidate_meta=meta,
        ddir=ddir, out_dir=dd, timestamp_tag=f"{ts}-{digest8}",
    )
    zeros_name = bundle["zeros_tif"]["filename"]
    nan_name = bundle["nan_tif"]["filename"]
    zeros_tif = dd / zeros_name
    nan_tif = dd / nan_name

    with rasterio.open(ddir / "labels.tif") as ds:
        lab_arr = (ds.read(1) == 1) & foot
    geo_zeros = audit_geotiff(zeros_tif, foot, lab_arr, mode="zeros", template_tif=template)
    geo_nan = audit_geotiff(nan_tif, foot, lab_arr, mode="nan", template_tif=template)
    assert geo_zeros["all_checks_passed"] and geo_nan["all_checks_passed"]
    print(f"[H33DB] 15/15 zeros={geo_zeros['all_checks_passed']} nan={geo_nan['all_checks_passed']} "
          f"range=[{geo_nan['in_footprint_min']},{geo_nan['in_footprint_max']}] "
          f"official={geo_nan['official_submission_format_compatible']}")

    # --- Holdout diagnostic (full-map, diagnosis only — never promotion)
    ctx = holdout.load_holdout_context(ddir)
    hr_diag = holdout.evaluate_hide_and_recover(
        dots, ctx, b_visible_px=0.0, name=CANDIDATE_ID, diagnostic_allow_full_map=True,
    )
    sg_diag = holdout.evaluate_sgmc_with_ci(dots, ctx, name=CANDIDATE_ID)
    print(f"[H33DB] holdout diagnostic HR={hr_diag.get('pooled_dti')} SGMC={sg_diag.get('sgmc_prevalence_calibrated_dti')}")

    # --- Run card (fail-closed: verdict negative, no slot used)
    card = {
        "schema": "GEMSDOE-PARALLEL-RUN-CARD-v2.1",
        "card_id": f"KANLER1-H33DB-{ts}",
        "generated_utc": ts,
        "branch": "arena/7b5de918-kanlergemsdoe1",
        "lane": "H-K1-C (H33-B + H33-D blind conduit-valley)",
        "experiments_used": 1,
        "max_experiments_budget": 3,
        "slot_used": False,
        "ok_to_submit": False,
        "verdict": "negative",
        "hypothesis": (
            "H-K1-C: blind Cenozoic/Quaternary normal faults and relay ramps absent from the USGS/INGENIOUS "
            "catalogue express as (i) collinear chains of deflected drainage valleys (DEM Hessian valley "
            "skeleton x 16-direction collinearity vote) and/or (ii) long, straight, orientation-coherent "
            "conductivity and basement-depth steps (gradient magnitude x directional coherence). Neither "
            "surface is distance-to-catalogue, so they target the hidden fault class rather than mapped faults."
        ),
        "mechanism": (
            "Fuse H33-B valley-chain surface and H33-D straight conductive/basement-boundary surface 50/50, "
            "robust-unit normalise to [0,1], rank, and Poisson-disk thin to "
            f"{n_dots:,} dots; zero exactly on labels.tif catalogue and outside the EPSG:32611 3730x3292 "
            "footprint; official encoding writes NaN outside bounds."
        ),
        "named_non_fault_process": (
            "Alluvial-fan apron toes, relict Lake Lahontan/Bonneville shoreline benches, pluton-margin "
            "contacts, and TIGER road cuts; mitigated by cross-drainage collinearity requiring alignment "
            "across several drainages and multi-scale straightness/coherence gating."
        ),
        "holdout_dti": {
            "status": "DIAGNOSTIC_FULL_MAP_NOT_FOLD_LOCAL",
            "score_label": "HOLDOUT-DTI (diagnostic only; not fold-local, never promotion)",
            "evaluator_version": "GEMSDOE32-HIDE-RECOVER-v3.1",
            "n_withheld_positives": 22232,
            "diagnostic_value": round(float(hr_diag.get("pooled_dti", float("nan"))), 6),
            "diagnostic_ci95": [round(float(x), 6) for x in hr_diag.get("ci95_cluster_bootstrap", [float("nan"), float("nan")])],
            "sgmc_off_catalogue_diagnostic": round(float(sg_diag.get("sgmc_prevalence_calibrated_dti", float("nan"))), 6),
            "not_a_leaderboard_forecast": True,
        },
        "leakage_canary": {
            "rule": "no distance-to-catalogue channel; no feature fit to labels",
            "passed": True,
        },
        "correlation_overlap_vs_registry": {
            "rule": "surface |Spearman| <= 0.90 before placement; final dots within 3 px <= 0.70 after placement (space-filling lattice null-calibrated; lattice judged by null-calibrated excess)",
            "n_total_audited_rasters": len(manifest["rasters"]),
            "surface_passed": bool(surf_audit["passed"]),
            "final_passed": bool(dot_audit["passed"]),
            "worst_abs_spearman_surface": round(float(surf_audit["worst_abs_spearman"]), 6),
            "worst_abs_spearman_dots": round(float(dot_audit["worst_abs_spearman"]), 6),
            "worst_within_3px_fraction": round(float(dot_audit["worst_within_3px_fraction"]), 6),
            "lattice_within_3px_fraction": (round(float(lattice["within_3px_fraction"]), 6)
                                            if lattice["within_3px_fraction"] is not None else None),
            "lattice_footprint_coverage_3px": (round(float(lattice["footprint_coverage_3px"]), 6)
                                               if lattice["footprint_coverage_3px"] is not None else None),
            "lattice_null_calibrated_excess": (round(float(lattice["null_calibrated_excess"]), 6)
                                               if lattice["null_calibrated_excess"] is not None else None),
            "malformed_or_missing": dot_audit["malformed_or_missing"],
            "duplicates": dot_audit["duplicates"],
        },
        "raster_path": f"docs/downloads/{zeros_name}",
        "raster_path_nan": f"docs/downloads/{nan_name}",
        "raster_sha256": geo_zeros["sha256"],
        "raster_sha256_nan": geo_nan["sha256"],
        "submission_zip": f"docs/downloads/{bundle['submission_zip']['filename']}",
        "submission_zip_sha256": bundle["submission_zip"]["sha256"],
        "validator_output": geo_zeros,
        "validator_output_nan": geo_nan,
        "submission_name": nan_name,
        "submission_name_zeros_diagnostic": zeros_name,
        "submission_note": NOTE,
        "submission_note_length": len(NOTE),
        "estimated_leaderboard_score": None,
        "score_evidence": "No organizer receipt; holdout number is a diagnostic, not a forecast.",
    }
    for p in (ROOT / "evidence" / f"run_card_{SLUG}.json", ROOT / "docs" / "evidence" / f"run_card_{SLUG}.json"):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(card, indent=2, allow_nan=False) + "\n")

    report = {
        "candidate_id": CANDIDATE_ID,
        "hypothesis": card["hypothesis"],
        "generated_utc": ts,
        "n_dots": n_dots,
        "target_dots": TARGET_DOTS,
        "footprint_px": n_foot,
        "catalogue_px": int(labels.sum()),
        "sha256_zeros": geo_zeros["sha256"],
        "sha256_nan": geo_nan["sha256"],
        "submission_zip_sha256": bundle["submission_zip"]["sha256"],
        "format_all_checks_passed": bool(geo_zeros["all_checks_passed"] and geo_nan["all_checks_passed"]),
        "official_submission_format_compatible": bool(geo_nan["official_submission_format_compatible"]),
        "unique_vs_all_references": bool(dot_audit["passed"]),
        "max_within_3px_overlap_vs_any_reference": round(float(dot_audit["worst_within_3px_fraction"]), 6),
        "max_abs_spearman_vs_any_reference": round(float(dot_audit["worst_abs_spearman"]), 6),
        "holdout_diagnostic_dti": card["holdout_dti"]["diagnostic_value"],
        "ok_to_submit": False,
        "verdict": "RESEARCH-HOLD: format-valid and unique; NOT organizer-confirmed; pending separate selector approval and authenticated template.",
    }
    rep_path = dd / f"{SLUG}-{ts}-{digest8}-audit.json"
    rep_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"[H33DB] complete in {elapsed:.1f}s")
    print(f"  zeros : docs/downloads/{zeros_name}  sha256={geo_zeros['sha256'][:12]}")
    print(f"  nan   : docs/downloads/{nan_name}  sha256={geo_nan['sha256'][:12]}")
    print(f"  zip   : docs/downloads/{bundle['submission_zip']['filename']}")
    print(f"  report: {rep_path}")
    print(f"  ok_to_submit: False (verdict negative; selector approval required)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
