#!/usr/bin/env python3
"""Build the portable fresh Prelude producer and run context mutation controls."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
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
    manifest_data = json.loads(manifest.read_text())
    source_roots = [ROOT / p for p in manifest_data['source_roots']]
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
    receipt = {'complete': False, 'scope': 'portable fresh prelinked Prelude generator and independent startup controls',
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
        # Compute a host-independent identity over the actual nongenerated
        # shared generator closure. Metadata registration does not alter it.
        module_sources = {}
        for root in source_roots:
            for path in root.rglob('*.hs'):
                match = re.search(r'^module\s+([A-Z][\w.]*)', path.read_text(), re.M)
                if match:
                    name = match.group(1)
                    if name == 'Main':
                        continue
                    if name in module_sources and module_sources[name] != path:
                        raise RuntimeError('duplicate source module: ' + name)
                    module_sources[name] = path
        pending, closure = ['MLF.Entry.BuiltinPrelude'], {}
        while pending:
            name = pending.pop()
            if name == 'MLF.Primitive' or name in closure:
                continue
            path = module_sources[name]
            closure[name] = {'path': str(path.relative_to(snapshot)), 'sha256': digest(path)}
            pending.extend(re.findall(r'^\s*import\s+(?:qualified\s+)?([A-Z][\w.]*)', path.read_text(), re.M))
        identity_inputs = {'format': 'builtin-source-v1', 'modules': closure,
            'source_syntax': manifest_data['source_syntax'],
            'frontend_semantics': manifest_data['frontend_semantics'],
            'primitive_abi': manifest_data['primitive_abi'],
            'builtin_interface': manifest_data['builtin_interface']}
        identity = 'builtin-source-v1:' + hashlib.sha256(json.dumps(identity_inputs, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()
        receipt['source_identity_inputs'] = identity_inputs
        receipt['source_identity'] = identity
        run('build-generator', [ghc, '--make', '-j1', *flags,
            snapshot / 'host/ghc/app/builtin-prelude/Main.hs', *transports, '-o', out / 'generate-builtin'])
        raw = generated / 'MLF/BuiltinPreludeData.hs'
        raw.parent.mkdir(parents=True, exist_ok=True)
        run('generate-builtin', [out / 'generate-builtin', identity], raw, timeout=300)
        receipt['generated_raw_ast'] = {'path': str(raw), 'sha256': digest(raw), 'bytes': raw.stat().st_size}
        snapshot_pins[str(raw)] = digest(raw)
        run('build-controls', [ghc, '--make', '-j1', *flags,
            build_here / 'BuiltinPreludeContextControls.hs', *transports, '-o', out / 'context-controls'])
        run('context-controls', [out / 'context-controls'], timeout=180)
        lines = (out / 'context-controls.stdout').read_text().splitlines()
        if len(lines) != 40 or lines[-1] != 'PASS all 39 builtin context controls' or len(set(lines[:-1])) != 39:
            raise RuntimeError('context control inventory changed')
        receipt['context_controls'] = lines[:-1]
        receipt.update(complete=True, executable=str(out / 'generate-builtin'),
                       executable_sha256=digest(out / 'generate-builtin'))
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
    print(out / 'receipt.json')


if __name__ == '__main__':
    main()
