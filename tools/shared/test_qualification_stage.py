#!/usr/bin/env python3
"""Ten isolated synthetic owner cases plus strict ledger controls.
Not production phase qualification or real root-installer qualification.
No compiler, package installer, interpreter or workload is executed. A second
pinned supervisor contains the synthetic controller, including its descendants.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
STAGE_BLOB = 'b6c4e56077af757b6a423cb0b254a2c9948209d9'
SUPERVISOR_BLOB = '620e88b557139a6b19ca63097decaa9148bdd819'

def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

class QualificationStageControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != 'linux' or os.geteuid() == 0:
            raise RuntimeError('synthetic controls require an unprivileged Linux test owner')
        if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
            raise RuntimeError('real pidfd support required; no skipped lifecycle tests')
        cls.stage = HERE / 'qualification_stage.py'
        cls.supervisor = HERE / 'crc_process_supervisor.py'
        cls.stage_raw = cls.stage.read_bytes()
        cls.supervisor_raw = cls.supervisor.read_bytes()
        if blob(cls.stage_raw) != STAGE_BLOB or blob(cls.supervisor_raw) != SUPERVISOR_BLOB:
            raise RuntimeError('exact reviewed controller/supervisor source required')
        configured = os.environ.get('QUALIFICATION_SYNTHETIC_OUTPUT')
        cls.persistent = bool(configured)
        if configured:
            cls.output = Path(configured).resolve()
            if os.path.lexists(configured) or os.path.lexists(cls.output):
                raise RuntimeError('fresh synthetic evidence directory required')
            cls.output.mkdir(parents=True, exist_ok=False)
        else:
            cls.output = Path(tempfile.mkdtemp(prefix='qualification-stage-synthetic-'))
        cls.blocked = False
        cls.failures = False
        save(cls.output / 'scope.json', {
            'scope': 'synthetic controller tests only; not production 120/625-second qualification',
            'stage_git_blob': STAGE_BLOB, 'supervisor_git_blob': SUPERVISOR_BLOB,
            'cases': ['success', 'nested-timeout', 'cancel', 'root-exit-orphan', 'missing-executable', 'uid-boundary',
                      'install-adopted-zero', 'install-adopted-nonzero', 'pure-adopted-zero', 'install-live-orphan'],
            'install_branch_cases': 'test-only UID stub; processes actually remain unprivileged',
            'outer_work_seconds': 12, 'outer_cleanup_seconds': 2,
            'test_stage_grace_seconds': .3, 'test_stage_cleanup_seconds': 2,
            'normal_and_optimized_runs_require_distinct_output_directories': True})

    @classmethod
    def tearDownClass(cls):
        if not cls.persistent and not cls.blocked and not cls.failures:
            shutil.rmtree(cls.output)
        else:
            print('Retained synthetic evidence: ' + str(cls.output), file=sys.stderr)

    def run_case(self, name):
        if self.blocked:
            raise RuntimeError('prior cleanup uncertified; refusing another synthetic child')
        case = self.output / name
        case.mkdir(exist_ok=False)
        ready = case / 'readiness.json'
        target = case / 'target.py'
        if name in ('nested-timeout', 'cancel', 'root-exit-orphan', 'install-live-orphan'):
            target_text = """import json,os,signal,time
from pathlib import Path
controller_fd=os.pidfd_open(os.getppid())
r,w=os.pipe()
pid=os.fork()
if pid==0:
    os.close(controller_fd)
    os.close(r)
    os.setsid()
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    os.write(w,b'R')
    os.close(w)
    while True: time.sleep(1)
os.close(w)
if os.read(r,1)!=b'R': raise RuntimeError('nested child readiness')
os.close(r)
Path(READY).write_text(json.dumps({'root_pid':os.getpid(),'child_pid':pid}))
if MODE=='cancel':
    signal.pidfd_send_signal(controller_fd,signal.SIGTERM)
os.close(controller_fd)
if MODE in ('root-exit-orphan','install-live-orphan'):
    raise SystemExit(0)
