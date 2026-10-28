#!/usr/bin/env python3
"""Independently inspect the staged OCDA pair, without granting submission clearance.

The NaN member is used only as an internal footprint cross-check, NOT as an
organizer-authenticated template. Missing data or mismatch fails the check.
"""
from pathlib import Path
import hashlib
import json
import zipfile

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
STEM = 'gemsdoe32-kanler1-ocda-mscs-exp3-37654d-20261027T1842Z-1db32b55'
DOWNLOADS = ROOT / 'docs/downloads'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def check(directory=DOWNLOADS):
    audit = json.loads((directory / (STEM + '-audit.json')).read_text())
    zero = directory / (STEM + '-zeros.tif')
    nan = directory / (STEM + '-nan.tif')
    archive = directory / (STEM + '-nan.zip')
    for file, key in ((zero, 'zeros_tif'), (nan, 'nan_tif')):
        if sha(file) != audit[key]['sha256']:
            raise ValueError(f'Hash mismatch: {file.name}')
    with rasterio.open(zero) as z, rasterio.open(nan) as n:
        if z.count != 1 or n.count != 1 or (z.shape, z.crs, z.transform) != (n.shape, n.crs, n.transform):
            raise ValueError('Pair grid or band mismatch')
        if z.shape != (3730, 3292) or z.crs.to_epsg() != 32611 or tuple(z.transform)[:6] != (100, 0, 243350, 0, -100, 4508550):
            raise ValueError('Pair does not match recorded grid')
        a, b = z.read(1), n.read(1)
        if not np.isfinite(a).all() or not ((a >= 0) & (a <= 1)).all():
            raise ValueError('Zero-outside raster contains nonfinite or out-of-range values')
        foot = np.isfinite(b)
        if not np.isnan(b[~foot]).all() or not ((b[foot] >= 0) & (b[foot] <= 1)).all():
            raise ValueError('NaN-outside raster has invalid values')
        if not np.array_equal(a[foot], b[foot]) or np.any(a[~foot] != 0):
            raise ValueError('Pair content mismatch')
        count = int(np.count_nonzero(a))
        if count != audit['zeros_tif']['emitted_positive_pixels'] or count != audit['nan_tif']['emitted_positive_pixels']:
            raise ValueError('Emitted count does not match audit')
        if int(foot.sum()) != audit['nan_tif']['in_footprint_finite_pixels']:
            raise ValueError('Footprint count does not match audit')
    with zipfile.ZipFile(archive) as zf:
        if zf.namelist() != [nan.name]:
            raise ValueError('Archive must contain exactly the NaN TIFF')
        if hashlib.sha256(zf.read(nan.name)).hexdigest() != sha(nan):
            raise ValueError('Archive member mismatch')
    return {'status': 'research-only; NOT cleared for submission',
            'zero_sha256': sha(zero), 'nan_sha256': sha(nan),
            'emitted_positive_pixels': count, 'template_authenticated': False,
            'uniqueness_and_holdout_replayed': False}


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
