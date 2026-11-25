#!/usr/bin/env python3
"""Bounded Python source-proof controls only. No Git, GHC or target executions.
MAP_POLICY_SOURCE chooses physical selected files; every byte must match the
Foundation pins, so neither local HEAD nor this environment variable authorizes drift.
"""
import os
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import prepare_map_policy as P
import run_controls as R

CONTEXT = (P.CURRENT_COMMIT, P.CURRENT_TREE, P.HISTORICAL_COMMIT, P.HISTORICAL_TREE)


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ['MAP_POLICY_SOURCE'])
        cls.current = {name: P.read_regular(root, name) for name in P.CURRENT_BLOBS}
        cls.historical = (Path(__file__).parent / 'fixtures/fc300-Map.hs').read_bytes()
        P.authenticate_inputs(cls.current, cls.historical, CONTEXT)

    def test_complete_inverse_and_distinct_candidate_imports(self):
        generated = P.prepare_bytes(self.current, self.historical, CONTEXT)
        P.verify_generated(generated, self.current, self.historical, CONTEXT)
        self.assertEqual(set(generated), {'RetainedBalanceControls.hs', 'HistoricalBalanceControls.hs',
                                         'HistoricalMap.hs', 'FrozenMap.hs', 'BaselineMap.hs'})
        retained = generated['RetainedBalanceControls.hs']
        historical = generated['HistoricalBalanceControls.hs']
        self.assertIn(b'import qualified Bootstrap.Map as C\n', retained)
        self.assertIn(b'import qualified HistoricalMap as C\n', historical)
        self.assertNotIn(b'import qualified Bootstrap.Map as C\n', historical)
        self.assertEqual(generated['FrozenMap.hs'], self.current[P.FROZEN])
        self.assertEqual(generated['BaselineMap.hs'], self.current[P.BASELINE])
        for name, old in [('RetainedBalanceControls', False), ('HistoricalBalanceControls', True)]:
            self.assertEqual(P.invert_unique(generated[name + '.hs'], P.changes(name, old)), self.current[P.BALANCE])
        self.assertEqual(generated['HistoricalMap.hs'].replace(b'module HistoricalMap where {',
                                                               b'module Bootstrap.Map where {'), self.historical)

    def test_wrong_current_or_historical_commit_and_tree(self):
        for index in range(4):
            wrong = list(CONTEXT); wrong[index] = '0' * 40
            with self.subTest(index=index), self.assertRaises(ValueError):
                P.prepare_bytes(self.current, self.historical, wrong)

    def test_each_selected_current_file_rejects_even_one_byte_change(self):
        for path in P.CURRENT_BLOBS:
            wrong = dict(self.current); wrong[path] += b' '
            with self.subTest(path=path), self.assertRaises(ValueError):
                P.prepare_bytes(wrong, self.historical, CONTEXT)

    def test_wrong_historical_and_swapped_endpoints(self):
        for raw in (self.historical + b' ', self.current[P.MAP], b''):
            with self.subTest(raw_length=len(raw)), self.assertRaises(ValueError):
                P.prepare_bytes(self.current, raw, CONTEXT)
        wrong = dict(self.current); wrong[P.MAP] = self.historical
        with self.assertRaises(ValueError):
            P.prepare_bytes(wrong, self.historical, CONTEXT)

    def test_missing_and_extra_inputs_are_refused(self):
        for mutation in ('missing', 'extra'):
            wrong = dict(self.current)
            if mutation == 'missing':
                wrong.pop('runtime/mlf_windows.h')
            else:
                wrong['unexpected.hs'] = b'other'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                P.prepare_bytes(wrong, self.historical, CONTEXT)

    def test_transitive_project_include_closure_is_explicit(self):
        graph = P.project_include_graph(self.current)
        self.assertEqual(len(graph), 11)
        self.assertIn('runtime/mlf_process_supervisor_posix.h', graph['runtime/mlf_process_supervisor.c'])
        self.assertIn('runtime/mlf_system_windows.h', graph['runtime/mlf_system.h'])
        self.assertIn('runtime/mlf_windows_path.h', graph['runtime/mlf_windows.h'])
        missing = dict(self.current); missing.pop('runtime/mlf_process_supervisor_posix.h')
        with self.assertRaisesRegex(ValueError, 'unbound transitive'):
            P.project_include_graph(missing)
        mutated = dict(self.current)
        mutated['host/ghc/cbits/host.c'] += b'\n#include "unbound.h"\n'
        with self.assertRaisesRegex(ValueError, 'unbound transitive'):
            P.project_include_graph(mutated)

    def test_generated_extra_omission_header_body_or_oracle_changes_refused(self):
        original = P.prepare_bytes(self.current, self.historical, CONTEXT)
        variants = []
        extra = dict(original); extra['other.hs'] = b'other'; variants.append(extra)
        missing = dict(original); missing.pop('FrozenMap.hs'); variants.append(missing)
        for path in original:
            wrong = dict(original); wrong[path] += b' '; variants.append(wrong)
        wrong = dict(original)
        wrong['HistoricalBalanceControls.hs'] = wrong['HistoricalBalanceControls.hs'].replace(
            b'import qualified HistoricalMap as C', b'import qualified Bootstrap.Map as C')
        variants.append(wrong)
        for index, value in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                P.verify_generated(value, self.current, self.historical, CONTEXT)

    def test_unique_edits_missing_duplicate_collision_refused(self):
        for raw in (b'absent', b'old old', b'old new'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                P.apply_unique(raw, [(b'old', b'new')])
        old = self.current[P.BALANCE].replace(b'module Main where\n', b'module Other where\n')
        with self.assertRaises(ValueError):
            P.apply_unique(old, P.changes('RetainedBalanceControls'))
        with self.assertRaises(ValueError):
            P.changes('HistoricalBalanceControls', False)

    def test_physical_git_reader_requests_only_fixed_tree_and_map(self):
        calls = []
        outputs = iter([(P.HISTORICAL_TREE + '\n').encode(), self.historical])
        def output(argv, timeout):
            self.assertEqual(timeout, 30)
            calls.append(argv)
            return next(outputs)
        self.assertEqual(P.historical_from_git('/fixture', output), self.historical)
        prefix = ['git', '--no-replace-objects', '-C', '/fixture']
        self.assertEqual(calls, [
            prefix + ['rev-parse', P.HISTORICAL_COMMIT + '^{tree}'],
            prefix + ['show', P.HISTORICAL_COMMIT + ':' + P.MAP]])
        with self.assertRaises(ValueError):
            P.historical_from_git('/fixture', lambda *a, **kw: b'wrong-tree\n')
        outputs = iter([(P.HISTORICAL_TREE + '\n').encode(), self.current[P.MAP]])
        with self.assertRaises(ValueError):
            P.historical_from_git('/fixture', lambda *a, **kw: next(outputs))


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
