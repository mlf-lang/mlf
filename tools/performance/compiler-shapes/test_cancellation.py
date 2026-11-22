#!/usr/bin/env python3
"""Real recorder cancellation with a bounded watchdog and disposable worker group."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import command_runner

H = command_runner.load_helper()


LIMITS = {
    'address_space_per_process_bytes': 2 * 1024**3,
    'process_tree_rss_bytes': 512 * 1024**2,
    'host_available_floor_bytes': 1,
    'disk_free_floor_bytes': 1,
    'max_work_bytes': 1024**2,
    'wall_seconds': 20,
}


def wait_for(check, description):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError('timed out waiting for ' + description)


def worker(root):
    (root / 'group').write_text(str(os.getpid()))
    child = subprocess.Popen([sys.executable, '-B', __file__, 'stop', str(root)])
    os.waitpid(child.pid, os.WUNTRACED)
    (root / 'ready').touch()
    child.wait()


def record(root, signum, mode):
    signal.signal(signum, signal.default_int_handler if signum == signal.SIGINT else signal.SIG_DFL)
    runner = H.Runner(root, LIMITS)
    if mode == 'startup':
        original = subprocess.Popen

        def start(*args, **kwargs):
            process = original(*args, **kwargs)
            if kwargs.get('start_new_session'):
                wait_for((root / 'ready').exists, 'stopped grandchild at launch')
                os.kill(os.getpid(), signum)
            return process
        subprocess.Popen = start
    elif mode == 'start-waiter':
        original_start = threading.Thread.start

        def start_waiter(thread):
            wait_for((root / 'ready').exists, 'stopped grandchild at wait-thread startup')
            os.kill(os.getpid(), signum)
            return original_start(thread)
        threading.Thread.start = start_waiter
    argv = [sys.executable, '-B', __file__, 'worker', root]
    if mode == 'threaded':
        with command_runner.cancellation_scope(), ThreadPoolExecutor(1) as pool:
            pool.submit(runner.run, argv, root, root / 'run').result(timeout=10)
    else:
        runner.run(argv, root, root / 'run')


def launcher_argv(root, mode, signum):
    # Run the public CLI as a separate process. Each stage script substitutes
    # the stopped-worker fixture for compiler setup and uses the real Runner.
    command = 'all' if mode == 'all-ready' else mode
    here = Path(__file__).resolve().parent
    stages = root / 'tools/performance/compiler-shapes'
    stages.mkdir(parents=True)
    shutil.copy(here / 'bench.py', stages)
    for name in ('matrix.json', 'command_runner.py', 'fit_growth.py'):
        (stages / name).symlink_to(here / name)
    fixture = ('from pathlib import Path\nimport sys, signal, os\n'
               f'sys.path.insert(0, {str(here)!r})\nfrom test_cancellation import record\n'
               f'root = Path({str(root)!r})\n'
               '(root / "stage").write_text(Path(__file__).name)\n'
               '(root / "recorder").write_text(str(os.getpid()))\n'
               f'record(root, {int(signum)}, "normal")\n')
    for name in ('prepare.py', 'run.py'):
        (stages / name).write_text(fixture)
    work = root / 'work'
    arguments = [sys.executable, '-B', stages / 'bench.py', command, '--workdir', work]
    if command in ('all', 'run'):
        arguments += ['--cohort', 'fixture']
    if command in ('all', 'prepare'):
        arguments += ['--producer', root / 'unused', '--build-builtin']
    if mode in ('run', 'all-ready'):
        setup = work / 'setup/setup.json'
        setup.parent.mkdir(parents=True)
        setup.write_text('{}')
    return arguments



class RecorderCancellation(unittest.TestCase):
    def check_signal(self, signum, mode='normal'):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryFile() as errors:
            root = Path(directory)
            if mode in ('run', 'prepare', 'all', 'all-ready'):
                argv = launcher_argv(root, mode, signum)
            else:
                argv = [sys.executable, '-B', __file__, 'record', root, str(int(signum)), mode]
            recorder = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=errors)
            try:
                wait_for((root / 'ready').exists, 'stopped grandchild')
                group = int((root / 'group').read_text())
                if mode not in ('startup', 'start-waiter'):
                    self.assertTrue(any(row['state'].startswith('T') for row in H.process_group(group)))
                    recorder.send_signal(signum)
                status = recorder.wait(timeout=5)
                errors.seek(0)
                self.assertEqual(status, -signum, errors.read().decode())
                wait_for(lambda: not any(not row['state'].startswith('Z')
                                        for row in H.process_group(group)), 'empty worker group')
                receipt = json.loads((root / 'run/command.json').read_text())
                self.assertEqual(receipt.get('exit_code'), -signal.SIGKILL)
                self.assertFalse(receipt['complete'])
                if (root / 'recorder').exists():
                    stage_pid = int((root / 'recorder').read_text())
                    with self.assertRaises(ProcessLookupError):
                        os.kill(stage_pid, 0)
                    self.assertEqual((root / 'stage').read_text(), 'run.py' if mode in ('run', 'all-ready') else 'prepare.py')
            finally:
                if recorder.poll() is None:
                    recorder.kill()
                    recorder.wait(timeout=5)
                if (root / 'group').exists():
                    H.kill_group(int((root / 'group').read_text()))

    def test_public_launcher_cancels_its_recorder(self):
        for command in ('run', 'prepare', 'all', 'all-ready'):
            with self.subTest(command=command):
                self.check_signal(signal.SIGINT if command == 'all-ready' else signal.SIGTERM, command)

    def test_sigterm_stopped_descendant(self):
        self.check_signal(signal.SIGTERM)

    def test_sighup_stopped_descendant(self):
        self.check_signal(signal.SIGHUP)

    def test_signal_after_spawn_before_popen_returns(self):
        self.check_signal(signal.SIGTERM, 'startup')

    def test_ctrl_c_before_popen_returns(self):
        self.check_signal(signal.SIGINT, 'startup')

    def test_ctrl_c_before_wait_thread_starts(self):
        self.check_signal(signal.SIGINT, 'start-waiter')

    def test_main_scope_cancels_threaded_runner(self):
        self.check_signal(signal.SIGTERM, 'threaded')

    def test_custom_and_ignored_handlers_with_nested_scopes(self):
        calls = []

        def custom(signum, frame):
            calls.append(signum)
        original_term = signal.signal(signal.SIGTERM, custom)
        original_hup = signal.signal(signal.SIGHUP, signal.SIG_IGN)
        try:
            with tempfile.TemporaryDirectory() as directory, command_runner.cancellation_scope():
                root = Path(directory)
                # A handled disposition in the recorder resets on exec, while
                # an ignored one is inherited. TERM also exercises the callback.
                child = ('import os, signal; '
                         'assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL; '
                         'assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN; '
                         'os.kill(os.getppid(), signal.SIGTERM); raise SystemExit(3)')
                receipt = H.Runner(root, LIMITS).run([sys.executable, '-c', child],
                                                    root, root / 'run', expected_exit=3, timed=True)
                self.assertTrue(receipt['complete'] and receipt['timed_target_leg'])
                self.assertEqual(calls, [signal.SIGTERM])
            self.assertIs(signal.getsignal(signal.SIGTERM), custom)
            self.assertEqual(signal.getsignal(signal.SIGHUP), signal.SIG_IGN)
        finally:
            signal.signal(signal.SIGTERM, original_term)
            signal.signal(signal.SIGHUP, original_hup)

    def test_failed_command_restores_signal_dispositions(self):
        signals = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
        previous = [signal.getsignal(signum) for signum in signals]
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(RuntimeError, 'command failed'):
            root = Path(directory)
            H.Runner(root, LIMITS).run([sys.executable, '-c', 'raise SystemExit(1)'], root, root / 'run')
        self.assertEqual([signal.getsignal(signum) for signum in signals], previous)

    def test_worker_thread_without_a_main_thread_scope(self):
        with tempfile.TemporaryDirectory() as directory, ThreadPoolExecutor(1) as pool:
            root = Path(directory)
            job = pool.submit(H.Runner(root, LIMITS).run,
                              [sys.executable, '-c', 'pass'], root, root / 'run')
            self.assertTrue(job.result(timeout=5)['complete'])


if __name__ == '__main__':
    if sys.argv[1:2] == ['record']:
        record(Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    elif sys.argv[1:2] == ['worker']:
        worker(Path(sys.argv[2]))
    elif sys.argv[1:2] == ['stop']:
        os.kill(os.getpid(), signal.SIGSTOP)
    else:
        unittest.main()
