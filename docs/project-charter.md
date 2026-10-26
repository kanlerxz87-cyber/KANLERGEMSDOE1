# Project charter — GEMS fault-mapping research

**Read this file at the beginning of every project session together with the repository README.** This document is the durable, actionable version of the user's long brief. Repeated instructions have been consolidated; dated score claims remain historical claims, not verified truth.

## North star

Build a scientifically defensible, reproducible, low-friction system for the DOE GEMS competition that can generate a valid GeoTIFF only after it passes the required technical, leakage, spatial holdout, and uniqueness gates. The goal is to improve the chance of a strong competition result, not to manufacture a score, copy a prior file, or fill a weekly slot. The prediction target is **geological faults**; geothermal vents/systems motivate the application but are not the pixel label.

The user wants:

- A clean GitHub Pages site with a clear executive summary at the top, an explanation of the best evidence, a per-site table for GEMSDOE24, 25, 27, 28, 30, 31, 32, 33, and 36, and a subpage explaining the DrivenData submission process.
- Each table row to identify a file, distinguish historical score claims from holdout measurements, state whether uniqueness is demonstrated, and say plainly whether the file may be downloaded and submitted.
- A unique, valid single-band GeoTIFF for competition submission, but only when the file is original and all gates pass. Never copy a previous submission as a new one.
- A current, source-linked view of competition information, careful scientific research, auditable hypotheses, limitations, and irregularities.
- A ranked slate of 3–5 previously untested hypotheses before implementation, with the exact layers, proposed physical signature, rationale for finding faults absent from the catalogue, differences from known work, costs, and official data sources where required.
- Three deliberate review passes: implement, audit for errors and omissions, then re-check against the whole brief.
- Work consistent with Arena's core values: **Maximize P(Win)** and **Own the Outcome**.

## Parallel-run protocol — hard stop conditions

1. **Lane:** one experimental lane must be named by one method paragraph. The supplied instructions mention a method paragraph, but no single method paragraph is present in this checkout. Do not silently choose a lane or combine concurrent lanes. Until a lane is specified, no hypothesis is treated as the experiment to run.
2. **Reuse, don't rebuild:** use the shared template's cached feature stack, `evaluate_holdout.py`, and `submission_writer.py`. A shared defect is fixed once in the template; do not maintain a private fork. None of those files is present in this repository.
3. **Holdout:** hide and recover whole fault segments with a buffer; calculate catalogue-derived features only from visible faults; mask visible faults pixel-exactly; score pooled DTI with alpha 0.2, beta 0.8, and a 300 m triangular kernel. Use the common evaluator/version.
4. **Leakage canary:** test every feature alone on the holdout before trusting it. AUC above 0.90 is a stop until leakage is disproved.
5. **Uniqueness:** compare both the surface before placement and final dots against every available registry raster. Absolute rank-correlation above 0.90, or more than 70% of dots within 3 pixels of a single registry raster, is a duplicate-lane stop.
6. **Budget:** stop after three experiments or two hours. Do not pick a submission or spend a competition slot; promotion is a separate selector step under the cap actually shown on the competition submission page.
7. **Evidence labels:** label a score only as `HOLDOUT-DTI` (include evaluator version, withheld-positive count, and 95% CI) or `ORGANIZER-CONFIRMED` only when copied from the matching organizer submission receipt. Do not present a model projection as a score. If a historical number is repeated for provenance, label it `OWNER-REPORTED / UNVERIFIED` and do not rank it as verified evidence.
8. **Run card:** end every experiment report with one machine-readable card containing hypothesis, mechanism, a named non-fault mimic, holdout DTI/CI, registry correlation and overlap, TIFF SHA-256, validator output (NaN inside footprint, `[0,1]` range, CRS/shape/transform), submission name/note (note ≤140 characters), and `promote` or `negative` verdict. A blocked/non-run card must explicitly use null or `not run`, never fabricated results.

## Competition facts to keep stable

The official problem page describes a fault-mapping task with potentially incomplete/inaccurate public fault labels and a hidden test set of expert-identified faults. It describes the distance-weighted Tversky metric with alpha 0.2, beta 0.8, and a triangular kernel supported to 300 m (three 100 m pixels). The stated submission is one `float32` GeoTIFF band on the training grid, in EPSG:32611, with matching bounds/resolution and null/NaN outside the valid bounds; in-footprint predictions are in `[0,1]`. Always verify against the current official page and downloaded sample template before submission.

The competition data download page redirects to login in this environment. Do not claim that files have been downloaded or that the training pipeline is ready. The current checkout has no `data/` directory, sample submission, feature stack, labels, DEM-link file, evaluator, or writer.

## Dated claims and evidence policy

As of the 2026-10-26 web review:

