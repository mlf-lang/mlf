#!/usr/bin/env python3
"""Exact source-field/checked-ABI controls against an authenticated O2 producer.

Compile only the fixture Main and independently rebuilt C transports. The
producer's Haskell objects/interfaces stay read-only. These are focused host
controls, not a native, full-corpus, bootstrap, or fixed-point qualification.
The legacy vacuous-selector entry-adaptation rejection is explicit; a no-entry
library preserves its exact ABI, and an ordinary-selector entry is a positive
compatibility control. No generic import/cache/target repair is authorized.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from build import DEMAND_FLAGS, EXHAUSTIVENESS_FLAGS, PACKAGES
from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tools/shared/fixtures/item4/SourceFieldLayouts.hs'
# Authored independently of fixture parsing and execution. Exact order, count,
# wording and terminal banner are mandatory; a partial run is never a pass.
MAIN_CHECKS = [
    'fresh producer ownData has exactly canonical Int field',
    'source plan uses identical canonical ownData',
    'legacy lowering recipe uses identical canonical ownData',
    'producer source SCC cache is cold',
    'producer public and lowered layouts agree exactly',
    'construction, constructor-as-value and extraction have canonical contracts',
    'producer targets pass production/frozen/roundtrip/erasure',
    'producer warm source cache reuses every fragment',
    'producer cold/warm objects are byte-identical',
    'saved producer preserves exact canonical layout',
    'actual fallback query route has cold/warm reuse',
    'fallback public/lowered layouts remain canonical',
    'fallback constructor and extraction schemes equal source SCC schemes',
    'fallback targets pass production/frozen/roundtrip/erasure and warm parity',
    'metadata-only consumer uses unchanged imported layout',
    'consumer source SCC cache has cold/warm reuse',
    'consumer cold/warm bytes and imported schemes remain exact',
    'saved producer/consumer link, check, roundtrip and erase to 42',
    'manual legacy import retains quantified constructor contract',
    'manual legacy class signature and dictionary preserve dead quantifier',
    'mixed source boundary normalizes only its fresh local declaration',
    'mixed fallback recipe also retains exact imported dictionary and datatype',
    'mixed exact-context source cache has cold/warm reuse',
    'mixed owned artifact does not re-export or rewrite imported layouts',
    'legacy selector entry adaptation rejects instead of rewriting checked ABI',
    'legacy/local saved library links with both exact checked layouts',
    'mixed fallback query route has cold/warm reuse',
    'mixed fallback preserves legacy ABI through checked library linking',
    'imported metadata, semantic fingerprint and class ABI remain byte-exact',
    'ordinary imported-selector entry adaptation succeeds with exact checked ABI',
    'fresh-source canonicalizer validates original ill-kinded fields',
    'fresh-source canonicalizer validates original checked context',
]
FORGERY_CHECKS = ['checked-layout key retains dead quantifiers'] + [
    direction + ': ' + invariant
    for direction in ['quantified header / canonical payload',
                      'canonical header / quantified payload']
    for invariant in [
        'exact cache context rejects',
        'encoded cache rejects',
        'expected cache metadata rejects opposite layout',
        'pooled object rejects',
        'linker rejects exact header/payload mismatch',
        'source/lowered metadata mismatch rejects',
    ]
]
SOURCE_CLASS_CHECKS = [
    'fresh source class parser retains leading and nested dead method forall',
    'fresh source class own header is canonical before planning',
    'fresh source class plan dictionary is canonical before cache keys',
    'fresh source class fallback dictionary uses the same canonical contract',
    'fresh source class producer cold/warm artifacts are byte-identical',
    'fresh source class emitted header dictionary and selector schemes agree',
    'fresh source class saved producer preserves canonical ABI',
    'fresh source class metadata-only consumer retains canonical imported dictionary',
    'fresh source class consumer cold/warm artifacts are byte-identical',
    'fresh source class saved method applications check and evaluate to 42',
]
EXPECTED_CHECKS = MAIN_CHECKS + FORGERY_CHECKS + SOURCE_CLASS_CHECKS
BANNER = ('item4 source field layouts: passed (55 checks; source/fallback, '
          'saved imports, cold/warm, exact legacy ABI, bidirectional forgery rejection, fresh source classes)')


def verify_inventory(stdout):
    if len(EXPECTED_CHECKS) != 55 or len(set(EXPECTED_CHECKS)) != 55:
        raise ValueError('authored 55-check inventory is inconsistent')
    expected = ('\n'.join(['PASS ' + label for label in EXPECTED_CHECKS] + [BANNER]) + '\n').encode('utf-8')
    if stdout != expected:
        raise ValueError('focused completion inventory changed: ' + repr(stdout))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--build-timeout', type=int, default=120)
    parser.add_argument('--run-timeout', type=int, default=600)
    args = parser.parse_args()
    for name, maximum in [('build_timeout', 300), ('run_timeout', 1200)]:
        if not 1 <= getattr(args, name) <= maximum:
            parser.error(name.replace('_', '-') + ' must be between 1 and ' + str(maximum))

    receipt_path = args.build_receipt.resolve(strict=True)
    producer_dir = receipt_path.parent
    output = args.output.resolve()
    if output.is_relative_to(producer_dir) or producer_dir.is_relative_to(output):
        parser.error('output must be separate from the read-only producer directory')
    output.mkdir(parents=True, exist_ok=False)
    record = {
        'format': 1, 'complete': False, 'status': 'running',
        'mode': 'authenticated-O2-source-field-layouts',
        'native_or_llvm_campaign': False, 'compiler_modules_rebuilt': False,
        'strict_stderr': True, 'commands': [],
    }

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'receipt.json')

    runner = CommandRunner(ROOT, output, record, save)
    objects, input_hashes, artifacts = {}, {}, {}
    producer_authenticated = False

    def check_objects():
        for name, digest in objects.items():
            path = (producer_dir / name).resolve(strict=True)
            if not path.is_relative_to(producer_dir) or sha(path) != digest:
                raise ValueError('producer object/interface changed: ' + name)

    def check_producer():
        authenticate_build(receipt_path, producer_dir / 'bin')
        if sha(receipt_path) != record['producer_receipt_sha256']:
            raise ValueError('producer receipt changed during focused controls')
        check_objects()

    save()
    try:
        producer = authenticate_build(receipt_path, producer_dir / 'bin')
        if producer['optimization'] != '2':
            raise ValueError('source field-layout controls require an O2 producer')
        objects = producer.get('object_inputs', {})
        if not objects:
            raise ValueError('producer omitted authenticated object/interface inventory')
        check_objects()
        paths = [Path(__file__).resolve(), FIXTURE, ROOT / 'tools/shared/test_direct.py',
                 ROOT / 'tools/shared/build.py', ROOT / 'host/ghc/cbits/host.c',
                 ROOT / 'runtime/mlf_process_supervisor.c']
        input_hashes = {str(path.relative_to(ROOT)): sha(path) for path in paths}
        record.update(producer_receipt=str(receipt_path),
                      producer_receipt_sha256=sha(receipt_path),
                      optimization=producer['optimization'], inputs=input_hashes,
                      object_inputs=objects, objects_verified_before=True,
                      source_toolchain_verified_before=True)
        producer_authenticated = True
        save()

        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db',
                 '-global-package-db', '-no-user-package-db', '-hide-all-packages',
                 '-O2', *DEMAND_FLAGS]
        for package in PACKAGES:
            flags.extend(['-package', package])
        ghc = producer['ghc']['path']
        main_object = output / 'SourceFieldLayouts.o'
        main_interface = output / 'SourceFieldLayouts.hi'
        # -ohi keeps Main separate without redirecting imported interface
        # lookup into a new hidir. Never run --make against the held producer.
        runner.run('compile-fixture', [ghc, '-c', *flags, *EXHAUSTIVENESS_FLAGS,
            '-i', '-i' + str(producer_dir / 'objects'), '-o', main_object,
            '-ohi', main_interface, FIXTURE], timeout=args.build_timeout)
        link_objects = [producer_dir / name for name in sorted(objects)
                        if name.endswith('.o') and name != 'objects/Main.o']
        if not link_objects:
            raise ValueError('producer has no authenticated linkable objects')
        transports = []
        for name, source in [('host', ROOT / 'host/ghc/cbits/host.c'),
                             ('supervisor', ROOT / 'runtime/mlf_process_supervisor.c')]:
            target = output / (name + '.o')
            runner.run('compile-' + name, [producer['cc']['path'], '-O2', '-std=c11',
                '-I' + str(ROOT / 'runtime'), '-c', source, '-o', target],
                timeout=args.build_timeout)
            transports.append(target)
        executable = output / 'source-field-layouts'
        runner.run('link-fixture', [ghc, *flags, '-rtsopts=ignoreAll', main_object,
            *link_objects, *transports, '-o', executable], timeout=args.build_timeout)
        artifacts = {str(path): sha(path)
                     for path in [executable, main_object, main_interface, *transports]}
        record['artifacts'] = artifacts
        save()
        check_producer()
        work = output / 'work'
        if work.exists():
            raise ValueError('source/cache controls require an absent work directory')
        result = runner.run('source-field-layouts', [executable, work], timeout=args.run_timeout)
        verify_inventory(result.stdout)
        record.update(passing_checks=55, passing_inventory=EXPECTED_CHECKS,
                      production_and_frozen_target_checks=True,
                      serialized_target_roundtrip_and_erasure=True,
                      source_and_fallback_cold_warm_parity=True,
                      exact_legacy_imported_layouts=True,
                      legacy_selector_entry_rejection_explicit=True,
                      ordinary_selector_entry_success=True,
                      source_class_headers_and_dictionary_canonical=True,
                      source_class_producer_consumer_cold_warm=True,
                      source_class_method_use_42=True)
        check_producer()
        record.update(complete=True, status='passed')
    except BaseException as error:
        record.update(complete=False, status='failed',
                      error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        # A timeout, partial stdout, compile warning or failed negative oracle
        # retains an incomplete receipt. Recheck immutable inputs on failures
        # too, including the complete producer source/toolchain identity.
        integrity_error = None
        try:
            if producer_authenticated:
                check_producer()
                record['source_toolchain_verified_after'] = True
            if objects:
                check_objects()
                record['objects_verified_after'] = True
            if input_hashes:
                if any(sha(ROOT / name) != digest for name, digest in input_hashes.items()):
                    raise ValueError('fixture, harness, or transport sources changed')
                record['sources_verified_after'] = True
            if artifacts:
                if any(sha(path) != digest for path, digest in artifacts.items()):
                    raise ValueError('focused test artifacts changed')
                record['artifacts_verified_after'] = True
        except BaseException as error:
            integrity_error = error
            record.update(complete=False, status='invalidated',
                          integrity_error=type(error).__name__ + ': ' + str(error))
        save()
        if integrity_error is not None and 'error' not in record:
            raise integrity_error
    print(str(output / 'receipt.json') + ': passed (55 checks)')


if __name__ == '__main__':
    main()
