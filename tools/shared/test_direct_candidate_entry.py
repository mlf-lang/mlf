"""Pure route controls plus three REAL bounded synthetic Linux supervisor cases.
No GHC/emlf/native fixture. Synthetic receipts are not project qualification.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock
import test_direct_candidate_successor as E
import candidate_batch_worker as W

class EntryControls(unittest.TestCase):
    def fixture(self):
        original=types.SimpleNamespace(ROOT=Path('/repo'),sha=lambda _: 'digest')
        runner=types.SimpleNamespace(root=original.ROOT,output=Path('/out'),receipt={'producer':{'path':'/build/receipt.json','sha256':'digest'},'inputs':{'/build/receipt.json':'digest'}})
        argv=[sys.executable,'-B',str(E.HERE/'test_candidate_selection.py'),'--build-receipt','/build/receipt.json','--clang','clang','--output','/out/candidate-selection']
        return runner,original,argv
    def test_exact_route_and_every_operand_refused(self):
        runner,original,argv=self.fixture(); E.validate_route(runner,original,argv,None,0,None,600)
        for index in (0,1,2,3,4,5,7,8):
            wrong=list(argv);wrong[index]='wrong'
            with self.subTest(index=index),self.assertRaises(RuntimeError): E.validate_route(runner,original,wrong,None,0,None,600)
        for kwargs in [(None,0,None,625),({'X':'1'},0,None,600),(None,False,None,600),(None,0,b'',600)]:
            with self.assertRaises(RuntimeError): E.validate_route(runner,original,argv,*kwargs)
        runner.receipt['inputs']['/build/receipt.json']='different'
        with self.assertRaises(RuntimeError): E.validate_route(runner,original,argv,None,0,None,600)
    def test_composition_leaves_crc_and_other_calls_to_original(self):
        calls=[]
        class Base:
            def run(self,*args,**kwargs):calls.append((args,kwargs));return 'physical'
        original=types.SimpleNamespace(CommandRunner=Base)
        E.compose(original,None,None,{})
        for name in ('bulk-crc','utf8-length','query-json','other'):
            self.assertEqual(original.CommandRunner().run(name,['unchanged'],timeout=600),'physical')
        self.assertEqual([x[0][0] for x in calls],['bulk-crc','utf8-length','query-json','other'])
    def test_candidate_positive_dispatch_exact_instance(self):
        runner,original,argv=self.fixture()
        original.CommandRunner=type('Base',(),{})
        E.compose(original,'crc','worker',{'pin':'value'})
        instance=original.CommandRunner();instance.__dict__.update(runner.__dict__)
        with mock.patch.object(E,'managed',return_value='managed') as call:
            self.assertEqual(instance.run('candidate-selection',argv,timeout=600),'managed')
            call.assert_called_once_with(instance,original,'crc','worker',{'pin':'value'},argv)
    def test_strict_terminal(self):
        good=dict(phase='terminal',reason='target exited',complete=True,cleanup_complete=True,target_exit_code=0,survivors=[],signals=[],cancel_signals=[],
                  command=['worker','exact'],work_seconds=600.,cleanup_seconds=10.,root_pid=123,reaped=[dict(pid=123,status=0)])
        worker=dict(complete=True,input_pins={'source':'digest'},producer_receipt_path='/receipt',producer_receipt_sha256='producer')
        binding=dict(worker_argv=['worker','exact'],pins={'source':'digest'},producer_path='/receipt',producer_sha='producer',work=600,cleanup=10)
        E.validate_terminal(0,good,worker,b'',**binding)
        for field in good:
            wrong=dict(good);wrong.pop(field)
            with self.subTest(field=field),self.assertRaises(RuntimeError):E.validate_terminal(0,wrong,worker,b'',**binding)
        for field in ('error','cleanup_error'):
            with self.assertRaises(RuntimeError): E.validate_terminal(0,dict(good,**{field:None}),worker,b'',**binding)
        for status,wrong,stderr in [(False,worker,b''),(0,dict(worker,complete=False),b''),(0,worker,b'error')]:
            with self.assertRaises(RuntimeError): E.validate_terminal(status,good,wrong,stderr,**binding)
        mutations={'command':['another'],'work_seconds':625,'cleanup_seconds':True,'root_pid':True,
                   'reaped':[dict(pid=123,status=False)]}
        for key,value in mutations.items():
            with self.subTest(key=key),self.assertRaises(RuntimeError): E.validate_terminal(0,dict(good,**{key:value}),worker,b'',**binding)
        for wrong in ([],[dict(pid=124,status=0)],[dict(pid=True,status=0)],[dict(pid=123,status=0)]*2):
            with self.assertRaises(RuntimeError):E.validate_terminal(0,dict(good,reaped=wrong),worker,b'',**binding)
        for field in ('input_pins','producer_receipt_path','producer_receipt_sha256'):
            for kind in ('missing','changed'):
                wrong=dict(worker)
                if kind=='missing':wrong.pop(field)
                else:wrong[field]='wrong'
                with self.subTest(field=field,kind=kind),self.assertRaises(RuntimeError):E.validate_terminal(0,good,wrong,b'',**binding)
        # Float limits are the CLI parser's actual representation; bools never
        # qualify as numeric values, including in a test-only one-second policy.
        for field in ('work_seconds','cleanup_seconds'):
            small=dict(binding,work=1,cleanup=1); changed=dict(good,work_seconds=1.,cleanup_seconds=1.);changed[field]=True
            with self.assertRaises(RuntimeError):E.validate_terminal(0,changed,worker,b'',**small)
    def test_each_existing_destination_refused_including_dangling_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            E.fresh_destinations(root)
            for name in ('candidate-selection','candidate-selection-supervisor.json','candidate-selection-batch-worker.json','candidate-selection-supervisor.tmp','candidate-selection-batch-worker.tmp','candidate-selection.stdout','candidate-selection.stderr'):
                path=root/name;path.write_bytes(b'old evidence')
                with self.subTest(name=name),self.assertRaises(RuntimeError):E.fresh_destinations(root)
                self.assertEqual(path.read_bytes(),b'old evidence');path.unlink()
            (root/'candidate-selection').symlink_to(root/'absent')
            with self.assertRaises(RuntimeError):E.fresh_destinations(root)


    def test_actual_managed_success_command_pins_and_handler_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'out';out.mkdir()
            pins={'source':'sha'}
            runner=types.SimpleNamespace(root=root,output=out,
                receipt={'commands':[],'producer':{'sha256':'producer'}},save=lambda:None)
            original=types.SimpleNamespace(sha=lambda _:'producer')
            worker=types.SimpleNamespace(snapshot=lambda:({},pins))
            crc=types.SimpleNamespace(require_pidfd=lambda:None)
            argv=[sys.executable,'-B',str(root/'test_candidate_selection.py'),
                  '--build-receipt','/receipt','--clang','clang','--output',str(out/'candidate-selection')]
            commands=[];before={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
            def spawn(actual,**kwargs):
                commands.append(actual)
                guard=dict(phase='terminal',reason='target exited',complete=True,
                    cleanup_complete=True,target_exit_code=0,survivors=[],signals=[],cancel_signals=[],
                    command=actual[9:],work_seconds=600.,cleanup_seconds=10.,
                    root_pid=123,reaped=[dict(pid=123,status=0)])
                (out/'candidate-selection-supervisor.json').write_text(json.dumps(guard))
                (out/'candidate-selection-batch-worker.json').write_text(json.dumps(dict(
                    complete=True,input_pins=pins,producer_receipt_path='/receipt',
                    producer_receipt_sha256='producer')))
                return types.SimpleNamespace(pid=456,returncode=0,
                    communicate=lambda timeout:(b'actual mock output\n',b''))
            with mock.patch.object(E,'HERE',root),mock.patch.object(E.subprocess,'Popen',side_effect=spawn),\
                 mock.patch.object(E.os,'pidfd_open',return_value=789,create=True),mock.patch.object(E.os,'close') as close:
                result=E.managed(runner,original,crc,worker,pins,argv)
                close.assert_called_once_with(789)
            self.assertEqual(commands[0],[sys.executable,'-B',str(root/'crc_process_supervisor.py'),
                '--receipt',str(out/'candidate-selection-supervisor.json'),'--work-seconds','600',
                '--cleanup-seconds','10',sys.executable,'-B',str(root/'candidate_batch_worker.py'),*argv[3:]])
            self.assertEqual(result.stdout,b'actual mock output\n')
            entry=runner.receipt['commands'][0]
            self.assertEqual(entry['state'],'passed');self.assertEqual(entry['timeout_seconds'],625)
            for sig,handler in before.items():self.assertEqual(signal.getsignal(sig),handler)

@unittest.skipUnless(sys.platform == 'linux', 'real supervisor requires Linux pidfds and procfs')
class RealSyntheticControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence=None
        if os.environ.get('MLF_CANDIDATE_TEST_EVIDENCE'):
            cls.evidence=Path(os.environ['MLF_CANDIDATE_TEST_EVIDENCE']).resolve()
            cls.evidence.mkdir(parents=True,exist_ok=False)
        source=E.HERE/'crc_process_supervisor.py'
        cls.supervisor=source.read_bytes()
        if W.blob(cls.supervisor)!=W.PINS['crc_process_supervisor.py']:raise RuntimeError('synthetic supervisor source pin')
    def case(self,name,work,outer,cancel=False):
        # managed() is the production cancellation path; only test globals and
        # the executed fake worker are replaced. No production CLI budget escape.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); out=root/'out';out.mkdir()
            (root/'crc_process_supervisor.py').write_bytes(self.supervisor)
            (root/'candidate_batch_worker.py').write_text('''import os,signal,time,json
+from pathlib import Path
+r,w=os.pipe()
+pid=os.fork()
+if pid==0:
+    os.close(r);os.setsid();signal.signal(signal.SIGTERM,signal.SIG_IGN)
+    os.write(w,b'R');os.close(w)
+    while True:time.sleep(1)
+os.close(w)
+if os.read(r,1)!=b'R':raise RuntimeError('child readiness')
+os.close(r)
+Path(__file__).with_name('readiness.json').write_text(json.dumps({'root_pid':os.getpid(),'child_pid':pid}))
+while True:time.sleep(1)
+'''.replace('\n+','\n'))
            runner=types.SimpleNamespace(root=root,output=out,receipt={'commands':[],'producer':{'sha256':'synthetic'}})
            runner.save=lambda:(out/'outer.json').write_text(json.dumps(runner.receipt,indent=2)+'\n')
            original=types.SimpleNamespace(sha=lambda _:'synthetic')
            worker=types.SimpleNamespace(snapshot=lambda:({},{}))
            def capability():
                if sys.platform!='linux' or not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal'):raise RuntimeError('Linux pidfd required')
                fd=os.pidfd_open(os.getpid());os.close(fd)
            crc=types.SimpleNamespace(require_pidfd=capability)
            argv=[sys.executable,'-B',str(root/'test_candidate_selection.py'),'--build-receipt','synthetic','--clang','clang','--output',str(out/'candidate-selection')]
            timer=None;before={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
            real_popen=subprocess.Popen
            def spawn(*args,**kwargs):
                nonlocal timer
                process=real_popen(*args,**kwargs)
                if cancel:
                    # managed has installed its handlers and blocked cancellation
                    # before Popen. Never arm a signal before entering that scope.
                    timer=threading.Timer(.7,lambda:os.kill(os.getpid(),signal.SIGTERM));timer.start()
                return process
            try:
                with mock.patch.object(E,'HERE',root),mock.patch.object(E,'WORK',work),mock.patch.object(E,'OUTER',outer),mock.patch.object(E,'CLEANUP',2),mock.patch.object(E,'CANCEL_GRACE',4),mock.patch.object(E.subprocess,'Popen',side_effect=spawn):
                    with self.assertRaises((RuntimeError,subprocess.TimeoutExpired,KeyboardInterrupt)): E.managed(runner,original,crc,worker,{},argv)
                guard=json.loads((out/'candidate-selection-supervisor.json').read_text())
                ready=json.loads((root/'readiness.json').read_text())
                self.assertIs(type(ready['root_pid']),int);self.assertIs(type(ready['child_pid']),int)
                self.assertGreater(ready['child_pid'],0);self.assertNotEqual(ready['root_pid'],ready['child_pid'])
                self.assertEqual(guard['root_pid'],ready['root_pid'])
                reaped={row['pid']:row['status'] for row in guard['reaped']}
                self.assertGreaterEqual(len(reaped),2)
                self.assertIn(ready['root_pid'],reaped)
                self.assertEqual(reaped[ready['child_pid']],-signal.SIGKILL)
                sent={(row['pid'],row['signal']) for row in guard['signals']}
                self.assertIn((ready['child_pid'],signal.SIGTERM),sent)
                self.assertIn((ready['child_pid'],signal.SIGKILL),sent)
                self.assertTrue(guard['cleanup_complete']);self.assertEqual(guard['survivors'],[])
                self.assertEqual(guard['phase'],'terminal');self.assertFalse(guard['complete'])
                entry=runner.receipt['commands'][0]
                self.assertEqual(entry['state'],'failed')
                self.assertNotIn('cleanup_unverified',entry)
                self.assertEqual(guard['reason'],'work deadline' if name=='work-deadline' else 'cancelled')
                if name=='outer-timeout':self.assertTrue(entry['error'].startswith('TimeoutExpired('))
                elif name=='external-cancel':self.assertTrue(entry['error'].startswith('KeyboardInterrupt('))
                else:self.assertTrue(entry['error'].startswith('RuntimeError('))
                if cancel:self.assertIn(signal.SIGTERM,guard['cancel_signals'])
            finally:
                if timer is not None:timer.cancel();timer.join(timeout=1)
                for sig,handler in before.items():self.assertEqual(signal.getsignal(sig),handler)
                if self.evidence is not None:
                    destination=self.evidence/name;destination.mkdir(exist_ok=False)
                    for path in out.iterdir():
                        if path.suffix in ('.json','.stdout','.stderr'):(destination/path.name).write_bytes(path.read_bytes())
                    if (root/'readiness.json').is_file():(destination/'readiness.json').write_bytes((root/'readiness.json').read_bytes())
    def test_actual_work_deadline_cleanup(self):self.case('work-deadline',.7,5)
    def test_actual_outer_timeout_cleanup(self):self.case('outer-timeout',5,.7)
    def test_actual_external_cancel_cleanup(self):self.case('external-cancel',5,6,True)

if __name__=='__main__':unittest.main()
