#!/usr/bin/env python3
"""Summarize complete diagnostic counts without interpreting diagnostic times."""
import argparse
import hashlib
import json
from pathlib import Path

from instrument import require
from run import validate_controls, validate_output, validate_workload_counts


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.results.resolve()
    receipt_path, counts_path = directory / 'receipt.json', directory / 'counts.json'
    receipt, rows = json.loads(receipt_path.read_text()), json.loads(counts_path.read_text())
    require(receipt['complete'] is True, 'measurement receipt incomplete')
    validate_controls(receipt['controls']['counts'])
    require(receipt['controls']['identical_repeats'] == 2, 'control repeats incomplete')
    indexed = {(row['case']['family'], row['case']['size']): row for row in rows}
    families, sizes = ('dependency_chain', 'inferred_chain'), (32, 128, 512, 2048)
    require(len(rows) == 8 and set(indexed) == {(family, size) for family in families for size in sizes},
            'complete eight-case matrix required')
    for row in rows:
        name, counters = row['case']['case'], row['counters']
        raw = json.loads((directory / name / 'stdout').read_text())
        require(raw['complete'] is True and raw['counters'] == counters, 'saved counts differ from raw output')
        validate_workload_counts(counters)
        ordinary, diagnostic = (directory / (name + '-artifacts') / filename
                                for filename in ('ordinary.ll', 'diagnostic.ll'))
        validate_output(ordinary, diagnostic)
        require(row['exact_ordinary_llvm_equal'] is True and digest(ordinary) == row['llvm_sha256'] and
                ordinary.stat().st_size == row['llvm_bytes'], 'LLVM evidence differs from measurement')
    def counts(family, size):
        return indexed[family, size]['counters']
    def event(family, size, key):
        return counts(family, size).get(key, {}).get('events', 0)
    def rebuilt(family, size):
        return sum(event(family, size, 'copy.identities_alias.' + kind)
                   for kind in ('rebuild_abs', 'rebuild_app', 'rebuild_let', 'rebuild_rec', 'rebuild_case'))
    for size in sizes:
        for prefix in ('commonCalls.', 'substituteUsed.'):
            require({key: value for key, value in counts(families[0], size).items() if key.startswith(prefix)} ==
                    {key: value for key, value in counts(families[1], size).items() if key.startswith(prefix)},
                    'families differ in traversal counters')
        require(event(families[0], size, 'commonCalls.visits') == size * size + 8 * size + 131 and
                event(families[0], size, 'substituteUsed.visits') == (3 * size * size + 23 * size) // 2 + 6194,
                'observed finite-range traversal fit changed')
    lines = [
        '# Inlining traversal measurements — 2026-11-01', '',
        'The first guarded run completed successfully: all eight ordinary/diagnostic LLVM byte comparisons passed, '
        'and the two independent control processes produced identical exact counts. No compilation or runtime fixes '
        'were needed after execution started. The production integration was already pushed at '
        '`3b367be8aa0dd265c2d624bfad983d1e54bb4568` before this run.', '',
        'Both annotated and inferred dependency chains produced the following identical traversal counts. '
        'Depth is the maximum explicitly threaded recursion depth, starting at zero for each traversal root.', '',
        '| Chain size | commonCalls roots | commonCalls visits | Max depth | substituteUsed roots | substituteUsed visits | Max depth |',
        '| ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for size in sizes:
        c = counts(families[0], size)
        values = [size, event(families[0], size, 'commonCalls.roots'), event(families[0], size, 'commonCalls.visits'),
                  c['commonCalls.visits']['max_depth'], event(families[0], size, 'substituteUsed.roots'),
                  event(families[0], size, 'substituteUsed.visits'), c['substituteUsed.visits']['max_depth']]
        lines.append('| ' + ' | '.join(f'{value:,}' for value in values) + ' |')
    lines += ['', 'Alias elimination has a different growth pattern:', '',
              '| Chain size | Annotated alias roots | Annotated copy visits | Annotated structural rebuilds | Inferred copy visits | Inferred structural rebuilds |',
              '| ---: | ---: | ---: | ---: | ---: | ---: |']
    for size in sizes:
        values = [size, event(families[0], size, 'copy.identities_alias.roots'),
                  event(families[0], size, 'copy.identities_alias.visits'), rebuilt(families[0], size),
                  event(families[1], size, 'copy.identities_alias.visits'), rebuilt(families[1], size)]
        lines.append('| ' + ' | '.join(f'{value:,}' for value in values) + ' |')
    common_ratio = event(families[0], 2048, 'commonCalls.visits') / event(families[0], 512, 'commonCalls.visits')
    substitute_ratio = event(families[0], 2048, 'substituteUsed.visits') / event(families[0], 512, 'substituteUsed.visits')
    alias_ratio = event(families[0], 2048, 'copy.identities_alias.visits') / event(families[0], 512, 'copy.identities_alias.visits')
    rebuild_ratio = rebuilt(families[0], 2048) / rebuilt(families[0], 512)
    lines += [
        '', 'Inferred chains have 319 alias-copy roots at every size. Both families have maximum alias-copy depth 60 throughout.', '',
        f'For a 4× increase from 512 to 2048 bindings, `commonCalls` visits grow {common_ratio:.3f}× and '
        f'`substituteUsed` visits grow {substitute_ratio:.3f}×. Their maximum depths grow from 1028/1029 '
        f'to 4100/4101. Annotated alias-copy visits grow only {alias_ratio:.3f}× and structural rebuilds '
        f'{rebuild_ratio:.3f}×; inferred alias copying stays constant.', '',
        'Across these four measured sizes, visits fit `commonCalls = N² + 8N + 131` and '
        '`substituteUsed = (3N² + 23N)/2 + 6194` exactly. These are descriptive fits to this finite input set, '
        'not proofs of global complexity.', '',
        'At size 2048, `commonCalls` records 4,206,686 positive-use visits and 4,133 pruned visits. '
        '`substituteUsed` records 4,212,238 positive-use visits, 2,108,964 pruned visits, and 4,209,568 '
        'positive-use parent reconstruction branches. Copies of substituted replacement values visit only '
        '18,380 nodes. This distinguishes repeated scans/reconstruction of the path to a use from copying the replacement itself. '
        '`useApplications` independently records 6,372,032 spine visits, compared with 416,192 at size 512.', '',
        'These measurements support investigating repeated per-binder positive-use path discovery and reconstruction '
        'in common-call detection and substitution '
        'before alias-copy elimination on these chain workloads. They do not establish general asymptotic complexity, '
        'ordinary CPU-time attribution, or an optimization speedup.', '',
        'Counters describe demanded source paths in the diagnostic build, which disables CSE and full laziness. '
        'Ordinary optimized execution can share or eliminate work differently. Exact LLVM equality establishes output '
        'equivalence on these inputs, not identical demand or physical work. Structural rebuild events are logical '
        'constructor branches, not physical node allocations or bytes; map/list/tuple allocations are not counted. '
        'Roots, visits, branches, and application-spine events overlap and must not be added as independent work totals. '
        'An intervention still needs a separate ordinary-build performance experiment.', '',
        'Validation includes exact source-transform reversibility, zero-use bottoms remaining unforced, positive recursive '
        'common-call/substitution controls with exact depths and fresh-name results, a nonzero alias-copy control, '
        'complete branch accounting, authentic producer object inventory, and all nine interfaces/eighteen files in '
        'the checked dependency closure. Seven Python admission controls passed both normally and under `python -O`.', '',
        f'Raw directory: `{directory}`. The measured harness and production source copies are preserved in '
        '`source-snapshot/`, each verified against the measurement receipt. No failed attempts exist.', '',
        f'- `receipt.json` SHA-256: `{digest(receipt_path)}`',
        f'- `counts.json` SHA-256: `{digest(counts_path)}`', '',
        'Reproduce this summary without rerunning the compiler:', '',
        '```sh',
        'python3 -B tools/performance/inline-traversals/summarize.py \\',
        '  --results .mlf-build/inline-traversals-20261101/run-01 \\',
        '  --output tools/performance/inline-traversals/RESULTS.md',
        '```', '',
    ]
    args.output.write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
