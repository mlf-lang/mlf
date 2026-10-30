#!/usr/bin/env python3
"""Darwin readiness correctness and actual GHC eligibility; no timing claim.

The original Linux W1 reproduction, fixtures and expectations are unchanged.
Both sides here must be authenticated ordinary GHC 9.14.1 O2 producers.
"""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main(validate_change=None, extra_fault_flags=(), extra_fault_sources=(), extra_pins=()):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['baseline-root', 'baseline-producer', 'producer', 'output', 'gc-prefix', 'gmp-prefix']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    require(sys.platform == 'darwin', 'Darwin required; no silent platform skips')
    base, old, new, out = [x.resolve() for x in [a.baseline_root, a.baseline_producer, a.producer, a.output]]
    require(not out.exists(), 'fresh output required')
    helper = base / 'tools/performance/a1-private-index/helper.py'
    H = types.ModuleType('darwin_control_helper'); H.__file__ = str(helper)
    exec(compile(helper.read_bytes(), str(helper), 'exec'), H.__dict__)
    before = H.authenticate(old, base), H.authenticate(new, ROOT)
    require(before[0]['ghc'] == before[1]['ghc'] and before[0]['cc'] == before[1]['cc'], 'same toolchains')
    # An exact reverse projection proves the Linux and fallback source text is
    # unchanged. It never transforms a production build or expected output.
    if validate_change is not None:
        validate_change(base, ROOT)
    else:
        header = (ROOT / 'runtime/mlf_system.h').read_text()
        lines, kept, arms, skipping = header.splitlines(keepends=True), [], 0, False
        for line in lines:
            if line == '#elif defined(__APPLE__)\n':
                require(not skipping, 'nested Darwin arm'); arms += 1; skipping = True
            elif skipping and line == '#endif\n':
                skipping = False; kept.append(line)
            elif not skipping:
                kept.append(line)
        require(arms == 3 and not skipping and ''.join(kept) == (base / 'runtime/mlf_system.h').read_text(),
                'only three additive Darwin arms allowed')
    for field in ['resolved_modules', 'resolved_host_modules', 'host_inputs', 'configuration_inputs']:
        require(before[0][field].keys() == before[1][field].keys(), 'same input inventory: ' + field)
        for name, row in before[0][field].items():
            relative = Path(row['path']).relative_to(base)
            if str(relative) != 'runtime/mlf_system.h':
                require(row['sha256'] == before[1][field][name]['sha256'], 'unrelated input changed: ' + str(relative))
    out.mkdir(parents=True)
    pins = {str(f): H.sha(f) for f in [helper, Path(__file__), HERE/'Faults.c', HERE/'Eligibility.hs',
            HERE/'EligibilityHooks.c', HERE/'NativeProbe.c', ROOT/'runtime/mlf_system.h',
            base/'runtime/mlf_system.h', old/'receipt.json', new/'receipt.json']}
    pins.update({str(f): H.sha(f) for f in extra_pins})
    fixtures = HERE.parent / 'fixtures'
    inventory = H.load(HERE.parent/'CONTROL-INVENTORY.json')
    for name in ['Probe.c', 'Tree.c']:
        require(H.sha(fixtures/name) == inventory['fixture_hashes']['fixtures/'+name], 'frozen fixture changed')
        pins[str(fixtures/name)] = H.sha(fixtures/name)
    record = {'complete': False, 'performance_measured': False, 'inputs': pins, 'commands': [],
              'linux_and_fallback_source_unchanged': True, 'faults': [], 'transport': []}
    def save(): H.save(out/'receipt.json', record)
    def run(label, argv, env=None):
        item = {'label': label, 'argv': list(map(str, argv))}; record['commands'].append(item); save()
        with (out/(label+'.stdout')).open('wb') as so, (out/(label+'.stderr')).open('wb') as se:
            r = subprocess.run(item['argv'], cwd=out, env=env or H.env(), stdout=so, stderr=se, timeout=120)
        item['exit_code'] = r.returncode; save(); require(r.returncode == 0, 'failed command: ' + label)
        return (out/(label+'.stdout')).read_bytes()
    cc = before[0]['cc']['path']
    save()
    try:
        for side, source, producer in [('base', base, old), ('candidate', ROOT, new)]:
            obj = out/('host-'+side+'.o')
            run('host-'+side, [cc,'-O2','-std=c11','-I'+str(source/'runtime'),'-c',source/'host/ghc/cbits/host.c','-o',obj])
            require(H.sha(obj) == H.sha(producer/'host.o'), 'ordinary host object identity: '+side)
            run('probe-'+side, [cc,'-O2','-std=c11',fixtures/'Probe.c',obj,producer/'supervisor.o','-o',out/('probe-'+side)])
        # Reuse the exact original transport expectations, with Darwin's true
        # executable path. These are handwritten outcomes, not candidate data.
        def spec(executable, args=(), timeout='3', stdin='', stdout='', stderr=''):
            return ('\0'.join([timeout,stdin,stdout,stderr,executable,*args])+'\0').encode()
        def expected(status, number=0, message=''):
            b=message.encode(); return f'{status} {number} {len(b)} {b.hex()}\n'.encode()
        names=inventory['transport_cases']
        for name in names:
            for side in ['base','candidate']:
                d=out/(name+'-'+side);d.mkdir();op=7;first=b'';wire=spec('/usr/bin/true');code=0;error='';files={}
                if name=='exit7':wire=spec('/bin/sh',['-c','exit 7']);code=7
                elif name=='exit124':wire=spec('/bin/sh',['-c','exit 124']);code=124
                elif name=='signal-term':wire=spec('/bin/sh',['-c','kill -TERM $$']);code=143
                elif name=='exec-missing':wire=spec(str(d/'missing'));code=127
                elif name=='bad-cwd':first=str(d/'missing').encode();code=126
                elif name=='missing-stdin':wire=spec('/usr/bin/true',stdin=str(d/'missing'));code=126
                elif name=='timeout':wire=spec('/bin/sleep',['2'],timeout='1');code=124
                elif name=='unterminated-spec':wire=b'3\0\0\0\0/usr/bin/true';error='IO error: invalid process specification'
                elif name=='missing-fields':wire=b'3\0\0';error='IO error: invalid process specification'
                elif name in ['zero-timeout','large-timeout','bad-timeout']:
                    wire=spec('/usr/bin/true',timeout={'zero-timeout':'0','large-timeout':'2147483648','bad-timeout':'x'}[name]);error='IO error: invalid process specification'
                elif name=='NUL-cwd':first=b'a\0b';error='file path contains NUL'
                elif name=='mkdir':wire=spec('/bin/mkdir',['-p',str(d/'nested dir/Unicode-λ')])
                elif name=='mv':
                    src=d/'move λ.new';dst=d/'move λ';src.write_bytes(b'new\0bytes');dst.write_bytes(b'old');wire=spec('/bin/mv',['-f',str(src),str(dst)]);files[dst]=b'new\0bytes'
                elif name=='shared-redirection':
                    dst=d/'shared λ.out';wire=spec('/bin/sh',['-c','printf OUT; printf ERR >&2'],stdout=str(dst),stderr=str(dst));files[dst]=b'OUTERR'
                elif name.startswith('write-'):
                    op=14;first=str(d/'written λ').encode();wire='a\0λ𐀀\n'.encode()
                    if name=='write-bad-parent':first=str(d/'missing/file').encode();error='IO error: file write failed'
                    elif name=='write-NUL-path':first=b'invalid\0name';error='file path contains NUL'
                    else:files[Path(first.decode())]=wire
                (d/'a').write_bytes(first);(d/'b').write_bytes(wire)
                got=run(name+'-'+side,[out/('probe-'+side),str(op),d/'a',d/'b'])
                require(got == (expected(1,0,error) if error else expected(0,code)), name+' observable: '+side)
                require(all(f.read_bytes()==b for f,b in files.items()),name+' file bytes')
                if name=='mkdir':require((d/'nested dir/Unicode-λ').is_dir(), 'mkdir')
                if name=='mv':require(not (d/'move λ.new').exists(), 'mv source removed')
                record['transport'].append({'case':name,'side':side});save()
        macros=['fork','clock_gettime','waitpid','kqueue','kevent','fcntl','close','nanosleep','kill']
        flags=['-D'+n+'=mlf_mock_'+n for n in macros]+['-Dsigaction(...)=mlf_mock_sigaction(__VA_ARGS__)']+list(extra_fault_flags)
        run('mock-host',[cc,'-O2','-std=c11','-I'+str(ROOT/'runtime'),*flags,'-c',ROOT/'host/ghc/cbits/host.c','-o',out/'mock-host.o'])
        run('mock-probe',[cc,'-O2','-std=c11',fixtures/'Probe.c',HERE/'Faults.c',*extra_fault_sources,out/'mock-host.o',new/'supervisor.o','-o',out/'mock-probe'])
        (out/'a').write_bytes(b'');(out/'b').write_bytes(spec('/usr/bin/true',timeout='1'))
        prefix='fork,clock,sigaction,open,cloexec,register,'
        cases={name:(expected(0,7),prefix+'wait,close') for name in ['immediate','deadline-ready']}
        for name in ['ready','event-timeout','event-eintr','wait-eintr','close-eintr']:
            cases[name]=(expected(0,7),prefix+'wait,clock,event,wait,close')
        for name in ['event-error','event-ev-error','event-wrong-pid','event-wrong-filter','event-no-exit','event-count']:
            cases[name]=(expected(0,7),prefix+'wait,clock,event,close,sleep,wait')
        for name in ['register-esrch','register-eintr','register-eperm']:
            cases[name]=(expected(0,7),prefix+'close,wait,clock,sleep,wait')
        cases['cloexec-fail']=(expected(0,7),'fork,clock,sigaction,open,cloexec,close,wait,clock,sleep,wait')
        for name in ['open-emfile','open-enomem']:
            cases[name]=(expected(0,7),'fork,clock,sigaction,open,wait,clock,sleep,wait')
        for name in ['sig-ignore','sig-custom','sig-no-wait','sig-query-fail']:
            cases[name]=(expected(0,7),'fork,clock,sigaction,wait,clock,sleep,wait')
        cases['timeout']=(expected(0,124),prefix+'wait,clock,close,kill-group,kill-child,reap')
        cases['wait-error']=(expected(1,0,'IO error: runProcess failed'),prefix+'wait,close')
        cases['start-clock-fail']=(expected(1,0,'IO error: runProcess failed'),'fork,clock,kill-group,kill-child,reap')
        cases['fork-fail']=(expected(1,0,'IO error: runProcess failed'),'fork')
        for name,(wanted,trace) in cases.items():
            env=H.env();env.pop('MLF_BUILD_SCOPE',None);env['MLF_WAIT_FAULT']=name
            got=run('fault-'+name,[out/'mock-probe','7',out/'a',out/'b'],env)
            require(got==wanted and (out/('fault-'+name+'.stderr')).read_text()=='MOCK '+trace+'\n','fault trace: '+name)
            record['faults'].append(name);save()
        hook_flags=['-D'+name+'=mlf_ready_'+name for name in ['kqueue','kevent','fcntl','close']]
        run('host-hooks',[cc,'-O2','-std=c11','-I'+str(ROOT/'runtime'),*hook_flags,'-c',ROOT/'host/ghc/cbits/host.c','-o',out/'host-hooks.o'])
        run('eligibility-hooks',[cc,'-O2','-std=c11','-c',HERE/'EligibilityHooks.c','-o',out/'hooks.o'])
        shutil.copytree(new/'objects',out/'objects')
        for suffix in ['o','hi']:(out/'objects'/('Main.'+suffix)).unlink(missing_ok=True)
        objects=H.file_pins(out/'objects')
        argv=next(c['argv'] for c in before[1]['commands'] if any('app/emlf/Main.hs' in x for x in c['argv']))
        argv=[x.replace(str(new/'objects'),str(out/'objects')).replace(str(ROOT/'host/ghc/app/emlf/Main.hs'),str(HERE/'Eligibility.hs')).replace(str(new/'host.o'),str(out/'host-hooks.o')).replace(str(new/'bin/emlf'),str(out/'eligibility')) for x in argv]
        argv.insert(argv.index('-o'),str(out/'hooks.o'));run('eligibility-build',argv)
        H.check_pins(objects)
        count_before,count_after,counters=ast.literal_eval(run('eligibility',[out/'eligibility']).decode())
        require(count_before==count_after and count_before>0 and counters[0:2]==[33,33] and counters[2]>0 and counters[3:]==[33,33], 'actual GHC readiness / descriptor ownership')
        record['eligibility']={'fds_before':count_before,'fds_after':count_after,'counters':counters}
        for side,source,producer in [('base',base,old),('candidate',ROOT,new)]:
            run('tree-build-'+side,[cc,'-O2','-std=c11','-I'+str(ROOT/'runtime'),fixtures/'Tree.c',out/('host-'+side+'.o'),producer/'supervisor.o','-o',out/('tree-'+side)])
            for mode in ['supervised','unsupervised']:
                label='tree-'+side+'-'+mode
                require(run(label,[out/('tree-'+side),'parent',mode,out/(label+'-leader'),out/(label+'-child')])==('PASS '+mode+' timeout descendant cleanup\n').encode(),'descendant cleanup')
            run('native-build-'+side,[cc,'-O2','-std=c11','-I'+str(source/'runtime'),'-I'+str(a.gc_prefix/'include'),'-I'+str(a.gmp_prefix/'include'),HERE/'NativeProbe.c','-L'+str(a.gc_prefix/'lib'),'-L'+str(a.gmp_prefix/'lib'),'-lgc','-lgmp','-o',out/('native-'+side)])
            for index,(command,code) in enumerate([('exit 0',0),('exit 7',7),('exit 124',124),('kill -TERM $$',143),('sleep 2',124)]):
                require(run('native-'+side+'-'+str(index),[out/('native-'+side),command,str(code)])==f'PASS native process status {code}\n'.encode(),'native status')
        require(before==(H.authenticate(old,base),H.authenticate(new,ROOT)),'producer changed')
        H.check_pins(pins);record.update(complete=True,transport_executions=40,fault_cases=len(cases),descendant_cases=4,native_cases=10)
    except BaseException as error:
        record['error']=repr(error);raise
    finally:
        save()
    print('PASS Darwin transport, fault/order, GHC eligibility, descriptor, descendant and native controls')


if __name__=='__main__':
    main()
