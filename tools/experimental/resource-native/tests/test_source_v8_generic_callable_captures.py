#!/usr/bin/env python3
"""Controlled source/event qualification of two concrete callable imports.

The actual inferred direct-helper source is preserved, not specialized. Static
facts authenticate its complete callable Type, own legacy representation and
Code. Events show physical nodes, allocation Envs, calls and handoff owners, not
every acquired owner Access/capsule. Focused guards supply separate evidence for
those private boundaries. The second authenticated source captures one pending
scalar inside the ordinary helper, not directly inside the generalized root.
"""
import argparse
import copy
from collections import Counter
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
BOOL = {'tag':'constructor','name':'Bool','arguments':[]}
QUALIFICATION_READY = True
SOURCE = 'import SharedPoly\nlet helper = \\n -> addInt 21 n in\nlet k = \\x -> helper 0 in\naddInt (k true) (k 0)\n'
CAPTURED_SOURCE = 'import SharedPoly\nlet bonus = addInt 20 1 in\nlet helper = \\n -> addInt bonus n in\nlet k = \\x -> helper 0 in\naddInt (k true) (k 0)\n'
SHARED = 'module SharedPoly (sharedId) where\nsharedId : forall a. a -> a\nsharedId x = x\n'
ACCESS_SCOPE = ('Source/resource/metadata/generated-Code identity joins and physical '
                'helper nodes, own Code/representation and E0 allocations are checked. '
                'Public events do not expose every acquired owner Access, authority-owner '
                'group association or callback capsule. Identity transport and private guard controls are separate '
                'bounded evidence, not a native import whitelist.')


def source_facts(capture):
    n=capture['normalization'];raw=n['raw_normalized']
    require(capture['checked_type']==INT and n['policy']=='shared-rank1-callable/1' and n['steps']==[] and
            all(n[k] for k in ('declarations_equal','erasure_equal','original_rechecked',
                              'normalized_rechecked','root_type_alpha_equal')) and raw['tag']=='with_data',
            'exact original checked normalization required')
    replay=derive_shared_fragment(capture['projection']['projected_annotated'])
    for key in ('policy','input_checked_type','input_annotated','input_erased','raw_normalized','steps'):
        require(replay[key]==n[key], 'independent normalization differs: '+key)
    top=raw['body'];captured=top['value']['tag']!='lambda';bonus=top if captured else None
    hp=['body','body'] if captured else ['body'];helper=at(raw,hp);shared=helper['body']
    kp=hp+['body'];lp=hp+['value'];cp=kp+['value','body'];bonus_args=[]
    require(helper['tag']==shared['tag']=='let' and shared['body']['tag']!='let', 'exact original lexical let spine required')
    if captured:
        head,_,bonus_args=spine(bonus['value'],['body','value'])
        require(bonus['tag']=='let' and head=={'tag':'primitive','id':8,'name':'addInt','arguments':[]} and
                [x for _,x in bonus_args]==[{'tag':'int64','value':20},{'tag':'int64','value':1}], 'original pending bonus must remain addInt20 1')
    lam=helper['value'];prefix=shared['value'];generic=prefix['body']
    require(lam['tag']=='lambda' and lam['parameter_type']==INT and prefix['tag']=='type_lambda' and
            prefix['bound']=={'tag':'bottom'} and generic['tag']=='lambda' and
            generic['parameter_type']=={'tag':'var','id':prefix['id']}, 'original ordinary/generic lambda contracts differ')
    head,_,args=spine(lam['body'],lp+['body'])
    require(head=={'tag':'primitive','id':8,'name':'addInt','arguments':[]} and len(args)==2 and
            (var(args[0][1],bonus['name']) if captured else args[0][1]=={'tag':'int64','value':21}) and
            var(args[1][1],lam['parameter']), 'helper must compute its original scalar plus parameter')
    app=generic['body']
    require(app['tag']=='application' and var(app['function'],helper['name']) and
            app['argument']=={'tag':'int64','value':0}, 'generic lambda must apply the original helper to zero')
    head,_,calls=spine(shared['body'],kp+['body'])
    require(head=={'tag':'primitive','id':8,'name':'addInt','arguments':[]} and len(calls)==2, 'original outer addition differs')
    for (_,call),arg in zip(calls,[{'tag':'bool','value':True},{'tag':'int64','value':0}]):
        require(call['tag']=='application' and call['function']['tag']=='type_application' and
                var(call['function']['value'],shared['name']) and call['argument']==arg, 'two complete original shared calls differ')
    require(len([1 for _,x in walk(raw) if isinstance(x,dict) and x.get('tag')=='lambda'])==2,
            'helper/shared lambda was cloned or substituted')
    return dict(raw=raw,replay=replay,helper=helper,shared=shared,lam=lam,prefix=prefix,generic=generic,
                hp=hp,kp=kp,lp=lp,cp=cp,helper_args=args,calls=calls,captured=captured,bonus=bonus,bonus_args=bonus_args,arrow={'tag':'arrow','from':INT,'to':INT})


