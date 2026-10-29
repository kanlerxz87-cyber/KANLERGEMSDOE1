#!/usr/bin/env python3
"""Crawl every GEMSDOE site repo named in the competition prompt for submission-grid TIFFs.

Owner/repo pairs come from the github.io URLs in the prompt (https://<owner>.github.io/<repo>/).
For each repo: default branch HEAD -> recursive tree -> every *.tif -> blob bytes via `gh api`
(authenticated GitHub REST, read-only). A TIF is kept only if it is single-band, EPSG:32611,
3730 x 3292 (the competition grid). Binaries go to data/sites/ (gitignored); the index with
sha256 and provenance goes to docs/evidence/gemsdoe_site_tif_index.json.
Scores are NOT read from this crawl (they are user-reported in the prompt).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import rasterio
from rasterio.io import MemoryFile

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "sites"

SITES = {
    "buffedlizard55-lab": [
        "GEMSDOE", "6GEMSDOE", "GEMSDOE3", "GEMSDOE2", "GEMSDOE4", "5GEMSDOE", "7GEMSDOE", "8GEMSDOE",
        "GEMSDOE9", "11GEMSDOE", "12GEMSDOE", "15GEMSDOE", "14GEMSDOE", "17GEMSDOE", "18GEMSDOE",
        "19GEMSDOE", "GEMSDOE10", "13GEMSDOE", "16GEMSDOE", "GEMSDOE21", "20GEMSDOE", "GEMSDOE22",
        "GEMSDOE23", "GEMSDOE24", "GEMSDOE25", "GEMSDOE26", "GEMSDOE27", "GEMSDOE28", "GEMSDOE29",
        "GEMSDOE30", "GEMSDOE31", "GEMSDOE32", "GEMSDOE33", "GEMSDOE34", "GEMSDOE35", "GEMSDOE36",
        "GEMSDOE37", "GEMSDOE38", "GEMSDOE39", "GEMSDOE40", "GEMSDOE41", "GEMSDOE42", "GEMSDOE43",
        "GEMSDOE44", "GEMSDOE45", "GEMSDOE46", "GEMSDOE47", "GEMSDOE48", "GEMSDOE49", "GEMSDOE50",
        "GEMSDOE51", "GEMSDOE52", "GEMSDOE53", "GEMSDOE54", "55GEMSDOE", "56GEMSDOE", "57GEMSDOE",
        "58GEMSDOE", "59GEMSDOE", "60GEMSDOE", "61GEMSDOE", "62GEMSDOE", "GEMSDOE63", "GEMSDOE64",
        "GEMSDOE65", "GEMSDOE66", "GEMSDOE67", "GEMSDOE68", "GEMSDOE69", "GEMSDOE70", "GEMSDOE71",
        "GEMSDOE72", "GEMSDOE73", "GEMSDOE74", "GEMSDOE75", "GEMSDOE76", "GEMSDOE77", "GEMSDOE78",
        "GEMSDOE79", "GEMSDOE80", "GEMSDOE81", "GEMSDOE82", "GEMSDOE83", "GEMSDOE84", "GEMSDOE85",
        "GEMSDOE86", "GEMSDOE87", "GEMSDOE88", "GEMSDOE89", "GEMSDOE90", "GEMSDOE91", "GEMSDOE92",
    ],
    "kanlerxz87-cyber": ["KANLERGEMSDOE1", "KANLERGEMSDOE2", "KANLERGEMSDOE3"],
    "eugboogieman123-ops": ["EUGGEMSDOE1", "EUGGEMSDOE2", "EUGGEMSDOE3"],
    "wingbangboozle1-lang": ["WBGGEMSDOE1", "WBGGEMSDOE2", "WBGGEMSDOE3"],
    "ginnymcfiner23-ux": ["GINNYGEMSDOE1", "GINNYGEMSDOE2", "GINNYGEMSDOE3"],
    "karagemop466-tech": ["GEMSDOEkarage1", "GEMSDOEkarage2", "GEMSDOEkarage3"],
    "apartanish22-droid": ["ApartGEMSDOE1", "ApartGEMSDOE2", "ApartGEMSDOE3"],
    "sassnarep3-star": ["GEMSDOESASS1", "GEMSDOESASS2", "GEMSDOESASS3"],
}


def gh_json(args: list[str]):
    r = subprocess.run(["gh", "api", *args], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return json.loads(r.stdout)


CACHE = ROOT / ".cache" / "site_git_cache"


def git_head_tifs(owner: str, repo: str) -> tuple[str, str, list[dict]]:
    """Partial bare clone (trees only, lazy blobs) -> default-branch HEAD and its .tif blobs."""
    CACHE.mkdir(parents=True, exist_ok=True)
    gd = CACHE / f"{owner}__{repo}.git"
    if not (gd / "HEAD").exists():
        r = subprocess.run(["git", "clone", "--quiet", "--bare", "--filter=blob:none", "--no-tags", "--depth=1",
                            f"https://github.com/{owner}/{repo}.git", str(gd)],
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[-300:])
    head_ref = subprocess.run(["git", "--git-dir", str(gd), "symbolic-ref", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    branch = head_ref.split("/")[-1]
    head = subprocess.run(["git", "--git-dir", str(gd), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    lt = subprocess.run(["git", "--git-dir", str(gd), "ls-tree", "-r", head],
                        capture_output=True, text=True, check=True).stdout.splitlines()
    tifs = []
    for line in lt:
        meta, path = line.split("\t", 1)
        mode, typ, sha = meta.split()  # no -l: sizes would force fetching every blob
        if typ == "blob" and path.lower().endswith((".tif", ".tiff", ".zip")):
            tifs.append({"path": path, "sha": sha, "size": None})
    return branch, head, tifs


def git_blob(owner: str, repo: str, sha: str) -> bytes:
    gd = CACHE / f"{owner}__{repo}.git"
    r = subprocess.run(["git", "--git-dir", str(gd), "cat-file", "blob", sha],
                       capture_output=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode()[-300:])
    return r.stdout


def is_competition_grid(data: bytes) -> tuple[bool, dict]:
    try:
        with MemoryFile(data) as mf, mf.open() as ds:
            info = {"count": ds.count, "crs": str(ds.crs), "shape": [ds.height, ds.width]}
            ok = ds.count == 1 and ds.crs is not None and ds.crs.to_epsg() == 32611 and (ds.height, ds.width) == (3730, 3292)
            return ok, info
    except Exception as exc:  # not a readable raster
        return False, {"error": str(exc)[:120]}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index, errors = [], []
    for owner, repos in SITES.items():
        for repo in repos:
            try:
                branch, head, tifs = git_head_tifs(owner, repo)
            except Exception as exc:
                errors.append({"repo": f"{owner}/{repo}", "stage": "tree", "error": str(exc)})
                continue
            for t in tifs:
                path = t["path"]
                if path.lower().endswith(".zip"):
                    index.append({"repo": f"{owner}/{repo}", "path": path, "kind": "zip-skipped-in-crawl"})
                    continue
                try:
                    data = git_blob(owner, repo, t["sha"])
                except Exception as exc:
                    errors.append({"repo": f"{owner}/{repo}", "path": path, "stage": "blob", "error": str(exc)})
                    continue
                ok, info = is_competition_grid(data)
                rec = {"repo": f"{owner}/{repo}", "head": head, "path": path, "blob_sha": t["sha"], "source": "git partial clone (github.com)",
                       "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                       "competition_grid": ok, **info}
                if ok:
                    # Content-addressed: one file per distinct SHA-256 (basename collisions overwrote data before).
                    BY_SHA = OUT_DIR / "by_sha"
                    BY_SHA.mkdir(parents=True, exist_ok=True)
                    dest = BY_SHA / f"{rec['sha256']}.tif"
                    if not dest.exists():
                        dest.write_bytes(data)
                    rec["local_file"] = f"data/sites/by_sha/{rec['sha256']}.tif"
                index.append(rec)
            print(f"{owner}/{repo}: branch={branch} tif_files={len(tifs)}", flush=True)
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_repos_attempted": sum(len(v) for v in SITES.values()),
           "n_grid_tifs": sum(1 for r in index if r.get("competition_grid")), "index": index, "errors": errors}
    (ROOT / "docs" / "evidence" / "gemsdoe_site_tif_index.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({"grid_tifs": out["n_grid_tifs"], "errors": len(errors)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
