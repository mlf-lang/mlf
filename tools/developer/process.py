"""Run an ordinary foreground build step with inherited stdio."""
from contextlib import closing
import os
import select
import signal
import subprocess
import sys
import time


def wait_for_exit(pid, cancelled):
    """Observe exit without reaping the leader, which reserves its process group ID."""
    if hasattr(os, 'waitid'):
        flags = os.WEXITED | os.WNOHANG | os.WNOWAIT
        while not cancelled and os.waitid(os.P_PID, pid, flags) is None:
            time.sleep(0.05)
    else:
        # Older macOS Pythons expose kqueue but not waitid.
        event = select.kevent(pid, filter=select.KQ_FILTER_PROC, flags=select.KQ_EV_ADD,
                              fflags=select.KQ_NOTE_EXIT)
        with closing(select.kqueue()) as queue:
            try:
                queue.control([event], 0, 0)
            except ProcessLookupError:
                return  # The child has already exited and remains waitable.
            while not cancelled and not queue.control(None, 1, 0.05):
                pass


def signal_group(pid, sig):
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        # Darwin reports EPERM when the only group members are zombies.
        if sys.platform != 'darwin':
            raise


def run_build(argv, cwd, *, cancellation_grace=0.5):
    """Return the child's exit status. The POSIX CLI owns the child's process group.

    Native package workers in other sessions have their own supervisors, which
    cancel them when the manager's control pipes close. On Windows, use the
    ordinary shared console and the native manager's existing worker jobs.
    """
    if os.name != 'posix':
        return subprocess.call(argv, cwd=cwd)

    cancelled = []
    previous = {}

    def remember(signum, frame):
        if not cancelled:
            cancelled.append(signum)

    try:
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            if signal.getsignal(sig) != signal.SIG_IGN:
                previous[sig] = signal.signal(sig, remember)
        # Record cancellation even if it arrives before Popen returns the pid.
        child = subprocess.Popen(argv, cwd=cwd, start_new_session=True)
        try:
            wait_for_exit(child.pid, cancelled)
        finally:
            try:
                if cancelled:
                    signal_group(child.pid, cancelled[0])
                    signal_group(child.pid, signal.SIGCONT)
                    time.sleep(cancellation_grace)
            finally:
                # A finished leader can still have stopped or signal-ignoring children.
                try:
                    signal_group(child.pid, signal.SIGKILL)
                finally:
                    child.wait()
        return -cancelled[0] if cancelled else child.returncode
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if cancelled:
            signal.raise_signal(cancelled[0])
