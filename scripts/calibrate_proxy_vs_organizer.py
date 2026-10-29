#!/usr/bin/env python3
"""Calibration check: does our HOLDOUT-DTI proxy rank files the way the organizer does?

For every raster in data/scored/ and data/registry_rasters/ that has an UNAMBIGUOUS
leaderboard score in the owner's score ledger (hard-coded below, copied from the
user-supplied ledger, USER-REPORTED - not a submission-page receipt), this script runs the
shared evaluator (`scripts/evaluate_holdout.py` -> `gems32.holdout`) in diagnostic
full-map mode and records the HOLDOUT-DTI numbers. It then reports Spearman rank
correlation between the proxy and the organizer score.

Writes evidence/proxy_vs_organizer_calibration.json. Nothing here is a submission.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import evaluate_holdout  # noqa: E402
from gems32.paths import data_dir  # noqa: E402

# (file under data/, USER-REPORTED organizer score, GEMSDOE site the ledger attributes it to)
LEDGER = [
    ("registry_rasters/champion_h33_b2_02778.tif", 0.2778, "GEMSDOE32"),
    ("registry_rasters/d28_02600.tif", 0.2600, "GEMSDOE30"),
    ("scored/gems24-h25-1-dotted-h19-5-d2-8-20261002-e56ea318af89-nan.tif", 0.2600, "GEMSDOE25"),
    ("scored/gems24-h25-1-dotted-h19-5-d1-5-20261002-989f59505db1-nan.tif", 0.2477, "GEMSDOE24"),
    ("scored/gems27-topo-gap-closure-t-v2-on-d1-5-20261002-5512495c6bd1-nan.tif", 0.2449, "GEMSDOE27"),
    ("scored/gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif", 0.1922, "GEMSDOE19"),
    ("scored/gems19-h19-4-multiline-corroborated-openness-thermal-pop-20260930-691e4dfa-nan.tif", 0.1894, "GEMSDOE19"),
    ("scored/gems16-h16-1-topo-geophys-baseline-ridges-20260930-df20f65e-nan.tif", 0.1855, "GEMSDOE16"),
    ("scored/gems10-h28-dotted-ridge-20260928T020256236880Z-6452ae1d00.tif", 0.1839, "GEMSDOE10"),
    ("scored/gems10-h25-ctx-ridge-20260927T232947704150Z-6452ae1d00.tif", 0.1280, "GEMSDOE10"),
    ("scored/8GEMSDOE_Hedge-v2_submission.tif", 0.1563, "8GEMSDOE"),
    ("scored/13gems_20261001_r13-lattice-s5_v2_nan-outside.tif", 0.0904, "13GEMSDOE"),
    ("scored/gemsdoe9-PLACEHOLDER-2314b599.tif", 0.0107, "GEMSDOE9"),
]


def binarize_to_npy(src: Path, dst: Path) -> None:
    with rasterio.open(src) as ds:
        arr = ds.read(1)
    arr = np.where(np.isfinite(arr), arr, 0.0)
    np.save(dst, (arr > 0).astype(np.uint8))


def main() -> int:
    ddir = data_dir()
    tmp = ROOT / "data" / "cache" / "calibration"
    tmp.mkdir(parents=True, exist_ok=True)
    rows = []
    for rel, org, site in LEDGER:
        src = ddir / rel
        npy = tmp / (src.stem + ".npy")
        binarize_to_npy(src, npy)
        res = evaluate_holdout.evaluate_path(npy, ddir=ddir, name=src.stem, diagnostic_full_map=True)
        hr = res["hide_and_recover"]
        sg = res["sgmc_off_catalogue"]
        rows.append({
            "file": rel,
            "organizer_score_user_reported": org,
            "site_per_ledger": site,
            "emitted_pixels": res["emitted_pixels"],
            "hr_pooled_dti_fullmap_diag": hr["pooled_dti"],
            "hr_ci95": hr["ci95_cluster_bootstrap"],
            "hr_n_withheld": hr["n_withheld_positives"],
            "sgmc_cal_dti": sg["sgmc_prevalence_calibrated_dti"],
            "sgmc_cal_ci95": sg["sgmc_calibrated_ci95"],
        })
        print(f"{src.name[:50]:50s} org={org:.4f} HR={hr['pooled_dti']:.4f} SGMC={sg['sgmc_prevalence_calibrated_dti']:.4f}")

    org = [r["organizer_score_user_reported"] for r in rows]
    hr = [r["hr_pooled_dti_fullmap_diag"] for r in rows]
    sg = [r["sgmc_cal_dti"] for r in rows]
    rho_hr = spearmanr(org, hr)
    rho_sg = spearmanr(org, sg)
    out = {
        "schema": "proxy-vs-organizer-calibration/v1",
        "evaluator_version_hr": "GEMSDOE32-HIDE-RECOVER-v3.1",
        "evaluator_version_sgmc": "GEMSDOE32-SGMC-CAL-v3.0",
        "score_label_proxy": "HOLDOUT-DTI (full-map diagnostic; NOT fold-local)",
        "score_label_organizer": "USER-REPORTED (leaderboard ledger in the prompt; not a submission receipt)",
        "n_files": len(rows),
        "spearman_organizer_vs_hr": {"rho": float(rho_hr.statistic), "p": float(rho_hr.pvalue)},
        "spearman_organizer_vs_sgmc_cal": {"rho": float(rho_sg.statistic), "p": float(rho_sg.pvalue)},
        "rows": rows,
    }
    path = ROOT / "evidence" / "proxy_vs_organizer_calibration.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("spearman_organizer_vs_hr", "spearman_organizer_vs_sgmc_cal")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
