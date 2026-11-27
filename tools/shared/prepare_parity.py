#!/usr/bin/env python3
"""Build the existing parity fixtures with an authenticated GHC O0 producer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from build import DEMAND_FLAGS, PACKAGES
from test_direct import CommandRunner, authenticate_build, identified, verify_file

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = 'MLF/shared-haskell-v1 GHC'

# Compile fixture modules in import order. Both programs expose the same
# guest entry interface, main :: IO (), to the GHC host wrapper.
CORPUS = ('Tests.Helpers', 'Tests.Map', 'Tests.Set', 'Tests.Figure12',
          'Tests.Oracle', 'Tests.Corpus', 'CorpusMain')

PRAGMA = ('{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, '
          'FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings, KindSignatures #-}\n')
# Consume comments and strings whole before matching legacy boolean literals
# and type annotations. In particular, keep embedded guest programs intact.
TOKENS = re.compile(
    r'--[^\n]*|"(?:[^"\\]|\\.)*"|\b(?:true|false)\b|'
    r'(?P<recursive>\blet[ \t]+rec\b)|'
    r"\((?P<binder>[a-z][\w']*)[ \t]+:[ \t]+\*[ \t]*->[ \t]*\*\)|"
    r'(?:^[ ]*|(?<=[{;] ))[a-z][A-Za-z0-9_]* +:(?= +)',
    re.MULTILINE,
)


def host_token(match):
    token = match[0]
    if match.group('recursive'):
        return 'let'
    if match.group('binder'):
        return '(' + match.group('binder') + ' :: Type -> Type)'
    if token in ('true', 'false'):
        return token.capitalize()
    if token.endswith(':') and not token.startswith(('--', '"')):
        return token + ':'
    return token


def host_source(module, source):
    source = re.sub(r'^import Prelude hiding .*\n', '', source, flags=re.MULTILINE)
    hidden = {'Tests.Helpers': ' hiding (Eq, fail, fmap)', 'Tests.Oracle': ' hiding (fail)'}
    imports = 'import MLF.Primitive' + hidden.get(module, '') + '\n'
    if module == 'Tests.Helpers':
        imports += 'import Data.Kind (Type)\n'
    declaration = re.compile(r'^module[ \t]+' + re.escape(module) + r'[ \t]+where[ \t]*$', re.MULTILINE)
    source, count = declaration.subn(lambda match: match[0] + '\n' + imports, source)
    if count != 1:
        raise ValueError('expected a single module declaration for ' + module)
    return PRAGMA + TOKENS.sub(host_token, source)


def verify_objects(build, objects):
    available = {
        str(path.relative_to(build)) for path in (build / 'objects').rglob('*') if path.is_file()
    }
    if not objects or set(objects) != available:
        raise ValueError('producer object inventory differs from the available objects and interfaces')
    for name, digest in objects.items():
        path = build / name
        verify_file({'path': str(path), 'sha256': digest})


def prepare(build_receipt, output):
    build_receipt = build_receipt.resolve(strict=True)
    build, output = build_receipt.parent, output.resolve()
    if output == ROOT or ROOT.is_relative_to(output) or output.is_relative_to(build):
        raise ValueError('parity fixtures require a separate fresh output directory')
    output.mkdir(parents=True, exist_ok=False)
    record = {
        'format': 1, 'complete': False, 'producer_host': 'GHC',
        'implementation_identity': IDENTITY, 'optimization': '0', 'commands': [],
        'build_receipt': str(build_receipt), 'sources': {}, 'outputs': {},
    }

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'receipt.json')

    save()
    runner = CommandRunner(ROOT, output, record, save)
    try:
        producer_identity = identified(build_receipt)
        record['build_receipt_sha256'] = producer_identity['sha256']
        producer = authenticate_build(build_receipt, build / 'bin')
        if producer['optimization'] != '0':
            raise ValueError('parity fixtures require the authenticated GHC O0 producer')
        objects = producer.get('object_inputs', {})
        verify_objects(build, objects)
        record['object_inputs'] = objects
        record['checker_inputs'] = {
            name: producer['shared_inputs'][name] for name in ('Tests.IndependentCheck', 'Tests.IndependentType')
        }
        record['preparer'] = identified(__file__)

        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
                 '-no-user-package-db', '-hide-all-packages', '-O0', *DEMAND_FLAGS]
        for package in PACKAGES:
            flags.extend(['-package', package])
        ghc, cc = producer['ghc']['path'], producer['cc']['path']
        modules = output / 'objects/modules'
        modules.mkdir(parents=True)
        binary_dir = output / 'bin'
        binary_dir.mkdir()

        def project(module):
            path = Path(*module.split('.'))
            relative = Path('tests') / path.with_suffix('.emlf')
            source = (ROOT / relative).read_bytes()
            target = (output / 'sources' / path).with_suffix('.hs')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(host_source(module, source.decode('utf-8')), encoding='utf-8')
            record['sources'][str(relative)] = {
                'original': {'path': str(ROOT / relative), 'sha256': hashlib.sha256(source).hexdigest()},
                'projection': identified(target),
            }
            obj = (modules / path).with_suffix('.o')
            compile_module(module, target, obj)
            return obj

        def compile_module(label, source, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            runner.run('compile-' + label, [ghc, '-c', *flags, '-i', '-i' + str(modules),
                       '-i' + str(build / 'objects'), '-o', target, '-ohi', target.with_suffix('.hi'), source])

        link_inputs = [build / name for name in sorted(objects)
                       if name.endswith('.o') and Path(name) != Path('objects/Main.o')]
        # The producer inventories Haskell objects. Rebuild the two small C
        # transports from the producer-authenticated sources and C compiler.
        transports = []
        for label, relative in [('host', 'host/ghc/cbits/host.c'),
                                ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            target = output / ('objects/' + label + '.o')
            runner.run('compile-' + label, [cc, '-O2', '-std=c11', '-I' + str(ROOT / 'runtime'),
                       '-c', ROOT / relative, '-o', target])
            transports.append(identified(target))
            link_inputs.append(target)
        record['transports'] = transports

        entries = {}
        for name, module, dependencies in [('corpus', 'CorpusMain', CORPUS),
                                           ('check-target', 'CheckTarget', ('CheckTarget',))]:
            private = [project(dependency) for dependency in dependencies]
            entry = output / 'sources' / name / 'Main.hs'
            entry.parent.mkdir(parents=True, exist_ok=True)
            entry.write_text(f'module Main where\nimport MLF.Host.IO (runEntry)\n'
                             f'import qualified {module} as Entry\nmain :: IO ()\nmain = runEntry Entry.main\n')
            entries[name] = identified(entry)
            main = output / 'objects' / name / 'Main.o'
            compile_module(name, entry, main)
            binary = binary_dir / name
            runner.run('link-' + name, [ghc, *flags, '-rtsopts=ignoreAll', main, *private, *link_inputs, '-o', binary])
            record['outputs'][name] = identified(binary)

        record['corpus_entry'] = entries['corpus']
        record['checker_entry'] = entries['check-target']
        authenticate_build(build_receipt, build / 'bin')
        verify_file(producer_identity)
        verify_objects(build, objects)
        for source in record['sources'].values():
            verify_file(source['original'])
            verify_file(source['projection'])
        for identity in [record['preparer'], *entries.values(), *transports, *record['outputs'].values()]:
            verify_file(identity)
        record['complete'] = True
    except BaseException as error:
        record['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.build_receipt, args.output)


if __name__ == '__main__':
    main()
