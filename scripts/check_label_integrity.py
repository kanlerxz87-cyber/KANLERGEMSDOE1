#!/usr/bin/env python3
"""Label-integrity check for the restored competition rasters.

Why this exists (2026-10-31 review): in the hash-pinned owner mirror restored by
scripts/restore_data.py, `labels.tif` and `existing_faults.tif` are byte-identical.
In the competition the catalogue faults (existing_faults) and the withheld truth
(labels) are different sets, so an identical pair makes any hide-and-recover
holdout built on them invalid. This script records the evidence reproducibly.

Writes evidence/label_integrity_20261031.json. Exits 1 if the pair is identical.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "evidence" / "label_integrity_20261031.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def positives(p: Path) -> np.ndarray:
    with rasterio.open(p) as ds:
        return ds.read(1) == 1


def main() -> int:
    labels, faults, sample = DATA / "labels.tif", DATA / "existing_faults.tif", DATA / "sample_submission.tif"
    lab_sha, flt_sha = sha256(labels), sha256(faults)
    lp, fp = positives(labels), positives(faults)
    sp = positives(sample)
    report = {
        "schema": "label-integrity/v1",
        "files": {
            "labels.tif": {"sha256": lab_sha, "positive_pixels": int(lp.sum())},
            "existing_faults.tif": {"sha256": flt_sha, "positive_pixels": int(fp.sum())},
            "sample_submission.tif": {"sha256": sha256(sample), "pixels_equal_to_1": int(sp.sum())},
        },
        "labels_and_existing_faults_byte_identical": lab_sha == flt_sha,
        "labels_vs_existing_faults_positive_overlap": int((lp & fp).sum()),
        "sample_ones_equal_labels_ones": bool(np.array_equal(sp, lp)),
        "provenance": "hash-pinned owner mirror (registry/data_manifest.json); not organizer-authenticated",
        "verdict": "BLOCKER: holdout invalid until labels are verified against the organizer download",
    }
    if report["labels_and_existing_faults_byte_identical"]:
        report["verdict"] = "BLOCKER: labels.tif == existing_faults.tif (byte-identical); holdout invalid until verified"
    else:
        report["verdict"] = "PASS: labels and existing_faults differ (still verify against organizer download)"
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 1 if report["labels_and_existing_faults_byte_identical"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
