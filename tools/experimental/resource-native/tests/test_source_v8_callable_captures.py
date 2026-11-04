#!/usr/bin/env python3
"""Two fresh recursive functions capturing ordinary closed scalar-arrow owners.

Actual event identities are joined to checked source and fresh public metadata.
Owner handoff events do not expose per-owner Access rows: view preservation is
checked through source/metadata/generated-code correspondence, stored slots,
actual instantiation and invocation events, and unchanged runtime guards.
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
sys.path[:0] = [str(BASE),str(BASE/'tests')]
import run_source_v8 as cli
import source_build_v8 as build
from source_snapshot_v8 import bounded_read
from resource_ir_v8.metadata import check_metadata
from test_shared_source_native import at, instruction
from test_source_v8_recursive_sum import one, walk, primitive, var, source_allocation, constructor_terms, closed_layout, SHARED, INT
from test_source_v8_monomorphic_recursion import ledger, observe_fault_pair, fault_controls

require=build.require
SOURCES={
    'pending-step': ('import SharedPoly\ndata IntList = Nil | Cons Int IntList;\n'
        'let bonus = addInt 20 1 in\n'
        'let step : Int -> Int = \\x -> sharedId (addInt x bonus) in\n'
        'let rec sumWith : IntList -> Int = \\xs -> case xs of { Nil -> 0; Cons _ rest -> addInt (step 0) (sumWith rest) } in\n'
        'if sharedId true then addInt (sumWith Nil) (sumWith (Cons 0 (Cons 0 Nil))) else 0\n'),
    'view-alias': ('import SharedPoly\ndata IntList = Nil | Cons Int IntList;\n'
        'let bonus = addInt 20 1 in\n'
        'let step : Int -> Int = sharedId in\n'
        'let rec sumWith : IntList -> Int = \\xs -> case xs of { Nil -> 0; Cons _ rest -> addInt (step bonus) (sumWith rest) } in\n'
        'if sharedId true then addInt (sumWith Nil) (sumWith (Cons 0 (Cons 0 Nil))) else 0\n')}
ARROW={'tag':'arrow','from':INT,'to':INT}
ACCESS_SCOPE=('Ordinary callable captures preserve a complete scalar-arrow Reference, not a reconstructed shared view. '
              'Actual wrapper/memo/slot/invoke events are joined with fresh metadata and generated code. '
              'There is no per-owner Access trace: guarded handoffs do not independently expose every owner Access. '
              'A concrete recursive host does not rebrand a captured generic Instance as E0.')

def read_json(path, limit=32<<20):
    return json.loads(bounded_read(path,limit))


def address(path):
    return {'stage':'normalized','path':path}


def spine(node,path):
    args=[]
    while node['tag']=='application':
        args.append((path+['argument'],node['argument']))
        node=node['function'];path=path+['function']
    return node,path,list(reversed(args))


def source_facts(capture,name):
    require(name in SOURCES,"known fixture required")
    raw=capture['normalization']['raw_normalized']
    path,term=one([(p,n) for p,n in walk(raw) if isinstance(n,dict) and n.get('tag')=='letrec'],'one recursive source')
    binding=one(term['bindings'],'one recursive binder');rhs_path=path+['bindings','0','value'];rhs=binding['value']
    annotation=binding['type'];step_let=at(raw,path[:-1]);bonus_let=at(raw,path[:-2])
    require(path[-2:]==['body','body'] and step_let['tag']==bonus_let['tag']=='let' and
            primitive(bonus_let['value'],20,1),'lexical bonus/step bindings differ')
    bonus_path=path[:-2]+['value'];bonus=bonus_let['name'];step=step_let['name'];step_path=path[:-1]+['value']
    step_rhs=step_let['value'];sw=step_rhs.get('function',{})
    require(step_rhs['tag']=='application' and sw.get('tag')=='lambda' and sw['parameter_type']==ARROW and
            var(sw['body'],sw['parameter']),'ordinary step annotation application must be preserved')
    step_function=step_path+['argument'];step_value=step_rhs['argument']
    if name=='pending-step':
        require(step_value['tag']=='lambda' and step_value['parameter_type']==INT,'real scalar step lambda required')
        local=step_value['body'];local_path=step_function+['body']
        require(local['tag']=='let' and local['value']['tag']=='application' and
                var(local['value']['argument'],step_value['parameter']),'step parameter wrapper missing')
        coerce=local['value']['function']
        require(coerce['tag']=='lambda' and coerce['parameter_type']==INT and var(coerce['body'],coerce['parameter']),
                'step parameter wrapper is not identity')
        int_call=local['body'];int_path=local_path+['body'];int_view=int_path+['function']
        require(int_call['tag']=='application' and int_call['function']['tag']=='type_application',
                'step must apply the full shared Int view')
        add,_,args=spine(int_call['argument'],int_path+['argument'])
        require(add['tag']=='primitive' and add['name']=='addInt' and len(args)==2 and
                var(args[0][1],local['name']) and var(args[1][1],bonus),'step payload is exact pending addInt(x,bonus)')
        step_add=int_path+['argument'];bonus_occurrence=args[1][0]
    else:
        require(step_value['tag']=='type_application','view alias must retain full type application under annotation')
        int_path=None;int_view=step_function;step_add=None;bonus_occurrence=None
    require(annotation['tag']=='arrow' and annotation['to']==INT and rhs['tag']=='application' and
            rhs['function']['tag']==rhs['argument']['tag']=='lambda','exact annotated recursive wrapper differs')
    wrapper,function=rhs['function'],rhs['argument'];function_path=rhs_path+['argument']
    require(wrapper['parameter_type']==annotation and var(wrapper['body'],wrapper['parameter']) and
            function['parameter_type']==annotation['from'],'ordinary RHS wrapper is not exact passthrough')
    arg_let=function['body'];arg_path=function_path+['body']
    require(arg_let['tag']=='let' and arg_let['value']['tag']=='application' and
            var(arg_let['value']['argument'],function['parameter']),'ordinary argument wrapper missing')
    coercion=arg_let['value']['function']
    require(coercion['tag']=='lambda' and coercion['parameter_type']==annotation['from'] and
            var(coercion['body'],coercion['parameter']),'argument wrapper is not exact passthrough')
    case_path=arg_path+['body'];case=at(raw,case_path)
    require(case['tag']=='case' and case['result_type']==INT and var(case['scrutinee'],arg_let['name']) and
            len(case['alternatives'])==2,'one recursive Int case differs')
    nil=one([(i,a) for i,a in enumerate(case['alternatives']) if not a['pattern']['fields']],'one Nil source arm')
    cons=one([(i,a) for i,a in enumerate(case['alternatives']) if len(a['pattern']['fields'])==2],'one Cons source arm')
    require(nil[1]['body']=={'tag':'int64','value':0} and cons[1]['pattern']['fields'][0] is None and
            cons[1]['pattern']['fields'][1] is not None,'Nil result or ignored head/tail pattern differs')
    cons_path=case_path+['alternatives',str(cons[0]),'body']
    add,_,args=spine(cons[1]['body'],cons_path)
    require(add['tag']=='primitive' and add['name']=='addInt' and len(args)==2,'Cons body must add view call and recursion')
    step_call_path,step_call=args[0];self_path,self_call=args[1]
    require(step_call['tag']=='application' and var(step_call['function'],step),
            'Cons must call the exact ordinary captured step')
    require(step_call['argument']=={'tag':'int64','value':0} if name=='pending-step' else
            var(step_call['argument'],bonus),'Cons callable argument differs')
    if name=='view-alias':bonus_occurrence=step_call_path+['argument']
    require(self_call['tag']=='application' and var(self_call['function'],binding['name']) and
            var(self_call['argument'],cons[1]['pattern']['fields'][1]),'self call must consume selected tail')
    body_path=path+['body'];branch,_,branch_args=spine(term['body'],body_path)
    require(branch['tag']=='primitive' and branch['name']=='ifThenElse' and len(branch_args)==3 and
            branch_args[2][1]=={'tag':'int64','value':0},'outer shared Bool branch differs')
    bool_path,bool_call=branch_args[0]
    require(bool_call['tag']=='application' and bool_call['function']['tag']=='type_application' and
            bool_call['argument']=={'tag':'bool','value':True},'outer shared Bool call differs')
    root_add_path,root_add=branch_args[1];head,_,root_args=spine(root_add,root_add_path)
    require(head['tag']=='primitive' and head['name']=='addInt' and len(root_args)==2,'main must add both recursive results')
    for _,call in root_args:
        require(call['tag']=='application' and var(call['function'],binding['name']),'main recursion source differs')
    return dict(raw=raw,path=path,binding=binding,rhs=rhs_path,function=function_path,argument_wrapper=arg_path+['value','function'],
                bonus=bonus,bonus_path=bonus_path,case=case,case_path=case_path,nil=nil,cons=cons,
                cons_path=cons_path,self_call=self_path,int_call=int_path,int_view=int_view,bool_call=bool_path,
                name=name,step=step,step_path=step_path,step_function=step_function,step_add=step_add,
                step_call=step_call_path,bonus_occurrence=bonus_occurrence,
                root_add=root_add_path,first_call=root_args[0][0],second_call=root_args[1][0])



def carrier_allocation(plan,path,kind):
    """A conditional branch wrapper and its primitive keep the same source path."""
    mapping=plan['binding']['source_map'];p=plan['program']
    carrier=one([r for r in mapping['carrier_map'] if r['source']==address(path) and r['kind']==kind],
                'one exact source carrier kind')
    return one([instruction(p,r['instruction']) for r in mapping['allocation_map'] if r['source']==address(path) and
                r['role']=='thunk' and instruction(p,r['instruction']).get('code')==carrier['ir_code']],
               'one exact source/carrier allocation')


def structure(capture,plan,generated,name):
    f=source_facts(capture,name);p=plan['program'];m=plan['binding']['source_map'];raw=f['raw']
    knot=one(m['knot_map'],'one recursive knot mapping');binding=f['binding']
    require(knot['source']==address(f['path']) and knot['binding_source']==address(f['path']+['bindings','0']) and
            knot['binder']==binding['name'] and knot['rhs']==address(f['rhs']) and knot['type_scope'] is None,
            'recursive source/knot correspondence differs')
    hole=instruction(p,knot['hole']);fill=instruction(p,knot['fill'])
    require(hole=={'op':'hole','out':knot['hole_owner'],'in':knot['home'],'layout':'^'+knot['logical_type']} and
            fill=={'op':'fill','hole':knot['hole_owner'],'value':knot['rhs_owner']} and
            instruction(p,knot['retain_self'])=={'op':'retain','out':knot['self_owner'],'value':knot['hole_owner']},
            'original hole/Fill/self ownership differs')
    for field,value in (('drop_rhs',knot['rhs_owner']),('drop_self',knot['self_owner']),('drop_hole',knot['hole_owner'])):
        require(instruction(p,knot[field])=={'op':'drop','value':value},'knot release differs')
    closure=source_allocation(plan,f['function'],'closure');rhs=source_allocation(plan,f['rhs'],'application')
    wrapper=source_allocation(plan,f['rhs']+['function'],'closure')
    bonus=source_allocation(plan,f['bonus_path'],'thunk')
    require(rhs['out']==knot['rhs_owner'] and rhs['function']==wrapper['out'] and rhs['argument']==closure['out'],
            'Fill must preserve pending ordinary wrapper RHS')
    carrier=one([x for x in m['carrier_map'] if x['source']==address(f['function'])],'one recursive lambda carrier')
    mono=carrier['mono_captures']
    require(carrier['ir_code']==closure['function'] and carrier['type_scope'] is None and
            len(mono)==(2 if name=='pending-step' else 3) and not carrier['view_captures'],
            'recursive ordinary callable capture census/scope differs')
    self_cap=one([x for x in mono if x['binder']==binding['name']['id']],'exact self capture')
    step_cap=one([x for x in mono if x['binder']==f['step']['id']],'exact ordinary callable capture')
    bonus_cap=(one([x for x in mono if x['binder']==f['bonus']['id']],'exact bonus capture') if name=='view-alias' else None)
    step=source_allocation(plan,f['step_path'],'application')
    step_wrapper=source_allocation(plan,f['step_path']+['function'],'closure')
    require(self_cap['layout']=='^'+knot['logical_type'] and self_cap['relation']=='down' and
            closure['captures'][self_cap['capture']]==knot['self_owner'] and
            closure['captures'][step_cap['capture']]==step['out'] and
            step['function']==step_wrapper['out'],'recursive self/ordinary callable Reference differs')
    require(step_cap['layout'].startswith('^'),'ordinary callable must have an explicit logical arrow')
    arrow=p['types'][step_cap['layout'][1:]]
    require(set(arrow)=={'tag','argument','result','protocol','result_identity'} and arrow['tag']=='arrow' and
            arrow['protocol']=='repeat' and arrow['result_identity']=='unknown' and
            closed_layout(p,'^'+arrow['argument'])==closed_layout(p,'^'+arrow['result'])=='#i64',
            'ordinary callable must retain complete unknown-Code scalar arrow')
    for c in m['carrier_map']:
        for r in c['mono_captures']:
            if r['binder']==f['step']['id']:
                require(r['layout']==step_cap['layout'],'ordinary callable contract lost in downstream carrier')
    if bonus_cap:
        require(closed_layout(p,bonus_cap['layout'])=='#i64' and
                closure['captures'][bonus_cap['capture']]==bonus['out'],'recursive scalar owner differs')
    require(knot['captures']=={'policy':'closed-scalar-callable-shared-view-captures/1',
        'scalars':([{'binding':f['bonus'],'type':INT,'occurrences':[address(f['bonus_occurrence'])]}] if bonus_cap else []),
        'callables':[{'binding':f['step'],'type':ARROW,'occurrences':[address(f['step_call']+['function'])]}],
        'views':[]},'ordinary callable capture inventory differs from exact source occurrences')
    require(knot['function_source']==address(f['function']) and knot['self_uses']==[address(f['self_call']+['function'])],
            'recursive function/self source evidence differs')
    for record in mono:
        require(p['functions'][closure['function']]['captures'][record['capture']]==
                {'layout':record['layout'],'relation':record['relation']},'capture layout/support contract differs')
    require(set(closure['captures'])=={x['capture'] for x in mono},'extra/missing recursive capture')
    require(not any(n.get('op')=='instantiate' for _,n in walk(p['functions'][closure['function']]['body']) if isinstance(n,dict)),
            'recursive callback must not instantiate or reconstruct ordinary callable')
    int_use=one([r for r in m['use_map'] if r['source']==address(f['int_view'])],'actual source Int use')
    step_closure=step_bonus_cap=step_view=step_argument_wrapper=None
    if name=='pending-step':
        step_closure=source_allocation(plan,f['step_function'],'closure')
        sc=one([x for x in m['carrier_map'] if x['source']==address(f['step_function'])],'step lambda carrier')
        require(step['argument']==step_closure['out'] and sc['type_scope'] is None and
                len(sc['mono_captures'])==len(sc['view_captures'])==1,'pending step capture census differs')
        step_bonus_cap=sc['mono_captures'][0];step_view=sc['view_captures'][0]
        require(step_bonus_cap['binder']==f['bonus']['id'] and closed_layout(p,step_bonus_cap['layout'])=='#i64' and
                step_closure['captures'][step_bonus_cap['capture']]==bonus['out'] and
                step_view['definition']==int_use['definition'] and step_view['occurrences']==[int_use['use']] and
                [p['types'][t]['layout'] for t in step_view['arguments']]==['#i64'],'step scalar/shared-view captures differ')
        step_argument_wrapper=source_allocation(plan,f['step_function']+['body','value','function'],'closure')
    family=one(m['sum_map'],'one IntList family');physical='%'+family['family']
    require(p['families'][family['family']]=={'variants':['V0','V1'],'fields':{'V0':[],'V1':['#i64',physical]}},
            'exact recursive nominal family differs')
    case=one(m['sum_case_map'],'one static recursive case')
    require(case['source']==address(f['case_path']) and case['family']==family['family'],'recursive case mapping differs')
    factory=instruction(p,case['factory']);arms={a['variant']:a for a in case['arms']}
    require(set(arms)=={0,1} and factory['op']=='case_fields_i64' and set(factory['arms'])=={'V0','V1'},
            'exhaustive selected factory differs')
    for variant,arm in arms.items():
        src=f['case']['alternatives'][arm['index']]
        require(arm['source']==address(f['case_path']+['alternatives',str(arm['index']),'body']) and
                arm['pattern_source']==address(f['case_path']+['alternatives',str(arm['index']),'pattern']) and
                arm['constructor']==src['pattern']['constructor'] and
                factory['arms']['V'+str(variant)]=={'code':arm['code'],'captures':arm['captures']},'arm source/Code identity differs')
        wanted=[(i,x) for i,x in enumerate(src['pattern']['fields']) if x is not None]
        require(len(arm['field_captures'])==len(wanted),'wildcard/field capture census differs')
        for field,(index,binder) in zip(arm['field_captures'],wanted):
            require(field['index']==index and field['binder']==binder['id'] and field['relation']=='down' and
                    arm['captures'][field['capture']]=={'kind':'field','index':index},'selected tail field differs')
    require(len(arms[0]['field_captures'])==0 and [x['index'] for x in arms[1]['field_captures']]==[1],
            'wildcard heads must not become field captures')
    constructors=[]
    for row in m['sum_constructor_map']:
        head,args=constructor_terms(raw,row)
        require(row['declaration']==family['declaration'] and head['name']==family['variants'][row['variant']]['constructor'],
                'constructor nominal source differs')
        op=instruction(p,row['allocation'])
        require(op==source_allocation(plan,row['source']['path'],'construct_sum' if args else 'construct_nullary'),
                'constructor allocation/source join differs')
        constructors.append((row,args,op))
    first_nil=one([r for r in constructors if r[0]['source']['path']==f['first_call']+['argument']],'initial Nil source')
    outer=one([r for r in constructors if r[0]['source']['path']==f['second_call']+['argument']],'outer Cons source')
    inner=one([r for r in constructors if r[0]['source']['path']==outer[1][1][0]],'inner Cons source')
    tail_nil=one([r for r in constructors if r[0]['source']['path']==inner[1][1][0]],'terminal Nil source')
    require(len(constructors)==4 and [r[0]['variant'] for r in (first_nil,outer,inner,tail_nil)]==[0,1,1,0] and
            all(r[1][0][1]=={'tag':'int64','value':0} for r in (outer,inner)),'exact finite list source differs')
    metadata=json.loads(check_metadata(p).metadata_json)
    code=one([r for r in metadata['codes'] if r['kind']=='function' and r['name']==closure['function']],'registered recursive Code')
    definitions=[int(x) for x in re.findall(r'static Rt8Handle \*rt8_body_(\d+)\(',generated)]
    registrations=[(int(a),int(b)) for a,b in re.findall(r'\{ \.code_id = (\d+), \.body = rt8_body_(\d+) \}',generated)]
    require(definitions==list(range(len(metadata['codes']))) and registrations==[(i,i) for i in definitions],
            'actual generated callback definitions/registrations differ')
    require(generated.count('rt8_fill(ctx,')==1 and generated.count(' = rt8_hole(ctx,')==1,'generated one-knot census differs')
    return dict(facts=f,knot=knot,hole=hole,fill=fill,rhs=rhs,closure=closure,wrapper=wrapper,bonus=bonus,
                self_capture=self_cap['capture'],bonus_capture=bonus_cap['capture'] if bonus_cap else None,
                callable_capture=step_cap['capture'],callable_layout=step_cap['layout'],step=step,step_wrapper=step_wrapper,
                step_closure=step_closure,step_bonus_capture=step_bonus_cap['capture'] if step_bonus_cap else None,
                step_view=step_view,step_argument_wrapper=step_argument_wrapper,code=closure['function'],code_id=code['id'],metadata=metadata,family=physical,arms=arms,
                constructors=[r[2] for r in (first_nil,outer,inner,tail_nil)],
                self_call=source_allocation(plan,f['self_call'],'application'),
                int_call=source_allocation(plan,f['int_call'],'application') if f['int_call'] else None,
                step_call=source_allocation(plan,f['step_call'],'application'),
                step_add=source_allocation(plan,f['step_add'],'thunk') if f['step_add'] else None,
                bool_call=source_allocation(plan,f['bool_call'],'application'),
                first_call=source_allocation(plan,f['first_call'],'application'),
                second_call=source_allocation(plan,f['second_call'],'application'),
                root_add=carrier_allocation(plan,f['root_add'],'primitive'),
                cons_add=source_allocation(plan,f['cons_path'],'thunk'),
                argument_wrapper=source_allocation(plan,f['argument_wrapper'],'closure'))


def shared_graph(plan,verified,capture,info):
    p,m,meta=plan['program'],plan['binding']['source_map'],info['metadata']
    scheme=one(m['scheme_map'],'one shared Scheme');definition=one(verified['fragment']['definitions'],'one verified shared definition')
    require(scheme['binder']==definition['binding']['id'] and len(p['schemes'])==1 and
            p['schemes'][scheme['scheme']]['parameters']==1,'shared definition/full prefix differs')
    generic,seal=instruction(p,scheme['generalize']),instruction(p,scheme['seal'])
    pending=one([x for x in generic['body'] if x['op']=='application'],'one pending generic RHS')
    closures={x['out']:x['function'] for x in generic['body'] if x['op']=='closure'}
    require(pending['out']==seal['value'] and not any(x['op']=='force' for x in generic['body']),
            'shared RHS must remain pending and single')
    expected={'#bool':info['facts']['bool_call']+['function'],'#i64':info['facts']['int_view']}
    require(len(m['use_map'])==len(verified['fragment']['uses'])==len(p['instantiations'])==2,'complete view census differs')
    uses={}
    for atom,path in expected.items():
        source=one([x for x in m['use_map'] if x['source']==address(path)],'exact source full view')
        require([p['types'][t]['layout'] for t in source['arguments']]==[atom] and source['definition']==definition['id'],
                'full view source/definition/vector differs')
        descriptor=one([name for name,row in p['instantiations'].items() if
                        row['scheme']==scheme['scheme'] and row['arguments']==source['arguments']],'exact instantiated vector')
        row=one([x for x in meta['uses'] if x['name']==descriptor],'fresh actual Use metadata')
        require(len(row['occurrences'])==1 and row['occurrences'][0]['root']=='entry',
                'complete views must be acquired once in entry, not recursive callbacks')
        operation=instruction(p,row['occurrences'][0])
        require(operation['op']=='instantiate' and operation['instantiation']==descriptor,'Use occurrence differs')
        typ=meta['types'][row['result_type']]
        require(typ['tag']=='arrow' and meta['types'][typ['argument']]['atom']==atom and
                meta['types'][typ['result']]['atom']==atom and typ['protocol']=='repeat' and typ['result_identity']=='unknown',
                'full callable view contract differs')
        uses[atom]={'source':source,'row':row,'operation':operation}
    require(uses['#i64']['source']['source_view']['kind']==('captured' if info['facts']['name']=='pending-step' else 'scheme'),
            'source full Int view acquisition differs')
    for body in [r['body'] for r in p['functions'].values()]+[r['body'] for r in p['codes'].values()]:
        require(not any(isinstance(n,dict) and n.get('op')=='instantiate' for _,n in walk(body)),
                'callback-local re-instantiation is forbidden')
    carriers=[x for x in m['carrier_map'] if x['kind']=='lambda']
    actual=[path for path,node in walk(info['facts']['raw']['body'],['body']) if isinstance(node,dict) and node.get('tag')=='lambda']
    require(sorted(x['source']['path'] for x in carriers)==sorted(actual) and len(carriers)==len(p['functions']),
            'ordinary lambda/source census differs')
    for variable,child in ((pending['function'],'function'),(pending['argument'],'argument')):
        carrier=one([x for x in carriers if x['source']['path']==scheme['rhs_cursor']['path']+[child]],'generic lambda source')
        require(carrier['ir_code']==closures[variable] and carrier['type_scope']==scheme['scheme'],'generic lambda scope differs')
    recursive=meta['codes'][info['code_id']]
    require(recursive['scope'] is None,'recursive host must remain concrete')
    resolved=one([x for x in recursive['captures'] if x['name']==info['callable_capture']],'ordinary callable metadata')
    require(resolved['type']==uses['#i64']['row']['result_type'],'ordinary callable full contract differs')
    if info['facts']['name']=='view-alias':
        require(info['step']['argument']==uses['#i64']['operation']['out'],'alias annotation must receive actual Int view')
    else:
        require(info['step_closure']['captures'][info['step_view']['capture']]==uses['#i64']['operation']['out'],
                'step closure must capture actual entry-acquired full Int view')
    argument_path=scheme['rhs_cursor']['path']+['argument','body','value']
    shared_lambda=at(info['facts']['raw'],scheme['rhs_cursor']['path']+['argument'])
    local=shared_lambda['body'];argument=at(info['facts']['raw'],argument_path)
    require(local['tag']=='let' and argument['tag']=='application' and
            var(argument['argument'],shared_lambda['parameter']) and
            argument['function']['tag']=='lambda' and
            var(argument['function']['body'],argument['function']['parameter']) and
            var(local['body'],local['name']),'shared body must preserve exact ordinary parameter wrapper')
    return {'outer_code':closures[pending['function']],'shared_code':closures[pending['argument']],
            'seal_owner':seal['value'],'uses':uses,'scheme':scheme,
            'parameter_wrapper':source_allocation(plan,argument_path+['function'],'closure'),
            'parameter_application':source_allocation(plan,argument_path,'application')}


def observe(e,info,graph):
    require(e['schema']=='resource-ir-v8-run/1' and e['state']==e['fault']==0 and
            e['result']=={'kind':'i64','value':42} and e['scalar_result_kind']==1 and e['scalar_result']==42 and
            e['events_omitted']==0 and e['events_emitted']==len(e['events']),'complete native Int42 report required')
    require(e['guards_failed_mask']==0 and e['guards_checked_mask']==(1<<27)-1 and
            e['guard_work_limit']==67_108_864 and 0<e['guard_work_used']<=e['guard_work_limit'],'native guard failure/work differs')
    ledger(e,True);events=e['events'];sel=lambda kind:[(i,x) for i,x in enumerate(events) if x['event']==kind]
    allocations=sel('allocate');nodes={x['node']:x for _,x in allocations}
    require(len(nodes)==len(allocations),'duplicate allocation node')
    def alloc(op,label):
        i,row=one([(i,x) for i,x in allocations if x['out']==op['out']],label+' allocation once')
        require(row['opcode']==op['op'] and row['code']==(op['function'] if op['op']=='closure' else op.get('code')),
                label+' source Code/opcode differs')
        return i,row
    name=info['facts']['name']
    bonus_i,bonus=alloc(info['bonus'],'bonus');hole_i,hole=alloc(info['hole'],'hole')
    step_i,step=alloc(info['step'],'pending step');_,step_wrapper=alloc(info['step_wrapper'],'step annotation wrapper')
    closure_i,closure=alloc(info['closure'],'recursive closure');wrapper_i,wrapper=alloc(info['wrapper'],'RHS wrapper')
    rhs_i,rhs=alloc(info['rhs'],'recursive RHS');fill_i,fill=one(sel('fill'),'one Fill')
    require(bonus['state']=='THUNK' and hole['state']=='HOLE' and closure['state']==wrapper['state']=='CLOSURE' and
            rhs['state']==step['state']=='APPLICATION' and bonus_i<step_i<hole_i<closure_i<rhs_i<fill_i and wrapper_i<rhs_i,
            'bonus/knot lazy allocation order differs')
    require(fill['hole']==hole['node'] and fill['target']==rhs['node'] and
            fill['hole_variable']==info['fill']['hole'] and fill['value_variable']==info['fill']['value'],
            'original Fill target/ticket differs')
    require(rhs['slots']=={'$function':wrapper['node'],'$argument':closure['node']} and
            closure['slots'][info['self_capture']]==hole['node'] and closure['slots'][info['callable_capture']]==step['node'] and
            (info['bonus_capture'] is None or closure['slots'][info['bonus_capture']]==bonus['node']),
            'recursive pending wrapper/self/callable/scalar graph differs')
    slot_i,_=one([(i,x) for i,x in sel('slot_install') if x['host']==hole['node'] and x['field']=='$target' and
                   x['target']==rhs['node']],'one original Fill edge')
    require(rhs_i<slot_i<fill_i and not any(i<fill_i and x['node'] in (hole['node'],rhs['node']) for i,x in sel('update_pin')),
            'knot was demanded before exact Fill')
    rhs_memo_i,rhs_memo=one([(i,x) for i,x in sel('memo_publish') if x['destination']==rhs['node']],'recursive RHS memo once')
    wrap_i,wrap_call=one([(i,x) for i,x in sel('invoke_enter') if x['closure']==wrapper['node']],'ordinary RHS wrapper once')
    require(fill_i<wrap_i<rhs_memo_i and wrap_call['argument']==rhs_memo['result']==closure['node'],
            'ordinary RHS wrapper erased or recursive closure changed')

    begin_i,begin=one(sel('generic_begin'),'one generic introduction');seal_i,seal=one(sel('generic_seal'),'one generic seal')
    shared=seal['node'];pending=nodes[shared]
    require(begin_i<seal_i and pending['out']==graph['seal_owner'] and pending['state']=='APPLICATION',
            'shared pending node lost original source allocation')
    outer_shared,body=pending['slots']['$function'],pending['slots']['$argument']
    require(nodes[outer_shared]['code']==graph['outer_code'] and nodes[body]['code']==graph['shared_code'] and
            sum(x['code']==graph['shared_code'] for _,x in allocations)==1,'sharedId body cloned/substituted')
    entry=one([x for _,x in sel('frame_enter') if x['context']['kind']=='entry'],'entry frame')['frame']
    uses=sel('instantiate');require(len(uses)==2,'shared views acquired again or omitted')
    observed_access={}
    meta=info['metadata']
    for atom,wanted in graph['uses'].items():
        i,event=one([(i,x) for i,x in uses if x['use']==wanted['row']['id']],'one exact full Use')
        require(event['node']==shared and event['frame']==entry and event['mode']=='own' and event['anchor'] is None,
                'view acquired inside callback or detached from shared node')
        before=meta['accesses'][event['old_access']];after=meta['accesses'][event['new_access']]
        require(before['mode']=='SCHEME' and after['mode']=='MONO' and before['site']==after['site']==pending['site_id'] and
                before['origin_env']==after['origin_env']==pending['env_id'] and after['origin_env']!=0 and
                meta['environments'][after['origin_env']]['mode']=='NEUTRAL' and
                after['use_env']==wanted['row']['env'] and after['type']==wanted['row']['result_type'] and
                after['scheme'] is None and meta['environments'][after['use_env']]['mode']=='CLOSED',
                'captured generic Access was relabelled E0 or lost full vector')
        observed_access[atom]={'event_index':i,'origin_env':after['origin_env'],'use_env':after['use_env'],
                               'access':after['id'],'type':after['type'],'use':event['use']}
    require(observed_access['#i64']['event_index']<step_i,'full Int view must be acquired before step annotation publication')
    require(closure['env_id']==0,'recursive host must be concrete without rebranding captured origin')
    handoffs=[(i,x) for i,x in sel('closure_capture_handoff') if x['node']==closure['node']]
    require(len(handoffs)==4 and all(set(x['owners'])==set(closure['slots']) and x['protocol']=='repeat' for _,x in handoffs) and
            len({owner for _,x in handoffs for owner in x['owners'].values()})==4*len(closure['slots']),
            'four recursive activations must acquire complete distinct capture owners')

    constructors=[alloc(op,'list constructor')[1] for op in info['constructors']]
    first_nil,outer,inner,tail_nil=constructors
    scalars={x['node']:(x['kind'],x['value']) for _,x in sel('scalar_value')}
    require(not first_nil['slots'] and not tail_nil['slots'] and outer['slots']['1']==inner['node'] and
            inner['slots']['1']==tail_nil['node'] and all(scalars.get(n['slots']['0'])==('i64',0) for n in (outer,inner)),
            'exact finite constructor graph differs')
    require(len(sel('sum_value'))==4,'constructor census differs')
    for n,variant in zip(constructors,(0,1,1,0)):
        _,row=one([(i,x) for i,x in sel('sum_value') if x['node']==n['node']],'one constructor value')
        require(row['family']==n['layout']==info['family'] and row['variant_index']==variant and row['variant']=='V'+str(variant),
                'nominal variant identity differs')
    calls=[(i,x) for i,x in sel('invoke_enter') if x['closure']==closure['node']]
    frames=[(i,x) for i,x in sel('frame_enter') if x['context'].get('name')==info['code']]
    require(len(calls)==len(frames)==4 and [x['argument'] for _,x in calls]==[n['node'] for n in constructors] and
            len({x['frame'] for _,x in frames})==4 and all(x['context']['node']==closure['node'] for _,x in frames) and
            sum(x['code']==info['code'] for _,x in allocations)==1,'same closure/Code must invoke Nil/Cons/Cons/Nil')
    require(rhs_memo_i<calls[0][0] and all(h[0]<c[0]<f[0] for h,c,f in zip(handoffs,calls,frames)),
            'capture handoff/callback order differs')
    argument_wrappers=[x for _,x in allocations if x['out']==info['argument_wrapper']['out']]
    require(len(argument_wrappers)==4 and all(x['code']==info['argument_wrapper']['function'] for x in argument_wrappers),
            'ordinary argument wrappers erased')
    for n,arg in zip(argument_wrappers,constructors):
        _,call=one([(i,x) for i,x in sel('invoke_enter') if x['closure']==n['node']],'argument wrapper once')
        require(call['argument']==arg['node'],'ordinary argument wrapper value differs')
    self_apps=[x for _,x in allocations if x['out']==info['self_call']['out']]
    require(len(self_apps)==2 and [x['slots'] for x in self_apps]==[
            {'$function':hole['node'],'$argument':n['node']} for n in (inner,tail_nil)],'recursive calls lost self/tail slots')
    first_i,first_app=alloc(info['first_call'],'initial Nil application');_,second_app=alloc(info['second_call'],'list application')
    require(first_app['slots']=={'$function':hole['node'],'$argument':first_nil['node']} and
            second_app['slots']=={'$function':hole['node'],'$argument':outer['node']},'outer recursive applications differ')
    first_memo_i,first_memo=one([(i,x) for i,x in sel('memo_publish') if x['destination']==first_app['node']],'initial Nil memo once')
    require(calls[0][0]<first_memo_i<calls[1][0] and scalars.get(first_memo['result'])==('i64',0),'initial Nil did not finish first with zero')

    factories=sel('case_fields_i64');require(len(factories)==4 and [x['scrutinee'] for _,x in factories]==[n['node'] for n in constructors]
            and [x['variant_index'] for _,x in factories]==[0,1,1,0],'selected recursive variants differ')
    fields=sel('sum_field_capture');require(len(fields)==2,'wildcard heads were captured or tails lost')
    activation_nodes=[]
    for (i,event),n,variant in zip(factories,constructors,(0,1,1,0)):
        arm=info['arms'][variant];allocated=nodes[event['result']]
        require(event['family']==info['family'] and event['variant']=='V'+str(variant) and event['code']==arm['code'] and
                allocated['code']==arm['code'] and allocated['opcode']=='case_fields_i64' and allocated['slots']==event['captures'],
                'selected factory Code/capture graph differs')
        cb,_=one([(j,x) for j,x in sel('callback_enter') if x['node']==event['result']],'selected factory callback once')
        require(i<cb,'selected factory callback before publication')
        mask={x['capture']:x['index'] for x in arm['field_captures']}
        require(event['field_indices']==mask and event['field_mask']==(2 if variant else 0),'selected tail-only field mask differs')
        for field in arm['field_captures']:
            _,captured=one([(j,x) for j,x in fields if x['scrutinee']==n['node'] and x['capture']==field['capture']],'tail capture once')
            require(captured['field_index']==1 and captured['node']==n['slots']['1']==event['captures'][field['capture']] and
                    captured['family']==captured['layout']==info['family'],'selected original tail edge differs')
        activation_nodes.append(event['result'])
    require(len(set(activation_nodes))==4 and sum(x['opcode']=='case_fields_i64' for _,x in allocations)==4,
            'repeated factory activation cloned/reused incorrectly')

    shared_memo_i,shared_memo=one([(i,x) for i,x in sel('memo_publish') if x['destination']==shared],'shared RHS memo once')
    require(shared_memo['result']==body,'shared RHS memo lost one callable')
    one([x for _,x in sel('invoke_enter') if x['closure']==outer_shared],'shared ordinary wrapper called once')
    shared_calls=[(i,x) for i,x in sel('invoke_enter') if x['closure']==body]
    require(len(shared_calls)==3 and scalars.get(shared_calls[0][1]['argument'])==('bool',True) and
            shared_memo_i<shared_calls[0][0]<calls[0][0]<first_memo_i<shared_calls[1][0]<shared_calls[2][0],
            'initial Nil invoked Int or shared calls lost Bool/Int/Int order')
    shared_frames=[x for _,x in sel('frame_enter') if x['context'].get('name')==graph['shared_code']]
    require(len(shared_frames)==3 and all(x['context'].get('node')==body for x in shared_frames),
            'same shared registered callback must run Bool/Int/Int')
    step_demand_i,_=one([(i,x) for i,x in sel('update_pin') if x['node']==step['node']],'step demand once')
    step_memo_i,step_memo=one([(i,x) for i,x in sel('memo_publish') if x['destination']==step['node']],'step memo once')
    step_wrap_i,step_wrap=one([(i,x) for i,x in sel('invoke_enter') if x['closure']==step_wrapper['node']],
                             'step annotation wrapper once')
    require(step['slots']['$function']==step_wrapper['node'] and first_memo_i<step_demand_i<step_wrap_i<step_memo_i,
            'initial Nil demanded step or step annotation was erased')
    step_apps=[(i,x) for i,x in allocations if x['out']==info['step_call']['out']]
    require(len(step_apps)==2 and len({x['node'] for _,x in step_apps})==2 and
            all(x['state']=='APPLICATION' and x['slots']['$function']==step['node'] and i>first_memo_i for i,x in step_apps),
            'both Cons calls must retain original pending step')
    demand_i,_=one([(i,x) for i,x in sel('update_pin') if x['node']==bonus['node']],'bonus demand once')
    cb_i,_=one([(i,x) for i,x in sel('callback_enter') if x['node']==bonus['node']],'bonus callback once')
    memo_i,memo=one([(i,x) for i,x in sel('memo_publish') if x['destination']==bonus['node']],'bonus memo once')
    require(first_memo_i<shared_calls[1][0]<demand_i<cb_i<memo_i and scalars.get(memo['result'])==('i64',21),
            'initial Nil or eager argument forced bonus, or bonus result differs')
    if name=='pending-step':
        _,step_closure=alloc(info['step_closure'],'real step closure')
        require(step['slots']['$argument']==step_wrap['argument']==step_memo['result']==step_closure['node'] and
                step_closure['env_id']==0 and step_closure['slots']=={
                    info['step_bonus_capture']:bonus['node'],info['step_view']['capture']:shared},
                'pending annotation did not preserve actual step closure/captures')
        step_calls=[(i,x) for i,x in sel('invoke_enter') if x['closure']==step_closure['node']]
        require(len(step_calls)==2 and step_memo_i<step_calls[0][0] and
                [x['argument'] for _,x in step_calls]==[x['slots']['$argument'] for _,x in step_apps] and
                all(scalars.get(x['argument'])==('i64',0) for _,x in step_calls),
                'same real step closure must run twice with zero')
        step_frames=[x for _,x in sel('frame_enter') if x['context'].get('name')==info['step_closure']['function']]
        require(len(step_frames)==2 and all(x['context']['node']==step_closure['node'] for x in step_frames),
                'step registered callback/closure identity differs')
        step_handoffs=[x for _,x in sel('closure_capture_handoff') if x['node']==step_closure['node']]
        require(len(step_handoffs)==2 and all(set(x['owners'])==set(step_closure['slots']) for x in step_handoffs),
                'step full scalar/view owner handoffs differ')
        wrappers=[x for _,x in allocations if x['out']==info['step_argument_wrapper']['out']]
        require(len(wrappers)==2 and all(x['code']==info['step_argument_wrapper']['function'] for x in wrappers),
                'step parameter wrappers erased')
        for wrapper_node,(_,call) in zip(wrappers,step_calls):
            _,event=one([(i,x) for i,x in sel('invoke_enter') if x['closure']==wrapper_node['node']],
                        'step parameter wrapper invoked once')
            require(event['argument']==call['argument'],'step parameter wrapper argument differs')
        int_apps=[(i,x) for i,x in allocations if x['out']==info['int_call']['out']]
        additions_step=[(i,x) for i,x in allocations if x['out']==info['step_add']['out']]
        require(len(int_apps)==len(additions_step)==2 and len({x['node'] for _,x in additions_step})==2,
                'two distinct step argument thunks required')
        for (_,app),(add_i,add),(call_i,call),(step_call_i,_) in zip(int_apps,additions_step,shared_calls[1:],step_calls):
            require(add['state']=='THUNK' and add['code']==info['step_add']['code'] and
                    app['slots']=={'$function':shared,'$argument':add['node']} and call['argument']==add['node'] and
                    first_memo_i<step_call_i<add_i<call_i,'shared Int argument must remain actual lazy step addition')
            ademand,_=one([(i,x) for i,x in sel('update_pin') if x['node']==add['node']],'step addition demand once')
            amemo,arow=one([(i,x) for i,x in sel('memo_publish') if x['destination']==add['node']],'step addition memo once')
            require(call_i<ademand<amemo and scalars.get(arow['result'])==('i64',21),
                    'step addition forced before shared call or produced wrong value')
            _,frow=one([(i,x) for i,x in sel('frame_enter') if x['context'].get('node')==add['node'] and
                       x['context'].get('name')==add['code']],'step addition actual callback')
            forced=[x for _,x in sel('ir_force_result') if x['frame']==frow['frame']]
            require(len(forced)==2 and scalars.get(forced[0]['result'])==('i64',0) and forced[1]['result']==memo['result'],
                    'both step additions must use original shared bonus memo')
        callable_node=step_closure['node'];callable_origin='concrete closure observed'
    else:
        require(step['slots']['$argument']==step_wrap['argument']==shared and step_memo['result']==body and
                [x['argument'] for _,x in shared_calls[1:]]==[bonus['node'],bonus['node']] and
                all(x['slots']['$argument']==bonus['node'] for _,x in step_apps) and
                step_memo_i<shared_calls[1][0],'ordinary alias must reuse actual shared Instance after wrapper memo')
        require(nodes[body]['env_id']==observed_access['#i64']['origin_env']!=0,
                'alias target generic origin must not be rebranded concrete')
        callable_node=body;callable_origin='shared generic callable with acquired Int view observed'
    step_results=[]
    if name=='pending-step':
        # This case has a nested force of addInt(x,bonus), so its own application
        # memo follows the bonus memo. Preserve the original stronger ordering.
        for _,app in step_apps:
            mi,row=one([(i,x) for i,x in sel('memo_publish') if x['destination']==app['node']],'step call memo once')
            require(mi>memo_i and scalars.get(row['result'])==('i64',21),'both step calls must complete21 after shared bonus')
            step_results.append(row['result'])
    else:
        # Shared identity raw-returns its ordinary parameter-wrapper application.
        # The wrapper raw-returns the original bonus Handle; Force follows it to
        # READY21, validates the whole chain, then publishes FIRST-to-LAST.
        # Thus the first step app and wrapper app memo *before* bonus's memo,
        # but all three target the same already-ready scalar. No pending target
        # or arbitrary publication reordering is accepted here.
        parameter_wrappers=[x for _,x in allocations if x['out']==graph['parameter_wrapper']['out']]
        parameter_apps=[x for _,x in allocations if x['out']==graph['parameter_application']['out']]
        require(len(parameter_wrappers)==len(parameter_apps)==3,'shared parameter wrapper activation census differs')
        bonus_raw_i,bonus_raw=one([(i,x) for i,x in sel('raw_return') if x['source']==bonus['node']],
                                'bonus raw scalar return once')
        scalar_i,scalar_event=one([(i,x) for i,x in sel('scalar_value') if x['node']==memo['result']],
                                 'one actual bonus scalar value')
        require(cb_i<scalar_i<bonus_raw_i and scalar_event['kind']=='i64' and scalar_event['value']==21 and
                nodes[memo['result']]['state']=='READY' and bonus_raw['result']==memo['result'] and
                bonus_raw['result_state']=='READY','alias chain must follow actual ready bonus return')
        for index,((_,app),(call_i,call),frame,wrapper,inner) in enumerate(zip(
                step_apps,shared_calls[1:],shared_frames[1:],parameter_wrappers[1:],parameter_apps[1:])):
            require(wrapper['code']==graph['parameter_wrapper']['function'] and
                    wrapper['frame']==inner['frame']==frame['frame'] and inner['state']=='APPLICATION' and
                    inner['slots']=={'$function':wrapper['node'],'$argument':bonus['node']},
                    'alias shared parameter wrapper/source callback differs')
            raw_i,raw=one([(i,x) for i,x in sel('invoke_raw_return') if x['closure']==body and x['result']==inner['node']],
                          'shared identity raw parameter application once')
            invoke_i,invoke=one([(i,x) for i,x in sel('invoke_enter') if x['closure']==wrapper['node']],
                                'shared parameter wrapper invoked once')
            wrapper_frame_i,wrapper_frame=one([(i,x) for i,x in sel('frame_enter') if
                x['context'].get('node')==wrapper['node']],'shared parameter wrapper actual callback once')
            return_i,returned=one([(i,x) for i,x in sel('invoke_raw_return') if x['closure']==wrapper['node']],
                                  'shared parameter wrapper raw return once')
            require(call_i<raw_i<invoke_i<wrapper_frame_i<return_i and raw['argument']==invoke['argument']==
                    returned['argument']==returned['result']==bonus['node'] and
                    wrapper_frame['context']['name']==graph['parameter_wrapper']['function'],
                    'alias raw-return chain must preserve original bonus owner')
            chain=[app['node'],inner['node']]+([bonus['node']] if index==0 else [])
            pins=[one([(i,x) for i,x in sel('update_pin') if x['node']==node],'alias chain pin once') for node in chain]
            memos=[one([(i,x) for i,x in sel('memo_publish') if x['destination']==node],'alias chain memo once') for node in chain]
            require(pins[0][0]<call_i<raw_i<pins[1][0]<invoke_i and
                    len({x['depth'] for _,x in pins})==1 and
                    all(row['result']==memo['result'] and row['pin']==pin['pin'] and row['depth']==pin['depth']
                        for (_,row),(_,pin) in zip(memos,pins)),
                    'alias memo chain must preserve exact final scalar/pins/depth')
            order=[i for i,_ in memos]
            require(order==sorted(order) and len(set(order))==len(order),
                    'alias memo publications must remain FIRST-to-LAST')
            if index==0:
                require(return_i<demand_i==pins[2][0]<cb_i<scalar_i<bonus_raw_i<order[0] and
                        order[-1]==memo_i and bonus_raw['home_pin']==pins[2][1]['pin'],
                        'alias initial demand/evaluation/publication order differs')
            else:
                require(memo_i<call_i<return_i<order[0],
                        'second alias call must reuse already memoized bonus')
            for node,(mi,row),(_,pin) in zip(chain,memos,pins):
                si,slot=one([(i,x) for i,x in sel('slot_install') if x['host']==node and x['field']=='$target'],
                            'alias exact memo slot once')
                require(si==mi-1 and slot['target']==memo['result'] and slot['target_state']=='READY' and
                        slot['reason']=='publication','alias memo slot must publish actual READY21')
                ui,unpin=one([(i,x) for i,x in sel('update_unpin') if x['node']==node],'alias chain unpin once')
                require(ui>order[-1] and unpin['pin']==pin['pin'] and unpin['depth']==pin['depth'],
                        'alias chain unpin must follow all publications')
            force_i,forced=one([(i,x) for i,x in sel('ir_force_result') if x['frame']==app['frame'] and
                               x['source_variable']==info['step_call']['out']],'alias consumer Force result once')
            require(force_i>order[-1] and forced['result']==memo['result'] and forced['layout']=='#i64',
                    'alias consumer Force must return the exact final scalar')
            step_results.append(memo['result'])
    additions=[x for _,x in allocations if x['out']==info['cons_add']['out']]
    require(len(additions)==2 and len({x['node'] for x in additions})==2,'recursive addition activations differ')
    for node,wanted,step_result in zip(additions,(42,21),step_results):
        require(node['code']==info['cons_add']['code'],'recursive addition Code differs')
        _,frame=one([(i,x) for i,x in sel('frame_enter') if x['context'].get('node')==node['node'] and
                     x['context'].get('name')==node['code']],'recursive addition callback once')
        forces=[(i,x) for i,x in sel('ir_force_result') if x['frame']==frame['frame']]
        add_memo_i,add_memo=one([(i,x) for i,x in sel('memo_publish') if x['destination']==node['node']],
                              'recursive addition memo once')
        require(len(forces)==2 and forces[0][1]['result']==step_result and
                memo_i<forces[0][0]<forces[1][0]<add_memo_i and scalars.get(add_memo['result'])==('i64',wanted),
                'recursive addition lost captured21 or exact unwind result')
    _,root_add=alloc(info['root_add'],'main addition')
    _,root_frame=one([(i,x) for i,x in sel('frame_enter') if x['context'].get('node')==root_add['node'] and
                     x['context'].get('name')==root_add['code']],'main addition callback once')
    root_forces=[(i,x) for i,x in sel('ir_force_result') if x['frame']==root_frame['frame']]
    require(len(root_forces)==2 and [scalars.get(x['result']) for _,x in root_forces]==[('i64',0),('i64',42)] and
            first_memo_i<root_forces[0][0]<calls[1][0]<root_forces[1][0],
            'main addition did not consume initial zero then complete recursive42')
    return {'recursive_closure':closure['node'],'recursive_code':info['code'],'registered_code_id':info['code_id'],
            'arguments':[n['node'] for n in constructors],'variants':[0,1,1,0],'recursive_calls':4,
            'factory_nodes':activation_nodes,'step_node':step['node'],'step_callable_node':callable_node,
            'step_origin_evidence':callable_origin,'step_demand_event':step_demand_i,'step_memo_event':step_memo_i,
            'bonus_node':bonus['node'],'bonus_evaluations':1,'bonus_memos':1,
            'shared_node':shared,'shared_body':body,'shared_call_kinds':['Bool','Int','Int'],'actual_views':observed_access,
            'initial_nil_memo_event':first_memo_i,'bonus_demand_event':demand_i,'access_observation_scope':ACCESS_SCOPE,
            'memory':e['memory'],'memory_categories':e['memory_categories']}


def copied_controls(evaluation,info,graph):
    """Only copied-report observer controls; never extra source/native runs."""
    observe(evaluation,info,graph);results=[]
    def event(report,kind,predicate=lambda x:True):
        return one([x for x in report['events'] if x['event']==kind and predicate(x)],'exact copied control event')
    def alloc(report,op):
        return event(report,'allocate',lambda x:x['out']==op['out'])
    def reject(name,mutation,expected):
        changed=copy.deepcopy(evaluation);mutation(changed);changed['events_emitted']=len(changed['events'])
        try:observe(changed,info,graph)
        except AssertionError as exc:
            require(expected in str(exc),name+' rejected at unrelated guard: '+str(exc))
            results.append({'control':name,'status':'rejected','guard':expected})
        else:raise AssertionError(name+' copied report accepted')
    reject('wrong-fill-target',lambda r:event(r,'fill').__setitem__('target',-1),'original Fill target/ticket differs')
    reject('wrong-self-slot',lambda r:alloc(r,info['closure'])['slots'].__setitem__(info['self_capture'],-1),
           'recursive pending wrapper/self/callable/scalar graph differs')
    reject('wrong-ordinary-callable-slot',lambda r:alloc(r,info['closure'])['slots'].__setitem__(info['callable_capture'],-1),
           'recursive pending wrapper/self/callable/scalar graph differs')
    if info['bonus_capture']:
        reject('wrong-bonus-slot',lambda r:alloc(r,info['closure'])['slots'].__setitem__(info['bonus_capture'],-1),
               'recursive pending wrapper/self/callable/scalar graph differs')
    reject('recursive-code-substitution',lambda r:alloc(r,info['closure']).__setitem__('code','other-code'),
           'recursive closure source Code/opcode differs')
    reject('missing-capture-handoff',lambda r:next(x for x in r['events'] if x['event']=='closure_capture_handoff' and
           x['node']==alloc(r,info['closure'])['node'])['owners'].pop(info['callable_capture']),
           'four recursive activations must acquire complete distinct capture owners')
    reject('callback-local-instantiation',lambda r:next(x for x in r['events'] if x['event']=='instantiate').__setitem__('frame',-1),
           'view acquired inside callback or detached from shared node')
    def wrong_access(report):
        uses={x['use']:x for x in report['events'] if x['event']=='instantiate'}
        uses[graph['uses']['#i64']['row']['id']]['new_access']=uses[graph['uses']['#bool']['row']['id']]['new_access']
    reject('partial-or-wrong-view-access',wrong_access,'captured generic Access was relabelled E0 or lost full vector')
    reject('host-relabelled-as-generic',lambda r:alloc(r,info['closure']).__setitem__('env_id',-1),
           'recursive host must be concrete without rebranding captured origin')
    reject('wrong-recursive-callback-node',lambda r:next(x for x in r['events'] if x['event']=='frame_enter' and
           x['context'].get('name')==info['code'])['context'].__setitem__('node',-1),
           'same closure/Code must invoke Nil/Cons/Cons/Nil')
    reject('wrong-self-tail-edge',lambda r:next(x for x in r['events'] if x['event']=='allocate' and
           x['out']==info['self_call']['out'])['slots'].__setitem__('$argument',-1),'recursive calls lost self/tail slots')
    reject('wrong-initial-nil-transition',lambda r:next(x for x in r['events'] if x['event']=='case_fields_i64').__setitem__('variant_index',1),
           'selected recursive variants differ')
    reject('wildcard-head-capture',lambda r:next(x for x in r['events'] if x['event']=='sum_field_capture').__setitem__('field_index',0),
           'selected original tail edge differs')
    def early_int(report):
        shared=event(report,'generic_seal')['node'];body=event(report,'allocate',lambda x:x['node']==shared)['slots']['$argument']
        calls=[x for x in report['events'] if x['event']=='invoke_enter' and x['closure']==body]
        report['events'].remove(calls[1])
        index=next(i for i,x in enumerate(report['events']) if x['event']=='invoke_enter' and x['closure']==alloc(report,info['closure'])['node'])
        report['events'].insert(index,calls[1])
    reject('initial-nil-invokes-int',early_int,'initial Nil invoked Int or shared calls lost Bool/Int/Int order')
    def early_bonus(report):
        node=alloc(report,info['bonus'])['node'];row=event(report,'update_pin',lambda x:x['node']==node)
        report['events'].remove(row);report['events'].insert(0,row)
    reject('initial-nil-demands-bonus',early_bonus,'initial Nil or eager argument forced bonus, or bonus result differs')
    def extra_bonus(report,kind,key):
        node=alloc(report,info['bonus'])['node'];report['events'].append(copy.deepcopy(event(report,kind,lambda x:x[key]==node)))
    reject('duplicate-bonus-callback',lambda r:extra_bonus(r,'callback_enter','node'),'bonus callback once')
    reject('duplicate-bonus-memo',lambda r:extra_bonus(r,'memo_publish','destination'),'bonus memo once')
    def early_step(report):
        row=event(report,'update_pin',lambda x:x['node']==alloc(report,info['step'])['node'])
        report['events'].remove(row);report['events'].insert(0,row)
    reject('initial-nil-demands-step',early_step,'initial Nil demanded step or step annotation was erased')
    reject('duplicate-step-memo',lambda r:r['events'].append(copy.deepcopy(event(r,'memo_publish',
           lambda x:x['destination']==alloc(r,info['step'])['node']))),'step memo once')
    reject('step-memo-wrong-callable',lambda r:event(r,'memo_publish',
           lambda x:x['destination']==alloc(r,info['step'])['node']).__setitem__('result',-1),
           'pending annotation did not preserve actual step closure/captures' if info['facts']['name']=='pending-step' else
           'ordinary alias must reuse actual shared Instance after wrapper memo')
    reject('step-call-target-substitution',lambda r:next(x for x in r['events'] if x['event']=='allocate' and
           x['out']==info['step_call']['out'])['slots'].__setitem__('$function',-1),
           'both Cons calls must retain original pending step')
    if info['facts']['name']=='pending-step':
        reject('step-closure-code-substitution',lambda r:alloc(r,info['step_closure']).__setitem__('code','wrong'),
               'real step closure source Code/opcode differs')
        reject('step-closure-view-substitution',lambda r:alloc(r,info['step_closure'])['slots'].__setitem__(info['step_view']['capture'],-1),
               'pending annotation did not preserve actual step closure/captures')
        def eager_add(report):
            node=next(x for x in report['events'] if x['event']=='allocate' and x['out']==info['step_add']['out'])['node']
            row=event(report,'update_pin',lambda x:x['node']==node)
            report['events'].remove(row);report['events'].insert(0,row)
        reject('shared-step-argument-eager',eager_add,'step addition forced before shared call or produced wrong value')
    else:
        def wrong_generic_origin(report):
            shared=event(report,'generic_seal')['node'];body=event(report,'allocate',lambda x:x['node']==shared)['slots']['$argument']
            event(report,'allocate',lambda x:x['node']==body).__setitem__('env_id',0)
        reject('alias-target-rebranded-E0',wrong_generic_origin,'alias target generic origin must not be rebranded concrete')
    if info['facts']['name']=='view-alias':
        def first_alias_app(report):
            return next(x for x in report['events'] if x['event']=='allocate' and x['out']==info['step_call']['out'])['node']
        reject('alias-memo-pending-target',lambda r:event(r,'memo_publish',lambda x:x['destination']==first_alias_app(r)).__setitem__(
            'result',alloc(r,info['bonus'])['node']),'alias memo chain must preserve exact final scalar/pins/depth')
        reject('alias-memo-pin-substitution',lambda r:event(r,'memo_publish',lambda x:x['destination']==first_alias_app(r)).__setitem__(
            'pin',-1),'alias memo chain must preserve exact final scalar/pins/depth')
        reject('alias-memo-slot-target',lambda r:event(r,'slot_install',lambda x:x['host']==first_alias_app(r) and
            x['field']=='$target').__setitem__('target',-1),'alias memo slot must publish actual READY21')
        def reorder_alias_memos(report):
            a=event(report,'memo_publish',lambda x:x['destination']==first_alias_app(report))
            b=event(report,'memo_publish',lambda x:x['destination']==alloc(report,info['bonus'])['node'])
            ai=report['events'].index(a);bi=report['events'].index(b)
            report['events'][ai],report['events'][bi]=b,a
        reject('alias-memo-order-swapped',reorder_alias_memos,'alias memo publications must remain FIRST-to-LAST')
        def alias_wrapper(report):
            return [x for x in report['events'] if x['event']=='allocate' and x['out']==graph['parameter_wrapper']['out']][1]
        reject('alias-wrapper-raw-result',lambda r:event(r,'invoke_raw_return',lambda x:x['closure']==alias_wrapper(r)['node']).__setitem__(
            'result',-1),'alias raw-return chain must preserve original bonus owner')
        reject('alias-wrapper-callback-substitution',lambda r:event(r,'frame_enter',lambda x:x['context'].get('node')==
            alias_wrapper(r)['node'])['context'].__setitem__('name','wrong'),'alias raw-return chain must preserve original bonus owner')
        def eager_alias_bonus(report):
            bonus=alloc(report,info['bonus'])['node'];row=event(report,'update_pin',lambda x:x['node']==bonus)
            report['events'].remove(row)
            call=event(report,'invoke_enter',lambda x:x['closure']==alias_wrapper(report)['node'])
            report['events'].insert(report['events'].index(call),row)
        reject('alias-bonus-demand-before-wrapper-return',eager_alias_bonus,'alias initial demand/evaluation/publication order differs')
    reject('shared-callback-node-substitution',lambda r:next(x for x in r['events'] if x['event']=='frame_enter' and
           x['context'].get('name')==graph['shared_code'])['context'].__setitem__('node',-1),
           'same shared registered callback must run Bool/Int/Int')
    reject('raised-guard-budget',lambda r:r.__setitem__('guard_work_limit',67_108_865),'native guard failure/work differs')
    reject('missing-guard-evidence',lambda r:r.__setitem__('guards_checked_mask',0),'native guard failure/work differs')
    reject('nonzero-live-pending',lambda r:r['memory_categories']['pending'].__setitem__('live_blocks',1),'ledger arithmetic differs')
    return results



def structure_controls(capture,plan,generated,name):
    """Copied source/plan negatives; no compiler/native execution or admission claim."""
    structure(capture,plan,generated,name);results=[]
    def reject(label,mutate,expected):
        c,p=copy.deepcopy(capture),copy.deepcopy(plan);g=generated
        g=mutate(c,p,g)
        try:structure(c,p,g,name)
        except AssertionError as exc:
            require(expected in str(exc),label+' failed at unrelated guard: '+str(exc))
            results.append({'control':label,'status':'rejected','guard':expected})
        else:raise AssertionError(label+' malformed structural copy accepted')
    def knot_change(field,value):
        def change(c,p,g):p['binding']['source_map']['knot_map'][0]['captures'][field]=value;return g
        return change
    reject('missing-callable-evidence',knot_change('callables',[]),'ordinary callable capture inventory differs')
    reject('invented-recursive-view',knot_change('views',[{'invented':True}]),'ordinary callable capture inventory differs')
    def wrong_type(c,p,g):
        p['binding']['source_map']['knot_map'][0]['captures']['callables'][0]['type']=INT;return g
    reject('scalarized-callable-evidence',wrong_type,'ordinary callable capture inventory differs')
    def wrong_occurrence(c,p,g):
        p['binding']['source_map']['knot_map'][0]['captures']['callables'][0]['occurrences'][0]['path'].append('value');return g
    reject('wrong-callable-occurrence',wrong_occurrence,'ordinary callable capture inventory differs')
    def erase_step(c,p,g):
        f=source_facts(c,name);at(c['normalization']['raw_normalized'],f['step_path'])['function']={'tag':'int64','value':0};return g
    reject('erased-step-annotation',erase_step,'ordinary step annotation application must be preserved')
    def wrong_owner(c,p,g):
        f=source_facts(c,name);k=p['binding']['source_map']['knot_map'][0]
        cl=source_allocation(p,f['function'],'closure')
        carrier=one([x for x in p['binding']['source_map']['carrier_map'] if x['source']==address(f['function'])],'control carrier')
        r=one([x for x in carrier['mono_captures'] if x['binder']==f['step']['id']],'control callable')
        cl['captures'][r['capture']]=k['self_owner'];return g
    reject('substituted-callable-owner',wrong_owner,'recursive self/ordinary callable Reference differs')
    def invent_code(c,p,g):
        f=source_facts(c,name)
        carrier=one([x for x in p['binding']['source_map']['carrier_map'] if x['source']==address(f['function'])],'control carrier')
        row=one([x for x in carrier['mono_captures'] if x['binder']==f['step']['id']],'control callable')
        p['program']['types'][row['layout'][1:]]['code']='invented';return g
    reject('invented-callable-Code',invent_code,'ordinary callable must retain complete unknown-Code scalar arrow')
    def instantiate_callback(c,p,g):
        f=source_facts(c,name);cl=source_allocation(p,f['function'],'closure')
        p['program']['functions'][cl['function']]['body'].append({'op':'instantiate'});return g
    reject('reconstructed-callback-view',instantiate_callback,'recursive callback must not instantiate')
    def wrong_registration(c,p,g):
        return g.replace('.body = rt8_body_0 }','.body = rt8_body_1 }',1)
    reject('substituted-registered-callback',wrong_registration,'actual generated callback definitions/registrations differ')
    return results


def run_case(args,output,env,name):
    source=SOURCES[name];inputs=output/(name+'-inputs');inputs.mkdir()
    (inputs/'SharedPoly.emlf').write_text(SHARED,encoding='utf-8')
    entry=inputs/'main.emlf';entry.write_text(source,encoding='utf-8');target=output/name
    command=[sys.executable,'-B',str(BASE/'run_source_v8.py'),str(entry),'--module-root',str(inputs),
             '--ghc',args.ghc,'--cc',args.cc,'--output',str(target)]
    build.run(command,output,name,cwd=BASE,env=env,wall=1200,cpu=900,memory=16<<30,
              termination_grace=15,stdout_limit=1<<20,stderr_limit=1<<20,file_limit=64<<20)
    require(not bounded_read(output/(name+'.stderr'),1<<20),'successful CLI wrote stderr')
    result=read_json(target/'result.json');evaluation=read_json(target/'native/run.stdout')
    require(result['status']=='complete' and result['failure_policy']=='retain' and result['native']==evaluation and
            'placement' not in result,'fresh CLI result differs')
    capture=read_json(target/'capture.stdout');verified=read_json(target/'verification.json')
    require(verified['fragment_admitted'] and verified['normalization_replay']=='all exact independent fields match' and
            capture['checked_type']==INT,'fresh original checking/replay differs')
    plan=read_json(target/'planned.json',8<<20);require(plan['binding']['mode']=='coarse-owned','default plan mode differs')
    generated=bounded_read(target/'native/ir8_runtime_generated.c',8<<20).decode('utf-8')
    info=structure(capture,plan,generated,name);graph=shared_graph(plan,verified,capture,info)
    result={'case':name,'status':'passed','observation':observe(evaluation,info,graph),
            'copied_report_controls':copied_controls(evaluation,info,graph),
            'copied_structure_controls':structure_controls(capture,plan,generated,name),
            'source_hashes':{'main.emlf':build.sha(source.encode()),'SharedPoly.emlf':build.sha(SHARED.encode())}}
    build.save(target/'callable-capture-observations.json',result)
    print(name+': PASS (ordinary callable capture, preserved annotation, lazy step/bonus once, shared Bool/Int/Int, Int42, zero ledgers)',flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc',required=True);parser.add_argument('--cc',default='cc')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.absolute()
    require(output.resolve()==output and output!=BASE.parents[2] and BASE.parents[2] not in output.parents,
            'output must be canonical, fresh and outside this checkout')
    output.mkdir(parents=True,exist_ok=False);env=cli.environment(output);build.SUITE_DEADLINE=time.monotonic()+2700
    results=[]
    try:
        for name in SOURCES:results.append(run_case(args,output,env,name))
    except BaseException as exc:
        try:build.save(output/'failure.json',{'error':type(exc).__name__+': '+str(exc),'completed_cases':[r['case'] for r in results]})
        except BaseException as persistence:exc.add_note('Failure persistence also failed: '+repr(persistence))
        raise
    build.save(output/'results.json',results);return 0


if __name__=='__main__':
    raise SystemExit(main())
