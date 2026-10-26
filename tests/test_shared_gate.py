from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
REV = '07806249f4ed3efe70b4fbf866183c32392b7853'


def test_shared_preview_bug_is_reported_without_forking():
    marker = ROOT/'.cache/upstream'/f'GEMSDOE32-{REV}'/'.verified-archive-sha256'
    if not marker.exists():
        pytest.skip('Pinned shared template not bootstrapped in this checkout')
    result = subprocess.run([sys.executable, str(ROOT/'scripts/check_shared_gate.py')],
                            text=True, capture_output=True)
    assert result.returncode == 1
    assert 'preview overlap=1.000' in result.stdout
    assert 'FAIL: upstream surface gate ignores' in result.stderr


def test_shared_empty_truth_bookkeeping_bug_is_reported():
    marker = ROOT/'.cache/upstream'/f'GEMSDOE32-{REV}'/'.verified-archive-sha256'
    if not marker.exists():
        pytest.skip('Pinned shared template not bootstrapped in this checkout')
    result = subprocess.run([sys.executable, str(ROOT/'scripts/check_shared_holdout.py')],
                            text=True, capture_output=True)
    assert result.returncode == 1
    assert 'fold TP/FP/FN=(1.0, 7.0, 0.0)' in result.stdout
    assert 'pooled block TP/FP/FN=(1.0, 0.0, 0.0)' in result.stdout
    assert 'FAIL: shared evaluator drops pooled mass' in result.stderr
