"""Emitters: how a detector field becomes a legal 0/1 prediction raster.

The official metric is ``DTI = TP / (TP + alpha*FP + beta*FN)``. For an added binary pixel whose
entire kernel credit ``k`` improves an otherwise-uncovered truth pixel, ``delta_TP=k``,
``delta_FP=1-k`` and ``delta_FN=-k``. Since ``1-beta=alpha``, the denominator changes by alpha and
the exact isolated-pixel break-even is ``k > alpha*DTI`` (0.05556 at score 0.2778).

That scalar is an idealized special case, not a universal threshold for an arbitrary candidate in a
partially covered field. In general, score improvement depends on the actual marginal TP/FP/FN:
``delta_TP * D > TP * (delta_TP + alpha*delta_FP + beta*delta_FN)``. Existing coverage can make
``delta_TP`` smaller than the candidate's kernel weight. The hidden truth is unavailable during
model selection, so code using ``alpha*DTI`` is a decision heuristic, never a projected leaderboard
score. See ``metric.marginal_inclusion_threshold`` for the qualified derivation and
``tests/test_metric.py`` for exact scoring checks.

A single pixel can be the best cover for several truth pixels (a fault network is 1 px wide, so a
pixel on a straight trace can serve 3-5 truth pixels at once); credit is therefore not proportional
to the number of emitted pixels, and the greedy/marginal view is more informative than raw field
mass.
"""
from __future__ import annotations

from typing import Iterable, Tuple

import numpy as np

from . import metric as M


# --------------------------------------------------------------------------------------- helpers
def threshold_field(field: np.ndarray, q: float, footprint: np.ndarray | None = None) -> np.ndarray:
    """Boolean support at the ``q`` quantile of a field inside the footprint."""
    f = np.asarray(field, dtype=np.float32)
    m = footprint if footprint is not None else np.isfinite(f)
    vals = f[m]
    if vals.size == 0:
        return np.zeros(f.shape, bool)
    tau = np.quantile(vals, 1.0 - q)
    return m & (f >= tau)


def topk_mask(field: np.ndarray, n: int, footprint: np.ndarray | None = None) -> np.ndarray:
    """Exactly ``n`` highest-field pixels inside the footprint (ties broken by raster index)."""
    f = np.asarray(field, dtype=np.float32).copy()
    m = footprint if footprint is not None else np.isfinite(f)
    f[~m] = -np.inf
    flat = f.ravel()
    if n >= int(m.sum()):
        return m.copy()
    idx = np.argpartition(flat, -n)[-n:]
    out = np.zeros(flat.size, bool)
    out[idx] = True
    return out.reshape(f.shape)


