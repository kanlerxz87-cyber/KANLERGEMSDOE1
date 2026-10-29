#!/usr/bin/env python3
"""Fetch the nine pinned focus-site GEMSDOE TIFs (24,25,27,28,30,31,32,33,36) into data/focus/.

Reuses `GitBlobFetcher` from `restore_data.py` (no private fork). Every file is verified against
the SHA-256 pinned in `registry/focus_sites.json`. Scores in that file are USER/OWNER-REPORTED,
not organizer receipts. Output: data/focus/GEMSDOE<NN>.tif (gitignored) and a receipt JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from restore_data import GitBlobFetcher, sha256_file  # noqa: E402

TARGET_SITES = {"GEMSDOE24", "GEMSDOE25", "GEMSDOE27", "GEMSDOE28", "GEMSDOE30",
                "GEMSDOE31", "GEMSDOE32", "GEMSDOE33", "GEMSDOE36"}


def main() -> int:
    manifest = json.loads((ROOT / "registry" / "focus_sites.json").read_text())
    fetcher = GitBlobFetcher(ROOT / ".cache" / "git_blob_cache")
    out_dir = ROOT / "data" / "focus"
    out_dir.mkdir(parents=True, exist_ok=True)
    receipts, failures = [], []
    for e in manifest["files"]:
        if e["site"] not in TARGET_SITES:
            continue
        dest = out_dir / f"{e['site']}.tif"
        try:
            fetcher.fetch(e["repo"], e["ref"], e["path"], dest)
            digest = sha256_file(dest)
            ok = digest == e["sha256"]
        except Exception as exc:  # explicit failure, never silent
            failures.append({"site": e["site"], "error": str(exc)})
            continue
        receipts.append({"site": e["site"], "reported_score": e["reported_score"],
                         "score_evidence": e["score_evidence"], "repo": e["repo"], "ref": e["ref"],
                         "path": e["path"], "reference_url": e["reference_url"],
                         "sha256": digest, "sha256_pinned": e["sha256"], "sha256_match": ok,
                         "bytes": dest.stat().st_size})
    receipt = {"receipts": receipts, "failures": failures, "n_ok": sum(r["sha256_match"] for r in receipts)}
    (ROOT / "data" / "focus_fetch_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"n_ok": receipt["n_ok"], "n_total": len(TARGET_SITES), "failures": failures}, indent=2))
    return 0 if receipt["n_ok"] == len(TARGET_SITES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
