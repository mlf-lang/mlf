"""Exact current target -> modified producer custody; no code generation/evaluation.

Loaded from hash-checked source bytes by both maintained builder and prepare.
Historical manifests remain immutable lineage, never an alternate live baseline.
"""
import hashlib,json,pathlib,re,types
TARGET='a250ec334b70b0e587c2dd6e894d111bf879c024'
TREE='63400c29c679ffc5e1a67b46ebbde12c5f81ddf4'
ANCHORS={'common_base':'7bf7ac6db5e3db2daff2e0a1c249e68ae0db2d0c','pr28':'ae680d2e8698b2a99f1957114b76394a1d6b39f5'}
HISTORICAL={'pr25-source.json': 'bd918d20b7bf4c0fa794d12e22788a9c2f55d1ae721f1d87f58258b808a99dbc', 'compiler-inputs.json': 'b836a052e5cc3a22e53c940d24a437e31552206b4bc4a2582842b6b5fdf6db66', 'c592-history/current-compiler-inputs.json': '0af6ad8809a442b8065796c22eab48548c40cb0a8f9dd8d057e49e9ee3822944', 'c592-history/current-producer.py': 'eb63f5d367014700098681dfe63f928adcde2f01dcf0f987dfcdb114c856dc8b', 'c592-history/current-target-source.json': 'b0ada8dcc8df7be5281d7a1a572600b0c912f2f13c3b727ab3f358c482ea72a8', 'c592-history/current-transition.json': '825339cfc513aaacf9b88160c3dbaa3fa1e8307d67ffbeadaca33c9d322daff0'}
ADDED=[{'module':'MLF.'+name,'path':'bootstrap/MLF/'+name+'.hs','role':'implementation'}for name in ['ResourceModuleExport','ResourceProjection','ResourceModules','ResourceExport']]
CHANGED=frozenset({'bootstrap/MLF/Entry/Emlf.hs','libraries/mlf-frontend/Bootstrap/Module.hs','libraries/mlf-inference/Bootstrap/CompilerCore.hs','bootstrap/MLF/BuiltinPreludeData.hs','shared-sources.json','mlf-shared.cabal','mlf-package.json','mlf.lock'})
PREFIX='tools/experimental/resource-native/'
BASELINE='current-target-source.json'
CONTRACT='current-compiler-inputs.json'
TRANSITION='current-transition.json'
HELPER='current-producer.py'

def require(test,message):
    if not test:raise ValueError(message)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def strict_pairs(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'duplicate producer JSON field: '+key);result[key]=value
    return result
def read(path):return json.loads(pathlib.Path(path).read_text(),object_pairs_hook=strict_pairs)
def digest(value):return type(value)is str and value!='0'*64 and re.fullmatch('[0-9a-f]{64}',value)is not None
def relative(path):
    require(type(path)is str and path and not pathlib.PurePosixPath(path).is_absolute() and '..'not in pathlib.PurePosixPath(path).parts and '\\'not in path and str(pathlib.PurePosixPath(path))==path,'noncanonical producer source path')
    return path
def inventory(root,manifest):
    return set(manifest['configuration_paths'])|set(manifest['runtime_headers'])|set(manifest['lineage_extra_paths'])|set(manifest['shared_manifest']['host_only'])|{r['path']for r in manifest['shared_manifest']['modules']}
def expected_shared(manifest):
    rows=manifest['shared_manifest']['modules']
    require(type(rows)is list and len(rows)==128 and len({r['module']for r in rows})==128 and len({r['path']for r in rows})==128,'exact target128 shared inventory required')
    require(rows[0]['module']=='Async.Process','target shared order anchor changed')
    return rows[:1]+ADDED[:3]+rows[1:]+ADDED[3:]
def check_transition(baseline,contract,transition,source_sha):
    require(type(contract)is dict and all(digest(v)for v in contract.values()),'current compiler input hashes malformed')
    original=baseline['files'];addpaths={r['path']for r in ADDED}
    require(set(contract)==set(original)|addpaths,'exact current compiler input set differs')
    for path in contract:relative(path)
    changed={p for p in original if contract[p]!=original[p]}
    require(changed==CHANGED,'current compiler transition changed unexpected ordinary dependencies')
    expected={'schema':'resource-current-producer-transition/1','target_commit':TARGET,'target_tree':TREE,'baseline_sha256':source_sha,'historical_anchors':ANCHORS,'historical_manifests':HISTORICAL,'changed':{p:{'old':original[p],'new':contract[p]}for p in sorted(CHANGED)},'added':{p:contract[p]for p in sorted(addpaths)},'unchanged':{p:original[p]for p in sorted(set(original)-CHANGED)},'shared_rows':expected_shared(baseline),'source_manifest_field_means':'unmodified current target dependency baseline; exact modified implementation is bound separately'}
    require(transition==expected,'exact current compiler transition schema/old/new/unchanged/shared inventory differs')
    return expected

