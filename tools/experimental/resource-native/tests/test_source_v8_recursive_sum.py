#!/usr/bin/env python3
"""Two fresh, bounded real-source self-recursive SUM CLI tests.

Finite IntList graphs only: nested shared heads and an undemanded ordinary tail
application. Derive nominal/binder/Site/code joins from each fresh checked source;
never recognize historical resolver IDs or substitute saved capture bytes. The
existing runtime ABI, old tests and default CLI remain unchanged. Optional
--data-groups changes supporting placement, not the coarse SUM/factory policy.

Copied-report controls test this observer without invoking another producer or
native target. The module also exposes structure(), shared_graph(), observe(),
and copied_controls() for a parent-owned host-only evidence check.
"""
import argparse
import copy
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

require = build.require
SHARED = ('module SharedPoly (sharedId) where\n'
          'sharedId : forall a. a -> a\nsharedId x = x\n')
NESTED = ('import SharedPoly\ndata IntList = Nil | Cons Int IntList;\n'
          'let payload = addInt 20 1 in\nlet rest = Cons payload Nil in\n'
          'let xs = Cons payload rest in\nif sharedId true then\n'
          '  sharedId (case xs of {\n    Nil -> 0;\n'
          '    Cons x tail -> case tail of {\n      Nil -> x;\n'
          '      Cons y _ -> addInt x y\n    }\n  })\nelse 0\n')
LAZY_TAIL = ('import SharedPoly\ndata IntList = Nil | Cons Int IntList;\n'
             'let payload = addInt 20 22 in\n'
             'let tail = (\\x -> Cons x Nil) (addInt 100 23) in\n'
             'let xs = Cons payload tail in\nif sharedId true then\n'
             '  sharedId (case xs of { Nil -> 0; Cons x _ -> x })\nelse 0\n')
CASES = ({'name': 'nested', 'source': NESTED, 'head': 21, 'case_count': 2},
         {'name': 'lazy-tail', 'source': LAZY_TAIL, 'head': 42, 'case_count': 1})
INT = {'tag': 'constructor', 'name': 'Int', 'arguments': []}


def read_json(path, limit=32 << 20):
    return json.loads(bounded_read(path, limit))


def one(rows, message):
    require(len(rows) == 1, message + ': ' + str(len(rows)))
    return rows[0]


def walk(value, path=()):
    """Iterative walk of already bounded, finite source/plan JSON."""
    pending = [(tuple(path), value)]
    while pending:
        current, node = pending.pop()
        yield list(current), node
        if isinstance(node, dict):
            pending.extend((current + (key,), child) for key, child in reversed(list(node.items())))
        elif isinstance(node, list):
            pending.extend((current + (str(i),), node[i]) for i in range(len(node)-1, -1, -1))


def primitive(node, left, right):
    if not isinstance(node, dict) or node.get('tag') != 'application':
        return False
    function = node.get('function', {})
    head = function.get('function', {})
    return (node.get('argument') == {'tag': 'int64', 'value': right} and
            function.get('tag') == 'application' and
            function.get('argument') == {'tag': 'int64', 'value': left} and
            head.get('tag') == 'primitive' and head.get('name') == 'addInt' and head.get('arguments') == [])


def var(node, binding):
    return node == {'tag': 'var', 'name': binding}


def closed_layout(program, reference):
    if reference.startswith('^'):
        row = program['types'][reference[1:]]
        require(set(row) == {'tag', 'layout'} and row['tag'] == 'closed', 'expected exact closed logical atom')
        return row['layout']
    return reference


def source_allocation(plan, path, role):
    mapping = one([row for row in plan['binding']['source_map']['allocation_map']
                   if row['source'] == {'stage': 'normalized', 'path': path} and row['role'] == role],
                  'one exact source allocation for ' + role)
    operation = instruction(plan['program'], mapping['instruction'])
    require(operation['op'] == role, 'source allocation opcode differs')
    return operation


def constructor_terms(raw, row):
    path = list(row['source']['path']); node = at(raw, path); arguments = []
    while node['tag'] == 'application':
        arguments.append((path + ['argument'], node['argument']))
        node = node['function']; path += ['function']
    require(row['head'] == {'stage': 'normalized', 'path': path} and node['tag'] == 'constructor' and
            node['arguments'] == [], 'constructor head/source correspondence differs')
    arguments.reverse()
    require(row['arguments'] == [{'stage': 'normalized', 'path': p} for p, _ in arguments],
            'constructor ordered argument correspondence differs')
    return node, arguments


