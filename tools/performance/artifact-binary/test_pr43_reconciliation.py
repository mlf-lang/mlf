#!/usr/bin/env python3
"""Independent transition checks and immutable predecessor regression replay."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

from source_migration_adapter import live_contract

ROOT = Path(__file__).resolve().parents[3]
HISTORY = ROOT / 'tools/performance'


class PR43SourceReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = live_contract(HISTORY)

    def test_formatter_follow_on_is_exactly_the_reviewed_live_delta(self):
        # Keep the previously published endpoint independently recoverable. This
        # is source provenance, not a claim that old measurements cover new code.
        base = 'd925341c0f617db3ba9847a1975cc8720196f400'
        git = ['git', '--no-replace-objects', '-C', str(ROOT)]
        def archived(path):
            return subprocess.check_output([*git, 'show', base + ':' + path])
        tree = subprocess.check_output([*git, 'rev-parse', base + '^{tree}'], text=True).strip()
        self.assertEqual(tree, 'feb2870d5067b8b434b2ebaf2843d468288838c7')
        manifest = archived('tools/performance/artifact-binary/pr43-reconciliation-migration.json')
        self.assertEqual(hashlib.sha256(manifest).hexdigest(),
                         'f0379aba40e33ae97d57381658ad1f7d12756831af9ea604dd3ab063ff107bf4')
        prior = json.loads(manifest)
        c = self.contract
        previous_endpoint = dict(c.previous.value['current_files'])
        previous_endpoint.update({p: row[1] for p, row in prior['changes'].items()})
        previous_endpoint.update(prior['additions'])
        reviewed = {
            'bootstrap/MLF/BuiltinPreludeData.hs',
            'libraries/mlf-crates/Bootstrap/SourceInference.hs',
            'libraries/mlf-frontend/Bootstrap/Layout.hs',
            'mlf.lock',
            'tests/shared/MLF/Tests/SharedFrontend.hs',
            'tools/shared/build.py',
        }
        self.assertEqual(set(previous_endpoint), set(c.value['current_files']))
        self.assertEqual({p for p, digest in previous_endpoint.items()
                          if c.value['current_files'][p] != digest}, reviewed)
        for path in reviewed:
            old = archived(path)
            self.assertEqual(hashlib.sha256(old).hexdigest(), previous_endpoint[path])
            # A previous-endpoint source or unreviewed byte must not pass as live.
            for wrong in (old, (ROOT / path).read_bytes() + b' '):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    c.restore_path(wrong, path)
        current = json.loads((c.directory / 'pr43-reconciliation-migration.json').read_bytes())
        for field in ('format', 'predecessor', 'additions', 'maintenance'):
            self.assertEqual(current[field], prior[field])
        for path, row in prior['changes'].items():
            self.assertEqual(current['changes'][path][0], row[0])
            if path not in reviewed:
                self.assertEqual(current['changes'][path], row)

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
            manifest = directory / 'pr43-reconciliation-migration.json'
            raw = manifest.read_bytes().replace(c.changes['mlf.lock'][1].encode(), b'0' * 64)
            manifest.write_bytes(raw)
            wrong = hashlib.sha256(raw).hexdigest()
            self.assertNotEqual(wrong, c.manifest_sha256)
            for digest in (c.manifest_sha256, wrong):
                with self.subTest(digest=digest), self.assertRaises(ValueError):
                    type(c)(directory, digest, HISTORY, source_root=ROOT)

    def test_rejected_manifest_does_not_materialize_a_predecessor(self):
        from unittest.mock import patch
        c = self.contract
        module = sys.modules[type(c).__module__]
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            (directory / 'pr43-reconciliation-migration.json').write_bytes(b'{}')
            with patch.object(module, 'archived_checkout',
                              side_effect=AssertionError('invalid manifest reached archive')):
                with self.assertRaisesRegex(ValueError, 'successor manifest SHA'):
                    type(c)(directory, c.manifest_sha256, HISTORY, source_root=ROOT)

    def test_verified_predecessor_module_reuses_its_original_cache(self):
        c = self.contract
        module = sys.modules[type(c).__module__]
        path = c.archived / 'tools/performance/artifact-binary/declid_contract.py'
        self.assertIs(module.module_at(path), module.module_at(path))

    def test_changed_maintenance_files_reconstruct_the_original_oracles(self):
        c = self.contract
        for name in c.maintenance:
            live = (HISTORY / name).read_bytes()
            previous = (c.archived / 'tools/performance' / name).read_bytes()
            self.assertEqual(c.restore_maintenance(live, name), c.previous.restore_maintenance(previous, name))
            for wrong in (previous, live + b' '):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    c.restore_maintenance(wrong, name)

    def test_predecessor_suite_source_is_unchanged(self):
        c = self.contract
        for name in ('test_declid_migration.py',):
            script = Path('tools/performance/artifact-binary', name)
            self.assertEqual((ROOT / script).read_bytes(), (c.archived / script).read_bytes())
            # The unchanged suite runs in a separate process after this one
            # exits, so its own archive does not overlap this contract's two.
            self.assertTrue((c.archived / script).is_file())


if __name__ == '__main__':
    unittest.main()
