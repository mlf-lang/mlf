#!/usr/bin/env python3
"""Seven synthetic raw-IR Instance scalar recipes, each at O0 and O2.

Both complete Int/Bool views are demanded. Results are genuine scalar results,
not success markers. This is runtime semantic coverage, not original-source
coverage or exhaustive hostile-input testing. Production sources are unchanged.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path[:0] = [str(BASE), str(HERE)]
import source_build_v8 as build
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime
from test_ir8_generic_primitives import primitive_program, selection_program
from test_shared_source_native import instruction
from test_source_v8_monomorphic_recursion import ledger
from test_source_v8_recursive_sum import one

require = build.require
RECIPES = {
    'addInt': (17, 6, 23),
    'subInt': (17, 6, 11),
    'mulInt': (-7, 6, -42),
    'eqInt': (17, 17, True),
    'ltInt': (17, 6, False),
    'select-true': (True, None, 37),
    'select-false': (False, None, -19),
}
FILES = (('ir8_packet_generated.h', 'packet_header'),
         ('ir8_packet_generated.c', 'packet_source'),
         ('ir8_runtime_generated.h', 'runtime_header'),
         ('ir8_runtime_generated.c', 'runtime_source'))


def recipe(name):
    left, right, expected = RECIPES[name]
    selection = name.startswith('select-')
    p = selection_program(left) if selection else primitive_program(name, pending=True)
    if selection:
        p['codes']['yes']['body'][0]['value'] = 37
        p['codes']['no']['body'][0]['value'] = -19
    else:
        next(x for x in p['entry'] if x.get('out') == 'seed')['value'] = left
        next(x for x in p['functions']['id']['body'] if x.get('out') == 'right')['value'] = right
    # Keep the original two complete instantiations and applications. Demand
    # Int first, then Bool, and return the actual second result to the driver.
    p['entry'].remove({'op': 'drop', 'value': 'ab'})
    at = p['entry'].index({'op': 'force', 'out': 'answer', 'value': 'ai'})
    p['entry'][at+1:at+1] = [
        {'op': 'drop', 'value': 'answer'},
        {'op': 'force', 'out': 'answer_b', 'value': 'ab'}]
    require(p['entry'][-1] == {'op': 'finish_scalar', 'value': 'answer'}, 'fixture terminal changed')
    p['entry'][-1]['value'] = 'answer_b'
    return p, {'name': name, 'selection': selection, 'left': left, 'right': right,
               'expected': expected, 'kind': 'bool' if type(expected) is bool else 'i64'}


def observe(e, p, meta, spec):
    expected = spec['expected']; selection = spec['selection']; events = e['events']
    require(e['state'] == e['fault'] == 0 and e['schema'] == 'resource-ir-v8-run/1' and
            e['result'] == {'kind': spec['kind'], 'value': expected} and
            type(e['result']['value']) is type(expected) and
            e['scalar_result_kind'] == (2 if spec['kind'] == 'bool' else 1) and
            e['scalar_result'] == int(expected) and e['graph_executed'] == 1 and
            e['events_omitted'] == 0 and e['events_emitted'] == len(events),
            'actual terminal scalar result differs')
    require(e['guards_failed_mask'] == 0 and
            0 < e['guard_work_used'] == e['guard_work_total'] <= e['guard_work_limit'] == 67108864,
            'guard or work failure')
    ledger(e, True)
    select = lambda name: [(i, x) for i, x in enumerate(events) if x['event'] == name]
    allocations = select('allocate')
    nodes = {x['node']: x for _, x in allocations}
    require(len(nodes) == len(allocations), 'duplicate node identity')
    for _, x in allocations:
        site = meta['sites'][x['site_id']]
        op = instruction(p, site['path'])
        se = one([r for r in meta['site_executions'] if r['site'] == site['id'] and r['env'] == x['env_id']], 'actual SiteExecution')
        require(x['out'] == op['out'] and x['opcode'] == op['op'] and
                x['shape_id'] == meta['representations'][se['representation']]['shape'] and
                x['code'] == (meta['codes'][site['code']]['name'] if site['code'] is not None else None) and
                x['state'] == {'scalar': 'READY', 'prim2': 'READY', 'closure': 'CLOSURE',
                               'application': 'APPLICATION', 'thunk': 'THUNK'}[op['op']],
                'actual allocation contract differs')
    bi, bonus = one([(i, x) for i, x in allocations if x['out'] == 'bonus'], 'original import')
    ci, closure = one([(i, x) for i, x in allocations if x['out'] == 'f'], 'single generic root')
    scheme = one(meta['schemes'], 'single Scheme')
    require(bonus['env_id'] == 0 and bonus['state'] == ('READY' if selection else 'APPLICATION') and
            closure['env_id'] == scheme['neutral_env'] and closure['slots'] == {'captured': bonus['node']},
            'generic root must preserve original concrete import')
    gi, begin = one(select('generic_begin'), 'one begin')
    si, seal = one(select('generic_seal'), 'one seal')
    require(bi < gi < ci < si and seal['node'] == closure['node'], 'intro ordering differs')
    imports = [(i, x) for i, x in select('slot_install') if x['host'] == closure['node']]
    pi, pub = one(imports, 'one import publication')
    require(gi < pi < ci and pub['target'] == bonus['node'] and pub['target_state'] == bonus['state'],
            'publication forced or replaced original import')
    inst = select('instantiate')
    require(len(inst) == 2 and len({x['owner'] for _, x in inst}) == 2 and
            all(x['node'] == closure['node'] and x['mode'] == 'own' and x['anchor'] is None for _, x in inst),
            'two distinct complete owned views required')
    scalar = lambda n: one([(i, x) for i, x in select('scalar_value') if x['node'] == n], 'scalar value')
    calls = [(i, x) for i, x in select('invoke_enter') if x['closure'] == closure['node']]
    returns = [(i, x) for i, x in select('invoke_raw_return') if x['closure'] == closure['node']]
    frames = [(i, x) for i, x in select('frame_enter') if x['context'].get('node') == closure['node']]
    hands = [(i, x) for i, x in select('closure_capture_handoff') if x['node'] == closure['node']]
    require(len(calls) == len(returns) == len(frames) == len(hands) == 2, 'both complete views must execute once')
    completed = []; call_envs = []; selected_nodes = []; dead_nodes = []
    for j, ((ii, call), (ri, ret), (fi, frame), (_, hand), arg_atom) in enumerate(zip(calls, returns, frames, hands, ['#i64', '#bool'])):
        tid = one([x['id'] for x in meta['types'] if x['tag'] == 'closed' and x['atom'] == arg_atom], 'coordinate Type')
        use = one([x for x in meta['uses'] if x['arguments'] == [tid]], 'complete use')
        env = use['env']; call_envs.append(env)
        view = one([x for _, x in inst if x['use'] == use['id']], 'actual view')
        access = meta['accesses'][view['new_access']]
        require(access['origin_env'] == scheme['neutral_env'] and access['use_env'] == env and
                access['type'] == use['result_type'] and access['mode'] == 'MONO', 'full-vector Access/Env differs')
        _, argument = scalar(call['argument'])
        require(argument['kind'] == ('i64' if j == 0 else 'bool') and
                argument['value'] == (42 if j == 0 else True) and
                ii < fi < ri and frame['context']['name'] == 'id' and
                ret['argument'] == call['argument'] and hand['protocol'] == 'repeat' and
                set(hand['owners']) == {'captured'}, 'ordinary invocation correspondence differs')
        actual_forces = [x for _, x in select('ir_force_result') if x['frame'] == frame['frame']]
        raw_forces = [x for x in p['functions']['id']['body'] if x['op'] == 'force']
        require(len(actual_forces) == len(raw_forces) == 1 and
                actual_forces[0]['out'] == raw_forces[0]['out'] and
                actual_forces[0]['source_variable'] == raw_forces[0]['value'], 'exact scoped FORCE differs')
        app = one([x for _, x in allocations if x['out'] == ('ai' if j == 0 else 'ab')], 'original application')
        require(app['slots'] == {'$function': closure['node'], '$argument': call['argument']}, 'application graph changed')
        mi, memo = one([(i, x) for i, x in select('memo_publish') if x['destination'] == app['node']], 'application memo')
        require(ri < mi, 'application memo precedes return')
        result = nodes[memo['result']]; vi, value = scalar(result['node'])
        require(result['env_id'] == env and value['kind'] == spec['kind'] and
                type(value['value']) is type(expected) and value['value'] == expected,
                'each closed Env must produce its exact scalar result')
        if selection:
            choice_i, choice = one([(i, x) for i, x in select('select_i64') if x['frame'] == frame['frame']], 'Instance selection')
            yes = one([x for _, x in allocations if x['frame'] == frame['frame'] and x['out'] == 'yes'], 'then allocation')
            no = one([x for _, x in allocations if x['frame'] == frame['frame'] and x['out'] == 'no'], 'else allocation')
            chosen, dead = (yes, no) if spec['left'] else (no, yes)
            require(yes['env_id'] == no['env_id'] == env and choice['condition_node'] == bonus['node'] and
                    choice['condition_value'] is spec['left'] and choice['then_node'] == yes['node'] and
                    choice['else_node'] == no['node'] and choice['result'] == ret['result'] == chosen['node'] and
                    choice_i < ri < vi and value['primitive'] is None,
                    'actual branch direction or deferred selected result differs')
            require(one([x for _, x in select('callback_enter') if x['node'] == chosen['node']], 'selected callback') and
                    not any(x.get('node') == dead['node'] for _, x in select('callback_enter') + select('update_pin')),
                    'unselected branch was demanded')
            branch_frame = one([x for _, x in select('frame_enter') if x['context'].get('node') == chosen['node']], 'selected frame')
            require(result['frame'] == branch_frame['frame'], 'selected callback must allocate final scalar')
            selected_nodes.append(chosen['node']); dead_nodes.append(dead['node'])
        else:
            right = one([x for _, x in allocations if x['frame'] == frame['frame'] and x['out'] == 'right'], 'actual right operand')
            _, right_value = scalar(right['node'])
            require(result['frame'] == frame['frame'] and result['opcode'] == 'prim2' and
                    value['primitive'] == spec['name'] and ret['result'] == result['node'] and vi < ri,
                    'actual Instance primitive result differs')
            require(right['env_id'] == env and right_value['kind'] == 'i64' and right_value['value'] == spec['right'],
                    'nontrivial right operand differs')
        completed.append({'env': env, 'result_node': result['node'], 'value': value['value'],
                          'force_result': actual_forces[0]['result'], 'memo_event': mi})
    require(len(set(call_envs)) == len({x['result_node'] for x in completed}) == 2 and
            len({x['owners']['captured'] for _, x in hands}) == 2, 'closed calls must have distinct Env/results/capture owners')
    if selection:
        _, imported = scalar(bonus['node'])
        require(imported['kind'] == 'bool' and imported['value'] is spec['left'] and
                all(x['force_result'] == bonus['node'] for x in completed) and
                not any(x['destination'] == bonus['node'] for _, x in select('memo_publish')),
                'ready Bool import must keep identity without a synthetic memo')
    else:
        memo_i, memo = one([(i, x) for i, x in select('memo_publish') if x['destination'] == bonus['node']], 'once-only pending import memo')
        _, imported = scalar(memo['result'])
        seed = one([x for _, x in allocations if x['out'] == 'seed'], 'original scalar seed')
        concrete = one([x for _, x in allocations if x['out'] == 'scalar_fn'], 'concrete pending-application closure')
        require(bonus['slots'] == {'$function': concrete['node'], '$argument': seed['node']} and
                len([x for _, x in select('invoke_enter') if x['closure'] == concrete['node']]) == 1,
                'original concrete APPLICATION must invoke its real callback exactly once')
        require(memo['result'] == seed['node'] and imported['kind'] == 'i64' and imported['value'] == spec['left'] and
                calls[0][0] < memo_i < returns[0][0] < calls[1][0] and
                all(x['force_result'] == memo['result'] for x in completed), 'pending APPLICATION import was recomputed or relabelled')
        require(len([x for _, x in select('update_pin') if x['node'] == bonus['node']]) == 1 and
                not any(x.get('node') == bonus['node'] for i, x in select('update_pin') if i < si),
                'pending owner must be demanded once, after introduction')
    require(e['metrics']['ordinary_calls'] == len(select('invoke_enter')) == (2 if selection else 3) and
            e['metrics']['nodes_allocated'] == len(allocations) and
            e['metrics']['memo_writes'] == len(select('memo_publish')), 'actual operation census differs')
    return {'status': 'passed', 'recipe': spec, 'synthetic_raw_ir': True, 'closed_calls': completed,
            'import_node': bonus['node'], 'shared_node': closure['node'],
            'selected_nodes': selected_nodes, 'unselected_nodes': dead_nodes,
            'events': len(events), 'work': e['guard_work_used'], 'all_seven_ledgers_zero': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    cc = build.executable(args.cc); env = dict(os.environ, LANG='C', LC_ALL='C', TZ='UTC', PYTHONHASHSEED='0')
    build.SUITE_DEADLINE = time.monotonic() + 1200
    rows = []
    try:
        for name in RECIPES:
            directory = output/name; directory.mkdir()
            p, spec = recipe(name)
            checked = check_resources(p); metadata = check_metadata(p); emission = emit_runtime(p)
            meta = json.loads(metadata.metadata_json)
            build.save(directory/'program.json', p)
            build.save(directory/'resources.json', json.loads(checked.derived_json))
            build.save(directory/'metadata.json', meta)
            for filename, field in FILES:
                with (directory/filename).open('x') as stream: stream.write(getattr(emission, field))
            reports = []; observations = []
            for opt in ('O0', 'O2'):
                native = directory/opt; native.mkdir(); binary = native/'program'
                command = [cc, '-std=c11', '-'+opt, '-g', '-Wall', '-Wextra', '-Werror', '-pedantic',
                           '-I'+str(BASE/'packet_v8'), '-I'+str(BASE/'runtime_v8'), '-I'+str(directory),
                           str(BASE/'packet_v8/ir8_packet.c')]
                command += [str(BASE/'runtime_v8'/name) for name in build.RUNTIME_SOURCES]
                command += [str(directory/'ir8_packet_generated.c'), str(directory/'ir8_runtime_generated.c'),
                            str(BASE/'source_v8/native_driver.c'), '-o', str(binary)]
                build.run(command, native, 'compile', cwd=BASE, env=env, wall=60, cpu=30, memory=1<<30)
                build.run([str(binary)], native, 'run', cwd=native, env=env, wall=60, cpu=40, memory=512<<20)
                require((native/'compile.stderr').read_bytes() == (native/'run.stderr').read_bytes() == b'', 'unexpected diagnostics')
                report = json.loads((native/'run.stdout').read_text())
                observation = observe(report, p, meta, spec)
                build.save(native/'observations.json', observation)
                reports.append(report); observations.append(observation)
                print(name, opt, 'PASS', report['result'], flush=True)
            require(reports[0] == reports[1], 'full O0/O2 reports differ, including work and ledgers')
            rows.append({'case': name, 'observations': observations, 'full_optimizer_equality': True})
    except BaseException as exc:
        build.save(output/'failure.json', {'error': repr(exc), 'completed': rows})
        raise
    build.save(output/'results.json', {'status': 'passed', 'scope': 'seven synthetic raw-IR Instance scalar recipes',
                                      'builds': 14, 'native_runs': 14, 'cases': rows})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
