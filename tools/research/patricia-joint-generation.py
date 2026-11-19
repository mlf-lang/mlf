"""Adopt actual generator output from an independently authenticated stale-only precursor; fully rebuild final producers."""
import hashlib,json,pathlib,re,shutil,subprocess,sys,types
ROOT=pathlib.Path.cwd();E=ROOT/'evidence'
PINS={'old_swap': 'd8325d909c249fd82d4ad6173d44d8818cc6f8bf', 'fast_only': 'd8325d909c249fd82d4ad6173d44d8818cc6f8bf', 'omit_only': 'd8325d909c249fd82d4ad6173d44d8818cc6f8bf'}
SOURCE_IDENTITIES={'old': {'surface_blob': '3e8082684587d25915d7f209bbf74d32e7c3dcc7', 'builtin_source': 'builtin-source-v1:b54f095675c2c7bd91b804689ab3de3775c0461ab982dc24bfc8d08477d88b6f'}, 'old_swap': {'surface_blob': 'a11262a585792e391d02e379e11e233af627fff0', 'builtin_source': 'builtin-source-v1:b43c5ddf9224142d296b984833de88528272e318f53fa6203614cd9576c7abae'}, 'fast_only': {'surface_blob': 'b781f419b82b91bbfed90aa5189107f0af6bf82d', 'builtin_source': 'builtin-source-v1:276ab74f565ea04cac324bbbf026a12c4ceda8316ac1c2e0f6c2efe2fc11ac82'}, 'omit_only': {'surface_blob': '0d50f8ae4713674ac7654c1a84cba0289ee6c57e', 'builtin_source': 'builtin-source-v1:47cef3a374d2075d43a2c707993baa62a3db760fa950a0ea0633afd8af0d3758'}}
PATCHES={'old_swap': '--- a/libraries/mlf-frontend/Bootstrap/Surface.hs\n+++ b/libraries/mlf-frontend/Bootstrap/Surface.hs\n@@ -282,9 +282,41 @@\n   lowerExpression :: SExpr -> Either String SExpr;\n   lowerExpression = lowerExpressionWithData D.emptyDataEnv;\n   lowerExpressionWithData :: DataEnv -> SExpr -> Either String SExpr;\n-  lowerExpressionWithData env original = do {\n-    shared <- Desugar.lowerSharedDo env original;\n-    runFresh (Desugar.allNames shared) (lower env (Desugar.desugarDo shared))\n+  lowerExpressionWithData env original =\n+    if surfaceCore original then Right original else do {\n+      shared <- Desugar.lowerSharedDo env original;\n+      -- lowerSharedDo also expands every legacy do block it visits.\n+      runFresh (Desugar.allNames shared) (lower env shared)\n+    };\n+  -- These forms need no pattern compilation or fresh names. Preserve the\n+  -- existing tree, including its declaration IDs, name hints and source spans.\n+  -- A case, equation or do block takes the ordinary lowering path.\n+  surfaceCore :: SExpr -> Bool;\n+  surfaceCore expression = case expression of {\n+    SDeclScope _ body -> surfaceCore body;\n+    SSourceDefinition body -> surfaceCore body;\n+    SCallSite _ _ body -> surfaceCore body;\n+    SLam _ _ body -> surfaceCore body;\n+    SApp f x -> surfaceCore f && surfaceCore x;\n+    SLet _ rhs body -> surfaceCore rhs && surfaceCore body;\n+    SAnn body _ -> surfaceCore body;\n+    SSignature body _ -> surfaceCore body;\n+    SChecked _ body -> surfaceCore body;\n+    SLetRec ds body -> all (\\((,,) _ _ rhs) -> surfaceCore rhs) ds && surfaceCore body;\n+    SCase _ _ -> False;\n+    SEquations _ -> False;\n+    SDo _ _ -> False;\n+    SSharedBind _ _ _ _ _ -> False;\n+    SGlobal _ _ -> True;\n+    SWantedRefs _ _ -> True;\n+    SVar _ -> True;\n+    SConstructor _ -> True;\n+    SIntLit _ -> True;\n+    SDoubleLit _ -> True;\n+    SBoolLit _ -> True;\n+    SStringLit _ -> True;\n+    SPrimitive _ -> True;\n+    SWanted _ _ -> True\n   };\n   flatPattern :: SPattern -> Bool;\n   flatPattern pattern =\n', 'fast_only': '--- a/libraries/mlf-frontend/Bootstrap/Surface.hs\n+++ b/libraries/mlf-frontend/Bootstrap/Surface.hs\n@@ -282,9 +282,41 @@\n   lowerExpression :: SExpr -> Either String SExpr;\n   lowerExpression = lowerExpressionWithData D.emptyDataEnv;\n   lowerExpressionWithData :: DataEnv -> SExpr -> Either String SExpr;\n-  lowerExpressionWithData env original = do {\n-    shared <- Desugar.lowerSharedDo env original;\n-    runFresh (Desugar.allNames shared) (lower env (Desugar.desugarDo shared))\n+  lowerExpressionWithData env original =\n+    if surfaceCore original then Right original else do {\n+      shared <- Desugar.lowerSharedDo env original;\n+      -- lowerSharedDo also expands every legacy do block it visits.\n+      runFresh (Desugar.allNames shared) (lower env (Desugar.desugarDo shared))\n+    };\n+  -- These forms need no pattern compilation or fresh names. Preserve the\n+  -- existing tree, including its declaration IDs, name hints and source spans.\n+  -- A case, equation or do block takes the ordinary lowering path.\n+  surfaceCore :: SExpr -> Bool;\n+  surfaceCore expression = case expression of {\n+    SDeclScope _ body -> surfaceCore body;\n+    SSourceDefinition body -> surfaceCore body;\n+    SCallSite _ _ body -> surfaceCore body;\n+    SLam _ _ body -> surfaceCore body;\n+    SApp f x -> surfaceCore f && surfaceCore x;\n+    SLet _ rhs body -> surfaceCore rhs && surfaceCore body;\n+    SAnn body _ -> surfaceCore body;\n+    SSignature body _ -> surfaceCore body;\n+    SChecked _ body -> surfaceCore body;\n+    SLetRec ds body -> all (\\((,,) _ _ rhs) -> surfaceCore rhs) ds && surfaceCore body;\n+    SCase _ _ -> False;\n+    SEquations _ -> False;\n+    SDo _ _ -> False;\n+    SSharedBind _ _ _ _ _ -> False;\n+    SGlobal _ _ -> True;\n+    SWantedRefs _ _ -> True;\n+    SVar _ -> True;\n+    SConstructor _ -> True;\n+    SIntLit _ -> True;\n+    SDoubleLit _ -> True;\n+    SBoolLit _ -> True;\n+    SStringLit _ -> True;\n+    SPrimitive _ -> True;\n+    SWanted _ _ -> True\n   };\n   flatPattern :: SPattern -> Bool;\n   flatPattern pattern =\n', 'omit_only': '--- a/libraries/mlf-frontend/Bootstrap/Surface.hs\n+++ b/libraries/mlf-frontend/Bootstrap/Surface.hs\n@@ -284,7 +284,7 @@\n   lowerExpressionWithData :: DataEnv -> SExpr -> Either String SExpr;\n   lowerExpressionWithData env original = do {\n     shared <- Desugar.lowerSharedDo env original;\n-    runFresh (Desugar.allNames shared) (lower env (Desugar.desugarDo shared))\n+    runFresh (Desugar.allNames shared) (lower env shared)\n   };\n   flatPattern :: SPattern -> Bool;\n   flatPattern pattern =\n'}
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

