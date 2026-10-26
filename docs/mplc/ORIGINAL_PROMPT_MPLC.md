# Earlier prompt-in-substance reconstruction (2026-10-26)

This is a prior summary, not the complete verbatim original. Read it alongside the current [standing protocol](../ORIGINAL_PROMPT.md) and current audit; historical leaderboard values and uniqueness claims are not receipts.

Focus on the highest-scoring submissions from GEMSDOE24, 25, 27, 28, 30, 31, 32, 33, 36.
Executive summary per site; obvious which file to download; estimate each score; prove
uniqueness vs all other GEMSDOE sites. MUST generate a UNIQUE TIF. Inspection must be
automated through the project, no human intervention. Parallel-run protocol: stay in one
method lane (surface Spearman <= 0.90, final-dot 3-px overlap <= 70% vs registry or log as
duplicate and stop); reuse the template's cached feature stack, evaluate_holdout.py and
submission_writer.py; holdout = whole-segment hide-and-recover with buffer, visible-only
catalogue features, visible faults masked pixel-exact, pooled DTI (alpha 0.2, beta 0.8,
300 m triangular kernel); label every number HOLDOUT-DTI (evaluator, n withheld, 95% CI)
or ORGANIZER-CONFIRMED; leakage canary per feature (AUC > 0.90 = leakage); end with a JSON
run card; budget 3 experiments / 2 hours; promotion is a separate selector step.
Highest urgency: unique TIF, obvious download/submit status, fixes the portal error
"Predicted values must be in range [0, 1]", unique name + <=140-char note, executive-summary
subpage explaining exactly how to submit. Answer at PhD level why GEMSDOE32
h33-h33-2-b2 (0.2778) scored highest and whether >0.2778 is achievable, then generate a
unique submission unlike any GEMSDOE site. Verify line by line, no hallucinations, official
sources linked. Generate 3-5 untried geological hypotheses naming layers, physical
signature, why catalogue-missing faults, difference vs this repo; rank by expected DTI /
cost; validate the top candidate on spatially-blocked holdout before touching a weekly
slot. Core values: Maximize P(Win); Own the Outcome. Prompt also quotes leaderboard
highs 0.4413 and 0.3195 (both superseded — see IR-K3 in README) and lists ~90 prior
GEMSDOE submission scores (all treated as OWNER-REPORTED; the nine focus sites are
tabulated in the executive summary).
