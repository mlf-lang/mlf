#!/usr/bin/env python3
"""Reference-data controls; current source spelling is not an oracle contract."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import figure12_data as data


class Figure12Data(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / data.REFERENCE
        self.path.parent.mkdir(parents=True)
        self.raw = (data.ROOT / data.REFERENCE).read_bytes()
        self.reference = json.loads(self.raw)
        self.path.write_bytes(self.raw)

    def write(self, reference):
        self.path.write_text(json.dumps(reference))

    def test_independent_reference_inventory(self):
        fixture = data.decode(self.root)
        self.assertEqual(len(fixture['cases']), 43)
        self.assertEqual(len(fixture['type_checks']), 4)
        self.assertEqual(len(fixture['repairs']), 3)
        cases = fixture['cases']
        self.assertEqual([c['id'] for c in cases if not c['paper_acceptance']],
                         ['A11', 'C1a', 'C1c', 'E1a'])
        self.assertEqual([c['id'] for c in cases if not c['expected_acceptance']],
                         ['A8', 'A11', 'C1a', 'C1c', 'E1a'])
        self.assertEqual([c['id'] for c in cases if c['paper_acceptance'] != c['expected_acceptance']], ['A8'])
        index = {c['id']: c for c in cases}
        for alias, canonical in [('A12.1', 'A10.1'), ('E3a', 'A12.2')]:
            self.assertEqual(index[alias]['expression'], index[canonical]['expression'])
            self.assertEqual(index[alias]['local_signatures'], index[canonical]['local_signatures'])
        self.assertEqual(json.loads(json.dumps(fixture)), fixture)

    def test_current_implementation_is_not_read(self):
        expected = data.decode(self.root)
        # A source-only checkout is unnecessary. Even a malformed or renamed
        # native helper cannot alter this independent compiler input corpus.
        for name in ('Figure12.emlf', 'Figure12Suite.emlf', 'Helpers.emlf', 'Map.emlf', 'Set.emlf'):
            target = self.root / 'tests/Tests' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('-- harmless reformatting of maintained source\n')
        self.assertEqual(data.decode(self.root), expected)

    def test_json_layout_is_irrelevant_but_input_digest_is_current(self):
        before = data.decode(self.root)
        self.write(self.reference)
        after = data.decode(self.root)
        old_hashes = before.pop('fixture_sha256')
        new_hashes = after.pop('fixture_sha256')
        self.assertEqual(before, after)
        self.assertNotEqual(old_hashes, new_hashes)
        self.assertEqual(new_hashes, {str(data.REFERENCE): hashlib.sha256(self.path.read_bytes()).hexdigest()})

    def test_guest_expressions_remain_opaque_data(self):
        self.reference['cases'][0]['expression'] = 'unsafe-looking guest source: (panic 1)'
        self.write(self.reference)
        self.assertEqual(data.decode(self.root)['cases'][0]['expression'], 'unsafe-looking guest source: (panic 1)')

    def test_expected_type_is_loaded_not_recomputed(self):
        expected = ['XArrow', ['XBot'], ['XBot']]
        self.reference['type_checks'][0]['expected'] = expected
        self.write(self.reference)
        self.assertEqual(data.decode(self.root)['type_checks'][0]['expected'], expected)

    def test_type_case_ids_preserve_inputs_when_rows_or_labels_change(self):
        original = data.decode(self.root)['type_checks']
        self.reference['type_checks'].reverse()
        for check in self.reference['type_checks']:
            check['label'] = 'Updated display label'
        self.write(self.reference)
        reordered = data.decode(self.root)['type_checks']
        self.assertEqual([check['id'] for check in reordered],
                         ['A1-principal', 'A2-principal', 'A4-result', 'A4-signature'])
        for before, after in zip(original, reordered):
            self.assertEqual(after['source'], before['source'])
            self.assertEqual(after['expected'], before['expected'])
            self.assertEqual(after['label'], 'Updated display label')

    def test_duplicate_missing_or_unknown_type_case_id_fails(self):
        for identity in ('A2-principal', 'unknown', None):
            changed = copy.deepcopy(self.reference)
            if identity is None:
                del changed['type_checks'][0]['id']
            else:
                changed['type_checks'][0]['id'] = identity
            self.write(changed)
            with self.subTest(identity=identity), self.assertRaises(data.FixtureError):
                data.decode(self.root)

    def test_missing_malformed_and_duplicate_json_fail(self):
        self.path.unlink()
        with self.assertRaises(data.FixtureError):
            data.decode(self.root)
        for raw in (b'{', b'\xff', b'{"schema_version":1,"schema_version":1}'):
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                with self.assertRaises(data.FixtureError):
                    data.decode(self.root)

    def test_invalid_schema_and_missing_data_fail(self):
        for key, value in [('schema_version', 2), ('schema_version', True),
                           ('origin', {}), ('signatures', [['name']]),
                           ('cases', []), ('type_checks', []), ('repairs', [])]:
            with self.subTest(key=key, value=value):
                changed = dict(self.reference, **{key: value})
                self.write(changed)
                with self.assertRaises(data.FixtureError):
                    data.decode(self.root)
        for key in self.reference:
            changed = dict(self.reference)
            del changed[key]
            self.write(changed)
            with self.subTest(missing=key), self.assertRaises(data.FixtureError):
                data.decode(self.root)

    def test_case_identity_and_acceptance_corruption_fail(self):
        for key, value in [('id', 'A2'), ('expression', None),
                           ('paper_acceptance', False), ('expected_acceptance', False),
                           ('expected_acceptance', 1), ('local_signatures', [['x', 'Int'], ['x', 'Bool']])]:
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(self.reference)
                changed['cases'][0][key] = value
                self.write(changed)
                with self.assertRaises(data.FixtureError):
                    data.decode(self.root)

    def test_malformed_expected_type_fails(self):
        for expected in ([], ['XTyVar', 1], ['XArrow', ['XBot']],
                         ['XVar', ['XTyVar', 'wrong']], ['XVar', ['XTyVar', True]]):
            with self.subTest(expected=expected):
                changed = copy.deepcopy(self.reference)
                changed['type_checks'][0]['expected'] = expected
                self.write(changed)
                with self.assertRaises(data.FixtureError):
                    data.decode(self.root)


if __name__ == '__main__':
    unittest.main()
