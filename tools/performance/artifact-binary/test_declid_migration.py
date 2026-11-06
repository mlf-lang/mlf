#!/usr/bin/env python3
"""Independent transition checks and immutable predecessor regression replay."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest

from source_migration_adapter import live_contract

ROOT = Path(__file__).resolve().parents[3]
HISTORY = ROOT / 'tools/performance'


class DeclIdSourceTransition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = live_contract(HISTORY)

    def test_complete_tree_projections_recover_exact_predecessor_and_live_inputs(self):
        c = self.contract
        raw = {p: (ROOT / p).read_bytes() for p in c.value['current_files']}
        ancestor = c.project_tree_bytes(raw)
        added = {p: raw[p] for p in c.added_paths}
        self.assertEqual(c.advance_tree_bytes(ancestor, added), raw)
        changed = next(iter(c.changes))
        for name, bad in [('wrong source', {**raw, changed: raw[changed] + b' '}),
                          ('wrong old source', {**raw, changed: (c.archived / changed).read_bytes()}),
                          ('extra file', {**raw, 'extra': b''}), ('missing file', {p: v for p, v in raw.items() if p != changed})]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                c.project_tree_bytes(bad)
        with self.assertRaises(ValueError):
            c.advance_tree_bytes(ancestor, {})

    def test_current_registry_host_and_runtime_round_trips(self):
        c = self.contract
        current = c.live_registry(ROOT)
        self.assertIn('Bootstrap.IndexVec', current)
        self.assertIn('Bootstrap.Resolved', current)
        restored = c.registry_to_parent(current, c.added_source_bytes(ROOT))
        self.assertEqual(c.advance_registry(restored), current)
        with self.assertRaises(ValueError):
            c.require_registry(c.previous.value['current_registry'], 'current')
        host = c.live_host_inventory(ROOT)
        self.assertEqual(c.advance_host_inventory(c.host_inventory_to_parent(host)), host)
        with self.assertRaises(ValueError):
            c.host_inventory_to_parent({})
        rt = {p: h for p, h in c.value['current_files'].items() if p.startswith('runtime/')}
        parent = c.runtime_inventory_to_parent(rt, (ROOT / 'runtime/mlf_byte_file.h').read_bytes())
        self.assertEqual(c.advance_runtime_inventory(parent), rt)
        with self.assertRaises(ValueError):
            c.runtime_inventory_to_parent(rt, b'wrong header')

    def test_relocated_sources_reject_drift_symlinks_and_registry_changes(self):
        c = self.contract
        with tempfile.TemporaryDirectory() as out:
            root = Path(out)
            for path in c.value['current_files']:
                file = root / path
                file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, file)
            self.assertEqual(c.live_source_inventory(root), c.value['current_files'])
            for path in ('shared-sources.json', 'libraries/mlf-foundation/Bootstrap/IndexVec.hs', 'mlf.lock'):
                file = root / path
                file.write_bytes(file.read_bytes() + b'\n')
                with self.subTest(path=path), self.assertRaises(ValueError):
                    c.live_source_inventory(root)
                file.unlink()
                file.symlink_to(ROOT / path)
                with self.subTest(symlink=path), self.assertRaises(ValueError):
                    c.live_source_inventory(root)
                file.unlink()
                shutil.copyfile(ROOT / path, file)

    def test_rehashed_manifest_cannot_admit_a_different_source(self):
        c = self.contract
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            for path in c.metadata_paths:
                copy = directory / path
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(c.directory / path, copy)
            manifest = directory / 'declid-source-migration.json'
            raw = manifest.read_bytes().replace(c.changes['mlf.lock'][1].encode(), b'0' * 64)
            manifest.write_bytes(raw)
            wrong = hashlib.sha256(raw).hexdigest()
            self.assertNotEqual(wrong, c.manifest_sha256)
            for digest in (c.manifest_sha256, wrong):
                with self.subTest(digest=digest), self.assertRaises(ValueError):
                    type(c)(directory, digest, HISTORY, source_root=ROOT)

    def test_changed_maintenance_files_reconstruct_the_original_oracles(self):
        c = self.contract
        for name in c.maintenance:
            live = (HISTORY / name).read_bytes()
            previous = (c.archived / 'tools/performance' / name).read_bytes()
            self.assertEqual(c.restore_maintenance(live, name), c.previous.restore_maintenance(previous, name))
            for wrong in (previous, live + b' '):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    c.restore_maintenance(wrong, name)

    def test_historical_graph_writer_and_builtin_suites_on_authenticated_parent(self):
        c = self.contract
        for name in ('test_query_graph_migration.py', 'test_builtin_regeneration_migration.py'):
            script = Path('tools/performance/artifact-binary', name)
            self.assertEqual((ROOT / script).read_bytes(), (c.archived / script).read_bytes())
            options = ['-O'] if sys.flags.optimize else []
            subprocess.run([sys.executable, *options, '-B', script], cwd=c.archived, check=True)


if __name__ == '__main__':
    unittest.main()
