from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_focus import capacity, load_binary  # noqa: E402
from fetch_focus_rasters import fetch  # noqa: E402


@pytest.mark.parametrize("outside,count,expected", [
    (0, 0, False), (0, 1, False), (3, 10, True), (3, 11, False),
    (6649, 22163, True), (6649, 22164, False), (6649, 37654, False),
])
def test_lattice_capacity_boundary(outside, count, expected):
    result = capacity(outside, count)
    assert result["can_pass_70pct_overlap_bound"] is expected
    assert result["first_impossible_count"] == (10 * outside // 3 + 1)
    if count:
        assert result["min_overlap_fraction"] == max(0, count - outside) / count
    else:
        assert result["min_overlap_fraction"] is None


@pytest.mark.parametrize("outside,count", [(True, 4), (1, True), (-1, 4), (2, -1), (2.0, 3)])
def test_capacity_rejects_invalid_counts(outside, count):
    with pytest.raises(ValueError):
        capacity(outside, count)


def make_tiff(path: Path, data: np.ndarray, transform=None, count=1):
    transform = transform or from_origin(0, 400, 100, 100)
    with rasterio.open(path, 'w', driver='GTiff', height=data.shape[0], width=data.shape[1],
                       count=count, dtype='float32', crs='EPSG:32611', transform=transform) as ds:
        ds.write(data.astype('float32'), 1)
        if count == 2:
            ds.write(data.astype('float32'), 2)
    return (rasterio.crs.CRS.from_epsg(32611), data.shape, transform)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_support_hash_ignores_outside_encoding(tmp_path):
    foot = np.array([[True, True, False], [True, True, False]])
    a = np.array([[1, 0, np.nan], [0, 1, np.nan]], dtype='float32')
    b = np.nan_to_num(a, nan=0)
    p, q = tmp_path/'a.tif', tmp_path/'b.tif'
    grid = make_tiff(p, a)
    make_tiff(q, b)
    ma, ia = load_binary(p, grid, foot, sha(p))
    mb, ib = load_binary(q, grid, foot, sha(q))
    assert np.array_equal(ma, mb)
    assert ia['binary_support_sha256'] == ib['binary_support_sha256']
    assert ia['sha256'] != ib['sha256']
    assert ia['all_finite_full_grid'] is False and ib['all_finite_full_grid'] is True


@pytest.mark.parametrize('bad', [np.nan, np.inf, -1., 1.01, 0.5])
def test_historical_binary_audit_rejects_bad_inside_footprint(tmp_path, bad):
    path = tmp_path/'bad.tif'
    data = np.zeros((3, 3), dtype='float32'); data[1, 1] = bad
    grid = make_tiff(path, data)
    with pytest.raises(ValueError, match='non-binary or invalid'):
        load_binary(path, grid, np.ones(data.shape, bool), sha(path))


def test_audit_rejects_changed_grid_band_count_and_hash(tmp_path):
    path = tmp_path/'bad.tif'; arr = np.zeros((3, 3), dtype='float32')
    grid = make_tiff(path, arr, count=2)
    with pytest.raises(ValueError, match='band count'):
        load_binary(path, grid, np.ones(arr.shape, bool), sha(path))
    grid = make_tiff(path, arr)
    wrong_grid = (grid[0], grid[1], from_origin(100, 400, 100, 100))
    with pytest.raises(ValueError, match='grid'):
        load_binary(path, wrong_grid, np.ones(arr.shape, bool), sha(path))
    with pytest.raises(ValueError, match='hash-mismatched'):
        load_binary(path, grid, np.ones(arr.shape, bool), '0' * 64)


def test_reference_fetch_validates_and_reuses_existing(tmp_path):
    dest = tmp_path/'reference.tif'; dest.write_bytes(b'hello')
    entry = {'repo':'buffedlizard55-lab/GEMSDOE24','ref':'a'*40,'path':'data/a.tif',
             'sha256':sha(dest),'bytes':5}
    assert fetch(entry, dest) == 'verified existing'
    for key, value in [('repo','evil/repo'),('ref','main'),('path','../x'),('sha256','bad'),('bytes',0)]:
        corrupt = dict(entry); corrupt[key] = value
        with pytest.raises(ValueError):
            fetch(corrupt, dest)


def test_reference_fetch_is_atomic_on_bad_download(tmp_path, monkeypatch):
    dest = tmp_path/'reference.tif'; dest.write_bytes(b'old')
    entry = {'repo':'buffedlizard55-lab/GEMSDOE24','ref':'a'*40,'path':'data/a.tif',
             'sha256':hashlib.sha256(b'good').hexdigest(),'bytes':4}
    def fake_run(_cmd, stdout, check):
        stdout.write(b'evil'); stdout.flush()
    monkeypatch.setattr('fetch_focus_rasters.subprocess.run', fake_run)
    with pytest.raises(ValueError, match='integrity mismatch'):
        fetch(entry, dest)
    assert dest.read_bytes() == b'old'
    assert not list(tmp_path.glob('*.partial'))
