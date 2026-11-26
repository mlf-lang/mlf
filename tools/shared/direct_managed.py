#!/usr/bin/env python3
"""Run expensive direct suites with one bounded, owned-process-tree supervisor."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
import test_direct as direct
HERE=Path(__file__).resolve().parent
@dataclass(frozen=True)
class Suite:
    name: str
    script: str
    worker: str | None = None
    work: float = 600
    cleanup: float = 10
    margin: float = 15

    @property
    def outer(self):
        return self.work + self.cleanup + self.margin

    @property
    def cancel_grace(self):
        return self.cleanup + self.margin


SUITES = {
    'bulk-crc': Suite('bulk-crc', 'test_crc32.py', work=1800),
    'utf8-length': Suite('utf8-length', 'test_utf8_length.py', 'utf8_batch_worker.py'),
    'candidate-selection': Suite('candidate-selection', 'test_candidate_selection.py', 'candidate_batch_worker.py'),
}


def snapshot(suite):
    if suite.worker == 'candidate_batch_worker.py':
        import candidate_batch_worker
        return candidate_batch_worker.snapshot()[1]
    if suite.worker == 'utf8_batch_worker.py':
        import utf8_batch_worker
        return utf8_batch_worker.snapshot()[1]
    names = ('test_direct.py', 'test_crc32.py', 'direct_managed.py',
             'crc_process_supervisor.py', 'default_stdlib.py',
             'fixtures/ByteArrayCRC32.hs')
    return {name: direct.sha(HERE / name) for name in names}


def require_pidfd():
    if sys.platform != 'linux' or not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise RuntimeError('Linux pidfd support required before supervisor spawn')
    fd = os.pidfd_open(os.getpid())
    os.close(fd)


def require(ok,message):
    if not ok: raise RuntimeError(message)
def validate_route(runner,suite,argv,overrides,status,expected,timeout):
    require(len(argv)==9 and argv[:4]==[sys.executable,'-B',str(HERE/suite.script),'--build-receipt'] and
            argv[5]=='--clang' and argv[7:]==['--output',str(runner.output/suite.name)] and
            type(timeout)is int and timeout==600 and not overrides and type(status)is int and status==0 and expected is None and runner.root==direct.ROOT,
            'unexpected '+suite.name+' invocation')
    producer=runner.receipt.get('producer',{})
    require(argv[4]==producer.get('path') and bool(producer.get('sha256')) and
            runner.receipt.get('inputs',{}).get(argv[4])==producer['sha256'] and
            direct.sha(Path(argv[4]))==producer['sha256'],'producer is not the authenticated instance')

def validate_terminal(status,guard,worker,stderr,*,worker_argv,pins,producer_path,producer_sha,work,cleanup):
    require(type(status)is int and status==0 and stderr==b'' and type(guard)is dict and
            guard.get('phase')=='terminal' and guard.get('reason')=='target exited' and
            guard.get('complete')is True and guard.get('cleanup_complete')is True and
            type(guard.get('target_exit_code'))is int and guard['target_exit_code']==0 and
            guard.get('survivors')==[] and guard.get('signals')==[] and guard.get('cancel_signals')==[] and
            'error' not in guard and 'cleanup_error' not in guard and (worker is None or type(worker)is dict and worker.get('complete')is True),
            'complete suite and owned-tree terminal evidence required')
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
    if worker is not None:
        require(worker.get('input_pins')==pins and type(worker.get('input_pins'))is dict and
                worker.get('producer_receipt_path')==producer_path and
                worker.get('producer_receipt_sha256')==producer_sha,
                'worker source and authenticated producer receipt binding required')

def fresh_destinations(output, suite):
    guard=output/(suite.name+'-supervisor.json')
    receipt=(output/(suite.name+'-batch-worker.json') if suite.worker
             else output/suite.name/'receipt.json')
    paths=(output/suite.name, guard, receipt, guard.with_suffix('.tmp'), receipt.with_suffix('.tmp'),
           output/(suite.name+'.stdout'), output/(suite.name+'.stderr'))
    for path in paths:
        require(not os.path.lexists(path),'fresh suite destination required: '+str(path))
    return guard,receipt

def managed(runner,suite,pins,argv):
    guard,worker_receipt=fresh_destinations(runner.output,suite)
    require_pidfd()
    require(snapshot(suite)==pins,'suite inputs changed during execution')
    worker_argv=[sys.executable,'-B',str(HERE/(suite.worker or suite.script)),*argv[3:]]
    actual=[sys.executable,'-B',str(HERE/'crc_process_supervisor.py'),'--receipt',str(guard),
            '--work-seconds',str(suite.work),'--cleanup-seconds',str(suite.cleanup),
            *worker_argv]
    entry=dict(name=suite.name,argv=argv,execution_argv=actual,input_pins=pins,state='running',
               original_timeout_seconds=600,work_seconds=suite.work,cleanup_seconds=suite.cleanup,timeout_seconds=suite.outer,
               scope='real suite commands and explicit batch projections; supervisor owns descendant cleanup')
    runner.receipt['commands'].append(entry); runner.save()
    process=None; fd=None; stdout=stderr=b''; old={}; started=time.monotonic()
    def cancel(sig,frame): raise KeyboardInterrupt(suite.name+' cancelled: '+str(sig))
    try:
        for sig in (signal.SIGINT,signal.SIGTERM): old[sig]=signal.signal(sig,cancel)
        mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        try:
            process=subprocess.Popen(actual,cwd=runner.root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            fd=os.pidfd_open(process.pid)
        finally: signal.pthread_sigmask(signal.SIG_SETMASK,mask)
        stdout,stderr=process.communicate(timeout=suite.outer)
        require(type(process.returncode)is int and process.returncode==0,
                suite.name+' supervisor failed; see its receipt')
        entry['supervisor']=json.loads(guard.read_text()); entry['worker']=json.loads(worker_receipt.read_text())
        validate_terminal(process.returncode,entry['supervisor'],entry['worker'] if suite.worker else None,stderr,
            worker_argv=worker_argv,pins=pins,producer_path=argv[4],
            producer_sha=runner.receipt['producer']['sha256'],work=suite.work,cleanup=suite.cleanup)
        if not suite.worker:
            require(entry['worker'].get('complete') is True and
                    entry['worker'].get('producer_sha256')==runner.receipt['producer']['sha256'],
                    'complete CRC suite and producer binding required')
        require(snapshot(suite)==pins,'suite source drift')
        require(direct.sha(Path(argv[4]))==runner.receipt['producer']['sha256'],'producer receipt drift')
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
                try: stdout,stderr=process.communicate(timeout=suite.cancel_grace)
                except subprocess.TimeoutExpired as capture:
                    entry['cleanup_unverified']='supervisor cancel grace expired; forced kill cannot contain descendants'
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
                    path=runner.output/(suite.name+'.'+label); path.write_bytes(raw)
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

class ManagedRunner(direct.CommandRunner):
    """Ordinary runner extension; no frozen loaders or successor composition."""
    def run(self,name,command,*,overrides=None,status=0,expected=None,timeout=180):
        suite=SUITES.get(name)
        if suite is None:
            return super().run(name,command,overrides=overrides,status=status,expected=expected,timeout=timeout)
        argv=list(map(str,command))
        validate_route(self,suite,argv,overrides,status,expected,timeout)
        return managed(self,suite,snapshot(suite),argv)
