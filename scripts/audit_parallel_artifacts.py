#!/usr/bin/env python3
"""Read-only saved-byte and lattice check of three already-existing parallel artifacts.

This does not generate a candidate, authenticate the sample, reproduce a holdout,
validate the full registry or authorize an upload. The footprint is provisional.
"""
from __future__ import annotations
import json
from pathlib import Path, PurePosixPath
import sys

import numpy as np
import rasterio
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from audit_focus import SAMPLE_SHA, load_binary  # noqa: E402
from fetch_focus_rasters import LATTICE, digest  # noqa: E402


def audit(root: Path, manifest: dict) -> dict:
    sample = root/'data/sample_submission.tif'
    if not sample.is_file() or digest(sample) != SAMPLE_SHA:
        raise ValueError('missing or mismatched owner-mirrored sample')
    with rasterio.open(sample) as ds:
        if ds.count != 1 or ds.crs is None or ds.crs.to_epsg() != 32611:
            raise ValueError('unexpected owner-mirrored sample')
        grid = (ds.crs, ds.shape, ds.transform)
        foot = np.isfinite(ds.read(1))
    if not foot.any():
        raise ValueError('empty owner-mirrored footprint')
    lattice, _ = load_binary(root/'data/registry/13gems_r13_lattice.tif', grid, foot, LATTICE['sha256'])
    if not lattice.any():
        raise ValueError('empty lattice')
    near = distance_transform_edt(~lattice) <= 3
    items = manifest['candidates']
    if len(items) != 3 or len({item['id'] for item in items}) != 3:
        raise ValueError('expected three distinct parallel artifacts')
    output = {}
    for item in items:
        relative = PurePosixPath(item['path'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[:2] != ('docs', 'downloads') or relative.suffix != '.tif':
            raise ValueError('unsafe parallel artifact path')
        path = root.joinpath(*relative.parts)
        dots, info = load_binary(path, grid, foot, item['sha256'])
        if not dots.any():
            raise ValueError(f"empty raster: {item['id']}")
        with rasterio.open(path) as ds:
            values = ds.read(1)
            info['saved_bytes_single_band_float32'] = bool(ds.count == 1 and ds.dtypes[0] == 'float32')
            info['saved_bytes_grid_matches_owner_mirror'] = bool((ds.crs, ds.shape, ds.transform) == grid)
            info['saved_bytes_inside_min'] = float(values[foot].min())
            info['saved_bytes_inside_max'] = float(values[foot].max())
            info['outside_footprint'] = 'all zero' if np.all(values[~foot] == 0) else 'other; not evaluated here'
            info['nodata_value'] = None if ds.nodata is None else str(ds.nodata)
        close_count = int((dots & near).sum())
        info['lattice_near_dots'] = close_count
        info['lattice_overlap_fraction'] = close_count / int(dots.sum())
        info['literal_lattice_gate_pass'] = bool(10 * close_count <= 7 * int(dots.sum()))
        info['organizer_acceptance'] = None
        output[item['id']] = info
    return {
        'schema_version': 1,
        'scope': 'Three existing parallel research artifacts; owner-mirrored sample is not authenticated. No new experiment or candidate was created by this audit.',
        'sample_sha256': SAMPLE_SHA,
        'lattice_sha256': LATTICE['sha256'],
        'registry_scope': 'only the registered lattice was replayed; full-registry and pre-placement checks were not reproduced',
        'holdout_status': 'Prior reports are preserved but not accepted as compliant: the placement collar used the complete catalogue before holdout; canaries were random catalogue samples, not blocked holdout tests.',
        'artifacts': output,
        'verdict': 'negative',
        'ok_to_submit': False,
    }


def main() -> int:
    manifest = json.loads((ROOT/'registry/parallel_artifacts.json').read_text())
    report = audit(ROOT, manifest)
    out = ROOT/'evidence/parallel-artifact-audit-20261026.json'
    out.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    for name, row in report['artifacts'].items():
        print(f"{name}: {row['positive_pixels']} dots; lattice overlap {row['lattice_overlap_fraction']:.4%}; literal gate pass={row['literal_lattice_gate_pass']}")
    print('Research only; no upload approved, no new experiment or file generated.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(f'Parallel artifact audit failed closed: {exc}', file=sys.stderr)
        raise SystemExit(1)
