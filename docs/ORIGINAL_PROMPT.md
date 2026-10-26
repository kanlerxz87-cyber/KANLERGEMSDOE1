# Standing Arena prompt (archive)

Read this at the start of every session. The live user message may add scores; the rules below do not expire.

## Goal

Place on the DrivenData DOE GEMS Prize leaderboard (competition 306) with a **unique** single-band float32 GeoTIFF that matches the official submission contract. Maximize P(Win). Own the Outcome.

Competition: https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/

## Parallel-run protocol (mandatory)

1. **LANE.** Stay inside the assigned method. If rank-correlation with any registry raster exceeds 0.90, or more than 70% of dots fall within 3 px of one genuine registry raster, log a duplicate and stop.
2. **REUSE, DON'T REBUILD.** Use the template cached feature stack, `evaluate_holdout.py` and `submission_writer.py`. Holdout = hide-and-recover: withhold whole fault segments with a buffer, derive catalogue features only from visible faults, mask visible faults pixel-exactly, score pooled DTI (α 0.2, β 0.8, 300 m triangular kernel). Fix shared tools in the template once; never keep a private fork.
3. **LABEL EVERY NUMBER** as HOLDOUT-DTI (evaluator version, n withheld positives, 95% CI) or ORGANIZER-CONFIRMED (copied from a submission-page receipt). A projection is never written as a score.
4. **LEAKAGE CANARY.** Test each feature alone on the holdout before trusting any result. AUC above 0.90 means leakage until proven otherwise.
5. **RUN CARD.** End with one JSON card: hypothesis; mechanism; named non-fault process that could mimic it; holdout DTI + CI; correlation/overlap vs registry; raster sha256; validator output (no NaN inside footprint, values in [0,1], CRS/shape/transform match); submission name + note ≤140 characters; verdict promote / negative. Negative results are deliverables.
6. **BUDGET.** Stop after 3 experiments or 2 hours. Do not pick submissions: promotion to a real slot is a separate selector step.

## Submission contract (official)

- Single-band GeoTIFF, EPSG:32611, 100 m, same grid as `sample_submission.tif` (3730 × 3292, origin 243350, 4508550).
- float32 values in **[0, 1]**. NaN or nodata sentinels inside the scored grid cause `Predicted values must be in range [0, 1]`.
- Prefer a zeros-outside-footprint variant (`nodata=None`) for portal upload.
- Unique name + short note.

## Scientific constraint

Known USGS/INGENIOUS faults are masked from scoring. The task is **hidden-fault discovery**, not catalogue reproduction. GEMSDOE32 h33-2-b2 OWNER-REPORT 0.2778 is D2.8 Poisson of H19-5 plus a 2 px catalogue collar — metric geometry, not a license to duplicate that raster.

## Site

GitHub Pages must make it **obvious** whether a file is OK to download and submit. Executive summary table: file, HOLDOUT-DTI (not a fake live estimate), uniqueness vs listed GEMSDOE sites, submit yes/no.

## Data

DrivenData data tab is login-walled. Restore hash-pinned mirrors with `scripts/restore_data.py`. Pins are not organizer authentication.
