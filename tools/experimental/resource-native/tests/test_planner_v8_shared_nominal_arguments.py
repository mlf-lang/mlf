"""Closed nominal shared vectors: host replay/check/emission, not native evidence.

Retained graphs are read-only inputs. Inferred old capture normalization remains
obsolete; this suite cannot qualify a changed original producer or source run.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

BASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(BASE),str(BASE/'tests')]
import planner_v8 as p
import module_shared_transport as m
import test_planner_v8 as f
import test_module_shared_transport as s
import test_module_shared_nominal_arguments as t
import test_planner_v8_recursive_captures as c
import test_planner_v8_nominal_captures as n
import test_planner_v8_nominal_callable_captures as old
from test_shared_source_native import instruction
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.program_schema import ResourceError
from resource_ir_v8.runtime_emit import emit_runtime


def atoms(program,vector):return [program['types'][x]['layout']for x in vector]


def dead_fixture():
    rhs=f.prefix([100,101],f.lam(2,f.ty(100),f.var(2)))
    body=f.add(f.app(f.use(1,f.I,t.N),f.lit(21)),f.app(f.use(1,f.I,f.B),f.lit(21)))
    return s.with_data(f.let(1,rhs,f.app(f.lam(30,f.I,body),f.lit(0))),s.recursive_decl())


def recursive_fixture(saved=False):
    raw=c.fixture(scalar=False,view=False,saved=saved)
    case=next(node for _,node in m._walk(raw) if node['tag']=='case')
    # Preserve ordinary recursive function and wrappers. Only its scrutinee
    # passes through one complete nominal view, captured lexically if nested.
    case['scrutinee']=f.app(f.use(1,c.SELF),case['scrutinee'])
    return raw


class SharedNominalPlannerTests(unittest.TestCase):
    def checked(self,raw,groups=False):
        result=n.checked(self,raw,groups)
        self.assertEqual(json.loads(emit_runtime(result['program']).canonical_ir_json),result['program'])
        return result

    def test_identity_and_inferred_const_preserve_one_pending_generic_rhs(self):
        for maker in (t.identity_fixture,lambda:t.const_fixture(True)):
            for groups in (False,True):
                raw=maker();result=self.checked(raw,groups);program=result['program'];mapping=result['binding']['source_map']
                self.assertEqual(len(program['schemes']),1)
                introductions=[x for x in c.all_ops(program) if x['op']=='generalize']
                self.assertEqual(len(introductions),1)
                self.assertTrue(any(x['op']=='application' for x in introductions[0]['body']))
                self.assertEqual(introductions[0]['body'][-1]['op'],'seal')
                self.assertFalse(any(x['op']=='force' for x in introductions[0]['body']))
                self.assertEqual(len(program['instantiations']),2)
                self.assertEqual(sum(x['op']=='instantiate' for x in c.all_ops(program)),2)
                self.assertEqual(len(mapping['use_map']),2)
                self.assertTrue(any('%' in atom for u in program['instantiations'].values()
                    for atom in atoms(program,u['arguments'])))
                fragment=m.derive_shared_fragment(raw)
                self.assertEqual(len(mapping['term_map']),len(fragment['term_correspondence']))
                self.assertEqual(len(mapping['allocation_map']),len({(tuple(x['source']['path']),json.dumps(x['instruction'],sort_keys=True),x['role'],x.get('arm'))for x in mapping['allocation_map']}))
                for row in mapping['allocation_map']:self.assertIn('out',instruction(program,row['instruction']))

    def test_full_const_vectors_capture_and_instance_descriptors_keep_exact_nominal_type(self):
        for groups in (False,True):
            result=self.checked(t.const_fixture(True),groups);program=result['program'];mapping=result['binding']['source_map']
            vectors=[atoms(program,x['arguments'])for x in program['instantiations'].values()]
            family,=program['families'];nominal='%'+family
            self.assertEqual(vectors,[[nominal,'#bool'],['#bool',nominal]])
            consumer,=[x for x in mapping['carrier_map'] if x['kind']=='lambda' and x['view_captures']]
            view,=consumer['view_captures'];self.assertEqual(atoms(program,view['arguments']),vectors[0])
            self.assertIsNone(consumer['type_scope']);self.assertEqual(view['relation'],'below' if groups else 'down')
            self.assertEqual(view['source_view']['kind'],'scheme')
            descendants=[x for carrier in mapping['carrier_map'] for x in carrier['view_captures']
                if x['source_view'].get('carrier')==consumer['carrier']]
            self.assertTrue(descendants)
            for child in descendants:
                self.assertEqual(child['arguments'],view['arguments']);self.assertEqual(child['layout'],view['layout'])
                self.assertEqual(child['source_view']['kind'],'captured')
            data=json.loads(check_metadata(program).metadata_json)
            nominal_id=next(x['id']for x in data['types']if x.get('atom')==nominal)
            generic_capture=[x for x in data['codes']if x['captures'] and x['scope'] is not None]
            self.assertTrue(generic_capture)
            for code in generic_capture:
                self.assertTrue(all(data['types'][v['type']]['tag']=='rigid'for v in code['captures']))
                executions=[x for x in data['code_executions']if x['code']==code['id'] and
                    any(y['type']==nominal_id for y in x['captures'])]
                self.assertTrue(executions)
                for execution in executions:
                    self.assertTrue(all(v['relation']=='down'for v in execution['captures']))
                    self.assertTrue(any(x['origin_kind']=='INSTANCE' and x['env']==execution['env']
                        and x['code_execution']==execution['id']for x in data['site_executions']))

    def test_dead_coordinate_does_not_merge_equal_arrow_views(self):
        for groups in (False,True):
            result=self.checked(dead_fixture(),groups);program=result['program']
            carrier=next(x for x in result['binding']['source_map']['carrier_map']if x['kind']=='lambda' and len(x['view_captures'])==2)
            a,b=carrier['view_captures'];self.assertEqual(a['layout'],b['layout'])
            self.assertNotEqual(a['arguments'],b['arguments']);self.assertNotEqual(a['capture'],b['capture'])
            data=json.loads(check_metadata(program).metadata_json);uses=data['uses']
            self.assertEqual(uses[0]['result_type'],uses[1]['result_type']);self.assertNotEqual(uses[0]['env'],uses[1]['env'])

    def test_recursive_nominal_view_preserves_saved_owner_and_coarse_knot(self):
        for saved in (False,True):
            for groups in (False,True):
                raw=recursive_fixture(saved);result=self.checked(raw,groups);knot,carrier,closure=c.target(result)
                view,=knot['captures']['views'];self.assertEqual(view['arguments'],[c.SELF])
                self.assertEqual(view['uses'],carrier['view_captures'][0]['occurrences'])
                actual=carrier['view_captures'][0]
                self.assertEqual(actual['source_view']['kind'],'captured' if saved else 'scheme')
                self.assertEqual(actual['relation'],'below' if groups else 'down');self.assertIsNone(carrier['type_scope'])
                self.assertEqual(instruction(result['program'],knot['fill'])['value'],knot['rhs_owner'])
                self.assertEqual(len(closure['captures']),2)
                self.assertEqual(sum(x['op']=='instantiate' for x in c.all_ops(result['program'])),2)

    def test_exact_data_and_sum_atoms_and_duplicate_shape_identity(self):
        raw=s.with_data(s.shared(s.case(s.app(s.use(1,s.nominal_type()),s.ctor('Pack',s.lit())))))
        for tree in (raw,t.identity_fixture()):
            result=self.checked(tree);self.assertEqual(len(result['program']['instantiations']),1 if tree is raw else 2)
        raw=s.with_data(f.let(1,f.prefix([100],f.lam(2,f.ty(100),f.var(2))),
            f.add(s.case(f.app(f.use(1,f.nominal('First')),f.construct('A',f.lit(21))),'A',(20,),f.var(20)),
                  s.case(f.app(f.use(1,f.nominal('Second')),f.construct('B',f.lit(21))),'B',(21,),f.var(21)))),
            s.data_decl('First','A'),s.data_decl('Second','B'))
        result=self.checked(raw);program=result['program']
        self.assertEqual(len({tuple(atoms(program,x['arguments']))for x in program['instantiations'].values()}),2)

    def test_unregistered_wrong_identity_and_open_vectors_cannot_plan(self):
        raw=t.identity_fixture();fragment=m.derive_shared_fragment(raw)
        use=next(x for x in fragment['polymorphism']['uses']if x['arguments']==[t.N])
        for bad_type in (f.nominal('Foreign'),f.arr(f.I,f.I),f.ty(999),
                         {'tag':'constructor','name':'Chain','arguments':[f.I]}):
            bad=copy.deepcopy(fragment);bad['polymorphism']['uses'][use['id']]['arguments']=[bad_type]
            with self.assertRaises(p.PlanningError):p.Planner(bad).finish()
            with self.assertRaises(m.SharedTransportError):p.plan_fragment(raw,fragment=bad)
        for change in ('name','index','source'):
            bad=copy.deepcopy(fragment);row=bad['nominal_sum']['declarations'][0]
            row[change]={'name':'Foreign','index':1,'source':{'stage':'projected','path':['declarations','1']}}[change]
            # The public entry replays declaration identity. Planner's internal
            # constructor consumes derived evidence, never caller authority.
            with self.assertRaises(m.SharedTransportError):p.plan_fragment(raw,fragment=bad)

    def test_wrong_captured_vector_type_and_support_reject_at_resource_boundary(self):
        result=self.checked(t.const_fixture(True));program=result['program']
        carrier=next(x for x in result['binding']['source_map']['carrier_map']if x['kind']=='lambda' and x['view_captures'])
        view,=carrier['view_captures'];code=carrier['ir_code']
        bool_use=next(x for x in program['instantiations'].values()if atoms(program,x['arguments'])[0]=='#bool')
        other_type=next(x['layout']for c_ in result['binding']['source_map']['carrier_map']for x in c_['view_captures']if x['arguments']==bool_use['arguments'])
        for change in ('type','support'):
            bad=copy.deepcopy(program);contract=bad['functions'][code]['captures'][view['capture']]
            contract['layout' if change=='type'else'relation']=other_type if change=='type'else'below'
            with self.assertRaises((ResourceError,ValueError)):check_resources(bad)
            with self.assertRaises((ResourceError,ValueError)):check_metadata(bad)

    def test_captured_view_logical_identity_is_checked_not_reconstructed(self):
        fragment=m.derive_shared_fragment(t.const_fixture())
        original=p.Planner.acquire_view
        def wrong(self,*args,**kwargs):
            ref,paths,source=original(self,*args,**kwargs)
            if source['kind']=='captured':ref=p.Reference(ref.variable,p.SCALARS['Int'],ref.carrier,ref.strict)
            return ref,paths,source
        from unittest import mock
        with mock.patch.object(p.Planner,'acquire_view',wrong),self.assertRaisesRegex(p.PlanningError,'full-vector view mismatch'):
            p.Planner(fragment).finish()

    def test_all_retained_original_graphs_plan_check_emit_without_upgrading_old_captures(self):
        for case in t.PINS:
            _,_,capture=t.retained(self,case);raw=capture['projection']['projected_annotated']
            fragment=m.derive_shared_fragment(raw)
            self.assertEqual(fragment['policy'],m.NOMINAL_BETA_POLICY if case=='curried-const'else m.POLICY)
            for groups in (False,True):
                result=self.checked(raw,groups)
                self.assertFalse(result['binding']['ordinary_K_checked']);self.assertFalse(result['binding']['source_admitted'])
                self.assertEqual(len(result['binding']['source_map']['scheme_map']),1)
                self.assertEqual(len(result['binding']['source_map']['use_map']),2)

    def test_stage20_complete_plans_and_generated_bytes_remain_exact(self):
        value=os.environ.get('IR8_NOMINAL_CALLABLE_CAPTURES_ROOT')
        if not value:self.skipTest('retained Stage20 root not configured')
        root=Path(value)
        for case,(sha,_) in old.PINS.items():
            blob=(root/f'capture-{case}01/capture.stdout').read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(),sha);raw=json.loads(blob)['projection']['projected_annotated']
            for mode in ('coarse','groups'):
                directory=root/'host-plan01'/case/mode;before=json.loads((directory/'planned.json').read_bytes())
                after=p.plan_fragment(raw,data_groups=mode=='groups');self.assertEqual(after,before)
                self.assertEqual(after['binding']['work'],before['binding']['work'])
                for name,blob in old.files(emit_runtime(after['program'])).items():
                    self.assertEqual(blob,(directory/name).read_bytes(),str(directory/name))


if __name__=='__main__':unittest.main()
