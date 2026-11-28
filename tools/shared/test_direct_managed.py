"""Direct-suite routing and real bounded descendant cleanup controls."""
from dataclasses import replace
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

import direct_managed as E


class EntryControls(unittest.TestCase):
    def fixture(self, suite, root=None):
        root = E.direct.ROOT if root is None else root
        runner = E.ManagedRunner(root, Path('/out'), {
            'producer': {'path': '/build/receipt.json', 'sha256': 'producer'},
            'inputs': {'/build/receipt.json': 'producer'}, 'commands': []}, lambda: None)
        argv = [sys.executable, '-B', str(E.HERE / suite.script), '--build-receipt',
                '/build/receipt.json', '--clang', 'clang', '--output', str(runner.output / suite.name)]
        return runner, argv

    def test_managed_routes_validate_every_operand_before_spawn(self):
        for suite in E.SUITES.values():
            runner, argv = self.fixture(suite)
            with mock.patch.object(E.direct, 'sha', return_value='producer'), \
                 mock.patch.object(E, 'snapshot', return_value={'source': 'current'}), \
                 mock.patch.object(E, 'managed', return_value='managed') as call:
                self.assertEqual(runner.run(suite.name, argv, timeout=600), 'managed')
                call.assert_called_once_with(runner, suite, {'source': 'current'}, argv)
                call.reset_mock()
                for index in (0, 1, 2, 3, 4, 5, 7, 8):
                    wrong = list(argv); wrong[index] = 'wrong'
                    with self.subTest(suite=suite.name, operand=index), self.assertRaises(RuntimeError):
                        runner.run(suite.name, wrong, timeout=600)
                for options in ({'timeout': 625}, {'timeout': 600, 'overrides': {'X': '1'}},
                                {'timeout': 600, 'status': False}, {'timeout': 600, 'expected': b''}):
                    with self.assertRaises(RuntimeError): runner.run(suite.name, argv, **options)
                runner.receipt['producer']['sha256'] = 'different'
                with self.assertRaises(RuntimeError): runner.run(suite.name, argv, timeout=600)
                call.assert_not_called()

    def test_unmanaged_commands_preserve_all_arguments(self):
        runner, _ = self.fixture(E.SUITES['bulk-crc'])
        with mock.patch.object(E.direct.CommandRunner, 'run', return_value='physical') as run:
            self.assertEqual(runner.run('other', ['cmd', Path('/input')], overrides={'X': '1'},
                                        status=7, expected=b'answer', timeout=13), 'physical')
            run.assert_called_once_with('other', ['cmd', Path('/input')], overrides={'X': '1'},
                                        status=7, expected=b'answer', timeout=13)

    def test_capability_and_source_drift_fail_before_spawn(self):
        suite = E.SUITES['bulk-crc']
        with tempfile.TemporaryDirectory() as directory:
            runner, argv = self.fixture(suite)
            runner.output = Path(directory)
            with mock.patch.object(E.subprocess, 'Popen') as spawn:
                with mock.patch.object(E, 'require_pidfd', side_effect=RuntimeError('no pidfd')):
                    with self.assertRaisesRegex(RuntimeError, 'no pidfd'):
                        E.managed(runner, suite, {}, argv)
                with mock.patch.object(E, 'require_pidfd'), mock.patch.object(E, 'snapshot', return_value={'new': 'input'}):
                    with self.assertRaisesRegex(RuntimeError, 'inputs changed'):
                        E.managed(runner, suite, {}, argv)
                spawn.assert_not_called()

    @staticmethod
    def terminal():
        guard = dict(phase='terminal', reason='target exited', complete=True, cleanup_complete=True,
                     target_exit_code=0, survivors=[], signals=[], cancel_signals=[],
                     command=['worker', 'exact'], work_seconds=600., cleanup_seconds=10.,
                     root_pid=123, reaped=[dict(pid=123, status=0)])
        worker = dict(complete=True, input_pins={'source': 'digest'},
                      producer_receipt_path='/receipt', producer_receipt_sha256='producer')
        binding = dict(worker_argv=['worker', 'exact'], pins={'source': 'digest'},
                       producer_path='/receipt', producer_sha='producer', work=600, cleanup=10)
        return guard, worker, binding

    def test_terminal_requires_real_exit_cleanup_and_input_identity(self):
        guard, worker, binding = self.terminal()
        E.validate_terminal(0, guard, worker, b'', **binding)
        for field in guard:
            wrong = dict(guard); wrong.pop(field)
            with self.subTest(missing=field), self.assertRaises(RuntimeError):
                E.validate_terminal(0, wrong, worker, b'', **binding)
        changes = {'error': None, 'cleanup_error': None, 'complete': False, 'cleanup_complete': False,
                   'target_exit_code': False, 'survivors': [456], 'signals': [15], 'cancel_signals': [2],
                   'command': ['another'], 'work_seconds': 625, 'cleanup_seconds': True, 'root_pid': True,
                   'reaped': [dict(pid=123, status=False)]}
        for field, value in changes.items():
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                E.validate_terminal(0, dict(guard, **{field: value}), worker, b'', **binding)
        for wrong in ([], [dict(pid=124, status=0)], [dict(pid=True, status=0)],
                      [dict(pid=123, status=0)] * 2):
            with self.assertRaises(RuntimeError):
                E.validate_terminal(0, dict(guard, reaped=wrong), worker, b'', **binding)
        for field in worker:
            wrong = dict(worker); wrong.pop(field)
            with self.assertRaises(RuntimeError): E.validate_terminal(0, guard, wrong, b'', **binding)
        for status, stderr in ((False, b''), (1, b''), (0, b'error')):
            with self.assertRaises(RuntimeError): E.validate_terminal(status, guard, worker, stderr, **binding)

    def test_fresh_destinations_do_not_overwrite_receipts_or_links(self):
        for suite in E.SUITES.values():
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                guard, receipt = E.fresh_destinations(root, suite)
                paths = (root / suite.name, guard, guard.with_suffix('.tmp'),
                         root / (suite.name + '.stdout'), root / (suite.name + '.stderr'))
                if suite.worker: paths += (receipt, receipt.with_suffix('.tmp'))
                for path in paths:
                    path.write_bytes(b'previous evidence')
                    with self.assertRaises(RuntimeError): E.fresh_destinations(root, suite)
                    self.assertEqual(path.read_bytes(), b'previous evidence')
                    path.unlink()
                (root / suite.name).symlink_to(root / 'absent')
                with self.assertRaises(RuntimeError): E.fresh_destinations(root, suite)

    def managed_mock(self, suite, failure=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); out = root / 'out'; out.mkdir()
            runner, argv = self.fixture(suite, root)
            runner.output = out; argv[-1] = str(out / suite.name)
            pins = {'source': 'current'}
            before = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
            calls = []
            def spawn(actual, **kwargs):
                calls.append(actual)
                guard, worker, _ = self.terminal()
                guard.update(command=actual[9:], work_seconds=float(suite.work), cleanup_seconds=float(suite.cleanup))
                (out / (suite.name + '-supervisor.json')).write_text(
                    '{malformed' if failure == 'malformed' else json.dumps(guard))
                if suite.worker:
                    worker.update(input_pins=pins, producer_receipt_path=argv[4])
                    path = out / (suite.name + '-batch-worker.json')
                else:
                    worker = dict(complete=True, producer_sha256='producer')
                    path = out / suite.name / 'receipt.json'; path.parent.mkdir()
                if failure == 'incomplete': worker['complete'] = False
                path.write_text(json.dumps(worker))
                return types.SimpleNamespace(pid=456, returncode=0,
                                             communicate=lambda timeout: (b'actual output\n', b''))
            original_write = Path.write_bytes
            def write(path, data):
                if failure == 'log' and path.name.endswith('.stdout'): raise OSError('injected log failure')
                return original_write(path, data)
            with mock.patch.object(E, 'HERE', root), mock.patch.object(E, 'snapshot', return_value=pins), \
                 mock.patch.object(E, 'require_pidfd'), mock.patch.object(E.direct, 'sha', return_value='producer'), \
                 mock.patch.object(E.subprocess, 'Popen', side_effect=spawn), \
                 mock.patch.object(E.os, 'pidfd_open', return_value=789, create=True), \
                 mock.patch.object(E.os, 'close') as close, mock.patch.object(Path, 'write_bytes', write):
                if failure:
                    with self.assertRaises((RuntimeError, ValueError, OSError)): E.managed(runner, suite, pins, argv)
                else:
                    self.assertEqual(E.managed(runner, suite, pins, argv).stdout, b'actual output\n')
                close.assert_called_once_with(789)
            for sig, handler in before.items(): self.assertEqual(signal.getsignal(sig), handler)
            entry = runner.receipt['commands'][0]
            self.assertEqual(entry['state'], 'failed' if failure else 'passed')
            self.assertEqual(entry['timeout_seconds'], suite.outer)
            self.assertEqual(calls[0][9:], [sys.executable, '-B', str(root / (suite.worker or suite.script)), *argv[3:]])
            if failure in ('log', 'malformed'): self.assertIn('evidence_error', entry)

    def test_all_suites_use_one_supervisor_with_their_real_budgets(self):
        for suite in E.SUITES.values():
            with self.subTest(suite=suite.name): self.managed_mock(suite)

    def test_evidence_failure_restores_handlers_and_closes_pidfd(self):
        for suite in E.SUITES.values():
            for failure in ('malformed', 'log', 'incomplete'):
                with self.subTest(suite=suite.name, failure=failure): self.managed_mock(suite, failure)


