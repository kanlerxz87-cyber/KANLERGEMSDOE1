#!/usr/bin/env python3
"""Fresh byte/range/grid audit; never promotes or estimates a leaderboard score."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]


def main():
    reference = ROOT / 'docs/downloads/gemsdoe32-h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros.tif'
    with rasterio.open(reference) as ds:
        shape, crs, transform = ds.shape, ds.crs, ds.transform
    rows = []
    for path in sorted((ROOT / 'docs/downloads').glob('kanler*-zeros.tif')):
        with rasterio.open(path) as ds:
            a = ds.read(1)
            grid = ds.shape == shape and ds.crs == crs and ds.transform == transform
            checks = dict(single_band=ds.count == 1, float32=ds.dtypes == ('float32',),
                          no_nan_anywhere=bool(np.isfinite(a).all()),
                          values_in_0_1=bool(((a >= 0) & (a <= 1)).all()),
                          nodata_none=ds.nodata is None, match_historical_reference_grid=grid)
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        historical = next((ROOT / 'evidence').glob('run_card_' + path.name.split('-')[1] + '_' + path.name.split('-')[2] + '.json'))
        card = json.loads(historical.read_text())
        checks['matches_recorded_sha256'] = h == card['raster_sha256']
        rows.append(dict(file=str(path.relative_to(ROOT)), sha256=h, checks=checks,
                         all_available_checks_pass=all(checks.values()),
                         official_template_match=None, footprint_and_catalogue_checks=None,
                         ok_to_submit=False))
    report = dict(audit_version='KANLER-STRICT-AUDIT-v1', artifacts=rows,
                  official_inputs_status='UNAVAILABLE: GitHub API restoration returned HTTP 403 rate limit',
                  reference_provenance='Historical GEMSDOE32 raster only; NOT official template authentication',
                  holdout_status='QUARANTINED: full-catalogue placement; no admissible new HOLDOUT-DTI',
                  uniqueness_status='FAIL: archived >70% lattice overlap; no exemption permitted',
                  promotion_authorized=False, experiments_run=0)
    (ROOT / 'evidence/artifact_audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if rows and all(x['all_available_checks_pass'] for x in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
