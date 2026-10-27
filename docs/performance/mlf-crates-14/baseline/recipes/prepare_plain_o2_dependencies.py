#!/usr/bin/env python3
"""Untimed setup: GHC dependency objects with exactly plain -O2 optimization policy."""
import hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
W=Path(__file__).resolve().parents[1]
j=json.loads((W/'frozen.json').read_text());out=W/'plain-o2-setup';assert not out.exists();out.mkdir()
obj=out/'objects';obj.mkdir()
prior=json.loads((W/'runs/baseline-make-ghc-3/receipt.json').read_text())
argv=[x for x in prior['argv'] if x not in ['-fpedantic-bottoms','-fno-state-hack']]
argv=[x.replace(str(W/'runs/baseline-make-ghc-3/objects'),str(obj)) for x in argv]
env={**os.environ,'GHC_ENVIRONMENT':'-','GHCRTS':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
receipt=dict(complete=False,argv=argv,purpose='Untimed cold preparation of plain-O2 GHC dependency object set; target14 objects discarded from reusable set.')
def save():(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
save()
with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:
 t=time.monotonic();r=subprocess.run(argv,env=env,cwd=out,stdout=stdout,stderr=stderr);receipt.update(exit_code=r.returncode,setup_wall_seconds=time.monotonic()-t)
save();assert r.returncode==0,(out/'stderr').read_text()[-2000:]
compiled=re.findall(r'^\[\s*\d+ of\s*\d+\] Compiling (\S+)',(out/'stdout').read_text()+(out/'stderr').read_text(),re.M)
assert set(j['order']).issubset(compiled) and len(compiled)>14
deps=W/'ghc-plain-o2-dependencies';deps.mkdir();targets={n.replace('.','/') for n in j['order']};files={}
for f in obj.rglob('*'):
 if not f.is_file() or f.suffix not in ['.hi','.o']:continue
 rel=f.relative_to(obj)
 if str(rel.with_suffix('')) in targets:continue
 dst=deps/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dst)
 files[str(rel)]=hashlib.file_digest(dst.open('rb'),'sha256').hexdigest()
receipt.update(complete=True,compiled_modules=compiled,reusable_dependency_files=files,reusable_directory=str(deps))
save();print(json.dumps({k:receipt[k] for k in ['complete','setup_wall_seconds','reusable_directory']},indent=2))
