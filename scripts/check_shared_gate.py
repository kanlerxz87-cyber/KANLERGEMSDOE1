#!/usr/bin/env python3
"""Fail if the upstream preview stage ignores >70% preview-dot overlap."""
from __future__ import annotations
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REV = "07806249f4ed3efe70b4fbf866183c32392b7853"
template = ROOT / ".cache/upstream" / f"GEMSDOE32-{REV}"
try:
    subprocess.run(["bash", str(ROOT / "scripts/bootstrap_template.sh")], check=True, stdout=subprocess.DEVNULL)
except subprocess.CalledProcessError:
    print("Pinned template could not be restored; cannot perform shared-gate check.", file=sys.stderr)
    raise SystemExit(2)
sys.path.insert(0, str(template / "src"))
from gems32.release_gate import compare_registry  # noqa: E402

rng = np.random.default_rng(27)
surface, peer = rng.random((16, 16)), rng.random((16, 16))
footprint = np.ones((16, 16), dtype=bool)
dots = np.zeros((16, 16), dtype=bool)
dots[4, 4] = dots[11, 11] = True
result = compare_registry(surface, dots, footprint, {"peer": (peer, dots)}, stage="surface")
row = result["comparisons"][0]
print(f"surface rho={row['spearman']:.6f}; preview overlap={row['within_3px_fraction']:.3f}; passed={result['passed']}")
if result["passed"] and row["within_3px_fraction"] > 0.70:
    print("FAIL: upstream surface gate ignores the preview overlap. Stop before placement.", file=sys.stderr)
    raise SystemExit(1)
print("PASS: overlapping preview was rejected.")
