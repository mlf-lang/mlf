#!/usr/bin/env python3
"""Qualify authenticated direct-host binaries without emitting implementation source."""
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
import time

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_CASES = [
    # --frontend runs the maintained recursive/evidence checks before its
    # final parser success banner. Require every banner in order, not only the suffix.
    ('frontend', '--frontend',
     b'shared frontend: qualified recursive inference checks passed\n'
     b'shared frontend: declaration provenance and declared forall field checks passed\n'
     b'shared frontend: recursive inference checks passed\n'
     b'shared frontend: parser and namespace checks passed\n'),
    ('native-first', '--native-first', b'shared frontend: first native semantics checks passed\n'),
    ('native-second', '--native-second', b'shared frontend: checks passed\n'),
]
# O0's canonical-prelude workload is substantially slower even on the upstream
# compiler. Select limits only from the authenticated producer, never a CLI
# optimization label. O2's native-first margin is justified separately below.
# CI166 exhausted 2400s after the qualified-recursion banner. The residual
# suite grew from 90 to 163 literal compilation calls; allow a bounded 3600s
# for O0 frontend only, without changing its cases/order or the 120m job bound.
def frontend_case_timeout(name, optimization, frontend_seconds=None):
    if optimization not in ('0', '2'):
        raise ValueError('unsupported authenticated optimization level')
    if name not in {case[0] for case in FRONTEND_CASES}:
        raise ValueError('unknown frontend case')
    maximum = 3600 if optimization == '0' else 1800
    if frontend_seconds is not None and not 1 <= frontend_seconds <= maximum:
        raise ValueError('frontend timeout must be between 1 and ' + str(maximum) + ' seconds')
    if name == 'frontend':
        return frontend_seconds if frontend_seconds is not None else (3600 if optimization == '0' else 1200)
    if optimization == '0':
        return 1200
    # CI167 timed out at 120s with the identical binary that passed CI166.
    # Only these six closed native-first checks get additional finite margin.
    return 180 if name == 'native-first' else 120

ORACLES = ['tests/async-task/suite.stdout', 'tests/async-task/processes.stdout',
           'tests/async-task/wait-graph.stdout', 'tests/async-process/suite.stdout']


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def identified(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha(path)}


def verify_file(item, expected=None):
    if not isinstance(item, dict) or not isinstance(item.get('path'), str):
        raise ValueError('missing input path in producer receipt')
    path = Path(item['path'])
    if not path.is_absolute() or not path.is_file() or path.resolve() != path:
        raise ValueError('producer input is not a resolved regular file: ' + str(path))
    if expected is not None and path != Path(expected).resolve():
        raise ValueError('producer resolved a different input: ' + str(path))
    if sha(path) != item.get('sha256'):
        raise ValueError('producer input changed: ' + str(path))


