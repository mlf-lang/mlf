#!/usr/bin/env python3
"""Cheap fail-closed runner controls, without compiler or native compilation."""
import contextlib
import io
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_io_action_sharing as gate
from test_direct import CommandRunner, sha

# Literal independent oracle. Do not extract labels/output from the fixture,
# gate constants or observed execution, even when updating this inventory.
LABELS = [
    'exact bind action exposes single use',
    'exact bind continuation exposes single use',
    'two-use action remains shared',
    'partial bind remains opaque',
    'non-lambda bind continuation remains opaque',
    'unrelated bind does not license substitution',
    'ordinary lambda remains a sharing boundary',
    'recursive group remains a sharing boundary',
    'unknown call remains a sharing boundary',
    'computed call remains a sharing boundary',
    'partial seq remains opaque',
    'two-use pure construction remains shared',
    'pure construction under ordinary lambda remains shared',
    'scalar under write remains shared',
    'scalar under return remains shared',
    'unused bottom is eliminated without demand',
    'substitution preserves same-hint captured identities',
    'single-use action restores kernel eligibility',
    'unsafe divisor remains ineligible',
]
PROGRAMS = [
    ('ground-string-sharing', '10\n10\n', None, False),
    ('different-class-instances', '1\n2\n', None, False),
    ('common-call-unused-bottom', 'ok\n', None, False),
    ('common-call-fresh-arrays', '0\n', None, False),
    ('bare-do-loop', '42\n', None, True),
    ('explicit-bind-loop', '42\n', None, True),
    ('shared-action-twice', 'tick\ntick\n2\n', None, False),
    ('pure-construction-sharing', '42\n42\n', None, False),
    ('unused-bottom', 'ok\n', None, False),
    ('early-failure-before-late-bottom', 'before\n', 'first failure', False),
    ('late-bottom-after-effect', 'before\n', 'late bottom', False),
    ('seq-action-does-not-execute', 'ok\n', None, False),
    ('partial-bind-stays-lazy', 'ok\n', None, False),
    ('partial-sequence-stays-lazy', 'ok\n', None, False),
    ('capture-avoiding-substitution', '42\n', None, False),
    ('ignored-return-payload', 'ok\n', None, False),
    ('custom-sequence-override', '', 'overridden sequence', False),
    ('custom-sequence-ignores-first', '42\n', None, False),
]
TERMINAL = 'IO action sharing: passed (19 shape checks, 18 source cases, 3 execution forms)'


def wire(labels=LABELS, programs=PROGRAMS):
    lines = ['PASS shape: ' + label + '\n' for label in labels]
    for label, output, error, kernel in programs:
        if kernel:
            lines.append('PASS kernel: ' + label + '\n')
        for form in ['original', 'serialized', 'optimized-erased']:
            lines += ['BEGIN ' + label + '/' + form + '\n', output,
                      'OUTCOME ' + ('ok' if error is None else 'error: ' + error) + '\n']
        lines.append('PASS semantics: ' + label + '\n')
    return (''.join(lines) + TERMINAL + '\n').encode()


