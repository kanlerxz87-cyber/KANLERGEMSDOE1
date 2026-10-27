"""Historical audit rendering must not invent score estimates or contest approvals."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_executive_summary as summary


class ExecutiveSummaryTests(unittest.TestCase):
    def test_published_table_is_reproducible(self):
        page = (ROOT / 'docs/executive-summary.html').read_text(encoding='utf-8')
        generated = (page.count(summary.BEGIN) == 1 and page.count(summary.END) == 1
                     and page.index(summary.BEGIN) < page.index(summary.END))
        if generated:
            for path, text in summary.outputs().items():
                self.assertEqual(path.read_text(), text, str(path))
        else:
            low = page.lower()
            self.assertIn('no organizer receipt', low)
            self.assertIn('not a leaderboard forecast', low)
            self.assertIn('selector approval', low)

    def test_all_nine_rows_explicitly_block_contest_download(self):
        report = summary.build()
        self.assertEqual(len(report['rows']), 9)
        self.assertEqual(report['highest_user_report']['site'], 'GEMSDOE32')
        self.assertFalse(report['ok_to_submit'])
        for row in report['rows']:
            self.assertIsNone(row['estimated_leaderboard_score'])
            self.assertIsNone(row['holdout_dti']['value'])
            self.assertIsNone(row['contest_download'])
            self.assertFalse(row['ok_to_download_and_submit'])
            self.assertFalse(row['unique_in_nine_champion_subset'])
            self.assertFalse(row['full_registry_checked'])

    def test_missing_duplicate_or_unexpected_site_fails(self):
        rows = [{'site': site} for site in summary.FOCUS_SITES]
        for bad in (rows[:-1], rows + [rows[0]], rows[:-1] + [rows[0]]):
            with self.assertRaises(ValueError): summary.indexed(bad)

    def test_mismatched_hash_score_or_measurement_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            inputs = {}
            for name, rel in summary.INPUTS.items():
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                inputs[name] = json.loads((ROOT / rel).read_text())
                p.write_text(json.dumps(inputs[name]))
            audit_path = root / summary.INPUTS['raster_audit']
            audit = inputs['raster_audit']
            for key, value in (('sha256', '0'*64), ('reported_score', .999),
                               ('worst_peer_3px_overlap', .01), ('literal_unique_vs_other_focus_champions', True)):
                changed = copy.deepcopy(audit)
                changed['focus_sites'][0][key] = value
                audit_path.write_text(json.dumps(changed))
                with self.subTest(key=key), self.assertRaises(ValueError): summary.build(root)
            changed = copy.deepcopy(audit)
            changed['focus_matrix']['GEMSDOE24']['GEMSDOE25']['spearman_final_dots'] = None
            audit_path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError): summary.build(root)

    def test_renderer_cannot_act_as_selector(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for name, rel in summary.INPUTS.items():
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                content = json.loads((ROOT / rel).read_text())
                if name == 'current_run_card':
                    content['ok_to_submit'] = True
                    content['verdict'] = 'promote'
                p.write_text(json.dumps(content))
            with self.assertRaises(ValueError): summary.build(root)

    def test_nonfinite_evidence_is_rejected(self):
        for value in (True, None, float('nan'), -1, 1.1):
            with self.subTest(value=value), self.assertRaises(ValueError):summary.fraction(value)
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'bad.json'
            p.write_text('{"score": NaN}')
            with self.assertRaises(ValueError):summary.read_json(p)


if __name__ == '__main__':
    unittest.main()
