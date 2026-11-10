#!/usr/bin/env python3
"""Private P1 review candidate. Never invoke before review and scheduling approval."""
from pathlib import Path
import argparse
import errno
import fcntl
import hashlib
import json
import os
import re
import sys
import threading
import time
import types

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'compiler-baseline-20261110'
SOURCE_COMMIT = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
PRODUCER_SHA = 'b71bbb5ebb757a206ed41932cdafca982f1e7246218496953be273afad5a8caf'
SETUP_SHA = 'a7073db2aeb7b3c9232201e1bb60322edeece95eff542940b7bdb280d83b5cf8'
WORKLOAD_SHA = 'db93d2deffdb38c524636218a6a85dcb7f40dd63c39dd4fe07a50191a2206f9a'


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): result.update(block)
    return result.hexdigest()


def load(path): return json.loads(Path(path).read_text())
def pack(values): return ''.join(str(len(value)) + ':' + value for value in values)
def pins(paths): return {str(Path(path).resolve()): sha(path) for path in paths}
def check(values):
    for path, digest in values.items():
        if sha(path) != digest: raise ValueError('changed pinned input: ' + path)


def process(identity):
    try:
        fields = Path('/proc', str(identity['pid']), 'stat').read_text().split(') ', 1)[1].split()
        return fields[19] == str(identity['start_ticks']) and fields[0] != 'Z'
    except FileNotFoundError: return False


def ancestry(identity, ancestor):
    # The real supervisor uses Main -> guard task -> setsid child. Do not assume
    # the executable is Main's direct child or shares Main's process group.
    chain = []; current = identity['pid']
    try:
        for unused in range(8):
            fields = Path('/proc', str(current), 'stat').read_text().split(') ', 1)[1].split()
            item = {'pid': current, 'start_ticks': fields[19], 'parent_pid': int(fields[1]),
                    'process_group': int(fields[2]), 'session': int(fields[3])}
            if fields[0] == 'Z': return None
            if not chain and item['start_ticks'] != str(identity['start_ticks']): return None
            chain.append(item)
            if current == ancestor['pid']:
                return chain if item['start_ticks'] == str(ancestor['start_ticks']) else None
            current = item['parent_pid']
    except FileNotFoundError: pass
    return None


def lock_available(path):
    # The host uses fcntl F_SETLKW, not flock. Do not create the evidence file.
    with Path(path).open('r+b') as stream:
        try: fcntl.lockf(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN): return False
            raise
        fcntl.lockf(stream, fcntl.LOCK_UN)
        return True


class Observer:
    def __init__(self, lock=None, child=None):
        self.lock, self.child = lock, child
        self.stop = threading.Event(); self.held = False; self.identity = None; self.error = None
        self.main_path = None; self.main_identity = None; self.lock_evidence = None; self.child_chain = None
    def start(self):
        def observe():
            try:
                while not self.stop.wait(0.005):
                    if self.main_path and self.main_path.is_file():
                        identity = load(self.main_path)
                        if process(identity): self.main_identity = identity
                    if self.main_identity and self.lock and Path(self.lock).is_file() and not lock_available(self.lock):
                        info = Path(self.lock).stat()
                        for line in Path('/proc/locks').read_text().splitlines():
                            fields = line.split()
                            if len(fields) < 8 or fields[1:4] != ['POSIX', 'ADVISORY', 'WRITE']: continue
                            device = fields[5].split(':')
                            if int(fields[4]) == self.main_identity['pid'] and len(device) == 3 and (
                                int(device[0], 16), int(device[1], 16), int(device[2])) == (
                                    os.major(info.st_dev), os.minor(info.st_dev), info.st_ino):
                                self.held = True; self.lock_evidence = line
                    if self.main_identity and self.child and Path(self.child).is_file():
                        identity = load(self.child)
                        chain = ancestry(identity, self.main_identity)
                        if chain:
                            self.identity = identity; self.child_chain = chain
            except BaseException as error: self.error = repr(error)
        self.thread = threading.Thread(target=observe, daemon=True); self.thread.start()
    def finish(self):
        self.stop.set(); self.thread.join()
        if self.error: raise ValueError('independent observer failed: ' + self.error)
        return {'lock_observed_held': self.held, 'lock_kernel_evidence': self.lock_evidence,
                'main_identity': self.main_identity, 'active_child_identity': self.identity,
                'active_child_to_main_ancestry': self.child_chain}


