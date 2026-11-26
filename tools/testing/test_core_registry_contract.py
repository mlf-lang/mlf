#!/usr/bin/env python3
"""Authenticate the runtime descriptor oracle without inspecting live source."""
import copy
import json
import unittest

import check_core_leaf_migration as audit


class CoreRegistryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = audit.expected_bindings()
        cls.contract = json.loads((audit.ROOT / audit.CASE_CONTRACT).read_text())

    def test_reviewed_descriptor_contract(self):
        audit.verify_case_contract(self.contract, self.expected)
        self.assertEqual(len(self.contract['cases']), 759)
        self.assertEqual(self.contract['cases'][0], {
            'id': 'core/substring-adapter/empty-in-empty',
            'name': 'substring empty-in-empty', 'family': 'core/substring-adapter'})

    def test_renamed_id_label_and_moved_family_are_rejected(self):
        for key, value in [('id', 'core/substring-adapter/renamed'),
                           ('name', 'changed independent label'),
                           ('family', 'core/optimizer-uses')]:
            with self.subTest(key=key):
                contract = copy.deepcopy(self.contract)
                contract['cases'][0][key] = value
                with self.assertRaises(ValueError):
                    audit.verify_case_contract(contract, self.expected)

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
                    rows[0], rows[1] = rows[1], rows[0]
                with self.assertRaises(ValueError):
                    audit.verify_case_contract(contract, self.expected)

    def test_schema_and_unknown_fields_are_rejected(self):
        for extra in ({'schema_version': True}, {'schema_version': 2},
                      {'cases': None}, {'unexpected': 'metadata'}):
            with self.subTest(extra=extra):
                contract = copy.deepcopy(self.contract)
                contract.update(extra)
                with self.assertRaises(ValueError):
                    audit.verify_case_contract(contract, self.expected)


if __name__ == '__main__':
    unittest.main()
