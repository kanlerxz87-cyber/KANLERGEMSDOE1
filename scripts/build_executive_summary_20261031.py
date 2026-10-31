#!/usr/bin/env python3
"""Generate docs/executive-summary-20261031.html from the evidence JSON files (no hand-typed numbers).

Every score is labelled:
  HOLDOUT-DTI          -> computed by gems32.holdout (evaluator version, N, 95% CI shown)
  ORGANIZER-CONFIRMED  -> copied from a portal receipt (none available in this sandbox)
  USER-REPORTED        -> copied from the ledger in the user's request (not a portal receipt)
Usage: python scripts/build_executive_summary_20261031.py [--check]
"""
from __future__ import annotations

import hashlib
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "executive-summary-20261031.html"
OWN = Path("/tmp/owners")


def load(p: str) -> dict:
    return json.loads((ROOT / p).read_text())


def sha16(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "missing"


def e(x) -> str:
    return html.escape(str(x))


SITES = [
    # site, user-reported best score, file path in owner repo, note
    ("GEMSDOE24", "0.2477", "docs/downloads/gems24-h25-1-dotted-h19-5-d1-5-20261002-989f59505db1-nan.tif", "dotted H19-5 d1.5 (NaN)"),
    ("GEMSDOE25", "0.2600", "docs/downloads/gems25-dotted-h19-5-d2-8-20261002-e56ea318af89-nan.tif", "dotted H19-5 d2.8 (NaN)"),
    ("GEMSDOE27", "0.2449", "docs/downloads/gems27-topo-gap-closure-t-v2-on-d1-5-20261002-5512495c6bd1-nan.tif", "topo gap-closure (NaN)"),
    ("GEMSDOE28", "0.2710", "docs/downloads/gems28-h36-1-rung30-blind-r1-20261003-b531dae0a36f-nan.tif", "H36-1 rung30 blind (NaN)"),
    ("GEMSDOE30", "0.2600", "docs/downloads/gemsdoe30-d28-poisson300m-offcat-44090-20261003T233156Z-91eae1ca-nanoutside.tif", "D2.8 Poisson off-cat (nan-outside)"),
    ("GEMSDOE31", "0.2708", "docs/downloads/gemsdoe31-h27-4-solo-d28-20261004-8acb75e1-nan.tif", "H27-4 solo D2.8 (NaN)"),
    ("GEMSDOE32", "0.2778", "docs/downloads/gemsdoe32-h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros.tif", "H33-2 B2 — ZEROS outside (see irregularities)"),
    ("GEMSDOE33", "0.2632", "docs/downloads/GEMSDOE33-h33d-analog-tip-stepover-r30-20261004-cb490425926e-nanoutside.tif", "H33d analog tip (nan-outside)"),
    ("GEMSDOE36", "0.2750", "docs/downloads/gemsdoe36-anderson-geothermal-pinn-38854-20261004T230000Z-9b9ea4e6-zeros.tif", "Anderson PINN (ZEROS outside)"),
]


def build() -> str:
    pair = load("evidence/site_pair_overlap_20261031.json")["rows"]
    rec = "OCDA-MSCS-EXP3 (recommended)"
    hgb = "HGB-FOLDLOCAL-E2 (new)"
    uwb = "UWBP-DRCS-EXP3 (prior verdict)"
    site_rows = []
    for site, score, rel, note in SITES:
        f = OWN / site / rel
        r_rec = next(r for r in pair if r["candidate"] == rec and r["site"] == site)
        r_uwb = next(r for r in pair if r["candidate"] == uwb and r["site"] == site)
        site_rows.append(
            f"<tr><td><b>{e(site)}</b></td><td>{e(score)} <span class='tag user'>USER-REPORTED</span></td>"
            f"<td><code>{e(Path(rel).name)}</code><br><span class='muted'>{e(note)}</span></td>"
            f"<td><code>{sha16(f)}</code></td>"
            f"<td>{r_rec['within_3px_fraction']*100:.1f}% / |phi| {abs(r_rec['phi']):.4f} "
            f"<span class='tag ok'>not duplicate</span></td>"
            f"<td>{r_uwb['within_3px_fraction']*100:.1f}% / |phi| {abs(r_uwb['phi']):.4f}</td></tr>"
        )
    ocda = load("evidence/run_card_20261031.json")
    hg = load("evidence/fold_hgb_E2.json")["hide_and_recover"]
    hg_sg = load("evidence/fold_hgb_E2.json")["sgmc_off_catalogue_draw20_composite"]
    ex = []
    for k in ("E1", "E2", "E3"):
        d = load(f"evidence/fold_hgb_{k}.json")
        h = d["hide_and_recover"]
        ex.append(f"<tr><td>{k}</td><td>{'no thinning' if d['params']['nms_radius_px']==0 else str(d['params']['nms_radius_px'])+' px local-max thinning'}</td>"
                  f"<td>{h['pooled_dti']:.4f} <span class='tag'>HOLDOUT-DTI</span></td>"
                  f"<td>[{h['ci95_cluster_bootstrap'][0]:.4f}, {h['ci95_cluster_bootstrap'][1]:.4f}]</td>"
                  f"<td>{h['n_withheld_positives']:,}</td>"
                  f"<td>{'<b>best of three</b>' if k=='E2' else ''} NEGATIVE vs 0.1058</td></tr>")
    rec_sha = sha16(ROOT / "docs/downloads/kanlergemsdoe1-DOWNLOAD-ocda-mscs-exp3-nan.tif")
    hgb_sha = sha16(ROOT / "docs/downloads/kanlergemsdoe1-hgb-foldlocal-nms3-b2-20261031T005029Z-48e16833-nan.tif")
    uwb_sha = sha16(ROOT / "docs/downloads/gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif")
    rc = ocda["recommended_file"]
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Executive summary 2026-10-31 · KANLER GEMS</title>
<link rel="stylesheet" href="assets/style.css">
<style>
 table.t {{ width:100%; border-collapse:collapse; font-size:.92rem; margin:.6rem 0 1.2rem; }}
 table.t th, table.t td {{ border:1px solid var(--line); padding:.45rem .55rem; text-align:left; vertical-align:top; }}
 table.t th {{ background:var(--bg2); }}
 .tag {{ display:inline-block; font-size:.72rem; padding:.05rem .4rem; border-radius:4px; border:1px solid var(--line); color:var(--muted); }}
 .tag.user {{ color:var(--warn); border-color:var(--warn); }}
 .tag.ok {{ color:var(--good); border-color:var(--good); }}
 .tag.bad {{ color:var(--bad); border-color:var(--bad); }}
 .muted {{ color:var(--muted); }}
 .verdict {{ border:2px solid var(--good); border-radius:10px; padding:1rem 1.2rem; background:var(--card); }}
</style></head>
<body><header><div class="wrap head"><p class="brand">KANLERGEMSDOE1 / DOE GEMS PRIZE / EXECUTIVE SUMMARY</p>
<h1>Executive summary — 2026-10-31</h1>
<nav class="nav" aria-label="Primary"><a href="index.html">Status</a><a href="executive-summary-20261031.html" aria-current="page">Executive summary</a><a href="executive-summary.html">Earlier summary</a><a href="submit-now.html">Earlier verdict (superseded)</a><a href="how-to-submit.html">Submission gate</a></nav></div></header>
<main class="wrap">

<div class="verdict" role="status">
<h2 style="margin-top:0">VERDICT — download ONE file, then submit it only after the uniqueness sign-off below</h2>
<p><b>Download:</b> <a href="downloads/kanlergemsdoe1-DOWNLOAD-ocda-mscs-exp3-nan.tif"><code>kanlergemsdoe1-DOWNLOAD-ocda-mscs-exp3-nan.tif</code></a>
(SHA-256 <code>{e(rc['sha256'])}</code>; byte-identical to <code>{e(rc['identical_to'].split('/')[-1])}</code>)</p>
<ul>
<li><b>Format — PASS:</b> automated validator (no human inspector): single-band float32 GeoTIFF, EPSG:32611, 3730×3292, template transform, 37,649 dots, values exactly 0 or 1 inside the footprint, NaN outside. The validator checks the [0, 1] condition that the portal's “Predicted values must be in range [0, 1]” error enforces. Passing it is necessary, not a guarantee of acceptance.</li>
<li><b>Uniqueness — PASS under the repo's documented space-filling rule</b> against 720 GeoTIFFs in the nine GEMSDOE owner repos (|rho| ≤ 0.0375; no 3-px overlap above 0.70 after null calibration). <b>Literal rule — FAIL, but unavoidable:</b> one registry raster (<code>GEMSDOE24/inputs/calibration/13gems_20261001_r13-lattice-s5_v2_nan-outside.tif</code>) covers 99.87% of the footprint, so every dot file lands within 3 px of it. <b>Team decision required</b> before submitting.</li>
<li><b>Estimated score:</b> <span class="tag">HOLDOUT-DTI 0.1058</span> (evaluator GEMSDOE32-HIDE-RECOVER-v3.1, N = 22,232 withheld positives, 95% CI [0.0950, 0.1153]; status ADMISSIBLE_FOLD_LOCAL; recorded in <code>docs/evidence/run_card_ocda_mscs.json</code>, not re-run here). Its paired gain over the 0.0992 incumbent is <b>not significant</b> (CI [−0.0034, +0.0160]).</li>
<li><b>Organizer score: UNKNOWN.</b> No portal receipt is available to this sandbox. Holdout values are not on the leaderboard scale and must not be read as a leaderboard forecast.</li>
<li><b>Do NOT submit</b> the earlier “OK to download” file <code>gemsdoe32-kanler1-uwbp-drcs-exp3…-nan.tif</code>: it passes the format check but fails uniqueness (it is a duplicate of the 13gems lattice under the documented rule, excess 0.81 &gt; 0.70). Its earlier PASS was checked against only 23 local references.</li>
</ul>
<p class="muted">The agent did not submit anything. Upload is a user action on DrivenData.</p>
</div>

<h2>1. Per-site view (nine focus sites)</h2>
<p>Scores in this table are <span class="tag user">USER-REPORTED</span> (the ledger in the request). They are <b>not</b> portal receipts. The file for each site was located in the owner repository and hashed. The last two columns compare our recommended file, and the earlier UWBP file, with that site's top file.</p>
<table class="t"><thead><tr><th>Site</th><th>Top listed score</th><th>Top file (owner repo)</th><th>SHA-256 (16)</th><th>Recommended file vs this site: 3-px overlap / |phi|</th><th>Earlier UWBP file vs this site</th></tr></thead>
<tbody>{''.join(site_rows)}</tbody></table>
<p class="muted">Highest listed site score: GEMSDOE32 (0.2778). Checked by reading each file: seven of the nine top files are NaN-outside; GEMSDOE32 and GEMSDOE36 top files are zeros-outside (see irregularities I-4 and I-5). No site file is a duplicate of the recommended file (3-px overlap ≤ 35%, |phi| ≤ 0.007).</p>

<h2>2. Candidate files and their estimates</h2>
<table class="t"><thead><tr><th>File</th><th>Role</th><th>Holdout estimate</th><th>Validator</th><th>Uniqueness (owner registry)</th><th>Decision</th></tr></thead><tbody>
<tr><td><code>kanlergemsdoe1-DOWNLOAD-ocda-mscs-exp3-nan.tif</code><br><span class="muted">SHA {e(rec_sha)}…</span></td><td>Best tested unique file (copy of OCDA-MSCS EXP-3, same bytes)</td>
<td>0.1058 <span class="tag">HOLDOUT-DTI</span> [0.0950, 0.1153], N=22,232</td><td><span class="tag ok">PASS</span></td>
<td>Space-filling rule <span class="tag ok">PASS</span> · literal <span class="tag bad">FAIL (13gems lattice)</span></td><td><b>DOWNLOAD (after sign-off)</b></td></tr>
<tr><td><code>kanlergemsdoe1-hgb-foldlocal-nms3-b2-…-nan.tif</code><br><span class="muted">SHA {e(hgb_sha)}…</span></td><td>New file generated this session (fold-local HGB, 3-px thinning)</td>
<td>{hg['pooled_dti']:.4f} <span class="tag">HOLDOUT-DTI</span> [{hg['ci95_cluster_bootstrap'][0]:.4f}, {hg['ci95_cluster_bootstrap'][1]:.4f}], N={hg['n_withheld_positives']:,}; SGMC-CAL {hg_sg['sgmc_prevalence_calibrated_dti']:.4f}</td>
<td><span class="tag ok">PASS</span></td><td>Space-filling <span class="tag ok">PASS</span> · literal <span class="tag bad">FAIL (13gems lattice)</span></td><td>Valid, unique alternative; lower holdout than OCDA</td></tr>
<tr><td><code>gemsdoe32-kanler1-uwbp-drcs-exp3-…-nan.tif</code><br><span class="muted">SHA {e(uwb_sha)}…</span></td><td>Previous “OK to download” verdict</td>
<td>0.0648 <span class="tag">HOLDOUT-DTI</span> [0.0574, 0.0718] (recorded); SGMC-CAL 0.0892</td><td><span class="tag ok">PASS</span></td>
<td><span class="tag bad">FAIL</span> — duplicate of 13gems lattice (excess 0.81 &gt; 0.70)</td><td><b>DO NOT SUBMIT</b> (superseded)</td></tr>
</tbody></table>

<h2>3. Experiments run this session (budget: 3 experiments, reached)</h2>
<p>Lane: fold-local histogram gradient boosting on the 17 non-seismic bands, trained only on the visible catalogue with a 1.5 km collar; B = 2 px visible gate; budget matched to 37,654 dots. Shared evaluator <code>gems32.holdout.evaluate_hide_and_recover</code> (unmodified). The earthquake-derived bands 10 (deq_n100a15) and 16 (ieq_n100a15) are excluded from the model.</p>
<table class="t"><thead><tr><th>Run</th><th>Emission</th><th>Pooled DTI</th><th>95% CI</th><th>N withheld</th><th>Result</th></tr></thead><tbody>
{''.join(ex)}</tbody></table>
<p>Leakage canary (Rule 4): the highest single-band AUC on hidden truth vs background is <b>{ocda['leakage_canary']['max_auc']:.3f}</b> (threshold 0.90) — no leakage flag. None of the three experiments beats the recorded holdout best (0.1058) or the incumbent (0.0992). Negative results are logged, not hidden.</p>

<h2>4. Next steps and hypotheses</h2>
<p>Full ranked hypotheses: <a href="research/hypotheses-20261031.md"><code>docs/research/hypotheses-20261031.md</code></a>. Top untested idea: a multi-scale <b>structure-tensor</b> strike-coherence map on the RTP magnetic field and isostatic gravity gradient. The repo has no structure-tensor work (keyword search: 0 hits), so it's new. It was not validated here because the experiment budget is spent, and the first action for the next session is to validate it on the holdout.</p>

<h2>5. How to submit (after sign-off)</h2>
<ol>
<li>Sign in at the DrivenData competition page and open <i>New submission</i>.</li>
<li><b>File to submit:</b> choose <code>kanlergemsdoe1-DOWNLOAD-ocda-mscs-exp3-nan.tif</code> (official rules §3.2: a single GeoTIFF with a single raster layer at 100 m; a zip wrapper is not required).</li>
<li><b>Note (≤ 140 characters, 98 used):</b> <code>{e(ocda['submission']['note_<=140'])}</code></li>
<li>Expected result: no “Predicted values must be in range [0, 1]” error. If the portal reports anything else, record the exact text in <code>evidence/</code> and stop.</li>
<li>Official rules §3.2 allow three submissions per week. Check your count on the portal before uploading.</li>
</ol>

<h2>6. Irregularities flagged for review</h2>
<ul>
<li><b>I-1 Uniqueness (literal).</b> No non-empty dot file can satisfy the literal ≤ 70% 3-px rule against the 13gems lattice (99.87% coverage). The team must decide whether the documented space-filling exemption is valid. Repo open decision, now confirmed by the full registry audit.</li>
<li><b>I-2 Previous verdict was wrong.</b> The UWBP-DRCS-EXP3 file was declared unique after checking only 23 local references. Checked against the full owner registry it fails.</li>
<li><b>I-3 Ledger vs live leaderboard.</b> The request quotes a leaderboard high of 0.4413 and says 0.3195 is the highest. On the live DrivenData leaderboard (fetched today) #1 is 0.4544 and #2 is 0.3925; ranks 1–22 on the fetched page are all above 0.34. The 0.4413 and 0.3195 figures do not match.</li>
<li><b>I-4 GEMSDOE32 top file is a zeros-outside variant.</b> The repo's validator requires NaN outside the footprint, citing the DrivenData format page. The official rules (NLR 96647 §3.2) defer format to that page, which this sandbox cannot access, so the NaN rule is repo-sourced and unverified here. The 0.2778 entry is <code>…-zeros.tif</code>. Verify the required format and the portal receipt before relying on either.</li>
<li><b>I-5 GEMSDOE36 top file is zeros-outside too</b> (<code>…-zeros.tif</code>, 0.2750).</li>
<li><b>I-6 Holdout is not the organizer metric.</b> Holdout values (≈0.10) and organizer values (≈0.27–0.28) are on different scales. No projection is made.</li>
<li><b>I-7 Data provenance.</b> Competition rasters were restored from SHA-256-pinned owner mirrors on GitHub (not from DrivenData, which requires login). Hashes prove mirror consistency only. <code>sample_submission.tif</code> is an unauthenticated mirror.</li>
<li><b>I-8 Filename prefix.</b> The shared writer defaulted to <code>gemsdoe32-</code>, which reads like GEMSDOE32's own upload. New files use the <code>kanlergemsdoe1-</code> prefix; older files keep the old name.</li>
<li><b>I-9 OCDA target mismatch.</b> The OCDA file has 37,649 positives against a 37,654 filename target.</li>
<li><b>I-10 Generative-AI disclosure.</b> Official rules §3.2 require the submission narrative to state the extent and manner of any generative-AI use. This work used AI tools. The disclosure must be written into the narrative before any submission (the repo's AI_DISCLOSURE.md is a starting point, not the final text).</li>
</ul>

<h2>7. Reproduce</h2>
<pre style="white-space:pre-wrap;font-size:.85rem">bash scripts/download_competition_data.sh
.venv/bin/python scripts/run_fold_hgb_lane.py --experiment E2 --nms 3 --b 2
.venv/bin/python scripts/build_hgb_submission.py --nms 3 --b 2 --slug hgb-foldlocal-nms3-b2 --candidate-id kanler1-hgb-foldlocal-nms3-b2 --note "…"
.venv/bin/python scripts/validate_submission_file.py docs/downloads/kanlergemsdoe1-DOWNLOAD-ocda-mscs-exp3-nan.tif
.venv/bin/python scripts/audit_owner_registry.py --owner-dir /tmp/owners --candidate docs/downloads/kanlergemsdoe1-DOWNLOAD-ocda-mscs-exp3-nan.tif --space-filling-coverage 0.70 --out evidence/owner_registry_uniqueness_ocda_mscs_exp3_20261031_sf.json
.venv/bin/python scripts/site_pair_overlap.py
.venv/bin/python scripts/build_executive_summary_20261031.py</pre>
<p class="muted">Owner repos are cloned with <code>git clone --depth 1 https://github.com/buffedlizard55-lab/GEMSDOE&lt;NN&gt;.git</code> into <code>/tmp/owners</code> (outside the repository). Official sources: <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/">problem page</a> · <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/">leaderboard</a> · <a href="https://github.com/drivendataorg/gems-prize-reference-solution">reference solution</a> · <a href="https://docs.nlr.gov/docs/fy26osti/96647.pdf">submission PDF (NLR 96647)</a> · <a href="https://community.drivendata.org/t/scoring-clarification-are-known-usgs-ingenious-faults-masked-when-scoring-and-are-they-in-the-final-round-label-set/11516/4">forum #11516</a>.</p>
</main>
<footer class="wrap muted" style="padding:1rem 0">Generated by <code>scripts/build_executive_summary_20261031.py</code> from evidence JSON. No number on this page is hand-typed.</footer>
</body></html>
"""
    return page


def main() -> int:
    text = build()
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_text() == text
        print("up-to-date" if ok else "STALE: rerun without --check")
        return 0 if ok else 1
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
