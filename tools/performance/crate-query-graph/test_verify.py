#!/usr/bin/env python3
"""Pure verifier adapters and attack fixtures; no compiler or production imports."""
from pathlib import Path
import ast
import hashlib
import inspect
import re
import tempfile
import unittest

import verify as v
from artifact_binary_reference import Invalid, read_document, tree_document
from test_query_index import read_index, fields, node, text, integer, listing, row, index

H1, H2, H3 = 'a' * 64, 'b' * 64, 'c' * 64


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.records = {
            'leaf/α😀': {'sha': H1, 'reads': [], 'payload': None},
            'other': {'sha': H2, 'reads': [], 'payload': H3},
            'root': {'sha': H3,
                     'reads': [('leaf/α😀', H1), ('other', H2),
                               ('leaf/α😀', H1), ('other', H2)],
                     'payload': H3},
        }

    def encode(self, records=None, version=2):
        return v.index_bytes('config', self.records if records is None else records, version=version)

    def test_legacy_and_v2_logical_parity(self):
        for version in (1, 2):
            raw = self.encode(version=version)
            decoded = v.index_data(raw, expected=v.sha(raw))
            self.assertEqual(decoded, (version, 'config', self.records))
            actual, _ = read_index(raw, 'config')
            self.assertEqual(actual['root'][1], self.records['root']['reads'])
            self.assertEqual(actual['other'][2], H3)
            self.assertEqual(v.index_bytes(decoded[1], decoded[2], version=version), raw)

    def test_empty_both_versions(self):
        for version in (1, 2):
            raw = v.index_bytes('', {}, version=version)
            self.assertEqual(v.index_data(raw), (version, '', {}))

    def test_independent_fixture_exact_v2_bytes(self):
        strings = [H1, H2, 'leaf', 'root']
        explicit = index(strings, [row(2, 0), row(3, 1, [(2, 0), (2, 0)], 0)])
        records = {'root': {'sha': H2, 'reads': [('leaf', H1), ('leaf', H1)], 'payload': H1},
                   'leaf': {'sha': H1, 'reads': [], 'payload': None}}
        raw = self.encode(records)
        self.assertEqual(raw, tree_document([explicit], schema=6))
        self.assertEqual(v.index_data(raw), (2, 'config', records))

    def test_reader_rejects_roots_versions_configuration_and_sha(self):
        raw = self.encode()
        with self.assertRaisesRegex(Invalid, 'SHA256'):
            v.index_data(raw, expected=H1)
        original = read_document(raw, 6).values()[0]
        bads = [
            tree_document([], schema=6),
            tree_document([original, original], schema=6),
            tree_document([text('not an index')], schema=6),
            tree_document([node(999)], schema=6),
            tree_document([node(412, text('wrong marker'), *original[2][1:])], schema=6),
            tree_document([node(412, original[2][0], integer(0), *original[2][2:])], schema=6),
        ]
        for bad in bads:
            with self.subTest(raw=bad[:24]), self.assertRaises(Invalid):
                v.index_data(bad)
        with self.assertRaises(Invalid):
            v.index_bytes('config', {}, version=3)

    def test_order_duplicates_location_and_key_order(self):
        original = self.encode()
        reversed_keys = dict(reversed(list(self.records.items())))
        self.assertEqual(self.encode(reversed_keys), original)
        _, _, decoded = v.index_data(original)
        self.assertEqual(decoded['root']['reads'], self.records['root']['reads'])
        self.assertEqual(decoded['other']['sha'], H2)
        self.assertEqual(decoded['other']['payload'], H3)
        reordered = {k: dict(e, reads=list(e['reads'])) for k, e in self.records.items()}
        reordered['root']['reads'].reverse()
        self.assertNotEqual(self.encode(reordered), original)
        self.assertEqual(v.index_data(self.encode(reordered))[2], reordered)

    def test_dangling_attack_has_only_intended_rejection(self):
        for version, reason in ((1, 'closure'), (2, 'missing dependency')):
            changed = {k: dict(e, reads=list(e['reads'])) for k, e in self.records.items()}
            changed['root']['reads'][0] = ('absent-definition', H1)
            raw = self.encode(changed, version=version)
            self.assertEqual(read_document(raw, 6).values()[0][1], 411 if version == 1 else 412)
            v.reject_index(raw, 'config', reason)
            with self.assertRaisesRegex(Invalid, 'unexpected query-index rejection'):
                v.reject_index(raw, 'config', 'unused dictionary')
            with self.assertRaisesRegex(Invalid, 'fixture was accepted'):
                v.reject_index(self.encode(version=version), 'config', reason)

    def test_stale_attack_keeps_reference_id_valid(self):
        for version, reason in ((1, 'closure'), (2, 'stale dependency')):
            changed = {k: dict(e, reads=list(e['reads'])) for k, e in self.records.items()}
            changed['root']['reads'][0] = ('leaf/α😀', H2)
            v.reject_index(self.encode(changed, version=version), 'config', reason)

    def test_trusted_repin_updates_all_incoming_reads(self):
        source = {k: dict(e, reads=list(e['reads'])) for k, e in self.records.items()}
        changed = v.replace_result(source, 'leaf/α😀', 'd' * 64)
        self.assertEqual(source, self.records)
        self.assertEqual(changed['leaf/α😀'], {'sha': 'd' * 64, 'reads': [], 'payload': 'd' * 64})
        self.assertEqual(changed['other'], source['other'])
        self.assertEqual(changed['root']['reads'],
                         [('leaf/α😀', 'd' * 64), ('other', H2),
                          ('leaf/α😀', 'd' * 64), ('other', H2)])
        for version in (1, 2):
            raw = self.encode(changed, version=version)
            self.assertEqual(v.index_data(raw), (version, 'config', changed))
            document = read_document(raw, 6)
            self.assertNotIn(H1, document.symbols)
        with self.assertRaisesRegex(Invalid, 'key missing'):
            v.replace_result(source, 'absent', H1)

    def test_v2_dictionary_and_row_corruptions_rejected(self):
        value = read_document(self.encode(), 6).values()[0]
        marker, config, dictionary, entries = value[2]
        strings, rows = list(dictionary[2]), list(entries[2])
        variants = [
            node(412, marker, config, listing(strings[::-1]), entries),
            node(412, marker, config, listing(strings + [text('zz-unused')]), entries),
            node(412, marker, config, listing([strings[0]] + strings), entries),
            node(412, marker, config, dictionary, listing(rows[::-1])),
            node(412, marker, config, dictionary, listing([rows[0]] + rows)),
        ]
        for value in variants:
            with self.assertRaises(Invalid):
                v.index_data(tree_document([value], schema=6))

    def test_v2_id_types_ranges_hash_and_location_rejected(self):
        strings = [H1, 'leaf']
        rows = [row(1, 0)]
        for bad in (-1, 2, (1 << 63) - 1):
            with self.assertRaisesRegex(Invalid, 'ID range'):
                v.index_data(tree_document([index(strings, [row(1, bad)])], schema=6))
        for bad in (text('0'), ('bits', 0), node(1)):
            damaged = node(413, integer(1), bad, listing([]), node(4))
            with self.assertRaises(Invalid):
                v.index_data(tree_document([index(strings, [damaged])], schema=6))
        for damaged in [row(1, 1), row(1, 0, location=1),
                        node(413, integer(1), integer(0), listing([]), node(4, integer(0)))]:
            with self.assertRaises(Invalid):
                v.index_data(tree_document([index(strings, [damaged])], schema=6))

    def cache(self, root, raw, payloads):
        directory = root / 'query-graph-v1'
        (directory / 'generations').mkdir(parents=True)
        (directory / 'results').mkdir()
        digest = v.sha(raw)
        (directory / 'CURRENT').write_bytes(tree_document([text(digest)], schema=6))
        (directory / 'generations' / (digest + '.mlfqg')).write_bytes(raw)
        for key, value in payloads.items():
            (directory / 'results' / (key + '.mlfqr')).write_bytes(value)
        return digest, directory

    def test_graph_api_payload_and_canonical_roundtrip_both_versions(self):
        payload = tree_document([node(77, integer(3))], schema=6)
        digest = v.sha(payload)
        records = {'leaf': {'sha': digest, 'reads': [], 'payload': digest},
                   'root': {'sha': H2, 'reads': [('leaf', digest)] * 2, 'payload': None}}
        for version in (1, 2):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                generation, _ = self.cache(root, self.encode(records, version), {digest: payload})
                self.assertEqual(v.graph(root), (generation, records))

    def test_graph_rejects_bad_payload_bytes_and_location_hash(self):
        payload = tree_document([node(77, integer(3))], schema=6)
        digest = v.sha(payload)
        for version in (1, 2):
            for row_hash, raw, reason in [
                (digest, payload[:-1] + bytes([payload[-1] ^ 1]), 'query payload SHA256'),
                # Legacy admission now checks the row/location identity before
                # opening the payload; dictionary v2 retains its original reader.
                (H2, payload, 'query graph payload matches result hash'
                 if version == 1 else 'query payload SHA256'),
            ]:
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    records = {'leaf': {'sha': row_hash, 'reads': [], 'payload': digest}}
                    self.cache(root, self.encode(records, version), {digest: raw})
                    with self.assertRaisesRegex(Invalid, '^' + re.escape(reason) + '$'):
                        v.graph(root)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad = b'not a binary payload'
            digest = v.sha(bad)
            records = {'leaf': {'sha': digest, 'reads': [], 'payload': digest}}
            self.cache(root, self.encode(records), {digest: bad})
            with self.assertRaisesRegex(Invalid, 'file length cap/header'):
                v.graph(root)

    def test_trusted_payload_changes_type_but_passes_structure(self):
        correct = tree_document([node(77, integer(3))], schema=6)
        wrong = tree_document([node(79, node(7))], schema=6)
        old, new = v.sha(correct), v.sha(wrong)
        original = {'infer': {'sha': old, 'reads': [], 'payload': old},
                    'user': {'sha': H1, 'reads': [('infer', old)] * 2, 'payload': None}}
        for version in (1, 2):
            changed = v.replace_result(original, 'infer', new)
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                generation, _ = self.cache(root, self.encode(changed, version), {new: wrong})
                self.assertEqual(v.graph(root), (generation, changed))
        # This pure test proves only structural fixture validity. Actual ICH
        # reuse, linker rejection and semantic repair remain in verify.main.

    def test_normalized_rows_preserve_all_three_wire_formats(self):
        from test_query_generation import fixture
        from artifact_binary_typed import n
        typed_fields, legacy = fixture(['A.f', 'B.f'])
        typed = tree_document([n(412, *typed_fields)], schema=6)
        records = v.Generation(legacy).nodes
        dictionary = v.index_bytes('cfg', records, version=2)
        for raw, reason in [(legacy, 'missing/stale dependency'),
                            (dictionary, 'missing dependency'),
                            (typed, 'dangling query read')]:
            wire = v.Generation(raw)
            self.assertEqual(wire.encode_rows(wire.rows), raw)
            self.assertEqual(wire.nodes, records)
            damaged = []
            changed = False
            for value in wire.rows:
                key, result, reads, location = v.node(value, 410, 4)
                edges = list(v.items(reads))
                if edges and not changed:
                    _, expected = v.pair(edges[0])
                    edges[0] = n(2, ('text', 'absent'), expected)
                    value = n(410, key, result, n(1, *edges), location)
                    changed = True
                damaged.append(value)
            self.assertTrue(changed)
            self.assertEqual(len(damaged), len(wire.rows))
            self.assertEqual(sum(a != b for a, b in zip(damaged, wire.rows)), 1)
            with self.assertRaisesRegex(Invalid, '^' + re.escape(reason) + '$'):
                v.Generation(wire.encode_rows(damaged), configuration='cfg')

    def test_finish_receipt_package_schema_dispatch(self):
        from finish_receipts import package_fragments
        from artifact_binary_open import OpenPairError
        from artifact_binary_typed import n, s, l
        final = n(401, s('group'), s(H1), l(), l(), n(77, integer(3)), l(), l())
        header7 = lambda finals: n(430, s('MLF-OPEN-CRATE-1/checker-1'),
                                  s('compiler'), s('metadata'), l(), l(), l(*finals))
        header8 = lambda count: n(432, s('MLF-OPEN-CRATE-2/checker-1'),
                                 s('compiler'), s('metadata'), l(), l(), integer(count))
        expected = {'group': final[2]}
        for schema, roots in [(7, [header7([final])]), (8, [header8(1), final])]:
            raw = tree_document(roots, schema=schema)
            self.assertEqual(package_fragments(raw), expected)
            damaged = raw[:-1] + bytes([raw[-1] ^ 1])
            with self.assertRaises((Invalid, OpenPairError)):
                package_fragments(damaged)
        cases = [(7, [header7([final]), final], 'exactly one schema7 open root'),
                 (8, [header8(0), final], 'open fragment count mismatch'),
                 (7, [header7([final, final])], 'duplicate open package fragment'),
                 (8, [header8(2), final, final], 'duplicate open package fragment'),
                 (6, [header7([final])], 'unsupported open schema')]
        for schema, roots, reason in cases:
            with self.assertRaisesRegex((Invalid, OpenPairError), '^' + re.escape(reason) + '$'):
                package_fragments(tree_document(roots, schema=schema))
        # A recognized schema must never retry the other layout.
        for schema, roots in [(7, [header8(1), final]), (8, [header7([final])])]:
            with self.assertRaises((Invalid, OpenPairError)):
                package_fragments(tree_document(roots, schema=schema))

    def test_main_case_and_failpoint_inventory_preserved(self):
        self.assertEqual(list(v.CASES),
                         ['body', 'type', 'protection', 'datatype', 'constructor-owner',
                          'scc', 'scope', 'scope-order', 'recursive-dictionary'])
        self.assertEqual([len(states) for states in v.CASES.values()], [2, 2, 2, 2, 2, 3, 3, 2, 2])
        source = inspect.getsource(v.main)
        constants = [n.value for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Constant)]
        # Generation.rows deliberately normalizes all three wire formats to
        # logical 410 rows. Only those row reads/writes may use this tag; actual
        # serialization must retain the source generation's tables/version.
        syntax = ast.parse(source)
        row_reads = [n for n in ast.walk(syntax) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == 'node'
                     and len(n.args) == 3 and isinstance(n.args[1], ast.Constant)
                     and n.args[1].value == 410]
        self.assertEqual(len(row_reads), 2)
        for call in row_reads:
            self.assertEqual(ast.literal_eval(call.args[2]), 4)
        row_writes = [n for n in ast.walk(syntax) if isinstance(n, ast.Tuple)
                      and len(n.elts) == 3 and isinstance(n.elts[1], ast.Constant)
                      and n.elts[1].value == 410]
        self.assertEqual(len(row_writes), 2)
        for value in row_writes:
            self.assertEqual(ast.literal_eval(value.elts[0]), 'node')
        self.assertEqual(constants.count(410), 4)
        encoders = [n for n in ast.walk(syntax) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == 'encode_rows']
        self.assertEqual([ast.unparse(n.func.value) for n in encoders], ['wire', 'wire'])
        calls = [n.func.id for n in ast.walk(syntax)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertNotIn('index_bytes', calls)
        self.assertNotIn('index_data', calls)
        self.assertNotIn(411, constants)
        for point in ('before-results', 'after-result-staging', 'after-result-batch',
                      'before-index', 'before-current'):
            self.assertIn(point, constants)
        for control in ('trusted-receipt', 'semantic-audit-repair',
                        'receipt_ich_semantic_audit_separated', 'serialized_writers',
                        'partial_batch_preserves_previous_generation'):
            self.assertIn(control, constants)


if __name__ == '__main__':
    unittest.main()
