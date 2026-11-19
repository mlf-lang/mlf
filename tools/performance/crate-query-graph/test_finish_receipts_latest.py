#!/usr/bin/env python3
"""Authored fixtures for direct Binding providers and shared empty authority."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import verify  # Existing independent oracle import path.
from artifact_binary_reference import Invalid, tree_document, read_document
from artifact_binary_typed import n, s, l, pack, value_node, list_values
from artifact_binary_open import open_bytes
from query_generation import Generation, V3
from finish_receipts import check_receipts, forge_direct_binding_generation, forge_generation


def sha(value):
    return hashlib.sha256(value).hexdigest()


def authored(root, shared=True, finish=False, spine=False, split_public=False):
    prefix = root / 'unit'; cache = root / 'cache'; directory = cache / 'query-graph-v3'
    (directory / 'results').mkdir(parents=True)
    (directory / 'CURRENT').write_text('not consulted by receipt inspector')
    member, group = 'App.value', 'actual-owner'
    identity = pack([member]); prepared = pack(['Input', pack(['Prepared', identity])])
    raw_key = pack(['InferScc', identity]); binding_key = pack(['Binding', member])
    finish_key = pack(['FinishScc', identity])
    binder = n(31, ('int', 19), s(member)); ty = n(44, s('Int'), l())
    body = n(75, binder, n(77, ('int', 5)), n(82, s('()'), l()))
    public_body = body
    if spine:
        def storage(split):
            integer = lambda x: ('int', x)
            rows = l(n(87), n(82, s('leaf:λ'), l()), n(88, integer(1), integer(0)),
                     n(82, s('end'), l()), n(88, integer(2), integer(3), integer(8)))
            run = n(89, integer(-3), integer(1), integer(8))
            stream = l(*(integer(i) for i in range(-3, 5))) if split else l(run)
            return n(75, binder, n(86, rows, stream, integer(4)), n(82, s('()'), l()))
        body = storage(False)
        public_body = storage(split_public)
    record = n(442 if spine else 400, s('raw'), s(group), s('10-20'), l(), body, l(n(2, binder, ty)), l())
    payload = tree_document([n(425, l(), record)], 6); digest = sha(payload)
    (directory / 'results' / (digest + '.mlfqr')).write_bytes(payload)
    if shared:
        inventory = pack(['Input', pack(['EmptyScopeInventory', ''])]); scope = pack(['EmptyScope', ''])
        ih = sha(pack(['MLF-SCOPE-INVENTORY-TEXT-1', '0']).encode())
        sh = sha(pack(['MLF-SCOPE-READS-TEXT-1', '0', '0']).encode())
    else:
        inventory = pack(['Input', pack(['ScopeInventory', identity])]); scope = pack(['Scope', identity])
        ih, sh = 'a' * 64, 'b' * 64
    nodes = {inventory: dict(sha=ih, reads=[], payload=None),
             scope: dict(sha=sh, reads=[(inventory, ih)], payload=None),
             prepared: dict(sha='c' * 64, reads=[], payload=None)}
    leading = [(raw_key, digest), (prepared, 'c' * 64), (scope, sh)]
    nodes[raw_key] = dict(sha=digest, reads=leading[1:], payload=digest)
    contract = sha(tree_document([n(420, ty, l(), n(7))], 6))
    nodes[binding_key] = dict(sha=contract, reads=leading, payload=None)
    if finish:
        receipt = pack(['MLF-FINISH-RECEIPT-TEXT-1', group, digest, '1', member, contract])
        fh = sha(receipt.encode())
        nodes[finish_key] = dict(sha=fh, reads=leading, payload=None)
        nodes[binding_key]['reads'] = [(finish_key, fh)]
    interface = [s('fixture'), l(), l(), l(), l(), l(), l(), l(), l(),
                 l(n(2, s(member), ty)), s(''), s(''), l(n(2, s(member), n(7)))]
    final = n(401, s(group), s('10-20'), l(), l(), public_body, l(binder), l())
    opened = [s('MLF-OPEN-CRATE-5/checker-1' if spine else 'MLF-OPEN-CRATE-2/checker-1'), s('compiler'), s('metadata'), l(), l(), l(final)]
    prefix.with_suffix('.mlfci').write_bytes(tree_document([n(242, *interface)], 3))
    prefix.with_suffix('.mlfco').write_bytes(open_bytes(11 if spine else 8, opened))
    prefix.with_suffix('.queries').write_text(json.dumps({'groups': [dict(id=group, members=[member])]}))
    return prefix, cache, nodes, dict(raw=raw_key, binding=binding_key, scope=scope,
                                    inventory=inventory, prepared=prepared, finish=finish_key)


class LatestReceiptTests(unittest.TestCase):
    def test_compact_query_commitment_binds_the_exact_retained_application_body(self):
        for finish in (False, True):
            for split in (False, True):
                with self.subTest(finish=finish, split=split), tempfile.TemporaryDirectory() as tmp:
                    prefix, cache, nodes, _ = authored(Path(tmp), finish=finish, spine=True, split_public=split)
                    if split:
                        with self.assertRaisesRegex(Invalid, 'retained application storage'):
                            check_receipts(prefix, cache, nodes)
                    else:
                        self.assertEqual(check_receipts(prefix, cache, nodes)['retained'], 1)

    def test_handwritten_direct_and_explicit_finish_shared_and_group_scope(self):
        for shared in (False, True):
            for finish in (False, True):
                with self.subTest(shared=shared, finish=finish), tempfile.TemporaryDirectory() as tmp:
                    prefix, cache, nodes, _ = authored(Path(tmp), shared, finish)
                    self.assertEqual(check_receipts(prefix, cache, nodes),
                                     dict(retained=1, rewritten=0, template_groups=[]))

    def test_direct_rejects_missing_reordered_payload_and_evidence(self):
        for mutation, message in [('missing', 'leading edges'), ('reordered', 'leading edges'),
                                  ('payload', 'has payload'), ('evidence', 'cannot carry evidence')]:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                prefix, cache, nodes, keys = authored(Path(tmp))
                target = nodes[keys['binding']]
                if mutation == 'missing': del target['reads'][1]
                elif mutation == 'reordered': target['reads'][:2] = reversed(target['reads'][:2])
                elif mutation == 'payload': target['payload'] = target['sha']
                else: target['reads'].append((pack(['Evidence', 'site']), 'e' * 64))
                with self.assertRaisesRegex(Invalid, message): check_receipts(prefix, cache, nodes)

    def test_empty_scope_exact_hash_edges_and_current_identity(self):
        for mutation, message in [('inventory', 'inventory authority'), ('hash', 'exact authority'),
                                  ('edge', 'exact authority'), ('foreign', 'current scope identity')]:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                prefix, cache, nodes, keys = authored(Path(tmp))
                if mutation == 'inventory': nodes[keys['inventory']]['payload'] = nodes[keys['inventory']]['sha']
                elif mutation == 'hash':
                    nodes[keys['scope']]['sha'] = 'f' * 64
                    nodes[keys['raw']]['reads'][1] = (keys['scope'], 'f' * 64)
                elif mutation == 'edge': nodes[keys['scope']]['reads'] = []
                else: nodes[keys['raw']]['reads'][1] = (pack(['Scope', 'other-group']), 'b' * 64)
                with self.assertRaisesRegex(Invalid, message): check_receipts(prefix, cache, nodes)

    def test_direct_rejects_changed_final_owner_body_and_spurious_finish(self):
        from artifact_binary_open import open_document
        for mutation, message in [('owner', 'raw stage/owner'), ('body', 'must retain exact'),
                                  ('orphan', 'unexpected finish')]:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                prefix, cache, nodes, keys = authored(Path(tmp))
                if mutation == 'orphan':
                    nodes[pack(['FinishScc', 'orphan'])] = dict(sha='f' * 64, reads=[], payload=None)
                else:
                    schema, _, opened = open_document(prefix.with_suffix('.mlfco').read_bytes())
                    opened = list(opened); final = list(opened[5][2][0][2])
                    if mutation == 'body': final[4] = n(82, s('()'), l())
                    else:
                        final[0] = s('wrong-owner')
                        prefix.with_suffix('.queries').write_text(json.dumps({'groups': [dict(id='wrong-owner', members=['App.value'])]}))
                    opened[5] = l(n(401, *final)); prefix.with_suffix('.mlfco').write_bytes(open_bytes(schema, opened))
                with self.assertRaisesRegex(Invalid, message): check_receipts(prefix, cache, nodes)

    def test_direct_attacks_preserve_actual_v3_column_wire_and_graph_closure(self):
        # Complete v3 column fixture authored without the mutation encoder.
        i = lambda value: ('int', value)
        descriptors = [n(435), n(436), n(416, i(0)), n(419, i(0)), i(0),
                       n(416, i(1)), n(419, i(1)), i(1)]
        edges = [[], [n(435)], [], [n(416, i(0)), n(436)],
                 [n(419, i(0)), n(416, i(0)), n(436)], [],
                 [n(416, i(1)), n(436)], [n(419, i(1)), n(416, i(1)), n(436)]]
        original = tree_document([n(412, s(V3), s('cfg'), l(s('A'), s('B')),
            l(l(i(0)), l(i(1))), l(), l(), l(*descriptors),
            l(*(s(str(j + 1) * 64) for j in range(8))), l(*(i(len(e)) for e in edges)),
            l(*(d for e in edges for d in e)), l(i(3), i(6)))], 6)
        for mode in ('swapped-result', 'reordered', 'missing-prepared'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                cache = Path(tmp); directory = cache / 'query-graph-v3'
                (directory / 'generations').mkdir(parents=True)
                current = sha(original); path = directory / 'generations' / (current + '.mlfqg')
                path.write_bytes(original); (directory / 'CURRENT').write_bytes(tree_document([s(current)], 6))
                before = Generation(original)
                forged = forge_direct_binding_generation(cache, current, mode)
                after = Generation((directory / 'generations' / (forged + '.mlfqg')).read_bytes(), expected_hash=forged)
                self.assertEqual(after.version, 3); self.assertEqual(path.read_bytes(), original)
                changed = [key for key in before.nodes if before.nodes[key] != after.nodes[key]]
                self.assertEqual(changed, [pack(['Binding', 'A'])])
                row = after.nodes[changed[0]]; prior = before.nodes[changed[0]]
                if mode == 'swapped-result': self.assertEqual(row['sha'], before.nodes[pack(['Binding', 'B'])]['sha'])
                elif mode == 'reordered': self.assertEqual(row['reads'], [prior['reads'][1], prior['reads'][0], prior['reads'][2]])
                else: self.assertEqual(row['reads'], [prior['reads'][0], prior['reads'][2]])

    def test_multimember_finish_attacks_preserve_v3_or_reject_exact_payload_range(self):
        i = lambda value: ('int', value)
        config = pack(['compiler', 'schema', 'format', 'open-fragment-checker-1/finish-receipt-1'])
        descriptors = [n(435), n(436)]
        edges = [[], [n(435)]]
        payloads = {}
        for group in range(2):
            prepared, raw, finish = n(416, i(group)), n(419, i(group)), n(431, i(group))
            descriptors += [prepared, raw, finish, i(group * 2), i(group * 2 + 1)]
            edges += [[], [prepared, n(436)], [raw, prepared, n(436)], [finish], [finish]]
            payloads[3 + 5 * group] = tree_document([n(425, l(), n(400,
                s('raw'), s('owner-' + str(group)), s('10-20'), l(),
                n(82, s('()'), l()), l(), l()))], 6)
        hashes = [sha(payloads[j]) if j in payloads else sha(('row-' + str(j)).encode())
                  for j in range(len(descriptors))]
        original = tree_document([n(412, s(V3), s(config), l(*map(s, ['A', 'B', 'C', 'D'])),
            l(l(i(0), i(1)), l(i(2), i(3))), l(), l(), l(*descriptors), l(*map(s, hashes)),
            l(*(i(len(e)) for e in edges)), l(*(d for e in edges for d in e)), l(i(3), i(8)))], 6)
        before = Generation(original)
        modes = ('swapped', 'stale', 'reordered', 'payload-row-range', 'finish-as-raw', 'previous-format')
        for mode in modes:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                cache = Path(tmp); directory = cache / 'query-graph-v3'
                (directory / 'generations').mkdir(parents=True); (directory / 'results').mkdir()
                current = sha(original); path = directory / 'generations' / (current + '.mlfqg')
                path.write_bytes(original); (directory / 'CURRENT').write_bytes(tree_document([s(current)], 6))
                for row, payload in payloads.items():
                    (directory / 'results' / (hashes[row] + '.mlfqr')).write_bytes(payload)
                forged = forge_generation(cache, current, mode)
                encoded = (directory / 'generations' / (forged + '.mlfqg')).read_bytes()
                self.assertEqual(sha(encoded), forged); self.assertNotEqual(forged, current)
                self.assertEqual(path.read_bytes(), original)
                if mode == 'payload-row-range':
                    a = value_node(read_document(original, 6).values()[0], 412, 11)
                    b = value_node(read_document(encoded, 6).values()[0], 412, 11)
                    self.assertEqual(a[:10], b[:10])
                    self.assertEqual(list_values(b[10]), (*list_values(a[10]), i(12)))
                    with self.assertRaisesRegex(Invalid, '^query payload row range$'):
                        Generation(encoded, expected_hash=forged)
                    continue
                after = Generation(encoded, expected_hash=forged)
                self.assertEqual(after.version, 3)
                target = pack(['FinishScc', pack(['A', 'B'])])
                if mode == 'previous-format':
                    self.assertEqual(after.nodes, before.nodes)
                    self.assertEqual(after.config, s(pack(['compiler', 'schema', 'format', 'open-fragment-checker-1'])))
                elif mode == 'reordered':
                    self.assertEqual(after.nodes[target]['reads'], list(reversed(before.nodes[target]['reads'])))
                    self.assertEqual(after.nodes[target]['sha'], before.nodes[target]['sha'])
                else:
                    if mode == 'finish-as-raw': target = pack(['InferScc', pack(['A', 'B'])])
                    self.assertNotEqual(after.nodes[target]['sha'], before.nodes[target]['sha'])
                    self.assertIsNone(after.nodes[target]['payload'])
                    if mode in ('swapped', 'finish-as-raw'):
                        self.assertEqual(after.nodes[target]['sha'], before.nodes[pack(['FinishScc', pack(['C', 'D'])])]['sha'])
                    if mode == 'stale':
                        stale = pack(['MLF-FINISH-RECEIPT-TEXT-1', 'owner-0', hashes[9], '2',
                                      'A', hashes[5], 'B', hashes[6]])
                        self.assertEqual(after.nodes[target]['sha'], sha(stale.encode()))
                    expected = verify.replace_result(before.nodes, target, after.nodes[target]['sha'])
                    expected[target]['payload'] = None
                    self.assertEqual(after.nodes, expected)


if __name__ == '__main__': unittest.main()
