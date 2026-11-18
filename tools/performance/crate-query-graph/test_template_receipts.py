#!/usr/bin/env python3
"""Complete independent wire fixtures, not compiler-generated proof evidence."""
from pathlib import Path
import copy
import hashlib
import json
import tempfile
import unittest

import verify  # Establish the existing independent-oracle import path.
from artifact_binary_reference import Invalid, tree_document, read_document
from artifact_binary_typed import n, s, l, pack, value_node as fields, list_values as items, unpack
from artifact_binary_open import open_bytes, open_document
from finish_receipts import check_receipts, wrong_template_stamp, forge_template_generation
from template_receipts import rebind_template, monotype_key, parse_template_key, expression_key


def h(raw):
    return hashlib.sha256(raw).hexdigest()


def binder(identity, hint):
    return n(31, ('int', identity), s(hint))


POLY = n(46, n(30, ('int', 0)), n(41),
         n(43, n(40, n(30, ('int', 0))), n(40, n(30, ('int', 0)))))
TYPE_KEY = pack(['forall', '0', pack(['bottom']),
                 pack(['arrow', pack(['variable', '0']), pack(['variable', '0'])])])


def fixture(owner='App.out', dependencies=('App.left', 'App.right')):
    parameters = [binder(i, 'templateParameter' + str(k)) for k, i in enumerate((7, 11))]
    exported = binder(19, 'templateOwner')
    body = n(75, exported, n(72, *(n(70, b) for b in parameters)), n(82, s('()'), l()))
    original = n(400, s('raw'), s('template'), s('10-20'),
                 l(*(n(2, b, b[2][1]) for b in parameters)), body,
                 l(n(2, exported, POLY)), l(*parameters))
    references = l(n(2, s('checked-inference-template-1'), s(pack([
        'checked-inference-template-1', '', pack([TYPE_KEY, TYPE_KEY]),
        pack(['application', pack(['variable', '0']), pack(['variable', '1'])])]))))
    raw_refs = [(pack(['Binding', x]), h(x.encode())) for x in dependencies]
    types = {x: POLY for x in [*dependencies, owner]}
    ps, rebound, owned, used = rebind_template(references, original, raw_refs, [owner], types)
    group = 'group/' + owner
    final = n(401, s(group), s('30-40'), l(),
              l(*(fields(x, 2, 2)[0] for x in items(ps))), rebound,
              l(*(fields(x, 2, 2)[0] for x in items(owned))), used)
    return dict(owner=owner, group=group, references=references, original=original,
                raw_refs=raw_refs, types=types, final=final, mode='template')


def signed_fixture():
    f = fixture()
    int_type = n(44, s('Int'), l())
    int_key = pack(['constructor', 'Int', ''])
    arrow = n(43, int_type, int_type)
    schemes = [pack(['arrow', int_key, int_key]), int_key]
    annotation = pack(['annotation', '', int_key])
    expression = pack(['checked', int_key, pack(['application',
        pack(['variable', '0']), pack(['variable', '1'])])])
    f['references'] = l(n(2, s('checked-inference-template-1'), s(pack([
        'checked-signed-inference-template-1', annotation, '', pack(schemes), expression]))))
    exported, _ = fields(items(f['original'][2][5])[0], 2, 2)
    f['original'] = changed(f['original'], 5, l(n(2, exported, int_type)))
    f['types'] = {'App.left': arrow, 'App.right': int_type, 'App.out': int_type}
    return f


def changed(value, index, replacement):
    values = list(value[2]); values[index] = replacement
    return n(value[1], *values)


