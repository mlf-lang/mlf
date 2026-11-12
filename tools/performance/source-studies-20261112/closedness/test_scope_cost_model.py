import itertools
import unittest
from closedness_model import Ty, free_vars, bounded_types
from scope_cost_model import (Scope, insert, member, size, closed_with_recipe,
                              family, measure)


def verify_tree(tree, lower=None, upper=None):
    if tree is None:
        return []
    if lower is not None:
        assert lower < tree.key
    if upper is not None:
        assert tree.key < upper
    left = verify_tree(tree.left, lower, tree.key)
    right = verify_tree(tree.right, tree.key, upper)
    assert tree.size == len(left) + len(right) + 1
    if len(left) + len(right) > 1:
        assert len(left) <= 3 * len(right)
        assert len(right) <= 3 * len(left)
    return left + [tree.key] + right


class ScopeCostTests(unittest.TestCase):
    def test_insert_invariants_all_six_key_orders(self):
        # 720 finite orders, every prefix; not a proof of Bootstrap.Map.
        for order in itertools.permutations(range(6)):
            tree, expected, counts = None, set(), {}
            for key in order:
                tree = insert(key, tree, counts)
                expected.add(key)
                self.assertEqual(verify_tree(tree), sorted(expected))
                for probe in range(-1, 7):
                    self.assertEqual(member(probe, tree, {}), probe in expected)

    def test_duplicate_and_signed_keys(self):
        tree, counts = None, {}
        for key in (0, -2**60, 2**60, 0, -2**60):
            tree = insert(key, tree, counts)
        self.assertEqual(verify_tree(tree), [-2**60, 0, 2**60])

    def test_small_grammar_agrees_with_independent_fv(self):
        for ty in bounded_types():
            self.assertEqual(closed_with_recipe(Scope(), ty, {}), not free_vars(ty))

    def test_unused_binders_do_not_materialize_scope(self):
        for d in (1, 8, 64):
            result = measure(d, "unused")["set_recipe_events"]
            self.assertEqual(result["scope-extension-expression"], d)
            self.assertNotIn("scope-materialized-insert", result)
            self.assertNotIn("tree-node-equation", result)

    def test_one_innermost_use_materializes_all_ancestors(self):
        for d in (1, 8, 64):
            result = measure(d, "innermost-once")["set_recipe_events"]
            self.assertEqual(result["scope-materialized-insert"], d)
            self.assertGreaterEqual(result.get("insert-key-compare", 0), d - 1)

    def test_scope_force_memoizes_shared_recipe(self):
        counts, scope = {}, Scope()
        for key in range(16):
            scope = scope.extend(key, counts)
        tree = scope.force(counts)
        before = counts.copy()
        self.assertIs(scope.force(counts), tree)
        self.assertEqual(counts, before)
        self.assertEqual(size(tree), 16)

    def test_outer_repeated_list_requires_depth_squared_comparisons(self):
        for d in (1, 2, 8, 32, 64):
            result = measure(d, "outer-repeated")
            self.assertEqual(result["list_events"]["list-key-compare"], d * d)
            self.assertEqual(result["set_recipe_events"]["scope-materialized-insert"], d)
            self.assertEqual(result["reference_symbolic_events"]["singleton"], d)

    def test_open_bound_does_not_extend_scope(self):
        counts = {}
        ty = Ty("forall", 0, (Ty("var", 0), Ty("bot")))
        self.assertFalse(closed_with_recipe(Scope(), ty, counts))
        self.assertNotIn("scope-extension-expression", counts)

    def test_invalid_family_inputs(self):
        with self.assertRaises(ValueError):
            family(0, "unused")
        with self.assertRaises(ValueError):
            family(1, "unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
