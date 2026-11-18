#!/usr/bin/env python3
"""Linux-only bounded subreaper. SIGKILL of this supervisor is NOT contained.

Only unreaped direct children are signalled, through pidfds. An empty proc
listing is not a completion proof: cleanup must reach waitpid ECHILD.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time
import errno
import traceback


def enable_subreaper():
    if sys.platform != 'linux' or not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise RuntimeError('Linux pidfd/subreaper support required')
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER')
    value = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(value), 0, 0, 0) != 0 or value.value != 1:
        raise RuntimeError('subreaper verification failed')
    fd = os.pidfd_open(os.getpid())
    os.close(fd)


def proc_identity(raw):
    prefix, rest = raw.rsplit(') ', 1)
    return int(prefix.split(' (', 1)[0]), int(rest.split()[1])


def children():
    children.last_discovery = {'mode': 'task-children'}
    pid = os.getpid()
    own_pid, _ = proc_identity(Path('/proc/self/stat').read_text())
    if own_pid != pid:
        raise RuntimeError('proc PID namespace does not match syscall namespace')
    try:
        raw = Path('/proc/self/task/%s/children' % pid).read_text()
    except OSError as error:
        if error.errno != errno.ENOENT:
            raise
    else:
        return [int(x) for x in raw.split()]
    # Explicit degraded discovery only when the task children interface is
    # absent. This bounded snapshot never establishes absence of descendants:
    # only waitpid ECHILD can complete cleanup. Any uncertainty other than a
    # positively identified vanished entry rejects the entire snapshot.
    deadline = time.monotonic() + 1
    result = []
    seen = skipped = 0
    with os.scandir('/proc') as entries:
        for entry in entries:
            if time.monotonic() >= deadline:
                raise RuntimeError('bounded proc discovery exceeded 1 second')
            seen += 1
            if seen > 4096:
                raise RuntimeError('bounded proc discovery exceeded 4096 entries')
            if not entry.name.isdigit():
                continue
            candidate = int(entry.name)
            try:
                stat_pid, parent = proc_identity(Path(entry.path, 'stat').read_text())
            except OSError as error:
                if error.errno not in (errno.ENOENT, errno.ESRCH):
                    raise
                skipped += 1
                continue
            if stat_pid != candidate:
                raise RuntimeError('proc stat PID does not match directory identity')
            if parent == pid:
                result.append(candidate)
    if time.monotonic() >= deadline:
        raise RuntimeError('bounded proc discovery exceeded 1 second')
    if proc_identity(Path('/proc/self/stat').read_text())[0] != pid:
        raise RuntimeError('proc PID namespace changed during discovery')
    children.last_discovery = dict(mode='bounded-proc-ppid-fallback', entries=seen,
                                   vanished_entries=skipped, snapshot_complete=True, absence_proven=False)
    return result


def signal_child(pid, sig):
    # This single-threaded owner never reaps during open/check/send. Thus an
    # owned child, even after exit, cannot have its PID reused in this interval.
    fd = os.pidfd_open(pid)
    try:
        stat_pid, parent = proc_identity(Path('/proc/%s/stat' % pid).read_text())
        if stat_pid != pid or parent != os.getpid():
            raise RuntimeError('refusing non-child identity')
        signal.pidfd_send_signal(fd, sig)
    finally:
        os.close(fd)


def cleanup(root, seconds, record):
    deadline = time.monotonic() + seconds
    sent = {}
    while True:
        # Reap only this supervisor's children. Reparenting follows parent exit,
        # including descendants which created another session or subreaper.
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                record['cleanup_complete'] = True
                record['survivors'] = []
                return
            if pid == 0:
                break
            record['reaped'].append({'pid': pid, 'status': os.waitstatus_to_exitcode(status)})
            if pid == root:
                record['target_exit_code'] = os.waitstatus_to_exitcode(status)
            sent.pop(pid, None)
        owned = children()
        discovery = getattr(children, 'last_discovery', None)
        record['last_discovery'] = discovery if type(discovery) is dict else {'mode': 'task-children'}
        if time.monotonic() >= deadline:
            record['cleanup_complete'] = False
            record['survivors'] = owned
            record['cleanup_error'] = 'deadline before ECHILD; descendants may remain'
            return
        for pid in owned:
            now = time.monotonic()
            sig = signal.SIGTERM if pid not in sent else signal.SIGKILL
            if pid in sent and now - sent[pid] < 0.2:
                continue
            try:
                signal_child(pid, sig)
                record['signals'].append({'pid': pid, 'signal': int(sig)})
                sent.setdefault(pid, now)
            except ProcessLookupError:
                pass  # It is still owned until the next waitpid reaps it.
        time.sleep(0.01)


def supervise(command, receipt, work_seconds, cleanup_seconds):
    record = dict(complete=False, phase='capability', command=command,
                  work_seconds=work_seconds, cleanup_seconds=cleanup_seconds,
                  cleanup_complete=False, reaped=[], signals=[],
                  scope='owned descendants via Linux subreaper and direct-child pidfds; supervisor SIGKILL not contained')
    def save():
        tmp = receipt.with_suffix('.tmp')
        tmp.write_text(json.dumps(record, indent=2) + '\n')
        tmp.replace(receipt)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    root = None
    cancelled = []
    previous = {}
    def interrupt(signum, frame):
        cancelled.append(signum)  # Never interrupt cleanup or spawn ownership.
    try:
        save()
        enable_subreaper()
        record['phase'] = 'initial-owned-children'
        save()
        if children():
            raise RuntimeError('supervisor must begin without children')
        discovery = getattr(children, 'last_discovery', None)
        record['initial_discovery'] = discovery if type(discovery) is dict else {'mode': 'task-children'}
        record['phase'] = 'install-handlers'
        save()
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, interrupt)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM, signal.SIGINT})
        record['phase'] = 'spawn'
        save()
        if cancelled:
            raise RuntimeError('cancelled before spawn')
        root = os.fork()
        if root == 0:
            try:
                for sig in previous:
                    signal.signal(sig, signal.SIG_DFL)
                os.setsid()
                os.execv(command[0], command)
            except BaseException:
                os._exit(127)
        record.update(root_pid=root, phase='work')
        save()
        deadline = time.monotonic() + work_seconds
        while True:
            if cancelled:
                record['reason'] = 'cancelled'
                break
            if time.monotonic() >= deadline:
                record['reason'] = 'work deadline'
                break
            exited = os.waitid(os.P_PID, root, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if exited is not None:
                record['reason'] = 'target exited'
                break
            time.sleep(0.02)
    except BaseException as error:
        record['error'] = repr(error)
        record.update(failed_phase=record['phase'], error_message=str(error),
                      errno=getattr(error, 'errno', None), filename=getattr(error, 'filename', None),
                      traceback=traceback.format_exc())
    finally:
        if root is not None and root != 0:
            record['phase'] = 'cleanup'
            save()
            try:
                cleanup(root, cleanup_seconds, record)
            except BaseException as error:
                record['cleanup_error'] = repr(error)
                record.update(cleanup_failed_phase=record['phase'], cleanup_error_message=str(error),
                              cleanup_errno=getattr(error, 'errno', None),
                              cleanup_filename=getattr(error, 'filename', None),
                              cleanup_traceback=traceback.format_exc())
        record['cancel_signals'] = cancelled
        record['complete'] = (record.get('reason') == 'target exited' and
                              record.get('target_exit_code') == 0 and
                              record['cleanup_complete'] and not cancelled and
                              not record.get('error') and not record['signals'])
        # A target which exits zero but leaves live children is a failure, even
        # when containment succeeds. Do not erase the cleanup's evidence.
        record['phase'] = 'terminal'
        save()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    if record['complete']:
        return 0
    status = record.get('target_exit_code', 1)
    return status if isinstance(status, int) and 0 < status < 126 else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--work-seconds', type=float, required=True)
    p.add_argument('--cleanup-seconds', type=float, default=10)
    p.add_argument('command', nargs=argparse.REMAINDER)
    a = p.parse_args()
    if not a.command or not 0 < a.work_seconds <= 1800 or not 0 < a.cleanup_seconds <= 10:
        p.error('command and bounded positive limits required')
    raise SystemExit(supervise(a.command, a.receipt, a.work_seconds, a.cleanup_seconds))


if __name__ == '__main__':
    main()


