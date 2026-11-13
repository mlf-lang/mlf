import fcntl
import hashlib
import json
from pathlib import Path
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import signal
import guard

class PidfdIdentityTests(unittest.TestCase):
    def test_bound_signal_checks_identity_after_open(self):
        events=[]
        with patch.object(guard.os,'pidfd_open',side_effect=lambda pid:events.append(('open',pid)) or 99), \
             patch.object(guard,'process_table',side_effect=lambda:events.append(('inspect',)) or {123:{'start':'456'}}), \
             patch.object(guard.signal,'pidfd_send_signal',side_effect=lambda fd,sig:events.append(('signal',fd,sig))), \
             patch.object(guard.os,'close') as close:
            self.assertTrue(guard.signal_identity(123,'456',signal.SIGTERM))
            self.assertEqual(events,[('open',123),('inspect',),('signal',99,signal.SIGTERM)])
            close.assert_called_once_with(99)
    def test_reused_pid_is_never_signaled(self):
        with patch.object(guard.os,'pidfd_open',return_value=99), \
             patch.object(guard,'process_table',return_value={123:{'start':'NEW'}}), \
             patch.object(guard.signal,'pidfd_send_signal') as send, \
             patch.object(guard.os,'close') as close:
            with self.assertRaisesRegex(ValueError,'identity changed'):guard.signal_identity(123,'OLD',signal.SIGKILL)
            send.assert_not_called();close.assert_called_once_with(99)
    def test_gone_before_open(self):
        with patch.object(guard.os,'pidfd_open',side_effect=ProcessLookupError), \
             patch.object(guard.signal,'pidfd_send_signal') as send:
            self.assertFalse(guard.signal_identity(123,'OLD',signal.SIGTERM));send.assert_not_called()
    def test_gone_after_open(self):
        with patch.object(guard.os,'pidfd_open',return_value=99), \
             patch.object(guard,'process_table',return_value={}), \
             patch.object(guard.signal,'pidfd_send_signal') as send, \
             patch.object(guard.os,'close') as close:
            self.assertFalse(guard.signal_identity(123,'OLD',signal.SIGTERM));send.assert_not_called();close.assert_called_once_with(99)
    def test_gone_at_signal(self):
        with patch.object(guard.os,'pidfd_open',return_value=99), \
             patch.object(guard,'process_table',return_value={123:{'start':'OLD'}}), \
             patch.object(guard.signal,'pidfd_send_signal',side_effect=ProcessLookupError), \
             patch.object(guard.os,'close') as close:
            self.assertFalse(guard.signal_identity(123,'OLD',signal.SIGTERM));close.assert_called_once_with(99)
    def test_unsupported_fails_closed(self):
        with patch.object(guard.os,'pidfd_open',None),patch.object(guard.signal,'pidfd_send_signal') as send:
            with self.assertRaisesRegex(ValueError,'pidfd support required'):guard.signal_identity(123,'OLD',signal.SIGTERM)
            with self.assertRaisesRegex(ValueError,'pidfd support required'):guard.require_pidfds()
            send.assert_not_called()
    def test_permission_failure_no_numeric_fallback(self):
        with patch.object(guard.os,'pidfd_open',side_effect=PermissionError), \
             patch.object(guard.os,'kill') as numeric:
            with self.assertRaises(PermissionError):guard.signal_identity(123,'OLD',signal.SIGTERM)
            numeric.assert_not_called()

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
        self.assertTrue(r['lease_cleared'])
        self.assertFalse(guard.epoch_active_path(self.locks,self.epoch).exists())
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
        if shutil.disk_usage(self.root).free < guard.LIMITS['free_disk'] or guard.available_memory() < guard.LIMITS['host_available']:
            self.skipTest('production host/disk floors unavailable; scope test not qualified')
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
    def test_footprint_does_not_follow_control_symlink(self):
        p=self.root/'link';p.symlink_to('/proc',target_is_directory=True)
        size=guard.footprint(self.root)
        self.assertLess(size,1024)
        self.assertGreaterEqual(size,p.lstat().st_size)
    def test_footprint_disappearing_entry(self):
        stable=self.root/'stable';stable.write_bytes(b'12345')
        with patch.object(guard.os,'walk',return_value=[(str(self.root),[],['ghc_tmp_55_1.c','stable'])]):
            self.assertEqual(guard.footprint(self.root),5)
    def test_footprint_missing_root_fatal(self):
        with self.assertRaises(FileNotFoundError):guard.footprint(self.root/'missing')
    def test_footprint_root_vanishes_before_sample_finishes(self):
        bound=self.root/'bound';bound.mkdir()
        def walk(root,followlinks,onerror):
            root.rmdir()
            return iter(())
        with patch.object(guard.os,'walk',side_effect=walk),self.assertRaises(FileNotFoundError):guard.footprint(bound)
    def test_footprint_non_directory_root_fatal(self):
        file=self.root/'file';file.write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'directory'):guard.footprint(file)
        link=self.root/'link';link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'symlink'):guard.footprint(link)
    def test_footprint_disappearing_directory_enumeration(self):
        stable=self.root/'stable';stable.write_bytes(b'12345')
        def walk(root,followlinks,onerror):
            self.assertFalse(followlinks)
            onerror(FileNotFoundError(2,'vanished',str(root/'ghc160_tmp_1')))
            yield (str(root),[],['stable'])
        with patch.object(guard.os,'walk',side_effect=walk):self.assertEqual(guard.footprint(self.root),5)
    def test_footprint_enumeration_root_and_permission_fatal(self):
        for error in [FileNotFoundError(2,'root vanished',str(self.root)),PermissionError(13,'denied',str(self.root/'child'))]:
            def walk(root,followlinks,onerror):
                onerror(error)
                yield (str(root),[],[])
            with self.subTest(error=type(error)),patch.object(guard.os,'walk',side_effect=walk),self.assertRaises(type(error)):
                guard.footprint(self.root)
    def test_footprint_non_enoent_still_fails(self):
        with patch.object(guard.os,'walk',return_value=[(str(self.root),[],['entry'])]):
            for error in [PermissionError('denied'),NotADirectoryError('changed type'),OSError('I/O failure')]:
                with self.subTest(error=type(error)),patch.object(Path,'lstat',side_effect=error),self.assertRaises(type(error)):
                    guard.footprint(self.root)
    def test_footprint_live_temporary_churn(self):
        stable=self.root/'stable';stable.write_bytes(b'x'*1024);errors=[];finished=threading.Event()
        def churn():
            try:
                for i in range(400):
                    p=self.root/('tmp'+str(i));p.write_bytes(b'x'*17);p.unlink()
            except BaseException as error:errors.append(error)
            finally:finished.set()
        thread=threading.Thread(target=churn);thread.start()
        try:
            for _ in range(80):self.assertGreaterEqual(guard.footprint(self.root),1024)
        finally:thread.join(timeout=3)
        self.assertTrue(finished.is_set());self.assertEqual(errors,[])
    def test_epoch_quarantine_cross_workroot(self):
        r=self.run_code('import os,signal;os.kill(os.getppid(),signal.SIGKILL)')
        self.assertFalse(r['complete'])
        marker=guard.epoch_quarantine_path(self.locks,self.epoch)
        original=marker.read_bytes()
        lease=guard.epoch_active_path(self.locks,self.epoch)
        self.assertTrue(lease.exists())
        self.assertEqual(json.loads(lease.read_text())['schema'],'sparse-scc-epoch-lease-v1')
        guard.persist_quarantine(marker,{'must':'not overwrite'})
        self.assertEqual(marker.read_bytes(),original)
        with self.assertRaisesRegex(ValueError,'quarantined epoch'):
            guard.run_guard([sys.executable,'-c','pass'],cwd=self.root,output=self.root/'second-work',
                            locks=self.locks,epoch=self.epoch,seconds=2,test_mode=True)
        self.assertFalse((self.root/'second-work').exists())
    def test_epoch_quarantine_path_validation(self):
        for bad in ['../elsewhere','a'*63,'A'*64,'f'*65,None]:
            with self.assertRaises(ValueError):
                guard.epoch_quarantine_path(self.locks,dict(self.epoch,sha256=bad))
        with self.assertRaises(ValueError):
            guard.epoch_quarantine_path([dict(self.locks[0],path='relative'),self.locks[1]],self.epoch)
        marker=guard.epoch_quarantine_path(self.locks,self.epoch)
        marker.symlink_to(self.epoch_file)
        with self.assertRaises(ValueError):guard.persist_quarantine(marker,{})
        self.assertEqual(self.epoch_file.read_text(),'{"epoch":"new-test-only"}')
    def test_preexisting_active_lease_blocks_launch(self):
        lease=guard.epoch_active_path(self.locks,self.epoch)
        guard.create_lease(lease,{'uncertain':'do not overwrite'})
        original=lease.read_bytes()
        with self.assertRaisesRegex(ValueError,'active epoch lease'):
            self.run_code('raise RuntimeError("must not run")')
        self.assertEqual(lease.read_bytes(),original)
        self.assertFalse((self.root/'run').exists())
    def test_budget_ceiling(self):
        with self.assertRaises(ValueError):self.run_code('pass',seconds=601)

if __name__=='__main__':unittest.main()
