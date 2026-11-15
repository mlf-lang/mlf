#!/usr/bin/env python3
"""Authenticated CLI controls for shared polymorphic-template query payloads."""
from pathlib import Path
from collections import Counter
import argparse
import json
import shutil
from test_direct import CommandRunner, authenticate_build, sha
from test_flat_compiler import HEADER, pack
from artifact_binary_reference import read_document
from query_generation import Generation

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--builtin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fused', action='store_true', help='also check the single-invocation retained-root entry')
    parser.add_argument('--cached-codegen', action='store_true', help='check fused codegen cache/report interoperability')
    args = parser.parse_args()
    if args.cached_codegen and not args.fused:
        parser.error('--cached-codegen requires --fused')
    receipt = args.build_receipt.resolve(strict=True)
    producer, output = receipt.parent, args.output.resolve()
    if output.is_relative_to(producer) or producer.is_relative_to(output):
        parser.error('independent output directory required')
    authenticate_build(receipt, producer / 'bin')
    output.mkdir(parents=True, exist_ok=False)
    evidence = {'complete': False, 'producer_sha256': sha(receipt),
                'driver_sha256': sha(__file__), 'fused': args.fused,
                'cached_codegen': args.cached_codegen, 'commands': [], 'checks': []}
    def save():
        (output / 'receipt.json').write_text(json.dumps(evidence, indent=2) + '\n')
    def check(label, condition):
        evidence['checks'].append({'name': label, 'passed': bool(condition)})
        save()
        if not condition:
            raise ValueError(label)
    save()
    runner = CommandRunner(ROOT, output, evidence, save)
    emlf = producer / 'bin/emlf'
    builtin = output / 'builtin'
    for suffix in ['.mlfci', '.mlfco']:
        shutil.copyfile(Path(str(args.builtin) + suffix), Path(str(builtin) + suffix))
    source = output / 'Main.hs'
    cache = output / 'cache'; cache.mkdir()
    spec = output / 'crate.spec'
    spec.write_text(pack(['MLF-CRATE-1', 'poly-chain-controls', 'Main', 'false',
        pack([pack(['Main', str(source)])]), pack([str(builtin) + '.mlfci']),
        str(cache), str(builtin)]))
    prefix = output / 'unit'
    def write(first='step y'):
        definitions = ['f0 step y = ' + first] + [
            f'f{i} step y = step (f{i-1} step y)' for i in range(1, 9)]
        source.write_text(HEADER + 'module Main (main) where { import MLF.Primitive; '
            + '; '.join(definitions) + '; entry :: Int -> Int; '
            'entry x = if f8 (\\v -> if v then False else True) (ltInt x 0) '
            'then f8 (\\v -> addInt v 1) x else subInt 0 (f8 (\\v -> addInt v 1) x); '
            'main :: IO (); main = printInt (entry 7); }\n')
    def compile(name, status=0, verify=False):
        report = output / (name + '.codegen.json')
        codegen = output / 'codegen'
        result = runner.run(name, [emlf, *(['-Zincremental-verify-ich'] if verify else []),
            '--compile-crate-to-llvm-gc' if args.fused else '--compile-crate', spec, '-o', prefix,
            *(['--codegen-cache', codegen, '--query-report', report] if args.cached_codegen else [])],
            status=status, timeout=120)
        if args.fused and status == 0:
            check(name + ' emits LLVM', b'define ' in result.stdout)
            runner.run(name + '-disk-link-parity', [emlf, '--crate-to-llvm-gc', output / 'unit.mlfci'],
                       expected=result.stdout, timeout=120)
            if args.cached_codegen:
                generated = json.loads(report.read_text())
                check(name + ' reports the actual compiler', generated['compiler'] == sha(emlf))
                if name == 'cold':
                    check('first codegen is freshly generated',
                          not generated['input_reused'] and not generated['optimized_reused'])
                if name in ['warm', 'verified']:
                    check(name + ' reuses codegen input', generated['input_reused'])
                disk_report = output / (name + '.disk-codegen.json')
                runner.run(name + '-disk-cache-parity', [emlf, '--crate-to-llvm-gc', output / 'unit.mlfci',
                    '--cache', codegen, '--query-report', disk_report], expected=result.stdout, timeout=120)
                disk = json.loads(disk_report.read_text())
                check(name + ' shares exact input and optimized cache keys with disk linking',
                      disk['input_reused'] and all(disk[key] == generated[key]
                          for key in ['input_key', 'optimized_key', 'compiler']))
        elif status != 0:
            check(name + ' emits no partial LLVM', not result.stdout)
            if args.cached_codegen:
                check(name + ' publishes no successful codegen report', not report.exists())
        if status == 0:
            return json.loads((output / 'unit.queries').read_text())
    def execute(name, expected):
        runner.run(name, [emlf, '--run-crate', output / 'unit.mlfci'],
                   expected=expected.encode(), timeout=120)
    def artifacts():
        return [(output / ('unit' + suffix)).read_bytes() for suffix in ['.mlfci', '.mlfco']]
    write()
    cold = compile('cold')
    count = cold['inferred_groups']
    check('all declarations are freshly inferred', count == 12 and cold['reused_groups'] == 0)
    original = artifacts()
    execute('cold-value', '16\n')
    warm = compile('warm')
    check('every declaration reuses a checked payload', warm['inferred_groups'] == 0 and warm['reused_groups'] == count)
    check('warm checked artifacts equal cold artifacts', artifacts() == original)
    verified = compile('verified', verify=True)
    check('ICH verification accepts normalized payloads', verified['inferred_groups'] == 0)
    check('verification preserves artifacts', artifacts() == original)
    graph = cache / 'query-graph-v2'
    address = read_document((graph / 'CURRENT').read_bytes(), 6).values()[0][1]
    generation = Generation((graph / 'generations' / (address + '.mlfqg')).read_bytes(), expected_hash=address)
    payloads = Counter(node['payload'] for key, node in generation.nodes.items()
                       if key.startswith('8:InferScc') and node['payload'] is not None)
    victim, users = payloads.most_common(1)[0]
    check('distinct declarations share an immutable payload', users == 7 and len(payloads) == 6)
    payload = graph / 'results' / (victim + '.mlfqr')
    damaged = bytearray(payload.read_bytes()); damaged[-1] ^= 1; payload.write_bytes(damaged)
    repaired = compile('repair-shared-payload')
    check('corruption rechecks every dependent declaration',
          repaired['inferred_groups'] == users and repaired['reused_groups'] == count-users)
    check('one repaired payload restores its exact address', sha(payload) == victim)
    check('repair restores checked artifacts', artifacts() == original)
    execute('repaired-value', '16\n')
    write('step (step y)')
    changed = compile('changed-predecessor')
    # This edit changes f0's scheme. The existing query graph invalidates the
    # full consumer chain through its recorded reads, including entry and main;
    # only the synthetic crate entry reuses. The checkpoint compiler has the
    # same 11/1 boundary. Template sharing must preserve that invalidation.
    check('changed scheme preserves consumer-chain invalidation',
          changed['inferred_groups'] == count - 1 and changed['reused_groups'] == 1
          and changed['groups'][-1]['cached'])
    execute('changed-value', '-17\n')
    stable = (graph / 'CURRENT').read_bytes()
    write('addInt y 1')
    compile('reject-monomorphic-predecessor', status=1)
    check('failed checking leaves the last good generation', (graph / 'CURRENT').read_bytes() == stable)
    write('step (step y)')
    restored = compile('restore-good-source', verify=True)
    check('restored source reuses the last good generation', restored['inferred_groups'] == 0)
    execute('restored-value', '-17\n')
    authenticate_build(receipt, producer / 'bin')
    check('producer receipt is unchanged', sha(receipt) == evidence['producer_sha256'])
    evidence['complete'] = True; save()
    print('PASS polymorphic chain CLI cache controls')


if __name__ == '__main__':
    main()
