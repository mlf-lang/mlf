#!/usr/bin/env python3
"""Finite source-custody negatives; no GHC/native or acceptance claims."""
import copy
import json
from pathlib import Path
import types
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
path = HERE / 'resource_source_migration.py'
migration = types.ModuleType('resource_source_migration_under_test')
migration.__file__ = str(path)
exec(compile(path.read_bytes(), str(path), 'exec'), migration.__dict__)


class ResourceSourceMigrationTests(unittest.TestCase):
    def setUp(self):
        self.raw = migration.MANIFEST.read_bytes()
        self.value = migration.parse_transition(self.raw)
        self.expected = migration.validate_transition(self.value)
        self.rows = [{key: row[key] for key in ('module', 'path', 'role')}
                     for row in self.expected]
        self.hashes = {row['module']: row['sha256'] for row in self.expected}
        self.base = {row['module']: row['sha256']
                     for row in self.value['target_snapshot']['modules']}

    def reject_inventory(self, rows=None, hashes=None):
        with self.assertRaises(ValueError):
            migration.authenticate_inventory(
                self.rows if rows is None else rows,
                self.hashes if hashes is None else hashes)

    def test_exact_complete_current_source_and_old_chain_endpoint(self):
        self.assertEqual(migration.migrate(self.base), self.hashes)
        self.assertEqual(migration.authenticate_current_source(ROOT, self.base), self.hashes)
        self.assertEqual(len(self.rows), 132)
        self.assertEqual([self.rows[index]['module'] for index in (1, 2, 3, 131)],
                         [row[1] for row in migration.ADDITIONS])

    def test_each_changed_and_added_actual_source_hash_is_required(self):
        names = migration.CHANGED | {row[1] for row in migration.ADDITIONS}
        for name in sorted(names):
            for mutation in ('zero', 'missing', 'other-valid', 'old'):
                bad = dict(self.hashes)
                if mutation == 'missing':
                    bad.pop(name)
                else:
                    bad[name] = (self.base.get(name, '1' * 64) if mutation == 'old'
                                 else '0' * 64 if mutation == 'zero' else 'f' * 64)
                self.assertNotEqual(bad, self.hashes)
                with self.subTest(name=name, mutation=mutation):
                    self.reject_inventory(hashes=bad)

    def test_every_unchanged_owner_is_also_bound(self):
        for name in sorted(set(self.base) - migration.CHANGED):
            bad = dict(self.hashes)
            bad[name] = '0' * 64
            with self.subTest(name=name):
                self.reject_inventory(hashes=bad)

    def test_missing_extra_duplicate_and_reordered_rows_reject(self):
        cases = {
            'missing': self.rows[:-1],
            'extra': self.rows + [{'module': 'Unexpected', 'path': 'bad.hs', 'role': 'implementation'}],
            'duplicate': [self.rows[0], *self.rows[:-1]],
            'reordered': [self.rows[1], self.rows[0], *self.rows[2:]],
            'same-count-alias': [self.rows[0], self.rows[0], *self.rows[2:]],
        }
        for name, rows in cases.items():
            with self.subTest(name=name):
                self.reject_inventory(rows=rows)

    def test_every_new_and_changed_path_and_role_are_bound(self):
        names = migration.CHANGED | {row[1] for row in migration.ADDITIONS}
        for index, row in enumerate(self.rows):
            if row['module'] not in names:
                continue
            for key, replacement in [('path', '../escaping.hs'), ('role', 'direct-test'),
                                     ('module', 'Unexpected')]:
                bad = copy.deepcopy(self.rows)
                bad[index][key] = replacement
                with self.subTest(name=row['module'], field=key):
                    self.reject_inventory(rows=bad)

    def test_partial_stale_extra_and_wrong_target_inputs_reject(self):
        cases = [dict(self.base), dict(self.base), dict(self.base), {}, dict(self.hashes)]
        cases[0].pop('Bootstrap.Module')
        cases[1]['Bootstrap.Module'] = '0' * 64
        cases[2]['Unexpected'] = '1' * 64
        for index, value in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                migration.migrate(value)
        self.reject_inventory(hashes=self.base)

    def test_raw_manifest_bytes_are_not_a_new_expected_snapshot(self):
        for raw in (self.raw + b' ', b'{}', b'', self.raw.replace(b'132', b'133', 1)):
            self.assertNotEqual(raw, self.raw)
            with self.subTest(raw_length=len(raw)), self.assertRaises(ValueError):
                migration.parse_transition(raw)
        value = copy.deepcopy(self.value)
        value['changed_modules'][0]['new'] = '1' * 64
        with self.assertRaises(ValueError):
            migration.parse_transition(json.dumps(value, sort_keys=True).encode())

    def test_transition_schema_metadata_anchor_and_all_ordered_rows_replay(self):
        mutators = {
            'wrong-target': lambda x: x.update(from_commit='0' * 40),
            'wrong-tree': lambda x: x.update(from_tree='0' * 40),
            'wrong-plan': lambda x: x.update(integration_plan_sha256='0' * 64),
            'wrong-snapshot-digest': lambda x: x.update(target_snapshot_sha256='0' * 64),
            'wrong-base-byte': lambda x: x['target_snapshot']['modules'][0].update(sha256='1' * 64),
            'wrong-count': lambda x: x.update(module_count=131),
            'bool-count': lambda x: x.update(module_count=True),
            'wrong-unchanged': lambda x: x.update(unchanged_shared_input_count=123),
            'extra-schema': lambda x: x.update(unexpected=True),
            'missing-schema': lambda x: x.pop('changed_modules'),
            'missing-change': lambda x: x['changed_modules'].pop(),
            'extra-change': lambda x: x['changed_modules'].append(x['changed_modules'][0]),
            'reorder-change': lambda x: x['changed_modules'].reverse(),
            'old-hash': lambda x: x['changed_modules'][0].update(old='1' * 64),
            'same-hash': lambda x: x['changed_modules'][0].update(new=x['changed_modules'][0]['old']),
            'addition-position': lambda x: x['added_modules'][0].update(index=2),
            'addition-path': lambda x: x['added_modules'][0].update(path='wrong.hs'),
            'addition-role': lambda x: x['added_modules'][0].update(role='direct-test'),
            'reorder-addition': lambda x: x['added_modules'].reverse(),
            'destination-missing': lambda x: x['destination_modules'].pop(),
            'destination-reorder': lambda x: x['destination_modules'].reverse(),
            'destination-prune': lambda x: x['destination_modules'][0].pop('role'),
        }
        for name, change in mutators.items():
            bad = copy.deepcopy(self.value)
            change(bad)
            self.assertNotEqual(bad, self.value)
            with self.subTest(name=name), self.assertRaises(ValueError):
                migration.validate_transition(bad)


if __name__ == '__main__':
    unittest.main()
