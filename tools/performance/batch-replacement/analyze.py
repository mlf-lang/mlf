#!/usr/bin/env python3
"""Describe a completed fixed batch-replacement window; no confidence claims."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('prior_analysis', HERE.parent / 'process-spawn/analyze.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)


def geometric(values):
    return math.exp(statistics.mean(math.log(v) for v in values))


def timing_decision(cases):
    """Current structural-adoption rule; use unrounded whole-run point estimates."""
    by_case = {c['case']: c for c in cases}
    primary = [by_case[f + '-2048'] for f in ('dependency_chain', 'inferred_chain')]
    positive = all(c['B_over_A'] < 1.0 for c in primary)
    guards = [c for c in cases if not c['case'].endswith('-2048')]
    regressions = [c['case'] for c in guards if c['B_over_A'] > 1.05 and c['difference_seconds'] > .1]
    return {'acceptance_rule': 'structural-positive-gain-v1',
            'both_2048_gain_positive': positive,
            'guard_and_smaller_meaningful_regressions': regressions,
            'timing_rule_pass': positive and not regressions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan, rows = prior.read_window(args.window)
    prior.require(plan['kind'] == 'shapes' and plan['purpose'] in ('discovery', 'confirmation'), 'known shape window')
    analysis = plan['analysis']
    prior.require(prior.sha(__file__) == analysis['analyzer_sha256'], 'frozen analyzer identity')
    prior.require(prior.sha(HERE.parent / 'process-spawn/analyze.py') == analysis['reader_sha256'], 'frozen reader identity')
    expected_counts = {'dependency_chain-2048': 1, 'inferred_chain-2048': 1} if plan['purpose'] == 'discovery' else {f'{f}-{n}': (2 if n == 2048 else 1) for f in ('dependency_chain', 'inferred_chain') for n in (32, 128, 512, 2048)}
    expected_counts.update({'flat_functions-512': 1, 'higher_order_chain-128': 1})
    prior.require({case: sum(b['case'] == case for b in plan['blocks']) for case in set(b['case'] for b in plan['blocks'])} == expected_counts, 'fixed case and block counts')
    for path, digest in plan['inputs'].items():
        prior.require(prior.sha(path) == digest, 'pinned input changed: ' + path)
    cases = []
    for case in dict.fromkeys(block['case'] for block in plan['blocks']):
        blocks = []
        for i, block in enumerate(plan['blocks']):
            if block['case'] != case:
                continue
            selected = [r for r in rows if r['block'] == i]
            times = {side: [r['command']['wall_seconds'] for r in selected if r['side'] == side] for side in 'AB'}
            a, b = geometric(times['A']), geometric(times['B'])
            blocks.append({'index': i, 'order': block['order'], 'A_seconds': times['A'], 'B_seconds': times['B'],
                           'A_geometric_seconds': a, 'B_geometric_seconds': b,
                           'log_B_over_A': math.log(b / a), 'B_over_A': b / a})
        a = geometric([b['A_geometric_seconds'] for b in blocks])
        b = geometric([b['B_geometric_seconds'] for b in blocks])
        stage_medians = {side: {stage: statistics.median(next(t for t in r['stages']['stages'] if t['name'] == stage)['wall_seconds'] for r in rows if r['case'] == case and r['side'] == side) for stage in ('source-to-checked', 'checked-to-llvm', 'llvm-to-executable')} for side in 'AB'}
        cases.append({'case': case, 'blocks': blocks, 'stage_wall_medians_seconds': stage_medians, 'A_geometric_seconds': a, 'B_geometric_seconds': b,
                      'B_over_A': b / a, 'gain_fraction': 1 - b / a, 'difference_seconds': b - a})
    report = {'purpose': plan['purpose'], 'plan_sha256': prior.sha(args.window / 'plan.json'),
              'receipt_sha256': prior.sha(args.window / 'receipt.json'),
              'analyzer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'cases': cases, **timing_decision(cases),
              'interpretation': 'Descriptive fixed-block geometric ratios; one or two blocks per cell do not support a strong confidence interval. Mechanism, qualification, semantic gates and final decision require separate review.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as out:
        json.dump(report, out, indent=2, allow_nan=False)
        out.write('\n')
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
