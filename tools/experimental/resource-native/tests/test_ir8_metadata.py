"""Finite static metadata qualification. No graph/model/native/source execution."""
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resource_ir_v8.metadata import MetadataClosure, MetadataError, check_metadata, loads_metadata, _verify_derived
from resource_ir_v8.checker import check_resources, ResourceError
from resource_ir_v8 import metadata_budget as mb

FIXTURE = Path(__file__).with_name('fixtures') / 'ir8-metadata.json'
CASES = json.loads(FIXTURE.read_text())['cases']
BY_NAME = {c['name']: c for c in CASES}
PHASE_CASES = json.loads(FIXTURE.with_name('ir8-metadata-boundaries.json').read_text())['cases']
EVIDENCE = Path(os.environ['METADATA_TEST_EVIDENCE'])
EVIDENCE.mkdir(exist_ok=False)
EVIDENCE_FILES = []
EVIDENCE_BYTES = 0
TABLES = ('types','callable_contracts','schemes','environments','codes','code_executions','shapes','shape_typing','representations','nominal_fields','families','type_resolutions','representation_resolutions','sites','site_executions','slots','accesses','introductions','uses','transports')
EXTRA = ('boundaries','coverage','storage_entries','storage_objects','access_transport_resolution_rows','metadata_records')
GUARDS = ('registered-membership','exact-site-origin','physical-origin','exact-mono-contract','symbolic-before-projection','same-neutral-capsule','preserve-foreign-access','live-exact-anchor','acquire-before-release','existing-support','code-association','return-identity','no-scheme-value','pending-all-before-publish','scope-token','complete-vector','same-handle-view-move','owner-mode','ticket-free','no-dependent-loans','child-discharge','scheme-input','view-move-mode','return-linear-contract','fill-linear-contract','state-category','application-slots')
PENDING = ('native-ABI-and-sizeof','emitter-storage-correspondence','dynamic-origin-representation-and-edges','model-native-and-lifecycle','source-proof-and-lowering','single-code-emission','GC-replacement','performance')
TOP = set(TABLES + ('format','core_sha256','ir_sha256','declaration_sha256','resource_sha256','type_remap','environment_remap','boundaries','coverage','storage_inventory','counts','native_status'))
PHASES = {'THUNK':('busy-demand','thunk-dispatch','cursor-return','reverse-pending','memo-publish','memo-read'),'APPLICATION':('busy-demand','application-dispatch','cursor-return','reverse-pending','memo-publish','memo-read'),'HOLE':('hole-demand','busy-demand','fill','indirect-dispatch','cursor-return','reverse-pending','memo-publish','memo-read')}
INSTRUCTIONS = ('generalize','seal','instantiate','retain','borrow','drop','end_borrow','select_i64','case_i64','case_fields_i64')
REPORT_KEYS = ('status','scope','ir_sha256','declaration_sha256','resource_sha256','metadata_sha256','counts','table_row_status','native_static_status','boundary_status','host_statistics','pending_gates')
def canon(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def digest(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()
def raw(name): return json.loads(BY_NAME[name]['text'])
def checked(name):
    r=loads_metadata(BY_NAME[name]['text']); return r,json.loads(r.metadata_json)
def census(value):
    pending=[value]; n=0
    while pending:
        v=pending.pop()
        if type(v) is dict: n+=1;pending.extend(v.values())
        elif type(v) is list: pending.extend(v)
    return n
def save(name,value):
    global EVIDENCE_BYTES
    data=value.encode('utf-8');assert EVIDENCE_BYTES+len(data)<=134217728
    assert '/' not in name and len(EVIDENCE_FILES)<400
    with (EVIDENCE/name).open('xb') as f: f.write(data)
    EVIDENCE_BYTES+=len(data);EVIDENCE_FILES.append({'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
def ref(table,index):
    assert type(index) is int and 0<=index<len(table);return table[index]
def resolution(d,ty,env):
    rows=[r for r in d['type_resolutions'] if (r['type'],r['env'])==(ty,env)]
    assert len(rows)==1;return rows[0]['result']
def source_instruction(p,path):
    body=p['entry'] if path['root']=='entry' else p['functions' if path['root']=='function' else 'codes'][path['name']]['body']
    for segment in path['segments']:body=body[segment]
    return body

def pool_bytes(d):
    strings=set()
    for r in d['schemes']+d['uses']:strings.add(r['name'])
    for r in d['codes']:
        strings.update((r['name'],canon(r['body_path'])));strings.update(x['name'] for x in r['captures'])
    for r in d['uses']:strings.update(canon(x) for x in r['occurrences'])
    for r in d['shapes']:
        if r['source']['kind']=='legacy':strings.add(r['source']['reference'])
    for r in d['sites']:
        strings.add(canon(r['path']))
        if r['legacy_physical'] is not None:strings.add(r['legacy_physical'])
    for r in d['types']:
        if r['tag']=='closed':strings.add(r['atom'])
    for r in d['nominal_fields']:strings.add(r['name'])
    for r in d['families']:strings.add(r['name']);strings.update(x['name'] for x in r['variants'])
    for r in d['introductions']:strings.update((canon(r['generalize_path']),canon(r['seal_path'])))
    return sum(len(x.encode('utf-8'))+1 for x in strings)

class RawCases(unittest.TestCase):
    def validate(self,result,p):
        self.assertIsInstance(result,MetadataClosure)
        self.assertEqual(result.canonical_json,canon(p));self.assertEqual(result.ir_sha256,digest(result.canonical_json))
        self.assertEqual(result.metadata_sha256,digest(result.metadata_json))
        d=json.loads(result.metadata_json);self.assertEqual(result.metadata_json,canon(d));self.assertEqual(set(d),TOP)
        lower=check_resources(p);proof=json.loads(lower.derived_json)
        self.assertEqual(result.resource_sha256,lower.derived_sha256);self.assertEqual(result.declaration_sha256,lower.declaration_sha256)
        for name in ('ir_sha256','declaration_sha256','resource_sha256'):self.assertEqual(d[name],getattr(result,name))
        self.assertEqual(d['format'],'resource-ir-v8-static-metadata/1')
        self.assertEqual(d['native_status'],{'state':'abi-unbound','typed_static_bytes':None,'graph_executed':False,'source_admitted':False})
        for table in TABLES+('boundaries','coverage','storage_inventory'):
            self.assertEqual([r['id'] for r in d[table]],list(range(len(d[table]))))
            for r in d[table]:self.assertIs(type(r['id']),int)
        self.assertEqual(tuple(k for k,v in result.counts),TABLES+EXTRA)
        self.assertEqual(dict(result.counts),d['counts']);self.assertEqual(set(d['counts']),set(TABLES+EXTRA))
        for table in TABLES+('boundaries','coverage'):self.assertEqual(d['counts'][table],len(d[table]))
        self.assertEqual(d['counts']['metadata_records'],census(d))
        R=sum(len(d[t]) for t in ('type_resolutions','representation_resolutions','accesses','transports'))
        self.assertEqual(d['counts']['access_transport_resolution_rows'],R);self.assertLessEqual(R,65536)
        self.assertLessEqual(len(d['types']),4096);self.assertLessEqual(len(d['environments']),1024)
        self.assertEqual([(r['type'],r['env']) for r in d['type_resolutions']],[(r['type'],r['env']) for r in d['representation_resolutions']])
        types=d['types'];schemes=d['schemes'];envs=d['environments']
        self.assertEqual(envs[0],{'id':0,'scheme':None,'mode':'CONCRETE','arguments':[]})
        for ty in types:
            self.assertEqual(set(ty),{'id','tag','atom','scheme','index','argument','result','protocol','result_identity'})
            if ty['tag']=='arrow':
                self.assertEqual(ty['protocol'],'repeat');ref(types,ty['argument']);ref(types,ty['result'])
            elif ty['tag']=='rigid':self.assertLess(ty['index'],ref(schemes,ty['scheme'])['parameters'])
            else:self.assertEqual(ty['tag'],'closed')
        depths=[]
        for ty in types:
            if ty['tag']=='arrow':
                self.assertLess(ty['argument'],ty['id']);self.assertLess(ty['result'],ty['id']);depth=1+max(depths[ty['argument']],depths[ty['result']])
            else:depth=1
            depths.append(depth)
        self.assertEqual(depths,sorted(depths));self.assertLessEqual(max(depths,default=0),32)
        contracts=[dict(id=i,type=t['id'],argument=t['argument'],result=t['result'],protocol=t['protocol'],result_identity=t['result_identity']) for i,t in enumerate(t for t in types if t['tag']=='arrow')]
        self.assertEqual(d['callable_contracts'],contracts)
        for e in envs[1:]:
            s=ref(schemes,e['scheme']);self.assertEqual(len(e['arguments']),s['parameters'])
            if e['mode']=='NEUTRAL':
                self.assertEqual(e['id'],s['neutral_env'])
                for i,t in enumerate(e['arguments']):self.assertEqual((types[t]['tag'],types[t]['scheme'],types[t]['index']),('rigid',s['id'],i))
            else:self.assertEqual(e['mode'],'CLOSED')
        for use in d['uses']:
            e=envs[use['env']];self.assertEqual((use['scheme'],use['arguments']),(e['scheme'],e['arguments']))
            self.assertEqual(use['result_type'],resolution(d,schemes[use['scheme']]['body'],use['env']))
        for r in d['type_resolutions']:
            ty=types[r['type']];out=types[r['result']];env=envs[r['env']]
            if ty['tag']=='closed':self.assertEqual(ty,out)
            elif ty['tag']=='rigid':self.assertEqual(r['result'],env['arguments'][ty['index']]);self.assertEqual(ty['scheme'],env['scheme'])
            else:
                self.assertEqual(out['tag'],'arrow');self.assertEqual((out['argument'],out['result']),(resolution(d,ty['argument'],r['env']),resolution(d,ty['result'],r['env'])))
                self.assertEqual((out['protocol'],out['result_identity']),(ty['protocol'],ty['result_identity']))
        self.assertEqual(len(d['codes']),len(p['functions'])+len(p['codes']))
        for c in d['codes']:
            actual=[e['env'] for e in d['code_executions'] if e['code']==c['id']]
            lawful=[0] if c['scope'] is None else [e['id'] for e in envs if e['scheme']==c['scope']]
            self.assertEqual(actual,lawful)
            if c['kind']=='thunk':self.assertIsNone(c['expected_protocol']);self.assertEqual(c['expected_identity_flag'],0)
            else:self.assertEqual(c['expected_identity_flag'],int(types[c['callable_type']]['result_identity']=='argument'))
        self.check_schemas(d,proof);self.check_origins(d);self.check_edges(d,proof);self.check_storage(d)
        report=dict(result.report());self.assertIs(result.report(),result.report());self.assertEqual(tuple(k for k,v in result.report()),REPORT_KEYS)
        self.assertEqual(report['status'],'checked-static-metadata-only');self.assertEqual(report['pending_gates'],PENDING)
        stats=dict(report['host_statistics']);self.assertEqual(stats['metadata_records'],census(d));self.assertEqual(stats['metadata_utf8_bytes'],len(result.metadata_json.encode()))
        self.assertLessEqual(stats['creation_units'],2097152);self.assertLessEqual(stats['work_units'],16777216)
        native=dict(report['native_static_status']);self.assertEqual(native['classification'],'abi-unbound');self.assertIsNone(native['measured_bytes']);self.assertIs(native['actual_emitted_rows_verified'],False)
        self.assertEqual(native['string_pool_bytes'],pool_bytes(d))
        guards=dict(report['boundary_status'])['guards'];self.assertEqual(tuple(dict(g)['guard'] for g in guards),GUARDS)
        for g in guards:
            g=dict(g);n=sum(g['guard'] in b['guards'] for b in d['boundaries']);self.assertEqual(g['occurrences'],n);self.assertEqual(g['status'],'derived-pending-runtime' if n else 'not-present')
        return d
    def check_schemas(self,d,proof):
        schemas={
          'types':'id tag atom scheme index argument result protocol result_identity',
          'callable_contracts':'id type argument result protocol result_identity','schemes':'id name parameters body neutral_env intro','environments':'id scheme mode arguments',
          'codes':'id kind name scope callable_type argument result captures body_path expected_protocol expected_identity_flag','code_executions':'id code env callable_type argument result captures',
          'shapes':'id source kind argument_rep result_rep','shape_typing':'id shape type scope contract','representations':'id shape typing ready_kind','nominal_fields':'id shape variant position name type declared_rep','families':'id name shape variants',
          'type_resolutions':'id type env result','representation_resolutions':'id type env representation','sites':'id path arm scope principal_type category code legacy_physical context','site_executions':'id site env origin_kind principal_type representation code_execution',
          'slots':'id site role type relation','accesses':'id site origin_env mode use_env type scheme','introductions':'id scheme container generalize_path seal_path body_type result_sites','uses':'id name scheme arguments env result_type occurrences','transports':'id source_access projection_env result_access kind',
          'boundaries':'id key principal_type resolution_env access_rule guards','coverage':'id source boundaries resolutions slots','storage_inventory':'id kind key count element_kind emission_status',
          'type_remap':'resource_type metadata_type','environment_remap':'resource_environment environment'}
        for table,fields in schemas.items():
            self.assertIs(type(d[table]),list)
            for row in d[table]:self.assertIs(type(row),dict);self.assertEqual(set(row),set(fields.split()))
        def reference(value,table,nullable=False):
            if nullable and value is None:return
            self.assertIs(type(value),int);self.assertGreaterEqual(value,0);self.assertLess(value,len(d[table]))
        def path(p):
            self.assertEqual(set(p),{'root','name','segments'});self.assertIn(p['root'],('entry','function','thunk'));self.assertEqual(p['name'] is None,p['root']=='entry');self.assertIs(type(p['segments']),list)
            for i,x in enumerate(p['segments']):
                if i%2:self.assertEqual(x,'body')
                else:self.assertIs(type(x),int);self.assertGreaterEqual(x,0)
        refs={
          'callable_contracts':{'type':'types','argument':'types','result':'types'},'schemes':{'body':'types','neutral_env':'environments','intro':'introductions'},'environments':{'scheme':'schemes?'},
          'codes':{'scope':'schemes?','callable_type':'types?','argument':'types?','result':'types'},'code_executions':{'code':'codes','env':'environments','callable_type':'types?','argument':'types?','result':'types'},
          'shapes':{'argument_rep':'representations?','result_rep':'representations?'},'shape_typing':{'shape':'shapes','type':'types','scope':'schemes?','contract':'callable_contracts?'},'representations':{'shape':'shapes','typing':'shape_typing'},'nominal_fields':{'shape':'shapes','type':'types','declared_rep':'representations'},'families':{'shape':'shapes'},
          'type_resolutions':{'type':'types','env':'environments','result':'types'},'representation_resolutions':{'type':'types','env':'environments','representation':'representations'},'sites':{'scope':'schemes?','principal_type':'types','code':'codes?'},'site_executions':{'site':'sites','env':'environments','principal_type':'types','representation':'representations','code_execution':'code_executions?'},
          'slots':{'site':'sites','type':'types'},'accesses':{'site':'sites','origin_env':'environments','use_env':'environments?','type':'types','scheme':'schemes?'},'introductions':{'scheme':'schemes','body_type':'types'},'uses':{'scheme':'schemes','env':'environments','result_type':'types'},'transports':{'source_access':'accesses','projection_env':'environments?','result_access':'accesses'},'boundaries':{'principal_type':'types?','resolution_env':'environments?'},'type_remap':{'metadata_type':'types'},'environment_remap':{'environment':'environments'}}
        for table,fields in refs.items():
            for row in d[table]:
                for field,target in fields.items():reference(row[field],target.rstrip('?'),target.endswith('?'))
        for t in d['types']:
            active={'closed':{'atom'},'rigid':{'scheme','index'},'arrow':{'argument','result','protocol','result_identity'}}[t['tag']]
            for field in set(t)-{'id','tag'}:
                if field not in active:self.assertIsNone(t[field])
            if t['tag']=='closed':self.assertIs(type(t['atom']),str)
            elif t['tag']=='rigid':reference(t['scheme'],'schemes');self.assertIs(type(t['index']),int)
            else:self.assertIn(t['result_identity'],('unknown','argument'))
        self.assertEqual([r['resource_type'] for r in d['type_remap']],list(range(len(proof['types']))))
        self.assertEqual([r['resource_environment'] for r in d['environment_remap']],['E'+str(i) for i in range(proof['counts']['environments'])])
        for e in d['environments']:
            self.assertIn(e['mode'],('CONCRETE','NEUTRAL','CLOSED'))
            for t in e['arguments']:reference(t,'types')
        for c in d['codes']:
            path(c['body_path']);self.assertIn(c['kind'],('function','thunk'));self.assertEqual(c['callable_type'] is None,c['kind']=='thunk');self.assertEqual(c['argument'] is None,c['kind']=='thunk');self.assertIs(type(c['expected_identity_flag']),int)
        for table in ('codes','code_executions'):
            for c in d[table]:
                self.assertEqual([x['name'] for x in c['captures']],sorted(x['name'] for x in c['captures']))
                for x in c['captures']:self.assertEqual(set(x),{'name','type','relation'});reference(x['type'],'types');self.assertIn(x['relation'],('same','down','below'))
        for x in d['code_executions']:
            c=d['codes'][x['code']]
            for key in ('callable_type','argument','result'):self.assertEqual(x[key],None if c[key] is None else resolution(d,c[key],x['env']))
            self.assertEqual(x['captures'],[dict(name=v['name'],relation=v['relation'],type=resolution(d,v['type'],x['env'])) for v in c['captures']])
        for s in d['shapes']:
            source=s['source'];self.assertEqual(set(source),{'legacy':{'kind','reference'},'canonical-arrow':{'kind','type'},'scoped-open':{'kind','scheme','type'}}[source['kind']]);self.assertIn(s['kind'],('I64','BOOL','DATA','SUM','REPEAT','OPEN'))
            self.assertEqual(s['argument_rep'] is not None,s['kind']=='REPEAT');self.assertEqual(s['result_rep'] is not None,s['kind']=='REPEAT')
            if 'type' in source:reference(source['type'],'types')
            if 'scheme' in source:reference(source['scheme'],'schemes')
        for t in d['shape_typing']:
            shape=d['shapes'][t['shape']];ty=d['types'][t['type']];self.assertEqual(t['id'],t['shape']);self.assertEqual(t['scope'] is not None,shape['kind']=='OPEN');self.assertEqual(t['contract'] is not None,ty['tag']=='arrow')
        for r in d['representations']:self.assertEqual((r['id'],r['shape']),(r['typing'],r['typing']));self.assertIn(r['ready_kind'],('scalar','data','sum','function','none'))
        for f in d['families']:
            for i,v in enumerate(f['variants']):
                self.assertEqual(set(v),{'name','index','fields'});self.assertEqual(v['index'],i)
                for x in v['fields']:reference(x,'nominal_fields')
        for f in d['nominal_fields']:
            self.assertIs(type(f['position']),int);self.assertGreaterEqual(f['position'],0)
            shape=d['shapes'][f['shape']];self.assertIn(shape['kind'],('DATA','SUM'));self.assertEqual(f['variant'] is None,shape['kind']=='DATA')
            if shape['kind']=='SUM':
                family=next(x for x in d['families'] if x['shape']==shape['id']);self.assertIs(type(f['variant']),int);self.assertGreaterEqual(f['variant'],0);self.assertLess(f['variant'],len(family['variants']))
                self.assertEqual(f['name'],str(f['position']));self.assertEqual(family['variants'][f['variant']]['fields'][f['position']],f['id'])
        for x in d['site_executions']:
            site=d['sites'][x['site']];self.assertIn(x['origin_kind'],('CONCRETE','GENERIC','INSTANCE'));self.assertEqual(x['code_execution'] is not None,site['code'] is not None)
            if x['code_execution'] is not None:self.assertEqual((d['code_executions'][x['code_execution']]['code'],d['code_executions'][x['code_execution']]['env']),(site['code'],x['env']))
        for t in d['transports']:self.assertIn(t['kind'],('identity','project'));self.assertEqual(t['projection_env'] is None,t['kind']=='identity')
        for s in d['sites']:
            path(s['path']);self.assertIn(s['category'],('DATA','CLOSURE','THUNK','HOLE','APPLICATION','SCALAR','SUM'));self.assertEqual(s['code'] is not None,s['category'] in ('CLOSURE','THUNK'))
            context=s['context'];self.assertEqual(set(context),{'concrete':{'kind'},'introduction':{'kind','intro'},'execution':{'kind','code','scheme'}}[context['kind']])
            if 'intro' in context:reference(context['intro'],'introductions')
            if 'code' in context:reference(context['code'],'codes');reference(context['scheme'],'schemes')
        for s in d['slots']:
            role=s['role'];self.assertEqual(set(role),{'capture':{'kind','name'},'field':{'kind','field'},'variant-field':{'kind','variant','field'},'function':{'kind'},'argument':{'kind'},'memo':{'kind'}}[role['kind']]);self.assertIn(s['relation'],('same','down','below'))
            if 'field' in role:reference(role['field'],'nominal_fields')
            if role['kind']=='variant-field':self.assertIs(type(role['variant']),int);self.assertEqual(role['variant'],d['nominal_fields'][role['field']]['variant'])
        for a in d['accesses']:
            self.assertIn(a['mode'],('MONO','SCHEME'));self.assertEqual(a['use_env'] is None,a['mode']=='SCHEME');self.assertEqual(a['scheme'] is not None,a['mode']=='SCHEME')
        for i in d['introductions']:
            container=i['container'];self.assertEqual(set(container),{'entry':{'kind'},'code':{'kind','code'}}[container['kind']]);path(i['generalize_path']);path(i['seal_path'])
            if 'code' in container:reference(container['code'],'codes')
            for x in i['result_sites']:reference(x,'sites')
        for u in d['uses']:
            for x in u['arguments']:reference(x,'types')
            for x in u['occurrences']:path(x)
        boundary_keys={'obligation':'kind index execution_env','instruction':'kind index','slot':'kind slot site_execution','entry':'kind code_execution origin_case role name','return':'kind code_execution','deferred':'kind site_execution request_access phase'}
        for b in d['boundaries']:
            k=b['key'];self.assertEqual(set(k),set(boundary_keys[k['kind']].split()));self.assertEqual(b['principal_type'] is None,b['resolution_env'] is None)
            for field,table in (('execution_env','environments'),('slot','slots'),('site_execution','site_executions'),('code_execution','code_executions'),('request_access','accesses')):
                if field in k:reference(k[field],table)
            if k['kind'] in ('obligation','instruction'):self.assertIs(type(k['index']),int);self.assertGreaterEqual(k['index'],0);self.assertLess(k['index'],len(proof['obligations' if k['kind']=='obligation' else 'instructions']))
            if k['kind']=='entry':self.assertIn(k['origin_case'],('CONCRETE','GENERIC_NEUTRAL','GENERIC_PROJECTED','INSTANCE'));self.assertIn(k['role'],('argument','capture'));self.assertEqual(k['name'] is None,k['role']=='argument')
        for c in d['coverage']:
            src=c['source'];kind=src['kind'];field='index' if kind in ('obligation','instruction') else kind;self.assertEqual(set(src),{'kind',field})
            if kind in ('obligation','instruction'):self.assertIs(type(src[field]),int);self.assertGreaterEqual(src[field],0);self.assertLess(src[field],len(proof['obligations' if kind=='obligation' else 'instructions']))
            else:reference(src[field],{'code':'codes','site':'sites','intro':'introductions','use':'uses'}[kind])
            for field,table in (('boundaries','boundaries'),('resolutions','type_resolutions'),('slots','slots')):
                for x in c[field]:reference(x,table)
    def check_origins(self,d):
        envs=d['environments'];access=d['accesses'];intro_sites={(i['scheme'],s) for i in d['introductions'] for s in i['result_sites']}
        expected=[]
        access_by_key={}
        for a in access:
            key=(a['site'],a['origin_env'],a['mode'],a['use_env'],a['scheme'])
            self.assertNotIn(key,access_by_key);access_by_key[key]=a
        for x in d['site_executions']:
            s=d['sites'][x['site']];e=envs[x['env']];self.assertEqual(x['principal_type'],resolution(d,s['principal_type'],x['env']))
            self.assertEqual(x['origin_kind'],{'CONCRETE':'CONCRETE','NEUTRAL':'GENERIC','CLOSED':'INSTANCE'}[e['mode']])
            if s['context']['kind']=='introduction':self.assertEqual(x['origin_kind'],'GENERIC')
            if x['origin_kind']=='GENERIC':uses=[v['id'] for v in envs if v['scheme']==e['scheme']]
            else:uses=[x['env']]
            for use in uses:expected.append((s['id'],x['env'],'MONO',use,resolution(d,s['principal_type'],use),None))
            if (e['scheme'],s['id']) in intro_sites and x['origin_kind']=='GENERIC':expected.append((s['id'],x['env'],'SCHEME',None,d['schemes'][e['scheme']]['body'],e['scheme']))
            rep=d['representations'][x['representation']];shape=d['shapes'][rep['shape']]
            ty=d['types'][x['principal_type']]
            if e['mode']=='NEUTRAL' and ty['tag'] in ('arrow','rigid'):
                self.assertEqual(shape['kind'],'OPEN');self.assertEqual(shape['source']['scheme'],e['scheme']);self.assertEqual(rep['ready_kind'],'function' if ty['tag']=='arrow' else 'none')
        actual=[(a['site'],a['origin_env'],a['mode'],a['use_env'],a['type'],a['scheme']) for a in access]
        self.assertCountEqual(actual,expected);self.assertEqual(len(actual),len(set(actual)))
        transport=[]
        for a in access:
            if a['mode']=='SCHEME':continue
            transport.append((a['id'],None,a['id'],'identity'))
            origin=envs[a['origin_env']]
            if origin['mode']=='NEUTRAL' and a['use_env']==a['origin_env']:
                for e in envs:
                    if e['mode']=='CLOSED' and e['scheme']==origin['scheme']:
                        key=(a['site'],a['origin_env'],'MONO',e['id'],None);self.assertIn(key,access_by_key)
                        transport.append((a['id'],e['id'],access_by_key[key]['id'],'project'))
        self.assertEqual([(r['source_access'],r['projection_env'],r['result_access'],r['kind']) for r in d['transports']],transport)
    def check_edges(self,d,proof):
        keys=[canon(b['key']) for b in d['boundaries']];self.assertEqual(len(keys),len(set(keys)))
        for b in d['boundaries']:
            self.assertEqual(b['guards'],[g for g in GUARDS if g in b['guards']])
            if b['key']['kind']=='deferred':
                k=b['key'];x=d['site_executions'][k['site_execution']];a=d['accesses'][k['request_access']]
                self.assertEqual((a['site'],a['origin_env']),(x['site'],x['env']));self.assertEqual(b['resolution_env'],x['env'])
                if k['phase']=='reverse-pending':self.assertIn('pending-all-before-publish',b['guards']);self.assertNotIn('acquire-before-release',b['guards'])
                if k['phase']=='memo-publish':self.assertIn('pending-all-before-publish',b['guards']);self.assertIn('acquire-before-release',b['guards'])
        for x in d['site_executions']:
            category=d['sites'][x['site']]['category']
            if category not in PHASES:continue
            for a in d['accesses']:
                if (a['site'],a['origin_env'],a['mode'])==(x['site'],x['env'],'MONO'):
                    phases=[b['key']['phase'] for b in d['boundaries'] if b['key']['kind']=='deferred' and (b['key']['site_execution'],b['key']['request_access'])==(x['id'],a['id'])]
                    self.assertEqual(phases,list(PHASES[category]))
        for c in d['coverage']:
            for field in ('boundaries','resolutions','slots'):self.assertEqual(c[field],sorted(set(c[field])))
        applicable=[]
        for i,r in enumerate(proof['instructions']):
            if r['op'] not in INSTRUCTIONS:continue
            if r['op']=='drop' and next(f for f in r['inputs'] if f['role']==['value'])['kind']!='value':continue
            applicable.append(i)
        self.assertEqual([b['key']['index'] for b in d['boundaries'] if b['key']['kind']=='instruction'],applicable)
        self.assertEqual([r['source']['index'] for r in d['coverage'] if r['source']['kind']=='instruction'],applicable)
        for kind,table in (('code','codes'),('site','sites'),('intro','introductions'),('use','uses')):
            self.assertEqual([r['source'][kind] for r in d['coverage'] if r['source']['kind']==kind],list(range(len(d[table]))))
    def check_storage(self,d):
        inventory=d['storage_inventory'];self.assertEqual(d['counts']['storage_entries'],len(inventory));self.assertEqual(d['counts']['storage_objects'],sum(r['count']>0 for r in inventory))
        expected=[]
        def add(kind,key,count,element):expected.append(dict(kind=kind,key=key,count=count,element_kind=element,emission_status='planned-unbound'))
        elements=('meta.Type','meta.CallableContract','meta.Scheme','meta.Env','meta.CodeTyping','meta.CodeExecution','meta.ShapeBinding','meta.ShapeTyping','meta.Representation','meta.NominalField','meta.FamilyTyping','meta.TypeResolution','meta.RepresentationResolution','meta.Site','meta.SiteExecution','meta.Slot','meta.Access','meta.Intro','meta.Use','meta.Transport')
        for table,element in zip(TABLES,elements):add('table','table/'+table,len(d[table]),element);add('index','index/table/'+table,len(d[table]),'meta.RegisteredRowRef')
        descriptors=(('shapes',len(d['shapes']),'physical.RtShape'),('codes',len(d['codes']),'physical.RtCode'),('families',len(d['families']),'physical.RtFamily'),('variants',sum(len(f['variants']) for f in d['families']),'physical.RtVariant'),('nominal-fields',len(d['nominal_fields']),'physical.RtField'),('code-capture-fields',sum(len(c['captures']) for c in d['codes']),'physical.RtField'))
        for suffix,count,element in descriptors:add('descriptor','descriptor/'+suffix,count,element);add('index','index/descriptor/'+suffix,count,'meta.RegisteredDescriptorRef')
        for e in d['environments']:add('vector','vector/env/'+str(e['id']),len(e['arguments']),'ref.Type')
        for c in d['codes']:add('vector','vector/code-captures/'+str(c['id']),len(c['captures']),'meta.CaptureTyping')
        for c in d['code_executions']:add('vector','vector/execution-captures/'+str(c['id']),len(c['captures']),'meta.ResolvedCapture')
        for i in d['introductions']:add('vector','vector/intro-sites/'+str(i['id']),len(i['result_sites']),'ref.Site')
        for u in d['uses']:add('vector','vector/use-occurrences/'+str(u['id']),len(u['occurrences']),'ref.PathString')
        for f in d['families']:
            key=str(f['id']);add('vector','vector/family-variants/'+key,len(f['variants']),'meta.VariantTyping');add('vector','vector/family-variant-pointers/'+key,len(f['variants']),'physical.RtVariantRef')
            for v in f['variants']:add('vector','vector/variant-fields/'+key+'/'+str(v['index']),len(v['fields']),'ref.NominalField')
        for shape in d['shapes']:
            if shape['kind']=='DATA':add('vector','vector/data-fields/'+str(shape['id']),sum(f['shape']==shape['id'] for f in d['nominal_fields']),'ref.NominalField')
        add('string-pool','pool/strings',pool_bytes(d),'byte.UTF8');add('header','header/program',1,'physical.RtProgram');add('header','header/typed',1,'meta.TypedHeader');add('header','header/bindings',5,'byte.Digest32')
        order=('table','vector','descriptor','index','string-pool','header');expected.sort(key=lambda r:(order.index(r['kind']),r['key']))
        self.assertEqual(inventory,[dict(id=i,**r) for i,r in enumerate(expected)])
        self.assertEqual(len({r['key'] for r in inventory}),len(inventory))
        for r in inventory:self.assertIs(type(r['count']),int)

def raw_case(case):
    def test(self):
        self.assertEqual(case['input_sha256'],digest(case['text']));self.assertEqual(case['input_bytes'],len(case['text'].encode()))
        if case['accepted']:
            result=loads_metadata(case['text']);self.validate(result,json.loads(case['text']))
            save(case['name']+'.metadata.json',result.metadata_json);save(case['name']+'.report.json',canon(result.report()))
        else:
            expected=MetadataError if case['expected_layer'].startswith('metadata-') else ResourceError
            with self.assertRaises(expected) as caught:loads_metadata(case['text'])
            e=caught.exception;self.assertEqual((e.layer,e.code,e.path),(case['expected_layer'],case['expected_code'],case['expected_path']))
            save(case['name']+'.error.json',canon({'layer':e.layer,'code':e.code,'path':e.path,'message':str(e)}))
    return test
for c in CASES:setattr(RawCases,'test_raw_'+c['name'],raw_case(c))

class Semantics(unittest.TestCase):
    def test_public_immutable_no_execution_route(self):
        p=raw('ready_shared_identity_two_views');r=check_metadata(p);before=(r.canonical_json,r.metadata_json,r.report())
        p['entry'].clear();self.assertEqual(before,(r.canonical_json,r.metadata_json,r.report()))
        with self.assertRaises((dataclasses.FrozenInstanceError,AttributeError)):r.metadata_json='{}'
        self.assertFalse(any(hasattr(r,k) for k in ('run','generate','data','from_checked','tables')))
        self.assertNotIn('resource_ir',sys.modules)
        with self.assertRaises(ResourceError):check_metadata(r)
        with self.assertRaises(ResourceError):check_metadata(check_resources(raw('concrete_scalar')))
    def test_reordered_maps_same_canonical(self):
        p=raw('two_scheme_closed_higher_order_capture')
        def reverse(v):
            if type(v) is dict:return {k:reverse(v[k]) for k in reversed(v)}
            if type(v) is list:return [reverse(x) for x in v]
            return v
        a=check_metadata(p);b=check_metadata(reverse(p))
        self.assertEqual((a.canonical_json,a.metadata_json),(b.canonical_json,b.metadata_json))
    def test_cached_report_has_final_statistics(self):
        r,d=checked('concrete_empty_finish');report=r.report();stats=dict(dict(report)['host_statistics'])
        for i in range(10):self.assertIs(r.report(),report);self.assertEqual(dict(dict(r.report())['host_statistics']),stats)
        self.assertGreater(stats['creation_units'],stats['metadata_records'])
        self.assertEqual(dict(dict(report)['native_static_status'])['planned_nonempty_objects'],d['counts']['storage_objects'])
    def test_dead_vector_and_unused_intermediate_closure(self):
        _,d=checked('scoped_intermediate_dead_parameter_substitution')
        uses=d['uses'];self.assertEqual(len(uses),2);self.assertNotEqual(uses[0]['env'],uses[1]['env']);self.assertEqual(uses[0]['result_type'],uses[1]['result_type'])
        bool_id=next(t['id'] for t in d['types'] if t['tag']=='closed' and t['atom']=='#bool')
        bb=next(t['id'] for t in d['types'] if t['tag']=='arrow' and t['argument']==bool_id and t['result']==bool_id)
        code=next(c for c in d['codes'] if c['name']=='unused_b')
        self.assertIn(bb,[c['callable_type'] for c in d['code_executions'] if c['code']==code['id']])
        self.assertEqual(len(d['codes']),2)
        lower=json.loads(check_resources(raw('scoped_intermediate_dead_parameter_substitution')).derived_json)
        lb=next(t['id'] for t in lower['types'] if t['tag']=='closed' and t['atom']=='#bool')
        self.assertFalse(any(t['tag']=='arrow' and t['argument']==lb and t['result']==lb for t in lower['types']))
        self.assertNotIn(bb,[r['metadata_type'] for r in d['type_remap']])
    def test_curried_single_code_identity(self):
        _,d=checked('curried_const_complete_ib_bi_views');self.assertEqual(len(d['codes']),2)
        inner=next(c for c in d['codes'] if c['name']=='return_x');sites=[s for s in d['sites'] if s['code']==inner['id']]
        self.assertTrue(sites)
        for s in sites:
            x=[x for x in d['site_executions'] if x['site']==s['id']]
            self.assertEqual([x['origin_kind'] for x in x],['GENERIC','INSTANCE','INSTANCE'])
            self.assertFalse(any(a['mode']=='SCHEME' and a['site']==s['id'] for a in d['accesses']))
        self.assertEqual(len([e for e in d['code_executions'] if e['code']==inner['id']]),3)
    def test_projected_and_instance_capture_keys_differ(self):
        _,d=checked('curried_const_complete_ib_bi_views')
        seen=0
        for x in d['code_executions']:
            c=d['codes'][x['code']]
            if d['environments'][x['env']]['mode']!='CLOSED' or not c['captures']:continue
            rows=[b for b in d['boundaries'] if b['key']['kind']=='entry' and b['key']['code_execution']==x['id'] and b['key']['role']=='capture']
            for name in [c['name'] for c in c['captures']]:
                gp=next(b for b in rows if b['key']['name']==name and b['key']['origin_case']=='GENERIC_PROJECTED')
                inst=next(b for b in rows if b['key']['name']==name and b['key']['origin_case']=='INSTANCE')
                self.assertEqual(gp['access_rule'],'transport-by-request');self.assertIn('symbolic-before-projection',gp['guards']);self.assertIn('same-neutral-capsule',gp['guards'])
                self.assertEqual(inst['access_rule'],'copy-actual');self.assertIn('preserve-foreign-access',inst['guards']);self.assertNotIn('symbolic-before-projection',inst['guards']);seen+=1
            args=[b for b in d['boundaries'] if b['key']['kind']=='entry' and b['key']['code_execution']==x['id'] and b['key']['role']=='argument']
            self.assertEqual({b['key']['origin_case'] for b in args},{'GENERIC_PROJECTED','INSTANCE'})
            for b in args:self.assertIn('preserve-foreign-access',b['guards']);self.assertNotIn('same-neutral-capsule',b['guards'])
        self.assertGreater(seen,0)
    def test_neutral_closed_looking_arrow_scalar(self):
        _,d=checked('neutral_closed_looking_arrow_and_scalar');code=next(c for c in d['codes'] if c['name']=='fixed')
        site=next(s for s in d['sites'] if s['code']==code['id']);xs=[x for x in d['site_executions'] if x['site']==site['id']]
        self.assertEqual(len(xs),1);x=xs[0];self.assertEqual(x['origin_kind'],'GENERIC')
        self.assertEqual(d['shapes'][d['representations'][x['representation']]['shape']]['kind'],'OPEN')
        literal=[s for s in d['sites'] if s['category']=='SCALAR' and s['context']['kind']=='introduction'];self.assertTrue(literal)
        for s in literal:
            x=next(x for x in d['site_executions'] if x['site']==s['id']);self.assertEqual(x['origin_kind'],'GENERIC')
            self.assertEqual(d['shapes'][d['representations'][x['representation']]['shape']]['kind'],'I64')
    def test_generic_thunk_principal_not_request_dispatch(self):
        _,d=checked('generic_thunk_and_instance_deferred_return');projected=0;instance=0
        for b in d['boundaries']:
            k=b['key']
            if k['kind']=='entry':
                c=d['codes'][d['code_executions'][k['code_execution']]['code']]
                if c['kind']=='thunk':self.assertNotEqual(k['origin_case'],'GENERIC_PROJECTED')
            if k['kind']=='deferred' and k['phase']=='thunk-dispatch':
                x=d['site_executions'][k['site_execution']];a=d['accesses'][k['request_access']]
                self.assertEqual(b['resolution_env'],x['env'])
                if x['origin_kind']=='GENERIC' and a['use_env']!=x['env']:projected+=1;self.assertEqual(d['environments'][x['env']]['mode'],'NEUTRAL')
                if x['origin_kind']=='INSTANCE':instance+=1;self.assertEqual(a['use_env'],x['env'])
        self.assertGreater(projected,0);self.assertGreater(instance,0)
    def test_closed_callable_alias_keeps_physical_descriptors(self):
        _,d=checked('closed_full_contract_alias_interchange')
        groups={}
        for r in d['shape_typing']:
            s=d['shapes'][r['shape']]
            if s['source']['kind']=='legacy' and s['kind']=='REPEAT':groups.setdefault(r['type'],[]).append(s['id'])
        self.assertTrue(any(len(v)>1 for v in groups.values()))
    def test_foreign_field_not_retagged(self):
        _,d=checked('concrete_callable_field_foreign_projection')
        field=next(f for f in d['nominal_fields'] if f['name']=='fn');self.assertEqual(d['shapes'][d['representations'][field['declared_rep']]['shape']]['kind'],'REPEAT')
        targets=[a for a in d['accesses'] if a['mode']=='MONO' and a['type']==field['type'] and a['origin_env']!=a['use_env']]
        self.assertTrue(targets)
        for a in targets:
            x=next(x for x in d['site_executions'] if (x['site'],x['env'])==(a['site'],a['origin_env']))
            self.assertEqual(d['shapes'][d['representations'][x['representation']]['shape']]['kind'],'OPEN')
        self.assertTrue(any(b['access_rule']=='copy-actual' and 'preserve-foreign-access' in b['guards'] for b in d['boundaries']))
    def test_sum_variant_slots_and_all_factory_arms(self):
        for name in ('closed_data_sum_factory','concrete_nullary_case_all_arms','sum_scalar_field_foreign_factory_capture'):
            _,d=checked(name);p=raw(name)
            for site in d['sites']:
                if site['category']!='SUM':continue
                i=source_instruction(p,site['path']);family=next(f for f in d['families'] if f['name']==i['family']);variant=next(v for v in family['variants'] if v['name']==i['variant'])
                slots=[s for s in d['slots'] if s['site']==site['id'] and s['role']['kind']=='variant-field']
                self.assertEqual([s['role']['field'] for s in slots],variant['fields'])
                for s in slots:self.assertEqual(s['role']['variant'],variant['index'])
            factory=[s for s in d['sites'] if s['arm'] is not None]
            if name!='concrete_nullary_case_all_arms':self.assertEqual({s['arm'] for s in factory},{0,1})
            if name=='sum_scalar_field_foreign_factory_capture':
                code=next(c for c in d['codes'] if c['name']=='some' and c['kind']=='thunk')
                site=next(s for s in factory if s['code']==code['id']);slots=[x for x in d['slots'] if x['site']==site['id']]
                self.assertEqual({x['role']['name'] for x in slots if x['role']['kind']=='capture'},{'fn','item'})
                self.assertEqual(sum(x['role']['kind']=='memo' for x in slots),1)
                fn=next(x for x in slots if x['role']=={'kind':'capture','name':'fn'})
                self.assertTrue(any(a['mode']=='MONO' and a['origin_env']!=a['use_env'] and a['type']==fn['type'] for a in d['accesses']))
                for b in d['boundaries']:
                    if b['key']['kind']=='slot' and b['key']['slot']==fn['id']:
                        self.assertEqual(b['access_rule'],'publish-by-host-origin');self.assertIn('preserve-foreign-access',b['guards']);self.assertNotIn('same-neutral-capsule',b['guards'])
                execution=next(e for e in d['code_executions'] if e['code']==code['id'])
                self.assertEqual(execution['env'],0)
                entry=next(b for b in d['boundaries'] if b['key']=={'kind':'entry','code_execution':execution['id'],'origin_case':'CONCRETE','role':'capture','name':'fn'})
                self.assertEqual(entry['access_rule'],'copy-actual');self.assertIn('preserve-foreign-access',entry['guards'])

    def test_scheme_view_moves_do_not_become_mono(self):
        _,d=checked('loan_view_move_and_promotion');proof=json.loads(check_resources(raw('loan_view_move_and_promotion')).derived_json)
        for b in d['boundaries']:
            if b['key']['kind']!='instruction':continue
            op=proof['instructions'][b['key']['index']]['op']
            if op in ('retain','borrow','drop','end_borrow'):self.assertNotIn('no-scheme-value',b['guards'])
            if op=='seal':self.assertIn('no-scheme-value',b['guards'])
            if op=='instantiate':self.assertIn('scheme-input',b['guards']);self.assertIn('view-move-mode',b['guards']);self.assertNotIn('owner-mode',b['guards'])
    def test_dependency_current_environment_after_resolved_arrow(self):
        from resource_ir_v8.metadata import _fresh,_verify_types
        budget=mb.Budget();resource,p,derived,t=_fresh(raw('ready_shared_identity_two_views'),budget);_verify_types(p,derived,t,budget)
        scheme=t.tables['schemes'][0];integer=next(x['id'] for x in t.tables['types'] if x['tag']=='closed' and x['atom']=='#i64')
        env=next(x['id'] for x in t.tables['environments'] if x['mode']=='CLOSED' and x['arguments']==[integer])
        body=scheme['body'];rigid=t.tables['types'][body]['argument'];resolved=t.resolve(body,env)
        ids=t.dependencies(body,env);keys={(t.tables['type_resolutions'][i]['type'],t.tables['type_resolutions'][i]['env']) for i in ids}
        self.assertEqual(keys,{(body,env),(rigid,env),(resolved,0),(integer,0)})
        self.assertNotIn((integer,env),{(r['type'],r['env']) for r in t.tables['type_resolutions']})
    def test_private_valid_verifier_never_returns_authority(self):
        _,d=checked('ready_shared_identity_two_views');self.assertIsNone(_verify_derived(raw('ready_shared_identity_two_views'),d))

MUTATIONS = [
 ('drop_type','types','metadata-type','TYPE_EQUATION'),
 ('bool_type_id','types','metadata-type','TYPE_EQUATION'),
 ('drop_resolution','type_resolutions','metadata-type','TYPE_EQUATION'),
 ('swap_full_vector','environments','metadata-type','TYPE_EQUATION'),
 ('alter_recursive_contract','callable_contracts','metadata-type','TYPE_EQUATION'),
 ('duplicate_code','codes','metadata-origin','ORIGIN'),
 ('retag_generic_instance','site_executions','metadata-origin','ORIGIN'),
 ('invent_scheme_site','introductions','metadata-origin','ORIGIN'),
 ('drop_code_execution','code_executions','metadata-origin','ORIGIN'),
 ('alter_representation','representation_resolutions','metadata-representation','REPRESENTATION'),
 ('collapse_legacy_alias','shapes','metadata-representation','REPRESENTATION'),
 ('change_nominal_field','nominal_fields','metadata-representation','REPRESENTATION'),
 ('variant_slot_mismatch','slots','metadata-closure','TABLE_EQUATION'),
 ('retag_projected_origin','accesses','metadata-closure','TABLE_EQUATION'),
 ('reproject_projected_access','transports','metadata-closure','TABLE_EQUATION'),
 ('drop_gp_capture','boundaries','metadata-closure','COVERAGE'),
 ('drop_instance_capture','boundaries','metadata-closure','COVERAGE'),
 ('drop_deferred_phase','boundaries','metadata-closure','COVERAGE'),
 ('principal_to_request','boundaries','metadata-closure','COVERAGE'),
 ('erase_request_key','boundaries','metadata-closure','COVERAGE'),
 ('publish_on_reverse','boundaries','metadata-closure','COVERAGE'),
 ('skip_unused_code_coverage','coverage','metadata-closure','COVERAGE'),
 ('invent_key_drop_boundary','boundaries','metadata-closure','COVERAGE'),
 ('extra_storage_array','storage_inventory','metadata-closure','STORAGE_INVENTORY'),
 ('omit_env_vector','storage_inventory','metadata-closure','STORAGE_INVENTORY'),
 ('omit_capture_descriptor','storage_inventory','metadata-closure','STORAGE_INVENTORY'),
 ('claim_native_bytes','native_status','metadata-closure','TABLE_EQUATION'),
 ('wrong_record_census','counts','metadata-closure','TABLE_EQUATION'),
 ('wrong_resource_binding','resource_sha256','metadata-closure','TABLE_EQUATION'),
 ('unknown_top_key',None,'metadata-schema','SCHEMA'),
]
class Mutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base={}
    def mutate(self,name):
        base='curried_const_complete_ib_bi_views'
        if name in ('drop_deferred_phase','principal_to_request','erase_request_key','publish_on_reverse'):base='generic_thunk_and_instance_deferred_return'
        if name=='collapse_legacy_alias':base='closed_full_contract_alias_interchange'
        if name in ('change_nominal_field','variant_slot_mismatch'):base='sum_scalar_field_foreign_factory_capture'
        if name=='skip_unused_code_coverage':base='scoped_intermediate_dead_parameter_substitution'
        if base not in self.base:self.base[base]=checked(base)[1]
        d=copy.deepcopy(self.base[base]);table=next(t for n,t,l,c in MUTATIONS if n==name)
        if name=='drop_type':d['types'].pop()
        elif name=='bool_type_id':d['types'][0]['id']=False
        elif name=='drop_resolution':d['type_resolutions'].pop()
        elif name=='swap_full_vector':next(e for e in d['environments'] if e['mode']=='CLOSED')['arguments'].reverse()
        elif name=='alter_recursive_contract':d['callable_contracts'][0]['result_identity']='argument'
        elif name=='duplicate_code':d['codes'].append(copy.deepcopy(d['codes'][0]))
        elif name=='retag_generic_instance':next(x for x in d['site_executions'] if x['origin_kind']=='GENERIC')['origin_kind']='INSTANCE'
        elif name=='invent_scheme_site':d['introductions'][0]['result_sites'].append(next(s['id'] for s in d['sites'] if s['context']['kind']=='execution'))
        elif name=='drop_code_execution':d['code_executions'].pop()
        elif name=='alter_representation':d['representation_resolutions'][0]['representation']=len(d['representations'])
        elif name=='collapse_legacy_alias':
            alias=next(r for r in d['shapes'] if r['source']['kind']=='legacy' and r['source']['reference']=='@B');alias['source']['reference']='@A'
        elif name=='change_nominal_field':d['nominal_fields'][0]['type']=len(d['types'])
        elif name=='variant_slot_mismatch':next(s for s in d['slots'] if s['role']['kind']=='variant-field')['role']['variant']=0
        elif name=='retag_projected_origin':next(a for a in d['accesses'] if a['mode']=='MONO' and a['origin_env']!=a['use_env'])['origin_env']=0
        elif name=='reproject_projected_access':
            a=next(a for a in d['accesses'] if a['mode']=='MONO' and a['origin_env']!=a['use_env'])
            row=next(t for t in d['transports'] if t['source_access']==a['id'] and t['kind']=='identity');row['projection_env']=a['use_env'];row['kind']='project'
            d['transports'].sort(key=lambda t:(t['source_access'],-1 if t['projection_env'] is None else t['projection_env']))
            for i,t in enumerate(d['transports']):t['id']=i
        elif name in ('drop_gp_capture','drop_instance_capture'):
            origin='GENERIC_PROJECTED' if name=='drop_gp_capture' else 'INSTANCE';row=next(b for b in d['boundaries'] if b['key']['kind']=='entry' and b['key']['role']=='capture' and b['key']['origin_case']==origin);d['boundaries'].remove(row)
        elif name in ('drop_deferred_phase','principal_to_request','erase_request_key','publish_on_reverse'):
            row=next(b for b in d['boundaries'] if b['key']['kind']=='deferred' and b['key']['phase']=='reverse-pending' and d['accesses'][b['key']['request_access']]['use_env']!=b['resolution_env'])
            if name=='drop_deferred_phase':d['boundaries'].remove(row)
            elif name=='principal_to_request':row['resolution_env']=d['accesses'][row['key']['request_access']]['use_env']
            elif name=='erase_request_key':del row['key']['request_access']
            else:row['guards'].append('acquire-before-release')
        elif name=='skip_unused_code_coverage':
            code=next(c['id'] for c in d['codes'] if c['name']=='unused_b');d['coverage']=[c for c in d['coverage'] if c['source']!={'kind':'code','code':code}]
        elif name=='invent_key_drop_boundary':
            proof=json.loads(check_resources(raw(base)).derived_json);index=next(i for i,r in enumerate(proof['instructions']) if r['op']=='drop' and next(f for f in r['inputs'] if f['role']==['value'])['kind']=='key')
            row=copy.deepcopy(next(b for b in d['boundaries'] if b['key']['kind']=='instruction'));row['key']['index']=index;d['boundaries'].append(row)
        elif name=='extra_storage_array':d['storage_inventory'].append(dict(id=len(d['storage_inventory']),kind='vector',key='invented',count=1,element_kind='byte',emission_status='planned-unbound'))
        elif name=='omit_env_vector':d['storage_inventory']=[r for r in d['storage_inventory'] if r['key']!='vector/env/0']
        elif name=='omit_capture_descriptor':d['storage_inventory']=[r for r in d['storage_inventory'] if r['key']!='descriptor/code-capture-fields']
        elif name=='claim_native_bytes':d['native_status']['typed_static_bytes']=1
        elif name=='wrong_record_census':d['counts']['metadata_records']+=1
        elif name=='wrong_resource_binding':d['resource_sha256']='0'*64
        elif name=='unknown_top_key':d['producer_validated']=True
        else:raise AssertionError(name)
        self.assertTrue(canon(d)!=canon(self.base[base]),'Mutation must change the exact JSON value, including bool/int types: '+name);return base,d

def mutation_case(name,table,layer,code):
    def test(self):
        base,d=self.mutate(name)
        with self.assertRaises(MetadataError) as caught:_verify_derived(raw(base),d)
        e=caught.exception;self.assertEqual((e.layer,e.code,e.path),(layer,code,'metadata' if table is None else 'metadata.'+table))
        save('mutation-'+name+'.json',canon({'fixture':base,'mutation':name,'layer':e.layer,'code':e.code,'path':e.path}))
    return test
for m in MUTATIONS:setattr(Mutations,'test_mutation_'+m[0],mutation_case(*m))

class PrivateBounds(unittest.TestCase):
    """Helper arithmetic/guard controls, not raw/native capacity witnesses."""
    def error(self,fn,code,path,layer='metadata-bounds'):
        with self.assertRaises(MetadataError) as caught:fn()
        e=caught.exception;self.assertEqual((e.layer,e.code,e.path),(layer,code,path))
    def test_atomic_creation_work_row_record_exact_limits(self):
        specs=(('creation','creation_units',2097152,'CREATION_UNITS','metadata.creation_units'),('work','work_units',16777216,'WORK_UNITS','metadata.work_units'),('rows','row_units',65536,'ROW_COUNT','metadata.access_transport_resolution_rows'),('records','retained_records',262144,'RECORD_COUNT','metadata.records'))
        for method,field,limit,code,path in specs:
            b=mb.Budget();getattr(b,method)(limit);self.assertEqual(getattr(b,field),limit)
            before=(b.creation_units,b.work_units,b.row_units,b.retained_records)
            self.error(lambda:getattr(b,method)(1),code,path);self.assertEqual(before,(b.creation_units,b.work_units,b.row_units,b.retained_records))
        b=mb.Budget();b.creation(mb.CREATION_LIMIT)
        self.error(lambda:b.reserve(creation=1,work=1,rows=1,records=1),'CREATION_UNITS','metadata.creation_units')
        self.assertEqual((b.work_units,b.row_units,b.retained_records),(0,0,0))
    def test_failed_append_no_destination_change(self):
        b=mb.Budget();b.creation(mb.CREATION_LIMIT);target=[]
        self.error(lambda:b.append(target,1),'CREATION_UNITS','metadata.creation_units');self.assertEqual(target,[])
    def test_retention_before_attachment_and_shared_occurrences(self):
        b=mb.Budget();b.records(mb.RECORD_LIMIT-2);shared={};subtree=[shared,shared];b.retain_json(subtree);self.assertEqual(b.retained_records,mb.RECORD_LIMIT)
        target={};before=b.retained_records
        def attach():b.retain_json({});target['extra']={}
        self.error(attach,'RECORD_COUNT','metadata.records');self.assertEqual(target,{});self.assertEqual(b.retained_records,before)
        c=mb.Budget();tree={'a':shared,'b':shared};c.retain_json(tree);self.assertEqual(c.retained_records,3);self.assertEqual(mb.census_records(tree,c),3)
    def test_retention_mutation_census_detects_mismatch(self):
        for mode in ('omit','double','mutate'):
            b=mb.Budget();tree={'a':{}}
            if mode!='omit':b.retain_json(tree)
            if mode=='double':b.retain_json(tree)
            if mode=='mutate':tree['b']={}
            self.assertNotEqual(mb.census_records(tree,b),b.retained_records)
    def test_verification_retains_actual_counters_and_costs(self):
        b=mb.Budget();b.records(10);b.rows(20);b.metadata_records=10;start=(b.creation_units,b.work_units)
        with b.verification():
            b.retain_json({'nested':[{}]});self.assertEqual(mb.census_records({'x':{}},b),2);b.rows(65536)
        self.assertEqual((b.retained_records,b.row_units,b.metadata_records),(10,20,10));self.assertGreater(b.creation_units,start[0]);self.assertGreater(b.work_units,start[1])
        b.work(mb.WORK_LIMIT-b.work_units)
        with b.verification():self.error(lambda:b.retain_json({}),'WORK_UNITS','metadata.work_units')
    def test_report_finalization_atomic_and_frozen(self):
        b=mb.Budget();b.finalize(creation=5,work=7);self.assertEqual((b.creation_units,b.work_units),(5,7))
        with self.assertRaises(RuntimeError):b.work()
        c=mb.Budget();c.creation(mb.CREATION_LIMIT)
        self.error(lambda:c.finalize(creation=1,work=2),'CREATION_UNITS','metadata.creation_units');self.assertEqual(c.work_units,0);self.assertFalse(c._finalized)
    def test_decoder_exact_small_charges_and_escaped_punctuation(self):
        for text,creation in (('{}',1),('{"x":[]}',3),(canon(['[,{:"}\\']),2)):
            b=mb.Budget();value=mb.decode_fresh(text,b);self.assertEqual(value,json.loads(text))
            openers=2 if text=='{"x":[]}' else 1
            self.assertEqual(b.creation_units,1+2*openers+creation)
            self.assertEqual(b.work_units,3*len(text)+creation+1);self.assertEqual(b.retained_records,0)
    def test_decoder_reservation_failure_never_calls_json(self):
        for field,used,code,path in (('creation',mb.CREATION_LIMIT-3,'CREATION_UNITS','metadata.creation_units'),('work',mb.WORK_LIMIT-7,'WORK_UNITS','metadata.work_units')):
            b=mb.Budget();getattr(b,field)(used)
            with mock.patch('json.loads',side_effect=AssertionError('decoder called after failed reservation')) as decoder:
                self.error(lambda:mb.decode_fresh('{}',b),code,path);decoder.assert_not_called()
        b=mb.Budget();b.creation(mb.CREATION_LIMIT-4);b.work(mb.WORK_LIMIT-8)
        self.assertEqual(mb.decode_fresh('{}',b),{});self.assertEqual((b.creation_units,b.work_units),(mb.CREATION_LIMIT,mb.WORK_LIMIT))
    def test_decoder_depth32_and_schema_boundaries(self):
        self.assertIsInstance(mb.decode_fresh('['*32+'0'+']'*32,mb.Budget()),list)
        self.error(lambda:mb.decode_fresh('['*33+'0'+']'*33,mb.Budget()),'DEPTH','metadata.snapshot','metadata-schema')
        for text in (None,'[}','{"x":','"unterminated'):
            self.error(lambda:mb.decode_fresh(text,mb.Budget()),'JSON','metadata.snapshot','metadata-schema')
        self.error(lambda:mb.decode_fresh('"\ud800"',mb.Budget()),'UTF8','metadata.snapshot','metadata-schema')
    def test_encoder_small_exact_bytes_and_actual_cap_arithmetic(self):
        text,sha,size=mb.canonical_encode('abcdef',mb.Budget(),limit=8);self.assertEqual((text,sha,size),('"abcdef"',digest('"abcdef"'),8))
        self.error(lambda:mb.canonical_encode('abcdef',mb.Budget(),limit=7),'OUTPUT_BYTES','metadata.bytes')
        b=mb.Budget();encoder=mb.CanonicalEncoder(b);encoder.size=mb.OUTPUT_BYTES-1;encoder.emit(b'x');self.assertEqual(encoder.size,mb.OUTPUT_BYTES)
        self.error(lambda:encoder.emit(b'y'),'OUTPUT_BYTES','metadata.bytes')
        with self.assertRaises(ValueError):mb.CanonicalEncoder(mb.Budget(),mb.OUTPUT_BYTES+1)
        with self.assertRaises(ValueError):mb.CanonicalEncoder(mb.Budget()).emit(b'x'*4097)
    def test_encoder_unicode_and_integer_guards(self):
        value={'z':'é中\n"\\','a':[None,False,True,-1]};text,sha,size=mb.canonical_encode(value,mb.Budget())
        self.assertEqual(text,canon(value));self.assertEqual(sha,digest(text));self.assertEqual(size,len(text.encode()))
        self.error(lambda:mb.canonical_encode('\ud800',mb.Budget()),'UTF8','metadata.bytes','metadata-schema')
        self.error(lambda:mb.canonical_encode(1<<65,mb.Budget()),'INTEGER','metadata.bytes','metadata-schema')
    def test_sort_keys_reserved_before_callback(self):
        b=mb.Budget();b.creation(mb.CREATION_LIMIT-1);called=[]
        def key(x):called.append(x);return (x,)
        self.error(lambda:b.ordered([1],key=key,key_units=2),'CREATION_UNITS','metadata.creation_units');self.assertEqual(called,[])
        self.assertEqual(mb.Budget().ordered([2,1],key=lambda x:(x,),key_units=2),[1,2])
        with self.assertRaises(ValueError):mb.Budget().ordered([1],key=lambda x:(x,))
    def test_private_bank_type4096_then4097(self):
        from resource_ir_v8.metadata_types import _Bank
        names=['N'+str(i) for i in range(4097)];p={'layouts':{n:{} for n in names},'families':{},'schemes':{}}
        bank=_Bank(p,{'types':[]},mb.Budget(),{})
        for name in names[:4096]:bank.intern(('closed',name),'metadata.types')
        self.assertEqual(len(bank.nodes),4096)
        self.error(lambda:bank.intern(('closed',names[-1]),'metadata.types'),'TYPE_COUNT','metadata.types');self.assertEqual(len(bank.nodes),4096)
    def test_private_bank_depth32_then33(self):
        from resource_ir_v8.metadata_types import _Bank
        bank=_Bank({'layouts':{},'families':{},'schemes':{}},{'types':[]},mb.Budget(),{})
        t=bank.intern(('closed','#i64'),'metadata.types')
        for i in range(31):t=bank.intern(('arrow',t,t,'repeat','unknown'),'metadata.type_resolutions[temporary_type,env]')
        self.assertEqual(bank.depths[t],32)
        self.error(lambda:bank.intern(('arrow',t,t,'repeat','unknown'),'metadata.type_resolutions[temporary_type,env]'),'TYPE_DEPTH','metadata.type_resolutions[temporary_type,env]')
    def test_private_environment1024_then1025(self):
        from resource_ir_v8.metadata_types import _Bank,_environment_rows
        def construct(extra):
            p={'layouts':{},'families':{},'schemes':{s:{'parameters':8} for s in 'ABCD'},'instantiations':{}}
            b=mb.Budget();mapping={s:i for i,s in enumerate('ABCD')};bank=_Bank(p,{'types':[]},b,mapping)
            refs={'^B':bank.intern(('closed','#bool'),'metadata.types'),'^I':bank.intern(('closed','#i64'),'metadata.types')}
            for s in 'ABCD':
                for i in range(8):bank.intern(('rigid',s,i),'metadata.types')
            uses=[];env=0
            for s in 'ABCD':
                env+=1
                for n in range(256 if s!='D' else 251+extra):
                    args=['I' if n&(1<<(7-i)) else 'B' for i in range(8)];name=s+str(n);p['instantiations'][name]={'scheme':s,'arguments':args};env+=1
                    uses.append({'name':name,'scheme':s,'arguments':[refs['^'+a] for a in args],'environment':'E'+str(env)})
            return _environment_rows(p,{'uses':uses,'counts':{'environments':env+1}},bank,refs,mapping,b)
        self.assertEqual(len(construct(0)[0]),1024)
        self.error(lambda:construct(1),'ENVIRONMENT_COUNT','metadata.environments')

class PhaseBoundaries(unittest.TestCase):
    """Fresh raw witnesses for named internal prefixes, never MetadataClosure."""
    def run_phase(self,case):
        from resource_ir_v8.metadata import _fresh,_verify_types
        self.assertEqual(digest(case['text']),case['input_sha256']);self.assertEqual(len(case['text'].encode()),case['input_bytes'])
        budget=mb.Budget();resource,owned,derived,types=_fresh(json.loads(case['text']),budget)
        _verify_types(owned,derived,types,budget)
        self.assertEqual(len(derived['types']),case['expected_lower_type_count'])
        self.assertEqual(len(types.tables['types']),case['expected_metadata_type_count'])
        if case['phase']=='fresh-type-closure':
            tables=types.tables
            boolean=next(t['id'] for t in tables['types'] if t['tag']=='closed' and t['atom']=='#bool')
            arrow=next(t['id'] for t in tables['types'] if t['tag']=='arrow' and t['argument']==boolean and t['result']==boolean)
            self.assertNotIn(arrow,[r['metadata_type'] for r in tables['type_remap']])
            self.assertEqual(len(tables['types'])-len(derived['types']),1)
        elif case['phase']=='four-row-table-prefix':
            from resource_ir_v8.metadata_representations import build_representations
            from resource_ir_v8.metadata_edges import EdgeClosure
            rep=build_representations(owned,derived,types,budget);edges=EdgeClosure(rep);edges.slot_rows();edges.access_rows()
            tables={**types.tables,**rep.tables,**edges.tables}
            actual={key:len(tables[key]) for key in ('type_resolutions','representation_resolutions','accesses','transports')}
            self.assertEqual(actual,case['expected_row_components']);self.assertEqual(sum(actual.values()),case['expected_R']);self.assertEqual(budget.row_units,case['expected_R'])
            self.assertEqual(tables['boundaries'],[]);self.assertEqual(tables['coverage'],[])
            RawCases.check_origins(self,tables)
        else:raise AssertionError(case['phase'])
        self.assertLessEqual(budget.creation_units,mb.CREATION_LIMIT);self.assertLessEqual(budget.work_units,mb.WORK_LIMIT)
        self.assertEqual(budget.retained_records,0);self.assertFalse(budget._finalized)
        save('phase-'+case['name']+'.json',canon({'scope':case['phase'],'status':'internal-prefix-only-no-MetadataClosure','input_sha256':case['input_sha256'],'ir_sha256':resource.sha256,'declaration_sha256':resource.declaration_sha256,'resource_sha256':resource.derived_sha256,'creation_units':budget.creation_units,'work_units':budget.work_units,'row_units':budget.row_units,'tables':tables,'full_metadata_api_accepted':None,'full_metadata_api_called':False,'graph_executed':False,'source_admitted':False}))
def phase_case(case):
    def test(self):self.run_phase(case)
    return test
for c in PHASE_CASES:setattr(PhaseBoundaries,'test_phase_'+c['name'],phase_case(c))

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    manifest={'schema':'ir8-metadata-case-evidence/1','tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'files':EVIDENCE_FILES,'total_bytes':EVIDENCE_BYTES,'graph_executed':False,'native_executed':False,'source_admitted':False}
    data=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    with (EVIDENCE/'MANIFEST.json').open('xb') as f:f.write(data)
    print(json.dumps({'status':'passed' if result.wasSuccessful() else 'failed','tests':result.testsRun,'case_files':len(EVIDENCE_FILES),'case_bytes':EVIDENCE_BYTES,'graph_executed':False,'native_executed':False,'source_admitted':False}))
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
