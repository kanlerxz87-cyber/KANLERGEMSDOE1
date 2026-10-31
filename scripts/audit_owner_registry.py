#!/usr/bin/env python3
"""Uniqueness audit of a candidate against every GeoTIFF in the GEMSDOE owner repositories.

Shared rule (not a fork): gems32.registry_audit.audit_final_dots, i.e. a candidate is a
DUPLICATE if |Spearman| > 0.90 with any registry raster OR more than 70% of its dots fall
within 3 px of one registry raster's dots (PARALLEL-RUN PROTOCOL rule 1).

Inputs:
  --owner-dir DIR   directory containing one clone per owner repo (e.g. /tmp/owners/GEMSDOE32)
                    cloned with: git clone --depth 1 https://github.com/buffedlizard55-lab/<REPO>.git
  --candidate PATH  candidate GeoTIFF (NaN-outside, single band) to audit
Every registry raster is listed with its repo, path, git blob SHA and per-raster overlap.
Zip archives are extracted to --extract-dir (outside the repository) and audited as members.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gems32 import registry_audit  # noqa: E402
from gems32.paths import data_dir  # noqa: E402


def collect(owner_dir: Path, extract_dir: Path) -> list[dict]:
    entries = []
    for repo_dir in sorted(p for p in owner_dir.iterdir() if p.is_dir()):
        rel_root = repo_dir
        for f in sorted(repo_dir.rglob("*")):
            if not f.is_file() or ".git" in f.relative_to(repo_dir).parts:
                continue
            if f.suffix.lower() in (".tif", ".tiff"):
                entries.append(_entry(repo_dir, f))
            elif f.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(f) as zf:
                        tifs = [m for m in zf.namelist() if m.lower().endswith((".tif", ".tiff")) and not m.endswith("/")]
                        for m in tifs:
                            out = extract_dir / repo_dir.name / f"{f.stem}__{Path(m).name}"
                            out.parent.mkdir(parents=True, exist_ok=True)
                            if not out.exists():
                                out.write_bytes(zf.read(m))
                            entries.append(_entry(repo_dir, f, local=out, member=m))
                except zipfile.BadZipFile:
                    continue
    return entries


def _entry(repo_dir: Path, f: Path, local: Path | None = None, member: str | None = None) -> dict:
    local = local or f
    rel = str(f.relative_to(repo_dir)) + (f" :: {member}" if member else "")
    blob = subprocess.run(["git", "-C", str(repo_dir), "hash-object", str(f)], capture_output=True, text=True).stdout.strip() \
        if member is None else None
    return {"repo": repo_dir.name, "path": rel, "local": str(local), "sha256": hashlib.sha256(local.read_bytes()).hexdigest(),
            "git_blob": blob}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--owner-dir", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--extract-dir", type=Path, default=Path("/tmp/owner_registry_extract"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--exclude-prefix", action="append", default=None,
                    help="repo-relative path prefix that holds INPUT layers, not submissions (default: data/)")
    ap.add_argument("--space-filling-coverage", type=float, default=None,
                    help="IR-47-LATTICE-FIX: null-calibrated excess rule for rasters whose 3-px coverage >= this")
    args = ap.parse_args()
    excludes = args.exclude_prefix if args.exclude_prefix is not None else ["data/"]

    ddir = data_dir()
    with rasterio.open(ddir / "sample_submission.tif") as tpl:
        template = {"shape": tpl.shape, "crs": tpl.crs, "transform": tpl.transform}
        foot = np.isfinite(tpl.read(1))
    with rasterio.open(args.candidate) as ds:
        cand = ds.read(1)
    dots = (cand > 0) & foot
    surface = np.where(foot, np.nan_to_num(cand, nan=0.0), 0.0).astype(np.float32)

    entries_all = collect(args.owner_dir, args.extract_dir)
    entries = [e for e in entries_all if not any(e["path"].startswith(x) for x in excludes)]
    manifest = {"rasters": [{"repo": e["repo"], "path": e["path"], "local": e["local"], "sha256": e["sha256"]} for e in entries]}
    res = registry_audit.audit_final_dots(surface, dots, foot, manifest, root=Path("/"),
                                          template_tif=ddir / "sample_submission.tif",
                                          space_filling_coverage=args.space_filling_coverage)
    # attach git blob ids for manual review
    blob = {(e["repo"], e["path"]): e["git_blob"] for e in entries}
    for row in res["comparisons"]:
        row["git_blob"] = blob.get((row.get("repo"), row.get("path")))
    summary = {k: res[k] for k in res if k != "comparisons"}
    summary.update({
        "schema": "owner-registry-uniqueness/v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": str(args.candidate.name),
        "candidate_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
        "owner_repos": sorted({e["repo"] for e in entries}),
        "registry_raster_count": len(entries),
        "registry_raster_count_before_input_exclusion": len(entries_all),
        "excluded_path_prefixes": excludes,
        "space_filling_coverage_rule": args.space_filling_coverage,
        "comparisons_top20_by_overlap": sorted(res["comparisons"], key=lambda r: -(r.get("within_3px_fraction") or 0))[:20],
    })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(json.dumps({k: summary[k] for k in ("passed", "literal_rule_passed", "registry_rasters", "malformed_or_missing",
                                             "worst_abs_spearman", "worst_within_3px_fraction", "candidate_dots")}, indent=2, default=str))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
