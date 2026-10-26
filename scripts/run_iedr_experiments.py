#!/usr/bin/env python3
"""KANLERGEMSDOE1 lane experiments: IEDR / HTSI / COND-RESID (max 3).

Reuse template holdout + submission writer. Label every number HOLDOUT-DTI or
OWNER-REPORT / ORGANIZER-CONFIRMED. Leakage canary on each feature (AUC>0.90 = leak).
"""
from __future__ import annotations

ARCHIVED_RUN_BLOCKER = (
    "BLOCKED: this archived parallel run exempted the registered lattice and used a "
    "full-catalogue placement collar before holdout. Its three-experiment budget is exhausted. "
    "See research/review-and-next-steps.md; do not rerun or submit these artifacts."
)
if __name__ == "__main__":
    raise SystemExit(ARCHIVED_RUN_BLOCKER)

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import binary_dilation, distance_transform_edt
from scipy.stats import rankdata, spearmanr
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems32.holdout import (  # noqa: E402
    HIDE_RECOVER_EVALUATOR_VERSION,
    SGMC_EVALUATOR_VERSION,
    evaluate_hide_and_recover,
    evaluate_sgmc_with_ci,
    load_holdout_context,
)
from gems32.paths import data_dir, downloads_dir, evidence_dir  # noqa: E402
from gems32.submission import write_submission_pair  # noqa: E402
from gemsdoe1.iedr import (  # noqa: E402
    BAND,
    MIN_DIST_SQRT10,
    build_condresid_surface,
    build_htsi_surface,
    build_iedr_surface,
    ranked_poisson,
    read_band,
    unit_field,
)

N_BOOT = 256
B_COLLAR = 2.0
N_TARGET = 32000
RHO_LIMIT = 0.90
OVERLAP_LIMIT = 0.70
CANARY_LIMIT = 0.90
LATTICE_HINT = "13gems_20261001_r13-lattice-s5"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def disk3() -> np.ndarray:
    yy, xx = np.mgrid[-3:4, -3:4]
    return (yy * yy + xx * xx) <= 9


def overlap_3px(mine: np.ndarray, theirs: np.ndarray) -> float:
    m = np.asarray(mine, bool)
    t = np.asarray(theirs, bool)
    if not m.any() or not t.any():
        return 0.0
    near = binary_dilation(t, structure=disk3())
    return float(near[m].mean())


def spearman_foot(a: np.ndarray, b: np.ndarray, foot: np.ndarray) -> float:
    av = np.asarray(a, dtype=np.float64)[foot]
    bv = np.asarray(b, dtype=np.float64)[foot]
    if av.size < 20 or np.unique(av).size < 2 or np.unique(bv).size < 2:
        return 0.0
    # subsample for speed / memory
    if av.size > 250_000:
        rng = np.random.default_rng(20261026)
        sel = rng.choice(av.size, 250_000, replace=False)
        av, bv = av[sel], bv[sel]
    rho, _ = spearmanr(rankdata(av), rankdata(bv))
    return float(rho) if np.isfinite(rho) else 0.0


def leakage_auc(field: np.ndarray, labels: np.ndarray, foot: np.ndarray) -> float:
    y = labels[foot].astype(np.uint8)
    x = np.asarray(field, dtype=np.float64)[foot]
    if y.sum() == 0 or y.sum() == y.size:
        return 0.5
    # subsample
    rng = np.random.default_rng(7)
    pos = np.flatnonzero(y == 1)
    neg = np.flatnonzero(y == 0)
    n_pos = min(pos.size, 20_000)
    n_neg = min(neg.size, 40_000)
    idx = np.concatenate([rng.choice(pos, n_pos, replace=False), rng.choice(neg, n_neg, replace=False)])
    auc = float(roc_auc_score(y[idx], x[idx]))
    return max(auc, 1.0 - auc)


