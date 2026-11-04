#!/usr/bin/env python3
"""Local controlled-source tests, NOT general diagnostic-JSON/export/3 admission.

Build the real standalone producer from this checkout, replay its three fresh
captures independently, lower/check/emit IR8, and link/run the real runtime.
The fourth source is an unused ordinary type error, rejected before projection.
No original evaluator, old receipt, body substitute or v7 fallback is used.

Linux/POSIX; supply a trusted official GHC 9.14.1 installation and a C11 compiler:
  python3 -B tests/test_shared_source_native.py --ghc /path/to/ghc --cc gcc \
      --output /path/to/new-output
The output directory must not exist. Failed commands and all logs are retained.
Version checking establishes the reported version, not download authenticity.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parents[1]
REPO = BASE.parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(BASE))
from planner_v8 import plan_fragment
from resource_ir_v8.checker import check_resources
from resource_ir_v8.runtime_emit import emit_runtime
from validate_shared_capture import verify_capture
import source_build_v8 as build_tools
from source_build_v8 import (MIB, PACKAGES, SOURCE_ROOTS, RUNTIME_SOURCES,
                             require, save, sha, executable, run, build_producer)

SUITE_DEADLINE = None
SCOPE = 'local controlled-source test; not arbitrary diagnostic JSON or export/3 admission'
SHARED_ID = ('module SharedPoly (sharedId) where\n'
             'sharedId : forall a. a -> a\nsharedId x = x\n')
SHARED_CONST = ('module SharedPoly (sharedConst) where\n'
                'sharedConst : forall a b. a -> b -> a\nsharedConst x y = x\n')
CASES = (
    ('int-first', SHARED_ID,
     'import SharedPoly\nlet i = sharedId 41 in let b = sharedId true in '
     'if ltInt i 42 then if b then addInt i 1 else 0 else 0\n',
     [['#i64'], ['#bool']], [('i64', 41), ('bool', True)]),
    ('bool-first', SHARED_ID,
     'import SharedPoly\nlet b = sharedId true in let i = sharedId 41 in '
     'if b then addInt i 1 else 0\n',
     [['#bool'], ['#i64']], [('bool', True), ('i64', 41)]),
    ('curried-const', SHARED_CONST,
     'import SharedPoly\nif sharedConst true 7 then sharedConst 42 false else 0\n',
     [['#bool', '#i64'], ['#i64', '#bool']], [('bool', True), ('i64', 42)]),
)
NEGATIVE = 'import SharedPoly\nlet bad = addInt true 1 in sharedId 42\n'














def at(root, path):
    for part in path:
        root = root[int(part)] if isinstance(root, list) else root[part]
    return root


def instruction(program, ref):
    root = program['entry'] if ref['root'] == 'entry' else program[
        'functions' if ref['root'] == 'function' else 'codes'][ref['name']]['body']
    return at(root, ref['segments'])


def check_structure(plan, verified, vectors):
    """Check this fixture's real graph, not its generated variable/name spelling."""
    p, mapping = plan['program'], plan['binding']['source_map']
    definitions = verified['fragment']['definitions']
    require(len(definitions) == len(p['schemes']) == len(mapping['scheme_map']) == 1,
            'expected exactly one shared definition and Scheme')
    definition, scheme_map = definitions[0], mapping['scheme_map'][0]
    require(scheme_map['binder'] == definition['binding']['id'], 'wrong real binder association')
    require(p['schemes'][scheme_map['scheme']]['parameters'] == len(vectors[0]),
            'full type parameter vector was lost')
    actual_vectors = [[p['types'][t]['layout'] for t in u['arguments']]
                      for u in p['instantiations'].values()]
    require(actual_vectors == vectors, 'complete ordered instantiation vectors differ')
    require(len(mapping['use_map']) == len(verified['fragment']['uses']) == 2,
            'shared uses were lost or duplicated')
    generic = instruction(p, scheme_map['generalize'])
    seal = instruction(p, scheme_map['seal'])
    require(generic['op'] == 'generalize' and seal['op'] == 'seal', 'generic boundaries differ')
    allocations = [x for x in generic['body'] if x['op'] == 'application']
    require(len(allocations) == 1 and allocations[0]['out'] == seal['value'],
            'the real pending RHS application must be sealed, not evaluated or replaced')
    require(not any(x['op'] == 'force' for x in generic['body']), 'generic RHS was eagerly forced')
    closures = {x['out']: x['function'] for x in generic['body'] if x['op'] == 'closure'}
    app = allocations[0]
    outer_code, shared_code = closures[app['function']], closures[app['argument']]
    carriers = [x for x in mapping['carrier_map'] if x['kind'] == 'lambda']
    require(len(carriers) == len(p['functions']) == (5 if len(vectors[0]) == 2 else 3),
            'actual source lambdas were lost, cloned or replaced')
    require(len({tuple(x['source']['path']) for x in carriers}) == len(carriers),
            'one source lambda was emitted more than once')
    require(all(x['type_scope'] == scheme_map['scheme'] for x in carriers),
            'generic lambda lost its lexical scope')
    return {'outer_code': outer_code, 'shared_code': shared_code,
            'seal_owner': seal['value'], 'vectors': actual_vectors}


