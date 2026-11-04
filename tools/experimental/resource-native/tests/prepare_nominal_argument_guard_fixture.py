#!/usr/bin/env python3
"""Prepare a synthetic raw-IR DATA shared-argument guard pair, not source evidence.

Reuse the host-tested generic application. Its nominal answer is genuinely
forced and dropped; a separate scalar42 is allocated before home is dropped.
Fresh resource checking and ordinary emission produce the actual callback C.
No compiler, native program, source producer or evaluator is invoked here.
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from test_ir8_nominal_arguments import nominal_application
from resource_ir_v8.checker import check_resources
from resource_ir_v8.runtime_emit import emit_runtime
from source_build_v8 import require, save


def program():
    raw, atom = nominal_application(family=False)
    require(atom == 'Box', 'expected host DATA fixture')
    require(raw['entry'][-4:] == [
        {'op': 'force', 'out': 'answer', 'value': 'ai'},
        {'op': 'drop', 'value': 'home'},
        {'op': 'drop', 'value': 'answer'}, {'op': 'finish'}],
        'host fixture changed; inspect ownership before adapting it')
    raw['entry'][-3:] = [
        {'op': 'drop', 'value': 'answer'},
        {'op': 'scalar', 'out': 'guard_result', 'in': 'home', 'kind': 'i64', 'value': 42},
        {'op': 'drop', 'value': 'home'},
        {'op': 'finish_scalar', 'value': 'guard_result'}]
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    raw = program()
    save(output / 'synthetic-program.json', raw)
    checked = check_resources(raw)
    save(output / 'resources.json', dict(checked.report()))
    emitted = emit_runtime(raw)
    for name, attr in (('ir8_packet_generated.h', 'packet_header'),
                       ('ir8_packet_generated.c', 'packet_source'),
                       ('ir8_runtime_generated.h', 'runtime_header'),
                       ('ir8_runtime_generated.c', 'runtime_source')):
        with (output / name).open('x', encoding='utf-8') as stream:
            stream.write(getattr(emitted, attr))
    print(json.dumps({'status': 'host-checked-and-emitted',
                      'scope': 'synthetic raw IR; not source or native evidence',
                      'output': str(output), 'native_executed': False}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
