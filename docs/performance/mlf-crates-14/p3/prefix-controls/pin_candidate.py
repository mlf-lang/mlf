from pathlib import Path
import hashlib,json,subprocess
D=Path(__file__).resolve().parent;S=D.parents[2]/'mlf-crates-prefix-source-20261026';S2=S.parent/'mlf-crates-fingerprint-source-20261026'
j=json.loads((D/'candidate.json').read_text());patch=b''
for n in j['source_sha256']:
 r=subprocess.run(['git','diff','--no-index','--src-prefix=a/','--dst-prefix=b/',str(S2/n),str(S/n)],capture_output=True);assert r.returncode in (0,1)
 patch+=r.stdout.replace(('a'+str(S2)).encode(),b'a').replace(('b'+str(S)).encode(),b'b')
 j['source_sha256'][n]=hashlib.sha256((S/n).read_bytes()).hexdigest()
(D/'prefix-sharing.patch').write_bytes(patch);j['candidate_patch_sha256']=hashlib.sha256(patch).hexdigest()
(D/'candidate.json').write_text(json.dumps(j,indent=2)+'\n')
subprocess.run(['git','-C',str(S2),'apply','--check',str(D/'prefix-sharing.patch')],check=True)
subprocess.run(['git','-C',str(S),'diff','--check'],check=True)
print(json.dumps(j,indent=2))