def check_native(report, plan, graph, expected_arguments, curried):
    e = report['evaluation']
    # IR8_PACKET_SHAPE_KIND_I64, the public packet/runtime scalar-kind tag.
    require(e['fault'] == 0 and e['scalar_result_kind'] == 1 and e['scalar_result'] == 42,
            'native result is not the expected Int42')
    require(e['metrics']['entries_completed'] == 1 and e['events_omitted'] == 0,
            'incomplete entry or event history')
    require(set(e['memory_categories']) == {'context', 'groups', 'nodes', 'slots',
                                          'handles', 'captures', 'pending'}, 'ledger categories differ')
    for row in [e['memory']] + list(e['memory_categories'].values()):
        require(row['live_bytes'] == row['live_blocks'] == 0, 'live allocation after healthy cleanup')
        require(row['allocated_bytes'] == row['freed_bytes'] and row['allocations'] == row['frees'],
                'allocation/free ledger imbalance')
    events = e['events']
    selected = lambda name: [(i, x) for i, x in enumerate(events) if x['event'] == name]
    begins, seals, uses = selected('generic_begin'), selected('generic_seal'), selected('instantiate')
    require(len(begins) == len(seals) == 1 and len(uses) == 2, 'duplicated generic graph or missing uses')
    shared_node = seals[0][1]['node']
    require(all(x['node'] == shared_node for _, x in uses), 'views do not share the sealed node')
    nodes = {x['node']: x for _, x in selected('allocate')}
    pending = nodes[shared_node]
    require(pending['state'] == 'APPLICATION' and pending['out'] == graph['seal_owner'],
            'sealed node is not the real pending application')
    outer, body = pending['slots']['$function'], pending['slots']['$argument']
    require(nodes[outer]['code'] == graph['outer_code'] and nodes[body]['code'] == graph['shared_code'],
            'pending graph uses different source bodies')
    require(sum(x.get('code') == graph['shared_code'] for x in nodes.values()) == 1,
            'the shared RHS closure was allocated per type view')
    memo = [(i, x) for i, x in selected('memo_publish') if x['destination'] == shared_node]
    require(len(memo) == 1 and memo[0][1]['result'] == body, 'shared pending RHS was not memoized once')
    calls = selected('invoke_enter')
    require(sum(x['closure'] == outer for _, x in calls) == 1, 'pending RHS outer body ran more than once')
    actual = [(i, x) for i, x in calls if x['closure'] == body]
    scalars = {x['node']: (x['kind'], x['value']) for _, x in selected('scalar_value')}
    require([scalars[x['argument']] for _, x in actual] == expected_arguments,
            'same shared closure was not demanded in the expected Int/Bool order')
    require(memo[0][0] < actual[0][0] < actual[1][0], 'shared memo/demand ordering differs')
    if curried:
        returns = [(i, x) for i, x in selected('invoke_raw_return') if x['closure'] == body]
        require(len(returns) == 2, 'missing curried creator returns')
        children = [x['result'] for _, x in returns]
        require(children[0] != children[1], 'distinct curried activations reused a mutable closure')
        require(nodes[children[0]]['code'] == nodes[children[1]]['code'], 'curried body cloned by vector')
        child_code = nodes[children[0]]['code']
        capture_fields = plan['program']['functions'][child_code]['captures']
        require(len(capture_fields) == 1, 'curried closure lost its real capture')
        capture_name = next(iter(capture_fields))
        for (returned_at, returned), child, expected in zip(returns, children, [('i64', 7), ('bool', False)]):
            cc = [(i, x) for i, x in calls if x['closure'] == child]
            require(len(cc) == 1 and cc[0][0] > returned_at, 'curried closure used before creator returned')
            require(scalars[cc[0][1]['argument']] == expected, 'second formal argument differs')
            captured = nodes[child]['slots'][capture_name]
            require(nodes[captured]['state'] == 'APPLICATION', 'captured pending coercion was replaced')
            require(nodes[captured]['slots']['$argument'] == returned['argument'], 'capture lost original argument')
            cr = [x for _, x in selected('invoke_raw_return') if x['closure'] == child]
            require(len(cr) == 1 and cr[0]['result'] == captured, 'curried return bypassed captured node')
    return {'scalar': 42, 'shared_node': shared_node, 'shared_body_node': body,
            'shared_body_code': graph['shared_code'], 'demand_order': expected_arguments,
            'pending_rhs_evaluations': 1, 'vectors': graph['vectors'],
            'metrics': e['metrics'], 'memory': e['memory'], 'memory_categories': e['memory_categories']}


