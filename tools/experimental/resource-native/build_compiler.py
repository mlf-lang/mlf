#!/usr/bin/env python3
"""Build only the actual PR25 emlf dependency closure with an existing GHC9.14.1.
No installer, standard-library native build, package cache, or benchmark is invoked.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,time,types
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
PINNED_COMMIT='7bf7ac6db5e3db2daff2e0a1c249e68ae0db2d0c'
SOURCE_MANIFEST_SHA='bd918d20b7bf4c0fa794d12e22788a9c2f55d1ae721f1d87f58258b808a99dbc'
COMPILER_CONTRACT_SHA='132aa66e8597da232cff4cde91fea2eb86c4f2235fcc7a85a88e27896adc8fb1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ghc',required=True,type=Path);p.add_argument('--build-dir',required=True,type=Path);args=p.parse_args()
    ghc=args.ghc.resolve(strict=True);cc=Path(shutil.which('cc')).resolve(strict=True)
    if subprocess.check_output([str(ghc),'--numeric-version'],text=True).strip()!='9.14.1':raise ValueError('requires existing officialGHC9.14.1')
    if sha(BASE/'provenance/pr25-source.json')!=SOURCE_MANIFEST_SHA:raise ValueError('pinned PR25 source manifest changed')
    if sha(BASE/'provenance/compiler-inputs.json')!=COMPILER_CONTRACT_SHA:raise ValueError('audited trial compiler input contract changed')
    contract=json.loads((BASE/'provenance/compiler-inputs.json').read_text())
    for rel,digest in contract.items():
        if sha(ROOT/rel)!=digest:raise ValueError('trial compiler source changed: '+rel)
    # Execute exact captured source bytes, never unchecked .pyc.
    path=ROOT/'tools/shared/build.py';blob=path.read_bytes()
    if hashlib.sha256(blob).hexdigest()!=contract['tools/shared/build.py']:raise ValueError('upstream builder changed before source-byte import')
    upstream=types.ModuleType('_pr25_build_inventory');upstream.__file__=str(path);exec(compile(blob,str(path),'exec'),upstream.__dict__)
    manifest=upstream.load_manifest()
    original=json.loads((BASE/'provenance/pr25-source.json').read_text())
    if original['source_commit']!=PINNED_COMMIT:raise ValueError('wrong pinned PR25 commit')
    allowed_changes={'bootstrap/MLF/Entry/Emlf.hs'}
    for rel,digest in original['files'].items():
        if rel not in allowed_changes and sha(ROOT/rel)!=digest:raise ValueError('pinned ordinary compiler dependency changed: '+rel)
    mapping={m['module']:m['path'] for m in manifest['modules']}
    mapping.update({'MLF.Primitive':'host/ghc/MLF/Primitive.hs','MLF.Host.Base':'host/ghc/MLF/Host/Base.hs','MLF.Host.Async':'host/ghc/MLF/Host/Async.hs','MLF.Host.IO':'host/ghc/MLF/Host/IO.hs','Main':'host/ghc/app/emlf/Main.hs'})
    paths=set(mapping.values())|{'shared-sources.json','mlf-shared.cabal','mlf-package.json','mlf.lock','tools/shared/build.py',str(Path(__file__).relative_to(ROOT)),'tools/experimental/resource-native/provenance/pr25-source.json','host/ghc/cbits/host.c'}
    paths|={str(x.relative_to(ROOT)) for x in (ROOT/'runtime').glob('*.h')};paths.add('runtime/mlf_process_supervisor.c')
    expected=set(contract)|{str(Path(__file__).relative_to(ROOT)),'tools/experimental/resource-native/provenance/pr25-source.json'}
    if paths!=expected:raise ValueError('compiler build input inventory differs from audited contract')
    inputs={s:sha(ROOT/s) for s in sorted(paths)}
    build=args.build_dir.resolve();build.mkdir(parents=True,exist_ok=False);objects=build/'objects';objects.mkdir()
    report={'status':'building','base_commit':original['source_commit'],'inputs':inputs,'commands':[],'tools':{str(ghc):sha(ghc),str(cc):sha(cc)},'compiler_contract_sha256':COMPILER_CONTRACT_SHA,'source_manifest_sha256':SOURCE_MANIFEST_SHA,'ghc_version':'9.14.1'}
    receipt=BASE/'validation/compiler-build.json'
    def save():receipt.write_text(json.dumps(report,indent=2)+'\n')
    def run(argv,label):
        argv=list(map(str,argv));start=time.monotonic()
        with (build/(label+'.log')).open('w') as log:r=subprocess.run(argv,cwd=ROOT,env=dict(os.environ,GHC_ENVIRONMENT='-',GHCRTS='',LC_ALL='C.UTF-8'),stdout=log,stderr=subprocess.STDOUT,timeout=600)
        report['commands'].append({'argv':argv,'cwd':str(ROOT),'exit_code':r.returncode,'seconds':time.monotonic()-start,'log':str(build/(label+'.log')),'log_sha256':sha(build/(label+'.log'))});save()
        if r.returncode:raise ValueError('actual compiler build failed: '+str(build/(label+'.log')))
    save()
    try:
        cobjects=[]
        for name,source in [('host','host/ghc/cbits/host.c'),('supervisor','runtime/mlf_process_supervisor.c')]:
            out=objects/(name+'.o');run([cc,'-O0','-std=c11','-I'+str(ROOT/'runtime'),'-c',ROOT/source,'-o',out],name);cobjects.append(out)
        flags=['-v','-ddump-types','-XHaskell2010','-O0','-fpedantic-bottoms','-fno-state-hack','-Werror=incomplete-patterns','-Werror=incomplete-uni-patterns','-Wno-star-is-type','-Wno-overlapping-patterns','-Wno-deprecations','-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db','-hide-all-packages','-i']+['-i'+str(ROOT/r) for r in manifest['source_roots']]+['-odir',objects,'-hidir',objects,'-rtsopts=ignoreAll']
        for package in ['base','array','bytestring','text','containers','directory']:flags+=['-package',package]
        binary=build/'emlf';run([ghc,'--make','-j1','-fforce-recomp',*flags,ROOT/'host/ghc/app/emlf/Main.hs',*cobjects,'-o',binary],'compile')
        resolved={}
        for name,path in re.findall(r'Compiling\s+([\w.]+)\s+\(\s*([^,\n]+),',(build/'compile.log').read_text()):
            if name not in mapping or Path(path.strip()).resolve()!=(ROOT/mapping[name]).resolve():raise ValueError('unexpected compiler module resolution: '+name)
            if name in resolved:raise ValueError('duplicate compiled module: '+name)
            resolved[name]={'path':mapping[name],'sha256':inputs[mapping[name]]}
        if not {'MLF.Entry.Emlf','MLF.ResourceExport','MLF.PreparedCompiler','Bootstrap.CompilerCore','Bootstrap.X.Checked','Bootstrap.X.Check','Bootstrap.Parser'}<=set(resolved):raise ValueError('actual compiler proof closure missing')
        shared_names={m['module'] for m in manifest['modules']}
        shared_inputs={name:item for name,item in resolved.items() if name in shared_names}
        interfaces=upstream.audit_inferred_interfaces((build/'compile.log').read_text(),shared_inputs)
        report.update(status='built',binary=str(binary),binary_sha256=sha(binary),resolved_modules=resolved,inferred_shared_interfaces=interfaces)
    finally:
        report['immutable_inputs_verified_after']=all(sha(ROOT/p)==digest for p,digest in inputs.items())
        if not report['immutable_inputs_verified_after']:report['status']='invalidated'
        save()
    print(receipt)
if __name__=='__main__':main()
