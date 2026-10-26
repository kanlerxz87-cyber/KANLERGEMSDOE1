#!/usr/bin/env python3
"""Restore and SHA-256 verify all competition, external, and historical scored files in registry/data_manifest.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gems32.paths import data_dir  # noqa: E402


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(repo: str, ref: str, path: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        if shutil.which("gh"):
            with tmp.open("wb") as out:
                subprocess.run(
                    [
                        "gh",
                        "api",
                        f"repos/{repo}/contents/{path}?ref={ref}",
                        "-H",
                        "Accept: application/vnd.github.raw",
                    ],
                    stdout=out,
                    check=True,
                )
        else:
            import requests

            url = f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                with tmp.open("wb") as out:
                    for chunk in r.iter_content(1 << 20):
                        out.write(chunk)
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)


def restore_entry(entry: dict, root: Path) -> dict:
    dest = root / entry["dest"]
    if dest.exists() and sha256_file(dest) == entry["sha256"]:
        return {
            "id": entry["id"],
            "dest": entry["dest"],
            "group": entry["group"],
            "status": "present",
            "bytes": dest.stat().st_size,
            "sha256": entry["sha256"],
        }
    if "parts" in entry:
        tmp = dest.with_suffix(".assembling")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("wb") as out:
            for part in entry["parts"]:
                p = root / "raw_parts" / Path(part).name
                fetch(entry["repo"], entry["ref"], part, p)
                with p.open("rb") as src:
                    shutil.copyfileobj(src, out, 1 << 20)
                p.unlink()
        got = sha256_file(tmp)
        if got != entry["sha256"]:
            tmp.unlink(missing_ok=True)
            raise SystemExit(f"HASH MISMATCH for {entry['id']}: {got} != {entry['sha256']}")
        tmp.replace(dest)
    else:
        fetch(entry["repo"], entry["ref"], entry["path"], dest)
        got = sha256_file(dest)
        if got != entry["sha256"]:
            dest.unlink(missing_ok=True)
            raise SystemExit(f"HASH MISMATCH for {entry['id']}: {got} != {entry['sha256']}")
    return {
        "id": entry["id"],
        "dest": entry["dest"],
        "group": entry["group"],
        "status": "restored",
        "bytes": dest.stat().st_size,
        "sha256": entry["sha256"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group", default="all", choices=["core", "external", "scored", "all"])
    ap.add_argument("--manifest", default=str(ROOT / "registry" / "data_manifest.json"))
    ap.add_argument("--target-dir", default=None, help="Override destination directory")
    args = ap.parse_args()

    man = json.loads(Path(args.manifest).read_text())
    root = Path(args.target_dir) if args.target_dir else data_dir()
    root.mkdir(parents=True, exist_ok=True)

    results = []
    for e in man["files"]:
        if args.group in ("all", e["group"]):
            r = restore_entry(e, root)
            results.append(r)
            print(f"{r['status']:>8}  {e['dest']:82s}  sha256={r['sha256'][:12]}…")

    try:
        storage_root = root.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        storage_root = str(root)
    receipt = {
        "schema_version": 1,
        "verified_files_count": len(results),
        "storage_root": storage_root,
        "files": results,
    }
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "restore_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Verified {len(results)} files; receipt written to data/restore_receipt.json")


if __name__ == "__main__":
    main()
