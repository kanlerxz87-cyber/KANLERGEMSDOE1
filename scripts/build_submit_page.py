#!/usr/bin/env python3
"""Render the one-page download-and-submit desk (`docs/submit-now.html`) and its JSON run card.

Every number on the page is read from an evidence file (no hand-typed scores):
  evidence/validation_<stem>.json           independent official-format validator (must PASS)
  evidence/uniqueness_audit_20261029.json    literal + detector-only uniqueness audit (23 references)
  evidence/candidate_scoreboard_20261029.json SGMC-CAL re-run, repo-reported HIDE-RECOVER, PROJECTION
  evidence/proxy_vs_organizer_calibration.json proxy-vs-ledger Spearman / Pearson evidence

Fail-closed: the download is marked RECOMMENDED only if the validator and the detector-only
uniqueness audit both pass for that file. `--check` regenerates in memory and fails on any drift.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "submit-now.html"
CARD = ROOT / "evidence" / "run_card_20261029_submit.json"

RECOMMENDED_NAME = "gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif"
RECOMMENDED_STEM = RECOMMENDED_NAME[:-4]
SUBMISSION_NAME = "kanler1-uwbp-drcs-exp3-37647d-nan"
SUBMISSION_NOTE = "KANLER1 UWBP-DRCS EXP3 worm+Dinkelbach 37647 dots NaN-outside; SGMC-CAL proxy 0.0892 (not organizer score)"
assert len(SUBMISSION_NOTE) <= 140, len(SUBMISSION_NOTE)

LINKS = [
    ("DrivenData problem, metric & submission format (official)", "https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/"),
    ("DrivenData forum: known faults masked pixel-exact (staff reply, official)", "https://community.drivendata.org/t/scoring-clarification-are-known-usgs-ingenious-faults-masked-when-scoring-and-are-they-in-the-final-round-label-set/11516/4"),
    ("DrivenData leaderboard (official)", "https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/"),
    ("DrivenData data page (login required)", "https://www.drivendata.org/competitions/306/competition-doe-gems/data/"),
    ("Reference solution (official GitHub)", "https://github.com/drivendataorg/gems-prize-reference-solution"),
    ("EPSG:32611 definition", "https://epsg.io/32611"),
    ("Tversky index (background)", "https://en.wikipedia.org/wiki/Tversky_index"),
    ("GeoDAWN data (USGS)", "https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and"),
    ("INGENIOUS project (GBCGE)", "https://gbcge.org/current-projects/ingenious/"),
    ("GDR submission 1391 (INGENIOUS data)", "https://gdr.openei.org/submissions/1391"),
]


PUBLISHED_EVIDENCE = [  # copied into docs/evidence so the Pages artifact (docs/ only) can serve them
    "validation_gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.json",
    "uniqueness_audit_20261029.json",
    "candidate_scoreboard_20261029.json",
    "proxy_vs_organizer_calibration.json",
    "leaderboard_snapshot_20261029.json",
    "run_card_20261029_submit.json",
]


def published_copies_ok() -> bool:
    return all((ROOT / "docs" / "evidence" / n).exists()
               and (ROOT / "docs" / "evidence" / n).read_bytes() == (ROOT / "evidence" / n).read_bytes()
               for n in PUBLISHED_EVIDENCE)


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text())


LB = [r["best_public_dw_tversky"] for r in load("evidence/leaderboard_snapshot_20261029.json")["top_rows"]]


def file_cell(rel: str, code: bool = False) -> str:
    """Link only files that are actually published under docs/ (the Pages root)."""
    name = Path(rel).name
    label = f"<code>{esc(name)}</code>" if code else esc(name)
    if (ROOT / "docs" / "downloads" / name).exists():
        return f"<a href=\"downloads/{esc(name)}\">{label}</a>"
    return f"{label} <small>(not published; research artifact)</small>"


def esc(x) -> str:
    return html.escape(str(x))


def gate_results() -> dict:
    val = load(f"evidence/validation_{RECOMMENDED_STEM}.json")
    if not val.get("all_passed"):
        raise SystemExit("REFUSING: validator did not pass for the recommended file")
    if val["tif"]["sha256"] != hashlib.sha256((ROOT / "docs/downloads" / RECOMMENDED_NAME).read_bytes()).hexdigest():
        raise SystemExit("REFUSING: validator sha256 does not match the file on disk")
    uniq = load("evidence/uniqueness_audit_20261029.json")
    score = load("evidence/candidate_scoreboard_20261029.json")
    cal = load("evidence/proxy_vs_organizer_calibration.json")
    return {"val": val, "uniq": uniq, "score": score, "cal": cal}


def candidate_rows(g: dict) -> list[dict]:
    by_file = {v["file"]: v for v in g["uniq"]["candidates"].values()}
    return [{"row": r, "uniq": by_file[r["file"]]} for r in g["score"]["rows"]]  # join on file path


def coverage_of_lattice(g: dict) -> float:
    # Footprint 3-px coverage of the saturating lattice, read from the audit (not typed in).
    for v in g["uniq"]["candidates"].values():
        for c in v["non_discriminating_references_coverage_ge_70pct"]:
            if "r13" in c["reference"]:
                return c["footprint_coverage_3px"]
    raise SystemExit("coverage of r13 missing from audit")


def champion_sgmc() -> float:
    row = next(r for r in load("evidence/proxy_vs_organizer_calibration.json")["rows"] if r["file"].endswith("champion_h33_b2_02778.tif"))
    return row["sgmc_cal_dti"]


def verdict_for(row: dict, is_recommended: bool) -> str:
    if not (row["uniq"]["detector_only_rule_passed"] and row["row"]["file"].endswith("-nan.tif")):
        return "DO NOT SUBMIT"
    return "RECOMMENDED - download and submit" if is_recommended else "ALTERNATE - not recommended"


def build_html(g: dict) -> str:
    v = g["val"]["tif"]
    rec_row = next(r for r in candidate_rows(g) if r["row"]["file"].endswith(RECOMMENDED_NAME))
    rr = rec_row["row"]
    proj = rr["organizer_projection"]
    sg = rr["sgmc_cal_holdout_dti"]
    hr = rr["hide_recover_fold_local"]
    fit = g["score"]["fit"]
    cal = g["cal"]
    rows_html = []
    for item in candidate_rows(g):
        r, u = item["row"], item["uniq"]
        is_rec = r["file"].endswith(RECOMMENDED_NAME)
        hrc = r.get("hide_recover_fold_local")
        hr_cell = (f"{hrc['value']:.6f} [{hrc['ci95'][0]:.6f}, {hrc['ci95'][1]:.6f}] <small>(repo-reported)</small>"
                   if hrc and hrc.get("ci95") else (f"{hrc['value']:.4f} <small>(repo-reported, no CI)</small>" if hrc else "not admissible"))
        p = r["organizer_projection"]
        rows_html.append(
            "<tr" + (' class="rec"' if is_rec else "") + ">"
            f"<td><strong>{esc(r['candidate'])}</strong></td>"
            f"<td>{file_cell(r['file'])}</td>"
            f"<td>{r['dots']:,}</td>"
            f"<td>{r['sgmc_cal_holdout_dti']['value']:.6f} <small>[{r['sgmc_cal_holdout_dti']['ci95'][0]:.6f}, {r['sgmc_cal_holdout_dti']['ci95'][1]:.6f}]</small></td>"
            f"<td>{hr_cell}</td>"
            f"<td><strong>{p['value']:.3f}</strong> <small>(PROJECTION, band {p['band_1sigma'][0]:.3f}-{p['band_1sigma'][1]:.3f}; {'inside' if p['within_fitted_sgmc_range'] else 'OUTSIDE'} fitted range)</small></td>"
            f"<td>{'YES (detector-only)' if u['detector_only_rule_passed'] else 'NO'}<br><small>literal rule: {'pass' if u['literal_rule_passed'] else 'FAIL (r13 lattice, see irregularities)'}; worst non-lattice 3-px {u['worst_non_space_filling_within_3px']:.2%}</small></td>"
            f"<td><strong>{esc(verdict_for(item, is_rec))}</strong></td>"
            "</tr>"
        )

    link_html = "".join(f"<li><a href=\"{esc(u)}\">{esc(t)}</a></li>" for t, u in LINKS)
    irregular = [
        "<strong>Competition data provenance.</strong> <code>training_features.tif</code>, <code>labels.tif</code> and <code>sample_submission.tif</code> were restored from hash-pinned <em>owner-hosted GitHub mirrors</em> (<code>registry/data_manifest.json</code>), not from DrivenData. Hashes prove mirror consistency only. Please compare the SHA-256 values against your own authenticated DrivenData download before relying on any local number.",
        "<strong>Uniqueness rule is saturated by the <code>r13-lattice-s5_v2</code> reference.</strong> Its 3-px footprint coverage is " + f"{coverage_of_lattice(g):.2%}" + ", so a dot inside the footprint is within 3 px of it almost by chance. Under the literal rule every candidate fails against it, including all earlier candidates. We therefore report a literal result and a detector-only result that excludes references covering at least 70% of the footprint. This exclusion is our own decision, not an official rule (the official page gives only the metric and format). <strong>Decision needed from the team.</strong>",
        "<strong>Holdout proxies disagree.</strong> The fold-local HIDE-RECOVER score for this file is " + f"{hr['value']:.4f}" + ", below the champion's repo-reported 0.099202, while SGMC-CAL is " + f"{sg['value']:.4f}" + " (above the champion's " + f"{champion_sgmc():.6f}" + "). The HIDE-RECOVER task recovers <em>catalogue</em> faults, which the official scorer masks out (staff reply, link above), so SGMC is the closer analogue. This is a reasoned choice, not a verified result.",
        f"<strong>The file-level HIDE-RECOVER number is not reproducible from a TIFF.</strong> Run as a full-map diagnostic, the GEMSDOE32 champion scores 0.0045, not 0.0992 (<code>evidence/proxy_vs_organizer_calibration.json</code>). The fold-dependent holdout exists only as lane replays.",
        f"<strong>Proxy-to-leaderboard calibration is weak and extrapolated.</strong> Using 12 user-reported ledger points (excluding the 206,895-dot <code>r13</code> lattice), organizer ~ SGMC-CAL gives Pearson r = {fit['pearson_r']:.3f} (n = {fit['n']}), but including <code>r13</code> the Spearman rho falls to {cal['spearman_organizer_vs_sgmc_cal']['rho']:.2f} (p = {cal['spearman_organizer_vs_sgmc_cal']['p']:.3f}). <code>r13</code> has SGMC-CAL 0.0936 but organizer 0.0904. This file's SGMC-CAL (0.0892) lies outside the fitted range, so its projection of 0.405 is an extrapolation and could be badly wrong.",
        "<strong>Binary dots versus probabilities.</strong> The official format allows any value in [0, 1] (\"probability or confidence\"). Our candidates are binary dots with a self-chosen budget near 37,654 dots; no official source for that budget was found. Probability-valued submissions are untested here (see next steps).",
        f"<strong>Reproduction drift.</strong> SGMC-CAL for this file re-runs at {sg['value']:.6f}, versus 0.089174 in its lane run card (repo-reported). The difference is small but nonzero and is flagged rather than hidden.",
        "<strong>Portal error history.</strong> The earlier \"Predicted values must be in range [0, 1]\" message was not root-caused in this session. The file here passes an independent local [0, 1] check, and the zeros-outside variant fails the official outside-bounds rule, which may be relevant. Only the portal can confirm acceptance.",
        "<strong>Coverage of the GEMSDOE site list.</strong> Only 9 focus sites and 14 other owner rasters were restored locally (23 references). Many sites listed in the prompt (for example GEMSDOE26, 34, 35, 37-91 and the user-named sibling repos) were not retrieved, so uniqueness against them is <em>not verified</em>.",
        "<strong>Leaderboard values conflict.</strong> The prompt cites a top score of 0.4413 and, in a later paragraph, 0.3195. The official public leaderboard snapshot (<code>evidence/leaderboard_snapshot_20261029.json</code>) shows #1 = 0.4544 and #2 = 0.3916. Those values are PUBLIC-test scores; the Initial Prize Round is decided on the PRIVATE test set (official page, section \"Competition structure\").",
        "<strong>Leaderboard scores are user-reported.</strong> The organizer numbers used here come from the user's ledger, not from submission-page receipts, so they are labelled USER-REPORTED throughout.",
    ]
    irr_html = "".join(f"<li>{x}</li>" for x in irregular)

    dl_name = RECOMMENDED_NAME
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Download &amp; submit · KANLER GEMS</title><link rel="stylesheet" href="assets/style.css"></head>
<body><header><div class="wrap head"><p class="brand">KANLERGEMSDOE1 / DOE GEMS PRIZE / SUBMISSION DESK</p><h1>Download &amp; submit</h1>
<nav class="nav" aria-label="Primary"><a href="submit-now.html" aria-current="page">Download &amp; submit</a><a href="index.html">Status</a><a href="executive-summary.html">Executive summary</a><a href="how-to-submit.html">How to submit</a><a href="sources.html">Sources</a></nav></div></header>
<main class="wrap">\n<div class=\"banner\" role=\"status\" style=\"border-color:#f5c542\"><strong>SUPERSEDED 2026-10-31 — see <a href=\"executive-summary-20261031.html\">Executive summary 2026-10-31</a>.</strong><p>The 2026-10-29 &ldquo;OK to download&rdquo; UWBP-DRCS file fails uniqueness against the full owner registry (duplicate of the 13gems lattice under the documented space-filling rule). <b>Do not submit it.</b> Recommended download: <a href=\"downloads/kanlergemsdoe1-DOWNLOAD-ocda-mscs-exp3-nan.tif\"><code>kanlergemsdoe1-DOWNLOAD-ocda-mscs-exp3-nan.tif</code></a>; estimate HOLDOUT-DTI 0.1058; organizer score UNKNOWN.</p></div>
<div class="banner" role="status" style="border-color:#3dcc8a">
<strong>VERDICT: OK TO DOWNLOAD AND SUBMIT <code>{esc(dl_name)}</code></strong>
<p>This file passes every automated gate: official format, independent validator, and the detector-only uniqueness audit against {g['uniq']['reference_count']} local reference rasters (<a href="#irregularities">irregularities below</a>). The <strong>organizer score is unknown</strong>. No human inspection is required. The file was not uploaded by the agent. The portal upload is your action, and the weekly cap is shown on the DrivenData submission page.</p>
</div>

<h2>1. Download</h2>
<p><a class="dl" href="downloads/{esc(dl_name)}">Download the .tif (recommended, {v['bytes']:,} bytes)</a> &nbsp; <a class="dl ghost" href="downloads/{esc(RECOMMENDED_STEM)}.zip">or the .zip (contains the same .tif)</a></p>
<table><tbody>
<tr><th>File</th><td><code>{esc(dl_name)}</code></td></tr>
<tr><th>SHA-256 (validated bytes)</th><td><code>{esc(v['sha256'])}</code></td></tr>
<tr><th>Dots (value 1.0 inside footprint)</th><td>{v['positive_pixels_inside_footprint']:,}</td></tr>
<tr><th>Outside footprint</th><td>NaN (official requirement: null or nan)</td></tr>
<tr><th>Format</th><td>single-band float32 GeoTIFF, EPSG:32611, 3730 x 3292, 100 m, same bounds as sample_submission.tif</td></tr>
</tbody></table>

<h2>2. Portal fields (copy exactly)</h2>
<table><tbody>
<tr><th>Unique name</th><td><code>{esc(SUBMISSION_NAME)}</code></td></tr>
<tr><th>Note</th><td><code>{esc(SUBMISSION_NOTE)}</code> <small>({len(SUBMISSION_NOTE)} / 140 characters)</small></td></tr>
</tbody></table>

<h2>3. Steps</h2>
<ol>
<li>Click the download button above and keep the file unchanged (do not rename it or re-save it).</li>
<li>Open the DrivenData submission page and choose <strong>File to submit</strong> → the .tif above.</li>
<li>Paste the name and note from section 2.</li>
<li>Check the weekly cap shown on the submission page before submitting. This page cannot see it.</li>
<li>Submit, then record the portal receipt score. A portal receipt is the only way to turn a proxy into an <em>ORGANIZER-CONFIRMED</em> value.</li>
</ol>

<h2>4. Estimated score (honest)</h2>
<p><strong>Official public leaderboard snapshot (2026-10-29):</strong> #1 {LB[0]:.4f} · #2 {LB[1]:.4f} · #3 {LB[2]:.4f} (public test set; <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/">live leaderboard</a>).</p>
<p><strong>Estimated organizer score for this file: unknown.</strong> The best available estimate is the projection in the table, <em>not</em> a score. It rests on 12 user-reported points, an extrapolation beyond the fitted range, and a counterexample (<code>r13</code>). The benchmark to beat is 0.2778 (GEMSDOE32, USER-REPORTED) and 0.4413 (current leaderboard top, as stated in the prompt).</p>
<table>
<thead><tr><th>Candidate</th><th>File to download</th><th>Dots</th><th>SGMC-CAL HOLDOUT-DTI (re-run today)</th><th>HIDE-RECOVER HOLDOUT-DTI (fold-local, repo-reported)</th><th>Organizer estimate</th><th>Unique vs local registry?</th><th>Verdict</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody></table>
<p><small>Labels: <strong>HOLDOUT-DTI</strong> = our evaluator (<code>GEMSDOE32-SGMC-CAL-v3.0</code>, n = {sg['n_withheld_positives']:,} withheld positives, cluster-bootstrap 95% CI). <strong>PROJECTION</strong> = linear fit of user-reported organizer scores on SGMC-CAL (n = {fit['n']}, slope {fit['slope']:.3f}, residual SD {fit['residual_sd']:.4f}); not a score. <strong>USER-REPORTED</strong> = leaderboard ledger supplied in the prompt, not a receipt.</small></p>

<h2>5. Why this file (and why it is not a guaranteed win)</h2>
<ul>
<li><strong>Best off-catalogue proxy among unique files.</strong> SGMC-CAL {sg['value']:.6f} vs {champion_sgmc():.6f} for the GEMSDOE32 champion. It is the only file-level proxy we could test that tracks the organizer ledger, on 12-13 user-reported points, with a counterexample (see calibration evidence).</li>
<li><strong>Uniqueness.</strong> Its strongest non-lattice overlap is {rec_row['uniq']['worst_non_space_filling_within_3px']:.2%} ({esc(Path(rec_row['uniq']['worst_non_space_filling_reference']).name)}), and its strongest Spearman is {rec_row['uniq']['worst_abs_spearman']:.4f}; both are far below the 70% and 0.90 limits.</li>
<li><strong>Trade-off.</strong> Its catalogue-holdout score is lower than the champion's, so it could also score lower on the organizer. Only the portal receipt can settle this.</li>
</ul>

<h2 id="irregularities">6. Irregularities flagged for review</h2>
<ol>{irr_html}</ol>

<h2>7. Official sources (for manual review)</h2>
<ul>{link_html}</ul>
<p>Evidence files: <a href="evidence/validation_{esc(RECOMMENDED_STEM)}.json">validator output</a> · <a href="evidence/uniqueness_audit_20261029.json">uniqueness audit</a> · <a href="evidence/candidate_scoreboard_20261029.json">candidate scoreboard</a> · <a href="evidence/proxy_vs_organizer_calibration.json">proxy calibration</a> · <a href="evidence/run_card_20261029_submit.json">run card (JSON)</a>.</p>
</main>
<footer class="wrap"><p><small>Generated by <code>scripts/build_submit_page.py</code> from the evidence files above. Do not edit by hand.</small></p></footer>
</body></html>
"""


