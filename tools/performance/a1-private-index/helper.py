#!/usr/bin/env python3
"""Local Linux/macOS process and pin transport for the A1 experimental reproduction.

No compiler implementation, source transformation or relaxed producer validator.
"""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import threading
import time
import types


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, 'duplicate JSON key: ' + key)
            out[key] = value
        return out
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def env():
    result = {**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8',
              'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MAKEFLAGS': '-j1',
              'PYTHONDONTWRITEBYTECODE': '1'}
    for key in list(result):
        if key.startswith('MLF_DIAGNOSTIC_'):
            del result[key]
    return result


def regular(path):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), 'regular file required: ' + str(path))
    return path.resolve()


def below(root, relative, directory=False):
    root = Path(root).resolve()
    relative = Path(relative)
    require(not relative.is_absolute() and '..' not in relative.parts, 'unsafe relative path')
    path = root / relative
    require(not path.is_symlink(), 'fixture symlink forbidden: ' + str(path))
    resolved = path.resolve(strict=True)
    require(resolved.is_relative_to(root), 'fixture escaped root')
    require(resolved.is_dir() if directory else resolved.is_file(), 'missing fixture: ' + str(path))
    return resolved


def check_pins(pins):
    for path, digest in pins.items():
        require(sha(regular(path)) == digest, 'immutable input changed: ' + str(path))


def file_pins(root):
    return {str(regular(path)): sha(path) for path in sorted(Path(root).rglob('*')) if path.is_file()}


def module(path, name):
    path = regular(path)
    result = types.ModuleType(name)
    result.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), result.__dict__)
    return result


def authenticate(producer, source):
    producer, source = Path(producer).resolve(), Path(source).resolve()
    direct = module(source / 'tools/shared/test_direct.py', 'unaltered_direct_authentication')
    record = direct.authenticate_build(producer / 'receipt.json', producer / 'bin', root=source)
    require(record['optimization'] == '2' and '-O2' in record['flags'], 'ordinary O2 producer required')
    require(record['ghc']['version'] == '9.14.1', 'GHC 9.14.1 required')
    return record


def host():
    if sys.platform == 'darwin':
        return {'platform': platform.platform(), 'machine': platform.machine(),
                'node': platform.node(), 'affinity': 'not exposed by macOS',
                'cpu': subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], text=True).strip(),
                'logical_cpus': os.cpu_count(), 'python': sys.version, 'os_cache_flush': False,
                'qualification': 'macOS experimental; sampled RSS, no hard address-space limit'}
    require(sys.platform == 'linux', 'The unchanged official producer supports Linux only. '
            'On a Mac use a user-provided Linux VM/container with GHC 9.14.1, or stop and report '
            'that no supported environment is available. Native macOS qualification is NOT supplied.')
    return {'platform': platform.platform(), 'machine': platform.machine(),
            'node': platform.node(), 'affinity': sorted(os.sched_getaffinity(0)),
            'cpuinfo': Path('/proc/cpuinfo').read_text(),
            'meminfo': Path('/proc/meminfo').read_text(),
            'cgroup': Path('/proc/self/cgroup').read_text(),
            'python': sys.version, 'os_cache_flush': False}


def memory_available():
    if sys.platform == 'darwin':
        output = subprocess.check_output(['/usr/bin/vm_stat'], text=True)
        import re
        page = int(re.search(r'page size of (\d+) bytes', output).group(1))
        fields = {key: int(value) for key, value in re.findall(r'^Pages ([^:]+):\s*(\d+)\.', output, re.M)}
        require(all(key in fields for key in ('free', 'inactive', 'speculative')), 'vm_stat memory fields missing')
        # Approximation, not Linux MemAvailable: inactive includes reclaimable and anonymous pages.
        return page * sum(fields[key] for key in ('free', 'inactive', 'speculative'))
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('MemAvailable is unavailable')


def process_group(group):
    rows = []
    if sys.platform == 'darwin':
        output = subprocess.check_output(['/bin/ps', '-axo', 'pid=,ppid=,pgid=,sess=,state=,rss='], text=True)
        for line in output.splitlines():
            parts = line.split()
            require(len(parts) == 6, 'invalid ps process row')
            pid, ppid, pgid, session = map(int, parts[:4])
            if pgid == group or session == group:
                rows.append({'pid': pid, 'state': parts[4], 'rss': int(parts[5]) * 1024})
        return rows
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().split(') ', 1)[1].split()
            # stat fields: state=3, ppid=4, pgrp=5, session=6, rss=24.
            if int(fields[2]) == group or int(fields[3]) == group:
                rows.append({'pid': int(entry.name), 'state': fields[0],
                             'rss': int(fields[21]) * os.sysconf('SC_PAGE_SIZE')})
        except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError):
            continue
    return rows


def tree_bytes(root):
    total = 0
    for path in Path(root).rglob('*'):
        try:
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:
            pass
    return total


