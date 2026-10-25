#!/usr/bin/env python3
"""Authored field-projection graph controls against an authenticated O2 producer.

Compile only the fixture Main and independently rebuilt C transports. The
producer's Haskell objects/interfaces stay read-only. These are focused host
controls, not a native, full-corpus, bootstrap, or fixed-point qualification.
Expected copies and graph identities are independently authored in the companion
fixture, with exact output inventory and independent index reconstruction.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from build import DEMAND_FLAGS, EXHAUSTIVENESS_FLAGS, PACKAGES
from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tools/shared/fixtures/item4/ParameterFieldGraph.hs'
# Authored independently of fixture parsing and execution. Exact order, count,
# wording and terminal banner are mandatory; a partial run is never a pass.
EXPECTED_CHECKS = [
    'rigid root-local quantifier is eligible',
    'authored copy map and full expected graph',
    'original nodes and captured skolem remain unchanged',
    'indexed materialization matches authored graph and rebuilt indexes',
    'sealed case and shared step evaluator agree',
    'flexible same-shape lower bound remains shared',
    'abstract rigid skolem remains shared',
    'inert constant-bound prefix remains shared',
    'nested-rank-only quantifier remains shared',
    'flexible bottom remains shared',
    'rigid bottom copies exactly its root',
    'missing non-Gen and replayed destinations reject',
    'internally captured nominal skolem is never copied',
    'invalid later descriptor rejects the whole case',
    'malformed binder cycle rejects before traversal',
    'high alias fresh-counter forgery rejects',
    'no-op case does not conceal malformed indexes',
    'higher-kinded local variables preserve kind and identity sharing',
]
BANNER = "field projection graph: passed (18 authored checks)"

def expected_stdout():
    if len(EXPECTED_CHECKS) != 18 or len(set(EXPECTED_CHECKS)) != 18:
        raise ValueError('authored 18-check inventory is inconsistent')
    return ('\n'.join(['PASS ' + label for label in EXPECTED_CHECKS] + [BANNER]) + '\n').encode()


def verify_inventory(stdout):
    if stdout != expected_stdout():
        raise ValueError('focused completion inventory changed: ' + repr(stdout))


def verify_result(returncode, stdout, stderr):
    if returncode != 0 or stderr:
        raise ValueError('focused graph controls require exit zero and empty stderr')
    verify_inventory(stdout)


def self_test():
    # Fixed independent wire oracle, not generated from EXPECTED_CHECKS or the
    # Haskell fixture. Mutating the gate's inventory must not redefine success.
    fixed = b"""PASS rigid root-local quantifier is eligible
PASS authored copy map and full expected graph
PASS original nodes and captured skolem remain unchanged
PASS indexed materialization matches authored graph and rebuilt indexes
PASS sealed case and shared step evaluator agree
PASS flexible same-shape lower bound remains shared
PASS abstract rigid skolem remains shared
PASS inert constant-bound prefix remains shared
PASS nested-rank-only quantifier remains shared
PASS flexible bottom remains shared
PASS rigid bottom copies exactly its root
PASS missing non-Gen and replayed destinations reject
PASS internally captured nominal skolem is never copied
PASS invalid later descriptor rejects the whole case
PASS malformed binder cycle rejects before traversal
PASS high alias fresh-counter forgery rejects
PASS no-op case does not conceal malformed indexes
PASS higher-kinded local variables preserve kind and identity sharing
field projection graph: passed (18 authored checks)
"""
    verify_result(0, fixed, b'')
    lines = fixed.splitlines(keepends=True)
    mutations = [
        ('missing observation', b''.join(lines[:-2] + lines[-1:])),
        ('extra observation', fixed + b'PASS unauthorized observation\n'),
        ('duplicate observation', b''.join(lines[:1] + lines)),
        ('reordered observations', b''.join([lines[1], lines[0]] + lines[2:])),
        ('partial output', lines[0]),
        ('missing banner', b''.join(lines[:-1])),
        ('wrong banner', fixed.replace(b'18 authored checks', b'17 authored checks')),
        ('diagnostic stdout', fixed + b'warning: incomplete\n'),
        ('invalid UTF-8', b'\xff'),
        ('CRLF output', fixed.replace(b'\n', b'\r\n')),
        ('missing terminal newline', fixed[:-1]),
    ]
    for label, changed in mutations:
        try:
            verify_result(0, changed, b'')
        except ValueError:
            pass
        else:
            raise AssertionError('accepted ' + label)
    for status, stderr in [(1, b''), (-9, b''), (0, b'warning\n')]:
        try:
            verify_result(status, fixed, stderr)
        except ValueError:
            pass
        else:
            raise AssertionError('accepted bad exit status or stderr')
    original = EXPECTED_CHECKS[:]
    try:
        EXPECTED_CHECKS.reverse()
        try:
            verify_inventory(fixed)
        except ValueError:
            pass
        else:
            raise AssertionError('mutated gate changed its own oracle')
    finally:
        EXPECTED_CHECKS[:] = original
    print('parameter field graph runner: passed (16 fixed-output controls)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true', help='run cheap fixed-output mutation controls only')
    parser.add_argument('--build-receipt', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--build-timeout', type=int, default=120)
    parser.add_argument('--run-timeout', type=int, default=120)
    args = parser.parse_args()
    if args.self_test:
        if args.build_receipt is not None or args.output is not None:
            parser.error('--self-test cannot be combined with build inputs')
        self_test()
        return
    if args.build_receipt is None or args.output is None:
        parser.error('--build-receipt and --output are required unless --self-test is selected')
    for name, maximum in [('build_timeout', 300), ('run_timeout', 300)]:
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
        'mode': 'authenticated-O2-field-projection-graph',
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
            raise ValueError('parameter-field graph controls require an O2 producer')
        objects = producer.get('object_inputs', {})
        if not objects:
            raise ValueError('producer omitted authenticated object/interface inventory')
        check_objects()
        paths = [Path(__file__).resolve(), FIXTURE, ROOT / 'tools/shared/test_direct.py',
                 ROOT / 'tools/shared/build.py', ROOT / 'host/ghc/cbits/host.c',
                 ROOT / 'runtime/mlf_process_supervisor.c',
                 ROOT / 'runtime/mlf_process_supervisor.h']
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
        main_object = output / 'ParameterFieldGraph.o'
        main_interface = output / 'ParameterFieldGraph.hi'
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
        executable = output / 'field-projection-graph'
        runner.run('link-fixture', [ghc, *flags, '-rtsopts=ignoreAll', main_object,
            *link_objects, *transports, '-o', executable], timeout=args.build_timeout)
        artifacts = {str(path): sha(path)
                     for path in [executable, main_object, main_interface, *transports]}
        record['artifacts'] = artifacts
        save()
        check_producer()
        result = runner.run('field-projection-graph', [executable], timeout=args.run_timeout)
        verify_result(result.returncode, result.stdout, result.stderr)
        record.update(passing_checks=18, passing_inventory=EXPECTED_CHECKS,
                      authored_expected_copy_graph=True, independent_index_reconstruction=True)
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
    print(str(output / 'receipt.json') + ': passed (18 checks)')


if __name__ == '__main__':
    main()
