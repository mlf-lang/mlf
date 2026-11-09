#!/usr/bin/env python3
"""Checked native-library contracts and fresh O0/O2 runtime controls.

Compile only independent test entry points against authenticated producer
objects. Exercise lazy exports, checked wrapper rejection, collector roots,
shared slots and repeatable IO. This focused gate makes no performance or
complete native toolchain-closure claim.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shlex
from build import DEMAND_FLAGS, EXHAUSTIVENESS_FLAGS, PACKAGES
from test_direct import CommandRunner, authenticate_build, sha
from test_native_string_index import local_c_closure, resolve_tool

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tools/shared/fixtures/native'
BOUNDARY_OUTPUT = (b'PASS native schema and actual checked-wrapper negative controls; 0/1/2/65 export library terms independently checked\n'
                   b'PASS native datatype extension: complete census, kind preservation, stable tags and collision rejection\n')
EMIT_OUTPUT = (b'PASS emitted checked native libraries: poison0 poison1 poison7 poison65 io\n'
               b'PASS emitted native datatype extension: user-first saved-first\n'
               b'PASS emitted native open fields: delayed unused demanded\n')
RUNTIME_OUTPUT = b'PASS native lazy getters, shared slots, GC and bounds\n'
CASES = [('poison0', 0, False), ('poison1', 1, False),
         ('poison7', 7, False), ('poison65', 65, False), ('io', 2, True)]
PREFIX = 'mlf_fixed_' + 'a' * 64
FRONTEND_FIXTURE = ROOT / 'tools/experimental/prepared-libraries/NativeFrontendControls.hs'
FRONTEND_OUTPUT = (b'Implicit.emlf accepted\nSubset.emlf accepted\nUserDatatype.emlf accepted\n'
                   b'InstanceControl.hs accepted\n'
                   b'native subset, implicit Prelude, instance reach and default loader controls passed\n')


def verify_root_shape(source, count):
    # A pointer to untraced malloc storage would fail this independent oracle.
    required = [f'@{PREFIX}_root = private global ptr null, align 8',
                f'@{PREFIX}_slots = private global [{count} x ptr] zeroinitializer, align 8',
                f'@{PREFIX}_state = private global i32 0, align 4',
                f'define ptr @{PREFIX}_get(i64 %index)',
                f'%valid = icmp ult i64 %index, {count}']
    if any(fragment not in source for fragment in required):
        raise ValueError('native exported roots/getter shape changed')
    getter = source.split(f'define ptr @{PREFIX}_get(i64 %index)', 1)[1]
    if 'call ptr @mlf_force(' in getter:
        raise ValueError('getter forces lazy exported leaves')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gc-prefix', type=Path, required=True)
    parser.add_argument('--clang', default='clang')
    parser.add_argument('--frontend-source-root', type=Path,
                        help='Require installed-registry frontend controls using this fixed library source root.')
    args = parser.parse_args()
    receipt = args.build_receipt.resolve(strict=True)
    producer_dir, output = receipt.parent, args.output.resolve()
    if output.is_relative_to(producer_dir) or producer_dir.is_relative_to(output):
        parser.error('output must be separate from the immutable producer')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'status': 'running',
              'scope': 'checked-fixed-native-library', 'compiler_modules_rebuilt': False,
              'native_execution': True, 'full_corpus_qualification': False,
              'performance_assertions': False, 'native_toolchain_closure_complete': False,
              'installed_frontend_controls_requested': args.frontend_source_root is not None,
              'commands': []}
    objects, inputs, artifacts = {}, {}, {}
    authenticated = False

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'receipt.json')

    def integrity():
        if authenticated:
            authenticate_build(receipt, producer_dir / 'bin')
            if sha(receipt) != record['producer_receipt_sha256']:
                raise ValueError('producer receipt changed')
        for name, digest in objects.items():
            path = (producer_dir / name).resolve(strict=True)
            if not path.is_relative_to(producer_dir) or sha(path) != digest:
                raise ValueError('producer object/interface changed: ' + name)
        for path, digest in {**inputs, **artifacts}.items():
            if sha(path) != digest:
                raise ValueError('native test input or artifact changed: ' + path)

    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        producer = authenticate_build(receipt, producer_dir / 'bin')
        objects = producer.get('object_inputs', {})
        if not objects:
            raise ValueError('producer omitted object/interface inventory')
        clang, pkg_config = resolve_tool(args.clang), resolve_tool('pkg-config')
        gc = args.gc_prefix.resolve(strict=True)
        archive = gc / 'lib/libgc.a'
        runtime_sources = local_c_closure(ROOT / 'runtime/mlf_runtime.c')
        paths = [Path(__file__), ROOT / 'tools/shared/test_direct.py',
                 ROOT / 'tools/shared/test_native_string_index.py', ROOT / 'tools/shared/build.py',
                 FIXTURES / 'NativeBoundaryTests.hs', FIXTURES / 'NativeLibraryRuntime.hs',
                 FIXTURES / 'NativePrivateConstructors.hs',
                 FIXTURES / 'MaterializeImportsTests.hs',
                 FIXTURES / 'PartialMaterializeImportsTests.hs',
                 FIXTURES / 'HeaderValidationTests.hs',
                 FIXTURES / 'SplitBuiltinControls.hs',
                 FIXTURES / 'native_library_runtime.c', ROOT / 'host/ghc/cbits/host.c',
                 ROOT / 'runtime/mlf_process_supervisor.c', clang, pkg_config, archive,
                 *runtime_sources, *sorted((ROOT / 'runtime').glob('*.h')),
                 *sorted((gc / 'include').rglob('*.h'))]
        if args.frontend_source_root is not None:
            paths.append(FRONTEND_FIXTURE)
        inputs = {str(p.resolve(strict=True)): sha(p) for p in paths}
        record.update(producer_receipt=str(receipt), producer_receipt_sha256=sha(receipt),
                      optimization=producer['optimization'], inputs=inputs, object_inputs=objects)
        authenticated = True
        integrity()
        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db',
                 '-global-package-db', '-no-user-package-db', '-hide-all-packages',
                 '-O' + producer['optimization'], *DEMAND_FLAGS]
        for package in PACKAGES:
            flags += ['-package', package]
        ghc = producer['ghc']['path']
        link_objects = [producer_dir / name for name in sorted(objects)
                        if name.endswith('.o') and name != 'objects/Main.o']
        if not link_objects:
            raise ValueError('producer has no authenticated linkable objects')
        transports = []
        for label, source in [('host', ROOT / 'host/ghc/cbits/host.c'),
                              ('supervisor', ROOT / 'runtime/mlf_process_supervisor.c')]:
            target = output / (label + '.o')
            runner.run('compile-' + label, [producer['cc']['path'], '-O2', '-std=c11',
                       '-I' + str(ROOT / 'runtime'), '-c', source, '-o', target], timeout=120)
            transports.append(target)
        artifacts.update({str(p): sha(p) for p in transports})
        executables = {}
        fixture_sources = {name: FIXTURES / (name + '.hs')
                           for name in ['NativeBoundaryTests', 'NativeLibraryRuntime',
                                        'NativePrivateConstructors', 'MaterializeImportsTests',
                                        'PartialMaterializeImportsTests', 'HeaderValidationTests',
                                        'SplitBuiltinControls']}
        if args.frontend_source_root is not None:
            fixture_sources['NativeFrontendControls'] = FRONTEND_FIXTURE
        for fixture, source in fixture_sources.items():
            obj, hi, executable = [output / (fixture + suffix) for suffix in ['.o', '.hi', '']]
            runner.run('compile-' + fixture, [ghc, '-c', *flags, *EXHAUSTIVENESS_FLAGS,
                       '-i', '-i' + str(producer_dir / 'objects'), '-o', obj, '-ohi', hi,
                       source], timeout=120)
            runner.run('link-' + fixture, [ghc, *flags, '-rtsopts=ignoreAll', obj,
                       *link_objects, *transports, '-o', executable], timeout=120)
            artifacts.update({str(p): sha(p) for p in [obj, hi, executable]})
            executables[fixture] = executable
        if args.frontend_source_root is not None:
            source_root = args.frontend_source_root.resolve(strict=True)
            if not source_root.is_dir() or not source_root.is_relative_to(ROOT):
                raise ValueError('frontend source root must belong to the authenticated source tree')
            frontend_work = output / 'frontend-fixtures'
            for directory in ['primary', 'default']:
                (frontend_work / directory).mkdir(parents=True)
            runner.run('installed-frontend-controls',
                       [executables['NativeFrontendControls'], frontend_work, source_root],
                       expected=FRONTEND_OUTPUT, timeout=120)
            artifacts.update({str(p): sha(p) for p in frontend_work.rglob('*') if p.is_file()})
            record.update(installed_frontend_controls_passed=True, frontend_source_root=str(source_root))
        else:
            record['installed_frontend_controls_passed'] = False
        runner.run('checked-boundary-controls', [executables['NativeBoundaryTests']],
                   expected=BOUNDARY_OUTPUT, timeout=120)
        runner.run('checked-builtin-materialization', [executables['MaterializeImportsTests']],
                   expected=b'PASS zero-native returned lambda, mixed imports, same-hint distinct identity, wrong mapping rejection, independent check\n',
                   timeout=120)
        runner.run('partial-checked-materialization', [executables['PartialMaterializeImportsTests']],
                   expected=b'PASS partial checked composition, unused prefix pruning, binder identity, nominal weakening and independent checker oracle\n',
                   timeout=120)
        runner.run('header-validation-equivalence', [executables['HeaderValidationTests']],
                   expected=b'PASS header duplicate errors, entity identity, Unicode naming and forged primitive rejection\n',
                   timeout=120)
        runner.run('split-builtin-selection-controls', [executables['SplitBuiltinControls']],
                   expected=b'PASS recursive SCC atomicity, polymorphic and lazy semantics, selected/full checker parity, incoming dependencies and malformed fragment rejection\n',
                   timeout=120)
        work = output / 'programs'
        work.mkdir()
        runner.run('emit-libraries', [executables['NativeLibraryRuntime'], work],
                   expected=EMIT_OUTPUT, timeout=120)
        extensions = ['extension-user-first', 'extension-saved-first']
        open_fields = ['open-fields-delayed', 'open-fields-unused', 'open-fields-demanded']
        expected_artifacts = ([label + '.ll' for label, _, _ in CASES]
                              + [label + '.ll' for label in extensions + open_fields]
                              + ['extension-library.ll', 'open-fields-library.ll'])
        if sorted(p.name for p in work.iterdir()) != sorted(expected_artifacts):
            raise ValueError('native library artifact inventory changed')
        for label, count, _ in CASES:
            verify_root_shape((work / (label + '.ll')).read_text(), count)
        artifacts.update({str(p): sha(p) for p in work.iterdir()})
        private_work = output / 'private-programs'
        private_work.mkdir()
        private_cases = ['private-identity', 'private-escape-ignore', 'private-escape-demand']
        runner.run('emit-private-boundary', [executables['NativePrivateConstructors'], private_work],
                   expected=b'PASS private constructor boundary emission\n', timeout=120)
        if sorted(p.name for p in private_work.iterdir()) != sorted(
                [name + '.ll' for name in private_cases] + ['private-library.ll']):
            raise ValueError('private constructor boundary artifact inventory changed')
        # Both sites must survive into the same actual root. A test containing
        # only the escaping site cannot catch overwriting an earlier True fact.
        private_ir = (private_work / 'private-escape-demand.ll').read_text()
        if ('call ptr @mlf.construct.1(i64 69,' not in private_ir
                or 'call ptr @mlf_constructor(i64 69, i64 1)' not in private_ir):
            raise ValueError('private strict-site plus escaping-constructor control became vacuous')
        artifacts.update({str(p): sha(p) for p in private_work.iterdir()})
        cflags = shlex.split(runner.run('gmp-cflags', [pkg_config, '--cflags', 'gmp'], timeout=30).stdout.decode())
        libraries = shlex.split(runner.run('gmp-libs', [pkg_config, '--libs', 'gmp'], timeout=30).stdout.decode())
        common = ['-std=c11', *cflags, '-I' + str(ROOT / 'runtime'), '-I' + str(gc / 'include')]
        passed = []
        for opt in ['0', '2']:
            runtime = output / ('runtime-O' + opt + '.o')
            runner.run('runtime-O' + opt, [clang, '-O' + opt, *common, '-c',
                       ROOT / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
            artifacts[str(runtime)] = sha(runtime)
            for label, count, is_io in CASES:
                case = label + '-O' + opt
                binary = output / case
                runner.run('link-' + case, [clang, '-O' + opt, '-Wno-override-module', *common,
                           '-DEXPORT_COUNT=' + str(count), '-DIO_EXPORT=' + str(int(is_io)),
                           FIXTURES / 'native_library_runtime.c', work / (label + '.ll'),
                           runtime, archive, *libraries, '-lm', '-lpthread', '-ldl', '-o', binary], timeout=120)
                artifacts[str(binary)] = sha(binary)
                runner.run('run-' + case, [binary], expected=(b'native-action\nnative-action\n' if is_io else b'')
                           + RUNTIME_OUTPUT, timeout=30)
                passed.append(case + ':lazy-shared-gc-bounds')
                if count:
                    demanded = runner.run('demand-' + case, [binary, 'demand'], status=1, expected=b'', timeout=30)
                    if demanded.stderr != b'Runtime: integer division by zero\n':
                        raise ValueError(case + ': poison demand diagnostic changed')
                    passed.append(case + ':demand-fails')
            for label in extensions:
                case = label + '-O' + opt
                binary = output / case
                runner.run('link-' + case, [clang, '-O' + opt, '-Wno-override-module',
                           work / (label + '.ll'), work / 'extension-library.ll', runtime,
                           archive, *libraries, '-lm', '-lpthread', '-ldl', '-o', binary], timeout=120)
                artifacts[str(binary)] = sha(binary)
                runner.run('run-' + case, [binary], expected=b'42\n', timeout=30)
                passed.append(case + ':installed-value-with-user-datatype')
            for label in open_fields:
                case = label + '-O' + opt
                binary = output / case
                runner.run('link-' + case, [clang, '-O' + opt, '-Wno-override-module',
                           work / (label + '.ll'), work / 'open-fields-library.ll', runtime,
                           archive, *libraries, '-lm', '-lpthread', '-ldl', '-o', binary], timeout=120)
                artifacts[str(binary)] = sha(binary)
                fails = label == 'open-fields-demanded'
                observed = runner.run('run-' + case, [binary], status=1 if fails else 0,
                                      expected=b'' if fails else b'1\n', timeout=30)
                if observed.stderr != (b'Runtime: lazy-field-demanded\n' if fails else b''):
                    raise ValueError(case + ': external field demand changed')
                passed.append(case + ':external-lazy-field')
            for label in private_cases:
                case = label + '-O' + opt
                binary = output / case
                runner.run('link-' + case, [clang, '-O' + opt, '-Wno-override-module',
                           private_work / (label + '.ll'), private_work / 'private-library.ll', runtime,
                           archive, *libraries, '-lm', '-lpthread', '-ldl', '-o', binary], timeout=120)
                artifacts[str(binary)] = sha(binary)
                fails = label == 'private-escape-demand'
                observed = runner.run('run-' + case, [binary], status=1 if fails else 0,
                                      expected=b'' if fails else b'1\n', timeout=30)
                if observed.stderr != (b'Runtime: private-poison\n' if fails else b''):
                    raise ValueError(case + ': escaped private constructor field demand changed')
                passed.append(case + ':private-constructor-boundary')
        record.update(native_cases_passed=passed, gmp_flags={'cflags': cflags, 'libraries': libraries},
                      artifacts=artifacts, complete=True, status='passed')
    except BaseException as error:
        record.update(complete=False, status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        try:
            integrity()
            record['immutable_inputs_verified_after'] = True
        except BaseException as error:
            record.update(complete=False, status='invalidated', integrity_error=type(error).__name__ + ': ' + str(error))
            save()
            raise
        save()
    print(str(output / 'receipt.json') + ': passed')


if __name__ == '__main__':
    main()
