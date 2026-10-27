# Archived concurrent continuation review

Preserved from main during PR #11 reconciliation. Statements below describe that earlier session, not the later independent replay in [the current review](review-20261027.md). Subsequent main updates recorded a new public-board observation and corrected the ZIP format.

# Three-pass continuation review — 2026-10-27 UTC

## Pass 1 — repository and prior next steps

Read README, the reconstructed standing prompt, previous review, negative run card, nine-site registry and executive summary. The prior IEDR lane remains stopped after measured registry duplication. No new single-method paragraph is supplied in the renewed request. No candidate experiment, placement, new raster or competition upload was run. The historical audit was inspected, **not independently rerun** in this session.

Added a generated [nine-site readiness table](submission-readiness.html) and [CSV](evidence/submission_readiness.csv), linked near the beginning of the executive summary. Each row explicitly lists the historical artifact, reported score attribution, unavailable estimate, overlap failure, file to submit **NONE**, and submit decision **NO**. Reproduction: `python scripts/build_readiness_report.py --check`. SHA-256 and pinned source information remain in the registry and underlying audit. The report deliberately cannot authorize promotion.

## Pass 2 — defects and edge cases

- The initial test invocation could not import NumPy. Created an ignored `.venv`, installed requirements and reran the full suite successfully.
- Added tests for missing/duplicate inventory, changed hashes or historical scores, NaN/infinite/negative overlap, and changed negative evidence. Inconsistent inputs fail rather than quietly publish a readiness decision.
- Added pull-request/main CI for all scientific/publication tests and generated-report drift detection. Local tests establish expected code behavior, not real-data provenance or leaderboard performance.
- Preserved the existing STOP and withholding of TIFF links; no lattice exemption, renaming trick or private evaluator was introduced.

## Pass 3 — full request check and limitations

- Full local suite: **35 tests passed**, including writer range/geometry/rollback, whole-segment hiding, pooled empty-truth false positives, cache integrity and publication safety. `git diff --check` passed. Two dependency-related affine multiplication deprecation warnings are non-failing; no scientific change was made to suppress them.
- The four ranked hypotheses remain in [the research slate](research/hypotheses-20261026.md). Their expected benefit is qualitative judgment, not a projected score. The top event-lineament idea still needs raw official event/uncertainty data and is not established viable here. No additional experiment is permitted by the current stopped lane.
- GEMSDOE32's reported 0.2778 is highest among the nine pinned champion reports, not an organizer-confirmed receipt. The dated audit finds its support equals D2.8 after the two-pixel catalogue collar. Sparse support/collar geometry is a plausible mechanism for the observed difference, **not a causal proof**. No valid estimate of beating it exists here.
- Current leaderboard cannot be verified from this environment's permitted hosts (GitHub and package registries only). The prompt's 0.3195 and 0.4413 claims conflict; the project's 0.4437 snapshot is dated, not refreshed by this review. No authenticated submission-page quota or receipt was available.
- Fresh official-source check: the [organizer reference repository README](https://github.com/drivendataorg/gems-prize-reference-solution/blob/aebe92f7c8a990f0e3443451b7a825d9afd6336b/README.md) at commit `aebe92f7c8a990f0e3443451b7a825d9afd6336b` instructs downloading competition data into `data/` and explicitly supports CPU-only as well as GPU environments. A GPU is helpful, **not universally required**. This check authenticates the reference instructions, not the mirrored rasters or historical scores.
- No unique high-scoring TIFF was produced: that deliverable remains unmet. No valid fold-local holdout best, complete registry, authenticated template or independent surface evidence was manufactured. The original prompt archive remains explicitly a reconstruction rather than a verbatim transcript; README preserves the operating requirements and this continuation.

## Next session, in order

1. Resolve/explicitly reset the stopped method lane before further experiments; do not silently remove dense registry witnesses.
2. Complete the raster registry and obtain an authenticated data/template provenance chain through approved access. Restore existing pinned data only for audit/learning in the meantime.
3. Establish a replayable visible-only baseline, feature canaries and paired spatial-bootstrap comparison. Only then test a preregistered hypothesis within the three-experiment budget.
4. Require surface/support and final-dot uniqueness, valid HOLDOUT-DTI with evaluator/count/CI, strict writer checks, and a separate selector decision. Only a selected, fully passing file should receive a contest download link.

The single current JSON card remains [current_run_card.json](evidence/current_run_card.json). It is historical negative evidence and was not re-dated to imply a fresh raster evaluation. GitHub PR/merge status is reported separately after the actual operations.
