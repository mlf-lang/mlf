#!/usr/bin/env python3
"""Fresh-runner Async9 qualification plus fixed ABBA three times; not native fixed point.
Run under the packaged outer subreaper with 600 s work + terminal cleanup.
All fifteen calls are retained; seed and two qualifications are never samples.
"""
import argparse, hashlib, json, os, resource, signal, stat, subprocess, sys, time, traceback
from pathlib import Path
import artifact_checks as checks
HERE=Path(__file__).resolve().parent
MODULES=[('Async.Process', 'libraries/mlf-async/Async/Process.hs'), ('Async.Process.Internal', 'libraries/mlf-async/Async/Process/Internal.hs'), ('Async.Task', 'libraries/mlf-async/Async/Task.hs'), ('Async.Task.Core', 'libraries/mlf-async/Async/Task/Core.hs'), ('Async.Task.Internal', 'libraries/mlf-async/Async/Task/Internal.hs'), ('Bootstrap.IndexVec', 'libraries/mlf-foundation/Bootstrap/IndexVec.hs'), ('Bootstrap.Std', 'libraries/mlf-foundation/Bootstrap/Std.hs'), ('Bootstrap.Types', 'libraries/mlf-foundation/Bootstrap/Types.hs'), ('Bootstrap.Version', 'libraries/mlf-foundation/Bootstrap/Version.hs')]
PAIRS=[('A'+str(i),'C'+str(i)) for i in range(1,7)]
SEQUENCE=[('qual-A','A'),('qual-C','C')]+[(side+str(i),side) for j in [1,3,5] for i,side in [(j,'A'),(j,'C'),(j+1,'C'),(j+1,'A')]]
START=time.monotonic(); CANCEL=False; QUIESCENT=True

def need(ok,msg):
    if not ok: raise RuntimeError(msg)
def stop(*_):
    global CANCEL
    CANCEL=True
def deadline(): need(not CANCEL and time.monotonic()-START<590,'screen work/post deadline')
def write(path,value):
    with Path(path).open('x') as f: json.dump(value,f,indent=2); f.write('\n')
def pack(fields): return ''.join(str(len(x))+':'+x for x in fields)
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''): deadline(); h.update(chunk)
    return h.hexdigest()
def pin(path):
    path=Path(path); s=path.lstat(); need(stat.S_ISREG(s.st_mode),'nonregular pin '+str(path))
    return dict(bytes=s.st_size,mode=stat.S_IMODE(s.st_mode),mtime_ns=s.st_mtime_ns,sha256=digest(path))
def inventory(root):
    result={}
    for base,dirs,files in os.walk(root,followlinks=False):
        for n in dirs:
            p=Path(base)/n; need(stat.S_ISDIR(p.lstat().st_mode),'non-directory tree entry')
        for n in files:
            p=Path(base)/n; result[str(p.relative_to(root))]=pin(p)
    return result

def bound(root):
    count=total=0
    for base,dirs,files in os.walk(root,followlinks=False):
        for name in dirs:
            need(stat.S_ISDIR((Path(base)/name).lstat().st_mode),'special output directory')
        for name in files:
            deadline(); p=Path(base)/name; s=p.lstat()
            need(stat.S_ISREG(s.st_mode),'special output file')
            count+=1; total+=s.st_size
            need(s.st_size<=16*1024**2 and count<=50000 and total<=2*1024**3,'output budget')
    return dict(files=count,bytes=total)
def limits():
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(80,80))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def fresh(path):
    path.mkdir()
    for n in ['cwd','home','tmp']: (path/n).mkdir()
def check_work(path):
    need({p.name for p in path.iterdir()}=={'cwd','home','tmp','unit.mlfci','unit.mlfco','unit.queries','query-cache'},'work artifact set')
    for n in ['cwd','home','tmp']: need(not any((path/n).iterdir()),'unexpected cwd/home/tmp outputs')
def compare_all(work,reference,expected,contract):
    actual=checks.full_artifact(work/'unit',work/'query-cache',contract,deadline)
    for ext in ['.mlfci','.mlfco','.queries']: checks.same_raw(reference/('unit'+ext),work/('unit'+ext),deadline)
    need(actual==expected,'full decoded result summary mismatch')
    rd=reference/'query-cache/query-graph-v2/results'; wd=work/'query-cache/query-graph-v2/results'
    rn={p.name for p in rd.iterdir()}; wn={p.name for p in wd.iterdir()}
    need(rn==wn,'complete raw result filename-set mismatch')
    for name in sorted(rn): checks.same_raw(rd/name,wd/name,deadline)
    return dict(complete_raw_files=len(rn),selected_groups=len(actual['raw_group_mappings']),coverage=actual['coverage'])
