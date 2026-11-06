"""Finite source-identity controls for the graph135 -> binary132 -> historical128 bridge.

No compiler is built and no runtime or builtin regeneration is claimed.
"""
from pathlib import Path
import copy
import json
import os
import shutil
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def load_adapter(directory=HERE):
    path = directory / 'source_migration_adapter.py'
    result = types.ModuleType('graph_boundary_adapter')
    result.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), result.__dict__)
    return result


class QueryGraphSourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = load_adapter().live_contract(ROOT / 'tools/performance')
        cls.raw = {p: (ROOT / p).read_bytes() for p in cls.binary.value['current_files']}

    def test_actual_current_identity_and_historical_generation_scope(self):
        b = self.binary
        self.assertEqual(len(b.live_registry(ROOT)), 135)
        self.assertEqual(len(b.live_source_inventory(ROOT)), 196)
        self.assertEqual(len(b.parent['registry']), 128)
        self.assertEqual(len(b.parent['files']), 188)
        self.assertEqual(b.value['primitive_count'], 132)
        self.assertEqual(b.frozen_value['module_count'], 132)
        self.assertNotEqual(b.frozen_value['generation']['output_sha256'],
                            b.value['current_files']['bootstrap/MLF/BuiltinPreludeData.hs'])
        self.assertIn('no new runtime or generation qualification', b.value['qualification_scope'])

    def test_whole_tree_and_lock_exact_roundtrip(self):
        b = self.binary
        old = b.project_tree_bytes(self.raw)
        additions = {p: self.raw[p] for p in b.added_paths}
        self.assertEqual(len(additions), 8)
        self.assertEqual(b.advance_tree_bytes(old, additions), self.raw)
        self.assertEqual(b.restore_previous_lock(self.raw['mlf.lock']), old['mlf.lock'])
        self.assertEqual(b.advance_lock(old['mlf.lock']), self.raw['mlf.lock'])
        for p in b.value['transition']['changed_paths']:
            frozen = b._to_frozen(self.raw[p], p)
            self.assertEqual(b._from_frozen(frozen, p), self.raw[p])

    def test_exact_current_and_added_byte_inventory(self):
        b = self.binary
        for p in list(b.value['transition']['changed_paths']) + list(b.value['transition']['added_paths']) + [
                'host/ghc/MLF/Host/Base.hs', 'runtime/mlf_runtime.c']:
            with self.subTest(path=p), self.assertRaises(ValueError):
                b.restore_path(self.raw[p] + b' ', p)
        old = b.project_tree_bytes(self.raw)
        additions = {p: self.raw[p] for p in b.added_paths}
        for p in additions:
            bad = dict(additions)
            del bad[p]
            with self.subTest(missing=p), self.assertRaises(ValueError):
                b.advance_tree_bytes(old, bad)
        for label, bad in [('missing', {p: raw for p, raw in self.raw.items()
                                       if p != 'shared-sources.json'}),
                           ('extra', {**self.raw, 'unexpected.hs': b''})]:
            with self.subTest(label=label), self.assertRaises(ValueError):
                b.project_tree_bytes(bad)

    def test_registry_requires_all_seven_real_added_modules(self):
        b = self.binary
        current = b.live_registry(ROOT)
        additions = b.added_source_bytes(ROOT)
        self.assertEqual(len(additions), 7)
        self.assertEqual(b.advance_registry(b.registry_to_parent(current, additions)), current)
        for n in additions:
            bad = dict(additions)
            del bad[n]
            with self.subTest(missing=n), self.assertRaises(ValueError):
                b.registry_to_parent(current, bad)
            bad = {**additions, n: additions[n] + b' '}
            with self.subTest(wrong=n), self.assertRaises(ValueError):
                b.registry_to_parent(current, bad)
        missing = dict(current)
        del missing[next(iter(missing))]
        mixed = dict(current)
        changed = next(n for n in b.parent['registry'] if b.parent['registry'][n] != current[n])
        mixed[changed] = b.parent['registry'][changed]
        for bad in [missing, mixed, b.frozen_value['current_registry'], b.parent['registry'],
                    {**current, 'Unexpected.Module': '0' * 64}]:
            with self.assertRaises(ValueError):
                b.require_registry(bad, 'current')

    def test_owner_deletion_and_host_runtime_bridges(self):
        b = self.binary
        for name, path in b.added_modules.items():
            self.assertIsNone(b.project_owner(self.raw[path], name))
        current = b.live_host_inventory(ROOT)
        parent = b.host_inventory_to_parent(current)
        self.assertEqual(b.advance_host_inventory(parent), current)
        bad = {**current, 'unexpected': '0' * 64}
        with self.assertRaises(ValueError):
            b.host_inventory_to_parent(bad)
        names = b.parent['legacy_host_bridge']
        subset = {p: current[p] for p in names}
        self.assertEqual(b.advance_legacy_host_subset(b.legacy_host_subset_to_parent(subset)), subset)
        with self.assertRaises(ValueError):
            b.legacy_host_subset_to_parent(bad)
        runtime = {p: h for p, h in b.value['current_files'].items() if p.startswith('runtime/')}
        old = b.runtime_inventory_to_parent(runtime, self.raw['runtime/mlf_byte_file.h'])
        self.assertEqual(b.advance_runtime_inventory(old), runtime)
        with self.assertRaises(ValueError):
            b.runtime_inventory_to_parent(runtime, b'wrong header')

    def test_two_maintenance_bridges_preserve_exact_frozen_history(self):
        b = self.binary
        for name in b.value['maintenance']:
            raw = (ROOT / 'tools/performance' / name).read_bytes()
            frozen = b._maintenance_to_frozen(raw, name)
            self.assertEqual(b._core.sha(frozen), b.frozen_value['maintenance'][name]['new'])
            old = b.restore_maintenance(raw, name)
            self.assertEqual(b._core.sha(old), b.maintenance_parent['files'][name]['sha256'])
            for bad in (raw + b' ', frozen):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    b.restore_maintenance(bad, name)

    def test_manifest_rejects_undeclared_paths_counts_and_mixed_pins(self):
        b = self.binary
        mutations = []
        bad = copy.deepcopy(b.value); bad['primitive_count'] = 135; mutations.append(bad)
        bad = copy.deepcopy(b.value); bad['module_count'] = 132; mutations.append(bad)
        bad = copy.deepcopy(b.value); bad['current_files'].pop('shared-sources.json'); mutations.append(bad)
        bad = copy.deepcopy(b.value); bad['current_files']['extra'] = '0' * 64; mutations.append(bad)
        bad = copy.deepcopy(b.value); bad['transition']['changed_paths'].pop(); mutations.append(bad)
        bad = copy.deepcopy(b.value); bad['maintenance'].pop('patricia/run_integrated.py'); mutations.append(bad)
        for value in mutations:
            trial = object.__new__(type(b))
            trial._core, trial.frozen_value, trial.value = b._core, b.frozen_value, value
            with self.assertRaises(ValueError):
                trial._validate_manifest()

    def test_metadata_relocation_and_mutation_fail_closed(self):
        b = self.binary
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'artifact-binary'
            for name in b.metadata_paths:
                destination = directory / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(b.directory / name, destination)
            relocated = load_adapter(directory).live_contract(
                ROOT / 'tools/performance', source_root=ROOT)
            self.assertEqual(relocated.live_registry(ROOT), b.value['current_registry'])
            self.assertEqual(relocated.evidence_source_root, b.evidence_source_root)
            targets = ['query_graph_contract.py', 'query-graph-migration.json', 'source_contract.py',
                       'source-migration.json', 'builtin-verification-receipt.json',
                       'parent-inventory.json', 'maintenance-parents.json']
            targets += [row['file'] for row in b.value['transition']['deltas'].values()]
            targets += [row['file'] for row in b.value['maintenance'].values()]
            targets += [row['file'] for row in b.frozen_value['deltas'].values()]
            targets += [row['file'] for row in b.frozen_value['maintenance'].values()]
            for name in targets:
                path = directory / name
                raw = path.read_bytes()
                path.write_bytes(raw + b' ')
                try:
                    with self.subTest(metadata=name), self.assertRaises(ValueError):
                        candidate = load_adapter(directory).live_contract(
                            ROOT / 'tools/performance', source_root=ROOT)
                        candidate.project_tree_bytes(self.raw)
                finally:
                    path.write_bytes(raw)
            manifest = directory / 'query-graph-migration.json'
            raw = manifest.read_bytes()
            manifest.unlink()
            manifest.symlink_to(b.directory / 'query-graph-migration.json')
            with self.assertRaises(ValueError):
                load_adapter(directory).live_contract(ROOT / 'tools/performance', source_root=ROOT)
            manifest.unlink()
            manifest.write_bytes(raw)

    def test_bounded_implementation_readers(self):
        readers = [load_adapter().read_implementation,
                   type(self.binary).__init__.__globals__['read_implementation']]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            regular = root / 'code.py'
            regular.write_bytes(b'bounded regular implementation\n')
            oversized = root / 'oversized.py'
            oversized.write_bytes(b'x' * 65537)
            linked = root / 'linked.py'
            linked.symlink_to(regular)
            rejected = [root, oversized, linked]
            if hasattr(os, 'mkfifo'):
                fifo = root / 'fifo.py'
                os.mkfifo(fifo)
                rejected.append(fifo)
            for read in readers:
                self.assertEqual(read(regular), regular.read_bytes())
                for path in rejected:
                    with self.subTest(reader=read, path=path), self.assertRaises(ValueError):
                        read(path)

    def test_shared_and_lock_structural_guards_beyond_outer_hashes(self):
        b = self.binary
        frozen = {p: b._to_frozen(self.raw[p], p) for p in b.frozen_value['current_files']}
        shared = json.loads(self.raw['shared-sources.json'])
        bad_shared = []
        changed = copy.deepcopy(shared)
        changed['primitive_abi'] = 'mlf-primitive-135-v7'
        bad_shared.append(changed)
        changed = copy.deepcopy(shared)
        changed['modules'][-1]['role'] = 'unexpected'
        bad_shared.append(changed)
        changed = copy.deepcopy(shared)
        changed['modules'].pop()
        bad_shared.append(changed)
        for changed in bad_shared:
            current = {**self.raw, 'shared-sources.json': json.dumps(changed).encode()}
            with self.assertRaises(ValueError):
                b._validate_metadata_transition(frozen, current)
        lock = json.loads(self.raw['mlf.lock'])
        bad_locks = []
        for key in ('version', 'manifest'):
            changed = copy.deepcopy(lock)
            changed['packages'][0][key] = 'wrong'
            bad_locks.append(changed)
        changed = copy.deepcopy(lock)
        package = next(row for row in changed['packages'] if row['path'] == 'libraries/mlf-crates')
        del package['sources']['Bootstrap/CrateGraph.hs']
        bad_locks.append(changed)
        changed = copy.deepcopy(lock)
        package = next(row for row in changed['packages'] if row['path'] == 'libraries/mlf-crates')
        package['sources']['Unexpected.hs'] = '0' * 64
        bad_locks.append(changed)
        changed = copy.deepcopy(lock)
        changed['packages'].reverse()
        bad_locks.append(changed)
        for changed in bad_locks:
            current = {**self.raw, 'mlf.lock': json.dumps(changed).encode()}
            with self.assertRaises(ValueError):
                b._validate_metadata_transition(frozen, current)


if __name__ == '__main__':
    unittest.main()

