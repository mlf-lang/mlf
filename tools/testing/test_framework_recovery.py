#!/usr/bin/env python3
"""Negative controls for narrowly reconstructed source and lock repairs."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import framework_recovery as recovery
import history_refs as history

ROOT = Path(__file__).resolve().parents[2]


class FrameworkRecoveryControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.originals = {
            path: subprocess.check_output(['git', '--no-replace-objects', 'show', recovery.FROZEN_FRAMEWORK + ':' + path], cwd=ROOT)
            for path in recovery.EDITS
        }
        self.old_lock = subprocess.check_output(['git', '--no-replace-objects', 'show', recovery.FROZEN_FRAMEWORK + ':mlf.lock'], cwd=ROOT)
        for path, original in self.originals.items():
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(recovery.repair_bytes(path, original))
        def frozen(command, **kwargs):
            prefix = ['git', '--no-replace-objects', 'show']
            self.assertEqual(command[:3], prefix)
            self.assertEqual(kwargs['cwd'], self.root)
            revision, path = command[3].split(':', 1)
            self.assertEqual(revision, recovery.FROZEN_FRAMEWORK)
            return self.originals[path]
        self.reader = patch.object(recovery.subprocess, 'check_output', side_effect=frozen)
        self.reader.start()
        self.addCleanup(self.reader.stop)

    def test_only_reviewed_source_and_hash_replacements_are_admitted(self):
        actual = recovery.repaired_root_lock(self.root, self.old_lock)
        before, after = json.loads(self.old_lock), json.loads(actual)
        changes = []
        for old, new in zip(before['packages'], after['packages']):
            self.assertEqual(set(old), set(new))
            for key in old:
                if key != 'sources':
                    self.assertEqual(old[key], new[key])
            self.assertEqual(set(old['sources']), set(new['sources']))
            for path, digest in old['sources'].items():
                if digest != new['sources'][path]:
                    changes.append(old['path'] + '/' + path)
        self.assertEqual(sorted(changes), ['testing/Test/Evidence.emlf', 'testing/Test/Outcome.emlf', 'testing/Test/Plan.emlf'])

    def test_each_unreviewed_source_change_fails(self):
        for path in recovery.EDITS:
            with self.subTest(path=path):
                target = self.root / path
                original = target.read_bytes()
                target.write_bytes(original + b'\n-- unrelated edit\n')
                with self.assertRaisesRegex(ValueError, 'exceeds reviewed repair'):
                    recovery.repaired_root_lock(self.root, self.old_lock)
                target.write_bytes(original)

    def test_missing_or_duplicate_transformation_anchor_fails(self):
        for path, changes in recovery.EDITS.items():
            with self.subTest(path=path):
                marker = changes[0][0].encode()
                for value in (self.originals[path].replace(marker, b'', 1), self.originals[path] + marker):
                    with self.assertRaisesRegex(ValueError, 'ambiguous frozen framework input'):
                        recovery.repair_bytes(path, value)
        with self.assertRaisesRegex(ValueError, 'unreviewed framework repair'):
            recovery.repair_bytes('arbitrary.emlf', b'')

    def test_wrong_frozen_hash_or_missing_module_fails(self):
        for mode in ('hash', 'missing'):
            value = json.loads(self.old_lock)
            package = next(row for row in value['packages'] if row['path'] == 'testing')
            if mode == 'hash':
                package['sources']['Test/Outcome.emlf'] = '0' * 64
            else:
                del package['sources']['Test/Outcome.emlf']
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                recovery.repaired_root_lock(self.root, json.dumps(value).encode())

    def test_duplicate_json_keys_fail(self):
        with self.assertRaisesRegex(ValueError, 'duplicate lock key'):
            recovery.repaired_root_lock(self.root, b'{"format":1,"format":1,"packages":[]}')

    def test_checker_rejects_arbitrary_lock_delta(self):
        expected = recovery.repaired_root_lock(self.root, self.old_lock)
        digest = recovery.digest(self.old_lock)
        with patch.object(history, 'ROOT', self.root), patch.object(history, 'historical_bytes', return_value=self.old_lock):
            self.assertTrue(history.checked_current('mlf.lock', expected, digest))
            self.assertFalse(history.checked_current('mlf.lock', expected + b'\n', digest))
            value = json.loads(expected)
            value['packages'][0]['version'] = '999.0.0'
            self.assertFalse(history.checked_current('mlf.lock', json.dumps(value).encode(), digest))


class PublishedFrameworkRecoveryControls(unittest.TestCase):
    def test_actual_root_lock_matches_exact_reviewed_repairs(self):
        original = subprocess.check_output(
            ['git', '--no-replace-objects', 'show', recovery.FROZEN_FRAMEWORK + ':mlf.lock'], cwd=ROOT)
        self.assertEqual((ROOT / 'mlf.lock').read_bytes(), recovery.repaired_root_lock(ROOT, original))


if __name__ == '__main__':
    unittest.main()
