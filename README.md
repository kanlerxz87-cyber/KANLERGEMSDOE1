# KANLERGEMSDOE1 — DOE GEMS Prize (DrivenData #306) fault-discovery lane: MPLC

**Read this first, every session.** Original prompt: [`docs/ORIGINAL_PROMPT.md`](docs/ORIGINAL_PROMPT.md).
Core values: **Maximize P(Win)** — a weekly slot is spent only on evidence, never on hope.
**Own the Outcome** — every number below carries an evidence class; failures are published, not buried.

## 🚦 Verdict (automated, no human inspector): 🔴 DO NOT SUBMIT — research download only

| Question | Answer |
|---|---|
| Best historical file across the 9 focus sites? | GEMSDOE32 `h33-h33-2-b2` — **0.2778 OWNER-REPORTED** (no organizer receipt anywhere; already submitted; nested duplicate of the whole H19-5 family). **Never re-upload it.** |
| New unique TIF generated here? | ✅ Yes — [`kanler-mplc-hgb-37654-20261026-0741963ae4e9-zeros.tif`](docs/downloads/kanler-mplc-hgb-37654-20261026-0741963ae4e9-zeros.tif) (37,654 dots, SHA-256 `fe4b8d74…`, all-finite `[0,1]`, validator PASS) |
| OK to download? | ✅ YES (research/reproducibility) |
| OK to submit to DrivenData? | 🔴 **NO** — verdict `negative`. It beats its control on catalogue holdout (paired CI > 0) but **trails the champion on the off-catalogue SGMC discovery proxy (0.0563 vs 0.0954)**, so there is no evidence it beats 0.2778 live. Spending a slot on it would violate Maximize P(Win). |
| Estimated live score? | **NOT ESTIMABLE** (see §Score estimation). Any number would be a fabrication. |

Submission name (for provenance only): `kanler-mplc-hgb-37654-20261026-0741963ae4e9` ·
Note (89/140): `KANLER MPLC phase-congruency HGB 37654d B2 | HOLDOUT-DTI 0.0894 vs 0.0840 | DO NOT SUBMIT`

## Executive summary — the 9 focus sites (all scores OWNER-REPORTED, none ORGANIZER-CONFIRMED)

Every site's best file is the **same H19-5 field** at different emission densities (forensic
lineage: GEMSDOE32 `knowledge/03`, GEMSDOE27 focus-site audit, both fetched 2026-10-26).
They are nested subsets of one another (88–100% 3-px overlap vs the champion) — **none is
unique, all are already submitted, none may be re-uploaded.**

| Site | Highest-scoring file | Score (OWNER-REPORTED) | Dots | Unique vs other 8 sites? | File to download | OK to submit? |
|---|---|---:|---:|---|---|---|
| GEMSDOE32 | h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros | **0.2778** | 37,654 | NO — family parent of the B2 prune | learning reference only | 🔴 NO (already submitted) |
| GEMSDOE36 | anderson-geothermal-pinn-38854 | 0.2750 | 38,854 | NO — 97.4% 3-px vs champion | learning reference only | 🔴 NO |
| GEMSDOE28 | h36-1-rung30-blind-r1 | 0.2710 | ~40,199 | NO — nested H19-5 | learning reference only | 🔴 NO |
| GEMSDOE31 | h27-4-solo-d28 | 0.2708 | 40,199 | NO — nested H19-5 | learning reference only | 🔴 NO |
| GEMSDOE33 | h33d-analog-tip-stepover-r30 | 0.2632 | 41,865 | NO — 92.6% vs champion | learning reference only | 🔴 NO |
| GEMSDOE25 | dotted-h19-5-d2-8 | 0.2600 | 44,090 | NO — exact family member | learning reference only | 🔴 NO |
| GEMSDOE30 | d28-poisson300m-offcat-44090 | 0.2600 | 44,090 | NO — duplicate of GEMSDOE25 d2.8 | learning reference only | 🔴 NO |
| GEMSDOE24 | h25-1-dotted-h19-5-d1-5 | 0.2477 | 60,069 | NO — over-packed H19-5 | learning reference only | 🔴 NO |
| GEMSDOE27 | topo-gap-closure-t-v2-on-d1-5 | 0.2449 | ~61,328 | NO — on d1.5 | learning reference only | 🔴 NO |
| **KANLERGEMSDOE1 (this repo)** | **kanler-mplc-hgb-37654-20261026-0741963ae4e9-zeros** | **live: NOT ESTIMABLE · HOLDOUT-DTI 0.0894 [0.0757, 0.1028]** | 37,654 | **YES vs discrete peers** (max 3-px overlap 46.2% ≤ 70%, max \|Spearman\| 0.126 ≤ 0.90, 33.7% vs champion) | **[⬇ Download TIF](docs/downloads/kanler-mplc-hgb-37654-20261026-0741963ae4e9-zeros.tif)** · [ZIP](docs/downloads/kanler-mplc-hgb-37654-20261026-0741963ae4e9-zeros.zip) | 🔴 **NO — verdict negative (SGMC proxy trails champion)** |

