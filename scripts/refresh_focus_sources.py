#!/usr/bin/env python3
"""Observe public focus-repository HEADs without treating them as score receipts.

Read-only GitHub API calls through gh. A changed HEAD is only a freshness warning:
it neither proves the pinned TIFF changed nor inventories every registry raster.
No manifest, model, TIFF, slot or approval is changed. Individual failures are
explicit and a prior observation is retained with its original timestamp.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def observe(entry, *, query=None):
    repo, pinned = entry['repo'], entry['ref']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', repo) or not re.fullmatch(r'[0-9a-f]{40}', pinned):
        raise ValueError('Unsafe focus source')
    if query is None:
        def query(endpoint):
            result = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True, check=True, timeout=25)
            return json.loads(result.stdout)
    commits = query(f'repos/{repo}/commits?per_page=1')
    sha = commits[0]['sha']
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid GitHub commit response')
    return {'site': entry['site'], 'repo': repo, 'pinned_artifact_commit': pinned,
            'observed_head_commit': sha, 'observed_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'head_url': f'https://github.com/{repo}/commit/{sha}',
            'status': 'HEAD_DIFFERS_FROM_PIN' if sha != pinned else 'HEAD_MATCHES_PIN',
            'artifact_at_head_verified': False, 'complete_registry_inventory': False}


def refresh(manifest, destination):
    entries = json.loads(manifest.read_text())['files']
    previous = {}
    if destination.exists():
        previous = {r['site']: r for r in json.loads(destination.read_text()).get('sources', [])}
    rows = []
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    for entry in entries:
        try:
            row = observe(entry)
        except Exception as exc:
            # Do not print subprocess errors, which may include sensitive context.
            prior = previous.get(entry['site'])
            row = {'site': entry['site'], 'repo': entry['repo'], 'status': 'REFRESH_UNAVAILABLE',
                   'pinned_artifact_commit': entry['ref'], 'observed_head_commit': None, 'observed_utc': None,
                   'error_type': type(exc).__name__, 'artifact_at_head_verified': False,
                   'complete_registry_inventory': False,
                   'last_successful_observation': (prior.get('last_successful_observation') if prior and prior.get('status') == 'REFRESH_UNAVAILABLE' else prior)}
        row['last_refresh_attempt_utc'] = now
        rows.append(row)
    report = {'schema_version': 1, 'last_refresh_attempt_utc': now,
              'scope': 'Public repository HEAD observations only; not current scores, TIFF verification, or complete registry inventory',
              'sources': rows, 'ok_to_submit': False}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/evidence/focus_source_refresh.json')
    args = parser.parse_args()
    report = refresh(ROOT/'registry/focus_sites.json', args.output)
    for row in report['sources']:
        print(f"{row['site']}: {row['status']}; no contest authorization")


if __name__ == '__main__':
    main()
