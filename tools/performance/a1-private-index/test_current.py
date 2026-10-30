#!/usr/bin/env python3
"""Cheap fail-closed contract checks; these do not claim compiled A1 coverage."""
import importlib.util
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('current_a1', HERE / 'run_current_controls.py')
current = importlib.util.module_from_spec(spec)
spec.loader.exec_module(current)


class CurrentCompatibilityTests(unittest.TestCase):
    def producer(self):
        return {'optimization': '2', 'resolved_modules': dict.fromkeys(current.SHARED_HASHES),
                'inferred_shared_interfaces': dict.fromkeys(current.SHARED_HASHES),
                'shared_inputs': {name: {'sha256': digest} for name, digest in current.SHARED_HASHES.items()}}

    def test_current_exact_source_inventory(self):
        current.authenticate_current_source(self.producer())
        manifest = json.loads((ROOT / 'shared-sources.json').read_text())
        actual = {row['module']: current.sha(ROOT / row['path']) for row in manifest['modules']}
        self.assertEqual(actual, current.SHARED_HASHES)

    def test_source_and_literal_mutations_rejected(self):
        for module in ['Bootstrap.Map', 'Bootstrap.CrateSession', 'Bootstrap.X.Checked', 'MLF.BuiltinPreludeData']:
            producer = self.producer()
            producer['shared_inputs'][module]['sha256'] = '0' * 64
            with self.subTest(module=module), self.assertRaises(ValueError):
                current.authenticate_current_source(producer)

    def test_missing_extra_and_stale_inventory_rejected(self):
        for kind in ['missing', 'extra', 'stale', 'optimization']:
            producer = self.producer()
            if kind == 'missing':
                producer['inferred_shared_interfaces'].pop('Bootstrap.CrateSession')
            elif kind == 'extra':
                producer['resolved_modules']['Unexpected'] = None
            elif kind == 'stale':
                producer['shared_inputs'] = {n: {'sha256': s} for n, s in current.historical.SHARED_HASHES.items()}
            else:
                producer['optimization'] = '0'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                current.authenticate_current_source(producer)

    def test_frozen_oracles_and_historical_runner_unchanged(self):
        self.assertEqual(current.sha(HERE / 'run_controls.py'), current.compatibility['historical_runner_sha256'])
        current.verify({str(HERE / 'controls' / name): digest for name, digest in current.CONTROL_HASHES.items()})
        self.assertEqual(current.historical.BUILTIN_HASHES,
            {'.mlfci': 'e7e79d5aba844f4eeb426bb65c65a4a52831b5274df4bd217ced55a9703f099b',
             '.mlfco': '3d0e214228cb180d8cee9fb3fd21c5ec6abd8348e1ddd131517831d1f5c2d799'})
        self.assertIn("a1source / 'tools/performance/a1-private-index/run_controls.py'", (HERE / 'reproduce.py').read_text())
        self.assertIn("HERE / 'run_current_controls.py'", (HERE / 'check_integrated.py').read_text())

    def test_old_builtin_pair_rejected_not_relabelled(self):
        with patch.object(current, 'sha', lambda path: current.historical.BUILTIN_HASHES[Path(path).suffix]):
            with self.assertRaisesRegex(ValueError, 'historical builtin'):
                current.snapshot_builtin('/not-read/builtin')

    def test_observed_hashes_do_not_grant_builtin_admission(self):
        current.require_builtin_result(0, current.CURRENT_BUILTIN_STDOUT, b'')
        for code, stdout, stderr in [(1, current.CURRENT_BUILTIN_STDOUT, b''),
                (0, b'', b''), (0, current.CURRENT_BUILTIN_STDOUT, b'warning'),
                (0, b'PASS current builtin\n', b'')]:
            with self.subTest(code=code, stdout=stdout, stderr=stderr), self.assertRaises(ValueError):
                current.require_builtin_result(code, stdout, stderr)

    def test_missing_extra_current_fixture_rejected(self):
        manifest = json.loads((HERE / 'current/manifest.json').read_text())
        expected = current.current_fixture_pins(HERE / 'current', manifest)
        self.assertEqual(set(expected), {str(HERE / 'current/CurrentBuiltinControls.hs')})
        for bad in [{}, {**manifest, 'Unpinned.hs': '0' * 64}, {'../controls/FileMain.hs': '0' * 64}]:
            with self.subTest(manifest=bad), self.assertRaises(ValueError):
                current.current_fixture_pins(HERE / 'current', bad)

    def test_current_builtin_control_is_pinned_and_has_fixed_oracle(self):
        manifest = json.loads((HERE / 'current/manifest.json').read_text())
        current.verify({str(HERE / 'current' / name): digest for name, digest in manifest.items()})
        code = (HERE / 'current/CurrentBuiltinControls.hs').read_text()
        for required in ['Literal.rawPrelude Canonical.builtin', 'Check.checkClosed (C.rawTerm raw)',
                         'C.checkCompilerPrelude raw', 'A.encodeInterface iface', 'A.encodeObject object',
                         'A.fragmentData linked', 'A.fragmentBindings linked', 'A.fragmentSerial linked']:
            self.assertIn(required, code)
        self.assertEqual(code.count('reject "'), 7)
        self.assertIn("require_builtin_result(code, so, se)", (HERE / 'run_current_controls.py').read_text())

    def test_cf39_transition_preserves_previous_anchor_and_other_inputs(self):
        self.assertEqual(current.sha(current.COMPATIBILITY), current.COMPATIBILITY_SHA256)
        self.assertEqual(current.sha(current.MIGRATION), current.MIGRATION_SHA256)
        result = current.migrate_source_hashes(current.PREVIOUS_SHARED_HASHES,
                                               current.migration, current.COMPATIBILITY_SHA256)
        self.assertEqual(result, current.CF39_SHARED_HASHES)
        self.assertEqual(len(result), 126)
        self.assertEqual({name for name in result
                          if result[name] != current.PREVIOUS_SHARED_HASHES[name]},
                         current.MIGRATED_MODULES)
        self.assertEqual(len(set(result) - current.MIGRATED_MODULES), 120)
        self.assertEqual(len(current.compatibility['changed_shared_inputs']), 15)
        self.assertEqual(len(current.compatibility['added_shared_inputs']), 3)

    def test_each_cf39_input_is_required_and_not_stale(self):
        for name in sorted(current.MIGRATED_MODULES):
            for mutation in ('missing', 'zero', 'previous'):
                producer = self.producer()
                if mutation == 'missing':
                    producer['shared_inputs'].pop(name)
                else:
                    producer['shared_inputs'][name]['sha256'] = (
                        '0' * 64 if mutation == 'zero' else current.PREVIOUS_SHARED_HASHES[name])
                with self.subTest(module=name, mutation=mutation), self.assertRaises(ValueError):
                    current.authenticate_current_source(producer)
        producer = self.producer()
        producer['shared_inputs'] = {name: {'sha256': digest}
                                    for name, digest in current.PREVIOUS_SHARED_HASHES.items()}
        with self.assertRaises(ValueError):
            current.authenticate_current_source(producer)

    def test_exact_resolved_and_inferred_keysets(self):
        for field in ('resolved_modules', 'inferred_shared_interfaces'):
            for mutation in ('missing', 'extra', 'same_count_wrong_name'):
                producer = self.producer()
                if mutation != 'extra':
                    producer[field].pop('Bootstrap.BuiltinPreludeLiteral')
                if mutation != 'missing':
                    producer[field]['Unexpected'] = None
                with self.subTest(field=field, mutation=mutation), self.assertRaises(ValueError):
                    current.authenticate_current_source(producer)

    def test_cf39_migration_wrong_metadata_rejected(self):
        mutations = {
            'format': 'unreviewed', 'from_ref': '0' * 40, 'from_tree': '0' * 40,
            'to_ref': '0' * 40, 'to_tree': '0' * 40,
            'prior_compatibility_sha256': '0' * 64, 'module_count': 125,
            'unchanged_shared_input_count': 119, 'historical_changed_count': 15,
            'historical_added_count': 4, 'added_shared_inputs': {'Unexpected': '0' * 64},
            'removed_shared_inputs': ['Bootstrap.Map']}
        for key, replacement in mutations.items():
            value = copy.deepcopy(current.migration)
            value[key] = replacement
            with self.subTest(field=key), self.assertRaises(ValueError):
                current.migrate_source_hashes(current.PREVIOUS_SHARED_HASHES, value,
                                              current.COMPATIBILITY_SHA256)
        for mutation in ('missing_field', 'extra_field', 'wrong_base_anchor', 'wrong_base_input'):
            value, base = copy.deepcopy(current.migration), dict(current.PREVIOUS_SHARED_HASHES)
            digest = current.COMPATIBILITY_SHA256
            if mutation == 'missing_field':
                value.pop('module_count')
            elif mutation == 'extra_field':
                value['unexpected'] = True
            elif mutation == 'wrong_base_anchor':
                digest = '0' * 64
            else:
                base['Bootstrap.Map'] = '0' * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                current.migrate_source_hashes(base, value, digest)

    def test_cf39_migration_exact_delta_and_old_hashes(self):
        for name in sorted(current.MIGRATED_MODULES):
            for mutation in ('missing', 'wrong_old', 'same_as_old', 'zero_new', 'bad_hex', 'extra_row_key'):
                value = copy.deepcopy(current.migration)
                row = value['changed_shared_inputs'][name]
                if mutation == 'missing':
                    value['changed_shared_inputs'].pop(name)
                elif mutation == 'wrong_old':
                    row['old'] = '0' * 64
                elif mutation == 'same_as_old':
                    row['new'] = row['old']
                elif mutation == 'zero_new':
                    row['new'] = '0' * 64
                elif mutation == 'bad_hex':
                    row['new'] = 'z' * 64
                else:
                    row['extra'] = True
                with self.subTest(module=name, mutation=mutation), self.assertRaises(ValueError):
                    current.migrate_source_hashes(current.PREVIOUS_SHARED_HASHES, value,
                                                  current.COMPATIBILITY_SHA256)
        for mutation in ('extra', 'same_count_wrong_name'):
            value = copy.deepcopy(current.migration)
            row = value['changed_shared_inputs']['Bootstrap.BuiltinPreludeLiteral']
            if mutation == 'same_count_wrong_name':
                value['changed_shared_inputs'].pop('Bootstrap.BuiltinPreludeLiteral')
            value['changed_shared_inputs']['Unexpected'] = row
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                current.migrate_source_hashes(current.PREVIOUS_SHARED_HASHES, value,
                                              current.COMPATIBILITY_SHA256)

    def test_cf39_manifest_tamper_is_not_a_new_expected_snapshot(self):
        raw = current.MIGRATION.read_bytes()
        self.assertEqual(current.parse_migration(raw), current.migration)
        altered = copy.deepcopy(current.migration)
        altered['changed_shared_inputs']['Bootstrap.BuiltinPreludeLiteral']['new'] = '1' * 64
        for mutation in (raw + b' ', json.dumps(altered).encode(), b'{}'):
            with self.subTest(mutation_bytes=len(mutation)), self.assertRaises(ValueError):
                current.parse_migration(mutation)

    def test_query_v6_source_delta_is_exact_and_previous_anchors_survive(self):
        raw = current.QUERY_MIGRATION.read_bytes()
        result = current.query_source_hashes(current.CF39_SHARED_HASHES, raw)
        self.assertEqual(result, current.SHARED_HASHES)
        self.assertEqual({name for name in result if result[name] != current.CF39_SHARED_HASHES[name]},
                         {'Bootstrap.CrateQuery'})
        self.assertEqual(current.sha(current.MIGRATION), current.MIGRATION_SHA256)
        for base, text in [(current.CF39_SHARED_HASHES, raw + b' '),
                           (current.CF39_SHARED_HASHES, b'{}'),
                           (current.PREVIOUS_SHARED_HASHES, raw),
                           ({**current.CF39_SHARED_HASHES, 'Bootstrap.Map': '0' * 64}, raw)]:
            with self.subTest(size=len(text)), self.assertRaises(ValueError):
                current.query_source_hashes(base, text)

    def test_query_v6_rejects_stale_source_for_each_changed_module(self):
        for name in ['Bootstrap.CrateQuery']:
            producer = self.producer()
            producer['shared_inputs'][name]['sha256'] = current.CF39_SHARED_HASHES[name]
            with self.subTest(module=name), self.assertRaises(ValueError):
                current.authenticate_current_source(producer)


if __name__ == '__main__':
    unittest.main()
