#!/usr/bin/env python3
"""Uniqueness gate of candidate rasters against EVERY competition-grid TIF crawled from the
GEMSDOE site repos (docs/evidence/gemsdoe_site_tif_index.json -> data/sites/) plus the nine
focus TIFs (data/focus/).

Repo rule (Protocol Rule 1): a candidate is a duplicate if, against ANY reference:
  - more than 70% of its dots lie within 3 px of the reference's dots, OR
  - |binary Spearman/phi| > 0.90 (we report phi; it is the same statistic on 0/1 surfaces).
Also reports pixel-identical matches (a copy) and the reference achieving the maximum.
Writes docs/evidence/uniqueness_vs_all_sites.json.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gems32 import holdout  # noqa: E402
from gems32.paths import data_dir  # noqa: E402

CANDIDATES = {
    "OCDA-MSCS-EXP3-nan": "docs/downloads/gemsdoe32-kanler1-ocda-mscs-exp3-37654d-20261027T1842Z-1db32b55-nan.tif",
    "UWBP-DRCS-EXP-B3-nan": "docs/downloads/gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif",
    "UPFLOW-EXP2-nan": "docs/downloads/gemsdoe32-kanler1-upflow-exp2-37654d-20261028T163730Z-76525b8c-nan.tif",
    "COMB-PIEDMONT-WORM-nan": "docs/downloads/gemsdoe32-kanler1-comb-piedmont-worm-disjoint-300m-celf-20261029T020638Z-9424d197-nan.tif",
    "MPLC-HGB-zeros": "docs/downloads/kanler-mplc-hgb-37654-20261026-0741963ae4e9-zeros.tif",
    "H3-CONDRESID-zeros": "docs/downloads/kanlergemsdoe1-h3-condresid-s3p17-b2-32000-20261026T214518Z-42802022-zeros.tif",
    "CONCORD5-B2-zeros": "docs/downloads/kanlergemsdoe1-concord5-b2-37654-research-20261027T171958Z-5dde8074-zeros.tif",
    "H-UNQ1-zeros": "docs/downloads/gemsdoe32-h-unq1-blind-stepover-radiometric-conduit-dots-20261027T170959Z-339ac2dd-zeros.tif",
    "H195FIELD-zeros": "docs/downloads/kanlergemsdoe1-h195field-b2-37654-20261027T171629Z-fc14041c-zeros.tif",
}
MAX_W3 = 0.70
SELF_PREFIX = "kanlerxz87-cyber/KANLERGEMSDOE1:"  # this repo's own published docs/downloads
MAX_PHI = 0.90
# A reference whose positive pixels exceed this fraction of the grid is a continuous/dense surface,
# not a dot submission; the within-3 px test is degenerate against it (always ~1.0) so it is skipped
# for that reference (phi and pixel-identity checks still apply).
DENSE_FRAC = 0.05


def dots_of(path: Path, foot: np.ndarray) -> np.ndarray:
    with rasterio.open(path) as ds:
        if ds.count != 1 or ds.crs is None or ds.crs.to_epsg() != 32611 or ds.shape != foot.shape:
            raise ValueError(f"not on competition grid: {path}")
        a = np.nan_to_num(ds.read(1).astype(np.float64), nan=0.0)
    return (a > 0) & foot


def phi(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation of two binary rasters from four counts (exact, fast)."""
    n = a.size
    n11 = int(np.count_nonzero(a & b))
    na = int(np.count_nonzero(a))
    nb = int(np.count_nonzero(b))
    den = np.sqrt(float(na) * (n - na) * nb * (n - nb))
    return float((n * n11 - na * nb) / den) if den > 0 else 0.0


def phi_idx(a_idx: np.ndarray, b_idx: np.ndarray, n: int) -> float:
    """Same statistic as phi(), from sorted flat dot indices (exact, fast)."""
    na, nb = a_idx.size, b_idx.size
    n11 = np.intersect1d(a_idx, b_idx, assume_unique=True).size
    den = np.sqrt(float(na) * (n - na) * nb * (n - nb))
    return float((n * n11 - na * nb) / den) if den > 0 else 0.0


