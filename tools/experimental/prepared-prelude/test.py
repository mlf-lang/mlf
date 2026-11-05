#!/usr/bin/env python3
"""Differential whole-root controls; no timing or broad qualification claim."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--benchmarks', action='store_true')
    parser.add_argument('--route', choices=['selected', 'full', 'direct'], default='selected')
    parser.add_argument('--skip-import-counts', action='store_true',
                        help='production entry has no synthetic-prefix diagnostic commands')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    compiler = args.compiler.resolve(strict=True)
    sources = [
        ('hello', ROOT / 'tools/experimental/installed-prelude/tests/fixtures/hello.emlf'),
        ('unicode', ROOT / 'tools/experimental/installed-prelude/tests/fixtures/unicode.emlf'),
        ('protected-collision', ROOT / 'tools/experimental/installed-prelude/tests/fixtures/collision.emlf'),
        ('negative-legacy-multiparameter', ROOT / 'examples/multiparameter.emlf'),
        ('user-superclass', ROOT / 'examples/monad-state-do.emlf'),
    ]
    snippets = {
        'ground-eq': 'if 1 == 1 then putStrLn "yes" else putStrLn "no"\n',
        'negative-polymorphic-eq': '\\x -> x == x\n',
        'polymorphic-eq': 'let same : forall a. Eq a => a -> Bool = \\x -> x == x in if same 1 then putStrLn "yes" else putStrLn "no"\n',
        'principal-let': 'let id = \\x -> x in if id true then putStrLn (\"value \" ++ showInt (id 7)) else putStrLn \"no\"\n',
        'rank-two': 'let use : (forall a. a -> a) -> Bool = let marker = true in \\g -> let n = g 1 in g true in if use (\\x -> x) then putStrLn \"yes\" else putStrLn \"no\"\n',
        'negative-unused-instance': 'class Broken a where { broken : a -> Bool }; instance Broken Int where { broken = \\x -> 7 }; putStrLn \"ok\"\n',
        'global-principal-id': 'let unused = putStrLn \"witness\" in \\x -> x\n',
        'global-principal-const': 'let unused = putStrLn \"witness\" in \\x y -> x\n',
        'zero-imports': 'let witness : forall a. Eq a => a -> Bool = \\x -> true in ioReturn ()\n',
        'evidence-only-import': 'let answer = true == false in ioReturn answer\n',
        'polymorphic-alias': 'let eq : forall a. Eq a => a -> a -> Bool = (==) in if eq 1 1 then if eq true true then putStrLn "yes" else putStrLn "no" else putStrLn "no"\n',
        'negative-unused-local': 'let unused = putStrLn 1 in putStrLn "ok"\n',
        'ground-string': 'putStrLn "hello"\n',
        'negative-application': 'putStrLn 1\n',
        'negative-unbound': 'let output = putStrLn "x" in missingName\n',
        'managed-alias': 'let failure = ioError in if true then putStrLn "ok" else failure (userError (textToChars "sample"))\n',
        'multiparameter': ('class Pick a b where { pick : a -> b -> a };\n'
                          'instance Pick Int Bool where { pick = \\a b -> a };\n'
                          'putStrLn ("picked " ++ showInt (pick 1 true))\n'),
        'user-adt': ('data Item = Item Int;\n'
                     'case Item 7 of { Item n -> putStrLn ("item " ++ showInt n) }\n'),
        'contextual-instance': ('data Bag a = Bag a;\n'
            'class Inspect a where { inspect : a -> Bool };\n'
            'instance Inspect Bool where { inspect = \\x -> x };\n'
            'instance Inspect a => Inspect (Bag a) where { inspect = \\bag -> case bag of { Bag value -> inspect value } };\n'
            'if inspect (Bag true) then putStrLn "yes" else putStrLn "no"\n'),
    }
    for name, contents in snippets.items():
        path = output / (name + '.emlf')
        path.write_text(contents)
        sources.append((name, path))
    if args.benchmarks:
        for name in ['binary-trees', 'fannkuch-redux', 'fasta', 'k-nucleotide', 'mandelbrot',
                     'n-body', 'pidigits', 'reverse-complement', 'spectral-norm']:
            sources.append(('benchmark-' + name, ROOT / 'benchmarks' / name / 'mlf/main.emlf'))
    pins = {str(path): sha(path) for _, path in sources}
    pins[str(compiler)] = sha(compiler)
    pins[str(Path(__file__).resolve())] = sha(Path(__file__))
    receipt = {'complete': False, 'scope': 'whole-root target scheme and layout differential controls',
               'performance_assertions': False, 'route': args.route,
               'synthetic_parameter_count_controls': not args.skip_import_counts,
               'inputs': pins, 'cases': []}
    compare_operation = {'selected': '--compare', 'full': '--compare-full', 'direct': '--compare-direct'}[args.route]
    try:
        for name, path in sources:
            result = subprocess.run([compiler, compare_operation, path], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=180)
            (output / (name + '.stdout')).write_bytes(result.stdout)
            (output / (name + '.stderr')).write_bytes(result.stderr)
            accepted = [b'PASS equal diagnostic\n', b'PASS alpha-equivalent ambiguity diagnostic\n', b'PASS prepared whole-root scheme and layouts\n',
                        b'PASS explicit original fallback\n']
            receipt['cases'].append({'name': name, 'exit': result.returncode,
                                     'outcome': result.stdout.decode(errors='replace').strip()})
            (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
            if result.returncode or result.stderr or result.stdout not in accepted:
                raise RuntimeError('differential control failed: ' + name)
            if name.startswith('negative-'):
                expected = b'PASS alpha-equivalent ambiguity diagnostic\n' if name == 'negative-polymorphic-eq' else b'PASS equal diagnostic\n'
                if result.stdout != expected:
                    raise RuntimeError('negative control was not rejected: ' + name)
            elif result.stdout in [b'PASS equal diagnostic\n', b'PASS alpha-equivalent ambiguity diagnostic\n']:
                raise RuntimeError('positive control was rejected on both routes: ' + name)
            if (name.startswith('benchmark-') or name in ['hello', 'unicode', 'ground-eq', 'polymorphic-eq',
                                                        'ground-string', 'managed-alias', 'user-adt', 'contextual-instance',
                                                        'multiparameter', 'user-superclass', 'principal-let', 'rank-two', 'global-principal-id', 'global-principal-const', 'zero-imports', 'evidence-only-import', 'polymorphic-alias']):
                if result.stdout != b'PASS prepared whole-root scheme and layouts\n':
                    raise RuntimeError('required prepared control fell back: ' + name)
            if name == 'protected-collision' and result.stdout != b'PASS explicit original fallback\n':
                raise RuntimeError('protected collision did not fall back')
            if not args.skip_import_counts and name in ['hello', 'zero-imports', 'evidence-only-import', 'polymorphic-alias']:
                counts = []
                for operation in ['--full-imports', '--direct-imports' if args.route == 'direct' else '--imports']:
                    counted = subprocess.run([compiler, operation, path], stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, timeout=180)
                    if counted.returncode or counted.stderr:
                        raise RuntimeError('import inventory control failed: ' + name)
                    counts.append(int(counted.stdout))
                if counts[0] <= counts[1] or counts[1] < 0:
                    raise RuntimeError('import parameter selection did not reduce inventory: ' + name)
                if name == 'zero-imports' and counts[1] != 0:
                    raise RuntimeError('zero-import control retained synthetic parameters')
                if name == 'evidence-only-import' and counts[1] == 0:
                    raise RuntimeError('wanted evidence candidates disappeared')
                receipt['cases'][-1]['full_imports'] = counts[0]
                receipt['cases'][-1]['selected_imports'] = counts[1]

        receipt['complete'] = True
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        changed = [path for path, expected in pins.items() if sha(Path(path)) != expected]
        receipt['immutable_inputs_verified_after'] = not changed
        if changed:
            receipt.update(complete=False, changed_inputs=changed)
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        if changed:
            raise RuntimeError('pinned differential inputs changed during execution')
    print(output / 'receipt.json')


if __name__ == '__main__':
    main()
