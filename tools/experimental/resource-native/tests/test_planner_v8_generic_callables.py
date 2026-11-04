"""Concrete callable imports: isolated host planning/checking/emission only."""
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
import test_module_shared_generic_callables as source
import test_module_shared_generic_captures as scalar
import test_planner_v8 as legacy
from test_planner_v8_generic_captures import target
from test_planner_v8_nominal_callable_captures import files
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime
from resource_ir_v8.program_schema import ResourceError


class GenericCallablePlannerTests(unittest.TestCase):
    def plan(self,tree,groups=False):
        before=copy.deepcopy(tree);out=p.plan_fragment(tree,data_groups=groups)
        self.assertEqual(before,tree);return out

    def checked(self,tree,groups=False,emit=False):
        plan=self.plan(tree,groups);facts=json.loads(check_resources(plan['program']).derived_json)
        if emit:
            check_metadata(plan['program']);out=emit_runtime(plan['program'])
            self.assertEqual(json.loads(out.canonical_ir_json),plan['program'])
        return plan,facts

    def test_direct_callable_lowering_preserves_one_shared_body_and_full_vectors(self):
        for groups in (False,True):
            plan=self.plan(source.fixture(),groups);mapping,intro=target(plan)
            self.assertEqual(len(plan['program']['schemes']),1)
            self.assertEqual(len(plan['program']['instantiations']),2)
            imported,=intro['imports'].values()
            typ=plan['program']['types'][imported['layout'][1:]]
            self.assertEqual((typ['tag'],typ['protocol'],typ['result_identity']),('arrow','repeat','unknown'))
            root,=[x for x in intro['body'] if x['op']=='closure'];fn=plan['program']['functions'][root['function']]
            self.assertEqual(fn['type_scope'],'S0')
            self.assertEqual([x['op'] for x in fn['body']].count('application'),1)
            self.assertFalse(any(x['op'] in ('force','prim2','select_i64') for x in fn['body']))
            self.assertFalse(any(x['op'] in ('application','force','thunk') for x in intro['body']))
            self.assertEqual(intro['body'][-1],{'op':'seal','value':root['out']})
            helper=next(x for x in plan['program']['entry'] if x.get('out')==imported['value'])
            self.assertEqual(helper['op'],'closure');self.assertIsNone(plan['program']['functions'][helper['function']]['type_scope'])
            self.assertNotEqual(helper['function'],root['function'])

    def test_nonempty_helper_graph_and_support_are_preserved(self):
        for captured in (False,True):
            plan=self.plan(source.fixture(captured=captured),True);_,intro=target(plan)
            row,=[x for x in plan['binding']['source_map']['group_map'] if x['kind']=='shared-rhs']
            self.assertEqual(row['strategy'],'same-home' if captured else 'fresh-below')
            self.assertEqual(len(row['support']),1);self.assertEqual(row['support'][0]['strict'],not captured)
            helper=next(x for x in plan['program']['entry'] if x.get('out')==next(iter(intro['imports'].values()))['value'])
            self.assertEqual(len(helper['captures']),int(captured))
            self.assertEqual(len(intro['imports']),1)
            k=next(x for x in intro['body'] if x['op']=='closure')
            self.assertEqual(len(k['captures']),1)

    def test_private_import_partition_reference_and_source_guards(self):
        tree=source.fixture(mixed=True);fragment=m.derive_shared_fragment(tree);d=fragment['polymorphism']['definitions'][0]
        engine=p.Planner(fragment);typ=p.arrow(p.SCALARS['Int'],p.SCALARS['Int'])
        helper=p.Reference('helper',typ,strict=True);bonus=p.Reference('bonus',p.SCALARS['Int'])
        imports,inner,support,mapping=engine.generalized_imports(d,{1:helper,9:bonus},p.Block('entry',None,[]),None)
        self.assertEqual(support,[helper,bonus]);self.assertIs(support[0],helper)
        self.assertEqual(inner[1].logical,helper.logical);self.assertTrue(inner[1].strict)
        self.assertEqual([r['binding'] for r in mapping],[1,9]);self.assertEqual(len(imports),2)
        wrong=[None,p.SchemeReference('s',0),p.Reference('f',p.SCALARS['Int']),
            p.Reference('f',('arrow',typ[1],typ[2],'once','unknown')),
            p.Reference('f',('arrow',typ[1],typ[2],'repeat','argument')),
            p.Reference('f',p.arrow(p.SCALARS['Bool'],p.SCALARS['Int']))]
        for ref in wrong:
            with self.assertRaises(p.PlanningError):p.Planner(fragment).generalized_imports(d,{1:ref,9:bonus},p.Block('entry',None,[]),None)
        for mutation in (lambda x:x['captures']['callables'][0]['binding_source'].update(path=['body','body']),
                         lambda x:x['captures']['callables'][0]['value_source'].update(path=['value']),
                         lambda x:x['captures']['callables'][0]['occurrences'].clear(),
                         lambda x:x['captures']['scalars'].append(copy.deepcopy(x['captures']['callables'][0])),
                         lambda x:x['captures']['callables'][0]['type'].update(protocol='once')):
            bad=copy.deepcopy(fragment);mutation(bad['polymorphism']['definitions'][0])
            with self.assertRaises(p.PlanningError):p.Planner(bad).finish()

    def test_nested_contracts_and_non_scalar_leaves_reject_in_private_import_guard(self):
        for options in ({'argument_arrow':True},{'result_arrow':True}):self.plan(source.fixture(**options))
        fragment=m.derive_shared_fragment(source.fixture());engine=p.Planner(fragment)
        d=fragment['polymorphism']['definitions'][0];row=d['captures']['callables'][0]
        for typ in (p.arrow(('nominal',0,'D',()),p.SCALARS['Int']),
                    p.arrow(('rigid','S0',0),p.SCALARS['Int']),
                    p.arrow(p.arrow(p.SCALARS['Int'],p.SCALARS['Int']),('arrow',p.SCALARS['Int'],p.SCALARS['Int'],'once','unknown'))):
            with self.assertRaises(p.PlanningError):engine.generic_callable_binding(d,row,typ)

    def test_original_legacy_direct_callable_examples_are_positive(self):
        tree=scalar.fixture();tree['value']=f.lam(80,f.I,f.var(80))
        tree['body']['value']['body']['body']=f.app(f.var(1),f.lit())
        other=legacy.let(9,legacy.lam(10,legacy.I,legacy.var(10)),legacy.let(1,
            legacy.prefix([100],legacy.lam(2,legacy.ty(100),legacy.app(legacy.var(9),legacy.lit()))),
            legacy.app(legacy.use(1,legacy.I),legacy.lit())))
        for raw in (tree,other):
            fragment=m.derive_shared_fragment(raw);d,=fragment['polymorphism']['definitions']
            row,=d['captures']['callables'];self.assertEqual(row['type'],f.arr(f.I,f.I));self.assertTrue(row['occurrences'])
            self.assertEqual(row['binding_source']['path'],[]);self.assertEqual(row['value_source']['path'],['value'])
            self.assertEqual(len(target(self.plan(raw))[1]['imports']),1)

    def test_application_only_scope_requires_closed_entry_proof(self):
        for groups in (False,True):
            plan,facts=self.checked(source.fixture(),groups,True)
            intro,=facts['introductions'];proof=intro['closed_entry']
            self.assertEqual(proof['policy'],'instance-only-concrete-callable-imports/1')
            self.assertEqual(proof['effects'],[])
            self.assertEqual(len(proof['callable_imports']),1)
            imported=proof['callable_imports'][0]
            self.assertEqual(facts['sites'][imported['site']]['category'],'CLOSURE')
            self.assertIsNone(facts['code_typing'][imported['code']]['type_scope'])
            self.assertEqual(imported['type'],facts['sites'][imported['site']]['principal_type'])

    def test_captured_mixed_and_nested_arrow_helpers_check_emit(self):
        for options in ({'captured':True},{'mixed':True},{'nested':True},{'argument_arrow':True},{'result_arrow':True}):
            for groups in (False,True):self.checked(source.fixture(**options),groups,True)

    def test_import_alias_facts_and_post_begin_retain_preserve_owner(self):
        plan,facts=self.checked(source.fixture(captured=True));_,intro=target(plan)
        record=next(r for r in facts['instructions'] if r['op']=='generalize')
        parent,alias=record['inputs'][1],record['outputs'][1]
        for key in ('node','group','type','provenance','ready','view','projection'):
            self.assertEqual(parent[key],alias[key])
        for key in ('capability','storage'):self.assertNotEqual(parent[key],alias[key])
        emitted=emit_runtime(plan['program']).runtime_source
        begin=emitted.index('rt8_generic_begin(');end=emitted.index('rt8_generic_seal(',begin)
        self.assertLess(begin,emitted.index('rt8_retain(',begin));self.assertNotIn('rt8_force(',emitted[begin:end])
        self.assertIn({'op':'drop','value':next(iter(intro['imports']))},intro['body'])

    def test_neutral_extra_allocation_and_wrong_support_reject(self):
        plan=self.plan(source.fixture());_,intro=target(plan)
        intro['body'].insert(0,{'op':'scalar','out':'bad','in':'$home','kind':'i64','value':0})
        intro['body'].insert(-1,{'op':'drop','value':'bad'})
        with self.assertRaises(ResourceError):check_resources(plan['program'])
        plan=self.plan(source.fixture(captured=True));_,intro=target(plan)
        root=next(x for x in intro['body'] if x['op']=='closure')
        contract=next(iter(plan['program']['functions'][root['function']]['captures'].values()));contract['relation']='below'
        with self.assertRaises(ResourceError):check_resources(plan['program'])

    def test_actual_original_both_placements_check_emit(self):
        _,_,capture=source.retained(self)
        for groups in (False,True):
            plan,facts=self.checked(capture['projection']['projected_annotated'],groups,True)
            intro,=facts['introductions'];self.assertEqual(intro['closed_entry']['effects'],[])
            self.assertEqual(len(plan['program']['schemes']),1);self.assertEqual(len(plan['program']['instantiations']),2)

    def test_actual_captured_helper_keeps_pending_graph_and_closed_entry(self):
        _,_,capture=source.retained_captured_helper(self)
        tree=capture['projection']['projected_annotated']
        bonus,helper,k=source.captured_helper_graph(self,tree)
        for groups in (False,True):
            plan,facts=self.checked(tree,groups,True);mapping,intro=target(plan)
            sm=plan['binding']['source_map'];entry=plan['program']['entry']
            self.assertEqual(mapping['binder'],k['name']['id'])
            imported,=mapping['imports'];self.assertEqual(imported['binding'],helper['name']['id'])
            self.assertEqual(len(intro['imports']),1)
            helper_op=next(x for x in entry if x.get('out')==imported['value'])
            self.assertEqual(helper_op['op'],'closure')
            helper_carrier,=[x for x in sm['carrier_map'] if x['ir_code']==helper_op['function']]
            self.assertEqual(helper_carrier['source'],{'stage':'normalized','path':['body','body','value']})
            self.assertIsNone(helper_carrier['type_scope']);self.assertEqual(helper_carrier['view_captures'],[])
            helper_capture,=helper_carrier['mono_captures'];self.assertEqual(helper_capture['binder'],bonus['name']['id'])
            bonus_owner=helper_op['captures'][helper_capture['capture']]
            bonus_op=next(x for x in entry if x.get('out')==bonus_owner)
            self.assertEqual(bonus_op['op'],'thunk');self.assertEqual(bonus_op['captures'],{})
            helper_fn=plan['program']['functions'][helper_op['function']]
            self.assertIsNone(helper_fn['type_scope'])
            helper_body,=[x for x in helper_fn['body'] if x['op']=='thunk']
            self.assertEqual(set(helper_body['captures'].values()),{helper_capture['capture'],helper_fn['parameter']})
            body_carrier,=[x for x in sm['carrier_map'] if x['ir_code']==helper_body['code']]
            self.assertIsNone(body_carrier['type_scope'])
            self.assertEqual([x['binder'] for x in body_carrier['mono_captures']],
                             sorted([bonus['name']['id'],helper['value']['parameter']['id']]))
            generic_root,=[x for x in intro['body'] if x['op']=='closure']
            self.assertEqual(list(generic_root['captures'].values()),[imported['import']])
            self.assertNotEqual(generic_root['function'],helper_op['function'])
            generic_fn=plan['program']['functions'][generic_root['function']]
            self.assertEqual(generic_fn['type_scope'],intro['scheme'])
            self.assertEqual([x['op'] for x in generic_fn['body']].count('application'),1)
            self.assertFalse(any(x['op'] in ('force','prim2','select_i64') for x in generic_fn['body']))
            proof=facts['introductions'][0]['closed_entry']
            self.assertEqual(proof['policy'],'instance-only-concrete-callable-imports/1')
            self.assertEqual(proof['effects'],[])
            callable_proof,=proof['callable_imports'];self.assertEqual(callable_proof['binding'],imported['import'])
            self.assertEqual(facts['sites'][callable_proof['site']]['category'],'CLOSURE')
            self.assertIsNone(facts['code_typing'][callable_proof['code']]['type_scope'])
            self.assertNotIn(callable_proof['code'],proof['codes'])
            self.assertEqual(len(plan['program']['schemes']),1);self.assertEqual(len(plan['program']['instantiations']),2)
            vectors=[[plan['program']['types'][t]['layout'] for t in row['arguments']] for row in sm['use_map']]
            self.assertEqual(vectors,[['#bool'],['#i64']])
            at=mapping['generalize']['segments'][0]
            self.assertFalse(any(x['op']=='force' for x in entry[:at]))
            self.assertFalse(any(x['op']=='drop' and x['value'] in (helper_op['out'],bonus_owner) for x in entry[:at]))
            if groups:
                placement,=[x for x in sm['group_map'] if x['kind']=='shared-rhs']
                self.assertEqual((placement['strategy'],placement['reason']),('same-home','support-only-down'))
                self.assertEqual(placement['support'],[{'reference':helper_op['out'],'strict':False}])

    def test_actual_pending_callable_rejects_before_plan_in_both_placements(self):
        _,path,capture=source.retained_pending_callable(self)
        old_record=(path.parent/'verification.json').read_bytes()
        tree=capture['projection']['projected_annotated'];before=copy.deepcopy(tree)
        for groups in (False,True):
            with self.assertRaises(m.SharedTransportError) as caught:p.plan_fragment(tree,data_groups=groups)
            self.assertEqual(caught.exception.code,'CAPTURE')
            self.assertEqual(caught.exception.path,['body','body','body','value','body','body','function'])
            self.assertIn('callable import requires a directly bound ordinary lambda',str(caught.exception))
            self.assertEqual(tree,before)
        self.assertEqual((path.parent/'verification.json').read_bytes(),old_record)

    def test_stage25_complete_plans_work_and_generated_files_exact(self):
        setting=os.environ.get('IR8_GENERIC_PRIMITIVES_ROOT')
        if setting is None:self.skipTest('set IR8_GENERIC_PRIMITIVES_ROOT for Stage25 goldens')
        root=Path(setting)
        for case,short in (('mixed-scalar','mixed'),('alias-scalar','alias')):
            capture=json.loads((root/'fresh-primitives01'/case/case/'capture.stdout').read_bytes())
            for mode in ('coarse','groups'):
                directory=root/'native-matrix01'/short/mode
                actual=self.plan(capture['projection']['projected_annotated'],mode=='groups')
                self.assertEqual(actual,json.loads((directory/'planned.json').read_bytes()))
                report=check_resources(actual['program']).report()
                self.assertEqual(json.loads(json.dumps(report)),json.loads((directory/'resources.json').read_bytes()))
                for name,blob in files(emit_runtime(actual['program'])).items():self.assertEqual(blob,(directory/name).read_bytes())


if __name__=='__main__':unittest.main()
