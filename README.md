# KANLERGEMSDOE1 · DOE GEMS Prize Research & Multi-Physics Fault Discovery

> **Standing instruction:** Read this README and [`docs/ORIGINAL_PROMPT.md`](docs/ORIGINAL_PROMPT.md) at the start of every session. Maximize P(Win). Own the Outcome.

## 🔴 Literal Release-Gate Status (`release_gate.py`) & 2026-10-27 `CGJI-HTB` Suite Summary

- **Literal Zero-Exemption Gate Status (`verdict = negative`, `ok_to_submit = false`, `selector_required = true`):**
  Under `src/gems32/release_gate.py` (Protocol Rule 1: *stop if `|Spearman| > 0.90` or `>70%` of candidate dots lie within `<=3 px` of any registry raster, with no density or calibration-lattice exemption*), the registered 206,895-dot spacing-5 grid lattice (`data/scored/13gems_20261001_r13-lattice-s5_v2_nan-outside.tif`, placing dots at every `y % 5 == 0, x % 5 == 0`) covers **`5,099,871 / 5,106,385 = 99.8724%`** of all off-catalogue footprint pixels within $\sqrt{8} \approx 2.828 \le 3\text{ px}$ and **`100.0000%` (`0` exceptions)** of off-catalogue pixels inside the 10-px eroded active evaluation domain. Consequently, any ~37,654-dot raster in the active domain has `>98%` 3-px overlap with the spacing-5 lattice (`99.28%` on `EXP2_CGJI_OOF_HGB`; `99.39375%`, `99.5875%`, and `99.190625%` on archival H1/H2/H3; `99.9522%` on archival MPLC; `99.13%–99.38%` on all 9 focus champions `GEMSDOE24`..`GEMSDOE36`). Without an explicit selector policy exemption for the calibration lattice, no weekly submission slot is consumed.
- **2026-10-27 `CGJI-HTB` 3-Experiment Suite (Fold-Local, Hidden-Label Invariant, Non-Lattice Unique):**
  We rebuilt and verified the 35-channel v2 feature stack (`gems32-structural-v2-principal-curvature`, SHA-256 `ec70d7eac8f19f6910b98342ad2eff571bbd9ef20c718eedd900e06ca4acc944`) and executed the 3-experiment **`L-CGJI-HTB-2026-10-27`** lane (*Gallardo–Meju Structural Cross-Gradient Collinearity + Piedmont Break-in-Slope Scarp Dipole + Hydrothermal Upflow Breach Detector* on a 1-px transverse Non-Maximum Suppressed crest skeleton, `37,654` dots, `min_dist = sqrt(8)`, fold-local `B = 2` visible-fault collar):

