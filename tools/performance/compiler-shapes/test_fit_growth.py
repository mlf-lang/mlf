"""Regression checks for selecting and pairing finite-range scaling observations."""
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import fit_growth as fit
import matrix_growth


class GrowthTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'case': 'baseline-0', 'family': 'baseline', 'size': 0}]
        for size in (8, 16, 32):
            for family in ('chain', 'flat'):
                self.rows.append({'case': f'{family}-{size}', 'family': family, 'size': size})
        self.samples = []
        for repeat in range(2):
            for row in reversed(self.rows):
                for offset, lane in enumerate(fit.LANES if repeat == 0 else reversed(fit.LANES)):
                    base = 100 if row['family'] == 'flat' else row['size']
                    self.samples.append({'case': row['case'], 'order': len(self.samples),
                                         'position': repeat * 2 + offset, 'lane': lane,
                                         'wall_seconds': base + 2 * repeat + int(lane == 'ghc')})

    def test_selects_only_requested_family_and_preserves_pairs(self):
        sizes, times = fit.paired_times(self.rows, self.samples[::-1], 'chain', 2)
        self.assertEqual(sizes, [0, 8, 16, 32])
        self.assertEqual(times, [[(n, n + 1), (n + 2, n + 3)] for n in sizes])

    def test_rejects_unusable_pairs(self):
        _, second = self.samples[-2:]
        for changes, message in [({'position': 2}, 'position'), ({'order': 0}, 'nonadjacent'),
                                 ({'lane': 'ghc'}, 'one MLF'), ({'wall_seconds': float('nan')}, 'invalid')]:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                fit.paired_times(self.rows, self.samples[:-1] + [{**second, **changes}], 'chain', 2)
        with self.assertRaisesRegex(ValueError, 'missing'):
            fit.paired_times(self.rows, self.samples[:-1], 'chain', 2)
        with self.assertRaisesRegex(ValueError, 'baseline'):
            fit.paired_times(self.rows, self.samples, 'absent', 2)

    def test_known_curves_and_boundary(self):
        sizes = [0, 32, 128, 256, 1024]
        times = [[(.3 + .12 * (n / 1024) ** 1.1, .6 + .3 * (n / 1024) ** 1.4)] * 3 for n in sizes]
        with patch.object(fit, 'REPLICATES', 12):
            result = fit.growth(sizes, times)
        self.assertTrue(result['accepted'])
        self.assertAlmostEqual(result['estimates']['mlf']['power']['p'], 1.1, places=5)
        self.assertAlmostEqual(result['estimates']['ghc']['power']['offset_seconds'], .6, places=6)
        for bound in result['paired_bootstrap']['p_delta_95']:
            self.assertAlmostEqual(bound, -.3, places=5)
        self.assertFalse(fit.power_fit(sizes, [1 + (n / 1024) ** 4 for n in sizes])['interior'])

    def test_directional_exponent_boundaries(self):
        sizes = [0, 4, 8, 14, 19]
        for mlf, ghc, expected in [(2.25, 4, True), (4, 2.25, False), (.05, 4, True),
                                   (.05, .05, True), (4, 4, True)]:
            with self.subTest(mlf=mlf, ghc=ghc), patch.object(fit, 'REPLICATES', 12):
                pairs = [[(.2 + .1 * (n / 19)**mlf, .8 + (n / 19)**ghc)] * 2 for n in sizes]
                result = fit.growth(sizes, pairs)
                self.assertIs(result['checks']['lower_power_point'], expected)
                self.assertIs(result['checks']['lower_power_95'], expected)
                self.assertIs(result['accepted'], expected is True)

    def test_lower_point_can_have_interval_touching_zero(self):
        sizes = [0, 4, 8, 14, 19]
        pairs = [[(.2 + .1 * (n / 19)**power, .8 + (n / 19)**4) for power in (1.6, 4)]
                 for n in sizes]
        with patch.object(fit, 'REPLICATES', 120):
            result = fit.growth(sizes, pairs)
        self.assertTrue(result['checks']['lower_power_point'])
        self.assertEqual(result['paired_bootstrap']['p_delta_95'][1], 0.)
        self.assertTrue(result['checks']['lower_power_95'])
        self.assertTrue(result['accepted'])

    def test_missing_or_failed_cells_do_not_supply_growth_estimates(self):
        small = [row for row in self.rows if row['family'] == 'chain' and row['size'] == 8]
        result, = fit.family_reports(small, self.samples, 2)
        self.assertEqual(result['status'], 'incomplete')
        self.assertTrue(result['checks']['all_positive_medians_lower'])
        self.assertIsNone(result['checks']['lower_ols_point'])

        with patch.dict(self.rows[1], {'status': 'failed'}), patch.object(fit, 'REPLICATES', 12):
            chain, flat = fit.family_reports(self.rows, self.samples, 2)
        self.assertEqual(chain['status'], 'incomplete')
        self.assertIn('chain-8', chain['reason'])
        self.assertIsNone(chain['checks']['all_positive_medians_lower'])
        self.assertEqual(flat['sizes'], [0, 8, 16, 32])
        self.assertIsNotNone(flat['checks']['lower_ols_95'])

    def test_committed_compiler_wall_gate_uses_largest_size(self):
        sizes = [0, 8, 16, 32]
        times = [[pair, pair] for pair in [(1, 1), (3, 2), (4, 3), (5, 7)]]
        with patch.object(fit, 'REPLICATES', 12):
            ghc = fit.growth(sizes, times)
            baseline = fit.growth(sizes, times, 'reference')
        self.assertFalse(ghc['checks']['all_positive_medians_lower'])
        self.assertTrue(baseline['checks']['largest_positive_median_lower'])
        self.assertEqual(ghc['paired_bootstrap'], baseline['paired_bootstrap'])

    def test_absolute_memory_gate_uses_largest_positive_size_and_allows_a_tie(self):
        rows = [row.copy() for row in self.rows if row['family'] in ('baseline', 'chain')]
        for row in rows[1:]:
            row.update(mlf_peak_rss_bytes=128, ghc_peak_rss_bytes=128, mlf_over_ghc_peak_rss=1.)
        times = {'mlf': (.3, .12, 1.1), 'ghc': (.6, .3, 1.4)}
        samples = []
        for sample in self.samples:
            size = int(sample['case'].rsplit('-', 1)[1])
            startup, scale, exponent = times[sample['lane']]
            samples.append(dict(sample, wall_seconds=startup + scale * (size / 32)**exponent,
                                sampled_process_tree_peak_rss_bytes=128))

        with patch.object(fit, 'REPLICATES', 12):
            tied, = fit.family_reports(rows, samples, 2)
            with patch.dict(rows[1], mlf_peak_rss_bytes=256, mlf_over_ghc_peak_rss=2.):
                small_over, = fit.family_reports(rows[::-1], samples, 2)
            with patch.dict(rows[-1], mlf_peak_rss_bytes=256, mlf_over_ghc_peak_rss=2.):
                over_budget, = fit.family_reports(rows, samples, 2)
            with patch.dict(rows[-1], mlf_peak_rss_bytes=None, mlf_over_ghc_peak_rss=None):
                missing, = fit.family_reports(rows, samples, 2)
        self.assertTrue(small_over['accepted'])
        self.assertEqual(small_over['peak_rss_check_size'], 32)
        self.assertTrue(tied['accepted'])
        self.assertTrue(tied['checks'][fit.PEAK_RSS_CHECK])
        self.assertEqual(tied['status'], 'met')
        self.assertEqual(over_budget['status'], 'unmet')
        self.assertFalse(over_budget['accepted'])
        self.assertFalse(over_budget['checks'][fit.PEAK_RSS_CHECK])
        self.assertTrue(all(over_budget['checks'][key] for key in fit.TIMING_CHECKS))
        self.assertIsNone(missing['accepted'])
        self.assertIsNone(missing['checks'][fit.PEAK_RSS_CHECK])
        self.assertEqual(missing['status'], 'incomplete')
        self.assertIn('RSS unavailable at largest size 32', missing['reason'])

    def test_smaller_peaks_can_grow_faster(self):
        sizes = [0, 8, 16, 32]
        pairs = [[((10 + n + noise) * 2**20, (100 + noise) * 2**20) for noise in (0, 7)]
                 for n in sizes]
        with patch.object(fit, 'REPLICATES', 80):
            result = fit.peak_rss_growth(sizes, pairs)
        self.assertEqual(result['mlf_mib_per_unit'], 1.)
        self.assertEqual(result['ghc_mib_per_unit'], 0.)
        for bound in result['delta_mib_per_unit_95']:
            self.assertAlmostEqual(bound, 1.)

    def test_fast_rss_growth_rejects_a_family_with_lower_absolute_peaks(self):
        rows = [row.copy() for row in self.rows if row['family'] in ('baseline', 'chain')]
        samples = []
        for row in rows:
            n = row['size']
            peaks = {'mlf': (8 + n) * 2**20, 'ghc': 64 * 2**20}
            row.update(mlf_peak_rss_bytes=peaks['mlf'], ghc_peak_rss_bytes=peaks['ghc'],
                       mlf_over_ghc_peak_rss=peaks['mlf'] / peaks['ghc'])
            for sample in self.samples:
                if sample['case'] == row['case']:
                    lane = sample['lane']
                    seconds = .2 + n / 64 if lane == 'mlf' else 1 + (n / 32)**2
                    samples.append(dict(sample, wall_seconds=seconds, **{fit.RSS_SAMPLE: peaks[lane]}))
        with patch.object(fit, 'REPLICATES', 20):
            result, = fit.family_reports(rows, samples, 2)
            self.assertTrue(result['checks'][fit.PEAK_RSS_CHECK])
            self.assertTrue(all(result['checks'][k] for k in fit.TIMING_CHECKS))
            self.assertFalse(result['checks'][fit.RSS_SLOPE_CHECK])
            self.assertFalse(result['checks'][fit.RSS_CI_CHECK])
            self.assertEqual(result['status'], 'unmet')
            with patch.dict(samples[0], {fit.RSS_SAMPLE: None}):
                missing, = fit.family_reports(rows, samples, 2)
            self.assertTrue(missing['checks'][fit.PEAK_RSS_CHECK])
            self.assertIsNone(missing['checks'][fit.RSS_CI_CHECK])
            self.assertEqual(missing['status'], 'incomplete')

    def test_pair_bootstrap_preserves_perfectly_correlated_lanes(self):
        sizes = [0, 8, 16, 32]
        times = [[(1 + n * factor, 2 + n * factor) for factor in (1., 2., 3.)] for n in sizes]
        with patch.object(fit, 'REPLICATES', 32):
            result = fit.growth(sizes, times)
        self.assertEqual(result['paired_bootstrap']['ols_delta_ms_95'], [0., 0.])
        self.assertFalse(result['checks']['lower_ols_95'])
        self.assertFalse(result['accepted'])


