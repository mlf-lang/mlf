"""Practical POSIX build/subprocess utilities for fresh opt-in IR8 source runs.

The caller chooses trusted GHC/CC executables. This is ordinary resource-bounded
process handling and retained diagnostics, not a hostile toolchain sandbox.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import time

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
SUITE_DEADLINE = None
SCOPE = 'fresh local source build and execution; no cached source admission'

MIB = 1024 * 1024


PACKAGES = ('base', 'array', 'bytestring', 'text', 'containers', 'directory')


SOURCE_ROOTS = ('tools/experimental/resource-native/source_v8',
                'libraries/mlf-async', 'libraries/mlf-crates',
                'libraries/mlf-developer-tools', 'libraries/mlf-foundation',
                'libraries/mlf-frontend', 'libraries/mlf-inference',
                'libraries/mlf-interpreter', 'libraries/mlf-language-core',
                'libraries/mlf-llvm', 'libraries/mlf-package-core',
                'libraries/mlf-xmlf', 'bootstrap', 'package', 'tests',
                'tests/shared', 'testing', 'host/ghc')


RUNTIME_SOURCES = ('rir8_binding.c', 'rir8_guard.c', 'rir8_memory.c',
                   'rir8_runtime.c', 'rir8_force.c', 'rir8_session.c')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def executable(value):
    found = shutil.which(value)
    require(found is not None, 'executable not found: ' + value)
    # Preserve a supplied official installation wrapper's original path.
    return os.path.abspath(found)


def run(argv, directory, stem, *, cwd, env, wall, cpu, memory, stdin=None,
        stdout_limit=16*MIB, stderr_limit=16*MIB, expected=0, file_limit=None, termination_grace=0):
    """Ordinary bounded subprocess with retained streams, no automatic retry."""
    directory = Path(directory)
    if SUITE_DEADLINE is not None:
        wall = min(wall, SUITE_DEADLINE - time.monotonic())
        require(wall > 0, 'run deadline exceeded before ' + stem)
    save(directory / (stem + '.argv.json'), argv)
    started = time.monotonic()
    result = {'argv': argv, 'cwd': str(cwd), 'scope': SCOPE,
              'cleanup_errors': [], 'cleanup_escalated': False,
              'termination_grace_seconds': termination_grace,
              'limits': {'wall_seconds': wall, 'cpu_seconds': cpu,
                         'address_space_bytes': memory,
                         'stdout_bytes': stdout_limit, 'stderr_bytes': stderr_limit,
                         'file_bytes': max(stdout_limit, stderr_limit) if file_limit is None else file_limit}}

    def limits():
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        ceiling = max(stdout_limit, stderr_limit) if file_limit is None else file_limit
        resource.setrlimit(resource.RLIMIT_FSIZE, (ceiling, ceiling))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    out_path, err_path = directory / (stem + '.stdout'), directory / (stem + '.stderr')
    process = None
    primary_error = None
    try:
        with out_path.open('xb') as out, err_path.open('xb') as err:
            process = subprocess.Popen(argv, cwd=cwd, env=env,
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=out, stderr=err, start_new_session=True, preexec_fn=limits)
            result['pid'] = process.pid
            process.communicate(input=stdin, timeout=wall)
            result['returncode'] = process.returncode
        result['stdout_bytes'] = out_path.stat().st_size
        result['stderr_bytes'] = err_path.stat().st_size
        require(result['stdout_bytes'] <= stdout_limit, stem + ': stdout cap exceeded')
        require(result['stderr_bytes'] <= stderr_limit, stem + ': stderr cap exceeded')
        require(process.returncode in ((expected,) if type(expected) is int else expected),
                '%s: rc %s, expected %s; see %s' % (stem, process.returncode, expected, err_path))
    except BaseException as exc:
        primary_error = exc
        result['error'] = '%s: %s' % (type(exc).__name__, exc)
        result['timeout'] = isinstance(exc, subprocess.TimeoutExpired)
    finally:
        # Never retry the command, and never let cleanup replace its primary failure.
        if process is not None and process.poll() is None:
            # A CLI can own children in separate sessions. Give its SIGTERM
            # handler time to kill/reap those children before outer escalation.
            if termination_grace:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except BaseException as exc:
                    result['cleanup_errors'].append('terminate: ' + repr(exc))
                try:
                    process.wait(timeout=termination_grace)
                except subprocess.TimeoutExpired:
                    result['cleanup_escalated'] = True
                    result['cleanup_errors'].append('termination grace expired; nested child cleanup uncertain')
                except BaseException as exc:
                    result['cleanup_errors'].append('grace reap: ' + repr(exc))
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except BaseException as exc:
                    result['cleanup_errors'].append('kill: ' + repr(exc))
                try:
                    process.wait(timeout=5)
                except BaseException as exc:
                    result['cleanup_errors'].append('reap: ' + repr(exc))
        if process is not None:
            result['returncode'] = process.returncode
            if process.stdin is not None and not process.stdin.closed:
                try:
                    process.stdin.close()
                except BaseException as exc:
                    result['cleanup_errors'].append('stdin close: ' + repr(exc))
        result['elapsed_seconds'] = time.monotonic() - started
        try:
            save(directory / (stem + '.result.json'), result)
        except BaseException as exc:
            result['cleanup_errors'].append('result persistence: ' + repr(exc))
            if primary_error is None:
                primary_error = exc
    if primary_error is not None:
        if result['cleanup_errors']:
            primary_error.add_note('Additional cleanup/persistence failures: ' + repr(result['cleanup_errors']))
        raise primary_error
    require(not result['cleanup_errors'], 'child cleanup failed: ' + repr(result['cleanup_errors']))
    return out_path, err_path


def build_producer(ghc, cc, output, env):
    build = output / 'producer-build'
    build.mkdir()
    objects = build / 'objects'
    objects.mkdir()
    # Limit only the short version probe's RTS virtual reservation, not RSS.
    # GHC's default 1TiB reservation can crowd thread startup under RLIMIT_AS.
    version, err = run([ghc, '--numeric-version', '+RTS', '-xr32m', '-RTS'],
                      build, 'version', cwd=REPO,
                      env=env, wall=10, cpu=10, memory=1 << 30)
    require(version.read_text().strip() == '9.14.1', 'GHC 9.14.1 is required')
    require(not err.read_bytes(), 'unexpected GHC version diagnostic')
    for name, source in (('host', REPO / 'host/ghc/cbits/host.c'),
                         ('supervisor', REPO / 'runtime/mlf_process_supervisor.c')):
        run([cc, '-O0', '-std=c11', '-I' + str(REPO / 'runtime'), '-c',
             str(source), '-o', str(objects / (name + '.o'))], build, name,
            cwd=REPO, env=env, wall=60, cpu=30, memory=1 << 30)
    binary = build / 'shared-source-capture'
    argv = [ghc, '--make', '-j1', '-fforce-recomp', '-XHaskell2010', '-O0',
            '-fpedantic-bottoms', '-fno-state-hack', '-Werror=incomplete-patterns',
            '-Werror=incomplete-uni-patterns', '-Wno-star-is-type',
            '-Wno-overlapping-patterns', '-Wno-deprecations', '-package-env', '-',
            '-clear-package-db', '-global-package-db', '-no-user-package-db',
            '-hide-all-packages', '-i']
    argv += ['-i' + str(REPO / root) for root in SOURCE_ROOTS]
    for package in PACKAGES:
        argv += ['-package', package]
    argv += ['-odir', str(objects), '-hidir', str(objects), '-rtsopts=ignoreAll',
             str(BASE / 'source_v8/Main.hs'), str(objects / 'host.o'),
             str(objects / 'supervisor.o'), '-o', str(binary)]
    run(argv, build, 'ghc', cwd=REPO, env=env, wall=600, cpu=480, memory=8 << 30)
    return binary
