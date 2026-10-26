"""Historical parallel MPLC lane — stopped after literal lattice duplication.

The earlier report described quadrant training, vendor hide-and-recover and
visible-only emission pruning. This review has not independently replayed the
fold provenance. The generator is disabled; old results remain historical.
"""
from __future__ import annotations
import sys, json, time
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vendor"))
sys.path.insert(0, str(ROOT / "src"))
from gems57 import holdout as vhold, metric as vmetric  # noqa: E402
from gems57.emit import expected_credit  # noqa: E402
from gems57.evaluate_holdout import pooled_summary  # noqa: E402
from gems57.grid import Grid  # noqa: E402

BUDGET_TOTAL = 37654
BLOCK = 200  # 20 km bootstrap blocks (vendor default)

# (path-key, band) base stack: 19 competition + 12 lidar + 4 rad + 4 extensions = 39
BASE_SPECS = ([("train", i) for i in range(1, 20)] + [("lidar", i) for i in range(1, 13)]
              + [("rad", i) for i in range(1, 5)] + [("ext", i) for i in range(1, 5)])
PATHS = {"train": ROOT / "data/training_features.tif", "lidar": ROOT / "data/external/lidar_scarp_features_u8.tif",
         "rad": ROOT / "data/external/geodawn_rad_u8.tif", "ext": ROOT / "data/external/geodawn_extensions_u8.tif"}


def load_grid():
    import rasterio
    with rasterio.open(ROOT / "data/sample_submission.tif") as ds:
        sample = ds.read(1); crs, tr = ds.crs, ds.transform
    with rasterio.open(ROOT / "data/labels.tif") as ds:
        labels = ds.read(1)
    footprint = np.isfinite(sample)
    catalogue = (labels > 0) & footprint
    return Grid(footprint=footprint, catalogue=catalogue, crs=crs, transform=tr,
                height=footprint.shape[0], width=footprint.shape[1]), footprint, catalogue


def band_window(key, band, window=None):
    import rasterio
    from rasterio.windows import Window
    with rasterio.open(PATHS[key]) as ds:
        if window is None:
            a = ds.read(band)
        else:
            r0, r1, c0, c1 = window
            a = ds.read(band, window=Window(c0, r0, c1 - c0, r1 - r0))
    a = a.astype(np.float32)
    if key == "train":
        a[~np.isfinite(a)] = np.nan
        a[a <= -3.0e38] = np.nan
    return a


def extract_points(ys, xs, use_mplc, mplc=None):
    """Feature matrix for points, reading one band at a time."""
    cols = []
    for key, band in BASE_SPECS:
        a = band_window(key, band)
        cols.append(a[ys, xs]); del a
    X = np.stack(cols, axis=1)
    if use_mplc:
        Xm = np.stack([mplc[i][ys, xs] for i in range(mplc.shape[0])], axis=1)
        X = np.concatenate([X, Xm], axis=1)
    return X


def predict_crop(model, bbox, use_mplc, mplc=None):
    r0, r1, c0, c1 = bbox[0].start, bbox[0].stop, bbox[1].start, bbox[1].stop
    h, w = r1 - r0, c1 - c0
    prob = np.zeros((h, w), np.float32)
    step = 128
    for rr in range(0, h, step):
        r_end = min(h, rr + step)
        cols = []
        for key, band in BASE_SPECS:
            cols.append(band_window(key, band, (r0 + rr, r0 + r_end, c0, c1)).ravel())
        if use_mplc:
            for i in range(mplc.shape[0]):
                cols.append(np.asarray(mplc[i][r0 + rr:r0 + r_end, c0:c1]).ravel())
        X = np.stack(cols, axis=1)
        prob[rr:r_end] = model.predict_proba(X)[:, 1].reshape(r_end - rr, w)
    return prob


def emit_dots(prob, allowed, budget):
    """Dotted greedy max-cover: rank by expected kernel credit E[k], accept in
    order, block Chebyshev <=2 px around each accepted dot."""
    ek = expected_credit(prob)
    cand = allowed & np.isfinite(prob)
    ys, xs = np.nonzero(cand)
    order = np.argsort(-ek[ys, xs], kind="stable")
    ys, xs = ys[order], xs[order]
    blocked = ~cand.copy()
    out = np.zeros(prob.shape, bool)
    n = 0
    H, W = prob.shape
    for y, x in zip(ys.tolist(), xs.tolist()):
        if n >= budget:
            break
        if blocked[y, x]:
            continue
        out[y, x] = True; n += 1
        blocked[max(0, y - 2):min(H, y + 3), max(0, x - 2):min(W, x + 3)] = True
    return out