def authenticate_build(receipt_path, binaries, root=ROOT):
    """Require a complete exact-source producer, never merely today's input hashes."""
    root, binaries = root.resolve(), binaries.resolve()
    manifest_path = root / 'shared-sources.json'
    manifest = json.loads(manifest_path.read_text())
    producer = json.loads(Path(receipt_path).read_text())
    if producer.get('complete') is not True or producer.get('typecheck_only') is not False:
        raise ValueError('complete executable-producing build receipt required')
    # Native aggregate build reports currently lack the same per-module producer
    # schema. Do not invent direct-source provenance for those reports.
    if producer.get('producer_host') != 'GHC' or producer.get('implementation_identity') != 'MLF/shared-haskell-v1 GHC':
        raise ValueError('supported direct GHC producer receipt required; native aggregate reports are not sufficient')
    if producer.get('ghc', {}).get('version') != '9.14.1' or producer.get('optimization') not in ['0', '2']:
        raise ValueError('unqualified direct-host toolchain')
    if not {'-fpedantic-bottoms', '-fno-state-hack', '-clear-package-db', '-global-package-db', '-no-user-package-db'}.issubset(producer.get('flags', [])):
        raise ValueError('missing demand-preserving compiler flags')
    for key in ['source_syntax', 'frontend_semantics', 'builtin_interface', 'primitive_abi']:
        if producer.get(key) != manifest.get(key):
            raise ValueError('source contract changed: ' + key)
    if producer.get('manifest_sha256') != sha(manifest_path):
        raise ValueError('shared manifest changed since build')
    expected_modules = {x['module']: (root / x['path']).resolve() for x in manifest['modules']}
    for key in ['shared_inputs', 'resolved_modules', 'inferred_shared_interfaces']:
        if set(producer.get(key, {})) != set(expected_modules):
            raise ValueError('incomplete producer module inventory: ' + key)
    for name, path in expected_modules.items():
        if not path.is_relative_to(root):
            raise ValueError('shared source escaped checkout: ' + name)
        verify_file(producer['shared_inputs'][name], path)
        verify_file(producer['resolved_modules'][name], path)
        audit = producer['inferred_shared_interfaces'][name]
        if audit.get('unresolved_literal_constraints') is not False or not isinstance(audit.get('signatures'), str):
            raise ValueError('incomplete inferred-interface audit: ' + name)
        if hashlib.sha256(audit['signatures'].encode()).hexdigest() != audit.get('sha256'):
            raise ValueError('inferred-interface audit digest mismatch: ' + name)
    hosts = {*root.glob('host/ghc/**/*.hs'), *root.glob('host/ghc/**/*.c'),
             root / 'runtime/mlf_process_supervisor.c', *root.glob('runtime/*.h')}
    expected_hosts = {str(path.relative_to(root)): path.resolve() for path in hosts}
    if set(producer.get('host_inputs', {})) != set(expected_hosts):
        raise ValueError('incomplete producer host inventory')
    for name, path in expected_hosts.items():
        verify_file(producer['host_inputs'][name], path)
    for path in manifest['host_only']:
        if path not in expected_hosts:
            raise ValueError('manifest host input omitted by producer: ' + path)
    configurations = [root / 'cabal.project', root / 'mlf-shared.cabal', root / 'shared-sources.json',
        *sorted(root.glob('libraries/*/mlf-package.json')), root / 'mlf-package.json',
        root / 'tests/mlf-package.json', root / 'tests/shared/mlf-package.json',
        root / 'testing/mlf-package.json', root / 'testing/tools/mlf-package.json']
    expected_configuration = {str(path.relative_to(root)): path for path in configurations}
    if set(producer.get('configuration_inputs', {})) != set(expected_configuration):
        raise ValueError('incomplete producer configuration inventory')
    for name, path in expected_configuration.items():
        verify_file(producer['configuration_inputs'][name], path)
    tools = {'build_driver': root / 'tools/shared/build.py', 'cabal_manifest': root / 'mlf-shared.cabal'}
    for key in ['ghc', 'cc', 'orchestrator', 'build_driver', 'cabal_manifest', 'ghc_settings']:
        verify_file(producer.get(key), tools.get(key))
    toolchain = producer.get('toolchain', {})
    verify_file(toolchain.get('actual_ghc'))
    toolchain_files = toolchain.get('files', {})
    actual = toolchain['actual_ghc']
    if not toolchain_files or toolchain_files.get(actual['path']) != actual['sha256']:
        raise ValueError('missing actual compiler/toolchain dependency closure')
    for path, digest in toolchain_files.items():
        verify_file({'path': path, 'sha256': digest})
    host_modules = {name: root / path for name, path in {
        'MLF.Primitive': 'host/ghc/MLF/Primitive.hs', 'MLF.Host.Base': 'host/ghc/MLF/Host/Base.hs',
        'MLF.Host.IO': 'host/ghc/MLF/Host/IO.hs', 'MLF.Host.Async': 'host/ghc/MLF/Host/Async.hs'}.items()}
    if set(producer.get('resolved_host_modules', {})) != set(host_modules):
        raise ValueError('missing actual host module resolution')
    for name, path in host_modules.items():
        verify_file(producer['resolved_host_modules'][name], path)
    dependencies = producer.get('installed_dependencies', {}).get('files', {})
    if not dependencies:
        raise ValueError('missing installed dependency closure')
    for path, digest in dependencies.items():
        verify_file({'path': path, 'sha256': digest})
    for file, key in [('packages.txt', 'package_database_sha256'), ('ghc-info.txt', 'ghc_info_sha256')]:
        if sha(Path(receipt_path).parent / file) != producer.get(key):
            raise ValueError('producer toolchain evidence changed: ' + file)
    expected_outputs = {x['name'] for x in manifest['executables']}
    if set(producer.get('outputs', {})) != expected_outputs:
        raise ValueError('incomplete producer executable inventory')
    for name in expected_outputs:
        verify_file(producer['outputs'][name], binaries / name)
    if not producer.get('commands') or any(x.get('exit_code') != 0 for x in producer['commands']):
        raise ValueError('producer did not finish every command')
    for entry in producer['commands']:
        verify_file({'path': entry['log'], 'sha256': entry['log_sha256']})
    return producer


