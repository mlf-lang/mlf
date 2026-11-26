#!/usr/bin/env python3
"""Check actual declaration-name APIs and the imported portable c1 codec."""
from pathlib import Path
import argparse
import json
import sys

from default_stdlib import configuration
from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'libraries/mlf-crates/Bootstrap/Separate.hs'
CODEC = ROOT / 'libraries/mlf-foundation/Bootstrap/NameEncoding.hs'
HOST = ROOT / 'tools/shared/fixtures/OwnerEncodingControls.hs'


def expected(value):
    return (''.join(c if c.isascii() and c.isalnum() and c != 'z' else
                    'zz' if c == 'z' else 'z' + format(ord(c), 'x') + 'z'
                    for c in value) + '\n').encode()


def long_ascii_vectors():
    return [(['text', 'a' * n], 'a' * n) for n in [255, 256, 257, 4096, 65536]]


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
              'scope': 'actual host identity/owner APIs; production NameEncoding module imported by interpreter/native tests',
              'native_self_bootstrap_qualified': False, 'native_toolchain_closure_complete': False}
    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    runner = CommandRunner(ROOT, output, record, save)
    try:
        producer = authenticate_build(receipt, build / 'bin')
        native = configuration(args.clang)
        record['native_configuration'] = native
        inputs = [receipt, SOURCE, CODEC, HOST, Path(__file__).resolve(),
                  ROOT / 'tools/shared/test_direct.py', ROOT / 'tools/shared/default_stdlib.py',
                  ROOT / 'runtime/mlf_runtime.c', *sorted((ROOT / 'runtime').glob('*.h')),
                  Path(native['clang']), Path(sys.executable).resolve(), build / 'host.o', build / 'supervisor.o']
        inputs += [Path(p) for p in native['link_args'] if Path(p).is_absolute()]
        record['inputs'] = {str(p): sha(p) for p in inputs}
        flags = ['-O2', '-fpedantic-bottoms', '-fno-state-hack', '-dcore-lint',
                 '-package-env', '-', '-clear-package-db', '-global-package-db', '-no-user-package-db', '-hide-all-packages']
        for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
            flags += ['-package', package]
        objects = [build / p for p in sorted(producer['object_inputs']) if p.endswith('.o') and p != 'objects/Main.o']
        runner.run('host-compile', [producer['ghc']['path'], '-c', *flags, '-i', '-i' + str(build / 'objects'),
                   HOST, '-o', output / 'Main.o', '-ohi', output / 'Main.hi'])
        host = output / 'host-controls'
        runner.run('host-link', [producer['ghc']['path'], *flags, '-rtsopts=ignoreAll', output / 'Main.o',
                   *objects, build / 'host.o', build / 'supervisor.o', '-o', host])
        runner.run('host-controls', [host], timeout=180)
        # Import the production module through its public codec API. Internal
        # helper names, their order and source formatting are not test inputs.
        fixture = output / 'Codec.hs'
        fixture.write_text('''-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.NameEncoding as Encoding;
  codes a b = if a > b then [] else (:) (stringFromCode a) (codes (a + 1) b);
  main = do {
    mode <- getArg 0; arg <- getArg 1;
    if eqString mode "range" then do {
      end <- getArg 2; putStrLn (Encoding.compactName (concatStringList (codes (readInt arg) (readInt end))))
    } else if eqString mode "repeat" then
      putStrLn (Encoding.compactName (concatStringList (S.replicate (readInt arg) "a:z_λ😀")))
    else putStrLn (Encoding.compactName arg)
  }
}
''')
        emitted = runner.run('emit-native', [build / 'bin/emlf', '-i', ROOT / 'libraries/mlf-foundation',
                             '--emit-llvm-gc', fixture], timeout=240)
        llvm = output / 'program.ll'; llvm.write_bytes(emitted.stdout)
        runtime = output / 'runtime.o'
        runner.run('runtime', [native['clang'], '-O2', '-std=c11', *native['runtime_flags'],
                   '-I' + str(ROOT / 'runtime'), '-c', ROOT / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
        lanes = {'interpreter': [build / 'bin/emlf', '-i', ROOT / 'libraries/mlf-foundation', '--run', fixture, '--']}
        for optimization in ['0', '2']:
            binary = output / ('native-O' + optimization)
            runner.run('native-link-O' + optimization, [native['clang'], '-O' + optimization,
                       '-Wno-override-module', llvm, runtime, *native['link_args'], '-lpthread', '-ldl', '-o', binary], timeout=120)
            lanes['native-O' + optimization] = [binary]
        vectors = [(['text', s], s) for s in ['', 'abcAZ09', 'zz', 'z0z', 'z3az', 'a_b', ':/_- .', 'λ😀', '模块', 'a\nb']]
        vectors += [(['range', str(a), str(b)], ''.join(map(chr, range(a, b + 1))))
                    for a, b in [(0, 127), (128, 255), (2046, 2050), (55294, 55295),
                                 (57344, 57346), (65534, 65538), (1114109, 1114111)]]
        vectors += [(['repeat', str(n)], 'a:z_λ😀' * n) for n in [0, 1, 16, 1024, 12000]]
        vectors += long_ascii_vectors()
        vectors += [(['text', s], s) for n in [255, 256, 257] for s in ['a' * n + 'z/λ😀' + 'b' * n]]
        record['vector_counts'] = {}
        for lane, command in lanes.items():
            count = 0
            for index, (arguments, value) in enumerate(vectors):
                if lane == 'interpreter' and index > 19:
                    continue
                result = runner.run(f'{lane}-{index}', [*command, *arguments], expected=expected(value), timeout=120)
                if result.stderr:
                    raise ValueError('unexpected diagnostic: ' + lane)
                count += 1
            record['vector_counts'][lane] = count
        for p in [host, fixture, llvm, runtime, *[Path(c[0]) for k, c in lanes.items() if k.startswith('native')]]:
            record['artifacts'][str(p)] = sha(p)
        for path, digest in record['inputs'].items():
            if sha(path) != digest:
                raise ValueError('input changed: ' + path)
        authenticate_build(receipt, build / 'bin')
        record['complete'] = True
        print('PASS compact names: ' + json.dumps(record['vector_counts'], sort_keys=True))
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
