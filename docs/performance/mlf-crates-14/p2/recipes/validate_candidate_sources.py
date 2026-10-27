#!/usr/bin/env python3
"""Narrow real-MLF check of optimized 14-module crate, NOT the timed workload.

Authenticated compiled dependencies are reused. The optimized source crate is
inferred afresh; no native compiler executable or 74-module bootstrap is built.
"""
import argparse,hashlib,json,os,subprocess,time,types
from pathlib import Path
W=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
pack=lambda xs:''.join(str(len(x))+':'+x for x in xs)
p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
P=W/'candidates'/a.candidate/'producer';r=json.loads((P/'receipt.json').read_text())
S=Path(r['build_driver']['path']).resolve().parents[2]
assert S.parent==W.parent and S.name.startswith('mlf-crates-')
direct=S/'tools/shared/test_direct.py';m=types.ModuleType('source_qualification_authentication');m.__file__=str(direct)
exec(compile(direct.read_bytes(),str(direct),'exec'),m.__dict__)
m.authenticate_build(P/'receipt.json',P/'bin',root=S)
frozen=json.loads((W/'frozen.json').read_text())
manifest=S/'libraries/mlf-crates/mlf-package.json';mods=json.loads(manifest.read_text())['library']['modules'];assert len(mods)==14 and set(mods)==set(frozen['modules'])
sourcepins={str(S/'libraries/mlf-crates'/rel):sha(S/'libraries/mlf-crates'/rel) for rel in mods.values()}
pins={**frozen['artifacts'],**sourcepins,str(P/'receipt.json'):sha(P/'receipt.json'),str(P/'bin/emlf'):sha(P/'bin/emlf'),str(manifest):sha(manifest),str(Path(__file__)):sha(__file__)}
def verify():
 for path,h in pins.items():assert sha(path)==h,path
verify();out=a.output.resolve();assert not out.exists();out.mkdir(parents=True)
cache=out/'queries';assert not cache.exists()
spec=pack(['MLF-CRATE-1','mlf-crates/0.3.0/library','','false',pack([pack([name,str(S/'libraries/mlf-crates'/rel)]) for name,rel in mods.items()]),pack([d['path'] for d in frozen['dependencies']]),str(cache),frozen['prelude']])
(out/'crate.spec').write_text(spec);(out/'recipe.py').write_bytes(Path(__file__).read_bytes())
j=dict(complete=False,candidate=a.candidate,scope='Actual optimized 14-module mlf-crates source accepted by MLF, not frozen performance input; no native bootstrap',
       source_root=str(S),source_pins=sourcepins,inputs=pins,modules=mods,commands=[],target_cache_initially_absent=True,
       producer_authenticated_before=True,performance_sample=False,full_compiler_bootstrap=False)
def save():(out/'receipt.json').write_text(json.dumps(j,indent=2)+'\n')
save()
env={**os.environ,'GHC_ENVIRONMENT':'-','GHCRTS':'','LC_ALL':'C.UTF-8','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
try:
 for label,argv in [('compile',[str(P/'bin/emlf'),'--compile-crate',str(out/'crate.spec'),'-o',str(out/'unit')]),('metadata-reload',[str(P/'bin/emlf'),'--show-crate',str(out/'unit.mlfci')])]:
  cmd=dict(label=label,argv=argv,cwd=str(out));j['commands'].append(cmd);save()
  with (out/(label+'.stdout')).open('wb') as stdout,(out/(label+'.stderr')).open('wb') as stderr:
   start=time.monotonic();result=subprocess.run(argv,cwd=out,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
  cmd.update(exit_code=result.returncode,wall_seconds=time.monotonic()-start);save();assert result.returncode==0,(out/(label+'.stderr')).read_text()[-4000:]
 report=json.loads((out/'unit.queries').read_text());assert report['inferred_groups']>0 and report['reused_groups']==0
 assert len(report['groups'])==report['inferred_groups'] and all(not g['cached'] for g in report['groups'])
 verify();m.authenticate_build(P/'receipt.json',P/'bin',root=S)
 j.update(complete=True,producer_authenticated_after=True,immutable_inputs_verified_after=True,query_report=report,
          artifacts={ext:sha(out/('unit'+ext)) for ext in ['.mlfci','.mlfco','.queries']})
except BaseException as e:
 j['error']=dict(type=type(e).__name__,message=str(e));raise
finally:save()
print(json.dumps({k:v for k,v in j.items() if k not in ['inputs','query_report','source_pins','modules','commands']},indent=2))
