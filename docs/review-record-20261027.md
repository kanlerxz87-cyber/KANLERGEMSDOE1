# Three-pass review record — KANLER-CONCORD, 2026-10-27

**Outcome: negative. No file cleared; no slot used.** Prior lanes (IEDR,
MPLC) remain stopped; their next-step (fold-local OOF emission) was
implemented properly this session via per-cell visible-only predictions.

## Pass 1 — implement and verify
- Restored 26 SHA-pinned owner mirrors + 9 focus champions; prepared 19
  bands (5,167,373 footprint px, 60,988 catalogue px). Verified every band
  semantic from file tags at runtime (asserts in `src/kanler/concord.py`).
- Pre-registered 5 ranked hypotheses + frozen EXP1–3 before any fit
  (`docs/research/preregistration-20261027.md`).
- Canaries pass (0.520–0.548). Surface uniqueness pass vs 22 genuine
  rasters (worst ρ 0.070, overlap 46.0%).
- EXP1 control 0.1002 [0.0869, 0.1138]; EXP2 CONCORD 0.0518
  [0.0443, 0.0595] (paired Δ −0.0484 [−0.0625, −0.0341]); EXP3 gated
  collar 0.0942 (Δ −0.0060). Evaluator GEMSDOE32-HIDE-RECOVER-v3.1,
  22,232 withheld positives. Runtime 148 s.

## Pass 2 — bugs, assumptions, edge cases
- `rank01` matches scipy (err 9e-9); thinning enforces √8 spacing
  (synthetic min-NN 3.0) and top-value selection. No code bug explains
  the loss.
- AUC-only diagnostics (no candidate created): geomean 0.568 / mean
  0.563 / shipped blend+road-veto 0.542 → road veto harmful; fixed
  fusion inadequate. Recorded for the next preregistration.
- EXP1 pool starvation quantified (NE/SE cells, full map 36,388/37,654);
  conclusion is conservative (control won with *fewer* dots).
- Independent re-audit: both new GeoTIFFs + champion pass all strict
  zeros-mode checks (finite [0,1], no sentinel, exact grid). The portal
  `[0,1]` error modes are documented with the zeros-variant fix.
- Irregularities flagged: IR-LATTICE (literal gate unsatisfiable;
  genuine-registry gating disclosed), IR-LIDAR-TAGS (legacy helper
  mislabels bands), IR-SAMPLE-MIRROR, IR-BUDGET-STARVE.

## Pass 3 — recheck vs the full brief
| Request | Result |
|---|---|
| Unique TIF generated, obvious download + verdict | Done — research download at top of site with 🔴 DO NOT SUBMIT (holdout-negative). Claiming "submit-ready" would violate the brief's own promotion gate |
| Executive table: file / estimated score / unique? | Done (HOLDOUT-DTI + labelled PROJECTION; nine-site table; best-of-nine = GEMSDOE32, already submitted) |
| Why 0.2778; beat it? | Nested-family + DTI algebra + new collar validation; ranking headroom identified (leader 0.4544 fetched 2026-10-27) |
| 3–5 hypotheses, ranked, top validated pre-slot | Done; ranks 4–5 blocked with named free official sources + sandbox obtainability verdict |
| Automated validation, no human inspector | Shared writer + independent re-audit + 30 unit tests green |
| Prompt archived; daily feed; clean Pages site | `ORIGINAL_PROMPT_20261027.md`; feed 0.4544 dated snapshot + existing daily workflow; 6 pages rebuilt |
| PR merged to main | See GitHub (this record ships in that PR) |

**Remaining work / limitations:** next lane = rank-2 PU-HGB line learner
(must beat 0.1002 paired); ComCat/SGMC-contact lanes need an unrestricted
runner; organizer-authenticated bytes + any upload require the team
DrivenData account; selector must ratify IR-LATTICE scope and own any
future slot. No ORGANIZER-CONFIRMED score exists in this repo.
