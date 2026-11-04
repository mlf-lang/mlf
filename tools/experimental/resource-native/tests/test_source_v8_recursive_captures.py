#!/usr/bin/env python3
"""One fresh recursive function with a pending scalar and full shared-view capture.

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
SOURCE=('import SharedPoly\ndata IntList = Nil | Cons Int IntList;\n'
        'let bonus = addInt 20 1 in\n'
        'let rec sumBonus : IntList -> Int = \\xs -> case xs of { Nil -> 0; Cons _ rest -> addInt (sharedId bonus) (sumBonus rest) } in\n'
        'if sharedId true then addInt (sumBonus Nil) (sumBonus (Cons 0 (Cons 0 Nil))) else 0\n')
ACCESS_SCOPE=('Capture owner events contain owner IDs, not an Access trace. Full view preservation combines '
              'fresh metadata/source bindings, actual instantiate rows, stored-slot/handoff evidence and runtime guards; '
              'a concrete recursive host never rebrands the captured generic origin as E0.')


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


def source_facts(capture):
    raw=capture['normalization']['raw_normalized']
    path,term=one([(p,n) for p,n in walk(raw) if isinstance(n,dict) and n.get('tag')=='letrec'],'one recursive source')
    binding=one(term['bindings'],'one recursive binder');rhs_path=path+['bindings','0','value'];rhs=binding['value']
    annotation=binding['type'];parent=at(raw,path[:-1])
    require(path[-1]=='body' and parent['tag']=='let' and primitive(parent['value'],20,1),
            'bonus must be one lexical pending21 before the recursive definition')
    bonus_path=path[:-1]+['value'];bonus=parent['name']
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
    int_path,int_call=args[0];self_path,self_call=args[1]
    require(int_call['tag']=='application' and int_call['function']['tag']=='type_application' and
            var(int_call['argument'],bonus),'Cons must pass original bonus to complete shared Int view')
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
                cons_path=cons_path,self_call=self_path,int_call=int_path,bool_call=bool_path,
                root_add=root_add_path,first_call=root_args[0][0],second_call=root_args[1][0])



def carrier_allocation(plan,path,kind):
    """A conditional branch wrapper and its primitive keep the same source path."""
    mapping=plan['binding']['source_map'];p=plan['program']
    carrier=one([r for r in mapping['carrier_map'] if r['source']==address(path) and r['kind']==kind],
                'one exact source carrier kind')
    return one([instruction(p,r['instruction']) for r in mapping['allocation_map'] if r['source']==address(path) and
                r['role']=='thunk' and instruction(p,r['instruction']).get('code')==carrier['ir_code']],
               'one exact source/carrier allocation')


def structure(capture,plan,generated):
    f=source_facts(capture);p=plan['program'];m=plan['binding']['source_map'];raw=f['raw']
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
    require(carrier['ir_code']==closure['function'] and carrier['type_scope'] is None and
            len(carrier['mono_captures'])==2 and len(carrier['view_captures'])==1,'recursive capture census/scope differs')
    self_cap=one([x for x in carrier['mono_captures'] if x['binder']==binding['name']['id']],'exact self capture')
    bonus_cap=one([x for x in carrier['mono_captures'] if x['binder']==f['bonus']['id']],'exact bonus capture')
    view=carrier['view_captures'][0]
    require(self_cap['layout']=='^'+knot['logical_type'] and self_cap['relation']=='down' and
            closure['captures'][self_cap['capture']]==knot['self_owner'] and
            closed_layout(p,bonus_cap['layout'])=='#i64' and closure['captures'][bonus_cap['capture']]==bonus['out'] and
            [p['types'][t]['layout'] for t in view['arguments']]==['#i64'],
            'recursive self/scalar/full Int capture contract differs')
    require(set(closure['captures'])=={self_cap['capture'],bonus_cap['capture'],view['capture']},'extra/missing recursive capture')
    int_use=one([r for r in m['use_map'] if r['source']==address(f['int_call']+['function'])],'actual source Int use')
    int_source=at(raw,f['int_call']+['function'])
    require(knot['captures']=={'policy':'closed-scalar-shared-view-captures/1',
        'scalars':[{'binding':f['bonus'],'type':INT,'occurrences':[address(f['int_call']+['argument'])]}],
        'views':[{'definition':int_use['definition'],'binding':int_source['value']['name'],'arguments':[INT],
                  'instantiated_type':{'tag':'arrow','from':INT,'to':INT},'uses':[int_use['use']]}]} and
        view['definition']==int_use['definition'] and view['binder']==int_source['value']['name']['id'] and
        view['occurrences']==[int_use['use']], 'recursive capture evidence differs from exact free occurrences')
    require(knot['function_source']==address(f['function']) and knot['self_uses']==[address(f['self_call']+['function'])],
            'recursive function/self source evidence differs')
    for record in [self_cap,bonus_cap,view]:
        require(p['functions'][closure['function']]['captures'][record['capture']]==
                {'layout':record['layout'],'relation':record['relation']},'capture layout/support contract differs')

    require(not any(n.get('op')=='instantiate' for _,n in walk(p['functions'][closure['function']]['body']) if isinstance(n,dict)),
            'recursive callback must not instantiate its captured view')
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
                self_capture=self_cap['capture'],bonus_capture=bonus_cap['capture'],view_capture=view['capture'],
                view=view,code=closure['function'],code_id=code['id'],metadata=metadata,family=physical,arms=arms,
                constructors=[r[2] for r in (first_nil,outer,inner,tail_nil)],
                self_call=source_allocation(plan,f['self_call'],'application'),
                int_call=source_allocation(plan,f['int_call'],'application'),
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
    expected={'#bool':info['facts']['bool_call']+['function'],'#i64':info['facts']['int_call']+['function']}
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
    require(uses['#i64']['source']['source_view']['kind']=='captured','recursive source must use stored Int view')
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
    resolved=one([x for x in recursive['captures'] if x['name']==info['view_capture']],'recursive full view capture metadata')
    require(resolved['type']==uses['#i64']['row']['result_type'],'stored Int capture full contract differs')
    return {'outer_code':closures[pending['function']],'shared_code':closures[pending['argument']],
            'seal_owner':seal['value'],'uses':uses,'scheme':scheme}


def observe(e,info,graph):
    require(e['schema']=='resource-ir-v8-run/1' and e['state']==e['fault']==0 and
            e['result']=={'kind':'i64','value':42} and e['scalar_result_kind']==1 and e['scalar_result']==42 and
            e['events_omitted']==0 and e['events_emitted']==len(e['events']),'complete native Int42 report required')
    require(e['guards_failed_mask']==0 and e['guards_checked_mask']==(1<<27)-1 and
            0<e['guard_work_used']<=e['guard_work_limit'],'native guard failure/work differs')
    ledger(e,True);events=e['events'];sel=lambda kind:[(i,x) for i,x in enumerate(events) if x['event']==kind]
    allocations=sel('allocate');nodes={x['node']:x for _,x in allocations}
    require(len(nodes)==len(allocations),'duplicate allocation node')
    def alloc(op,label):
        i,row=one([(i,x) for i,x in allocations if x['out']==op['out']],label+' allocation once')
        require(row['opcode']==op['op'] and row['code']==(op['function'] if op['op']=='closure' else op.get('code')),
                label+' source Code/opcode differs')
        return i,row
    bonus_i,bonus=alloc(info['bonus'],'bonus');hole_i,hole=alloc(info['hole'],'hole')
    closure_i,closure=alloc(info['closure'],'recursive closure');wrapper_i,wrapper=alloc(info['wrapper'],'RHS wrapper')
    rhs_i,rhs=alloc(info['rhs'],'recursive RHS');fill_i,fill=one(sel('fill'),'one Fill')
    require(bonus['state']=='THUNK' and hole['state']=='HOLE' and closure['state']==wrapper['state']=='CLOSURE' and
            rhs['state']=='APPLICATION' and bonus_i<hole_i<closure_i<rhs_i<fill_i and wrapper_i<rhs_i,
            'bonus/knot lazy allocation order differs')
    require(fill['hole']==hole['node'] and fill['target']==rhs['node'] and
            fill['hole_variable']==info['fill']['hole'] and fill['value_variable']==info['fill']['value'],
            'original Fill target/ticket differs')
    require(rhs['slots']=={'$function':wrapper['node'],'$argument':closure['node']} and
            closure['slots'][info['self_capture']]==hole['node'] and closure['slots'][info['bonus_capture']]==bonus['node'],
            'recursive pending wrapper/self/bonus graph differs')
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
    require(begin_i<seal_i and pending['out']==graph['seal_owner'] and pending['state']=='APPLICATION' and
            closure['slots'][info['view_capture']]==shared,'captured full view lost original shared pending node')
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
    require(observed_access['#i64']['event_index']<closure_i,'full Int view must be acquired before recursive capture publication')
    require(closure['env_id']==0,'recursive host must be concrete without rebranding captured origin')
    handoffs=[(i,x) for i,x in sel('closure_capture_handoff') if x['node']==closure['node']]
    require(len(handoffs)==4 and all(set(x['owners'])==set(closure['slots']) and x['protocol']=='repeat' for _,x in handoffs) and
            len({owner for _,x in handoffs for owner in x['owners'].values()})==12,
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
            [x['argument'] for _,x in shared_calls[1:]]==[bonus['node'],bonus['node']] and
            shared_memo_i<shared_calls[0][0]<calls[0][0]<first_memo_i<shared_calls[1][0]<shared_calls[2][0],
            'initial Nil invoked Int or shared calls lost Bool/Int/Int order')
    int_apps=[x for _,x in allocations if x['out']==info['int_call']['out']]
    require(len(int_apps)==2 and len({x['node'] for x in int_apps})==2 and
            all(x['slots']=={'$function':shared,'$argument':bonus['node']} for x in int_apps) and
            all(i>first_memo_i for i,x in allocations if x['out']==info['int_call']['out']),
            'Int applications lost same captured view/bonus')
    demand_i,_=one([(i,x) for i,x in sel('update_pin') if x['node']==bonus['node']],'bonus demand once')
    cb_i,_=one([(i,x) for i,x in sel('callback_enter') if x['node']==bonus['node']],'bonus callback once')
    memo_i,memo=one([(i,x) for i,x in sel('memo_publish') if x['destination']==bonus['node']],'bonus memo once')
    require(first_memo_i<shared_calls[1][0]<demand_i<cb_i<memo_i and scalars.get(memo['result'])==('i64',21),
            'initial Nil or eager argument forced bonus, or bonus result differs')
    for app in int_apps:
        _,row=one([(i,x) for i,x in sel('memo_publish') if x['destination']==app['node']],'Int application memo once')
        require(row['result']==memo['result'],'both captured Int calls must reuse one bonus scalar')
    additions=[x for _,x in allocations if x['out']==info['cons_add']['out']]
    require(len(additions)==2 and len({x['node'] for x in additions})==2,'recursive addition activations differ')
    for node,wanted in zip(additions,(42,21)):
        require(node['code']==info['cons_add']['code'],'recursive addition Code differs')
        _,frame=one([(i,x) for i,x in sel('frame_enter') if x['context'].get('node')==node['node'] and
                     x['context'].get('name')==node['code']],'recursive addition callback once')
        forces=[(i,x) for i,x in sel('ir_force_result') if x['frame']==frame['frame']]
        add_memo_i,add_memo=one([(i,x) for i,x in sel('memo_publish') if x['destination']==node['node']],
                              'recursive addition memo once')
        require(len(forces)==2 and forces[0][1]['result']==memo['result'] and
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
            'factory_nodes':activation_nodes,'bonus_node':bonus['node'],'bonus_evaluations':1,'bonus_memos':1,
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
           'recursive pending wrapper/self/bonus graph differs')
    reject('wrong-bonus-slot',lambda r:alloc(r,info['closure'])['slots'].__setitem__(info['bonus_capture'],-1),
           'recursive pending wrapper/self/bonus graph differs')
    reject('captured-view-node-substitution',lambda r:alloc(r,info['closure'])['slots'].__setitem__(info['view_capture'],-1),
           'captured full view lost original shared pending node')
    reject('recursive-code-substitution',lambda r:alloc(r,info['closure']).__setitem__('code','other-code'),
           'recursive closure source Code/opcode differs')
    reject('missing-capture-handoff',lambda r:next(x for x in r['events'] if x['event']=='closure_capture_handoff' and
           x['node']==alloc(r,info['closure'])['node'])['owners'].pop(info['bonus_capture']),
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
    reject('missing-guard-evidence',lambda r:r.__setitem__('guards_checked_mask',0),'native guard failure/work differs')
    reject('nonzero-live-pending',lambda r:r['memory_categories']['pending'].__setitem__('live_blocks',1),'ledger arithmetic differs')
    return results



# Selected from the actual healthy Stage14 coarse entry, before any fuel trial.
FAULT_FUEL=19
FAULT_REASON=('The actual coarse entry consumes seven ticks through root/begin/shared RHS and drops; seal and accessors do not tick. '
              'Bonus thunk, hole, self retain, wrapper closure, view retain, Int instantiate, recursive closure, view drop, '
              'RHS application, two drops and Fill add twelve. Fill is tick19; the next drop attempts tick20. '
              'Verify the actual filled live cycle and fault4; preserve any mismatch without searching another threshold.')


def run_fault_pair(program,output,env,info):
    """Use the single source-selected fixed budget, never a search."""
    fuel,reason=FAULT_FUEL,FAULT_REASON
    require(type(fuel) is int and fuel>0 and reason,'explicit selected fuel/reason required')
    output.mkdir();build.save(output/'selection.json',{'fuel':fuel,'reason':reason,'selected_before_launch':True})
    reports=[]
    for policy in ('retain','destroy-terminal'):
        stdout,stderr=build.run([str(program),'--fuel',str(fuel),'--failure-policy',policy],output,policy,
            cwd=program.parent,env=env,wall=30,cpu=20,memory=1<<30,expected=2,stdout_limit=32<<20,stderr_limit=1<<20)
        require(not bounded_read(stderr,1<<20),'known fuel fault wrote stderr');reports.append(read_json(stdout))
    result=observe_fault_pair(*reports,fuel,info)
    result['copied_report_controls']=(fault_controls(*reports,fuel,info)
        if result['after_fill'] and result['live_recursive_cycle_at_fault'] else [])
    build.save(output/'observation.json',result)
    require(result['after_fill'] and result['live_recursive_cycle_at_fault'],
            'fixed budget missed predicted filled cycle; actual reports retained, no search/retry')
    return result


def run_case(args,output,env):
    name='captured-sum';inputs=output/(name+'-inputs');inputs.mkdir()
    (inputs/'SharedPoly.emlf').write_text(SHARED,encoding='utf-8')
    entry=inputs/'main.emlf';entry.write_text(SOURCE,encoding='utf-8');target=output/name
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
    info=structure(capture,plan,generated);graph=shared_graph(plan,verified,capture,info)
    result={'case':name,'status':'passed','observation':observe(evaluation,info,graph),
            'copied_report_controls':copied_controls(evaluation,info,graph),
            'source_hashes':{'main.emlf':build.sha(SOURCE.encode()),'SharedPoly.emlf':build.sha(SHARED.encode())}}
    result['fault_pair']=run_fault_pair(target/'native/program',target/'fault-pair',env,info)
    build.save(target/'recursive-capture-observations.json',result)
    print('captured-sum: PASS (one recursive closure, full shared view, lazy bonus once, Nil/Cons/Cons/Nil, Int42, zero ledgers)',flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc',required=True);parser.add_argument('--cc',default='cc')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.absolute()
    require(output.resolve()==output and output!=BASE.parents[2] and BASE.parents[2] not in output.parents,
            'output must be canonical, fresh and outside this checkout')
    output.mkdir(parents=True,exist_ok=False);env=cli.environment(output);build.SUITE_DEADLINE=time.monotonic()+1800
    try:result=run_case(args,output,env)
    except BaseException as exc:
        try:build.save(output/'failure.json',{'error':type(exc).__name__+': '+str(exc),'completed_cases':[]})
        except BaseException as persistence:exc.add_note('Failure persistence also failed: '+repr(persistence))
        raise
    build.save(output/'results.json',[result]);return 0


if __name__=='__main__':
    raise SystemExit(main())
