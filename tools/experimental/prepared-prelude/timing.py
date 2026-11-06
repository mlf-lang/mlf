#!/usr/bin/env python3
"""Fresh-process frontend timings; run only under a separately granted quiet window."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--routes', nargs='+', choices=['ordinary', 'full', 'selected', 'direct'],
                        default=['ordinary', 'selected'])
    args = parser.parse_args()
    if len(args.routes) != len(set(args.routes)) or len(args.routes) < 2:
        parser.error('--routes requires at least two distinct routes')
    compiler = args.compiler.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    names = ['binary-trees', 'n-body', 'pidigits']
    sources = {name: ROOT / 'benchmarks' / name / 'mlf/main.emlf' for name in names}
    pins = {str(path): sha(path) for path in [compiler, Path(__file__), *sources.values()]}
    receipt = {'complete': False, 'scope': 'fresh-process end-to-end frontend with source parse and complete LLVM output',
               'full_native_compile_claim': False, 'filesystem_cache_cold_claim': False,
               'context_boundary': 'restoreCompiled Either completed, complete source-contract map counted; no source parsed',
               'routes': args.routes, 'inputs': pins, 'samples': []}

    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def run(label, command):
        stdout_path, stderr_path = out / (label + '.stdout'), out / (label + '.stderr')
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        start = time.perf_counter()
        with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
            result = subprocess.run(list(map(str, command)), stdout=stdout, stderr=stderr,
                                    cwd=ROOT, env={**os.environ, 'LC_ALL': 'C.UTF-8', 'GHCRTS': ''}, timeout=180)
        elapsed = time.perf_counter() - start
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        row = {'label': label, 'argv': list(map(str, command)), 'wall_seconds': elapsed,
               'cpu_seconds': after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
               'exit': result.returncode, 'stdout_sha256': sha(stdout_path)}
        receipt['samples'].append(row)
        save()
        if result.returncode or stderr_path.stat().st_size:
            raise RuntimeError('timed command failed: ' + label)

    save()
    try:
        for repeat in range(3):
            run('context-' + str(repeat), [compiler, '--prepared-context'])
        for name in names:
            for repeat in range(3):
                routes = args.routes if repeat % 2 == 0 else list(reversed(args.routes))
                for route in routes:
                    operation = {'ordinary': '--ordinary-emit-llvm-gc', 'full': '--full-emit-llvm-gc',
                                 'selected': '--emit-llvm-gc', 'direct': '--direct-emit-llvm-gc'}[route]
                    run(name + '-' + route + '-' + str(repeat), [compiler, operation, sources[name]])
        medians = {}
        for prefix in ['context'] + [name + '-' + route for name in names for route in args.routes]:
            rows = [row for row in receipt['samples'] if row['label'].rsplit('-', 1)[0] == prefix]
            if len(rows) != 3 or len({row['stdout_sha256'] for row in rows}) != 1:
                raise RuntimeError('missing sample or unstable frontend output: ' + prefix)
            medians[prefix] = statistics.median(row['wall_seconds'] for row in rows)
        receipt['median_wall_seconds'] = medians
        reference = args.routes[0]
        receipt['ratios_to_' + reference] = {
            name: {route: medians[name + '-' + route] / medians[name + '-' + reference]
                   for route in args.routes[1:]} for name in names}
        receipt['llvm_byte_equal_across_routes'] = {
            name: len({row['stdout_sha256'] for row in receipt['samples']
                       if row['label'].startswith(name + '-')}) == 1 for name in names}
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
            raise RuntimeError('timing inputs changed during execution')
    print(json.dumps(receipt['median_wall_seconds'], indent=2))


if __name__ == '__main__':
    main()
