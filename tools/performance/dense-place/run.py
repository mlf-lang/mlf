#!/usr/bin/env python3
"""Small f9 Graph-only differential gate. Never builds a compiler producer.

Must run under the sprint outer flock. Each executable is ordinary non-profiled
GHC, with the selected -O0/-O2 and unchanged pedantic demand flags. Optional
ABBA samples measure only this synthetic public-Graph corpus, not the compiler.
"""
from pathlib import Path
import argparse
import hashlib
import os
import shutil
import subprocess
import types
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
BASE='f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
OWNER='libraries/mlf-inference/Bootstrap/Graph.hs'
ORIGINAL='9df4833f55f0826181f8e1e974dc0672753e9462de0d134f64fc3f8c6f6e8a7f'
CANDIDATE='257c738b1c84446f02dda46b10139b2488e4ac95c8d353e6d0a1b77dca76110e'
LIMITS=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,
 host_available_floor_bytes=3*1024**3,max_work_bytes=3*1024**3,process_tree_rss_bytes=5*1024**3,wall_seconds=600)

def run_one(a):
 out=a.output.resolve();source=a.producer_source.resolve();producer=a.producer.resolve()
 assert 0<=a.bench_repetitions<=1000
 assert a.optimization=='2' or a.bench_repetitions==0
 assert not out.exists() and not out.is_relative_to(producer) and not producer.is_relative_to(out)
 out.mkdir(parents=True)
 hp=source/'tools/performance/a1-private-index/helper.py'
 H=types.ModuleType('guard');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
 record=dict(complete=False,baseline_ref=BASE,optimization=a.optimization,commands=[],
             compiler_producer_build=False,full_endpoint=False,performance_samples=[])
 save=lambda:H.save(out/'receipt.json',record);save()
 try:
  with H.SerialLock(source/'.mlf-build'):
   H.require(all(key not in os.environ for key in ['MLF_QUERY_PROFILE','MLF_QUERY_SEMANTIC_AUDIT','MLF_QUERY_FAILPOINT']), 'query diagnostic environment must be absent')
   auth=H.authenticate(producer,source)
   raw=subprocess.check_output(['git','show',BASE+':'+OWNER],cwd=ROOT)
   H.require(hashlib.sha256(raw).hexdigest()==ORIGINAL and H.sha(source/OWNER)==ORIGINAL,'current frozen oracle')
   H.require(H.sha(ROOT/OWNER)==CANDIDATE,'candidate owner changed')
   pins={str(path):H.sha(path) for path in [hp,Path(__file__),HERE/'Main.hs',ROOT/OWNER,source/OWNER,producer/'receipt.json']}
   sources=[]
   for name,data in [('LegacyGraph',raw),('CandidateGraph',(ROOT/OWNER).read_bytes())]:
    before=b'module Bootstrap.Graph where {';after=('module '+name+' where {').encode()
    H.require(data.count(before)==1 and after not in data,'unique header')
    adapted=data.replace(before,after);H.require(adapted.replace(after,before)==data,'reversible header-only oracle')
    path=out/(name+'.hs');path.write_bytes(adapted);sources.append(path);pins[str(path)]=H.sha(path)
   objects=out/'objects';objects.mkdir()
   borrowed={}
   for relative,digest in auth['object_inputs'].items():
    if relative.startswith('objects/') and relative.endswith(('.o','.hi')) and relative not in ['objects/Main.o','objects/Main.hi']:
     original=producer/relative;target=out/relative;target.parent.mkdir(parents=True,exist_ok=True)
     H.require(H.sha(original)==digest,'authenticated object changed');shutil.copy2(original,target)
     H.require(H.sha(target)==digest,'object copy mismatch');borrowed[str(target)]=digest
   def run(label,argv,wall=None):
    # Every child inherits the one outer Runner group and its remaining budget.
    folder=out/label;folder.mkdir();argv=list(map(str,argv))
    row=dict(argv=argv,cwd=str(source),complete=False,scope_guard='one outer 240-second process group')
    begin=time.perf_counter_ns()
    try:
     with (folder/'stdout').open('wb') as stdout,(folder/'stderr').open('wb') as stderr:
      done=subprocess.run(argv,cwd=source,env=H.env(),stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,check=False)
     row.update(exit_code=done.returncode,wall_seconds=(time.perf_counter_ns()-begin)/1e9,complete=done.returncode==0)
     H.require(row['complete'],'command failed: '+label)
     return row
    finally:
     H.save(folder/'command.json',row);record['commands'].append(row);save()
   H.require(H.sha(auth['cc']['path'])==auth['cc']['sha256'],'authenticated cc changed')
   cobjects=[]
   for name in ['host.o','supervisor.o']:
    commands=[c for c in auth['commands'] if '-o' in c['argv'] and c['argv'][c['argv'].index('-o')+1]==str(producer/name)]
    H.require(len(commands)==1,'unique original C compile')
    command=commands[0];H.require(command['cwd']==str(source) and command['argv'][0]==auth['cc']['path'],'C provenance')
    argv=list(command['argv']);argv[argv.index('-o')+1]=str(out/name)
    run('compile-'+name,argv)
    H.require(H.sha(out/name)==H.sha(producer/name),'private exact C rebuild byte equality')
    pins[str(producer/name)]=H.sha(producer/name);pins[str(out/name)]=H.sha(out/name);cobjects.append(out/name)
   flags=[];skip=False
   for flag in auth['flags']:
    if skip:skip=False;continue
    if flag in ['-odir','-hidir']:skip=True
    elif flag.startswith('-i'):continue
    else:flags.append('-O'+a.optimization if flag in ['-O0','-O2'] else flag)
   flags+=['-i','-i'+str(objects),'-odir',str(objects),'-hidir',str(objects)]
   H.require('-fpedantic-bottoms' in flags and '-fno-state-hack' in flags,'ordinary demand flags')
   record.update(inputs=pins,borrowed_objects=borrowed,flags=flags,authentication=auth,
     c_authentication='exact original cc/source/command rebuild and byte equality')
   save()
   ghc=auth['ghc']['path']
   for path in [*sources,HERE/'Main.hs']:run('compile-'+path.stem,[ghc,*flags,'-c',path])
   H.check_pins(borrowed)
   binary=out/'controls-probe'
   run('link',[ghc,*flags,'-rtsopts=ignoreAll',*sorted(objects.rglob('*.o')),*cobjects,'-o',binary])
   run('controls',[binary],120)
   text=(out/'controls/stdout').read_text()
   lines=text.splitlines()
   H.require(len(lines)==5 and lines[0]=='PASS 12000 exact validation outcomes' and
             lines[1].startswith('PASS public unification=') and
             lines[2]=='PASS 480 signed-Int64 and sparse-layout public results' and
             lines[3]=='PASS 20 placement demand, failure and scratch-state controls' and
             lines[4]=='PASS 6 aliased scratch-array controls: 5 placements and 1 entry cycle','complete fixed control inventory')
   H.require(not (out/'controls/stderr').read_bytes(),'empty control stderr')
   record['controls_stdout']=text;save()
   if a.bench_repetitions:
    expected=None
    # One non-sampled warm-up per side, then fixed two ABBA blocks.
    for index,side in enumerate(['base','candidate']+['base','candidate','candidate','base']*2):
     label=('warmup-' if index<2 else 'sample-')+str(index)+'-'+side
     outcome=run(label,[binary,'bench',side,str(a.bench_repetitions)],120)
     stdout=(out/label/'stdout').read_bytes()
     H.require(not (out/label/'stderr').read_bytes(),'empty benchmark stderr')
     if expected is None:expected=stdout
     H.require(stdout==expected,'same fully consumed graph-output checksum')
     if index>=2:record['performance_samples'].append(dict(side=side,command=label,wall_seconds=outcome['wall_seconds']))
     save()
   H.check_pins(pins);H.check_pins(borrowed)
   H.require(H.authenticate(producer,source)==auth,'producer unchanged')
   record.update(complete=True,executable_sha256=H.sha(binary));save();print(text,end='')
 except BaseException as e:
  record['error']=repr(e);save();raise

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['producer','producer-source','output']:p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--optimization',choices=['0','2','both'],default='both')
 p.add_argument('--bench-repetitions',type=int,default=0)
 p.add_argument('--scope-worker',action='store_true',help=argparse.SUPPRESS)
 a=p.parse_args()
 if a.scope_worker:
  if os.environ.get("MLF_BUILD_SCOPE")!=str(os.getpgrp()):
   raise RuntimeError("scope-worker requires the outer guarded process group")
  for optimization in (['0','2'] if a.optimization=='both' else [a.optimization]):
   selected=argparse.Namespace(**vars(a));selected.optimization=optimization
   selected.output=a.output/('O'+optimization)
   if optimization=='0':selected.bench_repetitions=0
   run_one(selected)
  return
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 source=a.producer_source.resolve();hp=source/'tools/performance/a1-private-index/helper.py'
 H=types.ModuleType('guard');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
 argv=[sys.executable,'-B',str(source/'tools/performance/process-spawn/with_scope.py'),sys.executable,'-B',str(Path(__file__).resolve()),*sys.argv[1:],'--scope-worker']
 H.Runner(out,{**LIMITS,'wall_seconds':240}).run(argv,ROOT,out/'scope')

if __name__=='__main__':main()
