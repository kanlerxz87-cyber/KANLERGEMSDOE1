#!/usr/bin/env python3
"""Pairwise overlap/rank-correlation of candidate files vs each GEMSDOE site's top-listed file.

Used for the executive-summary uniqueness column. Same definitions as gems32.registry_audit:
 * within_3px = fraction of candidate dots within a 3-px disk of a site dot
 * phi = Pearson correlation of the two binary dot masks inside the footprint (|phi| is the binary case of |rho|)
Inputs are read from the owner-repo clones (outside the repo, see scripts/audit_owner_registry.py).
"""
from __future__ import annotations
import json, sys, hashlib
from pathlib import Path
import numpy as np, rasterio
from scipy.ndimage import binary_dilation
ROOT = Path(__file__).resolve().parents[1]
OWN = Path("/tmp/owners")
SITES = {
 "GEMSDOE24": "docs/downloads/gems24-h25-1-dotted-h19-5-d1-5-20261002-989f59505db1-nan.tif",
 "GEMSDOE25": "docs/downloads/gems25-dotted-h19-5-d2-8-20261002-e56ea318af89-nan.tif",
 "GEMSDOE27": "docs/downloads/gems27-topo-gap-closure-t-v2-on-d1-5-20261002-5512495c6bd1-nan.tif",
 "GEMSDOE28": "docs/downloads/gems28-h36-1-rung30-blind-r1-20261003-b531dae0a36f-nan.tif",
 "GEMSDOE30": "docs/downloads/gemsdoe30-d28-poisson300m-offcat-44090-20261003T233156Z-91eae1ca-nanoutside.tif",
 "GEMSDOE31": "docs/downloads/gemsdoe31-h27-4-solo-d28-20261004-8acb75e1-nan.tif",
 "GEMSDOE32": "docs/downloads/gemsdoe32-h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros.tif",
 "GEMSDOE33": "docs/downloads/GEMSDOE33-h33d-analog-tip-stepover-r30-20261004-cb490425926e-nanoutside.tif",
 "GEMSDOE36": "docs/downloads/gemsdoe36-anderson-geothermal-pinn-38854-20261004T230000Z-9b9ea4e6-zeros.tif",
}
CANDS = {
 "OCDA-MSCS-EXP3 (recommended)": "docs/downloads/kanlergemsdoe1-DOWNLOAD-ocda-mscs-exp3-nan.tif",
 "HGB-FOLDLOCAL-E2 (new)": "docs/downloads/kanlergemsdoe1-hgb-foldlocal-nms3-b2-20261031T005029Z-48e16833-nan.tif",
 "UWBP-DRCS-EXP3 (prior verdict)": "docs/downloads/gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif",
}
def dots(path, foot):
    with rasterio.open(path) as ds:
        a = ds.read(1)
    return (a > 0) & foot, sha(path)
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    with rasterio.open(ROOT / "data/sample_submission.tif") as ds:
        foot = np.isfinite(ds.read(1))
    disk = np.array([[(y*y + x*x) <= 9 for x in range(-3, 4)] for y in range(-3, 4)])
    out = {"schema": "site-pair-overlap/v1", "rule": "within_3px (candidate dots within 3px disk of site dots); phi (binary Pearson)", "rows": []}
    site_masks = {}
    for s, rel in SITES.items():
        m, h = dots(OWN / s / rel, foot)
        site_masks[s] = (m, h, rel)
    for cname, crel in CANDS.items():
        cm, ch = dots(ROOT / crel, foot)
        for s, (m, h, rel) in site_masks.items():
            dil = binary_dilation(m, structure=disk)
            within = float(dil[cm].mean()) if cm.any() else 0.0
            phi = float(np.corrcoef(cm[foot].astype(float), m[foot].astype(float))[0, 1])
            out["rows"].append({"candidate": cname, "candidate_file": crel, "candidate_sha256": ch,
                                "site": s, "site_file": rel, "site_sha256": h,
                                "candidate_dots": int(cm.sum()), "site_dots": int(m.sum()),
                                "within_3px_fraction": round(within, 6), "phi": round(phi, 6),
                                "duplicate_by_literal_rule": bool(abs(phi) > 0.90 or within > 0.70)})
        print(cname, "done", flush=True)
    (ROOT / "evidence/site_pair_overlap_20261031.json").write_text(json.dumps(out, indent=2) + "\n")
    print("wrote evidence/site_pair_overlap_20261031.json")
if __name__ == "__main__":
    main()
