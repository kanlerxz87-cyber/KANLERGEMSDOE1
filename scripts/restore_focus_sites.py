#!/usr/bin/env python3
"""Restore the nine focus-site TIFFs pinned in `registry/focus_sites.json` into `data/focus/`.

Reuses `restore_data.GitBlobFetcher` (shared code, no private fork). Each file is fetched from the
pinned 40-hex commit on github.com and must match its pinned SHA-256 and byte size, otherwise the
restore fails closed. Pins prove owner-mirror consistency only, not organizer authentication.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from restore_data import GitBlobFetcher  # noqa: E402


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    manifest = json.loads((ROOT / "registry" / "focus_sites.json").read_text())
    out_dir = ROOT / "data" / "focus"
    out_dir.mkdir(parents=True, exist_ok=True)
    fetcher = GitBlobFetcher(ROOT / ".cache" / "git_blob_cache")
    receipt = []
    for entry in manifest["files"]:
        dest = out_dir / Path(entry["dest"]).name
        tmp = dest.with_name(dest.name + ".assembling")
        if not (dest.is_file() and sha256_file(dest) == entry["sha256"]):
            fetcher.fetch(entry["repo"], entry["ref"], entry["path"], tmp)
            got = sha256_file(tmp)
            if got != entry["sha256"] or tmp.stat().st_size != entry["bytes"]:
                tmp.unlink(missing_ok=True)
                raise SystemExit(f"FAIL-CLOSED {entry['site']}: sha256 {got} != pinned {entry['sha256']}")
            tmp.replace(dest)
        receipt.append({"site": entry["site"], "dest": dest.relative_to(ROOT).as_posix(),
                        "sha256": entry["sha256"], "bytes": entry["bytes"],
                        "reported_score": entry["reported_score"],
                        "score_evidence": entry["score_evidence"], "status": "verified"})
        print(f"verified {entry['site']:10s} {dest.name}")
    (ROOT / "data" / "restore_receipt_focus.json").write_text(json.dumps(
        {"schema_version": 1, "files": receipt,
         "provenance_warning": "Owner-hosted mirrors; hashes do not authenticate the organizer's files."},
        indent=2) + "\n")
    print(f"Verified {len(receipt)} focus-site files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
