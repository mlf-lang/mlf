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

# These sources also run in the native package. A source change requires
# reviewing its host projection before updating the exact input digest.
CORPUS = {
    'Tests.Helpers': ('tests/Tests/Helpers.emlf', '49091120fa91fc998e78cf5529fa5185643d883f11f22d2db19a2b5e8e6328fd'),
    'Tests.Map': ('tests/Tests/Map.emlf', '104b5066749811d3c9cc106fc40e83cd406c838fbc211e42da62237f626a8d25'),
    'Tests.Set': ('tests/Tests/Set.emlf', '07a3b77d3ade77e08aa7cd72e03e5a7023c3d7b3c976bbf652e35745a6989920'),
    'Tests.Figure12': ('tests/Tests/Figure12.emlf', 'dd7f8b94c22d9cc1634867d75317ff177282a6562f617b28c4391577c65857a1'),
    'Tests.Oracle': ('tests/Tests/Oracle.emlf', 'eab513eeba291a299ad8ab645e2f4c2bb563e5bc6d01c716c07bd981d0d32722'),
    'Tests.Corpus': ('tests/Tests/Corpus.emlf', '3d2a4c92455bde99f9f9654d09992e8cb451bbb37cd6dce4ad56a5a5e5680427'),
    'CorpusMain': ('tests/CorpusMain.emlf', 'd353b1db226ea57079ff4486dcc0fdbb07650bb4466cd95580574136078eeb12'),
}
CHECKER = ('tests/CheckTarget.emlf', '90efc9b11d3864ecc8185e687474766c6dfc6df31a8b6fb3425bb56fc78e6861')

PRAGMA = ('{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, '
          'FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings, KindSignatures #-}\n')
# Consume comments and strings whole before matching legacy boolean literals
# and type annotations. In particular, keep embedded guest programs intact.
TOKENS = re.compile(
    r'--[^\n]*|"(?:[^"\\]|\\.)*"|\b(?:true|false)\b|'
    r'(?:^[ ]*|(?<=[{;] ))[a-z][A-Za-z0-9_]* +:(?= +)',
    re.MULTILINE,
)


def host_token(match):
    token = match[0]
    if token in ('true', 'false'):
        return token.capitalize()
    if token.endswith(':') and not token.startswith(('--', '"')):
        return token + ':'
    return token


def host_source(module, source):
    source = re.sub(r'^import Prelude hiding .*\n', '', source, flags=re.MULTILINE)
    source = source.replace('import MLF.Primitive (Monad, return, bind)\n', '')
    hidden = {'Tests.Helpers': ' hiding (Eq, fail, fmap)', 'Tests.Oracle': ' hiding (fail)'}
    imports = 'import MLF.Primitive' + hidden.get(module, '') + '\n'
    if module == 'Tests.Helpers':
        imports += 'import Data.Kind (Type)\n'
        source = source.replace('(m : * -> *)', '(m :: Type -> Type)')
    if module == 'Main':
        imports += 'import MLF.Host.IO (runEntry)\n'
        source = source.replace('\nmain = do\n', '\nmain :: IO ()\nmain = runEntry entry\n\nentry = do\n')
    declaration = f'module {module} where\n'
    source = source.replace(declaration, declaration + imports, 1)
    source = TOKENS.sub(host_token, source)
    if module == 'Tests.Figure12':
        source = source.replace('freeNames e = let rec {', 'freeNames e = let {')
    return PRAGMA + source


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

        def project(module, identity, target):
            relative, digest = identity
            path = ROOT / relative
            source = path.read_bytes()
            if hashlib.sha256(source).hexdigest() != digest:
                raise ValueError('reviewed parity fixture source changed: ' + relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(host_source(module, source.decode('utf-8')).encode('utf-8'))
            record['sources'][relative] = {'original': {'path': str(path), 'sha256': digest},
                                           'projection': identified(target)}

        def compile_module(label, source, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            runner.run('compile-' + label, [ghc, '-c', *flags, '-i', '-i' + str(modules),
                       '-i' + str(build / 'objects'), '-o', target, '-ohi', target.with_suffix('.hi'), source])

        corpus_sources = []
        for module, identity in CORPUS.items():
            relative = Path(*module.split('.'))
            source = (output / 'sources/corpus' / relative).with_suffix('.hs')
            target = (modules / relative).with_suffix('.o')
            project(module, identity, source)
            corpus_sources.append((module, source, target))
        corpus_entry = output / 'sources/corpus/Main.hs'
        corpus_entry.write_bytes(b'module Main where\nimport MLF.Host.IO (runEntry)\n'
                                 b'import qualified CorpusMain as Entry\nmain :: IO ()\nmain = runEntry Entry.main\n')
        record['corpus_entry'] = identified(corpus_entry)
        checker_entry = output / 'sources/check-target/Main.hs'
        project('Main', CHECKER, checker_entry)

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

        for module, source, target in corpus_sources:
            compile_module(module, source, target)
        for name, entry, private in [('corpus', corpus_entry, [obj for _, _, obj in corpus_sources]),
                                     ('check-target', checker_entry, [])]:
            main = output / 'objects' / name / 'Main.o'
            compile_module(name, entry, main)
            binary = binary_dir / name
            runner.run('link-' + name, [ghc, *flags, '-rtsopts=ignoreAll', main, *private, *link_inputs, '-o', binary])
            record['outputs'][name] = identified(binary)

        authenticate_build(build_receipt, build / 'bin')
        verify_file(producer_identity)
        verify_objects(build, objects)
        for source in record['sources'].values():
            verify_file(source['original'])
            verify_file(source['projection'])
        for identity in [record['preparer'], record['corpus_entry'], *transports, *record['outputs'].values()]:
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
