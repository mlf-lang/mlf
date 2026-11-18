#!/usr/bin/env python3
"""Mock-only entry routing checks: no source contract, compiler or workload."""
import copy
import json
import signal
import subprocess
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import test_direct_crc_successor as E


class EntryTests(unittest.TestCase):
    def invoke(self, action):
        root = E.HERE.parents[1]
        calls = []
        class Base:
            def __init__(self):
                self.root = root
                self.output = root / 'synthetic-output'
                self.receipt = dict(producer=dict(path='/fixture/receipt.json', sha256='fixture'),
                                    inputs={'/fixture/receipt.json': 'fixture'}, commands=[])
                self.save = lambda: None
            def run(self, *args, **kwargs):
                calls.append((args, kwargs))
                return 'original-result'
        original = types.SimpleNamespace(CommandRunner=Base, ROOT=root, sha=lambda _: 'fixture')
        original.main = lambda: action(original.CommandRunner(), calls)
        with patch.object(E, 'pinned_inputs', return_value={'synthetic': 'identity'}), \
             patch.object(E, 'load_original', return_value=({'synthetic': 'identity'}, original)), \
             patch.object(E, 'require_pidfd'):
            E.main()

    @staticmethod
    def argv(runner):
        return [sys.executable, '-B', str(E.HERE / 'test_crc32.py'), '--build-receipt',
                '/fixture/receipt.json', '--clang', 'clang', '--output', str(runner.output / 'bulk-crc')]

    def test_other_commands_preserve_all_arguments_and_result(self):
        def action(runner, calls):
            result = runner.run('unrelated', ['x', Path('/y')], overrides={'A': 'B'},
                                status=7, expected=b'answer', timeout=13)
            self.assertEqual(result, 'original-result')
            self.assertEqual(calls, [(('unrelated', ['x', Path('/y')]),
                dict(overrides={'A': 'B'}, status=7, expected=b'answer', timeout=13))])
        self.invoke(action)

    def test_bulk_mismatches_fail_before_spawn(self):
        def action(runner, calls):
            originals = self.argv(runner)
            variants = []
            for index in (0, 1, 2, 3, 5, 7, 8):
                bad = copy.copy(originals); bad[index] = 'wrong'
                variants.append((bad, dict(timeout=600)))
            variants.extend([(originals + ['extra'], dict(timeout=600)),
                             (originals, dict(timeout=599)),
                             (originals, dict(timeout=600, overrides={'A': 'B'})),
                             (originals, dict(timeout=600, expected=b'')),
                             (originals, dict(timeout=600, status=1))])
            with patch.object(E.subprocess, 'Popen') as spawn:
                for argv, kwargs in variants:
                    with self.subTest(argv=argv, kwargs=kwargs), self.assertRaisesRegex(RuntimeError, 'unexpected bulk'):
                        runner.run('bulk-crc', argv, **kwargs)
                runner.root = Path('/wrong-root')
                with self.assertRaisesRegex(RuntimeError, 'unexpected bulk'):
                    runner.run('bulk-crc', originals, timeout=600)
                spawn.assert_not_called()
            self.assertEqual(calls, [])
        self.invoke(action)

    def test_wrong_producer_instance_fails_before_spawn(self):
        def action(runner, calls):
            argv = self.argv(runner)
            argv[4] = '/unrelated/receipt.json'
            with patch.object(E.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(RuntimeError, 'authenticated instance'):
                    runner.run('bulk-crc', argv, timeout=600)
                spawn.assert_not_called()
        self.invoke(action)

    def test_missing_pidfd_capability_never_spawns(self):
        def action(runner, calls):
            with patch.object(E, 'require_pidfd', side_effect=RuntimeError('no pidfd')), \
                 patch.object(E.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(RuntimeError, 'no pidfd'):
                    runner.run('bulk-crc', self.argv(runner), timeout=600)
                spawn.assert_not_called()
        self.invoke(action)

    def test_changed_pins_fail_before_execution(self):
        def action(runner, calls):
            with patch.object(E, 'pinned_inputs', return_value={'changed': 'identity'}), \
                 patch.object(E.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(RuntimeError, 'inputs changed'):
                    runner.run('bulk-crc', self.argv(runner), timeout=600)
                spawn.assert_not_called()
        self.invoke(action)

    def test_frozen_original_corruption_is_rejected(self):
        with patch.object(Path, 'read_bytes', return_value=b'changed original'):
            with self.assertRaisesRegex(RuntimeError, 'frozen CRC successor original changed'):
                E.pinned_inputs()

    def mock_bulk(self, mode):
        observed = {}
        with tempfile.TemporaryDirectory() as directory:
            def action(runner, calls):
                runner.output = Path(directory)
                argv = self.argv(runner)
                original_handlers = {signal.SIGTERM: object(), signal.SIGINT: object()}
                handlers = dict(original_handlers)
                process = types.SimpleNamespace(pid=321, returncode=None)
                def handler(sig, value):
                    old = handlers[sig]; handlers[sig] = value; return old
                def spawn(actual, **kwargs):
                    observed['argv'] = actual
                    observed['spawn_kwargs'] = kwargs
                    guard = Path(actual[actual.index('--receipt') + 1])
                    guard.write_text('{broken' if mode == 'malformed' else json.dumps(
                        dict(complete=True, cleanup_complete=True, phase='terminal')))
                    return process
                count = [0]
                def communicate(timeout):
                    count[0] += 1
                    if mode == 'cancel' and count[0] == 1:
                        # Exercise the installed external cancellation handler,
                        # rather than pretending the supervisor exited itself.
                        handlers[signal.SIGTERM](signal.SIGTERM, None)
                    process.returncode = 1 if mode == 'cancel' else 0
                    if mode == 'cancel':
                        (runner.output / 'bulk-crc-supervisor.json').write_text(json.dumps(
                            dict(complete=False, cleanup_complete=True, reason='cancelled')))
                    return b'finite output', b''
                process.communicate = Mock(side_effect=communicate)
                original_write = Path.write_bytes
                def write(path, data):
                    if mode == 'log-failure' and path.name == 'bulk-crc.stdout':
                        raise OSError('injected log failure')
                    return original_write(path, data)
                with patch.object(E.subprocess, 'Popen', side_effect=spawn), \
                     patch.object(E.os, 'pidfd_open', create=True, return_value=42) as open_fd, \
                     patch.object(E.os, 'close') as close_fd, \
                     patch.object(E.os, 'killpg', side_effect=AssertionError('bulk must not use group kill')) as kill_group, \
                     patch.object(E.signal, 'pidfd_send_signal', create=True) as send, \
                     patch.object(E.signal, 'signal', side_effect=handler), \
                     patch.object(E.signal, 'pthread_sigmask', return_value=set()), \
                     patch.object(Path, 'write_bytes', write):
                    if mode == 'positive':
                        result = runner.run('bulk-crc', argv, timeout=600)
                        self.assertEqual(result.args, argv)
                        self.assertEqual(result.returncode, 0)
                        self.assertEqual(result.stdout, b'finite output')
                    else:
                        kind = KeyboardInterrupt if mode == 'cancel' else (json.JSONDecodeError if mode == 'malformed' else OSError)
                        with self.assertRaises(kind):
                            runner.run('bulk-crc', argv, timeout=600)
                    self.assertEqual(handlers, original_handlers)
                    open_fd.assert_called_once_with(321)
                    close_fd.assert_called_once_with(42)
                    kill_group.assert_not_called()
                    observed['signals'] = send.call_args_list
                    observed['communications'] = process.communicate.call_args_list
                self.assertEqual(calls, [])
                observed['entry'] = runner.receipt['commands'][0]
                observed['original_argv'] = argv
            self.invoke(action)
        return observed

    def test_exact_positive_bulk_route_and_receipt(self):
        actual = self.mock_bulk('positive')
        argv = actual['argv']
        self.assertEqual(argv[:3], [sys.executable, '-B', str(E.HERE / 'crc_process_supervisor.py')])
        self.assertEqual(argv[3], '--receipt')
        self.assertEqual(Path(argv[4]).name, 'bulk-crc-supervisor.json')
        self.assertEqual(argv[5:9], ['--work-seconds', '1800', '--cleanup-seconds', '10'])
        self.assertEqual(argv[9:], actual['original_argv'])
        self.assertEqual(actual['communications'], [unittest.mock.call(timeout=1825)])
        self.assertEqual(actual['signals'], [])
        entry = actual['entry']
        self.assertEqual(entry['state'], 'passed')
        self.assertEqual(entry['input_pins'], {'synthetic': 'identity'})
        self.assertEqual(entry['original_timeout_seconds'], 600)
        self.assertEqual(entry['timeout_seconds'], 1825)
        self.assertEqual(entry['work_seconds'], 1800)
        self.assertEqual(entry['cleanup_seconds'], 10)
        self.assertTrue(entry['supervisor']['complete'])

    def test_external_cancel_uses_pidfd_and_full_cleanup_grace(self):
        actual = self.mock_bulk('cancel')
        self.assertEqual(actual['communications'], [unittest.mock.call(timeout=1825), unittest.mock.call(timeout=25)])
        self.assertEqual(actual['signals'], [unittest.mock.call(42, signal.SIGTERM)])
        self.assertEqual(actual['entry']['state'], 'failed')
        self.assertTrue(actual['entry']['supervisor']['cleanup_complete'])
        self.assertFalse(actual['entry']['supervisor']['complete'])

    def test_malformed_guard_restores_handlers_and_closes_pidfd(self):
        actual = self.mock_bulk('malformed')
        self.assertEqual(actual['entry']['state'], 'failed')
        self.assertIn('evidence_error', actual['entry'])

    def test_log_failure_restores_handlers_and_closes_pidfd(self):
        actual = self.mock_bulk('log-failure')
        self.assertEqual(actual['entry']['state'], 'failed')
        self.assertIn('injected log failure', actual['entry']['evidence_error'])


if __name__ == '__main__':
    unittest.main()
