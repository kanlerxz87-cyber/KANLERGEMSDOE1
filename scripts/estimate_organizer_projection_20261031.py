#!/usr/bin/env python3
"""PROJECTION (never a score) of organizer DTI from the off-catalogue SGMC-CAL proxy, 2026-10-31.

Input : docs/evidence/proxy_vs_organizer_calibration.json (13 user-reported organizer points).
Method: ordinary least squares  organizer = a + b * sgmc_cal  over the calibration rows, then the
        95% prediction interval for a new point. Only SGMC-CAL is used because it is the only proxy
        in the calibration file with a positive rank correlation to the organizer ledger
        (rho = +0.576, p = 0.039, n = 13). The hide-recover column is excluded: the file's own
        Spearman against the organizer is -0.10 (p = 0.74).
Caveats (must travel with any use of the output):
  * n = 13 rows, several rows are the same raster reported at two sites (not independent);
  * organizer scores are user-reported, not submission receipts;
  * a linear map from a 13-point proxy is an extrapolation for a new file family.

Also verifies whether two focus sites carry byte-identical rasters (GEMSDOE25 vs GEMSDOE30).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    cal = json.loads((ROOT / "docs/evidence/proxy_vs_organizer_calibration.json").read_text())
    rows = cal["rows"]
    x = np.array([r["sgmc_cal_dti"] for r in rows], float)
    y = np.array([r["organizer_score_user_reported"] for r in rows], float)
    n = len(x)
    res = stats.linregress(x, y)
    xbar = x.mean()
    sxx = float(((x - xbar) ** 2).sum())
    resid = y - (res.intercept + res.slope * x)
    s = float(np.sqrt((resid ** 2).sum() / (n - 2)))
    tcrit = float(stats.t.ppf(0.975, n - 2))

    def projection(x0: float) -> dict:
        yhat = res.intercept + res.slope * x0
        se_pred = s * np.sqrt(1 + 1 / n + (x0 - xbar) ** 2 / sxx)
        return {"x_sgmc_cal": x0, "projected_organizer": float(yhat),
                "pi95_low": float(yhat - tcrit * se_pred), "pi95_high": float(yhat + tcrit * se_pred)}

    # Inputs are the recorded SGMC-CAL values; the champion row is included as a self-check.
    champ = projection(0.0641209376417646)
    cand = projection(0.089174)  # UWBP-DRCS-EXP3 EXP-B3, recorded run card value (not re-run today)

    # Duplicate-raster check across focus sites (byte equality).
    fs = {e["site"]: e for e in json.loads((ROOT / "registry/focus_sites.json").read_text())["files"]}
    p25 = ROOT / "data/focus/GEMSDOE25.tif"
    p30 = ROOT / "data/focus/GEMSDOE30.tif"
    dup = {
        "GEMSDOE25_sha256": sha256_file(p25) if p25.exists() else None,
        "GEMSDOE30_sha256": sha256_file(p30) if p30.exists() else None,
        "byte_identical": (sha256_file(p25) == sha256_file(p30)) if p25.exists() and p30.exists() else None,
        "pinned_25": fs["GEMSDOE25"]["sha256"],
        "pinned_30": fs["GEMSDOE30"]["sha256"],
    }

    out = {
        "schema": "organizer-projection/v1",
        "label": "PROJECTION - NOT A SCORE",
        "method": "OLS organizer ~ SGMC-CAL on proxy_vs_organizer_calibration.json rows; 95% prediction interval",
        "calibration": {"n_rows": n, "slope": float(res.slope), "intercept": float(res.intercept),
                        "r": float(res.rvalue), "residual_sd": s,
                        "spearman_organizer_vs_sgmc_cal": cal["spearman_organizer_vs_sgmc_cal"],
                        "spearman_organizer_vs_hide_recover": cal["spearman_organizer_vs_hr"]},
        "self_check_champion_projection_vs_user_reported_0p2778": champ,
        "candidate_UWBP_projection": cand,
        "duplicate_check_GEMSDOE25_vs_GEMSDOE30": dup,
    }
    path = ROOT / "docs/evidence/organizer_projection_20261031.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("candidate_UWBP_projection", "self_check_champion_projection_vs_user_reported_0p2778", "duplicate_check_GEMSDOE25_vs_GEMSDOE30")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
