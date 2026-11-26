#!/usr/bin/env python3
"""Independent design fixture loading and retained failure reporting."""
import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import run_design_controls as D


class DesignIsolationTests(unittest.TestCase):
    def test_reference_loading_works_without_git(self):
        with mock.patch.object(subprocess, 'check_output', side_effect=AssertionError('Git unavailable')):
            actual = D.load_design_oracles()
        self.assertEqual(set(actual), set(D.DESIGN_ORACLES))
        self.assertTrue(all(actual.values()))

    def test_missing_or_changed_reference_is_rejected(self):
        for name in D.DESIGN_ORACLES:
            for missing in (True, False):
                with self.subTest(name=name, missing=missing), tempfile.TemporaryDirectory() as tmp:
                    directory=Path(tmp)
                    for fixture in D.DESIGN_ORACLES:
                        shutil.copyfile(D.DESIGN_DIRECTORY/fixture, directory/fixture)
                    path=directory/name
                    if missing:
                        path.unlink()
                    else:
                        path.write_bytes(path.read_bytes()+b'changed reference')
                    with self.assertRaises((RuntimeError, FileNotFoundError)):
                        D.load_design_oracles(directory)

    def test_preparation_failure_preserves_stage_and_traceback(self):
        def failed():
            raise OSError('unreadable independent fixture')
        record=dict(complete=False,checks=[])
        saved=[]
        with self.assertRaisesRegex(OSError, 'unreadable independent fixture'):
            D.run_stage(record, lambda: saved.append(copy.deepcopy(record)), 'load-independent-dependencies', failed)
        self.assertEqual(len(saved),2)
        self.assertEqual(saved[-1]['stage'],'load-independent-dependencies')
        self.assertFalse(saved[-1]['complete'])
        self.assertIn('unreadable independent fixture',saved[-1]['error'])
        self.assertIn('Traceback',saved[-1]['traceback'])
        self.assertEqual(saved[-1]['checks'],[])


if __name__ == '__main__':
    unittest.main()
