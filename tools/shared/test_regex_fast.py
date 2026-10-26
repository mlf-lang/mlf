#!/usr/bin/env python3
"""Opt-in finite semantic audit of the reusable regex engine's fast paths.

Builds the current library and a pinned pre-optimization reference from fresh
source snapshots. It compares every public operation over a fixed finite corpus
and checks independent literal oracles and fast-path admission. This is a GHC
host semantic test, not native compiler qualification or a performance result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from test_direct import CommandRunner, sha

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tools/shared/fixtures/regex'
REFERENCE_SHA256 = 'a3956f2647d3d4ddc6bf7e9f147b06c14e84ef7254a948d1551e9a445710a5e8'
REFERENCE_SOURCE_SHA256 = 'e3087cbcfd6873c2fcb00e1541d91122dc16be7796f61fcf1d38e39fe3528055'
REFERENCE_REVISION = '2957dd08321c38dbf94a75cb275a5f48e897f58e'
EXPECTED = (
    b'PASS plan-admission 20\n'
    b'PASS literal-oracles 60\n'
    b'PASS invalid-patterns 18\n'
    b'PASS demand-oracles 15\n'
    b'PASS internal-scheduling 12\n'
    b'PASS differential-patterns 233\n'
    b'PASS differential-subjects 356\n'
    b'PASS differential-pairs 82948\n'
    b'PASS adversarial-pairs 18\n'
    b'Regex fast-path semantic audit passed\n'
)


def verify_output(value):
    if value != EXPECTED:
        raise ValueError('regex audit completion inventory differs: ' + repr(value))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def tool(name):
    path = shutil.which(name)
    require(path is not None, 'missing tool: ' + name)
    return Path(path).resolve(strict=True)


def expose_test_constructors(source):
    original = 'module Bootstrap.Regex (Regex, compile, find, countMatches, replaceAll) where {'
    replacement = 'module Bootstrap.Regex (Regex(..), SearchPlan(..), compile, find, countMatches, replaceAll, scanSkip, countSkip) where {'
    require(source.count(original) == 1, 'candidate public module header differs')
    return source.replace(original, replacement, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', default='ghc')
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--candidate-regex', type=Path,
                        help='Use alternate Regex.hs source only in the isolated test snapshot')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output != ROOT and not ROOT.is_relative_to(output), 'output cannot contain the checkout')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'status': 'running',
              'scope': 'finite-regex-fast-path-semantic-audit', 'producer_host': 'GHC',
              'native_execution': False, 'performance_assertions': False,
              'full_corpus_qualification': False, 'held_objects_linked': False,
              'reference_revision': REFERENCE_REVISION,
              'reference_source_sha256': REFERENCE_SOURCE_SHA256,
              'commands': [], 'inputs': {}, 'snapshot_inputs': {}}

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        temporary.replace(output / 'receipt.json')

    def integrity():
        for path, digest in {**record['inputs'], **record['snapshot_inputs']}.items():
            require(sha(path) == digest, 'audit source/tool/snapshot changed: ' + path)

    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        ghc, cc = tool(args.ghc), tool(args.cc)
        reference = FIXTURES / 'RegexReference.hs'
        require(sha(reference) == REFERENCE_SHA256, 'frozen regex reference changed')
        import hashlib
        original = reference.read_bytes().replace(b'module RegexReference (', b'module Bootstrap.Regex (', 1)
        require(hashlib.sha256(original).hexdigest() == REFERENCE_SOURCE_SHA256,
                'reference differs from pinned source beyond module identity')
        production_regex = ROOT / 'libraries/mlf-foundation/Bootstrap/Regex.hs'
        selected_regex = (args.candidate_regex or production_regex).resolve(strict=True)
        require(selected_regex.is_file(), 'candidate Regex source must be a file')
        selected_bytes = selected_regex.read_bytes()
        selected_digest = hashlib.sha256(selected_bytes).hexdigest()
        record['candidate_regex'] = {
            'path': str(selected_regex), 'sha256': selected_digest,
            'override_requested': args.candidate_regex is not None,
            'production_path': str(production_regex.resolve()),
            'production_source_used': selected_regex == production_regex.resolve(),
        }
        source_paths = [*sorted((ROOT / 'libraries/mlf-foundation/Bootstrap').glob('*.hs')),
                        *sorted((ROOT / 'host/ghc/MLF').rglob('*.hs')),
                        ROOT / 'host/ghc/cbits/host.c', ROOT / 'runtime/mlf_process_supervisor.c',
                        *sorted((ROOT / 'runtime').glob('*.h'))]
        record['inputs'] = {str(path.resolve()): sha(path) for path in
            [*source_paths, selected_regex, reference, FIXTURES / 'Main.hs', Path(__file__).resolve(),
             ROOT / 'tools/shared/test_direct.py', ghc, cc, Path(sys.executable).resolve()]}
        require(record['inputs'][str(selected_regex)] == selected_digest,
                'selected Regex source changed while being read')
        snapshots = output / 'sources'
        for source in source_paths:
            target = snapshots / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        candidate = snapshots / 'libraries/mlf-foundation/Bootstrap/Regex.hs'
        candidate.write_bytes(selected_bytes)
        require(sha(candidate) == selected_digest, 'selected Regex snapshot differs')
        # Expose constructors and scheduling entry points only in the isolated
        # test copy; matcher, admission, and production exports stay untouched.
        candidate.write_text(expose_test_constructors(candidate.read_text()))
        for name in ['Main.hs', 'RegexReference.hs']:
            (snapshots / name).write_bytes((FIXTURES / name).read_bytes())
        record['snapshot_inputs'] = {str(path): sha(path) for path in snapshots.rglob('*') if path.is_file()}
        record['candidate_test_overlay'] = 'export Regex(..), SearchPlan(..), scanSkip and countSkip only'
        version = runner.run('ghc-version', [ghc, '--numeric-version'], timeout=30)
        require(version.stdout == b'9.14.1\n', 'qualified GHC 9.14.1 required')
        runner.run('cc-version', [cc, '--version'], timeout=30)
        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
                 '-no-user-package-db', '-hide-all-packages', '-O2', '-fpedantic-bottoms',
                 '-fno-state-hack', '-Wno-star-is-type', '-Wno-overlapping-patterns',
                 '-Wno-deprecations', '-Werror=incomplete-patterns', '-Werror=incomplete-uni-patterns']
        for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
            flags += ['-package', package]
        record['flags'] = flags
        objects = output / 'objects'
        objects.mkdir()
        transports = []
        for label, relative in [('host', 'host/ghc/cbits/host.c'),
                                ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            target = output / (label + '.o')
            runner.run('compile-' + label, [cc, '-O2', '-std=c11', '-I' + str(snapshots / 'runtime'),
                       '-c', snapshots / relative, '-o', target], timeout=60)
            transports.append(target)
        executable = output / 'regex-fast-audit'
        runner.run('compile-audit', [ghc, '--make', '-j1', *flags,
                   '-i', '-i' + str(snapshots), '-i' + str(snapshots / 'host/ghc'),
                   '-i' + str(snapshots / 'libraries/mlf-foundation'),
                   '-odir', objects, '-hidir', objects, '-rtsopts=ignoreAll',
                   snapshots / 'Main.hs', *transports, '-o', executable], timeout=180,
                   overrides={'GHC_ENVIRONMENT': '-'})
        result = runner.run('semantic-audit', [executable], expected=EXPECTED, timeout=180)
        verify_output(result.stdout)
        record['artifacts'] = {str(path): sha(path) for path in [executable, *transports]}
        record.update(status='passed', complete=True, admission_checks=20, literal_oracles=60,
                      invalid_patterns=18, demand_oracles=15, demand_evaluations=30,
                      internal_scheduling_oracles=12,
                      differential_patterns=233, differential_subjects=356,
                      differential_pairs=82948, adversarial_pairs=18)
    except BaseException as error:
        record.update(status='failed', complete=False, error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        try:
            integrity()
            record['immutable_inputs_verified_after'] = True
        except BaseException as error:
            record.update(status='invalidated', complete=False,
                          integrity_error=type(error).__name__ + ': ' + str(error))
            raise
        finally:
            save()
    print(str(output / 'receipt.json') + ': passed')


if __name__ == '__main__':
    main()
