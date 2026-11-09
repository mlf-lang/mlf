import pathlib,json,hashlib,sys
sys.path.insert(0,'tools/shared');from test_direct import authenticate_build
name=sys.argv[1];old=pathlib.Path('.mlf-build')/name;out=pathlib.Path('.mlf-build/integration-modular')/name
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=json.loads((out/'sources.before.json').read_text());after={n:sha(pathlib.Path(n)) for n in before};assert before==after
assert (out/'spec.sha256').read_text().strip()==sha(old/'crate.spec')
p=pathlib.Path('.mlf-build/recovery-ghc-O2/receipt.json');r=authenticate_build(p,p.parent/'bin');assert all(sha(p.parent/n)==h for n,h in r['object_inputs'].items())
receipt=json.loads((out/'bounded-receipt.json').read_text());assert receipt['complete']
artifacts={}
for ext in ['mlfci','mlfco']:
 f=pathlib.Path('artifact')/('unit.'+ext);current=sha(old/f);previous=sha(out/'historical'/f);artifacts[str(f)]={'current':current,'historical':previous,'identical':current==previous};assert current==previous
q=json.loads((old/'artifact/unit.queries').read_text());result={'complete':True,'source_unchanged':True,'producer_reauthenticated':True,'producer_receipt_sha256':sha(p),'spec_sha256':sha(old/'crate.spec'),'artifacts':artifacts,'inferred_groups':q['inferred_groups'],'reused_groups':q['reused_groups'],'native_or_llvm':False,'elapsed_seconds':receipt['elapsed_seconds'],'peak_rss':receipt['peak_group_rss']}
(out/'sources.after.json').write_text(json.dumps(after,indent=2)+'\n');(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
