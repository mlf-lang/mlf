#!/usr/bin/env python3
"""Focused native regex semantics and demand-order controls at Clang O0/O2.

Uses independent public-API literals plus exact public and private-scheduler
failure diagnostics. Private functions are exported only in the test snapshot.
This is a finite correctness gate, not a benchmark or full qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import sys

from test_direct import CommandRunner, sha

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tools/shared/fixtures/regex'
DEMAND_CASES = [
    ('count-both', b'', b'Runtime: subject-first\n'),
    ('count-empty', b'', b'Runtime: regex-required\n'),
    ('find-negative', b'1\n', b''),
    ('find-past-end', b'1\n', b''),
    ('find-both', b'', b'Runtime: subject-first\n'),
    ('replace-both', b'', b'Runtime: subject-first\n'),
    ('regex-before-replacement', b'', b'Runtime: regex-first\n'),
    ('fixed-replacement', b'', b'Runtime: replacement-required\n'),
    ('nullable-replacement', b'', b'Runtime: replacement-required\n'),
    ('span-replacement', b'', b'Runtime: replacement-required\n'),
    ('skip-replacement', b'', b'Runtime: replacement-required\n'),
    ('skip-empty-replacement', b'\n', b''),
    ('skip-short-replacement', b'a\n', b''),
]
SCHEDULING_CASES = [
    ('scan-width-first', b'', b'Runtime: width-first\n'),
    ('scan-credit-first', b'', b'Runtime: credit-first\n'),
    ('scan-shifts-required', b'', b'Runtime: shifts-required\n'),
    ('scan-empty', b'-1\n', b''),
    ('scan-accept', b'1\n', b''),
    ('count-width-first', b'', b'Runtime: width-first\n'),
    ('count-credit-first', b'', b'Runtime: credit-first\n'),
    ('count-shifts-required', b'', b'Runtime: shifts-required\n'),
    ('count-empty', b'73\n', b''),
    ('count-accept', b'74\n', b''),
    ('count-accept-count-first', b'', b'Runtime: count-first\n'),
    ('count-accept-width-required', b'', b'Runtime: width-required\n'),
]
PROGRAM_CASES = {
    'Native': [('public-api', b'native regex fast-path controls passed\n', b'')],
    'NativeDemand': DEMAND_CASES,
    'NativeScheduling': SCHEDULING_CASES,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def tool(name):
    path = shutil.which(str(name))
    require(path is not None, 'missing executable: ' + str(name))
    return Path(path).resolve(strict=True)


def c_closure(source):
    pending, visited = [source], set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        require(path.is_file(), 'missing runtime include: ' + str(path))
        visited.add(path)
        for include in re.findall(r'^\s*#\s*include\s*"([^\"]+)"', path.read_text(), re.M):
            pending.append((path.parent / include).resolve())
    return sorted(visited)


def expose_test_scheduling(source):
    original = 'module Bootstrap.Regex (Regex, compile, find, countMatches, replaceAll) where {'
    replacement = 'module Bootstrap.Regex (Regex, compile, find, countMatches, replaceAll, scanSkip, countSkip) where {'
    require(source.count(original) == 1, 'candidate public module header differs')
    return source.replace(original, replacement, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True)
    parser.add_argument('--clang', default='clang')
    parser.add_argument('--gc-prefix', type=Path, required=True)
    parser.add_argument('--candidate-regex', type=Path,
                        help='Use alternate Regex.hs source only in the isolated test snapshot')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output != ROOT and not ROOT.is_relative_to(output), 'output cannot contain the checkout')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'status': 'running',
              'scope': 'native-regex-semantics-and-demand-controls',
              'full_corpus_qualification': False, 'performance_assertions': False,
              'compiler_source_provenance_authenticated': False,
              'native_toolchain_closure_complete': False,
              'native_provenance_scope': 'selected compiler/Clang, foundation/runtime source closure, static BDWGC and GMP pkg-config flags; system libraries are not fully pinned',
              'commands': [], 'inputs': {}, 'artifacts': {}, 'cases': []}

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        temporary.replace(output / 'receipt.json')

    def integrity():
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            require(sha(path) == digest, 'input or artifact changed: ' + path)

    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        compiler, clang, pkg_config = tool(args.compiler), tool(args.clang), tool('pkg-config')
        gc = args.gc_prefix.resolve(strict=True)
        archive = gc / 'lib/libgc.a'
        require(archive.is_file(), 'BDWGC prefix must contain lib/libgc.a')
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
        sources = [*c_closure((ROOT / 'runtime/mlf_runtime.c').resolve()),
                   *sorted((ROOT / 'libraries/mlf-foundation/Bootstrap').glob('*.hs')),
                   *[FIXTURES / (name + '.emlf') for name in PROGRAM_CASES]]
        record['inputs'] = {str(path): sha(path) for path in
            [compiler, clang, pkg_config, archive, *sorted((gc / 'include').rglob('*.h')),
             *sources, selected_regex, Path(__file__).resolve(), ROOT / 'tools/shared/test_direct.py',
             Path(sys.executable).resolve()]}
        require(record['inputs'][str(selected_regex)] == selected_digest,
                'selected Regex source changed while being read')
        cflags = shlex.split(runner.run('gmp-cflags', [pkg_config, '--cflags', 'gmp'], timeout=30).stdout.decode())
        libraries = shlex.split(runner.run('gmp-libs', [pkg_config, '--libs', 'gmp'], timeout=30).stdout.decode())
        runner.run('clang-version', [clang, '--version'], timeout=30)
        record['gmp_flags'] = {'cflags': cflags, 'libraries': libraries}
        snapshot = output / 'sources'
        for source in sources:
            target = snapshot / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            record['artifacts'][str(target)] = sha(target)
        candidate = snapshot / 'libraries/mlf-foundation/Bootstrap/Regex.hs'
        candidate.write_bytes(selected_bytes)
        require(sha(candidate) == selected_digest, 'selected Regex snapshot differs')
        candidate.write_text(expose_test_scheduling(candidate.read_text()))
        record['artifacts'][str(candidate)] = sha(candidate)
        record['candidate_test_overlay'] = 'export scanSkip and countSkip only'
        programs = {}
        for name in PROGRAM_CASES:
            emitted = runner.run('emit-' + name,
                [compiler, '-i', snapshot / 'libraries/mlf-foundation', '--emit-llvm-gc',
                 snapshot / 'tools/shared/fixtures/regex' / (name + '.emlf')], timeout=180)
            llvm = output / (name + '.ll')
            llvm.write_bytes(emitted.stdout)
            record['artifacts'][str(llvm)] = sha(llvm)
            programs[name] = llvm
        for optimization in ['0', '2']:
            runtime = output / ('runtime-O' + optimization + '.o')
            runner.run('runtime-O' + optimization,
                [clang, '-O' + optimization, '-std=c11', *cflags, '-I' + str(gc / 'include'),
                 '-c', snapshot / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
            record['artifacts'][str(runtime)] = sha(runtime)
            for name, llvm in programs.items():
                binary = output / (name + '-O' + optimization)
                runner.run('link-' + name + '-O' + optimization,
                    [clang, '-O' + optimization, '-Wno-override-module', llvm, runtime,
                     archive, *libraries, '-lm', '-lpthread', '-ldl', '-o', binary], timeout=120)
                record['artifacts'][str(binary)] = sha(binary)
                for label, expected, diagnostic in PROGRAM_CASES[name]:
                    execution = name + '/' + label + '/O' + optimization
                    arguments = [] if name == 'Native' else [label]
                    result = runner.run('run-' + name + '-' + label + '-O' + optimization,
                        [binary, *arguments], expected=expected, status=1 if diagnostic else 0, timeout=60)
                    require(result.stderr == diagnostic, 'native diagnostic differs: ' + execution)
                    record['cases'].append({'case': execution, 'passed': True,
                                            'stdout': expected.decode(), 'stderr': diagnostic.decode()})
        require(len(record['cases']) == 52, 'native completion inventory differs')
        integrity()
        record.update(complete=True, status='passed', native_executions=52,
                      internal_scheduling_executions=24, optimizations=['0', '2'])
    except BaseException as error:
        record.update(complete=False, status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        try:
            integrity()
            record['immutable_inputs_verified_after'] = True
        except BaseException as error:
            record.update(complete=False, status='invalidated', integrity_error=type(error).__name__ + ': ' + str(error))
            raise
        finally:
            save()
    print(str(output / 'receipt.json') + ': passed (52 native executions, O0/O2)')


if __name__ == '__main__':
    main()
