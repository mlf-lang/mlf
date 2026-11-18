"""Adopt actual generator output from an independently authenticated stale-only precursor; fully rebuild final producers."""
import hashlib,json,pathlib,re,shutil,subprocess,sys,types
ROOT=pathlib.Path.cwd();E=ROOT/'evidence'
PINS={'old_swap':'d8325d909c249fd82d4ad6173d44d8818cc6f8bf','new_swap':'ee495d5783fca3c26a3c0e659ebeac1bab76a37d'}
CAN='bootstrap/MLF/BuiltinPreludeData.hs';SUR='libraries/mlf-frontend/Bootstrap/Surface.hs'
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):
 m=types.ModuleType(p.stem);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m

HISTORICAL='181f748533867c97488552777831aecaddd72232cd30c4850ec772017c30670a'
def authenticator(root):
 old=root/'tools/shared/generate_builtin_evidence.py';new=ROOT/'tools/research/patricia-stale-authenticator.py'
 assert sha(old)==HISTORICAL
 expected=old.read_text().replace("FORMAT = 'builtin-generation-evidence-v1'", "FORMAT = 'patricia-builtin-generation-evidence-v1'").replace('*builder.LINK_FLAGS,', "*builder.executable_link_flags(row['name']),")
 assert new.read_text()==expected
 return load(new)

def clean_failure(source):
 assert source in ('old_swap_generation','new_swap_generation')
 s=read(E/(source+'-build-supervisor.json'));g=read(E/(source+'-build-guard/bounded-receipt.json'))
 assert s['phase']=='terminal' and s['cleanup_complete'] and not s['survivors'] and not s['signals'] and not s['cancel_signals']
 assert s['reason']=='target exited' and s['target_exit_code']==1 and not s['complete']
 assert g['exit_code']==1 and g['reason'] is None and not g['complete']
 root=ROOT/source;h=authenticator(root)
 h.authenticate(root,root/'.mlf-build/shared-ghc/receipt.json')
 import difflib
 old=root/'tools/shared/generate_builtin_evidence.py';new=ROOT/'tools/research/patricia-stale-authenticator.py'
 (E/(source+'-authenticator.json')).write_text(json.dumps({'historical_sha256':sha(old),'diagnostic_sha256':sha(new)},indent=2)+'\n')
 (E/(source+'-authenticator.diff')).write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='historical',tofile='diagnostic')))

def adopt(lane):
 assert lane in PINS
 gen=ROOT/(lane+'_generation');final=ROOT/lane;h=authenticator(gen)
 _,evidence=h.authenticate(gen,gen/'.mlf-build/shared-ghc/receipt.json')
 result=gen/'.mlf-build/builtin-generation-guard/results';r=read(result/'receipt.json')
 assert r['format']=='patricia-builtin-generation-evidence-v1' and r['complete'] and r['generation_succeeded'] and r['immutable_inputs_verified_after']
 assert r['generation_only'] and not r['toolchain_qualification'] and not r['producer_build_complete']
 assert r['source_identity']==evidence['snapshot']['source_identity']
 assert all(r[k]==v for k,v in evidence.items())
 v=load(gen/'tools/shared/verify_builtin_prelude.py');v.verify_inputs(r['inputs'])
 assert len(r['commands'])==1
 c=r['commands'][0]
 assert c['label']=='fresh-literal' and c['argv']==[str(gen/'.mlf-build/shared-ghc/bin/builtin-prelude'),r['source_identity']]
 assert c['cwd']==str(gen) and c['timeout_seconds']==600
 v.verify_file(r['diagnostic_driver'],ROOT/'tools/research/patricia-stale-authenticator.py')
 assert c['exit_code']==0 and c['input_pins_verified_before'] and c['input_pins_verified_after']
 literal=v.verify_file(c['stdout'],result/'fresh-literal.stdout');err=v.verify_file(c['stderr'],result/'fresh-literal.stderr')
 assert not err.read_bytes() and 0<len(literal.read_bytes())<=8*1024**2
 assert git(gen,'rev-parse','HEAD')==git(final,'rev-parse','HEAD')
 for root in (gen,final):
  assert git(root,'show','-s','--format=%P','HEAD')==PINS[lane]
  assert git(root,'status','--porcelain','--untracked-files=no')==''
  assert git(root,'diff','--name-only',PINS[lane],'HEAD').splitlines()==[SUR]
 shutil.copyfile(literal,E/(lane+'-generated-literal.hs'))
 shutil.copyfile(result/'receipt.json',E/(lane+'-generation-receipt.json'))
 assert (E/(lane+'-generated-literal.hs')).read_bytes()==literal.read_bytes()
 shutil.copyfile(literal,final/CAN)
 assert (final/CAN).read_bytes()==literal.read_bytes()
 git(final,'add',CAN)
 git(final,'-c','user.name=Diagnostic','-c','user.email=diag@localhost','commit','--amend','--no-edit')
 assert git(final,'show','-s','--format=%P','HEAD')==PINS[lane]
 assert git(final,'diff','--name-only',PINS[lane],'HEAD').splitlines()==[CAN,SUR]
 (E/(lane+'-joint.patch')).write_text(git(final,'diff',PINS[lane],'HEAD')+'\n')
 v.verify_inputs(r['inputs'])

def collect():
 total=0
 for lane in ('old','new','old_swap','new_swap','old_swap_generation','new_swap_generation'):
  root=ROOT/lane;build=root/'.mlf-build/shared-ghc';dest=E/(lane+'-raw');dest.mkdir(exist_ok=False)
  files={p:dest/p.name for p in list(build.glob('*.log'))+[build/'receipt.json'] if p.is_file()}
  for source,name in ((build/'builtin-verification','builtin-verification'),(root/'.mlf-build/builtin-generation-guard/results','generation-results')):
   for p in source.rglob('*'):
    if p.is_file():files[p]=dest/name/p.relative_to(source)
  manifest={}
  for p,q in files.items():
   assert not p.is_symlink() and p.resolve().is_relative_to(root.resolve())
   n=p.stat().st_size;total+=n
   assert total<=256*1024**2 and shutil.disk_usage(E).free >= 5*1024**3+n+1024**2
   q.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(p,q);assert q.stat().st_size==n
   manifest[str(q.relative_to(dest))]=sha(q)
  (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
 if sys.argv[1:]==['collect']:collect()
 else:
  action,lane=sys.argv[1:]
  if action=='clean-failure':clean_failure(lane)
  elif action=='adopt':adopt(lane)
  else:raise ValueError(action)