def check_source(root,lane):
 assert lane in SOURCE_IDENTITIES
 assert git(root,'rev-parse','HEAD:'+SUR)==SOURCE_IDENTITIES[lane]['surface_blob']
 identity,_=load(root/'tools/shared/builtin_prelude_identity.py').source_identity(root)
 assert identity==SOURCE_IDENTITIES[lane]['builtin_source']

def prepare():
 E.mkdir(exist_ok=True)
 for lane in ('old','old_swap','fast_only','omit_only'):
  root=ROOT/lane
  git(ROOT,'worktree','add','--detach',str(root),'d8325d909c249fd82d4ad6173d44d8818cc6f8bf')
  if lane in PATCHES:
   patch=E/(lane+'-source.patch');patch.write_text(PATCHES[lane])
   subprocess.run(['git','-C',str(root),'apply','--check',str(patch)],check=True)
   subprocess.run(['git','-C',str(root),'apply',str(patch)],check=True)
   git(root,'add',SUR)
   git(root,'-c','user.name=Diagnostic','-c','user.email=diag@localhost','commit','-m','Temporary exact factorial Surface source')
   assert git(root,'diff','--name-only',PINS[lane],'HEAD').splitlines()==[SUR]
   assert git(root,'show','-s','--format=%P','HEAD')==PINS[lane]
  check_source(root,lane)
  assert git(root,'status','--porcelain','--untracked-files=no')==''
 (E/'factor-source-identities.json').write_text(json.dumps(SOURCE_IDENTITIES,indent=2)+'\n')

