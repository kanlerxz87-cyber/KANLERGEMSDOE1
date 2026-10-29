#!/usr/bin/env python3
"""Candidate scoreboard: one row per candidate with every number labelled by evidence class.

Evidence classes (never mixed in one column):
  HOLDOUT-DTI (SGMC-CAL, re-run this session)  - shared evaluator, full-map diagnostic, binarised NaN->0.
  HOLDOUT-DTI (HIDE-RECOVER, REPO-REPORTED)     - fold-local lane run card; NOT re-run here (a single
                                                  full-map file cannot reproduce fold-dependent scores).
  USER-REPORTED organizer score                  - the leaderboard ledger supplied in the prompt.
  PROJECTION                                     - linear fit of organizer vs SGMC-CAL on user-reported
                                                  points; an extrapolation, NOT a score.

Writes evidence/candidate_scoreboard_20261029.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import evaluate_holdout  # noqa: E402
from calibrate_proxy_vs_organizer import LEDGER  # noqa: E402
from gems32.paths import data_dir  # noqa: E402

CANDIDATES = [
    {
        "candidate": "KANLER1-UWBP-DRCS-EXP3 (EXP-B3)",
        "file": "docs/downloads/gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif",
        "dots_reported": 37647,
        "hide_recover_repo_reported": {"value": 0.064800, "ci95": [0.057434, 0.071809], "n": 22232,
                                       "source": "evidence/run_card_uwbp_drcs.json (fold-local, admissible)"},
    },
    {
        "candidate": "KANLER1-COMB-PIEDMONT-WORM (2026-10-29)",
        "file": "docs/downloads/gemsdoe32-kanler1-comb-piedmont-worm-disjoint-300m-celf-20261029T020638Z-9424d197-nan.tif",
        "dots_reported": 37654,
        "hide_recover_repo_reported": None,
    },
    {
        "candidate": "KANLER1-OCDA-MSCS-EXP3",
        "file": "docs/downloads/gemsdoe32-kanler1-ocda-mscs-exp3-37654d-20261027T1842Z-1db32b55-nan.tif",
        "dots_reported": 37649,
        "hide_recover_repo_reported": {"value": 0.105830, "ci95": [0.095019, 0.115257], "n": 22232,
                                       "source": "README.md section 2 / audit-20261028.md (fold-local)"},
    },
    {
        "candidate": "KANLER1-UPFLOW-EXP2",
        "file": "docs/downloads/gemsdoe32-kanler1-upflow-exp2-37654d-20261028T163730Z-76525b8c-nan.tif",
        "dots_reported": 37654,
        "hide_recover_repo_reported": {"value": 0.057717, "ci95": [0.049718, 0.064828], "n": 22232,
                                       "source": "README.md section 2 (fold-local)"},
    },
    {
        "candidate": "KANLER-CGJI-HTB-EXP2",
        "file": "submissions/cgji_htb_20261027/gemsdoe32-cgji-htb-exp2-oof-hgb-b2-20261027T013000Z-5214b9ec-nan.tif",
        "dots_reported": 37654,
        "hide_recover_repo_reported": {"value": 0.0997, "ci95": None, "n": 22232,
                                       "source": "submissions/cgji_htb_20261027 audit note"},
    },
]


def binarize(src: Path, dst: Path) -> None:
    with rasterio.open(src) as ds:
        arr = ds.read(1)
    np.save(dst, (np.where(np.isfinite(arr), arr, 0.0) > 0).astype(np.uint8))


def main() -> int:
    ddir = data_dir()
    tmp = ROOT / "data" / "cache" / "scoreboard"
    tmp.mkdir(parents=True, exist_ok=True)

    # 1) Re-run the SGMC proxy (the only file-level proxy that tracks the organizer ledger, rho=0.58).
    rows = []
    for c in CANDIDATES:
        npy = tmp / (Path(c["file"]).stem + ".npy")
        binarize(ROOT / c["file"], npy)
        res = evaluate_holdout.evaluate_path(npy, ddir=ddir, name=Path(c["file"]).stem, diagnostic_full_map=True)
        sg = res["sgmc_off_catalogue"]
        rows.append({
            "candidate": c["candidate"],
            "file": c["file"],
            "dots": res["emitted_pixels"],
            "sgmc_cal_holdout_dti": {
                "value": sg["sgmc_prevalence_calibrated_dti"], "ci95": sg["sgmc_calibrated_ci95"],
                "n_withheld_positives": sg["n_withheld_positives"], "evaluator_version": "GEMSDOE32-SGMC-CAL-v3.0",
                "label": "HOLDOUT-DTI (re-run this session; full-map diagnostic)",
            },
            "hide_recover_fold_local": c["hide_recover_repo_reported"] and {
                **c["hide_recover_repo_reported"], "label": "HOLDOUT-DTI (REPO-REPORTED, not re-run)"},
        })
        print(f"{c['candidate']:42s} SGMC-CAL={sg['sgmc_prevalence_calibrated_dti']:.6f} dots={res['emitted_pixels']}")

    # 2) PROJECTION only: linear fit organizer ~ SGMC-CAL on the user-reported ledger rows.
    xs, ys = [], []
    for rel, org, _site in LEDGER:
        if "r13" in rel:  # 206,895-dot space-filling lattice: different density regime, excluded from the fit
            continue
        arr_path = tmp / (Path(rel).stem + ".npy")
        if not arr_path.exists():
            binarize(ddir / rel, arr_path)
        res = evaluate_holdout.evaluate_path(arr_path, ddir=ddir, name=Path(rel).stem, diagnostic_full_map=True)
        xs.append(res["sgmc_off_catalogue"]["sgmc_prevalence_calibrated_dti"])
        ys.append(org)
    x, y = np.array(xs), np.array(ys)
    n = len(x)
    b1, b0 = np.polyfit(x, y, 1)
    resid = y - (b0 + b1 * x)
    s = np.sqrt((resid ** 2).sum() / (n - 2))
    sxx = ((x - x.mean()) ** 2).sum()
    corr = float(np.corrcoef(x, y)[0, 1])
    for row in rows:
        xv = row["sgmc_cal_holdout_dti"]["value"]
        pred = b0 + b1 * xv
        half = 1.0 * s * np.sqrt(1 + 1 / n + (xv - x.mean()) ** 2 / sxx)  # ~68% prediction band (1 sigma)
        in_range = bool(x.min() <= xv <= x.max())
        row["organizer_projection"] = {
            "value": round(float(pred), 4),
            "band_1sigma": [round(float(pred - half), 4), round(float(pred + half), 4)],
            "n_fit_points": n,
            "within_fitted_sgmc_range": in_range,
            "label": "PROJECTION - linear extrapolation from USER-REPORTED points; NOT a score",
        }

    out = {
        "schema": "candidate-scoreboard/v1",
        "generated_by": "scripts/build_candidate_scoreboard.py",
        "fit": {"model": "organizer_score ~ a + b * SGMC_CAL", "n": n, "pearson_r": round(corr, 4),
                "intercept": float(b0), "slope": float(b1), "residual_sd": float(s),
                "x_range": [float(x.min()), float(x.max())],
                "excluded": ["13GEMSDOE r13-lattice (206,895 dots; space-filling, different density regime)"]},
        "rows": rows,
    }
    (ROOT / "evidence" / "candidate_scoreboard_20261029.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out["fit"], indent=2))
    for row in rows:
        print(row["candidate"], row["organizer_projection"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
