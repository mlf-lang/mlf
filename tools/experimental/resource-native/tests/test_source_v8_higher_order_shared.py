#!/usr/bin/env python3
"""Genuine sharedApply sources with pending callable captures and reused partials.

A uses equal coordinates; B uses opposite scalar coordinates and a lazy helper
conditional. Neither uses arrow type arguments or runtime observation hooks.
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
sys.path[:0] = [str(BASE), str(BASE / 'tests')]
import run_source_v8 as cli
import source_build_v8 as build
from source_snapshot_v8 import bounded_read
from resource_ir_v8.metadata import check_metadata
from test_shared_source_native import at, instruction
from test_source_v8_recursive_sum import one, walk, primitive, var, source_allocation, INT
from test_source_v8_callable_captures import address, spine, read_json
from test_source_v8_nominal_captures import passthrough
from test_source_v8_monomorphic_recursion import ledger

require = build.require
BOOL = {'tag': 'constructor', 'name': 'Bool', 'arguments': []}
EXPECTED_GUARDS = ((1 << 27) - 1) & ~(1 << 24)
SHARED = ('module SharedPoly (sharedApply) where\n'
          'sharedApply : forall a b. (a -> b) -> a -> b\n'
          'sharedApply f x = f x\n')
SOURCE = ('import SharedPoly\nlet bonus = addInt 20 1 in\n'
          'let helper : Int -> Int = \\n -> addInt n bonus in\n'
          'let gate : Bool -> Bool = \\b -> b in\n'
          'let partial : Int -> Int = sharedApply helper in\n'
          'if sharedApply gate true then addInt (partial 0) (partial 0) else 0\n')
SOURCE_CROSS = ('import SharedPoly\nlet bonus = addInt 20 1 in\n'
                'let helper : Bool -> Int = \\b -> if b then bonus else 0 in\n'
                'let gate : Int -> Bool = \\n -> ltInt n 1 in\n'
                'let partial : Bool -> Int = sharedApply helper in\n'
                'if sharedApply gate 0 then addInt (partial true) (partial true) else 0\n')
SOURCES = {'shared-apply': SOURCE, 'shared-apply-cross': SOURCE_CROSS}
ACCESS_SCOPE = ('Fresh full metadata contracts, original slots, and guarded handoffs are checked. '
                'Events do not expose every owner Access or capsule; no arrow type argument is used.')


def arrow(a, b):
    return {'tag': 'arrow', 'from': a, 'to': b}


def source_facts(capture):
    n = capture['normalization']; raw = n['raw_normalized']
    require(capture['checked_type'] == INT and n['policy'] == 'shared-rank1-callable/1' and
            all(n[k] for k in ('declarations_equal', 'erasure_equal', 'normalized_rechecked',
                               'original_rechecked', 'root_type_alpha_equal')) and raw['tag'] == 'with_data',
            'complete checked normalization required')
    lets = []; current = raw['body']; path = ['body']
    while current['tag'] == 'let':
        lets.append((path, current)); current = current['body']; path = path + ['body']
    require(len(lets) == 5, 'five original lexical bindings required')
    (sp, shared), (bp, bonus), (hp, helper), (gp, gate), (pp, partial) = lets
    prefix = shared['value']; ids = []
    cursor_path = sp + ['value']
    while prefix['tag'] == 'type_lambda':
        require(prefix['bound'] == {'tag': 'bottom'}, 'unbounded rank1 prefix required')
        ids.append(prefix['id']); prefix = prefix['body']; cursor_path += ['body']
    require(len(ids) == 2 and len(set(ids)) == 2 and primitive(bonus['value'], 20, 1),
            'complete two-coordinate Scheme and pending bonus required')
    a, b = ({'tag': 'var', 'id': i} for i in ids); ab = arrow(a, b)
    require(prefix['tag'] == 'application', 'original shared annotation application required')
    passthrough(prefix['function'], arrow(ab, ab), 'shared annotation')
    creator = prefix['argument']; cp = cursor_path + ['argument']
    require(creator['tag'] == 'lambda' and creator['parameter_type'] == ab,
            'original higher-order creator type differs')
    local = creator['body']; child = local['body']; xp = cp + ['body', 'body']
    require(local['tag'] == 'let' and local['value']['tag'] == 'application' and
            var(local['value']['argument'], creator['parameter']) and
            child['tag'] == 'lambda' and child['parameter_type'] == a,
            'pending callable parameter wrapper required')
    passthrough(local['value']['function'], ab, 'callable parameter')
    second = child['body']
    require(second['tag'] == 'let' and second['value']['tag'] == 'application' and
            var(second['value']['argument'], child['parameter']) and
            second['body']['tag'] == 'application' and
            var(second['body']['function'], local['name']) and var(second['body']['argument'], second['name']),
            'ordinary higher-order body application differs')
    passthrough(second['value']['function'], a, 'second parameter')
    cross = helper['value']['argument']['parameter_type'] == BOOL
    helper_arg, gate_arg = (BOOL, INT) if cross else (INT, BOOL)
    for label, row, scalar, result_type in (('helper', helper, helper_arg, INT), ('gate', gate, gate_arg, BOOL)):
        rhs = row['value']; typ = arrow(scalar, result_type)
        require(rhs['tag'] == 'application' and rhs['argument']['tag'] == 'lambda' and
                rhs['argument']['parameter_type'] == scalar, 'ordinary ' + label + ' annotation required')
        passthrough(rhs['function'], typ, label + ' annotation')
        inner = rhs['argument']; param = inner['body']
        require(param['tag'] == 'let' and param['value']['tag'] == 'application' and
                var(param['value']['argument'], inner['parameter']), label + ' parameter wrapper differs')
        passthrough(param['value']['function'], scalar, label + ' parameter')
        if label == 'helper' and not cross:
            head, _, args = spine(param['body'], [])
            require(head['tag'] == 'primitive' and head['name'] == 'addInt' and len(args) == 2 and
                    var(args[0][1], param['name']) and var(args[1][1], bonus['name']),
                    'helper must add original parameter and captured bonus')
        elif label == 'helper':
            head, _, args = spine(param['body'], [])
            require(head['tag'] == 'primitive' and head['name'] == 'ifThenElse' and head['arguments'] == [INT] and
                    len(args) == 3 and var(args[0][1], param['name']) and var(args[1][1], bonus['name']) and
                    args[2][1] == {'tag':'int64','value':0}, 'helper must conditionally select original pending bonus')
        elif cross:
            head, _, args = spine(param['body'], [])
            require(head['tag'] == 'primitive' and head['name'] == 'ltInt' and len(args) == 2 and
                    var(args[0][1], param['name']) and args[1][1] == {'tag':'int64','value':1},
                    'gate must compare actual parameter with one')
        else:
            require(var(param['body'], param['name']), 'gate must return its actual parameter wrapper')
    pr = partial['value']
    require(pr['tag'] == 'application' and pr['argument']['tag'] == 'application' and
            var(pr['argument']['argument'], helper['name']), 'partial annotation/creator graph differs')
    passthrough(pr['function'], arrow(helper_arg, INT), 'partial annotation')
    int_use = pr['argument']['function']; ip = pp + ['value', 'argument', 'function']
    head, _, args = spine(current, path)
    require(head['tag'] == 'primitive' and head['name'] == 'ifThenElse' and head['arguments'] == [INT] and
            len(args) == 3 and args[2][1] == {'tag': 'int64', 'value': 0}, 'original lazy conditional differs')
    condition_path, condition = args[0]; bh, bpath, ba = spine(condition, condition_path)
    gate_value = {'tag':'int64','value':0} if cross else {'tag':'bool','value':True}
    call_value = {'tag':'bool','value':True} if cross else {'tag':'int64','value':0}
    require(len(ba) == 2 and var(ba[0][1], gate['name']) and ba[1][1] == gate_value,
            'Bool guard must apply original gate and source argument')
    for use in (int_use, bh):
        require(use['tag'] == 'type_application' and var(use['value'], shared['name']),
                'shared full inferred use differs')
    ah, _, aa = spine(args[1][1], args[1][0])
    require(ah['tag'] == 'primitive' and ah['name'] == 'addInt' and len(aa) == 2 and
            all(x['tag'] == 'application' and var(x['function'], partial['name']) and
                x['argument'] == call_value for _, x in aa),
            'two distinct calls must reuse the same partial binder')
    return dict(raw=raw, cross=cross, helper_arg=helper_arg, gate_arg=gate_arg, call_value=call_value, gate_value=gate_value,
        shared=shared, shared_path=sp, ids=ids, cursor=cursor_path,
        creator=creator, creator_path=cp, local=local, child=child, child_path=xp, second=second,
        bonus=bonus, bonus_path=bp+['value'], helper=helper, helper_path=hp+['value'],
        gate=gate, gate_path=gp+['value'], partial=partial, partial_path=pp+['value'],
        partial_view=ip, guard_view=bpath, condition_path=condition_path, branch_path=args[1][0],
        else_path=args[2][0], conditional_path=path, partial_calls=[p for p, _ in aa])


def structure(capture, verified, plan, generated):
    f = source_facts(capture); p = plan['program']; m = plan['binding']['source_map']
    require(verified['fragment_admitted'] and verified['normalization_replay'] == 'all exact independent fields match',
            'fresh independent replay required')
    require(not p['families'] and not p['layouts'] and not any(isinstance(n, dict) and
            n.get('op') in ('hole', 'fill', 'data', 'construct_sum', 'construct_nullary') for _, n in walk(p)),
            'fixture must remain nonnominal and nonrecursive')
    scheme = one(m['scheme_map'], 'one original Scheme'); definition = one(verified['fragment']['definitions'], 'one definition')
    require(scheme['binder'] == definition['binding']['id'] == f['shared']['name']['id'] and
            definition['binding_source'] == address(f['shared_path']) and
            scheme['rhs_cursor'] == definition['rhs_cursor'] == address(f['cursor']) and
            [x['id'] for x in definition['prefix']] == f['ids'] and
            len(p['schemes']) == 1 and p['schemes'][scheme['scheme']]['parameters'] == 2 and
            len(m['use_map']) == len(verified['fragment']['uses']) == len(p['instantiations']) == 2,
            'original binder/prefix/full Use correspondence differs')
    meta = json.loads(check_metadata(p).metadata_json)
    generic, seal = instruction(p, scheme['generalize']), instruction(p, scheme['seal'])
    pending = one([x for x in generic['body'] if x['op'] == 'application'], 'one original pending RHS')
    require(generic['op'] == 'generalize' and seal == {'op': 'seal', 'value': pending['out']} and
            not any(x['op'] == 'force' for x in generic['body']), 'shared RHS replaced or forced eagerly')
    carriers = m['carrier_map']
    lambdas = [c for c in carriers if c['kind'] == 'lambda']
    raw_lambdas = [path for path, node in walk(f['raw']['body'], ['body'])
                   if isinstance(node, dict) and node.get('tag') == 'lambda']
    require(sorted(c['source']['path'] for c in lambdas) == sorted(raw_lambdas) and
            len(lambdas) == len(p['functions']) and len(carriers) == len(p['functions']) + len(p['codes']),
            'source lambdas/carriers lost or cloned')
    carrier = lambda path, kind='lambda': one([c for c in carriers if c['source'] == address(path) and c['kind'] == kind],
                                            'exact source carrier')
    alloc = lambda path, kind: source_allocation(plan, path, kind)
    ops = { 'shared': alloc(f['cursor'], 'application'),
        'outer': alloc(f['cursor']+['function'], 'closure'), 'creator': alloc(f['creator_path'], 'closure'),
        'first_parameter': alloc(f['creator_path']+['body','value'], 'application'),
        'first_wrapper': alloc(f['creator_path']+['body','value','function'], 'closure'),
        'child': alloc(f['child_path'], 'closure'),
        'second_parameter': alloc(f['child_path']+['body','value'], 'application'),
        'body_application': alloc(f['child_path']+['body','body'], 'application'),
        'bonus': alloc(f['bonus_path'], 'thunk'), 'helper': alloc(f['helper_path'], 'application'),
        'helper_closure': alloc(f['helper_path']+['argument'], 'closure'),
        'helper_parameter': alloc(f['helper_path']+['argument','body','value'], 'application'),
        'helper_result': alloc(f['helper_path']+['argument','body','body'], 'thunk'),
        'gate': alloc(f['gate_path'], 'application'), 'gate_closure': alloc(f['gate_path']+['argument'], 'closure'),
        'gate_parameter': alloc(f['gate_path']+['argument','body','value'], 'application'),
        'partial': alloc(f['partial_path'], 'application'),
        'partial_creator': alloc(f['partial_path']+['argument'], 'application'),
        'guard_creator': alloc(f['condition_path']+['function'], 'application'),
        'guard_call': alloc(f['condition_path'], 'application') }
    ops['partial_calls'] = [alloc(path, 'application') for path in f['partial_calls']]
    child_carrier = carrier(f['child_path']); capture = one(child_carrier['mono_captures'], 'one callable capture')
    require(child_carrier['type_scope'] == scheme['scheme'] and not child_carrier['view_captures'] and
            capture['binder'] == f['local']['name']['id'] and capture['relation'] == 'down' and
            ops['child']['captures'] == {capture['capture']: ops['first_parameter']['out']} and
            ops['child']['function'] == child_carrier['ir_code'] and
            p['functions'][child_carrier['ir_code']]['captures'] ==
                {capture['capture']:{'layout':capture['layout'],'relation':'down'}},
            'pending callable capture/source relation differs')
    helper_carrier = carrier(f['helper_path']+['argument'])
    helper_capture = one(helper_carrier['mono_captures'], 'one helper bonus capture')
    require(helper_carrier['type_scope'] is None and not helper_carrier['view_captures'] and
            helper_capture['binder'] == f['bonus']['name']['id'] and
            ops['helper_closure']['captures'] == {helper_capture['capture']: ops['bonus']['out']},
            'helper must capture original pending bonus')
    helper_result_path = f['helper_path']+['argument','body','body']
    add_carrier = carrier(helper_result_path, 'conditional' if f['cross'] else 'primitive')
    add_bonus = one([x for x in add_carrier['mono_captures'] if x['binder'] == f['bonus']['name']['id']], 'addition bonus capture')
    add_parameter = one([x for x in add_carrier['mono_captures'] if x['binder'] == f['helper']['value']['argument']['body']['name']['id']], 'addition parameter capture')
    require(ops['helper_result']['captures'] == {add_bonus['capture']: helper_capture['capture'],
            add_parameter['capture']: ops['helper_parameter']['out']}, 'helper addition must preserve both owners')
    branches = None
    if f['cross']:
        head, _, args = spine(at(f['raw'], helper_result_path), helper_result_path)
        then = carrier(args[1][0], 'conditional-then'); otherwise = carrier(args[2][0], 'conditional-else')
        branch_capture = one(then['mono_captures'], 'helper true branch bonus owner')
        ops['helper_then'] = alloc(args[1][0], 'thunk'); ops['helper_else'] = alloc(args[2][0], 'thunk')
        ops['helper_else_scalar'] = alloc(args[2][0], 'scalar')
        ops['gate_result'] = alloc(f['gate_path']+['argument','body','body'], 'thunk')
        gate_carrier = carrier(f['gate_path']+['argument','body','body'], 'primitive')
        gate_capture = one(gate_carrier['mono_captures'], 'gate parameter owner')
        require(branch_capture['binder'] == f['bonus']['name']['id'] and not then['view_captures'] and
                ops['helper_then']['captures'] == {branch_capture['capture']:add_bonus['capture']} and
                not otherwise['mono_captures'] and not otherwise['view_captures'] and not ops['helper_else']['captures'] and
                gate_capture['binder'] == f['gate']['value']['argument']['body']['name']['id'] and
                ops['gate_result']['captures'] == {gate_capture['capture']:ops['gate_parameter']['out']},
                'conditional branches or gate must retain exact source owners')
        select = one([x for x in p['codes'][add_carrier['ir_code']]['body'] if x['op']=='select_i64'], 'helper selector')
        require(select['then'] == ops['helper_then']['out'] and select['else'] == ops['helper_else']['out'],
                'helper selection branches differ')
        branches = dict(then=then, otherwise=otherwise, capture=branch_capture, select=select, gate_capture=gate_capture)
    def typ(index):
        row = meta['types'][index]
        if row['tag'] == 'closed': return row['atom']
        require(row['tag'] == 'arrow' and row['protocol'] == 'repeat' and row['result_identity'] == 'unknown',
                'full callable contract changed')
        return [typ(row['argument']), typ(row['result'])]
    uses = {}
    # Labels denote source roles; each full vector fixes both argument and result.
    for label, path, atom, raw_atom, argument in (('partial',f['partial_view'],'#i64',INT,f['helper_arg']),
                                                ('guard',f['guard_view'],'#bool',BOOL,f['gate_arg'])):
        argument_atom = '#i64' if argument == INT else '#bool'
        vector = [argument_atom, atom]
        source = one([x for x in m['use_map'] if x['source'] == address(path)], 'exact source Use')
        replay = one([x for x in verified['fragment']['uses'] if x['id'] == source['use']], 'replayed Use')
        require(replay['source'] == source['source'] and replay['definition'] == definition['id'] == source['definition'] and
                replay['arguments'] == [argument,raw_atom] and
                [p['types'][x]['layout'] for x in source['arguments']] == vector, 'complete two-coordinate Use differs')
        uname = one([k for k,v in p['instantiations'].items() if v == {'scheme':scheme['scheme'],'arguments':source['arguments']}], 'full instantiation')
        row = one([x for x in meta['uses'] if x['name'] == uname], 'registered Use')
        operation = instruction(p, one(row['occurrences'], 'one upstream instantiation'))
        env = meta['environments'][row['env']]
        require(operation['op'] == 'instantiate' and operation['instantiation'] == uname and
                env['mode'] == 'CLOSED' and [meta['types'][i]['atom'] for i in env['arguments']] == vector and
                typ(row['result_type']) == [vector,vector], 'closed higher-order metadata contract differs')
        uses[label] = dict(source=source,row=row,operation=operation,atom=atom,argument_atom=argument_atom,vector=vector)
    require(uses['partial']['row']['env'] != uses['guard']['row']['env'] and
            uses['partial']['row']['result_type'] != uses['guard']['row']['result_type'], 'distinct full-vector contracts collapsed')
    cond = carrier(f['conditional_path'], 'conditional'); view = one(cond['view_captures'], 'captured complete Bool view')
    require(view['definition'] == definition['id'] and view['arguments'] == uses['guard']['source']['arguments'] and
            view['occurrences'] == [uses['guard']['source']['use']] and
            uses['guard']['source']['source_view'] == {'kind':'captured','carrier':cond['carrier'],'capture':view['capture']},
            'conditional must retain upstream complete Bool view')
    for table in ('functions','codes'):
        require(not any(isinstance(n,dict) and n.get('op') == 'instantiate' for row in p[table].values() for _,n in walk(row['body'])),
                'callback must not reconstruct shared views')
    child_code = one([x for x in meta['codes'] if x['name'] == child_carrier['ir_code']], 'registered child Code')
    child_site = one([x for x in meta['sites'] if x['code'] == child_code['id'] and x['category'] == 'CLOSURE'], 'child Site')
    require(instruction(p,child_site['path']) == ops['child'] and child_site['context'] ==
            {'kind':'execution','code':one([x['id'] for x in meta['codes'] if x['name'] == ops['creator']['function']], 'creator Code'),
             'scheme':uses['partial']['row']['scheme']}, 'child allocation must retain creator context')
    executions = {}
    for label,u in uses.items():
        se = one([x for x in meta['site_executions'] if x['site'] == child_site['id'] and x['env'] == u['row']['env']], 'closed child SiteExecution')
        ce = meta['code_executions'][se['code_execution']]
        require(se['origin_kind'] == 'INSTANCE' and ce['env'] == se['env'] and ce['code'] == child_code['id'] and
                se['principal_type'] == ce['callable_type'] and typ(ce['callable_type']) == u['vector'] and
                ce['captures'] == [{'name':capture['capture'],'relation':'down','type':ce['callable_type']}],
                'INSTANCE callable capture lost full resolved arrow')
        executions[label] = se
    definitions = [int(x) for x in re.findall(r'static Rt8Handle \*rt8_body_(\d+)\(',generated)]
    registrations = [(int(a),int(b)) for a,b in re.findall(r'\{ \.code_id = (\d+), \.body = rt8_body_(\d+) \}',generated)]
    require(definitions == list(range(len(meta['codes']))) and registrations == [(i,i) for i in definitions],
            'real generated Code registrations differ')
    return dict(facts=f,ops=ops,metadata=meta,scheme=scheme,uses=uses,child_capture=capture,
        child_code=child_code,child_site=child_site,child_executions=executions,
        helper_capture=helper_capture,add_bonus=add_bonus,add_parameter=add_parameter,branches=branches,
        conditional_code=cond['ir_code'],conditional_view=view)


def observe(e, info):
    require(e['schema'] == 'resource-ir-v8-run/1' and e['state'] == e['fault'] == 0 and
            e['result'] == {'kind':'i64','value':42} and e['scalar_result_kind'] == 1 and e['scalar_result'] == 42 and
            e['events_omitted'] == 0 and e['events_emitted'] == len(e['events']) and
            e['metrics']['entries_completed'] == 1, 'complete native Int42 report required')
    require(e['guards_failed_mask'] == 0 and e['guards_checked_mask'] == EXPECTED_GUARDS and
            e['guard_work_limit'] == 67_108_864 and 0 < e['guard_work_used'] <= e['guard_work_limit'],
            'native guard/work contract differs')
    ledger(e,True); events=e['events']; meta=info['metadata']; ops=info['ops']
    selected=lambda kind:[(i,x) for i,x in enumerate(events) if x['event']==kind]
    allocations=selected('allocate'); nodes={x['node']:x for _,x in allocations}
    require(len(nodes)==len(allocations),'duplicate node identity')
    def allocations_for(op):
        rows=[(i,x) for i,x in allocations if x['out']==op['out']]
        require(all(x['opcode']==op['op'] and x['code']==(op['function'] if op['op']=='closure' else op.get('code'))
                    for _,x in rows),'source allocation Code/opcode differs')
        return rows
    def alloc(op):return one(allocations_for(op),'one source allocation')
    def in_frame(op,frame):return one([(i,x) for i,x in allocations_for(op) if x['frame']==frame],'exact callback allocation')
    def memo(node):return one([(i,x) for i,x in selected('memo_publish') if x['destination']==node],'one exact memo')
    def demand(node):return one([(i,x) for i,x in selected('update_pin') if x['node']==node],'one pending demand')
    calls=lambda node:[(i,x) for i,x in selected('invoke_enter') if x['closure']==node]
    returns=lambda node:[(i,x) for i,x in selected('invoke_raw_return') if x['closure']==node]
    frames=lambda node:[(i,x) for i,x in selected('frame_enter') if x['context'].get('node')==node]
    scalars={x['node']:(x['kind'],x['value']) for _,x in selected('scalar_value')}
    _,bonus=alloc(ops['bonus']);_,helper=alloc(ops['helper']);_,helper_closure=alloc(ops['helper_closure'])
    _,gate=alloc(ops['gate']);_,gate_closure=alloc(ops['gate_closure']);_,partial=alloc(ops['partial'])
    require(bonus['state']=='THUNK' and helper['state']==gate['state']==partial['state']=='APPLICATION' and
            helper_closure['env_id']==gate_closure['env_id']==0 and
            helper_closure['slots']=={info['helper_capture']['capture']:bonus['node']} and not gate_closure['slots'] and
            helper['slots']['$argument']==helper_closure['node'] and gate['slots']['$argument']==gate_closure['node'],
            'original pending callable/bonus graph differs')
    begin_i,_=one(selected('generic_begin'),'one original generic begin')
    seal_i,seal=one(selected('generic_seal'),'one original generic seal')
    _,shared=alloc(ops['shared']);_,body=alloc(ops['creator']);_,outer=alloc(ops['outer'])
    require(begin_i<seal_i and seal['node']==shared['node'] and shared['state']=='APPLICATION' and
            shared['slots']=={'$function':outer['node'],'$argument':body['node']} and
            shared['out']==info['scheme']['result_owner'] and body['env_id']==shared['env_id']!=0,
            'one original neutral shared RHS/body required')
    smi,sm=memo(shared['node'])
    require(sm['result']==body['node'] and len(calls(outer['node']))==1,'neutral shared RHS must memo once')
    entry=one([x for _,x in selected('frame_enter') if x['context']['kind']=='entry'],'one entry frame')['frame']
    view_events=selected('instantiate'); observed={}
    require(len(view_events)==2,'two complete upstream views required')
    for label,u in info['uses'].items():
        i,x=one([(i,x) for i,x in view_events if x['use']==u['row']['id']],'exact Use event')
        before,after=meta['accesses'][x['old_access']],meta['accesses'][x['new_access']]
        require(x['node']==shared['node'] and x['frame']==entry and x['mode']=='own' and x['anchor'] is None and
                before['mode']=='SCHEME' and after['mode']=='MONO' and
                before['site']==after['site']==shared['site_id'] and
                before['origin_env']==after['origin_env']==shared['env_id'] and
                meta['environments'][after['origin_env']]['mode']=='NEUTRAL' and after['scheme'] is None and
                after['type']==u['row']['result_type'] and after['use_env']==u['row']['env'],
                'full shared Access/origin correspondence differs')
        observed[label]={'event_index':i,'origin_env':after['origin_env'],'use_env':after['use_env'],'access':after['id']}
    require(observed['partial']['event_index'] < observed['guard']['event_index'] < smi,
            'full views must be instantiated upstream in source order before shared demand')
    creator_calls,creator_returns,creator_frames=calls(body['node']),returns(body['node']),frames(body['node'])
    require(len(creator_calls)==len(creator_returns)==len(creator_frames)==2 and
            smi<creator_calls[0][0]<creator_calls[1][0] and
            [x['argument'] for _,x in creator_calls]==[gate['node'],helper['node']],
            'shared body demand must be guard then partial with original callable owners')
    children={}; details={}; first_parameters={}; child_call_rows={}
    for label,(ci,call),(ri,returned),(fi,frame) in zip(('guard','partial'),creator_calls,creator_returns,creator_frames):
        ai,child=in_frame(ops['child'],frame['frame']);pi,param=in_frame(ops['first_parameter'],frame['frame'])
        wi,wrapper=in_frame(ops['first_wrapper'],frame['frame']);children[label]=child;first_parameters[label]=param
        expected_count=1 if label=='guard' else 2
        cc,cr,cf=calls(child['node']),returns(child['node']),frames(child['node']);child_call_rows[label]=cc
        require(child['state']=='CLOSURE' and child['code']==info['child_code']['name'] and
                child['site_id']==info['child_site']['id'] and child['env_id']==info['child_executions'][label]['env'] and
                child['slots']=={info['child_capture']['capture']:param['node']} and
                param['state']=='APPLICATION' and param['slots']=={'$function':wrapper['node'],'$argument':call['argument']} and
                returned['result']==child['node'] and returned['argument']==call['argument'] and
                frame['context']['name']==ops['creator']['function'] and ci<fi<wi<pi<ai<ri and
                len(cc)==len(cr)==len(cf)==expected_count and ri<cc[0][0] and demand(param['node'])[0]>ri,
                'returned INSTANCE must retain pending callable after creator return')
        require(memo(param['node'])[1]['result']==(gate_closure if label=='guard' else helper_closure)['node'],
                'pending callable wrapper memo must preserve original closure')
        handoffs=[(i,x) for i,x in selected('closure_capture_handoff') if x['node']==child['node']]
        require(len(handoffs)==expected_count and all(x['protocol']=='repeat' and
                set(x['owners'])=={info['child_capture']['capture']} for _,x in handoffs),
                'repeated child capture handoff differs')
        for (ii,inv),(rr,ret),(ff,fr),(hi,handoff) in zip(cc,cr,cf,handoffs):
            require(ri<hi<ii<ff<rr and fr['context']['kind']=='function' and
                    fr['context']['name']==info['child_code']['name'] and ret['argument']==inv['argument'],
                    'registered child callback ordering differs')
            spi,sp=in_frame(ops['second_parameter'],fr['frame']);bai,ba=in_frame(ops['body_application'],fr['frame'])
            require(sp['state']==ba['state']=='APPLICATION' and sp['slots']['$argument']==inv['argument'] and
                    ba['slots']=={'$function':param['node'],'$argument':sp['node']} and
                    ret['result']==ba['node'] and ff<spi<bai<rr,
                    'child must return the ordinary pending callable application')
        details[label]={'child':child['node'],'pending_callable':param['node'],'calls':expected_count,'env':child['env_id'],
                        'argument_type':info['uses'][label]['argument_atom'],'result_type':info['uses'][label]['atom']}
    require(children['partial']['node']!=children['guard']['node'] and
            len(allocations_for(ops['child']))==len(allocations_for(ops['first_parameter']))==2 and
            len(allocations_for(ops['body_application']))==len(allocations_for(ops['second_parameter']))==3,
            'generic body/child graph cloned or call allocations lost')
    _,ic=alloc(ops['partial_creator']);_,bc=alloc(ops['guard_creator']);_,guard_call=alloc(ops['guard_call'])
    require(ic['slots']=={'$function':shared['node'],'$argument':helper['node']} and
            bc['slots']=={'$function':shared['node'],'$argument':gate['node']} and
            partial['slots']['$argument']==ic['node'] and
            memo(ic['node'])[1]['result']==memo(partial['node'])[1]['result']==children['partial']['node'] and
            memo(bc['node'])[1]['result']==children['guard']['node'] and
            guard_call['slots']['$function']==bc['node'] and
            scalars.get(guard_call['slots']['$argument'])==(('i64',0) if info['facts']['cross'] else ('bool',True)) and
            child_call_rows['guard'][0][1]['argument']==guard_call['slots']['$argument'] and
            scalars.get(memo(guard_call['node'])[1]['result'])==('bool',True),
            'partial or guard memo lost exact shared child')
    require(memo(guard_call['node'])[0]<demand(partial['node'])[0] and
            memo(partial['node'])[0]<child_call_rows['partial'][0][0],
            'partial must remain lazy until Bool guard finishes')
    partial_apps=[alloc(x)[1] for x in ops['partial_calls']]
    require(len({x['node'] for x in partial_apps})==2 and
            all(x['slots']['$function']==partial['node'] and scalars.get(x['slots']['$argument'])==(('bool',True) if info['facts']['cross'] else ('i64',0)) for x in partial_apps) and
            [x['argument'] for _,x in child_call_rows['partial']]==[x['slots']['$argument'] for x in partial_apps],
            'two source calls must reuse one partial without result reuse')
    helper_calls,helper_returns,helper_frames=calls(helper_closure['node']),returns(helper_closure['node']),frames(helper_closure['node'])
    require(len(helper_calls)==len(helper_returns)==len(helper_frames)==2 and len(calls(gate_closure['node']))==1 and
            memo(helper['node'])[1]['result']==helper_closure['node'] and
            memo(gate['node'])[1]['result']==gate_closure['node'], 'original helper must invoke twice and gate once')
    bonus_demand,_=demand(bonus['node']);bonus_cb,_=one([(i,x) for i,x in selected('callback_enter') if x['node']==bonus['node']], 'bonus callback once')
    bonus_memo,bm=memo(bonus['node'])
    require(child_call_rows['partial'][0][0]<helper_calls[0][0]<bonus_demand<bonus_cb<bonus_memo<helper_calls[1][0] and
            scalars.get(bm['result'])==('i64',21), 'bonus must evaluate once during first helper call')
    addition_nodes=[]
    for index,((hi,hcall),(hri,hret),(hfi,hframe)) in enumerate(zip(helper_calls,helper_returns,helper_frames)):
        cfi,cframe=frames(children['partial']['node'])[index]
        _,sp=in_frame(ops['second_parameter'],cframe['frame']);_,ba=in_frame(ops['body_application'],cframe['frame'])
        hpi,hp=in_frame(ops['helper_parameter'],hframe['frame']);adi,add=in_frame(ops['helper_result'],hframe['frame']);addition_nodes.append(add['node'])
        require(hcall['argument']==sp['node'] and hp['slots']['$argument']==sp['node'] and
                add['state']=='THUNK' and add['slots']=={info['add_bonus']['capture']:bonus['node'],info['add_parameter']['capture']:hp['node']} and
                hret['result']==add['node'] and hi<hfi<hpi<adi<hri and
                hframe['context']['name']==ops['helper_closure']['function'], 'helper pending result/parameter chain differs')
        expected_argument = ('bool',True) if info['facts']['cross'] else ('i64',0)
        require(scalars.get(memo(hp['node'])[1]['result'])==expected_argument and
                scalars.get(memo(sp['node'])[1]['result'])==expected_argument, 'parameter wrappers must retain original source argument')
        if info['facts']['cross']:
            branch = info['branches']; afi,aframe = one(frames(add['node']), 'helper conditional frame')
            ti,t = in_frame(ops['helper_then'],aframe['frame']); ei,otherwise = in_frame(ops['helper_else'],aframe['frame'])
            si,selection = one([(i,x) for i,x in selected('select_i64') if x['frame']==aframe['frame']], 'helper true selection')
            tci,_ = one([(i,x) for i,x in selected('callback_enter') if x['node']==t['node']], 'selected helper branch callback')
            tri,tr = one([(i,x) for i,x in selected('raw_return') if x['source']==t['node']], 'selected helper branch return')
            require(t['slots']=={branch['capture']['capture']:bonus['node']} and not otherwise['slots'] and
                    selection['out']==branch['select']['out'] and selection['condition_node']==memo(hp['node'])[1]['result'] and
                    selection['condition_value'] is True and selection['then_node']==selection['result']==t['node'] and
                    selection['else_node']==otherwise['node'] and afi<ti<ei<si<tci<tri and
                    one([x for _,x in selected('raw_return') if x['source']==add['node']], 'helper conditional return')['result']==t['node'] and
                    tr['result']==bonus['node'] and tr['result_state']==('THUNK' if index==0 else 'MEMO') and
                    memo(t['node'])[1]['result']==bm['result'], 'helper conditional must select the retained pending bonus')
            require(not any(x['node']==otherwise['node'] for _,x in selected('update_pin')+selected('callback_enter')) and
                    not any(x['destination']==otherwise['node'] for _,x in selected('memo_publish')) and
                    not allocations_for(ops['helper_else_scalar']), 'unselected helper branch must remain undemanded')
        result=memo(add['node'])[1]['result']
        require(scalars.get(result)==('i64',21) and memo(ba['node'])[1]['result']==result and
                memo(partial_apps[index]['node'])[1]['result']==result and
                len([x for _,x in selected('callback_enter') if x['node']==add['node']])==1,
                'ordinary helper call must memo its evaluated result')
    require(len(set(addition_nodes))==2,'two helper calls must not clone or reuse one invocation result graph')
    if info['facts']['cross']:
        _,gframe = one(frames(gate_closure['node']), 'gate frame')
        _,gp = in_frame(ops['gate_parameter'],gframe['frame']); _,gr = in_frame(ops['gate_result'],gframe['frame'])
        require(scalars.get(memo(gp['node'])[1]['result'])==('i64',0) and
                gr['slots']=={info['branches']['gate_capture']['capture']:gp['node']} and
                one(returns(gate_closure['node']), 'gate return')[1]['result']==gr['node'] and
                scalars.get(memo(gr['node'])[1]['result'])==('bool',True), 'cross gate must preserve its pending comparison')
    cond=one([x for _,x in allocations if x['code']==info['conditional_code']],'one conditional carrier')
    require(cond['slots'][info['conditional_view']['capture']]==shared['node'], 'conditional lost original shared view owner')
    return {'scalar':42,'shared_node':shared['node'],'shared_body':body['node'],'children':details,
        'partial_node':partial['node'],'partial_evaluations':1,'helper_node':helper_closure['node'],'helper_calls':2,
        'helper_results':addition_nodes,'bonus_node':bonus['node'],'bonus_evaluations':1,'views':observed,
        'memory':e['memory'],'memory_categories':e['memory_categories'],'access_scope':ACCESS_SCOPE,
        'case':'shared-apply-cross' if info['facts']['cross'] else 'shared-apply',
        'complete_vectors':{k:u['vector'] for k,u in info['uses'].items()},
        'coordinate_order_tested':info['facts']['cross'],'helper_conditional_selections':2 if info['facts']['cross'] else 0}


def copied_controls(evaluation, info):
    """These are corrupted copied observations, not native fault injections."""
    results=[];ops=info['ops']
    def event(r,kind,predicate=lambda x:True):return one([x for x in r['events'] if x['event']==kind and predicate(x)],'control event')
    def alloc(r,op):return one([x for x in r['events'] if x['event']=='allocate' and x['out']==op['out']],'control allocation')
    def child(r,label='partial'):
        return one([x for x in r['events'] if x['event']=='allocate' and x['out']==ops['child']['out'] and
                    x['env_id']==info['uses'][label]['row']['env']], 'control child')
    def reject(name,mutation,expected):
        row=copy.deepcopy(evaluation);mutation(row)
        try:observe(row,info)
        except AssertionError as exc:require(expected in str(exc),name+' rejected for wrong reason: '+str(exc))
        else:raise ValueError(name+' corrupted observation accepted')
        results.append({'control':name,'status':'rejected'})
    reject('lost-events',lambda r:r.__setitem__('events_omitted',1),'complete native Int42')
    reject('live-ledger',lambda r:r['memory'].__setitem__('live_bytes',1),'ledger arithmetic differs')
    reject('shared-origin-E0',lambda r:alloc(r,ops['shared']).__setitem__('env_id',0),'one original neutral shared')
    reject('shared-memo-wrong-body',lambda r:event(r,'memo_publish',lambda x:x['destination']==alloc(r,ops['shared'])['node']).__setitem__(
        'result',alloc(r,ops['outer'])['node']),'neutral shared RHS must memo once')
    reject('foreign-shared-use-node',lambda r:event(r,'instantiate',lambda x:x['use']==info['uses']['partial']['row']['id']).__setitem__(
        'node',alloc(r,ops['helper'])['node']),'full shared Access/origin')
    reject('lost-owned-view',lambda r:event(r,'instantiate',lambda x:x['use']==info['uses']['guard']['row']['id']).__setitem__('mode','loan'),
        'full shared Access/origin')
    reject('use-loses-projection',lambda r:event(r,'instantiate',lambda x:x['use']==info['uses']['partial']['row']['id']).__setitem__(
        'new_access',event(r,'instantiate',lambda x:x['use']==info['uses']['partial']['row']['id'])['old_access']),
        'full shared Access/origin')
    def early_child(r):
        inv=next(x for x in r['events'] if x['event']=='invoke_enter' and x['closure']==child(r)['node'])
        creator=event(r,'invoke_raw_return',lambda x:x['closure']==alloc(r,ops['creator'])['node'] and
                      x['argument']==alloc(r,ops['helper'])['node'])
        r['events'].remove(inv);r['events'].insert(r['events'].index(creator),inv)
    reject('child-before-creator-return',early_child,'returned INSTANCE must retain')
    def extra_helper_call(r):
        inv=next(x for x in r['events'] if x['event']=='invoke_enter' and x['closure']==alloc(r,ops['helper_closure'])['node'])
        r['events'].append(copy.deepcopy(inv));r['events_emitted']=len(r['events'])
    reject('duplicate-helper-invocation',extra_helper_call,'original helper must invoke twice')
    reject('child-code-substitution',lambda r:child(r).__setitem__('code','not-the-source-code'),'source allocation Code/opcode')
    reject('child-site-substitution',lambda r:child(r).__setitem__('site_id',-1),'returned INSTANCE must retain')
    reject('child-env-E0',lambda r:child(r).__setitem__('env_id',0),'returned INSTANCE must retain')
    reject('child-capture-owner',lambda r:child(r)['slots'].__setitem__(info['child_capture']['capture'],alloc(r,ops['bonus'])['node']),
        'returned INSTANCE must retain')
    def wrong_parameter(r):
        captured=child(r)['slots'][info['child_capture']['capture']]
        event(r,'allocate',lambda x:x['node']==captured)['slots']['$argument']=alloc(r,ops['gate'])['node']
    reject('callable-parameter-owner',wrong_parameter,'returned INSTANCE must retain')
    reject('creator-return-substitution',lambda r:event(r,'invoke_raw_return',lambda x:x['closure']==alloc(r,ops['creator'])['node'] and
        x['argument']==alloc(r,ops['helper'])['node']).__setitem__('result',alloc(r,ops['helper_closure'])['node']),
        'returned INSTANCE must retain')
    reject('missing-child-handoff',lambda r:event(r,'closure_capture_handoff',lambda x:x['node']==child(r,'guard')['node'])['owners'].clear(),
        'repeated child capture handoff')
    reject('partial-memo-substitution',lambda r:event(r,'memo_publish',lambda x:x['destination']==alloc(r,ops['partial'])['node']).__setitem__(
        'result',alloc(r,ops['helper_closure'])['node']),'partial or guard memo')
    def duplicate_memo(r,op):
        r['events'].append(copy.deepcopy(event(r,'memo_publish',lambda x:x['destination']==alloc(r,op)['node'])))
        r['events_emitted']=len(r['events'])
    reject('duplicate-partial-memo',lambda r:duplicate_memo(r,ops['partial']),'one exact memo')
    reject('second-partial-call-substitution',lambda r:alloc(r,ops['partial_calls'][1])['slots'].__setitem__(
        '$function',alloc(r,ops['helper'])['node']),'two source calls must reuse')
    reject('helper-lost-bonus-owner',lambda r:alloc(r,ops['helper_closure'])['slots'].__setitem__(info['helper_capture']['capture'],-1),
        'original pending callable/bonus graph')
    reject('duplicate-bonus-memo',lambda r:duplicate_memo(r,ops['bonus']),'one exact memo')
    reject('bonus-value-substitution',lambda r:event(r,'memo_publish',lambda x:x['destination']==alloc(r,ops['bonus'])['node']).__setitem__(
        'result',alloc(r,ops['gate_closure'])['node']),'bonus must evaluate once')
    def early_bonus(r):
        x=event(r,'update_pin',lambda x:x['node']==alloc(r,ops['bonus'])['node']);r['events'].remove(x);r['events'].insert(0,x)
    reject('eager-bonus',early_bonus,'bonus must evaluate once')
    def wrong_add(r):
        x=next(x for x in r['events'] if x['event']=='allocate' and x['out']==ops['helper_result']['out'])
        x['slots'][info['add_bonus']['capture']]=-1
    reject('helper-addition-capture',wrong_add,'helper pending result/parameter')
    def wrong_child_body(r):
        x=next(x for x in r['events'] if x['event']=='allocate' and x['out']==ops['body_application']['out'])
        x['slots']['$function']=alloc(r,ops['helper_closure'])['node']
    reject('bypassed-callable-wrapper',wrong_child_body,'child must return the ordinary pending')
    reject('conditional-view-owner',lambda r:event(r,'allocate',lambda x:x['code']==info['conditional_code'])['slots'].__setitem__(
        info['conditional_view']['capture'],alloc(r,ops['helper'])['node']),'conditional lost original shared')
    if info['facts']['cross']:
        def helper_selection(r):
            then_nodes={x['node'] for x in r['events'] if x['event']=='allocate' and x['out']==ops['helper_then']['out']}
            return next(x for x in r['events'] if x['event']=='select_i64' and x['then_node'] in then_nodes)
        reject('swapped-child-environment',lambda r:child(r).__setitem__('env_id',info['uses']['guard']['row']['env']),
               'returned INSTANCE must retain')
        reject('wrong-partial-argument-kind',lambda r:alloc(r,ops['partial_calls'][1])['slots'].__setitem__(
               '$argument',alloc(r,ops['bonus'])['node']), 'two source calls must reuse')
        reject('helper-selects-false',lambda r:helper_selection(r).__setitem__('result',helper_selection(r)['else_node']),
               'helper conditional must select')
        reject('helper-condition-false',lambda r:helper_selection(r).__setitem__('condition_value',False),
               'helper conditional must select')
        def wrong_then(r):
            node=helper_selection(r)['then_node']
            event(r,'allocate',lambda x:x['node']==node)['slots'][info['branches']['capture']['capture']]=-1
        reject('selected-branch-lost-bonus',wrong_then,'helper conditional must select')
        def force_else(r):
            r['events'].append({'event':'update_pin','node':helper_selection(r)['else_node'],'pin':-1})
            r['events_emitted']=len(r['events'])
        reject('unselected-helper-branch-demand',force_else,'unselected helper branch must remain')
        def bypass_bonus_memo(r):
            nodes={x['node'] for x in r['events'] if x['event']=='allocate' and x['out']==ops['helper_then']['out']}
            rows=[x for x in r['events'] if x['event']=='raw_return' and x['source'] in nodes]
            rows[1]['result_state']='THUNK'
        reject('second-branch-forgets-bonus-memo',bypass_bonus_memo,'helper conditional must select')
    return results


def structure_controls(capture, verified, plan, generated):
    results=[]
    def reject(name,mutation,expected):
        c,v,p=copy.deepcopy(capture),copy.deepcopy(verified),copy.deepcopy(plan)
        g=mutation(c,v,p,generated)
        try:structure(c,v,p,g)
        except AssertionError as exc:require(expected in str(exc),name+' rejected for wrong reason: '+str(exc))
        else:raise ValueError(name+' corrupted structure accepted')
        results.append({'control':name,'status':'rejected'})
    def edit(fn):
        def change(c,v,p,g):fn(c,v,p);return g
        return change
    reject('wrong-binder',edit(lambda c,v,p:p['binding']['source_map']['scheme_map'][0].__setitem__('binder',-1)),
        'original binder/prefix/full Use')
    reject('lost-coordinate',edit(lambda c,v,p:p['binding']['source_map']['use_map'][0]['arguments'].pop()),'complete two-coordinate Use')
    reject('wrong-replayed-coordinate',edit(lambda c,v,p:v['fragment']['uses'][0]['arguments'].__setitem__(1,BOOL if v['fragment']['uses'][0]['arguments'][1] == INT else INT)),
        'complete two-coordinate Use')
    reject('cloned-source-lambda',edit(lambda c,v,p:p['binding']['source_map']['carrier_map'].append(
        copy.deepcopy(p['binding']['source_map']['carrier_map'][0]))),'source lambdas/carriers lost')
    def child_change(c,v,p,key,value):
        f=source_facts(c);carrier=one([x for x in p['binding']['source_map']['carrier_map'] if x['source']==address(f['child_path'])],'control child carrier')
        carrier['mono_captures'][0][key]=value
    reject('callable-capture-binder',edit(lambda c,v,p:child_change(c,v,p,'binder',-1)), 'pending callable capture/source')
    reject('callable-support-upgrade',edit(lambda c,v,p:child_change(c,v,p,'relation','below')), 'pending callable capture/source')
    reject('callable-type-erasure',edit(lambda c,v,p:child_change(c,v,p,'layout','#i64')), 'pending callable capture/source')
    def replace_ordinary(c,v,p):
        f=source_facts(c);at(c['normalization']['raw_normalized'],f['child_path']+['body'])['body']={'tag':'int64','value':42}
    reject('direct-result-shortcut',edit(replace_ordinary),'ordinary higher-order body application')
    def replace_second_call(c,v,p):
        f=source_facts(c);at(c['normalization']['raw_normalized'],f['partial_calls'][1])['argument']['value']=False if f['cross'] else 1
    reject('changed-second-source-call',edit(replace_second_call),'two distinct calls must reuse')
    reject('generated-callback-substitution',lambda c,v,p,g:g.replace('.body = rt8_body_0 }','.body = rt8_body_1 }',1),
        'real generated Code registrations')
    if source_facts(capture)['cross']:
        reject('transposed-use-coordinates',edit(lambda c,v,p:p['binding']['source_map']['use_map'][0]['arguments'].reverse()),
               'complete two-coordinate Use')
        reject('transposed-replay-coordinates',edit(lambda c,v,p:v['fragment']['uses'][0]['arguments'].reverse()),
               'complete two-coordinate Use')
        def changed_branch(c,v,p):
            f=source_facts(c);body=at(c['normalization']['raw_normalized'],f['helper_path']+['argument','body','body'])
            body['function']['argument']={'tag':'int64','value':21}
        reject('replace-pending-bonus-with-result',edit(changed_branch),'helper must conditionally select original pending bonus')
    return results


def run_case(args, output, env, case='shared-apply'):
    source_text=SOURCES[case]
    inputs=output/'inputs';inputs.mkdir()
    (inputs/'SharedPoly.emlf').write_text(SHARED,encoding='utf-8');source=inputs/'main.emlf';source.write_text(source_text,encoding='utf-8')
    target=output/case
    build.run([sys.executable,'-B',str(BASE/'run_source_v8.py'),str(source),'--module-root',str(inputs),
               '--ghc',args.ghc,'--cc',args.cc,'--output',str(target)],output,case,cwd=BASE,env=env,
              wall=1200,cpu=900,memory=16<<30,termination_grace=15,stdout_limit=1<<20,stderr_limit=1<<20,file_limit=64<<20)
    require(not bounded_read(output/(case+'.stderr'),1<<20),'successful CLI stderr')
    result=read_json(target/'result.json');e=read_json(target/'native/run.stdout')
    require(result['status']=='complete' and result['failure_policy']=='retain' and result['native']==e and
            'placement' not in result,'fresh default CLI result differs')
    c=read_json(target/'capture.stdout');v=read_json(target/'verification.json');p=read_json(target/'planned.json',8<<20)
    require(p['binding']['mode']=='coarse-owned','default placement changed')
    g=bounded_read(target/'native/ir8_runtime_generated.c',8<<20).decode();info=structure(c,v,p,g)
    row={'status':'passed','observation':observe(e,info),'copied_report_controls':copied_controls(e,info),
         'copied_structure_controls':structure_controls(c,v,p,g),
         'source_hashes':{'main.emlf':build.sha(source_text.encode()),'SharedPoly.emlf':build.sha(SHARED.encode())}}
    build.save(target/'higher-order-shared-observations.json',row)
    print(case+': PASS (one shared RHS, pending callable capture, reused partial, helper twice/bonus once, Int42)',flush=True)
    return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc',required=True);parser.add_argument('--cc',default='cc')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case',choices=('all',)+tuple(SOURCES),default='all');args=parser.parse_args()
    output=args.output.absolute()
    require(output.resolve()==output and output!=BASE.parents[2] and BASE.parents[2] not in output.parents,
            'output must be canonical, fresh and outside checkout')
    output.mkdir(parents=True,exist_ok=False);env=cli.environment(output);build.SUITE_DEADLINE=time.monotonic()+1500
    rows={}
    try:
        for case in SOURCES if args.case=='all' else (args.case,):
            case_output=output/case;case_output.mkdir()
            rows[case]=run_case(args,case_output,env,case)
    except BaseException as exc:
        try:build.save(output/'failure.json',{'error':repr(exc)})
        except BaseException as persistence:exc.add_note('Failure persistence also failed: '+repr(persistence))
        raise
    build.save(output/'results.json',{'status':'passed','cases':rows});return 0


if __name__=='__main__':raise SystemExit(main())
