"""Separately admitted controls within controller.BUDGETS; never invoked on import.

All Haskell compilation/execution uses Stage guards. Matching official RTS writer source and installed archive/version linkage
must be supplied in reviewed admission controls.rts_definition. Synthetic
Python controls are explicitly transport evidence, never compiler semantics.
"""
from pathlib import Path
import os
import re
import sys
import threading
import signal
import time
import guard
import oracles as O
import profile as allocation
HERE=Path(__file__).resolve().parent
FIXTURE_COMPILE_LINK_SECONDS=120  # Unchanged per-command cap, not the controls phase window.

def positive_producer(summary):
    rows=[r for r in summary['stacks'] if r['stack'][-1]['label']=='TOY_PRODUCER']
    O.require(sum(r['self_alloc'] for r in rows)>0,'delayed producer has no source allocation')
    O.require(not any(any(c['label']=='TOY_CONSUMER' for c in r['stack'][:-1]) for r in rows if r['self_alloc']),'producer allocation attributed beneath consumer')
    return sum(r['self_alloc'] for r in rows)

def tagged_alloc(summary,label):
    return sum(r['self_alloc'] for r in summary['stacks'] if r['stack'][-1]['label']==label)

def unit_delta(first,second):
    delta=tagged_alloc(second,'UNIT_ALLOCATION')-tagged_alloc(first,'UNIT_ALLOCATION')
    O.require(delta==65536,'known byte-array allocation delta is not 65536 raw units')
    return delta

def lock_owner(raw,st):
    for line in raw.splitlines():
        cols=line.split()
        if len(cols)<8 or cols[1:4]!=['POSIX','ADVISORY','WRITE']:continue
        try:
            major,minor,inode=cols[5].split(':')
            if (int(major,16),int(minor,16),int(inode))==(os.major(st.st_dev),os.minor(st.st_dev),st.st_ino):
                return int(cols[4])
        except ValueError:continue
    return None

def guarded(stage,label,argv,reports=(),maximum=15,cancel=None,before_child=None):
    stage.recheck();stage.counter+=1
    folder=stage.out/'commands'/('%03d-%s'%(stage.counter,label))
    from controller import BUDGETS
    remaining=BUDGETS['PROBE-CONTROLS']-(time.monotonic()-stage.start);O.require(remaining>0,'control deadline')
    if before_child is not None:before_child(folder)
    row=guard.run_child(list(map(str,argv)),cwd=stage.source,output=folder,seconds=min(remaining,maximum),reports=reports,bounded_root=stage.work,cancel_event=cancel)
    stage.record['commands'].append(dict(label=label,**row));stage.save()
    O.require(row.get('cleanup') is True and not row.get('test_only') and row.get('standalone_admission') is False,'control cleanup/guard invalid')
    if (folder/'guard.json').is_file():stage.output_pin(folder/'guard.json')
    for path in [folder/'stdout',folder/'stderr',folder/'guard-config.json']:
        if path.is_file():stage.output_pin(path)
    for pin in row.get('archived',{}).values():stage.output_pin(pin['path'])
    stage.recheck()
    return folder,row

def compile_fixture(stage,name,source):
    from controller import profile_flags,main_profile_flags
    source=O.regular(source);stage.record['input_pins'][str(source)]=O.sha(source)
    folder=stage.out/name;O.absent(folder);folder.mkdir()
    objects=stage.work/'build/objects'
    flags=profile_flags(stage.auth['flags'],stage.source,stage.producer,stage.work/'mirror',objects)
    compile_flags=main_profile_flags(flags,objects,folder)
    ghc=stage.auth['ghc']['path'];binary=folder/'program'
    stage.command('compile-'+name,[ghc,'-c','-fforce-recomp',*compile_flags,source,'-o',folder/'Main.p_o'],maximum=FIXTURE_COMPILE_LINK_SECONDS)
    stage.command('link-'+name,[ghc,*flags,'-rtsopts=ignoreAll','-with-rtsopts=-pj -po'+str(folder/'active')+' -s'+str(folder/'active.stats'),folder/'Main.p_o',*[objects/(n.replace('.','/')+'.p_o') for n in stage.manifest['emlf_modules']],stage.work/'build/host.o',stage.work/'build/supervisor.o','-o',binary],maximum=FIXTURE_COMPILE_LINK_SECONDS)
    for path in [binary,folder/'Main.p_o',folder/'Main.p_hi']:stage.output_pin(path)
    return binary,[folder/'active.prof',folder/'active.stats']

