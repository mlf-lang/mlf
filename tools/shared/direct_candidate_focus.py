"""Execute one case from the authenticated direct-candidate campaign."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = ROOT / 'tools/testing/language-suites.json'
sys.path.insert(0, str(MANIFEST.parent))
from receipt_selection import identity, select

PREFIX = 'direct-candidate/'
ASYNC_TASK_CASES = ('async-task', 'async-task-processes', 'async-task-wait-graph')
ASYNC_PROCESS_CASES = ('async-process', 'async-process-panic', 'panic-child-reaped')
DELEGATES = {
    'ordered-map': ('test_ordered_map.py', 600, True),
    'bulk-crc': ('test_crc32.py', 600, True),
    'query-json': ('test_query_json.py', 1200, True),
    'byte-array-copy': ('test_byte_array_copy.py', 300, False),
    'utf8-length': ('test_utf8_length.py', 600, True),
    'parser-satisfy': ('test_parser_satisfy.py', 300, False),
    'candidate-selection': ('test_candidate_selection.py', 600, True),
    'metadata-receipt': ('test_metadata_receipt.py', 300, False),
}


def selected_label():
    catalog = json.loads(MANIFEST.read_text())
    return select(PREFIX, catalog['direct-candidate']['receipt']['inventory'])


def async_case(original, runner, receipt, args, label, binaries):
    output = runner.output
    task = label in ASYNC_TASK_CASES
    kind = 'task' if task else 'process'
    source = ROOT / ('tests/async-' + kind) / 'fixture.c'
    fixture = output / (kind + '-fixture')
    compiler = shutil.which(args.cc)
    if compiler is None:
        raise ValueError('missing C fixture compiler: ' + args.cc)
    receipt['fixture_compiler'] = original.identified(compiler)
    receipt['inputs'][receipt['fixture_compiler']['path']] = receipt['fixture_compiler']['sha256']
    receipt['inputs'][str(source)] = original.sha(source)
    runner.run(kind + '-fixture', [receipt['fixture_compiler']['path'], '-O2', '-std=c11',
                                 '-Wall', '-Wextra', '-Werror', source, '-o', fixture])
    receipt['helpers'] = {str(fixture): original.sha(fixture)}

    if label in (*ASYNC_TASK_CASES, 'async-process'):
        index = (*ASYNC_TASK_CASES, 'async-process').index(label)
        oracle = ROOT / original.ORACLES[index]
        expected = oracle.read_bytes()
        receipt['inputs'][str(oracle)] = hashlib.sha256(expected).hexdigest()
        work = output / (label + '-work')
        work.mkdir()
        runner.run(label, [binaries / label], expected=expected,
                   overrides={'MLF_ASYNC_FIXTURE': str(fixture), 'MLF_ASYNC_WORK': str(work)})
        return

    work = output / 'panic-work'
    work.mkdir()
    try:
        result = runner.run('async-process-panic', [binaries / 'async-process-panic'], status=1, expected=b'',
                            overrides={'MLF_ASYNC_FIXTURE': str(fixture), 'MLF_ASYNC_WORK': str(work)})
    finally:
        if label == 'panic-child-reaped':
            receipt['commands'][-1]['prerequisite'] = True
    if b'async-scope-panic' not in result.stderr:
        receipt['commands'][-1].update(state='failed', error='panic failed for unrelated reason')
        raise RuntimeError('panic failed for unrelated reason')
    if label == 'panic-child-reaped':
        runner.run(label, [fixture, 'assert-gone', work / 'panic.pid'])


def run(original, label):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', type=Path, required=True)
    parser.add_argument('--build-receipt', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    parser.add_argument('--clang', default=os.environ.get('CLANG', 'clang'))
    parser.add_argument('--frontend-timeout', type=int)
    args = parser.parse_args()
    if args.frontend_timeout is not None and not 1 <= args.frontend_timeout <= 3600:
        parser.error('frontend timeout must be between 1 and 3600 seconds')
    binaries, output = args.bin_dir.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'format': 1, 'complete': False, 'scope': 'focused',
               'source_mode': 'authenticated direct committed shared source',
               'selected_ids': [identity(PREFIX, label)], 'commands': [], 'inputs': {}, 'helpers': {}}

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(receipt, indent=2) + '\n')
        temporary.replace(output / 'receipt.json')

    save()
    environment = {name: os.environ.pop(name) for name in
                   ('MLF_TEST_EXACT', 'MLF_TEST_SUITE', 'MLF_TEST_EVENTS', 'MLF_TEST_ID_PREFIX')
                   if name in os.environ}
    try:
        if os.name != 'posix':
            raise ValueError('direct candidate qualification requires a POSIX host')
        build_receipt = (args.build_receipt or binaries.parent / 'receipt.json').resolve(strict=True)
        producer = original.authenticate_build(build_receipt, binaries)
        receipt['producer'] = {**original.identified(build_receipt), 'host': producer['producer_host'],
                               'optimization': producer['optimization']}
        receipt['orchestrator'] = original.identified(sys.executable)
        inputs = [Path(__file__).resolve(), Path(original.__file__).resolve(), MANIFEST,
                  MANIFEST.parent / 'receipt_selection.py', HERE / 'test_direct_candidate_successor.py',
                  ROOT / 'shared-sources.json', build_receipt,
                  Path(sys.executable).resolve()]
        receipt['inputs'] = {str(path): original.sha(path) for path in inputs}
        runner = original.CommandRunner(ROOT, output, receipt, save)

        if label in (*ASYNC_TASK_CASES, *ASYNC_PROCESS_CASES):
            async_case(original, runner, receipt, args, label, binaries)
        elif label.startswith('shared-frontend-'):
            name = label.removeprefix('shared-frontend-')
            _, option, expected = next(row for row in original.FRONTEND_CASES if row[0] == name)
            budget = original.frontend_case_timeout(name, producer['optimization'], args.frontend_timeout)
            receipt['execution_budgets'] = {name: budget}
            runner.run(label, [binaries / 'shared-frontend', option], expected=expected, timeout=budget)
        elif label == 'build-receipts':
            script = ROOT / 'tools/release/test-suite-build-receipts.py'
            receipt['inputs'][str(script)] = original.sha(script)
            runner.run(label, [sys.executable, script, '--executable', binaries / label,
                               '--output', output / label], timeout=1800)
        else:
            script_name, timeout, clang = DELEGATES[label]
            script = HERE / script_name
            receipt['inputs'][str(script)] = original.sha(script)
            options = ['--clang', args.clang] if clang else []
            runner.run(label, [sys.executable, '-B', script, '--build-receipt', build_receipt,
                               *options, '--output', output / label], timeout=timeout)

        for collection in (receipt['inputs'], receipt['helpers']):
            if any(original.sha(path) != digest for path, digest in collection.items()):
                raise RuntimeError('test input changed during qualification')
        original.authenticate_build(build_receipt, binaries)
        receipt['complete'] = True
    except BaseException as error:
        receipt['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        os.environ.update(environment)
        save()
