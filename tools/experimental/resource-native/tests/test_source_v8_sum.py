#!/usr/bin/env python3
"""Two fresh real-source SUM CLI tests; opt in with GHC9.14.1 and a C11 compiler.

Each source invokes the existing CLI and fresh producer, then independently
joins declaration/arm identities to actual selected factories and lazy payloads.
Number and Empty both preserve the unforced external addInt20 1 allocation.
Only Number may demand it. No saved capture, default-runtime change, or eager
scalar-argument assumption substitutes for the actual source/native run.
--data-groups changes eligible support placement; SUM/case remain coarse.
"""
import argparse
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE / 'tests')]
import run_source_v8 as cli
import source_build_v8 as build
from source_snapshot_v8 import bounded_read
from test_shared_source_native import at, instruction

SHARED = ('module SharedPoly (sharedId) where\n'
          'sharedId : forall a. a -> a\nsharedId x = x\n')
SOURCE = ('import SharedPoly\ndata Choice = Empty | Number Int;\n'
          'let payload = addInt 20 1 in\nlet choice = {constructor} in\n'
          'case choice of {{\n'
          '  Empty -> if sharedId true then sharedId 42 else 0;\n'
          '  Number n -> if sharedId true then sharedId (addInt n payload) else 0\n}}\n')
CASES = ({'name': 'number', 'variant': 1, 'source': SOURCE.format(constructor='Number payload')},
         {'name': 'empty', 'variant': 0, 'source': SOURCE.format(constructor='Empty')})
require = build.require


def read_json(path, limit=32 << 20):
    return json.loads(bounded_read(path, limit))


def one(rows, message):
    require(len(rows) == 1, message + ': ' + str(len(rows)))
    return rows[0]


def walk(value, path=()):
    yield list(path), value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, path + (key,))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk(child, path + (str(i),))


def is_payload(node):
    if not isinstance(node, dict) or node.get('tag') != 'application':
        return False
    left = node.get('function', {})
    return (node.get('argument') == {'tag': 'int64', 'value': 1} and
            left.get('tag') == 'application' and left.get('argument') == {'tag': 'int64', 'value': 20} and
            left.get('function') == {'tag': 'primitive', 'id': 8, 'name': 'addInt', 'arguments': []})


