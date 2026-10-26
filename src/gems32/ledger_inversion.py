"""Live-Ledger Inversion (LLI): estimate the hidden public-truth density by feature stratum from the
owner-reported live scores of many different rasters, and project the live DTI of a new raster.

Why this instrument exists
--------------------------
Every local holdout in this repository draws its truth from a published catalogue (USGS/INGENIOUS or
SGMC).  The organisers mask the catalogue out of scoring and score *new*, expert-mapped faults, so
those holdouts measure a different population; the repository has documented live counter-examples
(SGMC-tracing files scoring 0.56-0.65 locally and ~0.05 live).  The only measurements of the hidden
scoring population are the live scores themselves.  This module turns them into a calibrated model.

Exact identity used
-------------------
For a prediction field ``p`` (masked to the scored domain = footprint minus catalogue pixels) and a
hidden binary truth ``g`` with per-pixel inclusion probability ``pi(y)``:

* ``E[TP_w] = sum_y pi(y) * K_p(y)``, with ``K_p(y) = max_x p(x) k(d(x,y))``  (exact, linearity)
* ``E[|G|]  = sum_y pi(y)``                                                 (exact)
* ``E[M]    ~ (1/3) sum_y pi(y) * C_p(y)``, with ``C_p(y) = sum_x p(x) k(d(x,y))``
  (``M = sum_x p(x) max_g k`` is the prediction-side matched mass; the factor 1/3 is the exact ratio
  of the max to the sum of kernel weights for a straight 1-px truth line through a prediction at
  distance 0 and is within +-12% for distances 1-2 px.  ``M`` enters the DTI denominator only with
  weight 0.2, so this approximation moves projected scores by well under 0.002.)
* ``FP_w = N - M`` with ``N = sum_x p(x)``; ``FN_w = |G| - TP_w``.

With ``pi`` constant on strata ``S_k`` (``pi = lambda_k``) each observed score ``s`` gives one linear
equation in ``lambda``::

    sum_k lambda_k [A_k (1 - 0.2 s) + 0.2 s B_k - 0.8 s |S_k|] = 0.2 s N

where ``A_k = sum_{y in S_k} K_p(y)`` and ``B_k = (1/3) sum_{y in S_k} C_p(y)``.

Strata are defined only by *features* (distance to catalogue, distance to a reference ridge network,
slope, LiDAR scarp strength, SGMC proximity) -- never by location -- so a fitted density transfers to
the private chunks to the extent the feature/truth relation is stationary.  The model is
``log lambda_k = theta_0 + sum_f theta_f[level_f(k)]`` (log-additive, reference level 0 per factor),
fitted by bounded least squares on the predicted-vs-observed DTI.  Validation is leave-one-out and
leave-one-family-out prediction of live scores; projections must quote that empirical error.

Every number this module produces about a new raster is a PROJECTION, not a score.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares, nnls

from .metric import ALPHA, BETA, RADIUS_PX, kernel

# 25 kernel offsets with k > 0 (d < 3 px) on the 100 m grid
_OFFS = [(dy, dx, float(kernel(np.hypot(dy, dx))))
         for dy in range(-3, 4) for dx in range(-3, 4) if float(kernel(np.hypot(dy, dx))) > 0.0]
LINE_MAX_TO_SUM = 1.0 / 3.0


@dataclass
class StrataSpec:
    """Factor levels per pixel (int8 arrays, -1 = outside the scored domain)."""
    names: list[str]
    levels: list[np.ndarray]           # one int8 array per factor, same grid
    n_levels: list[int]
    level_labels: list[list[str]]
    active: np.ndarray                 # scored domain (footprint & ~catalogue)
    stratum: np.ndarray = field(init=False)
    n_strata: int = field(init=False)
    sizes: np.ndarray = field(init=False)
    stratum_levels: np.ndarray = field(init=False)   # (n_strata, n_factors) level index of each factor

    def __post_init__(self) -> None:
        mult = 1
        st = np.zeros(self.active.shape, np.int32)
        for lv, n in zip(self.levels, self.n_levels):
            if lv.shape != self.active.shape:
                raise ValueError("factor grid mismatch")
            if (lv[self.active] < 0).any() or (lv[self.active] >= n).any():
                raise ValueError("factor level out of range inside the active domain")
            st += lv.astype(np.int32) * mult
            mult *= n
        st[~self.active] = -1
        self.stratum = st
        self.n_strata = mult
        self.sizes = np.bincount(st[self.active], minlength=mult).astype(np.float64)
        ids = np.arange(mult, dtype=np.int64)
        lv_tab = np.zeros((mult, len(self.n_levels)), np.int16)
        m = 1
        for j, n in enumerate(self.n_levels):
            lv_tab[:, j] = (ids // m) % n
            m *= n
        self.stratum_levels = lv_tab


def design_row(pred: np.ndarray, spec: StrataSpec) -> dict:
    """Exact per-stratum kernel aggregates of one prediction raster (catalogue pixels zeroed)."""
    p = np.asarray(pred, np.float32)
    p = np.where(np.isfinite(p), p, 0.0).astype(np.float32)
    if (p[spec.active] < -1e-6).any() or (p[spec.active] > 1 + 1e-6).any():
        raise ValueError("prediction outside [0, 1] inside the scored domain")
    p = np.clip(p, 0.0, 1.0)
    p[~spec.active] = 0.0
    H, W = p.shape
    ys, xs = np.nonzero(p > 0.0)
    v = p[ys, xs].astype(np.float64)
    n_mass = float(v.sum())
    flat_n = H * W
    kmax = np.zeros(flat_n, np.float32)
    csum = np.zeros(flat_n, np.float64)
    touched = []
    for dy, dx, k in _OFFS:
        ty, tx = ys + dy, xs + dx
        ok = (ty >= 0) & (ty < H) & (tx >= 0) & (tx < W)
        # Source pixels are unique, so targets of ONE fixed offset are unique too: plain fancy
        # indexing is exact here (no ufunc.at needed).
        fi = ty[ok].astype(np.int64) * W + tx[ok]
        w = v[ok] * k
        kmax[fi] = np.maximum(kmax[fi], w.astype(np.float32))
        csum[fi] += w
        touched.append(fi)
    t = np.unique(np.concatenate(touched)) if touched else np.zeros(0, np.int64)
    st = spec.stratum.ravel()[t]
    ok = st >= 0
    a = np.bincount(st[ok], weights=kmax[t][ok].astype(np.float64), minlength=spec.n_strata)
    b = np.bincount(st[ok], weights=csum[t][ok], minlength=spec.n_strata) * LINE_MAX_TO_SUM
    binary = bool(np.all((v == 1.0)))
    return {"A": a, "B": b, "N": n_mass, "dots": int(v.size), "binary": binary}


def strata_lambda(theta: np.ndarray, spec: StrataSpec) -> np.ndarray:
    """lambda_k = exp(theta_0 + sum_f theta_f[level]) with level 0 of every factor as reference."""
    logl = np.full(spec.n_strata, theta[0], np.float64)
    off = 1
    for j, n in enumerate(spec.n_levels):
        coef = np.concatenate([[0.0], theta[off: off + n - 1]])
        logl += coef[spec.stratum_levels[:, j]]
        off += n - 1
    return np.exp(np.clip(logl, -60.0, 5.0))


def n_params(spec: StrataSpec) -> int:
    return 1 + sum(n - 1 for n in spec.n_levels)


def predict_components(A: np.ndarray, B: np.ndarray, N: np.ndarray, sizes: np.ndarray, lam: np.ndarray) -> dict:
    tp = A @ lam
    m = B @ lam
    g = float(sizes @ lam)
    fp = np.maximum(N - m, 0.0)
    fn = g - tp
    dti = tp / (tp + ALPHA * fp + BETA * fn + 1e-12)
    return {"tp": tp, "m": m, "fp": fp, "fn": fn, "g": g, "dti": dti}


def fit(A: np.ndarray, B: np.ndarray, N: np.ndarray, s: np.ndarray, spec: StrataSpec,
        ridge: float = 1e-3, weights: np.ndarray | None = None, theta0: np.ndarray | None = None) -> dict:
    """Bounded least squares of predicted vs observed live DTI for the log-additive stratum model."""
    sizes = spec.sizes
    w = np.ones_like(s) if weights is None else np.asarray(weights, float)
    sw = np.sqrt(w)
    k = n_params(spec)
    if theta0 is None:
        # Start from the stratum-free solution: one density lambda for every pixel, solved exactly
        # from the linearised identity by NNLS (1 unknown).
        X = (A * (1 - ALPHA * s)[:, None] + ALPHA * s[:, None] * B - BETA * s[:, None] * sizes[None, :]).sum(axis=1)
        y = ALPHA * s * N
        lam0, _ = nnls(X[:, None], y)
        lam0 = float(lam0[0]) if lam0[0] > 0 else 2.5e-3
        theta0 = np.zeros(k)
        theta0[0] = np.log(lam0)

    def resid(theta):
        lam = strata_lambda(theta, spec)
        pred = predict_components(A, B, N, sizes, lam)["dti"]
        r = sw * (pred - s)
        return np.concatenate([r, np.sqrt(ridge) * theta[1:]])

    lo = np.full(k, -12.0)
    hi = np.full(k, 8.0)
    lo[0], hi[0] = -20.0, 0.0
    sol = least_squares(resid, np.clip(theta0, lo + 1e-9, hi - 1e-9), bounds=(lo, hi), method="trf",
                        x_scale="jac", max_nfev=4000)
    lam = strata_lambda(sol.x, spec)
    comp = predict_components(A, B, N, sizes, lam)
    return {"theta": sol.x, "lambda": lam, "pred": comp["dti"], "g": comp["g"], "cost": float(sol.cost),
            "success": bool(sol.success), "nfev": int(sol.nfev)}


def factor_effects(theta: np.ndarray, spec: StrataSpec) -> dict:
    """Multiplicative truth-density effect of every factor level relative to its reference level."""
    out = {}
    off = 1
    for name, n, labels in zip(spec.names, spec.n_levels, spec.level_labels):
        coef = np.concatenate([[0.0], theta[off: off + n - 1]])
        out[name] = {lab: float(np.exp(c)) for lab, c in zip(labels, coef)}
        off += n - 1
    return out


def loo(A, B, N, s, spec, groups: np.ndarray | None = None, ridge: float = 1e-3, theta0=None) -> dict:
    """Leave-one-out (or leave-one-group-out) live-score prediction."""
    n = len(s)
    groups = np.arange(n) if groups is None else np.asarray(groups)
    pred = np.full(n, np.nan)
    for gval in np.unique(groups):
        te = groups == gval
        tr = ~te
        f = fit(A[tr], B[tr], N[tr], s[tr], spec, ridge=ridge, theta0=theta0)
        pred[te] = predict_components(A[te], B[te], N[te], spec.sizes, f["lambda"])["dti"]
    err = pred - s
    from scipy.stats import spearmanr
    rho = spearmanr(pred, s).correlation if n > 2 else float("nan")
    return {"pred": pred, "mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err ** 2))),
            "max_abs_err": float(np.max(np.abs(err))), "spearman": float(rho),
            "abs_err_q90": float(np.quantile(np.abs(err), 0.90))}


def project(row: dict, spec: StrataSpec, lam: np.ndarray) -> dict:
    A = row["A"][None, :]
    B = row["B"][None, :]
    N = np.array([row["N"]])
    c = predict_components(A, B, N, spec.sizes, lam)
    return {k: (float(v[0]) if isinstance(v, np.ndarray) else float(v)) for k, v in c.items()}


# ------------------------------------------------------------------------------------------------
# LLI-v2: convex fit (unique optimum -> stable leave-one-out).  The identity is LINEAR in lambda, so
# a nonnegative least-squares problem with a graph-Laplacian smoothness prior over adjacent feature
# levels has a single global optimum.  Rows are divided by the current DTI denominator D_R, which turns
# the linear residual into a first-order DTI residual (delta_s ~= delta_f / D_R); 4 IRLS passes.
# ------------------------------------------------------------------------------------------------

def level_ranks_default(spec: StrataSpec) -> list[np.ndarray]:
    """Ordinal rank of every level used for adjacency (distance-ordered for the distance factors)."""
    ranks = []
    for name, n in zip(spec.names, spec.n_levels):
        if name == "d_catalogue_px":          # codes: 0=>50, 1=1, 2=1.4-2, 3=2.2-3, 4=3-5, 5=5-10, 6=10-20, 7=20-50
            ranks.append(np.array([7, 0, 1, 2, 3, 4, 5, 6]))
        elif name.startswith("d_") and name.endswith("_px"):   # codes: 0=far, 1=on, 2.. increasing distance
            ranks.append(np.array([n - 1] + list(range(0, n - 1))))
        else:
            ranks.append(np.arange(n))
    return ranks


def laplacian_edges(spec: StrataSpec, ranks: list[np.ndarray] | None = None) -> np.ndarray:
    """Pairs of strata that differ by one ordinal step in exactly one factor."""
    ranks = level_ranks_default(spec) if ranks is None else ranks
    lv = spec.stratum_levels.astype(np.int64)
    mult = np.cumprod([1] + list(spec.n_levels[:-1]))
    edges = []
    for j, n in enumerate(spec.n_levels):
        inv = np.argsort(ranks[j])           # rank -> level code
        for r in range(n - 1):
            a_code, b_code = inv[r], inv[r + 1]
            sel = np.nonzero(lv[:, j] == a_code)[0]
            partner = sel + (b_code - a_code) * mult[j]
            edges.append(np.stack([sel, partner], 1))
    return np.concatenate(edges) if edges else np.zeros((0, 2), np.int64)


def fit_convex(A, B, N, s, spec: StrataSpec, mu: float = 1.0, edges: np.ndarray | None = None,
               weights: np.ndarray | None = None, n_irls: int = 4, lam_init: np.ndarray | None = None) -> dict:
    from scipy.optimize import lsq_linear
    sizes = spec.sizes
    live = sizes > 0
    idx = np.nonzero(live)[0]
    remap = -np.ones(spec.n_strata, np.int64)
    remap[idx] = np.arange(idx.size)
    edges = laplacian_edges(spec) if edges is None else edges
    e = edges[(remap[edges[:, 0]] >= 0) & (remap[edges[:, 1]] >= 0)]
    e = remap[e]
    w = np.ones_like(s) if weights is None else np.asarray(weights, float)
    X0 = A[:, idx] * (1 - ALPHA * s)[:, None] + ALPHA * s[:, None] * B[:, idx] - BETA * s[:, None] * sizes[None, idx]
    y0 = ALPHA * s * N
    if lam_init is None:
        tot = X0.sum(axis=1)
        l0 = float(max(np.dot(tot, y0) / max(np.dot(tot, tot), 1e-30), 1e-6))
        lam = np.full(idx.size, l0)
    else:
        lam = np.asarray(lam_init, float)[idx].copy()
    scale = float(np.median(lam[lam > 0])) if (lam > 0).any() else 1e-3
    L = np.zeros((e.shape[0], idx.size))
    L[np.arange(e.shape[0]), e[:, 0]] = 1.0
    L[np.arange(e.shape[0]), e[:, 1]] = -1.0
    for _ in range(n_irls):
        comp = predict_components(A[:, idx], B[:, idx], N, sizes[idx], lam)
        D = comp["tp"] + ALPHA * comp["fp"] + BETA * comp["fn"]
        D = np.maximum(D, 1e-9)
        sw = np.sqrt(w) / D
        M = np.vstack([X0 * sw[:, None], np.sqrt(mu) * L / scale * 1e-2])
        rhs = np.concatenate([y0 * sw, np.zeros(L.shape[0])])
        sol = lsq_linear(M, rhs, bounds=(0.0, 1.0), method="trf", lsmr_tol="auto", max_iter=2000)
        lam = sol.x
        scale = float(np.median(lam[lam > 0])) if (lam > 0).any() else scale
    full = np.zeros(spec.n_strata)
    full[idx] = lam
    comp = predict_components(A, B, N, sizes, full)
    return {"lambda": full, "pred": comp["dti"], "g": comp["g"], "success": bool(sol.success)}


def loo_convex(A, B, N, s, spec, groups=None, mu: float = 1.0, edges=None, lam_init=None) -> dict:
    from scipy.stats import spearmanr
    n = len(s)
    groups = np.arange(n) if groups is None else np.asarray(groups)
    edges = laplacian_edges(spec) if edges is None else edges
    pred = np.full(n, np.nan)
    for gval in np.unique(groups):
        te = groups == gval
        f = fit_convex(A[~te], B[~te], N[~te], s[~te], spec, mu=mu, edges=edges, lam_init=lam_init)
        pred[te] = predict_components(A[te], B[te], N[te], spec.sizes, f["lambda"])["dti"]
    err = pred - s
    return {"pred": pred, "mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err ** 2))),
            "max_abs_err": float(np.max(np.abs(err))), "spearman": float(spearmanr(pred, s).correlation),
            "abs_err_q90": float(np.quantile(np.abs(err), 0.90))}
