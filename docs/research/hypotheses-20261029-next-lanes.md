# Next-lane hypotheses (2026-10-29) — proposed, NOT validated

Status legend: **NOT VALIDATED** = no holdout number exists; nothing here is a score.
Repo check = `grep` of `src/` and `scripts/` on 2026-10-29 (see method note at bottom).

Ranked by expected DTI improvement per implementation cost (ranking is judgement; no expected-DTI value is computed).

| Rank | ID | Layer(s) (training_features band index, see `data/prepared_manifest.json`) | Physical signature targeted | Why it should find faults missing from USGS/INGENIOUS | Differs from repo code? (grep 2026-10-29) | Cost | Data status |
|---|---|---|---|---|---|---|---|
| 1 | **N1 Euler-SI** — structural-index-discriminated 3D Euler deconvolution | RTP magnetics (band 2), isostatic gravity (band 13), DEM (band 12) | Euler homogeneity solutions with structural index N=0 (fault/dike contacts) computed in moving windows; solutions cluster on source edges | Solutions come from the *field* alone, not from fault labels, so mapped-fault masking does not remove them | **No** (`euler` not found in `src/` or `scripts/`); listed as planned `H-K1-B` in `docs/research/` but not implemented | Medium (windowed least squares, 3730x3292) | Bands present locally |
| 2 | **N2 PBTD** — Poisson–Eötvös potential-field tensor bond | CBA gravity (band 2), isostatic gravity (band 3), basement gravity (band 14), RTP magnetics (band 4) | Local linear tensor relation between gravity curvature and horizontal magnetic gradients implied by Poisson's relation at a dipping basement contact | Measures a physical contact property, not a catalogue-derived quantity | **No** (`poisson_eotvos` / `PBTD` not found) | Medium-high (needs tensor derivatives) | Bands present locally |
| 3 | **N3 CSFD** — Coulomb slip-tendency from geodetic strain | Dilatation rate (band 16), second-invariant strain (band 17), structure-tensor strike (bands 32–33 as defined in `src/gems32/hypotheses33.py`) | Slip tendency under Byerlee friction, aligned with strain-field orientation | Targets currently active structures that may lack surface expression in the catalogue | **No** (`coulomb` / `CSFD` not found) | Low-medium | Bands present; risk: smooth regional strain may only recover broad belts |
| 4 | **N4 RMWD** — radiometric K/Th leaching asymmetry | GeoDAWN radiometric K, Th, U, K/Th (`data/external/geodawn_rad_u8.tif`), DEM (band 12) | Cross-strike K/Th asymmetry from hydrothermal leaching of the hanging wall | Radiometric signal is independent of the magnetic and gravity lanes | **No** (`RMWD` not found; `leaching` appears only in UWBP notes) | Low | Local raster present; risk: soil and lithology confounding |
| 5 | **N5 3DEP/QFFD/ComCat** — external 1 m LiDAR, USGS Quaternary Fault & Fold Database, relocated hypocenters | external | Fine-scale scarps; fault dips from hypocenters | Strongest physics but requires external data | Partial: `gdr_qfaults` used in lanes; 3DEP/ComCat not | High | **BLOCKED from this sandbox**: `usgs.gov` and `earthquake.usgs.gov` are not on the egress allow-list. Needs an unrestricted machine or an allow-list change. |

## Method note
- Repo-check commands: `grep -ril -- <term> src scripts` for `euler`, `poisson_eotvos`, `PBTD`, `coulomb`, `CSFD`, `RMWD`, `ComCat`, `QFFD`.
- Holdout gate for any of these: a candidate may not be spent on a weekly slot until it beats the current holdout best on the primary metric with a CI excluding zero (see `docs/submit.html`).
- Leakage canary required for each single feature before use (Protocol Rule 4).
