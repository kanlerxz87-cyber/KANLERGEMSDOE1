#!/usr/bin/env python3
"""Fail if the pinned shared evaluator drops FP mass in zero-truth cells.

Synthetic bookkeeping probe only: no real experiment, trained model, or score.
The upstream implementation is imported unchanged, never shadowed or patched.
"""
from __future__ import annotations
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REV = '07806249f4ed3efe70b4fbf866183c32392b7853'
try:
    subprocess.run(['bash', str(ROOT/'scripts/bootstrap_template.sh')], check=True, stdout=subprocess.DEVNULL)
except subprocess.CalledProcessError:
    print('Pinned template could not be restored; cannot check holdout bookkeeping.', file=sys.stderr)
    raise SystemExit(2)
sys.path.insert(0, str(ROOT/'.cache/upstream'/f'GEMSDOE32-{REV}'/'src'))
from gems32.holdout import DRAWS, FOLDS, evaluate_hide_and_recover  # noqa: E402

foot = np.ones((2, 2), bool)
mask = np.zeros((2, 2), bool); mask[0, 0] = True
cells = []
for i, (draw, fold) in enumerate((d, f) for d in DRAWS for f in FOLDS):
    positive = i == 0
    truth = (np.array([0], dtype=int), np.array([0], dtype=int)) if positive else (np.array([], dtype=int), np.array([], dtype=int))
    kernel = np.zeros((2, 2), dtype=float)
    if positive:
        kernel[0, 0] = 1.0
    cells.append(SimpleNamespace(key=f'draw{draw}_fold{fold}', bbox=(slice(0, 2), slice(0, 2)),
                                 active_sub=foot, n_truth=int(positive), truth_coords=truth,
                                 d_vis_sub=None, k_dg_sub=kernel))
result = evaluate_hide_and_recover(mask, SimpleNamespace(foot=foot, cells=cells), grid_n=2, n_boot=20)
tp, fp, fn, _ = result['_block_totals']
fold_totals = tuple(sum(row[k] for row in result['folds'].values()) for k in ('tp', 'fp', 'fn'))
block_totals = (float(tp.sum()), float(fp.sum()), float(fn.sum()))
print(f'fold TP/FP/FN={fold_totals}; pooled block TP/FP/FN={block_totals}')
if not np.allclose(fold_totals, block_totals):
    print('FAIL: shared evaluator drops pooled mass in a zero-truth cell. Stop before holdout.', file=sys.stderr)
    raise SystemExit(1)
print('PASS: fold and pooled bookkeeping agree.')