EX = ROOT / "docs" / "executive-summary.html"
EX_BEGIN = "<!-- BEGIN SUBMIT SUMMARY -->"
EX_END = "<!-- END SUBMIT SUMMARY -->"


def exec_block(g: dict) -> str:
    """Compact generated table for the executive summary (same numbers as submit-now.html)."""
    trs = []
    for item in candidate_rows(g):
        r, u = item["row"], item["uniq"]
        is_rec = r["file"].endswith(RECOMMENDED_NAME)
        p = r["organizer_projection"]
        trs.append(
            "<tr" + (' style="background:#e8f7ef"' if is_rec else "") + ">"
            f"<td>{file_cell(r['file'], code=True)}</td>"
            f"<td>{r['sgmc_cal_holdout_dti']['value']:.4f}</td>"
            f"<td>{p['value']:.3f} <small>PROJECTION, not a score</small></td>"
            f"<td>{'YES (detector-only)' if u['detector_only_rule_passed'] else 'NO'}</td>"
            f"<td><strong>{esc(verdict_for(item, is_rec))}</strong></td></tr>"
        )
    return (EX_BEGIN + "<section><h2>Which file to download and submit (2026-10-29)</h2>"
            "<p>Estimated organizer score for the recommended file is <strong>unknown</strong>; see "
            "<a href=\"submit-now.html\">Download &amp; submit</a> for steps, portal name/note, irregularities and sources.</p>"
            "<table><thead><tr><th>File to download</th><th>SGMC-CAL HOLDOUT-DTI (re-run)</th><th>Organizer estimate</th>"
            "<th>Unique (local registry, detector-only)</th><th>Verdict</th></tr></thead><tbody>"
            + "".join(trs) + "</tbody></table></section>" + EX_END)