def structure(case, capture, plan, generated=None):
    """Join complete declarations, lexical fields, every arm, and allocation paths."""
    p, mapping = plan['program'], plan['binding']['source_map']
    raw = capture['normalization']['raw_normalized']
    family = one(mapping['sum_map'], 'one recursive nominal mapping')
    require(raw['tag'] == 'with_data' and len(p['families']) == 1 and not p['layouts'],
            'recursive nominal representation differs')
    declaration = raw['declarations'][family['declaration']]
    require(family['source'] == {'stage': 'projected', 'path': ['declarations', str(family['declaration'])]} and
            at(capture['projection']['projected_annotated'], family['source']['path']) == declaration,
            'declaration custody/path differs')
    nominal = {'tag': 'applied', 'name': declaration['name'], 'arguments': []}
    fields = [[], [{'tag': 'applied', 'name': 'Int', 'arguments': []}, nominal]]
    require(declaration['tag'] == 'data_kind' and declaration['parameters'] == [] and
            declaration['name'] == family['name'] and
            [v['fields'] for v in declaration['constructors']] == fields,
            'exact parameter-free self-owner declaration differs')
    physical = '%' + family['family']
    require(p['families'][family['family']] == {'variants': ['V0', 'V1'],
            'fields': {'V0': [], 'V1': ['#i64', physical]}}, 'exact recursive family field inventory differs')
    require(len(family['variants']) == 2, 'complete nominal variant map differs')
    for index, variant in enumerate(family['variants']):
        require(variant['index'] == index and variant['variant'] == 'V'+str(index) and
                variant['constructor'] == declaration['constructors'][index]['name'] and
                variant['constructor_source'] == {'stage': 'projected', 'path':
                    family['source']['path'] + ['constructors', str(index)]} and
                [p['types'][t] for t in variant['fields']] ==
                    ([] if index == 0 else [{'tag': 'closed', 'layout': '#i64'}, {'tag': 'closed', 'layout': physical}]),
                'variant owner/order/full field types differ')
    terms = list(walk(raw['body'], ['body']))
    lets = [(path, node) for path, node in terms if isinstance(node, dict) and node.get('tag') == 'let']
    payload_path, _ = one([(path, node) for path, node in terms if primitive(node, 20, case['head'] - 20)],
                          'one actual pending head expression')
    payload_let = at(raw, payload_path[:-1])
    require(payload_path[-1] == 'value' and payload_let['tag'] == 'let', 'head must retain its lexical let')
    payload = source_allocation(plan, payload_path, 'thunk')
    constructors = []
    require(len(mapping['sum_constructor_map']) == 3, 'three lexical constructor occurrences required')
    for row in mapping['sum_constructor_map']:
        require(row['declaration'] == family['declaration'] and row['variant'] in (0, 1),
                'constructor nominal owner differs')
        head, arguments = constructor_terms(raw, row)
        require(head['name'] == declaration['constructors'][row['variant']]['name'] and
                len(arguments) == len(fields[row['variant']]), 'constructor full saturation differs')
        role = 'construct_sum' if arguments else 'construct_nullary'
        op = source_allocation(plan, row['source']['path'], role)
        require(op == instruction(p, row['allocation']) and op['family'] == family['family'] and
                op['variant'] == 'V'+str(row['variant']) and
                len(op.get('fields', [])) == len(arguments), 'constructor allocation binding differs')
        constructors.append({'map': row, 'operation': op, 'arguments': arguments})
    require(sorted(x['map']['variant'] for x in constructors) == [0, 1, 1], 'constructor inventory differs')
    uses = mapping['use_map']
    int_use = one([row for row in uses if [p['types'][t]['layout'] for t in row['arguments']] == ['#i64']],
                  'one actual complete Int use')
    call_path = int_use['source']['path'][:-1]
    require(int_use['source']['path'][-1] == 'function' and at(raw, call_path)['tag'] == 'application',
            'actual shared Int application lost')
    outer_path = call_path + ['argument']; outer_source = at(raw, outer_path)
    require(outer_source['tag'] == 'case' and outer_source['scrutinee']['tag'] == 'var',
            'shared Int argument must retain its lazy source case')
    xs_path, xs = one([(path, node) for path, node in lets
                       if node['name'] == outer_source['scrutinee']['name']], 'outer scrutinee lexical binding')
    outer_constructor = one([x for x in constructors if x['map']['source']['path'] == xs_path + ['value']],
                            'outer constructor source')
    head_argument, tail_argument = [node for _, node in outer_constructor['arguments']]
    require(var(head_argument, payload_let['name']) and tail_argument['tag'] == 'var',
            'outer Cons head/tail binding differs')
    tail_path, tail_let = one([(path, node) for path, node in lets if node['name'] == tail_argument['name']],
                             'tail lexical binding')
    cases = mapping['sum_case_map']
    require(len(cases) == case['case_count'], 'complete source case inventory differs')
    source_cases = [path for path, node in terms if isinstance(node, dict) and node.get('tag') == 'case']
    require(sorted(row['source']['path'] for row in cases) == sorted(source_cases), 'source case coverage differs')
    outer = one([row for row in cases if row['source']['path'] == outer_path], 'outer source case mapping')
    field_count = 0
    for row in cases:
        source = at(raw, row['source']['path'])
        require(row['source']['stage'] == 'normalized' and row['declaration'] == family['declaration'] and
                row['family'] == family['family'] and source['result_type'] == INT and
                p['types'][row['result_type']] == {'tag': 'closed', 'layout': '#i64'},
                'case exact owner/result type differs')
        require(len(source['alternatives']) == len(row['arms']) == 2 and
                sorted(a['variant'] for a in row['arms']) == [0, 1], 'exhaustive source arms lost')
        factory = instruction(p, row['factory'])
        require(factory['op'] == 'case_fields_i64' and factory['family'] == family['family'] and
                list(factory['arms']) == ['V0', 'V1'] and factory['in'] == '$home', 'factory inventory/placement differs')
        case_op = source_allocation(plan, row['source']['path'], 'thunk')
        require(case_op == instruction(p, row['allocation']) and case_op['code'] == row['code'], 'case thunk mapping differs')
        body = p['codes'][row['code']]['body']
        require(sum(op['op'] == 'force' for op in body) == 1 and
                not any(op['op'] in ('application', 'thunk', 'prim2', 'field', 'construct_sum', 'construct_nullary') for op in body),
                'case eagerly constructs an arm or payload')
        for arm in row['arms']:
            alternative = source['alternatives'][arm['index']]
            pattern = alternative['pattern']; variant = arm['variant']
            require(pattern['tag'] == 'constructor' and pattern['constructor'] == arm['constructor'] ==
                    declaration['constructors'][variant]['name'] and len(pattern['fields']) == len(fields[variant]) and
                    arm['pattern_source'] == {'stage': 'normalized', 'path': row['source']['path'] +
                        ['alternatives', str(arm['index']), 'pattern']} and
                    arm['source'] == {'stage': 'normalized', 'path': row['source']['path'] +
                        ['alternatives', str(arm['index']), 'body']} and at(raw, arm['source']['path']) == alternative['body'],
                    'arm pattern/body source identity differs')
            bindings = factory['arms']['V'+str(variant)]
            require(bindings == {'code': arm['code'], 'captures': arm['captures']} and
                    set(bindings['captures']) == set(p['codes'][arm['code']]['captures']), 'arm factory/code binding differs')
            expected = [(i, binder) for i, binder in enumerate(pattern['fields']) if binder is not None]
            require(len(arm['field_captures']) == len(expected), 'wildcard or complete field capture inventory differs')
            for field, (index, binder) in zip(arm['field_captures'], expected):
                layout = '#i64' if index == 0 else physical
                require(field['index'] == index and field['binder'] == binder['id'] and field['relation'] == 'down' and
                        p['types'][field['type']] == {'tag': 'closed', 'layout': layout} and
                        bindings['captures'][field['capture']] == {'kind': 'field', 'index': index} and
                        set(p['codes'][arm['code']]['captures'][field['capture']]) == {'layout', 'relation'} and
                        p['codes'][arm['code']]['captures'][field['capture']]['relation'] == 'down' and
                        closed_layout(p, p['codes'][arm['code']]['captures'][field['capture']]['layout']) == layout,
                        'field binder/position/exact nominal type differs')
            field_count += len(expected)
            site = one([x for x in mapping['allocation_map'] if x['instruction'] == row['factory'] and
                        x.get('arm') == variant], 'one exhaustive per-variant source Site')
            require(site['source'] == arm['source'] and site['role'] == 'case_fields_i64' and site['type_scope'] is None and
                    p['types'][site['logical_type']] == {'tag': 'closed', 'layout': '#i64'}, 'arm Site correspondence differs')
    outer_arm = one([a for a in outer['arms'] if a['variant'] == 1], 'outer Cons arm')
    info = {'family': family, 'physical': physical, 'constructors': constructors, 'cases': cases,
            'outer': outer, 'outer_constructor': outer_constructor['operation'], 'payload': payload,
            'int_argument': instruction(p, outer['allocation'])}
    if case['name'] == 'nested':
        inner_ctor = one([x for x in constructors if x['map']['source']['path'] == tail_path + ['value']],
                         'inner constructor source')
        require(var(inner_ctor['arguments'][0][1], payload_let['name']), 'both heads must share one lexical payload')
        nil = one([x for x in constructors if x['map']['variant'] == 0], 'terminal Nil constructor')
        require(inner_ctor['arguments'][1][0] == nil['map']['source']['path'], 'inner tail must be the same lexical Nil')
        inner = one([row for row in cases if row['source'] == outer_arm['source']], 'nested case exact arm body')
        outer_fields = outer_source['alternatives'][outer_arm['index']]['pattern']['fields']
        inner_source = at(raw, inner['source']['path'])
        require(var(inner_source['scrutinee'], outer_fields[1]), 'nested case did not use exact outer tail binder')
        inner_arm = one([a for a in inner['arms'] if a['variant'] == 1], 'inner Cons arm')
        inner_pattern = inner_source['alternatives'][inner_arm['index']]['pattern']['fields']
        add = at(raw, inner_arm['source']['path'])
        require(inner_pattern[1] is None and add['tag'] == 'application' and var(add['argument'], inner_pattern[0]) and
                add['function']['tag'] == 'application' and var(add['function']['argument'], outer_fields[0]) and
                add['function']['function'].get('tag') == 'primitive' and add['function']['function'].get('name') == 'addInt',
                'nested selected body must add the exact two field binders')
        info.update(inner=inner, inner_constructor=inner_ctor['operation'], nil=nil['operation'],
                    addition=source_allocation(plan, inner_arm['source']['path'], 'thunk'))
    else:
        tail_source = tail_let['value']; tail_source_path = tail_path + ['value']
        require(tail_source['tag'] == 'application' and tail_source['function']['tag'] == 'lambda' and
                tail_source['function']['parameter_type'] == INT and primitive(tail_source['argument'], 100, 23),
                'tail must retain its ordinary closed lambda/application/123 argument')
        lambda_path = tail_source_path + ['function']; function = tail_source['function']
        inner_ctor = one([x for x in constructors if x['map']['source']['path'] == lambda_path + ['body']],
                         'unentered lambda Cons body')
        require(var(inner_ctor['arguments'][0][1], function['parameter']), 'lambda Cons field lost its formal binder')
        nil = one([x for x in constructors if x['map']['variant'] == 0], 'unentered lambda Nil')
        require(inner_ctor['arguments'][1][0] == nil['map']['source']['path'], 'lambda Cons tail is not its actual Nil')
        closure = source_allocation(plan, lambda_path, 'closure')
        declared = p['functions'][closure['function']]
        signature = p['signatures'][declared['signature']]
        require(declared['type_scope'] is None and set(signature) == {'argument', 'result', 'protocol', 'result_identity'} and
                closed_layout(p, signature['argument']) == '#i64' and closed_layout(p, signature['result']) == physical and
                signature['protocol'] == 'repeat' and signature['result_identity'] == 'unknown',
                'tail lambda must remain monomorphic Int to exact family')
        pattern = outer_source['alternatives'][outer_arm['index']]['pattern']['fields']
        require(pattern[1] is None and var(at(raw, outer_arm['source']['path']), pattern[0]),
                'lazy case must return only its head with a wildcard tail')
        info.update(tail=source_allocation(plan, tail_source_path, 'application'), closure=closure,
                    argument=source_allocation(plan, tail_source_path + ['argument'], 'thunk'),
                    inner_constructor=inner_ctor['operation'], nil=nil['operation'])
    if generated is not None:
        require(generated.count('= rt8_case_fields_i64(') == len(cases) and '= rt8_case_i64(' not in generated and
                generated.count(' = RT8_FACTORY_FIELD;') == field_count, 'generated exhaustive factory/field grammar differs')
    return info


