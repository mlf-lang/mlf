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
        self.assertEqual(set(expected), {str(HERE / 'current' / name)
                                         for name in current.CURRENT_SOURCE_HASHES})
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
        self.assertEqual(result, current.QUERY_SHARED_HASHES)
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
    def test_c4_chain_has_only_three_authored_source_changes(self):
        self.assertEqual(current.sha(current.C4_MIGRATION), current.C4_MIGRATION_SHA256)
        self.assertEqual(current.parse_c4_migration(current.C4_MIGRATION.read_bytes()), current.c4_migration)
        result = current.migrate_c4_source_hashes(current.QUERY_SHARED_HASHES,
                                                current.c4_migration, current.QUERY_MIGRATION_SHA256)
        self.assertEqual(result, current.C4_SHARED_HASHES)
        self.assertEqual({name for name in result if result[name] != current.QUERY_SHARED_HASHES[name]},
                         set(current.C4_NEW_HASHES))
        self.assertEqual(len(result), 126)
        self.assertEqual(len(set(result) - set(current.C4_NEW_HASHES)), 123)
        for name in ['Bootstrap.CrateSession', 'Bootstrap.Graph.IndexStore']:
            self.assertEqual(result[name], current.historical.SHARED_HASHES[name])

    def test_c4_migration_rejects_every_metadata_change_and_bad_base(self):
        for name in set(current.c4_migration) - {'changed_shared_inputs'}:
            for replacement in (None, 'unreviewed'):
                value = copy.deepcopy(current.c4_migration)
                value[name] = replacement
                with self.subTest(field=name, replacement=replacement), self.assertRaises(ValueError):
                    current.migrate_c4_source_hashes(current.QUERY_SHARED_HASHES, value,
                                                    current.QUERY_MIGRATION_SHA256)
        for kind in ('missing_field', 'extra_field', 'wrong_prior_digest', 'wrong_base'):
            value, base, digest = copy.deepcopy(current.c4_migration), dict(current.QUERY_SHARED_HASHES), current.QUERY_MIGRATION_SHA256
            if kind == 'missing_field':
                value.pop('parent_ref')
            elif kind == 'extra_field':
                value['extra'] = True
            elif kind == 'wrong_prior_digest':
                digest = current.COMPATIBILITY_SHA256
            else:
                base['Bootstrap.Map'] = '0' * 64
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                current.migrate_c4_source_hashes(base, value, digest)

    def test_c4_exact_delta_and_all_old_new_hashes_required(self):
        for name in current.C4_NEW_HASHES:
            for kind in ('missing', 'wrong_old', 'wrong_new', 'same_as_old', 'extra_row_key'):
                value = copy.deepcopy(current.c4_migration)
                row = value['changed_shared_inputs'][name]
                if kind == 'missing':
                    value['changed_shared_inputs'].pop(name)
                elif kind == 'wrong_old':
                    row['old'] = '0' * 64
                elif kind == 'wrong_new':
                    row['new'] = '1' * 64
                elif kind == 'same_as_old':
                    row['new'] = row['old']
                else:
                    row['extra'] = True
                with self.subTest(module=name, kind=kind), self.assertRaises(ValueError):
                    current.migrate_c4_source_hashes(current.QUERY_SHARED_HASHES, value,
                                                    current.QUERY_MIGRATION_SHA256)
        for kind in ('extra', 'same_count_wrong_name'):
            value = copy.deepcopy(current.c4_migration)
            row = value['changed_shared_inputs']['Bootstrap.Constraint']
            if kind == 'same_count_wrong_name':
                value['changed_shared_inputs'].pop('Bootstrap.Constraint')
            value['changed_shared_inputs']['Unexpected'] = row
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                current.migrate_c4_source_hashes(current.QUERY_SHARED_HASHES, value,
                                                current.QUERY_MIGRATION_SHA256)

    def test_c4_manifest_byte_mutation_cannot_define_a_new_expectation(self):
        raw = current.C4_MIGRATION.read_bytes()
        for altered in (raw + b' ', b'{}', raw.replace(b'123', b'122', 1)):
            with self.subTest(length=len(altered)), self.assertRaises(ValueError):
                current.parse_c4_migration(altered)

    def test_each_c4_source_stale_missing_or_wrong_hash_rejected(self):
        for name in current.C4_NEW_HASHES:
            for kind in ('missing', 'zero', 'prior'):
                producer = self.producer()
                if kind == 'missing':
                    producer['shared_inputs'].pop(name)
                else:
                    producer['shared_inputs'][name]['sha256'] = (
                        '0' * 64 if kind == 'zero' else current.QUERY_SHARED_HASHES[name])
                with self.subTest(module=name, kind=kind), self.assertRaises(ValueError):
                    current.authenticate_current_source(producer)
        producer = self.producer()
        producer['shared_inputs'] = {name: {'sha256': digest}
                                    for name, digest in current.QUERY_SHARED_HASHES.items()}
        with self.assertRaises(ValueError):
            current.authenticate_current_source(producer)

    def test_c4_adapter_is_exactly_one_call_plus_one_import_and_inverse(self):
        adapter = current.load_c4_adapter(HERE / 'current')
        original = (HERE / 'controls/SessionTests.hs').read_bytes()
        adapted = adapter.adapt_session(original)
        self.assertEqual(adapted, original.replace(adapter.OLD_IMPORT, adapter.NEW_IMPORT)
                                          .replace(adapter.OLD_CALL, adapter.NEW_CALL))
        self.assertEqual(adapter.restore_session(adapted), original)
        self.assertEqual(adapted.count(b'C4.checkTransactionalOutcome('), 1)
        self.assertIn(b'checkOutcome(label++"/private closed final route")False expected(N.solvePrepared input)', adapted)
        self.assertEqual((HERE / 'controls/SessionTests.hs').read_bytes(), original)
        with self.assertRaises(ValueError):
            adapter.adapt_session(adapted)

    def test_c4_adapter_rejects_changed_original_and_ambiguous_sites(self):
        adapter = current.load_c4_adapter(HERE / 'current')
        original = (HERE / 'controls/SessionTests.hs').read_bytes()
        for altered in (original+b' ', original.replace(adapter.OLD_IMPORT,b''),
                        original.replace(adapter.OLD_CALL,b''), original+adapter.OLD_CALL,
                        original+adapter.OLD_IMPORT,
                        original.replace(b'False expected(N.solvePrepared input)',b'True expected(N.solvePrepared input)')):
            with self.subTest(length=len(altered)), self.assertRaises(ValueError):
                adapter.adapt_session(altered)

    def test_c4_inverse_rejects_extra_changes_private_edits_and_weaker_comparison(self):
        adapter = current.load_c4_adapter(HERE / 'current')
        original = (HERE / 'controls/SessionTests.hs').read_bytes()
        adapted = adapter.adapt_session(original)
        for altered in (adapted+b' ', adapted+adapter.NEW_CALL, adapted+adapter.NEW_IMPORT,
                        adapted.replace(adapter.NEW_CALL, adapter.OLD_CALL),
                        adapted.replace(adapter.NEW_CALL, adapter.OLD_CALL.replace(b'True',b'False')),
                        adapted.replace(b'False expected(N.solvePrepared input)',b'True expected(N.solvePrepared input)'),
                        adapted.replace(b'/delayed P0',b'/modified P0')):
            with self.subTest(length=len(altered)), self.assertRaises(ValueError):
                adapter.restore_session(altered)

    def test_c4_complete_transaction_oracle_is_only_module_renamed(self):
        adapter = current.load_c4_adapter(HERE / 'current')
        raw = (HERE / 'current/CurrentC4TransactionOracle.hs').read_bytes()
        original = adapter.verify_transaction_oracle(raw)
        self.assertEqual(adapter.digest(original), adapter.FROZEN_ORACLE_SHA256)
        for before, after in [(b'O.sameGraphPhysical',b'O.sameGraphLogical'),
                              (b'O.sameScopesPhysical',b'O.sameScopesLogical'),
                              (b'FS.finish value',b'T.Right graph'),
                              (b'O.validSolverMaps value',b'True'),
                              (b'FG.validateGraph graph',b'T.Right ()'),
                              (b'G.validateGraph graph',b'T.Right ()'),
                              (b'== O.indexOracle',b'/= O.indexOracle')]:
            self.assertIn(before, raw)
            with self.subTest(before=before), self.assertRaises(ValueError):
                adapter.verify_transaction_oracle(raw.replace(before,after))
        for malformed in (raw+b' ', raw+adapter.NEW_ORACLE_HEADER, original):
            with self.assertRaises(ValueError):
                adapter.verify_transaction_oracle(malformed)

    def test_c4_adapter_and_native_controls_have_fixed_manifest_pins(self):
        manifest = json.loads((HERE / 'current/manifest.json').read_text())
        self.assertEqual(manifest, current.CURRENT_SOURCE_HASHES)
        for name in manifest:
            altered = dict(manifest)
            altered[name] = '0' * 64
            with self.subTest(name=name), self.assertRaises(ValueError):
                current.current_fixture_pins(HERE / 'current', altered)
        with patch.object(current,'sha',return_value='0'*64), self.assertRaises(ValueError):
            current.load_c4_adapter(HERE / 'current')
        raw = (HERE / 'current/CurrentC4OracleControls.hs').read_text()
        self.assertIn('(FS.prepare graph)',raw)
        self.assertIn('not (O.sameSolverPhysical old changed)',raw)
        self.assertIn('C4.checkTransactional "self size" parentCount parentCount',raw)
        self.assertIn('C4.checkTransactional "self bucket" binderBucket binderBucket',raw)
        self.assertIn(current.CURRENT_C4_STDOUT.decode().strip(), raw)

    def test_c4_exact_build_closures_and_post_copy_inverse_are_wired(self):
        code = (HERE / 'run_current_controls.py').read_text()
        for expected in ["build_driver('CurrentBuiltinControls', {'CurrentBuiltinControls'})",
                         "build_driver('SessionTests', TEST_MODULES | {'CurrentC4TransactionOracle'})",
                         "build_driver('CurrentC4OracleControls', {'CurrentC4OracleControls'})",
                         "contract['module_sources']['SessionTests'] = str(session_copy)",
                         "len(rows) == len(expected) and actual == expected",
                         "so == CURRENT_C4_STDOUT and se == b''",
                         "'post-control frozen session inverse'",
                         "receipt['c4_comparator_rejections'] = 13"]:
            self.assertIn(expected,code)


    def test_composed_migration_rejects_skipped_reversed_and_repeated_stages(self):
        for base, digest in [
                (current.CF39_SHARED_HASHES, current.QUERY_MIGRATION_SHA256),
                (current.PREVIOUS_SHARED_HASHES, current.QUERY_MIGRATION_SHA256),
                (current.historical.SHARED_HASHES, current.QUERY_MIGRATION_SHA256),
                (current.SHARED_HASHES, current.QUERY_MIGRATION_SHA256),
                (current.QUERY_SHARED_HASHES, current.MIGRATION_SHA256),
                (current.QUERY_SHARED_HASHES, current.COMPATIBILITY_SHA256)]:
            with self.subTest(base=base.get('Bootstrap.CrateQuery'), digest=digest), self.assertRaises(ValueError):
                current.migrate_c4_source_hashes(base, current.c4_migration, digest)
        for base in (current.QUERY_SHARED_HASHES, current.SHARED_HASHES):
            with self.subTest(stage='query repeated or after C4'), self.assertRaises(ValueError):
                current.query_source_hashes(base, current.QUERY_MIGRATION.read_bytes())

    def test_final_inventory_rejects_old_c4_and_uncomposed_query_producers(self):
        old_c4 = {**current.CF39_SHARED_HASHES, **current.C4_NEW_HASHES}
        for snapshot in (old_c4, current.QUERY_SHARED_HASHES, current.CF39_SHARED_HASHES,
                         current.PREVIOUS_SHARED_HASHES):
            producer = self.producer()
            producer['shared_inputs'] = {name: {'sha256': digest} for name, digest in snapshot.items()}
            with self.subTest(query=snapshot['Bootstrap.CrateQuery'],
                              solver=snapshot['Bootstrap.Graph.Solver']), self.assertRaises(ValueError):
                current.authenticate_current_source(producer)
        self.assertEqual(current.SHARED_HASHES['Bootstrap.CrateQuery'],
                         current.QUERY_SHARED_HASHES['Bootstrap.CrateQuery'])
        self.assertNotEqual(current.SHARED_HASHES['Bootstrap.CrateQuery'],
                            current.CF39_SHARED_HASHES['Bootstrap.CrateQuery'])
        self.assertEqual({name for name in current.C4_SHARED_HASHES
                          if current.C4_SHARED_HASHES[name] != current.CF39_SHARED_HASHES[name]},
                         set(current.C4_NEW_HASHES) | {'Bootstrap.CrateQuery'})
        self.assertEqual({name for name in current.SHARED_HASHES
                          if current.SHARED_HASHES[name] != current.CF39_SHARED_HASHES[name]},
                         set(current.C4_NEW_HASHES) |
                         {'Bootstrap.CrateQuery', 'Bootstrap.Map', 'Bootstrap.CrateSession'})

    def test_composed_migration_pins_and_receipt_bind_all_stages(self):
        self.assertEqual(current.c4_migration['parent_ref'],
                         'd96f67726599fa4e21f236462886106434c8e417')
        self.assertEqual(current.c4_migration['prior_cf39_migration_sha256'], current.MIGRATION_SHA256)
        self.assertEqual(current.c4_migration['prior_migration_sha256'], current.QUERY_MIGRATION_SHA256)
        code = (HERE / 'run_current_controls.py').read_text()
        for constant in ('COMPATIBILITY', 'MIGRATION', 'QUERY_MIGRATION', 'C4_MIGRATION'):
            self.assertIn('str(' + constant + '): ' + constant + '_SHA256', code)
        for key, constant in [('source_compatibility_sha256', 'COMPATIBILITY'),
                              ('source_migration_sha256', 'MIGRATION'),
                              ('query_source_migration_sha256', 'QUERY_MIGRATION'),
                              ('c4_source_migration_sha256', 'C4_MIGRATION')]:
            self.assertIn(key + '=sha(' + constant + ')', code)



    def test_balance_source_delta_preserves_old_anchors_and_other_inputs(self):
        raw = current.BALANCE_MIGRATION.read_bytes()
        result = current.balance_source_hashes(current.C4_SHARED_HASHES, raw)
        self.assertEqual(result, current.BALANCE_SHARED_HASHES)
        self.assertEqual({n for n in result if result[n] != current.C4_SHARED_HASHES[n]},
                         {'Bootstrap.Map', 'MLF.BuiltinPreludeData'})
        self.assertEqual(current.sha(current.C4_MIGRATION), current.C4_MIGRATION_SHA256)
        self.assertEqual(len(result), 126)

    def test_balance_source_migration_tamper_and_wrong_base_rejected(self):
        raw = current.BALANCE_MIGRATION.read_bytes()
        for base, value in [(current.C4_SHARED_HASHES, raw + b' '),
                            (current.C4_SHARED_HASHES, b'{}'),
                            (current.CF39_SHARED_HASHES, raw),
                            ({**current.C4_SHARED_HASHES, 'Bootstrap.Map': '0' * 64}, raw)]:
            with self.subTest(length=len(value)), self.assertRaises(ValueError):
                current.balance_source_hashes(base, value)

    def test_balance_rejects_each_previous_source_hash(self):
        for name in ['Bootstrap.Map', 'MLF.BuiltinPreludeData']:
            producer = self.producer()
            producer['shared_inputs'][name]['sha256'] = current.C4_SHARED_HASHES[name]
            with self.subTest(module=name), self.assertRaises(ValueError):
                current.authenticate_current_source(producer)

    def test_validation_reuse_preserves_every_other_source_and_frozen_owner(self):
        contract = current.validation_contract
        self.assertEqual(contract.source_hashes(current.BALANCE_SHARED_HASHES), current.SHARED_HASHES)
        self.assertEqual({n for n in current.SHARED_HASHES
                          if current.SHARED_HASHES[n] != current.BALANCE_SHARED_HASHES[n]},
                         {'Bootstrap.CrateSession'})
        restored = contract.restore_previous_owner((ROOT / contract.OWNER).read_bytes())
        self.assertEqual(contract.sha(restored), current.historical.OWNER_SHA)
        producer = self.producer()
        producer['shared_inputs']['Bootstrap.CrateSession']['sha256'] = contract.OLD_OWNER_SHA
        with self.assertRaises(ValueError):
            current.authenticate_current_source(producer)


if __name__ == '__main__':
    unittest.main()