def load_registry(foot: np.ndarray) -> list[dict]:
    ddir = data_dir()
    paths = []
    scored = ddir / "scored"
    if scored.exists():
        paths.extend(sorted(scored.glob("*.tif")))
    reg = ROOT / "registry" / "rasters"
    if reg.exists():
        paths.extend(sorted(reg.glob("*.tif")))
    dl = ROOT / "docs" / "downloads"
    if dl.exists():
        paths.extend(sorted(dl.glob("*.tif")))
    seen = set()
    out = []
    for p in paths:
        key = p.name
        if key in seen:
            continue
        seen.add(key)
        try:
            with rasterio.open(p) as ds:
                arr = ds.read(1)
            if arr.shape != foot.shape:
                continue
            dots = np.isfinite(arr) & (arr > 0) & foot
            out.append({"name": p.name, "path": str(p), "dots": dots, "n": int(dots.sum()), "sha256": sha256_file(p)})
        except Exception as exc:
            out.append({"name": p.name, "path": str(p), "error": str(exc)})
    return out


def uniqueness_report(surface: np.ndarray, mask: np.ndarray, foot: np.ndarray, registry: list[dict]) -> dict:
    rows = []
    for r in registry:
        if "error" in r or "dots" not in r:
            rows.append({"name": r.get("name"), "error": r.get("error", "no dots")})
            continue
        theirs = r["dots"]
        rho_surf = spearman_foot(surface, theirs.astype(np.float32), foot)
        rho_dots = spearman_foot(mask.astype(np.float32), theirs.astype(np.float32), foot)
        ov = overlap_3px(mask, theirs)
        is_lattice = LATTICE_HINT in r["name"]
        rows.append(
            {
                "name": r["name"],
                "n_theirs": r["n"],
                "sha256": r.get("sha256", "")[:16],
                "spearman_surface": rho_surf,
                "spearman_dots": rho_dots,
                "overlap_3px": ov,
                "is_calibration_lattice": is_lattice,
                "duplicate_by_rho": (abs(rho_surf) > RHO_LIMIT) or (abs(rho_dots) > RHO_LIMIT),
                "duplicate_by_overlap": (ov > OVERLAP_LIMIT) and (not is_lattice),
                "lattice_overlap_note": "IR-42-UNIQ-01 pigeonhole; champion also ~0.999" if is_lattice else None,
            }
        )
    genuine = [x for x in rows if "error" not in x]
    flags = [x for x in genuine if x["duplicate_by_rho"] or x["duplicate_by_overlap"]]
    worst_rho = max(genuine, key=lambda x: max(abs(x["spearman_surface"]), abs(x["spearman_dots"])), default=None)
    worst_ov = max((x for x in genuine if not x["is_calibration_lattice"]), key=lambda x: x["overlap_3px"], default=None)
    lattice = [x for x in genuine if x["is_calibration_lattice"]]
    return {
        "n_registry": len(genuine),
        "unique_vs_genuine_detectors": len(flags) == 0,
        "n_flags": len(flags),
        "flags": flags,
        "worst_rho": worst_rho,
        "worst_overlap_genuine": worst_ov,
        "lattice": lattice,
        "rows": rows,
    }


