# KANLERGEMSDOE1 — GEMS fault discovery research

**STOP: no raster is cleared for submission.** No unique, high-scoring TIFF or reliable leaderboard prediction has been established in this review. [Executive summary](docs/executive-summary.html) · [Submission guide](docs/how-to-submit.html) · [Latest review](docs/review-20261028.md) · [Independent artifact audit](docs/audit-20261028.md) · [Research slate](docs/research/hypotheses-20261026.md)

At the start of every session, read this README, [`docs/REQUEST_20261027.md`](docs/REQUEST_20261027.md), [`docs/evidence/current_run_card.json`](docs/evidence/current_run_card.json), and the latest linked review. Maximize P(Win): conserve slots when evidence is weak. Own the Outcome: report failed gates and missing data instead of manufacturing a result.

## Current findings

## 2026-10-28 Session (Lane H-K1-B GEOALIGN-UPFLOW + Nine-Site Executive Audit) — read first

> **STOP — still no raster cleared (`verdict: "negative"`, `0` slots spent).** New unique
> research artifact `KANLER1-UPFLOW-EXP2`
> (`docs/downloads/gemsdoe32-kanler1-upflow-exp2-37654d-20261028T163730Z-76525b8c-zeros.tif`,
> SHA-256 `4761c508790d…`, 37,654 dots, 15/15 format checks): ✅ OK TO DOWNLOAD for
> research · 🛑 NOT OK TO SUBMIT — best `HOLDOUT-DTI = 0.057717` [0.0497, 0.0648] vs
> champion `0.099202` (paired Δ −0.0415, P=0.0), SGMC-cal `0.0455` vs `0.0641`. All 3
> pre-registered experiments negative; 50/50 canaries pass; 29/29 discrete-detector
> uniqueness pass (14.19% vs GEMSDOE32). Run card: `evidence/run_card_upflow.json`.
> Repo best remains `OCDA-MSCS EXP-3` (`0.105830`, likewise on research hold).

**Standing session directives ( distilled from the standing project prompt; full
9-site score ledger lives in `docs/ORIGINAL_PROMPT_20261027.md`):** (1) every
submission TIF must be unique (lane rule: surface |ρ| ≤ 0.90 AND ≤70% dots within
3 px of any registry raster) and pass the automated 15-check validator — no human
inspector; (2) every number is labeled `HOLDOUT-DTI` (evaluator + N + CI) or
`ORGANIZER-CONFIRMED` — a projection is never a score, leaderboard estimates stay
`NOT ESTIMABLE`; (3) ≤3 experiments per lane, leakage canary per feature (AUC ≤ 0.90),
fold-local training only; (4) verify line-by-line from official sources with links,
no hallucinations, flag irregularities; (5) work in 3 passes, then PR + merge to
`main`. Core values: **Maximize P(Win)** (conserve weekly slots for calibrated,
selector-approved entries) and **Own the Outcome** (negative results are deliverables).

**This session delivered:** 9-site pixel-exact re-forensics
(`evidence/focus_forensics_20261028.json`, `knowledge/04_*`, `knowledge/05_*`);
Lane H-K1-B code (`src/kanler/upflow.py`, `scripts/run_upflow_lane.py`,
`scripts/audit_upflow_candidate.py`, `tests/test_upflow_lane.py`); the staged unique
artifact + run card; site updates (status, executive summary, hypotheses, research,
submission gate); review record `docs/review-record-20261028.md`; EXP-1-only v2
sampler sensitivity check (`scripts/run_upflow_v2check.py`,
`evidence/upflow_v2_sensitivity.json`: ΔHR −0.00034, conclusion stable).

---

