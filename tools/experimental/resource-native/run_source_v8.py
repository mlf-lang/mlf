#!/usr/bin/env python3
"""Opt-in real .emlf source -> freshly checked capture -> IR8 -> native run.

Supply trusted GHC9.14.1 and C11 executables. No cached JSON, receipt or producer
binary is an input. The intermediate capture remains diagnostic; local custody
comes from this fresh build and invocation, not producer booleans. Old/default
routes are unchanged. POSIX only; output must be a new directory outside both
the input module tree and this checkout. Faults retain the diagnostic ledger by
default. --failure-policy destroy-terminal explicitly surrenders it afterward.
"""
import argparse
import json
import os
import signal
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
sys.path.insert(0, str(BASE))
import source_build_v8 as build
from source_capture_v8 import verify_capture
from source_snapshot_v8 import bounded_read, snapshot, verify_package, loaded_subset
from planner_v8 import plan_fragment
from resource_ir_v8.checker import check_resources
from resource_ir_v8.runtime_emit import emit_runtime
import transport

MAX_FUEL = 10_000_000


def fuel(value):
    if not value or any(c not in '0123456789' for c in value) or len(value) > 8:
        raise argparse.ArgumentTypeError('fuel must be decimal 1..10000000')
    number = int(value)
    if not 1 <= number <= MAX_FUEL:
        raise argparse.ArgumentTypeError('fuel must be decimal 1..10000000')
    return number


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path, help='headerless .emlf root inside --module-root')
    p.add_argument('--module-root', required=True, type=Path)
    p.add_argument('--ghc', required=True, help='trusted official GHC9.14.1 executable')
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'), help='trusted C11 compiler executable')
    p.add_argument('--output', required=True, type=Path, help='new external output directory')
    p.add_argument('--fuel', type=fuel, default=1_000_000)
    p.add_argument('--failure-policy', choices=('retain', 'destroy-terminal'), default='retain')
    return p


def fresh_output(path, module_root):
    path = Path(os.path.abspath(path))
    root = Path(os.path.abspath(module_root))
    build.require(root.resolve(strict=True) == root and root.is_dir(),
                  'module root must be canonical and must not traverse links')
    build.require(path.resolve() == path, 'output must not traverse links')
    build.require(path != root and root not in path.parents,
                  'output must be outside the module root')
    build.require(path != REPO and REPO not in path.parents,
                  'output must be outside this source checkout')
    path.mkdir(parents=True, exist_ok=False)
    return path


def environment(output):
    # Do not inherit compiler search paths, injected libraries or package settings.
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'SYSTEMROOT') if key in os.environ}
    tmp = output / 'tmp'
    tmp.mkdir()
    env.update(GHC_ENVIRONMENT='-', GHCRTS='', LC_ALL='C.UTF-8', LANG='C.UTF-8',
               TMPDIR=str(tmp), PYTHONDONTWRITEBYTECODE='1')
    return env


def native_compile(cc, emission, output, env):
    native = output / 'native'
    native.mkdir()
    for name, field in (('ir8_packet_generated.h', 'packet_header'),
                        ('ir8_packet_generated.c', 'packet_source'),
                        ('ir8_runtime_generated.h', 'runtime_header'),
                        ('ir8_runtime_generated.c', 'runtime_source')):
        with (native / name).open('x', encoding='utf-8') as stream:
            stream.write(getattr(emission, field))
    argv = [cc, '-std=c11', '-O0', '-g', '-Wall', '-Wextra', '-Werror', '-pedantic',
            '-I' + str(BASE / 'packet_v8'), '-I' + str(BASE / 'runtime_v8'), '-I' + str(native),
            str(BASE / 'packet_v8/ir8_packet.c')]
    argv += [str(BASE / 'runtime_v8' / name) for name in build.RUNTIME_SOURCES]
    argv += [str(native / 'ir8_packet_generated.c'), str(native / 'ir8_runtime_generated.c'),
             str(BASE / 'source_v8/native_driver.c'), '-o', str(native / 'program')]
    build.run(argv, native, 'compile', cwd=REPO, env=env, wall=60, cpu=30, memory=1 << 30)
    return native


