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
from artifact_binary_typed import l, n, pack, s
from query_generation import V3

H1, H2, H3 = 'a' * 64, 'b' * 64, 'c' * 64


def integer(value):
    return ('int', value)


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

    def encode(self, hashes, counts, targets, payloads=(), names=('leaf/α😀', 'root')):
        return tree_document([n(412, s(V3), s('cfg'), l(*map(s, names)),
            l(), l(), l(), l(*(integer(i) for i in range(len(names)))),
            l(*map(s, hashes)), l(*map(integer, counts)), l(*map(integer, targets)),
            l(*map(integer, payloads)))], schema=6)

    def cache(self, root, raw, payloads):
        directory = root / 'query-graph-v3'
        (directory / 'generations').mkdir(parents=True)
        (directory / 'results').mkdir()
        digest = v.sha(raw)
        (directory / 'CURRENT').write_bytes(tree_document([s(digest)], schema=6))
        (directory / 'generations' / (digest + '.mlfqg')).write_bytes(raw)
        for key, value in payloads.items():
            (directory / 'results' / (key + '.mlfqr')).write_bytes(value)
        return digest

    def test_graph_api_payload_and_canonical_roundtrip(self):
        payload = tree_document([n(77, integer(3))], schema=6)
        digest = v.sha(payload)
        names = ('leaf/α😀', 'root')
        leaf, root_key = (pack(['Binding', name]) for name in names)
        raw = self.encode((digest, H2), (0, 2), (0, 0), (0,), names)
        records = {leaf: dict(sha=digest, reads=[], payload=digest),
                   root_key: dict(sha=H2, reads=[(leaf, digest)] * 2, payload=None)}
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            generation = self.cache(cache, raw, {digest: payload})
            self.assertEqual(v.graph(cache), (generation, records))
        read = v.Generation(raw, configuration='cfg', expected_hash=generation)
        self.assertEqual(read.encode_rows(read.rows), raw)
        with self.assertRaises(Invalid):
            v.Generation(raw, expected_hash=H3)
        with self.assertRaises(Invalid):
            v.Generation(raw, configuration='other')

    def test_graph_rejects_bad_payload_sha_and_invalid_payload_wire(self):
        payload = tree_document([n(77, integer(3))], schema=6)
        digest = v.sha(payload)
        invalid = b'not a binary payload'
        cases = [
            (digest, payload[:-1] + bytes([payload[-1] ^ 1]), 'query payload SHA256'),
            (v.sha(invalid), invalid, 'file length cap/header'),
        ]
        for expected, raw, reason in cases:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                cache = Path(temporary)
                self.cache(cache, self.encode((expected,), (0,), (), (0,), names=('leaf',)), {expected: raw})
                with self.assertRaisesRegex(Invalid, '^' + re.escape(reason) + '$'):
                    v.graph(cache)

    def test_trusted_payload_changes_type_but_passes_structure(self):
        correct = tree_document([n(77, integer(3))], schema=6)
        wrong = tree_document([n(79, n(7))], schema=6)
        old, new = v.sha(correct), v.sha(wrong)
        infer, user = (pack(['Binding', name]) for name in ('infer', 'user'))
        original = {infer: dict(sha=old, reads=[], payload=old),
                    user: dict(sha=H1, reads=[(infer, old)] * 2, payload=None)}
        changed = v.replace_result(original, infer, new)
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            generation = self.cache(cache, self.encode((new, H1), (0, 2), (0, 0), (0,),
                                                       names=('infer', 'user')), {new: wrong})
            self.assertEqual(v.graph(cache), (generation, changed))
        # The live compiler case separately exercises ICH, linking and semantic repair.

    def test_verifier_mutations_preserve_current_columns_and_read_order(self):
        a, b = (pack(['Binding', name]) for name in ('A', 'B'))
        original = self.encode((H1, H2), (0, 2), (0, 0), (0,), names=('A', 'B'))
        generation = v.Generation(original, configuration='cfg')
        expected = {a: dict(sha=H3, reads=[], payload=H3),
                    b: dict(sha=H2, reads=[(a, H3)] * 2, payload=None)}
        repinned = v.repin_generation(generation, a, H3)
        self.assertEqual(v.Generation(repinned, configuration='cfg').nodes, expected)
        damaged = v.dangling_generation(generation)
        self.assertEqual(damaged, self.encode((H1, H2), (0, 2), (2, 0), (0,), names=('A', 'B')))
        with self.assertRaisesRegex(Invalid, '^dangling query read$'):
            v.Generation(damaged, configuration='cfg')
        original_root, = read_document(original, 6).values()
        for result in (damaged, repinned):
            root, = read_document(result, 6).values()
            self.assertEqual((root[1], len(root[2])), (412, 11))
            self.assertEqual(root[2][:6], original_root[2][:6])

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
