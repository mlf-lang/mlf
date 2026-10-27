#!/usr/bin/env python3
"""Build only two test modules against an authenticated, read-only GHC producer.

Run serially under the task's process-tree resource watchdog. This does not
build the compiler, change its sources, or invoke native/MLF bootstrap.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import types

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.file_digest(Path(path).open('rb'), 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve(strict=True)
    receipt_path = args.build_receipt.resolve(strict=True)
    producer_dir = receipt_path.parent
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(producer_dir) or producer_dir.is_relative_to(output):
        parser.error('output must be new and separate from producer')
    output.mkdir(parents=True)
    objects = output / 'objects'
    objects.mkdir()
    record = {'complete': False, 'scope': 'partial selector differential and lazy-demand controls',
              'compiler_modules_rebuilt': False, 'native_execution': False,
              'performance_assertion': False, 'commands': []}

    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    save()
    try:
        direct_path = source / 'tools/shared/test_direct.py'
        direct = types.ModuleType('selector_test_direct_authentication')
        direct.__file__ = str(direct_path)
        exec(compile(direct_path.read_bytes(), str(direct_path), 'exec'), direct.__dict__)
        producer = direct.authenticate_build(receipt_path, producer_dir / 'bin', root=source)
        if producer['optimization'] != '2':
            raise ValueError('this acceptance harness requires the candidate O2 producer')
        manifest_path = HERE / 'oracle-manifest.json'
        oracle = json.loads(manifest_path.read_text())
        if sha(HERE / 'FrozenSelectors.hs') != oracle['oracle_sha256']:
            raise ValueError('frozen oracle changed')
        if sha(HERE / 'original-selector-excerpts.txt') != oracle['excerpt_sha256']:
            raise ValueError('frozen original excerpts changed')
        for path, digest in oracle['shared_dependency_pins'].items():
            if sha(source / path) != digest:
                raise ValueError('oracle dependency changed; independent re-audit required: ' + path)
        inputs = {str(path): sha(path) for path in
                  [Path(__file__), HERE / 'SelectorDifferential.hs', HERE / 'FrozenSelectors.hs',
                   HERE / 'original-selector-excerpts.txt', manifest_path, receipt_path, direct_path]}
        record.update(producer_receipt_sha256=sha(receipt_path), source_root=str(source),
                      producer_directory=str(producer_dir), inputs=inputs,
                      expected_checks=154072, oracle_shared_dependencies=oracle['shared_dependency_pins'])
        env = {**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8'}

        def run(label, argv, timeout=300):
            argv = list(map(str, argv))
            item = {'label': label, 'argv': argv, 'cwd': str(output), 'timeout_seconds': timeout}
            record['commands'].append(item)
            save()
            with (output / (label + '.stdout')).open('wb') as stdout, (output / (label + '.stderr')).open('wb') as stderr:
                started = time.monotonic()
                process = subprocess.Popen(argv, cwd=output, env=env, stdin=subprocess.DEVNULL,
                                           stdout=stdout, stderr=stderr, start_new_session=True)
                try:
                    process.wait(timeout=timeout)
                except BaseException:
                    for sig in [signal.SIGTERM, signal.SIGKILL]:
                        try:
                            os.killpg(process.pid, sig)
                        except ProcessLookupError:
                            pass
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            pass
                    process.wait(timeout=5)
                    raise
                item.update(exit_code=process.returncode, wall_seconds=time.monotonic()-started)
            item['stdout_sha256'] = sha(output / (label + '.stdout'))
            item['stderr_sha256'] = sha(output / (label + '.stderr'))
            save()
            if process.returncode:
                raise RuntimeError(label + ' failed; inspect its retained logs')
            return (output / (label + '.stdout')).read_bytes()

        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
                 '-no-user-package-db', '-hide-all-packages', '-O2', '-fpedantic-bottoms',
                 '-fno-state-hack', '-Werror=incomplete-patterns']
        for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
            flags += ['-package', package]
        ghc = producer['ghc']['path']
        import_flags = ['-i', '-i'+str(objects), '-i'+str(producer_dir / 'objects')]
        # One-shot compilation: only immutable .hi files are searchable. No
        # implementation source root is on the module search path.
        run('compile-oracle', [ghc, '-c', *flags, *import_flags, '-odir', objects, '-hidir', objects,
                               HERE / 'FrozenSelectors.hs'])
        run('compile-harness', [ghc, '-c', *flags, *import_flags, '-o', objects / 'SelectorDifferential.o',
                                '-ohi', objects / 'Main.hi', HERE / 'SelectorDifferential.hs'])
        transport = []
        for label, path in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            target = objects / (label + '.o')
            run('compile-'+label, [producer['cc']['path'], '-O2', '-std=c11', '-I'+str(source / 'runtime'),
                                   '-c', source / path, '-o', target])
            transport.append(target)
        link_objects = [producer_dir / path for path in sorted(producer['object_inputs'])
                        if path.endswith('.o') and path != 'objects/Main.o']
        executable = output / 'selector-differential'
        run('link', [ghc, *flags, '-rtsopts=ignoreAll', objects / 'SelectorDifferential.o',
                     objects / 'FrozenSelectors.o', *link_objects, *transport, '-o', executable])
        stdout = run('execute', [executable], timeout=600)
        lines = stdout.splitlines()
        if len(lines) != 2 or lines[1] != b'Frozen selector differential, ordered identity/error and lazy-demand controls passed.':
            raise ValueError('completion output changed')
        observed = json.loads(lines[0])
        expected = {'format': 'selector-differential-v1', 'complete': True, 'checks': 154072,
                    'exhaustive_interfaces': 512, 'authored_interfaces': 20,
                    'stress_interfaces': 4, 'scope': 'partial'}
        if observed != expected or (output / 'execute.stderr').read_bytes():
            raise ValueError('actual test inventory/status/stderr changed')
        direct.authenticate_build(receipt_path, producer_dir / 'bin', root=source)
        for path, digest in inputs.items():
            if sha(path) != digest:
                raise ValueError('test input changed during run: '+path)
        for path, digest in producer['object_inputs'].items():
            if sha(producer_dir / path) != digest:
                raise ValueError('read-only producer object changed: '+path)
        record.update(complete=True, observed=observed, immutable_inputs_verified_after=True,
                      artifacts={str(path.relative_to(output)): sha(path)
                                 for path in [executable, *objects.glob('*.o'), *objects.glob('*.hi')]})
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
