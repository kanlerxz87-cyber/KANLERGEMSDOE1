# Research slate — pre-implementation, 2026-10-26 UTC

**All ideas below are unimplemented and untested in this review.** They remain
within the earthquake–strain–magnetic structural-context lane; a new lane or a
change to the literal registry rule requires an explicit future protocol decision.
The prior IEDR run has already triggered STOP, so none may be run in this session.
The expected ranking is qualitative scientific judgment, **not a DTI or forecast**.
Novelty is relative to code inspected in this checkout, not proof nobody else
has tried a similar idea. Earlier `H32-B` already combines independent/dependent
earthquake density with strain; that combination alone is **not** a new hypothesis.

| Priority / expected benefit / cost | Hypothesis and layers | Signature and why it might find a catalogue-missing fault | Difference from inspected implementation; non-fault mimic; data access |
|---|---|---|---|
| 1 · highest plausible / high | **Location-uncertainty-aware seismic corridor**: individual USGS ComCat events, time and location uncertainties, GeoDAWN `tmi_hg`, strain `geod_dilaterate`. | Fit uncertainty-weighted, anisotropic point-cloud lineaments, then demand a magnetic-edge strike consistency. A buried active structure could host distributed earthquakes without a mapped scarp. Event-location uncertainty sets the minimum credible scale. | `H1` uses a broad pre-gridded density and pointwise magnetic magnitude, not individual uncertainty ellipses with orientation agreement. `H33-E` had already *proposed* raw-event lineaments but did not implement them; this refines that idea rather than claiming the entire concept is new. **Mimics:** induced/injection or mining swarms, clustered stations. Official free [USGS FDSN event service](https://earthquake.usgs.gov/fdsnws/event/1/) responded to a [bounded count query](https://earthquake.usgs.gov/fdsnws/event/1/count?format=geojson&starttime=2020-01-01&endtime=2021-01-01&minlatitude=37&maxlatitude=42&minlongitude=-120&maxlongitude=-116&minmagnitude=2); full event extraction and license/uncertainty audit were not performed and shell access to that host is restricted here. **Feasibility conditional, not ready to run.** |
| 2 · medium / high | **Temporal stability vs swarm counterfactual**: same USGS events, INGENIOUS density bands 10/16, magnetic gradient. | Independently build early/late-event orientation fields, reward recurring alignments only when both periods have adequate detection, and contrast the result with a swarm-only model. Stable seismic structures might predate an omitted mapping campaign. | Unlike `H32-B`'s gridded density difference, this uses held-out temporal event windows and an explicit swarm counterfactual. **Mimics:** persistent injection or network sensitivity changes. Same public FDSN source; full event/time metadata not yet acquired. |
| 3 · medium / medium | **Uncertainty-aware, multiscale magnetic–seismic discordance**: cached `ieq_n100a15`/`deq_n100a15`, `tmi_hg`, `rtp`, `geod_dilaterate`. | Compare orientations of magnetic edges across survey scales, condition them on *regional* seismicity/strain, and downweight survey-line anisotropy. A coherent buried lithologic offset may be missed in scarps. | H1 uses scalar magnetic magnitude; this requires explicit multiscale strike and nuisance-direction controls, not just the H32-B density contrast. **Mimics:** lithologic contacts, dikes and flight-line leveling. Mirror data available; raw survey coverage and scale interpretation need checking. |
| 4 · exploratory / medium | **Seismic-context scarp-persistence**: cached regional earthquake bands, `det_elev_slope` and mirrored LiDAR scarp features. | Use regional seismicity only as a weak gate while requiring cross-scale persistent scarp evidence; separate spatial sampling from the structural evidence. Young subtle scarps can be absent in legacy maps. | Different from H1's seismicity-first ranking and from H33-C's pure scarp chain: compare an explicit seismic-context interaction against the exact same scarp-only control. **Mimics:** shorelines, roads, erosional terraces. Owner-mirrored layers available; original 1 m DEM link list still unavailable. |

## Evidence and constraints

- The [organizer](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/)
  scores **fault traces**, not geothermal vents or power-production potential. A
  plausible geothermal conduit is not automatically a positive test fault.
- USGS reports that the southern Gabbs Valley discovery was blind and lacked
  surface hot springs, fumaroles and palaeothermal deposits, despite a coupled
  structural/geophysical signal ([USGS report](https://www.usgs.gov/publications/discovering-blind-geothermal-systems-great-basin-region-integrated-geologic-and)).
  This supports studying subsurface corroboration, not assuming that its particular
  successful combination predicts this competition's labels.
- USGS process models show localized strain at fault interactions, stepovers and
  terminations ([Siler, 2023](https://www.usgs.gov/publications/structural-discontinuities-and-their-control-hydrothermal-systems-great-basin-usa)).
  A natural mechanism is not a proof that a particular pixel is a fault.
- On the restored owner mirror, the `ieq_n100a15` band had Pearson correlation
  **0.99354** with itself at a 3 km east–west lag across 5,045,164 paired finite
  cells; north–south it was **0.99411** across 5,017,822. These are feature-scale
  diagnostics, not competition scores or proof of absence of fine-scale information.
- A future valid test must pre-register the split, remove entire connected fault
  segments with a spatial buffer, rebuild each catalogue-derived feature and the
  dots using visible-only faults for every fold, run held-out feature AUC canaries,
  compare matched paired spatial bootstrap intervals to the strongest same-evaluator
  baseline, and check the surface and final dots against **every** registered raster.
  A complete inventory and an explicit policy for density-saturating registry maps
  are required; this session may not silently exempt them.

---

## Addendum — 2026-10-27 Execution (`L-CGJI-HTB-2026-10-27`) & Expanded Multi-Physics Slate

In the 2026-10-27 session, we rebuilt the verified 35-channel v2 feature stack (`gems32-structural-v2-principal-curvature`, SHA-256 `ec70d7eac8f19f6910b98342ad2eff571bbd9ef20c718eedd900e06ca4acc944`) and executed the 3-experiment **CGJI-HTB** lane (`src/kanler/cgji.py`, `scripts/run_cgji_experiments.py`) with strict fold-local visible-only masking (`invariance_verified = True`, `max_abs_diff = 0`) and 41/41 feature leakage canaries (`max sym-AUC = 0.584624 <= 0.90`):

1. **`EXP1_CGJI_PHYS_NMS`** (Label-free Gallardo–Meju Cross-Gradient Collinearity + Piedmont Break-in-Slope Scarp Dipole + Hydrothermal Upflow Breach on a 1-px transverse NMS crest skeleton):
   - `HOLDOUT-DTI = 0.060929` (`95% CI [0.049968, 0.073197]`, `GEMSDOE32-HIDE-RECOVER-v3.1`, `n_withheld_positives = 22,232`).
   - **`HOLDOUT-DTI = 0.115633` (`95% CI [0.097758, 0.134248]`, `GEMSDOE32-SGMC-CAL-v3.0`, `n_withheld_positives = 62,703`)** — #1 highest SGMC regional lithological contact score (vs `GEMSDOE32` `0.096060`).
   - Non-lattice 21-peer uniqueness: `max 3-px overlap = 40.99% <= 70%` (`25.51%` vs `GEMSDOE32`), `|Spearman| <= 0.2939 <= 0.90`.
2. **`EXP2_CGJI_OOF_HGB`** (Quadrant-blocked fold-local `HistGradientBoostingClassifier` on the 40-channel `CGJI-HTB` + v2 stack over the NMS crest):
   - **`HOLDOUT-DTI = 0.099671` (`95% CI [0.085008, 0.113669]`, `GEMSDOE32-HIDE-RECOVER-v3.1`, `n_withheld_positives = 22,232`)** — #1 highest clean fold-local hide-and-recover score (vs `GEMSDOE32` `D2.8 B=2` fold-local OOF `0.099202`, `95% CI [0.085951, 0.112668]`).
   - `HOLDOUT-DTI = 0.083354` (`95% CI [0.072470, 0.093394]`, `GEMSDOE32-SGMC-CAL-v3.0`, `n_withheld_positives = 62,703`).
   - Non-lattice 21-peer uniqueness: `max 3-px overlap = 58.70% <= 70%` (`45.28%` vs `GEMSDOE32`), `|Spearman| <= 0.2909 <= 0.90`.
3. **`EXP3_CGJI_EK_HYBRID`** (Expected-300m-kernel-credit crest-coherent hybrid):
   - `HOLDOUT-DTI = 0.096477` (`95% CI [0.082813, 0.110499]`, `GEMSDOE32-HIDE-RECOVER-v3.1`); `HOLDOUT-DTI = 0.092496` (`95% CI [0.079882, 0.104520]`, `GEMSDOE32-SGMC-CAL-v3.0`).
   - Non-lattice 21-peer uniqueness: `max 3-px overlap = 57.35% <= 70%` (`43.77%` vs `GEMSDOE32`), `|Spearman| <= 0.2887 <= 0.90`.

See [`docs/HYPOTHESES.md`](../HYPOTHESES.md) and [`evidence/cgji_htb_experiments_20261027.json`](../evidence/cgji_htb_experiments_20261027.json) for full specifications of the 5-hypothesis slate (`H1: CGJI-HTB`, `H2: PBTD`, `H3: CSFD`, `H4: RMWD`, `H5: USGS-3DEP-QF`).
