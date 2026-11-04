#!/usr/bin/env python3
"""Controlled genuine source qualification for closed-arrow shared arguments.

Source/metadata selectors are independent of compiler-generated binder numbers.
The four observers join actual returned nodes to their original source Sites,
Code and Env. Public events do not expose every Access or capsule; real-session
guard mutation tests provide separate evidence for those boundaries.
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
QUALIFICATION_READY = True
ACCESS_SCOPE = ('Source, exact metadata and guarded native handoffs are joined. '
                'Public events do not expose every owner Access or capsule. '
                'These four sources do not exercise dead type coordinates or nominal arrow leaves.')

FIXTURES = {'shared-id-arrow': {'main.emlf': 'import SharedPoly\nlet bonus = addInt 20 1 in\nlet helper = \\n -> addInt n bonus in\nlet returned = sharedId helper in\nif sharedId true then addInt (returned 0) (returned 0) else 0\n', 'SharedPoly.emlf': 'module SharedPoly (sharedId) where\nsharedId : forall a. a -> a\nsharedId x = x\n'}, 'shared-apply-arrow': {'main.emlf': 'import SharedPoly\nlet bonus = addInt 20 1 in\nlet helper = \\n -> addInt n bonus in\nlet use = \\f -> addInt (f 0) (f 0) in\nlet guard = \\n -> ltInt n 1 in\nif sharedApply guard 0 then sharedApply use helper else 0\n', 'SharedPoly.emlf': 'module SharedPoly (sharedApply) where\nsharedApply : forall a b. (a -> b) -> a -> b\nsharedApply f x = f x\n'}, 'shared-apply-instance': {'main.emlf': 'import SharedPoly\nlet bonus = addInt 20 1 in\nlet helper = \\n -> addInt n bonus in\nlet inner = sharedApply helper in\nlet returned = sharedApply (\\f -> f) inner in\nif ltInt (inner 0) 22 then addInt (returned 0) (returned 0) else 0\n', 'SharedPoly.emlf': 'module SharedPoly (sharedApply) where\nsharedApply : forall a b. (a -> b) -> a -> b\nsharedApply f x = f x\n'}, 'shared-id-instance': {'main.emlf': 'import SharedPoly\nlet bonus = addInt 20 1 in\nlet helper = \\n -> addInt n bonus in\nlet inner = sharedApply helper in\nlet returned = sharedId inner in\nif ltInt (inner 0) 22 then addInt (returned 0) (returned 0) else 0\n', 'SharedPoly.emlf': 'module SharedPoly (sharedApply, sharedId) where\nsharedApply : forall a b. (a -> b) -> a -> b\nsharedApply f x = f x\nsharedId : forall a. a -> a\nsharedId x = x\n'}}



def arrow(a, b):
    return {'tag': 'arrow', 'from': a, 'to': b}


FUNCTION = arrow(INT, INT)


def application(node, target, argument, label):
    require(node['tag'] == 'application' and var(node['function'], target) and
            node['argument'] == argument, label + ' ordinary application differs')


def generic_definition(path, binding, kind):
    current = binding['value']; cursor = path + ['value']; ids = []
    while current['tag'] == 'type_lambda':
        require(current['bound'] == {'tag': 'bottom'}, 'rank1 prefix bound differs')
        ids.append(current['id']); current = current['body']; cursor += ['body']
    require(len(ids) == (1 if kind == 'identity' else 2) and len(set(ids)) == len(ids),
            'complete original generic prefix differs')
    parameters = [{'tag': 'var', 'id': i} for i in ids]
    a = parameters[0]; b = parameters[-1]
    principal = arrow(a, a) if kind == 'identity' else arrow(arrow(a, b), arrow(a, b))
    require(current['tag'] == 'application', 'pending generic annotation application lost')
    passthrough(current['function'], principal, 'generic annotation')
    creator = current['argument']; cp = cursor + ['argument']
    require(creator['tag'] == 'lambda' and creator['parameter_type'] ==
            (a if kind == 'identity' else arrow(a, b)), 'generic creator signature differs')
    local = creator['body']
    require(local['tag'] == 'let' and local['value']['tag'] == 'application' and
            var(local['value']['argument'], creator['parameter']), 'first pending parameter wrapper lost')
    passthrough(local['value']['function'], creator['parameter_type'], 'first parameter')
    child = None; child_path = None
    if kind == 'identity':
        require(var(local['body'], local['name']), 'identity must return original parameter owner')
    else:
        child = local['body']; child_path = cp + ['body', 'body']
        require(child['tag'] == 'lambda' and child['parameter_type'] == a,
                'curried child signature differs')
        second = child['body']
        require(second['tag'] == 'let' and second['value']['tag'] == 'application' and
                var(second['value']['argument'], child['parameter']), 'second pending parameter wrapper lost')
        passthrough(second['value']['function'], a, 'second parameter')
        require(second['body']['tag'] == 'application' and var(second['body']['function'], local['name']) and
                var(second['body']['argument'], second['name']), 'ordinary generic callable application lost')
    return dict(kind=kind, binding=binding, path=path, ids=ids, cursor=cursor, principal=principal,
                creator=creator, creator_path=cp, local=local, child=child, child_path=child_path)


def source_facts(capture, case):
    require(case in FIXTURES, 'unknown controlled source case')
    n = capture['normalization']; raw = n['raw_normalized']
    policy = 'shared-rank1-callable/3' if case == 'shared-apply-instance' else 'shared-rank1-callable/1'
    require(capture['checked_type'] == INT and n['policy'] == policy and raw['tag'] == 'with_data' and
            all(n[k] for k in ('declarations_equal', 'erasure_equal', 'normalized_rechecked',
                               'original_rechecked', 'root_type_alpha_equal')),
            'complete current checked normalization required')
    # Exact producer steps are independently replayed. C's four-step order below
    # was established by its fresh /3 capture, never inferred from old /1 refusal.
    rows = []; current = raw['body']; path = ['body']
    while current['tag'] == 'let':
        rows.append((path, current)); current = current['body']; path = path + ['body']
    kinds = ['apply', 'identity'] if case == 'shared-id-instance' else [
        'identity' if case == 'shared-id-arrow' else 'apply']
    ordinary_count = 3 if case == 'shared-id-arrow' else 4
    require(len(rows) == len(kinds) + ordinary_count, 'original lexical bindings differ')
    definitions = [generic_definition(*row, kind) for row, kind in zip(rows, kinds)]
    roles = dict(zip(('bonus', 'helper', 'returned') if case == 'shared-id-arrow' else
                    ('bonus', 'helper', 'use', 'guard') if case == 'shared-apply-arrow' else
                    ('bonus', 'helper', 'inner', 'returned'), rows[len(kinds):]))
    bp, bonus = roles['bonus']; hp, helper = roles['helper']
    require(primitive(bonus['value'], 20, 1), 'original pending bonus differs')
    h = helper['value']
    require(h['tag'] == 'lambda' and h['parameter_type'] == INT, 'unannotated helper lambda differs')
    head, _, args = spine(h['body'], hp + ['value', 'body'])
    require(head['tag'] == 'primitive' and head['name'] == 'addInt' and len(args) == 2 and
            var(args[0][1], h['parameter']) and var(args[1][1], bonus['name']),
            'helper must add original parameter and captured pending bonus')
    head, _, branches = spine(current, path)
    require(head['tag'] == 'primitive' and head['name'] == 'ifThenElse' and head['arguments'] == [INT] and
            len(branches) == 3 and branches[2][1] == {'tag': 'int64', 'value': 0},
            'whole source conditional must remain lazy')
    condition_path, condition = branches[0]; then_path, then = branches[1]
    uses = {}; zero = {'tag': 'int64', 'value': 0}; helper_calls = []
    def use(role, source_path, source_node, definition, vector):
        require(source_node['tag'] == 'type_application' and
                var(source_node['value'], definitions[definition]['binding']['name']),
                role + ' must use the exact original generic binder')
        uses[role] = dict(path=source_path, definition=definition, vector=vector)
    if case == 'shared-id-arrow':
        rp, returned = roles['returned']; value = returned['value']
        require(value['tag'] == 'application' and var(value['argument'], helper['name']),
                'returned identity application must retain helper owner')
        use('returned', rp + ['value', 'function'], value['function'], 0, [FUNCTION])
        require(condition['tag'] == 'application' and condition['argument'] == {'tag': 'bool', 'value': True},
                'original scalar shared guard differs')
        use('guard', condition_path + ['function'], condition['function'], 0, [BOOL])
    elif case == 'shared-apply-arrow':
        up, consumer = roles['use']; gp, guard = roles['guard']; u = consumer['value']; g = guard['value']
        require(u['tag'] == 'lambda' and u['parameter_type'] == FUNCTION and
                g['tag'] == 'lambda' and g['parameter_type'] == INT, 'consumer/guard lambda types differ')
        ah, _, aa = spine(u['body'], up + ['value', 'body'])
        require(ah['tag'] == 'primitive' and ah['name'] == 'addInt' and len(aa) == 2,
                'consumer must add two ordinary callable results')
        for ap, app in aa:
            application(app, u['parameter'], zero, 'consumer helper call'); helper_calls.append(ap)
        gh, _, ga = spine(g['body'], gp + ['value', 'body'])
        require(gh['tag'] == 'primitive' and gh['name'] == 'ltInt' and len(ga) == 2 and
                var(ga[0][1], g['parameter']) and ga[1][1] == {'tag': 'int64', 'value': 1},
                'ordinary guard comparison differs')
        for role, node, node_path, first, second, vector in (
                ('guard', condition, condition_path, guard['name'], zero, [INT, BOOL]),
                ('consumer', then, then_path, consumer['name'], {'tag': 'var', 'name': helper['name']}, [FUNCTION, INT])):
            root, root_path, arguments = spine(node, node_path)
            require(len(arguments) == 2 and var(arguments[0][1], first) and arguments[1][1] == second,
                    role + ' source application spine differs')
            use(role, root_path, root, 0, vector)
    else:
        ip, inner = roles['inner']; rp, returned = roles['returned']; iv = inner['value']
        require(iv['tag'] == 'application' and var(iv['argument'], helper['name']),
                'inner shared partial must retain actual helper')
        use('inner', ip + ['value', 'function'], iv['function'], 0, [INT, INT])
        rv = returned['value']; root, root_path, arguments = spine(rv, rp + ['value'])
        if case == 'shared-id-instance':
            require(len(arguments) == 1 and var(arguments[0][1], inner['name']),
                    'foreign Scheme identity must receive original inner owner')
            use('returned', root_path, root, 1, [FUNCTION])
        else:
            require(len(arguments) == 2 and var(arguments[1][1], inner['name']),
                    'same Scheme application must receive original inner owner')
            passthrough(arguments[0][1], FUNCTION, 'normalized closed-arrow identity')
            use('returned', root_path, root, 0, [FUNCTION, FUNCTION])
        ch, _, ca = spine(condition, condition_path)
        require(ch['tag'] == 'primitive' and ch['name'] == 'ltInt' and len(ca) == 2 and
                ca[1][1] == {'tag': 'int64', 'value': 22}, 'initial inner demand must precede branch')
        application(ca[0][1], inner['name'], zero, 'initial inner demand')
    if case == 'shared-apply-instance':
        steps = n['steps']; outer_path = roles['returned'][0] + ['value','function']
        require(len(steps) == 4 and [x['arguments'] for x in steps] == [[FUNCTION],[FUNCTION],[INT],[INT]] and
                steps[0]['input']['path'] == outer_path and steps[1]['input']['path'] == outer_path + ['argument'] and
                all(x['rule'] == 'instantiate_direct_closed' and x['input']['state'] == i and
                    x['output']['state'] == i+1 for i,x in enumerate(steps)),
                'fresh outer-first closed-arrow normalization order differs')
    else:
        require(len(n['steps']) == 2 and all(x['arguments'] == [INT] for x in n['steps']),
                'original scalar normalization steps differ')
    returned_calls = []
    if case != 'shared-apply-arrow':
        ah, _, aa = spine(then, then_path)
        require(ah['tag'] == 'primitive' and ah['name'] == 'addInt' and len(aa) == 2,
                'returned callable must be invoked twice')
        for ap, app in aa:
            application(app, roles['returned'][1]['name'], zero, 'returned owner call'); returned_calls.append(ap)
    return dict(case=case, raw=raw, definitions=definitions, roles=roles, uses=uses,
                conditional_path=path, condition_path=condition_path, then_path=then_path,
                else_path=branches[2][0], helper_calls=helper_calls, returned_calls=returned_calls,
                normalization_policy=n['policy'], normalization_steps=len(n['steps']))


def raw_type(types, reference):
    row = types[reference]
    if row['tag'] == 'closed':
        atom = row.get('atom', row.get('layout'))
        require(atom in ('#i64', '#bool'), 'unexpected closed source coordinate')
        return INT if atom == '#i64' else BOOL
    require(row['tag'] == 'arrow' and row['protocol'] == 'repeat' and row['result_identity'] == 'unknown',
            'complete Repeat/unknown arrow contract required')
    return arrow(raw_type(types, row['argument']), raw_type(types, row['result']))


def structure(capture, verified, plan, generated, case):
    facts = source_facts(capture, case); p = plan['program']; m = plan['binding']['source_map']
    require(verified['fragment_admitted'] and verified['normalization_replay'] == 'all exact independent fields match',
            'fresh independent source/custody/proof replay required')
    require(not p['families'] and not p['layouts'] and not any(isinstance(n, dict) and
            n.get('op') in ('hole', 'fill', 'data', 'construct_sum', 'construct_nullary') for _, n in walk(p)),
            'source qualification must stay nonnominal and nonrecursive')
    fragment = verified['fragment']; expected_definitions = len(facts['definitions'])
    require(len(m['scheme_map']) == len(fragment['definitions']) == len(p['schemes']) == expected_definitions,
            'original generic definitions lost or cloned')
    meta = json.loads(check_metadata(p).metadata_json)
    schemes = []
    for definition_index, fact in enumerate(facts['definitions']):
        replay = one([x for x in fragment['definitions'] if x['binding_source'] == address(fact['path'])],
                     'actual source definition')
        row = one([x for x in m['scheme_map'] if x['definition'] == replay['id']], 'one lowered original Scheme')
        require(row['binder'] == replay['binding']['id'] == fact['binding']['name']['id'] and
                row['rhs_cursor'] == replay['rhs_cursor'] == address(fact['cursor']) and
                [x['id'] for x in replay['prefix']] == fact['ids'] and
                replay['body_type'] == fact['principal'] and
                p['schemes'][row['scheme']]['parameters'] == len(fact['ids']),
                'binder/full prefix/pending RHS principal correspondence differs')
        body = instruction(p, row['generalize']); sealed = instruction(p, row['seal'])
        pending = source_allocation(plan, fact['cursor'], 'application')
        require(body['op'] == 'generalize' and sealed == {'op': 'seal', 'value': pending['out']} and
                not any(isinstance(n, dict) and n.get('op') == 'force' for _, n in walk(body['body'])),
                'generic RHS graph must stay pending and unforced')
        schemes.append(dict(source=row, replay=replay, pending=pending))
    carriers = m['carrier_map']; lambdas = [c for c in carriers if c['kind'] == 'lambda']
    raw_lambdas = [path for path, node in walk(facts['raw']['body'], ['body'])
                   if isinstance(node, dict) and node.get('tag') == 'lambda']
    require(sorted(c['source']['path'] for c in lambdas) == sorted(raw_lambdas) and
            len(lambdas) == len(p['functions']) and len(carriers) == len(p['functions']) + len(p['codes']),
            'original callable carriers lost or cloned')
    terms = m['term_map']
    require(len({tuple(x['source']['path']) for x in terms}) == len(terms), 'duplicated ordinary source correspondence')
    for term in terms:
        node = at(facts['raw'], term['source']['path'])
        require(node['tag'] == term['tag'], 'ordinary source tag changed')
        if term['tag'] == 'application' and term['role'] == 'ordinary':
            source_allocation(plan, term['source']['path'], 'application')
    def carrier(path):
        return one([x for x in carriers if x['source'] == address(path) and x['kind'] == 'lambda'], 'exact lambda carrier')
    bp, bonus = facts['roles']['bonus']; hp, helper = facts['roles']['helper']
    bonus_op = source_allocation(plan, bp + ['value'], 'thunk')
    helper_op = source_allocation(plan, hp + ['value'], 'closure'); helper_carrier = carrier(hp + ['value'])
    helper_capture = one(helper_carrier['mono_captures'], 'one original helper bonus capture')
    require(helper_capture['binder'] == bonus['name']['id'] and not helper_carrier['view_captures'] and
            helper_carrier['type_scope'] is None and
            helper_op['captures'] == {helper_capture['capture']: bonus_op['out']},
            'ordinary helper must capture original pending bonus')
    require(len(m['use_map']) == len(fragment['uses']) == len(facts['uses']), 'complete shared Use census differs')
    uses = {}
    for role, expected in facts['uses'].items():
        row = one([x for x in m['use_map'] if x['source'] == address(expected['path'])], 'actual source Use')
        replay = one([x for x in fragment['uses'] if x['id'] == row['use']], 'independent full Use replay')
        scheme = schemes[expected['definition']]
        require(replay['source'] == row['source'] and replay['definition'] == row['definition'] == scheme['replay']['id'] and
                replay['arguments'] == expected['vector'] and
                [raw_type(p['types'], x) for x in row['arguments']] == expected['vector'],
                'ordered complete source Type vector differs')
        name = one([k for k, v in p['instantiations'].items() if
                    v == {'scheme': scheme['source']['scheme'], 'arguments': row['arguments']}], 'exact full instantiation')
        use = one([x for x in meta['uses'] if x['name'] == name], 'registered Use')
        env = meta['environments'][use['env']]
        require(env['mode'] == 'CLOSED' and env['arguments'] == use['arguments'] and
                [raw_type(meta['types'], x) for x in env['arguments']] == expected['vector'] and
                raw_type(meta['types'], use['result_type']) == replay['instantiated_type'],
                'Env/result must preserve complete arrow contracts and positions')
        operation = instruction(p, one(use['occurrences'], 'one upstream full instantiation'))
        require(operation['op'] == 'instantiate' and operation['instantiation'] == name,
                'full view must be instantiated before publication')
        uses[role] = dict(source=row, replay=replay, row=use, operation=operation)
    # Independent structural checks over every coordinate, including nested
    # children. Exact E0 mappings are not inferred from CLOSED/ARROW tags alone.
    pending = [t for u in uses.values() for t in u['row']['arguments']]; seen = set()
    while pending:
        index = pending.pop()
        if index in seen: continue
        seen.add(index); typ = meta['types'][index]
        resolution = one([x for x in meta['type_resolutions'] if x['type'] == index and x['env'] == 0], 'closed E0 resolution')
        require(resolution['result'] == index, 'closed coordinate E0 identity differs')
        if typ['tag'] == 'closed': continue
        require(typ['tag'] == 'arrow' and typ['protocol'] == 'repeat' and typ['result_identity'] == 'unknown' and
                typ['argument'] < index and typ['result'] < index, 'eligible closed arrow DAG differs')
        shape = one([x for x in meta['shapes'] if x['source'] == {'kind':'canonical-arrow','type':index}], 'canonical arrow Shape')
        sid = shape['id']; typing = meta['shape_typing'][sid]; rep = meta['representations'][sid]
        require(shape['kind'] == 'REPEAT' and typing['scope'] is None and typing['type'] == index and
                typing['shape'] == sid and rep['shape'] == sid and rep['typing'] == typing['id'] and
                rep['ready_kind'] == 'function', 'canonical arrow Shape/Typing/Representation differs')
        contract = meta['callable_contracts'][typing['contract']]
        require(all(contract[k] == typ[k] for k in ('argument','result','protocol','result_identity')) and
                contract['type'] == index, 'exact callable contract differs')
        for side in ('argument', 'result'):
            child = typ[side]
            cr = one([x for x in meta['type_resolutions'] if x['type'] == child and x['env'] == 0], 'child E0 resolution')
            rr = meta['representation_resolutions'][cr['id']]
            require(rr['representation'] == shape[side + '_rep'], 'exact canonical child representation differs')
            pending.append(child)
    for table in ('functions', 'codes'):
        require(not any(isinstance(n, dict) and n.get('op') == 'instantiate' for code in p[table].values() for _, n in walk(code['body'])),
                'callback must retain original shared view instead of recreating it')
    children = []
    for fact, scheme in zip(facts['definitions'], schemes):
        if fact['child'] is None: continue
        child = carrier(fact['child_path']); capture = one(child['mono_captures'], 'one pending callable child capture')
        operation = source_allocation(plan, fact['child_path'], 'closure')
        parameter = source_allocation(plan, fact['creator_path'] + ['body', 'value'], 'application')
        require(child['type_scope'] == scheme['source']['scheme'] and not child['view_captures'] and
                capture['binder'] == fact['local']['name']['id'] and capture['relation'] == 'down' and
                operation['captures'] == {capture['capture']: parameter['out']},
                'INSTANCE child must retain pending callable owner with original Down contract')
        code = one([x for x in meta['codes'] if x['name'] == child['ir_code']], 'registered curried child Code')
        site = one([x for x in meta['sites'] if x['code'] == code['id'] and x['category'] == 'CLOSURE'],
                   'curried child allocation Site')
        require(instruction(p, site['path']) == operation, 'curried child Site/source allocation differs')
        executions = {}
        for role, use in uses.items():
            if use['source']['definition'] != scheme['replay']['id']: continue
            vector = facts['uses'][role]['vector']
            se = one([x for x in meta['site_executions'] if x['site'] == site['id'] and x['env'] == use['row']['env']],
                     'full-vector child SiteExecution')
            ce = meta['code_executions'][se['code_execution']]
            require(se['origin_kind'] == 'INSTANCE' and ce['env'] == se['env'] and ce['code'] == code['id'] and
                    se['principal_type'] == ce['callable_type'] and
                    raw_type(meta['types'], ce['callable_type']) == arrow(*vector) and
                    raw_type(meta['types'], ce['argument']) == vector[0] and
                    raw_type(meta['types'], ce['result']) == vector[1] and
                    ce['captures'] == [{'name': capture['capture'], 'relation': 'down', 'type': ce['callable_type']}],
                    'resolved child argument/result/capture contract differs')
            executions[role] = se
        children.append(dict(carrier=child, capture=capture, operation=operation, parameter=parameter,
                             code=code, site=site, executions=executions))
    definitions = [int(x) for x in re.findall(r'static Rt8Handle \*rt8_body_(\d+)\(', generated)]
    registrations = [(int(a), int(b)) for a, b in re.findall(r'\{ \.code_id = (\d+), \.body = rt8_body_(\d+) \}', generated)]
    require(definitions == list(range(len(meta['codes']))) and registrations == [(i, i) for i in definitions],
            'real callback definitions/registrations lost or replaced')
    return dict(facts=facts, metadata=meta, schemes=schemes, uses=uses, helper_capture=helper_capture,
                helper=helper_op, bonus=bonus_op, carriers=carriers, children=children, coordinate_types=sorted(seen),
                program=p, allocation_map=m['allocation_map'])


def structure_controls(capture, verified, plan, generated, case):
    """Copied host records only; these are not native mutation controls."""
    results = []
    def reject(name, mutate, expected):
        c, v, p = copy.deepcopy(capture), copy.deepcopy(verified), copy.deepcopy(plan)
        g = mutate(c, v, p, generated)
        try:
            structure(c, v, p, g, case)
        except AssertionError as exc:
            require(expected in str(exc), name + ' rejected for an unexpected reason: ' + str(exc))
        else:
            raise AssertionError(name + ' corrupt copied structure accepted')
        results.append({'control': name, 'status': 'rejected'})
    def edit(fn):
        def mutate(c, v, p, g):
            fn(c, v, p)
            return g
        return mutate
    reject('wrong-generic-binder', edit(lambda c,v,p: p['binding']['source_map']['scheme_map'][0].__setitem__('binder', -1)),
           'binder/full prefix/pending RHS')
    reject('missing-vector-coordinate', edit(lambda c,v,p: p['binding']['source_map']['use_map'][0]['arguments'].pop()),
           'ordered complete source Type vector')
    def change_replay(c, v, p):
        row = v['fragment']['uses'][0]
        row['arguments'][0] = BOOL if row['arguments'][0] != BOOL else INT
    reject('wrong-replayed-coordinate', edit(change_replay), 'ordered complete source Type vector')
    reject('cloned-source-carrier', edit(lambda c,v,p: p['binding']['source_map']['carrier_map'].append(
        copy.deepcopy(p['binding']['source_map']['carrier_map'][0]))), 'original callable carriers lost or cloned')
    def helper_capture(c, v, p):
        f = source_facts(c, case); path = f['roles']['helper'][0] + ['value']
        row = one([x for x in p['binding']['source_map']['carrier_map'] if x['source'] == address(path)], 'control helper')
        row['mono_captures'][0]['binder'] = -1
    reject('lost-original-bonus-owner', edit(helper_capture), 'ordinary helper must capture original pending bonus')
    def change_bonus(c, v, p):
        f = source_facts(c, case)
        at(c['normalization']['raw_normalized'], f['roles']['bonus'][0])['value'] = {'tag':'int64','value':21}
    reject('eager-bonus-substitution', edit(change_bonus), 'original pending bonus differs')
    reject('generated-callback-substitution', lambda c,v,p,g: g.replace('.body = rt8_body_0 }', '.body = rt8_body_1 }', 1),
           'real callback definitions/registrations')
    if case == 'shared-apply-arrow':
        def transpose(c, v, p):
            f = source_facts(c, case)
            row = one([x for x in p['binding']['source_map']['use_map'] if x['source'] == address(f['uses']['consumer']['path'])],
                      'control distinct coordinates')
            row['arguments'].reverse()
        reject('transposed-distinct-coordinates', edit(transpose), 'ordered complete source Type vector')
    if case == 'shared-apply-instance':
        reject('inner-before-outer-normalization', edit(lambda c,v,p: c['normalization']['steps'].reverse()),
               'fresh outer-first closed-arrow normalization order')
    if case == 'shared-id-instance':
        def wrong_foreign_definition(c, v, p):
            f = source_facts(c, case)
            row = one([x for x in p['binding']['source_map']['use_map'] if x['source'] == address(f['uses']['returned']['path'])],
                      'control foreign definition')
            row['definition'] = 0
        reject('foreign-view-assigned-to-inner-scheme', edit(wrong_foreign_definition), 'ordered complete source Type vector')
    if case != 'shared-id-arrow':
        def upgrade_capture(c, v, p):
            f = source_facts(c, case); path = f['definitions'][0]['child_path']
            row = one([x for x in p['binding']['source_map']['carrier_map'] if x['source'] == address(path)], 'control generic child')
            row['mono_captures'][0]['relation'] = 'below'
        reject('unproved-callable-support-upgrade', edit(upgrade_capture), 'INSTANCE child must retain pending callable owner')
    return results


def checked_trace(e, info):
    require(e['schema'] == 'resource-ir-v8-run/1' and e['state'] == e['fault'] == 0 and
            e['result'] == {'kind':'i64','value':42} and e['scalar_result_kind'] == 1 and e['scalar_result'] == 42 and
            e['metrics']['entries_completed'] == 1 and e['events_omitted'] == 0 and
            e['events_emitted'] == len(e['events']), 'complete native Int42 report required')
    require(e['guards_failed_mask'] == 0 and e['guards_checked_mask'] == EXPECTED_GUARDS and
            e['guard_work_limit'] == 67_108_864 and 0 < e['guard_work_used'] <= e['guard_work_limit'],
            'native guard/work contract differs')
    ledger(e, True)
    events = e['events']; meta = info['metadata']; facts = info['facts']; p = info['program']
    selected = lambda kind: [(i,x) for i,x in enumerate(events) if x['event'] == kind]
    allocations = selected('allocate'); nodes = {x['node']:(i,x) for i,x in allocations}
    require(len(nodes) == len(allocations), 'duplicate allocated node identity')
    def by_op(op):
        return [(i,x) for i,x in allocations if x['out'] == op['out']]
    def alloc(op):
        return one(by_op(op), 'one original source allocation')
    def op(path, kind):
        return source_allocation({'program':p,'binding':{'source_map':{'allocation_map':info['allocation_map']}}},path,kind)
    def memo(node):
        return one([(i,x) for i,x in selected('memo_publish') if x['destination'] == node], 'one memo per demanded node')
    def calls(node):
        return [(i,x) for i,x in selected('invoke_enter') if x['closure'] == node]
    def returns(node):
        return [(i,x) for i,x in selected('invoke_raw_return') if x['closure'] == node]
    def scalar(node, kind, value):
        row = one([x for _,x in selected('scalar_value') if x['node'] == node], 'one exact scalar result')
        require((row['kind'],row['value']) == (kind,value), 'scalar node kind/value differs')
    def pending(node):
        return one([(i,x) for i,x in selected('update_pin') if x['node'] == node], 'one update of pending node')
    def callback(node):
        return one([(i,x) for i,x in selected('callback_enter') if x['node'] == node], 'one pending callback')
    def raw_return(node):
        return one([(i,x) for i,x in selected('raw_return') if x['source'] == node], 'one pending raw return')
    def frame(node, after, before):
        return one([(i,x) for i,x in selected('frame_enter') if after < i < before and
                    x['context'].get('node') == node], 'actual callback invocation frame')
    for ai,a in allocations:
        row = one([x for x in info['allocation_map'] if instruction(p,x['instruction'])['out'] == a['out']],
                  'allocation source instruction')
        instruction_row = instruction(p,row['instruction'])
        site = one([x for x in meta['sites'] if x['path'] == row['instruction']], 'allocation source Site')
        execution = one([x for x in meta['site_executions'] if x['site'] == a['site_id'] and x['env'] == a['env_id']],
                        'actual allocation SiteExecution')
        representation = meta['representations'][execution['representation']]
        require(a['site_id'] == site['id'] and a['opcode'] == instruction_row['op'] and
                a['code'] == (instruction_row['function'] if instruction_row['op'] == 'closure' else instruction_row.get('code')) and
                a['shape_id'] == representation['shape'] and
                ('type_id' not in a or a['type_id'] == execution['principal_type']) and
                any(i < ai and x['frame'] == a['frame'] for i,x in selected('frame_enter')),
                'allocation Site/Code/Env/representation identity differs')
        if a['opcode'] in ('closure','thunk'):
            require(set(a['slots']) == set(instruction_row.get('captures',{})), 'allocation capture field names differ')
        for name,target in a['slots'].items():
            si,s = one([(i,x) for i,x in selected('slot_install') if i < ai and x['host'] == a['node'] and
                        x['field'] == name], 'one original publication slot')
            require(s['target'] == target and target in nodes and nodes[target][0] < si and
                    s['host_group'] == a['group'] and s['target_group'] == nodes[target][1]['group'],
                    'allocation slot target identity differs')
    return dict(events=events, nodes=nodes, selected=selected, by_op=by_op, alloc=alloc, op=op,
                memo=memo, calls=calls, returns=returns, scalar=scalar, pending=pending,
                callback=callback, raw_return=raw_return, frame=frame)


def observe_identity_arrow(e, info):
    t = checked_trace(e,info)
    events=t['events']; nodes=t['nodes']; selected=t['selected']; by_op=t['by_op']; alloc=t['alloc']; op=t['op']
    memo=t['memo']; calls=t['calls']; returns=t['returns']; scalar=t['scalar']; pending=t['pending']
    callback=t['callback']; raw_return=t['raw_return']; frame=t['frame']
    meta=info['metadata']; facts=info['facts']; p=info['program']
    fact = facts['definitions'][0]; scheme = info['schemes'][0]
    _,shared = alloc(scheme['pending']); _,outer = alloc(op(fact['cursor']+['function'],'closure'))
    _,body = alloc(op(fact['creator_path'],'closure'))
    _,helper = alloc(info['helper']); _,bonus = alloc(info['bonus'])
    _,returned = alloc(op(facts['roles']['returned'][0]+['value'],'application'))
    _,guard = alloc(op(facts['condition_path'],'application'))
    _,conditional = alloc(op(facts['conditional_path'],'thunk'))
    def carrier_op(path, kind):
        carrier = one([x for x in info['carriers'] if x['source'] == address(path) and x['kind'] == kind],
                      'exact source thunk carrier')
        return one([instruction(p,x['instruction']) for x in info['allocation_map']
                    if x['source'] == address(path) and x['role'] == 'thunk' and
                    instruction(p,x['instruction'])['code'] == carrier['ir_code']], 'exact source thunk publication')
    _,then = alloc(carrier_op(facts['then_path'],'conditional-then'))
    _,otherwise = alloc(carrier_op(facts['else_path'],'conditional-else'))
    # Conditional-then and its primitive body share a source address but have
    # distinct carrier kinds and allocation outputs. Identify the actual chain.
    then_return_i,then_return = raw_return(then['node'])
    addition = nodes[then_return['result']][1]
    require(addition['state'] == 'THUNK' and addition['out'] == carrier_op(facts['then_path'],'primitive')['out'] and
            then_return['result_state'] == 'THUNK', 'selected branch must return its pending addition')
    conditional_carrier = one([c for c in info['carriers'] if c['source'] == address(facts['conditional_path']) and
                               c['kind'] == 'conditional'], 'original conditional carrier')
    view = one(conditional_carrier['view_captures'],'one complete scalar view capture')
    require(view['occurrences'] == [info['uses']['guard']['source']['use']] and
            view['arguments'] == info['uses']['guard']['source']['arguments'] and
            conditional['slots'][view['capture']] == shared['node'], 'conditional full shared view differs')
    require(shared['state'] == 'APPLICATION' and shared['slots'] == {'$function':outer['node'],'$argument':body['node']} and
            returned['slots'] == {'$function':shared['node'],'$argument':helper['node']} and
            guard['slots']['$function'] == shared['node'] and
            helper['slots'] == {info['helper_capture']['capture']:bonus['node']},
            'original generic/helper/pending graph differs')
    generic = one(meta['schemes'],'one Scheme metadata'); neutral = generic['neutral_env']
    require(shared['env_id'] == body['env_id'] == outer['env_id'] == neutral and helper['env_id'] == 0,
            'original neutral and concrete environments differ')
    helper_site = meta['sites'][helper['site_id']]
    helper_execution = one([x for x in meta['site_executions'] if x['site'] == helper_site['id'] and x['env'] == 0],
                           'original concrete helper execution')
    require(helper_site['context'] == {'kind':'concrete'} and helper_execution['origin_kind'] == 'CONCRETE',
            'helper origin must come from its original concrete allocation')
    begins = selected('generic_begin'); seals = selected('generic_seal')
    bi,begin = one(begins,'one generic introduction'); si,seal = one(seals,'one generic seal')
    require(begin['scheme'] == generic['id'] and begin['intro'] == generic['intro'] == seal['intro'] and
            begin['capsule'] == seal['capsule'] and begin['capsule'] > 0 and seal['node'] == shared['node'] and bi < si,
            'original shared capsule/introduction differs')
    instantiate = selected('instantiate'); require(len(instantiate) == 2,'two complete views required')
    for role,use in info['uses'].items():
        ii,event = one([(i,x) for i,x in instantiate if x['use'] == use['row']['id']], 'one source full view')
        old,new = meta['accesses'][event['old_access']],meta['accesses'][event['new_access']]
        require(si < ii < pending(shared['node'])[0] and event['node'] == shared['node'] and
                event['scheme'] == generic['id'] and event['mode'] == 'own' and event['anchor'] is None and
                old['mode'] == 'SCHEME' and old['scheme'] == generic['id'] and old['site'] == shared['site_id'] and
                old['origin_env'] == neutral and event['old_access'] == seal['new_access'] and
                new['mode'] == 'MONO' and new['site'] == shared['site_id'] and new['origin_env'] == neutral and
                new['use_env'] == use['row']['env'] and new['type'] == use['row']['result_type'],
                'shared view Access/Env/origin correspondence differs')
    smi,sm = memo(shared['node']); oi,oc = one(calls(outer['node']),'one generic annotation invocation')
    ori,orr = one(returns(outer['node']),'one generic annotation return')
    require(oc['argument'] == orr['argument'] == orr['result'] == body['node'] and
            sm['result'] == body['node'] and pending(shared['node'])[0] < oi < ori < smi,
            'one neutral generic RHS memo must return original body')
    body_calls = calls(body['node']); body_returns = returns(body['node'])
    require(len(body_calls) == len(body_returns) == 2 and
            [x['argument'] for _,x in body_calls] == [guard['slots']['$argument'],helper['node']],
            'same generic body must serve scalar then arrow demand')
    scalar(guard['slots']['$argument'],'bool',True)
    wrapper_op = op(fact['creator_path']+['body','value','function'],'closure')
    parameter_op = op(fact['creator_path']+['body','value'],'application')
    wrappers = []; parameters = []
    for role,(ci,call),(ri,ret) in zip(('guard','returned'),body_calls,body_returns):
        fi,fr = frame(body['node'],ci,ri)
        wi,wrapper = one([(i,x) for i,x in by_op(wrapper_op) if x['frame'] == fr['frame']], 'one closed parameter wrapper')
        pi,parameter = one([(i,x) for i,x in by_op(parameter_op) if x['frame'] == fr['frame']], 'one pending parameter application')
        wci,wcall = one(calls(wrapper['node']), 'one original parameter wrapper call')
        wri,wret = one(returns(wrapper['node']), 'one original parameter wrapper return')
        require(wrapper['env_id'] == parameter['env_id'] == info['uses'][role]['row']['env'] and
                wrapper['slots'] == {} and parameter['slots'] == {'$function':wrapper['node'],'$argument':call['argument']} and
                ret['argument'] == call['argument'] and ret['result'] == parameter['node'] and
                ci < fi < wi < pi < ri < pending(parameter['node'])[0] < wci < wri and
                wcall['argument'] == wret['argument'] == wret['result'] == call['argument'],
                'identity must preserve pending parameter then return original owner')
        outer_application = guard if role == 'guard' else returned
        omi,om = memo(outer_application['node']); pmi,pm = memo(parameter['node'])
        require(om['result'] == pm['result'] == call['argument'] and wri < omi < pmi,
                'identity reverse completion must memoize original returned node')
        wrappers.append(wrapper); parameters.append(parameter)
    require(len(by_op(wrapper_op)) == len(by_op(parameter_op)) == 2 and wrappers[0]['code'] == wrappers[1]['code'],
            'parameter wrapper Code must be shared across exact vectors')
    selection_i,selection = one(selected('select_i64'),'one original lazy conditional')
    require(selection['condition_node'] == guard['slots']['$argument'] and selection['condition_value'] is True and
            selection['then_node'] == selection['result'] == then['node'] and selection['else_node'] == otherwise['node'] and
            memo(guard['node'])[0] < selection_i < callback(then['node'])[0] < then_return_i,
            'scalar shared guard must select original pending then branch')
    require(not any(x.get('node') == otherwise['node'] for _,x in selected('update_pin')+selected('callback_enter')) and
            not any(x['destination'] == otherwise['node'] for _,x in selected('memo_publish')),
            'unselected branch must remain undemanded')
    call_allocations = [alloc(op(path,'application')) for path in facts['returned_calls']]
    helper_calls = calls(helper['node']); helper_returns = returns(helper['node'])
    require(len(helper_calls) == len(helper_returns) == 2 and len(by_op(info['helper'])) == 1,
            'original helper must be invoked twice without cloning')
    bonus_memo_i,bonus_memo = memo(bonus['node']); scalar(bonus_memo['result'],'i64',21)
    callback(bonus['node']); bonus_update_i,_ = pending(bonus['node'])
    results = []; thunks = []
    result_op = op(facts['roles']['helper'][0]+['value','body'],'thunk')
    for index,((ai,application_row),(ci,call),(ri,ret)) in enumerate(zip(call_allocations,helper_calls,helper_returns)):
        argument = application_row['slots']['$argument']; scalar(argument,'i64',0)
        require(application_row['slots']['$function'] == returned['node'] and
                call['argument'] == ret['argument'] == argument and memo(returned['node'])[0] < ci and ai < ci < ri,
                'two calls must reuse returned memo and original helper')
        _,fr = frame(helper['node'],ci,ri)
        ti,thunk = one([(i,x) for i,x in by_op(result_op) if x['frame'] == fr['frame']], 'one original helper result thunk')
        require(ret['result'] == thunk['node'] and ci < ti < ri < callback(thunk['node'])[0] and
                set(thunk['slots'].values()) == {bonus['node'],argument},
                'original helper result must retain argument and same bonus')
        _,raw = raw_return(thunk['node']); scalar(raw['result'],'i64',21)
        ami,am = memo(application_row['node']); tmi,tm = memo(thunk['node'])
        require(raw['result_state'] == 'READY' and am['result'] == tm['result'] == raw['result'] and ami < tmi,
                'ordinary helper result memo must preserve ready scalar')
        if index == 0:
            require(ri < bonus_update_i < bonus_memo_i < ami, 'first helper result must evaluate bonus once')
        else:
            require(bonus_memo_i < ci, 'second helper must reuse already memoized bonus')
        thunks.append(thunk); results.append(raw['result'])
    handoffs = [x for _,x in selected('closure_capture_handoff') if x['node'] == helper['node']]
    require(len(handoffs) == 2 and all(x['protocol'] == 'repeat' and
            set(x['owners']) == {info['helper_capture']['capture']} for x in handoffs),
            'each invocation must hand off original helper capture')
    require(len({x['owners'][info['helper_capture']['capture']] for x in handoffs}) == 2,
            'repeat helper needs fresh capture owners')
    for index,thunk in enumerate(thunks):
        slot = one([x for _,x in selected('slot_install') if x['host'] == thunk['node'] and x['target'] == bonus['node']],
                   'helper result retains original bonus')
        require(slot['target_state'] == ('THUNK' if index == 0 else 'MEMO'), 'bonus sharing state must progress once')
    _,final = raw_return(addition['node']); scalar(final['result'],'i64',42)
    require(final['result_state'] == 'READY' and all(memo(n)[1]['result'] == final['result'] for n in
            (conditional['node'],then['node'],addition['node'])), 'lazy conditional/addition final memo differs')
    expected_memos = {shared['node'],guard['node'],returned['node'],bonus['node'],conditional['node'],then['node'],addition['node']}
    expected_memos.update(x['node'] for x in parameters+thunks)
    expected_memos.update(x['node'] for _,x in call_allocations)
    require({x['destination'] for _,x in selected('memo_publish')} == expected_memos and
            len(selected('memo_publish')) == len(expected_memos), 'memo graph has unexpected evaluations')
    require([x['closure'] for _,x in selected('invoke_enter')] ==
            [outer['node'],body['node'],wrappers[0]['node'],body['node'],wrappers[1]['node'],helper['node'],helper['node']],
            'ordinary callback ordering or identity differs')
    require({x['node'] for _,x in selected('callback_enter')} ==
            {conditional['node'],then['node'],addition['node'],bonus['node'],*(x['node'] for x in thunks)} and
            len(selected('callback_enter')) == 6, 'pending callback graph differs')
    for kind,metric in (('allocate','nodes_allocated'),('invoke_enter','ordinary_calls'),
                        ('callback_enter','callback_calls'),('memo_publish','memo_writes'),('force_enter','force_calls')):
        require(len(selected(kind)) == e['metrics'][metric], 'event and runtime metric census differs')
    return {'status':'passed','case':facts['case'],'normalization_policy':facts['normalization_policy'],
            'normalization_steps':facts['normalization_steps'],'shared_node':shared['node'],'body_node':body['node'],
            'returned_application':returned['node'],'returned_original_helper':helper['node'],
            'helper_origin':'original-CONCRETE-E0-site','wrapper_envs':[x['env_id'] for x in wrappers],
            'helper_invocations':2,'bonus_evaluations':1,'bonus_node':bonus['node'],
            'events':len(events),'guard_work_used':e['guard_work_used'],'memory':e['memory'],
            'access_scope':ACCESS_SCOPE}


def identity_arrow_controls(evaluation, info):
    require(info['facts']['case'] == 'shared-id-arrow','native copied controls for this case are pending')
    original = observe(evaluation,info); results = []
    def reject(name, change, expected):
        altered = copy.deepcopy(evaluation); change(altered)
        try: observe(altered,info)
        except AssertionError as exc:
            require(expected in str(exc),name+' rejected for unexpected reason: '+str(exc))
        else: raise AssertionError(name+' copied corruption accepted')
        results.append({'control':name,'status':'rejected'})
    def event(r,kind,predicate=lambda x:True):
        return next(x for x in r['events'] if x['event']==kind and predicate(x))
    def allocation(r,node):return event(r,'allocate',lambda x:x['node']==node)
    def memo(r,node):return event(r,'memo_publish',lambda x:x['destination']==node)
    shared,body,helper,bonus,returned=(original[k] for k in
        ('shared_node','body_node','returned_original_helper','bonus_node','returned_application'))
    reject('wrong-scalar',lambda r:r['result'].__setitem__('value',41),'complete native Int42')
    reject('omitted-events',lambda r:r.__setitem__('events_omitted',1),'complete native Int42')
    reject('wrong-guard-mask',lambda r:r.__setitem__('guards_checked_mask',0),'native guard/work')
    reject('live-ledger',lambda r:r['memory'].__setitem__('live_bytes',1),'ledger')
    reject('wrong-shared-site',lambda r:allocation(r,shared).__setitem__('site_id',allocation(r,helper)['site_id']),
           'actual allocation SiteExecution')
    reject('wrong-helper-env',lambda r:allocation(r,helper).__setitem__('env_id',allocation(r,shared)['env_id']),
           'actual allocation SiteExecution')
    reject('wrong-helper-code',lambda r:allocation(r,helper).__setitem__('code',allocation(r,body)['code']),
           'allocation Site/Code/Env')
    reject('wrong-helper-capture',lambda r:allocation(r,helper)['slots'].__setitem__(info['helper_capture']['capture'],shared),
           'allocation slot target identity')
    reject('wrong-seal-node',lambda r:event(r,'generic_seal').__setitem__('node',helper),'original shared capsule')
    reject('wrong-capsule-join',lambda r:event(r,'generic_seal').__setitem__('capsule',-1),'original shared capsule')
    reject('wrong-view-node',lambda r:event(r,'instantiate').__setitem__('node',helper),'shared view Access/Env')
    reject('wrong-view-access',lambda r:event(r,'instantiate').__setitem__('new_access',event(r,'instantiate')['old_access']),
           'shared view Access/Env')
    reject('shared-memo-substitute',lambda r:memo(r,shared).__setitem__('result',helper),'one neutral generic RHS memo')
    reject('body-argument-substitute',lambda r:event(r,'invoke_enter',lambda x:x['closure']==body).__setitem__('argument',helper),
           'same generic body must serve')
    reject('premature-direct-owner-return',lambda r:event(r,'invoke_raw_return',lambda x:x['closure']==body and x['argument']==helper).__setitem__('result',helper),
           'identity must preserve pending parameter')
    reject('returned-memo-substitute',lambda r:memo(r,returned).__setitem__('result',body),
           'identity reverse completion')
    reject('helper-invocation-substitute',lambda r:event(r,'invoke_enter',lambda x:x['closure']==helper).__setitem__('closure',body),
           'same generic body must serve')
    reject('false-selection',lambda r:event(r,'select_i64').__setitem__('condition_value',False),'scalar shared guard')
    reject('wrong-selected-branch',lambda r:event(r,'select_i64').__setitem__('result',event(r,'select_i64')['else_node']),
           'scalar shared guard')
    def demand_false(r):
        r['events'].append({'event':'update_pin','node':event(r,'select_i64')['else_node'],'pin':-1,'depth':1})
        r['events_emitted']=len(r['events'])
    reject('demand-unselected-branch',demand_false,'unselected branch must remain')
    reject('wrong-bonus-value',lambda r:event(r,'scalar_value',lambda x:x['node']==memo(r,bonus)['result']).__setitem__('value',22),
           'scalar node kind/value')
    def bonus_reentry(r):
        r['events'].append(copy.deepcopy(event(r,'callback_enter',lambda x:x['node']==bonus)))
        r['events_emitted']=len(r['events'])
    reject('bonus-recomputed',bonus_reentry,'one pending callback')
    reject('wrong-capture-handoff',lambda r:event(r,'closure_capture_handoff',lambda x:x['node']==helper).__setitem__('owners',{}),
           'each invocation must hand off')
    reject('wrong-work-census',lambda r:r['metrics'].__setitem__('ordinary_calls',0),'event and runtime metric census')
    return results

def generic_trace(t, info):
    facts=info['facts']; meta=info['metadata']; selected=t['selected']; alloc=t['alloc']; op=t['op']
    pending=t['pending']; calls=t['calls']; returns=t['returns']; memo=t['memo']
    require(len(selected('generic_begin'))==len(selected('generic_seal'))==len(info['schemes']),
            'exact source generic introduction census required')
    require(len(selected('instantiate'))==len(info['uses']),'exact full shared view census required')
    generic_nodes=[]; generic_capsules=[]
    for gf,gs in zip(facts['definitions'],info['schemes']):
        gm=one([x for x in meta['schemes'] if x['name']==gs['source']['scheme']], 'original registered Scheme')
        _,gn=alloc(gs['pending']); _,go=alloc(op(gf['cursor']+['function'],'closure')); _,gb=alloc(op(gf['creator_path'],'closure'))
        bi,begin=one([(i,x) for i,x in selected('generic_begin') if x['scheme']==gm['id']], 'one original generic introduction')
        si,seal=one([(i,x) for i,x in selected('generic_seal') if x['intro']==gm['intro']], 'one original generic seal')
        require(begin['intro']==seal['intro']==gm['intro'] and begin['capsule']==seal['capsule']>0 and seal['node']==gn['node'] and bi<si and
                gn['env_id']==go['env_id']==gb['env_id']==gm['neutral_env'], 'original generic introduction/capsule differs')
        require(gn['slots']=={'$function':go['node'],'$argument':gb['node']}, 'original generic RHS application differs')
        for role,use in info['uses'].items():
            if use['source']['definition']!=gs['replay']['id']:continue
            ii,event=one([(i,x) for i,x in selected('instantiate') if x['use']==use['row']['id']], 'one complete source view')
            old,new=meta['accesses'][event['old_access']],meta['accesses'][event['new_access']]
            require(si<ii<pending(gn['node'])[0] and event['node']==gn['node'] and event['scheme']==gm['id'] and
                    event['mode']=='own' and event['anchor'] is None and event['old_access']==seal['new_access'] and
                    old['mode']=='SCHEME' and old['scheme']==gm['id'] and old['site']==gn['site_id'] and
                    old['origin_env']==gm['neutral_env'] and new['mode']=='MONO' and new['site']==gn['site_id'] and
                    new['origin_env']==gm['neutral_env'] and new['use_env']==use['row']['env'] and new['type']==use['row']['result_type'],
                    'full-vector Access/Env/origin correspondence differs')
        oi,oc=one(calls(go['node']),'one shared annotation invocation');ori,orr=one(returns(go['node']),'one annotation return')
        smi,sm=memo(gn['node'])
        require(oc['argument']==orr['argument']==orr['result']==gb['node'] and sm['result']==gb['node'] and oi<ori<smi,
                'one neutral pending RHS must memoize original shared body')
        generic_nodes.append((gn,go,gb));generic_capsules.append(begin['capsule'])
    require(len(set(generic_capsules))==len(generic_capsules),'distinct original Schemes require separate capsules')
    return generic_nodes,generic_capsules


def observe_instance(e, info):
    foreign = info['facts']['case'] == 'shared-id-instance'
    t=checked_trace(e,info)
    nodes=t['nodes']; selected=t['selected']; by_op=t['by_op']; alloc=t['alloc']; op=t['op']
    memo=t['memo']; calls=t['calls']; returns=t['returns']; scalar=t['scalar']; pending=t['pending']
    callback=t['callback']; raw_return=t['raw_return']; frame=t['frame']
    facts=info['facts']; meta=info['metadata']; p=info['program']; fact=facts['definitions'][0]
    scheme=info['schemes'][0]; generic=one([x for x in meta['schemes'] if x['name']==scheme['source']['scheme']], 'original apply Scheme')
    _,shared=alloc(scheme['pending']); _,outer=alloc(op(fact['cursor']+['function'],'closure'))
    _,body=alloc(op(fact['creator_path'],'closure')); _,helper=alloc(info['helper']); _,bonus=alloc(info['bonus'])
    ip=facts['roles']['inner'][0]+['value']; rp=facts['roles']['returned'][0]+['value']
    _,inner=alloc(op(ip,'application')); _,returned=alloc(op(rp,'application'))
    outer_partial = identity = None
    if not foreign:
        _,outer_partial=alloc(op(rp+['function'],'application'))
        _,identity=alloc(op(rp+['function','argument'],'closure'))
    require(shared['slots']=={'$function':outer['node'],'$argument':body['node']} and
            inner['slots']=={'$function':shared['node'],'$argument':helper['node']} and
            (foreign or (outer_partial['slots']=={'$function':shared['node'],'$argument':identity['node']} and
             returned['slots']=={'$function':outer_partial['node'],'$argument':inner['node']} and identity['slots']=={})) and
            helper['slots']=={info['helper_capture']['capture']:bonus['node']},
            'original inner/returned higher-order graph differs')
    neutral=generic['neutral_env']
    require(shared['env_id']==body['env_id']==outer['env_id']==neutral and helper['env_id']==0 and (foreign or identity['env_id']==0),
            'original generic and concrete origins differ')
    generic_nodes,generic_capsules=generic_trace(t,info)
    child_info=one(info['children'],'one generic child Code'); child_op=child_info['operation']
    first_wrapper_op=op(fact['creator_path']+['body','value','function'],'closure')
    first_parameter_op=child_info['parameter']; creators=calls(body['node']); creator_returns=returns(body['node'])
    require(len(creators)==len(creator_returns)==(1 if foreign else 2) and
            [x['argument'] for _,x in creators]==([helper['node']] if foreign else [helper['node'],identity['node']]),
            'same generic creator must receive original helper then identity')
    children={}; first_parameters={}; first_wrappers={}; creator_frontiers={}
    for role,(ci,call),(ri,ret),parent_application in zip(('inner',) if foreign else ('inner','returned'),creators,creator_returns,(inner,outer_partial)):
        fi,fr=frame(body['node'],ci,ri)
        wi,wrapper=one([(i,x) for i,x in by_op(first_wrapper_op) if x['frame']==fr['frame']], 'first callable parameter wrapper')
        pi,parameter=one([(i,x) for i,x in by_op(first_parameter_op) if x['frame']==fr['frame']], 'pending callable parameter')
        chi,child=one([(i,x) for i,x in by_op(child_op) if x['frame']==fr['frame']], 'original INSTANCE child')
        env=info['uses'][role]['row']['env']; execution=child_info['executions'][role]
        require(wrapper['env_id']==parameter['env_id']==child['env_id']==env and
                child['site_id']==child_info['site']['id'] and execution['origin_kind']=='INSTANCE' and
                child['slots']=={child_info['capture']['capture']:parameter['node']} and
                parameter['slots']=={'$function':wrapper['node'],'$argument':call['argument']} and wrapper['slots']=={} and
                ci<fi<wi<pi<chi<ri and ret['argument']==call['argument'] and ret['result']==child['node'],
                'INSTANCE allocation origin/Env/pending capture differs')
        mi,m=memo(parent_application['node'])
        require(ri<mi and m['result']==child['node'], 'creator result must memoize same original child')
        children[role]=child;first_parameters[role]=parameter;first_wrappers[role]=wrapper;creator_frontiers[role]=(ci,ri)
    original=children['inner']; transfer=children.get('returned')
    require(len(by_op(child_op))==(1 if foreign else 2) and (foreign or
            (original['node']!=transfer['node'] and original['code']==transfer['code'] and original['env_id']!=transfer['env_id'])), 'distinct full-vector children must share original Code')
    cp=fact['child_path']; second_wrapper_op=op(cp+['body','value','function'],'closure')
    second_parameter_op=op(cp+['body','value'],'application'); body_application_op=op(cp+['body','body'],'application')
    original_calls=calls(original['node']); original_returns=returns(original['node'])
    require(len(original_calls)==len(original_returns)==3,'original INSTANCE must be invoked before and twice after return')
    source_calls=[alloc(op(facts['condition_path']+['function','argument'],'application'))]+[
        alloc(op(path,'application')) for path in facts['returned_calls']]
    second_parameters=[]; second_wrappers=[]; body_applications=[]; helper_results=[]
    for index,((ai,application_row),(ci,call),(ri,ret)) in enumerate(zip(source_calls,original_calls,original_returns)):
        target=inner if index==0 else returned
        argument=application_row['slots']['$argument'];scalar(argument,'i64',0)
        require(application_row['slots']['$function']==target['node'] and call['argument']==ret['argument']==argument and ai<ci<ri,
                'source calls must reach exact original INSTANCE and argument')
        fi,fr=frame(original['node'],ci,ri)
        wi,wrapper=one([(i,x) for i,x in by_op(second_wrapper_op) if x['frame']==fr['frame']], 'original INSTANCE argument wrapper')
        pi,parameter=one([(i,x) for i,x in by_op(second_parameter_op) if x['frame']==fr['frame']], 'original INSTANCE pending argument')
        api,application_body=one([(i,x) for i,x in by_op(body_application_op) if x['frame']==fr['frame']], 'original INSTANCE ordinary body')
        require(wrapper['env_id']==parameter['env_id']==application_body['env_id']==original['env_id'] and
                wrapper['slots']=={} and parameter['slots']=={'$function':wrapper['node'],'$argument':argument} and
                application_body['slots']=={'$function':first_parameters['inner']['node'],'$argument':parameter['node']} and
                ci<fi<wi<pi<api<ri and ret['result']==application_body['node'],
                'returned INSTANCE callbacks must use original Env and pending callable capture')
        wci,wcall=one(calls(wrapper['node']),'one argument passthrough call');wri,wret=one(returns(wrapper['node']),'one argument passthrough return')
        require(wcall['argument']==wret['argument']==wret['result']==argument and wci<wri<memo(parameter['node'])[0] and
                memo(parameter['node'])[1]['result']==argument, 'pending ordinary argument wrapper differs')
        second_parameters.append(parameter);second_wrappers.append(wrapper);body_applications.append(application_body)
    if foreign:
        identity_fact=facts['definitions'][1]; identity_scheme=info['schemes'][1]
        _,identity_shared=alloc(identity_scheme['pending'])
        _,identity_outer=alloc(op(identity_fact['cursor']+['function'],'closure'))
        _,identity_body=alloc(op(identity_fact['creator_path'],'closure'))
        ici,icall=one(calls(identity_body['node']),'one foreign identity body invocation')
        iri,iret=one(returns(identity_body['node']),'one foreign identity body return')
        _,iframe=frame(identity_body['node'],ici,iri)
        identity_wrapper_op=op(identity_fact['creator_path']+['body','value','function'],'closure')
        identity_parameter_op=op(identity_fact['creator_path']+['body','value'],'application')
        _,twrapper=one([(i,x) for i,x in by_op(identity_wrapper_op) if x['frame']==iframe['frame']], 'foreign identity parameter wrapper')
        _,tparameter=one([(i,x) for i,x in by_op(identity_parameter_op) if x['frame']==iframe['frame']], 'foreign identity pending parameter')
        require(returned['slots']=={'$function':identity_shared['node'],'$argument':inner['node']} and
                identity_shared['slots']=={'$function':identity_outer['node'],'$argument':identity_body['node']} and
                icall['argument']==iret['argument']==inner['node'] and iret['result']==tparameter['node'] and
                twrapper['env_id']==tparameter['env_id']==info['uses']['returned']['row']['env'] and
                tparameter['slots']=={'$function':twrapper['node'],'$argument':inner['node']} and
                original['env_id']!=tparameter['env_id'],
                'foreign identity must retain original INSTANCE memo owner and distinct Env')
        twci,twcall=one(calls(twrapper['node']),'one foreign closed-arrow wrapper call')
        twri,twret=one(returns(twrapper['node']),'one foreign closed-arrow wrapper return')
        rmi,rm=memo(returned['node']);pmi,pm=memo(tparameter['node'])
        require(twcall['argument']==twret['argument']==twret['result']==inner['node'] and
                rm['result']==pm['result']==original['node'] and iri<twci<twri<rmi<pmi<original_calls[1][0],
                'foreign reverse completion must preserve original INSTANCE identity')
        later_creator_i=ici
    else:
        # The arrow-coordinate child runs in a different Env. Its ordinary
        # identity application returns the original inner memo owner.
        tci,tcall=one(calls(transfer['node']),'one higher-order transfer child invocation')
        tri,tret=one(returns(transfer['node']),'one higher-order transfer child return')
        _,tframe=frame(transfer['node'],tci,tri)
        _,twrapper=one([(i,x) for i,x in by_op(second_wrapper_op) if x['frame']==tframe['frame']], 'transfer parameter wrapper')
        _,tparameter=one([(i,x) for i,x in by_op(second_parameter_op) if x['frame']==tframe['frame']], 'transfer pending parameter')
        _,tapplication=one([(i,x) for i,x in by_op(body_application_op) if x['frame']==tframe['frame']], 'transfer ordinary application')
        require(tcall['argument']==tret['argument']==inner['node'] and tret['result']==tapplication['node'] and
                twrapper['env_id']==tparameter['env_id']==tapplication['env_id']==transfer['env_id'] and
                tparameter['slots']=={'$function':twrapper['node'],'$argument':inner['node']} and
                tapplication['slots']=={'$function':first_parameters['returned']['node'],'$argument':tparameter['node']},
                'higher-order transfer must retain original inner memo owner')
        ici,icall=one(calls(identity['node']),'one concrete identity invocation');iri,iret=one(returns(identity['node']),'one identity raw return')
        require(icall['argument']==iret['argument']==iret['result']==tparameter['node'] and tri<ici<iri,
                'concrete identity must return pending argument unchanged')
        twci,twcall=one(calls(twrapper['node']),'one closed-arrow parameter wrapper call')
        twri,twret=one(returns(twrapper['node']),'one closed-arrow parameter wrapper return')
        require(twcall['argument']==twret['argument']==twret['result']==inner['node'] and iri<twci<twri,
                'closed-arrow parameter wrapper must return original memo owner')
        rmi,rm=memo(returned['node']);ami,am=memo(tapplication['node']);pmi,pm=memo(tparameter['node'])
        require(rm['result']==am['result']==pm['result']==original['node'] and twri<rmi<ami<pmi<original_calls[1][0],
                'reverse completion must return original INSTANCE, never the transfer child')
        later_creator_i=creator_frontiers['returned'][0]
    for role,argument in ([('inner',helper)] if foreign else [('inner',helper),('returned',identity)]):
        wrapper=first_wrappers[role];parameter=first_parameters[role]
        ci,call=one(calls(wrapper['node']),'one first-parameter passthrough invocation')
        ri,ret=one(returns(wrapper['node']),'one first-parameter passthrough return')
        mi,m=memo(parameter['node'])
        require(call['argument']==ret['argument']==ret['result']==m['result']==argument['node'] and ci<ri<mi,
                'pending callable wrapper must memoize original callable')
    selection_i,selection=one(selected('select_i64'),'one original conditional')
    require(selection['condition_value'] is True and selection['result']==selection['then_node'] and
            original_returns[0][0]<selection_i<pending(returned['node'])[0]<later_creator_i and
            selection_i<original_calls[1][0]<original_calls[2][0],
            'initial INSTANCE demand must finish before later higher-order return')
    scalar(selection['condition_node'],'bool',True)
    comparison=nodes[selection['condition_node']][1]
    require(comparison['opcode']=='prim2' and
            one([x for _,x in selected('scalar_value') if x['node']==comparison['node']], 'comparison result')['primitive']=='ltInt',
            'initial demand must feed original less-than guard')
    require(not any(x.get('node')==selection['else_node'] for _,x in selected('update_pin')+selected('callback_enter')) and
            not any(x['destination']==selection['else_node'] for _,x in selected('memo_publish')),
            'unselected source branch must remain undemanded')
    helper_calls=calls(helper['node']);helper_returns=returns(helper['node'])
    require(len(helper_calls)==len(helper_returns)==3 and len(by_op(info['helper']))==1,
            'ordinary captured helper must be reused three times')
    bonus_memo_i,bonus_memo=memo(bonus['node']);scalar(bonus_memo['result'],'i64',21);callback(bonus['node'])
    bonus_update_i,_=pending(bonus['node']);result_op=op(facts['roles']['helper'][0]+['value','body'],'thunk')
    for index,((ci,call),(ri,ret),parameter,source_call,application_body) in enumerate(zip(
            helper_calls,helper_returns,second_parameters,source_calls,body_applications)):
        require(call['argument']==ret['argument']==parameter['node'] and original_returns[index][0]<ci<ri,
                'helper receives original pending argument wrapper')
        _,fr=frame(helper['node'],ci,ri)
        _,thunk=one([(i,x) for i,x in by_op(result_op) if x['frame']==fr['frame']], 'one concrete helper result')
        require(thunk['env_id']==0 and set(thunk['slots'].values())=={bonus['node'],parameter['node']} and ret['result']==thunk['node'],
                'original helper callback must use its concrete origin and captured bonus')
        rri,raw=raw_return(thunk['node']);scalar(raw['result'],'i64',21)
        require(raw['result_state']=='READY' and all(memo(n)[1]['result']==raw['result'] for n in
                (source_call[1]['node'],application_body['node'],thunk['node'])), 'three helper results must memoize exact scalars')
        if index==0:require(ri<bonus_update_i<bonus_memo_i<rri<selection_i,'bonus evaluated once during first inner demand')
        else:require(bonus_memo_i<ci,'later inner invocations must reuse bonus memo')
        slot=one([x for _,x in selected('slot_install') if x['host']==thunk['node'] and x['target']==bonus['node']],
                 'same bonus publication')
        require(slot['target_state']==('THUNK' if index==0 else 'MEMO'), 'bonus memo state differs')
        helper_results.append(thunk)
    handoffs=[x for _,x in selected('closure_capture_handoff') if x['node']==original['node']]
    require(len(handoffs)==3 and all(set(x['owners'])=={child_info['capture']['capture']} and x['protocol']=='repeat' for x in handoffs) and
            len({x['owners'][child_info['capture']['capture']] for x in handoffs})==3,
            'original INSTANCE must acquire fresh owners for same captured callable')
    require(len(by_op(child_op))==len(by_op(first_parameter_op))==(1 if foreign else 2) and
            len(by_op(second_parameter_op))==len(by_op(body_application_op))==(3 if foreign else 4),
            'actual generic graph must not be cloned or short-circuited')
    expected_calls={outer['node']:1,body['node']:(1 if foreign else 2),original['node']:3,
                    helper['node']:3,twrapper['node']:1}
    if foreign:
        expected_calls.update({identity_outer['node']:1,identity_body['node']:1})
    else:
        expected_calls.update({transfer['node']:1,identity['node']:1})
    expected_calls.update({x['node']:1 for x in list(first_wrappers.values())+second_wrappers})
    actual_calls={n:len(calls(n)) for n in {x['closure'] for _,x in selected('invoke_enter')}}
    require(actual_calls==expected_calls,'unexpected ordinary invocation identity/count')
    for kind,metric in (('allocate','nodes_allocated'),('invoke_enter','ordinary_calls'),
                        ('callback_enter','callback_calls'),('memo_publish','memo_writes'),('force_enter','force_calls')):
        require(len(selected(kind))==e['metrics'][metric],'event and runtime metric census differs')
    return {'status':'passed','case':facts['case'],'normalization_policy':facts['normalization_policy'],
            'normalization_steps':facts['normalization_steps'],'shared_node':shared['node'],'body_node':body['node'],
            'inner_application':inner['node'],'returned_application':returned['node'],
            'original_instance':original['node'],'original_env':original['env_id'],
            'transfer_instance':None if foreign else transfer['node'],
            'transfer_env':info['uses']['returned']['row']['env'],
            'return_kind':'foreign-Scheme' if foreign else 'same-Scheme',
            'generic_capsules':generic_capsules,
            'original_pending_callable':first_parameters['inner']['node'],'helper_node':helper['node'],'bonus_node':bonus['node'],
            'original_instance_invocations':3,'helper_invocations':3,'bonus_evaluations':1,
            'return_memo_event':rmi,'original_instance_call_events':[i for i,_ in original_calls],
            'events':len(e['events']),'guard_work_used':e['guard_work_used'],'memory':e['memory'],'access_scope':ACCESS_SCOPE}


def instance_controls(evaluation, info):
    original=observe_instance(evaluation,info);results=[]
    def reject(name,change,expected):
        altered=copy.deepcopy(evaluation);change(altered)
        try:observe_instance(altered,info)
        except AssertionError as exc:require(expected in str(exc),name+' rejected for unexpected reason: '+str(exc))
        else:raise AssertionError(name+' copied corruption accepted')
        results.append({'control':name,'status':'rejected'})
    def event(r,kind,predicate=lambda x:True):return next(x for x in r['events'] if x['event']==kind and predicate(x))
    def allocation(r,node):return event(r,'allocate',lambda x:x['node']==node)
    def memo(r,node):return event(r,'memo_publish',lambda x:x['destination']==node)
    shared,body,inner,returned,instance,transfer,helper,bonus=(original[k] for k in
        ('shared_node','body_node','inner_application','returned_application','original_instance','transfer_instance','helper_node','bonus_node'))
    reject('wrong-result',lambda r:r['result'].__setitem__('value',41),'complete native Int42')
    reject('truncated-trace',lambda r:r.__setitem__('events_omitted',1),'complete native Int42')
    reject('missing-guards',lambda r:r.__setitem__('guards_checked_mask',0),'native guard/work')
    reject('live-ledger',lambda r:r['memory'].__setitem__('live_blocks',1),'ledger')
    reject('wrong-view-node',lambda r:event(r,'instantiate').__setitem__('node',helper),'full-vector Access/Env')
    reject('wrong-view-access',lambda r:event(r,'instantiate').__setitem__('new_access',event(r,'instantiate')['old_access']),
           'full-vector Access/Env')
    reject('wrong-seal-capsule',lambda r:event(r,'generic_seal').__setitem__('capsule',-1),'original generic introduction/capsule')
    reject('shared-memo-replaced',lambda r:memo(r,shared).__setitem__('result',helper),'one neutral pending RHS')
    reject('inner-memo-replaced',lambda r:memo(r,inner).__setitem__('result',transfer),'creator result must memoize')
    reject('returned-transfer-not-original',lambda r:memo(r,returned).__setitem__('result',transfer),'reverse completion must return original INSTANCE')
    def relabel_origin(r):
        a,b=allocation(r,instance),allocation(r,transfer)
        for key in ('env_id','shape_id','type_id'):a[key]=b[key]
    reject('relabel-original-as-transfer-env',relabel_origin,'INSTANCE allocation origin/Env/pending capture')
    def lose_capture(r):
        a=allocation(r,instance);a['slots'][next(iter(a['slots']))]=helper
    reject('drop-pending-callable-capture',lose_capture,'allocation slot target identity')
    reject('clone-code-label',lambda r:allocation(r,instance).__setitem__('code',allocation(r,helper)['code']),
           'allocation Site/Code/Env')
    reject('inner-invocation-substitution',lambda r:event(r,'invoke_enter',lambda x:x['closure']==instance).__setitem__('closure',transfer),
           'original INSTANCE must be invoked')
    reject('helper-recomputed-node',lambda r:event(r,'invoke_enter',lambda x:x['closure']==helper).__setitem__('closure',instance),
           'original INSTANCE must be invoked')
    reject('skip-pending-child-body',lambda r:event(r,'invoke_raw_return',lambda x:x['closure']==instance).__setitem__('result',helper),
           'returned INSTANCE callbacks must use original Env')
    reject('wrong-transfer-argument',lambda r:event(r,'invoke_enter',lambda x:x['closure']==transfer).__setitem__('argument',instance),
           'higher-order transfer must retain original inner memo owner')
    reject('false-initial-guard',lambda r:event(r,'select_i64').__setitem__('condition_value',False),
           'initial INSTANCE demand must finish')
    reject('wrong-selected-branch',lambda r:event(r,'select_i64').__setitem__('result',event(r,'select_i64')['else_node']),
           'initial INSTANCE demand must finish')
    reject('wrong-bonus-value',lambda r:event(r,'scalar_value',lambda x:x['node']==memo(r,bonus)['result']).__setitem__('value',22),
           'scalar node kind/value')
    def duplicate_bonus(r):
        r['events'].append(copy.deepcopy(event(r,'callback_enter',lambda x:x['node']==bonus)));r['events_emitted']=len(r['events'])
    reject('duplicate-bonus-evaluation',duplicate_bonus,'one pending callback')
    reject('lost-instance-handoff',lambda r:event(r,'closure_capture_handoff',lambda x:x['node']==instance).__setitem__('owners',{}),
           'original INSTANCE must acquire fresh owners')
    reject('wrong-metric-census',lambda r:r['metrics'].__setitem__('ordinary_calls',0),'event and runtime metric census')
    return results


def observe_apply_arrow(e, info):
    t=checked_trace(e,info); facts=info['facts'];meta=info['metadata'];p=info['program']
    nodes=t['nodes'];selected=t['selected'];alloc=t['alloc'];op=t['op'];by_op=t['by_op'];memo=t['memo']
    calls=t['calls'];returns=t['returns'];frame=t['frame'];scalar=t['scalar'];pending=t['pending']
    callback=t['callback'];raw_return=t['raw_return']
    generic_nodes,capsules=generic_trace(t,info);shared,outer,body=one(generic_nodes,'one higher-order generic graph')
    fact=one(facts['definitions'],'one generic definition');child_info=one(info['children'],'one generic child Code')
    _,helper=alloc(info['helper']);_,bonus=alloc(info['bonus'])
    _,consumer=alloc(op(facts['roles']['use'][0]+['value'],'closure'))
    _,guard=alloc(op(facts['roles']['guard'][0]+['value'],'closure'))
    require(helper['env_id']==consumer['env_id']==guard['env_id']==0 and consumer['slots']==guard['slots']=={} and
            helper['slots']=={info['helper_capture']['capture']:bonus['node']},
            'original concrete helper/consumer/guard graph differs')
    paths={'guard':facts['condition_path'],'consumer':facts['then_path']}
    parents={role:alloc(op(path+['function'],'application'))[1] for role,path in paths.items()}
    applications={role:alloc(op(path,'application'))[1] for role,path in paths.items()}
    scalar(applications['guard']['slots']['$argument'],'i64',0)
    for role,argument in (('guard',guard),('consumer',consumer)):
        require(parents[role]['slots']=={'$function':shared['node'],'$argument':argument['node']} and
                applications[role]['slots']['$function']==parents[role]['node'],
                'original two-argument source application spine differs')
    require(applications['consumer']['slots']['$argument']==helper['node'], 'sharedApply must receive original helper as arrow argument')
    creators=calls(body['node']);creator_returns=returns(body['node'])
    require(len(creators)==len(creator_returns)==2 and [x['argument'] for _,x in creators]==[guard['node'],consumer['node']],
            'one shared generic body must serve guard then arrow consumer')
    first_wrapper_op=op(fact['creator_path']+['body','value','function'],'closure')
    first_parameter_op=child_info['parameter'];child_op=child_info['operation'];cp=fact['child_path']
    second_wrapper_op=op(cp+['body','value','function'],'closure')
    second_parameter_op=op(cp+['body','value'],'application');body_op=op(cp+['body','body'],'application')
    children={};first_parameters={};second_parameters={};body_applications={};wrappers=[];child_frontiers={}
    for role,(ci,call),(ri,ret),function in zip(('guard','consumer'),creators,creator_returns,(guard,consumer)):
        fi,fr=frame(body['node'],ci,ri)
        wi,wrapper=one([(i,x) for i,x in by_op(first_wrapper_op) if x['frame']==fr['frame']], 'first callable passthrough')
        pi,parameter=one([(i,x) for i,x in by_op(first_parameter_op) if x['frame']==fr['frame']], 'pending first callable')
        chi,child=one([(i,x) for i,x in by_op(child_op) if x['frame']==fr['frame']], 'returned higher-order INSTANCE')
        env=info['uses'][role]['row']['env']
        require(child['env_id']==wrapper['env_id']==parameter['env_id']==env and
                child['site_id']==child_info['site']['id'] and child_info['executions'][role]['origin_kind']=='INSTANCE' and
                wrapper['slots']=={} and parameter['slots']=={'$function':wrapper['node'],'$argument':function['node']} and
                child['slots']=={child_info['capture']['capture']:parameter['node']} and
                ret['argument']==function['node'] and ret['result']==child['node'] and ci<fi<wi<pi<chi<ri<memo(parents[role]['node'])[0] and
                memo(parents[role]['node'])[1]['result']==child['node'],
                'returned child must retain exact closed Env and pending callable')
        cci,ccall=one(calls(child['node']),'one returned child invocation');cri,cret=one(returns(child['node']),'one returned child raw result')
        cfi,cfr=frame(child['node'],cci,cri)
        swi,swrapper=one([(i,x) for i,x in by_op(second_wrapper_op) if x['frame']==cfr['frame']], 'second parameter wrapper')
        spi,sparameter=one([(i,x) for i,x in by_op(second_parameter_op) if x['frame']==cfr['frame']], 'pending second parameter')
        bai,body_application=one([(i,x) for i,x in by_op(body_op) if x['frame']==cfr['frame']], 'ordinary higher-order body application')
        argument=applications[role]['slots']['$argument']
        require(ri<cci<cfi<swi<spi<bai<cri and ccall['argument']==cret['argument']==argument and
                cret['result']==body_application['node'] and swrapper['env_id']==sparameter['env_id']==body_application['env_id']==env and
                swrapper['slots']=={} and sparameter['slots']=={'$function':swrapper['node'],'$argument':argument} and
                body_application['slots']=={'$function':parameter['node'],'$argument':sparameter['node']},
                'actual higher-order callback must preserve both pending parameters')
        wci,wcall=one(calls(wrapper['node']),'one first wrapper invocation');wri,wret=one(returns(wrapper['node']),'one first wrapper return')
        require(wcall['argument']==wret['argument']==wret['result']==memo(parameter['node'])[1]['result']==function['node'] and
                cri<wci<wri<memo(parameter['node'])[0], 'pending callable wrapper must resolve original concrete function')
        swci,swcall=one(calls(swrapper['node']),'one second wrapper invocation');swri,swret=one(returns(swrapper['node']),'one second wrapper return')
        require(swcall['argument']==swret['argument']==swret['result']==memo(sparameter['node'])[1]['result']==argument and swci<swri,
                'pending second wrapper must return original scalar or arrow owner')
        children[role]=child;first_parameters[role]=parameter;second_parameters[role]=sparameter
        body_applications[role]=body_application;wrappers.extend([wrapper,swrapper]);child_frontiers[role]=(cci,cri)
    require(len(by_op(child_op))==len(by_op(first_parameter_op))==len(by_op(second_parameter_op))==len(by_op(body_op))==2 and
            children['guard']['code']==children['consumer']['code'] and children['guard']['env_id']!=children['consumer']['env_id'],
            'one generic Code must serve both complete distinct vectors')
    gci,gcall=one(calls(guard['node']),'one concrete guard invocation');gri,gret=one(returns(guard['node']),'one guard raw return')
    require(gcall['argument']==gret['argument']==second_parameters['guard']['node'] and child_frontiers['guard'][1]<gci,
            'guard must receive original pending scalar argument')
    guard_result=nodes[gret['result']][1];_,guard_raw=raw_return(guard_result['node']);scalar(guard_raw['result'],'bool',True)
    require(guard_result['env_id']==0 and list(guard_result['slots'].values())==[second_parameters['guard']['node']] and
            guard_raw['result_state']=='READY' and all(memo(n)[1]['result']==guard_raw['result'] for n in
                (applications['guard']['node'],body_applications['guard']['node'],guard_result['node'])),
            'concrete guard must return the original checked comparison')
    si,selection=one(selected('select_i64'),'one outer source conditional')
    require(selection['condition_node']==guard_raw['result'] and selection['condition_value'] is True and
            selection['result']==selection['then_node'] and memo(applications['guard']['node'])[0]<si<creators[1][0],
            'guard must finish before selected arrow application is demanded')
    require(not any(x.get('node')==selection['else_node'] for _,x in selected('update_pin')+selected('callback_enter')) and
            not any(x['destination']==selection['else_node'] for _,x in selected('memo_publish')),
            'unselected source branch must stay undemanded')
    uci,ucall=one(calls(consumer['node']),'one original arrow consumer invocation')
    uri,uret=one(returns(consumer['node']),'one original arrow consumer return')
    _,uframe=frame(consumer['node'],uci,uri)
    consumer_result_op=op(facts['roles']['use'][0]+['value','body'],'thunk')
    _,consumer_result=one([(i,x) for i,x in by_op(consumer_result_op) if x['frame']==uframe['frame']], 'consumer pending addition')
    pending_helper=second_parameters['consumer']
    require(ucall['argument']==uret['argument']==pending_helper['node'] and uret['result']==consumer_result['node'] and
            consumer_result['env_id']==0 and list(consumer_result['slots'].values())==[pending_helper['node']] and
            uri<memo(pending_helper['node'])[0] and memo(pending_helper['node'])[1]['result']==helper['node'],
            'consumer must capture pending original helper owner before forcing it')
    source_calls=[alloc(op(path,'application')) for path in facts['helper_calls']]
    helper_calls=calls(helper['node']);helper_returns=returns(helper['node'])
    require(len(helper_calls)==len(helper_returns)==2 and len(by_op(info['helper']))==1,
            'original helper must be invoked twice without cloning')
    bmi,bm=memo(bonus['node']);scalar(bm['result'],'i64',21);callback(bonus['node']);bui,_=pending(bonus['node'])
    helper_result_op=op(facts['roles']['helper'][0]+['value','body'],'thunk');helper_results=[]
    for index,((ai,app),(ci,call),(ri,ret)) in enumerate(zip(source_calls,helper_calls,helper_returns)):
        argument=app['slots']['$argument'];scalar(argument,'i64',0)
        require(app['slots']['$function']==pending_helper['node'] and call['argument']==ret['argument']==argument and
                ai<ci<ri and memo(pending_helper['node'])[0]<ci,
                'consumer calls must reuse the same pending helper memo')
        _,fr=frame(helper['node'],ci,ri)
        _,result=one([(i,x) for i,x in by_op(helper_result_op) if x['frame']==fr['frame']], 'concrete helper addition')
        require(result['env_id']==0 and set(result['slots'].values())=={bonus['node'],argument} and ret['result']==result['node'],
                'returned helper callback must use original concrete origin and bonus')
        rri,raw=raw_return(result['node']);scalar(raw['result'],'i64',21)
        require(raw['result_state']=='READY' and memo(app['node'])[1]['result']==memo(result['node'])[1]['result']==raw['result'],
                'helper application must memoize its ready scalar')
        if index==0:require(ri<bui<bmi<rri,'first helper result evaluates bonus once')
        else:require(bmi<ci,'second helper must reuse original bonus memo')
        slot=one([x for _,x in selected('slot_install') if x['host']==result['node'] and x['target']==bonus['node']], 'same captured bonus slot')
        require(slot['target_state']==('THUNK' if index==0 else 'MEMO'),'bonus must transition once from pending to memo')
        helper_results.append(result)
    _,total=raw_return(consumer_result['node']);scalar(total['result'],'i64',42)
    require(total['result_state']=='READY' and all(memo(n)[1]['result']==total['result'] for n in
            (applications['consumer']['node'],body_applications['consumer']['node'],consumer_result['node'])),
            'ordinary higher-order consumer must return complete Int42 computation')
    expected_calls={outer['node']:1,body['node']:2,helper['node']:2,guard['node']:1,consumer['node']:1}
    expected_calls.update({x['node']:1 for x in list(children.values())+wrappers})
    require({n:len(calls(n)) for n in {x['closure'] for _,x in selected('invoke_enter')}}==expected_calls,
            'unexpected higher-order callback identity/count')
    for kind,metric in (('allocate','nodes_allocated'),('invoke_enter','ordinary_calls'),
                        ('callback_enter','callback_calls'),('memo_publish','memo_writes'),('force_enter','force_calls')):
        require(len(selected(kind))==e['metrics'][metric],'event and runtime metric census differs')
    return {'status':'passed','case':facts['case'],'normalization_policy':facts['normalization_policy'],
            'normalization_steps':facts['normalization_steps'],'shared_node':shared['node'],'body_node':body['node'],
            'guard_child':children['guard']['node'],'guard_env':children['guard']['env_id'],
            'consumer_child':children['consumer']['node'],'consumer_env':children['consumer']['env_id'],
            'consumer_node':consumer['node'],'helper_node':helper['node'],'pending_helper':pending_helper['node'],
            'bonus_node':bonus['node'],'helper_invocations':2,'bonus_evaluations':1,'events':len(e['events']),
            'guard_work_used':e['guard_work_used'],'memory':e['memory'],'access_scope':ACCESS_SCOPE}


def apply_arrow_controls(evaluation, info):
    original=observe_apply_arrow(evaluation,info);results=[]
    def reject(name,change,expected):
        r=copy.deepcopy(evaluation);change(r)
        try:observe_apply_arrow(r,info)
        except AssertionError as exc:require(expected in str(exc),name+' rejected for unexpected reason: '+str(exc))
        else:raise AssertionError(name+' copied corruption accepted')
        results.append({'control':name,'status':'rejected'})
    def event(r,kind,predicate=lambda x:True):return next(x for x in r['events'] if x['event']==kind and predicate(x))
    def allocation(r,node):return event(r,'allocate',lambda x:x['node']==node)
    def memo(r,node):return event(r,'memo_publish',lambda x:x['destination']==node)
    shared,body,helper,bonus,child,pending_helper,consumer=(original[k] for k in
        ('shared_node','body_node','helper_node','bonus_node','consumer_child','pending_helper','consumer_node'))
    reject('wrong-result',lambda r:r['result'].__setitem__('value',41),'complete native Int42')
    reject('omitted-events',lambda r:r.__setitem__('events_omitted',1),'complete native Int42')
    reject('wrong-guards',lambda r:r.__setitem__('guards_checked_mask',0),'native guard/work')
    reject('live-ledger',lambda r:r['memory'].__setitem__('live_bytes',1),'ledger')
    reject('wrong-view-access',lambda r:event(r,'instantiate').__setitem__('new_access',event(r,'instantiate')['old_access']),
           'full-vector Access/Env')
    reject('wrong-view-node',lambda r:event(r,'instantiate').__setitem__('node',helper),'full-vector Access/Env')
    reject('wrong-shared-memo',lambda r:memo(r,shared).__setitem__('result',helper),'one neutral pending RHS')
    reject('wrong-body-argument',lambda r:event(r,'invoke_enter',lambda x:x['closure']==body).__setitem__('argument',helper),
           'one shared generic body must serve')
    def swap_child_env(r):
        a,b=allocation(r,child),allocation(r,original['guard_child'])
        for key in ('env_id','shape_id','type_id'):a[key]=b[key]
    reject('swapped-closed-child-contract',swap_child_env,'returned child must retain exact closed Env')
    reject('wrong-actual-child-argument',lambda r:event(r,'invoke_enter',lambda x:x['closure']==child).__setitem__('argument',consumer),
           'actual higher-order callback must preserve')
    reject('wrong-pending-helper-result',lambda r:memo(r,pending_helper).__setitem__('result',consumer),
           'pending second wrapper must return original scalar or arrow owner')
    reject('wrong-consumer-argument',lambda r:event(r,'invoke_enter',lambda x:x['closure']==consumer).__setitem__('argument',helper),
           'consumer must capture pending original helper')
    reject('helper-invocation-substitution',lambda r:event(r,'invoke_enter',lambda x:x['closure']==helper).__setitem__('closure',consumer),
           'one original arrow consumer invocation')
    reject('wrong-branch',lambda r:event(r,'select_i64').__setitem__('result',event(r,'select_i64')['else_node']),
           'guard must finish before selected')
    reject('false-guard',lambda r:event(r,'select_i64').__setitem__('condition_value',False),'guard must finish before selected')
    reject('wrong-bonus-value',lambda r:event(r,'scalar_value',lambda x:x['node']==memo(r,bonus)['result']).__setitem__('value',22),
           'scalar node kind/value')
    def repeat_bonus(r):
        r['events'].append(copy.deepcopy(event(r,'callback_enter',lambda x:x['node']==bonus)));r['events_emitted']=len(r['events'])
    reject('recomputed-bonus',repeat_bonus,'one pending callback')
    reject('wrong-census',lambda r:r['metrics'].__setitem__('ordinary_calls',0),'event and runtime metric census')
    return results


def foreign_instance_controls(evaluation, info):
    original=observe_instance(evaluation,info);results=[]
    def reject(name,change,expected):
        r=copy.deepcopy(evaluation);change(r)
        try:observe_instance(r,info)
        except AssertionError as exc:require(expected in str(exc),name+' rejected for unexpected reason: '+str(exc))
        else:raise AssertionError(name+' copied corruption accepted')
        results.append({'control':name,'status':'rejected'})
    def event(r,kind,predicate=lambda x:True):return next(x for x in r['events'] if x['event']==kind and predicate(x))
    def allocation(r,node):return event(r,'allocate',lambda x:x['node']==node)
    def memo(r,node):return event(r,'memo_publish',lambda x:x['destination']==node)
    shared,body,instance,inner,returned,helper,bonus=(original[k] for k in
        ('shared_node','body_node','original_instance','inner_application','returned_application','helper_node','bonus_node'))
    foreign_shared=allocation(evaluation,returned)['slots']['$function']
    foreign_body=memo(evaluation,foreign_shared)['result']
    foreign_ret=event(evaluation,'invoke_raw_return',lambda x:x['closure']==foreign_body)
    foreign_parameter=foreign_ret['result']
    foreign_wrapper=allocation(evaluation,foreign_parameter)['slots']['$function']
    reject('wrong-result',lambda r:r['result'].__setitem__('value',41),'complete native Int42')
    reject('omitted-events',lambda r:r.__setitem__('events_omitted',1),'complete native Int42')
    reject('wrong-guards',lambda r:r.__setitem__('guards_checked_mask',0),'native guard/work')
    reject('live-ledger',lambda r:r['memory'].__setitem__('live_bytes',1),'ledger')
    def collapse_capsules(r):
        begins=[x for x in r['events'] if x['event']=='generic_begin'];seals=[x for x in r['events'] if x['event']=='generic_seal']
        begins[1]['capsule']=begins[0]['capsule'];seals[1]['capsule']=seals[0]['capsule']
    reject('collapse-distinct-capsules',collapse_capsules,'distinct original Schemes require separate capsules')
    reject('foreign-view-on-inner-scheme',lambda r:event(r,'instantiate',lambda x:x['node']==foreign_shared).__setitem__('node',shared),
           'full-vector Access/Env')
    reject('foreign-view-access',lambda r:event(r,'instantiate',lambda x:x['node']==foreign_shared).__setitem__('new_access',
           event(r,'instantiate',lambda x:x['node']==shared)['new_access']),'full-vector Access/Env')
    reject('foreign-neutral-memo-substitution',lambda r:memo(r,foreign_shared).__setitem__('result',body),'one neutral pending RHS')
    reject('original-child-memo-substitution',lambda r:memo(r,inner).__setitem__('result',helper),'creator result must memoize')
    reject('return-wrong-instance',lambda r:memo(r,returned).__setitem__('result',foreign_body),
           'foreign reverse completion must preserve original INSTANCE identity')
    reject('foreign-wrapper-returns-new-owner',lambda r:event(r,'invoke_raw_return',lambda x:x['closure']==foreign_wrapper).__setitem__('result',instance),
           'foreign reverse completion must preserve original INSTANCE identity')
    reject('foreign-body-skips-pending-return',lambda r:event(r,'invoke_raw_return',lambda x:x['closure']==foreign_body).__setitem__('result',inner),
           'foreign identity must retain original INSTANCE memo owner')
    reject('lost-instance-capture',lambda r:allocation(r,instance)['slots'].__setitem__(next(iter(allocation(r,instance)['slots'])),helper),
           'allocation slot target identity')
    reject('wrong-original-instance-env',lambda r:allocation(r,instance).__setitem__('env_id',original['transfer_env']),
           'actual allocation SiteExecution')
    reject('invoke-foreign-instead-of-original',lambda r:event(r,'invoke_enter',lambda x:x['closure']==instance).__setitem__('closure',foreign_body),
           'original INSTANCE must be invoked')
    reject('wrong-original-instance-body',lambda r:event(r,'invoke_raw_return',lambda x:x['closure']==instance).__setitem__('result',helper),
           'returned INSTANCE callbacks must use original Env')
    reject('false-initial-guard',lambda r:event(r,'select_i64').__setitem__('condition_value',False),'initial INSTANCE demand must finish')
    reject('wrong-bonus-value',lambda r:event(r,'scalar_value',lambda x:x['node']==memo(r,bonus)['result']).__setitem__('value',22),
           'scalar node kind/value')
    def repeat_bonus(r):
        r['events'].append(copy.deepcopy(event(r,'callback_enter',lambda x:x['node']==bonus)));r['events_emitted']=len(r['events'])
    reject('bonus-recomputed',repeat_bonus,'one pending callback')
    reject('wrong-original-capture-handoff',lambda r:event(r,'closure_capture_handoff',lambda x:x['node']==instance).__setitem__('owners',{}),
           'original INSTANCE must acquire fresh owners')
    reject('wrong-census',lambda r:r['metrics'].__setitem__('ordinary_calls',0),'event and runtime metric census')
    return results


def observe(evaluation, info):
    if info['facts']['case'] == 'shared-id-arrow':
        return observe_identity_arrow(evaluation,info)
    if info['facts']['case'] in ('shared-apply-instance','shared-id-instance'):
        return observe_instance(evaluation,info)
    if info['facts']['case'] == 'shared-apply-arrow':
        return observe_apply_arrow(evaluation,info)
    raise AssertionError('unknown source observation case')


def copied_controls(evaluation, info):
    if info['facts']['case'] == 'shared-id-arrow':
        return identity_arrow_controls(evaluation,info)
    if info['facts']['case'] == 'shared-apply-instance':
        return instance_controls(evaluation,info)
    if info['facts']['case'] == 'shared-apply-arrow':
        return apply_arrow_controls(evaluation,info)
    if info['facts']['case'] == 'shared-id-instance':
        return foreign_instance_controls(evaluation,info)
    raise AssertionError('unknown source control case')


def run_case(args, output, env, case):
    require(QUALIFICATION_READY, 'portable suite is awaiting independent review')
    inputs = output / 'inputs'; inputs.mkdir()
    for name, text in FIXTURES[case].items():
        (inputs / name).write_text(text, encoding='utf-8')
    target = output / case
    build.run([sys.executable, '-B', str(BASE / 'run_source_v8.py'), str(inputs / 'main.emlf'),
               '--module-root', str(inputs), '--ghc', args.ghc, '--cc', args.cc, '--output', str(target)],
              output, case, cwd=BASE, env=env, wall=1200, cpu=900, memory=16 << 30,
              termination_grace=15, stdout_limit=1 << 20, stderr_limit=1 << 20, file_limit=64 << 20)
    require(not bounded_read(output / (case + '.stderr'), 1 << 20), 'successful CLI stderr')
    result = read_json(target / 'result.json'); evaluation = read_json(target / 'native/run.stdout')
    require(result['status'] == 'complete' and result['failure_policy'] == 'retain' and
            result['native'] == evaluation and 'placement' not in result, 'fresh default CLI result differs')
    capture = read_json(target / 'capture.stdout'); verified = read_json(target / 'verification.json')
    plan = read_json(target / 'planned.json', 8 << 20)
    require(plan['binding']['mode'] == 'coarse-owned', 'default placement changed')
    generated = bounded_read(target / 'native/ir8_runtime_generated.c', 8 << 20).decode()
    info = structure(capture, verified, plan, generated, case)
    row = {'status': 'passed', 'observation': observe(evaluation, info),
           'copied_report_controls': copied_controls(evaluation, info),
           'copied_structure_controls': structure_controls(capture, verified, plan, generated, case),
           'source_hashes': {name: build.sha(text.encode()) for name, text in FIXTURES[case].items()}}
    build.save(target / 'arrow-argument-observations.json', row)
    print(case + ': PASS', flush=True)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', required=True); parser.add_argument('--cc', default='cc')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=('all',) + tuple(FIXTURES), default='all')
    args = parser.parse_args()
    # Leave fresh source/native launches disabled until this exact integrated
    # observer and its commands have received independent review.
    require(QUALIFICATION_READY, 'portable suite is awaiting independent review')
    output = args.output.absolute()
    require(output.resolve() == output and output != BASE.parents[2] and BASE.parents[2] not in output.parents,
            'output must be canonical, fresh and outside checkout')
    output.mkdir(parents=True, exist_ok=False); env = cli.environment(output)
    build.SUITE_DEADLINE = time.monotonic() + 1500
    rows = {}
    try:
        for case in FIXTURES if args.case == 'all' else (args.case,):
            child = output / case; child.mkdir()
            rows[case] = run_case(args, child, env, case)
    except BaseException as exc:
        try: build.save(output / 'failure.json', {'error': repr(exc)})
        except BaseException as persistence: exc.add_note('Failure persistence also failed: ' + repr(persistence))
        raise
    build.save(output / 'results.json', {'status': 'passed', 'cases': rows})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
