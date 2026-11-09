"""Wire fixtures constructed from the specification, independently of the compiler."""
import unittest

from artifact_binary_reference import Invalid, tree_document
from artifact_binary_typed import l, n, pack, s
from query_generation import Generation, V1, V2


def i(slot):
    return ("int", slot)


def fixture(names):
    d, e = map(names.index, ("A.f", "B.f"))
    group = pack(["A.f", "B.f"])
    target, infer, finish = (pack(["Binding", "A.f"]), pack(["InferScc", group]), pack(["FinishScc", group]))
    rows = [(target, i(d), "1" * 64, []),
            (infer, n(419, i(0)), "2" * 64, [(target, i(d), "1" * 64)] * 2),
            (finish, n(431, i(0)), "3" * 64, [(infer, n(419, i(0)), "2" * 64)])]
    requests = [(0, "Eq Int"), (1, "Eq Int"), (0, "Eq Bool")]
    for slot, (site, goal) in enumerate(requests):
        key = pack(["Evidence", pack([group, str(site), goal])])
        rows.append((key, n(432, i(slot)), str(slot + 4) * 64, []))
    for key, desc in [(pack(["Input", target]), n(415, i(d))),
                      (pack(["Datatype", "A.f"]), n(433, i(0))),
                      (pack(["Input", pack(["Datatype", "A.f"])]), n(434, i(0))),
                      (pack(["Scope", group]), n(418, i(0))),
                      (pack(["Input", pack(["Prepared", group])]), n(416, i(0))),
                      (pack(["Input", pack(["ScopeInventory", group])]), n(417, i(0)))]:
        rows.append((key, desc, "e" * 64, []))
    rows.sort()
    fields = [s(V2), s("cfg"), l(*map(s, names)), l(l(i(d), i(e))),
              l(*(n(414, i(0), i(site), s(goal)) for site, goal in requests)),
              l(s("A.f")), l(*(n(413, desc, s(h), l(*(ref for _, ref, _ in reads)), n(5, s(h)))
                                for key, desc, h, reads in rows))]
    v1 = n(411, s(V1), s("cfg"), l(*(n(410, s(key), s(h),
           l(*(n(2, s(child), s(version)) for child, _, version in reads)), n(5, s(h)))
           for key, _, h, reads in rows)))
    return fields, tree_document([v1], 6)


class GenerationTests(unittest.TestCase):
    def test_reordered_slots_and_complete_v1_bytes(self):
        slots = ["unused" + str(x) for x in range(13)]
        slots[7], slots[12] = "A.f", "B.f"
        graphs = []
        for names in [slots, slots[:7] + ["new1", "new2"] + slots[7:]]:
            fields, legacy = fixture(names)
            raw = tree_document([n(412, *fields)], 6)
            graph = Generation(raw, configuration="cfg")
            self.assertEqual(graph.encode_rows(graph.rows), raw)
            self.assertEqual(graph.legacy_bytes(), legacy)
            self.assertEqual(Generation(legacy).nodes, graph.nodes)
            graphs.append(graph.nodes)
        self.assertEqual(*graphs)

    def test_main_dictionary_shape_compatibility(self):
        # Authored four-field dictionary fixture, distinct from typed snapshots.
        raw = tree_document([n(412, s(V2), s("cfg"), l(s("1" * 64), s("leaf")),
                               l(n(413, i(1), i(0), l(), n(4))))], 6)
        graph = Generation(raw, configuration="cfg")
        self.assertTrue(graph.dictionary_format)
        self.assertEqual(graph.nodes, {"leaf": dict(sha="1" * 64, reads=[], payload=None)})
        self.assertEqual(graph.encode_rows(graph.rows), raw)
        self.assertEqual(Generation(graph.legacy_bytes()).nodes, graph.nodes)
        unused = tree_document([n(412, s(V2), s("cfg"), l(s("1" * 64), s("leaf"), s("unused")),
                                  l(n(413, i(1), i(0), l(), n(4))))], 6)
        with self.assertRaises(Invalid):
            Generation(unused, configuration="cfg")

    def test_malformed_tables_and_edges(self):
        def corrupted(field, value):
            fields, _ = fixture(["A.f", "B.f"])
            fields[field] = value
            return tree_document([n(412, *fields)], 6)
        def row(k, edges):
            return n(413, k, s("1" * 64), l(*edges), n(4))
        tests = [(0, s(V1)), (2, l(s("A.f"), s("A.f"))), (3, l(l())),
                 (3, l(l(i(0), i(0)))), (3, l(l(i(-1)))), (3, l(l(i(2)))),
                 (4, l(n(414, i(1), i(0), s("Eq Int")))),
                 (4, l(n(414, i(0), i(-1), s("Eq Int")))),
                 (4, l(n(414, i(0), i(0), s("")))), (5, l(s(""), s("A"))),
                 (6, l(row(n(426, i(0)), []))), (6, l(row(i(0), [i(1)]))),
                 (6, l(row(i(0), [i(0)]))), (6, l(row(i(0), []), row(i(0), [])))]
        for field, value in tests:
            with self.subTest(field=field, value=value), self.assertRaises(Invalid):
                Generation(corrupted(field, value))

    def test_depth_independent_of_row_order(self):
        graph = Generation.__new__(Generation)
        graph.nodes = {str(i): {"reads": [(str(i-1), "h")] if i else []} for i in range(4097)}
        with self.assertRaisesRegex(Invalid, "deep"):
            graph.check_cycles()
        del graph.nodes["4096"]
        graph.check_cycles()

    def test_checksum_configuration_and_payload(self):
        fields, _ = fixture(["A.f", "B.f"])
        raw = tree_document([n(412, *fields)], 6)
        with self.assertRaises(Invalid):
            Generation(raw, expected_hash="0" * 64)
        with self.assertRaises(Invalid):
            Generation(raw, configuration="other")
        fields[-1] = l(n(413, i(0), s("1" * 64), l(), n(5, s("2" * 64))))
        with self.assertRaises(Invalid):
            Generation(tree_document([n(412, *fields)], 6))


if __name__ == "__main__":
    unittest.main()
