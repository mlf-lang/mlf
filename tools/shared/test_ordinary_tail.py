#!/usr/bin/env python3
"""Ordinary boxed worker tail returns, demand boundaries and GC survival.

Checks independent literal/formula outputs at O0/O2, including deep mutual
recursion, captured values, escaping closures and lazy pattern defaults.
This is a focused gate, not native self-bootstrap or whole-corpus qualification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess

from test_direct import CommandRunner, authenticate_build, sha
from test_native_string_index import local_c_closure, require, resolve_tool

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tools/shared/fixtures/native/OrdinaryTail.emlf'
GC_DRIVER = ROOT / 'tools/shared/fixtures/native/ordinary_tail_gc.c'
NONRETURNING = 'let rec { loop x = loop x } in do { putStrLn "forcing"; printInt (loop 0) }'


def cases():
    result = []
    for n in [0, 1, 65536, 262144]:
        values = [('mutual', n), ('case', n * (n + 1) // 2),
                  ('capture', n + 17), ('escape', 2 * (n + 17) + 8),
                  ('default-unused', n), ('default-bound', n * (n + 1) // 2)]
        for mode, value in values:
            result.append((f'{mode}-{n}', [mode, str(n), '17'], f'{value}\n'.encode()))
    # Different private arities intentionally retain an ordinary call. Exercise
    # that boundary without claiming constant stack for the mismatched cycle.
    for n in [0, 1, 1024]:
        result.append((f'abi-{n}', ['abi', str(n), '17'], b'41\n'))
    for n in [0, 1, 65536]:
        value = sum(1 + len(str(i)) for i in range(1, n + 1))
        result.append((f'gc-{n}', ['gc', str(n), '17'], f'{value}\n'.encode()))
    return result


def worker_edges(llvm):
    workers = {
        match[1]: (len(re.findall(r'ptr %', match[2])), match[3])
        for match in re.finditer(
            r'^define private ptr @(mlf\.worker\.\d+)\(([^\n]*)\)(?: noinline)? \{\n(.*?)^\}',
            llvm, re.M | re.S)
    }
    edges = []
    for caller, (arity, body) in workers.items():
        for call in re.finditer(
                r'(?m)^  (%\w+) = (musttail )?call ptr @(mlf\.worker\.\d+)\(([^\n]*)\)\n', body):
            callee, tail = call[3], bool(call[2])
            require(callee in workers, 'worker call lacks definition')
            target_arity = workers[callee][0]
            if tail:
                require(arity == target_arity, 'musttail changes the pointer ABI')
                require(body[call.end():].startswith('  ret ptr ' + call[1] + '\n'),
                        'musttail does not immediately return its result')
            edges.append({'caller': caller, 'callee': callee,
                          'caller_arity': arity, 'callee_arity': target_arity,
                          'musttail': tail})
    require(any(x['musttail'] and x['caller'] == x['callee'] for x in edges),
            'missing recursive tail control')
    require(any(x['musttail'] and x['caller'] != x['callee'] for x in edges),
            'missing cross-worker tail control')
    require(any(not x['musttail'] and x['caller_arity'] != x['callee_arity'] for x in edges),
            'missing different-ABI fallback control')
    return edges


def observe_nonreturning(runner, binary):
    seconds = 2
    try:
        completed = subprocess.run([binary], cwd=runner.root, capture_output=True, timeout=seconds)
        code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as expired:
        code, stdout, stderr = None, expired.stdout or b'', expired.stderr or b''
    captures = {}
    for suffix, data in [('stdout', stdout), ('stderr', stderr)]:
        path = runner.output / (binary.name + '.' + suffix)
        path.write_bytes(data)
        captures[suffix] = {'path': str(path), 'sha256': sha(path)}
    runner.receipt['nonreturning_cases'].append(
        {'binary': str(binary), 'exit_code': code, 'timeout_seconds': seconds, **captures})
    runner.save()
    require(code is None and stdout == b'forcing\n' and stderr == b'',
            binary.name + ' did not remain live after reaching the recursive demand')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True)
    parser.add_argument('--producer-receipt', type=Path)
    parser.add_argument('--clang', default='clang')
    parser.add_argument('--gc-prefix', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output != ROOT and not ROOT.is_relative_to(output), 'output cannot contain checkout')
    output.mkdir(parents=True, exist_ok=False)
    record = {'complete': False, 'status': 'running', 'commands': [], 'inputs': {},
              'artifacts': {}, 'cases': [], 'gc_cases': [], 'nonreturning_cases': [],
              'scope': 'ordinary boxed worker tail returns and retained heap graphs',
              'full_corpus_qualification': False, 'native_toolchain_closure_complete': False,
              'compiler_source_provenance_authenticated': False}

    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')

    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        compiler = resolve_tool(args.compiler)
        clang, pkg = resolve_tool(args.clang), resolve_tool('pkg-config')
        gc = args.gc_prefix.resolve(strict=True)
        archive = gc / 'lib/libgc.a'
        sources = local_c_closure((ROOT / 'runtime/mlf_runtime.c').resolve())
        inputs = [compiler, clang, pkg, archive, FIXTURE, GC_DRIVER, Path(__file__).resolve(),
                  ROOT / 'tools/shared/test_direct.py',
                  ROOT / 'tools/shared/test_native_string_index.py',
                  *sources, *sorted((gc / 'include').rglob('*.h'))]
        if args.producer_receipt:
            receipt = args.producer_receipt.resolve(strict=True)
            authenticate_build(receipt, compiler.parent)
            inputs.append(receipt)
            record['compiler_source_provenance_authenticated'] = True
        record['inputs'] = {str(path): sha(path) for path in inputs}
        cflags = shlex.split(runner.run('gmp-cflags', [pkg, '--cflags', 'gmp']).stdout.decode())
        libraries = shlex.split(runner.run('gmp-libs', [pkg, '--libs', 'gmp']).stdout.decode())
        record['gmp_flags'] = {'cflags': cflags, 'libraries': libraries}
        result = runner.run('emit', [compiler, '--no-prelude', '--emit-llvm-gc', FIXTURE], timeout=240)
        llvm = output / 'program.ll'
        llvm.write_bytes(result.stdout)
        record['worker_edges'] = worker_edges(result.stdout.decode())
        gc_text, count = re.subn(r'(?m)^define i32 @main\(',
                                 'define i32 @tail_program_main(', result.stdout.decode())
        require(count == 1, 'GC harness could not isolate the native main symbol')
        gc_llvm = output / 'gc.ll'
        gc_llvm.write_text(gc_text)
        runtime = output / 'runtime.o'
        runner.run('runtime', [clang, '-O2', '-std=c11', '-I' + str(gc / 'include'),
                   *cflags, '-c', ROOT / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
        divergent = output / 'nonreturning.ll'
        divergent.write_bytes(runner.run('emit-nonreturning',
            [compiler, '--emit-llvm', '--expr', NONRETURNING], timeout=120).stdout)
        record['artifacts'][str(divergent)] = sha(divergent)
        for level in ['0', '2']:
            binary = output / ('native-O' + level)
            runner.run('link-O' + level, [clang, '-O' + level, '-Wno-override-module',
                       llvm, runtime, archive, *libraries, '-lm', '-lpthread', '-ldl', '-o', binary], timeout=120)
            for name, arguments, expected in cases():
                runner.run(name + '-O' + level, [binary, *arguments], expected=expected, timeout=120)
                record['cases'].append(name + '-O' + level)
            gc_binary = output / ('gc-O' + level)
            runner.run('link-gc-O' + level, [clang, '-O' + level, '-Wno-override-module',
                       '-I' + str(gc / 'include'), gc_llvm, GC_DRIVER, runtime, archive,
                       *libraries, '-lm', '-lpthread', '-ldl', '-o', gc_binary], timeout=120)
            result = runner.run('collect-O' + level, [gc_binary, 'gc', '65536', '17'],
                                timeout=120, overrides={'GC_INITIAL_HEAP_SIZE': '16777216',
                                                       'GC_FREE_SPACE_DIVISOR': '64'})
            match = re.fullmatch(rb'382110\ncollections=(\d+)\n', result.stdout)
            require(match is not None and int(match[1]) > 0,
                    'GC control has wrong value or no observed collection')
            record['gc_cases'].append({'optimization': level, 'collections': int(match[1]),
                                       'interior_pointers': False})
            divergent_binary = output / ('nonreturning-O' + level)
            runner.run('link-nonreturning-O' + level, [clang, '-O' + level, '-Wno-override-module',
                       divergent, runtime, archive, *libraries, '-lm', '-lpthread', '-ldl',
                       '-o', divergent_binary], timeout=120)
            observe_nonreturning(runner, divergent_binary)
            for path in [binary, gc_binary, divergent_binary]:
                record['artifacts'][str(path)] = sha(path)
        for path in [llvm, gc_llvm, runtime]:
            record['artifacts'][str(path)] = sha(path)
        require(len(record['cases']) == 60 and len(record['gc_cases']) == 2 and
                len(record['nonreturning_cases']) == 2,
                'execution inventory differs')
        record.update(complete=True, status='passed')
    except BaseException as error:
        record.update(complete=False, status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            require(sha(path) == digest, 'input/artifact changed: ' + path)
        save()
    print(str(output / 'receipt.json') + ': passed (60 native results, 2 GC and 2 nonreturning controls)')


if __name__ == '__main__':
    main()