def write_fixture(root, f):
    prefix = root / 'unit'
    cache = root / 'cache'
    directory = cache / 'query-graph-v2'
    (directory / 'results').mkdir(parents=True)
    (directory / 'CURRENT').write_text('fixture pointer is not read by this API')
    payload = tree_document([n(425, f['references'], f['original'])], 6)
    digest = h(payload)
    (directory / 'results' / (digest + '.mlfqr')).write_bytes(payload)
    identity = pack([f['owner']])
    raw_key = pack(['InferScc', identity]); finish_key = pack(['FinishScc', identity])
    prepared = pack(['Input', pack(['Prepared', identity])]); scope = pack(['Scope', identity])
    leading = [(prepared, 'a' * 64), (scope, 'b' * 64)]
    nodes = {k: dict(sha=v, reads=[], payload=None) for k, v in [*leading, *f['raw_refs']]}
    nodes[raw_key] = dict(sha=digest, reads=leading + f['raw_refs'], payload=digest)
    final = f['final']
    _, stamp, ds, ps, body, owned, uses = fields(final, 401, 7)
    final_keys = [pack(['Binding', fields(b, 31, 2)[1][1]]) for b in items(ps)]
    final_refs = l(*(n(2, s(k), s(nodes[k]['sha'])) for k in final_keys))
    content = digest
    if f['mode'] == 'concrete':
        params = l(*(n(2, b, fields(b, 31, 2)[1]) for b in items(ps)))
        exports = l(*(n(2, b, f['types'][fields(b, 31, 2)[1][1]]) for b in items(owned)))
        content = h(tree_document([n(425, final_refs, n(400, s('raw'), s(f['group']),
            stamp, params, body, exports, uses))], 6))
    contract = 'c' * 64
    # Expected receipt bytes are authored here, not returned by the inspector.
    receipt = pack(['MLF-FINISH-RECEIPT-TEXT-1', f['group'], content, '1', f['owner'], contract])
    finish = h(receipt.encode())
    nodes[finish_key] = dict(sha=finish, reads=[(raw_key, digest), *leading,
        *((k, nodes[k]['sha']) for k in final_keys)], payload=None)
    nodes[pack(['Binding', f['owner']])] = dict(sha=contract, reads=[(finish_key, finish)], payload=None)
    interface = [s('fixture'), l(), l(), l(), l(), l(), l(), l(), l(),
        l(*(n(2, s(k), ty) for k, ty in f['types'].items())), s(''), s(''), l()]
    opened = [s('MLF-OPEN-CRATE-2/checker-1'), s('compiler'), s('metadata'), l(), l(), l(final)]
    prefix.with_suffix('.mlfci').write_bytes(tree_document([n(242, *interface)], 3))
    prefix.with_suffix('.mlfco').write_bytes(open_bytes(8, opened))
    prefix.with_suffix('.queries').write_text(json.dumps({'groups': [dict(id=f['group'], members=[f['owner']])]}))
    return prefix, cache, nodes


def column_generation(nodes, owner, config='fixture'):
    """Small explicit v3 column fixture, independent of Generation.encode_rows."""
    declarations = sorted(unpack(key)[1] for key in nodes if unpack(key)[0] == 'Binding')
    integer = lambda value: ('int', value)
    def descriptor(key):
        kind, identity = unpack(key)
        if kind == 'Binding': return integer(declarations.index(identity))
        if kind == 'Input':
            category, members = unpack(identity)
            if category == 'EmptyScopeInventory': return n(435)
            assert category == 'Prepared' and members == pack([owner])
            return n(416, integer(0))
        if kind == 'EmptyScope':
            assert identity == ''
            return n(436)
        assert identity == pack([owner])
        return n({'Scope': 418, 'InferScc': 419, 'FinishScc': 431}[kind], integer(0))
    columns = [[], [], [], [], []]
    for row, (key, record) in enumerate(sorted(nodes.items())):
        columns[0].append(descriptor(key)); columns[1].append(s(record['sha']))
        columns[2].append(integer(len(record['reads'])))
        columns[3].extend(descriptor(key) for key, _ in record['reads'])
        if record['payload'] is not None:
            assert record['payload'] == record['sha']
            columns[4].append(integer(row))
    return tree_document([n(412, s('MLF-CRATE-QUERY-GRAPH-3'), s(config),
        l(*map(s, declarations)), l(l(integer(declarations.index(owner)))), l(), l(),
        *(l(*column) for column in columns))], 6)