def target(out,name,binary,spec,work,verify):
    global QUIESCENT
    deadline(); verify(); bound(out)
    log=out/'steps'/name; log.mkdir()
    command=[sys.executable,'-B',str(HERE/'crc_process_supervisor.py'),'--receipt',str(log/'supervisor.json'),'--work-seconds','60','--cleanup-seconds','10',sys.executable,'-B',str(HERE/'measure.py'),str(log/'measurement.json'),str(binary),'--compile-crate',str(spec),'-o',str(work/'unit')]
    env=dict(PATH='/usr/bin:/bin',HOME=str(work/'home'),TMPDIR=str(work/'tmp'),TMP=str(work/'tmp'),LANG='C.UTF-8',LC_ALL='C.UTF-8',GIT_OPTIONAL_LOCKS='0')
    write(log/'command.json',dict(argv=command,cwd=str(work/'cwd'),env=env,limits=dict(AS=4*1024**3,FSIZE=16*1024**2,CPU=80)))
    proc=None; error=None; terminal=False; started=time.monotonic()
    with (log/'stdout').open('xb') as stdout,(log/'stderr').open('xb') as stderr:
        try:
            proc=subprocess.Popen(command,cwd=work/'cwd',env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True,preexec_fn=limits)
            QUIESCENT=False
            while proc.poll() is None:
                deadline(); need(time.monotonic()-started<71,'supervisor total deadline')
                time.sleep(.1) # No scanning/hashing while the compiler runs.
            terminal=True
            need(proc.returncode==0,'supervisor nonzero')
        except BaseException as exc: error=repr(exc)
        finally:
            if proc is not None and proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try: proc.wait(timeout=12)
                except subprocess.TimeoutExpired: pass
            terminal=proc is not None and proc.poll() is not None
            receipt=None
            if terminal and (log/'supervisor.json').exists():
                receipt=json.loads((log/'supervisor.json').read_text())
                QUIESCENT=receipt.get('cleanup_complete') is True and receipt.get('phase')=='terminal' and receipt.get('survivors')==[]
            write(log/'screen-step.json',dict(error=error,supervisor_terminal=terminal,owned_quiescent=QUIESCENT,elapsed_seconds=time.monotonic()-started))
    need(QUIESCENT,'inner cleanup not proven; outer subreaper must finish')
    need(error is None,error)
    need(receipt.get('complete') is True and receipt.get('reason')=='target exited' and receipt.get('target_exit_code')==0,'target not clean')
    need(not receipt.get('signals') and not receipt.get('cancel_signals'),'unexpected cleanup signal')
    reaped=receipt.get('reaped',[])
    need(sum(r['pid']==receipt['root_pid'] for r in reaped)==1 and all(r['status']==0 for r in reaped),'reaped status')
    need((log/'stdout').stat().st_size==0 and (log/'stderr').stat().st_size==0,'target stdout/stderr nonempty')
    metric=json.loads((log/'measurement.json').read_text())
    need(metric['complete'] is True and metric['exit_code']==0 and metric['raw_wait_status']==0 and metric['wall_ns']>0 and metric['maxrss_KiB']>0,'invalid metric')
    verify(); bound(out)
    return dict(name=name,measurement=metric,supervisor=receipt,qualification=name.startswith('qual-'),sample=name in [n for pair in PAIRS for n in pair])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--selftest',action='store_true'); ap.add_argument('--root'); ap.add_argument('--sources'); ap.add_argument('--a'); ap.add_argument('--c'); args=ap.parse_args()
    if args.selftest: return selftest()
    need(all([args.root,args.sources,args.a,args.c]),'root/sources/a/c required')
    from bounded import ci_only
    ci=ci_only()
    root=Path(args.root).resolve(); sources=Path(args.sources).resolve(); producers={'A':Path(args.a).resolve(),'C':Path(args.c).resolve()}
    out=root/'artifacts'/'screen'; out.mkdir(parents=True,exist_ok=False)
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    result=dict(complete=False,native=False,new_runner=True,ci=ci,targets=[],errors=[],descriptive_only=True)
    fixed={}; runtime=[]; builtin=None; reference_inventory=None; seed_inventory=None
    def verify():
        deadline()
        for p,row in fixed.items(): need(pin(Path(p))==row,'immutable input changed '+p)
        for row in runtime:
            p=Path(row['reported_path']); need(str(p.resolve())==row['resolved'],'runtime resolution changed')
            actual=pin(p.resolve()); need(all(actual[k]==row[k] for k in ['bytes','mode','sha256']),'runtime bytes changed')
        if builtin is not None: need(inventory(out/'builtin')==builtin,'shared builtin changed')
        if seed_inventory is not None: need(inventory(out/'seed')==seed_inventory,'seed artifacts changed')
        if reference_inventory is not None: need(inventory(out/'evidence-qual-A')==reference_inventory,'qualification reference changed')
    try:
        (out/'steps').mkdir()
        build_path=root/'artifacts/build-receipt.json'; build=json.loads(build_path.read_text())
        need(build.get('complete') is True and build.get('cleanup') is True and build.get('within_whole') is True and not build.get('errors'),'fresh build receipt incomplete')
        for side in ['A','C']:
            expected_producer=build['builds'][side]['producer']; actual=pin(producers[side])
            need(str(producers[side])==expected_producer['resolved'] and all(actual[k]==expected_producer[k] for k in ['bytes','mode','sha256']),'producer differs from fresh build')
        need(build['builds']['A']['runtime']==build['builds']['C']['runtime'],'different producer runtimes'); runtime=build['builds']['A']['runtime']; need(runtime,'missing runtime evidence')
        source_pin_path=HERE/'async-input-pins.json'; source_pins=json.loads(source_pin_path.read_text())['rows']
        modules=[]
        for module,relative in MODULES:
            p=sources/relative; need(p.is_file(),'missing Async9 source '+str(p))
            matches=[r for r in source_pins if r['repo_path']==str(p.relative_to(sources))]; need(len(matches)==1,'Async9 source pin absent/duplicate')
            row=matches[0]['A']; actual=pin(p); need(actual['bytes']==row['bytes'] and actual['sha256']==row['sha256'],'Async9 source identity mismatch'); modules.append((module,p))
        contract_path=HERE/'query-contract.json'; contract=json.loads(contract_path.read_text())
        for p in [build_path,source_pin_path,*producers.values(),*[p for _,p in modules],contract_path,*[HERE/n for n in ['screen.py','artifact_checks.py','crc_process_supervisor.py','measure.py']]]: fixed[str(p)]=pin(p)
        write(out/'initial-pins.json',fixed)
        write(out/'scope.json',dict(sequence=[['seed','A']]+SEQUENCE,source_root=str(sources),source_modules=[m for m,_ in modules],producers={k:str(v)for k,v in producers.items()},screen_work_seconds=590,outer_required_work_seconds=600,each_target_seconds=60,cleanup_seconds=10,native=False,os_cache='not flushed',application_cache='fresh each call',timing='exact child fork/exec through wait4; not pure CPU or tree RSS',raw_equality='complete CI/CO/query bytes and ALL result file names/bytes; no normalization'))
        builtin_prefix=out/'builtin'/'unit'; seed=out/'seed'; fresh(seed)
        seed_spec=out/'seed.spec'; seed_spec.write_text(pack(['MLF-CRATE-1','depth-cursor-seed/0.3.0/library','','false',pack([pack(['Bootstrap.Version',str(dict(modules)['Bootstrap.Version'])])]),'',str(seed/'query-cache'),str(builtin_prefix)]))
        fixed[str(seed_spec)]=pin(seed_spec)
        result['targets'].append(target(out,'seed',producers['A'],seed_spec,seed,verify)); check_work(seed)
        checks.wire_integrity(seed/'unit.mlfci',[3],deadline); checks.wire_integrity(seed/'unit.mlfco',[8],deadline)
        result['builtin']=checks.builtin_pair(builtin_prefix,deadline); builtin=inventory(out/'builtin')
        need(set(builtin)=={'unit.mlfci','unit.mlfco','unit.lock'},'unexpected builtin set'); write(out/'builtin-pins.json',builtin)
        seed_inventory=inventory(seed); write(out/'seed-inventory.json',seed_inventory)
        work=out/'work'; spec=out/'async.spec'
        spec.write_text(pack(['MLF-CRATE-1','mlf-async9-screen/0.3.0/library','','false',pack([pack([m,str(p)])for m,p in modules]),pack([str(builtin_prefix)+'.mlfci']),str(work/'query-cache'),str(out/'forbidden-installer/unit')]))
        fixed[str(spec)]=pin(spec); write(out/'final-input-pins.json',fixed)
        expected=None; metrics={}
        for name,side in SEQUENCE:
            fresh(work); need(not os.path.lexists(out/'forbidden-installer'),'installer unexpectedly used')
            row=target(out,name,producers[side],spec,work,verify); row['side']=side
            need(not os.path.lexists(out/'forbidden-installer'),'installer unexpectedly used'); check_work(work)
            if name=='qual-A':
                expected=checks.full_artifact(work/'unit',work/'query-cache',contract,deadline); row['qualification_summary']=expected
            else: row['raw_equality']=compare_all(work,out/'evidence-qual-A',expected,contract)
            before=inventory(work); work.rename(out/('evidence-'+name)); need(inventory(out/('evidence-'+name))==before,'rename preservation failed')
            if name=='qual-A': reference_inventory=before; write(out/'reference-summary.json',expected)
            result['targets'].append(row); metrics[name]=row['measurement']; verify(); bound(out)
        pairs=[]
        for a,c in PAIRS:
            pairs.append(dict(A=a,C=c,wall_C_over_A=metrics[c]['wall_ns']/metrics[a]['wall_ns'],RSS_C_over_A=metrics[c]['maxrss_KiB']/metrics[a]['maxrss_KiB']))
        product=1.0
        for pair in pairs: product*=pair['wall_C_over_A']
        geo=product**(1.0/len(pairs))
        result.update(pairs=pairs,geometric_wall_C_over_A=geo,decision='CONTINUE' if all(p['wall_C_over_A']<=1.03 and p['RSS_C_over_A']<=1.05 for p in pairs) and geo<=1 else 'STOP',complete=True)
    except BaseException as exc:
        result['errors'].append(dict(error=repr(exc),traceback=traceback.format_exc(limit=15)))
    finally:
        try:
            need(QUIESCENT,'skip postscan before cleanup'); verify(); result['output_budget']=bound(out); result['postchecks']=True
        except BaseException as exc: result['complete']=False; result['errors'].append(dict(postcheck=repr(exc))); result['postchecks']=False
        result['elapsed_seconds']=time.monotonic()-START; result['owned_quiescent']=QUIESCENT
        if CANCEL: result['complete']=False; result['errors'].append('cancelled')
        write(out/'screen-receipt.json',result)
    return 0 if result['complete'] else 1
