#!/usr/bin/env python3
"""Cheap policy/structure controls; never execute a compiler or a full test suite."""
import ast
from pathlib import Path
import unittest

DRIVER = Path(__file__).with_name('test_framework_direct.py')
TREE = ast.parse(DRIVER.read_text())
POLICY = next(n for n in TREE.body if isinstance(n, ast.FunctionDef)
              and n.name == 'suite_timeout')
NAMESPACE = {}
exec(compile(ast.Module(body=[POLICY], type_ignores=[]), str(DRIVER), 'exec'), NAMESPACE)
resolve = NAMESPACE['suite_timeout']


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

    def test_full_suites_each_execute_once_with_policy_budget(self):
        calls = [n for n in ast.walk(TREE) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == 'run'
                 and n.args and isinstance(n.args[0], ast.Constant)]
        for label in ['default', 'framework']:
            matches = [n for n in calls if n.args[0].value == label]
            self.assertEqual(len(matches), 1, label)
            timeout = next(k.value for k in matches[0].keywords if k.arg == 'timeout')
            self.assertIsInstance(timeout, ast.Name)
            self.assertEqual(timeout.id, 'budget')

    def test_budget_selected_only_after_producer_authentication(self):
        main = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        calls = [n for n in ast.walk(main) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name)]
        auth = min(n.lineno for n in calls if n.func.id == 'authenticate_build')
        policy = [n for n in calls if n.func.id == 'suite_timeout']
        self.assertEqual(len(policy), 1)
        self.assertLess(auth, policy[0].lineno)
        self.assertEqual(ast.unparse(policy[0].args[0]), "producer['optimization']")

    def test_receipt_records_selected_and_requested_budget(self):
        keys = {kw.arg for n in ast.walk(TREE) if isinstance(n, ast.Call)
                for kw in n.keywords}
        self.assertTrue({'suite_timeout_seconds', 'suite_timeout_request',
                         'suite_timeout_policy'}.issubset(keys))

    def test_other_commands_keep_existing_default_budget(self):
        run = next(n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name == 'run')
        self.assertEqual(ast.literal_eval(run.args.defaults[-1]), 120)


if __name__ == '__main__':
    unittest.main()
