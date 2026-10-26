from __future__ import annotations
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.ids=set(); self.buttons=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if 'id' in a: self.ids.add(a['id'])
        for key in ('href','src'):
            if key in a: self.links.append(a[key])
        if tag == 'button': self.buttons.append(a)


def test_site_is_reproducible_and_local_links_exist():
    subprocess.run([sys.executable, str(ROOT/'scripts/build_site.py')], check=True, cwd=ROOT)
    for path in (ROOT/'docs').glob('*.html'):
        parser=Links(); parser.feed(path.read_text())
        for target in parser.links:
            split=urlsplit(target)
            if split.scheme or split.netloc or target.startswith('mailto:'): continue
            dest=(path.parent/split.path) if split.path else path
            assert dest.is_file(), f'{path.name}: {target} is missing'
            if split.fragment and dest.suffix == '.html':
                p=Links(); p.feed(dest.read_text()); assert split.fragment in p.ids, (path.name,target)
    html=(ROOT/'docs/index.html').read_text()
    assert 'No file approved' in html and 'Submission download unavailable' in html
    p=Links(); p.feed(html)
    assert len(p.buttons)==1 and 'disabled' in p.buttons[0]
    assert html.count('Historical file · research only') == 9
    assert html.count('User-reported claim, unverified') == 9


def test_negative_run_card_never_invents_a_file_or_score():
    card=json.loads((ROOT/'evidence/run-card.json').read_text())
    assert card['verdict']=='negative' and card['raster_sha256'] is None
    assert card['holdout']['value'] is None and card['holdout']['ci95'] is None
    assert card['validator_output']['status'].startswith('NOT RUN')
    assert card['weekly_slot_selected'] is False
    assert len(card['submission_note']) <= 140
    assert json.loads((ROOT/'docs/data/run-card.json').read_text()) == card


def test_audited_hashes_and_no_automatic_drivendata_feed():
    manifest=json.loads((ROOT/'registry/focus_sites.json').read_text())
    audit=json.loads((ROOT/'evidence/focus-site-audit-20261026.json').read_text())
    assert len(manifest['sites']) == 9
    for site in manifest['sites']:
        assert audit['sites'][site['id']]['sha256'] == site['sha256']
        assert not audit['sites'][site['id']]['literal_peer_gate_pass']
    js=(ROOT/'docs/assets/app.js').read_text()
    assert 'api.github.com' in js
    assert 'fetch(`https://www.drivendata.org' not in js
    assert 'fetch("https://www.drivendata.org' not in js
    assert json.loads((ROOT/'docs/data/focus-site-audit.json').read_text()) == audit


def test_builder_rejects_tampered_decisions_and_audit():
    import copy
    sys.path.insert(0,str(ROOT/'scripts'))
    from build_site import validate_negative_evidence
    manifest=json.loads((ROOT/'registry/focus_sites.json').read_text())
    audit=json.loads((ROOT/'evidence/focus-site-audit-20261026.json').read_text())
    card=json.loads((ROOT/'evidence/run-card.json').read_text())
    parallel_manifest=json.loads((ROOT/'registry/parallel_artifacts.json').read_text())
    parallel=json.loads((ROOT/'evidence/parallel-artifact-audit-20261026.json').read_text())
    validate_negative_evidence(manifest,audit,card,parallel_manifest,parallel)
    for key, value in [('verdict','promote'),('raster_sha256','abcd'),('weekly_slot_selected',True)]:
        altered=copy.deepcopy(card); altered[key]=value
        import pytest
        with pytest.raises(ValueError): validate_negative_evidence(manifest,audit,altered,parallel_manifest,parallel)
    altered=copy.deepcopy(card); altered['holdout']['value']=0.5
    with pytest.raises(ValueError): validate_negative_evidence(manifest,audit,altered,parallel_manifest,parallel)
    altered=copy.deepcopy(audit); altered['lattice']['outside_3px_pixels']=1
    with pytest.raises(ValueError): validate_negative_evidence(manifest,altered,card,parallel_manifest,parallel)
    altered=copy.deepcopy(audit); altered['sites']['GEMSDOE24']['literal_peer_gate_pass']=True
    with pytest.raises(ValueError): validate_negative_evidence(manifest,altered,card,parallel_manifest,parallel)
    altered_parallel=copy.deepcopy(parallel); altered_parallel['artifacts']['H1 IEDR']['lattice_overlap_fraction']=0.1
    with pytest.raises(ValueError): validate_negative_evidence(manifest,audit,card,parallel_manifest,altered_parallel)


def test_parallel_results_are_research_only_and_sha_pinned():
    import hashlib
    manifest=json.loads((ROOT/'registry/parallel_artifacts.json').read_text())
    audit=json.loads((ROOT/'evidence/parallel-artifact-audit-20261026.json').read_text())
    assert audit['verdict']=='negative' and audit['ok_to_submit'] is False
    assert len(manifest['candidates'])==3
    for entry in manifest['candidates']:
        row=audit['artifacts'][entry['id']]
        assert hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()==entry['sha256']==row['sha256']
        assert row['positive_pixels']==32000 and row['literal_lattice_gate_pass'] is False
        assert row['lattice_near_dots']*10>7*row['positive_pixels']
        assert row['saved_bytes_single_band_float32'] and row['saved_bytes_grid_matches_owner_mirror']
        assert row['organizer_acceptance'] is None
    assert json.loads((ROOT/'docs/data/parallel-artifact-audit.json').read_text()) == audit
