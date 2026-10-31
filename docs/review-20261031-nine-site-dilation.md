# Review 2026-10-31: nine-site summary, KANLER1 candidate, and dilation experiment

> **Status: HOLD. No file is cleared for submission.** This review agrees with the fail-closed decision in [`review-20261031.md`](review-20261031.md) and the blocker in [`review-20261031-labels.md`](review-20261031-labels.md). The candidate below is format-valid and unique under the detector-only rule, but its only holdout evidence is a proxy, and its labels inputs are not verified (blocker B1). Submitting it now is not recommended.

Every number below carries one of these labels:

- **HOLDOUT-DTI (proxy)**: our evaluator, with the evaluator version, withheld-positive count, and 95% CI.
- **USER/OWNER-REPORT**: a score claimed by a site or user. No submission-page receipt was seen.
- **ORGANIZER-CONFIRMED**: none exists for any file in this repository.
- **PROJECTION**: a fitted extrapolation. It is never a score.

## 1. Decision at a glance

**Candidate file (HOLD, not cleared, not published): `docs/downloads/gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif`** (the file exists in the repository; it is not a published download)

| Question | Answer |
|---|---|
| Download it? | Available as a format-valid artifact for review. Not cleared. |
| Submit it? | **NO. HOLD.** Blocked by B1 (labels identity) and by the unresolved uniqueness-rule decision (I4). |
| Organizer score | **UNKNOWN.** No portal receipt exists. |

| Item (for when the hold is lifted) | Value |
|---|---|
| Name for the portal | `kanler1-uwbp-drcs-exp3-37647d-nan` |
| Note (≤140 chars) | `KANLER1 UWBP-DRCS EXP3 worm+Dinkelbach 37647 dots NaN-outside; SGMC-CAL proxy 0.0892 (not organizer score)` |
| SHA-256 | `2693c2daf87bd7948d3d57fc41fdcf40653ef42014c93d0e947bc2a8fc00a30c` (re-checked today) |
| Format (automated, no human) | PASS on all 10 checks: single-band float32 GeoTIFF, EPSG:32611, 3730×3292, template transform, NaN outside footprint, no NaN inside, values in [0, 1], footprint identical to template |
| Unique? | Detector-only rule: **PASS** against 23 references (9 focus sites + 14 local). Worst non-space-filling 3-px overlap 33.8% (`8GEMSDOE_Hedge-v2`); max \|ρ\| 0.0064. Literal rule: **FAIL** only because of the r13 lattice (covers ≥70% of footprint). See irregularity I4. |
| Organizer score | **UNKNOWN.** Only the portal receipt can establish it. |
| Estimated score | HOLDOUT-DTI proxy, SGMC-CAL-v3.0, n = 62,703, 95% CI `[0.081246, 0.095651]` = **0.089182** (see I1: the calibration is fitted to the same ledger, so this is weak evidence). PROJECTION `0.405` (band 0.389–0.421) is an extrapolation and is not a score. |

**Before any upload:** B1 must be resolved by comparing the official DrivenData files with the mirror (the labels identity problem), and the team must decide on I4. Only then would a single final selection be considered. The agent did not upload anything and cannot. Official rules: choose one final submission before the deadline (S2, §3.5).

**What this does not establish:** that the file beats 0.2778, 0.3195, or the current top score. It is the best unique file this repository can produce, and it beats the 0.2778 champion on both of our SGMC proxies. The organizer's private set is unknown.

## 2. Nine-site executive table

Source: `evidence/focus_sgmc_reproduction_20261031.json` (SGMC-CAL recomputed today from the pinned bytes, with the shared evaluator). All nine files were restored from pinned GitHub commits and verified by SHA-256 (`scripts/restore_focus_sites.py`).

