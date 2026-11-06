#!/usr/bin/env python3
"""Focused recursive/managed-evidence controls against authenticated O2 objects.

Build only the fixture Main and tiny authenticated C transports in a fresh
output directory. Shared Haskell objects/interfaces remain read-only. This is
not a native-unit, bootstrap, or fixed-point qualification mode.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from build import DEMAND_FLAGS, EXHAUSTIVENESS_FLAGS, PACKAGES
from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tools/shared/fixtures/item4/RecursiveManagedEvidence.hs'
RAW_CHECKS = [
    *['raw managed recursion ' + order + ' ' + mode
      for order in ['first', 'last'] for mode in ['signed', 'mixed']],
    *['managed method with ' + mode + ' helper scope'
      for mode in ['direct', 'unsigned', 'signed']],
    *['standalone explicit qualified interface ' + name for name in [
        'coercionOrdinary', 'signatureOrdinary', 'coercionFirst',
        'signatureFirst', 'coercionLast', 'signatureLast']],
    *['standalone ' + wrapper + ' managed expression consumed' + order
      for order in ['First', 'Last'] for wrapper in ['located', 'copied']],
]
PARSED_CHECKS = [
    *[mode + ' managed-' + order for order in ['first', 'last']
      for mode in ['signed self recursion', 'mixed signed/unsigned recursion']],
    'parsed managed expression consumedFirst',
    'parsed managed expression consumedLast',
]
SOURCE_CHECKS = ['source recursive singleton/mutual and qualified successor contracts']


def verify_inventory(stdout, expected):
    actual = [line[5:].decode('utf-8') for line in stdout.splitlines()
              if line.startswith(b'PASS ')]
    if actual != expected:
        raise ValueError('focused completion inventory changed: ' + repr(actual))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    limits = [('build', 120, 300), ('raw', 300, 900),
              ('parsed', 600, 1200), ('source', 120, 600)]
    for name, default, _ in limits:
        parser.add_argument('--' + name + '-timeout', type=int, default=default,
                            help='Maximum seconds per ' + name + ' command.')
    args = parser.parse_args()
    for name, _, maximum in limits:
        if not 1 <= getattr(args, name + '_timeout') <= maximum:
            parser.error(name + ' timeout must be between 1 and ' + str(maximum))

    receipt_path = args.build_receipt.resolve(strict=True)
    producer_dir = receipt_path.parent
    output = args.output.resolve()
    if output.is_relative_to(producer_dir) or producer_dir.is_relative_to(output):
        parser.error('output must be separate from the read-only producer directory')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'full_native_unit': False,
              'mode': 'authenticated-O2-recursive-managed-evidence', 'commands': []}

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'receipt.json')

    runner = CommandRunner(ROOT, output, record, save)
    objects, input_hashes, artifacts = {}, {}, {}
    save()
    try:
        producer = authenticate_build(receipt_path, producer_dir / 'bin')
        if producer['optimization'] != '2':
            raise ValueError('recursive managed-evidence gate requires an O2 producer')
        objects = producer.get('object_inputs', {})
        if not objects:
            raise ValueError('producer omitted authenticated object/interface inventory')

        def check_objects():
            for name, expected in objects.items():
                path = (producer_dir / name).resolve(strict=True)
                if not path.is_relative_to(producer_dir) or sha(path) != expected:
                    raise ValueError('producer object/interface changed: ' + name)

        check_objects()
        inputs = [Path(__file__).resolve(), FIXTURE, ROOT / 'tools/shared/test_direct.py',
                  ROOT / 'tools/shared/build.py', ROOT / 'host/ghc/cbits/host.c',
                  ROOT / 'runtime/mlf_process_supervisor.c']
        input_hashes = {str(path.relative_to(ROOT)): sha(path) for path in inputs}
        record.update(producer_receipt=str(receipt_path),
                      producer_receipt_sha256=sha(receipt_path),
                      optimization=producer['optimization'], inputs=input_hashes,
                      object_inputs=objects, objects_verified_before=True)
        save()

        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db',
                 '-global-package-db', '-no-user-package-db', '-hide-all-packages',
                 '-O2', *DEMAND_FLAGS]
        for package in PACKAGES:
            flags.extend(['-package', package])
        ghc = producer['ghc']['path']
        main_object = output / 'RecursiveManagedEvidence.o'
        main_interface = output / 'RecursiveManagedEvidence.hi'
        # -hidir would redirect imported interface lookup too. -ohi keeps this
        # Main separate while imports read only the authenticated producer .hi.
        runner.run('compile-fixture', [ghc, '-c', *flags, *EXHAUSTIVENESS_FLAGS,
            '-i', '-i' + str(producer_dir / 'objects'), '-o', main_object,
            '-ohi', main_interface, FIXTURE], timeout=args.build_timeout)
        link_objects = [producer_dir / name for name in sorted(objects)
                        if name.endswith('.o') and name != 'objects/Main.o']
        if not link_objects:
            raise ValueError('producer has no authenticated linkable objects')
        # Standalone C outputs are not in producer.object_inputs. Rebuild only
        # these tiny transports from authenticated source/toolchain, rather
        # than trusting unauthenticated producer host.o/supervisor.o bytes.
        transport = []
        for name, source in [('host', ROOT / 'host/ghc/cbits/host.c'),
                             ('supervisor', ROOT / 'runtime/mlf_process_supervisor.c')]:
            target = output / (name + '.o')
            runner.run('compile-' + name, [producer['cc']['path'], '-O2', '-std=c11',
                '-I' + str(ROOT / 'runtime'), '-c', source, '-o', target],
                timeout=args.build_timeout)
            transport.append(target)
        executable = output / 'recursive-managed'
        runner.run('link-fixture', [ghc, *flags, '-rtsopts=ignoreAll', main_object,
            *link_objects, *transport, '-o', executable], timeout=args.build_timeout)
        artifacts = {str(path): sha(path)
                     for path in [executable, main_object, main_interface, *transport]}
        record['artifacts'] = artifacts
        save()

        fresh_cache = output / 'source-cache'
        if fresh_cache.exists():
            raise ValueError('source controls require an absent cold cache')
        for name, arguments, expected in [
                ('raw', ['--raw'], RAW_CHECKS),
                ('parsed', ['--parsed'], PARSED_CHECKS),
                ('source', ['--source', fresh_cache], SOURCE_CHECKS)]:
            result = runner.run(name, [executable, *arguments],
                                timeout=getattr(args, name + '_timeout'))
            verify_inventory(result.stdout, expected)
            record[name + '_checks'] = len(expected)
            save()

        authenticate_build(receipt_path, producer_dir / 'bin')
        check_objects()
        if sha(receipt_path) != record['producer_receipt_sha256']:
            raise ValueError('producer receipt changed during focused controls')
        if any(sha(ROOT / name) != expected for name, expected in input_hashes.items()):
            raise ValueError('fixture, harness, or transport sources changed during controls')
        if any(sha(path) != expected for path, expected in artifacts.items()):
            raise ValueError('focused test artifacts changed during controls')
        record.update(complete=True, objects_verified_after=True,
                      production_and_independent_target_checks=True,
                      target_roundtrip_and_erasure=True,
                      source_contract_cold_warm_parity=True)
    except BaseException as error:
        record['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        # A failed or timed-out probe must also record whether it changed its
        # authenticated inputs. Preserve the first failure while retaining any
        # additional integrity failure in the same receipt.
        integrity_error = None
        try:
            if objects:
                check_objects()
                record['objects_verified_after'] = True
            if input_hashes:
                if any(sha(ROOT / name) != expected
                       for name, expected in input_hashes.items()):
                    raise ValueError('input sources changed during focused controls')
                record['sources_verified_after'] = True
            if artifacts and any(sha(path) != expected for path, expected in artifacts.items()):
                raise ValueError('focused artifacts changed during controls')
        except BaseException as error:
            integrity_error = error
            record['integrity_error'] = type(error).__name__ + ': ' + str(error)
            record['complete'] = False
        save()
        if integrity_error is not None and 'error' not in record:
            raise integrity_error


if __name__ == '__main__':
    main()