def selftest():
    # No compiler/build/network or generated fixture execution.
    fixtures=[[],[''],['a:b','123','λ'],['MLF-CRATE-1',pack([pack(['M','/a:b'])]),'']]
    for row in fixtures: need(checks.unpack(pack(row))==row,'spec codec round-trip')
    need(len(SEQUENCE)==14 and len(set(n for n,_ in SEQUENCE))==14 and [x[1] for x in SEQUENCE[2:]]==['A','C','C','A']*3 and PAIRS==[('A'+str(i),'C'+str(i)) for i in range(1,7)],'fixed ABBA three times')
    need(len(MODULES)==9 and len(set(MODULES))==9,'Async9 source closure')
    input_rows=json.loads((HERE/'async-input-pins.json').read_text())['rows']
    expected=[p for m,p in MODULES]
    need(sorted(r['repo_path'] for r in input_rows)==sorted(expected),'exact Async9 input pin set')
    need(all(r['A']['bytes']>0 and len(r['A']['sha256'])==64 for r in input_rows),'Async9 pin shape')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='mlf-remote-screen-selftest-') as tmp:
        root=Path(tmp); p=root/'pin'; p.write_bytes(b'abc'); old=pin(p); p.write_bytes(b'abd'); need(pin(p)['sha256']!=old['sha256'],'pin sensitivity')
        check=root/'work'; fresh(check); need({x.name for x in check.iterdir()}=={'cwd','home','tmp'},'fresh work')
        try: fresh(check)
        except FileExistsError: pass
        else: raise RuntimeError('work overwrite accepted')
        symlink=root/'link'; symlink.symlink_to(p)
        try: pin(symlink)
        except RuntimeError: pass
        else: raise RuntimeError('pin symlink accepted')
    print(json.dumps(dict(complete=True,compiler_executed=False,cases=12)))
    return 0
if __name__=='__main__': sys.exit(main())

