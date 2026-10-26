# Three-pass review log

**Review date:** 2026-10-26 UTC
**Branch:** `arena/392fa676-kanlergemsdoe1`
**Scope:** this checkout and the public sources linked from the user brief. No authenticated competition files or external site TIFF bytes were downloaded.

## Pass 1 — implement the auditable project surface

- Inspected the initial repository: only a one-line `README.md` was tracked.
- Added a session-start README and a durable project charter that preserve the goals, Core Values, lane/budget/holdout/leakage/uniqueness rules, evidence labels, file requirements, and blockers.
- Added a static GitHub Pages desk with a conspicuous fail-closed landing state; a nine-site historical table; a submission guide; four ranked, falsifiable hypotheses; official/owner-source separation; and machine-readable audit/run-card JSON.
- Added a daily public-page availability feed design. It records status, title, final URL, and a content fingerprint only; it does not scrape scores, download gated files, or infer submission approval.
- Added a GitHub Pages deployment workflow and ignored local data/cache outputs.

**Pass-1 outcome:** documentation and site built; no scientific candidate or TIFF was generated because required shared assets and the active lane are absent.

## Pass 2 — adversarial evidence and implementation review

- Re-fetched the official competition problem, about, data, leaderboard, official rules PDF, reference repository, USGS GeoDAWN page, DOE GDR 1391 page, GBCGE INGENIOUS page, and EPSG reference.
- Confirmed the competition data URL resolves to a login page in this environment. Confirmed the current public leaderboard snapshot is 0.4437, not the user's earlier 0.3195/0.4413 snapshots; neither value is a score for this repository.
- Re-read the nine public site pages and their cross-site owner audit. Kept their historic values as `OWNER-REPORTED / UNVERIFIED`, made per-site leaderboard estimates `Not estimable`, and labeled uniqueness as not established. Flagged the unresolved GEMSDOE36 0.2683/0.2750 source conflict and inconsistent site-local selector scopes.
- Added official/peer-reviewed method context: the USGS Great Basin structural-discontinuity study, USGS potential-field/spring example, GDR shallow-temperature method caveat, USGS 3DEP fault-mapping example, and the Mattéo et al. fault-mapping paper. These inform mechanisms and confounders; none is treated as holdout evidence.
- Revised the H33-B2 explanation to separate a plausible metric mechanism (pruning redundant predictions can reduce additive FP mass) from unproven causation. The exact 0.2778 score-to-file association is not backed by a receipt on the fetched GEMSDOE32 page.
- Added mocked tests for the public-feed script so login redirects and network failures are represented without treating them as available data; removed third-party font loading.

**Pass-2 outcome:** source/evidence labels made more conservative; external approval banners are not adopted; feed cannot report a score or authorize a slot.

## Pass 3 — full requirements and smoke-test check

- Verified every local HTML/asset/JSON link, the exact nine-site set and historical-claim strings, the blocked run-card fields, and the landing-page `DO NOT SUBMIT` language.
- Verified the public-feed script with mocked pages and a mocked login redirect; verified JavaScript syntax and parsed every JSON artifact.
- Served the static site locally and confirmed HTTP 200 for the overview, executive summary, how-to-submit page, and source-status JSON.
- `git diff --check` passed. The test suite passed **12/12** tests after feed input validation was added.
- Confirmed that no `.tif`/`.tiff` exists in this checkout and the run card has null holdout values, null registry measurements, no TIFF hash, and `verdict: negative`.

**Pass-3 outcome:** the repository now satisfies the evidence/reporting/site requirements that can be completed without competition inputs. It does **not** satisfy the requested unique-TIFF-generation or high-score validation requirement; presenting a file or score now would be fabricated or borrowed. No competition slot was selected or spent.

## Remaining blockers and exact next work

1. The user/authorized participant must download the competition's official package through the logged-in DrivenData data page and place the required data in the project data folder. Do not share credentials in chat. The supplied Dropbox artifacts were not available in this checkout and were not fetched.
2. Restore the shared template (cached features, `evaluate_holdout.py`, `submission_writer.py`, exact sample grid, fold/registry metadata). The prompt mentions `scripts/download_competition_data.sh` and `scripts/prepare_data.py`, but neither exists in this clone.
3. Name the single active method paragraph/lane. Until then, the candidate slate is not an experiment order.
4. Install and verify the project GIS/ML environment (`numpy`, `rasterio`, `torch` were absent in this runtime); check actual GPU availability. This review made no training run.
5. Before any slot decision, freeze the lane, leak-canary protocol, buffered whole-segment holdout, registry snapshot, and evaluator. Validate candidate surface and final dots; produce a new-byte hash and complete run card.
6. Enable GitHub Pages/Actions on the repository's default branch. The scheduled feed workflow is configured but has not yet run from `main`; its first live-source snapshot is pending. It only monitors public-page availability and fingerprints; it does not refresh score claims.

**Final decision:** negative / blocked. No unique submission TIF is available to download or submit from this repository.
