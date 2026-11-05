#!/usr/bin/env python3
"""Tiny source/admission controls, including an optimized Python interpreter."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import instrument
import run

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class AdmissionControls(unittest.TestCase):
    def test_source_identity_and_reversibility(self):
        for relative, transform in [
            ('libraries/mlf-llvm/Bootstrap/LLVM/Optimize.hs', instrument.optimize),
            ('libraries/mlf-llvm/Bootstrap/LLVM.hs', instrument.llvm),
        ]:
            original = (ROOT / relative).read_bytes()
            adapted, edits = transform(original)
            self.assertNotEqual(adapted, original)
            self.assertTrue(edits)
            with self.assertRaisesRegex(ValueError, 'source identity changed'):
                transform(original + b'\n-- corrupted source\n')

    def test_reverse_ledger_rejects_tampering(self):
        original = b'old source'
        patch = instrument.Patch(original, instrument.sha(original))
        patch.change('old', 'new')
        patch.text += ' tampered'
        with self.assertRaisesRegex(ValueError, 'does not reverse exactly'):
            patch.finish()

    def test_counter_total_rejects_missing_branch(self):
        def row(events):
            return {'events': events, 'depth_sum': 0, 'max_depth': 0}
        valid = {'substituteUsed.roots': row(1), 'substituteUsed.visits': row(1),
                 'substituteUsed.pruned': row(1)}
        run.validate_counts(valid)
        invalid = dict(valid, **{'substituteUsed.visits': row(2)})
        with self.assertRaisesRegex(ValueError, 'substituteUsed'):
            run.validate_counts(invalid)
        invalid_copy = {'copy.identities_alias.roots': row(1), 'copy.identities_alias.visits': row(2),
                        'copy.identities_alias.variable_lookup': row(1)}
        with self.assertRaisesRegex(ValueError, 'copy.identities_alias'):
            run.validate_counts(invalid_copy)

    def test_output_rejects_any_byte_difference(self):
        scratch = ROOT / '.mlf-build/inline-traversals-20261101'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='admission-', dir=scratch) as directory:
            ordinary, diagnostic = Path(directory) / 'ordinary.ll', Path(directory) / 'diagnostic.ll'
            ordinary.write_bytes(b'same output\n')
            diagnostic.write_bytes(b'same output\n')
            run.validate_output(ordinary, diagnostic)
            diagnostic.write_bytes(b'same output\r\n')
            with self.assertRaisesRegex(ValueError, 'LLVM differs'):
                run.validate_output(ordinary, diagnostic)

    def test_object_inventory_rejects_unreceipted_object(self):
        root = Path('/fixture/producer')
        auth = {'object_inputs': {'objects/A.o': 'digest'}}
        pins = {str(root / 'objects/A.o'): 'digest'}
        run.validate_object_inventory(root, auth, pins)
        with self.assertRaisesRegex(ValueError, 'object inventory'):
            run.validate_object_inventory(root, auth, {**pins, str(root / 'objects/Extra.o'): 'extra'})

    def test_complete_checked_dependency_closure(self):
        def pack(fields):
            return ''.join(str(len(field)) + ':' + field for field in fields)
        scratch = ROOT / '.mlf-build/inline-traversals-20261101'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='closure-admission-', dir=scratch) as directory:
            directory = Path(directory)
            dependency, root = directory / 'dependency.mlfci', directory / 'root.mlfci'
            dependency.write_text(pack(['MLFCI-5', 'dependency', ''] + [''] * 11))
            root.write_text(pack(['MLFCI-5', 'root', pack([pack(['dependency', str(dependency), 'semantic'])])] + [''] * 11))
            for path in (dependency, root):
                path.with_suffix('.mlfco').write_bytes(b'fixture object')
            pins, graph = run.checked_closure([root])
            self.assertEqual(set(pins), {str(path) for path in
                             (root, dependency, root.with_suffix('.mlfco'), dependency.with_suffix('.mlfco'))})
            self.assertEqual(graph, {str(root): [str(dependency)], str(dependency): []})
            dependency.write_text(pack(['MLFCI-5', 'dependency', pack([pack(['root', str(root), 'semantic'])])] + [''] * 11))
            with self.assertRaisesRegex(ValueError, 'cyclic'):
                run.checked_closure([root])

    def test_missing_target_workload_counters_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing demanded workload traversal'):
            run.validate_workload_counts({'identities.roots': {'events': 1, 'depth_sum': 0, 'max_depth': 0}})


if __name__ == '__main__':
    if '--child' in sys.argv:
        unittest.main(argv=[sys.argv[0]])
    else:
        for flags in ([], ['-O']):
            subprocess.run([sys.executable, '-B', *flags, str(Path(__file__).resolve()), '--child'], check=True)
        print('Admission controls passed with normal Python and python -O; no compiler/workload execution.')
