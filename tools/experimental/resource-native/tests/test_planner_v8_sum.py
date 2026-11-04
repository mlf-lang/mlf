"""Synthetic SUM planner/checker/emitter tests, not genuine source acceptance.

No GHC, C compiler, original evaluator or native process is started here. Source
replay negatives have their own suite; these tests independently join source
arms, declaration variants, factory bindings and public metadata Sites.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE / 'tests')]
import planner_v8 as planner
import module_shared_transport as transport
import test_planner_v8 as f
import test_module_shared_transport as s
from test_planner_v8_placement import COARSE_GOLDENS
from test_shared_source_native import at, instruction
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime
from resource_ir_v8.program_schema import ResourceError


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def wrap(body, variants=(('Empty', ()), ('Number', (f.I,))), name='Choice'):
    return f.with_data([s.sum_decl(name, variants)], body)


def case(value, arms=None):
    return s.sum_case(value, arms)


def balanced(values):
    if len(values) == 1:
        return values[0]
    middle = len(values) // 2
    return f.add(balanced(values[:middle]), balanced(values[middle:]))


def captures_fixture(count):
    body = case(f.construct('Empty'), [s.sum_arm('Empty', (), balanced([f.var(i) for i in range(100, 100+count)])),
                                     s.sum_arm('Number', (2,), f.var(2))])
    for i in reversed(range(100, 100+count)):
        body = f.let(i, f.lit(1), body)
    return wrap(body)


class SumPlannerTests(unittest.TestCase):
    def checked(self, raw, groups=False):
        before = copy.deepcopy(raw)
        result = planner.plan_fragment(raw, data_groups=groups)
        self.assertEqual(raw, before)
        self.assertFalse(result['binding']['source_admitted'])
        self.assertFalse(result['binding']['ordinary_K_checked'])
        self.assertEqual(result['binding']['mode'], 'data-groups-prototype' if groups else 'coarse-owned')
        check_resources(result['program'])
        return result

    def mapped(self, result):
        maps = result['binding']['source_map']
        self.assertEqual(len(maps['sum_case_map']), 1)
        row = maps['sum_case_map'][0]
        return row, instruction(result['program'], row['factory'])

    def test_number_empty_both_modes_and_public_emission(self):
        for empty in (False, True):
            for groups in (False, True):
                with self.subTest(empty=empty, groups=groups):
                    r = self.checked(s.shared_sum(empty), groups)
                    p, m = r['program'], r['binding']['source_map']
                    ctor, = m['sum_constructor_map']
                    op = instruction(p, ctor['allocation'])
                    self.assertEqual(op['op'], 'construct_nullary' if empty else 'construct_sum')
                    self.assertEqual(op['variant'], 'V0' if empty else 'V1')
                    self.assertEqual(p['families'], {'F0': {'variants': ['V0', 'V1'], 'fields': {'V0': [], 'V1': ['#i64']}}})
                    self.assertEqual(op['in'], 'root')
                    row, factory = self.mapped(r)
                    self.assertEqual(instruction(p, row['allocation'])['in'], 'root')
                    self.assertEqual(factory['in'], '$home')
                    emission = emit_runtime(p)
                    self.assertEqual(json.loads(emission.canonical_ir_json), p)
                    self.assertEqual(emission.runtime_source.count('= rt8_case_fields_i64('), 1)
                    self.assertNotIn('= rt8_case_i64(', emission.runtime_source)

    def test_source_order_and_variant_order_have_distinct_site_joins(self):
        raw = wrap(case(f.construct('Number', f.lit())))
        raw['body']['alternatives'].reverse()
        r = self.checked(raw); row, op = self.mapped(r); p = r['program']
        self.assertEqual([(a['index'], a['variant']) for a in row['arms']], [(0, 1), (1, 0)])
        self.assertEqual(list(op['arms']), ['V0', 'V1'])
        metadata = json.loads(check_metadata(p).metadata_json)
        sites = [x for x in metadata['sites'] if x['path'] == row['factory']]
        self.assertEqual([x['arm'] for x in sites], [0, 1])
        self.assertEqual(len({x['id'] for x in sites}), 2)
        code_names = {x['id']: x['name'] for x in metadata['codes']}
        for arm in row['arms']:
            self.assertEqual(at(raw, arm['source']['path']), raw['body']['alternatives'][arm['index']]['body'])
            site, = [x for x in sites if x['arm'] == arm['variant']]
            self.assertEqual(code_names[site['code']], arm['code'])
            self.assertEqual(site['category'], 'THUNK')
            mapped, = [x for x in r['binding']['source_map']['allocation_map']
                       if x['instruction'] == row['factory'] and x.get('arm') == arm['variant']]
            self.assertEqual(mapped['source'], arm['source'])
            self.assertEqual(mapped['role'], 'case_fields_i64')

    def test_whole_arm_factory_not_eager_thunk_or_payload_force(self):
        r = self.checked(s.shared_sum()); row, op = self.mapped(r)
        body = r['program']['codes'][row['code']]['body']
        self.assertEqual([x['op'] for x in body].count('force'), 1)  # scrutinee only
        self.assertFalse(any(x['op'] in ('thunk', 'application', 'prim2', 'field') for x in body))
        self.assertEqual(set(op['arms']), {'V0', 'V1'})
        self.assertEqual(len({a['code'] for a in row['arms']}), 2)
        for arm in row['arms']:
            self.assertTrue(any(x['op'] == 'thunk' for x in r['program']['codes'][arm['code']]['body']))
        drop = instruction(r['program'], row['drop_scrutinee'])
        self.assertEqual(drop, {'op': 'drop', 'value': op['scrutinee']})
        self.assertGreater(row['drop_scrutinee']['segments'][0], row['factory']['segments'][0])

    def test_wildcards_keep_all_payloads_but_do_not_bind_or_force_them(self):
        raw = wrap(case(f.construct('Pair', f.lit(1), f.add(f.lit(2), f.lit(3))),
                   [s.sum_arm('Empty', (), f.lit()), s.sum_arm('Pair', (10, None), f.var(10))]),
                   (('Empty', ()), ('Pair', (f.I, f.I))))
        r = self.checked(raw); row, op = self.mapped(r)
        ctor = instruction(r['program'], r['binding']['source_map']['sum_constructor_map'][0]['allocation'])
        self.assertEqual(len(ctor['fields']), 2)
        self.assertEqual(list(op['arms']['V1']['captures'].values()), [{'kind': 'field', 'index': 0}])
        self.assertEqual([x['index'] for x in row['arms'][1]['field_captures']], [0])
        self.assertEqual(sum(x['op'] == 'force' for x in r['program']['codes'][row['code']]['body']), 1)

    def test_field_index_ten_is_numeric_and_bool_contract_is_exact(self):
        variants = (('Empty', ()), ('Wide', (f.I,) * 10 + (f.B,)))
        arm = s.sum_arm('Wide', (None,) * 10 + (20,), f.choose(f.var(20), f.lit(), f.lit(0)))
        r = self.checked(wrap(case(f.construct('Wide', *[f.lit(i) for i in range(10)], f.boolean()),
                             [s.sum_arm('Empty', (), f.lit()), arm]), variants))
        row, op = self.mapped(r); binding, = op['arms']['V1']['captures'].values()
        self.assertEqual(binding, {'kind': 'field', 'index': 10})
        field, = row['arms'][1]['field_captures']
        self.assertEqual(r['program']['types'][field['type']], {'tag': 'closed', 'layout': '#bool'})
        self.assertEqual(r['program']['codes'][row['arms'][1]['code']]['captures'][field['capture']]['relation'], 'down')

    def test_32_fields_32_external_and_total_64_are_independent_limits(self):
        raw = wrap(case(f.construct('Wide', *[f.lit(i) for i in range(32)]),
                   [s.sum_arm('Empty', (), f.lit()), s.sum_arm('Wide', tuple(range(100,132)), f.var(100))]),
                   (('Empty', ()), ('Wide', (f.I,) * 32)))
        r = self.checked(raw); row, op = self.mapped(r)
        self.assertEqual(len(op['arms']['V1']['captures']), 32)
        self.assertEqual(len(row['arms'][1]['field_captures']), 32)
        r = self.checked(captures_fixture(32)); _, op = self.mapped(r)
        self.assertEqual(len(op['arms']['V0']['captures']), 32)
        with self.assertRaisesRegex(planner.PlanningError, 'external capture count exceeds32'):
            planner.plan_fragment(captures_fixture(33))

    def test_64_capture_factory_and_32_field_ordinal_boundary(self):
        variants = (('Empty', ()), ('Wide', (f.I,) * 32))
        body = case(f.construct('Wide', *[f.lit(i) for i in range(32)]),
                    [s.sum_arm('Empty', (), f.lit()),
                     s.sum_arm('Wide', tuple(range(200,232)),
                               balanced([f.var(i) for i in range(100,132)]))])
        for ident in reversed(range(100,132)):
            body = f.let(ident, f.lit(1), body)
        r = self.checked(wrap(body, variants)); row, op = self.mapped(r)
        bindings = op['arms']['V1']['captures']
        self.assertEqual(len(bindings), 64)
        self.assertEqual(sum(x['kind'] == 'external' for x in bindings.values()), 32)
        self.assertEqual([x['index'] for x in bindings.values() if x['kind'] == 'field'], list(range(32)))
        bad = copy.deepcopy(r['program']); factory = instruction(bad, row['factory'])
        field = next(n for n,x in factory['arms']['V1']['captures'].items() if x.get('index') == 31)
        factory['arms']['V1']['captures'][field]['index'] = 32
        with self.assertRaises(ResourceError): check_resources(bad)

    def test_dead_formal_shared_views_remain_distinct_in_each_arm(self):
        arm_body = f.add(f.app(f.use(1,f.I,f.I),f.lit(20)), f.app(f.use(1,f.I,f.B),f.lit(22)))
        body = case(f.construct('Empty'), [s.sum_arm('Empty', (), arm_body),
                    s.sum_arm('Number', (3,), copy.deepcopy(arm_body))])
        raw = wrap(f.let(1,f.prefix([100,101],f.lam(2,f.ty(100),f.var(2))),body))
        r = self.checked(raw); p = r['program']
        vectors = [[p['types'][t]['layout'] for t in x['arguments']] for x in p['instantiations'].values()]
        self.assertCountEqual(vectors,[['#i64','#i64'],['#i64','#bool']])
        self.assertEqual(len(r['binding']['source_map']['use_map']),4)
        for carrier in r['binding']['source_map']['carrier_map']:
            if carrier['kind'] == 'sum-arm':
                views = carrier['view_captures']; self.assertEqual(len(views),2)
                self.assertEqual(views[0]['layout'],views[1]['layout'])
                self.assertNotEqual(views[0]['arguments'],views[1]['arguments'])
                self.assertNotEqual(views[0]['capture'],views[1]['capture'])

    def test_old_data_opt_in_complete_outputs_unchanged(self):
        # Canonical complete Stage09 outputs, including maps/work, from its
        # unmodified planner49b6f88a; no runtime/code oracle is imported.
        expected = {
            'scalar_box':'2f30dfed64b3ad2982cfbf3d9b6a45771a5d831c4e66bfdc42510f9fe691c1f0',
            'callable_box':'73ea5e9566631c06f82ed429b58b151df0f28390864b292291c5f35d7aa7dc6c',
            'curried_box':'448dac6c37176edd1bb847baa57d95b1b98d26e3e1dad63e07257e1d81c66609'}
        for name,digest in expected.items():
            with self.subTest(name=name):
                r = planner.plan_fragment(getattr(f,name)(),data_groups=True)
                self.assertEqual(hashlib.sha256(canonical(r)).hexdigest(),digest)
                self.assertNotIn('sum_map',r['binding']['source_map'])

    def test_duplicate_external_uses_deduplicate_capture_not_source_terms(self):
        raw = wrap(f.let(100, f.add(f.lit(20), f.lit(1)), case(f.construct('Empty'),
              [s.sum_arm('Empty', (), f.add(f.var(100), f.var(100))), s.sum_arm('Number', (2,), f.var(2))])))
        r = self.checked(raw); row, op = self.mapped(r)
        self.assertEqual(len(op['arms']['V0']['captures']), 1)
        arm = row['arms'][0]
        self.assertEqual(len(r['program']['codes'][arm['code']]['captures']), 1)
        source_uses = [x for x in r['binding']['source_map']['term_map'] if x.get('binder') == 100 and x['tag'] == 'var']
        self.assertEqual(len(source_uses), 2)

    def test_closed_callable_external_keeps_full_contract(self):
        raw = wrap(f.let(100, f.lam(101, f.I, f.var(101)), case(f.construct('Empty'),
              [s.sum_arm('Empty', (), f.app(f.var(100), f.lit())), s.sum_arm('Number', (2,), f.var(2))])))
        r = self.checked(raw); row, op = self.mapped(r)
        capture, = r['program']['codes'][row['arms'][0]['code']]['captures'].values()
        typ = r['program']['types'][capture['layout'][1:]]
        self.assertEqual((typ['tag'], typ['protocol'], typ['result_identity']), ('arrow', 'repeat', 'unknown'))
        self.assertEqual(list(op['arms']['V0']['captures'].values())[0]['kind'], 'external')

    def test_full_shared_pairs_case_union_and_per_arm_captures(self):
        r = self.checked(s.shared_sum()); p = r['program']; row, _ = self.mapped(r)
        self.assertEqual(len(p['schemes']), 1)
        self.assertEqual([[p['types'][t]['layout'] for t in x['arguments']] for x in p['instantiations'].values()], [['#bool'], ['#i64']])
        maps = r['binding']['source_map']; self.assertEqual(len(maps['use_map']), 4)
        self.assertEqual(sum(x['op'] == 'instantiate' for x in f.instructions(p)), 2)
        outer, = [x for x in maps['carrier_map'] if x['kind'] == 'sum-case']
        self.assertEqual(len(outer['view_captures']), 2)
        arms = [x for x in maps['carrier_map'] if x['kind'] == 'sum-arm']
        self.assertEqual(len(arms), 2)
        for arm in arms:
            self.assertEqual(len(arm['view_captures']), 2)
            self.assertTrue(all(x['source_view']['kind'] == 'captured' for x in arm['view_captures']))

    def test_all_nullary_uses_factories_and_never_nullary_data(self):
        r = self.checked(wrap(case(f.construct('Left'), [s.sum_arm('Right', (), f.lit(0)), s.sum_arm('Left', (), f.lit())]),
                              (('Left', ()), ('Right', ()))))
        row, op = self.mapped(r)
        self.assertEqual(list(op['arms']), ['V0', 'V1'])
        self.assertTrue(all(not a['captures'] for a in row['arms']))
        self.assertEqual(instruction(r['program'], r['binding']['source_map']['sum_constructor_map'][0]['allocation'])['op'], 'construct_nullary')
        self.assertFalse(r['program']['layouts'])

    def test_equal_field_layouts_never_merge_nominal_family_identity(self):
        a = s.sum_decl('A', (('A0', ()), ('A1', (f.I,))))
        b = s.sum_decl('B', (('B0', ()), ('B1', (f.I,))))
        raw = f.with_data([a,b], f.add(case(f.construct('A1', f.lit(21)),
              [s.sum_arm('A0', (), f.lit(0)), s.sum_arm('A1', (1,), f.var(1))]),
              case(f.construct('B1', f.lit(21)), [s.sum_arm('B0', (), f.lit(0)), s.sum_arm('B1', (2,), f.var(2))])))
        r = self.checked(raw)
        self.assertEqual(set(r['program']['families']), {'F0','F1'})
        self.assertEqual({x['family'] for x in r['binding']['source_map']['sum_case_map']}, {'F0','F1'})

    def test_non_sum_coarse_golden_outputs_unchanged(self):
        for name, expected in COARSE_GOLDENS.items():
            with self.subTest(name=name):
                r = planner.plan_fragment(getattr(f, name)())
                self.assertEqual(hashlib.sha256(canonical(r)).hexdigest(), expected)
                self.assertNotIn('sum_map', r['binding']['source_map'])

    def test_claimed_sum_evidence_cannot_bypass_fresh_replay(self):
        raw = s.shared_sum(); fragment = transport.derive_shared_fragment(raw)
        fragment['nominal_sum']['cases'][0]['arms'][0]['variant'] = 1
        with self.assertRaises(transport.SharedTransportError):
            planner.plan_fragment(raw, fragment=fragment)

    def test_malformed_factory_ir_rejected_even_for_unselected_arm(self):
        good = self.checked(s.shared_sum(True)); row, _ = self.mapped(good)
        def change(kind):
            p = copy.deepcopy(good['program']); op = instruction(p, row['factory']); arm = op['arms']['V1']
            field = next(n for n,v in arm['captures'].items() if v['kind'] == 'field')
            if kind == 'missing': del op['arms']['V1']
            elif kind == 'extra': op['arms']['V2'] = copy.deepcopy(arm)
            elif kind == 'index': arm['captures'][field]['index'] = 1
            elif kind == 'bool_index': arm['captures'][field]['index'] = True
            elif kind == 'field_type': p['codes'][arm['code']]['captures'][field]['layout'] = '#bool'
            elif kind == 'field_relation': p['codes'][arm['code']]['captures'][field]['relation'] = 'below'
            elif kind == 'external':
                key = next(n for n,v in arm['captures'].items() if v['kind'] == 'external')
                arm['captures'][key]['value'] = 'unknown_owner'
            elif kind == 'code': arm['code'] = 'missing_code'
            return p
        for kind in ('missing','extra','index','bool_index','field_type','field_relation','external','code'):
            with self.subTest(kind=kind):
                bad = change(kind)
                with self.assertRaises(ResourceError): check_resources(bad)
                with self.assertRaises(ResourceError): check_metadata(bad)


if __name__ == '__main__':
    unittest.main()
