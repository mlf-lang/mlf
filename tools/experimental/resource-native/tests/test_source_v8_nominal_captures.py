#!/usr/bin/env python3
"""Two fresh-source recursive closures retaining ordinary nominal owners.

DATA/SUM owner and proof identities come from the freshly checked normalized
source, public metadata and actual native reports. This is a finite observer,
not general runtime acceptance or a per-owner Access trace.
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
from test_source_v8_recursive_sum import one, walk, primitive, var, source_allocation, constructor_terms, closed_layout, SHARED, INT
from test_source_v8_monomorphic_recursion import ledger, observe_fault_pair, fault_controls
from test_source_v8_callable_captures import read_json, address, spine, carrier_allocation

require = build.require
ARROW = {'tag':'arrow','from':INT,'to':INT}
SOURCES = {
 'data-owner': ('import SharedPoly\ndata IntList = Nil | Cons Int IntList;\n'
  'data Payload = Payload Int (Int -> Int);\n'
  'let box : Payload = Payload (addInt 20 1) (sharedId : Int -> Int) in\n'
  'let rec sumBox : IntList -> Int = \\xs -> case xs of { Nil -> 0; Cons _ rest -> addInt (case box of { Payload bonus f -> f bonus }) (sumBox rest) } in\n'
  'if sharedId true then addInt (sumBox Nil) (sumBox (Cons 0 (Cons 0 Nil))) else 0\n'),
 'sum-owner': ('import SharedPoly\ndata IntList = Nil | Cons Int IntList;\n'
  'let seed : IntList = Cons (addInt 20 1) ((\\n -> Cons n Nil) 123) in\n'
  'let rec sumSeed : IntList -> Int = \\xs -> case xs of { Nil -> 0; Cons _ rest -> addInt (case seed of { Nil -> 0; Cons bonus _ -> sharedId bonus }) (sumSeed rest) } in\n'
  'if sharedId true then addInt (sumSeed Nil) (sumSeed (Cons 0 (Cons 0 Nil))) else 0\n')}
ACCESS_SCOPE = ('Nominal owners remain complete ordinary References. Source, full metadata, generated C, '
 'instantiation, stored slots and guarded handoffs establish the observed correspondence. No individual '
 'owner Access field or retain/end-borrow/drop operation is event-traced. A concrete recursive host '
 'does not rebrand a captured shared Instance as E0. No GC or performance conclusion follows.')


def passthrough(node, typ, label):
    require(node.get('tag')=='lambda' and node['parameter_type']==typ and var(node['body'],node['parameter']),
            label+' must remain an exact ordinary identity lambda')


def source_facts(capture, name):
    require(name in SOURCES, 'known nominal fixture required')
    raw=capture['normalization']['raw_normalized']
    path,term=one([(p,n) for p,n in walk(raw) if isinstance(n,dict) and n.get('tag')=='letrec'], 'one recursion')
    binding=one(term['bindings'],'one recursive binding');rhs_path=path+['bindings','0','value'];rhs=binding['value']
    owner_let=at(raw,path[:-1]);owner_path=path[:-1]+['value'];owner=owner_let['name'];owner_rhs=owner_let['value']
    require(path[-1]=='body' and owner_let['tag']=='let' and owner_rhs['tag']=='application',
            'lexical nominal owner annotation application must survive')
    owner_type=owner_rhs['function']['parameter_type'];passthrough(owner_rhs['function'],owner_type,'owner annotation')
    require(owner_type['tag']=='constructor' and not owner_type['arguments'] and owner_type['name'] not in ('Int','Bool'),
            'captured owner must be an exact closed nominal')
    head,head_path,args=spine(owner_rhs['argument'],owner_path+['argument'])
    require(head['tag']=='constructor' and not head['arguments'] and len(args)==2 and primitive(args[0][1],20,1),
            'captured nominal construction/lazy21 source differs')
    bonus_path=args[0][0];field_path,field=args[1]
    if name=='data-owner':
        require(field['tag']=='application' and field['argument']['tag']=='type_application',
                'DATA callable field annotation and proof must remain pending')
        passthrough(field['function'],ARROW,'callable field annotation')
        int_view=field_path+['argument'];unused=None
    else:
        require(field['tag']=='application' and field['function']['tag']=='lambda' and
                field['function']['parameter_type']==INT and field['argument']=={'tag':'int64','value':123},
                'unused SUM tail must retain actual lambda/application/123')
        tail_head,_,tail_args=spine(field['function']['body'],field_path+['function','body'])
        require(tail_head['tag']=='constructor' and tail_head['name']==head['name'] and len(tail_args)==2 and
                var(tail_args[0][1],field['function']['parameter']) and tail_args[1][1]['tag']=='constructor',
                'unused tail body must preserve Cons n Nil')
        int_view=None;unused=field_path
    annotation=binding['type']
    require(annotation['tag']=='arrow' and annotation['to']==INT and rhs['tag']=='application' and rhs['argument']['tag']=='lambda',
            'recursive wrapper/function shape differs')
    passthrough(rhs['function'],annotation,'recursive annotation')
    fn=rhs['argument'];fn_path=rhs_path+['argument'];arg_path=fn_path+['body'];arg_let=fn['body']
    require(fn['parameter_type']==annotation['from'] and arg_let['tag']=='let' and arg_let['value']['tag']=='application' and
            var(arg_let['value']['argument'],fn['parameter']),'ordinary recursive parameter wrapper differs')
    passthrough(arg_let['value']['function'],annotation['from'],'recursive parameter')
    case_path=arg_path+['body'];case=arg_let['body']
    require(case['tag']=='case' and case['result_type']==INT and var(case['scrutinee'],arg_let['name']) and
            len(case['alternatives'])==2,'recursive nominal case differs')
    nil=one([(i,a) for i,a in enumerate(case['alternatives']) if not a['pattern']['fields']], 'recursive Nil arm')
    cons=one([(i,a) for i,a in enumerate(case['alternatives']) if len(a['pattern']['fields'])==2], 'recursive Cons arm')
    require(nil[1]['body']=={'tag':'int64','value':0} and cons[1]['pattern']['fields'][0] is None and
            cons[1]['pattern']['fields'][1] is not None,'recursive Nil/head wildcard/tail differs')
    cons_path=case_path+['alternatives',str(cons[0]),'body'];add,_,cons_args=spine(cons[1]['body'],cons_path)
    require(add['tag']=='primitive' and add['name']=='addInt' and len(cons_args)==2,'recursive Cons addition differs')
    inner_path,inner=cons_args[0];self_path,self_call=cons_args[1]
    require(self_call['tag']=='application' and var(self_call['function'],binding['name']) and
            var(self_call['argument'],cons[1]['pattern']['fields'][1]),'same self call must consume tail')
    require(inner['tag']=='case' and inner['result_type']==INT and var(inner['scrutinee'],owner),
            'inner case must demand original captured owner')
    if name=='data-owner':
        arm=one(inner['alternatives'],'DATA sole arm');index=0
        require(arm['pattern']['constructor']==head['name'] and len(arm['pattern']['fields'])==2 and
                all(x is not None for x in arm['pattern']['fields']),'DATA fields must both be bound')
        call=arm['body'];call_path=inner_path+['alternatives','0','body']
        require(call['tag']=='application' and var(call['function'],arm['pattern']['fields'][1]) and
                var(call['argument'],arm['pattern']['fields'][0]),'DATA must call retained callable on original lazy field')
    else:
        require(owner_type==annotation['from'] and len(inner['alternatives'])==2,'SUM owner/family differs')
        index,arm=one([(i,a) for i,a in enumerate(inner['alternatives']) if len(a['pattern']['fields'])==2], 'inner Cons arm')
        other=one([a for a in inner['alternatives'] if not a['pattern']['fields']],'inner Nil arm')
        require(other['body']=={'tag':'int64','value':0} and arm['pattern']['constructor']==head['name'] and
                arm['pattern']['fields'][0] is not None and arm['pattern']['fields'][1] is None,
                'seed inner case must ignore actual tail')
        call=arm['body'];call_path=inner_path+['alternatives',str(index),'body']
        require(call['tag']=='application' and call['function']['tag']=='type_application' and
                var(call['argument'],arm['pattern']['fields'][0]),'seed head must reach full shared Int view')
        int_view=call_path+['function']
    body_path=path+['body'];branch,_,branch_args=spine(term['body'],body_path)
    require(branch['tag']=='primitive' and branch['name']=='ifThenElse' and len(branch_args)==3 and
            branch_args[2][1]=={'tag':'int64','value':0},'outer branch differs')
    bool_path,bool_call=branch_args[0]
    require(bool_call['tag']=='application' and bool_call['function']['tag']=='type_application' and
            bool_call['argument']=={'tag':'bool','value':True},'full shared Bool source differs')
    root_add_path,root_add=branch_args[1];add,_,root_args=spine(root_add,root_add_path)
    require(add['tag']=='primitive' and add['name']=='addInt' and len(root_args)==2 and all(
            n['tag']=='application' and var(n['function'],binding['name']) for _,n in root_args),
            'main must add initial Nil then recursive list result')
    return dict(name=name,raw=raw,path=path,binding=binding,rhs=rhs_path,function=fn_path,
                argument_wrapper=arg_path+['value','function'],owner=owner,owner_path=owner_path,owner_type=owner_type,
                owner_ctor=owner_path+['argument'],ctor_head=head,bonus_path=bonus_path,field_path=field_path,unused=unused,
                case=case,case_path=case_path,nil=nil,cons=cons,cons_path=cons_path,self_call=self_path,
                inner=inner,inner_path=inner_path,inner_arm=arm,inner_arm_index=index,field_call=call_path,int_view=int_view,
                bool_call=bool_path,root_add=root_add_path,first_call=root_args[0][0],second_call=root_args[1][0])


def sum_case_structure(plan, source, path, family):
    p,m=plan['program'],plan['binding']['source_map']
    row=one([r for r in m['sum_case_map'] if r['source']==address(path)],'exact source SUM case')
    factory=instruction(p,row['factory']);arms={a['variant']:a for a in row['arms']}
    require(row['family']==family['family'] and row['declaration']==family['declaration'] and
            factory['op']=='case_fields_i64' and set(arms)=={0,1} and set(factory['arms'])=={'V0','V1'},
            'exact exhaustive factory family differs')
    for variant,arm in arms.items():
        src=source['alternatives'][arm['index']]
        require(arm['source']==address(path+['alternatives',str(arm['index']),'body']) and
                arm['pattern_source']==address(path+['alternatives',str(arm['index']),'pattern']) and
                arm['constructor']==src['pattern']['constructor']==family['variants'][variant]['constructor'] and
                factory['arms']['V'+str(variant)]=={'code':arm['code'],'captures':arm['captures']},
                'factory arm source/nominal identity differs')
        wanted=[(i,b) for i,b in enumerate(src['pattern']['fields']) if b is not None]
        require(len(arm['field_captures'])==len(wanted),'factory wildcard capture census differs')
        for field,(index,binder) in zip(arm['field_captures'],wanted):
            require(field['index']==index and field['binder']==binder['id'] and field['relation']=='down' and
                    arm['captures'][field['capture']]=={'kind':'field','index':index},'factory field origin differs')
    return row,arms


def structure(capture,plan,generated,name):
    f=source_facts(capture,name);p,m=plan['program'],plan['binding']['source_map']
    knot=one(m['knot_map'],'one recursive knot');binding=f['binding']
    require(knot['source']==address(f['path']) and knot['binding_source']==address(f['path']+['bindings','0']) and
            knot['binder']==binding['name'] and knot['rhs']==address(f['rhs']) and knot['type_scope'] is None and
            knot['function_source']==address(f['function']) and knot['self_uses']==[address(f['self_call']+['function'])],
            'recursive source/knot/self correspondence differs')
    hole,fill=instruction(p,knot['hole']),instruction(p,knot['fill'])
    require(hole=={'op':'hole','out':knot['hole_owner'],'in':knot['home'],'layout':'^'+knot['logical_type']} and
            fill=={'op':'fill','hole':knot['hole_owner'],'value':knot['rhs_owner']} and
            instruction(p,knot['retain_self'])=={'op':'retain','out':knot['self_owner'],'value':knot['hole_owner']},
            'original hole/Fill/self ownership differs')
    for field,value in (('drop_rhs',knot['rhs_owner']),('drop_self',knot['self_owner']),('drop_hole',knot['hole_owner'])):
        require(instruction(p,knot[field])=={'op':'drop','value':value},'knot release differs')
    closure=source_allocation(plan,f['function'],'closure');rhs=source_allocation(plan,f['rhs'],'application')
    wrapper=source_allocation(plan,f['rhs']+['function'],'closure')
    owner=source_allocation(plan,f['owner_path'],'application');owner_wrapper=source_allocation(plan,f['owner_path']+['function'],'closure')
    bonus=source_allocation(plan,f['bonus_path'],'thunk')
    require(rhs['out']==knot['rhs_owner'] and rhs['function']==wrapper['out'] and rhs['argument']==closure['out'] and
            owner['function']==owner_wrapper['out'],'pending ordinary annotation applications differ')
    carrier=one([x for x in m['carrier_map'] if x['source']==address(f['function'])],'recursive source carrier')
    self_cap=one([x for x in carrier['mono_captures'] if x['binder']==binding['name']['id']],'self capture')
    owner_cap=one([x for x in carrier['mono_captures'] if x['binder']==f['owner']['id']],'nominal capture')
    require(len(carrier['mono_captures'])==2 and carrier['type_scope'] is None and carrier['ir_code']==closure['function'] and
            self_cap['relation']=='down' and self_cap['layout']=='^'+knot['logical_type'] and
            closure['captures'][self_cap['capture']]==knot['self_owner'] and
            closure['captures'][owner_cap['capture']]==owner['out'],'exact self/original nominal capture differs')
    nominal=one([r for r in m.get('nominal_map',[])+m['sum_map'] if r['name']==f['owner_type']['name']],
                'captured exact nominal declaration')
    physical=nominal.get('layout','%'+nominal.get('family',''))
    require(closed_layout(p,owner_cap['layout'])==physical,'captured nominal identity/layout differs')
    for c in m['carrier_map']:
        for row in c['mono_captures']:
            if row['binder']==f['owner']['id']:
                require(row['layout']==owner_cap['layout'],'nominal Reference lost downstream')
    int_use=one([r for r in m['use_map'] if r['source']==address(f['int_view'])],'exact Int proof occurrence')
    views=carrier['view_captures'];view=one(views,'captured full Int view') if name=='sum-owner' else None
    require(len(views)==(name=='sum-owner'),'DATA must not invent a recursive view capture')
    if view:
        require(view['definition']==int_use['definition'] and view['occurrences']==[int_use['use']] and
                [p['types'][t]['layout'] for t in view['arguments']]==['#i64'],'complete recursive Int view differs')
    captures=knot['captures']
    require(set(captures)=={'policy','scalars','callables','nominals','views'} and
            captures['policy']=='closed-scalar-callable-nominal-shared-view-captures/1' and
            captures['scalars']==captures['callables']==[] and captures['nominals']==[{
                'binding':f['owner'],'type':f['owner_type'],'declaration':nominal['declaration'],
                'occurrences':[address(f['inner_path']+['scrutinee'])]}], 'new ordinary nominal capture inventory differs')
    require(len(captures['views'])==len(views),'capture view census differs')
    if view:
        cv=captures['views'][0]
        require(cv['definition']==int_use['definition'] and cv['arguments']==[INT] and
                cv['instantiated_type']==ARROW and cv['uses']==[int_use['use']], 'capture view full vector differs')
    for record in carrier['mono_captures']:
        require(p['functions'][closure['function']]['captures'][record['capture']]==
                {'layout':record['layout'],'relation':record['relation']},'capture support/layout differs')
    require(set(closure['captures'])=={x['capture'] for x in carrier['mono_captures']+views},'extra recursive slot')
    family=one(m['sum_map'],'one IntList family');family_layout='%'+family['family']
    require(p['families'][family['family']]=={'variants':['V0','V1'],'fields':{'V0':[],'V1':['#i64',family_layout]}},
            'recursive family fields differ')
    rec_case,arms=sum_case_structure(plan,f['case'],f['case_path'],family)
    require([x['index'] for x in arms[1]['field_captures']]==[1] and not arms[0]['field_captures'],
            'recursive case must capture tail only')
    constructors=[]
    for row in m['sum_constructor_map']:
        head,args=constructor_terms(f['raw'],row);op=instruction(p,row['allocation'])
        require(row['declaration']==family['declaration'] and head['name']==family['variants'][row['variant']]['constructor'] and
                op==source_allocation(plan,row['source']['path'],'construct_sum' if args else 'construct_nullary'),
                'constructor exact source/nominal identity differs')
        constructors.append((row,args,op))
    def ctor(path):return one([r for r in constructors if r[0]['source']==address(path)],'exact list constructor')
    first=ctor(f['first_call']+['argument']);outer=ctor(f['second_call']+['argument']);inner=ctor(outer[1][1][0]);last=ctor(inner[1][1][0])
    require([r[0]['variant'] for r in (first,outer,inner,last)]==[0,1,1,0] and
            all(r[1][0][1]=={'tag':'int64','value':0} for r in (outer,inner)), 'finite recursion argument list differs')
    data_case=projections=field_app=field_wrapper=unused_app=unused_closure=None
    inner_case=inner_arms=None
    if name=='data-owner':
        row=one(m['constructor_map'],'DATA constructor once');head,args=constructor_terms(f['raw'],row)
        owner_value=instruction(p,row['allocation']);field_app=source_allocation(plan,f['field_path'],'application')
        field_wrapper=source_allocation(plan,f['field_path']+['function'],'closure')
        require(row['source']==address(f['owner_ctor']) and row['declaration']==nominal['declaration'] and
                owner_value['op']=='alloc' and owner_value['layout']==physical and
                owner_value['fields']=={'f0':bonus['out'],'f1':field_app['out']} and
                owner['argument']==owner_value['out'] and field_app['function']==field_wrapper['out'],
                'original DATA fields/annotation graph differs')
        data_case=one(m['case_map'],'inner DATA case once');require(data_case['source']==address(f['inner_path']) and
                data_case['declaration']==nominal['declaration'],'DATA case nominal identity differs')
        projections=data_case['projections'];require(len(projections)==2,'both DATA field projections required')
        refs=[]
        for i,row in enumerate(projections):
            require(row['index']==i and row['binder']==f['inner_arm']['pattern']['fields'][i]['id'],'DATA field binder/index differs')
            loan,retain,end=[instruction(p,row[k]) for k in ('loan','retain','end_borrow')]
            require(loan['op']=='field' and loan['field']=='f'+str(i) and retain['op']=='retain' and
                    retain['value']==loan['out'] and end=={'op':'end_borrow','value':loan['out']},'DATA borrow/retain/end sequence differs')
            paths=[row[k] for k in ('loan','retain','end_borrow')]
            require(all(x['root']=='thunk' and x['name']==data_case['code'] and len(x['segments'])==1 for x in paths) and
                    [x['segments'][0] for x in paths]==list(range(paths[0]['segments'][0],paths[0]['segments'][0]+3)),
                    'DATA field lifetime order differs')
            refs.append((loan,retain,end))
        drop=instruction(p,data_case['drop_container'])
        require(drop=={'op':'drop','value':refs[0][0]['value']} and refs[0][0]['value']==refs[1][0]['value'] and
                data_case['drop_container']['segments'][0]>projections[-1]['end_borrow']['segments'][0], 'container release order differs')
        pattern=re.compile(r'(?P<h>h\d+) = rt8_field\(ctx, h\d+, [01], p\d+, p\d+\);\n'
                           r'    h\d+ = rt8_retain\(ctx, (?P=h)\);\n    rt8_end_borrow\(ctx, (?P=h)\);')
        require(len(pattern.findall(generated))==generated.count('= rt8_field(')==2,'emitted field ownership sequence differs')
        require(len(constructors)==4 and len(m['sum_case_map'])==1,'extra DATA/SUM code occurrence')
    else:
        owner_row=ctor(f['owner_ctor']);owner_value=owner_row[2]
        unused_app=source_allocation(plan,f['unused'],'application');unused_closure=source_allocation(plan,f['unused']+['function'],'closure')
        require(owner['argument']==owner_value['out'] and owner_value['fields']==[bonus['out'],unused_app['out']] and
                unused_app['function']==unused_closure['out'],'seed preserves pending head and unused tail')
        inner_case,inner_arms=sum_case_structure(plan,f['inner'],f['inner_path'],family)
        require([x['index'] for x in inner_arms[1]['field_captures']]==[0] and not inner_arms[0]['field_captures'] and
                len(constructors)==7 and len(m['sum_case_map'])==2,'seed field wildcard/retained body census differs')
    metadata=json.loads(check_metadata(p).metadata_json)
    code=one([r for r in metadata['codes'] if r['kind']=='function' and r['name']==closure['function']],'registered recursive Code')
    definitions=[int(x) for x in re.findall(r'static Rt8Handle \*rt8_body_(\d+)\(',generated)]
    registrations=[(int(a),int(b)) for a,b in re.findall(r'\{ \.code_id = (\d+), \.body = rt8_body_(\d+) \}',generated)]
    require(definitions==list(range(len(metadata['codes']))) and registrations==[(i,i) for i in definitions] and
            generated.count('rt8_fill(ctx,')==generated.count(' = rt8_hole(ctx,')==1,'one real body per Code/one knot differs')
    return dict(facts=f,knot=knot,hole=hole,fill=fill,rhs=rhs,closure=closure,wrapper=wrapper,bonus=bonus,
        self_capture=self_cap['capture'],owner_capture=owner_cap['capture'],owner_layout=physical,owner=owner,
        owner_wrapper=owner_wrapper,owner_value=owner_value,view_capture=view['capture'] if view else None,
        code=closure['function'],code_id=code['id'],metadata=metadata,family=family_layout,arms=arms,
        constructors=[r[2] for r in (first,outer,inner,last)],rec_case=rec_case,inner_case=inner_case,inner_arms=inner_arms,
        data_case=data_case,projections=projections,projection_operations=([instruction(p,x['loan']) for x in projections] if projections else []),
        field_app=field_app,field_wrapper=field_wrapper,
        unused_app=unused_app,unused_closure=unused_closure,
        self_call=source_allocation(plan,f['self_call'],'application'),field_call=source_allocation(plan,f['field_call'],'application'),
        bool_call=source_allocation(plan,f['bool_call'],'application'),first_call=source_allocation(plan,f['first_call'],'application'),
        second_call=source_allocation(plan,f['second_call'],'application'),root_add=carrier_allocation(plan,f['root_add'],'primitive'),
        cons_add=source_allocation(plan,f['cons_path'],'thunk'),argument_wrapper=source_allocation(plan,f['argument_wrapper'],'closure'))


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
    require(uses['#i64']['source']['source_view']['kind']==('captured' if info['facts']['name']=='sum-owner' else 'scheme'),
            'source full Int acquisition differs')
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
    if info['facts']['name']=='sum-owner':
        resolved=one([x for x in recursive['captures'] if x['name']==info['view_capture']], 'recursive stored Int view')
        require(resolved['type']==uses['#i64']['row']['result_type'] and
                info['closure']['captures'][info['view_capture']]==uses['#i64']['operation']['out'], 'stored full view differs')
        require(info['knot']['captures']['views'][0]['binding']==definition['binding'], 'exact captured generic binder differs')
    else:
        require(info['field_app']['argument']==uses['#i64']['operation']['out'], 'callable field must retain acquired Int view')
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
            e['events_omitted']==0 and e['events_emitted']==len(e['events']), 'complete native Int42 report required')
    require(e['guards_failed_mask']==0 and e['guards_checked_mask']==(1<<27)-1 and
            e['guard_work_limit']==67_108_864 and 0<e['guard_work_used']<=e['guard_work_limit'], 'native guard failure/work differs')
    ledger(e,True);events=e['events'];sel=lambda k:[(i,x) for i,x in enumerate(events) if x['event']==k]
    allocations=sel('allocate');nodes={x['node']:x for _,x in allocations}
    require(len(nodes)==len(allocations),'duplicate allocation node')
    def alloc(op,label):
        i,row=one([(i,x) for i,x in allocations if x['out']==op['out']],label+' allocation once')
        require(row['opcode']==op['op'] and row['code']==(op['function'] if op['op']=='closure' else op.get('code')),
                label+' source Code/opcode differs')
        return i,row
    def memo(node,label):return one([(i,x) for i,x in sel('memo_publish') if x['destination']==node],label+' memo once')
    def demand(node,label):return one([(i,x) for i,x in sel('update_pin') if x['node']==node],label+' demand once')
    bonus_i,bonus=alloc(info['bonus'],'bonus');owner_i,owner=alloc(info['owner'],'pending nominal owner')
    value_i,value=alloc(info['owner_value'],'nominal value');_,owner_wrapper=alloc(info['owner_wrapper'],'nominal annotation wrapper')
    hole_i,hole=alloc(info['hole'],'hole');closure_i,closure=alloc(info['closure'],'recursive closure')
    _,wrapper=alloc(info['wrapper'],'recursive annotation wrapper');rhs_i,rhs=alloc(info['rhs'],'recursive RHS')
    fill_i,fill=one(sel('fill'),'one Fill')
    require(bonus['state']=='THUNK' and owner['state']==rhs['state']=='APPLICATION' and hole['state']=='HOLE' and
            closure['state']==wrapper['state']=='CLOSURE' and bonus_i<value_i<owner_i<hole_i<closure_i<rhs_i<fill_i,
            'nominal/knot pending allocation order differs')
    require(fill['hole']==hole['node'] and fill['target']==rhs['node'] and fill['hole_variable']==info['fill']['hole'] and
            fill['value_variable']==info['fill']['value'],'original Fill target/ticket differs')
    require(rhs['slots']=={'$function':wrapper['node'],'$argument':closure['node']} and
            owner['slots']=={'$function':owner_wrapper['node'],'$argument':value['node']} and
            closure['slots'][info['self_capture']]==hole['node'] and closure['slots'][info['owner_capture']]==owner['node'],
            'recursive self/original nominal owner graph differs')
    slot_i,_=one([(i,x) for i,x in sel('slot_install') if x['host']==hole['node'] and x['field']=='$target' and x['target']==rhs['node']],
                 'original Fill edge once')
    require(rhs_i<slot_i<fill_i and not any(i<fill_i and x['node'] in (hole['node'],rhs['node']) for i,x in sel('update_pin')),
            'knot demanded before Fill')
    rhs_memo_i,rhs_memo=memo(rhs['node'],'recursive RHS')
    wrap_i,wrap=one([(i,x) for i,x in sel('invoke_enter') if x['closure']==wrapper['node']],'recursive annotation once')
    require(fill_i<wrap_i<rhs_memo_i and wrap['argument']==rhs_memo['result']==closure['node'],'recursive annotation/closure changed')

    begin_i,_=one(sel('generic_begin'),'one generic introduction');seal_i,seal=one(sel('generic_seal'),'one generic seal')
    shared=seal['node'];pending=nodes[shared];outer_shared,body=pending['slots']['$function'],pending['slots']['$argument']
    require(begin_i<seal_i and pending['out']==graph['seal_owner'] and pending['state']=='APPLICATION' and
            nodes[outer_shared]['code']==graph['outer_code'] and nodes[body]['code']==graph['shared_code'] and
            sum(x['code']==graph['shared_code'] for _,x in allocations)==1,'original shared RHS/body changed or cloned')
    entry=one([x for _,x in sel('frame_enter') if x['context']['kind']=='entry'],'entry frame')['frame']
    uses=sel('instantiate');require(len(uses)==2,'shared view acquisition census differs');observed_access={};meta=info['metadata']
    for atom,wanted in graph['uses'].items():
        i,event=one([(i,x) for i,x in uses if x['use']==wanted['row']['id']],'actual full Use once')
        require(event['node']==shared and event['frame']==entry and event['mode']=='own' and event['anchor'] is None,
                'view acquired inside callback or detached from shared node')
        before,after=meta['accesses'][event['old_access']],meta['accesses'][event['new_access']]
        require(before['mode']=='SCHEME' and after['mode']=='MONO' and before['site']==after['site']==pending['site_id'] and
                before['origin_env']==after['origin_env']==pending['env_id'] and after['origin_env']!=0 and
                meta['environments'][after['origin_env']]['mode']=='NEUTRAL' and after['use_env']==wanted['row']['env'] and
                after['type']==wanted['row']['result_type'] and after['scheme'] is None and
                meta['environments'][after['use_env']]['mode']=='CLOSED','complete shared Access/origin differs')
        observed_access[atom]={'event_index':i,'origin_env':after['origin_env'],'use_env':after['use_env'],
                               'access':after['id'],'type':after['type'],'use':event['use']}
    require(closure['env_id']==0 and nodes[body]['env_id']==pending['env_id']!=0,
            'concrete host must preserve distinct actual generic origin')
    if info['view_capture']:
        require(closure['slots'][info['view_capture']]==shared,'recursive stored view target differs')
    handoffs=[(i,x) for i,x in sel('closure_capture_handoff') if x['node']==closure['node']]
    require(len(handoffs)==4 and all(set(x['owners'])==set(closure['slots']) and x['protocol']=='repeat' for _,x in handoffs) and
            len({o for _,x in handoffs for o in x['owners'].values()})==4*len(closure['slots']),
            'four activations require complete distinct capture owners')
    constructors=[alloc(op,'list constructor')[1] for op in info['constructors']]
    first_nil,outer,inner,tail_nil=constructors
    scalars={x['node']:(x['kind'],x['value']) for _,x in sel('scalar_value')}
    require(not first_nil['slots'] and not tail_nil['slots'] and outer['slots']['1']==inner['node'] and
            inner['slots']['1']==tail_nil['node'] and all(scalars.get(n['slots']['0'])==('i64',0) for n in (outer,inner)),
            'finite Nil/Cons/Cons/Nil graph differs')
    require(len(sel('sum_value'))==(4 if info['facts']['name']=='data-owner' else 5),'unexpected executed SUM constructor')
    for n,variant in zip(constructors,(0,1,1,0)):
        _,row=one([(i,x) for i,x in sel('sum_value') if x['node']==n['node']],'list constructor value once')
        require(row['family']==n['layout']==info['family'] and row['variant_index']==variant and row['variant']=='V'+str(variant),
                'nominal list variant differs')
    calls=[(i,x) for i,x in sel('invoke_enter') if x['closure']==closure['node']]
    frames=[(i,x) for i,x in sel('frame_enter') if x['context'].get('name')==info['code']]
    require(len(calls)==len(frames)==4 and [x['argument'] for _,x in calls]==[n['node'] for n in constructors] and
            len({x['frame'] for _,x in frames})==4 and all(x['context']['node']==closure['node'] for _,x in frames) and
            sum(x['code']==info['code'] for _,x in allocations)==1,'same closure/Code must invoke Nil/Cons/Cons/Nil')
    require(rhs_memo_i<calls[0][0] and all(h[0]<c[0]<f[0] for h,c,f in zip(handoffs,calls,frames)),
            'capture handoff/callback order differs')
    wrappers=[x for _,x in allocations if x['out']==info['argument_wrapper']['out']]
    require(len(wrappers)==4 and all(x['code']==info['argument_wrapper']['function'] for x in wrappers),'parameter wrappers erased')
    for n,arg in zip(wrappers,constructors):
        _,call=one([(i,x) for i,x in sel('invoke_enter') if x['closure']==n['node']],'parameter wrapper once')
        require(call['argument']==arg['node'],'parameter wrapper argument differs')
    self_apps=[x for _,x in allocations if x['out']==info['self_call']['out']]
    require(len(self_apps)==2 and [x['slots'] for x in self_apps]==[
        {'$function':hole['node'],'$argument':n['node']} for n in (inner,tail_nil)],'self calls lost tail/self identity')
    _,first_app=alloc(info['first_call'],'initial Nil application');_,second_app=alloc(info['second_call'],'list application')
    require(first_app['slots']=={'$function':hole['node'],'$argument':first_nil['node']} and
            second_app['slots']=={'$function':hole['node'],'$argument':outer['node']},'main recursive application graph differs')
    first_memo_i,first_memo=memo(first_app['node'],'initial Nil')
    require(calls[0][0]<first_memo_i<calls[1][0] and scalars.get(first_memo['result'])==('i64',0),'initial Nil must finish first')

    def factories_for(arms,expected,mask):
        codes={a['code'] for a in arms.values()}
        actual=[(i,x) for i,x in sel('case_fields_i64') if x['code'] in codes]
        require(len(actual)==len(expected) and [(x['scrutinee'],x['variant_index']) for _,x in actual]==expected,
                'selected factory source/scrutinee/variant differs')
        results=[]
        for (i,x),(node,variant) in zip(actual,expected):
            arm=arms[variant];n=nodes[x['result']]
            require(x['family']==info['family'] and x['variant']=='V'+str(variant) and n['code']==x['code']==arm['code'] and
                    n['opcode']=='case_fields_i64' and n['slots']==x['captures'] and
                    x['field_indices']=={f['capture']:f['index'] for f in arm['field_captures']} and
                    x['field_mask']==(mask if variant else 0),'factory Code/field origin differs')
            cb,_=one([(j,y) for j,y in sel('callback_enter') if y['node']==n['node']],'selected factory callback once')
            require(i<cb,'factory callback before publication')
            for f in arm['field_captures']:
                _,field=one([(j,y) for j,y in sel('sum_field_capture') if y['scrutinee']==node and y['capture']==f['capture'] and
                             j<i and (not results or j>actual[len(results)-1][0])],'selected field once per activation')
                require(field['field_index']==f['index'] and field['node']==nodes[node]['slots'][str(f['index'])]==x['captures'][f['capture']],
                        'selected field must retain original node')
            results.append(n['node'])
        return actual,results
    rec_factories,activation_nodes=factories_for(info['arms'],[(n['node'],v) for n,v in zip(constructors,(0,1,1,0))],2)
    expected_factories=4 if info['facts']['name']=='data-owner' else 6
    require(len(sel('case_fields_i64'))==expected_factories and
            sum(x['opcode']=='case_fields_i64' for _,x in allocations)==expected_factories,'unselected factory allocated or entered')
    shared_memo_i,shared_memo=memo(shared,'shared RHS');require(shared_memo['result']==body,'shared RHS did not retain same callable')
    one([x for _,x in sel('invoke_enter') if x['closure']==outer_shared],'shared wrapper once')
    shared_calls=[(i,x) for i,x in sel('invoke_enter') if x['closure']==body]
    require(len(shared_calls)==3 and scalars.get(shared_calls[0][1]['argument'])==('bool',True) and
            [x['argument'] for _,x in shared_calls[1:]]==[bonus['node'],bonus['node']] and
            shared_memo_i<shared_calls[0][0]<calls[0][0]<first_memo_i<shared_calls[1][0]<shared_calls[2][0],
            'shared Bool/Int/Int must retain original bonus after initial Nil')
    shared_frames=[x for _,x in sel('frame_enter') if x['context'].get('name')==graph['shared_code']]
    require(len(shared_frames)==3 and all(x['context'].get('node')==body for x in shared_frames),'shared callback substitution')
    owner_demand_i,_=demand(owner['node'],'nominal owner');owner_memo_i,owner_memo=memo(owner['node'],'nominal owner')
    owner_wrap_i,owner_wrap=one([(i,x) for i,x in sel('invoke_enter') if x['closure']==owner_wrapper['node']], 'nominal annotation once')
    require(first_memo_i<owner_demand_i<owner_wrap_i<owner_memo_i<shared_calls[1][0] and
            owner_wrap['argument']==owner_memo['result']==value['node'],'initial Nil demanded owner or nominal annotation lost value')
    demand_i,_=demand(bonus['node'],'bonus');cb_i,_=one([(i,x) for i,x in sel('callback_enter') if x['node']==bonus['node']], 'bonus callback once')
    memo_i,bonus_memo=memo(bonus['node'],'bonus')
    require(first_memo_i<shared_calls[1][0]<demand_i<cb_i<memo_i and scalars.get(bonus_memo['result'])==('i64',21),
            'bonus demanded eagerly, more than once or wrong scalar')
    bonus_raw_i,bonus_raw=one([(i,x) for i,x in sel('raw_return') if x['source']==bonus['node']], 'bonus raw return once')
    require(bonus_raw['result']==bonus_memo['result'] and cb_i<bonus_raw_i<memo_i,'bonus must return exact final scalar')
    field_calls=[(i,x) for i,x in allocations if x['out']==info['field_call']['out']]
    require(len(field_calls)==2 and len({x['node'] for _,x in field_calls})==2 and all(x['state']=='APPLICATION' for _,x in field_calls),
            'two inner field calls must be distinct pending applications')
    field_results=[]
    for index,((app_i,app),(invoke_i,invoke)) in enumerate(zip(field_calls,shared_calls[1:])):
        require(app['slots']['$argument']==bonus['node'] and first_memo_i<app_i<invoke_i,'inner call must preserve lazy bonus')
        result_i,result=memo(app['node'],'field call')
        require(result['result']==bonus_memo['result'] and result_i>bonus_raw_i and scalars.get(result['result'])==('i64',21),
                'field call must memo exact READY21, not pending owner')
        slot_i,slot=one([(i,x) for i,x in sel('slot_install') if x['host']==app['node'] and x['field']=='$target'], 'field call memo slot once')
        require(slot_i==result_i-1 and slot['target']==result['result'] and slot['target_state']=='READY', 'field call memo slot differs')
        pin_i,pin=demand(app['node'],'field call')
        require(app_i<pin_i<invoke_i<result_i and result['pin']==pin['pin'],'field call actual demand/publication differs')
        frame=shared_frames[index+1]['frame']
        parameter=one([x for _,x in allocations if x['out']==graph['parameter_wrapper']['out'] and x['frame']==frame],
                      'actual shared parameter wrapper once')
        parameter_app=one([x for _,x in allocations if x['out']==graph['parameter_application']['out'] and x['frame']==frame],
                          'actual shared parameter application once')
        shared_return_i,shared_return=one([(i,x) for i,x in sel('invoke_raw_return') if x['closure']==body and
                                          x['result']==parameter_app['node']], 'shared raw parameter application return once')
        wrapper_call_i,wrapper_call=one([(i,x) for i,x in sel('invoke_enter') if x['closure']==parameter['node']],
                                       'shared parameter wrapper invocation once')
        wrapper_frame=one([x for _,x in sel('frame_enter') if x['context'].get('node')==parameter['node']],
                          'shared parameter wrapper callback once')
        wrapper_return_i,wrapper_return=one([(i,x) for i,x in sel('invoke_raw_return') if x['closure']==parameter['node']],
                                           'shared parameter raw return once')
        require(parameter['code']==graph['parameter_wrapper']['function'] and
                wrapper_frame['context']['name']==parameter['code'] and
                parameter_app['slots']=={'$function':parameter['node'],'$argument':bonus['node']} and
                shared_return['argument']==wrapper_call['argument']==wrapper_return['argument']==wrapper_return['result']==bonus['node'] and
                invoke_i<shared_return_i<wrapper_call_i<wrapper_return_i<result_i,
                'shared identity raw-return chain must preserve original bonus owner')
        chain=[app['node'],parameter_app['node']]+([bonus['node']] if index==0 else [])
        chain_memos=[memo(n,'shared return-chain') for n in chain]
        chain_pins=[demand(n,'shared return-chain') for n in chain]
        order=[i for i,_ in chain_memos]
        require(order==sorted(order) and len(set(order))==len(order) and
                all(row['result']==bonus_memo['result'] and row['pin']==pin['pin'] and row['depth']==pin['depth']==chain_pins[0][1]['depth']
                    for (_,row),(_,pin) in zip(chain_memos,chain_pins)),
                'shared return-chain must publish exact READY21 FIRST-to-LAST')
        if index==0:
            require(wrapper_return_i<demand_i<cb_i<bonus_raw_i<order[0] and order[-1]==memo_i,
                    'first shared identity must return bonus before demand/publication')
        else:
            require(memo_i<invoke_i<wrapper_return_i<order[0], 'second shared identity must reuse memoized bonus')
        for n,(mi,row),(_,pin) in zip(chain,chain_memos,chain_pins):
            si,slot=one([(i,x) for i,x in sel('slot_install') if x['host']==n and x['field']=='$target'], 'return-chain memo slot once')
            ui,unpin=one([(i,x) for i,x in sel('update_unpin') if x['node']==n], 'return-chain unpin once')
            require(si==mi-1 and slot['target']==row['result'] and slot['target_state']=='READY' and
                    ui>order[-1] and unpin['pin']==pin['pin'] and unpin['depth']==pin['depth'],
                    'return-chain slot/unpin must preserve exact ready target')
        field_results.append(result['result'])
    detail={}
    if info['facts']['name']=='data-owner':
        _,field_app=alloc(info['field_app'],'callable field annotation');_,field_wrapper=alloc(info['field_wrapper'],'callable field wrapper')
        require(value['state']=='READY' and value['layout']==info['owner_layout'] and
                value['slots']=={'f0':bonus['node'],'f1':field_app['node']} and
                field_app['slots']=={'$function':field_wrapper['node'],'$argument':shared}, 'DATA exact pending field graph differs')
        field_demand_i,_=demand(field_app['node'],'callable field');field_memo_i,field_memo=memo(field_app['node'],'callable field')
        fw_i,fw=one([(i,x) for i,x in sel('invoke_enter') if x['closure']==field_wrapper['node']], 'callable field wrapper once')
        require(first_memo_i<field_demand_i<fw_i<field_memo_i<shared_calls[1][0] and fw['argument']==shared and
                field_memo['result']==body and all(x['slots']['$function']==field_app['node'] for _,x in field_calls),
                'callable field must reuse actual shared Instance via pending annotation')
        projections=sel('field_project');require(len(projections)==4 and e['metrics']['ir_end_borrow_ops']==4,'exact two-field borrow census differs')
        data_nodes=[x for _,x in allocations if x['code']==info['data_case']['code']]
        require(len(data_nodes)==2,'two DATA case activations required')
        for index,node in enumerate(data_nodes):
            _,frame=one([(i,x) for i,x in sel('frame_enter') if x['context'].get('node')==node['node'] and
                        x['context'].get('name')==node['code']],'DATA case callback once')
            rows=[(i,x) for i,x in projections if x['frame']==frame['frame']]
            require(len(rows)==2,'DATA field projection per activation differs')
            for (i,x),projection,target in zip(rows,info['projections'],(bonus['node'],field_app['node'])):
                require(x['host']==value['node'] and x['field']=='f'+str(projection['index']) and x['target']==target and
                        x['out']==instruction_from_projection(info,projection,'out') and
                        owner_memo_i<i<field_calls[index][0], 'DATA field projection lost original owner')
                force_i,forced=one([(j,y) for j,y in sel('ir_force_result') if y['owner']==x['anchor']], 'DATA container anchor once')
                require(forced['result']==value['node'] and forced['frame']==x['frame'] and force_i<i,'DATA anchor/Force mismatch')
            return_i,returned=one([(i,x) for i,x in sel('raw_return') if x['source']==node['node']], 'DATA case raw return once')
            require(returned['result']==field_calls[index][1]['node'] and returned['result_state']=='APPLICATION' and
                    field_calls[index][0]<return_i<demand(field_calls[index][1]['node'],'field call')[0],
                    'whole DATA case must return still-pending call')
        detail={'callable_field_node':field_app['node'],'callable_field_memo_event':field_memo_i,
                'field_projection_events':[i for i,_ in projections],'individual_handle_operations_event_traced':False}
    else:
        _,unused=alloc(info['unused_app'],'unused tail application');_,unused_closure=alloc(info['unused_closure'],'unused tail lambda')
        require(value['state']=='READY' and value['layout']==info['owner_layout'] and
                value['slots']=={'0':bonus['node'],'1':unused['node']} and
                unused['slots']['$function']==unused_closure['node'] and scalars.get(unused['slots']['$argument'])==('i64',123),
                'seed must preserve lazy head and original unused tail')
        require(not any(x['node']==unused['node'] for _,x in sel('update_pin')) and
                not any(x['destination']==unused['node'] for _,x in sel('memo_publish')) and
                not any(x['closure']==unused_closure['node'] for _,x in sel('invoke_enter')) and
                not any(x['context'].get('name')==info['unused_closure']['function'] for _,x in sel('frame_enter')),
                'unused tail application/body must not be entered')
        require(all(x['slots']['$function']==shared for _,x in field_calls),'inner SUM call must retain actual full shared view')
        inner_factories,_=factories_for(info['inner_arms'],[(value['node'],1)]*2,1)
        require(owner_memo_i<inner_factories[0][0] and len(sel('sum_field_capture'))==4,'inner seed field/wildcard census differs')
        detail={'unused_tail_node':unused['node'],'unused_tail_lambda':unused_closure['node'],
                'unused_ready_argument_node':unused['slots']['$argument'],'unused_tail_entered':False,
                'inner_factory_events':[i for i,_ in inner_factories]}
    additions=[x for _,x in allocations if x['out']==info['cons_add']['out']]
    require(len(additions)==2,'two recursive additions required')
    for node,wanted,result in zip(additions,(42,21),field_results):
        require(node['code']==info['cons_add']['code'],'recursive addition Code differs')
        _,frame=one([(i,x) for i,x in sel('frame_enter') if x['context'].get('node')==node['node'] and
                    x['context'].get('name')==node['code']],'addition callback once')
        forces=[(i,x) for i,x in sel('ir_force_result') if x['frame']==frame['frame']]
        end_i,end=memo(node['node'],'recursive addition')
        require(len(forces)==2 and forces[0][1]['result']==result and
                memo_i<forces[0][0]<forces[1][0]<end_i and scalars.get(end['result'])==('i64',wanted), 'recursive unwind result differs')
    _,root=alloc(info['root_add'],'main addition')
    _,frame=one([(i,x) for i,x in sel('frame_enter') if x['context'].get('node')==root['node'] and
                x['context'].get('name')==root['code']],'main addition callback once')
    forces=[(i,x) for i,x in sel('ir_force_result') if x['frame']==frame['frame']]
    require(len(forces)==2 and [scalars.get(x['result']) for _,x in forces]==[('i64',0),('i64',42)] and
            first_memo_i<forces[0][0]<calls[1][0]<forces[1][0],'main must consume initial zero then recursive42')
    return {'recursive_closure':closure['node'],'recursive_code':info['code'],'registered_code_id':info['code_id'],
        'arguments':[n['node'] for n in constructors],'variants':[0,1,1,0],'recursive_calls':4,'factory_nodes':activation_nodes,
        'owner_node':owner['node'],'nominal_value':value['node'],'owner_demand_event':owner_demand_i,'owner_memo_event':owner_memo_i,
        'initial_nil_memo_event':first_memo_i,'bonus_node':bonus['node'],'bonus_demand_event':demand_i,'bonus_evaluations':1,
        'bonus_memos':1,'bonus_memo_event':memo_i,'shared_node':shared,'shared_body':body,'shared_call_kinds':['Bool','Int','Int'],
        'actual_views':observed_access,'access_observation_scope':ACCESS_SCOPE,'memory':e['memory'],
        'memory_categories':e['memory_categories'],**detail}


def instruction_from_projection(info,row,key):
    return info['projection_operations'][row['index']][key]


def copied_controls(evaluation,info,graph):
    """Copied-report negatives only, no target executions."""
    observe(evaluation,info,graph);results=[]
    def event(r,kind,pred=lambda x:True):return one([x for x in r['events'] if x['event']==kind and pred(x)],'control selector')
    def allocation(r,op):return event(r,'allocate',lambda x:x['out']==op['out'])
    def reject(name,mutate,guard):
        r=copy.deepcopy(evaluation);mutate(r);r['events_emitted']=len(r['events'])
        try:observe(r,info,graph)
        except AssertionError as exc:
            require(guard in str(exc),name+' rejected at unrelated guard: '+str(exc))
            results.append({'control':name,'status':'rejected','guard':guard})
        else:raise AssertionError(name+' accepted copied corruption')
    reject('wrong-fill-target',lambda r:event(r,'fill').__setitem__('target',-1),'original Fill target/ticket differs')
    for key in ('self_capture','owner_capture'):
        reject('wrong-'+key,lambda r,k=key:allocation(r,info['closure'])['slots'].__setitem__(info[k],-1),
               'recursive self/original nominal owner graph differs')
    reject('recursive-Code-substitution',lambda r:allocation(r,info['closure']).__setitem__('code','wrong'),
           'recursive closure source Code/opcode differs')
    reject('missing-nominal-handoff',lambda r:next(x for x in r['events'] if x['event']=='closure_capture_handoff' and
        x['node']==allocation(r,info['closure'])['node'])['owners'].pop(info['owner_capture']),
        'four activations require complete distinct capture owners')
    reject('callback-local-instantiation',lambda r:next(x for x in r['events'] if x['event']=='instantiate').__setitem__('frame',-1),
           'view acquired inside callback or detached from shared node')
    def wrong_access(r):
        uses={x['use']:x for x in r['events'] if x['event']=='instantiate'}
        uses[graph['uses']['#i64']['row']['id']]['new_access']=uses[graph['uses']['#bool']['row']['id']]['new_access']
    reject('wrong-view-Access',wrong_access,'complete shared Access/origin differs')
    reject('generic-body-rebranded-E0',lambda r:event(r,'allocate',lambda x:x['code']==graph['shared_code']).__setitem__('env_id',0),
           'concrete host must preserve distinct actual generic origin')
    reject('recursive-callback-substitution',lambda r:next(x for x in r['events'] if x['event']=='frame_enter' and
        x['context'].get('name')==info['code'])['context'].__setitem__('node',-1), 'same closure/Code must invoke Nil/Cons/Cons/Nil')
    reject('self-tail-substitution',lambda r:next(x for x in r['events'] if x['event']=='allocate' and
        x['out']==info['self_call']['out'])['slots'].__setitem__('$argument',-1),'self calls lost tail/self identity')
    reject('wrong-selected-variant',lambda r:next(x for x in r['events'] if x['event']=='case_fields_i64').__setitem__('variant_index',1),
           'selected factory source/scrutinee/variant differs')
    reject('wrong-field-origin',lambda r:next(x for x in r['events'] if x['event']=='sum_field_capture').__setitem__('node',-1),
           'selected field must retain original node')
    def early(r,op,kind,key):
        row=event(r,kind,lambda x:x[key]==allocation(r,op)['node']);r['events'].remove(row);r['events'].insert(0,row)
    reject('initial-Nil-demands-owner',lambda r:early(r,info['owner'],'update_pin','node'),
           'initial Nil demanded owner or nominal annotation lost value')
    reject('initial-Nil-demands-bonus',lambda r:early(r,info['bonus'],'update_pin','node'),
           'bonus demanded eagerly, more than once or wrong scalar')
    def duplicate(r,op,kind,key):r['events'].append(copy.deepcopy(event(r,kind,lambda x:x[key]==allocation(r,op)['node'])))
    reject('owner-memo-duplicated',lambda r:duplicate(r,info['owner'],'memo_publish','destination'),'nominal owner memo once')
    reject('bonus-callback-duplicated',lambda r:duplicate(r,info['bonus'],'callback_enter','node'),'bonus callback once')
    reject('bonus-memo-duplicated',lambda r:duplicate(r,info['bonus'],'memo_publish','destination'),'bonus memo once')
    reject('owner-memo-substituted',lambda r:event(r,'memo_publish',lambda x:x['destination']==allocation(r,info['owner'])['node']).__setitem__('result',-1),
           'initial Nil demanded owner or nominal annotation lost value')
    def first_field(r):return next(x for x in r['events'] if x['event']=='allocate' and x['out']==info['field_call']['out'])
    reject('field-call-alias-target',lambda r:first_field(r)['slots'].__setitem__('$argument',-1),'inner call must preserve lazy bonus')
    reject('field-memo-pending-target',lambda r:event(r,'memo_publish',lambda x:x['destination']==first_field(r)['node']).__setitem__(
        'result',allocation(r,info['bonus'])['node']),'field call must memo exact READY21, not pending owner')
    reject('field-memo-slot-target',lambda r:event(r,'slot_install',lambda x:x['host']==first_field(r)['node'] and x['field']=='$target').__setitem__('target',-1),
           'field call memo slot differs')
    reject('shared-callback-substitution',lambda r:next(x for x in r['events'] if x['event']=='frame_enter' and
        x['context'].get('name')==graph['shared_code'])['context'].__setitem__('node',-1),'shared callback substitution')
    def first_parameter(r):
        return [x for x in r['events'] if x['event']=='allocate' and x['out']==graph['parameter_wrapper']['out']][1]
    reject('shared-parameter-raw-return-substitution',lambda r:event(r,'invoke_raw_return',
        lambda x:x['closure']==first_parameter(r)['node']).__setitem__('result',-1),
        'shared identity raw-return chain must preserve original bonus owner')
    reject('shared-parameter-callback-substitution',lambda r:event(r,'frame_enter',
        lambda x:x['context'].get('node')==first_parameter(r)['node'])['context'].__setitem__('name','wrong'),
        'shared identity raw-return chain must preserve original bonus owner')
    def early_wrapper_bonus(r):
        row=event(r,'update_pin',lambda x:x['node']==allocation(r,info['bonus'])['node'])
        r['events'].remove(row);before=event(r,'invoke_raw_return',lambda x:x['closure']==first_parameter(r)['node'])
        r['events'].insert(r['events'].index(before),row)
    reject('bonus-demand-before-identity-return',early_wrapper_bonus,
           'first shared identity must return bonus before demand/publication')
    if info['facts']['name']=='data-owner':
        reject('DATA-field-alias-substitution',lambda r:allocation(r,info['owner_value'])['slots'].__setitem__('f0',-1),
               'DATA exact pending field graph differs')
        reject('DATA-projection-substitution',lambda r:next(x for x in r['events'] if x['event']=='field_project').__setitem__('target',-1),
               'DATA field projection lost original owner')
        reject('DATA-callable-memo-substitution',lambda r:event(r,'memo_publish',lambda x:x['destination']==allocation(r,info['field_app'])['node']).__setitem__('result',-1),
               'callable field must reuse actual shared Instance via pending annotation')
        reject('DATA-missing-end-borrow-count',lambda r:r['metrics'].__setitem__('ir_end_borrow_ops',3),'exact two-field borrow census differs')
    else:
        reject('SUM-seed-slot-substitution',lambda r:allocation(r,info['owner_value'])['slots'].__setitem__('1',-1),
               'seed must preserve lazy head and original unused tail')
        def force_unused(r):
            row=copy.deepcopy(event(r,'update_pin',lambda x:x['node']==allocation(r,info['owner'])['node']))
            row['node']=allocation(r,info['unused_app'])['node'];r['events'].append(row)
        reject('SUM-unused-tail-demand',force_unused,'unused tail application/body must not be entered')
        def call_unused(r):
            row=copy.deepcopy(next(x for x in r['events'] if x['event']=='invoke_enter'))
            row['closure']=allocation(r,info['unused_closure'])['node'];r['events'].append(row)
        reject('SUM-unused-body-invoke',call_unused,'unused tail application/body must not be entered')
        reject('SUM-captured-view-target',lambda r:allocation(r,info['closure'])['slots'].__setitem__(info['view_capture'],-1),
               'recursive stored view target differs')
    reject('guard-budget-raised',lambda r:r.__setitem__('guard_work_limit',67_108_865),'native guard failure/work differs')
    reject('missing-guard',lambda r:r.__setitem__('guards_checked_mask',0),'native guard failure/work differs')
    reject('nonzero-ledger',lambda r:r['memory_categories']['pending'].__setitem__('live_blocks',1),'ledger arithmetic differs')
    return results


def structure_controls(capture,plan,generated,name):
    """Copies of actual plan/source maps, not synthetic source-program coverage."""
    structure(capture,plan,generated,name);rows=[]
    def reject(label,change):
        p=copy.deepcopy(plan);change(p)
        try:structure(capture,p,generated,name)
        except AssertionError as exc:rows.append({'control':label,'status':'rejected','guard':str(exc)})
        else:raise AssertionError(label+' accepted')
    def knot(p):return p['binding']['source_map']['knot_map'][0]
    reject('nominal-capture-type',lambda p:knot(p)['captures']['nominals'][0].__setitem__('type',INT))
    reject('nominal-declaration-identity',lambda p:knot(p)['captures']['nominals'][0].__setitem__('declaration',-1))
    reject('nominal-occurrence',lambda p:knot(p)['captures']['nominals'][0].__setitem__('occurrences',[]))
    reject('nominal-policy',lambda p:knot(p)['captures'].__setitem__('policy','closed-scalar-callable-shared-view-captures/1'))
    reject('invented-scalar',lambda p:knot(p)['captures']['scalars'].append({'invented':True}))
    reject('invented-callable',lambda p:knot(p)['captures']['callables'].append({'invented':True}))
    reject('wrong-Fill',lambda p:instruction(p['program'],knot(p)['fill']).__setitem__('value','wrong'))
    reject('missing-self-use',lambda p:knot(p).__setitem__('self_uses',[]))
    info=structure(capture,plan,generated,name)
    def wrong_slot(p):
        op=source_allocation(p,info['facts']['function'],'closure');op['captures'][info['owner_capture']]='wrong'
    reject('wrong-original-owner-slot',wrong_slot)
    if name=='data-owner':
        reject('DATA-field-index',lambda p:p['binding']['source_map']['case_map'][0]['projections'][0].__setitem__('index',1))
    else:
        reject('SUM-field-index',lambda p:next(r for r in p['binding']['source_map']['sum_case_map'] if
            r['source']==address(info['facts']['inner_path']))['arms'][1]['field_captures'][0].__setitem__('index',1))
    return rows


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
    build.save(target/'nominal-capture-observations.json',result)
    print(name+': PASS (ordinary nominal capture, preserved annotations, lazy owner/bonus once, shared Bool/Int/Int, Int42, zero ledgers)',flush=True)
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
