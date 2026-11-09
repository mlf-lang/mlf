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

    def test_complete_source_closure(self):
        self.assertEqual(len(self.rows), 51)
        self.assertEqual({r['module'] for r in self.rows}, M.NATIVE_MODULES)
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
        self.assertEqual(len(M.CONTROL_COMMANDS), 60)
        self.assertEqual(len(M.CONTROL_REJECTIONS), 13)
        self.assertIn('shared-native-closed-public-pair', M.CONTROL_COMMANDS)
        self.assertIn('formal-corrupt-4', M.CONTROL_COMMANDS)
        self.assertEqual(len(M.require_control_commands(self.complete_commands())), 60)

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