## Why 0.2778 won, and can we beat it? (PhD answer, short form; full: `docs/HYPOTHESES.md`)

Official metric (verified on the [problem page](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/)):
DTI = TPw/(TPw + 0.2·FPw + 0.8·FNw), 300 m triangular kernel. Algebra: a non-redundant dot
helps iff its kernel credit k > 0.2·DTI (≈0.056 at 0.2778). The family ladder
121,131 dots/0.1922 → 60,069/0.2477 → 44,090/0.2600 → 37,654/0.2778 is thinning deleting
sub-bar dots plus a ≤2 px catalogue prune removing dots whose credit is already saturated.
**The win is emission, not detection.** Beating it needs a field whose top ~37k off-catalogue
pixels earn >~25% more mean kernel credit — a detector problem. Our MPLC detector improves
its own control (+0.0054 HOLDOUT-DTI, CI > 0) but does **not** demonstrate that gain
(SGMC proxy 0.0563 vs champion 0.0954). Honest answer: **not demonstrated; do not submit.**

## Score estimation — why "NOT ESTIMABLE" is the only defensible estimate

Three mutually inconsistent instruments exist: catalogue HOLDOUT-DTI (champion fixed raster
0.0044 — anti-aligned by construction, GEMSDOE31 disclosure), SGMC off-catalogue proxy
(champion 0.0954), and OWNER-REPORTED live claims (0.2778). No calibrated mapping between
any of them and the hidden-fault leaderboard has ever been validated; GEMSDOE32 withdrew
its anchor-inversion projections on exactly this ground. Therefore every "estimated
leaderboard score" in this repo is labelled NOT ESTIMABLE, and HOLDOUT-DTI / SGMC numbers
are never written as scores (protocol rule 3).

## This lane (one method, per parallel-run protocol)

**MPLC** — multi-scale oriented log-Gabor **phase congruency** ( contrast-invariant local
phase; layers/signature/mimic/ranking in [`docs/HYPOTHESES.md`](docs/HYPOTHESES.md)) +
39-band HGB + dotted greedy max-cover emission. Experiments (budget 3/3 used):
EXP1 control HOLDOUT-DTI **0.0840 [0.0715, 0.0963]** · EXP2 MPLC **0.0894 [0.0757, 0.1028]**,
paired **+0.0054 [+0.0004, +0.0108]** (gems57-pooled-hide-v2, 11,318 withheld positives,
quadrant-blocked training) · EXP3 budget sweep (44,090: 0.0916 on catalogue holdout —
overruled for the final file by the live OWNER-REPORTED budget ladder; conflict disclosed).
Leakage canary PASS (MPLC AUC 0.506–0.528, no feature > 0.90 two-sided). Validator PASS
(vendor `gems57.validate`, all checks). Run card: [`evidence/run_card.json`](evidence/run_card.json).

## How to submit (when a future file ever earns OK TO SUBMIT)

