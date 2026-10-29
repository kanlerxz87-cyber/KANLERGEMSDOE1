#!/usr/bin/env python3
"""Uniqueness audit of candidate submission rasters against ALL locally-restored reference rasters.

Reference set (all hash-pinned, read-only):
  * the nine focus GEMSDOE sites (`registry/focus_sites.json` -> `data/focus/`)
  * organizer-scored owner mirrors (`data/scored/`) and registry rasters (`data/registry_rasters/`)

Rules are the protocol's rules, applied by the shared `gems32.registry_audit.audit_final_dots`:
  |Spearman| <= 0.90 AND candidate dots within 3 px of any reference dot <= 70 %, literal
  (no space-filling exemption). A candidate that FAILS on any reference is a duplicate.

Writes evidence/uniqueness_audit_20261029.json. Does not modify any submission file.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems32.registry_audit import audit_final_dots  # noqa: E402

TEMPLATE = ROOT / "data" / "sample_submission.tif"

CANDIDATES = {
    "KANLER1-UWBP-DRCS-EXP3 (EXP-B3)": "docs/downloads/gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif",
    "KANLER1-COMB-PIEDMONT-WORM": "docs/downloads/gemsdoe32-kanler1-comb-piedmont-worm-disjoint-300m-celf-20261029T020638Z-9424d197-nan.tif",
    "KANLER1-OCDA-MSCS-EXP3": "docs/downloads/gemsdoe32-kanler1-ocda-mscs-exp3-37654d-20261027T1842Z-1db32b55-nan.tif",
    "KANLER1-UPFLOW-EXP2": "docs/downloads/gemsdoe32-kanler1-upflow-exp2-37654d-20261028T163730Z-76525b8c-nan.tif",
    "KANLER-CGJI-HTB-EXP2": "submissions/cgji_htb_20261027/gemsdoe32-cgji-htb-exp2-oof-hgb-b2-20261027T013000Z-5214b9ec-nan.tif",
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def build_manifest() -> dict:
    focus = json.loads((ROOT / "registry" / "focus_sites.json").read_text())["files"]
    rasters = []
    for e in focus:
        local = Path("data/focus") / Path(e["dest"]).name
        rasters.append({"repo": e["repo"], "path": e["path"], "sha256": e["sha256"], "local": local.as_posix(),
                        "group": "focus", "site": e["site"]})
    for d in ("data/scored", "data/registry_rasters"):
        for p in sorted((ROOT / d).glob("*.tif")):
            rasters.append({"repo": "local-owner-mirror", "path": p.name, "sha256": sha256_file(p),
                            "local": f"{d}/{p.name}", "group": d.split("/")[-1], "site": p.stem})
    return {"rasters": rasters, "n_failed": 0}


def main() -> int:
    with rasterio.open(TEMPLATE) as ds:
        foot = np.isfinite(ds.read(1))
        template_info = {"crs": str(ds.crs), "shape": list(ds.shape), "transform": list(ds.transform)[:6]}
    manifest = build_manifest()
    results = {}
    for name, rel in CANDIDATES.items():
        path = ROOT / rel
        with rasterio.open(path) as ds:
            arr = ds.read(1)
        dots = np.isfinite(arr) & (arr > 0)
        literal = audit_final_dots(
            candidate_surface=np.where(np.isfinite(arr), arr, 0.0).astype(np.float32),
            candidate_dots=dots, footprint=foot, manifest=manifest, root=ROOT, template_tif=TEMPLATE,
        )
        # Detector-only view: references whose 3-px dilation covers < 70 % of the footprint.
        # A reference covering >= 70 % (the r13 lattice covers ~99.9 %) cannot discriminate: a random
        # dot inside the footprint is already within 3 px of it, so it is reported, not used to decide.
        rows = [c for c in literal["comparisons"] if c.get("within_3px_fraction") is not None]
        sf = [c for c in rows if (c.get("footprint_coverage_3px") or 0.0) >= 0.70]
        non_sf = [c for c in rows if (c.get("footprint_coverage_3px") or 0.0) < 0.70]
        non_sf.sort(key=lambda c: -c["within_3px_fraction"])
        detector_dups = [c for c in non_sf if abs(c.get("spearman") or 0.0) > 0.90 or c["within_3px_fraction"] > 0.70]
        exempt = {"passed": not detector_dups, "worst_abs_spearman": max(abs(c.get("spearman") or 0.0) for c in rows),
                  "worst_spearman_raster": None}
        results[name] = {
            "file": rel,
            "sha256": sha256_file(path),
            "candidate_dots": literal["candidate_dots"],
            "references_compared": literal["registry_rasters"] - literal["malformed_or_missing"],
            "malformed_or_missing": literal["malformed_or_missing"],
            "literal_rule_passed": literal["passed"],
            "literal_failing_references": [c.get("local") for c in literal["duplicates"]],
            "detector_only_rule_passed": exempt["passed"],
            "non_discriminating_references_coverage_ge_70pct": [{"reference": c.get("local"), "footprint_coverage_3px": round(c["footprint_coverage_3px"], 6),
                                                    "within_3px": round(c["within_3px_fraction"], 6)} for c in sf],
            "worst_non_space_filling_within_3px": non_sf[0]["within_3px_fraction"] if non_sf else None,
            "worst_non_space_filling_reference": non_sf[0].get("local") if non_sf else None,
            "worst_abs_spearman": exempt["worst_abs_spearman"],
            "top3_non_space_filling": [{"reference": c.get("local"), "within_3px": round(c["within_3px_fraction"], 4),
                                        "spearman": c.get("spearman")} for c in non_sf[:3]],
        }
        r = results[name]
        print(f"{name:34s} refs={r['references_compared']:3d} literal={r['literal_rule_passed']} "
              f"detector-only={r['detector_only_rule_passed']} max3px(non-SF)={r['worst_non_space_filling_within_3px']:.4f} "
              f"({r['worst_non_space_filling_reference']}) max|rho|={r['worst_abs_spearman']:.4f}")
    out = {
        "schema": "uniqueness-audit/v1",
        "rule": "literal: |Spearman| <= 0.90 AND within-3px <= 0.70 vs every reference; detector-only: same rule over references with 3-px footprint coverage < 0.70",
        "template": {"path": "data/sample_submission.tif", "sha256": sha256_file(TEMPLATE), **template_info},
        "reference_count": len(manifest["rasters"]),
        "candidates": results,
    }
    (ROOT / "evidence" / "uniqueness_audit_20261029.json").write_text(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
