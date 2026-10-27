# KANLERGEMSDOE1 · DOE GEMS Prize research

> **Standing instruction:** Read this README and [`docs/ORIGINAL_PROMPT.md`](docs/ORIGINAL_PROMPT.md) at the start of every session. Maximize P(Win). Own the Outcome.

## Active project brief — read this and the archive every session

Aim to place near the top of the DOE GEMS fault-mapping leaderboard through distinct, scientific, leakage-safe tests and an easy-to-use, automatically validated submission workflow. The focus sites and highest values quoted in the user's brief are GEMSDOE24 **0.2477**, 25 **0.2600**, 27 **0.2449**, 28 **0.2710**, 30 **0.2600**, 31 **0.2708**, 32 **0.2778**, 33 **0.2632**, and 36 **0.2750**. Every one is a **USER/OWNER-REPORT**, not a submission receipt or expected score. GEMSDOE32's h33 0.2778 is the highest of these nine reports, but is not a submit recommendation.

The brief also cites leaderboard values **0.3195** and **0.4413**; the repo retains a separate **0.4437** snapshot dated 2026-10-26. They conflict in date/scope. The current leaderboard value is **unknown** until a fresh, timestamped organizer page is verified. The active detailed brief, source links, protocol, data-access limitations, and prior rejection are in [`docs/ORIGINAL_PROMPT.md`](docs/ORIGINAL_PROMPT.md). It is an operational restatement, not a verbatim transcript.

## Latest review — 27 October 2026 UTC

The assigned IEDR lane remains stopped after the literal >70% registry-overlap failure. No new method lane was supplied and no experiment, prediction raster, or competition slot is authorized. **No TIFF is currently safe to download or submit.** The [nine-site readiness table](docs/submission-readiness.html) and [CSV](docs/evidence/submission_readiness.csv) list each historical reference, attribution, unavailable score estimate, measured overlap, and **file to submit: NONE**. Build/verify with `python scripts/build_readiness_report.py` / `--check`. The latest byte audit is [`evidence/protocol_audit_20261027.json`](evidence/protocol_audit_20261027.json); it is not a new experiment or holdout score.

Core values are **Maximize P(Win)** and **Own the Outcome**: prefer a verified negative result to an invented score or duplicate upload. The competition predicts fault traces, not geothermal vents directly. Review and limitations: [2026-10-27 three-pass record](docs/review-20261027.md).

## 🔴 STOP — no contest raster is cleared

The prior IEDR lane is stopped. A reproducible audit found **99.39375%, 99.5875% and 99.190625%** of H1/H2/H3 dots within three pixels of a registered spacing-5 lattice, respectively. The user set a strict **>70% = duplicate and stop**, with no density or lattice exemption. A surface-stage check was not recorded. The prior full-map holdout leaked catalogue information through its emission mask, and the feature canaries were not verified on withheld-only folds. Those scores and uniqueness claims are **not promotion evidence**. No new candidate, experiment, or competition slot was created in this review.

There is no demonstrated unique, high-scoring single-band TIFF ready to submit. A separately produced historical MPLC TIFF, added to main by a parallel lane, also fails the same rule: **99.9522%** overlap with the registered lattice. Its earlier discrete-peers-only "unique" claim is not an all-registry pass, and its holdout was not independently replayed in this review. The older TIFFs remain in Git under [`evidence/quarantine_rasters/`](evidence/quarantine_rasters/), outside the published Pages tree, for provenance only. No TIFF or ZIP is published in `docs/downloads/`. Local format compliance does not prove organizer acceptance or the cause of the user's prior `Predicted values must be in range [0, 1]` rejection.

- **Pages:** [`docs/index.html`](docs/index.html) → [executive summary](docs/executive-summary.html) · [submission gate](docs/how-to-submit.html) · [ranked research](docs/hypotheses.html) · [why 0.2778](docs/research.html) · [sources](docs/sources.html).
- **One current negative JSON card:** [`data/run-card.json`](data/run-card.json), also published at [`docs/evidence/current_run_card.json`](docs/evidence/current_run_card.json).
- **Independent retrospective evidence:** [`evidence/protocol_audit_20261027.json`](evidence/protocol_audit_20261027.json), nine immutable references in [`registry/focus_sites.json`](registry/focus_sites.json), the [parallel-lane correction](docs/mplc/index.html), and the dated [three-pass review](docs/review-20261027.md).
- **Score attribution:** h33-2-b2's 0.2778 and the nine-site values are user/owner reports, not submission-page receipts. The only repo-stored public-board observation is 0.4437 dated 2026-10-26. GitHub Actions confirms a leaderboard-refresh step ran on 2026-10-27, but the fetch result is not recorded in the repository; the live current rank remains unverified.

## Non-negotiable protocol