| Experiment / Baseline | `HOLDOUT-DTI` (`GEMSDOE32-HIDE-RECOVER-v3.1`, `n=22,232`) | `HOLDOUT-DTI` (`GEMSDOE32-SGMC-CAL-v3.0`, `n=62,703`) | 21 Non-Lattice Peers Max 3-px Overlap (`<=70%`) | Vs `GEMSDOE32` 3-px Overlap | Pre-Placement Max `\|Spearman\|` (`<=0.90`) | Literal Lattice Overlap |
|---|---|---|---|---|---|---|
| **`EXP1_CGJI_PHYS_NMS`** (Label-free physical NMS crest) | `0.060929` `[0.049968, 0.073197]` | **`0.115633` (#1)** `[0.097758, 0.134248]` | **`40.99%` PASS** | `25.51%` | `0.2939` PASS | `98.64%` STOP |
| **`EXP2_CGJI_OOF_HGB`** (Fold-local OOF-HGB on 40-ch stack over NMS crest) | **`0.099671` (#1)** `[0.085008, 0.113669]` | `0.083354` `[0.072470, 0.093394]` | **`58.70%` PASS** | `45.28%` | `0.2909` PASS | `99.28%` STOP |
| **`EXP3_CGJI_EK_HYBRID`** (300 m kernel-credit crest-coherent hybrid) | `0.096477` `[0.082813, 0.110499]` | `0.092496` `[0.079882, 0.104520]` | **`57.35%` PASS** | `43.77%` | `0.2887` PASS | `99.08%` STOP |
| **`GEMSDOE32` (`D2.8 B=2` fold-local OOF baseline)** | `0.099202` `[0.085951, 0.112668]` | `0.096060` `[0.081906, 0.111270]` | `100.00%` FAIL (nested) | `100.00%` | `1.0000` | `99.13%` STOP |
| **`GEMSDOE31` (`D2.8 B=1` fold-local OOF baseline)** | `0.098977` `[0.086062, 0.112073]` | `0.096273` `[0.082068, 0.111572]` | `100.00%` FAIL (nested) | `100.00%` | `0.9649` | `99.18%` STOP |
| **`GEMSDOE25 / 30` (`D2.8 B=0` fold-local OOF baseline)** | `0.096743` `[0.084162, 0.109525]` | `0.095282` `[0.081239, 0.110359]` | `100.00%` FAIL (XOR=0) | `100.00%` | `0.9229` | `99.26%` STOP |

- **Primary Staged GeoTIFF Artifact (15/15 Format Checks Passed, Research-Staged):**
  - Path: [`submissions/cgji_htb_20261027/gemsdoe32-cgji-htb-exp2-oof-hgb-b2-20261027T013000Z-5214b9ec-zeros.tif`](submissions/cgji_htb_20261027/gemsdoe32-cgji-htb-exp2-oof-hgb-b2-20261027T013000Z-5214b9ec-zeros.tif) (`sha256 = 74035c67056f7727fb16c04b61446f32a2c729fcf5d711a3b666761e56fcbffe`)
  - Companion NaN-outside GeoTIFF: [`submissions/cgji_htb_20261027/gemsdoe32-cgji-htb-exp2-oof-hgb-b2-20261027T013000Z-5214b9ec-nan.tif`](submissions/cgji_htb_20261027/gemsdoe32-cgji-htb-exp2-oof-hgb-b2-20261027T013000Z-5214b9ec-nan.tif) (`sha256 = 8c5db6b033576adab601393320ab789dbe290490fa67a12efd9d23659655eb11`)
  - Submission Note (`132 <= 140` chars): `CGJI-HTB Exp2 OOF-HGB NMS crest (37654 dots, B=2). HOLDOUT-DTI=0.0997 (GEMSDOE32-HIDE-RECOVER-v3.1, n=22232); research gate stop.`
  - Leakage Canaries & Invariance: 41/41 single features tested on withheld folds pass `sym_AUC <= 0.584624 <= 0.90`; hidden-label perturbation invariance verified bit-for-bit (`max_abs_diff = 0`).
- **Pages & Receipts:**
  - GitHub Pages UI: [`docs/index.html`](docs/index.html) → [executive summary](docs/executive-summary.html) · [submission gate](docs/how-to-submit.html) · [ranked research](docs/hypotheses.html) · [why 0.2778](docs/research.html) · [sources](docs/sources.html).
  - Canonical JSON Run Card: [`data/run-card.json`](data/run-card.json) / [`evidence/run_card.json`](evidence/run_card.json) / [`docs/evidence/current_run_card.json`](docs/evidence/current_run_card.json).
  - 2026-10-27 CGJI-HTB Suite Receipt: [`evidence/cgji_htb_experiments_20261027.json`](evidence/cgji_htb_experiments_20261027.json) / [`docs/evidence/cgji_htb_experiments_20261027.json`](docs/evidence/cgji_htb_experiments_20261027.json).
  - 2026-10-26 Retrospective Audit Receipt: [`evidence/protocol_audit_20261026.json`](evidence/protocol_audit_20261026.json) & [three-pass review record](docs/review-record.md).

---

## Executive Summary of the 9 Focus Sites (`GEMSDOE24` – `GEMSDOE36`)

Live scores below are `USER/OWNER-REPORTS` (not organizer-confirmed submission-page receipts). Every one of the nine focus-site rasters is derived from the `121,131`-pixel `H19-5` or `44,090`-pixel `D2.8` parent support and is **not unique** among the nine sites (`>70%` 3-px overlap with at least one other focus site):

| Focus Site | Pinned Champion File (`registry/focus_sites.json`) | Dots (`d_min`) | Owner-Reported Live Score | `HOLDOUT-DTI` (`GEMSDOE32-HIDE-RECOVER-v3.1`, `n=22,232`) | `HOLDOUT-DTI` (`GEMSDOE32-SGMC-CAL-v3.0`, `n=62,703`) | Lineage & Uniqueness vs Other 8 Focus Sites |
|---|---|---:|---:|---|---|---|
| [GEMSDOE24](https://buffedlizard55-lab.github.io/GEMSDOE24/) | `gems24-h25-1-dotted-h19-5-d1-5-20261002-989f59505db1-nan.tif` | `60,069` ($\sqrt{5}$) | `0.2477` | `0.093151` `[0.080230, 0.107269]` | `0.101118` `[0.084692, 0.117309]` | `100.0%` $\subset$ `H19-5` · **NOT UNIQUE** (`100.0%` vs `GEMSDOE30`) |
| [GEMSDOE25](https://buffedlizard55-lab.github.io/GEMSDOE25/) | `gems25-dotted-h19-5-d2-8-20261002-e56ea318af89-nan.tif` | `44,090` ($\sqrt{8}$) | `0.2600` | `0.096743` `[0.084162, 0.109525]` (OOF $B=0$) | `0.095282` `[0.081239, 0.110359]` | `D2.8` parent (`100.0%` $\subset$ `H19-5`) · **NOT UNIQUE** (`XOR=0` with `GEMSDOE30`) |
| [GEMSDOE27](https://buffedlizard55-lab.github.io/GEMSDOE27/) | `gems27-topo-gap-closure-t-v2-on-d1-5-20261002-5512495c6bd1-nan.tif` | `61,328` ($\ge 1$) | `0.2449` | `0.092748` `[0.079884, 0.106684]` | `0.102422` `[0.085895, 0.118597]` | `GEMSDOE24` + `1,259` gap dots · **NOT UNIQUE** (`98.02%` vs `GEMSDOE24`) |
| [GEMSDOE28](https://buffedlizard55-lab.github.io/GEMSDOE28/) | `gems28-h36-1-rung30-blind-r1-20261003-b531dae0a36f-nan.tif` | `37,660` ($\sqrt{5}$) | `0.2710` | `0.029360` (diag; partial $B=2$ collar) | `0.094341` `[0.080259, 0.109529]` | `100.0%` $\subset$ `H19-5`, `73.96%` $\subset$ `D2.8` · **NOT UNIQUE** (`100.0%` vs `GEMSDOE30`) |
| [GEMSDOE30](https://buffedlizard55-lab.github.io/GEMSDOE30/) | `gemsdoe30-d28-poisson300m-offcat-44090-20261003T233156Z-91eae1ca.tif` | `44,090` ($\sqrt{8}$) | `0.2600` | `0.096743` `[0.084162, 0.109525]` (OOF $B=0$) | `0.095282` `[0.081239, 0.110359]` | Exact duplicate support of `GEMSDOE25` (`XOR=0`) · **NOT UNIQUE** |
| [GEMSDOE31](https://buffedlizard55-lab.github.io/GEMSDOE31/docs/) | `gemsdoe31-h27-4-solo-d28-20261004-8acb75e1-nan.tif` | `40,199` ($\sqrt{8}$) | `0.2708` | `0.098977` `[0.086062, 0.112073]` (OOF $B=1$) | `0.096273` `[0.082068, 0.111572]` | Exact `D2.8` & $d(\mathbf{x},\mathcal{C})>1$ · **NOT UNIQUE** (`100.0%` vs `GEMSDOE30`) |
| [GEMSDOE32](https://buffedlizard55-lab.github.io/GEMSDOE32/docs/index.html) | `gemsdoe32-h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros.tif` | `37,654` ($\sqrt{8}$) | **`0.2778`** | `0.099202` `[0.085951, 0.112668]` (OOF $B=2$) | `0.096060` `[0.081906, 0.111270]` | Exact `D2.8` & $d(\mathbf{x},\mathcal{C})>2$ · **NOT UNIQUE** (`100.0%` vs `GEMSDOE36`) |
| [GEMSDOE33](https://buffedlizard55-lab.github.io/GEMSDOE33/) | `GEMSDOE33-h33d-analog-tip-stepover-r30-20261004-cb490425926e.tif` | `41,865` ($\ge 2$) | `0.2632` | `0.051969` (diag; partial $B=1$ collar) | `0.096764` `[0.082356, 0.112142]` | `99.68%` $\subset$ `H19-5`, `83.25%` $\subset$ `D2.8` · **NOT UNIQUE** (`99.71%` vs `GEMSDOE27`) |
| [GEMSDOE36](https://buffedlizard55-lab.github.io/GEMSDOE36/docs/) | `gemsdoe36-anderson-geothermal-pinn-38854-20261004T230000Z-9b9ea4e6-zeros.tif` | `38,854` ($\ge 1$) | `0.2750` | `0.004577` (diag; full-cat $B=2$ collar) | `0.097434` `[0.083010, 0.112842]` | `GEMSDOE32` + `1,200` grafted dots · **NOT UNIQUE** (`97.58%` vs `GEMSDOE27`) |

---

## Non-negotiable protocol

1. Stay in the assigned method lane. Before placement, compare the continuous surface **and preregistered preview support** to every registry raster; repeat on final dots. Stop if Spearman ρ > 0.90 or >70% of candidate dots/support lie within 3 pixels of any reference. Missing inventory, undefined measurements, missing surface evidence, or any duplicate fail closed. **No lattice, calibration, sparse or dense exemption is authorized.**
2. Reuse the shared cached feature stack, [`scripts/evaluate_holdout.py`](scripts/evaluate_holdout.py) and [`scripts/submission_writer.py`](scripts/submission_writer.py). Fix shared code once, not in a private fork. Hide whole fault segments in spatially buffered blocks; derive *every* catalogue-based feature and placement gate from that fold's visible faults only. Mask visible faults pixel-exactly and calculate pooled DTI with α=0.2, β=0.8, and a 300 m triangular kernel.
3. Label values **HOLDOUT-DTI**, with evaluator version, withheld-positive count and 95% CI, or **ORGANIZER-CONFIRMED** copied from a submission-page receipt. Historical scores without receipts are user/owner reports. A forecast is never a score.
4. Run each feature alone as a **withheld-fold** leakage canary; symmetric AUC >0.90 means leakage until disproven.
5. Finish with one JSON card: hypothesis, mechanism, named non-fault mimic, valid holdout DTI + CI or unavailable, registry correlations/overlaps and scope, raster SHA-256, validator checks including NaN/range/grid, filename and note ≤140 characters, and negative/promote verdict. Negative is a deliverable.
6. Maximum three experiments or two hours. Do not select or spend a real weekly submission slot: a separate selector decides after the scientific and format gates.

---

## Reproduce the full data pipeline, audit, and 3-experiment `CGJI-HTB` suite

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
bash scripts/download_competition_data.sh
.venv/bin/python scripts/prepare_data.py
.venv/bin/python scripts/audit_existing_candidates.py --restore --data-dir data
.venv/bin/python scripts/run_cgji_experiments.py
.venv/bin/python -m unittest discover -s tests -v
```