def shared_graph(plan, verified, capture):
    p, mapping = plan['program'], plan['binding']['source_map']
    scheme = one(mapping['scheme_map'], 'one actual shared Scheme')
    definition = one(verified['fragment']['definitions'], 'one verified shared definition')
    require(scheme['binder'] == definition['binding']['id'] and len(p['schemes']) == 1 and
            p['schemes'][scheme['scheme']]['parameters'] == 1, 'shared binder/full prefix differs')
    vectors = [[p['types'][t]['layout'] for t in row['arguments']] for row in p['instantiations'].values()]
    require(vectors == [['#bool'], ['#i64']] and len(mapping['use_map']) == len(verified['fragment']['uses']) == 2,
            'complete shared Bool/Int vectors or source uses differ')
    raw = capture['normalization']['raw_normalized']
    cursor = at(raw, scheme['rhs_cursor']['path'])
    generic, seal = instruction(p, scheme['generalize']), instruction(p, scheme['seal'])
    pending = one([x for x in generic['body'] if x['op'] == 'application'], 'one actual pending generic RHS')
    require(cursor['tag'] == 'application' and cursor['function']['tag'] == cursor['argument']['tag'] == 'lambda' and
            pending['out'] == seal['value'] and not any(x['op'] == 'force' for x in generic['body']),
            'shared pending RHS replaced or made eager')
    closures = {x['out']: x['function'] for x in generic['body'] if x['op'] == 'closure'}
    carriers = [x for x in mapping['carrier_map'] if x['kind'] == 'lambda']
    source_lambdas = [path for path, node in walk(raw['body'], ['body'])
                      if isinstance(node, dict) and node.get('tag') == 'lambda']
    require(sorted(row['source']['path'] for row in carriers) == sorted(source_lambdas) and
            len(carriers) == len(p['functions']), 'ordinary lambdas cloned or removed')
    for variable, child in ((pending['function'], 'function'), (pending['argument'], 'argument')):
        row = one([x for x in carriers if x['source']['path'] == scheme['rhs_cursor']['path'] + [child]],
                  'actual shared source lambda carrier')
        require(row['ir_code'] == closures[variable] and row['type_scope'] == scheme['scheme'],
                'generic source lambda/code/scope association differs')
    return {'outer_code': closures[pending['function']], 'shared_code': closures[pending['argument']],
            'seal_owner': seal['value'], 'vectors': vectors, 'uses': sorted(p['instantiations'])}


