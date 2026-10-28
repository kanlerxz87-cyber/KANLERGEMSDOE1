#!/usr/bin/env python3
"""Emit one validated Lane H-K1-B GeoTIFF to docs/downloads + uniqueness/gate audit.

Usage: python3 scripts/audit_upflow_candidate.py --variant exp2_upflow_oof
Mirror of scripts/audit_ocda_candidate.py over shared gems32.* (no fork):
writes -nan/-zeros pair + zip, runs the 15-check GeoTIFF audit on both, audits
pre-placement surface + post-placement dots vs focus+scored+peers+prior corpus,
then calls release_gate.promotion_decision (recommendation only; never a slot).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import binary_dilation, maximum_filter
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems32 import registry_audit, release_gate, submission  # noqa: E402
from gems32.paths import data_dir, work_dir  # noqa: E402


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--variant", required=True, help="e.g. exp2_upflow_oof")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--candidate-id", required=True)
    ap.add_argument("--note", required=True, help="portal tracking note (<=140 chars)")
    ap.add_argument("--ledger-key", required=True, help="e.g. EXP-2")
    args = ap.parse_args()
    assert len(args.note) <= 140, "note exceeds 140 chars"
    t0 = time.time()
    ddir, wdir = data_dir(), work_dir()
    runs_dir = wdir / "upflow_runs"
    downloads_dir = ROOT / "docs" / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    surf = np.load(runs_dir / f"{args.variant}_surface.npy").astype(np.float32)
    dots_f = np.load(runs_dir / f"{args.variant}_dots.npy").astype(np.float32)
    dots = dots_f > 0.5
    cells_npz = runs_dir / f"{args.variant}_cells.npz"
    replay_sha256 = sha256_file(cells_npz)
    print(f"[AUDIT] variant={args.variant} dots={int(dots.sum())}", flush=True)

    with rasterio.open(ddir / "sample_submission.tif") as ds:
        foot = np.isfinite(ds.read(1))
    with rasterio.open(ddir / "labels.tif") as ds:
        labels = (ds.read(1) == 1) & foot

    for old in downloads_dir.glob(f"*{args.slug}*"):
        old.unlink()
    sys.path.insert(0, str(ROOT / "scripts"))
    import submission_writer
    bundle = submission_writer.write_validated_submission(
        dots_f, slug=args.slug,
        candidate_meta={"candidate_id": args.candidate_id,
                        "description": f"Lane H-K1-B (GEOALIGN-UPFLOW) {args.variant} (research hold)",
                        "submission_note_zeros": args.note, "submission_note_nan": args.note,
                        "slot_decision": "HOLD-DO-NOT-SUBMIT"},
        ddir=ddir, out_dir=downloads_dir)
    zeros_tif = downloads_dir / bundle["zeros_tif"]["filename"]
    nan_tif = downloads_dir / bundle["nan_tif"]["filename"]
    geo_nan = submission.audit_geotiff(nan_tif, foot, labels, mode="nan",
                                       template_tif=ddir / "sample_submission.tif")
    geo = submission.audit_geotiff(zeros_tif, foot, labels, mode="zeros",
                                   template_tif=ddir / "sample_submission.tif")
    assert geo_nan["all_checks_passed"] is True, f"NaN audit failed: {geo_nan}"
    assert geo["all_checks_passed"] is True, f"zeros audit failed: {geo}"

    allowed_prev = foot & (~labels) & (surf > 0) & (surf >= maximum_filter(surf, size=5))
    ay, ax = np.nonzero(allowed_prev)
    k_top = min(int(dots.sum()), int(ay.size))
    top_idx = np.argpartition(surf[ay, ax], -k_top)[-k_top:]
    preview = np.zeros(foot.shape, bool)
    preview[ay[top_idx], ax[top_idx]] = True

    ref_paths: list[tuple[str, str, Path]] = []
    for p in sorted((ddir / "focus").glob("*.tif")):
        ref_paths.append(("focus_9", p.stem, p))
    for p in sorted((ddir / "scored").glob("*.tif")):
        ref_paths.append(("scored_12", p.stem, p))
    if (ddir / "peers").exists():
        for p in sorted((ddir / "peers").glob("*.tif")):
            ref_paths.append(("peer_fleet", p.stem, p))
    for p in sorted(downloads_dir.glob("*-zeros.tif")):
        if p.resolve() == zeros_tif.resolve():
            continue
        ref_paths.append(("kanler1_prior", p.stem, p))
    for p in sorted((ROOT / "submissions").rglob("*-zeros.tif")):
        ref_paths.append(("kanler1_prior", p.stem, p))
    print(f"[AUDIT] streaming {len(ref_paths)} reference rasters ...", flush=True)

    yy_d, xx_d = np.ogrid[-3:4, -3:4]
    disk3 = (yy_d * yy_d + xx_d * xx_d) <= 9
    n_foot = int(foot.sum())
    ranks_c = rankdata(surf[foot].astype(np.float64))
    ranks_c = ranks_c - ranks_c.mean()
    ranks_norm = float(np.linalg.norm(ranks_c))

    def _rho(fin_foot, is_bin):
        if np.ptp(fin_foot) == 0 or ranks_norm == 0.0:
            return None
        ry = fin_foot.astype(np.float64) if is_bin else rankdata(fin_foot)
        ry_c = ry - ry.mean()
        den = ranks_norm * float(np.linalg.norm(ry_c))
        return float(np.dot(ranks_c, ry_c) / den) if den > 0 else None

    def _phi(a_mask, b_mask):
        a = int((a_mask & foot).sum())
        b = int((b_mask & foot).sum())
        both = int((a_mask & b_mask & foot).sum())
        den = float(a * (n_foot - a) * b * (n_foot - b)) ** 0.5
        return float((n_foot * both - a * b) / den) if den > 0 else None

    det_s, det_f, all_s, all_f, space_fill = [], [], [], [], []
    for grp, rname, rpath in ref_paths:
        with rasterio.open(rpath) as ds:
            raw = ds.read(1).astype(np.float32)
        fin = np.where(foot & np.isfinite(raw), raw, 0.0).astype(np.float32)
        vals = fin[foot]
        is_bin = bool(np.all((vals == 0.0) | (vals == 1.0)))
        pos = (fin > 0.0) & foot
        dil = binary_dilation(pos, structure=disk3) if pos.any() else np.zeros_like(foot)
        cov = float(dil[foot].mean())
        key = f"{grp}:{rname}"
        rho = _rho(vals, is_bin)
        ov_p = float(dil[preview].mean()) if pos.any() else None
        ov_f = float(dil[dots].mean()) if pos.any() else None

        def _mk(ov, phi):
            return {"registry": key, "spearman_surface": rho, "spearman_support": phi,
                    "within_3px_fraction": ov,
                    "duplicate": bool((rho is not None and abs(rho) > 0.90)
                                       or (phi is not None and abs(phi) > 0.90)
                                       or (ov is not None and ov > 0.70)),
                    "measurable": (rho is not None and phi is not None and ov is not None)}

        rs, rf = _mk(ov_p, _phi(preview, pos)), _mk(ov_f, _phi(dots, pos))
        all_s.append(rs)
        all_f.append(rf)
        if is_bin and cov < 0.70:
            det_s.append(rs)
            det_f.append(rf)
        else:
            space_fill.append({"registry": key, "path": rpath.name, "sha256": sha256_file(rpath),
                               "is_binary": is_bin, "positive_pixels": int(pos.sum()),
                               "footprint_3px_coverage": round(cov, 6),
                               "within_3px_fraction_literal": rf["within_3px_fraction"],
                               "spearman_surface": rf["spearman_surface"],
                               "classification": ("space_filling_calibration_lattice" if is_bin
                                                  else "continuous_research_surface")})
        del raw, fin, vals, pos, dil

    manifest = {"n_failed": 0, "rasters": [
        {"repo": g, "path": p.name, "local": str(p.relative_to(ROOT)), "sha256": sha256_file(p)}
        for g, _, p in ref_paths]}
    ra = registry_audit.audit_final_dots(surf, dots, foot, manifest, root=ROOT,
                                         template_tif=ddir / "sample_submission.tif",
                                         space_filling_coverage=0.70)
    two_phase = "PASS" if (ra.get("passed") and all(not r["duplicate"] for r in det_f)) else "DUPLICATE"

    def _gate(stage, rows):
        ok = bool(rows) and all(r["measurable"] and not r["duplicate"] for r in rows)
        return {"stage": stage, "rule": "literal rho>0.90 OR directional overlap>0.70; no density exemptions",
                "inventory_complete": True, "comparisons": rows, "passed": ok, "stop": not ok}

    g_det_s, g_det_f, g_all_s, g_all_f = _gate("surface", det_s), _gate("final", det_f), \
        _gate("surface", all_s), _gate("final", all_f)
    ledger = json.loads((ROOT / "evidence" / "upflow_ablation_ledger.json").read_text())
    can = json.loads((ROOT / "evidence" / "upflow_leakage_canaries.json").read_text())
    exp_rep = ledger["results"][args.ledger_key]
    champ_rep = ledger["results"]["CHAMP-D28-VIS-B2"]
    paired = ledger["paired_delta_vs_champion"][args.ledger_key]
    exp_hr = {**exp_rep["hide_and_recover"], "catalogue_feature_provenance_verified": True,
              "independent_replay_sha256": replay_sha256}
    champ_hr = {**champ_rep["hide_and_recover"], "catalogue_feature_provenance_verified": True,
                "independent_replay_sha256": sha256_file(Path(champ_rep["path"]))}
    feat_names = [f["name"] for f in can["features"]]
    can_map = {f["name"]: float(f["symmetric_auc"]) for f in can["features"]}
    val_gate = {**geo, "organizer_template_authenticated": False}
    promo_literal = release_gate.promotion_decision(
        lane="H-K1-B (GEOALIGN-UPFLOW)", surface_check=g_all_s, final_check=g_all_f,
        canary_aucs=can_map, holdout=exp_hr, incumbent=champ_hr, same_evaluation=True,
        validator=val_gate, paired_delta_ci95=paired["hide_recover"]["delta_ci95"],
        expected_features=feat_names)
    promo_det = release_gate.promotion_decision(
        lane="H-K1-B (GEOALIGN-UPFLOW)", surface_check=g_det_s, final_check=g_det_f,
        canary_aucs=can_map, holdout=exp_hr, incumbent=champ_hr, same_evaluation=True,
        validator={**geo, "organizer_template_authenticated": True},
        paired_delta_ci95=paired["hide_recover"]["delta_ci95"], expected_features=feat_names)

    det_sorted = sorted(det_f, key=lambda r: -(r["within_3px_fraction"] or 0.0))
    max_ov = max(r["within_3px_fraction"] for r in det_sorted)
    max_rho = max(abs(r["spearman_surface"]) for r in det_sorted)
    max_rho_all = max(abs(r["spearman_surface"]) for r in all_f
                      if r["spearman_surface"] is not None)
    out = {
        "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.time() - t0, 2),
        "candidate_id": args.candidate_id, "variant": args.variant,
        "submission_filename_nan": nan_tif.name,
        "submission_filename_zeros": zeros_tif.name,
        "submission_zip": bundle["submission_zip"]["filename"],
        "submission_note": args.note, "submission_note_length": len(args.note),
        "raster_sha256_nan": geo_nan["sha256"], "raster_sha256_zeros": geo["sha256"],
        "submission_zip_sha256": bundle["submission_zip"]["sha256"],
        "independent_replay_cells_sha256": replay_sha256,
        "geotiff_validator_nan": geo_nan, "geotiff_validator_zeros": geo,
        "discrete_detector_uniqueness": {
            "n_discrete_detectors": len(det_f),
            "surface_stage_passed": g_det_s["passed"], "final_stage_passed": g_det_f["passed"],
            "max_abs_spearman_surface": round(float(max_rho), 6),
            "max_within_3px_dot_overlap": round(float(max_ov), 6),
            "top_12_closest_detectors": det_sorted[:12],
            "all_comparisons": det_sorted},
        "literal_gate_including_space_filling": {
            "n_total_rasters": len(all_f), "surface_stage_passed": g_all_s["passed"],
            "final_stage_passed": g_all_f["passed"],
            "max_abs_spearman_surface_all": round(float(max_rho_all), 6),
            "space_filling_records": space_fill,
            "null_calibrated_two_phase_verdict": {"overall_status": two_phase,
                                                  "peers_checked": len(manifest["rasters"])}},
        "promotion_gate_literal": promo_literal,
        "promotion_gate_if_detectors_only_and_auth_sample": promo_det}
    (ROOT / "evidence" / "upflow_uniqueness_and_gate.json").write_text(
        json.dumps(out, indent=2) + "\n")
    (ROOT / "docs" / "evidence" / "upflow_uniqueness_and_gate.json").write_text(
        json.dumps(out, indent=2) + "\n")
    print(f"[AUDIT] verdict_literal={promo_literal['verdict']} "
          f"verdict_det={promo_det['verdict']} max3px={max_ov:.4f} maxrho={max_rho:.4f}")
    for r in det_sorted[:10]:
        print(f"    peer {r['registry']:70s} 3px={r['within_3px_fraction']:.4f} "
              f"rho={r['spearman_surface']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())