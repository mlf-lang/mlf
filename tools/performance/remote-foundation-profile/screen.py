#!/usr/bin/env python3
"""Fresh-runner Foundation15 main-only diagnostic; not native fixed point.
Run under the packaged outer subreaper with 600 s work + terminal cleanup.
All three calls are retained; no calls are performance samples.
"""
import argparse, hashlib, json, os, resource, signal, stat, subprocess, sys, time, traceback
from pathlib import Path
import artifact_checks as checks
HERE=Path(__file__).resolve().parent
MODULES=['Fresh','Host','IndexVec','IntMap','IntRank','IntSet','IntTree','Map','Regex','ST','Set','Std','Types','Unicode','Version']
SEQUENCE=[('qual-A','A'),('profile-A','A')]
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
def check_work(path,profile=False):
    need({p.name for p in path.iterdir()}==({'cwd','home','tmp','unit.mlfci','unit.mlfco','unit.queries','query-cache'} | ({'unit.query-profile'} if profile else set())),'work artifact set')
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
    if name=='profile-A': env['MLF_QUERY_PROFILE']='1'
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
    return dict(name=name,measurement=metric,supervisor=receipt,qualification=name.startswith('qual-'),sample=False)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--selftest',action='store_true'); ap.add_argument('--root'); ap.add_argument('--sources'); ap.add_argument('--a'); args=ap.parse_args()
    if args.selftest: return selftest()
    need(all([args.root,args.sources,args.a]),'root/sources/a required')
    from bounded import ci_only
    ci=ci_only()
    root=Path(args.root).resolve(); sources=Path(args.sources).resolve(); producers={'A':Path(args.a).resolve()}
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
        for side in ['A']:
            expected_producer=build['builds'][side]['producer']; actual=pin(producers[side])
            need(str(producers[side])==expected_producer['resolved'] and all(actual[k]==expected_producer[k] for k in ['bytes','mode','sha256']),'producer differs from fresh build')
        runtime=build['builds']['A']['runtime']; need(runtime,'missing runtime evidence')
        source_pin_path=HERE/'foundation-input-pins.json'; source_pins=json.loads(source_pin_path.read_text())['rows']
        modules=[]
        for suffix in MODULES:
            p=sources/'libraries/mlf-foundation/Bootstrap'/(suffix+'.hs'); need(p.is_file(),'missing Foundation source '+str(p))
            matches=[r for r in source_pins if r['repo_path']==str(p.relative_to(sources))]; need(len(matches)==1,'Foundation source pin absent/duplicate')
            row=matches[0]['A']; actual=pin(p); need(actual['bytes']==row['bytes'] and actual['sha256']==row['sha256'],'Foundation source identity mismatch'); modules.append(('Bootstrap.'+suffix,p))
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
        work=out/'work'; spec=out/'foundation.spec'
        spec.write_text(pack(['MLF-CRATE-1','mlf-foundation/0.3.0/library','','false',pack([pack([m,str(p)])for m,p in modules]),pack([str(builtin_prefix)+'.mlfci']),str(work/'query-cache'),str(out/'forbidden-installer/unit')]))
        fixed[str(spec)]=pin(spec); write(out/'final-input-pins.json',fixed)
        expected=None; metrics={}
        for name,side in SEQUENCE:
            fresh(work); need(not os.path.lexists(out/'forbidden-installer'),'installer unexpectedly used')
            row=target(out,name,producers[side],spec,work,verify); row['side']=side
            need(not os.path.lexists(out/'forbidden-installer'),'installer unexpectedly used'); check_work(work,name=='profile-A')
            if name=='qual-A':
                expected=checks.full_artifact(work/'unit',work/'query-cache',contract,deadline); row['qualification_summary']=expected
            else: row['raw_equality']=compare_all(work,out/'evidence-qual-A',expected,contract)
            if name=='profile-A':
                phases=json.loads((work/'unit.query-profile').read_text())
                need(set(phases)=={'graph_ms','load_ms','infer_ms','finish_ms','output_ms','publish_ms'},'profile field set')
                need(all(type(v) is int and v>=0 for v in phases.values()) and sum(phases.values())>0,'invalid profile clocks')
                row['phase_clocks_ms']=phases
                row['phase_clock_sum_ms']=sum(phases.values())
            before=inventory(work); work.rename(out/('evidence-'+name)); need(inventory(out/('evidence-'+name))==before,'rename preservation failed')
            if name=='qual-A': reference_inventory=before; write(out/'reference-summary.json',expected)
            result['targets'].append(row); metrics[name]=row['measurement']; verify(); bound(out)
        result.update(complete=True,decision='DIAGNOSTIC_ONLY',performance_claim=False)
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
    need(SEQUENCE==[('qual-A','A'),('profile-A','A')],'fixed main diagnostic')
    need(len(MODULES)==15 and len(set(MODULES))==15,'Foundation source closure')
    input_rows=json.loads((HERE/'foundation-input-pins.json').read_text())['rows']
    expected=['libraries/mlf-foundation/Bootstrap/'+m+'.hs' for m in MODULES]
    need(sorted(r['repo_path'] for r in input_rows)==sorted(expected),'exact Foundation input pin set')
    need(all(r['A']['bytes']>0 and len(r['A']['sha256'])==64 for r in input_rows),'Foundation pin shape')
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

