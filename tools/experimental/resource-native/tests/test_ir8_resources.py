"""Reviewed finite host-only resource checks. Never run/emits the checked graph."""
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from resource_ir_v8.body_checker import BodyChecker
from resource_ir_v8.checker import ResourceError, ResourceCheck, check_resources, loads_resources
from resource_ir_v8.budgets import Budget, CanonicalEncoder, CREATION_LIMIT, ORDER_WORK_LIMIT, DERIVED_BYTES
from resource_ir_v8.ownership import State, Symbols, Order
from resource_ir_v8.provenance import Analysis
from resource_ir_v8.declaration_adapter import check_type_ids
from resource_ir_v8.program_schema import preflight, parse, snapshot

FIXTURE=Path(__file__).with_name('fixtures')/'ir8-resources.json'
CASES=json.loads(FIXTURE.read_text())['cases']
BY_NAME={c['name']:c for c in CASES}
EVIDENCE=Path(os.environ['RESOURCE_TEST_EVIDENCE'])
EVIDENCE.mkdir(exist_ok=False)
EVIDENCE_BYTES=0
EVIDENCE_FILES=[]
def save_evidence(name,payload):
    global EVIDENCE_BYTES
    data=payload.encode('utf-8');assert EVIDENCE_BYTES+len(data)<=33554432,'aggregate per-case evidence cap exceeded'
    assert '/' not in name and len(EVIDENCE_FILES)<400
    target=EVIDENCE/name
    with target.open('xb') as f:f.write(data)
    EVIDENCE_BYTES+=len(data)
    EVIDENCE_FILES.append({'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
RULES=('exact_mono_type','down_support','same_group','strict_below','argument_identity','no_once_copy','live_exact_anchor','neutral_same_capsule','closed_preserve_target_access','principal_force_result')
PENDING=('runtime-table-closure','physical-representation-and-Access','model-and-native-ABI','source-proof-and-lowering','single-code-emission','allocator-and-terminal-requalification','GC-replacement','performance')
TOP={'format','ir_sha256','declaration_sha256','types','code_typing','sites','introductions','uses','instructions','provenance','return_summaries','allocation_edges','obligations','counts'}
FACT={'role','capability','storage','node','group','kind','mode','anchor','ticket','ready','view','type','scheme','projection','provenance','authority_source'}
def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def digest(text):return hashlib.sha256(text.encode()).hexdigest()
def program(name):return json.loads(BY_NAME[name]['text'])
def check(name):
    result=loads_resources(BY_NAME[name]['text']);return result,json.loads(result.derived_json)
def instruction_source(raw,path):
    body=raw['entry'] if path['root']=='entry' else raw['functions' if path['root']=='function' else 'codes'][path['name']]['body']
    for segment in path['segments']:body=body[segment]
    return body

def records(d,op,root=None):
    return [r for r in d['instructions'] if r['op']==op and (root is None or r['path']['root']==root)]

class Cases(unittest.TestCase):
    def validate(self,result,raw):
        self.assertIsInstance(result,ResourceCheck)
        self.assertEqual(result.sha256,digest(result.canonical_json))
        self.assertEqual(result.derived_sha256,digest(result.derived_json))
        self.assertEqual(json.loads(result.canonical_json),raw)
        self.assertEqual(result.canonical_json,canon(raw))
        d=json.loads(result.derived_json)
        self.assertEqual(result.derived_json,canon(d));self.assertEqual(set(d),TOP)
        self.assertEqual(d['format'],'resource-ir-v8-resource-analysis/1')
        self.assertEqual(d['ir_sha256'],result.sha256)
        self.assertEqual(d['declaration_sha256'],result.declaration_sha256)
        self.assertEqual(d['counts'],dict(result.counts))
        ids=check_type_ids({k:raw[k] for k in ('layouts','families','signatures','types','schemes','instantiations')})
        for use in d['uses']:
            scheme,args,target,environment=ids.instantiation(use['name'])
            self.assertEqual((use['scheme'],use['arguments'],use['result_type'],use['environment']),(scheme,list(args),target,environment))
        report=dict(result.report());self.assertIs(result.report(),result.report())
        self.assertEqual(report['status'],'checked-resources-only');self.assertEqual(report['pending_gates'],PENDING)
        self.assertEqual([dict(r)['rule'] for r in report['rule_status']],list(RULES))
        for rule_index,status in enumerate(report['rule_status']):
            row=dict(status);n=sum(row['rule'] in o['rules'] for o in d['obligations'])
            self.assertEqual(row['occurrences'],n);self.assertEqual(row['class'],'static' if rule_index<7 else 'runtime')
            self.assertEqual(row['status'],'not-present' if not n else 'checked-symbolically' if rule_index<7 else 'pending-runtime')
        for key in ('types','code_typing','sites','introductions','provenance'):
            self.assertTrue(all(type(r['id']) is int for r in d[key]));self.assertEqual([r['id'] for r in d[key]],list(range(len(d[key]))))
        for key in ('instructions','uses','return_summaries','allocation_edges','obligations'):
            self.assertTrue(all('id' not in r for r in d[key]))
        def check_ref(value,collection,nullable=False):
            if nullable and value is None:return
            self.assertIs(type(value),int);self.assertGreaterEqual(value,0);self.assertLess(value,len(d[collection]))
        def check_path(path):
            self.assertEqual(set(path),{'root','name','segments'});self.assertIn(path['root'],('entry','function','thunk'))
            self.assertEqual(path['name'] is None,path['root']=='entry')
            self.assertIs(type(path['segments']),list)
            for i,segment in enumerate(path['segments']):
                if i%2:self.assertEqual(segment,'body')
                else:self.assertIs(type(segment),int);self.assertGreaterEqual(segment,0)
        for t in d['types']:
            self.assertEqual(set(t),{'id','tag','atom','scheme','index','argument','result','protocol','result_identity'})
            self.assertIn(t['tag'],('closed','rigid','arrow'))
            required={'closed':{'atom'},'rigid':{'scheme','index'},'arrow':{'argument','result','protocol','result_identity'}}[t['tag']]
            for field in set(t)-{'id','tag'}:
                if field not in required:self.assertIsNone(t[field])
            if t['tag']=='arrow':check_ref(t['argument'],'types');check_ref(t['result'],'types')
            if t['tag']=='rigid':self.assertIn(t['scheme'],raw['schemes']);self.assertIs(type(t['index']),int);self.assertGreaterEqual(t['index'],0)
        for code in d['code_typing']:
            self.assertEqual(set(code),{'id','kind','name','type_scope','callable_type','argument','result','captures','body_path'})
            self.assertIn(code['kind'],('function','thunk'));check_path(code['body_path']);check_ref(code['result'],'types')
            if code['kind']=='thunk':self.assertIsNone(code['callable_type']);self.assertIsNone(code['argument'])
            else:check_ref(code['callable_type'],'types');check_ref(code['argument'],'types')
            for capture in code['captures']:self.assertEqual(set(capture),{'name','type','relation'});check_ref(capture['type'],'types')
        for site in d['sites']:
            self.assertEqual(set(site),{'id','path','arm','type_scope','principal_type','category','code','legacy_physical'})
            check_path(site['path']);check_ref(site['principal_type'],'types');check_ref(site['code'],'code_typing',True)
            self.assertIn(site['category'],('DATA','CLOSURE','THUNK','HOLE','APPLICATION','SCALAR','SUM'))
            if site['arm'] is not None:self.assertIs(type(site['arm']),int);self.assertGreaterEqual(site['arm'],0)
            self.assertEqual(site['code'] is not None,site['category'] in ('CLOSURE','THUNK'))
        for intro in d['introductions']:
            self.assertEqual(set(intro),{'id','scheme','container','generalize_path','seal_path','body_type','result_sites'})
            check_ref(intro['container'],'code_typing',True);check_ref(intro['body_type'],'types')
            check_path(intro['generalize_path']);check_path(intro['seal_path']);self.assertTrue(intro['result_sites'])
            self.assertEqual(intro['result_sites'],sorted(set(intro['result_sites'])))
            for site in intro['result_sites']:check_ref(site,'sites')
        for use in d['uses']:
            self.assertEqual(set(use),{'name','scheme','arguments','environment','result_type','occurrences'})
            check_ref(use['result_type'],'types');self.assertTrue(use['occurrences'])
            for argument in use['arguments']:check_ref(argument,'types')
            for path in use['occurrences']:check_path(path);self.assertEqual(instruction_source(raw,path)['instantiation'],use['name'])
        for summary in d['return_summaries']:
            self.assertEqual(set(summary),{'code','type_scope','result_type','result_identity','return_paths'})
            check_ref(summary['code'],'code_typing');check_ref(summary['result_type'],'types')
            for path in summary['return_paths']:
                self.assertEqual(set(path),{'path','value','node','group','provenance','ready','required_ready','support','identity_proof'})
                check_path(path['path']);check_ref(path['provenance'],'provenance')
                self.assertEqual(path['support'],'down_home')
                if path['identity_proof'] is not None:
                    self.assertEqual(set(path['identity_proof']),{'parameter','node'})
                    for value in path['identity_proof'].values():self.assertIs(type(value),int);self.assertGreaterEqual(value,0)
        for edge in d['allocation_edges']:
            self.assertEqual(set(edge),{'from_code','to_code','site'});check_ref(edge['from_code'],'code_typing',True);check_ref(edge['to_code'],'code_typing');check_ref(edge['site'],'sites')
        for row in d['provenance']:
            self.assertEqual(set(row),{'id','value'});value=row['value'];kind=value['kind']
            keys={'allocated':{'kind','site','context'},'parameter':{'kind','code'},'capture':{'kind','code','name'},'field':{'kind','host','field'},'forced':{'kind','cursor'},'choice':{'kind','alternatives'}}
            self.assertIn(kind,keys);self.assertEqual(set(value),keys[kind])
            if kind in ('parameter','capture'):check_ref(value['code'],'code_typing')
            if kind=='allocated':
                check_ref(value['site'],'sites');context=value['context']
                context_keys={'concrete':{'kind'},'introduction':{'kind','intro'},'execution':{'kind','code','scheme'}}
                self.assertIn(context['kind'],context_keys);self.assertEqual(set(context),context_keys[context['kind']])
                if context['kind']=='introduction':check_ref(context['intro'],'introductions')
                if context['kind']=='execution':check_ref(context['code'],'code_typing');self.assertIn(context['scheme'],raw['schemes'])
        paths={}
        for index,r in enumerate(d['instructions']):
            self.assertEqual(set(r),{'path','op','type_scope','inputs','outputs','sites'});check_path(r['path'])
            for site in r['sites']:check_ref(site,'sites')
            self.assertEqual(set(r['path']),{'root','name','segments'})
            self.assertEqual(instruction_source(raw,r['path'])['op'],r['op'])
            paths[canon(r['path'])]=index
            for side in ('inputs','outputs'):
                for f in r[side]:
                    self.assertEqual(set(f),FACT)
                    self.assertTrue(f['role'])
                    if f['kind']=='authority':
                        for k in ('node','ticket','ready','view','type','scheme','projection','provenance'):self.assertIsNone(f[k])
                    if f['kind']=='value':
                        check_ref(f['type'],'types')
                        self.assertEqual(f['scheme'] is not None,f['view']=='SCHEME')
                        check_ref(f['provenance'],'provenance')
                        if f['projection'] is not None:
                            self.assertEqual(set(f['projection']),{'scheme','environment','arguments','use'})
                            self.assertIn(f['projection']['use'],raw['instantiations'])
                            projection=f['projection'];scheme,args,target,environment=ids.instantiation(projection['use'])
                            self.assertEqual((projection['scheme'],projection['arguments'],projection['environment'],f['type']),(scheme,list(args),environment,target))
            if 'out' in instruction_source(raw,r['path']):self.assertEqual([f['role'] for f in r['outputs']],[['out']])
            elif r['op']=='fill':self.assertEqual([f['role'] for f in r['outputs']],[['hole']])
            else:self.assertEqual(r['outputs'],[])
        for o in d['obligations']:
            self.assertEqual(set(o),{'path','role','kind','host_site','operands','expected_type','scope','rules'})
            index=paths[canon(o['path'])];self.assertTrue(o['operands']);self.assertTrue(o['rules'])
            self.assertEqual(o['rules'],[r for r in RULES if r in o['rules']])
            check_ref(o['expected_type'],'types')
            for ref in o['operands']:
                self.assertEqual(set(ref),{'instruction','side','index'});self.assertIs(type(ref['instruction']),int);self.assertGreaterEqual(ref['instruction'],0);self.assertLess(ref['instruction'],len(d['instructions']));self.assertEqual(ref['instruction'],index)
                self.assertIn(ref['side'],('inputs','outputs'));self.assertIs(type(ref['index']),int)
                self.assertGreaterEqual(ref['index'],0);self.assertLess(ref['index'],len(d['instructions'][index][ref['side']]))
            if o['host_site'] is not None:self.assertIs(type(o['host_site']),int);self.assertGreaterEqual(o['host_site'],0);self.assertLess(o['host_site'],len(d['sites']))
        for p in d['provenance']:
            v=p['value'];previous=[]
            if v['kind']=='field':previous=[v['host']]
            elif v['kind']=='forced':previous=[v['cursor']]
            elif v['kind']=='choice':previous=v['alternatives']
            self.assertTrue(all(type(i) is int and 0<=i<p['id'] for i in previous))
        for r in records(d,'instantiate'):
            a,b=r['inputs'][0],r['outputs'][0]
            for k in ('capability','storage','node','group','mode','anchor','ticket','ready','provenance'):self.assertEqual(a[k],b[k])
            self.assertEqual(a['view'],'SCHEME');self.assertEqual(b['view'],'MONO');self.assertIsNone(b['scheme'])
        for r in records(d,'generalize'):
            path=r['path'];prefix=path['segments']+['body']
            seal=next(s for s in records(d,'seal') if s['path']['root']==path['root'] and s['path']['name']==path['name'] and s['path']['segments'][:-1]==prefix)
            a,b=seal['inputs'][0],r['outputs'][0]
            for k in ('capability','storage','node','group','mode','anchor','ticket','ready','provenance','type'):self.assertEqual(a[k],b[k])
            self.assertEqual(b['view'],'SCHEME');self.assertIsNone(b['projection'])
            intro=next(x for x in d['introductions'] if x['generalize_path']==path)
            self.assertEqual(intro['result_sites'],[d['provenance'][b['provenance']]['value']['site']])
        for r in records(d,'application')+records(d,'application_borrow'):
            out=r['outputs'][0];prov=d['provenance'][out['provenance']]['value']
            self.assertEqual(prov['kind'],'allocated');self.assertEqual(d['sites'][prov['site']]['category'],'APPLICATION')
            self.assertFalse(out['ready']);self.assertIsNone(d['sites'][prov['site']]['legacy_physical'])
            for operand in r['inputs'][1:]:self.assertNotEqual(out['node'],operand['node'])
        return d

def install_case(case):
    def test(self):
        if case['accepted']:
            result=loads_resources(case['text'])
            self.validate(result,json.loads(case['text']))
            save_evidence(case['name']+'.derived.json',result.derived_json)
            save_evidence(case['name']+'.report.json',canon(dict(result.report())))
        else:
            with self.assertRaises(ResourceError) as caught:loads_resources(case['text'])
            error=caught.exception
            self.assertEqual(error.layer,case['expected_layer']);self.assertEqual(error.code,case['expected_code'])
            self.assertEqual(error.path,case['expected_path'])
            save_evidence(case['name']+'.rejection.json',canon({'layer':error.layer,'code':error.code,'path':error.path,'message':error.message}))
    setattr(Cases,'test_case_'+case['name'],test)
for _case in CASES:install_case(_case)

class Semantics(unittest.TestCase):
    def test_same_shared_owner_distinct_views(self):
        _,d=check('ready_shared_identity_two_views');views=records(d,'instantiate','entry')
        self.assertEqual(len(views),2)
        a,b=[r['outputs'][0] for r in views]
        self.assertEqual(a['node'],b['node']);self.assertEqual(a['provenance'],b['provenance'])
        self.assertNotEqual(a['storage'],b['storage']);self.assertNotEqual(a['type'],b['type'])
        self.assertNotEqual(a['projection']['environment'],b['projection']['environment'])
        summary=d['return_summaries'][0]
        self.assertEqual(summary['result_identity'],'unknown');self.assertIsNone(summary['return_paths'][0]['identity_proof'])
    def test_pending_intro_is_actual_application(self):
        _,d=check('pending_shared_three_lambda_two_application_shape')
        g=records(d,'generalize','entry')[0]['outputs'][0]
        p=d['provenance'][g['provenance']]['value']
        self.assertEqual(p['kind'],'allocated');self.assertEqual(d['sites'][p['site']]['category'],'APPLICATION');self.assertFalse(g['ready'])
    def test_dead_parameter_vectors_remain_distinct(self):
        _,d=check('dead_parameter_two_complete_vectors');out=[r['outputs'][0] for r in records(d,'instantiate','entry')]
        self.assertEqual(out[0]['type'],out[1]['type']);self.assertNotEqual(out[0]['projection']['arguments'],out[1]['projection']['arguments'])
        self.assertNotEqual(out[0]['projection']['environment'],out[1]['projection']['environment'])
    def test_projection_unknown_does_not_claim_E0(self):
        _,d=check('concrete_callback_foreign_projected_capture');found=set()
        for r in d['instructions']:
            for f in r['inputs']+r['outputs']:
                if f['kind']!='value':continue
                kind=d['provenance'][f['provenance']]['value']['kind']
                if kind in ('parameter','capture'):
                    found.add(kind);self.assertIsNone(f['projection']);self.assertEqual(f['view'],'MONO')
        self.assertEqual(found,{'parameter','capture'})
        self.assertTrue(records(d,'instantiate','entry'))
    def test_moved_loan_and_promotion(self):
        _,d=check('loan_view_move_and_promotion');move=next(r for r in records(d,'instantiate') if r['inputs'][0]['mode']=='loan')
        self.assertEqual(move['inputs'][0]['anchor'],move['outputs'][0]['anchor'])
        promoted=next(r for r in records(d,'retain') if r['inputs'][0]['mode']=='loan')
        self.assertEqual(promoted['outputs'][0]['mode'],'own');self.assertIsNone(promoted['outputs'][0]['anchor'])
        self.assertNotEqual(promoted['inputs'][0]['capability'],promoted['outputs'][0]['capability'])
    def test_physical_alias_is_preserved(self):
        _,d=check('closed_full_contract_alias_interchange')
        b=next(c for c in d['code_typing'] if c['name']=='actual_B')
        site=next(s for s in d['sites'] if s['code']==b['id'])
        self.assertEqual(site['legacy_physical'],'@B')
    def test_retained_argument_identity_uses_original_capability(self):
        _,d=check('closed_identity_retained_parameter');retain=records(d,'retain','function')[0]
        ret=d['return_summaries'][0]['return_paths'][0];proof=ret['identity_proof']
        self.assertEqual(proof['parameter'],retain['inputs'][0]['capability'])
        self.assertNotEqual(proof['parameter'],ret['value']);self.assertEqual(proof['node'],ret['node'])
    def test_api_snapshot_immutable_no_executor(self):
        raw=program('concrete_scalar');result=check_resources(raw);before=result.canonical_json
        raw['entry'][1]['value']=999;self.assertEqual(result.canonical_json,before)
        with self.assertRaises((AttributeError,dataclasses.FrozenInstanceError)):result.sha256='forged'
        self.assertFalse(hasattr(result,'__dict__'))
        self.assertFalse(any(hasattr(result,k) for k in ('run','generate','data','execute','native_eligible')))
        self.assertFalse(any(n=='resource_ir' or n.startswith('resource_ir.') for n in sys.modules))
        second=loads_resources(before);self.assertEqual(second.derived_json,result.derived_json)
    def test_scheme_authority_parent_loan_survives_child(self):
        _,d=check('authority_A02_second_intro_preserves_parent_loan');gs=records(d,'generalize','entry')
        self.assertEqual(len(gs),2)
        auth=gs[1]['inputs'][0];self.assertEqual(auth['kind'],'authority');self.assertIsNone(auth['view'])
        moves=records(d,'instantiate','entry');self.assertTrue(any(r['inputs'][0]['mode']=='loan' for r in moves))
        borrow=records(d,'borrow','entry')[0];source=borrow['inputs'][0];loan=borrow['outputs'][0]
        move=next(r for r in moves if r['inputs'][0]['capability']==loan['capability'])
        end=next(r for r in records(d,'end_borrow','entry') if r['inputs'][0]['capability']==loan['capability'])
        self.assertEqual(loan['anchor'],{'kind':'owner','capability':source['capability']})
        self.assertEqual(move['outputs'][0]['anchor'],loan['anchor']);self.assertEqual(end['inputs'][0]['anchor'],loan['anchor'])
        owner_drop=next(r for r in records(d,'drop','entry') if r['inputs'][0]['capability']==source['capability'])
        for key in ('capability','storage','node','group','view','scheme','projection','provenance'):
            self.assertEqual(source[key],owner_drop['inputs'][0][key])
        self.assertEqual(auth['capability'],source['capability'])

    def test_direct_ingress_defensive_cases(self):
        controls=[]
        p=program('concrete_scalar');p['cycle']=p;controls.append(('cycle',p,'JSON'))
        for name,value,code in [('custom',object(),'JSON'),('surrogate','\ud800','UTF8'),('oversized_integer',1<<65,'INTEGER')]:
            p=program('concrete_scalar');p['invalid']=value;controls.append((name,p,code))
        for name,raw,code in controls:
            with self.subTest(name=name):
                with self.assertRaises(ResourceError) as e:check_resources(raw)
                self.assertEqual((e.exception.layer,e.exception.code,e.exception.path),('schema',code,'program'))

    def test_adapter_shared_depth32_DAG_preserved(self):
        cases=json.loads((FIXTURE.parent/'ir8-declarations.json').read_text())['cases']
        raw=json.loads(next(c['text'] for c in cases if c['name']=='depth32_shared_dag_not_expanded_tree'))
        ids=check_type_ids(raw)
        self.assertLess(len(ids.rows),100)
        for row in ids.rows:
            if row[0]=='arrow':
                self.assertIs(type(row[1]),int);self.assertIs(type(row[2]),int)
                self.assertEqual(row[1],row[2])
        self.assertFalse(hasattr(ids,'run'))

    def test_curried_result_context_and_pending_summary(self):
        for fixture,callback in [('curried_const_complete_ib_bi_views','constant'),('two_scheme_closed_higher_order_capture','apply')]:
            _,d=check(fixture);code=next(c for c in d['code_typing'] if c['name']==callback)
            closure=next(r for r in records(d,'closure','function') if r['path']['name']==callback)
            out=closure['outputs'][0];term=d['provenance'][out['provenance']]['value']
            self.assertEqual(out['view'],'MONO');self.assertIsNone(out['scheme']);self.assertIsNone(out['projection'])
            self.assertEqual(term['context'],{'kind':'execution','code':code['id'],'scheme':'S'})
            self.assertEqual(out['type'],code['result']);self.assertEqual(d['sites'][term['site']]['type_scope'],'S')
            for capture in closure['inputs'][1:]:
                self.assertEqual(capture['view'],'MONO');self.assertIsNone(capture['projection'])
                self.assertEqual(d['provenance'][capture['provenance']]['value']['kind'],'parameter')
            summary=d['return_summaries'][code['id']]['return_paths'][0]
            self.assertEqual(summary['provenance'],out['provenance']);self.assertEqual(summary['node'],out['node'])
        _,d=check('pending_shared_three_lambda_two_application_shape')
        apps=records(d,'application','function');self.assertTrue(apps)
        for app in apps:
            code=next(c for c in d['code_typing'] if c['name']==app['path']['name'])
            ret=d['return_summaries'][code['id']]['return_paths'][0]
            self.assertEqual(ret['provenance'],app['outputs'][0]['provenance'])
            self.assertEqual(ret['node'],app['outputs'][0]['node']);self.assertFalse(ret['ready'])

class Boundaries(unittest.TestCase):
    def error(self,fn,code,path):
        with self.assertRaises(ResourceError) as e:fn()
        self.assertEqual((e.exception.layer,e.exception.code,e.exception.path),('bounds',code,path))
    def test_B01_creation_exact(self):
        b=Budget();target=[];b.charge(CREATION_LIMIT-2);b.record_append(target,value=1)
        self.assertEqual(b.creation_units,CREATION_LIMIT);self.assertEqual(target,[{'value':1}])
    def test_B02_creation_batch_one_over_atomic(self):
        b=Budget();target=[];b.charge(CREATION_LIMIT-1)
        self.error(lambda:b.record_append(target,value=1),'ANALYSIS_ROWS','analysis.creation_units')
        self.assertEqual(b.creation_units,CREATION_LIMIT-1);self.assertEqual(target,[])
    def test_B03_order_work_exact_and_copy(self):
        b=Budget();o=Order(b);o.add(0,1,True);before=b.creation_units;o.copy()
        self.assertGreater(b.creation_units,before);self.assertEqual(b.order_edge_examinations,0)
        b.examine(ORDER_WORK_LIMIT-1);self.assertTrue(o.below(1,0,strict=True))
        self.assertEqual(b.order_edge_examinations,ORDER_WORK_LIMIT)
    def test_B04_order_work_one_over(self):
        b=Budget();o=Order(b);o.add(0,1,True);b.examine(ORDER_WORK_LIMIT)
        self.error(lambda:o.below(1,0,strict=True),'ORDER_WORK','analysis.order_edge_examinations')
        self.assertEqual(b.order_edge_examinations,ORDER_WORK_LIMIT)
    def encoder_prefix(self):
        e=CanonicalEncoder();e.emit(b'[');shared='é\n\x01';e.string(shared);e.emit(b',');e.string(shared);e.emit(b',"')
        return e
    def test_B05_derived_exact_with_escapes_and_shared_strings(self):
        e=self.encoder_prefix();remaining=DERIVED_BYTES-e.size-2
        while remaining:
            n=min(4096,remaining);e.emit(b'a'*n);remaining-=n
        e.emit(b'"]');text,h=e.finish()
        self.assertEqual(e.size,DERIVED_BYTES);self.assertEqual(len(text.encode()),DERIVED_BYTES);self.assertEqual(digest(text),h)
        self.assertTrue(all(len(c)<=4096 for c in e.chunks));self.assertEqual(json.loads(text)[:2],['é\n\x01']*2)
    def test_B06_derived_one_over_atomic_append(self):
        e=self.encoder_prefix()
        while e.size<DERIVED_BYTES-1:
            e.emit(b'a'*min(4096,DERIVED_BYTES-1-e.size))
        prior=(e.size,len(e.chunks),bytes(e.buffer))
        self.error(lambda:e.emit(b'"]'),'DERIVED_BYTES','analysis.derived_bytes')
        self.assertEqual((e.size,len(e.chunks),bytes(e.buffer)),prior)
    def analysis(self):
        declarations=check_type_ids({k:{} for k in ('layouts','families','signatures','types','schemes','instantiations')})
        b=Budget();a=Analysis(b,declarations);return b,a
    def test_B07_choice_exact_remaining(self):
        b,a=self.analysis();n=1000;before=b.creation_units;b.charge(CREATION_LIMIT-before-3-n)
        # Opaque references test container budgeting only, not provenance validity.
        result=a.choice([0]*n);self.assertEqual(b.creation_units,CREATION_LIMIT)
        self.assertEqual(len(a.provenance[result]['value']['alternatives']),n)
        print('B07 budget-only choice trace: row+inner+inventory=3; references=1000; final=65536; no provenance admission claim')
    def test_B08_choice_one_more_reference_atomic(self):
        b,a=self.analysis();n=1000;b.charge(CREATION_LIMIT-b.creation_units-3-n);prior=b.creation_units
        self.error(lambda:a.choice([0]*(n+1)),'ANALYSIS_ROWS','analysis.creation_units')
        self.assertEqual(b.creation_units,prior);self.assertEqual(a.provenance,[])
        print('B08 budget-only choice trace: required=1004; remaining=1003; no insertion; no provenance admission claim')
    def nonempty_state(self):
        b=Budget();s=State(b);symbols=Symbols(b);g=symbols.fresh('groups');s.order.add(g,g+1,True)
        s.bind('key',symbols.key(g),'helper.key');return b,s
    def copy_cost(self,s):return 2+len(s.values)+len(s.used)+len(s.order.edges)+len(s.order.adjacency)+sum(map(len,s.order.adjacency.values()))
    def test_B11_state_copy_exact_remaining(self):
        b,s=self.nonempty_state();cost=self.copy_cost(s);b.charge(CREATION_LIMIT-b.creation_units-cost);before=(s.values.copy(),s.used.copy(),s.order.edges.copy())
        other=s.copy();self.assertEqual(b.creation_units,CREATION_LIMIT);self.assertEqual((s.values,s.used,s.order.edges),before)
        self.assertIsNot(other.values,s.values);self.assertIsNot(other.order.edges,s.order.edges)
    def test_B12_state_copy_one_member_over_atomic(self):
        b,s=self.nonempty_state();cost=self.copy_cost(s);b.charge(CREATION_LIMIT-b.creation_units-cost+1);prior=b.creation_units
        self.error(s.copy,'ANALYSIS_ROWS','analysis.creation_units');self.assertEqual(b.creation_units,prior)
        self.assertEqual(set(s.values),{'key'});self.assertEqual(s.used,{'key'})
    def test_schema_instruction_exact_and_one_over_helper(self):
        p=program('concrete_scalar');p['entry']=[{'op':'drop','value':'unbound'}]*9999+[{'op':'finish'}]
        preflight(p,Budget()) # Schema helper only: intentionally not resource-accepted.
        p['entry'].insert(0,{'op':'drop','value':'unbound'})
        with self.assertRaises(ResourceError) as e:preflight(p,Budget())
        self.assertEqual((e.exception.layer,e.exception.code,e.exception.path),('schema','INSTRUCTION_COUNT','program.instructions'))
    def test_parse_depth_exact_and_one_over_helper(self):
        self.assertIsInstance(parse('['*32+'0'+']'*32),list)
        with self.assertRaises(ResourceError) as e:parse('['*33+'0'+']'*33)
        self.assertEqual((e.exception.layer,e.exception.code,e.exception.path),('schema','INPUT_DEPTH','program'))

    def test_schema_code_site_exact_and_one_over_helper(self):
        p=program('concrete_scalar');p['entry']=[{'op':'finish'}]
        p['codes']={str(i):{'result':'#i64','captures':{},'type_scope':None,'body':[{'op':'return','value':'unbound'}]} for i in range(2048)}
        preflight(p,Budget()) # Structural helper only; no resource acceptance.
        p['codes']['extra']=p['codes']['0']
        with self.assertRaises(ResourceError) as e:preflight(p,Budget())
        self.assertEqual((e.exception.layer,e.exception.code,e.exception.path),('schema','SITE_CODE_COUNT','program.sites_and_codes'))
    def test_direct_input_oversized_string_is_byte_bounded(self):
        p=program('concrete_scalar');p['oversized']='x'*(DERIVED_BYTES+1)
        with self.assertRaises(ResourceError) as e:snapshot(p)
        self.assertEqual((e.exception.layer,e.exception.code,e.exception.path),('schema','INPUT_BYTES','program'))

class PrivateDefenses(unittest.TestCase):
    def seal_state(self,*,ticket,category='HOLE',context_kind='introduction'):
        raw=program('ready_shared_identity_two_views');budget=Budget()
        ids=check_type_ids({k:raw[k] for k in ('layouts','families','signatures','types','schemes','instantiations')})
        checker=BodyChecker(raw,ids,budget);checker.prepare()
        site=next(s for s in checker.a.sites if s['path']['root']=='entry' and s['category']=='CLOSURE')
        site['category']=category # Private malformed-state control, never a public artifact.
        context={'kind':'introduction','intro':0} if context_kind=='introduction' else {'kind':'concrete'}
        state=State(budget,home=0);value=checker.allocated(site['id'],context,0,ids.scheme('S')[1],ticket=ticket)
        state.bind('f',value,'private.f')
        seal=raw['entry'][1]['body'][-1]
        return checker,state,seal
    def test_private_raw_hole_ticket_cannot_seal(self):
        c,s,i=self.seal_state(ticket=True)
        with self.assertRaises(ResourceError) as e:c.check_block([i],s,{'kind':'introduction','intro':0},intro=0)
        self.assertEqual((e.exception.layer,e.exception.code,e.exception.path),('resource','UNFILLED_HOLE','entry[1].body[1]'))
        self.assertIn('f',s.values)
    def test_private_spent_hole_category_cannot_seal(self):
        c,s,i=self.seal_state(ticket=False)
        with self.assertRaises(ResourceError) as e:c.check_block([i],s,{'kind':'introduction','intro':0},intro=0)
        self.assertEqual((e.exception.layer,e.exception.code,e.exception.path),('resource','SEAL','entry[1].body[1]'))
    def test_private_foreign_origin_cannot_reseal(self):
        c,s,i=self.seal_state(ticket=False,category='CLOSURE',context_kind='concrete')
        with self.assertRaises(ResourceError) as e:c.check_block([i],s,{'kind':'introduction','intro':0},intro=0)
        self.assertEqual((e.exception.layer,e.exception.code,e.exception.path),('resource','SEAL','entry[1].body[1]'))
    def test_private_broken_anchor_move_is_atomic(self):
        for mode in ('missing','loan_is_not_owner'):
            with self.subTest(mode=mode):
                b=Budget();s=State(b);symbols=Symbols(b);g=symbols.fresh('groups')
                owner=symbols.value(g,0,None);anchor={'kind':'owner','capability':owner.capability}
                if mode=='loan_is_not_owner':s.bind('not_owner',symbols.changed(owner,mode='loan',anchor={'kind':'activation','code':0}),'private.not_owner')
                loan=symbols.copied_handle(owner,mode='loan',anchor=anchor);s.bind('loan',loan,'private.loan')
                with self.assertRaises(ResourceError) as e:s.move('loan','private.move')
                self.assertEqual((e.exception.layer,e.exception.code,e.exception.path),('resource','ANCHOR','private.move'))
                self.assertIs(s.values['loan'],loan)

if __name__=='__main__':
    result=unittest.main(verbosity=2,exit=False).result
    manifest={'schema':'ir8-resource-host-case-evidence/1','payload_files':EVIDENCE_FILES,'payload_bytes':EVIDENCE_BYTES,'fixed_cases':len(CASES),'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped),'graph_execution':False}
    (EVIDENCE/'MANIFEST.json').write_text(canon(manifest)+'\n')
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
