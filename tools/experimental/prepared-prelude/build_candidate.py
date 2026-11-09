#!/usr/bin/env python3
"""Build a frozen canonical macOS candidate; no closed-toolchain qualification."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/shared'))
from test_direct import CommandRunner


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ghc', type=Path, required=True)
    parser.add_argument('--cc', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('canonical_manifest', source / 'tools/shared/build.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    manifest = builder.load_manifest()
    ghc, cc = args.ghc.resolve(strict=True), args.cc.resolve(strict=True)
    inputs = [source / row['path'] for row in manifest['modules']]
    inputs += [source / row for row in manifest['host_only']]
    inputs += list((source / 'runtime').glob('*.h'))
    inputs += [source / 'shared-sources.json', source / 'mlf-shared.cabal',
               source / 'mlf-package.json', source / 'tools/shared/build.py',
               *source.glob('libraries/*/mlf-package.json'), Path(__file__).resolve(), ghc, cc]
    pins = {str(path): sha(path) for path in inputs}
    objects = out / 'objects'
    objects.mkdir()
    flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
             '-no-user-package-db', '-hide-all-packages', '-O2', '-fpedantic-bottoms', '-fno-state-hack',
             '-Werror=incomplete-patterns', '-Werror=incomplete-uni-patterns', '-Wno-star-is-type',
             '-Wno-overlapping-patterns', '-Wno-deprecations', '-i',
             *['-i' + str(source / root) for root in manifest['source_roots']],
             '-odir', str(objects), '-hidir', str(objects)]
    for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
        flags += ['-package', package]
    receipt = {'complete': False, 'scope': 'frozen canonical source, macOS correctness candidate',
               'closed_toolchain_qualification': False, 'source_conversion_or_overlay': False,
               'source': str(source), 'inputs': pins, 'flags': flags, 'commands': [], 'outputs': {},
               'primitive_abi': manifest['primitive_abi'], 'builtin_interface': manifest['builtin_interface']}

    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def run(label, command, timeout=600):
        command = list(map(str, command))
        started = time.monotonic()
        with (out / (label + '.stdout')).open('wb') as stdout, (out / (label + '.stderr')).open('wb') as stderr:
            process = subprocess.Popen(command, cwd=source, stdout=stdout, stderr=stderr,
                env={**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8'}, start_new_session=True)
            try:
                process.communicate(timeout=timeout)
            except BaseException:
                _, _, receipt['cleanup'] = CommandRunner.stop_group(process)
                raise
        receipt['commands'].append({'label': label, 'argv': command, 'exit': process.returncode,
                                    'seconds': time.monotonic() - started})
        save()
        if process.returncode:
            raise RuntimeError(label + ' failed')

    save()
    try:
        for label, relative in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            run(label, [cc, '-O2', '-std=c11', '-I' + str(source / 'runtime'), '-c', source / relative,
                        '-o', out / (label + '.o')])
        run('canonical-modules', [ghc, '--make', '-j1', '-no-link', *flags,
                                 *[source / row['path'] for row in manifest['modules']]])
        for name in ['emlf', 'builtin-prelude']:
            row = next(row for row in manifest['executables'] if row['name'] == name)
            run('link-' + name, [ghc, '--make', '-j1', *flags, source / row['wrapper'],
                                out / 'host.o', out / 'supervisor.o', '-o', out / name])
            receipt['outputs'][name] = {'path': str(out / name), 'sha256': sha(out / name),
                                         'bytes': (out / name).stat().st_size}
        receipt['complete'] = True
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        changed = [path for path, expected in pins.items() if sha(path) != expected]
        receipt['immutable_inputs_verified_after'] = not changed
        if changed:
            receipt.update(complete=False, changed_inputs=changed)
        save()
        if changed:
            raise RuntimeError('candidate inputs changed')
    print(out / 'receipt.json')


if __name__ == '__main__':
    main()
