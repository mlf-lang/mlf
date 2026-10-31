#!/usr/bin/env python3
"""Fresh flag-absent comparison compiler from the pinned PR25 git object only."""
from pathlib import Path
import argparse,hashlib,io,json,os,re,shutil,subprocess,tarfile
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PIN='7bf7ac6db5e3db2daff2e0a1c249e68ae0db2d0c'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ghc',type=Path,required=True);p.add_argument('--directory',type=Path,required=True);a=p.parse_args()
 ghc=a.ghc.resolve(strict=True)
 if subprocess.check_output([str(ghc),'--numeric-version'],text=True).strip()!='9.14.1':raise ValueError('existingGHC9.14.1 required')
 base=a.directory.resolve();base.mkdir(parents=True,exist_ok=False);source=base/'source';source.mkdir();build=base/'build';build.mkdir();(build/'objects').mkdir()
 archive=subprocess.check_output(['git','-C',str(ROOT),'archive',PIN]);tarfile.open(fileobj=io.BytesIO(archive)).extractall(source,filter='data')
 m=json.loads((source/'shared-sources.json').read_text());paths={x['path'] for x in m['modules']}|{'host/ghc/MLF/Primitive.hs','host/ghc/MLF/Host/Base.hs','host/ghc/MLF/Host/Async.hs','host/ghc/MLF/Host/IO.hs','host/ghc/app/emlf/Main.hs','host/ghc/cbits/host.c','runtime/mlf_process_supervisor.c','shared-sources.json','mlf-shared.cabal','mlf-package.json','mlf.lock'}|{str(p.relative_to(source)) for p in (source/'runtime').glob('*.h')}
 inputs={p:sha(source/p) for p in sorted(paths)};report={'status':'building','baseline':PIN,'git_archive_sha256':hashlib.sha256(archive).hexdigest(),'source_root':str(source),'inputs':inputs,'commands':[]}
 def save():(base/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 def run(cmd,label):
  cmd=list(map(str,cmd))
  with (build/(label+'.log')).open('w') as log:r=subprocess.run(cmd,cwd=source,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,GHC_ENVIRONMENT='-',GHCRTS='',LC_ALL='C.UTF-8'),timeout=600)
  report['commands'].append({'argv':cmd,'exit_code':r.returncode,'log_sha256':sha(build/(label+'.log'))});save();r.check_returncode()
 save();objs=[]
 try:
  for label,path in [('host','host/ghc/cbits/host.c'),('supervisor','runtime/mlf_process_supervisor.c')]:
   out=build/(label+'.o');run(['cc','-O0','-std=c11','-I'+str(source/'runtime'),'-c',source/path,'-o',out],label);objs.append(out)
  flags=['-XHaskell2010','-O0','-fpedantic-bottoms','-fno-state-hack','-Werror=incomplete-patterns','-Werror=incomplete-uni-patterns','-Wno-star-is-type','-Wno-overlapping-patterns','-Wno-deprecations','-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db','-hide-all-packages','-i']+['-i'+str(source/r) for r in m['source_roots']]+['-odir',build/'objects','-hidir',build/'objects','-rtsopts=ignoreAll']
  for package in ['base','array','bytestring','text','containers','directory']:flags+=['-package',package]
  binary=build/'emlf';run([ghc,'--make','-j1','-fforce-recomp',*flags,source/'host/ghc/app/emlf/Main.hs',*objs,'-o',binary],'compile')
  report.update(status='built',binary=str(binary),binary_sha256=sha(binary),resolved_modules=re.findall(r'Compiling\s+([\w.]+)\s+\(\s*([^,\n]+),',(build/'compile.log').read_text()))
 finally:
  report['immutable_inputs_verified_after']=all(sha(source/p)==h for p,h in inputs.items())
  if not report['immutable_inputs_verified_after']:report['status']='invalidated'
  save()
 print(base/'receipt.json')
if __name__=='__main__':main()