* The nine-site comparison and artifact hashes are in the [generated readiness table](docs/submission-readiness.html). Historical scores are user/owner reports, **not organizer-confirmed receipts**, and cannot be used as estimates of a new file's score.
* GEMSDOE32's reported 0.2778 is the highest among the supplied nine-site champions. Prior audits found it has D2.8 support with a two-pixel catalogue collar removed. Fewer redundant predictions is a plausible explanation, not proof of causality or of a future improvement.
* The recorded lane has triggered the literal duplicate rule against the lattice registry raster. A complete peer inventory, surface and dot uniqueness, and a separate selector are prerequisites, not optional steps. No new candidate was generated in this review.
* A local writer check does not prove portal acceptance. The exact cause of the user's range error is unknown without the rejected TIFF and receipt. The reference notebook's output behavior does not prove what the portal accepts. The official rules/format and authenticated sample need reconciliation before promotion.
* Data restored from pinned third-party mirrors are not proof of organizer origin or license eligibility. Current sandbox restrictions block direct access to DrivenData, Dropbox and USGS. Training is not universally GPU-only; the [official reference repository](https://github.com/drivendataorg/gems-prize-reference-solution) describes CPU use too.
* The dated prior claims and experiment receipts are archival, not newly verified by this review. See [the archived README](docs/archive/readme-20261027.md) and [prior review](docs/review-20261027.md).

## Session-start checklist

Before further project work, reread [`docs/ORIGINAL_PROMPT.md`](docs/ORIGINAL_PROMPT.md), [`docs/ORIGINAL_PROMPT_20261027.md`](docs/ORIGINAL_PROMPT_20261027.md), the active lane/run card, and the latest review linked from the [executive summary](docs/executive-summary.html). Stay in the assigned single-method lane; reuse the shared cache/evaluator/writer; stop after at most three experiments or two hours; stop on surface correlation above 0.90 or more than 70% dot overlap within 3 px of any registered raster; label every score by evidence class; never present an estimate as a score; do not use a submission slot without the separate selector decision.

The [2026-10-28 requested-site scorecard](docs/focus-sites-review-20261028.html) transcribes the latest supplied scores for GEMSDOE24/25/27/28/30/31/32/33/36, labels them USER/OWNER-REPORT, records that valid site-specific estimates are unavailable, and authorizes **no download or submission**. Conflicting leaderboard values in the request (0.3195 and 0.4413) are not freshly confirmed.

## Verify locally

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/build_executive_summary.py --check
.venv/bin/python scripts/build_readiness_report.py --check
```

The test suite uses synthetic tests and stored evidence; passing it does not certify a scientific score, portal acceptance, or uniqueness against missing registry members.

## Standing operating requirements (reconstructed, not verbatim)

<details>
<summary><strong>Click to expand reconstructed operating requirements</strong></summary>

```text
PARALLEL-RUN PROTOCOL — read once, follow strictly:

1. LANE & UNIQUENESS. Stay inside your assigned method lane. Before placing final dots AND after placing them, check your continuous surface and final dots against every raster in the registry: if Spearman rank-correlation exceeds [0.90] OR more than [70%] of your dots fall within 3 px of any registry raster's dots, log as duplicate and stop — do not emit a submission file.
2. REUSE, DON'T REBUILD. Load the cached feature stack from the template and call evaluate_holdout.py and submission_writer.py directly. Holdout = hide-and-recover: withhold whole fault segments with a spatial buffer, derive every catalogue-based feature only from the remaining visible faults, mask visible faults pixel-exact as the organizer does, and score with exact pooled DTI (alpha=0.2, beta=0.8, 300 m triangular kernel). Fix shared tool bugs once in shared code; never keep a private fork.
3. STRICT SCORE LABELING. Every number you report must be labeled either HOLDOUT-DTI (with evaluator version, number of withheld positives, and 95% CI) or ORGANIZER-CONFIRMED (copied from a submission-page receipt). Never write a projection or forecast as a score.
4. LEAKAGE CANARY. Test each feature alone on the holdout before trusting any result. AUC above [0.90] means leakage until proven otherwise.
5. RUN CARD. End with one JSON card: hypothesis, mechanism, named non-fault mimic, holdout DTI + CI, correlation/overlap vs registry, raster sha256, validator output (no NaN inside footprint, values in [0,1], CRS/shape/transform match), submission name + note <=140 chars, and verdict (promote / negative).
6. BUDGET. Stop after at most 3 experiments or 2 hours. A negative result is a deliverable — log it so no other session repeats it. Promotion to a real weekly slot is a separate selector step.

Take a look at the GitHub repo and help build a complete end to end research, evaluation, validation, and submission system for https://www.drivendata.org/competitions/306/competition-doe-gems/

Check prior work from GEMSDOE24..GEMSDOE91, KANLERGEMSDOE1..3, EUGGEMSDOE1..3, WBGGEMSDOE1..3, GINNYGEMSDOE1..3 and any other GEMSDOE sites to review.
In particular, focus on the highest scoring submissions from these 9 sites:
GEMSDOE24, GEMSDOE25, GEMSDOE27, GEMSDOE28, GEMSDOE30, GEMSDOE31, GEMSDOE32, GEMSDOE33, GEMSDOE36

Check why this submission from GEMSDOE32 scored the highest among these sites:
h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros: 0.2778

See if it is possible to get a higher scoring submission (>0.2778 or even >0.3195). Right now the top score on the leaderboard is 0.4413 (or higher). Think deeply at a PhD level on how we can achieve a breakthrough here. Make sure there are no hallucinations. Work line by line to make sure we verify everything from official verified trusted sources, with links for manual review. If you find any irregularities, flag them.

Before implementing, generate 3-5 candidate geological hypotheses we haven't tried yet, each naming: the specific layer(s) involved, the physical signature being targeted (e.g., an edge-detection or curvature transform), why it should catch a fault missing from the USGS/INGENIOUS catalogue rather than one already in it, and how it differs from anything already implemented in this repo. Rank them by expected DTI improvement and implementation cost. Validate the top candidate on our spatially-blocked holdout set before touching a weekly submission slot, and flag any external data source we could pull in to test the others (noting whether it's freely available).

