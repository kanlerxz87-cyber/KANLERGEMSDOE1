import sys, json
sys.path.insert(0,'src'); sys.path.insert(0,'vendor')
import numpy as np
from pathlib import Path
from scipy import ndimage as ndi
from sklearn.metrics import roc_auc_score
from kanler.lane import load_grid, BASE_SPECS, band_window, emit_dots, cell_terms, ROOT
from kanler.mplc import MPLC_NAMES
from gems57 import holdout as vhold

grid, footprint, catalogue = load_grid()
ctx = vhold.build_holdout(grid, seeds=(20,), modes=("all",))
mplc = np.load(ROOT/"data/cache/mplc.npy", mmap_mode="r")
rng = np.random.default_rng(999)
pos_yx = [[], []]
for cell in ctx.cells:
    ty, tx = cell.truth_yx
    r0, c0 = cell.bbox[0].start, cell.bbox[1].start
    pos_yx[0].append(ty + r0); pos_yx[1].append(tx + c0)
pos = (np.concatenate(pos_yx[0]), np.concatenate(pos_yx[1]))
# negatives: active pixels with zero kernel credit from truth (k_dg==0 inside cells), sampled
neg_candidates = []
for cell in ctx.cells:
    r0, c0 = cell.bbox[0].start, cell.bbox[1].start
    yy, xx = np.nonzero(cell.active & (cell.k_dg == 0))
    pick = rng.choice(len(yy), size=min(30000, len(yy)), replace=False)
    neg_candidates.append((yy[pick] + r0, xx[pick] + c0))
neg = (np.concatenate([n[0] for n in neg_candidates]), np.concatenate([n[1] for n in neg_candidates]))
ys = np.concatenate([pos[0], neg[0]]); xs = np.concatenate([pos[1], neg[1]])
y = np.concatenate([np.ones(len(pos[0])), np.zeros(len(neg[0]))])
names = [f"{k}{b}" for k, b in BASE_SPECS] + MPLC_NAMES
aucs = {}
for i, (k, b) in enumerate(BASE_SPECS):
    a = band_window(k, b); v = a[ys, xs].astype(float); del a
    ok = np.isfinite(v)
    aucs[names[i]] = float(roc_auc_score(y[ok], v[ok])) if ok.sum() > 100 else None
for i, nm in enumerate(MPLC_NAMES):
    v = np.asarray(mplc[i][ys, xs], float)
    aucs[nm] = float(roc_auc_score(y, v))
out = {"n_pos": int(len(pos[0])), "n_neg": int(len(neg[0])), "auc": aucs,
       "max_mplc_auc": max(aucs[n] for n in MPLC_NAMES),
       "flag_gt_0.90": [n for n, v in aucs.items() if v is not None and max(v, 1-v) > 0.90]}
Path("evidence/canary.json").write_text(json.dumps(out, indent=2))
print("MPLC AUCs:", {n: round(aucs[n],4) for n in MPLC_NAMES})
print("max |AUC-0.5| base:", max(abs(v-0.5) for v in aucs.values() if v is not None))
print("flags>0.90 (two-sided):", out["flag_gt_0.90"])

# EXP3: budget sweep on candidate probs
from gems57.evaluate_holdout import pooled_summary
cells = ctx.cells
for budget_total in (37654, 44090):
    actives = np.array([c.active.sum() for c in cells], float)
    budgets = np.maximum(1, np.round(budget_total * actives / actives.sum()).astype(int))
    emitted = np.zeros(footprint.shape, bool)
    for ci, cell in enumerate(cells):
        prob = np.load(ROOT/f"data/cache/prob_cand_fold{cell.fold}.npy").astype(np.float32)
        visible = catalogue & ~ctx.hidden_by_cell[cell.key]
        allowed = cell.active & ~ndi.binary_dilation(visible[cell.bbox], iterations=2)
        emitted[cell.bbox] |= emit_dots(prob, allowed, int(budgets[ci]))
    terms = np.zeros(((3730+199)//200 * ((3292+199)//200), 4))
    for cell in cells:
        terms += cell_terms(cell, emitted[cell.bbox] & cell.active)
    tp, fp, fn, n = terms.sum(axis=0)
    dti = tp / (tp + 0.2*fp + 0.8*fn)
    print(f"EXP3 cand budget {budget_total}: pooled HOLDOUT-DTI {dti:.5f} (TP {tp:.0f} FP {fp:.0f} FN {fn:.0f})")
    np.save(ROOT/f"data/cache/emitted_cand_b{budget_total}.npy", emitted)
