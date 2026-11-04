#!/usr/bin/env python3
"""Controlled original-source qualification of closed Instance scalar work.

The original direct generalized lambda stays shared. Concrete scalar imports
retain their identities; newly allocated scoped computations use the particular
closed Env. The closed-entry proof restricts lawful invocation, not neutral
construction/type rows. Public events do not expose every owner Access/capsule;
separate real-session guard controls cover those private boundaries.
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
from test_shared_source_native import instruction
from test_source_v8_recursive_sum import one, walk, var, source_allocation, INT
from test_source_v8_callable_captures import address, spine, read_json
from test_source_v8_monomorphic_recursion import ledger

require = build.require
BOOL = {'tag':'constructor','name':'Bool','arguments':[]}
QUALIFICATION_READY = True
SHARED = 'module SharedPoly (sharedId) where\nsharedId : forall a. a -> a\nsharedId x = x\n'
SOURCES = {
 'mixed-scalar': 'import SharedPoly\nlet bonus = addInt 20 1 in\nlet flag = ltInt bonus 22 in\nlet k = \\x -> if flag then bonus else 0 in\naddInt (k true) (k 0)\n',
 'alias-scalar': 'import SharedPoly\nlet bonus = addInt 5 5 in\nlet other = bonus in\nlet k = \\x -> addInt bonus other in\naddInt 2 (addInt (k true) (k 0))\n',
}
ACCESS_SCOPE = ('Exact source/import/resource/metadata/generated-Code joins are checked. '
                'Public events expose allocation Env, nodes and handoff owner IDs, but not '
                'every acquired owner Access or callback capsule. Private guard controls '
                'supply separate bounded evidence; no native effect/import whitelist is claimed.')


def primitive(node, path, name, ident, types=()):
    head, _, args = spine(node, path)
    require(head == {'tag':'primitive','id':ident,'name':name,'arguments':list(types)},
            'exact original primitive head differs: '+name)
    return args


def source_facts(capture, case):
    require(case in SOURCES, 'known controlled source required')
    mixed = case == 'mixed-scalar'
    normal = capture['normalization']; raw = normal['raw_normalized']
    require(capture['checked_type'] == INT and raw['tag'] == 'with_data' and
            normal['policy'] == 'shared-rank1-callable/1' and
            len(normal['steps']) == (2 if mixed else 0) and
            all(normal[k] for k in ('declarations_equal','erasure_equal','normalized_rechecked',
                                   'original_rechecked','root_type_alpha_equal')),
            'exact original checked normalization differs')
    replay = derive_shared_fragment(capture['projection']['projected_annotated'])
    for key in ('policy','input_checked_type','input_annotated','input_erased','raw_normalized','steps'):
        require(replay[key] == normal[key], 'independent normalization differs: '+key)
    bonus = raw['body']; second = bonus['body']; shared = second['body']
    bp=['body']; sp=bp+['body']; kp=sp+['body']; cp=kp+['value','body']; bodyp=cp+['body']
    require(bonus['tag']==second['tag']==shared['tag']=='let' and shared['body']['tag']!='let',
            'three original lexical lets required')
    args=primitive(bonus['value'],bp+['value'],'addInt',8)
    require([n for _,n in args] == [{'tag':'int64','value':20 if mixed else 5},
                                  {'tag':'int64','value':1 if mixed else 5}], 'original pending bonus differs')
    if mixed:
        args=primitive(second['value'],sp+['value'],'ltInt',11)
        require(len(args)==2 and var(args[0][1],bonus['name']) and
                args[1][1]=={'tag':'int64','value':22}, 'original pending flag dependency differs')
    else:
        require(var(second['value'],bonus['name']), 'lexical alias must keep original bonus')
    prefix=shared['value']; lam=prefix['body']
    require(prefix['tag']=='type_lambda' and prefix['bound']=={'tag':'bottom'} and
            lam['tag']=='lambda' and lam['parameter_type']=={'tag':'var','id':prefix['id']},
            'one direct rank1 generic lambda required')
    body_args=primitive(lam['body'],bodyp,'ifThenElse' if mixed else 'addInt',13 if mixed else 8,[INT] if mixed else [])
    if mixed:
        require(len(body_args)==3 and var(body_args[0][1],second['name']) and var(body_args[1][1],bonus['name']) and
                body_args[2][1]=={'tag':'int64','value':0}, 'original lazy conditional differs')
        occurrences=[body_args[1][0],body_args[0][0]]
    else:
        require(len(body_args)==2 and var(body_args[0][1],bonus['name']) and var(body_args[1][1],second['name']),
                'original alias computation differs')
        occurrences=[body_args[0][0],body_args[1][0]]
    root_args=primitive(shared['body'],kp+['body'],'addInt',8)
    if not mixed:
        require(root_args[0][1]=={'tag':'int64','value':2}, 'outer addition of two must remain')
        call_args=primitive(root_args[1][1],root_args[1][0],'addInt',8)
    else:call_args=root_args
    require(len(call_args)==2, 'two original calls required')
    for (path,node),arg in zip(call_args,[{'tag':'bool','value':True},{'tag':'int64','value':0}]):
        require(node['tag']=='application' and node['function']['tag']=='type_application' and
                var(node['function']['value'],shared['name']) and node['argument']==arg,
                'ordinary full-vector shared application differs')
    require(len([1 for _,n in walk(raw) if isinstance(n,dict) and n.get('tag')=='lambda'])==1,
            'original generic lambda cloned')
    return dict(case=case,mixed=mixed,raw=raw,replay=replay,bonus=bonus,second=second,shared=shared,
                prefix=prefix,lam=lam,bp=bp,sp=sp,kp=kp,cp=cp,bodyp=bodyp,body_args=body_args,
                occurrences=occurrences,calls=call_args,root_args=root_args,
                imports=[bonus['name']['id'],second['name']['id']],types=[INT,BOOL if mixed else INT])


def structure(capture, verified, plan, generated, case='mixed-scalar'):
    f=source_facts(capture,case); p=plan['program']; mapping=plan['binding']['source_map']
    require(verified['fragment_admitted'] and verified['normalization_replay']=='all exact independent fields match' and
            verified['producer_normalization_step_count']==(2 if f['mixed'] else 0) and
            verified['fragment']['definitions']==f['replay']['polymorphism']['definitions'] and
            verified['fragment']['uses']==f['replay']['polymorphism']['uses'], 'fresh fragment evidence differs')
    definition=one(verified['fragment']['definitions'],'one captured generalized definition')
    scheme_map=one(mapping['scheme_map'],'one Scheme source map')
    require(definition['binding']==f['shared']['name'] and definition['binding_source']==address(f['kp']) and
            definition['rhs_cursor']==scheme_map['rhs_cursor']==address(f['cp']) and
            definition['free_term_bindings']==f['imports'] and scheme_map['binder']==f['shared']['name']['id'] and
            len(definition['prefix'])==1 and definition['prefix'][0]['id']==f['prefix']['id'],
            'actual binding/prefix/free-owner identity differs')
    inventory=[{'binding':binder,'type':typ,'occurrences':[address(path)]}
               for binder,typ,path in zip(f['imports'],f['types'],f['occurrences'])]
    require(definition['captures']=={'policy':'closed-scalar-generalization-captures/1','scalars':inventory},
            'complete lexical scalar import inventory differs')
    require(len(p['schemes'])==len(p['functions'])==1 and not p['families'] and not p['layouts'],
            'one unchanged scalar generic graph required')
    scope=scheme_map['scheme']; g=instruction(p,scheme_map['generalize'])
    bonus=source_allocation(plan,f['bp']+['value'],'thunk')
    closure=source_allocation(plan,f['cp'],'closure')
    imports=scheme_map['imports']; require(len(imports)==len(g['imports'])==2, 'two distinct lexical imports required')
    if f['mixed']:
        second=source_allocation(plan,f['sp']+['value'],'thunk')
        parent_values=[bonus['out'],second['out']]
    else:
        second=one([i for i in p['entry'] if i.get('out')==imports[1]['value']], 'actual lexical retain')
        require(second=={'op':'retain','out':second['out'],'value':bonus['out']}, 'lexical alias must retain original owner')
        parent_values=[bonus['out'],second['out']]
    require(len(set(parent_values))==2 and g['in']==bonus['in'], 'shared RHS must retain actual import support')
    for row,binder,typ,path,parent in zip(imports,f['imports'],f['types'],f['occurrences'],parent_values):
        require(row=={'binding':binder,'import':row['import'],'layout':row['layout'],
                     'occurrences':[address(path)],'relation':'down','value':parent} and
                p['types'][row['layout'][1:]]=={'tag':'closed','layout':'#bool' if typ==BOOL else '#i64'},
                'typed import/source-parent join differs')
    require(g['imports']=={r['import']:{'value':r['value'],'layout':r['layout'],'relation':'down'} for r in imports},
            'explicit imports map differs')
    carriers=mapping['carrier_map']
    def carrier(path,kind):
        return one([r for r in carriers if r['source']==address(path) and r['kind']==kind], 'source carrier '+kind)
    root_carrier=carrier(f['cp'],'lambda'); computation=carrier(f['bodyp'],'conditional' if f['mixed'] else 'primitive')
    wanted=[root_carrier,computation]
    if f['mixed']:
        wanted += [carrier(f['body_args'][1][0],'conditional-then'),carrier(f['body_args'][2][0],'conditional-else')]
    require([r for r in carriers if r['type_scope']==scope]==wanted and
            all(not r['view_captures'] and r['type_scope']==scope for r in wanted),
            'same-Scheme scoped carrier closure differs')
    caps={x['binder']:x['capture'] for x in root_carrier['mono_captures']}
    require(list(caps)==f['imports'] and root_carrier['ir_code']==closure['function'] and
            closure['captures']=={caps[r['binding']]:r['import'] for r in imports} and
            g['body']==[closure]+[{'op':'drop','value':r['import']} for r in imports]+[{'op':'seal','value':closure['out']}],
            'direct root capture/import-discharge/seal sequence differs')
    for r in imports:
        require(p['entry'].index(g)<p['entry'].index({'op':'drop','value':r['value']}), 'parent owner dropped during intro')
    function=p['functions'][closure['function']]; body_allocation=source_allocation(plan,f['bodyp'],'thunk')
    inner_caps={x['binder']:x['capture'] for x in computation['mono_captures']}
    require(list(inner_caps)==f['imports'] and body_allocation=={
            'op':'thunk','out':body_allocation['out'],'in':'$home','code':computation['ir_code'],
            'captures':{inner_caps[b]:caps[b] for b in f['imports']}} and
            function['type_scope']==scope and function['body']==[body_allocation]+
            [{'op':'drop','value':caps[b]} for b in f['imports']]+
            [{'op':'drop','value':function['parameter']},{'op':'return','value':body_allocation['out']}],
            'each generic invocation must construct and return its pending scoped computation')
    for r in wanted:
        decl=p['functions' if r['kind']=='lambda' else 'codes'][r['ir_code']]
        require(decl['type_scope']==scope and decl['captures']=={
            x['capture']:{'layout':x['layout'],'relation':'down'} for x in r['mono_captures']},
            'closed capture contracts or scoped declaration lost')
    cb=p['codes'][computation['ir_code']]['body']
    if f['mixed']:
        yes=source_allocation(plan,f['body_args'][1][0],'thunk');no=source_allocation(plan,f['body_args'][2][0],'thunk')
        ycap=one(wanted[2]['mono_captures'],'selected bonus capture')['capture']
        require(yes['captures']=={ycap:inner_caps[f['imports'][0]]} and not no['captures'], 'lazy branch capture mapping differs')
        require([i['op'] for i in cb]==['retain','force','thunk','thunk','select_i64','drop','drop','drop','return'] and
                cb[0]['value']==inner_caps[f['imports'][1]] and cb[1]['value']==cb[0]['out'] and cb[2]==yes and cb[3]==no and
                cb[4]=={'op':'select_i64','out':cb[4]['out'],'in':'$home','condition':cb[1]['out'],'then':yes['out'],'else':no['out']} and
                cb[-1]=={'op':'return','value':cb[4]['out']}, 'condition must force flag then return a selected lazy branch')
        yb=p['codes'][yes['code']]['body'];nb=p['codes'][no['code']]['body']
        require(yb==[{'op':'retain','out':yb[0]['out'],'value':ycap},{'op':'drop','value':ycap},{'op':'return','value':yb[0]['out']}] and
                nb==[{'op':'scalar','out':nb[0]['out'],'in':'$home','kind':'i64','value':0},{'op':'return','value':nb[0]['out']}],
                'selected original bonus or unselected zero branch differs')
    else:
        require([i['op'] for i in cb]==['retain','force','retain','force','prim2','drop','drop','drop','drop','return'] and
                cb[0]['value']==inner_caps[f['imports'][0]] and cb[2]['value']==inner_caps[f['imports'][1]] and
                cb[1]['value']==cb[0]['out'] and cb[3]['value']==cb[2]['out'] and
                cb[4]=={'op':'prim2','out':cb[4]['out'],'in':'$home','primitive':'addInt','left':cb[1]['out'],'right':cb[3]['out']} and
                cb[-1]=={'op':'return','value':cb[4]['out']}, 'both lexical aliases must be demanded by each Instance add')
    checked=check_resources(p);d=json.loads(checked.derived_json);meta=json.loads(check_metadata(p).metadata_json)
    gf=one([x for x in d['instructions'] if x['path']==scheme_map['generalize']], 'generalize facts')
    parents=gf['inputs'][1:];children=gf['outputs'][1:]
    require(len(parents)==len(children)==2 and len({x['capability'] for x in parents+children})==4 and
            len({x['storage'] for x in parents+children})==4, 'distinct lexical/intro aliases lost')
    for row,parent,child in zip(imports,parents,children):
        require(parent['role']==['imports',row['import'],'value'] and child['role']==['imports',row['import']] and
                parent['mode']==child['mode']=='own' and parent['view']==child['view']=='MONO' and not parent['ready'] and
                parent['projection'] is None and parent['scheme'] is None and not parent['ticket'], 'import owner fact differs')
        require(all(parent[k]==child[k] for k in parent if k not in ('role','capability','storage')),
                'copied import facts must preserve original node/Access provenance/readiness')
        prov=d['provenance'][parent['provenance']]['value']
        require(prov['kind']=='allocated' and prov['context']=={'kind':'concrete'}, 'unknown origin is not an E0 import proof')
        drops=[x['inputs'][0] for x in d['instructions'] if x['op']=='drop']
        require(all(any(x['capability']==h['capability'] for x in drops) for h in (parent,child)), 'parent or child alias not discharged')
    require(len({x['node'] for x in children})==(2 if f['mixed'] else 1), 'lexical alias identity incorrectly copied/deduplicated')
    introduction=one(d['introductions'],'one conditional introduction proof');proof=introduction['closed_entry']
    def site(path,role):
        a=one([x for x in mapping['allocation_map'] if x['source']==address(path) and x['role']==role], 'exact source allocation')
        return one([x for x in meta['sites'] if x['path']==a['instruction']], 'exact metadata Site')
    root_site=site(f['cp'],'closure');scheme=one(meta['schemes'],'one metadata Scheme');root_code=meta['codes'][root_site['code']]
    scoped_codes=[c['id'] for c in meta['codes'] if c['scope']==scheme['id']]
    effects=[i for i,row in enumerate(d['instructions']) if row['type_scope']==scope and row['op'] in ('force','prim2','select_i64')]
    require(proof=={'policy':'instance-only-scoped-scalars/1','root_site':root_site['id'],'root_code':root_code['id'],
                   'codes':scoped_codes,'effects':effects} and introduction['result_sites']==[root_site['id']] and
            [d['instructions'][i]['op'] for i in effects]==(['force','select_i64'] if f['mixed'] else ['force','force','prim2']),
            'fresh complete closed-entry/effect proof differs')
    coverage=one([x for x in meta['coverage'] if x['source']['kind']=='closed-entry'], 'one independently rederived coverage proof')
    require(coverage['source']=={'kind':'closed-entry','intro':introduction['id'],'proof':proof}, 'metadata proof differs')
    neutral_exec={x['id'] for x in meta['code_executions'] if x['code'] in scoped_codes and x['env']==scheme['neutral_env']}
    require(len(neutral_exec)==len(scoped_codes) and any(x['env']==scheme['neutral_env'] for x in meta['site_executions']),
            'neutral construction/type rows must remain')
    for boundary in meta['boundaries']:
        key=boundary['key']
        if key['kind'] in ('entry','return'):
            require(key['code_execution'] not in neutral_exec, 'effectful neutral invocation advertised')
        if key['kind'] in ('slot','deferred'):
            sx=meta['site_executions'][key['site_execution']];sxsite=meta['sites'][sx['site']]
            if sxsite['context']['kind']=='execution':
                require(sx['env']!=scheme['neutral_env'], 'effectful neutral execution boundary advertised')
    require(len(mapping['use_map'])==len(verified['fragment']['uses'])==len(meta['uses'])==2, 'two full vectors required')
    semantic_uses=[]
    for index,((path,_),typ) in enumerate(zip(f['calls'],[BOOL,INT])):
        source=verified['fragment']['uses'][index];row=mapping['use_map'][index]
        require(source['arguments']==[typ] and source['instantiated_type']=={'tag':'arrow','from':typ,'to':INT} and
                source['source']==row['source']==address(path+['function']) and row['use']==index and row['definition']==0,
                'exact source witness/ordered vector correspondence differs')
        atom='#bool' if typ==BOOL else '#i64';tid=one([x['id'] for x in meta['types'] if x['tag']=='closed' and x['atom']==atom], 'intrinsic coordinate')
        use=one([u for u in meta['uses'] if u['arguments']==[tid]], 'exact full-vector Use');semantic_uses.append(use)
        env=meta['environments'][use['env']]
        require(env['mode']=='CLOSED' and env['scheme']==scheme['id'] and env['arguments']==[tid] and
                [p['types'][t]['layout'] for t in row['arguments']]==[atom], 'closed Env vector differs')
        ce=one([x for x in meta['code_executions'] if x['code']==root_code['id'] and x['env']==use['env']], 'projected root Code')
        require(ce['argument']==tid and ce['result']==root_code['result'] and ce['captures']==root_code['captures'],
                'projected generic root contract differs')
        view=row['source_view'];host=one([x for x in carriers if x['carrier']==view['carrier']], 'actual use carrier')
        cap=one([x for x in host['view_captures'] if x['capture']==view['capture']], 'actual full-vector capture')
        retained=instruction(p,one(row['creation'],'one source view retain'));call=source_allocation(plan,path,'application')
        require(cap['arguments']==row['arguments'] and cap['binder']==scheme_map['binder'] and
                retained=={'op':'retain','out':call['function'],'value':cap['capture']}, 'source call lost its full captured view')
    for host in carriers:
        for view in host['view_captures']:
            ops=[instruction(p,x) for x in view['creation']];origin=view['source_view']
            require(view['binder']==scheme_map['binder'] and view['definition']==0 and view['relation']=='down', 'captured view binder differs')
            if origin['kind']=='scheme':
                require(len(ops)==4 and ops[0]['op']=='retain' and ops[0]['value']==g['out'] and ops[1]['op']=='instantiate' and
                        ops[1]['value']==ops[0]['out'] and p['instantiations'][ops[1]['instantiation']]['arguments']==view['arguments'],
                        'complete root view creation differs')
                temp=ops[1]['out'];allocation=ops[2]
            else:
                parent=one([x for x in carriers if x['carrier']==origin['carrier']], 'parent view carrier')
                previous=one([x for x in parent['view_captures'] if x['capture']==origin['capture']], 'parent full view')
                require(origin['kind']=='captured' and len(ops)==3 and previous['arguments']==view['arguments'] and
                        previous['binder']==view['binder'] and ops[0]['op']=='retain' and ops[0]['value']==origin['capture'],
                        'transitive view pair differs')
                temp=ops[0]['out'];allocation=ops[1]
            require(allocation['op']=='thunk' and allocation['code']==host['ir_code'] and allocation['captures'][view['capture']]==temp and
                    ops[-1]=={'op':'drop','value':temp}, 'view lifetime must reach publication before release')
    require(emit_runtime(p).runtime_source==generated, 'fresh generated C differs')
    entry=generated.split('static void rt8_entry(Rt8Context *ctx)',1)[1].split('\n}\n',1)[0]
    begin=entry.index('rt8_generic_begin(');closure_at=entry.index('rt8_closure(',begin);seal_at=entry.index('rt8_generic_seal(',closure_at)
    acquired=re.findall(r'(h\d+) = rt8_retain\(ctx, (h\d+)\);',entry[begin:closure_at])
    require(len(acquired)==2 and len({x for x,_ in acquired})==len({x for _,x in acquired})==2,
            'two independent post-begin aliases required')
    for child,parent in acquired:
        require(re.search(r'\w+\[\d+\] = '+child+r';',entry[begin:closure_at]) and
                closure_at<entry.index('rt8_drop(ctx, '+child+');',closure_at)<seal_at and
                entry.index('rt8_drop(ctx, '+parent+');',seal_at)>seal_at,
                'each captured intro alias must discharge before seal, parent after seal')
    return dict(facts=f,program=p,mapping=mapping,derived=d,meta=meta,proof=proof,scheme=scheme,root_code=root_code,
                root_site=root_site,root_captures=caps,body_captures=inner_caps,
                bonus_site=site(f['bp']+['value'],'thunk'),second_site=site(f['sp']+['value'],'thunk') if f['mixed'] else None,
                body_site=site(f['bodyp'],'thunk'),body_code=meta['codes'][site(f['bodyp'],'thunk')['code']],
                call_sites=[site(path,'application') for path,_ in f['calls']],uses=semantic_uses,
                then_site=site(f['body_args'][1][0],'thunk') if f['mixed'] else None,
                else_site=site(f['body_args'][2][0],'thunk') if f['mixed'] else None,
                result_site=site(f['bodyp'],'prim2') if not f['mixed'] else None,
                bonus_result_site=site(f['bp']+['value'],'prim2'),
                flag_result_site=site(f['sp']+['value'],'prim2') if f['mixed'] else None,
                import_resource_facts={'parents':parents,'children':children})


def structure_controls(capture,verified,plan,generated,case='mixed-scalar'):
    base=structure(capture,verified,plan,generated,case);rows=[]
    def reject(name,change):
        c,v,p=copy.deepcopy(capture),copy.deepcopy(verified),copy.deepcopy(plan)
        alternate=change(c,v,p,generated);g=alternate if isinstance(alternate,str) else generated
        try:structure(c,v,p,g,case)
        except (AssertionError,KeyError,ValueError,IndexError):rows.append({'control':name,'status':'rejected'})
        else:raise AssertionError('copied structure accepted: '+name)
    sm=lambda p:p['binding']['source_map']['scheme_map'][0]
    reject('wrong-normalization-policy',lambda c,v,p,g:c['normalization'].__setitem__('policy','shared-rank1-callable/3'))
    if case=='mixed-scalar':reject('wrong-normalization-proof',lambda c,v,p,g:c['normalization']['steps'][0].__setitem__('rule','wrong'))
    reject('lost-import-occurrence',lambda c,v,p,g:sm(p)['imports'][0].__setitem__('occurrences',[]))
    reject('deduplicated-lexical-import',lambda c,v,p,g:sm(p)['imports'].pop())
    reject('wrong-import-parent',lambda c,v,p,g:sm(p)['imports'][1].__setitem__('value',sm(p)['imports'][0]['value']))
    reject('lost-full-coordinate',lambda c,v,p,g:p['binding']['source_map']['use_map'][0].__setitem__('arguments',[]))
    reject('wrong-capture-type',lambda c,v,p,g:v['fragment']['definitions'][0]['captures']['scalars'][0].__setitem__('type',BOOL))
    reject('missing-import-map',lambda c,v,p,g:instruction(p['program'],sm(p)['generalize']).__setitem__('imports',{}))
    reject('intro-owner-leak',lambda c,v,p,g:instruction(p['program'],sm(p)['generalize'])['body'].pop(1))
    def wrong_scope(c,v,p,g):
        r=next(r for r in p['binding']['source_map']['carrier_map'] if r['type_scope'] is not None and r['kind']!='lambda')
        p['program']['codes'][r['ir_code']]['type_scope']=None
    reject('concrete-scoped-carrier',wrong_scope)
    reject('removed-post-begin-retain',lambda c,v,p,g:g.replace(' = rt8_retain(ctx,',' = forbidden_alias(ctx,',1))
    reject('changed-operation-helper',lambda c,v,p,g:g.replace('rt8_select_i64(' if case=='mixed-scalar' else 'rt8_prim2(', 'forbidden_effect(',1))
    def reject_contract(name,change):
        info=copy.deepcopy(base);change(info)
        try:closed_entry_contract(info)
        except (AssertionError,KeyError,ValueError,IndexError):rows.append({'control':name,'status':'rejected'})
        else:raise AssertionError('copied closed-entry contract accepted: '+name)
    reject_contract('lost-closed-entry-proof',lambda i:i['derived']['introductions'][0].pop('closed_entry'))
    reject_contract('wrong-proof-root',lambda i:i['derived']['introductions'][0]['closed_entry'].__setitem__('root_site',i['bonus_site']['id']))
    reject_contract('lost-scoped-code',lambda i:i['derived']['introductions'][0]['closed_entry']['codes'].pop())
    reject_contract('lost-scoped-effect',lambda i:i['derived']['introductions'][0]['closed_entry']['effects'].pop())
    def neutral_boundary(i):
        neutral=next(x['id'] for x in i['meta']['code_executions'] if x['env']==i['scheme']['neutral_env'] and x['code']==i['root_code']['id'])
        next(x for x in i['meta']['boundaries'] if x['key']['kind']=='entry')['key']['code_execution']=neutral
    reject_contract('invented-neutral-invocation',neutral_boundary)
    return rows


def closed_entry_contract(info):
    """Check retained proof/coverage against the independently derived expectation."""
    d=info['derived'];meta=info['meta'];proof=info['proof']
    require(one(d['introductions'],'one introduction')['closed_entry']==proof and
            one([r for r in meta['coverage'] if r['source']['kind']=='closed-entry'],'closed coverage')['source']['proof']==proof,
            'closed-entry resource/metadata proof differs')
    neutral={r['id'] for r in meta['code_executions'] if r['code'] in proof['codes'] and r['env']==info['scheme']['neutral_env']}
    require(len(neutral)==len(proof['codes']), 'neutral construction typing was removed')
    for row in meta['boundaries']:
        key=row['key']
        if key['kind'] in ('entry','return'):
            require(key['code_execution'] not in neutral, 'neutral invocation is not a lawful closed-entry case')


def observe(evaluation,info):
    closed_entry_contract(info)
    e=evaluation;f=info['facts'];meta=info['meta'];events=e['events'];mixed=f['mixed']
    require(e['schema']=='resource-ir-v8-run/1' and e['state']==e['fault']==0 and e['graph_executed']==1 and
            e['result']=={'kind':'i64','value':42} and e['scalar_result_kind']==1 and e['scalar_result']==42 and
            e['events_omitted']==0 and e['events_emitted']==len(events), 'complete healthy native Int42 report required')
    require(e['guards_failed_mask']==0 and e['guards_checked_mask']==(((1<<27)-1)&~(1<<24)&~(1<<4)) and
            0<e['guard_work_used']==e['guard_work_total']<=e['guard_work_limit']==67108864,
            'actual guard coverage/work differs; neither Fill nor Project is exercised')
    ledger(e,True)
    select=lambda name:[(i,x) for i,x in enumerate(events) if x['event']==name]
    allocations=select('allocate');nodes={x['node']:x for _,x in allocations}
    require(len(nodes)==len(allocations), 'unique actual allocations required')
    by_site=lambda site:[(i,x) for i,x in allocations if x['site_id']==site['id']]
    scalar=lambda node:one([(i,x) for i,x in select('scalar_value') if x['node']==node], 'one actual scalar value')
    memo=lambda node:one([(i,x) for i,x in select('memo_publish') if x['destination']==node], 'one actual memo publication')
    callback=lambda node:one([(i,x) for i,x in select('callback_enter') if x['node']==node], 'one actual callback')
    raw=lambda node:one([(i,x) for i,x in select('raw_return') if x['source']==node], 'one actual raw return')
    frame=lambda node,kind:one([(i,x) for i,x in select('frame_enter') if x['context'].get('node')==node and
                             x['context']['kind']==kind], 'one actual callback frame')
    frames_by_id={x['frame']:x for _,x in select('frame_enter')}
    require(len(frames_by_id)==len(select('frame_enter')), 'unique activation frames required')
    for _,fr in select('frame_enter'):
        context=fr['context']
        if context['kind']!='entry':
            node=nodes[context['node']]
            require(context['name']==node['code'] and context['home_group']==node['group'], 'frame Code/owner origin differs')
    for _,x in allocations:
        site=meta['sites'][x['site_id']]
        sx=one([r for r in meta['site_executions'] if r['site']==site['id'] and r['env']==x['env_id']], 'registered SiteExecution')
        rep=meta['representations'][sx['representation']]
        context=frames_by_id[x['frame']]['context'];path=site['path']
        op=instruction(info['program'],path)
        require(context['kind']==path['root'] and context.get('name')==path['name'] and
                x['opcode']==op['op'] and x['out']==op['out'] and
                x['state']=={'scalar':'READY','prim2':'READY','thunk':'THUNK','closure':'CLOSURE','application':'APPLICATION'}[op['op']] and
                x['shape_id']==rep['shape'] and x['code']==(meta['codes'][site['code']]['name'] if site['code'] is not None else None),
                'actual Site/Code/Env/representation join differs')
    bi,b=one(by_site(info['bonus_site']), 'one original pending bonus')
    ci,c=one(by_site(info['root_site']), 'one neutral shared closure')
    fi,flag=one(by_site(info['second_site']), 'one original pending flag') if mixed else (bi,b)
    targets={f['imports'][0]:b['node'],f['imports'][1]:flag['node']}
    expected_slots={cap:targets[binder] for binder,cap in info['root_captures'].items()}
    require(b['state']=='THUNK' and b['env_id']==0 and b['slots']=={} and
            c['state']=='CLOSURE' and c['env_id']==info['scheme']['neutral_env'] and c['slots']==expected_slots and
            c['type_id']==info['root_site']['principal_type'] and c['scheme_id']==info['scheme']['id'],
            'direct closure must capture the original pending concrete owners')
    if mixed:
        require(flag['state']=='THUNK' and flag['env_id']==0 and len(flag['slots'])==1 and
                list(flag['slots'].values())==[b['node']], 'pending flag must capture original pending bonus')
    gi,g=one(select('generic_begin'),'one begin');si,s=one(select('generic_seal'),'one seal')
    require(bi<=fi<gi<ci<si and g['scheme']==info['scheme']['id'] and
            g['intro']==s['intro']==info['scheme']['intro'] and g['capsule']==s['capsule']>0 and
            s['node']==c['node'] and s['owner']>g['watermark'], 'intro/owner watermark/seal join differs')
    old=meta['accesses'][s['old_access']];sealed=meta['accesses'][s['new_access']]
    require(old['mode']=='MONO' and old['site']==info['root_site']['id'] and
            old['origin_env']==old['use_env']==c['env_id'] and old['type']==info['root_site']['principal_type'] and
            old['scheme'] is None and sealed['mode']=='SCHEME' and sealed['scheme']==info['scheme']['id'] and
            sealed['site']==old['site'] and sealed['origin_env']==c['env_id'], 'exact neutral-to-Scheme Access differs')
    for cap,target in expected_slots.items():
        ii,install=one([(i,x) for i,x in select('slot_install') if x['host']==c['node'] and x['field']==cap], 'initial capture slot')
        require(gi<ii<ci and install['target']==target and install['target_state']=='THUNK' and
                install['reason']=='publication', 'intro must publish original pending import without forcing')
    inst=select('instantiate');require(len(inst)==2 and {x['use'] for _,x in inst}=={u['id'] for u in info['uses']}, 'two full views required')
    require(len({x['owner'] for _,x in inst})==2 and all(i>si and x['owner']>g['watermark'] and
            x['owner']!=s['owner'] and x['anchor'] is None and x['mode']=='own' for i,x in inst), 'distinct unanchored owned views required')
    for _,x in inst:
        use=one([u for u in info['uses'] if u['id']==x['use']], 'full-vector use')
        a=meta['accesses'][x['new_access']]
        require(x['node']==c['node'] and x['scheme']==info['scheme']['id'] and x['old_access']==s['new_access'] and
                a['mode']=='MONO' and a['site']==info['root_site']['id'] and a['origin_env']==c['env_id'] and
                a['use_env']==use['env'] and a['type']==use['result_type'], 'same shared node complete-vector Access differs')
    invokes=select('invoke_enter');returns=select('invoke_raw_return');hands=select('closure_capture_handoff')
    frames=[r for r in select('frame_enter') if r[1]['context']['kind']=='function']
    bodies=by_site(info['body_site'])
    require(len(invokes)==len(returns)==len(hands)==len(frames)==len(bodies)==2 and
            all(x['closure']==c['node'] for _,x in invokes+returns), 'same direct generic Code must execute twice')
    capture_owners=[];body_owners=[];apps=[];body_frames=[];completed=[]
    for j,((ii,call),(ri,ret),(hi,hand),(fri,fr),(body_i,body),use) in enumerate(zip(invokes,returns,hands,frames,bodies,info['uses'])):
        ai,app=one(by_site(info['call_sites'][j]), 'one source ordinary application')
        _,arg=scalar(call['argument']);wanted=f['calls'][j][1]['argument']
        require(arg['kind']==('bool' if wanted['tag']=='bool' else 'i64') and type(arg['value']) is type(wanted['value']) and
                arg['value']==wanted['value'] and app['state']=='APPLICATION' and app['env_id']==0 and
                app['slots']=={'$function':c['node'],'$argument':call['argument']}, 'source call/argument must preserve complete view')
        require(ai<hi<ii<fri<body_i<ri and call['protocol']==hand['protocol']=='repeat' and hand['node']==c['node'] and
                set(hand['owners'])==set(expected_slots) and fr['context']['name']==info['root_code']['name'] and
                fr['context']['node']==c['node'] and body['frame']==fr['frame'] and body['state']=='THUNK' and
                body['env_id']==use['env'] and body['slots']=={cap:targets[binder] for binder,cap in info['body_captures'].items()} and
                ret['argument']==call['argument'] and ret['result']==body['node'] and ret['token'] is None,
                'each call must return a distinct pending computation in its exact closed Env')
        capture_owners.extend(hand['owners'].values());apps.append(app['node'])
        hbi,hb=one([(i,x) for i,x in select('capture_handoff') if x['node']==body['node']], 'body capture handoff')
        cbi,cb=callback(body['node']);bfi,bf=frame(body['node'],'thunk');rbi,rb=raw(body['node'])
        require(ri<hbi<cbi<bfi<rbi and set(hb['owners'])==set(body['slots']) and
                bf['context']['name']==info['body_code']['name'], 'pending body callback/capture frame differs')
        body_owners.extend(hb['owners'].values());body_frames.append(bf['frame'])
        actual_forces=[x for _,x in select('ir_force_result') if x['frame']==bf['frame']]
        raw_forces=[x for x in info['program']['codes'][info['body_code']['name']]['body'] if x['op']=='force']
        require(len(actual_forces)==len(raw_forces) and all(
                x['out']==op['out'] and x['source_variable']==op['value']
                for x,op in zip(actual_forces,raw_forces)),
                'ordered Instance force events must name their exact raw instruction operands/results')
        for cap,target in body['slots'].items():
            pi,pub=one([(i,x) for i,x in select('slot_install') if x['host']==body['node'] and x['field']==cap], 'body publication')
            di,drop=one([(i,x) for i,x in select('slot_remove') if x['host']==body['node'] and x['field']==cap], 'body capture removal')
            state='THUNK' if j==0 else 'MEMO'
            require(fri<pi<body_i and pub['target']==drop['target']==target and pub['target_state']==drop['target_state']==state and
                    hbi<di<cbi and drop['reason']=='payload_clear', 'body capture alias/state/discharge differs')
        mi,mm=memo(body['node']);ami,am=memo(app['node'])
        require(rbi<ami<mi and am['result']==mm['result'], 'application/body memo completion differs')
        completed.append((ami,am['result']))
    require(len(set(capture_owners+body_owners))==8 and all(x>g['watermark'] for x in capture_owners+body_owners),
            'two lexical captures per call require independent fresh owner capabilities')
    bci,_=callback(b['node']);bri,br=raw(b['node']);bmi,bm=memo(b['node']);bvi,bv=scalar(bm['result'])
    _,ba=one(by_site(info['bonus_result_site']), 'original bonus result Site')
    require(returns[0][0]<bci<bvi<bri<bmi<returns[1][0] and br['result']==bm['result']==ba['node'] and br['result_state']=='READY' and
            bv['kind']=='i64' and type(bv['value']) is int and bv['value']==(21 if mixed else 10) and
            bv['primitive']=='addInt' and ba['env_id']==0, 'original concrete bonus must compute once after invocation')
    require(not any((x['event'] in ('callback_enter','update_pin') and x.get('node') in set(targets.values())) for x in events[:si]) and
            not any(x['destination']==c['node'] for _,x in select('memo_publish')), 'intro eagerly forced imports or invented generic RHS memo')
    if mixed:
        fci,_=callback(flag['node']);fri,fr=raw(flag['node']);fmi,fm=memo(flag['node']);fvi,fv=scalar(fm['result'])
        _,fa=one(by_site(info['flag_result_site']), 'flag scalar Site')
        require(returns[0][0]<fci<bci<bmi<fvi<fri<fmi<returns[1][0] and fr['result']==fm['result']==fa['node'] and
                fr['result_state']=='READY' and fv['kind']=='bool' and fv['value'] is True and fv['primitive']=='ltInt' and fa['env_id']==0,
                'flag and its original bonus dependency must evaluate once')
        choices=select('select_i64');yes=by_site(info['then_site']);no=by_site(info['else_site'])
        require(len(choices)==len(yes)==len(no)==2, 'two lazy branch pairs required')
        branch_nodes=[]
        for j,((choice_i,choice),(yi,y),(ni,n),(_,body),use) in enumerate(zip(choices,yes,no,bodies,info['uses'])):
            rbi,rb=raw(body['node']);yci,_=callback(y['node']);yri,yr=raw(y['node']);ymi,ym=memo(y['node'])
            forces=[(i,x) for i,x in select('ir_force_result') if x['frame']==body_frames[j]]
            require(len(forces)==1 and forces[0][1]['result']==fm['result'] and forces[0][0]<yi,
                    'Instance condition must force the same original flag before allocating branches')
            require(y['state']==n['state']=='THUNK' and y['env_id']==n['env_id']==use['env'] and
                    y['frame']==n['frame']==choice['frame']==body_frames[j] and list(y['slots'].values())==[b['node']] and not n['slots'] and
                    fmi<yi<ni<choice_i<rbi<yci<yri<ymi and choice['condition_node']==fm['result'] and choice['condition_value'] is True and
                    choice['then_node']==choice['result']==y['node'] and choice['else_node']==n['node'] and
                    rb['result']==y['node'] and rb['result_state']=='THUNK' and yr['result']==b['node'] and yr['result_state']=='MEMO' and
                    ym['result']==completed[j][1]==bm['result'], 'closed Instance selection must preserve lazy original bonus identity')
            require(not any(x.get('node')==n['node'] for _,x in select('callback_enter')+select('update_pin')) and
                    not any(x.get('source')==n['node'] or x.get('destination')==n['node'] for _,x in select('raw_return')+select('memo_publish')),
                    'unselected branch body was demanded')
            branch_nodes.append({'then':y['node'],'else':n['node']})
        require(not any(x['env_id'] in {u['env'] for u in info['uses']} and x['opcode']=='scalar' for _,x in allocations),
                'unselected scoped zero allocation must not occur')
        expected_callback_nodes={b['node'],flag['node'],*[x['node'] for _,x in bodies],*[x['node'] for _,x in yes]}
    else:
        require(not select('select_i64'), 'alias source has no conditional')
        results=by_site(info['result_site']);require(len(results)==2, 'two Instance primitive results required')
        for j,((vi,v),(_,body),use) in enumerate(zip(results,bodies,info['uses'])):
            svi,sv=scalar(v['node']);rbi,rb=raw(body['node'])
            force_results=[(i,x) for i,x in select('ir_force_result') if x['frame']==body_frames[j]]
            require(v['env_id']==use['env'] and v['frame']==body_frames[j] and vi<svi<rbi and
                    sv['kind']=='i64' and type(sv['value']) is int and sv['value']==20 and sv['primitive']=='addInt' and
                    rb['result']==completed[j][1]==v['node'] and rb['result_state']=='READY' and
                    len(force_results)==2 and all(x['result']==bm['result'] and i<vi for i,x in force_results),
                    'each Instance add must demand both aliases of the same ready ten')
        require(results[0][1]['node']!=results[1][1]['node'], 'two separate Instance sums must not collapse')
        branch_nodes=[];expected_callback_nodes={b['node'],*[x['node'] for _,x in bodies]}
    # Other callbacks are the original unscoped outer expression carriers. All
    # actually entered callbacks run once, and every scoped one is accounted for.
    actual_callbacks=[x['node'] for _,x in select('callback_enter')]
    require(len(actual_callbacks)==len(set(actual_callbacks)) and expected_callback_nodes<=set(actual_callbacks), 'callback recomputation or omission')
    scoped_nodes={x['node'] for _,x in allocations if meta['sites'][x['site_id']]['code'] in info['proof']['codes']}
    require(scoped_nodes=={c['node'],*[x['node'] for _,x in bodies],*[n for row in branch_nodes for n in row.values()]},
            'unaccounted scoped carrier allocation')
    require(set(actual_callbacks)&scoped_nodes==expected_callback_nodes&scoped_nodes, 'unexpected neutral or unselected scoped invocation')
    for cap,target in expected_slots.items():
        di,drop=one([(i,x) for i,x in select('slot_remove') if x['host']==c['node'] and x['field']==cap], 'shared capture retirement')
        require(di>completed[-1][0] and drop['target']==target and drop['target_state']=='MEMO' and drop['reason']=='group_close',
                'shared capture lifetime must cover both full views')
    m=e['metrics']
    require(m['nodes_allocated']==m['nodes_freed']==len(allocations) and m['ordinary_calls']==len(invokes)==2 and
            m['callback_calls']==len(actual_callbacks) and m['memo_writes']==len(select('memo_publish')) and
            m['groups_closed']==m['groups_allocated']==len(select('close_group')) and m['memo_fast_paths']>0,
            'event/allocator/operation census differs')
    return {'status':'passed','case':f['case'],'shared_node':c['node'],'bonus_node':b['node'],'bonus_result':bm['result'],
            'flag_node':flag['node'] if mixed else None,'body_nodes':[x['node'] for _,x in bodies],
            'body_envs':[x['env_id'] for _,x in bodies],'application_nodes':apps,'branches':branch_nodes,
            'root_code':info['root_code']['name'],'body_code':info['body_code']['name'],
            'source_use_vectors':[u['arguments'] for u in info['uses']], 'root_capture_owners':capture_owners,
            'body_capture_owners':body_owners,'lexical_imports':info['import_resource_facts'],
            'closed_entry':info['proof'],'normalization_steps':2 if mixed else 0,
            'events':len(events),'work':e['guard_work_used'],'guard_mask':e['guards_checked_mask'],'access_scope':ACCESS_SCOPE}


def copied_controls(evaluation,info):
    actual=observe(evaluation,info);rows=[]
    def event(r,name,predicate=lambda x:True):return next(x for x in r['events'] if x['event']==name and predicate(x))
    def reject(name,change):
        r=copy.deepcopy(evaluation);change(r)
        try:observe(r,info)
        except (AssertionError,KeyError,ValueError,IndexError):rows.append({'control':name,'status':'rejected'})
        else:raise AssertionError('copied report accepted: '+name)
    b=actual['bonus_node'];c=actual['shared_node'];body=actual['body_nodes'][0];v=actual['bonus_result']
    reject('wrong-result',lambda r:r['result'].__setitem__('value',41))
    reject('omitted-events',lambda r:r.__setitem__('events_omitted',1))
    reject('invented-project-coverage',lambda r:r.__setitem__('guards_checked_mask',r['guards_checked_mask']|(1<<4)))
    reject('live-ledger',lambda r:r['memory'].__setitem__('live_bytes',1))
    reject('bonus-relabelled-neutral',lambda r:event(r,'allocate',lambda x:x['node']==b).__setitem__('env_id',info['scheme']['neutral_env']))
    reject('eager-import',lambda r:event(r,'allocate',lambda x:x['node']==b).__setitem__('state','READY'))
    reject('deduplicated-lexical-slot',lambda r:event(r,'allocate',lambda x:x['node']==c)['slots'].pop(next(iter(info['root_captures'].values()))))
    reject('copied-capture-target',lambda r:event(r,'slot_install',lambda x:x['host']==c).__setitem__('target',v))
    reject('wrong-shared-principal-type',lambda r:event(r,'allocate',lambda x:x['node']==c).__setitem__('type_id',999999))
    reject('wrong-shared-scheme',lambda r:event(r,'allocate',lambda x:x['node']==c).__setitem__('scheme_id',999999))
    reject('pending-primitive-result',lambda r:event(r,'allocate',lambda x:x['node']==v).__setitem__('state','THUNK'))
    reject('wrong-allocation-opcode',lambda r:event(r,'allocate',lambda x:x['node']==v).__setitem__('opcode','scalar'))
    reject('wrong-allocation-output',lambda r:event(r,'allocate',lambda x:x['node']==v).__setitem__('out','missing'))
    reject('seal-wrong-node',lambda r:event(r,'generic_seal').__setitem__('node',b))
    reject('seal-pre-watermark-owner',lambda r:event(r,'generic_seal').__setitem__('owner',event(r,'generic_begin')['watermark']))
    reject('seal-invalid-access',lambda r:event(r,'generic_seal').__setitem__('old_access',len(info['meta']['accesses'])))
    def reuse_owner(r):
        xs=[x for x in r['events'] if x['event']=='instantiate'];xs[1]['owner']=xs[0]['owner']
    reject('reused-view-owner',reuse_owner)
    reject('owned-view-anchor',lambda r:event(r,'instantiate').__setitem__('anchor',1))
    reject('wrong-view-access',lambda r:event(r,'instantiate').__setitem__('new_access',event(r,'generic_seal')['old_access']))
    reject('wrong-function-code',lambda r:event(r,'frame_enter',lambda x:x['context']['kind']=='function')['context'].__setitem__('name','wrong'))
    reject('wrong-call-argument',lambda r:event(r,'invoke_enter').__setitem__('argument',v))
    reject('eager-body-return',lambda r:event(r,'invoke_raw_return').__setitem__('result',v))
    reject('neutral-body-env',lambda r:event(r,'allocate',lambda x:x['node']==body).__setitem__('env_id',info['scheme']['neutral_env']))
    reject('crossed-body-env',lambda r:event(r,'allocate',lambda x:x['node']==body).__setitem__('env_id',info['uses'][1]['env']))
    reject('wrong-body-code',lambda r:event(r,'allocate',lambda x:x['node']==body).__setitem__('code','wrong'))
    reject('wrong-body-capture',lambda r:event(r,'allocate',lambda x:x['node']==body)['slots'].__setitem__(next(iter(info['body_captures'].values())),v))
    def body_forces(r):
        fr=event(r,'frame_enter',lambda x:x['context'].get('node')==body)['frame']
        return [x for x in r['events'] if x['event']=='ir_force_result' and x['frame']==fr]
    reject('nonexistent-force-source',lambda r:body_forces(r)[0].__setitem__('source_variable','missing'))
    reject('nonexistent-force-output',lambda r:body_forces(r)[0].__setitem__('out','missing'))
    def alias_owners(r):
        h=event(r,'closure_capture_handoff')['owners'];keys=list(h);h[keys[1]]=h[keys[0]]
    reject('collapsed-capture-owners',alias_owners)
    reject('lost-body-owner',lambda r:event(r,'capture_handoff',lambda x:x['node']==body).__setitem__('owners',{}))
    reject('early-capture-retirement',lambda r:event(r,'slot_remove',lambda x:x['host']==c).__setitem__('reason','payload_clear'))
    reject('wrong-bonus-value',lambda r:event(r,'scalar_value',lambda x:x['node']==v).__setitem__('value',22))
    reject('wrong-bonus-memo',lambda r:event(r,'memo_publish',lambda x:x['destination']==b).__setitem__('result',b))
    def duplicate(r):
        r['events'].append(copy.deepcopy(event(r,'callback_enter',lambda x:x['node']==b)));r['events_emitted']=len(r['events'])
    reject('bonus-recomputed',duplicate)
    reject('wrong-application-memo',lambda r:event(r,'memo_publish',lambda x:x['destination']==actual['application_nodes'][0]).__setitem__('result',b))
    reject('missing-memo-reuse',lambda r:r['metrics'].__setitem__('memo_fast_paths',0))
    reject('wrong-call-census',lambda r:r['metrics'].__setitem__('ordinary_calls',1))
    if info['facts']['mixed']:
        flag=actual['flag_node'];yes=actual['branches'][0]['then'];no=actual['branches'][0]['else']
        reject('wrong-flag-dependency',lambda r:event(r,'allocate',lambda x:x['node']==flag).__setitem__('slots',{}))
        reject('wrong-condition-node',lambda r:event(r,'select_i64').__setitem__('condition_node',v))
        reject('false-condition',lambda r:event(r,'select_i64').__setitem__('condition_value',False))
        reject('unselected-result',lambda r:event(r,'select_i64').__setitem__('result',no))
        reject('wrong-branch-env',lambda r:event(r,'allocate',lambda x:x['node']==yes).__setitem__('env_id',0))
        reject('copied-selected-return',lambda r:event(r,'raw_return',lambda x:x['source']==yes).__setitem__('result',v))
        def enter_dead(r):
            extra=copy.deepcopy(event(r,'callback_enter',lambda x:x['node']==yes));extra['node']=no
            r['events'].append(extra);r['events_emitted']=len(r['events'])
        reject('dead-branch-executed',enter_dead)
    else:
        result=next(x['result'] for x in evaluation['events'] if x['event']=='raw_return' and x['source']==body)
        reject('wrong-instance-sum',lambda r:event(r,'scalar_value',lambda x:x['node']==result).__setitem__('value',10))
        reject('concrete-instance-result',lambda r:event(r,'allocate',lambda x:x['node']==result).__setitem__('env_id',0))
        reject('alias-force-copied-value',lambda r:event(r,'ir_force_result',lambda x:x['frame']==event(r,'allocate',lambda y:y['node']==result)['frame']).__setitem__('result',result))
        def duplicate_force_labels(r):
            xs=body_forces(r);xs[1]['out']=xs[0]['out'];xs[1]['source_variable']=xs[0]['source_variable']
        reject('duplicated-first-alias-force-labels',duplicate_force_labels)
    return rows


def run_case(args,output,env,case):
    require(QUALIFICATION_READY,'portable suite awaits actual trace qualification and review')
    inputs=output/'inputs';inputs.mkdir()
    for name,text in {'main.emlf':SOURCES[case],'SharedPoly.emlf':SHARED}.items():
        (inputs/name).write_text(text,encoding='utf-8')
    target=output/case
    build.run([sys.executable,'-B',str(BASE/'run_source_v8.py'),str(inputs/'main.emlf'),'--module-root',str(inputs),
               '--ghc',args.ghc,'--cc',args.cc,'--output',str(target)],output,case,cwd=BASE,env=env,
              wall=1200,cpu=900,memory=16<<30,termination_grace=15,stdout_limit=1<<20,stderr_limit=1<<20,file_limit=64<<20)
    require(not bounded_read(output/(case+'.stderr'),1<<20),'successful CLI stderr')
    result=read_json(target/'result.json');evaluation=read_json(target/'native/run.stdout')
    require(result['status']=='complete' and result['failure_policy']=='retain' and result['native']==evaluation and
            'placement' not in result,'fresh default CLI result differs')
    c=read_json(target/'capture.stdout');v=read_json(target/'verification.json');p=read_json(target/'planned.json',8<<20)
    require(p['binding']['mode']=='coarse-owned','default placement changed')
    generated=bounded_read(target/'native/ir8_runtime_generated.c',8<<20).decode();info=structure(c,v,p,generated,case)
    row={'status':'passed','observation':observe(evaluation,info),'report_controls':copied_controls(evaluation,info),
         'structure_controls':structure_controls(c,v,p,generated,case),'source_hashes':{
          'main.emlf':build.sha(SOURCES[case].encode()),'SharedPoly.emlf':build.sha(SHARED.encode())}}
    build.save(target/'generic-primitives-observations.json',row);print(case+': PASS',flush=True);return row


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ghc',required=True)
    parser.add_argument('--cc',default='cc');parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case',choices=('all',)+tuple(SOURCES),default='all');args=parser.parse_args()
    require(QUALIFICATION_READY,'portable suite awaits actual trace qualification and review')
    output=args.output.absolute();require(output.resolve()==output and output!=BASE.parents[2] and BASE.parents[2] not in output.parents,
            'fresh output must be outside checkout')
    output.mkdir(parents=True,exist_ok=False);env=cli.environment(output);build.SUITE_DEADLINE=time.monotonic()+1500;rows={}
    try:
        for case in SOURCES if args.case=='all' else (args.case,):
            child=output/case;child.mkdir();rows[case]=run_case(args,child,env,case)
    except BaseException as exc:
        try:build.save(output/'failure.json',{'error':repr(exc)})
        except BaseException as persistence:exc.add_note('Failure persistence also failed: '+repr(persistence))
        raise
    build.save(output/'results.json',{'status':'passed','cases':rows});return 0


if __name__=='__main__':raise SystemExit(main())