class MatrixGrowthTests(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.matrix = {'sizes': [8, 32, 128, 1024, 8192], 'families': ['example'], 'repeats': 2}
        self.rows = [dict(family='example', size=n, passed='True', completed_pairs=6,
                          successful_mlf=6, successful_ghc=6, skipped_mlf=0, skipped_ghc=0,
                          mlf_seconds=.3 + (n / 8192)**1.2, ghc_seconds=.7 + (n / 8192)**1.4,
                          failed_lane='', reason='', compiler_revision='a'*40,
                          compiler_sha256='b'*64, producer_receipt_sha256='c'*64)
                     for n in self.matrix['sizes']]

    def fit(self):
        path = self.root / 'table.csv'
        with path.open('w', newline='') as stream:
            out = csv.DictWriter(stream, fieldnames=list(self.rows[0]))
            out.writeheader()
            out.writerows(self.rows)
        row, = matrix_growth.points(path, self.matrix)
        return row

    def test_five_positive_sizes_fit_the_offset_and_unrounded_difference(self):
        result = self.fit()
        self.assertEqual('met', result['status'])
        self.assertAlmostEqual(-.2, result['delta_p'], places=5)
        self.rows.append(dict(self.rows[-1], size=4, mlf_seconds=99))
        self.assertEqual(result, self.fit())
        for row in self.rows:
            row['mlf_seconds'] = row['ghc_seconds']
        self.assertEqual(('met', 0), (self.fit()['status'], self.fit()['delta_p']))

    def test_boundary_order_and_zero_amplitude(self):
        for row in self.rows:
            row['mlf_seconds'] = 1 + (row['size'] / 8192)**4
        result = self.fit()
        self.assertEqual('higher', result['status'])
        for row in self.rows:
            row['ghc_seconds'] = row['mlf_seconds']
        self.assertEqual('met', self.fit()['status'])
        for row in self.rows:
            row['mlf_seconds'] = 1 + (row['size'] / 8192)**1.2
        self.assertEqual('met', self.fit()['status'])
        for row in self.rows:
            row['mlf_seconds'] = 1
        result = self.fit()
        self.assertIsNone(result['delta_p'])
        self.assertEqual('mlf zero fitted growth', result['reason'])

    def test_failed_and_missing_pairs_stay_visible(self):
        self.rows.pop(0)
        self.rows[-1].update(passed='False', completed_pairs=0, failed_lane='ghc', reason='wall limit',
                             mlf_seconds='', ghc_seconds='')
        result = self.fit()
        self.assertEqual(('incomplete', '8: unmeasured; 8192: ghc: wall limit'),
                         (result['status'], result['reason']))
        self.assertIsNone(result['mlf_p'])
        self.assertIsNone(result['ghc_p'])

    def test_rejects_mixed_producers_and_incomplete_reported_success(self):
        for col, val in [('compiler_revision', '1'*40), ('compiler_sha256', '2'*64),
                         ('producer_receipt_sha256', '3'*64), ('completed_pairs', 5)]:
            with self.subTest(col=col), patch.dict(self.rows[-1], {col: val}), self.assertRaises(ValueError):
                self.fit()

    def test_sweep_uses_per_cell_compiler_identity_and_checks_recorded_medians(self):
        recorded = self.rows[0]
        row = dict(family='example', size=8, status='passed', completed_pairs=6,
                   mlf_seconds=recorded['mlf_seconds'], ghc_seconds=recorded['ghc_seconds'])
        metrics = [{'family':'example', 'size':8,
                    **{lane+'_wall_median': row[lane+'_seconds'] for lane in fit.LANES}}]
        plan = {'source': {'commit': 'd'*40}, 'benchmark': {'repeats': 6},
                'cases': [{'family': 'example', 'size': 8}],
                'toolchain': {'producer': {'emlf_sha256':'b'*64, 'receipt_sha256':'c'*64}}}
        receipt = {'runs': [dict(position=p, lane=fit.LANES[p%2], complete=True, output_correct=True)
                            for p in range(12)]}
        with patch.object(matrix_growth.analyze, 'analyze', return_value=(metrics, plan, receipt, [])), \
             patch.object(matrix_growth.analyze, 'compatibility',
                          side_effect=lambda p: {'repeats': p['benchmark']['repeats']}):
            profiles = {}
            ident, _, _ = matrix_growth.sweep_cell(self.root, row, profiles)
            self.assertEqual(('', 'b'*64, 'c'*64), ident)
            with patch.dict(row, {'mlf_seconds': 42}), self.assertRaisesRegex(ValueError, 'median mismatch'):
                matrix_growth.sweep_cell(self.root, row, profiles)
            with patch.dict(plan['benchmark'], repeats=2), patch.dict(row, completed_pairs=2), \
                 patch.dict(receipt, runs=receipt['runs'][:4]):
                self.assertEqual(ident, matrix_growth.sweep_cell(self.root, row, {})[0])
                with self.assertRaisesRegex(ValueError, 'incompatible measurements'):
                    matrix_growth.sweep_cell(self.root, row, profiles)


    def test_sweep_failure_checks_the_plan_digest_before_reporting_its_producer(self):
        row = dict(family='example', size=8192, status='failed', lane='', completed_pairs=0,
                   reason='recorder exit 1; incomplete recording', evidence='cohorts/example-8192')
        ident, values, issue = matrix_growth.sweep_cell(self.root, row, {})
        self.assertEqual((None, None, 'failed: incomplete recording'), (ident, values, issue))
        folder = self.root / row['evidence']
        folder.mkdir(parents=True)
        row.update(lane='ghc', reason='RSS limit', evidence=row['evidence']+'/receipt.json')
        plan = {'cases': [{'family': 'example', 'size': 8192}], 'benchmark': {'repeats': 6},
                'toolchain': {'producer': {'emlf_sha256':'b'*64, 'receipt_sha256':'c'*64}}}
        plan_path = folder / 'plan.json'
        plan_path.write_text(json.dumps(plan))
        receipt = folder / 'receipt.json'
        receipt.write_text(json.dumps({'plan_sha256': '0'*64}))
        with self.assertRaisesRegex(ValueError, 'frozen plan digest'):
            matrix_growth.sweep_cell(self.root, row, {})
        failed = dict(plan_sha256=matrix_growth.analyze.sha(plan_path), complete=True, all_cases_passed=False,
                      runs=[], failures=[dict(case='example-8192', position=0, lane='ghc', error='worker error')])
        receipt.write_text(json.dumps(failed))
        command = folder / 'legs/000-example-8192-ghc/command'
        command.mkdir(parents=True)
        (command/'command.json').write_text(json.dumps({'reason': 'RSS limit'}))
        with patch.object(matrix_growth.analyze, 'compatibility', return_value={}):
            ident, values, issue = matrix_growth.sweep_cell(self.root, row, {})
            self.assertEqual('failed: ghc: RSS limit', issue)
            for field, wrong in [('lane', 'mlf'), ('reason', 'worker error'), ('completed_pairs', 3)]:
                with self.subTest(field=field), patch.dict(row, {field: wrong}), self.assertRaises(ValueError):
                    matrix_growth.sweep_cell(self.root, row, {})
            with patch.dict(row, {'reason': 'recorder exit 1; RSS limit'}):
                self.assertEqual(issue, matrix_growth.sweep_cell(self.root, row, {})[2])
        receipt.write_text(json.dumps(dict(failed, all_cases_passed=True, failures=[])))
        with self.assertRaisesRegex(ValueError, 'failed qualified cell'):
            matrix_growth.sweep_cell(self.root, row, {})
        self.assertEqual(('', 'b'*64, 'c'*64), ident)
        self.assertIsNone(values)


if __name__ == '__main__':
    unittest.main()
