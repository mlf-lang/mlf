#!/usr/bin/python3
"""Fresh ordinary producer adapter. No import-time execution or archived grants.

Only `run BUILD` and `run CONTROLS` launch work. Each consumes a fresh SHA-bound
admission and one-use claim. The original f9 build and authenticators are unchanged.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import types

HERE = Path(__file__).resolve().parent
BASE = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
BUDGETS = {'BUILD': 600, 'CONTROLS': 120}
R13_PINS = {
    'guard.py': '53a5b322fe8ed9e1a527dda0596215ffc81322b43b1864442827c9056c313d0e',
    'oracles.py': '9a9bc72aef6bfe7cf3853620b8b4dc055b12d5ab50df1f53dd95247775d8777f',
    'insertion-map.json': 'c6b7882730f55fb6b8239c6e6462de22eff97e13696018e8133ce1f7d547bcc6',
}
ALLOWED_ENV = {'HOME', 'PATH', 'LD_LIBRARY_PATH', 'LC_ALL', 'LANG', 'TZ',
    'GHC_ENVIRONMENT', 'GHCRTS', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
    'MAKEFLAGS', 'PYTHONDONTWRITEBYTECODE', 'TMPDIR', 'CC', 'TC',
    'LIBRARY_PATH', 'PKG_CONFIG_PATH'}
FORBIDDEN_ENV = {'MLF_QUERY_PROFILE', 'MLF_QUERY_SEMANTIC_AUDIT', 'MLF_QUERY_FAILPOINT',
    'LD_PRELOAD', 'LD_AUDIT', 'LD_DEBUG', 'LD_DEBUG_OUTPUT', 'LD_PROFILE',
    'LD_ASSUME_KERNEL', 'GLIBC_TUNABLES', 'GHC_PACKAGE_PATH', 'GHC_CHARENC', 'HPCTIXFILE'}
CASES = [
    ('version', ['--version'], 0, b'emlf 0.3.0\n', b''),
    ('identity', ['--implementation-identity'], 0, b'MLF/shared-haskell-v1 GHC\n', b''),
    ('semantic-42', ['--run', '--expr', 'printInt (40 + 2)'], 0, b'42\n', b''),
    ('unicode-positive', ['--run', '--expr', 'putStrLn "λ雪🙂"'], 0, 'λ雪🙂\n'.encode(), b''),
    ('type-rejection', ['--type', '--expr', '(True :: Int)'], 1, b'',
     b'Inference: type constructor mismatch: Con "Bool" [] versus Con "Int" []\n'),
]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def safe(value, *, existing=False):
    p = Path(value)
    require(p.is_absolute() and '..' not in p.parts, 'absolute non-traversing path required')
    for q in [p, *p.parents]:
        require(not q.is_symlink(), 'symlink path forbidden: ' + str(q))
    if existing:
        require(p.exists(), 'missing path: ' + str(p))
    return p


def sha(path):
    p = safe(path, existing=True)
    require(p.is_file(), 'regular file required')
    with p.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pin(path):
    p = safe(path, existing=True)
    return {'path': str(p), 'sha256': sha(p), 'bytes': p.stat().st_size}


def verify_pin(item):
    p = safe(item['path'], existing=True)
    require(sha(p) == item['sha256'], 'pin mismatch: ' + str(p))
    if 'bytes' in item:
        require(type(item['bytes']) is int and p.stat().st_size == item['bytes'], 'pin length mismatch')
    return p


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(safe(path, existing=True).read_text(), object_pairs_hook=unique)


def save(path, value):
    p = safe(path)
    temporary = p.with_name(p.name + '.tmp')
    require(not os.path.lexists(temporary), 'temporary output already exists')
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(p)


def module(path, name):
    result = types.ModuleType(name)
    result.__file__ = str(path)
    exec(compile(Path(path).read_bytes(), str(path), 'exec'), result.__dict__)
    return result


def adapter_pins():
    return {str(HERE / 'controller.py'): sha(HERE / 'controller.py')}


def source_check(source):
    require(subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                                   text=True).strip() == BASE, 'frozen source HEAD differs')
    require(not subprocess.check_output(['git', '-C', str(source), 'status',
                                        '--porcelain', '--untracked-files=no']), 'tracked source changed')


def inner_command(phase, admission_path, digest):
    a = load(admission_path)
    python = str(Path(sys.executable).resolve())
    if phase == 'BUILD':
        return [python, '-B', str(Path(a['source']) / 'tools/shared/build.py'),
                '--bootstrap-only', '--optimization', '2', '--build-dir', str(HERE / 'build/producer')]
    return [python, '-B', str(HERE / 'controller.py'), '_qualify',
            '--admission', str(admission_path), '--sha256', digest]


def command(phase, admission_path, digest):
    a = load(admission_path)
    # Preserve the original ordinary watchdog's 2 GiB output limit and CPU cap.
    # An unchanged r13 outer guard adds subreaper/pidfd cleanup and epoch leasing.
    return [str(Path(sys.executable).resolve()), '-B',
            str(Path(a['source']) / 'tools/shared/resource_watchdog.py'),
            '--seconds', str(BUDGETS[phase]), '--address-space-mib', '6144',
            '--rss-mib', '5120', '--max-output-mib', '2048', '--disk-free-mib', '5120',
            str(HERE / phase.lower()), *inner_command(phase, admission_path, digest)]


def validate(path, digest, phase):
    path = safe(path, existing=True)
    require(sha(path) == digest, 'admission SHA mismatch')
    a = load(path)
    require(a['schema'] == 'r14-ordinary-admission-v1' and a['approved'] is True and
            a['phase'] == phase and a['budget_seconds'] == BUDGETS[phase], 'fresh phase admission required')
    require(a['adapter_code_pins'] == adapter_pins(), 'adapter changed after review')
    require(Path(sys.executable).resolve() == Path('/usr/bin/python3').resolve(), 'use /usr/bin/python3')
    require(verify_pin(a['python']) == Path(sys.executable).resolve(), 'Python pin mismatch')
    source = safe(a['source'], existing=True)
    require(source == HERE.parent / 'source', 'unexpected batch source')
    source_check(source)
    for p, h in a['source_pins'].items():
        require(safe(p).is_relative_to(source) and sha(p) == h, 'source input pin mismatch')
    required = [source / x for x in ['tools/shared/build.py', 'tools/shared/test_direct.py',
        'tools/shared/resource_watchdog.py', 'tools/performance/a1-private-index/helper.py',
        'tools/shared/verify_builtin_prelude.py', 'tools/shared/builtin_prelude_identity.py',
        'tools/shared/verify_prepared_libraries.py', 'shared-sources.json']]
    require(all(str(p) in a['source_pins'] for p in required), 'missing original driver/source pins')
    r13 = safe(a['r13'], existing=True)
    for name, expected in R13_PINS.items():
        require(sha(r13 / name) == expected, 'r13 restoration mismatch: ' + name)
    require(a['review']['complete'] is True, 'adapter review required')
    verify_pin(a['review']['receipt'])
    require(isinstance(a['toolchain_evidence'], list) and a['toolchain_evidence'], 'toolchain evidence required')
    for item in a['toolchain_evidence']:
        verify_pin(item)
    require(a['toolchain_files'], 'current toolchain file pins required')
    for p, h in a['toolchain_files'].items():
        require(sha(p) == h, 'toolchain bytes changed: ' + p)
    env = load(verify_pin(a['environment']))
    require(set(env).issubset(ALLOWED_ENV) and all(isinstance(k, str) and isinstance(v, str)
            for k, v in env.items()), 'explicit non-secret environment required')
    require(not (FORBIDDEN_ENV & set(os.environ)), 'unreviewed inherited override')
    for k, v in {'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8',
                 'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(HERE / 'tmp'),
                 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MAKEFLAGS': '-j1'}.items():
        require(env.get(k) == v, 'environment mismatch: ' + k)
    require(all(k in env for k in ['HOME', 'PATH', 'CC']), 'missing tool environment')
    require(safe(env['TMPDIR'], existing=True).is_dir(), 'bounded temporary directory required')
    epoch = load(verify_pin(a['epoch']))
    require(epoch['schema'] == 'astra-lock-epoch-v1' and epoch['new_epoch'] is True and
            epoch['historical_continuity_claimed'] is False, 'new epoch required')
    require(epoch['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'boot changed')
    workspace = safe(a['workspace'], existing=True)
    require(HERE.is_relative_to(workspace) and epoch['workspace'] == str(workspace), 'workspace mismatch')
    require(a['locks'] == [epoch['shared'], epoch['reproduction']], 'lock receipt mismatch')
    require(len(a['locks']) == 2 and Path(a['locks'][0]['path']) == workspace / '.astra-resource-locks/heavy.lock'
            and Path(a['locks'][1]['path']) == source / '.mlf-build/.reproduction.lock', 'lock paths mismatch')
    require(epoch['shared_peer_contention_passed'] is True and epoch['reproduction_reacquired'] is True,
            'current peer/reacquisition evidence required')
    for item in a['locks']:
        st = safe(item['path'], existing=True).stat()
        require((st.st_dev, st.st_ino) == (item['device'], item['inode']), 'lock identity changed')
    if phase == 'BUILD':
        require(a['prior'] == {}, 'BUILD cannot reuse an earlier stage')
    else:
        require(set(a['prior']) == {'controller', 'outer', 'producer'}, 'complete BUILD evidence required')
        old = load(verify_pin(a['prior']['controller']))
        outer_path = verify_pin(a['prior']['outer'])
        producer = verify_pin(a['prior']['producer'])
        require(outer_path == HERE / 'build/outer/guard.json' and producer == HERE / 'build/producer/receipt.json',
                'wrong prior BUILD paths')
        require(old['complete'] is True and old['phase'] == 'BUILD' and old['epoch'] == a['epoch'] and
                old['environment'] == a['environment'] and old['adapter_code_pins'] == a['adapter_code_pins'],
                'prior BUILD binding mismatch')
        require(old['outer'] == a['prior']['outer'] and old['producer_receipt'] == a['prior']['producer'],
                'prior files do not match completed controller')
        require(old['source_pins'] == a['source_pins'] and old['toolchain_files'] == a['toolchain_files'] and
                old['toolchain_evidence'] == a['toolchain_evidence'], 'ordinary inputs changed between stages')
        check_outer(load(outer_path), 'BUILD', old['command'], a)
    return a, env, module(r13 / 'guard.py', 'r14_original_guard'), module(r13 / 'oracles.py', 'r14_original_oracles')


def check_outer(row, phase, argv, a):
    require(row['complete'] is True and row['exit_code'] == 0 and row['reason'] is None and
            row['cleanup'] is True and row['lock_reacquired'] is True and row['lease_cleared'] is True and
            row['standalone_admission'] is True and row['test_only'] is False, 'outer stage not clean/successful')
    require(row['command'] == argv and row['seconds'] == BUDGETS[phase] and
            row['locks'] == a['locks'] and row['epoch'] == a['epoch'] and row['cwd'] == a['source'] and
            row['output'] == str(HERE / phase.lower() / 'outer') and row['bounded_root'] == str(HERE),
            'outer identity mismatch')


def authenticate(O, source):
    producer = HERE / 'build/producer'
    auth = O.authenticate(producer, source)
    require(auth['orchestrator']['path'] == str(Path(sys.executable).resolve()), 'builder Python mismatch')
    require(len(auth['object_inputs']) == 284, 'expected complete 284 objects/interfaces')
    return auth


def verify_qualifier_scope(a, guard, path, digest):
    """Bind the two real ancestors: unchanged watchdog, then lock-owning guard."""
    folder = HERE / 'controls'
    cfg = folder / 'outer/guard-config.json'
    expected = {'command': command('CONTROLS', path, digest), 'cwd': a['source'],
        'output': str(folder / 'outer'), 'locks': a['locks'], 'epoch': a['epoch'],
        'seconds': 120, 'reports': [], 'test_mode': False, 'nested': False,
        'bounded_root': str(HERE), 'accepted_exit_codes': [0]}
    require(load(cfg) == expected, 'qualifier outer configuration mismatch')
    table = guard.process_table()
    watchdog = os.getppid()
    require(watchdog in table, 'missing watchdog parent')
    supervisor = table[watchdog]['ppid']
    require(supervisor in table, 'missing outer supervisor')
    starts = {pid: table[pid]['start'] for pid in [watchdog, supervisor]}
    def argv(pid):
        return (Path('/proc') / str(pid) / 'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
    require(argv(watchdog) == [v.encode() for v in expected['command']], 'wrong watchdog ancestry')
    require(argv(supervisor) == [str(Path(sys.executable).resolve()).encode(), b'-B',
            str(Path(a['r13']) / 'guard.py').encode(), str(cfg).encode()], 'wrong guard ancestry')
    require(Path(os.readlink('/proc/self/cwd')) == Path(a['source']), 'qualifier cwd differs')
    lease = load(guard.epoch_active_path(a['locks'], a['epoch']))
    require(lease == {'schema': 'sparse-scc-epoch-lease-v1', 'epoch': a['epoch'], 'locks': a['locks'],
        'supervisor_pid': supervisor, 'supervisor_start': starts[supervisor],
        'guard_config_sha256': sha(cfg), 'output': str(folder / 'outer')}, 'wrong active lease')
    owners = guard.lock_owners(Path('/proc/locks').read_text())
    for item in a['locks']:
        require((supervisor, item['device'], item['inode']) in owners, 'supervisor does not own lock')
    after = guard.process_table()
    require(os.getppid() == watchdog and all(after.get(pid, {}).get('start') == start
            for pid, start in starts.items()), 'ancestor identity changed')


def qualify(path, digest):
    a, env, guard, O = validate(path, digest, 'CONTROLS')
    require(dict(os.environ) == env, 'qualifier environment mismatch')
    folder = HERE / 'controls'
    claim = load(HERE / 'claims/CONTROLS.json')
    require(claim == {'phase': 'CONTROLS', 'admission': pin(path), 'retry_allowed': False}, 'qualifier claim mismatch')
    verify_qualifier_scope(a, guard, path, digest)
    record = {'schema': 'r14-ordinary-focused-controls-v1', 'complete': False, 'commands': [],
              'driver': pin(__file__), 'python': pin(Path(sys.executable).resolve()),
              'no_target_compilation': True, 'started': time.time()}
    destination = folder / 'focused-control-receipt.json'
    save(destination, record)
    try:
        source = Path(a['source'])
        auth = authenticate(O, source)
        producer = HERE / 'build/producer'
        record.update(producer_receipt=pin(producer / 'receipt.json'), full_object_inputs_verified=True,
                      object_inputs=auth['object_inputs'], outputs=auth['outputs'],
                      builtin_verification=auth['builtin_verification'])
        c_objects = []
        for label, relative in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            obj = producer / (label + '.o')
            expected = [auth['cc']['path'], '-O2', '-std=c11', '-I' + str(source / 'runtime'),
                        '-c', str(source / relative), '-o', str(obj)]
            rows = [r for r in auth['commands'] if Path(r['log']).name == 'c-' + label + '.log']
            require(len(rows) == 1 and rows[0]['argv'] == expected and rows[0]['exit_code'] == 0 and
                    rows[0]['cwd'] == str(source), 'original C command differs')
            require(sha(source / relative) == auth['host_inputs'][relative]['sha256'], 'C source differs')
            c_objects.append({'label': label, 'source': pin(source / relative), 'object': pin(obj),
                              'original_command': rows[0]})
        record['c_objects'] = c_objects
        save(destination, record)
        for label, arguments, status, expected_out, expected_err in CASES:
            argv = [auth['outputs']['emlf']['path'], *arguments]
            entry = {'label': label, 'argv': argv, 'cwd': str(source), 'passed': False}
            record['commands'].append(entry)
            save(destination, record)
            out, err = folder / (label + '.stdout'), folder / (label + '.stderr')
            with out.open('xb') as stdout, err.open('xb') as stderr:
                result = subprocess.run(argv, cwd=source, env=env, stdin=subprocess.DEVNULL,
                                        stdout=stdout, stderr=stderr)
            entry.update(exit_code=result.returncode, stdout=pin(out), stderr=pin(err))
            require(result.returncode == status and out.read_bytes() == expected_out and
                    err.read_bytes() == expected_err, 'focused semantic control failed: ' + label)
            entry['passed'] = True
            save(destination, record)
        authenticate(O, source)
        for item in c_objects:
            verify_pin(item['object'])
        # No historical workload.json is needed: use the reviewed frozen closure.
        spec = load(Path(a['r13']) / 'insertion-map.json')
        names = spec['emlf_modules']
        require(len(names) == len(set(names)) == 94, 'exact Emlf non-Main closure required')
        closure = [{'module': name, 'object': pin(producer / 'objects' / (name.replace('.', '/') + '.o')),
                    'interface': pin(producer / 'objects' / (name.replace('.', '/') + '.hi'))} for name in names]
        links = [r for r in auth['commands'] if Path(r['log']).name == 'link-emlf.log']
        require(len(links) == 1 and '-rtsopts=ignoreAll' in links[0]['argv'], 'original Emlf link missing')
        relink = {'complete': True, 'producer': str(producer), 'source': str(source), 'source_commit': BASE,
                  'producer_receipt': pin(producer / 'receipt.json'), 'non_main_count': 94,
                  'non_main_closure': closure, 'c_objects': c_objects, 'original_main': pin(source / 'host/ghc/app/emlf/Main.hs'),
                  'original_main_link_command': links[0], 'environment': env,
                  'main_object_warning': 'Final shared Main.o/Main.hi are not Emlf Main; compile distinct original Main for any future relink.',
                  'future_attribution_not_run': True}
        save(HERE / 'relink-inputs.json', relink)
        record['relink_inputs'] = pin(HERE / 'relink-inputs.json')
        validate(path, digest, 'CONTROLS')
        verify_qualifier_scope(a, guard, path, digest)
        record.update(complete=True, finished=time.time())
    except BaseException as error:
        record.update(error=repr(error), finished=time.time())
        raise
    finally:
        save(destination, record)
    print('PASS original producer authentication, 284 objects/interfaces, C inputs, and five focused CLI controls')


def launch(phase, path, digest):
    a, env, guard, O = validate(path, digest, phase)
    require(not os.path.lexists(guard.epoch_active_path(a['locks'], a['epoch'])) and
            not os.path.lexists(guard.epoch_quarantine_path(a['locks'], a['epoch'])), 'new batch epoch blocked')
    for name in ['claims']:
        (HERE / name).mkdir(mode=0o700, exist_ok=True)
    claim_path = HERE / 'claims' / (phase + '.json')
    with claim_path.open('x') as stream:
        json.dump({'phase': phase, 'admission': pin(path), 'retry_allowed': False}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    folder = HERE / phase.lower()
    folder.mkdir(mode=0o700, exist_ok=False)
    argv = command(phase, path, digest)
    record = {'schema': 'r14-ordinary-controller-v1', 'complete': False, 'phase': phase,
              'command': argv, 'source': a['source'], 'epoch': a['epoch'], 'locks': a['locks'],
              'environment': a['environment'], 'adapter_code_pins': a['adapter_code_pins'],
              'source_pins': a['source_pins'], 'toolchain_files': a['toolchain_files'],
              'toolchain_evidence': a['toolchain_evidence'], 'admission': pin(path),
              'budget_seconds': BUDGETS[phase], 'started': time.time()}
    output = folder / 'controller.json'
    save(output, record)
    try:
        os.environ.clear()
        os.environ.update(env)
        row = guard.run_guard(argv, cwd=Path(a['source']), output=folder / 'outer',
                              locks=a['locks'], epoch=a['epoch'], seconds=BUDGETS[phase], bounded_root=HERE)
        if (folder / 'outer/guard.json').is_file():
            record['outer'] = pin(folder / 'outer/guard.json')
        check_outer(row, phase, argv, a)
        watchdog = load(folder / 'bounded-receipt.json')
        require(watchdog['complete'] is True and watchdog['exit_code'] == 0 and watchdog['reason'] is None
                and watchdog['command'] == inner_command(phase, path, digest)
                and watchdog['samples'] and watchdog['samples'][-1]['group_rss'] == 0,
                'original watchdog did not complete cleanly')
        record['original_watchdog'] = pin(folder / 'bounded-receipt.json')
        validate(path, digest, phase)
        if phase == 'BUILD':
            authenticate(O, Path(a['source']))
            record['producer_receipt'] = pin(HERE / 'build/producer/receipt.json')
        else:
            result = load(folder / 'focused-control-receipt.json')
            require(result['complete'] is True, 'focused controls incomplete')
            record['controls'] = pin(folder / 'focused-control-receipt.json')
        record.update(complete=True, finished=time.time())
        save(output, record)
        if phase == 'CONTROLS':
            # Only real completed paths/hashes are emitted, never synthetic receipts.
            handoff = {'producer': str(HERE / 'build/producer'),
                'receipt': pin(HERE / 'build/producer/receipt.json'),
                'build_outer': pin(HERE / 'build/outer/guard.json'),
                'build_controller': pin(HERE / 'build/controller.json'),
                'controls': pin(folder / 'focused-control-receipt.json'),
                'controls_outer': pin(folder / 'outer/guard.json'),
                'controls_controller': pin(output), 'environment': a['environment'],
                'relink': pin(HERE / 'relink-inputs.json')}
            save(HERE / 'ordinary-handoff.json', handoff)
        return record
    except BaseException as error:
        record.update(complete=False, error=repr(error), finished=time.time())
        save(output, record)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run')
    run.add_argument('phase', choices=list(BUDGETS))
    worker = sub.add_parser('_qualify')
    for entry in [run, worker]:
        entry.add_argument('--admission', type=Path, required=True)
        entry.add_argument('--sha256', required=True)
    a = parser.parse_args()
    if a.command == '_qualify':
        qualify(a.admission, a.sha256)
    else:
        print(json.dumps(launch(a.phase, a.admission, a.sha256), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