def structure(case, capture, plan, generated=None):
    p, m = plan['program'], plan['binding']['source_map']
    raw = capture['normalization']['raw_normalized']
    family = one(m['sum_map'], 'one nominal SUM mapping required')
    ctor = one(m['sum_constructor_map'], 'one constructor occurrence required')
    outer = one(m['sum_case_map'], 'one source case required')
    require(raw['tag'] == 'with_data' and len(family['variants']) == 2, 'nominal declarations absent')
    decl = raw['declarations'][family['declaration']]
    require(decl['tag'] == 'data_kind' and decl['parameters'] == [] and decl['name'] == family['name'] and
            [x['fields'] for x in decl['constructors']] == [[], [{'tag': 'applied', 'name': 'Int', 'arguments': []}]],
            'actual complete two-variant declaration differs')
    require(ctor['declaration'] == outer['declaration'] == family['declaration'] and
            ctor['variant'] == case['variant'], 'constructor/case nominal identity differs')
    require([v['constructor'] for v in family['variants']] == [v['name'] for v in decl['constructors']] and
            [v['variant'] for v in family['variants']] == ['V0', 'V1'], 'variant order differs')
    selected_name = decl['constructors'][case['variant']]['name']
    require(at(raw, ctor['head']['path']) == {'tag': 'constructor', 'name': selected_name, 'arguments': []},
            'actual constructor head identity differs')
    raw_case = at(raw, outer['source']['path'])
    require(raw_case['tag'] == 'case' and raw_case['result_type'] ==
            {'tag': 'constructor', 'name': 'Int', 'arguments': []}, 'case must return exact Int')
    require(len(raw_case['alternatives']) == len(outer['arms']) == 2, 'exhaustive source arms lost')
    factory = instruction(p, outer['factory'])
    require(factory['op'] == 'case_fields_i64' and list(factory['arms']) == ['V0', 'V1'] and
            factory['family'] == family['family'], 'declaration-order factory table differs')
    allocation = instruction(p, ctor['allocation'])
    require(allocation['op'] == ('construct_sum' if case['variant'] else 'construct_nullary') and
            allocation['family'] == family['family'] and allocation['variant'] == 'V'+str(case['variant']) and
            allocation['in'] == instruction(p, outer['allocation'])['in'] == 'root' and
            factory['in'] == '$home', 'SUM allocation/case unexpectedly split or changed')
    for arm in outer['arms']:
        alternative = raw_case['alternatives'][arm['index']]
        require(alternative['pattern']['constructor'] == arm['constructor'] ==
                decl['constructors'][arm['variant']]['name'] and
                at(raw, arm['source']['path']) == alternative['body'], 'arm source identity differs')
        expected = factory['arms']['V'+str(arm['variant'])]
        require(expected == {'code': arm['code'], 'captures': arm['captures']}, 'arm binding mapping differs')
        require(set(expected['captures']) == set(p['codes'][arm['code']]['captures']), 'capture set differs')
        fields = arm['field_captures']
        require(len(fields) == arm['variant'], 'nullary/one-field capture distinction lost')
        if fields:
            field, = fields
            require(field['index'] == 0 and field['binder'] == alternative['pattern']['fields'][0]['id'] and
                    expected['captures'][field['capture']] == {'kind': 'field', 'index': 0} and
                    p['types'][field['type']] == {'tag': 'closed', 'layout': '#i64'}, 'field source/position/type differs')
        sites = [x for x in m['allocation_map'] if x['instruction'] == outer['factory'] and x.get('arm') == arm['variant']]
        site = one(sites, 'one source allocation correspondence per arm')
        require(site['source'] == arm['source'] and site['role'] == 'case_fields_i64', 'arm Site source differs')
    body = p['codes'][outer['code']]['body']
    require(sum(x['op'] == 'force' for x in body) == 1 and
            not any(x['op'] in ('application', 'thunk', 'prim2', 'field') for x in body),
            'case eagerly constructs or evaluates an arm/payload')
    payload_path, _ = one([(path, n) for path,n in walk(raw) if is_payload(n)], 'one original addInt20 1 payload')
    payload_map = one([x for x in m['allocation_map'] if x['source']['path'] == payload_path and x['role'] == 'thunk'],
                      'pending payload source correspondence')
    payload = instruction(p, payload_map['instruction'])
    require(payload['op'] == 'thunk' and not any(x['op'] == 'force' for x in p['entry'][:-3]),
            'external payload became eager')
    selected_arm = one([x for x in outer['arms'] if x['variant'] == case['variant']], 'selected source arm')
    prefix = selected_arm['source']['path']
    int_use = one([x for x in m['use_map'] if x['source']['path'][:len(prefix)] == prefix and
                   [p['types'][t]['layout'] for t in x['arguments']] == ['#i64']], 'selected Int shared source use')
    call_path = int_use['source']['path'][:-1]
    require(int_use['source']['path'][-1] == 'function', 'shared Int use is not directly applied')
    source_call = at(raw, call_path); argument_path = call_path + ['argument']
    require(source_call['tag'] == 'application', 'shared Int source application absent')
    if case['variant']:
        payload_let = at(raw, payload_path[:-1])
        field_binder = selected_arm['field_captures'][0]['binder']
        argument = source_call['argument']
        require(payload_path[-1] == 'value' and payload_let['tag'] == 'let' and
                argument['tag'] == 'application' and argument['argument'] == {'tag':'var','name':payload_let['name']} and
                argument['function']['tag'] == 'application' and
                argument['function']['argument']['tag'] == 'var' and
                argument['function']['argument']['name']['id'] == field_binder and
                argument['function']['function'] == {'tag':'primitive','id':8,'name':'addInt','arguments':[]},
                'Number Int argument is not the exact n/payload alias addition')
    else:
        require(source_call['argument'] == {'tag':'int64','value':42}, 'Empty Int source argument differs')
    arg_map = one([x for x in m['allocation_map'] if x['source']['path'] == argument_path and
                   x['role'] == ('thunk' if case['variant'] else 'scalar')], 'Int argument source allocation')
    argument_op = instruction(p,arg_map['instruction'])
    if generated is not None:
        require(generated.count('= rt8_case_fields_i64(') == 1 and '= rt8_case_i64(' not in generated and
                generated.count(' = RT8_FACTORY_FIELD;') == 1, 'generated selected factory/field grammar differs')
    return {'family': family, 'constructor': allocation, 'outer': outer,
            'factory': factory, 'payload': payload, 'int_argument': argument_op}


