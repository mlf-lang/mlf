#!/usr/bin/env python3
"""Two finite fresh-source recursion cases capturing admitted nominal arrows.

The original helper Reference, annotations and parameter coercions are retained.
Selectors come from normalized source and fresh planner/metadata correspondence,
not resolver hints or historical Code/node IDs. No per-owner Access trace exists.
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
from resource_ir_v8.metadata import check_metadata
from test_shared_source_native import at, instruction
from test_source_v8_recursive_sum import (one, walk, primitive, var, source_allocation,
    constructor_terms, closed_layout, SHARED, INT)
from test_source_v8_monomorphic_recursion import ledger, observe_fault_pair, fault_controls
from test_source_v8_callable_captures import read_json, address, spine, carrier_allocation
from test_source_v8_nominal_captures import passthrough, sum_case_structure

require = build.require
SOURCES = {
 'nominal-argument': ('import SharedPoly\ndata IntList = Nil | Cons Int IntList;\n'
  'let helper : IntList -> Int = \\ys -> case ys of { Nil -> 0; Cons n _ -> sharedId n } in\n'
  'let rec sumWith : IntList -> Int = \\xs -> case xs of { Nil -> 0; Cons _ rest -> addInt (addInt (helper xs) (helper xs)) (sumWith rest) } in\n'
  'let bonus = addInt 20 1 in\n'
  'if sharedId true then addInt (sumWith Nil) (sumWith (Cons bonus Nil)) else 0\n'),
 'nominal-result': ('import SharedPoly\ndata IntList = Nil | Cons Int IntList;\ndata Box = Box Int;\n'
  'let helper : Int -> Box = \\n -> Box (sharedId n) in\n'
  'let rec sumWith : IntList -> Int = \\xs -> case xs of { Nil -> 0; Cons n rest -> addInt (addInt (case helper n of { Box value -> value }) (case helper n of { Box value -> value })) (sumWith rest) } in\n'
  'let bonus = addInt 20 1 in\n'
  'if sharedId true then addInt (sumWith Nil) (sumWith (Cons bonus Nil)) else 0\n')}
ACCESS_SCOPE = ('The ordinary helper Reference retains its complete admitted nominal-arrow contract and support. '
 'Fresh metadata, generated code, actual acquired shared views, stored slots and guarded handoffs are joined; '
 'no event exposes every owner Access field. The concrete recursive host does not rebrand the captured '
 'generic origin. This finite observation is not general GC or performance acceptance.')


def parameter(node, path, typ, label):
    require(node['tag']=='lambda' and node['parameter_type']==typ, label+' lambda differs')
    local=node['body'];lp=path+['body']
    require(local['tag']=='let' and local['value']['tag']=='application' and
            var(local['value']['argument'],node['parameter']), label+' parameter application missing')
    passthrough(local['value']['function'],typ,label+' parameter')
    return local,lp+['body'],lp+['value','function']


def alternatives(case, scrutinee, label):
    require(case['tag']=='case' and case['result_type']==INT and var(case['scrutinee'],scrutinee) and
            len(case['alternatives'])==2,label+' exact Int case differs')
    nil=one([(i,a) for i,a in enumerate(case['alternatives']) if not a['pattern']['fields']],label+' Nil')
    cons=one([(i,a) for i,a in enumerate(case['alternatives']) if len(a['pattern']['fields'])==2],label+' Cons')
    require(nil[1]['body']=={'tag':'int64','value':0},label+' Nil result differs')
    return nil,cons


def source_facts(capture,name):
    require(name in SOURCES,'known nominal-callable fixture required')
    raw=capture['normalization']['raw_normalized']
    path,rec=one([(p,n) for p,n in walk(raw) if isinstance(n,dict) and n.get('tag')=='letrec'],'one recursion')
    binding=one(rec['bindings'],'one recursive binding');rhs_path=path+['bindings','0','value'];rhs=binding['value']
    typ=binding['type'];helper_let=at(raw,path[:-1]);helper_path=path[:-1]+['value']
    require(path[-1]=='body' and helper_let['tag']=='let','lexical helper binding differs')
    helper=helper_let['name'];helper_rhs=helper_let['value']
    require(helper_rhs['tag']=='application' and helper_rhs['argument']['tag']=='lambda',
            'helper must retain pending annotation around actual lambda')
    helper_type=helper_rhs['function']['parameter_type']
    require(helper_type['tag']=='arrow','complete ordinary helper arrow required')
    passthrough(helper_rhs['function'],helper_type,'helper annotation')
    hp=helper_path+['argument'];hf=helper_rhs['argument']
    hlocal,hbody,harg=parameter(hf,hp,helper_type['from'],'helper')
    require(typ['tag']=='arrow' and typ['to']==INT and rhs['tag']=='application','recursive annotation differs')
    passthrough(rhs['function'],typ,'recursive annotation');fn_path=rhs_path+['argument']
    local,case_path,arg_wrapper=parameter(rhs['argument'],fn_path,typ['from'],'recursive')
    case=local['body'];nil,cons=alternatives(case,local['name'],'recursive')
    cp=case_path+['alternatives',str(cons[0]),'body'];add,_,args=spine(cons[1]['body'],cp)
    require(add['tag']=='primitive' and add['name']=='addInt' and len(args)==2,'recursive addition differs')
    pair_path,pair=args[0];self_path,self_call=args[1];add,_,pair_args=spine(pair,pair_path)
    require(add['tag']=='primitive' and add['name']=='addInt' and len(pair_args)==2,'two helper results required')
    fields=cons[1]['pattern']['fields']
    require(fields[1] is not None and self_call['tag']=='application' and
            var(self_call['function'],binding['name']) and var(self_call['argument'],fields[1]),'self must consume exact tail')
    calls=[];data_cases=[];helper_case=None;box_path=None
    if name=='nominal-argument':
        require(helper_type==typ and fields[0] is None,'nominal-argument full type/wildcard differs')
        helper_case=hlocal['body'];hn,hc=alternatives(helper_case,hlocal['name'],'helper')
        require(hc[1]['pattern']['fields'][0] is not None and hc[1]['pattern']['fields'][1] is None,
                'helper must bind head and ignore tail')
        int_call_path=hbody+['alternatives',str(hc[0]),'body'];int_call=hc[1]['body']
        require(int_call['tag']=='application' and int_call['function']['tag']=='type_application' and
                var(int_call['argument'],hc[1]['pattern']['fields'][0]),'helper shared Int must receive original head')
        for p,n in pair_args:
            require(n['tag']=='application' and var(n['function'],helper) and var(n['argument'],local['name']),
                    'both helper calls must receive same original recursive parameter')
            calls.append(p)
    else:
        require(helper_type['from']==INT and helper_type['to']['tag']=='constructor' and
                not helper_type['to']['arguments'] and helper_type['to']['name'] not in ('Int','Bool') and
                fields[0] is not None,'nominal-result full arrow/field differs')
        box_path=hbody;head,_,box_args=spine(hlocal['body'],hbody)
        require(head['tag']=='constructor' and not head['arguments'] and len(box_args)==1,
                'helper must allocate one concrete Box with one pending field')
        int_call_path,int_call=box_args[0]
        require(int_call['tag']=='application' and int_call['function']['tag']=='type_application' and
                var(int_call['argument'],hlocal['name']),'Box field must retain shared Int application')
        for p,n in pair_args:
            require(n['tag']=='case' and n['result_type']==INT and len(n['alternatives'])==1,
                    'each returned Box must be projected by its own Int case')
            arm=n['alternatives'][0];fs=arm['pattern']['fields'];call=n['scrutinee']
            require(arm['pattern']['constructor']==head['name'] and len(fs)==1 and fs[0] is not None and
                    var(arm['body'],fs[0]) and call['tag']=='application' and var(call['function'],helper) and
                    var(call['argument'],fields[0]),'returned Box projection/helper argument differs')
            data_cases.append((p,n));calls.append(p+['scrutinee'])
    continuation=rec['body'];bonus_path=path+['body','value']
    require(continuation['tag']=='let' and primitive(continuation['value'],20,1),
            'bonus must remain pending in the continuation, not captured by recursion')
    branch_path=path+['body','body'];branch,_,ba=spine(continuation['body'],branch_path)
    require(branch['tag']=='primitive' and branch['name']=='ifThenElse' and len(ba)==3 and
            ba[2][1]=={'tag':'int64','value':0},'outer branch differs')
    bp,bc=ba[0]
    require(bc['tag']=='application' and bc['function']['tag']=='type_application' and
            bc['argument']=={'tag':'bool','value':True},'shared Bool condition differs')
    root_path,root=ba[1];add,_,ra=spine(root,root_path)
    require(add['tag']=='primitive' and add['name']=='addInt' and len(ra)==2 and all(
        n['tag']=='application' and var(n['function'],binding['name']) for _,n in ra), 'main must call initial Nil then one Cons')
    first=ra[0][1]['argument'];head,_,ca=spine(ra[1][1]['argument'],ra[1][0]+['argument'])
    require(first['tag']=='constructor' and not first['arguments'] and head['tag']=='constructor' and len(ca)==2 and
            var(ca[0][1],continuation['name']) and ca[1][1]==first and
            first['name']==nil[1]['pattern']['constructor'] and head['name']==cons[1]['pattern']['constructor'],
            'actual finite Nil/Cons bonus/Nil graph differs')
    return dict(name=name,raw=raw,path=path,binding=binding,rhs=rhs_path,function=fn_path,
        argument_wrapper=arg_wrapper,case=case,case_path=case_path,nil=nil,cons=cons,cons_path=cp,
        pair_add=pair_path,self_call=self_path,helper=helper,helper_type=helper_type,helper_path=helper_path,
        helper_function=hp,helper_argument_wrapper=harg,helper_body=hbody,helper_case=helper_case,
        helper_calls=calls,data_cases=data_cases,box_path=box_path,int_call=int_call_path,int_view=int_call_path+['function'],
        bonus=continuation['name'],bonus_path=bonus_path,bool_call=bp,root_add=root_path,
        first_call=ra[0][0],second_call=ra[1][0],tail_path=ca[1][0])


def structure(capture,plan,generated,name):
    f=source_facts(capture,name);p,m=plan['program'],plan['binding']['source_map']
    knot=one(m['knot_map'],'one exact knot');binding=f['binding']
    require(knot['source']==address(f['path']) and knot['binding_source']==address(f['path']+['bindings','0']) and
            knot['binder']==binding['name'] and knot['rhs']==address(f['rhs']) and knot['type_scope'] is None and
            knot['function_source']==address(f['function']) and knot['self_uses']==[address(f['self_call']+['function'])],
            'recursive source/knot correspondence differs')
    hole,fill=instruction(p,knot['hole']),instruction(p,knot['fill'])
    require(hole=={'op':'hole','out':knot['hole_owner'],'in':knot['home'],'layout':'^'+knot['logical_type']} and
            fill=={'op':'fill','hole':knot['hole_owner'],'value':knot['rhs_owner']} and
            instruction(p,knot['retain_self'])=={'op':'retain','out':knot['self_owner'],'value':knot['hole_owner']},
            'original hole/Fill/self ownership differs')
    for key,value in (('drop_rhs',knot['rhs_owner']),('drop_self',knot['self_owner']),('drop_hole',knot['hole_owner'])):
        require(instruction(p,knot[key])=={'op':'drop','value':value},'knot release differs')
    alloc=lambda path,kind:source_allocation(plan,path,kind)
    closure=alloc(f['function'],'closure');rhs=alloc(f['rhs'],'application');wrapper=alloc(f['rhs']+['function'],'closure')
    helper=alloc(f['helper_path'],'application');hc=alloc(f['helper_function'],'closure');hw=alloc(f['helper_path']+['function'],'closure')
    require(rhs['out']==knot['rhs_owner'] and rhs['function']==wrapper['out'] and rhs['argument']==closure['out'] and
            helper['function']==hw['out'] and helper['argument']==hc['out'],'pending original annotation graph differs')
    carrier=one([c for c in m['carrier_map'] if c['source']==address(f['function'])],'recursive carrier')
    mono=carrier['mono_captures'];self_cap=one([c for c in mono if c['binder']==binding['name']['id']],'self capture')
    helper_cap=one([c for c in mono if c['binder']==f['helper']['id']],'helper capture')
    require(len(mono)==2 and not carrier['view_captures'] and carrier['type_scope'] is None and
            carrier['ir_code']==closure['function'] and self_cap['layout']=='^'+knot['logical_type'] and
            self_cap['relation']=='down' and closure['captures']=={self_cap['capture']:knot['self_owner'],helper_cap['capture']:helper['out']},
            'recursive must capture exact self and ordinary helper only')
    require(knot['captures']=={'policy':'closed-admitted-callable-shared-view-captures/1','scalars':[],
        'callables':[{'binding':f['helper'],'type':f['helper_type'],
                     'occurrences':[address(path+['function']) for path in f['helper_calls']]}], 'nominals':[], 'views':[]},
        'exact nominal callable capture inventory differs')
    family=one(m['sum_map'],'one exact recursive SUM');physical='%'+family['family']
    require(family['name']==binding['type']['from']['name'] and
            p['families'][family['family']]=={'variants':['V0','V1'],'fields':{'V0':[],'V1':['#i64',physical]}},
            'exact recursive nominal family differs')
    arrow=p['types'][helper_cap['layout'][1:]]
    box=one(m['nominal_map'],'one exact Box') if name=='nominal-result' else None
    expected=(physical,'#i64') if box is None else ('#i64',box['layout'])
    require(helper_cap['layout'].startswith('^') and set(arrow)=={'tag','argument','result','protocol','result_identity'} and
            arrow['tag']=='arrow' and arrow['protocol']=='repeat' and arrow['result_identity']=='unknown' and
            (closed_layout(p,'^'+arrow['argument']),closed_layout(p,'^'+arrow['result']))==expected,
            'ordinary nominal arrow must retain full unknown-Code contract')
    for c in m['carrier_map']:
        for row in c['mono_captures']:
            if row['binder']==f['helper']['id']:require(row['layout']==helper_cap['layout'],'downstream helper type changed')
    for row in mono:
        require(p['functions'][closure['function']]['captures'][row['capture']]==
                {'layout':row['layout'],'relation':row['relation']},'capture support/layout differs')
    helper_carrier=one([c for c in m['carrier_map'] if c['source']==address(f['helper_function'])],'helper carrier')
    view=one(helper_carrier['view_captures'],'helper full Int view')
    require(not helper_carrier['mono_captures'] and helper_carrier['type_scope'] is None and
            helper_carrier['ir_code']==hc['function'] and set(hc['captures'])=={view['capture']},'helper captures must be full Int view only')
    rec_case,arms=sum_case_structure(plan,f['case'],f['case_path'],family)
    helper_case=helper_arms=None
    if f['helper_case'] is not None:helper_case,helper_arms=sum_case_structure(plan,f['helper_case'],f['helper_body'],family)
    constructors=[]
    for path in (f['first_call']+['argument'],f['second_call']+['argument'],f['tail_path']):
        row=one([r for r in m['sum_constructor_map'] if r['source']==address(path)],'exact finite constructor')
        head,args=constructor_terms(f['raw'],row);op=instruction(p,row['allocation'])
        require(row['declaration']==family['declaration'] and head['name']==family['variants'][row['variant']]['constructor'] and
                op==alloc(path,'construct_sum' if args else 'construct_nullary'),'constructor source/variant differs')
        constructors.append(op)
    require(len(m['sum_constructor_map'])==3 and [x['op'] for x in constructors]==['construct_nullary','construct_sum','construct_nullary'],
            'only exact three list constructors allowed')
    bonus=alloc(f['bonus_path'],'thunk')
    root_carrier=one([c for c in m['carrier_map'] if c['source']==address(f['root_add']) and c['kind']=='primitive'],
                     'root addition carrier')
    bonus_capture=one([c for c in root_carrier['mono_captures'] if c['binder']==f['bonus']['id']],'root original bonus capture')
    bonus_retain=one([row for row in p['codes'][root_carrier['ir_code']]['body'] if
                     row.get('out')==constructors[1]['fields'][0]],'constructor pending bonus retain')
    require(bonus_retain=={'op':'retain','out':constructors[1]['fields'][0],'value':bonus_capture['capture']} and
            closed_layout(p,bonus_capture['layout'])=='#i64' and constructors[1]['fields'][1]==constructors[2]['out'],
            'Cons keeps original pending bonus')
    cases=[];box_op=None
    if box is not None:
        require(box['name']==f['helper_type']['to']['name'],'Box nominal identity differs')
        row=one(m['constructor_map'],'one static Box allocation');box_op=instruction(p,row['allocation'])
        require(row['source']==address(f['box_path']) and row['declaration']==box['declaration'] and
                box_op['op']=='alloc' and box_op['layout']==box['layout'] and
                box_op['fields']=={'f0':alloc(f['int_call'],'application')['out']},'Box must keep pending shared field')
        for path,node in f['data_cases']:
            c=one([r for r in m['case_map'] if r['source']==address(path)],'exact returned Box case')
            projection=one(c['projections'],'one Box field');loan,retain,end=[instruction(p,projection[k]) for k in ('loan','retain','end_borrow')]
            require(c['declaration']==box['declaration'] and projection['index']==0 and
                    projection['binder']==node['alternatives'][0]['pattern']['fields'][0]['id'] and
                    loan['op']=='field' and loan['field']=='f0' and retain['op']=='retain' and retain['value']==loan['out'] and
                    end=={'op':'end_borrow','value':loan['out']} and
                    instruction(p,c['drop_container'])=={'op':'drop','value':loan['value']},'Box borrow/retain/end/drop differs')
            paths=[projection[k] for k in ('loan','retain','end_borrow')]+[c['drop_container']]
            require(all(x['root']=='thunk' and x['name']==c['code'] and len(x['segments'])==1 for x in paths) and
                    [x['segments'][0] for x in paths[:3]]==list(range(paths[0]['segments'][0],paths[0]['segments'][0]+3)) and
                    paths[3]['segments'][0]>paths[2]['segments'][0],'Box field lifetime order differs')
            cases.append(c)
        pattern=r'(?P<h>h\d+) = rt8_field\(ctx, h\d+, 0, p\d+, p\d+\);\n    h\d+ = rt8_retain\(ctx, (?P=h)\);\n    rt8_end_borrow\(ctx, (?P=h)\);'
        require(len(re.findall(pattern,generated))==generated.count('= rt8_field(')==2,'generated Box ownership order differs')
    meta=json.loads(check_metadata(p).metadata_json)
    code=one([c for c in meta['codes'] if c['kind']=='function' and c['name']==closure['function']],'recursive Code')
    definitions=[int(x) for x in re.findall(r'static Rt8Handle \*rt8_body_(\d+)\(',generated)]
    registrations=[(int(a),int(b)) for a,b in re.findall(r'\{ \.code_id = (\d+), \.body = rt8_body_(\d+) \}',generated)]
    require(definitions==list(range(len(meta['codes']))) and registrations==[(i,i) for i in definitions] and
            generated.count('rt8_fill(ctx,')==generated.count(' = rt8_hole(ctx,')==1,'real Code/knot generated census differs')
    return dict(facts=f,knot=knot,hole=hole,fill=fill,rhs=rhs,closure=closure,wrapper=wrapper,bonus=bonus,
        helper=helper,helper_closure=hc,helper_wrapper=hw,helper_view=view,callable_layout=helper_cap['layout'],
        self_capture=self_cap['capture'],callable_capture=helper_cap['capture'],code=closure['function'],code_id=code['id'],
        metadata=meta,family=physical,rec_case=rec_case,arms=arms,helper_case=helper_case,helper_arms=helper_arms,
        constructors=constructors,box=box_op,data_cases=cases,
        argument_wrapper=alloc(f['argument_wrapper'],'closure'),helper_argument_wrapper=alloc(f['helper_argument_wrapper'],'closure'),
        argument_application=alloc(f['argument_wrapper'][:-1],'application'),
        helper_argument_application=alloc(f['helper_argument_wrapper'][:-1],'application'),
        helper_body_thunk=carrier_allocation(plan,f['helper_body'],'sum-case') if helper_case is not None else None,
        helper_calls=[alloc(path,'application') for path in f['helper_calls']],int_call=alloc(f['int_call'],'application'),
        self_call=alloc(f['self_call'],'application'),first_call=alloc(f['first_call'],'application'),
        second_call=alloc(f['second_call'],'application'),bool_call=alloc(f['bool_call'],'application'),
        root_add=carrier_allocation(plan,f['root_add'],'primitive'),cons_add=alloc(f['cons_path'],'thunk'),pair_add=alloc(f['pair_add'],'thunk'))


def shared_graph(plan,verified,capture,info):
    p,m,meta=plan['program'],plan['binding']['source_map'],info['metadata'];uses={}
    scheme=one(m['scheme_map'],'shared Scheme');definition=one(verified['fragment']['definitions'],'shared definition')
    require(scheme['binder']==definition['binding']['id'] and len(p['schemes'])==1 and
            p['schemes'][scheme['scheme']]['parameters']==1 and
            len(m['use_map'])==len(verified['fragment']['uses'])==len(p['instantiations'])==2,'shared definition/full prefix census differs')
    generic,seal=instruction(p,scheme['generalize']),instruction(p,scheme['seal'])
    pending=one([x for x in generic['body'] if x['op']=='application'],'one pending shared RHS')
    closures={x['out']:x['function'] for x in generic['body'] if x['op']=='closure'}
    cursor=at(info['facts']['raw'],scheme['rhs_cursor']['path'])
    require(cursor['tag']=='application' and cursor['function']['tag']==cursor['argument']['tag']=='lambda' and
            pending['out']==seal['value'] and not any(x['op']=='force' for x in generic['body']),'shared RHS became eager or substituted')
    carriers=[c for c in m['carrier_map'] if c['kind']=='lambda']
    source_lambdas=[path for path,node in walk(info['facts']['raw']['body'],['body']) if isinstance(node,dict) and node.get('tag')=='lambda']
    require(sorted(c['source']['path'] for c in carriers)==sorted(source_lambdas) and len(carriers)==len(p['functions']),
            'ordinary source lambda census differs')
    for variable,child in ((pending['function'],'function'),(pending['argument'],'argument')):
        c=one([c for c in carriers if c['source']['path']==scheme['rhs_cursor']['path']+[child]],'shared source lambda')
        require(c['ir_code']==closures[variable] and c['type_scope']==scheme['scheme'],'shared lambda Code/scope differs')
    graph={'outer_code':closures[pending['function']],'shared_code':closures[pending['argument']],'seal_owner':seal['value']}
    for atom,path in (('#bool',info['facts']['bool_call']+['function']),('#i64',info['facts']['int_view'])):
        source=one([r for r in m['use_map'] if r['source']==address(path)],'exact shared source Use')
        require([p['types'][t]['layout'] for t in source['arguments']]==[atom] and source['definition']==definition['id'],'full shared vector differs')
        name=one([n for n,r in p['instantiations'].items() if r['scheme']==scheme['scheme'] and
                  r['arguments']==source['arguments']],'actual full instantiation')
        row=one([r for r in meta['uses'] if r['name']==name],'actual Use metadata')
        require(len(row['occurrences'])==1 and row['occurrences'][0]['root']=='entry','view must be acquired once in entry')
        op=instruction(p,row['occurrences'][0]);typ=meta['types'][row['result_type']]
        require(op['op']=='instantiate' and op['instantiation']==name and typ['tag']=='arrow' and
                meta['types'][typ['argument']]['atom']==meta['types'][typ['result']]['atom']==atom and
                typ['protocol']=='repeat' and typ['result_identity']=='unknown','complete shared contract differs')
        uses[atom]={'source':source,'row':row,'operation':op}
    view=info['helper_view'];u=uses['#i64']
    require(view['definition']==u['source']['definition'] and view['occurrences']==[u['source']['use']] and
            [p['types'][t]['layout'] for t in view['arguments']]==['#i64'] and
            info['helper_closure']['captures'][view['capture']]==u['operation']['out'] and
            u['source']['source_view']['kind']=='captured','helper must retain genuine upstream full Int view')
    for table in ('functions','codes'):
        for row in p[table].values():
            require(not any(isinstance(n,dict) and n.get('op')=='instantiate' for _,n in walk(row['body'])),
                    'callback-local instantiate is forbidden')
    require(meta['codes'][info['code_id']]['scope'] is None,'recursive host must remain concrete')
    ap=scheme['rhs_cursor']['path']+['argument','body','value'];raw=info['facts']['raw'];arg=at(raw,ap)
    sf=at(raw,scheme['rhs_cursor']['path']+['argument'])
    require(arg['tag']=='application' and var(arg['argument'],sf['parameter']) and
            var(arg['function']['body'],arg['function']['parameter']) and var(sf['body']['body'],sf['body']['name']),
            'shared ordinary parameter wrapper differs')
    graph.update(uses=uses,scheme=scheme,parameter_wrapper=source_allocation(plan,ap+['function'],'closure'),
                 parameter_application=source_allocation(plan,ap,'application'))
    return graph


def observe(e,info,graph):
    require(e['schema']=='resource-ir-v8-run/1' and e['state']==e['fault']==0 and
            e['result']=={'kind':'i64','value':42} and e['scalar_result_kind']==1 and e['scalar_result']==42 and
            e['events_omitted']==0 and e['events_emitted']==len(e['events']),'complete native Int42 report required')
    require(e['guards_failed_mask']==0 and e['guards_checked_mask']==(1<<27)-1 and
            e['guard_work_limit']==67_108_864 and 0<e['guard_work_used']<=e['guard_work_limit'],'native guard/work contract differs')
    ledger(e,True);events=e['events'];sel=lambda kind:[(i,x) for i,x in enumerate(events) if x['event']==kind]
    allocations=sel('allocate');nodes={x['node']:x for _,x in allocations}
    require(len(nodes)==len(allocations),'duplicate node identity')
    def allocations_for(op):
        found=[(i,x) for i,x in allocations if x['out']==op['out']]
        require(all(x['opcode']==op['op'] and x['code']==(op['function'] if op['op']=='closure' else op.get('code')) for _,x in found),
                'source allocation Code/opcode differs')
        return found
    def alloc(op):return one(allocations_for(op),'one source allocation')
    def memo(node):return one([(i,x) for i,x in sel('memo_publish') if x['destination']==node],'one exact memo')
    def demand(node):return one([(i,x) for i,x in sel('update_pin') if x['node']==node],'one exact demand')
    def invokes(node):return [(i,x) for i,x in sel('invoke_enter') if x['closure']==node]
    def raw_returns(node):return [(i,x) for i,x in sel('invoke_raw_return') if x['closure']==node]
    def frames(node,code):
        found=[(i,x) for i,x in sel('frame_enter') if x['context'].get('name')==code]
        require(all(x['context'].get('node')==node for _,x in found),'registered callback source differs')
        return found
    def wrappers(op,arguments):
        found=allocations_for(op);require(len(found)==len(arguments),'parameter wrapper census differs')
        for (_,node),argument in zip(found,arguments):
            i,call=one(invokes(node['node']),'parameter wrapper invocation')
            j,ret=one(raw_returns(node['node']),'parameter wrapper raw return')
            require(i<j and call['argument']==ret['argument']==ret['result']==argument,'parameter wrapper changed original owner')
        return found
    def memo_slot(node,result,after):
        j,row=memo(node)
        require(row['result']==result and j>after,'memo changed exact result')
        i,_=one([(i,x) for i,x in sel('slot_install') if x['host']==node and x['field']=='$target' and x['target']==result],
                'memo exact target slot')
        require(after<i<j,'memo target publication order differs')
        return j
    scalars={x['node']:(x['kind'],x['value']) for _,x in sel('scalar_value')}
    scalar_events={x['node']:i for i,x in sel('scalar_value')}
    _,hole=alloc(info['hole']);_,closure=alloc(info['closure']);_,wrapper=alloc(info['wrapper']);_,rhs=alloc(info['rhs'])
    helper_i,helper=alloc(info['helper']);_,helper_closure=alloc(info['helper_closure']);_,helper_wrapper=alloc(info['helper_wrapper'])
    bonus_i,bonus=alloc(info['bonus']);fill_i,fill=one(sel('fill'),'one Fill')
    require(hole['state']=='HOLE' and rhs['state']==helper['state']=='APPLICATION' and bonus['state']=='THUNK' and
            rhs['slots']=={'$function':wrapper['node'],'$argument':closure['node']} and
            closure['slots']=={info['self_capture']:hole['node'],info['callable_capture']:helper['node']} and
            helper['slots']=={'$function':helper_wrapper['node'],'$argument':helper_closure['node']},
            'original recursive/helper Reference graph differs')
    require(fill['hole']==hole['node'] and fill['target']==rhs['node'] and
            fill['hole_variable']==info['fill']['hole'] and fill['value_variable']==info['fill']['value'],
            'original Fill target/ticket differs')
    edge_i,_=one([(i,x) for i,x in sel('slot_install') if x['host']==hole['node'] and x['field']=='$target' and x['target']==rhs['node']],
                'original Fill edge')
    require(edge_i<fill_i<bonus_i and not any(i<fill_i and x['node'] in (hole['node'],rhs['node']) for i,x in sel('update_pin')),
            'continuation bonus or knot demand moved before Fill')
    wi,wcall=one(invokes(wrapper['node']),'recursive annotation invoked once');rm,rr=memo(rhs['node'])
    require(fill_i<wi<rm and wcall['argument']==rr['result']==closure['node'],'recursive annotation wrapper differs')
    constructors=[alloc(op)[1] for op in info['constructors']];first,cons,last=constructors
    require(not first['slots'] and not last['slots'] and cons['slots']=={'0':bonus['node'],'1':last['node']},
            'same original Cons/bonus/tail graph differs')
    values=sel('sum_value');require(len(values)==3,'SUM constructor census differs')
    for node,variant in zip(constructors,(0,1,0)):
        _,value=one([(i,x) for i,x in values if x['node']==node['node']],'one SUM value')
        require(value['family']==node['layout']==info['family'] and value['variant_index']==variant and value['variant']=='V'+str(variant),
                'SUM exact nominal identity differs')
    calls=invokes(closure['node']);rf=frames(closure['node'],info['code'])
    require(len(calls)==len(rf)==3 and [x['argument'] for _,x in calls]==[n['node'] for n in constructors] and
            len({x['frame'] for _,x in rf})==3 and sum(x['code']==info['code'] for _,x in allocations)==1,
            'one recursive closure must invoke Nil/Cons/Nil')
    handoffs=[(i,x) for i,x in sel('closure_capture_handoff') if x['node']==closure['node']]
    require(len(handoffs)==3 and all(set(x['owners'])==set(closure['slots']) and x['protocol']=='repeat' for _,x in handoffs) and
            len({v for _,x in handoffs for v in x['owners'].values()})==6 and
            all(h[0]<c[0]<f[0] for h,c,f in zip(handoffs,calls,rf)),'three distinct complete capture handoffs differ')
    recursive_wrappers=wrappers(info['argument_wrapper'],[n['node'] for n in constructors])
    recursive_parameters=allocations_for(info['argument_application'])
    require(len(recursive_parameters)==3 and all(x['slots']=={'$function':w['node'],'$argument':n['node']} and
            memo(x['node'])[1]['result']==n['node'] for (_,x),(_,w),n in zip(recursive_parameters,recursive_wrappers,constructors)),
            'recursive parameter application must memo exact original owner')
    self_app=one(allocations_for(info['self_call']),'one self-tail application')[1]
    require(self_app['slots']=={'$function':hole['node'],'$argument':last['node']},'same self must receive original tail')
    _,first_app=alloc(info['first_call']);_,second_app=alloc(info['second_call'])
    require(first_app['slots']=={'$function':hole['node'],'$argument':first['node']} and
            second_app['slots']=={'$function':hole['node'],'$argument':cons['node']},'outer recursive arguments differ')
    first_done,first_memo=memo(first_app['node'])
    require(calls[0][0]<first_done<calls[1][0] and scalars.get(first_memo['result'])==('i64',0),'initial Nil must finish first')
    factories=sel('case_fields_i64');selected=[]
    for case_map,arms,scrutinees in ((info['rec_case'],info['arms'],constructors),
            (info['helper_case'],info['helper_arms'],[cons,cons])):
        if case_map is None:continue
        found=[(i,x) for i,x in factories if x['code'] in {a['code'] for a in arms.values()}]
        require(len(found)==len(scrutinees),'selected factory census differs')
        for (i,x),node in zip(found,scrutinees):
            variant=1 if node['slots'] else 0;arm=arms[variant];target=nodes[x['result']]
            require(x['scrutinee']==node['node'] and x['family']==info['family'] and x['variant_index']==variant and
                    x['variant']=='V'+str(variant) and x['code']==target['code']==arm['code'] and
                    target['opcode']=='case_fields_i64' and target['slots']==x['captures'] and
                    x['field_indices']=={c['capture']:c['index'] for c in arm['field_captures']} and
                    x['field_mask']==sum(1<<c['index'] for c in arm['field_captures']),'selected factory original source differs')
            cb,_=one([(j,y) for j,y in sel('callback_enter') if y['node']==x['result']],'selected callback once')
            require(i<cb,'selected callback publication order differs')
            for c in arm['field_captures']:
                require(x['captures'][c['capture']]==node['slots'][str(c['index'])],'factory field lost original owner')
                fields=[(j,y) for j,y in sel('sum_field_capture') if y['frame']==x['frame'] and y['capture']==c['capture']]
                j,y=one(fields,'exact selected field capture')
                require(j<i and y['scrutinee']==node['node'] and y['field_index']==c['index'] and
                        y['node']==node['slots'][str(c['index'])] and y['family']==info['family'],
                        'selected field trace lost original owner')
            selected.append(x['result'])
    require(len(selected)==len(factories) and len(set(selected))==len(selected),'extra/unselected factory entered')
    begin_i,_=one(sel('generic_begin'),'one generic RHS');seal_i,seal=one(sel('generic_seal'),'one generic seal')
    shared=seal['node'];pending=nodes[shared];body=pending['slots']['$argument'];outer=pending['slots']['$function']
    require(begin_i<seal_i and pending['state']=='APPLICATION' and pending['out']==graph['seal_owner'] and
            nodes[body]['code']==graph['shared_code'] and nodes[outer]['code']==graph['outer_code'] and
            sum(x['code']==graph['shared_code'] for _,x in allocations)==1,'one original shared RHS/body differs')
    require(memo(shared)[1]['result']==body and len(invokes(outer))==1,'shared RHS evaluated more than once')
    entry=one([x for _,x in sel('frame_enter') if x['context']['kind']=='entry'],'entry frame')['frame']
    uses=sel('instantiate');require(len(uses)==2,'shared full-view acquisition census differs');observed={};meta=info['metadata']
    for atom,wanted in graph['uses'].items():
        i,x=one([(i,x) for i,x in uses if x['use']==wanted['row']['id']],'exact full Use')
        before,after=meta['accesses'][x['old_access']],meta['accesses'][x['new_access']]
        require(x['node']==shared and x['frame']==entry and x['mode']=='own' and x['anchor'] is None and
                before['mode']=='SCHEME' and after['mode']=='MONO' and before['site']==after['site']==pending['site_id'] and
                before['origin_env']==after['origin_env']==pending['env_id']!=0 and
                meta['environments'][after['origin_env']]['mode']=='NEUTRAL' and
                after['use_env']==wanted['row']['env'] and after['type']==wanted['row']['result_type'] and
                after['scheme'] is None and meta['environments'][after['use_env']]['mode']=='CLOSED',
                'full shared Access/origin/capsule differs')
        observed[atom]={'event_index':i,'origin_env':after['origin_env'],'use_env':after['use_env'],'access':after['id'],'type':after['type']}
    require(observed['#i64']['event_index']<helper_i and closure['env_id']==helper_closure['env_id']==0 and
            helper_closure['slots']=={info['helper_view']['capture']:shared},'helper full view storage differs')
    hd,_=demand(helper['node']);hm,hmem=memo(helper['node']);hwi,hwcall=one(invokes(helper_wrapper['node']),'helper annotation once')
    require(first_done<hd<hwi<hm and hwcall['argument']==hmem['result']==helper_closure['node'],
            'initial Nil demanded helper or annotation lost callable')
    hc=invokes(helper_closure['node']);hframes=frames(helper_closure['node'],info['helper_closure']['function'])
    hreturns=raw_returns(helper_closure['node']);apps=[alloc(op) for op in info['helper_calls']]
    argument=recursive_parameters[1][1]['node'] if info['facts']['name']=='nominal-argument' else bonus['node']
    require(len(hc)==len(hframes)==len(hreturns)==2 and hm<hc[0][0] and all(x['argument']==argument for _,x in hc) and
            len({x['node'] for _,x in apps})==2 and all(x['state']=='APPLICATION' and
                x['slots']=={'$function':helper['node'],'$argument':argument} and i>first_done for i,x in apps),
            'two helper calls must preserve same original argument/Reference')
    wrappers(info['helper_argument_wrapper'],[argument,argument])
    hpapps=allocations_for(info['helper_argument_application'])
    require(len(hpapps)==2 and all(x['slots']['$argument']==argument for _,x in hpapps),'helper parameter owner differs')
    if info['facts']['name']=='nominal-argument':
        require(memo(argument)[0]<hc[0][0] and all(memo(x['node'])[1]['result']==cons['node'] for _,x in hpapps),
                'helper coercions must follow same memoized original Cons owner')
    hh=[x for _,x in sel('closure_capture_handoff') if x['node']==helper_closure['node']]
    require(len(hh)==2 and all(set(x['owners'])==set(helper_closure['slots']) for x in hh) and
            len({v for x in hh for v in x['owners'].values()})==2,'helper complete full-view handoffs differ')
    shared_calls=invokes(body);sf=frames(body,graph['shared_code'])
    require(len(shared_calls)==len(sf)==3 and scalars.get(shared_calls[0][1]['argument'])==('bool',True) and
            shared_calls[0][0]<calls[0][0]<first_done<shared_calls[1][0]<shared_calls[2][0],
            'shared callback must run Bool/Int/Int after initial Nil')
    int_apps=allocations_for(info['int_call'])
    expected_args=[bonus['node'],bonus['node']] if info['facts']['name']=='nominal-argument' else [x['node'] for _,x in hpapps]
    require(len(int_apps)==2 and [x['argument'] for _,x in shared_calls[1:]]==expected_args and all(
        x['state']=='APPLICATION' and x['slots']=={'$function':shared,'$argument':arg} for (_,x),arg in zip(int_apps,expected_args)),
        'shared Int must receive exact original helper field/parameter owner')
    demand_i,_=demand(bonus['node']);cb_i,_=one([(i,x) for i,x in sel('callback_enter') if x['node']==bonus['node']],'bonus callback once')
    bm,bmem=memo(bonus['node']);scalar=bmem['result']
    require(first_done<shared_calls[1][0]<demand_i<cb_i<scalar_events.get(scalar,-1)<bm and scalars.get(scalar)==('i64',21),
            'bonus must evaluate once after first shared Int call')
    # Shared identity returns its ordinary parameter APPLICATION. Force then
    # follows the original owner chain; memo publication order is not evaluation order.
    sw=wrappers(graph['parameter_wrapper'],[x['argument'] for _,x in shared_calls])
    spa=allocations_for(graph['parameter_application']);sr=raw_returns(body)
    require(len(spa)==len(sr)==3,'shared parameter application census differs')
    for (_,app),(_,wrapper_node),(call_i,call),(ret_i,ret) in zip(spa,sw,shared_calls,sr):
        require(app['slots']=={'$function':wrapper_node['node'],'$argument':call['argument']} and
                call_i<ret_i and ret['argument']==call['argument'] and ret['result']==app['node'],
                'shared identity raw-return owner chain differs')
    for (_,app) in int_apps:
        memo_slot(app['node'],scalar,scalar_events[scalar])
    detail={}
    if info['box'] is None:
        case_nodes=allocations_for(info['helper_body_thunk'])
        require(len(case_nodes)==2,'two original helper case thunks required')
        for (_,app),(ret_i,returned),(_,case_node),(_,parameter_app) in zip(apps,hreturns,case_nodes,hpapps):
            require(returned['result']==case_node['node'] and nodes[returned['result']]['state']=='THUNK' and
                    demand(parameter_app['node'])[0]>ret_i,
                    'helper must return genuine pending case before coercion demand')
            memo_slot(app['node'],scalar,scalar_events[scalar])
        detail['same_sum_argument_reference']=argument
        detail['original_sum_owner']=cons['node']
    else:
        boxes=allocations_for(info['box']);require(len(boxes)==2 and len({x['node'] for _,x in boxes})==2,'two distinct concrete Boxes required')
        projects=sel('field_project');require(len(projects)==2,'two Box field projections required')
        for index,((box_i,box),(app_i,app),(ret_i,ret),(_,call_app),(field_i,field)) in enumerate(zip(boxes,int_apps,hreturns,apps,projects)):
            require(box['state']=='READY' and box['layout']==info['box']['layout'] and box['slots']=={'f0':app['node']} and
                    ret['result']==box['node'] and app_i<box_i<ret_i and
                    field['host']==box['node'] and field['field']=='f0' and field['target']==app['node'] and
                    ret_i<field_i<demand(app['node'])[0], 'Box must return with separate pending field before projection/demand')
            memo_slot(call_app['node'],box['node'],ret_i)
        detail['returned_boxes']=[x['node'] for _,x in boxes]
        detail['pending_box_fields']=[x['node'] for _,x in int_apps]
    require(memo(second_app['node'])[1]['result'] in scalars and
            scalars[memo(second_app['node'])[1]['result']]==('i64',42) and
            scalars.get(memo(self_app['node'])[1]['result'])==('i64',0),'recursive one-Cons result differs')
    return {'recursive_closure':closure['node'],'recursive_code':info['code'],'registered_code_id':info['code_id'],
        'recursive_calls':3,'variants':[0,1,0],'helper_owner':helper['node'],'helper_closure':helper_closure['node'],
        'helper_calls':2,'helper_argument':argument,'helper_memo_event':hm,'initial_nil_memo_event':first_done,
        'bonus_node':bonus['node'],'bonus_evaluations':1,'bonus_memos':1,'bonus_memo_event':bm,
        'shared_node':shared,'shared_body':body,'shared_call_kinds':['Bool','Int','Int'],'actual_views':observed,
        'access_observation_scope':ACCESS_SCOPE,'memory':e['memory'],'memory_categories':e['memory_categories'],**detail}


def copied_controls(evaluation,info,graph):
    """Copied evidence only. Each corruption must fail its intended assertion."""
    observe(evaluation,info,graph);results=[]
    def event(r,kind,pred=lambda x:True):return one([x for x in r['events'] if x['event']==kind and pred(x)],'control selector')
    def allocation(r,op):return event(r,'allocate',lambda x:x['out']==op['out'])
    def first(r,kind,pred):return next(x for x in r['events'] if x['event']==kind and pred(x))
    def reject(name,change,guard):
        r=copy.deepcopy(evaluation);change(r);r['events_emitted']=len(r['events'])
        try:observe(r,info,graph)
        except AssertionError as exc:
            require(guard in str(exc),name+' failed unrelated guard: '+str(exc))
            results.append({'control':name,'status':'rejected','guard':guard})
        else:raise AssertionError(name+' accepted copied report corruption')
    reject('fill-target',lambda r:event(r,'fill').__setitem__('target',-1),'original Fill target/ticket')
    for key in ('self_capture','callable_capture'):
        reject(key,lambda r,k=key:allocation(r,info['closure'])['slots'].__setitem__(info[k],-1),'original recursive/helper Reference')
    reject('helper-memo-target',lambda r:event(r,'memo_publish',lambda x:x['destination']==allocation(r,info['helper'])['node']).__setitem__('result',-1),
           'initial Nil demanded helper or annotation lost callable')
    reject('recursive-Code',lambda r:allocation(r,info['closure']).__setitem__('code','wrong'),'source allocation Code/opcode')
    reject('helper-Code',lambda r:allocation(r,info['helper_closure']).__setitem__('code','wrong'),'source allocation Code/opcode')
    reject('helper-callback',lambda r:first(r,'frame_enter',lambda x:x['context'].get('name')==info['helper_closure']['function'])['context'].__setitem__('node',-1),
           'registered callback source differs')
    reject('helper-argument',lambda r:first(r,'invoke_enter',lambda x:x['closure']==allocation(r,info['helper_closure'])['node']).__setitem__('argument',-1),
           'two helper calls must preserve same original argument')
    reject('helper-call-reference',lambda r:allocation(r,info['helper_calls'][0])['slots'].__setitem__('$function',-1),
           'two helper calls must preserve same original argument')
    reject('cons-payload',lambda r:allocation(r,info['constructors'][1])['slots'].__setitem__('0',-1),'same original Cons/bonus/tail')
    reject('shared-view-origin',lambda r:event(r,'instantiate',lambda x:x['use']==graph['uses']['#i64']['row']['id']).__setitem__('new_access',
           event(r,'instantiate',lambda x:x['use']==graph['uses']['#bool']['row']['id'])['new_access']),'full shared Access/origin/capsule')
    reject('shared-view-storage',lambda r:allocation(r,info['helper_closure'])['slots'].__setitem__(info['helper_view']['capture'],-1),
           'helper full view storage')
    reject('shared-callback',lambda r:first(r,'frame_enter',lambda x:x['context'].get('name')==graph['shared_code'])['context'].__setitem__('node',-1),
           'registered callback source differs')
    reject('factory-field-mask',lambda r:first(r,'case_fields_i64',lambda x:x['variant_index']==1).__setitem__('field_mask',0),
           'selected factory original source differs')
    reject('bonus-extra-evaluation',lambda r:r['events'].append(copy.deepcopy(event(r,'callback_enter',lambda x:x['node']==allocation(r,info['bonus'])['node']))),
           'bonus callback once')
    reject('bonus-extra-memo',lambda r:r['events'].append(copy.deepcopy(event(r,'memo_publish',lambda x:x['destination']==allocation(r,info['bonus'])['node']))),
           'one exact memo')
    reject('shared-argument-substitution',lambda r:first(r,'allocate',lambda x:x['out']==info['int_call']['out'])['slots'].__setitem__('$argument',-1),
           'shared Int must receive exact original helper field/parameter')
    reject('shared-memo-substitution',lambda r:event(r,'memo_publish',lambda x:x['destination']==first(r,'allocate',lambda a:a['out']==info['int_call']['out'])['node']).__setitem__('result',-1),
           'memo changed exact result')
    def early(r,node):
        row=event(r,'update_pin',lambda x:x['node']==node(r));r['events'].remove(row)
        index=next(i for i,x in enumerate(r['events']) if x['event']=='memo_publish' and x['destination']==allocation(r,info['first_call'])['node'])
        r['events'].insert(index,row)
    reject('initial-Nil-helper-demand',lambda r:early(r,lambda q:allocation(q,info['helper'])['node']),
           'initial Nil demanded helper or annotation lost callable')
    reject('initial-Nil-bonus-demand',lambda r:early(r,lambda q:allocation(q,info['bonus'])['node']),
           'bonus must evaluate once after first shared Int call')
    if info['box'] is not None:
        reject('Box-field-substitution',lambda r:first(r,'allocate',lambda x:x['out']==info['box']['out'])['slots'].__setitem__('f0',-1),
               'Box must return with separate pending field')
        reject('Box-return-substitution',lambda r:first(r,'invoke_raw_return',lambda x:x['closure']==allocation(r,info['helper_closure'])['node']).__setitem__('result',-1),
               'Box must return with separate pending field')
        reject('Box-projection-substitution',lambda r:first(r,'field_project',lambda x:True).__setitem__('target',-1),
               'Box must return with separate pending field')
        def eager_field(r):
            node=first(r,'allocate',lambda x:x['out']==info['int_call']['out'])['node']
            row=event(r,'update_pin',lambda x:x['node']==node);r['events'].remove(row)
            index=next(i for i,x in enumerate(r['events']) if x['event']=='invoke_raw_return' and
                       x['closure']==allocation(r,info['helper_closure'])['node'])
            r['events'].insert(index,row)
        reject('Box-eager-field-demand',eager_field,'Box must return with separate pending field')
    reject('guard-cap-raised',lambda r:r.__setitem__('guard_work_limit',67_108_865),'native guard/work contract')
    reject('guard-missing',lambda r:r.__setitem__('guards_checked_mask',(1<<27)-2),'native guard/work contract')
    reject('ledger-live',lambda r:r['memory'].__setitem__('live_bytes',1),'ledger arithmetic differs')
    return results


def structure_controls(capture,plan,generated,name):
    structure(capture,plan,generated,name);results=[]
    def reject(label,change,guard):
        p=copy.deepcopy(plan);change(p)
        try:structure(capture,p,generated,name)
        except AssertionError as exc:
            require(guard in str(exc),label+' failed unrelated guard: '+str(exc))
            results.append({'control':label,'status':'rejected','guard':guard})
        else:raise AssertionError(label+' accepted copied structural corruption')
    knot=lambda p:one(p['binding']['source_map']['knot_map'],'one knot control')
    reject('capture-policy',lambda p:knot(p)['captures'].__setitem__('policy','closed-scalar-callable-shared-view-captures/1'),
           'exact nominal callable capture inventory')
    reject('capture-type',lambda p:knot(p)['captures']['callables'][0]['type'].__setitem__('to',{'tag':'constructor','name':'Bool','arguments':[]}),
           'exact nominal callable capture inventory')
    reject('capture-occurrence',lambda p:knot(p)['captures']['callables'][0]['occurrences'].pop(),'exact nominal callable capture inventory')
    reject('invented-nominal-owner',lambda p:knot(p)['captures']['nominals'].append({}),'exact nominal callable capture inventory')
    reject('Fill-owner',lambda p:instruction(p['program'],knot(p)['fill']).__setitem__('value','wrong'),'original hole/Fill/self ownership')
    reject('self-source',lambda p:knot(p).__setitem__('self_uses',[]),'recursive source/knot correspondence')
    return results


def run_case(args,output,env,name):
    inputs=output/(name+'-inputs');inputs.mkdir()
    (inputs/'SharedPoly.emlf').write_text(SHARED,encoding='utf-8');entry=inputs/'main.emlf'
    entry.write_text(SOURCES[name],encoding='utf-8');target=output/name
    build.run([sys.executable,'-B',str(BASE/'run_source_v8.py'),str(entry),'--module-root',str(inputs),
        '--ghc',args.ghc,'--cc',args.cc,'--output',str(target)],output,name,cwd=BASE,env=env,
        wall=1200,cpu=900,memory=16<<30,termination_grace=15,stdout_limit=1<<20,stderr_limit=1<<20,file_limit=64<<20)
    require(not bounded_read(output/(name+'.stderr'),1<<20),'successful CLI stderr')
    result=read_json(target/'result.json');evaluation=read_json(target/'native/run.stdout')
    require(result['status']=='complete' and result['failure_policy']=='retain' and result['native']==evaluation and
            'placement' not in result,'fresh CLI result differs')
    capture=read_json(target/'capture.stdout');verified=read_json(target/'verification.json');plan=read_json(target/'planned.json',8<<20)
    require(verified['fragment_admitted'] and verified['normalization_replay']=='all exact independent fields match' and
            capture['checked_type']==INT and plan['binding']['mode']=='coarse-owned','fresh checking/replay/default mode differs')
    generated=bounded_read(target/'native/ir8_runtime_generated.c',8<<20).decode()
    info=structure(capture,plan,generated,name);graph=shared_graph(plan,verified,capture,info)
    row={'case':name,'status':'passed','observation':observe(evaluation,info,graph),
         'copied_report_controls':copied_controls(evaluation,info,graph),
         'copied_structure_controls':structure_controls(capture,plan,generated,name),
         'source_hashes':{'main.emlf':build.sha(SOURCES[name].encode()),'SharedPoly.emlf':build.sha(SHARED.encode())}}
    build.save(target/'nominal-callable-observations.json',row);print(name+': PASS',flush=True);return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc',required=True);parser.add_argument('--cc',default='cc');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.absolute()
    require(output.resolve()==output and output!=BASE.parents[2] and BASE.parents[2] not in output.parents,
            'output must be canonical, fresh and outside checkout')
    output.mkdir(parents=True,exist_ok=False);env=cli.environment(output);build.SUITE_DEADLINE=time.monotonic()+2700;results=[]
    try:
        for name in SOURCES:results.append(run_case(args,output,env,name))
    except BaseException as exc:
        try:build.save(output/'failure.json',{'error':repr(exc),'completed_cases':[r['case'] for r in results]})
        except BaseException as persistence:exc.add_note('Failure persistence also failed: '+repr(persistence))
        raise
    build.save(output/'results.json',results);return 0


if __name__=='__main__':raise SystemExit(main())
