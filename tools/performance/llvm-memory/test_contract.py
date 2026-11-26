#!/usr/bin/env python3
"""Audit the immutable UTF-8 migration fixture, without admitting today's tree.

The current implementation is exercised by run_controls.py against the old
owner and an independent Unicode list oracle. This audit only checks the
retained historical delta and its inverse; source refactoring needs no update.
"""
from pathlib import Path
import importlib.util
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('utf8_contract', HERE / 'source_contract.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


class HostContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delta = C.manifest()
        cls.before = subprocess.check_output([
            'git', '--no-replace-objects', 'show',
            cls.delta['parent_ref'] + ':' + cls.delta['path'],
        ], cwd=ROOT)
        if C.sha(cls.before) != C.OLD_SHA:
            raise ValueError('historical UTF-8 owner digest changed')
        cls.after = cls.before
        for edit in cls.delta['edits']:
            before, after = edit['old'].encode(), edit['new'].encode()
            if cls.after.count(before) != 1:
                raise ValueError('historical UTF-8 edit is not unique')
            cls.after = cls.after.replace(before, after, 1)

    def test_recorded_transition_round_trips_the_complete_historical_owner(self):
        self.assertEqual(C.sha(self.after), C.NEW_SHA)
        self.assertEqual(C.restore_before(self.after), self.before)

    def test_altered_historical_owner_is_rejected(self):
        self.assertEqual(C.restore_before(self.after), self.before)
        for altered in (self.before, self.after + b'\n', self.after[:-1], b''):
            with self.subTest(sha256=C.sha(altered)), self.assertRaises(ValueError):
                C.restore_before(altered)

    def test_manifest_corruption_is_rejected(self):
        original = (HERE / 'host-delta.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / 'host-delta.json').write_bytes(original)
            with patch.object(C, 'HERE', target):
                self.assertEqual(C.restore_before(self.after), self.before)
                for altered in (original + b'\n', original.replace(b'9dfcd662', b'00000000')):
                    (target / 'host-delta.json').write_bytes(altered)
                    with self.assertRaises(ValueError):
                        C.restore_before(self.after)


if __name__ == '__main__':
    unittest.main()
