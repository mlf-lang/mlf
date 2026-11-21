"""Serial family-by-family measurements with a table of complete and failed cells."""
import csv
import io
import sys
from pathlib import Path

import analyze
import bench
import command_runner


def failure_detail(folder, receipt):
    """Prefer an observed resource guard or compiler diagnostic over a wrapper error."""
    failures = receipt.get('failures', [])
    if not failures:
        return '', receipt.get('stop_reason', 'incomplete recording')
    failure = failures[0]
    lane = failure['lane']
    leg = folder / 'legs' / f"{failure['position']:03d}-{failure['case']}-{lane}"
    # Each sweep cohort has exactly one cell, so its positions are leg indices.
    for command_path in sorted(leg.glob('*/command.json')):
        command = analyze.load(command_path)
        if command.get('reason'):
            return lane, command['reason']
    stages = leg / 'build' / 'stages.json'
    if stages.exists():
        for stage in analyze.load(stages)['stages']:
            if stage['exit_code']:
                diagnostic = ''
                error_path = leg / 'build' / (stage['name'] + '.stderr')
                if error_path.is_file():
                    with error_path.open('rb') as stream:
                        diagnostic = ' '.join(stream.read(4096).decode(errors='replace').split())[:320]
                return lane, f"{stage['name']} exit {stage['exit_code']} {diagnostic}".strip()
    return lane, failure.get('error', 'compiler or executable check failed')[:400]


