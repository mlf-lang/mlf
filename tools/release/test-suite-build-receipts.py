#!/usr/bin/env python3
"""Execute production receipt and preparation guards with the native MLF compiler.

Extracting those exact expressions avoids a native compiler-tests rebuild for
these small JSON contracts. This does not substitute for a complete campaign run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--source', type=Path, default=Path('tests/Tests/CompilerTests.emlf'))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    source = args.source.resolve(strict=True)
    compiler = args.compiler.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    prefix = ' record c "suite_builds" '
    expressions = [line[len(prefix):] for line in source.read_text().splitlines() if line.startswith(prefix)]
    if len(expressions) != 1:
        raise ValueError('Expected exactly one production suite-build receipt append')
    selection_prefix = ' if S.all '
    selection_suffix = ' then return Unit else nativeTests c targets'
    selections = [line[len(' if '):-len(selection_suffix)] for line in source.read_text().splitlines()
                  if line.startswith(selection_prefix) and line.endswith(selection_suffix)]
    if len(selections) != 1:
        raise ValueError('Expected exactly one production focused-Core build preparation guard')
    header = ('module Main where\nimport Bootstrap.Types\n'
              'import qualified Bootstrap.Std as S\nimport qualified Package.Json as J\n'
              'append saved receipt = ' + expressions[0] + '\n'
              'prepared saved targets = ' + selections[0] + '\n')
    environment = dict(os.environ, GC_FREE_SPACE_DIVISOR='1')
    result = {'complete': False, 'compiler': str(compiler), 'compiler_sha256': digest(compiler),
              'source': str(source), 'source_sha256': digest(source), 'cases': []}
    try:
        bodies = {'first-and-second': '''main : IO Unit
main = do
 let first = append J.empty (J.num 0)
 let second = append (J.set "suite_builds" first J.empty) (J.num 7)
 putStrLn (J.render first)
 putStrLn (J.render second)
 if prepared J.empty (Cons "core-crates" Nil) then panic "missing prepared map accepted" else putStrLn "missing map builds"
 let one = J.set "prepared_suite_targets" (J.set "core-crates" (J.str "retained") J.empty) J.empty
 if prepared one (Cons "core-crates" Nil) then putStrLn "existing map reused" else panic "existing prepared map ignored"
 if prepared one (Cons "core-crates" (Cons "core-solver" Nil)) then panic "missing target accepted" else putStrLn "partial map builds"
'''}
        for name, value in [('null', 'J.Null'), ('object', 'J.empty'), ('string', 'J.str "malformed"')]:
            bodies['reject-' + name] = ('main : IO Unit\nmain = putStrLn (J.render '
                '(append (J.set "suite_builds" (' + value + ') J.empty) (J.num 7)))\n')
        bodies['reject-prepared-null'] = ('main : IO Unit\nmain = if prepared '
            '(J.set "prepared_suite_targets" J.Null J.empty) (Cons "core-crates" Nil) '
            'then putStrLn "bad" else putStrLn "bad"\n')
        for name, body in bodies.items():
            program = output / (name + '.emlf')
            program.write_text(header + body)
            command = [str(compiler), '-i', str(root / 'libraries/mlf-foundation'),
                       '-i', str(root / 'libraries/mlf-package-core'), '--run', str(program)]
            completed = subprocess.run(command, cwd=root, env=environment, capture_output=True, timeout=120)
            (output / (name + '.stdout')).write_bytes(completed.stdout)
            (output / (name + '.stderr')).write_bytes(completed.stderr)
            row = {'name': name, 'command': command, 'exit_code': completed.returncode,
                   'program_sha256': digest(program), 'stdout_sha256': digest(output / (name + '.stdout')),
                   'stderr_sha256': digest(output / (name + '.stderr'))}
            result['cases'].append(row)
            if name == 'first-and-second':
                if completed.returncode != 0 or completed.stdout != b'[0]\n[0,7]\nmissing map builds\nexisting map reused\npartial map builds\n':
                    raise ValueError('Receipt append or focused-Core preparation contract failed')
            elif completed.returncode != 1 or (b'expected JSON object' if name == 'reject-prepared-null' else b'expected JSON array') not in completed.stderr:
                raise ValueError('Malformed existing receipt list was not rejected: ' + name)
            print('PASS suite-build receipts: ' + name, flush=True)
        result['complete'] = True
    finally:
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
