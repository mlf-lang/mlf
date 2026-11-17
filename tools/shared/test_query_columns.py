"""Independently authored version-3 columns and constant-scope wire controls."""
import unittest
from query_generation import Generation, V2, V3
from artifact_binary_reference import Invalid, tree_document
from artifact_binary_typed import l, n, s, list_values, value_node
from test_query_generation import fixture

def i(x): return ('int', x)
def document(fields): return tree_document([n(412, *fields)], 6)
def authored():
    fields, legacy = fixture(['A.f', 'B.f'])
    keys, hashes, counts, targets, payloads = [], [], [], [], []
    for row, entry in enumerate(list_values(fields[6])):
        key, digest, reads, location = value_node(entry, 413, 4)
        keys.append(key); hashes.append(digest)
        edges = list_values(reads); counts.append(i(len(edges))); targets.extend(edges)
        if location != n(4): payloads.append(i(row))
    return [s(V3), fields[1], *fields[2:6], l(*keys), l(*hashes),
            l(*counts), l(*targets), l(*payloads)], document(fields), legacy

class Columns(unittest.TestCase):
    def test_independent_exact_roundtrip_and_legacy_projection(self):
        fields, previous, legacy = authored(); raw = document(fields)
        graph = Generation(raw, configuration='cfg')
        self.assertEqual(graph.version, 3)
        self.assertEqual(graph.nodes, Generation(previous).nodes)
        self.assertEqual(graph.legacy_bytes(), legacy)
        self.assertEqual(graph.encode_rows(graph.rows), raw)
        self.assertTrue(any(len(row['reads']) == 2 and row['reads'][0] == row['reads'][1]
                            for row in graph.nodes.values()))
    def test_empty(self):
        fields = [s(V3), s('cfg'), *(l() for _ in range(9))]
        graph = Generation(document(fields))
        self.assertEqual(graph.nodes, {})
        self.assertEqual(graph.encode_rows(graph.rows), document(fields))
    def test_column_lengths_counts_and_payload_rows(self):
        fields, _, _ = authored(); count=len(list_values(fields[6]))
        cases=[(0,s(V2)), (1,s('')), (6,l()), (7,l()), (8,l()),
               (8,l(*([i(-1)]+[i(0)]*(count-1)))),
               (8,l(*([i(9223372036854775807)]+[i(0)]*(count-1)))),
               (8,l(*([i(0)]*count))),
               (9,l()), (9,l(*list_values(fields[9]),i(0))),
               (10,l(i(0),i(0))), (10,l(i(1),i(0))),
               (10,l(i(-1))), (10,l(i(count))), (10,l(s('0')))]
        for field,value in cases:
            with self.subTest(field=field,value=value):
                changed=list(fields);changed[field]=value
                with self.assertRaises(Invalid):Generation(document(changed))
    def test_descriptor_hash_and_cycle_controls_still_apply(self):
        fields, _, _ = authored()
        for field, first in [(6,n(999,i(0))), (7,s('z'*64))]:
            changed=list(fields); changed[field]=l(first,*list_values(fields[field])[1:])
            with self.assertRaises(Invalid):Generation(document(changed))
        single=[s(V3),s('cfg'),l(s('A.f')),l(),l(),l(),l(i(0)),
                l(s('1'*64)),l(i(1)),l(i(0)),l()]
        with self.assertRaisesRegex(Invalid,'cyclic/deep'):Generation(document(single))


class ConstantScopes(unittest.TestCase):
    def test_distinct_constant_identities_and_edges(self):
        fields = [s(V3),s('cfg'),*(l() for _ in range(4)),
                  l(n(435),n(436)),l(s('1'*64),s('2'*64)),
                  l(i(0),i(1)),l(n(435)),l()]
        raw=document(fields);g=Generation(raw)
        from artifact_binary_typed import pack
        inventory=pack(['Input',pack(['EmptyScopeInventory',''])]);scope=pack(['EmptyScope',''])
        self.assertEqual(g.nodes,{inventory:dict(sha='1'*64,reads=[],payload=None),
                                 scope:dict(sha='2'*64,reads=[(inventory,'1'*64)],payload=None)})
        self.assertEqual(g.encode_rows(g.rows),raw)
        for key in [n(435,i(0)),n(436,i(0)),n(437),n(435,n(1))]:
            changed=list(fields);changed[6]=l(key,n(436))
            with self.subTest(key=key),self.assertRaises(Invalid):Generation(document(changed))
        old=[s(V2),s('cfg'),*(l() for _ in range(4)),l(n(413,n(435),s('1'*64),l(),n(4)))]
        with self.assertRaises(Invalid):Generation(document(old))

if __name__=='__main__':unittest.main()
