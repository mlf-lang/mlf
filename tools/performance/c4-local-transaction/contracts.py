"""Pure fail-closed inventory/output checks; never runs a compiler."""
import ast
import hashlib
import json
from pathlib import Path
import re


def require(value, message):
    if not value:
        raise ValueError(message)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def exact_fields(actual, expected):
    require(set(actual) == set(expected), 'exact summary field inventory')
    require(all(type(actual[k]) is type(v) and actual[k] == v
                for k, v in expected.items()), 'exact typed summary values')


def builtin_payload(data):
    pattern = rb'builtin-source-v1:[0-9a-f]{64}'
    require(len(re.findall(pattern, data)) == 1, 'one generated source identity literal')
    return re.sub(pattern, b'builtin-source-v1:<source-identity>', data)


def verify_oracles(directory, manifest, base):
    for row in manifest['full_algorithm_modules']:
        frozen = (directory / 'controls' / (row['module'] + '.hs')).read_bytes()
        require(sha_bytes(frozen) == row['frozen_sha256'], 'fixed complete old oracle')
        inverse = frozen
        for old, new in reversed(row['substitutions']):
            require(inverse.count(new.encode()) == 1, 'one declared oracle substitution')
            inverse = inverse.replace(new.encode(), old.encode())
        require(sha_bytes(inverse) == row['original_sha256'], 'exact P3 inverse source identity')
        if base is not None:
            require((base / row['source_path']).read_bytes() == inverse,
                    'actual before algorithms equal complete independent oracle')


def public_result(stdout, stderr):
    require(stderr == b'', 'public controls stderr empty')
    lines = stdout.decode().splitlines()
    summary = json.loads(lines[-1])
    exact_fields(summary, dict(complete=True, public_trace_cases=28,
        validation_cases=12000, renamed_cases=400, parsed_expression_cases=8,
        authored_permission_cases=4, a1_private_controls_applicable=False,
        candidate_output_used_for_expectations=False))
    row = re.fullmatch(r'PASS finite validation=12000 unification=(\d+) accepted=(\d+) unchanged-binders=(\d+) changed-binders=(\d+)', lines[0])
    require(row is not None, 'finite public outcome inventory')
    total, accepted, same, changed = map(int, row.groups())
    require(total == 5616 and 100 < accepted < total-100 and same > 100 and changed > 0,
            'complete nonvacuous finite old corpus')
    row = re.fullmatch(r'PASS frozen binder-premise outcomes \[same-success,same-rejection,changed-success,changed-rejection\]=(\[.*\])', lines[1])
    require(row is not None, 'four actual frozen premise buckets')
    buckets = json.loads(row[1])
    require(len(buckets) == 4 and all(type(n) is int and n > 0 for n in buckets),
            'success and downstream rejection on both premise paths')
    require(lines[2].startswith('PASS frozen dense-rebind permission rejection inventory='),
            'complete frozen downstream error inventory')
    require('PASS four authored legal dense permission cases: reuse/fallback x success/exact protected rejection' in lines,
            'independent authored permission controls')
    return dict(summary=summary, unification_cases=total, accepted=accepted,
                unchanged_binders=same, changed_binders=changed,
                frozen_premise_buckets=buckets, frozen_errors=lines[2])


TRANSACTION = dict(complete=True, authored_fixtures=18, renamed_fixtures=10,
    fixture_successes=19, fixture_rejections=9, admitted_fixtures=23,
    nonadmitted_fixtures=5, exact_compact_projections=23, literal_full_graphs=2,
    literal_compact_graphs=1, unchanged_fresh_survivor_assertions=3,
    original_traces=28, fixture_and_trace_solve_drivers=56,
    fixture_and_trace_flush_drivers=56, invalid_driver_graphs=5,
    source_target_error_boundaries=4, mixed_project_sequences=1,
    fallback_equation_branches=5, direct_restore_outcomes=4,
    isolated_restore_payload_probe=1, public_partial_probes=3,
    prepared_unused_payload_probes=3, force_edge_probes=5,
    prefix_payload_barriers=2, seen_prefix_probes=2,
    prepared_original_payload_demand_probes=2, oracle_boundary_checks=9,
    candidate_chooses_expected=False, old_public_physical_oracle_weakened=False,
    arbitrary_forged_prepared_equivalence_claimed=False)