- The live official public leaderboard page showed 0.4437 at rank 1. This supersedes the prompt's older 0.3195 and 0.4413 snapshots as a **current public-page observation**, but is not a score for this project and is not a submission receipt.
- GEMSDOE32's H33-B2 value 0.2778 is reported in the linked GEMSDOE pages as `OWNER-REPORTED`; the page says there is no submission-page receipt tying that value to the exact raster hash. Do not label it organizer-confirmed.
- A public cross-site owner audit describes the B2 raster as a pruned subset of the D2.8/H19-5 lineage. This is a source-reported lineage finding; its rasters and hashes were not independently loaded in this checkout. It is enough to block a claim that B2 is a new, unique candidate here.
- A GEMSDOE25 page reports a conflicting GEMSDOE36 historical value (0.2683 in one ledger versus 0.2750 in the focus-site summary). Keep the conflict visible; do not resolve it by guesswork.
- Source-site gate decisions are not equivalent to this project's selector decision: different repositories report different evaluators, registries, masks, and even conflicting promotion statuses. No external site's `OK TO SUBMIT` banner transfers to this repository.
- No calibrated mapping from catalogue holdout DTI to the organizer's public/private test score has been established. A leaderboard estimate is therefore `Not estimable`, not a guessed decimal.

The source-by-source review and nine-site table are in [`executive-summary.html`](executive-summary.html); source URLs and access status are in [`sources.html`](sources.html) and [`data/site-audit.json`](data/site-audit.json). A scheduled GitHub Pages workflow refreshes a public-page availability/fingerprint feed daily after deployment; it intentionally does not scrape scores, infer approval, or access login-gated data. That hosted workflow has not yet run from `main` in this session.

## Ranked candidate slate (proposals, not results)

The repository itself has no implementation, so these are new relative to this checkout. Whether they are globally new across all GEMSDOE repositories is **not established**; broad prior-art text on the source pages is not a complete machine-verified archive. No experiment has been run. The detailed table is in [`hypotheses.html`](hypotheses.html).

1. **Conductive-base step geometry × geodetic dilation:** competition layers `depth to conductive base surface`, surface conductivity, dilatation/shear strain/second strain invariant. Look for persistent discontinuities and structural step-overs supported by local dilation. Plausible blind-fault signal; lithologic contacts, clay alteration, and saturated basin fill can mimic it. Moderate cost.
2. **Effort-adjusted shallow-temperature residual × strain:** official INGENIOUS 2-m temperature probe observations plus competition strain layers. Remove elevation/season/sampling-effort structure first; test for localized thermal residuals aligned with deformation. Could expose hidden fluid pathways; soil moisture, aspect/solar forcing, shallow groundwater, and measurement effort can mimic it. High cost; external data retrieval and metadata validation required.
3. **Potential-field source-depth edge persistence × gravity-edge concordance:** top-of-crustal magnetic source-depth estimate, magnetic anomaly gradients, isostatic gravity and its slope. Persistent, cross-physics edges may reveal buried basement offsets. Intrusions and lithologic contacts can mimic faults. Moderate cost; prior-art overlap risk is high because source sites already discuss potential-field/dipole/pseudogravity methods.
4. **Earthquake-density anisotropy × strain-gradient interaction:** earthquake-density layer with shear strain, dilation, and second invariant. Test orientation/persistence of seismic-density gradients where the public fault catalogue has no trace. Swarms, network completeness, and anthropogenic seismicity can mimic the signal. Low-to-moderate cost; prior-art overlap risk is high.

Qualitative rank is a research-priority judgment, **not a DTI or leaderboard score**. None can be validated until the lane, labels, features, shared evaluator, and registry are available. The 2-m probe dataset is listed as publicly downloadable on DOE GDR submission 1391 under CC BY 4.0; this sandbox confirmed the listing and license, not a successful file transfer.

## Session-start verification checklist

At each future session, before modeling:

1. Read this charter and README; verify current date, branch, `git status`, and upstream sources.
2. Inventory the shared template and data. Confirm `training_features.tif`, labels, `sample_submission.tif`, `1m_DEM_links.csv`, the shared evaluator, and the shared writer by path and hash. If absent, stop model work.
3. Confirm the exact lane and run budget. If missing, stop experiments and preserve the negative/blocker result.
4. Refresh official problem/rules/leaderboard/data-page snapshots and keep official facts separate from user-site claims.
5. Freeze the holdout protocol, leakage canaries, registry snapshot, and pre-registration before evaluation.
6. Run at most the allowed experiments; publish failed results and do not select a slot.
7. Validate the saved TIFF, not only an in-memory array. Attach byte SHA-256 and the complete run card.
8. Make the landing-page verdict impossible to misread: `OK TO DOWNLOAD` and `OK TO SUBMIT` are separate flags.

## Current blockers in this checkout

- Only `README.md` was tracked before this documentation work.
- No cached features/labels/template, no shared holdout evaluator or writer, and no registry rasters are present.
- The claimed `scripts/download_competition_data.sh` and `scripts/prepare_data.py` are absent, as are the `scripts/` directory and all expected inputs (`training_features.tif`, labels, sample submission, and `1m_DEM_links.csv`).
- The competition data page redirects to login; no authenticated data or submission receipt is available here. The Dropbox links in the brief were not fetched, and no data attachments are present in this checkout.
- Python 3.11 is available, but `numpy`, `rasterio`, `torch`, and `pytest` are missing; GPU availability was not established. The current static-site tests use only the Python standard library.
- No single experimental lane paragraph was supplied.
- No candidate TIF can be safely generated, format-checked, compared for uniqueness, scored on holdout, or approved. **Current verdict: negative / blocked; no file to download or submit.**
