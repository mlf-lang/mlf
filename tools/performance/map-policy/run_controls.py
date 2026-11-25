#!/usr/bin/env python3
"""Source-bound Map maintenance successor; no copied producer objects.
The public receipt requires an owned-tree supervisor's successful terminal
receipt. Forced SIGKILL of that supervisor remains outside its guarantee.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import traceback
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tools/testing'))
from receipt_selection import select

OPTIMIZATIONS = (0, 2)
PREPARE_SHA = 'fc6191e1cc7d7024cbc580836917e6efb9be86e64989e89b3eef4da720b8bf41'
FIXTURE_SHA = '30ccc1caeaec7de404a00c4432ebb92c1a5b52167291f060da08552d79522d72'
DIRECT_BLOB = 'a46bd66949e81c5761dff3446201640837ec8f68'
SUPERVISOR_BLOB = '620e88b557139a6b19ca63097decaa9148bdd819'
WORK_SECONDS = 1200
CLEANUP_SECONDS = 10
HISTORICAL_LINE = 'Balance controls: 24649 raw-shape pairs; 400 mutation steps; 30 independent demand/order cases passed'
WITNESS = 'PASS witness step21/full-shape/valid/content; historical exact-shape equivalence is false'
FINAL_LINE = 'Current Map policy controls passed; historical exact-shape equivalence explicitly does not hold at step 21'
GROUPS = ['complete historical 24649/400/30', 'retained live raw/demand',
          '400-step live/model/historical trace', 'independent policy contents']
DEMAND_LABELS = [
    'empty ignores comparator', 'singleton ignores comparator and payload', 'singleton forces key',
    'duplicates keep last lazy value', 'list tail versus key', 'comparator versus later key',
    'ascending run lazy values', 'descending run lazy values', 'mixed run first demanded value',
    'fromListWith duplicate lazy combine', 'fromListWith demanded combine',
    'fromListWith select new discard old', 'fromListWith select old discard new',
    'fromListWith new before old', 'fromListWith distinct ignores combiner',
    'both tree bottoms', 'empty left right bottom', 'union empty ignores comparator and combine',
    'union lazy combine', 'union demanded combine', 'union comparator versus values',
    'union left value before right', 'union right value selected',
    'multi-node union lazy values', 'multi-node comparator versus values',
]
# Fixed per-case outcomes reviewed against the authored demands and the source-
# bound O0/O2 qualification. These are additional protocol checks, not a claim
# that recorded observations alone establish semantic correctness.
DEMAND_VALUES = [
    'Right True', 'Right True', 'Left "key"', 'Right True', 'Left "key"', 'Left "cmp"',
    'Right True', 'Right True', 'Left "one"', 'Right True', 'Left "combine"',
    'Right True', 'Right True', 'Left "new"', 'Right True', 'Left "left"', 'Left "right"',
    'Right True', 'Right True', 'Left "combine"', 'Left "cmp"', 'Left "left-value"',
    'Left "right-value"', 'Right True', 'Left "cmp"',
]
EXPECTED_MODULES = {
    'Bootstrap/Map', 'Bootstrap/Types', 'Bootstrap/Std', 'Bootstrap/IndexVec',
    'MLF/Primitive', 'MLF/Host/Base', 'MLF/Host/IO', 'MLF/Host/Async',
    'HistoricalMap', 'FrozenMap', 'BaselineMap', 'RetainedBalanceControls',
    'HistoricalBalanceControls', 'CurrentMapPolicyControls', 'Main',
}

def require(value, message):
    if not value:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()

def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)

def source_module(path, name, expected_sha=None, expected_blob=None):
    require(not path.is_symlink() and path.is_file(), 'regular module source')
    raw = path.read_bytes()
    require((expected_sha is None or sha(raw) == expected_sha) and
            (expected_blob is None or blob(raw) == expected_blob), 'module source identity: ' + str(path))
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module, sha(raw)

def validate_success(stdout, stderr, exit_code):
    require(type(exit_code) is int and exit_code == 0 and stderr == b'', 'successful clean target required')
    require(type(stdout) is bytes and stdout.endswith(b'\n') and b'\r' not in stdout,
            'strict LF-terminated target protocol required')
    lines = stdout.decode('utf-8')[:-1].split('\n')
    prefix = [HISTORICAL_LINE, 'PASS ' + GROUPS[0], 'PASS ' + GROUPS[1],
              WITNESS, 'PASS ' + GROUPS[2], 'PASS ' + GROUPS[3]]
    require(lines[:6] == prefix, 'complete ordered historical/current/witness inventory')
    require(len(lines) == 6 + 2 * len(DEMAND_LABELS) + 1 and lines[-1] == FINAL_LINE,
            'complete exact target output inventory')
    value = r'(?:Right (?:True|False)|Left "(?:[^"\\]|\\.)*")'
    for index, label in enumerate(DEMAND_LABELS):
        observation, passed = lines[6 + index * 2:8 + index * 2]
        match = re.fullmatch(re.escape('Demand observation ' + label + ': historical=') +
                             '(' + value + ')' + r' current=(' + value + ')', observation)
        require(match is not None and match[1] == match[2] == DEMAND_VALUES[index],
                'exact reviewed paired demand observation: ' + label)
        require(passed == 'PASS demand ' + label, 'one exact demand PASS: ' + label)
    return {'groups': GROUPS, 'witness': WITNESS, 'demand_labels': DEMAND_LABELS,
            'historical': {'raw_pairs': 24649, 'mutation_steps': 400, 'demand_cases': 30}}

def command_log_summary(stdout, stderr):
    require(type(stdout) is bytes and type(stderr) is bytes, 'raw command captures required')
    return {'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr),
            'stdout_bytes': len(stdout), 'stderr_bytes': len(stderr)}

def validate_command_logs(summary, stdout, stderr):
    require(summary == command_log_summary(stdout, stderr), 'command capture digest/length mismatch')

def require_same_artifacts(before, after):
    require(type(before) is dict and bool(before) and type(after) is dict and before == after,
            'fresh binary/home outputs changed across target')

def validate_supervision(status, guard):
    require(type(status) is int and status == 0 and type(guard) is dict and
            guard.get('complete') is True and guard.get('cleanup_complete') is True and
            type(guard.get('target_exit_code')) is int and guard['target_exit_code'] == 0 and
            guard.get('survivors') == [] and guard.get('cancel_signals') == [] and
            guard.get('phase') == 'terminal' and guard.get('reason') == 'target exited' and
            guard.get('signals') == [] and 'error' not in guard and 'cleanup_error' not in guard,
            'successful owned-tree terminal evidence required')

def worker_bootstrap():
    # A single ordinary Python program: no nested string-encoded exec statement.
    return '''import pathlib, hashlib, sys, types
if len(sys.argv) != 6:
    raise RuntimeError('worker argument inventory')
p = pathlib.Path(sys.argv[1])
raw = p.read_bytes()
if hashlib.sha256(raw).hexdigest() != sys.argv[2]:
    raise RuntimeError('worker source identity')
m = types.ModuleType('map_policy_worker')
m.__file__ = str(p)
exec(compile(raw, str(p), 'exec'), m.__dict__)
m.worker(types.SimpleNamespace(source=pathlib.Path(sys.argv[3]), producer=pathlib.Path(sys.argv[4]), output=pathlib.Path(sys.argv[5])))
'''

def worker(a):
    chosen = select('map-policy/', OPTIMIZATIONS)
    optimizations = OPTIMIZATIONS if chosen is None else (chosen,)
    source, producer, out = a.source.resolve(), a.producer.resolve(), a.output.resolve()
    record = {'complete': False, 'stage': 'authenticate', 'commands': [], 'lanes': [],
              'scope': 'fresh 15-module shared-GHC qualification; historical Map algorithms on current Int64/host base; not native/full-producer qualification',
              'performance_measured': False, 'copied_producer_objects': False}
    def persist():
        save(out / 'worker-receipt.json', record)
    def log(name, stream):
        return out / name / stream
    def run(name, argv, timeout, accepted=(0,)):
        record['stage'] = name
        row = {'name': name, 'argv': list(map(str, argv)), 'timeout_seconds': timeout, 'complete': False}
        record['commands'].append(row); persist()
        (out / name).mkdir(exist_ok=False)
        start = time.monotonic()
        try:
            with log(name, 'stdout').open('wb') as stdout, log(name, 'stderr').open('wb') as stderr:
                # Do not detach from the supervised worker. A timeout aborts
                # this worker; its supervisor adopts and cleans remaining kids.
                result = subprocess.run(row['argv'], cwd=out, env=environment,
                                        stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, timeout=timeout)
            row['exit_code'] = result.returncode
            require(result.returncode in accepted, name + ' failed')
            row['complete'] = True
            return result.returncode
        finally:
            row['seconds'] = time.monotonic() - start
            if log(name, 'stdout').is_file() and log(name, 'stderr').is_file():
                row.update(command_log_summary(log(name, 'stdout').read_bytes(), log(name, 'stderr').read_bytes()))
            else:
                row.update(complete=False, capture_error='missing command capture file')
            save(out / name / 'command.json', row)
            persist()
            require(not row.get('capture_error'), 'command capture incomplete')
    environment = {**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'PYTHONDONTWRITEBYTECODE': '1',
                   'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_NOSYSTEM': '1',
                   'GIT_CONFIG_GLOBAL': '/dev/null', 'LC_ALL': 'C.UTF-8', 'OMP_NUM_THREADS': '1',
                   'OPENBLAS_NUM_THREADS': '1', 'MAKEFLAGS': '-j1'}
    for key in ('GHC_PACKAGE_PATH', 'GHC_OPTIONS', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
                'LIBRARY_PATH', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'PYTHONPATH'):
        environment.pop(key, None)
    record['subprocess_environment_policy'] = 'Inherited environment with explicit GHC/Git/thread bounds and removed compiler/library/Python injection search overrides; not hermetic OS execution'
    try:
        persist()
        direct, direct_sha = source_module(source / 'tools/shared/test_direct.py', 'map_direct_auth', expected_blob=DIRECT_BLOB)
        auth = direct.authenticate_build(producer / 'receipt.json', producer / 'bin', root=source)
        require(auth['optimization'] == '2', 'ordinary current O2 producer authentication required')
        preparation, prepare_sha = source_module(HERE / 'prepare_map_policy.py', 'map_preparation', expected_sha=PREPARE_SHA)
        current_fixture = (HERE / 'CurrentMapPolicyControls.hs').read_bytes()
        require(sha(current_fixture) == FIXTURE_SHA, 'reviewed current policy fixture')
        record['driver_inputs'] = {str(Path(__file__)): sha(Path(__file__).read_bytes()),
                                  str(HERE / 'prepare_map_policy.py'): prepare_sha,
                                  str(HERE / 'CurrentMapPolicyControls.hs'): FIXTURE_SHA,
                                  str(source / 'tools/shared/test_direct.py'): direct_sha}
        record['producer_receipt_sha256'] = direct.sha(producer / 'receipt.json')
        record['authenticated_manifest_sha256'] = auth['manifest_sha256']
        # The receipt need not assert a Git commit. Record the observed checkout
        # separately, not as an invented field in the producer's attestation.
        run('checkout-head', ['git', '--no-replace-objects', '-C', source, 'rev-parse', 'HEAD'], 15)
        record['observed_checkout_head'] = log('checkout-head', 'stdout').read_text().strip()
        record['source_basis_commit'] = preparation.CURRENT_COMMIT
        record['source_basis_tree'] = preparation.CURRENT_TREE
        prepared = out / 'prepared'
        record['stage'] = 'prepare-source-bound-copies'; persist()
        selected = {path: preparation.read_regular(source, path) for path in preparation.CURRENT_BLOBS}
        git_calls = []
        def git_output(argv, timeout):
            name = 'historical-git-' + str(len(git_calls))
            git_calls.append(name)
            run(name, argv, timeout)
            return log(name, 'stdout').read_bytes()
        historical = preparation.historical_from_git(source, git_output)
        context = (preparation.CURRENT_COMMIT, preparation.CURRENT_TREE,
                   preparation.HISTORICAL_COMMIT, preparation.HISTORICAL_TREE)
        generated = preparation.prepare_bytes(selected, historical, context)
        preparation.verify_generated(generated, selected, historical, context)
        prepared.mkdir(exist_ok=False)
        for name, raw in generated.items():
            (prepared / name).write_bytes(raw)
        for path, raw in selected.items():
            destination = prepared / 'source' / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            require(destination.read_bytes() == raw, 'source copy identity')
        originals = prepared / 'originals'; originals.mkdir()
        for path in preparation.ORACLE_SHA:
            (originals / Path(path).name).write_bytes(selected[path])
            require((originals / Path(path).name).read_bytes() == selected[path], 'retained original copy')
        (originals / 'fc300-Map.hs').write_bytes(historical)
        require((originals / 'fc300-Map.hs').read_bytes() == historical, 'physical historical copy')
        preparation.verify_generated({name: (prepared / name).read_bytes() for name in generated},
                                     selected, historical, context)
        prep = {'prepared': True, 'qualification_complete': False,
                'source_basis_commit': preparation.CURRENT_COMMIT, 'source_basis_tree': preparation.CURRENT_TREE,
                'historical_commit': preparation.HISTORICAL_COMMIT, 'historical_tree': preparation.HISTORICAL_TREE,
                'current_inputs': {path: {'git_blob': preparation.CURRENT_BLOBS[path], 'sha256': sha(raw)}
                                   for path, raw in selected.items()},
                'generated_sha256': {name: sha(raw) for name, raw in generated.items()},
                'original_oracle_sha256': preparation.ORACLE_SHA,
                'historical_map_sha256': sha(historical), 'historical_map_git_blob': preparation.HISTORICAL_MAP_BLOB,
                'project_include_graph': preparation.project_include_graph(selected),
                'scope': 'exact 22-input source basis, not a current full Git tree or reconstructed historical runtime'}
        save(prepared / 'preparation.json', prep)
        record['preparation'] = prep
        (prepared / 'CurrentMapPolicyControls.hs').write_bytes(current_fixture)
        (prepared / 'Main.hs').write_text('module Main where\nimport qualified CurrentMapPolicyControls as C\nmain :: IO ()\nmain = C.main\n')
        frozen = {str(path): sha(path.read_bytes()) for path in prepared.rglob('*') if path.is_file()}
        for name in ('c', 'o0', 'o2'):
            (out / name).mkdir(exist_ok=False)
        root = prepared / 'source'
        allowed = {(root / path).resolve() for path in prep['current_inputs'] if path.endswith(('.c', '.h'))}
        for name, path in [('host', root / 'host/ghc/cbits/host.c'), ('supervisor', root / 'runtime/mlf_process_supervisor.c')]:
            run('c-' + name, [auth['cc']['path'], '-O2', '-std=c11', '-I' + str(root / 'runtime'),
                             '-MMD', '-MF', out / 'c' / (name + '.d'), '-c', path, '-o', out / 'c' / (name + '.o')], 60)
            dependencies = shlex.split((out / 'c' / (name + '.d')).read_text().replace('\\\n', ' ').split(':', 1)[1])
            actual = {Path(value).resolve() for value in dependencies}
            required = {path.resolve(), (root / 'runtime/mlf_process_supervisor.h').resolve()}
            if name == 'supervisor':
                required.add((root / 'runtime/mlf_process_supervisor_posix.h').resolve())
            require(actual and required <= actual <= allowed, 'exact project C dependency closure')
            record.setdefault('project_C_dependencies', {})[name] = dependencies
        record['fresh_C_objects'] = {str(out / 'c' / (name + '.o')): direct.sha(out / 'c' / (name + '.o'))
                                     for name in ('host', 'supervisor')}
        flags = ['--make', '-j1', '-fforce-recomp', '-XHaskell2010', '-fpedantic-bottoms', '-fno-state-hack',
                 '-package-env', '-', '-clear-package-db', '-global-package-db', '-no-user-package-db',
                 '-hide-all-packages', '-rtsopts=ignoreAll', '-i', '-i' + str(prepared),
                 '-i' + str(root / 'libraries/mlf-foundation'), '-i' + str(root / 'host/ghc')]
        for package in ('base', 'array', 'bytestring', 'text', 'containers', 'directory'):
            flags += ['-package', package]
        ldd = Path(shutil.which('ldd') or '').resolve()
        require(ldd.is_file(), 'installed runtime inspection tool required')
        record['runtime_inspector'] = {'path': str(ldd), 'sha256': direct.sha(ldd)}
        known_runtime = {**auth['toolchain']['files'], **auth['installed_dependencies']['files']}
        for opt in optimizations:
            lane = out / ('o' + str(opt)); binary = lane / 'controls'
            run('build-o' + str(opt), [auth['ghc']['path'], *flags, '-O' + str(opt), '-odir', lane,
                '-hidir', lane, '-stubdir', lane, out / 'c/host.o', out / 'c/supervisor.o', '-o', binary,
                prepared / 'Main.hs'], 240)
            modules = {str(path.relative_to(lane))[:-3] for path in lane.rglob('*.hi')}
            require(modules == EXPECTED_MODULES and all((lane / (name + '.o')).is_file() for name in modules),
                    'exact 15 fresh home modules and objects')
            run('runtime-o' + str(opt), [ldd, binary], 15)
            runtime = {}
            for line in log('runtime-o' + str(opt), 'stdout').read_text().splitlines():
                if 'linux-vdso' in line:
                    continue
                parts = line.strip().split()
                path = parts[2] if '=>' in parts else parts[0] if parts else ''
                require(path.startswith('/'), 'unresolved target dynamic runtime')
                resolved = str(Path(path).resolve())
                require(resolved in known_runtime, 'target runtime outside authenticated producer closure: ' + resolved)
                direct.verify_file({'path': resolved, 'sha256': known_runtime[resolved]})
                runtime[resolved] = known_runtime[resolved]
            require(runtime, 'nonempty target dynamic runtime inventory')
            artifacts_before = {'controls': direct.sha(binary), **{
                name + suffix: direct.sha(lane / (name + suffix))
                for name in sorted(modules) for suffix in ('.o', '.hi')}}
            status = run('target-o' + str(opt), [binary], 40, accepted=(0, 1))
            stdout = log('target-o' + str(opt), 'stdout').read_bytes()
            stderr = log('target-o' + str(opt), 'stderr').read_bytes()
            artifacts_after = {'controls': direct.sha(binary), **{
                name + suffix: direct.sha(lane / (name + suffix))
                for name in sorted(modules) for suffix in ('.o', '.hi')}}
            result = {'optimization': opt, 'exit_code': status, 'binary_sha256': artifacts_before['controls'],
                      'modules': sorted(modules), 'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr),
                      'runtime': runtime, 'artifacts_before_target': artifacts_before,
                      'artifacts_after_target': artifacts_after}
            record['lanes'].append(result)
            persist()
            require_same_artifacts(artifacts_before, artifacts_after)
            try:
                result['success_inventory'] = validate_success(stdout, stderr, status)
                result['complete'] = True
            except ValueError as error:
                result.update(complete=False, error=str(error))
            persist()
        for path, digest in frozen.items():
            require(direct.sha(Path(path)) == digest, 'prepared input changed')
        for path, digest in record['driver_inputs'].items():
            require(direct.sha(Path(path)) == digest, 'driver changed during qualification')
        for path, digest in record['fresh_C_objects'].items():
            require(direct.sha(Path(path)) == digest, 'fresh FFI object changed')
        require(direct.sha(ldd) == record['runtime_inspector']['sha256'], 'runtime inspector changed')
        direct.authenticate_build(producer / 'receipt.json', producer / 'bin', root=source)
        require(direct.sha(producer / 'receipt.json') == record['producer_receipt_sha256'],
                'authenticated producer receipt identity changed during qualification')
        for row in record['commands']:
            require(row['complete'] is True and json.loads((out / row['name'] / 'command.json').read_text()) == row,
                    'terminal command receipt changed or incomplete')
            validate_command_logs({key: row[key] for key in ('stdout_sha256', 'stderr_sha256', 'stdout_bytes', 'stderr_bytes')},
                                  log(row['name'], 'stdout').read_bytes(), log(row['name'], 'stderr').read_bytes())
        record['complete'] = ([lane['optimization'] for lane in record['lanes']] == list(optimizations)
                              and all(lane['complete'] for lane in record['lanes']))
        require(record['complete'], 'Map policy qualification failed; historical/current differences are not waived')
        record['stage'] = 'complete'
    except BaseException as error:
        record.update(complete=False, error=repr(error), failed_stage=record['stage'], traceback=traceback.format_exc())
        raise
    finally:
        persist()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=HERE.parents[2])
    p.add_argument('--producer', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    require(sys.platform == 'linux', 'Linux owned-tree qualification only')
    source, out = a.source.resolve(), a.output.resolve()
    producer = a.producer.resolve()
    require(not out.exists() and not source.is_relative_to(out) and
            (not out.is_relative_to(source) or out.is_relative_to(source / '.mlf-build')) and
            not out.is_relative_to(producer) and not producer.is_relative_to(out),
            'fresh output outside inputs, or dedicated source .mlf-build area')
    out.mkdir(parents=True, exist_ok=False)
    record = {'complete': False, 'stage': 'supervisor-authentication', 'source': str(source),
              'scope': 'limited source-bound Map qualification, not native producer/performance evidence',
              'forced_supervisor_SIGKILL_contained': False}
    try:
        supervisor, digest = source_module(source / 'tools/shared/crc_process_supervisor.py',
                                          'map_owned_tree_supervisor', expected_blob=SUPERVISOR_BLOB)
        record['supervisor_source_sha256'] = digest
        runner_path = Path(__file__).resolve()
        runner_sha = sha(runner_path.read_bytes())
        record['runner_source_sha256'] = runner_sha
        record['work_seconds'] = WORK_SECONDS; record['cleanup_seconds'] = CLEANUP_SECONDS
        save(out / 'receipt.json', record)
        # No CLI bypass mode. The supervised child executes exactly these
        # pinned bytes as a module, then calls the internal worker function.
        bootstrap = worker_bootstrap()
        status = supervisor.supervise([sys.executable, '-B', '-c', bootstrap, str(runner_path), runner_sha,
            str(source), str(producer), str(out)], out / 'supervision.json', WORK_SECONDS, CLEANUP_SECONDS)
        guard = json.loads((out / 'supervision.json').read_text())
        record['supervision'] = guard
        if (out / 'worker-receipt.json').is_file():
            record['worker'] = json.loads((out / 'worker-receipt.json').read_text())
        validate_supervision(status, guard)
        require(record.get('worker', {}).get('complete') is True, 'complete qualified worker receipt required')
        record['cleanup_proof_scope'] = 'Pinned supervisor cleanup_complete is set only after waitpid ECHILD; its schema has no separate ECHILD boolean.'
        require(sha((source / 'tools/shared/crc_process_supervisor.py').read_bytes()) == digest, 'supervisor source drift')
        require(sha(runner_path.read_bytes()) == runner_sha, 'public runner source drift')
        record['stage'] = 'complete'; record['complete'] = True
        opt_labels = '/'.join('O' + str(lane['optimization']) for lane in record['worker']['lanes'])
        print(f'PASS source-bound Map maintenance successor: {opt_labels}; complete historical 24649/400/30; current content/invariants and 25 demand observations; exact step21 shape difference retained', flush=True)
    except BaseException as error:
        record.update(complete=False, error=repr(error), traceback=traceback.format_exc())
        raise
    finally:
        save(out / 'receipt.json', record)

if __name__ == '__main__':
    main()
