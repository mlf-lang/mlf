#!/usr/bin/env python3
"""Fit complete-build growth for one family in a qualified compiler-shapes cohort."""
import argparse
import json
from pathlib import Path

import numpy as np

import analyze


LANES = ('mlf', 'ghc')
SEED = 20261115
REPLICATES = 2000


def paired_times(rows, samples, family, repeats):
    """Rows provide verified sizes. Position identifies the adjacent compiler pair."""
    if family == 'baseline':
        raise ValueError('choose the growing family; baseline-0 is included automatically')
    selected = sorted((row for row in rows if row['family'] in ('baseline', family)),
                      key=lambda row: row['size'])
    sizes = [row['size'] for row in selected]
    if (len(sizes) < 4 or len(set(sizes)) != len(sizes) or sizes[0] != 0
            or selected[0]['family'] != 'baseline' or repeats < 2
            or any(row['family'] != family for row in selected[1:])):
        raise ValueError('need baseline-0, at least three distinct positive sizes and repeated pairs')
    cells = {row['case']: [None] * (2 * repeats) for row in selected}
    for sample in samples:
        cell = cells.get(sample['case'])
        if cell is None:
            continue
        position = sample['position']
        if not 0 <= position < len(cell) or cell[position] is not None:
            raise ValueError('duplicate or unexpected compiler position')
        cell[position] = sample
    times = np.empty((len(sizes), repeats, 2))
    for index, cell in enumerate(cells.values()):
        for number, (first, second) in enumerate(zip(cell[::2], cell[1::2])):
            if first is None or second is None or second['order'] != first['order'] + 1:
                raise ValueError('missing or nonadjacent compiler pair')
            if {first['lane'], second['lane']} != set(LANES):
                raise ValueError('need one MLF and one GHC measurement per pair')
            for sample in (first, second):
                times[index, number, LANES.index(sample['lane'])] = sample['wall_seconds']
    if not np.isfinite(times).all() or (times < 0).any():
        raise ValueError('invalid paired timing')
    return np.asarray(sizes), times


def nonnegative_line(x, y):
    """Least squares for y = a + b*x with a,b nonnegative."""
    x_mean, y_mean = x.mean(), y.mean()
    centered = x - x_mean
    denominator = (centered ** 2).sum()
    b = max(0., float((centered * (y - y_mean)).sum() / denominator)) if denominator else 0.
    a = float(y_mean - b * x_mean)
    if a < 0:
        a = 0.
        b = max(0., float((x * y).sum() / (x * x).sum()))
    residual = y - (a + b * x)
    return float(residual @ residual), a, b


def power_fit(sizes, times):
    """Fit a + b*(n/nmax)**p on the original seconds scale, including n=0."""
    scale = sizes / max(sizes)

    def error(power):
        return nonnegative_line(scale ** power, times)[0]

    grid = np.linspace(0.1, 3., 21)
    scores = [error(power) for power in grid]
    best = int(np.argmin(scores))
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
    power = float(min((scores[best], grid[best]), (fc, c), (fd, d))[1])
    squared_error, floor, amplitude = nonnegative_line(scale ** power, times)
    return {'p': power, 'offset_seconds': floor, 'scale_seconds': amplitude,
            'rmse_seconds': (squared_error / len(sizes)) ** .5,
            'interior': .101 <= power <= 2.999}


def slope(sizes, times):
    centered = sizes - sizes.mean()
    return float((centered * (times - times.mean())).sum() / (centered ** 2).sum())


def growth(sizes, times):
    medians = np.median(times, axis=1)
    estimates = {}
    for index, lane in enumerate(LANES):
        observed = medians[:, index]
        estimates[lane] = {
            'median_seconds': observed.tolist(), 'ols_ms_per_function': 1000 * slope(sizes, observed),
            'endpoint_ms_per_function': float(1000 * (observed[-1] - observed[0]) / (sizes[-1] - sizes[0])),
            'power': power_fit(sizes, observed),
        }
    rng = np.random.default_rng(SEED)
    deltas = []
    for _ in range(REPLICATES):
        # Draw both compiler times together at each size, independently across sizes.
        sample = np.array([np.median(cell[rng.integers(len(cell), size=len(cell))], axis=0)
                           for cell in times])
        a, b = sample.T
        deltas.append([1000 * (slope(sizes, a) - slope(sizes, b)),
                       power_fit(sizes, a)['p'] - power_fit(sizes, b)['p']])
    slope_ci, power_ci = np.quantile(deltas, [.025, .975], axis=0).T.tolist()
    mlf, ghc = (estimates[lane] for lane in LANES)
    checks = {'all_positive_medians_lower': bool(np.all(medians[1:, 0] < medians[1:, 1])),
              'lower_ols_point': mlf['ols_ms_per_function'] < ghc['ols_ms_per_function'],
              'lower_endpoint_point': mlf['endpoint_ms_per_function'] < ghc['endpoint_ms_per_function'],
              'lower_power_point': mlf['power']['p'] < ghc['power']['p'],
              'lower_ols_95': slope_ci[1] < 0, 'lower_power_95': power_ci[1] < 0}
    interior = all(item['power']['interior'] for item in estimates.values())
    return {'sizes': sizes.tolist(), 'pairs_per_size': times.shape[1], 'estimates': estimates,
            'paired_bootstrap': {'seed': SEED, 'iterations': REPLICATES,
                                 'ols_delta_ms_95': slope_ci, 'p_delta_95': power_ci},
            'checks': checks, 'interior': interior, 'accepted': interior and all(checks.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cohort', type=Path)
    parser.add_argument('--family', required=True)
    parser.add_argument('--output', type=Path, help='write the JSON result to this path')
    args = parser.parse_args()
    rows, plan, _, samples = analyze.analyze(args.cohort)
    sizes, times = paired_times(rows, samples, args.family, plan['benchmark']['repeats'])
    result = growth(sizes, times)
    result.update(family=args.family, endpoint=plan['benchmark']['endpoint']['id'],
                  receipt_sha256=analyze.sha(args.cohort / 'receipt.json'))
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
