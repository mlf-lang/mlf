#!/usr/bin/env python3
"""Independently compare checker-owned inventories with full RHS rechecking."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from build import DEMAND_FLAGS, EXHAUSTIVENESS_FLAGS, PACKAGES
from test_direct import CommandRunner, sha

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tools/shared/fixtures/CheckedBindings.hs'
CHECKS = [
    'empty', 'one-let', 'ordered-lets', 'rhs-local-excluded', 'lambda-rhs',
    'recursive', 'mutual-recursive', 'let-after-recursive', 'empty-recursive',
    'import-parameter', 'two-import-parameters', 'polymorphic-rhs',
    'quantified-field-fresh-negative-id', 'quantified-field-and-negative-term-id',
    'valid-nonfragment', 'valid-lambda-nonfragment', 'lambda-after-declaration',
    'type-abstraction-nonfragment', 'unbound-rhs', 'late-unbound-rhs',
    'duplicate-let-priority', 'duplicate-import', 'open-import-type',
    'duplicate-recursive-priority', 'recursive-shadow-priority',
    'bad-recursive-signature', 'unbound-recursive-rhs', 'unknown-constructor',
    'bad-unit-arguments', 'nested-data', 'duplicate-datatype', 'bad-tail-after-let',
    'checked-link-and-metadata-controls',
]
EXPECTED = (''.join('PASS ' + name + '\n' for name in CHECKS) +
            'Checked binding inventory audit: 33 checks passed\n').encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', type=Path, required=True)
    parser.add_argument('--cc', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--crate-interface', type=Path)
    parser.add_argument('--crate-object', type=Path)
    args = parser.parse_args()
    if bool(args.crate_interface) != bool(args.crate_object):
        parser.error('--crate-interface and --crate-object must be supplied together')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    objects = output / 'objects'
    objects.mkdir()
    manifest = ROOT / 'shared-sources.json'
    roots = [ROOT / root for root in json.loads(manifest.read_text())['source_roots']]
    ghc, cc = args.ghc.resolve(strict=True), args.cc.resolve(strict=True)
    sources = {FIXTURE, Path(__file__), manifest, ROOT / 'tools/shared/build.py',
               ROOT / 'tools/shared/test_direct.py', ROOT / 'host/ghc/cbits/host.c',
               ROOT / 'runtime/mlf_process_supervisor.c', *sorted((ROOT / 'runtime').glob('*.h'))}
    pending, visited = [FIXTURE], set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        sources.add(path)
        for name in re.findall(r'\bimport\s+(?:qualified\s+)?([A-Z][A-Za-z0-9_.]*)', path.read_text()):
            relative = Path(*name.split('.')).with_suffix('.hs')
            candidates = [root / relative for root in roots if (root / relative).is_file()]
            if candidates:
                pending.append(candidates[0])
    inputs = {str(path): sha(path) for path in sorted(sources)}
    if args.crate_interface:
        inputs.update({str(path.resolve()): sha(path) for path in [args.crate_interface, args.crate_object]})
    inputs.update({str(ghc): sha(ghc), str(cc): sha(cc)})
    record = {'complete': False, 'status': 'running', 'inputs': inputs, 'checks': CHECKS,
              'scope': 'checker binding inventory differential controls',
              'performance_assertions': False, 'commands': []}

    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        transports = []
        for label, source in [('host', ROOT / 'host/ghc/cbits/host.c'),
                              ('supervisor', ROOT / 'runtime/mlf_process_supervisor.c')]:
            target = output / (label + '.o')
            runner.run('compile-' + label, [cc, '-O2', '-std=c11', '-I' + str(ROOT / 'runtime'),
                       '-c', source, '-o', target], timeout=120)
            transports.append(target)
        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db',
                 '-global-package-db', '-no-user-package-db', '-hide-all-packages',
                 '-O2', *DEMAND_FLAGS, *EXHAUSTIVENESS_FLAGS, '-Wno-star-is-type',
                 '-Wno-overlapping-patterns', '-Wno-deprecations', '-i',
                 *['-i' + str(root) for root in roots],
                 '-odir', objects, '-hidir', objects, '-rtsopts=ignoreAll']
        for package in PACKAGES:
            flags += ['-package', package]
        executable = output / 'checked-bindings-audit'
        runner.run('compile-audit', [ghc, '--make', '-j1', *flags, FIXTURE,
                   *transports, '-o', executable], timeout=600)
        runner.run('audit', [executable], expected=EXPECTED, timeout=120)
        if args.crate_interface:
            result = runner.run('real-crate-audit', [executable, '--crate', args.crate_interface.resolve(),
                                args.crate_object.resolve()], timeout=180)
            lines = result.stdout.decode().splitlines()
            match = re.fullmatch(r'Checked real crate binding inventory audit: ([1-9][0-9]*) fragments passed',
                                 lines[-1] if lines else '')
            if not match or lines[:-1] != ['PASS crate-fragment-' + str(i) for i in range(int(match[1]))]:
                raise ValueError('real crate audit completion inventory changed')
            record['real_crate_fragments'] = int(match[1])
        record.update(complete=True, status='passed', executable_sha256=sha(executable))
    except BaseException as error:
        record.update(complete=False, status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        changed = [path for path, digest in inputs.items() if sha(path) != digest]
        record['immutable_inputs_verified_after'] = not changed
        if changed:
            record.update(complete=False, status='invalidated', changed_inputs=changed)
        save()
        if changed:
            raise ValueError('audit inputs changed during execution: ' + ', '.join(changed))
    print(str(output / 'receipt.json') + ': passed')


if __name__ == '__main__':
    main()
