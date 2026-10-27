#!/usr/bin/env python3
"""Canonical generator after official build fails solely on source identity.

Never edits an identity token. Installs only complete fresh generator stdout,
after proving the only generated-content delta is its expected source identity.
"""
import argparse,hashlib,json,re,subprocess,time,types
from pathlib import Path
W=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--producer',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--install',action='store_true');a=p.parse_args()
S=a.source.resolve();P=a.producer.resolve();O=a.output.resolve()
assert S==W.parent/'mlf-crates-profile-source-20261026','Only new optimization source may be installed'
assert P.is_relative_to(W/'candidates') and O.is_relative_to(W/'candidates')
assert not O.exists();O.mkdir(parents=True)
j=json.loads((P/'receipt.json').read_text())
assert j['complete'] is False and len(j['inferred_shared_interfaces'])==121
assert all(v['unresolved_literal_constraints'] is False for v in j['inferred_shared_interfaces'].values())
assert all(c['exit_code']==0 for c in j['commands'])
assert (P/'shared-profile.log').read_bytes()==b'PASS shared syntax/name resolution: 121 modules\n'
failed=json.loads((P/'builtin-verification/receipt.json').read_text())
assert failed['complete'] is False and failed['commands'][0]['label']=='check-candidate'
assert (P/'builtin-verification/check-candidate.stderr').read_bytes()==b'prepared Prelude build source identity is stale\n'
pins={}
def collect(x):
 if isinstance(x,dict):
  if isinstance(x.get('path'),str) and isinstance(x.get('sha256'),str):pins[x['path']]=x['sha256']
  for k,v in x.items():
   if k=='files' and isinstance(v,dict):
    for name,digest in v.items():
     if Path(name).is_absolute() and isinstance(digest,str):pins[name]=digest
   collect(v)
 elif isinstance(x,list):
  for v in x:collect(v)
collect(j)
for rel,digest in j.get('object_inputs',{}).items():pins[str(P/rel)]=digest
for f in [P/'receipt.json',S/'tools/shared/builtin_prelude_identity.py',Path(__file__)]:pins[str(f)]=sha(f)
def verify():
 for path,digest in pins.items():assert sha(path)==digest,path
verify()
m=types.ModuleType('candidate_identity');m.__file__=str(S/'tools/shared/builtin_prelude_identity.py');exec(compile(Path(m.__file__).read_bytes(),m.__file__,'exec'),m.__dict__)
identity,closure=m.source_identity(S)
command=[str(P/'bin/builtin-prelude'),identity]
record={'complete':False,'scope':'Canonical regeneration, not qualified producer or benchmark','source':str(S),'producer':str(P),'source_identity':identity,'source_closure':closure,'command':command,'input_pins':pins}
def save():(O/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
save()
with (O/'BuiltinPreludeData.hs').open('wb') as out,(O/'stderr').open('wb') as err:
 t=time.monotonic();r=subprocess.run(command,cwd=S,stdin=subprocess.DEVNULL,stdout=out,stderr=err);record.update(exit_code=r.returncode,wall_seconds=time.monotonic()-t)
save();verify();assert r.returncode==0 and not (O/'stderr').read_bytes()
target=S/'bootstrap/MLF/BuiltinPreludeData.hs';old=target.read_bytes();new=(O/'BuiltinPreludeData.hs').read_bytes()
tokens=re.findall(rb'builtin-source-v1:[0-9a-f]{64}',old);assert len(tokens)==1
assert old.replace(tokens[0],identity.encode())==new,'Canonical generator changed non-identity content; stop for review'
(O/'BuiltinPreludeData.before.hs').write_bytes(old)
record.update(complete=True,input_pins_unchanged=True,only_source_identity_differs=True,before_sha256=sha(target),generated_sha256=sha(O/'BuiltinPreludeData.hs'),installed=False)
if a.install:
 target.write_bytes(new);assert sha(target)==record['generated_sha256'];record['installed']=True
save();print(json.dumps({k:v for k,v in record.items() if k not in {'source_closure','input_pins'}},indent=2))
