#!/usr/bin/env python3
"""Build an isolated compiler-owned raw Prelude experiment from exact sources.

This is not the production compiler or a native qualification. No user program
is installed/cached. The generated raw constructor data is checked at startup.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/shared'))
from test_direct import CommandRunner


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', type=Path, required=True)
    parser.add_argument('--cc', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    objects, generated = out / 'objects', out / 'generated'
    objects.mkdir()
    (generated / 'Bootstrap').mkdir(parents=True)
    manifest = ROOT / 'shared-sources.json'
    source_roots = [ROOT / p for p in json.loads(manifest.read_text())['source_roots']]
    inputs = {manifest, Path(__file__), ROOT / 'tools/shared/test_direct.py', *HERE.rglob('*.hs'),
              ROOT / 'tools/experimental/installed-prelude/source/Bootstrap/Standalone.hs',
              ROOT / 'host/ghc/cbits/host.c', ROOT / 'runtime/mlf_process_supervisor.c',
              *sorted((ROOT / 'runtime').glob('*.h'))}
    for root in source_roots:
        inputs.update(root.rglob('*.hs'))
    ghc, cc = args.ghc.resolve(strict=True), args.cc.resolve(strict=True)
    inputs.update([ghc, cc])
    pins = {str(path): digest(path) for path in sorted(inputs)}
    # A snapshot makes later unrelated source edits harmless to this producer.
    # Copy and authenticate every selected source before invoking either GHC.
    snapshot = out / 'source'
    snapshot_pins = {}
    for source in sorted(inputs):
        if source.is_relative_to(ROOT):
            target = snapshot / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            if digest(target) != pins[str(source)]:
                raise RuntimeError('source changed while snapshotting: ' + str(source))
            snapshot_pins[str(target)] = pins[str(source)]
    build_here = snapshot / HERE.relative_to(ROOT)
    source_roots = [snapshot / root.relative_to(ROOT) for root in source_roots]
    receipt = {'complete': False, 'scope': 'opt-in raw builtin AST, full startup checking, whole root inference',
               'source_pins': pins, 'compiled_snapshot_pins': snapshot_pins,
               'commands': [], 'user_program_cache': False,
               'default_compiler_changed': False, 'native_qualification': False}
    environment = {**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8'}

    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def run(label, command, output=None, timeout=600):
        started = time.monotonic()
        target = output or out / (label + '.stdout')
        with target.open('wb') as stdout, (out / (label + '.stderr')).open('wb') as stderr:
            process = subprocess.Popen(list(map(str, command)), cwd=snapshot, env=environment,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                process.communicate(timeout=timeout)
            except BaseException:
                _, _, receipt['cleanup'] = CommandRunner.stop_group(process)
                raise
        receipt['commands'].append({'label': label, 'argv': list(map(str, command)),
                                    'exit': process.returncode, 'seconds': time.monotonic() - started})
        save()
        if process.returncode:
            raise RuntimeError(label + ' failed; see ' + str(out / (label + '.stderr')))

    save()
    try:
        for label, source in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            run(label, [cc, '-O2', '-std=c11', '-I' + str(snapshot / 'runtime'), '-c', snapshot / source,
                        '-o', out / (label + '.o')])
        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
                 '-no-user-package-db', '-hide-all-packages', '-O2', '-fpedantic-bottoms', '-fno-state-hack',
                 '-Werror=incomplete-patterns', '-Werror=incomplete-uni-patterns', '-Wno-star-is-type',
                 '-Wno-overlapping-patterns', '-Wno-deprecations', '-i',
                 *['-i' + str(root) for root in source_roots], '-odir', objects, '-hidir', objects]
        for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
            flags += ['-package', package]
        transports = [out / 'host.o', out / 'supervisor.o']
        run('build-generator', [ghc, '--make', '-j1', *flags, build_here / 'Generate.hs', *transports,
                                '-o', out / 'generate-builtin'])
        raw = generated / 'Bootstrap/PreparedBuiltinData.hs'
        run('generate-builtin', [out / 'generate-builtin'], raw, timeout=300)
        receipt['generated_raw_ast'] = {'path': str(raw), 'sha256': digest(raw), 'bytes': raw.stat().st_size}
        snapshot_pins[str(raw)] = digest(raw)
        overlays = [generated, build_here / 'source', snapshot / 'tools/experimental/installed-prelude/source']
        # Explicitly select the already-reviewed normalization factoring seam;
        # all other modules are the current ordinary sources listed above.
        include = flags.index('-i') + 1
        flags[include:include] = ['-i' + str(root) for root in overlays]
        run('build-prototype', [ghc, '--make', '-j1', *flags, build_here / 'source/Harness.hs', *transports,
                               '-o', out / 'prepared-emlf'])
        receipt.update(complete=True, executable=str(out / 'prepared-emlf'),
                       executable_sha256=digest(out / 'prepared-emlf'))
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        changed = [path for path, expected in snapshot_pins.items() if digest(Path(path)) != expected]
        changed += [str(path) for path in [ghc, cc] if digest(path) != pins[str(path)]]
        receipt['live_sources_changed_after_snapshot'] = [path for path, expected in pins.items()
            if Path(path).is_relative_to(ROOT) and digest(Path(path)) != expected]
        receipt['immutable_inputs_verified_after'] = not changed
        if changed:
            receipt.update(complete=False, changed_inputs=changed)
        save()
        if changed:
            raise RuntimeError('inputs changed during experimental build')
    print(out / 'prepared-emlf')


if __name__ == '__main__':
    main()