# --------------------------------------------------------------------------------------- emitters
def dot_thin(support: np.ndarray, min_dist: float) -> np.ndarray:
    """Canonical raster-order Poisson-disk thinning (the incumbent rule, kept for comparison).

    Keeps a pixel iff no already-kept pixel is closer than ``min_dist``, walking candidates in
    ascending raster index; the field never influences the layout.
    """
    ys, xs = np.nonzero(support)
    if ys.size == 0:
        return np.zeros(support.shape, bool)
    r2 = min_dist * min_dist
    cell = max(1.0, float(min_dist))
    grid: dict = {}
    out = np.zeros(support.shape, bool)
    r = int(np.ceil(min_dist))
    for i in range(ys.size):
        y, x = int(ys[i]), int(xs[i])
        cy, cx = int(y // cell), int(x // cell)
        ok = True
        for gy in range(cy - 2, cy + 3):
            for gx in range(cx - 2, cx + 3):
                for (ky, kx) in grid.get((gy, gx), ()):
                    dy, dx = y - ky, x - kx
                    if dy * dy + dx * dx < r2:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            out[y, x] = True
            grid.setdefault((cy, cx), []).append((y, x))
    return out


def dot_thin_matched(field: np.ndarray, n_target: int, footprint: np.ndarray,
                     min_dist: float = 2.8, tol: float = 0.10) -> np.ndarray:
    """Incumbent ``dot_thin`` rule calibrated to emit ~``n_target`` pixels.

    The group's own density sweep showed the shipped artifact is the maximum of its family, so a
    rule comparison at unequal mass is not informative; this driver binary-searches the support
    quantile so the raster-order cascade emits the same number of pixels as the arms it is
    compared with.
    """
    lo, hi = 0.0, 1.0
    best = None
    for _ in range(14):
        q = 0.5 * (lo + hi)
        sup = threshold_field(field, q, footprint)
        m = dot_thin(sup, min_dist)
        n = int(m.sum())
        if best is None or abs(n - n_target) < abs(best[0] - n_target):
            best = (n, m)
        if n > n_target * (1 + tol):
            hi = q                     # too many kept -> shrink the support
        elif n < n_target * (1 - tol):
            lo = q
        else:
            break
    return best[1]


def _kernel_offsets() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    r = int(M.RADIUS_PX)
    dy, dx = np.mgrid[-r:r + 1, -r:r + 1]
    dy, dx = dy.ravel(), dx.ravel()
    d = np.hypot(dy, dx)
    k = d <= M.RADIUS_PX
    return dy[k].astype(int), dx[k].astype(int), M.kernel(d[k])


_OFF = _kernel_offsets()


def _cover_update(pred: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """Roll ``pred`` by (dy, dx) with zero fill (used for neighbour coverage maps)."""
    out = np.zeros_like(pred, dtype=np.float32)
    h, w = pred.shape
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    out[ys0:ys1, xs0:xs1] = pred[max(0, -dy):min(h, h - dy), max(0, -dx):min(w, w - dx)]
    return out


def coverage_credit(field: np.ndarray, footprint: np.ndarray) -> np.ndarray:
    """Expected credit ``E[sum_q max(0, k(x,q) - C(q))]`` for a single candidate pixel.

    This is the metric's own true-positive gain with the detector probability acting as a
    surrogate for the (unknown) truth indicator, exactly as in the group's H37-1 objective:
    ``gain(x) = sum_q p(q) max(0, k(|x-q|) - C(q))`` with ``C(q)`` the coverage already
    supplied by the emitted set.  For an empty starting set ``C = 0`` and
    ``gain(x) = sum_q p(q) k(|x-q|)``, i.e. a kernel correlation of the field.
    """
    f = np.asarray(field, dtype=np.float32) * footprint
    gain = np.zeros_like(f)
    for dy, dx, k in zip(*_OFF):
        gain += k * _cover_update(f, dy, dx)
    return gain * footprint


def coverage_credit_residual(field: np.ndarray, footprint: np.ndarray,
                             C: np.ndarray) -> np.ndarray:
    """EXACT marginal gain with the coverage already delivered deducted.

    ``gain(x) = sum_o f(x+o) * max(0, k(o) - C(x+o))`` -- the objective emitter.py maximises.
    Computing it as a sum of shifted products is exact and costs the same 29 shifts as the
    un-deducted ``coverage_credit``.
    """
    f = np.asarray(field, dtype=np.float32) * footprint
    gain = np.zeros_like(f)
    for dy, dx, k in zip(*_OFF):
        w = f * np.maximum(0.0, np.float32(k) - C)
        gain += _cover_update(w, dy, dx)
    return gain * footprint


def greedy_cover(field: np.ndarray, n: int, footprint: np.ndarray, min_dist: float = 0.0,
                 seed: int = 0, verbose: bool = False) -> np.ndarray:
    """Lazy-greedy maximum expected coverage at a fixed pixel budget ``n``.

    ``gain(x | S) = sum_q p(q) max(0, k(x,q) - C(q))`` is monotone and submodular, so the greedy
    order carries the (1 - 1/e) guarantee; lazily re-evaluated here.  ``min_dist`` > 0 disables
    candidates within that radius of an already-chosen pixel (the group's packing used the kernel
    itself as the exclusion, i.e. min_dist = 0 with C(q) doing the work).
    """
    f = np.asarray(field, dtype=np.float32) * footprint
    C = np.zeros_like(f)                                  # coverage already supplied at each q
    chosen = np.zeros(f.shape, bool)
    n = int(min(n, f.size))
    gain = coverage_credit(f, footprint)
    blocked = np.zeros(f.shape, bool)
    for _ in range(n):
        g = np.where(chosen | blocked, -np.inf, gain)
        i = int(np.argmax(g))
        if not np.isfinite(g.reshape(-1)[i]) or g.reshape(-1)[i] <= 0:
            break
        y, x = divmod(i, f.shape[1])
        chosen[y, x] = True
        # update the coverage map only in the neighbourhood (cheap because R = 3 px)
        for dy, dx, k in zip(*_OFF):
            yy, xx = y + dy, x + dx
            if 0 <= yy < f.shape[0] and 0 <= xx < f.shape[1]:
                newC = max(C[yy, xx], k)
                if newC > C[yy, xx]:
                    C[yy, xx] = newC
        if min_dist > 0:
            r = int(np.ceil(min_dist))
            y0, y1 = max(0, y - r), min(f.shape[0], y + r + 1)
            x0, x1 = max(0, x - r), min(f.shape[1], x + r + 1)
            blocked[y0:y1, x0:x1] = True
        gain = coverage_credit_residual(f, footprint, C)     # exact, recomputed each step
    return chosen


def credit_bar_emit(field: np.ndarray, bar: float, footprint: np.ndarray,
                    min_dist: float = 2.8) -> np.ndarray:
    """Metric-native threshold emission: keep pixels whose expected credit clears the bar.

    ``field`` is read as a *per-pixel expected kernel credit toward the hidden truth* (a
    probability-like quantity in [0, 1]); the rule emits a pixel iff
    ``field(x) > bar``, then thins at ``min_dist`` so that the emitted set does not pay twice for
    the same hidden truth pixel.
    """
    support = footprint & (np.asarray(field, np.float32) > bar)
    if min_dist > 0:
        support = dot_thin(support, min_dist)
    return support


def masked_along_support(field: np.ndarray, support: np.ndarray, keep_frac: float,
                         rng: np.random.Generator) -> np.ndarray:
    """Random sub-selection of a support (content-blind control)."""
    out = np.zeros(support.shape, bool)
    ys, xs = np.nonzero(support)
    if ys.size == 0:
        return out
    take = rng.random(ys.size) < keep_frac
    out[ys[take], xs[take]] = True
    return out


def as_float(mask: np.ndarray) -> np.ndarray:
    return np.asarray(mask, dtype=np.float32)


def greedy_cover_fast(field: np.ndarray, footprint: np.ndarray, max_n: int,
                      stop_bar: float | None = None, min_dist: float = 0.0,
                      exact: bool = True, headroom: int = 8):
    """Same result as ``holdout.greedy_cover_adaptive`` but with a candidate-set restriction.

    Why this is exact.  The marginal gain ``gain[x]`` is non-increasing in the number of chosen
    pixels.  If, at the end of a restricted run, ``max(gain)`` over the *excluded* pixels is
    ``<=`` the smallest marginal actually taken (``v_last``), then at every earlier step no
    excluded pixel could have been the argmax either (its gain was then >= its final gain), so the
    restricted run is a valid exact-greedy run.  The certificate is checked once and the whole run
    is repeated from scratch with a larger candidate set if it fails.

    Returns ``(mask, trace)`` with the same semantics as ``greedy_cover_adaptive``.
    """
    from . import holdout as _H  # local import: holdout imports emission
    if not exact:
        return _H.greedy_cover_adaptive(field, footprint, max_n, stop_bar, min_dist)
    base = np.asarray(field, dtype=np.float32) * footprint
    H, W = base.shape
    dy, dx, kw = _OFF
    n = int(min(max_n, int(footprint.sum())))
    flat_fp = footprint.reshape(-1)
    fp_idx = np.flatnonzero(flat_fp)
    k_seed = min(int(headroom) * max(n, 1), int(footprint.sum()))
    g0 = np.zeros(base.shape, np.float32)
    for d, e, k in zip(dy, dx, kw):
        g0 += k * _cover_update(base, d, e)
    g0 *= footprint
    flat_g0 = g0.reshape(-1)
    tau = float(np.partition(flat_g0[fp_idx], -k_seed)[-k_seed]) if fp_idx.size > k_seed else -np.inf

    while True:
        # ---- fresh state for every attempt (a retry must not inherit the previous run)
        f = base.copy()
        C = np.zeros((H, W), np.float32)
        chosen = np.zeros((H, W), bool)
        blocked = np.zeros((H, W), bool)
        gain = g0.copy()
        idx = fp_idx if not np.isfinite(tau) else fp_idx[flat_g0[fp_idx] >= tau]
        pos = np.full(H * W, -1, np.int32)
        pos[idx] = np.arange(idx.size, dtype=np.int32)
        g = flat_g0[idx].copy()
        trace: list = []
        taken, v_last, ok = 0, 0.0, True
        for _ in range(n):
            i = int(np.argmax(g))
            v = float(g[i])
            if not np.isfinite(v) or v <= 0.0:
                ok = (v_last > 0.0) or (v > 0.0)
                break
            if stop_bar is not None and v < stop_bar:
                trace.append({"stopped": True, "marginal": v, "bar": stop_bar, "n": taken})
                ok = True
                break
            trace.append({"stopped": False, "marginal": v})
            v_last, taken = v, taken + 1
            y, x = divmod(int(idx[i]), W)
            chosen[y, x] = True
            for d, e, k in zip(dy, dx, kw):
                qy, qx = y + d, x + e
                if not (0 <= qy < H and 0 <= qx < W):
                    continue
                old = C[qy, qx]
                if k <= old:
                    continue
                C[qy, qx] = k
                wq = f[qy, qx]
                if wq == 0:
                    continue
                for d2, e2, k2 in zip(dy, dx, kw):
                    xy, xx = qy + d2, qx + e2
                    if 0 <= xy < H and 0 <= xx < W:
                        dgw = wq * (max(0.0, k2 - k) - max(0.0, k2 - old))
                        if dgw:
                            flat = xy * W + xx
                            gain.reshape(-1)[flat] += dgw
                            p = pos[flat]
                            if p >= 0:
                                g[p] += dgw
            # --- invalidate *after* the neighbourhood update: the update writes the selected
            #     pixel's own entry back (it is inside its own update neighbourhood), which would
            #     otherwise resurrect it and let argmax pick it twice.
            g[i] = -np.inf
            if min_dist > 0:
                r = int(np.ceil(min_dist))
                blocked[max(0, y - r):min(H, y + r + 1), max(0, x - r):min(W, x + r + 1)] = True
        # Certificate: every excluded pixel has *initial* gain <= tau, and its gain is
        # non-increasing, so requiring ``tau <= v_last`` rules it out at every step.
        if (not ok) or taken == 0 or (not np.isfinite(tau)) or tau <= v_last + 1e-6:
            break
        tau *= 0.5
    return chosen, trace
