# GEMS Field Notes

> **Submission status: BLOCKED.** No new GeoTIFF was generated or approved, no holdout experiment was run, and no competition slot was used. Historical files linked from the site are **research artifacts, not authorized submissions**. See the [submission guide](https://kanlerxz87-cyber.github.io/KANLERGEMSDOE1/executive-summary.html), [negative run card](evidence/run-card.json), and [evidence review](research/review-and-next-steps.md).

An independent, evidence-first research and decision record for the DOE Geologic Enhanced Mapping System (GEMS) Prize fault-mapping challenge. The goal is a **genuinely new, high-performing, reproducible** GeoTIFF—not a repackaged earlier submission. The scientific target is previously unmapped faults associated with hidden geothermal systems; a spatial holdout is only a proxy for the organizers' hidden labels.

**Read first in every new session:** this README → [standing project brief](research/project-brief.md) → [preregistration](research/preregistration.md) → [current run card](evidence/run-card.json). The brief accurately reconstructs the requirements available in this session; the original full prompt was not available verbatim, so it is not represented as a transcript. If the user supplies the complete original, preserve it separately and link it here.

## Executive decision · 26 October 2026

- The [public leaderboard](https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/) was observed at **0.4437** around 21:37 UTC. It does **not** identify the user's file. No leaderboard is automatically scraped; DrivenData's terms prohibit automated monitoring.
- The user's reported **0.2778** for GEMSDOE32 H33 has no organizer receipt available here. Its attribution and the reason for the reported performance remain unverified. The pinned H33 support is exactly the D2.8 support with dots within two pixels of the mirrored known-fault catalogue removed. That may reduce false-positive mass, but can also remove true nearby hidden faults; the causal effect on a hidden score is unknown.
- Under the literal shared uniqueness rule, the registered lattice covers **5,160,724 of 5,167,373** cells of the provisional owner-mirrored footprint within three pixels. At the H33 budget of 37,654 distinct dots, at least **82.34%** must overlap it, exceeding 70%; any candidate with **22,164 or more** dots must fail. Smaller candidates are not categorically ruled out. The footprint is not authenticated organizer data, and this is a mathematical bound, not a candidate test or a score.
- Two sibling recommendations conflict with this broader registry: GEMSDOE27 H31 and GEMSDOE31 H31-X have **99.61%** and **99.34%** lattice overlap, respectively. Neither is approved here. The nine focus-site historical supports also each fail against at least one audited focus peer.
- The mandatory shared 35-channel feature cache is missing and the sample is an unauthenticated owner mirror. The shared pre-placement overlap gate and holdout bookkeeping have reproduced defects; the writer/holdout CLI also silently binarize probabilities. They are tracked in upstream issues [#42](https://github.com/buffedlizard55-lab/GEMSDOE32/issues/42), [#41](https://github.com/buffedlizard55-lab/GEMSDOE32/issues/41), and [#37](https://github.com/buffedlizard55-lab/GEMSDOE32/issues/37). The template is read-only to this account; it has not been privately forked or patched. Do not exempt the lattice, target rare lattice holes, or use a weekly slot to work around these blockers.

### Nine-site historical snapshot

These file-to-score associations were user-reported, not verified against organizer receipts. They are neither forecasts nor candidates. The [interactive table](https://kanlerxz87-cyber.github.io/KANLERGEMSDOE1/#portfolio) links each pinned research file and records its nearest audited peer; [manifest](registry/focus_sites.json), [full audit](evidence/focus-site-audit-20261026.json).

| Site | Reported historical claim | Decision |
|---|---:|---|
| GEMSDOE24 | 0.2477 | Historical research only; peer overlap fails |
| GEMSDOE25 | 0.2600 | Historical research only; same in-footprint mask as 30 |
| GEMSDOE27 | 0.2449 | Historical research only; peer overlap fails |
| GEMSDOE28 | 0.2710 | Historical research only; peer overlap fails |
| GEMSDOE30 | 0.2600 | Historical research only; same in-footprint mask as 25 |
| GEMSDOE31 | 0.2708 | Historical research only; peer overlap fails |
| GEMSDOE32 H33 | 0.2778 | Attribution unverified; peer/lattice overlap fails |
| GEMSDOE33 | 0.2632 | Historical research only; peer overlap fails |
| GEMSDOE36 | 0.2750 | Historical research only; peer overlap fails |

## Research plan

[Preregistration](research/preregistration.md) ranks four falsifiable hypotheses before experimentation. The preferred lane is a contrast of temperature/chemistry residuals at geothermal sites paired across independent potential-field edges. Lithologic contacts, fluid mixing, sampling density, and inconsistent measurements are named non-fault mimics. Its novelty, data coverage, reproducibility and predictive benefit remain to be tested; exclude the well dataset's `dist_known_fault_px` from predictive features. Alternatives involve directional potential-field edges, multiscale topography, and geology-aware hydrothermal intersections.

Before promoting anything, fix the shared template **at its source**, agree the registry interpretation centrally, obtain the required shared cache and authenticate the organizer sample. Then test each feature for leakage and evaluate whole withheld fault segments with a spatial buffer using the unmodified shared holdout evaluator. Only after full registry comparisons, an improved same-holdout result, byte-level format validation and a separate cap-aware selector can a candidate be marked submit-ready. A holdout result is not an organizer score. The [detailed review](research/review-and-next-steps.md) gives sources and next steps.

## Reproduce the audit

Requires Python 3.10+, GitHub CLI, and access to the pinned public GitHub artifacts. Mirror restoration downloads hundreds of MB; generated data and caches are ignored by Git. These are owner mirrors, **not authenticated organizer assets**. No credentials are requested or stored by this project.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
bash scripts/restore_owner_mirrors.sh     # pinned core owner mirrors
python scripts/fetch_focus_rasters.py        # nine historical files, lattice, two sibling claims
python scripts/prepare_owner_mirror.py               # optional shared 19-band preparation; NOT the missing 35-channel cache
OPENBLAS_NUM_THREADS=1 python scripts/audit_focus.py
python scripts/build_site.py
python -m pytest -q
python scripts/check_shared_gate.py           # currently exits 1: known preview-gate defect reproduced
python scripts/check_shared_holdout.py        # currently exits 1: known holdout-bookkeeping defect reproduced
```

The template bootstrap verifies the pinned archive SHA-256, rejects unsafe archive entries, and refreshes its ignored extracted tree before use. The audit checks SHA-256, common raster geometry, in-footprint binary values and directional three-pixel overlaps. Site generation is intentionally fail-closed and only supports the current negative decision. Tests cover geometry, range, hashes, archive restoration, capacity boundaries, local links, the run card and the known shared-gate and holdout-bookkeeping bugs. Saved-site copies of the audit and run card are under `docs/data/`.

## Key sources and limitations

- [Official problem, format and metric](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/); [known-fault scoring clarification](https://community.drivendata.org/t/scoring-clarification-are-known-usgs-ingenious-faults-masked-when-scoring-and-are-they-in-the-final-round-label-set/11516/4); [pooled scoring clarification](https://community.drivendata.org/t/leaderboard-aggregation-pooled-over-public-test-pixels-or-mean-of-per-chunk-scores/11550/2).
- [Official reference solution](https://github.com/drivendataorg/gems-prize-reference-solution); [USGS GeoDAWN magnetic and radiometric data](https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and); [GDR INGENIOUS compilation](https://gdr.openei.org/submissions/1391).
- [Official rules](https://docs.nlr.gov/docs/fy26osti/96647.pdf) and [DrivenData terms](https://www.drivendata.org/termsofuse/). Weekly availability, receipts, authoritative organizer files, and later rule changes require confirmation through legitimate access.
- [Research review](research/review-and-next-steps.md), [site claims manifest](registry/current_site_claims.json), and [verification record](research/verification.md). GitHub freshness checks on the website are best effort, can be rate-limited, and never refresh scores.
