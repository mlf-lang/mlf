#!/usr/bin/env python3
"""Authenticated, serial GHC-hosted frontend/provenance/source-smoke controls.

This runs no compiler build, LLVM compilation, native bootstrap, or async
fixture campaign. Use the outer task process-tree resource watchdog. Source
smoke outputs and all receipts are owned by the new --output directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import types
import unittest

sys.dont_write_bytecode = True


def sha(path):
    return hashlib.file_digest(Path(path).open('rb'), 'sha256').hexdigest()


def load_source(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def provenance_child(source, output):
    """Execute every maintained test_provenance.py unittest exactly once.

    Its normal unittest.main also uses this default loader. A tracking result
    records method IDs and routes unittest's ordinary report to stdout so real
    unexpected stderr remains a failure under the unchanged bounded runner.
    The 17 imported builtin verifier methods are included, not run separately.
    """
    module = load_source(source / 'tools/shared/test_provenance.py', 'scoped_provenance_tests')
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)

    def leaves(node):
        if isinstance(node, unittest.TestSuite):
            for child in node:
                yield from leaves(child)
        else:
            yield node

    expected = [test.id() for test in leaves(suite)]
    builtin = [name for name in expected if '.BuiltinPreludeVerification.' in name]
    if len(expected) != 86 or len(set(expected)) != 86 or len(builtin) != 17:
        raise ValueError('maintained provenance inventory changed; re-review required')
    record = {'format': 'scoped-provenance-methods-v1', 'complete': False,
              'scope': 'unittest methods, not subtest-input count or compiler semantic cases',
              'expected_ids': expected, 'expected_distinct_methods': 86,
              'builtin_verifier_ids': builtin, 'builtin_verifier_methods': 17,
              'other_provenance_methods': 69,
              'started_ids': [], 'passed_ids': [], 'failed_ids': [], 'skipped_ids': []}

    def save():
        output.write_text(json.dumps(record, indent=2) + '\n')

    save()

    class TrackingResult(unittest.TextTestResult):
        def startTest(self, test):
            record['started_ids'].append(test.id())
            save()
            super().startTest(test)

        def addSuccess(self, test):
            record['passed_ids'].append(test.id())
            save()
            super().addSuccess(test)

        def addFailure(self, test, error):
            record['failed_ids'].append(test.id())
            save()
            super().addFailure(test, error)

        def addError(self, test, error):
            record['failed_ids'].append(test.id())
            save()
            super().addError(test, error)

        def addSkip(self, test, reason):
            record['skipped_ids'].append({'id': test.id(), 'reason': reason})
            save()
            super().addSkip(test, reason)

    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2, resultclass=TrackingResult).run(suite)
    record.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  unexpected_successes=len(result.unexpectedSuccesses), expected_failures=len(result.expectedFailures))
    record['complete'] = (result.wasSuccessful() and result.testsRun == 86 and
                          record['started_ids'] == expected and record['passed_ids'] == expected and
                          not record['failed_ids'] and not record['skipped_ids'] and
                          not result.expectedFailures and not result.unexpectedSuccesses)
    save()
    if not record['complete']:
        raise RuntimeError('provenance methods failed, skipped, changed, or incomplete')
    print('Scoped provenance controls passed: 86 distinct methods = 69 provenance + 17 builtin verifier; no double-counting.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve(strict=True)
    producer_dir = args.producer.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or any(output.is_relative_to(root) or root.is_relative_to(output)
                              for root in [source, producer_dir]):
        parser.error('output must be absent and separate from source and producer')
    output.mkdir(parents=True)
    shutil.copy2(__file__, output / 'runner-used.py')
    producer_receipt = producer_dir / 'receipt.json'
    record = {'format': 'scoped-frontend-controls-v1', 'complete': False,
              'scope': 'partial GHC-hosted frontend, interpreter demand, provenance and five source-smoke cases',
              'full_native_unit': False, 'llvm_execution': False, 'compiler_bootstrap': False,
              'compiler_build_performed': False, 'commands': [], 'source_root': str(source),
              'producer_directory': str(producer_dir), 'output_directory': str(output)}

    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    save()
    authenticated = False
    passed = False
    direct = None
    pins = {}
    try:
        direct = load_source(source / 'tools/shared/test_direct.py', 'scoped_direct_contracts')
        producer = direct.authenticate_build(producer_receipt, producer_dir / 'bin', root=source)
        authenticated = True
        if producer['optimization'] != '2':
            raise ValueError('this scoped candidate gate requires an authenticated O2 producer')
        # Include all actual compiled source/configuration pins plus every new
        # control/oracle read not necessarily part of the compiler build.
        for field in ['shared_inputs', 'host_inputs', 'configuration_inputs', 'builtin_verification_helpers']:
            for item in producer[field].values():
                path = Path(item['path'])
                pins[str(path)] = sha(path)
                if pins[str(path)] != item['sha256']:
                    raise ValueError('producer input changed before controls: ' + str(path))
        extra = [Path(__file__).resolve(), producer_receipt, Path(sys.executable).resolve(),
                 source / '.github/workflows/ci.yml',
                 *[source / 'tools/shared' / name for name in
                   ['test_provenance.py', 'test_builtin_prelude_verification.py', 'test_direct.py',
                    'build.py', 'builtin_prelude_identity.py', 'verify_builtin_prelude.py']],
                 *sorted((source / 'tests/pr-smoke').glob('*'))]
        for path in extra:
            if path.is_file():
                pins[str(path)] = sha(path)
        budgets = {name: direct.frontend_case_timeout(name, producer['optimization'])
                   for name, _, _ in direct.FRONTEND_CASES}
        if [(name, mode) for name, mode, _ in direct.FRONTEND_CASES] != [
                ('frontend', '--frontend'), ('native-first', '--native-first'), ('native-second', '--native-second')]:
            raise ValueError('maintained frontend partition changed')
        record.update(producer_receipt_sha256=sha(producer_receipt), authenticated_before=True,
                      inputs=pins, frontend_budgets=budgets,
                      expected_frontend_stdout={name: expected.decode('utf-8')
                                                for name, _, expected in direct.FRONTEND_CASES},
                      environment={'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8',
                                   'PYTHONDONTWRITEBYTECODE': '1', 'OMP_NUM_THREADS': '1',
                                   'OPENBLAS_NUM_THREADS': '1'})
        save()
        # All commands run in owned output, not source/.mlf-build. The maintained
        # process helper checks exact exit status/expected stdout/empty stderr,
        # records CPU/elapsed separately and bounds original-group cleanup.
        runner = direct.CommandRunner(output, output, record, save)
        env = record['environment']
        for name, mode, expected in direct.FRONTEND_CASES:
            runner.run('shared-frontend-'+name, [producer_dir / 'bin/shared-frontend', mode],
                       expected=expected, timeout=budgets[name], overrides=env)
        record['frontend_modes_passed'] = [name for name, _, _ in direct.FRONTEND_CASES]
        record['native_named_modes_endpoint'] = 'Bootstrap.Runtime interpreter, not LLVM/native output'
        save()

        provenance_output = output / 'provenance-methods.json'
        runner.run('provenance', [sys.executable, Path(__file__).resolve(), '--provenance-child',
                   source, provenance_output], timeout=300, overrides=env)
        methods = json.loads(provenance_output.read_text())
        if not methods['complete'] or methods['expected_distinct_methods'] != 86 or methods['builtin_verifier_methods'] != 17:
            raise ValueError('provenance method receipt incomplete')
        record['provenance'] = {'receipt': str(provenance_output), 'sha256': sha(provenance_output),
                                'distinct_methods': 86, 'builtin_verifier_methods_included': 17,
                                'other_provenance_methods': 69, 'separate_builtin_reexecution': False}
        save()

        smoke = output / 'source-smoke'
        smoke.mkdir()
        expected_smoke = (
            b'PASS current-source accepted polymorphic-let\n'
            b'PASS current-source accepted impredicative-self-application\n'
            b'PASS current-source rejected monomorphic-mismatch\n'
            b'PASS current-source rejected invalid-universal-annotation\n'
            b'PASS current-source malformed target\n'
            b'PR current-source smoke passed: 2 accepted, 2 rejected, 1 malformed target.\n')
        runner.run('source-smoke', [producer_dir / 'bin/source-smoke', source / 'tests/pr-smoke', smoke],
                   expected=expected_smoke, timeout=600, overrides=env)
        expected_files = {'polymorphic-let.xmlf', 'impredicative-self-application.xmlf', 'progress.log'}
        if {path.name for path in smoke.iterdir()} != expected_files:
            raise ValueError('source-smoke artifact inventory changed')
        if (smoke / 'progress.log').read_bytes() != b'Completed all five current-source cases\n':
            raise ValueError('source-smoke did not reach final progress state')
        record['source_smoke'] = {'cases': 5, 'accepted': 2, 'source_rejected': 2, 'malformed_target': 1,
                                  'artifacts': {path.name: sha(path) for path in sorted(smoke.iterdir())},
                                  'output_owned_outside_source': True}
        passed = True
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        # Even a failing control must retain a post-run provenance outcome.
        if authenticated:
            try:
                direct.authenticate_build(producer_receipt, producer_dir / 'bin', root=source)
                for path, digest in pins.items():
                    if sha(path) != digest:
                        raise ValueError('control input changed during execution: ' + path)
                record['authenticated_after'] = True
                record['immutable_inputs_verified_after'] = True
            except BaseException as error:
                record['authenticated_after'] = False
                record['post_authentication_error'] = {'type': type(error).__name__, 'message': str(error)}
                passed = False
                if 'error' not in record:
                    record['error'] = record['post_authentication_error']
        record['complete'] = passed and record.get('authenticated_after', False)
        save()
    if not record['complete']:
        raise RuntimeError('post-run authentication failed; inspect retained receipt')
    print(json.dumps({'complete': True, 'scope': record['scope'], 'frontend_modes': 3,
                      'provenance_distinct_methods': 86, 'builtin_methods_included': 17,
                      'source_smoke_cases': 5}, indent=2))


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--provenance-child':
        provenance_child(Path(sys.argv[2]).resolve(strict=True), Path(sys.argv[3]).resolve())
    else:
        main()
