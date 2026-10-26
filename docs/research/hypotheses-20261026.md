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