1. Stay in the assigned method lane. Before placement, compare the continuous surface **and preregistered preview support** to every registry raster; repeat on final dots. Stop if Spearman ρ > 0.90 or >70% of candidate dots/support lie within 3 pixels of any reference. Missing inventory, undefined measurements, missing surface evidence, or any duplicate fail closed. **No lattice, calibration, sparse or dense exemption is authorized.** A lower dot budget might change the lattice bound; that does not authorize a new experiment after STOP.
2. Reuse the shared cached feature stack, [`scripts/evaluate_holdout.py`](scripts/evaluate_holdout.py) and [`scripts/submission_writer.py`](scripts/submission_writer.py). Fix shared code once, not in a private fork. Hide whole fault segments in spatially buffered blocks; derive *every* catalogue-based feature and placement gate from that fold's visible faults only. Mask visible faults pixel-exactly and calculate pooled DTI with α=0.2, β=0.8, and a 300 m triangular kernel. A file of per-cell predictions does not by itself prove their provenance.
3. Label values **HOLDOUT-DTI**, with evaluator version, withheld-positive count and 95% CI, or **ORGANIZER-CONFIRMED** copied from a submission-page receipt. Historical scores without receipts are user/owner reports. A forecast is never a score.
4. Run each feature alone as a **withheld-fold** leakage canary; symmetric AUC >0.90 means leakage until disproven. Missing/failed canaries stop the lane.
5. Finish with one JSON card: hypothesis, mechanism, named non-fault mimic, valid holdout DTI + CI or unavailable, registry correlations/overlaps and scope, raster SHA-256, validator checks including NaN/range/grid, filename and note ≤140 characters, and negative/promote verdict. Negative is a deliverable.
6. Maximum three experiments or two hours. Do not select or spend a real weekly submission slot: a separate selector decides after the scientific and format gates, and the authenticated platform's displayed quota governs. Do not copy a previous submission except to learn.

The standing archive is a **structured restatement**, not a verbatim transcript. It now captures the user brief supplied on 2026-10-27 and carries the consequential requirements and source links for future sessions.

## Reproduce the retrospective audit

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export GEMS_DATA_DIR="$PWD/data"
bash scripts/download_competition_data.sh
.venv/bin/python scripts/prepare_data.py
.venv/bin/python scripts/audit_existing_candidates.py --restore
.venv/bin/python -m unittest discover -s tests -v
```

The restore command fetches 26 SHA-256/size-pinned owner mirrors via immutable Git commits; the audit additionally restores nine pinned focus references. The `data/` receipts record hashes and preparation details, but **do not authenticate those bytes as official organizer downloads**. The portal data tab is login-walled. Root-level `data/*.tif` and restored `data/focus/` are ignored; manifests/receipts remain versioned, not the large core rasters. `.cache/` and `.venv/` are transient/ignored; restore after a fresh checkout. The mirrored sample is used as a grid/footprint template only: its 60,988 positive pixels coincide with labels, despite the official description of an all-zero sample prediction.

`scripts/run_iedr_experiments.py` intentionally exits with STOP. Do not rerun the old runner or generate a replacement in this lane. The audit reopens historical files only, spends no slot, and cannot certify an inventory beyond the nine champions and one lattice it checks.

## Shared-tool corrections and limitations

- The hide-and-recover evaluator is `GEMSDOE32-HIDE-RECOVER-v3.1`: false-positive mass from truth-empty folds is included in pooled DTI and spatial bootstrap. Full-catalogue maps require explicit diagnostic opt-in and cannot establish promotion evidence. Fold-local arrays require an independent provenance replay.
- The writer rejects nonfinite/out-of-range input and off-footprint/on-catalogue positives instead of clipping or thresholding, preserves soft probabilities, validates against the sample grid, and stages both encodings, sidecar and one-file ZIP with collision-safe rollback. Its checks are local, not a guarantee of portal acceptance. Follow current official instructions for outside-footprint nodata.
- A shared Hessian correction uses the larger-magnitude principal eigenvalue and explicitly distinguishes bright ridges from both-polarity responses. H33 thermal-conduit code also now uses the magnetic rather than elevation gradient. Historical outputs used the old code and are unchanged. All old **derived** feature caches are incompatible: rebuild with `gems32.features.build` and load with `load_checked`; the 19 prepared input-band caches are separate and unaffected. No corrected derived stack has been built from the real data in this stopped lane.
- `GEMSDOE32` h33-2-b2's decoded support is exactly the D2.8 support minus cells within 2 pixels of the mirrored catalogue. This supports a geometric hypothesis about sparse DTI credit, not proof of causation or access to private test labels. The organizer excludes only exact known-fault pixels; nearby unknown truth may be useful.
- Four [unimplemented hypotheses](docs/research/hypotheses-20261026.md) are qualitatively ranked, with costs, data access, novelty limits and non-fault mimics. The highest-ranked raw-event idea was not acquired or tested; even its broad concept had already been proposed in H33-E. A future trial needs a new protocol decision after the stop, verified open data, a complete registry and unbiased evidence.
- The Pages workflow attempts a daily public-leaderboard refresh and labels the dated fallback when fetching/parsing fails. GitHub Actions API confirms the refresh step completed at 2026-10-27 12:07:26 UTC; the deployed artifact/log could not be inspected here, so fetch success is unknown. The repository copy remains the dated 2026-10-26 snapshot.
- The pinned [official reference-solution README](https://github.com/drivendataorg/gems-prize-reference-solution/blob/aebe92f7c8a990f0e3443451b7a825d9afd6336b/README.md) documents CPU-only and GPU environments; GPU is not shown to be universally required. The full training path in this repository has not been run.
