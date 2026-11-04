"""Concrete recursion captures: host replay/check/emission, never native runs."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

BASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(BASE),str(BASE/'tests')]
import planner_v8 as planner
import module_shared_transport as transport
import test_planner_v8 as f
import test_module_shared_transport as s
from test_shared_source_native import instruction
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.program_schema import ResourceError
from resource_ir_v8.runtime_emit import emit_runtime

SELF=f.nominal('IntList')
CALLABLE=f.arr(SELF,f.I)


def fixture(*, scalar=True, view=True, saved=False, dead=False):
    bonus=f.var(30) if scalar else f.lit(21)
    if view:
        value=f.app(f.use(1,f.I,*([f.I] if dead else [])),bonus)
        if dead:
            value=f.add(value,f.app(f.use(1,f.I,f.B),bonus))
    else:
        value=bonus
    case=s.sum_case(f.var(12),[s.sum_arm('Nil',(),f.lit(0)),
        s.sum_arm('Cons',(None,14),f.add(value,f.app(f.var(10),f.var(14))))])
    target=f.lam(11,SELF,f.let(12,f.app(f.lam(15,SELF,f.var(15)),f.var(11)),case))
    rhs=f.app(f.lam(16,CALLABLE,f.var(16)),target)
    values=f.construct('Cons',f.lit(0),f.construct('Cons',f.lit(0),f.construct('Nil')))
    body=f.choose(f.app(f.use(1,f.B,*([f.I] if dead else [])),f.boolean()),
        f.add(f.app(f.var(10),f.construct('Nil')),f.app(f.var(10),values)),f.lit(0))
    recursive={'tag':'letrec','bindings':[{'name':f.name(10),'type':CALLABLE,'value':rhs}], 'body':body}
    if saved:
        recursive=f.app(f.lam(40,f.I,recursive),f.lit(0))
    if scalar:
        recursive=f.let(30,f.add(f.lit(20),f.lit(1)),recursive)
    shared=(f.prefix([100,101],f.lam(2,f.ty(100),f.var(2))) if dead else f.pending_shared()['value'])
    return f.with_data([s.sum_decl('IntList',(('Nil',()),('Cons',(f.I,SELF))))],f.let(1,shared,recursive))


def all_ops(program):
    bodies=[program['entry']]+[x['body'] for table in ('functions','codes') for x in program[table].values()]
    while bodies:
        for op in bodies.pop():
            yield op
            if op['op']=='generalize':bodies.append(op['body'])


def target(result):
    mapping=result['binding']['source_map'];knot,=mapping['knot_map']
    carrier,=[x for x in mapping['carrier_map'] if x['source']==knot['function_source']]
    allocation,=[x for x in mapping['allocation_map'] if x['source']==knot['function_source'] and x['role']=='closure']
    return knot,carrier,instruction(result['program'],allocation['instruction'])


class RecursiveCapturePlannerTests(unittest.TestCase):
    def checked(self, raw, groups=False):
        before=copy.deepcopy(raw);result=planner.plan_fragment(raw,data_groups=groups)
        self.assertEqual(raw,before)
        self.assertFalse(result['binding']['source_admitted']);self.assertFalse(result['binding']['ordinary_K_checked'])
        check_resources(result['program'])
        return result

    def test_scalar_view_and_combined_captures_both_modes(self):
        for scalar,view in ((True,False),(False,True),(True,True)):
            for groups in (False,True):
                with self.subTest(scalar=scalar,view=view,groups=groups):
                    result=self.checked(fixture(scalar=scalar,view=view),groups)
                    knot,carrier,closure=target(result);program=result['program']
                    self.assertEqual(len(carrier['mono_captures']),1+scalar)
                    self.assertEqual(len(carrier['view_captures']),int(view))
                    self.assertEqual(len(closure['captures']),1+scalar+view)
                    self.assertEqual(len(knot['captures']['scalars']),int(scalar))
                    self.assertEqual(len(knot['captures']['views']),int(view))
                    self.assertIsNone(carrier['type_scope'])
                    self.assertIsNone(program['functions'][carrier['ir_code']]['type_scope'])
                    self.assertEqual(program['signatures'][program['functions'][carrier['ir_code']]['signature']]['result_identity'],'unknown')

    def test_complete_int_view_acquired_once_and_reused_in_callbacks(self):
        result=self.checked(fixture());program=result['program'];mapping=result['binding']['source_map']
        knot,carrier,_=target(result);view,=carrier['view_captures']
        self.assertEqual(view['source_view']['kind'],'scheme')
        self.assertEqual([program['types'][x]['layout'] for x in view['arguments']],['#i64'])
        self.assertEqual(len(program['schemes']),1)
        self.assertEqual(sum(x['op']=='instantiate' for x in all_ops(program)),2)
        self.assertEqual(sum(x['op']=='instantiate' for x in program['entry']),2)
        descendants=[x for c in mapping['carrier_map'] for x in c['view_captures']
                     if x['arguments']==view['arguments'] and x is not view]
        self.assertTrue(descendants)
        self.assertTrue(all(x['source_view']['kind']=='captured' for x in descendants))
        self.assertEqual(knot['captures']['views'][0]['uses'],view['occurrences'])
        self.assertEqual(json.loads(emit_runtime(program).canonical_ir_json),program)

    def test_closed_bool_capture_preserves_unselected_view_inventory(self):
        raw=fixture();bonus=raw['body']['body'];recursive=bonus['body']
        case=recursive['bindings'][0]['value']['argument']['body']['body']
        arm=case['alternatives'][1]
        arm['body']=f.choose(f.var(31),arm['body'],f.lit(0))
        bonus['body']=f.let(31,f.boolean(False),recursive)
        for groups in (False,True):
            result=self.checked(raw,groups);knot,carrier,_=target(result)
            self.assertEqual([x['type'] for x in knot['captures']['scalars']],[f.I,f.B])
            self.assertEqual(len(carrier['mono_captures']),3)
            self.assertEqual(len(carrier['view_captures']),1)

    def test_recursive_closure_can_receive_previously_saved_view(self):
        result=self.checked(fixture(saved=True));program=result['program']
        knot,carrier,_=target(result);view,=carrier['view_captures']
        self.assertEqual(view['source_view']['kind'],'captured')
        self.assertEqual(knot['hole']['root'],'function')
        self.assertEqual(sum(x['op']=='instantiate' for x in all_ops(program)),2)
        self.assertFalse(any(x['op']=='instantiate' for code in program['functions'].values() for x in code['body']))
        self.assertEqual(json.loads(emit_runtime(program).canonical_ir_json),program)

    def test_dead_parameters_keep_distinct_view_pairs_with_same_arrow(self):
        result=self.checked(fixture(dead=True));program=result['program'];knot,carrier,_=target(result)
        a,b=carrier['view_captures']
        self.assertEqual(a['layout'],b['layout'])
        self.assertNotEqual(a['capture'],b['capture'])
        self.assertNotEqual(a['arguments'],b['arguments'])
        self.assertEqual(a['arguments'][0],b['arguments'][0])
        self.assertEqual(len(knot['captures']['views']),2)
        self.assertEqual(len(program['instantiations']),3)

    def test_existing_support_and_full_rhs_graph_preserved(self):
        for groups in (False,True):
            result=self.checked(fixture(),groups);program=result['program'];mapping=result['binding']['source_map']
            knot,carrier,closure=target(result)
            scalar,=[x for x in carrier['mono_captures'] if x['binder']==30]
            own,=[x for x in carrier['mono_captures'] if x['binder']==knot['binder']['id']]
            view,=carrier['view_captures']
            self.assertEqual(own['relation'],'down');self.assertEqual(scalar['relation'],'down')
            self.assertEqual(view['relation'],'below' if groups else 'down')
            self.assertEqual(closure['captures'][own['capture']],knot['self_owner'])
            rhs,=[x for x in mapping['allocation_map'] if x['source']==knot['rhs']]
            self.assertEqual(instruction(program,rhs['instruction'])['op'],'application')
            self.assertEqual(instruction(program,knot['fill'])['value'],knot['rhs_owner'])
            start=knot['hole']['segments'][0];end=knot['fill']['segments'][0]
            self.assertFalse(any(x['op'] in ('force','new_below') for x in program['entry'][start:end]))

    def test_claimed_capture_evidence_is_freshly_replayed(self):
        raw=fixture();fragment=transport.derive_shared_fragment(raw)
        changes=[lambda r:r.pop('captures'),lambda r:r['captures']['scalars'].clear(),
            lambda r:r['captures']['scalars'][0].update(type=f.B),
            lambda r:r['captures']['views'][0].update(arguments=[f.B]),
            lambda r:r['captures']['views'][0].update(uses=[1]),
            lambda r:r.update(free_term_bindings=[])]
        for change in changes:
            bad=copy.deepcopy(fragment);change(bad['recursion']['bindings'][0])
            with self.assertRaises(transport.SharedTransportError):planner.plan_fragment(raw,fragment=bad)

    def test_internal_planner_rechecks_scalar_and_view_support(self):
        raw=fixture();fragment=transport.derive_shared_fragment(raw)
        changes=[lambda r:r['captures']['scalars'][0].update(type=f.B),
            lambda r:r['captures']['views'][0].update(arguments=[f.B]),
            lambda r:r['captures']['views'][0].update(uses=[1]),
            lambda r:r['captures']['views'].append(copy.deepcopy(r['captures']['views'][0]))]
        for change in changes:
            bad=copy.deepcopy(fragment);change(bad['recursion']['bindings'][0])
            with self.assertRaises(planner.PlanningError):planner.Planner(bad).finish()

    def test_independent_checker_rejects_wrong_capture_type_and_support(self):
        result=self.checked(fixture());knot,carrier,closure=target(result)
        scalar,=[x for x in carrier['mono_captures'] if x['binder']==30]
        view,=carrier['view_captures']
        for kind in ('scalar-type','view-type','scalar-below','view-below','wrong-view-target'):
            with self.subTest(kind=kind):
                program=copy.deepcopy(result['program']);code=program['functions'][carrier['ir_code']]
                if kind=='scalar-type':code['captures'][scalar['capture']]['layout']='#bool'
                elif kind=='view-type':code['captures'][view['capture']]['layout']='#i64'
                elif kind=='scalar-below':code['captures'][scalar['capture']]['relation']='below'
                elif kind=='view-below':code['captures'][view['capture']]['relation']='below'
                else:
                    op=next(x for x in program['entry'] if x.get('out')==closure['out'])
                    op['captures'][view['capture']]=knot['self_owner']
                with self.assertRaises(ResourceError):check_resources(program)
                with self.assertRaises(ResourceError):check_metadata(program)


CAPTURE_ROOT=os.environ.get('IR8_RECURSIVE_CAPTURES_ROOT')
PRIOR_ROOT=os.environ.get('IR8_MONOMORPHIC_RECURSION_CAPTURE_ROOT')


class RetainedRecursiveCaptureTests(unittest.TestCase):
    @unittest.skipUnless(CAPTURE_ROOT,'set IR8_RECURSIVE_CAPTURES_ROOT for exact retained capture')
    def test_actual_capture_full_replay_and_emission_both_modes(self):
        from source_capture_v8 import verify_capture
        root=Path(CAPTURE_ROOT);path=root/'capture-captured-sum01'/'capture.stdout'
        verified=verify_capture(path,fixture_root=root/'inputs'/'captured-sum',entry='main.emlf',
            expected_capture_sha256='fc0f27b7e2841aa98e3219defc3df75a159595093463949c2942cbdeac2e28fb',
            expected_source_hashes={'main.emlf':'628d6a3d5f6f4dae9b6f64a9fa0a9e8ccc5ccc6bf06d9b8188cd31c1e5d5029c',
                'SharedPoly.emlf':'50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'})
        self.assertTrue(verified['fragment_admitted'])
        self.assertFalse(verified['source_admitted']);self.assertFalse(verified['native_admitted'])
        capture=json.loads(path.read_bytes());raw=capture['projection']['projected_annotated']
        fragment=transport.derive_shared_fragment(raw)
        self.assertEqual(fragment['raw_normalized'],capture['normalization']['raw_normalized'])
        self.assertEqual(fragment['steps'],capture['normalization']['steps'])
        self.assertEqual([u['arguments'] for u in fragment['polymorphism']['uses']],[[f.I],[f.B]])
        evidence,=fragment['recursion']['bindings']
        for groups in (False,True):
            result=planner.plan_fragment(raw,fragment=fragment,data_groups=groups)
            knot,carrier,closure=target(result)
            self.assertEqual(knot['captures'],evidence['captures'])
            self.assertEqual(len(carrier['mono_captures']),2);self.assertEqual(len(carrier['view_captures']),1)
            self.assertEqual(len(closure['captures']),3)
            check_resources(result['program'])
            self.assertEqual(json.loads(emit_runtime(result['program']).canonical_ir_json),result['program'])

    @unittest.skipUnless(PRIOR_ROOT,'set IR8_MONOMORPHIC_RECURSION_CAPTURE_ROOT for frozen Stage13 plans')
    def test_complete_capture_free_stage13_plans_remain_exact(self):
        root=Path(PRIOR_ROOT);path=root/'capture-sum-list01'/'capture.stdout';data=path.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),'b49db8a0433d827325af18f112098eba3bcda21aa06f147d085b97ce9be922e5')
        raw=json.loads(data)['projection']['projected_annotated']
        pins={'coarse':'173037a68da97df72f2f1211cc979138ca1288665ff5811aa7de0646f504c1f4',
              'groups':'3ad1d170c74788265da31ed6f6894435f19eb25eddc464ee6e74b11a1338ad8c'}
        for mode,pin in pins.items():
            prior=json.loads((root/'host-plan01'/mode/'planned.json').read_bytes())
            canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
            self.assertEqual(hashlib.sha256(canonical(prior)).hexdigest(),pin)
            current=planner.plan_fragment(raw,data_groups=mode=='groups')
            self.assertEqual(current,prior)
            self.assertEqual(canonical(current),canonical(prior))
            self.assertNotIn('captures',current['binding']['source_map']['knot_map'][0])


if __name__=='__main__':unittest.main()
