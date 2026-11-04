"""Synthetic finite self-SUM lowering; not source/K/native acceptance."""
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
from test_shared_source_native import instruction
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime
from resource_ir_v8.program_schema import ResourceError

SELF = f.nominal('IntList')


def declaration():
    return s.sum_decl('IntList', (('Nil', ()), ('Cons', (f.I, SELF))))


def fixture(lazy=False):
    if lazy:
        tail = f.app(f.lam(40, f.I, f.construct('Cons', f.var(40), f.construct('Nil'))),
                     f.add(f.lit(100), f.lit(23)))
        case = s.sum_case(f.var(12), [s.sum_arm('Nil', (), f.lit(0)),
                                    s.sum_arm('Cons', (20, None), f.var(20))])
    else:
        tail = f.construct('Cons', f.var(10), f.construct('Nil'))
        inner = s.sum_case(f.var(21), [s.sum_arm('Nil', (), f.var(20)),
                      s.sum_arm('Cons', (22, None), f.add(f.var(20), f.var(22)))])
        case = s.sum_case(f.var(12), [s.sum_arm('Nil', (), f.lit(0)),
                                    s.sum_arm('Cons', (20, 21), inner)])
    body = f.let(10, f.add(f.lit(20), f.lit(22 if lazy else 1)),
        f.let(11, tail, f.let(12, f.construct('Cons', f.var(10), f.var(11)),
            f.choose(f.app(f.use(1, f.B), f.boolean()), f.app(f.use(1, f.I), case), f.lit(0)))))
    return f.with_data([declaration()], f.let(1, f.prefix([100], f.lam(2, f.ty(100), f.var(2))), body))


