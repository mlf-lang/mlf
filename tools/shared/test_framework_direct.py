#!/usr/bin/env python3
"""Direct shared-framework controls; not full guest/native unit qualification.

Run under a process-tree watchdog. Only a tiny host test entry and authenticated
C transport sources are compiled; producer objects are read-only.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from build import PACKAGES, DEMAND_FLAGS
from test_direct import CommandRunner, authenticate_build

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/testing'))
import events

CASE_PREFIX = 'framework-direct/'


def selected_cases(selection, exact=None):
    names = ['tuple-static', 'host-classes']
    if selection != 'controls':
        names.append('tuple-registry')
    if selection != 'default':
        names.append('tuple-cli')
    names.append('producer-receipt')
    ids = [CASE_PREFIX + name for name in names]
    if exact is not None and exact not in ids:
        raise ValueError('unknown framework case: ' + exact)
    return [exact] if exact else ids


@contextmanager
def observed(name, record):
    first = len(record['commands'])
    identity = CASE_PREFIX + name
    events.start(identity)
    try:
        yield
    except Exception as error:
        commands = record['commands'][first:]
        command = commands[-1] if commands else {}
        status = 'timeout' if command.get('timed_out') else 'crash' if (command.get('exit_code') or 0) < 0 else 'fail'
        events.result(identity, status, detail=str(error), commands=commands)
        raise
    else:
        events.result(identity, 'pass', commands=record['commands'][first:])

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def selected_suites(selection):
    if selection not in ('all', 'default', 'framework', 'controls'):
        raise ValueError('unknown framework suite selection')
    return ('default', 'framework') if selection == 'all' else (selection,)


def suite_timeout(optimization, override=None):
    if optimization not in ('0', '2'):
        raise ValueError('unsupported authenticated optimization level')
    maximum = 5400 if optimization == '0' else 900
    if override is not None and (type(override) is not int or not 1 <= override <= maximum):
        raise ValueError('suite timeout must be between 1 and ' + str(maximum) + ' seconds')
    return override if override is not None else (4500 if optimization == '0' else 600)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-receipt', type=Path)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--list-cases', action='store_true')
    ap.add_argument('--suite', choices=['all', 'default', 'framework', 'controls'], default='all',
                    help='Exact coverage partition; all remains the default.')
    ap.add_argument('--suite-timeout', type=int,
                    help='Bound each selected suite: authenticated O0 defaults4500 (max5400), O2 defaults600 (max900).')
    args = ap.parse_args()
    try:
        ids_selected = selected_cases(args.suite, os.environ.get('MLF_TEST_EXACT'))
    except ValueError as error:
        ap.error(str(error))
    if args.list_cases:
        print(json.dumps(ids_selected))
        return
    if args.build_receipt is None or args.output is None:
        ap.error('--build-receipt and --output are required')
    events.plan(ids_selected)

    def selected(name):
        return CASE_PREFIX + name in ids_selected

    if args.suite_timeout is not None and not 1 <= args.suite_timeout <= 5400:
        ap.error('suite timeout must be between 1 and 5400 seconds')
    suites = selected_suites(args.suite)
    receipt = args.build_receipt.resolve(strict=True)
    producer_dir = receipt.parent
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {'complete': False, 'full_native_unit': False, 'selected_case_ids': ids_selected, 'commands': []}
    def save():
        (output/'receipt.json').write_text(json.dumps(record, indent=2)+'\n')
    runner = CommandRunner(ROOT, output, record, save)
    def run(label, command, status=0, overrides=None, timeout=120):
        # Share the bounded process-group watchdog and exact status/stderr
        # contract with the direct gate; suite-specific output checks remain
        # below, including expected-failure controls with their original status.
        return runner.run(label, command, status=status, timeout=timeout, overrides=overrides).stdout
    try:
        producer = authenticate_build(receipt, producer_dir/'bin')
        budget = suite_timeout(producer['optimization'], args.suite_timeout)
        record.update(selected_suites=list(suites), execution_budget=budget,
                      suite_timeout_seconds=budget, suite_timeout_request=args.suite_timeout,
                      suite_timeout_policy='authenticated-producer-optimization-v1',
                      coverage_scope='full' if args.suite == 'all' and not os.environ.get('MLF_TEST_EXACT') else 'partition')
        save()
        objects = producer['object_inputs']
        def check_objects():
            for name, sha in objects.items():
                path = (producer_dir/name).resolve(strict=True)
                if not path.is_relative_to(producer_dir) or digest(path) != sha:
                    raise ValueError('producer object changed: '+name)
        check_objects()
        inputs = [Path(__file__), ROOT/'tools/shared/FrameworkDirect.hs', ROOT/'tools/shared/test_direct.py',
                  ROOT/'tools/shared/build.py', ROOT/'tools/testing/check_tuple_list_migration.py',
                  ROOT/'tools/testing/tuple-list-active-contract.json',
                  ROOT/'tests/Tests/TupleList.hs', ROOT/'tools/testing/events.py',
                  ROOT/'tests/MLF/Entry/TupleList.hs']
        hashes = {str(p.resolve().relative_to(ROOT)):digest(p) for p in inputs}
        record.update(producer_receipt_sha256=digest(receipt), inputs=hashes, object_inputs=objects,
                      optimization=producer['optimization'])
        if selected('tuple-static'):
            with observed('tuple-static', record):
                run('static-oracle-contract', [sys.executable, ROOT/'tools/testing/check_tuple_list_migration.py'])
        contract = json.loads((ROOT/'tools/testing/tuple-list-active-contract.json').read_text())
        framework_count = contract['framework_count']
        legacy_count = contract['legacy_pass_count']
        ids = re.findall(r'leaf\s+"([^"]+)"', (ROOT/'tests/Tests/TupleList.hs').read_text())
        if ids != contract['framework_ids'] or len(ids) != framework_count or len(set(ids)) != framework_count:
            raise ValueError('reviewed registry inventory changed')
        artifacts = {}
        if selected('host-classes'):
            with observed('host-classes', record):
                flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
                         '-no-user-package-db', '-hide-all-packages', '-O'+producer['optimization'], *DEMAND_FLAGS]
                for package in PACKAGES:
                    flags += ['-package', package]
                ghc = producer['ghc']['path']
                obj = output/'FrameworkDirect.o'
                run('compile-harness', [ghc, '-c', *flags, '-i', '-i'+str(producer_dir/'objects'), '-o', obj,
                    '-ohi', output/'FrameworkDirect.hi', ROOT/'tools/shared/FrameworkDirect.hs'])
                link_objects = [producer_dir/n for n in sorted(objects) if n.endswith('.o') and n != 'objects/Main.o']
                transport = []
                for label, source in [('host', ROOT/'host/ghc/cbits/host.c'), ('supervisor', ROOT/'runtime/mlf_process_supervisor.c')]:
                    target = output/(label+'.o')
                    run('c-'+label, [producer['cc']['path'], '-O2', '-std=c11', '-I'+str(ROOT/'runtime'), '-c', source, '-o', target])
                    transport.append(target)
                executable = output/'framework-direct'
                run('link-harness', [ghc, *flags, '-rtsopts=ignoreAll', obj, *link_objects, *transport, '-o', executable])
                artifacts = {str(p):digest(p) for p in [executable, obj, *transport]}
                stdout = run('class-demand-IO-controls', [executable])
                harness_lines = stdout.splitlines()
                if len(harness_lines) != 2 or harness_lines[-1] != b'Framework standard-class, demand, IO-order, discovery and continuation controls passed.':
                    raise ValueError('harness completion marker changed')
                harness_inventory = json.loads(harness_lines[0])
                if harness_inventory.get('schema_version') != 1 or harness_inventory.get('event') != 'inventory' or [x['id'] for x in harness_inventory['cases']] != ['probe/fail','probe/after']:
                    raise ValueError('actual discovery control output invalid')
        binary = producer_dir/'bin/tuple-list'
        if selected('tuple-registry'):
            with observed('tuple-registry', record):
                report = output/'framework-report.jsonl'
                if args.suite == 'framework':
                    full = run('framework', [binary, '--framework', '--format', 'json', '--report', report], timeout=budget)
                    if report.read_bytes() != full:
                        raise ValueError('report/stdout disagreement')
                else:
                    default = run('default', [binary], timeout=budget, overrides={'MLF_TUPLE_LIST_REPORT': str(report)})
                    passed = [line.split(None, 2)[1].decode() for line in default.splitlines() if line.startswith(b'PASS tuple-list/')]
                    if passed != ids or not default.endswith(b'Tuple/list focused checks passed.\n'):
                        raise ValueError('default active registry observation inventory changed')
                    full = report.read_bytes()
                artifacts[str(report)] = digest(report)
                rows = [json.loads(line) for line in full.splitlines()]
                if any(row.get('schema_version') != 1 for row in rows) or rows[0]['event'] != 'start' or rows[0]['ids'] != ids or len(rows) != framework_count + 2:
                    raise ValueError('framework start/inventory changed')
                if [row['id'] for row in rows[1:-1]] != ids or any(row.get('event') != 'case' or row.get('schema_version') != 1 or row['status'] != 'passed' for row in rows[1:-1]):
                    raise ValueError('framework cases failed or changed identity')
                summary = rows[-1]
                if summary['event'] != 'summary' or summary['complete'] is not True or any(summary[k] != v for k,v in {'total':framework_count,'selected':framework_count,'executed':framework_count,'passed':framework_count,'failed':0,'scope':'full'}.items()):
                    raise ValueError('framework terminal summary invalid')
        if selected('tuple-cli'):
            with observed('tuple-cli', record):
                inventory = json.loads(run('discovery', [binary, '--framework-list', '--format', 'json']))
                if inventory.get('schema_version') != 1 or inventory['event'] != 'inventory' or inventory['total'] != framework_count or inventory['selected'] != framework_count or [x['id'] for x in inventory['cases']] != ids:
                    raise ValueError('discovery identity inventory changed')
                partial = [json.loads(line) for line in run('exact-selection', [binary, '--framework', '--format', 'json', '--exact', ids[0]]).splitlines()]
                if (len(partial) != 3 or partial[0].get('event') != 'start' or partial[0].get('ids') != [ids[0]]
                    or partial[1].get('event') != 'case' or partial[1].get('id') != ids[0] or partial[1].get('status') != 'passed'
                    or partial[-1].get('event') != 'summary' or partial[-1].get('complete') is not True
                    or any(row.get('schema_version') != 1 for row in partial)
                    or any(partial[-1].get(k) != v for k,v in {'total':framework_count,'selected':1,'executed':1,'passed':1,'failed':0,'scope':'partial'}.items())):
                    raise ValueError('exact selection identity/scope changed')
                for label, argv in [('unknown',['--unknown']), ('empty',['--exact','']), ('absent',['--exact','not-registered'])]:
                    run('reject-'+label, [binary, '--framework', *argv], status=2)
                run('report-write-failure', [binary, '--framework-list', '--report', output/'missing-parent/report.json'], status=1)
        def authenticate_receipt():
            authenticate_build(receipt, producer_dir/'bin')
            check_objects()
            if digest(receipt) != record['producer_receipt_sha256'] or any(digest(ROOT/p) != h for p,h in hashes.items()) or any(digest(p) != h for p,h in artifacts.items()):
                raise ValueError('inputs or produced test artifacts changed during run')

        if selected('producer-receipt'):
            with observed('producer-receipt', record):
                authenticate_receipt()
        else:
            authenticate_receipt()
        checks = framework_count if selected('tuple-registry') else 0
        record.update(complete=True, registry_checks=checks, legacy_observations=legacy_count,
                      default_checks=checks if args.suite != 'framework' else 0,
                      framework_checks=checks if args.suite == 'framework' else 0,
                      discovery_only=selected('tuple-cli'), exact_selection=selected('tuple-cli'),
                      standard_class_demand_IO_controls=selected('host-classes'), artifacts=artifacts)
    except BaseException as error:
        record['error'] = type(error).__name__+': '+str(error)
        raise
    finally:
        save()

if __name__ == '__main__':
    main()
