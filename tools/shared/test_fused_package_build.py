#!/usr/bin/env python3
"""Exercise default package builds, retained LLVM handoff and staged cache reuse."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from test_direct import authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--build-runner', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    receipt = args.build_receipt.resolve(strict=True)
    producer = receipt.parent
    output = args.output.resolve()
    if output.is_relative_to(producer) or producer.is_relative_to(output):
        parser.error('independent output directory required')
    authenticate_build(receipt, producer / 'bin')
    runner = args.build_runner.resolve(strict=True)
    emlf, manager = producer / 'bin/emlf', producer / 'bin/mlfpkg'
    output.mkdir(parents=True, exist_ok=False)
    app, cache = output / 'app', output / 'cache'
    shutil.copytree(ROOT / 'examples/packages', app, ignore=shutil.ignore_patterns('.mlf-build'))
    manifest = app / 'mlf-package.json'
    data = json.loads(manifest.read_text())
    data['executables']['another'] = dict(data['executables']['hello'])
    manifest.write_text(json.dumps(data, indent=2) + '\n')
    evidence = {'complete': False, 'producer_receipt_sha256': sha(receipt),
                'driver_sha256': sha(__file__), 'build_runner_sha256': sha(runner),
                'fixture_inputs': {str(p.relative_to(ROOT)): sha(p)
                    for p in (ROOT / 'examples/packages').rglob('*')
                    if p.is_file() and '.mlf-build' not in p.parts},
                'commands': [], 'checks': [], 'build_reports': {}}

    def save():
        (output / 'receipt.json').write_text(json.dumps(evidence, indent=2) + '\n')

    def check(name, passed):
        evidence['checks'].append({'name': name, 'passed': bool(passed)})
        save()
        if not passed:
            raise AssertionError(name)

    def run(name, argv, *, success=True, expected=None):
        command = list(map(str, argv))
        row = {'name': name, 'argv': command, 'state': 'running'}
        evidence['commands'].append(row)
        save()
        start = time.monotonic()
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env={**os.environ, 'MLF_BUILD_RUNNER': str(runner)}, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
            row['timed_out'] = True
        for suffix, content in [('stdout', stdout), ('stderr', stderr)]:
            path = output / (name + '.' + suffix)
            path.write_bytes(content)
            row[suffix + '_sha256'] = sha(path)
        row.update(exit_code=process.returncode, seconds=time.monotonic() - start)
        # Package commands legitimately report "Building ..." on stderr.
        # Executable oracles require exact stdout and empty stderr.
        passed = (not row.get('timed_out') and (process.returncode == 0) == success
                  and (expected is None or (stdout == expected and not stderr)))
        row['state'] = 'passed' if passed else 'failed'
        save()
        if not passed:
            raise RuntimeError(name + ' failed; retained stdout/stderr in ' + str(output))
        return stdout

    def build(name, *, directory=None, store=None, jobs=2, compiler=None, success=True):
        directory = directory or output / 'build'
        run(name, [manager, '--manifest', manifest, '--compiler', compiler or emlf,
            '--runtime', ROOT / 'runtime/mlf_runtime.c', '--build-dir', directory,
            '--cache-dir', store or cache, '--jobs', str(jobs), 'build'], success=success)
        report = directory / 'build-report.json'
        saved = output / (name + '.build-report.json')
        shutil.copyfile(report, saved)
        evidence['build_reports'][name] = {'path': str(saved), 'sha256': sha(saved)}
        result = json.loads(saved.read_text())
        check(name + ' completion is current', result['complete'] == success)
        return result

    def calls(report, flag):
        return [row['argv'] for row in report['commands'] if len(row['argv']) > 1 and row['argv'][1] == flag]

    def binaries(name, expected, directory=None):
        directory = directory or output / 'build'
        for target in ['hello', 'another']:
            run(name + '-' + target, [directory / 'bin' / target], expected=expected)

    def target_artifact(report, name='hello'):
        return Path(next(row['metadata'] for row in report['crates']
                         if row['crate'].endswith('/target-' + name))).parent

    def emitted_artifacts(report):
        return [Path(row['query_report']).parent for row in report['codegen']]

    save()
    run('runner-protocol', [runner, '--protocol-version'], expected=b'1\n')
    original_output = b'Hello, local packages!\n'
    cold = build('cold')
    check('current compiler advertises fused codegen', cold['toolchain']['compiler-fused-codegen'])
    fused = calls(cold, '--compile-crate-to-llvm-gc')
    check('two cold targets each invoke the compiler once', len(fused) == 2 and not calls(cold, '--crate-to-llvm-gc'))
    check('dependency libraries remain checked-only', len(calls(cold, '--compile-crate')) == 2
          and all(not (Path(row['metadata']).parent / 'retained.ll').exists()
                  for row in cold['crates'] if row['crate'].endswith('/library')))
    check('parallel targets have separate codegen partitions',
          len({argv[argv.index('--codegen-cache') + 1] for argv in fused}) == 2)
    check('emission workers consume authenticated retained results', len(cold['codegen']) == 2
          and all(row['queries']['cache_source'] == 'retained-root' for row in cold['codegen']))
    binaries('cold-output', original_output)
    original_llvm = {path.joinpath('program.ll').read_bytes() for path in emitted_artifacts(cold)}

    warm = build('warm')
    check('warm build reuses every artifact', all(row['cached'] for row in warm['builds']))
    check('warm build does not compile or emit again', not any(calls(warm, flag) for flag in
          ['--compile-crate', '--compile-crate-to-llvm-gc', '--crate-to-llvm-gc']))
    binaries('warm-output', original_output)

    serial_dir = output / 'serial-build'
    serial = build('serial-cold', directory=serial_dir, store=output / 'serial-cache', jobs=1)
    check('jobs 1 and 2 produce identical LLVM',
          {path.joinpath('program.ll').read_bytes() for path in emitted_artifacts(serial)} == original_llvm)
    binaries('serial-output', original_output, serial_dir)

    shutil.rmtree(output / 'build')
    restored = build('restore-build-directory')
    check('shared artifacts survive removal of the producing directory', all(row['cached'] for row in restored['builds']))
    binaries('restored-output', original_output)

    target = target_artifact(restored)
    retained_bytes = (target / 'retained.ll').read_bytes()
    (target / 'retained.ll').write_bytes(retained_bytes + b'\n; damaged retained result\n')
    repaired = build('repair-retained')
    check('damaged retained LLVM invalidates its owning artifact',
          len(calls(repaired, '--compile-crate-to-llvm-gc')) == 1
          and (target / 'retained.ll').read_bytes() == retained_bytes)
    check('repair preserves backend input-cache reuse',
          json.loads((target / 'retained-codegen-query.json').read_text())['input_reused'])
    binaries('retained-repair-output', original_output)

    emitted = emitted_artifacts(repaired)[0]
    (emitted / 'program.ll').write_bytes(b'damaged emission\n')
    repaired_emission = build('repair-emission')
    check('emission repair uses the valid retained artifact without recompilation',
          not any(calls(repaired_emission, flag) for flag in
                  ['--compile-crate', '--compile-crate-to-llvm-gc', '--crate-to-llvm-gc'])
          and any(row['queries']['cache_source'] == 'retained-root' for row in repaired_emission['codegen']))
    binaries('emission-repair-output', original_output)

    dependency = app / 'message/Message.emlf'
    old = dependency.read_text()
    needle = 'render (Message text) = text'
    check('dependency mutation reaches the intended body', old.count(needle) == 1)
    dependency.write_text(old.replace(needle, needle + ' ++ " updated"'))
    changed = build('changed-dependency')
    check('changed dependency rebuilds both roots through the fused entry',
          len(calls(changed, '--compile-crate-to-llvm-gc')) == 2 and not calls(changed, '--crate-to-llvm-gc'))
    changed_output = b'Hello, local packages! updated\n'
    binaries('changed-output', changed_output)

    published = {name: sha(output / 'build/bin' / name) for name in ['hello', 'another']}
    source = app / 'Main.emlf'
    original_source = source.read_text()
    source.write_text('module Main where\nmain = missingFusedBuildName\n')
    build('rejected-source', success=False)
    check('failed compilation preserves previously published binaries',
          all(sha(output / 'build/bin' / name) == digest for name, digest in published.items()))
    binaries('failed-build-kept-output', changed_output)
    source.write_text(original_source)
    recovered = build('recover-source')
    check('restoring good source reuses the last successful artifacts', all(row['cached'] for row in recovered['builds']))

    # This adapter changes only feature discovery. It executes the same compiler
    # for real staged builds, so the legacy fallback cannot pass with fake output.
    wrapper = output / 'compiler-without-fused-protocol'
    wrapper.write_text('#!' + sys.executable + '\nimport os, subprocess, sys\nreal = ' + repr(str(emlf)) + '\n'
        'if sys.argv[1:] == ["--help"]:\n'
        '    p = subprocess.run([real, "--help"], stdout=subprocess.PIPE)\n'
        '    sys.stdout.buffer.write(p.stdout.replace(b"--codegen-cache", b"--unavailable-codegen-cache"))\n'
        '    raise SystemExit(p.returncode)\n'
        'os.execv(real, [real, *sys.argv[1:]])\n')
    wrapper.chmod(0o755)
    evidence['legacy_adapter_sha256'] = sha(wrapper)
    legacy_dir = output / 'legacy-build'
    legacy = build('legacy-cold', compiler=wrapper, directory=legacy_dir, store=output / 'legacy-cache')
    check('compiler without fused-cache protocol uses the staged path',
          not legacy['toolchain']['compiler-fused-codegen'] and not calls(legacy, '--compile-crate-to-llvm-gc')
          and len(calls(legacy, '--compile-crate')) == 4 and len(calls(legacy, '--crate-to-llvm-gc')) == 2)
    binaries('legacy-output', changed_output, legacy_dir)
    legacy_warm = build('legacy-warm', compiler=wrapper, directory=legacy_dir, store=output / 'legacy-cache')
    check('staged fallback retains its independent caches', all(row['cached'] for row in legacy_warm['builds']))

    authenticate_build(receipt, producer / 'bin')
    check('producer, driver, runner and original fixtures stayed pinned',
          sha(receipt) == evidence['producer_receipt_sha256'] and sha(__file__) == evidence['driver_sha256']
          and sha(runner) == evidence['build_runner_sha256']
          and all(sha(ROOT / name) == digest for name, digest in evidence['fixture_inputs'].items()))
    evidence['complete'] = True
    save()
    print('PASS fused package builds, staged libraries, cache reuse, recovery and publication')


if __name__ == '__main__':
    main()
