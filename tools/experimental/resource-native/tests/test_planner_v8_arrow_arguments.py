"""Bounded closed-arrow-coordinate planner checks; synthetic unless pinned.

These are host replay/resource/metadata/emission checks, never compiler or native
execution. Retained raw captures remain diagnostic evidence, not JSON authority.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE / 'tests')]
import planner_v8 as p
import module_shared_transport as m
import test_planner_v8 as f
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime

I, B = f.I, f.B
II, BB = f.arr(I, I), f.arr(B, B)


def identity_fixture():
    return f.let(1, f.prefix([100], f.lam(2, f.ty(100), f.var(2))),
        f.let(3, f.lam(4, I, f.add(f.var(4), f.lit(21))),
            f.let(5, f.app(f.use(1, II), f.var(3)),
                f.choose(f.app(f.use(1, B), f.boolean()),
                    f.add(f.app(f.var(5), f.lit(0)), f.app(f.var(5), f.lit(0))), f.lit(0)))))


def apply_fixture():
    a, b = f.ty(100), f.ty(101)
    rhs = f.prefix([100, 101], f.lam(2, f.arr(a, b), f.lam(3, a, f.app(f.var(2), f.var(3)))))
    helper = f.lam(4, I, f.add(f.var(4), f.lit(21)))
    consumer = f.lam(5, II, f.add(f.app(f.var(5), f.lit(0)), f.app(f.var(5), f.lit(0))))
    gate = f.lam(6, I, f.prim(11, 'ltInt', f.var(6), f.lit(1)))
    return f.let(1, rhs, f.choose(f.app(f.app(f.use(1, I, B), gate), f.lit(0)),
        f.app(f.app(f.use(1, II, I), consumer), helper), f.lit(0)))


def captured_fixture():
    inner = f.app(f.app(f.use(1, II), f.lam(12, I, f.var(12))), f.var(10))
    carrier = f.lam(10, I, f.lam(11, B, inner))
    return f.let(1, f.prefix([100], f.lam(2, f.ty(100), f.var(2))),
                 f.app(f.app(carrier, f.lit()), f.boolean()))


def curried_arrow_fixture():
    rhs = f.prefix([100, 101], f.lam(2, f.ty(100), f.lam(3, f.ty(101), f.var(2))))
    partial = f.app(f.use(1, II, B), f.lam(4, I, f.var(4)))
    return f.let(1, rhs, f.let(5, partial, f.app(f.app(f.var(5), f.boolean()), f.lit())))


def recursive_view_fixture():
    import test_planner_v8_recursive_captures as r
    raw = r.fixture(scalar=False, view=True)
    # Change only the shared use in the recursive RHS, preserving the complete
    # typed knot and the Bool use outside it. This is synthetic raw source.
    pending = [raw]
    while pending:
        node = pending.pop()
        if type(node) is dict:
            if node == f.app(f.use(1, I), f.lit(21)):
                node.clear(); node.update(f.app(f.app(f.use(1, II), f.lam(70, I, f.var(70))), f.lit(21)))
            else:
                pending.extend(node.values())
        elif type(node) is list:
            pending.extend(node)
    return raw


def dead_fixture():
    rhs = f.prefix([100, 101], f.lam(2, f.ty(100), f.var(2)))
    body = f.add(f.app(f.use(1, I, II), f.lit(21)), f.app(f.use(1, I, BB), f.lit(21)))
    return f.let(1, rhs, f.app(f.lam(3, I, body), f.lit(0)))


def nominal_fixture(result=False):
    nominal = f.nominal('Box')
    typ = f.arr(I, nominal) if result else f.arr(nominal, I)
    helper = (f.lam(3, I, f.construct('Pack', f.var(3))) if result else
              f.lam(3, nominal, f.data_case(f.var(3), 'Pack', [4], f.var(4))))
    call = f.app(f.app(f.use(1, typ), helper), f.lit() if result else f.construct('Pack', f.lit()))
    body = f.data_case(call, 'Pack', [5], f.var(5)) if result else call
    return f.with_data([f.declaration('Box', 'Pack', I)],
        f.let(1, f.prefix([100], f.lam(2, f.ty(100), f.var(2))), body))


def nested_fixture():
    typ = f.arr(II, II)
    rhs = f.prefix([100], f.lam(2, f.ty(100), f.var(2)))
    value = f.lam(3, II, f.var(3))
    return f.let(1, rhs, f.app(f.app(f.app(f.use(1, typ), value), f.lam(4, I, f.var(4))), f.lit()))


def logical(program, name):
    t = program['types'][name]
    if t['tag'] == 'closed': return t['layout']
    if t['tag'] == 'rigid': return (t['scheme'], t['index'])
    return (logical(program, t['argument']), logical(program, t['result']), t['protocol'], t['result_identity'])


def vectors(program):
    return [[logical(program, x) for x in u['arguments']] for u in program['instantiations'].values()]


def guard():
    obj = object.__new__(p.Planner)
    obj.arrow_coordinates = True; obj._type_costs = {}; obj.work = 0
    obj.types = {}; obj.type_names = {}; obj.signatures = {}; obj.signature_names = {}; obj.nominal_layouts = {}
    return obj


def chain(arrows, base=None):
    t = p.SCALARS['Int'] if base is None else base
    for _ in range(arrows): t = p.arrow(p.SCALARS['Int'], t)
    return t


class ArrowCostTests(unittest.TestCase):
    def test_exact_depth32_and_substitution_depth33_rejection_before_construction(self):
        g = guard(); t = chain(31)
        self.assertEqual(g.type_cost(t)[0], 32)
        rigid = ('rigid', 'S', 0)
        with mock.patch.object(g, '_substitute', side_effect=AssertionError('construction entered')):
            with self.assertRaisesRegex(p.PlanningError, 'substituted logical type depth'):
                g.substitute(p.arrow(rigid, rigid), 'S', (t,))
        g = guard(); result = g.substitute(p.arrow(rigid, rigid), 'S', (chain(30),))
        self.assertEqual(g.type_cost(result)[0], 32)
        with self.assertRaisesRegex(p.PlanningError, 'logical type depth'):
            g.type_cost(chain(32))

    def test_shared_dag_cost_rejects_before_type_key_lookup(self):
        g = guard(); t = p.SCALARS['Int']
        for _ in range(24): t = p.arrow(t, t)
        class NoKeys(dict):
            def __contains__(self, key): raise AssertionError('structural hashing entered')
        g.type_names = NoKeys()
        with self.assertRaisesRegex(p.PlanningError, 'work limit'): g.type_name(t)
        self.assertLess(g.work, 100)
        self.assertEqual(len(g._type_costs), 25)
        self.assertTrue(all(k == id(row[0]) for k, row in g._type_costs.items()))
        self.assertFalse(g.types)

    def test_repeated_rigids_preflight_expanded_result_without_expansion(self):
        g = guard(); rigid = ('rigid', 'S', 0); t = rigid
        for _ in range(14): t = p.arrow(t, t)
        with mock.patch.object(g, '_substitute', side_effect=AssertionError('construction entered')):
            with self.assertRaisesRegex(p.PlanningError, 'work limit'):
                g.substitute(t, 'S', (chain(10),))
        self.assertLess(g.work, 300)

    def test_dead_vector_hash_and_sort_work_is_charged_before_traversal(self):
        t = p.SCALARS['Int']
        for _ in range(20): t = p.arrow(t, t)
        for operation in (lambda g: g.pair_work((7, (p.SCALARS['Int'], t))),
                          lambda g: g.sorted_pairs([(7, (t,)), (8, (t,))]),
                          lambda g: g.same_type(t, t)):
            g = guard()
            with self.assertRaisesRegex(p.PlanningError, 'work limit'): operation(g)
            self.assertLess(g.work, 100)

    def test_type_count4096_is_separate_from_depth_and_expanded_cost(self):
        g = guard(); g.types = {str(i): {} for i in range(p.MAX_TYPES-1)}
        g.type_name(p.SCALARS['Int']); self.assertEqual(len(g.types), p.MAX_TYPES)
        before = copy.deepcopy(g.types)
        with self.assertRaisesRegex(p.PlanningError, 'type count'): g.type_name(p.SCALARS['Bool'])
        self.assertEqual(g.types, before)

    def test_complete_repeat_unknown_closed_domain_only(self):
        g = guard(); nominal = ('nominal', 0, 'Box', ('declarations', '0')); g.nominal_layouts[nominal] = 'D0'
        self.assertTrue(g.closed_argument(p.arrow(p.SCALARS['Int'], nominal)))
        self.assertFalse(g.closed_argument(p.arrow(('rigid', 'S', 0), p.SCALARS['Int'])))
        self.assertFalse(g.closed_argument(p.arrow(('nominal', 1, 'Other', ('declarations', '1')), p.SCALARS['Int'])))
        for protocol, identity in [('once', 'unknown'), ('repeat', 'argument')]:
            with self.assertRaisesRegex(p.PlanningError, 'callable contract'):
                g.closed_argument(('arrow', p.SCALARS['Int'], p.SCALARS['Int'], protocol, identity))

    def test_old_path_adds_no_guard_work_or_reorders_pairs(self):
        g = guard(); g.arrow_coordinates = False
        before = g.work
        self.assertTrue(g.same_type(p.SCALARS['Int'], p.SCALARS['Int']))
        pairs = [(3, (p.SCALARS['Bool'],)), (2, (p.SCALARS['Int'],))]
        self.assertEqual(g.sorted_pairs(pairs), sorted(pairs)); g.pair_work(pairs[0]); g.structural_work(chain(2))
        self.assertTrue(g.same_pairs(pairs, pairs)); self.assertEqual(g.work, before)


class ArrowPlannerTests(unittest.TestCase):
    def checked(self, raw, groups=False):
        result = p.plan_fragment(raw, data_groups=groups)
        check_resources(result['program']); check_metadata(result['program'])
        generated = emit_runtime(result['program'])
        self.assertEqual(json.loads(generated.canonical_ir_json), result['program'])
        self.assertFalse(result['binding']['source_admitted'])
        return result

    def test_identity_and_nonidentity_higher_order_body_keep_full_graph(self):
        for make in (identity_fixture, apply_fixture):
            for groups in (False, True):
                raw = make(); result = self.checked(raw, groups); program = result['program']; mapping = result['binding']['source_map']
                self.assertEqual(len(program['schemes']), 1); self.assertEqual(len(program['instantiations']), 2)
                self.assertTrue(any(isinstance(t, tuple) for vector in vectors(program) for t in vector))
                self.assertEqual(len(mapping['term_map']), len(m.derive_shared_fragment(raw)['term_correspondence']))
                self.assertEqual(len(mapping['scheme_map']), 1)
                for typ in program['types'].values():
                    if typ['tag'] == 'arrow':
                        self.assertEqual((typ['protocol'], typ['result_identity']), ('repeat', 'unknown'))

    def test_dead_arrow_coordinates_do_not_merge_equal_return_types(self):
        for groups in (False, True):
            result = self.checked(dead_fixture(), groups); program = result['program']
            carrier = next(x for x in result['binding']['source_map']['carrier_map'] if len(x['view_captures']) == 2)
            a, b = carrier['view_captures']; self.assertEqual(a['layout'], b['layout'])
            self.assertNotEqual(a['arguments'], b['arguments']); self.assertNotEqual(a['capture'], b['capture'])
            self.assertNotEqual(vectors(program)[0], vectors(program)[1])

    def test_saved_view_retains_complete_arrow_vector_and_support(self):
        for groups in (False, True):
            result = self.checked(captured_fixture(), groups)
            rows = [x for c in result['binding']['source_map']['carrier_map'] for x in c['view_captures']]
            self.assertTrue(any(x['source_view']['kind'] == 'scheme' for x in rows))
            self.assertTrue(any(x['source_view']['kind'] == 'captured' for x in rows))
            self.assertTrue(all(x['arguments'] == rows[0]['arguments'] and x['layout'] == rows[0]['layout'] for x in rows))
            self.assertTrue(all(x['relation'] == ('below' if groups else 'down') for x in rows))
            program = result['program']
            bad = copy.deepcopy(program)
            row = next(c for c in result['binding']['source_map']['carrier_map'] if c['view_captures'])
            capture = row['view_captures'][0]
            if not groups:
                bad['functions'][row['ir_code']]['captures'][capture['capture']]['relation'] = 'below'
                with self.assertRaises(ValueError): check_resources(bad)

    def test_curried_instance_child_with_arrow_coordinate(self):
        for groups in (False, True):
            result = self.checked(curried_arrow_fixture(), groups); program = result['program']
            self.assertEqual(vectors(program), [[('#i64', '#i64', 'repeat', 'unknown'), '#bool']])
            meta = json.loads(check_metadata(program).metadata_json)
            children = [x for x in meta['site_executions'] if x['origin_kind'] == 'INSTANCE']
            self.assertTrue(children)
            coordinate = next(t['id'] for t in meta['types'] if t['tag'] == 'arrow' and
                meta['types'][t['argument']]['atom'] == '#i64' and
                meta['types'][t['result']]['atom'] == '#i64')
            captured = [x for x in meta['code_executions'] if meta['codes'][x['code']]['scope'] is not None and
                        any(c['type'] == coordinate for c in x['captures'])]
            self.assertTrue(captured)
            self.assertTrue(any(child['code_execution'] == execution['id'] and
                                child['env'] == execution['env']
                                for child in children for execution in captured))
            self.assertTrue(all(c['relation'] == 'down' for x in captured for c in x['captures']))
            self.assertEqual(len(result['binding']['source_map']['scheme_map']), 1)
            self.assertTrue(all(t['result_identity'] == 'unknown'
                                for t in program['types'].values() if t['tag'] == 'arrow'))

    def test_recursive_saved_view_preserves_arrow_coordinate_pair(self):
        for groups in (False, True):
            result = self.checked(recursive_view_fixture(), groups)
            knot, = result['binding']['source_map']['knot_map']
            view, = knot['captures']['views']
            self.assertEqual(view['arguments'], [II])
            rows = [r for c in result['binding']['source_map']['carrier_map'] for r in c['view_captures']]
            self.assertTrue(any(r['source_view']['kind'] == 'captured' for r in rows))
            self.assertEqual(len(result['program']['schemes']), 1)

    def test_recursive_mixed_dead_vectors_keep_distinct_complete_pairs(self):
        import test_planner_v8_recursive_captures as r
        raw = r.fixture(scalar=False, view=True, dead=True)
        pending = [raw]; changed = 0
        while pending:
            node = pending.pop()
            if type(node) is dict:
                if node == f.use(1, I, I):
                    node.clear(); node.update(f.use(1, I, II)); changed += 1
                else:
                    pending.extend(node.values())
            elif type(node) is list:
                pending.extend(node)
        self.assertEqual(changed, 1)
        for groups in (False, True):
            result = self.checked(raw, groups)
            knot, = result['binding']['source_map']['knot_map']
            self.assertEqual([v['arguments'] for v in knot['captures']['views']], [[I, II], [I, B]])
            self.assertEqual(len(result['program']['instantiations']), 3)

    def test_exact_nominal_leaves_and_nested_arrows(self):
        for raw in (nominal_fixture(), nominal_fixture(True), nested_fixture()):
            for groups in (False, True): self.checked(raw, groups)

    def test_scheme_binder_identity_is_not_result_type_identity(self):
        rhs1 = f.prefix([100], f.lam(3, f.ty(100), f.var(3)))
        rhs2 = f.prefix([101], f.lam(4, f.ty(101), f.var(4)))
        helper = lambda n: f.lam(n, I, f.var(n))
        raw = f.let(1, rhs1, f.let(2, rhs2, f.add(
            f.app(f.app(f.use(1, II), helper(5)), f.lit(21)),
            f.app(f.app(f.use(2, II), helper(6)), f.lit(21)))))
        result = self.checked(raw)
        self.assertEqual(len(result['program']['schemes']), 2)
        self.assertEqual(len({u['scheme'] for u in result['program']['instantiations'].values()}), 2)
        self.assertEqual(len({r['binder'] for r in result['binding']['source_map']['scheme_map']}), 2)

    def test_changed_coordinates_and_full_callable_types_reject(self):
        raw = identity_fixture(); fragment = m.derive_shared_fragment(raw)
        for typ in (BB, f.arr(I, f.nominal('Foreign')), f.arr(I, f.ty(999))):
            bad = copy.deepcopy(fragment)
            row = next(x for x in bad['polymorphism']['uses'] if x['arguments'] == [II]); row['arguments'] = [typ]
            with self.assertRaises(p.PlanningError): p.Planner(bad).finish()
            with self.assertRaises(m.SharedTransportError): p.plan_fragment(raw, fragment=bad)

    def test_retained_actual_unannotated_captures(self):
        root = os.environ.get('IR8_ARROW_ARGUMENTS_ROOT')
        if not root: self.skipTest('retained Stage23 capture root not configured')
        pins = {'shared-id-arrow': 'bd430a27d03287b544890d825a5f75902629e14980a6dfb7674bd1b6a3e0066d',
                'shared-apply-arrow': '1108bb4359def06dfaee507f314720459657f4808fecd1e4a6395ceb2c2cdc69'}
        for case, sha in pins.items():
            blob = (Path(root)/f'capture-{case}01/capture.stdout').read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), sha)
            raw = json.loads(blob)['projection']['projected_annotated']
            for groups in (False, True):
                result = self.checked(raw, groups)
                self.assertEqual(len(result['program']['schemes']), 1)
                self.assertEqual(len(result['program']['instantiations']), 2)

    def test_retained_instance_graphs_are_fresh_replay_not_old_producer_admission(self):
        root = os.environ.get('IR8_ARROW_ARGUMENTS_ROOT')
        if not root: self.skipTest('retained Stage23 capture root not configured')
        pins = {'shared-id-instance': 'a73e7e87b3695a7101579f5d8ce1d793df95d29d186b522d9f1781841766db2d',
                'shared-apply-instance': '6deda5e135a4d52dc350a6d17d76855ee68c35d56bfaa88bf2b50ef2819db35e'}
        for case, sha in pins.items():
            blob = (Path(root)/f'capture-{case}01/capture.stdout').read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), sha)
            capture = json.loads(blob); raw = capture['projection']['projected_annotated']
            # In particular, the old producer's C normalization is not used as
            # authority for the newly replayed direct arrow beta.
            for groups in (False, True):
                result = self.checked(raw, groups); program = result['program']
                self.assertTrue(program['schemes'])
                self.assertTrue(any(isinstance(t, tuple) for vector in vectors(program) for t in vector))
                for use in program['instantiations'].values():
                    self.assertEqual(len(use['arguments']), program['schemes'][use['scheme']]['parameters'])

    def test_old_stage21_and22_complete_plans_and_emission_are_exact(self):
        from test_planner_v8_nominal_callable_captures import files
        roots = [(os.environ.get('IR8_NOMINAL_SHARED_ARGUMENTS_ROOT'), ('identity', 'curried-const')),
                 (os.environ.get('IR8_HIGHER_ORDER_SHARED_ROOT'), ('shared-apply', 'shared-apply-cross'))]
        if any(not root for root, _ in roots): self.skipTest('retained Stage21/22 roots not configured')
        for root, cases in roots:
            root = Path(root)
            for case in cases:
                if case in ('identity', 'curried-const'):
                    cap = root/f'capture-{case}02/capture.stdout'; directory = root/'host-plan01'/case
                else:
                    cap = root/('capture-shared-apply01' if case == 'shared-apply' else 'capture-shared-apply-cross02')/'capture.stdout'
                    directory = root/('host-plan01' if case == 'shared-apply' else 'host-plan-b01')
                raw = json.loads(cap.read_bytes())['projection']['projected_annotated']
                for mode in ('coarse', 'groups'):
                    before = json.loads((directory/mode/'planned.json').read_bytes())
                    after = self.checked(raw, mode == 'groups'); self.assertEqual(after, before)
                    for name, blob in files(emit_runtime(after['program'])).items():
                        self.assertEqual(blob, (directory/mode/name).read_bytes())


if __name__ == '__main__': unittest.main()
