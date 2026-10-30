#!/usr/bin/env python3
"""Compile three small differential-control modules using an authenticated P3.
No producer compilation; requires an explicitly reserved serial heavy slot.
Run beneath the task resource_watchdog, with output-root equal to --output.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, time, types
from pathlib import Path
if not __debug__:
 raise RuntimeError('P3 controls require enabled assertions; Python -O is forbidden')
D=Path(__file__).resolve().parent
EXPECTED_CONTROLS=922
EXPECTED_MODULES={'FrozenPrefix','FrozenInferenceUnit','Main'}
CURRENT_MODULES=EXPECTED_MODULES|{'QueryV6Bridge'}
EXPECTED_NEW_FILES={name+suffix for name in CURRENT_MODULES for suffix in ['.hi','.o']}
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
p=argparse.ArgumentParser();p.add_argument('--serial-slot-granted',action='store_true',required=True)
p.add_argument('--build-receipt',type=Path,required=True);p.add_argument('--source-root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);a=p.parse_args()
S=a.source_root.resolve(strict=True);receipt=a.build_receipt.resolve(strict=True);P=receipt.parent
out=a.output.resolve();assert not out.exists() and not out.is_relative_to(P) and not P.is_relative_to(out)
out.mkdir(parents=True)
j={'complete':False,'scope':'P3 prefix sharing byte/digest/error/lazy controls; no performance assertion',
   'commands':[],'producer_receipt_sha256':sha(receipt),'recipe_sha256':sha(__file__),'source':str(S)}
def save():(out/'receipt.json').write_text(json.dumps(j,indent=2)+'\n')
save()
try:
 direct=S/'tools/shared/test_direct.py';m=types.ModuleType('prefix_control_authentication');m.__file__=str(direct)
 exec(compile(direct.read_bytes(),str(direct),'exec'),m.__dict__)
 m.authenticate_build(receipt,P/'bin',root=S)
 compatibility_path=D.parent/'p2/native_compatibility.py'
 compatibility=types.ModuleType('native_p3_compatibility');compatibility.__file__=str(compatibility_path)
 exec(compile(compatibility_path.read_bytes(),str(compatibility_path),'exec'),compatibility.__dict__)
 native_manifest,historical_sources=compatibility.authenticate(S)
 helper_manifest=json.loads((D/'controls-manifest.json').read_text())
 assert helper_manifest['expected_differential_controls']==EXPECTED_CONTROLS
 assert set(helper_manifest['expected_compiled_modules'])==EXPECTED_MODULES
 # Retain the historical runner bytes/pin as provenance; the new runner and
 # exact source projection are pinned by the later compatibility manifest.
 assert all(sha(D/('historical-run-controls.py.txt' if n=='run_controls.py' else n))==h
            for n,h in helper_manifest['inputs'].items()),'frozen helper input changed'
 oracle=json.loads((D/'oracle-manifest.json').read_text())
 assert all(sha(D/n)==h for n,h in oracle['frozen'].items())
 candidate=json.loads((D/'candidate.json').read_text())
 assert all(hashlib.sha256(historical_sources.get(n,(S/n).read_bytes())).hexdigest()==h
            for n,h in candidate['source_sha256'].items())
 inputs=[D/n for n in ['FrozenPrefix.hs','FrozenInferenceUnit.hs','PrefixControls.hs','QueryV6Bridge.hs','oracle-manifest.json','candidate.json','controls-manifest.json','run_controls.py']]
 inputs += [compatibility.MANIFEST,compatibility_path,*[S/n for n in native_manifest['inputs']]]
 j['historical_candidate_pins_verified_after_exact_native_projection']=True
 j['native_compatibility_source_pins']={n:e['current_sha256'] for n,e in native_manifest['sources'].items()}
 j['test_input_sha256']={str(f):sha(f) for f in inputs};j['authentication_before']=True
 # Keep the complete frozen control and oracle files unchanged. Only its Q
 # import is redirected in an owned copy, so the 45 empty source-key cases can
 # compare the explicitly changed wire envelope. All other Q exports are the
 # production functions, and all checked-object byte comparisons stay raw.
 original=(D/'PrefixControls.hs').read_bytes()
 old_import=b'import qualified Bootstrap.CrateQuery as Q\n'
 new_import=b'import qualified QueryV6Bridge as Q\n'
 assert original.count(old_import)==1 and new_import not in original
 current_control=out/'PrefixControls.hs'
 old_main=b'main = do\n';new_main=old_main+b'  Q.validateBridge\n'
 assert original.count(old_main)==1 and new_main not in original
 current_control.write_bytes(original.replace(old_import,new_import).replace(old_main,new_main))
 assert current_control.read_bytes().replace(new_import,old_import).replace(new_main,old_main)==original
 j['test_input_sha256'][str(current_control)]=sha(current_control)
 j['query_key_compatibility']={'version':'v6-to-v5-empty-group-only','cases':45,'bridge_controls':7,
   'frozen_control_sha256':sha(D/'PrefixControls.hs'),'copy_sha256':sha(current_control),
   'checked_output_normalized':False}
 objects=out/'objects';shutil.copytree(P/'objects',objects)
 for ext in ['hi','o']:(objects/('Main.'+ext)).unlink(missing_ok=True)
 pins={str(f.relative_to(objects)):sha(f) for f in objects.rglob('*') if f.is_file()}
 j['copied_object_file_sha256']=pins
 r=json.loads(receipt.read_text())
 argv=next(c['argv'] for c in r['commands'] if any('app/emlf/Main.hs' in x for x in c['argv']))
 argv=[x.replace(str(P/'objects'),str(objects)).replace(str(P/'bin/emlf'),str(out/'check')).replace(str(S/'host/ghc/app/emlf/Main.hs'),str(current_control)) for x in argv]
 argv.insert(argv.index('-i')+1,'-i'+str(D));save()
 def command(label,argv):
  with (out/(label+'.stdout')).open('wb') as stdout,(out/(label+'.stderr')).open('wb') as stderr:
   t=time.monotonic_ns();r=subprocess.run(argv,cwd=S,env={**os.environ,'GHC_ENVIRONMENT':'-','GHCRTS':'','LC_ALL':'C.UTF-8'},stdout=stdout,stderr=stderr)
  j['commands'].append({'name':label,'argv':argv,'wall_ns':time.monotonic_ns()-t,'exit_code':r.returncode});save()
  assert r.returncode==0,(out/(label+'.stderr')).read_text()[-3000:]
 command('build',argv)
 assert all(sha(objects/n)==h for n,h in pins.items()),'a copied producer file changed'
 after_files={str(f.relative_to(objects)) for f in objects.rglob('*') if f.is_file()}
 assert after_files-set(pins)==EXPECTED_NEW_FILES,'unexpected new test/producer object inventory'
 build_log=(out/'build.stdout').read_text()+'\n'+(out/'build.stderr').read_text()
 compile_lines=[line for line in build_log.splitlines() if 'Compiling ' in line]
 modules=[]
 for line in compile_lines:
  match=re.fullmatch(r'\[\s*\d+\s+of\s+\d+\] Compiling ([A-Za-z0-9_.]+)\s+\( .* \)',line)
  assert match,'unknown compiler build record: '+line
  modules.append(match.group(1))
 assert len(modules)==4 and set(modules)==CURRENT_MODULES,'compiler module rebuilt or test module missing'
 j.update(compiled_modules=modules,new_object_files=sorted(after_files-set(pins)),expected_control_count=EXPECTED_CONTROLS)
 save()
 command('controls',[str(out/'check')])
 result=json.loads((out/'controls.stdout').read_text())
 assert result=={'complete':True,'differential_controls':EXPECTED_CONTROLS},'unexpected/truncated differential control result'
 assert (out/'controls.stderr').read_bytes()==b'','control stderr must be empty'
 m.authenticate_build(receipt,P/'bin',root=S)
 assert sha(receipt)==j['producer_receipt_sha256']
 assert all(sha(Path(n))==h for n,h in j['test_input_sha256'].items())
 assert all(sha(objects/n)==h for n,h in pins.items()),'copied producer inputs changed after controls'
 j.update(complete=True,authentication_after=True,copied_object_pins_verified=True,compiler_modules_rebuilt=False,
          result=result,binary_sha256=sha(out/'check'));save()
 print(json.dumps({k:v for k,v in j.items() if k not in ['commands','test_input_sha256','copied_object_file_sha256']},indent=2))
except BaseException as e:
 j['failure']=repr(e);save();raise
