"""Physical QueryGraph source controls plus unchanged predecessor suite replay.

Every invocation reconstructs the complete physical root-bounded predecessor
and executes its unchanged suite, including all three older physical levels.
Source projection and historical replay do not establish runtime qualification.
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
CHANGED = {LITERAL, 'mlf.lock', 'libraries/mlf-crates/Bootstrap/QueryGraph.hs'}
OLD_LOADER = 'open-package-roots-test-loader.py'
OLD_LOADER_SHA256 = '77fa80b077346456d12953ddf4558ee31f3d7802df5b6de7ac3704e9982e4cbf'
OLD_TEST = 'test_open_package_roots_migration.py'
OLD_TEST_SHA256 = '706365e3b04ec3d07488a6cc3f14f11973823dea3a1bfc7318efc0f1b57fe5a4'
REPLAY_DEPENDENCIES = {
    'open-release-test-loader.py': '2d07b8ae1afa7d501af427b02c9381054ee30b83d6d40d3def1d769190a537c6',
    'test_open_release_migration.py': '2e331c5e91912182c69f7284c823d4103d41ea84431878bac258d9a10875a54a',
    'builtin-regeneration-test-loader.py': '019ba542650dfc0383807bd79b8d9ae3f7e25b46774df7c1d2bc6e947d8b9792',
    'test_builtin_regeneration_migration.py': '120324ae7187b2a2b02e5a578f7cae033ec9405fe8ba364f86a2ef51c8b2f451',
    'writer-preflight-test-loader.py': '354ded2e9593c63010b671281dd76da6f9ec1a61885da8297923835bda9edde5',
    'test_writer_preflight_migration.py': '47113a2abe0ca0d00e16c2c4e6d06dff40be6b3ea0fed7e802bf14ad64d520b7',
}



def load_adapter(directory=HERE):
    path = directory / 'source_migration_adapter.py'
    module = types.ModuleType('query_index_test_loader')
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def fixture_files(binary, current, predecessor=False):
    """Enumerate complete physical fixtures, keeping roles and pins explicit."""
    c = binary._core
    binary._require_raw_map(current, binary.value['current_files'], 'fixture current')
    files = ({p: binary._to_roots(raw, p) for p, raw in current.items()}
             if predecessor else dict(current))
    expected = binary.package_roots_value['current_files'] if predecessor else binary.value['current_files']
    binary._require_raw_map(files, expected, 'fixture package-roots' if predecessor else 'fixture current')

    def add(name, raw):
        c.relative_path(name)
        c.require(name not in files and type(raw) is bytes, 'duplicate physical fixture target')
        files[name] = raw

    for name in set(binary.parent['frozen_history']) | set(binary.maintenance_parent['files']):
        add('tools/performance/' + name, c.read_file(ROOT / 'tools/performance', name))
    names = binary.package_roots_metadata_paths if predecessor else binary.metadata_paths
    for name in names:
        add(str(BUNDLE / name), c.read_file(binary.directory, name, c.MAX_METADATA_BYTES))
    if predecessor:
        loader = c.read_file(HERE, OLD_LOADER, 65536)
        c.require(c.sha(loader) == OLD_LOADER_SHA256, 'exact unchanged package-roots selector')
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


class QueryIndexBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = load_adapter().live_contract(ROOT / 'tools/performance')
        cls.raw = {p: cls.binary._core.read_file(ROOT, p) for p in cls.binary.value['current_files']}
        cls.roots_raw = {p: cls.binary._to_roots(raw, p) for p, raw in cls.raw.items()}

    def test_three_source_two_registry_edge_and_unchanged_history(self):
        b, c = self.binary, self.binary._core
        edge = b.value['query_index_successor']
        self.assertEqual((len(b.value['current_files']), len(b.value['current_registry']),
                          b.value['primitive_count']), (196, 135, 132))
        self.assertEqual((b.frozen_value['module_count'], len(b.parent['registry']),
                          len(b.parent['files'])), (132, 128, 188))
        self.assertEqual(c.canonical_sha(b.package_roots_value), edge['roots_value_sha256'])
        self.assertEqual({p for p in self.raw if self.raw[p] != self.roots_raw[p]}, CHANGED)
        self.assertEqual({n for n in b.value['current_registry']
                          if b.value['current_registry'][n] != b.package_roots_value['current_registry'][n]},
                         {'Bootstrap.QueryGraph', 'MLF.BuiltinPreludeData'})
        for key in ('transition', 'maintenance', 'successor', 'builtin_successor',
                    'open_release_successor', 'open_package_roots_successor', 'graph_source_head'):
            self.assertEqual(b.value[key], b.package_roots_value[key])
        self.assertEqual(b.package_roots_value['source_base_head'], '9ef905033caa654ca07507d8b5ac2363f3207269')
        self.assertEqual(b.open_release_value['source_base_head'], 'eea644f405f90a81a6a81982570bb82fdf425c34')
        self.assertEqual(b.builtin_value['source_base_head'], 'aa661e80f159d4851f05b71bbf77fa868da23b7e')
        self.assertEqual(b.writer_value['source_base_head'], '6d829369efd58c482ac28ac6e0a8cdd96b17adb4')
        self.assertEqual(b.value['source_base_head'], '9ef905033caa654ca07507d8b5ac2363f3207269')
        self.assertEqual(b.value['source_base_tree'], '5688ecefcfce0eaa9f79a4ddf39d122f35d8195a')
        self.assertEqual(c.sha(c.read_file(HERE, 'open_package_roots_contract.py')), edge['roots_contract_sha256'])
        self.assertEqual(c.sha(c.read_file(HERE, 'open-package-roots-migration.json')), edge['roots_manifest_sha256'])
        self.assertEqual(c.sha(c.read_file(HERE, 'builtin-verification-receipt.json')),
                         b.frozen_value['generation']['receipt_sha256'])
        required = {'query_index_contract.py', 'query-index-migration.json',
                    'query-index-provenance.json'}
        required.update(row['file'] for row in edge['transition']['deltas'].values())
        self.assertTrue(required <= set(b.metadata_paths))
        self.assertTrue(set(b.package_roots_metadata_paths) <= set(b.metadata_paths))

    def test_complete_raw_path_owner_lock_tree_registry_and_unchanged_bridges(self):
        b = self.binary
        old = b.project_tree_bytes(self.raw)
        additions = {p: self.raw[p] for p in b.added_paths}
        self.assertEqual(b.advance_tree_bytes(old, additions), self.raw)
        self.assertEqual(b.restore_previous_lock(self.raw['mlf.lock']), old['mlf.lock'])
        self.assertEqual(b.advance_lock(old['mlf.lock']), self.raw['mlf.lock'])
        for p, raw in self.raw.items():
            with self.subTest(path=p):
                self.assertEqual(b._from_roots(b._to_roots(raw, p), p), raw)
                if p in b.added_paths:
                    self.assertIsNone(b.restore_path(raw, p))
                else:
                    self.assertEqual(b.advance_path(b.restore_path(raw, p), p), raw)
                self.assertEqual(b._to_builtin(raw, p), b._roots_proxy()._to_builtin(self.roots_raw[p], p))
                self.assertEqual(b._to_writer(raw, p), b._roots_proxy()._to_writer(self.roots_raw[p], p))
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
            self.assertEqual(b._from_roots(self.roots_raw[path], path), self.raw[path])
            for raw in (self.roots_raw[path], self.raw[path] + b' ', self.raw[path][:-1],
                        self.raw[path].decode(), bytearray(self.raw[path]), None):
                with self.subTest(path=path, kind=type(raw).__name__), self.assertRaises(ValueError):
                    b.restore_path(raw, path)
            with self.assertRaises(ValueError):
                b.project_tree_bytes({**self.raw, path: self.roots_raw[path]})
            with self.assertRaises(ValueError):
                b._from_roots(self.raw[path], path)
        for wrong in ('mlf.lock', '../OpenFragment.hs', 'not-a-source'):
            with self.assertRaises(ValueError):
                b.restore_path(self.raw['libraries/mlf-crates/Bootstrap/OpenFragment.hs'], wrong)
        for wrong in ({p: raw for p, raw in self.raw.items() if p != LITERAL},
                      {**self.raw, 'unexpected.hs': b''}):
            with self.assertRaises(ValueError):
                b.project_tree_bytes(wrong)
        with self.assertRaises(ValueError):
            b.require_registry(b.package_roots_value['current_registry'], 'current')
        additions = {p: self.raw[p] for p in b.added_paths}
        for path in additions:
            with self.subTest(missing_added=path), self.assertRaises(ValueError):
                b.advance_tree_bytes(parent, {p: raw for p, raw in additions.items() if p != path})

    def test_manifest_validation_preserves_three_field_object_api(self):
        b = self.binary
        trial = object.__new__(type(b))
        trial._core, trial.frozen_value, trial.value = b._core, b.frozen_value, copy.deepcopy(b.value)
        trial._validate_manifest()
        self.assertEqual(trial.package_roots_value, b.package_roots_value)
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
        for key, replacement in [('file_count', True), ('roots_value_sha256', '0' * 64)]:
            v = copy.deepcopy(b.value); v['query_index_successor'][key] = replacement; mutations.append(v)
        v = copy.deepcopy(b.value); v['query_index_successor']['transition']['deltas'].pop('mlf.lock'); mutations.append(v)
        v = copy.deepcopy(b.value); v['query_index_successor']['transition']['added_paths'] = ['extra']; mutations.append(v)
        for v in mutations:
            trial = object.__new__(type(b))
            trial._core, trial.frozen_value, trial.value = b._core, b.frozen_value, v
            with self.assertRaises(ValueError):
                trial._validate_manifest()

    def test_independent_literal_and_exact_two_hash_lock_guards(self):
        b, c = self.binary, self.binary._core
        b._validate_index_literal(self.roots_raw[LITERAL], self.raw[LITERAL])
        b._validate_index_lock(self.roots_raw['mlf.lock'], self.raw['mlf.lock'])
        for raw in (self.raw[LITERAL] + b' ', self.roots_raw[LITERAL],
                    b'X' + self.raw[LITERAL][1:], self.raw[LITERAL][:775] + b'X' + self.raw[LITERAL][776:]):
            with self.assertRaises(ValueError):
                b._validate_index_literal(self.roots_raw[LITERAL], raw)
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
                        package['sources'][key] = b.package_roots_value['current_files'][name]
            variants.append(value)
        for value in variants:
            with self.assertRaises(ValueError):
                b._validate_index_lock(self.roots_raw['mlf.lock'], c.json.dumps(value).encode())

    def test_new_actual_generation_and_unchanged_failed_ancestor_proof(self):
        b = self.binary
        b._validate_provenance_record(b.generation_evidence)
        b._roots_proxy()._open_proxy()._validate_open_release_provenance_record(b.open_release_generation_evidence)
        old = b.open_package_roots_generation_evidence
        b._validate_roots_provenance_record(old)
        self.assertTrue(old['collector']['generation_body_complete'])
        self.assertFalse(old['collector']['wrapper_complete'])
        self.assertEqual(old['wrapper_failure']['exit_code'], 1)
        self.assertIn('TypeError', old['wrapper_failure']['reason'])
        self.assertEqual(old['receipt']['sha256'], 'ed73b3ca8b2be7443194907bceddaee6c5a37946fa86f6fd579c733b6e81a030')
        self.assertEqual(old['recovery']['receipt']['sha256'], '95614d49e13d621b42441b8c1a1846f0e32b95616aa0948ee0f0b161f845bde0')
        self.assertTrue(old['recovery']['complete'])
        self.assertEqual(old['recovery']['actual_command_exits'], [0, 0, 0])
        value = b.query_index_generation_evidence
        b._validate_index_provenance_record(value)
        self.assertEqual(value['comparison']['generated']['sha256'], b.value['current_files'][LITERAL])
        self.assertNotIn('/workspace/', b._core.json.dumps(value))
        self.assertEqual((value['collector']['fresh_compilation_count'],
                          value['collector']['reused_compilation_count'],
                          value['collector']['total_compilation_closure'],
                          value['collector']['nongenerated_module_count']), (6, 53, 59, 54))
        self.assertTrue(value['collector']['generation_body_complete'])
        self.assertTrue(value['collector']['wrapper_complete'])
        self.assertFalse(value['collector']['full_compiler_build'])
        self.assertEqual(value['terminal']['actual_command_exits'], [0] * 8)
        self.assertEqual(value['receipt']['sha256'], 'd6fd1fab0becc825c2752bf30a13205ee65f71e8589e6aefade2195cf1129de2')
        self.assertEqual(value['terminal']['receipt']['sha256'], 'e692ed27b3c3a5470ea1d443624ef98020304d153428f12fb94a6a2f5a0d304a')
        self.assertEqual(len(value['source']['compiled_sources']), 59)
        self.assertEqual(len(value['source']['identity_inputs']['modules']), 54)
        self.assertEqual(value['source']['generation_snapshot_file_count'], 571)
        self.assertEqual(value['source']['generation_snapshot_sha256'],
                         '62eef95d451d08a0bc283a3ecb354a65d6a2543a02de84a66da394a7a738c015')
        self.assertEqual(value['commands'][-1]['stdout'], value['comparison']['generated'])
        self.assertEqual(set(value['guards']), {'whole', 'root', 'phase', 'stage'})
        for guard in value['guards'].values():
            self.assertTrue(guard['complete']); self.assertEqual(guard['exit_code'], 0)
        variants = []
        for field, key, replacement in [('collector', 'fresh_compilation_count', 1),
                                        ('collector', 'wrapper_complete', False),
                                        ('collector', 'full_compiler_build', True),
                                        ('terminal', 'complete', False)]:
            altered = copy.deepcopy(value); altered[field][key] = replacement; variants.append(altered)
        for key in value['qualification']:
            altered = copy.deepcopy(value); altered['qualification'][key] = True; variants.append(altered)
        altered = copy.deepcopy(value); altered['reused_modules'].pop(); variants.append(altered)
        altered = copy.deepcopy(value); altered['object_inputs']['Bootstrap.QueryGraph']['origin'] = 'authenticated-parent-generation'; variants.append(altered)
        altered = copy.deepcopy(value); altered['source']['overlay'].pop('mlf.lock'); variants.append(altered)
        altered = copy.deepcopy(value); altered['commands'][-1]['argv'][-1] = 'identity-label-only'; variants.append(altered)
        for altered in variants:
            with self.assertRaises(ValueError):
                b._validate_index_provenance_record(altered)
        # The new view cannot reinterpret the old successful body as a clean wrapper.
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
                path.write_bytes(self.roots_raw[name] if name in CHANGED else original + b' ')
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
            targets = ['query_index_contract.py', 'query-index-migration.json',
                       'query-index-provenance.json', 'open_package_roots_contract.py',
                       'open-package-roots-migration.json', 'open-package-roots-provenance.json']
            targets += [row['file'] for row in b.value['query_index_successor']['transition']['deltas'].values()]
            for name in targets:
                path = bundle / name; raw = path.read_bytes(); path.write_bytes(raw + b' ')
                try:
                    with self.subTest(metadata=name), self.assertRaises(ValueError):
                        load_adapter(bundle).live_contract(checkout / 'tools/performance')
                finally:
                    path.write_bytes(raw)
            path = bundle / 'query-index-migration.json'
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
            (directory / 'query_index_contract.py').write_bytes((HERE / 'query_index_contract.py').read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'fixed query-index source contract implementation SHA'):
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

    def test_unchanged_root_suite_on_physical_authenticated_predecessor(self):
        b = self.binary
        expected = fixture_files(b, self.raw, predecessor=True)
        self.assertEqual(len(expected), 350)
        self.assertNotIn('tools/shared/run_artifact_binary_controls.py', expected)
        self.assertNotIn('tools/shared/test_artifact_binary.py', expected)
        self.assertNotIn('tools/shared/fixtures/item4/QueryIndex.hs', expected)
        self.assertNotIn('tools/shared/test_query_index.py', expected)
        with tempfile.TemporaryDirectory(prefix='query-index-predecessor-') as temporary:
            checkout = Path(temporary) / 'package-roots-predecessor'
            bundle = physical_fixture(b, self.raw, checkout, predecessor=True)
            for name, raw in expected.items():
                self.assertEqual(b._core.read_file(checkout, name), raw, name)
            predecessor = load_adapter(bundle).live_contract(checkout / 'tools/performance')
            self.assertEqual(predecessor.value, b.package_roots_value)
            self.assertEqual(predecessor.live_source_inventory(checkout),
                             b.package_roots_value['current_files'])
            self.assertEqual(predecessor.evidence_source_root, b.evidence_source_root)
            print('PHYSICAL PACKAGE-ROOTS PREDECESSOR REGRESSION: unchanged historical assertions; not current-checkout runtime coverage.',
                  flush=True)
            command = [sys.executable, '-B']
            if sys.flags.optimize:
                command.append('-' + 'O' * sys.flags.optimize)
            command.append(str(bundle / OLD_TEST))
            subprocess.run(command, cwd=checkout, check=True, timeout=300,
                           env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})


if __name__ == '__main__':
    unittest.main()
