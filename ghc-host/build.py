#!/usr/bin/env python3
"""Generate the implementation dialect, then build it offline with Cabal.

Only Python's standard library, installed GHC/Cabal packages and the C compiler
are required. This never invokes emlf or mlfpkg to produce the GHC compiler.
"""
import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tool_identity(name, version_args):
    found = shutil.which(name)
    if not found:
        raise RuntimeError('required installed tool is missing: '+name)
    path = Path(found).resolve()
    return {'path':str(path),'sha256':sha(path),
            'version':subprocess.check_output([str(path),*version_args],text=True).strip()}


def run(args, cwd=ROOT):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, default=ROOT / '.mlf-build/ghc-host')
    parser.add_argument('--optimization', choices=['0', '1', '2'], default='0')
    parser.add_argument('--generate-only', action='store_true')
    options = parser.parse_args()
    output = options.build_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    converter = output / 'mlf-to-haskell'
    run(['ghc', '-O0', '-w', '-i'+str(ROOT/'ghc-host/converter'),
         '-outputdir', output/'converter', '-o', converter, ROOT/'ghc-host/converter/Main.hs'])
    modules = {}
    manifests = sorted((ROOT/'libraries').glob('*/mlf-package.json'))
    for manifest in manifests:
        data = json.loads(manifest.read_text())
        for name, source in data.get('library', {}).get('modules', {}).items():
            if name in modules:
                raise ValueError('duplicate module: '+name)
            modules[name] = manifest.parent/source
    root_manifest = ROOT/'mlf-package.json'
    executables = json.loads(root_manifest.read_text())['executables']
    entries = {}
    for name, spec in executables.items():
        entry = 'MLF.Entry.' + ''.join(word.title() for word in name.split('-'))
        entries[name] = entry
        modules[entry] = ROOT/spec['main']
        for module, source in spec.get('modules', {}).items():
            if module in modules and modules[module] != ROOT/source:
                raise ValueError('conflicting private module: '+module)
            modules[module] = ROOT/source
    lines = []
    source_hashes = {}
    for module, source in sorted(modules.items()):
        target = output/'generated'/(module.replace('.', '/')+'.hs')
        target.parent.mkdir(parents=True, exist_ok=True)
        # Relative source paths make generated text/source maps reproducible
        # across isolated checkouts. Output paths do not appear in generated code.
        relative = str(source.relative_to(ROOT))
        source_hashes[relative] = sha(source)
        lines.append('\t'.join([relative, str(target), module])+'\n')
    manifest = output/'sources.tsv'
    manifest.write_text(''.join(lines))
    run([converter, '--batch', manifest])
    shutil.copytree(ROOT/'ghc-host/runtime', output/'host-runtime', dirs_exist_ok=True)
    shutil.copytree(ROOT/'runtime', output/'native-runtime', dirs_exist_ok=True)
    (output/'cbits').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'ghc-host/cbits/host.c', output/'cbits/host.c')
    shutil.copy2(ROOT/'LICENSE', output/'LICENSE')
    entry_dir = output/'entry'
    entry_dir.mkdir(exist_ok=True)
    cabal = [
        'cabal-version: 3.0', 'name: mlf-ghc-host', 'version: 0.3.0',
        'build-type: Simple', 'license: BSD-3-Clause', '',
        'library', '  hs-source-dirs: generated, host-runtime',
        '  exposed-modules: '+', '.join(sorted(modules)),
        '  other-modules: MLF.Host.Base, MLF.Host.IO, MLF.Host.Async, MLF.Host.Primitives',
        '  build-depends: base >= 4.18 && < 5, array, bytestring, text >= 2, containers, directory',
        '  default-language: Haskell2010', '  ghc-options: -w',
        '  c-sources: cbits/host.c, native-runtime/mlf_process_supervisor.c',
        '  include-dirs: native-runtime',
    ]
    for name, module in sorted(entries.items()):
        source = name+'.hs'
        (entry_dir/source).write_text('module Main where\nimport MLF.Host.IO (runEntry)\nimport qualified '+module+' as Entry\nmain :: IO ()\nmain = runEntry Entry.v_main\n')
        cabal.extend(['', 'executable '+name, '  hs-source-dirs: entry', '  main-is: '+source,
                      '  build-depends: base, mlf-ghc-host', '  default-language: Haskell2010'])
    # Entry wrappers use the host runner without exposing the rest of its API.
    cabal[8] += ', MLF.Host.IO'
    cabal[9] = cabal[9].replace('MLF.Host.IO, ', '')
    (output/'mlf-ghc-host.cabal').write_text('\n'.join(cabal)+'\n')
    (output/'cabal.project').write_text('packages: .\nactive-repositories: :none\noptimization: '+options.optimization+'\njobs: 1\n')
    inputs = {**source_hashes, **{str(p.relative_to(ROOT)): sha(p) for p in (ROOT/'ghc-host').rglob('*') if p.is_file() and '__pycache__' not in p.parts},
              **{str(p.relative_to(ROOT)): sha(p) for p in (ROOT/'runtime').glob('*') if p.is_file()},
              **{str(p.relative_to(ROOT)): sha(p) for p in manifests+[root_manifest]}}
    evidence = {'format': 1, 'complete': False, 'implementation_source': 'MLF', 'host': 'GHC',
                'code_baseline': '8a3e69b165765931c3ff762379a78db9659b2cd8',
                'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'ghc': subprocess.check_output(['ghc', '--numeric-version'], text=True).strip(),
                'cabal': subprocess.check_output(['cabal', '--numeric-version'], text=True).strip(),
                'optimization': options.optimization, 'inputs': inputs,
                'converter_sha256': sha(converter),
                'generated': {str(p.relative_to(output)): sha(p) for p in (output/'generated').rglob('*.hs')},
                'executables': {}}
    evidence['platform']={'system':platform.system(),'machine':platform.machine(),'release':platform.release()}
    evidence['toolchain']={name:tool_identity(name,args) for name,args in
                          [('ghc',['--numeric-version']),('cabal',['--numeric-version']),
                           (os.environ.get('CC','clang'),['--version']),('python3',['--version'])]}
    for label,command in [('ghc-info',['ghc','--info']),('ghc-packages',['ghc-pkg','dump','--global'])]:
        destination=output/(label+'.txt')
        destination.write_bytes(subprocess.check_output(command))
        evidence[label]={'path':str(destination),'sha256':sha(destination),'command':command}
    evidence_path = output/'build-evidence.json'
    evidence_path.write_text(json.dumps(evidence, indent=2)+'\n')
    if options.generate_only:
        return
    config = output/'cabal.config'
    config.write_text('active-repositories: :none\nstore-dir: '+str(output/'store')+'\nlogs-dir: '+str(output/'logs')+'\nremote-repo-cache: '+str(output/'packages')+'\n')
    cabal_command = ['cabal', '--config-file='+str(config)]
    start = time.monotonic()
    run(cabal_command+['v2-build', '--offline', '--project-file='+str(output/'cabal.project'), 'all'], output)
    binary_dir = output/'bin'
    binary_dir.mkdir(exist_ok=True)
    for name in entries:
        built = Path(subprocess.check_output(cabal_command+['list-bin', '--project-file='+str(output/'cabal.project'), 'exe:'+name], cwd=output, text=True).strip())
        target = binary_dir/name
        shutil.copy2(built, target)
        evidence['executables'][name] = {'path': str(target), 'sha256': sha(target)}
    run([os.environ.get('CC', 'clang'), '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', ROOT/'runtime/mlf_build_runner.c', '-o', binary_dir/'mlf-build-runner'])
    run([binary_dir/'mlf-build-runner', '--protocol-version'])
    evidence['executables']['mlf-build-runner'] = {'path': str(binary_dir/'mlf-build-runner'), 'sha256': sha(binary_dir/'mlf-build-runner')}
    for relative, expected in inputs.items():
        if sha(ROOT/relative) != expected:
            raise RuntimeError('input changed during build: '+relative)
    for tool in evidence['toolchain'].values():
        if sha(Path(tool['path'])) != tool['sha256']:
            raise RuntimeError('tool changed during build: '+tool['path'])
    evidence.update(complete=True, build_seconds=time.monotonic()-start)
    evidence_path.write_text(json.dumps(evidence, indent=2)+'\n')
    print('Build receipt:', evidence_path)


if __name__ == '__main__':
    main()
