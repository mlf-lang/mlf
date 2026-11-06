#!/usr/bin/env python3
"""Five paired all-workload benchmarks of default emlf installed-stdlib builds."""
import argparse, hashlib, json, math, os, shlex, statistics, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/'benchmarks/manifest.json'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
 return h.hexdigest()
def run(argv, *, stdin=None, stdout=None):
 start=time.monotonic_ns()
 with (Path(stdin).open('rb') if stdin else open(os.devnull,'rb')) as inp,(Path(stdout).open('wb') if stdout else open(os.devnull,'wb')) as out:
  result=subprocess.run([str(x) for x in argv],cwd=ROOT,stdin=inp,stdout=out,stderr=subprocess.PIPE,timeout=1800)
 elapsed=(time.monotonic_ns()-start)/1e9
 if result.returncode: raise RuntimeError(f'command failed {argv}: {result.stderr.decode(errors="replace")}')
 return {'command':[str(x) for x in argv],'wall_seconds':elapsed,'exit_code':result.returncode,'stderr':result.stderr.decode(errors='replace')}
def compare(name,actual,expected):
 a=Path(actual).read_bytes(); b=Path(expected).read_bytes()
 if name in ('n-body','spectral-norm'):
  aa=a.split(); bb=b.split(); needed=2 if name=='n-body' else 1
  if len(aa)!=needed or len(bb)!=needed: raise ValueError('numeric token count')
  try: pairs=[(float(x),float(y)) for x,y in zip(aa,bb)]
  except ValueError: raise ValueError('invalid numeric token')
  if not all(math.isfinite(x) and math.isfinite(y) and abs(x-y)<=1e-8 for x,y in pairs): raise ValueError('numeric mismatch')
 elif name in ('binary-trees','pidigits','fannkuch-redux','k-nucleotide'):
  if a.split()!=b.split(): raise ValueError('token output mismatch '+name)
 elif sha(actual)!=sha(expected): raise ValueError('byte output mismatch '+name)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for x in ['compiler','install-receipt','install-timing','oracle','baseline-dir','check-dir','clang','output']: p.add_argument('--'+x,required=True,type=Path)
 a=p.parse_args(); compiler=a.compiler.resolve(strict=True); baseline=a.baseline_dir.resolve(strict=True); check=a.check_dir.resolve(strict=True); validate=a.oracle.resolve(strict=True); clang=a.clang.resolve(strict=True); output=a.output.absolute(); output.mkdir(parents=True,exist_ok=False)
 report={'status':'running','scope':'default emlf, installed standard library; installation excluded and separately reported','workloads':[]}
 def save(): (output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
 save()
 try:
  manifest=json.loads(MANIFEST.read_text()); previous=json.loads((baseline/'results.json').read_text()); prior=json.loads((check/'results.json').read_text())
  if previous.get('status')!='correctness-passed' or prior.get('status')!='correctness-passed' or prior.get('mode')!='check-only' or prior.get('performance_checked') is not False: raise ValueError('baseline or fixture proof incomplete')
  baseline_by_name={x['benchmark']:x for x in previous['workloads']}
  if set(baseline_by_name)!={w['name'] for w in manifest['workloads']}: raise ValueError('baseline inventory mismatch')
  install=a.install_receipt.resolve(strict=True); timing=a.install_timing.resolve(strict=True); compiler_receipt=compiler.parent.parent/'receipt.json'
  report['install_receipt']=json.loads(install.read_text()); report['install_timing']=json.loads(timing.read_text()); report['compiler_receipt']=json.loads(compiler_receipt.read_text())
  cr=report['compiler_receipt']; ir=report['install_receipt']; tr=report['install_timing']
  record=cr.get('outputs',{}).get('emlf',{})
  if cr.get('format')!=1 or cr.get('complete') is not True or not isinstance(record.get('path'),str) or Path(record['path']).resolve(strict=True)!=compiler or record.get('sha256')!=sha(compiler): raise ValueError('compiler receipt does not authenticate selected compiler')
  if ir.get('format')!='MLF-NATIVE-INSTALL-1' or ir.get('complete') is not True: raise ValueError('native installation receipt incomplete')
  if tr.get('status')!='complete' or tr.get('returncode')!=0: raise ValueError('installation timing receipt incomplete')
  dependencies=[compiler,compiler_receipt,install,timing,MANIFEST,validate,clang,baseline/'results.json',check/'results.json',ROOT/'benchmarks/fasta/c/upstream.c',Path(__file__).resolve(),ROOT/'tools/bench/Oracle.hs'] + [baseline/w['name']/'program' for w in manifest['workloads']]
  for name,expected in previous['fingerprints'].items():
   if sha(name)!=expected: raise ValueError('baseline provenance changed: '+name)
  report['fingerprints']={str(x):sha(x) for x in dependencies}; report['manifest_pins']=manifest['pinned_sha256']
  for path,expected in report['manifest_pins'].items():
   if sha(ROOT/path)!=expected: raise ValueError('manifest pin mismatch '+path)
  fasta=output/'fasta-generator'; run([clang,'-O3',ROOT/'benchmarks/fasta/c/upstream.c','-lm','-o',fasta])
  for work in manifest['workloads']:
   name=work['name']; d=output/name; d.mkdir(); source=(ROOT/work['sources']['mlf']).resolve(); csource=(ROOT/work['sources']['c']).resolve(); old=baseline/name/'program'
   if sha(old)!=baseline_by_name[name]['binary_sha256']: raise ValueError('baseline binary changed '+name)
   n=work['default_input']; inp=d/'input'; fasta_kind=work.get('input_kind')=='fasta'
   if fasta_kind: run([fasta,str(n)],stdout=inp)
   else: inp.write_text(str(n)+'\n')
   cflags=list(work['flags']['c']); libs=[]
   for package in work.get('pkg_config',{}).get('c',[]):
    actual=subprocess.check_output(['pkg-config','--modversion',package],text=True).strip()
    if actual!=work['pkg_config_versions'][package]: raise ValueError('package version mismatch '+package)
    libs+=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',package],text=True))
   if 'c' in work.get('gmp_languages',[]): libs+=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gmp'],text=True))
   def carg(dest): return [clang,*cflags,csource,*libs,'-lm','-o',dest]
   run(carg(d/'reference-c'))
   def args(binary): return [binary] if fasta_kind else [binary,str(n)]
   run(args(d/'reference-c'),stdin=inp,stdout=d/'reference-output'); run([old],stdin=inp,stdout=d/'baseline-output'); compare(name,d/'baseline-output',d/'reference-output')
   wrow={'benchmark':name,'default_input':n,'input_sha256':sha(inp),'samples':[],'correctness':[]}; report['workloads'].append(wrow)
   for i in range(6):
    sd=d/f'sample-{i}'; sd.mkdir(); rec={'index':i,'warmup':i==0}
    def candidate_compile():
     rec['candidate_compile']=run([compiler,source,'-o',sd/'program','--build-dir',sd/'build'],stdout=sd/'compile.stdout')
     receipt=json.loads((sd/'build/receipt.json').read_text()); cmds=receipt['commands']; count=receipt.get('native_export_count'); inline=receipt.get('builtin_inline_count')
     if receipt.get('format')!='MLF-NATIVE-PROGRAM-BUILD-2' or receipt.get('complete') is not True or receipt.get('fresh_user_compilation') is not True or receipt.get('llvm_jobs')!=1 or receipt.get('stdlib_path')!='installed' or not isinstance(count,int) or count<0 or receipt.get('fixed_library_reused')!=(count>0) or receipt.get('fallback_reason')!='' or type(inline) is not int or inline<0 or receipt.get('fixed_runtime_reused') is not True: raise ValueError('invalid installed-path receipt '+name)
     if [x['phase'] for x in cmds]!=['llvm','link'] or any(x['exit_code']!=0 for x in cmds): raise ValueError('invalid stages '+name)
     llvm=cmds[0]['command']
     if Path(llvm[0]).resolve()!=clang or llvm[1:4]!=['-O2','-Wno-override-module','-c']: raise ValueError('invalid clang invocation '+name)
     if sha(sd/'program')!=receipt['output_sha256'] or sha(sd/'build/program.ll')!=receipt['llvm_sha256'] or sha(sd/'build/program.o')!=receipt['user_object_sha256']: raise ValueError('output receipt mismatch '+name)
     rec['receipt']=receipt
    def c_compile(): rec['c_compile']=run(carg(sd/'c'))
    for f in ([candidate_compile,c_compile] if i%2 else [c_compile,candidate_compile]): f()
    if i==0:
     for size in work['check_inputs']:
      inputpath=check/name/'checks/mlf'/str(size)/'stdin'; result=sd/f'check-{size}'; run([sd/'program'],stdin=inputpath,stdout=result)
      run([validate,name,str(size),result]); wrow['correctness'].append({'size':size,'input_sha256':sha(inputpath),'output_sha256':sha(result)})
     fixture=ROOT/work['fixture']; run([validate,name,str(work['fixture_input']),fixture])
    lanes=[('candidate',sd/'program'),('c',sd/'c'),('baseline',old)]
    if i%2==0: lanes.reverse()
    for label,binary in lanes:
     command=args(binary) if label=='c' else [binary]
     run(command,stdin=inp,stdout=sd/f'{label}-warm'); compare(name,sd/f'{label}-warm',d/'reference-output')
     rec[label+'_runtime']=run(command,stdin=inp,stdout=sd/f'{label}-output'); compare(name,sd/f'{label}-output',d/'reference-output')
    if i==0: wrow['warmup']=rec
    else: wrow['samples'].append(rec)
    save()
   cmed=statistics.median(x['c_compile']['wall_seconds'] for x in wrow['samples']); mmed=statistics.median(x['candidate_compile']['wall_seconds'] for x in wrow['samples'])
   wrow['compile_medians']={'candidate':mmed,'c':cmed,'ratio':mmed/cmed}
   wrow['runtime_medians']={key:statistics.median(x[key+'_runtime']['wall_seconds'] for x in wrow['samples']) for key in ['candidate','baseline','c']}
   wrow['stdlib_path']='installed'; wrow['native_export_count']=wrow['samples'][0]['receipt']['native_export_count']; wrow['fixed_library_reused']=wrow['samples'][0]['receipt']['fixed_library_reused']; wrow['builtin_inline_count']=wrow['samples'][0]['receipt']['builtin_inline_count']; wrow['fixed_runtime_reused']=wrow['samples'][0]['receipt']['fixed_runtime_reused']
   save()
  for path,want in report['fingerprints'].items():
   if sha(path)!=want: raise ValueError('input changed '+path)
  for path,want in report['manifest_pins'].items():
   if sha(ROOT/path)!=want: raise ValueError('pinned source changed '+path)
  report['status']='complete'
 except BaseException as e:
  report['status']='failed'; report['error']=repr(e); raise
 finally: save()
if __name__=='__main__': main()
