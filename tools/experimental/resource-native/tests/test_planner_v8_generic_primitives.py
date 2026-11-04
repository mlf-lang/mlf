"""Scoped closed-scalar carriers: raw plan/check/emission only, no targets."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest

BASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(BASE),str(BASE/'tests')]
import module_shared_transport as m
import planner_v8 as p
import test_module_shared_transport as f
import test_module_shared_generic_primitives as source
import test_planner_v8_generic_captures as old
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime
from resource_ir_v8.program_schema import ResourceError
from test_planner_v8_nominal_callable_captures import files


def actual_instruction(program,row):
    current=program['entry'] if row['root']=='entry' else program['functions' if row['root']=='function' else 'codes'][row['name']]['body']
    for part in row['segments']:current=current[part]
    return current


class GenericPrimitivePlannerTests(unittest.TestCase):
    def checked(self,tree,groups=False,emission=False):
        before=copy.deepcopy(tree);plan=p.plan_fragment(tree,data_groups=groups)
        self.assertEqual(tree,before)
        resource=check_resources(plan['program']);facts=json.loads(resource.derived_json)
        if emission:
            metadata=check_metadata(plan['program']);result=emit_runtime(plan['program'])
            self.assertEqual(json.loads(result.canonical_ir_json),plan['program'])
        return plan,facts

    def proof(self,plan,facts):
        intro,=facts['introductions'];contract=intro['closed_entry']
        self.assertEqual(contract['policy'],'instance-only-scoped-scalars/1')
        scope=intro['scheme'];codes=[c['id'] for c in facts['code_typing'] if c['type_scope']==scope]
        self.assertEqual(contract['codes'],codes)
        site=facts['sites'][contract['root_site']]
        self.assertEqual(site['category'],'CLOSURE');self.assertEqual(site['code'],contract['root_code'])
        expected=[i for i,row in enumerate(facts['instructions']) if row['type_scope']==scope and row['op'] in ('force','prim2','select_i64')]
        self.assertEqual(contract['effects'],expected)
        mapping,g=old.target(plan)
        self.assertEqual(g['body'][-1]['op'],'seal')
        self.assertEqual(sum(op['op']=='closure' for op in g['body']),1)
        self.assertFalse(any(op['op'] in ('force','prim2','select_i64','application','thunk') for op in g['body']))
        for row in plan['binding']['source_map']['carrier_map']:
            if row['type_scope']==scope:
                self.assertFalse(row['view_captures'])
                self.assertTrue(all(plan['program']['types'][v['layout'][1:]]['layout'] in ('#i64','#bool') for v in row['mono_captures']))
        return contract

    def test_five_primitives_both_placements_have_scoped_effect_proof(self):
        for ident,label in ((8,'addInt'),(9,'subInt'),(10,'eqInt'),(11,'ltInt'),(14,'mulInt')):
            for groups in (False,True):
                plan,facts=self.checked(source.fixture(ident,label,boolean=ident in (10,11)),groups)
                contract=self.proof(plan,facts)
                self.assertTrue(any(facts['instructions'][i]['op']=='prim2' for i in contract['effects']))
                scoped=[c for c in plan['program']['codes'].values() if c['type_scope']=='S0']
                self.assertEqual(len(scoped),1)

    def test_conditional_and_branch_carriers_retain_scope_and_laziness(self):
        for groups in (False,True):
            plan,facts=self.checked(source.fixture(conditional=True),groups,True);self.proof(plan,facts)
            rows=[c for c in plan['binding']['source_map']['carrier_map'] if c['type_scope']=='S0']
            self.assertEqual([r['kind'] for r in rows],['lambda','conditional','conditional-then','conditional-else'])
            for row in rows[1:]:self.assertEqual(plan['program']['codes'][row['ir_code']]['type_scope'],'S0')
            conditional=plan['program']['codes'][rows[1]['ir_code']]['body']
            self.assertEqual(sum(i['op']=='force' for i in conditional),1)
            self.assertEqual(sum(i['op']=='thunk' for i in conditional),2)
            self.assertEqual(sum(i['op']=='select_i64' for i in conditional),1)
            branch_names={r['ir_code'] for r in rows[2:]}
            for name in branch_names:self.assertFalse(any(i['op']=='force' for i in plan['program']['codes'][name]['body']))

    def test_nested_primitive_carriers_and_scalar_result_types(self):
        plan,facts=self.checked(source.fixture(nested=True),emission=True);contract=self.proof(plan,facts)
        self.assertEqual(sum(facts['instructions'][i]['op']=='prim2' for i in contract['effects']),3)
        self.assertTrue(all(c['type_scope']=='S0' for c in plan['program']['codes'].values() if c['captures'] and any(x['layout'].startswith('^') for x in c['captures'].values()) and c['type_scope'] is not None))

    def test_alias_imports_remain_distinct_and_preserve_parent_retain(self):
        plan,facts=self.checked(source.fixture(aliases=True),emission=True);self.proof(plan,facts)
        mapping,g=old.target(plan);self.assertEqual(len(g['imports']),2)
        self.assertEqual([r['binding'] for r in mapping['imports']],[1,4])
        parents=[r['value'] for r in g['imports'].values()]
        self.assertNotEqual(parents[0],parents[1])
        alias=next(i for i in plan['program']['entry'] if i.get('out')==parents[1])
        self.assertEqual(alias,{'op':'retain','out':parents[1],'value':parents[0]})
        root=next(i for i in g['body'] if i['op']=='closure')
        self.assertEqual(set(root['captures'].values()),set(g['imports']))
        fact=next(row for row in facts['instructions'] if row['op']=='generalize')
        aliases=fact['outputs'][1:]
        self.assertEqual(len({row['capability'] for row in aliases}),2)
        self.assertEqual(len({row['storage'] for row in aliases}),2)
        self.assertEqual(len({row['node'] for row in aliases}),1)
        self.assertTrue(all(row['view']=='MONO' and row['projection'] is None and not row['ready'] for row in aliases))

    def test_group_support_is_complete_and_same_home(self):
        plan,facts=self.checked(source.fixture(conditional=True),True);self.proof(plan,facts)
        mapping,g=old.target(plan)
        shared,=[r for r in plan['binding']['source_map']['group_map'] if r['kind']=='shared-rhs']
        self.assertEqual(shared['strategy'],'same-home')
        self.assertEqual([r['reference'] for r in shared['support']],[r['value'] for r in g['imports'].values()])
        self.assertFalse(any(r['strict'] for r in shared['support']))

    def test_ready_import_support_can_stay_strict_without_retagging_code(self):
        tree=source.fixture();tree['value']=f.lit(21)
        plan,facts=self.checked(tree,True,True);self.proof(plan,facts)
        shared,=[r for r in plan['binding']['source_map']['group_map'] if r['kind']=='shared-rhs']
        self.assertEqual(shared['strategy'],'fresh-below')
        self.assertTrue(all(r['strict'] for r in shared['support']))
        self.assertTrue(any(row['type_scope']=='S0' and row['kind']=='primitive' for row in plan['binding']['source_map']['carrier_map']))

    def test_new_effect_scheme_rejects_neutral_pending_root_before_emission(self):
        plan,_=self.checked(source.fixture());program=plan['program'];_,g=old.target(plan)
        root=next(i for i in g['body'] if i['op']=='closure')
        g['body'].insert(-1,{'op':'thunk','out':'bad','in':'$home','code':next(k for k,v in program['codes'].items() if v['type_scope']=='S0'),'captures':copy.deepcopy(root['captures'])})
        g['body'].insert(-1,{'op':'drop','value':'bad'})
        with self.assertRaises(ResourceError):check_resources(program)

    def test_wrong_scope_and_import_support_are_not_inferred_away(self):
        plan,_=self.checked(source.fixture());program=plan['program']
        name=next(k for k,v in program['codes'].items() if v['type_scope']=='S0')
        program['codes'][name]['type_scope']=None
        with self.assertRaises(ResourceError) as caught:check_resources(program)
        self.assertEqual(caught.exception.code,'ALLOCATION_SCOPE')
        plan,_=self.checked(source.fixture());_,g=old.target(plan)
        root=next(i for i in g['body'] if i['op']=='closure');name=root['function']
        capture=next(iter(plan['program']['functions'][name]['captures']))
        plan['program']['functions'][name]['captures'][capture]['relation']='below'
        with self.assertRaises(ResourceError):check_resources(plan['program'])

    def test_public_replay_rejects_forged_manifest(self):
        tree=source.fixture();fragment=m.derive_shared_fragment(tree)
        fragment['polymorphism']['definitions'][0]['captures']['scalars'][0]['occurrences']=[]
        with self.assertRaises(m.SharedTransportError):p.plan_fragment(tree,fragment=fragment)

    def test_private_lowering_rejects_closed_callable_dependency(self):
        tree=source.fixture();fragment=m.derive_shared_fragment(tree);planner=p.Planner(fragment)
        node=tree['body']['value']['body']['body'];path=('body','value','body','body')
        env={1:p.Reference('ordinary',p.arrow(p.SCALARS['Int'],p.SCALARS['Int']))}
        with self.assertRaisesRegex(p.PlanningError,'closed scalar dependencies'):
            planner.emit(node,path,env,{},'$home',p.Block('function','test',[],scope='S0'),'S0')

    def test_actual_saved_captures_both_placements_check_emit(self):
        for case in source.PINS:
            _,_,capture=source.retained(self,case)
            for groups in (False,True):
                plan,facts=self.checked(capture['projection']['projected_annotated'],groups,True)
                self.proof(plan,facts);self.assertEqual(len(plan['program']['instantiations']),2)
                mapping,g=old.target(plan);self.assertEqual(len(g['imports']),2)
                self.assertEqual(len(plan['program']['schemes']),1)
                self.assertEqual(len(mapping['imports']),2)

    def test_frozen_stage24_full_plans_work_and_generated_files_exact(self):
        setting=os.environ.get('IR8_CLOSED_GENERIC_CAPTURES_ROOT')
        if setting is None:self.skipTest('set IR8_CLOSED_GENERIC_CAPTURES_ROOT for Stage24 goldens')
        root=Path(setting)
        for case,short in (('generic-closed-scalar','int'),('bool-scalar','bool')):
            capture=json.loads((root/'fresh-source01'/case/case/'capture.stdout').read_bytes())
            for mode in ('coarse','groups'):
                directory=root/'native-matrix01'/short/mode
                expected=json.loads((directory/'planned.json').read_bytes())
                actual=p.plan_fragment(capture['projection']['projected_annotated'],data_groups=mode=='groups')
                self.assertEqual(actual,expected)
                facts=json.loads(check_resources(actual['program']).derived_json)
                self.assertTrue(all('closed_entry' not in i for i in facts['introductions']))
                for name,blob in files(emit_runtime(actual['program'])).items():
                    self.assertEqual(blob,(directory/name).read_bytes())


if __name__=='__main__':unittest.main()
