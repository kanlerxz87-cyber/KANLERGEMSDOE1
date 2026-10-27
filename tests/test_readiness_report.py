"""Report consistency checks do not replace a raster or fold-provenance audit."""
import copy
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_readiness_report as report


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads((ROOT / 'registry/focus_sites.json').read_text())
        self.audit = json.loads((ROOT / 'evidence/protocol_audit_20261026.json').read_text())

    def test_generated_reports_are_current(self):
        subprocess.run([sys.executable, str(ROOT / 'scripts/build_readiness_report.py'), '--check'], check=True)

    def test_nine_rows_are_unambiguously_negative(self):
        rows = report.rows_from_evidence(self.registry, self.audit)
        self.assertEqual(tuple(r['site'] for r in rows), report.SITES)
        page, csv_text = report.render(rows, self.audit['reviewed_utc'])
        self.assertEqual(len(list(csv.DictReader(io.StringIO(csv_text)))), 9)
        for row in rows:
            self.assertEqual(row['file_to_submit'], 'NONE')
            self.assertEqual(row['ok_to_submit'], 'NO')
            self.assertIn('UNAVAILABLE', row['estimated_score'])
        self.assertIn('not a new evaluation', page)
        self.assertIn('no receipt', page)

    def test_missing_or_duplicate_inventory_fails(self):
        for key in ('files',):
            broken = copy.deepcopy(self.registry)
            broken[key].pop()
            with self.assertRaises(ValueError):
                report.rows_from_evidence(broken, self.audit)
        broken = copy.deepcopy(self.audit)
        broken['focus_sites'][1] = broken['focus_sites'][0]
        with self.assertRaises(ValueError):
            report.rows_from_evidence(self.registry, broken)

    def test_stale_hash_or_score_fails(self):
        for key, value in (('sha256', '0' * 64), ('reported_score', .999)):
            broken = copy.deepcopy(self.audit)
            broken['focus_sites'][0][key] = value
            with self.assertRaises(ValueError):
                report.rows_from_evidence(self.registry, broken)

    def test_invalid_overlap_and_changed_policy_require_review(self):
        for value in (float('nan'), float('inf'), -1, .70):
            broken = copy.deepcopy(self.audit)
            broken['focus_sites'][0]['worst_peer_3px_overlap'] = value
            with self.assertRaises(ValueError):
                report.rows_from_evidence(self.registry, broken)


if __name__ == '__main__':
    unittest.main()
