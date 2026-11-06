#!/usr/bin/env python3
"""Compare direct and synthetic import graph counts; not a timing benchmark."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = {name: ROOT / 'benchmarks' / name / 'mlf/main.emlf'
               for name in ['binary-trees', 'n-body', 'pidigits']}
    pins = {str(path): sha(path) for path in [compiler, Path(__file__), *sources.values()]}
    receipt = {'complete': False, 'performance_assertions': False, 'inputs': pins, 'cases': [],
               'fields': ['initial_graph_nodes', 'initial_equalities', 'initial_solve_steps',
                          'allocated_import_signature_nodes']}

    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    save()
    try:
        for name, source in sources.items():
            rows = {}
            for route in ['full', 'selected', 'direct']:
                command = [str(compiler), '--' + route + '-counts', str(source)]
                result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
                (out / (name + '-' + route + '.stdout')).write_bytes(result.stdout)
                (out / (name + '-' + route + '.stderr')).write_bytes(result.stderr)
                if result.returncode or result.stderr:
                    raise RuntimeError('count operation failed: ' + name + '-' + route)
                values = ast.literal_eval(result.stdout.decode())
                if not isinstance(values, list) or len(values) != 4 or not all(type(x) is int and x >= 0 for x in values):
                    raise RuntimeError('invalid count output')
                rows[route] = values
                receipt['cases'].append({'name': name, 'route': route, 'counts': values, 'argv': command})
                save()
            if rows['selected'][3] != rows['direct'][3]:
                raise RuntimeError('direct route changed signature graph allocation: ' + name)
            if not all(rows['direct'][index] < rows['selected'][index] for index in [0, 2]):
                raise RuntimeError('direct route did not remove dummy graph/steps: ' + name)
        receipt['complete'] = True
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        changed = [path for path, expected in pins.items() if sha(path) != expected]
        receipt['immutable_inputs_verified_after'] = not changed
        if changed:
            receipt.update(complete=False, changed_inputs=changed)
        save()
        if changed:
            raise RuntimeError('graph count inputs changed')
    print(out / 'receipt.json')


if __name__ == '__main__':
    main()
