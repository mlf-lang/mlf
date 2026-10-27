#!/usr/bin/env python3
"""Build GHC-hosted diagnostic compiler; never starts native/MLF bootstrap."""
import argparse, hashlib, json, os, shutil, subprocess, time
from pathlib import Path
W=Path(__file__).resolve().parents[1]
B=W.parent/'pr25-latest-benchmark-work-20261026'
P=B/'setup/fixed-producer-2/producer'
OLD=W.parent/'pr25-latest-benchmark-fixed-20261026'
SOURCE=W.parent/'mlf-crates-profile-source-20261026'
def sha(p):return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
p=argparse.ArgumentParser();p.add_argument('label');p.add_argument('--profile',action='store_true');p.add_argument('--late-profile',action='store_true');p.add_argument('--fresh',action='store_true');p.add_argument('--source',type=Path,default=SOURCE);p.add_argument('--diagnostic-path',type=Path);a=p.parse_args()
out=W/'compilers'/a.label;assert not out.exists();out.mkdir(parents=True)
receipt=json.loads((P/'receipt.json').read_text())
argv=next(c['argv'] for c in receipt['commands'] if any('app/emlf/Main.hs' in x for x in c['argv']))
argv=[x.replace(str(OLD),str(a.source)).replace(str(P/'objects'),str(out/'objects')).replace(str(P/'bin/emlf'),str(out/'emlf')) for x in argv]
argv=[('-rtsopts' if x=='-rtsopts=ignoreAll' else x) for x in argv]
if a.diagnostic_path:
    reset=argv.index('-i')
    argv[reset+1:reset+1]=['-i'+str(a.diagnostic_path)]
(out/'core').mkdir()
argv[1:1]=['-dumpdir',str(out/'core')+'/']
if a.profile or a.late_profile:argv[1:1]=['-prof','-fprof-late' if a.late_profile else '-fprof-auto','-fprof-cafs','-fno-prof-count-entries']
elif not a.fresh:
    # Reuse exact compiler implementation .hi/.o; only wrapper/link may rebuild.
    shutil.copytree(P/'objects',out/'objects')
    for ext in ['.hi','.o']:(out/'objects'/('Main'+ext)).unlink(missing_ok=True)
env={**os.environ,'GHC_ENVIRONMENT':'-','GHCRTS':''}
j=dict(complete=False,argv=argv,cwd=str(a.source),profile=a.profile or a.late_profile,
       profile_method='late' if a.late_profile else ('early-auto' if a.profile else 'none'),
       purpose='Diagnostic GHC-hosted tool only; not a native/compiler-bootstrap benchmark',
       source_files={str(f.relative_to(a.source)):sha(f) for root in ['libraries','bootstrap','host','Diagnostic'] for f in (a.source/root).rglob('*.hs')},recipe_sha256=sha(__file__))
shutil.copy2(__file__,out/'recipe.py')
(out/'receipt.json').write_text(json.dumps(j,indent=2)+'\n')
with (out/'build.log').open('wb') as log:
    t=time.monotonic();r=subprocess.run(argv,cwd=a.source,env=env,stdout=log,stderr=subprocess.STDOUT);j['wall_seconds']=time.monotonic()-t
j.update(exit_code=r.returncode,complete=r.returncode==0)
unchanged=all(sha(a.source/rel)==digest for rel,digest in j['source_files'].items())
j['source_files_unchanged_after']=unchanged
if not unchanged:j.update(complete=False,error='Diagnostic compiler source changed during build')
if j['complete']:j['binary_sha256']=sha(out/'emlf')
(out/'receipt.json').write_text(json.dumps(j,indent=2)+'\n')
print(json.dumps(j,indent=2));raise SystemExit(0 if j['complete'] else (r.returncode or 1))
