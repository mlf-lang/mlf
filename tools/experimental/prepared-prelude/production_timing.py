#!/usr/bin/env python3
"""Time a correctness-qualified production candidate in an explicit quiet window."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_pins(pins):
    changed = [path for path, expected in pins.items() if sha(path) != expected]
    if changed:
        raise RuntimeError('qualified inputs changed: ' + repr(changed))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controls', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    controls_path = args.controls.resolve(strict=True)
    controls = json.loads(controls_path.read_text())
    if not controls['complete'] or not controls['immutable_inputs_verified_after']:
        raise RuntimeError('production correctness controls are incomplete')
    candidate_path = Path(controls['candidate_receipt'])
    candidate = json.loads(candidate_path.read_text())
    if not candidate['complete'] or not candidate['immutable_inputs_verified_after']:
        raise RuntimeError('production candidate is incomplete')
    semantic_path = Path(controls['results']['semantic']['receipt'])
    semantic = json.loads(semantic_path.read_text())
    harness = controls_path.parent / 'production-control'
    compiler = Path(candidate['outputs']['emlf']['path'])
    names = ['binary-trees', 'n-body', 'pidigits']
    sources = {name: controls_path.parent / 'suite-source/benchmarks' / name / 'mlf/main.emlf'
               for name in names}
    pins = {**candidate['inputs'], **controls['inputs'], **semantic['inputs']}
    require_pins(pins)
    for path in [Path(__file__).resolve(), controls_path, candidate_path, semantic_path, harness,
                 compiler, *sources.values()]:
        digest = sha(path)
        if str(path) in pins and pins[str(path)] != digest:
            raise RuntimeError('conflicting qualification pin: ' + str(path))
        pins[str(path)] = digest
    if sha(compiler) != candidate['outputs']['emlf']['sha256']:
        raise RuntimeError('candidate executable no longer matches its build receipt')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    receipt = {
        'complete': False,
        'scope': 'fresh-process ordinary frontend versus actual production CLI, source read through LLVM write',
        'full_native_compile_claim': False,
        'filesystem_cache_cold_claim': False,
        'closed_toolchain_qualification': candidate['closed_toolchain_qualification'],
        'context_boundary': 'current checkCompilerPrelude Either completed and complete contracts counted; no user source parsed',
        'ordinary_boundary': 'same frozen canonical modules in qualified host harness; compileProgramWithPrelude then emitCheckedChunks',
        'production_boundary': 'actual MLF.Entry.Emlf --emit-llvm-gc, including file read, parse, prepared admission, whole root inference and full linked check',
        'controls_receipt': str(controls_path), 'candidate_receipt': str(candidate_path),
        'builtin_identity': controls['builtin_identity'], 'inputs': pins, 'samples': []}

    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def run(label, command):
        stdout_path, stderr_path = out / (label + '.stdout'), out / (label + '.stderr')
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        started = time.perf_counter()
        with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
            result = subprocess.run(list(map(str, command)), stdout=stdout, stderr=stderr,
                cwd=controls['source'], env={**os.environ, 'LC_ALL': 'C.UTF-8', 'GHCRTS': ''}, timeout=180)
        elapsed = time.perf_counter() - started
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        receipt['samples'].append({'label': label, 'argv': list(map(str, command)),
            'wall_seconds': elapsed,
            'cpu_seconds': after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
            'exit': result.returncode, 'stdout_sha256': sha(stdout_path)})
        save()
        if result.returncode or stderr_path.stat().st_size:
            raise RuntimeError('timed command failed: ' + label)

    save()
    try:
        for repeat in range(3):
            run('context-' + str(repeat), [harness, '--prepared-context'])
        for name in names:
            for repeat in range(3):
                routes = ['ordinary', 'production'] if repeat % 2 == 0 else ['production', 'ordinary']
                for route in routes:
                    command = ([harness, '--ordinary-emit-llvm-gc', sources[name]] if route == 'ordinary'
                               else [compiler, '--emit-llvm-gc', sources[name]])
                    run(name + '-' + route + '-' + str(repeat), command)
        medians = {}
        for prefix in ['context'] + [name + '-' + route for name in names for route in ['ordinary', 'production']]:
            rows = [row for row in receipt['samples'] if row['label'].rsplit('-', 1)[0] == prefix]
            if len(rows) != 3 or len({row['stdout_sha256'] for row in rows}) != 1:
                raise RuntimeError('missing samples or unstable output: ' + prefix)
            medians[prefix] = statistics.median(row['wall_seconds'] for row in rows)
        equal = {name: len({row['stdout_sha256'] for row in receipt['samples']
                          if row['label'].startswith(name + '-')}) == 1 for name in names}
        if not all(equal.values()):
            raise RuntimeError('ordinary and actual production LLVM outputs differ: ' + repr(equal))
        receipt.update(median_wall_seconds=medians, llvm_byte_equal_across_routes=equal,
            production_over_ordinary={name: medians[name + '-production'] / medians[name + '-ordinary']
                                      for name in names}, complete=True)
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
