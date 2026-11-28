#!/usr/bin/env python3
"""Pure budget boundary checks; main-entrypoint contracts live in controls.

Import the production policy normally so extracting a helper, renaming a local,
or changing how main delegates does not require rewriting these tests.
"""
import unittest
from test_framework_direct import suite_timeout as resolve


class FrameworkBudgetPolicy(unittest.TestCase):
    def test_authenticated_defaults(self):
        self.assertEqual(resolve('0', None), 4500)
        self.assertEqual(resolve('2', None), 600)

    def test_explicit_bounded_overrides(self):
        for optimization, values in [('0', [1, 600, 900, 5400]), ('2', [1, 600, 900])]:
            for value in values:
                with self.subTest(optimization=optimization, value=value):
                    self.assertEqual(resolve(optimization, value), value)

    def test_invalid_budgets_fail_closed(self):
        for optimization, values in [('0', [0, -1, 5401, True, 1.5, '5400']),
                                      ('2', [0, -1, 901, 5400, True, 1.5, '600'])]:
            for value in values:
                with self.subTest(optimization=optimization, value=value):
                    with self.assertRaises(ValueError):
                        resolve(optimization, value)

    def test_unknown_optimization_fails_closed(self):
        for optimization in ['1', '3', '', 'O0', 0, 2, False, None, {}, {'optimization': '0'}]:
            with self.subTest(optimization=optimization):
                with self.assertRaises(ValueError):
                    resolve(optimization, None)

if __name__ == '__main__':
    unittest.main()
