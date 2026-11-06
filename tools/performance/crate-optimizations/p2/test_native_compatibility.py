#!/usr/bin/env python3
"""Cheap fail-closed tests; valid under both ordinary Python and python -O."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location('native_compatibility', HERE / 'native_compatibility.py')
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


class NativeCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(compat.MANIFEST.read_text())

    def test_authentication_reconnects_historical_pins(self):
        manifest, projected = compat.authenticate(ROOT)
        self.assertEqual(set(projected), compat.SOURCE_PATHS)
        self.assertEqual(manifest['additional_controls']['checks'], 1243)

    def test_every_source_byte_mutation_is_rejected(self):
        for name, entry in self.manifest['sources'].items():
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'unreviewed'):
                    compat.project_historical((ROOT / name).read_bytes() + b'\n', entry)

    def test_input_inventory_is_exact(self):
        for name in compat.INPUT_PATHS:
            with self.subTest(name=name):
                changed = copy.deepcopy(self.manifest)
                del changed['inputs'][name]
                with self.assertRaisesRegex(ValueError, 'input inventory'):
                    compat.validate_manifest(changed)
        for name in ['../unreviewed.hs', '/tmp/unreviewed.hs', 'unreviewed.hs']:
            changed = copy.deepcopy(self.manifest)
            changed['inputs'][name] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'input inventory'):
                compat.validate_manifest(changed)

    def test_supplemental_control_count_is_fixed(self):
        changed = copy.deepcopy(self.manifest)
        changed['additional_controls']['checks'] -= 1
        with self.assertRaisesRegex(ValueError, 'control count'):
            compat.validate_manifest(changed)
        changed = copy.deepcopy(self.manifest)
        changed['additional_controls']['derivation']['distinct_poison'] -= 1
        with self.assertRaisesRegex(ValueError, 'control count'):
            compat.validate_manifest(changed)

    def test_repinned_current_source_still_requires_original_projection(self):
        for name, entry in self.manifest['sources'].items():
            with self.subTest(name=name):
                changed = (ROOT / name).read_bytes() + b'\n'
                repinned = copy.deepcopy(entry)
                repinned['current_sha256'] = compat.digest(changed)
                with self.assertRaisesRegex(ValueError, 'historical source'):
                    compat.project_historical(changed, repinned)

    def test_mutated_hunk_current_text_is_rejected(self):
        for name, entry in self.manifest['sources'].items():
            with self.subTest(name=name):
                changed = copy.deepcopy(entry)
                changed['hunks'][0]['after'] += '\n'
                with self.assertRaisesRegex(ValueError, 'match exactly'):
                    compat.project_historical((ROOT / name).read_bytes(), changed)

    def test_mutated_historical_text_is_rejected(self):
        for name, entry in self.manifest['sources'].items():
            with self.subTest(name=name):
                changed = copy.deepcopy(entry)
                changed['hunks'][0]['before'] += '\n'
                with self.assertRaisesRegex(ValueError, 'historical source'):
                    compat.project_historical((ROOT / name).read_bytes(), changed)

    def test_missing_or_reordered_hunks_are_rejected(self):
        for name, entry in self.manifest['sources'].items():
            with self.subTest(name=name):
                changed = copy.deepcopy(entry)
                changed['hunks'] = changed['hunks'][1:]
                with self.assertRaises(ValueError):
                    compat.project_historical((ROOT / name).read_bytes(), changed)
                changed = copy.deepcopy(entry)
                changed['hunks'] = (list(reversed(changed['hunks'])) if len(changed['hunks']) > 1
                                    else changed['hunks'] * 2)
                with self.assertRaises(ValueError):
                    compat.project_historical((ROOT / name).read_bytes(), changed)

    def test_historical_controls_and_runner_provenance_unchanged(self):
        p3 = HERE.parent / 'p3'
        historical = json.loads((p3 / 'controls-manifest.json').read_text())
        self.assertEqual(historical['expected_differential_controls'], 922)
        for name, expected in historical['inputs'].items():
            path = p3 / ('historical-run-controls.py.txt' if name == 'run_controls.py' else name)
            self.assertEqual(compat.digest(path.read_bytes()), expected, name)
        p2 = json.loads((HERE / 'oracle-manifest.json').read_text())
        self.assertEqual(compat.digest((HERE / 'FrozenFingerprint.hs').read_bytes()), p2['oracle_sha256'])
        self.assertEqual(compat.digest((HERE / 'original-fingerprint-excerpts.txt').read_bytes()), p2['excerpts_sha256'])
        changed = p2['changed_dependency_oracles']['libraries/mlf-crates/Bootstrap/Separate.hs']
        self.assertEqual(compat.digest((HERE / 'original-Separate.hs').read_bytes()), changed['original_sha256'])
        self.assertEqual(compat.digest((HERE / 'p2-Separate.hs').read_bytes()), changed['candidate_sha256'])


if __name__ == '__main__':
    unittest.main()
