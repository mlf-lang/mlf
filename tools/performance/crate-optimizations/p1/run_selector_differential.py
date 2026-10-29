#!/usr/bin/env python3
"""Build isolated test modules against an authenticated, read-only GHC producer.

Run serially under the task's process-tree resource watchdog. This does not
build the compiler, change its sources, or invoke native/MLF bootstrap.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import types

HERE = Path(__file__).resolve().parent


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def replace_once(contents, old, new):
    if contents.count(old) != 1:
        raise ValueError('oracle adaptation must replace exactly one occurrence: ' + old.decode())
    return contents.replace(old, new)


def authenticate_oracle(source, here=HERE):
    """Check literal fixtures and narrowly adapted independent dependencies."""
    manifest_path = here / 'oracle-manifest.json'
    oracle = json.loads(manifest_path.read_text())
    original = (here / 'FrozenSelectors.hs').read_bytes()
    if hashlib.sha256(original).hexdigest() != oracle['oracle_sha256']:
        raise ValueError('frozen oracle changed')
    if sha(here / 'original-selector-excerpts.txt') != oracle['excerpt_sha256']:
        raise ValueError('frozen original excerpts changed')
    for path, digest in oracle['shared_dependency_pins'].items():
        if sha(source / path) != digest:
            raise ValueError('oracle dependency changed; independent re-audit required: ' + path)
    layer = oracle['collection_dependency_reaudit']
    for path, digest in layer['candidate_dependency_pins'].items():
        if sha(source / path) != digest:
            raise ValueError('reviewed collection dependency changed; independent re-audit required: ' + path)
    adaptations = {
        'FrozenSelectorMap.hs': [(b'module Bootstrap.Map where {', b'module FrozenSelectorMap where {')],
        'FrozenSelectorSet.hs': [(b'module Bootstrap.Set where {', b'module FrozenSelectorSet where {'),
                                 (b'import qualified Bootstrap.Map as M;', b'import qualified FrozenSelectorMap as M;')],
    }
    if (len(layer['frozen_modules']) != len(adaptations) or
            {item['file'] for item in layer['frozen_modules']} != set(adaptations)):
        raise ValueError('frozen collection module inventory changed')
    for item in layer['frozen_modules']:
        contents = (here / item['file']).read_bytes()
        if hashlib.sha256(contents).hexdigest() != item['oracle_sha256']:
            raise ValueError('frozen collection oracle changed: ' + item['file'])
        for old, new in reversed(adaptations[item['file']]):
            contents = replace_once(contents, new, old)
        if hashlib.sha256(contents).hexdigest() != item['baseline_sha256']:
            raise ValueError('frozen collection body differs from historical baseline: ' + item['file'])
    adapted = replace_once(original, b'import qualified Bootstrap.Map as M;',
                            b'import qualified FrozenSelectorMap as M;')
    adapted = replace_once(adapted, b'import qualified Bootstrap.Set as Set;',
                            b'import qualified FrozenSelectorSet as Set;')
    if hashlib.sha256(adapted).hexdigest() != layer['adapted_selector_sha256']:
        raise ValueError('import-only selector adaptation changed')
    return oracle, adapted


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
        oracle, adapted_selectors = authenticate_oracle(source)
        oracle_sources = output / 'oracle-sources'
        oracle_sources.mkdir()
        adapted_selector_path = oracle_sources / 'FrozenSelectors.hs'
        adapted_selector_path.write_bytes(adapted_selectors)
        inputs = {str(path): sha(path) for path in
                  [Path(__file__), HERE / 'SelectorDifferential.hs', HERE / 'FrozenSelectors.hs',
                   HERE / 'original-selector-excerpts.txt', HERE / 'FrozenSelectorMap.hs',
                   HERE / 'FrozenSelectorSet.hs', manifest_path, receipt_path, direct_path,
                   adapted_selector_path]}
        shutil.copy2(__file__, output / 'runner-used.py')
        # GHC one-shot home-module lookup uses the requested interface output
        # directory. Populate that directory from the authenticated producer,
        # rather than asking an empty -hidir to fall back to a second -i path.
        # Copy bytes, never hardlink: even an accidental compiler write must not
        # mutate the producer. No compiler implementation source is searchable.
        copied_dependencies = {}
        for path, digest in sorted(producer['object_inputs'].items()):
            relative = Path(path)
            if relative.parts[0] != 'objects' or relative.suffix not in {'.o', '.hi'}:
                raise ValueError('unexpected producer object inventory entry: ' + path)
            original = (producer_dir / relative).resolve(strict=True)
            if not original.is_relative_to(producer_dir) or sha(original) != digest:
                raise ValueError('unauthenticated producer object before copy: ' + path)
            if relative.name in {'Main.o', 'Main.hi'} and len(relative.parts) == 2:
                continue
            target = objects / relative.relative_to('objects')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            if sha(target) != digest:
                raise ValueError('copied dependency differs: ' + path)
            copied_dependencies[str(target.relative_to(objects))] = digest

        def verify_copied_dependencies():
            for path, digest in copied_dependencies.items():
                if sha(objects / path) != digest:
                    raise ValueError('copied compiler dependency was rewritten: ' + path)

        record.update(producer_receipt_sha256=sha(receipt_path), source_root=str(source),
                      producer_directory=str(producer_dir), inputs=inputs,
                      expected_checks=154072, expected_collection_checks=6162,
                      oracle_shared_dependencies=oracle['shared_dependency_pins'],
                      oracle_collection_dependency_layer=oracle['collection_dependency_reaudit'],
                      selector_adaptation='Map/Set imports only; original literal fixture unchanged',
                      copied_dependency_files=copied_dependencies,
                      producer_main_objects_excluded=True,
                      compiler_sources_on_search_path=False)
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
        import_flags = ['-i', '-i'+str(objects)]
        # One-shot compilation: only copied, pinned .hi files are searchable. No
        # implementation source root is on the module search path.
        for module in ['FrozenSelectorMap', 'FrozenSelectorSet']:
            run('compile-'+module, [ghc, '-c', *flags, *import_flags, '-odir', objects, '-hidir', objects,
                                    HERE / (module + '.hs')])
        run('compile-oracle', [ghc, '-c', *flags, *import_flags, '-odir', objects, '-hidir', objects,
                               adapted_selector_path])
        run('compile-harness', [ghc, '-c', *flags, *import_flags, '-odir', objects, '-hidir', objects,
                                '-o', objects / 'SelectorDifferential.o',
                                '-ohi', objects / 'Main.hi', HERE / 'SelectorDifferential.hs'])
        verify_copied_dependencies()
        actual_object_files = {str(path.relative_to(objects)) for path in objects.rglob('*') if path.is_file()}
        expected_test_files = {'FrozenSelectorMap.o', 'FrozenSelectorMap.hi',
                               'FrozenSelectorSet.o', 'FrozenSelectorSet.hi',
                               'FrozenSelectors.o', 'FrozenSelectors.hi', 'SelectorDifferential.o', 'Main.hi'}
        if actual_object_files != set(copied_dependencies) | expected_test_files:
            raise ValueError('Haskell compilation output was not exactly four test modules')
        record['new_haskell_modules'] = ['FrozenSelectorMap', 'FrozenSelectorSet',
                                         'FrozenSelectors', 'Main (SelectorDifferential.hs)']
        record['only_four_test_modules_compiled'] = True
        transport = []
        for label, path in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            target = objects / (label + '.o')
            run('compile-'+label, [producer['cc']['path'], '-O2', '-std=c11', '-I'+str(source / 'runtime'),
                                   '-c', source / path, '-o', target])
            transport.append(target)
        link_objects = [objects / path for path in sorted(copied_dependencies) if path.endswith('.o')]
        executable = output / 'selector-differential'
        run('link', [ghc, *flags, '-rtsopts=ignoreAll', objects / 'SelectorDifferential.o',
                     objects / 'FrozenSelectors.o', objects / 'FrozenSelectorMap.o',
                     objects / 'FrozenSelectorSet.o', *link_objects, *transport, '-o', executable])
        stdout = run('execute', [executable], timeout=600)
        lines = stdout.splitlines()
        if len(lines) != 2 or lines[1] != b'Frozen selector differential, ordered identity/error and lazy-demand controls passed.':
            raise ValueError('completion output changed')
        observed = json.loads(lines[0])
        expected = {'format': 'selector-differential-v1', 'complete': True, 'checks': 154072,
                    'collection_checks': 6162, 'exhaustive_interfaces': 512, 'authored_interfaces': 20,
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
        verify_copied_dependencies()
        record.update(complete=True, observed=observed, immutable_inputs_verified_after=True,
                      copied_dependency_files_unchanged=True,
                      artifacts={str(path.relative_to(output)): sha(path)
                                 for path in [executable, *objects.glob('*.o'), *objects.glob('*.hi')]})
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
