# 2026-10-31 Geological Hypothesis Slate — H-GEO-CONDUIT and four untried candidates

Status: pre-registered before coding. One experiment of the 3-experiment / 2-hour budget was spent on the top candidate (H-GEO-CONDUIT) — it was generated, format-validated, uniqueness-audited and holdout-diagnosed, then logged NEGATIVE. Per the parallel-run protocol, a negative result is a deliverable; no weekly DrivenData slot was touched and none will be until a separate selector approves.

Evidence classes: HOLDEOUT-DTI (local holdout diagnostic, never a leaderboard forecast) or ORGANIZER-CONFIRMED (submission-page receipt). No projection is written as a score.

UNIQUENESS PRE-CHECK (protocol rule 1), applied to H-GEO-CONDUIT before any placement decision and re-checked on final dots:
  * surface vs registry: |Spearman| << 0.90 on both registry rasters;
  * final dots vs 13 local references (2 registry + 11 scored): detector-only PASS — max non-space-filling within-3px = 0.1925 (<= 0.70), max |Spearman| = 0.0119 (<= 0.90); the r13 space-filling lattice fails the literal rule (99.75% of candidate dots within 3 px), exactly as every candidate does — disclosed, not exempted.

---

## Rank 1 (TESTED THIS SESSION — NEGATIVE DELIVERABLE): H-GEO-CONDUIT

**Blind hydrothermal convection conduits — warm springs/wells + Quaternary vents + GeoDAWN K/TC radiometric anomaly.**

