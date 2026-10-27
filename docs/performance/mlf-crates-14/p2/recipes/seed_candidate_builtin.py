#!/usr/bin/env python3
"""Generate canonical builtin bytes with a qualified prior tool, then require
a fresh official candidate build to independently regenerate/verify them.
This skips only a known-stale preliminary build, never the final fresh gate.
"""
import argparse,hashlib,json,re,subprocess,time,types
from pathlib import Path
W=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--seed',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--install',action='store_true');a=p.parse_args()
S=a.source.resolve();P=a.seed.resolve();O=a.output.resolve()
assert S.parent==W.parent and S.name.startswith('mlf-crates-')
assert P.is_relative_to(W/'candidates') and O.is_relative_to(W/'candidates') and not O.exists()
prior=json.loads((P/'receipt.json').read_text());seed_source=Path(prior['build_driver']['path']).resolve().parents[2]
assert S!=seed_source,'Do not mutate the retained qualified seed source'
direct=seed_source/'tools/shared/test_direct.py';m=types.ModuleType('seed_authentication');m.__file__=str(direct);exec(compile(direct.read_bytes(),str(direct),'exec'),m.__dict__)
m.authenticate_build(P/'receipt.json',P/'bin',root=seed_source)
identity_path=S/'tools/shared/builtin_prelude_identity.py';i=types.ModuleType('candidate_identity');i.__file__=str(identity_path);exec(compile(identity_path.read_bytes(),str(identity_path),'exec'),i.__dict__)
identity,closure=i.source_identity(S)
before_files={str(f.relative_to(S)):sha(f) for root in ['libraries','bootstrap','host','runtime','package'] for f in (S/root).rglob('*') if f.is_file() and '__pycache__' not in f.parts}
O.mkdir(parents=True);target=S/'bootstrap/MLF/BuiltinPreludeData.hs';old=target.read_bytes();(O/'BuiltinPreludeData.before.hs').write_bytes(old)
record={'complete':False,'source':str(S),'qualified_seed':str(P),'qualified_seed_source':str(seed_source),'qualified_seed_receipt_sha256':sha(P/'receipt.json'),'source_identity':identity,'source_closure':closure,'source_files_before':before_files,'recipe_sha256':sha(__file__),'policy':'Seed output is canonical-generation input only; candidate is not qualified until its own fresh generator reproduces these exact bytes under official build.py.'}
def save():(O/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
command=[str(P/'bin/builtin-prelude'),identity];record['command']=command;save()
with (O/'BuiltinPreludeData.hs').open('wb') as out,(O/'stderr').open('wb') as err:
 t=time.monotonic();r=subprocess.run(command,cwd=S,stdin=subprocess.DEVNULL,stdout=out,stderr=err);record.update(exit_code=r.returncode,wall_seconds=time.monotonic()-t)
save();assert r.returncode==0 and not (O/'stderr').read_bytes()
m.authenticate_build(P/'receipt.json',P/'bin',root=seed_source)
assert sha(P/'receipt.json')==record['qualified_seed_receipt_sha256']
assert all(sha(S/f)==h for f,h in before_files.items()),'Source changed during canonical generation'
assert i.source_identity(S)[0]==identity
new=(O/'BuiltinPreludeData.hs').read_bytes();tokens=re.findall(rb'builtin-source-v1:[0-9a-f]{64}',old);assert len(tokens)==1
assert old.replace(tokens[0],identity.encode())==new,'Unexpected non-identity canonical delta; retain evidence and review'
record.update(complete=True,only_source_identity_differs=True,generated_sha256=sha(O/'BuiltinPreludeData.hs'),installed=False)
if a.install:target.write_bytes(new);assert sha(target)==record['generated_sha256'];record['installed']=True
save();print(json.dumps({k:v for k,v in record.items() if k not in {'source_closure','source_files_before'}},indent=2))
