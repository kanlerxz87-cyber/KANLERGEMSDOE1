# Pre-registration — KANLER-CONCORD lane, 2026-10-27 UTC

**Session lane (single method, stay inside it):** an unsupervised *cross-family
soft-min concordance* ranking surface over five independent physics families,
emitted by value-ordered 2.83 px thinning, with the catalogue collar tested as
a pre-registered emission factor. No catalogue-derived feature enters the
surface; the catalogue is used only (a) fold-locally, to define each holdout
cell's visible-fault exclusion, and (b) in the final map, for the same
exclusion the control uses. Evaluator: shared `scripts/evaluate_holdout.py`
→ `gems32.holdout` **GEMSDOE32-HIDE-RECOVER-v3.1** (pooled DTI, α=0.2,
β=0.8, 300 m triangular kernel) plus the independent
**GEMSDOE32-SGMC-CAL-v3.0** off-catalogue instrument. Writer: shared
`scripts/submission_writer.py`. Budget: ≤3 experiments, ≤2 h. No submission
slot is spent by this session; promotion is a separate selector decision.

Evidence classes used below: **HOLDOUT-DTI** (evaluator version + withheld
count + 95% CI), **ORGANIZER-CONFIRMED** (submission-page receipt only),
**USER/OWNER-REPORT** (no receipt in this repo), **PROJECTION** (labelled
forecast, never a score), **ORGANIZER-PUBLISHED** (public leaderboard page).

## Why the reported 0.2778 (GEMSDOE32 h33-2-b2) plausibly led the fleet — PhD reading

