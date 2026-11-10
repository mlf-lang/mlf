#!/usr/bin/env python3
"""Safe Ormolu/current-parser corpus check; never rewrites maintained sources.

This is syntax/AST compatibility evidence, not a native bootstrap, typechecking,
execution or fixed-point claim. Every invocation builds the host harness afresh.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
FORMAT_FLAGS = ['--no-cabal', '--no-dot-ormolu', '--check-idempotence', '--color', 'never']
PACKAGES = ['base', 'array', 'bytestring', 'text', 'containers', 'directory']


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def executable(value):
    found = shutil.which(value)
    if not found:
        raise RuntimeError('executable not found: ' + value)
    return Path(found).absolute()


def corpus_sources(root):
    return (sorted((root / "libraries").rglob("*.hs"))
            + sorted((root / "tools/shared/fixtures/formatter").rglob("*.hs")))


def source_inputs(root, roots):
    paths = {root / 'shared-sources.json', root / 'tools/shared/FormatterCompatibility.hs',
             root / 'tools/shared/test_formatter_compatibility.py',
             root / 'host/ghc/cbits/host.c', root / 'runtime/mlf_process_supervisor.c'}
    for directory in roots:
        paths.update((root / directory).rglob('*.hs'))
    paths.update((root / 'runtime').glob('*.h'))
    paths.update((root / 'host/ghc').rglob('*.h'))
    paths.update((root / 'tools/shared/fixtures/formatter').rglob('*.hs'))
    return {str(path.relative_to(root)): sha(path) for path in sorted(paths)}


def run(command, output, label, timeout, receipt, stdout=None):
    command = list(map(str, command))
    out = stdout or output / 'logs' / (label + '.stdout')
    err = output / 'logs' / (label + '.stderr')
    event = {'command': command, 'stdout': str(out), 'stderr': str(err)}
    receipt['commands'].append(event)
    with out.open('wb') as fout, err.open('wb') as ferr:
        try:
            process = subprocess.run(command, cwd=ROOT, stdout=fout, stderr=ferr,
                                     timeout=timeout, check=False)
            event['returncode'] = process.returncode
        except subprocess.TimeoutExpired:
            event['timed_out'] = True
            raise RuntimeError('timed out: ' + label)
    return process.returncode, out.read_text(errors='replace'), err.read_text(errors='replace')


def require_success(result, label):
    if result[0] != 0:
        raise RuntimeError(label + ' failed; see command logs')
    return result[1].strip()


def controls(binary, output, timeout, receipt):
    folder = output / 'controls'
    folder.mkdir()
    prologue = ('-- mlf:syntax shared-haskell-v1\n'
                '{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,\n'
                'KindSignatures, FlexibleContexts, FlexibleInstances,\n'
                'MultiParamTypeClasses, OverloadedStrings #-}\n')
    baseline = prologue + 'module Control where\nimport MLF.Primitive (Int)\nvalue = 1\nother = 2\n'
    original = folder / 'Original.hs'
    original.write_text(baseline)
    cases = [('identity', baseline, None),
             ('literal', baseline.replace('value = 1', 'value = 3'), 'source AST changed'),
             ('binding', baseline.replace('other = 2\n', ''), 'source AST changed'),
             ('import-selection', baseline.replace('(Int)', '(Bool)'), 'import multiset changed'),
             ('parser-rejection', prologue + 'module Control where\nvalue = (\n', 'parse failed:')]
    for name, content, diagnostic in cases:
        altered = folder / (name + '.hs')
        altered.write_text(content)
        result = run([binary, original, altered], output, 'control-' + name, timeout, receipt)
        passed = (result[0] == 0 if diagnostic is None else
                  result[0] == 1 and diagnostic in result[2])
        receipt['controls'].append({'name': name, 'passed': passed,
                                    'original_sha256': sha(original), 'altered_sha256': sha(altered)})
        if not passed:
            raise RuntimeError('harness control failed: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', default='ghc')
    parser.add_argument('--ormolu', default='ormolu')
    parser.add_argument('--output', type=Path, help='must not already exist')
    parser.add_argument('--timeout', type=int, default=60, help='seconds per formatter/parser invocation')
    parser.add_argument('--compile-timeout', type=int, default=600)
    args = parser.parse_args()
    if args.timeout <= 0 or args.compile_timeout <= 0:
        parser.error('timeouts must be positive')
    if args.output:
        output = args.output.absolute()
        output.mkdir(parents=True, exist_ok=False)
    else:
        output = Path(tempfile.mkdtemp(prefix='mlf-formatter-compat-'))
    (output / 'logs').mkdir()
    receipt = {'schema': 1, 'completed': False, 'scope': 'host parser syntax/AST compatibility',
               'output': str(output), 'files': [], 'controls': [], 'commands': [],
               'formatted_count': 0, 'passed_count': 0}
    try:
        ghc, ormolu = executable(args.ghc), executable(args.ormolu)
        ghc_version = require_success(run([ghc, '--numeric-version'], output, 'ghc-version', args.timeout, receipt), 'GHC version')
        formatter_version = require_success(run([ormolu, '--version'], output, 'ormolu-version', args.timeout, receipt), 'Ormolu version')
        if ghc_version != '9.14.1' or not formatter_version.startswith('ormolu 0.9.0.0 '):
            raise RuntimeError('requires GHC 9.14.1 and Ormolu 0.9.0.0')
        libdir = Path(require_success(run([ghc, '--print-libdir'], output, 'ghc-libdir', args.timeout, receipt), 'GHC libdir'))
        actual_ghc = libdir.parent / 'bin' / 'ghc-9.14.1'
        receipt['tools'] = {'ghc': {'path': str(ghc), 'sha256': sha(ghc), 'version': ghc_version,
                                    'actual_path': str(actual_ghc), 'actual_sha256': sha(actual_ghc)},
                            'ormolu': {'path': str(ormolu), 'sha256': sha(ormolu), 'version': formatter_version}}
        manifest = json.loads((ROOT / 'shared-sources.json').read_text())
        roots = manifest['source_roots']
        if ('host/ghc' not in roots or len(set(roots)) != len(roots)
                or any(Path(p).is_absolute() or '..' in Path(p).parts
                       or not (ROOT / p).is_dir() for p in roots)):
            raise RuntimeError('invalid source roots')
        receipt['source_sha256'] = source_inputs(ROOT, roots)
        sources = corpus_sources(ROOT)
        if not sources:
            raise RuntimeError('empty corpus')
        receipt['files'] = [{'path': str(p.relative_to(ROOT)), 'original_sha256': sha(p), 'passed': False} for p in sources]
        objects = output / 'objects'
        objects.mkdir()
        binary = output / 'formatter-compatibility'
        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
                 '-no-user-package-db', '-hide-all-packages', '-O1', '-fpedantic-bottoms',
                 '-fno-state-hack', '-Werror=incomplete-patterns', '-i',
                 *['-i' + str(ROOT / p) for p in roots], '-odir', objects, '-hidir', objects]
        for package in PACKAGES:
            flags.extend(['-package', package])
        require_success(run([ghc, '--make', '-j1', '-fforce-recomp', *flags,
                             ROOT / 'tools/shared/FormatterCompatibility.hs',
                             ROOT / 'host/ghc/cbits/host.c', ROOT / 'runtime/mlf_process_supervisor.c',
                             '-I' + str(ROOT / 'runtime'), '-o', binary], output, 'compile', args.compile_timeout, receipt), 'harness build')
        receipt['harness_sha256'] = sha(binary)
        controls(binary, output, args.timeout, receipt)
        failures = []
        for index, (source, entry) in enumerate(zip(sources, receipt['files'])):
            formatted = output / 'formatted' / entry['path']
            formatted.parent.mkdir(parents=True, exist_ok=True)
            entry['formatted_path'] = str(formatted)
            result = run([ormolu, *FORMAT_FLAGS, source], output, f'format-{index}', args.timeout, receipt, stdout=formatted)
            entry['formatted_sha256'] = sha(formatted)
            if result[0] != 0:
                failures.append(entry['path'] + ': formatter failed')
                continue
            receipt['formatted_count'] += 1
            result = run([binary, source, formatted], output, f'compare-{index}', args.timeout, receipt)
            if result[0] != 0:
                failures.append(entry['path'] + ': parser comparison failed')
                continue
            entry['passed'] = True
            receipt['passed_count'] += 1
        if source_inputs(ROOT, roots) != receipt['source_sha256']:
            failures.append('source inputs changed during run')
        if failures:
            receipt['failures'] = failures
            raise RuntimeError(f'{len(failures)} failures; see receipt and logs')
        receipt['completed'] = True
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        receipt['error'] = str(error)
    finally:
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(str(output / 'receipt.json'))
    print(f"{receipt['passed_count']}/{len(receipt['files'])} file pairs passed")
    if not receipt['completed']:
        print(receipt.get('error', 'incomplete run'), file=sys.stderr)
    return 0 if receipt['completed'] else 1


if __name__ == '__main__':
    sys.exit(main())
