#!/usr/bin/env python3
"""Build and run the exact closed-expansion graft audit from current sources.

This focused solver gate compares the candidate against both the unchanged
component instantiation and raw graph unification. It is not release/native
self-host qualification or a performance measurement.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from build import DEMAND_FLAGS, EXHAUSTIVENESS_FLAGS, PACKAGES
from test_direct import CommandRunner, sha

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tools/shared/fixtures/native/FreshBottomGraftAudit.hs'
CASES = [
    'shared-quantifier', 'nested-flexible-quantifier', 'protected-nested-quantifier',
    'rigid-source-root', 'higher-kind-application', 'higher-kind-bottom',
    'explicit-star-source-bottom', 'explicit-star-target-bottom',
    'external-frontier', 'rigid-target', 'kind-mismatch',
    'incoming-target-structural-reference', 'green-target-under-type-binder',
    'rigid-target-intermediary',
]
CHECKS = CASES + [prefix + '-' + case for prefix in ['sparse', 'huge', 'negative']
                 for case in CASES[:8]] + [
    'source-and-target-aliases', 'fresh-root-binder-mismatch',
    'fresh-generalization-node', 'fresh-external-binder', 'fresh-external-edge',
    'fresh-missing-edge', 'fresh-invalid-internal-binder',
    'existing-target-binding-child', 'malformed-disconnected-index',
    'frontier-orange-original', 'frontier-two-originals',
    'frontier-root-flexible-bottom',
    'frontier-root-rigid-skolem', 'frontier-root-existing-target-parent',
    'frontier-root-explicit-star-source', 'frontier-root-explicit-star-target',
    'frontier-explicit-star-source',
    'frontier-root-kind-mismatch', 'frontier-original-descendant-scope',
    'frontier-root-younger-original', 'frontier-root-already-target',
    'frontier-identity-rigid-skolem', 'frontier-identity-existing-children',
    'frontier-identity-explicit-star', 'frontier-identity-existing-aliases',
    'frontier-existing-alias-chain',
    'frontier-original-under-rigid-type',
    'congruence-shared-local', 'congruence-flexible-variable-instance',
    'congruence-many-fresh-one-flexible-original',
    'congruence-many-fresh-one-orange-original',
    'congruence-frontier-descendant', 'congruence-sharing-conflict',
    'congruence-binder-capture', 'congruence-flag-change',
    'congruence-protected-flexible', 'congruence-rigid-variable-instantiation',
    'congruence-old-cycle-equations',
    'congruence-frontier-capture', 'congruence-target-alias-chain',
    'congruence-rigid-variable-rejection-diagnostic',
    'congruence-long-shared-arrow-spine', 'congruence-long-spine-aliases',
    'congruence-higher-kind-instance', 'congruence-higher-kind-instance-mismatch',
    'congruence-malformed-old-kind-cycle',
]
FRAGMENT_CASES = [
    'valid', 'missing-root', 'missing-scope', 'missing-structural-node',
    'missing-binder', 'structural-cycle', 'binding-cycle', 'invalid-type-binder',
    'extra-binding-root', 'generalization-child', 'invalid-arrow-kind',
    'rigid-root', 'protected-variable', 'higher-kind-application',
    'unused-direct-gen-node',
]
CHECKS += ['fragment-' + prefix + '/' + case
           for prefix in ['ordinary', 'sparse', 'huge', 'negative']
           for case in FRAGMENT_CASES]
CHECKS += ['fragment-duplicate-node', 'fragment-anchor-collision']
EXPECTED = (''.join('PASS ' + name + '\n' for name in CHECKS) +
            'Fresh bottom graft audit: 146 checks passed\n').encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', required=True, type=Path)
    parser.add_argument('--cc', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    objects = output / 'objects'
    objects.mkdir()
    manifest = ROOT / 'shared-sources.json'
    roots = [ROOT / name for name in json.loads(manifest.read_text())['source_roots']]
    ghc, cc = args.ghc.resolve(strict=True), args.cc.resolve(strict=True)
    sources = {FIXTURE, Path(__file__), manifest, ROOT / 'tools/shared/build.py',
               ROOT / 'tools/shared/test_direct.py', ROOT / 'host/ghc/cbits/host.c',
               ROOT / 'runtime/mlf_process_supervisor.c', *sorted((ROOT / 'runtime').glob('*.h'))}
    # Freeze the actual transitive local imports, allowing unrelated library
    # work to proceed. Every object is compiled afresh from this source closure.
    pending = [FIXTURE]
    visited = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        sources.add(path)
        for module in re.findall(r'\bimport\s+(?:qualified\s+)?([A-Z][A-Za-z0-9_.]*)', path.read_text()):
            relative = Path(*module.split('.')).with_suffix('.hs')
            candidates = [root / relative for root in roots if (root / relative).is_file()]
            if candidates:
                pending.append(candidates[0])
    inputs = {str(path): sha(path) for path in sorted(sources)}
    inputs.update({str(ghc): sha(ghc), str(cc): sha(cc)})
    record = {'format': 1, 'complete': False, 'status': 'running',
              'scope': 'fresh-bottom-graft-exact-solver-audit',
              'full_corpus_qualification': False, 'performance_assertions': False,
              'inputs': inputs, 'checks': CHECKS, 'commands': []}

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
        executable = output / 'fresh-bottom-graft-audit'
        runner.run('compile-audit', [ghc, '--make', '-j1', *flags, FIXTURE,
                   *transports, '-o', executable], timeout=600)
        result = runner.run('audit', [executable], expected=EXPECTED, timeout=120)
        if result.stdout != EXPECTED:
            raise ValueError('exact audit completion inventory changed')
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
            raise ValueError('audit input changed during execution: ' + ', '.join(changed))
    print(str(output / 'receipt.json') + ': passed')


if __name__ == '__main__':
    main()
