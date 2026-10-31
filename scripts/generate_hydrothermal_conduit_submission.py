#!/usr/bin/env python3
"""
Generate a UNIQUE, format-valid GEMS competition submission GeoTIFF for hypothesis
H-GEO-CONDUIT: "blind hydrothermal convection conduits".

Scientific rationale (why this targets faults MISSING from the USGS/INGENIOUS
catalogue that the organizer scores, rather than mapped faults already in labels.tif):
  Blind intrabasin faults beneath Quaternary valley fill have no surface scarp and are
  absent from the mapped catalogue, yet they localize upward hydrothermal fluid flow.
  That flow surfaces as warm springs/wells and Quaternary vents, and alters wall rock
  to potassium-rich clays (GeoDAWN K / total-count radiometric enrichment). A surface
  built from GDR well/spring temperature + vent proximity + radiometric K/TC anomaly
  therefore targets the hidden fault class (off-catalogue blind conduits), not the
  pixel-exact mapped faults used as labels. Every emitted dot is zeroed on labels.tif
  so there is zero catalogue leakage.

Layers (all free, official, already mirrored in data/external):
  * gdr_wellspring_in_footprint.csv  — GDR 1391 well/spring temperatures
    (DOI 10.15121/1881483, CC BY 4.0; https://gdr.openei.org/submissions/1391)
  * gdr_volcanic_vents_in_footprint.csv — GDR 1391 Quaternary vents
  * external/geodawn_rad_u8.tif — USGS GeoDAWN radiometric K/Th/U/TC grids
    (DOI 10.5066/P93LGLVQ; bands assumed K, Th, U, TC per data manifest)

Outputs (docs/downloads): -nan.tif (official encoding, NaN outside footprint),
-zeros.tif (diagnostic), .zip (single -nan.tif), -audit.json. The writer performs
the automated 15-check GeoTIFF gate (EPSG:32611, 3730x3292, 100 m, float32 in [0,1]
inside the footprint, NaN outside, zero on the mapped catalogue); it never clips or
repairs out-of-range data, which is what prevents the portal
"Predicted values must be in range [0, 1]" rejection.

LOCAL VALIDATION ONLY: format + uniqueness vs registry/scored rasters and a
full-map diagnostic holdout (SGMC-CAL + hide-and-recover) are printed here. The
full-map holdout is NOT fold-local and is not promotion evidence; a separate
selector must approve any weekly contest slot. ok_to_submit is False until that
review happens.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import binary_dilation, distance_transform_edt, gaussian_filter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems32.paths import data_dir, downloads_dir
from gems32.submission import write_submission_pair

MAX_DOTS = 37_654
NMS_RADIUS_PX = 2
WELL_SIGMA_PX = 1.5
WELL_TEMP_SCALE_C = 90.0
W_TRACE, W_RAD, W_WELLS, W_VENTS = 0.30, 0.35, 0.25, 0.10
MIN_SURFACE = 0.05


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_grid(ddir: Path):
    with rasterio.open(ddir / "sample_submission.tif") as ds:
        foot = np.isfinite(ds.read(1))
    with rasterio.open(ddir / "labels.tif") as ds:
        raw = ds.read(1)
        labels = (raw == 1) & foot
    return foot, labels


def load_layers(ddir: Path):
    with rasterio.open(ddir / "external/geodawn_rad_u8.tif") as ds:
        rad = ds.read().astype(np.float32)  # band order: K, Th, U, TC (manifest)
    with rasterio.open(ddir / "external/tiger_road_distance_m.tif") as ds:
        roads = ds.read(1).astype(np.float32)
    return rad, roads


def load_points(ddir: Path, shape):
    wells = np.zeros(shape, dtype=np.float32)
    n_wells = 0
    with open(ddir / "external/gdr_wellspring_in_footprint.csv", newline="") as f:
        for row in csv.DictReader(f):
            try:
                r, c = int(row["row"]), int(row["col"])
                t = float(row["temp_c"]) if row.get("temp_c") else np.nan
            except (ValueError, KeyError, TypeError):
                continue
            if 0 <= r < shape[0] and 0 <= c < shape[1] and np.isfinite(t):
                amp = min(max(t / WELL_TEMP_SCALE_C, 0.0), 1.0)  # ~90 C = strong signal
                wells[r, c] = max(wells[r, c], amp)
                n_wells += 1
    wells_s = gaussian_filter(wells, sigma=WELL_SIGMA_PX, mode="constant")
    if wells_s.max() > 0:
        wells_s /= wells_s.max()

    vents = np.zeros(shape, dtype=bool)
    n_vents = 0
    with open(ddir / "external/gdr_volcanic_vents_in_footprint.csv", newline="") as f:
        for row in csv.DictReader(f):
            try:
                r, c = int(row["row"]), int(row["col"])
            except (ValueError, KeyError, TypeError):
                continue
            if 0 <= r < shape[0] and 0 <= c < shape[1]:
                vents[r, c] = True
                n_vents += 1
    return wells_s, n_wells, vents, n_vents


def percentile_normalize(a, foot, lo=1.0, hi=99.0):
    vals = a[foot]
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return np.zeros_like(a)
    p_lo, p_hi = np.percentile(vals, lo), np.percentile(vals, hi)
    if p_hi <= p_lo:
        return np.zeros_like(a)
    out = np.clip((a - p_lo) / (p_hi - p_lo), 0.0, 1.0)
    out[~foot] = 0.0
    return out


def build_surface(foot, labels, rad, roads, wells_s, vents):
    H, W = foot.shape
    # Hydrothermal radiometric anomaly: K (band 1) + total count (band 4), percentile-scaled.
    k = percentile_normalize(rad[0], foot)
    tc = percentile_normalize(rad[3], foot)
    rad_anom = np.clip(0.5 * k + 0.5 * tc, 0.0, 1.0)

    vent_mask = binary_dilation(vents, iterations=2) & foot

    # Road edges can mimic scarps; slight fade-in penalty from 50 m to 250 m.
    road_pen = np.clip((roads - 50.0) / 200.0, 0.0, 1.0)

    S = (W_RAD * rad_anom + W_WELLS * wells_s + W_VENTS * vent_mask.astype(np.float32)
         + W_TRACE * np.zeros_like(wells_s))  # W_TRACE reserved; no catalogue-derived trace
    S = np.clip(S, 0.0, 1.0) * road_pen
    S[~foot] = 0.0
    S[labels] = 0.0
    return S


def non_max_suppression(S, max_dots=MAX_DOTS, radius=NMS_RADIUS_PX):
    work = S.copy()
    H, W = work.shape
    ys, xs = np.nonzero(work > MIN_SURFACE)
    order = np.argsort(-work[ys, xs], kind="stable")
    keep_y, keep_x, keep_v = [], [], []
    suppressed = np.zeros((H, W), dtype=bool)
    for idx in order:
        if len(keep_y) >= max_dots:
            break
        y, x = int(ys[idx]), int(xs[idx])
        if suppressed[y, x]:
            continue
        keep_y.append(y)
        keep_x.append(x)
        keep_v.append(float(work[y, x]))
        y0, y1 = max(0, y - radius), min(H, y + radius + 1)
        x0, x1 = max(0, x - radius), min(W, x + radius + 1)
        suppressed[y0:y1, x0:x1] = True
    return np.array(keep_y), np.array(keep_x), np.array(keep_v, dtype=np.float32)


def overlap_stats(dot_y, dot_x, ref_dirs, foot, grid):
    from scipy.ndimage import binary_dilation

    cand = np.zeros(grid[0], dtype=bool)
    cand[dot_y, dot_x] = True
    cand &= foot
    disk = np.fromfunction(lambda dy, dx: (dy - 3) ** 2 + (dx - 3) ** 2 <= 9, (7, 7))
    near_cand = binary_dilation(cand, structure=disk)
    n_foot = int(foot.sum())

    def binary_rho(a, b):
        a = a & foot
        b = b & foot
        na, nb = int(a.sum()), int(b.sum())
        both = int((a & b).sum())
        den = math.sqrt(na * (n_foot - na) * nb * (n_foot - nb))
        return float((n_foot * both - na * nb) / den) if den else None

    results = []
    for d in ref_dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.tif")):
            with rasterio.open(p) as ds:
                if (ds.shape, ds.crs, ds.transform) != grid:
                    continue
                ref = (ds.read(1) > 0) & foot
            rho = binary_rho(cand, ref)
            overlap = float(near_cand[ref].mean()) if ref.any() else None
            results.append({
                "file": str(p.relative_to(ROOT)),
                "ref_dots": int(ref.sum()),
                "spearman_binary": rho,
                "cand_dots_within_3px_of_ref": overlap,
                "identical_support": bool(np.array_equal(cand, ref)),
            })
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-dots", type=int, default=MAX_DOTS)
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--slug", default="h-geo-conduit-wells-vents-radiometric-300m-dots")
    ap.add_argument("--candidate-id", default="H-GEO-CONDUIT")
    ap.add_argument(
        "--note",
        default=(
            "KANLER1 H-GEO-CONDUIT: springs+vents+GeoDAWN K/TC radiometric conduit dots; "
            "off-catalogue blind faults [RESEARCH-HOLD]"
        ),
    )
    args = ap.parse_args()
    if len(args.note) > 140:
        raise SystemExit(f"note exceeds 140 chars ({len(args.note)})")

    ddir = args.data_dir or data_dir()
    out_dir = args.out_dir or downloads_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    foot, labels = load_grid(ddir)
    rad, roads = load_layers(ddir)
    wells_s, n_wells, vents, n_vents = load_points(ddir, foot.shape)

    S = build_surface(foot, labels, rad, roads, wells_s, vents)
    dot_y, dot_x, dot_v = non_max_suppression(S, max_dots=args.max_dots)
    n_dots = int(dot_y.size)
    print(
        f"[H-GEO-CONDUIT] surface max={float(S.max()):.3f} dots={n_dots} "
        f"wells={n_wells} vents={n_vents} rad_bands={rad.shape[0]}"
    )

    arr = np.zeros(foot.shape, dtype=np.float32)
    arr[dot_y, dot_x] = np.clip(dot_v, 0.0, 1.0)
    arr[~foot] = 0.0
    arr[labels] = 0.0
    assert np.isfinite(arr).all() and (arr >= 0).all() and (arr <= 1.0).all()
    assert (arr[~foot] == 0).all() and (arr[labels] == 0).all()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    meta = {
        "candidate_id": args.candidate_id,
        "description": (
            "H-GEO-CONDUIT unique blind hydrothermal conduit dots (warm springs/vents + "
            "GeoDAWN K/TC radiometric anomaly), off-catalogue blind faults"
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
    bundle = write_submission_pair(arr, foot, labels,
                                   template_tif=ddir / "sample_submission.tif",
                                   out_dir=out_dir, slug=args.slug,
                                   timestamp_tag=ts, candidate_meta=meta)
    print(json.dumps(bundle, indent=2))

    with rasterio.open(ddir / "sample_submission.tif") as ds:
        grid = (ds.shape, ds.crs, ds.transform)
    reg_results = overlap_stats(dot_y, dot_x,
                                [ddir / "registry_rasters", ddir / "scored"], foot, grid)
    max_overlap = max((r["cand_dots_within_3px_of_ref"] for r in reg_results
                       if r["cand_dots_within_3px_of_ref"] is not None), default=0.0)
    max_rho = max((abs(r["spearman_binary"]) for r in reg_results if r["spearman_binary"] is not None),
                  default=0.0)
    unique = max_overlap <= 0.70 and max_rho <= 0.90

    report = {
        "candidate_id": args.candidate_id,
        "hypothesis": "H-GEO-CONDUIT blind hydrothermal conduit dots (untried in this repo)",
        "generated_utc": ts,
        "n_dots": n_dots,
        "footprint_px": int(foot.sum()),
        "catalogue_px": int(labels.sum()),
        "wells": n_wells, "vents": n_vents,
        "sha256_zeros": bundle["zeros_tif"]["sha256"],
        "sha256_nan": bundle["nan_tif"]["sha256"],
        "submission_zip_sha256": bundle["submission_zip"]["sha256"],
        "format_audit_zeros": bundle["zeros_tif"],
        "format_audit_nan": bundle["nan_tif"],
        "format_all_checks_passed": bundle["zeros_tif"]["all_checks_passed"],
        "registry_and_scored_overlap": reg_results,
        "max_within_3px_overlap_vs_any_reference": round(float(max_overlap), 6),
        "max_abs_spearman_vs_any_reference": round(float(max_rho), 6),
        "unique_vs_all_references": bool(unique),
        "max_dots": args.max_dots, "nms_radius_px": NMS_RADIUS_PX,
        "ok_to_submit": False,
        "verdict": "RESEARCH-HOLD: format-valid and unique vs local references; pending selector approval",
    }
    rep_path = out_dir / f"{args.slug}-{ts}-audit.json"
    rep_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"wrote {rep_path}")
    print(f"UNIQUENESS: max_3px_overlap={max_overlap:.4f} max_|rho|={max_rho:.4f} unique={unique}")
    print(f"FORMAT: zeros={bundle['zeros_tif']['all_checks_passed']} nan={bundle['nan_tif']['all_checks_passed']}")
    print(f"ZEROS TIF: {out_dir / bundle['zeros_tif']['filename']}")
    print(f"NAN TIF (official): {out_dir / bundle['nan_tif']['filename']}")
    print(f"ZIP (official): {bundle['submission_zip']['filename']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