class TemplateReceiptTests(unittest.TestCase):
    def check(self, f, mutate=None):
        with tempfile.TemporaryDirectory() as temp:
            args = write_fixture(Path(temp), f)
            if mutate:
                mutate(*args)
            return check_receipts(*args)

    def reject(self, f, message):
        with self.assertRaisesRegex(Invalid, message):
            self.check(f)

    def test_signed_template_retains_real_payload_with_monomorphic_dependencies(self):
        f = signed_fixture()
        self.assertEqual(self.check(f), dict(retained=1, rewritten=0, template_groups=[f['group']]))
        f['mode'] = 'concrete'
        self.reject(f, 'finish receipt commitment')

    def unsigned_monomorphic_fixture(self):
        f = signed_fixture()
        signed = unpack(f['references'][2][0][2][1][1])
        f['references'] = l(n(2, s('checked-inference-template-1'), s(pack([
            'checked-inference-template-1', *signed[2:]]))))
        return f

    def test_unsigned_template_accepts_nonempty_monomorphic_dependencies(self):
        # The producer admits any nonempty dependency inventory, not only forall.
        f = self.unsigned_monomorphic_fixture()
        self.assertEqual(self.check(f), dict(retained=1, rewritten=0, template_groups=[f['group']]))
        f['mode'] = 'concrete'
        self.reject(f, 'finish receipt commitment')

    def test_unsigned_template_rejects_empty_dependency_inventory(self):
        f = self.unsigned_monomorphic_fixture()
        key = unpack(f['references'][2][0][2][1][1]); key[2] = ''
        f['raw_refs'] = []
        f['references'] = l(n(2, s('checked-inference-template-1'), s(pack(key))))
        with self.assertRaisesRegex(Invalid, 'template dependency scheme inventory'):
            rebind_template(f['references'], f['original'], [], [f['owner']], f['types'])

    def test_unsigned_template_rejects_missing_and_extra_dependency_schemes(self):
        for count in (1, 3):
            f = self.unsigned_monomorphic_fixture()
            key = unpack(f['references'][2][0][2][1][1])
            schemes = unpack(key[2]); key[2] = pack((schemes * 2)[:count])
            f['references'] = l(n(2, s('checked-inference-template-1'), s(pack(key))))
            self.reject(f, 'template dependency scheme inventory')

    def test_unsigned_monomorphic_template_keeps_scheme_and_expression_checks(self):
        f = self.unsigned_monomorphic_fixture()
        f['types']['App.left'] = n(44, s('Bool'), l())
        self.reject(f, 'template dependency scheme mismatch')
        f = self.unsigned_monomorphic_fixture()
        key = unpack(f['references'][2][0][2][1][1]); key[3] = pack(['variable', '2'])
        f['references'] = l(n(2, s('checked-inference-template-1'), s(pack(key))))
        self.reject(f, 'template variable slot')

    def test_signed_signature_must_match_owned_type(self):
        f = signed_fixture()
        key = unpack(f['references'][2][0][2][1][1])
        key[1] = pack(['annotation', '', pack(['constructor', 'Bool', ''])])
        f['references'] = l(n(2, s('checked-inference-template-1'), s(pack(key))))
        self.reject(f, 'template declaration signature mismatch')

    def test_signed_template_rejects_existentials_open_types_and_empty_dependencies(self):
        integer = pack(['constructor', 'Int', ''])
        for annotation in [pack(['annotation', pack(['a']), integer]),
                           pack(['annotation', '', pack(['variable', 'a'])]),
                           pack(['annotation', '', pack(['bottom'])])]:
            f = signed_fixture(); key = unpack(f['references'][2][0][2][1][1]); key[1] = annotation
            f['references'] = l(n(2, s('checked-inference-template-1'), s(pack(key))))
            self.reject(f, 'template monomorphic annotation|template requires closed monotype')
        f = signed_fixture(); key = unpack(f['references'][2][0][2][1][1]); key[3] = ''
        f['raw_refs'] = []
        f['references'] = l(n(2, s('checked-inference-template-1'), s(pack(key))))
        with self.assertRaisesRegex(Invalid, 'template dependency scheme inventory'):
            rebind_template(f['references'], f['original'], [], [f['owner']], f['types'])

    def test_checked_expression_uses_closed_surface_monotype(self):
        integer = pack(['constructor', 'Int', ''])
        expression_key(pack(['checked', integer, pack(['variable', '0'])]), 1)
        with self.assertRaisesRegex(Invalid, 'closed monotype'):
            expression_key(pack(['checked', pack(['variable', 'a']), pack(['variable', '0'])]), 1)
        with self.assertRaisesRegex(Invalid, 'template variable slot'):
            expression_key(pack(['checked', integer, pack(['variable', '1'])]), 1)
        applied = pack(['application', pack(['constructor', 'List', '']), integer])
        self.assertEqual(monotype_key(applied), n(44, s('List'), l(n(44, s('Int'), l()))))

    def test_signed_structural_key_tag_and_field_count_are_exact(self):
        for key in [[], ['checked-signed-inference-template-1'],
                    ['checked-signed-inference-template-2', '', '', '']]:
            with self.assertRaisesRegex(Invalid, 'template structural key'):
                parse_template_key(pack(key))

    def test_retained_real_template_commitment_not_concrete_reserialization(self):
        f = fixture()
        self.assertEqual(self.check(f), dict(retained=1, rewritten=0, template_groups=[f['group']]))
        f['mode'] = 'concrete'
        self.reject(f, 'finish receipt commitment')

    def test_manually_authored_rebinding_golden_preserves_repeats_and_local_binder(self):
        f = fixture()
        p0, p1, owner, local = (binder(7, 'templateParameter0'), binder(11, 'templateParameter1'),
                                binder(19, 'templateOwner'), binder(41, 'untouchedLocal'))
        raw_body = n(75, owner, n(71, local, POLY,
            n(72, n(70, p0), n(72, n(70, p0), n(70, p1)))), n(82, s('()'), l()))
        f['original'] = n(400, s('raw'), s('template'), s('10-20'),
            l(n(2, p0, s('templateParameter0')), n(2, p1, s('templateParameter1'))),
            raw_body, l(n(2, owner, POLY)), l(p0, p1))
        # Every expected field is written independently: no rename helper is
        # used to produce this oracle's answer.
        a, b, result = binder(7, 'App.left'), binder(11, 'App.right'), binder(19, 'App.out')
        final_body = n(75, result, n(71, binder(41, 'untouchedLocal'), POLY,
            n(72, n(70, a), n(72, n(70, a), n(70, b)))), n(82, s('()'), l()))
        expected = (l(n(2, a, s('App.left')), n(2, b, s('App.right'))),
                    final_body, l(n(2, result, POLY)), l(a, b))
        self.assertEqual(rebind_template(f['references'], f['original'], f['raw_refs'],
                                        ['App.out'], f['types']), expected)
        f['final'] = n(401, s('group/App.out'), s('30-40'), l(), l(a, b),
                        final_body, l(result), l(a, b))
        self.assertEqual(self.check(f)['retained'], 1)

    def test_same_template_rebinds_distinct_owners_and_dependencies(self):
        a = fixture(); b = fixture('Other.renamed', ('Other.first', 'Other.second'))
        self.assertEqual((a['references'], a['original']), (b['references'], b['original']))
        self.assertNotEqual(a['final'], b['final'])
        self.assertEqual(self.check(a)['retained'], self.check(b)['retained'])

    def test_ordinary_path_keeps_strict_owner_and_stamp_commitment(self):
        f = fixture()
        ps, body, owned, uses = rebind_template(f['references'], f['original'], f['raw_refs'], [f['owner']], f['types'])
        f['references'] = l(*(n(2, s(k), s(v)) for k, v in f['raw_refs']))
        f['original'] = n(400, s('raw'), s(f['group']), f['final'][2][1], ps, body, owned, uses)
        self.assertEqual(self.check(f)['template_groups'], [])
        f['original'] = changed(f['original'], 1, s('other-owner'))
        self.reject(f, 'raw stage/owner')

    def test_wrong_template_owner_and_stage(self):
        for index, value, error in [(0, 'final', 'template stage/owner'), (1, 'other', 'raw stage/owner')]:
            f = fixture(); f['original'] = changed(f['original'], index, s(value))
            self.reject(f, error)

    def test_marker_key_context_and_scheme_corruptions(self):
        for references, error in [
            (l(), 'template reference inventory'),
            (l(n(2, s('wrong'), s(''))), 'template reference marker'),
            (l(n(2, s('checked-inference-template-1'), s(pack(['wrong'])))), 'template structural key'),
        ]:
            f = fixture(); f['references'] = references; self.reject(f, error)
        from artifact_binary_typed import unpack
        for index, value, error in [(1, pack(['d' * 64]), 'template datatype context'),
                                    (2, pack([TYPE_KEY]), 'template dependency scheme inventory'),
                                    (3, pack(['variable', '99']), 'template variable slot')]:
            f = fixture(); key = unpack(f['references'][2][0][2][1][1]); key[index] = value
            f['references'] = l(n(2, s('checked-inference-template-1'), s(pack(key))))
            self.reject(f, error)

    def test_wrong_dependency_scheme(self):
        f = fixture(); f['types']['App.left'] = n(44, s('Int'), l())
        self.reject(f, 'template dependency scheme mismatch')

    def test_canonical_hints_and_identity_collisions(self):
        f = fixture(); ps = list(items(f['original'][2][3])); b, ref = fields(ps[0], 2, 2)
        ps[0] = n(2, changed(b, 1, s('not-canonical')), ref)
        f['original'] = changed(f['original'], 3, l(*ps)); self.reject(f, 'template canonical parameter')
        f = fixture(); ps = list(items(f['original'][2][3])); b, ref = fields(ps[1], 2, 2)
        ps[1] = n(2, changed(b, 0, ('int', 7)), ref)
        f['original'] = changed(f['original'], 3, l(*ps)); self.reject(f, 'template binder collision')
        f = fixture(); owner, ty = fields(items(f['original'][2][5])[0], 2, 2)
        f['original'] = changed(f['original'], 5, l(n(2, changed(owner, 0, ('int', 7)), ty)))
        self.reject(f, 'template binder collision')

    def test_partial_hint_rebinding_wrong_uses_and_owner_spine(self):
        f = fixture(); body = f['original'][2][4]
        # Only one occurrence gets a new hint; declaration/uses remain canonical.
        application = body[2][1]
        application = changed(application, 0, n(70, binder(7, 'forged')))
        f['original'] = changed(f['original'], 4, changed(body, 1, application))
        self.reject(f, 'template use inventory|template inconsistent binder hint')
        f = fixture(); f['original'] = changed(f['original'], 6, l())
        self.reject(f, 'template use inventory')
        f = fixture(); f['original'] = changed(f['original'], 4, n(82, s('()'), l()))
        self.reject(f, 'template owned spine')

    def test_final_parameter_swap_cannot_define_its_own_mapping(self):
        f = fixture(); f['final'] = changed(f['final'], 3, l(*reversed(items(f['final'][2][3]))))
        self.reject(f, 'finish receipt commitment')

    def test_wrong_final_body_uses_and_export_type(self):
        for index, value in [(4, n(82, s('()'), l())), (6, l())]:
            f = fixture(); f['final'] = changed(f['final'], index, value)
            self.reject(f, 'finish receipt commitment')
        f = fixture(); f['types'][f['owner']] = n(44, s('Bool'), l())
        self.reject(f, 'retained export type')

    def test_rewritten_template_requires_concrete_commitment(self):
        f = fixture(); body = f['final'][2][4]
        f['final'] = changed(f['final'], 4, changed(body, 1, n(77, ('int', 5))))
        f['final'] = changed(f['final'], 6, l())
        self.reject(f, 'finish receipt commitment')
        f['mode'] = 'concrete'
        self.assertEqual(self.check(f), dict(retained=0, rewritten=1, template_groups=[f['group']]))

    def test_raw_and_finish_digests_are_rejected_even_under_python_O(self):
        def corrupt(prefix, cache, nodes):
            raw = next(v for k, v in nodes.items() if k.startswith('8:InferScc'))
            path = cache / 'query-graph-v2/results' / (raw['sha'] + '.mlfqr')
            path.write_bytes(path.read_bytes() + b'bad')
        with self.assertRaisesRegex(Invalid, 'raw payload commitment'):
            self.check(fixture(), corrupt)
        def finish(prefix, cache, nodes):
            for k, row in nodes.items():
                if k.startswith('9:FinishScc'):
                    old = row['sha']; row['sha'] = 'f' * 64
                    for dependent in nodes.values():
                        dependent['reads'] = [(k, row['sha']) if key == k and digest == old else (key, digest)
                                              for key, digest in dependent['reads']]
        with self.assertRaisesRegex(Invalid, 'finish receipt commitment'):
            self.check(fixture(), finish)

    def test_forged_templates_preserve_exact_graph_closure_for_actual_reader_controls(self):
        from artifact_binary_typed import unpack
        for version in (1, 2, 3):
            for mode in ('owner', 'member', 'source-key', 'scheme-key'):
                with self.subTest(version=version, mode=mode), tempfile.TemporaryDirectory() as temp:
                    prefix, cache, nodes = write_fixture(Path(temp), fixture())
                    directory = cache / 'query-graph-v2'
                    (directory / 'generations').mkdir()
                    raw = column_generation(nodes, 'App.out') if version == 3 else verify.index_bytes('fixture', nodes, version=version)
                    current = h(raw)
                    (directory / 'generations' / (current + '.mlfqg')).write_bytes(raw)
                    (directory / 'CURRENT').write_bytes(tree_document([s(current)], 6))
                    key = next(key for key in nodes if unpack(key)[0] == 'InferScc')
                    forged = forge_template_generation(cache, current, key, mode)
                    self.assertNotEqual(forged, current)
                    actual, damaged = verify.graph(cache)
                    self.assertEqual(actual, forged)
                    replacement = damaged[key]['sha']
                    self.assertEqual(damaged, verify.replace_result(nodes, key, replacement))
                    self.assertEqual((directory / 'generations' / (current + '.mlfqg')).read_bytes(), raw)
                    # Typed framing/closure remains valid. The source-key
                    # mismatch is intentionally left to the actual compiler's
                    # current-source admission rather than a self-attested key.

    def test_signed_template_attacks_preserve_v3_graph_and_target_fields(self):
        from query_generation import Generation
        for mode in ('owner', 'member', 'source-key', 'scheme-key', 'signature-key'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                f = signed_fixture(); prefix, cache, nodes = write_fixture(Path(temp), f)
                directory = cache / 'query-graph-v2'
                (directory / 'generations').mkdir()
                raw = column_generation(nodes, f['owner']); current = h(raw)
                (directory / 'generations' / (current + '.mlfqg')).write_bytes(raw)
                (directory / 'CURRENT').write_bytes(tree_document([s(current)], 6))
                key = pack(['InferScc', pack([f['owner']])])
                forged = forge_template_generation(cache, current, key, mode)
                actual = Generation((directory / 'generations' / (forged + '.mlfqg')).read_bytes())
                self.assertEqual(actual.version, 3)
                self.assertEqual(actual.nodes, verify.replace_result(nodes, key, actual.nodes[key]['sha']))
                payload = (directory / 'results' / (actual.nodes[key]['sha'] + '.mlfqr')).read_bytes()
                refs, original = fields(read_document(payload, 6).values()[0], 425, 2)
                if mode.endswith('-key'):
                    previous = unpack(f['references'][2][0][2][1][1])
                    changed_key = unpack(refs[2][0][2][1][1])
                    offset = {'signature-key': 1, 'scheme-key': 3, 'source-key': 4}[mode]
                    self.assertNotEqual(previous[offset], changed_key[offset])
                    previous[offset] = changed_key[offset]
                    self.assertEqual(previous, changed_key)
                    self.assertEqual(original, f['original'])

    def test_raw_edge_inventory_cannot_be_redefined_by_final_references(self):
        def reordered(prefix, cache, nodes):
            raw = next(row for key, row in nodes.items() if key.startswith('8:InferScc'))
            raw['reads'][:2] = list(reversed(raw['reads'][:2]))
        with self.assertRaisesRegex(Invalid, 'raw prepared/scope edges'):
            self.check(fixture(), reordered)
        def duplicate(prefix, cache, nodes):
            raw = next(row for key, row in nodes.items() if key.startswith('8:InferScc'))
            raw['reads'][3] = raw['reads'][2]
        with self.assertRaisesRegex(Invalid, 'template duplicate binding edge'):
            self.check(fixture(), duplicate)

    def test_template_stamp_has_only_syntax_evidence_in_pure_oracle(self):
        # This explicit boundary prevents the lightweight fixture from being
        # reported as proof of content-stamp validity. verify.main separately
        # demands rejection by both real normal and semantic-audit link paths.
        f = fixture(); f['final'] = changed(f['final'], 1, s('123-456'))
        self.assertEqual(self.check(f)['retained'], 1)
        f['final'] = changed(f['final'], 1, s('not-a-stamp'))
        from artifact_binary_open import OpenPairError
        with self.assertRaisesRegex(OpenPairError, 'malformed open fragment stamp'):
            self.check(f)

    def test_wrong_stamp_fixture_changes_only_stamp_and_outer_object_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            f = fixture(); prefix, _, _ = write_fixture(Path(temp), f)
            pair = tuple(prefix.with_suffix(ext).read_bytes() for ext in ('.mlfci', '.mlfco'))
            corrupted = wrong_template_stamp(pair, f['group'])
            before, after = [list(fields(read_document(x, 3).values()[0], 242, 13)) for x in (pair[0], corrupted[0])]
            before[11] = after[11]
            self.assertEqual(before, after)
            self.assertEqual(after[11], s(h(corrupted[1])))
            before, after = [open_document(x)[2] for x in (pair[1], corrupted[1])]
            self.assertEqual(before[:5], after[:5])
            a, b = [list(fields(items(x[5])[0], 401, 7)) for x in (before, after)]
            self.assertNotEqual(a[1], b[1]); a[1] = b[1]
            self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()
