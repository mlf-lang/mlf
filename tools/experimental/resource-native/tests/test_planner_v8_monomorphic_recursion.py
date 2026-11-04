"""Typed concrete function-knot planning; no compiler or native execution.

Synthetic fixtures are explicitly not source/K evidence. The optional retained
capture test replays exact producer bytes, then checks/emits without running C.
"""
import copy
import hashlib
import json
import os
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
from resource_ir_v8.program_schema import ResourceError
from resource_ir_v8.runtime_emit import emit_runtime

SELF = f.nominal('IntList')
CALLABLE = f.arr(SELF, f.I)


def fixture(*, empty=False, selected=True, wrapped=True):
    case = s.sum_case(f.var(12), [s.sum_arm('Nil', (), f.lit(0)),
        s.sum_arm('Cons', (13,14), f.add(f.var(13), f.app(f.var(10),f.var(14))))])
    target = f.lam(11,SELF,f.let(12,f.app(f.lam(15,SELF,f.var(15)),f.var(11)),case))
    rhs = f.app(f.lam(16,CALLABLE,f.var(16)),target) if wrapped else target
    values = f.construct('Nil') if empty else f.construct('Cons',f.var(20),
                                                        f.construct('Cons',f.var(20),f.construct('Nil')))
    tail = f.let(20,f.add(f.lit(20),f.lit(1)),
        f.choose(f.app(f.use(1,f.B),f.boolean(selected)),
                 f.app(f.use(1,f.I),f.app(f.var(10),values)),f.lit(42)))
    recursive = {'tag':'letrec','bindings':[{'name':f.name(10),'type':CALLABLE,'value':rhs}],
                 'body':tail}
    return f.with_data([s.sum_decl('IntList',(('Nil',()),('Cons',(f.I,SELF))))],
        f.let(1,f.pending_shared()['value'],recursive))


def below(path, parent):
    return path[:len(parent)] == parent


