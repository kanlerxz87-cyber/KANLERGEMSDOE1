# Ranked candidate hypotheses (pre-registered 2026-10-26, before any model fit in this repo)

Evidence classes: HOLDOUT-DTI / OWNER-REPORTED / ORGANIZER-CONFIRMED / PROJECTION.
No number in this file is a score. Live scores quoted from the prompt are OWNER-REPORTED
(no submission-page receipt in this repo links them to exact bytes).

## Why the 0.2778 file (GEMSDOE32 h33-h33-2-b2) plausibly scored highest — PhD reading

Official metric (DrivenData #306 problem page, verified 2026-10-26): distance-weighted
Tversky, alpha=0.2 (FP), beta=0.8 (FN), 300 m triangular kernel, EPSG:32611, 100 m.
Algebra (vendor/gems57/metric.py, brute-force tested upstream): with T=kernel TP credit,
S=emitted mass, M=self-credit, DTI = T / (0.2*(T+S-M) + 0.8*|G|). A non-redundant dot
raises DTI iff its kernel credit k > 0.2*DTI (~0.056 at 0.2778). The H19-5 lineage is
nested (OWNER-REPORTED): solid 121,131 dots 0.1922 -> d1.5 60,069 dots 0.2477 ->
d2.8 44,090 dots 0.2600 -> B2-pruned 37,654 dots 0.2778. Thinning deletes dots whose
realised credit is below the metric's own break-even bar while the 300 m kernel still
covers the same truth pixels from neighbours; B=2 additionally removes dots within
2 px of the *known* catalogue, which can only earn credit already saturated by the
catalogue trace itself on hidden-fault scoring. Conclusion: the win is mostly an
*emission* effect on one good field, not a new detector. Beating it requires a field
whose top ~37k off-catalogue pixels carry >~25% more mean kernel credit (GEMSDOE32
knowledge/01 derivation), i.e. a detector improvement, verified on hide-and-recover
holdout — not another thinning of the same field (that is also the duplicate lane).

## Candidates (all use only data already restored hash-verified in data/, see registry/data_manifest.json)

| Rank | ID | Layers | Physical signature | Why it should catch catalogue-missing faults | Difference vs everything in sibling repos | Cost |
|---|---|---|---|---|---|---|
| 1 | **MPLC** (this lane) | RTP/mag_anom (B2/B1), iso_grav_anom (B13), det_elev (B12), extensions TMI_up150 | Multi-scale (8/20/50 px) monogenic **local-phase congruency**: phase alignment across scales via Riesz transform; contrast-invariant step/line detection + cross-source PC concordance (min/mean) + gradient structure-tensor orientation coherence | Gradient-magnitude detectors (every prior HGB/ridge lane) are amplitude-biased toward shallow, high-contrast sources — exactly the faults already mapped. Buried/blind faults under sedimentary cover keep a *phase* signature (aligned step across scales) at low amplitude. PC normalises amplitude away, so it ranks low-contrast blind steps that magnitude stacks bury | `grep` of GEMSDOE32 knowledge/src/scripts (2026-10-26): zero hits for phase-congruency/monogenic/Riesz/local-phase. Frangi/Steger/Hessian/tilt/analytic-signal were tried; none is phase-based | Medium: FFT features once (~min), then HGB |
| 2 | TIPFIELD | Visible catalogue only + B12/B19 | Fault-tip continuation: endpoint density + collinearity-weighted orientation field from visible segment endpoints (<=12 px segments) | Unmapped faults are often continuations/step-overs of mapped tips | Tip/stepover tried live (GEMSDOE33 0.2632 OWNER-REPORTED) as a *placement* rule; as a fold-local *feature* with buffer-honest derivation it is untested here — but catalogue-derived features carry the highest leakage-canary risk | Low |
| 3 | RADALT | GeoDAWN rad K/Th/U/TC + ThK/UK/UTh extensions | Hydrothermal alteration ratios (K enrichment, Th/K lows) *edges* (not levels) concordant with mag PC | Alteration halos follow fluid pathways = faults even where the fault has no mag/grav contrast | Alteration *levels*/clay-cap tried (GEMSDOE15, H72); ratio-edge concordance as a feature block is new, but rad is 100 m-resampled and alteration also follows lithology | Low |
| 4 | STRAINVORT | B4/B7/B8 strain rates | Strain incompatibility: spatial curl/gradient discordance of dilatation vs shear (second-invariant-normalised) | Actively localising structures partition strain; a discordance line can precede a mapped trace | Strain bands used as raw levels in many stacks; the *normalised discordance* transform is new. Only 3 strain bands exist (no full tensor), so true vorticity is not computable — flagged approximation | Low |
| 5 | SCARPASYM | B12/B19 + LiDAR u8 stack | Scarp asymmetry index: signed cross-ridge elevation difference normalised by relief, from 100 m DEM + LiDAR step bands | Young scarps are asymmetric; symmetric ridges (dikes, shorelines) are the main mimic and are explicitly down-weighted | LiDAR scarp *magnitude* is heavily tried (GEMSDOE7/12/47/64/66); the signed asymmetry normalisation is not in the sibling grep | Medium |

Ranking logic: expected DTI gain per unit cost and per unit leakage risk. MPLC is rank 1
because it is the only candidate whose targeted population (low-amplitude blind steps)
is disjoint from the population every magnitude-based lane already harvests.

**Non-fault mimic for MPLC (named, per protocol):** lithologic contacts, mafic dikes,
paleo-shoreline risers, and road/terrace edges are also phase-congruent steps. The
cross-source concordance (mag AND gravity AND DEM phase agreement) and the supervised
HGB (trained on real faults) are the mitigations; the holdout decides.

## Frozen experiment plan (max 3 experiments, fail-closed)

- EXP1 control: HGB on 39-band base stack (19 competition + 12 LiDAR u8 + 4 rad u8 + 4 extensions u8).
- EXP2 candidate: EXP1 + 6 MPLC bands. Same folds, same budgets, same emission.
- EXP3 (only if EXP2 paired 95% CI vs EXP1 > 0): emission budget sweep 37,654 vs 44,090 on the winning arm.
- Holdout: KANLER-HOLDOUT-v1 = vendor gems57 holdout (whole <=12 px segments, quadrant
  domains eroded 12 px, seed 20, mode=all, hide 20%/quadrant) + spatially-blocked training
  (model for a quadrant never trains on that quadrant), visible faults masked pixel-exact,
  catalogue features: none used; emission prune uses visible catalogue only.
  Pooled DTI alpha=0.2 beta=0.8 R=3px; paired 20-km block bootstrap CI (vendor pooled_summary).
- Leakage canary: every MPLC band alone, AUC withheld-vs-active per pooled folds; >0.90 = leakage stop.
- Uniqueness gates (protocol): surface |Spearman| <= 0.90 and final-dot 3-px overlap <= 70%
  vs every registry raster (discrete scored peers; the spacing-5 lattice blanket is
  reported separately — under a literal all-raster reading every dense map fails it,
  disclosed as IR-K1, same disclosure as GEMSDOE31 IR-U-02).
- Promotion gate: candidate must beat EXP1 AND the champion raster's same-evaluator
  HOLDOUT-DTI with paired CI > 0, pass canary + uniqueness + vendor format validator.
  Otherwise verdict=negative, file is research-only, no slot spent.
