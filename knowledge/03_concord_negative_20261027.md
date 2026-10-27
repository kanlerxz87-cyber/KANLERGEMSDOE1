# KANLER-CONCORD negative result — 2026-10-27 (transferable knowledge)

**Lane tested (pre-registered, 3 experiments, fold-local v3.1, n=22,232):**
5-family soft-min concordance (mag/grav/topo+LiDAR/rad/sub ridge ranks,
road veto) + value-ordered √8 thinning. **EXP2 0.0518 [0.0443, 0.0595] vs
EXP1 H19-5-field control 0.1002 [0.0869, 0.1138]; paired Δ −0.0484
[−0.0625, −0.0341].** Gated collar relaxation also lost (EXP3 0.0942,
Δ −0.0060). Verdict: negative; lane closed. Full data:
`evidence/concord_experiments.json`, `evidence/concord_pass2.json`.

Reusable findings for any GEMSDOE sibling project:

1. **Fixed-weight unsupervised fusion is a dead end at this operating
   point.** Per-family withheld AUCs were 0.520–0.548; no fusion (mean
   0.563, geomean 0.568, max 0.511, shipped blend+veto 0.542) approaches
   the H19-5 field's holdout strength. Family weights must be *learned*
   under spatial blocks (next lane: PU-HGB), not asserted.
2. **Road-distance vetoes backfire.** Down-weighting near-road cells cut
   AUC 0.568→0.542: roads track range-front/piedmont corridors where
   faults (and mapping access) concentrate. Treat roads as a *covariate to
   model*, never a hard veto.
3. **The B2 (200 m) catalogue collar is fold-locally validated.** Allowing
   top-decile dots at 0–2 px from visible faults cost −0.006 DTI with CI
   excluding 0. Near-trace halos are net FP mass on withheld segments —
   even though live truth *can* sit there (staff 11516/4). Keep B2 unless
   a smarter near-trace model (tips/splays only) proves otherwise.
4. **Emission order matters for counts.** Prune-then-thin on the H19-5
   support starves at 36,388 dots (pool geometry), thin-then-prune gives
   the champion's 37,654. Compare methods at matched *accepted* counts
   and report starvation per fold.
5. **SGMC and hide-recover can disagree** (CONCORD: SGMC-CAL 0.0670 >
   champion 0.0641 while hide-recover halved). Pre-register one primary
   instrument; never shop for the flattering one post hoc.
6. **LiDAR band tags ≠ legacy helper comments.** `lidar_scarp_features_u8`
   band 3 is `step_max` (bands: 1 ex_max, 2 ex_mean, 4 lapneg, 5 lappos,
   6 downface, 7 upface, 8 cross, 10 coh100, 12 valid; valid = 75.37% of
   footprint). Assert descriptions at runtime.
7. **Uniqueness is cheap; ranking is hard.** CONCORD passed genuine-registry
   uniqueness easily (worst overlap 46%, vs champion 28.8%) while losing
   2× on DTI. Optimize ranking first; decorrelation follows.