def cell_terms(cell, emitted_crop):
    """Per-20km-block [TP,FP,FN,N] terms for one vendor cell (binary emission)."""
    p = emitted_crop & cell.active
    nblocks_y = (3730 + BLOCK - 1) // BLOCK; nblocks_x = (3292 + BLOCK - 1) // BLOCK
    terms = np.zeros((nblocks_y * nblocks_x, 4))
    r0, c0 = cell.bbox[0].start, cell.bbox[1].start
    ty, tx = cell.truth_yx
    if len(ty):
        dist_e = ndi.distance_transform_edt(~p)
        covers = vmetric.kernel(dist_e[ty, tx])
        ids = ((ty + r0) // BLOCK) * nblocks_x + ((tx + c0) // BLOCK)
        terms[:, 0] = np.bincount(ids, weights=covers, minlength=len(terms))
        terms[:, 2] = np.bincount(ids, weights=1.0 - covers, minlength=len(terms))
        terms[:, 3] = np.bincount(ids, minlength=len(terms))
    ey, ex = np.nonzero(p)
    if len(ey):
        fpw = 1.0 - cell.k_dg[ey, ex]
        ids = ((ey + r0) // BLOCK) * nblocks_x + ((ex + c0) // BLOCK)
        terms[:, 1] = np.bincount(ids, weights=fpw, minlength=len(terms))
    return terms


def run_holdout(budget_total=BUDGET_TOTAL, seed=20):
    raise RuntimeError("STOP: the parallel MPLC lane failed the literal registry-lattice uniqueness rule; no further experiment is authorized.")
    from sklearn.ensemble import HistGradientBoostingClassifier
    grid, footprint, catalogue = load_grid()
    ctx = vhold.build_holdout(grid, seeds=(seed,), modes=("all",))
    mplc = np.load(ROOT / "data/cache/mplc.npy", mmap_mode="r")
    quad = vhold.quadrant_ids(footprint)
    cache = ROOT / "data/cache"; cache.mkdir(parents=True, exist_ok=True)
    cells = ctx.cells
    actives = np.array([c.active.sum() for c in cells], float)
    budgets = np.maximum(1, np.round(budget_total * actives / actives.sum()).astype(int))
    result = {"evaluator": "KANLER-HOLDOUT-v1 (vendor gems57 holdout seed20 all + quadrant-train + vendor pooled_summary)",
              "cells": [], "budget_total": int(budget_total)}
    emitted_by_arm = {a: np.zeros(footprint.shape, bool) for a in ("base", "cand")}
    terms_by_arm = {}
    rng_global = np.random.default_rng(12345)
    for ci, cell in enumerate(cells):
        fold = cell.fold
        train_reg = footprint & (quad != fold)
        pos_yx = np.nonzero(catalogue & train_reg)
        neg_pool = np.nonzero(train_reg & ~ndi.binary_dilation(catalogue, iterations=3))
        n_neg = min(3 * len(pos_yx[0]), len(neg_pool[0]))
        pick = rng_global.choice(len(neg_pool[0]), size=n_neg, replace=False)
        ys = np.concatenate([pos_yx[0], neg_pool[0][pick]]); xs = np.concatenate([pos_yx[1], neg_pool[1][pick]])
        y = np.concatenate([np.ones(len(pos_yx[0]), np.int8), np.zeros(n_neg, np.int8)])
        t0 = time.time()
        Xfull = extract_points(ys, xs, True, mplc)
        np.save(cache / f"trainX_fold{fold}.npy", Xfull); np.save(cache / f"trainy_fold{fold}.npy", y)
        r0, r1, c0, c1 = cell.bbox[0].start, cell.bbox[0].stop, cell.bbox[1].start, cell.bbox[1].stop
        visible = catalogue & ~ctx.hidden_by_cell[cell.key]
        prune = ndi.binary_dilation(visible[cell.bbox], iterations=2)
        allowed = cell.active & ~prune
        for arm, use_mplc in (("base", False), ("cand", True)):
            X = Xfull if use_mplc else Xfull[:, :len(BASE_SPECS)]
            model = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.06, max_leaf_nodes=31,
                                                   min_samples_leaf=40, l2_regularization=1.0, random_state=7)
            wts = np.where(y == 1, len(y) / (2 * max(1, (y == 1).sum())), len(y) / (2 * max(1, (y == 0).sum())))
            model.fit(X, y, sample_weight=wts)
            prob = predict_crop(model, cell.bbox, use_mplc, mplc)
            np.save(cache / f"prob_{arm}_fold{fold}.npy", prob.astype(np.float16))
            dots = emit_dots(prob, allowed, int(budgets[ci]))
            emitted_by_arm[arm][cell.bbox] |= dots
            print(f"[{arm} fold{fold}] train {len(y)} ({int((y==1).sum())} pos) dots {dots.sum()} {time.time()-t0:.0f}s", flush=True)
        result["cells"].append({"key": cell.key, "n_truth": cell.n_truth, "budget": int(budgets[ci])})
    for arm in ("base", "cand"):
        np.save(cache / f"emitted_{arm}.npy", emitted_by_arm[arm])
        terms = np.zeros(((3730 + BLOCK - 1) // BLOCK * ((3292 + BLOCK - 1) // BLOCK), 4))
        per = {}
        for cell in cells:
            crop = emitted_by_arm[arm][cell.bbox]
            terms += cell_terms(cell, crop)
            per[cell.key] = vhold.score_cell(cell, emitted_by_arm[arm])
        terms_by_arm[arm] = terms
        result[arm] = {"per_cell": per}
    summary = pooled_summary(terms_by_arm, candidate="cand")
    result["summary"] = summary
    # champion anchor on identical cells (fixed raster; NOT fold-honest for the champion - disclosed)
    import rasterio
    champ_path = ROOT / "data/registry_rasters/champion_h33_b2_02778.tif"
    with rasterio.open(champ_path) as ds:
        champ = ds.read(1) > 0
    champ_terms = np.zeros_like(terms_by_arm["base"])
    for cell in cells:
        champ_terms += cell_terms(cell, champ[cell.bbox] & cell.active)
    terms_by_arm2 = dict(terms_by_arm); terms_by_arm2["champion_fixed"] = champ_terms
    result["summary_vs_champion"] = pooled_summary(terms_by_arm2, candidate="cand")
    (ROOT / "evidence/holdout_result.json").write_text(json.dumps(result, indent=2, default=float))
    print(json.dumps(summary["scores"], indent=2))
    print("paired vs base:", json.dumps(summary["paired_differences"], indent=2))
    return result


if __name__ == "__main__":
    run_holdout(int(sys.argv[1]) if len(sys.argv) > 1 else BUDGET_TOTAL)
