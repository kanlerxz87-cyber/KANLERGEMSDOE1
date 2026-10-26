# KANLERGEMSDOE1 — evidence-first GEMS research

> **Session-start rule:** read this README and [`docs/project-charter.md`](docs/project-charter.md) before every project session. Treat historical site scores as claims until tied to an organizer receipt. Never let a download link, a clean GeoTIFF, or an attractive holdout result alone authorize a competition upload.

## Current decision — 2026-10-26

**No competition-ready TIFF exists in this checkout. Do not upload or submit a file from this repository.** Before this documentation work, the checkout contained only a one-line README. There is no competition data, cached feature stack, shared holdout evaluator, submission writer, template, registry raster set, candidate raster, or run receipt. The claimed `scripts/download_competition_data.sh` and `scripts/prepare_data.py` are also absent. The DrivenData data page redirects to login. Creating a random/borrowed TIFF would be neither a valid experiment nor a defensible unique submission, so none was fabricated. Python's GIS/modeling dependencies (`numpy`, `rasterio`, `torch`) are not installed in this environment.

The best historical claim among the nine requested sites is GEMSDOE32 H33-B2 at **0.2778 (OWNER-REPORTED; not ORGANIZER-CONFIRMED)**. Its own source material says it is derived as a pruned subset of the older D2.8 pattern; the strict cross-registry uniqueness gate is therefore not established and the artifact must not be copied or re-uploaded. This is a learning benchmark, not an approved file. A live check of the official public leaderboard on 2026-10-26 showed a leading public value of **0.4437**; the prompt's 0.3195 / 0.4413 figures are stale snapshots, not a forecast for this project.

## Start here

- [Executive summary and nine-site comparison](docs/executive-summary.html)
- [Submission guide and automated gates](docs/how-to-submit.html)
- [Ranked research hypotheses](docs/hypotheses.html)
- [Sources, scope, and irregularities](docs/sources.html) (includes a daily public-page availability feed; it deliberately does not scrape scores or authorize submissions)
- [Machine-readable audit](docs/data/site-audit.json)
- [Required run card](docs/data/run-card.json)
- [Three-pass review log and remaining blockers](docs/review-passes.md)

## Non-negotiable project rules

1. **Stay in the selected experimental lane.** The supplied parallel-run protocol requires one specific method paragraph, but this checkout/request does not identify one. Until a lane and the shared template assets are available, do not run or promote an experiment.
2. **Reuse the shared stack.** Use the template's cached features, `evaluate_holdout.py`, and `submission_writer.py`; fix shared defects in the template, not in a private fork. None of these assets is present here.
3. **Do not claim a leaderboard forecast from a proxy.** Every future result must be identified as either `HOLDOUT-DTI` (evaluator version, withheld-positive count, and 95% CI) or an organizer result with its submission-page receipt. A holdout or model projection is not an organizer score.
4. **No leakage or duplicate drift.** Run each feature-only leakage canary before use; AUC > 0.90 is a stop until leakage is ruled out. Compare both the pre-placement surface and final dots against the full registry; stop if absolute rank correlation > 0.90 or >70% of candidate dots are within 3 px of a single registry raster.
5. **Holdout is hide-and-recover.** Withhold whole fault segments plus a buffer; derive catalogue-based features only from visible faults; mask visible faults pixel-exactly; evaluate pooled DTI with alpha 0.2, beta 0.8, and the 300 m triangular kernel. Use the shared evaluator.
6. **Format is necessary, not sufficient.** Match the official sample template's one-band `float32` grid, EPSG:32611 CRS, bounds, resolution, and transform. Validate every in-footprint value is finite and in `[0,1]`; outside-footprint cells must follow the official null/NaN specification. Do not infer portal acceptance from local validation.
7. **Never copy, rename, jitter, or relabel an old submission as unique.** A research-only TIF is not approved for upload. Keep the download/submit decision explicit and fail closed.
8. **Stop at three experiments or two hours.** Do not select or spend a competition slot here; promotion is a separate selector decision under the live competition cap.
9. **Preserve provenance.** Record source URL, observation date, file hash, evaluator version, withheld count, confidence interval, uniqueness measurements, validator output, submission name/note, and verdict.

## Values

- **Maximize P(Win):** prefer evidence that improves the odds over activity, attractive maps, or uncalibrated score projections.
- **Own the Outcome:** surface blockers and contradictory evidence; publish negative results; keep the site explicit about what is and is not approved.

The full actionable brief, source inventory, and current blockers are in [`docs/project-charter.md`](docs/project-charter.md). The static GitHub Pages site is in `docs/`.