while True: time.sleep(1)
"""
            target_text = 'READY=' + repr(str(ready)) + '\nMODE=' + repr(name) + '\n' + target_text
        elif name in ('install-adopted-zero', 'install-adopted-nonzero', 'pure-adopted-zero'):
            target_text = """import json,os
from pathlib import Path
pid=os.fork()
if pid==0:
    os.setsid()
    os._exit(CHILD_STATUS)
# Observe the exited child without reaping it: the controller must perform
# actual subreaper adoption and its own waitpid, not accept a forged ledger.
info=os.waitid(os.P_PID,pid,os.WEXITED|os.WNOWAIT)
if info.si_pid!=pid or info.si_code!=os.CLD_EXITED or info.si_status!=CHILD_STATUS:
    raise RuntimeError('natural child exit readiness')
Path(READY).write_text(json.dumps({'root_pid':os.getpid(),'child_pid':pid}))
os._exit(0)
"""
            target_text = ('READY=' + repr(str(ready)) + '\nCHILD_STATUS=' +
                           repr(7 if name == 'install-adopted-nonzero' else 0) + '\n' + target_text)
        else:
            target_text = "print('synthetic stage success',flush=True)\n"
        target.write_text(target_text)
        command = [sys.executable, '-B', str(target)]
        if name == 'missing-executable':
            command = [str(case / 'absent-executable')]
        work = .8 if name == 'nested-timeout' else 3
        config = {
            'stage': str(self.stage), 'stage_blob': STAGE_BLOB,
            'budget': work, 'uid_boundary': name == 'uid-boundary',
            'install_uid_stub': name.startswith('install-'),
            'phase': 'install' if name.startswith('install-') else 'pure',
            'argv': ['qualification_stage.py', '--phase', 'install' if name.startswith('install-') else 'pure', '--output',
                     str(case / 'stage'), '--supervisor', str(self.supervisor), '--', *command]}
        save(case / 'test-config.json', config)
        harness = case / 'harness.py'
        harness.write_text("""import hashlib,json,sys,types
from pathlib import Path
config=json.loads(Path(sys.argv[1]).read_text())
path=Path(config['stage'])
raw=path.read_bytes()
actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\\0'+raw).hexdigest()
if actual!=config['stage_blob']: raise RuntimeError('controller source changed')
module=types.ModuleType('synthetic_qualification_owner')
module.__file__=str(path)
exec(compile(raw,str(path),'exec'),module.__dict__)
# Test-only in-memory budgets. No production CLI override exists.
module.PHASES=dict(module.PHASES)
module.PHASES[config['phase']]=config['budget']
module.GRACE=.3
module.CLEANUP=2
if config['uid_boundary'] or config['install_uid_stub']:
    # Test-only stub: no privilege escalation or package installation.
    module.os.geteuid=lambda:0
