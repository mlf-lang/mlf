#!/usr/bin/env python3
"""Prepare checked synthetic callable-import guard inputs, without C execution.

The default helper owns a pending scalar capture and is imported twice through
distinct aliases. The nested option checks (Int->Int)->(Int->Int) admission and
identity capture transport; that helper is not invoked by the nested fixture.
Neither fixture is original-source evidence.
"""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path[:0] = [str(BASE), str(HERE)]
from test_ir8_generic_callable_imports import callable_program
from test_ir8_generic_imports import generalize
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime
from source_build_v8 import require, save


def program(nested=False):
    p = callable_program(entries=2, captures=not nested)
    if nested:
        p['types']['G'] = {'tag': 'arrow', 'argument': 'F', 'result': 'F',
                          'protocol': 'repeat', 'result_identity': 'unknown'}
        p['signatures']['helper'].update(argument='^F', result='^F')
        for row in generalize(p)['imports'].values():
            row['layout'] = '^G'
        p['functions']['id']['captures']['captured']['layout'] = '^G'
        p['functions']['id']['body'] = [
            {'op': 'drop', 'value': 'x'}, {'op': 'drop', 'value': 'captured'},
            {'op': 'scalar', 'out': 'result', 'in': '$home', 'kind': 'i64', 'value': 42},
            {'op': 'return', 'value': 'result'}]
    p['entry'].remove({'op': 'drop', 'value': 'ab'})
    at = p['entry'].index({'op': 'force', 'out': 'answer', 'value': 'ai'})
    p['entry'][at+1:at+1] = [
        {'op': 'drop', 'value': 'answer'},
        {'op': 'force', 'out': 'answer_b', 'value': 'ab'}]
    require(p['entry'][-1] == {'op': 'finish_scalar', 'value': 'answer'}, 'fixture terminal changed')
    p['entry'][-1]['value'] = 'answer_b'
    return p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--nested', action='store_true')
    args = parser.parse_args()
    p = program(args.nested)
    resource = check_resources(p); metadata = check_metadata(p); emission = emit_runtime(p)
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    save(output/'program.json', p)
    save(output/'resources.json', json.loads(resource.derived_json))
    save(output/'metadata.json', json.loads(metadata.metadata_json))
    for name, field in (('ir8_packet_generated.h', 'packet_header'),
                        ('ir8_packet_generated.c', 'packet_source'),
                        ('ir8_runtime_generated.h', 'runtime_header'),
                        ('ir8_runtime_generated.c', 'runtime_source')):
        with (output/name).open('x') as stream:
            stream.write(getattr(emission, field))
    save(output/'fixture.json', {'scope': 'synthetic raw IR; host checks only',
         'nested_contract': args.nested, 'helper_has_pending_capture': not args.nested,
         'helper_invocation_covered': not args.nested,
         'both_complete_views_demanded': True, 'expected_scalar': 42,
         'compiler_executed': False, 'native_executed': False})
    print('Prepared checked synthetic callable import fixture', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
