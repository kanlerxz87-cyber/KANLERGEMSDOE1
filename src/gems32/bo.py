"""Bayesian-optimisation slot controller: GP surrogate + expected improvement + cost gate.

The competition gives at most three scored submissions per week and one submission that counts
for both prize rounds, so a live submission is an *expensive, rate-limited observation* next to
the unlimited cheap evaluations available on the local holdout.  This module makes that
asymmetry explicit:

* every evaluation -- submitted or not -- is appended to an observation log
  (``registry/observations.jsonl``): one JSON object per line with the design vector, the
  holdout score, the (optional) live score and its verification status;
* a Gaussian-process surrogate models ``score = f(design) + noise`` with an anisotropic RBF
  kernel, fitted on the log;
* the acquisition is **expected improvement** over the incumbent best, penalised by the cost of
  a slot (``cost_slots``) and by the risk of the two-round objective (a single submission is
  re-scored in round 2 against an expanded label set, so its value is ``DTI_1 + rho * DTI_2``);
* a persistent gap between the surrogate's prediction and the live score is reported as
  *holdout drift* -- evidence that the local proxy no longer tracks the live scoring
  distribution -- rather than as noise.

The GP is a plain implementation (no external surrogate dependency) so the whole controller is
auditable and unit-testable offline.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, fields
from pathlib import Path

import numpy as np

LOG_DEFAULT = Path("registry/observations.jsonl")


@dataclass
class Observation:
    """One evaluation, submitted or not: the surrogate's training data.

    ``kind`` is ``holdout`` (cheap, unlimited, on the proxy) or ``live`` (expensive: one of the three
    weekly slots).  ``x`` is the design vector when one is available, which is what the GP consumes;
    ``live`` records the leaderboard score once a design has actually been submitted, so a persistent
    gap between what the surrogate predicts and what the board returns can be measured.
    """
    kind: str
    name: str
    score: float
    n_px: float | None = None
    source: str = ""
    design_id: str = ""
    x: list | None = None
    live: float | None = None
    live_verified: bool = False
    note: str = ""
    meta: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True)

    @staticmethod
    def from_json(line: str) -> "Observation":
        d = json.loads(line)
        known = {f.name for f in fields(Observation)}
        return Observation(**{k: v for k, v in d.items() if k in known})


def append_observation(obs: Observation, path: str | Path = LOG_DEFAULT) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(obs.to_json() + "\n")
    return p


def load_observations(path: str | Path = LOG_DEFAULT) -> list[Observation]:
    p = Path(path)
    if not p.exists():
        return []
    return [Observation.from_json(ln) for ln in p.read_text().splitlines() if ln.strip()]


# ---------------------------------------------------------------------------------------------- GP
class GPSurrogate:
    """Anisotropic-RBF Gaussian process with a fitted noise level (maximises log marginal L)."""

    def __init__(self, lengthscale: float = 0.5, noise: float = 1e-3, jitter: float = 1e-8):
        self.lengthscale = float(lengthscale)
        self.noise = float(noise)
        self.jitter = float(jitter)

    @staticmethod
    def _k(a, b, ls):
        d = a[:, None, :] - b[None, :, :]
        return np.exp(-0.5 * np.sum((d / ls) ** 2, axis=-1))

    def fit(self, X: np.ndarray, y: np.ndarray):
        X = np.atleast_2d(np.asarray(X, float))
        y = np.asarray(y, float)
        self.X = X
        self.y_mean = y.mean()
        yc = y - self.y_mean
        ls_grid = np.array([0.15, 0.3, 0.5, 0.8, 1.2]) * X.shape[1] ** 0.5
        best = (-np.inf, self.lengthscale, self.noise)
        for ls in ls_grid:
            for noise in (1e-4, 1e-3, 1e-2):
                K = self._k(X, X, ls) + (noise + self.jitter) * np.eye(X.shape[0])
                try:
                    L = np.linalg.cholesky(K)
                except np.linalg.LinAlgError:
                    continue
                alpha = np.linalg.solve(L.T, np.linalg.solve(L, yc))
                ll = -0.5 * yc @ alpha - np.log(np.diag(L)).sum() - 0.5 * X.shape[0] * math.log(2 * math.pi)
                if ll > best[0]:
                    best = (ll, ls, noise)
        _, self.lengthscale, self.noise = best
        K = self._k(X, X, self.lengthscale) + (self.noise + self.jitter) * np.eye(X.shape[0])
        self.L = np.linalg.cholesky(K)
        self.alpha = np.linalg.solve(self.L.T, np.linalg.solve(self.L, yc))
        self.fitted = True
        return self

    def predict(self, Xs: np.ndarray):
        Xs = np.atleast_2d(np.asarray(Xs, float))
        Ks = self._k(self.X, Xs, self.lengthscale)
        mu = Ks.T @ self.alpha + self.y_mean
        v = np.linalg.solve(self.L, Ks)
        var = np.clip(np.diag(self._k(Xs, Xs, self.lengthscale)) - np.sum(v ** 2, axis=0), 1e-12, None)
        return mu, np.sqrt(var)


def expected_improvement(mu: np.ndarray, sd: np.ndarray, best: float, xi: float = 0.0) -> np.ndarray:
    """EI for maximisation with a normal posterior and an exploration margin ``xi``."""
    from scipy.stats import norm
    mu, sd = np.asarray(mu, float), np.asarray(sd, float)
    imp = mu - best - xi
    z = imp / sd
    return imp * norm.cdf(z) + sd * norm.pdf(z)


@dataclass
class SlotDecision:
    design_id: str
    holdout: float
    ei: float
    incumbent: float
    bar: float
    approved: bool
    reasons: list = field(default_factory=list)

    def as_dict(self):
        return self.__dict__


def slot_gate(candidates: list[dict], incumbent: float, rho: float = 1.0,
              min_holdout_gain: float = 0.0005, min_ei: float = 0.0, cost_slots: float = 1.0) -> SlotDecision:
    """Decide whether to spend one of the week's slots on the best candidate.

    A candidate is approved only if **all** of the following hold:

    1. its holdout score beats the incumbent by ``min_holdout_gain`` (the standing "don't spend a
       slot on an idea that has not beaten the holdout" rule);
    2. the surrogate's expected improvement over the incumbent exceeds ``min_ei`` plus the
       explicit slot cost (a slot is a scarce, rate-limited observation -- three per week);
    3. the design is not already in the verified-live record (do not pay twice for one piece of
       information).

    ``rho`` is the round-2 weight in the objective ``DTI_1 + rho * DTI_2``: for a *discovery*
    candidate (a prediction that is likely to be verified as a new fault by the expert panel)
    the effective bar is lower, ``bar / (1 + rho)``, because the same file is re-scored against
    an expanded label set.
    """
    best = max(candidates, key=lambda c: c.get("mu", c.get("holdout", -1)))
    bar = max(min_ei, cost_slots * 1e-3)
    # The two-round objective DTI_1 + rho*DTI_2 prices a *discovery* candidate (a prediction with a
    # plausible path to being verified as a new fault by the expert panel) as if rho extra rounds of
    # credit were riding on it, so its effective bar and required gain are divided by (1 + rho).
    discovery = bool(best.get("discovery"))
    eff_bar = bar / (1.0 + (rho if discovery else 0.0))
    eff_gain = min_holdout_gain / (1.0 + (rho if discovery else 0.0))
    reasons = []
    if best.get("holdout", -1) - incumbent < eff_gain:
        reasons.append("holdout does not beat the incumbent by the required margin")
    if best.get("ei", 0.0) < eff_bar:
        reasons.append("expected improvement below the cost of a slot")
    if best.get("already_live"):
        reasons.append("design already has a verified live observation")
    if best.get("format_ok") is False:
        reasons.append("submission artifact failed its format receipt")
    return SlotDecision(best.get("design_id", "?"), best.get("holdout", float("nan")),
                        best.get("ei", float("nan")), incumbent, eff_bar, not reasons, reasons)


def drift_report(observations: list[Observation], surrogate: GPSurrogate, threshold: float = 0.03) -> dict:
    """Compare surrogate predictions with live scores; a persistent gap is holdout drift."""
    live = [o for o in observations if o.live is not None and o.x is not None]
    if not live or not getattr(surrogate, "fitted", False):
        return {"n": 0, "status": "insufficient data"}
    mu, sd = surrogate.predict(np.array([o.x for o in live], float))
    resid = np.array([o.live for o in live]) - mu
    return {"n": len(live), "mean_residual": float(resid.mean()), "sd_residual": float(resid.std()),
            "status": "drift-suspected" if abs(resid.mean()) > threshold else "consistent",
            "threshold": threshold, "residuals": resid.round(6).tolist()}
