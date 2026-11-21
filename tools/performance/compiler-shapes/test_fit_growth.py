"""Regression checks for selecting and pairing finite-range scaling observations."""
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

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
        np.testing.assert_array_equal(sizes, [0, 8, 16, 32])
        np.testing.assert_array_equal(times[:, 0, 0], sizes)
        np.testing.assert_array_equal(times[:, 1, 1], sizes + 3)
        np.testing.assert_array_equal(times[:, :, 1], times[:, :, 0] + 1)

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
        sizes = np.array([0, 32, 128, 256, 1024])
        small = .3 + .12 * (sizes / 1024) ** 1.1
        large = .6 + .3 * (sizes / 1024) ** 1.4
        times = np.repeat(np.column_stack((small, large))[:, None, :], 3, axis=1)
        with patch.object(fit, 'REPLICATES', 12):
            result = fit.growth(sizes, times)
        self.assertTrue(result['accepted'])
        self.assertAlmostEqual(result['estimates']['mlf']['power']['p'], 1.1, places=5)
        self.assertAlmostEqual(result['estimates']['ghc']['power']['offset_seconds'], .6, places=6)
        np.testing.assert_allclose(result['paired_bootstrap']['p_delta_95'], [-.3, -.3], atol=1e-5)
        self.assertFalse(fit.power_fit(sizes, 1 + (sizes / 1024) ** 4)['interior'])


class MatrixGrowthTests(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.matrix = {'sizes': [8, 32, 128, 1024, 8192], 'families': ['example'], 'repeats': 6}
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

    def test_bounds_and_zero_amplitude_are_indeterminate(self):
        for row in self.rows:
            row['mlf_seconds'] = 1 + (row['size'] / 8192)**4
        result = self.fit()
        self.assertEqual(('indeterminate', 'mlf boundary fit'), (result['status'], result['reason']))
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
             patch.object(matrix_growth.analyze, 'compatibility', return_value={'ghc_version': '9.14.1'}):
            profiles = {}
            ident, _, _ = matrix_growth.sweep_cell(self.root, row, 6, profiles)
            self.assertEqual(('', 'b'*64, 'c'*64), ident)
            with self.assertRaisesRegex(ValueError, 'incompatible measurements'):
                matrix_growth.sweep_cell(self.root, row, 6, {'example': {'ghc_version':'older'}})
            with patch.dict(row, {'mlf_seconds': 42}), self.assertRaisesRegex(ValueError, 'median mismatch'):
                matrix_growth.sweep_cell(self.root, row, 6, profiles)


    def test_sweep_failure_checks_the_plan_digest_before_reporting_its_producer(self):
        row = dict(family='example', size=8192, status='failed', lane='ghc', reason='RSS limit')
        _, values, reason = matrix_growth.sweep_cell(self.root, row, 6, {})
        self.assertIsNone(values)
        self.assertIn('ghc: RSS limit', reason)
        folder = self.root / 'cohorts/example-8192'
        folder.mkdir(parents=True)
        plan = {'cases': [{'family': 'example', 'size': 8192}], 'benchmark': {'repeats': 6},
                'toolchain': {'producer': {'emlf_sha256':'b'*64, 'receipt_sha256':'c'*64}}}
        plan_path = folder / 'plan.json'
        plan_path.write_text(json.dumps(plan))
        receipt = folder / 'receipt.json'
        receipt.write_text(json.dumps({'plan_sha256': '0'*64}))
        with self.assertRaisesRegex(ValueError, 'frozen plan digest'):
            matrix_growth.sweep_cell(self.root, row, 6, {})
        receipt.write_text(json.dumps({'plan_sha256': matrix_growth.analyze.sha(plan_path)}))
        with patch.object(matrix_growth.analyze, 'compatibility', return_value={}):
            ident, values, _ = matrix_growth.sweep_cell(self.root, row, 6, {})
        self.assertEqual(('', 'b'*64, 'c'*64), ident)
        self.assertIsNone(values)


if __name__ == '__main__':
    unittest.main()
