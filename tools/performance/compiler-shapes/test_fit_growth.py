"""Regression checks for selecting and pairing finite-range scaling observations."""
import unittest
from unittest.mock import patch

import numpy as np

import fit_growth as fit


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


if __name__ == '__main__':
    unittest.main()
