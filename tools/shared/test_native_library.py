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
import os
from pathlib import Path
import shlex
import sys
from build import DEMAND_FLAGS, EXHAUSTIVENESS_FLAGS, PACKAGES
from test_direct import CommandRunner, authenticate_build, sha
from source_root_cli import check_source_root, check_installed_root
from test_native_string_index import local_c_closure, resolve_tool
from header_validation_adapter import (input_paths as header_validation_inputs,
                                       prepare as prepare_header_validation,
                                       verify_prepared as verify_header_validation)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/testing'))
from receipt_selection import identity, select
FIXTURES = ROOT / 'tools/shared/fixtures/native'
BOUNDARY_OUTPUT = (b'PASS native schema and actual checked-wrapper negative controls; 0/1/2/65 export library terms independently checked\n'
                   b'PASS native datatype extension: complete census, kind preservation, stable tags and collision rejection\n')
EMIT_OUTPUT = (b'PASS emitted checked native libraries: poison0 poison1 poison7 poison65 io\n'
               b'PASS emitted native datatype extension: user-first saved-first\n'
               b'PASS emitted native open fields: delayed unused demanded\n')
RUNTIME_OUTPUT = b'PASS native lazy getters, shared slots, GC and bounds\n'
CASES = [('poison0', 0, False), ('poison1', 1, False),
         ('poison7', 7, False), ('poison65', 65, False), ('io', 2, True)]
