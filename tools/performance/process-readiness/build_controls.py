#!/usr/bin/env python3
"""Build finite C probes and a Main-only GHC eligibility fixture; not a benchmark."""
import ast,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
import support as common
args=common.arguments();common.check_pair(args)
S=common.HERE/'fixtures';root=args.baseline_root;candidate=common.ROOT
producer=args.baseline_producer;out=args.output/'build';sha=common.sha
pr,root=common.authenticate(producer);contract=common.inventory()['candidate']
assert not out.exists()
out.mkdir();pins={**common.input_pins(),**{str(candidate/p):h for p,h in contract['source_hashes'].items()},str(S/'Probe.c'):sha(S/'Probe.c'),str(Path(__file__)):sha(__file__),str(common.HERE/'CONTROL-INVENTORY.json'):sha(common.HERE/'CONTROL-INVENTORY.json'),str(S/'Eligibility.hs'):sha(S/'Eligibility.hs'),str(S/'EligibilityHooks.c'):sha(S/'EligibilityHooks.c'),str(producer/'receipt.json'):sha(producer/'receipt.json')}
r={'complete':False,'unqualified_screen_build':True,'ordinary_sample':False,'base_producer':str(producer),'base_source':str(root),'inputs':pins,'commands':[]}
def save():(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
def run(label,argv):
 argv=common.prepare_command(argv,out,label);item={'label':label,'argv':list(map(str,argv))};r['commands'].append(item);save()
 with (out/(label+'.stdout')).open('wb') as so,(out/(label+'.stderr')).open('wb') as se:p=subprocess.run(item['argv'],cwd=root,env=common.env(),stdout=so,stderr=se,timeout=600)
 item['exit_code']=p.returncode;save();assert p.returncode==0,label
 common.record_c_resolution(item);save()
save()
try:
 cc=pr['cc']['path'];ghc=pr['ghc']['path'];include='-I'+str(root/'runtime')
 run('host-base',[cc,'-O2','-std=c11',include,'-c',root/'host/ghc/cbits/host.c','-o',out/'host-base.o'])
 run('host-candidate',[cc,'-O2','-std=c11','-I'+str(candidate/'runtime'),'-c',candidate/'host/ghc/cbits/host.c','-o',out/'host-candidate.o'])
 assert sha(out/'host-base.o')==sha(producer/'host.o'),'rebuilt original C object differs from baseline producer'
 assert sha(out/'host-candidate.o')==sha(args.producer/'host.o'),'rebuilt candidate C object differs from candidate producer'
 run('host-hooks',[cc,'-O2','-std=c11','-I'+str(candidate/'runtime'),'-Dsyscall=mlf_wait_test_syscall','-Dpoll=mlf_wait_test_poll','-Dclose=mlf_wait_test_close','-c',candidate/'host/ghc/cbits/host.c','-o',out/'host-hooks.o'])
 run('eligibility-hooks',[cc,'-O2','-std=c11','-c',S/'EligibilityHooks.c','-o',out/'eligibility-hooks.o'])
 for side in ['base','candidate']:run('probe-'+side,[cc,'-O2','-std=c11',S/'Probe.c',out/('host-'+side+'.o'),producer/'supervisor.o','-pthread','-o',out/('probe-'+side)])
 shutil.copytree(producer/'objects',out/'objects')
 for suffix in ['o','hi']:(out/'objects'/('Main.'+suffix)).unlink()
 copied={str(p.relative_to(out/'objects')):sha(p) for p in (out/'objects').rglob('*') if p.is_file()}
 argv=next(c['argv'] for c in pr['commands'] if any('host/ghc/app/emlf/Main.hs' in str(x) for x in c['argv']))
 argv=[str(x).replace(str(producer/'objects'),str(out/'objects')).replace(str(producer/'host.o'),str(out/'host-candidate.o')).replace(str(producer/'bin/emlf'),str(out/'emlf')) for x in argv]
 run('candidate-emlf',argv)
 assert all(sha(out/'objects'/p)==h for p,h in copied.items()),'copied Haskell dependency changed'
 assert {str(p.relative_to(out/'objects')) for p in (out/'objects').rglob('*') if p.is_file()}-set(copied)=={'Main.o','Main.hi'}
 lines=[l for l in (out/'candidate-emlf.stdout').read_text().splitlines() if 'Compiling ' in l];assert len(lines)==1 and 'Compiling Main ' in lines[0] and str(root/'host/ghc/app/emlf/Main.hs') in lines[0],lines
 assert common.authenticate(producer)==(pr,root);common.check_pins(pins)
 # The GHC eligibility probe retains the same registered host modules/flags, but links counting-only C wrappers.
 for suffix in ['o','hi']:(out/'objects'/('Main.'+suffix)).unlink()
 eligibility=[str(x).replace(str(root/'host/ghc/app/emlf/Main.hs'),str(S/'Eligibility.hs')).replace(str(out/'host-candidate.o'),str(out/'host-hooks.o')).replace(str(out/'emlf'),str(out/'eligibility')) for x in argv]
 eligibility.insert(eligibility.index('-o'),str(out/'eligibility-hooks.o'));run('ghc-eligibility-build',eligibility)
 lines=[l for l in (out/'ghc-eligibility-build.stdout').read_text().splitlines() if 'Compiling ' in l]
 assert len(lines)==1 and 'Compiling Main ' in lines[0] and str(S/'Eligibility.hs') in lines[0],lines
 run('ghc-eligibility-run',[out/'eligibility'])
 import ast
 before_fds,after_fds,counts=ast.literal_eval((out/'ghc-eligibility-run.stdout').read_text());assert before_fds==after_fds and before_fds>=0 and counts[0:3]==[33,33,33] and counts[4:]==[33,1] and counts[3]>0,(before_fds,after_fds,counts)
 assert all(sha(out/'objects'/p)==h for p,h in copied.items())
 assert {str(p.relative_to(out/'objects')) for p in (out/'objects').rglob('*') if p.is_file()}-set(copied)=={'Main.o','Main.hi'}
 common.check_pair(args);common.check_pins(pins)
 r.update(complete=True,actual_GHC_eligible_fastpath_verified=True,eligibility_fd_counts=[before_fds,after_fds],eligibility_counters=counts,all_Haskell_dependency_objects_unchanged=True,only_Main_recompiled=True,copied_Haskell_objects=copied,outputs={str(out/n):sha(out/n) for n in ['host-base.o','host-candidate.o','probe-base','probe-candidate','emlf','eligibility']})
except BaseException as e:r['error']=repr(e);raise
finally:save()
print(json.dumps({'complete':True,'actual_GHC_fastpath':True,'all_Haskell_dependency_objects_unchanged':True,'only_Main_recompiled':True}))
