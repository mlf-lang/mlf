#!/usr/bin/env python3
"""One fresh source program exercising a genuine monomorphic recursive knot.

Selectors come from the checked source and its current planner correspondence,
not historical resolver IDs. Copied-report controls are observer tests only.
The Stage11 ignored-tail fixture remains a separate regression: sumList consumes
both tails here. Low-fuel retained poison and explicit terminal surrender are
observed separately and are never relabelled successful evaluation.
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
from test_source_v8_recursive_sum import (one, walk, primitive, var, source_allocation,
    constructor_terms, shared_graph, SHARED, INT)

require = build.require
SOURCE = ('import SharedPoly\ndata IntList = Nil | Cons Int IntList;\n'
          'let rec sumList : IntList -> Int = \\xs -> case xs of { Nil -> 0; Cons x rest -> addInt x (sumList rest) } in\n'
          'let payload = addInt 20 1 in\n'
          'if sharedId true then sharedId (sumList (Cons payload (Cons payload Nil))) else 0\n')
CATEGORIES = {'context', 'groups', 'nodes', 'slots', 'handles', 'captures', 'pending'}


def read_json(path, limit=32 << 20):
    return json.loads(bounded_read(path, limit))


def structure(capture, plan, generated=None):
    p, mapping = plan['program'], plan['binding']['source_map']
    raw = capture['normalization']['raw_normalized']
    path, term = one([(path, node) for path, node in walk(raw) if
                     isinstance(node, dict) and node.get('tag') == 'letrec'], 'one actual recursive binding')
    binding = one(term['bindings'], 'singleton recursive group')
    rhs_path = path + ['bindings', '0', 'value']
    rhs = binding['value']; annotation = binding['type']
    knot = one(mapping['knot_map'], 'one exact knot correspondence')
    address = lambda path: {'stage': 'normalized', 'path': path}
    require(knot['source'] == address(path) and knot['binding_source'] == address(path+['bindings','0']) and
            knot['binder'] == binding['name'] and knot['rhs'] == address(rhs_path) and
            knot['body'] == address(path+['body']) and knot['type_scope'] is None,
            'recursive binder/source/type-scope correspondence differs')
    require(annotation['tag'] == 'arrow' and annotation['to'] == INT and rhs['tag'] == 'application' and
            rhs['function']['tag'] == rhs['argument']['tag'] == 'lambda', 'actual typed recursive RHS spine differs')
    wrapper, function = rhs['function'], rhs['argument']
    require(wrapper['parameter_type'] == annotation and var(wrapper['body'], wrapper['parameter']) and
            function['parameter_type'] == annotation['from'], 'ordinary RHS passthrough wrapper differs')
    function_path = rhs_path+['argument']
    arg_let = function['body']; arg_path = function_path+['body']
    require(arg_let['tag'] == 'let' and arg_let['value']['tag'] == 'application' and
            var(arg_let['value']['argument'], function['parameter']), 'ordinary argument wrapper removed')
    coercion = arg_let['value']['function']
    require(coercion['tag'] == 'lambda' and coercion['parameter_type'] == annotation['from'] and
            var(coercion['body'], coercion['parameter']), 'ordinary argument passthrough differs')
    case_path = arg_path+['body']; case = at(raw, case_path)
    require(case['tag'] == 'case' and var(case['scrutinee'], arg_let['name']) and case['result_type'] == INT,
            'actual recursive case/source argument differs')
    family = one(mapping['sum_map'], 'one exact IntList family')
    declaration = raw['declarations'][family['declaration']]
    require(annotation['from'] == {'tag':'constructor','name':declaration['name'],'arguments':[]} and
            family['name'] == declaration['name'] and not declaration['parameters'], 'recursive nominal annotation differs')
    fields = [[], [{'tag':'applied','name':'Int','arguments':[]},
                   {'tag':'applied','name':declaration['name'],'arguments':[]}]]
    require([row['fields'] for row in declaration['constructors']] == fields and
            len(family['variants']) == 2, 'recursive nominal constructors differ')
    physical = '%'+family['family']
    require(p['families'][family['family']] == {'variants':['V0','V1'],
            'fields':{'V0':[],'V1':['#i64',physical]}}, 'recursive family physical edges differ')
    for index, variant in enumerate(family['variants']):
        require(variant['index'] == index and variant['variant'] == 'V'+str(index) and
                variant['constructor'] == declaration['constructors'][index]['name'], 'nominal variant/source identity differs')
    case_map = one(mapping['sum_case_map'], 'one static recursive case')
    require(case_map['source'] == address(case_path) and case_map['family'] == family['family'] and
            case_map['declaration'] == family['declaration'] and len(case_map['arms']) == 2,
            'static recursive case/family correspondence differs')
    arms = {}
    factory = instruction(p, case_map['factory'])
    require(factory['op'] == 'case_fields_i64' and set(factory['arms']) == {'V0','V1'}, 'exhaustive factory differs')
    for arm in case_map['arms']:
        source = case['alternatives'][arm['index']]
        require(arm['source'] == address(case_path+['alternatives',str(arm['index']),'body']) and
                arm['pattern_source'] == address(case_path+['alternatives',str(arm['index']),'pattern']) and
                arm['constructor'] == source['pattern']['constructor'] == declaration['constructors'][arm['variant']]['name'],
                'source arm/variant association differs')
        require(factory['arms']['V'+str(arm['variant'])] == {'code':arm['code'],'captures':arm['captures']},
                'selected factory registered Code differs')
        expected = source['pattern']['fields']
        require(len(expected) == len(arm['field_captures']), 'complete recursive field inventory differs')
        for index, (field, binder) in enumerate(zip(arm['field_captures'], expected)):
            require(field['index'] == index and field['binder'] == binder['id'] and field['relation'] == 'down' and
                    arm['captures'][field['capture']] == {'kind':'field','index':index}, 'recursive field source/index differs')
        arms[arm['variant']] = arm
    require(set(arms) == {0,1} and at(raw, arms[0]['source']['path']) == {'tag':'int64','value':0}, 'Nil source result differs')
    self_path, self_app = one([(path, node) for path, node in walk(rhs, rhs_path) if isinstance(node,dict) and
        node.get('tag') == 'application' and var(node['function'], binding['name'])], 'one lexical recursive self application')
    cons_fields = case['alternatives'][arms[1]['index']]['pattern']['fields']
    require(var(self_app['argument'], cons_fields[1]), 'self recursion does not use exact tail binder')
    addition_path = arms[1]['source']['path']; addition = at(raw, addition_path)
    require(addition['tag'] == addition['function']['tag'] == 'application' and
            addition['function']['function']['tag'] == 'primitive' and
            addition['function']['function']['name'] == 'addInt' and
            var(addition['function']['argument'], cons_fields[0]) and addition['argument'] == self_app,
            'recursive source must add the selected head and recursive tail result')
    payload_path, _ = one([(path,node) for path,node in walk(term['body'],path+['body']) if primitive(node,20,1)],
                          'one shared pending21 source')
    payload_let = at(raw, payload_path[:-1])
    require(payload_let['tag'] == 'let' and payload_path[-1] == 'value', 'payload lexical binding differs')
    constructors = []
    require(len(mapping['sum_constructor_map']) == 3, 'three lexical list constructors')
    for row in mapping['sum_constructor_map']:
        head, args = constructor_terms(raw,row)
        require(row['declaration'] == family['declaration'] and
                head['name'] == declaration['constructors'][row['variant']]['name'], 'constructor nominal identity differs')
        op = source_allocation(plan,row['source']['path'],'construct_sum' if args else 'construct_nullary')
        require(op == instruction(p,row['allocation']), 'constructor allocation join differs')
        constructors.append((row,args,op))
    nil = one([row for row in constructors if row[0]['variant'] == 0], 'one lexical Nil')
    cons = [row for row in constructors if row[0]['variant'] == 1]
    require(len(cons) == 2 and all(len(row[1]) == 2 and var(row[1][0][1],payload_let['name']) for row in cons),
            'both lexical Cons heads must use one payload binding')
    inner = one([row for row in cons if row[1][1][0] == nil[0]['source']['path']], 'inner Cons tail is exact Nil')
    outer = one([row for row in cons if row[1][1][0] == inner[0]['source']['path']], 'outer Cons tail is exact inner Cons')
    int_use = one([row for row in mapping['use_map'] if [p['types'][t].get('layout') for t in row['arguments']] == ['#i64']],
                  'one full sharedId Int view')
    call_path = int_use['source']['path'][:-1]
    require(int_use['source']['path'][-1] == 'function', 'sharedId Int use source differs')
    int_path = call_path+['argument']; int_app = at(raw,int_path)
    require(int_app['tag'] == 'application' and var(int_app['function'],binding['name']) and
            int_path+['argument'] == outer[0]['source']['path'], 'sharedId Int argument is not actual recursive application')

    hole = instruction(p,knot['hole']); fill = instruction(p,knot['fill'])
    require(hole == {'op':'hole','out':knot['hole_owner'],'in':knot['home'],'layout':'^'+knot['logical_type']} and
            instruction(p,knot['retain_self']) == {'op':'retain','out':knot['self_owner'],'value':knot['hole_owner']} and
            fill == {'op':'fill','hole':knot['hole_owner'],'value':knot['rhs_owner']}, 'original hole ticket/Fill ownership differs')
    for field, value in (('drop_rhs',knot['rhs_owner']),('drop_self',knot['self_owner']),('drop_hole',knot['hole_owner'])):
        require(instruction(p,knot[field]) == {'op':'drop','value':value}, 'knot release differs')
    ordered = [knot[key] for key in ('hole','retain_self','fill','drop_rhs','drop_self','drop_hole')]
    require(all(item['root'] == 'entry' and item['name'] is None and len(item['segments']) == 1 for item in ordered) and
            [item['segments'][0] for item in ordered] == sorted({item['segments'][0] for item in ordered}),
            'knot operations must preserve one concrete ordered entry')
    closure = source_allocation(plan,function_path,'closure')
    rhs_op = source_allocation(plan,rhs_path,'application')
    wrapper_op = source_allocation(plan,rhs_path+['function'],'closure')
    require(rhs_op['out'] == knot['rhs_owner'] and rhs_op['function'] == wrapper_op['out'] and
            rhs_op['argument'] == closure['out'], 'filled RHS root bypassed ordinary wrapper')
    carrier = one([row for row in mapping['carrier_map'] if row['source'] == address(function_path)], 'recursive lambda carrier')
    capture = one([row for row in carrier['mono_captures'] if row['binder'] == binding['name']['id']], 'exact recursive self capture')
    require(carrier['kind'] == 'lambda' and carrier['ir_code'] == closure['function'] and carrier['type_scope'] is None and
            carrier['view_captures'] == [] and len(carrier['mono_captures']) == 1 and
            capture['layout'] == '^'+knot['logical_type'] and capture['relation'] == 'down' and
            closure['captures'] == {capture['capture']:knot['self_owner']}, 'recursive closure self contract differs')
    metadata = json.loads(check_metadata(p).metadata_json)
    code = one([row for row in metadata['codes'] if row['kind'] == 'function' and row['name'] == closure['function']],
               'one registered real recursive Code')
    if generated is not None:
        definitions = [int(x) for x in re.findall(r'static Rt8Handle \*rt8_body_(\d+)\(',generated)]
        bindings = [(int(a),int(b)) for a,b in re.findall(r'\{ \.code_id = (\d+), \.body = rt8_body_(\d+) \}',generated)]
        require(definitions == list(range(len(metadata['codes']))) and bindings == [(i,i) for i in definitions],
                'generated one-body/registered Code census differs')
        require(generated.count('rt8_fill(ctx,') == 1 and generated.count(' = rt8_hole(ctx,') == 1,
                'generated knot hole/Fill census differs')
    return {'hole':hole,'fill':fill,'rhs':rhs_op,'closure':closure,'wrapper':wrapper_op,
            'self_capture':capture['capture'],'code':closure['function'],'code_id':code['id'],
            'family':physical,'arms':arms,'payload':source_allocation(plan,payload_path,'thunk'),
            'nil':nil[2],'inner':inner[2],'outer':outer[2],
            'addition':source_allocation(plan,addition_path,'thunk'),
            'recursive_call':source_allocation(plan,self_path,'application'),
            'argument_wrapper':source_allocation(plan,arg_path+['value','function'],'closure'),
            'int_argument':source_allocation(plan,int_path,'application')}


def ledger(evaluation, completed):
    metrics = evaluation['metrics']
    require(set(evaluation['memory_categories']) == CATEGORIES, 'seven ledger categories required')
    for row in [evaluation['memory'], *evaluation['memory_categories'].values()]:
        require(row['allocated_bytes'] - row['freed_bytes'] == row['live_bytes'] and
                row['allocations'] - row['frees'] == row['live_blocks'], 'ledger arithmetic differs')
        if completed:
            require(row['live_bytes'] == row['live_blocks'] == 0, 'successful live ledger remains')
    for key in ('allocated_bytes', 'freed_bytes', 'live_bytes', 'allocations', 'frees', 'live_blocks'):
        require(evaluation['memory'][key] == sum(row[key] for row in evaluation['memory_categories'].values()),
                'ledger categories do not sum')
    if completed:
        require(metrics['entries_completed'] == 1 and metrics['groups_allocated'] == metrics['groups_closed'] and
                metrics['nodes_allocated'] == metrics['nodes_freed'], 'entry or graph cleanup incomplete')
        for role in ('owner', 'loan'):
            require(metrics[role+'_handle_acquisitions'] == metrics[role+'_handle_releases'], 'handle balance differs')
        for role in ('owner', 'builder', 'pin', 'key', 'slot', 'sum'):
            require(metrics['rc_inc_'+role] == metrics['rc_dec_'+role], 'RC balance differs')


def observe(evaluation, info, graph):
    e = evaluation
    require(e['schema'] == 'resource-ir-v8-run/1' and e['state'] == e['fault'] == 0 and
            e['result'] == {'kind': 'i64', 'value': 42} and e['scalar_result_kind'] == 1 and
            e['scalar_result'] == 42 and e['events_omitted'] == 0 and
            e['events_emitted'] == len(e['events']), 'complete native Int42 report required')
    require(e['guards_failed_mask'] == 0 and 0 < e['guard_work_used'] <= e['guard_work_limit'],
            'native guards failed or work invalid')
    ledger(e, True)
    events = e['events']
    selected = lambda name: [(i, x) for i, x in enumerate(events) if x['event'] == name]
    allocations = selected('allocate')
    nodes = {x['node']: x for _, x in allocations}
    require(len(nodes) == len(allocations), 'duplicate allocated node identity')

    def allocation(op, label):
        row = one([(i, x) for i, x in allocations if x['out'] == op['out']], label+' allocation once')
        require(row[1]['opcode'] == op['op'] and
                row[1]['code'] == (op['function'] if op['op'] == 'closure' else op.get('code')),
                label+' source opcode/Code differs')
        return row

    hole_i, hole = allocation(info['hole'], 'recursive hole')
    closure_i, closure = allocation(info['closure'], 'recursive closure')
    wrapper_i, wrapper = allocation(info['wrapper'], 'RHS wrapper closure')
    rhs_i, rhs = allocation(info['rhs'], 'pending recursive RHS')
    fill_i, fill = one(selected('fill'), 'one actual recursive Fill')
    require(hole['state'] == 'HOLE' and closure['state'] == wrapper['state'] == 'CLOSURE' and
            rhs['state'] == 'APPLICATION' and hole_i < closure_i < rhs_i < fill_i and wrapper_i < rhs_i,
            'recursive allocation/Fill order differs')
    require(fill['hole'] == hole['node'] and fill['target'] == rhs['node'] and
            fill['hole_variable'] == info['fill']['hole'] and fill['value_variable'] == info['fill']['value'],
            'Fill target or original knot variables substituted')
    require(closure['slots'][info['self_capture']] == hole['node'] and
            rhs['slots'] == {'$function': wrapper['node'], '$argument': closure['node']},
            'self slot or preserved RHS wrapper graph substituted')
    fill_slot_i, _ = one([(i, x) for i, x in selected('slot_install') if
                         x['host'] == hole['node'] and x['field'] == '$target' and x['target'] == rhs['node']],
                        'one exact hole target edge')
    require(rhs_i < fill_slot_i < fill_i, 'Fill publication order differs')
    require(not any(i < fill_i and x['node'] in (hole['node'], rhs['node'])
                    for i, x in selected('update_pin')), 'recursive knot demanded before Fill')
    rhs_memo_i, rhs_memo = one([(i, x) for i, x in selected('memo_publish') if x['destination'] == rhs['node']],
                             'recursive RHS memo once')
    require(fill_i < rhs_memo_i and rhs_memo['result'] == closure['node'], 'RHS memo lost recursive closure')
    wrapper_call_i, wrapper_call = one([(i, x) for i, x in selected('invoke_enter') if x['closure'] == wrapper['node']],
                                      'RHS wrapper called once')
    require(fill_i < wrapper_call_i < rhs_memo_i and wrapper_call['argument'] == closure['node'],
            'ordinary RHS wrapper was erased or substituted')

    payload_i, payload = allocation(info['payload'], 'shared pending21')
    nil_i, nil = allocation(info['nil'], 'Nil')
    inner_i, inner = allocation(info['inner'], 'inner Cons')
    outer_i, outer = allocation(info['outer'], 'outer Cons')
    require(payload['state'] == 'THUNK' and payload_i < nil_i < inner_i < outer_i and not nil['slots'] and
            inner['slots'] == {'0': payload['node'], '1': nil['node']} and
            outer['slots'] == {'0': payload['node'], '1': inner['node']}, 'list graph or shared head identity differs')
    constructors = (outer, inner, nil)
    sum_values = selected('sum_value')
    require(len(sum_values) == 3, 'extra/missing lexical list constructor')
    for node, variant in zip(constructors, (1, 1, 0)):
        _, value = one([(i, x) for i, x in sum_values if x['node'] == node['node']], 'one constructor value')
        require(value['family'] == info['family'] and value['variant_index'] == variant and
                value['variant'] == 'V'+str(variant) and node['layout'] == info['family'], 'list nominal identity differs')

    calls = [(i, x) for i, x in selected('invoke_enter') if x['closure'] == closure['node']]
    frames = [(i, x) for i, x in selected('frame_enter') if x['context'].get('name') == info['code']]
    require(len(calls) == len(frames) == 3 and [x['argument'] for _, x in calls] == [n['node'] for n in constructors]
            and rhs_memo_i < calls[0][0], 'same recursive closure must traverse Cons/Cons/Nil')
    require(sum(x['code'] == info['code'] for _, x in allocations) == 1 and
            len({x['frame'] for _, x in frames}) == 3 and all(x['context']['node'] == closure['node'] and
            x['context']['kind'] == 'function' for _, x in frames), 'recursive closure/Code cloned or callback substituted')
    self_apps = [x for _,x in allocations if x['out'] == info['recursive_call']['out']]
    require(len(self_apps) == 2 and len({x['node'] for x in self_apps}) == 2 and
            all(x['opcode'] == 'application' and x['state'] == 'APPLICATION' for x in self_apps) and
            [x['slots'] for x in self_apps] == [{'$function':hole['node'],'$argument':n['node']} for n in (inner,nil)],
            'recursive applications bypassed self hole or exact tails')
    argument_wrappers = [x for _,x in allocations if x['out'] == info['argument_wrapper']['out']]
    require(len(argument_wrappers) == 3 and all(x['code'] == info['argument_wrapper']['function'] for x in argument_wrappers),
            'ordinary recursive argument wrappers removed or substituted')
    for wrapper_node, argument_node in zip(argument_wrappers,constructors):
        _, call = one([(i,x) for i,x in selected('invoke_enter') if x['closure'] == wrapper_node['node']],
                      'ordinary argument wrapper called once per activation')
        require(call['argument'] == argument_node['node'], 'ordinary argument wrapper received wrong source value')
    for (call_i, _), (frame_i, _) in zip(calls, frames):
        require(call_i < frame_i, 'recursive callback preceded invocation')
    factories = selected('case_fields_i64')
    require(len(factories) == 3 and [x['scrutinee'] for _, x in factories] == [n['node'] for n in constructors] and
            [x['variant_index'] for _, x in factories] == [1, 1, 0], 'recursive case transitions differ')
    factory_nodes = []
    heads = []
    field_events = selected('sum_field_capture')
    require(len(field_events) == 4, 'recursive selected field capture census differs')
    for position, ((factory_i, event), node, variant) in enumerate(zip(factories, constructors, (1, 1, 0))):
        arm = info['arms'][variant]
        require(event['family'] == info['family'] and event['variant'] == 'V'+str(variant) and
                event['code'] == arm['code'] and calls[position][0] < factory_i,
                'selected recursive factory/Code differs')
        allocated_i, allocated = one([(i, x) for i, x in allocations if x['node'] == event['result']],
                                    'one selected activation thunk')
        callback_i, _ = one([(i, x) for i, x in selected('callback_enter') if x['node'] == allocated['node']],
                           'selected activation callback once')
        require(allocated['opcode'] == 'case_fields_i64' and allocated['code'] == arm['code'] and
                allocated['slots'] == event['captures'] and allocated_i < factory_i < callback_i,
                'selected factory allocation/entry differs')
        mask = {f['capture']: f['index'] for f in arm['field_captures']}
        require(event['field_indices'] == mask and event['field_mask'] == sum(1 << i for i in mask.values()),
                'selected exact field mask differs')
        for field in arm['field_captures']:
            field_i, acquired = one([(i, x) for i, x in field_events if
                x['scrutinee'] == node['node'] and x['capture'] == field['capture']], 'one selected source field')
            target = node['slots'][str(field['index'])]
            require(acquired['node'] == event['captures'][field['capture']] == target and
                    acquired['field_index'] == field['index'] and acquired['family'] == info['family'] and
                    acquired['variant_index'] == variant and acquired['variant'] == 'V'+str(variant) and
                    acquired['layout'] == ('#i64' if field['index'] == 0 else info['family']) and
                    field_i < allocated_i, 'selected original field edge/type substituted')
            if field['index'] == 0:
                heads.append(field_i)
        factory_nodes.append(allocated['node'])
    require(len(set(factory_nodes)) == 3 and sum(x['opcode'] == 'case_fields_i64' for _, x in allocations) == 3,
            'repeated activation reused a thunk or allocated an extra factory')

    demand_i, _ = one([(i, x) for i, x in selected('update_pin') if x['node'] == payload['node']], 'shared21 demand once')
    callback_i, _ = one([(i, x) for i, x in selected('callback_enter') if x['node'] == payload['node']], 'shared21 callback once')
    memo_i, memo = one([(i, x) for i, x in selected('memo_publish') if x['destination'] == payload['node']], 'shared21 memo once')
    scalars = {x['node']: (x['kind'], x['value']) for _, x in selected('scalar_value')}
    require(heads[0] < demand_i < callback_i < memo_i and scalars.get(memo['result']) == ('i64', 21),
            'shared21 lazy evaluation differs')
    # Recursion may capture the second head after the first head already memoized.
    # It still has to force the same original node and obtain its same scalar.
    additions = [(i, x) for i, x in allocations if x['out'] == info['addition']['out']]
    require(len(additions) == 2 and len({x['node'] for _, x in additions}) == 2,
            'two recursive activations require distinct addition thunks')
    added_results = []
    for _, addition in additions:
        require(addition['code'] == info['addition']['code'] and addition['opcode'] == 'thunk', 'recursive addition Code differs')
        _, frame = one([(i, x) for i, x in selected('frame_enter') if x['context'].get('node') == addition['node'] and
                       x['context'].get('name') == addition['code']], 'recursive addition callback once')
        forces = [(i, x) for i, x in selected('ir_force_result') if x['frame'] == frame['frame']]
        added_i, added = one([(i, x) for i, x in selected('memo_publish') if x['destination'] == addition['node']],
                            'recursive addition memo once')
        require(len(forces) == 2 and forces[0][1]['result'] == memo['result'] and
                memo_i < forces[0][0] < forces[1][0] < added_i, 'recursive head did not reuse one21 memo')
        added_results.append(scalars.get(added['result']))
    require(added_results == [('i64', 42), ('i64', 21)], 'recursive unwind results differ')

    begin = one(selected('generic_begin'), 'one shared introduction')
    seal = one(selected('generic_seal'), 'one shared seal')
    uses = selected('instantiate'); shared = seal[1]['node']
    require(begin[0] < seal[0] and sorted(x['use'] for _, x in uses) == list(range(len(graph['uses']))) and
            all(x['node'] == shared for _, x in uses), 'full sharedId views lost common node')
    pending = nodes[shared]
    require(pending['state'] == 'APPLICATION' and pending['out'] == graph['seal_owner'], 'sharedId RHS became eager')
    outer_fn, body = pending['slots']['$function'], pending['slots']['$argument']
    require(nodes[outer_fn]['code'] == graph['outer_code'] and nodes[body]['code'] == graph['shared_code'] and
            sum(x['code'] == graph['shared_code'] for _, x in allocations) == 1, 'sharedId callable cloned')
    shared_memo_i, shared_memo = one([(i, x) for i, x in selected('memo_publish') if x['destination'] == shared],
                                   'sharedId RHS memo once')
    require(shared_memo['result'] == body, 'sharedId RHS memo target differs')
    one([x for _, x in selected('invoke_enter') if x['closure'] == outer_fn], 'sharedId outer call once')
    shared_calls = [(i, x) for i, x in selected('invoke_enter') if x['closure'] == body]
    _, int_arg = allocation(info['int_argument'], 'pending sumList application')
    require(len(shared_calls) == 2 and shared_memo_i < shared_calls[0][0] < shared_calls[1][0] and
            scalars.get(shared_calls[0][1]['argument']) == ('bool', True) and
            shared_calls[1][1]['argument'] == int_arg['node'] and int_arg['state'] == 'APPLICATION' and
            int_arg['slots'] == {'$function':hole['node'],'$argument':outer['node']},
            'same sharedId Bool/Int calls or pending recursive argument differ')
    arg_demand_i, _ = one([(i, x) for i, x in selected('update_pin') if x['node'] == int_arg['node']], 'recursive result demand once')
    arg_memo_i, arg_memo = one([(i, x) for i, x in selected('memo_publish') if x['destination'] == int_arg['node']],
                             'recursive result memo once')
    require(shared_calls[1][0] < arg_demand_i < arg_memo_i and scalars.get(arg_memo['result']) == ('i64', 42),
            'sharedId recursive argument was forced before call or lost42')
    return {'hole': hole['node'], 'fill_target': rhs['node'], 'recursive_closure': closure['node'],
            'recursive_code': info['code'], 'registered_code_id': info['code_id'], 'recursive_calls': 3, 'arguments': [n['node'] for n in constructors],
            'selected_variants': [1, 1, 0], 'factory_nodes': factory_nodes, 'shared_head': payload['node'],
            'shared_head_evaluations': 1, 'shared_head_memos': 1, 'head_scalar': memo['result'],
            'sharedId_node': shared, 'sharedId_body': body, 'sharedId_vectors': graph['vectors'],
            'memory': e['memory'], 'memory_categories': e['memory_categories']}


def observe_fault_pair(retained, terminal, fuel, info):
    require(type(fuel) is int and fuel > 0, 'explicit positive fault fuel required')
    require(retained['schema'] == 'resource-ir-v8-run/1' and retained['fault'] == 4 and retained['state'] == 1 and
            retained['metrics']['entries_completed'] == 0 and retained['metrics']['steps'] == fuel + 1 and
            retained['memory']['live_bytes'] > 0 and retained['memory']['live_blocks'] > 0,
            'low fuel must remain a genuine retained fault')
    ledger(retained, False)
    require(terminal['schema'] == 'resource-ir-v8-terminal-run/1' and terminal['evaluation'] == retained,
            'terminal surrender changed the original evaluation fault')
    destruction = terminal['destruction']
    require(destruction['status'] == 1 and destruction['totals_overflow'] is False and
            destruction['retired_bytes'] == retained['memory']['live_bytes'] and
            destruction['retired_blocks'] == retained['memory']['live_blocks'], 'terminal retirement totals differ')
    require(set(destruction['categories']) == CATEGORIES, 'terminal category census differs')
    for name, row in retained['memory_categories'].items():
        require(destruction['categories'][name] == {'bytes': row['live_bytes'], 'blocks': row['live_blocks']},
                'terminal category retirement differs')
    require(retained['events_omitted'] == 0 and retained['events_emitted'] == len(retained['events']),
            'fault coverage needs complete retained events')
    fills = [x for x in retained['events'] if x['event'] == 'fill']
    require(len(fills) <= 1, 'fault report contains extra Fill')
    live_cycle = False
    if fills:
        allocations = [x for x in retained['events'] if x['event'] == 'allocate']
        get = lambda op: one([x for x in allocations if x['out'] == op['out']], 'fault knot allocation')
        hole, rhs, closure, wrapper = (get(info[key]) for key in ('hole','rhs','closure','wrapper'))
        require(fills[0]['hole'] == hole['node'] and fills[0]['target'] == rhs['node'] and
                closure['code'] == info['code'] and closure['slots'][info['self_capture']] == hole['node'] and
                rhs['slots'] == {'$function':wrapper['node'],'$argument':closure['node']} and
                hole['group'] == rhs['group'] == closure['group'], 'fault Fill did not form the same recursive cycle')
        live_cycle = not any(x['event'] == 'close_group' and x['group'] == hole['group'] for x in retained['events'])
    return {'fuel': fuel, 'fault': 4, 'evaluation_retained_live_bytes': retained['memory']['live_bytes'],
            'retired_bytes': destruction['retired_bytes'], 'after_fill': len(fills) == 1,
            'live_recursive_cycle_at_fault': live_cycle,
            'recursive_internal_cycle_retirement_claimed': live_cycle}



def fault_controls(retained, terminal, fuel, info):
    """Copied evidence must not claim a filled knot is still live after close."""
    baseline=observe_fault_pair(retained,terminal,fuel,info)
    require(baseline['after_fill'] and baseline['live_recursive_cycle_at_fault'],
            'fault closure control needs actual filled/live baseline')
    changed=copy.deepcopy(retained)
    hole=one([x for x in changed['events'] if x['event']=='allocate' and x['out']==info['hole']['out']],
             'fault closure control knot group')
    changed['events'].append({'event':'close_group','group':hole['group']})
    changed['events_emitted']=len(changed['events'])
    changed_terminal=copy.deepcopy(terminal);changed_terminal['evaluation']=changed
    result=observe_fault_pair(changed,changed_terminal,fuel,info)
    require(result['after_fill'] and not result['live_recursive_cycle_at_fault'] and
            not result['recursive_internal_cycle_retirement_claimed'],
            'copied close_group incorrectly retained live-cycle claim')
    return [{'control':'closed-knot-group-not-live','status':'claim-rejected','event':'close_group'}]


def copied_controls(capture, plan, evaluation, generated):
    """Mutate copies of an actual report/plan; these are not native fault runs."""
    info = structure(capture, plan, generated)
    p, mapping = plan['program'], plan['binding']['source_map']
    scheme = one(mapping['scheme_map'], 'one shared Scheme for controls')
    generic, seal = instruction(p, scheme['generalize']), instruction(p, scheme['seal'])
    pending = one([x for x in generic['body'] if x['op'] == 'application'], 'shared RHS for controls')
    closures = {x['out']: x['function'] for x in generic['body'] if x['op'] == 'closure'}
    graph = {'outer_code': closures[pending['function']], 'shared_code': closures[pending['argument']],
             'seal_owner': seal['value'], 'uses': sorted(p['instantiations']),
             'vectors': [[p['types'][t]['layout'] for t in row['arguments']] for row in p['instantiations'].values()]}
    observe(evaluation, info, graph)
    results = []

    def event(report, kind, predicate=lambda row: True):
        return one([x for x in report['events'] if x['event'] == kind and predicate(x)], 'control exact event')

    def allocation(report, op):
        return event(report, 'allocate', lambda x: x['out'] == op['out'])

    def reject(name, mutation, expected):
        changed = copy.deepcopy(evaluation)
        mutation(changed)
        changed['events_emitted'] = len(changed['events'])
        try:
            observe(changed, info, graph)
        except AssertionError as exc:
            require(expected in str(exc), name+' rejected at unrelated guard: '+str(exc))
            results.append({'control': name, 'status': 'rejected', 'guard': expected})
        else:
            raise AssertionError(name+' copied report unexpectedly accepted')

    reject('fill-target-substitution', lambda r: event(r,'fill').__setitem__('target',-1),
           'Fill target or original knot variables substituted')
    reject('fill-ticket-substitution', lambda r: event(r,'fill').__setitem__('hole_variable','not-the-original-ticket'),
           'Fill target or original knot variables substituted')
    reject('self-slot-substitution', lambda r: allocation(r,info['closure'])['slots'].__setitem__(info['self_capture'],-1),
           'self slot or preserved RHS wrapper graph substituted')
    reject('recursive-code-substitution', lambda r: allocation(r,info['closure']).__setitem__('code','wrong-code'),
           'recursive closure source opcode/Code differs')
    reject('callback-node-substitution', lambda r: next(x for x in r['events'] if x['event']=='frame_enter' and
           x['context'].get('name')==info['code'])['context'].__setitem__('node',-1),
           'recursive closure/Code cloned or callback substituted')
    reject('recursive-tail-substitution', lambda r: next(x for x in r['events'] if x['event']=='allocate' and
           x['out']==info['recursive_call']['out'])['slots'].__setitem__('$argument',-1),
           'recursive applications bypassed self hole or exact tails')
    reject('wrong-case-transition', lambda r: next(x for x in r['events'] if x['event']=='case_fields_i64').__setitem__('variant_index',0),
           'recursive case transitions differ')
    reject('field-edge-substitution', lambda r: next(x for x in r['events'] if x['event']=='sum_field_capture').__setitem__('node',-1),
           'selected original field edge/type substituted')
    reject('head-alias-substitution', lambda r: allocation(r,info['inner'])['slots'].__setitem__('0',-1),
           'list graph or shared head identity differs')

    def duplicate(report, kind):
        node = allocation(report, info['payload'])['node']
        key = 'destination' if kind == 'memo_publish' else 'node'
        report['events'].append(copy.deepcopy(event(report,kind,lambda x:x[key]==node)))
    reject('extra-shared-payload-callback', lambda r:duplicate(r,'callback_enter'), 'shared21 callback once')
    reject('extra-shared-payload-memo', lambda r:duplicate(r,'memo_publish'), 'shared21 memo once')

    def early_demand(report):
        arg = allocation(report, info['int_argument'])['node']
        demand = event(report,'update_pin',lambda x:x['node']==arg)
        report['events'].remove(demand)
        report['events'].insert(0,demand)
    reject('premature-sharedId-recursive-argument',early_demand,
           'sharedId recursive argument was forced before call or lost42')
    reject('split-sharedId-view',lambda r:next(x for x in r['events'] if x['event']=='instantiate').__setitem__('node',-1),
           'full sharedId views lost common node')
    reject('nonzero-pending-ledger',lambda r:r['memory_categories']['pending'].__setitem__('live_blocks',1),
           'ledger arithmetic differs')

    altered = copy.deepcopy(plan)
    instruction(altered['program'], altered['binding']['source_map']['knot_map'][0]['fill'])['value'] = 'other-owner'
    try:
        structure(capture, altered, generated)
    except AssertionError as exc:
        require('original hole ticket/Fill ownership differs' in str(exc), 'bad Fill rejected at unrelated source guard')
        results.append({'control':'wrong-plan-fill','status':'rejected','guard':'original hole ticket/Fill ownership differs'})
    else:
        raise AssertionError('wrong copied plan Fill accepted')
    changed_c = generated.replace('.code_id = '+str(info['code_id'])+', .body = rt8_body_'+str(info['code_id']),
                                  '.code_id = '+str(info['code_id'])+', .body = rt8_body_999999',1)
    require(changed_c != generated,'exact generated registration control not found')
    try:
        structure(capture,plan,changed_c)
    except AssertionError as exc:
        require('generated one-body/registered Code census differs' in str(exc),'bad callback rejected at unrelated source guard')
        results.append({'control':'wrong-generated-callback','status':'rejected','guard':'generated one-body/registered Code census differs'})
    else:
        raise AssertionError('wrong generated callback accepted')
    return results



# Chosen once from the healthy emitted coarse entry, before any fault run.
FAULT_FUEL = 15
FAULT_REASON = ('The emitted entry consumes 7 ticks through the shared generic RHS; seal and accessors use no tick. '
                'Hole, retain, two closures, application and two drops consume 7 more. Fill is tick15. '
                'The next drop attempts tick16 and must retain the just-filled internal cycle on fuel exhaustion. '
                'Group-mode coverage is reported from its actual trace, not assumed from this coarse schedule.')


def run_fault_pair(program, output, env, info):
    output.mkdir()
    build.save(output/'selection.json', {'fuel':FAULT_FUEL,'reason':FAULT_REASON,
               'selected_before_launch':True,'policies':['retain','destroy-terminal']})
    reports = []
    for policy in ('retain','destroy-terminal'):
        stdout, stderr = build.run([str(program),'--fuel',str(FAULT_FUEL),'--failure-policy',policy],
            output,policy,cwd=program.parent,env=env,wall=30,cpu=20,memory=1<<30,
            expected=2,stdout_limit=32<<20,stderr_limit=1<<20)
        require(not bounded_read(stderr,1<<20),'known native fuel fault wrote stderr')
        reports.append(read_json(stdout))
    observed=observe_fault_pair(*reports,FAULT_FUEL,info)
    observed['copied_report_controls']=(fault_controls(*reports,FAULT_FUEL,info)
        if observed['after_fill'] and observed['live_recursive_cycle_at_fault'] else [])
    build.save(output/'observation.json',observed)
    return observed


def run_case(args, output, env):
    name = 'sum-list'; inputs = output/(name+'-inputs'); inputs.mkdir()
    (inputs/'SharedPoly.emlf').write_text(SHARED,encoding='utf-8')
    entry = inputs/'main.emlf'; entry.write_text(SOURCE,encoding='utf-8')
    target = output/name
    command = [sys.executable,'-B',str(BASE/'run_source_v8.py'),str(entry),'--module-root',str(inputs),
               '--ghc',args.ghc,'--cc',args.cc,'--output',str(target)]
    if args.data_groups:
        command.append('--data-groups')
    build.run(command,output,name,cwd=BASE,env=env,wall=1200,cpu=900,memory=16<<30,
              termination_grace=15,stdout_limit=1<<20,stderr_limit=1<<20,file_limit=64<<20)
    require(not bounded_read(output/(name+'.stderr'),1<<20),'successful CLI wrote stderr')
    result=read_json(target/'result.json'); evaluation=read_json(target/'native/run.stdout')
    require(result['status']=='complete' and result['failure_policy']=='retain' and result['native']==evaluation and
            'placement' not in result and evaluation['schema']=='resource-ir-v8-run/1','fresh CLI result contract differs')
    capture=read_json(target/'capture.stdout'); verified=read_json(target/'verification.json')
    require(verified['fragment_admitted'] and verified['normalization_replay']=='all exact independent fields match' and
            capture['checked_type']==INT,'fresh ordinary checking/replay differs')
    plan=read_json(target/'planned.json',8<<20)
    require(plan['binding']['mode']==('data-groups-prototype' if args.data_groups else 'coarse-owned'),'plan mode differs')
    generated=bounded_read(target/'native/ir8_runtime_generated.c',8<<20).decode('utf-8')
    info=structure(capture,plan,generated); graph=shared_graph(plan,verified,capture)
    observation=observe(evaluation,info,graph)
    controls=copied_controls(capture,plan,evaluation,generated)
    fault=run_fault_pair(target/'native/program',target/'fault-pair',env,info)
    if not args.data_groups:
        require(fault['after_fill'] and fault['live_recursive_cycle_at_fault'],
                'fixed coarse fuel did not cover the predicted filled cycle; retain actual report')
    row={'case':name,'status':'passed','data_groups':args.data_groups,
         'source_hashes':{'main.emlf':build.sha(SOURCE.encode()),'SharedPoly.emlf':build.sha(SHARED.encode())},
         'observation':observation,'copied_report_controls':controls,'fault_pair':fault}
    build.save(target/'monomorphic-recursion-observations.json',row)
    print('sum-list: PASS (fresh singleton recursive knot, one closure/Code, Cons/Cons/Nil, shared21 once, Int42, zero ledgers)',flush=True)
    return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc',required=True)
    parser.add_argument('--cc',default='cc')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--data-groups',action='store_true')
    args=parser.parse_args(); output=args.output.absolute()
    require(output.resolve()==output and output!=BASE.parents[2] and BASE.parents[2] not in output.parents,
            'output must be canonical and outside this checkout')
    output.mkdir(parents=True,exist_ok=False); env=cli.environment(output)
    build.SUITE_DEADLINE=time.monotonic()+1800
    try:
        row=run_case(args,output,env)
    except BaseException as exc:
        try:
            build.save(output/'failure.json',{'error':type(exc).__name__+': '+str(exc),'completed_cases':[]})
        except BaseException as persistence:
            exc.add_note('Failure persistence also failed: '+repr(persistence))
        raise
    build.save(output/'results.json',[row])
    return 0


if __name__=='__main__':
    raise SystemExit(main())
