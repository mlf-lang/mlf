"""Serial family-by-family measurements with a table of complete and failed cells."""
import csv
import io
import json
import sys
from pathlib import Path

import analyze
import bench
import command_runner
import compiler_reference
import fit_growth
import framework_results as framework
import provenance
import worker


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


def completed_pairs(runs, with_reference=False):
    lanes_per_round = 3 if with_reference else 2
    expected = {'mlf', 'ghc', 'reference'} if with_reference else {'mlf', 'ghc'}
    pairs = {}
    for run in runs:
        if run['complete'] and run['output_correct']:
            pairs.setdefault(run['position'] // lanes_per_round, set()).add(run['lane'])
    return sum(lanes == expected for lanes in pairs.values())


def measure(folder, setup, row, args, repeats, reference, source_root):
    family, size = row['family'], row['size']
    argv = [sys.executable, '-B', bench.HERE / 'run.py', '--output', folder, '--setup', setup,
            '--cohort', folder.name, '--family', family, '--endpoint', args.endpoint,
            '--repeats', repeats, '--interleave-pairs', '--record-only', '--framework-child']
    argv += ['--sweep-reference', json.dumps(args.baseline_selection)]
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
    plan_file = folder/'plan.json'
    has_reference = plan_file.is_file() and bool(analyze.load(plan_file).get('compiler_reference'))
    row['completed_pairs'] = completed_pairs(runs, has_reference)
    if receipt:
        row['evidence'] += '/receipt.json'
    if status or not receipt.get('all_cases_passed') or not receipt.get('complete') or receipt['failures']:
        lane, reason = failure_detail(folder, receipt)
        if status:
            reason = f'recorder exit {status}; {reason}'
        row.update(status='failed', lane=lane, reason=reason)
        return []
    rows, plan, receipt, samples = analyze.analyze(folder)
    if (len(rows) != 1 or (rows[0]['family'], rows[0]['size']) != (family, size)
            or row['completed_pairs'] != repeats or plan['benchmark']['repeats'] != repeats
            or plan['benchmark']['endpoint']['id'] != args.endpoint):
        raise ValueError('analyzed cohort differs from the requested cell')
    check_shared_inputs(source_root, folder, plan, reference)
    metrics = rows[0]
    row.update(status='passed', mlf_seconds=metrics['mlf_wall_median'],
               ghc_seconds=metrics['ghc_wall_median'], mlf_over_ghc=metrics['mlf_over_ghc'],
               **{field: metrics[field] for field in fit_growth.PEAK_RSS_FIELDS})
    if has_reference:
        row.update(reference_commit=plan['compiler_reference']['commit'],
                   reference_seconds=metrics['reference_wall_median'],
                   mlf_over_reference=metrics['mlf_over_reference'],
                   reference_peak_rss_bytes=metrics['reference_peak_rss_bytes'],
                   mlf_over_reference_peak_rss=metrics['mlf_over_reference_peak_rss'])
    return samples


def check_shared_inputs(root, folder, plan, reference):
    sources = {case['source'] for case in plan['cases']}
    sources.update(lib['source'] for case in plan['cases'] for lib in worker.dependencies(case))
    inputs = {path: digest for path, digest in plan['inputs'].items() if path not in sources}
    if not inputs:
        raise ValueError('missing shared measurement inputs')
    source = plan['source']
    if reference and source['commit'] != reference['commit']:
        raise ValueError('source revision changed during sweep')
    if reference and inputs != reference['inputs']:
        raise ValueError('shared measurement inputs changed during sweep')
    try:
        patch = provenance.archived_patch(folder, source)
        patch_key = (source['patch_sha256'], source.get('patch_format'))
        if reference and patch_key == reference['patch_key']:
            return
        changes = provenance.protected_changes(root, source, patch)
    except (KeyError, OSError, ValueError) as exc:
        raise ValueError(f'invalid tracked patch evidence: {exc}') from exc
    if reference and changes != reference['changes']:
        raise ValueError('tracked files outside the documentation exception changed during sweep')
    reference.update(inputs=inputs, commit=source['commit'], patch_key=patch_key, changes=changes)


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


def comparison_table(by_cell, families, sizes, format_cell):
    lines = ['| Family | ' + ' | '.join(map(str, sizes)) + ' |', '| --- |' + ' ---: |' * len(sizes)]
    for family in families:
        cells = []
        for size in sizes:
            row = by_cell.get((family, size))
            if row is None:
                cells.append('—')
            elif row['status'] == 'passed':
                cells.append(f"[{format_cell(row)}]({row['evidence']})")
            else:
                cells.append(row['status'])
        lines.append(f'| `{family}` | ' + ' | '.join(cells) + ' |')
    return lines


def save_tables(root, rows, repeats, endpoint, growth=None, reference_growth=None, selection=None):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    families = list(dict.fromkeys(row['family'] for row in rows))
    sizes = sorted({row['size'] for row in rows})
    by_cell = {(row['family'], row['size']): row for row in rows}
    lines = ['# MLF and GHC compilation time and memory', '',
             f'Each cell shows MLF / GHC for {repeats} paired builds at endpoint `{endpoint}`. '
             'Each compiler builds the same source to a fresh native executable.', '',
             '## Median elapsed time (seconds)', '']
    lines.extend(comparison_table(by_cell, families, sizes,
                                  lambda row: f"{row['mlf_seconds']:.3f} / {row['ghc_seconds']:.3f}"))
    lines.extend(['', '## Median sampled peak process-group RSS (MiB)', '',
                  fit_growth.PEAK_RSS_NOTE, 'Each cell shows MLF / GHC and the MLF-to-GHC ratio in parentheses.', ''])

    def memory_cell(row):
        mlf, ghc, ratio = fit_growth.format_peak_rss(row)
        return f'{mlf} / {ghc} ({ratio})'

    lines.extend(comparison_table(by_cell, families, sizes, memory_cell))
    if selection:
        show = [dict(row,mlf_wall_median=row['mlf_seconds'],reference_wall_median=row['reference_seconds'])
                for row in rows if row['status']=='passed' and row.get('reference_seconds') != '']
        lines += analyze.baseline_table(show, {'baseline_selection':selection})
    failures = [row for row in rows if row['status'] == 'failed']
    if failures:
        lines.extend(['', '## Failed cells', ''])
        for row in failures:
            reason = ' '.join(row['reason'].split())
            lines.append(f"- [{row['family']} at {row['size']}]({row['evidence']}) "
                         f"({row['completed_pairs']}/{repeats} complete pairs). {row['lane']} {reason}".rstrip())
    files = {'summary.csv': out.getvalue()}
    if growth is not None:
        lines += ['', '## Build performance checks', '', *fit_growth.markdown(growth), '',
                  '[Full-precision check results](growth.json)']
        result = {'endpoint':endpoint,'growth':growth,'baseline_selection':selection}
        if reference_growth is not None:
            result['reference_growth'] = reference_growth
            lines += ['', '## Growth against the committed compiler', '', *fit_growth.markdown(reference_growth,'reference')]
        files['growth.json'] = json.dumps(result, indent=2) + '\n'
    lines += ['', '[Full-precision timings, median peak RSS in bytes, and outcomes](summary.csv)', '']
    files['summary.md'] = '\n'.join(lines)
    for filename, content in files.items():
        path = root / filename
        temporary = root / (filename + '.tmp')
        temporary.write_text(content)
        temporary.replace(path)


def run(args):
    matrix, families, sizes, baseline = bench.resolve('default', args.family, args.size)
    bench.measured_endpoint(args.endpoint)
    repeats = args.repeats if args.repeats is not None else matrix['repeats']
    if repeats < fit_growth.MIN_PAIRED_REPEATS or (args.cohort_output_gib is not None and args.cohort_output_gib <= 0):
        raise SystemExit(f'sweep requires at least {fit_growth.MIN_PAIRED_REPEATS} pairs per size and a positive output budget')
    root = args.workdir.resolve()
    cells = ([('baseline', 0)] if baseline else []) + [(f, n) for f in families for n in sizes]
    if not cells or len(set(cells)) != len(cells):
        raise SystemExit('sweep requires distinct family/size cells')
    cells, ids = framework.select(cells)
    if framework.active():
        framework.events.plan(ids)
    else:
        ids = []
    if any((root / name).exists() for name in ('summary.csv', 'summary.md', 'growth.json', 'cohorts')):
        raise SystemExit(f'choose a fresh sweep output directory: {root}')
    # Reserve the output before preparing inputs. Concurrent sweeps cannot both
    # build into the same producer or replace one another's table.
    cohorts = root / 'cohorts'
    cohorts.mkdir(parents=True)
    try:
        setup = bench.sweep_setup(args)
        if not setup.is_file():
            raise SystemExit(f'missing setup {setup}')
        setup_record = analyze.load(setup)
        if not setup_record.get('complete') or setup_record.get('endpoint') != args.endpoint:
            raise SystemExit(f'incomplete or incompatible benchmark setup {setup}')
    except BaseException:
        cohorts.rmdir()
        raise
    source_root = Path(setup_record.get('source', bench.ROOT)).resolve()
    args.baseline_selection = compiler_reference.select_revision(source_root,
        [cohorts,setup.parent,setup_record.get('producer',root/'producer'),root/'summary.md',root/'summary.csv',root/'growth.json'])
    rows = [dict(reference_seconds='',reference_commit='',mlf_over_reference='',reference_peak_rss_bytes=None,
                 mlf_over_reference_peak_rss=None,family=family, size=size, status='pending', completed_pairs=0,
                 mlf_seconds='', ghc_seconds='', mlf_over_ghc='', **dict.fromkeys(fit_growth.PEAK_RSS_FIELDS),
                 lane='', reason='',
                 evidence=f'cohorts/{family}-{size}', pruned_files=0, pruned_bytes=0)
            for family, size in cells]
    reference, samples = {}, []
    for row in rows:
        cell = (row['family'], row['size'])
        framework.start(ids, cell, endpoint=args.endpoint, repeats=repeats)
        row['status'] = 'running'
        save_tables(root, rows, repeats, args.endpoint, selection=args.baseline_selection)
        folder = root / row['evidence']
        try:
            samples.extend(measure(folder, setup, row, args, repeats, reference, source_root))
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            row.update(status='failed', reason=f'{type(exc).__name__}: {exc}')
        save_tables(root, rows, repeats, args.endpoint, selection=args.baseline_selection)
        if args.prune_build_products and row['status'] == 'passed':
            row['pruned_files'], row['pruned_bytes'] = prune_products(folder)
            save_tables(root, rows, repeats, args.endpoint, selection=args.baseline_selection)
        framework.result(ids, cell, 'pass' if row['status'] == 'passed' else 'fail',
                         completed_pairs=row['completed_pairs'], lane=row['lane'], reason=row['reason'],
                         receipt=str(root / row['evidence']))
    cases = [dict(row, case=f"{row['family']}-{row['size']}") for row in rows]
    growth = fit_growth.family_reports(cases, samples, repeats)
    reference_growth = (fit_growth.family_reports(cases,samples,repeats,'reference')
                        if any(s['lane']=='reference' for s in samples) or (not samples and args.baseline_selection['commit']) else None)
    save_tables(root, rows, repeats, args.endpoint, growth, reference_growth, args.baseline_selection)
    print(root / 'summary.md', flush=True)
    if any(row['status'] != 'passed' for row in rows):
        raise SystemExit(1)
