"""Independently authored column and constant-scope wire controls."""
import unittest

from artifact_binary_reference import Invalid, tree_document
from artifact_binary_typed import l, list_values, n, pack, s
from query_generation import Generation, V3
from test_query_generation import fixture, i


def document(fields):
    return tree_document([n(412, *fields)], 6)


class Columns(unittest.TestCase):
    def test_independent_exact_roundtrip(self):
        fields, expected = fixture(['A.f', 'B.f'])
        raw = document(fields)
        graph = Generation(raw, configuration='cfg')
        self.assertEqual(graph.nodes, expected)
        self.assertEqual(graph.encode_rows(graph.rows), raw)
        self.assertTrue(any(len(row['reads']) == 2 and row['reads'][0] == row['reads'][1]
                            for row in graph.nodes.values()))

    def test_empty(self):
        fields = [s(V3), s('cfg'), *(l() for _ in range(9))]
        graph = Generation(document(fields))
        self.assertEqual(graph.nodes, {})
        self.assertEqual(graph.encode_rows(graph.rows), document(fields))

    def test_column_lengths_counts_and_payload_rows(self):
        fields, _ = fixture(['A.f', 'B.f'])
        count = len(list_values(fields[6]))
        cases = [
            (0, s('obsolete')), (1, s('')), (6, l()), (7, l()), (8, l()),
            (8, l(i(-1), *[i(0)] * (count - 1))),
            (8, l(i(9223372036854775807), *[i(0)] * (count - 1))),
            (8, l(*[i(0)] * count)), (9, l()), (9, l(*list_values(fields[9]), i(0))),
            (10, l(i(0), i(0))), (10, l(i(1), i(0))), (10, l(i(-1))), (10, l(i(count))),
            (10, l(s('0'))),
        ]
        for field, value in cases:
            changed = list(fields)
            changed[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(Invalid):
                Generation(document(changed))

    def test_descriptor_hash_and_cycle_controls(self):
        fields, _ = fixture(['A.f', 'B.f'])
        for field, first in [(6, n(999, i(0))), (7, s('z' * 64))]:
            changed = list(fields)
            changed[field] = l(first, *list_values(fields[field])[1:])
            with self.subTest(field=field), self.assertRaises(Invalid):
                Generation(document(changed))
        single = [s(V3), s('cfg'), l(s('A.f')), l(), l(), l(), l(i(0)),
                  l(s('1' * 64)), l(i(1)), l(i(0)), l()]
        with self.assertRaisesRegex(Invalid, 'cyclic query graph'):
            Generation(document(single))


class ConstantScopes(unittest.TestCase):
    def test_distinct_constant_identities_and_edges(self):
        fields = [s(V3), s('cfg'), *(l() for _ in range(4)),
                  l(n(435), n(436)), l(s('1' * 64), s('2' * 64)), l(i(0), i(1)), l(n(435)), l()]
        raw = document(fields)
        graph = Generation(raw)
        inventory = pack(['Input', pack(['EmptyScopeInventory', ''])])
        scope = pack(['EmptyScope', ''])
        self.assertEqual(graph.nodes, {
            inventory: dict(sha='1' * 64, reads=[], payload=None),
            scope: dict(sha='2' * 64, reads=[(inventory, '1' * 64)], payload=None),
        })
        self.assertEqual(graph.encode_rows(graph.rows), raw)
        for key in [n(435, i(0)), n(436, i(0)), n(437), n(435, n(1))]:
            changed = list(fields)
            changed[6] = l(key, n(436))
            with self.subTest(key=key), self.assertRaises(Invalid):
                Generation(document(changed))


if __name__ == '__main__':
    unittest.main()
