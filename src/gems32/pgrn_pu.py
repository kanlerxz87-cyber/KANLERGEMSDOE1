"""Physics-guarded reliable-negative positive-unlabelled learning for the MDRC lane.

The key invariant is fold locality: ``visible_labels`` is the only catalogue array
accepted by the sampler. High label-free physical-concordance pixels are protected
from the negative class instead of being silently treated as confirmed negatives.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import distance_transform_edt
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score


@dataclass(frozen=True)
class TrainingReceipt:
    reliable_negative_quantile: float
    physical_threshold: float
    n_visible_positive_pool: int
    n_positive_sample: int
    n_unlabelled_eligible_before_physics_guard: int
    n_reliable_negative_pool: int
    n_reliable_negative_sample: int
    halo_exclude_px: float

    def as_dict(self) -> dict:
        return {
            "reliable_negative_quantile": self.reliable_negative_quantile,
            "physical_threshold": self.physical_threshold,
            "n_visible_positive_pool": self.n_visible_positive_pool,
            "n_positive_sample": self.n_positive_sample,
            "n_unlabelled_eligible_before_physics_guard": self.n_unlabelled_eligible_before_physics_guard,
            "n_reliable_negative_pool": self.n_reliable_negative_pool,
            "n_reliable_negative_sample": self.n_reliable_negative_sample,
            "halo_exclude_px": self.halo_exclude_px,
        }


def select_training_indices(
    visible_labels: np.ndarray,
    train_mask: np.ndarray,
    physical_prior: np.ndarray,
    *,
    reliable_negative_quantile: float,
    rng: np.random.Generator,
    halo_exclude_px: float = 5.0,
    max_positive: int = 50_000,
    negative_ratio: int = 4,
) -> tuple[np.ndarray, np.ndarray, TrainingReceipt]:
    """Return sorted flat indices and labels for one reliable-negative PU fit.

    Only low-physical-concordance unlabelled pixels farther than ``halo_exclude_px``
    from *visible* labels can enter the negative class. The physical threshold is
    estimated inside the fold's training region, never in its held-out quadrant.
    """
    visible = np.asarray(visible_labels, bool)
    train = np.asarray(train_mask, bool)
    prior = np.asarray(physical_prior, np.float32)
    if visible.shape != train.shape or prior.shape != train.shape:
        raise ValueError("visible_labels/train_mask/physical_prior shape mismatch")
    if not (0.0 < reliable_negative_quantile < 1.0):
        raise ValueError("reliable_negative_quantile must be in (0, 1)")
    if np.any(visible & ~train) and not np.any(visible & train):
        raise ValueError("training mask excludes every visible positive")
    if not np.isfinite(prior[train]).all():
        raise ValueError("physical prior must be finite in the training region")

    pos_pool = np.flatnonzero(visible & train)
    if pos_pool.size == 0:
        raise ValueError("no fold-visible positive pixels in training region")
    pos_idx = (
        rng.choice(pos_pool, size=max_positive, replace=False)
        if pos_pool.size > max_positive
        else pos_pool
    )

    # Every catalogue-dependent operation is derived from the fold-visible mask.
    d_visible = distance_transform_edt(~visible)
    eligible_mask = train & ~visible & (d_visible > halo_exclude_px)
    eligible_vals = prior[eligible_mask]
    if eligible_vals.size == 0:
        raise ValueError("no unlabelled pixels survive the visible-fault halo")
    threshold = float(np.quantile(eligible_vals, reliable_negative_quantile))
    neg_pool = np.flatnonzero(eligible_mask & (prior <= threshold))
    if neg_pool.size == 0:
        raise ValueError("physics guard produced an empty reliable-negative pool")
    n_neg = min(neg_pool.size, max(int(pos_idx.size) * int(negative_ratio), 1))
    neg_idx = rng.choice(neg_pool, size=n_neg, replace=False)

    idx = np.concatenate([pos_idx, neg_idx]).astype(np.int64, copy=False)
    y = np.concatenate([
        np.ones(pos_idx.size, dtype=np.int8),
        np.zeros(neg_idx.size, dtype=np.int8),
    ])
    order = np.argsort(idx)
    receipt = TrainingReceipt(
        reliable_negative_quantile=float(reliable_negative_quantile),
        physical_threshold=threshold,
        n_visible_positive_pool=int(pos_pool.size),
        n_positive_sample=int(pos_idx.size),
        n_unlabelled_eligible_before_physics_guard=int(eligible_vals.size),
        n_reliable_negative_pool=int(neg_pool.size),
        n_reliable_negative_sample=int(neg_idx.size),
        halo_exclude_px=float(halo_exclude_px),
    )
    return idx[order], y[order], receipt


def extract_feature_rows(
    base_stack: np.ndarray,
    extra_stack: np.ndarray,
    flat_indices: np.ndarray,
    *,
    chunk_rows: int = 256,
) -> np.ndarray:
    """Read sorted random rows sequentially from two disk-backed feature stacks."""
    h, w, n_base = base_stack.shape
    if extra_stack.shape[:2] != (h, w):
        raise ValueError("base and extra stack grids differ")
    idx = np.asarray(flat_indices, np.int64)
    if idx.ndim != 1 or (idx.size and (idx[0] < 0 or idx[-1] >= h * w)):
        raise ValueError("flat_indices outside stack grid")
    if idx.size > 1 and np.any(idx[1:] < idx[:-1]):
        raise ValueError("flat_indices must be sorted for sequential extraction")

    n_extra = extra_stack.shape[2]
    out = np.empty((idx.size, n_base + n_extra), dtype=np.float32)
    rows = idx // w
    cols = idx % w
    start = 0
    for y0 in range(0, h, chunk_rows):
        y1 = min(h, y0 + chunk_rows)
        end = int(np.searchsorted(rows, y1, side="left"))
        if end > start:
            rr = rows[start:end] - y0
            cc = cols[start:end]
            out[start:end, :n_base] = np.asarray(base_stack[y0:y1], np.float32)[rr, cc]
            out[start:end, n_base:] = np.asarray(extra_stack[y0:y1], np.float32)[rr, cc]
            start = end
        if start == idx.size:
            break
    if start != idx.size:
        raise RuntimeError("sequential feature extraction did not consume every index")
    return out


def fit_reliable_negative_model(X: np.ndarray, y: np.ndarray, *, seed: int) -> HistGradientBoostingClassifier:
    """Fit the deterministic CPU model used by each PGRN bag member."""
    model = HistGradientBoostingClassifier(
        max_iter=150,
        learning_rate=0.065,
        max_leaf_nodes=63,
        min_samples_leaf=80,
        l2_regularization=2.5,
        early_stopping=False,
        random_state=int(seed),
    )
    # Balance positive and reliable-negative totals. This changes calibration, not
    # the physical guard, and prevents the arbitrary 1:4 sampling ratio dominating.
    n_pos = max(int((y == 1).sum()), 1)
    n_neg = max(int((y == 0).sum()), 1)
    weights = np.where(y == 1, 0.5 / n_pos, 0.5 / n_neg).astype(np.float64)
    weights *= y.size
    model.fit(X, y, sample_weight=weights)
    return model


def predict_models_on_mask(
    models: dict[float, HistGradientBoostingClassifier],
    base_stack: np.ndarray,
    extra_stack: np.ndarray,
    target_mask: np.ndarray,
    *,
    chunk_rows: int = 128,
) -> dict[float, np.ndarray]:
    """Predict several PU bags in one sequential pass over a target grid."""
    h, w, n_base = base_stack.shape
    n_extra = extra_stack.shape[2]
    target = np.asarray(target_mask, bool)
    if target.shape != (h, w):
        raise ValueError("target mask shape mismatch")
    outputs = {q: np.zeros((h, w), dtype=np.float32) for q in models}
    for y0 in range(0, h, chunk_rows):
        y1 = min(h, y0 + chunk_rows)
        sub = target[y0:y1]
        if not sub.any():
            continue
        rr, cc = np.nonzero(sub)
        xb = np.asarray(base_stack[y0:y1], np.float32)[rr, cc]
        xe = np.asarray(extra_stack[y0:y1], np.float32)[rr, cc]
        X = np.empty((rr.size, n_base + n_extra), dtype=np.float32)
        X[:, :n_base] = xb
        X[:, n_base:] = xe
        for q, model in models.items():
            outputs[q][y0 + rr, cc] = model.predict_proba(X)[:, 1].astype(np.float32)
    return outputs


def compose_physics_guarded_surface(
    posterior: np.ndarray,
    physical_prior: np.ndarray,
    corroboration_gate: np.ndarray,
    footprint: np.ndarray,
) -> np.ndarray:
    """Fuse PU posterior with a soft, label-free physical guard before crest NMS."""
    p = np.clip(np.nan_to_num(posterior, nan=0.0), 0.0, 1.0)
    phys = np.clip(np.nan_to_num(physical_prior, nan=0.0), 0.0, 1.0)
    gate = np.clip(np.nan_to_num(corroboration_gate, nan=0.0), 0.0, 1.0)
    out = (
        np.power(np.maximum(p, 1e-6), 0.72)
        * np.power(0.20 + 0.80 * phys, 0.28)
        * (0.65 + 0.35 * gate)
    ).astype(np.float32)
    out[~np.asarray(footprint, bool)] = 0.0
    return out


def two_polarity_feature_canary(
    base_stack: np.ndarray,
    extra_stack: np.ndarray,
    labels: np.ndarray,
    footprint: np.ndarray,
    quadrants: np.ndarray,
    channel_names: list[str],
    *,
    seed: int,
    n_negative: int = 200_000,
) -> dict:
    """Single-feature pooled and per-quadrant two-polarity AUC leakage screen."""
    rng = np.random.default_rng(seed)
    pos_idx = np.flatnonzero(labels & footprint)
    neg_pool = np.flatnonzero(footprint & ~labels)
    neg_idx = rng.choice(neg_pool, size=min(n_negative, neg_pool.size), replace=False)
    idx = np.sort(np.concatenate([pos_idx, neg_idx]))
    X = extract_feature_rows(base_stack, extra_stack, idx)
    y_by_flat = np.zeros(footprint.size, dtype=np.int8)
    y_by_flat[pos_idx] = 1
    y = y_by_flat[idx]
    qv = quadrants.ravel()[idx]

    if X.shape[1] != len(channel_names):
        raise ValueError("channel_names length does not match feature stacks")
    rows: dict[str, dict] = {}
    worst_auc = 0.0
    worst_name = ""
    for j, name in enumerate(channel_names):
        x = X[:, j].astype(np.float64)
        finite = np.isfinite(x)
        fill = float(np.median(x[finite])) if finite.any() else 0.0
        x[~finite] = fill
        auc0 = float(roc_auc_score(y, x))
        pooled = max(auc0, 1.0 - auc0)
        per_q: dict[str, float] = {}
        for q in range(4):
            m = qv == q
            if m.any() and np.unique(y[m]).size == 2:
                aq = float(roc_auc_score(y[m], x[m]))
                per_q[str(q)] = max(aq, 1.0 - aq)
        qmax = max(per_q.values(), default=pooled)
        oriented = max(pooled, qmax)
        rows[name] = {
            "pooled_two_polarity_auc": pooled,
            "per_quadrant_two_polarity_auc": per_q,
            "max_two_polarity_auc": oriented,
        }
        if oriented > worst_auc:
            worst_auc, worst_name = oriented, name
    return {
        "n_channels": len(channel_names),
        "n_positive": int(pos_idx.size),
        "n_negative": int(neg_idx.size),
        "threshold": 0.90,
        "worst_auc": worst_auc,
        "worst_channel": worst_name,
        "passed": bool(worst_auc <= 0.90),
        "channels": rows,
    }
