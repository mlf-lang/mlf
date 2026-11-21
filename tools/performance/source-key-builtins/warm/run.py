#!/usr/bin/env python3
"""Foundation warm profile on one compiler and one cache. See PROTOCOL.md."""
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BINARY = Path(sys.argv[1]).resolve(strict=True)
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True,exist_ok=False)
REFERENCE = Path(sys.argv[3]).resolve(strict=True) if len(sys.argv)>3 else None
ORDER = ['P','C','D','D','C','P'] if REFERENCE else ['P','C','D', 'C','D','P', 'D','P','C']

def require(value,message):
    if not value:
        raise RuntimeError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def pack(xs):
    return ''.join(f'{len(x)}:{x}' for x in xs)

def run(argv, label):
    require(shutil.disk_usage(OUT).free >= 4*1024**3,'disk floor')
    with (OUT/(label+'.log')).open('xb') as log:
        start = time.monotonic_ns()
        proc = subprocess.Popen([BINARY,*argv],cwd=OUT,stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,stderr=log,start_new_session=True)
        def stop():
            try:
                os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
        timer = threading.Timer(900,stop)
        timer.start()
        try:
            _,status,u = os.wait4(proc.pid,0)
            proc.returncode = os.waitstatus_to_exitcode(status)
        except BaseException:
            stop()
            proc.wait()
            raise
        finally:
            timer.cancel()
        wall = time.monotonic_ns()-start
    require(proc.returncode==0,f'{label}: exit {proc.returncode}; see {log.name}')
    return dict(wall_ns=wall,cpu_user_s=u.ru_utime,cpu_sys_s=u.ru_stime,
                peak_rss_bytes=u.ru_maxrss*(1 if sys.platform=='darwin' else 1024),
                inblock=u.ru_inblock,outblock=u.ru_oublock)

def detail(log):
    rows = {}
    for line in log.read_text().splitlines():
        name, calls, inclusive, exclusive = line.split()
        require(name not in rows and (name=='session' or name.startswith('session/')),'bad span: '+name)
        rows[name] = list(map(int,(calls,inclusive,exclusive)))
    sums = {}
    for name,(n,total,self_ns) in rows.items():
        require(n>0 and total>=self_ns>=0,'invalid time: '+name)
        if '/' in name:
            parent = name.rsplit('/',1)[0]
            require(parent in rows,'missing parent: '+parent)
            sums[parent] = sums.get(parent,0)+total
    for name,(n,total,self_ns) in rows.items():
        require(total==self_ns+sums.get(name,0),'unreconciled timer: '+name)
    def count(leaf):
        return sum(row[0] for name,row in rows.items() if name.split('/')[-1]==leaf)
    for name,n in [('hit',504),('finish',504),('raw.record',504),('key.equal',504),
                   ('xmlf.bindings',504),('scratch.force',504),('group.prepare',504),
                   ('final.write',1),('final.report',1),('session',1)]:
        require(count(name)==n,f'{name} count {count(name)} expected {n}')
    return rows

def coarse(log):
    cols = [row.split() for row in log.read_text().splitlines()]
    keys = [list(map(int,row[1:])) for row in cols if row[0]=='key']
    require(len(keys)==504 and len(cols)==504*4,'coarse probe counts')
    data=dict(key_scalars=sum(k[0] for k in keys),key_force_ns=sum(k[1] for k in keys),
              key_write_ns=sum(k[2] for k in keys))
    for name in ['read+sha','read+decode','prepared']:
        values = [int(row[1]) for row in cols if row[0]==name]
        require(len(values)==504,'coarse coverage: '+name)
        data[name+'_ns']=sum(values)
    return data

source = (REFERENCE or OUT)/'source'
if not REFERENCE:
    shutil.copytree(ROOT/'libraries/mlf-foundation',source)
