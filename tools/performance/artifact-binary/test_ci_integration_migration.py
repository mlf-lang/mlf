"""Physical CI-integration controls and complete five-level historical replay.

Every invocation reconstructs the exact query-index physical predecessor and runs
its unchanged suite, including package-roots, open-release, builtin and writer
physical levels. Source projection and replay are not native-runtime qualification.
"""
from pathlib import Path
import copy
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BUNDLE = Path('tools/performance/artifact-binary')
LITERAL = 'bootstrap/MLF/BuiltinPreludeData.hs'
CHANGED = {'bootstrap/MLF/BuiltinPreludeData.hs', 'libraries/mlf-crates/Bootstrap/Crate.hs', 'libraries/mlf-crates/Bootstrap/OpenFragment.hs', 'mlf.lock'}
OLD_LOADER = 'query-index-test-loader.py'
OLD_LOADER_SHA256 = '156e1963c096fdae8eb49cd04bb4bf4d06be423e68063763904cad4e53992b7d'
OLD_TEST = 'test_query_index_migration.py'
OLD_TEST_SHA256 = '7b6596657daa6c929c0c3efc8e9560ed650fe34d19177f18601a3d47aaf8cb96'
REPLAY_DEPENDENCIES = {'open-release-test-loader.py': '2d07b8ae1afa7d501af427b02c9381054ee30b83d6d40d3def1d769190a537c6', 'test_open_release_migration.py': '2e331c5e91912182c69f7284c823d4103d41ea84431878bac258d9a10875a54a', 'builtin-regeneration-test-loader.py': '019ba542650dfc0383807bd79b8d9ae3f7e25b46774df7c1d2bc6e947d8b9792', 'test_builtin_regeneration_migration.py': '120324ae7187b2a2b02e5a578f7cae033ec9405fe8ba364f86a2ef51c8b2f451', 'writer-preflight-test-loader.py': '354ded2e9593c63010b671281dd76da6f9ec1a61885da8297923835bda9edde5', 'test_writer_preflight_migration.py': '47113a2abe0ca0d00e16c2c4e6d06dff40be6b3ea0fed7e802bf14ad64d520b7', 'open-package-roots-test-loader.py': '77fa80b077346456d12953ddf4558ee31f3d7802df5b6de7ac3704e9982e4cbf', 'test_open_package_roots_migration.py': '706365e3b04ec3d07488a6cc3f14f11973823dea3a1bfc7318efc0f1b57fe5a4'}



def load_adapter(directory=HERE):
    path = directory / 'source_migration_adapter.py'
    module = types.ModuleType('ci_integration_test_loader')
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def fixture_files(binary, current, predecessor=False):
    """Enumerate complete physical fixtures, keeping roles and pins explicit."""
    c = binary._core
    binary._require_raw_map(current, binary.value['current_files'], 'fixture current')
    files = ({p: binary._to_index(raw, p) for p, raw in current.items()}
             if predecessor else dict(current))
    expected = binary.query_index_value['current_files'] if predecessor else binary.value['current_files']
    binary._require_raw_map(files, expected, 'fixture query-index' if predecessor else 'fixture current')

    def add(name, raw):
        c.relative_path(name)
        c.require(name not in files and type(raw) is bytes, 'duplicate physical fixture target')
        files[name] = raw

    for name in set(binary.parent['frozen_history']) | set(binary.maintenance_parent['files']):
        add('tools/performance/' + name, c.read_file(ROOT / 'tools/performance', name))
    names = binary.query_index_metadata_paths if predecessor else binary.metadata_paths
    for name in names:
        add(str(BUNDLE / name), c.read_file(binary.directory, name, c.MAX_METADATA_BYTES))
    if predecessor:
        loader = c.read_file(HERE, OLD_LOADER, 65536)
        c.require(c.sha(loader) == OLD_LOADER_SHA256, 'exact unchanged query-index selector')
        files[str(BUNDLE / 'source_migration_adapter.py')] = loader
        for name, digest in {OLD_TEST: OLD_TEST_SHA256, **REPLAY_DEPENDENCIES}.items():
            raw = c.read_file(HERE, name, 65536)
            c.require(c.sha(raw) == digest, 'exact unchanged historical suite dependency: ' + name)
            add(str(BUNDLE / name), raw)
    c.require(sum(map(len, files.values())) <= 64 * 1024**2, 'physical fixture exceeds 64MiB bound')
    return files


