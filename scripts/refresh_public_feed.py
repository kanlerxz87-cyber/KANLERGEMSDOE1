#!/usr/bin/env python3
"""Refresh a public leaderboard snapshot during Pages deployment, with safe fallback.

No organizer account is used. A public leaderboard is not a submission receipt.
The parser fails closed; fetch/format changes keep the dated snapshot rather than
inventing a current value. A scheduled workflow deploys the result without pushing.
"""
from __future__ import annotations
import argparse
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

URL = 'https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/'


class Rows(HTMLParser):
    def __init__(self):
        super().__init__();self.tables=[];self.table=None;self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='table':self.table=[]
        elif tag=='tr' and self.table is not None:self.row=[]
        elif tag in ('th','td') and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('th','td') and self.cell is not None and self.row is not None:
            self.row.append(' '.join(' '.join(self.cell).split()));self.cell=None
        elif tag=='tr' and self.row is not None and self.table is not None:
            self.table.append(self.row);self.row=None
        elif tag=='table' and self.table is not None:
            self.tables.append(self.table);self.table=None


def parse_rank_one(html: str) -> float:
    parser=Rows();parser.feed(html)
    for table in parser.tables:
        if not table:
            continue
        header=' '.join(table[0]).lower()
        if 'public' not in header or 'tversky' not in header:
            continue
        for row in table[1:]:
            if not row or not re.fullmatch(r'#?\s*1',row[0]):continue
            # The official numeric score must be a standalone cell, never a time/count.
            if len(row)<3:continue
            values=[float(x) for x in row[1:] if re.fullmatch(r'(?:0(?:\.\d+)?|1(?:\.0+)?)',x)]
            if len(values)==1 and 0<=values[0]<=1:return values[0]
    raise ValueError('No unambiguous rank-one public DTI found')


def refresh(path: Path) -> dict:
    existing=json.loads(path.read_text(encoding='utf-8'))
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    try:
        req=Request(URL,headers={'User-Agent':'GEMS-public-leaderboard-snapshot/1.0'})
        with urlopen(req,timeout=25) as response:
            if response.status!=200:raise ValueError(f'HTTP {response.status}')
            html=response.read(5_000_001)
            if len(html)>5_000_000:raise ValueError('Leaderboard response too large')
        score=parse_rank_one(html.decode('utf-8','replace'))
        existing.update(rank_one_public_dti=score, observed_utc=now, status='refreshed',
                        last_refresh_attempt_utc=now, refresh_message='Public page parsed successfully')
    except Exception as exc:
        existing.update(status='stale_snapshot',last_refresh_attempt_utc=now,
                        refresh_message=f'Refresh unavailable ({type(exc).__name__}); retained dated snapshot')
    existing['source_url']=URL
    path.write_text(json.dumps(existing,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return existing


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'docs/feed.json')
    args=ap.parse_args();result=refresh(args.output)
    print(f"Leaderboard feed: {result['status']}; observed {result['observed_utc']}")

if __name__=='__main__':main()
