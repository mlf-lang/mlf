#!/usr/bin/env python3
"""Check actual owned symbol writers against independent UTF-8/varint bytes."""
from pathlib import Path
import argparse
import hashlib
import json
import re

from default_stdlib import configuration
from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]


def vectors():
    pairs = [(0, 0, 0, 0), (0, 1, 0, 127), (0, 127, 0, 128),
             (0, 128, 0, 16383), (0, 16383, 0, 16384),
             (1, 42, 1, 43), (1, 5461, 1, 5462),
             (2, 31, 2, 32), (2, 4095, 2, 4096),
             (3, 127, 3, 128), (1, 0, 0, 128), (3, 7, 2, 8)]
    return [(mode, start, *pair) for mode in ['sizes', 'full']
            for start in [0, 7] for pair in pairs]


def expected(case):
    mode, start, kind, count, other, more = case
    units = ['a', '中', '😀', '\0']
    first = (units[kind] * count).encode('utf-8')
    second = (units[other] * more).encode('utf-8')
    result = bytearray([211] * start)
    for value in [first, b'', second, first]:
        size = len(value)
        while size >= 128:
            size, digit = divmod(size, 128)
            result.append(digit + 128)
        result.append(size)
        result.extend(value if mode == 'full' else bytes([211]) * len(value))
    end = len(result) * 8
    result.extend([211, 211])
    return f'{end}\n{hashlib.sha256(result).hexdigest()}\n'.encode()


def extract(text):
    ranges = [('  putBits ::', '  putText ::'),
              ('  packedBits bytes', '  packedRefs bytes'),
              ('  putOwnedSymbolSizes bytes position symbols =', '  data Cursor')]
    parts = []
    for start, end in ranges:
        starts = list(re.finditer('^' + re.escape(start), text, re.M))
        ends = list(re.finditer('^' + re.escape(end), text, re.M))
        if len(starts) != 1 or len(ends) != 1 or starts[0].start() >= ends[0].start():
            raise ValueError('symbol writer extraction boundary changed')
        parts.append(text[starts[0].start():ends[0].start()])
    return '\n'.join(parts)


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
              'scope': 'actual owned symbol writers, finite interpreter/native O0/O2 controls',
              'native_compiler_self_bootstrap_qualified': False}

    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    runner = CommandRunner(ROOT, output, record, save)
    try:
        authenticate_build(receipt, build / 'bin')
        native = configuration(args.clang)
        record['native_configuration'] = native
        source = ROOT / 'libraries/mlf-crates/Bootstrap/Bitstream.hs'
        template = ROOT / 'tools/shared/fixtures/SymbolPrefixNative.hs.txt'
        inputs = [receipt, source, template, Path(__file__).resolve(),
                  ROOT / 'tools/shared/test_direct.py', ROOT / 'tools/shared/default_stdlib.py',
                  ROOT / 'runtime/mlf_runtime.c', *sorted((ROOT / 'runtime').glob('*.h')),
                  Path(native['clang']), build / 'bin/emlf']
        inputs += [Path(p) for p in native['link_args'] if Path(p).is_absolute()]
        record['inputs'] = {str(p): sha(p) for p in inputs}
        body = template.read_text()
        if body.count('  -- INSERT_ACTUAL_SYMBOL_WRITERS') != 1:
            raise ValueError('symbol fixture insertion boundary changed')
        portable = output / 'SymbolNative.hs'
        portable.write_text(body.replace('  -- INSERT_ACTUAL_SYMBOL_WRITERS', extract(source.read_text())))
        include = ['-i', ROOT / 'libraries/mlf-foundation']
        emitted = runner.run('emit-native', [build / 'bin/emlf', *include,
                             '--emit-llvm-gc', portable], timeout=300)
        llvm = output / 'program.ll'; llvm.write_bytes(emitted.stdout)
        lanes = {'interpreter': [build / 'bin/emlf', *include, '--run', portable, '--']}
        for optimization in ['0', '2']:
            runtime = output / ('runtime-O' + optimization + '.o')
            binary = output / ('native-O' + optimization)
            runner.run('runtime-O' + optimization, [native['clang'], '-O' + optimization,
                       '-std=c11', *native['runtime_flags'], '-I' + str(ROOT / 'runtime'),
                       '-c', ROOT / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
            runner.run('link-native-O' + optimization, [native['clang'], '-O' + optimization,
                       '-Wno-override-module', llvm, runtime, *native['link_args'],
                       '-lpthread', '-ldl', '-o', binary], timeout=120)
            lanes['native-O' + optimization] = [binary]
        record['vector_counts'] = {}
        for lane, argv in lanes.items():
            count = 0
            for index, case in enumerate(vectors()):
                if lane == 'interpreter' and (case[1] != 7 or max(case[3], case[5]) > 128):
                    continue
                runner.run(lane + '-' + str(index), [*argv, *case], expected=expected(case), timeout=180)
                count += 1
            record['vector_counts'][lane] = count
        assert record['vector_counts'] == {'interpreter': 16, 'native-O0': 48, 'native-O2': 48}
        for path in [portable, llvm, *[output / (prefix + opt + suffix) for opt in ['0', '2']
                                     for prefix, suffix in [('native-O', ''), ('runtime-O', '.o')]]]:
            record['artifacts'][str(path)] = sha(path)
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            if sha(path) != digest:
                raise ValueError('input or artifact changed: ' + path)
        authenticate_build(receipt, build / 'bin')
        record['complete'] = True
        print('PASS symbol prefixes: ' + json.dumps(record['vector_counts'], sort_keys=True))
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
