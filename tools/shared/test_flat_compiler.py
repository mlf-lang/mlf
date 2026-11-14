#!/usr/bin/env python3
"""CLI regression controls for signed groups, demanded inputs and fixed Prelude linking.

Uses an authenticated producer; does not regenerate any independent oracle.
The performance benchmark and its native executable oracles remain separate.
"""
from pathlib import Path
import argparse
import json
import shutil

from test_direct import CommandRunner, authenticate_build, sha
from artifact_binary_reference import read_document
from query_generation import Generation

ROOT = Path(__file__).resolve().parents[2]
HEADER = ('-- mlf:syntax shared-haskell-v1\n'
          '{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, '
          'KindSignatures, FlexibleContexts, FlexibleInstances, '
          'MultiParamTypeClasses, OverloadedStrings #-}\n')


def pack(fields):
    return ''.join(str(len(field)) + ':' + field for field in fields)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', required=True, type=Path)
    parser.add_argument('--builtin', required=True, type=Path, help='existing builtin prefix')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    receipt = args.build_receipt.resolve(strict=True)
    producer = receipt.parent
    output = args.output.resolve()
    if output.is_relative_to(producer) or producer.is_relative_to(output):
        parser.error('output must be separate from the producer')
    authenticate_build(receipt, producer / 'bin')
    output.mkdir(parents=True, exist_ok=False)
    evidence = {'complete': False, 'producer_receipt': str(receipt),
                'producer_sha256': sha(receipt), 'driver_sha256': sha(__file__),
                'commands': [], 'checks': []}

    def save():
        (output / 'receipt.json').write_text(json.dumps(evidence, indent=2) + '\n')

    def check(name, condition):
        evidence['checks'].append({'name': name, 'passed': bool(condition)})
        save()
        if not condition:
            raise ValueError(name)

    save()
    runner = CommandRunner(ROOT, output, evidence, save)
    emlf = producer / 'bin/emlf'
    builtin = output / 'builtin'
    for suffix in ['.mlfci', '.mlfco']:
        source = Path(str(args.builtin) + suffix).resolve(strict=True)
        shutil.copyfile(source, Path(str(builtin) + suffix))
    good_builtin = Path(str(builtin) + '.mlfco').read_bytes()
    library = output / 'Lib.hs'
    consumer = output / 'Main.hs'
    lib_prefix, main_prefix = output / 'lib', output / 'main'

    def write_lib(offset=1, spare='spare :: Int; spare = 0;', result='Int'):
        rhs = 'True' if result == 'Bool' else 'addInt x ' + str(offset)
        library.write_text(HEADER + 'module Lib (inc, spare) where { import MLF.Primitive; '
                           'inc :: Int -> ' + result + '; inc x = ' + rhs + '; ' + spare + ' }\n')

    def write_main(offset=2):
        consumer.write_text(HEADER + 'module Main (main) where { import MLF.Primitive; import Lib; '
            'f0 :: Int -> Int; f0 x = inc x; f1 :: Int -> Int; f1 x = addInt x ' + str(offset) + '; '
            'main = printInt (addInt (f0 3) (f1 4)); }\n')

    def spec(module, source, dependencies, entry):
        cache = output / (module + '-cache')
        cache.mkdir(exist_ok=True)
        path = output / (module + '.spec')
        path.write_text(pack(['MLF-CRATE-1', 'flat-controls/' + module, entry, 'false',
            pack([pack([module, str(source)])]), pack([str(p) for p in dependencies]),
            str(cache), str(builtin)]))
        return path

    lib_spec = spec('Lib', library, [Path(str(builtin) + '.mlfci')], '')
    main_spec = spec('Main', consumer, [Path(str(lib_prefix) + '.mlfci')], 'Main')

    def compile(name, specification, prefix, status=0):
        runner.run(name, [emlf, '--compile-crate', specification, '-o', prefix],
                   status=status, timeout=120)
        if status == 0:
            return json.loads(Path(str(prefix) + '.queries').read_text())

    def run(name, prefix, expected):
        runner.run(name, [emlf, '--run-crate', Path(str(prefix) + '.mlfci')],
                   expected=expected.encode(), timeout=120)

    write_lib(); write_main()
    compile('library-cold', lib_spec, lib_prefix)
    cold = compile('consumer-cold', main_spec, main_prefix)
    count = cold['inferred_groups']
    check('cold consumer has four fresh groups', count == 4 and cold['reused_groups'] == 0)
    run('cold-value', main_prefix, '10\n')
    cold_bytes = [Path(str(main_prefix) + s).read_bytes() for s in ['.mlfci', '.mlfco']]
    warm = compile('consumer-warm', main_spec, main_prefix)
    check('warm consumer reuses every group', warm['inferred_groups'] == 0 and warm['reused_groups'] == count)
    check('cold and warm artifacts agree', cold_bytes ==
          [Path(str(main_prefix) + s).read_bytes() for s in ['.mlfci', '.mlfco']])
    graph = output / 'Main-cache/query-graph-v2'
    pointer = read_document((graph / 'CURRENT').read_bytes(), 6).values()
    check('one generation pointer', len(pointer) == 1 and pointer[0][0] == 'text')
    address = pointer[0][1]
    generation = Generation((graph / 'generations' / (address + '.mlfqg')).read_bytes(),
                            expected_hash=address)
    payloads = [(key, node['payload']) for key, node in generation.nodes.items()
                if node['payload'] is not None]
    check('only reloadable query values have payload files', bool(payloads) and
          all(key.startswith(('8:InferScc', '8:Evidence')) for key, _ in payloads))
    victim = next(digest for key, digest in payloads if key.startswith('8:InferScc'))
    payload = graph / 'results' / (victim + '.mlfqr')
    corrupt_raw = bytearray(payload.read_bytes()); corrupt_raw[-1] ^= 1
    payload.write_bytes(corrupt_raw)
    repaired = compile('consumer-corrupt-query-repaired', main_spec, main_prefix)
    check('corrupt inference payload rechecks exactly its group',
          repaired['inferred_groups'] == 1 and repaired['reused_groups'] == count - 1)
    check('repaired inference payload restores its content address', sha(payload) == victim)
    run('repaired-query-value', main_prefix, '10\n')
    write_lib(2)
    compile('library-body-change', lib_spec, lib_prefix)
    changed = compile('consumer-after-library-body', main_spec, main_prefix)
    check('library body change preserves inference reuse', changed['inferred_groups'] == 0)
    run('changed-library-value', main_prefix, '11\n')
    write_lib(2, 'spare :: Bool; spare = True;')
    compile('library-unused-type-change', lib_spec, lib_prefix)
    unused = compile('consumer-after-unused-type', main_spec, main_prefix)
    check('unobserved import type preserves reuse', unused['inferred_groups'] == 0)
    run('unused-type-value', main_prefix, '11\n')
    write_main(3)
    edited = compile('consumer-one-body-change', main_spec, main_prefix)
    check('one body edit infers one group', edited['inferred_groups'] == 1 and edited['reused_groups'] == count - 1)
    run('changed-consumer-value', main_prefix, '12\n')
    current = output / 'Main-cache/query-graph-v2/CURRENT'
    prior = current.read_bytes()
    write_lib(result='Bool')
    compile('library-used-type-change', lib_spec, lib_prefix)
    compile('consumer-rejects-used-type-change', main_spec, main_prefix, status=1)
    check('failed recheck does not publish a generation', current.read_bytes() == prior)
    write_lib(2)
    compile('library-restored', lib_spec, lib_prefix)
    restored = compile('consumer-restored', main_spec, main_prefix)
    check('restored contracts reuse the previous good generation', restored['inferred_groups'] == 0)
    run('restored-value', main_prefix, '12\n')
    # A fixed-literal hit must authenticate the physical object, not just its
    # filename, interface or declared fingerprint.
    bad = bytearray(good_builtin); bad[len(bad) // 2] ^= 1
    Path(str(builtin) + '.mlfco').write_bytes(bad)
    corrupt = runner.run('corrupt-builtin-rejected', [emlf, '--crate-to-llvm-gc', str(main_prefix) + '.mlfci'],
                         status=1, timeout=120)
    check('corrupt builtin fails physical admission', b'binary checksum mismatch' in corrupt.stderr)
    Path(str(builtin) + '.mlfco').write_bytes(good_builtin + b'\0')
    trailing = runner.run('trailing-builtin-rejected', [emlf, '--crate-to-llvm-gc', str(main_prefix) + '.mlfci'],
                          status=1, timeout=120)
    check('trailing builtin bytes fail physical admission', b'binary file/header length mismatch' in trailing.stderr)
    Path(str(builtin) + '.mlfco').write_bytes(good_builtin)
    run('physical-builtin-restored', main_prefix, '12\n')
    consumer.write_text(HEADER + 'module Main (main) where { import MLF.Primitive; '
        'equal :: Int -> Bool; equal x = x == 7; '
        'main = ifThenElse (equal 7) (printInt 42) (printInt 0); }\n')
    compile('consumer-dictionary-dependency', main_spec, main_prefix)
    run('dictionary-dependency-value', main_prefix, '42\n')
    authenticate_build(receipt, producer / 'bin')
    check('producer receipt unchanged', sha(receipt) == evidence['producer_sha256'])
    evidence['complete'] = True
    save()
    print('PASS flat compiler CLI controls')


if __name__ == '__main__':
    main()