Verified facts (this repo's byte audit, `evidence/protocol_audit_20261026.json`):
the H19-5 binary support (121,131 px) contains the D2.8 support (44,090 px,
minimum spacing √8 px ≈ 283 m); intersecting D2.8 with catalogue distance
>1 px reproduces GEMSDOE31 (40,199 px) and >2 px reproduces GEMSDOE32
(37,654 px) with **zero XOR mismatch**. The associated 0.1922 / 0.2600 /
0.2708 / 0.2778 values are **USER/OWNER-REPORTS** (no receipt binds any of
them to exact bytes here), so the mechanism below is a hypothesis about a
reported ordering, not proven causation.

Under the official metric (DrivenData #306, page 967; fetched 2026-10-27),
DTI = TPw/(TPw+0.2·FPw+0.8·FNw) with a 300 m triangular kernel. For binary
dots, DTI = T/(0.2·(T+n−M)+0.8·|G|) where T is kernel credit summed over
truth pixels, n the dot count and M self-credit summed over dots
(`vendor/gems57/metric.py`, brute-force tested). Three consequences:

1. **Redundant dots are pure cost.** A second dot within ~300 m of the same
   truth pixel adds ≈0 to T (max-kernel saturates) but pays up to 0.2 in the
   denominator. The 121k→44k dotting therefore removes mostly denominator,
   which is why sparsification — not new geology — explains the large
   0.1922→0.2600 reported jump. Spacing √8 px is near the kernel diameter:
   adjacent dots' 300 m disks just touch, an efficient covering code.
2. **The catalogue collar is a precision bet, not a rule.** Organizer staff
   confirm the known-fault mask is *pixel-exact*, near-catalogue predictions
   far from new truth are fully penalised, *and* new truth can lie within
   300 m of a known trace (corrections/splays are an explicit aim)
   (forum 11516, posts 2+4; fetched 2026-10-27). B1→B2 pruning helped the
   reported public score (+0.007, within plausible split noise) presumably
   because the base surface fires in halos around mapped traces; the same
   collar necessarily deletes genuine near-catalogue discoveries. Whether
   B2 beats a *gated* allowance (near-catalogue dots only at top-decile
   surface values) is testable fold-locally — EXP3 below.
3. **Headroom is in the ranking, not the dotting.** A non-redundant dot
   raises DTI iff its realised kernel credit exceeds ≈0.2·DTI (≈0.056 at
   DTI 0.28; exact two-sided test in `metric.marginal_accept`). At the
   champion's operating point the marginal bar is low, so live gains must
   come from *which* corridors get dots (surface precision at fixed budget),
   not from further thinning. The public leader was **0.4544**
   (ORGANIZER-PUBLISHED leaderboard, fetched 2026-10-27), i.e. hidden faults
   are far more recoverable than 0.2778; the fleet's later 0.3195
   hybrid-anchor (USER/OWNER-REPORT via sibling repos, 31,182 weighted
   cells) likewise points to *consensus ranking* as the live-rewarded
   direction. Can we beat 0.2778? Only a fold-local holdout win over the
   champion *method* (not its static file) licenses trying; that is the
   promotion gate, and a negative result is a deliverable.

## Five candidate hypotheses (formulated before any fit in this session)

| Rank | Hypothesis (layers → signature) | Why it should find catalogue-*missing* faults | Difference vs implemented record; named mimic; data |
|---|---|---|---|
| **1 — RUN** | **CONCORD.** MAG (bands 02 rtp, 03 tmi_hg) + GRAV (13 iso_grav_anom, 18 hg) + TOPO (12 det_elev ridge + tag-correct LiDAR scarp step/dipole/cross/coherence with valid-aware DEM fallback) + RAD (K/Th and ThK edges) + SUB (17 cond_surf ridge, 15 depth_to_base step) → per-family Hessian-ridge/edge percentile ranks fused by soft-min (0.7·geometric-mean + 0.3·mean), TIGER road-distance veto | A buried piedmont fault under fan alluvium is weak in *every* single survey (no scarp, muted magnetics) — which is why it is unmapped — but its basement step still deflects gravity, magnetics, conductivity and fan slope *on the same trace*. AND-fusion promotes coincident micro-edges that amplitude stacks and catalogue-trained classifiers bury under shallow high-contrast (already-mapped) sources | Unsupervised 5-family rank-AND; prior fleet concordance used ≤2 families or opaque binary supports (H19-5), HGB lanes learn catalogue appearance, MPLC is phase-based, IEDR seismic. Tag-correct LiDAR bands (legacy composite mislabels b2/b5 — IR flagged). **Mimic:** lithologic contacts/dikes are also multi-family edges; roads/terraces (vetoed/suppressed). **Data:** all layers already restored hash-pinned in `.cache/gems_data` (owner mirrors, *not* organizer-authenticated); no new download needed. Cost: low |
| 2 | **PU-HGB line learner.** Same 19 bands + derived ridge stack → HistGradientBoosting with reliable negatives (far-from-fault, low-concordance), spatially-blocked training | Learns multivariate fault appearance incl. low-amplitude combos | Prior HGBs used raw/blob features + top-k emission and scored 0.02–0.04 live (USER/OWNER-REPORTS); line-only features + matched thinning is untested, but any catalogue-trained model inherits catalogue bias — the exact failure CONCORD avoids. **Mimic:** anything catalogue-like (halos). Cost: medium. *Not run this session (budget); next lane if CONCORD is negative* |
| 3 | **TIPFIELD.** Visible-catalogue endpoints → collinearity/orientation continuation field, gated by CONCORD | Organizers explicitly seek tip extensions/splays within 300 m of known traces (forum 11516/4) | Tip rules were tried as *placement* (GEMSDOE33, 0.2632 USER/OWNER-REPORT); as a fold-local *feature* it is untested here but carries the highest leakage-canary risk. **Mimic:** erosional lineaments collinear by chance. Cost: low–medium. *Future lane* |
| 4 | **Seismic lineaments.** Individual USGS ComCat events (location-uncertainty ellipses) → anisotropic alignment × magnetic strike agreement | Active buried structures host aligned microseismicity without scarps | Only gridded density bands (10/16) used before; raw-event version proposed (H33-E) never implemented. **Mimic:** injection/mining swarms. **Data check:** free official FDSN service `https://earthquake.usgs.gov/fdsnws/event/1/` exists, but this sandbox's egress allowlist (github/pypi only) blocks bulk download → **not obtainable here, not viable this session**. Cost: high |
| 5 | **SGMC contact offsets.** USGS SGMC geologic *contacts* → contacts truncated/offset along lineaments | Pre-Quaternary faults omitted from Qfaults still offset map units | SGMC *faults* raster exists in-repo and is reserved as the independent SGMC-CAL instrument (using it as a feature would corrupt that instrument). Contacts vector is free via USGS NGMDB (`https://ngmdb.usgs.gov/`) but likewise not downloadable from this sandbox → **not viable this session**. **Mimic:** depositional pinch-outs. Cost: medium |

## Frozen experiments (all fold-local; evaluator B=0, collar inside emission)

Common emission: value-ordered thinning, min-distance √8 px, per-cell budget
`round(37654 · active_px / 5,106,385)` (champion density), candidate pool =
top 4× budget by field value inside the allowed mask (control: its binary
support). Allowed = cell active domain (visible faults already excluded
pixel-exactly by the evaluator context).

- **EXP1 control (champion method, fold-local):** field = H19-5 binary
  support; allowed additionally requires distance-to-*visible* > 2 px (B2).
- **EXP2 candidate:** field = CONCORD surface; identical B2 emission.
- **EXP3 emission factor (branch pre-registered):** winning field of
  EXP1/EXP2 with B2 replaced by the gated allowance
  `(d_visible > 2) OR (field ≥ cell-active 90th percentile)`.

Gates, in order: (a) per-family + surface leakage canaries (pooled withheld
AUC, symmetric ≤ 0.90) before placement; (b) surface uniqueness before
placement (sampled Spearman |ρ| ≤ 0.90 and preview-support 3 px overlap
≤ 70% vs every genuine registry raster — 9 pinned focus champions + 12 local
scored detectors + this repo's historical candidates, deduplicated by
SHA-256); (c) EXP2 must beat EXP1 with paired spatial-bootstrap 95% CI > 0
to claim a surface win; EXP3 must beat its B2 parent likewise; (d) final-dot
uniqueness re-checked; (e) shared-writer format audit (single-band float32,
EPSG:32611, exact grid, finite [0,1] in footprint, zero on catalogue).
The synthetic spacing-5 lattice (206,895 px; 3 px halo covers 99.87% of the
eligible domain, champion included) is reported as a diagnostic, not a
genuine-submission gate — see IR-LATTICE in the run card; this scope decision
is flagged for the selector rather than hidden. If any mandatory gate fails:
verdict **negative**, file (if written) is research-only, no slot spent.

Final map (only from the winning configuration): same field/emission on the
full catalogue at 37,654 dots, written via the shared writer as `-zeros`
(primary; 0.0 outside footprint — immune to NaN→sentinel form conversion)
and `-nan` twins plus a one-file ZIP. A **PROJECTION** (never a score) may
be reported as `0.2778 × (candidate HOLDOUT-DTI / EXP1 HOLDOUT-DTI)` with
the paired-CI ratio interval, anchored on the USER/OWNER-REPORTED 0.2778.

*Written before running any experiment in this session. Git history is the
timestamp.*
