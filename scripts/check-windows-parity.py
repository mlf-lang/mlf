#!/usr/bin/env python3
"""Run the existing independent bootstrap parity gate with Win64 linking."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--checker', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--clang', type=Path, required=True)
    parser.add_argument('--native-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / '.mlf-build/windows/parity')
    args = parser.parse_args()
    compiler, checker, manifest, clang, prefix, out = (p.resolve() for p in
        (args.compiler, args.checker, args.manifest, args.clang, args.native_prefix, args.output))
    out.mkdir(parents=True, exist_ok=True)
    os.environ['PATH'] = str(prefix / 'bin') + os.pathsep + os.environ['PATH']
    spec = importlib.util.spec_from_file_location('bootstrap_gate', ROOT / 'scripts/bootstrap-compiler.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    version = subprocess.check_output([clang, '--version'], text=True)
    major = int(version.split('clang version ')[1].split('.')[0])
    ir_flags = ['-mllvm', '-opaque-pointers'] if major < 15 else []
    runtime = out / 'runtime.o'
    subprocess.run([clang, '-O2', '-std=c11', '-I' + str(prefix / 'include'),
                    '-c', ROOT / 'runtime/mlf_runtime.c', '-o', runtime], check=True)

    # Keep the upstream acceptance, independent checker, expected IO, and
    # rejection-diagnostic checks intact. Only the host linker differs.
    def windows_link(ir, binary, runtime, flags):
        subprocess.run([clang, '-O2', '-Wno-override-module', *ir_flags, ir, runtime,
                        prefix / 'lib/libgmp.dll.a', '-lshell32', '-lm',
                        '-Wl,--stack,268435456', '-o', binary], check=True)
    gate.link = windows_link
    identities = {str(p): sha(p) for p in (compiler, checker, manifest)}
    report = {'complete': False, 'identities': identities, 'gate_sha256': sha(ROOT / 'scripts/bootstrap-compiler.py')}
    result_path = out / 'verification.json'
    result_path.write_text(json.dumps(report, indent=2) + '\n')
    try:
        report['parity'] = gate.parity(compiler, manifest, checker, out, runtime, [])
        for path, expected in identities.items():
            if sha(Path(path)) != expected:
                raise RuntimeError('Input changed during parity: ' + path)
        report['complete'] = True
        result_path.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report['parity'], indent=2), flush=True)
    except BaseException as error:
        report['error'] = str(error)
        result_path.write_text(json.dumps(report, indent=2) + '\n')
        raise


if __name__ == '__main__':
    main()
