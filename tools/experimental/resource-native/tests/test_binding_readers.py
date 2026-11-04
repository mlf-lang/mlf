#!/usr/bin/env python3
"""Explicit low-level reader differential tests, not runtime/packet admission.

Run with a fresh --output directory for portable current-only O0/O2 checks.
Optionally supply --baseline-root pointing to the unchanged Stage11, Stage14,
Stage15 or Stage17/18 repository
for exact differential diagnostics/data/work checks. Both modes use the same
bounded storage driver and real binding/packet sources. No callback, runtime,
source compiler or evaluator is mocked or invoked. This is a correctness/work-
accounting test, not a benchmark; elapsed times are ordinary diagnostics.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE))
from source_build_v8 import MIB, executable, require, run, save

BASELINE_BINDING_SHA = '4bbbf9eb9f9638dccd12e46d51fce0b0ae16b05f7ce6d8e2cd8e460f66e27f4f'
STAGE14_BINDING_SHA = 'd06bcb313748642e69b3bf511d6bda95a7d3673c12f65f80fc7c02aca16132ba'
STAGE15_BINDING_SHA = '519f8a90b29d8e3d915193f674f3aef08a8bb4cd6d0a5ca9db6efad5ed4e3f50'
STAGE17_BINDING_SHA = '48586d46d990f6e9a4e167e69f2ae6a4b906376b9f3ea677f9ea54455386f491'
BASELINES = {BASELINE_BINDING_SHA: 'stage11', STAGE14_BINDING_SHA: 'stage14',
             STAGE15_BINDING_SHA: 'stage15', STAGE17_BINDING_SHA: 'stage17'}
AUTH_SUCCESS_CASES = ('freshness-prime', 'freshness-restored', 'freshness-span-restored', 'short-one', 'short-two',
                      'after-target-id', 'budget-auth-first-middle')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows(path):
    lines = path.read_text().splitlines()
    require(0 < len(lines) < 10000, 'finite reader result count')
    rows = [json.loads(line) for line in lines]
    summary = rows.pop()
    require(summary.get('summary') is True and summary['failures'] == 0,
            'reader output/sentinel/budget checks failed')
    require(summary['table_domains'] == 20 and summary['descriptor_domains'] == 6,
            'all reader domains must be tested')
    keys = [(r['case'], r['kind'], r['domain'], r['row'], r['op']) for r in rows]
    require(len(set(keys)) == len(keys), 'duplicate reader case')
    require(all(r['output_ok'] == 1 for r in rows), 'reader output changed unexpectedly')
    require(len([r for r in rows if r['op'] == 4]) == 25,
            'all direct external-wrapper controls must run')
    return rows, summary


def removed_directory_calls(row):
    # Public object reads still call directory once, with identical accounting.
    if row['op'] == 3:
        return 0
    name = row['case']
    if name in ('valid', 'budget-exact-and-all-below') + AUTH_SUCCESS_CASES:
        return row['row'] + 1 if row['op'] == 2 else 1
    if name in ('foreign-ref', 'interior-ref', 'one-past-ref'):
        return 5
    if name in ('element-mismatch', 'wanted-size', 'wanted-zero', 'preceding-id-first'):
        return 1
    if name == 'preceding-id-middle':
        return 3
    if name == 'target-id':
        return 5
    if name in ('short-one-miss', 'short-two-miss'):
        return 1 if name == 'short-one-miss' else 2
    # All other malformed controls fail before the former duplicate read.
    return 0


def reused_auth_directory_calls(row):
    # Count directory-reached visits, including an ID failure, not just rows
    # whose IDs passed. The first visit always performs full directory checks.
    if row['op'] != 2:
        return 0
    name = row['case']
    if name in ('valid', 'budget-exact-and-all-below') + AUTH_SUCCESS_CASES:
        return row['row']
    if name in ('foreign-ref', 'interior-ref', 'one-past-ref', 'target-id'):
        return 4
    if name == 'preceding-id-middle':
        return 2
    if name == 'short-two-miss':
        return 1
    return 0


def compare(old, new, census, baseline):
    require(len(old) == len(new), 'differential case count differs')
    saved = 0
    for a, b in zip(old, new):
        # The wrapper has explicit invalid-counter/NULL-state controls; these
        # are not ordinary reads and do not use the reader total==used+17 rule.
        if a['op'] == 4:
            require(a == b, 'external reserve wrapper changed: ' + str((a, b)))
            continue
        if baseline == 'stage17':
            require(a == b, 'inline reserve changed a reader field: ' + str((a, b)))
        require({k: v for k, v in a.items() if k not in ('used', 'total')} ==
                {k: v for k, v in b.items() if k not in ('used', 'total')},
                'reader status/coordinates/bytes/sentinel differ: ' + str(a))
        later_rows = reused_auth_directory_calls(a)
        delta = 0
        if later_rows and baseline != 'stage17':
            require(a['kind'] in (1, 2), 'unknown authentication domain kind')
            key = 'auth_table_reuse_work' if a['kind'] == 1 else 'auth_descriptor_reuse_work'
            delta = later_rows * census[key]
        if baseline in ('stage11', 'stage14'):
            delta += later_rows * census['directory_work']
        if baseline == 'stage11':
            delta += removed_directory_calls(a) * census['directory_work']
        require(a['used'] - b['used'] == delta and a['total'] - b['total'] == delta,
                'work changed beyond removed directory/span/layout checks: ' + str((a, b, delta)))
        require(a['total'] - a['used'] == 17 and b['total'] - b['used'] == 17,
                'cumulative work counter drift')
        saved += delta
    return saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root', type=Path,
                        help='optional unchanged Stage11, Stage14, Stage15 or Stage17/18 repository for differential checks')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    args = parser.parse_args(argv)
    sources = [('optimized', BASE)]
    baseline_sha = baseline = None
    if args.baseline_root is not None:
        old = args.baseline_root.resolve() / 'tools/experimental/resource-native'
        baseline_sha = digest(old / 'runtime_v8/rir8_binding.c')
        require(baseline_sha in BASELINES, 'expected exact Stage11, Stage14, Stage15 or Stage17/18 binding source')
        baseline = BASELINES[baseline_sha]
        # Differential mode cannot silently compare different contracts.
        for relative in ('runtime_v8/rir8_binding.h', 'runtime_v8/rir8_binding_internal.h',
                         'packet_v8/ir8_packet.h', 'packet_v8/ir8_packet.c'):
            require((old / relative).read_bytes() == (BASE / relative).read_bytes(),
                    'differential shared input differs: ' + relative)
        sources.insert(0, ('baseline', old))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    cc = executable(args.cc)
    env = dict(os.environ, LANG='C', LC_ALL='C', TZ='UTC')
    results = {}
    for optimization in ('-O0', '-O2'):
        for label, source in sources:
            directory = output / (label + optimization)
            directory.mkdir()
            binary = directory / 'reader-tests'
            command = [cc, '-std=c11', optimization, '-g', '-Wall', '-Wextra', '-Werror',
                       '-pedantic', '-fno-lto', '-I', str(source / 'runtime_v8'),
                       str(HERE / 'binding_reader_driver.c'),
                       str(source / 'runtime_v8/rir8_binding.c'),
                       str(source / 'packet_v8/ir8_packet.c'), '-o', str(binary)]
            run(command, directory, 'compile', cwd=directory, env=env,
                wall=60, cpu=30, memory=1024*MIB)
            run([str(binary)], directory, 'run', cwd=directory, env=env,
                wall=30, cpu=20, memory=512*MIB)
            require((directory / 'run.stderr').read_bytes() == b'', 'unexpected reader stderr')
            results[(label, optimization)] = load_rows(directory / 'run.stdout')
        b, sb = results[('optimized', optimization)]
        if args.baseline_root is not None:
            a, sa = results[('baseline', optimization)]
            require(sa == sb, 'independent C census/expectations differ')
            saved = compare(a, b, sa, baseline)
            print(optimization, len(a), 'reader comparisons PASS;', saved, 'redundant charged units removed', flush=True)
        else:
            print(optimization, len(b), 'current reader expectation/sentinel/budget checks PASS', flush=True)
    for label, _ in sources:
        require(results[(label, '-O0')] == results[(label, '-O2')],
                'optimizer changed reader behavior or accounting: ' + label)
    summary = {'scope': 'reader-only correctness; not packet/runtime admission or timing',
               'mode': 'differential' if args.baseline_root is not None else 'current-only',
               'status': 'pass', 'cases_per_build': len(results[('optimized', '-O0')][0]),
               'builds': 2*len(sources), 'native_runs': 2*len(sources),
               'baseline': baseline, 'baseline_binding_sha256': baseline_sha,
               'external_wrapper_cases': 25,
               'optimized_binding_sha256': digest(BASE / 'runtime_v8/rir8_binding.c'),
               'driver_sha256': digest(HERE / 'binding_reader_driver.c'),
               'all_work_budgets_below_success': 'all operations final row; auth first/middle/final; all20table/6descriptor',
               'notes': ['No authentication scan shortcut.', 'No output changes on failure.',
                         'Stage17/18 differential mode requires every field, including all work, to remain exact.',
                         'External-wrapper boundary controls keep separate explicit counter expectations.',
                         'First row fully validates; later auth rows reuse only same-call directory/span/element facts.',
                         'Independent calls, span-object replacement, short spans, and post-match ID corruption are checked.',
                         'Exact baseline diagnostics/work deltas require optional differential mode.']}
    save(output / 'results.json', summary)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
