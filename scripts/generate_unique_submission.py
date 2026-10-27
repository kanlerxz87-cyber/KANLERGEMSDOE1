#!/usr/bin/env python3
"""
Generate a UNIQUE, format-valid GEMS competition submission GeoTIFF.

Hypothesis H-UNQ-1 (untried in this lane): "blind stepover-radiometric conduit dots".
All nine owner-reported champions (GEMSDOE 24/25/27/28/30/31/32/33/36) derive from ONE
nested dotted support (H19-5 121,131 px -> D2.8 44,090 px -> B=1 prune 40,199 px ->
B=2 prune 37,654 px = h33-2-b2, reported 0.2778) and are near-duplicates of each other.
None uses off-catalogue blind-structure evidence.

This generator places soft dotted predictions on:
  * off-catalogue USGS SGMC geologic-map faults (>300 m from the mapped catalogue)
    dilated 1 px (trace nuclei) - targets faults missing from the USGS/INGENIOUS
    catalogue used for labels, i.e. the hidden fault class the organizer scores last;
  * GeoDAWN radiometric anomalies (assumed band order K, Th, U, TC per the data
    manifest) - potassium/thorium enrichment marks hydrothermal clay alteration along
    buried conduits (Faulds et al. USGS 2019 blind Gabbs Valley; Siler USGS 2023
    structural discontinuities localize strain at stepovers/terminations);
  * GDR 1391 geothermal wells/springs (temperature-weighted) and Quaternary vents
    (corroboration of active fluid pathways);
  * LiDAR scarp context (small weight); penalized near TIGER roads (road edges mimic
    scarps) and zeroed exactly on the mapped catalogue (organizer-masked pixels).
Dots are non-maximum-suppressed at >= 2 px spacing and capped at ~34 000 (champion
budget class) so false-positive mass stays controlled under DTI (alpha=0.2, beta=0.8,
300 m triangular kernel).

Outputs (docs/downloads): -zeros.tif (0 outside footprint, no NaNs anywhere - immune
to the "Predicted values must be in range [0, 1]" rejection), -nan.tif, .zip, -audit.json.
LOCAL VALIDATION ONLY: format checks and uniqueness vs registry rasters. A holdout
DTI on the restored owner label mirror is a diagnostic estimate, not an organizer
receipt, and is not organizer-confirmed. The file is NOT cleared for submission until
a separate selector reviews the run card.
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
from scipy.ndimage import binary_dilation, distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems32.paths import data_dir, docs_dir, downloads_dir
from gems32.submission import write_submission_pair, audit_geotiff

MAX_DOTS = 34_000
NMS_RADIUS_PX = 2
CATALOGUE_COLLAR_PX = 1
MIN_SURFACE = 0.05

# Surface weights (convex, keeps S in [0,1]); documented tuning, not fitted to hidden truth.
W_TRACE, W_RAD, W_WELLS, W_VENTS, W_SCARP = 0.35, 0.25, 0.20, 0.10, 0.05


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


def load_layers(ddir: Path, foot: np.ndarray):
    with rasterio.open(ddir / "external/geodawn_rad_u8.tif") as ds:
        rad = ds.read().astype(np.float32)  # assumed band order: K, Th, U, TC (manifest)
    with rasterio.open(ddir / "external/derived_sgmc_faults_100m_u8.tif") as ds:
        sgmc = ds.read(1) > 0
    with rasterio.open(ddir / "external/lidar_scarp_features_u8.tif") as ds:
        lidar = ds.read().astype(np.float32)
    with rasterio.open(ddir / "external/tiger_road_distance_m.tif") as ds:
        roads = ds.read(1).astype(np.float32)
    return rad, sgmc, lidar, roads


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
                amp = min(max(t / 90.0, 0.0), 1.0)  # 90 C ~ strong geothermal signal
                wells[r, c] = max(wells[r, c], amp)
                n_wells += 1
    # temperature-smoothed well influence (sigma 1.5 px)
    from scipy.ndimage import gaussian_filter
    wells_s = gaussian_filter(wells, sigma=1.5, mode="constant")
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


def build_surface(foot, labels, rad, sgmc, lidar, roads, wells_s, vents):
    H, W = foot.shape
    # Off-catalogue trace nuclei: SGMC faults more than 3 px from mapped catalogue
    off = sgmc & ~labels & ~binary_dilation(labels, iterations=3) & foot
    trace = binary_dilation(off, iterations=1) & foot & ~labels

    # Radiometric anomaly: K + TC (assumed bands 1 and 4)
    k = rad[0] / 255.0
    tc = rad[3] / 255.0
    rad_anom = np.clip(0.5 * k + 0.5 * tc, 0.0, 1.0)

    scarps = np.clip(lidar.max(axis=0) / 255.0, 0.0, 1.0)

    vent_mask = binary_dilation(vents, iterations=2) & foot

    # Road penalty: road edges mimic scarps; fade in from 50 m to 250 m
    road_pen = np.clip((roads - 50.0) / 200.0, 0.0, 1.0)

    S = (W_TRACE * trace.astype(np.float32)
         + W_RAD * rad_anom
         + W_WELLS * wells_s
         + W_VENTS * vent_mask.astype(np.float32)
         + W_SCARP * scarps)
    S = np.clip(S, 0.0, 1.0) * road_pen
    S[~foot] = 0.0
    S[labels] = 0.0
    # keep dots off the 1-px catalogue collar too (voluntary, conservative uniqueness)
    S[binary_dilation(labels, iterations=CATALOGUE_COLLAR_PX)] = 0.0
    return S


def non_max_suppression(S, max_dots=MAX_DOTS, radius=NMS_RADIUS_PX):
    """Greedy NMS: repeatedly take the highest surviving pixel, suppress its neighborhood."""
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


def registry_overlap(dot_y, dot_x, registry_dir: Path):
    """Spearman rho (binary fields) and 3-px dot overlap vs every registry raster."""
    from scipy.ndimage import binary_dilation
    from scipy.spatial import cKDTree
    import rasterio

    y, x = np.nonzero(np.zeros((1, 1)))  # placeholder
    del y, x
    footprint = None
    results = []
    with rasterio.open(data_dir() / "sample_submission.tif") as ds:
        foot = np.isfinite(ds.read(1))
        grid = (ds.shape, ds.crs, ds.transform)
    cand = np.zeros(grid[0], dtype=bool)
    cand[dot_y, dot_x] = True
    cand &= foot
    disk = np.fromfunction(lambda dy, dx: (dy - 3) ** 2 + (dx - 3) ** 2 <= 9, (7, 7))
    near_cand = binary_dilation(cand, structure=disk)

    def binary_rho(a, b):
        a = a & foot
        b = b & foot
        n = int(foot.sum())
        na, nb = int(a.sum()), int(b.sum())
        both = int((a & b).sum())
        den = math.sqrt(na * (n - na) * nb * (n - nb))
        return float((n * both - na * nb) / den) if den else None

    for p in sorted(registry_dir.glob("*.tif")):
        with rasterio.open(p) as ds:
            if (ds.shape, ds.crs, ds.transform) != grid:
                continue
            ref = (ds.read(1) > 0) & foot
        rho = binary_rho(cand, ref)
        overlap = float(near_cand[ref].mean()) if ref.any() else None
        overlap_rev = float(binary_dilation(ref, structure=disk)[cand].mean()) if cand.any() else None
        results.append({
            "file": p.name, "ref_dots": int(ref.sum()),
            "spearman_binary": rho,
            "cand_dots_within_3px_of_ref": overlap,
            "ref_dots_within_3px_of_cand": overlap_rev,
            "identical_support": bool(np.array_equal(cand, ref)),
        })
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-dots", type=int, default=MAX_DOTS)
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--slug", default="h-unq1-blind-stepover-radiometric-conduit-dots")
    ap.add_argument("--candidate-id", default="H-UNQ-1")
    ap.add_argument("--note", default="Unique blind stepover-radiometric conduit dots; off-catalogue SGMC traces; holdout diagnostic only; selector review first")
    args = ap.parse_args()

    if len(args.note) > 140:
        raise SystemExit(f"note exceeds 140 chars ({len(args.note)})")

    ddir = args.data_dir or data_dir()
    out_dir = args.out_dir or downloads_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    template, foot, labels = load_grid(ddir)
    rad, sgmc, lidar, roads = load_layers(ddir, foot)
    wells_s, n_wells, vents, n_vents = load_points(ddir, foot.shape)

    S = build_surface(foot, labels, rad, sgmc, lidar, roads, wells_s, vents)
    dot_y, dot_x, dot_v = non_max_suppression(S, max_dots=args.max_dots)
    n_dots = int(dot_y.size)
    print(f"[H-UNQ-1] surface max={float(S.max()):.3f} dots={n_dots} wells={n_wells} vents={n_vents}")

    arr = np.zeros(foot.shape, dtype=np.float32)
    arr[dot_y, dot_x] = np.clip(dot_v, 0.0, 1.0)
    arr[~foot] = 0.0
    arr[labels] = 0.0
    assert np.isfinite(arr).all() and (arr >= 0).all() and (arr <= 1.0).all()
    assert (arr[~foot] == 0).all() and (arr[labels] == 0).all()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    meta = {
        "candidate_id": args.candidate_id,
        "description": "H-UNQ-1 unique blind stepover-radiometric conduit dots",
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

    # Uniqueness vs registry rasters
    reg = registry_overlap(dot_y, dot_x, Path("data/registry_rasters"))
    print("REGISTRY OVERLAP:")
    for r in reg:
        print("  ", json.dumps(r))

    # Sidecar uniqueness report
    report = {
        "candidate_id": args.candidate_id,
        "hypothesis": "H-UNQ-1 blind stepover-radiometric conduit dots (untried)",
        "generated_utc": ts,
        "n_dots": n_dots,
        "footprint_px": int(foot.sum()),
        "catalogue_px": int(labels.sum()),
        "sha256_zeros": bundle["zeros_tif"]["sha256"],
        "sha256_nan": bundle["nan_tif"]["sha256"],
        "format_audit_zeros": bundle["zeros_tif"],
        "registry_overlap": reg,
        "wells": n_wells, "vents": n_vents,
        "max_dots": args.max_dots, "nms_radius_px": NMS_RADIUS_PX,
    }
    rep_path = out_dir / f"{args.slug}-{ts}-uniqueness.json"
    rep_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"wrote {rep_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
