# Standing request — 2026-10-31 (CONDENSED record, not verbatim)

This is a condensed list of the 2026-10-31 request's requirements, kept so every future session reads the same constraints. The full wording lives in the session transcript. Items marked **active** still govern the work.

## Deliverables (active)
1. Executive summary per GEMSDOE site (24, 25, 27, 28, 30, 31, 32, 33, 36): best submission, file to download, estimated score labelled HOLDOUT-DTI or ORGANIZER-CONFIRMED (never a projection written as a score), and uniqueness versus the other listed sites. → `docs/executive-summary-20261031.html`
2. Explain why GEMSDOE32 `h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros` scored 0.2778 and whether a higher-scoring submission is buildable. Leaderboard top is unresolved (user reported 0.4413 and, elsewhere, 0.3195). → executive summary §3 and irregularities I-3, I-4.
3. A unique single-band GeoTIFF (EPSG:32611, shape/transform matching the sample, values in [0,1]), easy to download, auto-validated with no human inspector, with clear "OK to download and submit" status, a unique name, and a note of 140 characters or fewer. → `docs/downloads/kanlergemsdoe1-DOWNLOAD-ocda-mscs-exp3-nan.tif`.
4. 3–5 untried geological hypotheses, ranked by expected DTI gain and cost; validate the top one on the spatially blocked holdout before spending any submission slot. → `docs/research/hypotheses-20261031.md`.
5. GitHub Pages: clean UI, executive summary at the top, how-to-submit page with error avoidance for "Predicted values must be in range [0, 1]". → `docs/executive-summary-20261031.html`, `docs/how-to-submit.html`.
6. Store this standing prompt in README.md. → README §0 and §5.
7. Multi-pass work (implement, review, re-check), then PR and merge to main, with next steps and limitations listed.

## Rules (active)
- Never copy a prior GEMSDOE submission except for learning. Submissions must be unique.
- Validation is automatic. No human inspector. Inspection happens through the project.
- Do not pick submissions. Promotion to a weekly slot is a separate selector step.
- Label every score as HOLDOUT-DTI (evaluator version, withheld-positive count, 95% CI) or ORGANIZER-CONFIRMED.
- Negative results are deliverables; log them.
- No hallucinated sources. Provide official links for manual review; flag irregularities.
- Do not spend a submission slot on an idea that has not beaten the current holdout best.
- If a candidate needs external data, name a free official source and verify it is obtainable from the sandbox.
- Parallel-run protocol: duplicate rule = Spearman > 0.90 or > 70% of dots within 3 px; leakage canary = single-feature AUC > 0.90; run card JSON; budget of 3 experiments or 2 hours.
- Apply Arena core values: maximize P(Win), own the outcome.

## Status against these rules (2026-10-31)
- Three experiments were run (budget reached). All were negative against the holdout best (0.1058).
- The recommended download is the best tested file that passes the uniqueness gate. Its literal-rule clause is blocked by an unsatisfiable registry raster, which needs a team decision.
- Organizer score: UNKNOWN. No portal receipt is available to the sandbox.
