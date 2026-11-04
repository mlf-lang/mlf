#!/usr/bin/env python3
"""Emit two host-checked synthetic generic scalar capture guard fixtures.

This prepares raw IR, reports and C/H only. It never invokes a compiler, original
producer or native target. Use PYTHONHASHSEED=0 for exact host-work reproduction.
An output directory must be fresh; partial output is retained on any failure.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from test_ir8_generic_imports import import_program, generalize
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime
from source_build_v8 import require

MIB = 1048576


def paired_captures(program, scalar_type):
    """Two logical slots alias one actual owner; import02 stays unused."""
    intro = generalize(program)
    require(list(intro['imports']) == ['import00', 'import01', 'import02'],
            'three-entry base recipe changed')
    intro['body'][0]['captures'] = {'captured_a': 'import00', 'captured_b': 'import01'}
    program['functions']['id']['captures'] = {
        name: {'layout': '^' + scalar_type, 'relation': 'down'}
        for name in ('captured_a', 'captured_b')}
    program['functions']['id']['body'] = [
        {'op': 'drop', 'value': 'x'}, {'op': 'drop', 'value': 'captured_b'},
        {'op': 'return', 'value': 'captured_a'}]


def pending_int_program():
    p = import_program('i64', True, 3)
    paired_captures(p, 'I')
    p['types']['II'] = {'tag': 'arrow', 'argument': 'I', 'result': 'I',
                       'protocol': 'repeat', 'result_identity': 'unknown'}
    p['types']['AA']['result'] = 'II'
    p['signatures']['id']['result'] = '^II'
    p['signatures']['inner'] = {'argument': '^I', 'result': '^I',
                              'protocol': 'repeat', 'result_identity': 'unknown'}
    p['functions']['inner'] = {
        'signature': 'inner', 'parameter': 'q',
        'captures': {name: {'layout': '^I', 'relation': 'down'}
                     for name in ('captured_a', 'captured_b')},
        'type_scope': 'S', 'body': [
            {'op': 'drop', 'value': 'q'}, {'op': 'drop', 'value': 'captured_b'},
            {'op': 'return', 'value': 'captured_a'}]}
    p['functions']['id']['body'] = [
        {'op': 'drop', 'value': 'x'},
        {'op': 'closure', 'out': 'inner', 'in': '$home', 'function': 'inner',
         'captures': {'captured_a': 'captured_a', 'captured_b': 'captured_b'}},
        {'op': 'drop', 'value': 'captured_a'}, {'op': 'drop', 'value': 'captured_b'},
        {'op': 'return', 'value': 'inner'}]
    at = next(i for i, instruction in enumerate(p['entry']) if instruction.get('out') == 'ab') + 1
    p['entry'][at:at] = [
        {'op': 'force', 'out': 'bool_view_child', 'value': 'ab'},
        {'op': 'drop', 'value': 'bool_view_child'},
        {'op': 'application', 'out': 'inner_application', 'in': 'home',
         'function': 'ai', 'argument': 'i'}, {'op': 'drop', 'value': 'ai'}]
    p['entry'] = [instruction for instruction in p['entry']
                  if not (instruction['op'] == 'drop' and instruction.get('value') == 'ab')]
    next(instruction for instruction in p['entry']
         if instruction['op'] == 'force' and instruction.get('out') == 'answer')['value'] = 'inner_application'
    return p


def ready_bool_program():
    p = import_program('bool', False, 3)
    paired_captures(p, 'B')
    at = next(i for i, instruction in enumerate(p['entry']) if instruction.get('out') == 'answer') + 1
    p['entry'][at:at] = [
        {'op': 'drop', 'value': 'answer'},
        {'op': 'scalar', 'out': 'synthetic_Int42_marker_after_Bool_force',
         'in': 'home', 'kind': 'i64', 'value': 42}]
    require(p['entry'][-1] == {'op': 'finish_scalar', 'value': 'answer'},
            'base terminal recipe changed')
    p['entry'][-1]['value'] = 'synthetic_Int42_marker_after_Bool_force'
    return p


def structure(resource, metadata, emitted, *, pending):
    intro = next(row for row in resource['instructions'] if row['op'] == 'generalize')
    require(len(intro['inputs']) == 4 and len(intro['outputs']) == 4, 'import fact count differs')
    parents, aliases = intro['inputs'][1:], intro['outputs'][1:]
    require(len({row['node'] for row in parents + aliases}) == 1, 'aliases changed actual source node')
    require(len({row['capability'] for row in parents}) == 1, 'imports no longer share parent owner')
    require(len({row['capability'] for row in aliases}) == 3 and
            len({row['storage'] for row in aliases}) == 3, 'child owners are not independently retained')
    for alias in aliases:
        for key in parents[0]:
            if key not in ('role', 'capability', 'storage'):
                require(alias[key] == parents[0][key], 'import copy equation changed: ' + key)
    require(parents[0]['capability'] not in {row['capability'] for row in aliases},
            'parent owner was moved instead of retained')
    origin = resource['provenance'][parents[0]['provenance']]['value']
    site = resource['sites'][origin['site']]
    require(origin['context'] == {'kind': 'concrete'} and site['type_scope'] is None,
            'source is not the original concrete allocation')
    require(site['category'] == ('APPLICATION' if pending else 'SCALAR') and
            parents[0]['ready'] is (not pending), 'source category/readiness changed')
    closure = next(row for row in resource['instructions'] if row['op'] == 'closure'
                   and len(row['path']['segments']) > 1 and row['path']['root'] == 'entry')
    require([row['node'] for row in closure['inputs'][1:]] == [parents[0]['node']] * 2,
            'two captures no longer share actual source')
    require([row['capability'] for row in closure['inputs'][1:]] ==
            [row['capability'] for row in aliases[:2]], 'capture-to-import association changed')
    dropped = {row['inputs'][0]['capability'] for row in resource['instructions'] if row['op'] == 'drop'}
    require(all(row['capability'] in dropped for row in aliases + parents), 'owner discharge missing')
    require(not any(row['capability'] == aliases[2]['capability']
                    for instruction in resource['instructions'] if instruction['op'] in ('closure', 'thunk')
                    for row in instruction['inputs'][1:]), 'unused import became a published capture')
    accesses = [row for row in metadata['accesses'] if row['site'] == site['id']]
    require(len(accesses) == 1, 'source Access was cloned/projected')
    access = accesses[0]
    require((access['origin_env'], access['use_env'], access['mode'], access['scheme']) == (0, 0, 'MONO', None),
            'source actual E0 Access changed')
    require(any(row['source_access'] == access['id'] and row['projection_env'] is None and
                row['result_access'] == access['id'] for row in metadata['transports']),
            'exact identity transport missing')
    begin = emitted.runtime_source.index('rt8_generic_begin(ctx,')
    seal = emitted.runtime_source.index('rt8_generic_seal(ctx,', begin)
    segment = emitted.runtime_source[begin:seal]
    require(segment.count('rt8_retain(ctx,') == 3 and segment.count('rt8_drop(ctx,') == 3,
            'post-begin retain/discharge count changed')
    require(segment.index('rt8_retain(ctx,') < segment.index('rt8_closure(ctx,') and
            'rt8_force(ctx,' not in segment, 'capture construction began demanding the scalar')
    return {'category': site['category'], 'ready': parents[0]['ready'],
            'imports': 3, 'capture_slots': 2, 'unused_imports': 1,
            'expected_terminal_scalar': 42,
            'terminal_is_synthetic_marker': not pending}


def emit_fixture(output, name, program, *, pending):
    directory = output / name
    directory.mkdir(exist_ok=False)
    generated = directory / 'generated'
    generated.mkdir(exist_ok=False)
    total = 0

    def write(path, text):
        nonlocal total
        data = text.encode('utf-8')
        require(len(data) <= 32*MIB and total + len(data) <= 32*MIB,
                'fixed fixture output exceeds32MiB')
        with path.open('xb') as stream:
            stream.write(data)
        total += len(data)

    # Persist input first. Any checking/emission failure leaves its real inputs
    # and completed reports in place; never overwrite or delete a failed run.
    canonical = json.dumps(program, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    write(directory / 'program.json', canonical)
    resource = check_resources(program)
    require(resource.canonical_json == canonical, 'canonical fixture encoding differs')
    write(directory / 'resources.json', resource.derived_json)
    write(directory / 'resource-report.json', json.dumps(dict(resource.report()), sort_keys=True, indent=2) + '\n')
    metadata = check_metadata(program)
    write(directory / 'metadata.json', metadata.metadata_json)
    write(directory / 'metadata-report.json', json.dumps(dict(metadata.report()), sort_keys=True, indent=2) + '\n')
    emitted = emit_runtime(program)
    require(emitted.canonical_ir_json == canonical and emitted.metadata_json == metadata.metadata_json,
            'fresh emitter admission differs')
    proof = structure(json.loads(resource.derived_json), json.loads(metadata.metadata_json), emitted, pending=pending)
    for filename, text in (
            ('ir8_packet_generated.h', emitted.packet_header),
            ('ir8_packet_generated.c', emitted.packet_source),
            ('ir8_runtime_generated.h', emitted.runtime_header),
            ('ir8_runtime_generated.c', emitted.runtime_source),
            ('runtime-emission.json', emitted.manifest_json),
            ('packet-emission.json', emitted.packet_manifest_json)):
        write(generated / filename, text)
    return {'fixture': name, 'files': 11, 'bytes': total, 'structure': proof}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require(os.environ.get('PYTHONHASHSEED') == '0', 'launch with PYTHONHASHSEED=0 for exact host-work reproduction')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    fixtures = [emit_fixture(output, 'pending-int-application-aliases', pending_int_program(), pending=True),
                emit_fixture(output, 'ready-bool-aliases', ready_bool_program(), pending=False)]
    print(json.dumps({'status': 'host-checked-and-emitted', 'native_executed': False,
                      'source_admitted': False, 'fixtures': fixtures,
                      'note': 'The ready-Bool Int42 marker does not prove the Bool truth value.'}, sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
