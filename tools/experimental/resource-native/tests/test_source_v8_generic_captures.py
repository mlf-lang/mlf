#!/usr/bin/env python3
"""Controlled original-source tests for closed scalar generic captures.

One pending concrete owner is retained into a direct generic closure, then
returned through both complete scalar views. Source import authorization is a
fresh checker/generated-Code fact, not a runtime packet whitelist. Public events
do not expose every owner Access or capsule. Native guard controls cover that
separate boundary. No general capture, GC or performance claim is made here.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE/'tests')]
import run_source_v8 as cli
import source_build_v8 as build
from source_snapshot_v8 import bounded_read
from module_shared_transport import derive_shared_fragment
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime
from test_shared_source_native import at, instruction
from test_source_v8_recursive_sum import one, walk, var, source_allocation, INT
from test_source_v8_callable_captures import address, spine, read_json
from test_source_v8_monomorphic_recursion import ledger

require = build.require
QUALIFICATION_READY = True
BOOL = {'tag':'constructor','name':'Bool','arguments':[]}
EXPECTED_GUARDS = ((1 << 27)-1) & ~(1 << 24) & ~(1 << 4)
SHARED = 'module SharedPoly (sharedId) where\nsharedId : forall a. a -> a\nsharedId x = x\n'
SOURCES = {
 'generic-closed-scalar': 'import SharedPoly\nlet bonus = addInt 20 1 in\nlet k = \\x -> bonus in\naddInt (k true) (k 0)\n',
 'bool-scalar': 'import SharedPoly\nlet flag = ltInt 20 21 in\nlet k = \\x -> flag in\nif k 0 then if k true then 42 else 0 else 0\n',
}
NEGATIVES = {
 'mixed-scalar': ('import SharedPoly\nlet bonus = addInt 20 1 in\nlet flag = ltInt bonus 22 in\nlet k = \\x -> if flag then bonus else 0 in\naddInt (k true) (k 0)\n',
                 ['body','body','body','value','body','body','function','function','function']),
 'alias-scalar': ('import SharedPoly\nlet bonus = addInt 5 5 in\nlet other = bonus in\nlet k = \\x -> addInt bonus other in\naddInt 2 (addInt (k true) (k 0))\n',
                 ['body','body','body','value','body','body','function','function']),
}
ACCESS_SCOPE = ('The actual capture node and full metadata identity transport are checked; '
                'public events do not expose each acquired owner Access or callback Env. '
                'Post-begin retain and discharge are checked in emitted C and fresh resource facts.')


def source_facts(capture, case):
    require(case in SOURCES, 'known controlled source required')
    n=capture['normalization']; raw=n['raw_normalized']; boolean=case=='bool-scalar'
    require(capture['checked_type']==INT and n['policy']=='shared-rank1-callable/1' and
            len(n['steps'])==(4 if boolean else 0) and all(n[k] for k in
            ('declarations_equal','erasure_equal','normalized_rechecked','original_rechecked','root_type_alpha_equal')),
            'exact checked normalization policy/steps required')
    require(raw['tag']=='with_data', 'complete declaration context required')
    bonus=raw['body']; shared=bonus['body']; bp=['body']; sp=bp+['body']
    require(bonus['tag']==shared['tag']=='let' and shared['body']['tag']!='let', 'two original lexical lets required')
    head,_,args=spine(bonus['value'],bp+['value'])
    require(head['tag']=='primitive' and head['name']==('ltInt' if boolean else 'addInt') and head['arguments']==[] and
            [x for _,x in args]==[{'tag':'int64','value':20},{'tag':'int64','value':21 if boolean else 1}],
            'original pending scalar primitive differs')
    prefix=shared['value']; require(prefix['tag']=='type_lambda' and prefix['bound']=={'tag':'bottom'}, 'one bottom-bounded prefix required')
    lam=prefix['body']; cp=sp+['value','body']; scalar=BOOL if boolean else INT
    require(lam['tag']=='lambda' and lam['parameter_type']=={'tag':'var','id':prefix['id']} and
            var(lam['body'],bonus['name']), 'direct generic lambda must return the original lexical scalar')
    calls=[]
    for path,node in walk(shared['body'],sp+['body']):
        if isinstance(node,dict) and node.get('tag')=='application' and node['function'].get('tag')=='type_application' and var(node['function']['value'],shared['name']):
            calls.append((path,node))
    discovered=calls
    if boolean:
        _,_,outer_args=spine(shared['body'],sp+['body'])
        _,_,inner_args=spine(outer_args[1][1],outer_args[1][0])
        calls=[outer_args[0],inner_args[0]]
    else:
        _,_,calls=spine(shared['body'],sp+['body'])
    require({tuple(p) for p,_ in calls}=={tuple(p) for p,_ in discovered} and len(discovered)==2, 'exact semantic call positions differ')
    actual_args=[x['argument'] for _,x in calls]
    wanted=[{'tag':'int64','value':0},{'tag':'bool','value':True}] if boolean else [{'tag':'bool','value':True},{'tag':'int64','value':0}]
    require(actual_args==wanted, 'two actual ordered shared call arguments required')
    if boolean:
        outer,_,oa=spine(shared['body'],sp+['body']); inner,_,ia=spine(oa[1][1],oa[1][0])
        require(outer['tag']==inner['tag']=='primitive' and outer['name']==inner['name']=='ifThenElse' and
                outer['arguments']==inner['arguments']==[INT] and len(oa)==len(ia)==3 and
                oa[0][0]==calls[0][0] and ia[0][0]==calls[1][0] and
                ia[1][1]=={'tag':'int64','value':42} and oa[2][1]==ia[2][1]=={'tag':'int64','value':0},
                'two original lazy Int conditionals differ')
        dead_paths=[oa[2][0],ia[2][0]]
    else:
        root,_,aa=spine(shared['body'],sp+['body'])
        require(root['tag']=='primitive' and root['name']=='addInt' and [p for p,_ in aa]==[p for p,_ in calls], 'two shared results must be added')
        dead_paths=[]
    require(len([1 for _,x in walk(raw) if isinstance(x,dict) and x.get('tag')=='lambda'])==1, 'original lambda census differs')
    return dict(case=case,boolean=boolean,raw=raw,bonus=bonus,shared=shared,bp=bp,sp=sp,cp=cp,
                scalar=scalar,prefix=prefix,lam=lam,calls=calls,arguments=wanted,dead_paths=dead_paths)


def structure(capture, verified, plan, generated, case='generic-closed-scalar'):
    f=source_facts(capture,case);p=plan['program'];mapping=plan['binding']['source_map']
    replay=derive_shared_fragment(capture['projection']['projected_annotated'])
    for key in ('policy','input_checked_type','input_annotated','input_erased','raw_normalized','steps'):
        require(replay[key]==capture['normalization'][key], 'exact independent normalization differs: '+key)
    require(replay['polymorphism']['definitions']==verified['fragment']['definitions'] and
            replay['polymorphism']['uses']==verified['fragment']['uses'], 'fresh fragment evidence differs')
    require(verified['fragment_admitted'] and verified['normalization_replay']=='all exact independent fields match' and
            verified['producer_normalization_step_count']==(4 if f['boolean'] else 0), 'fresh exact independent replay required')
    definition=one(verified['fragment']['definitions'],'one captured generalized definition')
    scheme=one(mapping['scheme_map'],'one original Scheme map')
    require(definition['binding']==f['shared']['name'] and definition['binding_source']==address(f['sp']) and
            definition['rhs_cursor']==scheme['rhs_cursor']==address(f['cp']) and scheme['binder']==f['shared']['name']['id'] and
            len(definition['prefix'])==1 and definition['prefix'][0]['id']==f['prefix']['id'] and
            definition['free_term_bindings']==[f['bonus']['name']['id']], 'actual generalized binder/prefix/free owner differs')
    occurrence=address(f['cp']+['body'])
    require(definition['captures']=={'policy':'closed-scalar-generalization-captures/1','scalars':[
        {'binding':f['bonus']['name']['id'],'type':f['scalar'],'occurrences':[occurrence]}]}, 'exact captured source inventory differs')
    require(len(p['schemes'])==1 and p['schemes'][scheme['scheme']]['parameters']==1 and not p['families'] and not p['layouts'], 'only this one scalar Scheme is admitted')
    imported=one(scheme['imports'],'one exact import mapping');g=instruction(p,scheme['generalize']);seal=instruction(p,scheme['seal'])
    bonus=source_allocation(plan,f['bp']+['value'],'thunk');closure=source_allocation(plan,f['cp'],'closure')
    require(imported=={'binding':f['bonus']['name']['id'],'import':imported['import'],'layout':imported['layout'],
            'occurrences':[occurrence],'relation':'down','value':bonus['out']} and
            p['types'][imported['layout'][1:]]=={'tag':'closed','layout':'#bool' if f['boolean'] else '#i64'}, 'import owner/type/source join differs')
    require(g['imports']=={imported['import']:{'value':bonus['out'],'layout':imported['layout'],'relation':'down'}} and
            g['in']==bonus['in'] and g['scheme']==scheme['scheme'], 'original same-home import support/fallback differs')
    cap=one(list(closure['captures']),'one scalar capture')
    require(closure['captures']=={cap:imported['import']} and g['body']==[
            closure,{'op':'drop','value':imported['import']},{'op':'seal','value':closure['out']}] and seal==g['body'][-1],
            'direct closure/import drop/seal sequence differs')
    function=p['functions'][closure['function']];body=function['body'];ret=body[0]['out']
    require(function['type_scope']==scheme['scheme'] and function['captures']=={cap:{'layout':imported['layout'],'relation':'down'}} and
            body==[{'op':'retain','out':ret,'value':cap},{'op':'drop','value':cap},
                   {'op':'drop','value':function['parameter']},{'op':'return','value':ret}], 'generic callback must retain and return original capture')
    lambdas=[x for x in mapping['carrier_map'] if x['kind']=='lambda']
    require(len(lambdas)==len(p['functions'])==1 and lambdas[0]['source']==address(f['cp']) and
            lambdas[0]['ir_code']==closure['function'] and lambdas[0]['mono_captures']==[
             {'binder':f['bonus']['name']['id'],'capture':cap,'layout':imported['layout'],'relation':'down'}], 'generic Code cloned or capture origin lost')
    require(len(mapping['use_map'])==len(verified['fragment']['uses'])==len(p['instantiations'])==2, 'complete use census differs')
    vector_types=[INT,BOOL] if f['boolean'] else [BOOL,INT]
    for i,(row,source) in enumerate(zip(mapping['use_map'],verified['fragment']['uses'])):
        require(row['use']==i and row['definition']==source['definition']==0 and row['source']==source['source']==address(f['calls'][i][0]+['function']) and
                source['arguments']==[vector_types[i]] and source['instantiated_type']=={'tag':'arrow','from':vector_types[i],'to':f['scalar']} and
                [p['types'][t]['layout'] for t in row['arguments']]==['#i64' if vector_types[i]==INT else '#bool'], 'complete ordered Type/Use correspondence differs')
    checked=check_resources(p);d=json.loads(checked.derived_json);meta=json.loads(check_metadata(p).metadata_json)
    gf=one([x for x in d['instructions'] if x['path']==scheme['generalize']],'generalize resource facts')
    parent,alias=gf['inputs'][1],gf['outputs'][1]
    require(len(gf['inputs'])==len(gf['outputs'])==2 and parent['role']==['imports',imported['import'],'value'] and alias['role']==['imports',imported['import']] and
            parent['mode']==alias['mode']=='own' and parent['view']==alias['view']=='MONO' and not parent['ready'] and
            parent['capability']!=alias['capability'] and parent['storage']!=alias['storage'], 'fresh post-begin owned alias differs')
    for key in parent:
        if key not in ('role','capability','storage'):require(parent[key]==alias[key], 'import copied facts differ: '+key)
    prov=d['provenance'][parent['provenance']]['value']
    require(prov['kind']=='allocated' and prov['context']=={'kind':'concrete'} and parent['projection'] is None and parent['scheme'] is None and not parent['ticket'], 'allocated E0 provenance must not be guessed')
    drops=[x['inputs'][0] for x in d['instructions'] if x['op']=='drop']
    require(any(x['capability']==alias['capability'] for x in drops) and any(x['capability']==parent['capability'] for x in drops), 'parent/child aliases not independently discharged')
    require(p['entry'].index(g)<p['entry'].index({'op':'drop','value':bonus['out']}), 'parent owner released before intro completes')
    def mapped(path,role):
        m=one([x for x in mapping['allocation_map'] if x['source']==address(path) and x['role']==role], 'source allocation map')
        return one([x for x in meta['sites'] if x['path']==m['instruction']], 'exact allocation Site')
    bonus_site=mapped(f['bp']+['value'],'thunk');closure_site=mapped(f['cp'],'closure')
    call_sites=[mapped(path,'application') for path,_ in f['calls']]
    scheme_row=one(meta['schemes'],'one metadata Scheme');code=meta['codes'][closure_site['code']]
    scalar_type=one([x for x in meta['types'] if x['tag']=='closed' and x['atom']==('#bool' if f['boolean'] else '#i64')],'intrinsic Type')['id']
    require(bonus_site['id']==prov['site'] and bonus_site['scope'] is None and bonus_site['principal_type']==scalar_type and
            closure_site['scope']==scheme_row['id'] and code['scope']==scheme_row['id'] and code['captures']==[{'name':cap,'relation':'down','type':scalar_type}], 'actual concrete/generic Site contracts differ')
    slot=one([x for x in meta['slots'] if x['site']==closure_site['id']],'generic capture slot')
    require(slot['role']=={'kind':'capture','name':cap} and slot['type']==scalar_type and slot['relation']=='down', 'registered scalar CAPTURE contract differs')
    access=one([x for x in meta['accesses'] if x['site']==bonus_site['id']],'concrete bonus Access')
    require(access['mode']=='MONO' and access['origin_env']==access['use_env']==0 and access['type']==scalar_type and access['scheme'] is None, 'bonus actual E0 Access differs')
    transport=one([x for x in meta['transports'] if x['source_access']==access['id']],'one concrete identity transport')
    require(transport['kind']=='identity' and transport['projection_env'] is None and transport['result_access']==access['id'], 'concrete capture must preserve identity Access')
    uses=meta['uses'];require(len(uses)==2, 'two metadata Uses')
    semantic_uses=[]
    for i,vector in enumerate(vector_types):
        wanted='#i64' if vector==INT else '#bool';t=one([x for x in meta['types'] if x['tag']=='closed' and x['atom']==wanted],'argument atom')
        u=one([x for x in uses if x['arguments']==[t['id']]], 'source full vector metadata Use');semantic_uses.append(u)
        env=meta['environments'][u['env']];execution=one([x for x in meta['code_executions'] if x['code']==code['id'] and x['env']==env['id']], 'projected Code execution')
        require(u['arguments']==env['arguments']==[t['id']] and env['mode']=='CLOSED' and env['scheme']==u['scheme']==scheme_row['id'] and
                execution['argument']==t['id'] and execution['result']==scalar_type and execution['captures']==code['captures'], 'complete Env/Code scalar contract differs')
    for i,row in enumerate(mapping['use_map']):
        source_view=row['source_view'];require(source_view['kind']=='captured','shared source use must keep captured full view')
        carrier=one([x for x in mapping['carrier_map'] if x['carrier']==source_view['carrier']],'use carrier')
        view=one([x for x in carrier['view_captures'] if x['capture']==source_view['capture']],'actual captured full view')
        creation=one(row['creation'],'source use retains original view');retain=instruction(p,creation)
        op=source_allocation(plan,f['calls'][i][0],'application')
        require(view['arguments']==row['arguments'] and view['binder']==scheme['binder'] and
                retain['op']=='retain' and retain['value']==view['capture'] and retain['out']==op['function'],
                'source call must consume its complete captured view')
        fnslot=one([x for x in meta['slots'] if x['site']==call_sites[i]['id'] and x['role']=={'kind':'function'}],'ordinary function slot')
        require(fnslot['type']==semantic_uses[i]['result_type'], 'source call callable contract differs')
    for carrier in mapping['carrier_map']:
        for view in carrier['view_captures']:
            ops=[instruction(p,x) for x in view['creation']];origin=view['source_view']
            require(view['binder']==scheme['binder'] and view['definition']==0 and view['relation']=='down', 'captured view origin/full pair differs')
            if origin['kind']=='scheme':
                require(len(ops)==4 and ops[0]['op']=='retain' and ops[0]['value']==g['out'] and
                        ops[1]['op']=='instantiate' and ops[1]['value']==ops[0]['out'] and
                        p['instantiations'][ops[1]['instantiation']]['arguments']==view['arguments'], 'initial complete view creation differs')
                temp=ops[1]['out'];host=ops[2]
            else:
                require(origin['kind']=='captured' and len(ops)==3,'transitive view must retain original pair')
                parent_carrier=one([x for x in mapping['carrier_map'] if x['carrier']==origin['carrier']],'parent view carrier')
                parent_view=one([x for x in parent_carrier['view_captures'] if x['capture']==origin['capture']],'parent captured pair')
                require(parent_view['arguments']==view['arguments'] and parent_view['binder']==view['binder'] and
                        ops[0]['op']=='retain' and ops[0]['value']==origin['capture'], 'transitive full-vector capture differs')
                temp=ops[0]['out'];host=ops[1]
            require(host['op']=='thunk' and host['code']==carrier['ir_code'] and host['captures'][view['capture']]==temp and
                    ops[-1]=={'op':'drop','value':temp}, 'captured view must be published before temporary release')
    require(emit_runtime(p).runtime_source==generated, 'generated C differs from fresh checked emission')
    entry=generated.split('static void rt8_entry(Rt8Context *ctx)',1)[1].split('\n}\n',1)[0]
    acquired=re.search(r'rt8_generic_begin\([^;]+;\s*(h\d+) = rt8_retain\(ctx, (h\d+)\);',entry)
    require(acquired is not None, 'post-begin retain must precede generic publication')
    child,parent_c=acquired.groups();begin=acquired.start();drop=entry.index('rt8_drop(ctx, '+child+');',acquired.end());seal_at=entry.index('rt8_generic_seal(',drop)
    closure_at=entry.index('rt8_closure(',acquired.end())
    require(begin<closure_at<drop<seal_at<entry.index('rt8_drop(ctx, '+parent_c+');',seal_at) and
            re.search(r'\w+\[0\] = '+child+r';',entry[acquired.end():closure_at]), 'emitted alias capture/discharge/parent preservation differs')
    return dict(facts=f,meta=meta,scheme=scheme_row,bonus_site=bonus_site,closure_site=closure_site,call_sites=call_sites,
                bonus_op=bonus,closure_op=closure,cap=cap,code=code,uses=uses,semantic_uses=semantic_uses,identity_access=access['id'],
                alias_facts={'parent_capability':parent['capability'],'child_capability':alias['capability'],'node':parent['node'],'ready':parent['ready']})


def observe(evaluation, info):
    e=evaluation;f=info['facts'];meta=info['meta'];events=e['events']
    require(e['schema']=='resource-ir-v8-run/1' and e['state']==e['fault']==0 and e['result']=={'kind':'i64','value':42} and
            e['scalar_result_kind']==1 and e['scalar_result']==42 and not e['events_omitted'] and e['events_emitted']==len(events), 'complete native Int42 report required')
    require(e['guards_failed_mask']==0 and e['guards_checked_mask']==EXPECTED_GUARDS and
            0<e['guard_work_used']==e['guard_work_total']<=e['guard_work_limit']==67108864, 'native guard/work coverage differs')
    ledger(e,True)
    select=lambda name:[(i,x) for i,x in enumerate(events) if x['event']==name]
    allocations=select('allocate');nodes={x['node']:x for _,x in allocations}
    require(len(nodes)==len(allocations), 'allocation identities must be unique')
    for _,x in allocations:
        site=meta['sites'][x['site_id']];se=one([y for y in meta['site_executions'] if y['site']==site['id'] and y['env']==x['env_id']], 'actual SiteExecution')
        rep=meta['representations'][se['representation']]
        require(x['shape_id']==rep['shape'] and x['code']==(meta['codes'][site['code']]['name'] if site['code'] is not None else None), 'allocation Site/Code/representation differs')
    bi,b=one([(i,x) for i,x in allocations if x['site_id']==info['bonus_site']['id']], 'one original pending scalar allocation')
    ci,c=one([(i,x) for i,x in allocations if x['site_id']==info['closure_site']['id']], 'one original generic closure allocation')
    require(b['state']=='THUNK' and b['env_id']==0 and b['slots']=={} and c['state']=='CLOSURE' and
            c['env_id']==info['scheme']['neutral_env'] and c['slots']=={info['cap']:b['node']}, 'capture must preserve original pending concrete node')
    gi,g=one(select('generic_begin'),'one generic begin');si,s=one(select('generic_seal'),'one generic seal')
    require(bi<gi<ci<si and g['scheme']==info['scheme']['id'] and g['intro']==s['intro']==info['scheme']['intro'] and
            g['capsule']==s['capsule']>0 and s['node']==c['node'] and s['owner']>g['watermark'], 'generic intro/closure/seal ordering differs')
    sealed_old=meta['accesses'][s['old_access']]
    require(sealed_old['mode']=='MONO' and sealed_old['site']==info['closure_site']['id'] and
            sealed_old['origin_env']==sealed_old['use_env']==c['env_id'] and
            sealed_old['type']==info['closure_site']['principal_type'] and sealed_old['scheme'] is None,
            'seal must consume the exact neutral generic callable Access')
    install_i,install=one([(i,x) for i,x in select('slot_install') if x['host']==c['node'] and x['field']==info['cap']], 'one original scalar capture publication')
    require(gi<install_i<ci and install['target']==b['node'] and install['target_state']=='THUNK', 'capture was forced, copied or substituted during intro')
    inst=select('instantiate');require(len(inst)==2, 'two complete actual shared instantiations required')
    require(len({x['owner'] for _,x in inst})==2 and all(
            i>si and x['owner']>g['watermark'] and x['owner']!=s['owner'] and x['anchor'] is None
            for i,x in inst), 'complete owned views require distinct fresh unanchored owners')
    for (_,x),u in zip(inst,info['uses']):
        a=meta['accesses'][x['new_access']];old=meta['accesses'][x['old_access']]
        require(x['node']==c['node'] and x['use']==u['id'] and x['scheme']==info['scheme']['id'] and x['mode']=='own' and
                old['id']==s['new_access'] and old['mode']=='SCHEME' and
                a['mode']=='MONO' and a['site']==info['closure_site']['id'] and a['origin_env']==c['env_id'] and
                a['use_env']==u['env'] and a['type']==u['result_type'], 'full-vector same-node Access/Env move differs')
    invokes=[x for x in select('invoke_enter') if x[1]['closure']==c['node']]
    returns=[x for x in select('invoke_raw_return') if x[1]['closure']==c['node']]
    handoffs=[x for x in select('closure_capture_handoff') if x[1]['node']==c['node']]
    frames=[x for x in select('frame_enter') if x[1]['context'].get('kind')=='function']
    require(len(invokes)==len(returns)==len(handoffs)==len(frames)==2 and
            all(x['context']['name']==info['code']['name'] and x['context']['node']==c['node'] for _,x in frames), 'same generic Code must execute twice')
    owners=[];apps=[]
    for i,((enter_i,call),(return_i,ret),(hand_i,hand)) in enumerate(zip(invokes,returns,handoffs)):
        ai,app=one([(j,x) for j,x in allocations if x['site_id']==info['call_sites'][i]['id']], 'one ordinary source call allocation')
        scalar=one([x for _,x in select('scalar_value') if x['node']==call['argument']], 'actual call argument')
        wanted=f['arguments'][i]
        require(scalar['kind']==('bool' if wanted['tag']=='bool' else 'i64') and scalar['value']==wanted['value'] and
                app['state']=='APPLICATION' and app['slots']=={'$function':c['node'],'$argument':call['argument']} and
                ai<hand_i<enter_i<return_i and ret['argument']==call['argument'] and ret['result']==b['node'] and
                hand['protocol']=='repeat' and set(hand['owners'])=={info['cap']}, 'ordinary invocation must return the original imported owner')
        owners.append(hand['owners'][info['cap']]);apps.append(app['node'])
    require(len(set(owners))==2 and all(x>0 for x in owners), 'each call must acquire a fresh capture owner')
    callback_i,callback=one([(i,x) for i,x in select('callback_enter') if x['node']==b['node']], 'one pending bonus callback')
    memo_i,memo=one([(i,x) for i,x in select('memo_publish') if x['destination']==b['node']], 'one bonus memo publication')
    raw_i,raw=one([(i,x) for i,x in select('raw_return') if x['source']==b['node']], 'one bonus raw return')
    value=one([x for _,x in select('scalar_value') if x['node']==memo['result']], 'one ready bonus result')
    require(si<returns[0][0]<callback_i<raw_i<memo_i<returns[1][0] and raw['result']==memo['result'] and raw['result_state']=='READY' and
            value['kind']==('bool' if f['boolean'] else 'i64') and value['value']==(True if f['boolean'] else 21) and
            value['primitive']==('ltInt' if f['boolean'] else 'addInt'), 'bonus must evaluate once after first call and be reused after memo')
    require(not any(x['event'] in ('callback_enter','update_pin') and x.get('node')==b['node'] for x in events[:si]), 'intro forced imported pending owner')
    for node in apps:
        result=one([x for _,x in select('memo_publish') if x['destination']==node], 'one application completion')
        require(result['result']==memo['result'], 'both calls must memoize the same original scalar result')
    require(e['metrics']['memo_fast_paths']>=1, 'second bonus demand must use memo')
    removed_i,removed=one([(i,x) for i,x in select('slot_remove') if x['host']==c['node'] and x['field']==info['cap']], 'one captured owner release')
    require(removed_i>returns[-1][0] and removed['target']==b['node'] and removed['target_state']=='MEMO' and removed['reason']=='group_close', 'capture lifetime must cover both invocations')
    if f['boolean']:
        choices=select('select_i64');require(len(choices)==2 and all(x['condition_value'] is True for _,x in choices), 'both Bool uses must choose the true arm')
        for (choice_i,choice),app_node in zip(choices,apps):
            app_memo_i,_=one([(i,x) for i,x in select('memo_publish') if x['destination']==app_node], 'selected source call memo')
            require(choice['condition_node']==memo['result'] and choice['result']==choice['then_node'] and
                    app_memo_i<choice_i, 'true selection must use the actual shared Bool and corresponding completed call')
        require(not any(x.get('event')=='scalar_value' and x.get('value')==0 and x.get('node') not in [r[1]['argument'] for r in invokes] for x in events), 'unselected zero branch was evaluated')
    metrics=e['metrics']
    require(metrics['nodes_allocated']==len(allocations) and metrics['ordinary_calls']==len(select('invoke_enter')) and
            metrics['callback_calls']==len(select('callback_enter')) and metrics['memo_writes']==len(select('memo_publish')) and
            metrics['groups_closed']==len(select('close_group')), 'event/metric census differs')
    return {'status':'passed','case':f['case'],'shared_node':c['node'],'bonus_node':b['node'],'bonus_result':memo['result'],
            'code':info['code']['name'],'vectors':[u['arguments'] for u in info['uses']],
            'source_use_vectors':[u['arguments'] for u in info['semantic_uses']],
            'normalization_policy':'shared-rank1-callable/1','normalization_steps':4 if f['boolean'] else 0,
            'capture_owners':owners,'identity_access':info['identity_access'],'callback_once':True,'imports':info['alias_facts'],
            'guard_mask':e['guards_checked_mask'],'events':len(events),'work':e['guard_work_used'],'access_scope':ACCESS_SCOPE}


def copied_controls(evaluation, info):
    original=observe(evaluation,info);rows=[]
    def event(r,name,predicate=lambda x:True):return next(x for x in r['events'] if x['event']==name and predicate(x))
    def reject(name,change):
        r=copy.deepcopy(evaluation);change(r)
        try:observe(r,info)
        except (AssertionError,KeyError,ValueError,IndexError):rows.append({'control':name,'status':'rejected'})
        else:raise AssertionError('copied report control accepted: '+name)
    b=original['bonus_node'];c=original['shared_node'];v=original['bonus_result']
    reject('wrong-result',lambda r:r['result'].__setitem__('value',41))
    reject('omitted-events',lambda r:r.__setitem__('events_omitted',1))
    reject('project-bit-invented',lambda r:r.__setitem__('guards_checked_mask',r['guards_checked_mask']|(1<<4)))
    reject('live-ledger',lambda r:r['memory'].__setitem__('live_bytes',1))
    reject('bonus-relabelled-neutral',lambda r:event(r,'allocate',lambda x:x['node']==b).__setitem__('env_id',info['scheme']['neutral_env']))
    reject('bonus-forced-before-capture',lambda r:event(r,'allocate',lambda x:x['node']==b).__setitem__('state','READY'))
    reject('capture-target-replaced',lambda r:event(r,'allocate',lambda x:x['node']==c)['slots'].__setitem__(info['cap'],v))
    reject('slot-publication-ready',lambda r:event(r,'slot_install',lambda x:x['host']==c).__setitem__('target_state','READY'))
    reject('seal-wrong-node',lambda r:event(r,'generic_seal').__setitem__('node',b))
    reject('seal-pre-watermark-owner',lambda r:event(r,'generic_seal').__setitem__('owner',event(r,'generic_begin')['watermark']))
    reject('seal-invalid-old-access',lambda r:event(r,'generic_seal').__setitem__('old_access',len(info['meta']['accesses'])))
    def reused_view_owner(r):
        xs=[x for x in r['events'] if x['event']=='instantiate'];xs[1]['owner']=xs[0]['owner']
    reject('reused-instantiation-owner',reused_view_owner)
    reject('anchored-owned-view',lambda r:event(r,'instantiate').__setitem__('anchor',1))
    reject('collapse-use-views',lambda r:[x.__setitem__('new_access',event(r,'instantiate')['new_access']) for x in r['events'] if x['event']=='instantiate'])
    reject('invoke-wrong-code',lambda r:event(r,'frame_enter',lambda x:x['context'].get('kind')=='function')['context'].__setitem__('name','wrong'))
    reject('return-copied-scalar',lambda r:event(r,'invoke_raw_return',lambda x:x['closure']==c).__setitem__('result',v))
    reject('lost-capture-owner',lambda r:event(r,'closure_capture_handoff',lambda x:x['node']==c).__setitem__('owners',{}))
    def alias_owners(r):
        xs=[x for x in r['events'] if x['event']=='closure_capture_handoff' and x['node']==c];xs[1]['owners']=dict(xs[0]['owners'])
    reject('reused-capture-owner',alias_owners)
    reject('wrong-bonus-value',lambda r:event(r,'scalar_value',lambda x:x['node']==v).__setitem__('value',False if info['facts']['boolean'] else 22))
    reject('wrong-bonus-memo',lambda r:event(r,'memo_publish',lambda x:x['destination']==b).__setitem__('result',b))
    def duplicate(r):
        r['events'].append(copy.deepcopy(event(r,'callback_enter',lambda x:x['node']==b)));r['events_emitted']=len(r['events'])
    reject('bonus-recomputed',duplicate)
    reject('capture-released-early',lambda r:event(r,'slot_remove',lambda x:x['host']==c).__setitem__('reason','payload_clear'))
    reject('memo-fast-path-missing',lambda r:r['metrics'].__setitem__('memo_fast_paths',0))
    reject('wrong-call-census',lambda r:r['metrics'].__setitem__('ordinary_calls',1))
    if info['facts']['boolean']:
        reject('wrong-selected-branch',lambda r:event(r,'select_i64').__setitem__('condition_value',False))
        reject('foreign-condition-node',lambda r:event(r,'select_i64').__setitem__('condition_node',max(x['node'] for x in r['events'] if x['event']=='allocate')+1))
        reject('false-selected-result',lambda r:event(r,'select_i64').__setitem__('result',event(r,'select_i64')['else_node']))
    return rows


def structure_controls(capture,verified,plan,generated,case='generic-closed-scalar'):
    structure(capture,verified,plan,generated,case);rows=[]
    def reject(name,change):
        c,v,p,g=copy.deepcopy(capture),copy.deepcopy(verified),copy.deepcopy(plan),generated
        altered=change(c,v,p,g);g=altered if isinstance(altered,str) else g
        try:structure(c,v,p,g,case)
        except (AssertionError,ValueError,KeyError,IndexError):rows.append({'control':name,'status':'rejected'})
        else:raise AssertionError('copied structure control accepted: '+name)
    sm=lambda p:p['binding']['source_map']['scheme_map'][0]
    reject('changed-normalization-policy',lambda c,v,p,g:c['normalization'].__setitem__('policy','shared-rank1-callable/3'))
    if case=='bool-scalar':
        reject('changed-normalization-proof',lambda c,v,p,g:c['normalization']['steps'][0].__setitem__('rule','wrong'))
    reject('wrong-source-owner',lambda c,v,p,g:sm(p)['imports'][0].__setitem__('binding',sm(p)['binder']))
    reject('lost-source-occurrence',lambda c,v,p,g:sm(p)['imports'][0].__setitem__('occurrences',[]))
    reject('lost-full-vector',lambda c,v,p,g:p['binding']['source_map']['use_map'][0].__setitem__('arguments',[]))
    reject('false-capture-type',lambda c,v,p,g:v['fragment']['definitions'][0]['captures']['scalars'][0].__setitem__('type',INT if case=='bool-scalar' else BOOL))
    reject('missing-import',lambda c,v,p,g:instruction(p['program'],sm(p)['generalize']).__setitem__('imports',{}))
    reject('leaked-child-owner',lambda c,v,p,g:instruction(p['program'],sm(p)['generalize'])['body'].pop(1))
    reject('wrong-import-support',lambda c,v,p,g:instruction(p['program'],sm(p)['generalize'])['imports'][sm(p)['imports'][0]['import']].__setitem__('relation','below'))
    reject('removed-post-begin-retain',lambda c,v,p,g:g.replace(' = rt8_retain(ctx,',' = forbidden_alias(ctx,',1))
    reject('changed-generic-return',lambda c,v,p,g:g.replace('return rt8_return(ctx,','return forbidden_return(ctx,',1))
    return rows


def run_case(args,output,env,case):
    require(QUALIFICATION_READY,'portable suite is awaiting independent review')
    inputs=output/'inputs';inputs.mkdir()
    for name,text in {'main.emlf':SOURCES[case],'SharedPoly.emlf':SHARED}.items():(inputs/name).write_text(text,encoding='utf-8')
    target=output/case
    build.run([sys.executable,'-B',str(BASE/'run_source_v8.py'),str(inputs/'main.emlf'),'--module-root',str(inputs),
               '--ghc',args.ghc,'--cc',args.cc,'--output',str(target)],output,case,cwd=BASE,env=env,
              wall=1200,cpu=900,memory=16<<30,termination_grace=15,stdout_limit=1<<20,stderr_limit=1<<20,file_limit=64<<20)
    require(not bounded_read(output/(case+'.stderr'),1<<20),'successful CLI stderr')
    result=read_json(target/'result.json');e=read_json(target/'native/run.stdout')
    require(result['status']=='complete' and result['failure_policy']=='retain' and result['native']==e and 'placement' not in result,'fresh default CLI result differs')
    c=read_json(target/'capture.stdout');v=read_json(target/'verification.json');p=read_json(target/'planned.json',8<<20)
    require(p['binding']['mode']=='coarse-owned','default placement changed')
    g=bounded_read(target/'native/ir8_runtime_generated.c',8<<20).decode();info=structure(c,v,p,g,case)
    row={'status':'passed','observation':observe(e,info),'copied_report_controls':copied_controls(e,info),
         'copied_structure_controls':structure_controls(c,v,p,g,case),'source_hashes':{
          'main.emlf':build.sha(SOURCES[case].encode()),'SharedPoly.emlf':build.sha(SHARED.encode())}}
    build.save(target/'generic-capture-observations.json',row);print(case+': PASS',flush=True);return row


def rejected_source(capture,verified,case):
    _,path=NEGATIVES[case]
    diagnostic='FRAGMENT at '+repr(path)+': generic construction opcode outside exact allowlist'
    require(verified['status']=='diagnostic-custody-pass-fragment-rejected' and
            verified['fragment_admitted'] is False and not verified['source_admitted'] and not verified['native_admitted'] and
            verified['fragment_error']=={'code':'FRAGMENT','path':path,'message':diagnostic} and
            verified['normalization_replay']=='not completed; retained fragment rejected' and
            capture['checked_type']==INT, 'exact checked-source FRAGMENT refusal differs')
    return {'status':'rejected-before-native','diagnostic':diagnostic,'source_hash':build.sha(NEGATIVES[case][0].encode()),
            'normalization_replay':verified['normalization_replay']}


def rejection_controls(capture,verified,case):
    rejected_source(capture,verified,case);rows=[]
    for name,key,value in [('wrong-code','code','CAPTURE'),('wrong-path','path',[]),('wrong-message','message','unrelated refusal')]:
        v=copy.deepcopy(verified);v['fragment_error'][key]=value
        try:rejected_source(capture,v,case)
        except AssertionError:rows.append({'control':name,'status':'rejected'})
        else:raise AssertionError('copied source refusal accepted: '+name)
    return rows


def negative(args,output,env,case):
    text,path=NEGATIVES[case];inputs=output/'inputs';inputs.mkdir()
    (inputs/'main.emlf').write_text(text,encoding='utf-8');(inputs/'SharedPoly.emlf').write_text(SHARED,encoding='utf-8')
    target=output/case
    build.run([sys.executable,'-B',str(BASE/'run_source_v8.py'),str(inputs/'main.emlf'),'--module-root',str(inputs),
               '--ghc',args.ghc,'--cc',args.cc,'--output',str(target)],output,case,cwd=BASE,env=env,
              wall=1200,cpu=900,memory=16<<30,expected=1,termination_grace=15,stdout_limit=1<<20,stderr_limit=1<<20,file_limit=64<<20)
    failure=read_json(target/'failure.json')
    capture=read_json(target/'capture.stdout');verified=read_json(target/'verification.json')
    row=rejected_source(capture,verified,case)
    expected='AssertionError: source outside supported shared fragment: '+repr({'code':'FRAGMENT','path':path,'message':row['diagnostic']})
    require(failure.get('error')==expected and failure['source_recheck_errors']==[] and
            not (target/'native').exists() and not (target/'planned.json').exists(),
            'exact unsupported generic operation must reject before planning/native')
    row['copied_refusal_controls']=rejection_controls(capture,verified,case)
    build.save(target/'generic-capture-rejection.json',row);print(case+': EXPECTED FRAGMENT',flush=True);return row


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ghc',required=True);parser.add_argument('--cc',default='cc')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--case',choices=('all',)+tuple(SOURCES)+tuple(NEGATIVES),default='all');args=parser.parse_args()
    require(QUALIFICATION_READY,'portable suite is awaiting independent review')
    output=args.output.absolute();require(output.resolve()==output and output!=BASE.parents[2] and BASE.parents[2] not in output.parents,'fresh output must be outside checkout')
    output.mkdir(parents=True,exist_ok=False);env=cli.environment(output);build.SUITE_DEADLINE=time.monotonic()+1500;rows={}
    try:
        for case in tuple(SOURCES)+tuple(NEGATIVES) if args.case=='all' else (args.case,):
            child=output/case;child.mkdir();rows[case]=run_case(args,child,env,case) if case in SOURCES else negative(args,child,env,case)
    except BaseException as exc:
        try:build.save(output/'failure.json',{'error':repr(exc)})
        except BaseException as persistence:exc.add_note('Failure persistence also failed: '+repr(persistence))
        raise
    build.save(output/'results.json',{'status':'passed','cases':rows});return 0


if __name__=='__main__':raise SystemExit(main())
