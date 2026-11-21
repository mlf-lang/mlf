#!/usr/bin/env python3
"""Compose the unchanged CRC successor with a 600-second UTF8 batch successor."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import types
HERE=Path(__file__).resolve().parent
WORK=600
CLEANUP=10
OUTER=625
CANCEL_GRACE=25

def require(ok,message):
    if not ok: raise RuntimeError(message)
def load(raw,name,path):
    module=types.ModuleType(name); module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module

def validate_route(runner,original,argv,overrides,status,expected,timeout):
    require(len(argv)==9 and argv[:4]==[sys.executable,'-B',str(HERE/'test_utf8_length.py'),'--build-receipt'] and
            argv[5]=='--clang' and argv[7:]==['--output',str(runner.output/'utf8-length')] and
            type(timeout)is int and timeout==600 and not overrides and type(status)is int and status==0 and expected is None and runner.root==original.ROOT,
            'unexpected UTF8 successor invocation')
    producer=runner.receipt.get('producer',{})
    require(argv[4]==producer.get('path') and bool(producer.get('sha256')) and
            runner.receipt.get('inputs',{}).get(argv[4])==producer['sha256'] and
            original.sha(Path(argv[4]))==producer['sha256'],'UTF8 producer is not the authenticated instance')

def validate_terminal(status,guard,worker,stderr,*,worker_argv,pins,producer_path,producer_sha,work,cleanup):
    require(type(status)is int and status==0 and stderr==b'' and type(guard)is dict and
            guard.get('phase')=='terminal' and guard.get('reason')=='target exited' and
            guard.get('complete')is True and guard.get('cleanup_complete')is True and
            type(guard.get('target_exit_code'))is int and guard['target_exit_code']==0 and
            guard.get('survivors')==[] and guard.get('signals')==[] and guard.get('cancel_signals')==[] and
            'error' not in guard and 'cleanup_error' not in guard and type(worker)is dict and worker.get('complete')is True,
            'UTF8 complete worker and owned-tree terminal evidence required')
    require(guard.get('command')==worker_argv and type(guard.get('command'))is list and
            type(guard.get('work_seconds'))in (int,float) and guard['work_seconds']==work and
            type(guard.get('cleanup_seconds'))in (int,float) and guard['cleanup_seconds']==cleanup,
            'exact executed worker command and budgets required')
    root=guard.get('root_pid')
    require(type(root)is int and root>0 and type(guard.get('reaped'))is list and
            len(guard['reaped'])==1 and type(guard['reaped'][0])is dict and
            type(guard['reaped'][0].get('pid'))is int and guard['reaped'][0]['pid']==root and
            type(guard['reaped'][0].get('status'))is int and guard['reaped'][0]['status']==0,
            'one actually reaped worker identity required')
    require(worker.get('input_pins')==pins and type(worker.get('input_pins'))is dict and
            worker.get('producer_receipt_path')==producer_path and
            worker.get('producer_receipt_sha256')==producer_sha,
            'worker source and authenticated producer receipt binding required')

def fresh_destinations(output):
    guard=output/'utf8-length-supervisor.json'; worker=output/'utf8-length-batch-worker.json'
    for path in (output/'utf8-length',guard,worker,guard.with_suffix('.tmp'),worker.with_suffix('.tmp'),
                 output/'utf8-length.stdout',output/'utf8-length.stderr'):
        require(not os.path.lexists(path),'fresh UTF8 destination required: '+str(path))
    return guard,worker

def managed(runner,original,crc,worker,pins,argv):
    guard,worker_receipt=fresh_destinations(runner.output)
    crc.require_pidfd()
    require(worker.snapshot()[1]==pins,'successor inputs changed')
    worker_argv=[sys.executable,'-B',str(HERE/'utf8_batch_worker.py'),*argv[3:]]
    actual=[sys.executable,'-B',str(HERE/'crc_process_supervisor.py'),'--receipt',str(guard),
            '--work-seconds',str(WORK),'--cleanup-seconds',str(CLEANUP),
            *worker_argv]
    entry=dict(name='utf8-length',argv=argv,execution_argv=actual,input_pins=pins,state='running',
               original_timeout_seconds=600,work_seconds=WORK,cleanup_seconds=CLEANUP,timeout_seconds=OUTER,
               scope='frozen original controls; explicit batch projections, no fresh-process equivalence; guard SIGKILL is not containment')
    runner.receipt['commands'].append(entry); runner.save()
    process=None; fd=None; stdout=stderr=b''; old={}; started=time.monotonic()
    def cancel(sig,frame): raise KeyboardInterrupt('UTF8 successor cancelled: '+str(sig))
    try:
        for sig in (signal.SIGINT,signal.SIGTERM): old[sig]=signal.signal(sig,cancel)
        mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        try:
            process=subprocess.Popen(actual,cwd=runner.root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            fd=os.pidfd_open(process.pid)
        finally: signal.pthread_sigmask(signal.SIG_SETMASK,mask)
        stdout,stderr=process.communicate(timeout=OUTER)
        require(type(process.returncode)is int and process.returncode==0,
                'UTF8 supervisor returned a failure; see retained guard evidence')
        entry['supervisor']=json.loads(guard.read_text()); entry['worker']=json.loads(worker_receipt.read_text())
        validate_terminal(process.returncode,entry['supervisor'],entry['worker'],stderr,
            worker_argv=worker_argv,pins=pins,producer_path=argv[4],
            producer_sha=runner.receipt['producer']['sha256'],work=WORK,cleanup=CLEANUP)
        require(worker.snapshot()[1]==pins,'successor source drift')
        require(original.sha(Path(argv[4]))==runner.receipt['producer']['sha256'],'producer receipt drift')
        entry['state']='passed'
        return subprocess.CompletedProcess(argv,process.returncode,stdout,stderr)
    except BaseException as error:
        entry.update(state='failed',error=repr(error))
        if process is not None and process.returncode is None:
            previous={}
            try:
                for sig in (signal.SIGINT,signal.SIGTERM): previous[sig]=signal.signal(sig,lambda *_:None)
                if fd is None: fd=os.pidfd_open(process.pid)
                try: signal.pidfd_send_signal(fd,signal.SIGTERM)
                except ProcessLookupError: pass
                try: stdout,stderr=process.communicate(timeout=CANCEL_GRACE)
                except subprocess.TimeoutExpired as capture:
                    entry['cleanup_unverified']='supervisor 25s cancel grace expired; forced kill cannot contain descendants'
                    try: signal.pidfd_send_signal(fd,signal.SIGKILL)
                    except ProcessLookupError: pass
                    try: stdout,stderr=process.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        stdout,stderr=capture.stdout or b'',capture.stderr or b''
                        process.stdout.close(); process.stderr.close()
                        try: process.wait(timeout=2)
                        except subprocess.TimeoutExpired: entry['leader_reap_unverified']=True
            finally:
                for sig,handler in previous.items(): signal.signal(sig,handler)
        raise
    finally:
        try:
            entry['exit_code']=None if process is None else process.returncode
            try:
                for label,path in [('supervisor',guard),('worker',worker_receipt)]:
                    if path.is_file(): entry[label]=json.loads(path.read_text())
                for label,raw in [('stdout',stdout),('stderr',stderr)]:
                    path=runner.output/('utf8-length.'+label); path.write_bytes(raw)
                    entry[label+'_sha256']=hashlib.sha256(raw).hexdigest()
            except BaseException as error:
                entry.update(state='failed',evidence_error=repr(error)); raise
            finally:
                entry['seconds']=time.monotonic()-started; runner.save()
        finally:
            try:
                if fd is not None: os.close(fd)
            finally:
                for sig,handler in old.items(): signal.signal(sig,handler)

def compose(original,crc,worker,pins):
    base=original.CommandRunner
    class UTF8Successor(base):
        def run(self,name,command,*,overrides=None,status=0,expected=None,timeout=180):
            if name!='utf8-length':
                return super().run(name,command,overrides=overrides,status=status,expected=expected,timeout=timeout)
            argv=list(map(str,command))
            validate_route(self,original,argv,overrides,status,expected,timeout)
            return managed(self,original,crc,worker,pins,argv)
    original.CommandRunner=UTF8Successor
    return original

def main():
    worker_raw=(HERE/'utf8_batch_worker.py').read_bytes()
    worker=load(worker_raw,'utf8_bound_worker',HERE/'utf8_batch_worker.py')
    raws,pins=worker.snapshot()
    require(worker_raw==raws['utf8_batch_worker.py'],'loaded worker source changed')
    crc=load(raws['test_direct_crc_successor.py'],'crc_bound_successor',HERE/'test_direct_crc_successor.py')
    original_loader=crc.load_original
    def composite_loader():
        crc_pins,original=original_loader()
        return crc_pins,compose(original,crc,worker,pins)
    crc.load_original=composite_loader
    try: crc.main()
    finally: crc.load_original=original_loader
if __name__=='__main__': main()
