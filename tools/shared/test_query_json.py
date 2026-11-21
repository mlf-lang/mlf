#!/usr/bin/env python3
"""Check actual query JSON functions against independent host and native oracles."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from default_stdlib import configuration
from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]
HOST = ROOT / 'tests/shared-host/QueryJsonProbe.hs'
TEMPLATE = ROOT / 'tools/shared/fixtures/QueryJson.hs.txt'
SOURCE = ROOT / 'libraries/mlf-crates/Bootstrap/CrateQuery.hs'


def quote(text):
    # json.dumps supplies the independent JSON encoder; normalize its five
    # permitted short control escapes to the compiler's documented spelling.
    output = json.dumps(text, ensure_ascii=False)
    replacements = {'b': '0008', 'f': '000c', 'n': '000a', 'r': '000d', 't': '0009'}
    pieces, index = [], 0
    while index < len(output):
        if output[index] == '\\' and index + 1 < len(output):
            escaped = output[index + 1]
            pieces.append('\\u' + replacements[escaped] if escaped in replacements else output[index:index + 2])
            index += 2
        else:
            pieces.append(output[index])
            index += 1
    return ''.join(pieces)


def sample(mode, count):
    if mode == 0:
        return ''.join(chr(i % 32) for i in range(count))
    if mode == 1:
        return 'a"\\\n😀é中' * count
    if mode == 2:
        return 'ordinary-AZ09_' * count
    return ''.join(map(chr, [0,31,32,34,92,127,128,255,256,2047,2048,55295,57344,65535,65536,1114111]))


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
              'scope': 'GHC-hosted actual CrateQuery at O0/O2; generated native programs containing the exact maintained JSON function block',
              'native_toolchain_closure_complete': False}
    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    def artifact(path):
        record['artifacts'][str(path)] = sha(path)
    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        producer = authenticate_build(receipt, build / 'bin')
        native = configuration(args.clang)
        record['producer_sha256'] = sha(receipt)
        record['native_configuration'] = native
        sources = [HOST, TEMPLATE, SOURCE, Path(__file__).resolve(), receipt,
                   ROOT / 'tools/shared/test_direct.py', ROOT / 'tools/shared/default_stdlib.py',
                   ROOT / 'host/ghc/cbits/host.c', ROOT / 'runtime/mlf_process_supervisor.c',
                   ROOT / 'runtime/mlf_runtime.c', *sorted((ROOT / 'runtime').glob('*.h')),
                   Path(sys.executable).resolve(), Path(producer['ghc']['path']),
                   Path(producer['cc']['path']), Path(native['clang'])]
        sources += [Path(x) for x in native['link_args'] if Path(x).is_absolute()]
        record['inputs'] = {str(p): sha(p) for p in sources}
        flags = ['-XHaskell2010', '-fpedantic-bottoms', '-fno-state-hack',
                 '-Wno-star-is-type', '-Wno-deprecations', '-Wno-overlapping-patterns',
                 '-Werror=incomplete-patterns', '-Werror=incomplete-uni-patterns',
                 '-package-env', '-', '-clear-package-db', '-global-package-db',
                 '-no-user-package-db', '-hide-all-packages']
        for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
            flags += ['-package', package]
        for label, source in [('host', ROOT / 'host/ghc/cbits/host.c'),
                              ('supervisor', ROOT / 'runtime/mlf_process_supervisor.c')]:
            target = output / (label + '.o')
            runner.run('compile-' + label, [producer['cc']['path'], '-O2', '-std=c11',
                       '-I' + str(ROOT / 'runtime'), '-c', source, '-o', target])
            artifact(target)
        expected = (b'PASS JSON: 4705 strings at four suffix positions; 1112064 Unicode scalars; '
                    b'4 demand controls; independent literal report\n')
        for optimization in ['0', '2']:
            directory = output / ('host-O' + optimization)
            directory.mkdir()
            roots = [ROOT / name for name in ['host/ghc', 'bootstrap', 'package', 'testing', 'tests', 'tests/shared']]
            roots += sorted((ROOT / 'libraries').iterdir())
            runner.run('build-host-O' + optimization, [producer['ghc']['path'], '--make', '-j1',
                       '-O' + optimization, *flags, '-i', *['-i' + str(p) for p in roots if p.is_dir()],
                       '-odir', directory, '-hidir', directory, '-rtsopts=ignoreAll', HOST,
                       output / 'host.o', output / 'supervisor.o', '-o', directory / 'probe'], timeout=360)
            artifact(directory / 'probe')
            runner.run('host-O' + optimization, [directory / 'probe'], expected=expected, timeout=180)
        text = SOURCE.read_text()
        start = text.index('  data GroupResult =')
        end = text.index('  data QueryState =', start)
        boolean_start = text.index('  boolean :: Bool -> String;')
        boolean_end = text.index('  encodeKind ::', boolean_start)
        functions = text[boolean_start:boolean_end] + text[start:end]
        template = TEMPLATE.read_text()
        assert template.count('  -- INSERT_EXACT_QUERY_JSON_FUNCTIONS\n') == 1
        fixture = output / 'QueryJson.hs'
        fixture.write_text(template.replace('  -- INSERT_EXACT_QUERY_JSON_FUNCTIONS\n', functions))
        artifact(fixture)
        record['native_extraction'] = {'source': str(SOURCE), 'start_marker': '  data GroupResult =',
                                      'end_marker': '  data QueryState =',
                                      'dependency_markers': ['  boolean :: Bool -> String;', '  encodeKind ::'],
                                      'sha256': sha(SOURCE)}
        emitted = runner.run('emit-native', [build / 'bin/emlf', '-i', ROOT / 'libraries/mlf-foundation',
                             '--emit-llvm-gc', fixture], timeout=300)
        llvm = output / 'program.ll'
        llvm.write_bytes(emitted.stdout)
        artifact(llvm)
        # This literal is independent of both the compiler and quote().
        report = ('{"format":1,"crate":"crate","semantic_fingerprint":"sha",'
                  '"inferred_groups":1,"reused_groups":0,"groups":[{"id":"id\\u000a",'
                  '"members":["é","\\u0000"],"cached":false,"semantic_fingerprint":"hash",'
                  '"query_key":"key\\\\"}]}\n').encode()
        cases = [(mode, size) for mode in range(3) for size in [0,1,31,32,255,256,257,1024]] + [(3,0), (2,4096)]
        executions = 0
        for optimization in ['0', '2']:
            program = output / ('native-O' + optimization)
            runtime = output / ('runtime-O' + optimization + '.o')
            runner.run('compile-runtime-O' + optimization, [native['clang'], '-O' + optimization,
                       '-std=c11', *native['runtime_flags'], '-I' + str(ROOT / 'runtime'),
                       '-c', ROOT / 'runtime/mlf_runtime.c', '-o', runtime], timeout=180)
            artifact(runtime)
            runner.run('link-native-O' + optimization, [native['clang'], '-O' + optimization,
                       '-Wno-override-module', llvm, runtime, *native['link_args'], '-lpthread', '-ldl',
                       '-o', program], timeout=180)
            artifact(program)
            for mode, count in cases:
                value = sample(mode, count)
                for position in [-1, len(value) // 2]:
                    wanted = value if position < 0 else value[position:]
                    expected_bytes = (quote(wanted) + '\n').encode()
                    assert json.loads(expected_bytes) == wanted
                    runner.run(f'native-O{optimization}-{mode}-{count}-{position}',
                               [program, mode, count, position], expected=expected_bytes, timeout=30)
                    executions += 1
            runner.run('report-O' + optimization, [program, 'report'], expected=report, timeout=30)
            executions += 1
            for mode, message in [('position','position-first'),('value','value'),('bounds','string index out of bounds')]:
                result = runner.run('error-O' + optimization + '-' + mode, [program, mode],
                                    status=1, expected=b'', timeout=30)
                assert result.stderr == ('Runtime: ' + message + '\n').encode(), result.stderr
                executions += 1
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            if sha(path) != digest:
                raise ValueError('input or artifact changed: ' + path)
        authenticate_build(receipt, build / 'bin')
        record.update(complete=True, host_optimizations=['0','2'], strings_per_host=4705,
                      scalars_per_host=1112064, host_demand_controls=4, native_executions=executions)
        print(f'PASS query JSON: 4705 strings, 1112064 scalars and 4 demand controls at O0/O2; {executions} native executions')
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
