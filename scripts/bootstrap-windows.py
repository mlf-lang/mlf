#!/usr/bin/env python3
"""Bootstrap native Win64 MLF with a Windows Haskell seed and MinGW Clang.

Build the seed with `cabal build exe:emlf`, then pass its path with --seed.
--native-prefix must contain include/{gmp.h,gc/gc.h}, lib/*.dll.a and bin/*.dll.
This script checks a three-stage LLVM fixed point. It records that gate
separately from the full independent parity corpus and native release gates.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--clang', type=Path, required=True)
    parser.add_argument('--native-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / '.mlf-build/windows')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('Run this script with native Windows Python.')
    seed, clang, prefix, out = (p.resolve() for p in (args.seed, args.clang, args.native_prefix, args.output))
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PATH=str(prefix / 'bin') + os.pathsep + os.environ['PATH'])
    env.setdefault('GC_INITIAL_HEAP_SIZE', '536870912')
    env.setdefault('GC_FREE_SPACE_DIVISOR', '1')
    report = {'complete': False, 'fixed_point': False, 'full_parity': False,
              'platform': 'windows-x86_64', 'seed_sha256': digest(seed), 'stages': []}
    inputs = sorted((ROOT / 'bootstrap').rglob('*.emlf')) + sorted((ROOT / 'runtime').glob('*.[ch]'))
    snapshot = {str(p.relative_to(ROOT)): digest(p) for p in inputs}
    report['sources'] = snapshot
    report_path = out / 'verification.json'

    def save():
        report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

    def run(command, name, stdout=None):
        print('+', subprocess.list2cmdline(list(map(str, command))), flush=True)
        with (out / (name + '.stderr')).open('wb') as errors:
            subprocess.run(list(map(str, command)), cwd=ROOT, env=env,
                           stdout=stdout, stderr=errors, check=True)

    # LLVM 14 needs explicit opaque pointers; LLVM 15+ enables them by default.
    version = subprocess.check_output([clang, '--version'], text=True)
    major = int(version.split('clang version ')[1].split('.')[0])
    ir_flags = ['-mllvm', '-opaque-pointers'] if major < 15 else []
    libraries = [prefix / 'lib/libgc.dll.a', prefix / 'lib/libgmp.dll.a', '-lshell32', '-lm']
    report['clang_version'] = version
    report['native_libraries'] = {p.name: digest(p) for p in (prefix / 'bin').glob('*.dll')}
    save()
    try:
        runtime = out / 'runtime.o'
        run([clang, '-O2', '-std=c11', '-DMLF_USE_BDWGC', '-DMLF_COMPACT_BDWGC',
             '-DMLF_GC_THRESHOLD=1048576', '-I' + str(prefix / 'include'),
             '-c', ROOT / 'runtime/mlf_runtime.c', '-o', runtime], 'runtime')
        previous = seed
        for stage in (1, 2, 3):
            ir, binary = out / f'stage{stage}.ll', out / f'emlf-stage{stage}.exe'
            start = time.monotonic()
            with ir.open('wb') as output:
                run([previous, '-i', ROOT / 'bootstrap', '--emit-llvm-gc', ROOT / 'bootstrap/Main.emlf'],
                    f'stage{stage}-emit', output)
            if not ir.stat().st_size:
                raise RuntimeError('Empty LLVM output')
            run([clang, '-O2', '-Wno-override-module', *ir_flags, ir, runtime, *libraries,
                 '-Wl,--stack,268435456', '-o', binary], f'stage{stage}-link')
            report['stages'].append({'stage': stage, 'llvm_sha256': digest(ir),
                                     'binary_sha256': digest(binary), 'seconds': time.monotonic() - start})
            save()
            previous = binary
        if digest(out / 'stage2.ll') != digest(out / 'stage3.ll'):
            raise RuntimeError('Stage 2 and stage 3 LLVM differ')
        report['fixed_point'] = True
        for path, expected in snapshot.items():
            if digest(ROOT / path) != expected:
                raise RuntimeError('Source changed during bootstrap: ' + path)
        report['complete'] = True
        save()
        print('Native Win64 three-stage fixed point passed:', previous, flush=True)
    except BaseException as error:
        report['error'] = str(error)
        save()
        raise


if __name__ == '__main__':
    main()
