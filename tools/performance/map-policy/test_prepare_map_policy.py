#!/usr/bin/env python3
"""Current-run snapshots, semantic output protocol, and failure propagation controls."""
import os
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import prepare_map_policy as P
import run_controls as R

class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ.get('MAP_POLICY_SOURCE', P.ROOT))
        cls.current = P.read_inputs(cls.root)
        cls.fixtures = P.read_fixtures()

    def prepare(self, parent, name='prepared', inputs=None, fixtures=None):
        output = Path(parent) / name
        receipt = P.prepare(output, self.current if inputs is None else inputs,
                            self.fixtures if fixtures is None else fixtures)
        return output, receipt

    def test_fresh_source_edits_are_accepted_and_identified(self):
        original = P.input_identity(self.current)
        with tempfile.TemporaryDirectory() as directory:
            for index, path in enumerate(self.current):
                changed = dict(self.current)
                changed[path] += b'\n'
                with self.subTest(path=path):
                    output, receipt = self.prepare(directory, str(index), inputs=changed)
                    self.assertEqual((output / 'source' / path).read_bytes(), changed[path])
                    self.assertNotEqual(receipt['current_inputs'][path], original[path])
                    P.verify_snapshot(output, receipt)
                    with self.assertRaisesRegex(ValueError, 'changed during run'):
                        P.verify_identity(changed, original)

    def test_fresh_control_edits_are_accepted_and_identified(self):
        original = P.input_identity(self.fixtures)
        with tempfile.TemporaryDirectory() as directory:
            for index, path in enumerate(self.fixtures):
                changed = dict(self.fixtures)
                changed[path] += b'\n'
                with self.subTest(path=path):
                    output, receipt = self.prepare(directory, str(index), fixtures=changed)
                    self.assertEqual((output / path).read_bytes(), changed[path])
                    self.assertNotEqual(receipt['fixture_inputs'][path], original[path])
                    with self.assertRaisesRegex(ValueError, 'changed during run'):
                        P.verify_identity(changed, original)

    def test_each_changed_or_missing_snapshot_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, receipt = self.prepare(directory)
            originals = {'source/' + path: raw for path, raw in self.current.items()}
            originals.update(self.fixtures)
            for relative, raw in originals.items():
                path = output / relative
                for mutation in ('changed', 'missing'):
                    with self.subTest(path=relative, mutation=mutation):
                        if mutation == 'changed':
                            path.write_bytes(raw + b'\n')
                        else:
                            path.unlink()
                        with self.assertRaises((ValueError, FileNotFoundError)):
                            P.verify_snapshot(output, receipt)
                        path.write_bytes(raw)
            for relative in ('source/unbound.hs', 'Unexpected.hs'):
                path = output / relative
                path.write_text('module Unexpected where\n')
                with self.subTest(path=relative), self.assertRaisesRegex(ValueError, 'inventory changed'):
                    P.verify_snapshot(output, receipt)
                path.unlink()

    def test_old_receipt_rejects_new_inventory(self):
        expected = P.input_identity(self.current)
        missing = dict(self.current)
        missing.pop(P.MAP)
        extra = dict(self.current, **{'unexpected.hs': b'module Unexpected where\n'})
        for value in (missing, extra):
            with self.assertRaisesRegex(ValueError, 'changed during run'):
                P.verify_identity(value, expected)

    def test_preparation_works_in_a_source_copy_without_git_history(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'checkout'
            for name, raw in self.current.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            output = Path(directory) / 'prepared'
            with mock.patch.object(sys, 'argv', ['prepare_map_policy.py', '--source', str(source), '--output', str(output)]):
                P.main()
            receipt = json.loads((output / 'preparation.json').read_text())
            self.assertEqual(receipt['current_inputs'], P.input_identity(self.current))
            P.verify_snapshot(output, receipt)

    def test_import_closure_follows_new_local_module(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            for name, raw in self.current.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            module = source / 'libraries/mlf-foundation/Bootstrap/MapSupport.hs'
            module.write_text('module Bootstrap.MapSupport where\n')
            path = source / P.MAP
            path.write_bytes(path.read_bytes().replace(b'import MLF.Primitive;',
                b'import MLF.Primitive; import qualified Bootstrap.MapSupport as Support;'))
            self.assertIn(module.relative_to(source).as_posix(), P.read_inputs(source))
            module.unlink()
            with self.assertRaisesRegex(ValueError, 'missing/ambiguous local module'):
                P.read_inputs(source)

    def test_transitive_project_include_closure(self):
        graph = P.project_include_graph(self.current)
        self.assertIn('runtime/mlf_process_supervisor_posix.h', graph['runtime/mlf_process_supervisor.c'])
        self.assertIn('runtime/mlf_system_windows.h', graph['runtime/mlf_system.h'])
        missing = dict(self.current)
        missing.pop('runtime/mlf_process_supervisor_posix.h')
        with self.assertRaisesRegex(ValueError, 'unbound transitive'):
            P.project_include_graph(missing)
        changed = dict(self.current)
        changed['host/ghc/cbits/host.c'] += b'\n#include "additional.h"\n'
        with self.assertRaisesRegex(ValueError, 'unbound transitive'):
            P.project_include_graph(changed)
        changed['runtime/additional.h'] = b'#include "mlf_process_supervisor.h"\n'
        self.assertIn('runtime/additional.h', P.project_include_graph(changed))

    def test_incomplete_controls_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in self.fixtures:
                missing = dict(self.fixtures)
                missing.pop(name)
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'complete Map control inventory'):
                    self.prepare(directory, fixtures=missing)

    def test_sources_cannot_escape_or_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data.hs').write_bytes(b'module Data where\n')
            (root / 'link.hs').symlink_to(root / 'data.hs')
            for path in ('../data.hs', str(root / 'data.hs'), 'link.hs', ''):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    P.read_regular(root, path)
            with self.assertRaises(ValueError):
                P.input_identity({'../outside.hs': b'invalid'})

    def test_source_loader_accepts_current_helper_and_records_its_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'helper.py'
            for value in (1, 2):
                raw = ('value = ' + str(value) + '\n').encode()
                path.write_bytes(raw)
                module, identity = R.source_module(path, 'map_policy_helper')
                self.assertEqual(module.value, value)
                self.assertEqual(identity, hashlib.sha256(raw).hexdigest())


class SuccessInventoryTests(unittest.TestCase):
    def complete_lines(self):
        lines = [R.HISTORICAL_LINE, 'PASS ' + R.GROUPS[0], 'PASS ' + R.GROUPS[1],
                 R.WITNESS, 'PASS ' + R.GROUPS[2], 'PASS ' + R.GROUPS[3]]
        values = ['Right True', 'Right True', 'Left "key"', 'Right True', 'Left "key"', 'Left "cmp"',
                  'Right True', 'Right True', 'Left "one"', 'Right True', 'Left "combine"', 'Right True',
                  'Right True', 'Left "new"', 'Right True', 'Left "left"', 'Left "right"', 'Right True',
                  'Right True', 'Left "combine"', 'Left "cmp"', 'Left "left-value"', 'Left "right-value"',
                  'Right True', 'Left "cmp"']
        for label, value in zip(R.DEMAND_LABELS, values):
            lines += ['Demand observation ' + label + ': historical=' + value + ' current=' + value,
                      'PASS demand ' + label]
        return lines + [R.FINAL_LINE]

    def validate(self, lines, stderr=b'', status=0):
        return R.validate_success(('\n'.join(lines) + '\n').encode(), stderr, status)

    def test_complete_handwritten_protocol_inventory(self):
        result = self.validate(self.complete_lines())
        self.assertEqual(len(set(result['demand_labels'])), 25)
        self.assertEqual(result['historical'], dict(raw_pairs=24649, mutation_steps=400, demand_cases=30))

    def test_each_omission_duplicate_and_extra_line_is_rejected(self):
        original = self.complete_lines()
        for index in range(len(original)):
            missing = original[:index] + original[index + 1:]
            duplicate = original[:index] + [original[index]] + original[index:]
            for changed in (missing, duplicate):
                with self.subTest(index=index), self.assertRaises(ValueError):
                    self.validate(changed)
        with self.assertRaises(ValueError):
            self.validate(original + ['PASS unrelated'])

    def test_wrong_order_labels_and_historical_difference_waiver_rejected(self):
        original = self.complete_lines()
        variants = []
        changed = list(original); changed[1], changed[2] = changed[2], changed[1]; variants.append(changed)
        changed = list(original); changed[6:8] = original[8:10]; variants.append(changed)
        changed = list(original); changed[3] = 'PASS historical shape equivalence'; variants.append(changed)
        changed = list(original); changed[-1] = 'Current Map policy controls passed'; variants.append(changed)
        changed = list(original); changed[0] = original[0].replace('400', '399'); variants.append(changed)
        for index, changed in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.validate(changed)

    def test_mismatched_demand_error_or_nonzero_exit_never_success(self):
        original = self.complete_lines()
        changed = list(original); changed[6] = changed[6].replace('current=Right True', 'current=Left "wrong demand"')
        with self.assertRaises(ValueError):
            self.validate(changed)
        changed = list(original); changed[6] = changed[6].replace('Right True', 'Right False')
        with self.assertRaises(ValueError):
            self.validate(changed)
        for stderr, status in [(b'unexpected diagnostic', 0), (b'', 1), (b'', -9), (b'', False)]:
            with self.subTest(stderr=stderr, status=status), self.assertRaises(ValueError):
                self.validate(original, stderr, status)

    def test_supervision_requires_all_terminal_fields(self):
        good = dict(complete=True, cleanup_complete=True, target_exit_code=0, survivors=[], cancel_signals=[],
                    phase='terminal', reason='target exited', signals=[])
        R.validate_supervision(0, good)
        for key, value in [('complete', False), ('cleanup_complete', False), ('target_exit_code', 1),
                           ('survivors', [123]), ('cancel_signals', [15]), ('phase', 'cleanup'),
                           ('reason', 'work deadline'), ('signals', [15]), ('target_exit_code', False)]:
            for mutation in ('changed', 'missing'):
                wrong = dict(good)
                if mutation == 'changed': wrong[key] = value
                else: del wrong[key]
                with self.subTest(key=key, mutation=mutation), self.assertRaises(ValueError):
                    R.validate_supervision(0, wrong)
        with self.assertRaises(ValueError):
            R.validate_supervision(1, good)
        for key in ('error', 'cleanup_error'):
            for value in ('failure', '', None):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    R.validate_supervision(0, dict(good, **{key: value}))

    def test_strict_lf_protocol(self):
        raw = ('\n'.join(self.complete_lines()) + '\n').encode()
        for wrong in (raw[:-1], raw.replace(b'\n', b'\r\n'), raw + b'\n', raw.replace(b'\n', b'\x0b', 1)):
            with self.subTest(raw=wrong), self.assertRaises(ValueError):
                R.validate_success(wrong, b'', 0)

    def test_bootstrap_compiles_and_runs_only_bound_worker(self):
        code = compile(R.worker_bootstrap(), '<worker-bootstrap>', 'exec')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'fake_worker.py'
            marker = root / 'called'
            raw = b'''from pathlib import Path
if __name__ == '__main__':
    raise RuntimeError('implicit CLI bypass')
def worker(a):
    if str(a.source) != 'source' or str(a.producer) != 'producer':
        raise RuntimeError('wrong worker arguments')
    Path(a.output).write_text(__name__)
'''
            source.write_bytes(raw)
            argv = ['-c', str(source), hashlib.sha256(raw).hexdigest(), 'source', 'producer', str(marker)]
            with mock.patch.object(sys, 'argv', argv):
                exec(code, {})
            self.assertEqual(marker.read_text(), 'map_policy_worker')
            marker.unlink()
            for bad in (argv[:2] + ['0' * 64] + argv[3:], argv + ['--worker'], ['-c', '--worker']):
                with mock.patch.object(sys, 'argv', bad), self.assertRaisesRegex(RuntimeError, 'worker (source identity|argument inventory)'):
                    exec(code, {})
                self.assertFalse(marker.exists())
            # Even module top-level side effects must not execute on a digest mismatch.
            source.write_text('raise RuntimeError("unbound module executed")\n')
            with mock.patch.object(sys, 'argv', argv), self.assertRaisesRegex(RuntimeError, 'worker source identity'):
                exec(code, {})

    def test_capture_digest_lengths_and_artifact_identity_refuse_drift(self):
        summary = R.command_log_summary(b'captured', b'')
        R.validate_command_logs(summary, b'captured', b'')
        for stdout, stderr in [(b'changed', b''), (b'captured', b'error')]:
            with self.assertRaises(ValueError):
                R.validate_command_logs(summary, stdout, stderr)
        for key in summary:
            bad = dict(summary); bad.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                R.validate_command_logs(bad, b'captured', b'')
        R.require_same_artifacts({'controls': 'a', 'Main.o': 'b'}, {'controls': 'a', 'Main.o': 'b'})
        for wrong in ({}, {'controls': 'a'}, {'controls': 'changed', 'Main.o': 'b'}):
            with self.assertRaises(ValueError):
                R.require_same_artifacts({'controls': 'a', 'Main.o': 'b'}, wrong)


if __name__ == '__main__':
    unittest.main()
