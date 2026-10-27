#!/usr/bin/env python3
"""Pass-2 audit for KANLER-CONCORD: verify primitives, run AUC-only diagnostics
(no new candidate, no promotion path), write the CONCORD research GeoTIFF via
the shared writer (slot HOLD), and independently re-audit both new files."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from scipy.spatial import cKDTree
from scipy.stats import rankdata
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from gems32 import holdout  # noqa: E402
from gems32.paths import data_dir, work_dir  # noqa: E402
from gems32.submission import audit_geotiff  # noqa: E402
from kanler.concord import FAMILIES, rank01, score_ordered_thin  # noqa: E402
from run_concord_experiments import emit_full  # noqa: E402
from submission_writer import write_validated_submission  # noqa: E402


def main() -> int:
    out: dict = {"pass": 2, "purpose": "bug audit + diagnostics; NOT a new experiment"}
    # 1) rank01 vs scipy rankdata (with ties)
    rng = np.random.default_rng(3)
    a = rng.integers(0, 5, size=(60, 70)).astype(np.float64)
    mask = np.ones(a.shape, bool); mask[:5, :] = False
    mine = rank01(a, mask)[mask]
    ref = (rankdata(a[mask]) - 1) / (a[mask].size - 1)
    out["rank01_max_abs_err_vs_scipy"] = float(np.abs(mine - ref).max())

    # 2) thinning: spacing + budget + top-value property on a synthetic field
    field = rng.random((300, 300), dtype=np.float32)
    allowed = np.ones((300, 300), bool)
    dots, info = score_ordered_thin(field, allowed, 2000)
    ys, xs = np.nonzero(dots)
    tree = cKDTree(np.c_[ys, xs])
    dd, _ = tree.query(np.c_[ys, xs], k=2)
    out["thin_synthetic"] = {"info": info, "n": int(dots.sum()),
                             "min_nn_dist": float(dd[:, 1].min()),
                             "mean_field_dots": float(field[dots].mean()),
                             "mean_field_all": float(field.mean())}

    ddir = data_dir()
    bands_dir = work_dir() / "bands"
    wdir = work_dir() / "concord"
    foot = np.load(bands_dir / "_footprint.npy")
    labels = np.load(bands_dir / "_labels.npy")
    fam = {k: np.load(wdir / f"family_{k}.npy") for k in FAMILIES}
    surface = np.load(wdir / "surface.npy")

    # 3) AUC-only diagnostics for fusion variants (guides next preregistration)
    stack = np.stack([fam[k] for k in FAMILIES])
    diag_fields = {
        "mean_fusion_DIAGNOSTIC": rank01(stack.mean(axis=0), foot),
        "geomean_only_DIAGNOSTIC": rank01(np.exp(np.log(stack + 1e-3).mean(axis=0)), foot),
        "topo_only_DIAGNOSTIC": fam["topo"],
        "max_fusion_DIAGNOSTIC": rank01(stack.max(axis=0), foot),
    }
    del stack
    ctx = holdout.load_holdout_context(ddir)
    rng2 = np.random.default_rng(11)  # same neg sampling seed as canaries
    pos = {k: [] for k in diag_fields}; neg = {k: [] for k in diag_fields}
    for cell in ctx.cells:
        sl = cell.bbox
        ty, tx = cell.truth_coords
        ay, ax = np.nonzero(cell.active_sub)
        is_truth = np.zeros(cell.active_sub.shape, bool); is_truth[ty, tx] = True
        neg_idx = np.flatnonzero(~is_truth[ay, ax])
        take = rng2.choice(neg_idx, size=min(30_000, neg_idx.size), replace=False)
        ny, nx = ay[take], ax[take]
        for k, f in diag_fields.items():
            sub = f[sl]
            pos[k].append(sub[ty, tx].astype(np.float64))
            neg[k].append(sub[ny, nx].astype(np.float64))
    out["auc_diagnostics_NOT_candidates"] = {}
    for k in diag_fields:
        p = np.concatenate(pos[k]); n = np.concatenate(neg[k])
        auc = float(roc_auc_score(np.r_[np.ones(p.size), np.zeros(n.size)], np.r_[p, n]))
        out["auc_diagnostics_NOT_candidates"][k] = auc
        print(k, round(auc, 4), flush=True)

    # 4) CONCORD research GeoTIFF (unique, format-valid, HOLD - do not submit)
    dots, info = emit_full(surface, foot, labels, "b2")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    exp = json.loads((ROOT / "evidence" / "concord_experiments.json").read_text())
    hr2 = float(exp["exp2"]["pooled_dti"])
    note = f"RESEARCH ONLY concord5-b2 HR31={hr2:.4f} NEGATIVE do-not-submit"
    assert len(note) <= 140
    bundle = write_validated_submission(
        dots.astype(np.float32), slug="concord5-b2-37654-research",
        candidate_meta={"candidate_id": "KANLER-CONCORD-EXP2-RESEARCH",
                        "filename_prefix": "kanlergemsdoe1",
                        "description": "EXP2 CONCORD full map; HOLDOUT-negative research artifact",
                        "submission_note_zeros": note, "submission_note_nan": note,
                        "catalogue_hidden_mean": hr2,
                        "slot_decision": "HOLD-DO-NOT-SUBMIT"},
        ddir=ddir, out_dir=ROOT / "docs" / "downloads", timestamp_tag=ts)
    out["concord_research_bundle"] = {"zeros": bundle["zeros_tif"]["filename"],
                                      "sha256": bundle["zeros_tif"]["sha256"],
                                      "emit_info": info}

    # 5) independent re-audit of both new zeros files + champion (range demo)
    tmpl = ddir / "sample_submission.tif"
    targets = {"concord_research": ROOT / "docs" / "downloads" / bundle["zeros_tif"]["filename"],
               "h195_control": ROOT / "docs" / "downloads" / exp["bundle"]["zeros_tif"]["filename"],
               "champion_h33": ROOT / "data" / "registry_rasters" / "champion_h33_b2_02778.tif"}
    out["independent_reaudit"] = {}
    for k, p in targets.items():
        try:
            a = audit_geotiff(p, foot, labels, mode="zeros", template_tif=tmpl)
            out["independent_reaudit"][k] = {"all_checks_passed": a["all_checks_passed"],
                                             "min": a["in_footprint_min"], "max": a["in_footprint_max"],
                                             "dots": a["emitted_positive_pixels"], "sha256": a["sha256"]}
        except Exception as e:  # champion is zeros-mode too; record honestly
            out["independent_reaudit"][k] = {"error": f"{type(e).__name__}: {e}"}
        # raw range facts regardless of audit strictness
        with rasterio.open(p) as ds:
            arr = ds.read(1)
        v = arr[foot]
        out["independent_reaudit"][k].update(
            {"foot_finite": int(np.isfinite(v).sum()), "foot_nan": int(np.isnan(v).sum()),
             "foot_min": float(np.nanmin(v)), "foot_max": float(np.nanmax(v)),
             "full_min": float(np.nanmin(arr)), "full_max": float(np.nanmax(arr)),
             "sentinel_lt_-1e30_anywhere": bool((arr < -1e30).any())})
    out["lidar_valid_px_of_footprint"] = {
        "valid_px": 3894460, "footprint_px": int(foot.sum()),
        "fraction_of_footprint": 3894460 / int(foot.sum())}
    (ROOT / "evidence" / "concord_pass2.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