def physical_fixture(binary, current, checkout, predecessor=False):
    for name, raw in fixture_files(binary, current, predecessor).items():
        path = checkout / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return checkout / BUNDLE


class CIIntegrationBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = load_adapter().live_contract(ROOT / 'tools/performance')
        cls.raw = {p: cls.binary._core.read_file(ROOT, p) for p in cls.binary.value['current_files']}
        cls.index_raw = {p: cls.binary._to_index(raw, p) for p, raw in cls.raw.items()}


    def test_four_source_three_registry_edge_and_unchanged_history(self):
        b, c = self.binary, self.binary._core
        edge = b.value['ci_integration_successor']
        self.assertEqual((len(b.value['current_files']), len(b.value['current_registry']),
                          b.value['primitive_count']), (196, 135, 132))
        self.assertEqual(c.canonical_sha(b.query_index_value), edge['index_value_sha256'])
        self.assertEqual({p for p in self.raw if self.raw[p] != self.index_raw[p]}, CHANGED)
        self.assertEqual({n for n in b.value['current_registry']
                          if b.value['current_registry'][n] != b.query_index_value['current_registry'][n]},
                         {'Bootstrap.OpenFragment', 'Bootstrap.Crate', 'MLF.BuiltinPreludeData'})
        for key in ('transition', 'maintenance', 'successor', 'builtin_successor',
                    'open_release_successor', 'open_package_roots_successor',
                    'query_index_successor', 'graph_source_head'):
            self.assertEqual(b.value[key], b.query_index_value[key])
        self.assertEqual(b.query_index_value['source_base_head'],
                         '9ef905033caa654ca07507d8b5ac2363f3207269')
        self.assertEqual(b.value['source_base_head'],
                         'd5e18cde20a6e0308a85fa219152363219c2ed6b')
        self.assertEqual(b.value['source_base_tree'],
                         '7f813ad30f6f0c8029f4a21a8b0a3c2c828837e4')
        self.assertEqual(edge['integration_base'], {
            'head': 'a250ec334b70b0e587c2dd6e894d111bf879c024',
            'tree': '63400c29c679ffc5e1a67b46ebbde12c5f81ddf4'})
        self.assertEqual(c.sha(c.read_file(HERE, 'query_index_contract.py')),
                         edge['index_contract_sha256'])
        self.assertEqual(c.sha(c.read_file(HERE, 'query-index-migration.json')),
                         edge['index_manifest_sha256'])
        required = {'ci_integration_contract.py', 'ci-integration-migration.json',
                    'ci-integration-provenance.json'}
        required.update(row['file'] for row in edge['transition']['deltas'].values())
        self.assertTrue(required <= set(b.metadata_paths))
        self.assertTrue(set(b.query_index_metadata_paths) <= set(b.metadata_paths))

    def test_complete_raw_path_owner_lock_tree_registry_and_unchanged_bridges(self):
        b = self.binary
        old = b.project_tree_bytes(self.raw)
        additions = {p: self.raw[p] for p in b.added_paths}
        self.assertEqual(b.advance_tree_bytes(old, additions), self.raw)
        self.assertEqual(b.restore_previous_lock(self.raw['mlf.lock']), old['mlf.lock'])
        self.assertEqual(b.advance_lock(old['mlf.lock']), self.raw['mlf.lock'])
        for p, raw in self.raw.items():
            with self.subTest(path=p):
                self.assertEqual(b._from_index(b._to_index(raw, p), p), raw)
                if p in b.added_paths:
                    self.assertIsNone(b.restore_path(raw, p))
                else:
                    self.assertEqual(b.advance_path(b.restore_path(raw, p), p), raw)
                self.assertEqual(b._to_builtin(raw, p), b._index_proxy()._to_builtin(self.index_raw[p], p))
                self.assertEqual(b._to_writer(raw, p), b._index_proxy()._to_writer(self.index_raw[p], p))
        for name, p in b.added_modules.items():
            self.assertIsNone(b.project_owner(self.raw[p], name))
        for p in CHANGED & set(b.frozen_value['current_files']):
            self.assertEqual(b._from_frozen(b._to_frozen(self.raw[p], p), p), self.raw[p])
        registry = b.live_registry(ROOT)
        self.assertEqual(b.live_source_inventory(ROOT), b.value['current_files'])
        self.assertEqual(b.advance_registry(b.registry_to_parent(registry, b.added_source_bytes(ROOT))), registry)
        hosts = b.live_host_inventory(ROOT)
        self.assertEqual(b.advance_host_inventory(b.host_inventory_to_parent(hosts)), hosts)
        subset = {p: hosts[p] for p in b.parent['legacy_host_bridge']}
        self.assertEqual(b.advance_legacy_host_subset(b.legacy_host_subset_to_parent(subset)), subset)
        runtime = {p: digest for p, digest in b.value['current_files'].items() if p.startswith('runtime/')}
        self.assertEqual(b.advance_runtime_inventory(
            b.runtime_inventory_to_parent(runtime, self.raw['runtime/mlf_byte_file.h'])), runtime)
        for name in b.value['maintenance']:
            raw = b._core.read_file(ROOT / 'tools/performance', name)
            self.assertEqual(b._core.sha(b.restore_maintenance(raw, name)),
                             b.maintenance_parent['files'][name]['sha256'])

    def test_stale_mixed_wrong_role_nonbytes_missing_and_extra_reject(self):
        b = self.binary
        parent = b.project_tree_bytes(self.raw)
        for path in CHANGED:
            self.assertEqual(b._from_index(self.index_raw[path], path), self.raw[path])
            for raw in (self.index_raw[path], self.raw[path] + b' ', self.raw[path][:-1],
                        self.raw[path].decode(), bytearray(self.raw[path]), None):
                with self.subTest(path=path, kind=type(raw).__name__), self.assertRaises(ValueError):
                    b.restore_path(raw, path)
            with self.assertRaises(ValueError):
                b.project_tree_bytes({**self.raw, path: self.index_raw[path]})
            with self.assertRaises(ValueError):
                b._from_index(self.raw[path], path)
        for wrong in ('mlf.lock', '../OpenFragment.hs', 'not-a-source'):
            with self.assertRaises(ValueError):
                b.restore_path(self.raw['libraries/mlf-crates/Bootstrap/OpenFragment.hs'], wrong)
        for wrong in ({p: raw for p, raw in self.raw.items() if p != LITERAL},
                      {**self.raw, 'unexpected.hs': b''}):
            with self.assertRaises(ValueError):
                b.project_tree_bytes(wrong)
        with self.assertRaises(ValueError):
            b.require_registry(b.query_index_value['current_registry'], 'current')
        additions = {p: self.raw[p] for p in b.added_paths}
        for path in additions:
            with self.subTest(missing_added=path), self.assertRaises(ValueError):
                b.advance_tree_bytes(parent, {p: raw for p, raw in additions.items() if p != path})

    def test_manifest_validation_preserves_three_field_object_api(self):
        b = self.binary
        trial = object.__new__(type(b))
        trial._core, trial.frozen_value, trial.value = b._core, b.frozen_value, copy.deepcopy(b.value)
        trial._validate_manifest()
        self.assertEqual(trial.query_index_value, b.query_index_value)
        self.assertEqual(trial.builtin_value, b.builtin_value)
        self.assertEqual(trial.writer_value, b.writer_value)
        mutations = []
        for key, replacement in [('primitive_count', 135), ('module_count', 132),
                                 ('source_base_head', '0' * 40), ('source_base_tree', '0' * 40)]:
            v = copy.deepcopy(b.value); v[key] = replacement; mutations.append(v)
        v = copy.deepcopy(b.value); v['current_files'].pop('shared-sources.json'); mutations.append(v)
        v = copy.deepcopy(b.value); v['current_files']['extra'] = '0' * 64; mutations.append(v)
        v = copy.deepcopy(b.value); v['current_registry']['Bootstrap.QueryGraph'] = '0' * 64; mutations.append(v)
        v = copy.deepcopy(b.value); v['transition']['changed_paths'].pop(); mutations.append(v)
        v = copy.deepcopy(b.value); v['maintenance'].pop('patricia/run_integrated.py'); mutations.append(v)
        v = copy.deepcopy(b.value); v['open_package_roots_successor']['base_head'] = '0' * 40; mutations.append(v)
        for key, replacement in [('file_count', True), ('index_value_sha256', '0' * 64)]:
            v = copy.deepcopy(b.value); v['ci_integration_successor'][key] = replacement; mutations.append(v)
        v = copy.deepcopy(b.value); v['ci_integration_successor']['transition']['deltas'].pop('mlf.lock'); mutations.append(v)
        v = copy.deepcopy(b.value); v['ci_integration_successor']['transition']['added_paths'] = ['extra']; mutations.append(v)
        for v in mutations:
            trial = object.__new__(type(b))
            trial._core, trial.frozen_value, trial.value = b._core, b.frozen_value, v
            with self.assertRaises(ValueError):
                trial._validate_manifest()

    def test_independent_literal_and_exact_three_hash_lock_guards(self):
        b, c = self.binary, self.binary._core
        b._validate_ci_literal(self.index_raw[LITERAL], self.raw[LITERAL])
        b._validate_ci_lock(self.index_raw['mlf.lock'], self.raw['mlf.lock'])
        for raw in (self.raw[LITERAL] + b' ', self.index_raw[LITERAL],
                    b'X' + self.raw[LITERAL][1:], self.raw[LITERAL][:775] + b'X' + self.raw[LITERAL][776:]):
            with self.assertRaises(ValueError):
                b._validate_ci_literal(self.index_raw[LITERAL], raw)
        parsed = c.strict_json(self.raw['mlf.lock'])
        variants = []
        value = copy.deepcopy(parsed); value['packages'].reverse(); variants.append(value)
        value = copy.deepcopy(parsed); value['packages'][0]['version'] = 'unexpected'; variants.append(value)
        value = copy.deepcopy(parsed); value['extra'] = True; variants.append(value)
        for name in CHANGED - {'mlf.lock'}:
            value = copy.deepcopy(parsed)
            for package in value['packages']:
                for key in package['sources']:
                    if c.lock_path(package['path'], key) == name:
                        package['sources'][key] = b.query_index_value['current_files'][name]
            variants.append(value)
        for value in variants:
            with self.assertRaises(ValueError):
                b._validate_ci_lock(self.index_raw['mlf.lock'], c.json.dumps(value).encode())


    def test_new_actual_generation_and_unchanged_failed_ancestor_proof(self):
        b = self.binary
        b._validate_provenance_record(b.generation_evidence)
        b._validate_index_provenance_record(b.query_index_generation_evidence)
        b._validate_roots_provenance_record(b.open_package_roots_generation_evidence)
        b._index_proxy()._roots_proxy()._open_proxy()._validate_open_release_provenance_record(
            b.open_release_generation_evidence)
        old = b.open_package_roots_generation_evidence
        self.assertTrue(old['collector']['generation_body_complete'])
        self.assertFalse(old['collector']['wrapper_complete'])
        self.assertEqual(old['wrapper_failure']['exit_code'], 1)
        self.assertIn('TypeError', old['wrapper_failure']['reason'])
        self.assertTrue(old['recovery']['complete'])
        self.assertEqual(old['recovery']['actual_command_exits'], [0, 0, 0])
        value = b.ci_integration_generation_evidence
        b._validate_ci_provenance_record(value)
        self.assertEqual(value['comparison']['generated']['sha256'],
                         b.value['current_files'][LITERAL])
        self.assertEqual((value['collector']['fresh_compilation_count'],
                          value['collector']['reused_compilation_count'],
                          value['collector']['total_compilation_closure']), (8, 51, 59))
        self.assertEqual(len(value['commands']), 10)
        self.assertEqual(set(value['type_audits']), {'0', '2'})
        self.assertEqual(value['controls']['methods'], 7)
        self.assertEqual(value['toolchain_inputs']['format'],
                         'authenticated-complete-toolchain-inventory-reference-v1')
        self.assertEqual(value['toolchain_inputs']['file_count'], 1926)
        self.assertEqual(value['toolchain_inputs']['inventory_sha256'],
                         'b6aa43d2399f722b788e24660078a450a2c3c97958bf2824cb34097e3c0bc52e')
        self.assertEqual(value['toolchain_inputs']['receipt'], value['preparation_receipt'])
        self.assertEqual(value['toolchain_inputs']['ghc']['label'], 'GHC_EXECUTABLE')
        self.assertEqual(value['toolchain_inputs']['ghc']['version'], '9.14.1')
        self.assertEqual(value['toolchain_inputs']['ghc']['input'],
                         {'bytes': 736, 'mode': 493,
                          'sha256': '6b0b015104f88cb39030a2e2613dcda21ad449260183ff50d6ebec8a49efe711'})
        self.assertEqual(value['preparation_receipt']['sha256'],
                         '99d365c9100efea8c2a7cff673fd4a350f25ba151201898bd517ea773d9233b2')
        self.assertNotIn('Bootstrap.Crate', value['source']['compiled_sources'])
        self.assertNotIn('Bootstrap.Crate', value['source']['identity_inputs']['modules'])
        self.assertIn('libraries/mlf-crates/Bootstrap/Crate.hs', value['source']['overlay'])
        self.assertIn('Bootstrap.QueryGraph', value['reused_modules'])
        for marker in ('/workspace/', '/tmp/', '/home/', '/root/'):
            self.assertNotIn(marker, b._core.json.dumps(value))
        for key, replacement in [('fresh_compilation_count', 1),
                                  ('wrapper_complete', False),
                                  ('full_compiler_build', True)]:
            altered = copy.deepcopy(value)
            altered['collector'][key] = replacement
            with self.assertRaises(ValueError):
                b._validate_ci_provenance_record(altered)
        variants = []
        altered = copy.deepcopy(value); altered['commands'].pop(); variants.append(altered)
        altered = copy.deepcopy(value); altered['toolchain_inputs']['file_count'] -= 1; variants.append(altered)
        altered = copy.deepcopy(value); altered['toolchain_inputs']['inventory_sha256'] = '0' * 64; variants.append(altered)
        altered = copy.deepcopy(value); altered['toolchain_inputs']['inventory_field'] = 'other'; variants.append(altered)
        altered = copy.deepcopy(value); altered['reused_modules'].pop(); variants.append(altered)
        altered = copy.deepcopy(value); altered['type_audits'].pop('2'); variants.append(altered)
        altered = copy.deepcopy(value); altered['source']['overlay'].pop('mlf.lock'); variants.append(altered)
        altered = copy.deepcopy(value); altered['qualification']['full_ci'] = True; variants.append(altered)
        for altered in variants:
            with self.assertRaises(ValueError):
                b._validate_ci_provenance_record(altered)
        altered = copy.deepcopy(b.query_index_generation_evidence)
        altered['source']['overlay']['mlf.lock']['sha256'] = b.value['current_files']['mlf.lock']
        with self.assertRaises(ValueError):
            b._validate_index_provenance_record(altered)
        altered = copy.deepcopy(old); altered['collector']['wrapper_complete'] = True
        with self.assertRaises(ValueError):
            b._validate_roots_provenance_record(altered)

    def test_real_default_explicit_relocation_and_full196_admission(self):
        b = self.binary
        explicit = type(b)(b.directory, b.manifest_sha256, ROOT / 'tools/performance', source_root=ROOT)
        self.assertEqual(explicit.live_source_inventory(ROOT), b.value['current_files'])
        with self.assertRaises(ValueError):
            type(b)(b.directory, '0' * 64, ROOT / 'tools/performance', source_root=ROOT)
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / 'current'
            bundle = physical_fixture(b, self.raw, checkout)
            relocated = load_adapter(bundle).live_contract(checkout / 'tools/performance')
            self.assertEqual(relocated.live_source_inventory(checkout), b.value['current_files'])
            self.assertEqual(relocated.source_root, checkout.resolve())
            self.assertEqual(relocated.evidence_source_root, b.evidence_source_root)
            for name in sorted(CHANGED) + ['host/ghc/MLF/Host/Base.hs', 'runtime/mlf_byte_file.h', 'cabal.project']:
                path = checkout / name
                original = path.read_bytes()
                path.write_bytes(self.index_raw[name] if name in CHANGED else original + b' ')
                try:
                    with self.subTest(source=name), self.assertRaises(ValueError):
                        load_adapter(bundle).live_contract(checkout / 'tools/performance')
                finally:
                    path.write_bytes(original)
            missing = checkout / 'cabal.project'; missing.unlink()
            try:
                with self.assertRaises(FileNotFoundError):
                    load_adapter(bundle).live_contract(checkout / 'tools/performance')
            finally:
                missing.write_bytes(self.raw['cabal.project'])
            self.assertEqual(load_adapter(bundle).live_contract(checkout / 'tools/performance').value, b.value)

    def test_metadata_mutation_and_symlink_fail_closed(self):
        b = self.binary
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / 'current'
            bundle = physical_fixture(b, self.raw, checkout)
            self.assertEqual(load_adapter(bundle).live_contract(checkout / 'tools/performance').value, b.value)
            targets = ['ci_integration_contract.py', 'ci-integration-migration.json',
                       'ci-integration-provenance.json', 'query_index_contract.py',
                       'query-index-migration.json', 'query-index-provenance.json',
                       'open_package_roots_contract.py',
                       'open-package-roots-migration.json', 'open-package-roots-provenance.json']
            targets += [row['file'] for row in b.value['ci_integration_successor']['transition']['deltas'].values()]
            for name in targets:
                path = bundle / name; raw = path.read_bytes(); path.write_bytes(raw + b' ')
                try:
                    with self.subTest(metadata=name), self.assertRaises(ValueError):
                        load_adapter(bundle).live_contract(checkout / 'tools/performance')
                finally:
                    path.write_bytes(raw)
            path = bundle / 'ci-integration-migration.json'
            raw = path.read_bytes(); path.unlink(); path.symlink_to(b.directory / path.name)
            try:
                with self.assertRaises(ValueError):
                    load_adapter(bundle).live_contract(checkout / 'tools/performance')
            finally:
                path.unlink(); path.write_bytes(raw)
            self.assertEqual(load_adapter(bundle).live_contract(checkout / 'tools/performance').value, b.value)

    def test_new_implementation_pin_precedes_missing_dependency_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'source_migration_adapter.py').write_bytes((HERE / 'source_migration_adapter.py').read_bytes())
            (directory / 'ci_integration_contract.py').write_bytes((HERE / 'ci_integration_contract.py').read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'fixed ci-integration source contract implementation SHA'):
                load_adapter(directory).live_contract(ROOT / 'tools/performance', source_root=ROOT)

    def test_historical_replay_helpers_are_pinned_before_execution(self):
        b = self.binary
        helpers = (OLD_LOADER, OLD_TEST, *REPLAY_DEPENDENCIES)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in helpers:
                (directory / name).write_bytes((HERE / name).read_bytes())
            with patch.object(sys.modules[__name__], 'HERE', directory):
                valid = fixture_files(b, self.raw, predecessor=True)
                self.assertEqual(valid[str(BUNDLE / 'source_migration_adapter.py')],
                                 (directory / OLD_LOADER).read_bytes())
                for name in helpers:
                    path = directory / name; original = path.read_bytes()
                    path.write_bytes(original + b' ')
                    try:
                        with self.subTest(helper=name), self.assertRaisesRegex(ValueError, 'exact unchanged'):
                            fixture_files(b, self.raw, predecessor=True)
                    finally:
                        path.write_bytes(original)

    def test_unchanged_index_suite_on_physical_authenticated_predecessor(self):
        b = self.binary
        expected = fixture_files(b, self.raw, predecessor=True)
        self.assertEqual(len(expected), 358)
        self.assertNotIn('tools/shared/run_artifact_binary_controls.py', expected)
        self.assertNotIn('tools/shared/test_artifact_binary.py', expected)
        self.assertNotIn('tools/shared/fixtures/item4/QueryIndex.hs', expected)
        self.assertNotIn('tools/shared/test_query_index.py', expected)
        with tempfile.TemporaryDirectory(prefix='ci-integration-predecessor-') as temporary:
            checkout = Path(temporary) / 'query-index-predecessor'
            bundle = physical_fixture(b, self.raw, checkout, predecessor=True)
            for name, raw in expected.items():
                self.assertEqual(b._core.read_file(checkout, name), raw, name)
            predecessor = load_adapter(bundle).live_contract(checkout / 'tools/performance')
            self.assertEqual(predecessor.value, b.query_index_value)
            self.assertEqual(predecessor.live_source_inventory(checkout),
                             b.query_index_value['current_files'])
            self.assertEqual(predecessor.evidence_source_root, b.evidence_source_root)
            print('PHYSICAL QUERY-INDEX PREDECESSOR REGRESSION: unchanged historical assertions; not current-checkout runtime coverage.',
                  flush=True)
            command = [sys.executable, '-B']
            if sys.flags.optimize:
                command.append('-' + 'O' * sys.flags.optimize)
            command.append(str(bundle / OLD_TEST))
            subprocess.run(command, cwd=checkout, check=True, timeout=300,
                           env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})


    def test_integration_base_head_tree_extra_and_missing_reject(self):
        variants = []
        for field in ('head', 'tree'):
            value = copy.deepcopy(self.binary.value)
            value['ci_integration_successor']['integration_base'][field] = '0' * 40
            variants.append(value)
        value = copy.deepcopy(self.binary.value)
        value['ci_integration_successor']['integration_base']['extra'] = True
        variants.append(value)
        value = copy.deepcopy(self.binary.value)
        del value['ci_integration_successor']['integration_base']['head']
        variants.append(value)
        value = copy.deepcopy(self.binary.value)
        del value['ci_integration_successor']['integration_base']
        variants.append(value)
        for value in variants:
            trial = object.__new__(type(self.binary))
            trial._core, trial.frozen_value, trial.value = (
                self.binary._core, self.binary.frozen_value, value)
            with self.assertRaises(ValueError):
                trial._validate_manifest()

    def test_exact_two_line_signature_and_helper_guards(self):
        b = self.binary
        b._validate_ci_sources(self.index_raw, self.raw)
        open_path = 'libraries/mlf-crates/Bootstrap/OpenFragment.hs'
        crate_path = 'libraries/mlf-crates/Bootstrap/Crate.hs'
        approved = (b'  restoreFinals8 :: [] PackageFinalFields8 -> [] XTerm ->\n'
                    b'    Either String ([] ((,) String Fragment));\n')
        self.assertIn(approved, self.raw[open_path])
        for path in (open_path, crate_path):
            for bad in (self.index_raw[path], self.raw[path] + b' ',
                        self.raw[path][:-1], self.raw[path].decode()):
                changed = dict(self.raw); changed[path] = bad
                with self.subTest(path=path, kind=type(bad).__name__), self.assertRaises(ValueError):
                    b._validate_ci_sources(self.index_raw, changed)
        changed = dict(self.raw)
        changed[open_path] = self.raw[open_path].replace(
            approved, approved.replace(b'->\n    Either', b'-> Either'), 1)
        with self.assertRaises(ValueError):
            b._validate_ci_sources(self.index_raw, changed)

    def test_current_source_symlinks_still_fail_closed(self):
        b = self.binary
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / 'current'
            bundle = physical_fixture(b, self.raw, checkout)
            self.assertEqual(load_adapter(bundle).live_contract(
                checkout / 'tools/performance').value, b.value)
            for name in ('libraries/mlf-crates/Bootstrap/OpenFragment.hs',
                         'libraries/mlf-crates/Bootstrap/Crate.hs'):
                path = checkout / name
                original = path.read_bytes()
                path.unlink()
                path.symlink_to(ROOT / name)
                try:
                    with self.subTest(path=name), self.assertRaises(ValueError):
                        load_adapter(bundle).live_contract(checkout / 'tools/performance')
                finally:
                    path.unlink()
                    path.write_bytes(original)
            self.assertEqual(load_adapter(bundle).live_contract(
                checkout / 'tools/performance').value, b.value)


if __name__ == '__main__':
    unittest.main()
