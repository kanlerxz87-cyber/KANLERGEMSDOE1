# Downloads — NO FILE CLEARED FOR CONTEST SUBMISSION (reviewed 2026-10-31)

All files in this directory are archived research artifacts. Do not upload any of them. The latest candidate fails the literal registry uniqueness threshold, and no candidate has selector approval. See [the current review](../review-20261031.md) and [submission gate](../submit-now.html).

| File | Method Lane & Scientific Summary | Submit? |
|---|---|---|
| `gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.zip` (`-nan.tif`, `-zeros.tif`, `-audit.json`) | **2026-10-28 `KANLER1-UWBP-DRCS-EXP3` (`37,647` dots).** 2D DCT-II Poisson worms + $55^\circ$ up-dip back-projection + elevation-deconfounded dual-regime + Dinkelbach 300 m CELF. `15/15` GeoTIFF checks PASS; `57/57` discrete fault-detector peers PASS (`max 3-px = 52.16%`, `19.49%` vs `GEMSDOE32`). Sets zero-SGMC regional Cenozoic record (`SGMC-CAL = 0.089174`, `EXP-B2 = 0.090111`, `+80.1%` vs `OCDA-EXP3`), while `HIDE-RECOVER-v3.1 = 0.064800` is below `GEMSDOE32` (`0.099202`). **NO — historical research artifact only. DO NOT SUBMIT. Detector-only uniqueness does not satisfy the literal all-registry rule; see the current negative run card and review.** |
| `gemsdoe32-kanler1-ocda-mscs-exp3-37654d-20261027T1842Z-1db32b55-nan.zip` (`-nan.tif`, `-zeros.tif`, `-audit.json`) | **2026-10-27 `KANLER1-OCDA-MSCS-EXP3` (`37,649` dots).** Offset-coupled dip-asymmetry + two-stage inner-withheld PU-HGB + 300 m CELF. `15/15` GeoTIFF checks PASS; `44/44` discrete detectors PASS (`29.49%` vs `GEMSDOE32`). Leads `KANLER1` on `HIDE-RECOVER-v3.1 = 0.105830` (`P(>Champ) = 90.9%`), `SGMC-CAL = 0.050040`. | **NO — research-hold (`verdict: negative`, selector approval required)** |
| `kanlergemsdoe1-concord5-b2-37654-research-20261027T171958Z-5dde8074-zeros.tif` (+ `-nan` twin, `.zip`, audit JSON) | Concurrent 2026-10-27 `KANLER-CONCORD` candidate (`HOLDOUT-DTI = 0.0518` vs control `0.1002`). | **NO — holdout-negative** |
| `gemsdoe32-h-unq1-blind-stepover-radiometric-conduit-dots-20261027T170959Z-339ac2dd-zeros.tif` (+ `-nan.tif`, `-zeros.zip`, `-audit.json`) | Concurrent 2026-10-27 `H-UNQ-1` (`7,420` dots, full-map holdout DTI diagnostic `0.0078`). | **NO — holdout-negative** |
| `kanlergemsdoe1-h195field-b2-37654-20261027T171629Z-fc14041c-zeros.tif` (+ twins) | `EXP1` control reconstruction (`H19-5` field + `B2`). `100%` within 3 px of the `GEMSDOE24/25/30` family. | **NO — duplicate lane** |
| `gemsdoe32-h33-h33-2-b2-…-zeros.tif` | `GEMSDOE32` champion reference copy (learning/benchmarking only). | **NO — already submitted** |
| `kanlergemsdoe1-h1/h2/h3-…` (2026-10-26), `kanler-mplc-…` | Stopped `IEDR` / `MPLC` lanes; inadmissible holdouts / lattice-duplicate. | **NO** |

Evidence: [`../evidence/run_card_uwbp_drcs.json`](../evidence/run_card_uwbp_drcs.json) ·
[`../evidence/run_card_ocda_mscs.json`](../evidence/run_card_ocda_mscs.json) ·
[`../evidence/current_run_card.json`](../evidence/current_run_card.json) ·
[Executive Summary](../executive-summary.html). No file in this directory is
authorized for a DrivenData weekly submission slot without separate team-selector clearance.