def structure(capture,verified,plan,generated):
    f=source_facts(capture);p=plan['program'];mapping=plan['binding']['source_map'];poly=f['replay']['polymorphism']
    require(verified['fragment_admitted'] and verified['normalization_replay']=='all exact independent fields match' and
            verified['producer_normalization_step_count']==0 and verified['fragment']['definitions']==poly['definitions'] and
            verified['fragment']['uses']==poly['uses'], 'fresh source witness/capture evidence differs')
    require([(x['source'],x['tag']) for x in mapping['term_map']]==
            [(x['normalized'],x['tag']) for x in f['replay']['term_correspondence']], 'ordinary term correspondence changed')
    for row in mapping['term_map']:
        node=at(f['raw'],row['source']['path'])
        if node['tag'] in ('let','var','lambda'):
            require(row['binder']==node['parameter' if node['tag']=='lambda' else 'name']['id'], 'ordinary lexical binder correspondence changed')
    definition=one(poly['definitions'],'one inferred generic definition');sm=one(mapping['scheme_map'],'one Scheme mapping')
    occurrence=address(f['cp']+['body','function'])
    require(definition['binding']==f['shared']['name'] and definition['binding_source']==address(f['kp']) and
            definition['rhs_cursor']==sm['rhs_cursor']==address(f['cp']) and sm['binder']==f['shared']['name']['id'] and
            definition['free_term_bindings']==[f['helper']['name']['id']] and definition['captures']=={
                'policy':'closed-scalar-concrete-callable-generalization-captures/1','scalars':[],
                'callables':[{'binding':f['helper']['name']['id'],'type':f['arrow'],'occurrences':[occurrence],
                              'binding_source':address(f['hp']),'value_source':address(f['lp'])}]},
            'exact helper binding/type/direct-allocation/occurrence inventory differs')
    require(len(p['functions'])==2 and len(p['codes'])==(3 if f['captured'] else 2) and len(p['schemes'])==1 and not p['families'] and not p['layouts'],
            'one helper, one shared generic and two ordinary primitive carriers required')
    g=instruction(p,sm['generalize']);helper=source_allocation(plan,f['lp'],'closure');root=source_allocation(plan,f['cp'],'closure')
    imp=one(sm['imports'],'one explicit helper import');scope=sm['scheme']
    require(imp=={'binding':f['helper']['name']['id'],'import':imp['import'],'layout':imp['layout'],
                  'occurrences':[occurrence],'relation':'down','value':helper['out']} and
            g['imports']=={imp['import']:{'layout':imp['layout'],'relation':'down','value':helper['out']}}, 'import must retain original helper owner')
    carriers=mapping['carrier_map']
    def carrier(path,kind):return one([x for x in carriers if x['source']==address(path) and x['kind']==kind], 'exact source carrier')
    hc=carrier(f['lp'],'lambda');gc=carrier(f['cp'],'lambda');bc=carrier(f['lp']+['body'],'primitive');outer=carrier(f['kp']+['body'],'primitive')
    cap=one(gc['mono_captures'],'whole helper capture')
    require(plan['binding']['mode'] in ('coarse-owned','data-groups-prototype'), 'known placement required')
    grouped=plan['binding']['mode']=='data-groups-prototype';strict=grouped and not f['captured'];relation='below' if strict else 'down'
    hcap=one(hc['mono_captures'],'one original helper capture') if f['captured'] else None
    bonus=source_allocation(plan,['body','value'],'thunk') if f['captured'] else None
    require(hc['ir_code']==helper['function'] and len(hc['mono_captures'])==int(f['captured']) and not hc['view_captures'] and hc['type_scope'] is None and
            gc['ir_code']==root['function'] and cap=={'binder':imp['binding'],'capture':cap['capture'],'layout':imp['layout'],'relation':relation} and
            gc['type_scope']==scope and not gc['view_captures'] and root['captures']=={cap['capture']:imp['import']} and
            g['body']==[root,{'op':'drop','value':imp['import']},{'op':'seal','value':root['out']}], 'whole closure/import-discharge/direct seal sequence differs')
    require(helper['captures']==({hcap['capture']:bonus['out']} if f['captured'] else {}) and p['entry'].index({'op':'drop','value':helper['out']})>p['entry'].index(g), 'parent helper must remain live through seal')
    if strict:
        authority=one([x for x in p['entry'] if x.get('out')==g['in']], 'actual import-supported introduction group')
        require(authority=={'op':'new_below','out':g['in'],'ceiling':p['entry'][0]['out'],'imports':[helper['out']]},
                'Below relation needs actual imported support, not distinct group names')
    else:
        require(g['in']==helper['in']==p['entry'][0]['out'], 'captured helper must use actual same-home Down fallback')
    if f['captured']:
        require(hcap['binder']==f['bonus']['name']['id'] and hcap['relation']=='down' and
                p['types'][hcap['layout'][1:]]=={'tag':'closed','layout':'#i64'} and bonus['captures']=={} and
                p['entry'].index(bonus)<p['entry'].index(helper)<p['entry'].index(g)<p['entry'].index({'op':'drop','value':bonus['out']}),
                'whole helper must retain its original pending scalar without flattening or forcing')
    hf=p['functions'][helper['function']];gf=p['functions'][root['function']]
    hpending=source_allocation(plan,f['lp']+['body'],'thunk');bodyapp=source_allocation(plan,f['cp']+['body'],'application')
    zero=source_allocation(plan,f['cp']+['body','argument'],'scalar')
    argcap=one([x for x in bc['mono_captures'] if x['binder']==f['lam']['parameter']['id']], 'helper argument carrier capture');bcap=argcap['capture']
    bbonus=one([x for x in bc['mono_captures'] if x['binder']==f['bonus']['name']['id']], 'helper body bonus capture') if f['captured'] else None
    hcontracts={hcap['capture']:{'layout':hcap['layout'],'relation':'down'}} if f['captured'] else {}
    bbindings={bcap:hf['parameter']};hbody=[hpending]
    if f['captured']:
        bbindings[bbonus['capture']]=hcap['capture'];hbody.append({'op':'drop','value':hcap['capture']})
    hbody += [{'op':'drop','value':hf['parameter']},{'op':'return','value':hpending['out']}]
    require(hf['type_scope'] is None and hf['captures']==hcontracts and hpending['captures']==bbindings and
            hf['body']==hbody and
            hpending['code']==bc['ir_code'] and bc['type_scope'] is None and not bc['view_captures'] and
            len(bc['mono_captures'])==1+int(f['captured']) and argcap['relation']=='down', 'helper must keep its own ordinary lazy body')
    require(gf['type_scope']==scope and gf['captures']=={cap['capture']:{'layout':imp['layout'],'relation':relation}} and
            gf['body']==[{'op':'retain','out':bodyapp['function'],'value':cap['capture']},zero,bodyapp,
                         {'op':'drop','value':bodyapp['function']},{'op':'drop','value':zero['out']},
                         {'op':'drop','value':cap['capture']},{'op':'drop','value':gf['parameter']},
                         {'op':'return','value':bodyapp['out']}] and bodyapp['argument']==zero['out'] and
            zero['kind']=='i64' and zero['value']==0 and zero['in']==bodyapp['in']=='$home', 'Instance body must call, not replace, the original helper')
    hb=p['codes'][bc['ir_code']]['body'];addition=source_allocation(plan,f['lp']+['body'],'prim2')
    literal=None
    if f['captured']:
        require(bbonus['relation']=='down' and bbonus['layout']==argcap['layout']==hcap['layout'] and
                hb==[{'op':'retain','out':hb[0]['out'],'value':bbonus['capture']},
                     {'op':'force','out':addition['left'],'value':hb[0]['out']},
                     {'op':'retain','out':hb[2]['out'],'value':bcap},{'op':'force','out':addition['right'],'value':hb[2]['out']},addition,
                     {'op':'drop','value':addition['right']},{'op':'drop','value':addition['left']},
                     {'op':'drop','value':bbonus['capture']},{'op':'drop','value':bcap},{'op':'return','value':addition['out']}],
                'helper body must retain and force original bonus and argument independently')
        bonus_carrier=carrier(['body','value'],'primitive');bb=p['codes'][bonus_carrier['ir_code']]['body']
        left,right=[source_allocation(plan,path,'scalar') for path,_ in f['bonus_args']]
        summed=source_allocation(plan,['body','value'],'prim2')
        require(bonus_carrier['type_scope'] is None and not bonus_carrier['mono_captures'] and not bonus_carrier['view_captures'] and
                bonus['code']==bonus_carrier['ir_code'] and not p['codes'][bonus['code']]['captures'], 'bonus must keep its own ordinary concrete Code')
        if grouped:
            require(bb[0]=={'op':'new_below','out':left['in'],'ceiling':'$home','imports':[]} and bb[1]==left and
                    bb[2]=={'op':'drop','value':left['in']} and
                    bb[4]=={'op':'new_below','out':right['in'],'ceiling':'$home','imports':[]} and bb[5]==right and
                    bb[6]=={'op':'drop','value':right['in']}, 'bonus literal placement scaffolding differs')
            bb=[bb[1],bb[3],bb[5]]+bb[7:]
        require(bb==[left,{'op':'force','out':summed['left'],'value':left['out']},right,
                     {'op':'force','out':summed['right'],'value':right['out']},summed,
                     {'op':'drop','value':summed['right']},{'op':'drop','value':summed['left']},{'op':'return','value':summed['out']}] and
                left['value']==20 and right['value']==1 and summed['primitive']=='addInt', 'original pending bonus expression differs')
    else:
        literal=source_allocation(plan,f['helper_args'][0][0],'scalar')
        if grouped:
            require(hb[0]=={'op':'new_below','out':literal['in'],'ceiling':'$home','imports':[]} and hb[1]==literal and
                    hb[2]=={'op':'drop','value':literal['in']}, 'ordinary helper literal placement scaffolding differs')
            hb=[hb[1]]+hb[3:]
        require(hb==[literal,{'op':'force','out':addition['left'],'value':literal['out']},
                     {'op':'retain','out':hb[2]['out'],'value':bcap},{'op':'force','out':addition['right'],'value':hb[2]['out']},addition,
                     {'op':'drop','value':addition['right']},{'op':'drop','value':addition['left']},
                     {'op':'drop','value':bcap},{'op':'return','value':addition['out']}] and literal['value']==21,
                'ordinary helper arithmetic graph differs')
    require(addition['primitive']=='addInt','helper must retain original primitive')
    checked=check_resources(p);d=json.loads(checked.derived_json);m=json.loads(check_metadata(p).metadata_json)
    require(plan['binding']['candidate_sha256']==m['ir_sha256'] and plan['binding']['input_sha256']==
            build.sha(json.dumps(f['replay']['input_annotated'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()),
            'planned input/program byte association differs')
    def site(path,role):
        row=one([x for x in mapping['allocation_map'] if x['source']==address(path) and x['role']==role], 'source allocation mapping')
        return one([x for x in m['sites'] if x['path']==row['instruction']], 'metadata allocation Site')
    hs=site(f['lp'],'closure');rs=site(f['cp'],'closure');scheme=one(m['schemes'],'one metadata Scheme')
    hcode=m['codes'][hs['code']];rcode=m['codes'][rs['code']]
    require(hs['context']=={'kind':'concrete'} and hs['scope'] is None and hcode['scope'] is None and
            hcode['callable_type']==hs['principal_type'] and hcode['expected_protocol']=='repeat' and
            hcode['expected_identity_flag']==0 and hcode['captures']==([{'name':hcap['capture'],'relation':'down','type':hcode['argument']}] if f['captured'] else []), 'helper own complete Code/type contract differs')
    he=one([x for x in m['site_executions'] if x['site']==hs['id']], 'own concrete SiteExecution')
    rep=m['representations'][he['representation']];typing=m['shape_typing'][rep['typing']];shape=m['shapes'][rep['shape']]
    contract=m['callable_contracts'][typing['contract']]
    execution=m['code_executions'][he['code_execution']]
    require(he['env']==0 and he['origin_kind']=='CONCRETE' and rep['ready_kind']=='function' and shape['kind']=='REPEAT' and
            shape['source']=={'kind':'legacy','reference':hs['legacy_physical']} and typing['scope'] is None and
            typing['type']==contract['type']==hs['principal_type'] and contract['protocol']=='repeat' and
            contract['result_identity']=='unknown' and contract['argument']==hcode['argument'] and contract['result']==hcode['result'] and
            execution['code']==hcode['id'] and execution['env']==0 and execution['callable_type']==hs['principal_type'],
            'helper must retain its own legacy physical representation with exact canonical callable contract')
    access=one([x for x in m['accesses'] if x['site']==hs['id']], 'own helper Access')
    require(access['mode']=='MONO' and access['origin_env']==access['use_env']==0 and access['type']==hs['principal_type'] and access['scheme'] is None,
            'helper Access must stay concrete E0')
    require(one([x for x in m['transports'] if x['source_access']==access['id'] and x['projection_env'] is None], 'identity helper transport')==
            {'id':one([x['id'] for x in m['transports'] if x['source_access']==access['id'] and x['projection_env'] is None], 'identity transport id'),
             'kind':'identity','projection_env':None,'source_access':access['id'],'result_access':access['id']}, 'helper identity transport changed')
    facts=one([x for x in d['instructions'] if x['path']==sm['generalize']], 'generalize acquisition facts');parent=one(facts['inputs'][1:],'parent import');child=one(facts['outputs'][1:],'child import')
    require(parent['role']==['imports',imp['import'],'value'] and child['role']==['imports',imp['import']] and
            parent['capability']!=child['capability'] and parent['storage']!=child['storage'] and
            all(parent[k]==child[k] for k in parent if k not in ('role','capability','storage')) and
            parent['mode']=='own' and parent['view']=='MONO' and parent['ready'] is True and not parent['ticket'] and
            parent['projection'] is None and parent['scheme'] is None and parent['type']==hs['principal_type'] and
            d['provenance'][parent['provenance']]['value']=={'kind':'allocated','site':hs['id'],'context':{'kind':'concrete'}},
            'helper import must retain all original facts and acquire only a fresh owner/storage')
    intro=one(d['introductions'],'one closed-entry proof');expected_proof={'policy':'instance-only-concrete-callable-imports/1',
        'root_site':rs['id'],'root_code':rcode['id'],'codes':[rcode['id']],'effects':[],
        'callable_imports':[{'binding':imp['import'],'input':1,'output':1,'site':hs['id'],'code':hcode['id'],'type':hs['principal_type']}]}
    require(intro['closed_entry']==expected_proof and intro['result_sites']==[rs['id']] and
            [x['id'] for x in m['codes'] if x['scope']==scheme['id']]==[rcode['id']], 'callable import must trigger closed entry even with no scalar effects')
    obligation=one([x for x in d['obligations'] if x['kind']=='publish' and x['host_site']==rs['id'] and
                    x['role']==['captures',cap['capture']]], 'fresh imported capture support obligation')
    require(('strict_below' in obligation['rules'])==strict and 'down_support' in obligation['rules'],
            'actual capture relation must be freshly proved')
    uses=[]
    for j,((path,call),typ) in enumerate(zip(f['calls'],[BOOL,INT])):
        src=poly['uses'][j];row=mapping['use_map'][j];atom='#bool' if typ==BOOL else '#i64'
        require(src['arguments']==[typ] and src['instantiated_type']=={'tag':'arrow','from':typ,'to':INT} and
                src['source']==row['source']==address(path+['function']) and row['definition']==0 and row['use']==j and
                [p['types'][x]['layout'] for x in row['arguments']]==[atom], 'complete source use vector differs')
        witness=one([x for x in poly['type_applications'] if x['id'] in src['type_applications']], 'complete original type witness')
        require(witness['witness']==call['function']['witness'] and witness['result_type']==src['instantiated_type'] and witness['disposition']=='shared_use',
                'ordinary proof or dead coordinate was lost')
        tid=one([x['id'] for x in m['types'] if x['tag']=='closed' and x['atom']==atom], 'intrinsic coordinate')
        use=one([x for x in m['uses'] if x['arguments']==[tid]], 'full-vector metadata Use');uses.append(use)
        env=m['environments'][use['env']]
        require(env['mode']=='CLOSED' and env['scheme']==scheme['id'] and env['arguments']==[tid], 'complete closed Env differs')
        view=row['source_view'];host=one([x for x in carriers if x['carrier']==view['carrier']], 'source view host')
        vc=one([x for x in host['view_captures'] if x['capture']==view['capture']], 'source full view')
        retain=instruction(p,one(row['creation'],'call retain'));callop=source_allocation(plan,path,'application')
        require(vc['binder']==sm['binder'] and vc['arguments']==row['arguments'] and
                retain=={'op':'retain','out':callop['function'],'value':vc['capture']}, 'source call lost its actual full captured view')
    for vc in outer['view_captures']:
        ops=[instruction(p,x) for x in vc['creation']]
        require(vc['source_view']=={'kind':'scheme','definition':0} and len(ops)==4 and
                ops[0]=={'op':'retain','out':ops[0]['out'],'value':g['out']} and ops[1]['op']=='instantiate' and
                ops[1]['value']==ops[0]['out'] and p['instantiations'][ops[1]['instantiation']]['arguments']==vc['arguments'] and
                ops[2]['op']=='thunk' and ops[2]['code']==outer['ir_code'] and ops[2]['captures'][vc['capture']]==ops[1]['out'] and
                ops[3]=={'op':'drop','value':ops[1]['out']}, 'view creation/lifetime differs')
    require(emit_runtime(p).runtime_source==generated, 'fresh generated runtime differs')
    entry=generated.split('static void rt8_entry(Rt8Context *ctx)',1)[1].split('\n}\n',1)[0]
    begin=entry.index('rt8_generic_begin(');alloc=entry.index('rt8_closure(',begin);seal=entry.index('rt8_generic_seal(',alloc)
    alias,original=one(re.findall(r'(h\d+) = rt8_retain\(ctx, (h\d+)\);',entry[begin:alloc]), 'one post-begin imported alias')
    require(re.search(r'\w+\[\d+\] = '+alias+r';',entry[begin:alloc]) and
            alloc<entry.index('rt8_drop(ctx, '+alias+');',alloc)<seal<entry.index('rt8_drop(ctx, '+original+');',seal),
            'import alias must be captured then discharged before seal; parent later')
    info=dict(facts=f,program=p,mapping=mapping,derived=d,meta=m,proof=expected_proof,scheme=scheme,helper_site=hs,root_site=rs,
              helper_code=hcode,root_code=rcode,helper_access=access,helper_representation=rep,root_capture=cap['capture'],
              helper_body_capture=bcap,helper_scalar_capture=hcap,helper_body_bonus=bbonus,parent_import=parent,child_import=child,uses=uses,
              inner_site=site(f['cp']+['body'],'application'),zero_site=site(f['cp']+['body','argument'],'scalar'),
              helper_body_site=site(f['lp']+['body'],'thunk'),helper_literal_site=site(f['helper_args'][0][0],'scalar') if not f['captured'] else None,
              helper_result_site=site(f['lp']+['body'],'prim2'),outer_site=site(f['kp']+['body'],'thunk'),
              outer_result_site=site(f['kp']+['body'],'prim2'),call_sites=[site(path,'application') for path,_ in f['calls']])
    if f['captured']:
        info.update(bonus_site=site(['body','value'],'thunk'),bonus_result_site=site(['body','value'],'prim2'),
                    bonus_literal_sites=[site(path,'scalar') for path,_ in f['bonus_args']])
        require(all(m['sites'][x['site']]['scope'] is None and x['env']==0 for x in m['site_executions']
                    if x['site'] in {info['bonus_site']['id'],info['bonus_result_site']['id'],*[z['id'] for z in info['bonus_literal_sites']]}),
                'helper-owned bonus graph must retain its own concrete E0 identity')
    closed_entry_contract(info)
    return info


def closed_entry_contract(info):
    d=info['derived'];m=info['meta'];proof=info['proof']
    require(one(d['introductions'],'single introduction')['closed_entry']==proof and
            one([x for x in m['coverage'] if x['source']['kind']=='closed-entry'],'complete proof coverage')['source']['proof']==proof,
            'resource and independently rederived metadata closed-entry proof differ')
    neutral=one([x['id'] for x in m['code_executions'] if x['code']==info['root_code']['id'] and
                 x['env']==info['scheme']['neutral_env']], 'neutral construction typing must remain')
    for row in m['boundaries']:
        key=row['key']
        if key['kind'] in ('entry','return'):
            require(key['code_execution']!=neutral, 'neutral callable-import invocation was advertised')
        if key['kind'] in ('slot','deferred'):
            sx=m['site_executions'][key['site_execution']]
            if m['sites'][sx['site']]['context']['kind']=='execution':
                require(sx['env']!=info['scheme']['neutral_env'], 'neutral scoped execution coverage was invented')


def observe(e,info):
    closed_entry_contract(info)
    m=info['meta'];p=info['program'];events=e['events'];captured=info['facts']['captured']
    require(e['schema']=='resource-ir-v8-run/1' and e['state']==e['fault']==0 and e['graph_executed']==1 and
            e['result']=={'kind':'i64','value':42} and e['scalar_result_kind']==1 and e['scalar_result']==42 and
            e['events_omitted']==0 and e['events_emitted']==len(events), 'complete healthy actual Int42 report required')
    require(e['guards_failed_mask']==0 and e['guards_checked_mask']==(((1<<27)-1)&~(1<<24)&~(1<<4)) and
            0<e['guard_work_used']==e['guard_work_total']<=e['guard_work_limit']==67108864, 'guard coverage/work differs')
    ledger(e,True)
    select=lambda name:[(i,x) for i,x in enumerate(events) if x['event']==name]
    allocations=select('allocate');nodes={x['node']:x for _,x in allocations};frames={x['frame']:(i,x) for i,x in select('frame_enter')}
    require(len(nodes)==len(allocations) and len(frames)==len(select('frame_enter')), 'unique physical nodes/activation frames required')
    twice={info[k]['id'] for k in ('inner_site','zero_site','helper_body_site','helper_result_site')}
    if not captured:twice.add(info['helper_literal_site']['id'])
    require(Counter(x['site_id'] for _,x in allocations)==Counter({s['id']:2 if s['id'] in twice else 1 for s in m['sites']}),
            'complete source allocation-site execution census differs')
    by_site=lambda site:[(i,x) for i,x in allocations if x['site_id']==site['id']]
    scalar=lambda node:one([(i,x) for i,x in select('scalar_value') if x['node']==node], 'one actual scalar event')
    memo=lambda node:one([(i,x) for i,x in select('memo_publish') if x['destination']==node], 'one actual memo publication')
    raw=lambda node:one([(i,x) for i,x in select('raw_return') if x['source']==node], 'one raw callback return')
    frame_for=lambda node,kind:one([(i,x) for i,x in select('frame_enter') if x['context'].get('node')==node and x['context']['kind']==kind], 'one exact callback frame')
    for i,x in allocations:
        site=m['sites'][x['site_id']];op=instruction(p,site['path']);fi,fr=frames[x['frame']]
        sx=one([z for z in m['site_executions'] if z['site']==site['id'] and z['env']==x['env_id']], 'actual own SiteExecution')
        require(fi<i and fr['context']['kind']==site['path']['root'] and fr['context'].get('name')==site['path']['name'] and
                x['out']==op['out'] and x['opcode']==op['op'] and x['state']=={
                    'scalar':'READY','prim2':'READY','closure':'CLOSURE','thunk':'THUNK','application':'APPLICATION'}[op['op']] and
                x['shape_id']==m['representations'][sx['representation']]['shape'] and
                x['code']==(m['codes'][site['code']]['name'] if site['code'] is not None else None),
                'actual allocation must use its exact instruction/Code/Env/own representation')
        if op['op'] in ('scalar','prim2'):
            vi,v=scalar(x['node'])
            require(i<vi and v['opcode']==op['op'] and v['primitive']==op.get('primitive'), 'scalar event must name its allocating operation')
            if op['op']=='scalar':require(v['kind']==op['kind'] and type(v['value']) is type(op['value']) and v['value']==op['value'], 'source literal changed')
    for _,fr in frames.values():
        c=fr['context']
        if c['kind']!='entry':
            node=nodes[c['node']]
            require(c['name']==node['code'] and fr['parent_frame'] in frames, 'callback must use the actual node own Code')
            if c['kind']=='thunk':require(c['home_group']==node['group'], 'thunk callback must use its own node home')
    hi,h=one(by_site(info['helper_site']),'one whole concrete helper');ki,k=one(by_site(info['root_site']),'one shared generic root')
    oi,outer=one(by_site(info['outer_site']),'one original outer carrier');cap=info['root_capture']
    bonus_pair=one(by_site(info['bonus_site']),'one helper-owned pending bonus') if captured else None
    bonus=bonus_pair[1] if captured else None
    require(h['env_id']==0 and h['slots']==({info['helper_scalar_capture']['capture']:bonus['node']} if captured else {}) and h['layout']==info['helper_site']['legacy_physical'] and
            h['shape_id']==info['helper_representation']['shape'] and k['env_id']==info['scheme']['neutral_env'] and
            k['slots']=={cap:h['node']} and k['type_id']==info['root_site']['principal_type'] and k['scheme_id']==info['scheme']['id'],
            'helper own E0 representation or whole generic capture changed')
    gi,begin=one(select('generic_begin'),'one begin');si,seal=one(select('generic_seal'),'one seal')
    require(hi<gi<ki<si<oi and begin['scheme']==info['scheme']['id'] and begin['intro']==seal['intro']==info['scheme']['intro'] and
            begin['capsule']==seal['capsule']>0 and 0<begin['authority']<=begin['watermark'] and
            begin['frame']==seal['frame']==k['frame'] and seal['node']==k['node'] and seal['owner']>begin['watermark'], 'direct generic lifetime/seal changed')
    old=m['accesses'][seal['old_access']];sealed=m['accesses'][seal['new_access']]
    require(old['site']==sealed['site']==info['root_site']['id'] and old['mode']=='MONO' and old['scheme'] is None and
            old['origin_env']==old['use_env']==sealed['origin_env']==k['env_id'] and old['type']==info['root_site']['principal_type'] and
            sealed['mode']=='SCHEME' and sealed['scheme']==info['scheme']['id'], 'neutral-to-Scheme Access changed')
    pi,pub=one([(i,x) for i,x in select('slot_install') if x['host']==k['node'] and x['field']==cap],'whole helper publication')
    require(gi<pi<ki and pub['target']==h['node'] and pub['target_group']==h['group'] and pub['target_state']=='CLOSURE' and
            pub['reason']=='publication', 'intro must publish original ready helper without executing it')
    inst=select('instantiate')
    require(len(inst)==2 and len({x['owner'] for _,x in inst})==2 and {x['use'] for _,x in inst}=={u['id'] for u in info['uses']}, 'two distinct full views required')
    for i,x in inst:
        use=one([u for u in info['uses'] if u['id']==x['use']], 'actual full-vector use');a=m['accesses'][x['new_access']]
        require(si<i<oi and x['owner']>begin['watermark'] and x['owner']!=seal['owner'] and x['mode']=='own' and x['anchor'] is None and
                x['node']==k['node'] and x['scheme']==info['scheme']['id'] and x['old_access']==seal['new_access'] and
                a['mode']=='MONO' and a['site']==info['root_site']['id'] and a['origin_env']==k['env_id'] and
                a['use_env']==use['env'] and a['type']==use['result_type'], 'shared node full-vector Access differs')
    require(outer['env_id']==0 and set(outer['slots'].values())=={k['node']} and len(outer['slots'])==2, 'outer carrier must retain both full views')
    ofi,of=frame_for(outer['node'],'thunk')
    allcalls=select('invoke_enter');allreturns=select('invoke_raw_return')
    require([x['closure'] for _,x in allcalls]==[k['node'],h['node'],k['node'],h['node']] and
            [x['closure'] for _,x in allreturns]==[k['node'],h['node'],k['node'],h['node']], 'two distinct helper calls must follow two generic calls')
    kc=allcalls[::2];hc=allcalls[1::2];kr=allreturns[::2];hr=allreturns[1::2]
    kframes=[x for x in select('frame_enter') if x[1]['context'].get('node')==k['node']]
    hframes=[x for x in select('frame_enter') if x[1]['context'].get('node')==h['node']]
    kh=[x for x in select('closure_capture_handoff') if x[1]['node']==k['node']]
    hh=[x for x in select('closure_capture_handoff') if x[1]['node']==h['node']]
    inner=by_site(info['inner_site']);zero=by_site(info['zero_site']);pending=by_site(info['helper_body_site'])
    results=by_site(info['helper_result_site']);literals=by_site(info['helper_literal_site']) if not captured else []
    require(all(len(xs)==2 for xs in (kframes,hframes,kh,hh,inner,zero,pending,results)) and (captured or len(literals)==2), 'exact two-call carrier census differs')
    owners=[];completed=[];pending_nodes=[];outer_apps=[];bonus_owners=[]
    if captured:
        bi,bonus=bonus_pair;bri,bonus_result=one(by_site(info['bonus_result_site']),'one actual bonus result')
        bvi,bv=scalar(bonus_result['node']);bci,bonus_callback=one([(i,x) for i,x in select('callback_enter') if x['node']==bonus['node']], 'bonus must execute only once')
        bfi0,bonus_frame=frame_for(bonus['node'],'thunk');brawi,braw=raw(bonus['node']);bmi,bm=memo(bonus['node'])
        bpi,bpin=one([(i,x) for i,x in select('update_pin') if x['node']==bonus['node']], 'one bonus update pin')
        bli=[one(by_site(x),'one original bonus literal') for x in info['bonus_literal_sites']]
        bforces=[(i,x) for i,x in select('ir_force_result') if x['frame']==bonus_frame['frame']]
        rawbf=[x for x in p['codes'][bonus_frame['context']['name']]['body'] if x['op']=='force']
        require(bi<hi<si<bpi<bci<bfi0<bli[0][0]<bli[1][0]<bri<bvi<brawi<bmi and
                bonus['env_id']==bonus_result['env_id']==0 and not bonus['slots'] and bonus['state']=='THUNK' and
                bonus_result['frame']==bonus_frame['frame'] and bonus_frame['context']['name']==bonus['code'] and
                all(x['frame']==bonus_frame['frame'] and x['env_id']==0 for _,x in bli) and
                bv['kind']=='i64' and type(bv['value']) is int and bv['value']==21 and bv['primitive']=='addInt' and
                braw['result']==bm['result']==bonus_result['node'] and braw['result_state']=='READY' and
                bpin['pin']==bonus_callback['pin']==braw['home_pin']==bm['pin'] and
                len(bforces)==len(rawbf)==2 and [x['result'] for _,x in bforces]==[x['node'] for _,x in bli] and
                all(x['out']==op['out'] and x['source_variable']==op['value'] and i<bri for (i,x),op in zip(bforces,rawbf)),
                'helper-owned pending bonus must execute exact addInt20 1 once through its own E0 Code and memo')
        bsi,bs=one([(i,x) for i,x in select('slot_install') if x['host']==h['node']], 'whole helper original bonus slot')
        bdi,bd=one([(i,x) for i,x in select('slot_remove') if x['host']==h['node']], 'whole helper bonus retirement')
        require(bi<bsi<hi and bs['field']==bd['field']==info['helper_scalar_capture']['capture'] and
                bs['target']==bd['target']==bonus['node'] and bs['target_group']==bd['target_group']==bonus['group'] and
                bs['target_state']=='THUNK' and bd['target_state']=='MEMO' and bs['reason']=='publication' and bd['reason']=='group_close',
                'whole helper must retain original pending bonus slot through memoization, not flatten or replace it')
        btsi,bts=one([(i,x) for i,x in select('slot_install') if x['host']==bonus['node'] and x['field']=='$target'], 'one bonus memo target slot')
        btdi,btd=one([(i,x) for i,x in select('slot_remove') if x['host']==bonus['node'] and x['field']=='$target'], 'bonus memo target retirement')
        require(brawi<btsi<bmi<btdi and bts['target']==btd['target']==bonus_result['node'] and
                bts['target_state']==btd['target_state']=='READY' and bts['reason']=='publication' and btd['reason']=='group_close',
                'actual shared bonus memo must preserve its original ready result')
    def slot_pair(host,field,target,before,after,state=None):
        ai,a=one([(i,x) for i,x in select('slot_install') if x['host']==host and x['field']==field],'original slot publication')
        di,d=one([(i,x) for i,x in select('slot_remove') if x['host']==host and x['field']==field],'original slot clearing')
        require(before<ai<after<di and a['target']==d['target']==target and a['target_group']==d['target_group']==nodes[target]['group'] and
                a['target_state']==d['target_state']==(state if state is not None else nodes[target]['state']) and a['reason']=='publication' and d['reason']=='payload_clear',
                'application/capture slot identity, readiness or lifetime differs')
        return di
    for j,use in enumerate(info['uses']):
        ici,ic=kc[j];iri,ir=kr[j];fci,fc=hc[j];fri,fr=hr[j];kfi,kf=kframes[j];hfi,hf=hframes[j]
        khi,hand=kh[j];hhi,hhand=hh[j];ai,app=inner[j];zi,z=zero[j];ti,t=pending[j];ri,result=results[j]
        if not captured:li,literal=literals[j]
        cai,callapp=one(by_site(info['call_sites'][j]),'actual source application');outer_apps.append(callapp['node'])
        _,arg=scalar(ic['argument']);wanted=info['facts']['calls'][j][1]['argument']
        require(arg['kind']==('bool' if wanted['tag']=='bool' else 'i64') and type(arg['value']) is type(wanted['value']) and arg['value']==wanted['value'] and
                callapp['slots']=={'$function':k['node'],'$argument':ic['argument']} and callapp['env_id']==0 and callapp['frame']==of['frame'], 'source call/argument graph differs')
        require(cai<khi<ici<kfi<zi<ai<iri<hhi<fci<hfi<ti<fri and ic['protocol']==fc['protocol']==hand['protocol']==hhand['protocol']=='repeat' and
                hand['owners'].keys()=={cap} and hhand['owners'].keys()==({info['helper_scalar_capture']['capture']} if captured else set()) and
                ic['closure_group']==k['group'] and fc['closure_group']==h['group'] and
                ic['home']==ir['home']==kf['context']['home_group']==callapp['group'] and
                fc['home']==fr['home']==hf['context']['home_group']==app['group'] and
                ir['argument']==ic['argument'] and ir['result']==app['node'] and fr['argument']==fc['argument']==z['node'] and fr['result']==t['node'] and
                ir['token'] is None and fr['token'] is None, 'exact shared/helper invocation and returned pending graphs differ')
        require(kf['context']['name']==info['root_code']['name'] and hf['context']['name']==info['helper_code']['name'] and
                app['frame']==z['frame']==kf['frame'] and app['env_id']==z['env_id']==use['env'] and
                app['slots']=={'$function':h['node'],'$argument':z['node']} and app['group']==z['group']==ic['home'] and
                t['frame']==hf['frame'] and t['env_id']==0 and t['group']==fc['home'] and
                t['slots']==({info['helper_body_capture']:z['node'],info['helper_body_bonus']['capture']:bonus['node']} if captured else {info['helper_body_capture']:z['node']}), 'Instance application must invoke helper own E0 Code, preserving the argument node')
        for field,target in app['slots'].items():require(slot_pair(app['node'],field,target,kfi,ai)<fci,'helper application slots must clear before call')
        ahi,ah=one([(i,x) for i,x in select('capture_handoff') if x['node']==app['node']], 'inner application acquired owners')
        require(iri<ahi<fci and set(ah['owners'])=={'$function','$argument'}, 'inner application handoff differs')
        freturn=one([x for i,x in select('force_return') if ahi<i<fci and x['result']==h['node']], 'own helper force result')
        require(freturn['owner']==ah['owners']['$function'] and freturn['group']==h['group'] and freturn['layout']==h['layout'], 'helper owner/own representation lost during ordinary forcing')
        owners.extend([hand['owners'][cap],ah['owners']['$function']])
        cbi,cb=one([(i,x) for i,x in select('callback_enter') if x['node']==t['node']], 'one helper computation callback');bfi,bf=frame_for(t['node'],'thunk')
        rbi,rb=raw(t['node']);mi,mm=memo(t['node']);ami,am=memo(app['node']);cmi,cm=memo(callapp['node'])
        vi,value=scalar(result['node'])
        require(fri<cbi<bfi<ri<vi<rbi<cmi<ami<mi and result['env_id']==0 and
                result['frame']==bf['frame'] and rb['result_state']=='READY' and
                rb['result']==mm['result']==am['result']==cm['result']==result['node'] and
                value['kind']=='i64' and type(value['value']) is int and value['value']==21 and value['primitive']=='addInt',
                'each helper call must compute its own ready21 through its own concrete body')
        if captured:
            require(slot_pair(t['node'],info['helper_body_bonus']['capture'],bonus['node'],hfi,ti,'THUNK' if j==0 else 'MEMO')<cbi,
                    'each helper body must acquire original bonus slot, preserving its pending or memo state')
            thi,th=one([(i,x) for i,x in select('capture_handoff') if x['node']==t['node']], 'exact helper-body captured owners')
            require(fri<thi<cbi and set(th['owners'])=={info['helper_body_capture'],info['helper_body_bonus']['capture']},
                    'helper body must acquire separate bonus and argument owners')
            bonus_owners.extend([hhand['owners'][info['helper_scalar_capture']['capture']],th['owners'][info['helper_body_bonus']['capture']]])
            if j==0:require(bfi<bci<bmi<ri and bonus_frame['parent_frame']==bf['frame'], 'bonus must first execute inside first helper body, not before demand')
            else:require(bmi<fci and bdi>mi, 'second helper must reuse completed bonus while helper capture remains live')
        else:
            _,lv=scalar(literal['node'])
            require(bfi<li<ri and literal['env_id']==0 and literal['frame']==bf['frame'] and lv['kind']=='i64' and lv['value']==21,
                    'each direct helper must allocate original literal21 in its own body')
        require(slot_pair(t['node'],info['helper_body_capture'],z['node'],hfi,ti)<cbi,'helper argument capture must survive until callback handoff')
        forces=[(i,x) for i,x in select('ir_force_result') if x['frame']==bf['frame']]
        rawforces=[x for x in p['codes'][bf['context']['name']]['body'] if x['op']=='force']
        require(len(forces)==len(rawforces)==2 and all(x['out']==op['out'] and x['source_variable']==op['value'] for (_,x),op in zip(forces,rawforces)) and
                [x['result'] for _,x in forces]==[bonus_result['node'] if captured else literal['node'],z['node']] and all(i<ri for i,_ in forces), 'helper arithmetic must force exact original operands')
        if captured:
            cursor=bfi
            for (fi,force),target in zip(forces,[bonus['node'],z['node']]):
                entrances=[(i,x) for i,x in select('force_enter') if cursor<i<fi]
                require(entrances and entrances[0][1]['cursor']==target, 'helper source force must demand its actual captured node')
                returned=one([x for i,x in select('force_return') if entrances[0][0]<i<fi and x['depth']==entrances[0][1]['depth']], 'exact helper operand force return')
                require(returned['result']==force['result'] and returned['owner']==force['owner'] and returned['group']==force['group'] and returned['layout']==force['layout'],
                        'helper force result must correspond to actual return owner and representation')
                cursor=fi
            if j==1:require(btdi>forces[0][0], 'bonus memo must survive second operand demand')
        for dest in (callapp['node'],app['node'],t['node']):
            pi,pin=one([(i,x) for i,x in select('update_pin') if x['node']==dest], 'one pending update pin')
            mindex,mrow=memo(dest);require(pi<mindex and pin['pin']==mrow['pin'],'pending memo must match its actual update pin')
        pending_nodes.extend([callapp['node'],app['node'],t['node']]);completed.append(result['node'])
        if j==0:require(mi<kc[1][0],'first full computation must finish before the second source demand')
    if captured:require(len([1 for _,x in select('force_enter') if x['cursor']==bonus['node']])==2,'exactly two demands of one original bonus node required')
    if captured:require(len(bonus_owners)==len(set(bonus_owners))==4 and not set(bonus_owners)&set(owners) and all(x>begin['watermark'] for x in bonus_owners), 'whole-helper and body bonus owners must be separate acquired aliases')
    require(len(set(owners))==4 and all(x>begin['watermark'] for x in owners) and len(set(completed))==2,
            'helper owner aliases and per-call results must remain distinct')
    finali,final=one(by_site(info['outer_result_site']),'actual outer addition');fvi,fv=scalar(final['node']);ori,orr=raw(outer['node']);omi,om=memo(outer['node'])
    outerforces=[x for _,x in select('ir_force_result') if x['frame']==of['frame']]
    rawforces=[x for x in p['codes'][of['context']['name']]['body'] if x['op']=='force']
    require(len(outerforces)==len(rawforces)==2 and [x['result'] for x in outerforces]==completed and
            all(x['out']==op['out'] and x['source_variable']==op['value'] for x,op in zip(outerforces,rawforces)) and
            final['env_id']==0 and final['frame']==of['frame'] and finali<fvi<ori<omi and
            fv['value']==42 and type(fv['value']) is int and fv['primitive']=='addInt' and
            orr['result']==om['result']==final['node'] and orr['result_state']=='READY', 'actual outer addition must consume both distinct helper results')
    di,drop=one([(i,x) for i,x in select('slot_remove') if x['host']==k['node'] and x['field']==cap],'shared helper retirement')
    require(mi<di and drop['target']==h['node'] and drop['target_state']=='CLOSURE' and drop['reason']=='group_close', 'whole helper must survive both uses without becoming a memo')
    require(not any(x['destination'] in (h['node'],k['node']) for _,x in select('memo_publish')) and
            not any(x.get('node') in (h['node'],k['node']) for _,x in select('update_pin')+select('payload_cleared')) and
            all(i>si for i,_ in select('invoke_enter')), 'helper/root was memoized, cleared or executed during introduction')
    expected_callbacks={outer['node'],*[x['node'] for _,x in pending]};expected_memos=set(pending_nodes+[outer['node']])
    if captured:expected_callbacks.add(bonus['node']);expected_memos.add(bonus['node'])
    require({x['node'] for _,x in select('callback_enter')}==expected_callbacks and len(select('callback_enter'))==3+int(captured) and
            {x['destination'] for _,x in select('memo_publish')}==expected_memos, 'unexpected callback or memo graph')
    metrics=e['metrics']
    require(metrics['ordinary_calls']==len(allcalls)==4 and metrics['callback_calls']==3+int(captured) and metrics['memo_writes']==len(select('memo_publish'))==7+int(captured) and
            metrics['memo_fast_paths']==int(captured) and metrics['applications_allocated']==len(outer_apps)+len(inner)==4 and
            metrics['nodes_allocated']==metrics['nodes_freed']==len(allocations) and
            metrics['groups_allocated']==metrics['groups_closed']==len(select('close_group')), 'actual invocation/allocation/memo census differs')
    return {'status':'passed','helper_node':h['node'],'shared_node':k['node'],'helper_code':info['helper_code']['name'],
            'root_code':info['root_code']['name'],'helper_shape':h['shape_id'],'helper_access_metadata':info['helper_access']['id'],
            'closed_use_vectors':[x['arguments'] for x in info['uses']],'inner_applications':[x['node'] for _,x in inner],
            'helper_body_nodes':[x['node'] for _,x in pending],'helper_result_nodes':completed,'capture_owners':owners,
            'bonus_node':bonus['node'] if captured else None,'bonus_result_node':bonus_result['node'] if captured else None,'bonus_owners':bonus_owners,
            'normalization_steps':0,'events':len(events),'work':e['guard_work_used'],'guard_mask':e['guards_checked_mask'],
            'closed_entry':info['proof'],'access_scope':ACCESS_SCOPE}


def copied_controls(evaluation,info):
    actual=observe(evaluation,info);rows=[];helper=actual['helper_node'];root=actual['shared_node']
    inner=actual['inner_applications'][0];body=actual['helper_body_nodes'][0];result=actual['helper_result_nodes'][0]
    def event(r,name,predicate=lambda x:True):return next(x for x in r['events'] if x['event']==name and predicate(x))
    def reject(name,change):
        r=copy.deepcopy(evaluation);change(r)
        try:observe(r,info)
        except (AssertionError,KeyError,ValueError,IndexError):rows.append({'control':name,'status':'rejected'})
        else:raise AssertionError('copied callable report accepted: '+name)
    reject('wrong-result',lambda r:r['result'].__setitem__('value',41))
    reject('omitted-events',lambda r:r.__setitem__('events_omitted',1))
    reject('invented-project-coverage',lambda r:r.__setitem__('guards_checked_mask',r['guards_checked_mask']|(1<<4)))
    reject('live-ledger',lambda r:r['memory'].__setitem__('live_bytes',1))
    reject('helper-retagged-generic',lambda r:event(r,'allocate',lambda x:x['node']==helper).__setitem__('env_id',info['scheme']['neutral_env']))
    reject('helper-not-ready-closure',lambda r:event(r,'allocate',lambda x:x['node']==helper).__setitem__('state','APPLICATION'))
    canonical=one([x['id'] for x in info['meta']['shapes'] if x['source']=={'kind':'canonical-arrow','type':info['helper_site']['principal_type']}], 'canonical helper shape')
    reject('helper-replaced-by-canonical-shape',lambda r:event(r,'allocate',lambda x:x['node']==helper).__setitem__('shape_id',canonical))
    reject('helper-wrong-code',lambda r:event(r,'allocate',lambda x:x['node']==helper).__setitem__('code',info['root_code']['name']))
    reject('root-wrong-principal',lambda r:event(r,'allocate',lambda x:x['node']==root).__setitem__('type_id',info['helper_site']['principal_type']))
    reject('root-wrong-scheme',lambda r:event(r,'allocate',lambda x:x['node']==root).__setitem__('scheme_id',999999))
    reject('whole-helper-capture-replaced',lambda r:event(r,'allocate',lambda x:x['node']==root)['slots'].__setitem__(info['root_capture'],root))
    reject('helper-publication-pending',lambda r:event(r,'slot_install',lambda x:x['host']==root).__setitem__('target_state','THUNK'))
    reject('invalid-seal-access',lambda r:event(r,'generic_seal').__setitem__('old_access',len(info['meta']['accesses'])))
    reject('invalid-authority-owner',lambda r:event(r,'generic_begin').__setitem__('authority',event(r,'generic_begin')['watermark']+1))
    reject('pre-watermark-seal',lambda r:event(r,'generic_seal').__setitem__('owner',event(r,'generic_begin')['watermark']))
    def reuse_view(r):
        xs=[x for x in r['events'] if x['event']=='instantiate'];xs[1]['owner']=xs[0]['owner']
    reject('reused-view-owner',reuse_view)
    reject('anchored-owned-view',lambda r:event(r,'instantiate').__setitem__('anchor',1))
    reject('wrong-view-access',lambda r:event(r,'instantiate').__setitem__('new_access',event(r,'generic_seal')['old_access']))
    reject('concrete-instance-application',lambda r:event(r,'allocate',lambda x:x['node']==inner).__setitem__('env_id',0))
    reject('crossed-instance-application',lambda r:event(r,'allocate',lambda x:x['node']==inner).__setitem__('env_id',info['uses'][1]['env']))
    reject('application-function-cloned',lambda r:event(r,'allocate',lambda x:x['node']==inner)['slots'].__setitem__('$function',root))
    reject('helper-invoked-as-generic-code',lambda r:event(r,'frame_enter',lambda x:x['context'].get('node')==helper)['context'].__setitem__('name',info['root_code']['name']))
    reject('wrong-helper-invocation-home',lambda r:event(r,'invoke_enter',lambda x:x['closure']==helper).__setitem__('home',999999))
    reject('helper-body-rebranded-instance',lambda r:event(r,'allocate',lambda x:x['node']==body).__setitem__('env_id',info['uses'][0]['env']))
    reject('wrong-helper-argument',lambda r:event(r,'invoke_enter',lambda x:x['closure']==helper).__setitem__('argument',result))
    reject('eager-helper-return',lambda r:event(r,'invoke_raw_return',lambda x:x['closure']==helper).__setitem__('result',result))
    reject('wrong-helper-force-owner',lambda r:event(r,'force_return',lambda x:x['result']==helper).__setitem__('owner',999999))
    reject('wrong-helper-force-layout',lambda r:event(r,'force_return',lambda x:x['result']==helper).__setitem__('layout',None))
    reject('helper-result-not-ready',lambda r:event(r,'allocate',lambda x:x['node']==result).__setitem__('state','THUNK'))
    reject('wrong-allocation-output',lambda r:event(r,'allocate',lambda x:x['node']==result).__setitem__('out','missing'))
    reject('wrong-helper-value',lambda r:event(r,'scalar_value',lambda x:x['node']==result).__setitem__('value',42))
    reject('lost-force-operand-label',lambda r:event(r,'ir_force_result').__setitem__('source_variable','missing'))
    reject('lost-force-result-label',lambda r:event(r,'ir_force_result').__setitem__('out','missing'))
    def reused_capture(r):
        xs=[x for x in r['events'] if x['event']=='closure_capture_handoff' and x['node']==root]
        xs[1]['owners']=copy.deepcopy(xs[0]['owners'])
    reject('reused-import-capture-owner',reused_capture)
    reject('early-whole-helper-release',lambda r:event(r,'slot_remove',lambda x:x['host']==root).__setitem__('reason','payload_clear'))
    second=actual['helper_result_nodes'][1]
    reject('collapsed-helper-results',lambda r:event(r,'raw_return',lambda x:x['result']==second).__setitem__('result',result))
    def memo_helper(r):
        r['events'].append({'event':'memo_publish','destination':helper,'result':result,'pin':1,'depth':1,'internal':True});r['events_emitted']=len(r['events'])
    reject('memoized-helper-closure',memo_helper)
    def early_call(r):
        row=event(r,'invoke_enter',lambda x:x['closure']==helper);r['events'].remove(row);r['events'].insert(0,row)
    reject('helper-executed-during-introduction',early_call)
    reject('single-helper-call-census',lambda r:r['metrics'].__setitem__('ordinary_calls',3))
    reject('invented-helper-memo-reuse',lambda r:r['metrics'].__setitem__('memo_fast_paths',2 if info['facts']['captured'] else 1))
    if info['facts']['captured']:
        bonus=actual['bonus_node'];bonus_result=actual['bonus_result_node'];hcap=info['helper_scalar_capture']['capture'];bcap=info['helper_body_bonus']['capture']
        reject('lost-helper-owned-capture',lambda r:event(r,'allocate',lambda x:x['node']==helper)['slots'].clear())
        reject('flattened-bonus-into-generic-root',lambda r:event(r,'allocate',lambda x:x['node']==root)['slots'].__setitem__('invented',bonus))
        reject('eager-bonus-allocation',lambda r:event(r,'allocate',lambda x:x['node']==bonus).__setitem__('state','READY'))
        reject('bonus-rebranded-instance',lambda r:event(r,'allocate',lambda x:x['node']==bonus_result).__setitem__('env_id',info['uses'][0]['env']))
        reject('wrong-bonus-computation',lambda r:event(r,'scalar_value',lambda x:x['node']==bonus_result).__setitem__('value',22))
        reject('wrong-bonus-memo-target',lambda r:event(r,'slot_install',lambda x:x['host']==bonus and x['field']=='$target').__setitem__('target',result))
        reject('wrong-body-bonus-node',lambda r:event(r,'allocate',lambda x:x['node']==body)['slots'].__setitem__(bcap,result))
        second_body=actual['helper_body_nodes'][1]
        reject('second-bonus-slot-not-memo',lambda r:event(r,'slot_install',lambda x:x['host']==second_body and x['field']==bcap).__setitem__('target_state','THUNK'))
        def lost_reuse(r):
            frame=event(r,'frame_enter',lambda x:x['context'].get('node')==second_body)['frame']
            event(r,'ir_force_result',lambda x:x['frame']==frame).__setitem__('result',result)
        reject('second-helper-lost-bonus-reuse',lost_reuse)
        reject('wrong-bonus-force-cursor',lambda r:event(r,'force_enter',lambda x:x['cursor']==bonus).__setitem__('cursor',result))
        def duplicate_owner(r):
            xs=[x for x in r['events'] if x['event']=='closure_capture_handoff' and x['node']==helper];xs[1]['owners'][hcap]=xs[0]['owners'][hcap]
        reject('reused-helper-bonus-owner',duplicate_owner)
        reject('bonus-retirement-lost-memo',lambda r:event(r,'slot_remove',lambda x:x['host']==helper).__setitem__('target_state','THUNK'))
        reject('lost-bonus-memo-census',lambda r:r['metrics'].__setitem__('memo_fast_paths',0))
        def early_bonus(r):
            row=event(r,'callback_enter',lambda x:x['node']==bonus);r['events'].remove(row);r['events'].insert(0,row)
        reject('bonus-forced-during-introduction',early_bonus)
    return rows


def structure_controls(capture,verified,plan,generated):
    base=structure(capture,verified,plan,generated);rows=[]
    def reject(name,change):
        c,v,p=copy.deepcopy(capture),copy.deepcopy(verified),copy.deepcopy(plan)
        alternate=change(c,v,p,generated);g=alternate if isinstance(alternate,str) else generated
        try:structure(c,v,p,g)
        except (AssertionError,KeyError,ValueError,IndexError):rows.append({'control':name,'status':'rejected'})
        else:raise AssertionError('copied callable structure accepted: '+name)
    sm=lambda p:p['binding']['source_map']['scheme_map'][0]
    reject('changed-normalization-policy',lambda c,v,p,g:c['normalization'].__setitem__('policy','shared-rank1-callable/3'))
    reject('invented-normalization-step',lambda c,v,p,g:c['normalization']['steps'].append({}))
    reject('wrong-callable-source-type',lambda c,v,p,g:v['fragment']['definitions'][0]['captures']['callables'][0].__setitem__('type',INT))
    reject('wrong-direct-binding-origin',lambda c,v,p,g:v['fragment']['definitions'][0]['captures']['callables'][0].__setitem__('value_source',address([])))
    reject('lost-callable-occurrence',lambda c,v,p,g:v['fragment']['definitions'][0]['captures']['callables'][0].__setitem__('occurrences',[]))
    reject('lost-ordinary-binder',lambda c,v,p,g:p['binding']['source_map']['term_map'][0].__setitem__('binder',999999))
    reject('lost-dead-coordinate',lambda c,v,p,g:p['binding']['source_map']['use_map'][0].__setitem__('arguments',[]))
    reject('wrong-import-owner',lambda c,v,p,g:sm(p)['imports'][0].__setitem__('value',instruction(p['program'],sm(p)['generalize'])['out']))
    reject('missing-import-map',lambda c,v,p,g:instruction(p['program'],sm(p)['generalize']).__setitem__('imports',{}))
    reject('undischarged-child-alias',lambda c,v,p,g:instruction(p['program'],sm(p)['generalize'])['body'].pop(1))
    reject('helper-rebranded-scoped',lambda c,v,p,g:p['program']['functions'][base['helper_code']['name']].__setitem__('type_scope',sm(p)['scheme']))
    reject('changed-helper-capture-contract',lambda c,v,p,g:p['program']['functions'][base['helper_code']['name']]['captures'].__setitem__('extra',{'layout':'^T1','relation':'down'}))
    reject('changed-input-binding-hash',lambda c,v,p,g:p['binding'].__setitem__('input_sha256','0'*64))
    reject('removed-post-begin-retain',lambda c,v,p,g:g.replace(' = rt8_retain(ctx,',' = forbidden_alias(ctx,',1))
    reject('changed-generated-application',lambda c,v,p,g:g.replace('rt8_application(', 'forbidden_application(',1))
    def wrong_support(c,v,p,g):
        generalize=instruction(p['program'],sm(p)['generalize'])
        if base['program']['functions'][base['root_code']['name']]['captures'][base['root_capture']]['relation']=='below':
            next(x for x in p['program']['entry'] if x.get('out')==generalize['in'])['imports']=[]
        else:
            p['program']['functions'][base['root_code']['name']]['captures'][base['root_capture']]['relation']='below'
    reject('invented-strict-import-support',wrong_support)
    if base['facts']['captured']:
        hname=base['helper_code']['name'];hcap=base['helper_scalar_capture']['capture'];bcap=base['helper_body_bonus']['capture'];bsite=base['bonus_site']
        reject('flattened-pending-scalar-import',lambda c,v,p,g:instruction(p['program'],sm(p)['generalize'])['imports'].__setitem__('flattened',{'value':instruction(p['program'],bsite['path'])['out'],'layout':'^T1','relation':'down'}))
        reject('lost-original-helper-capture',lambda c,v,p,g:instruction(p['program'],base['helper_site']['path'])['captures'].clear())
        reject('changed-helper-body-bonus',lambda c,v,p,g:instruction(p['program'],base['helper_body_site']['path'])['captures'].__setitem__(bcap,p['program']['functions'][hname]['parameter']))
        reject('bonus-wrong-concrete-code',lambda c,v,p,g:p['program']['codes'][instruction(p['program'],bsite['path'])['code']].__setitem__('type_scope',sm(p)['scheme']))
        reject('bonus-dropped-before-helper',lambda c,v,p,g:p['program']['entry'].insert(1,{'op':'drop','value':instruction(p['program'],bsite['path'])['out']}))
    def contract(name,change):
        info=copy.deepcopy(base);change(info)
        try:closed_entry_contract(info)
        except (AssertionError,KeyError,ValueError,IndexError):rows.append({'control':name,'status':'rejected'})
        else:raise AssertionError('copied callable proof accepted: '+name)
    contract('missing-no-effects-proof',lambda i:i['derived']['introductions'][0].pop('closed_entry'))
    contract('missing-callable-proof-owner',lambda i:i['derived']['introductions'][0]['closed_entry']['callable_imports'].clear())
    contract('helper-added-to-scoped-closure',lambda i:i['derived']['introductions'][0]['closed_entry']['codes'].append(i['helper_code']['id']))
    contract('forged-scalar-effect-proof',lambda i:i['derived']['introductions'][0]['closed_entry'].__setitem__('policy','instance-only-scoped-scalars/1'))
    def neutral(i):
        ce=next(x['id'] for x in i['meta']['code_executions'] if x['code']==i['root_code']['id'] and x['env']==i['scheme']['neutral_env'])
        next(x for x in i['meta']['boundaries'] if x['key']['kind']=='entry')['key']['code_execution']=ce
    contract('invented-neutral-callable-entry',neutral)
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc',required=True);parser.add_argument('--cc',default='cc');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();require(QUALIFICATION_READY,'portable callable suite awaits independent review')
    output=args.output.absolute();require(output.resolve()==output and output!=BASE.parents[2] and BASE.parents[2] not in output.parents,
                                         'fresh output must be outside checkout')
    output.mkdir(parents=True,exist_ok=False);env=cli.environment(output);build.SUITE_DEADLINE=time.monotonic()+1500
    rows={}
    try:
        for case,source in (('direct-helper',SOURCE),('captured-helper',CAPTURED_SOURCE)):
            inputs=output/(case+'-inputs');inputs.mkdir()
            for name,text in {'main.emlf':source,'SharedPoly.emlf':SHARED}.items():(inputs/name).write_text(text,encoding='utf-8')
            target=output/case
            build.run([sys.executable,'-B',str(BASE/'run_source_v8.py'),str(inputs/'main.emlf'),'--module-root',str(inputs),
                       '--ghc',args.ghc,'--cc',args.cc,'--output',str(target)],output,case,cwd=BASE,env=env,
                      wall=1200,cpu=900,memory=16<<30,termination_grace=15,stdout_limit=1<<20,stderr_limit=1<<20,file_limit=64<<20)
            require(not bounded_read(output/(case+'.stderr'),1<<20),'successful source CLI diagnostics')
            result=read_json(target/'result.json');e=read_json(target/'native/run.stdout')
            require(result['status']=='complete' and result['failure_policy']=='retain' and result['native']==e and 'placement' not in result,
                    'fresh default source result differs')
            c=read_json(target/'capture.stdout');v=read_json(target/'verification.json');p=read_json(target/'planned.json',8<<20)
            require(p['binding']['mode']=='coarse-owned','default placement changed')
            generated=bounded_read(target/'native/ir8_runtime_generated.c',8<<20).decode();info=structure(c,v,p,generated)
            require(info['facts']['captured']==(case=='captured-helper'), 'fresh source case association differs')
            row={'status':'passed','observation':observe(e,info),'report_controls':copied_controls(e,info),
                 'structure_controls':structure_controls(c,v,p,generated),
                 'source_hashes':{'main.emlf':build.sha(source.encode()),'SharedPoly.emlf':build.sha(SHARED.encode())}}
            build.save(target/'generic-callable-observations.json',row);rows[case]=row
            print(case+': PASS',flush=True)
        build.save(output/'results.json',{'status':'passed','cases':rows})
    except BaseException as exc:
        try:build.save(output/'failure.json',{'error':repr(exc)})
        except BaseException as persistence:exc.add_note('Failure persistence also failed: '+repr(persistence))
        raise
    return 0


if __name__=='__main__':raise SystemExit(main())
