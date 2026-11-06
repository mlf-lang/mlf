#!/usr/bin/env python3
"""Public shared compiler build: fixed standard-library installation defaults."""
from __future__ import annotations
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


def configuration(clang='clang'):
    executable = shutil.which(clang)
    if not executable:
        raise RuntimeError('Clang is required for the standard library installation')
    includes, libraries = [], []
    for package, stem, static in [('gmp', 'gmp', False), ('bdw-gc', 'gc', True)]:
        try:
            flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', package], text=True))
            directory = Path(subprocess.check_output(['pkg-config', '--variable=libdir', package], text=True).strip())
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            raise RuntimeError('install pkg-config and development packages for GMP/BDWGC, or pass --native-config') from error
        if not directory.is_absolute():
            raise RuntimeError('pkg-config must identify an absolute library directory')
        for flag in flags:
            if flag not in includes:
                includes.append(flag)
        suffixes = ['.a'] if static else (['.dylib', '.a'] if sys.platform == 'darwin' else ['.so', '.a'])
        candidates = [directory / ('lib' + stem + suffix) for suffix in suffixes]
        chosen = next((p for p in candidates if p.is_file()), None)
        if chosen is None:
            raise RuntimeError('missing fixed native dependency: ' + str(candidates))
        libraries.append(str(chosen.resolve(strict=True)))
    return {'clang': str(Path(executable).resolve()), 'runtime_flags': includes, 'link_args': libraries + ['-lm']}


def build(root, options):
    output = options.build_dir.resolve()
    if output.exists():
        raise RuntimeError('standard-library installation requires a fresh --build-dir; use --bootstrap-only for explicit low-level development builds')
    manifest = root / 'libraries/mlf-foundation/mlf-package.json'
    modules = json.loads(manifest.read_text())['library']['modules']
    if not modules:
        raise RuntimeError('standard library package has no explicit module inventory')
    command = [sys.executable, str(root / 'tools/shared/build_prepared.py'),
        '--library-manifest', str(manifest), '--standard-library',
        '--lexical-root', str(output / 'sources/libraries/mlf-foundation'),
        '--ghc', options.ghc, '--cc', options.cc, '--compiler-optimization', options.optimization,
        '--compiler-at-root', '--output', str(output)]
    if options.native_config:
        subprocess.run(command + ['--native-config', str(options.native_config.resolve(strict=True))], check=True, cwd=root)
    else:
        with tempfile.TemporaryDirectory(prefix='mlf-native-config-') as temporary:
            config = Path(temporary) / 'config.json'
            config.write_text(json.dumps(configuration(options.clang), indent=2) + '\n')
            subprocess.run(command + ['--native-config', str(config)], check=True, cwd=root)
