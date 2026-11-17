#!/usr/bin/env python3
"""Six isolated synthetic owner tests, not production phase qualification.
No compiler, package installer, interpreter or workload is executed. A second
pinned supervisor contains the synthetic controller, including its descendants.
"""
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
STAGE_BLOB = '61efb73fb2bf07c51f40e1d6fc800adf5e74c3be'
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
            'cases': ['success', 'nested-timeout', 'cancel', 'root-exit-orphan', 'missing-executable', 'uid-boundary'],
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
        if name in ('nested-timeout', 'cancel', 'root-exit-orphan'):
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
if MODE=='root-exit-orphan':
    raise SystemExit(0)
while True: time.sleep(1)
"""
            target_text = 'READY=' + repr(str(ready)) + '\nMODE=' + repr(name) + '\n' + target_text
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
            'argv': ['qualification_stage.py', '--phase', 'pure', '--output',
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
module.PHASES=dict(module.PHASES,pure=config['budget'])
module.GRACE=.3
module.CLEANUP=2
if config['uid_boundary']:
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
                    if name == 'root-exit-orphan':
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

    def test_uid_boundary_and_pure_failclosed_helpers(self):
        module = types.ModuleType('qualification_pure_helpers')
        module.__file__ = str(self.stage)
        exec(compile(self.stage_raw, str(self.stage), 'exec'), module.__dict__)
        self.assertEqual(module.PHASES, {'install': 900, 'build': 1200, 'pure': 120, 'utf8': 625})
        self.assertEqual((module.GRACE, module.CLEANUP), (30, 10))
        self.assertEqual((module.AS_LIMIT, module.RSS_LIMIT), (6*1024**3, 5*1024**3))
        with self.assertRaises(RuntimeError):
            module.require(False, 'pure refusal')
        with self.assertRaises(FileNotFoundError):
            module.sha_file(self.output / 'missing-identity')
        self.run_case('uid-boundary')

if __name__ == '__main__':
    unittest.main()