def completed_pairs(runs):
    pairs = {}
    for run in runs:
        if run['complete'] and run['output_correct']:
            pairs.setdefault(run['position'] // 2, set()).add(run['lane'])
    return sum(lanes == {'mlf', 'ghc'} for lanes in pairs.values())


def measure(folder, setup, row, args, repeats, reference):
    family, size = row['family'], row['size']
    argv = [sys.executable, '-B', bench.HERE / 'run.py', '--output', folder, '--setup', setup,
            '--cohort', folder.name, '--family', family, '--endpoint', args.endpoint,
            '--repeats', repeats, '--interleave-pairs']
    if size:
        argv += ['--size', size]
    if args.cohort_output_gib is not None:
        argv += ['--cohort-output-gib', args.cohort_output_gib]
    print(f'Running {family} at size {size}', flush=True)
    status = command_runner.run_recorder(list(map(str, argv)), bench.ROOT)
    if status < 0:
        raise SystemExit(128 - status)
    receipt_path = folder / 'receipt.json'
    receipt = analyze.load(receipt_path) if receipt_path.is_file() else {}
    runs = receipt.get('runs', [])
    row['completed_pairs'] = completed_pairs(runs)
    if receipt:
        row['evidence'] += '/receipt.json'
    if status or not receipt.get('all_cases_passed') or not receipt.get('complete') or receipt['failures']:
        lane, reason = failure_detail(folder, receipt)
        if status:
            reason = f'recorder exit {status}; {reason}'
        row.update(status='failed', lane=lane, reason=reason)
        return
    rows, plan, _, _ = analyze.analyze(folder)
    if (len(rows) != 1 or (rows[0]['family'], rows[0]['size']) != (family, size)
            or row['completed_pairs'] != repeats or plan['benchmark']['repeats'] != repeats
            or plan['benchmark']['endpoint']['id'] != args.endpoint):
        raise ValueError('analyzed cohort differs from the requested cell')
    # Per-cell sources vary. All other inputs, including the compiler, benchmark
    # scripts and setup, must match before putting their numbers in one table.
    sources = {case['source'] for case in plan['cases']}
    identity = {path: digest for path, digest in plan['inputs'].items() if path not in sources}
    identity.update(revision=plan['source']['commit'], patch=plan['source']['patch_sha256'])
    if not reference:
        reference.update(identity)
    if reference != identity:
        raise ValueError('source revision, tracked patch or shared measurement inputs changed during sweep')
    metrics = rows[0]
    row.update(status='passed', mlf_seconds=metrics['mlf_wall_median'],
               ghc_seconds=metrics['ghc_wall_median'], mlf_over_ghc=metrics['mlf_over_ghc'])


def prune_products(folder):
    """Keep source, checked artifacts, command receipts, oracle results and cache evidence."""
    receipt = analyze.load(folder / 'receipt.json')
    products = []
    for run in receipt['runs']:
        build = folder / 'legs' / f"{run['position']:03d}-{run['case']}-{run['lane']}" / 'build'
        executable = build / 'program'
        if analyze.sha(executable) != run['executable_sha256']:
            raise ValueError(f'could not verify {executable} before pruning')
        products.append(executable)
        if run['lane'] == 'ghc':
            products.extend([build / 'Main.o', build / 'Main.hi'])
    sizes = [path.stat().st_size for path in products]
    for path in products:
        path.unlink()
    return len(products), sum(sizes)


def save_tables(root, rows, repeats, endpoint):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    families = list(dict.fromkeys(row['family'] for row in rows))
    sizes = sorted({row['size'] for row in rows})
    by_cell = {(row['family'], row['size']): row for row in rows}
    lines = ['# MLF and GHC compilation time', '',
             f'Median elapsed seconds for MLF / GHC, {repeats} paired builds per size, endpoint `{endpoint}`. '
             'Each compiler builds the same source to a fresh native executable.', '',
             '| Family | ' + ' | '.join(map(str, sizes)) + ' |', '| --- |' + ' ---: |' * len(sizes)]
    for family in families:
        cells = []
        for size in sizes:
            row = by_cell.get((family, size))
            if row is None:
                cells.append('—')
            elif row['status'] == 'passed':
                cells.append(f"[{row['mlf_seconds']:.3f} / {row['ghc_seconds']:.3f}]({row['evidence']})")
            else:
                cells.append(row['status'])
        lines.append(f'| `{family}` | ' + ' | '.join(cells) + ' |')
    failures = [row for row in rows if row['status'] == 'failed']
    if failures:
        lines.extend(['', '## Failed cells', ''])
        for row in failures:
            reason = ' '.join(row['reason'].split())
            lines.append(f"- [{row['family']} at {row['size']}]({row['evidence']}) "
                         f"({row['completed_pairs']}/{repeats} complete pairs). {row['lane']} {reason}".rstrip())
    lines += ['', '[Full-precision timings and outcomes](summary.csv)', '']
    for filename, content in [('summary.csv', out.getvalue()), ('summary.md', '\n'.join(lines))]:
        path = root / filename
        temporary = root / (filename + '.tmp')
        temporary.write_text(content)
        temporary.replace(path)


def run(args):
    matrix, families, sizes, baseline = bench.resolve('default', args.family, args.size)
    bench.measured_endpoint(args.endpoint)
    repeats = args.repeats if args.repeats is not None else matrix['repeats']
    if repeats < 3 or (args.cohort_output_gib is not None and args.cohort_output_gib <= 0):
        raise SystemExit('sweep requires at least three repetitions and a positive output budget')
    root = args.workdir.resolve()
    setup = (args.setup or root / 'setup' / 'setup.json').resolve()
    if not setup.is_file():
        raise SystemExit(f'missing setup {setup}')
    cells = ([('baseline', 0)] if baseline else []) + [(f, n) for f in families for n in sizes]
    if not cells or len(set(cells)) != len(cells):
        raise SystemExit('sweep requires distinct family/size cells')
    setup_record = analyze.load(setup)
    if not setup_record.get('complete') or setup_record.get('endpoint') != args.endpoint:
        raise SystemExit(f'incomplete or incompatible benchmark setup {setup}')
    if any((root / name).exists() for name in ('summary.csv', 'summary.md', 'cohorts')):
        raise SystemExit(f'choose a fresh sweep output directory: {root}')
    (root / 'cohorts').mkdir(parents=True)
    rows = [dict(family=family, size=size, status='pending', completed_pairs=0,
                 mlf_seconds='', ghc_seconds='', mlf_over_ghc='', lane='', reason='',
                 evidence=f'cohorts/{family}-{size}', pruned_files=0, pruned_bytes=0)
            for family, size in cells]
    reference = {}
    for row in rows:
        row['status'] = 'running'
        save_tables(root, rows, repeats, args.endpoint)
        folder = root / row['evidence']
        try:
            measure(folder, setup, row, args, repeats, reference)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            row.update(status='failed', reason=f'{type(exc).__name__}: {exc}')
        save_tables(root, rows, repeats, args.endpoint)
        if args.prune_build_products and row['status'] == 'passed':
            row['pruned_files'], row['pruned_bytes'] = prune_products(folder)
            save_tables(root, rows, repeats, args.endpoint)
    print(root / 'summary.md', flush=True)
    if any(row['status'] != 'passed' for row in rows):
        raise SystemExit(1)
