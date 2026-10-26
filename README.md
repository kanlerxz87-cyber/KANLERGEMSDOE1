# KANLERGEMSDOE1

DOE GEMS Prize (DrivenData #306) — lane **L-IEDR-2026-10-26** (independent-earthquake dilatation residual).

> **Standing instruction — read this README and `docs/ORIGINAL_PROMPT.md` before every session.** Maximize P(Win). Own the Outcome.

## Latest audit — 2026-10-26

**DO NOT SUBMIT. Historical holdout and uniqueness clearance are revoked.**
See [the audit](docs/audit-20261026.md) and [fresh artifact checks](evidence/artifact_audit.json).
Full-catalogue masking before placement invalidates the archived hide-and-recover comparison.
The registry lattice overlap exceeds the explicit 70% rule; there is no authorized exemption.
The legacy runner is now fail-closed. No new experiment or weekly slot was used in this audit.
The tables below are archived diagnostics, **not admissible HOLDOUT-DTI or leaderboard estimates**.
Leaderboard snapshots are inherited claims, not reverified receipts in this session.

## 🔴 DO NOT SUBMIT

**No file in this repository is authorized for DrivenData upload.**

Three unique, format-valid GeoTIFFs were generated in `docs/downloads/`. Their archived format audits pass; strict lane uniqueness does not pass (the prior lattice exemption was unauthorized). They do **not** beat the GEMSDOE32 champion on holdout 95% CI or off-catalogue SGMC. A HOLDOUT-DTI is not a live score. Promotion to a weekly slot is a separate selector step.

Primary site: [`docs/index.html`](docs/index.html) (GitHub Pages from `/docs`).

| Download | HOLDOUT-DTI | Unique vs GEMSDOE 24/25/27/28/30/31/32/33/36? | Submit? |
|---|---|---|---|
| [H1 IEDR zeros.tif](docs/downloads/kanlergemsdoe1-h1-iedr-s3p17-b2-32000-20261026T214518Z-fe519ae3-zeros.tif) | 0.00617 [0.00426, 0.00857] · GEMSDOE32-HIDE-RECOVER-v3.0 · n=22232 · **not a live estimate** | NO CLEARANCE — lattice overlap >70% | **NO** |
| [H2 HTSI zeros.tif](docs/downloads/kanlergemsdoe1-h2-htsi-s3p17-b2-32000-20261026T214518Z-571145eb-zeros.tif) | 0.00628 [0.00415, 0.00888] · **not a live estimate** | NO CLEARANCE — lattice overlap >70% | **NO** |
| [H3 COND-RESID zeros.tif](docs/downloads/kanlergemsdoe1-h3-condresid-s3p17-b2-32000-20261026T214518Z-42802022-zeros.tif) | 0.00426 · **not a live estimate** | NO CLEARANCE — lattice overlap >70% | **NO** |
| GEMSDOE32 h33-2-b2 zeros | OWNER-REPORT live **0.2778** · HOLDOUT 0.00452 on this evaluator | reference | **NO** (already submitted) |

Portal note if a future file is authorized (≤140 chars), **not for use today**:

`KANLER H1 IEDR ieq*dil*hgm s3.17 B2 32000d HR=0.0062 | research | DO-NOT-SUBMIT`

Use the **`-zeros.tif`** (or its zip). That variant has `nodata=None` and 0.0 outside the footprint so DrivenData will not return `Predicted values must be in range [0, 1]`.

## Session start (read this every time)

1. Read this README and `docs/ORIGINAL_PROMPT.md`.
2. Status banner is the source of truth for submit / do-not-submit.
3. Reuse `scripts/evaluate_holdout.py` and `scripts/submission_writer.py`. Do not fork the metric.
4. Label every number `HOLDOUT-DTI` (evaluator, n withheld, 95% CI) or `ORGANIZER-CONFIRMED` / `OWNER-REPORT`. Never write a projection as a score.
5. Leakage canary: per-feature symmetric AUC > 0.90 vs the catalogue is a leak.
6. Uniqueness: Spearman ≤ 0.90 and ≤70% of dots within 3 px of **any** registry raster; no lattice exemption.
7. Budget: 3 experiments or 2 hours. Negative results are deliverables.

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export GEMS_DATA_DIR="$PWD/.cache/gems_data"
.venv/bin/python scripts/restore_data.py --group all --target-dir "$GEMS_DATA_DIR"
.venv/bin/python -u scripts/run_iedr_experiments.py
```

Competition rasters are SHA-256-pinned owner mirrors fetched via GitHub API (no DrivenData login). Pins prove mirror consistency, not organizer authentication (`IR-DATA-01`).

## Why 0.2778, and can we beat it?

See [docs/research.html](docs/research.html). Short version: 0.2778 is Poisson-disk + 200 m catalogue collar applied to H19-5, not a new detector. The public leaderboard high is **not freshly verified** (inherited snapshot claims 0.4437; no organizer receipt stored here). This session’s unique IEDR lane did not earn a slot.

## Official links

- Problem: https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/
- About: https://www.drivendata.org/competitions/306/competition-doe-gems/page/968/
- Data (login): https://www.drivendata.org/competitions/306/competition-doe-gems/data/
- Leaderboard: https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/
- Reference solution: https://github.com/drivendataorg/gems-prize-reference-solution
- GeoDAWN: https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and
- INGENIOUS GDR 1391: https://gdr.openei.org/submissions/1391
- EPSG:32611: https://epsg.io/32611
- Tversky index: https://en.wikipedia.org/wiki/Tversky_index

## Limitations

- No DrivenData credentials in this sandbox.
- Hide-and-recover of mapped scarps is a biased proxy for blind geothermal faults.
- Template holdout code is reused from GEMSDOE32 (`src/gems32/`). One template fix: `filename_prefix` on the writer so artifacts are not forced to a `gemsdoe32-` name.
- Root entry pages now redirect to the canonical research site under `docs/`.

## Next work

1. Per-cell OOF emission of IEDR so holdout is comparable to GEMSDOE32’s 0.0992 visible-only number.
2. Human with DrivenData access: byte-compare pinned rasters to the portal download (`IR-DATA-01`) before any live slot.
3. Do not spend a slot on H1/H2/H3 as they stand.

## Core values

Maximize P(Win). Own the Outcome.

---

## Archived session prompt

The standing Arena prompt is in [`docs/ORIGINAL_PROMPT.md`](docs/ORIGINAL_PROMPT.md). Read it at the start of every session.