class CommandRunner:
    def __init__(self, root, output, receipt, save):
        self.root, self.output, self.receipt, self.save = root, output, receipt, save

    @staticmethod
    def stop_group(process):
        # start_new_session gives this command its own original process group.
        # A dead leader (or closed capture pipes) does not mean its children died.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        finally:
            # Always escalate, including when communicate already returned after
            # the leader exited and a TERM-ignoring child redirected its stdio.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        cleanup = {'scope': 'original-process-group', 'capture_drained': True, 'leader_reaped': True}
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired as error:
            # An escaped descendant can retain these pipes. Do not hang while
            # draining them or signal an unrelated/new process group to fix it.
            stdout, stderr = error.stdout or b'', error.stderr or b''
            cleanup['capture_drained'] = False
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                cleanup['leader_reaped'] = False
        cleanup['complete'] = cleanup['capture_drained'] and cleanup['leader_reaped']
        if not cleanup['complete']:
            cleanup['error'] = 'original process-group cleanup could not drain captures or reap the leader within its bounds'
        return stdout, stderr, cleanup

    def run(self, name, command, *, overrides=None, status=0, expected=None, timeout=180):
        command = list(map(str, command))
        overrides = overrides or {}
        entry = {'name': name, 'argv': command, 'cwd': str(self.root), 'started': time.time(),
                 'timeout_seconds': timeout, 'environment_overrides': overrides, 'state': 'running'}
        self.receipt['commands'].append(entry)
        self.save()
        stdout, stderr = b'', b''
        started = time.monotonic()
        process = None
        group_stopped = False
        try:
            process = subprocess.Popen(command, cwd=self.root, env={**os.environ, **overrides},
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                entry['timed_out'] = True
                stdout, stderr, entry['cleanup'] = self.stop_group(process)
                group_stopped = True
            entry['exit_code'] = process.returncode
            if entry.get('timed_out'):
                raise RuntimeError(name + ' exceeded ' + str(timeout) + ' seconds')
            if process.returncode != status or (expected is not None and stdout != expected) or (status == 0 and stderr):
                raise RuntimeError(name + ' failed; see ' + str(self.output / (name + '.stderr')))
            entry['state'] = 'passed'
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        except BaseException as error:
            entry['state'] = 'failed'
            entry['error'] = str(error)
            if process is not None:
                if not group_stopped:
                    stdout, stderr, entry['cleanup'] = self.stop_group(process)
                entry['exit_code'] = process.returncode
            raise
        finally:
            for suffix, data in [('stdout', stdout), ('stderr', stderr)]:
                path = self.output / (name + '.' + suffix)
                path.write_bytes(data)
                entry[suffix + '_sha256'] = sha(path)
            entry['seconds'] = time.monotonic() - started
            self.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', type=Path, required=True)
    parser.add_argument('--build-receipt', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    parser.add_argument('--frontend-timeout', type=int,
                        help='bounded frontend override: O0 1..3600, O2 1..1800; defaults come from authenticated optimization')
    args = parser.parse_args()
    if args.frontend_timeout is not None and not 1 <= args.frontend_timeout <= 3600:
        parser.error('frontend timeout must be between 1 and 3600 seconds')
    binaries, output = args.bin_dir.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'format': 1, 'complete': False, 'source_mode': 'authenticated direct committed shared source',
               'commands': [], 'inputs': {}}

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(receipt, indent=2) + '\n')
        temporary.replace(output / 'receipt.json')

    save()
    try:
        if os.name != 'posix':
            raise ValueError('direct async fixture qualification requires a POSIX host')
        build_receipt = (args.build_receipt or binaries.parent / 'receipt.json').resolve(strict=True)
        producer = authenticate_build(build_receipt, binaries)
        budgets = {name: frontend_case_timeout(name, producer['optimization'], args.frontend_timeout)
                   for name, _, _ in FRONTEND_CASES}
        receipt['execution_budgets'] = budgets
        receipt['producer'] = {**identified(build_receipt), 'host': producer['producer_host'],
                               'optimization': producer['optimization']}
        compiler = shutil.which(args.cc)
        if not compiler:
            raise ValueError('missing C fixture compiler: ' + args.cc)
        receipt['fixture_compiler'] = identified(compiler)
        compiler = receipt['fixture_compiler']['path']
        receipt['orchestrator'] = identified(sys.executable)
        inputs = [ROOT / x for x in ORACLES]
        inputs += [ROOT / 'shared-sources.json', ROOT / 'tests/async-process/fixture.c',
                   ROOT / 'tests/async-task/fixture.c', Path(__file__).resolve(),
                   ROOT / 'tools/release/test-suite-build-receipts.py', build_receipt,
                   Path(compiler), Path(sys.executable).resolve()]
        receipt['inputs'] = {str(path): sha(path) for path in inputs}
        runner = CommandRunner(ROOT, output, receipt, save)
        process_helper, task_helper = output / 'process-fixture', output / 'task-fixture'
        for name, source, destination in [('process', 'tests/async-process/fixture.c', process_helper),
                                           ('task', 'tests/async-task/fixture.c', task_helper)]:
            runner.run(name + '-fixture', [compiler, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', ROOT / source, '-o', destination])
        receipt['helpers'] = {str(path): sha(path) for path in [process_helper, task_helper]}
        specs = [('async-task', ORACLES[0], task_helper), ('async-task-processes', ORACLES[1], task_helper),
                 ('async-task-wait-graph', ORACLES[2], task_helper), ('async-process', ORACLES[3], process_helper)]
        for name, oracle, helper in specs:
            work = output / (name + '-work')
            work.mkdir()
            runner.run(name, [binaries / name], overrides={'MLF_ASYNC_FIXTURE': str(helper), 'MLF_ASYNC_WORK': str(work)},
                       expected=(ROOT / oracle).read_bytes())
        work = output / 'panic-work'
        work.mkdir()
        result = runner.run('async-process-panic', [binaries / 'async-process-panic'], status=1, expected=b'',
                            overrides={'MLF_ASYNC_FIXTURE': str(process_helper), 'MLF_ASYNC_WORK': str(work)})
        if b'async-scope-panic' not in result.stderr:
            raise RuntimeError('panic failed for unrelated reason')
        runner.run('panic-child-reaped', [process_helper, 'assert-gone', work / 'panic.pid'])
        for name, option, expected in FRONTEND_CASES:
            runner.run('shared-frontend-' + name, [binaries / 'shared-frontend', option], expected=expected,
                       timeout=budgets[name])
        runner.run('build-receipts', [sys.executable, ROOT / 'tools/release/test-suite-build-receipts.py',
                   '--executable', binaries / 'build-receipts', '--output', output / 'build-receipts'], timeout=1800)
        for collection in [receipt['inputs'], receipt['helpers']]:
            if any(sha(path) != digest for path, digest in collection.items()):
                raise RuntimeError('test input changed during qualification')
        # A successful run cannot outlive the source/tool identities it claims.
        authenticate_build(build_receipt, binaries)
        receipt['complete'] = True
    except BaseException as error:
        receipt['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
