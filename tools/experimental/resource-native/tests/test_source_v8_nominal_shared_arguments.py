#!/usr/bin/env python3
"""Finite inferred-source tests for complete nominal shared type vectors.

These fixtures do not annotate shared uses. The curried case must pass the real
producer's nominal beta normalization. All source, Scheme, Use and node joins
come from fresh checked captures and metadata, not historical binder numbers.
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
from test_shared_source_native import at, instruction, SHARED_ID, SHARED_CONST
from test_source_v8_recursive_sum import (one, walk, primitive, var,
    source_allocation, constructor_terms, closed_layout, INT)
from test_source_v8_callable_captures import address, spine, read_json
from test_source_v8_nominal_captures import passthrough, sum_case_structure
from test_source_v8_monomorphic_recursion import ledger

require = build.require
BOOL = {'tag': 'constructor', 'name': 'Bool', 'arguments': []}
# These two nonrecursive graphs have no hole/Fill. Bit24 is the Fill-ticket
# guard, not a universal healthy-run coverage requirement. All others execute.
EXPECTED_GUARDS = ((1 << 27) - 1) & ~(1 << 24)
SOURCES = {
    'identity': ('import SharedPoly\ndata IntList = Nil | Cons Int IntList;\n'
        'let bonus = addInt 20 1 in\nlet xs = Cons bonus Nil in\n'
        'if sharedId true then case sharedId xs of { Nil -> 0; Cons n _ -> addInt n n } else 0\n'),
    'curried-const': ('import SharedPoly\ndata IntList = Nil | Cons Int IntList;\n'
        'let bonus = addInt 20 1 in\nlet xs = Cons bonus Nil in\n'
        'let unused : IntList = (\\n -> Cons n Nil) 123 in\n'
        'let consume : IntList -> Int = \\ys -> case sharedConst ys false of { Nil -> 0; Cons n _ -> addInt n n } in\n'
        'if sharedConst true unused then consume xs else 0\n')}
MODULES = {'identity': SHARED_ID, 'curried-const': SHARED_CONST}


def source_facts(capture, name):
    require(name in SOURCES, 'known inferred nominal fixture required')
    n = capture['normalization']; raw = n['raw_normalized']
    require(raw['tag'] == 'with_data' and all(n[k] for k in (
        'declarations_equal', 'erasure_equal', 'normalized_rechecked',
        'original_rechecked', 'root_type_alpha_equal')), 'full checked normalization required')
    require(n['policy'] == 'shared-rank1-callable/' + ('1' if name == 'identity' else '2'),
            'actual nominal-beta dialect differs')
    current, path, lets = raw['body'], ['body'], []
    while current['tag'] == 'let':
        lets.append((path, current)); current = current['body']; path = path + ['body']
    require(len(lets) == (3 if name == 'identity' else 5), 'original lexical let graph differs')
    shared_path, shared = lets[0]; bonus_path, bonus = lets[1]; xs_path, xs = lets[2]
    require(shared['value']['tag'] == 'type_lambda' and primitive(bonus['value'], 20, 1),
            'original generalized RHS or pending bonus differs')
    cons, _, fields = spine(xs['value'], xs_path + ['value'])
    require(cons['tag'] == 'constructor' and not cons['arguments'] and len(fields) == 2 and
            var(fields[0][1], bonus['name']) and fields[1][1]['tag'] == 'constructor' and
            not fields[1][1]['arguments'], 'original Cons bonus Nil graph differs')
    decl_index, declaration = one([(i, d) for i, d in enumerate(raw['declarations'])
        if any(c['name'] == cons['name'] for c in d['constructors'])], 'exact Cons declaration')
    nominal = {'tag': 'constructor', 'name': declaration['name'], 'arguments': []}
    require(not declaration['parameters'] and len(declaration['constructors']) == 2,
            'exact parameter-free two-variant declaration required')
    nil_name = fields[1][1]['name']
    branch, _, args = spine(current, path)
    require(branch['tag'] == 'primitive' and branch['name'] == 'ifThenElse' and
            branch['arguments'] == [INT] and len(args) == 3 and
            args[2][1] == {'tag': 'int64', 'value': 0}, 'original outer Int conditional differs')
    condition_path, condition = args[0]
    bh, bp, ba = spine(condition, condition_path)
    require(bh['tag'] == 'type_application' and var(bh['value'], shared['name']) and
            ba[0][1] == {'tag': 'bool', 'value': True}, 'inferred Bool shared use differs')
    consume = unused = None
    if name == 'identity':
        require(len(ba) == 1, 'identity application arity differs')
        case_path, case = args[1]
    else:
        unused_path, unused = lets[3]; consume_path, consume = lets[4]
        require(len(ba) == 2 and var(ba[1][1], unused['name']), 'complete dead nominal argument differs')
        ur = unused['value']
        require(ur['tag'] == 'application' and ur['argument']['tag'] == 'application' and
                ur['argument']['argument'] == {'tag': 'int64', 'value': 123}, 'unused application graph differs')
        passthrough(ur['function'], nominal, 'unused annotation')
        uf = ur['argument']['function']
        require(uf['tag'] == 'lambda' and uf['parameter_type'] == INT, 'unused source lambda differs')
        uh, _, ua = spine(uf['body'], unused_path + ['value', 'argument', 'function', 'body'])
        require(uh == cons and len(ua) == 2 and var(ua[0][1], uf['parameter']) and
                ua[1][1] == fields[1][1], 'unused lambda must retain actual Cons allocation')
        cr = consume['value']; typ = {'tag': 'arrow', 'from': nominal, 'to': INT}
        require(cr['tag'] == 'application' and cr['argument']['tag'] == 'lambda' and
                cr['argument']['parameter_type'] == nominal, 'ordinary consume lambda differs')
        passthrough(cr['function'], typ, 'consume annotation')
        local = cr['argument']['body']
        require(local['tag'] == 'let' and local['value']['tag'] == 'application' and
                var(local['value']['argument'], cr['argument']['parameter']), 'consume parameter owner differs')
        passthrough(local['value']['function'], nominal, 'consume parameter')
        case_path = consume_path + ['value', 'argument', 'body', 'body']; case = local['body']
        require(args[1][1]['tag'] == 'application' and var(args[1][1]['function'], consume['name']) and
                var(args[1][1]['argument'], xs['name']), 'consume must receive original list')
    require(case['tag'] == 'case' and case['result_type'] == INT and len(case['alternatives']) == 2,
            'original Int case differs')
    nil = one([a for a in case['alternatives'] if a['pattern']['constructor'] == nil_name], 'Nil alternative')
    arm = one([a for a in case['alternatives'] if a['pattern']['constructor'] == cons['name']], 'Cons alternative')
    fs = arm['pattern']['fields']; ah, _, aa = spine(arm['body'], [])
    require(nil['pattern']['fields'] == [] and nil['body'] == {'tag': 'int64', 'value': 0} and
            len(fs) == 2 and fs[0] is not None and fs[1] is None and ah['tag'] == 'primitive' and
            ah['name'] == 'addInt' and len(aa) == 2 and all(var(x, fs[0]) for _, x in aa),
            'selected case must use original field twice and ignore tail')
    nh, np, na = spine(case['scrutinee'], case_path + ['scrutinee'])
    require(nh['tag'] == 'type_application' and var(nh['value'], shared['name']) and
            len(na) == (1 if name == 'identity' else 2) and
            var(na[0][1], xs['name'] if name == 'identity' else local['name']),
            'inferred nominal shared use differs')
    if name != 'identity':
        require(na[1][1] == {'tag': 'bool', 'value': False}, 'curried second scalar argument differs')
    return dict(name=name, raw=raw, shared=shared, shared_path=shared_path,
        bonus=bonus, bonus_path=bonus_path + ['value'], xs=xs, xs_path=xs_path + ['value'],
        tail_path=fields[1][0], declaration=decl_index, nominal=nominal,
        case=case, case_path=case_path, bool_view=bp, nominal_view=np,
        bool_call=condition_path, nominal_call=case_path + ['scrutinee'],
        consume=consume, unused=unused,
        consume_path=None if consume is None else consume_path + ['value'],
        unused_path=None if unused is None else unused_path + ['value'])


def structure(capture, verified, plan, generated, name):
    f = source_facts(capture, name); p, m = plan['program'], plan['binding']['source_map']
    require(not any(isinstance(n, dict) and n.get('op') in ('hole', 'fill') for _, n in walk(p)),
            'nonrecursive fixtures must have no hole/Fill instructions')
    family = one(m['sum_map'], 'one exact IntList family'); atom = '%' + family['family']
    require(not m.get('nominal_map', []) and family['name'] == f['nominal']['name'] and
            family['declaration'] == f['declaration'] and p['families'][family['family']] ==
            {'variants': ['V0', 'V1'], 'fields': {'V0': [], 'V1': ['#i64', atom]}},
            'exact recursive nominal identity differs')
    case, arms = sum_case_structure(plan, f['case'], f['case_path'], family)
    meta = json.loads(check_metadata(p).metadata_json)
    scheme = one(m['scheme_map'], 'one shared Scheme'); definition = one(
        verified['fragment']['definitions'], 'one checked shared definition')
    width = 1 if name == 'identity' else 2
    require(len(p['schemes']) == 1 and scheme['binder'] == definition['binding']['id'] ==
            f['shared']['name']['id'] and p['schemes'][scheme['scheme']]['parameters'] == width and
            len(m['use_map']) == len(p['instantiations']) == len(verified['fragment']['uses']) == 2,
            'one original definition and complete vectors required')
    generic, seal = instruction(p, scheme['generalize']), instruction(p, scheme['seal'])
    pending = one([x for x in generic['body'] if x['op'] == 'application'], 'one original pending generic RHS')
    closures = {x['out']: x['function'] for x in generic['body'] if x['op'] == 'closure'}
    require(generic['op'] == 'generalize' and seal['op'] == 'seal' and pending['out'] == seal['value'] and
            not any(x['op'] == 'force' for x in generic['body']), 'generic RHS replaced or forced eagerly')
    carriers = [c for c in m['carrier_map'] if c['kind'] == 'lambda']
    raw_lambdas = [path for path, node in walk(f['raw']['body'], ['body'])
                   if isinstance(node, dict) and node.get('tag') == 'lambda']
    require(sorted(c['source']['path'] for c in carriers) == sorted(raw_lambdas) and
            len(carriers) == len(p['functions']) and
            sum(c['type_scope'] == scheme['scheme'] for c in carriers) == (3 if width == 1 else 5),
            'actual source lambdas lost, cloned or specialized')
    for key, side in (('function', 'function'), ('argument', 'argument')):
        c = one([c for c in carriers if c['source']['path'] == scheme['rhs_cursor']['path'] + [side]],
                'original generic lambda source')
        require(c['ir_code'] == closures[pending[key]] and c['type_scope'] == scheme['scheme'],
                'generic Code or lexical scope differs')
    vectors = {'bool': ['#bool'] if width == 1 else ['#bool', atom],
               'nominal': [atom] if width == 1 else [atom, '#bool']}
    uses = {}
    def type_shape(index):
        row = meta['types'][index]
        if row['tag'] == 'closed': return row['atom']
        require(row['tag'] == 'arrow' and row['protocol'] == 'repeat' and row['result_identity'] == 'unknown',
                'complete ordinary arrow contract differs')
        return [type_shape(row['argument']), type_shape(row['result'])]
    for label, path in (('bool', f['bool_view']), ('nominal', f['nominal_view'])):
        source = one([r for r in m['use_map'] if r['source'] == address(path)], 'exact source shared Use')
        vector = vectors[label]
        checked_use = one([r for r in verified['fragment']['uses'] if r['id'] == source['use']],
                          'independently replayed shared Use')
        raw_vector = [BOOL if atom == '#bool' else f['nominal'] for atom in vector]
        require(checked_use['source'] == source['source'] and checked_use['definition'] == definition['id'] and
                checked_use['arguments'] == raw_vector, 'replayed nominal Use/vector correspondence differs')
        require([p['types'][t]['layout'] for t in source['arguments']] == vector and
                source['definition'] == definition['id'], 'complete ordered nominal vector differs')
        uname = one([key for key, row in p['instantiations'].items() if row['scheme'] == scheme['scheme'] and
                     row['arguments'] == source['arguments']], 'unique complete instantiation')
        row = one([r for r in meta['uses'] if r['name'] == uname], 'exact Use metadata')
        occurrence = one(row['occurrences'], 'one upstream view acquisition')
        operation = instruction(p, occurrence); env = meta['environments'][row['env']]
        require(occurrence['root'] == 'entry' and operation['op'] == 'instantiate' and
                operation['instantiation'] == uname and env['mode'] == 'CLOSED' and
                [meta['types'][t]['atom'] for t in env['arguments']] == vector,
                'complete closed environment or upstream acquisition differs')
        expected = [vector[0], vector[0]] if width == 1 else [vector[0], [vector[1], vector[0]]]
        require(type_shape(row['result_type']) == expected, 'full substituted callable type differs')
        uses[label] = {'source': source, 'row': row, 'operation': operation, 'vector': vector}
    for table in ('functions', 'codes'):
        require(not any(isinstance(n, dict) and n.get('op') == 'instantiate'
                        for row in p[table].values() for _, n in walk(row['body'])),
                'callback-local view reconstruction is forbidden')
    alloc = lambda path, kind: source_allocation(plan, path, kind)
    xs = alloc(f['xs_path'], 'construct_sum'); tail = alloc(f['tail_path'], 'construct_nullary')
    bonus = alloc(f['bonus_path'], 'thunk')
    require(xs['family'] == tail['family'] == family['family'] and xs['variant'] == 'V1' and
            tail['variant'] == 'V0', 'constructor family/variant identity differs')
    definitions = [int(x) for x in re.findall(r'static Rt8Handle \*rt8_body_(\d+)\(', generated)]
    registrations = [(int(a), int(b)) for a, b in re.findall(
        r'\{ \.code_id = (\d+), \.body = rt8_body_(\d+) \}', generated)]
    require(definitions == list(range(len(meta['codes']))) and registrations == [(i, i) for i in definitions],
            'generated callback registrations differ')
    result = dict(facts=f, family=atom, metadata=meta, scheme=scheme, uses=uses,
        outer_code=closures[pending['function']], shared_code=closures[pending['argument']],
        seal_owner=seal['value'], bonus=bonus, xs=xs, tail=tail, case=case, arms=arms,
        bool_call=alloc(f['bool_call'], 'application'), nominal_call=alloc(f['nominal_call'], 'application'))
    if name == 'curried-const':
        first_path = scheme['rhs_cursor']['path'] + ['argument']
        first = at(f['raw'], first_path); first_local = first['body']
        child_path = first_path + ['body', 'body']; child = at(f['raw'], child_path)
        require(first['tag'] == 'lambda' and first_local['tag'] == 'let' and
                first_local['value']['tag'] == 'application' and
                var(first_local['value']['argument'], first['parameter']) and
                child['tag'] == 'lambda' and child['body']['tag'] == 'let' and
                child['body']['value']['tag'] == 'application' and
                var(child['body']['value']['argument'], child['parameter']) and
                var(child['body']['body'], first_local['name']), 'original curried source ownership differs')
        passthrough(first_local['value']['function'], first['parameter_type'], 'curried first parameter')
        passthrough(child['body']['value']['function'], child['parameter_type'], 'curried second parameter')
        child_carrier = one([c for c in carriers if c['source'] == address(child_path)], 'nested source carrier')
        child_op = alloc(child_path, 'closure')
        first_parameter = alloc(first_path + ['body', 'value'], 'application')
        capture = one(child_carrier['mono_captures'], 'nested first-argument capture')
        require(child_carrier['type_scope'] == scheme['scheme'] and not child_carrier['view_captures'] and
                child_op['function'] == child_carrier['ir_code'] and capture['binder'] == first_local['name']['id'] and
                child_op['captures'] == {capture['capture']: first_parameter['out']},
                'nested source Code/capture join differs')
        child_code = one([r for r in meta['codes'] if r['name'] == child_carrier['ir_code']], 'nested registered Code')
        child_site = one([r for r in meta['sites'] if r['code'] == child_code['id'] and r['category'] == 'CLOSURE'],
                         'nested closure Site')
        require(instruction(p, child_site['path']) == child_op and child_site['context'] ==
                {'kind': 'execution', 'code': one([r['id'] for r in meta['codes'] if r['name'] == result['shared_code']],
                 'creator Code'), 'scheme': uses['bool']['row']['scheme']}, 'nested creator Site context differs')
        child_executions = {}
        for label, use in uses.items():
            execution = one([r for r in meta['site_executions'] if r['site'] == child_site['id'] and
                             r['env'] == use['row']['env']], 'nested closed SiteExecution')
            code_execution = meta['code_executions'][execution['code_execution']]
            require(execution['origin_kind'] == 'INSTANCE' and code_execution['code'] == child_code['id'] and
                    code_execution['env'] == use['row']['env'] and
                    execution['principal_type'] == code_execution['callable_type'] and
                    code_execution['captures'] == [{'name': capture['capture'], 'relation': capture['relation'],
                                                   'type': meta['environments'][use['row']['env']]['arguments'][0]}],
                    'nested closed CodeExecution/capture type differs')
            child_executions[label] = execution
        result.update(child_op=child_op, child_site=child_site, child_code=child_code,
                      child_capture=capture, first_parameter=first_parameter, child_executions=child_executions)
        consume = alloc(f['consume_path'], 'application')
        consume_closure = alloc(f['consume_path'] + ['argument'], 'closure')
        carrier = one([c for c in carriers if c['source'] == address(f['consume_path'] + ['argument'])],
                      'consume carrier')
        view = one(carrier['view_captures'], 'consume full nominal view')
        u = uses['nominal']
        require(not carrier['mono_captures'] and carrier['type_scope'] is None and
                view['definition'] == u['source']['definition'] and view['occurrences'] == [u['source']['use']] and
                [p['types'][t]['layout'] for t in view['arguments']] == vectors['nominal'] and
                consume_closure['captures'] == {view['capture']: u['operation']['out']} and
                u['source']['source_view']['kind'] == 'captured', 'consume must retain the upstream complete nominal view')
        result.update(consume=consume, consume_closure=consume_closure, consume_view=view,
            consume_parameter=alloc(f['consume_path'] + ['argument', 'body', 'value'], 'application'),
            unused=alloc(f['unused_path'], 'application'),
            unused_inner=alloc(f['unused_path'] + ['argument'], 'application'),
            unused_closure=alloc(f['unused_path'] + ['argument', 'function'], 'closure'),
            bool_creator=alloc(f['bool_call'] + ['function'], 'application'),
            nominal_creator=alloc(f['nominal_call'] + ['function'], 'application'))
    return result


def observe(e, info):
    require(e['schema'] == 'resource-ir-v8-run/1' and e['state'] == e['fault'] == 0 and
            e['result'] == {'kind': 'i64', 'value': 42} and e['scalar_result_kind'] == 1 and
            e['scalar_result'] == 42 and e['events_omitted'] == 0 and
            e['events_emitted'] == len(e['events']) and e['metrics']['entries_completed'] == 1,
            'complete native Int42 report required')
    require(e['guards_failed_mask'] == 0 and e['guards_checked_mask'] == EXPECTED_GUARDS and
            e['guard_work_limit'] == 67_108_864 and 0 < e['guard_work_used'] <= e['guard_work_limit'],
            'native guard/work contract differs')
    ledger(e, True); events = e['events']; meta = info['metadata']
    selected = lambda kind: [(i, x) for i, x in enumerate(events) if x['event'] == kind]
    allocations = selected('allocate'); nodes = {x['node']: x for _, x in allocations}
    require(len(nodes) == len(allocations), 'duplicate node identity')
    def alloc(op):
        i, x = one([(i, x) for i, x in allocations if x['out'] == op['out']], 'one source allocation')
        require(x['opcode'] == op['op'] and x['code'] == (op['function'] if op['op'] == 'closure' else op.get('code')),
                'source allocation Code/opcode differs')
        return i, x
    def memo(node):
        return one([(i, x) for i, x in selected('memo_publish') if x['destination'] == node], 'one exact memo')
    invokes = lambda node: [(i, x) for i, x in selected('invoke_enter') if x['closure'] == node]
    returns = lambda node: [(i, x) for i, x in selected('invoke_raw_return') if x['closure'] == node]
    scalars = {x['node']: (x['kind'], x['value']) for _, x in selected('scalar_value')}
    _, xs = alloc(info['xs']); _, tail = alloc(info['tail']); _, bonus = alloc(info['bonus'])
    require(xs['slots'] == {'0': bonus['node'], '1': tail['node']} and not tail['slots'] and
            xs['layout'] == tail['layout'] == info['family'] and bonus['state'] == 'THUNK',
            'same original nominal owner and pending payload required')
    values = selected('sum_value')
    require(len(values) == 2 and {x['node'] for _, x in values} == {xs['node'], tail['node']},
            'unused or duplicate nominal constructor evaluated')
    for node, variant in ((xs, 1), (tail, 0)):
        _, value = one([(i, x) for i, x in values if x['node'] == node['node']], 'one exact nominal value')
        require(value['family'] == info['family'] and value['variant_index'] == variant and
                value['variant'] == 'V' + str(variant), 'exact nominal family/variant changed')
    begin_i, _ = one(selected('generic_begin'), 'one original generic RHS')
    seal_i, seal = one(selected('generic_seal'), 'one original generic seal')
    shared = seal['node']; pending = nodes[shared]
    body, outer = pending['slots']['$argument'], pending['slots']['$function']
    require(begin_i < seal_i and pending['state'] == 'APPLICATION' and pending['out'] == info['seal_owner'] and
            nodes[body]['code'] == info['shared_code'] and nodes[outer]['code'] == info['outer_code'] and
            sum(x['code'] == info['shared_code'] for _, x in allocations) == 1,
            'one original shared pending RHS/body required')
    shared_memo, shared_value = memo(shared)
    require(shared_value['result'] == body and len(invokes(outer)) == 1, 'neutral shared RHS must memo once')
    entry = one([x for _, x in selected('frame_enter') if x['context']['kind'] == 'entry'], 'entry frame')['frame']
    uses = selected('instantiate'); observed = {}
    require(len(uses) == 2, 'two complete views required')
    for label, wanted in info['uses'].items():
        i, x = one([(i, x) for i, x in uses if x['use'] == wanted['row']['id']], 'exact nominal Use event')
        before, after = meta['accesses'][x['old_access']], meta['accesses'][x['new_access']]
        require(x['node'] == shared and x['frame'] == entry and x['mode'] == 'own' and x['anchor'] is None and
                before['mode'] == 'SCHEME' and after['mode'] == 'MONO' and
                before['site'] == after['site'] == pending['site_id'] and
                before['origin_env'] == after['origin_env'] == pending['env_id'] != 0 and
                meta['environments'][after['origin_env']]['mode'] == 'NEUTRAL' and
                after['scheme'] is None and after['type'] == wanted['row']['result_type'] and
                after['use_env'] == wanted['row']['env'], 'full nominal Access/origin/capsule differs')
        observed[label] = {'event_index': i, 'origin_env': after['origin_env'],
            'use_env': after['use_env'], 'access': after['id'], 'vector': wanted['vector']}
    calls, raw_returns = invokes(body), returns(body)
    require(len(calls) == len(raw_returns) == 2 and shared_memo < calls[0][0] < calls[1][0] and
            scalars.get(calls[0][1]['argument']) == ('bool', True), 'shared body must run Bool then nominal')
    frames = [(i, x) for i, x in selected('frame_enter') if x['context'].get('name') == info['shared_code']]
    require(len(frames) == 2 and all(x['context'].get('node') == body for _, x in frames),
            'registered original shared callback differs')
    _, nominal_app = alloc(info['nominal_call']); _, bool_app = alloc(info['bool_call'])
    detail = {}
    if info['facts']['name'] == 'identity':
        require(calls[1][1]['argument'] == xs['node'] and
                nominal_app['slots'] == {'$function': shared, '$argument': xs['node']},
                'shared identity must receive same original nominal owner')
        for (_, call), (_, returned) in zip(calls, raw_returns):
            parameter = nodes[returned['result']]
            require(returned['argument'] == call['argument'] and parameter['state'] == 'APPLICATION' and
                    parameter['slots']['$argument'] == call['argument'], 'shared parameter owner chain differs')
    else:
        _, consume = alloc(info['consume']); _, consume_closure = alloc(info['consume_closure'])
        _, parameter = alloc(info['consume_parameter']); _, unused = alloc(info['unused'])
        _, unused_inner = alloc(info['unused_inner']); _, unused_closure = alloc(info['unused_closure'])
        require(consume['state'] == unused['state'] == unused_inner['state'] == 'APPLICATION' and
                consume_closure['env_id'] == 0 and consume_closure['slots'] ==
                {info['consume_view']['capture']: shared} and
                calls[1][1]['argument'] == parameter['node'] and parameter['slots']['$argument'] == xs['node'],
                'captured full nominal view or parameter owner changed')
        require(memo(consume['node'])[1]['result'] == consume_closure['node'] and
                len(invokes(consume_closure['node'])) == 1 and
                invokes(consume_closure['node'])[0][1]['argument'] == xs['node'],
                'ordinary captured-view consumer differs')
        forbidden = {unused['node'], unused_inner['node']}
        require(not any(x['node'] in forbidden for _, x in selected('update_pin')) and
                not invokes(unused_closure['node']) and
                not any(x['destination'] in forbidden for _, x in selected('memo_publish')),
                'dead nominal coordinate caused eager argument evaluation')
        children = [nodes[x['result']] for _, x in raw_returns]
        require(children[0]['node'] != children[1]['node'] and
                all(x['code'] == info['child_code']['name'] and x['out'] == info['child_op']['out'] and
                    x['site_id'] == info['child_site']['id'] and x['opcode'] == 'closure' and
                    x['state'] == 'CLOSURE' for x in children),
                'curried instances cloned Code or reused mutable closure')
        for label, (return_i, returned), child, (call_i, call), (creator_i, creator), expected_second in zip(
                ('bool', 'nominal'), raw_returns, children, calls, frames, (unused['node'], None)):
            child_calls, child_returns = invokes(child['node']), returns(child['node'])
            child_frame_i, child_frame = one([(i, x) for i, x in selected('frame_enter')
                if x['context'].get('node') == child['node']], 'one registered nested callback')
            child_alloc_i = one([i for i, x in allocations if x['node'] == child['node']], 'nested allocation event')
            require(len(child_calls) == len(child_returns) == 1 and return_i < child_calls[0][0] < child_returns[0][0] and
                    child['env_id'] == info['child_executions'][label]['env'] == observed[label]['use_env'] and
                    set(child['slots']) == {info['child_capture']['capture']} and
                    child['frame'] == creator['frame'] and call_i < creator_i < child_alloc_i < return_i and
                    child_calls[0][0] < child_frame_i < child_returns[0][0] and
                    child_frame['context']['kind'] == 'function' and
                    child_frame['context']['name'] == info['child_code']['name'],
                    'returned curried closure lost full INSTANCE environment or outlived owner')
            captured = nodes[next(iter(child['slots'].values()))]
            require(returned['argument'] == call['argument'] and captured['state'] == 'APPLICATION' and
                    captured['out'] == info['first_parameter']['out'] and captured['frame'] == creator['frame'] and
                    captured['slots']['$argument'] == call['argument'] and
                    child_returns[0][1]['result'] == captured['node'], 'curried capture lost original first argument')
            second = child_calls[0][1]['argument']
            require(second == expected_second if label == 'bool' else scalars.get(second) == ('bool', False),
                    'curried complete second argument differs')
            handoff = one([x for _, x in selected('closure_capture_handoff') if x['node'] == child['node']],
                          'one curried capture handoff')
            require(handoff['protocol'] == 'repeat' and set(handoff['owners']) == set(child['slots']),
                    'curried captured Reference handoff differs')
        require(memo(parameter['node'])[1]['result'] == xs['node'], 'nominal parameter memo changed original owner')
        detail = {'curried_children': [x['node'] for x in children], 'unused_nominal_owner': unused['node'],
                  'consumer_parameter': parameter['node']}
    require(memo(nominal_app['node'])[1]['result'] == xs['node'] and
            scalars.get(memo(bool_app['node'])[1]['result']) == ('bool', True), 'view memo changed exact result owner')
    case_i, factory = one(selected('case_fields_i64'), 'only selected Cons factory')
    arm = info['arms'][1]
    require(factory['scrutinee'] == xs['node'] and factory['family'] == info['family'] and
            factory['variant_index'] == 1 and factory['variant'] == 'V1' and
            factory['code'] == arm['code'] and factory['field_mask'] == 1 and
            factory['captures'] == {c['capture']: bonus['node'] for c in arm['field_captures']},
            'selected factory must retain original nominal payload')
    bonus_demand, _ = one([(i, x) for i, x in selected('update_pin') if x['node'] == bonus['node']], 'bonus demanded once')
    bonus_cb, _ = one([(i, x) for i, x in selected('callback_enter') if x['node'] == bonus['node']], 'bonus callback once')
    bonus_memo, bonus_result = memo(bonus['node'])
    require(case_i < bonus_demand < bonus_cb < bonus_memo and scalars.get(bonus_result['result']) == ('i64', 21),
            'pending nominal field must evaluate once after selection')
    return {'scalar': 42, 'shared_node': shared, 'shared_body': body, 'original_nominal_owner': xs['node'],
            'views': observed, 'bonus_node': bonus['node'], 'bonus_evaluations': 1,
            'memory': e['memory'], 'memory_categories': e['memory_categories'],
            'access_scope': 'Exact metadata, stored slots and guarded handoffs; no per-owner Access event trace.', **detail}


def copied_controls(evaluation, info):
    """Mutate copied observations only, never another target or its packet."""
    observe(evaluation, info); results = []
    def event(r, kind, predicate=lambda x: True):
        return one([x for x in r['events'] if x['event'] == kind and predicate(x)], 'copied control selector')
    def allocation(r, op): return event(r, 'allocate', lambda x: x['out'] == op['out'])
    def reject(name, change, guard):
        report = copy.deepcopy(evaluation); change(report); report['events_emitted'] = len(report['events'])
        try: observe(report, info)
        except AssertionError as exc:
            require(guard in str(exc), name + ' failed unrelated observer guard: ' + str(exc))
            results.append({'control': name, 'status': 'rejected', 'guard': guard})
        else: raise AssertionError(name + ' accepted copied corruption')
    reject('result', lambda r: r['result'].__setitem__('value', 41), 'complete native Int42')
    reject('nominal-field-owner', lambda r: allocation(r, info['xs'])['slots'].__setitem__('0', -1),
           'same original nominal owner')
    reject('nominal-family', lambda r: allocation(r, info['xs']).__setitem__('layout', '%foreign'),
           'same original nominal owner')
    reject('bonus-code', lambda r: allocation(r, info['bonus']).__setitem__('code', 'foreign'), 'source allocation Code')
    def wrong_origin(r):
        row = event(r, 'instantiate', lambda x: x['use'] == info['uses']['nominal']['row']['id'])
        row['old_access'] = row['new_access']
    reject('shared-origin', wrong_origin, 'full nominal Access')
    reject('view-node', lambda r: event(r, 'instantiate', lambda x: x['use'] == info['uses']['nominal']['row']['id'])
           .__setitem__('node', allocation(r, info['xs'])['node']), 'full nominal Access')
    reject('view-memo', lambda r: event(r, 'memo_publish', lambda x: x['destination'] == allocation(r, info['nominal_call'])['node'])
           .__setitem__('result', allocation(r, info['tail'])['node']), 'view memo changed exact result')
    reject('case-payload', lambda r: event(r, 'case_fields_i64')['captures'].__setitem__(
           info['arms'][1]['field_captures'][0]['capture'], -1), 'selected factory must retain')
    reject('case-family', lambda r: event(r, 'case_fields_i64').__setitem__('family', '%foreign'),
           'selected factory must retain')
    reject('case-mask', lambda r: event(r, 'case_fields_i64').__setitem__('field_mask', 0), 'selected factory must retain')
    reject('bonus-extra-callback', lambda r: r['events'].append(copy.deepcopy(event(r, 'callback_enter',
           lambda x: x['node'] == allocation(r, info['bonus'])['node']))), 'bonus callback once')
    reject('bonus-extra-memo', lambda r: r['events'].append(copy.deepcopy(event(r, 'memo_publish',
           lambda x: x['destination'] == allocation(r, info['bonus'])['node']))), 'one exact memo')
    reject('guard-cap', lambda r: r.__setitem__('guard_work_limit', 67_108_865), 'native guard/work')
    reject('guard-mask', lambda r: r.__setitem__('guards_checked_mask', (1 << 27) - 2), 'native guard/work')
    reject('unexpected-fill-coverage', lambda r: r.__setitem__('guards_checked_mask', (1 << 27) - 1), 'native guard/work')
    reject('live-ledger', lambda r: r['memory'].__setitem__('live_bytes', 1), 'ledger arithmetic differs')
    if info['facts']['name'] == 'curried-const':
        reject('captured-view-storage', lambda r: allocation(r, info['consume_closure'])['slots'].__setitem__(
               info['consume_view']['capture'], -1), 'captured full nominal view')
        reject('consumer-origin-env', lambda r: allocation(r, info['consume_closure']).__setitem__('env_id', 1),
               'captured full nominal view')
        reject('dead-nominal-demand', lambda r: r['events'].append(
               {'event': 'update_pin', 'node': allocation(r, info['unused'])['node']}), 'dead nominal coordinate')
        def child(r):
            body = next(x['node'] for x in r['events'] if x['event'] == 'allocate' and x['code'] == info['shared_code'])
            returned = next(x for x in r['events'] if x['event'] == 'invoke_raw_return' and x['closure'] == body)
            return next(x for x in r['events'] if x['event'] == 'allocate' and x['node'] == returned['result'])
        reject('curried-instance-env', lambda r: child(r).__setitem__('env_id', 0), 'returned curried closure lost')
        def wrong_both_codes(r):
            for row in r['events']:
                if row['event'] == 'allocate' and row['out'] == info['child_op']['out']:
                    row['code'] = info['outer_code']
        reject('both-curried-codes-substituted', wrong_both_codes, 'curried instances cloned Code')
        reject('curried-source-site', lambda r: child(r).__setitem__('site_id', -1), 'curried instances cloned Code')
        def wrong_child_callback(r):
            node = child(r)['node']
            event(r, 'frame_enter', lambda x: x['context'].get('node') == node)['context']['name'] = info['outer_code']
        reject('curried-callback-substituted', wrong_child_callback, 'returned curried closure lost')
        reject('curried-capture-owner', lambda r: child(r)['slots'].__setitem__(next(iter(child(r)['slots'])),
               allocation(r, info['xs'])['node']), 'curried capture lost original first argument')
    return results


def structure_controls(capture, verified, plan, generated, name):
    structure(capture, verified, plan, generated, name); results = []
    def reject(label, change, guard):
        c, v, p = copy.deepcopy(capture), copy.deepcopy(verified), copy.deepcopy(plan)
        change(c, v, p)
        try: structure(c, v, p, generated, name)
        except AssertionError as exc:
            require(guard in str(exc), label + ' failed unrelated guard: ' + str(exc))
            results.append({'control': label, 'status': 'rejected', 'guard': guard})
        else: raise AssertionError(label + ' accepted copied structural corruption')
    reject('normalization-dialect', lambda c, v, p: c['normalization'].__setitem__('policy',
           'shared-rank1-callable/' + ('2' if name == 'identity' else '1')), 'actual nominal-beta dialect')
    reject('unexpected-hole', lambda c, v, p: p['program']['entry'].append({'op': 'hole'}),
           'nonrecursive fixtures must have no hole/Fill')
    reject('family-identity', lambda c, v, p: p['binding']['source_map']['sum_map'][0].__setitem__('name', 'Foreign'),
           'exact recursive nominal identity')
    reject('definition-binder', lambda c, v, p: p['binding']['source_map']['scheme_map'][0].__setitem__('binder', -1),
           'one original definition and complete vectors')
    reject('duplicated-source-carrier', lambda c, v, p: p['binding']['source_map']['carrier_map'].append(
           copy.deepcopy(next(x for x in p['binding']['source_map']['carrier_map'] if x['kind'] == 'lambda'))),
           'actual source lambdas lost')
    reject('lost-complete-coordinate', lambda c, v, p: p['binding']['source_map']['use_map'][0]['arguments'].pop(),
           'complete ordered nominal vector')
    reject('replayed-use-coordinate', lambda c, v, p: v['fragment']['uses'][0]['arguments'].reverse()
           if name == 'curried-const' else v['fragment']['uses'][0].__setitem__('arguments', [INT]),
           'replayed nominal Use/vector correspondence')
    if name == 'curried-const':
        def wrong_capture(c, v, p):
            info = structure(c, v, p, generated, name)
            carrier = one([x for x in p['binding']['source_map']['carrier_map']
                           if x['source'] == address(info['facts']['consume_path'] + ['argument'])], 'consume control')
            carrier['view_captures'][0]['arguments'].reverse()
        reject('captured-vector-order', wrong_capture, 'consume must retain the upstream complete nominal view')
    return results


def run_case(args, output, env, name):
    inputs = output / (name + '-inputs'); inputs.mkdir()
    (inputs / 'SharedPoly.emlf').write_text(MODULES[name], encoding='utf-8')
    source = inputs / 'main.emlf'; source.write_text(SOURCES[name], encoding='utf-8')
    target = output / name
    build.run([sys.executable, '-B', str(BASE / 'run_source_v8.py'), str(source), '--module-root', str(inputs),
               '--ghc', args.ghc, '--cc', args.cc, '--output', str(target)], output, name,
        cwd=BASE, env=env, wall=1200, cpu=900, memory=16 << 30, termination_grace=15,
        stdout_limit=1 << 20, stderr_limit=1 << 20, file_limit=64 << 20)
    require(not bounded_read(output / (name + '.stderr'), 1 << 20), 'successful CLI stderr')
    result = read_json(target / 'result.json'); evaluation = read_json(target / 'native/run.stdout')
    require(result['status'] == 'complete' and result['failure_policy'] == 'retain' and
            result['native'] == evaluation and 'placement' not in result, 'fresh default CLI result differs')
    capture = read_json(target / 'capture.stdout'); verified = read_json(target / 'verification.json')
    plan = read_json(target / 'planned.json', 8 << 20)
    require(verified['fragment_admitted'] and verified['normalization_replay'] == 'all exact independent fields match' and
            capture['checked_type'] == INT and plan['binding']['mode'] == 'coarse-owned',
            'fresh checked source/replay/default placement differs')
    generated = bounded_read(target / 'native/ir8_runtime_generated.c', 8 << 20).decode()
    info = structure(capture, verified, plan, generated, name)
    row = {'case': name, 'status': 'passed', 'observation': observe(evaluation, info),
        'copied_report_controls': copied_controls(evaluation, info),
        'copied_structure_controls': structure_controls(capture, verified, plan, generated, name),
        'source_hashes': {'main.emlf': build.sha(SOURCES[name].encode()),
                          'SharedPoly.emlf': build.sha(MODULES[name].encode())}}
    build.save(target / 'nominal-shared-observations.json', row)
    print(name + ': PASS', flush=True); return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', required=True); parser.add_argument('--cc', default='cc')
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    output = args.output.absolute()
    require(output.resolve() == output and output != BASE.parents[2] and BASE.parents[2] not in output.parents,
            'output must be canonical, fresh and outside checkout')
    output.mkdir(parents=True, exist_ok=False); env = cli.environment(output)
    build.SUITE_DEADLINE = time.monotonic() + 2700; results = []
    try:
        for name in SOURCES: results.append(run_case(args, output, env, name))
    except BaseException as exc:
        try: build.save(output / 'failure.json', {'error': repr(exc), 'completed_cases': [r['case'] for r in results]})
        except BaseException as persistence: exc.add_note('Failure persistence also failed: ' + repr(persistence))
        raise
    build.save(output / 'results.json', results); return 0


if __name__ == '__main__': raise SystemExit(main())
