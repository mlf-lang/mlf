#!/usr/bin/env python3
"""Finite O0/O2 prepared-vs-ordinary output controls, not timing qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/shared'))
from test_direct import CommandRunner


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def closure(source):
    pending, visited = [source], set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        for include in re.findall(r'^\s*#\s*include\s*"([^\"]+)"', path.read_text(), re.M):
            pending.append((path.parent / include).resolve(strict=True))
    return visited


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--clang', type=Path, required=True)
    parser.add_argument('--gc-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--route', choices=['selected', 'full', 'direct'], default='selected')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    compiler, clang = args.compiler.resolve(strict=True), args.clang.resolve(strict=True)
    gc = args.gc_prefix.resolve(strict=True)
    archive = (gc / 'lib/libgc.a').resolve(strict=True)
    pkg = Path(shutil.which('pkg-config')).resolve(strict=True)
    manifest_path = ROOT / 'benchmarks/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    workloads = [row for row in manifest['workloads'] if row['name'] != 'regex-redux']
    names = {'binary-trees', 'pidigits', 'n-body', 'fannkuch-redux', 'spectral-norm',
             'fasta', 'mandelbrot', 'reverse-complement', 'k-nucleotide'}
    require(len(workloads) == len(names) and {row['name'] for row in workloads} == names,
            'standalone workload inventory changed')
    inputs = {compiler, clang, pkg, archive, Path(__file__).resolve(),
              Path(sys.executable).resolve(), ROOT / 'tools/shared/test_direct.py', manifest_path,
              *gc.glob('include/**/*.h'), *closure((ROOT / 'runtime/mlf_runtime.c').resolve())}
    for row in workloads:
        inputs.update([ROOT / row['sources']['mlf'], ROOT / row['fixture']])
        if row.get('input_fixture'):
            inputs.add(ROOT / row['input_fixture'])
        for relative in [row['fixture']] + ([row['input_fixture']] if row.get('input_fixture') else []):
            require(sha(ROOT / relative) == manifest['pinned_sha256'][relative],
                    'fixture differs from manifest pin: ' + relative)
    pins = {str(path): sha(path) for path in sorted(inputs)}
    receipt = {'complete': False, 'performance_assertions': False,
               'scope': 'same compiler ordinary/prepared native outputs against nine pinned fixtures at O0/O2',
               'compiler_source_provenance_authenticated': False,
               'native_toolchain_closure_complete': False,
               'route': args.route, 'inputs': pins, 'commands': [], 'cases': []}

    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def run(label, command, data=None):
        command = list(map(str, command))
        process = subprocess.Popen(command, cwd=ROOT, env={**os.environ, 'LC_ALL': 'C.UTF-8'},
                                   stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = process.communicate(data, timeout=180)
        except BaseException:
            stdout, stderr, cleanup = CommandRunner.stop_group(process)
            receipt['cleanup'] = cleanup
            raise
        finally:
            if process.returncode is not None:
                receipt['commands'].append({'label': label, 'argv': command, 'exit': process.returncode})
                save()
        (out / (label + '.stdout')).write_bytes(stdout)
        (out / (label + '.stderr')).write_bytes(stderr)
        require(process.returncode == 0 and not stderr, 'command failed: ' + label)
        return stdout

    save()
    try:
        cflags = shlex.split(run('gmp-cflags', [pkg, '--cflags', 'gmp']).decode())
        libraries = shlex.split(run('gmp-libs', [pkg, '--libs', 'gmp']).decode())
        receipt['gmp_flags'] = {'cflags': cflags, 'libraries': libraries}
        snapshot = out / 'runtime'
        for path in closure((ROOT / 'runtime/mlf_runtime.c').resolve()):
            dest = snapshot / path.relative_to(ROOT / 'runtime')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())
        programs = {}
        operation = {'selected': '--emit-llvm-gc', 'full': '--full-emit-llvm-gc',
                     'direct': '--direct-emit-llvm-gc'}[args.route]
        for row in workloads:
            name = row['name']
            for route, emit_operation in [('ordinary', '--ordinary-emit-llvm-gc'), ('prepared', operation)]:
                llvm = out / (name + '-' + route + '.ll')
                llvm.write_bytes(run('emit-' + name + '-' + route,
                                     [compiler, emit_operation, ROOT / row['sources']['mlf']]))
                programs[name, route] = llvm
        for opt in ['0', '2']:
            runtime = out / ('runtime-O' + opt + '.o')
            run('runtime-O' + opt, [clang, '-O' + opt, '-std=c11', *cflags,
                                    '-I' + str(gc / 'include'), '-c', snapshot / 'mlf_runtime.c', '-o', runtime])
            for row in workloads:
                name = row['name']
                expected = (ROOT / row['fixture']).read_bytes()
                data = ((ROOT / row['input_fixture']).read_bytes() if row.get('input_fixture')
                        else (str(row['fixture_input']) + '\n').encode())
                outputs = []
                for route in ['ordinary', 'prepared']:
                    binary = out / (name + '-' + route + '-O' + opt)
                    run('link-' + binary.name, [clang, '-O' + opt, '-Wno-override-module',
                        programs[name, route], runtime, archive, *libraries, '-lm', '-lpthread', '-ldl', '-o', binary])
                    actual = run('run-' + binary.name, [binary], data)
                    require(actual == expected, 'pinned output differs: ' + binary.name)
                    outputs.append(actual)
                    receipt['cases'].append({'name': binary.name, 'passed': True,
                                             'stdout_sha256': hashlib.sha256(actual).hexdigest()})
                    save()
                require(outputs[0] == outputs[1], 'prepared output differs: ' + name)
        expected_cases = {name + '-' + route + '-O' + opt for name in names
                          for route in ['ordinary', 'prepared'] for opt in ['0', '2']}
        require(len(receipt['cases']) == len(expected_cases) and
                {row['name'] for row in receipt['cases']} == expected_cases,
                'native execution inventory changed')
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
            raise RuntimeError('native inputs changed during execution')
    print(out / 'receipt.json')


if __name__ == '__main__':
    main()
