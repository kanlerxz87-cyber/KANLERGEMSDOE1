# Three-pass review record

**Date:** 2026-10-26 UTC. **Outcome:** negative; do not submit any existing TIFF. This review did not generate a new candidate, spend a competition slot, or rerun the stopped lane.

## Pass 1 — implement and verify the evidence

- Restored all 26 owner-mirrored files from pinned commits with size and SHA-256 checks; prepared the 19 input bands. Receipts are `data/restore_receipt.json` and `data/prepared_manifest.json`. Pins attest mirror bytes, not organizer origin. The unauthenticated mirrored sample has 60,988 positives on labels, contrary to the description of an all-zero sample; it is used only to establish a grid and footprint.
- Fetched and independently checked nine pinned focus champion TIFFs and the registered spacing-5 lattice. `scripts/audit_existing_candidates.py --restore` reproduces the comparisons and writes `evidence/protocol_audit_20261026.json`, its Pages copy, and the one current negative JSON card. This is an audit of existing bytes, not a candidate experiment.
- H1/H2/H3 have directional 3-pixel lattice overlaps 99.39375%, 99.5875% and 99.190625%. Any exceeds the literal 70% stop threshold. H1 passes the nine-focus-only overlap subset, but that is not the entire registry and does not erase the lattice failure. Every one of the nine focus champions exceeds 70% overlap with another focus champion.
- During PR reconciliation, main advanced with a separate pre-existing MPLC lane. Reopened its historical raster only: SHA-256 `fe4b8d742c1b12f60727ae22d4ae2dd96e6bfcb76b7f35e985d0e707bb816db3`, 37,654 dots, 99.952196% lattice overlap. Its earlier discrete-peers-only uniqueness claim is not a literal all-registry pass. No MPLC experiment was rerun, and its fold provenance was not independently replayed. Its old generator and experiment entry points now stop before running.
- Confirmed a budget-specific saturation bound: of 5,106,385 eligible off-label pixels, only 6,514 lie outside the lattice halo; a 32,000-dot map must overlap at least 79.64375%. This is not a proof for every sparse budget. Exact binary support for 25/30 is identical; 31 and 32 equal the 25 support after the >1- and >2-pixel catalogue distance tests, respectively.
- Replaced the executable IEDR experiment runner with an explicit STOP. Preserved original TIFFs and historical metrics for provenance, but annotated their JSONs as superseded. Removed contest download links; root pages redirect to the actual `docs/` Pages site.

## Pass 2 — find and fix defects

- **Holdout:** prior final maps used full-catalogue placement/collar masks; archived holdouts and canaries are inadmissible. Shared hide-and-recover v3.1 includes false positives in truth-empty cells and rejects nonbinary/nonfinite predictions. A full map requires an explicit diagnostic opt-in; per-cell arrays cannot prove visible-only provenance. Catalogue/SGMC grids and binary values are checked against the sample.
- **Uniqueness and selection:** no lattice/density exemption; candidate and reference support validated, surface and final checks required, missing/undefined comparisons and incomplete inventory fail closed. Promotion recommendations require all expected canaries, a separately verified fold-local replay, paired positive improvement and an authenticated template. A separate selector still decides any slot.
- **Writer:** no clipping, thresholding or hidden mask repair; preserves soft probabilities, rejects bad/outside/on-catalogue pixels, validates geometry/range/nodata and stages TIFFs, JSON and one-file ZIP. Collision/failure rolls back linked outputs; the local format result does not guarantee organizer acceptance.
- **Shared scientific code:** fixed principal-curvature eigenvalue sign/magnitude; distinguished bright-ridge and both-polarity callers; corrected a thermal-conduit magnetic term that previously used elevation gradients; fixed NAD83 and containing-pixel conversion in the palaeothermal helper. Historical results remain tied to old code. Derived feature caches require a new schema/source/sample/cache hash receipt and must be rebuilt before use; the real corrected stack was not rebuilt or evaluated after STOP. The original 19 prepared input-band caches are unaffected.
- **Restoration and Pages:** enforced safe relative destinations, hashes and sizes, and aligned source CRS/shape/transform. Fixed the actual `/docs` pages rather than only the obsolete root files; eliminated unsupported claims about uniqueness, live score and portal acceptance. A daily Pages build attempts a public-board refresh and falls back to a dated snapshot; it has not yet been observed on GitHub Actions.
- **Vendor provenance:** every recorded source hash matched at review time, but `vendor/README.md` and `vendor/PROVENANCE.json` give different source descriptions and cite a missing registry file. See `vendor/PROVENANCE-NOTES.md`; neither source attribution was silently rewritten.

## Pass 3 — full request recheck

| Request | Result and limitation |
|---|---|
| Unique, high-scoring TIFF with easy contest download | **Not met.** Literal registry STOP; there is no demonstrated admissible high-scoring candidate, so no authorized download or portal note. |
| Test the strongest new hypothesis before a slot | **Blocked by mandatory STOP.** Four future directions are ranked, but no new lane experiment was run and no slot was used. USGS event data were not downloaded. |
| Nine-site executive summary | **Provided with attribution.** Owner-reported scores, pinned file names/hashes, and all 81 directional pair checks are disclosed; no submission receipts bind score to file. |
| Explain h33 0.2778 | **Mechanism and limits provided.** Nested support was measured; DTI pruning is a plausible mechanism, not proof of private-score causation. |
| Score and 95% uncertainty | **No valid new HOLDOUT-DTI.** The old v3.0 proxy and CI remain archival and explicitly inadmissible; no public leaderboard score was forecast. |
| Automatic format checks and rejection guidance | **Implemented/tested locally.** Exact grid, footprint, dtype, range, nodata, exclusion and safe staging are checked; the organizer template and portal acceptance remain unverified. |
| Official sources and feed | **Sources cited; feed conditional.** Organizer public leaderboard, staff clarifications, USGS and GDR sources linked. Pages has a tested parser and stale fallback, not an observed successful scheduled deployment. |
| Prompt archive / three passes | **Provided.** Exact original wording is unavailable; the standing archive is explicitly a reconstruction. |
| PR / merge and hosted Pages | **External action not established by this document.** Check the actual GitHub operation result and deployment status; never assume success from local files. |

## Automated verification

- `python -m unittest discover -s tests -v` — 30 tests, including literal saturation, whole-segment hiding, zero-truth false positives, exact DTI vs brute force, probability preservation and rollback, cache invalidation, the stopped parallel lane, actual `/docs` links, and feed success/fallback.
- `python scripts/prepare_data.py` — prepared 19 aligned bands; 5,167,373 footprint pixels, 60,988 catalogue positives; recorded 58,171 sentinel band-pixels.
- `python scripts/audit_existing_candidates.py --restore` — reproduced the lattice STOP, focus matrix and negative card. The 81 comparisons include each site's self-comparison.
- Local output checks are automated. Tests do not authenticate data mirrors, prove independent per-fold feature construction, observe a GitHub Pages deployment, establish full-registry coverage, or replace an organizer receipt.
