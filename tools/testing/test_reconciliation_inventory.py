#!/usr/bin/env python3
"""Historical census vs current source fault controls; no builds or network."""
import tempfile
import unittest
from pathlib import Path
import check_reconciliation_inventory as audit


class ReconciliationInventoryControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        import json
        raw = audit.RECORD.read_bytes()
        value = json.loads(raw)
        paths = set(audit.EXPECTED) | set(value['preserved_inputs']) | {str(audit.RECORD.relative_to(audit.ROOT))}
        for path in paths:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((audit.ROOT / path).read_bytes())

    def test_follow_on_change_not_historical_identity_or_validation(self):
        path = '.github/workflows/ci.yml'
        with (self.root / path).open('a') as stream:
            stream.write('\n# unvalidated follow-on\n')
        result = audit.validate(self.root)
        row = next(x for x in result['current_sources'] if x['path'] == path)
        self.assertTrue(row['differs_from_historical'])
        self.assertFalse(row['current_validation_verified'])
        self.assertFalse(result['current_validation_verified'])
        self.assertTrue(row['required_follow_on_validation'])

    def test_forged_dated_census_rejected(self):
        with self.assertRaisesRegex(ValueError, 'dated census changed'):
            audit.validate(self.root, audit.RECORD.read_bytes() + b'\n')

    def test_frozen_input_change_rejected(self):
        path = 'tests/fixtures/async-gate/counterexample/incorrect-quantifier.emlf'
        (self.root / path).write_text('-- changed')
        with self.assertRaisesRegex(ValueError, 'unreviewed current source change'):
            audit.validate(self.root)

    def test_selector_change_requires_current_policy_validation(self):
        path = 'tools/release/async-change-scope.py'
        (self.root / path).write_text('print(False)')
        result = audit.validate(self.root)
        row = next(x for x in result['current_sources'] if x['path'] == path)
        self.assertTrue(row['differs_from_historical'])
        self.assertFalse(row['current_validation_verified'])
        self.assertEqual(row['required_follow_on_validation'],
                         'python3 tools/release/test-async-change-scope.py')


if __name__ == '__main__':
    unittest.main()
