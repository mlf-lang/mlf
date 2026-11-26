#!/usr/bin/env python3
"""Check exact bulk byte equality, mutable IO, both ABI lanes and GC ownership."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import shutil
import sys

from default_stdlib import configuration
from test_direct import CommandRunner, authenticate_build, sha, verify_file

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tools/shared/fixtures/byte-array-equal'


def expected(left, right):
    changed = bytes([left[0] ^ 255]) + left[1:] if left else left
    return ''.join(f'{int(value)}\n' for value in
                   [left == right, changed == right, left == right, changed == right, True, True]).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--clang', default='clang')
    args = parser.parse_args()
    receipt = args.build_receipt.resolve(strict=True)
    build, output = receipt.parent, args.output.resolve()
    if output == ROOT or ROOT.is_relative_to(output) or output.is_relative_to(build):
        parser.error('independent output directory required')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'commands': [], 'inputs': {}, 'artifacts': {},
              'scope': 'exact bytes, mutation, lazy IO, host pinned-owner GC, interpreter and native saturated/dynamic ABI',
              'performance_assertions': False, 'native_toolchain_closure_complete': False,
              'native_provenance_scope': 'selected Clang, runtime/header closure, fixed GMP/BDWGC libraries; system dependencies are not fully pinned'}

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'receipt.json')

    def artifact(path):
        record['artifacts'][str(path)] = sha(path)

    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        producer = authenticate_build(receipt, build / 'bin')
        native = configuration(args.clang)
        record['native_configuration'] = native
        record['producer_sha256'] = sha(receipt)
        objects = []
        for name, digest in producer['object_inputs'].items():
            path = (build / name).resolve(strict=True)
            verify_file({'path': str(path), 'sha256': digest})
            record['inputs'][str(path)] = digest
            if path.suffix == '.o' and path.name != 'Main.o':
                objects.append(path)
        inputs = [*FIXTURES.glob('*.hs'), receipt, Path(__file__).resolve(),
                  ROOT / 'tools/shared/test_direct.py', ROOT / 'tools/shared/default_stdlib.py',
                  ROOT / 'host/ghc/MLF/Host/IO.hs', ROOT / 'host/ghc/cbits/host.c',
                  ROOT / 'tests/native/runtime_byte_array_equal.c',
                  ROOT / 'runtime/mlf_process_supervisor.c', ROOT / 'runtime/mlf_runtime.c',
                  *sorted((ROOT / 'runtime').glob('*.h')), Path(sys.executable).resolve(),
                  Path(native['clang']), Path(producer['cc']['path']),
                  Path(shutil.which('pkg-config')).resolve()]
        inputs += [Path(arg) for arg in native['link_args'] if Path(arg).is_absolute()]
        record['inputs'].update({str(path): sha(path) for path in inputs})
        flags = ['-O' + producer['optimization'], '-fpedantic-bottoms', '-fno-state-hack',
                 '-dcore-lint', '-package-env', '-', '-clear-package-db', '-global-package-db',
                 '-no-user-package-db', '-hide-all-packages']
        for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
            flags += ['-package', package]
        ghc = producer['ghc']['path']
        for label, source in [('host', ROOT / 'host/ghc/cbits/host.c'),
                              ('supervisor', ROOT / 'runtime/mlf_process_supervisor.c')]:
            target = output / (label + '.o')
            runner.run('compile-' + label, [producer['cc']['path'], '-O2', '-std=c11',
                       '-I' + str(ROOT / 'runtime'), '-c', source, '-o', target])
            objects.append(target)
            artifact(target)

        # Exercise a collection while both safe-FFI borrows are active. The
        # production adapter remains unchanged; the copied module is recorded.
        host_source = (ROOT / 'host/ghc/MLF/Host/IO.hs').read_text()
        boundary = ('      withByteStorage rightCells $ \\b ->\n'
                    '        (/= 0) <$> c_byteArrayEqual a b (fromIntegral leftSize)')
        if host_source.count(boundary) != 1:
            raise ValueError('byte equality borrow boundary changed')
        injected = output / 'EqualGC.hs'
        injected.write_text(host_source.replace('module MLF.Host.IO where', 'module EqualGC where', 1)
            .replace('import Prelude hiding (Int, String)',
                     'import Prelude hiding (Int, String)\nimport System.Mem (performGC)', 1)
            .replace(boundary, '      withByteStorage rightCells $ \\b -> do\n'
                     '        performGC\n'
                     '        (/= 0) <$> c_byteArrayEqual a b (fromIntegral leftSize)', 1))
        artifact(injected)
        runner.run('compile-GC-borrow', [ghc, '-c', *flags, '-Wno-deprecations', '-i',
                   '-i' + str(build / 'objects'), injected, '-o', output / 'EqualGC.o',
                   '-ohi', output / 'EqualGC.hi'])
        for label, fixture, extra in [('oracle', 'Host.hs', [output / 'EqualGC.o']),
                                      ('host', 'Equal.hs', [])]:
            runner.run('compile-' + label, [ghc, '-c', *flags, '-i', '-i' + str(output),
                       '-i' + str(build / 'objects'), FIXTURES / fixture,
                       '-o', output / (label + '-Main.o'), '-ohi', output / (label + '-Main.hi')])
            runner.run('link-' + label, [ghc, *flags, '-rtsopts=ignoreAll',
                       output / (label + '-Main.o'), *extra, *sorted(objects), '-o', output / label])
            artifact(output / label)
        runner.run('host-exact-bytes-GC-demand', [output / 'oracle'], expected=(
            b'PASS byte-array equality: independent exact bytes, mutation, metadata, lazy IO, and pinned-owner GC\n'), timeout=180)

        emitted = runner.run('emit-native', [build / 'bin/emlf', '-i', ROOT / 'libraries/mlf-foundation',
                             '--emit-llvm-gc', FIXTURES / 'Equal.hs'], timeout=240)
        llvm = output / 'program.ll'
        llvm.write_bytes(emitted.stdout)
        artifact(llvm)
        if b'mlf_require_byte_array_equal_abi' not in emitted.stdout or b'i64 137' not in emitted.stdout:
            raise ValueError('generated byte equality is missing its appended ABI guard/opcode')
        interpreted = runner.run('emit-interpreter', [build / 'bin/emlf', '-i',
                                 ROOT / 'libraries/mlf-foundation', FIXTURES / 'Equal.hs'], timeout=240)
        xmlf = output / 'program.xmlf'
        xmlf.write_bytes(interpreted.stdout)
        artifact(xmlf)
        lanes = {'host': [output / 'host'],
                 'interpreter': [build / 'bin/emlf', '--run-xmlf', xmlf, '--']}
        record['direct_runtime_cases'] = []
        for opt in ['0', '2']:
            runtime = output / ('runtime-O' + opt + '.o')
            runner.run('compile-runtime-O' + opt, [native['clang'], '-O' + opt, '-std=c11',
                       *native['runtime_flags'], '-I' + str(ROOT / 'runtime'), '-c',
                       ROOT / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
            artifact(runtime)
            binary = output / ('native-O' + opt)
            runner.run('link-native-O' + opt, [native['clang'], '-O' + opt, '-Wno-override-module',
                       llvm, runtime, *native['link_args'], '-lpthread', '-ldl', '-o', binary], timeout=120)
            artifact(binary)
            lanes['native-O' + opt] = [binary]
            probe = output / ('runtime-equal-O' + opt)
            runner.run('link-probe-O' + opt, [native['clang'], '-O' + opt, '-std=c11', '-Wall',
                       '-Wextra', '-Werror', *native['runtime_flags'], '-I' + str(ROOT / 'runtime'),
                       ROOT / 'tests/native/runtime_byte_array_equal.c', runtime, *native['link_args'],
                       '-lpthread', '-ldl', '-o', probe], timeout=120)
            artifact(probe)
            for mode, message in [('success', ''), ('no-interior', ''), ('left', 'left-demand'),
                                  ('right', 'right-demand'), ('wrong-left', 'invalid value for runtime operation'),
                                  ('wrong-right', 'invalid value for runtime operation')]:
                result = runner.run('runtime-' + mode + '-O' + opt, [probe, mode],
                    expected=b'' if message else b'runtime byte-array equality: 36 dynamic/saturated ABI, IO demand, exact-byte and GC cases passed\n',
                    status=1 if message else 0, timeout=120)
                if result.stderr != (('Runtime: ' + message + '\n').encode() if message else b''):
                    raise ValueError('direct runtime diagnostic differs: ' + mode)
                record['direct_runtime_cases'].append({'optimization': opt, 'case': mode})

        rng = random.Random(1372026)
        record['vector_counts'] = {lane: 0 for lane in lanes}
        for size in [0,1,2,31,256,4097,65537,1048583]:
            data = bytes(rng.randrange(256) for _ in range(size))
            left = output / ('left-' + str(size))
            left.write_bytes(data)
            artifact(left)
            variants = [('equal', data), ('longer', data + b'\0'), ('shorter', data[:-1])]
            if size:
                variants += [(name, data[:index] + bytes([data[index] ^ 255]) + data[index+1:])
                             for name, index in [('first',0), ('middle',size//2), ('last',size-1)]]
            for name, other in variants:
                right = output / (name + '-' + str(size))
                right.write_bytes(other)
                artifact(right)
                for lane, argv in lanes.items():
                    result = runner.run(f'{lane}-{size}-{name}', [*argv, 'compare', left, right],
                                        expected=expected(data, other), timeout=90)
                    if result.stderr:
                        raise ValueError('unexpected diagnostic: ' + lane)
                    record['vector_counts'][lane] += 1
        for lane, argv in lanes.items():
            for mode in ['defer', 'unused']:
                runner.run(lane + '-' + mode, [*argv, mode], expected=b'42\n', timeout=90)
            for mode, message in [('left','left-demand'), ('right','right-demand')]:
                result = runner.run(lane + '-' + mode, [*argv, mode], expected=b'', status=1, timeout=90)
                text = result.stderr.decode()
                if message not in text or (mode == 'left' and 'right-demand' in text):
                    raise ValueError('incorrect IO demand diagnostic: ' + lane + '/' + mode)
        record['demand_checks_per_lane'] = 4
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            if sha(path) != digest:
                raise ValueError('input or artifact changed: ' + path)
        authenticate_build(receipt, build / 'bin')
        record['complete'] = True
        print('PASS byte-array equality: ' + json.dumps(record['vector_counts'], sort_keys=True) +
              '; 4 demand checks per backend; host pinned-owner GC; 12 direct runtime cases')
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