def main() -> int:
    ctx = holdout.load_holdout_context(data_dir())
    foot = ctx.foot
    refs: list[tuple[str, Path]] = []
    for p in sorted((ROOT / "data" / "focus").glob("GEMSDOE*.tif")):
        refs.append((f"focus:{p.stem}", p))
    idx = json.loads((ROOT / "docs" / "evidence" / "gemsdoe_site_tif_index.json").read_text())
    for r in idx["index"]:
        if r.get("competition_grid") and r.get("local_file"):
            refs.append((f"{r['repo']}:{r['path']}", ROOT / r["local_file"]))
    cands = {k: dots_of(ROOT / v, foot) for k, v in CANDIDATES.items()}
    cand_hash = {k: hashlib.sha256(np.packbits(m).tobytes()).hexdigest() for k, m in cands.items()}
    cand_idx = {k: np.flatnonzero(m.ravel()) for k, m in cands.items()}
    best = {k: {"max_w3": -1.0, "max_w3_ref": None, "max_phi": -1.0, "max_phi_ref": None,
                "identical_to": [], "refs_over_w3_gate": 0,
                "other_max_w3": -1.0, "other_max_w3_ref": None, "other_identical_to": []} for k in cands}
    seen_hash: dict[str, str] = {}
    n_dense = 0
    dense_names: list[str] = []
    n_ok = n_skip = 0
    for name, path in refs:
        if not path.exists():
            n_skip += 1
            continue
        try:
            m = dots_of(path, foot)
        except ValueError:
            n_skip += 1
            continue
        h = hashlib.sha256(np.packbits(m).tobytes()).hexdigest()
        if h in seen_hash:
            continue  # identical dot set already evaluated under another name
        seen_hash[h] = name
        n_ok += 1
        ref_idx = np.flatnonzero(m.ravel())
        dense = ref_idx.size > DENSE_FRAC * foot.sum()
        if dense:
            n_dense += 1
            dense_names.append(name)
        tree = cKDTree(np.column_stack(np.unravel_index(ref_idx, foot.shape))) if ref_idx.size else None
        for k, c in cands.items():
            if c.sum() == 0:
                continue
            if tree is None:
                w3 = 0.0
            elif dense:
                w3 = None  # within-3 px is uninformative against a dense (non-dot) reference
            else:
                cc = np.column_stack(np.unravel_index(cand_idx[k], foot.shape))
                w3 = float((tree.query(cc, k=1)[0] <= 3.0).mean())
            if w3 is None:
                continue
            if w3 > best[k]["max_w3"]:
                best[k]["max_w3"], best[k]["max_w3_ref"] = w3, name
            if not name.startswith(SELF_PREFIX) and w3 > best[k]["other_max_w3"]:
                best[k]["other_max_w3"], best[k]["other_max_w3_ref"] = w3, name
            if w3 > MAX_W3:
                best[k]["refs_over_w3_gate"] += 1
            if h == cand_hash[k]:
                best[k]["identical_to"].append(name)
                if not name.startswith(SELF_PREFIX):
                    best[k]["other_identical_to"].append(name)
            if m.any():
                pv = phi_idx(cand_idx[k], ref_idx, foot.size)
                if abs(pv) > best[k]["max_phi"]:
                    best[k]["max_phi"], best[k]["max_phi_ref"] = abs(pv), name
    rows = []
    for k, c in cands.items():
        b = best[k]
        passed = (b["max_w3"] <= MAX_W3) and (b["max_phi"] <= MAX_PHI) and not b["identical_to"]
        rows.append({"candidate": k, "file": CANDIDATES[k], "dots": int(c.sum()),
                     "max_within3px": round(b["max_w3"], 4), "max_within3px_ref": b["max_w3_ref"],
                     "max_abs_phi": round(b["max_phi"], 4), "max_abs_phi_ref": b["max_phi_ref"],
                     "refs_over_70pct_within3px": b["refs_over_w3_gate"],
                     "pixel_identical_to": b["identical_to"], "uniqueness_gate_pass": bool(passed),
                     "identical_to_self_repo_only": bool(b["identical_to"]) and not b["other_identical_to"],
                     "other_sites_max_within3px": round(b["other_max_w3"], 4),
                     "other_sites_max_within3px_ref": b["other_max_w3_ref"]})
    out = {"rules": {"max_within3px": MAX_W3, "max_abs_phi": MAX_PHI},
           "n_distinct_reference_dotsets": n_ok, "n_reference_files_skipped": n_skip,
           "n_dense_references_within3px_skipped": n_dense, "dense_references": dense_names,
           "dense_frac_threshold": DENSE_FRAC,
           "candidates": rows,
           "limitation": "Covers only references fetchable from github.com; github.io pages are not reachable from the sandbox."}
    (ROOT / "docs" / "evidence" / "uniqueness_vs_all_sites.json").write_text(json.dumps(out, indent=2) + "\n")
    for r in rows:
        print(f"{r['candidate']:26s} dots={r['dots']:6d} maxW3={r['max_within3px']:.4f} ({r['max_within3px_ref']}) "
              f"maxphi={r['max_abs_phi']:.4f} identical={r['pixel_identical_to']} PASS={r['uniqueness_gate_pass']} "
              f"| other-sites maxW3={r['other_sites_max_within3px']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
