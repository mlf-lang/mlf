"""Offline point estimates for the standard compiler-shape matrix."""
import csv
import math
import re

import numpy as np

import analyze
from fit_growth import LANES, power_fit
from sweep import completed_pairs, failure_detail


def producer(revision, binary, receipt):
    analyze.require(re.fullmatch('[0-9a-f]{64}', binary) and re.fullmatch('[0-9a-f]{64}', receipt),
                    'invalid compiler identity')
    analyze.require(not revision or re.fullmatch('[0-9a-f]{40}', revision), 'invalid compiler revision')
    return revision, binary, receipt


def published_cell(row, repeats):
    ident = producer(row['compiler_revision'], row['compiler_sha256'], row['producer_receipt_sha256'])
    analyze.require(ident[0], 'missing published compiler revision')
    if row['passed'] == 'False':
        analyze.require(0 <= int(row['completed_pairs']) < repeats and row['failed_lane'] in LANES
                        and row['reason'] and not any(row[lane + '_seconds'] for lane in LANES),
                        'inconsistent failed cell')
        return ident, None, row['failed_lane'] + ': ' + row['reason']
    analyze.require(row['passed'] == 'True' and int(row['completed_pairs']) == repeats
                    and not row['reason'] and not row['failed_lane']
                    and all(int(row['successful_' + lane]) == repeats and int(row['skipped_' + lane]) == 0
                            for lane in LANES), 'inconsistent completed cell')
    return ident, [float(row[lane + '_seconds']) for lane in LANES], ''


def sweep_cell(root, row, repeats, profiles):
    # The plan records the executable and receipt hashes. Its source commit
    # belongs to the recorder and need not identify the measured compiler.
    size = int(row['size'])
    folder = root / 'cohorts' / f"{row['family']}-{size}"
    status = row['status']
    if status in ('pending', 'running'):
        return None, None, status
    if status == 'failed':
        plan_path, receipt_path = folder / 'plan.json', folder / 'receipt.json'
        has_receipt = receipt_path.is_file()
        evidence = folder.relative_to(root) / 'receipt.json' if has_receipt else folder.relative_to(root)
        analyze.require(row['evidence'] == str(evidence), 'summary failure evidence path mismatch')
        receipt = analyze.load(receipt_path) if has_receipt else {}
        if has_receipt:
            analyze.require(plan_path.is_file() and receipt['plan_sha256'] == analyze.sha(plan_path),
                            'frozen plan digest')
            analyze.require(not (receipt['complete'] and receipt.get('all_cases_passed') and not receipt['failures']),
                            'summary reports a failed qualified cell')
        count = completed_pairs(receipt['runs']) if has_receipt else 0
        analyze.require(int(row['completed_pairs']) == count, 'summary failed-cell pair count mismatch')
        lane, reason = failure_detail(folder, receipt)
        # The recorder's process exit status is available only to the sweep.
        # Use the recorded lane diagnostic in the point report.
        summary_reason = row['reason']
        analyze.require(row['lane'] == lane and (summary_reason == reason or
                        re.sub(r'^recorder exit [1-9][0-9]*; ', '', summary_reason) == reason),
                        'summary failure detail mismatch')
        issue = ': '.join(filter(None, (status, lane, reason)))
        if not has_receipt:
            return None, None, issue
        plan = analyze.load(plan_path)
        measurements = None
    else:
        analyze.require(status == 'passed', 'unknown sweep status')
        metrics, plan, receipt, _ = analyze.analyze(folder)
        analyze.require(len(metrics) == 1 and completed_pairs(receipt['runs']) == repeats
                        and int(row['completed_pairs']) == repeats, 'summary differs from measured pairs')
        measurements = [metrics[0][lane + '_wall_median'] for lane in LANES]
        analyze.require(measurements == [float(row[lane + '_seconds']) for lane in LANES], 'summary median mismatch')
        issue = ''
    cases = [(case['family'], case['size']) for case in plan['cases']]
    analyze.require(cases == [(row['family'], size)] and plan['benchmark']['repeats'] == repeats,
                    'summary differs from measured cell')
    profile = analyze.compatibility(plan)
    analyze.require(profiles.setdefault(row['family'], profile) == profile,
                    f"incompatible measurements in {row['family']}")
    tool = plan['toolchain']['producer']
    return producer('', tool['emlf_sha256'], tool['receipt_sha256']), measurements, issue


def points(source, matrix):
    sweep = source.is_dir()
    path = source / 'summary.csv' if sweep else source
    sizes = matrix['sizes']
    repeats = matrix['repeats']
    groups = {}
    profiles = {}
    with path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            family, size = row['family'], int(row['size'])
            if size not in sizes:
                continue
            analyze.require(family in matrix['families'], f'unknown family {family}')
            cells = groups.setdefault(family, {})
            analyze.require(size not in cells, f'duplicate {family}/{size}')
            ident, times, issue = (sweep_cell(source, row, repeats, profiles) if sweep
                                   else published_cell(row, repeats))
            analyze.require(times is None or all(math.isfinite(t) and t > 0 for t in times),
                            f'invalid times at {family}/{size}')
            cells[size] = ident, times, issue
    analyze.require(groups, 'no standard measurements')
    for family in matrix['families']:
        if family not in groups and sweep:
            continue
        cells = groups.get(family, {})
        identities = {c[0] for c in cells.values() if c[0] is not None}
        analyze.require(len(identities) <= 1, f'mixed compiler identities in {family}')
        revision, binary, receipt = next(iter(identities), ('', '', ''))
        row = dict(family=family, compiler_revision=revision, compiler_sha256=binary,
                   producer_receipt_sha256=receipt, mlf_p=None, ghc_p=None, delta_p=None,
                   status='incomplete', reason='')
        failures = [f"{n}: {cells[n][2] if n in cells else 'unmeasured'}"
                    for n in sizes if n not in cells or cells[n][1] is None]
        if failures:
            row['reason'] = '; '.join(failures)
        else:
            issues = []
            for lane, times in zip(LANES, np.asarray([cells[n][1] for n in sizes]).T):
                fit = power_fit(np.asarray(sizes), times)
                if fit['scale_seconds'] == 0:
                    issues.append(lane + ' zero fitted growth')
                else:
                    row[lane + '_p'] = fit['p']
                    if not fit['interior']:
                        issues.append(lane + ' boundary fit')
            if row['mlf_p'] is not None and row['ghc_p'] is not None:
                row['delta_p'] = row['mlf_p'] - row['ghc_p']
            if issues:
                row.update(status='indeterminate', reason='; '.join(issues))
            else:
                row['status'] = 'met' if row['delta_p'] <= 0 else 'higher'
        yield row