Check how we can build a unique single-band GeoTIFF (.tif) submission to be competitive with the top submissions on the leaderboard. Per competition rules, submissions must be a single-band GeoTIFF (.tif) — or a .zip containing a single GeoTIFF — matching the sample submission's CRS (EPSG:32611), shape, and geotransform, with predicted values in [0, 1]. Make sure we do not copy any previous submissions from GEMSDOE (use them to learn from only) and we must make a unique TIF submission unlike previous GEMSDOE submissions. Make sure it has a unique submission name and short note (<=140 chars) for tracking on the DrivenData portal. Make sure our submission is validated before making it available to download (do not require a human inspector since it should be validated automatically). We should also make sure it is obvious whether a generated TIF file is ok to download and submit.

Complete the data download and placement (`bash scripts/download_competition_data.sh` and `python scripts/prepare_data.py`), run the full evaluation pipeline to verify the actual out-of-fold score, and build the final submission file autonomously, without requiring any manual input.

Provide an executive summary subpage with a clear table showing what file to download, estimated score, and uniqueness across all sites. Also explain how to submit on the website, making sure we don't hit errors like "Predicted values must be in range [0, 1]".

Make sure that we keep the GitHub Pages site clean and intuitive to use (good UI/UX).

Store this prompt into the repo README.md for reference. Let's apply Arena Core Values to this problem, such as "Maximize P(Win)" and "Own the Outcome"

Let's work in multiple passes:
Pass 1: Implement and verify
Pass 2: Review and fix any bugs, assumptions, or edge cases
Pass 3: Re-check the entire implementation against the original request

After completing all passes, create a PR and merge it onto main. Note any next steps, recommendations, and limitations.
```

Earlier prompt archives are historical reconstructions; see [`docs/REQUEST_20261027.md`](docs/REQUEST_20261027.md).
</details>
