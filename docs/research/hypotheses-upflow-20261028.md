# Pre-registered Lane H-K1-B (GEOALIGN-UPFLOW) — 5 hypotheses, 3 experiment slots

**Date (UTC):** 2026-10-28 **Repo:** `KANLERGEMSDOE1` **Evaluator:** `GEMSDOE32-HIDE-RECOVER-v3.1`
(N=22,232) + `GEMSDOE32-SGMC-CAL-v3.0` (N=62,703) **Budget:** 3 experiments, 37,654-dot
emission budget each, fold-visible B=2 collar, min spacing d=sqrt(8) px.

**Lane thesis.** OCDA-MSCS (Lane H-K1-A) consumed geothermal point data only as *isotropic
gaussian halos* (`_parse_2m_probes_halo`, `_build_vent_sinter_halo`). Faults are *linear,
anisotropic* permeability structures: hot-spring trains, sinter/travertine corridors, vent
alignments and thermal-plume *margins* (gradient ridges, not blob centers) projected along
local structural strike and *intersected* with potential-field edges should recover blind
segments that halos blur out. Every channel below is label-free; catalogue interactions use
only per-fold `cell.visible_full` (perturbation-invariance gated). Nothing reads
`dist_known_fault_px` (full-catalogue derived).

## Ranked hypotheses (expected DTI gain × novelty / cost)

| Rank | ID | Layers / signature | Why off-catalogue | Differs from repo | Slot |
|---|---|---|---|---|---|
| 1 | **H-K1B-1 ALIGN-CORRIDOR** (unsupervised) | wellsprings T≥32 °C + quartz-gt + paleo sinter/travertine + vents, strike-projected ±1–2 km along potential-field strike, ∩ (tmi_edge ∪ grav_edge ∪ cond_edge), NMS 1-px skeleton | upflow manifestations sit above blind segments w/o Quaternary rupture (Faulds+ 2021 play fairway) | anisotropic corridors+edge-∩ vs OCDA isotropic halos; alignment-first vs CGJI cross-gradient-first | EXP-1 |
| 2 | **H-K1B-2 OOF-FUSION** (supervised) | shared35 + 12 upflow channels → fold-local PU-HGB (4:1, d_vis>4 + phys-guard), alignment-crest concentration, 300 m CELF | calibrated fusion beats fixed weights; PU guard avoids mapped-fault overfit | same *protocol* as OCDA EXP-1, disjoint *feature lane* | EXP-2 |
| 3 | **H-K1B-3 TWOSTAGE-ALIGN** (two-stage) | inner-withheld log-odds fusion of EXP-2 posterior + H-K1B-1 surface; sharp alignment-crest²·²; flank explaining-away; anisotropic collar | EXP-3 mechanics won in OCDA (0.1058); alignment continuation replaces tip/relay continuation | continuation prior is upflow-linear, not tip-stress | EXP-3 |
| 4 | H-K1B-4 SHORELINE-FP (backup) | Lahontan shoreline-contour confound model to downweight wave-cut scarps | FP reduction on 12 % of dots | unimplemented this session (needs level-datum audit) | — |
| 5 | H-K1B-5 WORM-QF (backup) | FFT upward-continuation worm persistence + QFaults slip-rate tip fans | multi-height edges | overlaps GEMSDOE73 idea family; QFaults has centroids only | — |

**Named non-fault mimic:** alluvial-fan toes, playa margins and irrigation/pumping thermal
noise produce linear thermal contrasts; mitigated by (a) quartz-geothermometer ≥90 °C
(deep-reservoir) weighting, (b) mandatory potential-field edge intersection, (c) TIGER
road-corridor damping. **Leakage canary:** single-feature withheld-fold AUC ≤ 0.90 each.
**Uniqueness gate:** pre-placement |Spearman| ≤ 0.90 AND post-placement ≤70 % within 3 px
vs every registry raster incl. OCDA EXP-3 and GEMSDOE32 champion, else STOP-negative.
**Promotion bar:** paired 95 % CI > 0 vs champion AND no SGMC-cal regression, else the
emitted GeoTIFF stays `DO-NOT-SUBMIT` research/audit-only.