Full guide: [`docs/executive-summary.html`](docs/executive-summary.html). Short form:
DrivenData #306 → New submission → choose the single-band float32 `.tif` (all-finite
`[0,1]` build — this is what prevents "Predicted values must be in range [0, 1]") or its
single-TIF `.zip` → paste the ≤140-char note → confirm weekly quota → submit. This repo
never contacts DrivenData; upload is manual and is a separate selector decision.

## Irregularities flagged for review

- **IR-K1 (literal lattice):** the registered spacing-5 lattice blanket is within 3 px of
  99.95% of our dots (and of every dense map). Under a literal all-raster reading of the
  uniqueness rule, nothing is submittable; we gate on discrete scored peers (max 46.2%)
  and disclose, mirroring GEMSDOE31 IR-U-02 / GEMSDOE36.
- **IR-K2 (cross-site gate conflict):** GEMSDOE27 and GEMSDOE31 pages (fetched 2026-10-26)
  banner other files "OK TO SUBMIT" under a discrete-peer rescope, while GEMSDOE24/25/32/36
  fail-closed audits say no file is approved. Site banners are not slot approvals.
- **IR-K3 (stale leaderboard numbers):** the prompt quotes highs of 0.4413 and 0.3195.
  The [live leaderboard](https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/)
  fetched 2026-10-26 shows #1 xiaofanhu **0.4437** (public, time-stamped observation only).
- **IR-K4 (unverified scores):** all 9-site scores are OWNER-REPORTED; no submission-page
  receipt linking bytes→score exists in any fetched repo. Data files here are restored
  SHA-256-verified from sibling GitHub mirrors (`registry/data_manifest.json`); their
  official DrivenData origin is not independently authenticated (no DrivenData auth).
- **IR-K5 (band-description conflicts):** local band B6 `tc` is described as magnetic tilt
  while the official page captions `tc` imagery as radiometric total count; B10 as distance
  vs density (GEMSDOE31 IR-31-B06/B10). We use bands as uninterpreted numeric channels.

## Limitations & next steps (for the next session)

1. No GPU / no DrivenData auth in this sandbox; data restored from hash-pinned GitHub mirrors only.
2. The SGMC regression is the blocker: next lane should target *why* the champion field
   earns SGMC credit (multiline corroboration) without copying its dots — e.g. TIPFIELD or
   RADALT from `docs/HYPOTHESES.md`, each as a fresh pre-registered lane with the same gates.
3. A calibrated live-score estimator requires at least one ORGANIZER-CONFIRMED receipt
   tied to exact bytes; until a slot is legitimately spent, none can exist.
4. Promotion remains a separate selector step under the weekly cap. Slots spent by this repo: **0**.

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install numpy scipy rasterio scikit-learn pytest
.venv/bin/python scripts/restore_data.py --group all   # SHA-256-verified restore into data/ (git-ignored)
.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from kanler.mplc import build_mplc; build_mplc('data/training_features.tif','data/sample_submission.tif','data/cache/mplc.npy')"
.venv/bin/python src/kanler/lane.py 37654              # EXP1+EXP2 holdout (evidence/holdout_result.json)
.venv/bin/python scripts/canary_and_exp3.py            # canary + EXP3
.venv/bin/python scripts/final_build.py && .venv/bin/python scripts/audit_final.py
.venv/bin/python -m pytest tests -q
```

Sources (official/verified): [competition problem](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/) ·
[leaderboard](https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/) ·
[reference solution](https://github.com/drivendataorg/gems-prize-reference-solution) ·
[USGS GeoDAWN](https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and) ·
[INGENIOUS](https://gbcge.org/current-projects/ingenious/) · [EPSG:32611](https://epsg.io/32611) ·
[Tversky index](https://en.wikipedia.org/wiki/Tversky_index) · [GDR #1391](https://gdr.openei.org/submissions/1391) ·
[GEMS rules PDF (NLR 96647)](https://docs.nlr.gov/docs/fy26osti/96647.pdf)
