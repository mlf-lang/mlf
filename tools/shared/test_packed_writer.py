#!/usr/bin/env python3
"""Check the actual private packed writers against independent arithmetic."""
from pathlib import Path
import argparse
import json
import re

from default_stdlib import configuration
from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]


def vectors():
    cases = []
    patterns = [0, 1, -1, -(2**63), 0x55AA55AA55AA55AA]
    for used in range(8):
        pending = 2**used - 1
        cases += [('byte', used, pending, 8, value) for value in [0, 127, 128, 255]]
        cases += [('bits', used, pending, width, patterns[(used + width) % len(patterns)])
                  for width in [0, 1, 2, 7, 8, 9, 15, 16, 31, 32, 55, 56, 57, 63, 64]]
        cases += [('var', used, pending, 0, value)
                  for value in [0, 1, 127, 128, 16383, 16384, 2**63 - 1, -1, -(2**63)]]
    assert len(cases) == 224
    return cases


def expected(case):
    mode, used, pending, width, value = case
    bits = value % 2**64
    if mode == 'byte':
        width = 8
    elif mode == 'var':
        digits = []
        while bits >= 128:
            bits, digit = divmod(bits, 128)
            digits.append(digit + 128)
        digits.append(bits)
        bits = sum(digit * 256**i for i, digit in enumerate(digits))
        width = 8 * len(digits)
    total = pending + (bits % 2**width) * 2**used
    count, remaining = divmod(used + width, 8)
    carry = total // 256**count
    cells = [211] * 16
    for i in range(count):
        cells[i + 1] = (total // 256**i) % 256
    if remaining:
        cells[count + 1] = carry
    return ''.join(str(x) + '\n' for x in
                   [1 + count, remaining, carry, (1 + count) * 8 + remaining, *cells]).encode()


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
              'scope': 'actual packed writer source, finite host/interpreter/native O0/O2 checks',
              'native_compiler_self_bootstrap_qualified': False}

    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    runner = CommandRunner(ROOT, output, record, save)
    try:
        producer = authenticate_build(receipt, build / 'bin')
        native = configuration(args.clang)
        record['native_configuration'] = native
        source = ROOT / 'libraries/mlf-crates/Bootstrap/Bitstream.hs'
        fixture = ROOT / 'tools/shared/fixtures/PackedByteControls.hs'
        fields_fixture = ROOT / 'tools/shared/fixtures/PackedFieldControls.hs'
        template = ROOT / 'tools/shared/fixtures/PackedWriterNative.hs.txt'
        inputs = [receipt, source, fixture, fields_fixture, template, Path(__file__).resolve(),
                  ROOT / 'tools/shared/test_direct.py', ROOT / 'tools/shared/default_stdlib.py',
                  ROOT / 'runtime/mlf_runtime.c', *sorted((ROOT / 'runtime').glob('*.h')),
                  Path(native['clang']), build / 'host.o', build / 'supervisor.o']
        inputs += [Path(p) for p in native['link_args'] if Path(p).is_absolute()]
        record['inputs'] = {str(p): sha(p) for p in inputs}
        text = source.read_text()
        candidate = output / 'CandidateWire.hs'
        renamed, count = re.subn(r'module Bootstrap.Bitstream\s*\(.*?\) where \{',
                                'module CandidateWire where {', text, count=1, flags=re.S)
        if count != 1:
            raise ValueError('codec module boundary changed')
        candidate.write_text(renamed)
        first = text[text.index('  packedBits ::'):text.index('  packedRefs ::')]
        last = text[text.index('  packedFinish bytes'):text.index('  encodeTables ::')]
        if first.count('  packedByte bytes') != 1 or first.count('  packedVar bytes') != 1:
            raise ValueError('packed writer extraction boundary changed')
        portable = output / 'PackedNative.hs'
        body = template.read_text()
        if body.count('  -- INSERT_ACTUAL_PACKED_WRITERS') != 1:
            raise ValueError('packed fixture insertion boundary changed')
        portable.write_text(body.replace('  -- INSERT_ACTUAL_PACKED_WRITERS', first + last))
        flags = ['-O2', '-fpedantic-bottoms', '-fno-state-hack', '-dcore-lint',
                 '-package-env', '-', '-clear-package-db', '-global-package-db',
                 '-no-user-package-db', '-hide-all-packages']
        for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
            flags += ['-package', package]
        for label, path in [('CandidateWire', candidate), ('Main', fixture)]:
            runner.run('compile-' + label, [producer['ghc']['path'], '-c', *flags, '-i',
                       '-i' + str(output), '-i' + str(build / 'objects'), path,
                       '-o', output / (label + '.o'), '-ohi', output / (label + '.hi')])
        objects = [build / p for p in sorted(producer['object_inputs'])
                   if p.endswith('.o') and p != 'objects/Main.o']
        runner.run('link-host', [producer['ghc']['path'], *flags, '-rtsopts=ignoreAll',
                   output / 'Main.o', output / 'CandidateWire.o', *objects,
                   build / 'host.o', build / 'supervisor.o', '-o', output / 'host-controls'])
        runner.run('host-controls', [output / 'host-controls'], expected=(
            b'PASS packed byte: 65280 states, independent arithmetic, general writer, sentinels and finish padding\n'))
        runner.run('compile-field-controls', [producer['ghc']['path'], '-c', *flags, '-i',
                   '-i' + str(output), '-i' + str(build / 'objects'), fields_fixture,
                   '-o', output / 'Fields.o', '-ohi', output / 'Fields.hi'])
        runner.run('link-field-controls', [producer['ghc']['path'], *flags, '-rtsopts=ignoreAll',
                   output / 'Fields.o', output / 'CandidateWire.o', *objects,
                   build / 'host.o', build / 'supervisor.o', '-o', output / 'field-controls'])
        runner.run('field-controls', [output / 'field-controls'], expected=(
            b'PASS packed fields: 10920 states, all widths 0..64, offsets, signed patterns, continuation and sentinels\n'))
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
                mode, used, pending, width, value = case
                selected = (mode == 'var' and value == -(2**63) or
                            mode == 'bits' and width in [56, 57] and used in [0, 7] or
                            mode == 'bits' and width == 64 and used in [0, 3, 6, 7] or
                            mode == 'byte' and used in [0, 1, 2, 3] and value == 128)
                if lane == 'interpreter' and not selected:
                    continue
                runner.run(lane + '-' + str(index), [*argv, *case], expected=expected(case), timeout=180)
                count += 1
            record['vector_counts'][lane] = count
        assert record['vector_counts'] == {'interpreter': 20, 'native-O0': 224, 'native-O2': 224}
        for path in [candidate, portable, llvm, output / 'host-controls', output / 'field-controls',
                     *[output / (prefix + opt + suffix) for opt in ['0', '2']
                       for prefix, suffix in [('native-O', ''), ('runtime-O', '.o')]]]:
            record['artifacts'][str(path)] = sha(path)
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            if sha(path) != digest:
                raise ValueError('input or artifact changed: ' + path)
        authenticate_build(receipt, build / 'bin')
        record['complete'] = True
        print('PASS packed writer: 65280 host states; ' + json.dumps(record['vector_counts'], sort_keys=True))
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
