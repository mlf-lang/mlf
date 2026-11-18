#!/usr/bin/env python3
"""Check exact lowered-syntax reuse and portable IEEE equality policies."""
from pathlib import Path
import argparse
import json
import struct

from default_stdlib import configuration
from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]


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
    record = {'complete': False, 'commands': [], 'inputs': {}, 'artifacts': {},
              'scope': 'actual host prepared-cache API; actual shared equality source under interpreter and native O0/O2',
              'native_compiler_self_bootstrap_qualified': False}

    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    runner = CommandRunner(ROOT, output, record, save)
    try:
        producer = authenticate_build(receipt, build / 'bin')
        native = configuration(args.clang)
        record['native_configuration'] = native
        corpus = ROOT / 'tools/shared/fixtures/item4/QueryEncoding.hs'
        host = ROOT / 'tools/shared/fixtures/PreparedSyntaxControls.hs'
        portable = ROOT / 'tools/shared/fixtures/PreparedEqualityNative.hs'
        sources = [receipt, corpus, host, portable, Path(__file__).resolve(),
                   ROOT / 'libraries/mlf-crates/Bootstrap/CrateGraph.hs',
                   ROOT / 'libraries/mlf-crates/Bootstrap/SourceEquality.hs',
                   ROOT / 'tools/shared/test_direct.py', ROOT / 'tools/shared/default_stdlib.py',
                   ROOT / 'runtime/mlf_runtime.c', *sorted((ROOT / 'runtime').glob('*.h')),
                   Path(native['clang']), build / 'host.o', build / 'supervisor.o']
        sources += [Path(p) for p in native['link_args'] if Path(p).is_absolute()]
        record['inputs'] = {str(p): sha(p) for p in sources}
        copied = output / 'Corpus.hs'
        text = corpus.read_text()
        if text.count('module Main where') != 1:
            raise ValueError('query corpus module boundary changed')
        copied.write_text(text.replace('module Main where', 'module Corpus where'))
        flags = ['-O2', '-fpedantic-bottoms', '-fno-state-hack', '-dcore-lint', '-Wno-x-partial',
                 '-package-env', '-', '-clear-package-db', '-global-package-db', '-no-user-package-db', '-hide-all-packages']
        for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
            flags += ['-package', package]
        for label, source in [('Corpus', copied), ('Main', host)]:
            runner.run('compile-' + label, [producer['ghc']['path'], '-c', *flags, '-i',
                       '-i' + str(output), '-i' + str(build / 'objects'), source,
                       '-o', output / (label + '.o'), '-ohi', output / (label + '.hi')])
        objects = [build / p for p in sorted(producer['object_inputs']) if p.endswith('.o') and p != 'objects/Main.o']
        runner.run('host-link', [producer['ghc']['path'], *flags, '-rtsopts=ignoreAll',
                   output / 'Main.o', output / 'Corpus.o', *objects, build / 'host.o', build / 'supervisor.o',
                   '-o', output / 'host-controls'])
        runner.run('host-controls', [output / 'host-controls'],
                   expected=b'Prepared syntax controls: 9910 checks; 53 syntax variants\n')
        include = ['-i', ROOT / 'libraries/mlf-foundation', '-i', ROOT / 'libraries/mlf-crates',
                   '-i', ROOT / 'libraries/mlf-language-core']
        emitted = runner.run('emit-native', [build / 'bin/emlf', *include, '--emit-llvm-gc', portable], timeout=300)
        llvm = output / 'program.ll'; llvm.write_bytes(emitted.stdout)
        runtime = output / 'runtime.o'
        runner.run('runtime', [native['clang'], '-O2', '-std=c11', *native['runtime_flags'],
                   '-I' + str(ROOT / 'runtime'), '-c', ROOT / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
        lanes = {'interpreter': [build / 'bin/emlf', *include, '--run', portable, '--']}
        for optimization in ['0', '2']:
            binary = output / ('native-O' + optimization)
            runner.run('link-native-O' + optimization, [native['clang'], '-O' + optimization,
                       '-Wno-override-module', llvm, runtime, *native['link_args'], '-lpthread', '-ldl', '-o', binary], timeout=120)
            lanes['native-O' + optimization] = [binary]
        pairs = [(0, 0), (0, -(2**63)), (9221120237041090561, 9221120237041090561),
                 (9221120237041090561, 9221120237041090562), (9218868437227405312, 9218868437227405312)]
        record['vector_counts'] = {}
        for lane, command in lanes.items():
            modes = [0, 6, 13, 15, 17] if lane == 'interpreter' else range(18)
            count = 0
            for mode in modes:
                for index, (first, second) in enumerate(pairs):
                    number = lambda bits: struct.unpack('>d', struct.pack('>q', bits))[0]
                    expected = (str(int(first == second)) + str(int(number(first) == number(second))) + '\n').encode()
                    runner.run(f'{lane}-{mode}-{index}', [*command, mode, first, second], expected=expected, timeout=180)
                    count += 1
            record['vector_counts'][lane] = count
        for path in [copied, output / 'host-controls', llvm, runtime, output / 'native-O0', output / 'native-O2']:
            record['artifacts'][str(path)] = sha(path)
        for path, digest in record['inputs'].items():
            if sha(path) != digest:
                raise ValueError('input changed: ' + path)
        authenticate_build(receipt, build / 'bin')
        record['complete'] = True
        print('PASS prepared syntax: 9910 host checks; ' + json.dumps(record['vector_counts'], sort_keys=True))
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
