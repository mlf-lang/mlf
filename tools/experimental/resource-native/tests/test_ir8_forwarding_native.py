#!/usr/bin/env python3
"""Explicit native before/after controls for adjacent owned forwarding.

Uses the existing bounded native smoke builder and real IR8 C runtime. Six
finite programs, each before/after and one/three entries. No source compiler,
default pipeline activation, timing claim or general GC-replacement claim.
"""
import argparse
import json
from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_stage05_runtime_native import build_programs, run_process, COMMANDS
from test_ir8_forwarding import fixture, pair, scalar_pair, inject_copy
from resource_ir_v8.checker import check_resources
from resource_ir_v8.forwarding import forward_owned

SAME_METRICS = ('groups_allocated', 'groups_closed', 'nodes_allocated', 'nodes_freed',
    'peak_groups', 'peak_nodes', 'force_calls', 'max_force_depth', 'callback_calls',
    'ordinary_calls', 'applications_allocated', 'raw_deferred_returns', 'memo_writes',
    'internal_memo_slots', 'cross_group_memo_slots', 'memo_fast_paths',
    'groups_closed_during_force', 'borrowed_slot_publications', 'ir_borrow_ops',
    'ir_end_borrow_ops', 'ir_application_borrow_ops', 'max_activation_depth', 'entries_completed')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def inserted(name, opcode):
    p = fixture(name)
    d = json.loads(check_resources(p).derived_json)
    row = next(r for r in d['instructions'] if r['op'] == opcode and r['path']['root'] == 'entry')
    return inject_copy(p, row, d)


def cases():
    hole = fixture('concrete_fill_force_hole')
    index = next(i for i, op in enumerate(hole['entry']) if op['op'] == 'fill') + 1
    hole['entry'][index:index] = pair('h', 'saved_hole')
    next(op for op in hole['entry'] if op['op'] == 'force')['value'] = 'saved_hole'
    return {
        'scalar': scalar_pair(),
        'identity_parameter': fixture('closed_identity_retained_parameter'),
        'pending_thunk': inserted('concrete_standalone_thunk', 'thunk'),
        'closure': inserted('explicit_closed_identity', 'closure'),
        'sum_factory': inserted('closed_data_sum_factory', 'construct_sum'),
        'filled_hole': hole,
    }


def report_ok(document, repetitions):
    require(document['schema'] == 'resource-ir-v8-terminal-run/1', 'unexpected terminal schema')
    result = document['evaluation']
    require(result['state'] == 0 and result['graph_executed'] == 1, 'graph did not complete')
    require(result['fault'] == 0 and result['guards_failed_mask'] == 0, 'native fault')
    require(result['result'] == {'kind': 'i64', 'value': 42}, 'wrong independent scalar oracle')
    require(result['metrics']['entries_completed'] == repetitions, 'entry count differs')
    require(result['events_omitted'] == 0, 'event stream was truncated')
    require(result['events_emitted'] == len(result['events']), 'event inventory differs')
    metrics = result['metrics']
    for acquired, released in (('owner_handle_acquisitions', 'owner_handle_releases'),
            ('loan_handle_acquisitions', 'loan_handle_releases'),
            ('groups_allocated', 'groups_closed'), ('nodes_allocated', 'nodes_freed'),
            ('rc_inc_sum', 'rc_dec_sum')):
        require(metrics[acquired] == metrics[released], 'unbalanced ' + acquired)
    require(result['memory']['live_bytes'] == result['memory']['live_blocks'] == 0, 'live aggregate memory')
    require(len(result['memory_categories']) == 7, 'expected seven memory categories')
    for name, counters in result['memory_categories'].items():
        require(counters['live_bytes'] == counters['live_blocks'] == 0, 'live category: ' + name)
        require(counters['allocated_bytes'] == counters['freed_bytes'], 'unbalanced category: ' + name)
        require(counters['allocations'] == counters['frees'], 'unbalanced blocks: ' + name)
    retired = document['destruction']
    require(retired['status'] == 2 and retired['retired_blocks'] == retired['retired_bytes'] == 0
            and retired['totals_overflow'] is False, 'unexpected retirement')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--optimization', choices=('O0', 'O2'), default='O0')
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    checkout = Path(__file__).resolve().parents[4]
    require(output != checkout and checkout not in output.parents,
            'output must be outside the checkout')
    output.mkdir(parents=True, exist_ok=False)
    summary = {'format': 'ir8-owned-forwarding-native/1', 'status': 'running',
        'optimization': args.optimization, 'sanitized': args.sanitize, 'cases': [],
        'source_admitted': False, 'default_pipeline_changed': False, 'timing_claim': False}
    try:
        raw_texts = {}
        for name, p in cases().items():
            original = check_resources(p)
            optimized = forward_owned(p)
            require(optimized.eliminated_pairs == 1, name + ': expected one static pair')
            raw_texts[name + '_before'] = original.canonical_json
            raw_texts[name + '_after'] = optimized.canonical_json
            (output / (name + '.witness.json')).write_text(optimized.witness_json + '\n')
        build = build_programs(output, raw_texts, shlex.split(args.cc), args.sanitize, args.optimization)
        for name in cases():
            for repetitions in (1, 3):
                reports = {}
                for version in ('before', 'after'):
                    case_id = name + '_' + version
                    directory = output / (case_id + '_repeat' + str(repetitions))
                    command = run_process([build / case_id / 'smoke', str(repetitions)], directory,
                                          sanitize=args.sanitize)
                    require(command['returncode'] == 0, case_id + ': guest did not exit zero')
                    require((directory / 'stderr.raw').read_bytes() == b'', case_id + ': unexpected stderr')
                    document = json.loads((directory / 'stdout.raw').read_text())
                    report_ok(document, repetitions)
                    reports[version] = document['evaluation']
                before, after = reports['before'], reports['after']
                for field in SAME_METRICS:
                    require(before['metrics'][field] == after['metrics'][field], name + ': changed ' + field)
                for field in ('ir_retain_ops', 'ir_drop_ops', 'rc_inc_owner', 'rc_dec_owner',
                              'owner_handle_acquisitions', 'owner_handle_releases'):
                    require(before['metrics'][field] - after['metrics'][field] == repetitions,
                            name + ': unexpected dynamic owner delta ' + field)
                require(before['memory']['allocated_bytes'] > after['memory']['allocated_bytes'],
                        name + ': no requested allocation reduction')
                summary['cases'].append({'name': name, 'repetitions': repetitions,
                    'result': after['result'], 'removed_dynamic_pairs': repetitions,
                    'before_requested_bytes': before['memory']['allocated_bytes'],
                    'after_requested_bytes': after['memory']['allocated_bytes'],
                    'before_peak_bytes': before['memory']['peak_bytes'],
                    'after_peak_bytes': after['memory']['peak_bytes'],
                    'seven_zero_live_categories': True})
        summary['status'] = 'passed'
    finally:
        summary['commands'] = COMMANDS
        (output / 'RESULT.json').write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'commands'}, sort_keys=True))


if __name__ == '__main__':
    main()
