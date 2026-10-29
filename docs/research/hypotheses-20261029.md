# Candidate hypotheses — 2026-10-29 (UNTESTED; no slot, no submission)

Scope: the prompt asked for 3–5 candidates, ranked by expected DTI gain and cost, each naming layers,
physical signature, why it targets off-catalogue faults, and how it differs from the repo. **None of these is
validated.** Ranking uses the official metric and the calibration evidence in `evidence/`.

Verified facts used (official sources, fetched 2026-10-29):
- Metric: distance-weighted Tversky, alpha = 0.2, beta = 0.8, triangular kernel with R = 300 m; predictions
  may be any probability in [0, 1]; the submission must be float32 with NaN or null outside the bounds
  (https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/).
- Known USGS/INGENIOUS fault pixels are masked pixel-exact; a prediction near a known trace but far from
  new-fault truth is fully penalised (staff reply, https://community.drivendata.org/t/scoring-clarification-are-known-usgs-ingenious-faults-masked-when-scoring-and-are-they-in-the-final-round-label-set/11516/4).

| Rank | Candidate | Layer(s) | Physical signature targeted | Why it should hit an off-catalogue fault | Difference from repo | Expected DTI gain | Cost | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | **H-P1 probability halo** | Existing UWBP-DRCS dots (B3) only | Dots at p = 1, one-pixel ring at p = λ (λ tuned on SGMC only, never on HIDE-RECOVER) | Official metric is continuous; a partial ring costs less FP mass than a full dot where the dot is 1–3 px off the true trace, so it can raise expected TP per FP | Repo emits only binary dots (`submission_writer`/`evaluate_holdout` reject non-binary); needs a DTI evaluator that accepts p | Unknown; plausible positive | Medium (new evaluator path in shared `gems32.holdout`) | UNTESTED |
| 2 | **H-P2 collar sweep** | Catalogue traces (visible faults only in fold-local runs) | Radius B of exclusion around mapped traces, sweep B in {1, 2, 3} px | Pixel-exact masking means halo pixels are *not* free; B = 2 is the incumbent choice with no sweep on the SGMC proxy | Repo fixed B = 2 from the 0.2778 lineage; no sweep | Small; overfit risk on 12 points | Low | UNTESTED |
| 3 | **H-P3 density control** | All candidates | Whether SGMC-CAL is inflated by dot density (r13 has 206,895 dots, SGMC 0.0936, organizer 0.0904) | If density drives the proxy, B3's 0.089 may overstate its organizer score | Repo has not tested density as a confound | Diagnostic only | Low | UNTESTED |

Rejected on purpose: training on the off-catalogue SGMC layer. That layer is the evaluator's own truth
set, so any gain would be leakage, not discovery (see `docs/review-20261027.md` on leakage canaries).
