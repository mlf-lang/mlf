#!/usr/bin/env python3
"""Original twenty fault/order cases, four real cleanup cases, and ABI fallback."""
import json,os,subprocess,sys
from pathlib import Path
import support as common
args=common.arguments();common.check_pair(args)
S=common.HERE/'fixtures';sha=common.sha;root=common.ROOT;build=args.output/'build';out=args.output/'faults'
assert not out.exists();out.mkdir()
b=json.loads((build/'receipt.json').read_text());assert b['complete'];common.check_pins(b['inputs']);common.check_pins(b['outputs']);p,source=common.authenticate(Path(b['base_producer']));cc=p['cc']['path']
pins={**common.input_pins(),**b['inputs'],str(S/'Faults.c'):sha(S/'Faults.c'),str(S/'Tree.c'):sha(S/'Tree.c'),str(__file__):sha(__file__),str(build/'receipt.json'):sha(build/'receipt.json')}
r={'complete':False,'performance_measured':False,'inputs':pins,'commands':[],'faults':[]}
def save():(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
def run(name,argv,env=None,expected=0):
 argv=common.prepare_command(argv,out,name);item={'name':name,'argv':list(map(str,argv))};r['commands'].append(item);save()
 with (out/(name+'.stdout')).open('wb')as so,(out/(name+'.stderr')).open('wb')as se:q=subprocess.run(item['argv'],env=env or common.env(),cwd=out,stdout=so,stderr=se,timeout=30)
 item.update(exit_code=q.returncode,stdout_sha256=sha(out/(name+'.stdout')),stderr_sha256=sha(out/(name+'.stderr')));save();assert q.returncode==expected,(name,q.returncode)
 common.record_c_resolution(item);save()
save()
try:
 macros=['fork','clock_gettime','syscall','waitpid','poll','close','nanosleep','kill']
 flags=['-D'+n+'=mlf_mock_'+n for n in macros]+['-Dsigaction(...)=mlf_mock_sigaction(__VA_ARGS__)']
 run('mock-host',[cc,'-O2','-std=c11','-I'+str(root/'runtime'),*flags,'-c',root/'host/ghc/cbits/host.c','-o',out/'mock-host.o'])
 run('mock-link',[cc,'-O2','-std=c11',S/'Probe.c',S/'Faults.c',out/'mock-host.o',Path(b['base_producer'])/'supervisor.o','-pthread','-o',out/'mock-probe'])
 (out/'a.bin').write_bytes(b'');(out/'b.bin').write_bytes(b'1\0\0\0\0/bin/true\0')
 prefix='fork,clock,sigaction,open,'
 cases={
 'immediate':('0 7 0 \n',prefix+'wait,close'),
 'deadline-ready':('0 7 0 \n',prefix+'wait,close'),
 'ready':('0 7 0 \n',prefix+'wait,clock,poll,wait,close'),
 'poll-hup':('0 7 0 \n',prefix+'wait,clock,poll,wait,close'),
 'poll-eintr':('0 7 0 \n',prefix+'wait,clock,poll,wait,close'),
 'close-eintr':('0 7 0 \n',prefix+'wait,clock,poll,wait,close'),
 'timeout':('0 124 0 \n',prefix+'wait,clock,close,kill-group,kill-child,reap')}
 for name in ['poll-error','poll-nval','poll-err-event']:cases[name]=('0 7 0 \n',prefix+'wait,clock,poll,close,sleep,wait')
 for name in ['open-enosys','open-emfile','open-eperm']:cases[name]=('0 7 0 \n',prefix+'wait,clock,sleep,wait')
 for name in ['sig-ignore','sig-custom','sig-no-wait','sig-query-fail']:cases[name]=('0 7 0 \n','fork,clock,sigaction,wait,clock,sleep,wait')
 failure='IO error: runProcess failed';wanted=f'1 0 {len(failure)} {failure.encode().hex()}\n'
 cases['wait-error']=(wanted,prefix+'wait,close');cases['start-clock-fail']=(wanted,'fork,clock,kill-group,kill-child,reap');cases['fork-fail']=(wanted,'fork')
 assert list(cases)==common.inventory()['fault_cases']
 for name,(stdout,trace) in cases.items():
  env=common.env();env.pop('MLF_BUILD_SCOPE',None);env['MLF_WAIT_FAULT']=name
  run(name,[out/'mock-probe','7',out/'a.bin',out/'b.bin'],env);assert (out/(name+'.stdout')).read_text()==stdout,name;assert (out/(name+'.stderr')).read_text()=='MOCK '+trace+'\n',name;r['faults'].append({'case':name,'expected_stdout':stdout,'expected_trace':trace});save()
 # A header without SYS_pidfd_open must compile and use the old path.
 (out/'no-pidfd.h').write_text('#include <sys/syscall.h>\n#undef SYS_pidfd_open\n')
 run('missing-SYS-host',[cc,'-O2','-std=c11','-D_DEFAULT_SOURCE=1','-include',out/'no-pidfd.h','-I'+str(root/'runtime'),'-c',root/'host/ghc/cbits/host.c','-o',out/'no-pidfd.o'])
 run('missing-SYS-link',[cc,'-O2','-std=c11',S/'Probe.c',out/'no-pidfd.o',Path(b['base_producer'])/'supervisor.o','-pthread','-o',out/'no-pidfd-probe'])
 run('missing-SYS-execute',[out/'no-pidfd-probe','7',out/'a.bin',out/'b.bin']);assert (out/'missing-SYS-execute.stdout').read_bytes()==b'0 0 0 \n'
 for side in ['base','candidate']:
  run('tree-link-'+side,[cc,'-O2','-std=c11','-I'+str(root/'runtime'),S/'Tree.c',build/('host-'+side+'.o'),Path(b['base_producer'])/'supervisor.o','-pthread','-o',out/('tree-'+side)])
  for mode in ['supervised','unsupervised']:
   name='tree-'+side+'-'+mode;run(name,[out/('tree-'+side),'parent',mode,out/(name+'-leader.pid'),out/(name+'-grandchild.pid')]);assert (out/(name+'.stdout')).read_text()=='PASS '+mode+' timeout descendant cleanup\n';assert not (out/(name+'.stderr')).read_bytes()
 run('candidate-dynamic-symbols',['readelf','--dyn-syms','--wide',build/'emlf']);symbols=(out/'candidate-dynamic-symbols.stdout').read_text();assert 'pidfd_open' not in symbols and 'syscall@GLIBC_2.2.5' in symbols
 common.check_pair(args);common.check_pins(pins);common.check_pins(b['outputs']);common.authenticate(Path(b['base_producer']));r.update(complete=True,fault_cases=len(cases),exact_mock_call_traces_passed=True,real_descendant_cleanup_cases=4,missing_header_constant_fallback_passed=True,no_new_glibc_pidfd_symbol=True)
except BaseException as e:r['error']=repr(e);raise
finally:save()
print('PASS 20 precise fault/order/ownership controls + missing SYS fallback + 4 real descendant cleanup cases + old syscall ABI')
