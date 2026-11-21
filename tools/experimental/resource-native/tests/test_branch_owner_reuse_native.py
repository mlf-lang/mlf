#!/usr/bin/env python3
"""Maintained native regression for opt-in Int branch owner reuse.

Six synthetic typed fragments, two group placements, before/after, one entry.
This automates a narrow part of prior native research; it is not source
qualification, performance evidence or general GC-replacement evidence.
"""
import argparse
import copy
import json
from pathlib import Path
import shlex
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import test_branch_owner_reuse as reuse
from test_branch_owner_reuse_scopes import nested_fixture
from test_stage05_runtime_native import build_programs, run_process, COMMANDS
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def cases():
    selected = {name: reuse.CASES[name] for name in (
        'same-true', 'same-false', 'one-expression', 'two-pending', 'unselected-loop')}
    selected['nested'] = (nested_fixture(), 3)
    return selected


def check_report(document):
    require(document['schema'] == 'resource-ir-v8-terminal-run/1', 'terminal schema')
    r = document['evaluation']
    require(r['state'] == 0 and r['graph_executed'] == 1, 'graph incomplete')
    require(r['fault'] == 0 and r['guards_failed_mask'] == 0, 'native fault')
    # Independent fixture oracle: both shared arms are 42; pending 20+22 is
    # selected over 100+200; the recursive loop and nested else are not demanded.
    require(r['result'] == {'kind': 'i64', 'value': 42}, 'independent Int oracle')
    require(r['metrics']['entries_completed'] == 1, 'entry count')
    require(r['events_omitted'] == 0 and r['events_emitted'] == len(r['events']), 'events truncated')
    for acquired, released in (('owner_handle_acquisitions', 'owner_handle_releases'),
            ('loan_handle_acquisitions', 'loan_handle_releases'),
            ('groups_allocated', 'groups_closed'), ('nodes_allocated', 'nodes_freed'),
            ('rc_inc_sum', 'rc_dec_sum')):
        require(all(type(r['metrics'][key]) is int and r['metrics'][key] >= 0
                    for key in (acquired, released)), 'invalid counter: ' + acquired)
        require(r['metrics'][acquired] == r['metrics'][released], 'unbalanced ' + acquired)
    require(len(r['memory_categories']) == 7, 'memory categories')
    for category, counters in [('aggregate', r['memory']), *r['memory_categories'].items()]:
        require(counters['live_bytes'] == counters['live_blocks'] == 0, 'live memory: ' + category)
        require(counters['allocated_bytes'] == counters['freed_bytes'], 'byte balance: ' + category)
        require(counters['allocations'] == counters['frees'], 'block balance: ' + category)
    d = document['destruction']
    require(d['status'] == 2 and d['retired_blocks'] == d['retired_bytes'] == 0
            and d['totals_overflow'] is False, 'retirement')
    return r


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default='gcc')
    args = parser.parse_args()
    require(not sys.flags.optimize, 'checker assertions require unoptimized Python')
    output = args.output.resolve()
    checkout = HERE.parents[3]
    require(output != checkout and checkout not in output.parents, 'output must be outside checkout')
    output.mkdir(parents=True, exist_ok=False)
    summary = {'format': 'ir8-branch-owner-reuse-native/1', 'status': 'running',
               'optimization': 'O2', 'sanitize': False, 'cases': [],
               'source_admitted': False, 'timing_claim': False,
               'not_covered': ['multiple entries', 'sanitizers', 'source compiler qualification',
                               'general GC replacement', 'performance']}
    try:
        raw_texts = {}
        for name, (raw, expected_rows) in cases().items():
            fragment = reuse.derive_shared_fragment(raw)
            for groups in (False, True):
                key = name + ('_data' if groups else '_plain')
                for version, enabled in (('before', False), ('after', True)):
                    plan = reuse.planner.plan_fragment(raw, fragment=fragment,
                        data_groups=groups, reuse_int_branches=enabled)
                    checked = check_resources(plan['program'])
                    metadata = check_metadata(plan['program'])
                    require(checked.sha256 == plan['binding']['candidate_sha256'] == metadata.ir_sha256,
                            key + ': resource/metadata identity')
                    if enabled:
                        require(len(reuse.audit_rows(fragment['raw_normalized'], plan)) == expected_rows,
                                key + ': reuse correspondence')
                    case_id = key + '_' + version
                    raw_texts[case_id] = checked.canonical_json
                    (output / (case_id + '.plan.json')).write_text(json.dumps(plan, sort_keys=True) + '\n')
        build = build_programs(output, raw_texts, shlex.split(args.cc), False, 'O2')
        for name in cases():
            for groups in (False, True):
                key = name + ('_data' if groups else '_plain')
                observed = {}
                for version in ('before', 'after'):
                    case_id = key + '_' + version
                    directory = output / case_id
                    command = run_process([build / case_id / 'smoke', '1'], directory)
                    require(command['returncode'] == 0, case_id + ': child exit')
                    require((directory / 'stderr.raw').read_bytes() == b'', case_id + ': stderr')
                    document = json.loads((directory / 'stdout.raw').read_text())
                    observed[version] = check_report(document)
                    if not summary['cases'] and version == 'before':
                        # A pair of invalid counters must not pass as balanced.
                        for invalid in (None, -1, True):
                            corrupted = copy.deepcopy(document)
                            for counter_key in ('rc_inc_sum', 'rc_dec_sum'):
                                corrupted['evaluation']['metrics'][counter_key] = invalid
                            try:
                                check_report(corrupted)
                            except AssertionError:
                                pass
                            else:
                                raise AssertionError('invalid equal RC counters accepted')
                        summary['counter_negative_checks'] = 3
                require(observed['before']['result'] == observed['after']['result'], key + ': result mismatch')
                summary['cases'].append({'name': name, 'data_groups': groups,
                    'result': observed['after']['result'], 'zero_live_categories': 7,
                    'before_metrics': observed['before']['metrics'],
                    'after_metrics': observed['after']['metrics']})
        summary['status'] = 'passed'
    finally:
        summary['commands'] = COMMANDS
        (output / 'RESULT.json').write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': summary['status'], 'pairs': len(summary['cases']),
                      'native_runs': len(summary['cases']) * 2}, sort_keys=True))


if __name__ == '__main__':
    main()