def load_json(path, limit):
    return json.loads(bounded_read(path, limit).decode('utf-8'),
                      object_pairs_hook=transport.strict_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def execute(args, output):
    started = time.monotonic()
    build.SUITE_DEADLINE = started + 900
    package = None
    result = None
    primary = None
    cleanup_errors = []
    try:
        # Snapshot before any build/invocation. Unimported .emlf bytes are bounded
        # and rechecked, but are not claimed to have passed source type checking.
        package, source = snapshot(args.source, args.module_root, output)
        build.save(output / 'package.json', package)
        env = environment(output)
        ghc, cc = build.executable(args.ghc), build.executable(args.cc)
        producer = build.build_producer(ghc, cc, output, env)
        capture, stderr = build.run([str(producer), '--capture-shared'], output, 'capture',
            cwd=package['snapshot_root'], env=env, stdin=source,
            wall=180, cpu=120, memory=4 << 30, stdout_limit=33 << 20, stderr_limit=1 << 20)
        build.require(not bounded_read(stderr, 1 << 20), 'producer wrote unexpected successful diagnostics')
        verify_package(package)
        selected = loaded_subset(capture, package, source)
        raw_bytes = bounded_read(capture, 32 << 20)
        verified = verify_capture(capture, fixture_root=package['snapshot_root'],
            entry=package['root_relative'], expected_source_hashes=selected,
            expected_capture_sha256=build.sha(raw_bytes))
        build.save(output / 'verification.json', verified)
        build.require(verified['fragment_admitted'],
                      'source outside supported shared fragment: ' + repr(verified.get('fragment_error')))
        capture_data = json.loads(raw_bytes.decode('utf-8'), object_pairs_hook=transport.strict_pairs)
        build.require(build.sha(bounded_read(capture, 32 << 20)) == build.sha(raw_bytes),
                      'fresh capture changed after replay')
        plan = plan_fragment(capture_data['projection']['projected_annotated'])
        checked = check_resources(plan['program'])
        build.save(output / 'planned.json', plan)
        build.save(output / 'resources.json', checked.report())
        emission = emit_runtime(plan['program'])
        native = native_compile(cc, emission, output, env)
        verify_package(package)
        stdout, stderr = build.run([str(native / 'program'), '--fuel', str(args.fuel),
                                   '--failure-policy', args.failure_policy], native, 'run',
            cwd=native, env=env, wall=30, cpu=20, memory=1 << 30,
            stdout_limit=32 << 20, stderr_limit=1 << 20, expected=(0, 2))
        build.require(not bounded_read(stderr, 1 << 20), 'native wrote unexpected diagnostics')
        report = load_json(stdout, 32 << 20)
        evaluation = report if args.failure_policy == 'retain' else report['evaluation']
        build.require(type(evaluation['fault']) is int and evaluation['fault'] >= 0,
                      'invalid native fault record')
        fault = evaluation['fault']
        process = load_json(native / 'run.result.json', 1 << 20)
        build.require(process['returncode'] == (2 if fault else 0), 'native exit and fault disagree')
        result = {'status': 'fault' if fault else 'complete', 'fuel': args.fuel,
                  'failure_policy': args.failure_policy, 'native': report,
                  'loaded_sources': verified['loaded_sources'],
                  'copied_source_files': len(package['files']),
                  'unimported_sources_are_not_claimed_type_checked': True,
                  'capture_format': 'mlf-shared-source-capture/1',
                  'capture_is_not_export3': True, 'fresh_producer_build': True,
                  'elapsed_seconds': time.monotonic() - started}
    except BaseException as exc:
        primary = exc
    finally:
        if package is not None:
            try:
                verify_package(package)
            except BaseException as exc:
                cleanup_errors.append('%s: %s' % (type(exc).__name__, exc))
    if primary is not None or cleanup_errors:
        failure = {'status': 'failed', 'error': None if primary is None else
                   '%s: %s' % (type(primary).__name__, primary),
                   'source_recheck_errors': cleanup_errors,
                   'elapsed_seconds': time.monotonic() - started}
        if primary is None:
            primary = ValueError('source recheck failed: ' + repr(cleanup_errors))
        elif cleanup_errors:
            primary.add_note('Source recheck failures: ' + repr(cleanup_errors))
        try:
            build.save(output / 'failure.json', failure)
        except BaseException as exc:
            primary.add_note('Failure record persistence also failed: ' + repr(exc))
        raise primary
    build.save(output / 'result.json', result)
    print(json.dumps({'status': result['status'], 'output': str(output),
                      'fault': result['native'].get('fault', result['native'].get('evaluation', {}).get('fault')),
                      'failure_policy': args.failure_policy}, sort_keys=True))
    return 2 if result['status'] == 'fault' else 0


def main(argv=None):
    args = parser().parse_args(argv)
    def interrupted(signum, _frame):
        raise KeyboardInterrupt('received signal %d' % signum)
    previous_term = signal.signal(signal.SIGTERM, interrupted)
    try:
        output = fresh_output(args.output, args.module_root)
        return execute(args, output)
    except (Exception, KeyboardInterrupt) as exc:
        print('%s: %s' % (type(exc).__name__, exc), file=sys.stderr)
        for note in getattr(exc, '__notes__', ()):
            print(note, file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous_term)


if __name__ == '__main__':
    raise SystemExit(main())
