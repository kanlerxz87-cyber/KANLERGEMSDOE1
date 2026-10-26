"""Metric-exact emission: maximum-expected-coverage packing of a belief field.

Why this module exists
----------------------
``docs/research/score-ceiling-analysis.md`` §2 records the defect that this module repairs.
The superseded rule (``gems32-h19-5-smoothmaxcov-44090``) blurred the binary ridge by
``sigma = 1.85 px`` and then ran a max-coverage greedy on the blurred image.  Blurring a 1-px
binary ridge lowers and *shifts* its peak, so the greedy spread mass across the blurred blob
instead of locking onto the crest.  Measured consequence on the only real truth raster in this
competition (``labels.tif``, 60,988 catalogue pixels):

    rule                        dots   off-field dots   credit / unit mass   catalogue-proxy DTI
    incumbent raster-order     44,090          0             0.2154               0.1617720
    smoothmaxcov-44090         44,090     25,485 (57.8%)    0.0213               0.0163197

A 10x collapse in credit per unit of emitted mass, at identical budget.  The cause is arithmetic,
not geological: **mass placed outside the belief field's own support cannot earn credit from any
truth consistent with the belief.**

What this module guarantees
---------------------------
1. **Support confinement.**  Every emitted pixel is a pixel the belief field nominates
   (``field > 0``).  Emitting off-support is never defensible under the field's own beliefs, and
   it is the exact failure mode measured above.
2. **Exact marginal gain.**  For a candidate ``x`` the gain used for acceptance is

       dT(x) = sum_delta field(x+delta) * max(0, k(delta) - C(x+delta))

   where ``C`` is the credit already delivered by the accepted set and ``k`` is the official
   triangular kernel.  ``C`` is tracked so that overlapping dots are never double-credited.
   This is the exact *incremental* credit; the naive ``sum_delta field(x+delta) k(delta)``
   over-counts and is what makes a max-coverage sweep scatter.
3. **The metric's own stopping rule.**  A candidate is accepted only while the exact marginal
   theorem of ``metric.py`` holds:

       accept  <=>  dT * D > alpha * T * (dT + 1 - kbar)

   with ``kbar = sum_delta field(x+delta) k(delta)`` the expected kernel proximity that sets the
   added false-positive mass ``1 - kbar``.  The theorem is verified against brute force in
   ``tests/test_emitter.py``.

Algorithm
---------
**Lazy greedy** (Minoux / Cormode et al.) on the exact marginal gain, not on the static upper
bound.  A max-heap holds one key per support pixel; the key is re-validated against the live gain
on pop and re-pushed if stale.  Only pixels within `2R` of a new dot can have changed gain, so an
acceptance costs one local re-evaluation sweep, and on the sparse 1-px H19-5 ridge that is a
handful of support pixels rather than 169.

*Why not a static-order sweep:* the first version of this module ranked candidates by the static
upper bound `(field correlate k)(x)` and accepted in that order.  On a straight 1-px ridge every
interior pixel has the **same** static bound, so the sweep accepted adjacent pixels and delivered
**10.0 of the 15.0** units of credit the exact greedy delivered at the same budget — a 33 %
shortfall, i.e. a milder version of the very defect this module exists to repair.
`tests/test_emitter.py::test_lazy_greedy_matches_exact_greedy` pins that down.

Complexity: `O(|support| log|support| + budget * neighbours)`, which is a few seconds for the
121,131-px H19-5 support on 2 vCPU (measured: 4.2 s at a 44,090-px budget).
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field as dc_field

import numpy as np

from . import metric as M


@dataclass
class EmissionLog:
    """Receipt for one emission run (every number is measured, none assumed)."""

    rule: str
    n_support_px: int = 0
    n_emitted: int = 0
    total_mass: float = 0.0
    off_support_px: int = 0
    credit_delivered: float = 0.0
    last_marginal_gain: float = 0.0
    first_marginal_gain: float = 0.0
    stopped_by: str = ""
    candidates_considered: int = 0
    candidates_accepted: int = 0
    extras: dict = dc_field(default_factory=dict)

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d.pop("extras")
        d.update(self.extras)
        return d


def expected_proximity(field: np.ndarray) -> np.ndarray:
    """``kbar(x) = sum_delta field(x+delta) k(delta)`` — expected kernel proximity of a dot at x.

    This is the field's own estimate of the realised kernel weight to the nearest truth pixel,
    and therefore of the false-positive mass ``1 - kbar`` that the dot would add.
    """
    f = np.asarray(field, dtype=np.float64)
    out = np.zeros_like(f)
    dy, dx, kw = M._OFF
    for d, e, kk in zip(dy, dx, kw):
        out += M._shift(f, -d, -e) * kk
    return out


def _deliver(coverage: np.ndarray, y: int, x: int) -> None:
    """Update ``coverage`` in place: a dot at (y, x) delivers kernel weight to its disk."""
    h, w = coverage.shape
    dy, dx, kw = M._OFF
    for d, e, kk in zip(dy, dx, kw):
        gy, gx = y + d, x + e
        if 0 <= gy < h and 0 <= gx < w and kk > coverage[gy, gx]:
            coverage[gy, gx] = kk


def marginal_gain(field: np.ndarray, coverage: np.ndarray, y: int, x: int) -> float:
    """Exact incremental credit of adding unit mass at (y, x), given delivered ``coverage``."""
    h, w = field.shape
    dy, dx, kw = M._OFF
    gain = 0.0
    for d, e, kk in zip(dy, dx, kw):
        gy, gx = y + d, x + e
        if 0 <= gy < h and 0 <= gx < w:
            resid = kk - coverage[gy, gx]
            if resid > 0.0 and field[gy, gx] > 0.0:
                gain += field[gy, gx] * resid
    return gain


def exact_greedy(field: np.ndarray, budget: int | None = None, prior_dti: float = 0.26,
                 alpha: float = M.ALPHA, rho: float = 0.0) -> tuple[np.ndarray, EmissionLog]:
    """Fully re-evaluated greedy: at every step re-score all remaining candidates.

    Correct but ``O(budget * |support|)``; intended for small fields and as the reference the
    fast path is tested against.
    """
    f = np.asarray(field, dtype=np.float64)
    cov = np.zeros_like(f)
    mask = np.zeros(f.shape, dtype=bool)
    log = EmissionLog(rule="exact_greedy")
    sup = np.argwhere(f > 0)
    log.n_support_px = int(sup.shape[0])
    eff_alpha = alpha / (1.0 + rho)
    prox = expected_proximity(f)
    while True:
        if budget is not None and log.n_emitted >= budget:
            log.stopped_by = "budget"
            break
        best, best_g = None, 0.0
        for y, x in sup:
            if mask[y, x]:
                continue
            g = marginal_gain(f, cov, int(y), int(x))
            if g > best_g:
                best_g, best = g, (int(y), int(x))
        if best is None:
            log.stopped_by = "no_candidates"
            break
        y, x = best
        kb = float(prox[y, x])
        # exact marginal theorem with the field's own proximity estimate (and two-round option rho)
        if prior_dti > 0.0:
            # D/T = 1/s ; accept while dT*(1/s) > (alpha/(1+rho))*(dT + 1 - kbar)
            lhs = best_g * (1.0 / max(prior_dti, 1e-12)) - eff_alpha * (best_g + 1.0 - kb)
            if lhs <= 0.0:
                log.stopped_by = "credit_bar"
                break
        mask[y, x] = True
        _deliver(cov, y, x)
        if log.n_emitted == 0:
            log.first_marginal_gain = best_g
        log.last_marginal_gain = best_g
        log.credit_delivered += best_g
        log.n_emitted += 1
    log.total_mass = float(mask.sum())
    log.off_support_px = int((mask & (f <= 0)).sum())
    log.candidates_considered = int(sup.shape[0])
    log.candidates_accepted = log.n_emitted
    return mask, log


def emit(field: np.ndarray, budget: int | None = None, prior_dti: float = 0.26,
         alpha: float = M.ALPHA, rho: float = 0.0, gain_floor: float = 0.0,
         initial_mask: np.ndarray | None = None,
         ) -> tuple[np.ndarray, EmissionLog]:
    """Near-greedy maximum-expected-coverage emission, confined to the field's support.

    Parameters
    ----------
    field : array
        Belief surface (probability-like; the H19-5 arm is binary 0/1).
    budget : int, optional
        Hard cap on emitted pixels.  ``None`` means the credit bar alone decides.
    prior_dti : float
        The index at which the marginal bar is priced (the live anchor, 0.26).
    rho : float
        Two-round option value.  ``rho > 0`` lowers the bar to
        ``alpha * prior_dti / (1 + rho)``, the value of a fault that the expanded final-round
        label set may verify.
    gain_floor : float
        Absolute floor on the marginal gain, applied in addition to the bar.
    initial_mask : bool array, optional
        Already-emitted dots from an earlier stage (e.g., Regime-A exposed scarps in a
        two-regime allocation).  Pre-populates the 300 m kernel coverage array ``cov`` and
        excludes ``initial_mask`` pixels so Stage-2 dots maximize exact residual coverage
        without double-crediting covered traces.
    """
    f = np.asarray(field, dtype=np.float64)
    if f.min() < 0:
        raise ValueError("field must be non-negative")
    h, w = f.shape
    cov = np.zeros(f.shape, dtype=np.float64)
    mask = np.zeros(f.shape, dtype=bool)
    init = np.zeros(f.shape, dtype=bool)
    if initial_mask is not None:
        init = np.asarray(initial_mask, dtype=bool)
        if init.shape != f.shape:
            raise ValueError(f"initial_mask shape {init.shape} != field shape {f.shape}")
        if init.any():
            init_f = init.astype(np.float64)
            dy_o, dx_o, kw_o = M._OFF
            for d, e, kk in zip(dy_o, dx_o, kw_o):
                np.maximum(cov, M._shift(init_f, -int(d), -int(e)) * kk, out=cov)

    log = EmissionLog(rule="lazy_greedy_maxcov_support_confined")

    prox = expected_proximity(f)
    support = np.argwhere((f > 0) & (~init))
    log.n_support_px = int(support.shape[0])
    if log.n_support_px == 0:
        log.stopped_by = "empty_support"
        return mask, log

    flat = (support[:, 0] * w + support[:, 1]).astype(np.int64)
    is_sup = np.zeros(h * w, dtype=bool)
    is_sup[flat] = True

    if init.any():
        gain = np.zeros_like(f)
        dy_o, dx_o, kw_o = M._OFF
        for d, e, kk in zip(dy_o, dx_o, kw_o):
            gain += M._shift(f * np.maximum(0.0, kk - cov), -int(d), -int(e))
    else:
        # with zero coverage the exact marginal gain IS the expected proximity
        gain = prox.copy()
    heap = [(-float(gain[sy, sx]), int(fl)) for (sy, sx), fl in zip(support, flat)]
    heapq.heapify(heap)

    # only pixels within 2R of an accepted dot can have a changed gain
    two_r = int(2 * M.RADIUS_PX)
    upd = [(dy, dx) for dy in range(-two_r, two_r + 1) for dx in range(-two_r, two_r + 1)
           if dy * dy + dx * dx <= two_r * two_r]

    eff_alpha = alpha / (1.0 + rho)
    bar = max(gain_floor, 0.0)
    while heap:
        neg_g, fl = heapq.heappop(heap)
        y, x = divmod(int(fl), w)
        if mask[y, x] or init[y, x]:
            continue
        cur = float(gain[y, x])
        if -neg_g > cur + 1e-12:                     # stale key: re-insert with the live gain
            heapq.heappush(heap, (-cur, fl))
            continue
        if budget is not None and log.n_emitted >= budget:
            log.stopped_by = "budget"
            break
        kb = float(prox[y, x])
        if prior_dti > 0.0:
            lhs = cur * (1.0 / max(prior_dti, 1e-12)) - eff_alpha * (cur + 1.0 - kb)
            if lhs <= 0.0 or cur < bar:
                log.stopped_by = "credit_bar"
                break
        elif cur < bar:
            log.stopped_by = "gain_floor"
            break

        mask[y, x] = True
        _deliver(cov, y, x)
        if log.n_emitted == 0:
            log.first_marginal_gain = cur
        log.last_marginal_gain = cur
        log.credit_delivered += cur
        log.n_emitted += 1

        for dy, dx in upd:                            # local lazy re-evaluation
            yy, xx = y + dy, x + dx
            if 0 <= yy < h and 0 <= xx < w:
                fl2 = yy * w + xx
                if is_sup[fl2] and not mask[yy, xx]:
                    ng = marginal_gain(f, cov, yy, xx)
                    gain[yy, xx] = ng
                    heapq.heappush(heap, (-ng, int(fl2)))
    if not log.stopped_by:
        log.stopped_by = "exhausted_support"

    log.total_mass = float(mask.sum())
    log.off_support_px = int((mask & (f <= 0)).sum())
    log.candidates_considered = int(support.shape[0])
    log.candidates_accepted = log.n_emitted
    log.extras = {
        "prior_dti": prior_dti,
        "rho": rho,
        "alpha": alpha,
        "budget": budget,
        "gain_floor": gain_floor,
        "implied_bar_alpha_s": alpha * prior_dti,
        "implied_bar_two_round": alpha * prior_dti / (1.0 + rho),
    }
    return mask, log


def dot_thin(field: np.ndarray, min_dist: float, budget: int | None = None) -> tuple[np.ndarray, EmissionLog]:
    """The incumbent's own rule, reimplemented for matched-mass controls.

    Raster-order thinning of the field's support at a minimum Euclidean spacing, as used by
    ``dotted-h19-5-d2-8``.  ``min_dist = 2.828`` px reproduces the 44,090-dot layout's budget
    statistics; this implementation is a faithful *control*, not a byte-for-byte copy of the
    owner's script (the owner's TIF is measured directly in ``scripts/audit_shipped.py``).
    """
    f = np.asarray(field, dtype=np.float64)
    mask = np.zeros(f.shape, dtype=bool)
    log = EmissionLog(rule=f"raster_order_dot_thin_d{min_dist}")
    sel = np.zeros(f.shape, dtype=bool)          # pixels excluded by the spacing rule
    d2 = float(min_dist) ** 2
    r = int(np.ceil(min_dist))
    dy, dx = np.mgrid[-r:r + 1, -r:r + 1]
    off = np.stack([dy.ravel(), dx.ravel()], 1)
    off = off[(off ** 2).sum(1) <= d2]
    h, w = f.shape
    for y, x in np.argwhere(f > 0):
        y, x = int(y), int(x)
        if sel[y, x]:
            continue
        mask[y, x] = True
        log.n_emitted += 1
        for oy, ox in off:
            gy, gx = y + oy, x + ox
            if 0 <= gy < h and 0 <= gx < w:
                sel[gy, gx] = True
        if budget is not None and log.n_emitted >= budget:
            log.stopped_by = "budget"
            break
    log.n_support_px = int((f > 0).sum())
    log.total_mass = float(mask.sum())
    log.off_support_px = int((mask & (f <= 0)).sum())
    return mask, log
