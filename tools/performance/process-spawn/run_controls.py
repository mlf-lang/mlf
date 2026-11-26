#!/usr/bin/env python3
"""Darwin spawn controls, plus the complete retained readiness inventory."""
from pathlib import Path
import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def require(value,message):
    if not value:raise RuntimeError(message)


def cwd_capability(stdout):
    """Read the compiled SDK/runtime probe, never infer features from a source hash."""
    require(stdout in (b'spawn-cwd\n', b'fork-cwd-fallback\n'),
            'complete CWD capability response required')
    return stdout == b'spawn-cwd\n'


def validate_eligibility(stdout,cwd_supported):
    """Require the independently counted spawn/fallback and descriptor outcomes."""
    value=ast.literal_eval(stdout.decode('utf-8'))
    require(type(value) is tuple and len(value)==3,'eligibility result tuple required')
    before,after,counters=value
    expected=([30,29,1,30,30,21,9,1] if cwd_supported else
              [29,28,2,30,30,20,9,0])
    require(type(before) is int and type(after) is int and before==after and before>0
            and type(counters) is list and all(type(n) is int for n in counters)
            and counters==expected,
            'actual GHC spawn, fallback, process groups, inherited environment and descriptor ownership')
    return {'fds_before':before,'fds_after':after,'counters':counters}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['baseline-root','baseline-producer','output']:
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--producer',type=Path)
    p.add_argument('--full',action='store_true')
    p.add_argument('--gc-prefix',type=Path)
    p.add_argument('--gmp-prefix',type=Path)
    a=p.parse_args();require(sys.platform=='darwin','Darwin controls require Darwin')
    if a.producer:a.producer=a.producer.resolve()
    base=a.baseline_root.resolve();old=a.baseline_producer.resolve();out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__,out/'controller-used.py')
    hp=ROOT/'tools/performance/a1-private-index/helper.py'
    H=types.ModuleType('retained_helper');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    before=H.authenticate(old,base)
    candidate=H.authenticate(a.producer.resolve(),ROOT) if a.producer else None
    record={'complete':False,'ordinary_candidate_authenticated':candidate is not None,'performance_measured':False,
            'commands':[],'faults':[],'real':[]}
    limits={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,
            'host_available_floor_bytes':3*1024**3,'max_work_bytes':2*1024**3,
            'process_tree_rss_bytes':5*1024**3,'wall_seconds':120}
    def save():H.save(out/'receipt.json',record)
    def run(name,argv,env=None):
        # Real probes and compiler commands use the unchanged process guard.
        if env is None:
            command=H.Runner(out,limits).run(argv,ROOT,out/name)
        else:
            # Fault probes do not create processes; their mocked PIDs must not
            # be passed to any real syscall. Keep them separately bounded.
            d=out/name;d.mkdir()
            with (d/'stdout').open('wb') as so,(d/'stderr').open('wb') as se:
                result=subprocess.run(list(map(str,argv)),cwd=ROOT,env=env,stdout=so,stderr=se,timeout=10)
            command={'argv':list(map(str,argv)),'exit_code':result.returncode}
            require(result.returncode==0,'mock probe '+name)
        record['commands'].append({'name':name,'command':command});save()
        return (out/name/'stdout').read_bytes()
    def spec(executable,args=(),timeout='3',stdin='',stdout='',stderr=''):
        return ('\0'.join([timeout,stdin,stdout,stderr,executable,*args])+'\0').encode()
    def expected(code=7,message=''):
        value=message.encode();return f'{int(bool(message))} {0 if message else code} {len(value)} {value.hex()}\n'.encode()
    cc=before['cc']['path'];fixtures=ROOT/'tools/performance/process-readiness/fixtures'
    pins={str(x):H.sha(x) for x in [Path(__file__),HERE/'SpawnFaults.c',HERE/'SpawnUnavailable.c',hp,
        ROOT/'runtime/mlf_system.h',base/'runtime/mlf_system.h',fixtures/'Probe.c',
        ROOT/'tools/performance/process-readiness/darwin/Faults.c',
        HERE/'SpawnHooks.c',HERE/'Eligibility.hs',HERE/'ChildState.c',HERE/'CwdCapability.c']}
    record['inputs']=pins;save()
    with H.SerialLock(ROOT/'.mlf-build'):
        run('build-cwd-capability',[cc,'-O2','-std=c11',HERE/'CwdCapability.c','-o',out/'cwd-capability'])
        cwd_supported=cwd_capability(run('cwd-capability',[out/'cwd-capability']))
        record['cwd_spawn_supported']=cwd_supported;save()
        for side,source,producer in [('base',base,old),('candidate',ROOT,a.producer)]:
            run('host-'+side,[cc,'-O2','-std=c11','-I'+str(source/'runtime'),'-c',source/'host/ghc/cbits/host.c','-o',out/(side+'.o')])
            if producer:require(H.sha(out/(side+'.o'))==H.sha(producer/'host.o'),'ordinary host object identity '+side)
            run('build-probe-'+side,[cc,'-O2','-std=c11',fixtures/'Probe.c',out/(side+'.o'),old/'supervisor.o','-o',out/('probe-'+side)])
        names=['fork','getpgrp','clock_gettime','waitpid','kqueue','kevent','fcntl','close','nanosleep','kill',
            'posix_spawnattr_init','posix_spawnattr_setpgroup','posix_spawnattr_setflags','posix_spawnattr_destroy','posix_spawnp',
            'posix_spawn_file_actions_init','posix_spawn_file_actions_addchdir','posix_spawn_file_actions_destroy']
        flags=['-D'+n+'=mlf_mock_'+n for n in names]+['-Dsigaction(...)=mlf_mock_sigaction(__VA_ARGS__)']
        run('mock-host',[cc,'-O2','-std=c11','-I'+str(ROOT/'runtime'),*flags,'-c',ROOT/'host/ghc/cbits/host.c','-o',out/'mock.o'])
        run('build-mock-probe',[cc,'-O2','-std=c11',fixtures/'Probe.c',HERE/'SpawnFaults.c',out/'mock.o',old/'supervisor.o','-o',out/'mock-probe'])
        spawn='init,group,flags,spawn,destroy,'
        ready='clock,sigaction,open,cloexec,register,'
        cases=[]
        for name,prefix in [('ok',spawn),('init-fail','init,fork,'),('group-fail','init,group,destroy,fork,'),
            ('flags-fail','init,group,flags,destroy,fork,'),('spawn-fail',spawn+'fork,'),
            ('spawn-resource-fail',spawn+'fork,'),('destroy-fail',spawn)]:
            cases.append((name,name,'immediate',None,b'',spec('/usr/bin/true'),expected(),prefix+ready+'wait,close'))
        for name,scope,prefix in [('supervised','4242','init,spawn,destroy,'),('stale-scope','4241',spawn),('invalid-scope','bad',spawn)]:
            cases.append((name,'ok','immediate',scope,b'',spec('/usr/bin/true'),expected(),prefix+ready+'wait,close'))
        if cwd_supported:
            start='init,group,flags,'
            for mode,tail in [
                    ('ok','actions-init,chdir,spawn,actions-destroy,destroy,'),
                    ('actions-init-fail','actions-init,destroy,fork,'),
                    ('chdir-fail','actions-init,chdir,actions-destroy,destroy,fork,'),
                    ('spawn-fail','actions-init,chdir,spawn,actions-destroy,destroy,fork,')]:
                cases.append(('cwd-'+mode,mode,'immediate',None,b'.',spec('/usr/bin/true'),
                              expected(),start+tail+ready+'wait,close'))
        else:
            cases.append(('cwd-fallback','ok','immediate',None,b'.',spec('/usr/bin/true'),
                          expected(),'init,group,flags,destroy,fork,'+ready+'wait,close'))
        for name,first,wire in [('relative-cwd',b'.',spec('./true')),('stdin',b'',spec('/usr/bin/true',stdin='/unused')),
            ('stdout',b'',spec('/usr/bin/true',stdout='/unused')),('stderr',b'',spec('/usr/bin/true',stderr='/unused'))]:
            cases.append(('ineligible-'+name,'ok','immediate',None,first,wire,expected(),'fork,'+ready+'wait,close'))
        for fault,tail,wanted in [('deadline-ready','wait,close',expected()),
            ('timeout','wait,clock,close,kill-group,kill-child,reap',expected(124)),
            ('wait-eintr','wait,clock,event,wait,close',expected()),
            ('event-error','wait,clock,event,close,sleep,wait',expected())]:
            cases.append((fault,'ok',fault,None,b'',spec('/usr/bin/true',timeout='1'),wanted,spawn+ready+tail))
        cases.append(('initial-clock-error','ok','start-clock-fail',None,b'',spec('/usr/bin/true'),
            expected(message='IO error: runProcess failed'),spawn+'clock,kill-group,kill-child,reap'))
        cases.append(('failed-spawn-then-fork-error','spawn-fail','fork-fail',None,b'',spec('/usr/bin/true'),
            expected(message='IO error: runProcess failed'),spawn+'fork'))
        for name,spawn_mode,wait_mode,scope,first,wire,wanted,trace in cases:
            (out/'a').write_bytes(first);(out/'b').write_bytes(wire)
            env=H.env();env.pop('MLF_BUILD_SCOPE',None)
            env.update(MLF_SPAWN_FAULT=spawn_mode,MLF_WAIT_FAULT=wait_mode)
            if scope is not None:env['MLF_BUILD_SCOPE']=scope
            got=run('fault-'+name,[out/'mock-probe','7',out/'a',out/'b'],env)
            require(got==wanted and (out/('fault-'+name)/'stderr').read_text()=='MOCK '+trace+'\n','handwritten fault expectation '+name)
            record['faults'].append(name);save()
        for side in ['base','candidate']:
            d=out/('real-'+side);d.mkdir()
            plain=d/'plain text λ';plain.write_text('exit 9\n');plain.chmod(0o700)
            denied=d/'no execute';denied.write_text('#!/bin/sh\nexit 0\n');denied.chmod(0o600)
            trials=[('no-shebang',str(plain),[],9),('no-execute',str(denied),[],126),
                ('missing',str(d/'absent'),[],127),('directory',str(d),[],126),('path-search','true',[],0),
                ('signal','/bin/sh',['-c','kill -TERM $$'],143)]
            for name,executable,argv,status in trials:
                (d/'a').write_bytes(b'');(d/'b').write_bytes(spec(executable,argv))
                require(run(name+'-'+side,[out/('probe-'+side),'7',d/'a',d/'b'])==expected(status),name+' parity '+side)
                record['real'].append([side,name]);save()
            for name,child_dir,executable,args,status in [
                    ('cwd-relative-argument',d,'/bin/test',['-f',plain.name],0),
                    ('cwd-relative-executable',d,'./'+plain.name,[],9),
                    ('cwd-text-executable',d,str(plain),[],9),
                    ('cwd-missing-directory',d/'absent','/usr/bin/true',[],126),
                    ('cwd-missing-executable',d,str(d/'absent'),[],127)]:
                (d/'a').write_bytes(os.fsencode(child_dir));(d/'b').write_bytes(spec(executable,args))
                require(run(name+'-'+side,[out/('probe-'+side),'7',d/'a',d/'b'])==expected(status),
                        name+' parity '+side)
                record['real'].append([side,name]);save()
        H.check_pins(pins)
    if a.full:
        require(a.producer and a.gc_prefix and a.gmp_prefix,'full retained controls require ordinary producer and native dependencies')
        path=ROOT/'tools/performance/process-readiness/darwin/run_controls.py'
        legacy=H.module(path,'retained_darwin_controls')
        sys.argv=[str(path),'--baseline-root',str(base),'--baseline-producer',str(old),'--producer',str(a.producer.resolve()),
            '--output',str(out/'retained'),'--gc-prefix',str(a.gc_prefix),'--gmp-prefix',str(a.gmp_prefix)]
        with H.SerialLock(ROOT/'.mlf-build'):
            legacy.main(extra_fault_flags=['-Dposix_spawnp=mlf_spawn_unavailable'],
                extra_fault_sources=[HERE/'SpawnUnavailable.c'],extra_pins=[Path(__file__),HERE/'SpawnUnavailable.c'])
        record['retained']=H.load(out/'retained/receipt.json')
        require(record['retained']['complete'],'entire retained inventory')
        with H.SerialLock(ROOT/'.mlf-build'):
            producer=a.producer.resolve()
            flags=['-Dfork=mlf_spawn_fork','-Dposix_spawnp=mlf_spawn_call',
                '-Dposix_spawnattr_init=mlf_spawn_init','-Dposix_spawnattr_destroy=mlf_spawn_destroy']
            run('spawn-hooks-host',[cc,'-O2','-std=c11','-I'+str(ROOT/'runtime'),*flags,
                '-c',ROOT/'host/ghc/cbits/host.c','-o',out/'spawn-hooks-host.o'])
            run('spawn-hooks',[cc,'-O2','-std=c11','-c',HERE/'SpawnHooks.c','-o',out/'spawn-hooks.o'])
            run('build-child-state',[cc,'-O2','-std=c11',HERE/'ChildState.c','-o',out/'child-state'])
            objects=out/'eligibility-objects';shutil.copytree(producer/'objects',objects)
            for suffix in ['o','hi']:(objects/('Main.'+suffix)).unlink(missing_ok=True)
            object_pins=H.file_pins(objects)
            argv=next(c['argv'] for c in candidate['commands'] if any('app/emlf/Main.hs' in x for x in c['argv']))
            argv=[x.replace(str(producer/'objects'),str(objects)).replace(str(ROOT/'host/ghc/app/emlf/Main.hs'),str(HERE/'Eligibility.hs'))
                .replace(str(producer/'host.o'),str(out/'spawn-hooks-host.o')).replace(str(producer/'bin/emlf'),str(out/'eligibility')) for x in argv]
            argv.insert(argv.index('-o'),str(out/'spawn-hooks.o'))
            run('build-eligibility',argv);H.check_pins(object_pins)
            record['eligibility']=validate_eligibility(
                run('eligibility-result',[out/'eligibility',out/'child-state']),cwd_supported);save()
    H.check_pins(pins)
    require(H.authenticate(old,base)==before,'baseline remains authenticated')
    if candidate:require(H.authenticate(a.producer.resolve(),ROOT)==candidate,'candidate remains authenticated')
    record.update(complete=True,fault_cases=len(cases),extra_real_cases=len(record['real']));save()
    print('PASS spawn fault/fallback and real command parity'+(' plus all retained controls' if a.full else ''),flush=True)


if __name__=='__main__':main()
