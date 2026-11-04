"""Stage26 synthetic host-only concrete callable generic import contracts.

Source and native observation are separate gates. These tests neither compile
nor evaluate the generated C. Old scalar import/effect programs are goldens.
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from resource_ir_v8.checker import check_resources, ResourceError
from resource_ir_v8.metadata import check_metadata, _verify_derived, NATIVE_TABLES
from resource_ir_v8.metadata_types import build_types
from resource_ir_v8.metadata_budget import MetadataError, Budget as MetadataBudget
from resource_ir_v8.provenance import CALLABLE_ENTRY_POLICY, CALLABLE_CAPTURE_ORIGIN_CASES
from resource_ir_v8.runtime_emit import emit_runtime
from resource_ir_v8.runtime_emit_body import derive_plan
from resource_ir_v8.runtime_emit_budget import Budget, RuntimeEmissionError
from test_ir8_generic_imports import raw, import_program, generalize
from test_ir8_generic_primitives import primitive_program, selection_program


def callable_program(*, entries=1, captures=False, mixed=False):
    p=import_program(pending=False, entries=entries)
    p['types']['F']={'tag':'arrow','argument':'I','result':'I','protocol':'repeat','result_identity':'unknown'}
    p['signatures']['helper']={'argument':'^I','result':'^I','protocol':'repeat','result_identity':'unknown'}
    p['functions']['helper']={'signature':'helper','parameter':'n','captures':{},'type_scope':None,
                             'body':[{'op':'return','value':'n'}]}
    g=generalize(p)
    for row in g['imports'].values():row.update(value='helper',layout='^F')
    p['functions']['id']['captures']['captured']['layout']='^F'
    p['functions']['id']['body']=[{'op':'drop','value':'x'},
        {'op':'scalar','out':'zero','in':'$home','kind':'i64','value':42},
        {'op':'application','out':'result','in':'$home','function':'captured','argument':'zero'},
        {'op':'drop','value':'captured'},{'op':'drop','value':'zero'},{'op':'return','value':'result'}]
    p['entry'][1]={'op':'closure','out':'helper','in':'home','function':'helper','captures':{}}
    next(x for x in p['entry'] if x['op']=='drop' and x['value']=='bonus')['value']='helper'
    if captures:
        # A lawful already-owned concrete closure may carry a pending scalar.
        p['codes']['seed']={'result':'^I','captures':{},'type_scope':None,'body':[
            {'op':'scalar','out':'value','in':'$home','kind':'i64','value':42},{'op':'return','value':'value'}]}
        p['entry'].insert(1,{'op':'thunk','out':'seed','in':'home','code':'seed','captures':{}})
        p['entry'][2]['captures']={'bonus':'seed'}
        p['functions']['helper']['captures']={'bonus':{'layout':'^I','relation':'down'}}
        p['functions']['helper']['body']=[{'op':'drop','value':'n'},{'op':'return','value':'bonus'}]
        p['entry'].insert(3,{'op':'drop','value':'seed'})
    if mixed:
        p['entry'].insert(1,{'op':'scalar','out':'flag','in':'home','kind':'bool','value':True})
        g['imports']['scalar']={'value':'flag','layout':'^B','relation':'down'}
        g['body'].insert(-1,{'op':'drop','value':'scalar'})
        p['entry'].insert(-2,{'op':'drop','value':'flag'})
    return p


def checked(p):
    r=check_resources(p);m=check_metadata(p);e=emit_runtime(p)
    return json.loads(r.derived_json),json.loads(m.metadata_json),e


class GenericCallableImportTests(unittest.TestCase):
    def reject(self,p,code=None):
        with self.assertRaises((ResourceError,ValueError)) as caught:check_resources(p)
        if code:self.assertEqual(caught.exception.code,code)
        return caught.exception

    def test_ready_callable_without_scalar_effects_has_full_proof(self):
        p=callable_program();d,m,e=checked(p)
        proof=d['introductions'][0]['closed_entry']
        self.assertEqual(proof['policy'],CALLABLE_ENTRY_POLICY)
        self.assertEqual(proof['effects'],[])
        self.assertEqual(len(proof['callable_imports']),1)
        fact=next(x for x in d['instructions'] if x['op']=='generalize')
        row=proof['callable_imports'][0];old,alias=fact['inputs'][row['input']],fact['outputs'][row['output']]
        self.assertEqual(row['binding'],'import00')
        self.assertEqual(row['type'],old['type']);self.assertTrue(old['ready'])
        self.assertEqual(d['sites'][row['site']]['category'],'CLOSURE')
        self.assertEqual(d['code_typing'][row['code']]['name'],'helper')
        for key in old:
            if key not in ('role','capability','storage'):self.assertEqual(old[key],alias[key],key)
        for key in ('capability','storage'):self.assertNotEqual(old[key],alias[key])
        self.assertTrue(any(x.get('origin_cases')==list(CALLABLE_CAPTURE_ORIGIN_CASES) for x in d['obligations']))
        coverage=next(x for x in m['coverage'] if x['source']['kind']=='closed-entry')
        self.assertEqual(coverage['source']['proof'],proof)
        self.assertNotIn('closed_entry',str(m['introductions']))
        for code in proof['codes']:
            self.assertTrue(any(x['code']==code and m['environments'][x['env']]['mode']=='NEUTRAL' for x in m['code_executions']))
        self.assertTrue(e.runtime_source)

    def test_captured_pending_scalar_helper_and_mixed_aliases(self):
        for captures,mixed in ((True,False),(False,True),(True,True)):
            with self.subTest(captures=captures,mixed=mixed):
                d,m,e=checked(callable_program(entries=2,captures=captures,mixed=mixed))
                rows=d['introductions'][0]['closed_entry']['callable_imports']
                self.assertEqual(len(rows),2);self.assertEqual(rows[0]['site'],rows[1]['site'])
                self.assertNotEqual(rows[0]['output'],rows[1]['output'])

    def test_recursive_arrow_full_contract_and_legacy_representation(self):
        p=callable_program()
        p['types']['G']={'tag':'arrow','argument':'F','result':'F','protocol':'repeat','result_identity':'unknown'}
        p['signatures']['helper'].update(argument='^F',result='^F')
        generalize(p)['imports']['import00']['layout']='^G'
        p['functions']['id']['captures']['captured']['layout']='^G'
        p['functions']['id']['body']=[{'op':'drop','value':'x'},{'op':'drop','value':'captured'},
            {'op':'scalar','out':'result','in':'$home','kind':'i64','value':42},{'op':'return','value':'result'}]
        d,m,e=checked(p)
        row=d['introductions'][0]['closed_entry']['callable_imports'][0]
        self.assertEqual(d['sites'][row['site']]['legacy_physical'],'@helper')
        self.assertEqual(d['code_typing'][row['code']]['callable_type'],row['type'])
        self.assertEqual(d['introductions'][0]['closed_entry']['effects'],[])

    def test_scalar_and_callable_effect_trigger_combines(self):
        p=callable_program(mixed=True);g=generalize(p)
        p['functions']['id']['captures']['flag']={'layout':'^B','relation':'down'}
        g['body'][0]['captures']['flag']='scalar'
        p['functions']['id']['body'][0:0]=[{'op':'force','out':'checked_flag','value':'flag'},{'op':'drop','value':'checked_flag'}]
        d,m,e=checked(p)
        proof=d['introductions'][0]['closed_entry']
        self.assertEqual(proof['policy'],CALLABLE_ENTRY_POLICY);self.assertEqual(len(proof['effects']),1)

    def test_import_aliases_and_sealed_alias_preserve_actual_site(self):
        p=callable_program(entries=3);g=generalize(p);at=p['entry'].index(g)
        p['entry'].insert(at,{'op':'retain','out':'helper_alias','value':'helper'})
        g['imports']['import01']['value']='helper_alias'
        p['entry'].insert(-2,{'op':'drop','value':'helper_alias'})
        g['body'].insert(-1,{'op':'retain','out':'root_alias','value':'f'})
        g['body'].insert(-1,{'op':'drop','value':'f'});g['body'][-1]['value']='root_alias'
        d,m,e=checked(p)
        rows=d['introductions'][0]['closed_entry']['callable_imports']
        self.assertEqual(len({r['site'] for r in rows}),1)
        self.assertEqual([r['input'] for r in rows],[1,2,3])

    def test_64_explicit_imports_not_distinct_nodes(self):
        p=callable_program(entries=64);d=json.loads(check_resources(p).derived_json)
        rows=d['introductions'][0]['closed_entry']['callable_imports']
        self.assertEqual(len(rows),64);self.assertEqual(len({r['site'] for r in rows}),1)
        check_metadata(p)
        self.reject(callable_program(entries=65),'IMPORT_COUNT')
        self.reject(callable_program(entries=0),'IMPORT_COUNT')

    def test_nonclosed_nonrepeat_refined_and_nominal_contracts_reject(self):
        for change in ('rigid','once','identity','nominal','nested-once','nested-nominal'):
            p=callable_program();row=p['types']['F']
            if change=='rigid':row['argument']='A'
            elif change=='once':row['protocol']='once'
            elif change=='identity':row['result_identity']='argument'
            elif change=='nominal':
                p['layouts']['Box']={};p['types']['N']={'tag':'closed','layout':'Box'};row['result']='N'
            else:
                p['types']['Inner']=copy.deepcopy(row);row['argument']='Inner'
                if change=='nested-once':p['types']['Inner']['protocol']='once'
                else:
                    p['families']['List']={'variants':['Nil'],'fields':{'Nil':[]}}
                    p['types']['N']={'tag':'closed','layout':'%List'};p['types']['Inner']['result']='N'
            with self.subTest(change=change):self.reject(p)

    def test_wrong_type_pending_thunk_hole_and_application_reject(self):
        p=callable_program();generalize(p)['imports']['import00']['layout']='^I';self.reject(p,'TYPE')
        for origin in ('thunk','hole','application'):
            p=callable_program();g=generalize(p)
            if origin=='hole':p['entry'][1]={'op':'hole','out':'helper','in':'home','layout':'^F'}
            elif origin=='thunk':
                p['codes']['factory']={'type_scope':None,'result':'^F','captures':{},'body':[
                    {'op':'closure','out':'f','in':'$home','function':'helper','captures':{}},{'op':'return','value':'f'}]}
                p['entry'][1]={'op':'thunk','out':'helper','in':'home','code':'factory','captures':{}}
            else:
                p['signatures']['factory']={'argument':'^I','result':'^F','protocol':'repeat','result_identity':'unknown'}
                p['functions']['factory']={'signature':'factory','parameter':'n','captures':{},'type_scope':None,'body':[
                    {'op':'drop','value':'n'},{'op':'closure','out':'f','in':'$home','function':'helper','captures':{}},{'op':'return','value':'f'}]}
                p['entry'][1:2]=[{'op':'closure','out':'factory','in':'home','function':'factory','captures':{}},
                    {'op':'scalar','out':'seed','in':'home','kind':'i64','value':0},
                    {'op':'application','out':'helper','in':'home','function':'factory','argument':'seed'},
                    {'op':'drop','value':'factory'},{'op':'drop','value':'seed'}]
            with self.subTest(origin=origin):self.reject(p,'GENERIC_IMPORT')

    def test_forced_loan_unsupported_owner_and_missing_down_reject(self):
        for change in ('forced','loan','parameter','capture','support'):
            p=callable_program();g=generalize(p);at=p['entry'].index(g)
            if change in ('forced','loan'):
                p['entry'].insert(at,{'op':'force' if change=='forced' else 'borrow','out':'altered','value':'helper'})
                g['imports']['import00']['value']='altered'
            elif change=='support':
                p['entry'].insert(at,{'op':'new_root','out':'foreign','imports':[]});g['in']='foreign'
            else:
                p['entry'].remove(g);g['in']='$home'
                p['signatures']['outer']={'argument':'^F','result':'^F','protocol':'repeat','result_identity':'unknown'}
                p['functions']['outer']={'signature':'outer','type_scope':None,'parameter':'helper' if change=='parameter' else 'unused',
                    'captures':{} if change=='parameter' else {'helper':{'layout':'^F','relation':'down'}},
                    'body':[g,{'op':'drop','value':'shared'},{'op':'return','value':'helper'}]}
            with self.subTest(change=change):self.reject(p)

    def test_child_lifetime_leaks_and_early_parent_release_reject(self):
        p=callable_program();g=generalize(p);g['body'].pop(1);self.reject(p,'UNDISCHARGED')
        p=callable_program();g=generalize(p);p['entry'].insert(p['entry'].index(g),{'op':'drop','value':'helper'});self.reject(p,'NOT_LIVE')
        p=callable_program();g=generalize(p);g['body'].insert(0,{'op':'drop','value':'import00'});self.reject(p,'NOT_LIVE')

    def test_neutral_noncapture_publication_stays_rejected(self):
        p=callable_program();g=generalize(p)
        g['body'][0:0]=[{'op':'scalar','out':'zero','in':'$home','kind':'i64','value':0},
            {'op':'application','out':'bad','in':'$home','function':'import00','argument':'zero'},
            {'op':'drop','value':'bad'},{'op':'drop','value':'zero'}]
        self.reject(p,'GENERIC_PUBLICATION')

    def test_direct_entry_proof_rejects_extra_neutral_allocations(self):
        for change in ('scalar','closure','new_below','thunk'):
            p=callable_program();g=generalize(p)
            if change=='scalar':extra={'op':'scalar','out':'extra','in':'$home','kind':'i64','value':1}
            elif change=='closure':extra=dict(g['body'][0],out='extra')
            elif change=='new_below':extra={'op':'new_below','out':'extra','ceiling':'$home','imports':[]}
            else:
                p['codes']['unused']={'result':'^I','captures':{},'type_scope':'S','body':[
                    {'op':'scalar','out':'n','in':'$home','kind':'i64','value':0},{'op':'return','value':'n'}]}
                extra={'op':'thunk','out':'extra','in':'$home','code':'unused','captures':{}}
            g['body'][1:1]=[extra,{'op':'drop','value':'extra'}]
            with self.subTest(change=change):self.reject(p,'CLOSED_ENTRY')

    def test_all_same_scope_codes_even_unused_require_reachability(self):
        p=callable_program();p['functions']['unreachable']=copy.deepcopy(p['functions']['id'])
        self.reject(p,'CLOSED_ENTRY')
        p=callable_program();d=json.loads(check_resources(p).derived_json)
        p['functions']['unreachable']=copy.deepcopy(p['functions']['id'])
        with self.assertRaises(MetadataError):build_types(p,d,MetadataBudget())

    def test_neutral_typing_remains_but_invocation_is_instance_only(self):
        d,m,e=checked(callable_program());proof=d['introductions'][0]['closed_entry']
        neutral={x['id'] for x in m['code_executions'] if x['code'] in proof['codes'] and m['environments'][x['env']]['mode']=='NEUTRAL'}
        self.assertTrue(neutral)
        self.assertTrue(any(x['env']==m['schemes'][0]['neutral_env'] for x in m['site_executions']))
        for boundary in m['boundaries']:
            if boundary['key']['kind'] in ('entry','return'):self.assertNotIn(boundary['key']['code_execution'],neutral)
        rules={b['access_rule'] for b in m['boundaries']}
        self.assertIn('capture-neutral-or-concrete-callable',rules)
        self.assertIn('capture-project-or-concrete-callable-identity',rules)
        for row in m['boundaries']:
            if row['access_rule'] in ('capture-neutral-or-concrete-callable','capture-project-or-concrete-callable-identity'):
                self.assertTrue({'same-neutral-capsule','preserve-foreign-access','state-category','code-association'} <= set(row['guards']))
        self.assertEqual(len(NATIVE_TABLES),20)

    def test_independent_metadata_rejects_import_and_proof_forgery(self):
        p=callable_program();d=json.loads(check_resources(p).derived_json)
        for change in ('missing','policy','empty','input','output','type','site','code','binding','ready','projection','category','raw-allocation'):
            q=copy.deepcopy(d);r=copy.deepcopy(p);intro=q['introductions'][0];proof=intro['closed_entry']
            parent=next(x for x in q['instructions'] if x['op']=='generalize')
            if change=='missing':del intro['closed_entry']
            elif change=='policy':proof['policy']='instance-only-scoped-scalars/1'
            elif change=='empty':proof['callable_imports']=[]
            elif change in ('input','output','type','site','code'):proof['callable_imports'][0][change]=-1
            elif change=='binding':proof['callable_imports'][0]['binding']='other'
            elif change=='ready':parent['inputs'][1]['ready']=False;parent['outputs'][1]['ready']=False
            elif change=='projection':parent['inputs'][1]['projection']=0;parent['outputs'][1]['projection']=0
            elif change=='category':q['sites'][proof['callable_imports'][0]['site']]['category']='THUNK'
            else:r['entry'][1]['op']='thunk'
            with self.subTest(change=change),self.assertRaises(MetadataError):build_types(r,q,MetadataBudget())

    def test_emitter_rederives_empty_effect_import_proof(self):
        p=callable_program();d,m,e=checked(p)
        for change in ('missing','coverage','policy','import','ready','type'):
            q,n=copy.deepcopy(d),copy.deepcopy(m)
            proof=q['introductions'][0]['closed_entry']
            coverage=next(x for x in n['coverage'] if x['source']['kind']=='closed-entry')
            if change=='missing':del q['introductions'][0]['closed_entry']
            elif change=='coverage':n['coverage'].remove(coverage)
            elif change=='policy':proof['policy']='instance-only-scoped-scalars/1';coverage['source']['proof']=copy.deepcopy(proof)
            elif change=='import':proof['callable_imports'][0]['code']=-1;coverage['source']['proof']=copy.deepcopy(proof)
            else:
                parent=next(x for x in q['instructions'] if x['op']=='generalize')
                for fact in (parent['inputs'][1],parent['outputs'][1]):fact['ready' if change=='ready' else 'type']=False if change=='ready' else 0
            with self.subTest(change=change),self.assertRaises(RuntimeEmissionError):derive_plan(p,n,q,Budget())

    def test_metadata_cannot_widen_neutral_execution_or_drop_origin_alternative(self):
        p=callable_program();m=json.loads(check_metadata(p).metadata_json)
        for change in ('neutral','concrete','proof','invoke'):
            q=copy.deepcopy(m)
            if change=='proof':q['coverage']=[x for x in q['coverage'] if x['source']['kind']!='closed-entry']
            elif change=='invoke':
                root=next(x for x in q['coverage'] if x['source']['kind']=='closed-entry')['source']['proof']['root_code']
                row=next(x for x in q['boundaries'] if x['key']['kind']=='entry' and q['code_executions'][x['key']['code_execution']]['code']==root)
                row['key']['code_execution']=next(x['id'] for x in q['code_executions'] if x['code']==root and q['environments'][x['env']]['mode']=='NEUTRAL')
            else:
                row=next(x for x in q['boundaries'] if x['access_rule']=='capture-neutral-or-concrete-callable')
                row['guards'].remove('same-neutral-capsule' if change=='neutral' else 'preserve-foreign-access')
            with self.subTest(change=change),self.assertRaises(MetadataError):_verify_derived(p,q)

    def test_same_typed_distinct_import_owner_identity_is_not_swappable(self):
        p=callable_program(entries=2);g=generalize(p)
        p['entry'].insert(2,{'op':'closure','out':'other','in':'home','function':'helper','captures':{}})
        g['imports']['import01']['value']='other'
        p['entry'].insert(-2,{'op':'drop','value':'other'})
        d,m,e=checked(p)
        rows=d['introductions'][0]['closed_entry']['callable_imports'];self.assertNotEqual(rows[0]['site'],rows[1]['site'])
        q=copy.deepcopy(p);generalize(q)['body'][0]['captures']['captured']='import01'
        with self.assertRaises(MetadataError):build_types(q,d,MetadataBudget())

    def test_type_depth_32_and_33_keep_existing_limits(self):
        p=callable_program()
        previous='I'
        for i in range(1,32):
            key='Deep'+str(i);p['types'][key]={'tag':'arrow','argument':'I','result':previous,'protocol':'repeat','result_identity':'unknown'};previous=key
        p['signatures']['helper']['result']='^Deep30'
        p['functions']['helper']['captures']={'tail':{'layout':'^Deep30','relation':'down'}}
        # The declaration/eligibility test is direct; a synthetic physical value
        # of this depth is not invented to satisfy the import owner contract.
        from resource_ir_v8.declarations import check_declarations
        # check_resources still rejects missing captures, independently of type eligibility.
        from resource_ir_v8.program_schema import DECLARATION_KEYS
        from resource_ir_v8.declaration_adapter import check_type_ids
        from resource_ir_v8.provenance import Analysis, scalar_arrow
        from resource_ir_v8.budgets import Budget as ResourceBudget
        six={k:p[k] for k in DECLARATION_KEYS};ids=check_type_ids(six);budget=ResourceBudget()
        types=Analysis(budget,ids).types
        self.assertTrue(scalar_arrow(types,ids.resolve_id('^'+previous),budget))
        p['types']['TooDeep']={'tag':'arrow','argument':'I','result':previous,'protocol':'repeat','result_identity':'unknown'}
        with self.assertRaises(ValueError):check_declarations({k:p[k] for k in DECLARATION_KEYS})

    def test_old_scalar_import_and_primitive_bytes_work_exact(self):
        baseline=os.environ.get('IR8_GENERIC_CALLABLE_BASELINE')
        if not baseline:self.skipTest('set IR8_GENERIC_CALLABLE_BASELINE to retained Stage25 resource-native root')
        script='\n'.join(['import json,sys','from resource_ir_v8.checker import check_resources','from resource_ir_v8.metadata import check_metadata','from resource_ir_v8.runtime_emit import emit_runtime',
            'p=json.load(sys.stdin);r=check_resources(p);m=check_metadata(p);e=emit_runtime(p)',
            'print(json.dumps([r.canonical_json,r.derived_json,r.report(),m.metadata_json,m.report(),e.runtime_header,e.runtime_source,e.packet_header,e.packet_source,e.manifest_json,e.statistics],sort_keys=True))'])
        for p in (raw(),import_program(),import_program('bool',False),primitive_program(),selection_program()):
            outputs=[]
            for root in (baseline,str(ROOT)):
                env=dict(os.environ,PYTHONPATH=root,PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0')
                run=subprocess.run([sys.executable,'-B','-c',script],input=json.dumps(p),text=True,capture_output=True,env=env,timeout=60,check=True)
                outputs.append(json.loads(run.stdout))
            self.assertEqual(outputs[0],outputs[1])


if __name__=='__main__':unittest.main()

