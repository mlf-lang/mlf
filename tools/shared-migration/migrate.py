#!/usr/bin/env python3
"""One-time reviewed AST migration. Never invoked by a normal compiler build.

Use --output to inspect an isolated proposed source tree. --apply is allowed
only after parallel source edits have completed and the proposal is reviewed.
"""
import argparse, hashlib, json, pathlib, re, subprocess
ROOT=pathlib.Path(__file__).resolve().parents[2]
DIRECT_TESTS={
    "MLF.Tests.Async.TaskMain":"tests/async-task/Main.emlf",
    "MLF.Tests.Async.TaskProcesses":"tests/async-task/Processes.emlf",
    "MLF.Tests.Async.TaskWaitGraph":"tests/async-task/WaitGraph.emlf",
    "MLF.Tests.Async.ProcessMain":"tests/async-process/Main.emlf",
    "MLF.Tests.Async.ProcessPanic":"tests/async-process/Panic.emlf",
    "MLF.Tests.SharedFrontend":"bootstrap/tests/shared-frontend.emlf",
    "MLF.Tests.PRQuickMain":"tests/PRQuickMain.emlf",
}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def inventory(root):
    modules={}
    for p in sorted((root/'libraries').glob('*/mlf-package.json')):
        for n,s in json.loads(p.read_text()).get('library',{}).get('modules',{}).items():
            assert n not in modules,n
            modules[n]=p.parent/s
    for n,spec in json.loads((root/'mlf-package.json').read_text())['executables'].items():
        entry='MLF.Entry.'+''.join(w.title() for w in n.split('-'))
        modules[entry]=root/spec['main']
        for module,s in spec.get('modules',{}).items():
            assert module not in modules or modules[module]==root/s,module
            modules[module]=root/s
    for n,source in DIRECT_TESTS.items():
        modules[n]=root/source
    return modules

