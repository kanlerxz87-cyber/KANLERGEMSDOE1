# Standing project brief and protocol — refreshed 2026-10-27 UTC

**Read this file and `README.md` before every project session.** This is an organized, operational restatement of the long user brief supplied on 2026-10-27, not a byte-for-byte transcript. It preserves the requirements that govern future work; later user instructions may amend it. Core values: **Maximize P(Win)** and **Own the Outcome**.

## Mission and required product

Build an auditable, easy-to-use research and submission workflow for the DOE GEMS fault-mapping competition. The objective is high leaderboard performance, but a candidate must be scientifically tested, unique under the stated registry rule, technically valid, and separately selected before it is offered as a contest download. The Pages landing page and executive summary must make the download/submit decision unmistakable. Keep a current-information feed, citations to official or appropriately licensed sources, a ranked research slate, and an automatic upload guide. Do not require a human to perform project-side validation. Do not claim portal acceptance without a submission-page receipt.

Explain the reported 0.2778 GEMSDOE32 result with testable reasoning and clearly separate observed raster geometry from causal claims. Do not promise to beat it or estimate a private score from public reports. A valid score is either:

- **HOLDOUT-DTI:** exact pooled evaluator result, with evaluator version, withheld-positive count and 95% CI; or
- **ORGANIZER-CONFIRMED:** copied from an actual organizer submission-page receipt.

Historical public scores supplied by the user, or stated without a receipt tied to exact bytes, are **USER/OWNER-REPORTS**, not verified scores or a model's expected score.

## Focus sites and reported historical maxima

The following are the highest results quoted in the user's brief for these nine sites. They are reference points only; values are user/owner reports with no submission-page receipts. See [`registry/focus_sites.json`](../registry/focus_sites.json), the [generated readiness table](submission-readiness.html), and its [CSV](evidence/submission_readiness.csv) for pinned file names, hashes, and pairwise support audit.

| Site | Highest supplied report | Interpretation |
|---|---:|---|
| GEMSDOE24 | 0.2477 | Historical report; not a current estimate |
| GEMSDOE25 | 0.2600 | Historical report; not a current estimate |
| GEMSDOE27 | 0.2449 | Historical report; not a current estimate |
| GEMSDOE28 | 0.2710 | Historical report; not a current estimate |
| GEMSDOE30 | 0.2600 | Historical report; not a current estimate |
| GEMSDOE31 | 0.2708 | Historical report; not a current estimate |
| GEMSDOE32 | 0.2778 | Highest of these nine reports; not a receipt or submit recommendation |
| GEMSDOE33 | 0.2632 | Historical report; not a current estimate |
| GEMSDOE36 | 0.2750 | Historical report; not a current estimate |

The brief also states current/high scores of 0.3195 and 0.4413 at different points; the repository holds a separate 0.4437 public-board snapshot dated 2026-10-26. These values conflict in date and scope. Unless the public board is freshly fetched and timestamped, the current leader is **unknown**. Never treat a public leaderboard row as a receipt for a repository TIFF.

## Scientific research and experiment selection

Before implementing a new method, propose 3–5 differentiated geological hypotheses. For each, name (1) the exact layers, (2) the physical signal or transform, (3) why it could reveal catalogue-missing faults rather than re-detect mapped faults, (4) how it differs from code and prior submissions actually inspected, (5) a non-fault process that could mimic it, (6) expected benefit and implementation cost, and (7) official free/licensed data needed and whether it is obtainable. Mark qualitative rankings as judgment, never as DTI estimates. If required data are unavailable or rights cannot be checked, the idea is not ready to run.

Use a predeclared spatially blocked, whole-segment hide-and-recover test before any real submission slot. Reuse the shared cached feature stack and shared `scripts/evaluate_holdout.py` / `scripts/submission_writer.py`; fix shared tools once, not in a private fork. No new experiment is allowed when the assigned lane has stopped or its budget is exhausted. Negative results are valid deliverables.

## Mandatory parallel-run protocol

