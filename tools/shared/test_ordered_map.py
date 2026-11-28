#!/usr/bin/env python3
"""Check ordered Map construction against independent host and native oracles."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from default_stdlib import configuration
from test_direct import CommandRunner, authenticate_build, sha, verify_file

ROOT = Path(__file__).resolve().parents[2]
HOST = ROOT / 'tests/indexvec/OrderedMapControls.hs'
NATIVE = ROOT / 'tools/shared/fixtures/OrderedMap.hs'
UNION_HOST = ROOT / 'tests/indexvec/UnionMapControls.hs'
UNION_NATIVE = ROOT / 'tools/shared/fixtures/UnionMap.hs'
SIZES = [0, 1, 2, 3, 7, 16, 31, 32, 127, 256, 511, 1024]


def expected(mode, count):
    """Integer-key dictionary oracle, independent of balancing or prefix detection."""
    ascending = list(range(count + 1))
    keys = [ascending, ascending[::-1], [k for k in ascending for _ in range(3)],
            ascending + [-1] + ascending,
            [k * 79 % (count + 1) for k in ascending],
            [k*4+j for k in ascending for j in [3,2,1,0]],
            [k*4+j for k in reversed(ascending) for j in [0,1,2,3]],
            [x for k in ascending for x in [k,0,k,1,k,2]]][mode]
    wrap = lambda n: (n + 2**63) % 2**64 - 2**63
    ordinary, combined = {}, {}
    for value, key in enumerate(keys):
        ordinary[key] = value
        combined[key] = wrap(value * 131 + combined[key]) if key in combined else value

    def summarize(entries, tagged=False):
        result = len(entries)
        for key, value in sorted(entries.items()):
            result = wrap(result * 131 + key)
            if tagged:
                result = wrap(result * 131 + value)
            result = wrap(result * 131 + value)
        return result

    return f'{summarize(ordinary)},{summarize(combined)},{summarize(ordinary, True)}\n'.encode()


def union_expected(mode, count):
    """Dictionary union oracle; retain the left representative explicitly."""
    asc = list(range(count + 1))
    left, right = [
        (asc, list(range(count // 2, count + count // 2 + 1))),
        (asc, list(range(count + 1, count * 2 + 2))),
        ([2 * k for k in asc], [2 * k + 1 for k in asc]),
        ([k for k in reversed(asc) for _ in range(3)], asc),
        ([0, count // 2, count + 1], asc),
        (asc, [0, count // 2, count + 1]),
    ][mode]
    first = {key: (ordinal, ordinal) for ordinal, key in enumerate(left)}
    second = {key: (ordinal, ordinal) for ordinal, key in enumerate(right, 10000)}
    wrap = lambda n: (n + 2**63) % 2**64 - 2**63
    ordinary, combined = dict(second), dict(second)
    ordinary.update(first)
    for key, (representative, value) in first.items():
        combined[key] = (representative, wrap(value * 131 + second[key][1] * 17)
                         if key in second else value)

    def summarize(entries, tagged=False):
        result = len(entries)
        for key, (representative, value) in sorted(entries.items()):
            result = wrap(result * 131 + key)
            if tagged:
                result = wrap(result * 131 + representative)
            result = wrap(result * 131 + value)
        return result

    return f'{summarize(ordinary)},{summarize(combined)},{summarize(combined, True)}\n'.encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--clang', default='clang')
    args = parser.parse_args()
    build_receipt = args.build_receipt.resolve(strict=True)
    build, output = build_receipt.parent, args.output.resolve()
    if output == ROOT or ROOT.is_relative_to(output):
        raise ValueError('output cannot contain the checkout')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'commands': [], 'inputs': {}, 'artifacts': {},
              'scope': 'GHC-hosted Map and generated native Map programs; finite semantic controls',
              'native_toolchain_closure_complete': False,
              'native_provenance_scope': 'selected Clang, runtime sources, fixed GMP/BDWGC libraries; system headers and libraries are not fully pinned'}

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'receipt.json')

    def artifact(path):
        record['artifacts'][str(path)] = sha(path)

    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        producer = authenticate_build(build_receipt, build / 'bin')
        native = configuration(args.clang)
        record['native_configuration'] = native
        record['producer_sha256'] = sha(build_receipt)
        objects = []
        for name, digest in producer['object_inputs'].items():
            path = (build / name).resolve(strict=True)
            verify_file({'path': str(path), 'sha256': digest})
            record['inputs'][str(path)] = digest
            if path.suffix == '.o' and path.name != 'Main.o':
                objects.append(path)
        inputs = [HOST, NATIVE, UNION_HOST, UNION_NATIVE, Path(__file__).resolve(),
                  ROOT / 'tools/shared/test_direct.py', ROOT / 'tools/shared/default_stdlib.py',
                  build_receipt, Path(sys.executable).resolve(), Path(native['clang']),
                  Path(producer['cc']['path']), ROOT / 'host/ghc/cbits/host.c',
                  ROOT / 'runtime/mlf_process_supervisor.c',
                  Path(shutil.which('pkg-config')).resolve(), ROOT / 'runtime/mlf_runtime.c',
                  *sorted((ROOT / 'runtime').glob('*.h'))]
        inputs += [Path(arg) for arg in native['link_args'] if Path(arg).is_absolute()]
        record['inputs'].update({str(path): sha(path) for path in inputs})
        producer_optimization = producer['optimization']
        flags = ['-O' + producer_optimization, '-fpedantic-bottoms', '-fno-state-hack',
                 '-package-env', '-', '-clear-package-db', '-global-package-db',
                 '-no-user-package-db', '-hide-all-packages']
        for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
            flags += ['-package', package]
        ghc = producer['ghc']['path']
        # The producer's object inventory contains Haskell modules only. Build
        # the two C transports from authenticated sources instead of silently
        # relying on unlisted objects left in its build directory.
        for label, source in [('host', ROOT / 'host/ghc/cbits/host.c'),
                              ('supervisor', ROOT / 'runtime/mlf_process_supervisor.c')]:
            target = output / (label + '.o')
            runner.run('compile-' + label + '-transport', [producer['cc']['path'], '-O2',
                       '-std=c11', '-I' + str(ROOT / 'runtime'), '-c', source, '-o', target])
            objects.append(target)
            artifact(target)
        runner.run('compile-host', [ghc, '-c', *flags, '-i', '-i' + str(build / 'objects'),
                   HOST, '-o', output / 'Main.o', '-ohi', output / 'Main.hi'])
        runner.run('link-host', [ghc, *flags, '-rtsopts=ignoreAll', output / 'Main.o',
                   *sorted(objects), '-o', output / 'host-controls'])
        artifact(output / 'host-controls')
        runner.run('run-host', [output / 'host-controls'], timeout=120,
                   expected=b'PASS ordered maps: 19611 cases and 11 demand checks\n')
        union_message = (b'PASS union: 16745 map pairs; independent content, representatives, '
                         b'combine order and balance; 9 demand controls\n')
        runner.run('compile-union-host', [ghc, '-c', *flags, '-i', '-i' + str(build / 'objects'),
                   UNION_HOST, '-o', output / 'UnionMain.o', '-ohi', output / 'UnionMain.hi'])
        runner.run('link-union-host', [ghc, *flags, '-rtsopts=ignoreAll', output / 'UnionMain.o',
                   *sorted(objects), '-o', output / 'union-host-controls'])
        artifact(output / 'union-host-controls')
        runner.run('run-union-host', [output / 'union-host-controls'],
                   expected=union_message, timeout=120)
        # Build the real Map closure at the other optimization level in a
        # fresh directory. Recompiling only the fixture would mix levels.
        alternate_optimization = '2' if producer_optimization == '0' else '0'
        alternate_flags = ['-O' + alternate_optimization, *flags[1:]]
        alternate_name = 'union-host-O' + alternate_optimization
        alternate_objects = output / alternate_name
        alternate_controls = output / (alternate_name + '-controls')
        alternate_objects.mkdir()
        runner.run('compile-' + alternate_name, [ghc, '--make', '-j1', *alternate_flags,
                   '-i', '-Wno-star-is-type', '-Wno-deprecations',
                   '-i' + str(ROOT / 'libraries/mlf-foundation'), '-i' + str(ROOT / 'host/ghc'),
                   '-odir', alternate_objects, '-hidir', alternate_objects, '-rtsopts=ignoreAll',
                   UNION_HOST, output / 'host.o', output / 'supervisor.o', '-o', alternate_controls],
                   timeout=180)
        artifact(alternate_controls)
        runner.run('run-' + alternate_name, [alternate_controls], expected=union_message, timeout=180)
        emitted = runner.run('emit-native', [build / 'bin/emlf', '-i',
                             ROOT / 'libraries/mlf-foundation', '--emit-llvm-gc', NATIVE], timeout=240)
        llvm = output / 'program.ll'
        llvm.write_bytes(emitted.stdout)
        artifact(llvm)
        runner.run('compile-runtime', [native['clang'], '-O2', '-std=c11',
                   *native['runtime_flags'], '-I' + str(ROOT / 'runtime'), '-c',
                   ROOT / 'runtime/mlf_runtime.c', '-o', output / 'runtime.o'], timeout=120)
        artifact(output / 'runtime.o')
        runner.run('link-native', [native['clang'], '-O2', '-Wno-override-module', llvm,
                   output / 'runtime.o', *native['link_args'], '-lpthread', '-ldl',
                   '-o', output / 'native-controls'], timeout=120)
        artifact(output / 'native-controls')
        for mode in range(8):
            for size in SIZES:
                runner.run(f'native-{mode}-{size}', [output / 'native-controls', mode, size],
                           expected=expected(mode, size), timeout=30)
        runner.run('native-lazy', [output / 'native-controls', 'lazy'], expected=b'17,23,1\n', timeout=30)
        runner.run('native-lazy-runs', [output / 'native-controls', 'lazy-runs'], expected=b'17,23\n', timeout=30)
        for mode, diagnostic in [('key', b'Runtime: first-key\n'), ('compare', b'Runtime: comparison\n')]:
            result = runner.run('native-' + mode, [output / 'native-controls', mode],
                                status=1, expected=b'', timeout=30)
            if result.stderr != diagnostic:
                raise ValueError('incorrect native demand order: ' + mode)
        emitted = runner.run('emit-union-native', [build / 'bin/emlf', '-i',
                             ROOT / 'libraries/mlf-foundation', '--emit-llvm-gc', UNION_NATIVE], timeout=240)
        union_llvm = output / 'union.ll'
        union_llvm.write_bytes(emitted.stdout)
        artifact(union_llvm)
        runner.run('link-union-native', [native['clang'], '-O2', '-Wno-override-module', union_llvm,
                   output / 'runtime.o', *native['link_args'], '-lpthread', '-ldl',
                   '-o', output / 'union-native-controls'], timeout=120)
        artifact(output / 'union-native-controls')
        for mode in range(6):
            for size in SIZES:
                runner.run(f'union-native-{mode}-{size}', [output / 'union-native-controls', mode, size],
                           expected=union_expected(mode, size), timeout=30)
        runner.run('union-native-lazy', [output / 'union-native-controls', 'lazy'],
                   expected=b'17,23,2\n', timeout=30)
        for mode, diagnostic in [('left', b'Runtime: left-tree\n'), ('right', b'Runtime: right-tree\n')]:
            result = runner.run('union-native-' + mode, [output / 'union-native-controls', mode],
                                status=1, expected=b'', timeout=30)
            if result.stderr != diagnostic:
                raise ValueError('incorrect union native demand order: ' + mode)
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            if sha(path) != digest:
                raise ValueError('input or artifact changed: ' + path)
        authenticate_build(build_receipt, build / 'bin')
        record.update(complete=True, host_cases=19611, host_demand_checks=11, native_cases=100,
                      union_host_pairs_per_optimization=16745, union_host_demand_checks=9,
                      union_host_optimizations=sorted([producer_optimization, alternate_optimization]),
                      union_native_cases=75)
        print('PASS ordered maps: 19611 host cases, 11 host demand checks, 100 native cases; '
              'union 16745 host pairs at O0/O2, 9 demand checks and 75 native cases')
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
