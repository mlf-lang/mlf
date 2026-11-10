#!/usr/bin/env python3
"""Proposed 60-second synthetic Graph screen; never builds a compiler.

This runner requires separate coordinator admission after the ordinary owner
codegen gate. Preparing this file does not authorize execution. All warm-ups,
eight predetermined samples, source authentication and postchecks share one
outer resource scope. A result is not compiler or native MLF throughput.
"""
from pathlib import Path
import argparse
import json
import math
import statistics
import os
import re
import subprocess
import sys
import threading
import time
import types

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OWNER='libraries/mlf-inference/Bootstrap/Graph.hs'
CANDIDATE='fdb9e899392ac0068f9f11432d512d1168934455a6da733a10e7cabb52d19df3'
SEMANTIC={
 'scope/command.json':'797431e95c583d49826b28a340c657cfaa82ef3c406182413d7010209c637eb1',
 'O0/receipt.json':'9b30709536ce1de10006d1d949149ef8a6400cfac97d642c88a01a678ee826d4',
 'O2/receipt.json':'33195a0c8cc283f3134b8f269e7c31ddae92171b29001238116dadc654263c92'}
CODEGEN={
 'bounded-receipt.json':'4855bb5e2c857f03c6ffde9de7b04fa6e024b9fdc59d3c5d4539c299beffb9dd',
 'work/receipt.json':'eaa78545d5a7f7eb71928c04094a69cb44d59b28c6095e5bd859ae5ec1e36ede'}
MECHANISM='bcb421e427f48fd10c10408f700f498ef6819375b2441ecaa0a8c75322e34426'
REPETITIONS=32
ORDER=['base','candidate']+['base','candidate','candidate','base']*2
LIMITS=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,
 host_available_floor_bytes=3*1024**3,max_work_bytes=3*1024**3,
 process_tree_rss_bytes=5*1024**3,wall_seconds=60)

def load_helper(source):
 hp=source/'tools/performance/a1-private-index/helper.py'
 H=types.ModuleType('guard');H.__file__=str(hp)
 exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
 return H,hp

