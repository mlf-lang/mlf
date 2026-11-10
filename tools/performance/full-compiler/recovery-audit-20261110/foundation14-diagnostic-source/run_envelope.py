#!/usr/bin/env python3
"""Own the sole heavy lock, unchanged watchdog, and post-exit cleanup proof."""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import types

HERE=Path(__file__).resolve().parent
LOCK=Path('/workspace/scratch/3f83e2ebe290/.astra-resource-locks/heavy.lock')
WATCHDOG='5368803eb84dabc9dcefa89225b6ff56afd637e105f227bade15e40f9a5e923f'
HELPER='0d11b29419a32fc9832096951aa085cc317c8a304b9db110ee96ba411a4ce7cc'

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def require(v,m):
    if not v:raise ValueError(m)

def table():
    rows={}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            v=(p/'stat').read_text().split(') ',1)[1].split()
            rows[int(p.name)]=dict(ppid=int(v[1]),pgid=int(v[2]),session=int(v[3]),starttime=v[19],state=v[0])
        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['SETUP','QD']);p.add_argument('source',type=Path)
    p.add_argument('handoff',type=Path);p.add_argument('digest');p.add_argument('output',type=Path)
    a=p.parse_args();require(sha(a.handoff)==a.digest,'handoff hash')
    handoff=json.loads(a.handoff.read_text());require(handoff['source']==str(a.source),'source binding')
    for name,key in [('run_diagnostic.py','controller_sha256'),('run-phase.sh','launcher_sha256'),('run_envelope.py','envelope_sha256')]:
        require(sha(HERE/name)==handoff[key],'reviewed execution source '+name)
    require(sha(a.source/'tools/shared/resource_watchdog.py')==WATCHDOG,'unchanged watchdog')
    hp=a.source/'tools/performance/a1-private-index/helper.py';require(sha(hp)==HELPER,'unchanged lock helper')
    H=types.ModuleType('lock_helper');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    plan=H.load(handoff['plan']['path']);require(sha(handoff['plan']['path'])==handoff['plan']['sha256'],'frozen plan')
    require(a.output==Path(plan['workspace'])/('thin-setup' if a.phase=='SETUP' else 'execution'),'phase output')
    for parent in [a.output,*a.output.parents]:require(not parent.is_symlink(),'symlink phase path')
    require(not a.output.exists() and not a.output.is_symlink(),'fresh phase root required')
    require(Path(sys.executable).resolve()==Path(H.load(Path(plan['producer'])/'receipt.json')['orchestrator']['path']),'exact producer Python')
    seconds={'SETUP':120,'QD':420}[a.phase]
    worker=[sys.executable,'-B',str(a.source/'tools/performance/process-spawn/with_scope.py'),
            sys.executable,'-B',str(HERE/'run_diagnostic.py'),a.phase,'--handoff',str(a.handoff),
            '--handoff-sha256',a.digest,'--output',str(a.output)]
    command=[sys.executable,'-B',str(a.source/'tools/shared/resource_watchdog.py'),'--seconds',str(seconds),
             '--address-space-mib','6144','--rss-mib','5120','--disk-free-mib','5120','--max-output-mib','4096',str(a.output),*worker]
    rec=dict(format='baseline-gc-envelope-v1',complete=False,phase=a.phase,output=str(a.output),command=command,
             worker_command=worker,handoff=dict(path=str(a.handoff),sha256=a.digest),
             controller_sha256=sha(HERE/'run_diagnostic.py'),envelope_sha256=sha(__file__),
             budget_seconds=seconds,started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    tracked={};proc=None;created=False;leader_start=None
    def save():
        if created:H.save(a.output/'envelope.json',rec)
    def observe():
        rows=table();owned={pid for pid,v in tracked.items() if pid in rows and rows[pid]['starttime']==v['starttime']}
        if proc and leader_start is not None and proc.pid in rows and rows[proc.pid]['starttime']==leader_start:
            owned.add(proc.pid)
        while True:
            new={pid for pid,v in rows.items() if v['ppid'] in owned}-owned
            if not new:break
            owned|=new
        for pid in owned:tracked[pid]=rows[pid]
        return {pid:rows[pid] for pid in owned if rows[pid]['state']!='Z'}
    def stop():
        for sig in [signal.SIGTERM,signal.SIGKILL]:
            for pid in observe():
                try:os.kill(pid,sig)
                except ProcessLookupError:pass
            time.sleep(.2)
        if proc and proc.poll() is None:proc.wait(timeout=3)
    def interrupted(signum,frame):raise RuntimeError('envelope interrupted '+str(signum))
    signal.signal(signal.SIGTERM,interrupted)
    try:
        with LOCK.open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            a.output.parent.mkdir(mode=0o700,parents=True,exist_ok=True);a.output.mkdir(mode=0o700);created=True;save()
            try:
                with (a.output/'watchdog.stdout').open('wb') as log:
                    proc=subprocess.Popen(command,cwd=a.source,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                    rows=table();require(proc.pid in rows,'watchdog process identity unavailable')
                    leader_start=rows[proc.pid]['starttime'];tracked[proc.pid]=rows[proc.pid]
                    rec['watchdog_pid']=proc.pid;rec['watchdog_starttime']=leader_start;save()
                    while proc.poll() is None:observe();time.sleep(.1)
                rec['watchdog_exit']=proc.returncode;rec['remaining_after_watchdog']=observe()
                if rec['remaining_after_watchdog']:stop()
                rec['remaining_after_cleanup']=observe();require(not rec['remaining_after_cleanup'],'remaining descendants')
                bounded=H.load(a.output/'bounded-receipt.json')
                rec['bounded_receipt_sha256']=sha(a.output/'bounded-receipt.json')
                require(bounded['command']==worker,'bounded actual command binding')
                rec['work_receipt_sha256']=sha(a.output/'receipt.json')
                work=H.load(a.output/'receipt.json')
                require(work['phase']==a.phase,'work phase binding')
                with H.SerialLock(a.source/'.mlf-build'):rec['internal_lock_reacquired']=True
                rec['guarded_success']=proc.returncode==0 and bounded['complete'] is True and bounded['reason'] is None and work['complete'] is True and not rec['remaining_after_watchdog']
            finally:
                if proc and (proc.poll() is None or observe()):stop()
                rec['final_live_descendants']=observe()
                fcntl.flock(lock,fcntl.LOCK_UN)
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);rec['shared_lock_reacquired']=True;fcntl.flock(lock,fcntl.LOCK_UN)
            rec['complete']=bool(rec.get('guarded_success') and not rec['final_live_descendants'])
    except BaseException as error:
        rec.update(error=repr(error),complete=False)
        if proc and (proc.poll() is None or observe()):stop()
    finally:
        rec['tracked_processes']=tracked;save()
    require(rec['complete'],'phase failed; retain envelope/guard/work receipts, no automatic retry')
    print(json.dumps({k:rec[k] for k in ['phase','complete','bounded_receipt_sha256','work_receipt_sha256','internal_lock_reacquired','shared_lock_reacquired']}))

if __name__=='__main__':main()
