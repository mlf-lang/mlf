"""Strict writer-preflight source-identity tests, not native/runtime tests.

Default: use the real current checkout and real constructor. For a deliberately
bounded local check, --source-base OLD --overlay SPARSE authenticates the old
physical checkout first and transports only the pinned new files through an
explicit test-only reader. That mode does NOT establish current-filesystem
constructor, filesystem relocation, codec or runtime correctness. CI must run
this file without those options and run both unchanged historical test suites.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

options = argparse.ArgumentParser(add_help=False)
options.add_argument('--source-base', type=Path)
options.add_argument('--overlay', type=Path)
OPTIONS, remaining = options.parse_known_args()
if (OPTIONS.source_base is None) != (OPTIONS.overlay is None):
    raise ValueError('bounded test mode requires both --source-base and --overlay')
sys.argv = [sys.argv[0], *remaining]
BOUNDED = OPTIONS.overlay is not None
ROOT = OPTIONS.source_base.resolve(strict=True) if BOUNDED else Path(__file__).resolve().parents[3]
OVERLAY = OPTIONS.overlay.resolve(strict=True) if BOUNDED else ROOT
BUNDLE = Path('tools/performance/artifact-binary')


def load(path, name, virtual_path=None):
    module = types.ModuleType(name)
    module.__file__ = str(path if virtual_path is None else virtual_path)
    exec(compile(path.read_bytes(), module.__file__, 'exec'), module.__dict__)
    return module


def contract():
    loader = load(OVERLAY / BUNDLE / 'source_migration_adapter.py', 'preflight_test_loader')
    if not BOUNDED:
        return loader.live_contract(ROOT / 'tools/performance')
    print('BOUNDED AUTHENTICATED OVERLAY: not a current-filesystem constructor or relocation test.',
          flush=True)
    old_loader = load(ROOT / BUNDLE / 'source_migration_adapter.py', 'preflight_test_old_loader')
    old = old_loader.live_contract(ROOT / 'tools/performance')
    writer_path = OVERLAY / BUNDLE / 'writer_preflight_contract.py'
    if hashlib.sha256(writer_path.read_bytes()).hexdigest() != loader.CONTRACT_SOURCE_SHA256:
        raise ValueError('bounded new implementation pin')
    module = load(writer_path, 'preflight_test_contract', ROOT / BUNDLE / writer_path.name)
    raw = (OVERLAY / BUNDLE / module.MANIFEST_NAME).read_bytes()
    if old._core.sha(raw) != loader.FINAL_MANIFEST_SHA256:
        raise ValueError('bounded successor manifest pin')
    successor = old._core.strict_json(raw)
    current = object.__new__(module.Contract)
    current.__dict__.update(old.__dict__)
    current._initializing_successor = False
    current.value = module._materialize(old.value, successor)
    current.manifest_sha256 = loader.FINAL_MANIFEST_SHA256
    current._validate_manifest()
    names = set(old.metadata_paths) | {'writer_preflight_contract.py', module.MANIFEST_NAME}
    names.update(row['file'] for row in successor['transition']['deltas'].values())
    current.metadata_paths = tuple(sorted(names))
    allowed = set(module.CHANGED_PATHS) | {
        str(BUNDLE / name) for name in ('source_migration_adapter.py', 'writer_preflight_contract.py',
                                       module.MANIFEST_NAME)}
    allowed.update(str(BUNDLE / row['file']) for row in successor['transition']['deltas'].values())
    physical_read = current._core.read_file

    def bounded_read(root, name, limit=current._core.MAX_SOURCE_BYTES):
        # Production implementation remains unchanged. Only this test instance
        # routes the finite declared patch; every physical read keeps the
        # original canonical-path, no-symlink, regular-file and size gates.
        target = Path(root).resolve(strict=True) / name
        try:
            relative = str(target.relative_to(ROOT))
        except ValueError:
            return physical_read(root, name, limit)
        if relative in allowed:
            return physical_read(OVERLAY, relative, limit)
        return physical_read(root, name, limit)

    current._core.read_file = bounded_read
    return current


class WriterPreflightBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = contract()
        cls.raw = {p: cls.binary._core.read_file(ROOT, p)
                   for p in cls.binary.value['current_files']}

    def test_exact_successor_and_unchanged_historical_scope(self):
        b = self.binary
        successor = b.value['successor']
        self.assertEqual(len(b.value['current_files']), 196)
        self.assertEqual(len(b.value['current_registry']), 135)
        self.assertEqual(len(b.parent['registry']), 128)
        self.assertEqual(b.frozen_value['module_count'], 132)
        self.assertEqual(b.value['primitive_count'], 132)
        self.assertNotIn('source_head', b.value)
        self.assertEqual(b.value['graph_source_head'], 'bdc5db805975c3d77fb3eb93c6199b7452820658')
        self.assertEqual(b.value['source_base_head'], '6d829369efd58c482ac28ac6e0a8cdd96b17adb4')
        self.assertEqual(b.value['transition'], b.graph_value['transition'])
        self.assertEqual(b.value['maintenance'], b.graph_value['maintenance'])
        self.assertEqual(sorted(p for p in b.graph_value['current_files']
                              if b.graph_value['current_files'][p] != b.value['current_files'][p]),
                         successor['transition']['changed_paths'])
        self.assertEqual([n for n in b.graph_value['current_registry']
                          if b.graph_value['current_registry'][n] != b.value['current_registry'][n]],
                         ['Bootstrap.CrateArtifact'])
        self.assertIn('no new runtime or generation qualification', successor['qualification_scope'])

    def test_complete_public_roundtrips_and_live_byte_gates(self):
        b = self.binary
        old = b.project_tree_bytes(self.raw)
        additions = {p: self.raw[p] for p in b.added_paths}
        self.assertEqual(b.advance_tree_bytes(old, additions), self.raw)
        self.assertEqual(b.advance_lock(b.restore_previous_lock(self.raw['mlf.lock'])), self.raw['mlf.lock'])
        registry = b.live_registry(ROOT)
        self.assertEqual(b.live_source_inventory(ROOT), b.value['current_files'])
        self.assertEqual(b.advance_registry(b.registry_to_parent(registry, b.added_source_bytes(ROOT))), registry)
        hosts = b.live_host_inventory(ROOT)
        self.assertEqual(b.advance_host_inventory(b.host_inventory_to_parent(hosts)), hosts)
        runtime = {p: h for p, h in b.value['current_files'].items() if p.startswith('runtime/')}
        self.assertEqual(b.advance_runtime_inventory(
            b.runtime_inventory_to_parent(runtime, self.raw['runtime/mlf_byte_file.h'])), runtime)
        for path in b.value['successor']['transition']['changed_paths']:
            with self.subTest(path=path):
                frozen = b._to_frozen(self.raw[path], path)
                self.assertEqual(b._from_frozen(frozen, path), self.raw[path])
                with self.assertRaises(ValueError):
                    b.restore_path(self.raw[path] + b' ', path)

    def test_old_and_half_repaired_inputs_fail_closed(self):
        b = self.binary
        rows = b.value['successor']['transition']['deltas']
        old = {p: b._apply(self.raw[p], p, rows, True) for p in rows}
        for path in rows:
            with self.subTest(old_path=path), self.assertRaises(ValueError):
                b.restore_path(old[path], path)
            mixed = {**self.raw, path: old[path]}
            with self.subTest(mixed_path=path), self.assertRaises(ValueError):
                b.project_tree_bytes(mixed)
        with self.assertRaises(ValueError):
            b.require_registry(b.graph_value['current_registry'], 'current')

    def test_manifest_validation_needs_only_existing_three_fields(self):
        b = self.binary
        values = []
        for field, replacement in [('primitive_count', 135), ('module_count', 132),
                                   ('source_base_head', '0' * 40)]:
            value = copy.deepcopy(b.value); value[field] = replacement; values.append(value)
        value = copy.deepcopy(b.value); value['current_files'].pop('shared-sources.json'); values.append(value)
        value = copy.deepcopy(b.value); value['transition']['changed_paths'].pop(); values.append(value)
        value = copy.deepcopy(b.value); value['maintenance'].pop('patricia/run_integrated.py'); values.append(value)
        value = copy.deepcopy(b.value); value['successor']['transition']['deltas'].pop('mlf.lock'); values.append(value)
        value = copy.deepcopy(b.value); value['successor']['graph_manifest_sha256'] = '0' * 64; values.append(value)
        value = copy.deepcopy(b.value); value['successor']['transition']['added_paths'] = ['extra']; values.append(value)
        for value in values:
            trial = object.__new__(type(b))
            trial._core, trial.frozen_value, trial.value = b._core, b.frozen_value, value
            with self.assertRaises(ValueError):
                trial._validate_manifest()
        trial = object.__new__(type(b))
        trial._core, trial.frozen_value, trial.value = b._core, b.frozen_value, copy.deepcopy(b.value)
        trial._validate_manifest()

    def test_exact_lock_structure_without_current_outer_hash(self):
        b = self.binary
        rows = b.value['successor']['transition']['deltas']
        graph_raw = b._apply(self.raw['mlf.lock'], 'mlf.lock', rows, True)
        b._validate_successor_lock(graph_raw, self.raw['mlf.lock'])
        lock = b._core.strict_json(self.raw['mlf.lock'])
        variants = []
        changed = copy.deepcopy(lock); changed['packages'].reverse(); variants.append(changed)
        changed = copy.deepcopy(lock); changed['packages'][0]['version'] = 'unexpected'; variants.append(changed)
        changed = copy.deepcopy(lock)
        crates = next(row for row in changed['packages'] if row['path'] == 'libraries/mlf-crates')
        crates['sources']['Bootstrap/CrateGraph.hs'] = '0' * 64; variants.append(changed)
        changed = copy.deepcopy(lock); changed['extra'] = True; variants.append(changed)
        for changed in variants:
            with self.assertRaises(ValueError):
                b._validate_successor_lock(graph_raw, b._core.json.dumps(changed).encode())

    def test_new_metadata_authentication_and_complete_closure(self):
        b, c = self.binary, self.binary._core
        rows = b.value['successor']['transition']['deltas']
        required = {'writer_preflight_contract.py', 'writer-preflight-migration.json',
                    'query_graph_contract.py', 'query-graph-migration.json'}
        required.update(row['file'] for row in rows.values())
        self.assertTrue(required.issubset(b.metadata_paths))
        physical_read = c.read_file
        manifest = physical_read(b.directory, 'writer-preflight-migration.json')
        for damaged in (manifest + b' ', b'{}'):
            trial = object.__new__(type(b))
            trial._core, trial.frozen_value = c, b.frozen_value
            trial.value, trial.directory = copy.deepcopy(b.graph_value), b.directory
            trial._initializing_successor, trial._successor_sha256 = True, b.manifest_sha256
            def read(root, name, limit=c.MAX_SOURCE_BYTES):
                return damaged if name == 'writer-preflight-migration.json' else physical_read(root, name, limit)
            with patch.object(c, 'read_file', read), self.assertRaises(ValueError):
                trial._validate_manifest()
        for path, row in rows.items():
            raw = physical_read(b.directory, row['file'])
            def read(root, name, limit=c.MAX_SOURCE_BYTES):
                return raw + b' ' if name == row['file'] else physical_read(root, name, limit)
            with self.subTest(delta=path), patch.object(c, 'read_file', read), self.assertRaises(ValueError):
                b._to_frozen(self.raw[path], path)

    def test_new_implementation_pin_precedes_any_missing_metadata(self):
        loader_raw = (OVERLAY / BUNDLE / 'source_migration_adapter.py').read_bytes()
        writer_raw = (OVERLAY / BUNDLE / 'writer_preflight_contract.py').read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'source_migration_adapter.py').write_bytes(loader_raw)
            (directory / 'writer_preflight_contract.py').write_bytes(writer_raw + b' ')
            loader = load(directory / 'source_migration_adapter.py', 'preflight_corrupt_loader')
            with self.assertRaisesRegex(ValueError, 'fixed writer-preflight source contract implementation SHA'):
                loader.live_contract(ROOT / 'tools/performance', source_root=ROOT)

    @unittest.skipIf(BOUNDED, 'Requires a real repaired checkout; bounded overlay is not constructor coverage.')
    def test_real_default_and_explicit_constructor(self):
        b = self.binary
        current = type(b)(b.directory, b.manifest_sha256, ROOT / 'tools/performance', source_root=ROOT)
        self.assertEqual(current.live_source_inventory(ROOT), b.value['current_files'])
        self.assertEqual(current.evidence_source_root, b.evidence_source_root)
        with self.assertRaises(ValueError):
            type(b)(b.directory, '0' * 64, ROOT / 'tools/performance', source_root=ROOT)


if __name__ == '__main__':
    unittest.main()