def profile(folder, outcome, code):
    result = load(folder / 'outcome.json')
    if (result.get('outcome'), result.get('exit_code')) != (outcome, code):
        raise ValueError('exit/outcome mismatch; exit 124 alone is not timeout evidence')
    if result.get('diagnostic_only') is not True or result.get('ordinary_endpoint') is not False:
        raise ValueError('missing diagnostic boundary')
    if outcome == 'internal-timeout' and result.get('compiler_action_complete') is not False:
        raise ValueError('timeout labeled complete')
    if outcome == 'compiler-returned' and result.get('compiler_action_complete') is not True:
        raise ValueError('normal return not labeled complete')
    path = folder / 'cost-centres.prof'; report = load(path)
    centres = report.get('cost_centres'); tree = report.get('profile'); ticks = report.get('total_ticks')
    if not isinstance(centres, list) or not centres or not isinstance(tree, dict) or type(ticks) is not int or ticks <= 0:
        raise ValueError('missing nonzero samples or cost-centre structure')
    if any(type(row.get('id')) is not int or not isinstance(row.get('label'), str) for row in centres):
        raise ValueError('invalid cost-centre metadata')
    ids = {row['id'] for row in centres}; pending = [tree]; sampled = 0
    if len(ids) != len(centres): raise ValueError('duplicate cost-centre IDs')
    while pending:
        node = pending.pop()
        if node.get('id') not in ids or type(node.get('ticks')) is not int or node['ticks'] < 0 or not isinstance(node.get('children'), list):
            raise ValueError('invalid cost-centre tree')
        sampled += node['ticks']; pending.extend(node['children'])
    if sampled <= 0: raise ValueError('no attributed sampling')
    return {'outcome': result, 'profile_sha256': sha(path), 'total_ticks': ticks, 'attributed_ticks': sampled}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=['build', 'controls', 'target'])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--build', type=Path)
    p.add_argument('--controls', type=Path)
    a = p.parse_args(); out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic(); budget = {'build': 600, 'controls': 60, 'target': 120}[a.phase]
    helper = BASE / 'tools/performance/a1-private-index/helper.py'
    scope = BASE / 'tools/performance/process-spawn/with_scope.py'
    watchdog = BASE / 'tools/shared/resource_watchdog.py'
    H = types.ModuleType('retained_guard'); H.__file__ = str(helper)
    exec(compile(helper.read_bytes(), str(helper), 'exec'), H.__dict__)
    producer = BASE / '.mlf-build/baseline-producer'
    setup_path = BASE / '.mlf-build/baseline-setup/setup.json'
    workload_path = HERE.parent / 'compiler-baseline-evidence-20261110/workload.json'
    record = {'complete': False, 'diagnostic_only': True, 'ordinary_performance_sample': False,
              'source_commit': SOURCE_COMMIT, 'phase': a.phase, 'budget_seconds': budget, 'commands': []}
    save = lambda: H.save(out / 'receipt.json', record)
    save(); environment = dict(os.environ)
    def remaining():
        seconds = budget - (time.monotonic() - started)
        if seconds <= 0: raise TimeoutError('shared phase budget exhausted')
        return seconds
    def run(label, argv, code=0, mode='target', inner=None, observer=None, hard_kill=False, allow_early_success=False):
        os.environ.clear(); os.environ.update(environment)
        for key in list(os.environ):
            if key.startswith('MLF_DIAGNOSTIC_') or key.startswith('MLF_COST_CENTRE_') or key in (
                    'MLF_QUERY_PROFILE', 'MLF_QUERY_SEMANTIC_AUDIT', 'MLF_QUERY_FAILPOINT'):
                del os.environ[key]
        folder = out / label
        if inner is not None:
            os.environ.update(MLF_COST_CENTRE_MODE=mode, MLF_COST_CENTRE_TIMEOUT_MS=str(inner),
                              MLF_COST_CENTRE_OUTCOME=str(folder / 'outcome.json'),
                              MLF_COST_CENTRE_PYTHON=sys.executable,
                              MLF_COST_CENTRE_CHILD=str(HERE / 'owned_child.py'),
                              MLF_COST_CENTRE_CHILD_IDENTITY=str(folder / 'child-identity.json'))
            argv = [*argv, '+RTS', '-pj', '-po' + str(folder / 'cost-centres'), '-RTS']
        wall = min(remaining(), 15) if a.phase == 'controls' else remaining()
        if hard_kill: wall = min(wall, 1)
        limits = dict(address_space_per_process_bytes=6*1024**3, process_tree_rss_bytes=5*1024**3,
                      host_available_floor_bytes=3*1024**3, disk_free_floor_bytes=5*1024**3,
                      max_work_bytes=4*1024**3, wall_seconds=wall)
        if observer:
            observer.main_path = folder / 'outcome.json.process.json'; observer.start()
        failed = None
        try:
            result = H.Runner(out, limits).run([sys.executable, '-B', scope, *argv], BASE, folder, expected_exit=code)
        except RuntimeError as error:
            failed = error
            result = load(folder / 'command.json')
            if hard_kill:
                if result.get('reason') != 'wall limit' or result.get('complete') is not False: raise
            elif allow_early_success and result.get('exit_code') == 0 and not result.get('reason') and not result.get('terminal_live_descendants'):
                # Preserve the unchanged Runner's expected-124 failure receipt.
                # Only this explicit real-target alternative is admissible.
                pass
            else: raise
        finally:
            observations = observer.finish() if observer else None
        if hard_kill and failed is None: raise ValueError('hard-guard control did not reach guard')
        row = {'label': label, 'resource': result, 'observer': observations,
               'diagnostic_environment': {key: value for key, value in H.env().items()
                   if key.startswith('MLF_COST_CENTRE_') or key in ('GHC_ENVIRONMENT', 'GHCRTS')},
               'cleared_environment': ['MLF_QUERY_PROFILE', 'MLF_QUERY_SEMANTIC_AUDIT', 'MLF_QUERY_FAILPOINT', 'MLF_DIAGNOSTIC_*']}
        record['commands'].append(row); save()
        return folder, row
    def spec(path, module, source, identity, cache):
        cache.mkdir()
        path.write_text(pack(['MLF-CRATE-1', identity, module, 'false',
                             pack([pack([module, str(source)])]), pack([setup['builtin'] + '.mlfci']),
                             str(cache), setup['builtin']]))
    try:
        with H.SerialLock(BASE / '.mlf-build'):
            check({str(producer / 'receipt.json'): PRODUCER_SHA, str(setup_path): SETUP_SHA,
                   str(workload_path): WORKLOAD_SHA})
            auth = H.authenticate(producer, BASE); setup = load(setup_path); workload = load(workload_path)
            if workload['module_count'] != 90: raise ValueError('wrong frozen target')
            inputs = {**workload['input_files'], **pins([Path(__file__), HERE / 'ProfileMain.hs',
                       HERE / 'owned_child.py', HERE / 'run-phase.sh', helper, scope, watchdog,
                       setup_path, workload_path, producer / 'receipt.json'])}
            inputs.update(pins((BASE / 'runtime').glob('*.h')))
            inputs.update(pins((BASE / 'host/ghc').rglob('*.hs')))
            inputs.update(pins([BASE / 'host/ghc/cbits/host.c', BASE / 'runtime/mlf_process_supervisor.c']))
            # Ordinary authentication already pins installed archives, including
            # _p.a. Add profiling interfaces used by the same installed closure.
            prof_interfaces = [Path(path).with_suffix('.p_hi') for path in auth['installed_dependencies']['files']
                               if path.endswith('.hi') and not path.endswith('.dyn_hi')]
            inputs.update(pins(path for path in prof_interfaces if path.is_file()))
            inputs.update({path: digest for path, digest in setup['builtin_record'].items() if path.startswith('/')})
            check(inputs)
            record['inputs'] = inputs; save()
            if a.phase == 'build':
                objects = out / 'objects'; objects.mkdir()
                c_objects = []
                for label, source in [('host', BASE / 'host/ghc/cbits/host.c'), ('supervisor', BASE / 'runtime/mlf_process_supervisor.c')]:
                    obj = out / (label + '.o')
                    run('c-' + label, [auth['cc']['path'], '-O2', '-std=c11', '-I' + str(BASE / 'runtime'), '-c', source, '-o', obj])
                    c_objects.append(obj)
                flags = list(auth['flags'])
                for option in ['-odir', '-hidir']: flags[flags.index(option) + 1] = str(objects)
                if any(flag not in flags for flag in ['-O2', '-fpedantic-bottoms', '-fno-state-hack']):
                    raise ValueError('ordinary flags missing')
                binary = out / 'emlf-profile'
                folder, _ = run('ghc-profile', [auth['ghc']['path'], '--make', '-j1', '-fforce-recomp', '-v',
                                 *flags, '-prof', '-fprof-late', '-rtsopts', HERE / 'ProfileMain.hs', *c_objects, '-o', binary])
                log = (folder / 'stdout').read_text() + '\n' + (folder / 'stderr').read_text()
                actual = re.findall(r'Compiling\s+([\w.]+)\s+\(\s*([^,\n]+),', log)
                expected = {row['module']: row['source'] for row in workload['modules']}
                expected.update({name: str(BASE / relative) for name, relative in {
                    'MLF.Primitive': 'host/ghc/MLF/Primitive.hs', 'MLF.Host.Base': 'host/ghc/MLF/Host/Base.hs',
                    'MLF.Host.IO': 'host/ghc/MLF/Host/IO.hs', 'MLF.Host.Async': 'host/ghc/MLF/Host/Async.hs'}.items()})
                expected['Main'] = str(HERE / 'ProfileMain.hs')
                resolved = [(name, str((BASE / path.strip()).resolve())) for name, path in actual]
                if len(actual) != 95 or dict(resolved) != expected: raise ValueError('not exactly 95 fresh pinned home modules')
                record.update(binary=str(binary), output_pins=pins([binary, *c_objects, *objects.rglob('*.o'), *objects.rglob('*.hi')]),
                              compiled=resolved, compiler_flags=flags + ['-prof', '-fprof-late', '-rtsopts'])
            else:
                if a.build is None: raise ValueError('--build receipt directory required')
                build = load(a.build / 'receipt.json')
                build_guard = a.build.parent / 'bounded-receipt.json'
                if build.get('complete') is not True or build.get('phase') != 'build' or load(build_guard).get('complete') is not True:
                    raise ValueError('profiling build/controller outer guard not qualified')
                check(build['inputs']); check(build['output_pins'])
                if build['inputs'] != inputs: raise ValueError('build/current input identities disagree')
                binary = Path(build['binary']); record['build_receipt_sha256'] = sha(a.build / 'receipt.json')
                record['build_guard_sha256'] = sha(build_guard)
                if a.phase == 'controls':
                    tiny = out / 'Tiny.emlf'; tiny.write_text('module Tiny where\nmain = printInt (40 + 2)\n')
                    prefixes = []
                    for side in ['ordinary', 'profiled']:
                        prefix = out / ('tiny-' + side); declaration = out / ('tiny-' + side + '.spec')
                        spec(declaration, 'Tiny', tiny, 'p1/tiny', out / ('cache-' + side))
                        compiler = producer / 'bin/emlf' if side == 'ordinary' else binary
                        folder, row = run('tiny-' + side, [compiler, '--compile-crate', declaration, '-o', prefix],
                                          inner=10000 if side == 'profiled' else None)
                        if side == 'profiled': row['profile'] = profile(folder, 'compiler-returned', 0); save()
                        q = load(str(prefix) + '.queries')
                        if q['reused_groups'] != 0 or q['inferred_groups'] != len(q['groups']) or not q['groups'] or any(g['cached'] for g in q['groups']):
                            raise ValueError('tiny target not freshly inferred')
                        prefixes.append(prefix)
                    for suffix in ['.mlfci', '.mlfco']:
                        if Path(str(prefixes[0]) + suffix).read_bytes() != Path(str(prefixes[1]) + suffix).read_bytes():
                            raise ValueError('tiny ordinary/profiled checked bytes differ')
                    groups = [[{k:g[k] for k in ['id','members']} for g in load(str(prefix) + '.queries')['groups']] for prefix in prefixes]
                    if groups[0] != groups[1]: raise ValueError('tiny ordered groups differ')
                    folder, row = run('alloc-timeout', [binary], code=124, mode='allocate', inner=1000)
                    row['profile'] = profile(folder, 'internal-timeout', 124); save()
                    large = out / 'LockCase.emlf'
                    large.write_text('module LockCase where\nidentity x = x\n' + ''.join('value'+str(n)+' = identity '+str(n)+'\n' for n in range(512)) + 'main = printInt value511\n')
                    declaration = out / 'lock.spec'; cache = out / 'lock-cache'; spec(declaration, 'LockCase', large, 'p1/lock', cache)
                    observer = Observer(lock=cache / '.lock')
                    folder, row = run('compiler-lock', [binary, '--compile-crate', declaration, '-o', out / 'partial'],
                                      code=124, inner=2000, observer=observer)
                    row['profile'] = profile(folder, 'internal-timeout', 124)
                    if not observer.held or not lock_available(cache / '.lock') or process(observer.main_identity):
                        raise ValueError('compiler lock was not owned by live Main then independently reacquired after its exit')
                    row['lock_reacquired'] = True; save()
                    observer = Observer(child=out / 'active-child/child-identity.json')
                    folder, row = run('active-child', [binary], code=124, mode='active-child', inner=2000, observer=observer)
                    row['profile'] = profile(folder, 'internal-timeout', 124)
                    if observer.identity is None or any(process(item) for item in observer.child_chain):
                        raise ValueError('active child/main identity cleanup not proved')
                    row['child_identity_gone'] = True; save()
                    folder, row = run('not-a-timeout', [binary], code=124, mode='exit-124', inner=1000)
                    outcome = load(folder / 'outcome.json')
                    if outcome.get('outcome') != 'compiler-exit-failure': raise ValueError('ordinary exit124 misclassified')
                    try: profile(folder, 'internal-timeout', 124)
                    except ValueError: row['false_timeout_rejected'] = True
                    else: raise ValueError('exit124 accepted without timeout outcome')
                    save()
                    folder, row = run('hard-kill', [binary], mode='allocate', inner=90000, hard_kill=True)
                    try: profile(folder, 'internal-timeout', 124)
                    except (ValueError, FileNotFoundError, json.JSONDecodeError): row['missing_or_invalid_report_rejected'] = True
                    else: raise ValueError('hard-killed run accepted as a valid profile')
                    if row['resource'].get('terminal_live_descendants'): raise ValueError('hard-kill left live descendants')
                    record['passed'] = ['normal_crate_bytes', 'internal_timeout_report', 'compiler_lock_observed_held_then_released',
                                        'active_child_identity_gone', 'ordinary_exit124_rejected', 'hard_guard_missing_report_rejected']
                else:
                    if a.controls is None: raise ValueError('--controls receipt required')
                    controls = load(a.controls / 'receipt.json')
                    control_guard = a.controls.parent / 'bounded-receipt.json'
                    required = {'normal_crate_bytes', 'internal_timeout_report', 'compiler_lock_observed_held_then_released',
                                'active_child_identity_gone', 'ordinary_exit124_rejected', 'hard_guard_missing_report_rejected'}
                    if controls.get('complete') is not True or load(control_guard).get('complete') is not True or set(controls.get('passed', [])) != required or controls['build_receipt_sha256'] != sha(a.build / 'receipt.json'):
                        raise ValueError('controls do not admit this exact build')
                    check(controls['inputs']); record['control_receipt_sha256'] = sha(a.controls / 'receipt.json')
                    record['control_guard_sha256'] = sha(control_guard)
                    if remaining() < 105: raise ValueError('insufficient remaining outer budget for the fixed 90s target and shutdown')
                    # A scheduling decision authorizes one real attempt, not an
                    # automatic retry with another fresh output directory.
                    with (a.build / 'real-target-claim.json').open('x') as claim:
                        json.dump({'output': str(out), 'controller_sha256': sha(__file__)}, claim)
                    cache = out / 'queries'; cache.mkdir(); declaration = out / 'crate.spec'
                    declaration.write_text(pack(['MLF-CRATE-1', 'full-compiler/current', workload['entry'], 'false',
                        pack([pack([row['module'], row['source']]) for row in sorted(workload['modules'], key=lambda row: row['module'])]),
                        pack([setup['builtin'] + '.mlfci']), str(cache), setup['builtin']]))
                    # The bounded prefix is expected to time out. An unexpectedly
                    # successful complete action is retained but not substituted.
                    folder, row = run('target', [binary, '--compile-crate', declaration, '-o', out / 'unit'],
                                      code=124, inner=90000, allow_early_success=True)
                    actual_exit = row['resource']['exit_code']
                    label = 'internal-timeout' if actual_exit == 124 else 'compiler-returned'
                    row['profile'] = profile(folder, label, actual_exit)
            check(inputs)
            if H.authenticate(producer, BASE) != auth: raise ValueError('ordinary producer changed')
            if a.phase != 'build': check(build['output_pins'])
            remaining(); record.update(complete=True, elapsed_seconds=time.monotonic() - started); save()
    except BaseException as error:
        record.update(error=repr(error), elapsed_seconds=time.monotonic() - started); save(); raise
    finally:
        os.environ.clear(); os.environ.update(environment)


if __name__ == '__main__': main()