@unittest.skipUnless(sys.platform == 'linux', 'requires Linux pidfds and procfs')
class RealSyntheticControls(unittest.TestCase):
    """Exercise production cancellation against an escaped, TERM-ignoring child."""
    @classmethod
    def setUpClass(cls):
        cls.supervisor = (E.HERE / 'crc_process_supervisor.py').read_bytes()
        cls.evidence = None
        if os.environ.get('MLF_DIRECT_TEST_EVIDENCE'):
            cls.evidence = Path(os.environ['MLF_DIRECT_TEST_EVIDENCE']).resolve()
            cls.evidence.mkdir(parents=True, exist_ok=False)

    def case(self, name, work, outer, cancel=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); out = root / 'out'; out.mkdir()
            (root / 'crc_process_supervisor.py').write_bytes(self.supervisor)
            (root / 'candidate_batch_worker.py').write_text('''import os,signal,time,json
from pathlib import Path
r,w=os.pipe()
pid=os.fork()
if pid==0:
    os.close(r);os.setsid();signal.signal(signal.SIGTERM,signal.SIG_IGN)
    os.write(w,b'R');os.close(w)
    while True:time.sleep(1)
os.close(w)
if os.read(r,1)!=b'R':raise RuntimeError('child readiness')
os.close(r)
Path(__file__).with_name('readiness.json').write_text(json.dumps({'root_pid':os.getpid(),'child_pid':pid}))
while True:time.sleep(1)
''')
            runner = types.SimpleNamespace(root=root, output=out,
                         receipt={'commands': [], 'producer': {'sha256': 'synthetic'}})
            runner.save = lambda: (out / 'outer.json').write_text(json.dumps(runner.receipt, indent=2) + '\n')
            suite = replace(E.SUITES['candidate-selection'], work=work, cleanup=2, margin=outer-work-2)
            argv = [sys.executable, '-B', str(root / suite.script), '--build-receipt', 'synthetic',
                    '--clang', 'clang', '--output', str(out / suite.name)]
            timer = None
            before = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
            real_popen = subprocess.Popen
            def spawn(*args, **kwargs):
                nonlocal timer
                process = real_popen(*args, **kwargs)
                if cancel:
                    timer = threading.Timer(.7, lambda: os.kill(os.getpid(), signal.SIGTERM)); timer.start()
                return process
            try:
                # Keep a separate, sufficient cancellation grace while testing
                # an outer timeout shorter than the worker's deadline.
                with mock.patch.object(E, 'HERE', root), mock.patch.object(E, 'snapshot', return_value={}), \
                     mock.patch.object(E.Suite, 'cancel_grace', new_callable=mock.PropertyMock, return_value=4), \
                     mock.patch.object(E.subprocess, 'Popen', side_effect=spawn):
                    with self.assertRaises((RuntimeError, subprocess.TimeoutExpired, KeyboardInterrupt)):
                        E.managed(runner, suite, {}, argv)
                guard = json.loads((out / (suite.name + '-supervisor.json')).read_text())
                ready = json.loads((root / 'readiness.json').read_text())
                self.assertEqual(guard['root_pid'], ready['root_pid'])
                reaped = {row['pid']: row['status'] for row in guard['reaped']}
                self.assertIn(ready['root_pid'], reaped)
                self.assertEqual(reaped[ready['child_pid']], -signal.SIGKILL)
                sent = {(row['pid'], row['signal']) for row in guard['signals']}
                self.assertIn((ready['child_pid'], signal.SIGTERM), sent)
                self.assertIn((ready['child_pid'], signal.SIGKILL), sent)
                self.assertTrue(guard['cleanup_complete']); self.assertEqual(guard['survivors'], [])
                self.assertEqual(guard['phase'], 'terminal'); self.assertFalse(guard['complete'])
                entry = runner.receipt['commands'][0]
                self.assertEqual(entry['state'], 'failed'); self.assertNotIn('cleanup_unverified', entry)
                self.assertEqual(guard['reason'], 'work deadline' if name == 'work-deadline' else 'cancelled')
                if name == 'outer-timeout': self.assertTrue(entry['error'].startswith('TimeoutExpired('))
                if cancel:
                    self.assertTrue(entry['error'].startswith('KeyboardInterrupt('))
                    self.assertIn(signal.SIGTERM, guard['cancel_signals'])
            finally:
                if timer is not None: timer.cancel(); timer.join(timeout=1)
                for sig, handler in before.items(): self.assertEqual(signal.getsignal(sig), handler)
                if self.evidence is not None:
                    destination = self.evidence / name; destination.mkdir(exist_ok=False)
                    for path in out.iterdir():
                        if path.suffix in ('.json', '.stdout', '.stderr'):
                            (destination / path.name).write_bytes(path.read_bytes())
                    if (root / 'readiness.json').is_file():
                        (destination / 'readiness.json').write_bytes((root / 'readiness.json').read_bytes())

    def test_work_deadline_cleanup(self): self.case('work-deadline', .7, 5)
    def test_outer_timeout_cleanup(self): self.case('outer-timeout', 5, .7)
    def test_external_cancel_cleanup(self): self.case('external-cancel', 5, 6, True)


if __name__ == '__main__':
    unittest.main()
