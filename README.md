# KANLERGEMSDOE1 · DOE GEMS Prize research

> **Standing instruction:** Read this README and [`docs/ORIGINAL_PROMPT.md`](docs/ORIGINAL_PROMPT.md) at the start of every session. Maximize P(Win). Own the Outcome.

## 📋 Standing prompt (operative requirements, archive)

Goal: place top of the DOE GEMS Prize leaderboard with a **genuinely unique, high-scoring, single-band GeoTIFF readily downloadable from a clean GitHub Pages executive summary**. Never manufacture a live-score prediction; never copy a previous submission except to learn.

1. **Focus sites:** GEMSDOE24, 25, 27, 28, 30, 31, 32, 33, 36. Produce an executive summary that makes it obvious which submission is best, with a table listing: file to download, estimated score (labeled owner-report / HOLDOUT-DTI diagnostic / ORGANIZER-CONFIRMED receipt — never a bare projection), and whether it is unique vs the other GEMSDOE sites. All nine focus champions are near-duplicates of one nested dotted support; the highest owner-reported score is GEMSDOE32 h33-2-b2 at 0.2778 (no receipt).
2. **Generate a unique TIF submission.** It must not duplicate any prior submission. The site must offer an obvious, easy download of the submission TIF, and state explicitly whether it is OK to download and submit.
3. **Fix the `[0, 1]` problem:** predictions must be finite and in [0, 1] (the prior portal rejection was `Predicted values must be in range [0, 1]`). Use a zeros encoding (0 outside footprint, no NaNs anywhere) or verified NaN-outside convention; do not clip invalid input silently.
4. **Submission identity:** unique file name plus a portal note ≤ 140 characters. Record the exact uploaded file hash, timestamp, and organizer submission-page receipt after any upload.
5. **Validation gates:** exact CRS EPSG:32611, shape 3730 × 3292, 100 m geotransform matching the sample; single band float32; no NaN inside the footprint; values in [0, 1]; zero outside footprint; zero on the mapped catalogue. Local format validity ≠ organizer acceptance.
6. **Scoring attribution:** label numbers HOLDOUT-DTI (evaluator version, withheld positives, 95% CI) or ORGANIZER-CONFIRMED (from a receipt). A projection is never a score.
7. **Lane protocol:** stay in one method lane. Stop if Spearman ρ > 0.90 vs any registry raster, or > 70% of dots within 3 px of one registry raster (no lattice/density exemption). Hide whole fault segments with buffers; derive catalogue features from visible faults only; score pooled DTI (α=0.2, β=0.8, 300 m triangular kernel). Leakage canary: AUC > 0.90 on a single feature means leakage until disproven. Budget: ≤3 experiments or ≤2 hours; negative results are deliverables; a separate selector decides any slot.

**Current state:** H-UNQ-1 (blind stepover–radiometric conduit dots, 34,000 dots) generated: format-valid, unique vs registry, holdout-DTI diagnostic 0.0078 [0.0049, 0.0107] — **negative, not score-cleared**. Download: `docs/downloads/gemsdoe32-h-unq1-blind-stepover-radiometric-conduit-dots-20261027T170959Z-339ac2dd-zeros.tif`.

## 🔴 STOP — no contest raster is cleared

The prior IEDR lane is stopped. A reproducible audit found **99.39375%, 99.5875% and 99.190625%** of H1/H2/H3 dots within three pixels of a registered spacing-5 lattice, respectively. The user set a strict **>70% = duplicate and stop**, with no density or lattice exemption. A surface-stage check was not recorded. The prior full-map holdout leaked catalogue information through its emission mask, and the feature canaries were not verified on withheld-only folds. Those scores and uniqueness claims are **not promotion evidence**. No new candidate, experiment, or competition slot was created in this review.

There is no demonstrated unique, high-scoring single-band TIFF ready to submit. A separately produced historical MPLC TIFF, added to main by a parallel lane, also fails the same rule: **99.9522%** overlap with the registered lattice. Its earlier discrete-peers-only "unique" claim is not an all-registry pass, and its holdout was not independently replayed in this review. The older TIFFs remain in Git for provenance, **not** for contest download. Local format compliance does not prove organizer acceptance or the cause of the user's prior `Predicted values must be in range [0, 1]` rejection.

- **Pages:** [`docs/index.html`](docs/index.html) → [executive summary](docs/executive-summary.html) · [submission gate](docs/how-to-submit.html) · [ranked research](docs/hypotheses.html) · [why 0.2778](docs/research.html) · [sources](docs/sources.html).
- **One current negative JSON card:** [`data/run-card.json`](data/run-card.json), also published at [`docs/evidence/current_run_card.json`](docs/evidence/current_run_card.json).
- **Independent retrospective evidence:** [`evidence/protocol_audit_20261026.json`](evidence/protocol_audit_20261026.json), nine immutable references in [`registry/focus_sites.json`](registry/focus_sites.json), the [parallel-lane correction](docs/mplc/index.html), and the dated [three-pass review](docs/review-record.md).
- **Scores:** h33-2-b2's 0.2778 and the nine-site values are user/owner reports, not submission-page receipts. Rank 1 public leaderboard was 0.4437 on 2026-10-26: an organizer-published board snapshot, not a receipt for any file. No future live score is forecast.

