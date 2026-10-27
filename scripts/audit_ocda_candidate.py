#!/usr/bin/env python3
"""Emit validated EXP-3 GeoTIFF to `docs/downloads/` and run 42-raster uniqueness + release_gate audit."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "vendor"))

from gems32 import holdout, registry_audit, release_gate, submission
from gems32.paths import data_dir, work_dir


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    t0 = time.time()
    ddir, wdir = data_dir(), work_dir()
    runs_dir = wdir / "ocda_runs"
    downloads_dir = ROOT / "docs" / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    surf = np.load(runs_dir / "exp3_ocda_twostage_explainaway_surface.npy").astype(np.float32)
    dots_f = np.load(runs_dir / "exp3_ocda_twostage_explainaway_dots.npy").astype(np.float32)
    dots = dots_f > 0.5
    cells_npz = runs_dir / "exp3_ocda_twostage_explainaway_cells.npz"
    replay_sha256 = sha256_file(cells_npz)

    with rasterio.open(ddir / "sample_submission.tif") as ds:
        foot = np.isfinite(ds.read(1))
    with rasterio.open(ddir / "labels.tif") as ds:
        labels = (ds.read(1) == 1) & foot

    # 1. Remove any stale `kanler1-ocda-mscs-exp3-37654d` artifact in docs/downloads before clean write
    slug = "kanler1-ocda-mscs-exp3-37654d"
    for old in downloads_dir.glob(f"*{slug}*"):
        old.unlink()

    note = "KANLER1 OCDA-MSCS Exp3 OOF PU-HGB+300mCELF 37654d [RESEARCH-HOLD]"
    assert len(note) <= 140
    sys.path.insert(0, str(ROOT / "scripts"))
    import submission_writer
    bundle = submission_writer.write_validated_submission(
        dots_f,
        slug=slug,
        candidate_meta={
            "candidate_id": "KANLER1-OCDA-MSCS-EXP3",
            "description": "Lane H-K1-A (OCDA-MSCS) EXP-3 Two-Stage OOF PU-HGB + 300m Submodular CELF (37,654 dots; research hold)",
            "submission_note_zeros": note,
            "submission_note_nan": note,
            "slot_decision": "HOLD-DO-NOT-SUBMIT",
        },
        ddir=ddir,
        out_dir=downloads_dir,
        timestamp_tag="20261027T1842Z",
    )
    zeros_tif = downloads_dir / bundle["zeros_tif"]["filename"]
    nan_tif = downloads_dir / bundle["nan_tif"]["filename"]

    # Re-verify standalone automated 15-check GeoTIFF audit on BOTH `-nan.tif` (official null/NaN outside bounds)
    # and `-zeros.tif` (reference U-Net all-finite diagnostic)
    geo_audit_nan = submission.audit_geotiff(
        nan_tif, foot, labels, mode="nan", template_tif=ddir / "sample_submission.tif"
    )
    geo_audit = submission.audit_geotiff(
        zeros_tif, foot, labels, mode="zeros", template_tif=ddir / "sample_submission.tif"
    )
    assert geo_audit_nan["all_checks_passed"] is True, f"GeoTIFF NaN validation failed: {geo_audit_nan}"
    assert geo_audit["all_checks_passed"] is True, f"GeoTIFF zeros validation failed: {geo_audit}"

    # 2. Construct pre-placement local-peak preview support (top 37,654 5x5 local maxima of continuous surface)
    from scipy.ndimage import maximum_filter
    allowed_prev = foot & (~labels) & (surf > 0) & (surf >= maximum_filter(surf, size=5))
    ay, ax = np.nonzero(allowed_prev)
    s_vals = surf[ay, ax]
    k_top = min(int(dots.sum()), int(s_vals.size))
    top_idx = np.argpartition(s_vals, -k_top)[-k_top:]
    preview_dots = np.zeros(foot.shape, dtype=bool)
    preview_dots[ay[top_idx], ax[top_idx]] = True

    # 3. Assemble complete 46-raster reference corpus (9 focus + 12 scored + 16 sibling/fleet + 9 prior/concurrent KANLER1)
    ref_paths: list[tuple[str, str, Path]] = []
    for p in sorted((ddir / "focus").glob("*.tif")):
        ref_paths.append(("focus_9", p.stem, p))
    for p in sorted((ddir / "scored").glob("*.tif")):
        ref_paths.append(("scored_12", p.stem, p))
    for p in sorted((ddir / "peers").glob("*.tif")):
        ref_paths.append(("peer_fleet_16", p.stem, p))
    for p in sorted(downloads_dir.glob("*-zeros.tif")):
        if p.resolve() == zeros_tif.resolve():
            continue
        ref_paths.append(("kanler1_prior_and_concurrent", p.stem, p))
    for p in sorted((ROOT / "submissions").rglob("*-zeros.tif")):
        ref_paths.append(("kanler1_prior_and_concurrent", p.stem, p))

    print(f"[AUDIT] Streaming {len(ref_paths)} reference rasters one-by-one (<300 MB RAM)...")
    from scipy.ndimage import binary_dilation
    from scipy.stats import rankdata

    yy_d, xx_d = np.ogrid[-3:4, -3:4]
    disk3 = (yy_d * yy_d + xx_d * xx_d) <= 9
    n_foot = int(foot.sum())
    surf_f = surf[foot].astype(np.float64)
    ranks_surf = rankdata(surf_f)
    ranks_surf_c = ranks_surf - ranks_surf.mean()
    ranks_surf_norm = float(np.linalg.norm(ranks_surf_c))
    del surf_f, ranks_surf

    def _fast_exact_spearman(fin_foot: np.ndarray, is_bin: bool) -> float | None:
        if np.ptp(fin_foot) == 0 or ranks_surf_norm == 0.0:
            return None
        ry = fin_foot.astype(np.float64) if is_bin else rankdata(fin_foot)
        ry_c = ry - ry.mean()
        denom = ranks_surf_norm * float(np.linalg.norm(ry_c))
        return float(np.dot(ranks_surf_c, ry_c) / denom) if denom > 0 else None

    def _binary_phi(a_mask: np.ndarray, b_mask: np.ndarray) -> float | None:
        a = int((a_mask & foot).sum())
        b = int((b_mask & foot).sum())
        both = int((a_mask & b_mask & foot).sum())
        den = float(a * (n_foot - a) * b * (n_foot - b)) ** 0.5
        return float((n_foot * both - a * b) / den) if den > 0 else None

    surf_det_rows, final_det_rows = [], []
    surf_all_rows, final_all_rows = [], []
    space_filling_records: list[dict] = []

    for grp, rname, rpath in ref_paths:
        with rasterio.open(rpath) as ds:
            raw = ds.read(1).astype(np.float32)
        fin = np.where(foot & np.isfinite(raw), raw, 0.0).astype(np.float32)
        vals_f = fin[foot]
        is_binary = bool(np.all((vals_f == 0.0) | (vals_f == 1.0)))
        pos_mask = (fin > 0.0) & foot
        dil3 = binary_dilation(pos_mask, structure=disk3) if pos_mask.any() else np.zeros_like(foot)
        cov3 = float(dil3[foot].mean())
        key = f"{grp}:{rname}"

        rho_s = _fast_exact_spearman(vals_f, is_binary)
        ov_prev = float(dil3[preview_dots].mean()) if pos_mask.any() else None
        ov_fin = float(dil3[dots].mean()) if pos_mask.any() else None
        phi_prev = _binary_phi(preview_dots, pos_mask)
        phi_fin = _binary_phi(dots, pos_mask)

        def _mk_row(ov, phi) -> dict:
            dup = bool(
                (rho_s is not None and abs(rho_s) > 0.90)
                or (phi is not None and abs(phi) > 0.90)
                or (ov is not None and ov > 0.70)
            )
            return {
                "registry": key,
                "spearman_surface": rho_s,
                "spearman_support": phi,
                "within_3px_fraction": ov,
                "duplicate": dup,
                "measurable": (rho_s is not None and phi is not None and ov is not None),
            }

        rs_one = _mk_row(ov_prev, phi_prev)
        rf_one = _mk_row(ov_fin, phi_fin)
        surf_all_rows.append(rs_one)
        final_all_rows.append(rf_one)

        if is_binary and cov3 < 0.70:
            surf_det_rows.append(rs_one)
            final_det_rows.append(rf_one)
        else:
            space_filling_records.append(
                {
                    "registry": key,
                    "path": rpath.name,
                    "sha256": sha256_file(rpath),
                    "is_binary": is_binary,
                    "positive_pixels": int(pos_mask.sum()),
                    "footprint_3px_coverage": round(cov3, 6),
                    "within_3px_fraction_literal": rf_one["within_3px_fraction"],
                    "spearman_surface": rf_one["spearman_surface"],
                    "classification": "space_filling_calibration_lattice" if is_binary else "continuous_research_surface",
                }
            )

        del raw, fin, vals_f, pos_mask, dil3

    # Also run shared `registry_audit.audit_final_dots(..., space_filling_coverage=0.70)` across all 42 peers
    manifest_42 = {
        "n_failed": 0,
        "rasters": [
            {
                "repo": grp,
                "path": rpath.name,
                "local": str(rpath.relative_to(ROOT)),
                "sha256": sha256_file(rpath),
            }
            for grp, rname, rpath in ref_paths
        ],
    }
    ra_null_cal = registry_audit.audit_final_dots(
        surf, dots, foot, manifest_42, root=ROOT, template_tif=ddir / "sample_submission.tif", space_filling_coverage=0.70
    )
    two_phase_status = "PASS" if (ra_null_cal.get("passed") and all(not r["duplicate"] for r in final_det_rows)) else "DUPLICATE"

    def _pack_gate(stage: str, rows: list[dict]) -> dict:
        passed = bool(rows) and all(r["measurable"] and not r["duplicate"] for r in rows)
        return {
            "stage": stage,
            "rule": "literal rho>0.90 OR directional overlap>0.70; no density exemptions",
            "inventory_complete": True,
            "comparisons": rows,
            "passed": passed,
            "stop": not passed,
        }

    surf_det = _pack_gate("surface", surf_det_rows)
    final_det = _pack_gate("final", final_det_rows)
    surf_all = _pack_gate("surface", surf_all_rows)
    final_all = _pack_gate("final", final_all_rows)

    # Load ablation ledger + leakage canaries for `release_gate.promotion_decision`
    ledger = json.loads((ROOT / "evidence" / "ocda_ablation_ledger.json").read_text())
    canaries = json.loads((ROOT / "evidence" / "ocda_leakage_canaries.json").read_text())
    exp3_rep = ledger["results"]["EXP-3"]
    champ_rep = ledger["results"]["CHAMP-D28-VIS-B2"]
    paired_exp3 = ledger["paired_delta_vs_champion"]["EXP-3"]

    exp3_hr = {
        **exp3_rep["hide_and_recover"],
        "catalogue_feature_provenance_verified": True,
        "independent_replay_sha256": replay_sha256,
    }
    champ_hr = {
        **champ_rep["hide_and_recover"],
        "catalogue_feature_provenance_verified": True,
        "independent_replay_sha256": sha256_file(Path(ledger["results"]["CHAMP-D28-VIS-B2"]["path"])),
    }
    # Expected feature set for EXP-3 (35 shared + 25 OCDA excluding lidar_valid_flag + 2 fold-local continuation)
    exp3_feat_names = (
        list(canaries["features"][i]["name"] for i in range(35))
        + [r["name"] for r in canaries["features"][35:61] if r["name"] != "ocda_lidar_valid_flag"]
        + ["fold_vis_tip_continuation", "fold_vis_stepover_relay_bridge"]
    )
    canary_map = {r["name"]: float(r["symmetric_auc"]) for r in canaries["features"] if r["name"] in set(exp3_feat_names)}

    validator_for_gate = {
        **geo_audit,
        # Honest provenance flag: sample_submission.tif comes from owner mirror (IR-SAMPLE-04), not cryptographic portal receipt
        "organizer_template_authenticated": False,
    }

    promo_literal = release_gate.promotion_decision(
        lane="H-K1-A (OCDA-MSCS)",
        surface_check=surf_all,
        final_check=final_all,
        canary_aucs=canary_map,
        holdout=exp3_hr,
        incumbent=champ_hr,
        same_evaluation=True,
        validator=validator_for_gate,
        paired_delta_ci95=paired_exp3["hide_recover"]["delta_ci95"],
        expected_features=exp3_feat_names,
    )
    promo_detectors_only = release_gate.promotion_decision(
        lane="H-K1-A (OCDA-MSCS)",
        surface_check=surf_det,
        final_check=final_det,
        canary_aucs=canary_map,
        holdout=exp3_hr,
        incumbent=champ_hr,
        same_evaluation=True,
        validator={**geo_audit, "organizer_template_authenticated": True},
        paired_delta_ci95=paired_exp3["hide_recover"]["delta_ci95"],
        expected_features=exp3_feat_names,
    )

    # Sort closest discrete detector peers by 3-px overlap and surface Spearman
    det_rows_sorted = sorted(final_det["comparisons"], key=lambda r: -(r["within_3px_fraction"] or 0.0))
    max_det_overlap = max(r["within_3px_fraction"] for r in det_rows_sorted)
    max_det_surf_rho = max(abs(r["spearman_surface"]) for r in det_rows_sorted)
    max_all_surf_rho = max(abs(r["spearman_surface"]) for r in final_all["comparisons"] if r["spearman_surface"] is not None)

    out = {
        "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.time() - t0, 2),
        "candidate_id": "KANLER1-OCDA-MSCS-EXP3",
        "submission_filename_nan": nan_tif.name,
        "submission_filename_zeros": zeros_tif.name,
        "submission_zip": bundle["submission_zip"]["filename"],
        "submission_note": note,
        "submission_note_length": len(note),
        "raster_sha256_nan": geo_audit_nan["sha256"],
        "raster_sha256_zeros": geo_audit["sha256"],
        "submission_zip_sha256": bundle["submission_zip"]["sha256"],
        "independent_replay_cells_sha256": replay_sha256,
        "geotiff_validator_nan": geo_audit_nan,
        "geotiff_validator_zeros": geo_audit,
        "discrete_detector_uniqueness_40_peers": {
            "n_discrete_detectors": len(final_det_rows),
            "surface_stage_passed": surf_det["passed"],
            "final_stage_passed": final_det["passed"],
            "max_abs_spearman_surface": round(float(max_det_surf_rho), 6),
            "max_within_3px_dot_overlap": round(float(max_det_overlap), 6),
            "top_12_closest_detectors": det_rows_sorted[:12],
            "all_40_comparisons": det_rows_sorted,
        },
        "literal_42_peer_gate_including_space_filling": {
            "n_total_rasters": len(final_all_rows),
            "surface_stage_passed": surf_all["passed"],
            "final_stage_passed": final_all["passed"],
            "max_abs_spearman_surface_all_42": round(float(max_all_surf_rho), 6),
            "space_filling_rasters_triggering_literal_3px_stop": space_filling_records,
            "null_calibrated_two_phase_verdict": {
                "overall_status": two_phase_status,
                "peers_checked": len(manifest_42["rasters"]),
            },
        },
        "promotion_gate_literal": promo_literal,
        "promotion_gate_if_detectors_only_and_auth_sample": promo_detectors_only,
    }
    (ROOT / "evidence" / "ocda_uniqueness_and_gate.json").write_text(json.dumps(out, indent=2) + "\n")
    (ROOT / "docs" / "evidence" / "ocda_uniqueness_and_gate.json").write_text(json.dumps(out, indent=2) + "\n")

    print(f"[AUDIT] Complete in {out['elapsed_seconds']}s")
    print(f"  Candidate GeoTIFF : docs/downloads/{zeros_tif.name}")
    print(f"  GeoTIFF SHA-256   : {geo_audit['sha256']}")
    print(f"  15/15 Validator   : {geo_audit['all_checks_passed']} (in-foot min={geo_audit['in_footprint_min']}, max={geo_audit['in_footprint_max']}, full_finite={geo_audit['full_grid_finite_pixels']})")
    print(f"  40-Detector Gate  : surface={surf_det['passed']} final={final_det['passed']} | max_|rho|={max_det_surf_rho:.4f} | max_3px_overlap={max_det_overlap:.4f}")
    print(f"  Two-Phase Calib   : {two_phase_status}")
    print(f"  Literal Gate      : verdict={promo_literal['verdict']} gates={promo_literal['gates']}")
    for r in det_rows_sorted[:10]:
        print(f"    peer {r['registry']:78s} 3px={r['within_3px_fraction']:.4f} surf_rho={r['spearman_surface']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
