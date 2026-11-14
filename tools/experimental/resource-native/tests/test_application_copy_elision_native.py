#!/usr/bin/env python3
"""Finite native before/after checks; no timing or source admission claim."""
import argparse
import json
from pathlib import Path
import shlex
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
from test_application_copy_elision import fixture
from test_branch_owner_reuse_native import check_report, require
from test_stage05_runtime_native import build_programs, run_process, COMMANDS
from resource_ir_v8.application_copy_elision import elide_application_input_copies
from resource_ir_v8.checker import check_resources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default='gcc')
    args = parser.parse_args()
    require(not sys.flags.optimize, 'checker assertions required')
    output = args.output.resolve()
    checkout = HERE.parents[3]
    require(output != checkout and checkout not in output.parents, 'external output required')
    output.mkdir(parents=True, exist_ok=False)
    summary = {'format': 'ir8-application-copy-native/1', 'status': 'running', 'cases': [],
               'source_admitted': False, 'timing_claim': False, 'optimization': 'O2'}
    try:
        texts = {}
        for pending in (False, True):
            for groups in (False, True):
                name = ('pending' if pending else 'literal') + ('_data' if groups else '_plain')
                original = check_resources(fixture(groups, pending))
                optimized = elide_application_input_copies(json.loads(original.canonical_json))
                require(optimized.eliminated_applications == 1, name + ': one static window')
                texts[name + '_before'] = original.canonical_json
                texts[name + '_after'] = optimized.canonical_json
                (output / (name + '.witness.json')).write_text(optimized.witness_json + '\n')
        build = build_programs(output, texts, shlex.split(args.cc), False, 'O2')
        for pending in (False, True):
            for groups in (False, True):
                name = ('pending' if pending else 'literal') + ('_data' if groups else '_plain')
                for repetitions in ((1,) if pending else (1, 3)):
                    reports = {}
                    for version in ('before', 'after'):
                        case = name + '_' + version
                        directory = output / (case + '_repeat' + str(repetitions))
                        command = run_process([build / case / 'smoke', str(repetitions)], directory)
                        require(command['returncode'] == 0, case + ': exit')
                        require((directory / 'stderr.raw').read_bytes() == b'', case + ': stderr')
                        document = json.loads((directory / 'stdout.raw').read_text())
                        require(document['evaluation']['metrics']['entries_completed'] == repetitions, 'entries')
                        # Reuse the existing full resource/42/zero-live gate;
                        # its single-entry predicate is adapted only in a copy.
                        gate = json.loads(json.dumps(document))
                        gate['evaluation']['metrics']['entries_completed'] = 1
                        check_report(gate)
                        reports[version] = document['evaluation']
                    before, after = reports['before'], reports['after']
                    for field in ('groups_allocated', 'groups_closed', 'nodes_allocated', 'nodes_freed',
                                  'applications_allocated', 'callback_calls', 'ordinary_calls',
                                  'force_calls', 'memo_writes', 'entries_completed'):
                        require(before['metrics'][field] == after['metrics'][field], name + ': changed ' + field)
                    for field in ('owner_handle_acquisitions', 'owner_handle_releases',
                                  'ir_retain_ops', 'ir_drop_ops'):
                        require(before['metrics'][field] - after['metrics'][field] == 2 * repetitions,
                                name + ': unexpected owner delta ' + field)
                    summary['cases'].append({'name': name, 'repetitions': repetitions,
                        'before_metrics': before['metrics'], 'after_metrics': after['metrics'],
                        'result': after['result'], 'zero_live_categories': 7})
        summary['status'] = 'passed'
    finally:
        summary['commands'] = COMMANDS
        (output / 'RESULT.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': summary['status'], 'pairs': len(summary['cases']),
                      'native_runs': len(summary['cases']) * 2}, sort_keys=True))


if __name__ == '__main__':
    main()
