#!/usr/bin/env python3
"""Host regression tests for optional plain-Int branch owner reuse.

These synthetic typed-fragment probes are not source-producer qualification.
Native/source A/B evidence is a separate campaign. The existing source default,
transport whitelist and independent resource checker remain unchanged.
"""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import planner_v8 as planner
from module_shared_transport import derive_shared_fragment, SharedTransportError
from resource_ir_v8.checker import check_resources, ResourceError
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime

INT = {'tag':'constructor','name':'Int','arguments':[]}
BOOL = {'tag':'constructor','name':'Bool','arguments':[]}
def name(i): return {'id':i,'hint':'v'+str(i)}
def var(i): return {'tag':'var','name':name(i)}
def lit(i): return {'tag':'int64','value':i}
def boolean(v): return {'tag':'bool','value':v}
def app(f,a): return {'tag':'application','function':f,'argument':a}
def let(i,v,b): return {'tag':'let','name':name(i),'value':v,'body':b}
def lam(i,t,b): return {'tag':'lambda','parameter':name(i),'parameter_type':t,'body':b}
def prim(ident,label,*args):
    result={'tag':'primitive','id':ident,'name':label,'arguments':[INT] if ident==13 else []}
    for arg in args: result=app(result,arg)
    return result
def add(a,b): return prim(8,'addInt',a,b)
def conditional(c,a,b): return prim(13,'ifThenElse',c,a,b)
def instruction(program,path):
    value=program['entry'] if path['root']=='entry' else program['functions' if path['root']=='function' else 'codes'][path['name']]['body']
    for key in path['segments']: value=value[key]
    return value

def audit_rows(raw,plan):
    mapping=plan['binding']['source_map'];rows=mapping['branch_owner_reuse']
    seen_sources=set();seen_retains=set();seen_arms=set()
    for row in rows:
        source_key=tuple(row['source']['path'])
        retain_key=(row['retain']['root'],row['retain']['name'],tuple(row['retain']['segments']))
        arm_key=(row['retain']['name'],row['branch'])
        if source_key in seen_sources or retain_key in seen_retains or arm_key in seen_arms:
            raise AssertionError('reused branch correspondence is duplicated')
        seen_sources.add(source_key);seen_retains.add(retain_key);seen_arms.add(arm_key)
        node=raw
        for key in row['source']['path']: node=node[int(key)] if isinstance(node,list) else node[key]
        if node['tag']!='var' or node['name']['id']!=row['binding']:
            raise AssertionError('reuse row does not name original plain variable')
        if row['branch'] not in ('conditional-then','conditional-else'):
            raise AssertionError('wrong branch kind')
        carriers=[c for c in mapping['carrier_map'] if c['kind']=='conditional' and
                  c['ir_code']==row['retain']['name']]
        if len(carriers)!=1 or row['retain']['root']!='thunk':
            raise AssertionError('reuse retain is not in its conditional carrier')
        carrier=carriers[0];code=plan['program']['codes'][carrier['ir_code']]
        suffix=['function','argument'] if row['branch']=='conditional-then' else ['argument']
        if row['source']!={'stage':'normalized','path':carrier['source']['path']+suffix}:
            raise AssertionError('reuse row names the wrong source branch position')
        if row['type_scope']!=carrier['type_scope'] or row['type_scope']!=code['type_scope']:
            raise AssertionError('reuse row names the wrong type scope')
        captures=[c for c in carrier['mono_captures'] if c['binder']==row['binding']]
        if len(captures)!=1 or captures[0]['capture']!=row['source_owner']:
            raise AssertionError('reuse row does not retain the source binder capture')
        selectors=[(i,s) for i,s in enumerate(code['body']) if s['op']=='select_i64']
        arm='then' if row['branch']=='conditional-then' else 'else'
        if (len(selectors)!=1 or selectors[0][1][arm]!=row['retained_owner'] or
                row['retain']['segments']!=[row['retain']['segments'][0]] or
                not row['retain']['segments'][0]<selectors[0][0]):
            raise AssertionError('reuse owner is not consumed by its exact selector arm')
        if plan['program']['types'][row['logical_type']]!={'tag':'closed','layout':'#i64'}:
            raise AssertionError('reuse row is not exact intrinsic Int')
        if instruction(plan['program'],row['retain'])!={'op':'retain','out':row['retained_owner'],'value':row['source_owner']}:
            raise AssertionError('reuse row does not name the exact owner retain')
    if plan['binding']['optimizations']!={'int_branch_owner_reuse':{'policy':'plain-int-variable-branch-owner-reuse/1','reused_branches':len(rows)}}:
        raise AssertionError('optimization binding differs')
    return rows

CASES = {
 'same-true':(let(1,add(lit(20),lit(22)),conditional(boolean(True),var(1),var(1))),2),
 'same-false':(let(1,add(lit(20),lit(22)),conditional(boolean(False),var(1),var(1))),2),
 'two-aliases':(let(1,add(lit(20),lit(22)),let(2,var(1),conditional(boolean(False),var(1),var(2)))),2),
 'two-pending':(let(1,add(lit(20),lit(22)),let(2,add(lit(100),lit(200)),conditional(boolean(True),var(1),var(2)))),2),
 'one-expression':(let(1,lit(42),conditional(boolean(True),var(1),add(lit(21),lit(21)))),1),
 'lambda-parameter':(app(lam(1,INT,conditional(boolean(False),var(1),var(1))),lit(42)),2),
 'let-branch':(let(1,lit(42),conditional(boolean(True),let(2,var(1),var(2)),var(1))),1),
 'application-branch':(let(1,lit(42),conditional(boolean(True),app(lam(2,INT,var(2)),var(1)),var(1))),1),
 'literal-control':(conditional(boolean(True),lit(42),lit(0)),0),
}
CASES['unselected-loop']=({'tag':'letrec','bindings':[{'name':name(10),'type':{'tag':'arrow','from':INT,'to':INT},'value':lam(11,INT,app(var(10),var(11)))}],'body':let(12,app(var(10),lit(0)),let(13,add(lit(20),lit(22)),conditional(boolean(False),var(12),var(13))))},2)

