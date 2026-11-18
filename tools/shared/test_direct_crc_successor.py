#!/usr/bin/env python3
"""Exact bulk-CRC supervision successor; all other direct commands unchanged."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import types

HERE = Path(__file__).resolve().parent
ORIGINALS = {'test_direct.py': 'a46bd66949e81c5761dff3446201640837ec8f68',
             'test_crc32.py': 'f906dde582c2aef13d56ec608accedec7f746dae'}
WORK = 1800
CLEANUP = 10
MARGIN = 15


def pinned_inputs(raws=None):
    result = {}
    for name in (*ORIGINALS, Path(__file__).name, 'crc_process_supervisor.py'):
        raw = (HERE / name).read_bytes() if raws is None else raws[name]
        if name in ORIGINALS:
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if blob != ORIGINALS[name]:
                raise RuntimeError('frozen CRC successor original changed: ' + name)
        result[name] = hashlib.sha256(raw).hexdigest()
    return result


def load_original():
    names = (*ORIGINALS, Path(__file__).name, 'crc_process_supervisor.py')
    raws = {name: (HERE / name).read_bytes() for name in names}
    pins = pinned_inputs(raws)
    original = types.ModuleType('crc_original_direct')
    original.__file__ = str(HERE / 'test_direct.py')
    exec(compile(raws['test_direct.py'], original.__file__, 'exec'), original.__dict__)
    return pins, original


def require_pidfd():
    if sys.platform != 'linux' or not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise RuntimeError('Linux pidfd support required before supervisor spawn')
    fd = os.pidfd_open(os.getpid())
    os.close(fd)


def main():
    pins, original = load_original()
    base = original.CommandRunner

    class Successor(base):
        def run(self, name, command, *, overrides=None, status=0, expected=None, timeout=180):
            if name != 'bulk-crc':
                return super().run(name, command, overrides=overrides, status=status,
                                   expected=expected, timeout=timeout)
            argv = list(map(str, command))
            # Exact parser shape is nine tokens: executable, -B, script and
            # three option/value pairs. Never intercept arbitrary commands.
            valid = (len(argv) == 9 and argv[:4] == [sys.executable, '-B', str(HERE / 'test_crc32.py'), '--build-receipt'] and
                     argv[5] == '--clang' and argv[7:] == ['--output', str(self.output / 'bulk-crc')])
            if not valid or timeout != 600 or overrides or status != 0 or expected is not None or self.root != original.ROOT:
                raise RuntimeError('unexpected bulk CRC successor invocation')
            producer = self.receipt.get('producer', {})
            if (argv[4] != producer.get('path') or not producer.get('sha256') or
                    self.receipt.get('inputs', {}).get(argv[4]) != producer['sha256']):
                raise RuntimeError('bulk CRC producer receipt is not the authenticated instance')
            if original.sha(Path(argv[4])) != producer['sha256']:
                raise RuntimeError('authenticated producer receipt changed')
            require_pidfd()
            if pinned_inputs() != pins:
                raise RuntimeError('successor inputs changed')
            guard = self.output / 'bulk-crc-supervisor.json'
            actual = [sys.executable, '-B', str(HERE / 'crc_process_supervisor.py'),
                      '--receipt', str(guard), '--work-seconds', str(WORK),
                      '--cleanup-seconds', str(CLEANUP), *argv]
            entry = dict(name=name, argv=argv, execution_argv=actual, cwd=str(self.root),
                         started=time.time(), state='running', original_timeout_seconds=600,
                         timeout_seconds=WORK + CLEANUP + MARGIN, work_seconds=WORK,
                         cleanup_seconds=CLEANUP, input_pins=pins,
                         budget_basis='Finite 1800s policy informed by observed ~72s x 17 interpreter invocations + ~74s setup; not a sum-of-maxima bound or performance root-cause fix',
                         scope='original CRC cases and inner limits unchanged; Linux subreaper successor')
            self.receipt['commands'].append(entry)
            self.save()
            process = None
            fd = None
            stdout = stderr = b''
            started = time.monotonic()
            old_handlers = {}
            def cancelled(signum, frame):
                raise KeyboardInterrupt('CRC successor cancelled by signal ' + str(signum))
            try:
                for sig in (signal.SIGTERM, signal.SIGINT):
                    old_handlers[sig] = signal.signal(sig, cancelled)
                mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
                try:
                    process = subprocess.Popen(actual, cwd=self.root, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, start_new_session=True)
                    fd = os.pidfd_open(process.pid)
                finally:
                    signal.pthread_sigmask(signal.SIG_SETMASK, mask)
                stdout, stderr = process.communicate(timeout=WORK + CLEANUP + MARGIN)
                entry['exit_code'] = process.returncode
                supervisor = json.loads(guard.read_text())
                entry['supervisor'] = supervisor
                if process.returncode != 0 or not supervisor.get('complete') or stderr:
                    raise RuntimeError('bulk-crc failed; see supervisor receipt and bulk-crc.stderr')
                if pinned_inputs() != pins:
                    raise RuntimeError('successor inputs changed')
                entry['state'] = 'passed'
                return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
            except BaseException as error:
                entry.update(state='failed', error=repr(error))
                if process is not None and process.returncode is None:
                    # No original stop_group call: its 2s escalation would kill
                    # the supervisor during its separate 10s cleanup allowance.
                    previous = {}
                    try:
                        for sig in (signal.SIGTERM, signal.SIGINT):
                            previous[sig] = signal.signal(sig, lambda *_: None)
                        if fd is None:
                            fd = os.pidfd_open(process.pid)
                        try:
                            signal.pidfd_send_signal(fd, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        try:
                            stdout, stderr = process.communicate(timeout=CLEANUP + MARGIN)
                        except subprocess.TimeoutExpired as capture:
                            try:
                                signal.pidfd_send_signal(fd, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            entry['cleanup_unverified'] = 'supervisor grace expired; SIGKILL cannot contain descendants'
                            try:
                                stdout, stderr = process.communicate(timeout=2)
                            except subprocess.TimeoutExpired:
                                stdout, stderr = capture.stdout or b'', capture.stderr or b''
                                process.stdout.close(); process.stderr.close()
                                try:
                                    process.wait(timeout=2)
                                except subprocess.TimeoutExpired:
                                    entry['leader_reap_unverified'] = True
                    finally:
                        for sig, handler in previous.items():
                            signal.signal(sig, handler)
                raise
            finally:
                try:
                    if process is not None:
                        entry['exit_code'] = process.returncode
                    try:
                        if guard.is_file():
                            entry['supervisor'] = json.loads(guard.read_text())
                        for suffix, data in [('stdout', stdout), ('stderr', stderr)]:
                            path = self.output / (name + '.' + suffix)
                            path.write_bytes(data)
                            entry[suffix + '_sha256'] = original.sha(path)
                    except BaseException as evidence_error:
                        entry.update(state='failed', evidence_error=repr(evidence_error))
                        raise
                    finally:
                        entry['seconds'] = time.monotonic() - started
                        self.save()
                finally:
                    try:
                        if fd is not None:
                            os.close(fd)
                    finally:
                        for sig, handler in old_handlers.items():
                            signal.signal(sig, handler)

    original.CommandRunner = Successor
    original.main()


if __name__ == '__main__':
    main()
