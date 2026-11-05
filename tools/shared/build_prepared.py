#!/usr/bin/env python3
"""Build an owned GHC -O2 source tree with a fixed, freshly verified library closure.

No user program is an input. Lexical source paths retain the original manifest
prefix (or the explicit --lexical-root); moving this job does not rebase them.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = 'bootstrap/MLF/PreparedLibraryData.hs'
NATIVE_DATA = 'bootstrap/MLF/PreparedNativeData.hs'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def dump(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')

def inventory(root):
    raw = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'])
    names = sorted(set(raw.decode().split('\0')) - {''})
    for name in names:
        path = Path(name)
        if path.is_absolute() or any(p in {'.git', '.mlf-build', '..'} for p in path.parts):
            raise ValueError('unsafe source inventory entry: ' + name)
        if not (root / path).is_file() or (root / path).is_symlink():
            raise ValueError('source must be a regular file: ' + name)
    return names

def complete_snapshot(root, job, names):
    pins = json.loads((job / 'source-pins.json').read_text())
    if not set(pins) <= set(names):
        raise ValueError('staged sources missing from git source inventory')
    for name in names:
        source, target = root / name, job / 'sources' / name
        before = digest(source)
        if name in pins and pins[name]['sha256'] != before:
            raise ValueError('source changed during staging: ' + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(source) != before or digest(target) != before:
            raise ValueError('source changed during copy: ' + name)
        pins[name] = {'path': str(source), 'snapshot': str(target), 'sha256': before,
                      'bytes': target.stat().st_size, 'mode': stat.S_IMODE(target.stat().st_mode)}
    if inventory(root) != names:
        raise ValueError('source inventory changed during staging')
    identity = json.loads((job / 'identity-input.json').read_text())
    identity['source_hashes'] = {name: pin['sha256'] for name, pin in pins.items() if name not in {DATA, NATIVE_DATA}}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    request = json.loads((job / 'request.json').read_text())
    request.update(input_identity=key, library_identity='mlf:prepared-library:' + key)
    dump(job / 'source-pins.json', pins)
    dump(job / 'identity-input.json', identity)
    dump(job / 'request.json', request)
    dump(job / 'owned-source.json', {'format': 1, 'root': str(root), 'inventory': names,
                                   'input_identity': key})
    receipt = json.loads((job / 'receipt.json').read_text())
    receipt.update(input_identity=key, source_pins=pins)
    dump(job / 'receipt.json', receipt)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--library-manifest', type=Path, required=True)
    p.add_argument('--module', action='append', default=[])
    p.add_argument('--standard-library', action='store_true', help='select the complete explicit package module inventory')
    p.add_argument('--compiler-optimization', choices=['0', '2'], default='2')
    p.add_argument('--compiler-at-root', action='store_true', help='preserve public BUILD/bin and BUILD/receipt.json layout')
    p.add_argument('--lexical-root')
    p.add_argument('--no-prelude', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--native-config', type=Path, help='install fixed native library/runtime from exact JSON toolchain flags')
    p.add_argument('--ghc', default='ghc')
    p.add_argument('--cc', default='cc')
    a = p.parse_args()
    if a.standard_library:
        if a.module:
            p.error('--standard-library and --module cannot be combined')
        a.module = sorted(json.loads(a.library_manifest.read_text())['library']['modules'])
    if not a.module:
        p.error('choose --standard-library or explicit --module roots')
    job = a.output.resolve()
    if job == ROOT or ROOT.is_relative_to(job):
        raise ValueError('output must not contain the source checkout')
    names = inventory(ROOT)
    tool = ROOT / 'tools/experimental/prepared-libraries'
    def run(args):
        subprocess.run([sys.executable, *map(str, args)], check=True, cwd=ROOT)
    args = [tool / 'prepare.py', '--library-manifest', a.library_manifest.resolve(), '--output', job]
    for name in a.module:
        args += ['--module', name]
    if a.lexical_root is not None:
        args += ['--lexical-root', a.lexical_root]
    if a.no_prelude:
        args += ['--no-prelude']
    run(args)
    complete_snapshot(ROOT, job, names)
    owned = job / 'sources'
    tool = owned / 'tools/experimental/prepared-libraries'
    ghc, cc = shutil.which(a.ghc), shutil.which(a.cc)
    if not ghc or not cc:
        raise ValueError('GHC and C compiler must be installed')
    run([tool / 'build.py', '--job', job, '--ghc', ghc, '--cc', cc, '--generate-only'])
    run([tool / 'regenerate.py', '--job', job])
    if a.native_config:
        run([owned / 'tools/shared/native_install.py', '--job', job, '--config', a.native_config.resolve()])
    compiler = job if a.compiler_at_root else job / 'compiler'
    if a.compiler_at_root:
        # Preserve the original staging receipt before the normal builder writes
        # its distinct public receipt. No verifier treats this as a compiler proof.
        (job / 'preparation-receipt.json').write_bytes((job / 'receipt.json').read_bytes())
    run([owned / 'tools/shared/build.py', '--bootstrap-only', '--ghc', ghc, '--cc', cc,
         '--optimization', a.compiler_optimization, '--build-dir', compiler])
    print(compiler / 'receipt.json')

if __name__ == '__main__':
    main()
