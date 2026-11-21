"""Check the generated polymorphic types, use sites and independent native oracles."""
import re
import unittest

import generate
import rank_shapes


class RankShapeTests(unittest.TestCase):
    def test_nested_boxes_reach_the_full_depth_before_any_unboxing(self):
        flat = generate.program('poly_calls', 1)
        for n in (1, 4, 16, 128, 8192):
            with self.subTest(size=n):
                decls, expr = rank_shapes.program_body('nested_poly_types', n, generate.balanced)
                self.assertTrue(flat.startswith(generate.HEADER + decls + 'entry ::'))
                # Read the unary applications in evaluation-dependency order.
                opens, closes = expr.rsplit('x', 1)
                self.assertEqual(opens.replace('(', ' ').split()[::-1], ['hold'] * n + ['unbox'] * n)
                self.assertEqual(closes, ')' * (2 * n))
                for x in (-2**63, -1, 0, 7, 2**63 - 1):
                    self.assertEqual(rank_shapes.expected('nested_poly_types', n, x), x)

    def test_every_callback_consumer_checks_two_types_and_is_called(self):
        for n in (1, 4, 16, 128, 8192):
            with self.subTest(size=n):
                decls, expr = rank_shapes.program_body('rank2_callbacks', n, generate.balanced)
                signatures = re.findall(r'^consume(\d+) :: \(forall a\. a -> a\) -> Int -> Int;$',
                                        decls, re.MULTILINE)
                bodies = re.findall(
                    r'^consume(\d+) callback x = let \{ value = callback \(addInt x (\d+)\) \} in '
                    r'if callback \(ltInt x (\d+)\) then addInt value (\d+) else subInt value (\d+);$',
                    decls, re.MULTILINE)
                self.assertIn('identity :: forall a. a -> a;\nidentity value = value;', decls)
                self.assertEqual([int(i) for i in signatures], list(range(n)))
                self.assertEqual([tuple(map(int, row)) for row in bodies],
                                 [(i, i, i, i + 1, i + 1) for i in range(n)])
                calls = re.findall(r'\bconsume(\d+) identity x\b', expr)
                self.assertEqual([int(i) for i in calls], list(range(n)))
                self.assertEqual(expr.count('addInt '), n - 1)

    def test_callback_oracle_across_thresholds_and_machine_int_boundaries(self):
        family = 'rank2_callbacks'
        self.assertEqual([rank_shapes.expected(family, 3, x) for x in (-1, 0, 1, 2, 7)],
                         [6, 7, 6, 3, 18])
        for n in (1, 2, 5, 32, 8192):
            for x in (-2**63, -1, 0, n // 2, n - 1, n, 2**63 - 1):
                with self.subTest(size=n, value=x):
                    value = sum((x + i) + (i + 1 if x < i else -(i + 1)) for i in range(n))
                    bits = value & ((1 << 64) - 1)
                    signed = bits if bits < 1 << 63 else bits - (1 << 64)
                    self.assertEqual(rank_shapes.expected(family, n, x), signed)


if __name__ == '__main__':
    unittest.main()
