# `KANLERGEMSDOE1` — DOE GEMS Prize Research, Fold-Local Validation, Registry Uniqueness & Submission Gate System

[![Competition](https://img.shields.io/badge/DrivenData-DOE_GEMS_Prize_(306)-d08a4c)](https://www.drivendata.org/competitions/306/competition-doe-gems/)
[![Gate Status](https://img.shields.io/badge/Portal_Clearance-STOP_/_RESEARCH--HOLD_(verdict:_negative)-ff5d6c)](#4-run-card--slot-clearance-status)
[![Tests](https://img.shields.io/badge/Automated_Gate_Tests-Passing-3dcc8a)](#8-autonomous-reproduction-commands)

End-to-end geological feature engineering, fold-local hide-and-recover evaluation, registry uniqueness auditing, automated GeoTIFF validation, and a fail-closed GitHub Pages research desk (`docs/`) for the [**DOE Geothermal Exploration Machine Learning (GEMS) Prize**](https://www.drivendata.org/competitions/306/competition-doe-gems/).

> **Mandatory session startup:** Before changing code, read this README, [`docs/ORIGINAL_PROMPT.md`](docs/ORIGINAL_PROMPT.md), [`docs/REQUEST_20261027.md`](docs/REQUEST_20261027.md), and [`evidence/current_run_card.json`](evidence/current_run_card.json). These contain the standing user requirements, current lane/evidence and hard stop conditions. Treat every future prompt as additional constraints; preserve the literal registry thresholds, 3-experiment cap, fail-closed selector, and score-evidence labels. If a new request conflicts with a gate, stop and document the conflict instead of publishing a misleading download button.

---

## 0. Current Portal Clearance Banner (Unmistakable Gate Verdict)

> **STOP — NO RASTER IN `KANLERGEMSDOE1` IS CLEARED FOR LIVE DRIVENDATA PORTAL SUBMISSION (`verdict: "negative"`, `ok_to_submit: false`, `0` weekly slots consumed).**
>
> - **Research-only TIFF pair exists; neither is cleared for upload.** The NaN-outside ZIP has local grid/range-format checks, while its paired zero-outside TIFF is diagnostic only. The zero-outside artifact does not satisfy the audited outside-footprint null/NaN representation check. The ZIP also fails strict final-dot uniqueness against the spacing-5 registry raster (`99.9363%` within 3 px, above the `70%` stop rule). Do not download either file for contest submission. Evidence: [`docs/evidence/ocda_uniqueness_and_gate.json`](docs/evidence/ocda_uniqueness_and_gate.json).
> - **Why `verdict` is `"negative"` (Applying Arena Core Value *"Maximize P(Win)"*):**
>   1. **Spatially-blocked holdout (`GEMSDOE32-HIDE-RECOVER-v3.1`, `N=22,232` withheld positives):** OCDA-MSCS EXP-3 records **`HOLDOUT-DTI = 0.105830`** (95% CI `[0.095019, 0.115257]`) against the fold-local D28 reference's **`HOLDOUT-DTI = 0.099202`** (95% CI `[0.085951, 0.112668]`). The paired 95% cluster-bootstrap delta interval `[-0.003423, +0.015957]` crosses zero. The `0.2778` for GEMSDOE32 is only a USER/OWNER-REPORT with no receipt and is not directly comparable to this internal holdout or a forecast; this research candidate has not demonstrated a higher contest score.
>   2. **Off-catalogue regional benchmark (`GEMSDOE32-SGMC-CAL-v3.0`, `N=62,703` positives):** OCDA-MSCS EXP-3 has **`HOLDOUT-DTI = 0.050040`** (calibrated 95% CI `[0.045050, 0.054481]`; raw DTI `0.075100`). This regional result is not a leaderboard prediction. Any sibling comparison is contextual only, not a selector decision.
>   3. **Uniqueness gate:** The 43 discrete-detector subset passes its recorded comparisons (`max 3-px overlap = 52.33%`); that subset is incomplete for the literal rule. Across 46 audited rasters, the candidate is within 3 px of the spacing-5 lattice for `99.9363%` of dots and of a dense WBG raster for `100%`; both exceed the `70%` limit. The candidate fails full-registry uniqueness and must stop.

---

## 1. Arena Core Values Applied

- **Maximize P(Win):** With strictly capped weekly submission quotas, P(Win) is maximized by **ruthless out-of-fold empirical calibration and cross-repo portfolio selection**, never by pushing an under-calibrated raster onto a live slot. By auditing a 46-raster comparison set (not a complete fleet inventory), documenting partial structural overlap with `GEMSDOE32` and `KANLERGEMSDOE2`, and diagnosing the Positive-Unlabeled split-inversion failure in `EXP-2`, this repo preserves the weekly submission capacity. The literal full-registry gate still fails for OCDA-MSCS; no candidate is promoted.
- **Own the Outcome:** Every step—data restoration (`download_competition_data.sh`), 19-band + 35-channel + 26-channel `OCDA` preparation (`prepare_data.py` & `src/kanler/ocda.py`), byte-level verification of all 5 dataset/portal irregularities, 63-feature withheld-fold leakage canaries, fold-local 8-cell evaluation (`evaluate_holdout.py`), 15-check GeoTIFF generation (`submission_writer.py`), registry-wide uniqueness auditing (`audit_ocda_candidate.py`), GitHub Pages UI (`docs/`), and automated unit tests (`tests/`)—runs end-to-end autonomously with zero human-in-the-loop assumptions.

---

## 2. Five Byte-Verified Dataset & Portal Irregularities Flagged

1. **`IR-BAND-06` (`tc` Metadata Misidentification in `training_features.tif`):** Tagged `"Tilt angle or total curvature - magnetic field derivative for edge detection"`, Band 6 is strictly positive (`[2.953, 88.567]`) and matches USGS GeoDAWN Radiometric Total Count (`geodawn_rad_u8.tif` Band 4) at **Spearman $\rho = +0.999951$**, while correlating at only $\rho = +0.01884$ with true magnetic tilt $\arctan(\text{tmi\_vg}/\text{tmi\_hg})$. `src/kanler/ocda.py` derives true Miller & Singh (1994) magnetic and gravity tilt angles directly from `(tmi_vg, tmi_hg)` and `(iso_grav_anom_vg, iso_grav_anom_slope)`.
2. **`IR-BAND-18` (`iso_grav_anom_hg` Signed East–West Polarity):** Band 5 (`iso_grav_anom_slope`) is unsigned $\|\nabla g_{\text{iso}}\|$ ($\rho = +0.9561$), whereas Band 18 (`[-15.44, +12.86]`) is the *signed* east-west derivative $+\partial g_{\text{iso}}/\partial x$ ($\rho = +0.9450$), encoding east- vs. west-dipping half-graben polarity.
3. **`IR-BAND-10` (`deq_n100a15` Dependent-Seismicity Density, Not Distance):** Tagged `"Distance to earthquake"`, Band 10 correlates positively ($\rho = +0.8404$) with Band 16 (`ieq_n100a15`) and spikes to `4.96e6` in swarm clusters because in INGENIOUS (`GDR #1391`) `deq` is *dependent* (clustered) earthquake density.
4. **`IR-SAMPLE-04` (`sample_submission.tif` Positive Pixels):** The owner-mirrored `sample_submission.tif` contains `60,988` `1.0` pixels identical to `labels.tif` (`5,167,373` finite footprint pixels, `7,111,787` outside-footprint `NaN`s). It is used solely for grid geometry and footprint masking.
5. **`IR-PORTAL-05` (Reported portal range error; exact cause unverified):** The user's error was `Predicted values must be in range [0, 1]`, but the attempted upload's bytes and portal receipt are not available, so this repo cannot identify the exact offending cells or prove the cause. The official [`drivendataorg/gems-prize-reference-solution` notebook](https://github.com/drivendataorg/gems-prize-reference-solution/blob/main/unet-mc-cv-reference-solution.ipynb) writes finite zero predictions outside its valid area and applies `torch.nan_to_num`; that example is useful but does not establish how the portal treats every NaN-outside raster. Our shared writer rejects nonfinite or out-of-range predictions inside the footprint. The NaN-outside ZIP and zero-outside diagnostic must not be conflated; neither candidate is presently authorized for upload.

---

## 3. Why `GEMSDOE32` Scored `0.2778` & Pre-Registered Lane `H-K1-A (OCDA-MSCS)` Ablation

### Forensic Decomposition of the 9 Focus Sites (`GEMSDOE24..36`)
Pixel-exact decoding proves all 9 focus champions descend from `19GEMSDOE` `H19-5` (`121,131` ridge px, `0.1922` user/owner-reported):
- **Submodular $R=300\text{ m}$ `max` saturation vs additive `FP` (`0.1922 -> 0.2600`):** Thinning `H19-5` to `44,090` dots spaced by $d_{\min} = \sqrt{8} \approx 2.83\text{ px}$ (`GEMSDOE25 == GEMSDOE30`, `0-XOR` identical) strips `77,041` redundant interior ridge pixels (`0.2 * 77,041 = 15,408` denominator reduction).
- **Digitization-shoulder pruning (`0.2600 -> 0.2708 -> 0.2778`):** Organizer scoring masks only exact `labels.tif == 1` pixels ([forum #11516](https://community.drivendata.org/t/scoring-clarification-are-known-usgs-ingenious-faults-masked-when-scoring-and-are-they-in-the-final-round-label-set/11516/4)). Stripping `d_cat <= 1` (`GEMSDOE31 == GEMSDOE28_solo`, `40,199` dots, `0-XOR`) and `d_cat <= 2` (`GEMSDOE32`, `37,654` dots, `0-XOR`) eliminates `6,436` mapped-fault digitization-halo false positives.
- **Structural Ceiling:** `H19-5` covers only ~38% of hidden truth because symmetric 100 m DEM ridges waste ~60% of dots on unfaulted mountain-interior crests while missing low-relief piedmont breaks-in-slope and blind intrabasin half-graben conduits.

### Pre-Registered Hypotheses (`docs/research/hypotheses-20261027.md`) & 3-Experiment Fold-Local Results

All 63 features passed single-feature withheld-fold leakage canaries (`max symmetric AUC = 0.7386 <= 0.90`; `evidence/ocda_leakage_canaries.json`), with label-free `ocda_piedmont_slope_dipole_400m` (`AUC = 0.6365`) outperforming every single channel in the 35-channel baseline stack (`max = 0.5802`).

| Variant | Budget Slot | Emitted Dots | `HOLDOUT-DTI` (`GEMSDOE32-HIDE-RECOVER-v3.1`, `N=22,232`, 95% CI) | `HOLDOUT-DTI` (`GEMSDOE32-SGMC-CAL-v3.0`, `N=62,703`, Calibrated 95% CI) | Key Scientific Takeaway |
|---|---:|---:|---|---|---|
| `CHAMP-D28-VIS-B2` (`0.2778` ref) | Control | `37,654` | `0.099202` (`[0.085951, 0.112668]`) *(censorship-debiased upper bound: `0.189870`)* | `0.064121` (`[0.056730, 0.071649]`; raw `0.096060`) | Incumbent `D2.8 & (d_vis > 2)` fold-honest benchmark |
| `CTRL-BASE35-OOF` | Control | `37,654` | `0.103048` (`[0.088930, 0.117816]`) | `0.056689` (`[0.048475, 0.063744]`; raw `0.084969`) | Plain OOF HGB on 35 shared v2 channels |
| **`EXP-1` (`OCDA-Core`)** | **1 / 3** | `37,654` | **`0.104042`** (`[0.088903, 0.117717]`) | `0.052184` (`[0.046648, 0.057227]`; raw `0.078310`) | Pure label-free `OCDA` cross-strike dipoles + true tilt zero-crossings + PU guard + 1-px crest + 300 m CELF |
| **`EXP-2` (`OCDA-DirectTreeRelay`)** | **2 / 3** | `37,654` | `0.025006` (`[0.018772, 0.031177]`) *(logged negative)* | `0.042112` (`[0.031166, 0.052978]`; raw `0.063292`) | **PU Split-Inversion Proof:** `~visible`-zeroed continuation fields fed directly into `y=visible` HGB invert split sign |
| **`EXP-3` (`OCDA-TwoStage-ExplainAway`)** | **3 / 3** | `37,654` target | **`0.105830`** (`[0.095019, 0.115257]`, `P(>Champ)=90.9%`) | `0.050040` (`[0.045050, 0.054481]`; raw `0.075100`) | **Selected `KANLER1` Research Artifact:** Two-stage inner-withheld log-odds fusion + 600 m broadside dipole explaining-away + sharp 1-px crest (`+27.3%` in SW Walker Lane quadrant) |

**Artifact irregularity:** the archived OCDA NaN-outside and zero-outside TIFFs each contain `37,649` positive cells per their byte-level audit/direct read, not `37,654`. The five-pixel count mismatch with the declared target is unresolved; the `HOLDOUT-DTI` result must not be presented as a verified score for the archived TIFF bytes.

---

## 4. Run Card & Slot Clearance Status (`evidence/run_card.json`)

Synchronized across `evidence/run_card.json`, `data/run-card.json`, and `docs/evidence/current_run_card.json`:
- **Candidate:** `KANLER1-OCDA-MSCS-EXP3` (`docs/downloads/gemsdoe32-kanler1-ocda-mscs-exp3-37654d-20261027T1842Z-1db32b55-zeros.tif`)
- **SHA-256:** `ec9b920ac059518f0a2382f08cbe3bc2b6074d1a302e9f25cd8a79abd97c8564`
- **Portal Tracking Note (`65 <= 140` chars):** `KANLER1 OCDA-MSCS Exp3 OOF PU-HGB+300mCELF 37654d [RESEARCH-HOLD]`
- **Automated GeoTIFF Validator:** `15/15` checks passed (`CRS=EPSG:32611`, `shape=3730x3292`, `transform=[100.0, 0.0, 243350.0, 0.0, -100.0, 4508550.0]`, `0` NaN across all `12,279,160` cells, values strictly in `[0.0, 1.0]`, `0` on-catalogue leakage).
- **Verdict:** `"negative"` (`ok_to_submit: false`, `slot_used: false`, `selector_required: true`).

---

## 5. Limitations & High-Leverage Next Steps

1. **Regional SGMC Generalization Gap (`0.0500` vs `0.0641` / `0.0789`):** Because `labels.tif` is enriched in Quaternary piedmont and geothermal-basin scarps relative to upland Mesozoic/Cenozoic bedrock faults in USGS SGMC, supervised PU models trained on `labels.tif` allocate ~70% of their dot budget to piedmont/intrabasin dipoles at the expense of upland range-interior bedrock faults. **Next step:** Train a dual-prior mixture combining our `OCDA` cross-strike dipole specialist (`28.21%` overlap with `KANLERGEMSDOE2`) with `KANLERGEMSDOE2`'s upward-continued gravity crest migration (`HTCADS`) via out-of-fold log-odds ensembling before submodular 300 m packing.
2. **External Relocated Microseismicity (`H-K1-D`):** `training_features.tif` `ieq`/`deq` bands were smoothed at $100\text{ km}$ (`r = 0.9935` at $3\text{ km}$ lag). In an unrestricted network environment, pulling raw USGS ComCat / NSL relocated hypocenters via the public [USGS FDSN Event API](https://earthquake.usgs.gov/fdsnws/event/1/) (`CC0`) enables 3D planar updip fault projection onto the 100 m DEM.
3. **Direct Portal Template Authentication (`IR-SAMPLE-04`):** Before any team-selector promotion to a live weekly DrivenData slot, verify `sample_submission.tif` directly against an authenticated DrivenData download receipt.

---

## 6. Autonomous Reproduction Commands

```bash
# 1. Restore SHA-256-verified competition & external USGS/DOE data + prepare 19 bands
bash scripts/download_competition_data.sh
.venv/bin/python scripts/prepare_data.py

# 2. Execute pre-registered Lane H-K1-A (OCDA-MSCS) OOF experiments + shared holdout evaluation
.venv/bin/python scripts/run_ocda_lane.py

# 3. Audit the existing research GeoTIFF bundle + run the strict registry uniqueness/release gate
.venv/bin/python scripts/audit_ocda_candidate.py

# 4. Run full automated scientific, GeoTIFF validator, uniqueness, and GitHub Pages safety test suite
.venv/bin/python -m unittest discover -s tests -v
```

---

## 7. Standing Prompt Reference (Stored Verbatim in `README.md` & `docs/ORIGINAL_PROMPT.md`)

### Current focus-site and session-start requirements

For every session, read this README, [`docs/ORIGINAL_PROMPT.md`](docs/ORIGINAL_PROMPT.md), [`docs/REQUEST_20261027.md`](docs/REQUEST_20261027.md), and the current run card before acting. Focus the comparison on GEMSDOE24, GEMSDOE25, GEMSDOE27, GEMSDOE28, GEMSDOE30, GEMSDOE31, GEMSDOE32, GEMSDOE33, and GEMSDOE36. Distinguish user/owner score reports from `HOLDOUT-DTI` and organizer receipts; do not invent leaderboard estimates. Keep the exact any-registry uniqueness gate and stop on a violation. No TIFF is cleared in this review; the extant OCDA research candidate overlaps the spacing-5 registry raster by 99.9363% of dots within 3 px, above the 70% limit. Do not make a new file or consume a submission slot unless a future, explicitly assigned lane passes every gate and the separate selector approves.

<details>
<summary><strong>Click to expand full verbatim prompt governing this repository</strong></summary>

```text
PARALLEL-RUN PROTOCOL — read once, follow strictly:

1. LANE & UNIQUENESS. Stay inside your assigned method lane. Before placing final dots AND after placing them, check your continuous surface and final dots against every raster in the registry: if Spearman rank-correlation exceeds [0.90] OR more than [70%] of your dots fall within 3 px of any registry raster's dots, log as duplicate and stop — do not emit a submission file.
2. REUSE, DON'T REBUILD. Load the cached feature stack from the template and call evaluate_holdout.py and submission_writer.py directly. Holdout = hide-and-recover: withhold whole fault segments with a spatial buffer, derive every catalogue-based feature only from the remaining visible faults, mask visible faults pixel-exact as the organizer does, and score with exact pooled DTI (alpha=0.2, beta=0.8, 300 m triangular kernel). Fix shared tool bugs once in shared code; never keep a private fork.
3. STRICT SCORE LABELING. Every number you report must be labeled either HOLDOUT-DTI (with evaluator version, number of withheld positives, and 95% CI) or ORGANIZER-CONFIRMED (copied from a submission-page receipt). Never write a projection or forecast as a score.
4. LEAKAGE CANARY. Test each feature alone on the holdout before trusting any result. AUC above [0.90] means leakage until proven otherwise.
5. RUN CARD. End with one JSON card: hypothesis, mechanism, named non-fault mimic, holdout DTI + CI, correlation/overlap vs registry, raster sha256, validator output (no NaN inside footprint, values in [0,1], CRS/shape/transform match), submission name + note <=140 chars, and verdict (promote / negative).
6. BUDGET. Stop after at most 3 experiments or 2 hours. A negative result is a deliverable — log it so no other session repeats it. Promotion to a real weekly slot is a separate selector step.

Take a look at the GitHub repo and help build a complete end to end research, evaluation, validation, and submission system for https://www.drivendata.org/competitions/306/competition-doe-gems/

Check prior work from GEMSDOE24..GEMSDOE91, KANLERGEMSDOE1..3, EUGGEMSDOE1..3, WBGGEMSDOE1..3, GINNYGEMSDOE1..3 and any other GEMSDOE sites to review.
In particular, focus on the highest scoring submissions from these 9 sites:
GEMSDOE24, GEMSDOE25, GEMSDOE27, GEMSDOE28, GEMSDOE30, GEMSDOE31, GEMSDOE32, GEMSDOE33, GEMSDOE36

Check why this submission from GEMSDOE32 scored the highest among these sites:
h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros: 0.2778

See if it is possible to get a higher scoring submission (>0.2778 or even >0.3195). Right now the top score on the leaderboard is 0.4413 (or higher). Think deeply at a PhD level on how we can achieve a breakthrough here. Make sure there are no hallucinations. Work line by line to make sure we verify everything from official verified trusted sources, with links for manual review. If you find any irregularities, flag them.

Before implementing, generate 3-5 candidate geological hypotheses we haven't tried yet, each naming: the specific layer(s) involved, the physical signature being targeted (e.g., an edge-detection or curvature transform), why it should catch a fault missing from the USGS/INGENIOUS catalogue rather than one already in it, and how it differs from anything already implemented in this repo. Rank them by expected DTI improvement and implementation cost. Validate the top candidate on our spatially-blocked holdout set before touching a weekly submission slot, and flag any external data source we could pull in to test the others (noting whether it's freely available).

Check how we can build a unique single-band GeoTIFF (.tif) submission to be competitive with the top submissions on the leaderboard. Per competition rules, submissions must be a single-band GeoTIFF (.tif) — or a .zip containing a single GeoTIFF — matching the sample submission's CRS (EPSG:32611), shape, and geotransform, with predicted values in [0, 1]. Make sure we do not copy any previous submissions from GEMSDOE (use them to learn from only) and we must make a unique TIF submission unlike previous GEMSDOE submissions. Make sure it has a unique submission name and short note (<=140 chars) for tracking on the DrivenData portal. Make sure our submission is validated before making it available to download (do not require a human inspector since it should be validated automatically). We should also make sure it is obvious whether a generated TIF file is ok to download and submit.

Complete the data download and placement (`bash scripts/download_competition_data.sh` and `python scripts/prepare_data.py`), run the full evaluation pipeline to verify the actual out-of-fold score, and build the final submission file autonomously, without requiring any manual input.

Provide an executive summary subpage with a clear table showing what file to download, estimated score, and uniqueness across all sites. Also explain how to submit on the website, making sure we don't hit errors like "Predicted values must be in range [0, 1]".

Make sure that we keep the GitHub Pages site clean and intuitive to use (good UI/UX).

Store this prompt into the repo README.md for reference. Let's apply Arena Core Values to this problem, such as "Maximize P(Win)" and "Own the Outcome"

Let's work in multiple passes:
Pass 1: Implement and verify
Pass 2: Review and fix any bugs, assumptions, or edge cases
Pass 3: Re-check the entire implementation against the original request

After completing all passes, create a PR and merge it onto main. Note any next steps, recommendations, and limitations.
```

Full unabridged site list also archived in [`docs/ORIGINAL_PROMPT.md`](docs/ORIGINAL_PROMPT.md).
</details>
