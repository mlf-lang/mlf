#!/usr/bin/env python3
"""Emit one host-checked synthetic nested-arrow/DATA/SUM guard pair.

This is raw IR fixture preparation, not source, native, evaluator or GC evidence.
No compiler or target is invoked. The ordinary emitter performs fresh admission.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from test_ir8_arrow_arguments import arrow
from test_ir8_nominal_arguments import raw, nominal
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime
from source_build_v8 import require, save


def program():
    p = raw('ready_shared_identity_two_views')
    nominal(p, 'Box', alias='N')
    nominal(p, 'Chain', family=True, alias='L')
    arrow(p, 'DataFn', 'N', 'I')
    arrow(p, 'SumFn', 'L', 'I')
    arrow(p, 'Nested', 'DataFn', 'SumFn')
    # b is genuinely dead in the unchanged abstract identity RHS/body.
    p['schemes']['S']['parameters'] = 2
    p['types']['Z'] = {'tag': 'rigid', 'scheme': 'S', 'index': 1}
    p['instantiations']['int_use']['arguments'] = ['Nested', 'I']
    p['instantiations']['bool_use']['arguments'] = ['B', 'Nested']
    for name, argument, result in (
            ('data_const', 'Box', '#i64'),
            ('sum_const', '%Chain', '#i64'),
            ('make_sum', '@data_const', '@sum_const')):
        p['signatures'][name] = {'argument': argument, 'result': result,
            'protocol': 'repeat', 'result_identity': 'unknown'}
        body = [{'op': 'drop', 'value': 'x'}]
        if name == 'make_sum':
            body.append({'op': 'closure', 'out': 'result', 'in': '$home',
                         'function': 'sum_const', 'captures': {}})
        else:
            body.append({'op': 'scalar', 'out': 'result', 'in': '$home',
                         'kind': 'i64', 'value': 42})
        body.append({'op': 'return', 'value': 'result'})
        p['functions'][name] = {'signature': name, 'type_scope': None,
            'parameter': 'x', 'captures': {}, 'body': body}
    for index, instruction in enumerate(p['entry']):
        if instruction['op'] == 'scalar' and instruction['kind'] == 'i64':
            p['entry'][index] = {'op': 'closure', 'out': instruction['out'],
                'in': 'home', 'function': 'make_sum', 'captures': {}}
    require(p['entry'][-3:] == [
        {'op': 'force', 'out': 'answer', 'value': 'ai'},
        {'op': 'drop', 'value': 'home'},
        {'op': 'finish_scalar', 'value': 'answer'}], 'base ownership fixture changed')
    p['entry'][-2:] = [
        {'op': 'closure', 'out': 'data_arg', 'in': 'home', 'function': 'data_const', 'captures': {}},
        {'op': 'application', 'out': 'sum_application', 'in': 'home',
         'function': 'answer', 'argument': 'data_arg'},
        {'op': 'drop', 'value': 'answer'},
        {'op': 'drop', 'value': 'data_arg'},
        {'op': 'force', 'out': 'sum_result', 'value': 'sum_application'},
        {'op': 'drop', 'value': 'sum_result'},
        {'op': 'scalar', 'out': 'guard_result', 'in': 'home', 'kind': 'i64', 'value': 42},
        {'op': 'drop', 'value': 'home'},
        {'op': 'finish_scalar', 'value': 'guard_result'}]
    return p


def structure(metadata):
    types = metadata['types']
    ids = {row['atom']: row['id'] for row in types if row['tag'] == 'closed'}
    equations = {(row['argument'], row['result']): row['id'] for row in types if row['tag'] == 'arrow'}
    data_fn = equations[(ids['Box'], ids['#i64'])]
    sum_fn = equations[(ids['%Chain'], ids['#i64'])]
    nested = equations[(data_fn, sum_fn)]
    depths = []
    for row in types:
        if row['tag'] == 'arrow':
            require(row['argument'] < row['id'] and row['result'] < row['id'], 'non-topological Type')
            require((row['protocol'], row['result_identity']) == ('repeat', 'unknown'), 'arrow contract changed')
            depths.append(1 + max(depths[row['argument']], depths[row['result']]))
        else:
            depths.append(1)
    require(depths[nested] == 3 and max(depths) == 4, 'nested/substituted depth changed')
    scheme = metadata['schemes'][0]
    body = types[scheme['body']]
    require(scheme['parameters'] == 2 and body['argument'] == body['result'], 'identity scheme changed')
    rigid = types[body['argument']]
    require((rigid['tag'], rigid['scheme'], rigid['index']) == ('rigid', scheme['id'], 0), 'body uses dead parameter')
    uses = {use['name']: use for use in metadata['uses']}
    expected = {'int_use': [nested, ids['#i64']], 'bool_use': [ids['#bool'], nested]}
    for name, vector in expected.items():
        use = uses[name]
        require(use['arguments'] == vector, 'complete ordered vector changed')
        require(metadata['environments'][use['env']]['arguments'] == vector, 'Env lost exact coordinates')
        require((types[use['result_type']]['argument'], types[use['result_type']]['result']) == (vector[0], vector[0]),
                'dead coordinate changed substituted body')
    needed = {nested, data_fn, sum_fn, ids['Box'], ids['%Chain'], ids['#i64']}
    resolutions = {(row['type'], row['env']): row['result'] for row in metadata['type_resolutions']}
    require(all(resolutions[(typ, 0)] == typ for typ in needed), 'missing exact E0 dependency')
    shapes = metadata['shapes']
    for typ in (nested, data_fn, sum_fn):
        shape = next(row for row in shapes if row['source'] == {'kind': 'canonical-arrow', 'type': typ})
        require(shape['kind'] == 'REPEAT', 'wrong canonical arrow kind')
    for atom, kind in (('Box', 'DATA'), ('%Chain', 'SUM')):
        shape = next(row for row in shapes if row['source'] == {'kind': 'legacy', 'reference': atom})
        require(shape['kind'] == kind, 'wrong exact nominal shape')
    return {'scheme': 'forall a b. a -> a', 'dead_parameter_indices': [1],
        'coordinate': '(Box -> Int) -> (Chain -> Int)', 'coordinate_depth': depths[nested],
        'maximum_type_depth': max(depths), 'nested_type': nested,
        'child_arrow_types': [data_fn, sum_fn], 'nominal_atoms': ['Box', '%Chain'],
        'full_vectors': expected, 'environments': {name: use['env'] for name, use in uses.items()},
        'generic_codes': [row['name'] for row in metadata['codes'] if row['scope'] is not None],
        'expected_terminal_scalar': 42, 'nominal_fields_unfolded_by_argument_type_walk': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    p = program()
    save(output / 'synthetic-program.json', p)
    resource = check_resources(p)
    metadata = check_metadata(p)
    data = json.loads(metadata.metadata_json)
    proof = structure(data)
    emitted = emit_runtime(p)
    require(emitted.metadata_json == metadata.metadata_json, 'fresh emitted metadata differs')
    save(output / 'resources.json', dict(resource.report()))
    files = {'metadata.json': metadata.metadata_json,
        'packet-manifest.json': emitted.packet_manifest_json,
        'runtime-manifest.json': emitted.manifest_json,
        'ir8_packet_generated.h': emitted.packet_header,
        'ir8_packet_generated.c': emitted.packet_source,
        'ir8_runtime_generated.h': emitted.runtime_header,
        'ir8_runtime_generated.c': emitted.runtime_source}
    for name, text in files.items():
        with (output / name).open('x', encoding='utf-8') as stream:
            stream.write(text)
    save(output / 'host-proof.json', {
        'status': 'resource-checked-metadata-checked-emitted-uncompiled',
        'scope': 'synthetic native-guard fixture only; not source/evaluation/GC evidence',
        'native_executed': False, 'structure': proof,
        'ir_sha256': metadata.ir_sha256, 'metadata_sha256': metadata.metadata_sha256,
        'metadata_counts': dict(metadata.counts),
        'metadata_host_statistics': dict(dict(metadata.report())['host_statistics']),
        'emitter_statistics': dict(emitted.statistics),
        'generated': {name: {'bytes': len(text.encode()), 'sha256': hashlib.sha256(text.encode()).hexdigest()}
                      for name, text in files.items() if name.startswith('ir8_')}})
    print(json.dumps({'status': 'host-checked-and-emitted', 'output': str(output),
                      'structure': proof, 'native_executed': False}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