| Site | Best file to submit? | Reported score | SGMC-CAL proxy (HOLDOUT-DTI, n=62,703) | Unique vs other GEMSDOE sites? | Verdict |
|---|---|---|---|---|---|
| GEMSDOE24 | **No** (another team's file) | 0.2477 (USER/OWNER-REPORT) | 0.057932 | Different dot count (60,069) from every other focus file | Do not submit |
| GEMSDOE25 | **No** | 0.2600 (USER/OWNER-REPORT) | 0.060592 | **Same 44,090 dots as GEMSDOE30 and registry `d28`**, different bytes | Do not submit; duplicate content |
| GEMSDOE27 | **No** | 0.2449 (USER/OWNER-REPORT) | 0.058262 | Not checked pairwise | Do not submit |
| GEMSDOE28 | **No** | 0.2710 (USER/OWNER-REPORT) | 0.062967 | Not checked pairwise | Do not submit |
| GEMSDOE30 | **No** | 0.2600 (USER/OWNER-REPORT) | 0.060592 | **Same dots as GEMSDOE25** | Do not submit; duplicate content |
| GEMSDOE31 | **No** | 0.2708 (USER/OWNER-REPORT) | 0.063010 | Not checked pairwise | Do not submit |
| GEMSDOE32 | **No** (zeros-outside; see I2) | 0.2778 (USER/OWNER-REPORT) | 0.064121 `[0.056730, 0.071649]` | n/a (reference) | Do not submit |
| GEMSDOE33 | **No** | 0.2632 (USER/OWNER-REPORT) | 0.062551 | Not checked pairwise | Do not submit |
| GEMSDOE36 | **No** | 0.2750 (USER/OWNER-REPORT) | 0.064444 | Not checked pairwise | Do not submit |
| **KANLER1 (this repo)** | **Candidate only (HOLD)** | None (not submitted) | **0.089182** `[0.081246, 0.095651]` | Yes, detector-only (section 1) | **HOLD; not cleared** |

Notes on the table:

- The "Not checked pairwise" entries mean only that the pairwise overlap was not computed today. Hash-level uniqueness is not enough, as the GEMSDOE25/30 pair shows.
- On the raw SGMC metric (no calibration), the nine focus files cluster between 0.094 and 0.102. The KANLER1 file scores 0.132736 `[0.124812, 0.139178]`, against 0.096060 `[0.085660, 0.107072]` for GEMSDOE32. All are HOLDOUT-DTI (proxy).
- The focus files are other teams' submissions. The prompt says do not copy them, so they are listed for learning only.

## 3. Why GEMSDOE32 (0.2778) scored highest, and whether 0.2778 can be beaten

**Mechanism (what the evidence supports):**

1. The official rule masks known USGS/INGENIOUS faults pixel-exact. Pixels on known faults count for nothing. A predicted pixel that is near a known fault but far from any new-fault truth pixel is **fully penalised**. The 300 m buffer does not apply to known faults. DrivenData staff confirmed this in the forum thread (see sources, S3).
2. Under that rule, the mapped-fault digitisation halo is pure false-positive mass. The GEMSDOE32 construction removes it with a 2-px collar prune (`D2.8 & (EDT(~labels) > 2)`, which removes 6,436 pixels). Repo forensics (`evidence/focus_forensics_20261028.json`) decode the other focus files as nested variants of the same H19-5 ridge set, so this is the main difference.
3. Thinning to a minimum spacing of √8 px (D2.8) removes redundant interior ridge pixels, which would otherwise be false positives inside the kernel.

**Why it is only 0.2778 and not higher:** the dot set covers only a small part of the true new-fault set. The repo's calibration constant is 12,691 px of hidden truth (`src/gems32/holdout.py`), while the README gives about 13.7k (see I1). The README also says H19-5 captures about 38% of that set (repo-reported, not re-verified today). Pruning and thinning improve precision but cannot create recall.

**Can we beat 0.2778?** On our proxies, yes:

- KANLER1 UWBP-DRCS EXP3 (the download) beats GEMSDOE32 on calibrated SGMC (0.0892 vs 0.0641) and on raw SGMC (0.1327 vs 0.0961). Both are HOLDOUT-DTI (proxy). This does not establish an organizer score.
- The organizer score of KANLER1 is unknown. The proxies have known weaknesses (irregularities I1 and I3).

**Experiment log (budget 1 of 3):** we tested whether 1-px dilation helps under the official β = 0.8 > α = 0.2 asymmetry (hypothesis, mechanism, and named mimic are in `evidence/run_card_20261031_dilation.json`).

| Variant | Emitted px | SGMC-CAL (HOLDOUT-DTI) | SGMC raw (HOLDOUT-DTI) | Uniqueness (detector-only) |
|---|---:|---|---|---|
| V0 base (download) | 37,647 | **0.089182** `[0.081246, 0.095651]` | 0.132736 `[0.124812, 0.139178]` | PASS, worst 3-px 33.8% |
| V1 cross-1px dilation | 188,232 | 0.063669 `[0.055642, 0.071231]` | **0.170749** `[0.156270, 0.182440]` | PASS, worst 3-px 33.8% |
| V2 square-1px dilation | 338,796 | 0.049443 `[0.042751, 0.055903]` | 0.162937 `[0.146364, 0.177434]` | PASS, worst 3-px 33.8% |

Verdict: **negative for dilation under the calibrated proxy, positive under the raw proxy.** The proxies disagree because they assume different hidden-truth sizes (12.7k vs 62.7k px). The organizer's size is unknown, so this experiment cannot promote a variant. V1 is kept as a **probe** only (not in `docs/downloads/`). The team can test it on the portal's feedback submissions (up to three per week), which is the only way to resolve the question.

## 4. Verification performed today

- Core data (`training_features.tif`, `labels.tif`, `sample_submission.tif`) restored from the pinned GitHub mirror through `scripts/restore_data.py`. The SHA-256 values match `registry/data_manifest.json`. They are **owner mirrors, not DrivenData downloads** (I5).
- Dependencies installed into `.venv` from `requirements.txt` (PyPI).
- `python -m unittest discover -s tests`: **77 tests, all pass.**
- `build_executive_summary.py --check`, `build_readiness_report.py --check`, `build_submit_page.py --check`: all pass.
- Reproduction: the recommended file gives SGMC-CAL 0.0891815 (repo: 0.089182); the 0.2778 champion gives 0.064121 (repo: 0.064121). Both match.
- Shared-tool fix (see I9): `scripts/evaluate_holdout.py` rejected any NaN-outside file, which is the official format, so the portal file could not be scored. The check now requires binary finite values inside the footprint and NaN or 0 outside it. Strictness inside the footprint is unchanged.

## 5. Irregularities flagged for review

- **B1 (from `review-20261031-labels.md`, verified again today) Labels identity.** `labels.tif` and `existing_faults.tif` are byte-identical (SHA-256 `7ba308cc…4093`). The mirror's `sample_submission.tif` contains exactly the same 60,988 positive pixels, although the official page says the sample "predicts total fault absence" (S1). Any holdout reading these files is suspect until the official files are compared.
- **I1 Circular calibration.** `ESTIMATED_LB_HIDDEN_TRUTH_PX = 12691` in `src/gems32/holdout.py` has the comment "Calibrated from blind lattice-s5 (0.0904) & h19-5->d1.5->d2.8". Those are the same leaderboard-ledger values the calibration is then "validated" against. The repo's claim that SGMC-CAL tracks the ledger with r = 0.988 is therefore in-sample, not independent validation. The README states |G| ≈ 13.7k while the code uses 12,691; reconcile them.
- **I2 Zeros-outside champion vs official format.** The official page says "data outside the bounds is null or nan" (S1). The 0.2778 champion (`gemsdoe32-h33-…-zeros.tif`) is zeros-outside, yet it is reported at 0.2778. Either the portal accepted zeros, or the reported file differs from the one in `docs/downloads/`. This must be resolved. We do not rely on it.
- **I3 Projection is not a score.** The 0.405 PROJECTION is a linear fit on 12 user-reported points plus a circular proxy (I1), and it lies outside the fitted range. Do not quote it as an estimate of the leaderboard.
- **I4 Literal uniqueness rule fails for every candidate.** The r13 lattice covers ≥70% of the footprint, so a random dot is within 3 px of it. The "detector-only" exclusion is the repo's own decision, not an official rule. The team must decide whether to accept it.
- **I5 Data provenance.** The training features and labels come from third-party GitHub repositories (`buffedlizard55-lab/GEMSDOE` and `…/GEMSDOE24`), not from DrivenData. The DrivenData data page is login-walled (the repo reports this; the sandbox could not reach drivendata.org's data page today to re-check). The hashes prove mirror consistency only. Also check the DrivenData terms before redistributing the mirrored competition files.
- **I6 Inconsistent validator claims.** The README says "15-check" validation, `submission_writer.py` says "13-check", and the validator emits 10 checks. All 10 pass. Reconcile the documentation.
- **I7 Generative-AI disclosure is required.** The official rules (§3.2) require stating in the narrative the extent to which generative AI was used. This repository was built with AI agents. The user must include this disclosure.
- **I8 Leaderboard values conflict.** The prompt cites 0.4413 and 0.3195. The live leaderboard fetched today shows #1 = 0.4544 and #2 = 0.3925 (public-test). The 0.4413 and 0.3195 figures could not be matched to any row (S4).
- **I13 Mixed statuses in main.** `review-20261031-labels.md` says "Yes, as a format-valid artifact" for download, while the top-level README and `review-20261031.md` say no file is cleared. This review follows the stricter reading: no clearance, download is for inspection only.
- **I9 Shared-tool bug, fixed.** `scripts/evaluate_holdout.py` rejected the official NaN-outside format in its diagnostic path. Fixed in place today. It was not a private fork.
- **I10 Root cause of the portal error "Predicted values must be in range [0, 1]" is unconfirmed.** A plausible hypothesis is that the raw training bands contain float32 sentinels (`-3.4028235e+38`). The README reports 58,171 such in-footprint sentinels in the raw bands, and the prepared rasters sanitise them. This is a hypothesis, not a diagnosis. The files here contain no such values.
- **I11 Hash-level uniqueness is not enough.** GEMSDOE25 and GEMSDOE30 have identical dot sets with different bytes (section 2).
- **I12 Restore receipts are provenance-labelled.** `data/restore_receipt*.json` record `owner-hosted mirror; not organizer-authenticated`. This is correct.

## 6. Official sources (for manual review)

- S1. DrivenData problem description, performance metric and submission format (the "null or nan" outside rule, values in [0, 1]): https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/
- S2. GEMS Prize official rules PDF (single 100 m layer; up to 3 feedback submissions per week; one final selection; generative-AI disclosure in §3.2): https://docs.nlr.gov/docs/fy26osti/96647.pdf
- S3. DrivenData forum, staff answers on known-fault masking (pixel-exact; buffer does not apply to known faults): https://community.drivendata.org/t/scoring-clarification-are-known-usgs-ingenious-faults-masked-when-scoring-and-are-they-in-the-final-round-label-set/11516/4
- S4. DrivenData leaderboard (live, fetched 2026-10-31): https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/
- S5. DrivenData competition overview: https://www.drivendata.org/competitions/306/competition-doe-gems/
- S6. DrivenData reference solution: https://github.com/drivendataorg/gems-prize-reference-solution
- S7. GeoDAWN data release (USGS, DOI 10.5066/P93LGLVQ): https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and
- S8. INGENIOUS dataset (DOI 10.15121/1881483): https://doi.org/10.15121/1881483
- S9. EPSG:32611 (UTM 11N): https://epsg.io/32611
- S10. Tversky index background: https://en.wikipedia.org/wiki/Tversky_index

Evidence files: `evidence/validation_gemsdoe32-kanler1-uwbp-drcs-exp3-…-nan.json` (base), `evidence/validation_V1_dilate_cross1px.json`, `evidence/uniqueness_audit_20261029.json`, `evidence/focus_sgmc_reproduction_20261031.json`, `evidence/reproduction_champion_0.2778_20261031.json`, `evidence/experiment_dilation_20261031.json`, `evidence/run_card_20261031_dilation.json`, `evidence/leaderboard_snapshot_20261031.json`.

## 7. Next steps (ordered, with owners)

1. **User (blocking):** compare the official DrivenData `labels.tif` and `existing_faults.tif` with the mirror (B1), and decide on the literal-vs-detector uniqueness rule (I4). Only after both, and only if the team selects this file as its single final submission, upload it with the name and note above. Record the portal receipt; that is the first ORGANIZER-CONFIRMED number.
2. **User (after B1 is resolved):** use one feedback slot on probe V1 (`data/experiments/V1_dilate_cross1px.tif`, regenerated by `scripts/experiment_dilation_variants.py`). This settles the truth-size question (I1, section 3) with the organizer's own scorer.
3. **User (authenticated):** download the competition files from DrivenData on an unrestricted machine and compare SHA-256 values with `registry/data_manifest.json` (I5).
4. **Team:** resolve the zeros-outside champion question (I2) and reconcile the validator counts (I6).
5. **Team:** before any final selection, add the generative-AI disclosure (I7).
6. **Agent (next session, budget not yet used):** replace the single fitted calibration constant with an independent estimate of hidden-truth size, and add pairwise uniqueness across all nine focus files (I11).

## 8. Run card (summary of the experiment; verdict HOLD for all files)

Full JSON: `evidence/run_card_20261031_dilation.json`. Summary: hypothesis = dilation raises score under β > α; mechanism = FN weighted 0.8, FP 0.2; named mimic = mapped-fault digitisation halo; holdout = V0 0.089182 `[0.081246, 0.095651]` (calibrated) and 0.132736 `[0.124812, 0.139178]` (raw), n = 62,703; overlap vs registry = 33.8% (3-px, detector-only), |ρ| ≤ 0.0064; SHA-256 V0 `2693c2da…a30c`; validator PASS; verdict: V0 remains the download candidate; V1 negative as a download, kept as a probe.
