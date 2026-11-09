#!/usr/bin/env python3
"""Pinned ordinary-GHC counterpart for exact PatternDo source bodies; test-only driver."""
import argparse,json,pathlib,re,subprocess,hashlib,time,shutil
p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--ghc',required=True);p.add_argument('--cc',default='cc');p.add_argument('--opt',choices=['0','2'],default='0');a=p.parse_args()
if a.out.exists() and any(a.out.iterdir()):p.error('output directory must be empty (preserve prior evidence)')
a.out.mkdir(parents=True,exist_ok=True)
fixture=a.root/'tools/shared/fixtures/item4/PatternDo.hs';text=fixture.read_text();dec=json.JSONDecoder();cases=[]
input_paths=[fixture,pathlib.Path(__file__).resolve(),*sorted((a.root/'host/ghc').rglob('*.hs')),a.root/'host/ghc/cbits/host.c',a.root/'runtime/mlf_process_supervisor.c',a.root/'runtime/mlf_process_supervisor.h']
def hashes():return {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in input_paths}
inputs=hashes()
version=subprocess.check_output([a.ghc,'--numeric-version'],text=True).strip()
if version!='9.14.1':raise RuntimeError('requires pinned GHC9.14.1, got '+version)
for line in text.splitlines():
 m=re.match(r'  (checkFamily|rejectFamily|rejectConstraint|rejectInference|check|fails) ',line)
 if not m:continue
 rest=line[m.end():];name,n=dec.raw_decode(rest);rest=rest[n:].lstrip();body,n=dec.raw_decode(rest);rest=rest[n:].strip()
 cases.append((m[1],name,body,rest))
header=dec.raw_decode(next(line.split('B.literal $ ',1)[1] for line in text.splitlines() if line.startswith('source body =')))[0]
family=header.replace('module Example where','module Family (Choice(Only), makeOther) where')+'data Choice = Only | Other\nmakeOther = Other\n'
receipt={'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'cases':[],'scope':'ordinary GHC exact source bodies with separate -main-is Driver; no production translation','inputs':inputs,'optimization':'O'+a.opt,'ghc_version':version,'ghc_sha256':hashlib.sha256(pathlib.Path(a.ghc).resolve().read_bytes()).hexdigest()}
# Compile C explicitly to isolated objects: GHC -odir does not relocate .c side objects.
cc=pathlib.Path(shutil.which(a.cc) or a.cc).resolve(strict=True)
receipt['cc']={'path':str(cc),'sha256':hashlib.sha256(cc.read_bytes()).hexdigest()}
c_objects=[];receipt['c_objects']=[]
for label,src in [('host',a.root/'host/ghc/cbits/host.c'),('supervisor',a.root/'runtime/mlf_process_supervisor.c')]:
 obj=a.out/(label+'.o');cmd=[str(cc),'-O2','-std=c11','-I'+str(a.root/'runtime'),'-c',str(src),'-o',str(obj)]
 built=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
 (a.out/(label+'-compile.log')).write_text(built.stdout)
 if built.returncode:raise RuntimeError(label+' C compile failed: '+built.stdout)
 c_objects.append(str(obj));receipt['c_objects'].append({'command':cmd,'path':str(obj),'sha256':hashlib.sha256(obj.read_bytes()).hexdigest()})
for i,(kind,name,body,expect) in enumerate(cases):
 d=a.out/str(i);d.mkdir(exist_ok=True);(d/'Example.hs').write_text(header+('import qualified Family as F\n' if kind.endswith('Family') else '')+body+'\n');(d/'Family.hs').write_text(family)
 extension=name.startswith('MLF ')
 negative=extension or kind in {'rejectConstraint','rejectInference'} or (kind=='rejectFamily' and 'T.Resolution' in expect)
 if negative:
  cmd=[a.ghc,'-w','-j1','-O'+a.opt,'-fforce-recomp','-I'+str(a.root/'runtime'),'-fno-code','-i'+str(a.root/'host/ghc'),'-i'+str(d),'-odir',str(d),'-hidir',str(d),str(d/'Example.hs')]
 else:
  if kind.startswith('check'):
   observation=f'Right value | value == {expect} -> putStrLn "PASS"; Right value -> error ("wrong value " ++ show value); Left err -> error (displayException err)'
  elif kind=='rejectFamily':
   observation='Left err | Just (_ :: PatternMatchFail) <- fromException err -> putStrLn "PASS: GHC runtime rejection (MLF rejects statically)"; Left err -> error ("wrong exception " ++ displayException err); Right _ -> error "unexpected success"'
  else:
   msg=dec.raw_decode(expect)[0]
   if msg=='Irrefutable pattern failed':
    observation='Left err | Just (_ :: PatternMatchFail) <- fromException err -> putStrLn "PASS: delayed pattern failure"; Left err -> error ("wrong exception " ++ displayException err); Right _ -> error "unexpected success"'
   else:
    observation='Left err | '+json.dumps(msg)+' `isInfixOf` displayException err -> putStrLn "PASS: demanded source error"; Left err -> error ("wrong exception " ++ displayException err); Right _ -> error "unexpected success"'
  wrapper='{-# LANGUAGE ScopedTypeVariables #-}\nmodule Driver where\nimport Prelude\nimport Control.Exception\nimport Data.List (isInfixOf)\nimport qualified Example\nmain :: IO ()\nmain = do { result <- try (evaluate Example.main) :: IO (Either SomeException Integer); case result of { '+observation+' } }\n'
  (d/'Driver.hs').write_text(wrapper);cmd=[a.ghc,'-w','-j1','-O'+a.opt,'-fforce-recomp','-I'+str(a.root/'runtime'),'-i'+str(a.root/'host/ghc'),'-i'+str(d),'-odir',str(d),'-hidir',str(d),'-main-is','Driver',str(d/'Driver.hs'),*c_objects,'-o',str(d/'probe')]
 print('BEGIN',i,name,flush=True);r=subprocess.run(cmd+['+RTS','-M700m','-RTS'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60);(d/'compile.log').write_text(r.stdout)
 if negative:
  if extension:category='Num Bool'
  elif kind=='rejectInference':
   category='GHC-27346' if 'arity' in name else 'GHC-83865'
  else:
   category='IsString Key' if 'requires IsString' in name else ('Eq Key' if 'requires Eq' in name else 'MonadFail')
  ok=r.returncode!=0 and category in r.stdout;result=('MLF extension positive / GHC compile rejection / ' if extension else 'GHC compile rejection / ')+category
 else:
  if r.returncode:raise RuntimeError(name+' compile failed\n'+r.stdout)
  run=subprocess.run([str(d/'probe')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30);(d/'run.log').write_text(run.stdout);ok=run.returncode==0;result=run.stdout.strip()
 receipt['cases'].append({'name':name,'kind':kind,'ok':ok,'observation':result,'body_sha256':hashlib.sha256(body.encode()).hexdigest()});(a.out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 if not ok:raise RuntimeError(name+' failed; see '+str(d))
 print('PASS',i,name,flush=True)
if hashes()!=inputs:raise RuntimeError('input closure changed during reference run')
receipt['status']='passed';receipt['unchanged_inputs']=True
(a.out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('PASS all',len(cases),flush=True)
