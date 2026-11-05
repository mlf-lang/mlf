#!/usr/bin/env python3
"""Compile a fresh user program against an authenticated fixed native installation.

The compiler supplies the installed library/runtime objects and their link
contract. Each invocation emits new user LLVM, runs one ordinary Clang -O2
compilation, and links a new executable. No user compilation cache is read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time


def sha(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pinned_file(record):
    require(isinstance(record, dict), 'invalid installed file record')
    name, digest = record.get('path'), record.get('sha256')
    require(isinstance(name, str) and Path(name).is_absolute(), 'installed file path must be absolute')
    require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest), 'invalid installed file digest')
    path = Path(name).resolve(strict=True)
    require(path.is_file() and sha(path) == digest, 'installed file changed: ' + name)
    return path


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('-i', '--include', action='append', default=[], type=Path)
    parser.add_argument('--no-prelude', action='store_true')
    parser.add_argument('-o', '--output', required=True, type=Path)
    parser.add_argument('--build-dir', type=Path, help='fresh directory for IR, objects, logs and receipt')
    parser.add_argument('--timeout', type=float, default=1800)
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    source = args.source.resolve(strict=True)
    require(compiler.is_file() and os.access(compiler, os.X_OK), 'compiler is not executable')
    require(source.is_file(), 'source is not a regular file')
    output = args.output.absolute()
    require(output.resolve() not in {source, compiler}, 'output would replace an input')
    require(not output.is_dir(), 'output is a directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.build_dir:
        build = args.build_dir.absolute()
        build.mkdir(parents=True, exist_ok=False)
    else:
        build = Path(tempfile.mkdtemp(prefix='.mlf-native-', dir=output.parent))
    receipt = {'format': 'MLF-NATIVE-PROGRAM-BUILD-1', 'complete': False,
               'source': str(source), 'compiler': str(compiler), 'output': str(output),
               'fixed_library_precompiled': True, 'fresh_user_compilation': True,
               'llvm_jobs': 1, 'commands': []}

    def save():
        temporary = build / 'receipt.json.new'
        temporary.write_text(json.dumps(receipt, indent=2) + '\n')
        temporary.replace(build / 'receipt.json')

    def run(label, argv, stdout):
        command = [str(value) for value in argv]
        before = time.perf_counter()
        with stdout.open('wb') as out:
            process = subprocess.Popen(command, stdout=out, stderr=subprocess.PIPE,
                                       start_new_session=True)
            try:
                _, errors = process.communicate(timeout=args.timeout)
            except BaseException:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, errors = process.communicate()
                (build / (label + '.stderr')).write_bytes(errors)
                raise
        (build / (label + '.stderr')).write_bytes(errors)
        receipt['commands'].append({'phase': label, 'command': command,
                                    'wall_seconds': time.perf_counter() - before,
                                    'exit_code': process.returncode, 'stdout': str(stdout),
                                    'stderr': str(build / (label + '.stderr'))})
        save()
        require(process.returncode == 0, label + ' failed; see ' + str(build / (label + '.stderr')))

    save()
    try:
        run('installation', [compiler, '--native-install-info'], build / 'installation.json')
        installation = json.loads((build / 'installation.json').read_text())
        require(installation.get('format') == 'MLF-NATIVE-LIBRARY-1', 'unsupported native installation format')
        require(isinstance(installation.get('identity'), str), 'native installation omitted identity')
        native_records = installation.get('objects')
        require(isinstance(native_records, list) and len(native_records) >= 2, 'native library/runtime inventory missing')
        objects = [pinned_file(record) for record in native_records]
        require(len(set(objects)) == len(objects), 'duplicate installed object')
        clang = pinned_file(installation.get('clang'))
        require(os.access(clang, os.X_OK), 'installed Clang is not executable')
        require(output.resolve() not in {*objects, clang}, 'output would replace an installation input')
        flags = installation.get('link_args')
        require(isinstance(flags, list) and all(isinstance(x, str) and '\0' not in x for x in flags),
                'native link arguments must be an array of strings')
        require(all(x == '-lm' or Path(x).is_absolute() for x in flags),
                'native link dependencies must use explicit absolute paths')
        link_records = installation.get('link_inputs')
        require(isinstance(link_records, list), 'native link input inventory missing')
        link_inputs = [pinned_file(record) for record in link_records]
        require(len(set(link_inputs)) == len(link_inputs), 'duplicate native link input')
        require(set(link_inputs) == {Path(x).resolve(strict=True) for x in flags if x != '-lm'},
                'native link arguments differ from authenticated input inventory')
        require(output.resolve() not in set(link_inputs), 'output would replace a link dependency')
        # These arguments come from the compiler-authenticated manifest, never
        # from a user-supplied shell command or self-authenticating JSON file.
        receipt['installation'] = installation
        receipt['source_sha256'] = sha(source)
        frontend = [compiler]
        if args.no_prelude:
            frontend += ['--no-prelude']
        for include in args.include:
            frontend += ['-i', include.resolve(strict=True)]
        frontend += ['--emit-native-llvm', source]
        run('frontend', frontend, build / 'program.ll')
        require((build / 'program.ll').stat().st_size > 0, 'compiler produced empty LLVM')
        run('llvm', [clang, '-O2', '-Wno-override-module', '-c', build / 'program.ll',
                     '-o', build / 'program.o'], build / 'llvm.stdout')
        # Detect changed installation inputs between source admission and link.
        require([pinned_file(record) for record in native_records] == objects,
                'native object inventory changed')
        require([pinned_file(record) for record in link_records] == link_inputs,
                'native link input inventory changed')
        run('link', [clang, build / 'program.o', *objects, *flags,
                     '-o', build / 'program'], build / 'link.stdout')
        require([pinned_file(record) for record in native_records] == objects,
                'native object changed during linking')
        require([pinned_file(record) for record in link_records] == link_inputs,
                'native dependency changed during linking')
        require(sha(source) == receipt['source_sha256'], 'source changed during compilation')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix='.' + output.name + '-', dir=output.parent,
                                             delete=False) as file:
                temporary = Path(file.name)
            shutil.copy2(build / 'program', temporary)
            temporary.replace(output)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        receipt.update(complete=True, output_sha256=sha(output),
                       llvm_sha256=sha(build / 'program.ll'),
                       user_object_sha256=sha(build / 'program.o'))
    except BaseException as error:
        receipt['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        receipt['wall_seconds'] = time.perf_counter() - started
        save()
    print(build / 'receipt.json')


if __name__ == '__main__':
    main()