def observe(case, evaluation, info, graph):
    e = evaluation
    require(e['fault'] == 0 and e['result'] == {'kind': 'i64', 'value': 42} and
            e['scalar_result_kind'] == 1 and e['scalar_result'] == 42 and e['events_omitted'] == 0,
            'actual native Int42/fault/event result differs')
    metrics = e['metrics']
    require(metrics['entries_completed'] == 1 and metrics['groups_allocated'] == metrics['groups_closed'] and
            metrics['nodes_allocated'] == metrics['nodes_freed'], 'incomplete runtime cleanup')
    for role in ('owner', 'loan'):
        require(metrics[role+'_handle_acquisitions'] == metrics[role+'_handle_releases'], 'unbalanced '+role)
    require(set(e['memory_categories']) == {'context', 'groups', 'nodes', 'slots', 'handles', 'captures', 'pending'},
            'exact seven ledger categories differ')
    for row in [e['memory']] + list(e['memory_categories'].values()):
        require(row['live_bytes'] == row['live_blocks'] == 0 and row['allocated_bytes'] == row['freed_bytes'] and
                row['allocations'] == row['frees'], 'nonempty/unbalanced runtime ledger')
    events = e['events']
    selected = lambda name: [(i, x) for i, x in enumerate(events) if x['event'] == name]
    allocations = selected('allocate'); nodes = {x['node']: x for _, x in allocations}
    require(len(nodes) == len(allocations), 'allocation node identity repeated')

    def allocation(op, label):
        index, event = one([(i, x) for i, x in allocations if x['out'] == op['out']], label + ' allocation once')
        expected_code = op['function'] if op['op'] == 'closure' else op.get('code')
        require(event['opcode'] == op['op'] and event['code'] == expected_code,
                label + ' allocation opcode/code differs')
        return index, event

    outer_i, outer_node = allocation(info['outer_constructor'], 'outer Cons')
    payload_i, payload = allocation(info['payload'], 'pending head')
    require(payload['state'] == 'THUNK' and payload_i < outer_i, 'original head thunk became eager')
    require(outer_node['slots'].get('0') == payload['node'], 'outer head slot lost shared pending payload')
    actual_constructors = [outer_node]
    if case['name'] == 'nested':
        inner_i, inner_node = allocation(info['inner_constructor'], 'inner Cons')
        nil_i, nil = allocation(info['nil'], 'Nil')
        require(payload_i < nil_i < inner_i < outer_i and not nil['slots'] and
                inner_node['slots'] == {'0': payload['node'], '1': nil['node']} and
                outer_node['slots'] == {'0': payload['node'], '1': inner_node['node']},
                'nested constructor edges lost head sharing or exact tail identity')
        actual_constructors += [inner_node, nil]
        expected_cases = [(info['outer'], outer_node), (info['inner'], inner_node)]
    else:
        tail_i, tail = allocation(info['tail'], 'pending ordinary tail')
        closure_i, closure = allocation(info['closure'], 'ordinary tail lambda')
        argument_i, argument = allocation(info['argument'], 'pending 123 argument')
        require(closure['state'] == 'CLOSURE' and tail['state'] == 'APPLICATION' and argument['state'] == 'THUNK' and
                max(closure_i, argument_i) < tail_i < outer_i and
                tail['slots'] == {'$function': closure['node'], '$argument': argument['node']} and
                outer_node['slots'] == {'0': payload['node'], '1': tail['node']},
                'pending tail graph or outer exact tail identity differs')
        require(not any(x['out'] in (info['inner_constructor']['out'], info['nil']['out']) for _, x in allocations),
                'unentered tail lambda allocated an inner constructor')
        for target in (tail['node'], argument['node']):
            require(not any(x['node'] == target for _, x in selected('update_pin') + selected('callback_enter')) and
                    not any(x['destination'] == target for _, x in selected('memo_publish')),
                    'unused tail or 123 argument was demanded')
        require(not any(x['closure'] == closure['node'] for _, x in selected('invoke_enter')) and
                not any(x['context'].get('name') == info['closure']['function'] for _, x in selected('frame_enter')),
                'unused ordinary tail lambda was entered')
        require(not any(x['kind'] == 'i64' and x['value'] == 123 for _, x in selected('scalar_value')),
                'unused 123 argument was computed')
        expected_cases = [(info['outer'], outer_node)]
    sum_values = selected('sum_value')
    require(len(sum_values) == len(actual_constructors), 'only demanded lexical SUM constructors may allocate')
    for node in actual_constructors:
        _, value = one([(i, x) for i, x in sum_values if x['node'] == node['node']], 'one exact SUM value')
        index = 0 if not node['slots'] else 1
        require(value['family'] == info['physical'] and value['variant_index'] == index and
                value['variant'] == 'V'+str(index) and node['layout'] == info['physical'], 'actual nominal family/variant differs')
    factory_events = selected('case_fields_i64')
    require(len(factory_events) == len(expected_cases), 'selected factory event count differs')
    require(len([x for _, x in allocations if x['opcode'] == 'case_fields_i64']) == len(expected_cases),
            'unselected factory allocated')
    field_events = selected('sum_field_capture'); expected_field_count = 0; factory_nodes = []; head_captures = []
    for (row, scrutinee), (factory_i, event) in zip(expected_cases, factory_events):
        arm = one([a for a in row['arms'] if a['variant'] == 1], 'selected Cons source arm')
        unselected = one([a for a in row['arms'] if a['variant'] == 0], 'unselected Nil source arm')
        require(event['scrutinee'] == scrutinee['node'] and event['family'] == info['physical'] and
                event['variant_index'] == 1 and event['variant'] == 'V1' and event['code'] == arm['code'],
                'selected factory exact source/scrutinee/variant identity differs')
        allocated_i, allocated = one([(i, x) for i, x in allocations if x['node'] == event['result']], 'selected factory allocation')
        require(allocated['opcode'] == 'case_fields_i64' and allocated['code'] == arm['code'] and
                allocated['slots'] == event['captures'], 'selected factory allocation/captures differ')
        require(not any(x['code'] == unselected['code'] for _, x in allocations) and
                not any(x['context'].get('name') == unselected['code'] for _, x in selected('frame_enter')),
                'unselected Nil factory allocated or entered')
        callback_i, _ = one([(i, x) for i, x in selected('callback_enter') if x['node'] == allocated['node']],
                           'selected factory callback once')
        require(allocated_i < factory_i < callback_i, 'selected factory allocation/entry order differs')
        expected_indices = {field['capture']: field['index'] for field in arm['field_captures']}
        require(event['field_indices'] == expected_indices and event['field_mask'] ==
                sum(1 << index for index in expected_indices.values()), 'wildcard field acquisition/mask differs')
        expected_field_count += len(expected_indices)
        for field in arm['field_captures']:
            field_i, acquired = one([(i, x) for i, x in field_events if x['scrutinee'] == scrutinee['node'] and
                                     x['capture'] == field['capture']], 'one selected field edge acquisition')
            target = scrutinee['slots'][str(field['index'])]
            require(acquired['node'] == event['captures'][field['capture']] == target and
                    acquired['field_index'] == field['index'] and acquired['family'] == info['physical'] and
                    acquired['variant'] == 'V1' and acquired['variant_index'] == 1 and
                    acquired['layout'] == ('#i64' if field['index'] == 0 else info['physical']) and
                    field_i < allocated_i, 'selected field lost its exact original node/type')
            if field['index'] == 0:
                require(target == payload['node'], 'selected head capture lost shared pending payload')
                head_captures.append(field_i)
        factory_nodes.append(allocated['node'])
    require(len(field_events) == expected_field_count, 'extra/unselected/wildcard field capture occurred')
    demand_i, _ = one([(i, x) for i, x in selected('update_pin') if x['node'] == payload['node']], 'head demanded once')
    callback_i, _ = one([(i, x) for i, x in selected('callback_enter') if x['node'] == payload['node']], 'head callback once')
    memo_i, memo = one([(i, x) for i, x in selected('memo_publish') if x['destination'] == payload['node']], 'head memo once')
    scalars = {x['node']: (x['kind'], x['value']) for _, x in selected('scalar_value')}
    require(scalars.get(memo['result']) == ('i64', case['head']) and
            max(head_captures) < demand_i < callback_i < memo_i, 'head lazy timing/value differs')
    if case['name'] == 'nested':
        _, addition = allocation(info['addition'], 'nested field addition')
        _, frame = one([(i, x) for i, x in selected('frame_enter') if
                        x['context'].get('node') == addition['node'] and x['context'].get('name') == info['addition']['code']],
                       'nested field addition callback frame')
        forces = [(i, x) for i, x in selected('ir_force_result') if x['frame'] == frame['frame']]
        add_memo_i, add_memo = one([(i, x) for i, x in selected('memo_publish') if x['destination'] == addition['node']],
                                 'nested field addition memo once')
        require(len(forces) == 2 and all(x['result'] == memo['result'] for _, x in forces) and
                memo_i < forces[0][0] < forces[1][0] < add_memo_i and scalars.get(add_memo['result']) == ('i64', 42),
                'both nested heads did not reuse the one 21 memo result')
    begin = one(selected('generic_begin'), 'one generic introduction')
    seal = one(selected('generic_seal'), 'one generic seal')
    uses = selected('instantiate'); shared = seal[1]['node']
    require(begin[0] < seal[0] and sorted(x['use'] for _, x in uses) == list(range(len(graph['uses']))) and
            all(x['node'] == shared for _, x in uses), 'full generic views lost one shared node')
    pending = nodes[shared]
    require(pending['state'] == 'APPLICATION' and pending['out'] == graph['seal_owner'], 'generic shared pending RHS differs')
    outer, body = pending['slots']['$function'], pending['slots']['$argument']
    require(nodes[outer]['code'] == graph['outer_code'] and nodes[body]['code'] == graph['shared_code'] and
            sum(x['code'] == graph['shared_code'] for _, x in allocations) == 1, 'generic shared body cloned or changed')
    rhs_memo_i, rhs_memo = one([(i, x) for i, x in selected('memo_publish') if x['destination'] == shared], 'generic RHS memo once')
    require(rhs_memo['result'] == body, 'generic RHS memo bypassed its actual body')
    calls = selected('invoke_enter')
    one([x for _, x in calls if x['closure'] == outer], 'generic RHS outer invocation once')
    actual = [(i, x) for i, x in calls if x['closure'] == body]
    require(len(actual) == 2 and rhs_memo_i < actual[0][0] < actual[1][0] and
            scalars.get(actual[0][1]['argument']) == ('bool', True), 'same generic body Bool/Int demand order differs')
    _, int_argument = allocation(info['int_argument'], 'lazy shared Int case argument')
    require(actual[1][1]['argument'] == int_argument['node'] and int_argument['state'] == 'THUNK',
            'shared Int argument lost its actual pending case')
    arg_demand_i, _ = one([(i, x) for i, x in selected('update_pin') if x['node'] == int_argument['node']],
                        'lazy case argument demanded once')
    arg_memo_i, arg_memo = one([(i, x) for i, x in selected('memo_publish') if x['destination'] == int_argument['node']],
                             'lazy case argument memo once')
    require(actual[1][0] < arg_demand_i < arg_memo_i and scalars.get(arg_memo['result']) == ('i64', 42),
            'shared Int case argument demand/result differs')
    return {'case': case['name'], 'head_node': payload['node'], 'head_memo_node': memo['result'],
            'head_evaluations': 1, 'head_memos': 1, 'constructor_nodes': [x['node'] for x in actual_constructors],
            'selected_factory_nodes': factory_nodes, 'selected_factory_only': True,
            'unused_tail_demanded': False if case['name'] == 'lazy-tail' else None,
            'shared_node': shared, 'shared_body_node': body, 'shared_rhs_evaluations': 1,
            'vectors': graph['vectors'], 'memory': e['memory'], 'memory_categories': e['memory_categories']}


