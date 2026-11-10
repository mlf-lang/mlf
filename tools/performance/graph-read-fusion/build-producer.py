#!/usr/bin/env python3
"""Prepare one fresh ordinary producer and independent CLI/semantic qualification.

Requires separate coordinator admission. This never runs a native-generation,
fixed-point, full90, or performance comparison campaign.
"""
from pathlib import Path
import argparse
import hashlib
import os
import re
import subprocess
import sys
import time
import types

ROOT=Path(__file__).resolve().parents[3]
OWNER='libraries/mlf-inference/Bootstrap/Graph.hs'
CANDIDATE='fdb9e899392ac0068f9f11432d512d1168934455a6da733a10e7cabb52d19df3'
CANONICAL='bootstrap/MLF/BuiltinPreludeData.hs'
DERIVED='c0d4205ebfe8fde9fddf7ab63442558ada389056916fa2fe41dfc94b90297be8'
WATCHDOG='5368803eb84dabc9dcefa89225b6ff56afd637e105f227bade15e40f9a5e923f'
BASE_RECEIPT='b71bbb5ebb757a206ed41932cdafca982f1e7246218496953be273afad5a8caf'
HELPER='0d11b29419a32fc9832096951aa085cc317c8a304b9db110ee96ba411a4ce7cc'
SCOPE='d8ffe4256f333c0b48b22b9e68d9c3fa5dc9b471fd22a0d636ba9b157fe419a3'


def helper(a):
 path=a.baseline_source/'tools/performance/a1-private-index/helper.py'
 if hashlib.sha256(path.read_bytes()).hexdigest()!=HELPER:raise RuntimeError('original helper changed')
 H=types.ModuleType('guard');H.__file__=str(path)
 exec(compile(path.read_bytes(),str(path),'exec'),H.__dict__)
 H.require(H.sha(a.baseline_source/'tools/performance/process-spawn/with_scope.py')==SCOPE,'original scope wrapper changed')
 H.require(H.sha(ROOT/'tools/shared/resource_watchdog.py')==WATCHDOG,'original cross-session watchdog changed')
 return H,path