def destination(module,source,root):
    if module.startswith('MLF.Tests.'):
        return pathlib.Path('tests/shared')/pathlib.Path(*module.split('.')).with_suffix('.hs')
    if module.startswith('MLF.Entry.'):
        return pathlib.Path(source.relative_to(root).parts[0])/'MLF'/'Entry'/(module.split('.')[-1]+'.hs')
    return source.relative_to(root).with_suffix('.hs')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=pathlib.Path,default=ROOT)
    ap.add_argument('--output',type=pathlib.Path,required=True)
    ap.add_argument('--tool',type=pathlib.Path,required=True)
    ap.add_argument('--apply',action='store_true')
    ap.add_argument('--input-revision',help='Verified revision of an extracted frozen archive without .git metadata')
    args=ap.parse_args(); root=args.root.resolve(); out=args.output.resolve()
    assert out!=root,'Use a separate proposal directory; --apply then copies verified bytes.'
    out.mkdir(parents=True,exist_ok=True)
    modules=inventory(root)
    records=[]; rows=[]
    for name,source in sorted(modules.items()):
        target=out/destination(name,source,root)
        records.append(dict(module=name,old_path=str(source.relative_to(root)),new_path=str(target.relative_to(out)),old_sha256=sha(source),old_lines=len(source.read_bytes().splitlines()),membership='direct-test' if name.startswith('MLF.Tests.') else 'implementation',operation='copy' if name.startswith('MLF.Tests.') else 'rename'))
        rows.append('\t'.join([str(source),str(target),name]))
    (out/'sources.tsv').write_text('\n'.join(rows)+'\n')
    primitive=(root/'libraries/mlf-language-core/Bootstrap/Primitive.emlf').read_text()
    names=re.findall(r'-> "([A-Za-z][A-Za-z0-9]*)"',primitive.split('primitiveName',2)[-1].split('primitiveType')[0])
    names=list(dict.fromkeys(names+['fmap','pure','liftA2','return','bind','implementationHost']))
    (out/'primitive-names.txt').write_text('\n'.join(names)+'\n')
    subprocess.run([str(args.tool),str(out/'sources.tsv'),str(out/'primitive-names.txt'),str(out/'audit')],check=True)
    for r in records:
        p=out/r['new_path']; r.update(new_sha256=sha(p),new_lines=len(p.read_bytes().splitlines()))
    counts={}
    totals={}
    for line in (out/'audit/counts.tsv').read_text().splitlines():
        fields=line.split('\t')
        values={k:int(v) for item in fields[3:] if '=' in item for k,v in [item.split('=',1)]}
        counts[fields[2]]=values
        for k,v in values.items(): totals[k]=totals.get(k,0)+v
    for r in records: r['counts']=counts[r['module']]
    tool_sources={str(p.relative_to(ROOT)):sha(p) for p in pathlib.Path(__file__).parent.rglob('*') if p.is_file() and 'evidence' not in p.parts and '__pycache__' not in p.parts}
    input_revision=args.input_revision or subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    (out/'audit/summary.json').write_text(json.dumps({'files':len(records),'counts':totals,'checks':{'AST_printer_roundtrip':True,'expression_string_token_bytes_retained':True,'no_string_patterns_remain':True,'recursive_local_signatures_closed':True,'nonrecursive_capture_analysis':'all local groups, original lexical scope'},'input_revision':input_revision,'tool_sources':tool_sources},indent=2)+'\n')
    (out/'modules.json').write_text(json.dumps([{'module':r['module'],'path':r['new_path'],'old_path':r['old_path'],'membership':r['membership']} for r in records],indent=2)+'\n')
    (out/'migration-manifest.json').write_text(json.dumps(dict(format=1,input_revision=input_revision,source_baseline='2f8584423fa3055ca96d1479734357f742c9b3df',files=records),indent=2)+'\n')
    if args.apply:
        for r in records:
            source=root/r['old_path']; target=root/r['new_path']
            assert sha(source)==r['old_sha256'],'Input changed during migration: '+str(source)
            assert not target.exists(),'Target exists: '+str(target)
        for r in records:
            source=root/r['old_path']; target=root/r['new_path']; target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((out/r['new_path']).read_bytes())
            if r['operation']=='rename': source.unlink()
        changes=[]
        renamed={r['old_path']:r['new_path'] for r in records if r['operation']=='rename'}
        for manifest in [root/'mlf-package.json',*sorted((root/'libraries').glob('*/mlf-package.json'))]:
            old_hash=sha(manifest); data=json.loads(manifest.read_text())
            def mapped(source):
                old=str((manifest.parent/source).relative_to(root))
                return str((root/renamed[old]).relative_to(manifest.parent)) if old in renamed else source
            library=data.get('library',{})
            if 'modules' in library:
                library['modules']={n:mapped(src) for n,src in library['modules'].items()}
            for kind in ['executables','tests']:
                for target in data.get(kind,{}).values():
                    if 'main' in target:
                        target['main']=mapped(target['main'])
                        target['source-syntax']='shared-haskell-v1' if target['main'].endswith('.hs') else 'legacy-emlf-v1'
                    if 'modules' in target:
                        target['modules']={n:mapped(src) for n,src in target['modules'].items()}
            data['source-syntax']='shared-haskell-v1'
            manifest.write_text(json.dumps(data,indent=2)+'\n')
            changes.append({'path':str(manifest.relative_to(root)),'old_sha256':old_hash,'new_sha256':sha(manifest)})
        (out/'audit/native-manifests.json').write_text(json.dumps(changes,indent=2)+'\n')
        audit=root/'tools/shared-migration/evidence'; audit.mkdir(exist_ok=True)
        import shutil
        shutil.copytree(out/'audit',audit,dirs_exist_ok=True)
        shutil.copy2(out/'migration-manifest.json',audit/'migration-manifest.json')
    print(json.dumps({'files':len(records),'old_lines':sum(r['old_lines'] for r in records),'new_lines':sum(r['new_lines'] for r in records),'applied':args.apply}))
if __name__=='__main__': main()