def transaction_result(stdout, stderr):
    require(stderr == b'', 'transaction controls stderr empty')
    lines = stdout.decode().splitlines()
    require(sum(s.startswith('PASS ') for s in lines) == 9, 'nine transaction groups')
    summary = json.loads(lines[-1])
    exact_fields(summary, TRANSACTION)
    return summary


def heteroinput_result(stdout, stderr, manifest):
    require(stderr == b'', 'layout controls stderr empty')
    lines = stdout.decode().splitlines()
    cursor, rows, labels = 0, [], []
    for fixture in manifest['authored_matrix_fixtures']:
        for layout in manifest['matrix']['permutations']:
            for coordinate, _, _ in manifest['matrix']['coordinates']:
                serial = len(rows)+1
                label = f'heteroinput/{serial}/{layout}/{coordinate}/{fixture["label"]}'
                require(lines[cursor] == 'CASE-BEGIN '+label, 'fixed ordered case start')
                require(lines[cursor+1].startswith('FROZEN-SPEC '), 'independent spec before case')
                spec = ast.literal_eval(lines[cursor+1][len('FROZEN-SPEC '):])
                require(type(spec) is tuple and len(spec) == 11, 'complete Frozen spec tuple')
                require(spec[:4] == (serial, fixture['label'], layout, coordinate), 'spec identity')
                require(all(type(x) is int for x in spec[4:9]), 'integer node/count/position spec')
                require(spec[4] > 1 and spec[6] > 0 and 0 <= spec[7] < spec[6] and spec[8] >= 0,
                        'valid Frozen expansion range')
                require(type(spec[9]) is bool and spec[9] == fixture['admitted'] and
                        type(spec[10]) is bool and spec[10] == fixture['success'], 'authored outcome flags')
                cursor += 2
                if not fixture['success']:
                    require(lines[cursor].startswith('FROZEN ERROR '+label+': '),
                            'complete per-variant original first error retained')
                    cursor += 1
                require(lines[cursor] == 'CASE-PASS '+label, 'matching case terminal success')
                cursor += 1
                rows.append(spec)
                labels.append(label)
    require(len(rows) == len(set(labels)) == 216, 'all fixed distinct labels')
    require(lines[cursor:] and len(lines[cursor:]) == 2 and lines[cursor] ==
        'PASS fixed 216 nonmonotone identity variants with complete Frozen P3 and unchanged transaction oracle',
        'exact matrix terminal boundary, no extra/missing events')
    summary = json.loads(lines[-1])
    def count(predicate):
        return sum(predicate(r) for r in rows)
    bins = dict(root_first=count(lambda r: r[7] == 0),
        root_middle=count(lambda r: 0 < r[7] < r[6]-1),
        root_last=count(lambda r: r[6] > 1 and r[7] == r[6]-1),
        admitted_root_first=count(lambda r: r[9] and r[7] == 0),
        admitted_root_middle=count(lambda r: r[9] and 0 < r[7] < r[6]-1),
        admitted_root_last=count(lambda r: r[9] and r[6] > 1 and r[7] == r[6]-1))
    require(all(n > 0 for n in bins.values()), 'nonvacuous all/admitted root position bins')
    exact_fields(summary, dict(complete=True, cases=216, admitted=156, successes=156,
        rejections=60, candidate_selected_inputs=False, ordinary_timing_samples_added=0, **bins))
    require(count(lambda r: r[9]) == 156 and count(lambda r: r[10]) == 156,
            'recomputed fixed outcomes')
    return dict(summary=summary, labels=labels, frozen_specs=rows)
