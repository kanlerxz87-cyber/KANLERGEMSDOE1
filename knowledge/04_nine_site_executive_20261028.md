# Nine-site executive audit — 2026-10-28 (KANLERGEMSDOE1 session)

**Scope.** The nine focus sites named in the session prompt: GEMSDOE24, 25, 27, 28,
30, 31, 32, 33, 36. Two evidence layers: (A) our own pixel-exact forensics on the
hash-pinned rasters (`evidence/focus_forensics_20261028.json`, all 9 SHA-256 verified
against `registry/focus_sites.json`); (B) each site's self-declared status page as
fetched today (2026-10-28, UTC).

**Headline verdict: download NONE for submission.** Every historical file below is
already scored (a resubmission spends a weekly slot and adds zero information), carries
no organizer receipt, and every live site currently answers its own "OK to submit?"
with NO. The highest owner-reported number remains GEMSDOE32's 0.2778.

## Decision table (file → estimate → uniqueness → submit?)

| Site | File to download (research only) | Dots | Reported | Estimate | Unique vs other 8? | Submit? |
|---|---|---|---|---|---|---|
| GEMSDOE24 | `gems24-h25-1-dotted-h19-5-d1-5-20261002-989f59505db1-nan.tif` | 60,069 | 0.2477 [OWNER-REPORT] | NOT ESTIMABLE | NO (⊂ G27; J=0.9795) | **NO — already scored** |
| GEMSDOE25 | `gems25-dotted-h19-5-d2-8-20261002-e56ea318af89-nan.tif` | 44,090 | 0.2600 [OWNER-REPORT] | NOT ESTIMABLE | NO (== G30 bit-identical) | **NO — already scored** |
| GEMSDOE27 | `gems27-topo-gap-closure-t-v2-on-d1-5-20261002-5512495c6bd1-nan.tif` | 61,328 | 0.2449 [OWNER-REPORT] | NOT ESTIMABLE | NO (⊃ G24) | **NO — already scored** |
| GEMSDOE28 | `gems28-h36-1-rung30-blind-r1-20261003-b531dae0a36f-nan.tif` | 37,660 | 0.2710 [OWNER-REPORT] | NOT ESTIMABLE | NO (100% in H19-5) | **NO — already scored** |
| GEMSDOE30 | `gemsdoe30-d28-poisson300m-offcat-44090-20261003T233156Z-91eae1ca.tif` | 44,090 | 0.2600 [OWNER-REPORT] | NOT ESTIMABLE | NO (== G25 bit-identical) | **NO — already scored** |
| GEMSDOE31 | `gemsdoe31-h27-4-solo-d28-20261004-8acb75e1-nan.tif` | 40,199 | 0.2708 [OWNER-REPORT] | NOT ESTIMABLE | NO (⊂ G25/G30) | **NO — already scored** |
| GEMSDOE32 | `gemsdoe32-h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros.tif` | 37,654 | 0.2778 [OWNER-REPORT] | NOT ESTIMABLE | NO (⊂ G25/G30/G31/G36) | **NO — already scored** |
| GEMSDOE33 | `GEMSDOE33-h33d-analog-tip-stepover-r30-20261004-cb490425926e.tif` | 41,865 | 0.2632 [OWNER-REPORT] | NOT ESTIMABLE | NO (J=0.682 vs G25) | **NO — already scored** |
| GEMSDOE36 | `gemsdoe36-anderson-geothermal-pinn-38854-20261004T230000Z-9b9ea4e6-zeros.tif` | 38,854 | 0.2750 [OWNER-REPORT] | NOT ESTIMABLE | NO (⊃ G32, +1,200 dots) | **NO — already scored** |

Why "NOT ESTIMABLE" instead of a number: a catalogue holdout cannot be converted
honestly into the organizer's hidden-fault score (no transfer calibration exists;
GEMSDOE31 measured out-of-family RMSE 0.196 / bias +0.135 over 67 matched
owner-reports — worse than guessing the mean). Every site's own table says the same.
A projection is never written as a score.

## Per-site notes (forensics + live status observed 2026-10-28)

**GEMSDOE24** (0.2477, 60,069 dots, NaN-outside). D1.5-spaced thinning of H19-5;
strict subset of GEMSDOE27. Live: "DOWNLOAD: YES / SUBMIT: NO", point-best S3DEP1
HOLDOUT-DTI 0.16606 is research-only, blocked by literal lattice overlap (99.78%).
Source: <https://buffedlizard55-lab.github.io/GEMSDOE24/>

**GEMSDOE25** (0.2600, 44,090 dots, NaN-outside). D2.8 Poisson thinning of H19-5;
**bit-identical positive mask to GEMSDOE30** (XOR = 0) — the two 0.2600 reports are
the same raster scored twice, which cross-validates report self-consistency. Live:
"Competition-ready TIF: NO", newest H79-CTHM research-only (fails CTRL_H35).
Source: <https://buffedlizard55-lab.github.io/GEMSDOE25/>

