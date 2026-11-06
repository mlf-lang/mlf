"""Physical current-source tests and explicit physical writer-predecessor replay.

No generator or compiler runs here. The separately reviewed real O0 evidence is
checked as portable provenance, never promoted to runtime qualification. These
tests require a complete physical current checkout and use bounded temporary
physical fixtures. They offer no virtual-reader or sparse pass mode.
"""
from pathlib import Path
import copy
import hashlib
import os
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BUNDLE = Path('tools/performance/artifact-binary')
LITERAL = 'bootstrap/MLF/BuiltinPreludeData.hs'
OLD_LOADER_SHA256 = '354ded2e9593c63010b671281dd76da6f9ec1a61885da8297923835bda9edde5'
OLD_TEST_SHA256 = '47113a2abe0ca0d00e16c2c4e6d06dff40be6b3ea0fed7e802bf14ad64d520b7'
OLD_LOADER_FIXTURE = 'writer-preflight-test-loader.py'
OLD_TEST = 'test_writer_preflight_migration.py'


def load_adapter(directory=HERE):
    path = directory / 'source_migration_adapter.py'
    module = types.ModuleType('builtin_regeneration_test_loader')
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def physical_fixture(binary, current, checkout, writer=False):
    """Reuse the existing three-group relocation closure, with exact bytes."""
    c = binary._core
    binary._require_raw_map(current, binary.value['current_files'], 'fixture current')
    sources = ({path: binary._to_writer(raw, path) for path, raw in current.items()}
               if writer else dict(current))
    expected = binary.writer_value['current_files'] if writer else binary.value['current_files']
    binary._require_raw_map(sources, expected, 'fixture writer' if writer else 'fixture current')
    files = dict(sources)

    def add(name, raw):
        c.relative_path(name)
        c.require(name not in files and type(raw) is bytes, 'duplicate physical fixture target')
        files[name] = raw

    names = set(binary.parent['frozen_history']) | set(binary.maintenance_parent['files'])
    for name in names:
        add('tools/performance/' + name, c.read_file(ROOT / 'tools/performance', name))
    names = binary.writer_metadata_paths if writer else binary.metadata_paths
    for name in names:
        add(str(BUNDLE / name), c.read_file(binary.directory, name, c.MAX_METADATA_BYTES))
    if writer:
        loader = c.read_file(HERE, OLD_LOADER_FIXTURE, 65536)
        tests = c.read_file(HERE, OLD_TEST, 65536)
        c.require(c.sha(loader) == OLD_LOADER_SHA256 and c.sha(tests) == OLD_TEST_SHA256,
                  'exact unchanged writer test and historical selector')
        # Deliberate temporary selector replacement: the old suite must see its
        # genuine writer view, not a new edge disguised as the old current view.
        files[str(BUNDLE / 'source_migration_adapter.py')] = loader
        add(str(BUNDLE / OLD_TEST), tests)
    c.require(sum(map(len, files.values())) <= 64 * 1024 * 1024, 'physical fixture exceeds 64MiB bound')
    for name, raw in files.items():
        target = checkout / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return checkout / BUNDLE


class BuiltinRegenerationBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = load_adapter().live_contract(ROOT / 'tools/performance')
        cls.raw = {p: cls.binary._core.read_file(ROOT, p) for p in cls.binary.value['current_files']}
        cls.writer_raw = {p: cls.binary._to_writer(raw, p) for p, raw in cls.raw.items()}

    def test_exact_two_file_edge_and_unchanged_predecessor_meanings(self):
        b, c = self.binary, self.binary._core
        edge = b.value['builtin_successor']
        self.assertEqual(len(b.value['current_files']), 196)
        self.assertEqual(len(b.value['current_registry']), 135)
        self.assertEqual(b.value['primitive_count'], 132)
        self.assertEqual(b.frozen_value['module_count'], 132)
        self.assertEqual(len(b.parent['registry']), 128)
        self.assertEqual(len(b.parent['files']), 188)
        self.assertEqual(c.canonical_sha(b.writer_value), edge['writer_value_sha256'])
        self.assertEqual(b.value['successor'], b.writer_value['successor'])
        self.assertEqual(b.value['transition'], b.writer_value['transition'])
        self.assertEqual(b.value['maintenance'], b.writer_value['maintenance'])
        self.assertEqual(b.value['graph_source_head'], 'bdc5db805975c3d77fb3eb93c6199b7452820658')
        self.assertEqual(b.writer_value['source_base_head'], '6d829369efd58c482ac28ac6e0a8cdd96b17adb4')
        self.assertEqual(b.value['source_base_head'], 'aa661e80f159d4851f05b71bbf77fa868da23b7e')
        self.assertEqual(sorted(p for p in self.raw if self.raw[p] != self.writer_raw[p]), [LITERAL, 'mlf.lock'])
        self.assertEqual([n for n in b.value['current_registry']
                          if b.value['current_registry'][n] != b.writer_value['current_registry'][n]],
                         ['MLF.BuiltinPreludeData'])
        self.assertIn('no new runtime or generation qualification', b.value['qualification_scope'])
        self.assertEqual(c.sha(c.read_file(b.directory, 'writer_preflight_contract.py')), edge['writer_contract_sha256'])
        self.assertEqual(c.sha(c.read_file(b.directory, 'writer-preflight-migration.json')), edge['writer_manifest_sha256'])
        self.assertEqual(c.sha(c.read_file(b.directory, 'builtin-verification-receipt.json')),
                         b.frozen_value['generation']['receipt_sha256'])
        required = {'builtin_regeneration_contract.py', 'builtin-regeneration-migration.json',
                    'builtin-regeneration-provenance.json', 'writer_preflight_contract.py',
                    'writer-preflight-migration.json', 'query_graph_contract.py', 'source_contract.py'}
        required.update(row['file'] for row in edge['transition']['deltas'].values())
        self.assertTrue(required <= set(b.metadata_paths))

    def test_all_inherited_public_roundtrips_and_byte_gates(self):
        b = self.binary
        old = b.project_tree_bytes(self.raw)
        additions = {p: self.raw[p] for p in b.added_paths}
        self.assertEqual(b.advance_tree_bytes(old, additions), self.raw)
        self.assertEqual(b.restore_previous_lock(self.raw['mlf.lock']), old['mlf.lock'])
        self.assertEqual(b.advance_lock(old['mlf.lock']), self.raw['mlf.lock'])
        registry = b.live_registry(ROOT)
        self.assertEqual(b.live_source_inventory(ROOT), b.value['current_files'])
        self.assertEqual(b.advance_registry(b.registry_to_parent(registry, b.added_source_bytes(ROOT))), registry)
        hosts = b.live_host_inventory(ROOT)
        self.assertEqual(b.advance_host_inventory(b.host_inventory_to_parent(hosts)), hosts)
        legacy = {p: hosts[p] for p in b.parent['legacy_host_bridge']}
        self.assertEqual(b.advance_legacy_host_subset(b.legacy_host_subset_to_parent(legacy)), legacy)
        runtime = {p: digest for p, digest in b.value['current_files'].items() if p.startswith('runtime/')}
        self.assertEqual(b.advance_runtime_inventory(
            b.runtime_inventory_to_parent(runtime, self.raw['runtime/mlf_byte_file.h'])), runtime)
        for path in (LITERAL, 'mlf.lock'):
            with self.subTest(path=path):
                self.assertEqual(b._from_frozen(b._to_frozen(self.raw[path], path), path), self.raw[path])
                with self.assertRaises(ValueError):
                    b.restore_path(self.raw[path] + b' ', path)
        for name, path in b.added_modules.items():
            self.assertIsNone(b.project_owner(self.raw[path], name))

    def test_old_half_updated_missing_and_extra_source_inputs_reject(self):
        b = self.binary
        for path in (LITERAL, 'mlf.lock'):
            with self.subTest(old_path=path), self.assertRaises(ValueError):
                b.restore_path(self.writer_raw[path], path)
            with self.subTest(mixed_path=path), self.assertRaises(ValueError):
                b.project_tree_bytes({**self.raw, path: self.writer_raw[path]})
        with self.assertRaises(ValueError):
            b.project_tree_bytes({p: raw for p, raw in self.raw.items() if p != LITERAL})
        with self.assertRaises(ValueError):
            b.project_tree_bytes({**self.raw, 'unexpected.hs': b''})
        with self.assertRaises(ValueError):
            b.require_registry(b.writer_value['current_registry'], 'current')

    def test_manifest_validation_retains_three_field_object_api(self):
        b = self.binary
        mutations = []
        for key, replacement in [('primitive_count', 135), ('module_count', 132),
                                 ('source_base_head', '0' * 40), ('source_base_tree', '0' * 40)]:
            value = copy.deepcopy(b.value); value[key] = replacement; mutations.append(value)
        value = copy.deepcopy(b.value); value['current_files'].pop('shared-sources.json'); mutations.append(value)
        value = copy.deepcopy(b.value); value['current_files']['extra'] = '0' * 64; mutations.append(value)
        value = copy.deepcopy(b.value); value['transition']['changed_paths'].pop(); mutations.append(value)
        value = copy.deepcopy(b.value); value['maintenance'].pop('patricia/run_integrated.py'); mutations.append(value)
        value = copy.deepcopy(b.value); value['successor']['base_head'] = '0' * 40; mutations.append(value)
        value = copy.deepcopy(b.value); value['builtin_successor']['transition']['deltas'].pop('mlf.lock'); mutations.append(value)
        value = copy.deepcopy(b.value); value['builtin_successor']['file_count'] = True; mutations.append(value)
        value = copy.deepcopy(b.value); value['builtin_successor']['transition']['added_paths'] = ['extra']; mutations.append(value)
        for value in mutations:
            trial = object.__new__(type(b))
            trial._core, trial.frozen_value, trial.value = b._core, b.frozen_value, value
            with self.assertRaises(ValueError):
                trial._validate_manifest()
        trial = object.__new__(type(b))
        trial._core, trial.frozen_value, trial.value = b._core, b.frozen_value, copy.deepcopy(b.value)
        trial._validate_manifest()
        self.assertEqual(trial.writer_value, b.writer_value)

    def test_independent_literal_and_lock_structural_guards(self):
        b, c = self.binary, self.binary._core
        b._validate_builtin_literal(self.writer_raw[LITERAL], self.raw[LITERAL])
        b._validate_builtin_lock(self.writer_raw['mlf.lock'], self.raw['mlf.lock'])
        for raw in (self.raw[LITERAL] + b' ', b'X' + self.raw[LITERAL][1:],
                    self.raw[LITERAL][:775] + b'X' + self.raw[LITERAL][776:], self.writer_raw[LITERAL]):
            with self.assertRaises(ValueError):
                b._validate_builtin_literal(self.writer_raw[LITERAL], raw)
        parsed = c.strict_json(self.raw['mlf.lock'])
        variants = []
        changed = copy.deepcopy(parsed); changed['packages'].reverse(); variants.append(changed)
        changed = copy.deepcopy(parsed); changed['packages'][0]['version'] = 'unexpected'; variants.append(changed)
        changed = copy.deepcopy(parsed); changed['extra'] = True; variants.append(changed)
        changed = copy.deepcopy(parsed)
        package = next(row for row in changed['packages'] if row['path'] == 'libraries/mlf-crates')
        package['sources']['Bootstrap/CrateArtifact.hs'] = '0' * 64; variants.append(changed)
        for changed in variants:
            with self.assertRaises(ValueError):
                b._validate_builtin_lock(self.writer_raw['mlf.lock'], c.json.dumps(changed).encode())

    def test_actual_o0_evidence_never_qualifies_the_incomplete_producer(self):
        b = self.binary
        value = b.generation_evidence
        b._validate_provenance_record(value)
        self.assertTrue(value['collector']['generation_succeeded'])
        self.assertEqual(value['collector']['optimization'], '0')
        self.assertEqual(value['comparison']['offset'], 776)
        self.assertEqual(value['comparison']['length'], 64)
        for field in ('candidate_verified', 'producer_build_complete', 'original_build_complete',
                      'toolchain_qualification', 'source_files_rewritten'):
            self.assertIs(value['collector'][field], False)
            changed = copy.deepcopy(value); changed['collector'][field] = True
            with self.assertRaises(ValueError):
                b._validate_provenance_record(changed)
        for field in ('O2_generation_verified', 'native_candidate_verified'):
            self.assertIs(value['other_qualification'][field], False)
            changed = copy.deepcopy(value); changed['other_qualification'][field] = True
            with self.assertRaises(ValueError):
                b._validate_provenance_record(changed)
        changed = copy.deepcopy(value); changed['comparison']['offset'] = 775
        with self.assertRaises(ValueError):
            b._validate_provenance_record(changed)

    def test_real_default_and_explicit_constructors(self):
        b = self.binary
        current = type(b)(b.directory, b.manifest_sha256, ROOT / 'tools/performance', source_root=ROOT)
        self.assertEqual(current.live_source_inventory(ROOT), b.value['current_files'])
        self.assertEqual(current.evidence_source_root, b.evidence_source_root)
        with self.assertRaises(ValueError):
            type(b)(b.directory, '0' * 64, ROOT / 'tools/performance', source_root=ROOT)

    def test_physical_current_relocation_and_new_metadata_corruption(self):
        b = self.binary
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / 'current-checkout'
            bundle = physical_fixture(b, self.raw, checkout)
            history = checkout / 'tools/performance'
            relocated = load_adapter(bundle).live_contract(history)
            explicit = type(b)(bundle, b.manifest_sha256, history, source_root=checkout)
            for instance in (relocated, explicit):
                self.assertEqual(instance.source_root, checkout.resolve())
                self.assertEqual(instance.evidence_source_root, b.evidence_source_root)
                self.assertEqual(instance.live_source_inventory(checkout), b.value['current_files'])
            targets = ['builtin_regeneration_contract.py', 'builtin-regeneration-migration.json',
                       'builtin-regeneration-provenance.json']
            targets += [row['file'] for row in b.value['builtin_successor']['transition']['deltas'].values()]
            for name in targets:
                path = bundle / name
                raw = path.read_bytes()
                path.write_bytes(raw + b' ')
                try:
                    with self.subTest(metadata=name), self.assertRaises(ValueError):
                        load_adapter(bundle).live_contract(history)
                finally:
                    path.write_bytes(raw)
            manifest = bundle / 'builtin-regeneration-migration.json'
            manifest.unlink()
            manifest.symlink_to(b.directory / 'builtin-regeneration-migration.json')
            with self.assertRaises(ValueError):
                load_adapter(bundle).live_contract(history)

    def test_new_implementation_pin_precedes_dependency_reads(self):
        loader = (HERE / 'source_migration_adapter.py').read_bytes()
        implementation = (HERE / 'builtin_regeneration_contract.py').read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'source_migration_adapter.py').write_bytes(loader)
            (directory / 'builtin_regeneration_contract.py').write_bytes(implementation + b' ')
            with self.assertRaisesRegex(ValueError, 'fixed builtin-regeneration source contract implementation SHA'):
                load_adapter(directory).live_contract(ROOT / 'tools/performance', source_root=ROOT)

    def test_unchanged_writer_suite_on_physical_authenticated_predecessor(self):
        b = self.binary
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / 'writer-predecessor'
            bundle = physical_fixture(b, self.raw, checkout, writer=True)
            predecessor = load_adapter(bundle).live_contract(checkout / 'tools/performance')
            self.assertEqual(predecessor.value, b.writer_value)
            self.assertEqual(predecessor.live_source_inventory(checkout), b.writer_value['current_files'])
            self.assertEqual(predecessor.evidence_source_root, b.evidence_source_root)
            print('PHYSICAL WRITER PREDECESSOR REGRESSION: unchanged historical assertions; not current-checkout coverage.', flush=True)
            command = [sys.executable, '-B']
            if sys.flags.optimize:
                command.append('-' + 'O' * sys.flags.optimize)
            command.append(str(bundle / OLD_TEST))
            subprocess.run(command, cwd=checkout, check=True, timeout=180,
                           env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})


if __name__ == '__main__':
    unittest.main()
