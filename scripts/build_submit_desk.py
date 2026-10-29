#!/usr/bin/env python3
"""Build the submission desk: a machine-computed verdict on whether ANY repo raster may be downloaded.

Reads only evidence written by the audit scripts (no hand-typed scores):
  docs/evidence/focus_submission_audit.json      (9 focus files: format, dots, zero-SGMC proxy)
  docs/evidence/uniqueness_vs_all_sites.json     (every candidate vs every crawled GEMSDOE TIF, incl. this repo)
  docs/evidence/leakage_canary_sgmc.json         (SGMC-lift canary per candidate file)
  docs/evidence/run_card_ocda_mscs.json          (HOLDOUT-DTI hide-and-recover paired delta vs incumbent)
  docs/evidence/gemsdoe_site_tif_index.json      (crawl coverage)

Writes docs/evidence/submit_verdict.json and docs/submit.html. `--check` fails if they are stale.

Gates (automated; none needs a human):
  G1 FORMAT   : shared validator passes on the NaN-outside file (single band, EPSG:32611, 3730x3292, values in [0,1])
  G2 UNIQUE   : not pixel-identical to ANY crawled GEMSDOE TIF (this repo included, because its Pages site is listed),
                AND max within-3px <= 0.70 AND max |phi| <= 0.90 against every crawled reference
  G3 CANARY   : SGMC lift <= 1.5 (screen only; the protocol AUC canary is NOT run here)
  G4 BEATS    : primary HOLDOUT-DTI (hide-and-recover) paired delta vs incumbent: CI lower bound > 0
  G5 NOTE     : portal note <= 140 characters
  G6 RECEIPT  : organizer leaderboard receipt for the file (not available from this sandbox)
DOWNLOAD = G1 and G2 and G5.      SUBMIT = DOWNLOAD and G3 and G4.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
EVID = ROOT / "docs" / "evidence"
OUT_JSON = EVID / "submit_verdict.json"
OUT_HTML = ROOT / "docs" / "submit.html"
CANDIDATE = "OCDA-MSCS-EXP3-nan"
SOURCE = "docs/downloads/gemsdoe32-kanler1-ocda-mscs-exp3-37654d-20261027T1842Z-1db32b55-nan.tif"
NOTE = "KANLER1 OCDA-MSCS EXP3 piedmont-relay dots 37649d 300m; unique vs all GEMSDOE sites; automated gates"
PORTAL_NAME = "kanler1-ocda-mscs-exp3-37649d-nan"


def load(name: str):
    return json.loads((EVID / name).read_text())


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _find_paired(card) -> dict:
    if isinstance(card, dict):
        if "delta_ci95" in card and "ref_pooled_dti" in card:
            return card
        for v in card.values():
            r = _find_paired(v)
            if r:
                return r
    return None


def derive() -> dict:
    from gems32 import holdout, submission
    from gems32.paths import data_dir
    import rasterio

    ddir = data_dir()
    ctx = holdout.load_holdout_context(ddir)
    with rasterio.open(ddir / "labels.tif") as ds:
        labels = (ds.read(1) == 1) & ctx.foot
    audit = submission.audit_geotiff(ROOT / SOURCE, ctx.foot, labels, mode="nan",
                                     template_tif=ddir / "sample_submission.tif")
    uniq = load("uniqueness_vs_all_sites.json")
    canary = load("leakage_canary_sgmc.json")
    card = load("run_card_ocda_mscs.json")
    index = load("gemsdoe_site_tif_index.json")
    focus = load("focus_submission_audit.json")

    u = next(r for r in uniq["candidates"] if r["candidate"] == CANDIDATE)
    # The canary is run on the -zeros sibling (same dots, zeros-outside template); match by stem.
    canary_file = SOURCE.replace("-nan.tif", "-zeros.tif")
    c = next(r for r in canary["rows"] if r["file"] == canary_file)
    hr = _find_paired(card)
    src_sha = sha256(ROOT / SOURCE)

    g = {
        "G1_format": bool(audit["all_checks_passed"] and audit["official_submission_format_compatible"]),
        "G2_unique_vs_all_crawled_sites": bool(u["uniqueness_gate_pass"]),
        "G3_leakage_canary_sgmc_lift_le_1p5": bool(c["lift"] is not None and c["lift"] <= 1.5),
        "G4_beats_current_best_hr_ci_gt_0": bool(hr["delta_ci95"][0] > 0),
        "G5_note_le_140": len(NOTE) <= 140,
        "G6_organizer_receipt": False,
    }
    download = g["G1_format"] and g["G2_unique_vs_all_crawled_sites"] and g["G5_note_le_140"]
    submit = download and g["G3_leakage_canary_sgmc_lift_le_1p5"] and g["G4_beats_current_best_hr_ci_gt_0"]
    reasons = []
    if not g["G2_unique_vs_all_crawled_sites"]:
        if u["pixel_identical_to"]:
            reasons.append("Pixel-identical to already-published file(s): " + "; ".join(u["pixel_identical_to"]))
        if u["other_sites_max_within3px"] > uniq["rules"]["max_within3px"]:
            reasons.append(f"Within-3px overlap {u['other_sites_max_within3px']:.4f} with another GEMSDOE site's dots "
                           f"({u['other_sites_max_within3px_ref']}) exceeds 0.70 (rule: more than 70% within 3 px = duplicate)")
        if u["max_abs_phi"] > uniq["rules"]["max_abs_phi"]:
            reasons.append(f"|phi| {u['max_abs_phi']:.4f} exceeds 0.90")
    if not g["G4_beats_current_best_hr_ci_gt_0"]:
        reasons.append(f"Primary HOLDOUT-DTI paired delta CI {hr['delta_ci95']} includes 0 (not significantly better than the 0.2778 incumbent)")
    reasons.append("No organizer receipt is available from this sandbox (DrivenData not reachable)")
    return {
        "candidate": CANDIDATE, "source_file": SOURCE, "source_sha256": src_sha,
        "portal_name": PORTAL_NAME, "portal_note": NOTE, "portal_note_chars": len(NOTE),
        "format_audit": {k: audit[k] for k in ("crs", "dtype", "nodata_repr", "emitted_positive_pixels",
                                               "in_footprint_min", "in_footprint_max", "in_footprint_finite_pixels",
                                               "on_catalogue_positive_pixels", "all_checks_passed",
                                               "official_outside_bounds_null_or_nan")},
        "uniqueness": {"max_within3px": u["max_within3px"], "max_within3px_ref": u["max_within3px_ref"],
                       "max_abs_phi": u["max_abs_phi"], "max_abs_phi_ref": u["max_abs_phi_ref"],
                       "pixel_identical_to": u["pixel_identical_to"],
                       "other_sites_max_within3px": u["other_sites_max_within3px"],
                       "other_sites_max_within3px_ref": u["other_sites_max_within3px_ref"],
                       "n_distinct_reference_dotsets": uniq["n_distinct_reference_dotsets"],
                       "crawl_grid_tifs": sum(1 for r in index["index"] if r.get("competition_grid"))},
        "all_candidates": [{k: r[k] for k in ("candidate", "file", "dots", "max_within3px", "max_within3px_ref",
                                              "max_abs_phi", "pixel_identical_to", "other_sites_max_within3px",
                                              "uniqueness_gate_pass")} for r in uniq["candidates"]],
        "leakage_canary": {"sgmc_lift": c["lift"], "sgmc_frac": c["sgmc_canary_frac"],
                           "expected_random_frac": c["expected_random_frac"],
                           "protocol_auc_canary": "NOT RUN for this raster"},
        "holdout": {
            "primary_metric": "HOLDOUT-DTI hide-and-recover (GEMSDOE32-HIDE-RECOVER-v3.1), per-cell OOF npz from prior session; N_withheld=22232; not re-run here",
            "candidate_hr": hr["cand_pooled_dti"], "incumbent_hr": hr["ref_pooled_dti"],
            "paired_delta": hr["delta_dti"], "paired_delta_ci95": hr["delta_ci95"],
            "secondary_metric": "HOLDOUT-DTI zero-SGMC (GEMSDOE32-SGMC-CAL-v3.0), N_withheld=62703; see candidate_screen_vs_focus.json",
        },
        "gates": g, "download_ok": bool(download), "submit_ok": bool(submit), "hold_reasons": reasons,
        "projection_note": "No leaderboard score is estimated. Cross-lineage extrapolation is not a score.",
        "focus_sites_checked": len(focus["sites"]),
    }


def render(v: dict, focus: dict) -> str:
    e = html.escape
    ok = lambda b: "PASS" if b else "FAIL"  # noqa: E731
    if v["download_ok"]:
        dl_bg, dl_txt = "#0f5132", "YES — download the file"
    else:
        dl_bg, dl_txt = "#842029", "NO — no file in this repo is cleared for download or submission"
    uniq_why = ("the uniqueness gate fails: " + " ".join(v["hold_reasons"][:1]) if not v["gates"]["G2_unique_vs_all_crawled_sites"]
                else "all gates pass.")
    sb_bg, sb_txt = ("#0f5132", "YES — submit it") if v["submit_ok"] else ("#664d03", "HOLD — do not submit")
    rows = []
    for s in focus["sites"]:
        f = s["format"]
        rows.append(
            f"<tr><td>{e(s['site'])}</td><td class=n>{s['reported_score']:.4f}</td>"
            f"<td class=n>{s['emitted_dots']:,}</td>"
            f"<td class=n>{s['zero_sgmc_proxy']['calibrated_dti']:.4f} "
            f"[{s['zero_sgmc_proxy']['calibrated_ci95'][0]:.4f}, {s['zero_sgmc_proxy']['calibrated_ci95'][1]:.4f}]</td>"
            f"<td>{'NaN outside' if f['nonnull_outside'] == 0 else 'zeros outside'}</td>"
            f"<td>{'PASS' if f['in_range_01_inside'] and f['nan_inside'] == 0 else 'FAIL'}</td></tr>")
    cand_rows = []
    for r in v["all_candidates"]:
        cand_rows.append(
            f"<tr><td><code>{e(r['candidate'])}</code></td><td class=n>{r['dots']:,}</td>"
            f"<td class=n>{r['max_within3px']:.4f}</td><td>{e(r['max_within3px_ref'] or '')}</td>"
            f"<td>{'YES — identical to: ' + e('; '.join(r['pixel_identical_to'])) if r['pixel_identical_to'] else 'no'}</td>"
            f"<td class=n>{r['other_sites_max_within3px']:.4f}</td>"
            f"<td>{'PASS' if r['uniqueness_gate_pass'] else 'FAIL'}</td></tr>")
    g = v["gates"]
    gate_rows = "".join(f"<tr><td>{e(k)}</td><td>{ok(val) if isinstance(val, bool) else e(str(val))}</td></tr>" for k, val in g.items())
    ho = v["holdout"]
    reasons = "".join(f"<li>{e(r)}</li>" for r in v["hold_reasons"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Submission desk · KANLER GEMS</title><link rel="stylesheet" href="assets/style.css">
<style>.v{{padding:18px 22px;border-radius:12px;color:#fff;margin:14px 0}} table{{border-collapse:collapse;width:100%;margin:10px 0}} td,th{{border:1px solid #2a3442;padding:6px 8px;text-align:left;font-size:14px;vertical-align:top}} td.n{{text-align:right;font-variant-numeric:tabular-nums}} .big{{font-size:20px;font-weight:700}} code{{word-break:break-all}}</style>
</head><body><header><div class="wrap head"><p class="brand">KANLERGEMSDOE1 / SUBMISSION DESK</p><h1>Submission desk — is anything here OK to download and submit?</h1>
<nav class="nav" aria-label="Primary"><a href="index.html">Status</a><a href="submit.html" aria-current="page">Submission desk</a><a href="executive-summary.html">Executive summary</a><a href="how-to-submit.html">Submission gate</a></nav></div></header>
<main class="wrap">
<section class="v" style="background:{dl_bg}"><div class="big">DOWNLOAD: {e(dl_txt)}</div>
<p>Closest candidate: <code>{e(v['source_file'])}</code> · SHA-256 <code>{e(v['source_sha256'])}</code></p>
<p>Format is valid (EPSG:32611, 3730×3292, NaN outside, values in [0,1]). It is <b>not</b> cleared: {e(uniq_why)}</p></section>
<section class="v" style="background:{sb_bg}"><div class="big">SUBMIT: {e(sb_txt)}</div>
<ul>{reasons}</ul></section>
<h2>1. Gate results (computed by <code>scripts/build_submit_desk.py</code>)</h2>
<table><tr><th>Gate</th><th>Result</th></tr>{gate_rows}</table>
<h2>2. Every repo candidate vs every crawled GEMSDOE TIF</h2>
<p>Crawl: {v['uniqueness']['crawl_grid_tifs']:,} competition-grid TIFs from 107 listed repos ({v['uniqueness']['n_distinct_reference_dotsets']:,} distinct dot sets). Gate counts this repo's own published files. The last column excludes them.</p>
<table><tr><th>Candidate</th><th>Dots</th><th>Max within-3px</th><th>Max-overlap reference</th><th>Pixel-identical?</th><th>Max within-3px, other sites only</th><th>Gate</th></tr>{''.join(cand_rows)}</table>
<h2>3. Holdout numbers (labelled)</h2>
<table><tr><th>Metric</th><th>Value</th><th>Label / source</th></tr>
<tr><td>Primary: hide-and-recover, closest candidate</td><td class=n>{ho['candidate_hr']:.6f}</td><td>HOLDOUT-DTI, GEMSDOE32-HIDE-RECOVER-v3.1, N=22,232; prior-session per-cell OOF; not re-run here</td></tr>
<tr><td>Primary: hide-and-recover, incumbent (GEMSDOE32, 0.2778 receipt)</td><td class=n>{ho['incumbent_hr']:.6f}</td><td>HOLDOUT-DTI, same evaluator</td></tr>
<tr><td>Primary: paired delta (candidate − incumbent)</td><td class=n>{ho['paired_delta']:+.6f} [{ho['paired_delta_ci95'][0]:+.6f}, {ho['paired_delta_ci95'][1]:+.6f}]</td><td>HOLDOUT-DTI paired bootstrap 95% CI; includes 0 means not significantly better</td></tr>
<tr><td>Leaderboard estimate</td><td class=n>NOT ESTIMATED</td><td>No organizer receipt and no calibrated mapping. Projections across lineages are not scores.</td></tr></table>
<h2>4. The nine focus sites (reported scores; files fetched from pinned GitHub commits, SHA-256 verified)</h2>
<table><tr><th>Site</th><th>Reported score (USER/OWNER-REPORT)</th><th>Dots</th><th>Zero-SGMC proxy [95% CI] (HOLDOUT-DTI, re-computed)</th><th>Outside footprint</th><th>Range [0,1]</th></tr>
{''.join(rows)}</table>
<p>These nine are one lineage: pairwise within-3-px overlap is 0.87–1.00 (<code>docs/evidence/focus_submission_audit.json</code>).</p>
<h2>5. What to do next</h2>
<ol><li>Do not download or submit any file from this repo until the desk shows DOWNLOAD: YES.</li>
<li>Generate a new raster from a new lane (see <code>docs/research/hypotheses-20261029-next-lanes.md</code>) and rerun <code>scripts/uniqueness_vs_all_sites.py</code> and <code>scripts/build_submit_desk.py</code>.</li>
<li>When the desk shows DOWNLOAD: YES, the download link and the portal name and note appear here automatically.</li></ol>
<h2>6. Irregularities flagged for review</h2>
<ul>
<li><code>data/sample_submission.tif</code> has exactly the same 60,988 positive pixels as <code>labels.tif</code> across the whole footprint, so it is not a neutral template (our own check).</li>
<li><code>existing_faults.tif</code> is byte-identical to <code>labels.tif</code> (SHA-256 <code>7ba308cc…</code>).</li>
<li><code>GEMSDOE25</code> and <code>GEMSDOE30</code> both have 44,090 dots and identical zero-SGMC values.</li>
<li><code>H-UNQ1</code> shows zero-SGMC 0.3985 but places its dots on the SGMC truth (SGMC lift 7.07): leakage. Its number is excluded.</li>
<li>The crawl first stored files by basename, so same-named submissions overwrote each other. This was caught and fixed: every local file is now stored under its SHA-256 and re-hashed (0 mismatches).</li>
<li>Outside-footprint convention: GEMSDOE32 (reported 0.2778) is a zeros-outside file, while this repo asserts the official rule is NaN outside. Not resolvable offline.</li>
<li>Top leaderboard score differs across the prompt (0.3195 and 0.4413). Not reconciled.</li></ul>
<h2>7. Limitations</h2>
<ul><li>No DrivenData access; no organizer receipt is possible from this sandbox. All scores here are HOLDOUT-DTI or USER/OWNER-REPORT.</li>
<li>The crawl covers the default branch of 113 listed repos (107 hold competition-grid TIFs). Non-default <code>arena/*</code> branches and GitHub Pages builds were not crawled.</li>
<li>The protocol AUC leakage canary was not run for any raster.</li></ul>
<p><small>Deterministic output of <code>scripts/build_submit_desk.py</code> (no timestamp; <code>--check</code> verifies it is current). Evidence: <code>docs/evidence/submit_verdict.json</code>.</small></p>
</main></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    v = derive()
    focus = load("focus_submission_audit.json")
    text_json = json.dumps(v, indent=2, sort_keys=True) + "\n"
    text_html = render(v, focus)
    if args.check:
        ok = OUT_JSON.exists() and OUT_JSON.read_text() == text_json and OUT_HTML.exists() and OUT_HTML.read_text() == text_html
        print("CHECK", "PASS" if ok else "STALE")
        return 0 if ok else 1
    OUT_JSON.write_text(text_json)
    OUT_HTML.write_text(text_html)
    print(json.dumps({"download_ok": v["download_ok"], "submit_ok": v["submit_ok"], "gates": v["gates"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
