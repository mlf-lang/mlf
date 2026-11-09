#!/usr/bin/env python3
"""Exact lazy-IO optimization regressions using an authenticated producer.

Only a test Main and isolated C transports are compiled. Maintained Haskell
objects are read-only; changed compiler modules require a fresh producer. With
--gc-prefix, emitted LLVM also runs natively. No performance-time assertion,
producer qualification, full-corpus claim, or workflow/lock mutation is made.
Native provenance authenticates selected inputs, not the complete system
linker/GMP/libc closure; exact native behavior remains independently checked.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from build import DEMAND_FLAGS, EXHAUSTIVENESS_FLAGS, PACKAGES
from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tools/shared/fixtures/native/IOActionSharing.hs'
SHAPES = [
    'exact bind action exposes single use',
    'exact bind continuation exposes single use',
    'two-use action remains shared',
    'partial bind remains opaque',
    'non-lambda bind continuation remains opaque',
    'unrelated bind does not license substitution',
    'ordinary lambda remains a sharing boundary',
    'recursive group remains a sharing boundary',
    'unknown call remains a sharing boundary',
    'computed call remains a sharing boundary',
    'partial seq remains opaque',
    'two-use pure construction remains shared',
    'pure construction under ordinary lambda remains shared',
    'scalar under write remains shared',
    'scalar under return remains shared',
    'unused bottom is eliminated without demand',
    'substitution preserves same-hint captured identities',
    'single-use action restores kernel eligibility',
    'unsafe divisor remains ineligible',
]
# Independent, reviewed oracle: never derive expected IDs, output or success
# from the fixture's stdout or its source text.
CASES = [
    ('ground-string-sharing', '10\n10\n', None, False),
    ('different-class-instances', '1\n2\n', None, False),
    ('common-call-unused-bottom', 'ok\n', None, False),
    ('common-call-fresh-arrays', '0\n', None, False),
    ('bare-do-loop', '42\n', None, True),
    ('explicit-bind-loop', '42\n', None, True),
    ('shared-action-twice', 'tick\ntick\n2\n', None, False),
    ('pure-construction-sharing', '42\n42\n', None, False),
    ('unused-bottom', 'ok\n', None, False),
    ('early-failure-before-late-bottom', 'before\n', 'first failure', False),
    ('late-bottom-after-effect', 'before\n', 'late bottom', False),
    ('seq-action-does-not-execute', 'ok\n', None, False),
    ('partial-bind-stays-lazy', 'ok\n', None, False),
    ('partial-sequence-stays-lazy', 'ok\n', None, False),
    ('capture-avoiding-substitution', '42\n', None, False),
    ('ignored-return-payload', 'ok\n', None, False),
    ('custom-sequence-override', '', 'overridden sequence', False),
    ('custom-sequence-ignores-first', '42\n', None, False),
]
FORMS = ['original', 'serialized', 'optimized-erased']
BANNER = 'IO action sharing: passed (19 shape checks, 18 source cases, 3 execution forms)'


def expected_inventory():
    if len(SHAPES) != 19 or len(set(SHAPES)) != 19 or len(CASES) != 18:
        raise ValueError('authored regression inventory is inconsistent')
    chunks = ['PASS shape: ' + label + '\n' for label in SHAPES]
    for label, output, error, kernel in CASES:
        if kernel:
            chunks.append('PASS kernel: ' + label + '\n')
        for form in FORMS:
            chunks.extend(['BEGIN ' + label + '/' + form + '\n', output,
                           'OUTCOME ' + ('ok' if error is None else 'error: ' + error) + '\n'])
        chunks.append('PASS semantics: ' + label + '\n')
    return (''.join(chunks) + BANNER + '\n').encode()


def verify_inventory(stdout):
    if stdout != expected_inventory():
        raise ValueError('regression completion inventory changed: ' + repr(stdout))


def verify_artifact_inventory(work):
    expected = sorted(label + suffix for label, *_ in CASES for suffix in ['.ll', '.xmlf'])
    if sorted(p.name for p in work.iterdir()) != expected:
        raise ValueError('emitted artifact inventory changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-timeout', type=int, default=120)
    parser.add_argument('--run-timeout', type=int, default=600)
    parser.add_argument('--gc-prefix', type=Path,
                        help='Also compile and run all emitted LLVM with this BDWGC prefix.')
    parser.add_argument('--clang', default='clang')
    args = parser.parse_args()
    for option, maximum in [('build_timeout', 300), ('run_timeout', 1200)]:
        if not 1 <= getattr(args, option) <= maximum:
            parser.error(option.replace('_', '-') + ' must be between 1 and ' + str(maximum))
    receipt_path = args.build_receipt.resolve(strict=True)
    producer_dir = receipt_path.parent
    output = args.output.resolve()
    if output.is_relative_to(producer_dir) or producer_dir.is_relative_to(output):
        parser.error('output must be separate from the immutable producer')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'status': 'running',
              'scope': 'focused-io-action-sharing', 'compiler_modules_rebuilt': False,
              'native_execution_requested': args.gc_prefix is not None,
              'native_toolchain_closure_complete': False,
              'native_provenance_scope': 'selected Clang, runtime source and BDWGC inputs; system libraries not pinned',
              'full_corpus_qualification': False, 'performance_assertions': False,
              'commands': []}
    objects, inputs, artifacts, external = {}, {}, {}, {}
    authenticated = False

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'receipt.json')

    runner = CommandRunner(ROOT, output, record, save)

    def integrity():
        if authenticated:
            authenticate_build(receipt_path, producer_dir / 'bin')
            if sha(receipt_path) != record['producer_receipt_sha256']:
                raise ValueError('producer receipt changed')
        for name, digest in objects.items():
            path = (producer_dir / name).resolve(strict=True)
            if not path.is_relative_to(producer_dir) or sha(path) != digest:
                raise ValueError('producer object/interface changed: ' + name)
        for name, digest in inputs.items():
            if sha(ROOT / name) != digest:
                raise ValueError('regression input changed: ' + name)
        for name, digest in {**artifacts, **external}.items():
            if sha(name) != digest:
                raise ValueError('artifact or external input changed: ' + name)

    save()
    try:
        producer = authenticate_build(receipt_path, producer_dir / 'bin')
        objects = producer.get('object_inputs', {})
        if not objects:
            raise ValueError('producer omitted object/interface inventory')
        paths = [Path(__file__), FIXTURE, ROOT / 'tools/shared/test_direct.py',
                 ROOT / 'tools/shared/build.py', ROOT / 'host/ghc/cbits/host.c',
                 ROOT / 'runtime/mlf_process_supervisor.c', ROOT / 'runtime/mlf_runtime.c']
        paths.extend((ROOT / 'runtime').glob('*.h'))
        inputs = {str(p.resolve().relative_to(ROOT)): sha(p) for p in paths}
        record.update(producer_receipt=str(receipt_path),
                      producer_receipt_sha256=sha(receipt_path),
                      optimization=producer['optimization'], inputs=inputs,
                      object_inputs=objects)
        authenticated = True
        integrity()
        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db',
                 '-global-package-db', '-no-user-package-db', '-hide-all-packages',
                 '-O' + producer['optimization'], *DEMAND_FLAGS]
        for package in PACKAGES:
            flags += ['-package', package]
        ghc = producer['ghc']['path']
        main_object, main_interface = output / 'IOActionSharing.o', output / 'IOActionSharing.hi'
        runner.run('compile-fixture', [ghc, '-c', *flags, *EXHAUSTIVENESS_FLAGS,
                   '-i', '-i' + str(producer_dir / 'objects'), '-o', main_object,
                   '-ohi', main_interface, FIXTURE], timeout=args.build_timeout)
        link_objects = [producer_dir / name for name in sorted(objects)
                        if name.endswith('.o') and name != 'objects/Main.o']
        if not link_objects:
            raise ValueError('producer has no authenticated linkable objects')
        transports = []
        for label, source in [('host', ROOT / 'host/ghc/cbits/host.c'),
                              ('supervisor', ROOT / 'runtime/mlf_process_supervisor.c')]:
            target = output / (label + '.o')
            runner.run('compile-' + label, [producer['cc']['path'], '-O2', '-std=c11',
                       '-I' + str(ROOT / 'runtime'), '-c', source, '-o', target],
                       timeout=args.build_timeout)
            transports.append(target)
        executable = output / 'io-action-sharing'
        runner.run('link-fixture', [ghc, *flags, '-rtsopts=ignoreAll', main_object,
                   *link_objects, *transports, '-o', executable], timeout=args.build_timeout)
        artifacts.update({str(p): sha(p) for p in [executable, main_object, main_interface, *transports]})
        work = output / 'programs'
        work.mkdir()
        result = runner.run('shape-and-semantics', [executable, work],
                            expected=expected_inventory(), timeout=args.run_timeout)
        verify_inventory(result.stdout)
        verify_artifact_inventory(work)
        artifacts.update({str(p): sha(p) for p in work.iterdir()})
        record.update(shape_checks=SHAPES, source_cases=[c[0] for c in CASES],
                      execution_forms=FORMS, independent_target_check=True,
                      serialized_target_check=True, serialized_llvm_identical=True,
                      restored_array_loop_kernels=2)
        if args.gc_prefix is not None:
            clang = Path(shutil.which(args.clang) or args.clang).resolve(strict=True)
            gc = args.gc_prefix.resolve(strict=True)
            archive = gc / 'lib/libgc.a'
            external = {str(p): sha(p) for p in [clang, archive, *sorted((gc / 'include').rglob('*.h'))]}
            common = ['-O2', '-std=c11', '-I' + str(ROOT / 'runtime'), '-I' + str(gc / 'include')]
            runtime = output / 'runtime.o'
            runner.run('compile-native-runtime', [clang, *common, '-c',
                       ROOT / 'runtime/mlf_runtime.c', '-o', runtime], timeout=args.build_timeout)
            artifacts[str(runtime)] = sha(runtime)
            for label, expected, error, _ in CASES:
                binary = output / ('native-' + label)
                runner.run('link-' + label, [clang, '-O2', '-Wno-override-module',
                           work / (label + '.ll'), runtime, archive, '-lgmp', '-lm',
                           '-lpthread', '-ldl', '-o', binary], timeout=args.build_timeout)
                observed = runner.run('run-' + label, [binary], status=0 if error is None else 1,
                                      expected=expected.encode(), timeout=30)
                wanted_error = b'' if error is None else ('Runtime: ' + error + '\n').encode()
                if observed.stderr != wanted_error:
                    raise ValueError(label + ': native diagnostic changed')
                artifacts[str(binary)] = sha(binary)
            record['native_cases_passed'] = [c[0] for c in CASES]
        else:
            record['native_cases_passed'] = []
        record.update(artifacts=artifacts, external_inputs=external)
        integrity()
        record.update(complete=True, status='passed')
    except BaseException as error:
        record.update(complete=False, status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        try:
            integrity()
            record['immutable_inputs_verified_after'] = True
        except BaseException as error:
            record.update(complete=False, status='invalidated',
                          integrity_error=type(error).__name__ + ': ' + str(error))
            save()
            raise
        save()
    print(str(output / 'receipt.json') + ': passed')


if __name__ == '__main__':
    main()
