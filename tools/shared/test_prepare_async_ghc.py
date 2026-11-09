#!/usr/bin/env python3
"""Filesystem and mocked-command controls; never invoke GHC, Clang or project tools."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('prepare_async_ghc', HERE / 'prepare_async_ghc.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class Preparation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='async-ghc-control-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / 'build'
        for name in ('runtime/mlf_build_runner.c', 'tools/shared/prepare_async_ghc.py', 'tools/clang'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture\n')
        (self.root / 'tools/shared/test_direct.py').write_bytes((HERE / 'test_direct.py').read_bytes())
        self.auth = prepare.authenticator(self.root)
        self.calls = []
        self.bad = None
        self.mutation = None
        self.auth_count = 0
        self.producer = None

    def authenticate(self, receipt, binaries, root):
        self.auth_count += 1
        producer = json.loads(receipt.read_text())
        if self.bad == 'authenticate' or self.bad == 'post-authenticate' and self.auth_count == 2:
            raise ValueError('producer rejected')
        # Command mocks do not pretend to be GHC. Exercise real path/hash checks
        # here; the production call always uses full test_direct authentication.
        for item in producer['outputs'].values():
            self.auth.verify_file(item)
        return producer

    def command(self, argv, **kwargs):
        self.calls.append(argv)
        label = Path(kwargs['stdout'].name).stem
        stdout = b''
        if label == 'build':
            binaries = self.output / 'bin'
            binaries.mkdir(exist_ok=True)
            names = ['emlf', 'mlfpkg'] + ['fixture-' + str(i) for i in range(11)]
            for name in names:
                (binaries / name).write_text(name)
            self.producer = {'optimization': '2', 'outputs': {
                name: self.auth.identified(binaries / name) for name in names}}
            (self.output / 'receipt.json').write_text(json.dumps(self.producer))
        elif label == 'runner-build':
            Path(argv[-1]).write_text('runner')
        elif label == 'runner-protocol':
            stdout = b'1\n'
        elif label.endswith('-identity'):
            stdout = (prepare.IDENTITY + '\n').encode()
        elif label == 'process-capability':
            stdout = b'1\n'
        elif label == 'completion-capability':
            stdout = b'41\n'
            if self.mutation:
                self.mutation()
        if self.bad == label:
            stdout = b'wrong\n'
        kwargs['stdout'].write(stdout)
        kwargs['stdout'].flush()
        if self.bad == 'stderr' and label == 'process-capability':
            kwargs['stderr'].write(b'diagnostic\n')
        if self.bad == 'timeout':
            raise subprocess.TimeoutExpired(argv, 1)
        return subprocess.CompletedProcess(argv, 1 if self.bad == 'exit' else 0)

    def execute(self):
        with patch.object(prepare, 'authenticator', return_value=self.auth), \
             patch.object(self.auth, 'authenticate_build', side_effect=self.authenticate), \
             patch.object(prepare.shutil, 'which', return_value=str(self.root / 'tools/clang')), \
             patch.object(prepare.subprocess, 'run', side_effect=self.command):
            return prepare.prepare(self.root, self.output, 'clang')

    def fails(self):
        self.output.mkdir(exist_ok=True)
        (self.output / 'async-tools.json').write_text('{"complete":true}')
        with self.assertRaises((ValueError, RuntimeError, subprocess.TimeoutExpired)):
            self.execute()
        self.assertFalse(json.loads((self.output / 'async-tools.json').read_text())['complete'])

    def test_success_is_separate_ghc_proof_with_unchanged_inventory(self):
        result = self.execute()
        self.assertTrue(result['complete'])
        self.assertEqual(result['implementation_identity'], prepare.IDENTITY)
        self.assertEqual(self.auth_count, 2)
        self.assertEqual(len(self.producer['outputs']), 13)
        self.assertNotIn('mlf-build-runner', json.loads((self.output / 'receipt.json').read_text())['outputs'])
        self.assertEqual(result['runner']['path'], str(self.output / 'bin/mlf-build-runner'))
        self.assertIn('--bootstrap-only', self.calls[0])
        self.assertIn('--optimization', self.calls[0])
        self.assertEqual(self.calls[1][1:6], ['-O2', '-std=c11', '-Wall', '-Wextra', '-Werror'])
        self.assertEqual(len(self.calls), 7)
        self.assertEqual(result['producer_receipt'], self.auth.identified(self.output / 'receipt.json'))

    def test_fail_closed_for_command_and_authentication_failures(self):
        for bad in ['exit', 'timeout', 'stderr', 'runner-protocol', 'emlf-identity',
                    'mlfpkg-identity', 'process-capability', 'completion-capability',
                    'authenticate', 'post-authenticate']:
            with self.subTest(bad=bad):
                self.bad = bad
                self.auth_count = 0
                self.fails()

    def test_changed_inputs_receipt_runner_outputs_and_logs_fail(self):
        for name in ['runtime/mlf_build_runner.c', 'tools/shared/prepare_async_ghc.py',
                     'tools/shared/test_direct.py', 'tools/clang', 'build/receipt.json',
                     'build/bin/mlf-build-runner.new', 'build/bin/mlfpkg', 'build/build.stdout']:
            with self.subTest(name=name):
                path = self.root / name
                prior = path.read_bytes() if path.exists() else None
                self.mutation = lambda: path.write_text('changed')
                self.fails()
                if prior is not None:
                    path.write_bytes(prior)

    def test_missing_clang_invalidates_old_proof(self):
        self.output.mkdir()
        (self.output / 'async-tools.json').write_text('{"complete":true}')
        with patch.object(prepare.shutil, 'which', return_value=None), self.assertRaises(ValueError):
            prepare.prepare(self.root, self.output, 'missing')
        self.assertFalse(json.loads((self.output / 'async-tools.json').read_text())['complete'])

    def test_authenticator_import_does_not_execute_main(self):
        with patch.object(subprocess, 'run', side_effect=AssertionError('unexpected command')):
            loaded = prepare.authenticator(self.root)
        self.assertTrue(callable(loaded.authenticate_build))

    def test_real_authentication_rejects_partial_and_wrong_host_receipts(self):
        self.output.mkdir()
        (self.root / 'shared-sources.json').write_text('{}')
        receipt = self.output / 'receipt.json'
        for value in [{'complete': False}, {'complete': True, 'typecheck_only': True},
                      {'complete': True, 'typecheck_only': False, 'producer_host': 'native-MLF'}]:
            receipt.write_text(json.dumps(value))
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.auth.authenticate_build(receipt, self.output / 'bin', self.root)


class CanonicalAsyncUnitOracles(unittest.TestCase):
    """Keep the existing byte-exact gates, including their negative boundary."""
    def test_canonical_oracles_remain_exact(self):
        root = HERE.parents[1]
        expected = b'IO ()\n'
        values = [(root / name).read_bytes() for name in (
            'tests/async-process/io-unit.type', 'tests/async-task/io-unit.type',
            'tests/async-task/guards.type')]
        script = (root / 'tests/fixtures/async-completion/check.sh').read_text()
        self.assertIn("printf 'IO ()\\n' > \"$work/io-unit.type\"", script)
        self.assertIn('cmp "$work/io-unit.type" "$work/$name.check.stdout"', script)
        for actual in values:
            self.assertEqual(actual, expected)
            for invalid in (b'IO Int\n', b'Unit\n', b'IO Unit\n', b'IO ()',
                            b'IO ()\nwarning\n', b'warning\nIO ()\n', b'IO () \n'):
                with self.subTest(actual=actual, invalid=invalid):
                    self.assertNotEqual(actual, invalid)
        for name in ('test-async-process.sh', 'test-async-task.sh'):
            text = (root / 'tools/release' / name).read_text()
            self.assertIn('cmp "$fixtures/', text)


    def test_scoped_fixture_migration_preserves_error_payloads(self):
        root = HERE.parents[1]
        for name in ('tests/async-process/Main.emlf', 'tests/async-process/Panic.emlf',
                     'tests/async-task/Main.emlf', 'tests/async-task/Processes.emlf'):
            text = (root / name).read_text()
            self.assertNotRegex(text, r'\b(?:Unit|List|Cons|Nil|Pair)\b')
            self.assertIn('(:)', text)
            self.assertIn('[]', text)
        task = (root / 'tests/async-task/Main.emlf').read_text()
        self.assertIn('integers : [] Int -> [] Int -> Bool', task)
        self.assertIn('case value of (,) stopped answer ->', task)
        negative = root / 'tests/fixtures/async-completion/negative'
        for name in ('alias-widen', 'mixed-values', 'generalize-allocated'):
            text = (negative / (name + '.emlf')).read_text()
            self.assertIn('asyncReadCompletion cell putStrLn (ioReturn ())', text)
            self.assertIn('42', text)
        self.assertIn('cell : forall a. Completion a',
                      (negative / 'generalize-allocated.emlf').read_text())
        self.assertIn('Completion (forall a. a -> a)',
                      (negative / 'impredicative-overwrite.emlf').read_text())
        self.assertIn('function "wrong"',
                      (negative / 'function-confusion.emlf').read_text())


class CurrentAsyncAbiGuard(unittest.TestCase):
    def setUp(self):
        path = HERE.parents[1] / 'tools/release/check_async_abi.py'
        spec = importlib.util.spec_from_file_location('check_async_abi', path)
        self.abi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.abi)
        self.declarations = [b'declare void @' + name + b'()' for name in self.abi.GUARDS]
        self.calls = [b'  call void @' + name + b'()' for name in self.abi.GUARDS]
        self.valid = b'\n'.join(self.declarations + [b'define ptr @mlf_entry() {'] +
                                 self.calls + [b'  ret ptr null', b'}', b''])

    def test_exact_current_contract(self):
        self.abi.check(self.valid)

    def test_each_declaration_and_entry_call_is_required(self):
        for line in self.declarations + self.calls:
            for replacement in (b'', b'; ' + line, line + b' ; mention only'):
                with self.subTest(line=line, replacement=replacement), self.assertRaises(ValueError):
                    self.abi.check(self.valid.replace(line, replacement))
        for altered in (
            self.valid.replace(b'haskell_boundary_v4', b'async_completion_v2'),
            self.valid.replace(b'define ptr @mlf_entry()', b'define ptr @unrelated()'),
            self.valid.replace(self.calls[0], b'  %root = call ptr @evaluate()\n' + self.calls[0]),
            self.valid + self.declarations[0] + b'\n',
            b'\n'.join(self.declarations + self.calls),
        ):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                self.abi.check(altered)

    def test_all_three_gates_bind_and_use_the_helper(self):
        root = HERE.parents[1]
        for name in ('tests/fixtures/async-completion/check.sh',
                     'tools/release/test-async-process.sh', 'tools/release/test-async-task.sh'):
            text = (root / name).read_text()
            self.assertIn('python3 -B "$root/tools/release/check_async_abi.py"', text)
            inputs = text.split('record_inputs()', 1)[1].split('record_inputs ', 1)[0]
            self.assertIn('"$root/tools/release/check_async_abi.py"', inputs)
            self.assertNotIn('mlf_require_async_completion_v2_abi', text)


class MixedCompletionIntegerPayload(unittest.TestCase):
    def setUp(self):
        root = HERE.parents[1] / 'tests/fixtures/async-completion/runtime'
        self.source = (root / 'mixed-values.emlf').read_text()
        self.expected = (root / 'mixed-values.expected').read_bytes()

    def test_explicit_integer_payload_keeps_int_statuses(self):
        self.assertIn('printPayload : Integer -> IO ()', self.source)
        self.assertIn('printPayload value = putStrLn (showInteger value)', self.source)
        self.assertIn('asyncSubscribeCompletion integers printPayload', self.source)
        self.assertEqual(self.source.count('asyncReadCompletion integers printPayload'), 2)
        self.assertIn('ioBind (asyncResolveCompletion integers (readInteger "123456789012345678901234567890")) printInt', self.source)
        self.assertIn('ioBind (asyncResolveCompletion integers (intToInteger 0)) printInt', self.source)
        self.assertIn('ioBind (asyncResolveCompletion integers (panic "duplicate payload forced")) printInt', self.source)
        self.assertNotIn('integers printInt', self.source)
        self.assertIn('asyncReadCompletion strings putStrLn (putStrLn "closed")', self.source)

    def test_literal_observation_is_not_replaced_by_wrapped_int(self):
        original = (b'1\n0\n0\n0\n2\n123456789012345678901234567890\n0\ntyped string\n0\n1\n'
                    b'123456789012345678901234567890\n123456789012345678901234567890\n'
                    b'0\ntyped string\n0\n6\n3\nclosed\n')
        self.assertEqual(self.expected, original)
        payload = b'123456789012345678901234567890'
        wrapped = ((int(payload) + 2**63) % 2**64) - 2**63
        self.assertEqual(wrapped, -4362896299872285998)
        for wrong in (str(wrapped).encode(), b'42', b'0'):
            with self.subTest(wrong=wrong):
                self.assertNotEqual(self.expected, self.expected.replace(payload, wrong))
        self.assertNotEqual(self.expected, self.expected.rstrip(b'\n'))
        self.assertNotEqual(self.expected, self.expected + b'diagnostic\n')


class CompletionKindRejection(unittest.TestCase):
    def test_wrong_kind_reaches_kind_checker_without_cons_ambiguity(self):
        root = HERE.parents[1]
        source = (root / 'tests/fixtures/async-completion/negative/wrong-kind.emlf').read_text()
        self.assertEqual(source, 'main = panic "unused" :: Completion IO\n')
        gate = (root / 'tests/fixtures/async-completion/check.sh').read_text()
        self.assertIn("wrong-kind) expected='(kind|arity)' ;;", gate)


if __name__ == '__main__':
    unittest.main()