class MonomorphicRecursionPlannerTests(unittest.TestCase):
    def checked(self, raw, groups=False):
        before = copy.deepcopy(raw)
        result = planner.plan_fragment(raw,data_groups=groups)
        self.assertEqual(raw,before)
        self.assertFalse(result['binding']['source_admitted'])
        self.assertFalse(result['binding']['ordinary_K_checked'])
        check_resources(result['program'])
        return result

    def knot(self, result):
        program = result['program']; mapping = result['binding']['source_map']
        knot, = mapping['knot_map']
        hole = instruction(program,knot['hole'])
        keep = instruction(program,knot['retain_self'])
        fill = instruction(program,knot['fill'])
        self.assertEqual(hole,{'op':'hole','out':knot['hole_owner'],'in':knot['home'],
                               'layout':'^'+knot['logical_type']})
        self.assertEqual(keep,{'op':'retain','out':knot['self_owner'],'value':knot['hole_owner']})
        self.assertEqual(fill,{'op':'fill','hole':knot['hole_owner'],'value':knot['rhs_owner']})
        self.assertIsNone(knot['type_scope'])
        return program,mapping,knot

    def test_wrapped_rhs_checked_and_emitted_in_both_modes(self):
        for groups in (False,True):
            with self.subTest(groups=groups):
                result = self.checked(fixture(),groups)
                program,mapping,knot = self.knot(result)
                rhs, = [x for x in mapping['allocation_map'] if x['source']==knot['rhs']]
                op = instruction(program,rhs['instruction'])
                self.assertEqual(op['op'],'application')
                self.assertEqual(op['out'],knot['rhs_owner'])
                self.assertEqual(op['in'],knot['home'])
                typ = program['types'][knot['logical_type']]
                self.assertEqual((typ['protocol'],typ['result_identity']),('repeat','unknown'))
                self.assertEqual(program['types'][typ['argument']],{'tag':'closed','layout':'%F0'})
                self.assertEqual(program['types'][typ['result']],{'tag':'closed','layout':'#i64'})
                self.assertEqual(len(mapping['scheme_map']),1)
                self.assertEqual(len(mapping['use_map']),2)
                self.assertCountEqual([[program['types'][t]['layout'] for t in x['arguments']]
                    for x in program['instantiations'].values()],[['#i64'],['#bool']])
                emission = emit_runtime(program)
                self.assertEqual(json.loads(emission.canonical_ir_json),program)
                self.assertEqual(emission.runtime_source.count('= rt8_hole('),1)
                self.assertEqual(emission.runtime_source.count('rt8_fill('),1)

    def test_self_capture_uses_retained_owner_and_fill_precedes_body(self):
        program,mapping,knot = self.knot(self.checked(fixture()))
        carrier, = [c for c in mapping['carrier_map'] if c['kind']=='lambda' and
                    any(x['binder']==knot['binder']['id'] for x in c['mono_captures'])]
        capture, = [x for x in carrier['mono_captures'] if x['binder']==knot['binder']['id']]
        closure, = [x for x in mapping['allocation_map'] if x['source']==carrier['source'] and x['role']=='closure']
        op = instruction(program,closure['instruction'])
        self.assertEqual(op['captures'][capture['capture']],knot['self_owner'])
        self.assertEqual(capture['relation'],'down')
        self.assertEqual(program['functions'][carrier['ir_code']]['type_scope'],None)
        start = knot['hole']['segments'][0]; end = knot['fill']['segments'][0]
        self.assertFalse(any(op['op']=='force' for op in program['entry'][start:end]))
        self.assertLess(start,end)
        self.assertLess(end,knot['drop_self']['segments'][0])
        self.assertLess(end,knot['drop_hole']['segments'][0])
        for allocation in mapping['allocation_map']:
            if allocation['instruction']['root']=='entry' and below(allocation['source']['path'],knot['body']['path']):
                self.assertGreater(allocation['instruction']['segments'][0],end)

    def test_data_groups_never_split_recursive_rhs_or_callback_construction(self):
        program,mapping,knot = self.knot(self.checked(fixture(),True))
        rows = [x for x in mapping['group_map'] if below(x['source']['path'],knot['rhs']['path'])]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row['strategy'],'same-home')
            self.assertEqual(row['reason'],'recursive-knot-coarse')
            self.assertNotIn('create',row)
        self.assertTrue(any(x['strategy']=='fresh-below' for x in mapping['group_map']
                            if not below(x['source']['path'],knot['rhs']['path'])))

    def test_plain_function_empty_and_unselected_cases_remain_complete(self):
        for empty,selected,wrapped in ((True,True,False),(False,False,True)):
            with self.subTest(empty=empty,selected=selected,wrapped=wrapped):
                _,mapping,knot = self.knot(self.checked(fixture(empty=empty,selected=selected,wrapped=wrapped)))
                case, = mapping['sum_case_map']
                self.assertEqual(len(case['arms']),2)
                self.assertEqual(sum(x['tag']=='letrec' for x in mapping['term_map']),1)
                self.assertTrue(any(x['tag']=='var' and x.get('binder')==10 and
                                    below(x['source']['path'],knot['rhs']['path']) for x in mapping['term_map']))

    def test_needed_binds_recursive_name_in_rhs_and_body(self):
        raw = fixture(); fragment = transport.derive_shared_fragment(raw)
        planned = planner.Planner(fragment)
        self.assertEqual(planned.needed(fragment['raw_normalized'],()),(set(),{}))

    def test_independent_checker_rejects_knot_type_ticket_and_order_mutations(self):
        original = self.checked(fixture()); _,_,knot = self.knot(original)
        for mutation in ('wrong-type','missing-fill','duplicate-fill','fill-before-rhs'):
            with self.subTest(mutation=mutation):
                program = copy.deepcopy(original['program'])
                fill_index = knot['fill']['segments'][0]
                if mutation=='wrong-type': instruction(program,knot['hole'])['layout']='#i64'
                elif mutation=='missing-fill': del program['entry'][fill_index]
                elif mutation=='duplicate-fill': program['entry'].insert(fill_index,copy.deepcopy(program['entry'][fill_index]))
                else:
                    fill = program['entry'].pop(fill_index)
                    program['entry'].insert(knot['retain_self']['segments'][0]+1,fill)
                with self.assertRaises(ResourceError): check_resources(program)
                with self.assertRaises(ResourceError): check_metadata(program)

    def test_old_nonrecursive_candidate_bytes_unchanged(self):
        expected={(False,False):'ed7913080538bae20cf6547bb6dded8c06cda84e266a65d89d3ed6eb98b106d4',
                  (False,True):'52316e8daf74f105c2a85141b3f0ed183fd554227a540ac4e4e59c87399a2e13',
                  (True,False):'778dffb497003d511f6a1823dbcd2680602495b7a57737afd3040b89a4971cd0',
                  (True,True):'0eb67a89db12fe3f68391d0b11c02bc7c09c4f491e396f3b0cc116069cbb7943'}
        for (empty,groups),digest in expected.items():
            result=planner.plan_fragment(s.shared_sum(empty),data_groups=groups)
            self.assertNotIn('knot_map',result['binding']['source_map'])
            data=json.dumps(result,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
            self.assertEqual(hashlib.sha256(data).hexdigest(),digest)


CAPTURE_ROOT=os.environ.get('IR8_MONOMORPHIC_RECURSION_CAPTURE_ROOT')


@unittest.skipUnless(CAPTURE_ROOT,'set IR8_MONOMORPHIC_RECURSION_CAPTURE_ROOT for retained producer evidence')
class GenuineMonomorphicRecursionPlannerTests(unittest.TestCase):
    def test_retained_capture_replay_checker_and_emitter_both_modes(self):
        from source_capture_v8 import verify_capture
        root=Path(CAPTURE_ROOT); path=root/'capture-sum-list01'/'capture.stdout'
        verified=verify_capture(path,fixture_root=root/'inputs'/'sum-list',entry='main.emlf',
            expected_capture_sha256='b49db8a0433d827325af18f112098eba3bcda21aa06f147d085b97ce9be922e5',
            expected_source_hashes={'main.emlf':'dc591096eb609920208a4d1875047e4e054393ecd11c660a90fceb6cebc39775',
                'SharedPoly.emlf':'50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'})
        self.assertTrue(verified['fragment_admitted'])
        self.assertFalse(verified['source_admitted']);self.assertFalse(verified['native_admitted'])
        capture=json.loads(path.read_bytes()); raw=capture['projection']['projected_annotated']
        fragment=transport.derive_shared_fragment(raw)
        self.assertEqual(fragment['steps'],capture['normalization']['steps'])
        self.assertEqual(fragment['raw_normalized'],capture['normalization']['raw_normalized'])
        rec_path,rec=next((p,n) for p,n in transport._walk(fragment['raw_normalized']) if n['tag']=='letrec')
        binding,=rec['bindings'];self.assertEqual(binding['value']['tag'],'application')
        for groups in (False,True):
            result=planner.plan_fragment(raw,fragment=fragment,data_groups=groups)
            program=result['program'];mapping=result['binding']['source_map'];knot,=mapping['knot_map']
            self.assertEqual(knot['source'],planner.address(rec_path))
            self.assertEqual(knot['binder'],binding['name'])
            rhs,=[x for x in mapping['allocation_map'] if x['source']==knot['rhs']]
            self.assertEqual(instruction(program,rhs['instruction'])['op'],'application')
            self.assertEqual(instruction(program,knot['fill'])['value'],knot['rhs_owner'])
            check_resources(program)
            self.assertEqual(json.loads(emit_runtime(program).canonical_ir_json),program)


if __name__=='__main__':unittest.main()