class RecursiveSumPlannerTests(unittest.TestCase):
    def checked(self, raw, groups=False):
        before = copy.deepcopy(raw)
        result = planner.plan_fragment(raw, data_groups=groups)
        self.assertEqual(raw, before)
        self.assertFalse(result['binding']['source_admitted'])
        self.assertFalse(result['binding']['ordinary_K_checked'])
        check_resources(result['program'])
        return result

    def test_nested_and_lazy_both_modes_use_finite_nominal_atom(self):
        for lazy in (False, True):
            for groups in (False, True):
                with self.subTest(lazy=lazy, groups=groups):
                    r = self.checked(fixture(lazy), groups)
                    p, m = r['program'], r['binding']['source_map']
                    self.assertEqual(p['families'], {'F0': {'variants':['V0','V1'],
                                     'fields':{'V0':[], 'V1':['#i64','%F0']}}})
                    self.assertEqual(len(m['sum_constructor_map']), 3)
                    self.assertEqual(len(m['sum_case_map']), 1 if lazy else 2)
                    self.assertEqual(len(m['scheme_map']), 1)
                    self.assertEqual(len(m['use_map']), 2)
                    self.assertCountEqual([[p['types'][t]['layout'] for t in v['arguments']]
                        for v in p['instantiations'].values()], [['#bool'],['#i64']])
                    emission = emit_runtime(p)
                    self.assertEqual(json.loads(emission.canonical_ir_json), p)
                    self.assertEqual(emission.runtime_source.count('= rt8_case_fields_i64('), 1 if lazy else 2)

    def test_nested_self_field_is_down_and_all_arm_sites_are_distinct(self):
        r = self.checked(fixture()); p = r['program']; m = r['binding']['source_map']
        metadata = json.loads(check_metadata(p).metadata_json)
        self_fields = []
        site_ids = []
        for case in m['sum_case_map']:
            factory = instruction(p, case['factory'])
            self.assertEqual(factory['in'], '$home')
            for arm in case['arms']:
                sites = [x for x in metadata['sites'] if x['path'] == case['factory'] and x['arm'] == arm['variant']]
                self.assertEqual(len(sites), 1); site_ids.append(sites[0]['id'])
                self.assertEqual(factory['arms']['V'+str(arm['variant'])]['code'], arm['code'])
                for field in arm['field_captures']:
                    if p['types'][field['type']] == {'tag':'closed','layout':'%F0'}:
                        self_fields.append(field)
                        self.assertEqual(field['relation'], 'down')
                        self.assertEqual(p['codes'][arm['code']]['captures'][field['capture']]['relation'], 'down')
        self.assertEqual(len(self_fields), 1)
        self.assertEqual(len(site_ids), len(set(site_ids)))
        self.assertEqual(len(site_ids), 4)

    def test_wildcard_tail_retains_application_without_eager_force(self):
        r = self.checked(fixture(True)); p = r['program']; m = r['binding']['source_map']
        case, = m['sum_case_map']; arm = next(a for a in case['arms'] if a['variant'] == 1)
        self.assertEqual([f['index'] for f in arm['field_captures']], [0])
        self.assertEqual(sum(x['op'] == 'force' for x in p['codes'][case['code']]['body']), 1)
        tail, = [x for x in m['allocation_map'] if x['source']['path'] == ['body','body','body','value'] and x['role'] == 'application']
        op = instruction(p, tail['instruction'])
        self.assertEqual(op['op'], 'application')
        self.assertEqual(p['types'][tail['logical_type']], {'tag':'closed','layout':'%F0'})
        self.assertFalse(any(x['op'] == 'force' for x in p['entry'][:-3]))

    def test_declaration_identity_is_not_layout_equality(self):
        a = s.sum_decl('A', (('A0',()),('A1',(f.I,f.nominal('A')))))
        b = s.sum_decl('B', (('B0',()),('B1',(f.I,f.nominal('B')))))
        raw = f.with_data([a,b], s.sum_case(f.construct('A1',f.lit(),f.construct('B0')),
                [s.sum_arm('A0',(),f.lit(0)),s.sum_arm('A1',(2,None),f.var(2))]))
        with self.assertRaises(transport.SharedTransportError): planner.plan_fragment(raw)

    def test_complete_marker_replayed_and_internal_guard_checked(self):
        raw = fixture(); fragment = transport.derive_shared_fragment(raw)
        self.assertEqual(fragment['nominal_sum']['self_recursive'],
                         {'policy':'closed-self-atom/1','declarations':[0]})
        for marker in ({'policy':'closed-self-atom/1','declarations':[]},
                       {'policy':'closed-self-atom/1','declarations':[1]},
                       {'policy':'wrong','declarations':[0]}):
            bad = copy.deepcopy(fragment); bad['nominal_sum']['self_recursive'] = marker
            with self.assertRaises(transport.SharedTransportError): planner.plan_fragment(raw,fragment=bad)
            with self.assertRaisesRegex(planner.PlanningError, 'self-atom evidence'): planner.Planner(bad)
        scalar = transport.derive_shared_fragment(s.shared_sum())
        scalar['nominal_sum']['self_recursive'] = {'policy':'closed-self-atom/1','declarations':[0]}
        with self.assertRaisesRegex(planner.PlanningError, 'spurious'): planner.Planner(scalar)

    def test_unselected_self_field_contract_still_checked(self):
        raw = fixture()
        # The outer scrutinee is Nil, but its unused Cons arm and nested case
        # must still carry valid self-field contracts and complete factories.
        raw['body']['body']['body']['body']['value'] = f.construct('Nil')
        good = self.checked(raw); p = good['program']
        case = next(c for c in good['binding']['source_map']['sum_case_map']
                    if any(f['index'] == 1 for a in c['arms'] for f in a['field_captures']))
        arm = next(a for a in case['arms'] if a['variant'] == 1)
        field = next(f for f in arm['field_captures'] if f['index'] == 1)
        for kind in ('type','relation','index','missing'):
            with self.subTest(kind=kind):
                bad = copy.deepcopy(p); factory = instruction(bad,case['factory'])
                if kind == 'type': bad['codes'][arm['code']]['captures'][field['capture']]['layout'] = '#i64'
                if kind == 'relation': bad['codes'][arm['code']]['captures'][field['capture']]['relation'] = 'below'
                if kind == 'index': factory['arms']['V1']['captures'][field['capture']]['index'] = 2
                if kind == 'missing': del factory['arms']['V1']
                with self.assertRaises(ResourceError): check_resources(bad)
                with self.assertRaises(ResourceError): check_metadata(bad)

    def test_scalar_sum_complete_stage10_outputs_unchanged(self):
        expected = {
            (False,False): 'ed7913080538bae20cf6547bb6dded8c06cda84e266a65d89d3ed6eb98b106d4',
            (False,True): '52316e8daf74f105c2a85141b3f0ed183fd554227a540ac4e4e59c87399a2e13',
            (True,False): '778dffb497003d511f6a1823dbcd2680602495b7a57737afd3040b89a4971cd0',
            (True,True): '0eb67a89db12fe3f68391d0b11c02bc7c09c4f491e396f3b0cc116069cbb7943'}
        for (empty,groups), digest in expected.items():
            value = planner.plan_fragment(s.shared_sum(empty),data_groups=groups)
            data = json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
            self.assertEqual(hashlib.sha256(data).hexdigest(),digest)


if __name__ == '__main__': unittest.main()