def worker(a):
 H,hp=helper(a);out=a.output;producer=out/'producer'
 H.require(os.environ.get('MLF_BUILD_SCOPE')==str(os.getpgrp()),'guarded worker required')
 record=dict(complete=False,ordinary_full_producer=True,performance_samples=[],
  native_generational_comparison=False,fixed_point=False,derived_canonical_verified=False,stages=[])
 save=lambda:H.save(out/'receipt.json',record);save()
 def stage(label,argv,expected_exit=0):
  folder=out/label;folder.mkdir()
  row=dict(label=label,argv=list(map(str,argv)),complete=False,begin_monotonic_ns=time.perf_counter_ns())
  record['stages'].append(row);save()
  with (folder/'stdout').open('wb') as stdout,(folder/'stderr').open('wb') as stderr:
   result=subprocess.run(argv,cwd=ROOT,env=environment,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
  row.update(exit_code=result.returncode,end_monotonic_ns=time.perf_counter_ns(),
   stdout_sha256=H.sha(folder/'stdout'),stderr_sha256=H.sha(folder/'stderr'))
  row['complete']=result.returncode==expected_exit;save()
  H.require(row['complete'],'failed stage; no retry: '+label)
  return (folder/'stdout').read_bytes(),(folder/'stderr').read_bytes()
 try:
  with H.SerialLock(a.baseline_source/'.mlf-build'):
   H.require(all(k not in os.environ for k in ['MLF_QUERY_PROFILE','MLF_QUERY_SEMANTIC_AUDIT','MLF_QUERY_FAILPOINT']),'query instrumentation absent')
   baseline_path=a.baseline_producer/'receipt.json'
   H.require(H.sha(baseline_path)==BASE_RECEIPT,'fixed ordinary baseline receipt')
   baseline=H.load(baseline_path);H.require(baseline['complete'],'baseline incomplete')
   pins={str(baseline_path):BASE_RECEIPT,str(hp):HELPER,str(Path(__file__)):H.sha(Path(__file__))}
   scope=a.baseline_source/'tools/performance/process-spawn/with_scope.py';pins[str(scope)]=SCOPE
   pins[str(ROOT/'tools/shared/resource_watchdog.py')]=WATCHDOG
   historical_builtin=baseline['builtin_verification']
   H.require(H.sha(historical_builtin['path'])==historical_builtin['sha256'],'baseline builtin evidence changed')
   pins[historical_builtin['path']]=historical_builtin['sha256']
   historical=H.load(historical_builtin['path'])
   identity_path=ROOT/'tools/shared/builtin_prelude_identity.py'
   H.require(H.sha(identity_path)==baseline['builtin_verification_helpers']['tools/shared/builtin_prelude_identity.py']['sha256'],'official identity helper changed')
   identity_module=types.ModuleType('identity');identity_module.__file__=str(identity_path)
   exec(compile(identity_path.read_bytes(),str(identity_path),'exec'),identity_module.__dict__)
   new_identity,new_identity_inputs=identity_module.source_identity(ROOT)
   old_identity,old_identity_inputs=historical['source_identity'],historical['source_identity_inputs']
   H.require(len(new_identity_inputs['modules'])==56 and set(new_identity_inputs)==set(old_identity_inputs),'exact builtin identity inventory')
   H.require(set(new_identity_inputs['modules'])==set(old_identity_inputs['modules']),'same builtin closure')
   for key in new_identity_inputs:
    if key!='modules':H.require(new_identity_inputs[key]==old_identity_inputs[key],'builtin identity contract unchanged')
   changed_modules=[name for name in new_identity_inputs['modules'] if new_identity_inputs['modules'][name]!=old_identity_inputs['modules'][name]]
   H.require(changed_modules==['Bootstrap.Graph'],'Graph-only builtin closure difference')
   H.require(new_identity_inputs['modules']['Bootstrap.Graph']['path']==OWNER and new_identity_inputs['modules']['Bootstrap.Graph']['sha256']==CANDIDATE,'builtin Graph identity')
   original=(a.baseline_source/CANONICAL).read_bytes();derived=(ROOT/CANONICAL).read_bytes()
   H.require(H.sha(a.baseline_source/CANONICAL)==baseline['shared_inputs']['MLF.BuiltinPreludeData']['sha256'],'frozen original canonical')
   pins[str(a.baseline_source/CANONICAL)]=baseline['shared_inputs']['MLF.BuiltinPreludeData']['sha256']
   H.require(len(re.findall(rb'builtin-source-v1:[0-9a-f]{64}',original))==1 and original.count(old_identity.encode())==1,'one original identity field')
   H.require(b'builtin = (RawPrelude "'+old_identity.encode()+b'"' in original,'identity is the first RawPrelude field')
   H.require(new_identity!=old_identity and derived==original.replace(old_identity.encode(),new_identity.encode()) and derived.replace(new_identity.encode(),old_identity.encode())==original,'only true derived identity; inverse full bytes')
   record.update(derived_source_identity=new_identity,derived_canonical_status='unverified derived candidate until original fresh gates pass');save()
   changes=[]
   for group in ['shared_inputs','host_inputs','configuration_inputs']:
    for name,item in baseline[group].items():
     relative=Path(item['path']).relative_to(a.baseline_source);path=ROOT/relative
     expected={OWNER:CANDIDATE,CANONICAL:DERIVED}.get(str(relative),item['sha256'])
     H.require(H.sha(path)==expected,'unexpected source change: '+str(relative));pins[str(path)]=expected
     if expected!=item['sha256']:changes.append((group,name,str(relative)))
   H.require(set(changes)=={('shared_inputs','Bootstrap.Graph',OWNER),('shared_inputs','MLF.BuiltinPreludeData',CANONICAL)},'Graph plus one derived canonical difference')
   for item in [baseline['build_driver'],baseline['prepared_verification_helper'],*baseline['builtin_verification_helpers'].values()]:
    path=ROOT/Path(item['path']).relative_to(a.baseline_source)
    H.require(H.sha(path)==item['sha256'],'original build/verification code');pins[str(path)]=item['sha256']
   native=ROOT/'tools/shared/native_install.py'
   H.require(H.sha(native)==baseline['prepared_verification']['native']['verifier_sha256'],'original empty native registry verifier')
   pins[str(native)]=H.sha(native)
   direct=ROOT/'tools/shared/test_direct.py'
   H.require(H.sha(direct)=='138b387bbcff0f8bb717a3c7d7906337e9942d32f621ea963ca320d8d5ddd85e','original producer authenticator')
   pins[str(direct)]=H.sha(direct)
   ghc=Path(baseline['ghc']['path']);cc=Path(baseline['cc']['path'])
   for item in [baseline['ghc'],baseline['cc']]:H.require(H.sha(item['path'])==item['sha256'],'fixed build tool')
   environment=dict(PATH=str(ghc.parent)+':/usr/bin:/bin',LD_LIBRARY_PATH=str(a.runtime_library_dir),
    LIBRARY_PATH=str(a.runtime_library_dir),GHC_ENVIRONMENT='-',GHCRTS='',LC_ALL='C.UTF-8',LANG='C.UTF-8',
    OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MAKEFLAGS='-j1',PYTHONDONTWRITEBYTECODE='1')
   H.require(a.runtime_library_dir.is_dir(),'explicit build/runtime library directory')
   H.require(not producer.exists(),'fresh producer; no borrowed object tree')
   record.update(inputs=pins,source_changes=changes,build_environment=environment,
    source_counts={group:len(baseline[group]) for group in ['shared_inputs','host_inputs','configuration_inputs']});save()
   stage('build',[sys.executable,'-B',ROOT/'tools/shared/build.py','--bootstrap-only','--optimization','2',
    '--ghc',ghc,'--cc',cc,'--build-dir',producer])
   auth=H.authenticate(producer,ROOT)
   for group in ['shared_inputs','host_inputs','configuration_inputs']:
    H.require(set(auth[group])==set(baseline[group]),'unchanged source inventory: '+group)
   H.require(set(auth['resolved_modules'])==set(baseline['resolved_modules']) and len(auth['resolved_host_modules'])==4,'all shared and host modules rebuilt')
   H.require(set(auth['outputs'])==set(baseline['outputs']),'all ordinary executables linked')
   for key in ['ghc','cc','toolchain','installed_dependencies','ghc_info_sha256','ghc_settings','package_database_sha256','orchestrator']:
    H.require(auth[key]==baseline[key],'build tool/dependency identity differs: '+key)
   expected_flags=[f.replace(str(a.baseline_producer),str(producer)).replace(str(a.baseline_source),str(ROOT)) for f in baseline['flags']]
   H.require(auth['flags']==expected_flags,'ordinary flags differ beyond owned paths')
   verified_builtin=H.load(auth['builtin_verification']['path'])
   H.require(verified_builtin['source_identity']==new_identity and verified_builtin['candidate_verified'] is True and verified_builtin['exact_regeneration'] is True,'original complete builtin gates')
   record.update(derived_canonical_verified=True,derived_canonical_status='verified by original complete fresh builtin gates',producer_receipt_sha256=H.sha(producer/'receipt.json'),producer_outputs=auth['outputs']);save()
   emlf=producer/'bin/emlf'
   for label,flag,want in [('version','--version',b'emlf 0.3.0\n'),('identity','--implementation-identity',b'MLF/shared-haskell-v1 GHC\n')]:
    stdout,stderr=stage(label,[emlf,flag]);H.require(stdout==want and not stderr,'independent CLI output: '+label)
   stdout,stderr=stage('positive',[emlf,'--run','--expr','main = do { printInt 42; putStrLn "fusion λ" }'])
   H.require(stdout=='42\nfusion λ\n'.encode() and not stderr,'independent positive semantics')
   stdout,stderr=stage('negative',[emlf,'--type','--expr','stringLength 1'],expected_exit=1)
   H.require(not stdout and b'type constructor mismatch' in stderr,'independent negative type semantics')
   H.check_pins(pins)
   H.require(H.authenticate(producer,ROOT)==auth,'candidate producer changed after qualification')
   record.update(complete=True,pins_unchanged=True,qualified_cli=True,qualified_independent_semantics=True);save()
 except BaseException as error:
  record['error']=repr(error);save();raise


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for key in ['baseline-source','baseline-producer','runtime-library-dir','output']:parser.add_argument('--'+key,type=Path,required=True)
 parser.add_argument('--scope-worker',action='store_true',help=argparse.SUPPRESS)
 a=parser.parse_args()
 for key in ['baseline_source','baseline_producer','runtime_library_dir','output']:setattr(a,key,getattr(a,key).resolve())
 if a.scope_worker:return worker(a)
 a.output.mkdir(parents=True,exist_ok=False)
 H,hp=helper(a)
 argv=[sys.executable,'-B',a.baseline_source/'tools/performance/process-spawn/with_scope.py',sys.executable,'-B',Path(__file__).resolve()]
 for key in ['baseline-source','baseline-producer','runtime-library-dir','output']:argv.extend(['--'+key,getattr(a,key.replace('-','_'))])
 argv.append('--scope-worker')
 os.chdir(ROOT)
 watchdog=[sys.executable,'-B',ROOT/'tools/shared/resource_watchdog.py','--seconds','600',
  '--address-space-mib','6144','--rss-mib','5120','--disk-free-mib','5120','--max-output-mib','3072',a.output,*argv]
 os.execv(sys.executable,list(map(str,watchdog)))
if __name__=='__main__':main()
