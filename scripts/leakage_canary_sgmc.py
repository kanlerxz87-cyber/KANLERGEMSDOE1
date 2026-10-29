#!/usr/bin/env python3
"""Leakage canary for the zero-SGMC proxy (Protocol Rule 4).

The zero-SGMC proxy scores predictions against off-catalogue SGMC faults. A candidate whose inputs
were derived from those same SGMC faults will score high for the wrong reason. This canary reports,
for each candidate in docs/downloads/*-zeros.tif:
  - sgmc_canary_frac: fraction of candidate dots within 3 px of the SGMC off-catalogue truth mask
  - expected_random_frac: the same statistic for a uniform random placement of the same dot count
    inside the footprint (the chance baseline)
  - lift = sgmc_canary_frac / expected_random_frac
A lift far above ~1.5 means the candidate was built from SGMC and its zero-SGMC number is circular.
It also checks whether two candidates are the same raster (pixel-exact).
Writes docs/evidence/leakage_canary_sgmc.json.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gems32 import holdout  # noqa: E402
from gems32.paths import data_dir  # noqa: E402


def main() -> int:
    ctx = holdout.load_holdout_context(data_dir())
    foot = ctx.foot
    sg_off = ctx.sgmc_off  # off-catalogue SGMC truth, same mask the zero-SGMC proxy scores
    d_sg = distance_transform_edt(~sg_off)
    rng = np.random.default_rng(0)
    fidx = np.flatnonzero(foot.ravel())
    rows, hashes = [], {}
    for p in sorted((ROOT / "docs" / "downloads").glob("*zeros.tif")):
        with rasterio.open(p) as ds:
            arr = np.nan_to_num(ds.read(1).astype(np.float64), nan=0.0)
        m = (arr > 0) & foot
        n = int(m.sum())
        frac = float((d_sg[m] <= 3.0).mean()) if n else float("nan")
        rand_fracs = []
        for _ in range(5):
            pick = rng.choice(fidx, size=n, replace=False)
            rm = np.zeros(foot.size, bool)
            rm[pick] = True
            rand_fracs.append(float((d_sg.ravel()[rm] <= 3.0).mean()))
        exp = float(np.mean(rand_fracs))
        h = hashlib.sha256(np.packbits(m).tobytes()).hexdigest()[:16]
        hashes.setdefault(h, []).append(p.name)
        rows.append({"file": f"docs/downloads/{p.name}", "dots": n,
                     "sgmc_canary_frac": round(frac, 4), "expected_random_frac": round(exp, 4),
                     "lift": round(frac / exp, 2) if exp > 0 else None,
                     "canary_flag": bool(exp > 0 and frac / exp > 1.5),
                     "dot_mask_sha256_16": h})
        print(f"{p.name[:72]:72s} n={n:6d} sgmc_frac={frac:.4f} rand={exp:.4f} lift={rows[-1]['lift']} "
              f"FLAG={rows[-1]['canary_flag']}")
    dup = {k: v for k, v in hashes.items() if len(v) > 1}
    out = {"truth_mask": "SGMC off-catalogue (derived_sgmc_faults_100m_u8, >NEAR_LABEL_PX from labels, on footprint)",
           "rows": rows, "pixel_identical_groups": list(dup.values())}
    (ROOT / "docs" / "evidence" / "leakage_canary_sgmc.json").write_text(json.dumps(out, indent=2) + "\n")
    print("pixel-identical groups:", list(dup.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