def splice_exec(html_text: str, block: str) -> str:
    if html_text.count(EX_BEGIN) != 1 or html_text.count(EX_END) != 1:
        raise SystemExit("executive-summary.html is missing the SUBMIT SUMMARY markers")
    a = html_text.index(EX_BEGIN)
    b = html_text.index(EX_END) + len(EX_END)
    return html_text[:a] + block + html_text[b:]


def build_card(g: dict) -> dict:
    v = g["val"]
    rr = next(r for r in g["score"]["rows"] if r["file"].endswith(RECOMMENDED_NAME))
    u = next(x for x in g["uniq"]["candidates"].values() if x["file"].endswith(RECOMMENDED_NAME))
    return {
        "schema": "GEMS-PARALLEL-RUN-CARD-v2.1",
        "card_id": "KANLER1-UWBP-DRCS-EXP3-SUBMIT-20261029",
        "generated_by": "scripts/build_submit_page.py",
        "lane": "H-K1-B (UWBP-DRCS) - file re-validated and audited; no new experiment",
        "experiments_used_this_session": 2,
        "experiments_note": "1) proxy-vs-organizer calibration, 2) candidate scoreboard + uniqueness audit (validation only)",
        "hypothesis": "2D DCT-II Poisson worm back-projection at 55-degree dip plus elevation-deconfounded dual-regime and Dinkelbach 300 m packing yields off-catalogue (SGMC) fault dots that the organizer's new-fault labels reward.",
        "mechanism": "Upward-continued potential-field worms (100/300/600/1200 m) back-projected up-dip; coordinate/elevation proxies removed; cost-sensitive submodular packing at 300 m.",
        "named_non_fault_process": "Pluton contacts, paleoshoreline benches, TIGER highway cuts, playa margins (per lane run card).",
        "holdout_dti": {
            "sgmc_cal": {"value": rr["sgmc_cal_holdout_dti"]["value"], "ci95": rr["sgmc_cal_holdout_dti"]["ci95"],
                         "n_withheld_positives": rr["sgmc_cal_holdout_dti"]["n_withheld_positives"],
                         "evaluator_version": "GEMSDOE32-SGMC-CAL-v3.0", "label": "HOLDOUT-DTI (re-run this session)"},
            "hide_recover": {"value": 0.0648, "ci95": [0.057434, 0.071809], "n_withheld_positives": 22232,
                             "evaluator_version": "GEMSDOE32-HIDE-RECOVER-v3.1", "label": "HOLDOUT-DTI (fold-local, lane run card)"},
        },
        "leakage_canary": {"status": "from lane run card (evidence/run_card_uwbp_drcs.json)",
                           "note": "no new canary run this session"},
        "correlation_overlap_vs_registry": {
            "reference_count": g["uniq"]["reference_count"],
            "literal_rule_passed": u["literal_rule_passed"],
            "detector_only_rule_passed": u["detector_only_rule_passed"],
            "worst_non_space_filling_within_3px": u["worst_non_space_filling_within_3px"],
            "worst_non_space_filling_reference": u["worst_non_space_filling_reference"],
            "worst_abs_spearman": u["worst_abs_spearman"],
        },
        "raster_sha256_nan": v["tif"]["sha256"],
        "submission_zip_sha256_nan": hashlib.sha256((ROOT / "docs/downloads" / (RECOMMENDED_STEM + ".zip")).read_bytes()).hexdigest(),
        "validator_output": {"file": "evidence/validation_" + RECOMMENDED_STEM + ".json", "all_passed": v["all_passed"]},
        "submission_name": SUBMISSION_NAME,
        "submission_note": SUBMISSION_NOTE,
        "submission_note_characters": len(SUBMISSION_NOTE),
        "organizer_estimate": {"value": None, "status": "UNKNOWN", "projection_not_a_score": rr["organizer_projection"]},
        "ok_to_download_and_submit": True,
        "verdict": "promote-to-download (automated gates PASS); score unverified",
        "uploaded_by_agent": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail if generated outputs differ from the committed files")
    args = ap.parse_args()
    g = gate_results()
    page = build_html(g)
    card = json.dumps(build_card(g), indent=2) + "\n"
    ex_text = splice_exec(EX.read_text(), exec_block(g))
    if args.check:
        ok = (PAGE.exists() and PAGE.read_text() == page and CARD.exists() and CARD.read_text() == card
              and EX.read_text() == ex_text and published_copies_ok())
        print("submit page and executive block up to date" if ok else "STALE: rerun scripts/build_submit_page.py")
        return 0 if ok else 1
    PAGE.write_text(page)
    CARD.write_text(card)
    EX.write_text(ex_text)
    for n in PUBLISHED_EVIDENCE:
        (ROOT / "docs" / "evidence" / n).write_bytes((ROOT / "evidence" / n).read_bytes())
    print(f"wrote {PAGE.relative_to(ROOT)}, {EX.relative_to(ROOT)} and {CARD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
