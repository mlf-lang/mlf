import itertools
import unittest
from closedness_model import Ty, free_vars, closed_in, bounded_types, balanced_repeated_variable


BOT = Ty("bot")
V0 = Ty("var", 0)
V1 = Ty("var", 1)
def forall(name, bound, body):
    return Ty("forall", name, (bound, body))
def arrow(a, b):
    return Ty("arrow", None, (a, b))


class ClosednessTests(unittest.TestCase):
    def test_exhaustive_small_grammar_and_scopes(self):
        types = bounded_types()
        self.assertEqual(len(types), 888)
        scopes = [frozenset(x for x, keep in zip((-1, 0, 1), flags) if keep)
                  for flags in itertools.product((False, True), repeat=3)]
        comparisons = 0
        for ty, scope in itertools.product(types, scopes):
            self.assertEqual(closed_in(scope, ty), free_vars(ty).issubset(scope))
            comparisons += 1
        self.assertEqual(comparisons, 7104)

    def test_forall_bound_does_not_bind_itself(self):
        value = forall(0, V0, V0)
        self.assertFalse(closed_in(frozenset(), value))
        self.assertEqual(free_vars(value), {0})

    def test_forall_bound_can_reference_outer_same_id(self):
        value = forall(0, BOT, forall(0, V0, V0))
        self.assertTrue(closed_in(frozenset(), value))
        self.assertFalse(free_vars(value))

    def test_shadowing_does_not_remove_outer_scope(self):
        value = forall(0, BOT, arrow(forall(0, BOT, V0), V0))
        self.assertTrue(closed_in(frozenset(), value))

    def test_sibling_scope_does_not_leak(self):
        value = arrow(forall(0, BOT, V0), V0)
        self.assertFalse(closed_in(frozenset(), value))

    def test_all_constructor_arguments_are_considered(self):
        value = Ty("con", "Opaque", (forall(0, BOT, V0), V1))
        self.assertFalse(closed_in(frozenset(), value))
        self.assertTrue(closed_in(frozenset({1}), value))

    def test_bottom_kind_is_closed_not_necessarily_star(self):
        value = Ty("bot-kind", "(* -> *) -> *")
        self.assertTrue(closed_in(frozenset(), value))
        # This is no claim that Check.termType accepts the non-Star kind.

    def test_large_negative_and_positive_ids_preserved(self):
        for name in (-2**62, 0, 2**62):
            value = forall(name, BOT, Ty("var", name))
            self.assertTrue(closed_in(frozenset(), value))

    def test_closed_predicate_is_not_type_validity(self):
        ill_kinded_but_closed = Ty("apply", None, (BOT, BOT))
        self.assertTrue(closed_in(frozenset(), ill_kinded_but_closed))
        self.assertFalse(free_vars(ill_kinded_but_closed))

    def test_alpha_renaming_keeps_closedness(self):
        for name in (-1, 0, 1, 1000000):
            self.assertTrue(closed_in(frozenset(), forall(name, BOT, arrow(Ty("var", name), Ty("var", name)))))

    def test_counter_model_avoids_free_variable_result_sets(self):
        value = forall(0, BOT, balanced_repeated_variable(7))
        old, new = {}, {}
        self.assertFalse(free_vars(value, old))
        self.assertTrue(closed_in(frozenset(), value, new))
        self.assertEqual(old["singleton"], 128)
        self.assertEqual(old["union"], 128)
        self.assertEqual(old["delete"], 1)
        self.assertEqual(new["scope-insert"], 1)
        self.assertEqual(new["member"], 128)
        self.assertNotIn("singleton", new)
        self.assertEqual(old["node"], new["node"])

    def test_short_circuit_is_not_a_bottom_equivalence_proof(self):
        class Poison:
            @property
            def tag(self):
                raise RuntimeError("modeled bottom")
        value = arrow(V0, Poison())
        self.assertFalse(closed_in(frozenset(), value))
        with self.assertRaises(RuntimeError):
            free_vars(value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