def clean_failure(source):
 assert source in tuple(lane+'_generation' for lane in PINS)
 s=read(E/(source+'-build-supervisor.json'));g=read(E/(source+'-build-guard/bounded-receipt.json'))
 assert s['phase']=='terminal' and s['cleanup_complete'] and not s['survivors'] and not s['signals'] and not s['cancel_signals']
 assert s['reason']=='target exited' and s['target_exit_code']==1 and not s['complete']
 assert g['exit_code']==1 and g['reason'] is None and not g['complete']
 root=ROOT/source;check_source(root,source.removesuffix('_generation'));h=authenticator(root)
 h.authenticate(root,root/'.mlf-build/shared-ghc/receipt.json')
 import difflib
 old=root/'tools/shared/generate_builtin_evidence.py';new=ROOT/'tools/research/patricia-stale-authenticator.py'
 (E/(source+'-authenticator.json')).write_text(json.dumps({'historical_sha256':sha(old),'diagnostic_sha256':sha(new)},indent=2)+'\n')
 (E/(source+'-authenticator.diff')).write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='historical',tofile='diagnostic')))

def adopt(lane):
 assert lane in PINS
 gen=ROOT/(lane+'_generation');final=ROOT/lane;check_source(gen,lane);check_source(final,lane);h=authenticator(gen)
 _,evidence=h.authenticate(gen,gen/'.mlf-build/shared-ghc/receipt.json')
 result=gen/'.mlf-build/builtin-generation-guard/results';r=read(result/'receipt.json')
 assert r['format']=='patricia-builtin-generation-evidence-v1' and r['complete'] and r['generation_succeeded'] and r['immutable_inputs_verified_after']
 assert r['generation_only'] and not r['toolchain_qualification'] and not r['producer_build_complete']
 assert r['source_identity']==evidence['snapshot']['source_identity']==SOURCE_IDENTITIES[lane]['builtin_source']
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
 for lane in ('old','old_swap','fast_only','omit_only','old_swap_generation','fast_only_generation','omit_only_generation'):
  root=ROOT/lane;build=root/'.mlf-build/shared-ghc';dest=E/(lane+'-raw');dest.mkdir(exist_ok=False)
  files={p:dest/p.name for p in list(build.glob('*.log'))+[build/'receipt.json',build/'packages.txt'] if p.is_file()}
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
 if sys.argv[1:]==['prepare']:prepare()
 elif sys.argv[1:]==['collect']:collect()
 else:
  action,lane=sys.argv[1:]
  if action=='clean-failure':clean_failure(lane)
  elif action=='adopt':adopt(lane)
  else:raise ValueError(action)
