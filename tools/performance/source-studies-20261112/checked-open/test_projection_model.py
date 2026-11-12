"""Run only this pure, tiny Python model. Does not import or execute Haskell."""
import unittest
from projection_model import (Binding, Term, UNIT, INTEGER, ModeledReceipt,
    Projection, SHAPE, ORDER, baseline, candidate, project,
    projected_inventory, declaration_inventory, fixture_inputs, result, safe_adapter)


class ProjectionModelTests(unittest.TestCase):
    def test_bounded_structural_differential(self):
        cases = list(fixture_inputs())
        self.assertEqual(len(cases), 810)
        for source, expected in cases:
            with self.subTest(source=source, expected=expected):
                self.assertEqual(result(lambda: baseline(ModeledReceipt(source), expected)),
                                 result(lambda: candidate(ModeledReceipt(source), expected)))
                self.assertEqual(result(lambda: baseline(ModeledReceipt(source), expected)),
                                 result(lambda: safe_adapter(project(ModeledReceipt(source), expected))))

    def test_r2_negative_adapter_blindspot_counterexample(self):
        source = Term("rec", (Binding(0, "a"),), INTEGER)
        expected = (("a", "Int"),)
        projection = project(ModeledReceipt(source), expected)
        # Model a faulty extraction: body changed, checked inventory unchanged.
        mutant = Projection(projection.receipt, projection.context,
                             projection.parameters, UNIT, projection.cut)
        old_assertion = result(lambda: projected_inventory(mutant))
        reference = result(lambda: baseline(ModeledReceipt(source), expected))
        self.assertEqual(old_assertion, reference)  # r2's negative assertion misses it
        self.assertNotEqual(result(lambda: safe_adapter(mutant)), reference)
        # r3 directly compares adapter outcome on negatives, so detects the fault.

    def test_discarded_early_inventory_is_observable(self):
        receipt = ModeledReceipt(INTEGER)
        result(receipt.inventory)  # Discarding a finite Left is invisible to value equality.
        projection = project(receipt, ())
        self.assertEqual(result(lambda: projected_inventory(projection)), ("left", "open", SHAPE))
        self.assertEqual(receipt.inventory_calls, 2)
        # A no-early-demand assertion before admission must inspect calls/poison.

    def test_pending_projection_does_not_demand_inventory(self):
        def poison():
            raise AssertionError("inventory demanded too early")
        for source, expected in [(INTEGER, ()),
                                 (Term("lambda", (Binding(8, "p"),), UNIT), ()),
                                 (Term("rec", (Binding(0, "a"),), INTEGER), (("a", "Int"),))]:
            receipt = ModeledReceipt(source, poison)
            projection = project(receipt, expected)
            self.assertIsNotNone(projection.body)
            self.assertEqual(receipt.inventory_calls, 0)

    def test_wrapper_errors_precede_inventory_even_when_tail_invalid(self):
        source = Term("rec", (Binding(0, "b"), Binding(1, "a")), INTEGER)
        receipt = ModeledReceipt(source, lambda: (_ for _ in ()).throw(AssertionError("early demand")))
        self.assertEqual(result(lambda: candidate(receipt, (("a", "Int"), ("b", "Int")))),
                         ("left", "wrapper", ORDER))
        self.assertEqual(receipt.inventory_calls, 0)

    def test_reject_leading_lambda_without_demanding_raw_receipt(self):
        receipt = ModeledReceipt(Term("lambda", (Binding(5, "a"),), UNIT))
        self.assertEqual(receipt.inventory(), ())
        receipt.inventory_calls = 0
        self.assertEqual(result(lambda: candidate(receipt, ())), ("left", "open", SHAPE))
        self.assertEqual(receipt.inventory_calls, 0)

    def test_actual_alpha_annotation_is_not_replaced(self):
        actual = Binding(0, "a", "forall-id", "forall x. x -> x")
        source = Term("rec", (actual,), UNIT)
        projection = project(ModeledReceipt(source), (("a", "forall-id"),))
        self.assertEqual(projection.parameters, (actual,))
        self.assertNotEqual(projection.parameters, (Binding(0, "a", "forall-id", "forall y. y -> y"),))

    def test_exact_cut_is_not_name_filter(self):
        imported, owned = Binding(0, "same"), Binding(1, "same")
        source = Term("rec", (imported,), Term("let", (owned,), UNIT))
        self.assertEqual(candidate(ModeledReceipt(source), (("same", "Int"),))[-1], (owned,))

    def test_wrong_receipt_prefix_is_detected(self):
        original = Binding(0, "a")
        other = Binding(1, "a")
        source = Term("rec", (original,), UNIT)
        projection = project(ModeledReceipt(source, lambda: (other,)), (("a", "Int"),))
        self.assertEqual(result(lambda: projected_inventory(projection))[1], "lemma")

    def test_short_prefix_is_not_silently_truncated(self):
        source = Term("rec", (Binding(0, "a"),), UNIT)
        projection = project(ModeledReceipt(source, lambda: ()), (("a", "Int"),))
        self.assertEqual(result(lambda: projected_inventory(projection)),
            ("left", "lemma", "checked inventory is shorter than its exact root prefix"))

    def test_mutant_lambda_peeling_is_killed(self):
        source = Term("lambda", (Binding(0, "a"),), UNIT)
        mutant = result(lambda: ModeledReceipt(source).inventory())
        reference = result(lambda: declaration_inventory(source))
        self.assertNotEqual(mutant, reference)

    def test_mutant_unconditional_rec_cut_is_killed(self):
        owned = Binding(0, "owned")
        source = Term("rec", (owned,), UNIT)
        mutant = declaration_inventory(source.body)
        self.assertNotEqual(mutant, baseline(ModeledReceipt(source), ())[-1])

    def test_mutant_name_filter_is_killed(self):
        imported, owned = Binding(0, "same"), Binding(1, "same")
        source = Term("rec", (imported,), Term("let", (owned,), UNIT))
        whole = ModeledReceipt(source).inventory()
        mutant = tuple(x for x in whole if x.hint != "same")
        self.assertNotEqual(mutant, baseline(ModeledReceipt(source), (("same", "Int"),))[-1])

    def test_mutant_eager_inventory_is_killed(self):
        source = Term("rec", (Binding(0, "b"),), INTEGER)
        def eager_mutant():
            receipt = ModeledReceipt(source)
            receipt.inventory()
            return candidate(receipt, (("a", "Int"),))
        self.assertNotEqual(result(eager_mutant),
                            result(lambda: baseline(ModeledReceipt(source), (("a", "Int"),))))

    def test_mutant_partial_prefix_drop_is_killed(self):
        # Ordinary drop tolerates an impossible short receipt; a total cut must reject.
        source = Term("rec", (Binding(0, "a"),), UNIT)
        projection = project(ModeledReceipt(source, lambda: ()), (("a", "Int"),))
        self.assertNotEqual(("right", ()[1:]), result(lambda: projected_inventory(projection)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