def run_fixture(stage,name,binary,reports,args,expected):
    for p in reports:O.absent(p)
    folder,row=guarded(stage,name,[binary,*args],reports,maximum=30)
    O.require(row['complete'] and (folder/'stdout').read_bytes()==expected and not (folder/'stderr').read_bytes(),'fixture result: '+name)
    raw=O.verify_pin(row['archived'][str(reports[0])]);summary=allocation.parse_profile(raw.read_bytes())
    O.require(summary['total_alloc']>0,'real nonzero JSON allocation required')
    stage.record.setdefault('semantic_controls',[]).append(dict(name=name,guard=O.pin(folder/'guard.json'),profile=O.pin(raw),summary=summary))
    stage.save();return summary

SESSION_CHILD_CODE = r"""
import json,os,sys,time
from pathlib import Path
os.setsid()
def start(pid):return Path('/proc/'+str(pid)+'/stat').read_text().rsplit(') ',1)[1].split()[19]
pid=os.getpid();parent=os.getppid();path=Path(sys.argv[1]);tmp=path.with_suffix('.tmp')
row=dict(pid=pid,start=start(pid),parent_pid=parent,parent_start=start(parent),session=os.getsid(pid),parent_session=os.getsid(parent))
with tmp.open('x') as f:json.dump(row,f);f.flush();os.fsync(f.fileno())
os.rename(tmp,path)
time.sleep(30)
"""
SESSION_PARENT_CODE = 'import subprocess,sys; subprocess.Popen([sys.executable,"-B","-c",sys.argv[1],sys.argv[2]]).wait()'

