"""Path resolution for GEMSDOE32."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """Resolve the directory holding competition inputs (checks GEMS_DATA_DIR, .cache/gems_data/, and data/)."""
    env = os.environ.get("GEMS_DATA_DIR")
    if env:
        return Path(env).expanduser()
    cache = ROOT / ".cache" / "gems_data"
    for cand in (cache, ROOT / "data", ROOT / "data" / "raw"):
        for stem in ("core", ""):
            if (cand / stem / "training_features.tif").exists():
                return (cand / stem) if stem else cand
    return cache


def work_dir() -> Path:
    """Scratch directory for regenerable numpy caches."""
    env = os.environ.get("GEMS_WORK_DIR")
    if env:
        return Path(env).expanduser()
    return ROOT / ".cache" / "gems_work"


def docs_dir() -> Path:
    """Directory holding GitHub Pages site, figures, and downloadable submissions."""
    d = ROOT / "docs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def downloads_dir() -> Path:
    """Directory holding downloadable submission GeoTIFFs and verification sidecars."""
    d = ROOT / "docs" / "downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def evidence_dir() -> Path:
    """Directory holding machine-readable experimental and surrogate receipts."""
    d = ROOT / "evidence"
    d.mkdir(parents=True, exist_ok=True)
    return d


def registry_dir() -> Path:
    """Directory holding the auditable registries (sources, manifests, slot plan, irregularities)."""
    d = ROOT / "registry"
    d.mkdir(parents=True, exist_ok=True)
    return d
