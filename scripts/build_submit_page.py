#!/usr/bin/env python3
"""Build the fail-closed submission status page and review run card.

This renderer is intentionally not a submission selector. It only publishes a file as
eligible when literal full-registry checks, a valid fold-local holdout improvement, an
authenticated template and the independent format validator all pass. The committed
candidate fails those conditions, so no download link is rendered as submission-ready.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "submit-now.html"
CARD = ROOT / "evidence" / "run_card_20261029_submit.json"
EXEC = ROOT / "docs" / "executive-summary.html"
CANDIDATE = "gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif"
STEM = CANDIDATE[:-4]
NOTE = "KANLER1 UWBP-DRCS Exp3 55deg-Worm+DeconfDual+Dinkelbach 37647d [RESEARCH-HOLD]"
LINKS = [
    ("DrivenData competition rules and submission format", "https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/"),
    ("DrivenData public leaderboard", "https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/"),
    ("DrivenData data page (login required)", "https://www.drivendata.org/competitions/306/competition-doe-gems/data/"),
    ("Official DrivenData reference solution", "https://github.com/drivendataorg/gems-prize-reference-solution"),
    ("USGS GeoDAWN", "https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and"),
    ("INGENIOUS project", "https://gbcge.org/current-projects/ingenious/"),
    ("DOE GDR submission 1391", "https://gdr.openei.org/submissions/1391"),
]
PUBLISHED_EVIDENCE = [
    "validation_gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.json",
    "uniqueness_audit_20261029.json", "candidate_scoreboard_20261029.json",
    "proxy_vs_organizer_calibration.json", "leaderboard_snapshot_20261029.json",
    "run_card_20261029_submit.json", "uwbp_uniqueness_and_gate.json",
]


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def evidence() -> dict:
    val = load(f"evidence/validation_{STEM}.json")
    gate = load("evidence/uwbp_uniqueness_and_gate.json")
    lane = load("evidence/run_card_uwbp_drcs.json")
    manifest = load("registry/data_manifest.json")
    template = next((x for x in manifest["files"] if x.get("id") == "sample_submission"), None)
    # The manifest/evidence explicitly mark mirror provenance rather than an authenticated
    # portal receipt; absent or unknown authentication can never be treated as True.
    authenticated = bool(template and template.get("organizer_authenticated") is True)
    tif = ROOT / "docs" / "downloads" / CANDIDATE
    if not tif.is_file() or hashlib.sha256(tif.read_bytes()).hexdigest() != val["tif"]["sha256"]:
        raise SystemExit("REFUSING: candidate bytes do not match the validator SHA-256")
    return {"val": val, "gate": gate, "lane": lane,
            "template_authenticated": authenticated, "tif": tif}


def build_card(g: dict) -> dict:
    lane = g["lane"]
    valid = lane["holdout_dti"]
    sgmc = valid["sgmc_regional_off_catalogue"]
    audit = g["gate"]["literal_peer_gate_including_space_filling"]
    raster_validation = g["val"]["tif"]
    return {
        "schema": "GEMS-PARALLEL-RUN-CARD-v2.2",
        "review_date_utc": "2026-10-31",
        "lane": "H-K1-B (UWBP-DRCS), previously executed; no experiment run in this review",
        "hypothesis": lane["hypothesis"],
        "mechanism": lane["mechanism"],
        "named_non_fault_process": lane["named_non_fault_process"],
        "holdout_dti": {
            "hide_recover": {"label": "HOLDOUT-DTI", "evaluator_version": "GEMSDOE32-HIDE-RECOVER-v3.1",
                "n_withheld_positives": valid["n_withheld_positives"], "value": valid["valid_value"],
                "ci95": valid["valid_ci95"], "status": "historical lane evidence; not rerun in this review"},
            "sgmc_cal": {"label": "HOLDOUT-DTI", "evaluator_version": "GEMSDOE32-SGMC-CAL-v3.0",
                "n_withheld_positives": sgmc["n_withheld_positives"],
                "value": sgmc["exp_b3_sgmc_prevalence_calibrated_dti"],
                "ci95": sgmc["exp_b3_sgmc_calibrated_ci95"], "status": "historical lane evidence; not rerun in this review"}
        },
        "comparison": {
            "benchmark_hide_recover": {"label": "HOLDOUT-DTI", "evaluator_version": "GEMSDOE32-HIDE-RECOVER-v3.1",
                "n_withheld_positives": valid["n_withheld_positives"], "value": valid["incumbent_gemsdoe32_fold_honest_d28_b2"]["pooled_dti"],
                "ci95": valid["incumbent_gemsdoe32_fold_honest_d28_b2"]["ci95"]},
            "paired_delta_ci95": valid["paired_delta_vs_incumbent_hide_recover"]["delta_ci95"],
            "note": "UWBP-DRCS is below the D2.8/B2 hide-and-recover benchmark; no improvement claim."
        },
        "correlation_overlap_vs_registry": {
            "registry_rasters_checked": audit["n_total_rasters"],
            "literal_surface_gate_passed": audit["surface_stage_passed"],
            "literal_final_dot_gate_passed": audit["final_stage_passed"],
            "max_abs_surface_spearman": audit["max_abs_spearman_surface_all"],
            "lattice_overlap_fraction": audit["space_filling_rasters_triggering_literal_3px_stop"][0]["within_3px_fraction_literal"],
            "duplicate_verdict": audit["null_calibrated_two_phase_verdict"]["overall_status"],
            "full_fleet_complete": False
        },
        "raster_sha256": raster_validation["sha256"],
        "validator_output": {
            "local_format_validator_passed": g["val"]["all_passed"],
            "single_band_float32": raster_validation["checks"]["single_band"] and raster_validation["checks"]["dtype_float32"],
            "no_nan_inside_footprint": raster_validation["checks"]["no_nan_or_inf_inside_footprint"],
            "values_in_0_1": raster_validation["checks"]["values_in_0_1_inside_footprint"],
            "crs_shape_transform_match_local_template": all(raster_validation["checks"][k] for k in ("crs_epsg_32611", "shape_3730x3292", "transform_matches_template")),
            "template_authenticated_by_organizer": g["template_authenticated"],
            "qualification": "format preflight only; not authorization or organizer acceptance"
        },
        "submission_name": "kanler1-uwbp-drcs-exp3-37647d-nan",
        "submission_note": NOTE,
        "submission_note_characters": len(NOTE),
        "organizer_confirmed_score": None,
        "organizer_score_estimate": None,
        "verdict": "negative",
        "ok_to_download_and_submit": False,
        "reason": "Literal uniqueness gate fails; full registry is incomplete; candidate does not beat the best hide-and-recover holdout; organizer template provenance is unauthenticated.",
        "weekly_slots_used": 0,
        "new_experiments_this_review": 0
    }


def build_html(g: dict) -> str:
    val, card = g["val"]["tif"], build_card(g)
    hr, sg = card["holdout_dti"]["hide_recover"], card["holdout_dti"]["sgmc_cal"]
    overlap = card["correlation_overlap_vs_registry"]
    links = "".join(f'<li><a href="{esc(url)}">{esc(title)}</a></li>' for title, url in LINKS)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Submission readiness · KANLER GEMS</title><link rel="stylesheet" href="assets/style.css"></head>
<body><header><div class="wrap head"><p class="brand">KANLERGEMSDOE1 / DOE GEMS PRIZE / SUBMISSION DESK</p><h1>Submission readiness</h1>
<nav class="nav"><a href="index.html">Status</a><a href="executive-summary.html">Executive summary</a><a href="focus-sites-review-20261028.html">Nine-site review</a><a href="how-to-submit.html">How to submit</a><a href="sources.html">Sources</a></nav></div></header>
<main class="wrap"><div class="banner" role="alert"><strong>STOP — NO TIFF IS CLEARED TO DOWNLOAD AND SUBMIT.</strong>
<p>A previously generated research TIFF exists, but it fails the literal registry uniqueness gate and does not beat the best recorded fold-local HIDE-AND-RECOVER benchmark. Its format validation is not contest clearance. Do not upload it or spend a weekly slot.</p></div>
<h2>Reviewed candidate (research artifact only)</h2>
<table><thead><tr><th>Research file</th><th>Score evidence</th><th>Registry uniqueness</th><th>Format preflight</th><th>Decision</th></tr></thead><tbody>
<tr><td><code>{esc(CANDIDATE)}</code><br><small>SHA-256 <code>{esc(val['sha256'])}</code></small></td>
<td><strong>HOLDOUT-DTI</strong> {hr['value']:.6f} (GEMSDOE32-HIDE-RECOVER-v3.1; {hr['n_withheld_positives']:,} withheld positives; 95% CI [{hr['ci95'][0]:.6f}, {hr['ci95'][1]:.6f}])<br>
<strong>HOLDOUT-DTI</strong> {sg['value']:.6f} (GEMSDOE32-SGMC-CAL-v3.0; {sg['n_withheld_positives']:,} withheld positives; 95% CI [{sg['ci95'][0]:.6f}, {sg['ci95'][1]:.6f}])<br><small>Historical lane evidence, not rerun in this review; these are not organizer scores.</small></td>
<td><strong>FAIL</strong><br><small>Literal 3-px overlap {overlap['lattice_overlap_fraction']:.2%} with <code>13gems_20261001_r13-lattice-s5_v2_nan-outside</code> (spacing-5 calibration raster); exceeds the 70% stop threshold. Surface gate: FAIL. References measured: {overlap['registry_rasters_checked']}; complete fleet coverage: no.</small></td>
<td>PASS locally<br><small>single-band float32; EPSG:32611; 3730 × 3292; values in [0,1]; no NaN in footprint. Template source is not organizer-authenticated.</small></td>
<td><strong>NEGATIVE / DO NOT SUBMIT</strong></td></tr></tbody></table>
<p><strong>Organizer score:</strong> UNKNOWN; no submission-page receipt exists for this artifact. No defensible numerical organizer estimate is available. Historical user/owner reports are not receipts. The reported GEMSDOE32 maximum is <strong>0.2778 USER/OWNER-REPORT</strong>, not an independently confirmed score.</p>
<h2>Why the reported GEMSDOE32 entry is highest in the supplied nine-site history</h2>
<p>The repository's raster forensics describe the GEMSDOE32 candidate as a sparsified member of a family descended from the H19-5 support, with thinning and a visible-catalogue collar. A plausible explanation is fewer redundant interior ridge pixels and reduced mapped-fault halo overlap under an asymmetric distance-weighted Tversky metric. This is a mechanism-based interpretation, not causal proof: no paired organizer experiment isolates these changes. The reported 0.2778 is USER/OWNER-REPORT, not ORGANIZER-CONFIRMED.</p>
<p>The requested nine-site table is at <a href="focus-sites-review-20261028.html">Focus-site review</a>. It lists each supplied site's top reported reference, alternative reported entries, pairwise overlap result, unavailable holdout/leaderboard estimate, and explicit NO submission decision.</p>
<h2>Known blockers</h2><ul>
<li>Literal uniqueness: the existing candidate has >70% proximity to a registry raster and is stopped; detector-only exclusions do not override the supplied literal rule.</li>
<li>Registry completeness: the repository audit covers a subset, not every listed site/raster, and no full current-fleet certification is available.</li>
<li>Holdout promotion: this candidate's <strong>HOLDOUT-DTI</strong> HIDE-RECOVER result is below the recorded incumbent; there is no evidence it beats the best admissible holdout.</li>
<li>Data provenance: competition rasters are mirrored; authenticated DrivenData training/sample files are not present in <code>data/</code> in this checkout.</li>
<li>No additional experiments were run during this review. The previous UWBP-DRCS lane has already consumed its three-experiment budget.</li>
</ul>
<h2>Submission instructions (only after a future selector clearance)</h2>
<ol><li>Do not use any file linked or named on this research site unless its run card says <code>verdict: promote</code> and a separate selector authorizes a slot.</li><li>Use the official DrivenData submission form and confirm the current weekly cap there.</li><li>Upload one single-band GeoTIFF or a ZIP containing one GeoTIFF, matching the authenticated template's CRS, shape, geotransform and value range.</li><li>Use a unique short note of at most 140 characters and archive the portal receipt. Only then may a result be called ORGANIZER-CONFIRMED.</li></ol>
<p><strong>[0,1] range error:</strong> local validator PASS proves only local format/range checks against the local template; it cannot guarantee that the competition portal will accept the file. Never use the current candidate because its uniqueness and scientific gates fail.</p>
<h2>Official source links</h2><ul>{links}</ul>
<p>Evidence: <a href="evidence/run_card_20261029_submit.json">current negative run card</a> · <a href="evidence/uniqueness_audit_20261029.json">23-reference uniqueness audit</a> · <a href="evidence/uwbp_uniqueness_and_gate.json">59-raster literal gate audit</a> · <a href="evidence/validation_{esc(STEM)}.json">local validator receipt</a>.</p>
</main><footer class="wrap"><p>Generated from committed audit evidence. No submission was uploaded; zero weekly slots used.</p></footer></body></html>'''


def exec_block(g: dict) -> str:
    return ('<!-- BEGIN SUBMIT SUMMARY --><section><h2>Submission decision</h2>'
            '<p><strong>NO FILE IS CLEARED TO SUBMIT.</strong> The existing research artifact fails the literal registry uniqueness gate and is below the recorded HIDE-AND-RECOVER benchmark. '
            '<a href="submit-now.html">Open the fail-closed readiness report</a> · '
            '<a href="focus-sites-review-20261028.html">Compare the nine requested sites</a>.</p></section><!-- END SUBMIT SUMMARY -->')


def build_card_file(g: dict) -> str:
    return json.dumps(build_card(g), indent=2, allow_nan=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    g = evidence()
    page = build_html(g)
    card = build_card_file(g)
    text = EXEC.read_text(encoding="utf-8")
    begin, end = "<!-- BEGIN SUBMIT SUMMARY -->", "<!-- END SUBMIT SUMMARY -->"
    if text.count(begin) != 1 or text.count(end) != 1:
        raise SystemExit("executive summary markers missing or duplicated")
    start, stop = text.index(begin), text.index(end) + len(end)
    ex = text[:start] + exec_block(g) + text[stop:]
    copies_ok = all((ROOT / "docs/evidence" / name).is_file()
                    and (ROOT / "docs/evidence" / name).read_bytes() == (ROOT / "evidence" / name).read_bytes()
                    for name in PUBLISHED_EVIDENCE)
    outputs_ok = PAGE.exists() and PAGE.read_text(encoding="utf-8") == page and CARD.exists() and CARD.read_text(encoding="utf-8") == card and EXEC.read_text(encoding="utf-8") == ex and copies_ok
    if args.check:
        print("fail-closed submission desk is current" if outputs_ok else "STALE: run scripts/build_submit_page.py")
        return 0 if outputs_ok else 1
    PAGE.write_text(page, encoding="utf-8")
    CARD.write_text(card, encoding="utf-8")
    EXEC.write_text(ex, encoding="utf-8")
    for name in PUBLISHED_EVIDENCE:
        (ROOT / "docs/evidence" / name).write_bytes((ROOT / "evidence" / name).read_bytes())
    print("Updated fail-closed submission status; no file is cleared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