PRELUDE_MANIFEST_SHA256='4acb3a90757a375a423fda9db6eda022597f350d34090ca8f4712a478fa594f5'
TARGET_LOCK_SHA256='7a175b669ef61ec8fe41765777c9b58cbd10aabe4e3b54e28c201b595f07ee79'
def validate_baseline_lineage(root,prov,baseline):
    previous=read(prov/'c592-history/current-target-source.json')
    path=prov/'c592-history/current-producer.py';blob=path.read_bytes()
    historical=types.ModuleType('_historical_resource_custody')
    exec(compile(blob,str(path),'exec'),historical.__dict__)
    historical.check_transition(previous,read(prov/'c592-history/current-compiler-inputs.json'),read(prov/'c592-history/current-transition.json'),sha(prov/'c592-history/current-target-source.json'))
    path=root/'tools/performance/crate-prelude/source-migration.json'
    require(sha(path)==PRELUDE_MANIFEST_SHA256,'fixed checked Prelude target transition')
    delta=read(path);require(delta['parent']==previous['source_commit'],'checked Prelude exact predecessor')
    rows={row['module']:row['path']for row in previous['shared_manifest']['modules']}
    files=dict(previous['files'])
    for name,row in delta['changed_sources'].items():
        require(files[rows[name]]==row['old'],'checked Prelude old owner differs')
        files[rows[name]]=row['new']
    files['mlf.lock']=TARGET_LOCK_SHA256
    expected={**previous,'source_commit':TARGET,'source_tree':TREE,'files':files,'dependency_digest':hashlib.sha256(canonical(files)).hexdigest()}
    require(baseline==expected,'exact full checked Prelude target baseline differs')

def validate(root,base,*,source_sha,contract_sha,transition_sha,helper_sha,build_sha=None):
    root=pathlib.Path(root).resolve();base=pathlib.Path(base).resolve();prov=base/'provenance'
    pins={BASELINE:source_sha,CONTRACT:contract_sha,TRANSITION:transition_sha,HELPER:helper_sha,**HISTORICAL}
    for name,wanted in pins.items():
        require(digest(wanted) and sha(prov/name)==wanted,('pinned current-target source manifest changed'if name==BASELINE else'current producer custody file changed: '+name))
    baseline=read(prov/BASELINE);contract=read(prov/CONTRACT);transition=read(prov/TRANSITION)
    validate_baseline_lineage(root,prov,baseline)
    require(set(baseline)=={'schema','source_commit','source_tree','dependency_digest','meaning','historical_anchors','shared_manifest','configuration_paths','runtime_headers','lineage_extra_paths','files'},'exact current target baseline schema differs')
    require(baseline['schema']=='resource-current-target-source/1'and baseline['source_commit']==TARGET and baseline['source_tree']==TREE and baseline['historical_anchors']==ANCHORS,'wrong current target baseline identity')
    require(type(baseline['files'])is dict and all(digest(v)for v in baseline['files'].values()),'target dependency hashes malformed')
    require(set(baseline['files'])==inventory(root,baseline),'target dependency inventory differs from complete manifest')
    require(baseline['configuration_paths']==sorted(set(baseline['configuration_paths']))and baseline['runtime_headers']==sorted(set(baseline['runtime_headers'])),'target configuration/header order or duplication differs')
    require(baseline['lineage_extra_paths']==['runtime/mlf_build_runner.c','runtime/mlf_runtime.c','runtime/mlf_windows_host.c'],'historical extra runtime dependency guards changed')
    require(hashlib.sha256(canonical(baseline['files'])).hexdigest()==baseline['dependency_digest'],'target dependency digest differs')
    check_transition(baseline,contract,transition,source_sha)
    current=read(root/'shared-sources.json');expected=dict(baseline['shared_manifest']);expected['modules']=expected_shared(baseline)
    require(current==expected,'current shared module path/role/order or metadata differs')
    inputs=dict(contract)
    for path,wanted in contract.items():
        source=root/relative(path)
        require(not source.is_symlink()and source.resolve().is_relative_to(root),'producer source escapes root')
        require(sha(source)==wanted,'current compiler input changed: '+path)
    for name,wanted in pins.items():inputs[PREFIX+'provenance/'+name]=wanted
    inputs['tools/performance/crate-prelude/source-migration.json']=PRELUDE_MANIFEST_SHA256
    builder=base/'build_compiler.py'
    if build_sha is not None:require(sha(builder)==build_sha,'audited compiler builder changed')
    inputs[PREFIX+'build_compiler.py']=sha(builder)
    mapping={r['module']:r['path']for r in current['modules']}
    mapping.update({'MLF.Primitive':'host/ghc/MLF/Primitive.hs','MLF.Host.Base':'host/ghc/MLF/Host/Base.hs','MLF.Host.Async':'host/ghc/MLF/Host/Async.hs','MLF.Host.IO':'host/ghc/MLF/Host/IO.hs','Main':'host/ghc/app/emlf/Main.hs'})
    return baseline,contract,inputs,mapping,current

