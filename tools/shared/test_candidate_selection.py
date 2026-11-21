#!/usr/bin/env python3
"""Verify actual candidate selection and its exact portable implementation."""
from pathlib import Path
import argparse
import json
import sys

from default_stdlib import configuration
from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'libraries/mlf-inference/Bootstrap/Classes.hs'
HOST = ROOT / 'tools/shared/fixtures/CandidateSelectionControls.hs'


def expected(n, period, indices):
    selected = set(indices)
    names = [i % period if period else i for i in range(n) if i in selected]
    return (''.join(f'i:n{i};' for i in names) + 's:super;g:given;i:n0;i:n0;\n').encode()


def vectors():
    result = [(n, 0, indices) for n in [0, 1, 2, 7]
              for indices in [[], [-1, n], [0, 0, 1, n - 1]]]
    result += [(n, 7, indices) for n in [63, 64, 65, 127, 128, 255, 256, 257, 1024]
               for indices in [[0, n - 1], [-1, n, n + 1], list(range(0, n, 7))]]
    result += [(4096, 7, [0, 63, 64, 65, 255, 256, 4095]),
               (65536, 7, []), (65536, 7, [0, 65535]),
               (65536, 7, [-(2**63), -1, 2**63 - 1]),
               (131072, 7, [0, 131071])]
    result += [(n, 7, ids) for n in [63,64,65,127,128,255,256,257,1024]
               for ids in [list(range(n)), [-1, *range(n), n, 2**63 - 1]]]
    return result


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
              'scope': 'actual host Classes API; exact source bodies isolated for portable backend controls',
              'native_self_bootstrap_qualified': False}

    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    runner = CommandRunner(ROOT, output, record, save)
    try:
        producer = authenticate_build(receipt, build / 'bin')
        native = configuration(args.clang)
        record['native_configuration'] = native
        inputs = [receipt, SOURCE, HOST, Path(__file__).resolve(),
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
        runner.run('host-controls', [host], expected=b'PASS candidate selection: 8254 cases and 2 demand checks\nPASS candidate IDs: 12369 cases and 5 demand checks\n', timeout=180)
        source = SOURCE.read_text()
        body = source[source.index('  selectCandidates ::'):source.index('  methodBindings ::')]
        if body.count('  selectCandidateOrdinals ordinal names indices supers =') != 1:
            raise ValueError('selector extraction boundary changed')
        fixture = output / 'CandidateSelection.hs'
        fixture.write_text('''-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.IntSet as I;
''' + body + '''
  readIndices position count = if count == 0 then ioReturn [] else do {
    value <- getArg position; rest <- readIndices (position + 1) (count - 1);
    ioReturn ((:) (readInt value) rest)
  };
  role value = case value of { InstanceEvidence -> "i"; SuperclassEvidence -> "s"; GivenEvidence -> "g" };
  main = do {
    selector <- getArg 0;
    size <- getArg 1; modulus <- getArg 2; count <- getArg 3;
    indices <- readIndices 4 (readInt count);
    let { period = readInt modulus;
      names = S.map (\\i -> "n" ++ showInt (if period == 0 then i else i % period)) (S.range 0 (readInt size - 1));
      supers = [(,) SuperclassEvidence "super", (,) GivenEvidence "given", (,) InstanceEvidence "n0", (,) InstanceEvidence "n0"] };
    putStrLn (S.concatMapString (\\((,) r n) -> role r ++ ":" ++ n ++ ";")
      ((if eqString selector "ids"
        then selectCandidateValues (S.map ((,) InstanceEvidence) names) supers
        else selectCandidates names supers) (I.fromList indices)))
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
        record['vector_counts'] = {}
        for lane, command in lanes.items():
            cases = vectors()[:12] if lane == 'interpreter' else vectors()
            for selector in ['named', 'ids']:
                for index, (n, period, indices) in enumerate(cases):
                    arguments = [selector, *map(str, [n, period, len(indices), *indices])]
                    result = runner.run(f'{lane}-{selector}-{index}', [*command, *arguments],
                                        expected=expected(n, period, indices), timeout=120)
                    if result.stderr:
                        raise ValueError('unexpected diagnostic: ' + lane)
            record['vector_counts'][lane] = 2 * len(cases)
        for p in [host, fixture, llvm, runtime, *[Path(c[0]) for k, c in lanes.items() if k.startswith('native')]]:
            record['artifacts'][str(p)] = sha(p)
        for path, digest in record['inputs'].items():
            if sha(path) != digest:
                raise ValueError('input changed: ' + path)
        authenticate_build(receipt, build / 'bin')
        record['complete'] = True
        print('PASS candidate selection: ' + json.dumps(record['vector_counts'], sort_keys=True))
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
