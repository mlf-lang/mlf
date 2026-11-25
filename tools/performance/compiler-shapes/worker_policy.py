"""Compare Clang worker attributes on identical compiler-shapes IR on macOS."""
import argparse
import json
import re
import shlex
import statistics
import subprocess
import time
from pathlib import Path

import generate


FAMILIES = ('escaping_curried_jobs', 'independent_wide_recursive_groups', 'demand_forwarding_chain')
LOOP = r"""
repeatEntry :: Int -> Int -> Int;
repeatEntry n acc = if eqInt n 0 then acc else let {
  next = addInt acc (entry (remInt n 17))
} in seq next (repeatEntry (subInt n 1) next);
main :: IO ();
main = ioBind (getArg 0) (\text -> printInt (repeatEntry (readInt text) 0))
}
"""


def measure(command):
    start = time.perf_counter()
    done = subprocess.run(['/usr/bin/time', '-l', *command], check=True, capture_output=True)
    elapsed = time.perf_counter() - start
    rss = re.search(rb'(\d+)\s+maximum resident set size', done.stderr)
    return elapsed, int(rss[1]), done.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--reference-compiler', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--size', type=int, default=16)
    parser.add_argument('--iterations', type=int, default=16384)
    parser.add_argument('--samples', type=int, default=3)
    parser.add_argument('--clang', default='clang')
    args = parser.parse_args()
    if min(args.size, args.iterations, args.samples) < 1:
        parser.error('size, iterations and samples must be positive')
    args.out.mkdir(exist_ok=True, parents=True)
    runtime = args.out / 'runtime.o'
    def flags(flag):
        return shlex.split(subprocess.check_output(['pkg-config', flag, 'gmp', 'bdw-gc'], text=True))
    subprocess.run([args.clang, '-O2', '-std=c11', '-Iruntime', *flags('--cflags'),
                    '-c', 'runtime/mlf_runtime.c', '-o', runtime], check=True)
    report = {'size': args.size, 'iterations': args.iterations, 'samples': args.samples, 'families': {}}
    for family in FAMILIES:
        folder = args.out / family
        folder.mkdir(exist_ok=True)
        source = folder / 'Main.hs'
        program = generate.program(family, args.size)
        assert program.endswith(generate.MAIN)
        source.write_text(program[:-len(generate.MAIN)] + LOOP)
        emit, emit_rss, ir = measure([args.compiler, '--emit-llvm', source])
        if args.reference_compiler:
            original = subprocess.check_output([args.reference_compiler, '--emit-llvm', source])
            if original != ir:
                (folder / 'reference.ll').write_bytes(original)
                (folder / 'candidate.ll').write_bytes(ir)
                raise ValueError(f'{family}: LLVM output differs from reference')
        plain, count = re.subn(rb'(?m)^(define [^\n]+?) optnone \{', rb'\1 {', ir)
        assert count and count == ir.count(b' optnone')
        variants = {'default': ir, 'without-optnone': plain}
        for key, data in variants.items():
            (folder / (key + '.ll')).write_bytes(data)
        expected = sum(generate.expected(family, args.size, n % 17) for n in range(1, args.iterations + 1))
        expected = f'{(expected + 2**63) % 2**64 - 2**63}\n'.encode()
        rows = {key: [] for key in variants}
        for sample in range(args.samples):
            for key in list(variants)[::1 if sample % 2 == 0 else -1]:
                binary = folder / key
                build, rss, _ = measure([args.clang, '-O2', folder / (key + '.ll'), runtime,
                                         *flags('--libs'), '-lm', '-lpthread', '-ldl', '-o', binary])
                # The first launch can include platform executable verification.
                subprocess.run([binary, '0'], capture_output=True, check=True)
                run, run_rss, output = measure([binary, str(args.iterations)])
                if output != expected:
                    raise ValueError(f'{family} {key}: expected {expected!r}, got {output!r}')
                rows[key].append(dict(clang_seconds=build, clang_rss_bytes=rss, run_seconds=run,
                                      run_rss_bytes=run_rss, binary_bytes=binary.stat().st_size))
        report['families'][family] = dict(annotated_functions=count, emit_seconds=emit,
                                          emit_rss_bytes=emit_rss, measurements=rows)
        print(family, {key: statistics.median(row['run_seconds'] for row in samples)
                       for key, samples in rows.items()}, flush=True)
        (args.out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