def upstream_module(root,contract):
    path=pathlib.Path(root)/'tools/shared/build.py';blob=path.read_bytes()
    require(hashlib.sha256(blob).hexdigest()==contract['tools/shared/build.py'],'upstream builder changed before source-byte import')
    module=types.ModuleType('_current_resource_build_inventory');module.__file__=str(path)
    exec(compile(blob,str(path),'exec'),module.__dict__)
    return module

def actual_interfaces(root,log,mapping,inputs,shared,upstream):
    root=pathlib.Path(root).resolve();resolved={}
    for name,path in re.findall(r'Compiling\s+([\w.]+)\s+\(\s*([^,\n]+),',log):
        require(name in mapping and pathlib.Path(path.strip()).resolve()==(root/mapping[name]).resolve(),'unexpected compiler module resolution: '+name)
        require(name not in resolved,'duplicate compiled module: '+name)
        resolved[name]={'path':mapping[name],'sha256':inputs[mapping[name]]}
    required={'MLF.Entry.Emlf','MLF.ResourceExport','MLF.ResourceModules','MLF.ResourceProjection','MLF.ResourceModuleExport','MLF.PreparedCompiler','Bootstrap.CompilerCore','Bootstrap.X.Checked','Bootstrap.X.Check','Bootstrap.Parser'}
    require(required<=set(resolved),'actual compiler proof closure missing')
    shared_names={r['module']for r in shared['modules']}
    interfaces=upstream.audit_inferred_interfaces(log,{n:r for n,r in resolved.items()if n in shared_names})
    return resolved,interfaces

def authenticate_logs(root,receipt,mapping,inputs,shared,contract):
    commands=receipt.get('commands',[])
    require(len(commands)==3 and [r.get('label')for r in commands]==['host','supervisor','compile'] and all(r.get('status')=='terminal'and r.get('exit_code')==0 for r in commands),'actual compiler successful build commands missing')
    build=pathlib.Path(receipt.get('build_directory','')).resolve()
    require(build.is_dir()and str(build)==receipt.get('build_directory'),'actual build directory missing or noncanonical')
    roles=receipt.get('tool_roles',{})
    require(set(roles)=={'ghc','cc'} and set(roles.values())==set(receipt.get('tools',{})),'actual compiler tool roles differ')
    expected=command_recipe(root,build,shared,roles['ghc'],roles['cc'])
    require([(r.get('label'),r.get('argv'))for r in commands]==expected,'actual compiler command recipe differs')
    for row in commands:
        path=build/(row['label']+'.log')
        require(row.get('cwd')==str(pathlib.Path(root).resolve())and row.get('log')==str(path)and sha(path)==row.get('log_sha256'),'actual compiler build log changed')
    for path,wanted in receipt.get('tools',{}).items():require(sha(path)==wanted,'actual compiler tool changed')
    require(len(receipt.get('tools',{}))==2,'actual compiler tool inventory differs')
    require(receipt.get('binary')==str(build/'emlf')and sha(build/'emlf')==receipt.get('binary_sha256'),'actual compiler binary changed')
    actual=actual_interfaces(root,(build/'compile.log').read_text(),mapping,inputs,shared,upstream_module(root,contract))
    require(actual[0]==receipt.get('resolved_modules'),'actual compiled module evidence differs from GHC log')
    require(actual[1]==receipt.get('inferred_shared_interfaces'),'actual inferred-interface evidence differs from GHC log')

def command_recipe(root,build,shared,ghc,cc):
    root=pathlib.Path(root);build=pathlib.Path(build);objects=build/'objects'
    cobjects=[objects/'host.o',objects/'supervisor.o']
    rows=[]
    for label,source,obj in [('host','host/ghc/cbits/host.c',cobjects[0]),('supervisor','runtime/mlf_process_supervisor.c',cobjects[1])]:
        rows.append((label,[cc,'-O0','-std=c11','-I'+str(root/'runtime'),'-c',root/source,'-o',obj]))
    flags=['-v','-ddump-types','-XHaskell2010','-O0','-fpedantic-bottoms','-fno-state-hack','-Werror=incomplete-patterns','-Werror=incomplete-uni-patterns','-Wno-star-is-type','-Wno-overlapping-patterns','-Wno-deprecations','-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db','-hide-all-packages','-i']+['-i'+str(root/r)for r in shared['source_roots']]+['-odir',objects,'-hidir',objects,'-rtsopts=ignoreAll']
    for package in ['base','array','bytestring','text','containers','directory']:flags+=['-package',package]
    rows.append(('compile',[ghc,'--make','-j1','-fforce-recomp',*flags,root/'host/ghc/app/emlf/Main.hs',*cobjects,'-o',build/'emlf']))
    return [(label,list(map(str,argv)))for label,argv in rows]
