"""Source monitoring is a freshness observation, never an approval or receipt."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import refresh_focus_sources as sources


class FocusSourceTests(unittest.TestCase):
    entry = {'site': 'GEMSDOE24', 'repo': 'example/research', 'ref': 'a'*40}

    def test_matching_and_different_heads_remain_unverified(self):
        for sha, status in (('a'*40,'HEAD_MATCHES_PIN'),('b'*40,'HEAD_DIFFERS_FROM_PIN')):
            row = sources.observe(self.entry, query=lambda endpoint: [{'sha': sha}])
            self.assertEqual(row['status'],status)
            self.assertFalse(row['artifact_at_head_verified'])
            self.assertFalse(row['complete_registry_inventory'])
            self.assertEqual(row['observed_head_commit'],sha)

    def test_bad_source_or_response_fails(self):
        for entry in ({**self.entry,'repo':'../bad'}, {**self.entry,'ref':'main'}):
            with self.assertRaises(ValueError):sources.observe(entry)
        with self.assertRaises(ValueError):sources.observe(self.entry,query=lambda _: [{'sha':'invalid'}])

    def test_repeated_failure_retains_original_dated_observation(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);manifest=root/'manifest.json';dest=root/'sources.json'
            manifest.write_text(json.dumps({'files':[self.entry]}))
            old=sources.observe(self.entry,query=lambda _: [{'sha':'a'*40}])
            dest.write_text(json.dumps({'sources':[old]}))
            with mock.patch.object(sources,'observe',side_effect=OSError('offline')):
                first=sources.refresh(manifest,dest)
                second=sources.refresh(manifest,dest)
            for report in (first,second):
                row=report['sources'][0]
                self.assertEqual(row['status'],'REFRESH_UNAVAILABLE')
                self.assertIsNone(row['observed_utc'])
                self.assertEqual(row['last_successful_observation'],old)
                self.assertFalse(report['ok_to_submit'])


if __name__ == '__main__':unittest.main()
