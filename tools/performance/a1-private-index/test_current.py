#!/usr/bin/env python3
"""Cheap fail-closed contract checks; these do not claim compiled A1 coverage."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('current_a1', HERE / 'run_current_controls.py')
current = importlib.util.module_from_spec(spec)
spec.loader.exec_module(current)


class CurrentCompatibilityTests(unittest.TestCase):
    def producer(self):
        return {'optimization': '2', 'resolved_modules': dict.fromkeys(current.SHARED_HASHES),
                'inferred_shared_interfaces': dict.fromkeys(current.SHARED_HASHES),
                'shared_inputs': {name: {'sha256': digest} for name, digest in current.SHARED_HASHES.items()}}

    def test_current_exact_source_inventory(self):
        current.authenticate_current_source(self.producer())
        manifest = json.loads((ROOT / 'shared-sources.json').read_text())
        actual = {row['module']: current.sha(ROOT / row['path']) for row in manifest['modules']}
        self.assertEqual(actual, current.SHARED_HASHES)

    def test_source_and_literal_mutations_rejected(self):
        for module in ['Bootstrap.Map', 'Bootstrap.CrateSession', 'Bootstrap.X.Checked', 'MLF.BuiltinPreludeData']:
            producer = self.producer()
            producer['shared_inputs'][module]['sha256'] = '0' * 64
            with self.subTest(module=module), self.assertRaises(ValueError):
                current.authenticate_current_source(producer)

    def test_missing_extra_and_stale_inventory_rejected(self):
        for kind in ['missing', 'extra', 'stale', 'optimization']:
            producer = self.producer()
            if kind == 'missing':
                producer['inferred_shared_interfaces'].pop('Bootstrap.CrateSession')
            elif kind == 'extra':
                producer['resolved_modules']['Unexpected'] = None
            elif kind == 'stale':
                producer['shared_inputs'] = {n: {'sha256': s} for n, s in current.historical.SHARED_HASHES.items()}
            else:
                producer['optimization'] = '0'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                current.authenticate_current_source(producer)

    def test_frozen_oracles_and_historical_runner_unchanged(self):
        self.assertEqual(current.sha(HERE / 'run_controls.py'), current.compatibility['historical_runner_sha256'])
        current.verify({str(HERE / 'controls' / name): digest for name, digest in current.CONTROL_HASHES.items()})
        self.assertEqual(current.historical.BUILTIN_HASHES,
            {'.mlfci': 'e7e79d5aba844f4eeb426bb65c65a4a52831b5274df4bd217ced55a9703f099b',
             '.mlfco': '3d0e214228cb180d8cee9fb3fd21c5ec6abd8348e1ddd131517831d1f5c2d799'})
        self.assertIn("a1source / 'tools/performance/a1-private-index/run_controls.py'", (HERE / 'reproduce.py').read_text())
        self.assertIn("HERE / 'run_current_controls.py'", (HERE / 'check_integrated.py').read_text())

    def test_old_builtin_pair_rejected_not_relabelled(self):
        with patch.object(current, 'sha', lambda path: current.historical.BUILTIN_HASHES[Path(path).suffix]):
            with self.assertRaisesRegex(ValueError, 'historical builtin'):
                current.snapshot_builtin('/not-read/builtin')

    def test_observed_hashes_do_not_grant_builtin_admission(self):
        current.require_builtin_result(0, current.CURRENT_BUILTIN_STDOUT, b'')
        for code, stdout, stderr in [(1, current.CURRENT_BUILTIN_STDOUT, b''),
                (0, b'', b''), (0, current.CURRENT_BUILTIN_STDOUT, b'warning'),
                (0, b'PASS current builtin\n', b'')]:
            with self.subTest(code=code, stdout=stdout, stderr=stderr), self.assertRaises(ValueError):
                current.require_builtin_result(code, stdout, stderr)

    def test_missing_extra_current_fixture_rejected(self):
        manifest = json.loads((HERE / 'current/manifest.json').read_text())
        expected = current.current_fixture_pins(HERE / 'current', manifest)
        self.assertEqual(set(expected), {str(HERE / 'current/CurrentBuiltinControls.hs')})
        for bad in [{}, {**manifest, 'Unpinned.hs': '0' * 64}, {'../controls/FileMain.hs': '0' * 64}]:
            with self.subTest(manifest=bad), self.assertRaises(ValueError):
                current.current_fixture_pins(HERE / 'current', bad)

    def test_current_builtin_control_is_pinned_and_has_fixed_oracle(self):
        manifest = json.loads((HERE / 'current/manifest.json').read_text())
        current.verify({str(HERE / 'current' / name): digest for name, digest in manifest.items()})
        code = (HERE / 'current/CurrentBuiltinControls.hs').read_text()
        for required in ['Literal.rawPrelude Canonical.builtin', 'Check.checkClosed (C.rawTerm raw)',
                         'C.checkCompilerPrelude raw', 'A.encodeInterface iface', 'A.encodeObject object',
                         'A.fragmentData linked', 'A.fragmentBindings linked', 'A.fragmentSerial linked']:
            self.assertIn(required, code)
        self.assertEqual(code.count('reject "'), 7)
        self.assertIn("require_builtin_result(code, so, se)", (HERE / 'run_current_controls.py').read_text())


if __name__ == '__main__':
    unittest.main()
