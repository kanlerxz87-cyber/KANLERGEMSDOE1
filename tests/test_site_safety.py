"""Safety checks for the Pages artifact actually deployed by .github/workflows/pages.yml."""
import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit, unquote

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_public_feed as feed


class Links(HTMLParser):
    def __init__(self):super().__init__();self.hrefs=[];self.disabled=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'href' in a:self.hrefs.append(a['href'])
        if tag=='button' and 'disabled' in a:self.disabled=True


class SiteSafetyTests(unittest.TestCase):
    def html(self,name):return (ROOT/'docs'/name).read_text(encoding='utf-8')
    def test_actual_landing_prominently_blocks_submission(self):
        html=self.html('index.html')
        self.assertIn('STOP — NO RASTER IS CLEARED FOR SUBMISSION',html)
        self.assertIn('Submission download unavailable',html)
        self.assertIn('99.39375%',html)
        parser=Links();parser.feed(html);self.assertTrue(parser.disabled)
    def test_executive_covers_nine_sites_and_negative_findings(self):
        html=self.html('executive-summary.html')
        for site in ('GEMSDOE24','GEMSDOE25','GEMSDOE27','GEMSDOE28','GEMSDOE30','GEMSDOE31','GEMSDOE32','GEMSDOE33','GEMSDOE36'):
            with self.subTest(site=site):self.assertIn(site,html)
        self.assertIn('Unavailable — no admissible HOLDOUT-DTI',html)
        self.assertIn('99.5875%',html);self.assertIn('99.190625%',html)
        self.assertIn('not organizer-confirmed receipts',html)
    def test_no_contest_tiff_or_zip_download_links(self):
        for path in (ROOT/'docs').rglob('*.html'):
            p=Links();p.feed(path.read_text())
            with self.subTest(page=path.name):
                self.assertFalse(any(urlsplit(h).path.lower().endswith(('.tif','.tiff','.zip')) for h in p.hrefs))
    def test_all_local_html_links_resolve(self):
        for path in (ROOT/'docs').rglob('*.html'):
            p=Links();p.feed(path.read_text())
            for href in p.hrefs:
                parsed=urlsplit(href)
                if parsed.scheme or parsed.netloc or not parsed.path:continue
                with self.subTest(page=path.name,href=href):
                    self.assertTrue((path.parent/unquote(parsed.path)).is_file())
    def test_one_current_card_has_correction_and_hash(self):
        p=ROOT/'data/run-card.json';c=json.loads(p.read_text())
        self.assertEqual(c['verdict'],'negative');self.assertFalse(c['ok_to_submit'])
        self.assertEqual(c['holdout_dti']['status'],'INADMISSIBLE')
        self.assertIsNone(c['holdout_dti']['valid_value']);self.assertIsNone(c['holdout_dti']['valid_ci95'])
        self.assertEqual(len(c['raster_sha256']),64);self.assertTrue(c['validator_output']['all_checks_passed'])
        self.assertFalse(c['correlation_overlap_vs_registry']['full_registry_checked'])
        self.assertGreater(c['correlation_overlap_vs_registry']['final_dots_within_3px_of_lattice'],.70)
        self.assertLessEqual(len(c['submission_note']),140)
        self.assertEqual(c,json.loads((ROOT/'docs/evidence/current_run_card.json').read_text()))
    def test_hypothesis_page_discloses_untested_and_scope(self):
        text=self.html('hypotheses.html')
        self.assertIn('unimplemented and untested in this review',text)
        self.assertIn('No new experiment will run',text)
        self.assertIn('swarm',text.lower())
    def test_root_pages_redirect_to_actual_pages(self):
        for name in ('index','executive-summary','hypotheses','sources'):
            self.assertIn('docs/'+name+'.html',(ROOT/(name+'.html')).read_text())
    def test_parallel_archive_is_literal_duplicate(self):
        page=self.html('mplc/index.html')
        self.assertIn('NOT UNIQUE, DO NOT SUBMIT',page)
        self.assertIn('99.9522%',page)
        audit=json.loads((ROOT/'docs/evidence/protocol_audit_20261026.json').read_text())
        parallel=audit['prior_parallel_artifacts']
        self.assertEqual(len(parallel),1)
        self.assertTrue(parallel[0]['lattice_duplicate'])
        self.assertFalse(parallel[0]['ok_to_submit'])

    def test_historical_cards_carry_supersession(self):
        for path in (ROOT/'docs/evidence').glob('run_card_h*.json'):
            self.assertFalse(json.loads(path.read_text())['status_update_20261026']['ok_to_submit'])


class PublicFeedTests(unittest.TestCase):
    fixture='''<table><tr><th>Rank</th><th>Participant</th><th>Best public DW-Tversky</th></tr>
    <tr><td>#1</td><td>example</td><td>0.4437</td></tr></table>'''
    def test_parses_only_unambiguous_public_table(self):
        self.assertEqual(feed.parse_rank_one(self.fixture),.4437)
        for bad in ('<table><tr><td>#1</td><td>0.9</td></tr></table>',
                    self.fixture.replace('0.4437','not a number'),
                    self.fixture.replace('0.4437','1.12')):
            with self.assertRaises(ValueError):feed.parse_rank_one(bad)
    def test_successful_fetch_updates_snapshot(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'feed.json';p.write_text(json.dumps({'rank_one_public_dti':.1,'observed_utc':'2026-01-01'}))
            class Response:
                status=200
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self,n):return PublicFeedTests.fixture.encode()
            with mock.patch.object(feed,'urlopen',return_value=Response()):result=feed.refresh(p)
            self.assertEqual(result['status'],'refreshed')
            self.assertEqual(result['rank_one_public_dti'],.4437)
            self.assertNotEqual(result['observed_utc'],'2026-01-01')

    def test_failed_fetch_keeps_dated_value_and_labels_stale(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'feed.json';p.write_text(json.dumps({'rank_one_public_dti':.4437,'observed_utc':'2026-10-26'}))
            with mock.patch.object(feed,'urlopen',side_effect=OSError('offline')):result=feed.refresh(p)
            self.assertEqual(result['status'],'stale_snapshot')
            self.assertEqual(result['rank_one_public_dti'],.4437)
            self.assertEqual(result['observed_utc'],'2026-10-26')
            self.assertIsNotNone(result['last_refresh_attempt_utc'])

if __name__=='__main__':unittest.main()
