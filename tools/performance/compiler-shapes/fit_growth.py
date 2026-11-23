#!/usr/bin/env python3
"""Report build-time growth and peak memory for a qualified compiler-shape family."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import random
import statistics


LANES = ('mlf', 'ghc')
SEED = 20261115
REPLICATES = 2000
MIN_POSITIVE_SIZES = 3
MIN_PAIRED_REPEATS = 2
TIMING_CHECKS = (
    'all_positive_medians_lower', 'lower_ols_point', 'lower_endpoint_point',
    'lower_power_point', 'lower_ols_95', 'lower_power_95',
)
PEAK_RSS_CHECK = 'peak_rss_at_most_ghc'
RSS_SAMPLE = 'sampled_process_tree_peak_rss_bytes'
RSS_SLOPE_CHECK = 'peak_rss_slope_at_most_ghc'
RSS_CI_CHECK = 'peak_rss_slope_delta_95_at_most_zero'
CHECKS = (*TIMING_CHECKS, PEAK_RSS_CHECK, RSS_SLOPE_CHECK, RSS_CI_CHECK)
PEAK_RSS_MEDIANS = ('mlf_peak_rss_bytes', 'ghc_peak_rss_bytes')
PEAK_RSS_RATIO = 'mlf_over_ghc_peak_rss'
PEAK_RSS_FIELDS = (*PEAK_RSS_MEDIANS, PEAK_RSS_RATIO)
PEAK_RSS_NOTE = ('Each build contributes its largest sampled sum of resident bytes across the build process group. '
                 'Sampling about every 100 ms can miss short peaks. A leg without an RSS observation '
                 'leaves that compiler’s median unavailable.')


def include_baseline(families, sizes, automatic):
    return 'baseline' in families or (automatic and len(sizes) >= MIN_POSITIVE_SIZES)


def paired_times(rows, samples, family, repeats):
    """Rows provide verified sizes. Position identifies the adjacent compiler pair."""
    if family == 'baseline':
        raise ValueError('choose the growing family; baseline-0 is included automatically')
    selected = sorted((row for row in rows if row['family'] in ('baseline', family)),
                      key=lambda row: row['size'])
    sizes = [row['size'] for row in selected]
    if (len(sizes) <= MIN_POSITIVE_SIZES or len(set(sizes)) != len(sizes) or sizes[0] != 0
            or selected[0]['family'] != 'baseline' or repeats < MIN_PAIRED_REPEATS
            or any(row['family'] != family for row in selected[1:])):
        raise ValueError('need baseline-0, at least three distinct positive sizes and repeated pairs')
    cells = {row['case']: [] for row in selected}
    for sample in samples:
        if sample['case'] in cells:
            cells[sample['case']].append(sample)
    return sizes, [paired_cell(cell, repeats) for cell in cells.values()]


def paired_cell(samples, repeats, field='wall_seconds'):
    cell = [None] * (2 * repeats)
    for sample in samples:
        position = sample['position']
        if not 0 <= position < len(cell) or cell[position] is not None:
            raise ValueError('duplicate or unexpected compiler position')
        cell[position] = sample
    pairs = []
    for first, second in zip(cell[::2], cell[1::2]):
        if first is None or second is None or second['order'] != first['order'] + 1:
            raise ValueError('missing or nonadjacent compiler pair')
        if {first['lane'], second['lane']} != set(LANES):
            raise ValueError('need one MLF and one GHC measurement per pair')
        observed = {sample['lane']: sample[field] for sample in (first, second)}
        if any(not math.isfinite(t) or t < 0 for t in observed.values()):
            raise ValueError('invalid paired timing')
        pairs.append(tuple(observed[lane] for lane in LANES))
    return pairs


def nonnegative_line(x, y):
    """Least squares for y = a + b*x with a,b nonnegative."""
    x_mean, y_mean = statistics.fmean(x), statistics.fmean(y)
    centered = [value - x_mean for value in x]
    denominator = sum(value * value for value in centered)
    b = 0.
    if denominator:
        b = max(0., sum(dx * (observed - y_mean) for dx, observed in zip(centered, y)) / denominator)
    a = y_mean - b * x_mean
    if a < 0:
        a = 0.
        b = max(0., sum(u * v for u, v in zip(x, y)) / sum(u * u for u in x))
    error = sum((observed - (a + b * value)) ** 2 for value, observed in zip(x, y))
    return error, a, b


INTERIOR_MIN = 0.101
INTERIOR_MAX = 2.999


def power_fit(sizes, times):
    """Fit a + b*(n/nmax)**p on the original seconds scale at the supplied sizes."""
    largest = max(sizes)
    scale = [size / largest for size in sizes]
    if max(times) == min(times):
        return {'p': .1, 'offset_seconds': times[0], 'scale_seconds': 0.,
                'rmse_seconds': 0., 'interior': False}

    def error(power):
        return nonnegative_line([value ** power for value in scale], times)[0]

    grid = [0.1 + i * ((3. - 0.1) / 20) for i in range(21)]
    scores = [error(power) for power in grid]
    best = min(range(len(scores)), key=scores.__getitem__)
    left, right = grid[max(0, best - 1)], grid[min(len(grid) - 1, best + 1)]
    ratio = (5 ** .5 - 1) / 2
    c, d = right - ratio * (right - left), left + ratio * (right - left)
    fc, fd = error(c), error(d)
    for _ in range(40):
        if right - left <= 1e-6:
            break
        if fc < fd:
            right, d, fd = d, c, fc
            c = right - ratio * (right - left)
            fc = error(c)
        else:
            left, c, fc = c, d, fd
            d = left + ratio * (right - left)
            fd = error(d)
    power = min((scores[best], grid[best]), (fc, c), (fd, d))[1]
    squared_error, floor, amplitude = nonnegative_line([value ** power for value in scale], times)
    return {'p': power, 'offset_seconds': floor, 'scale_seconds': amplitude,
            'rmse_seconds': (squared_error / len(sizes)) ** .5,
            'interior': INTERIOR_MIN <= power <= INTERIOR_MAX}


def power_order_issue(mlf, ghc):
    for lane, fit in zip(LANES, (mlf, ghc)):
        if fit['scale_seconds'] == 0:
            return lane + ' zero fitted growth'
    return ''


def median_pair(pairs):
    return tuple(map(statistics.median, zip(*pairs)))


def median_peak_rss(observations):
    """A zero or missing observation means the build peak was unavailable."""
    return statistics.median(observations) if observations and all(observations) else None


def peak_rss_ratio(mlf, ghc):
    return mlf / ghc if mlf is not None and ghc is not None else None


def slope_estimator(sizes, scale=1.):
    mean_size = statistics.fmean(sizes)
    centered = [size - mean_size for size in sizes]
    variation = sum(dx * dx for dx in centered)

    def slope(values):
        mean = statistics.fmean(values)
        return scale * sum(dx * (y - mean) for dx, y in zip(centered, values)) / variation
    return slope


def peak_rss_growth(sizes, pairs):
    slope = slope_estimator(sizes)
    def slopes(medians):
        return [slope(lane) / 2**20 for lane in zip(*medians)]
    mlf, ghc = slopes(map(median_pair, pairs))
    rng = random.Random(SEED)
    deltas = []
    for _ in range(REPLICATES):
        a, b = slopes(median_pair(rng.choices(cell, k=len(cell))) for cell in pairs)
        deltas.append(a - b)
    cuts = statistics.quantiles(deltas, n=40, method='inclusive')
    return dict(mlf_mib_per_unit=mlf, ghc_mib_per_unit=ghc, delta_mib_per_unit_95=[cuts[0], cuts[-1]])


def growth(sizes, times):
    medians = [median_pair(cell) for cell in times]
    slope_ms = slope_estimator(sizes, 1000.)

    estimates = {}
    for lane, observed in zip(LANES, zip(*medians)):
        estimates[lane] = {
            'median_seconds': list(observed), 'ols_ms_per_function': slope_ms(observed),
            'endpoint_ms_per_function': 1000 * (observed[-1] - observed[0]) / (sizes[-1] - sizes[0]),
            'power': power_fit(sizes, observed),
        }
    rng = random.Random(SEED)
    slope_deltas, power_deltas = [], []
    for _ in range(REPLICATES):
        # Draw both compiler times together at each size, independently across sizes.
        a, b = zip(*(median_pair(rng.choices(cell, k=len(cell))) for cell in times))
        slope_deltas.append(slope_ms(a) - slope_ms(b))
        power_deltas.append(power_fit(sizes, a)['p'] - power_fit(sizes, b)['p'])
    # 40 equal-probability groups put the first and last cut at 2.5% and 97.5%.
    intervals = [statistics.quantiles(deltas, n=40, method='inclusive')
                 for deltas in (slope_deltas, power_deltas)]
    slope_ci, power_ci = ([cuts[0], cuts[-1]] for cuts in intervals)
    mlf, ghc = (estimates[lane] for lane in LANES)
    checks = {'all_positive_medians_lower': all(a < b for a, b in medians[1:]),
              'lower_ols_point': mlf['ols_ms_per_function'] < ghc['ols_ms_per_function'],
              'lower_endpoint_point': mlf['endpoint_ms_per_function'] < ghc['endpoint_ms_per_function'],
              'lower_power_point': mlf['power']['p'] <= ghc['power']['p'],
              'lower_ols_95': slope_ci[1] < 0, 'lower_power_95': power_ci[1] <= 0}
    interior = all(item['power']['interior'] for item in estimates.values())
    issue = power_order_issue(mlf['power'], ghc['power'])
    if issue:
        checks.update(lower_power_point=None, lower_power_95=None)
    return {'sizes': list(sizes), 'pairs_per_size': len(times[0]), 'estimates': estimates,
            'paired_bootstrap': {'seed': SEED, 'iterations': REPLICATES,
                                 'ols_delta_ms_95': slope_ci, 'p_delta_95': power_ci},
            'checks': checks, 'interior': interior, 'power_order_issue': issue, 'accepted': all(checks.values())}


def family_reports(rows, samples, repeats):
    """Evaluate each selected family using qualified pairs from one measurement window."""
    families, by_case = defaultdict(list), defaultdict(list)
    for row in rows:
        families[row['family']].append(row)
    for sample in samples:
        by_case[sample['case']].append(sample)
    baseline = families.pop('baseline', [])
    reports = []
    for family, positives in sorted(families.items()):
        positives.sort(key=lambda row: row['size'])
        selected = baseline + positives
        incomplete = [row['case'] for row in selected if row.get('status', 'passed') != 'passed']
        reasons = []
        if not baseline or len(positives) < MIN_POSITIVE_SIZES or repeats < MIN_PAIRED_REPEATS:
            reasons.append('requires baseline-0, at least three positive sizes and repeated pairs')
        if incomplete:
            reasons.append('incomplete cells: ' + ', '.join(incomplete))
        report = {'family': family, 'sizes': [row['size'] for row in selected],
                  'pairs_per_size': repeats, 'status': 'incomplete',
                  'reason': '. '.join(reasons), 'checks': dict.fromkeys(CHECKS), 'accepted': None}
        if reasons:
            if not any(row['case'] in incomplete for row in positives) and repeats:
                medians = [median_pair(paired_cell(by_case[row['case']], repeats)) for row in positives]
                report['checks']['all_positive_medians_lower'] = all(a < b for a, b in medians)
        else:
            observations = (sample for row in selected for sample in by_case[row['case']])
            sizes, times = paired_times(selected, observations, family, repeats)
            result = growth(sizes, times)
            report.update(result)
            if result['power_order_issue']:
                report.update(status='indeterminate', reason=result['power_order_issue'])
            else:
                report['status'] = 'met' if result['accepted'] else 'unmet'
        rss = [{'size': row['size'], **{field: row.get(field) for field in PEAK_RSS_FIELDS}}
               for row in selected]
        report['peak_rss'] = rss
        positive_peaks = [row for row in rss if row['size'] > 0]
        missing_rss = [str(row['size']) for row in positive_peaks if row[PEAK_RSS_RATIO] is None]
        if missing_rss:
            reason = 'peak build RSS unavailable at sizes ' + ', '.join(missing_rss)
            report.update(status='incomplete', accepted=None,
                          reason='. '.join(filter(None, (report['reason'], reason))))
            report['checks'][PEAK_RSS_CHECK] = None
        else:
            memory_ok = all(row[PEAK_RSS_RATIO] <= 1. for row in positive_peaks)
            report['checks'][PEAK_RSS_CHECK] = memory_ok
            if report['accepted'] and not memory_ok:
                report.update(status='unmet', accepted=False)
        report['checks'].update(dict.fromkeys((RSS_SLOPE_CHECK, RSS_CI_CHECK)))
        if not reasons:
            missing = [row['case'] for row in selected
                       if any(not sample.get(RSS_SAMPLE) for sample in by_case[row['case']])]
            if missing:
                reason = 'paired peak RSS unavailable for ' + ', '.join(missing)
                report.update(status='incomplete', accepted=None,
                              reason='. '.join(filter(None, (report['reason'], reason))))
            else:
                pairs = [paired_cell(by_case[row['case']], repeats, RSS_SAMPLE) for row in selected]
                memory = peak_rss_growth(report['sizes'], pairs)
                report['peak_rss_growth'] = memory
                point = memory['mlf_mib_per_unit'] <= memory['ghc_mib_per_unit']
                confidence = memory['delta_mib_per_unit_95'][1] <= 0
                report['checks'].update({RSS_SLOPE_CHECK: point, RSS_CI_CHECK: confidence})
                if report['accepted'] and not (point and confidence):
                    report.update(status='unmet', accepted=False)
        reports.append(report)
    return reports


def format_peak_rss(row):
    medians = ['—' if row.get(field) is None else f'{row[field] / 2**20:.2f}' for field in PEAK_RSS_MEDIANS]
    ratio = row.get(PEAK_RSS_RATIO)
    return (*medians, '—' if ratio is None else f'{ratio:.3f}')


def peak_rss_markdown(rows):
    lines = ['**Median sampled peak build RSS (MiB)**', '', PEAK_RSS_NOTE, '',
             '| Family | Size | MLF | GHC | MLF / GHC |', '| --- | ---: | ---: | ---: | ---: |']
    for row in sorted(rows, key=lambda r: (r['family'], r['size'])):
        fields = (f"`{row['family']}`", str(row['size']), *format_peak_rss(row))
        lines.append('| ' + ' | '.join(fields) + ' |')
    return lines


def format_exponent(fit):
    value = f"{fit['p']:.6g}"
    if fit['interior'] or fit['scale_seconds'] == 0:
        return value
    bound = 'lower' if fit['p'] < INTERIOR_MIN else 'upper'
    return f'{value} ({bound} bound)'


def markdown(reports):
    lines = ['Lower values favor MLF. Point estimates are MLF / GHC. Intervals are 95% paired '
             'bootstrap intervals for MLF minus GHC over the measured sizes.', '']
    if not reports:
        return lines + ['No growing family selected.']
    lines += ['| Family | Sizes | Lower wall medians at all positive sizes | OLS slope (ms/unit) '
              '| Endpoint slope (ms/unit) | Exponent | OLS slope interval | Exponent interval '
              '| Peak RSS ≤ GHC at all positive sizes | Peak RSS slope (MiB/unit) | RSS slope difference 95% interval | Verdict |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    verdicts = {True: 'pass', False: 'fail', None: '—'}
    for report in reports:
        checks = report['checks']
        values = ['—'] * 5
        if 'estimates' in report:
            mlf, ghc = (report['estimates'][lane] for lane in LANES)
            paired = report['paired_bootstrap']
            values = [f"{mlf['ols_ms_per_function']:.6g} / {ghc['ols_ms_per_function']:.6g}",
                      f"{mlf['endpoint_ms_per_function']:.6g} / {ghc['endpoint_ms_per_function']:.6g}",
                      f"{format_exponent(mlf['power'])} / {format_exponent(ghc['power'])}",
                      *[f'[{lo:.6g}, {hi:.6g}]' for lo, hi in
                        (paired['ols_delta_ms_95'], paired['p_delta_95'])]]
            values = [f'{value} ({verdicts[checks[key]]})' for value, key in zip(values, TIMING_CHECKS[1:])]
        outcome = report['status']
        if report['reason']:
            outcome += ' · ' + report['reason']
        memory = checks[PEAK_RSS_CHECK]
        slope_result = interval_result = '—'
        if 'peak_rss_growth' in report:
            rss = report['peak_rss_growth']
            lo, hi = rss['delta_mib_per_unit_95']
            slope_result = (f"{rss['mlf_mib_per_unit']:.5g} / {rss['ghc_mib_per_unit']:.5g} "
                            f"({verdicts[checks[RSS_SLOPE_CHECK]]})")
            interval_result = f"[{lo:.5g}, {hi:.5g}] ({verdicts[checks[RSS_CI_CHECK]]})"
        fields = [f"`{report['family']}`", ', '.join(map(str, report['sizes'])),
                  verdicts[checks[TIMING_CHECKS[0]]], *values,
                  'incomplete' if memory is None else verdicts[memory], slope_result, interval_result, outcome]
        lines.append('| ' + ' | '.join(fields) + ' |')
    return lines


def main():
    import analyze

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cohort', type=Path)
    parser.add_argument('--family', required=True)
    parser.add_argument('--output', type=Path, help='write the JSON result to this path')
    args = parser.parse_args()
    rows, plan, _, samples = analyze.analyze(args.cohort)
    selected = [row for row in rows if row['family'] in ('baseline', args.family)]
    reports = family_reports(selected, samples, plan['benchmark']['repeats'])
    if not reports:
        parser.error('choose a growing family recorded in the cohort')
    result, = reports
    result.update(endpoint=plan['benchmark']['endpoint']['id'],
                  receipt_sha256=analyze.sha(args.cohort / 'receipt.json'))
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
