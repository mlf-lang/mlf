#!/usr/bin/env python3
"""Single documented entry for the GHC / MLF compiler shape benchmark.

Subcommands:
  list     show endpoints, matrices, families and the cells a matrix resolves to
  prepare  build the fixed dependencies once (private GHC package DB, runtime,
           builtin checked pair) and write setup.json
  run      execute one frozen cohort and report its build performance checks
  sweep    run families one at a time and tabulate their paired build times
  growth   fit standard-size point exponents from a published CSV or sweep directory
  installed  compare two public installations with GHC using fresh and warm targets
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

import command_runner
import fit_growth

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def registry():
    return json.loads((HERE / 'matrix.json').read_text())


def run(argv, *, recorder=False):
    argv = [str(value) for value in argv]
    print('+ ' + ' '.join(argv), flush=True)
    if recorder:
        status = command_runner.run_recorder(argv, ROOT)
    else:
        status = subprocess.run(argv, cwd=ROOT).returncode
    if status:
        raise SystemExit(status)


def measured_endpoint(name):
    endpoints = registry()['endpoints']
    if name not in endpoints:
        raise SystemExit('profile unavailable to the crate runner: ' + name
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
    if len(set(chosen_families)) != len(chosen_families) or len(set(chosen_sizes)) != len(chosen_sizes):
        raise SystemExit('families and sizes must be distinct')
    for size in chosen_sizes:
        if not 0 < size <= 8192:
            raise SystemExit('size out of the bounded range: ' + str(size))
    include_baseline = fit_growth.include_baseline(chosen_families, chosen_sizes, matrix['baseline'])
    chosen_families = [family for family in chosen_families if family != 'baseline']
    return matrix, chosen_families, chosen_sizes, include_baseline


def compile_count(cells, repeats):
    return cells * repeats * 2


def command_growth(args):
    import csv
    from matrix_growth import points
    try:
        rows = list(points(args.input, registry()['matrices']['default']))
    except (OSError, KeyError, ValueError) as err:
        raise SystemExit(f'cannot analyze {args.input}: {err}') from err
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)


def command_list(args):
    data = registry()
    matrix, families, sizes, include_baseline = resolve(args.matrix, args.family, args.size)
    cells = len(families) * len(sizes) + (1 if include_baseline else 0)
    print('suite:    ' + data['title'])
    print('matrix:   ' + args.matrix + ' (' + matrix['description'] + ')')
    print('endpoint: ' + args.endpoint + ' (' + data['endpoints'][args.endpoint]['status'] + ')')
    print('families: ' + ', '.join(families))
    print('sizes:    ' + ', '.join(str(size) for size in sizes))
    print('baseline: ' + ('yes' if include_baseline else 'no'))
    print('cells:    ' + str(cells) + ', timed compilations: '
          + str(compile_count(cells, matrix['repeats'])))
    print('')
    print('separate paired comparison (bench.py installed):')
    for name, endpoint in data['paired_endpoints'].items():
        print('  ' + name + ': ' + endpoint['summary'])
    print('')
    print('claim limits:')
    for limit in data['claim_limits']:
        print('  - ' + limit)


def prepare_setup(workdir, endpoint, producer, *, source=None, builtin_prefix=None,
                  build_builtin=False, ghc=None, clang=None):
    if not producer or bool(builtin_prefix) == build_builtin:
        raise SystemExit('prepare needs --producer and either --builtin-prefix or --build-builtin')
    setup = workdir.resolve() / 'setup'
    argv = [sys.executable, '-B', HERE / 'prepare.py', '--output', setup,
            '--endpoint', endpoint, '--producer', producer]
    if source:
        argv += ['--source', source]
    if builtin_prefix:
        argv += ['--builtin-prefix', builtin_prefix]
    if build_builtin:
        argv += ['--build-builtin']
    if ghc:
        argv += ['--ghc', ghc]
    if clang:
        argv += ['--clang', clang]
    measured_endpoint(endpoint)
    run(argv, recorder=True)
    return setup / 'setup.json'


def command_prepare(args):
    return prepare_setup(args.workdir, args.endpoint, args.producer, source=args.source,
                         builtin_prefix=args.builtin_prefix, build_builtin=args.build_builtin,
                         ghc=args.ghc, clang=args.clang)


def sweep_setup(args):
    root = args.workdir.resolve()
    setup = (args.setup or root / 'setup' / 'setup.json').resolve()
    selected_producer = getattr(args, 'producer', None)
    if args.setup or setup.is_file():
        if selected_producer and Path(json.loads(setup.read_text())['producer']).resolve() != selected_producer.resolve():
            raise SystemExit('existing setup uses another producer: ' + str(setup))
        return setup
    if setup.parent.exists():
        raise SystemExit(f'incomplete preparation at {setup.parent}; select a fresh --workdir or pass --setup')
    producer = selected_producer or root / 'producer'
    if not selected_producer and not producer.exists():
        # Keep cold bootstrap builds out of the public installed-compiler directory.
        sys.path.insert(0, str(ROOT / 'tools'))
        from developer.process import run_build
        command = [sys.executable, '-B', ROOT / 'tools/shared/build.py', '--bootstrap-only',
                   '--optimization', '2', '--build-dir', producer]
        status = run_build(command, ROOT)
        if status:
            raise SystemExit(status if status > 0 else 128 - status)
    return prepare_setup(root, args.endpoint, producer, build_builtin=True)


def comma_values(value):
    """Accept repeated filters locally and comma-separated dispatch inputs in CI."""
    if not value.strip():
        return []
    values = [part.strip() for part in value.split(',')]
    if not all(values):
        raise argparse.ArgumentTypeError('empty value in selection')
    return values


def add_filters(parser):
    parser.add_argument('--family', action='extend', type=comma_values,
                        help='repeat or comma-separate families')
    parser.add_argument('--size', action='extend', type=lambda value: list(map(int, comma_values(value))),
                        help='repeat or comma-separate sizes')


def command_run(args, setup=None, *, record_only=False):
    workdir = args.workdir.resolve()
    setup = Path(setup or args.setup or workdir / 'setup' / 'setup.json').resolve()
    if not setup.is_file():
        raise SystemExit('missing setup; run "prepare" first: ' + str(setup))
    cohort = args.cohort
    if not cohort or '/' in cohort or cohort in ('.', '..'):
        raise SystemExit('cohort needs a plain directory label')
    output = workdir / 'cohorts' / cohort
    matrix, families, sizes, include_baseline = resolve(args.matrix, args.family, args.size)
    repeats = matrix['repeats'] if args.repeats is None else args.repeats
    if repeats < fit_growth.MIN_PAIRED_REPEATS:
        raise SystemExit(f'run requires at least {fit_growth.MIN_PAIRED_REPEATS} pairs per size. '
                         'For a one-pair qualification, use --pilot in run.py.')
    argv = [sys.executable, '-B', HERE / 'run.py', '--setup', setup, '--output', output,
            '--endpoint', args.endpoint, '--cohort', cohort, '--repeats', repeats]
    if record_only:
        argv.append('--record-only')
    if getattr(args, 'interleave_pairs', False):
        argv.append('--interleave-pairs')
    if getattr(args, 'cohort_output_gib', None) is not None:
        argv += ['--cohort-output-gib', args.cohort_output_gib]
    if include_baseline:
        argv += ['--family', 'baseline']
    for family in families:
        argv += ['--family', family]
    for size in sizes:
        argv += ['--size', str(size)]
    run(argv, recorder=True)
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


def command_sweep(args):
    import sweep
    raise SystemExit(sweep.run(args))


def main():
    if sys.argv[1:2] == ['installed']:
        run([sys.executable, '-B', HERE / 'installed.py', *sys.argv[2:]])
        return
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    listing = sub.add_parser('list', help='show the resolved matrix without running anything')
    listing.add_argument('--matrix', default='default')
    listing.add_argument('--endpoint', default=registry()['default_endpoint'])
    add_filters(listing)
    listing.set_defaults(func=command_list)

    prepare = sub.add_parser('prepare', help='build fixed dependencies once')
    prepare.add_argument('--workdir', type=Path, required=True)
    prepare.add_argument('--producer', type=Path)
    prepare.add_argument('--source', type=Path)
    prepare.add_argument('--builtin-prefix', type=Path)
    prepare.add_argument('--build-builtin', action='store_true')
    prepare.add_argument('--ghc')
    prepare.add_argument('--clang')
    prepare.add_argument('--endpoint', default=registry()['default_endpoint'])
    prepare.set_defaults(func=command_prepare)

    runner = sub.add_parser('run', help='run one frozen cohort and report its build performance checks')
    runner.add_argument('--workdir', type=Path, required=True)
    runner.add_argument('--cohort', required=True)
    runner.add_argument('--matrix', default='default')
    runner.add_argument('--endpoint', default=registry()['default_endpoint'])
    add_filters(runner)
    runner.add_argument('--repeats', type=int)
    runner.add_argument('--interleave-pairs', action='store_true')
    runner.add_argument('--cohort-output-gib', type=int)
    runner.add_argument('--setup', type=Path)
    runner.set_defaults(func=command_run)

    sweep = sub.add_parser('sweep', help='measure each shape and size in sequence and write a comparison table')
    sweep.add_argument('--workdir', type=Path, default=ROOT / '.mlf-build/compiler-shapes',
                       help='fresh sweep output (default: .mlf-build/compiler-shapes)')
    inputs = sweep.add_mutually_exclusive_group()
    inputs.add_argument('--setup', type=Path, help='reuse an existing setup.json')
    inputs.add_argument('--producer', type=Path, help='prepare with an existing O2 bootstrap producer')
    sweep.add_argument('--endpoint', default=registry()['default_endpoint'], choices=sorted(registry()['endpoints']))
    add_filters(sweep)
    sweep.add_argument('--repeats', type=int)
    sweep.add_argument('--cohort-output-gib', type=int)
    sweep.add_argument('--prune-build-products', action='store_true')
    sweep.set_defaults(func=command_sweep)

    growth = sub.add_parser('growth', help='fit standard-matrix point exponents and print CSV')
    growth.add_argument('input', type=Path, help='full-precision published CSV or sweep directory')
    growth.set_defaults(func=command_growth)

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
    everything.add_argument('--endpoint', default=registry()['default_endpoint'])
    add_filters(everything)
    everything.add_argument('--repeats', type=int)
    everything.add_argument('--interleave-pairs', action='store_true')
    everything.add_argument('--cohort-output-gib', type=int)
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
        folder = command_run(args, setup, record_only=True)
        if not json.loads((folder / 'receipt.json').read_text())['all_cases_passed']:
            from analyze import save_recorded_growth
            print(save_recorded_growth(folder), flush=True)
        analyze = argparse.Namespace(workdir=args.workdir, cohort=[args.cohort],
                                     label=args.label, plot=args.plot)
        command_analyze(analyze)
        return
    args.func(args)


if __name__ == '__main__':
    main()
