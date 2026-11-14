#!/usr/bin/env python3
"""Pure source/spec admission controls; never builds a compiler or native fixture."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('artifact_modular_actual', HERE / 'test_artifact_binary.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
parser = argparse.ArgumentParser()
parser.add_argument('--source-root', type=Path, default=HERE.parents[1])
args, rest = parser.parse_known_args()
SOURCE = args.source_root.resolve(strict=True)
REQUIRED_NATIVE_ADDITIONS = ('Bootstrap.EvidenceBoundary', 'Bootstrap.OpenFragment',
                             'Bootstrap.QueryGraph')


def unpack(text):
    values = []
    while text:
        n, colon, text = text.partition(':')
        if not colon or not n.isdecimal() or len(text) < int(n):
            raise ValueError('bad independent length field')
        size = int(n)
        values.append(text[:size])
        text = text[size:]
    return values


class ModularControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((SOURCE / 'shared-sources.json').read_text())
        cls.fixture = SOURCE / 'tools/shared/fixtures/item4/RawBinaryShared.hs'
        cls.rows = M.native_source_closure(SOURCE, cls.fixture, cls.manifest)

    def test_closed_companion_owner_checks_exact_crate_and_full_membership(self):
        import artifact_binary_open as O
        crate, members = 'crate/λ', ['a', 'bc']
        encoded = lambda value: ''.join(str(ord(c)) + '_' for c in value)
        legacy = 'Query_' + encoded(crate) + 'z_' + encoded(members[0])
        owner = O.pack(['MLF-OPEN-GROUP-1', crate, O.pack(sorted(members))])
        self.assertTrue(O.companion_group_matches(crate, legacy, owner, members))
        self.assertFalse(O.companion_group_matches('other', legacy, owner, members))
        self.assertFalse(O.companion_group_matches(crate, legacy, owner, ['a']))
        self.assertFalse(O.companion_group_matches(crate, legacy, owner + 'x', members))
        self.assertFalse(O.companion_group_matches(crate, 'wrong', owner, members))

    def test_query_fixture_separates_dictionary_and_legacy_payload_contracts(self):
        source = (SOURCE / 'tools/shared/fixtures/item4/QueryIndex.hs').read_text()
        self.assertIn('rootRow = row 3 1 [refs 2 0, refs 2 0] (just (W.VInt 0))', source)
        self.assertIn('(\"root\",Q.QueryNode \"root\" hashB [(\"leaf\",hashA),(\"leaf\",hashA)] (T.Just hashB))', source)
        self.assertIn('right "legacy index reader" (decode (Q.encodeLegacyIndex "config" legacyNodes)) >>= same "legacy compatibility" legacyNodes', source)
        self.assertIn('decodeReject "legacy mismatched payload" "invalid query graph digest"\n    (Q.encodeLegacyIndex "config" decoded)', source)
        self.assertIn('oldRoot = legacyNode "root" hashB [("leaf",hashA)] (just (W.VText hashB))', source)
        self.assertIn('decodeReject "legacy duplicate" "duplicate" (legacy [oldLeaf,oldLeaf,oldRoot])', source)
        self.assertIn('decodeReject "legacy missing" "unpublished" (legacy [oldRoot])', source)

    def test_stamp_syntax_and_semantic_mutations_remain_distinct(self):
        import artifact_binary_open as O
        for value in ('0-0', '0-1', '2147483646-2147483628'):
            O.checked_stamp_syntax(value)
            changed = O.different_content_stamp(value)
            self.assertNotEqual(changed, value)
            O.checked_stamp_syntax(changed)
        for value in ('', '1', '-1-2', '+1-2', '01-2', '1-02', '1-2-forged',
                      '2147483647-0', '0-2147483629', '１-2', '1-2\n', '9' * 100 + '-0'):
            with self.subTest(value=value), self.assertRaises(O.OpenPairError):
                O.checked_stamp_syntax(value)
        n, text, seq = O.node, O.string, O.sequence
        ty = n(44, text('Int'), seq([]))
        name = n(31, ('int', 1), text('value'))
        interface = n(242, text('fixture'), seq([]), seq([text('Main')]),
                      seq([]), seq([]), seq([]), seq([]), seq([]), seq([]),
                      seq([n(2, text('value'), ty)]), text('value'), text(''), seq([]))
        body = n(75, name, n(77, ('int', 41)), n(82, text('()'), seq([])))
        fragment = n(401, text('g'), text('0-1'), seq([]), seq([]), body,
                     seq([name]), seq([]))
        # Synthetic canonical syntax only: this stamp is not claimed to bind body.
        for schema in (7, 8):
            opened = [text(O.OPEN_FORMATS[schema]), text(O.compatibility_identity()),
                      text(O.pack([O.interface_association(interface)])),
                      seq([n(2, text('value'), text(O.fingerprint(ty)))]), seq([]), seq([fragment])]
            pair = O.repinned((O.tree_document([interface], 3), b''), O.open_bytes(schema, opened))
            O.inspect_pair(pair, [])
            label, changed, diagnostic = O.content_stamp_mutation(pair)
            self.assertEqual(label, ('schema7-' if schema == 7 else '') + 'wrong-open-fragment-content-stamp')
            self.assertEqual(diagnostic, 'open crate fragment fingerprint mismatch')
            O.inspect_pair(changed, [])  # semantic authentication is NOT Python's claim
            _, _, changed_fields = O.open_document(changed[1])
            changed_fragment = list(O.fields(O.items(changed_fields[5])[0], 401, 7))
            self.assertEqual(O.text(changed_fragment[1]), '1-1')
            changed_fragment[1] = O.fields(fragment, 401, 7)[1]
            self.assertEqual(O.node(401, *changed_fragment), fragment)
            self.assertEqual(changed_fields[:5], tuple(opened[:5]))
            malformed = next(row for row in O.mutation_cases(pair) if row[0] == 'wrong-open-fragment-stamp')
            with self.assertRaisesRegex(O.OpenPairError, '^malformed open fragment stamp$'):
                O.inspect_pair(malformed[1], [])

    def test_both_stamp_schemas_require_all_three_actual_readers(self):
        expected = {backend + '-' + case
                    for backend in ('formal', 'shared-ghc', 'shared-native')
                    for case in ('wrong-open-fragment-stamp', 'wrong-open-fragment-content-stamp',
                                 'schema7-wrong-open-fragment-content-stamp')}
        self.assertTrue(expected <= M.CONTROL_COMMANDS)
        for name in expected:
            rows = self.complete_commands()
            with self.subTest(name=name), self.assertRaises(ValueError):
                M.require_control_commands([row for row in rows if row['name'] != name])
            next(row for row in rows if row['name'] == name)['state'] = 'failed'
            with self.subTest(name=name), self.assertRaises(ValueError):
                M.require_control_commands(rows)

    def test_complete_source_closure(self):
        self.assertEqual(len(self.rows), 51)
        self.assertEqual({r['module'] for r in self.rows}, M.NATIVE_MODULES)
        self.assertEqual([r['module'] for r in self.rows], sorted(M.NATIVE_MODULES))
        for name in REQUIRED_NATIVE_ADDITIONS:
            self.assertIn(name, {r['module'] for r in self.rows})
        self.assertIn('Bootstrap.CrateArtifact', M.NATIVE_MODULES)
        self.assertEqual(next(r['path'] for r in self.rows if r['module'] == 'Main'), str(self.fixture))
        for row in self.rows:
            self.assertEqual(row['sha256'], M.sha(Path(row['path'])))
            self.assertEqual(row['bytes'], Path(row['path']).stat().st_size)

    def test_specs_independent_decode(self):
        directory = Path('/fresh/binary gate/π😀')
        plan = M.native_crate_plan(self.rows, directory, SOURCE)
        names = ['mlf-foundation', 'mlf-language-core', 'mlf-frontend',
                 'mlf-xmlf', 'mlf-inference', 'mlf-crates', 'fixture']
        self.assertEqual([p['name'] for p in plan], names)
        self.assertEqual([len(p['modules']) for p in plan], [13, 4, 10, 6, 9, 8, 1])
        all_modules = [name for p in plan for name in p['modules']]
        self.assertEqual(sorted(all_modules), sorted(M.NATIVE_MODULES))
        self.assertEqual(len(all_modules), len(set(all_modules)))
        expected_dependencies = [[], names[:1], names[:2], names[:3], names[:4], names[:5],
                                 ['mlf-crates', 'mlf-foundation', 'mlf-xmlf']]
        paths = {row['module']: row['path'] for row in self.rows}
        finished = {}
        for component, dependencies in zip(plan, expected_dependencies):
            name = component['name']
            prefix = directory / 'fixture' if name == 'fixture' else directory / name / 'unit'
            self.assertEqual(component['prefix'], str(prefix))
            fields = unpack(component['spec'])
            self.assertEqual(fields[:4], ['MLF-CRATE-1', 'artifact-binary-native-' + name,
                                         'Main' if name == 'fixture' else '', 'false'])
            self.assertEqual([unpack(x) for x in unpack(fields[4])],
                             [[module, paths[module]] for module in component['modules']])
            self.assertEqual(component['dependencies'], sorted(dependencies))
            self.assertEqual(unpack(fields[5]), [finished[dep] for dep in sorted(dependencies)])
            self.assertEqual(fields[6:], [str(directory / name / 'inference-cache'),
                                         str(directory / 'builtin/prelude')])
            finished[name] = str(prefix.with_suffix('.mlfci'))
        self.assertEqual(plan[-1]['modules'], ['Main'])
        self.assertEqual(paths['Main'], str(self.fixture))

    def test_specs_reject_wrong_owner(self):
        rows = copy.deepcopy(self.rows)
        row = next(r for r in rows if r['module'] == 'Bootstrap.ST')
        row['path'] = str(SOURCE / 'libraries/mlf-crates/Bootstrap/ST.hs')
        with self.assertRaisesRegex(ValueError, 'module declaration'):
            M.native_crate_plan(rows, Path('/fresh'), SOURCE)

    def test_specs_reject_unknown_import(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['imports'].append('Missing.Module')
        with self.assertRaisesRegex(ValueError, 'outside authenticated closure'):
            M.native_crate_plan(rows, Path('/fresh'), SOURCE)

    def test_specs_reject_undeclared_dependency(self):
        rows = copy.deepcopy(self.rows)
        next(r for r in rows if r['module'] == 'Bootstrap.ST')['imports'].append('Bootstrap.CrateArtifact')
        with self.assertRaisesRegex(ValueError, 'undeclared native library dependency'):
            M.native_crate_plan(rows, Path('/fresh'), SOURCE)

    def manifest_mutation(self, mutate, expected):
        # Exercise the actual JSON/path admissions on a tiny owner-manifest tree.
        # Source hashes/headers are covered separately by the closure controls.
        with tempfile.TemporaryDirectory() as d:
            source = Path(d).resolve()
            manifests = {}
            for name in M.NATIVE_LIBRARIES:
                manifests[name] = json.loads((SOURCE / 'libraries' / name / 'mlf-package.json').read_text())
            rows = copy.deepcopy(self.rows)
            for row in rows:
                if row['module'] != 'Main':
                    row['path'] = str(source / Path(row['path']).relative_to(SOURCE))
            mutate(manifests, rows)
            for name, manifest in manifests.items():
                path = source / 'libraries' / name / 'mlf-package.json'
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, expected):
                M.native_crate_plan(rows, Path('/fresh'), source)

    def test_specs_reject_manifest_identity(self):
        def mutate(manifests, rows):
            manifests['mlf-crates']['name'] = 'different-owner'
        self.manifest_mutation(mutate, 'identity mismatch')

    def test_specs_reject_module_path(self):
        def mutate(manifests, rows):
            manifests['mlf-foundation']['library']['modules']['Bootstrap.ST'] = 'Bootstrap/Different.hs'
        self.manifest_mutation(mutate, 'module declaration')

    def test_specs_reject_external_dependency_path(self):
        def mutate(manifests, rows):
            manifests['mlf-crates']['dependencies']['mlf-foundation']['path'] = '/installed/mlf-foundation'
        self.manifest_mutation(mutate, 'local library owner')

    def test_specs_reject_dependency_cycle(self):
        def mutate(manifests, rows):
            manifests['mlf-foundation']['dependencies'] = {'mlf-crates': {'path': '../mlf-crates'}}
            next(r for r in rows if r['module'] == 'Bootstrap.ST')['imports'].append('Bootstrap.CrateArtifact')
        self.manifest_mutation(mutate, 'cyclic native library dependencies')

    def test_scalar_field_roundtrip(self):
        values = ['', 'a:b', 'π😀', 'space path']
        self.assertEqual(unpack(M.crate_fields(values)), values)

    def test_field_rejects_nul(self):
        with self.assertRaises(ValueError): M.crate_fields(['a\0b'])

    def test_field_rejects_surrogate(self):
        with self.assertRaises(ValueError): M.crate_fields(['\ud800'])

    def test_field_rejects_nonstring(self):
        with self.assertRaises(ValueError): M.crate_fields([1])

    def test_spec_rejects_omission(self):
        with self.assertRaises(ValueError): M.native_crate_plan(self.rows[:-1], Path('/fresh'), SOURCE)

    def test_spec_rejects_reordering(self):
        with self.assertRaises(ValueError): M.native_crate_plan(list(reversed(self.rows)), Path('/fresh'), SOURCE)

    def test_manifest_rejects_duplicate(self):
        m = copy.deepcopy(self.manifest); m['modules'].append(m['modules'][0])
        with self.assertRaises(ValueError): M.native_source_closure(SOURCE, self.fixture, m)

    def test_manifest_rejects_escape(self):
        m = copy.deepcopy(self.manifest); m['modules'][0]['path'] = '../outside.hs'
        with self.assertRaises(ValueError): M.native_source_closure(SOURCE, self.fixture, m)

    def test_manifest_rejects_absolute(self):
        m = copy.deepcopy(self.manifest); m['modules'][0]['path'] = '/outside.hs'
        with self.assertRaises(ValueError): M.native_source_closure(SOURCE, self.fixture, m)

    def test_manifest_rejects_missing_dependency(self):
        m = copy.deepcopy(self.manifest)
        m['modules'] = [r for r in m['modules'] if r['module'] != 'Bootstrap.CrateArtifact']
        with self.assertRaises(ValueError): M.native_source_closure(SOURCE, self.fixture, m)

    def test_manifest_rejects_each_required_new_module(self):
        for name in REQUIRED_NATIVE_ADDITIONS:
            with self.subTest(module=name):
                m = copy.deepcopy(self.manifest)
                m['modules'] = [r for r in m['modules'] if r['module'] != name]
                self.assertEqual(len(m['modules']), len(self.manifest['modules']) - 1)
                with self.assertRaises(ValueError) as error:
                    M.native_source_closure(SOURCE, self.fixture, m)
                self.assertEqual(str(error.exception), 'native source import absent from manifest: ' + name)

    def test_spec_rejects_each_required_module(self):
        for row in self.rows:
            with self.subTest(module=row['module']):
                reduced = [r for r in self.rows if r['module'] != row['module']]
                self.assertEqual(len(reduced), 50)
                with self.assertRaisesRegex(ValueError, '^native crate inventory order/identity mismatch$'):
                    M.native_crate_plan(reduced, Path('/fresh'), SOURCE)

    def extra_module_row(self):
        name = 'Bootstrap.Version'
        self.assertNotIn(name, M.NATIVE_MODULES)
        matches = [r for r in self.manifest['modules'] if r['module'] == name]
        self.assertEqual(len(matches), 1)
        return {'module': name, 'path': str(M.regular(SOURCE / matches[0]['path']))}

    def test_fixture_rejects_manifested_extra_module(self):
        extra = self.extra_module_row()
        text = self.fixture.read_text()
        anchor = '  import MLF.Primitive;'
        self.assertEqual(text.count(anchor), 1)
        text = text.replace(anchor, anchor + '\n  import ' + extra['module'] + ';', 1)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'Main.hs'; p.write_text(text)
            with self.assertRaisesRegex(ValueError, '^native fixture must retain exact reviewed 51-module closure$'):
                M.native_source_closure(SOURCE, p, self.manifest)

    def test_spec_rejects_extra_module(self):
        rows = sorted([*self.rows, self.extra_module_row()], key=lambda r: r['module'])
        self.assertEqual(len(rows), 52)
        with self.assertRaisesRegex(ValueError, '^native crate inventory order/identity mismatch$'):
            M.native_crate_plan(rows, Path('/fresh'), SOURCE)

    def test_spec_rejects_same_size_substitution(self):
        extra = self.extra_module_row()
        for name in REQUIRED_NATIVE_ADDITIONS:
            with self.subTest(module=name):
                rows = sorted([extra if r['module'] == name else r for r in self.rows],
                              key=lambda r: r['module'])
                self.assertEqual(len(rows), 51)
                with self.assertRaisesRegex(ValueError, '^native crate inventory order/identity mismatch$'):
                    M.native_crate_plan(rows, Path('/fresh'), SOURCE)

    def bad_fixture(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'Main.hs'; p.write_text(text)
            with self.assertRaises(ValueError): M.native_source_closure(SOURCE, p, self.manifest)

    def test_fixture_rejects_wrong_header(self):
        self.bad_fixture(self.fixture.read_text().replace('module Main where', 'module Wrong where', 1))

    def test_fixture_rejects_unknown_import(self):
        self.bad_fixture(self.fixture.read_text().replace('  import MLF.Primitive;', '  import Missing.Module;'))

    def test_fixture_rejects_reduced_scope(self):
        self.bad_fixture('module Main where {\n import MLF.Primitive;\n main = return ();\n}\n')

    def complete_commands(self):
        return [{'name': name, 'state': 'passed',
                 'exit_code': 1 if name in M.CONTROL_REJECTIONS else 0}
                for name in sorted(M.CONTROL_COMMANDS)]

    def test_complete_control_inventory(self):
        self.assertEqual(len(M.CONTROL_COMMANDS), 142)
        self.assertEqual(len(M.CONTROL_REJECTIONS), 13)
        self.assertIn('shared-native-public-pair-closed', M.CONTROL_COMMANDS)
        self.assertIn('formal-corrupt-4', M.CONTROL_COMMANDS)
        self.assertEqual(len(M.require_control_commands(self.complete_commands())), 142)

    def test_controls_reject_omitted_materialization(self):
        rows = [row for row in self.complete_commands() if row['name'] != 'release-materialize-warm']
        with self.assertRaises(ValueError): M.require_control_commands(rows)

    def test_controls_reject_duplicate(self):
        rows = self.complete_commands()
        with self.assertRaises(ValueError): M.require_control_commands(rows + rows[:1])

    def test_controls_reject_unknown_stage(self):
        rows = self.complete_commands(); rows[0]['name'] = 'unreviewed-stage'
        with self.assertRaises(ValueError): M.require_control_commands(rows)

    def test_controls_reject_unchecked_failure(self):
        rows = self.complete_commands(); rows[0]['state'] = 'failed'
        with self.assertRaises(ValueError): M.require_control_commands(rows)

    def test_controls_require_actual_negative_exit(self):
        rows = self.complete_commands()
        next(row for row in rows if row['name'] == 'release-forged-current')['exit_code'] = 0
        with self.assertRaises(ValueError): M.require_control_commands(rows)

    def test_controls_keep_self_checked_rejections_successful(self):
        rows = self.complete_commands()
        next(row for row in rows if row['name'] == 'formal-corrupt-4')['exit_code'] = 1
        with self.assertRaises(ValueError): M.require_control_commands(rows)

    def test_cold_query_accepts_fresh(self):
        M.require_cold_queries({'groups': [{'cached': False}], 'inferred_groups': 1, 'reused_groups': 0})

    def test_cold_query_rejects_empty(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [], 'inferred_groups': 0, 'reused_groups': 0})

    def test_cold_query_rejects_reuse(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [{'cached': True}], 'inferred_groups': 1, 'reused_groups': 0})

    def test_cold_query_rejects_bool_count(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [{'cached': False}], 'inferred_groups': True, 'reused_groups': 0})

    def test_cold_query_rejects_missing_cached(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [{}], 'inferred_groups': 1, 'reused_groups': 0})

    def test_cold_query_rejects_count_mismatch(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [{'cached': False}], 'inferred_groups': 2, 'reused_groups': 0})


if __name__ == '__main__':
    unittest.main(argv=[__file__, *rest])
