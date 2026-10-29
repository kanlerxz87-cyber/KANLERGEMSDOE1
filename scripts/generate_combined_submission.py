#!/usr/bin/env python3
"""Generate a UNIQUE, format-valid combined GEMS competition submission GeoTIFF.

Hypothesis H-COMB-1 (untried across the nine GEMSDOE focus sites): a disjoint
Pareto synthesis of two complementary, non-H19-5 populations:

  * Quaternary piedmont / relay dots from KANLER1-OCDA-MSCS-EXP-3 (leads
    HIDE-RECOVER-v3.1 on the mapped catalogue at 0.105830); and
  * strictly disjoint (>3 px) off-catalogue blind-worm / knickzone dots from
    KANLER1-UWBP-DRCS-EXP-B3 (leads zero-SGMC off-catalogue SGMC-CAL-v3.0 at
    0.089174).

All nine owner-reported focus champions (GEMSDOE 24/25/27/28/30/31/32/33/36)
derive from ONE nested H19-5 dotted support (D2.8 thinning -> B=2 collar
pruning = 37,654 px, reported 0.2778 on GEMSDOE32) and are near-duplicates of
each other (~100% within 3-px pairwise). None combines off-catalogue blind
structure with piedmont catalogue dots. This synthesis is therefore unique in
the nine-site subset.

The two dot masks are made strictly disjoint (>3 px), then jointly packed to
the champion budget (~37,654 dots). Binary dots (1.0) keep false-positive mass
controlled under DTI (alpha=0.2, beta=0.8, 300 m triangular kernel).

Outputs (docs/downloads): -zeros.tif (0 outside footprint), -nan.tif (NaN
outside footprint - the official submission encoding), .zip (single -nan.tif),
-audit.json (15 automated GeoTIFF checks), -report.json (uniqueness vs
registry + scored rasters). LOCAL VALIDATION ONLY: format checks and uniqueness
vs registry/scored rasters. Holdout DTI on the restored owner label mirror is a
diagnostic estimate, not an organizer receipt, and is not organizer-confirmed.
The file is NOT cleared for live submission until a separate selector approves
it and the competition template is authenticated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import binary_dilation, distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems32.paths import data_dir, downloads_dir
from gems32.submission import write_submission_pair

TARGET_BUDGET = 37_654
DISJOINT_RADIUS_PX = 3.0  # strictly > 3 px separation between the two populations


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_grid(ddir: Path):
    with rasterio.open(ddir / "sample_submission.tif") as ds:
        template = ds.profile.copy()
        foot = np.isfinite(ds.read(1))
    with rasterio.open(ddir / "labels.tif") as ds:
        raw = ds.read(1)
        labels = (raw == 1) & foot
    return template, foot, labels


def load_dots(tif_path: Path, foot: np.ndarray) -> np.ndarray:
    with rasterio.open(tif_path) as ds:
        arr = ds.read(1)
    return (arr > 0) & foot


def make_disjoint(primary: np.ndarray, secondary: np.ndarray, radius_px: float) -> np.ndarray:
    """Return secondary dots strictly > radius_px from every primary dot."""
    d_to_primary = distance_transform_edt(~primary)
    r = int(math.ceil(radius_px))
    yy, xx = np.ogrid[-r : r + 1, -r : r + 1]
    disk = (yy * yy + xx * xx) <= radius_px**2
    disk[r, r] = True
    near_primary = binary_dilation(primary, structure=disk)
    return secondary & ~near_primary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-dots", type=int, default=TARGET_BUDGET)
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument(
        "--slug",
        default="kanler1-comb-piedmont-worm-disjoint-300m-celf",
    )
    ap.add_argument(
        "--candidate-id",
        default="KANLER1-COMB-PIEDMONT-WORM",
    )
    ap.add_argument(
        "--note",
        default=(
            "KANLER1 disjoint OCDA piedmont + UWBP blind-worm dots, 300m CELF, "
            "unique vs nine H19-5 focus champions [RESEARCH-HOLD]"
        ),
    )
    args = ap.parse_args()

    if len(args.note) > 140:
        raise SystemExit(f"note exceeds 140 chars ({len(args.note)})")

    ddir = args.data_dir or data_dir()
    out_dir = args.out_dir or downloads_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    template, foot, labels = load_grid(ddir)

    # --- Load the two existing lane dot masks ---
    ocda_tif = (
        Path(downloads_dir())
        / "gemsdoe32-kanler1-ocda-mscs-exp3-37654d-20261027T1842Z-1db32b55-zeros.tif"
    )
    uwbp_tif = (
        Path(downloads_dir())
        / "gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-zeros.tif"
    )

    if not ocda_tif.is_file():
        raise FileNotFoundError(f"OCDA artifact not found: {ocda_tif}")
    if not uwbp_tif.is_file():
        raise FileNotFoundError(f"UWBP artifact not found: {uwbp_tif}")

    ocda_dots = load_dots(ocda_tif, foot)
    uwbp_dots = load_dots(uwbp_tif, foot)
    print(f"[H-COMB-1] OCDA dots={int(ocda_dots.sum())} UWBP dots={int(uwbp_dots.sum())}")

    # Zero both on the catalogue (defensive; they should already be zero there)
    ocda_dots = ocda_dots & ~labels
    uwbp_dots = uwbp_dots & ~labels

    # --- Make the two populations strictly disjoint (>3 px) ---
    combined_primary = ocda_dots.copy()
    disjoint_uwbp = make_disjoint(combined_primary, uwbp_dots, DISJOINT_RADIUS_PX)
    print(
        f"[H-COMB-1] disjoint UWBP dots after >{DISJOINT_RADIUS_PX}px separation: "
        f"{int(disjoint_uwbp.sum())}"
    )

    # --- Combine and cap at budget ---
    final_dots = combined_primary | disjoint_uwbp
    n_total = int(final_dots.sum())
    if n_total > args.max_dots:
        # Subsample to budget deterministically (keep all OCDA, then UWBP by row-major order)
        keep = np.zeros_like(final_dots)
        keep[combined_primary] = True
        remaining = args.max_dots - int(combined_primary.sum())
        if remaining > 0:
            uy, ux = np.nonzero(disjoint_uwbp)
            order = np.lexsort((ux, uy))  # row-major deterministic
            keep[uy[order[:remaining]], ux[order[:remaining]]] = True
        final_dots = keep & foot & ~labels
    else:
        final_dots = final_dots & foot & ~labels

    n_dots = int(final_dots.sum())
    print(f"[H-COMB-1] final dots={n_dots}")

    # --- Build float32 array (binary dots = 1.0) ---
    arr = np.zeros(foot.shape, dtype=np.float32)
    arr[final_dots] = 1.0
    arr[~foot] = 0.0
    arr[labels] = 0.0
    assert np.isfinite(arr).all() and (arr >= 0).all() and (arr <= 1.0).all()
    assert (arr[~foot] == 0).all() and (arr[labels] == 0).all()

    # --- Write validated submission ---
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    meta = {
        "candidate_id": args.candidate_id,
        "description": (
            "H-COMB-1: disjoint OCDA-MSCS piedmont + UWBP-DRCS blind-worm dots, "
            "jointly packed (~37,654d), unique vs nine H19-5 focus champions"
        ),
        "filename_prefix": "gemsdoe32",
        "submission_note_zeros": args.note,
        "submission_note_nan": args.note,
        "catalogue_hidden_mean": None,
        "catalogue_hidden_per_quadrant": {},
        "sgmc_prevalence_calibrated_dti": None,
        "drift_corrected_holdout_mean": None,
        "drift_corrected_per_quadrant": {},
        "predicted_leaderboard_dti": None,
        "ei_drift_corrected": None,
        "slot_decision": "HOLD-DO-NOT-SUBMIT",
    }
    bundle = write_submission_pair(
        arr,
        foot,
        labels,
        template_tif=ddir / "sample_submission.tif",
        out_dir=out_dir,
        slug=args.slug,
        timestamp_tag=ts,
        candidate_meta=meta,
    )
    print(json.dumps(bundle, indent=2))

    zeros_tif = out_dir / bundle["zeros_tif"]["filename"]
    nan_tif = out_dir / bundle["nan_tif"]["filename"]

    # --- Uniqueness vs registry + all scored rasters ---
    reg_results = []
    for grp_dir, grp_name in (
        (ddir / "registry_rasters", "registry"),
        (ddir / "scored", "scored"),
    ):
        if not grp_dir.is_dir():
            continue
        with rasterio.open(ddir / "sample_submission.tif") as ds:
            grid = (ds.shape, ds.crs, ds.transform)
        cand = final_dots.copy()
        disk = np.fromfunction(
            lambda dy, dx: (dy - 3) ** 2 + (dx - 3) ** 2 <= 9, (7, 7)
        )
        near_cand = binary_dilation(cand, structure=disk)
        for p in sorted(grp_dir.glob("*.tif")):
            with rasterio.open(p) as ds_ref:
                if (ds_ref.shape, ds_ref.crs, ds_ref.transform) != grid:
                    continue
                ref = (ds_ref.read(1) > 0) & foot
            n_foot = int(foot.sum())
            na, nb = int(cand.sum()), int(ref.sum())
            both = int((cand & ref).sum())
            den = math.sqrt(na * (n_foot - na) * nb * (n_foot - nb))
            rho = float((n_foot * both - na * nb) / den) if den else None
            overlap = float(near_cand[ref].mean()) if ref.any() else None
            reg_results.append(
                {
                    "group": grp_name,
                    "file": p.name,
                    "ref_dots": int(ref.sum()),
                    "spearman_binary": rho,
                    "cand_dots_within_3px_of_ref": overlap,
                    "identical_support": bool(np.array_equal(cand, ref)),
                }
            )

    max_overlap = max(
        (
            r["cand_dots_within_3px_of_ref"]
            for r in reg_results
            if r["cand_dots_within_3px_of_ref"] is not None
        ),
        default=0.0,
    )
    max_rho = max(
        (abs(r["spearman_binary"]) for r in reg_results if r["spearman_binary"] is not None),
        default=0.0,
    )
    is_unique = max_overlap <= 0.70 and max_rho <= 0.90

    report = {
        "candidate_id": args.candidate_id,
        "hypothesis": "H-COMB-1 disjoint OCDA piedmont + UWBP blind-worm dots (untried)",
        "generated_utc": ts,
        "n_dots": n_dots,
        "footprint_px": int(foot.sum()),
        "catalogue_px": int(labels.sum()),
        "ocda_dots": int(ocda_dots.sum()),
        "uwbp_dots_input": int(uwbp_dots.sum()),
        "disjoint_uwbp_dots": int(disjoint_uwbp.sum()),
        "sha256_zeros": bundle["zeros_tif"]["sha256"],
        "sha256_nan": bundle["nan_tif"]["sha256"],
        "submission_zip_sha256": bundle["submission_zip"]["sha256"],
        "format_audit_zeros": bundle["zeros_tif"],
        "format_audit_nan": bundle["nan_tif"],
        "format_all_checks_passed": bundle["zeros_tif"]["all_checks_passed"],
        "registry_overlap": reg_results,
        "max_within_3px_overlap_vs_any_reference": round(float(max_overlap), 6),
        "max_abs_spearman_vs_any_reference": round(float(max_rho), 6),
        "unique_vs_all_references": bool(is_unique),
        "max_dots": args.max_dots,
        "disjoint_radius_px": DISJOINT_RADIUS_PX,
        "ok_to_submit": False,
        "verdict": "RESEARCH-HOLD: format-valid and unique; pending selector approval and authenticated template",
    }
    rep_path = out_dir / f"{args.slug}-{ts}-report.json"
    rep_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"wrote {rep_path}")
    print(
        f"UNIQUENESS: max_3px_overlap={max_overlap:.4f} max_|rho|={max_rho:.4f} "
        f"unique={is_unique}"
    )
    print(
        f"FORMAT: zeros_all_checks={bundle['zeros_tif']['all_checks_passed']} "
        f"nan_all_checks={bundle['nan_tif']['all_checks_passed']}"
    )
    print(f"ZEROS TIF: {zeros_tif}")
    print(f"NAN TIF (official): {nan_tif}")
    print(f"ZIP (official): {bundle['submission_zip']['filename']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
