#!/usr/bin/env python3
"""Python-only controls for the direct framework gate; no GHC/native campaign.

Exercise the real main and real reviewed source contract. Only command execution
and producer authentication are faked. Fixtures and expected dispatch are authored
here, not obtained from the gate's selection or timeout helpers. Real process-tree
cleanup/authentication controls live in test_provenance.py.
"""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_framework_direct as gate

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / 'tools/testing/tuple-list-active-contract.json'
CONTRACT = json.loads(CONTRACT_PATH.read_text())
IDS = CONTRACT['framework_ids']
COMMON = ['static-oracle-contract', 'compile-harness', 'c-host', 'c-supervisor',
          'link-harness', 'class-demand-IO-controls']
FRAMEWORK = ['discovery', 'framework', 'exact-selection', 'reject-unknown',
             'reject-empty', 'reject-absent', 'report-write-failure']
EXPECTED_DISPATCH = {
    'all': COMMON + ['default'] + FRAMEWORK,
    'default': COMMON + ['default'],
    'framework': COMMON + FRAMEWORK,
}
EXPECTED_ERRORS = {'reject-unknown': 2, 'reject-empty': 2,
                   'reject-absent': 2, 'report-write-failure': 1}
HARNESS_MARKER = b'Framework standard-class, demand, IO-order, discovery and continuation controls passed.\n'


def json_lines(rows):
    return b''.join((json.dumps(row) + '\n').encode() for row in rows)


def successful_rows(ids, scope):
    count = len(ids)
    return [dict(schema_version=1, event='start', ids=list(ids))] + [
        dict(schema_version=1, event='case', id=case_id, status='passed')
        for case_id in ids
    ] + [dict(schema_version=1, event='summary', total=105, selected=count,
              executed=count, passed=count, failed=0, scope=scope, complete=True)]


def successful_outputs():
    return {
        'class-demand-IO-controls': json_lines([
            dict(schema_version=1, event='inventory', total=2, selected=2,
                 cases=[{'id': 'probe/fail'}, {'id': 'probe/after'}])
        ]) + HARNESS_MARKER,
        'default': b''.join(b'PASS tuple/list fixture-' + str(i).encode() + b'\n'
                            for i in range(305)) + b'Tuple/list focused checks passed.\n',
        'discovery': json_lines([dict(schema_version=1, event='inventory', total=105,
                                     selected=105, cases=[{'id': name} for name in IDS])]),
        'framework': json_lines(successful_rows(IDS, 'full')),
        'exact-selection': json_lines(successful_rows(IDS[:1], 'partial')),
    }


