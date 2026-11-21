#!/usr/bin/env python3
"""Independent UTF-8 byte-length controls for host, interpreter and native paths."""
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
FIXTURES = ROOT / 'tools/shared/fixtures/utf8-length'



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
              'scope': 'UTF-8 byte length, scalar distinction, primitive ABI, validation, demand and GC controls',
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
                  ROOT / 'tests/native/runtime_utf8_length.c',
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
        for label, fixture in [('oracle', 'Main.hs'), ('host', 'Length.hs')]:
            runner.run('compile-' + label, [ghc, '-c', *flags, '-i', '-i' + str(build / 'objects'),
                       FIXTURES / fixture, '-o', output / (label + '-Main.o'),
                       '-ohi', output / (label + '-Main.hi')])
            runner.run('link-' + label, [ghc, *flags, '-rtsopts=ignoreAll',
                       output / (label + '-Main.o'), *sorted(objects), '-o', output / label])
            artifact(output / label)
        runner.run('host-oracle', [output / 'oracle'], expected=(
            b'PASS UTF-8 length: 78 host count/slice/concat cases, byte budgets, primitive metadata and demand\n'))
        emitted = runner.run('emit-native', [build / 'bin/emlf', '-i', ROOT / 'libraries/mlf-foundation',
                             '--emit-llvm-gc', FIXTURES / 'Length.hs'], timeout=240)
        llvm = output / 'program.ll'; llvm.write_bytes(emitted.stdout); artifact(llvm)
        if not re.search(rb'call ptr @mlf_string_utf8_length\(ptr ', emitted.stdout):
            raise ValueError('generated program does not call the UTF-8 byte-length helper')
        lanes = {'host': [output / 'host'], 'interpreter': [build / 'bin/emlf', '-i',
                 ROOT / 'libraries/mlf-foundation', '--run', FIXTURES / 'Length.hs', '--']}
        record['direct_runtime_cases'] = []
        probes = [('success', ''), ('no-interior', ''), ('bottom', 'text-first'),
                  ('wrong-type', 'invalid value for runtime operation'),
                  ('invalid-utf8', 'invalid Unicode scalar'), ('overflow', 'string too large')]
        for opt in ['0', '2']:
            runtime = output / ('runtime-O' + opt + '.o')
            runner.run('compile-runtime-O' + opt, [native['clang'], '-O' + opt, '-std=c11',
                       *native['runtime_flags'], '-I' + str(ROOT / 'runtime'), '-c',
                       ROOT / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
            artifact(runtime)
            binary = output / ('native-O' + opt)
            runner.run('link-native-O' + opt, [native['clang'], '-O' + opt, '-Wno-override-module',
                       llvm, runtime, *native['link_args'], '-lpthread', '-ldl', '-o', binary], timeout=120)
            artifact(binary); lanes['native-O' + opt] = [binary]
            probe = output / ('runtime-length-O' + opt)
            runner.run('link-probe-O' + opt, [native['clang'], '-O' + opt, '-std=c11', '-Wall',
                       '-Wextra', '-Werror', *native['runtime_flags'], '-I' + str(ROOT / 'runtime'),
                       ROOT / 'tests/native/runtime_utf8_length.c', runtime, *native['link_args'],
                       '-lpthread', '-ldl', '-o', probe], timeout=120)
            artifact(probe)
            for mode, error in probes:
                result = runner.run('runtime-' + mode + '-O' + opt, [probe, mode],
                    expected=b'' if error else b'runtime UTF-8 length: values, validation cache, ABI, demand and GC passed\n',
                    status=1 if error else 0, timeout=120)
                if result.stderr != (('Runtime: ' + error + '\n').encode() if error else b''):
                    raise ValueError('direct runtime diagnostic differs: ' + mode)
                record['direct_runtime_cases'].append({'optimization': opt, 'case': mode})
        unit = 'aα中😀\0'
        vectors = [(['count', str(n)], unit*n) for n in [0,1,2,63,64,65,255,256,257,1024]]
        vectors += [(['scalar', str(n)], chr(n)) for n in [0,1,127,128,2047,2048,55295,57344,65535,65536,1114111]]
        vectors += [(['slice','65',str(start),str(count)], (unit*65)[start:start+count])
                    for start,count in [(0,0),(0,5),(1,3),(3,7),(255,1),(256,3),(324,1),(325,0)]]
        record['vector_counts'], record['demand_counts'] = {}, {}
        for lane, argv in lanes.items():
            record['vector_counts'][lane] = record['demand_counts'][lane] = 0
            for index, (arguments, text) in enumerate(vectors):
                if lane == 'interpreter' and arguments[0] == 'count' and int(arguments[1]) > 65:
                    continue
                expected = f'{len(text.encode("utf-8"))}\n{len(text)}\n'.encode()
                result = runner.run(lane + '-vector-' + str(index), [*argv, *arguments], expected=expected, timeout=120)
                if result.stderr: raise ValueError('unexpected diagnostic: ' + lane)
                record['vector_counts'][lane] += 1
            runner.run(lane + '-unused', [*argv, 'unused'], expected=b'42\n', timeout=120)
            record['demand_counts'][lane] += 1
            for mode, error in [('argument', 'text-first'), ('invalid', 'invalid Unicode scalar')]:
                result = runner.run(lane + '-' + mode, [*argv, mode], expected=b'', status=1, timeout=120)
                if error not in result.stderr.decode(): raise ValueError('wrong demand diagnostic: ' + lane + '/' + mode)
                record['demand_counts'][lane] += 1
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            if sha(path) != digest: raise ValueError('input or artifact changed: ' + path)
        authenticate_build(receipt, build / 'bin')
        record['complete'] = True
        print('PASS UTF-8 length: ' + json.dumps(record['vector_counts'], sort_keys=True) +
              '; 3 demand checks per backend; 12 direct runtime cases')
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
