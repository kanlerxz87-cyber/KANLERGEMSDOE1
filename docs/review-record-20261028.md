# Review record — 2026-10-28 (Lane H-K1-B + nine-site audit)

Branch: `arena/e4a3944d-kanlergemsdoe1`. Slots spent: 0. Verdict: negative.

## What was done
1. Restored hash-verified core data (`training_features.tif` 400 MB + labels +
   sample + existing_faults) via `scripts/restore_data.py`; moved from
   `.cache/gems_data/` (non-persistent) to `data/` (gitignored, snapshotted).
2. Re-fetched all 9 focus rasters — every SHA-256 matches `registry/focus_sites.json`.
3. Pixel-exact forensics (`evidence/focus_forensics_20261028.json`): G25==G30 (0-XOR),
   G32⊂G31⊂G25 chain, G36=G32+1,200, dose–response monotone within nested pairs.
4. Surveyed all 9 live sites: every one currently answers OK-to-submit with NO.
5. Pre-registered 5 hypotheses (`docs/research/hypotheses-upflow-20261028.md`), ran
   3/3 lane experiments + champion control (reproduced 0.099202/0.064121 exactly).
6. Emitted + validated unique EXP-2 artifact (15/15 checks, 29/29 detectors,
   run card `evidence/run_card_upflow.json`); staged research-only, DO NOT SUBMIT.
7. Updated site (index, executive summary, hypotheses, research, how-to-submit),
   README session section, knowledge docs 04/05, tests (+6 upflow, +1 allowlist).

## Key findings
- Lane H-K1-B triple negative: EXP-1 0.0448 / EXP-2 0.0577 / EXP-3 0.0525
  (HOLDOUT-DTI v3.1); canaries predicted it (best label-free AUC 0.573).
- Diagnosis: far-field alignment dots (p50 22.5 px) miss both withheld-catalogue
  and SGMC faults; not a code bug (dot spread rules out PU-inversion pile-up).
  Caveat: EXP-2 vs CTRL-BASE35 is not a pure feature ablation — negatives at
  d_vis>4 + upflow PU-guard + alignment-crest concentration differ from CTRL's
  d_vis>2/no-guard/no-crest protocol. The lane conclusion (upflow-alignment loses
  to ridge support on both populations) stands, but the exact attribution across
  features vs protocol is not isolated.
- GEMSDOE24#77 (registry_audit accepts wrong-CRS rasters): NOT PRESENT in our
  vendored `src/gems32/registry_audit.py` — `_load_registry_array` enforces
  count/shape/CRS/transform and marks mismatches `grid_mismatch` (fail-closed via
  measurability gate). No fork needed; verified, not fixed.
- `_rasterize_segments` linspace sampler could skip pixels (caught by new test);
  fixed with dense 0.5 px walk AFTER the lane ran on the cached v1 stack.
  Impact is sub-smoothing-scale (σ=1.5 smooth + max-merge); post-merge
  sensitivity re-run of cheap EXP-1 on a v2 stack is queued as follow-up.

## Irregularities flagged
- Owner-reported scores (incl. 0.2778) still lack organizer receipts everywhere.
- Prompt-quoted leaderboard highs (0.3195/0.4413) and inherited 0.4437 (all
  unverified, no receipts) vs today's observed public #1 0.4544 (GEMSDOE32 page):
  leaderboard moves; none receipt-bind any repo raster.
- Second local bar: the prior OCDA lane's plain-OOF-HGB control scored
  HOLDOUT-DTI 0.103048 on the same v3.1 evaluator (N = 22,232) — above the
  0.099202 champion replay on HR but below it on SGMC-cal (0.0567 vs 0.0641).
  Upflow EXP-2 (0.0577 / 0.0455) clears neither bar on either population.
- `data/peers/` fleet corpus from the OCDA session is not in git; this session's
  uniqueness corpus is the 31-raster local set (9 focus + 12 scored + 10 priors),
  stated exactly in the run card (`full_registry_checked: false`).

## Remaining work / limitations
- No new external data obtainable in-sandbox (egress: github/npm/pypi only);
  FDSN swarm-relocation lane stays conditional.
- No validated leaderboard-transfer calibration exists fleet-wide; estimates stay
  NOT ESTIMABLE by policy.
- Next scientific step (separate lane + pre-registration): near-catalogue
  off-support placement (d 2–10 px ring) or cross-repo OOF rank-blend via the
  team selector — not a 4th H-K1-B experiment.
