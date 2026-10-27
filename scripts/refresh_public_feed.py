#!/usr/bin/env python3
"""Refresh a public-board snapshot, not a candidate score or submission receipt.

Match rank and score by column headers, never by a guess among numeric cells.
Fail closed on duplicate ranks/score columns, redirects or malformed data, and
retain the last dated value on fetch failure. Network failures are not scores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

URL = 'https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/'
PARSER_VERSION = 'public-dti-header-v2'


class Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.table = self.row = self.cell = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.depth += 1
            if self.depth > 1:
                raise ValueError('Nested leaderboard tables are ambiguous')
            self.table = []
        elif tag == 'tr' and self.table is not None:
            self.row = []
        elif tag in ('th', 'td') and self.row is not None:
            attrs = dict(attrs)
            if attrs.get('colspan', '1') != '1' or attrs.get('rowspan', '1') != '1':
                raise ValueError('Spanning cells are not supported')
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('th', 'td') and self.cell is not None and self.row is not None:
            self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None and self.table is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table)
            self.table = None
            self.depth -= 1


def parse_rank_one(html: str) -> float:
    parser = Rows()
    parser.feed(html)
    parser.close()
    if parser.depth or parser.row is not None or parser.cell is not None:
        raise ValueError('Truncated leaderboard table')
    candidates = []
    for table in parser.tables:
        if not table:
            continue
        headers = [h.casefold() for h in table[0]]
        score_cols = [i for i, h in enumerate(headers) if 'public' in h and 'tversky' in h]
        if not score_cols:
            continue
        rank_cols = [i for i, h in enumerate(headers) if h in ('rank', '#', 'position')]
        if len(score_cols) != 1 or len(rank_cols) != 1:
            raise ValueError('Ambiguous public DTI or rank header')
        ri, si = rank_cols[0], score_cols[0]
        for row in table[1:]:
            if len(row) <= ri or not re.fullmatch(r'#?\s*1', row[ri]):
                continue
            if len(row) != len(headers) or not re.fullmatch(r'(?:0(?:\.\d+)?|1(?:\.0+)?)', row[si]):
                raise ValueError('Malformed rank-one score row')
            candidates.append(float(row[si]))
    if len(candidates) != 1:
        raise ValueError('No unique rank-one public DTI found')
    return candidates[0]


def refresh(path: Path) -> dict:
    existing = json.loads(path.read_text(encoding='utf-8'))
    # A damaged baseline must not masquerade as a valid dated fallback.
    baseline = existing.get('rank_one_public_dti')
    if isinstance(baseline, bool) or not isinstance(baseline, (int, float)) or not math.isfinite(baseline) or not 0 <= baseline <= 1:
        raise ValueError('Invalid dated leaderboard fallback')
    observed = datetime.fromisoformat(existing['observed_utc'].replace('Z', '+00:00'))
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    now_dt = datetime.now(timezone.utc)
    if observed > now_dt:
        raise ValueError('Future-dated leaderboard fallback')
    now = now_dt.isoformat(timespec='seconds')
    try:
        req = Request(URL, headers={'User-Agent': 'GEMS-public-leaderboard-snapshot/2.0'})
        with urlopen(req, timeout=25) as response:
            if response.status != 200:
                raise ValueError(f'HTTP {response.status}')
            if response.geturl() != URL:
                raise ValueError('Redirected away from the official leaderboard URL')
            html = response.read(5_000_001)
            if len(html) > 5_000_000:
                raise ValueError('Leaderboard response too large')
        score = parse_rank_one(html.decode('utf-8', 'strict'))
        existing.update(rank_one_public_dti=score, observed_utc=now, status='refreshed',
                        last_refresh_attempt_utc=now, refresh_message='Public score column parsed successfully',
                        response_sha256=hashlib.sha256(html).hexdigest(), parser_version=PARSER_VERSION)
        # Older participant names would otherwise silently attach to a new score.
        existing.pop('participant', None)
    except Exception as exc:
        existing.update(status='stale_snapshot', last_refresh_attempt_utc=now,
                        refresh_message=f'Refresh unavailable ({type(exc).__name__}); retained dated snapshot')
    existing['source_url'] = URL
    path.write_text(json.dumps(existing, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return existing


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'docs/feed.json')
    args = ap.parse_args()
    result = refresh(args.output)
    print(f"Leaderboard feed: {result['status']}; observed {result['observed_utc']}")


if __name__ == '__main__':
    main()
