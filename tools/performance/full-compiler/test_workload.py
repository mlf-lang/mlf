#!/usr/bin/env python3
"""Fail-closed inventory checks for changing complete compiler closures."""
from pathlib import Path
import copy
import importlib.util
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('complete_qualifier', HERE / 'qualify.py')
Q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(Q)


def workload(count):
    rows = [dict(module=f'Target.M{i}', source=f'/source/M{i}.hs',
                 sha256=f'{i:064x}', bytes=i + 1) for i in range(count)]
    return dict(format='full-emlf-source-closure-v1', entry='MLF.Entry.Emlf',
                modules=rows, module_count=count,
                input_files={r['source']: r['sha256'] for r in rows},
                source_bytes=sum(r['bytes'] for r in rows),
                nonshared_imports=['MLF.Primitive'])


class CompleteInventory(unittest.TestCase):
    def test_historical_and_current_sizes_are_not_semantic_constants(self):
        for count in [81, 90]:
            self.assertEqual(Q.validate_inventory(workload(count)), count)

    def test_invalid_count(self):
        for count in [0, -1, True, 89, 91]:
            w = workload(90); w['module_count'] = count
            with self.subTest(count=count), self.assertRaises(ValueError):
                Q.validate_inventory(w)

    def test_duplicate_module_or_source(self):
        for field in ['module', 'source']:
            w = workload(90); w['modules'][1][field] = w['modules'][0][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                Q.validate_inventory(w)

    def test_missing_extra_or_disagreeing_source_pin(self):
        for kind in ['missing', 'extra', 'changed']:
            w = workload(90)
            if kind == 'missing': del w['input_files']['/source/M0.hs']
            elif kind == 'extra': w['input_files']['/source/Other.hs'] = '0' * 64
            else: w['input_files']['/source/M0.hs'] = 'f' * 64
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                Q.validate_inventory(w)

    def test_wrong_bytes_format_entry_or_external_imports(self):
        for key, value in [('source_bytes', 1), ('format', 'other'),
                           ('entry', 'Other.Main'), ('nonshared_imports', [])]:
            w = workload(90); w[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                Q.validate_inventory(w)

    def test_validation_is_read_only(self):
        w = workload(90); expected = copy.deepcopy(w)
        Q.validate_inventory(w)
        self.assertEqual(w, expected)


if __name__ == '__main__':
    unittest.main()
