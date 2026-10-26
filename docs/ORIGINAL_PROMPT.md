# Standing request and protocol — reconstructed archive

**Read on every session.** This is a reconstruction of the consequential user requirements retained in the session memory, **not** a verbatim copy of the original prompt, whose full text is not available here. A parallel lane's earlier [prompt-in-substance archive](mplc/ORIGINAL_PROMPT_MPLC.md) preserves additional details, but also does not reproduce the full original or the roughly 90 listed historical scores. Later user instructions can add or amend it. Maximize P(Win); Own the Outcome.

## Objective and deliverables

Perform an autonomous deep review and improve this competition repository toward a genuinely unique, high-scoring, single-band GeoTIFF readily downloadable from a clean GitHub Pages executive summary. Use strict automatic validation, and prominently say whether any specific file is actually acceptable to download and submit. Explain the prior portal rejection `Predicted values must be in range [0, 1]` without inventing its cause or claiming an untested fix. Provide a nine-site executive summary for GEMSDOE24/25/27/28/30/31/32/33/36, a scientific account of the owner-reported GEMSDOE32 h33 0.2778 result, cited official/free/licensable sources, transparent limitations, a current-information feed, and future upload instructions and a unique note. Never manufacture a live-score prediction.

Rank 3–5 previously untried/differentiated geological hypotheses by expected benefit and cost, with input layers, transforms, hidden-fault mechanism, meaningful novelty relative to the examined record, named non-fault mimics and data availability. Test the top candidate with spatial-blocked holdout before spending a slot, **unless a mandatory duplicate STOP prohibits a further run**. Do not copy a previous submission except to learn. Negative results are deliverables.

## Mandatory parallel-run protocol

1. **Lane and uniqueness:** stay in one assigned method lane. Before placement check the surface and preregistered support, then check final dots. If rank correlation with any registry raster exceeds 0.90 **or** more than 70% of candidate dots lie within 3 pixels of any one registry raster, log a duplicate and stop. No lattice/density exemption was authorized; an incomplete registry is not a global pass.
2. **Reuse and fold isolation:** use the shared cached feature stack, `evaluate_holdout.py`, and `submission_writer.py`. Withhold whole fault segments with a spatial buffer; compute every catalogue-derived feature and emission from visible faults only; mask visible faults pixel-exactly. Score pooled DTI, α=0.2, β=0.8, triangular 300 m kernel. Fix a shared tool once in the template, never as a private fork.
3. **Score attribution:** label scores `HOLDOUT-DTI` with evaluator version, withheld-positive count and 95% CI, or `ORGANIZER-CONFIRMED` copied from an actual submission-page receipt. User/owner reports without receipts must be identified as such. A projection is not a score.
4. **Leakage canary:** test each feature alone on the holdout; AUC >0.90 is leakage until disproven.
5. **One JSON card:** include hypothesis, mechanism, named non-fault mimic, holdout DTI and CI, registry correlation/overlap, raster SHA-256, validator output including no NaN in footprint, [0,1] values and CRS/shape/transform match, submission name and note ≤140 characters, and verdict promote/negative.
6. **Budget and selector:** at most three experiments or two hours. Do not pick or promote a real weekly submission; a separate selector step must decide. Respect the authenticated platform's actual weekly cap.

## Execution and rigor

Handle previous sessions' next steps first. Do not require manual inspection or validation. Verify claims line by line and flag irregularities; use only sources with appropriate rights and cite them. Carry out three review passes: implement/verify, find/fix bugs, then recheck the full request. Create and merge a PR only if GitHub authentication and repository permissions allow; never imply a merge, score, download readiness, slot use, or scheduled feed success that has not occurred.

The current lane has stopped. See the README and [executive summary](executive-summary.html) for the present negative result, [current run card](evidence/current_run_card.json) for machine-readable evidence, and [review record](review-record.md) for what remains unproven.
