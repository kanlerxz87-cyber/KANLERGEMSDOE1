"""Live-anchored decision rule for the three-slot budget (GEMSDOE32, session 3).

Why this exists
---------------
The prompt asks for the standing rule "do not spend a slot on an idea that has not beaten the
current holdout best" to become *a running decision rule that also says what to try next*, and for
any persistent gap between the surrogate and the leaderboard to be chased rather than shrugged off.

This module does both, using the group's own live-scored record as the only ground truth about the
hidden scoring population.  It contains:

1. ``invert_live_pair`` -- the exact algebraic inversion of one *controlled* live pair.  The pair
   D2.8 (44,090 dots, live 0.2600) and H27-4-R1-SOLO (40,199 dots, live 0.2708) differ by exactly
   one mechanism: the 3,891 dots whose distance to the published catalogue is exactly 1 px were
   deleted.  Nothing else changed, so the pair identifies the live scoring population's scale.
2. ``removal_gain_bound`` -- the decision rule.  For a proposed removal of ``dn`` dots that costs
   ``dS`` units of weighted credit, it returns the largest credit loss the live metric can absorb
   and still improve.  A candidate is slot-eligible only if its measured credit cost is below that
   bound with a stated safety factor.
3. ``lm_validity_report`` -- the drift finding.  It shows that the live-mirror instrument, used
   outside its validated regime, ranks a 7,943-dot "safe-mass-pruned" variant of the 0.2708
   emission at 0.4413, which the live record refutes.  That refutation is quantified.

Nothing here contacts DrivenData.  Every live number is an [OWNER-REPORT] from the standing brief.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Owner-reported public scores for the group's submissions (standing brief + GEMSDOE28 manifest).
LIVE_LEDGER: dict[str, dict] = {
    "H27-4-R1-SOLO": {"dots": 40199, "dti": 0.2708,
                      "path": "scored/gems28-h27-4-r1-solo-d2-8-20261003-8acb75e1f2cc-nan.tif"},
    "D2.8": {"dots": 44090, "dti": 0.2600,
             "path": "scored/gems24-h25-1-dotted-h19-5-d2-8-20261002-e56ea318af89-nan.tif"},
    "D1.5": {"dots": 60069, "dti": 0.2477,
             "path": "scored/gems24-h25-1-dotted-h19-5-d1-5-20261002-989f59505db1-nan.tif"},
    "T-V2-ON-D1.5": {"dots": 61328, "dti": 0.2449,
                     "path": "scored/gems27-topo-gap-closure-t-v2-on-d1-5-20261002-5512495c6bd1-nan.tif"},
    "H19-5": {"dots": 121131, "dti": 0.1922,
              "path": "scored/gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif"},
    "H19-4": {"dots": 123779, "dti": 0.1912,
              "path": "scored/gems19-h19-4-multiline-corroborated-openness-thermal-pop-20260930-691e4dfa-nan.tif"},
    "H16-1": {"dots": 123939, "dti": 0.1911,
              "path": "scored/gems16-h16-1-topo-geophys-baseline-ridges-20260930-df20f65e-nan.tif"},
    "ENS12": {"dots": 172974, "dti": 0.1846, "path": "scored/gemsdoe-ens12-adopted-7f00890a.tif"},
    "LATTICE-S5": {"dots": 206895, "dti": 0.0904,
                   "path": "scored/13gems_20261001_r13-lattice-s5_v2_nan-outside.tif"},
    "PLACEHOLDER": {"dots": 147684, "dti": 0.0445, "path": "scored/gemsdoe9-PLACEHOLDER-2314b599.tif"},
}


@dataclass
class LiveInversion:
    """The live scoring population recovered from one controlled live pair."""

    dti_hi: float
    dti_lo: float
    n_hi: int
    n_lo: int
    g_assumed: float
    s_hi: float          # TP_w of the higher-scoring emission
    d_hi: float          # its denominator
    implied_credit_loss_budget: float   # max weighted credit a removal may cost
    measured_credit_loss: float | None
    safety_factor: float | None


def invert_live_pair(hi: str = "H27-4-R1-SOLO", lo: str = "D2.8",
                     g_assumed: float = 12226.0,
                     measured_credit_loss: float | None = None) -> LiveInversion:
    """Invert the controlled live pair ``hi`` > ``lo`` under the zero-credit-loss assumption.

    The two emissions differ only by the deleted dots, so with ``DTI = S / D``:

        S / D_lo      = dti_lo
        S / (D_lo - 0.2*dn + 0.8*(c - b)) = dti_hi

    where ``dn`` is the number of deleted dots, ``c`` the weighted credit those dots were earning
    (TP_p side) and ``b`` the nearest-dot coverage they were uniquely providing (TP_g side).  Setting
    ``c = b = 0`` -- i.e. assuming the deleted dots earned nothing -- gives the *smallest* denominator
    consistent with the observed gain, hence the most conservative credit-loss budget.  Any positive
    ``c`` makes the observed gain harder to explain and *shrinks* the budget.
    """
    a, b_ = LIVE_LEDGER[hi], LIVE_LEDGER[lo]
    dn = b_["dots"] - a["dots"]
    if dn <= 0:
        raise ValueError(f"{hi} does not have fewer dots than {lo}")
    # S/D_lo = dti_lo and S/(D_lo - 0.2*dn) = dti_hi  ->  D_lo = 0.2*dn*dti_hi/(dti_hi-dti_lo)
    d_lo = 0.2 * dn * a["dti"] / (a["dti"] - b_["dti"])
    s_hi = a["dti"] * (d_lo - 0.2 * dn)
    budget = s_hi * 0.2 * dn / (d_lo - 0.2 * dn)
    safety = (budget / measured_credit_loss) if (measured_credit_loss or 0) > 0 else None
    return LiveInversion(dti_hi=a["dti"], dti_lo=b_["dti"], n_hi=a["dots"], n_lo=b_["dots"],
                         g_assumed=g_assumed, s_hi=float(s_hi), d_hi=float(d_lo - 0.2 * dn),
                         implied_credit_loss_budget=float(budget),
                         measured_credit_loss=measured_credit_loss, safety_factor=safety)


def removal_gain_bound(inv: LiveInversion, dn: int, d_credit: float, d_tp_g: float = 0.0) -> dict:
    """Is a removal of ``dn`` dots costing ``d_credit`` weighted credit live-beneficial?

    Exact condition, from ``DTI = S / (0.2 n_p + 0.8 G + 0.8 (TP_g - TP_p))``:

        gain  <=>  d_credit < S * (0.2*dn - 0.8*(d_credit - d_tp_g)) / D

    ``d_tp_g`` is the nearest-dot coverage the removal destroys; it is 0 for a removal that never
    deletes a dot which is the unique nearest dot of any truth pixel.
    """
    d_new = inv.d_hi - 0.2 * dn + 0.8 * (d_credit - d_tp_g)
    s_new = inv.s_hi - d_credit
    if d_new <= 0:
        return {"dn": dn, "d_credit": d_credit, "gain": False, "reason": "non-positive denominator"}
    budget = inv.s_hi * (0.2 * dn - 0.8 * (d_credit - d_tp_g)) / inv.d_hi
    return {
        "dn": int(dn),
        "d_credit": float(d_credit),
        "d_tp_g": float(d_tp_g),
        "max_allowed_credit_loss": float(budget),
        "safety_factor": float(budget / d_credit) if d_credit > 0 else float("inf"),
        "projected_dti_if_live_credit_matches": float(s_new / d_new),
        "gain": bool(d_credit < budget),
        "denominator_after": float(d_new),
    }


def lm_validity_report(lm_scores: dict[str, dict], live_ledger: dict[str, dict] | None = None) -> dict:
    """Quantify the drift between the live-mirror instrument and the live record.

    The live-mirror instrument is only trusted inside the regime it was validated in.  This report
    measures how badly it fails outside it, so the failure is on the record instead of being
    discovered by spending a slot.
    """
    live_ledger = live_ledger or LIVE_LEDGER
    rows = []
    for name, sc in lm_scores.items():
        lb = live_ledger.get(name, {}).get("dti")
        rows.append({
            "candidate": name,
            "lm_calibrated_mean": sc["lm_mean"],
            "emitted_pixels": sc.get("emitted_pixels"),
            "owner_reported_live_dti": lb,
            "live_minus_lm": (lb - sc["lm_mean"]) if lb is not None else None,
        })
    ref = [r for r in rows if r["owner_reported_live_dti"] is not None]
    ref.sort(key=lambda r: -r["owner_reported_live_dti"])
    return {
        "instrument": "LM-calibrated (spatially blocked official DTI vs SGMC off-catalogue truth, "
                      "|G| calibrated to 12,691 px)",
        "validated_regime": ("catalogue-flank and budget perturbations of the 40k-62k dot operating "
                             "point; it reproduces H27-4-R1-SOLO > D2.8, D2.8 > D1.5 and "
                             "LATTICE-S5 > PLACEHOLDER"),
        "rows": rows,
        "worst_live_minus_lm": min((r["live_minus_lm"] for r in ref if r["live_minus_lm"] is not None),
                                   default=None),
        "note": ("A positive live_minus_lm means the live score is higher than the instrument says. "
                 "The magnitude of that gap on mass-removal arms is the drift measurement."),
    }