def worker(a):
 H,hp=load_helper(a.producer_source);out=a.output
 H.require(os.environ.get('MLF_BUILD_SCOPE')==str(os.getpgrp()),'guarded scope-worker only')
 record=dict(complete=False,synthetic_graph_only=True,compiler_speedup_claim=False,
  native_mlf_result=False,allocation_measurement=False,
  checksum_kind='weak sum of all serialized character codes; equality is not exact graph equality',repetitions=REPETITIONS,
  operations_per_process=5616*REPETITIONS,fixed_order=ORDER,samples=[],warmups=[],
  timed_boundary='Popen through exact-child wait4; includes startup, frozen input selection, ID renaming, public unification, complete result serialization and checksum')
 save=lambda:H.save(out/'samples.json',record);save()
 try:
  with H.SerialLock(a.producer_source/'.mlf-build'):
   H.require(all(k not in os.environ for k in ['MLF_QUERY_PROFILE','MLF_QUERY_SEMANTIC_AUDIT','MLF_QUERY_FAILPOINT']),'query diagnostic environment absent')
   auth=H.authenticate(a.producer,a.producer_source)
   H.require(H.sha(ROOT/OWNER)==CANDIDATE,'candidate owner changed')
   pins={str(path):H.sha(path) for path in [hp,Path(__file__),ROOT/OWNER,a.producer/'receipt.json']}
   for relative,digest in SEMANTIC.items():
    path=a.semantics/relative;H.require(H.sha(path)==digest,'exact successful semantic receipt')
    H.require(H.load(path)['complete'],'semantic gate incomplete');pins[str(path)]=digest
   for relative,digest in CODEGEN.items():
    path=a.codegen/relative;H.require(H.sha(path)==digest,'exact successful owner-codegen receipt')
    H.require(H.load(path)['complete'],'owner-codegen capture incomplete');pins[str(path)]=digest
   outer=H.load(a.codegen/'bounded-receipt.json');capture=H.load(a.codegen/'work/receipt.json')
   H.require(outer['exit_code']==0 and outer['reason'] is None,'owner-codegen scope failed')
   H.require(capture['capture_only'] is True and capture['compiler_producer_build'] is False and capture['benchmark_samples']==[], 'owner-only codegen provenance')
   H.require(capture['inputs'].get(str(ROOT/OWNER))==CANDIDATE,'codegen candidate identity')
   H.require(capture['sides']['baseline']['object_sha256']==capture['sides']['anchor']['object_sha256'] and
    capture['sides']['baseline']['interface_sha256']==capture['sides']['anchor']['interface_sha256'],'baseline owner anchor equality')
   H.check_pins(capture['inputs']);H.check_pins(capture['output_pins'])
   H.require(H.sha(a.mechanism)==MECHANISM,'exact independent mechanism review')
   proof=H.load(a.mechanism);pins[str(a.mechanism)]=MECHANISM
   H.require(proof['candidate_sha256']==CANDIDATE and proof['mechanism_supported'] is True and
    proof['eligible_for_graph_sample'] is True and proof['execution_authorized_by_this_file'] is False and
    proof['performance_demonstrated'] is False,'codegen mechanism does not qualify this sample')
   semantic=H.load(a.semantics/'O2/receipt.json')
   H.require(semantic['optimization']=='2' and '-O2' in semantic['flags'] and
    '-fpedantic-bottoms' in semantic['flags'] and '-fno-state-hack' in semantic['flags'] and
    not any(f.startswith('-prof') for f in semantic['flags']),'ordinary semantic flags')
   H.check_pins(semantic['inputs']);H.check_pins(semantic['borrowed_objects'])
   binary=a.semantics/'O2/controls-probe'
   H.require(H.sha(binary)==semantic['executable_sha256'],'qualified executable changed')
   pins[str(binary)]=semantic['executable_sha256'];record.update(inputs=pins,binary_sha256=pins[str(binary)])
   save();expected=None
   for index,side in enumerate(ORDER):
    label=('warmup-' if index<2 else 'sample-')+str(index)+'-'+side
    folder=out/label;folder.mkdir()
    argv=[str(binary),'bench',side,str(REPETITIONS)]
    row=dict(side=side,index=index,warmup=index<2,argv=argv,complete=False)
    done=threading.Event();waited=[];errors=[]
    H.save(folder/'command.json',row)
    record['warmups' if index<2 else 'samples'].append(row);save()
    with (folder/'stdout').open('wb') as stdout,(folder/'stderr').open('wb') as stderr:
     begin=time.perf_counter_ns()
     process=subprocess.Popen(argv,cwd=ROOT,env=H.env(),stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
     def wait():
      try:
       _,status,usage=os.wait4(process.pid,0)
       waited.append((status,usage,time.perf_counter_ns()))
      except BaseException as e:errors.append(e)
      finally:done.set()
     thread=threading.Thread(target=wait,daemon=True);thread.start()
     row['pid']=process.pid;H.save(folder/'command.json',row);save()
     timed_out=not done.wait(max(0,15-(time.perf_counter_ns()-begin)/1e9))
     if timed_out:
      process.kill();done.wait()
     thread.join()
     H.require(not errors and len(waited)==1,'exact wait4 failed')
     status,usage,end=waited[0];process.returncode=os.waitstatus_to_exitcode(status)
     row.update(exit_code=process.returncode,reason='child 15-second limit' if timed_out else None,
       wall_seconds=(end-begin)/1e9,child_user_seconds=usage.ru_utime,
       child_system_seconds=usage.ru_stime,max_child_rss_bytes=usage.ru_maxrss*1024)
    stdout=(folder/'stdout').read_bytes();stderr=(folder/'stderr').read_bytes()
    row.update(stdout_sha256=H.sha(folder/'stdout'),stderr_sha256=H.sha(folder/'stderr'))
    if expected is None:expected=stdout
    row['complete']=not timed_out and process.returncode==0 and not stderr and stdout==expected and bool(re.fullmatch(rb'\(179712,[0-9]+\)\n',stdout))
    H.save(folder/'command.json',row)
    save()
    H.require(row['complete'],'failed/timed-out/mismatched sample; no retry')
   H.check_pins(pins);H.check_pins(semantic['inputs']);H.check_pins(semantic['borrowed_objects'])
   H.check_pins(capture['inputs']);H.check_pins(capture['output_pins'])
   H.require(H.authenticate(a.producer,a.producer_source)==auth,'producer changed')
   base=[r['wall_seconds'] for r in record['samples'] if r['side']=='base']
   candidate=[r['wall_seconds'] for r in record['samples'] if r['side']=='candidate']
   H.require(len(record['samples'])==8 and len(base)==len(candidate)==4 and all(r['complete'] for r in record['samples']),'complete fixed cohort required')
   geometric=lambda xs:math.exp(sum(map(math.log,xs))/len(xs))
   record['descriptive_wall_summary']=dict(all_base_seconds=base,all_candidate_seconds=candidate,
    base_median_seconds=statistics.median(base),candidate_median_seconds=statistics.median(candidate),
    candidate_divided_by_base_median=statistics.median(candidate)/statistics.median(base),
    candidate_divided_by_base_geometric_mean=geometric(candidate)/geometric(base),
    block_candidate_divided_by_base_geometric_mean=[geometric(candidate[i:i+2])/geometric(base[i:i+2]) for i in [0,2]],
    warmups_excluded=True,no_outliers_removed=True,no_significance_claim=True)
   record.update(complete=True,checksum_stdout=expected.decode(),pins_unchanged=True)
   save()
 except BaseException as e:
  record['error']=repr(e);save();raise

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['producer','producer-source','semantics','codegen','mechanism','output']:p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--scope-worker',action='store_true',help=argparse.SUPPRESS)
 a=p.parse_args()
 for key in ['producer','producer_source','semantics','codegen','mechanism','output']:setattr(a,key,getattr(a,key).resolve())
 if a.scope_worker:return worker(a)
 names=[('warmup-' if i<2 else 'sample-')+str(i)+'-'+side for i,side in enumerate(ORDER)]
 if len(names)!=10 or len(set(names))!=10 or set(names)&{'scope','samples.json','samples.json.tmp'}:
  raise RuntimeError('artifact/log name inventory conflicts')
 a.output.mkdir(parents=True,exist_ok=False)
 H,hp=load_helper(a.producer_source)
 argv=[sys.executable,'-B',str(a.producer_source/'tools/performance/process-spawn/with_scope.py'),sys.executable,'-B',str(Path(__file__).resolve()),
  '--producer',str(a.producer),'--producer-source',str(a.producer_source),'--semantics',str(a.semantics),'--codegen',str(a.codegen),'--mechanism',str(a.mechanism),'--output',str(a.output),'--scope-worker']
 H.Runner(a.output,LIMITS).run(argv,ROOT,a.output/'scope')
if __name__=='__main__':main()
