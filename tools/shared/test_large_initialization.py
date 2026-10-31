#!/usr/bin/env python3
"""Execute large literal/recursive initialization through ordinary Clang -O2.

The runtime object is an explicit input, normally INSTALL/native/runtime.o.
This is a focused regression, not a compiler-bootstrap timing qualification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import time

from test_direct import sha


def source():
    tree = '(Leaf 1)'
    for _ in range(14):
        tree = '(Node ' + tree + ' ' + tree + ')'
    rows = [
        'data Tree = Leaf Int | Node Tree Tree',
        'sumTree tree = case tree of { Leaf x -> x; Node a b -> addInt (sumTree a) (sumTree b) }',
        'tree :: Tree', 'tree = ' + tree,
        'choose f = f 12',
        'evenCount n = if eqInt n 0 then v159 else oddCount (subInt n 1)',
        'oddCount n = if eqInt n 0 then addInt v159 1 else evenCount (subInt n 1)',
    ]
    for index in range(160):
        rows += [f'v{index} :: Int', f'v{index} = readInt "{index}"']
    total = '0'
    for index in range(160):
        total = f'addInt v{index} ({total})'
    rows += ['total = ' + total,
             'main = ioBind (getArg 0) (\\flag -> printInt '
             '(if eqString flag "skip" then 7 else '
             'if eqString flag "panic" then panic "late initialization" else '
             'addInt (sumTree tree) (addInt total '
             '(choose (if eqString flag "odd" then oddCount else evenCount)))))']
    return '\n'.join(rows) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--runtime-object', type=Path, required=True)
    parser.add_argument('--clang', type=Path, required=True)
    parser.add_argument('--gc-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    compiler, runtime, clang = [p.resolve(strict=True) for p in
                                (args.compiler, args.runtime_object, args.clang)]
    archive = (args.gc_prefix / 'lib/libgc.a').resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {'complete': False, 'scope': 'large-initialization-regression',
              'inputs': {str(p): sha(p) for p in (compiler, runtime, clang, archive)},
              'commands': [], 'cases': []}

    def run(command, expected=None, status=0):
        started = time.monotonic()
        result = subprocess.run([str(x) for x in command], capture_output=True, timeout=300)
        record['commands'].append({'argv': [str(x) for x in command],
                                   'seconds': time.monotonic() - started,
                                   'exit_code': result.returncode})
        if result.returncode != status or (expected is not None and result.stdout != expected):
            raise AssertionError((command, result.returncode, result.stdout, result.stderr))
        return result

    try:
        program = output / 'large.emlf'
        program.write_text(source())
        emitted = run([compiler, '--no-prelude', '--emit-llvm-gc', program]).stdout
        llvm = output / 'large.ll'
        llvm.write_bytes(emitted)
        text = emitted.decode()
        functions = re.findall(r'^define [^\n]*\{\n(.*?)^\}', text, re.M | re.S)
        largest = max(len(body.splitlines()) for body in functions)
        assert largest < 12000, ('unbounded LLVM initialization', largest)
        record['largest_function_lines'] = largest
        libraries = subprocess.check_output(['pkg-config', '--libs', 'gmp'], text=True).split()
        binary = output / 'large'
        run([clang, '-O2', '-Wno-override-module', llvm, runtime, archive,
             *libraries, '-lm', '-o', binary])
        for argument, expected in [('take', b'29263\n'), ('odd', b'29264\n'), ('skip', b'7\n')]:
            run([binary, argument], expected)
            record['cases'].append(argument)
        result = run([binary, 'panic'], b'', 1)
        assert result.stderr == b'Runtime: late initialization\n', result.stderr
        record['cases'].append('panic')
        for path, digest in record['inputs'].items():
            assert sha(path) == digest, 'input changed: ' + path
        record['complete'] = True
    finally:
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    print(str(output / 'receipt.json') + ': passed')


if __name__ == '__main__':
    main()