1. **Single lane and uniqueness.** Stay in the assigned method lane. Before placement compare the continuous candidate surface and preregistered preview support against every registry raster. Repeat after final placement. If absolute rank correlation with any reference exceeds 0.90, or more than 70% of candidate dots lie within 3 pixels of any one reference, record a duplicate and STOP. No lattice, density, sparse, or calibration exemption is authorized. Missing inventory, undefined results, missing surface evidence, or a failure is not a pass.
2. **Leakage-safe holdout.** Withhold whole fault segments with a spatial buffer. Derive every catalogue-based feature, collar, preview-support gate and emission from visible faults only for that fold. Mask visible faults pixel-exactly. Score pooled distance-weighted Tversky (DTI), α=0.2, β=0.8, with a 300 m triangular kernel. A per-cell prediction file is not proof that features were constructed fold-locally.
3. **Leakage canaries.** Test each feature alone on withheld folds before trusting it. Symmetric AUC above 0.90 is leakage until disproven; failed or missing canaries stop the lane.
4. **One run card.** End an experiment/audit with one JSON card: hypothesis, mechanism, named non-fault mimic, HOLDOUT-DTI and 95% CI or why unavailable, evaluator/count, registry correlations and overlap with scope, raster SHA-256, validator output (no NaN in footprint, values in [0,1], CRS/shape/transform match), submission name and note ≤140 characters, and promote/negative verdict.
5. **Budget/selector.** At most three experiments or two hours for a lane. Do not spend a weekly submission slot or choose a real slot here. A separate selector acts only after scientific, uniqueness, provenance, and format gates; use the actual authenticated platform quota.
6. **No copying.** Do not copy a previous submission as a candidate. Existing rasters may be used only for learning, audit, or comparison, and must never be presented as an approved new submission.

## Submission format, UX, and prior rejection

The user needs a single-band GeoTIFF matching the official template's CRS, shape and geotransform; prediction values must be in [0,1]. Validate the exact data footprint, NaN/Inf/nodata rules from the current official instructions, and pixel-exact known-label exclusion. Reject invalid data rather than clipping or silently repairing it. Use a distinct experiment name and a portal note no longer than 140 characters. Stage artifacts safely and roll back on failure. Local validation is not organizer acceptance.

The prior portal error was: `Predicted values must be in range [0, 1]`. Do not claim a cause or a fix without the exact rejected bytes and organizer response. The site must clearly show **NONE / DO NOT SUBMIT** when no file passes; never leave historical TIFFs looking like live downloads. Only a selected, fully passing artifact may get a contest-download link.

## Sources supplied for manual review

These URLs were supplied in the user brief. Their inclusion here is a reference list, not a claim that each page or current rule was reachable during every session.

- [DrivenData competition](https://www.drivendata.org/competitions/306/competition-doe-gems/) · [problem/format](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/) · [about](https://www.drivendata.org/competitions/306/competition-doe-gems/page/968/) · [data tab (login required)](https://www.drivendata.org/competitions/306/competition-doe-gems/data/) · [public leaderboard](https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/).
- [Official reference solution](https://github.com/drivendataorg/gems-prize-reference-solution) · [2026 rules PDF](https://docs.nlr.gov/docs/fy26osti/96647.pdf).
- [USGS GeoDAWN](https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and) · [GDR/INGENIOUS 1391](https://gdr.openei.org/submissions/1391) · [USGS FDSN event service](https://earthquake.usgs.gov/fdsnws/event/1/) · [EPSG:32611](https://epsg.io/32611) · [DOE structural inventory DOI](https://www.osti.gov/dataexplorer/biblio/dataset/1148722).
- [Tversky index background](https://en.wikipedia.org/wiki/Tversky_index) is contextual, not the organizer's metric specification.
- Dropbox files were supplied as learning references: GEMS rules PDF, example submission TIFF, existing faults TIFF, numerical GeoDAWN features TIFF and DEM-links JSON PDF. A Dropbox hash or owner mirror does not authenticate official organizer data.

## Known limitations and current stop

- DrivenData training data require account access; this environment has not authenticated the organizer portal. Pinned GitHub owner mirrors are useful for reproducible learning and audits, but are **not organizer-authenticated**.
- Private final-round labels and submission receipts are unavailable here. The authenticated weekly submission cap cannot be inferred from an old page or public score.
- Current outbound access may exclude DrivenData, USGS and other source hosts; inability to fetch is not evidence that a URL is dead. Record it and do not fabricate verification.
- The prior IEDR lane is stopped: its final dots exceed the literal lattice-overlap threshold, its surface-stage check was not recorded, and prior full-catalogue holdouts/canaries are inadmissible for promotion. The historical MPLC output also exceeds the threshold. No unique, scientifically validated contest TIFF is currently authorized; no holdout estimate is available. Do not make a trivial/empty raster just to satisfy the request to produce a file.
- The leaderboard feed must state its observation date and whether refresh succeeded. A stale snapshot is not current; conflicts among reports remain explicitly flagged.

## Three-pass execution and core values

1. Implement/review the requested work and verify outputs.
2. Inspect bugs, missing requirements, assumptions, and edge cases; fix them.
3. Re-check all original requirements, source attribution, gates, and user-facing decision.

Work autonomously when possible, cite sources for manual review, report real blockers, and finish end-to-end. **Maximize P(Win)** means choose the evidence-backed path most likely to improve the competition result, not a fabricated high score. **Own the Outcome** means fix shared defects, communicate negative evidence, and never imply that an unavailable TIFF, score, deployment, PR, or merge succeeded.
