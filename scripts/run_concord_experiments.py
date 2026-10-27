#!/usr/bin/env python3
"""Run the pre-registered KANLER-CONCORD experiments (EXP1-EXP3).

Pre-registration: docs/research/preregistration-20261027.md
Reuse (no forks): gems32.holdout evaluator v3.1 + SGMC-CAL v3.0 via the
shared context, scripts/submission_writer.py for the final GeoTIFF pair.
Outputs: .cache/gems_work/concord/* (surfaces), evidence/concord_*.json,
docs/downloads/<final> via the shared writer, data/run-card.json.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import binary_dilation, distance_transform_edt
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from gems32 import holdout  # noqa: E402
from gems32.paths import data_dir, work_dir  # noqa: E402
from gems32.submission import sha256_file  # noqa: E402
from kanler.concord import FAMILIES, build_families, build_surface, score_ordered_thin  # noqa: E402
from submission_writer import write_validated_submission  # noqa: E402

FULL_BUDGET = 37654
MIN_DIST = float(np.sqrt(8.0))
N_BOOT = 1000
BOOT_SEED = 20261026  # evaluator default; identical resamples -> paired deltas


def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


def disk3():
    y, x = np.ogrid[-3:4, -3:4]
    return (y * y + x * x) <= 9


def read_field(path: Path) -> np.ndarray:
    with rasterio.open(path) as ds:
        return ds.read(1)


def dots_of(arr: np.ndarray, foot: np.ndarray) -> np.ndarray:
    return np.isfinite(arr) & (arr > 0) & foot


def restore_focus(ddir: Path) -> list[dict]:
    from restore_data import GitBlobFetcher, restore_entry
    focus = json.loads((ROOT / "registry/focus_sites.json").read_text())["files"]
    fetcher = GitBlobFetcher(ROOT / ".cache" / "git_blob_cache")
    for e in focus:
        r = restore_entry(e, ddir, fetcher)
        log(f"focus {r['status']} {e['dest']}")
    return focus


def collect_registry(ddir: Path, focus: list[dict]) -> list[dict]:
    """Genuine-submission registry available locally, deduped by file SHA-256."""
    entries = []
    for e in focus:
        entries.append({"name": f"{e['site']} champion", "path": ddir / e["dest"],
                        "kind": "focus_champion", "site": e["site"],
                        "reported_score": e["reported_score"]})
    for p in sorted((ddir / "scored").glob("*.tif")):
        kind = "calibration_lattice" if "lattice" in p.name else "scored_detector"
        entries.append({"name": p.name, "path": p, "kind": kind})
    for p in sorted((ROOT / "data" / "registry_rasters").glob("*.tif")):
        entries.append({"name": p.name, "path": p, "kind": "registry_raster"})
    for p in sorted((ROOT / "docs" / "downloads").glob("*-zeros.tif")):
        entries.append({"name": p.name, "path": p, "kind": "repo_historical"})
    seen, out = {}, []
    for e in entries:
        if not e["path"].is_file():
            e["error"] = "missing"
            out.append(e)
            continue
        e["sha256"] = sha256_file(e["path"])
        e["path_str"] = str(e["path"].relative_to(ROOT)) if str(e["path"]).startswith(str(ROOT)) else str(e["path"])
        if e["sha256"] in seen:
            e["duplicate_bytes_of"] = seen[e["sha256"]]
        else:
            seen[e["sha256"]] = e["name"]
        out.append(e)
    return out


def uniqueness(surface: np.ndarray, my_dots: np.ndarray, registry: list[dict],
               foot: np.ndarray, stage: str) -> dict:
    rng = np.random.default_rng(7)
    fy, fx = np.nonzero(foot)
    take = rng.choice(fy.size, size=min(400_000, fy.size), replace=False)
    sy, sx = fy[take], fx[take]
    my_surf = surface[sy, sx].astype(np.float64)
    rows = []
    st = disk3()
    for e in registry:
        if "error" in e or "duplicate_bytes_of" in e:
            continue
        arr = read_field(e["path"])
        theirs = dots_of(arr, foot)
        rho = float(spearmanr(my_surf, arr[sy, sx].astype(np.float64)).statistic) \
            if np.isfinite(arr[sy, sx]).all() else None
        near = binary_dilation(theirs, structure=st)
        ov = float(near[my_dots].mean()) if my_dots.any() else 0.0
        rows.append({"name": e["name"], "kind": e["kind"], "sha256": e["sha256"][:16],
                     "their_dots": int(theirs.sum()), "spearman_surface_sampled": rho,
                     "my_dots_within_3px": ov})
        del arr, theirs, near
    genuine = [r for r in rows if r["kind"] != "calibration_lattice"]
    lattice = [r for r in rows if r["kind"] == "calibration_lattice"]
    worst_rho = max(genuine, key=lambda r: abs(r["spearman_surface_sampled"] or 0), default=None)
    worst_ov = max(genuine, key=lambda r: r["my_dots_within_3px"], default=None)
    return {"stage": stage, "n_genuine_checked": len(genuine),
            "worst_abs_spearman": worst_rho, "worst_overlap": worst_ov,
            "lattice_diagnostic_only": lattice,
            "pass_vs_genuine": bool(worst_rho and abs(worst_rho["spearman_surface_sampled"]) <= 0.90
                                    and worst_ov and worst_ov["my_dots_within_3px"] <= 0.70),
            "rows": rows}


def emit_cells(field: np.ndarray, ctx, mode: str, offcat_px: int,
               support: np.ndarray | None = None) -> tuple[dict, dict]:
    """mode: 'b2' or 'gated'. Returns per-cell cropped predictions + info."""
    preds, infos = {}, {}
    for cell in ctx.cells:
        sl = cell.bbox
        f = field[sl]
        allowed = cell.active_sub.copy()
        dvis = cell.d_vis_sub
        if mode == "b2":
            allowed &= dvis > 2.0
        elif mode == "gated":
            act_vals = f[cell.active_sub]
            q90 = float(np.quantile(act_vals, 0.90)) if act_vals.size else 1.0
            allowed &= (dvis > 2.0) | (f >= q90)
        else:
            raise ValueError(mode)
        n_target = max(1, int(round(FULL_BUDGET * int(cell.active_sub.sum()) / offcat_px)))
        cand = support[sl] if support is not None else None
        dots, info = score_ordered_thin(f, allowed, n_target, MIN_DIST,
                                        candidate_mask=cand)
        preds[cell.key] = dots
        infos[cell.key] = info
    return preds, infos


def emit_full(field: np.ndarray, foot: np.ndarray, labels: np.ndarray,
              mode: str, support: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    dlab = distance_transform_edt(~labels).astype(np.float32)
    allowed = foot & ~labels
    if mode == "b2":
        allowed &= dlab > 2.0
    elif mode == "gated":
        q90 = float(np.quantile(field[foot & ~labels], 0.90))
        allowed &= (dlab > 2.0) | (field >= q90)
    return score_ordered_thin(field, allowed, FULL_BUDGET, MIN_DIST,
                              candidate_mask=support)


def paired(a: dict, b: dict) -> dict:
    d = np.asarray(a["_boots"]) - np.asarray(b["_boots"])
    return {"delta_pooled": float(a["pooled_dti"] - b["pooled_dti"]),
            "delta_ci95": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))],
            "p_delta_gt_0": float((d > 0).mean())}


def strip(res: dict) -> dict:
    return {k: v for k, v in res.items() if not k.startswith("_")}


def main() -> int:
    t0 = time.time()
    ddir = data_dir()
    wdir = work_dir() / "concord"
    wdir.mkdir(parents=True, exist_ok=True)
    bands_dir = work_dir() / "bands"
    log(f"data_dir={ddir} bands={bands_dir}")

    foot = np.load(bands_dir / "_footprint.npy")
    labels = np.load(bands_dir / "_labels.npy")
    offcat_px = int((foot & ~labels).sum())
    log(f"footprint={int(foot.sum())} labels={int(labels.sum())} offcat={offcat_px}")

    # ---- surfaces (cached) ----
    surf_path = wdir / "surface.npy"
    fam_paths = {k: wdir / f"family_{k}.npy" for k in FAMILIES}
    if surf_path.exists() and all(p.exists() for p in fam_paths.values()):
        surface = np.load(surf_path)
        fam = {k: np.load(p) for k, p in fam_paths.items()}
        log("loaded cached concord surface")
    else:
        fam = build_families(bands_dir, ddir, foot, log=log)
        for k, v in fam.items():
            np.save(fam_paths[k], v)
        surface = build_surface(fam, ddir, foot)
        np.save(surf_path, surface)
        log("built concord surface")

    h195_path = ddir / "scored" / "gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif"
    h195 = dots_of(read_field(h195_path), foot)
    h195_field = h195.astype(np.float32)
    log(f"H19-5 support px={int(h195.sum())}")

    # ---- shared holdout context ----
    ctx = holdout.load_holdout_context(ddir)
    n_withheld = int(sum(c.n_truth for c in ctx.cells))
    log(f"holdout cells={len(ctx.cells)} withheld positives={n_withheld} "
        f"evaluator={holdout.HIDE_RECOVER_EVALUATOR_VERSION}")

    # ---- leakage canaries (before placement) ----
    rng = np.random.default_rng(11)
    canary_fields = {**fam, "concord_surface": surface}
    # pooled pos/neg value collectors per field
    pos = {k: [] for k in canary_fields}
    neg = {k: [] for k in canary_fields}
    for cell in ctx.cells:
        sl = cell.bbox
        ty, tx = cell.truth_coords
        ay, ax = np.nonzero(cell.active_sub)
        is_truth = np.zeros(cell.active_sub.shape, bool)
        is_truth[ty, tx] = True
        neg_idx = np.flatnonzero(~is_truth[ay, ax])
        take = rng.choice(neg_idx, size=min(30_000, neg_idx.size), replace=False)
        ny, nx = ay[take], ax[take]
        for k, f in canary_fields.items():
            sub = f[sl]
            pos[k].append(sub[ty, tx].astype(np.float64))
            neg[k].append(sub[ny, nx].astype(np.float64))
    canaries = {}
    for k in canary_fields:
        p = np.concatenate(pos[k]); n = np.concatenate(neg[k])
        y = np.r_[np.ones(p.size), np.zeros(n.size)]
        s = np.r_[p, n]
        auc = float(roc_auc_score(y, s))
        sym = max(auc, 1.0 - auc)
        canaries[k] = {"auc_withheld_vs_active": auc, "symmetric_auc": sym,
                       "n_pos": int(p.size), "n_neg_sampled": int(n.size),
                       "pass_le_0.90": bool(sym <= 0.90)}
        log(f"canary {k}: AUC={auc:.4f} sym={sym:.4f}")
    del pos, neg
    canary_pass = all(v["pass_le_0.90"] for v in canaries.values())

    # ---- registry + surface-stage uniqueness (before placement) ----
    focus = restore_focus(ddir)
    registry = collect_registry(ddir, focus)
    preview_dots, prev_info = emit_full(surface, foot, labels, "b2")
    uniq_surface = uniqueness(surface, preview_dots, registry, foot, "surface_preview_b2")
    log(f"surface uniqueness pass={uniq_surface['pass_vs_genuine']} "
        f"worst_rho={uniq_surface['worst_abs_spearman']} worst_ov={uniq_surface['worst_overlap']}")

    results = {"canaries": canaries, "canary_pass": canary_pass,
               "uniqueness_surface_stage": uniq_surface,
               "preview_full_b2": prev_info}
    if not canary_pass:
        results["stop"] = "leakage canary failed"
        (ROOT / "evidence" / "concord_experiments.json").write_text(json.dumps(results, indent=2) + "\n")
        log("STOP: canary")
        return 2
    if not uniq_surface["pass_vs_genuine"]:
        results["stop"] = "surface-stage duplicate vs genuine registry"
        (ROOT / "evidence" / "concord_experiments.json").write_text(json.dumps(results, indent=2) + "\n")
        log("STOP: surface duplicate")
        return 3

    # ---- EXP1 / EXP2 ----
    def run_exp(field, mode, name, support=None):
        preds, infos = emit_cells(field, ctx, mode, offcat_px, support=support)
        res = holdout.evaluate_hide_and_recover(preds, ctx, b_visible_px=0.0,
                                                n_boot=N_BOOT, seed=BOOT_SEED, name=name)
        log(f"{name}: HOLDOUT-DTI={res['pooled_dti']:.5f} CI={res['ci95_cluster_bootstrap']} "
            f"emitted/cell={[infos[k]['accepted'] for k in infos]}")
        return res, infos

    exp1, exp1_info = run_exp(h195_field, "b2", "EXP1_h195_b2", support=h195)
    exp2, exp2_info = run_exp(surface, "b2", "EXP2_concord_b2")
    d21 = paired(exp2, exp1)
    surface_win = d21["delta_ci95"][0] > 0
    log(f"EXP2-EXP1 paired {d21} surface_win={surface_win}")

    # ---- EXP3 (pre-registered branch on the winner) ----
    if surface_win:
        exp3, exp3_info = run_exp(surface, "gated", "EXP3_concord_gated")
        parent, parent_name = exp2, "EXP2_concord_b2"
        win_field, win_support, win_slug = surface, None, "concord5"
    else:
        exp3, exp3_info = run_exp(h195_field, "gated", "EXP3_h195_gated", support=h195)
        parent, parent_name = exp1, "EXP1_h195_b2"
        win_field, win_support, win_slug = h195_field, h195, "h195field"
    d3p = paired(exp3, parent)
    emission_win = d3p["delta_ci95"][0] > 0
    log(f"EXP3-{parent_name} paired {d3p} emission_win={emission_win}")
    win_mode = "gated" if emission_win else "b2"
    win_res = exp3 if emission_win else (exp2 if surface_win else exp1)
    slug = f"{win_slug}-{'gatedb' if win_mode == 'gated' else 'b2'}-{FULL_BUDGET}"

    # ---- full-map emissions + SGMC instrument ----
    full = {}
    for tag, fld, mode, sup in [("exp1cfg", h195_field, "b2", h195),
                                ("exp2cfg", surface, "b2", None),
                                ("winner", win_field, win_mode, win_support)]:
        dots, info = emit_full(fld, foot, labels, mode, support=sup)
        sg = holdout.evaluate_sgmc_with_ci(dots, ctx, n_boot=N_BOOT, seed=BOOT_SEED, name=tag)
        full[tag] = {"info": info, "dots": int(dots.sum()),
                     "sgmc": {k: v for k, v in sg.items() if not k.startswith("_")}}
        log(f"full {tag}: dots={int(dots.sum())} SGMC-cal={sg['sgmc_prevalence_calibrated_dti']:.5f}")
        if tag == "winner":
            winner_dots = dots
    champ = dots_of(read_field(ROOT / "data" / "registry_rasters" / "champion_h33_b2_02778.tif"), foot)
    sg_champ = holdout.evaluate_sgmc_with_ci(champ, ctx, n_boot=N_BOOT, seed=BOOT_SEED, name="champion_static")
    full["champion_static_file"] = {"dots": int(champ.sum()),
        "sgmc": {k: v for k, v in sg_champ.items() if not k.startswith("_")},
        "note": "static submitted file; SGMC instrument only (not fold-local)"}

    # ---- final-dot uniqueness ----
    uniq_final = uniqueness(surface if win_field is surface else h195_field,
                            winner_dots, registry, foot, "final_dots")
    log(f"final uniqueness pass={uniq_final['pass_vs_genuine']}")

    # ---- write final submission via shared writer ----
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    hr = float(win_res["pooled_dti"])
    note = f"KANLER {slug} HR31={hr:.4f} | concord5 soft-min + thin2.83"
    assert len(note) <= 140, note
    meta = {"candidate_id": f"KANLER-CONCORD-{slug}",
            "filename_prefix": "kanlergemsdoe1",
            "description": "KANLER-CONCORD pre-registered lane 2026-10-27; see evidence/concord_experiments.json",
            "submission_note_zeros": note, "submission_note_nan": note,
            "catalogue_hidden_mean": hr,
            "sgmc_prevalence_calibrated_dti": float(full["winner"]["sgmc"]["sgmc_prevalence_calibrated_dti"]),
            "slot_decision": "SELECTOR-REVIEW"}
    bundle = write_validated_submission(winner_dots.astype(np.float32), slug=slug,
                                        candidate_meta=meta, ddir=ddir,
                                        out_dir=ROOT / "docs" / "downloads",
                                        timestamp_tag=ts)
    zeros_name = bundle["zeros_tif"]["filename"]
    log(f"wrote {zeros_name} sha={bundle['zeros_tif']['sha256']}")

    # ---- verdict ----
    candidate_is_concord = surface_win  # winner field must be the new surface
    promote = bool(candidate_is_concord and uniq_final["pass_vs_genuine"]
                   and bundle["zeros_tif"]["all_checks_passed"])
    # PROJECTION (labelled; anchored on USER/OWNER-REPORTED 0.2778 via EXP1)
    ratio = float(win_res["pooled_dti"] / exp1["pooled_dti"]) if exp1["pooled_dti"] > 0 else None
    boots_ratio = (np.asarray(win_res["_boots"]) / np.maximum(np.asarray(exp1["_boots"]), 1e-12))
    projection = {"evidence_class": "PROJECTION-NOT-A-SCORE",
                  "anchor": "0.2778 USER/OWNER-REPORT for GEMSDOE32 h33-2-b2 (no receipt)",
                  "method": "0.2778 * (winner HOLDOUT-DTI / EXP1 HOLDOUT-DTI), paired boots ratio CI",
                  "point": float(0.2778 * ratio) if ratio else None,
                  "ci95_from_ratio": [float(0.2778 * np.percentile(boots_ratio, 2.5)),
                                      float(0.2778 * np.percentile(boots_ratio, 97.5))],
                  "warning": "Holdout (withheld catalogue segments) != live test (new expert faults); use only for ranking."}

    results.update({
        "evaluator": holdout.HIDE_RECOVER_EVALUATOR_VERSION,
        "n_withheld_positives": n_withheld, "n_bootstrap": N_BOOT,
        "exp1": strip(exp1), "exp1_emit_info": exp1_info,
        "exp2": strip(exp2), "exp2_emit_info": exp2_info,
        "paired_exp2_minus_exp1": d21,
        "exp3": strip(exp3), "exp3_emit_info": exp3_info,
        "exp3_parent": parent_name, "paired_exp3_minus_parent": d3p,
        "surface_win": surface_win, "emission_win": emission_win,
        "winner": {"slug": slug, "mode": win_mode,
                   "field": "concord" if win_field is surface else "h19-5"},
        "full_map_sgmc": full,
        "uniqueness_final": uniq_final,
        "bundle": bundle, "projection": projection,
        "verdict": "promote" if promote else "negative",
        "runtime_s": round(time.time() - t0, 1),
    })
    (ROOT / "evidence" / "concord_experiments.json").write_text(
        json.dumps(results, indent=2) + "\n")
    log(f"VERDICT {'promote' if promote else 'negative'} runtime={results['runtime_s']:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
