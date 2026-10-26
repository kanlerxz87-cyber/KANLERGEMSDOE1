#!/usr/bin/env python3
"""Restore pinned historical rasters as read-only comparison data (never submissions)."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "registry/focus_sites.json"
LATTICE = {
    "repo": "buffedlizard55-lab/GEMSDOE24",
    "ref": "07345ea0604953d7efb858d9cfbc21e20c7aca0b",
    "path": "inputs/calibration/13gems_20261001_r13-lattice-s5_v2_nan-outside.tif",
    "sha256": "b4570b406efec198eb2f4d142ad8d0d6184b14b66f2f52b5c4d697f0647dc9b2",
    "bytes": 1706456,
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(entry: dict, dest: Path) -> str:
    if not re.fullmatch(r"buffedlizard55-lab/GEMSDOE\d+", entry["repo"]):
        raise ValueError("unexpected reference repository")
    if not re.fullmatch(r"[0-9a-f]{40}", entry["ref"]):
        raise ValueError("reference must be an immutable full commit SHA")
    if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
        raise ValueError("invalid expected SHA-256")
    path = entry["path"]
    if path.startswith("/") or ".." in Path(path).parts or "?" in path or "#" in path:
        raise ValueError("unsafe reference path")
    expected_size = entry["bytes"]
    if type(expected_size) is not int or expected_size <= 0:
        raise ValueError("invalid expected byte size")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size == expected_size and digest(dest) == entry["sha256"]:
        return "verified existing"
    api = f"repos/{entry['repo']}/contents/{path}?ref={entry['ref']}"
    with tempfile.NamedTemporaryFile(dir=dest.parent, suffix=".partial", delete=False) as out:
        tmp = Path(out.name)
        try:
            subprocess.run(["gh", "api", api, "-H", "Accept: application/vnd.github.raw+json"], stdout=out, check=True)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        if tmp.stat().st_size != expected_size or digest(tmp) != entry["sha256"]:
            raise ValueError(f"download integrity mismatch: {dest}")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return "restored and verified"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    for item in manifest["sites"]:
        if not re.fullmatch(r"GEMSDOE\d+", item["id"]):
            raise ValueError("unsafe site id")
        dest = ROOT / "data/focus" / (item["id"] + ".tif")
        print(f"{item['id']}: {fetch(item, dest)}")
    print(f"r13 lattice: {fetch(LATTICE, ROOT / 'data/registry/13gems_r13_lattice.tif')}")
    current = json.loads((ROOT / 'registry/current_site_claims.json').read_text())
    for item in current['candidates']:
        if not re.fullmatch(r'GEMSDOE\d+-[A-Z0-9]+', item['id']):
            raise ValueError('unsafe candidate id')
        dest = ROOT / 'data/registry/current-reviews' / (item['id'] + '.tif')
        print(f"{item['id']}: {fetch(item, dest)}")
    print("Research comparisons only; no historic file is a new submission.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
