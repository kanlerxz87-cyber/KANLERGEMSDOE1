# Three-Pass Implementation & Verification Record (`2026-10-27 UTC`)

**Repository:** `kanlerxz87-cyber/KANLERGEMSDOE1`  
**Branch:** `arena/b23a6373-kanlergemsdoe1`  
**Candidate:** `KANLER1-OCDA-MSCS-EXP3` (`docs/downloads/gemsdoe32-kanler1-ocda-mscs-exp3-37654d-20261027T1842Z-1db32b55-zeros.tif`, SHA-256 `ec9b920ac059518f0a2382f08cbe3bc2b6074d1a302e9f25cd8a79abd97c8564`)  
**Release Gate Verdict:** `verdict: "negative"`, `ok_to_submit: false`, `slot_used: false` (`0` weekly DrivenData slots consumed)

---

## Pass 1 — Implement & Verify End-to-End

1. **Autonomous Data Restoration & Preparation:**
   - Executed `bash scripts/download_competition_data.sh` (restored & SHA-256-verified all 26 core, external, and historical scored files) and `python scripts/prepare_data.py` (prepared 19 input bands + rebuilt 35-channel `gems32-structural-v2` feature stack).
   - Restored the 9 focus rasters (`GEMSDOE24..36`) and pulled 16 SHA-256-pinned sibling/fleet rasters (`KANLERGEMSDOE2`, `KANLERGEMSDOE3`, `WBGGEMSDOE1..3`, `GEMSDOE70/73/76/91`) for a 42-raster uniqueness corpus.
2. **Byte-Level Dataset & Portal Forensic Audit:**
   - Verified and documented 5 raw-byte irregularities: `IR-BAND-06` (`tc` = GeoDAWN Radiometric Total Count, $\rho = +0.999951$), `IR-BAND-18` (signed $+\partial g_{\text{iso}}/\partial x$), `IR-BAND-10` (dependent seismicity density), `IR-SAMPLE-04` (`60,988` positive pixels in mirrored `sample_submission.tif`), and `IR-PORTAL-05` (`y_out = np.zeros(...)`, `nodata=None` in official reference U-Net preventing IEEE-754 `NaN` range failures).
   - Proved the zero-XOR nested pixel geometry of `H19-5 (0.1922) -> D2.8 (0.2600) -> B1 (0.2708) -> B2 (0.2778)` and its ~38% recall ceiling.
3. **Pre-Registration, Leakage Canaries, & 3-Experiment Fold-Local Execution:**
   - Pre-registered 4 untried geological hypotheses (`H-K1-A..D`) in `docs/research/hypotheses-20261027.md` prior to coding.
   - Implemented `src/kanler/ocda.py` (`26` label-free `OCDA` channels + `2` fold-local `cell.visible_full` continuation channels); verified `63/63` single-feature withheld-fold leakage canaries (`max AUC = 0.7386 <= 0.90`) and exact hidden-perturbation provenance invariance (`0` overlap, `0.0` float diff).
   - Executed `CTRL-BASE35-OOF` (`0.103048`) and `EXP-1..3` (`EXP-1: 0.104042`, `EXP-2: 0.025006` logged negative, `EXP-3: 0.105830`) strictly through shared `scripts/evaluate_holdout.py` and `scripts/submission_writer.py`.

---

## Pass 2 — Review & Fix Bugs, Assumptions, and Edge Cases

1. **`float32` Right/Bottom Boundary Rounding in `sample_bilinear_offset`:**
   - *Bug caught:* `np.float32(3292 - 1.0001)` rounded to `3291.0` in 24-bit float32 significand, causing `x0 + 1 == 3292` `IndexError`.
   - *Fix:* Replaced with `np.nextafter(np.float32(W - 1), np.float32(0.0))`, explicit `np.minimum(x0, W - 2)`, convex weight clamping `np.clip(wx, 0.0, 1.0)`, and explicit `H >= 2, W >= 2` shape validation.
2. **Positive-Unlabeled Split-Inversion Theorem (`EXP-2 -> EXP-3`):**
   - *Bug/assumption caught:* Zeroing `fold_vis_tip_continuation` and `fold_vis_stepover_relay_bridge` on `visible_mask` while training a PU classifier with `y = visible_mask` caused every positive training sample to have value `0.0`, inverting tree splits (`0.104042 -> 0.025006`).
   - *Fix:* Decoupled Stage-1 geophysical `OCDA` likelihood from Stage-2 logistic calibration fit strictly on 20% inner-withheld training-quadrant fault segments (`w_tip ≈ +2.47, w_relay ≈ +0.45`), raising `HIDE-RECOVER-v3.1` to `0.105830` (`+27.3%` in SW Walker Lane).
3. **Submodular Heap Pool Sizing & `min_dist_px == 0` Self-Blocking:**
   - *Edge case caught:* Small candidate pools (`pool_mult=6`) starved `ctrl_base35_oof` on wide un-thinned blobs, and `min_dist_px=0` did not set `blk_disk[0, 0] = True`.
   - *Fix:* Passed `cell.active_sub` with `pool_mult=26..28` so 100% of fold budgets fill cleanly, and set `blk_disk[r_blk, r_blk] = True` unconditionally.
4. **Memory-Safe Streaming Registry Uniqueness & `affine` Matmul Deprecation:**
   - *Bug caught:* Holding all 42 `3730x3292` float32 rasters simultaneously (`2.58 GB`) triggered container OOM on the zero-swap `3.8 GiB` host; `inv * (e, n)` emitted `PendingDeprecationWarning`.
   - *Fix:* Precomputed candidate rank vector once and streamed the 42 peers one-by-one (`< 300 MB` RSS, `49 s` runtime); replaced `inv * (e, n)` with `rasterio.transform.rowcol`; added outside-footprint zero validation to `evaluate_holdout.py --sgmc-map`.

---

## Pass 3 — Full Re-Check Against Original Prompt & Protocol

- **Protocol Rule 1 (Lane & Uniqueness):** Single lane `H-K1-A (OCDA-MSCS)` enforced; both pre-placement continuous surface (`max |Spearman| = 0.0785` vs discrete detectors; `0.3227` across all 42) and post-placement dots (`max 3-px = 52.33% <= 70%` across all 40 discrete detectors; `99.9363%` vs space-filling `r13-lattice-s5_v2` explicitly flagged) verified in `evidence/ocda_uniqueness_and_gate.json`.
- **Protocol Rule 2 (Reuse, Don't Rebuild):** Shared `gems32.features.load_checked`, `scripts/evaluate_holdout.py`, and `scripts/submission_writer.py` called directly; `--sgmc-map` added cleanly in shared `scripts/evaluate_holdout.py`.
- **Protocol Rule 3 (Strict Score Labeling):** Every local score labeled `HOLDOUT-DTI` with evaluator version, `N`, and 95% CI; historical site reports labeled `USER/OWNER-REPORT`; zero unlabeled forecasts.
- **Protocol Rule 4 (Leakage Canary):** All 63 features tested individually on withheld folds (`max AUC = 0.7386 <= 0.90`).
- **Protocol Rule 5 (Run Card):** Synchronized JSON Run Card written to `evidence/run_card.json`, `data/run-card.json`, and `docs/evidence/current_run_card.json`.
- **Protocol Rule 6 (Budget):** Exactly `3 / 3` experiments executed well within `< 2` hours; `0` weekly competition slots consumed.
- **UI/UX, Standing Prompt & Tests:** Standing prompt stored verbatim in `README.md` and `docs/ORIGINAL_PROMPT.md`; all 6 GitHub Pages subpages + 6 root redirects verified; all 35 automated unit tests passing (`0` failures).
