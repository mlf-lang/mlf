"""Process-level checks for the developer build launcher."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from developer import process


SCRIPT = Path(__file__).resolve()


def args(role, root):
    return [sys.executable, '-B', SCRIPT, role, root]


def wait_for(path):
    deadline = time.monotonic() + 5
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError(str(path))
        time.sleep(0.01)


def fixture(role, root):
    if role == 'grandchild':
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(sig, signal.SIG_IGN)
        os.kill(os.getpid(), signal.SIGSTOP)
        time.sleep(60)
    elif role == 'leader':
        child = subprocess.Popen(args('grandchild', root))
        os.waitpid(child.pid, os.WUNTRACED)
        (root / 'ready').write_text(str(os.getpid()))
        time.sleep(60)
    elif role == 'startup':
        popen = subprocess.Popen

        def interrupt_before_return(*pargs, **kwargs):
            child = popen(*pargs, **kwargs)
            wait_for(root / 'ready')
            os.kill(os.getpid(), signal.SIGTERM)
            return child

        with mock.patch.object(subprocess, 'Popen', interrupt_before_return):
            return process.run_build(args('leader', root), root)
    else:
        return process.run_build(args('leader', root), root)


def check_tools_fixture(root, script):
    tools = root / 'tools'
    suite = tools / 'developer'
    suite.mkdir(parents=True)
    shutil.copyfile(SCRIPT.parents[1] / 'dev.py', tools / 'dev.py')
    shutil.copyfile(process.__file__, suite / 'process.py')
    (suite / 'test_commands.py').write_text(script)
    (suite / 'test_process.py').write_text('from pathlib import Path; Path("next").touch()')
    return [sys.executable, '-B', tools / 'dev.py', 'check-tools']


class BuildProcessTests(unittest.TestCase):
    def test_exit_status_and_working_directory(self):
        with tempfile.TemporaryDirectory() as cwd:
            status = process.run_build(
                [sys.executable, '-c', 'from pathlib import Path; Path("observed").touch(); raise SystemExit(23)'], cwd)
            self.assertEqual(status, 23)
            self.assertTrue((Path(cwd) / 'observed').exists())

    def test_failed_check_returns_shell_status_and_stops(self):
        cases = [('raise SystemExit(23)', 23)]
        if os.name == 'posix':
            cases.append(('import os, signal; os.kill(os.getpid(), signal.SIGTERM)', 143))
        for script, status in cases:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as cwd:
                root = Path(cwd)
                result = subprocess.run(check_tools_fixture(root, script), capture_output=True, timeout=5)
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertFalse((root / 'next').exists())

    @unittest.skipUnless(os.name == 'posix', 'POSIX process groups')
    def test_signalling_check_tools_cleans_up_the_active_suite(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(sig=sig), tempfile.TemporaryDirectory() as cwd:
                root = Path(cwd)
                script = ('import sys, os\nfrom pathlib import Path\n'
                          f'sys.path.insert(0, {str(SCRIPT.parent)!r})\n'
                          'from test_process import fixture\n'
                          'Path("suite-pid").write_text(str(os.getpid()))\n'
                          'fixture("driver", Path.cwd())\n')
                argv = check_tools_fixture(root, script)
                with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as cli:
                    try:
                        wait_for(root / 'ready')
                        cli.send_signal(sig)
                        # The nested worker is stopped, ignores TERM, and holds stdout.
                        # EOF proves the suite supervisor killed it after receiving the signal.
                        _, stderr = cli.communicate(timeout=7)
                        self.assertEqual(cli.returncode, 130 if sig == signal.SIGINT else -sig, stderr)
                        self.assertFalse((root / 'next').exists())
                    finally:
                        if cli.poll() is None:
                            cli.kill()
                        if not cli.stdout.closed:
                            if (root / 'ready').exists():
                                process.signal_group(int((root / 'ready').read_text()), signal.SIGKILL)
                            if (root / 'suite-pid').exists():
                                try:
                                    os.kill(int((root / 'suite-pid').read_text()), signal.SIGKILL)
                                except ProcessLookupError:
                                    pass

    @unittest.skipUnless(os.name == 'posix', 'POSIX process groups')
    def test_signal_reaps_build_and_stopped_descendant(self):
        for mode, sig in [('driver', signal.SIGTERM), ('startup', signal.SIGTERM),
                          ('driver', signal.SIGHUP), ('driver', signal.SIGINT)]:
            with self.subTest(mode=mode, sig=sig), tempfile.TemporaryDirectory() as cwd:
                root = Path(cwd)
                # Both descendants inherit stdout. EOF proves the stopped process
                # has exited, including when the build leader died on TERM.
                driver = subprocess.Popen(args(mode, root), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    wait_for(root / 'ready')
                    if mode == 'driver':
                        driver.send_signal(sig)
                    driver.communicate(timeout=6)
                    self.assertEqual(driver.returncode, -sig)
                finally:
                    if driver.poll() is None:
                        driver.kill()
                        driver.wait()
                    if driver.stdout and not driver.stdout.closed:
                        if (root / 'ready').exists():
                            try:
                                os.killpg(int((root / 'ready').read_text()), signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        driver.stdout.close()
                        driver.stderr.close()


if __name__ == '__main__':
    if len(sys.argv) == 3:
        sys.exit(fixture(sys.argv[1], Path(sys.argv[2])))
    unittest.main()