class SerialLock:
    def __init__(self, work):
        self.path = Path(work) / '.reproduction.lock'
    def __enter__(self):
        self.stream = self.path.open('a+')
        try:
            fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.stream.close()
            raise RuntimeError('another reproduction owns this work directory')
        return self
    def __exit__(self, *unused):
        fcntl.flock(self.stream, fcntl.LOCK_UN)
        self.stream.close()


class Runner:
    """Serial child launch with platform resource guards and exact-child wait4 usage.

    Compiler wall is measured immediately before Popen through wait4 completion;
    file copying, authentication, snapshots and semantic postchecks are excluded.
    The process-group guard is not a sandbox for deliberately escaped processes.
    """
    def __init__(self, work, limits):
        self.work, self.limits = Path(work), limits

    def run(self, argv, cwd, output, expected_exit=0, timed=False):
        output = Path(output)
        require(not output.exists(), 'fresh command output required: ' + str(output))
        output.mkdir(parents=True)
        argv = [str(value) for value in argv]
        limit = self.limits
        require(memory_available() >= limit['host_available_floor_bytes'], 'host memory floor before launch')
        require(__import__('shutil').disk_usage(self.work).free >= limit['disk_free_floor_bytes'], 'disk floor before launch')
        record = {'complete': False, 'argv': argv, 'cwd': str(Path(cwd).resolve()),
                  'timed_target_leg': timed, 'limits': limit, 'environment': {
                      key: env()[key] for key in ['GHC_ENVIRONMENT','GHCRTS','LC_ALL','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MAKEFLAGS']},
                  'boundary': 'Popen launch through exact-child wait4 completion; setup/copy/auth/postchecks excluded',
                  'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        receipt = output / 'command.json'
        if sys.platform == 'darwin':
            record['resource_qualification'] = {'address_space_limit': 'not enforced: user accepted sampled RSS protection',
                'process_group_rss': 'ps RSS sampled every 100 ms; short peaks may be missed',
                'host_available': 'vm_stat free + inactive + speculative estimate; not Linux MemAvailable'}
        save(receipt, record)
        done, waited, errors = threading.Event(), [], []
        def limits():
            maximum = limit['address_space_per_process_bytes']
            if sys.platform != 'darwin':
                resource.setrlimit(resource.RLIMIT_AS, (maximum, maximum))
        with (output / 'stdout').open('wb') as stdout, (output / 'stderr').open('wb') as stderr:
            begin = time.perf_counter_ns()
            process = subprocess.Popen(argv, cwd=cwd, env=env(), stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, start_new_session=True, preexec_fn=limits)
            def wait():
                try:
                    pid, status, usage = os.wait4(process.pid, 0)
                    waited.append((status, usage, time.perf_counter_ns()))
                except BaseException as error:
                    errors.append(error)
                finally:
                    done.set()
            thread = threading.Thread(target=wait, daemon=True)
            thread.start()
            reason, peak, next_disk = None, 0, time.monotonic()
            try:
                while not done.wait(0.1):
                    rows = process_group(process.pid)
                    peak = max(peak, sum(row['rss'] for row in rows))
                    if peak > limit['process_tree_rss_bytes']:
                        reason = 'process-tree RSS limit'
                    elif memory_available() < limit['host_available_floor_bytes']:
                        reason = 'host available-memory floor'
                    elif (time.perf_counter_ns() - begin) / 1e9 > limit['wall_seconds']:
                        reason = 'wall limit'
                    if time.monotonic() >= next_disk:
                        next_disk = time.monotonic() + 2
                        if __import__('shutil').disk_usage(self.work).free < limit['disk_free_floor_bytes']:
                            reason = 'disk free floor'
                        elif tree_bytes(self.work) > limit['max_work_bytes']:
                            reason = 'work-directory size limit'
                    if reason:
                        os.killpg(process.pid, signal.SIGKILL)
                        done.wait()
                        break
            except BaseException:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                done.wait()
                raise
            finally:
                thread.join()
                if waited:
                    status, usage, end = waited[0]
                    process.returncode = os.waitstatus_to_exitcode(status)
                    survivors = [row for row in process_group(process.pid) if not row['state'].startswith('Z')]
                    if survivors:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        reason = reason or 'live descendants after leader completion'
                    record.update(exit_code=process.returncode, reason=reason,
                                  wall_seconds=(end-begin)/1e9, child_user_seconds=usage.ru_utime,
                                  child_system_seconds=usage.ru_stime,
                                  max_individual_child_rss_bytes=usage.ru_maxrss if sys.platform == 'darwin' else usage.ru_maxrss*1024,
                                  sampled_process_tree_peak_rss_bytes=peak,
                                  voluntary_context_switches=usage.ru_nvcsw,
                                  involuntary_context_switches=usage.ru_nivcsw,
                                  terminal_live_descendants=survivors)
                record['complete'] = bool(waited and not errors and not reason and process.returncode == expected_exit)
                save(receipt, record)
        if errors:
            raise errors[0]
        record['logs'] = {str(output/name): sha(output/name) for name in ['stdout','stderr']}
        save(receipt, record)
        require(record['complete'], 'command failed/guarded: ' + str(receipt))
        return record