class BranchOwnerReuseTests(unittest.TestCase):
    def test_fragment_matrix(self):
        for case,(raw,count) in CASES.items():
            for groups in (False,True):
                with self.subTest(case=case,data_groups=groups):
                    original=copy.deepcopy(raw);fragment=derive_shared_fragment(raw)
                    default=planner.plan_fragment(raw,fragment=fragment,data_groups=groups)
                    explicit=planner.plan_fragment(raw,fragment=fragment,data_groups=groups,reuse_int_branches=False)
                    self.assertEqual(default,explicit)
                    self.assertNotIn('optimizations',default['binding'])
                    self.assertNotIn('branch_owner_reuse',default['binding']['source_map'])
                    optimized=planner.plan_fragment(raw,fragment=fragment,data_groups=groups,reuse_int_branches=True)
                    rows=audit_rows(fragment['raw_normalized'],optimized)
                    self.assertEqual(len(rows),count)
                    self.assertEqual(default['binding']['source_map']['term_map'],optimized['binding']['source_map']['term_map'])
                    self.assertEqual(len(default['program']['codes'])-len(optimized['program']['codes']),count)
                    self.assertEqual(len(default['binding']['source_map']['allocation_map'])-len(optimized['binding']['source_map']['allocation_map']),count)
                    checked=check_resources(optimized['program']);check_metadata(optimized['program'])
                    emitted=emit_runtime(optimized['program'])
                    self.assertEqual(checked.sha256,optimized['binding']['candidate_sha256'])
                    self.assertEqual(json.loads(emitted.canonical_ir_json),optimized['program'])
                    if count==0:
                        self.assertEqual(default['program'],optimized['program'])
                        self.assertEqual(emit_runtime(default['program']).runtime_source,emitted.runtime_source)
                    self.assertEqual(raw,original)
                    self.assertEqual(fragment,derive_shared_fragment(raw))

    def test_options_are_actual_booleans(self):
        raw=CASES['literal-control'][0]
        for value in (None,0,1,'true',[],{}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(planner.PlanningError,'reuse_int_branches must be a boolean'):
                    planner.plan_fragment(raw,reuse_int_branches=value)

    def test_supplied_fragment_is_not_authority(self):
        raw=CASES['same-true'][0];fragment=derive_shared_fragment(raw)
        fragment['raw_normalized']['value']['argument']['value']=999
        with self.assertRaises(SharedTransportError):
            planner.plan_fragment(raw,fragment=fragment,reuse_int_branches=True)

    def test_bool_result_conditional_still_rejected(self):
        head={'tag':'primitive','id':13,'name':'ifThenElse','arguments':[BOOL]}
        raw=app(app(app(head,boolean(True)),boolean(True)),boolean(False))
        for enabled in (False,True):
            with self.assertRaises(SharedTransportError) as error:
                planner.plan_fragment(raw,reuse_int_branches=enabled)
            self.assertEqual(error.exception.code,'PRIMITIVE')

    def test_checker_rejects_duplicate_branch_handle(self):
        plan=planner.plan_fragment(CASES['same-true'][0],reuse_int_branches=True)
        program=copy.deepcopy(plan['program'])
        selection=next(i for code in program['codes'].values() for i in code['body'] if i['op']=='select_i64')
        selection['else']=selection['then']
        with self.assertRaises(ResourceError): check_resources(program)

    def test_checker_rejects_missing_owner_retain(self):
        plan=planner.plan_fragment(CASES['same-true'][0],reuse_int_branches=True)
        program=copy.deepcopy(plan['program']);path=plan['binding']['source_map']['branch_owner_reuse'][0]['retain']
        instruction(program,path)['value']='missing-owner'
        with self.assertRaises(ResourceError): check_resources(program)

    def test_provenance_oracle_rejects_corruption(self):
        raw=CASES['same-true'][0];plan=planner.plan_fragment(raw,reuse_int_branches=True)
        for key,value in [('binding',999),('source_owner','wrong-owner'),('retained_owner','wrong-owner'),('branch','ordinary-application'),('branch','conditional-else'),('type_scope','forged-scope')]:
            corrupted=copy.deepcopy(plan);corrupted['binding']['source_map']['branch_owner_reuse'][0][key]=value
            with self.subTest(key=key),self.assertRaises(AssertionError):audit_rows(raw,corrupted)
        for field in ('source','retain','retained_owner'):
            corrupted=copy.deepcopy(plan)
            corrupted['binding']['source_map']['branch_owner_reuse'][0][field]=copy.deepcopy(
                corrupted['binding']['source_map']['branch_owner_reuse'][1][field])
            with self.subTest(field=field),self.assertRaises(AssertionError):audit_rows(raw,corrupted)

    def test_provenance_oracle_rejects_duplicate_rows(self):
        raw=CASES['same-true'][0];plan=planner.plan_fragment(raw,reuse_int_branches=True)
        rows=plan['binding']['source_map']['branch_owner_reuse']
        rows[1]=copy.deepcopy(rows[0])
        with self.assertRaises(AssertionError):audit_rows(raw,plan)

if __name__=='__main__': unittest.main()
