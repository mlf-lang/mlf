#!/usr/bin/env python3
"""Prepare authenticated GHC-origin tools for ordinary async parity, not self-hosting."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = 'MLF/shared-haskell-v1 GHC'
PROCESS = r'do { reply <- processSupervisor "MLF-PROCESS-1\0version\0"; printInt (if eqString reply ("0\0" ++ "1\0") then 1 else 0) }'
COMPLETION = r'do { scope <- asyncScopeNew 1 1; asyncNewCompletion scope (\cell -> do { code <- asyncResolveCompletion cell 41; asyncReadCompletion cell printInt (printInt 0) }) (printInt 0); asyncScopeClose scope }'


def authenticator(root):
    path = root / 'tools/shared/test_direct.py'
    module = types.ModuleType('async_direct_authenticator')
    module.__file__ = str(path)
    # A non-main module name deliberately prevents test_direct's CLI from running.
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def prepare(root, output, clang):
    root, output = root.resolve(strict=True), output.resolve()
    if output == root or root.is_relative_to(output):
        raise ValueError('build directory must not contain the checkout')
    output.mkdir(parents=True, exist_ok=True)
    proof_path = output / 'async-tools.json'
    proof = {'format': 1, 'complete': False, 'producer_host': 'GHC',
             'implementation_identity': IDENTITY, 'commands': []}

    def save():
        temporary = output / 'async-tools.json.tmp'
        temporary.write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n')
        temporary.replace(proof_path)

    save()  # Invalidate an earlier success before any operation that can fail.
    auth = authenticator(root)
    selected = shutil.which(clang)
    if selected is None:
        raise ValueError('selected Clang not found')
    cc = Path(selected).resolve(strict=True)
    inputs = {str(path): auth.identified(path) for path in [
        root / 'runtime/mlf_build_runner.c', root / 'tools/shared/prepare_async_ghc.py',
        root / 'tools/shared/test_direct.py', cc]}

    def unchanged():
        for item in inputs.values():
            auth.verify_file(item)

    def run(label, argv, timeout, expected=None):
        argv = list(map(str, argv))
        stdout, stderr = output / (label + '.stdout'), output / (label + '.stderr')
        entry = {'argv': argv, 'exit_code': None}
        proof['commands'].append(entry)
        save()
        with stdout.open('wb') as out, stderr.open('wb') as err:
            result = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, timeout=timeout, check=False)
        entry.update(exit_code=result.returncode, stdout=auth.identified(stdout),
                     stderr=auth.identified(stderr))
        save()
        if result.returncode != 0:
            raise RuntimeError(label + ' failed; see ' + str(stderr))
        if expected is not None and (stdout.read_bytes() != expected or stderr.stat().st_size):
            raise ValueError(label + ' capability or identity mismatch')

    run('build', [sys.executable, '-B', root / 'tools/shared/build.py', '--bootstrap-only',
                 '--optimization', '2', '--cc', cc, '--build-dir', output], 18000)
    receipt, binaries = output / 'receipt.json', output / 'bin'
    producer = auth.authenticate_build(receipt, binaries, root)
    if producer.get('optimization') != '2':
        raise ValueError('async parity requires the O2 GHC producer')
    receipt_identity = auth.identified(receipt)
    unchanged()
    runner = binaries / 'mlf-build-runner'
    temporary_runner = binaries / 'mlf-build-runner.new'
    # The runner is a C adjunct, never a new entry in the GHC outputs manifest.
    run('runner-build', [cc, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        root / 'runtime/mlf_build_runner.c', '-o', temporary_runner], 120)
    run('runner-protocol', [temporary_runner, '--protocol-version'], 30, b'1\n')
    runner_identity = auth.identified(temporary_runner)
    for name in ('emlf', 'mlfpkg'):
        run(name + '-identity', [binaries / name, '--implementation-identity'], 30,
            (IDENTITY + '\n').encode())
    run('process-capability', [binaries / 'emlf', '--run', '--expr', PROCESS], 60, b'1\n')
    run('completion-capability', [binaries / 'emlf', '--run', '--expr', COMPLETION], 60, b'41\n')
    auth.authenticate_build(receipt, binaries, root)
    auth.verify_file(receipt_identity)
    unchanged()
    auth.verify_file(runner_identity)
    for command in proof['commands']:
        auth.verify_file(command['stdout'])
        auth.verify_file(command['stderr'])
    temporary_runner.replace(runner)
    proof.update(producer_receipt=receipt_identity, inputs=inputs,
                 runner=auth.identified(runner), runner_protocol_version=1,
                 compiler=producer['outputs']['emlf'], manager=producer['outputs']['mlfpkg'],
                 complete=True)
    save()
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, default=ROOT / '.mlf-build/async-ghc')
    parser.add_argument('--clang', default=os.environ.get('CC', 'clang'))
    options = parser.parse_args()
    prepare(ROOT, options.build_dir, options.clang)


if __name__ == '__main__':
    main()
