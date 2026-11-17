#!/usr/bin/env python3
"""Check byte-copy ownership, exact slice lengths, GC lifetime and IO demand."""
from pathlib import Path
import argparse
import json

from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    receipt = args.build_receipt.resolve(strict=True)
    build, output = receipt.parent, args.output.resolve()
    if output == ROOT or ROOT.is_relative_to(output) or output.is_relative_to(build):
        parser.error('independent output directory required')
    output.mkdir(parents=True, exist_ok=False)
    record = {'complete': False, 'commands': [], 'inputs': {}, 'artifacts': {},
              'scope': 'GHC host byte copies; actual adapter plus a GC-injected copy',
              'native_compiler_self_bootstrap_qualified': False}

    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        producer = authenticate_build(receipt, build / 'bin')
        source = ROOT / 'host/ghc/MLF/Host/IO.hs'
        fixture = ROOT / 'tools/shared/fixtures/ByteArrayCopy.hs'
        inputs = [receipt, source, fixture, Path(__file__).resolve(),
                  ROOT / 'tools/shared/test_direct.py',
                  build / 'host.o', build / 'supervisor.o']
        inputs += [build / name for name in producer['object_inputs']]
        record['inputs'] = {str(path): sha(path) for path in inputs}
        text = source.read_text()
        module = 'module MLF.Host.IO where'
        injection = '  storage <- newByteStorage size\n  if size == 0'
        if text.count(module) != 1 or text.count(injection) != 1:
            raise ValueError('byte-copy extraction boundary changed')
        gc_source = output / 'CopyGC.hs'
        gc_source.write_text(text.replace(module, 'module CopyGC where', 1)
            .replace('import Prelude hiding (Int, String)',
                     'import Prelude hiding (Int, String)\nimport System.Mem (performGC)', 1)
            .replace(injection, '  storage <- newByteStorage size\n  performGC\n  if size == 0', 1))
        flags = ['-O' + producer['optimization'], '-fpedantic-bottoms', '-fno-state-hack',
                 '-dcore-lint', '-package-env', '-', '-clear-package-db',
                 '-global-package-db', '-no-user-package-db', '-hide-all-packages']
        for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
            flags += ['-package', package]
        for label, path in [('CopyGC', gc_source), ('Main', fixture)]:
            # The copied host module includes the existing deprecated
            # ByteString.hGetLine adapter, outside this byte-copy change.
            warning_flags = ['-Wno-deprecations'] if label == 'CopyGC' else []
            runner.run('compile-' + label, [producer['ghc']['path'], '-c', *flags, *warning_flags,
                       '-i', '-i' + str(output), '-i' + str(build / 'objects'), path,
                       '-o', output / (label + '.o'), '-ohi', output / (label + '.hi')])
        objects = [build / name for name in sorted(producer['object_inputs'])
                   if name.endswith('.o') and name != 'objects/Main.o']
        runner.run('link', [producer['ghc']['path'], *flags, '-rtsopts=ignoreAll',
                   output / 'Main.o', output / 'CopyGC.o', *objects,
                   build / 'host.o', build / 'supervisor.o', '-o', output / 'controls'])
        runner.run('ownership-GC-demand', [output / 'controls'], expected=(
            b'PASS byte copies: 128 sliced ownership/GC cases, 8 UTF-8 vectors, 3 transient-owner cases, 4 demand comparisons\n'), timeout=180)
        record['vector_counts'] = {'slice_ownership_gc': 128, 'utf8': 8,
                                   'transient_owner': 3, 'demand_comparisons': 4}
        record['artifacts'] = {str(path): sha(path) for path in [gc_source, output / 'controls']}
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            if sha(path) != digest:
                raise ValueError('input or artifact changed: ' + path)
        authenticate_build(receipt, build / 'bin')
        record['complete'] = True
        print('PASS byte-copy ownership, GC lifetime, UTF-8 and IO demand')
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
