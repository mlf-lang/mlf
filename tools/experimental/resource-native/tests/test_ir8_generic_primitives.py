"""Stage25 synthetic resource/effect-proof/metadata/emitter checks; host only.

A conditional closed-entry proof restricts invocation, not neutral type rows.
No source capture, original compiler, C compiler or native evaluator runs here.
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_ir8_generic_imports import import_program, generalize, raw
from resource_ir_v8.checker import check_resources, ResourceError
from resource_ir_v8.metadata import check_metadata, _verify_derived, NATIVE_TABLES
from resource_ir_v8.metadata_budget import MetadataError, Budget as MetadataBudget
from resource_ir_v8.metadata_types import build_types
from resource_ir_v8.provenance import CLOSED_ENTRY_POLICY
from resource_ir_v8.runtime_emit import emit_runtime
from resource_ir_v8.runtime_emit_body import derive_plan
from resource_ir_v8.runtime_emit_budget import Budget, RuntimeEmissionError


def primitive_program(primitive='addInt', pending=True, entries=1):
    p = import_program('i64', pending, entries)
    ty = 'B' if primitive in ('eqInt', 'ltInt') else 'I'
    p['types']['AA']['result'] = ty
    p['signatures']['id']['result'] = '^' + ty
    p['functions']['id']['body'] = [
        {'op':'drop','value':'x'},
        {'op':'force','out':'left','value':'captured'},
        {'op':'scalar','out':'right','in':'$home','kind':'i64','value':0},
        {'op':'prim2','out':'answer','in':'$home','primitive':primitive,'left':'left','right':'right'},
        {'op':'drop','value':'left'},{'op':'drop','value':'right'},
        {'op':'return','value':'answer'}]
    return p


def selection_program(condition=True):
    p=import_program('bool', False)
    next(i for i in p['entry'] if i['op']=='scalar' and i['out']=='bonus')['value']=condition
    p['types']['AA']['result']='I';p['signatures']['id']['result']='^I'
    for name,value in [('yes',42),('no',0)]:
        p['codes'][name]={'result':'^I','type_scope':'S','captures':{},'body':[
            {'op':'scalar','out':'n','in':'$home','kind':'i64','value':value},
            {'op':'return','value':'n'}]}
    p['functions']['id']['body']=[{'op':'drop','value':'x'},
        {'op':'force','out':'condition','value':'captured'},
        {'op':'thunk','out':'yes','in':'$home','code':'yes','captures':{}},
        {'op':'thunk','out':'no','in':'$home','code':'no','captures':{}},
        {'op':'select_i64','out':'answer','in':'$home','condition':'condition','then':'yes','else':'no'},
        {'op':'drop','value':'condition'}, {'op':'return','value':'answer'}]
    return p


def checked(p):
    r=check_resources(p);m=check_metadata(p);e=emit_runtime(p)
    return json.loads(r.derived_json),json.loads(m.metadata_json),e


class GenericPrimitiveTests(unittest.TestCase):
    def reject(self,p,code=None):
        with self.assertRaises(ResourceError) as caught:check_resources(p)
        if code:self.assertEqual(caught.exception.code,code)
        return caught.exception

    def test_all_five_primitives_pending_ready_and_bool_result(self):
        for op in ('addInt','subInt','mulInt','eqInt','ltInt'):
            for pending in (False,True):
                with self.subTest(op=op,pending=pending):
                    d,m,e=checked(primitive_program(op,pending))
                    proof=d['introductions'][0]['closed_entry']
                    self.assertEqual(proof['policy'],CLOSED_ENTRY_POLICY)
                    self.assertEqual([d['instructions'][i]['op'] for i in proof['effects']],['force','prim2'])
                    self.assertEqual(proof['codes'],[c['id'] for c in d['code_typing'] if c['type_scope']=='S'])
                    self.assertIn('rt8_prim2',e.runtime_source)

    def test_selection_both_directions_keeps_both_branch_codes(self):
        for condition in (False,True):
            d,m,e=checked(selection_program(condition))
            proof=d['introductions'][0]['closed_entry']
            self.assertEqual(len(proof['codes']),3)
            self.assertEqual([d['instructions'][i]['op'] for i in proof['effects']],['force','select_i64'])
            self.assertIn('rt8_select_i64',e.runtime_source)
            # Host checking never claims which callback runs.
            self.assertFalse(m['native_status']['graph_executed'])

    def test_neutral_type_rows_kept_but_no_neutral_invocation(self):
        d,m,e=checked(selection_program())
        proof=d['introductions'][0]['closed_entry'];scope=m['schemes'][0]
        neutral=scope['neutral_env'];codes=set(proof['codes'])
        neutral_exec={x['id'] for x in m['code_executions'] if x['code'] in codes and x['env']==neutral}
        self.assertEqual(len(neutral_exec),3)
        self.assertTrue(any(x['env']==neutral for x in m['site_executions']))
        for boundary in m['boundaries']:
            key=boundary['key']
            if key['kind'] in ('entry','return'):self.assertNotIn(key['code_execution'],neutral_exec)
            if key['kind'] in ('slot','deferred'):
                sx=m['site_executions'][key['site_execution']];site=m['sites'][sx['site']]
                if site['context']['kind']=='execution':self.assertNotEqual(sx['env'],neutral)
        rows=[c for c in m['coverage'] if c['source']['kind']=='closed-entry']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['source']['proof'],proof)
        self.assertEqual(set(NATIVE_TABLES)&{'closed_entry','closed_entries'},set())
        self.assertTrue(all('closed_entry' not in intro for intro in m['introductions']))

    def test_import_aliases_and_retained_seal_owner(self):
        p=primitive_program(entries=2);g=generalize(p)
        g['body'].insert(-1,{'op':'retain','out':'sealed_alias','value':g['body'][0]['out']})
        g['body'].insert(-1,{'op':'drop','value':g['body'][0]['out']})
        g['body'][-1]['value']='sealed_alias'
        d,m,e=checked(p)
        intro=d['introductions'][0];self.assertEqual(intro['result_sites'],[intro['closed_entry']['root_site']])

    def test_64_import_entries_pass_65_reject(self):
        check_resources(primitive_program(entries=64))
        self.reject(primitive_program(entries=65),'IMPORT_COUNT')

    def test_scoped_force_rigid_rejects(self):
        p=primitive_program();p['functions']['id']['body']=[
            {'op':'drop','value':'captured'},{'op':'force','out':'f','value':'x'}, {'op':'return','value':'f'}]
        self.reject(p,'INSTANCE_SCALAR')

    def test_wrong_primitive_name_type_and_readiness_reject(self):
        p=primitive_program();p['functions']['id']['body'][3]['primitive']='divInt';self.reject(p,'PRIMITIVE')
        p=primitive_program();p['functions']['id']['body'][2]['kind']='bool';p['functions']['id']['body'][2]['value']=False;self.reject(p,'TYPE')
        p=primitive_program();p['functions']['id']['body'].pop(1);p['functions']['id']['body'][2]['left']='captured';self.reject(p,'DEMAND')

    def test_effect_in_introduction_stays_forbidden(self):
        p=primitive_program();generalize(p)['body'].insert(0,{'op':'force','out':'f','value':'import00'})
        self.reject(p,'OPCODE')

    def test_extra_neutral_scalar_closure_or_thunk_reject(self):
        for op in ('scalar','closure','thunk'):
            p=primitive_program();g=generalize(p)
            if op=='scalar':extra={'op':'scalar','out':'extra','in':'$home','kind':'i64','value':1}
            elif op=='closure':extra=dict(g['body'][0],out='extra')
            else:
                p['codes']['extra']={'result':'^I','captures':{},'type_scope':'S','body':[
                    {'op':'scalar','out':'n','in':'$home','kind':'i64','value':1},{'op':'return','value':'n'}]}
                extra={'op':'thunk','out':'extra','in':'$home','code':'extra','captures':{}}
            g['body'][1:1]=[extra,{'op':'drop','value':'extra'}]
            self.reject(p,'CLOSED_ENTRY')

    def test_new_below_is_explicit_bounded_slice_rejection(self):
        p=primitive_program();g=generalize(p);g['body'].insert(0,{'op':'new_below','out':'child','ceiling':'$home','imports':[]})
        g['body'].insert(-1,{'op':'drop','value':'child'})
        self.reject(p,'CLOSED_ENTRY')

    def test_effectful_dead_code_rejects_even_if_main_root_is_clean(self):
        p=import_program();p['functions']['unused']=copy.deepcopy(primitive_program()['functions']['id'])
        self.reject(p,'CLOSED_ENTRY')

    def test_unreachable_pure_same_scheme_declaration_rejects_on_new_path(self):
        p=primitive_program();p['functions']['unused']=copy.deepcopy(import_program()['functions']['id'])
        self.reject(p,'CLOSED_ENTRY')

    def test_wrong_scope_carrier_rejects(self):
        p=selection_program();p['codes']['yes']['type_scope']=None
        self.reject(p,'ALLOCATION_SCOPE')

    def test_unselected_bad_branch_is_statically_rejected(self):
        p=selection_program(True);p['codes']['no']['body'][0]['kind']='bool';p['codes']['no']['body'][0]['value']=False
        self.reject(p,'TYPE')

    def test_neutral_pending_root_into_effectful_code_rejects(self):
        p=primitive_program();g=generalize(p)
        # A same-S neutral pending application of effectful id is never allowed
        # to escape as the generalized callable root, even if another wrapper
        # would preserve the final type. Extra allocation is rejected first.
        p['types']['II']={'tag':'arrow','argument':'I','result':'I','protocol':'repeat','result_identity':'unknown'}
        p['signatures']['neutral']={'argument':'^I','result':'^I','protocol':'repeat','result_identity':'unknown'}
        p['functions']['neutral']={'signature':'neutral','parameter':'arg','captures':{},'type_scope':'S','body':[
            {'op':'force','out':'f','value':'arg'},{'op':'return','value':'f'}]}
        g['body'][1:1]=[
            {'op':'closure','out':'neutral','in':'$home','function':'neutral','captures':{}},
            {'op':'scalar','out':'arg','in':'$home','kind':'i64','value':0},
            {'op':'application','out':'pending','in':'$home','function':'neutral','argument':'arg'},
            {'op':'drop','value':'pending'},{'op':'drop','value':'neutral'},{'op':'drop','value':'arg'}]
        self.reject(p,'CLOSED_ENTRY')

    def test_forged_missing_extra_resource_proof_rejected_by_metadata(self):
        p=primitive_program();d=json.loads(check_resources(p).derived_json)
        for change in ('missing','root','code','effects','codes','policy','extra'):
            q=copy.deepcopy(d);intro=q['introductions'][0];proof=intro['closed_entry']
            if change=='missing':del intro['closed_entry']
            elif change=='root':proof['root_site']=0
            elif change=='code':proof['root_code']=0
            elif change=='effects':proof['effects']=[]
            elif change=='codes':proof['codes']=[]
            elif change=='policy':proof['policy']='source-says-okay'
            else:proof['unused']=True
            with self.subTest(change=change),self.assertRaises(MetadataError):build_types(p,q,MetadataBudget())
        p=import_program();d=json.loads(check_resources(p).derived_json);d['introductions'][0]['closed_entry']={}
        with self.assertRaises(MetadataError):build_types(p,d,MetadataBudget())

    def test_independent_metadata_cannot_hide_raw_dead_code(self):
        p=primitive_program();d=json.loads(check_resources(p).derived_json)
        # Preserve the complete old proof while introducing a raw declaration
        # that a forged lower inventory would otherwise fail to enumerate.
        p['functions']['hidden']=copy.deepcopy(p['functions']['id'])
        with self.assertRaises(MetadataError) as caught:build_types(p,d,MetadataBudget())
        self.assertEqual(caught.exception.code,'CLOSED_ENTRY')

    def test_metadata_proof_and_neutral_invocation_mutants_rejected(self):
        p=selection_program();m=json.loads(check_metadata(p).metadata_json)
        for change in ('remove','duplicate','root','effect','neutral'):
            q=copy.deepcopy(m);proof=next(c for c in q['coverage'] if c['source']['kind']=='closed-entry')
            if change=='remove':q['coverage'].remove(proof)
            elif change=='duplicate':q['coverage'].append(copy.deepcopy(proof))
            elif change=='root':proof['source']['proof']['root_site']=0
            elif change=='effect':proof['source']['proof']['effects']=[]
            else:
                boundary=next(b for b in q['boundaries'] if b['key']['kind']=='entry')
                execution=q['code_executions'][boundary['key']['code_execution']]
                boundary['key']['code_execution']=next(x['id'] for x in q['code_executions'] if x['code']==execution['code'] and q['environments'][x['env']]['mode']=='NEUTRAL')
            with self.subTest(change=change),self.assertRaises(MetadataError):_verify_derived(p,q)

    def test_emitter_requires_matching_effect_proofs(self):
        p=primitive_program();d,m,e=checked(p)
        for change in ('resource','metadata','effects','code'):
            q=copy.deepcopy(d);n=copy.deepcopy(m)
            if change=='resource':del q['introductions'][0]['closed_entry']
            elif change=='metadata':n['coverage']=[r for r in n['coverage'] if r['source']['kind']!='closed-entry']
            else:
                proof=q['introductions'][0]['closed_entry'];proof['effects' if change=='effects' else 'root_code']=[] if change=='effects' else 0
                next(r for r in n['coverage'] if r['source']['kind']=='closed-entry')['source']['proof']=copy.deepcopy(proof)
            with self.subTest(change=change),self.assertRaises(RuntimeEmissionError):derive_plan(p,n,q,Budget())

    def test_no_effect_full_old_bytes_and_work(self):
        baseline=os.environ.get('IR8_GENERIC_PRIMITIVE_BASELINE')
        if not baseline:self.skipTest('set IR8_GENERIC_PRIMITIVE_BASELINE to retained Stage24 resource-native root')
        script='''import json,sys
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime
p=json.load(sys.stdin);r=check_resources(p);m=check_metadata(p);e=emit_runtime(p)
print(json.dumps([r.canonical_json,r.derived_json,r.report(),m.metadata_json,m.report(),e.runtime_header,e.runtime_source,e.packet_header,e.packet_source,e.manifest_json,e.statistics],sort_keys=True))
'''
        programs=[raw(),import_program(),import_program('bool',False),raw('curried_const_complete_ib_bi_views')]
        for p in programs:
            outputs=[]
            for root in (baseline,str(ROOT)):
                env=dict(os.environ,PYTHONPATH=root,PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0')
                run=subprocess.run([sys.executable,'-B','-c',script],input=json.dumps(p),text=True,capture_output=True,env=env,timeout=60,check=True)
                outputs.append(json.loads(run.stdout))
            self.assertEqual(outputs[0],outputs[1])


if __name__=='__main__':unittest.main()
