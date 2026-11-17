#!/usr/bin/env python3
"""Single-threaded Linux qualification owner. Not a performance measurement.
Only this owner's descendants are controlled; SIGKILL of this owner is not
contained. A missing final ECHILD receipt is an incomplete qualification.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import stat
import sys
import time
import traceback
import types

PHASES = {'install': 900, 'build': 1200, 'pure': 120, 'utf8': 625}
SUPERVISOR_BLOB = '620e88b557139a6b19ca63097decaa9148bdd819'
AS_LIMIT = 6 * 1024**3
RSS_LIMIT = 5 * 1024**3
DISK_FLOOR = 4 * 1024**3
CAPTURE_LIMIT = 128 * 1024**2
GRACE = 30
CLEANUP = 10

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def sha_file(path):
    path = Path(path)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= 256 * 1024**2,
            'bounded regular identity input: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024**2), b''):
            digest.update(block)
    return {'path': str(path), 'resolved': str(path.resolve()),
            'bytes': info.st_size, 'sha256': digest.hexdigest()}

def persist(path, record):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    os.chmod(temporary, 0o644)
    temporary.replace(path)

def owned_resources(sup, directory):
    """Bounded ancestry snapshot, for accounting only, never signal selection."""
    deadline = time.monotonic() + 1
    own = os.getpid()
    require(sup.proc_identity(Path('/proc/self/stat').read_text())[0] == own,
            'proc/syscall namespace mismatch')
    rows = {}
    vanished = 0
    with os.scandir('/proc') as entries:
        for count, entry in enumerate(entries, 1):
            require(count <= 4096 and time.monotonic() < deadline,
                    'bounded resource snapshot exceeded')
            if not entry.name.isdigit():
                continue
            try:
                raw = Path(entry.path, 'stat').read_text()
            except OSError as error:
                if error.errno not in (errno.ENOENT, errno.ESRCH):
                    raise
                vanished += 1
                continue
            pid, parent = sup.proc_identity(raw)
            require(pid == int(entry.name), 'resource PID directory mismatch')
            fields = raw.rsplit(') ', 1)[1].split()
            rows[pid] = (parent, int(fields[21]) * os.sysconf('SC_PAGE_SIZE'))
    require(time.monotonic() < deadline and
            sup.proc_identity(Path('/proc/self/stat').read_text())[0] == own,
            'resource snapshot incomplete or namespace changed')
    owned = {own}
    for unused in range(len(rows) + 1):
        more = {pid for pid, (parent, rss) in rows.items() if parent in owned}
        if more <= owned:
            break
        owned |= more
    rss = sum(rows[pid][1] for pid in owned if pid in rows)
    disk = shutil.disk_usage(directory).free
    return {'owned_pids': sorted(owned), 'sampled_owned_rss_bytes': rss,
            'disk_free_bytes': disk, 'vanished_entries': vanished,
            'scope': 'bounded sampled ancestry, not a global or continuous memory guarantee'}

def successful_exit(record):
    """Validate this owner's actual waitpid ledger, not externally supplied proof.
    Only root install may naturally adopt extra zero-exit children. Nothing in
    this predicate selects PIDs to signal or replaces the pinned helper's
    ownership/ECHILD proof.
    """
    phase = record.get('phase')
    root = record.get('root_pid')
    uid = record.get('effective_uid')
    cleanup = record.get('cleanup')
    if (phase not in PHASES or type(root) is not int or root <= 0 or
            type(uid) is not int or uid < 0 or
            ((uid == 0) != (phase == 'install')) or
            record.get('ownership_admitted_after_ECHILD') is not True or
            record.get('initial_children') != [] or
            type(record.get('commands_started')) is not int or
            record['commands_started'] != 1 or
            record.get('reason') != 'root exited' or
            record.get('cancel_signals') != [] or
            record.get('root_notifications', []) != [] or
            'root_notification_race' in record or
            any(k == 'error' or k.endswith('_error') or k.endswith('_errors')
                for k in record) or type(cleanup) is not dict):
        return False
    if (cleanup.get('cleanup_complete') is not True or
            cleanup.get('survivors') != [] or cleanup.get('signals') != [] or
            type(cleanup.get('target_exit_code')) is not int or
            cleanup['target_exit_code'] != 0 or
            any(k == 'error' or k.endswith('_error') or k.endswith('_errors')
                for k in cleanup)):
        return False
    reaped = cleanup.get('reaped')
    if type(reaped) is not list or not reaped:
        return False
    seen = set()
    for row in reaped:
        if (type(row) is not dict or set(row) != {'pid', 'status'} or
                type(row['pid']) is not int or row['pid'] <= 0 or
                type(row['status']) is not int or row['status'] != 0 or
                row['pid'] in seen):
            return False
        seen.add(row['pid'])
    return root in seen and (phase == 'install' or len(reaped) == 1)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=PHASES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--supervisor', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    require(bool(command), 'one command required')
    require(not os.path.lexists(args.output), 'fresh output spelling required')
    directory = args.output.resolve()
    require(not os.path.lexists(directory), 'fresh evidence directory required')
    require(directory.parent.is_dir(), 'existing evidence parent directory required')
    directory.mkdir(mode=0o755, exist_ok=False)
    os.chmod(directory, 0o755)
    receipt = directory / 'receipt.json'
    start = time.monotonic()
    work = PHASES[args.phase]
    record = {'complete': False, 'phase': args.phase, 'state': 'preflight',
              'argv': command, 'cwd': os.getcwd(), 'work_seconds': work,
              'root_notification_grace_seconds': GRACE, 'cleanup_seconds': CLEANUP,
              'started_unix': time.time(), 'commands_started': 0,
              'effective_uid': os.geteuid(), 'effective_gid': os.getegid(),
              'capture_combined_limit_bytes': CAPTURE_LIMIT,
              'child_AS_limit_bytes': AS_LIMIT, 'sampled_owned_RSS_limit_bytes': RSS_LIMIT,
              'initial_disk_floor_bytes': DISK_FLOOR, 'performance_sample': False,
              'runtime': {'python': sys.version, 'platform': sys.platform},
              'checkout_commit_environment': os.environ.get('GITHUB_SHA'),
              'identity_scope': 'controller, pinned helper, invoking Python and resolved command executable; child qualification authenticates its full project inputs',
              'limitations': [
                  'RSS, capture-size and disk limits are sampled checks, not instantaneous hard caps; no full machine isolation or full toolchain closure.',
                  'Privileged install commands may change their own inherited limits.',
                  'SIGKILL/hard deadline cannot certify containment or ECHILD.',
                  'Only a terminal complete receipt is success.']}
    persist(receipt, record)
    cancelled = []
    previous = {}
    sup = None
    admitted = False
    root = None
    try:
        require(sys.platform == 'linux', 'Linux only')
        require((os.geteuid() == 0) == (args.phase == 'install'),
                'install owner must be root; other phases must be unprivileged')
        def on_cancel(number, frame):
            cancelled.append(number)  # Do not interrupt safe ownership/cleanup.
        def on_hard(number, frame):
            os.write(2, b'qualification hard deadline: cleanup NOT certified\n')
            os._exit(124)
        for number in (signal.SIGTERM, signal.SIGINT):
            previous[number] = signal.signal(number, on_cancel)
        previous[signal.SIGALRM] = signal.signal(signal.SIGALRM, on_hard)
        signal.setitimer(signal.ITIMER_REAL, work + GRACE + CLEANUP + 5)
        require(args.supervisor.stat().st_size <= 1024**2, 'bounded supervisor source')
        raw = args.supervisor.read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        require(blob == SUPERVISOR_BLOB, 'fixed supervisor source identity')
        sup = types.ModuleType('qualification_owned_supervisor')
        sup.__file__ = str(args.supervisor.resolve())
        exec(compile(raw, sup.__file__, 'exec'), sup.__dict__)
        executable = shutil.which(command[0])
        require(executable is not None, 'command executable unavailable')
        identities = [sha_file(Path(__file__).resolve()), sha_file(args.supervisor.resolve()),
                      sha_file(Path(sys.executable).resolve()), sha_file(Path(executable).resolve())]
        record['identity_inputs'] = identities
        record['supervisor_git_blob'] = blob
        record['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        sup.enable_subreaper()
        record['initial_children'] = sup.children()
        try:
            os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            no_children = False
        except ChildProcessError:
            no_children = True
        require(not record['initial_children'] and no_children, 'preexisting children; no generic cleanup authorized')
        admitted = True
        record['ownership_admitted_after_ECHILD'] = True
        snapshot = owned_resources(sup, directory)
        record['initial_resources'] = snapshot
        require(snapshot['disk_free_bytes'] >= DISK_FLOOR, 'initial disk floor')
        require(snapshot['sampled_owned_rss_bytes'] <= RSS_LIMIT, 'initial RSS floor')
        require(not cancelled, 'cancelled before spawn')
        record['state'] = 'spawning'
        persist(receipt, record)
        with (directory / 'stdout').open('xb') as stdout, (directory / 'stderr').open('xb') as stderr:
            os.fchmod(stdout.fileno(), 0o644)
            os.fchmod(stderr.fileno(), 0o644)
            root = os.fork()
            if root == 0:
                try:
                    for number in previous:
                        signal.signal(number, signal.SIG_DFL)
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    resource.setrlimit(resource.RLIMIT_AS, (AS_LIMIT, AS_LIMIT))
                    os.dup2(stdout.fileno(), 1)
                    os.dup2(stderr.fileno(), 2)
                    with open('/dev/null', 'rb') as stdin:
                        os.dup2(stdin.fileno(), 0)
                    os.execv(executable, command)
                except BaseException:
                    os._exit(127)
        record.update(root_pid=root, commands_started=1, state='work')
        persist(receipt, record)
        deadline = time.monotonic() + work
        trigger = None
        while True:
            # WNOWAIT preserves root ownership and prevents root PID reuse.
            exited = os.waitid(os.P_PID, root, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if exited is not None:
                record['reason'] = 'root exited'
                break
            if cancelled:
                trigger = 'cancelled'
            elif time.monotonic() >= deadline:
                trigger = 'work deadline'
            else:
                try:
                    snapshot = owned_resources(sup, directory)
                    record['last_resources'] = snapshot
                    record['peak_sampled_owned_rss_bytes'] = max(record.get('peak_sampled_owned_rss_bytes', 0), snapshot['sampled_owned_rss_bytes'])
                    require(snapshot['sampled_owned_rss_bytes'] <= RSS_LIMIT, 'owned RSS limit')
                    require(snapshot['disk_free_bytes'] >= DISK_FLOOR, 'disk floor during work')
                    require(sum((directory / name).stat().st_size for name in ('stdout', 'stderr')) <= CAPTURE_LIMIT, 'combined capture limit')
                except BaseException as error:
                    trigger = 'resource check failed'
                    record['resource_error'] = repr(error)
            if trigger is not None:
                record['reason'] = trigger
                break
            time.sleep(.1)
    except BaseException as error:
        record.update(error=repr(error), traceback=traceback.format_exc())
    finally:
        # Every abnormal path after spawn, including evidence/resource errors,
        # first gives the still-owned root its own bounded graceful shutdown.
        # Do not silently jump from an exception to the helper's short TERM/KILL.
        if admitted and root is not None and record.get('reason') != 'root exited':
            record['state'] = 'root notification grace'
            record['root_notifications'] = []
            try:
                try:
                    persist(receipt, record)
                except BaseException as error:
                    record['notification_evidence_error'] = repr(error)
                try:
                    sup.signal_child(root, signal.SIGTERM)
                    record['root_notifications'].append({'pid': root, 'signal': int(signal.SIGTERM)})
                except ProcessLookupError:
                    record['root_notification_race'] = 'root already exited, still unreaped'
                grace_deadline = time.monotonic() + GRACE
                while time.monotonic() < grace_deadline:
                    if os.waitid(os.P_PID, root, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
                        break
                    time.sleep(.1)
            except BaseException as error:
                record['root_notification_error'] = repr(error)
        record['state'] = 'cleanup'
        cleanup = {'cleanup_complete': False, 'reaped': [], 'signals': []}
        try:
            if admitted:
                sup.cleanup(root or 0, CLEANUP, cleanup)
            else:
                cleanup['reason'] = 'ownership not admitted; no reaping or signalling'
        except BaseException as error:
            cleanup.update(cleanup_complete=False, error=repr(error))
        record['cleanup'] = cleanup
        try:
            if admitted:
                final_resources = owned_resources(sup, directory)
                record['final_resources'] = final_resources
                require(final_resources['sampled_owned_rss_bytes'] <= RSS_LIMIT, 'final owned RSS limit')
                require(final_resources['disk_free_bytes'] >= DISK_FLOOR, 'final disk floor')
            capture_bytes = sum((directory / name).stat().st_size for name in ('stdout', 'stderr') if (directory / name).exists())
            record['capture_combined_bytes'] = capture_bytes
            require(capture_bytes <= CAPTURE_LIMIT, 'final combined capture limit')
            for name in ('stdout', 'stderr'):
                path = directory / name
                if path.exists():
                    record[name] = sha_file(path)
            if 'identity_inputs' in record:
                record['identity_inputs_after'] = [sha_file(row['path']) for row in record['identity_inputs']]
                require(record['identity_inputs_after'] == record['identity_inputs'], 'qualification controller/runtime identity changed')
            record['cancel_signals'] = cancelled
            record['elapsed_seconds'] = time.monotonic() - start
            record['complete'] = successful_exit(record)
        except BaseException as error:
            record.update(complete=False, finalization_error=repr(error))
        finally:
            record['state'] = 'terminal'
            record['elapsed_seconds'] = time.monotonic() - start
            try:
                persist(receipt, record)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                for number, handler in previous.items():
                    signal.signal(number, handler)
    return 0 if record['complete'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
