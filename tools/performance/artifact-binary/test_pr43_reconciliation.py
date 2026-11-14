#!/usr/bin/env python3
"""Independent transition checks and immutable predecessor regression replay."""
from pathlib import Path
import copy
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
MACOS_BASE = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
MACOS_BASE_TREE = '3148203097e7622ced1b272e606bfa892fad746b'
MACOS_BASE_MANIFEST = '63598306f049a050def3fd21ddf21878a7f4f882b59a48a86c53a3398624e9c5'
MACOS_PATH = 'tools/shared/build.py'
MACOS_BASE_SOURCE = 'eff291112f318206ce0f7ab85cb8a2e474be41489441204696630a395f4ca3df'


PERFORMANCE_BASE = 'fc300bc9fdc389b585cbef0630fc8915d53e89c5'

def performance_base_bytes(path):
    return subprocess.check_output(['git', '--no-replace-objects', '-C', str(ROOT),
                                    'show', PERFORMANCE_BASE + ':' + path])

def base_spec():
    return json.loads(performance_base_bytes('tools/performance/artifact-binary/pr43-reconciliation-migration.json'))

def base_files(contract):
    spec = base_spec()
    files = dict(contract.previous.value['current_files'])
    files.update({p: row[1] for p, row in spec['changes'].items()})
    files.update(spec['additions'])
    return files

def main_bytes(path):
    return subprocess.check_output(['git', '--no-replace-objects', '-C', str(ROOT),
                                    'show', MACOS_BASE + ':' + path])


