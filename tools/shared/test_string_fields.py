#!/usr/bin/env python3
"""Independent field framing controls for host, interpreter and native paths."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import sys

from default_stdlib import configuration
from test_direct import CommandRunner, authenticate_build, sha, verify_file

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tools/shared/fixtures/fields'


def framed(fields):
    text = ''.join(str(len(field)) + ':' + field for field in fields)
    return (text + '\n' + str(len(text)) + '\n').encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--clang', default='clang')
    args = parser.parse_args()
    receipt = args.build_receipt.resolve(strict=True)
    build, output = receipt.parent, args.output.resolve()
    if output == ROOT or ROOT.is_relative_to(output):
        raise ValueError('output cannot contain the checkout')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'commands': [], 'inputs': {}, 'artifacts': {},
              'scope': 'finite Unicode field framing, demand order, primitive ABI and GC root controls',
              'performance_assertions': False, 'native_toolchain_closure_complete': False,
              'native_provenance_scope': 'selected Clang, runtime/header closure and fixed GMP/BDWGC libraries; system dependencies are not fully pinned'}

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
        inputs = [*FIXTURES.glob('*.hs'), Path(__file__).resolve(), receipt,
                  ROOT / 'tools/shared/test_direct.py', ROOT / 'tools/shared/default_stdlib.py',
                  ROOT / 'tests/native/runtime_string_fields.c',
                  ROOT / 'host/ghc/cbits/host.c', ROOT / 'runtime/mlf_process_supervisor.c',
                  ROOT / 'runtime/mlf_runtime.c', *sorted((ROOT / 'runtime').glob('*.h')),
                  Path(sys.executable).resolve(), Path(native['clang']), Path(producer['cc']['path']),
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
        for label, fixture in [('oracle', 'Main.hs'), ('host', 'Fields.hs')]:
            runner.run('compile-' + label, [ghc, '-c', *flags, '-i', '-i' + str(build / 'objects'),
                       FIXTURES / fixture, '-o', output / (label + '-Main.o'),
                       '-ohi', output / (label + '-Main.hi')])
            runner.run('link-' + label, [ghc, *flags, '-rtsopts=ignoreAll',
                       output / (label + '-Main.o'), *sorted(objects), '-o', output / label])
            artifact(output / label)
        runner.run('host-oracle', [output / 'oracle'], expected=(
            b'PASS framing 241 independent cases in 3 lanes, Unicode scalar caches and 6 demand controls per lane\n'))
        emitted = runner.run('emit-native', [build / 'bin/emlf', '-i',
                             ROOT / 'libraries/mlf-foundation', '--emit-llvm-gc', FIXTURES / 'Fields.hs'], timeout=240)
        llvm = output / 'program.ll'
        llvm.write_bytes(emitted.stdout)
        artifact(llvm)
        if not re.search(rb'call ptr @mlf_pack_string_fields\(ptr ', emitted.stdout):
            raise ValueError('generated program did not call the field framing helper')
        lanes = {'host': [output / 'host'], 'interpreter': [build / 'bin/emlf', '-i',
                 ROOT / 'libraries/mlf-foundation', '--run', FIXTURES / 'Fields.hs', '--']}
        record['direct_runtime_cases'] = []
        direct_cases = [('success', ''), ('no-interior', ''), ('list-bottom', 'list-first'),
                        ('head-before-tail', 'head-first'), ('later-head-before-tail', 'second-head'),
                        ('tail-bottom', 'tail-second'), ('wrong-list', 'expected canonical string list'),
                        ('improper-tail', 'expected canonical string list'),
                        ('wrong-head', 'invalid value for runtime operation'),
                        *[(name, 'string too large') for name in
                          ['overflow-total', 'overflow-wrap', 'overflow-scalars', 'overflow-before-tail']]]
        for optimization in ['0', '2']:
            runtime = output / ('runtime-O' + optimization + '.o')
            runner.run('compile-runtime-O' + optimization, [native['clang'], '-O' + optimization,
                       '-std=c11', *native['runtime_flags'], '-I' + str(ROOT / 'runtime'),
                       '-c', ROOT / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
            artifact(runtime)
            binary = output / ('native-O' + optimization)
            runner.run('link-native-O' + optimization, [native['clang'], '-O' + optimization,
                       '-Wno-override-module', llvm, runtime, *native['link_args'],
                       '-lpthread', '-ldl', '-o', binary], timeout=120)
            artifact(binary)
            lanes['native-O' + optimization] = [binary]
            probe = output / ('runtime-fields-O' + optimization)
            runner.run('link-probe-O' + optimization, [native['clang'], '-O' + optimization,
                       '-std=c11', '-Wall', '-Wextra', '-Werror', *native['runtime_flags'],
                       '-I' + str(ROOT / 'runtime'), ROOT / 'tests/native/runtime_string_fields.c',
                       runtime, *native['link_args'], '-lpthread', '-ldl', '-o', probe], timeout=120)
            artifact(probe)
            for mode, diagnostic in direct_cases:
                expected = b'' if diagnostic else b'runtime fields: bytes, scalar indices, sharing, order, ABI, and GC passed\n'
                result = runner.run('runtime-' + mode + '-O' + optimization, [probe, mode],
                                    expected=expected, status=1 if diagnostic else 0, timeout=120)
                if result.stderr != (('Runtime: ' + diagnostic + '\n').encode() if diagnostic else b''):
                    raise ValueError('direct runtime diagnostic differs: ' + mode)
                record['direct_runtime_cases'].append({'optimization': optimization, 'case': mode})
        vectors = [('empty', [], []), ('literal', [], ['', 'a:β', '🌍', '\0', '0:12:'])]
        vectors += [('boundary', [str(n)], ['aα😀' * n, '', ':0:ab', '\0'])
                    for n in [0, 1, 2, 3, 9, 10, 33, 34, 85, 86, 333, 334, 3333, 3334]]
        vectors += [('many', [str(n)], ['aα😀' * ((i * 37) % 300) for i in range(n)])
                    for n in [0, 1, 16, 256, 1024]]
        demands = [('list', 'list-first'), ('head', 'head-first'), ('tail', 'tail-required'),
                   ('later-head', 'second-first'), ('empty-tail', 'tail-required')]
        record['vector_counts'], record['demand_counts'] = {}, {}
        for lane, argv in lanes.items():
            record['vector_counts'][lane] = record['demand_counts'][lane] = 0
            for engine in ['primitive', 'reference']:
                for index, (mode, arguments, fields) in enumerate(vectors):
                    if lane == 'interpreter' and index not in [0, 1, 2, 9, 10, 14, 18]:
                        continue
                    result = runner.run(f'{lane}-{engine}-{index}', [*argv, engine, mode, *arguments],
                                        expected=framed(fields), timeout=120)
                    if result.stderr:
                        raise ValueError('unexpected diagnostic: ' + lane)
                    record['vector_counts'][lane] += 1
                runner.run(f'{lane}-{engine}-unused', [*argv, engine, 'unused'], expected=b'lazy\n', timeout=120)
                record['demand_counts'][lane] += 1
                for mode, diagnostic in demands:
                    result = runner.run(f'{lane}-{engine}-{mode}', [*argv, engine, mode],
                                        expected=b'', status=1, timeout=120)
                    errors = result.stderr.decode()
                    if diagnostic not in errors or any(other in errors for other in
                            ['list-first', 'head-first', 'tail-second', 'tail-required', 'second-first'] if other != diagnostic):
                        raise ValueError('incorrect demand order: ' + lane + '/' + engine + '/' + mode)
                    record['demand_counts'][lane] += 1
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            if sha(path) != digest:
                raise ValueError('input or artifact changed: ' + path)
        authenticate_build(receipt, build / 'bin')
        record['complete'] = True
        print('PASS field framing: ' + json.dumps(record['vector_counts'], sort_keys=True) +
              '; 12 demand checks per backend; 26 direct runtime cases')
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
