# Supplementary review 2026-10-31 UTC — label-integrity blocker and restored-data findings

Complements [`review-20261031.md`](review-20261031.md) (main's fail-closed decision). This file adds the label-identity blocker (B1), the verified official-page statements, and the live leaderboard figures. Its verdict wording is aligned with the main review: no file is cleared for submission.

## Decision at a glance (aligned with review-20261031.md)

| Question | Answer |
|---|---|
| Can I **download** `gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif`? | **Yes, as a format-valid artifact.** It passes the official-format validator against the restored template (15/15 checks, see below). |
| Can I **submit** it to the DrivenData portal? | **No, not yet — HOLD.** The local holdout is invalid (blocker B1 below), and the file's only holdout evidence is below the champion's. |
| What is its organizer score? | **UNKNOWN.** No portal receipt exists. The `0.405` leaderboard figure in earlier pages is an extrapolation, not a score. |
| Is it unique? | **Yes by the repo's detector-only rule**, against all 23 restored references (worst non-lattice 3-px overlap 33.83%, max \|ρ\| 0.0064). The literal rule fails only on the `r13` spacing-5 lattice (see B3). |

Earlier pages said "OK TO DOWNLOAD AND SUBMIT", while the 2026-10-29 review said "NEGATIVE / RESEARCH HOLD". The 2026-10-31 check found a data blocker that the 10-29 review did not list. The verdict now follows the evidence, and every page has been updated to match.

## What was done this session

1. Created the local venv (`.venv`, gitignored) and installed `requirements.txt`. 77 unit tests pass.
2. Restored the core competition rasters with `scripts/restore_data.py --group core`. These are hash-pinned **owner mirrors** from GitHub (`buffedlizard55-lab/GEMSDOE`, `GEMSDOE24`), not DrivenData downloads. The receipt is `data/restore_receipt_core.json`.
3. Restored the nine focus-site rasters with `scripts/restore_focus_sites.py`. Until they were restored, this sandbox's audit ran against only 14 of 23 references (`malformed_or_missing: 9`), which is what made the first re-run differ from the committed file. With the focus sites restored, the re-run reproduces the committed 10-29 `evidence/uniqueness_audit_20261029.json` (23 references) byte-for-byte.
4. Re-ran `scripts/validate_submission_file.py` on the candidate. Result: PASS, SHA-256 `2693c2daf87bd7948d3d57fc41fdcf40653ef42014c93d0e947bc2a8fc00a30c`, 37,647 positive pixels, values in [0, 1], CRS EPSG:32611, shape 3730×3292, transform matches the template, NaN outside the footprint. Evidence: `evidence/validation_gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.json`.
5. Re-ran `scripts/audit_unique_candidates.py` against 23 references. Output matches the committed evidence `evidence/uniqueness_audit_20261029.json`.
6. Added `scripts/check_label_integrity.py` and its evidence, `evidence/label_integrity_20261031.json`.
7. Changed the verdict in `scripts/build_submit_page.py`, the generated `docs/submit-now.html`, `docs/executive-summary.html`, `docs/index.html`, `README.md`, and two tests. The card now says `ok_to_download: true`, `ok_to_submit: false`.

## Irregularities (flagged for review)

- **B1 — `labels.tif` and `existing_faults.tif` are byte-identical** (SHA-256 `7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093`, 60,988 positive pixels each, overlap 60,988). The catalogue faults and the withheld truth should be different sets. Either the owner mirror is wrong or the labels are not what they claim. Every hide-and-recover holdout that reads these files is invalid until the organizer download is compared. The mirror's `sample_submission.tif` also has exactly the same 60,988 ones. The official page says the sample "predicts total fault absence" (https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/, section *Submission format*), and it describes the test labels as *new* faults that are not in the USGS database, so an identical labels/existing-faults pair contradicts the official description on two counts. *Action:* download the official DrivenData files on an authorised machine and compare SHA-256 values with `data/restore_receipt_core.json`.
- **B2 — Competition inputs are owner mirrors, not organizer files.** `training_features.tif`, `labels.tif`, `existing_faults.tif` and `sample_submission.tif` came from other teams' GitHub repositories. Their hashes prove mirror consistency only. Using third-party copies of a login-gated competition dataset may also breach the competition's data terms; the team should check that before relying on them.
- **B3 — The literal uniqueness rule is saturated by the `r13-lattice-s5_v2` reference.** Its 3-px footprint coverage is 99.87%, so a dot inside the footprint is almost always within 3 px of it. Under the literal rule every candidate fails. Excluding this reference is our own choice and not an official rule. The team must decide this.
- **B4 — The holdout proxy disagrees with the organizer ledger.** This file's HIDE-RECOVER score is `0.0648` (repo-reported, lane run card), below the champion's `0.0992`. Its SGMC-CAL is `0.0892` (repo-reported 2026-10-29, not re-run this session), above the champion's `0.0641`. The SGMC calibration is extrapolated outside the fitted range.
- **B5 — The leaderboard figures conflict with the prompt.** The prompt cites `0.4413` and `0.3195`. The public leaderboard, fetched live on 2026-10-31 (https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/), shows #1 `0.4544`, #2 `0.3925`, #3 `0.3917`, #4 `0.3860`, #5 `0.3642`. These are public-test scores. The Initial Prize Round is scored on the private test set, and the official page says the final round rescores all selected submissions against an expanded label set.
- **B8 — One submission per team is final.** The official page states: "Competitors must choose a single submission for scoring across both rounds before the deadline, without knowing their private test set performance." A weekly-cap workflow therefore cannot substitute for choosing one well-tested file. Any upload must be the team's deliberate final pick.
- **B6 — Portal error history.** The `Predicted values must be in range [0, 1]` error was not root-caused. The validated file passes the local [0, 1] check, but only the portal can confirm acceptance.
- **B7 — Coverage.** Only 9 focus sites and 14 other owner rasters are restored. Many listed sites (for example GEMSDOE26, 34, 35, 37–91 and the sibling repos) were not retrieved. Uniqueness against them is **not verified**.

## Run card

```json
{
  "hypothesis": "A UWBP-DRCS blind-worm candidate (EXP-B3) is a unique, format-valid submission that could exceed the 0.2778 incumbent.",
  "mechanism": "2D DCT-II Poisson worms with 55-degree up-dip back-projection, elevation-deconfounded dual-regime and Dinkelbach 300 m CELF selection.",
  "named_non_fault_process": "Alluvial-fan toes, lake-shore scarps and intrusive contacts.",
  "holdout_dti": {
    "label": "HOLDOUT-DTI (repo-reported lane run card; NOT re-run this session; INVALID until B1 is resolved)",
    "evaluator_version": "GEMSDOE32-HIDE-RECOVER-v3.1",
    "withheld_positives": 22232,
    "value": 0.0648,
    "ci95": [0.057434, 0.071809]
  },
  "sgmc_cal": {
    "label": "HOLDOUT-DTI (repo-reported 2026-10-29 scoreboard; NOT re-run on 2026-10-31; inherits B1)",
    "evaluator_version": "GEMSDOE32-SGMC-CAL-v3.0",
    "withheld_positives": 62703,
    "value": 0.0892
  },
  "correlation_overlap_vs_registry": {
    "references_compared": 23,
    "worst_non_space_filling_within_3px": 0.3383,
    "worst_abs_spearman": 0.0064,
    "literal_rule_passed": false,
    "literal_failing_reference": "data/scored/13gems_20261001_r13-lattice-s5_v2_nan-outside.tif (lattice, 99.87% footprint coverage; see B3)",
    "detector_only_rule_passed": true
  },
  "raster_sha256": "2693c2daf87bd7948d3d57fc41fdcf40653ef42014c93d0e947bc2a8fc00a30c",
  "validator_output": {
    "file": "evidence/validation_gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.json",
    "all_passed": true,
    "no_nan_inside_footprint": true,
    "values_in_0_1": true,
    "crs_shape_transform_match_restored_template": true,
    "caveat": "template is an owner mirror (B2), not the organizer file"
  },
  "submission_name": "kanler1-uwbp-drcs-exp3-37647d-nan",
  "submission_note": "KANLER1 UWBP-DRCS EXP3 worm+Dinkelbach 37647 dots NaN-outside; SGMC-CAL proxy 0.0892 (not organizer score)",
  "experiments_used_this_session": 0,
  "verdict": "NEGATIVE / HOLD for submission. Download allowed as format-valid artifact only. Do not spend a weekly slot until B1 is resolved and the selector clears it."
}
```

## Sources for manual review

- Competition overview and rules: https://www.drivendata.org/competitions/306/competition-doe-gems/
- Problem description and submission format: https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/
- Leaderboard (fetched 2026-10-31): https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/
- Submission format PDF: https://docs.nlr.gov/docs/fy26osti/96647.pdf
- Reference solution: https://github.com/drivendataorg/gems-prize-reference-solution
- Projections are not scores. Organizer scores appear only from a portal receipt.
