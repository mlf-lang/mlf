import fcntl
import hashlib
import json
from pathlib import Path
import os
import sys
import tempfile
import threading
import unittest
import guard

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='test-work-', dir=Path(guard.__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.epoch_file = self.root/'epoch.json'
        self.epoch_file.write_text('{"epoch":"new-test-only"}')
        self.epoch = dict(path=str(self.epoch_file), sha256=guard.digest(self.epoch_file))
        self.locks = []
        for name in ['heavy.lock', 'reproduction.lock']:
            p = self.root/name
            p.touch()
            st = p.stat()
            self.locks.append(dict(path=str(p), device=st.st_dev, inode=st.st_ino))
    def run_code(self, code, **kwargs):
        return guard.run_guard([sys.executable, '-B', '-c', code], cwd=self.root,
                               output=self.root/'run', locks=self.locks, epoch=self.epoch,
                               seconds=kwargs.pop('seconds', 2), test_mode=True, **kwargs)
    def test_success_archives_reports(self):
        p = self.root/'run'/'active.prof'
        r = self.run_code('from pathlib import Path; Path('+repr(str(p))+').write_text("raw")', reports=[p])
        self.assertTrue(r['complete'], r)
        self.assertTrue(r['cleanup'] and r['lock_reacquired'])
        self.assertFalse(p.exists())
        self.assertEqual(Path(r['archived'][str(p)]['path']).read_text(), 'raw')
    def test_false_124_is_not_timeout(self):
        r = self.run_code('raise SystemExit(124)')
        self.assertFalse(r['complete'])
        self.assertNotEqual(r['reason'], 'timeout')
        self.assertEqual(r['exit_code'],124)
    def test_negative_expected_exit(self):
        self.assertTrue(self.run_code('raise SystemExit(1)', accepted_exit_codes=[1])['complete'])
    def test_hard_kill_missing_profile(self):
        r = self.run_code('import os,signal; os.kill(os.getpid(),signal.SIGKILL)', reports=[self.root/'run'/'active.prof'])
        self.assertFalse(r['complete'])
    def test_missing_report(self):
        self.assertFalse(self.run_code('pass',reports=[self.root/'run'/'active.prof'])['complete'])
    def test_timeout_descendant_session_cleanup(self):
        code = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import os,time; os.setsid(); time.sleep(30)"]); time.sleep(30)'
        r = self.run_code(code, seconds=.2)
        self.assertFalse(r['complete'])
        self.assertEqual(r['reason'],'timeout')
        self.assertTrue(r['cleanup'])
        self.assertGreaterEqual(len(r['tracked_processes']),2)
    def test_double_fork_surviving_leader(self):
        code = 'import os,time; p=os.fork();\nif p==0:\n os.setsid(); time.sleep(30)\nelse:\n os._exit(0)'
        r=self.run_code(code)
        self.assertFalse(r['complete'])
        self.assertTrue(r['cleanup'])
        self.assertIn('descendants survived',r['reason'])
    def test_cancel(self):
        event=threading.Event()
        t=threading.Timer(.2,event.set);t.start();self.addCleanup(t.cancel)
        r=self.run_code('import time; time.sleep(30)',cancel_event=event)
        self.assertEqual(r['reason'],'cancelled');self.assertTrue(r['cleanup'])
    def test_stale_and_symlink_report(self):
        p=self.root/'active.prof';p.write_text('stale')
        self.assertFalse(self.run_code('pass',reports=[p],bounded_root=self.root)['complete'])
        self.assertEqual(p.read_text(), 'stale')
    def test_symlink_parent(self):
        p=self.root/'link';p.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):
            guard.safe(p/'missing')
    def test_wrong_epoch(self):
        self.epoch['sha256']='0'*64
        self.assertFalse(self.run_code('pass')['complete'])
    def test_replaced_lock(self):
        self.locks[0]['inode']+=1
        self.assertFalse(self.run_code('pass')['complete'])
    def test_nested_not_stage_admission(self):
        r=guard.run_child([sys.executable,'-c','pass'],cwd=self.root,output=self.root/'run',seconds=2,test_mode=True)
        self.assertTrue(r['complete'],r)
        self.assertFalse(r['standalone_admission'])
        self.assertFalse(r['lock_reacquired'])
    def test_contended_lock(self):
        with open(self.locks[0]['path'], 'r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r=self.run_code('raise RuntimeError("must not launch")')
            self.assertFalse(r['complete'])
            self.assertIsNone(r['exit_code'])
    def test_symlink_report(self):
        p=self.root/'active.prof'; target=self.root/'target'; target.write_text('do not touch')
        p.symlink_to(target)
        self.assertFalse(self.run_code('pass',reports=[p],bounded_root=self.root)['complete'])
        self.assertTrue(p.is_symlink()); self.assertEqual(target.read_text(),'do not touch')
    def test_lock_replaced_during_run(self):
        p=self.locks[0]['path']
        code='from pathlib import Path; import time; p=Path('+repr(p)+'); p.unlink(); p.touch(); time.sleep(1)'
        r=self.run_code(code)
        self.assertFalse(r['complete']); self.assertFalse(r['lock_reacquired']); self.assertTrue(r['cleanup'])
    def test_supervisor_transport_failure_quarantines(self):
        r=self.run_code('import os,signal; os.kill(os.getppid(),signal.SIGKILL)')
        self.assertFalse(r['complete'])
        self.assertIn('quarantine',r['reason'])
        self.assertFalse(json.loads((self.root/'run'/'quarantine.json').read_text())['complete'])
    def test_failed_child_preserves_incomplete_report(self):
        p=self.root/'run'/'active.prof'
        code='from pathlib import Path; Path('+repr(str(p))+').write_text("partial"); raise SystemExit(1)'
        r=self.run_code(code,reports=[p])
        self.assertFalse(r['complete']); self.assertEqual(r['archived'],{})
        self.assertFalse(p.exists())
        self.assertEqual((self.root/'run'/'incomplete-reports'/'0-active.prof').read_text(),'partial')
    def test_independent_posix_reacquisition(self):
        binding=dict(self.locks[0],kind='posix')
        self.assertTrue(guard.reacquire_locks([binding]))
        with open(binding['path'],'r+') as fd:
            fcntl.lockf(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(ValueError):guard.reacquire_locks([binding])
    def scope_run(self, test_mode=False):
        helper=self.root/'scope_worker.py'; payload=self.root/'scope.json'
        command=[sys.executable,'-B',str(helper),str(payload)]
        claim=self.root/'claim.json';claim_expected={'phase':'TEST','retry_allowed':False}
        claim.write_text(json.dumps(claim_expected))
        params=dict(command=command,cwd=str(self.root),output=str(self.root/'run'),locks=self.locks,
                    epoch=self.epoch,seconds=2,bounded_root=str(self.root),claim_path=str(claim),claim_expected=claim_expected)
        payload.write_text(json.dumps(params))
        helper.write_text('import sys,json; sys.path.insert(0,'+repr(str(Path(guard.__file__).parent))+'); import guard; guard.verify_worker_scope(**json.load(open(sys.argv[1])))')
        return guard.run_guard(command,cwd=self.root,output=self.root/'run',locks=self.locks,
                               epoch=self.epoch,seconds=2,bounded_root=self.root,test_mode=test_mode)
    def test_actual_worker_scope(self):
        r=self.scope_run()
        self.assertTrue(r['complete'],r)
        self.assertEqual(r['locks'],self.locks);self.assertEqual(r['epoch'],self.epoch)
    def test_test_scope_cannot_admit_worker(self):
        r=self.scope_run(test_mode=True)
        self.assertFalse(r['complete'])
    def test_proc_lock_parser(self):
        raw='1: FLOCK  ADVISORY  WRITE 123 00:2a:555 0 EOF\n2: -> FLOCK ADVISORY WRITE 124 00:2a:555 0 EOF\n3: POSIX ADVISORY WRITE 99 00:2a:777 0 EOF\n'
        self.assertEqual(guard.lock_owners(raw),{(123,os.makedev(0,42),555)})
    def test_quarantine_refuses_launch(self):
        (self.root/'quarantine.json').write_text('{}')
        with self.assertRaises(ValueError):self.run_code('pass',bounded_root=self.root)
    def test_budget_ceiling(self):
        with self.assertRaises(ValueError):self.run_code('pass',seconds=601)

if __name__=='__main__':unittest.main()
