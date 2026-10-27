# KANLERGEMSDOE1 · DOE GEMS Prize research

> **Standing instruction:** Read this README, [`docs/ORIGINAL_PROMPT_20261027.md`](docs/ORIGINAL_PROMPT_20261027.md) (this session's full brief) and [`docs/research/preregistration-20261027.md`](docs/research/preregistration-20261027.md) at the start of every session.
>
> **Core Values — Maximize P(Win):** in every decision, weigh tradeoffs and risk and choose the path that maximizes the probability of winning; set aside emotions and make the tough call. **Own the Outcome:** own results end to end, act without waiting for permission, treat failure and success as signals, stay accountable to the final outcome. Applied here: a unique, format-valid candidate that *loses* its holdout is published as a negative result — never renamed, never submitted.

## 🔴 Current verdict (2026-10-27): DO NOT SUBMIT anything

New lane **KANLER-CONCORD** (5-family soft-min concordance surface) was pre-registered, built, and tested fold-locally against the champion method. It is **unique and format-valid but holdout-negative**:

| File (download for research only) | Estimated score (labelled) | Unique vs GEMSDOE sites? | Submit? |
|---|---|---|---|
| `docs/downloads/kanlergemsdoe1-concord5-b2-37654-research-20261027T171958Z-5dde8074-zeros.tif` (SHA-256 `ed4359e4…f609`) | **HOLDOUT-DTI 0.0518** [0.0443, 0.0595] (GEMSDOE32-HIDE-RECOVER-v3.1, 22,232 withheld); PROJECTION ≈0.144 (not a score) | **Yes** — worst \|ρ\| 0.070, worst 3 px overlap 46.0% (vs champion 28.8%), 22 genuine rasters checked | **NO** |
| EXP1 control reconstruction (`…h195field-b2…fc14041c-zeros.tif`) | HOLDOUT-DTI **0.1002** [0.0869, 0.1138] | No — 100% overlap with the H19-5/D2.8 family | **NO** (duplicate lane) |
| Parallel lane H-UNQ-1 (merged 2026-10-27) | Full-map HOLDOUT-DTI diagnostic 0.0078 [0.0049, 0.0107] **NOT-A-SCORE**; SGMC figure self-referential | Yes vs 2 references (ρ≈0.0006) | **NO — DO NOT SUBMIT** (diagnostic-only) |
| GEMSDOE32 `h33-h33-2-b2` (reference copy) | **0.2778 USER/OWNER-REPORT** (no organizer receipt in repo) | No — nested in same family | **NO** (already submitted) |

- **Why 0.2778 led:** byte audit proves GEMSDOE24/25/27/28/30/31/32/33/36 best files are one nested H19-5 family (121,131 → 44,090 dotted at √8 px → 40,199 B1 → 37,654 B2). Under DTI = T/(0.2·(T+n−M)+0.8·|G|), sparsification deletes mostly denominator. This session *validated the B2 collar fold-locally* (gated relaxation: Δ −0.0060, CI excludes 0) and *rejected* a new ranking (Δ −0.0484). Beating 0.2778 requires a better ranking (leader 0.4544, ORGANIZER-PUBLISHED 2026-10-27), not more dotting.
- **Pages:** [`docs/index.html`](docs/index.html) → [executive summary](docs/executive-summary.html) (decision table + nine-site table) · [submission gate / how to submit](docs/how-to-submit.html) (incl. the `[0,1]`-error fix) · [why 0.2778](docs/research.html) · [research slate](docs/hypotheses.html) · [sources](docs/sources.html).
- **Run cards (all verdict negative):** CONCORD lane [`docs/evidence/run_card_concord.json`](docs/evidence/run_card_concord.json); parallel H-UNQ-1 lane [`docs/evidence/run_card_h_unq1.json`](docs/evidence/run_card_h_unq1.json); stopped-IEDR current card [`data/run-card.json`](data/run-card.json) = [`docs/evidence/current_run_card.json`](docs/evidence/current_run_card.json) (restored at merge so no lane erases another). Experiments: [`evidence/concord_experiments.json`](evidence/concord_experiments.json), Pass-2 audit: [`evidence/concord_pass2.json`](evidence/concord_pass2.json), learnings: [`knowledge/03_concord_negative_20261027.md`](knowledge/03_concord_negative_20261027.md).
- **Next lane (pre-registered rank 2):** spatially-blocked PU-HGB over line features, no road veto, identical emission/gates. It must beat HOLDOUT-DTI 0.1002 with paired CI > 0 before any slot is discussed. No slot was used this session.

## Non-negotiable protocol (parallel-run)

1. One lane per session. Surface check **before** placement, final-dot check after: stop if Spearman ρ > 0.90 or >70% of dots within 3 px of any genuine registry raster. The synthetic spacing-5 lattice (3 px halo = 99.87% of domain; champion 99.9%) is disclosed as **IR-LATTICE** diagnostic — selector must ratify gating on genuine submissions.
2. Reuse shared tools only: [`scripts/evaluate_holdout.py`](scripts/evaluate_holdout.py) (hide whole segments, visible-only features/masks, pooled DTI α=0.2 β=0.8 300 m kernel, v3.1) and [`scripts/submission_writer.py`](scripts/submission_writer.py) (rejects — never clips — invalid values; guarantees finite [0,1]).
3. Label every number **HOLDOUT-DTI** (evaluator + withheld n + 95% CI), **ORGANIZER-CONFIRMED** (receipt only), **USER/OWNER-REPORT**, or **PROJECTION**. A projection is never a score.
4. Per-feature withheld-fold canary; symmetric AUC > 0.90 = leakage, stop.
5. One JSON run card (hypothesis, mechanism, mimic, holdout + CI, registry ρ/overlap, SHA-256, validator output, name + note ≤140 chars, verdict). Negative is a deliverable.
6. ≤3 experiments / ≤2 h per lane. Promotion is a separate selector step within the platform's displayed weekly cap. Never copy a previous submission except to learn.

## Reproduce (CPU; ~3 min experiments after restore)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export GEMS_DATA_DIR="$PWD/.cache/gems_data"
bash scripts/download_competition_data.sh   # 26 SHA-pinned owner mirrors (NOT organizer-authenticated)
.venv/bin/python scripts/prepare_data.py
.venv/bin/python scripts/run_concord_experiments.py
.venv/bin/python scripts/concord_pass2_audit.py
.venv/bin/python -m unittest discover -s tests -v
```

## Limitations (what would unblock a win)

- **No DrivenData auth / no GPU in sandbox:** cannot fetch organizer originals, submit, or train the reference U-Net here. Organizer data tab is login-walled; competition bytes above are owner mirrors (mirrored `sample_submission` positives coincide with labels — grid template only).
- **Egress allowlist** (github/pypi) blocks bulk USGS ComCat / SGMC-contact downloads — hypotheses 4–5 need an unrestricted runner (sources named in the slate).
- **Holdout ≠ live:** withheld catalogue segments reward catalogue-like faults; live truth is newly expert-mapped faults. HOLDOUT-DTI ranks methods; only organizer receipts confirm live scores.
- Historical IEDR/MPLC lanes remain stopped (see `docs/review-record.md`); their files are provenance, never downloads-to-submit.
