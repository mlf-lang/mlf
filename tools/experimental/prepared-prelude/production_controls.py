#!/usr/bin/env python3
"""Finite correctness controls for one frozen canonical production candidate.

This does not qualify a closed toolchain or assert performance. It snapshots
test inputs and reuses a byte-pinned copy of the candidate's canonical cache.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/shared'))
from test_direct import CommandRunner


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-receipt', type=Path, required=True)
    parser.add_argument('--clang', type=Path, required=True)
    parser.add_argument('--gc-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    original_receipt = args.candidate_receipt.resolve(strict=True)
    candidate = original_receipt.parent
    producer = json.loads(original_receipt.read_text())
    require(producer.get('complete') is True, 'candidate receipt is incomplete')
    source = Path(producer['source']).resolve(strict=True)
    ghc = Path(next(c['argv'][0] for c in producer['commands'] if c['label'] == 'canonical-modules'))
    clang = args.clang.resolve(strict=True)
    gc = args.gc_prefix.resolve(strict=True)
    emlf = Path(producer['outputs']['emlf']['path'])
    generator = Path(producer['outputs']['builtin-prelude']['path'])
    pins = dict(producer['inputs'])
    for item in producer['outputs'].values():
        pins[item['path']] = item['sha256']
    for path in [original_receipt, ghc, clang, Path(sys.executable).resolve(), Path(__file__).resolve(),
                 ROOT / 'tools/shared/test_direct.py', candidate / 'host.o', candidate / 'supervisor.o']:
        pins[str(path)] = sha(path)
    receipt = {'complete': False, 'scope': 'frozen production candidate finite correctness controls',
               'closed_toolchain_qualification': False, 'performance_assertions': False,
               'candidate_receipt': str(original_receipt), 'source': str(source),
               'source_conversion_or_overlay': False, 'inputs': pins,
               'commands': [], 'results': {}, 'fixture_transformations': []}

    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def check_pins():
        changed = [path for path, expected in pins.items() if sha(path) != expected]
        require(not changed, 'pinned inputs changed: ' + ', '.join(changed))

    def snapshot(path, relative):
        target = out / 'suite-source' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = sha(path)
        target.write_bytes(Path(path).read_bytes())
        require(sha(target) == expected and sha(path) == expected, 'input changed while snapshotting: ' + str(path))
        pins[str(target)] = expected
        return target

    def run(label, argv, timeout=1800):
        check_pins()
        stdout_path, stderr_path = out / (label + '.stdout'), out / (label + '.stderr')
        command = list(map(str, argv))
        entry = {'label': label, 'argv': command, 'cwd': str(source),
                 'input_pins_verified_before': True, 'stdout': str(stdout_path), 'stderr': str(stderr_path)}
        receipt['commands'].append(entry)
        save()
        with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
            process = subprocess.Popen(command, cwd=source,
                env={**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8'},
                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                process.communicate(timeout=timeout)
            except BaseException:
                _, _, cleanup = CommandRunner.stop_group(process)
                entry['cleanup'] = cleanup
                raise
            finally:
                entry['exit'] = process.returncode
                entry['stdout_sha256'] = sha(stdout_path)
                entry['stderr_sha256'] = sha(stderr_path)
                save()
        check_pins()
        entry['input_pins_verified_after'] = True
        save()
        require(process.returncode == 0, 'command failed: ' + label)
        print('PASS ' + label, flush=True)
        return stdout_path.read_bytes(), stderr_path.read_bytes()

    save()
    try:
        check_pins()
        identity_script = snapshot(ROOT / 'tools/shared/builtin_prelude_identity.py',
                                   Path('tools/shared/builtin_prelude_identity.py'))
        identity_spec = importlib.util.spec_from_file_location('frozen_builtin_identity', identity_script)
        identity_module = importlib.util.module_from_spec(identity_spec)
        identity_spec.loader.exec_module(identity_module)
        identity, identity_inputs = identity_module.source_identity(source)
        receipt['builtin_identity'] = identity
        receipt['builtin_identity_inputs'] = identity_inputs
        stdout, stderr = run('verify-candidate-builtin', [emlf, '--verify-builtin-prelude', identity])
        require(stdout == b'builtin Prelude verified\n' and not stderr, 'unexpected builtin verifier result')
        stdout, stderr = run('regenerate-candidate-builtin', [generator, identity])
        canonical = source / 'bootstrap/MLF/BuiltinPreludeData.hs'
        require(not stderr and stdout == canonical.read_bytes(), 'fresh regeneration differs from canonical source')
        receipt['results']['builtin'] = {'verified': True, 'exact_regeneration': True,
                                         'canonical_sha256': sha(canonical), 'bytes': len(stdout)}
        save()

        # Keep each test's repository-relative root stable while freezing its
        # runtime, source programs and expected outputs. These are test inputs,
        # never alternate production implementation modules.
        for relative in ['tools/experimental/prepared-prelude/test.py',
                         'tools/experimental/prepared-prelude/native.py',
                         'tools/shared/test_direct.py']:
            snapshot(ROOT / relative, Path(relative))
        manifest_path = snapshot(source / 'benchmarks/manifest.json', Path('benchmarks/manifest.json'))
        manifest = json.loads(manifest_path.read_text())
        fixture_paths = {'examples/multiparameter.emlf', 'examples/monad-state-do.emlf',
            'tools/experimental/installed-prelude/tests/fixtures/hello.emlf',
            'tools/experimental/installed-prelude/tests/fixtures/unicode.emlf',
            'tools/experimental/installed-prelude/tests/fixtures/collision.emlf'}
        for row in manifest['workloads']:
            if row['name'] != 'regex-redux':
                fixture_paths.update([row['sources']['mlf'], row['fixture']])
                if row.get('input_fixture'):
                    fixture_paths.add(row['input_fixture'])
        for relative in sorted(fixture_paths):
            snapshot(source / relative, Path(relative))
        for path in sorted((source / 'runtime').rglob('*')):
            if path.is_file() and path.suffix in ['.c', '.h']:
                snapshot(path, path.relative_to(source))

        # A private copy avoids Main.o races with independent parent controls.
        objects = out / 'objects'
        objects.mkdir()
        cache_pins = {}
        for path in sorted((candidate / 'objects').rglob('*')):
            if path.is_file() and path.name not in ['Main.o', 'Main.hi']:
                dest = objects / path.relative_to(candidate / 'objects')
                dest.parent.mkdir(parents=True, exist_ok=True)
                expected = sha(path)
                shutil.copyfile(path, dest)
                require(sha(dest) == expected and sha(path) == expected, 'candidate cache changed while copying')
                cache_pins[str(dest)] = expected
        receipt['copied_canonical_cache'] = cache_pins
        flags = list(producer['flags'])
        for option in ['-odir', '-hidir']:
            flags[flags.index(option) + 1] = str(objects)

        def build_fixture(label, path, replace_import=False):
            text = path.read_text()
            dest = out / 'fixtures' / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if replace_import:
                old, new = 'Bootstrap.PreparedImportedCore', 'Bootstrap.ImportedRoot'
                require(text.count(old) == 1, 'direct fixture import seam changed')
                text = text.replace(old, new)
                receipt['fixture_transformations'].append({'source': str(path), 'source_sha256': sha(path),
                    'output': str(dest), 'replacement': [old, new], 'scope': 'host fixture import only'})
            dest.write_text(text)
            pins[str(dest)] = sha(dest)
            for name in ['Main.o', 'Main.hi']:
                (objects / name).unlink(missing_ok=True)
            binary = out / label
            run('build-' + label, [ghc, '--make', '-j1', *flags, dest,
                candidate / 'host.o', candidate / 'supervisor.o', '-o', binary])
            pins[str(binary)] = sha(binary)
            return binary

        host = build_fixture('production-control', HERE / 'ProductionControls.hs')
        suite = out / 'suite-source/tools/experimental/prepared-prelude'
        run('semantic-controls', [sys.executable, suite / 'test.py', '--compiler', host,
            '--output', out / 'semantic', '--benchmarks', '--route', 'direct', '--skip-import-counts'], timeout=3600)
        semantic = json.loads((out / 'semantic/receipt.json').read_text())
        require(semantic.get('complete') and len(semantic['cases']) == 33 and
                semantic.get('immutable_inputs_verified_after'), 'semantic control receipt incomplete')
        receipt['results']['semantic'] = {'complete': True, 'cases': 33, 'receipt': str(out / 'semantic/receipt.json')}
        save()
        run('native-controls', [sys.executable, suite / 'native.py', '--compiler', host,
            '--clang', clang, '--gc-prefix', gc, '--output', out / 'native', '--route', 'direct'], timeout=3600)
        native = json.loads((out / 'native/receipt.json').read_text())
        require(native.get('complete') and len(native['cases']) == 36 and
                native.get('immutable_inputs_verified_after'), 'native control receipt incomplete')
        receipt['results']['native'] = {'complete': True, 'cases': 36, 'receipt': str(out / 'native/receipt.json')}
        save()
        for label, path, replacement, count, banner in [
            ('direct-import', HERE / 'DirectImportControls.hs', True, 46, b'PASS all independent direct import controls\n'),
            ('builtin-context', HERE / 'BuiltinPreludeContextControls.hs', False, 39, b'PASS all 39 builtin context controls\n'),
            ('builtin-artifact', source / 'tools/shared/fixtures/item4/BuiltinArtifact.hs', False, None,
             b'item4 builtin artifact end-to-end: passed\n')]:
            binary = build_fixture(label, path, replacement)
            stdout, stderr = run('run-' + label, [binary])
            require(not stderr and stdout.endswith(banner), 'unexpected fixture result: ' + label)
            if count is not None:
                require(len(stdout.splitlines()) == count + 1 and
                        all(line.startswith(b'PASS ') for line in stdout.splitlines()),
                        'fixture case inventory changed: ' + label)
            receipt['results'][label] = {'complete': True, 'cases': count,
                'stdout_sha256': hashlib.sha256(stdout).hexdigest(), 'executable_sha256': sha(binary)}
            save()
        changed_cache = [path for path, expected in cache_pins.items() if sha(path) != expected]
        require(not changed_cache, 'canonical shared cache recompiled or changed: ' + ', '.join(changed_cache))
        receipt['canonical_cache_unchanged'] = True
        receipt['complete'] = True
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        changed = [path for path, expected in pins.items() if sha(path) != expected]
        receipt['immutable_inputs_verified_after'] = not changed
        if changed:
            receipt.update(complete=False, changed_inputs=changed)
        save()
        if changed:
            raise RuntimeError('correctness inputs changed during execution')
    print(out / 'receipt.json')


if __name__ == '__main__':
    main()