def shared_graph(plan, verified):
    p, m = plan['program'], plan['binding']['source_map']
    scheme = one(m['scheme_map'], 'one shared Scheme')
    definition = one(verified['fragment']['definitions'], 'one real shared source definition')
    require(scheme['binder'] == definition['binding']['id'] and len(p['schemes']) == 1 and
            p['schemes'][scheme['scheme']]['parameters'] == 1, 'shared binder/full Scheme mismatch')
    vectors = [[p['types'][t]['layout'] for t in row['arguments']] for row in p['instantiations'].values()]
    require(vectors == [['#bool'], ['#i64']] and len(m['use_map']) == len(verified['fragment']['uses']) == 4,
            'full vectors or four checked source occurrences lost')
    generic, seal = instruction(p, scheme['generalize']), instruction(p, scheme['seal'])
    pending = one([x for x in generic['body'] if x['op'] == 'application'], 'one pending shared RHS')
    require(pending['out'] == seal['value'] and not any(x['op'] == 'force' for x in generic['body']),
            'shared RHS replaced or eager')
    closures = {x['out']: x['function'] for x in generic['body'] if x['op'] == 'closure'}
    return {'outer_code': closures[pending['function']], 'shared_code': closures[pending['argument']],
            'seal_owner': seal['value'], 'vectors': vectors}


