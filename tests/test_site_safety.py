import importlib.util
import json
import unittest
from pathlib import Path
from html.parser import HTMLParser

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runner', ROOT / 'scripts/run_iedr_experiments.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for key in ('href', 'src'):
            if key in a:
                self.links.append(a[key])


class SafetyTests(unittest.TestCase):
    def test_canonical_site_and_redirects(self):
        for page in ('index', 'executive-summary', 'hypotheses', 'sources'):
            self.assertIn('docs/' + page + '.html', (ROOT / (page + '.html')).read_text())
            s = (ROOT / 'docs' / (page + '.html')).read_text()
            self.assertIn('DO NOT SUBMIT', s)
            self.assertIn('historical evidence quarantined', s)

    def test_local_links(self):
        for page in list(ROOT.glob('*.html')) + list((ROOT / 'docs').glob('*.html')):
            p = Links()
            p.feed(page.read_text())
            for link in p.links:
                if ':' in link or link.startswith(('#', '//')):
                    continue
                path = page.parent / link.split('#')[0].split('?')[0]
                self.assertTrue(path.exists(), f'{page}: {link}')

    def test_all_nine_sites(self):
        s = (ROOT / 'docs/executive-summary.html').read_text()
        for n in (24, 25, 27, 28, 30, 31, 32, 33, 36):
            self.assertIn('GEMSDOE' + str(n), s)

    def test_lattice_has_no_exemption(self):
        f = np.ones((8, 8), dtype=bool)
        dots = np.zeros_like(f)
        dots[::2, ::2] = True
        result = runner.uniqueness_report(np.arange(64).reshape(8, 8), dots, f, [
            dict(name=runner.LATTICE_HINT, dots=dots, n=int(dots.sum()))])
        self.assertFalse(result['unique_vs_genuine_detectors'])
        self.assertTrue(result['rows'][0]['duplicate_by_overlap'])

    def test_missing_registry_is_fail_closed(self):
        f = np.ones((8, 8), dtype=bool)
        for registry in ([], [dict(name='broken', error='unreadable')]):
            result = runner.uniqueness_report(f, f, f, registry)
            self.assertFalse(result['unique_vs_genuine_detectors'])

    def test_legacy_runner_stops_before_loading_data(self):
        with self.assertRaisesRegex(RuntimeError, 'quarantined'):
            runner.main()

    def test_cards_quarantined(self):
        for p in (ROOT / 'evidence').glob('run_card_h*.json'):
            c = json.loads(p.read_text())
            self.assertFalse(c['ok_to_submit'])
            self.assertEqual(c['audit_status'], 'QUARANTINED_NOT_PROMOTION_EVIDENCE')
            self.assertLessEqual(len(c['submission_note']), 140)


if __name__ == '__main__':
    unittest.main()
