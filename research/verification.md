# Three-pass verification record

Date: 2026-10-26 UTC. This record describes the audit on branch `arena/39575ccf-kanlergemsdoe1`; it does not authorize a competition entry.

## Pass 1 — implementation and verification

- Restored four checksum-pinned owner mirrors with the unchanged shared restorer; prepared the 19-band source cache with the unchanged shared preparation tool after independent hash/CRS/shape/transform checks. The required pre-existing 35-channel stack remains missing. Mirrors are not organizer authentication.
- Downloaded and hashed the nine pinned historical rasters, the registered lattice and two conflicting sibling recommendations. Recomputed binary support, directional overlap, H33 lineage and the exact lattice-capacity bound.
- After concurrent main-branch work appeared, preserved its three research TIFFs and original run cards and reopened the saved TIFF bytes against the provisional grid. H1/H2/H3 lattice overlaps are 99.39375%, 99.58750%, 99.190625%; each fails the literal gate. Their full-catalogue placement collar and nonblocked canaries make the recorded holdout reports unsuitable for promotion.
- Generated a negative-only Pages site, run card and two JSON audits. Research file links are explicitly labeled; the submission control is disabled. The original parallel site text is retained as non-authoritative source snapshots in `research/archive/parallel-site-20261026/`.
- `OPENBLAS_NUM_THREADS=1 python -m pytest -q`: **47 passed**, 17 subtests passed, 10 upstream rasterio/affine deprecation warnings. The suite includes the existing vendored evaluator tests and this audit's synthetic and site tests. `python -m compileall -q scripts tests` and `git diff --check origin/main` passed. The merge-index check also reported two pre-existing trailing blank lines in unchanged upstream source files; they were not edited to avoid forking the shared template.
- HTTP smoke tests returned 200 for the overview, guide, evidence, audit JSON and a research TIFF. Headless Chromium checked 1440 px desktop and 390 px mobile: no document-width overflow and no page errors; the mobile tables scroll horizontally. A simulated GitHub API success/change/rate-limit mix produced the expected freshness labels. A separate root-source test verified the root landing page redirects to `docs/index.html`.

## Pass 2 — bugs, edge cases and fixes

- Tested zero-dot and exact 70% capacity boundaries, malformed counts, nonfinite/in-range values, raster grid/band/hash mismatch, atomic downloads, unsafe archive paths/symlinks and restoring modified template files. Empty supports fail closed.
- The shared surface gate ignored 100% overlap when ranks were uncorrelated. The unchanged shared implementation still fails the synthetic probe; reported upstream as [#42](https://github.com/buffedlizard55-lab/GEMSDOE32/issues/42).
- Independently reproduced the shared zero-truth-cell pooled false-positive omission: synthetic fold TP/FP/FN `1/7/0`, pooled blocks `1/0/0`. It is not a real score; [#41](https://github.com/buffedlizard55-lab/GEMSDOE32/issues/41) already reports it. The shared writer/holdout CLI's probability binarization is tracked by [#37](https://github.com/buffedlizard55-lab/GEMSDOE32/issues/37).
- Upstream permissions are read-only. No private evaluator, writer or gate fix was claimed. The previous parallel branch's local filename-prefix alteration in `src/gems32/submission.py` was restored to the pinned upstream bytes; its session-specific experiment script now stops before execution, with historical code preserved in Git history.
- Changed stale Pages routes into safe redirects, annotated superseded historical JSON rather than deleting it, preserved the parallel TIFFs, and reconciled the newer `main` without presenting a narrower-registry or zero-outside claim as approval.

## Pass 3 — requirement recheck

| Requirement | Finding |
|---|---|
| New unique, format-validated TIFF | **Not completed.** This audit generated none. Three pre-existing parallel files fail literal uniqueness; their in-footprint format was checked only against an unauthenticated mirror. |
| Submit status and instructions | **Met safely.** No file is approved; research downloads and future conditional instructions are clearly separated. No slot selected by this audit. |
| Nine focus sites, H33 and leaderboard | **Met with limits.** Pinned files and overlap matrix are auditable; 0.2778 attribution has no receipt; 0.4437 is a dated public-board observation, not a file score. |
| 3–5 hypotheses and top holdout | **Four preregistered; holdout blocked.** No effect is claimed. A separate previous run already records three experiments, so its budget is exhausted. |
| Shared protocol, leakage and saved bytes | **Blocked, not bypassed.** Cache, organizer sample, shared repairs, full-registry replay and compliant spatial validation remain prerequisites. The prior experiment is guarded rather than silently fixed or repeated. |
| Original prompt and future sessions | **Partial but honest.** `research/project-brief.md` and the prior `docs/ORIGINAL_PROMPT.md` are explicitly labeled reconstructions, not a verbatim prompt; README and `AGENTS.md` require them to be read. |
| Freshness, provenance and terms | **Conservative.** Only GitHub head freshness is automated; DrivenData is linked, never polled. Public data licenses and mirror caveats are recorded. |
| PR, merge and live Pages | To be recorded after the GitHub operations; local checks do not prove deployment. |
