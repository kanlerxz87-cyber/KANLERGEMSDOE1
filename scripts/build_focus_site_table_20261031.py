#!/usr/bin/env python3
"""Build the auditable per-site table for the nine focus GEMSDOE sites (2026-10-31).

For each focus site (restored + SHA-pinned into data/focus/ by restore_focus_sites.py) this records:
  - the user-reported organizer score for that site's best listed submission (USER-REPORTED label),
  - the restored file's SHA-256 and emitted-dot count,
  - 3-px dot overlap of the site file with the repo's recommended unique candidate (UWBP-DRCS-EXP3)
    and with the GEMSDOE32 champion, using the same definition as the shared uniqueness audit
    (fraction of candidate dots within 3 px of any reference dot).

Writes docs/evidence/focus_site_table_20261031.json. Reads only; no submission files are changed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Best listed submission per focus site, transcribed from the user's list (USER-REPORTED).
SITE_BEST = {
    "GEMSDOE24": ("h25-1-dotted-h19-5-d1-5-20261002-989f59505db1-nan", 0.2477),
    "GEMSDOE25": ("dotted-h19-5-d2-8-20261002-e56ea318af89-nan", 0.2600),
    "GEMSDOE27": ("topo-gap-closure-t-v2-on-d1-5-20261002-5512495c6bd1-nan", 0.2449),
    "GEMSDOE28": ("h36-1-rung30-blind-r1-20261003-b531dae0a36f-nan", 0.2710),
    "GEMSDOE30": ("d28-poisson300m-offcat-44090-20261003T233156Z-91eae1ca", 0.2600),
    "GEMSDOE31": ("h27-4-solo-d28-20261004-8acb75e1-nan", 0.2708),
    "GEMSDOE32": ("h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros", 0.2778),
    "GEMSDOE33": ("h33d-analog-tip-stepover-r30-20261004-cb490425926e", 0.2632),
    "GEMSDOE36": ("anderson-geothermal-pinn-38854-20261004T230000Z-9b9ea4e6-zeros", 0.2750),
}
CANDIDATE = ROOT / "docs/downloads/gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif"
CHAMPION = ROOT / "docs/downloads/gemsdoe32-h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros.tif"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def dots(path: Path) -> np.ndarray:
    with rasterio.open(path) as ds:
        a = ds.read(1)
    return np.isfinite(a) & (a > 0)


def within3(cand: np.ndarray, ref: np.ndarray) -> float:
    if cand.sum() == 0 or ref.sum() == 0:
        return 0.0
    d = distance_transform_edt(~ref)
    return float((d[cand] <= 3.0).mean())


def main() -> int:
    focus_manifest = json.loads((ROOT / "registry" / "focus_sites.json").read_text())["files"]
    by_site = {e["site"]: e for e in focus_manifest}
    cand = dots(CANDIDATE)
    champ = dots(CHAMPION)
    rows = []
    for site, (name, score) in SITE_BEST.items():
        entry = by_site[site]
        local = ROOT / "data" / "focus" / Path(entry["dest"]).name
        if not local.exists():
            raise SystemExit(f"missing restored focus file {local}; run scripts/restore_focus_sites.py")
        sha = sha256_file(local)
        if sha != entry["sha256"]:
            raise SystemExit(f"SHA mismatch for {site}: {sha} != pinned {entry['sha256']}")
        ref = dots(local)
        rows.append({
            "site": site,
            "best_listed_submission": name,
            "organizer_score_user_reported": score,
            "score_label": "USER-REPORTED (copied from the user's site list; not a submission receipt)",
            "restored_file": local.relative_to(ROOT).as_posix(),
            "sha256_pinned_and_verified": sha,
            "dots_in_file": int(ref.sum()),
            "within3px_candidate_dots_vs_site": round(within3(cand, ref), 4),
            "within3px_site_dots_vs_candidate": round(within3(ref, cand), 4),
            "within3px_site_dots_vs_champion": round(within3(ref, champ), 4),
            "duplicate_under_literal_70pct_rule": within3(cand, ref) > 0.70,
        })
    out = {
        "schema": "focus-site-table/v1",
        "generated_utc": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        "candidate": CANDIDATE.relative_to(ROOT).as_posix(),
        "candidate_sha256": sha256_file(CANDIDATE),
        "candidate_dots": int(cand.sum()),
        "champion": CHAMPION.relative_to(ROOT).as_posix(),
        "champion_dots": int(champ.sum()),
        "rule": "candidate dots within 3 px of any site dot > 70% => duplicate (protocol rule 1)",
        "rows": rows,
    }
    path = ROOT / "docs" / "evidence" / "focus_site_table_20261031.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    for r in rows:
        print(f"{r['site']} score={r['organizer_score_user_reported']:.4f} dots={r['dots_in_file']:6,d} "
              f"cand_within3={r['within3px_candidate_dots_vs_site']:.4f} dup={r['duplicate_under_literal_70pct_rule']}")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
