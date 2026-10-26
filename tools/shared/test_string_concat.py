#!/usr/bin/env python3
"""Opt-in GHC and native controls for string-list concatenation.

Uses a frozen balanced binary-concatenation reference and independent literal,
scalar, demand-order, and metadata oracles. Native controls run at O0/O2; stress
cases observe actual GC collections. This is finite semantic evidence, not a
benchmark or full compiler qualification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import shutil
import sys

from test_direct import CommandRunner, sha

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tools/shared/fixtures/concat'
REFERENCE_REVISION = '2957dd08321c38dbf94a75cb275a5f48e897f58e'
REFERENCE_SHA256 = '308a131b9dd34dba11d816d5c26d08c05147296332ab5ee05f13bec9d3d94cfd'
REFERENCE_BODY_SHA256 = 'b0a5d2a2b997e629a96290786fc5173d575921e0b35e8e219c362a55e392167d'
HOST_EXPECTED = (
    b'PASS concat-engines 3\n'
    b'PASS concat-metadata 8\n'
    b'PASS concat-interpreter-payload 3\n'
    b'PASS concat-literals 16\n'
    b'PASS concat-finite 1555\n'
    b'PASS concat-large 5\n'
    b'PASS concat-demand 13\n'
    b'String-list concatenation semantic audit passed\n'
)
NATIVE_CASES = [
    ('literals', b'concat literals passed\n', b''),
    ('stress', b'concat stress passed\n', b''),
    ('list-bottom', b'', b'Runtime: list-first\n'),
    ('head-before-tail', b'', b'Runtime: head-first\n'),
    ('tail-required', b'', b'Runtime: tail-required\n'),
    ('second-before-tail', b'', b'Runtime: second-first\n'),
    ('third-before-tail', b'', b'Runtime: third-first\n'),
    ('empty-before-second', b'', b'Runtime: second-first\n'),
    ('singleton-bottom', b'', b'Runtime: singleton-required\n'),
    ('empty-pair-tail', b'', b'Runtime: tail-required\n'),
    ('strict-string-left', b'', b'Runtime: string-left\n'),
    ('outer-head-before-suffix', b'', b'Runtime: head-first\n'),
    ('outer-tail-before-suffix', b'', b'Runtime: tail-first\n'),
    ('unused-result', b'1\n', b''),
    ('untaken-result', b'1\n', b''),
]
RUNTIME_SUCCESS = b'runtime concat: bytes, scalar indices, sharing, order, ABI, and GC passed\n'
RUNTIME_CASES = [
    ('success', RUNTIME_SUCCESS, b''), ('no-interior', RUNTIME_SUCCESS, b''),
    ('list-bottom', b'', b'Runtime: list-first\n'),
    ('head-before-tail', b'', b'Runtime: head-first\n'),
    ('later-head-before-tail', b'', b'Runtime: second-head\n'),
    ('tail-bottom', b'', b'Runtime: tail-second\n'),
    ('wrong-list', b'', b'Runtime: expected canonical string list\n'),
    ('improper-tail', b'', b'Runtime: expected canonical string list\n'),
    ('wrong-head', b'', b'Runtime: invalid value for runtime operation\n'),
    ('overflow-total', b'', b'Runtime: string too large\n'),
    ('overflow-wrap', b'', b'Runtime: string too large\n'),
    ('overflow-before-tail', b'', b'Runtime: string too large\n'),
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def tool(name):
    selected = shutil.which(str(name))
    require(selected is not None, 'missing executable: ' + str(name))
    return Path(selected).resolve(strict=True)


def local_c_closure(source):
    pending, seen = [source], set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        require(path.is_file(), 'missing runtime include: ' + str(path))
        seen.add(path)
        for include in re.findall(r'^\s*#\s*include\s*"([^"]+)"', path.read_text(), re.M):
            pending.append((path.parent / include).resolve())
    return sorted(seen)


def shared_haskell_closure(source):
    pending, seen = [source], set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        for module in re.findall(r'^\s*import\s+(?:qualified\s+)?(Bootstrap\.[A-Za-z0-9_.]+)',
                                 path.read_text(), re.M):
            matches = list(ROOT.glob('libraries/*/' + module.replace('.', '/') + '.hs'))
            require(len(matches) == 1, 'ambiguous/missing shared module: ' + module)
            pending.append(matches[0])
    return sorted(seen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['ghc', 'native', 'all'], default='all')
    parser.add_argument('--ghc', default='ghc')
    parser.add_argument('--compiler')
    parser.add_argument('--clang', default='clang')
    parser.add_argument('--gc-prefix', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    host_enabled, native_enabled = args.mode != 'native', args.mode != 'ghc'
    require(not native_enabled or (args.compiler and args.gc_prefix),
            'native/all mode requires --compiler and --gc-prefix')
    output = args.output.resolve()
    require(output != ROOT and not ROOT.is_relative_to(output), 'output cannot contain the checkout')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'status': 'running', 'mode': args.mode,
              'scope': 'finite-string-list-concatenation-controls',
              'performance_assertions': False, 'full_corpus_qualification': False,
              'compiler_source_provenance_authenticated': False,
              'native_toolchain_closure_complete': False,
              'native_provenance_scope': 'selected compiler/Clang, source/header closure, static BDWGC and GMP pkg-config flags; system libraries are not fully pinned',
              'reference_revision': REFERENCE_REVISION,
              'reference_body_sha256': REFERENCE_BODY_SHA256,
              'commands': [], 'inputs': {}, 'snapshot_inputs': {}, 'artifacts': {},
              'native_cases': [], 'interpreted_cases': [], 'direct_runtime_cases': [], 'shape_checks': []}

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        temporary.replace(output / 'receipt.json')

    def integrity():
        for path, digest in {**record['inputs'], **record['snapshot_inputs'], **record['artifacts']}.items():
            require(sha(path) == digest, 'source, tool, snapshot, or artifact changed: ' + path)

    def artifact(path):
        record['artifacts'][str(path)] = sha(path)

    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        clang = tool(args.clang)
        reference = FIXTURES / 'ConcatReference.hs'
        require(sha(reference) == REFERENCE_SHA256, 'frozen balanced reference changed')
        foundations = sorted((ROOT / 'libraries/mlf-foundation/Bootstrap').glob('*.hs'))
        metadata = ROOT / 'libraries/mlf-language-core/Bootstrap/Primitive.hs'
        source_paths = [*foundations, metadata, *sorted(FIXTURES.glob('*'))]
        inputs = [Path(__file__).resolve(), ROOT / 'tools/shared/test_direct.py',
                  Path(sys.executable).resolve(), clang]
        if host_enabled:
            ghc = tool(args.ghc)
            inputs.append(ghc)
            source_paths += [*sorted((ROOT / 'host/ghc/MLF').rglob('*.hs')),
                             ROOT / 'host/ghc/cbits/host.c', ROOT / 'runtime/mlf_process_supervisor.c',
                             *sorted((ROOT / 'runtime').glob('*.h'))]
            source_paths += shared_haskell_closure(ROOT / 'libraries/mlf-interpreter/Bootstrap/Runtime.hs')
        if native_enabled:
            compiler, pkg_config = tool(args.compiler), tool('pkg-config')
            gc = args.gc_prefix.resolve(strict=True)
            gc_archive = gc / 'lib/libgc.a'
            require(gc_archive.is_file(), 'BDWGC prefix must contain lib/libgc.a')
            inputs += [compiler, pkg_config, gc_archive, *sorted((gc / 'include').rglob('*.h'))]
            source_paths += local_c_closure((ROOT / 'runtime/mlf_runtime.c').resolve())
            source_paths.append(ROOT / 'tests/native/runtime_string_concat.c')
        source_paths = sorted(set(path.resolve() for path in source_paths if path.is_file()))
        record['inputs'] = {str(path): sha(path) for path in [*inputs, *source_paths]}
        snapshots = output / 'sources'
        for source in source_paths:
            target = snapshots / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        record['snapshot_inputs'] = {str(path): sha(path) for path in snapshots.rglob('*') if path.is_file()}
        fixture_dir = snapshots / 'tools/shared/fixtures/concat'
        foundation_dir = snapshots / 'libraries/mlf-foundation'
        metadata_dir = snapshots / 'libraries/mlf-language-core'
        shared_roots = sorted(set(snapshots / Path(*path.relative_to(ROOT).parts[:2])
                                  for path in source_paths if path.is_relative_to(ROOT / 'libraries')))
        runner.run('clang-version', [clang, '--version'], timeout=30)

        if host_enabled:
            version = runner.run('ghc-version', [ghc, '--numeric-version'], timeout=30)
            require(version.stdout == b'9.14.1\n', 'qualified GHC 9.14.1 required')
            flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
                     '-no-user-package-db', '-hide-all-packages', '-O2', '-fpedantic-bottoms',
                     '-fno-state-hack', '-Wno-star-is-type', '-Wno-overlapping-patterns',
                     '-Wno-deprecations', '-Werror=incomplete-patterns', '-Werror=incomplete-uni-patterns']
            for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
                flags += ['-package', package]
            record['ghc_flags'] = flags
            objects = output / 'ghc-objects'
            objects.mkdir()
            transports = []
            for label, relative in [('host', 'host/ghc/cbits/host.c'),
                                    ('supervisor', 'runtime/mlf_process_supervisor.c')]:
                target = output / (label + '.o')
                runner.run('compile-' + label, [clang, '-O2', '-std=c11',
                           '-I' + str(snapshots / 'runtime'), '-c', snapshots / relative, '-o', target], timeout=60)
                transports.append(target)
                artifact(target)
            binary = output / 'concat-ghc-audit'
            runner.run('compile-ghc', [ghc, '--make', '-j1', *flags,
                       '-i', '-i' + str(fixture_dir), '-i' + str(snapshots / 'host/ghc'),
                       *['-i' + str(path) for path in shared_roots],
                       '-odir', objects, '-hidir', objects, '-rtsopts=ignoreAll',
                       fixture_dir / 'Main.hs', *transports, '-o', binary], timeout=180,
                       overrides={'GHC_ENVIRONMENT': '-'})
            artifact(binary)
            runner.run('run-ghc', [binary], expected=HOST_EXPECTED, timeout=180)
            record['ghc_inventory'] = {'engines': 3, 'metadata_oracles': 8, 'interpreter_payload_oracles': 3,
                                       'literal_cases': 16,
                                       'finite_cases': 1555, 'large_cases': 5, 'demand_cases': 13,
                                       'demand_evaluations': 39}

        if native_enabled:
            cflags = shlex.split(runner.run('gmp-cflags', [pkg_config, '--cflags', 'gmp'], timeout=30).stdout.decode())
            libraries = shlex.split(runner.run('gmp-libs', [pkg_config, '--libs', 'gmp'], timeout=30).stdout.decode())
            record['gmp_flags'] = {'cflags': cflags, 'libraries': libraries}
            emitted = runner.run('emit-native', [compiler, '-i', foundation_dir, '-i', metadata_dir,
                                 '-i', fixture_dir, '--emit-llvm-gc', fixture_dir / 'Native.emlf'], timeout=240)
            llvm = output / 'concat-native.ll'
            llvm.write_bytes(emitted.stdout)
            artifact(llvm)
            require(re.search(r'call ptr @mlf_concat_string_list\(ptr ', emitted.stdout.decode()) is not None,
                    'no actual concatStringList helper call in emitted LLVM')
            record['shape_checks'].append('used-concatStringList-helper-call')
            for optimization in ['0', '2']:
                runtime = output / ('runtime-O' + optimization + '.o')
                runner.run('runtime-O' + optimization,
                           [clang, '-O' + optimization, '-std=c11', *cflags,
                            '-I' + str(gc / 'include'), '-I' + str(snapshots / 'runtime'),
                            '-c', snapshots / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
                artifact(runtime)
                runtime_probe = output / ('runtime-concat-O' + optimization)
                runner.run('link-runtime-probe-O' + optimization,
                           [clang, '-O' + optimization, '-std=c11', '-Wall', '-Wextra', '-Werror', *cflags,
                            '-I' + str(gc / 'include'), '-I' + str(snapshots / 'runtime'),
                            snapshots / 'tests/native/runtime_string_concat.c', runtime, gc_archive,
                            *libraries, '-lm', '-lpthread', '-ldl', '-o', runtime_probe], timeout=120)
                artifact(runtime_probe)
                for label, expected, diagnostic in RUNTIME_CASES:
                    name = label + '-O' + optimization
                    result = runner.run('runtime-probe-' + name, [runtime_probe, label],
                                        expected=expected, status=1 if diagnostic else 0, timeout=90)
                    require(result.stderr == diagnostic, 'exact direct runtime diagnostic differs: ' + name)
                    record['direct_runtime_cases'].append({'case': name, 'passed': True,
                                                          'stdout': expected.decode(), 'stderr': diagnostic.decode()})
                probe = output / ('gc-probe-O' + optimization + '.o')
                runner.run('probe-O' + optimization,
                           [clang, '-O' + optimization, '-std=c11', '-I' + str(gc / 'include'),
                            '-c', fixture_dir / 'gc_probe.c', '-o', probe], timeout=60)
                artifact(probe)
                binary = output / ('concat-native-O' + optimization)
                runner.run('link-native-O' + optimization,
                           [clang, '-O' + optimization, '-Wno-override-module', llvm, runtime, probe,
                            gc_archive, *libraries, '-lm', '-lpthread', '-ldl', '-o', binary], timeout=120)
                artifact(binary)
                for engine in ['stdlib', 'primitive', 'reference']:
                    for label, expected, diagnostic in NATIVE_CASES:
                        name = engine + '-' + label + '-O' + optimization
                        overrides = {'MLF_CONCAT_GC_REPORT': ''}
                        # The probe is disabled for ordinary exact-output cases.
                        # Empty path is treated as disabled by its C observer.
                        if label == 'stress':
                            report = output / (name + '.gc-count')
                            overrides = {'MLF_CONCAT_GC_REPORT': str(report),
                                         'GC_INITIAL_HEAP_SIZE': '1048576', 'GC_FREE_SPACE_DIVISOR': '4'}
                        arguments = [engine, label, *(['32768'] if label == 'stress' else [])]
                        result = runner.run('run-' + name, [binary, *arguments], expected=expected,
                                            status=1 if diagnostic else 0, timeout=90, overrides=overrides)
                        require(result.stderr == diagnostic, 'exact native diagnostic differs: ' + name)
                        entry = {'case': name, 'passed': True, 'stdout': expected.decode(),
                                 'stderr': diagnostic.decode()}
                        if label == 'stress':
                            count = report.read_text()
                            require(re.fullmatch(r'[0-9]+\n', count) is not None, 'invalid GC count report: ' + name)
                            require(int(count) >= 2, 'stress control did not observe multiple GC collections: ' + name)
                            entry['observed_gc_collections'] = int(count)
                            entry['stress_fragment_count'] = 32768
                            artifact(report)
                        record['native_cases'].append(entry)
                save()
            require(len(record['native_cases']) == 90, 'native completion inventory differs')
            require(len(record['direct_runtime_cases']) == 24, 'direct runtime completion inventory differs')
            record['native_inventory'] = {'engines': 3, 'optimizations': ['0', '2'],
                                          'cases_per_engine_per_optimization': 15, 'executions': 90,
                                          'gc_observed_stress_executions': 6}
            for engine in ['stdlib', 'primitive', 'reference']:
                for label, expected, diagnostic in NATIVE_CASES:
                    name = engine + '-' + label
                    # The interpreter covers the same generated-list/scalar
                    # semantics with a bounded 128-fragment workload. Large
                    # allocation/GC behavior belongs to the native stress run.
                    arguments = [engine, label, *(['128'] if label == 'stress' else [])]
                    result = runner.run('interpret-' + name,
                                        [compiler, '-i', foundation_dir, '-i', metadata_dir, '-i', fixture_dir,
                                         '--run', fixture_dir / 'Native.emlf', '--', *arguments],
                                        expected=expected, status=1 if diagnostic else 0, timeout=180)
                    require(result.stderr == diagnostic, 'exact interpreter diagnostic differs: ' + name)
                    record['interpreted_cases'].append({'case': name, 'passed': True,
                                                        'stdout': expected.decode(), 'stderr': diagnostic.decode(),
                                                        'stress_fragment_count': 128 if label == 'stress' else None})
            require(len(record['interpreted_cases']) == 45, 'interpreter completion inventory differs')
        integrity()
        record.update(complete=True, status='passed')
    except BaseException as error:
        record.update(complete=False, status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        try:
            integrity()
            record['immutable_inputs_verified_after'] = True
        except BaseException as error:
            record.update(complete=False, status='invalidated',
                          integrity_error=type(error).__name__ + ': ' + str(error))
            raise
        finally:
            save()
    print(str(output / 'receipt.json') + ': passed (' + args.mode + ')')


if __name__ == '__main__':
    main()
