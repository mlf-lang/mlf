import unittest
from admission_model import Entry, Decl, Program, Outcome, run, finite_programs


def let(name, closure):
    return Decl("let", (Entry(name, closure),))


class AdmissionTests(unittest.TestCase):
    def assert_same(self, program):
        old, old_trace = run(program, True)
        new, new_trace = run(program, False)
        self.assertEqual(old, new)
        self.assertEqual(new_trace, [e for e in old_trace if e[0] != "repeated-closure"])
        return new, old_trace, new_trace

    def test_finite_protocols_preserve_results_and_nonrepeat_trace(self):
        count = 0
        for program in finite_programs():
            self.assert_same(program)
            count += 1
        self.assertEqual(count, 6342)

    def test_body_type_error_precedes_delayed_outer_open_guard(self):
        result, trace, _ = self.assert_same(Program((let("outer", "open"),),
                                                  terminal_inference_error="body type error"))
        self.assertEqual(result, Outcome("left", "body type error"))
        self.assertFalse(any(e[0].endswith("closure") for e in trace))

    def test_outer_open_guard_precedes_terminal_shape_error(self):
        result, _, _ = self.assert_same(Program((let("outer", "open"),), "other-valid-term"))
        self.assertEqual(result, Outcome("left", "inference binding has an open type"))

    def test_outer_open_guard_precedes_inner_modeled_bottom(self):
        result, trace, _ = self.assert_same(Program((let("outer", "open"), let("inner", "bottom"))))
        self.assertEqual(result, Outcome("left", "inference binding has an open type"))
        self.assertNotIn(("first-closure", "inner"), trace)

    def test_first_guard_still_forces_modeled_bottom(self):
        result, trace, _ = self.assert_same(Program((let("x", "bottom"),)))
        self.assertEqual(result, Outcome("modeled-bottom", "x"))
        self.assertEqual(sum(e[0] == "first-closure" for e in trace), 1)

    def test_recursive_group_order_is_preserved(self):
        ds = (Decl("rec", (Entry("a", "closed"), Entry("b", "open"), Entry("c", "bottom"))),)
        result, trace, _ = self.assert_same(Program(ds))
        self.assertEqual(result.status, "left")
        self.assertEqual([e[1] for e in trace if e[0] == "first-closure"], ["a", "b"])

    def test_closed_export_order_and_calls(self):
        for n in (0, 1, 8, 64):
            ds = tuple(let(str(i), "closed") for i in range(n))
            result, old_trace, new_trace = self.assert_same(Program(ds))
            self.assertEqual(tuple(e.name for e in result.exports), tuple(str(i) for i in range(n)))
            self.assertEqual(sum(e[0].endswith("closure") for e in old_trace), 2 * n)
            self.assertEqual(sum(e[0].endswith("closure") for e in new_trace), n)

    def test_ignored_partial_metadata_is_not_forced(self):
        class Poison:
            def __bool__(self):
                raise AssertionError("irrelevant metadata forced")
            def __repr__(self):
                raise AssertionError("irrelevant metadata printed")
        entry = Entry("unused-outer-id", "closed", Poison())
        result, _, _ = self.assert_same(Program((Decl("let", (entry,)),)))
        self.assertEqual(result.status, "right")

    def test_mutation_skipping_first_guard_breaks_equivalence(self):
        program = Program((let("unsafe", "open"),))
        old, _ = run(program, True, skip_first_guards=True)
        new, _ = run(program, False, skip_first_guards=True)
        self.assertEqual(old, Outcome("left", "open fragment exports an open type"))
        self.assertEqual(new.status, "right")
        self.assertNotEqual(old, new)

    def test_mutation_forging_inventory_breaks_equivalence(self):
        forged = (Entry("unsafe-new-export", "open"),)
        old, _ = run(Program(), True, forged_exports=forged)
        new, _ = run(Program(), False, forged_exports=forged)
        self.assertEqual(old.status, "left")
        self.assertEqual(new.status, "right")


if __name__ == "__main__":
    unittest.main(verbosity=2)