**GEMSDOE27** (0.2449, 61,328 dots, NaN-outside). D1.5 + 1,259 topo-gap-closure dots
(only 2.05% outside H19-5); superset of GEMSDOE24. Live: newest H33-1
HOLDOUT-DTI 0.0252 < control 0.0414, "NOT OK TO SUBMIT". Its own "why 0.2778" note
reproduces our subset chain exactly (6,436 / 3,891 / 2,545 collar dots).
Source: <https://buffedlizard55-lab.github.io/GEMSDOE27/>

**GEMSDOE28** (0.2710, 37,660 dots, NaN-outside). Independent "rung30-blind" thinning,
100% inside H19-5 but NOT in the G25⊃G31⊃G32 nested chain (Jaccard 0.535 vs G32).
Live: S25-PCSUP unique but HOLDOUT-DTI 0.0450 < random control 0.0699 — "OK to
submit? NO".
Source: <https://buffedlizard55-lab.github.io/GEMSDOE28/>

**GEMSDOE30** (0.2600, 44,090 dots, zeros-outside). Same decoded support as GEMSDOE25
(XOR = 0); zeros-outside twin of the same dot set. Live: "DUPLICATE-STOP / NOT
APPROVED", POOL-1 holdout wins blocked at 71–89% registry overlap, no TIFF published.
Source: <https://buffedlizard55-lab.github.io/GEMSDOE30/>

**GEMSDOE31** (0.2708, 40,199 dots, NaN-outside). D2.8 minus 3,891 dots within 1 px of
catalogue (strict subset of G25/G30; superset of G32). Live: newest H31-CC basement-step
is unique vs all 9 focus (≤9.6%) but HOLDOUT-DTI 0.0471 < chance — "DO NOT SUBMIT".
Source: <https://buffedlizard55-lab.github.io/GEMSDOE31/docs/>

**GEMSDOE32** (0.2778, 37,654 dots, zeros-outside). D2.8 minus 6,436 dots within 2 px
of catalogue (strict subset of G25/G30/G31 — and of G36). Highest owner-report of the
nine; already submitted ("do not resubmit"). Live: newest H51-1 EWSP beats the champion
on HIDE-RECOVER (0.1151 vs 0.0992, paired CI > 0) yet is held DO-NOT-SUBMIT on SGMC-cal
gap + lattice overlap + selector review; public #1 observed 0.4544 (xiaofanhu).
Source: <https://buffedlizard55-lab.github.io/GEMSDOE32/docs/index.html>

**GEMSDOE33** (0.2632, 41,865 dots, zeros-outside). D2.8-family + analog tip-stepover
grafts (only 133 dots / 0.32% outside H19-5). Live: three newest unique TIFFs
(A33-R7-PCSUP, A33-R6-BASESTEP, PFRT) all format-valid and registry-unique but
holdout-negative — "✅ DOWNLOAD YES · 🛑 SUBMIT NO" throughout.
Source: <https://buffedlizard55-lab.github.io/GEMSDOE33/docs/index.html>

**GEMSDOE36** (0.2750, 38,854 dots, zeros-outside). **Champion + 1,200 grafted dots**
(G32 ⊂ G36, XOR = 1,200; 1,199 of the grafts outside H19-5 — the PINN geothermal
extension). Scores 0.2750, just below 0.2778: the grafts added FP mass without
compensating TP. Live: "DO NOT SUBMIT — literal uniqueness gate failed".
Source: <https://buffedlizard55-lab.github.io/GEMSDOE36/docs/>

## Cross-site mechanism (measured, not inferred)

1. **One family.** 8 of 9 rasters are 100% inside the 121,131-px H19-5 ridge support
   (G27 +2.05%, G33 +0.32%, G36 +3.09% outside). G25 == G30 exactly.
2. **Dose–response in sparsity (within controlled nested pairs).** Reported score
   rises as dots fall along every strict-subset step: G27 ⊃ G24 (61,328@0.2449 →
   60,069@0.2477); G25/G30 ⊃ G31 ⊃ G32 (44,090@0.2600 → 40,199@0.2708 →
   37,654@0.2778); G36 ⊃ G32 (38,854@0.2750 → 37,654@0.2778). G28 (37,660@0.2710)
   is a different dot *placement* off the nested chain (J = 0.535 vs G32), so its
   score is not a controlled sparsity comparison — but it still lands on the
   sparse-is-better trend (37.7k dots, second-highest score).
3. **Collar steps.** 0.2600 → 0.2708 → 0.2778 as the catalogue collar widens none →
   1 px → 2 px (3,891 then 2,545 dots removed). Consistent with the organizer masking
   only exact known-fault pixels (forum #11516): near-catalogue predictions pay FP
   unless they sit on hidden truth.
4. **Graft penalty.** G36 = G32 + 1,200 dots → −0.0028. New dots must earn their FP
   tax: this is the bar any discovery method must clear.

Causality is NOT proven: hidden truth and score-to-file receipts are unavailable.
But the geometry + metric algebra + monotone dose-response make FP-denominator
reduction the most parsimonious PhD-level explanation (see `knowledge/05_*`).
