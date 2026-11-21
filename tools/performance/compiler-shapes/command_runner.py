"""Resource accounting and recorder cancellation for the serial shape commands."""
from contextlib import contextmanager
from pathlib import Path
import signal
import subprocess
import threading
import types


# None outside a main-thread scope. Keep the first signal received inside it.
_received = None
_waiting_recorders = set()


def _forward_to_recorders():
    # Remove each recorder before sending, including when a signal arrived
    # between Popen returning and the launcher registering the new process.
    while _waiting_recorders:
        _waiting_recorders.pop().send_signal(_received[0])


@contextmanager
def cancellation_scope():
    """Defer default termination until all commands in this scope have unwound.

    A threaded embedding can open this scope on its main thread and join the
    workers inside it. Only the main thread can install Python signal handlers.
    """
    global _received
    if _received is not None or threading.current_thread() is not threading.main_thread():
        yield
        return

    received = []
    installed = []

    def remember(signum, _frame):
        if not received:
            received.append(signum)
            _forward_to_recorders()

    _received = received
    try:
        for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            previous = signal.getsignal(signum)
            python_interrupt = signum == signal.SIGINT and previous is signal.default_int_handler
            if previous == signal.SIG_DFL or python_interrupt:
                signal.signal(signum, remember)
                installed.append((signum, previous))
        yield
    finally:
        for signum, previous in installed:
            if signal.getsignal(signum) is remember:
                signal.signal(signum, previous)
        _received = None
        if received:
            signal.raise_signal(received[0])


def run_recorder(argv, cwd):
    """Forward cancellation from bench.py and wait for the recorder to finish."""
    with cancellation_scope(), subprocess.Popen(argv, cwd=cwd) as process:
        _waiting_recorders.add(process)
        try:
            if _received:
                _forward_to_recorders()
            return process.wait()
        finally:
            _waiting_recorders.discard(process)


def load_helper():
    source = Path(__file__).resolve().parents[1] / 'a1-private-index/helper.py'
    helper = types.ModuleType('shape_resource_helper')
    helper.__file__ = str(source)
    exec(compile(source.read_bytes(), str(source), 'exec'), helper.__dict__)

    # This private instance polls group membership in the wait loop and once
    # again after wait4. Both points have a known PGID and an installed reaper,
    # including when the signal arrived during Popen or wait-thread startup.
    original_group = helper.process_group

    def checked_group(pgid):
        rows = original_group(pgid)
        if _received and any(not row['state'].startswith('Z') for row in rows):
            helper.kill_group(pgid, members=original_group)
        return rows

    class Runner(helper.Runner):
        def run(self, argv, cwd, output, expected_exit=0, timed=False):
            with cancellation_scope():
                return super().run(argv, cwd, output, expected_exit, timed)

    helper.process_group = checked_group
    helper.Runner = Runner
    return helper