def observe(case, evaluation, info, graph):
    e = evaluation
    require(e['fault'] == 0 and e['result'] == {'kind': 'i64', 'value': 42} and
            e['scalar_result_kind'] == 1 and e['scalar_result'] == 42 and e['events_omitted'] == 0,
            'actual native result or event completeness differs')
    metrics = e['metrics']
    require(metrics['entries_completed'] == 1 and metrics['groups_allocated'] == metrics['groups_closed'] and
            metrics['nodes_allocated'] == metrics['nodes_freed'], 'incomplete runtime cleanup')
    for role in ('owner', 'loan'):
        require(metrics[role+'_handle_acquisitions'] == metrics[role+'_handle_releases'], 'unbalanced '+role)
    require(set(e['memory_categories']) == {'context','groups','nodes','slots','handles','captures','pending'},
            'ledger categories differ')
    for row in [e['memory']] + list(e['memory_categories'].values()):
        require(row['live_bytes'] == row['live_blocks'] == 0 and row['allocated_bytes'] == row['freed_bytes'] and
                row['allocations'] == row['frees'], 'nonempty/unbalanced runtime ledger')
    events = e['events']
    selected = lambda name: [(i,x) for i,x in enumerate(events) if x['event'] == name]
    allocations = selected('allocate'); nodes = {x['node']:x for _,x in allocations}
    require(len(nodes) == len(allocations), 'allocation node identities repeated')
    ctor_i, ctor = one([(i,x) for i,x in allocations if x['out'] == info['constructor']['out']], 'actual SUM allocation')
    sum_i, value = one(selected('sum_value'), 'one actual SUM value')
    factory_i, factory = one(selected('case_fields_i64'), 'one selected factory')
    arm = one([x for x in info['outer']['arms'] if x['variant'] == case['variant']], 'selected source arm')
    other = one([x for x in info['outer']['arms'] if x['variant'] != case['variant']], 'unselected source arm')
    require(value['node'] == factory['scrutinee'] == ctor['node'] and
            value['variant_index'] == factory['variant_index'] == case['variant'] and
            value['family'] == factory['family'] == '%'+info['family']['family'] and
            value['variant'] == factory['variant'] == 'V'+str(case['variant']), 'actual family/variant identity differs')
    arm_i, allocated = one([(i,x) for i,x in allocations if x['opcode'] == 'case_fields_i64'], 'selected-only allocation')
    require(allocated['node'] == factory['result'] and allocated['code'] == factory['code'] == arm['code'] and
            allocated['slots'] == factory['captures'], 'actual selected thunk/source/captures differ')
    require(not any(x['code'] == other['code'] for _,x in allocations), 'unselected factory allocated')
    frames = selected('frame_enter')
    require(not any(x['context'].get('name') == other['code'] for _,x in frames), 'unselected factory entered')
    enter_i, _ = one([(i,x) for i,x in selected('callback_enter') if x['node'] == allocated['node']], 'selected callback once')
    require(ctor_i < sum_i < arm_i < factory_i < enter_i, 'selected allocation/entry order differs')
    payload_i, payload = one([(i,x) for i,x in allocations if x['out'] == info['payload']['out']], 'original external payload')
    require(payload['state'] == 'THUNK' and payload['code'] == info['payload']['code'] and payload_i < ctor_i,
            'original payload allocation replaced/eager')
    demands = [(i,x) for i,x in selected('update_pin') if x['node'] == payload['node']]
    memos = [(i,x) for i,x in selected('memo_publish') if x['destination'] == payload['node']]
    callbacks = [(i,x) for i,x in selected('callback_enter') if x['node'] == payload['node']]
    fields = selected('sum_field_capture')
    if case['variant']:
        field_i, field = one(fields, 'one selected scalar-field capture')
        fm, = arm['field_captures']
        require(ctor['slots'] == {'0': payload['node']} and field['node'] == payload['node'] and
                field['scrutinee'] == ctor['node'] and field['capture'] == fm['capture'] and
                field['field_index'] == 0 and factory['field_indices'] == {fm['capture']: 0} and
                factory['field_mask'] == 1, 'field did not capture original pending payload')
        aliases = [name for name,target in factory['captures'].items() if target == payload['node']]
        require(len(aliases) == 2 and fm['capture'] in aliases and
                sorted(arm['captures'][name]['kind'] for name in aliases) == ['external','field'],
                'field/external alias no longer shares original payload')
        demand_i, _ = one(demands, 'payload demanded once despite both aliases')
        memo_i, memo = one(memos, 'payload memoized once')
        callback_i, _ = one(callbacks, 'payload callback once')
        scalar = one([x for _,x in selected('scalar_value') if x['node'] == memo['result']], 'payload scalar result')
        require((scalar['kind'],scalar['value']) == ('i64',21) and
                field_i < arm_i < enter_i < demand_i < callback_i < memo_i, 'lazy payload timing/result differs')
    else:
        require(not ctor['slots'] and not factory['field_indices'] and factory['field_mask'] == 0 and
                not fields and not demands and not memos and not callbacks, 'Empty demanded unselected payload')
    # Separate lazy-argument-aware sharing oracle. Do not reuse the older helper
    # that assumes every sharedId actual argument already has a scalar event.
    begin = one(selected('generic_begin'), 'one generic introduction')
    seal = one(selected('generic_seal'), 'one actual seal')
    uses = selected('instantiate'); shared = seal[1]['node']
    require(begin[0] < seal[0] and len(uses) == 2 and len({x['use'] for _,x in uses}) == 2 and
            all(x['node'] == shared for _,x in uses), 'full views do not share one sealed node')
    pending = nodes[shared]
    require(pending['state'] == 'APPLICATION' and pending['out'] == graph['seal_owner'], 'shared pending RHS differs')
    outer, body = pending['slots']['$function'], pending['slots']['$argument']
    require(nodes[outer]['code'] == graph['outer_code'] and nodes[body]['code'] == graph['shared_code'] and
            sum(x['code'] == graph['shared_code'] for _,x in allocations) == 1, 'shared body cloned/substituted')
    rhs_memo_i, rhs_memo = one([(i,x) for i,x in selected('memo_publish') if x['destination'] == shared], 'RHS memo once')
    require(rhs_memo['result'] == body, 'RHS memo bypassed actual shared closure')
    calls = selected('invoke_enter')
    one([x for _,x in calls if x['closure'] == outer], 'RHS outer invocation once')
    actual = [(i,x) for i,x in calls if x['closure'] == body]
    require(len(actual) == 2 and rhs_memo_i < actual[0][0] < actual[1][0], 'Bool/Int shared demand order differs')
    scalars = {x['node']:(x['kind'],x['value']) for _,x in selected('scalar_value')}
    require(scalars.get(actual[0][1]['argument']) == ('bool',True), 'first shared demand not Bool true')
    int_call_i, int_call = actual[1]; argument = int_call['argument']
    require(nodes[argument]['out'] == info['int_argument']['out'], 'actual Int argument lost exact source allocation')
    deferred = case['variant'] == 1
    if deferred:
        require(nodes[argument]['state'] == 'THUNK' and nodes[argument]['code'] == info['int_argument']['code'],
                'Number Int argument was eagerly scalarized or changed source thunk')
        arg_demand_i, _ = one([(i,x) for i,x in selected('update_pin') if x['node'] == argument], 'lazy Int argument demand once')
        arg_memo_i, arg_memo = one([(i,x) for i,x in selected('memo_publish') if x['destination'] == argument], 'lazy Int argument memo once')
        require(int_call_i < arg_demand_i < arg_memo_i and scalars.get(arg_memo['result']) == ('i64',42),
                'deferred Int argument demand/result differs')
        _, argument_frame = one([(i,x) for i,x in frames if x['context'].get('node') == argument and
                                  x['context'].get('name') == info['int_argument']['code']],
                                 'source argument thunk frame')
        alias_forces = [(i,x) for i,x in selected('ir_force_result') if x['frame'] == argument_frame['frame']]
        require(len(alias_forces) == 2 and all(x['result'] == memos[0][1]['result'] for _,x in alias_forces) and
                memos[0][0] < alias_forces[0][0] < alias_forces[1][0] < arg_memo_i,
                'n and external payload alias did not both reuse the one memo result')
    else:
        require(scalars.get(argument) == ('i64',42), 'Empty Int argument not literal42')
    return {'variant':case['variant'], 'constructor_node':ctor['node'], 'selected_factory_node':allocated['node'],
            'selected_factory_code':arm['code'], 'unselected_factory_code':other['code'],
            'payload_node':payload['node'], 'payload_evaluations':len(demands), 'payload_memos':len(memos),
            'selected_factory_only':True, 'shared_node':shared, 'shared_body_node':body,
            'shared_rhs_evaluations':1, 'vectors':graph['vectors'], 'int_argument_deferred':deferred,
            'memory':e['memory'], 'memory_categories':e['memory_categories']}


