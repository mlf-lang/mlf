#!/usr/bin/env python3
"""Package reviewed engineering evidence; no caches, toolchains, or private notes."""
import hashlib,json,zipfile
from pathlib import Path
W=Path(__file__).resolve().parents[1]
files={}
def add(p,name=None):
    p=Path(p)
    if p.is_file():
        name=name or str(p.relative_to(W))
        assert name not in files or files[name]==p
        files[name]=p
def tree(root,suffixes=None):
    for p in sorted(root.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and (suffixes is None or p.suffix in suffixes):add(p)
add(W/'frozen.json')
tree(W/'frozen-target')
tree(W/'recipes',{'.py'})
for p in (W/'evidence').glob('*'):
    if p.suffix in {'.json','.py'}:add(p)
for p in (W/'deliverables').glob('*'):
    if p.suffix in {'.json','.patch'}:add(p)
for p in (W/'reports').glob('*'):
    if p.suffix in {'.docx','.pdf','.txt','.json','.md','.py'}:add(p)
for p in (W/'diagnostic').glob('*'):
    if p.suffix in {'.py','.json','.hs','.txt'}:add(p)
tree(W/'diagnostic/Diagnostic',{'.hs'})
add(W/'diagnostic/phase-source/Diagnostic/Phase.dump-simpl')
for p in (W/'diagnostic-tests').glob('*'):
    if p.is_file() and p.suffix not in {'.o','.hi'} and p.name not in {'PhaseSelfTest','ForceSelfTest'}:add(p)
for name in ['baseline-mlf-1','baseline-mlf-2','baseline-mlf-3',
             'baseline-make-ghc-1','baseline-make-ghc-2','baseline-make-ghc-3',
             'baseline-plain-ghc-1','baseline-plain-ghc-2','baseline-plain-ghc-3',
             'profile-ghc-phases-1','profile-late-1','profile-forced-1','profile-baseline-rts-1']:
    for f in ['receipt.json','recipe.py','stdout','stderr','crate.spec','emlf.prof','phases.jsonl','ghc-9.14.1.eventlog']:add(W/'runs'/name/f)
    for f in ['bounded-receipt.json','build.log']:add(W/'guards'/name/f)
for name in ['late-profile','forced-phases','baseline-rts']:
    for f in ['receipt.json','recipe.py','build.log']:add(W/'compilers'/name/f)
for f in ['receipt.json','stdout','stderr']:add(W/'plain-o2-setup'/f)
tree(W/'profile-late-analysis',{'.json','.gz','.py','.txt'})
assert any(n.endswith('.docx') for n in files),'Reviewed editable report is required'
assert json.loads((W/'reports/render-validation.json').read_text())['complete'],'Render/visual review required'
sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
manifest={'format':'mlf-crates-preoptimization-evidence-v1','files':{n:{'sha256':sha(p),'bytes':p.stat().st_size} for n,p in sorted(files.items())},
 'scope':'Completed pre-optimization14module baseline and profiles. No production optimization patch in this milestone.',
 'reproduction':'Checkout pinned repository commit and apply approvedlocalfixes. Toolchain and dependency artifacts are hash-pinned but excluded for size; rebuild or retain authenticated originalinputs. Scripts retain actual experiment paths; relocation requires explicit path reconfiguration and a new manifest, never silent substitution.',
 'exclusions':['Compiled toolchains/binaries, querycache bodies, dependency objects, failed diagnostic builds, private notes and transfercredentials.']}
out=W/'deliverables/mlf-crates-profile-20261026.zip'
assert not out.exists(),'Refusing to silently overwrite an already saved milestone'
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    z.writestr('MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
    for n,p in sorted(files.items()):z.write(p,n)
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
    for n,v in manifest['files'].items():assert hashlib.sha256(z.read(n)).hexdigest()==v['sha256']
receipt={'complete':True,'archive':str(out),'bytes':out.stat().st_size,'sha256':sha(out),'files':len(files),'member_hashes_verified':True}
(W/'deliverables/profile-package-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
