#!/usr/bin/env python3
"""EXP-1-only v2 sensitivity check for the H-K1-B upflow lane (research-only).

Rebuilds the label-free upflow stack with the FIXED 0.5px dense segment sampler
(src/kanler/upflow.py), re-runs the FROZEN EXP-1 protocol, and compares against
the v1 lane result. No new submission artifacts; writes one JSON verdict.
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    t0 = time.time()
    lane = _load("run_upflow_lane", ROOT / "scripts" / "run_upflow_lane.py")
    upflow = lane.upflow
    holdout = lane.holdout
    shared_features = lane.shared_features

    ddir, wdir = lane.data_dir(), lane.work_dir()
    v2dir = wdir / "upflow_v2"
    v2dir.mkdir(parents=True, exist_ok=True)
    out_dir = v2dir / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)

    shared_mm = shared_features.load_checked(wdir / "features_v2.npy",
                                             ddir / "training_features.tif")
    ctx = holdout.load_holdout_context(ddir)
    import rasterio
    with rasterio.open(ddir / "sample_submission.tif") as ds:
        transform = ds.transform
    # Fresh build (empty v2dir defeats the v1 cache); fixed sampler active.
    up2 = upflow.build_or_load_upflow_stack(ddir, v2dir, shared_mm, ctx.foot, transform)
    v1 = np.load(wdir / "upflow_free_v1.npy", mmap_mode="r")
    diffs = {}
    for i, nm in enumerate(upflow.UPFLOW_FREE_NAMES):
        a = np.asarray(v1[i], dtype=np.float32)
        b = np.asarray(up2[i], dtype=np.float32)
        d = np.abs(a - b)
        diffs[nm] = {"max_abs_diff": float(d[ctx.foot].max()),
                     "mean_abs_diff": float(d[ctx.foot].mean()),
                     "frac_changed": float((d[ctx.foot] > 1e-6).mean())}
    print("[v2check] stack diffs:", json.dumps(diffs, indent=1), flush=True)
    belief2, crest2 = upflow.build_alignment_surface(up2, ctx.foot)
    collars = [lane._collar_mask_for_fold(ctx.foot, ctx.quad, f) for f in range(4)]
    e1v2 = lane.run_exp1(ctx, collars, belief2, crest2, belief2, crest2, out_dir, ddir)
    v1rep = json.loads((wdir / "upflow_runs" / "exp1_upflow_align_eval.json").read_text())
    hr1 = v1rep["hide_and_recover"]["pooled_dti"]
    hr2 = e1v2["hide_and_recover"]["pooled_dti"]
    sg1 = v1rep["sgmc_off_catalogue"]["sgmc_prevalence_calibrated_dti"]
    sg2 = e1v2["sgmc_off_catalogue"]["sgmc_prevalence_calibrated_dti"]
    ci1 = v1rep["hide_and_recover"]["ci95_cluster_bootstrap"]
    verdict = {
        "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sampler_fix": "0.5px dense segment walk (src/kanler/upflow.py)",
        "exp1_v1_HR": hr1, "exp1_v2_HR": hr2, "delta_HR": hr2 - hr1,
        "exp1_v1_SGMC": sg1, "exp1_v2_SGMC": sg2, "delta_SGMC": sg2 - sg1,
        "v1_ci95": ci1, "v2_within_v1_ci": ci1[0] <= hr2 <= ci1[1],
        "champion_HR": 0.099202,
        "conclusion_stable": (hr2 < 0.099202),
        "stack_channel_diffs": diffs,
        "wall_seconds": round(time.time() - t0, 2),
    }
    (ROOT / "evidence" / "upflow_v2_sensitivity.json").write_text(
        json.dumps(verdict, indent=2) + "\n")
    print("[v2check] verdict:", json.dumps({k: v for k, v in verdict.items()
                                           if k != "stack_channel_diffs"}, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
