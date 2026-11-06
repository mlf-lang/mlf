#!/usr/bin/env python3
"""Focused static validator fault controls; no compiler, process suite or network."""
import copy
import unittest
from unittest.mock import patch
import migration_inventory as inventory


class MigrationInventoryControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = inventory.build()

    def assert_rejected(self, change):
        bad = copy.deepcopy(self.expected)
        change(bad)
        # Cache only immutable source reconstruction, not validation or mutations.
        with patch.object(inventory, 'build', return_value=self.expected):
            with self.assertRaises(ValueError):
                inventory.validate(bad)

    def test_valid_exact_inventory(self):
        with patch.object(inventory, 'build', return_value=self.expected):
            self.assertEqual(inventory.validate(self.expected)['records'], 577)

    def test_missing_record(self):
        self.assert_rejected(lambda x: x['entries'].pop())

    def test_duplicate_replaces_missing_at_equal_count(self):
        self.assert_rejected(lambda x: x['entries'].__setitem__(1, x['entries'][0]))

    def test_unknown_id(self):
        self.assert_rejected(lambda x: x['entries'][0].update(id='invented'))

    def test_blank_owner(self):
        self.assert_rejected(lambda x: x['entries'][0].update(owner=''))

    def test_unreviewed_role(self):
        self.assert_rejected(lambda x: x['entries'][0].update(review_status='pending'))

    def test_changed_source_hash(self):
        self.assert_rejected(lambda x: x['entries'][0]['evidence'][0].update(sha256='0'*64))

    def test_fabricated_source_excerpt(self):
        self.assert_rejected(lambda x: x['entries'][0]['evidence'][0].update(excerpt='invented proof'))

    def test_counterexample_cannot_execute(self):
        def change(x):
            next(e for e in x['entries'] if e['source'] == inventory.COUNTEREXAMPLE)['execution_policy'] = 'ALLOW_RUNTIME'
        self.assert_rejected(change)

    def test_publication_cannot_be_test(self):
        def change(x):
            next(e for e in x['entries'] if e['role'] == 'external-publication')['test_invocation_policy'] = 'execute'
        self.assert_rejected(change)

    def test_role_review_cannot_claim_qualification(self):
        self.assert_rejected(lambda x: x.update(qualification_complete=True))

    def test_source_registration_cannot_claim_execution(self):
        self.assert_rejected(lambda x: x['entries'][0].update(execution_verified=True))

    def test_external_path_duplicate_at_equal_count(self):
        self.assert_rejected(lambda x: x['external_paths'].__setitem__(1, x['external_paths'][0]))

    def test_fixture_same_name_does_not_merge(self):
        def change(x):
            x['asset_provenance'] = [a for a in x['asset_provenance'] if a['path'] != 'test/fixtures/figure12-a8.emlf']
        self.assert_rejected(change)

    def test_legacy_framework_dual_ownership_rejected(self):
        self.assert_rejected(lambda x: x['entries'][0].update(active_implementation=['legacy', 'framework']))

    def test_unknown_schema(self):
        self.assert_rejected(lambda x: x.update(schema_version=2))

    def test_extra_fields_rejected(self):
        self.assert_rejected(lambda x: x.update(pass_override=True))

    def test_baseline_pin_cannot_be_rewritten(self):
        with patch.object(inventory, 'FROZEN_INPUTS', {inventory.INVENTORY: '0'*64}):
            with self.assertRaisesRegex(ValueError, 'Frozen inventory changed'):
                inventory.build()


if __name__ == '__main__':
    unittest.main()