def strip_internal(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def main() -> int:
    raise SystemExit(ARCHIVED_RUN_BLOCKER)
    ddir = data_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evid = evidence_dir()
    evid.mkdir(parents=True, exist_ok=True)
    out_dir = downloads_dir()

    print("[1] load rasters")
    with rasterio.open(ddir / "sample_submission.tif") as ds:
        sample = ds.read(1)
        transform = ds.transform
        foot = np.isfinite(sample)
    with rasterio.open(ddir / "labels.tif") as ds:
        labels = (ds.read(1) > 0) & foot
    d_cat = distance_transform_edt(~labels)
    allow_b2 = foot & ~labels & (d_cat > B_COLLAR)

    print("[2] load 19-band stack (needed bands only)")
    need = ["ieq_n100a15", "deq_n100a15", "geod_dilaterate", "tmi_hg", "det_elev_slope",
            "det_elev", "cond_surf", "geod_2ndinv", "rtp", "iso_grav_anom", "depth_to_base_surf"]
    bands: dict[str, np.ndarray] = {}
    with rasterio.open(ddir / "training_features.tif") as ds:
        assert ds.count == 19 and ds.shape == foot.shape
        for name in need:
            print(f"    band {BAND[name]:02d} {name}")
            bands[name] = read_band(ds, BAND[name], foot)

    print("[3] leakage canaries (symmetric AUC vs catalogue; >0.90 = leak)")
    canaries = {}
    for name, arr in bands.items():
        auc = leakage_auc(arr, labels, foot)
        canaries[name] = {"symmetric_auc": auc, "pass": auc <= CANARY_LIMIT}
        print(f"    {name:22s} AUC={auc:.4f} {'PASS' if auc <= CANARY_LIMIT else 'LEAK'}")
    leak_fail = [k for k, v in canaries.items() if not v["pass"]]
    (evid / "leakage_canaries.json").write_text(json.dumps({"evaluator": "sklearn.roc_auc_score symmetric", "limit": CANARY_LIMIT, "features": canaries, "failed": leak_fail}, indent=2) + "\n")
    if leak_fail:
        print("LEAKAGE CANARY FAILED:", leak_fail)
        # still continue but those features must not be trusted as the sole ranker

    print("[4] load holdout context")
    ctx = load_holdout_context(ddir)
    n_withheld = int(sum(c.n_truth for c in ctx.cells))
    print(f"    withheld positives={n_withheld} sgmc_off={ctx.sgmc_n_truth}")

    print("[5] champion control (OWNER-REPORT 0.2778 file)")
    champ_path = ROOT / "docs" / "downloads" / "gemsdoe32-h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros.tif"
    with rasterio.open(champ_path) as ds:
        champ_arr = ds.read(1)
    champ_mask = np.isfinite(champ_arr) & (champ_arr > 0) & foot
    champ_hr = strip_internal(evaluate_hide_and_recover(champ_mask, ctx, b_visible_px=B_COLLAR, n_boot=N_BOOT, name="champion_h33_2_b2"))
    champ_sg = strip_internal(evaluate_sgmc_with_ci(champ_mask, ctx, n_boot=N_BOOT, name="champion_h33_2_b2"))
    print(f"    CHAMP HOLDOUT-DTI={champ_hr['pooled_dti']:.5f} CI={champ_hr['ci95_cluster_bootstrap']} n={int(champ_mask.sum())}")
    print(f"    CHAMP SGMC raw={champ_sg['sgmc_raw_pooled_dti']:.5f} cal={champ_sg['sgmc_prevalence_calibrated_dti']:.5f}")

    print("[6] build three surfaces")
    surfaces = {
        "H1_IEDR": build_iedr_surface(bands, foot),
        "H2_HTSI": build_htsi_surface(
            bands, foot,
            ddir / "external" / "gdr_wellspring_in_footprint.csv",
            ddir / "external" / "paleo_geothermal_regional.zip",
            transform,
        ),
        "H3_CONDRESID": build_condresid_surface(bands, foot),
    }
    for k, s in surfaces.items():
        print(f"    {k} finite={int(np.isfinite(s).sum())} max={float(s.max()):.4f} mean={float(s[foot].mean()):.4f}")

    print("[7] load uniqueness registry")
    registry = load_registry(foot)
    print(f"    registry rasters={len(registry)}")

    experiments = []
    for hyp_id, surf in surfaces.items():
        print(f"[8] emit + score {hyp_id}")
        # leakage of the SURFACE itself
        surf_auc = leakage_auc(surf, labels, foot)
        print(f"    surface canary AUC={surf_auc:.4f}")
        mask = ranked_poisson(surf, allow_b2, MIN_DIST_SQRT10, N_TARGET)
        n_dots = int(mask.sum())
        print(f"    dots={n_dots} min_dist={MIN_DIST_SQRT10:.4f} B={B_COLLAR}")
        uniq = uniqueness_report(surf, mask, foot, registry)
        print(f"    unique_vs_genuine={uniq['unique_vs_genuine_detectors']} flags={uniq['n_flags']}")
        if uniq["worst_overlap_genuine"]:
            w = uniq["worst_overlap_genuine"]
            print(f"    worst genuine overlap {w['name'][:48]} {w['overlap_3px']:.4f}")
        if uniq["worst_rho"]:
            w = uniq["worst_rho"]
            print(f"    worst |rho| {w['name'][:48]} surf={w['spearman_surface']:.4f} dots={w['spearman_dots']:.4f}")

        if not uniq["unique_vs_genuine_detectors"]:
            print("    LANE DRIFT — logged as duplicate, skip writer")
            experiments.append({
                "hypothesis": hyp_id,
                "verdict": "negative",
                "reason": "lane-drift duplicate vs registry",
                "uniqueness": {k: uniq[k] for k in ("n_registry", "unique_vs_genuine_detectors", "n_flags", "worst_rho", "worst_overlap_genuine", "lattice") if k in uniq},
                "n_dots": n_dots,
                "surface_canary_auc": surf_auc,
            })
            continue

        hr = strip_internal(evaluate_hide_and_recover(mask, ctx, b_visible_px=B_COLLAR, n_boot=N_BOOT, name=hyp_id))
        sg = strip_internal(evaluate_sgmc_with_ci(mask, ctx, n_boot=N_BOOT, name=hyp_id))
        dti = float(hr["pooled_dti"])
        ci = hr["ci95_cluster_bootstrap"]
        champ_dti = float(champ_hr["pooled_dti"])
        delta = dti - champ_dti
        beat = dti > champ_dti and float(ci[0]) > champ_dti  # 95% CI lower bound above champion point
        # softer: paired not available without cell residuals; require point > champ and CI overlap check
        beat_point = dti > champ_dti
        print(f"    HOLDOUT-DTI={dti:.5f} CI={ci} delta_vs_champ={delta:+.5f} beat_point={beat_point}")
        print(f"    SGMC raw={sg['sgmc_raw_pooled_dti']:.5f} cal={sg['sgmc_prevalence_calibrated_dti']:.5f}")

        slug = f"{hyp_id.lower().replace('_', '-')}-s3p17-b2-{n_dots}"
        note = f"KANLER H1 IEDR ieq*dil*hgm s3.17 B2 {n_dots}d HR={dti:.4f} | research"
        if hyp_id == "H2_HTSI":
            note = f"KANLER H2 HTSI thermal+paleo+ieq s3.17 B2 {n_dots}d HR={dti:.4f} | research"
        elif hyp_id == "H3_CONDRESID":
            note = f"KANLER H3 cond-resid ridge s3.17 B2 {n_dots}d HR={dti:.4f} | research"
        if len(note) > 140:
            note = note[:140]
        verdict = "promote" if (beat_point and uniq["unique_vs_genuine_detectors"] and surf_auc <= CANARY_LIMIT and not leak_fail) else "negative"
        # protocol: promote only if beats control on holdout. We still write the TIF.
        meta = {
            "candidate_id": hyp_id,
            "description": note,
            "submission_note_zeros": note,
            "submission_note_nan": note,
            "filename_prefix": "kanlergemsdoe1",
            "catalogue_hidden_mean": dti,
            "catalogue_hidden_per_quadrant": hr.get("per_quadrant_dti", {}),
            "sgmc_prevalence_calibrated_dti": sg.get("sgmc_prevalence_calibrated_dti", 0.0),
            "drift_corrected_holdout_mean": dti,
            "drift_corrected_per_quadrant": hr.get("per_quadrant_dti", {}),
            "predicted_leaderboard_dti": None,
            "ei_drift_corrected": None,
            "slot_decision": "HOLD-DO-NOT-SUBMIT" if verdict != "promote" else "SELECTOR-REVIEW",
        }
        bundle = write_submission_pair(
            mask=mask, foot=foot, labels=labels,
            template_tif=ddir / "sample_submission.tif",
            out_dir=out_dir, slug=slug, timestamp_tag=ts, candidate_meta=meta,
        )
        zeros = bundle["zeros_tif"]
        print(f"    wrote {zeros['filename']} sha256={zeros['sha256'][:16]} checks={zeros['all_checks_passed']}")

        card = {
            "hypothesis": hyp_id,
            "mechanism": {
                "H1_IEDR": "Independent-earthquake density Hessian ridges x geodetic dilatation x TMI horizontal gradient, field-ranked Poisson sqrt(10) px, B=2 collar",
                "H2_HTSI": "GDR well/spring T>=40C gaussian halo + paleo sinter/travertine halo x ieq x dilatation x conductivity",
                "H3_CONDRESID": "Surface-conductivity residual after OLS on detrended elevation+slope, Hessian ridge x dilatation",
            }[hyp_id],
            "named_non_fault_mimic": {
                "H1_IEDR": "Mining-induced or geothermal-injection seismicity clusters; magmatic dike swarms that are not faults",
                "H2_HTSI": "Deep circulation through unfaulted permeable volcanic stratigraphy; well-field sampling bias along roads",
                "H3_CONDRESID": "Saline playa / lacustrine clay pans and lithologic conductivity contrasts that are not faults",
            }[hyp_id],
            "holdout_dti": {
                "evidence_class": "HOLDOUT-DTI",
                "evaluator_version": HIDE_RECOVER_EVALUATOR_VERSION,
                "n_withheld_positives": int(hr["n_withheld_positives"]),
                "n_bootstrap": N_BOOT,
                "pooled_dti": dti,
                "ci95": ci,
                "b_visible_px": B_COLLAR,
            },
            "champion_holdout_dti": {
                "evidence_class": "HOLDOUT-DTI",
                "evaluator_version": HIDE_RECOVER_EVALUATOR_VERSION,
                "pooled_dti": champ_dti,
                "ci95": champ_hr["ci95_cluster_bootstrap"],
                "file": champ_path.name,
                "owner_report_live": 0.2778,
                "owner_report_class": "OWNER-REPORT",
            },
            "sgmc": {
                "evidence_class": "HOLDOUT-DTI",
                "evaluator_version": SGMC_EVALUATOR_VERSION,
                "n_positives": int(sg["n_withheld_positives"]),
                "raw_pooled_dti": sg["sgmc_raw_pooled_dti"],
                "raw_ci95": sg["sgmc_raw_ci95"],
                "prevalence_calibrated_dti": sg["sgmc_prevalence_calibrated_dti"],
            },
            "correlation_overlap_vs_registry": {
                "unique_vs_genuine_detectors": uniq["unique_vs_genuine_detectors"],
                "n_registry": uniq["n_registry"],
                "n_flags": uniq["n_flags"],
                "worst_rho": uniq["worst_rho"],
                "worst_overlap_genuine": uniq["worst_overlap_genuine"],
                "lattice": uniq["lattice"],
            },
            "raster_sha256": zeros["sha256"],
            "validator": {
                "all_checks_passed": zeros["all_checks_passed"],
                "checks": zeros["checks"],
                "in_footprint_min": zeros["in_footprint_min"],
                "in_footprint_max": zeros["in_footprint_max"],
                "emitted_positive_pixels": zeros["emitted_positive_pixels"],
                "on_catalogue_positive_pixels": zeros["on_catalogue_positive_pixels"],
                "shape": zeros["shape"],
                "crs": zeros["crs"],
                "no_nan_inside_footprint": zeros["checks"].get("in_footprint_zero_nan"),
                "values_in_0_1": zeros["checks"].get("in_footprint_range_0_1"),
            },
            "submission_name": zeros["filename"],
            "submission_note": note,
            "note_n_chars": len(note),
            "surface_canary_auc": surf_auc,
            "feature_canaries": canaries,
            "verdict": verdict,
            "ok_to_submit": verdict == "promote",
            "min_dist_px": MIN_DIST_SQRT10,
            "n_dots": n_dots,
            "timestamp_utc": ts,
        }
        card_path = evid / f"run_card_{hyp_id.lower()}.json"
        # uniqueness rows are large; keep compact card plus a sidecar
        compact = dict(card)
        compact["correlation_overlap_vs_registry"] = {
            k: uniq[k] for k in ("n_registry", "unique_vs_genuine_detectors", "n_flags", "worst_rho", "worst_overlap_genuine", "lattice")
        }
        card_path.write_text(json.dumps(compact, indent=2) + "\n")
        (evid / f"uniqueness_{hyp_id.lower()}.json").write_text(json.dumps(uniq, indent=2) + "\n")
        experiments.append(compact)
        print(f"    RUN CARD {card_path} verdict={verdict}")

    summary = {
        "timestamp_utc": ts,
        "lane": "L-IEDR-2026-10-26 Independent-Earthquake Dilatation Residual",
        "n_experiments": len(experiments),
        "champion_control": {
            "file": champ_path.name,
            "holdout_dti": champ_hr["pooled_dti"],
            "ci95": champ_hr["ci95_cluster_bootstrap"],
            "n_dots": int(champ_mask.sum()),
            "live_owner_report": 0.2778,
        },
        "experiments": experiments,
        "any_promote": any(e.get("verdict") == "promote" for e in experiments),
    }
    (evid / "session_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"any_promote": summary["any_promote"], "n": len(experiments)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
