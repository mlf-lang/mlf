#!/usr/bin/env python3
"""Verify fixed builtin data against fresh canonical preparation.

Both GHC and native qualification drivers can call verify() and authenticate().
The candidate binaries' producer provenance remains the caller's responsibility.
Fresh literal bytes are evidence only: this tool never replaces or compiles an
implementation source file and never grants toolchain qualification on its own.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
FORMAT = 'builtin-prelude-verification-v1'
BANNER = b'builtin Prelude verified\n'
CANONICAL = 'bootstrap/MLF/BuiltinPreludeData.hs'
HELPERS = ('tools/shared/builtin_prelude_identity.py', 'tools/shared/verify_builtin_prelude.py')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def identified(path):
    path = Path(path).resolve(strict=True)
    require(path.is_file(), 'builtin verification input is not a file: ' + str(path))
    return {'path': str(path), 'sha256': sha(path)}


def verify_file(item, expected=None):
    require(isinstance(item, dict) and isinstance(item.get('path'), str),
            'missing builtin verification file identity')
    path = Path(item['path'])
    require(path.is_absolute() and path.is_file() and path.resolve() == path,
            'noncanonical builtin verification file: ' + str(path))
    if expected is not None:
        require(path == Path(expected).resolve(), 'builtin verification resolved a different file: ' + str(path))
    require(sha(path) == item.get('sha256'), 'builtin verification input changed: ' + str(path))
    return path


def configuration_paths(root):
    return [root / 'cabal.project', root / 'mlf-shared.cabal', root / 'shared-sources.json',
            *sorted(root.glob('libraries/*/mlf-package.json')), root / 'mlf-package.json',
            root / 'tests/mlf-package.json', root / 'tests/shared/mlf-package.json',
            root / 'testing/mlf-package.json', root / 'testing/tools/mlf-package.json']


def input_snapshot(root, compiler, generator):
    root = Path(root).resolve(strict=True)
    # Load the helper whose exact bytes are part of this source checkout. A
    # relocated verifier may inspect an immutable canonical checkout directly.
    helper = identified(root / HELPERS[0])
    verifier = identified(__file__)
    require(sha(root / HELPERS[1]) == verifier['sha256'],
            'executing builtin verifier differs from canonical helper')
    manifest_input = identified(root / 'shared-sources.json')
    module = types.ModuleType('builtin_source_identity')
    # Execute the pinned source, never a timestamp-selected .pyc from a prior
    # checkout, and do not create bytecode inside an immutable source tree.
    exec(compile(Path(helper['path']).read_bytes(), helper['path'], 'exec'), module.__dict__)
    identity, source_inputs = module.source_identity(root)
    verify_file(helper)
    verify_file(manifest_input)
    manifest = json.loads((root / 'shared-sources.json').read_text())
    rows = manifest['modules']
    require(len({row['module'] for row in rows}) == len(rows) and
            len({row['path'] for row in rows}) == len(rows), 'duplicate canonical builtin source inventory')
    registered = {row['module']: row['path'] for row in rows}
    require(registered.get('MLF.BuiltinPreludeData') == CANONICAL,
            'canonical builtin literal registration changed')
    paths = set(configuration_paths(root)) | {root / CANONICAL, *(root / path for path in HELPERS)}
    for row in source_inputs['modules'].values():
        relative = Path(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts,
                'invalid canonical builtin source path')
        source = (root / relative).resolve(strict=True)
        require(source.is_relative_to(root), 'canonical builtin source escaped checkout')
        require(sha(source) == row['sha256'], 'canonical builtin source changed during identity calculation')
        paths.add(source)
    compiler, generator = identified(compiler), identified(generator)
    interpreter = identified(sys.executable)
    paths.update(Path(item['path']) for item in [compiler, generator, interpreter, verifier])
    return {'source_root': str(root), 'source_identity': identity, 'source_identity_inputs': source_inputs,
            'compiler': compiler, 'generator': generator, 'orchestrator': interpreter,
            'verification_driver': verifier,
            'canonical': identified(root / CANONICAL),
            'inputs': {str(path.resolve(strict=True)): sha(path) for path in sorted(paths)}}


def verify_inputs(inputs):
    for path, digest in inputs.items():
        verify_file({'path': path, 'sha256': digest})


def commands(snapshot):
    identity = snapshot['source_identity']
    return [('check-candidate', [snapshot['compiler']['path'], '--verify-builtin-prelude', identity]),
            ('fresh-literal', [snapshot['generator']['path'], identity])]


def stop(process):
    # Bound cancellation of the original process group. As with the build
    # driver, this is not a sandbox for descendants which escape that group.
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    else:
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    finally:
        if os.name == 'posix':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def verify(root, compiler, generator, output, timeout=1800):
    """Run both current-source checks and return the completed receipt path."""
    root, output = Path(root).resolve(), Path(output).resolve()
    require(output != root and not root.is_relative_to(output),
            'builtin verification output must not contain the checkout')
    require(type(timeout) in (int, float) and 0 < timeout <= 7200,
            'builtin verification timeout must be bounded by 7200 seconds')
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output / 'receipt.json'
    receipt = {'format': FORMAT, 'complete': False, 'source_root': str(root),
               'scope': 'canonical builtin source freshness and exact regeneration',
               'toolchain_qualification': False, 'source_files_rewritten': False, 'commands': []}

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')

    # Invalidate old success even when this attempt fails during preflight.
    save()
    try:
        snapshot = input_snapshot(root, compiler, generator)
        receipt.update(snapshot)
        save()
        for label, argv in commands(snapshot):
            verify_inputs(snapshot['inputs'])
            stdout_path, stderr_path = output / (label + '.stdout'), output / (label + '.stderr')
            entry = {'label': label, 'argv': argv, 'cwd': str(root),
                     'input_pins_verified_before': True, 'timeout_seconds': timeout}
            receipt['commands'].append(entry)
            save()
            with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
                process = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL,
                    stdout=stdout, stderr=stderr, start_new_session=True,
                    env={**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8'})
                try:
                    process.wait(timeout=timeout)
                except BaseException:
                    stop(process)
                    raise
                finally:
                    entry.update(exit_code=process.returncode, stdout=identified(stdout_path), stderr=identified(stderr_path))
                    save()
            verify_inputs(snapshot['inputs'])
            entry['input_pins_verified_after'] = True
            require(entry['exit_code'] == 0, 'builtin verification command failed: ' + label)
            require(not stderr_path.read_bytes(), 'builtin verification command wrote stderr: ' + label)
            expected = BANNER if label == 'check-candidate' else (root / CANONICAL).read_bytes()
            require(stdout_path.read_bytes() == expected,
                    'builtin verifier banner differs' if label == 'check-candidate' else 'fresh builtin literal differs from canonical source')
            save()
        require(input_snapshot(root, compiler, generator) == snapshot,
                'builtin verification input inventory changed during verification')
        receipt.update(exact_regeneration=True, candidate_verified=True, complete=True)
    except BaseException as error:
        receipt.update(complete=False, error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        try:
            verify_inputs(receipt.get('inputs', {}))
            receipt['immutable_inputs_verified_after'] = bool(receipt.get('inputs'))
        except BaseException as error:
            receipt.update(complete=False, immutable_inputs_verified_after=False,
                           input_error=type(error).__name__ + ': ' + str(error))
            save()
            raise
        save()
    return receipt_path


def authenticate(reference, root, compiler, generator):
    """Authenticate saved evidence without executing candidates again."""
    path = verify_file(reference)
    receipt = json.loads(path.read_text())
    require(receipt.get('format') == FORMAT and receipt.get('complete') is True,
            'complete builtin verification receipt required')
    require(receipt.get('immutable_inputs_verified_after') is True and
            receipt.get('exact_regeneration') is True and receipt.get('candidate_verified') is True and
            receipt.get('source_files_rewritten') is False and receipt.get('toolchain_qualification') is False,
            'incomplete builtin verification evidence')
    expected = input_snapshot(root, compiler, generator)
    for key, value in expected.items():
        require(receipt.get(key) == value, 'builtin verification input inventory mismatch: ' + key)
    verify_inputs(receipt['inputs'])
    rows = receipt.get('commands', [])
    require(len(rows) == 2, 'builtin verification command inventory mismatch')
    for entry, (label, argv) in zip(rows, commands(expected)):
        require(entry.get('label') == label and entry.get('argv') == argv and
                entry.get('cwd') == expected['source_root'] and entry.get('exit_code') == 0 and
                entry.get('input_pins_verified_before') is True and entry.get('input_pins_verified_after') is True,
                'builtin verification command evidence mismatch: ' + label)
        timeout = entry.get('timeout_seconds')
        require(type(timeout) in (int, float) and 0 < timeout <= 7200,
                'builtin verification command timeout is not bounded')
        stdout = verify_file(entry.get('stdout'), path.parent / (label + '.stdout'))
        stderr = verify_file(entry.get('stderr'), path.parent / (label + '.stderr'))
        require(not stderr.read_bytes(), 'builtin verification stderr is not empty')
        literal = BANNER if label == 'check-candidate' else Path(expected['canonical']['path']).read_bytes()
        require(stdout.read_bytes() == literal, 'builtin verification recorded output differs: ' + label)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--generator', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=1800)
    args = parser.parse_args()
    print(verify(args.root, args.compiler, args.generator, args.output, args.timeout))


if __name__ == '__main__':
    main()