mods = json.loads((source/'mlf-package.json').read_text())['library']['modules']
sources = {k:sha((source/v).read_bytes()) for k,v in mods.items()}
historical = json.loads((HERE.parent/'results-20261103.json').read_text())['paired']
require(len(mods)==14 and sources==historical['modules'],'Foundation input differs from the previous study')
builtin,cache,spec,prefix = (REFERENCE or OUT)/'builtin/unit',OUT/'cache',OUT/'crate.spec',OUT/'final'
entries = pack(pack([name,str(source/v)]) for name,v in sorted(mods.items()))
spec.write_text(pack(['MLF-CRATE-1','mlf-foundation/0.3.0/library','','false',entries,'',str(cache),str(builtin)]))
record = dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              compiler_sha256=sha(BINARY.read_bytes()),ghc=subprocess.check_output(['ghc','--numeric-version'],text=True).strip(),
              platform=platform.platform(),modules=sources,order=ORDER,samples=[],complete=False)

def save():
    (OUT/'results.json').write_text(json.dumps(record,indent=2)+'\n')

if REFERENCE:
    reference=json.loads((REFERENCE/'results.json').read_text())
    require(reference['complete'] and reference['compiler_sha256']!=record['compiler_sha256'],'fresh focused executable')
    record['primary_compiler_sha256']=reference['compiler_sha256']
else:
    run(['builtin',builtin],'builtin')
builtin_bytes={suffix:builtin.with_suffix(suffix).read_bytes() for suffix in ['.mlfci','.mlfco']}
record['cold']=run(['P',spec,prefix],'cold')
original = {e:prefix.with_suffix(e).read_bytes() for e in ['.mlfci','.mlfco']}
if REFERENCE:
    require(all((REFERENCE/'final').with_suffix(k).read_bytes()==v for k,v in original.items()),'focused output differs from primary')
cold = json.loads(prefix.with_suffix('.queries').read_bytes())
require((cold['inferred_groups'],cold['reused_groups'])==(504,0),'cold SCC inventory')
group_image = lambda r: [(g['id'],g['members'],g['semantic_fingerprint'],g['query_key']) for g in r['groups']]
population = group_image(cold)
require(len(population)==len(set(g[0] for g in population))==504,'invalid SCC population')
records = {f.name:f.read_bytes() for f in cache.iterdir()}
def immutable_stats():
    return {f.name:(f.stat().st_ino,f.stat().st_size,f.stat().st_mtime_ns)
            for f in cache.iterdir() if f.suffix in ('.mlfqc','.mlfq')}
stats = immutable_stats()
require({k for k in records if k.endswith('.mlfq')}=={g[3]+'.mlfq' for g in population},'active record set')
require(len([k for k in records if k.endswith('.mlfqc')])==83,'context carrier count')
record.update(cache_bytes=sum(map(len,records.values())),
              artifact_bytes={k:len(v) for k,v in original.items()},
              artifact_sha256={k:sha(v) for k,v in original.items()},
              query_keys_sha256=sha('\n'.join(g[3] for g in population).encode()))
save()

def verify():
    require(records.keys()=={p.name for p in cache.iterdir()} and immutable_stats()==stats,'cache files changed')
    require(all((cache/k).read_bytes()==v for k,v in records.items()),'cache contents changed')
    require(all(builtin.with_suffix(k).read_bytes()==v for k,v in builtin_bytes.items()),'builtin changed')
    require({k:sha((source/v).read_bytes()) for k,v in mods.items()}==sources,'inputs changed')

warm_report = None
for sample,mode in enumerate(['P','C','D',*ORDER]):
    verify()
    label=f'{sample:02}-{mode}'
    usage=run([mode,spec,prefix],label)
    verify()
    require(all(prefix.with_suffix(k).read_bytes()==v for k,v in original.items()),'final bytes changed: '+label)
    raw=prefix.with_suffix('.queries').read_bytes()
    if warm_report is None:
        warm_report=raw
    report=json.loads(raw)
    require(raw==warm_report and group_image(report)==population and all(g['cached'] for g in report['groups'])
            and (report['inferred_groups'],report['reused_groups'])==(0,504),'warm group mismatch: '+label)
    row=dict(preflight=sample<3,arm=mode,**usage)
    log=OUT/(label+'.log')
    if mode=='D':
        row['spans']=detail(log)
        require(row['spans']['session'][1]<=row['wall_ns'],'session exceeds process')
    elif mode=='C':
        row['coarse']=coarse(log)
    else:
        require(log.stat().st_size==0,'unexpected plain diagnostics')
    record['samples'].append(row)
    save()
    print(label,round(usage['wall_ns']/1e9,3),flush=True)
record['warm_report_sha256']=sha(warm_report)
record['complete']=True
save()
