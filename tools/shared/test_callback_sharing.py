#!/usr/bin/env python3
"""Check exact callback code sharing against an authenticated producer.

Compiles only the independent audit Main and C transports, never compiler
modules. This is a structural/semantic unit gate, not full native qualification
or a performance threshold. Producer and fixture inputs are rechecked at exit.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from build import DEMAND_FLAGS, EXHAUSTIVENESS_FLAGS, PACKAGES
from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tools/shared/fixtures/native/CallbackSharingAudit.hs'
# Independent exact inventory, not extracted from the Haskell fixture/output.
CHECKS = [
    'capture alpha equivalence',
    'capture order differs',
    'argument alpha equivalence',
    'argument presence differs',
    'capture count differs',
    'clear mode differs',
    'primitive mode differs',
    'static worker differs',
    'implicit worker capture slots differ',
    'unused capture identity is irrelevant',
    'case binders alpha equivalence',
    'double signed zero distinct',
    'string token boundary exact',
    'global identity same hint differs',
    'primitive identities differ',
    'local let alpha equivalence',
    'bound worker refused',
    'worker argument refused',
    'recursive group refused',
    'ignored pattern field differs',
    'branch order differs',
    'reuses completed callback',
    'one definition per distinct key',
    'small worker retains inline choice',
    'large worker bounds cloning',
    'large numeric worker stays inline',
    'collecting numeric worker stays ordinary',
]
EXPECTED = (''.join('PASS ' + x + '\n' for x in CHECKS)
            + 'Independent callback sharing audit: 27 checks passed\n').encode()


def verify_inventory(stdout):
    if stdout != EXPECTED:
        raise ValueError('callback-sharing completion inventory changed: ' + repr(stdout))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    receipt = args.build_receipt.resolve(strict=True)
    producer_dir, output = receipt.parent, args.output.resolve()
    if output.is_relative_to(producer_dir) or producer_dir.is_relative_to(output):
        parser.error('output must be separate from the immutable producer')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'status': 'running',
              'scope': 'callback-sharing-unit-audit',
              'compiler_modules_rebuilt': False, 'native_execution': False,
              'full_corpus_qualification': False, 'performance_assertions': False,
              'commands': []}
    objects, inputs, artifacts = {}, {}, {}
    authenticated = False

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'receipt.json')

    def integrity():
        if authenticated:
            authenticate_build(receipt, producer_dir / 'bin')
            if sha(receipt) != record['producer_receipt_sha256']:
                raise ValueError('producer receipt changed')
        for name, digest in objects.items():
            path = (producer_dir / name).resolve(strict=True)
            if not path.is_relative_to(producer_dir) or sha(path) != digest:
                raise ValueError('producer object/interface changed: ' + name)
        for path, digest in {**inputs, **artifacts}.items():
            if sha(path) != digest:
                raise ValueError('audit input or artifact changed: ' + path)

    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        producer = authenticate_build(receipt, producer_dir / 'bin')
        objects = producer.get('object_inputs', {})
        if not objects:
            raise ValueError('producer omitted object/interface inventory')
        paths = [Path(__file__), FIXTURE, ROOT / 'tools/shared/test_direct.py',
                 ROOT / 'tools/shared/build.py', ROOT / 'host/ghc/cbits/host.c',
                 ROOT / 'runtime/mlf_process_supervisor.c', *sorted((ROOT / 'runtime').glob('*.h'))]
        inputs = {str(p.resolve()): sha(p) for p in paths}
        record.update(producer_receipt=str(receipt), producer_receipt_sha256=sha(receipt),
                      optimization=producer['optimization'], inputs=inputs, object_inputs=objects)
        authenticated = True
        integrity()
        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db',
                 '-global-package-db', '-no-user-package-db', '-hide-all-packages',
                 '-O' + producer['optimization'], *DEMAND_FLAGS]
        for package in PACKAGES:
            flags += ['-package', package]
        ghc = producer['ghc']['path']
        obj, hi = output / 'CallbackSharingAudit.o', output / 'CallbackSharingAudit.hi'
        runner.run('compile-fixture', [ghc, '-c', *flags, *EXHAUSTIVENESS_FLAGS,
                   '-i', '-i' + str(producer_dir / 'objects'), '-o', obj, '-ohi', hi, FIXTURE], timeout=120)
        link_objects = [producer_dir / name for name in sorted(objects)
                        if name.endswith('.o') and name != 'objects/Main.o']
        if not link_objects:
            raise ValueError('producer has no authenticated linkable objects')
        transports = []
        for label, source in [('host', ROOT / 'host/ghc/cbits/host.c'),
                              ('supervisor', ROOT / 'runtime/mlf_process_supervisor.c')]:
            target = output / (label + '.o')
            runner.run('compile-' + label, [producer['cc']['path'], '-O2', '-std=c11',
                       '-I' + str(ROOT / 'runtime'), '-c', source, '-o', target], timeout=120)
            transports.append(target)
        executable = output / 'callback-sharings-audit'
        runner.run('link-fixture', [ghc, *flags, '-rtsopts=ignoreAll', obj,
                   *link_objects, *transports, '-o', executable], timeout=120)
        artifacts = {str(p): sha(p) for p in [obj, hi, executable, *transports]}
        result = runner.run('audit', [executable], expected=EXPECTED, timeout=120)
        verify_inventory(result.stdout)
        record.update(checks=CHECKS, artifacts=artifacts, complete=True, status='passed')
    except BaseException as error:
        record.update(complete=False, status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        try:
            integrity()
            record['immutable_inputs_verified_after'] = True
        except BaseException as error:
            record.update(complete=False, status='invalidated', integrity_error=type(error).__name__ + ': ' + str(error))
            save()
            raise
        save()
    print(str(output / 'receipt.json') + ': passed')


if __name__ == '__main__':
    main()