class MainFixture:
    """A minimal on-disk producer plus independent canned command responses."""
    def __init__(self, test, optimization='2'):
        temporary = tempfile.TemporaryDirectory(prefix='mlf-framework-control-')
        test.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.producer_dir = self.root / 'producer'
        self.output = self.root / 'result'
        (self.producer_dir / 'objects').mkdir(parents=True)
        (self.producer_dir / 'bin').mkdir()
        self.object_file = self.producer_dir / 'objects/Fixture.o'
        self.object_file.write_bytes(b'unchanged producer object\n')
        (self.producer_dir / 'bin/tuple-list').write_bytes(b'not an executable\n')
        self.producer = {
            'optimization': optimization,
            'object_inputs': {'objects/Fixture.o': hashlib.sha256(self.object_file.read_bytes()).hexdigest()},
            'ghc': {'path': '/fake/ghc'}, 'cc': {'path': '/fake/cc'},
        }
        self.build_receipt = self.producer_dir / 'receipt.json'
        self.build_receipt.write_text(json.dumps(self.producer))
        self.outputs = successful_outputs()
        self.events, self.calls, self.auth_calls = [], [], []
        self.returncodes = dict(EXPECTED_ERRORS)
        self.report_bytes = None
        self.auth_error_at = None
        self.on_final_auth = None

    def authenticate(self, receipt, binaries):
        self.events.append('authenticate')
        self.auth_calls.append((receipt, binaries))
        if self.auth_error_at == len(self.auth_calls):
            raise ValueError('fixture authentication rejected')
        if len(self.auth_calls) == 2 and self.on_final_auth:
            self.on_final_auth()
        return copy.deepcopy(self.producer)

    def runner(self, root, output, record, save):
        assert root == ROOT and output == self.output

        def run(label, command, *, status=0, timeout=120):
            command = list(map(str, command))
            call = dict(name=label, argv=command, status=status, timeout_seconds=timeout)
            self.events.append(label)
            self.calls.append(call)
            record['commands'].append(call)
            save()
            # Produce only test artifacts, so the gate's actual digest checks run.
            if label in ('compile-harness', 'c-host', 'c-supervisor', 'link-harness'):
                for flag in ('-o', '-ohi'):
                    if flag in command:
                        Path(command[command.index(flag) + 1]).write_bytes((label + flag).encode())
            stdout = self.outputs.get(label, b'')
            if label == 'framework':
                report = Path(command[command.index('--report') + 1])
                report.write_bytes(stdout if self.report_bytes is None else self.report_bytes)
            actual_status = self.returncodes.get(label, 0)
            call['exit_code'] = actual_status
            if actual_status != status:
                call['state'] = 'failed'
                raise RuntimeError('fixture unexpected status: ' + label)
            call['state'] = 'passed'
            return SimpleNamespace(stdout=stdout, returncode=actual_status)
        return SimpleNamespace(run=run)

    def execute(self, *arguments):
        argv = ['test_framework_direct.py', '--build-receipt', str(self.build_receipt),
                '--output', str(self.output), *arguments]
        with patch.object(sys, 'argv', argv), \
                patch.object(gate, 'CommandRunner', side_effect=self.runner), \
                patch.object(gate, 'authenticate_build', side_effect=self.authenticate), \
                contextlib.redirect_stderr(io.StringIO()):
            gate.main()
        return self.receipt()

    def receipt(self):
        return json.loads((self.output / 'receipt.json').read_text())

    def replace_rows(self, label, mutation):
        rows = [json.loads(line) for line in self.outputs[label].splitlines()]
        mutation(rows)
        self.outputs[label] = json_lines(rows)


