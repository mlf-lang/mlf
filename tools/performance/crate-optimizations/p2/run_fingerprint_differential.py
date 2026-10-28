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
import shutil
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
    record = {'complete': False, 'scope': 'fingerprint byte/error/lazy and write-order controls',
              'compiler_modules_rebuilt': False, 'native_execution': False,
              'performance_assertion': False, 'commands': []}

    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    save()
    try:
        direct_path = source / 'tools/shared/test_direct.py'
        direct = types.ModuleType('fingerprint_test_direct_authentication')
        direct.__file__ = str(direct_path)
        exec(compile(direct_path.read_bytes(), str(direct_path), 'exec'), direct.__dict__)
        producer = direct.authenticate_build(receipt_path, producer_dir / 'bin', root=source)
        if producer['optimization'] != '2':
            raise ValueError('this acceptance harness requires the candidate O2 producer')
        manifest_path = HERE / 'oracle-manifest.json'
        oracle = json.loads(manifest_path.read_text())
        if sha(HERE / 'FrozenFingerprint.hs') != oracle['oracle_sha256']:
            raise ValueError('frozen oracle changed')
        if sha(HERE / 'original-fingerprint-excerpts.txt') != oracle['excerpts_sha256']:
            raise ValueError('frozen original excerpts changed')
        for path, digest in oracle['shared_dependency_pins'].items():
            if sha(source / path) != digest:
                raise ValueError('oracle dependency changed; independent re-audit required: ' + path)
        changed_oracles = oracle['changed_dependency_oracles']
        if set(changed_oracles) != {'libraries/mlf-crates/Bootstrap/Separate.hs'}:
            raise ValueError('unexpected changed-dependency oracle inventory')
        changed_inputs = []
        for path, frozen in changed_oracles.items():
            original_file = HERE / frozen['frozen_original_file']
            excerpts_file = HERE / frozen['frozen_original_excerpts_file']
            changed_inputs.extend([original_file, excerpts_file])
            if sha(original_file) != frozen['original_sha256']:
                raise ValueError('frozen old Separate source changed')
            if sha(excerpts_file) != frozen['frozen_original_excerpts_sha256']:
                raise ValueError('frozen old Separate fingerprint excerpts changed')
            # The integrated tree includes the independently controlled P3
            # prefix pool. Retain the exact P2 source as the reviewed bridge:
            # do not repin or weaken the old-vs-P2 outside-region assertion.
            p2_file = HERE / 'p2-Separate.hs'
            changed_inputs.append(p2_file)
            if sha(p2_file) != frozen['candidate_sha256']:
                raise ValueError('frozen P2 Separate bridge changed')
            if sha(source / path) != oracle['integrated_p3_sha256']:
                raise ValueError('integrated Separate differs from reviewed P3')
            before = original_file.read_text()
            after = p2_file.read_text()
            integrated = (source / path).read_text()
            start = frozen['permitted_start_marker']
            end = frozen['permitted_end_marker']
            def unchanged(text):
                if text.count(start) != 1 or text.count(end) != 1:
                    raise ValueError('ambiguous Separate change-boundary markers')
                first, last = text.index(start), text.index(end)
                if first >= last:
                    raise ValueError('invalid Separate change boundaries')
                return text[:first] + text[last:]
            old_outside = unchanged(before)
            if old_outside != unchanged(after) or hashlib.sha256(old_outside.encode()).hexdigest() != frozen['unchanged_outside_region_sha256']:
                raise ValueError('Separate changed outside independently frozen fingerprint region')
            unchanged(integrated)  # Require unique ordered boundaries as well.
            p2_region = after[after.index(start):after.index(end)]
            p3_region = integrated[integrated.index(start):integrated.index(end)]
            old_comment = '  -- with any initial state, so shared datatype prefixes need not be rescanned\n'
            new_comment = '  -- with a canonical nonnegative rolling state, so datatype prefixes need not be rescanned\n'
            if p2_region.count(old_comment) != 1 or p3_region.count(new_comment) != 1:
                raise ValueError('reviewed P3 comment correction changed')
            if p2_region.replace(old_comment, new_comment) != p3_region:
                raise ValueError('P3 changed the independently controlled P2 fingerprint logic')
        inputs = {str(path): sha(path) for path in
                  [Path(__file__), HERE / 'FingerprintDifferential.hs', HERE / 'FrozenFingerprint.hs',
                   HERE / 'original-fingerprint-excerpts.txt', manifest_path, receipt_path, direct_path,
                   *changed_inputs]}
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
                      expected_checks=2503, oracle_shared_dependencies=oracle['shared_dependency_pins'],
                      changed_dependency_oracles=changed_oracles,
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
        for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory', 'filepath']:
            flags += ['-package', package]
        ghc = producer['ghc']['path']
        import_flags = ['-i', '-i'+str(objects)]
        # One-shot compilation: only copied, pinned .hi files are searchable. No
        # implementation source root is on the module search path.
        # Keep the literal old fingerprint loops independent of the new F1
        # arithmetic rules, including later inlining into the harness. Omit
        # oracle interface unfoldings; candidate production stays normal O2.
        run('compile-oracle', [ghc, '-c', *flags, '-fno-enable-rewrite-rules', '-fomit-interface-pragmas', '-dcore-lint',
                               '-ddump-rule-rewrites', '-ddump-to-file',
                               '-ddump-file-prefix', str(output / 'frozen-oracle'),
                               *import_flags, '-odir', objects, '-hidir', objects,
                               HERE / 'FrozenFingerprint.hs'])
        rewrite = output / 'frozen-oracle.dump-rule-rewrites'
        if rewrite.exists() and 'mlf/fingerprintIntStep/' in rewrite.read_text():
            raise ValueError('F1 rule contaminated the frozen P2 oracle')
        record['frozen_oracle_rewrite_rules_disabled'] = True
        record['frozen_oracle_interface_pragmas_omitted'] = True
        record['frozen_oracle_rule_dump_sha256'] = sha(rewrite) if rewrite.exists() else None
        run('compile-harness', [ghc, '-c', *flags, *import_flags, '-odir', objects, '-hidir', objects,
                                '-o', objects / 'FingerprintDifferential.o',
                                '-ohi', objects / 'Main.hi', HERE / 'FingerprintDifferential.hs'])
        verify_copied_dependencies()
        actual_object_files = {str(path.relative_to(objects)) for path in objects.rglob('*') if path.is_file()}
        expected_test_files = {'FrozenFingerprint.o', 'FrozenFingerprint.hi', 'FingerprintDifferential.o', 'Main.hi'}
        if actual_object_files != set(copied_dependencies) | expected_test_files:
            raise ValueError('Haskell compilation output was not exactly two test modules')
        record['new_haskell_modules'] = ['FrozenFingerprint', 'Main (FingerprintDifferential.hs)']
        record['only_two_test_modules_compiled'] = True
        transport = []
        for label, path in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            target = objects / (label + '.o')
            run('compile-'+label, [producer['cc']['path'], '-O2', '-std=c11', '-I'+str(source / 'runtime'),
                                   '-c', source / path, '-o', target])
            transport.append(target)
        link_objects = [objects / path for path in sorted(copied_dependencies) if path.endswith('.o')]
        executable = output / 'fingerprint-differential'
        run('link', [ghc, *flags, '-rtsopts=ignoreAll', objects / 'FingerprintDifferential.o',
                     objects / 'FrozenFingerprint.o', *link_objects, *transport, '-o', executable])
        stdout = run('execute', [executable, output / 'test-files'], timeout=600)
        lines = stdout.splitlines()
        if len(lines) != 2 or lines[1] != b'Frozen fingerprint byte/error/lazy and write-order controls passed.':
            raise ValueError('completion output changed')
        observed = json.loads(lines[0])
        expected = {'format': 'fingerprint-differential-v1', 'complete': True, 'checks': 2503}
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
