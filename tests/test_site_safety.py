"""Safety checks adapted for both root and /docs Pages deployment modes."""
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.hrefs=[]; self.disabled_download_button=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='a' and 'href' in a: self.hrefs.append(a['href'])
        if tag=='button' and 'disabled' in a: self.disabled_download_button=True


class SiteSafetyTests(unittest.TestCase):
    def read_html(self,name):
        return (ROOT/name).read_text(encoding='utf-8')

    def test_landing_page_has_negative_release_gate_in_both_pages_modes(self):
        root=self.read_html('index.html')
        self.assertIn('No file approved for submission',root)
        self.assertIn('docs/index.html',root)
        html=self.read_html('docs/index.html')
        self.assertIn('No file approved',html)
        self.assertIn('Submission download unavailable',html)
        parser=Links(); parser.feed(html)
        self.assertTrue(parser.disabled_download_button)

    def test_executive_overview_covers_nine_sites_and_blocks_submit(self):
        html=self.read_html('docs/index.html')
        for site in ('GEMSDOE24','GEMSDOE25','GEMSDOE27','GEMSDOE28','GEMSDOE30','GEMSDOE31','GEMSDOE32','GEMSDOE33','GEMSDOE36'):
            with self.subTest(site=site): self.assertIn(site,html)
        self.assertIn('OUR SCORE ESTIMATE',html)
        self.assertEqual(html.count('Download TIFF · research only'),3)
        self.assertGreaterEqual(html.count('Do not submit'),12)
        self.assertIn('not admissible',html.lower())

    def test_legacy_pages_redirect_to_current_safety_guidance(self):
        for name in ('index.html','executive-summary.html','hypotheses.html','sources.html',
                     'docs/how-to-submit.html','docs/hypotheses.html','docs/research.html','docs/sources.html'):
            html=self.read_html(name)
            with self.subTest(page=name):
                self.assertIn('No file approved for submission',html)
                self.assertIn('http-equiv="refresh"',html)

    def test_negative_run_card_is_well_formed_and_has_no_new_result(self):
        card=json.loads((ROOT/'evidence/run-card.json').read_text())
        self.assertEqual(card['verdict'],'negative')
        self.assertFalse(card['weekly_slot_selected'])
        self.assertIsNone(card['holdout']['value'])
        self.assertIsNone(card['raster_sha256'])
        self.assertIsNone(card['submission_name'])
        self.assertEqual(card['prior_parallel_run']['experiments_recorded'],3)

    def test_hypotheses_are_not_presented_as_validated(self):
        html=self.read_html('docs/evidence.html')
        self.assertIn('hypothesis, not a detected fault or projected score',html)
        self.assertIn('holdout are missing',html)
        self.assertIn('this audit ran no experiment',html.lower())

    def test_archived_experiment_entrypoint_is_blocked(self):
        result=subprocess.run([sys.executable,str(ROOT/'scripts/run_iedr_experiments.py')],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('BLOCKED:',result.stderr)
        self.assertIn('full-catalogue',result.stderr)


if __name__=='__main__': unittest.main()