def observe_session_ready(marker,scope):
    row=O.load(marker)
    O.require(set(row)=={'pid','start','parent_pid','parent_start','session','parent_session'},'readiness schema')
    O.require(all(type(row[k]) is int and row[k]>0 for k in ['pid','parent_pid','session','parent_session']) and all(type(row[k]) is str and row[k].isdigit() for k in ['start','parent_start']),'readiness identities')
    table=guard.process_table();identities=[(row['pid'],row['start']),(row['parent_pid'],row['parent_start'])]
    O.require(row['pid']!=row['parent_pid'] and table.get(row['pid'],{}).get('ppid')==row['parent_pid'],'readiness parent relation')
    for pid,start in identities:
        O.require(table.get(pid,{}).get('start')==start and table[pid]['state']!='Z','live readiness identity')
        O.require(Path('/proc/'+str(pid)+'/exe').resolve()==Path(sys.executable).resolve(),'readiness Python executable')
    O.require(os.getsid(row['pid'])==row['session']==row['pid'] and os.getsid(row['parent_pid'])==row['parent_session'] and row['session']!=row['parent_session'],'distinct live sessions required')
    # Anchor the pair BEFORE arming cancellation, not merely after cleanup.
    supervisor=table[row['parent_pid']]['ppid'];stage_pid=scope['stage_pid']
    O.require(stage_pid==os.getpid() and table.get(stage_pid,{}).get('start')==scope['stage_start'],'current stage identity')
    O.require(table.get(supervisor,{}).get('ppid')==stage_pid and table[supervisor]['state']!='Z','readiness supervisor belongs to another invocation')
    def argv(pid):return Path('/proc/'+str(pid)+'/cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
    expected_supervisor=[sys.executable,'-B',str(Path(guard.__file__).resolve()),str(scope['config'])]
    O.require(argv(supervisor)==expected_supervisor and argv(row['parent_pid'])==scope['command'],'exact readiness supervisor/config/child argv')
    config=O.load(scope['config'])
    O.require(config['command']==scope['command'] and config['cwd']==scope['source'] and config['output']==scope['output'] and config['bounded_root']==scope['work'],'readiness guard configuration binding')
    identities += [(supervisor,table[supervisor]['start']),(stage_pid,scope['stage_start'])]
    again=guard.process_table()
    O.require(all(again.get(pid,{}).get('start')==start and again[pid]['state']!='Z' for pid,start in identities) and again[row['pid']]['ppid']==row['parent_pid'] and again[row['parent_pid']]['ppid']==supervisor and again[supervisor]['ppid']==stage_pid,'readiness identity/relationship changed')
    return dict(row,supervisor_pid=supervisor,supervisor_start=table[supervisor]['start'],stage_pid=stage_pid,stage_start=scope['stage_start'],guard_config=str(scope['config']))

def wait_session_ready(marker,cancel,stop,observed,scope,timeout=15):
    # Readiness is observed after child launch, irrespective of precheck cost.
    deadline=time.monotonic()+timeout
    try:
        while not stop.wait(.005):
            O.require(time.monotonic()<deadline,'session readiness timeout')
            if not marker.exists():continue
            observed.update(observe_session_ready(marker,scope))
            # Only now begin the cancellation delay, after both live identities
            # and the cross-session relationship have been independently proved.
            if not stop.wait(.3):cancel.set()
            return
    except BaseException as error:
        observed['error']=repr(error);cancel.set()

def child_session_control(stage):
    marker=stage.out/'cross-session-ready.json';O.absent(marker)
    cancel=threading.Event();stop=threading.Event();observed={}
    command=[sys.executable,'-B','-c',SESSION_PARENT_CODE,SESSION_CHILD_CODE,str(marker)]
    thread=None
    def start_watch(folder):
        nonlocal thread
        stage_pid=os.getpid();scope=dict(stage_pid=stage_pid,stage_start=guard.process_table()[stage_pid]['start'],config=folder/'guard-config.json',command=command,source=str(stage.source),output=str(folder),work=str(stage.work))
        thread=threading.Thread(target=wait_session_ready,args=(marker,cancel,stop,observed,scope));thread.start()
    try:
        _,row=guarded(stage,'child-session-cancellation',command,cancel=cancel,before_child=start_watch)
    finally:
        stop.set()
        if thread is not None:thread.join(timeout=1)
    O.require(thread is not None and not thread.is_alive() and 'error' not in observed and 'pid' in observed,'cross-session readiness not proved')
    O.require(row['reason']=='cancelled' and all(row['tracked_processes'].get(str(pid))==start for pid,start in [(observed['pid'],observed['start']),(observed['parent_pid'],observed['parent_start'])]),'cross-session cancellation not proved')
    stage.output_pin(marker);stage.record['cross_session_readiness']=dict(observed=observed,marker=O.pin(marker),delay_begins_after_verified_readiness=True)

def transport_controls(stage):
    # Deliberate failures are inspected, never treated as successful target runs.
    tests=[('false124','raise SystemExit(124)',(),None),
           ('hardkill','import os,signal;os.kill(os.getpid(),signal.SIGKILL)',[stage.out/'missing.prof'],None),
           ('missing-profile','pass',[stage.out/'absent.prof'],None)]
    for name,code,reports,cancel in tests:
        _,r=guarded(stage,name,[sys.executable,'-B','-c',code],reports,cancel=cancel)
        O.require(not r['complete'],'negative control accepted: '+name)
        if name=='false124':O.require(r['exit_code']==124 and r['reason']!='timeout','false124 misclassified')
    child_session_control(stage)
    stale=stage.out/'stale.prof';stale.write_bytes(b'do not truncate')
    _,r=guarded(stage,'stale-report',[sys.executable,'-B','-c','raise RuntimeError("must not run")'],[stale])
    O.require(not r['complete'] and r['exit_code'] is None and stale.read_bytes()==b'do not truncate','stale report protection')
    link=stage.out/'symlink.prof';link.symlink_to(stale)
    _,r=guarded(stage,'symlink-report',[sys.executable,'-B','-c','raise RuntimeError("must not run")'],[link])
    O.require(not r['complete'] and r['exit_code'] is None and link.is_symlink() and stale.read_bytes()==b'do not truncate','symlink report protection')
    stage.record['transport_controls_complete']=True

def compiler_lock_control(stage,binary):
    folder=stage.out/'compiler-lock';folder.mkdir();queries=folder/'queries';queries.mkdir()
    source=folder/'Fixture.emlf';source.write_text('module Fixture where\n'+''.join('value'+str(i)+' = '+str(i)+'\n' for i in range(256)))
    spec=folder/'crate.spec';builtin=stage.work/'builtin/builtin';prefix=folder/'unit'
    fields=['MLF-CRATE-1','sparse-scc/lock-control','','false',O.pack([O.pack(['Fixture',str(source)])]),O.pack([str(builtin)+'.mlfci']),str(queries),str(builtin)]
    spec.write_text(O.pack(fields));stage.output_pin(source);stage.output_pin(spec)
    event=threading.Event();stop=threading.Event();observed={}
    def monitor():
        while not stop.wait(.001):
            path=queries/'.lock'
            if path.exists() and not path.is_symlink():
                st=O.regular(path).stat();owner=lock_owner(Path('/proc/locks').read_text(),st)
                if owner:
                    try:
                        # This is process/lock transport only, never a completed
                        # semantic or allocation observation. A stopped owner
                        # remains held until the supervisor's TERM/KILL cleanup.
                        table=guard.process_table();start=table[owner]['start']
                        O.require(Path(os.readlink('/proc/'+str(owner)+'/exe')).resolve()==Path(binary).resolve(),'lock owner is not the admitted compiler')
                        fd=os.pidfd_open(owner)
                        try:
                            O.require(guard.process_table().get(owner,{}).get('start')==start,'lock owner PID reused')
                            signal.pidfd_send_signal(fd,signal.SIGSTOP)
                            for _ in range(100):
                                row=guard.process_table().get(owner,{})
                                if row.get('state') in ('T','t'):break
                                time.sleep(.001)
                            O.require(row.get('start')==start and row.get('state') in ('T','t') and lock_owner(Path('/proc/locks').read_text(),st)==owner,'stopped compiler lock ownership not retained')
                            observed.update(pid=owner,start=start,device=st.st_dev,inode=st.st_ino,path=str(path),stopped_before_cancel=True)
                            event.set();return
                        finally:os.close(fd)
                    except (OSError,KeyError,ValueError) as error:
                        observed['error']=repr(error);event.set();return
    thread=threading.Thread(target=monitor);thread.start()
    try:_,row=guarded(stage,'actual-compiler-lock-cancel',[binary,'--compile-crate',spec,'-o',prefix],stage.reports('emlf'),maximum=10,cancel=event)
    finally:stop.set();thread.join(timeout=1)
    O.require('pid' in observed and observed.get('stopped_before_cancel') is True and str(observed['pid']) in row['tracked_processes'],'actual compiler-owned POSIX lock not observed')
    O.require(not row['complete'] and row['reason']=='cancelled','compiler lock cancellation not observed')
    O.require(guard.reacquire_locks([dict(path=observed['path'],device=observed['device'],inode=observed['inode'],kind='posix')]),'compiler query lock not reacquired')
    stage.record['compiler_lock_control']=dict(observed=observed,cancelled=True,reacquired=True,guard=row)

def run(stage):
    binaries=stage.built()
    before=stage.runtime('runtime-before',True);stage.record['runtime_before']=before
    transport_controls(stage)
    for name,args,expected in [('DeferredDemand',['100000'],b'PASS deferred-demand\n'),('InventoryDemand',[],b'PASS inventory-demand\n'),('IgnoredRTS',['+RTS','-M1m','-RTS'],b'["+RTS","-M1m","-RTS"]\n')]:
        binary,reports=compile_fixture(stage,name,HERE/'fixtures'/(name+'.hs'))
        summary=run_fixture(stage,name,binary,reports,args,expected)
        if name=='DeferredDemand':stage.record['delayed_producer_self_alloc']=positive_producer(summary)
    binary,reports=compile_fixture(stage,'UnitAllocation',HERE/'fixtures/UnitAllocation.hs')
    first=run_fixture(stage,'unit-1',binary,reports,['1048576'],b'1048576\n')
    second=run_fixture(stage,'unit-2',binary,reports,['1114112'],b'1114112\n')
    delta=unit_delta(first,second)
    definition=stage.a['controls']['rts_definition'];stage.pin_inputs(definition)
    O.require(definition['ghc_version']=='9.14.1' and definition['installed_ghc_sha256']==stage.auth['toolchain']['actual_ghc']['sha256'],'RTS definition version/installed compiler binding')
    build=O.load(O.verify_pin(stage.a['prior']['BUILD']['receipt']))
    rts_archives=[a for unit in build['profiling_packages']['units'] if unit['unit_id']=='rts-1.0.3' for a in unit['profiling_archives'] if Path(a['path']).name.startswith('libHSrts')]
    O.require(len(rts_archives)==1 and definition['installed_rts_archive']==rts_archives[0],'RTS definition profiling archive binding')
    writer=definition['source'];text=O.verify_pin(writer).read_text()
    provenance=O.load(O.verify_pin(definition['provenance']))
    expected_commit='902339d332fb4ce2b3c87dcac1ee6495d41ad886'
    O.require(writer['sha256']=='e979f39bd392effb4e1289ac059da1276cac67446d49ac9256d0209bea599b1e' and provenance['source_sha256']==writer['sha256'] and provenance['source_commit']==provenance['installed_ghc_project_git_commit']==expected_commit and provenance['installed_ghc_project_version']=='9.14.1' and provenance['external_source_executed'] is False,'exact official RTS writer and installed commit provenance')
    O.require(expected_commit in (stage.producer/'ghc-info.txt').read_text(),'authenticated producer GHC Project Git commit differs')
    O.require(definition['release_tag']=='ghc-9.14.1-release','reviewed official release source required')
    O.require(re.search(r'ccs\s*->\s*mem_alloc\s*\*\s*sizeof\s*\(\s*W_\s*\)',text) is not None and re.search(r'total_alloc\s*\*\s*sizeof\s*\(\s*W_\s*\)',text) is not None and Path(writer['path']).name=='ProfilerReportJson.c','installed RTS JSON allocation-byte expressions required')
    stage.record['allocation_unit_control']=dict(complete=True,raw_delta=delta,expected_byte_delta=65536,writer=writer,definition=definition,unit='bytes',requires_reviewed_writer_expression=True)
    # Run original complete maintained harnesses with exact independently reviewed output pins.
    maintained=stage.a['controls']['maintained']
    required={'CheckedBindings':'tools/shared/fixtures/CheckedBindings.hs','SourceValueScope':'tools/shared/fixtures/item4/SourceValueScope.hs'}
    O.require(set(maintained)==set(required),'complete maintained fixture inventory required')
    for name,relative in required.items():
        contract=maintained[name];stage.pin_inputs(contract)
        O.require(O.verify_pin(contract['source'])==stage.source/relative and O.verify_pin(contract['stdout'])==HERE/'fixtures'/(name+'.stdout'),'maintained source/expected output substitution')
        binary,reports=compile_fixture(stage,name,stage.source/relative)
        run_fixture(stage,name,binary,reports,[],O.verify_pin(contract['stdout']).read_bytes())
    compiler_lock_control(stage,binaries['emlf'])
    after=stage.runtime('runtime-after',True);O.require(after==before,'controls runtime drift');stage.record['runtime_after']=after
    stage.record['probe_controls_complete']=True;stage.save()
