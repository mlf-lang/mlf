#!/usr/bin/env python3
"""Authenticate a qualified candidate around the unchanged frozen benchmark."""
import argparse,hashlib,json,subprocess,sys,time,types
from pathlib import Path
W=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('label');a=p.parse_args()
P=W/'candidates'/a.candidate/'producer';assert P.is_relative_to(W/'candidates')
producer=json.loads((P/'receipt.json').read_text())
S=Path(producer['build_driver']['path']).resolve().parents[2]
assert S.parent==W.parent and S.name.startswith('mlf-crates-')
direct=S/'tools/shared/test_direct.py';m=types.ModuleType('candidate_authentication');m.__file__=str(direct);exec(compile(direct.read_bytes(),str(direct),'exec'),m.__dict__)
source=m.authenticate_build(P/'receipt.json',P/'bin',root=S);assert source['optimization']=='2'
receipt_sha=sha(P/'receipt.json');script_sha=sha(__file__);benchmark_sha=sha(W/'recipes/benchmark.py')
argv=[sys.executable,str(W/'recipes/benchmark.py'),'mlf',a.label,'--compiler',str(P/'bin/emlf')]
r=subprocess.run(argv)
out=W/'runs'/a.label
auth={'complete':False,'candidate':a.candidate,'qualified_producer_receipt_sha256':receipt_sha,'source':str(S),'producer':str(P),'benchmark_recipe_sha256':benchmark_sha,'wrapper_sha256':script_sha,'benchmark_exit_code':r.returncode,'authentication_before':True}
if out.exists():
 (out/'candidate-authentication.json').write_text(json.dumps(auth,indent=2)+'\n')
 (out/'candidate-wrapper.py').write_bytes(Path(__file__).read_bytes())
assert r.returncode==0
m.authenticate_build(P/'receipt.json',P/'bin',root=S)
assert sha(P/'receipt.json')==receipt_sha and sha(__file__)==script_sha and sha(W/'recipes/benchmark.py')==benchmark_sha
auth.update(complete=True,authentication_after=True)
(out/'candidate-authentication.json').write_text(json.dumps(auth,indent=2)+'\n')
print(json.dumps(auth,indent=2))
