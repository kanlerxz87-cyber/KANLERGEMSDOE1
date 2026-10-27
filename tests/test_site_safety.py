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
        self.assertIn('submission-readiness.html',html)
        self.assertIn('99.39375%',html)
        parser=Links();parser.feed(html);self.assertTrue(parser.disabled)

    def test_leaderboard_feed_never_claims_unverified_snapshot_is_current(self):
        feed_data=json.loads((ROOT/'docs/feed.json').read_text())
        self.assertEqual(feed_data['status'],'refresh_result_unverified')
        self.assertEqual(feed_data['rank_one_public_dti'],0.4437)
        self.assertEqual(feed_data['observed_utc'],'2026-10-26')
        self.assertEqual(feed_data['last_refresh_attempt_utc'],'2026-10-27T12:07:26Z')
        page=self.html('index.html')
        self.assertIn('0.3195 and 0.4413',page)
        js=(ROOT/'docs/assets/feed.js').read_text()
        self.assertIn('not verifiable in this repository',js)
        self.assertIn('textContent',js)

    def test_prompt_archive_records_focus_reports_and_stop(self):
        brief=(ROOT/'docs/ORIGINAL_PROMPT.md').read_text()
        for token in ('GEMSDOE24','GEMSDOE32','0.2778','0.3195','0.4413','0.4437','70%','not a byte-for-byte transcript'):
            with self.subTest(token=token):self.assertIn(token,brief)

    def test_data_placement_receipt_discloses_owner_mirror_provenance(self):
        receipt=json.loads((ROOT/'data/restore_receipt.json').read_text())
        prepared=json.loads((ROOT/'data/prepared_manifest.json').read_text())
        self.assertEqual(receipt['storage_root'],'data')
        self.assertEqual(receipt['verified_files_count'],26)
        self.assertIn('not authenticate',receipt['provenance_warning'].lower())
        self.assertEqual(len(prepared['bands']),19)
        self.assertEqual(prepared['counts']['footprint_valid_pixels'],5167373)
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
        self.assertFalse(list((ROOT/'docs').rglob('*.tif')))
        self.assertFalse(list((ROOT/'docs').rglob('*.tiff')))
        self.assertFalse(list((ROOT/'docs').rglob('*.zip')))
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
