"""Wire fixtures constructed from the specification, independently of the compiler."""
import tempfile
import unittest
from pathlib import Path

from artifact_binary_reference import Invalid, tree_document
from artifact_binary_typed import l, n, pack, s
from query_generation import CACHE_DIRECTORY, Generation, V3, cache_directory


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
    fields = [s(V3), s("cfg"), l(*map(s, names)), l(l(i(d), i(e))),
              l(*(n(414, i(0), i(site), s(goal)) for site, goal in requests)),
              l(s("A.f")), l(*(desc for _, desc, _, _ in rows)), l(*(s(h) for _, _, h, _ in rows)),
              l(*(i(len(edges)) for _, _, _, edges in rows)),
              l(*(ref for _, _, _, edges in rows for _, ref, _ in edges)),
              l(*(i(ordinal) for ordinal in range(len(rows))))]
    expected = {key: dict(sha=h, reads=[(name, sha) for name, _, sha in edges], payload=h)
                for key, _, h, edges in rows}
    return fields, expected


class GenerationTests(unittest.TestCase):
    def test_generations_resolve_their_own_slots(self):
        slots = ["unused" + str(x) for x in range(13)]
        slots[7], slots[12] = "A.f", "B.f"
        graphs = []
        for names in [slots, slots[:7] + ["new1", "new2"] + slots[7:]]:
            fields, expected = fixture(names)
            raw = tree_document([n(412, *fields)], 6)
            graph = Generation(raw, configuration="cfg")
            self.assertEqual(graph.nodes, expected)
            self.assertEqual(graph.encode_rows(graph.rows), raw)
            graphs.append(graph.nodes)
        self.assertEqual(*graphs)

    def test_only_current_cache_directory_is_selected(self):
        with tempfile.TemporaryDirectory() as root:
            cache = Path(root)
            for name in ("query-graph-v1", "query-graph-v2"):
                (cache / name).mkdir()
                (cache / name / "CURRENT").touch()
            with self.assertRaisesRegex(Invalid, "CURRENT absent"):
                cache_directory(cache)
            (cache / CACHE_DIRECTORY).mkdir()
            (cache / CACHE_DIRECTORY / "CURRENT").touch()
            self.assertEqual(cache_directory(cache), cache / CACHE_DIRECTORY)

    def test_malformed_tables(self):
        tests = [(2, l(s("A.f"), s("A.f"))), (3, l(l())), (3, l(l(i(0), i(0)))),
                 (3, l(l(i(-1)))), (3, l(l(i(2)))),
                 (4, l(n(414, i(1), i(0), s("Eq Int")))),
                 (4, l(n(414, i(0), i(-1), s("Eq Int")))),
                 (4, l(n(414, i(0), i(0), s("")))), (5, l(s(""), s("A")))]
        for field, value in tests:
            fields, _ = fixture(["A.f", "B.f"])
            fields[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(Invalid):
                Generation(tree_document([n(412, *fields)], 6))

    def test_deep_shared_graph_and_cycle_in_both_row_orders(self):
        graph = Generation.__new__(Generation)
        for order in (range(8192), reversed(range(8192))):
            graph.nodes = {i: {"reads": [(i-1, "h")] * 2 if i else []} for i in order}
            graph.check_cycles()
            graph.nodes[0]["reads"].append((8191, "h"))
            with self.assertRaisesRegex(Invalid, "cycl"):
                graph.check_cycles()

    def test_checksum_and_configuration(self):
        fields, _ = fixture(["A.f", "B.f"])
        raw = tree_document([n(412, *fields)], 6)
        with self.assertRaisesRegex(Invalid, "generation address"):
            Generation(raw, expected_hash="0" * 64)
        with self.assertRaisesRegex(Invalid, "generation configuration"):
            Generation(raw, configuration="other")


if __name__ == "__main__":
    unittest.main()