def run_case(case, args, output, env):
    name = case['name']; inputs = output / (name+'-inputs'); inputs.mkdir()
    (inputs/'SharedPoly.emlf').write_text(SHARED, encoding='utf-8')
    entry = inputs/'main.emlf'; entry.write_text(case['source'], encoding='utf-8')
    target = output/name
    command = [sys.executable,'-B',str(BASE/'run_source_v8.py'),str(entry),'--module-root',str(inputs),
               '--ghc',args.ghc,'--cc',args.cc,'--output',str(target)]
    if args.data_groups:
        command.append('--data-groups')
    build.run(command, output, name, cwd=BASE, env=env, wall=1200, cpu=900, memory=16 << 30,
              termination_grace=15, stdout_limit=1 << 20, stderr_limit=1 << 20, file_limit=64 << 20)
    require(not bounded_read(output/(name+'.stderr'),1 << 20), 'successful CLI stderr')
    result = read_json(target/'result.json'); evaluation = read_json(target/'native/run.stdout')
    require(result['status'] == 'complete' and result['failure_policy'] == 'retain' and result['native'] == evaluation and
            'placement' not in result and evaluation['schema'] == 'resource-ir-v8-run/1', 'CLI result contract differs')
    capture = read_json(target/'capture.stdout'); verified = read_json(target/'verification.json')
    require(verified['fragment_admitted'] and verified['normalization_replay'] == 'all exact independent fields match' and
            capture['checked_type'] == {'tag':'constructor','name':'Int','arguments':[]}, 'fresh checking/replay differs')
    plan = read_json(target/'planned.json',8 << 20)
    require(plan['binding']['mode'] == ('data-groups-prototype' if args.data_groups else 'coarse-owned'), 'plan mode differs')
    info = structure(case,capture,plan,bounded_read(target/'native/ir8_runtime_generated.c',8 << 20).decode())
    graph = shared_graph(plan,verified); observation = observe(case,evaluation,info,graph)
    row = {'case':name,'status':'passed','data_groups':args.data_groups,
           'source_hashes':{'main.emlf':build.sha(case['source'].encode()),'SharedPoly.emlf':build.sha(SHARED.encode())},
           'observation':observation}
    build.save(target/'sum-observations.json',row)
    print(name+': PASS (fresh checked SUM, selected factory only, lazy payload, Int42, balanced ledger)',flush=True)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc',required=True)
    parser.add_argument('--cc',default='cc')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--data-groups',action='store_true',help='opt-in supporting groups; SUM placement remains coarse')
    args = parser.parse_args(); output = args.output.absolute()
    require(output.resolve() == output and output != BASE.parents[2] and BASE.parents[2] not in output.parents,
            'output must be canonical and outside this checkout')
    output.mkdir(parents=True,exist_ok=False); env = cli.environment(output)
    build.SUITE_DEADLINE = time.monotonic()+3600
    results = []
    try:
        for case in CASES:
            results.append(run_case(case,args,output,env))
    except BaseException as exc:
        try:
            build.save(output/'failure.json',{'error':type(exc).__name__+': '+str(exc),
                                              'completed_cases':[r['case'] for r in results]})
        except BaseException as persistence:
            exc.add_note('Failure persistence also failed: '+repr(persistence))
        raise
    build.save(output/'results.json',results)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
