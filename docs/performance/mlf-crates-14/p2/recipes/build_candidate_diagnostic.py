#!/usr/bin/env python3
"""Authenticated candidate diagnostics, separate from ordinary qualification."""
import argparse, hashlib, json, os, shutil, subprocess, types, time
from pathlib import Path
W=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
p=argparse.ArgumentParser()
p.add_argument('candidate');p.add_argument('label')
p.add_argument('--late-profile',action='store_true')
a=p.parse_args()
P=W/'candidates'/a.candidate/'producer'
assert P.is_relative_to(W/'candidates')
r=json.loads((P/'receipt.json').read_text())
S=Path(r['build_driver']['path']).resolve().parents[2]
assert S.parent==W.parent and S.name.startswith('mlf-crates-')
direct=S/'tools/shared/test_direct.py'
m=types.ModuleType('candidate_authentication');m.__file__=str(direct)
exec(compile(direct.read_bytes(),str(direct),'exec'),m.__dict__)
m.authenticate_build(P/'receipt.json',P/'bin',root=S)
out=W/'compilers'/a.label;assert not out.exists();out.mkdir(parents=True)
argv=next(c['argv'] for c in r['commands'] if any('app/emlf/Main.hs' in x for x in c['argv']))
argv=[x.replace(str(P/'objects'),str(out/'objects')).replace(str(P/'bin/emlf'),str(out/'emlf')) for x in argv]
argv=['-rtsopts' if x=='-rtsopts=ignoreAll' else x for x in argv]
if a.late_profile:
    argv[1:1]=['-prof','-fprof-late','-fprof-cafs','-fno-prof-count-entries']
else:
    shutil.copytree(P/'objects',out/'objects')
    for ext in ['.hi','.o']:(out/'objects'/('Main'+ext)).unlink(missing_ok=True)
j=dict(complete=False,candidate=a.candidate,source=str(S),producer=str(P),
       producer_receipt_sha256=sha(P/'receipt.json'),recipe_sha256=sha(__file__),
       authentication_before=True,argv=argv,cwd=str(S),
       method='late-cost-centre' if a.late_profile else 'ordinary-objects-rts-relink',
       purpose='Diagnostic only; separate overhead and not an ordinary performance sample')
(out/'recipe.py').write_bytes(Path(__file__).read_bytes())
(out/'receipt.json').write_text(json.dumps(j,indent=2)+'\n')
with (out/'build.log').open('wb') as log:
    t=time.monotonic();result=subprocess.run(argv,cwd=S,env={**os.environ,'GHC_ENVIRONMENT':'-','GHCRTS':''},stdout=log,stderr=subprocess.STDOUT)
    j.update(wall_seconds=time.monotonic()-t,exit_code=result.returncode)
assert result.returncode==0
m.authenticate_build(P/'receipt.json',P/'bin',root=S)
assert sha(P/'receipt.json')==j['producer_receipt_sha256'] and sha(__file__)==j['recipe_sha256']
if not a.late_profile:
    pins={str(f.relative_to(P/'objects')):sha(f) for f in (P/'objects').rglob('*') if f.is_file() and f.suffix in ['.hi','.o'] and f.name not in ['Main.hi','Main.o']}
    assert all(sha(out/'objects'/rel)==h for rel,h in pins.items())
    j.update(unchanged_non_main_object_files=pins,non_main_objects_byte_identical=True)
j.update(complete=True,authentication_after=True,binary_sha256=sha(out/'emlf'))
(out/'receipt.json').write_text(json.dumps(j,indent=2)+'\n')
print(json.dumps({k:v for k,v in j.items() if k not in ['argv','unchanged_non_main_object_files']},indent=2))
