#!/usr/bin/env python3
"""Check mirror geometry and hashes, then run the unmodified shared preparation tool.

The upstream script creates a per-band cache, not the separately required 35-channel
feature_stack.npy. A matching owner mirror is NOT an authenticated organizer sample.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REV = "07806249f4ed3efe70b4fbf866183c32392b7853"
TEMPLATE = ROOT / ".cache" / "upstream" / f"GEMSDOE32-{REV}"
PINS = {
    "training_features.tif": "4371c82e3b8339b807bdffcf4ef59a225520fe2988d521be208ae33743123bc5",
    "labels.tif": "7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093",
    "sample_submission.tif": "2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_inputs(root: Path) -> None:
    import rasterio
    expected = None
    for name, digest in PINS.items():
        path = root / name
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f"missing or hash-mismatched mirror: {path}")
        with rasterio.open(path) as ds:
            grid = (ds.crs, ds.shape, ds.transform)
            if expected is None:
                expected = grid
                if ds.count != 19:
                    raise ValueError("unexpected number of feature bands")
            elif grid != expected or ds.count != 1:
                raise ValueError(f"grid or band count mismatch: {name}")
            if ds.crs is None or ds.crs.to_epsg() != 32611:
                raise ValueError(f"unexpected CRS in {name}")
    if expected is None or expected[1] != (3730, 3292):
        raise ValueError("unexpected reference shape")
    # Reference is an owner mirror, not an authenticated organizer sample.


def main() -> int:
    # Re-extract from the verified archive so local modifications are never imported.
    subprocess.run(["bash", str(ROOT / "scripts/bootstrap_template.sh")], check=True)
    data = ROOT / "data"
    check_inputs(data)
    env = os.environ.copy()
    env.update(GEMS_DATA_DIR=str(data), GEMS_WORK_DIR=str(data / "prepared"))
    subprocess.run([sys.executable, str(TEMPLATE / "scripts/prepare_data.py")], cwd=ROOT, env=env, check=True)
    print("Owner-mirror per-band preparation complete. The 35-channel shared cache remains a separate prerequisite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