EXTENSIONS = ('extension-user-first', 'extension-saved-first')
OPEN_FIELDS = ('open-fields-delayed', 'open-fields-unused', 'open-fields-demanded')
PRIVATE_CASES = ('private-identity', 'private-escape-ignore', 'private-escape-demand')
NATIVE_CASES = tuple(
    f'{label}-O{opt}:{oracle}'
    for opt in ('0', '2')
    for label, oracles in (
        *((name, ('lazy-shared-gc-bounds', 'demand-fails') if count else ('lazy-shared-gc-bounds',))
          for name, count, _ in CASES),
        *((name, ('installed-value-with-user-datatype',)) for name in EXTENSIONS),
        *((name, ('external-lazy-field',)) for name in OPEN_FIELDS),
        *((name, ('private-constructor-boundary',)) for name in PRIVATE_CASES),
    )
    for oracle in oracles
)
HOST_FIXTURES = {
    'checked-boundary-controls': 'NativeBoundaryTests',
    'checked-builtin-materialization': 'MaterializeImportsTests',
    'partial-checked-materialization': 'PartialMaterializeImportsTests',
    'header-validation-historical': 'HeaderValidationHistorical',
    'header-validation-current': 'HeaderValidationCurrent',
    'split-builtin-selection-controls': 'SplitBuiltinControls',
}
FRONTEND_CASE = 'installed-frontend-controls'
SOURCE_CLI = 'source-root-cli'
INSTALLED_CLI = 'installed-root-cli'
PREFIX = 'mlf_fixed_' + 'a' * 64
FRONTEND_FIXTURE = ROOT / 'tools/experimental/prepared-libraries/NativeFrontendControls.hs'
FRONTEND_OUTPUT = (b'Implicit.emlf accepted\nSubset.emlf accepted\nUserDatatype.emlf accepted\n'
                   b'InstanceControl.hs accepted\n'
                   b'shared roots preserve polymorphism, IO, imported/local scopes, checked results and rejection phases\n'
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


def case_inventory(installed):
    frontend = (FRONTEND_CASE, INSTALLED_CLI) if installed else (SOURCE_CLI,)
    return frontend + tuple(HOST_FIXTURES) + NATIVE_CASES


def main():
    prefix = os.environ.get('MLF_TEST_ID_PREFIX', 'native-library/')
    arguments = sys.argv[1:]
    installed = prefix == 'installed-native-library/' or any(
        arg == '--frontend-source-root' or arg.startswith('--frontend-source-root=') for arg in arguments
    )
    inventory = case_inventory(installed)
    if '--framework-list' in arguments:
        print(json.dumps([identity(prefix, label) for label in inventory]))
        return
    selection = select(prefix, inventory)
    selected_program = selection.split(':', 1)[0] if selection in NATIVE_CASES else None
    selected_label, _, selected_opt = selected_program.rpartition('-O') if selected_program else (None, None, None)

    def wants(label):
        return selection is None or selection == label

    def selected(label, opt, oracle):
        return wants(f'{label}-O{opt}:{oracle}')

    native_selected = selection is None or selection in NATIVE_CASES
    headers_selected = selection is None or selection in ('header-validation-historical', 'header-validation-current')

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gc-prefix', type=Path, required=True)
    parser.add_argument('--clang', default='clang')
    parser.add_argument('--frontend-source-root', type=Path,
                        help='Require installed-registry frontend controls using this fixed library source root.')
    args = parser.parse_args()
    if installed and args.frontend_source_root is None and wants(FRONTEND_CASE):
        parser.error('installed frontend control requires --frontend-source-root')
    receipt = args.build_receipt.resolve(strict=True)
    producer_dir, output = receipt.parent, args.output.resolve()
    if output.is_relative_to(producer_dir) or producer_dir.is_relative_to(output):
        parser.error('output must be separate from the immutable producer')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'status': 'running',
              'scope': 'checked-fixed-native-library', 'compiler_modules_rebuilt': False,
              'native_execution': native_selected or selection == INSTALLED_CLI, 'full_corpus_qualification': False,
              'performance_assertions': False, 'native_toolchain_closure_complete': False,
              'installed_frontend_controls_requested': args.frontend_source_root is not None,
              'framework_selection': selection, 'framework_plan': [selection] if selection else list(inventory),
              'native_cases_passed': [], 'framework_cases_passed': [],
              'commands': []}
    objects, inputs, artifacts = {}, {}, {}
    authenticated = False
    header_preparation = None

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'receipt.json')

    def passed(label, native=False):
        record['framework_cases_passed'].append(label)
        if native:
            record['native_cases_passed'].append(label)
        save()

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
        if header_preparation is not None:
            directory, evidence = header_preparation
            verify_header_validation(ROOT, directory, evidence, expected_inputs=inputs)

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
                 *header_validation_inputs(ROOT).values(), ROOT / 'tools/shared/header_validation_adapter.py',
                 FIXTURES / 'SplitBuiltinControls.hs',
                 FIXTURES / 'native_library_runtime.c', ROOT / 'host/ghc/cbits/host.c',
                 ROOT / 'runtime/mlf_process_supervisor.c', clang, pkg_config, archive,
                 *runtime_sources, *sorted((ROOT / 'runtime').glob('*.h')),
                 *sorted((gc / 'include').rglob('*.h'))]
        paths.append(ROOT / 'tools/testing/receipt_selection.py')
        paths.extend(ROOT / 'tools/shared' / name for name in (
            'source_root_cli.py', 'query_generation.py', 'artifact_binary_reference.py',
            'artifact_binary_typed.py', 'artifact_structure_contract.json'))
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
        if selection not in (SOURCE_CLI, INSTALLED_CLI):
            for label, source in [('host', ROOT / 'host/ghc/cbits/host.c'),
                                  ('supervisor', ROOT / 'runtime/mlf_process_supervisor.c')]:
                target = output / (label + '.o')
                runner.run('compile-' + label, [producer['cc']['path'], '-O2', '-std=c11',
                           '-I' + str(ROOT / 'runtime'), '-c', source, '-o', target], timeout=120)
                transports.append(target)
        artifacts.update({str(p): sha(p) for p in transports})
        header_objects = []
        header_dir = output
        if headers_selected:
            header_dir, header_evidence = prepare_header_validation(ROOT, output)
            verify_header_validation(ROOT, header_dir, header_evidence, expected_inputs=inputs)
            header_preparation = (header_dir, header_evidence)
            record['header_preparation'] = header_evidence
            save()
            artifacts.update({str(p): sha(p) for p in header_dir.iterdir() if p.is_file()})
            for module in ['HistoricalHeaderNames', 'HeaderNamingOracle']:
                obj, hi = [header_dir / (module + suffix) for suffix in ['.o', '.hi']]
                runner.run('compile-' + module, [ghc, '-c', *flags, *EXHAUSTIVENESS_FLAGS,
                           '-i', '-i' + str(producer_dir / 'objects'), '-i' + str(header_dir),
                           '-o', obj, '-ohi', hi, header_dir / (module + '.hs')], timeout=120)
                header_objects.append(obj)
                artifacts.update({str(p): sha(p) for p in [obj, hi]})
        executables = {}
        if selection is None:
            fixture_sources = {name: FIXTURES / (name + '.hs')
                               for name in ['NativeBoundaryTests', 'NativeLibraryRuntime',
                                            'NativePrivateConstructors', 'MaterializeImportsTests',
                                            'PartialMaterializeImportsTests',
                                            'SplitBuiltinControls']}
            fixture_sources.update({name: header_dir / (name + '.hs')
                                    for name in ['HeaderValidationHistorical', 'HeaderValidationCurrent']})
            if args.frontend_source_root is not None:
                fixture_sources['NativeFrontendControls'] = FRONTEND_FIXTURE
        elif native_selected:
            emitter = 'NativePrivateConstructors' if selected_label in PRIVATE_CASES else 'NativeLibraryRuntime'
            fixture_sources = {emitter: FIXTURES / (emitter + '.hs')}
        elif selection == FRONTEND_CASE:
            fixture_sources = {'NativeFrontendControls': FRONTEND_FIXTURE}
        elif selection in (SOURCE_CLI, INSTALLED_CLI):
            fixture_sources = {}
        else:
            selected_fixture = HOST_FIXTURES[selection]
            fixture_directory = header_dir if headers_selected else FIXTURES
            fixture_sources = {selected_fixture: fixture_directory / (selected_fixture + '.hs')}
        for fixture, source in fixture_sources.items():
            obj, hi, executable = [output / (fixture + suffix) for suffix in ['.o', '.hi', '']]
            runner.run('compile-' + fixture, [ghc, '-c', *flags, *EXHAUSTIVENESS_FLAGS,
                       '-i', '-i' + str(producer_dir / 'objects'), '-i' + str(header_dir), '-o', obj, '-ohi', hi,
                       source], timeout=120)
            runner.run('link-' + fixture, [ghc, *flags, '-rtsopts=ignoreAll', obj,
                       *link_objects, *header_objects, *transports, '-o', executable], timeout=120)
            artifacts.update({str(p): sha(p) for p in [obj, hi, executable]})
            executables[fixture] = executable
        if args.frontend_source_root is not None and wants(FRONTEND_CASE):
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
            passed(FRONTEND_CASE)
        else:
            record['installed_frontend_controls_passed'] = False
        cli_case = INSTALLED_CLI if installed else SOURCE_CLI
        if wants(cli_case):
            cli_root = output / cli_case
            cli_root.mkdir()
            cli_runner = CommandRunner(cli_root, output, record, save)
            check_cli = check_installed_root if installed else check_source_root
            check_cli(cli_runner, producer_dir / 'bin/emlf')
            passed(cli_case, native=installed)
        if wants('checked-boundary-controls'):
            runner.run('checked-boundary-controls', [executables['NativeBoundaryTests']],
                       expected=BOUNDARY_OUTPUT, timeout=120)
            passed('checked-boundary-controls')
        if wants('checked-builtin-materialization'):
            runner.run('checked-builtin-materialization', [executables['MaterializeImportsTests']],
                       expected=b'PASS zero-native returned lambda, mixed imports, same-hint distinct identity, wrong mapping rejection, independent check\n',
                       timeout=120)
            passed('checked-builtin-materialization')
        if wants('partial-checked-materialization'):
            runner.run('partial-checked-materialization', [executables['PartialMaterializeImportsTests']],
                       expected=b'PASS partial checked composition, unused prefix pruning, binder identity, nominal weakening and independent checker oracle\n',
                       timeout=120)
            passed('partial-checked-materialization')
        for lane, fixture in [('historical', 'HeaderValidationHistorical'),
                              ('current', 'HeaderValidationCurrent')]:
            label = 'header-validation-' + lane
            if not wants(label):
                continue
            runner.run(label, [executables[fixture]],
                       expected=b'PASS header duplicate errors, entity identity, Unicode naming and forged primitive rejection\n',
                       timeout=120)
            record.setdefault('header_lanes_passed', []).append(lane)
            passed(label)
        if headers_selected:
            record['header_qualification'] = {
                'complete': selection is None,
                'lanes': list(record['header_lanes_passed']),
                'preparation_sha256': artifacts[str(header_dir / 'preparation.json')],
                'scope': 'historical formatter component and current production naming; all original non-naming assertions',
            }
            save()
        if wants('split-builtin-selection-controls'):
            runner.run('split-builtin-selection-controls', [executables['SplitBuiltinControls']],
                       expected=b'PASS recursive SCC atomicity, polymorphic and lazy semantics, selected/full checker parity, incoming dependencies and malformed fragment rejection\n',
                       timeout=120)
            passed('split-builtin-selection-controls')
        if native_selected:
            work = output / 'programs'
            private_work = output / 'private-programs'
            extensions, open_fields, private_cases = EXTENSIONS, OPEN_FIELDS, PRIVATE_CASES
            if selection is None or selected_label not in private_cases:
                work.mkdir()
                command = [executables['NativeLibraryRuntime'], work]
                expected_output = EMIT_OUTPUT
                if selected_label:
                    command.append(selected_label)
                    expected_output = b'PASS emitted selected native library\n'
                    expected_artifacts = [selected_label + '.ll']
                    if selected_label in extensions:
                        expected_artifacts.append('extension-library.ll')
                    if selected_label in open_fields:
                        expected_artifacts.append('open-fields-library.ll')
                else:
                    expected_artifacts = ([label + '.ll' for label, _, _ in CASES]
                                          + [label + '.ll' for label in (*extensions, *open_fields)]
                                          + ['extension-library.ll', 'open-fields-library.ll'])
                runner.run('emit-libraries', command, expected=expected_output, timeout=120)
                if sorted(p.name for p in work.iterdir()) != sorted(expected_artifacts):
                    raise ValueError('native library artifact inventory changed')
                for label, count, _ in CASES:
                    if selected_label is None or selected_label == label:
                        verify_root_shape((work / (label + '.ll')).read_text(), count)
                artifacts.update({str(p): sha(p) for p in work.iterdir()})
            if selection is None or selected_label in private_cases:
                private_work.mkdir()
                command = [executables['NativePrivateConstructors'], private_work]
                if selected_label:
                    command.append(selected_label)
                runner.run('emit-private-boundary', command,
                           expected=b'PASS private constructor boundary emission\n', timeout=120)
                wanted = [selected_label] if selected_label else private_cases
                if sorted(p.name for p in private_work.iterdir()) != sorted(
                        [name + '.ll' for name in wanted] + ['private-library.ll']):
                    raise ValueError('private constructor boundary artifact inventory changed')
                if 'private-escape-demand' in wanted:
                    # Both sites must survive into the actual root, exercising the
                    # escaping site and overwriting an earlier strict-field fact.
                    private_ir = (private_work / 'private-escape-demand.ll').read_text()
                    if ('call ptr @mlf.construct.1(i64 69,' not in private_ir
                            or 'call ptr @mlf_constructor(i64 69, i64 1)' not in private_ir):
                        raise ValueError('private strict-site plus escaping-constructor control became vacuous')
                artifacts.update({str(p): sha(p) for p in private_work.iterdir()})
            cflags = shlex.split(runner.run('gmp-cflags', [pkg_config, '--cflags', 'gmp'], timeout=30).stdout.decode())
            libraries = shlex.split(runner.run('gmp-libs', [pkg_config, '--libs', 'gmp'], timeout=30).stdout.decode())
            common = ['-std=c11', *cflags, '-I' + str(ROOT / 'runtime'), '-I' + str(gc / 'include')]
            for opt in ([selected_opt] if selected_opt else ['0', '2']):
                runtime = output / ('runtime-O' + opt + '.o')
                runner.run('runtime-O' + opt, [clang, '-O' + opt, *common, '-c',
                           ROOT / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
                artifacts[str(runtime)] = sha(runtime)
                for label, count, is_io in CASES:
                    if selected_label and selected_label != label:
                        continue
                    case = label + '-O' + opt
                    binary = output / case
                    runner.run('link-' + case, [clang, '-O' + opt, '-Wno-override-module', *common,
                               '-DEXPORT_COUNT=' + str(count), '-DIO_EXPORT=' + str(int(is_io)),
                               FIXTURES / 'native_library_runtime.c', work / (label + '.ll'),
                               runtime, archive, *libraries, '-lm', '-lpthread', '-ldl', '-o', binary], timeout=120)
                    artifacts[str(binary)] = sha(binary)
                    if selected(label, opt, 'lazy-shared-gc-bounds'):
                        runner.run('run-' + case, [binary], expected=(b'native-action\nnative-action\n' if is_io else b'')
                                   + RUNTIME_OUTPUT, timeout=30)
                        passed(case + ':lazy-shared-gc-bounds', native=True)
                    if count and selected(label, opt, 'demand-fails'):
                        demanded = runner.run('demand-' + case, [binary, 'demand'], status=1, expected=b'', timeout=30)
                        if demanded.stderr != b'Runtime: integer division by zero\n':
                            raise ValueError(case + ': poison demand diagnostic changed')
                        passed(case + ':demand-fails', native=True)
                for label in extensions:
                    if not selected(label, opt, 'installed-value-with-user-datatype'):
                        continue
                    case = label + '-O' + opt
                    binary = output / case
                    runner.run('link-' + case, [clang, '-O' + opt, '-Wno-override-module',
                               work / (label + '.ll'), work / 'extension-library.ll', runtime,
                               archive, *libraries, '-lm', '-lpthread', '-ldl', '-o', binary], timeout=120)
                    artifacts[str(binary)] = sha(binary)
                    runner.run('run-' + case, [binary], expected=b'42\n', timeout=30)
                    passed(case + ':installed-value-with-user-datatype', native=True)
                for label in open_fields:
                    if not selected(label, opt, 'external-lazy-field'):
                        continue
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
                    passed(case + ':external-lazy-field', native=True)
                for label in private_cases:
                    if not selected(label, opt, 'private-constructor-boundary'):
                        continue
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
                    passed(case + ':private-constructor-boundary', native=True)
            record.update(gmp_flags={'cflags': cflags, 'libraries': libraries})
        if record['framework_cases_passed'] != record['framework_plan']:
            raise ValueError('native library exact result inventory changed')
        record.update(artifacts=artifacts, complete=True, status='passed')
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
