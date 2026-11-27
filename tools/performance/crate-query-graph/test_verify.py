#!/usr/bin/env python3
"""Pure verifier adapters and attack fixtures; no compiler or production imports."""
from pathlib import Path
import re
import tempfile
import unittest

from test_template_receipts import TemplateReceiptTests
from test_finish_receipts_latest import LatestReceiptTests

import verify as v
from artifact_binary_reference import Invalid, read_document, tree_document
from test_query_index import read_index, node, text, integer, listing, row, index

H1, H2, H3 = 'a' * 64, 'b' * 64, 'c' * 64


class VerifierTests(unittest.TestCase):
    def test_resume_requires_complete_current_verifier_input_identity(self):
        inputs = v.verifier_inputs()
        self.assertIn('tools/performance/crate-query-graph/template_receipts.py', inputs)
        self.assertIn('tools/shared/artifact_structure_contract.json', inputs)
        original = dict(complete=False, binary_sha256=H1, verifier_inputs=inputs,
                        recovery=['body', 'protection'])
        v.require_current_run(original, H1, inputs)
        variants = [dict(original, verifier_inputs={}),
                    {k: value for k, value in original.items() if k != 'verifier_inputs'},
                    dict(original, verifier_inputs={**inputs, 'tools/shared/artifact_binary_open.py': H2})]
        for record in variants:
            with self.assertRaisesRegex(Invalid, 'resume verifier inputs changed'):
                v.require_current_run(record, H1, inputs)
        for record in [dict(original, binary_sha256=H2), dict(original, complete=True)]:
            with self.assertRaisesRegex(Invalid, 'same unfinished compiler run'):
                v.require_current_run(record, H1, inputs)

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

    def test_verifier_mutations_preserve_the_input_wire_format(self):
        from artifact_binary_typed import l, n, pack, s

        a, b = (pack(['Binding', name]) for name in ('A', 'B'))
        records = {a: dict(sha=H1, reads=[], payload=H1),
                   b: dict(sha=H2, reads=[(a, H1)] * 2, payload=None)}
        tables = [l(s('A'), s('B')), l(), l(), l()]
        slots = [integer(0), integer(1)]
        def typed(first_edge):
            rows = l(n(413, slots[0], s(H1), l(), n(5, s(H1))),
                     n(413, slots[1], s(H2), l(first_edge, slots[0]), n(4)))
            return tree_document([n(412, s('MLF-CRATE-QUERY-GRAPH-2'), s('cfg'), *tables, rows)], 6)

        def columns(first_edge):
            return tree_document([n(412, s('MLF-CRATE-QUERY-GRAPH-3'), s('cfg'), *tables,
                l(*slots), l(s(H1), s(H2)), l(integer(0), integer(2)),
                l(first_edge, slots[0]), l(slots[0]))], 6)

        broken = {**records, b: {**records[b], 'reads': [(pack(['Binding', 'absent-definition']), H1), (a, H1)]}}
        formats = [(v.index_bytes('cfg', records, version=1), v.index_bytes('cfg', broken, version=1), 'missing/stale dependency'),
                   (v.index_bytes('cfg', records, version=2), v.index_bytes('cfg', broken, version=2), 'missing dependency'),
                   (typed(slots[0]), typed(integer(2)), 'dangling query read'),
                   (columns(slots[0]), columns(integer(2)), 'dangling query read')]
        expected = {a: dict(sha=H3, reads=[], payload=H3),
                    b: dict(sha=H2, reads=[(a, H3)] * 2, payload=None)}
        for raw, expected_damage, reason in formats:
            original, = read_document(raw, 6).values()
            with self.subTest(marker=original[2][0], fields=len(original[2])):
                generation = v.Generation(raw, configuration='cfg')
                self.assertEqual(generation.nodes, records)
                self.assertEqual(generation.encode_rows(generation.rows), raw)
                repinned = v.repin_generation(generation, a, H3)
                self.assertEqual(v.Generation(repinned, configuration='cfg').nodes, expected)
                damaged = v.dangling_generation(generation)
                self.assertEqual(damaged, expected_damage)
                with self.assertRaisesRegex(Invalid, '^' + re.escape(reason) + '$'):
                    v.Generation(damaged, configuration='cfg')
                for result in (damaged, repinned):
                    root, = read_document(result, 6).values()
                    self.assertEqual((root[1], len(root[2])), (original[1], len(original[2])))
                    self.assertEqual(root[2][:2], original[2][:2])
                    if len(original[2]) in (7, 11):
                        self.assertEqual(root[2][2:6], original[2][2:6])

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


if __name__ == '__main__':
    unittest.main()