class PR43SourceReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = live_contract(HISTORY)

    def test_macos_repair_is_exactly_the_declared_main_follow_on(self):
        c = self.contract
        tree = subprocess.check_output(['git', '--no-replace-objects', '-C', str(ROOT),
                                        'rev-parse', MACOS_BASE + '^{tree}'], text=True).strip()
        self.assertEqual(tree, MACOS_BASE_TREE)
        raw = main_bytes('tools/performance/artifact-binary/pr43-reconciliation-migration.json')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), MACOS_BASE_MANIFEST)
        prior = json.loads(raw)
        before = dict(c.previous.value['current_files'])
        before.update({p: row[1] for p, row in prior['changes'].items()})
        before.update(prior['additions'])
        self.assertEqual(set(before), set(base_files(c)))
        self.assertEqual({p for p in before if before[p] != base_files(c)[p]}, {MACOS_PATH})
        self.assertEqual(before[MACOS_PATH], MACOS_BASE_SOURCE)
        self.assertEqual(hashlib.sha256(main_bytes(MACOS_PATH)).hexdigest(), MACOS_BASE_SOURCE)
        current = base_spec()
        transition = current.pop('live_transition')
        self.assertEqual(transition, {
            'predecessor': MACOS_BASE, 'predecessor_tree': MACOS_BASE_TREE,
            'predecessor_manifest_sha256': MACOS_BASE_MANIFEST,
            'changes': {MACOS_PATH: [MACOS_BASE_SOURCE, base_files(c)[MACOS_PATH]]},
        })
        # Rewind precisely one live endpoint. Everything else, including all
        # first endpoints and the Patricia maintenance boundary, must be equal.
        self.assertEqual(current['changes'][MACOS_PATH][0], prior['changes'][MACOS_PATH][0])
        current['changes'][MACOS_PATH][1] = MACOS_BASE_SOURCE
        self.assertEqual(current, prior)

    def test_macos_transition_validator_cannot_expand_or_rewrite_the_delta(self):
        c = self.contract
        module = sys.modules[type(c).__module__]
        spec = json.loads((c.directory / 'pr43-reconciliation-migration.json').read_bytes())
        module.validate_live_transition(spec, ROOT, c.core)
        mutations = []
        def changed(label, mutate):
            value = copy.deepcopy(spec)
            mutate(value)
            mutations.append((label, value))
        changed('old source endpoint', lambda s: s['changes'][MACOS_PATH].__setitem__(0, '0' * 64))
        changed('another live endpoint', lambda s: s['changes']['mlf.lock'].__setitem__(1, '0' * 64))
        changed('added path', lambda s: s['additions'].__setitem__('extra', '0' * 64))
        changed('maintenance endpoint', lambda s: s['maintenance']['patricia/test_adapters.py'].__setitem__(1, '0' * 64))
        changed('wrong base commit', lambda s: s['live_transition'].__setitem__('predecessor', '0' * 40))
        changed('wrong base tree', lambda s: s['live_transition'].__setitem__('predecessor_tree', '0' * 40))
        changed('wrong base manifest', lambda s: s['live_transition'].__setitem__('predecessor_manifest_sha256', '0' * 64))
        changed('wrong prior bytes', lambda s: s['live_transition']['changes'][MACOS_PATH].__setitem__(0, '0' * 64))
        changed('wrong current bytes', lambda s: s['live_transition']['changes'][MACOS_PATH].__setitem__(1, '0' * 64))
        changed('extra transition path', lambda s: s['live_transition']['changes'].__setitem__('mlf.lock', ['0' * 64, '1' * 64]))
        changed('unchanged endpoint', lambda s: s['changes'][MACOS_PATH].__setitem__(1, MACOS_BASE_SOURCE))
        for label, value in mutations:
            with self.subTest(label=label), self.assertRaises(ValueError):
                module.validate_live_transition(value, ROOT, c.core)

    def test_macos_source_rejects_prior_mutated_and_wrong_layer_bytes(self):
        c = self.contract
        live = (ROOT / MACOS_PATH).read_bytes()
        prior = main_bytes(MACOS_PATH)
        predecessor = (c.archived / MACOS_PATH).read_bytes()
        ancestor = c.restore_path(live, MACOS_PATH)
        self.assertEqual(c.advance_path(ancestor, MACOS_PATH), live)
        for label, raw in [('main', prior), ('PR43 predecessor', predecessor), ('mutated', live + b' ')]:
            with self.subTest(restore=label), self.assertRaises(ValueError):
                c.restore_path(raw, MACOS_PATH)
        for label, raw in [('main', prior), ('live', live), ('mutated ancestor', ancestor + b' ')]:
            with self.subTest(advance=label), self.assertRaises(ValueError):
                c.advance_path(raw, MACOS_PATH)
        with self.assertRaises(ValueError):
            c.previous.restore_path(live, MACOS_PATH)
        raw = {p: (ROOT / p).read_bytes() for p in c.value['current_files']}
        with self.assertRaises(ValueError):
            c.project_tree_bytes({**raw, MACOS_PATH: prior})

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
        self.assertEqual(set(previous_endpoint), set(base_files(c)))
        self.assertEqual({p for p, digest in previous_endpoint.items()
                          if base_files(c)[p] != digest}, reviewed)
        for path in reviewed:
            old = archived(path)
            self.assertEqual(hashlib.sha256(old).hexdigest(), previous_endpoint[path])
            # A previous-endpoint source or unreviewed byte must not pass as live.
            for wrong in (old, (ROOT / path).read_bytes() + b' '):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    c.restore_path(wrong, path)
        current = base_spec()
        for field in ('format', 'predecessor', 'additions'):
            self.assertEqual(current[field], prior[field])
        # Only the live Patricia boundary test follows the Layout overlap.
        # Its frozen predecessor oracle and every other maintenance row remain
        # unchanged, and the production constructor authenticates the new SHA.
        maintenance = 'patricia/test_adapters.py'
        self.assertEqual(set(current['maintenance']), set(prior['maintenance']))
        self.assertEqual({p for p in prior['maintenance']
                          if current['maintenance'][p] != prior['maintenance'][p]}, {maintenance})
        self.assertEqual(current['maintenance'][maintenance][0], prior['maintenance'][maintenance][0])
        self.assertEqual(current['maintenance'][maintenance][1],
                         hashlib.sha256((HISTORY / maintenance).read_bytes()).hexdigest())
        for path, row in prior['changes'].items():
            self.assertEqual(current['changes'][path][0], row[0])
            if path not in reviewed:
                self.assertEqual(current['changes'][path], row)

    def test_performance_follow_on_exact_paths_and_negative_controls(self):
        c = self.contract
        module = sys.modules[type(c).__module__]
        spec = json.loads((c.directory / 'pr43-reconciliation-migration.json').read_bytes())
        baseline = base_files(c)
        changes = spec['performance_transition']['changes']
        self.assertEqual(set(changes), module.PERFORMANCE_PATHS)
        self.assertEqual({p for p in baseline if baseline[p] != c.value['current_files'][p]}, set(changes))
        for path, (old, new) in changes.items():
            self.assertEqual(old, hashlib.sha256(performance_base_bytes(path)).hexdigest())
            self.assertEqual(old, baseline[path])
            self.assertEqual(new, hashlib.sha256((ROOT / path).read_bytes()).hexdigest())
            with self.subTest(path=path), self.assertRaises(ValueError):
                c.restore_path((ROOT / path).read_bytes() + b' ', path)
            with self.subTest(previous=path), self.assertRaises(ValueError):
                c.restore_path(performance_base_bytes(path), path)
        for mutation in ('old', 'new', 'missing', 'extra', 'base', 'tree', 'manifest'):
            bad = copy.deepcopy(spec)
            transition = bad['performance_transition']
            path = sorted(changes)[0]
            if mutation == 'old': transition['changes'][path][0] = '0' * 64
            elif mutation == 'new': transition['changes'][path][1] = '0' * 64
            elif mutation == 'missing': del transition['changes'][path]
            elif mutation == 'extra': transition['changes']['extra'] = ['0' * 64, '1' * 64]
            elif mutation == 'base': transition['predecessor'] = '0' * 40
            elif mutation == 'tree': transition['predecessor_tree'] = '0' * 40
            else: transition['predecessor_manifest_sha256'] = '0' * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                module.validate_live_transition(bad, ROOT, c.core)

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
            build = root / MACOS_PATH
            build.write_bytes(main_bytes(MACOS_PATH))
            with self.assertRaises(ValueError):
                c.live_source_inventory(root)
            with self.assertRaises(ValueError):
                live_contract(HISTORY, source_root=root)
            shutil.copyfile(ROOT / MACOS_PATH, build)
            for path in ('shared-sources.json', 'libraries/mlf-foundation/Bootstrap/IndexVec.hs', 'mlf.lock', MACOS_PATH):
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
            original = manifest.read_bytes()
            variants = [
                ('lock', original.replace(c.changes['mlf.lock'][1].encode(), b'0' * 64)),
                # Replace both copies, so the transition record is internally
                # consistent but still cannot authorize different live bytes.
                ('build', original.replace(c.changes[MACOS_PATH][1].encode(), b'0' * 64)),
                ('prior main', main_bytes('tools/performance/artifact-binary/pr43-reconciliation-migration.json')),
            ]
            for label, raw in variants:
                manifest.write_bytes(raw)
                wrong = hashlib.sha256(raw).hexdigest()
                self.assertNotEqual(wrong, c.manifest_sha256)
                for digest in (c.manifest_sha256, wrong):
                    with self.subTest(label=label, digest=digest), self.assertRaises(ValueError):
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
