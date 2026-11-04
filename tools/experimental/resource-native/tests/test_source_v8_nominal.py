#!/usr/bin/env python3
"""Three opt-in, fresh real-source DATA/closed-callable-field CLI integrations.

POSIX; trusted GHC 9.14.1 and C11 compiler required. Example:
  python3 -B tests/test_source_v8_nominal.py --ghc /path/to/ghc --cc cc \
      --output /path/to/new-output
No cached capture, original evaluator, alternate runtime, or default change.
Each case independently builds the real producer through run_source_v8.py.
Physical node reclamation is group-based: dropping a container handle is NOT
claimed to deallocate its node. Retain/end-borrow/drop order is checked in IR
and actual generated C, with runtime projection/return events and aggregate
owner/loan balances; the runtime does not emit each individual handle operation.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import run_source_v8 as cli
import source_build_v8 as build
from source_snapshot_v8 import bounded_read
# This module has no top-level evidence generation. Reuse its finite shared-node,
# curried-capture and seven-category assertions, not historical output files.
from test_shared_source_native import at, instruction, check_native

SHARED_ID = ('module SharedPoly (sharedId) where\n'
             'sharedId : forall a. a -> a\nsharedId x = x\n')
SHARED_CONST = ('module SharedPoly (sharedConst) where\n'
                'sharedConst : forall a b. a -> b -> a\nsharedConst x y = x\n')
CASES = (
    {'name': 'scalar-box', 'module': 'BoxData.emlf',
     'module_text': 'module BoxData (Box(..)) where\ndata Box = Box Int\n',
     'source': 'import BoxData\nlet boxed = Box 42 in\ncase boxed of { Box value -> value }\n',
     'field': ('Int',), 'vectors': [], 'curried': False},
    {'name': 'shared-field', 'module': 'SharedPoly.emlf', 'module_text': SHARED_ID,
     'source': 'import SharedPoly\ndata FnBox = FnBox (Int -> Int);\n'
               'let boxed = FnBox (sharedId : Int -> Int) in\n'
               'let extracted = case boxed of { FnBox field -> field } in\n'
               'if sharedId true then extracted 42 else 0\n',
     'field': ('Int', 'Int'), 'vectors': [['#i64'], ['#bool']], 'curried': False},
    {'name': 'curried-field', 'module': 'SharedPoly.emlf', 'module_text': SHARED_CONST,
     'source': 'import SharedPoly\ndata FnBox = FnBox (Bool -> Int);\n'
               'let b = sharedConst true 7 in\n'
               'let boxed = FnBox (sharedConst 42) in\n'
               'let extracted = case boxed of { FnBox field -> field } in\n'
               'if b then extracted false else 0\n',
     'field': ('Bool', 'Int'), 'vectors': [['#bool', '#i64'], ['#i64', '#bool']],
     'curried': True},
)
require = build.require


def read_json(path, limit=32 << 20):
    return json.loads(bounded_read(path, limit))


def only(rows, message):
    require(len(rows) == 1, message)
    return rows[0]


def scalar_type(name, declaration=False):
    return {'tag': 'applied' if declaration else 'constructor', 'name': name, 'arguments': []}


def expected_field(case, declaration=False):
    fields = case['field']
    if len(fields) == 1:
        return scalar_type(fields[0], declaration)
    return {'tag': 'function' if declaration else 'arrow',
            'from': scalar_type(fields[0], declaration),
            'to': scalar_type(fields[1], declaration)}


def shared_graph(case, plan, verified):
    p, m = plan['program'], plan['binding']['source_map']
    if not case['vectors']:
        require(not p['schemes'] and not m['scheme_map'] and not verified['fragment']['definitions'],
                'scalar Box unexpectedly contains a shared Scheme')
        return None
    d = only(verified['fragment']['definitions'], 'expected one shared source definition')
    s = only(m['scheme_map'], 'expected one Scheme mapping')
    require(len(p['schemes']) == 1 and s['binder'] == d['binding']['id'],
            'shared definition mapping differs')
    require(p['schemes'][s['scheme']]['parameters'] == len(case['vectors'][0]),
            'complete type vector was lost')
    vectors = [[p['types'][t]['layout'] for t in u['arguments']]
               for u in p['instantiations'].values()]
    require(vectors == case['vectors'] and len(m['use_map']) == len(verified['fragment']['uses']) == 2,
            'full ordered shared uses differ')
    generic, seal = instruction(p, s['generalize']), instruction(p, s['seal'])
    require(generic['op'] == 'generalize' and seal['op'] == 'seal', 'missing generic boundary')
    app = only([x for x in generic['body'] if x['op'] == 'application'], 'pending RHS differs')
    require(app['out'] == seal['value'] and not any(x['op'] == 'force' for x in generic['body']),
            'shared pending RHS was replaced or eagerly evaluated')
    closures = {x['out']: x['function'] for x in generic['body'] if x['op'] == 'closure'}
    carriers = [x for x in m['carrier_map'] if x['kind'] == 'lambda' and x['type_scope'] == s['scheme']]
    require(len(carriers) == (5 if case['curried'] else 3), 'generic source lambdas lost or cloned')
    require(len({tuple(x['source']['path']) for x in carriers}) == len(carriers), 'cloned source lambda')
    return {'outer_code': closures[app['function']], 'shared_code': closures[app['argument']],
            'seal_owner': seal['value'], 'vectors': vectors}


def nominal_structure(case, capture, plan, generated):
    p, m = plan['program'], plan['binding']['source_map']
    raw = capture['normalization']['raw_normalized']
    require(raw['tag'] == 'with_data', 'missing genuine declaration context')
    nominal = only(m['nominal_map'], 'expected one used nominal family')
    ctor = only(m['constructor_map'], 'expected one constructor occurrence')
    arm = only(m['case_map'], 'expected one case occurrence')
    declaration = raw['declarations'][nominal['declaration']]
    constructor = only(declaration['constructors'], 'expected a single-constructor DATA')
    require(declaration['tag'] == 'data_kind' and declaration['parameters'] == [] and
            declaration['name'] == nominal['name'] and constructor['fields'] == [expected_field(case, True)],
            'actual checked nominal declaration differs')
    require(ctor['declaration'] == arm['declaration'] == nominal['declaration'], 'wrong family mapping')
    head = at(raw, ctor['head']['path'])
    require(head == {'tag': 'constructor', 'name': constructor['name'], 'arguments': []},
            'constructor identity/type arguments differ')
    argument = only(ctor['arguments'], 'expected one exact field source')
    source_argument = at(raw, argument['path'])
    require(source_argument['tag'] == ('application' if case['vectors'] else 'int64'),
            'unexpected genuine field expression; inspect capture, do not specialize it')
    source_case = at(raw, arm['source']['path'])
    alternative = only(source_case['alternatives'], 'case alternatives differ')
    binder = only(alternative['pattern']['fields'], 'expected one bound case field')
    require(source_case['tag'] == 'case' and source_case['result_type'] == expected_field(case) and
            alternative['pattern']['constructor'] == constructor['name'] and
            alternative['body'] == {'tag': 'var', 'name': binder}, 'case field identity/result differs')
    allocation = instruction(p, ctor['allocation'])
    case_allocation = instruction(p, arm['allocation'])
    require(allocation['op'] == 'alloc' and allocation['layout'] == nominal['layout'] and
            set(allocation['fields']) == {'f0'} and case_allocation['op'] == 'thunk' and
            case_allocation['code'] == arm['code'], 'lazy DATA/case allocation differs')
    field_type = only(nominal['fields'], 'field map differs')['type']
    require(arm['result_type'] == field_type, 'case lost its full field result type')
    if case['vectors']:
        typ = p['types'][field_type]
        require(typ['tag'] == 'arrow' and typ['protocol'] == 'repeat' and typ['result_identity'] == 'unknown',
                'callable field contract was erased')
        require([p['types'][typ[k]]['layout'] for k in ('argument', 'result')] ==
                [('#bool' if x == 'Bool' else '#i64') for x in case['field']], 'field arrow changed')
    projection = only(arm['projections'], 'field projection mapping differs')
    require(projection['binder'] == binder['id'] and projection['index'] == 0, 'wrong field binder')
    refs = [projection['loan'], projection['retain'], projection['end_borrow'], arm['drop_container']]
    require(all(r['root'] == 'thunk' and r['name'] == arm['code'] and len(r['segments']) == 1 for r in refs),
            'unexpected case instruction shape')
    indices = [r['segments'][0] for r in refs]
    require(indices == list(range(indices[0], indices[0] + 4)), 'field ownership order differs')
    loan, retain, end, drop = [instruction(p, r) for r in refs]
    require(loan['op'] == 'field' and loan['field'] == 'f0' and retain['op'] == 'retain' and
            retain['value'] == loan['out'] and end == {'op': 'end_borrow', 'value': loan['out']} and
            drop == {'op': 'drop', 'value': loan['value']}, 'loan/retain/end/container-drop mismatch')
    # Restricted emitted spelling, not a general C parser or individual runtime trace.
    sequence = re.compile(r'(?P<loan>h\d+) = rt8_field\(ctx, (?P<container>h\d+), 0, p\d+, p\d+\);\n'
                          r'    h\d+ = rt8_retain\(ctx, (?P=loan)\);\n'
                          r'    rt8_end_borrow\(ctx, (?P=loan)\);\n'
                          r'    rt8_drop\(ctx, (?P=container)\);')
    require(len(sequence.findall(generated)) == 1 and generated.count('= rt8_field(') == 1,
            'generated C does not preserve the sole field ownership sequence')
    return {'nominal': nominal, 'constructor': allocation, 'case': case_allocation,
            'projection': loan, 'source_binder': binder['id']}


def observe(case, evaluation, structure, graph):
    e = evaluation
    require(e['fault'] == 0 and e['result'] == {'kind': 'i64', 'value': 42} and e['events_omitted'] == 0,
            'native result/event history differs')
    metrics = e['metrics']
    require(metrics['entries_completed'] == 1 and metrics['groups_allocated'] == metrics['groups_closed'] and
            metrics['nodes_allocated'] == metrics['nodes_freed'], 'incomplete group/node cleanup')
    for prefix in ('owner', 'loan'):
        require(metrics[prefix + '_handle_acquisitions'] == metrics[prefix + '_handle_releases'],
                'unbalanced ' + prefix + ' handles')
    require(metrics['ir_end_borrow_ops'] == 1, 'sole case loan was not ended')
    require(set(e['memory_categories']) == {'context', 'groups', 'nodes', 'slots', 'handles', 'captures', 'pending'},
            'seven-category ledger changed')
    for row in [e['memory']] + list(e['memory_categories'].values()):
        require(row['live_bytes'] == row['live_blocks'] == 0 and row['allocated_bytes'] == row['freed_bytes'] and
                row['allocations'] == row['frees'], 'runtime-owned allocation imbalance')
    events = e['events']
    selected = lambda event: [(i, x) for i, x in enumerate(events) if x['event'] == event]
    allocations = selected('allocate')
    data_i, data = only([(i,x) for i,x in allocations if x['out'] == structure['constructor']['out']],
                        'DATA allocation event differs')
    thunk_i, thunk = only([(i,x) for i,x in allocations if x['code'] == structure['case']['code']],
                          'case thunk event differs')
    nodes = {x['node']: x for _,x in allocations}
    target = data['slots']['f0']
    project_i, project = only(selected('field_project'), 'projection event count differs')
    require(project['host'] == data['node'] and project['target'] == target and project['field'] == 'f0' and
            project['out'] == structure['projection']['out'] and
            project['source_variable'] == structure['projection']['value'], 'wrong actual field projection')
    force_i, force = only([(i,x) for i,x in selected('ir_force_result') if x['owner'] == project['anchor']],
                          'missing actual container anchor')
    require(force['result'] == data['node'] and force['frame'] == project['frame'] and force_i < project_i,
            'field anchor/container frame mismatch')
    return_i, returned = only([(i,x) for i,x in selected('raw_return') if x['source'] == thunk['node']],
                              'case did not return the observed field')
    require(returned['result'] == target and data_i < thunk_i < project_i < return_i,
            'case return/laziness order differs')
    close_i, close = only([(i,x) for i,x in selected('close_group') if x['group'] == data['group']],
                          'container group retirement missing')
    require(close_i > return_i, 'group closed before case return')
    detail = {'container_node': data['node'], 'field_node': target, 'case_node': thunk['node'],
              'field_event': project_i, 'case_return_event': return_i, 'group_close_event': close_i,
              'ownership_order': 'IR and generated-C sequence; runtime projection/return plus balanced counters',
              'physical_container_retirement_before_field_call_claimed': False}
    if case['vectors']:
        require(nodes[target]['state'] == returned['result_state'] == 'APPLICATION',
                'callable payload was eagerly evaluated or substituted')
        target_i = only([i for i,x in allocations if x['node'] == target], 'pending allocation missing')
        force_target = [i for i,x in selected('update_pin') if x['node'] == target]
        require(target_i < data_i and force_target and min(force_target) > return_i,
                'stored pending field forced before lazy case returned')
        memo_i, memo = only([(i,x) for i,x in selected('memo_publish') if x['destination'] == target],
                            'field application memo count differs')
        calls = [(i,x) for i,x in selected('invoke_enter') if x['closure'] == memo['result'] and i > memo_i]
        call_i, call = only(calls, 'extracted callable was not invoked exactly once later')
        scalars = {x['node']: (x['kind'], x['value']) for _,x in selected('scalar_value')}
        require(scalars[call['argument']] == (('bool', False) if case['curried'] else ('i64', 42)) and
                return_i < memo_i < call_i < close_i, 'extracted invocation/order differs')
        detail.update(field_memo_event=memo_i, later_call_event=call_i, callable_node=memo['result'])
    return detail


def run_case(case, args, output, env):
    name = case['name']
    inputs = output / (name + '-inputs')
    inputs.mkdir()
    (inputs / case['module']).write_text(case['module_text'], encoding='utf-8')
    entry = inputs / 'main.emlf'
    entry.write_text(case['source'], encoding='utf-8')
    target = output / name
    command = [sys.executable, '-B', str(BASE / 'run_source_v8.py'), str(entry),
               '--module-root', str(inputs), '--ghc', args.ghc, '--cc', args.cc,
               '--output', str(target)]
    build.run(command, output, name, cwd=BASE, env=env, wall=1200, cpu=900, memory=16 << 30,
              termination_grace=15, stdout_limit=1 << 20, stderr_limit=1 << 20, file_limit=64 << 20)
    require(not bounded_read(output / (name + '.stderr'), 1 << 20), 'successful CLI stderr')
    result = read_json(target / 'result.json')
    evaluation = read_json(target / 'native/run.stdout')
    require(result['status'] == 'complete' and result['failure_policy'] == 'retain' and
            result['native'] == evaluation and evaluation['schema'] == 'resource-ir-v8-run/1',
            'default CLI result/policy differs')
    capture = read_json(target / 'capture.stdout')
    verified = read_json(target / 'verification.json')
    require(verified['fragment_admitted'] and verified['normalization_replay'] == 'all exact independent fields match',
            'fresh independent capture replay failed')
    require(capture['checked_type'] == scalar_type('Int'), 'actual ordinary checked root differs')
    plan = read_json(target / 'planned.json', 8 << 20)
    structure = nominal_structure(case, capture, plan,
                                  bounded_read(target / 'native/ir8_runtime_generated.c', 8 << 20).decode())
    graph = shared_graph(case, plan, verified)
    shared = None
    if graph:
        shared = check_native({'evaluation': evaluation}, plan, graph,
                              [('bool', True), ('i64', 42)], case['curried'])
    observation = observe(case, evaluation, structure, graph)
    row = {'case': name, 'status': 'passed', 'source_hashes': {
        'main.emlf': build.sha(case['source'].encode()),
        case['module']: build.sha(case['module_text'].encode())},
        'observation': observation, 'shared': shared,
        'memory_categories': evaluation['memory_categories']}
    build.save(target / 'nominal-observations.json', row)
    print(name + ': PASS (fresh checked source, lazy DATA field, Int42, balanced seven-category ledger)', flush=True)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', required=True)
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.resolve() == output and output != BASE.parents[2] and BASE.parents[2] not in output.parents,
            'output must be canonical and outside this checkout')
    output.mkdir(parents=True, exist_ok=False)
    env = cli.environment(output)
    build.SUITE_DEADLINE = time.monotonic() + 3600
    results = []
    try:
        for case in CASES:
            results.append(run_case(case, args, output, env))
    except BaseException as exc:
        try:
            build.save(output / 'failure.json', {'error': type(exc).__name__ + ': ' + str(exc),
                                               'completed_cases': [r['case'] for r in results]})
        except BaseException as persistence:
            exc.add_note('Failure persistence also failed: ' + repr(persistence))
        raise
    build.save(output / 'results.json', results)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
