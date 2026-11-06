#!/usr/bin/env python3
"""Single documented entry for the GHC / MLF compiler shape benchmark.

Subcommands:
  list     show endpoints, matrices, families and the cells a matrix resolves to
  prepare  build the fixed dependencies once (private GHC package DB, runtime,
           builtin checked pair) and write setup.json
  run      execute one frozen cohort (filters: --family, --size, --repeats)
  analyze  write summary.json, summary.csv, samples.csv and summary.md
  all      prepare if needed, then run, then analyze

Layout under --workdir:
  WORKDIR/setup/setup.json
  WORKDIR/cohorts/<cohort>/{plan.json,receipt.json,legs/,sources/,scripts/}
  WORKDIR/results/<label>/{summary.json,summary.csv,samples.csv,summary.md}

No measurement, ordering or correctness rule is reimplemented here: this file only
resolves the matrix and calls the unchanged prepare/run/analyze implementations.
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def registry():
    return json.loads((HERE / 'matrix.json').read_text())


def run(argv):
    print('+ ' + ' '.join(str(value) for value in argv), flush=True)
    result = subprocess.run([str(value) for value in argv], cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)


def measured_endpoint(name):
    endpoints = registry()['endpoints']
    if name not in endpoints:
        raise SystemExit('unknown or unmeasured endpoint profile: ' + name
                         + '; measured profiles are ' + ', '.join(sorted(endpoints)))
    return endpoints[name]


def resolve(matrix_name, families, sizes):
    data = registry()
    if matrix_name not in data['matrices']:
        raise SystemExit('unknown matrix: ' + matrix_name)
    matrix = data['matrices'][matrix_name]
    chosen_families = list(families) if families else list(matrix['families'])
    chosen_sizes = list(sizes) if sizes else list(matrix['sizes'])
    unknown = [name for name in chosen_families if name not in data['families']]
    if unknown:
        raise SystemExit('unknown families: ' + ', '.join(unknown))
    if 'baseline' in chosen_families:
        raise SystemExit('baseline is added by the matrix flag, not by --family')
    for size in chosen_sizes:
        if not 0 < size <= 1024:
            raise SystemExit('size out of the bounded range: ' + str(size))
    include_baseline = bool(matrix['baseline'])
    if families is None and not include_baseline:
        raise SystemExit('matrix without baseline must be filtered explicitly')
    return matrix, chosen_families, chosen_sizes, include_baseline


def compile_count(cells, repeats):
    return cells * repeats * 2


def command_list(args):
    data = registry()
    matrix, families, sizes, include_baseline = resolve(args.matrix, args.family, args.size)
    cells = len(families) * len(sizes) + (1 if include_baseline else 0)
    for family in families:
        if data['families'][family]['default'] is False and args.family is None:
            raise SystemExit('optional family reached the default matrix: ' + family)
    print('suite:    ' + data['title'])
    print('matrix:   ' + args.matrix + ' (' + matrix['description'] + ')')
    print('endpoint: ' + args.endpoint + ' (' + data['endpoints'][args.endpoint]['status'] + ')')
    print('families: ' + ', '.join(families))
    print('sizes:    ' + ', '.join(str(size) for size in sizes))
    print('baseline: ' + ('yes' if include_baseline else 'no'))
    print('cells:    ' + str(cells) + ', timed compilations: '
          + str(compile_count(cells, matrix['repeats'])))
    print('')
    print('declared but not measured here:')
    for name, endpoint in data['unmeasured_endpoints'].items():
        print('  ' + name + ': ' + endpoint['summary'])
    print('')
    print('claim limits:')
    for limit in data['claim_limits']:
        print('  - ' + limit)


def command_prepare(args):
    workdir = args.workdir.resolve()
    setup = workdir / 'setup'
    argv = [sys.executable, '-B', HERE / 'prepare.py', '--output', setup, '--endpoint', args.endpoint]
    if args.producer:
        argv += ['--producer', args.producer]
    if args.source:
        argv += ['--source', args.source]
    if args.builtin_prefix:
        argv += ['--builtin-prefix', args.builtin_prefix]
    if args.build_builtin:
        argv += ['--build-builtin']
    if not args.producer and not args.builtin_prefix:
        raise SystemExit('prepare needs --producer and either --builtin-prefix or --build-builtin')
    if args.ghc:
        argv += ['--ghc', args.ghc]
    if args.clang:
        argv += ['--clang', args.clang]
    measured_endpoint(args.endpoint)
    run(argv)
    return setup / 'setup.json'


def command_run(args, setup=None):
    workdir = args.workdir.resolve()
    setup = Path(setup or workdir / 'setup' / 'setup.json').resolve()
    if not setup.is_file():
        raise SystemExit('missing setup; run "prepare" first: ' + str(setup))
    cohort = args.cohort
    if not cohort or '/' in cohort or cohort in ('.', '..'):
        raise SystemExit('cohort needs a plain directory label')
    output = workdir / 'cohorts' / cohort
    matrix, families, sizes, include_baseline = resolve(args.matrix, args.family, args.size)
    repeats = args.repeats or matrix['repeats']
    if repeats < 3:
        raise SystemExit('fewer than three repetitions are qualification data, not samples; use --pilot in run.py')
    argv = [sys.executable, '-B', HERE / 'run.py', '--setup', setup, '--output', output,
            '--endpoint', args.endpoint, '--cohort', cohort, '--repeats', repeats]
    if include_baseline:
        argv += ['--family', 'baseline']
    for family in families:
        argv += ['--family', family]
    for size in sizes:
        argv += ['--size', str(size)]
    run(argv)
    return output


def command_analyze(args):
    workdir = args.workdir.resolve()
    coherents = [workdir / 'cohorts' / name for name in args.cohort]
    for path in coherents:
        if not (path / 'receipt.json').is_file():
            raise SystemExit('missing cohort: ' + str(path))
    label = args.label or '-'.join(args.cohort)
    output = workdir / 'results' / label
    argv = [sys.executable, '-B', HERE / 'analyze.py', *coherents, '--output', output]
    if args.plot:
        argv += ['--plot']
    run(argv)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    listing = sub.add_parser('list', help='show the resolved matrix without running anything')
    listing.add_argument('--matrix', default='default')
    listing.add_argument('--endpoint', default='crate-bootstrap-v1')
    listing.add_argument('--family', action='append')
    listing.add_argument('--size', action='append', type=int)
    listing.set_defaults(func=command_list)

    prepare = sub.add_parser('prepare', help='build fixed dependencies once')
    prepare.add_argument('--workdir', type=Path, required=True)
    prepare.add_argument('--producer', type=Path)
    prepare.add_argument('--source', type=Path)
    prepare.add_argument('--builtin-prefix', type=Path)
    prepare.add_argument('--build-builtin', action='store_true')
    prepare.add_argument('--ghc')
    prepare.add_argument('--clang')
    prepare.add_argument('--endpoint', default='crate-bootstrap-v1')
    prepare.set_defaults(func=command_prepare)

    runner = sub.add_parser('run', help='run one frozen cohort')
    runner.add_argument('--workdir', type=Path, required=True)
    runner.add_argument('--cohort', required=True)
    runner.add_argument('--matrix', default='default')
    runner.add_argument('--endpoint', default='crate-bootstrap-v1')
    runner.add_argument('--family', action='append')
    runner.add_argument('--size', action='append', type=int)
    runner.add_argument('--repeats', type=int)
    runner.add_argument('--setup', type=Path)
    runner.set_defaults(func=command_run)

    analyzer = sub.add_parser('analyze', help='write the analysis outputs')
    analyzer.add_argument('--workdir', type=Path, required=True)
    analyzer.add_argument('--cohort', action='append', required=True)
    analyzer.add_argument('--label')
    analyzer.add_argument('--plot', action='store_true')
    analyzer.set_defaults(func=command_analyze)

    everything = sub.add_parser('all', help='prepare if needed, run one cohort, analyze')
    everything.add_argument('--workdir', type=Path, required=True)
    everything.add_argument('--cohort', required=True)
    everything.add_argument('--matrix', default='default')
    everything.add_argument('--endpoint', default='crate-bootstrap-v1')
    everything.add_argument('--family', action='append')
    everything.add_argument('--size', action='append', type=int)
    everything.add_argument('--repeats', type=int)
    everything.add_argument('--producer', type=Path)
    everything.add_argument('--source', type=Path)
    everything.add_argument('--builtin-prefix', type=Path)
    everything.add_argument('--build-builtin', action='store_true')
    everything.add_argument('--ghc')
    everything.add_argument('--clang')
    everything.add_argument('--label')
    everything.add_argument('--plot', action='store_true')

    args = parser.parse_args()
    if args.command == 'all':
        setup = args.workdir.resolve() / 'setup' / 'setup.json'
        if not setup.is_file():
            setup = command_prepare(args)
        args.setup = setup
        command_run(args, setup)
        analyze = argparse.Namespace(workdir=args.workdir, cohort=[args.cohort],
                                     label=args.label, plot=args.plot)
        command_analyze(analyze)
        return
    args.func(args)


if __name__ == '__main__':
    main()