def positive(case, producer, cc, output, env):
    name, shared, entry_text, vectors, expected_arguments = case
    directory = output / name
    directory.mkdir()
    inputs = directory / 'inputs'
    inputs.mkdir()
    entry = name + '.emlf'
    for filename, text in (('SharedPoly.emlf', shared), (entry, entry_text)):
        (inputs / filename).write_text(text, encoding='utf-8')
    capture, err = run([str(producer), '--capture-shared'], directory, 'capture', cwd=inputs,
        env=env, stdin=entry_text.encode(), wall=180, cpu=120, memory=4 << 30,
        stdout_limit=33*MIB, stderr_limit=MIB)
    require(not err.read_bytes(), 'positive capture has stderr')
    verified = verify_capture(capture, fixture_root=inputs, entry=entry,
        expected_source_hashes={entry: sha(entry_text.encode()), 'SharedPoly.emlf': sha(shared.encode())},
        expected_capture_sha256=sha(capture.read_bytes()))
    save(directory / 'verification.json', verified)
    require(verified['fragment_admitted'] and
            verified['status'] == 'diagnostic-capture-replay-pass-not-source-admission',
            'independent source custody/projection/fragment replay failed')
    raw = json.loads(capture.read_bytes())['projection']['projected_annotated']
    plan = plan_fragment(raw)
    check_resources(plan['program'])
    graph = check_structure(plan, verified, vectors)
    save(directory / 'planned.json', plan)
    emission = emit_runtime(plan['program'])
    native = directory / 'native'
    native.mkdir()
    for filename, field in (('ir8_packet_generated.h', 'packet_header'),
                            ('ir8_packet_generated.c', 'packet_source'),
                            ('ir8_runtime_generated.h', 'runtime_header'),
                            ('ir8_runtime_generated.c', 'runtime_source')):
        (native / filename).write_text(getattr(emission, field), encoding='utf-8')
    argv = [cc, '-std=c11', '-O0', '-g', '-Wall', '-Wextra', '-Werror', '-pedantic',
            '-I' + str(BASE / 'packet_v8'), '-I' + str(BASE / 'runtime_v8'), '-I' + str(native),
            str(BASE / 'packet_v8/ir8_packet.c')]
    argv += [str(BASE / 'runtime_v8' / f) for f in RUNTIME_SOURCES]
    argv += [str(native / 'ir8_packet_generated.c'), str(native / 'ir8_runtime_generated.c'),
             str(BASE / 'tests/stage05_runtime_driver.c'), '-o', str(native / 'program')]
    run(argv, native, 'compile', cwd=REPO, env=env, wall=60, cpu=30, memory=1 << 30)
    stdout, stderr = run([str(native / 'program')], native, 'run', cwd=native,
                        env=env, wall=20, cpu=20, memory=1 << 30)
    require(not stderr.read_bytes(), 'native stderr is not empty')
    result = check_native(json.loads(stdout.read_bytes()), plan, graph, expected_arguments,
                          name == 'curried-const')
    result.update(case=name, scope=SCOPE, capture_sha256=sha(capture.read_bytes()), status='pass')
    save(directory / 'result.json', result)
    print(name + ': PASS (fresh source capture/replay/IR8/native, Int42, zero live ledger)', flush=True)
    return result