## Non-negotiable protocol

1. Stay in the assigned method lane. Before placement, compare the continuous surface **and preregistered preview support** to every registry raster; repeat on final dots. Stop if Spearman ρ > 0.90 or >70% of candidate dots/support lie within 3 pixels of any reference. Missing inventory, undefined measurements, missing surface evidence, or any duplicate fail closed. **No lattice, calibration, sparse or dense exemption is authorized.** A lower dot budget might change the lattice bound; that does not authorize a new experiment after STOP.
2. Reuse the shared cached feature stack, [`scripts/evaluate_holdout.py`](scripts/evaluate_holdout.py) and [`scripts/submission_writer.py`](scripts/submission_writer.py). Fix shared code once, not in a private fork. Hide whole fault segments in spatially buffered blocks; derive *every* catalogue-based feature and placement gate from that fold's visible faults only. Mask visible faults pixel-exactly and calculate pooled DTI with α=0.2, β=0.8, and a 300 m triangular kernel. A file of per-cell predictions does not by itself prove their provenance.
3. Label values **HOLDOUT-DTI**, with evaluator version, withheld-positive count and 95% CI, or **ORGANIZER-CONFIRMED** copied from a submission-page receipt. Historical scores without receipts are user/owner reports. A forecast is never a score.
4. Run each feature alone as a **withheld-fold** leakage canary; symmetric AUC >0.90 means leakage until disproven. Missing/failed canaries stop the lane.
5. Finish with one JSON card: hypothesis, mechanism, named non-fault mimic, valid holdout DTI + CI or unavailable, registry correlations/overlaps and scope, raster SHA-256, validator checks including NaN/range/grid, filename and note ≤140 characters, and negative/promote verdict. Negative is a deliverable.
6. Maximum three experiments or two hours. Do not select or spend a real weekly submission slot: a separate selector decides after the scientific and format gates, and the authenticated platform's displayed quota governs. Do not copy a previous submission except to learn.

The surviving prompt archive is a **reconstruction**, not a verbatim original: earlier user wording is not available in this session. The archive carries all consequential requirements known to this session.

## Reproduce the retrospective audit

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export GEMS_DATA_DIR="$PWD/.cache/gems_data"
bash scripts/download_competition_data.sh
.venv/bin/python scripts/prepare_data.py
.venv/bin/python scripts/audit_existing_candidates.py --restore
.venv/bin/python -m unittest discover -s tests -v
```

The restore command fetches 26 SHA-256/size-pinned owner mirrors via immutable Git commits; the audit additionally restores nine pinned focus references. The `data/` receipts record hashes and preparation details, but **do not authenticate those bytes as official organizer downloads**. The portal data tab is login-walled. `.cache/` and `.venv/` are transient/ignored; restore after a fresh checkout. The mirrored sample is used as a grid/footprint template only: its 60,988 positive pixels coincide with labels, despite the official description of an all-zero sample prediction.

`scripts/run_iedr_experiments.py` intentionally exits with STOP. Do not rerun the old runner or generate a replacement in this lane. The audit reopens historical files only, spends no slot, and cannot certify an inventory beyond the nine champions and one lattice it checks.

## Shared-tool corrections and limitations

- The hide-and-recover evaluator is `GEMSDOE32-HIDE-RECOVER-v3.1`: false-positive mass from truth-empty folds is included in pooled DTI and spatial bootstrap. Full-catalogue maps require explicit diagnostic opt-in and cannot establish promotion evidence. Fold-local arrays require an independent provenance replay.
- The writer rejects nonfinite/out-of-range input and off-footprint/on-catalogue positives instead of clipping or thresholding, preserves soft probabilities, validates against the sample grid, and stages both encodings, sidecar and one-file ZIP with collision-safe rollback. Its checks are local, not a guarantee of portal acceptance. Follow current official instructions for outside-footprint nodata.
- A shared Hessian correction uses the larger-magnitude principal eigenvalue and explicitly distinguishes bright ridges from both-polarity responses. H33 thermal-conduit code also now uses the magnetic rather than elevation gradient. Historical outputs used the old code and are unchanged. All old **derived** feature caches are incompatible: rebuild with `gems32.features.build` and load with `load_checked`; the 19 prepared input-band caches are separate and unaffected. No corrected derived stack has been built from the real data in this stopped lane.
- `GEMSDOE32` h33-2-b2's decoded support is exactly the D2.8 support minus cells within 2 pixels of the mirrored catalogue. This supports a geometric hypothesis about sparse DTI credit, not proof of causation or access to private test labels. The organizer excludes only exact known-fault pixels; nearby unknown truth may be useful.
- Four [unimplemented hypotheses](docs/research/hypotheses-20261026.md) are qualitatively ranked, with costs, data access, novelty limits and non-fault mimics. The highest-ranked raw-event idea was not acquired or tested; even its broad concept had already been proposed in H33-E. A future trial needs a new protocol decision after the stop, verified open data, a complete registry and unbiased evidence.
- The Pages workflow is configured to attempt a daily public-leaderboard refresh, falling back to its explicitly dated snapshot if unavailable or unparsable. Its scheduled deployment has not yet been observed running in GitHub Actions.