class InventoryControls(unittest.TestCase):
    def test_independent_exact_inventory(self):
        self.assertEqual(len(LABELS), 19)
        self.assertEqual(len(PROGRAMS), 18)
        self.assertEqual(len({p[0] for p in PROGRAMS}), 18)
        gate.verify_inventory(wire())

    def test_missing_extra_reordered_duplicate_truncated_and_corrupt(self):
        mutations = [wire(labels=LABELS[:-1]), wire(labels=LABELS + ['extra']),
                     wire(labels=LABELS[1:] + LABELS[:1]),
                     wire(labels=LABELS[:-1] + LABELS[:1]),
                     wire(programs=PROGRAMS[:-1]), wire()[:-1],
                     wire().replace(b'tick\ntick\n2\n', b'tick\n1\n'),
                     wire().replace(b'first failure', b'late bottom'),
                     wire().replace(b'original', b'wrong form'),
                     wire() + b'warning\n', wire().replace(b'\n', b'\r\n'),
                     b'\xff', b'']
        for output in mutations:
            with self.subTest(output=output[:60]), self.assertRaises(ValueError):
                gate.verify_inventory(output)

    def test_changed_gate_oracle_does_not_change_independent_control(self):
        with patch.object(gate, 'SHAPES', list(reversed(LABELS))):
            with self.assertRaises(ValueError):
                gate.verify_inventory(wire())
        with patch.object(gate, 'BANNER', 'unreviewed banner'):
            with self.assertRaises(ValueError):
                gate.verify_inventory(wire())

    def test_exact_artifacts_reject_missing_extra_and_misnamed(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            for label, *_ in PROGRAMS:
                for suffix in ['.ll', '.xmlf']:
                    (work / (label + suffix)).write_text('fixture')
            gate.verify_artifact_inventory(work)
            selected = work / 'bare-do-loop.ll'
            selected.rename(work / 'wrong.ll')
            with self.assertRaises(ValueError):
                gate.verify_artifact_inventory(work)
            (work / 'wrong.ll').rename(selected)
            (work / 'extra').touch()
            with self.assertRaises(ValueError):
                gate.verify_artifact_inventory(work)
            (work / 'extra').unlink()
            selected.unlink()
            with self.assertRaises(ValueError):
                gate.verify_artifact_inventory(work)


class CommandControls(unittest.TestCase):
    def test_existing_runner_rejects_wrong_exit_stderr_and_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            record = {'commands': []}
            runner = CommandRunner(work, work, record, lambda: None)
            for label, code in [('exit', 'raise SystemExit(2)'),
                                ('stderr', 'import sys; sys.stderr.write("warning")'),
                                ('stdout', 'print("wrong")')]:
                with self.subTest(label=label), self.assertRaises(RuntimeError):
                    runner.run(label, [sys.executable, '-c', code], expected=b'')
            runner.run('expected-failure', [sys.executable, '-c', 'raise SystemExit(1)'],
                       status=1, expected=b'')


class AdmissionControls(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='io-action-controls-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.producer = self.root / 'producer'
        (self.producer / 'objects').mkdir(parents=True)
        self.object = self.producer / 'objects/Module.o'
        self.object.write_bytes(b'authenticated object')
        self.receipt = self.producer / 'receipt.json'
        self.receipt.write_text('{}\n')
        self.output = self.root / 'result'
        self.metadata = {'optimization': '2', 'object_inputs': {'objects/Module.o': sha(self.object)},
                         'ghc': {'path': '/verified/ghc'}, 'cc': {'path': '/verified/cc'}}
        self.calls = []
        self.requests = []
        self.mutation = None
        self.gc = self.root / 'gc'
        (self.gc / 'lib').mkdir(parents=True)
        (self.gc / 'include/gc').mkdir(parents=True)
        (self.gc / 'lib/libgc.a').write_bytes(b'test archive')
        (self.gc / 'include/gc/gc.h').write_bytes(b'test header')
        self.clang = self.root / 'clang'
        self.clang.write_bytes(b'test clang identity')

    def run_command(self, label, command, **kwargs):
        self.calls.append((label, list(map(str, command))))
        self.requests.append((label, kwargs))
        argv = list(map(str, command))
        for option in ['-o', '-ohi']:
            if option in argv:
                Path(argv[argv.index(option) + 1]).write_bytes(b'isolated fixture artifact')
        output = b''
        if label == 'shape-and-semantics':
            work = Path(argv[-1])
            for name, *_ in PROGRAMS:
                for suffix in ['.ll', '.xmlf']:
                    (work / (name + suffix)).write_bytes(b'checked test artifact')
            output = wire()
            if self.mutation == 'object':
                self.object.write_bytes(b'changed object')
            elif self.mutation == 'receipt':
                self.receipt.write_text('changed receipt\n')
            elif self.mutation == 'truncated':
                output = output[:-1]
            elif self.mutation == 'artifact':
                (work / 'bare-do-loop.ll').unlink()
        diagnostics = b''
        if label.startswith('run-'):
            case = next(case for case in PROGRAMS if 'run-' + case[0] == label)
            output = case[1].encode()
            if case[2] is not None:
                diagnostics = ('Runtime: ' + case[2] + '\n').encode()
                if self.mutation == 'native-diagnostic':
                    diagnostics = b'Runtime: wrong diagnostic\n'
        return subprocess.CompletedProcess(argv, kwargs.get('status', 0), output, diagnostics)

    def invoke(self, authentication=None, native=False):
        argv = ['test_io_action_sharing.py', '--build-receipt', str(self.receipt),
                '--output', str(self.output)]
        if native:
            argv += ['--gc-prefix', str(self.gc), '--clang', str(self.clang)]
        with patch.object(sys, 'argv', argv), \
             patch.object(gate, 'authenticate_build', side_effect=authentication,
                          return_value=self.metadata), \
             patch.object(gate.CommandRunner, 'run', side_effect=self.run_command), \
             contextlib.redirect_stdout(io.StringIO()):
            gate.main()

    def test_fixture_main_only_and_no_native_dependency(self):
        self.invoke()
        receipt = json.loads((self.output / 'receipt.json').read_text())
        self.assertTrue(receipt['complete'])
        self.assertEqual(receipt['native_cases_passed'], [])
        self.assertFalse(receipt['compiler_modules_rebuilt'])
        compile_argv = next(argv for label, argv in self.calls if label == 'compile-fixture')
        self.assertIn('-c', compile_argv)
        self.assertNotIn('--make', compile_argv)
        self.assertEqual(compile_argv[-1], str(gate.FIXTURE))
        self.assertNotIn('compile-native-runtime', [label for label, _ in self.calls])
        self.assertEqual(self.object.read_bytes(), b'authenticated object')

    def test_native_dispatch_has_exact_cases_outputs_and_statuses(self):
        self.invoke(native=True)
        native = [(label, request) for label, request in self.requests if label.startswith('run-')]
        self.assertEqual([label for label, _ in native], ['run-' + case[0] for case in PROGRAMS])
        for (_, request), (_, output, error, _) in zip(native, PROGRAMS):
            self.assertEqual(request['expected'], output.encode())
            self.assertEqual(request['status'], 0 if error is None else 1)
        receipt = json.loads((self.output / 'receipt.json').read_text())
        self.assertTrue(receipt['complete'])
        self.assertEqual(receipt['native_cases_passed'], [case[0] for case in PROGRAMS])
        self.assertFalse(receipt['native_toolchain_closure_complete'])
        self.assertIn(str(self.gc / 'lib/libgc.a'), receipt['external_inputs'])

    def test_native_wrong_diagnostic_never_passes(self):
        self.mutation = 'native-diagnostic'
        with self.assertRaisesRegex(ValueError, 'native diagnostic changed'):
            self.invoke(native=True)
        self.assertFalse(json.loads((self.output / 'receipt.json').read_text())['complete'])

    def test_missing_native_archive_never_dispatches_native(self):
        (self.gc / 'lib/libgc.a').unlink()
        with self.assertRaises(FileNotFoundError):
            self.invoke(native=True)
        self.assertNotIn('compile-native-runtime', [label for label, _ in self.calls])
        self.assertFalse(json.loads((self.output / 'receipt.json').read_text())['complete'])

    def test_unauthenticated_producer_never_compiles(self):
        with self.assertRaisesRegex(ValueError, 'unauthenticated'):
            self.invoke(authentication=ValueError('unauthenticated'))
        self.assertEqual(self.calls, [])
        self.assertFalse(json.loads((self.output / 'receipt.json').read_text())['complete'])

    def test_object_mutation_invalidates_success(self):
        self.mutation = 'object'
        with self.assertRaisesRegex(ValueError, 'object/interface changed'):
            self.invoke()
        receipt = json.loads((self.output / 'receipt.json').read_text())
        self.assertFalse(receipt['complete'])
        self.assertEqual(receipt['status'], 'invalidated')

    def test_receipt_mutation_invalidates_success(self):
        self.mutation = 'receipt'
        with self.assertRaisesRegex(ValueError, 'producer receipt changed'):
            self.invoke()
        self.assertFalse(json.loads((self.output / 'receipt.json').read_text())['complete'])

    def test_partial_output_never_passes(self):
        self.mutation = 'truncated'
        with self.assertRaisesRegex(ValueError, 'completion inventory'):
            self.invoke()
        self.assertFalse(json.loads((self.output / 'receipt.json').read_text())['complete'])

    def test_missing_artifact_never_passes(self):
        self.mutation = 'artifact'
        with self.assertRaisesRegex(ValueError, 'artifact inventory'):
            self.invoke()
        self.assertFalse(json.loads((self.output / 'receipt.json').read_text())['complete'])


class WorkflowControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (gate.ROOT / '.github/workflows/ci.yml').read_text()
        match = re.search(r'^  native:\n(.*?)(?=^  [a-zA-Z0-9_-]+:|\Z)',
                          cls.workflow, re.MULTILINE | re.DOTALL)
        if match is None:
            raise AssertionError('existing direct-host native job missing')
        cls.job = match.group(1)
        matches = re.findall(r'^      - name: Check lazy IO action specialization with native execution\n'
                             r'(.*?)(?=^      - |\Z)', cls.job, re.MULTILINE | re.DOTALL)
        if len(matches) != 1:
            raise AssertionError('expected exactly one lazy IO regression step')
        cls.step = matches[0]

    def test_one_existing_o2_only_native_gate_without_new_matrix_or_caps(self):
        self.assertEqual(self.workflow.count('tools/shared/test_io_action_sharing.py'), 1)
        self.assertIn("        if: matrix.optimization == '2'\n", self.step)
        matrix = re.findall(r"          - optimization: '([02])'\n            suite: ([a-z]+)", self.job)
        self.assertEqual(matrix, [('2', 'all'), ('0', 'direct'), ('0', 'default'), ('0', 'framework')])
        self.assertIn('    timeout-minutes: 120\n', self.job)
        self.assertNotIn('timeout-minutes:', self.step)
        self.assertNotIn('--run-timeout', self.step)
        self.assertNotIn('--build-timeout', self.step)
        self.assertNotIn('continue-on-error', self.step)

    def test_native_step_uses_authenticated_producer_and_matching_static_gc(self):
        for command in [
            'set -euo pipefail',
            'sudo apt-get install -y libgc-dev',
            'prefix="$PWD/.mlf-build/io-action-gc"',
            'cp /usr/include/gc.h "$prefix/include/gc.h"',
            'cp -R /usr/include/gc "$prefix/include/gc"',
            'archive="$(cc -print-file-name=libgc.a)"',
            'test -f "$archive"',
            'cp "$archive" "$prefix/lib/libgc.a"',
            'dpkg-query -W libgc-dev > "$prefix/dependency-version.txt"',
            '--build-receipt .mlf-build/shared-ghc/receipt.json',
            '--output .mlf-build/io-action-sharing --clang clang --gc-prefix "$prefix"',
        ]:
            with self.subTest(command=command):
                self.assertIn(command, self.step)
        self.assertLess(self.step.index('sudo apt-get install'), self.step.index('cp /usr/include/gc.h'))
        self.assertLess(self.step.index('cp "$archive"'), self.step.index('python3 tools/shared/test_io_action_sharing.py'))

    def test_evidence_and_metadata_controls_are_retained(self):
        for suffix in ['json', 'stdout', 'stderr', 'll', 'xmlf']:
            self.assertIn('.mlf-build/io-action-sharing/**/*.' + suffix, self.job)
        self.assertIn('.mlf-build/io-action-gc/dependency-version.txt', self.job)
        upload = self.job[self.job.index('      - uses: actions/upload-artifact@'):]
        self.assertIn('        if: always()\n', upload)
        self.assertIn('          include-hidden-files: true\n', upload)
        check = (gate.ROOT / 'tools/release/check.sh').read_text()
        self.assertEqual(check.count('python3 tools/shared/test_io_action_sharing_controls.py'), 1)


if __name__ == '__main__':
    unittest.main()