def negative(producer, output, env):
    directory = output / 'unused-type-error'
    directory.mkdir()
    inputs = directory / 'inputs'
    inputs.mkdir()
    (inputs / 'SharedPoly.emlf').write_text(SHARED_ID, encoding='utf-8')
    (inputs / 'unused-type-error.emlf').write_text(NEGATIVE, encoding='utf-8')
    out, err = run([str(producer), '--capture-shared'], directory, 'capture', cwd=inputs,
        env=env, stdin=NEGATIVE.encode(), wall=180, cpu=120, memory=4 << 30,
        stdout_limit=33*MIB, stderr_limit=MIB, expected=1)
    require(not out.read_bytes(), 'type error produced a diagnostic capture')
    message = err.read_text(encoding='utf-8')
    require(message == 'Inference: type constructor mismatch: Con "Bool" [] versus Con "Int" []\n',
            'negative did not report the expected ordinary Bool/Int mismatch before projection')
    result = {'case': 'unused-type-error', 'scope': SCOPE, 'status': 'pass',
              'ordinary_inference_rejection': True, 'native_started': False}
    save(directory / 'result.json', result)
    print('unused-type-error: PASS (ordinary inference rejects unused bad source)', flush=True)
    return result


def main():
    global SUITE_DEADLINE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', required=True, help='trusted official GHC 9.14.1 executable')
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'), help='one C compiler executable')
    parser.add_argument('--output', required=True, type=Path, help='new output directory; retained on failure')
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    for key in ('GHC_PACKAGE_PATH', 'GHC_PACKAGE_ENVIRONMENT'):
        env.pop(key, None)
    env.update(GHC_ENVIRONMENT='-', GHCRTS='', LC_ALL='C.UTF-8', PYTHONDONTWRITEBYTECODE='1')
    results = []
    started = time.monotonic()
    SUITE_DEADLINE = started + 1200
    build_tools.SUITE_DEADLINE = SUITE_DEADLINE
    try:
        ghc, cc = executable(args.ghc), executable(args.cc)
        producer = build_producer(ghc, cc, output, env)
        for case in CASES:
            results.append(positive(case, producer, cc, output, env))
        results.append(negative(producer, output, env))
        save(output / 'results.json', {'scope': SCOPE, 'status': 'pass', 'cases': results,
                                     'elapsed_seconds': time.monotonic() - started})
    except BaseException as exc:
        save(output / 'failure.json', {'scope': SCOPE, 'status': 'failed', 'completed': results,
             'error': '%s: %s' % (type(exc).__name__, exc), 'elapsed_seconds': time.monotonic() - started})
        raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
