"""CPU-feasible detectors trained on the visible catalogue.

The sandbox has 2 vCPU / 3 GB RAM, so a U-Net (the official reference solution) is out of reach
here; these are honest baselines for *harness* work, not the proposed final model.  The detector
matters only through the field it produces; the emission rule is validated on that field.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


@dataclass
class DetectorSpec:
    kind: str = "hgb"          # 'hgb' | 'logistic'
    max_iter: int = 80
    learning_rate: float = 0.1
    max_leaf_nodes: int = 31
    sample_pos: int = 60_000
    sample_neg: int = 240_000
    seed: int = 0

    def as_dict(self):
        return asdict(self)


def sample_training_rows(stack: np.ndarray, labels: np.ndarray, train_mask: np.ndarray,
                         spec: DetectorSpec, rng: np.random.Generator):
    """Sample (X, y) from a *training region only* (blocks are removed by ``train_mask``).

    Negatives are drawn by rejection sampling on flat indices rather than ``setdiff1d``, because
    sorting 12 M indices was the dominant cost of a fold on this CPU-only box.
    """
    h, w, f = stack.shape
    flat_lab = labels.reshape(-1)
    flat_tr = train_mask.reshape(-1)
    pos = np.flatnonzero(labels & train_mask)
    if pos.size > spec.sample_pos:
        pos = rng.choice(pos, spec.sample_pos, replace=False)
    neg_parts, got = [], 0
    while got < spec.sample_neg:
        need = int((spec.sample_neg - got) * 1.35) + 4096
        idx = rng.integers(0, h * w, size=need, dtype=np.int64)
        idx = idx[flat_tr[idx] & ~flat_lab[idx]]
        if idx.size:
            neg_parts.append(idx)
            got += idx.size
    neg = np.concatenate(neg_parts)[:spec.sample_neg]
    idx = np.concatenate([pos, neg])
    y = np.concatenate([np.ones(pos.size, np.int8), np.zeros(neg.size, np.int8)])
    flat = stack.reshape(-1, f)                      # memmap-friendly: no full materialisation
    X = np.asarray(flat[np.sort(idx)], dtype=np.float32)
    order = np.argsort(idx)                          # keep X and y aligned after the sort
    y = y[order] if order.size == y.size else y
    return X, y


class Detector:
    def __init__(self, spec: DetectorSpec | None = None):
        self.spec = spec or DetectorSpec()
        self.model = None
        self.mu = None
        self.sd = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        self.mu = X.mean(0)
        self.sd = X.std(0) + 1e-6
        Xs = (X - self.mu) / self.sd
        if self.spec.kind == "hgb":
            from sklearn.ensemble import HistGradientBoostingClassifier
            self.model = HistGradientBoostingClassifier(
                max_iter=self.spec.max_iter, learning_rate=self.spec.learning_rate,
                max_leaf_nodes=self.spec.max_leaf_nodes, early_stopping=False,
                random_state=self.spec.seed)
            self.model.fit(Xs, y)
        else:
            from sklearn.linear_model import LogisticRegression
            self.model = LogisticRegression(max_iter=400, class_weight="balanced")
            self.model.fit(Xs, y)
        return self

    def predict_field(self, stack: np.ndarray, y0: int, y1: int) -> np.ndarray:
        """Probability field for rows [y0, y1) of the stack."""
        block = stack[y0:y1]
        h, w, f = block.shape
        Xs = (np.asarray(block, dtype=np.float32).reshape(-1, f) - self.mu) / self.sd
        p = self.model.predict_proba(Xs)[:, 1].astype(np.float32)
        return p.reshape(h, w)
