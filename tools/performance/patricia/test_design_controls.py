#!/usr/bin/env python3
"""Failure reporting for the index design qualification."""
import copy
import unittest

import run_design_controls as D


class DesignIsolationTests(unittest.TestCase):
    def test_preparation_failure_preserves_stage_and_traceback(self):
        def failed():
            raise OSError('unreadable independent fixture')
        record=dict(complete=False,checks=[])
        saved=[]
        with self.assertRaisesRegex(OSError, 'unreadable independent fixture'):
            D.run_stage(record, lambda: saved.append(copy.deepcopy(record)), 'frozen-oracles', failed)
        self.assertEqual(len(saved),2)
        self.assertEqual(saved[-1]['stage'],'frozen-oracles')
        self.assertFalse(saved[-1]['complete'])
        self.assertIn('unreadable independent fixture',saved[-1]['error'])
        self.assertIn('Traceback',saved[-1]['traceback'])
        self.assertEqual(saved[-1]['checks'],[])


if __name__ == '__main__':
    unittest.main()
