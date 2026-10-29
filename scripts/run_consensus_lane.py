#!/usr/bin/env python3
"""Experiment C1 (H-CONS-1): multi-lane agreement consensus raster.

Hypothesis (falsifiable): a pixel supported by >= 2 independently built, unique, non-leaking
fault-dot lanes (each with a dot within 3 px) is more likely a true off-catalogue fault than a
single lane's dot, so keeping only agreement pixels lifts the zero-SGMC proxy over the best
single contributing lane (UWBP-DRCS EXP-B3, 0.0892) without copying any lane.

Lanes = repo-held candidate rasters that pass the uniqueness screen against the nine focus sites
and are NOT leaking (H-UNQ1 excluded: its dots are placed on the SGMC truth; see leakage canary).
Output: docs/downloads-style NaN/zeros pair via the shared submission_writer, plus
docs/evidence/run_consensus_lane.json. Pass --dry-run to skip writing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from gems32 import holdout  # noqa: E402
from gems32.paths import data_dir  # noqa: E402
import submission_writer  # noqa: E402

LANES = {
    "UWBP-DRCS-EXP-B3": "gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-zeros.tif",
    "OCDA-MSCS-EXP3": "gemsdoe32-kanler1-ocda-mscs-exp3-37654d-20261027T1842Z-1db32b55-zeros.tif",
    "UPFLOW-EXP2": "gemsdoe32-kanler1-upflow-exp2-37654d-20261028T163730Z-76525b8c-zeros.tif",
    "CONCORD5-B2": "kanlergemsdoe1-concord5-b2-37654-research-20261027T171958Z-5dde8074-zeros.tif",
    "MPLC-HGB": "kanler-mplc-hgb-37654-20261026-0741963ae4e9-zeros.tif",
    "H3-CONDRESID": "kanlergemsdoe1-h3-condresid-s3p17-b2-32000-20261026T214518Z-42802022-zeros.tif",
    "H1-IEDR": "kanlergemsdoe1-h1-iedr-s3p17-b2-32000-20261026T214518Z-fe519ae3-zeros.tif",
    "H2-HTSI": "kanlergemsdoe1-h2-htsi-s3p17-b2-32000-20261026T214518Z-571145eb-zeros.tif",
}
BUDGET = 37654
RADIUS = 3.0
MIN_SUPPORT = 2


def load_mask(name: str, foot: np.ndarray) -> np.ndarray:
    with rasterio.open(ROOT / "docs" / "downloads" / name) as ds:
        a = np.nan_to_num(ds.read(1).astype(np.float64), nan=0.0)
    return (a > 0) & foot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--slug", default="kanler1-lane-consensus-v1")
    ap.add_argument("--min-support", type=int, default=MIN_SUPPORT)
    ap.add_argument("--exclude", default="", help="comma-separated lane names to drop (variant)")
    args = ap.parse_args()

    ctx = holdout.load_holdout_context(data_dir())
    foot = ctx.foot
    excl = {x for x in args.exclude.split(",") if x}
    lanes = {k: load_mask(v, foot) for k, v in LANES.items() if k not in excl}
    dts = {k: distance_transform_edt(~m) for k, m in lanes.items()}
    union = np.zeros_like(foot)
    for m in lanes.values():
        union |= m
    # Support of each candidate pixel = number of lanes with a dot within RADIUS px of it.
    support = np.zeros(foot.shape, np.int16)
    for k in lanes:
        support += (dts[k] <= RADIUS).astype(np.int16)
    min_support = args.min_support
    cand = union & (support >= min_support)
    n_cand = int(cand.sum())
    keep = cand
    if n_cand > BUDGET:
        # Deterministic budget cap: highest support first, then raster order.
        idx = np.flatnonzero(cand.ravel())
        order = np.lexsort((idx, -support.ravel()[idx]))
        keep = np.zeros(foot.size, bool)
        keep[idx[order[:BUDGET]]] = True
        keep = keep.reshape(foot.shape)
    n_keep = int(keep.sum())
    rep = {"candidate_id": args.slug, "min_support": min_support, "radius_px": RADIUS,
           "lanes": {k: v for k, v in LANES.items() if k not in excl}, "excluded_lanes": sorted(excl), "support_pixels_before_cap": n_cand, "dots_after_cap": n_keep,
           "budget": BUDGET, "budget_capped": n_cand > BUDGET}
    rep["within3px_of_each_lane"] = {k: round(float((dts[k][keep] <= RADIUS).mean()), 4) for k in lanes}
    print(json.dumps(rep, indent=2))
    if args.dry_run:
        return 0
    if n_keep == 0:
        raise SystemExit("empty consensus")
    arr = keep.astype(np.float32)
    meta = {
        "candidate_id": args.slug,
        "description": f"H-CONS-1 (excluded={sorted(excl)}) multi-lane agreement consensus (>={min_support} of {len(lanes)} unique non-leaking lanes within 3 px)",
        "submission_note_zeros": "KANLER1 H-CONS-1 multi-lane agreement dots (>=2 of 8 lanes), 300m, unique [RESEARCH-HOLD]",
        "submission_note_nan": "KANLER1 H-CONS-1 multi-lane agreement dots (>=2 of 8 lanes), 300m, unique [RESEARCH-HOLD]",
    }
    bundle = submission_writer.write_validated_submission(arr, slug=args.slug, candidate_meta=meta,
                                                          ddir=data_dir(), out_dir=ROOT / "docs" / "downloads")
    rep["bundle"] = bundle if isinstance(bundle, dict) else str(bundle)
    (ROOT / "docs" / "evidence" / "run_consensus_lane.json").write_text(json.dumps(rep, indent=2, default=str) + "\n")
    print("WROTE", json.dumps(bundle, indent=2, default=str)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
