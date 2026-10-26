#!/usr/bin/env python3
"""Link a finite bootstrap seed manager from a retained diagnostic GHC cache.

This is not a fresh compiler build or closed-toolchain qualification. The old
candidate may predate the maintained builtin verifier. Its completed controls
receipt must bind the reusable object bytes; only a byte-exact archived copy of
the known noncompiled producer driver may replace that driver's historical pin.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

DRIVER_RELATIVE = 'tools/experimental/prepared-prelude/build_candidate.py'
DRIVER_COMMIT = '24a777e25b16600ecdd1d14b703f7d98375d199f'
DRIVER_SHA256 = '106c09d4db9b6f0b8ee783214139bdb3f88e4ed18dd6bb229db9bde8ab240a81'
ABI = 'mlf-primitive-108-v5'
BUILTIN = 'mlf-primitive/shared-haskell-v1/9'
MAIN_FILES = {'Main.o', 'Main.hi'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def regular(path):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and path.resolve() == path,
            'expected a canonical regular file: ' + str(path))
    return path


def identity(path):
    path = regular(Path(path).resolve(strict=True))
    return {'path': str(path), 'sha256': sha(path)}


def cache_snapshot(root):
    require(root.is_dir() and not root.is_symlink(), 'missing or indirect canonical object cache')
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'object cache contains a symlink: ' + str(path))
        if path.is_file():
            result[str(path.relative_to(root))] = sha(path)
        else:
            require(path.is_dir(), 'object cache contains an unsupported entry')
    require(bool(result), 'canonical object cache is empty')
    return result


def expected_flags(source, objects, manifest):
    # This finite route accepts only the diagnostic producer's reviewed flags.
    # No additional output/search options can redirect writes into its cache.
    return ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
            '-no-user-package-db', '-hide-all-packages', '-O2', '-fpedantic-bottoms', '-fno-state-hack',
            '-Werror=incomplete-patterns', '-Werror=incomplete-uni-patterns', '-Wno-star-is-type',
            '-Wno-overlapping-patterns', '-Wno-deprecations', '-i',
            *['-i' + str(source / root) for root in manifest['source_roots']],
            '-odir', str(objects), '-hidir', str(objects),
            *[item for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']
              for item in ['-package', package]]]


def stop_group(process):
    # Bound cleanup of the original process group; this is not a sandbox.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True, help='completed diagnostic candidate receipt')
    parser.add_argument('--cache-evidence', type=Path, required=True, help='completed finite controls receipt')
    parser.add_argument('--producer-driver-evidence', type=Path,
                        help='archived exact producer driver from checkpoint ' + DRIVER_COMMIT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(os.name == 'posix', 'this finite seed linker requires POSIX process groups')
    candidate_path = regular(args.candidate.resolve(strict=True))
    evidence_path = regular(args.cache_evidence.resolve(strict=True))
    out = args.output.resolve()
    candidate = candidate_path.parent
    require(not out.is_relative_to(candidate) and not candidate.is_relative_to(out),
            'seed output must be separate from the canonical candidate')
    out.mkdir(parents=True, exist_ok=False)
    receipt_path = out / 'receipt.json'
    pins = {}
    original_cache = None
    cache_before = None
    receipt = {'format': 'diagnostic-seed-manager-v1', 'complete': False,
               'scope': 'finite bootstrap seed from retained canonical objects',
               'closed_toolchain_qualification': False, 'source_conversion_or_overlay': False,
               'fresh_compiler_build': False, 'performance_assertions': False,
               'candidate_receipt': identity(candidate_path), 'cache_evidence': identity(evidence_path),
               'inputs': pins, 'commands': [], 'outputs': {}}

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')

    def pin(path, expected=None):
        path = regular(Path(path).resolve(strict=True))
        digest = sha(path)
        require(expected is None or digest == expected, 'seed input differs: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == digest, 'conflicting seed input identity')
        pins[str(path)] = digest
        return path

    def check_pins():
        changed = [path for path, digest in pins.items() if not Path(path).is_file() or sha(path) != digest]
        require(not changed, 'seed inputs changed: ' + ', '.join(changed))

    save()
    try:
        pin(candidate_path, receipt['candidate_receipt']['sha256'])
        pin(evidence_path, receipt['cache_evidence']['sha256'])
        pin(Path(__file__).resolve())
        pin(Path(sys.executable).resolve())
        producer = json.loads(candidate_path.read_text())
        evidence = json.loads(evidence_path.read_text())
        require(producer.get('complete') is True and producer.get('immutable_inputs_verified_after') is True,
                'complete immutable diagnostic candidate required')
        require(producer.get('closed_toolchain_qualification') is False and
                producer.get('source_conversion_or_overlay') is False, 'unsupported diagnostic candidate scope')
        source = Path(producer['source']).resolve(strict=True)
        require(not out.is_relative_to(source) and not source.is_relative_to(out),
                'seed output must be separate from the frozen source')
        receipt.update(source=str(source), candidate_has_builtin_verification=bool(producer.get('builtin_verification')),
                       builtin_verification_required_for_seed=False)
        original_inputs = producer.get('inputs', {})
        require(bool(original_inputs), 'candidate has no input pins')
        replacements = []
        for name, digest in original_inputs.items():
            path = regular(Path(name))
            if sha(path) == digest:
                pin(path, digest)
                continue
            require(args.producer_driver_evidence is not None and
                    path.as_posix().endswith('/' + DRIVER_RELATIVE) and
                    not path.is_relative_to(source) and digest == DRIVER_SHA256,
                    'candidate input changed: ' + name)
            archived = pin(args.producer_driver_evidence.resolve(strict=True), DRIVER_SHA256)
            current = pin(path)
            replacements.append({'original_path': name, 'expected_sha256': digest,
                'current_sha256': pins[str(current)], 'archive': identity(archived),
                'origin_commit': DRIVER_COMMIT, 'origin_path': DRIVER_RELATIVE,
                'scope': 'historical noncompiled producer driver evidence; not executed'})
        require(len(replacements) <= 1, 'multiple historical driver substitutions are forbidden')
        require(args.producer_driver_evidence is None or len(replacements) == 1,
                'producer driver evidence was supplied but no historical driver substitution was needed')
        receipt['historical_driver_evidence'] = replacements
        manifest_path = source / 'shared-sources.json'
        require(str(manifest_path) in original_inputs, 'candidate omitted canonical manifest identity')
        manifest = json.loads(manifest_path.read_text())
        require(producer.get('primitive_abi') == manifest.get('primitive_abi') == ABI and
                producer.get('builtin_interface') == manifest.get('builtin_interface') == BUILTIN,
                'seed requires the primitive 108 / builtin v9 boundary')
        receipt.update(primitive_abi=ABI, builtin_interface=BUILTIN)
        rows = manifest['modules']
        require(len({row['module'] for row in rows}) == len(rows), 'duplicate canonical module identity')
        for relative in [*[row['path'] for row in rows], *manifest['host_only']]:
            path = regular(source / relative)
            require(path.is_relative_to(source) and str(path) in original_inputs,
                    'candidate omitted a canonical source: ' + str(path))
        selections = [row for row in manifest['executables'] if row['name'] == 'mlfpkg']
        require(len(selections) == 1, 'canonical manager wrapper is missing or ambiguous')
        wrapper = regular(source / selections[0]['wrapper'])
        require(str(wrapper) in original_inputs, 'manager wrapper was not pinned by the candidate')
        commands = producer.get('commands', [])
        require(commands and all(row.get('exit') == 0 for row in commands), 'candidate command failed or is incomplete')
        compile_rows = [row for row in commands if row['label'] == 'canonical-modules']
        require(len(compile_rows) == 1, 'candidate canonical compilation is missing or ambiguous')
        ghc = regular(Path(compile_rows[0]['argv'][0]))
        require(str(ghc) in original_inputs, 'candidate omitted its GHC identity')
        original_cache = candidate / 'objects'
        flags = producer.get('flags')
        require(flags == expected_flags(source, original_cache, manifest), 'unsupported candidate compiler flags')
        require(compile_rows[0]['argv'] == [str(ghc), '--make', '-j1', '-no-link', *flags,
                                         *[str(source / row['path']) for row in rows]],
                'canonical compile command differs from the complete manifest')
        emlf = regular(Path(producer['outputs']['emlf']['path']))
        require(emlf == candidate / 'emlf', 'candidate compiler output was relocated')
        for output in producer['outputs'].values():
            pin(output['path'], output['sha256'])
        require(evidence.get('complete') is True and evidence.get('immutable_inputs_verified_after') is True and
                evidence.get('canonical_cache_unchanged') is True and
                evidence.get('closed_toolchain_qualification') is False,
                'completed finite controls with unchanged canonical cache required')
        require(evidence.get('candidate_receipt') == str(candidate_path) and evidence.get('source') == str(source),
                'cache evidence belongs to another candidate/source')
        evidence_inputs = evidence.get('inputs', {})
        require(evidence_inputs.get(str(candidate_path)) == sha(candidate_path) and
                evidence_inputs.get(str(emlf)) == producer['outputs']['emlf']['sha256'] and
                evidence_inputs.get(str(ghc)) == original_inputs[str(ghc)],
                'cache evidence does not bind the candidate compiler/tool')
        c_objects = []
        for name, relative in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            path = candidate / (name + '.o')
            require(str(path) in evidence_inputs, 'cache evidence omitted ' + name + ' object')
            c_rows = [row for row in commands if row['label'] == name]
            require(len(c_rows) == 1, 'candidate C object command is missing or ambiguous: ' + name)
            cc = regular(Path(c_rows[0]['argv'][0]))
            require(str(cc) in original_inputs and str(source / relative) in original_inputs,
                    'candidate C compiler/source identity is missing')
            require(c_rows[0]['argv'] == [str(cc), '-O2', '-std=c11', '-I' + str(source / 'runtime'),
                                         '-c', str(source / relative), '-o', str(path)],
                    'candidate C object command differs: ' + name)
            c_objects.append(pin(path, evidence_inputs[str(path)]))
        cache_before = cache_snapshot(original_cache)
        recorded_cache = {}
        copied_prefix = evidence_path.parent / 'objects'
        for name, digest in evidence.get('copied_canonical_cache', {}).items():
            path = Path(name)
            require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(copied_prefix),
                    'cache evidence contains an unrelated object path')
            relative = str(path.relative_to(copied_prefix))
            require(relative not in recorded_cache, 'duplicate cache evidence identity')
            recorded_cache[relative] = digest
        require(recorded_cache and
                {name: digest for name, digest in cache_before.items() if name not in MAIN_FILES} ==
                {name: digest for name, digest in recorded_cache.items() if name not in MAIN_FILES},
                'canonical cache differs from the completed finite controls')
        for name, digest in recorded_cache.items():
            require(cache_before.get(name) == digest, 'recorded cache entry differs: ' + name)
        for row in rows:
            for suffix in ['.o', '.hi']:
                require(row['module'].replace('.', '/') + suffix in recorded_cache,
                        'finite controls omitted a canonical module object/interface')
        for name, digest in cache_before.items():
            pin(original_cache / name, digest)
        receipt.update(canonical_cache=str(original_cache), canonical_cache_before=cache_before,
                       prior_cache_evidence=recorded_cache, discarded_wrapper_files=sorted(MAIN_FILES),
                       source_flags=flags, ghc=identity(ghc), c_objects=[identity(path) for path in c_objects])
        check_pins()
        owned_objects = out / 'objects'
        shutil.copytree(original_cache, owned_objects, copy_function=shutil.copy2)
        require(cache_snapshot(owned_objects) == cache_before, 'copied object cache differs before linking')
        receipt.update(copied_cache=str(owned_objects), copied_cache_verified_before=True)
        for name in MAIN_FILES:
            (owned_objects / name).unlink(missing_ok=True)
        copied_compiler = out / 'emlf'
        shutil.copy2(emlf, copied_compiler)
        require(sha(copied_compiler) == producer['outputs']['emlf']['sha256'], 'copied compiler differs')
        receipt['compiler_origin'] = identity(emlf)
        receipt['outputs']['emlf'] = identity(copied_compiler)
        new_flags = expected_flags(source, owned_objects, manifest)
        receipt['flags'] = new_flags
        receipt['flag_relocations'] = [{'option': option, 'from': str(original_cache), 'to': str(owned_objects)}
                                       for option in ['-odir', '-hidir']]
        manager = out / 'mlfpkg'
        argv = [str(ghc), '--make', '-j1', *new_flags, str(wrapper),
                *map(str, c_objects), '-o', str(manager)]
        entry = {'label': 'link-seed-manager', 'argv': argv, 'cwd': str(source),
                 'timeout_seconds': 600, 'input_pins_verified_before': True}
        receipt['commands'].append(entry)
        save()
        check_pins()
        stdout_path, stderr_path = out / 'link.stdout', out / 'link.stderr'
        with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
            process = subprocess.Popen(argv, cwd=source, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, start_new_session=True,
                env={**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8'})
            try:
                process.wait(timeout=600)
            except BaseException:
                stop_group(process)
                raise
            finally:
                entry.update(exit_code=process.returncode, stdout=identity(stdout_path), stderr=identity(stderr_path))
                save()
        check_pins()
        entry['input_pins_verified_after'] = True
        require(process.returncode == 0, 'seed manager link failed')
        copied_after = cache_snapshot(owned_objects)
        require({name: digest for name, digest in copied_after.items() if name not in MAIN_FILES} ==
                {name: digest for name, digest in cache_before.items() if name not in MAIN_FILES},
                'manager link changed a copied canonical module')
        require(MAIN_FILES.issubset(copied_after), 'manager wrapper did not produce its own objects')
        require(manager.is_file() and manager.stat().st_size > 0 and os.access(manager, os.X_OK),
                'manager link did not produce an executable')
        receipt['copied_cache_after'] = copied_after
        receipt['outputs']['mlfpkg'] = identity(manager)
        require(sha(copied_compiler) == producer['outputs']['emlf']['sha256'], 'paired compiler changed during link')
        receipt['pair'] = {'compiler': receipt['outputs']['emlf'], 'manager': receipt['outputs']['mlfpkg']}
        receipt['complete'] = True
    except BaseException as error:
        receipt.update(complete=False, error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        changed = [path for path, digest in pins.items() if not Path(path).is_file() or sha(path) != digest]
        changed_outputs = [name for name, item in receipt['outputs'].items()
                           if not Path(item['path']).is_file() or sha(item['path']) != item['sha256']]
        receipt['immutable_inputs_verified_after'] = bool(pins) and not changed
        receipt['immutable_outputs_verified_after'] = bool(receipt['outputs']) and not changed_outputs
        if cache_before is not None:
            try:
                receipt['canonical_cache_unchanged'] = cache_snapshot(original_cache) == cache_before
            except (ValueError, OSError):
                receipt['canonical_cache_unchanged'] = False
        if changed or changed_outputs or receipt.get('canonical_cache_unchanged') is False:
            receipt.update(complete=False, changed_inputs=changed, changed_outputs=changed_outputs)
        save()
        if changed or changed_outputs or receipt.get('canonical_cache_unchanged') is False:
            raise RuntimeError('seed inputs, outputs or canonical cache changed')
    print(receipt_path)


if __name__ == '__main__':
    main()
