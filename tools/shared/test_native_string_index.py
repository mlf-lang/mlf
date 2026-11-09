#!/usr/bin/env python3
"""Bounded native controls for checked ASCII StringCodeAt/Length lowering.

Compiles fresh no-Prelude source fixtures with the selected compiler, then runs
their emitted LLVM at Clang O0 and O2 against independent literal outputs and
diagnostics. This is a focused native gate, not a benchmark or full qualification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import shutil
import sys

from test_direct import CommandRunner, sha

ROOT = Path(__file__).resolve().parents[2]
BOUNDS = b'Runtime: string index out of bounds\n'
# Each row is (source, require_used_index_fast_path, executions).
# An execution is (label, argv, stdout, stderr); error cases exit exactly one.
FIXTURES = {
    'dynamic-index': (
        'main = ioBind (getArg 0) (\\text -> ioBind (getArg 1) (\\position -> '
        'printInt (stringCodeAt text (readInt position))))\n', True, [
            ('ascii-first', ['AZz', '0'], b'65\n', b''),
            ('ascii-last', ['AZz', '2'], b'122\n', b''),
            ('unicode-bmp', ['Aé😀Z', '1'], b'233\n', b''),
            ('unicode-astral', ['Aé😀Z', '2'], b'128512\n', b''),
            ('unicode-after-astral', ['Aé😀Z', '3'], b'90\n', b''),
            ('sparse-astral', ['01234567890123456789😀Z', '20'], b'128512\n', b''),
            ('sparse-after-astral', ['01234567890123456789😀Z', '21'], b'90\n', b''),
            ('negative', ['abc', '-1'], b'', BOUNDS),
            ('wrapped-positive', ['abc', '18446744073709551616'], b'97\n', b''),
            ('wrapped-negative', ['abc', '-18446744073709551616'], b'97\n', b''),
            ('signed-maximum', ['abc', '9223372036854775807'], b'', BOUNDS),
            ('signed-minimum', ['abc', '-9223372036854775808'], b'', BOUNDS),
            ('empty', ['', '0'], b'', BOUNDS),
            ('past-ascii-end', ['abc', '3'], b'', BOUNDS),
            ('scalar-not-byte-bound', ['Aé😀Z', '4'], b'', BOUNDS),
        ]),
    'cached-repeat': (
        'main = ioBind (getArg 0) (\\text -> '
        'ioBind (printInt (stringCodeAt text 0)) (\\a -> '
        'ioBind (printInt (stringCodeAt text 1)) (\\b -> '
        'ioBind (printInt (stringCodeAt text 2)) (\\c -> '
        'ioBind (printInt (stringCodeAt text 0)) (\\d -> '
        'printInt (stringLength text))))))\n', True, [
            ('ascii-cached', ['AZz'], b'65\n90\n122\n65\n3\n', b''),
            ('unicode-cached', ['Aé😀'], b'65\n233\n128512\n65\n3\n', b''),
            ('sparse-cached', ['01234567890123456789😀Z'], b'48\n49\n50\n48\n22\n', b''),
        ]),
    'cached-dynamic-index': (
        'main = ioBind (getArg 0) (\\text -> ioBind (getArg 1) (\\position -> '
        'ioBind (printInt (stringLength text)) (\\a -> '
        'printInt (stringCodeAt text (readInt position)))))\n', True, [
            ('cached-negative', ['abc', '-1'], b'3\n', BOUNDS),
            ('cached-wrapped-positive', ['abc', '18446744073709551616'], b'3\n97\n', b''),
            ('cached-wrapped-negative', ['abc', '-18446744073709551616'], b'3\n97\n', b''),
            ('cached-signed-maximum', ['abc', '9223372036854775807'], b'3\n', BOUNDS),
            ('cached-signed-minimum', ['abc', '-9223372036854775808'], b'3\n', BOUNDS),
            ('cached-past-end', ['abc', '3'], b'3\n', BOUNDS),
        ]),
    'constructed-nul': (
        'main = ioBind (getArg 0) (\\prefix -> '
        'let text = concatString prefix (stringFromCode 0) in '
        'ioBind (printInt (stringLength text)) (\\a -> '
        'ioBind (printInt (stringCodeAt text 0)) (\\b -> '
        'printInt (stringCodeAt text 1))))\n', True, [
            ('nul-is-scalar', ['A'], b'2\n65\n0\n', b''),
        ]),
    'unused-index': (
        'main = ioBind (getArg 0) (\\text -> '
        'let invalid = stringCodeAt text (-1) in printInt 7)\n', False, [
            ('unused-invalid-remains-lazy', ['abc'], b'7\n', b''),
        ]),
    'untaken-index': (
        'main = ioBind (getArg 0) (\\text -> if eqString text "safe" '
        'then printInt 7 else printInt (stringCodeAt text (-1)))\n', True, [
            ('untaken-invalid-remains-lazy', ['safe'], b'7\n', b''),
            ('taken-invalid-still-fails', ['other'], b'', BOUNDS),
        ]),
    'string-before-index': (
        'main = printInt (stringCodeAt (panic "string-first") (panic "index-second"))\n', False, [
            ('strict-string-first', [], b'', b'Runtime: string-first\n'),
        ]),
    'cached-index-failure': (
        'main = ioBind (getArg 0) (\\text -> '
        'ioBind (printInt (stringLength text)) (\\a -> '
        'printInt (stringCodeAt text (panic "index-second"))))\n', False, [
            ('strict-index-before-fast-load', ['abc'], b'3\n', b'Runtime: index-second\n'),
        ]),
    'io-before-index': (
        'main = ioBind (putStrLn "before") (\\a -> '
        'printInt (stringCodeAt "x" (-1)))\n', True, [
            ('effect-before-index-error', [], b'before\n', BOUNDS),
        ]),
    'prior-action-failure': (
        'main = ioBind (putStrLn "before") (\\a -> '
        'ioBind (panic "earlier-action") (\\b -> '
        'printInt (stringCodeAt (panic "late-string") (-1))))\n', False, [
            ('earlier-action-wins', [], b'before\n', b'Runtime: earlier-action\n'),
        ]),
    'unused-length': (
        'main = let invalid = stringLength (panic "unused-length") in printInt 7\n', False, [
            ('unused-length-remains-lazy', [], b'7\n', b''),
        ]),
    'failed-length': (
        'main = printInt (stringLength (panic "length-first"))\n', False, [
            ('length-demands-string', [], b'', b'Runtime: length-first\n'),
        ]),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def resolve_tool(name):
    selected = shutil.which(str(name))
    require(selected is not None, 'missing executable: ' + str(name))
    return Path(selected).resolve(strict=True)


def local_c_closure(source):
    pending, visited = [source], set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        require(path.is_file(), 'missing runtime include: ' + str(path))
        visited.add(path)
        for include in re.findall(r'^\s*#\s*include\s*"([^"]+)"', path.read_text(), re.M):
            pending.append((path.parent / include).resolve())
    return sorted(visited)


def verify_fast_path(llvm):
    checks = {
        'ascii-cache-sentinel-comparison': r'icmp eq ptr [^,\n]+, @mlf_ascii_string_indices',
        'tagged-integer-guard': r'and i64 [^,\n]+, 1\b',
        'nonnegative-index-guard': r'icmp sge i64 [^,\n]+, 0\b',
        'unsigned-bounds-guard': r'icmp ult i64 ',
        'checked-fallback-call': r'call ptr @mlf_string_code_at\(ptr ',
        'ascii-byte-load': r'load i8, ptr ',
    }
    for label, expression in checks.items():
        require(re.search(expression, llvm) is not None, 'missing used fast-path operation: ' + label)
    return list(checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True)
    parser.add_argument('--clang', default='clang')
    parser.add_argument('--gc-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output != ROOT and not ROOT.is_relative_to(output), 'output cannot contain the checkout')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'status': 'running',
              'scope': 'native-string-index-lowering-controls',
              'full_corpus_qualification': False, 'performance_assertions': False,
              'compiler_source_provenance_authenticated': False,
              'native_toolchain_closure_complete': False,
              'native_provenance_scope': 'selected compiler/Clang, source/header closure, static BDWGC and GMP pkg-config flags; system libraries are not fully pinned',
              'commands': [], 'inputs': {}, 'artifacts': {}, 'cases': [], 'shape_checks': {}}

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        temporary.replace(output / 'receipt.json')

    def integrity():
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            require(sha(path) == digest, 'input or output artifact changed: ' + path)

    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        compiler, clang, pkg_config = resolve_tool(args.compiler), resolve_tool(args.clang), resolve_tool('pkg-config')
        gc = args.gc_prefix.resolve(strict=True)
        gc_archive = gc / 'lib/libgc.a'
        require(gc_archive.is_file(), 'BDWGC prefix must contain lib/libgc.a')
        source_paths = local_c_closure((ROOT / 'runtime/mlf_runtime.c').resolve())
        inputs = [compiler, clang, pkg_config, gc_archive, *sorted((gc / 'include').rglob('*.h')),
                  *source_paths, Path(__file__).resolve(), ROOT / 'tools/shared/test_direct.py',
                  Path(sys.executable).resolve()]
        record['inputs'] = {str(path): sha(path) for path in inputs}
        cflags = shlex.split(runner.run('gmp-cflags', [pkg_config, '--cflags', 'gmp'], timeout=30).stdout.decode())
        libraries = shlex.split(runner.run('gmp-libs', [pkg_config, '--libs', 'gmp'], timeout=30).stdout.decode())
        runner.run('clang-version', [clang, '--version'], timeout=30)
        record['gmp_flags'] = {'cflags': cflags, 'libraries': libraries}
        source_dir = output / 'sources'
        source_dir.mkdir()
        for path in source_paths:
            target = source_dir / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            record['artifacts'][str(target)] = sha(target)
        programs = {}
        for label, (source, required_shape, executions) in FIXTURES.items():
            fixture = source_dir / (label + '.emlf')
            fixture.write_text(source)
            record['artifacts'][str(fixture)] = sha(fixture)
            emitted = runner.run('emit-' + label,
                                 [compiler, '--no-prelude', '--emit-llvm-gc', fixture], timeout=120)
            llvm = output / (label + '.ll')
            llvm.write_bytes(emitted.stdout)
            record['artifacts'][str(llvm)] = sha(llvm)
            if required_shape:
                record['shape_checks'][label] = verify_fast_path(emitted.stdout.decode())
            programs[label] = llvm
        # Require a real helper call in the used-length fixture, rather than
        # accepting the helper's unconditional module-level declaration alone.
        require('call ptr @mlf_string_length(ptr ' in programs['cached-repeat'].read_text(),
                'used stringLength did not take the checked direct helper')
        record['shape_checks']['cached-repeat'].append('checked-string-length-call')
        for optimization in ['0', '2']:
            runtime = output / ('runtime-O' + optimization + '.o')
            runner.run('runtime-O' + optimization, [clang, '-O' + optimization, '-std=c11', *cflags,
                       '-I' + str(gc / 'include'), '-I' + str(source_dir / 'runtime'),
                       '-c', source_dir / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
            record['artifacts'][str(runtime)] = sha(runtime)
            for label, (_, _, executions) in FIXTURES.items():
                binary = output / (label + '-O' + optimization)
                runner.run('link-' + label + '-O' + optimization,
                           [clang, '-O' + optimization, '-Wno-override-module', programs[label],
                            runtime, gc_archive, *libraries, '-lm', '-lpthread', '-ldl', '-o', binary], timeout=120)
                record['artifacts'][str(binary)] = sha(binary)
                for name, arguments, expected, diagnostic in executions:
                    execution = label + '/' + name + '/O' + optimization
                    result = runner.run('run-' + name + '-O' + optimization, [binary, *arguments],
                                        expected=expected, status=1 if diagnostic else 0, timeout=30)
                    require(result.stderr == diagnostic, 'native diagnostic differs: ' + execution)
                    record['cases'].append({'case': execution, 'passed': True,
                                            'stdout': expected.decode(), 'stderr': diagnostic.decode()})
        require(len(record['cases']) == 68, 'native case completion inventory differs')
        integrity()
        record.update(complete=True, status='passed', fixtures=12, native_cases=68,
                      optimizations=['0', '2'])
    except BaseException as error:
        record.update(complete=False, status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        try:
            integrity()
            record['immutable_inputs_verified_after'] = True
        except BaseException as error:
            record.update(complete=False, status='invalidated',
                          integrity_error=type(error).__name__ + ': ' + str(error))
            raise
        finally:
            save()
    print(str(output / 'receipt.json') + ': passed (60 native cases, O0/O2)')


if __name__ == '__main__':
    main()