class FrameworkMainControls(unittest.TestCase):
    def assert_failed(self, fixture, *arguments, error=ValueError, message=None):
        with self.assertRaises(error) as caught:
            fixture.execute(*arguments)
        if message:
            self.assertIn(message, str(caught.exception))
        receipt = fixture.receipt()
        self.assertFalse(receipt['complete'])
        self.assertFalse(receipt['full_native_unit'])
        self.assertIn(type(caught.exception).__name__, receipt['error'])
        return receipt

    def test_fixture_tracks_reviewed_305_and_105_contract_and_actual_ids(self):
        self.assertEqual(CONTRACT['legacy_pass_count'], 305)
        self.assertEqual(CONTRACT['framework_count'], 105)
        self.assertEqual(len(IDS), 105)
        self.assertEqual(len(set(IDS)), 105)
        source = (ROOT / 'tests/Tests/TupleList.hs').read_text()
        self.assertEqual(re.findall(r'leaf\s+"([^"]+)"', source), IDS)
        self.assertEqual(IDS[0], 'tuple-list/focused/pair-ast')

    def test_omitted_suite_preserves_old_all_dispatch(self):
        fixture = MainFixture(self)
        receipt = fixture.execute()
        self.assertEqual([call['name'] for call in fixture.calls], EXPECTED_DISPATCH['all'])
        calls = {call['name']: call for call in fixture.calls}
        self.assertEqual(calls['default']['argv'], [str(fixture.producer_dir / 'bin/tuple-list')])
        self.assertEqual(calls['static-oracle-contract']['argv'],
                         [sys.executable, str(ROOT / 'tools/testing/check_tuple_list_migration.py')])
        self.assertEqual(calls['class-demand-IO-controls']['argv'], [str(fixture.output / 'framework-direct')])
        self.assertEqual(receipt['selected_suites'], ['default', 'framework'])
        self.assertEqual((receipt['default_checks'], receipt['framework_checks']), (305, 105))
        self.assertEqual(receipt['coverage_scope'], 'full')

    def test_all_and_disjoint_shards_preserve_exact_union_and_shared_controls(self):
        heavy = {}
        for selection, counts in [('all', (305, 105)), ('default', (305, 0)), ('framework', (0, 105))]:
            with self.subTest(selection=selection):
                fixture = MainFixture(self)
                receipt = fixture.execute('--suite', selection)
                labels = [call['name'] for call in fixture.calls]
                self.assertEqual(labels, EXPECTED_DISPATCH[selection])
                heavy[selection] = [label for label in labels if label in ('default', 'framework')]
                self.assertTrue(receipt['complete'])
                self.assertFalse(receipt['full_native_unit'])
                self.assertEqual((receipt['default_checks'], receipt['framework_checks']), counts)
                self.assertEqual(receipt['selected_suites'], ['default', 'framework'] if selection == 'all' else [selection])
                self.assertEqual(receipt['coverage_scope'], 'full' if selection == 'all' else 'partition')
                self.assertTrue(receipt['standard_class_demand_IO_controls'])
                self.assertEqual(receipt['discovery_only'], selection != 'default')
                self.assertEqual(receipt['exact_selection'], selection != 'default')
        self.assertEqual(heavy['default'], ['default'])
        self.assertEqual(heavy['framework'], ['framework'])
        self.assertFalse(set(heavy['default']) & set(heavy['framework']))
        self.assertEqual(heavy['all'], heavy['default'] + heavy['framework'])

    def test_producer_authentication_brackets_every_successful_partition(self):
        for selection in ('all', 'default', 'framework'):
            with self.subTest(selection=selection):
                fixture = MainFixture(self)
                fixture.execute('--suite', selection)
                self.assertEqual(fixture.events, ['authenticate', *EXPECTED_DISPATCH[selection], 'authenticate'])
                self.assertEqual(fixture.auth_calls, [(fixture.build_receipt, fixture.producer_dir / 'bin')] * 2)

    def test_o2_budget_is_unchanged_for_both_heavy_suites(self):
        fixture = MainFixture(self, '2')
        receipt = fixture.execute()
        self.assertEqual(receipt['execution_budget'], 600)
        self.assertEqual({call['name']: call['timeout_seconds'] for call in fixture.calls
                          if call['name'] in ('default', 'framework')}, {'default': 600, 'framework': 600})
        self.assertTrue(all(call['timeout_seconds'] == 120 for call in fixture.calls
                            if call['name'] not in ('default', 'framework')))

    def test_o0_budget_and_compile_flags_come_from_authenticated_producer(self):
        fixture = MainFixture(self, '0')
        # The authenticated result, not an unauthenticated receipt hint, wins.
        fixture.build_receipt.write_text('{"optimization":"2"}')
        receipt = fixture.execute()
        self.assertEqual(receipt['optimization'], '0')
        self.assertEqual(receipt['execution_budget'], 4500)
        for call in fixture.calls:
            if call['name'] in ('default', 'framework'):
                self.assertEqual(call['timeout_seconds'], 4500)
            if call['name'] in ('compile-harness', 'link-harness'):
                self.assertIn('-O0', call['argv'])
                self.assertNotIn('-O2', call['argv'])

    def test_bounded_overrides_include_both_endpoints(self):
        for optimization, budget in [('0', 1), ('0', 5400), ('2', 1), ('2', 900), ('2', 37)]:
            with self.subTest(optimization=optimization, budget=budget):
                fixture = MainFixture(self, optimization)
                receipt = fixture.execute('--suite-timeout', str(budget))
                self.assertEqual(receipt['execution_budget'], budget)
                self.assertEqual([call['timeout_seconds'] for call in fixture.calls
                                  if call['name'] in ('default', 'framework')], [budget, budget])

    def test_o0_framework_override_preserves_other_command_budgets_and_coverage(self):
        fixture = MainFixture(self, '0')
        receipt = fixture.execute('--suite', 'framework', '--suite-timeout', '5400')
        self.assertEqual(receipt['execution_budget'], 5400)
        self.assertEqual(receipt['selected_suites'], ['framework'])
        self.assertEqual((receipt['default_checks'], receipt['framework_checks']), (0, 105))
        self.assertEqual(fixture.events, ['authenticate', *EXPECTED_DISPATCH['framework'], 'authenticate'])
        self.assertEqual({call['name']: call['timeout_seconds'] for call in fixture.calls},
                         {label: 5400 if label == 'framework' else 120 for label in EXPECTED_DISPATCH['framework']})
        self.assertTrue(receipt['complete'])
        self.assertFalse(receipt['full_native_unit'])

    def test_o0_partition_defaults_remain_4500_without_explicit_override(self):
        for selection in ('default', 'framework'):
            with self.subTest(selection=selection):
                fixture = MainFixture(self, '0')
                receipt = fixture.execute('--suite', selection)
                self.assertEqual(receipt['execution_budget'], 4500)
                self.assertEqual({call['name']: call['timeout_seconds'] for call in fixture.calls
                                  if call['name'] in ('default', 'framework')}, {selection: 4500})

    def test_invalid_cli_fails_before_authentication_or_execution(self):
        arguments = [('--suite', 'unknown'), ('--suite', 'default,framework'),
                     ('--suite-timeout', '0'), ('--suite-timeout', '-1'),
                     ('--suite-timeout', '5401'), ('--suite-timeout', '1.5'),
                     ('--optimization', '0')]
        for arguments in arguments:
            with self.subTest(arguments=arguments):
                fixture = MainFixture(self)
                with self.assertRaises(SystemExit) as caught:
                    fixture.execute(*arguments)
                self.assertEqual(caught.exception.code, 2)
                self.assertEqual(fixture.events, [])
                self.assertFalse(fixture.output.exists())

    def test_o2_oversized_budget_fails_before_any_command(self):
        for budget in (901, 5400):
            for selection in ('all', 'default', 'framework'):
                with self.subTest(budget=budget, selection=selection):
                    fixture = MainFixture(self, '2')
                    fixture.build_receipt.write_text('{"optimization":"0"}')
                    self.assert_failed(fixture, '--suite', selection, '--suite-timeout', str(budget), message='900')
                    self.assertEqual(fixture.events, ['authenticate'])

    def test_unknown_authenticated_optimization_fails_before_any_command(self):
        fixture = MainFixture(self, '1')
        self.assert_failed(fixture, message='unsupported authenticated optimization')
        self.assertEqual(fixture.events, ['authenticate'])

    def test_initial_authentication_failure_prevents_execution(self):
        fixture = MainFixture(self)
        fixture.auth_error_at = 1
        self.assert_failed(fixture, message='authentication rejected')
        self.assertEqual(fixture.events, ['authenticate'])

    def test_final_authentication_failure_never_marks_partition_complete(self):
        fixture = MainFixture(self)
        fixture.auth_error_at = 2
        self.assert_failed(fixture, '--suite', 'framework', message='authentication rejected')
        self.assertEqual(fixture.events, ['authenticate', *EXPECTED_DISPATCH['framework'], 'authenticate'])

    def test_expected_error_statuses_and_original_command_arguments_preserved(self):
        fixture = MainFixture(self)
        fixture.execute('--suite', 'framework')
        calls = {call['name']: call for call in fixture.calls}
        self.assertEqual({name: call['status'] for name, call in calls.items() if call['status']}, EXPECTED_ERRORS)
        binary = str(fixture.producer_dir / 'bin/tuple-list')
        expected = {
            'discovery': [binary, '--framework-list', '--format', 'json'],
            'framework': [binary, '--framework', '--format', 'json', '--report', str(fixture.output / 'framework-report.jsonl')],
            'exact-selection': [binary, '--framework', '--format', 'json', '--exact', IDS[0]],
            'reject-unknown': [binary, '--framework', '--unknown'],
            'reject-empty': [binary, '--framework', '--exact', ''],
            'reject-absent': [binary, '--framework', '--exact', 'not-registered'],
            'report-write-failure': [binary, '--framework-list', '--report', str(fixture.output / 'missing-parent/report.json')],
        }
        for label, argv in expected.items():
            self.assertEqual(calls[label]['argv'], argv)

    def test_unexpected_success_or_wrong_error_status_is_not_accepted(self):
        for label, status in [('reject-unknown', 0), ('reject-empty', 1), ('reject-absent', 1), ('report-write-failure', 2)]:
            with self.subTest(label=label, status=status):
                fixture = MainFixture(self)
                fixture.returncodes[label] = status
                self.assert_failed(fixture, '--suite', 'framework', error=RuntimeError)
                self.assertEqual(fixture.events.count('authenticate'), 1)

    def test_default_missing_or_extra_observation_rejected(self):
        for count in (304, 306):
            with self.subTest(count=count):
                fixture = MainFixture(self)
                fixture.outputs['default'] = b'PASS tuple/list fixture\n' * count + b'Tuple/list focused checks passed.\n'
                self.assert_failed(fixture, '--suite', 'default', message='legacy observation inventory')

    def test_default_missing_or_nonterminal_completion_marker_rejected(self):
        for mutation in (lambda data: data.rsplit(b'Tuple/list', 1)[0], lambda data: data + b'late output\n'):
            fixture = MainFixture(self)
            fixture.outputs['default'] = mutation(fixture.outputs['default'])
            self.assert_failed(fixture, '--suite', 'default', message='legacy observation inventory')

    def test_harness_missing_marker_or_truncated_discovery_rejected_in_each_shard(self):
        for selection in ('default', 'framework'):
            for output in (HARNESS_MARKER, successful_outputs()['class-demand-IO-controls'].splitlines()[0] + b'\n'):
                with self.subTest(selection=selection, output=output):
                    fixture = MainFixture(self)
                    fixture.outputs['class-demand-IO-controls'] = output
                    self.assert_failed(fixture, '--suite', selection, message='harness completion marker')

    def test_harness_reordered_ids_rejected(self):
        fixture = MainFixture(self)
        inventory = dict(schema_version=1, event='inventory', cases=[{'id': 'probe/after'}, {'id': 'probe/fail'}])
        fixture.outputs['class-demand-IO-controls'] = json_lines([inventory]) + HARNESS_MARKER
        self.assert_failed(fixture, '--suite', 'default', message='actual discovery control output')

    def test_discovery_missing_reordered_or_changed_ids_rejected(self):
        mutations = [lambda rows: rows[0]['cases'].pop(), lambda rows: rows[0]['cases'].reverse(),
                     lambda rows: rows[0]['cases'][0].update(id='unexpected/case'),
                     lambda rows: rows[0].update(selected=104), lambda rows: rows[0].update(schema_version=2)]
        for mutation in mutations:
            fixture = MainFixture(self)
            fixture.replace_rows('discovery', mutation)
            self.assert_failed(fixture, '--suite', 'framework', message='discovery identity inventory')

    def test_full_missing_reordered_or_truncated_cases_rejected(self):
        mutations = [lambda rows: rows.pop(1), lambda rows: rows.insert(1, rows.pop(2)),
                     lambda rows: rows.pop(), lambda rows: rows.clear()]
        for mutation in mutations:
            fixture = MainFixture(self)
            fixture.replace_rows('framework', mutation)
            # Empty output may fail at the initial row access, but never succeeds.
            self.assert_failed(fixture, '--suite', 'framework', error=(ValueError, IndexError))

    def test_full_start_inventory_or_case_identity_mutations_rejected(self):
        mutations = [lambda rows: rows[0]['ids'].reverse(), lambda rows: rows[1].update(id=IDS[1]),
                     lambda rows: rows[1].update(status='failed'), lambda rows: rows[1].update(event='summary'),
                     lambda rows: rows[1].update(schema_version=2)]
        for mutation in mutations:
            fixture = MainFixture(self)
            fixture.replace_rows('framework', mutation)
            self.assert_failed(fixture, '--suite', 'framework')

    def test_full_summary_cannot_claim_partial_or_incomplete_coverage(self):
        for mutation in ({'complete': False}, {'scope': 'partial'}, {'executed': 104},
                         {'passed': 104}, {'failed': 1}, {'selected': 104}, {'total': 104}):
            with self.subTest(mutation=mutation):
                fixture = MainFixture(self)
                fixture.replace_rows('framework', lambda rows: rows[-1].update(mutation))
                self.assert_failed(fixture, '--suite', 'framework', message='terminal summary invalid')

    def test_report_and_stdout_must_agree(self):
        fixture = MainFixture(self)
        fixture.report_bytes = fixture.outputs['framework'][:-1]
        self.assert_failed(fixture, '--suite', 'framework', message='report/stdout disagreement')

    def test_partial_missing_reordered_or_truncated_rows_rejected(self):
        mutations = [lambda rows: rows.pop(1), lambda rows: rows.reverse(), lambda rows: rows.pop()]
        for mutation in mutations:
            fixture = MainFixture(self)
            fixture.replace_rows('exact-selection', mutation)
            self.assert_failed(fixture, '--suite', 'framework', message='exact selection identity/scope')

    def test_partial_identity_status_schema_and_scope_mutations_rejected(self):
        mutations = [lambda rows: rows[0].update(ids=[IDS[1]]), lambda rows: rows[1].update(id=IDS[1]),
                     lambda rows: rows[1].update(status='failed'), lambda rows: rows[1].update(schema_version=2),
                     lambda rows: rows[-1].update(scope='full'), lambda rows: rows[-1].update(complete=False),
                     lambda rows: rows[-1].update(executed=105), lambda rows: rows[-1].update(total=1)]
        for mutation in mutations:
            fixture = MainFixture(self)
            fixture.replace_rows('exact-selection', mutation)
            self.assert_failed(fixture, '--suite', 'framework', message='exact selection identity/scope')

    def test_missing_or_changed_producer_object_prevents_any_command(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                fixture = MainFixture(self)
                if missing:
                    fixture.object_file.unlink()
                else:
                    fixture.object_file.write_bytes(b'changed')
                self.assert_failed(fixture, error=FileNotFoundError if missing else ValueError)
                self.assertEqual(fixture.events, ['authenticate'])

    def test_final_object_receipt_or_artifact_mutation_invalidates_success(self):
        for target in ('object', 'receipt', 'artifact'):
            with self.subTest(target=target):
                fixture = MainFixture(self)
                path = {'object': fixture.object_file, 'receipt': fixture.build_receipt,
                        'artifact': fixture.output / 'framework-direct'}[target]
                fixture.on_final_auth = lambda: path.write_bytes(b'changed after execution')
                self.assert_failed(fixture, '--suite', 'default')
                self.assertEqual(len(fixture.auth_calls), 2)

    def test_receipt_retains_actual_source_and_producer_digest_evidence(self):
        fixture = MainFixture(self)
        receipt = fixture.execute('--suite', 'framework')
        self.assertEqual(receipt['producer_receipt_sha256'], hashlib.sha256(fixture.build_receipt.read_bytes()).hexdigest())
        self.assertEqual(receipt['object_inputs'], fixture.producer['object_inputs'])
        for relative in ('tools/shared/test_framework_direct.py', 'tools/shared/test_direct.py',
                         'tools/testing/tuple-list-active-contract.json', 'tests/Tests/TupleList.hs',
                         'tests/Tests/TupleListLegacy.hs', 'tests/MLF/Entry/TupleList.hs'):
            self.assertEqual(receipt['inputs'][relative], hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())
        self.assertEqual(len(receipt['artifacts']), 4)


if __name__ == '__main__':
    unittest.main()
