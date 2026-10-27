#!/usr/bin/env python3
"""Serial runtime controls for diagnostic timing and structural traversals."""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
W=Path(__file__).resolve().parents[1];D=W/'diagnostic';P=W/'compilers/forced-phases'
out=W/'diagnostic-tests';assert not out.exists();out.mkdir()
j=json.loads((P/'receipt.json').read_text());assert j['complete']
def sha(p):return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
assert all(sha(Path(j['cwd'])/rel)==digest for rel,digest in j['source_files'].items())
receipt=dict(complete=False,compiler_receipt_sha256=sha(P/'receipt.json'),commands=[],source_pins={str(D/f):sha(D/f) for f in ['PhaseSelfTest.hs','ForceSelfTest.hs']})
def save():(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
def command(name,argv,cwd=out):
 with (out/(name+'.stdout')).open('wb') as stdout,(out/(name+'.stderr')).open('wb') as stderr:
  t=time.monotonic();r=subprocess.run(list(map(str,argv)),cwd=cwd,env={**os.environ,'GHCRTS':'-T -s','GHC_ENVIRONMENT':'-'},stdout=stdout,stderr=stderr)
 row=dict(name=name,argv=list(map(str,argv)),exit_code=r.returncode,wall_seconds=time.monotonic()-t);receipt['commands'].append(row);save()
 assert r.returncode==0,(out/(name+'.stderr')).read_text()[-3500:]
 return row
for name in ['PhaseSelfTest','ForceSelfTest']:
 obj=out/(name+'-objects');shutil.copytree(P/'objects',obj)
 for ext in ['.hi','.o']:(obj/('Main'+ext)).unlink(missing_ok=True)
 argv=[x.replace(str(P/'objects'),str(obj)).replace(str(P/'emlf'),str(out/name)).replace(str(D/'phase-source/host/ghc/app/emlf/Main.hs'),str(D/(name+'.hs'))) for x in j['argv']]
 reset=argv.index('-i');argv[reset+1:reset+1]=['-i'+str(D)]
 command('build-'+name,argv)
 command('run-'+name,[out/name]+([out/'phase-selftest.jsonl'] if name=='PhaseSelfTest' else []))
expected={'PhaseSelfTest':'phase nesting/exception/repeated-traversal/effect-once controls passed\n','ForceSelfTest':'force helper constructor/negative/lazy-fallback controls passed\n'}
for name,text in expected.items():assert (out/('run-'+name+'.stdout')).read_text()==text
for name in ['phase-selftest.jsonl','phase-selftest.jsonl.no-repeat']:
 command('analyze-'+name,['python3',D/'analyze_phase.py',out/name])
for path,h in receipt['source_pins'].items():assert sha(path)==h
receipt.update(complete=True,immutable_diagnostic_source_verified=True)
save();print(json.dumps({k:v for k,v in receipt.items() if k!='commands'},indent=2))