def copied_controls(case, capture, plan, evaluation, generated=None):
    """Reject targeted copies; never invoke a producer, planner, or native target."""
    info = structure(case, capture, plan, generated)
    # A caller passes already checked source structure; only the source graph
    # fields needed below are derived directly from its exact immutable mappings.
    p, mapping = plan['program'], plan['binding']['source_map']
    scheme = one(mapping['scheme_map'], 'one shared Scheme for copied controls')
    generic = instruction(p, scheme['generalize']); seal = instruction(p, scheme['seal'])
    pending = one([x for x in generic['body'] if x['op'] == 'application'], 'one shared cursor for copied controls')
    closures = {x['out']: x['function'] for x in generic['body'] if x['op'] == 'closure'}
    graph = {'outer_code': closures[pending['function']], 'shared_code': closures[pending['argument']],
             'seal_owner': seal['value'], 'uses': sorted(p['instantiations']),
             'vectors': [[p['types'][t]['layout'] for t in row['arguments']] for row in p['instantiations'].values()]}
    observe(case, evaluation, info, graph)
    results = []

    def reject(name, mutation, expected):
        changed = copy.deepcopy(evaluation); mutation(changed)
        try:
            observe(case, changed, info, graph)
        except AssertionError as exc:
            require(expected in str(exc), name + ' rejected at unexpected observer guard: ' + str(exc))
            results.append({'control': name, 'status': 'rejected', 'guard': expected})
        else:
            raise AssertionError(name + ' copied report unexpectedly accepted')

    def event(report, kind, predicate=lambda row: True):
        return one([x for x in report['events'] if x['event'] == kind and predicate(x)], 'copied control target')

    def wrong_head(report):
        row = event(report, 'allocate', lambda x: x['out'] == info['outer_constructor']['out'])
        row['slots']['0'] = row['slots']['1']
    reject('head-alias-substitution', wrong_head, 'outer head slot lost shared pending payload')

    def duplicate_memo(report):
        head = event(report, 'allocate', lambda x: x['out'] == info['payload']['out'])['node']
        report['events'].append(copy.deepcopy(event(report, 'memo_publish', lambda x: x['destination'] == head)))
    reject('duplicate-head-memo', duplicate_memo, 'head memo once')

    def wrong_factory(report):
        next(x for x in report['events'] if x['event'] == 'case_fields_i64')['variant_index'] = 0
    reject('wrong-selected-variant', wrong_factory, 'selected factory exact source/scrutinee/variant identity differs')

    def wrong_shared(report):
        next(x for x in report['events'] if x['event'] == 'instantiate')['node'] = -1
    reject('split-generic-view', wrong_shared, 'full generic views lost one shared node')
    reject('nonzero-pending-ledger', lambda r: r['memory_categories']['pending'].__setitem__('live_blocks', 1),
           'nonempty/unbalanced runtime ledger')
    if case['name'] == 'lazy-tail':
        def tail_demand(report):
            tail = event(report, 'allocate', lambda x: x['out'] == info['tail']['out'])['node']
            report['events'].append({'event': 'update_pin', 'node': tail})
        reject('unused-tail-demand', tail_demand, 'unused tail or 123 argument was demanded')
        def lambda_entry(report):
            closure = event(report, 'allocate', lambda x: x['out'] == info['closure']['out'])['node']
            report['events'].append({'event': 'invoke_enter', 'closure': closure})
        reject('unused-tail-lambda-entry', lambda_entry, 'unused ordinary tail lambda was entered')
    altered = copy.deepcopy(plan)
    altered['program']['families'][info['family']['family']]['fields']['V1'][1] = '#i64'
    try:
        structure(case, capture, altered, generated)
    except AssertionError as exc:
        require('exact recursive family field inventory differs' in str(exc), 'wrong self-atom rejected at unrelated guard')
        results.append({'control': 'wrong-self-family-atom', 'status': 'rejected',
                        'guard': 'exact recursive family field inventory differs'})
    else:
        raise AssertionError('wrong self-family atom copied plan accepted')
    return results


