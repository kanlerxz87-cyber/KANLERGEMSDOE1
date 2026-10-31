# `KANLERGEMSDOE1` — DOE GEMS Prize Research, Fold-Local Validation, Uniqueness & Submission Gate System

[![Competition](https://img.shields.io/badge/DrivenData-DOE_GEMS_Prize_(306)-d08a4c)](https://www.drivendata.org/competitions/306/competition-doe-gems/)
[![Download Verdict](https://img.shields.io/badge/Download_verdict-NO_FILE_CLEARED-red)](docs/submit-now.html)
[![Tests](https://img.shields.io/badge/Automated_Gate_Tests-See_current_review-lightgrey)](docs/review-2026-10-31.md)

End-to-end geological feature engineering, fold-local hide-and-recover evaluation, multi-site uniqueness audits, automated GeoTIFF validation, and GitHub Pages research desk ([Executive summary](docs/executive-summary.html) · [Focus-site scorecard](docs/focus-sites-review-20261028.html) · [Submission readiness](docs/submit-now.html) · [Latest review](docs/review-2026-10-31.md)) for the [**DOE Geothermal Exploration Machine Learning (GEMS) Prize**](https://www.drivendata.org/competitions/306/competition-doe-gems/).

**Project-start rule:** Before every research or implementation session, read this README's standing prompt, [`docs/ORIGINAL_PROMPT.md`](docs/ORIGINAL_PROMPT.md), and the latest dated review. Apply the literal parallel-run gates; do not silently waive the raster uniqueness rule, spend a submission slot, or treat a projection as a score. If evidence is incomplete, fail closed and document the limitation.

---

## 0. START HERE — Submission decision (reviewed 2026-10-31)

> **STOP — NO TIFF IS CLEARED TO DOWNLOAD AND SUBMIT.** The existing UWBP-DRCS TIFF is a historical research artifact, not a recommended submission. It fails the literal registry overlap gate, its recorded HIDE-RECOVER result is below the recorded benchmark, the full peer registry is incomplete, and the local template is not authenticated from DrivenData.
>
> - **Research artifact (do not submit):** `docs/downloads/gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif`, SHA-256 `2693c2daf87bd7948d3d57fc41fdcf40653ef42014c93d0e947bc2a8fc00a30c`. The local GeoTIFF format/range validator passed; that is not scientific clearance or organizer acceptance.
> - **Literal uniqueness gate:** fails; historical raster audit records 99.976% within 3 px of a space-filling calibration reference. The detector-only view is not an allowed waiver of the prompt's literal rule.
> - **HOLDOUT-DTI:** HIDE-RECOVER-v3.1 = 0.064800 (22,232 withheld positives; 95% CI [0.057434, 0.071809]) for UWBP-DRCS, versus the recorded D2.8/B2 benchmark 0.099202 ([0.085951, 0.112668]). These are repository lane results, not organizer scores, and were not rerun in this review.
> - **Organizer score estimate: unavailable.** There is no submission receipt for this raster. Earlier proxy-to-leaderboard projections are withdrawn as unsupported forecasts.
> - **Experiments and slots:** no new experiment or contest slot used in this review. The UWBP lane has already used its three-experiment budget. No new TIFF was generated because the required stop conditions fail.

This README contains a standing prompt archive below. At the project start, read the full original request plus this dated decision; do not rely on old green banners or old generated artifacts. The current nine-site historical comparison is [`docs/focus-sites-review-20261028.html`](docs/focus-sites-review-20261028.html); its scores are user/owner reports, not receipts.

## 1. Six Byte-Verified Dataset & Portal Irregularities Flagged

1. **`IR-BAND-06` (`tc` Metadata Misidentification in `training_features.tif`):** Tagged `"Tilt angle or total curvature - magnetic field derivative"`, Band 6 (`[2.953, 88.567]`) matches USGS GeoDAWN Radiometric Total Count (`geodawn_rad_u8.tif` Band 4) at **Spearman $\rho = +0.999951$** ($\rho = +0.01884$ vs true magnetic tilt).
2. **`IR-BAND-18` (`iso_grav_anom_hg` Signed East–West Polarity):** Band 5 (`iso_grav_anom_slope`) is unsigned $\|\nabla g_{\text{iso}}\|$ ($\rho = +0.9561$), whereas Band 18 (`[-15.44, +12.86]`) is signed $+\partial g_{\text{iso}}/\partial x$ ($\rho = +0.9450$), encoding east- vs. west-dipping half-graben polarity.
3. **`IR-BAND-10` (`deq_n100a15` Dependent-Seismicity Density & 100 km Smoothing):** Tagged `"Distance to earthquake"`, Band 10 is INGENIOUS *dependent* earthquake density ($\rho = +0.8404$ with Band 16 `ieq_n100a15`; spatial autocorrelation $r = 0.9935$ at $3\text{ km}$ lag).
4. **`IR-BAND-17` (`cond_surf` Decade Log-Resistivity Scale):** Spans `[0.194, 4.969]` (median `2.886`) — already in decade $\log_{10}\rho$ units rather than linear S/m or $\Omega\cdot\text{m}$.
5. **`IR-SAMPLE-04` (`sample_submission.tif` Unauthenticated Mirror & Positive Pixels):** Contains `60,988` `1.0` pixels identical to `labels.tif` plus `7,111,787` outside-footprint `NaN`s (`organizer_template_authenticated: false`).
6. **`IR-PORTAL-05` (`Predicted values must be in range [0, 1]` Safeguards):** `58,171` in-footprint `-3.4028235e+38` sentinels in raw bands are sanitized by `prepare_data.py`; `submission_writer.py` validates both `-nan.tif` and `-zeros.tif` across 15 automated checks (`0` in-footprint `NaN`/`Inf`/sentinels, values strictly in `[0.0, 1.0]`).

---

## 2. Why `GEMSDOE32` Scored `0.2778` & Multi-Lane Fold-Local Ablation Summary

Pixel-exact decoding (`evidence/focus_forensics_20261028.json`, `docs/focus-sites-review-20261028.html`) proves all 9 focus champions (`GEMSDOE24..36`, user/owner reports, not organizer receipts) descend from `19GEMSDOE` `H19-5` (`121,131` px): `d_min = √8` thinning (`44,090` px in `GEMSDOE25 == GEMSDOE30`, `0.2600`) strips `77,041` redundant interior ridge pixels inside the $R=3.0\text{ px}$ `max` kernel, and `B=2` collar pruning (`GEMSDOE32`, `37,654` px, `0.2778`, `0-XOR` to `D2.8 & (EDT(~labels) > 2)`) removes `6,436` mapped-fault digitization-halo false positives ([forum #11516](https://community.drivendata.org/t/scoring-clarification-are-known-usgs-ingenious-faults-masked-when-scoring-and-are-they-in-the-final-round-label-set/11516/4)). Because `H19-5` captures only ~38% of hidden truth (`|G| ≈ 13.7k`), surpassing `0.32+` requires subsurface + piedmont discovery without coordinate overfitting:

| Variant | Lane & Slot | Emitted Dots | `HOLDOUT-DTI` (`GEMSDOE32-HIDE-RECOVER-v3.1`, `N=22,232`, 95% CI) | `HOLDOUT-DTI` (Zero-SGMC `GEMSDOE32-SGMC-CAL-v3.0`, `N=62,703`, 95% CI) | Scientific Takeaway |
|---|---|---:|---|---|---|
| `CHAMP-D28-VIS-B2` (`0.2778` ref) | Anchor | `37,654` | `0.099202` (`[0.085951, 0.112668]`) | `0.064121` (`[0.056730, 0.071649]`; raw `0.096060`) | Incumbent `D2.8 & (d_vis > 2)` fold-honest benchmark |
| `OCDA-EXP3` (2026-10-27) | `H-K1-A` (3/3) | `37,649` | **`0.105830`** (`[0.095019, 0.115257]`, `#1` HR) | `0.050040` (`[0.045050, 0.054481]`; raw `0.075100`) | Leads Quaternary catalogue HR; coordinate bands suppress upland SGMC |
| `UPFLOW-EXP2` (2026-10-28) | `UPFLOW` (2/3) | `37,654` | `0.057717` (`[0.049718, 0.064828]`) | `0.045464` (`[0.038395, 0.053052]`) | Rules out far-field alignment corridors without worm back-projection |
| **`EXP-B1` (`UWBP-Deconf-PU`)** | `UWBP` (**1/3**) | `37,649` | `0.057902` (`[0.051042, 0.064541]`) | **`0.088558`** (`[0.080972, 0.094641]`; raw `0.131830`) | 2D DCT-II Poisson worms + $55^\circ$ up-dip + hard coordinate removal (`+77%` vs `OCDA`) |
| **`EXP-B2` (`UWBP-DRCS-Dual`)** | `UWBP` (**2/3**) | `37,646` | `0.064581` (`[0.057262, 0.071741]`, `+11.5%` vs B1) | **`0.090111`** (`[0.082001, 0.096680]`; raw `0.134102`, `#1` SGMC) | Stage-2 continuation + Dual-Regime `M_struct` sets all-time repo zero-SGMC record (`+40.5%` vs `G32`) |
| **`EXP-B3` (`UWBP-DRCS-Dinkelbach`)** | `UWBP` (**3/3**) | `37,647` | **`0.064800`** (`[0.057434, 0.071809]`, `+11.9%` vs B1) | **`0.089174`** (`[0.081232, 0.095645]`; raw `0.132733`) | Strike-steered hydrothermal conduits + Dinkelbach 300 m CELF (`58/58` discrete detectors PASS) |

---

## 3. Limitations & High-Leverage Next Steps

1. **Split-Budget Two-Population Pareto Synthesis:** `OCDA-MSCS EXP-3` (`0.105830` HR) and `UWBP-DRCS EXP-B2/B3` (`0.090111` SGMC) share only **`24.05%`** 3-px dot overlap (`Spearman \rho = 0.0502`). Packing `~24,000` Quaternary piedmont/relay dots with `~13,654` strictly disjoint (`> 3 px`) deconfounded worm/knickzone dots via joint 300 m CELF targets simultaneous superiority on both `HIDE-RECOVER-v3.1` and `SGMC-CAL-v3.0`.
2. **External Relocated Hypocenters & InSAR (`H-K1-B4` & `H-K1-B5`):** In an unrestricted network environment, ingesting relocated 3D hypocenters from [USGS ANSS ComCat](https://earthquake.usgs.gov/fdsnws/event/1/) and InSAR phase-velocity steps from [NASA ASF OPERA](https://search.asf.alaska.edu/) unlocks blind seismogenic shear zones and flat-playa groundwater barriers.
3. **Authenticated Organizer Template & Registry Policy:** Before any separate team-selector promotion to a weekly DrivenData slot, verify `sample_submission.tif` against a direct authenticated portal receipt and reconcile treatment of the non-detector `r13-lattice-s5_v2` calibration grid.

---

## 4. Autonomous Reproduction Commands

```bash
bash scripts/download_competition_data.sh
.venv/bin/python scripts/prepare_data.py
.venv/bin/python scripts/run_uwbp_lane.py
.venv/bin/python scripts/audit_uwbp_candidate.py
.venv/bin/python scripts/build_executive_summary.py --check
.venv/bin/python scripts/build_readiness_report.py --check
.venv/bin/python scripts/restore_focus_sites.py            # 9 focus TIFFs, SHA-256 pinned
.venv/bin/python scripts/audit_unique_candidates.py        # uniqueness vs 23 local references
.venv/bin/python scripts/calibrate_proxy_vs_organizer.py   # proxy vs user-reported ledger
.venv/bin/python scripts/build_candidate_scoreboard.py     # SGMC-CAL re-run + projection (labelled)
.venv/bin/python scripts/validate_submission_file.py docs/downloads/gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif
.venv/bin/python scripts/build_submit_page.py --check      # submit page + executive block
.venv/bin/python -m unittest discover -s tests -v
```

---

## 5. Standing Prompt Reference (Stored Verbatim in `README.md`, `docs/ORIGINAL_PROMPT.md` & `docs/REQUEST_20261027.md`)

<details>
<summary><strong>Click to expand full prompt governing this repository</strong></summary>

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

Full unabridged multi-site prompt & score ledgers are also archived verbatim in [`docs/ORIGINAL_PROMPT.md`](docs/ORIGINAL_PROMPT.md), [`docs/ORIGINAL_PROMPT_20261027.md`](docs/ORIGINAL_PROMPT_20261027.md), and [`docs/REQUEST_20261027.md`](docs/REQUEST_20261027.md).
</details>
