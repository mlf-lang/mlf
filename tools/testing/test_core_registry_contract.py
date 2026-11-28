#!/usr/bin/env python3
"""Check current Core descriptors without historical source projections."""
import copy
import json
from pathlib import Path
import unittest

from core_registry_contract import verify_contract

ROOT = Path(__file__).resolve().parents[2]


class CoreRegistryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((ROOT / "tests/golden/core-registry-contract.json").read_text())
        cls.catalog = json.loads((ROOT / "tests/test-catalog.json").read_text())

    def test_current_public_descriptors_match_catalog(self):
        self.assertEqual(verify_contract(self.contract, self.catalog), self.contract['cases'])

    def test_renamed_id_label_and_moved_family_are_rejected(self):
        index = next(i for i, row in enumerate(self.contract['cases'])
                     if row['family'] != 'core/substring-adapter')
        for key, value in [('id', 'core/renamed/case'),
                           ('name', 'changed independent label'),
                           ('family', 'core/renamed')]:
            with self.subTest(key=key):
                contract = copy.deepcopy(self.contract)
                contract['cases'][index][key] = value
                with self.assertRaises(ValueError):
                    verify_contract(contract, self.catalog)

    def test_missing_duplicate_and_reordered_cases_are_rejected(self):
        for mutation in ('missing', 'duplicate', 'reordered'):
            with self.subTest(mutation=mutation):
                contract = copy.deepcopy(self.contract)
                rows = contract['cases']
                if mutation == 'missing':
                    rows.pop()
                elif mutation == 'duplicate':
                    rows[-1] = rows[0]
                else:
                    rows[-1], rows[-2] = rows[-2], rows[-1]
                with self.assertRaises(ValueError):
                    verify_contract(contract, self.catalog)

    def test_schema_and_unknown_fields_are_rejected(self):
        for extra in ({'schema_version': True}, {'schema_version': 2},
                      {'cases': None}, {'cases': []}, {'unexpected': 'metadata'}):
            with self.subTest(extra=extra):
                contract = copy.deepcopy(self.contract)
                contract.update(extra)
                with self.assertRaises(ValueError):
                    verify_contract(contract, self.catalog)

    def test_malformed_descriptors_are_rejected(self):
        for extra in ({'name': ''}, {'name': False}, {'family': 'other'},
                      {'id': 'core/substring-adapter/'}, {'unknown': 'field'}):
            with self.subTest(extra=extra):
                contract = copy.deepcopy(self.contract)
                contract['cases'][0].update(extra)
                with self.assertRaises(ValueError):
                    verify_contract(contract, self.catalog)

    def test_explicit_public_addition_needs_only_current_data(self):
        contract, catalog = copy.deepcopy(self.contract), copy.deepcopy(self.catalog)
        family = next(row for row in catalog['families']
                      if row['id'] == contract['cases'][-1]['family'])
        label = 'new explicit behavior case'
        family['evidence']['executions'].append(label)
        contract['cases'].append({'id': family['id'] + '/new-explicit-behavior-case',
                                  'name': label, 'family': family['id']})
        self.assertEqual(verify_contract(contract, catalog), contract['cases'])


if __name__ == '__main__':
    unittest.main()