def run_case(case, args, output, env):
    name = case['name']; inputs = output / (name+'-inputs'); inputs.mkdir()
    (inputs/'SharedPoly.emlf').write_text(SHARED, encoding='utf-8')
    entry = inputs/'main.emlf'; entry.write_text(case['source'], encoding='utf-8')
    target = output/name
    command = [sys.executable, '-B', str(BASE/'run_source_v8.py'), str(entry), '--module-root', str(inputs),
               '--ghc', args.ghc, '--cc', args.cc, '--output', str(target)]
    if args.data_groups:
        command.append('--data-groups')
    build.run(command, output, name, cwd=BASE, env=env, wall=1200, cpu=900, memory=16 << 30,
              termination_grace=15, stdout_limit=1 << 20, stderr_limit=1 << 20, file_limit=64 << 20)
    require(not bounded_read(output/(name+'.stderr'), 1 << 20), 'successful CLI wrote stderr')
    result = read_json(target/'result.json'); evaluation = read_json(target/'native/run.stdout')
    require(result['status'] == 'complete' and result['failure_policy'] == 'retain' and result['native'] == evaluation and
            'placement' not in result and evaluation['schema'] == 'resource-ir-v8-run/1', 'fresh CLI result contract differs')
    capture = read_json(target/'capture.stdout'); verified = read_json(target/'verification.json')
    require(verified['fragment_admitted'] and verified['normalization_replay'] == 'all exact independent fields match' and
            capture['checked_type'] == INT, 'fresh ordinary source checking/replay differs')
    plan = read_json(target/'planned.json', 8 << 20)
    require(plan['binding']['mode'] == ('data-groups-prototype' if args.data_groups else 'coarse-owned'), 'plan mode differs')
    generated = bounded_read(target/'native/ir8_runtime_generated.c', 8 << 20).decode('utf-8')
    info = structure(case, capture, plan, generated); graph = shared_graph(plan, verified, capture)
    observation = observe(case, evaluation, info, graph)
    controls = copied_controls(case, capture, plan, evaluation, generated)
    row = {'case': name, 'status': 'passed', 'data_groups': args.data_groups,
           'source_hashes': {'main.emlf': build.sha(case['source'].encode()), 'SharedPoly.emlf': build.sha(SHARED.encode())},
           'observation': observation, 'copied_report_controls': controls}
    build.save(target/'recursive-sum-observations.json', row)
    print(name+': PASS (fresh self-recursive SUM, selected factories, shared/lazy fields, Int42, zero ledgers)', flush=True)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', required=True)
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--data-groups', action='store_true', help='opt-in supporting groups; SUM placement remains coarse')
    args = parser.parse_args(); output = args.output.absolute()
    require(output.resolve() == output and output != BASE.parents[2] and BASE.parents[2] not in output.parents,
            'output must be canonical and outside this checkout')
    output.mkdir(parents=True, exist_ok=False); env = cli.environment(output)
    build.SUITE_DEADLINE = time.monotonic() + 3600
    results = []
    try:
        for case in CASES:
            results.append(run_case(case, args, output, env))
    except BaseException as exc:
        try:
            build.save(output/'failure.json', {'error': type(exc).__name__+': '+str(exc),
                                              'completed_cases': [row['case'] for row in results]})
        except BaseException as persistence:
            exc.add_note('Failure persistence also failed: '+repr(persistence))
        raise
    build.save(output/'results.json', results)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
