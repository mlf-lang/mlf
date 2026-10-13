"""Measured POSIX subprocesses shared by the native driver and benchmarks."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent


def run_group(commands, *, cwd=ROOT, env=None, timeout=600):
    """Start independent commands together, measuring each owned child.

    Each entry is (argv, stdin_bytes, optional_stdout_path). Files avoid pipe
    deadlocks. A waiter owns one exact PID; it never reaps an unrelated child.
    Failure or timeout kills every unfinished process group before returning.
    """
    if not commands:
        raise ValueError("An empty command group cannot be measured")
    children = []

    def expired(_signum, _frame):
        raise TimeoutError(f"Command group exceeded {timeout}s")

    def wait(item):
        child, started, argv, output_file, out, err = item
        _, status, usage = os.wait4(child.pid, 0)
        elapsed = time.perf_counter() - started
        child.returncode = os.waitstatus_to_exitcode(status)
        err.seek(0)
        errors = err.read().decode(errors="replace")
        if child.returncode:
            raise RuntimeError(f"Command exited {child.returncode}: {shlex.join(argv)}\n{errors}")
        out.seek(0)
        sample = {"command": argv, "cwd": str(cwd), "wall_seconds": elapsed,
                  "user_seconds": usage.ru_utime, "system_seconds": usage.ru_stime,
                  "cpu_seconds": usage.ru_utime + usage.ru_stime,
                  "peak_rss_bytes": int(usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024)),
                  "stderr": errors}
        if output_file is not None:
            sample["stdout_file"] = str(output_file)
        return sample, b"" if output_file is not None else out.read()

    previous = signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, timeout)
        with ExitStack() as files, ThreadPoolExecutor(max_workers=len(commands)) as pool:
            futures = []
            try:
                for argv, data, output_file in commands:
                    argv = list(map(str, argv))
                    inp = files.enter_context(tempfile.TemporaryFile())
                    err = files.enter_context(tempfile.TemporaryFile())
                    out = files.enter_context(open(output_file, "w+b") if output_file is not None
                                              else tempfile.TemporaryFile())
                    inp.write(data)
                    inp.seek(0)
                    started = time.perf_counter()
                    child = subprocess.Popen(argv, stdin=inp, stdout=out, stderr=err,
                                             cwd=cwd, env=env, start_new_session=True)
                    item = (child, started, argv, output_file, out, err)
                    children.append(item)
                    futures.append(pool.submit(wait, item))
                # Inspect completed futures promptly, including a failure in a
                # later command while the earlier command is still running.
                from concurrent.futures import as_completed
                for future in as_completed(futures):
                    future.result()
                return [future.result() for future in futures]
            finally:
                for child, *_ in children:
                    if child.returncode is None:
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                # Every submitted waiter reaps its exact child before file
                # handles close. Disable the alarm while cleaning up a failure.
                signal.setitimer(signal.ITIMER_REAL, 0)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        # The pool has joined every submitted waiter. Reap any child whose
        # waiter could not be submitted (including interruption at submission).
        for child, *_ in children:
            if child.returncode is None:
                _, status, _ = os.wait4(child.pid, 0)
                child.returncode = os.waitstatus_to_exitcode(status)
        signal.signal(signal.SIGALRM, previous)


def run(command, *, data=b"", cwd=ROOT, env=None, timeout=600, output_file=None):
    return run_group([(command, data, output_file)], cwd=cwd, env=env, timeout=timeout)[0]