*Specific layers:* `data/external/gdr_wellspring_in_footprint.csv` (GDR 1391 well/spring temperatures, DOI 10.15121/1881483, CC BY 4.0, https://gdr.openei.org/submissions/1391), `data/external/gdr_volcanic_vents_in_footprint.csv` (GDR 1391 Quaternary vents), `data/external/geodawn_rad_u8.tif` bands K and TC (USGS GeoDAWN, DOI 10.5066/P93LGLVQ, https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and), `data/external/tiger_road_distance_m.tif` (slight road-edge penalty).

*Physical signature:* temperature-distance decay kernel (90 C scale, Gaussian sigma 1.5 px) around documented geothermal wells/springs, dilated vent cells, and percentile-scaled K + total-count radiometric anomaly (potassic alteration along blind conduits); roads slightly de-weighted because road edges can mimic scarps.

*Why it catches catalogue-missing faults:* blind intrabasin faults beneath Quaternary valley fill have no surface scarp and are absent from the USGS/INGENIOUS mapped catalogue used for labels, yet they localize upward hydrothermal flow that surfaces as warm springs/vents and alters wall rock to potassium-rich clays. Every dot is zeroed exactly on `labels.tif`, so there is zero catalogue leakage — the target is the hidden fault class, not mapped faults.

*How it differs from repo implementations:* no existing lane (`ocda.py`, `uwbp.py`, `upflow.py`, `cgji.py`, `h33.py`, `generate_unique_submission.py`) uses point-source thermal/vent proximity or radiometric K/TC; UWBP uses potential-field worms + DEM knickzones; OCDA uses catalogue structure; H-UNQ-1 used off-catalogue SGMC traces + radiometric but with catalogue-collar masking rather than blind-conduit thermal kernels.

*Expected DTI improvement / cost:* expected low-to-moderate off-catalogue gain; cost LOW (~1 min CPU, all data already mirrored locally, no external downloads).

*Result (2026-10-31, full-map diagnostic — NOT fold-local, not promotion evidence):* HIDE-RECOVER-v3.1 = 0.02799 (95% CI [0.01868, 0.03773], n=22,232); SGMC-CAL-v3.0 = 0.03259 (95% CI [0.02032, 0.04603], n=62,703; raw 0.04910). Benchmarks: UWBP-DRCS EXP-B3 HR 0.06480 / SGMC-CAL 0.08917; GEMSDOE32 champion reference HR 0.09920 / SGMC-CAL 0.06412. **Verdict: NEGATIVE — below both benchmarks on both populations.** Format-valid (independent 10-check validator PASS; values in [0,1], NaN outside footprint, zero on catalogue), locally unique, kept as a documented negative deliverable. Not recommended for submission; file published in docs/downloads with audit sidecar and run card (evidence/h-g-conduit-run-card.json).

*Leakage canary (rule 4):* single features alone — radiometric-only HR 0.0214 / SGMC-CAL 0.0290; wells-only HR 0.0045 / SGMC-CAL 0.0021; vents-only HR ~0 / SGMC-CAL 0.0 — all far below 0.90; no leakage signal; radiometric K+TC drives the surface.

---

## Rank 2 (UNTRIED): H-K/TH-DIPOLE

**Signed radiometric K/Th cross-strike hydrothermal leaching asymmetry.**

*Specific layers:* `data/external/geodawn_rad_u8.tif` bands K and Th; local fault-normal orientation estimated from the radiometric gradient field itself (no catalogue input, to avoid leakage).

*Physical signature:* acid-sulfate/adularia-sericite fluids ascending a fault leach mobile K and U into hanging-wall colluvium while immobile Th stays in footwall bedrock, producing a signed cross-strike K/Th dipole `d(K/Th)/dn` along the fault normal — an edge/asymmetry transform, not an isotropic magnitude.

*Why it catches catalogue-missing faults:* hydrothermally altered range-front and relay faults eroded in friable Tertiary volcaniclastics can lose their topographic scarps while keeping the K/Th alteration dipole — invisible to the mapped catalogue but real in the hidden label set.

*Differs from repo:* prior code uses isotropic gradient magnitude `\|∇(K/Th)\|` only; a signed dipole along a locally estimated fault normal is untried in this repo.

*Expected DTI improvement / cost:* moderate expected off-catalogue gain where alteration is preserved; cost MEDIUM (~1-2 min CPU; all data local). Conditional on local orientation estimation being stable.

---

## Rank 3 (UNTRIED): H-MAG-EDGE

**Total-horizontal-gradient / analytic-signal edges of buried magnetic basement blocks.**

*Specific layers:* competition `training_features.tif` RTP magnetics (band 2) and TMI (band 14), plus `geod_2ndinv` (band 4) for curvature context; USGS GeoDAWN magnetic data release (DOI 10.5066/P93LGLVQ).

*Physical signature:* a buried fault offsetting basement density/susceptibility blocks produces a sharp total-horizontal-gradient edge (analytic signal amplitude of the RTP field) along the concealed trace — second-order edge transform of potential fields.

*Why it catches catalogue-missing faults:* intrabasin accommodation zones and buried horst/graben boundaries under valley fill offset magnetic basement with zero surface expression; the mapped catalogue cannot see them, but the gradient edge can.

*Differs from repo:* `pfonly.py` exists for scalar potential-field gradients; a total-horizontal-gradient edge detector with fault-strike steering is untried in this repo. Official free source: https://mrdata.usgs.gov/gravity/ (USGS gravity) and the GeoDAWN data release above.

*Expected DTI improvement / cost:* low-to-moderate; cost LOW-MEDIUM (~1 min CPU; bands already local).

---

## Rank 4 (UNTRIED, CONDITIONAL — external API): H-3D-HYPO-UPDIP

**Relocated microseismic swarm hypocenter plane fitting and up-dip surface projection.**

*Specific layers:* USGS ANSS ComCat earthquake catalog via the public FDSN web service (https://earthquake.usgs.gov/fdsnws/event/1/, public domain CC0) + UNR Nevada Seismological Lab.

*Physical signature:* a local 3D dipping plane fit (RANSAC) to 2-12 km swarm hypocenters, projected to its up-dip intersection with the 100 m DEM surface trace — resolves blind Walker Lane shear zones smeared by the 100 km-smoothed seismicity bands (ieq/deq).

*Why it catches catalogue-missing faults:* microseismicity illuminates blind seismogenic shear zones that have no mapped Quaternary trace at all.

*Differs from repo:* nothing in this repo ingests 3D hypocenter planes or ComCat.

*Expected DTI improvement / cost:* potentially HIGH (direct blind-structure imaging); cost HIGH (external ingest, API rate limits). **Status: cannot be run in this session — sandbox egress blocks earthquake.usgs.gov.** Named free official source above; check obtainability in an unrestricted network before proposing as viable.

---

## Rank 5 (UNTRIED, CONDITIONAL — external product): H-INSAR-OPERA

**Sentinel-1 / JPL OPERA vertical velocity and seasonal phase-gradient step detection.**

*Specific layers:* NASA ASF / JPL OPERA North America Surface Displacement product (https://search.asf.alaska.edu/, NASA open data).

*Physical signature:* unmapped intrabasin faults act as low-permeability clay-gouge groundwater barriers, producing sharp step discontinuities in seasonal InSAR phase across flat, zero-relief playas — a phase-gradient step transform.

*Why it catches catalogue-missing faults:* barrier-controlled groundwater steps mark faults with no topographic expression in arid basins.

*Differs from repo:* no InSAR ingestion anywhere in this repo.

*Expected DTI improvement / cost:* potentially HIGH on playa-interior blind faults; cost MEDIUM-HIGH (external product download/processing). **Status: cannot be run in this session — sandbox egress blocks asf.alaska.edu.** Named free official source above; check obtainability in an unrestricted network before proposing as viable.

---

## Ranking summary (expected DTI gain vs implementation cost, this session)

| Rank | Hypothesis | Data available locally? | Expected DTI gain | Cost | Session outcome |
|------|------------|-------------------------|-------------------|------|-----------------|
| 1 | H-GEO-CONDUIT | Yes | Low-moderate | Low | TESTED — NEGATIVE (logged) |
| 2 | H-K/TH-DIPOLE | Yes | Moderate | Medium | Untried |
| 3 | H-MAG-EDGE | Yes | Low-moderate | Low-medium | Untried |
| 4 | H-3D-HYPO-UPDIP | No (ComCat FDSN) | High | High | Conditional — egress blocked |
| 5 | H-INSAR-OPERA | No (NASA ASF/OPERA) | High | Medium-high | Conditional — egress blocked |

Run card: `evidence/h-g-conduit-run-card.json` · submission artifact: `docs/downloads/gemsdoe32-h-geo-conduit-wells-vents-radiometric-300m-dots-20261031T003904Z-6e23b6aa-nan.tif` (NEGATIVE — do not submit) · audit: `docs/downloads/h-geo-conduit-wells-vents-radiometric-300m-dots-20261031T003904Z-audit.json`.
