#!/usr/bin/env python3
"""Qualify diagnostic clocks through the real disk crate entry, including failures."""
import argparse
import json
import shutil
from pathlib import Path
from test_direct import CommandRunner, authenticate_build, sha
from test_flat_compiler import HEADER, pack

ROOT = Path(__file__).resolve().parents[2]
PHASES = {'read_ms', 'decode_ms', 'validate_ms', 'prelude_check_ms', 'link_ms',
          'final_check_ms', 'optimize_ms', 'emit_ms', 'other_ms', 'wire_decode_ms',
          'syntax_decode_ms', 'image_decode_ms', 'metadata_hash_ms',
          'reference_validate_ms', 'fragment_validate_ms'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', required=True, type=Path)
    parser.add_argument('--builtin', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    receipt = args.build_receipt.resolve(strict=True)
    output = args.output.resolve()
    if output.is_relative_to(receipt.parent) or receipt.parent.is_relative_to(output):
        parser.error('independent output directory required')
    authenticate_build(receipt, receipt.parent / 'bin')
    output.mkdir(parents=True, exist_ok=False)
    evidence = {'complete': False, 'producer_sha256': sha(receipt),
                'driver_sha256': sha(__file__), 'commands': [], 'checks': []}
    def save():
        (output / 'receipt.json').write_text(json.dumps(evidence, indent=2) + '\n')
    def check(label, condition):
        evidence['checks'].append({'name': label, 'passed': bool(condition)})
        save()
        if not condition:
            raise ValueError(label)
    runner = CommandRunner(ROOT, output, evidence, save)
    compiler = receipt.parent / 'bin/emlf'
    builtin = output / 'builtin'
    for suffix in ('.mlfci', '.mlfco'):
        shutil.copyfile(Path(str(args.builtin) + suffix), Path(str(builtin) + suffix))
    source = output / 'Main.hs'
    source.write_text(HEADER + '''module Main (main) where { import MLF.Primitive;
f0 step y = step y;
f1 step y = step (f0 step y);
main :: IO ();
main = printInt (if f1 (\\v -> if v then False else True) True
                then f1 (\\v -> addInt v 1) 7 else 0); }
''')
    cache = output / 'queries'; cache.mkdir()
    spec = output / 'crate.spec'
    spec.write_text(pack(['MLF-CRATE-1', 'profile-controls', 'Main', 'false',
        pack([pack(['Main', str(source)])]), pack([str(builtin) + '.mlfci']),
        str(cache), str(builtin)]))
    prefix = output / 'unit'
    fused = runner.run('fused', [compiler, '--compile-crate-to-llvm-gc', spec, '-o', prefix])
    paths = [output / ('unit' + suffix) for suffix in ('.mlfci', '.mlfco')]
    original = {str(p): sha(p) for p in paths}
    plain_env = {'MLF_CRATE_PROFILE': ''}
    def compare(name, argv, status=0, expected=None):
        plain = runner.run(name + '-plain', argv, overrides=plain_env, status=status, expected=expected)
        profile = output / (name + '.phases.json')
        timed = runner.run(name + '-timed', argv, overrides={'MLF_CRATE_PROFILE': str(profile)},
                           status=status, expected=plain.stdout)
        check(name + ' diagnostics unchanged', timed.stderr == plain.stderr)
        data = json.loads(profile.read_text())
        check(name + ' complete finite phase inventory', set(data) == PHASES and
              all(type(v) is int and v >= 0 for v in data.values()))
        if status == 0:
            check(name + ' clocks exercised', sum(data.values()) > 0)
        return data
    compare('llvm', [compiler, '--crate-to-llvm-gc', paths[0]], expected=fused.stdout)
    compare('execute', [compiler, '--run-crate', paths[0]], expected=b'9\n')
    check('profiling does not change checked artifacts', original == {str(p): sha(p) for p in paths})
    raw = paths[1].read_bytes()
    corrupted = bytearray(raw); corrupted[-1] ^= 1; paths[1].write_bytes(corrupted)
    compare('corruption', [compiler, '--crate-to-llvm-gc', paths[0]], status=1, expected=b'')
    paths[1].write_bytes(raw)
    compare('missing', [compiler, '--crate-to-llvm-gc', output / 'absent.mlfci'], status=1, expected=b'')
    authenticate_build(receipt, receipt.parent / 'bin')
    evidence['complete'] = True
    save()
    print('crate profile controls passed:', len(evidence['checks']), 'checks,', len(evidence['commands']), 'commands')


if __name__ == '__main__':
    main()
