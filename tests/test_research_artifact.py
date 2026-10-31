"""A research-only check: this never promotes or authenticates an artifact."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_research_artifact import check


class ResearchArtifactTest(unittest.TestCase):
    def test_archived_pair_and_count(self):
        result = check()
        self.assertEqual(result['emitted_positive_pixels'], 37649)
        self.assertNotEqual(result['zero_sha256'], result['nan_sha256'])
        self.assertFalse(result['template_authenticated'])
        self.assertFalse(result['uniqueness_and_holdout_replayed'])
        self.assertIn('NOT cleared', result['status'])

    def test_missing_artifacts_fail_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d, self.assertRaises(FileNotFoundError):
            check(Path(d))

    def test_landing_does_not_offer_any_historical_tiff_as_submit_ready(self):
        html = (ROOT / 'docs/index.html').read_text()
        self.assertIn('STOP — NO TIFF IS CLEARED TO DOWNLOAD AND SUBMIT', html)
        self.assertNotIn('06ccd852475120cbdff86732252478096c821babe6e608aae9e66945cc7c4bb2', html)
        self.assertNotIn('VERDICT: OK TO DOWNLOAD AND SUBMIT', html)


if __name__ == '__main__':
    unittest.main()
