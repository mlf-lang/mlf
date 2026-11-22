#!/usr/bin/env python3
"""Check bulk CRC against zlib across the host, interpreter and native runtime."""
from __future__ import annotations

import argparse
import json
import hashlib
import random
import zlib
from pathlib import Path
import shutil
import sys

from default_stdlib import configuration
from test_direct import CommandRunner, authenticate_build, sha, verify_file

ROOT = Path(__file__).resolve().parents[2]
HOST = NATIVE = ROOT / 'tools/shared/fixtures/ByteArrayCRC32.hs'


SIZES = [0, 1, 2, 3, 4, 76, 77, 79, 80, 81, 255, 256, 1023, 1024, 16383, 16384, 65536, 1048583]


def expected(data, start, count):
    def crc(value):
        return zlib.crc32(value[:start] + bytes(count) + value[start + count:])
    changed = bytes([data[0] ^ 255]) + data[1:] if data else data
    return f'{crc(data)},{crc(changed)},{hashlib.sha256(changed).hexdigest()}\n'.encode()


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
              'scope': 'GHC host, interpreter and generated native bulk CRC; independent finite checksum and IO demand controls',
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
        inputs = [HOST, NATIVE, Path(__file__).resolve(),
                  ROOT / 'tools/shared/test_direct.py', ROOT / 'tools/shared/default_stdlib.py',
                  build_receipt, Path(sys.executable).resolve(), Path(native['clang']),
                  Path(producer['cc']['path']), ROOT / 'host/ghc/cbits/host.c',
                  ROOT / 'runtime/mlf_process_supervisor.c',
                  Path(shutil.which('pkg-config')).resolve(), ROOT / 'runtime/mlf_runtime.c',
                  *sorted((ROOT / 'runtime').glob('*.h'))]
        inputs += [Path(arg) for arg in native['link_args'] if Path(arg).is_absolute()]
        record['inputs'].update({str(path): sha(path) for path in inputs})
        flags = ['-O' + producer['optimization'], '-fpedantic-bottoms', '-fno-state-hack',
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
        # Prepare one checked interpreter target. The CRC and demand cases
        # still execute in fresh processes without repeating source compilation.
        interpreted = runner.run('emit-interpreter', [build / 'bin/emlf', '-i',
                                 ROOT / 'libraries/mlf-foundation', NATIVE], timeout=240)
        xmlf = output / 'program.xmlf'
        xmlf.write_bytes(interpreted.stdout)
        artifact(xmlf)
        lanes = {'host': [output / 'host-controls'], 'native': [output / 'native-controls'],
                 'interpreter': [build / 'bin/emlf', '--run-xmlf', xmlf, '--']}
        rng = random.Random(88513)
        record['vector_counts'] = {lane: 0 for lane in lanes}
        for size in SIZES:
            data = bytes(rng.randrange(256) for _ in range(size))
            path = output / ('bytes-' + str(size)); path.write_bytes(data); artifact(path)
            ranges = sorted({(0, 0), (0, size), (size, 0), (size // 2, size - size // 2),
                             (min(76, size), min(4, max(0, size - 76)))})
            for index, (start, count) in enumerate(ranges):
                for lane, argv in lanes.items():
                    # Preserve the reviewed finite interpreter vector subset.
                    if lane == 'interpreter' and (size not in [0, 1, 80, 1024, 16384] or index not in [0, len(ranges)-1]):
                        continue
                    runner.run(f'{lane}-{size}-{index}', [*argv, 'crc', path, start, count],
                               expected=expected(data, start, count), timeout=90)
                    record['vector_counts'][lane] += 1
        diagnostics = [('array', 'array-demand'), ('start', 'start-demand'),
                       ('bad-start', 'invalid CRC zero range'), ('count', 'count-demand'),
                       ('negative-start', 'invalid CRC zero range'),
                       ('negative-count', 'invalid CRC zero range'), ('overflow-count', 'invalid CRC zero range')]
        for lane, argv in lanes.items():
            runner.run(lane + '-defer', [*argv, 'defer'], expected=b'deferred\n', timeout=90)
            for mode, message in diagnostics:
                result = runner.run(lane + '-' + mode, [*argv, mode], status=1, expected=b'', timeout=90)
                errors = result.stderr.decode()
                if message not in errors or any(other in errors for other in
                        ['array-demand', 'start-demand', 'count-demand'] if other != message):
                    raise ValueError('incorrect IO demand or bounds diagnostic: ' + lane + '/' + mode)
        record['demand_checks_per_lane'] = 8
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            if sha(path) != digest:
                raise ValueError('input or artifact changed: ' + path)
        authenticate_build(build_receipt, build / 'bin')
        record['complete'] = True
        print('PASS bulk CRC: ' + json.dumps(record['vector_counts'], sort_keys=True) +
              '; 8 demand/bounds checks per backend')
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
