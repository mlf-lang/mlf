#!/usr/bin/env python3
"""New-runtime 60-second synthetic Graph screen; never builds a compiler.

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
import struct

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

EXPECTED_CONTROLS=(
 'PASS 12000 exact validation outcomes\n'
 'PASS public unification=5616 frozen-successful-rebinds=1433 graft-parent-edges=16\n'
 'PASS 480 signed-Int64 and sparse-layout public results\n'
 'PASS 20 placement demand, failure and scratch-state controls\n'
 'PASS 6 aliased scratch-array controls: 5 placements and 1 entry cycle\n'
 'PASS 120 valid complete normalization graphs\n'
 'PASS 21 read action, offset, array/cell demand, sharing and cached-kind controls\n').encode()
HELPER_SHA='0d11b29419a32fc9832096951aa085cc317c8a304b9db110ee96ba411a4ce7cc'
SCOPE_SHA='d8ffe4256f333c0b48b22b9e68d9c3fa5dc9b471fd22a0d636ba9b157fe419a3'


def load_helper(source):
 hp=source/'tools/performance/a1-private-index/helper.py'
 import hashlib
 if hashlib.sha256(hp.read_bytes()).hexdigest()!=HELPER_SHA:
  raise RuntimeError('guard helper changed')
 H=types.ModuleType('guard');H.__file__=str(hp)
 exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
 return H,hp


def target_environment(library_dir):
 # Deliberate allowlist, not an overlay of os.environ. The unknown historical
 # LD tail is not reconstructed or claimed equivalent. No injection/allocator
 # variables, LIBRARY_PATH, locale search paths or extra GHC settings survive.
 return dict(PATH='/usr/bin:/bin',LD_LIBRARY_PATH=str(library_dir),
  LANG='C.UTF-8',LC_ALL='C.UTF-8',TZ='UTC',GHC_ENVIRONMENT='-',GHCRTS='',
  OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MAKEFLAGS='-j1')


def identity(H,path):
 path=Path(path);real=path.resolve(strict=True)
 H.require(path.is_absolute() and real.is_file(),'runtime file required')
 return dict(path=str(path),realpath=str(real),sha256=H.sha(real))


def elf_interpreter(H,binary):
 # Narrow reader for the authenticated Linux x86-64 probe, not a generic ELF
 # resolver. The trusted system loader performs actual transitive resolution.
 with binary.open('rb') as stream:
  header=stream.read(64)
  H.require(len(header)==64 and header[:7]==b'\x7fELF\x02\x01\x01','ELF64 little-endian probe required')
  H.require(struct.unpack_from('<H',header,18)[0]==62,'x86-64 probe required')
  offset=struct.unpack_from('<Q',header,32)[0]
  entry_size,count=struct.unpack_from('<HH',header,54)
  H.require(entry_size==56 and 0<count<=128 and offset+count*56<=binary.stat().st_size,'bounded ELF program headers')
  interpreters=[]
  for index in range(count):
   stream.seek(offset+index*56);entry=stream.read(56)
   if struct.unpack_from('<I',entry)[0]==3:
    position,size=struct.unpack_from('<Q',entry,8)[0],struct.unpack_from('<Q',entry,32)[0]
    H.require(1<size<=256 and position+size<=binary.stat().st_size,'bounded PT_INTERP')
    stream.seek(position);data=stream.read(size)
    H.require(data.endswith(b'\0') and b'\0' not in data[:-1],'single ELF interpreter')
    interpreters.append(data[:-1].decode('ascii'))
 H.require(interpreters==['/lib64/ld-linux-x86-64.so.2'],'expected trusted system loader required')
 return Path(interpreters[0])


def loader_rows(H,stdout,loader):
 rows=[];names=set()
 for line in stdout.decode('utf-8').splitlines():
  text=line.strip()
  if re.fullmatch(r'linux-vdso\.so\.1 \(0x[0-9a-f]+\)',text):
   row=dict(name='linux-vdso.so.1',kind='kernel virtual mapping; no file hash')
  else:
   match=re.fullmatch(r'(?:(\S+) => )?(/\S+) \(0x[0-9a-f]+\)',text)
   H.require(match is not None,'unrecognized or unresolved trusted-loader row: '+text)
   name,path=match.groups();row=dict(name=name or path,kind='file',**identity(H,path))
  H.require(row['name'] not in names,'duplicate runtime library name')
  names.add(row['name']);rows.append(row)
 H.require(any(r.get('realpath')==str(loader.resolve()) for r in rows),'loader missing from runtime listing')
 H.require(any(r['name']=='libc.so.6' for r in rows),'libc missing from runtime listing')
 return sorted(rows,key=lambda row:row['name'])


def runtime_configuration(H):
 # The fixed environment cannot disable the system-wide preload file. Refuse
 # nonempty global injection; retain cache bytes because it affects resolution.
 result={}
 for name in ['/etc/ld.so.cache','/etc/ld.so.preload']:
  path=Path(name)
  if path.exists():
   if name.endswith('preload'):H.require(path.read_bytes().strip()==b'','system-wide preload is not empty')
   result[name]=identity(H,path)
  else:result[name]=None
 return result


def worker(a):
 H,hp=load_helper(a.producer_source);out=a.output
 H.require(os.environ.get('MLF_BUILD_SCOPE')==str(os.getpgrp()),'guarded scope-worker only')
 environment=target_environment(a.runtime_library_dir)
 record=dict(complete=False,synthetic_graph_only=True,compiler_speedup_claim=False,
  native_mlf_result=False,allocation_measurement=False,
  qualification_environment_changed=True,qualification_environment_history_incomplete=True,
  historical_runtime_environment_reproduced=False,build_provenance_verified_at_gate=True,
  toolchain_reauthenticated_this_run=False,borrowed_build_objects_reauthenticated_this_run=False,
  historical_codegen_outputs_reauthenticated_this_run=False,
  checksum_kind='weak sum of all serialized character codes; equality is not exact graph equality',
  repetitions=REPETITIONS,operations_per_process=5616*REPETITIONS,fixed_order=ORDER,
  target_environment=environment,phases=[],commands=[],samples=[],warmups=[],
  timed_boundary='Popen through exact-child wait4; includes startup, frozen input selection, ID renaming, public unification, complete result serialization and checksum')
 save=lambda:H.save(out/'samples.json',record);save()
 def phase(label,action):
  item=dict(label=label,begin_monotonic_ns=time.perf_counter_ns(),complete=False)
  record['phases'].append(item);save()
  result=action()
  item.update(end_monotonic_ns=time.perf_counter_ns(),complete=True);save()
  return result
 def command(label,argv):
  folder=out/label;folder.mkdir()
  row=dict(label=label,argv=argv,complete=False)
  record['commands'].append(row);H.save(folder/'command.json',row);save()
  done=threading.Event();waited=[];errors=[]
  with (folder/'stdout').open('wb') as stdout,(folder/'stderr').open('wb') as stderr:
   begin=time.perf_counter_ns()
   process=subprocess.Popen(argv,cwd=ROOT,env=environment,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
   def wait():
    try:
     _,status,usage=os.wait4(process.pid,0);waited.append((status,usage,time.perf_counter_ns()))
    except BaseException as e:errors.append(e)
    finally:done.set()
   thread=threading.Thread(target=wait,daemon=True);thread.start()
   row['pid']=process.pid;H.save(folder/'command.json',row);save()
   timed_out=not done.wait(max(0,15-(time.perf_counter_ns()-begin)/1e9))
   if timed_out:process.kill();done.wait()
   thread.join();H.require(not errors and len(waited)==1,'exact wait4 failed')
   status,usage,end=waited[0];process.returncode=os.waitstatus_to_exitcode(status)
   row.update(exit_code=process.returncode,reason='child 15-second limit' if timed_out else None,
    wall_seconds=(end-begin)/1e9,child_user_seconds=usage.ru_utime,
    child_system_seconds=usage.ru_stime,max_child_rss_bytes=usage.ru_maxrss*1024)
  stdout=(folder/'stdout').read_bytes();stderr=(folder/'stderr').read_bytes()
  row.update(stdout_sha256=H.sha(folder/'stdout'),stderr_sha256=H.sha(folder/'stderr'),
   process_complete=not timed_out and process.returncode==0 and not stderr)
  H.save(folder/'command.json',row);save()
  H.require(row['process_complete'],'failed/timed-out command; no retry')
  return row,stdout
 def accept(row):
  row['complete']=True;H.save(out/row['label']/'command.json',row);save()
 try:
  with H.SerialLock(a.producer_source/'.mlf-build'):
   H.require(all(k not in os.environ for k in ['MLF_QUERY_PROFILE','MLF_QUERY_SEMANTIC_AUDIT','MLF_QUERY_FAILPOINT']),'query diagnostic environment absent')
   def provenance():
    pins={}
    for root,receipts in [(a.semantics,SEMANTIC),(a.codegen,CODEGEN)]:
     for relative,digest in receipts.items():
      path=root/relative;H.require(H.sha(path)==digest,'exact historical qualification receipt')
      H.require(H.load(path)['complete'],'historical qualification incomplete');pins[str(path)]=digest
    outer=H.load(a.codegen/'bounded-receipt.json');capture=H.load(a.codegen/'work/receipt.json')
    H.require(outer['exit_code']==0 and outer['reason'] is None,'historical codegen scope failed')
    H.require(capture['capture_only'] is True and capture['compiler_producer_build'] is False and capture['benchmark_samples']==[],'owner-only codegen provenance')
    H.require(capture['inputs'].get(str(ROOT/OWNER))==CANDIDATE,'codegen candidate identity')
    H.require(capture['sides']['baseline']['object_sha256']==capture['sides']['anchor']['object_sha256'] and
     capture['sides']['baseline']['interface_sha256']==capture['sides']['anchor']['interface_sha256'],'historical baseline anchor equality')
    H.require(H.sha(a.mechanism)==MECHANISM,'exact independent mechanism review')
    proof=H.load(a.mechanism);pins[str(a.mechanism)]=MECHANISM
    H.require(proof['candidate_sha256']==CANDIDATE and proof['mechanism_supported'] is True and
     proof['eligible_for_graph_sample'] is True and proof['execution_authorized_by_this_file'] is False and
     proof['performance_demonstrated'] is False,'mechanism eligibility only, not execution approval')
    return pins
   pins=phase('historical-receipts',provenance)
   semantic=H.load(a.semantics/'O2/receipt.json')
   H.require(semantic['optimization']=='2' and '-O2' in semantic['flags'] and
    '-fpedantic-bottoms' in semantic['flags'] and '-fno-state-hack' in semantic['flags'] and
    not any(f.startswith('-prof') for f in semantic['flags']),'ordinary semantic flags')
   H.require(len(semantic['inputs'])==15,'exact historical semantic input inventory')
   phase('semantic-inputs',lambda:H.check_pins(semantic['inputs']))
   pins.update(semantic['inputs'])
   def execution_inputs():
    H.require(H.sha(a.producer_source/'tools/performance/process-spawn/with_scope.py')==SCOPE_SHA,'scope wrapper changed')
    H.require(H.sha(ROOT/OWNER)==CANDIDATE,'candidate owner changed')
    for path in [hp,Path(__file__),a.producer_source/'tools/performance/process-spawn/with_scope.py',Path(sys.executable).resolve()]:
     pins[str(path)]=H.sha(path)
    binary=a.semantics/'O2/controls-probe'
    H.require(H.sha(binary)==semantic['executable_sha256'],'qualified executable changed')
    pins[str(binary)]=semantic['executable_sha256']
    record.update(inputs=pins,binary_sha256=pins[str(binary)],python=identity(H,Path(sys.executable)),
     python_version=sys.version,kernel=tuple(os.uname()),cpu_affinity=sorted(os.sched_getaffinity(0)))
    save();return binary
   binary=phase('execution-inputs',execution_inputs)
   def runtime(label):
    H.require(a.runtime_library_dir.is_dir(),'explicit runtime library directory required')
    loader=elf_interpreter(H,binary)
    config=runtime_configuration(H)
    loader_pin=identity(H,loader)
    row,stdout=command(label,[str(loader),'--list',str(binary)])
    result=dict(loader=loader_pin,library_directory=dict(path=str(a.runtime_library_dir),realpath=str(a.runtime_library_dir.resolve(strict=True))),
     configuration=config,libraries=loader_rows(H,stdout,loader))
    H.require(identity(H,loader)==loader_pin,'loader changed during resolution')
    accept(row);return result
   runtime_before=phase('runtime-before',lambda:runtime('runtime-resolve-before'))
   record['runtime_before']=runtime_before;save()
   def qualify():
    row,stdout=command('runtime-controls',[str(binary)])
    H.require(stdout==EXPECTED_CONTROLS,'new runtime controls exact seven-line output')
    accept(row);record['runtime_controls']=row;save()
   phase('runtime-controls',qualify)
   expected=None
   for index,side in enumerate(ORDER):
    label=('warmup-' if index<2 else 'sample-')+str(index)+'-'+side
    row,stdout=phase(label,lambda:command(label,[str(binary),'bench',side,str(REPETITIONS)]))
    row.update(side=side,index=index,warmup=index<2)
    record['warmups' if index<2 else 'samples'].append(row)
    if expected is None:expected=stdout
    H.require(stdout==expected and bool(re.fullmatch(rb'\(179712,[0-9]+\)\n',stdout)),'mismatched sample; no retry')
    accept(row)
   phase('post-inputs',lambda:H.check_pins(pins))
   runtime_after=phase('runtime-after',lambda:runtime('runtime-resolve-after'))
   record['runtime_after']=runtime_after;save()
   H.require(runtime_after==runtime_before,'runtime mapping or bytes changed')
   H.require(identity(H,Path(sys.executable))==record['python'],'Python executable path changed')
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
   record.update(complete=True,checksum_stdout=expected.decode(),pins_unchanged=True,runtime_unchanged=True)
   save()
 except BaseException as e:
  record['error']=repr(e);save();raise


def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['producer-source','semantics','codegen','mechanism','runtime-library-dir','output']:p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--scope-worker',action='store_true',help=argparse.SUPPRESS)
 a=p.parse_args()
 for key in ['producer_source','semantics','codegen','mechanism','runtime_library_dir','output']:
  # Keep the explicit library search path (including its symlink identity).
  path=getattr(a,key);setattr(a,key,path.absolute() if key=='runtime_library_dir' else path.resolve())
 if a.scope_worker:return worker(a)
 names=[('warmup-' if i<2 else 'sample-')+str(i)+'-'+side for i,side in enumerate(ORDER)]
 reserved={'scope','samples.json','samples.json.tmp','runtime-controls','runtime-resolve-before','runtime-resolve-after'}
 if len(names)!=10 or len(set(names))!=10 or set(names)&reserved:raise RuntimeError('artifact/log name inventory conflicts')
 a.output.mkdir(parents=True,exist_ok=False)
 H,hp=load_helper(a.producer_source)
 H.require(H.sha(a.producer_source/'tools/performance/process-spawn/with_scope.py')==SCOPE_SHA,'scope wrapper changed before launch')
 argv=[sys.executable,'-B',str(a.producer_source/'tools/performance/process-spawn/with_scope.py'),sys.executable,'-B',str(Path(__file__).resolve())]
 for key in ['producer-source','semantics','codegen','mechanism','runtime-library-dir','output']:
  argv.extend(['--'+key,str(getattr(a,key.replace('-','_')))])
 argv.append('--scope-worker')
 H.Runner(a.output,LIMITS).run(argv,ROOT,a.output/'scope')
if __name__=='__main__':main()
