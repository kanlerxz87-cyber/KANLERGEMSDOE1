#!/usr/bin/env python3
"""Restore immutable, SHA-256-pinned owner mirrors through Git's partial clone.

This avoids rate-limited GitHub REST content endpoints and raw.githubusercontent.com.
The files are *owner mirrors*, not verified copies from the competition organizer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gems32.paths import data_dir  # noqa: E402

REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
REF_RE = re.compile(r"^[0-9a-f]{40}$")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_relative(value: str) -> Path:
    p = Path(value)
    if not value or p.is_absolute() or ".." in p.parts or value.startswith("-"):
        raise ValueError(f"Unsafe manifest path: {value!r}")
    return p


class GitBlobFetcher:
    """One isolated, lazy Git object cache per public source repository."""
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.prepared: set[tuple[str, str]] = set()

    def fetch(self, repo: str, ref: str, path: str, destination: Path) -> None:
        if not REPO_RE.fullmatch(repo) or not REF_RE.fullmatch(ref):
            raise ValueError("Git source must have a safe repo name and a full immutable 40-hex commit")
        safe_relative(path)
        cache = self.cache_dir / repo.replace("/", "__")
        if not (cache / "HEAD").exists():
            if cache.exists():
                raise RuntimeError(f"Incomplete Git cache at {cache}; remove this cache before retrying")
            subprocess.run(["git", "clone", "--quiet", "--bare", "--filter=blob:none",
                            "--no-tags", "--depth=1", f"https://github.com/{repo}.git", str(cache)],
                           check=True, timeout=300)
        key = (repo, ref)
        if key not in self.prepared:
            exists = subprocess.run(["git", "--git-dir", str(cache), "cat-file", "-e", ref + "^{commit}"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
            if not exists:
                subprocess.run(["git", "--git-dir", str(cache), "fetch", "--quiet", "--depth=1", "origin", ref],
                               check=True, timeout=300)
            self.prepared.add(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as out:
            subprocess.run(["git", "--git-dir", str(cache), "show", f"{ref}:{path}"],
                           stdout=out, check=True, timeout=300)


def restore_entry(entry: dict, root: Path, fetcher: GitBlobFetcher) -> dict:
    dest = root / safe_relative(entry["dest"])
    if not dest.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Destination escapes restore root: {entry['dest']}")
    expected = entry["sha256"]
    if not SHA_RE.fullmatch(expected):
        raise ValueError(f"Invalid SHA-256 for {entry['id']}")
    if dest.is_file() and sha256_file(dest) == expected:
        if "bytes" in entry and dest.stat().st_size != entry["bytes"]:
            raise ValueError(f"SIZE MISMATCH for {entry['id']}")
        status = "present"
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".assembling")
        tmp.unlink(missing_ok=True)
        try:
            if "parts" in entry:
                with tmp.open("wb") as output:
                    for index, part in enumerate(entry["parts"]):
                        part_file = tmp.with_name(f"{tmp.name}.part-{index}")
                        try:
                            fetcher.fetch(entry["repo"], entry["ref"], part, part_file)
                            with part_file.open("rb") as src:
                                shutil.copyfileobj(src, output, 1024 * 1024)
                        finally:
                            part_file.unlink(missing_ok=True)
            else:
                fetcher.fetch(entry["repo"], entry["ref"], entry["path"], tmp)
            actual = sha256_file(tmp)
            if actual != expected:
                raise ValueError(f"HASH MISMATCH for {entry['id']}: {actual} != {expected}")
            if "bytes" in entry and tmp.stat().st_size != entry["bytes"]:
                raise ValueError(f"SIZE MISMATCH for {entry['id']}")
            os.replace(tmp, dest)
            status = "restored"
        finally:
            tmp.unlink(missing_ok=True)
    return {"id": entry["id"], "dest": entry["dest"], "group": entry["group"],
            "status": status, "bytes": dest.stat().st_size, "sha256": expected,
            "provenance": "hash-pinned owner mirror; not organizer-authenticated"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group", default="all", choices=["core", "external", "scored", "all"])
    ap.add_argument("--manifest", default=str(ROOT / "registry" / "data_manifest.json"))
    ap.add_argument("--target-dir", default=None)
    args = ap.parse_args()
    man = json.loads(Path(args.manifest).read_text())
    root = (Path(args.target_dir) if args.target_dir else data_dir()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    fetcher = GitBlobFetcher(ROOT / ".cache" / "git_blob_cache")
    results = []
    for entry in man["files"]:
        if args.group in ("all", entry["group"]):
            result = restore_entry(entry, root, fetcher)
            results.append(result)
            print(f"{result['status']:>8}  {entry['dest']:82s}  sha256={result['sha256'][:12]}…", flush=True)
    try:
        storage_root = root.relative_to(ROOT).as_posix()
    except ValueError:
        storage_root = str(root)
    receipt = {"schema_version": 2, "generated_utc": datetime.now(timezone.utc).isoformat(),
               "group": args.group, "verified_files_count": len(results), "storage_root": storage_root,
               "provenance_warning": "Owner-hosted mirrors; hashes do not authenticate the organizer's files.",
               "files": results}
    receipt_path = ROOT / "data" / ("restore_receipt.json" if args.group == "all" else f"restore_receipt_{args.group}.json")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Verified {len(results)} files; receipt written to {receipt_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
