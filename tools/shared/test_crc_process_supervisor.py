#!/usr/bin/env python3
"""Finite synthetic lifecycle tests, never invokes a compiler or CRC workload."""
import json
import errno
import contextlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import crc_process_supervisor as S


class SupervisorTests(unittest.TestCase):
    evidence_root = None
    evidence_counter = 0

    def evidence_case(self):
        configured = os.environ.get('MLF_CRC_TEST_EVIDENCE')
        if not configured:
            return None
        cls = type(self)
        if cls.evidence_root is None:
            root = Path(configured)
            # Normal and optimized invocations must use separate fresh roots.
            root.mkdir(parents=True, exist_ok=False)
            cls.evidence_root = root
        elif cls.evidence_root != Path(configured):
            raise RuntimeError('evidence destination changed during test process')
        cls.evidence_counter += 1
        destination = cls.evidence_root / ('%03d-%s' % (cls.evidence_counter, self._testMethodName))
        destination.mkdir(exist_ok=False)
        return destination

    def run_case(self, script, work=0.5, cancel=False, ready=False):
        evidence = self.evidence_case()
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / 'receipt.json'
            probe = os.pidfd_open(os.getpid())
            os.close(probe)
            p = subprocess.Popen([sys.executable, '-B', str(Path(S.__file__)),
                '--receipt', str(receipt), '--work-seconds', str(work),
                '--cleanup-seconds', '2', sys.executable, '-c', script, str(Path(directory) / 'ready')],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            fd = None
            stdout = stderr = b''
            try:
                fd = os.pidfd_open(p.pid)
                if cancel:
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        if (receipt.exists() and json.loads(receipt.read_text()).get('phase') == 'work'
                                and (not ready or (Path(directory) / 'ready').exists())):
                            p.send_signal(signal.SIGTERM)
                            break
                        time.sleep(0.01)
                    else:
                        self.fail('supervisor did not enter work')
                    if cancel == 'twice':
                        deadline = time.monotonic() + 2
                        while time.monotonic() < deadline:
                            current = json.loads(receipt.read_text())
                            if current.get('phase') == 'cleanup':
                                p.send_signal(signal.SIGTERM)
                                break
                            time.sleep(0.005)
                        else:
                            self.fail('supervisor did not enter cleanup')
                stdout, stderr = p.communicate(timeout=6)
                return p.returncode, json.loads(receipt.read_text()), stderr
            finally:
                try:
                    if p.returncode is None:
                        try:
                            if fd is None:
                                p.terminate()  # This Popen child has not been reaped.
                            else:
                                signal.pidfd_send_signal(fd, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        try:
                            stdout, stderr = p.communicate(timeout=4)  # Exceeds this test's 2s cleanup.
                        except subprocess.TimeoutExpired:
                            try:
                                if fd is None:
                                    p.kill()
                                else:
                                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            try:
                                stdout, stderr = p.communicate(timeout=2)
                            except subprocess.TimeoutExpired as capture:
                                stdout, stderr = capture.stdout or b'', capture.stderr or b''
                                p.stdout.close(); p.stderr.close()
                                try:
                                    p.wait(timeout=2)
                                except subprocess.TimeoutExpired:
                                    pass
                            self.fail('test cleanup grace expired: supervisor SIGKILL; descendant cleanup UNVERIFIED')
                finally:
                    try:
                        if fd is not None:
                            os.close(fd)
                    finally:
                        if evidence is not None:
                            # Only real subprocess evidence is exported. The
                            # mock fault-injection tests never call this path.
                            if receipt.is_file():
                                with (evidence / 'receipt.json').open('xb') as stream:
                                    stream.write(receipt.read_bytes())
                            with (evidence / 'stdout').open('xb') as stream:
                                stream.write(stdout)
                            with (evidence / 'stderr').open('xb') as stream:
                                stream.write(stderr)

    def test_normal_and_status_forwarding(self):
        for code in (0, 7):
            status, receipt, err = self.run_case('raise SystemExit(%s)' % code)
            self.assertEqual(status, code, err)
            self.assertEqual(receipt['complete'], code == 0)
            self.assertTrue(receipt['cleanup_complete'])

    def test_nested_sessions_term_resistance_and_early_exit(self):
        for early in (False, True, False, True):
            script = '''import os,signal,time
read_ready,write_ready=os.pipe()
pid=os.fork()
if pid==0:
 os.close(read_ready)
 os.setsid()
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 os.close(1);os.close(2)
 os.write(write_ready,b'R');os.close(write_ready)
 while True: time.sleep(1)
os.close(write_ready)
if os.read(read_ready,1)!=b'R': raise RuntimeError('child readiness missing')
os.close(read_ready)
'''
            if not early:
                script += 'while True: time.sleep(1)\n'
            status, receipt, err = self.run_case(script, work=1)
            self.assertNotEqual(status, 0, err)
            self.assertTrue(receipt['cleanup_complete'])
            self.assertEqual(receipt['survivors'], [])
            self.assertGreaterEqual(len(receipt['reaped']), 2)
            self.assertIn(9, [row['signal'] for row in receipt['signals']])

    def test_cancellation(self):
        status, receipt, err = self.run_case('import time; time.sleep(20)', work=3, cancel=True)
        self.assertNotEqual(status, 0, err)
        self.assertEqual(receipt['reason'], 'cancelled')
        self.assertTrue(receipt['cleanup_complete'])

    def test_unrelated_child_survives_timeout(self):
        unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])
        try:
            status, receipt, err = self.run_case('import time; time.sleep(20)')
            self.assertNotEqual(status, 0, err)
            self.assertEqual(receipt['reason'], 'work deadline')
            self.assertTrue(receipt['cleanup_complete'])
            self.assertIsNone(unrelated.poll())
            self.assertNotIn(unrelated.pid, [row['pid'] for row in receipt['signals']])
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=2)

    def test_second_cancel_does_not_interrupt_cleanup(self):
        # Explicit target readiness prevents an exec/handler installation race.
        script = ('import signal,time,pathlib,sys; signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                  'pathlib.Path(sys.argv[1]).write_text("ready"); time.sleep(20)')
        status, receipt, err = self.run_case(script, work=3, cancel='twice', ready=True)
        self.assertNotEqual(status, 0, err)
        self.assertTrue(receipt['cleanup_complete'])
        self.assertGreaterEqual(len(receipt['cancel_signals']), 2)
        self.assertIn(9, [row['signal'] for row in receipt['signals']])

    def test_cleanup_deadline_is_not_success_or_empty_tree(self):
        record = dict(reaped=[], signals=[], cleanup_complete=False)
        with patch.object(os, 'waitpid', return_value=(0, 0)):
            with patch.object(S, 'children', return_value=[12345]):
                with patch.object(S.time, 'monotonic', side_effect=[0, 2]):
                    with patch.object(S, 'signal_child') as send:
                        S.cleanup(12345, 1, record)
                        send.assert_not_called()
        self.assertFalse(record['cleanup_complete'])
        self.assertEqual(record['survivors'], [12345])
        self.assertIn('before ECHILD', record['cleanup_error'])

    def test_cleanup_exception_is_saved_as_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / 'receipt.json'
            with patch.object(S, 'enable_subreaper'), patch.object(S, 'children', return_value=[]), \
                 patch.object(os, 'fork', return_value=12345), patch.object(os, 'waitid', return_value=object()), \
                 patch.object(S, 'cleanup', side_effect=RuntimeError('injected cleanup failure')):
                status = S.supervise([sys.executable, '-c', 'pass'], receipt, 1, 1)
            record = json.loads(receipt.read_text())
            self.assertNotEqual(status, 0)
            self.assertFalse(record['complete'])
            self.assertFalse(record['cleanup_complete'])
            self.assertIn('injected cleanup failure', record['cleanup_error'])

    def test_nonchild_is_never_signalled(self):
        with patch.object(signal, 'pidfd_send_signal') as send:
            with self.assertRaisesRegex(RuntimeError, 'non-child'):
                S.signal_child(os.getpid(), signal.SIGTERM)
            send.assert_not_called()

    def test_capability_fails_closed(self):
        with patch.object(S.sys, 'platform', 'unsupported'):
            with self.assertRaisesRegex(RuntimeError, 'Linux'):
                S.enable_subreaper()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(S, 'enable_subreaper', side_effect=RuntimeError('unavailable')):
                with patch.object(os, 'fork') as fork:
                    status = S.supervise([sys.executable, '-c', 'pass'], Path(directory) / 'r.json', 1, 1)
                    fork.assert_not_called()
                    self.assertNotEqual(status, 0)


class ProcFallbackTests(unittest.TestCase):
    def discover(self, rows, *, self_pid=100, task_error=None, clock=None, cleanup=False):
        entries = [types.SimpleNamespace(name=str(pid), path='/proc/' + str(pid)) for pid in rows]
        def read(path, *args, **kwargs):
            value = str(path)
            if value == '/proc/self/stat':
                return '%s (self) S 1 0' % self_pid
            if value == '/proc/self/task/100/children':
                raise task_error or FileNotFoundError(errno.ENOENT, 'absent', value)
            pid = int(path.parent.name)
            row = rows[pid]
            if isinstance(row, BaseException):
                raise row
            return row
        timing = patch.object(S.time, 'monotonic', side_effect=clock) if clock else contextlib.nullcontext()
        with patch.object(os, 'getpid', return_value=100), patch.object(Path, 'read_text', read), \
             patch.object(os, 'scandir', side_effect=lambda _: contextlib.nullcontext(iter(entries))), \
             timing, \
             patch.object(S, 'signal_child') as send:
            if cleanup:
                with patch.object(os, 'waitpid', return_value=(0, 0)):
                    try:
                        S.cleanup(101, 1, dict(reaped=[], signals=[]))
                    finally:
                        send.assert_not_called()
            else:
                return S.children()

    def test_exact_children_only_and_vanished_race(self):
        self.assertEqual(self.discover({101: '101 (child) S 100 0',
                                       102: '102 (unrelated) S 999 0',
                                       103: FileNotFoundError(errno.ENOENT, 'vanished')}), [101])
        self.assertTrue(S.children.last_discovery['snapshot_complete'])
        self.assertFalse(S.children.last_discovery['absence_proven'])

    def test_namespace_and_directory_identity_mismatch_reject(self):
        with self.assertRaisesRegex(RuntimeError, 'namespace'):
            self.discover({}, self_pid=999)
        with self.assertRaisesRegex(RuntimeError, 'directory identity'):
            self.discover({101: '999 (wrong) S 100 0'})

    def test_opaque_task_children_cannot_fallback(self):
        with self.assertRaises(PermissionError):
            self.discover({}, task_error=PermissionError(errno.EACCES, 'opaque'))

    def test_partial_or_malformed_snapshot_never_signals(self):
        for problem in (PermissionError(errno.EACCES, 'opaque'), OSError(errno.EIO, 'failed'), 'malformed'):
            with self.subTest(problem=repr(problem)), self.assertRaises((OSError, ValueError)):
                self.discover({101: '101 (child) S 100 0', 102: problem}, cleanup=True)

    def test_entry_and_time_limits_reject(self):
        with self.assertRaisesRegex(RuntimeError, '4096'):
            self.discover({pid: '%s (unrelated) S 999 0' % pid for pid in range(1000, 5097)})
        with self.assertRaisesRegex(RuntimeError, '1 second'):
            self.discover({101: '101 (child) S 100 0'}, clock=[0, 2])


if __name__ == '__main__':
    unittest.main()
