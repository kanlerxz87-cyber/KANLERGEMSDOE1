# KANLERGEMSDOE1 — GEMS research and submission gate

> **Standing instruction — read this README before every project session.** This is the durable project brief and the release policy. Keep the work auditable, scientific, and conservative: maximize the probability of a defensible result; own the outcome end to end.

## Current decision: no submission is cleared

**DO NOT DOWNLOAD OR SUBMIT A TIFF from this repository.** There is no generated candidate TIFF here, no compliant holdout run, no local template, and no verified submission receipt. The website therefore has no enabled download button. Historical rasters from other GEMSDOE sites are evidence for review, not new submissions.

This checkout began with only this README. In particular, it does **not** contain `data/`, `scripts/download_competition_data.sh`, `scripts/prepare_data.py`, `evaluate_holdout.py`, `submission_writer.py`, a cached feature stack, `sample_submission.tif`, or the registry rasters needed for the requested checks. The official reference-solution repository is a separate project; its README says competition data must be downloaded from the competition site and placed in `data/`. This checkout cannot run that pipeline by assumption or by copying a sibling site's code.

The conversation's parallel-run protocol also requires a single, explicit method paragraph (“lane”), but the request does not unambiguously designate one. Do not guess the lane. No experiment was run in this session. The candidate slate on the site is research-only and is **not** a submission authorization.

## Standing project brief

The goal is to build a useful, reproducible project for discovering geothermal-vent-related faults and producing a valid, unique single-band GeoTIFF for the DOE GEMS Prize challenge. Make the “OK TO DOWNLOAD AND SUBMIT” decision unmistakable at the very top of the site. Never show a historical or experimental artifact as ready to submit.

### Non-negotiable research and release protocol

1. **One lane only.** Use only the method paragraph explicitly selected for the run. Before and after dot placement, check the candidate's continuous surface against every registry raster; stop and record a duplicate if absolute rank correlation is above `0.90` or more than `70%` of candidate dots are within three raster pixels of a registry raster's dots.
2. **Reuse the shared template.** Use its cached feature stack, shared `evaluate_holdout.py`, and shared `submission_writer.py`. Do not make a private duplicate of shared scientific tools. If a shared tool is wrong, fix it in its owning template and document the change. None of these tools is present in this checkout yet.
3. **Spatial holdout only.** Hide whole fault segments with a buffer; derive every catalogue-dependent feature only from visible faults; mask visible faults pixel-exactly; pool the prescribed Distance-Weighted Tversky Index (DTI) with the competition's stated weights and distance kernel. A fold must rebuild all catalogue-based preprocessing from its visible faults. Do not use full-label geometry before the holdout.
4. **Leakage canary.** Evaluate each feature alone on the same holdout before trusting it. AUC above `0.90` is a leakage warning until explained.
5. **Honest numbers.** A score may be reported only as `HOLDOUT-DTI` with evaluator version, withheld-positive count, and a 95% confidence interval, or as `ORGANIZER-CONFIRMED` copied from a saved submission-page receipt tied to the exact raster bytes. A projection is never a score. The historical values in the request are not treated as organizer-confirmed in this checkout because no receipt tying their exact bytes to those values is available here.
6. **Run card.** End every experiment with one JSON card containing the hypothesis, mechanism, named non-fault mimic, holdout DTI and CI, registry correlation/overlap, raster SHA-256, validator output, submission name and a note of at most 140 characters, and a `promote` or `negative` verdict. Negative results are deliverables.
7. **Budget and selector.** Stop after three experiments or two hours, whichever comes first. Do not pick a real submission slot in the research lane. A separate selector must authorize promotion within the competition's current weekly cap.
8. **Valid output.** Before any release, validate the written GeoTIFF against the official sample template: single band; expected CRS, shape, and geotransform; predictions in `[0, 1]`; no NaN inside the scoring footprint; and all other official format rules. Local validation is not organizer acceptance.
9. **Unique bytes and science.** Do not copy a previous submission as a new entry. Check both the surface and final output against the complete registry. Preserve the exact raster hash and the validator/run-card evidence.
10. **No fabricated feed or access.** Do not claim a live leaderboard, score, or official data retrieval unless it was actually checked. The competition data page requires authentication per the information supplied in the request; no DrivenData credentials or submission-page receipt are available in this checkout.

### Core values

- **Maximize P(Win):** choose the next step by expected scientific value, leakage risk, cost, and submission-slot risk—not by enthusiasm or an unverified score.
- **Own the Outcome:** follow a failure through to its cause, document it, and improve the shared source of truth rather than hiding it in a private fork.

## What this session delivered

- A GitHub Pages landing page with a prominent **not cleared** status and no misleading TIFF download.
- A nine-site executive summary that names the historical file IDs from the supplied record, reports no score estimate where the evidence standard is unmet, and flags the prior-file uniqueness concern.
- Three new, research-only geological hypotheses with named layers, physical signatures, confounds, candidate official data sources, and explicit availability blockers.
- A negative run card. It records that no experiment, holdout, raster comparison, or output validation could be performed in this starter checkout.

The site's historical uniqueness notes are attributed to a separate GEMSDOE32 repository report and have **not** been recomputed from raster bytes in this repository. That report itself says the historic score values are not linked to organizer receipts. See the source register for provenance and caveats.

## Read next

- [Executive summary and nine-site table](executive-summary.html)
- [Candidate hypotheses and blockers](hypotheses.html)
- [Source register and access status](sources.html)
- [Current negative run card](data/run-card.json)
- [Three-pass review record](docs/review-record.md)
- [Live GitHub Pages site](https://kanlerxz87-cyber.github.io/KANLERGEMSDOE1/)

## Submission instructions (only after a future `promote` decision)

1. Confirm the site's top banner says **OK TO DOWNLOAD AND SUBMIT** and that a fresh TIFF link, exact SHA-256, passing run card, holdout evidence, registry uniqueness results, and strict validator output are all present. If the banner says anything else, do not upload.
2. On the official competition page, open the submission flow and select the one-band GeoTIFF. Add a unique submission name and a short note (maximum 140 characters in this project's run-card convention). Check the current weekly cap and competition rules.
3. Save the submission-page receipt and bind it to the exact submitted file hash. Only then can its result be called `ORGANIZER-CONFIRMED`.

This repository cannot log in to DrivenData, choose a weekly slot, or submit a file automatically. The upload step requires a competition account. The project should automate scientific and file-format preflight; it must not pretend to automate organizer-side acceptance.

## Limitations and blockers

- Competition features, labels, sample template, and full registry rasters are absent from this checkout.
- The expected shared holdout evaluator and writer are absent; rebuilding them privately would violate the request's reuse rule.
- DrivenData, USGS, NASA, OpenEI, NLR, and EPSG pages and scientific-literature sources were not fetched in this session. The execution environment only permits outbound access to GitHub and package registries. Links on the source page are provided for review, with verification status stated explicitly; candidate mechanisms are hypotheses, not literature conclusions.
- The current checkout has no Python geospatial stack installed (`numpy`, `rasterio`, `scipy`, and `scikit-learn` were unavailable at review time). No raster analysis was attempted.
- The prompt contains conflicting, undated statements about the public leaderboard. No live value is repeated here or used as a target.

## Local checks

The Pages site is static and uses no JavaScript or third-party runtime. Run the repository safety checks with:

```bash
python -m unittest discover -s tests -v
```

The tests verify the not-cleared release banner, presence of all nine site rows, the negative run-card status, and that the site does not link directly to a prior TIFF. They are website-safety checks, **not** scientific validation.