sys.argv=config['argv']
raise SystemExit(module.main())
""")
        guard = case / 'outer-supervisor.json'
        argv = [sys.executable, '-B', str(self.supervisor), '--receipt', str(guard),
                '--work-seconds', '12', '--cleanup-seconds', '2',
                sys.executable, '-B', str(harness), str(case / 'test-config.json')]
        save(case / 'execution.json', {'argv': argv, 'kind': 'actual synthetic subprocess'})
        process = None
        fd = None
        stdout = stderr = b''
        evidence = {'complete': False, 'cleanup_certified': False}
        try:
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            fd = os.pidfd_open(process.pid)
            try:
                stdout, stderr = process.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                evidence['test_outer_timeout'] = True
                try:
                    signal.pidfd_send_signal(fd, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    stdout, stderr = process.communicate(timeout=6)
                except subprocess.TimeoutExpired as error:
                    evidence['cleanup_unverified'] = 'outer guard did not finish; no broad descendant signalling'
                    self.__class__.blocked = True
                    try:
                        signal.pidfd_send_signal(fd, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        stdout, stderr = process.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        stdout, stderr = error.stdout or b'', error.stderr or b''
                        process.stdout.close()
                        process.stderr.close()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            evidence['leader_reap_unverified'] = True
                raise RuntimeError('synthetic outer deadline; not a passing cleanup case')
            outer = json.loads(guard.read_text())
            evidence['outer'] = outer
            if outer.get('cleanup_complete') is not True or outer.get('survivors') != []:
                self.__class__.blocked = True
                raise RuntimeError('synthetic outer cleanup is not certified')
            evidence['cleanup_certified'] = True
            self.assertEqual(outer['phase'], 'terminal')
            self.assertEqual(outer['reason'], 'target exited')
            self.assertEqual(outer['signals'], [])
            self.assertEqual(outer['cancel_signals'], [])
            self.assertEqual(len(outer['reaped']), 1)
            self.assertEqual(outer['reaped'][0]['pid'], outer['root_pid'])
            stage = json.loads((case / 'stage/receipt.json').read_text())
            evidence['stage'] = stage
            evidence['synthetic_install_uid_stub'] = config['install_uid_stub']
            self.assertEqual(stage['state'], 'terminal')
            self.assertEqual(stage['work_seconds'], work)
            self.assertEqual(stage['root_notification_grace_seconds'], .3)
            self.assertEqual(stage['cleanup_seconds'], 2)
            self.assertEqual(blob(self.stage.read_bytes()), STAGE_BLOB)
            self.assertEqual(blob(self.supervisor.read_bytes()), SUPERVISOR_BLOB)
            if name in ('missing-executable', 'uid-boundary'):
                self.assertEqual(process.returncode, 1)
                self.assertFalse(stage['complete'])
                self.assertEqual(stage['commands_started'], 0)
                self.assertNotIn('root_pid', stage)
                self.assertFalse(stage['cleanup']['cleanup_complete'])
                self.assertIn('ownership not admitted', stage['cleanup']['reason'])
                wanted = 'command executable unavailable' if name == 'missing-executable' else 'install owner must be root'
                self.assertIn(wanted, stage['error'])
            else:
                cleanup = stage['cleanup']
                self.assertTrue(cleanup['cleanup_complete'])
                self.assertEqual(cleanup['survivors'], [])
                self.assertTrue(stage['ownership_admitted_after_ECHILD'])
                if name == 'success':
                    self.assertEqual(process.returncode, 0)
                    self.assertTrue(stage['complete'])
                    self.assertEqual(cleanup['target_exit_code'], 0)
                    self.assertEqual(cleanup['signals'], [])
                    self.assertEqual(len(cleanup['reaped']), 1)
                    self.assertEqual((case / 'stage/stdout').read_bytes(), b'synthetic stage success\n')
                    self.assertEqual((case / 'stage/stderr').read_bytes(), b'')
                elif name in ('install-adopted-zero', 'install-adopted-nonzero', 'pure-adopted-zero'):
                    readiness = json.loads(ready.read_text())
                    self.assertEqual(stage['root_pid'], readiness['root_pid'])
                    self.assertEqual(stage['reason'], 'root exited')
                    self.assertEqual(cleanup['signals'], [])
                    self.assertEqual(cleanup['target_exit_code'], 0)
                    self.assertEqual(stage['cancel_signals'], [])
                    self.assertNotIn('root_notifications', stage)
                    self.assertEqual(len(cleanup['reaped']), 2)
                    reaped = {row['pid']: row['status'] for row in cleanup['reaped']}
                    self.assertEqual(reaped, {readiness['root_pid']: 0, readiness['child_pid']:
                                              7 if name == 'install-adopted-nonzero' else 0})
                    accepted = name == 'install-adopted-zero'
                    self.assertIs(stage['complete'], accepted)
                    self.assertEqual(process.returncode, 0 if accepted else 1)
                    self.assertEqual((case / 'stage/stdout').read_bytes(), b'')
                    self.assertEqual((case / 'stage/stderr').read_bytes(), b'')
                else:
                    readiness = json.loads(ready.read_text())
                    self.assertEqual(stage['root_pid'], readiness['root_pid'])
                    self.assertIs(type(readiness['child_pid']), int)
                    reaped = {row['pid']: row['status'] for row in cleanup['reaped']}
                    self.assertEqual(set(reaped), {readiness['root_pid'], readiness['child_pid']})
                    self.assertEqual(reaped[readiness['child_pid']], -signal.SIGKILL)
                    sent = {(row['pid'], row['signal']) for row in cleanup['signals']}
                    self.assertIn((readiness['child_pid'], signal.SIGTERM), sent)
                    self.assertIn((readiness['child_pid'], signal.SIGKILL), sent)
                    self.assertFalse(stage['complete'])
                    self.assertEqual(process.returncode, 1)
                    if name in ('root-exit-orphan', 'install-live-orphan'):
                        self.assertEqual(stage['reason'], 'root exited')
                        self.assertEqual(reaped[readiness['root_pid']], 0)
                        self.assertNotIn('root_notifications', stage)
                    else:
                        self.assertEqual(stage['reason'], 'cancelled' if name == 'cancel' else 'work deadline')
                        self.assertEqual(stage['root_notifications'],
                                         [{'pid': readiness['root_pid'], 'signal': int(signal.SIGTERM)}])
                        if name == 'cancel':
                            self.assertIn(signal.SIGTERM, stage['cancel_signals'])
                        else:
                            self.assertEqual(stage['cancel_signals'], [])
            evidence['complete'] = True
        except BaseException as error:
            self.__class__.failures = True
            evidence['error'] = repr(error)
            # An assertion, Python cancellation or pidfd acquisition error must
            # not abandon a still-running owned outer supervisor.
            if process is not None and process.returncode is None:
                try:
                    if fd is None:
                        fd = os.pidfd_open(process.pid)
                    try:
                        signal.pidfd_send_signal(fd, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        stdout, stderr = process.communicate(timeout=6)
                    except subprocess.TimeoutExpired:
                        self.__class__.blocked = True
                        evidence['cleanup_unverified'] = 'exception cleanup grace expired; forced outer kill is not containment'
                        try:
                            signal.pidfd_send_signal(fd, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        try:
                            stdout, stderr = process.communicate(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.stdout.close()
                            process.stderr.close()
                            try:
                                process.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                evidence['leader_reap_unverified'] = True
                    if guard.is_file():
                        terminal = json.loads(guard.read_text())
                        evidence['outer_after_exception'] = terminal
                        evidence['cleanup_certified'] = terminal.get('cleanup_complete') is True and terminal.get('survivors') == []
                    if not evidence['cleanup_certified']:
                        self.__class__.blocked = True
                except BaseException as cleanup_error:
                    self.__class__.blocked = True
                    evidence['test_cleanup_error'] = repr(cleanup_error)
            raise
        finally:
            if process is not None:
                evidence['exit_code'] = process.returncode
            if fd is not None:
                os.close(fd)
            (case / 'stdout').write_bytes(stdout)
            (case / 'stderr').write_bytes(stderr)
            save(case / 'test-result.json', evidence)

    def test_success(self):
        self.run_case('success')

    def test_nested_timeout(self):
        self.run_case('nested-timeout')

    def test_cancel(self):
        self.run_case('cancel')

    def test_root_exit_with_orphan_is_not_success(self):
        self.run_case('root-exit-orphan')

    def test_missing_executable_never_spawns(self):
        self.run_case('missing-executable')

    def test_install_natural_adopted_zero(self):
        self.run_case('install-adopted-zero')

    def test_install_natural_adopted_nonzero_is_not_success(self):
        self.run_case('install-adopted-nonzero')

    def test_pure_natural_adopted_zero_remains_rejected(self):
        self.run_case('pure-adopted-zero')

    def test_install_live_orphan_is_not_success(self):
        self.run_case('install-live-orphan')

    def test_strict_success_ledger_rejects_malformed_or_incomplete_records(self):
        module = types.ModuleType('qualification_pure_ledger')
        module.__file__ = str(self.stage)
        exec(compile(self.stage_raw, str(self.stage), 'exec'), module.__dict__)
        good = dict(phase='install', root_pid=101, effective_uid=0,
                    ownership_admitted_after_ECHILD=True, initial_children=[],
                    commands_started=1, reason='root exited', cancel_signals=[],
                    cleanup=dict(cleanup_complete=True, survivors=[], signals=[],
                                 target_exit_code=0,
                                 reaped=[dict(pid=101, status=0), dict(pid=102, status=0)]))
        self.assertTrue(module.successful_exit(good))
        for phase in ('pure', 'build', 'candidate', 'header'):
            changed = copy.deepcopy(good)
            changed.update(phase=phase, effective_uid=1000)
            self.assertFalse(module.successful_exit(changed))
            changed['cleanup']['reaped'] = [dict(pid=101, status=0)]
            self.assertTrue(module.successful_exit(changed))
        bad = []
        for key, value in (
            ('phase', 'unknown'), ('root_pid', True), ('root_pid', -1),
            ('root_pid', 999), ('effective_uid', True), ('effective_uid', 1000),
            ('effective_uid', -1), ('ownership_admitted_after_ECHILD', False),
            ('ownership_admitted_after_ECHILD', 1), ('initial_children', [5]),
            ('commands_started', True), ('commands_started', 2),
            ('reason', 'cancelled'), ('cancel_signals', [15]),
            ('root_notifications', [dict(pid=101, signal=15)]),
            ('root_notification_race', None), ('error', None),
            ('resource_error', None), ('finalization_error', None),
            ('notification_evidence_error', None), ('cleanup', None)):
            changed = copy.deepcopy(good)
            changed[key] = value
            bad.append(changed)
        for key, value in (
            ('cleanup_complete', False), ('cleanup_complete', 1),
            ('survivors', [102]), ('signals', [dict(pid=102, signal=15)]),
            ('target_exit_code', True), ('target_exit_code', 7),
            ('error', None), ('reaped', None), ('reaped', []),
            ('reaped', [dict(pid=101, status=0), dict(pid=101, status=0)]),
            ('reaped', [dict(pid=102, status=0)]),
            ('reaped', [dict(pid=101, status=0), dict(pid=102)]),
            ('reaped', [dict(pid=101, status=0), dict(pid=102, status=0, unknown=True)]),
            ('reaped', [dict(pid=101, status=0), dict(pid=True, status=0)]),
            ('reaped', [dict(pid=101, status=0), dict(pid=-1, status=0)]),
            ('reaped', [dict(pid=101, status=0), dict(pid=102, status=True)]),
            ('reaped', [dict(pid=101, status=0), dict(pid=102, status=7)]),
            ('reaped', [dict(pid=101, status=0), dict(pid=102, status=-15)]),
            ('reaped', [dict(pid=101, status=7), dict(pid=102, status=0)])):
            changed = copy.deepcopy(good)
            changed['cleanup'][key] = value
            bad.append(changed)
        for key in good:
            changed = copy.deepcopy(good)
            del changed[key]
            bad.append(changed)
        for key in good['cleanup']:
            changed = copy.deepcopy(good)
            del changed['cleanup'][key]
            bad.append(changed)
        for changed in bad:
            with self.subTest(changed=changed):
                self.assertFalse(module.successful_exit(changed))
        # This pure function checks record consistency only. Actual PID
        # provenance is exclusively the pinned helper's owned waitpid events.

    def test_uid_boundary_and_pure_failclosed_helpers(self):
        module = types.ModuleType('qualification_pure_helpers')
        module.__file__ = str(self.stage)
        exec(compile(self.stage_raw, str(self.stage), 'exec'), module.__dict__)
        self.assertEqual(module.PHASES, {'install': 900, 'build': 1200, 'pure': 120, 'candidate': 625, 'header': 120})
        self.assertEqual((module.GRACE, module.CLEANUP), (30, 10))
        self.assertEqual((module.AS_LIMIT, module.RSS_LIMIT), (6*1024**3, 5*1024**3))
        with self.assertRaises(RuntimeError):
            module.require(False, 'pure refusal')
        with self.assertRaises(FileNotFoundError):
            module.sha_file(self.output / 'missing-identity')
        self.run_case('uid-boundary')

if __name__ == '__main__':
    unittest.main()
