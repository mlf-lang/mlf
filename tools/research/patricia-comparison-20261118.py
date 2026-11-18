import hashlib, json, os, pathlib, subprocess, types
ROOT=pathlib.Path.cwd(); OUT=ROOT/'evidence'; OUT.mkdir(exist_ok=True)
def load(path):
    m=types.ModuleType(path.stem);m.__file__=str(path);exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
pins={'old':'d8325d909c249fd82d4ad6173d44d8818cc6f8bf','new':'ee495d5783fca3c26a3c0e659ebeac1bab76a37d'}
BASE={'old':'old','new':'new','old_swap':'old','new_swap':'new'}
DONOR={'old_swap':'new','new_swap':'old'}
surface='libraries/mlf-frontend/Bootstrap/Surface.hs'
literal='bootstrap/MLF/BuiltinPreludeData.hs'
expected_identity={'old_swap':'builtin-source-v1:b43c5ddf9224142d296b984833de88528272e318f53fa6203614cd9576c7abae','new_swap':'builtin-source-v1:3e12091e64154a07bfd2e0423383cdcedcd509f980c656ca5352a7b481faaa21'}
surf_blobs={'old':'3e8082684587d25915d7f209bbf74d32e7c3dcc7','new':'a11262a585792e391d02e379e11e233af627fff0'}
roots={k:(ROOT/k).resolve() for k in BASE}
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
H=load(roots['new']/'tools/performance/a1-private-index/helper.py')
limits=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,host_available_floor_bytes=3*1024**3,process_tree_rss_bytes=5*1024**3,max_work_bytes=2*1024**3,wall_seconds=600)
record={'complete':False,'scope':'type-only bounded same-runner diagnosis; not semantic or speed qualification','pins':pins,'limits':limits,'legs':[],'host':H.host()}
def save(): (OUT/'comparison.json').write_text(json.dumps(record,indent=2)+'\n')
save()
fixture=None
for label,root in roots.items():
    head=git(root,'rev-parse','HEAD');base=pins[BASE[label]]
    if label in DONOR:
        assert git(root,'show','-s','--format=%P',head)==base
        assert git(root,'diff','--name-only',base,head).splitlines()==sorted([surface,literal])
        assert git(root,'rev-parse','HEAD:'+surface)==surf_blobs[DONOR[label]]
    else:assert head==base and git(root,'rev-parse','HEAD:'+surface)==surf_blobs[label]
    assert git(root,'status','--porcelain','--untracked-files=no')==''
    assert not git(root,'diff','--name-only','HEAD')
    producer=root/'.mlf-build/shared-ghc'
    H.authenticate(producer,root)
    if label in DONOR:
        fresh=OUT/(label+'-generated-literal.hs')
        gr=json.loads((OUT/(label+'-generation-receipt.json')).read_text())
        vr=json.loads((producer/'builtin-verification'/'receipt.json').read_text())
        assert gr['complete'] and gr['generation_succeeded'] and gr['immutable_inputs_verified_after']
        assert gr['source_identity']==vr['source_identity']==expected_identity[label]
        assert vr['complete'] and vr['exact_regeneration'] and vr['candidate_verified']
        assert fresh.read_bytes()==(root/literal).read_bytes() and gr['commands'][0]['stdout']['sha256']==sha(fresh)
        assert vr['canonical']['sha256']==vr['commands'][1]['stdout']['sha256']==sha(fresh)
    text,wanted,_,_=load(root/'tools/performance/patricia/run_native.py').fixture('rank-views')
    if fixture is None: fixture=text
    assert fixture==text
    record[label]={'binary_sha256':sha(producer/'bin/emlf'),'receipt_sha256':sha(producer/'receipt.json')}
entry=OUT/'Main.hs';entry.write_text(fixture);record['fixture_sha256']=sha(entry);save()

# No compiler or fixture changes. Both control legs must reproduce before observation.
import inspect,time,resource
ref_bins={'old':'d90ecca441c0c1a00c224639b335124ec4802d97f99e7d44eea9ccce3a715c8d','new':'8845fbb4729e555157c2cd3ca45d2981741bf8308bbdbef6ece74c85a5d90245'}
assert record['fixture_sha256']=='e7bc0d6bdd6ec6ac1a7d9b2cd6f71cb398c430f3029c870057d096efff2aaa82'
locked_inputs={"old":{"object_inputs":"3d4e55562e15482eb19265820d648d8f7fe261e4700c585bdd4fe02228d7b779","resolved_modules":"dc980d404188953009eba29c04a7fa856be709708e04923fcfd6416e73da7ae8","resolved_host_modules":"f6bb370236c702e1282baca2ada46b5944df522bb1eca16a28ca5f4980d35d7f","configuration_inputs":"ec04b1382d64c5b43ffa6ffd2b663e1d94e216006526695fef1d28869cb36501","shared_inputs":"1c1b747c167c5936b8856e89d0280789622d4538173a93306464a2ae04b8d2f0","host_inputs":"a8a09986e2e01b941741151e12e7a2cbf8665996bb6d53f78561b556cfa28e04","flags":"50e344ad68ebb24127b0b8e73be203817bc964f033bcf3fbcf1d43afe166258f","ghc":"8057b580fb047c5302ab1291596cf79a30e906f21c4cd223ea2d5e7c71ada348","cc":"f0eaee113e92135d35342b0994c6a039894e5da8991860c3f7c11c6202c4afa3","installed_dependencies":"6588b2ecaea0410f237fd3a23d4a78073940ca89304ea83e1596ff16ee6b9572","toolchain":"ac75b1bd6f94190ba6e09c5d687876f57d229bf992a3678fe2104e311814ddfa"},"new":{"object_inputs":"26215720f9596e5462c611c0254498fd8c1a4ede4b6b9281666c28d40c41243a","resolved_modules":"2a65c9034307623cc7d411925648209d56021b9657e01341b9768259b6f46a6a","resolved_host_modules":"7d6328f49a88fc532323ac3be760d3ff3fa37bcee9fb50bd395650d664de8b1e","configuration_inputs":"d14ae947e683961893ca57020002c71042fa797a69dd1a63eb890994aa5179cd","shared_inputs":"36c769215036a3f72d32d82b54193304a291930b2e967dff63cbc10509927bdb","host_inputs":"ea210294596583ac33ff4dbedb5d5e82a0c4c30d7a48cf9d31a962f2bd9c3694","flags":"0f373f3be1a95bf7d1a0a00fcd9e8dc6be3435188249f2f67ad23208db703e8c","ghc":"8057b580fb047c5302ab1291596cf79a30e906f21c4cd223ea2d5e7c71ada348","cc":"f0eaee113e92135d35342b0994c6a039894e5da8991860c3f7c11c6202c4afa3","installed_dependencies":"6588b2ecaea0410f237fd3a23d4a78073940ca89304ea83e1596ff16ee6b9572","toolchain":"ac75b1bd6f94190ba6e09c5d687876f57d229bf992a3678fe2104e311814ddfa"}}

import re
# This is an independent new-host experiment, not the historic executable cohort.
def canon(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
def file_sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
current_epoch_files={'/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2': '5fc0940888e9d2e1a00e66d6b1a559c36364ee867683652e1074fa576952cc3f', '/usr/lib/x86_64-linux-gnu/libc.so.6': '755a371e86cc9f564ab54f66140747700fb0a103f698f659f2060f707897e09a', '/usr/lib/x86_64-linux-gnu/libm.so.6': '5dcc4d25466e29ca390ed6fabb371c69b65dff6fa4e91c34561057a020d6994a'}
def runtime_manifest(exe):
    # Use the trusted, just-built program and clean loader environment. Identify ELF interpreter and ELF runtime closure.
    if any(os.environ.get(k) for k in ('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH')):raise RuntimeError('nonempty loader override')
    env=dict(os.environ,LC_ALL='C'); listing=subprocess.check_output(['/usr/bin/ldd',str(exe)],text=True,env=env,timeout=15)
    if 'not found' in listing:raise RuntimeError('unresolved dependency')
    files={}
    for line in listing.splitlines():
        line=line.strip()
        if not line or line.startswith('linux-vdso.'):continue
        v=line.split('=>',1)[-1].strip().split(' (0x',1)[0]
        if not v.startswith('/'):raise RuntimeError('unexpected ldd row')
        p=pathlib.Path(v).resolve(strict=True)
        files[str(p)]={'sha256':file_sha(p),'bytes':p.stat().st_size}
    ph=subprocess.check_output(['/usr/bin/readelf','-lW',str(exe)],text=True,env=env,timeout=15)
    ld=re.search(r'Requesting program interpreter: ([^]]+)\]',ph)
    if not ld or str(pathlib.Path(ld.group(1)).resolve(strict=True)) not in files:raise RuntimeError('missing interpreter')
    for path,expected in current_epoch_files.items():
        if file_sha(path)!=expected:raise RuntimeError('frozen same-host epoch file differs: '+path)
    return {'binary_sha256':file_sha(exe),'interpreter':str(pathlib.Path(ld.group(1)).resolve()),'loaded_elf_dependencies':files}
cohort={'epoch':'44392609307 producer-toolchain cohort, independent; never substitute for historical runtime identity','image':os.environ.get('ImageVersion'),'run_id':os.environ.get('GITHUB_RUN_ID'),'members':{}}
if not cohort['image'] or not cohort['run_id']:raise RuntimeError('missing environment identity')
expected_epoch_native_elf={'old': 'fbc253d428204532bff22c36c1361969c8f4e73174bf15945127c6ca030e1467', 'new': '50892889234f62276128a542a718f0c74ce7cdf9f06cd62fa094adf18faa0677'}
for l,r in roots.items():
    receipt=json.loads((r/'.mlf-build/shared-ghc/receipt.json').read_text())
    actual={k:canon(receipt[k]) for k in locked_inputs[BASE[l]]}
    if l not in DONOR:
        if record[l]['binary_sha256']!=expected_epoch_native_elf[l]:raise RuntimeError('new epoch native executable differs: '+l)
        if actual!=locked_inputs[l]:raise RuntimeError('pinned native intermediate mismatch: '+l)
    else:
        base=BASE[l];donor=DONOR[l];baseline=json.loads((roots[base]/'.mlf-build/shared-ghc/receipt.json').read_text())
        donor_receipt=json.loads((roots[donor]/'.mlf-build/shared-ghc/receipt.json').read_text())
        def normalized(x,root):return json.loads(json.dumps(x,sort_keys=True).replace(str(root)+'/', '<worktree>/'))
        for k in ['resolved_modules','shared_inputs','configuration_inputs','resolved_host_modules','host_inputs','flags','ghc','cc','installed_dependencies','toolchain']:
            bx=normalized(baseline[k],roots[base]);vx=normalized(receipt[k],r)
            if k in ('resolved_modules','shared_inputs'):
                bx['MLF.BuiltinPreludeData']['sha256']=sha(r/literal)
                bx['Bootstrap.Surface']=normalized(donor_receipt[k]['Bootstrap.Surface'],roots[donor])
            if bx!=vx:raise RuntimeError('hybrid admitted inputs mismatch '+l+' '+k)
        if set(receipt['object_inputs'])!=set(baseline['object_inputs']):raise RuntimeError('object membership mismatch')
    record[l]['git_head']=git(r,'rev-parse','HEAD')
    ex=r/'.mlf-build/shared-ghc/bin/emlf'
    m=runtime_manifest(ex)
    if m['binary_sha256']!=record[l]['binary_sha256'] or m['binary_sha256']!=receipt['outputs']['emlf']['sha256']:raise RuntimeError('unverified executable')
    cohort['members'][l]={'runtime':m,'package_database_sha256':receipt['package_database_sha256'],'receipt_sha256':record[l]['receipt_sha256'],'intermediate_sha256':actual}
a,b=cohort['members']['old'],cohort['members']['new']
if a['runtime']['loaded_elf_dependencies']!=b['runtime']['loaded_elf_dependencies'] or a['package_database_sha256']!=b['package_database_sha256'] or a['runtime']['binary_sha256']==b['runtime']['binary_sha256']:raise RuntimeError('mismatched shared runtime or non-distinct producers')
for member in cohort['members'].values():
    if member['runtime']['loaded_elf_dependencies']!=a['runtime']['loaded_elf_dependencies'] or member['package_database_sha256']!=a['package_database_sha256']:raise RuntimeError('inconsistent 4-build runtime')
manifest=OUT/'new-epoch-cohort.json';manifest.write_text(json.dumps(cohort,indent=2)+'\n');frozen=sha(manifest)
def verify_frozen(l):
    if sha(manifest)!=frozen:raise RuntimeError('mutated manifest')
    ex=roots[l]/'.mlf-build/shared-ghc/bin/emlf'
    if runtime_manifest(ex)!=cohort['members'][l]['runtime'] or sha(roots[l]/'.mlf-build/shared-ghc/receipt.json')!=cohort['members'][l]['receipt_sha256']:raise RuntimeError('changed executable, dependency or receipt')
record['epoch_manifest_sha256']=frozen;save()

helper=roots['new']/'tools/performance/a1-private-index/helper.py'
assert subprocess.check_output(['git','hash-object',str(helper)],text=True).strip()=='1feffe5d9f360a8fbb9f27868985d4a1a97ab010'

record['scope']='Independent ordinary 6GiB reciprocal historical Surface + necessary freshly generated canonical literal swaps. Binary cohort is not historical ELF. No compiler probes or RSS/time speed conclusions.'
record['schedule']=['old','new','new_swap','old_swap']
smoke=OUT/'SurfaceSmoke.hs';smoke.write_text('''-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude #-}
module Main (main) where {
import MLF.Primitive;
identityInt :: Int -> Int; identityInt x = x;
choose :: Bool -> Int; choose flag = case flag of { True -> identityInt 7; False -> identityInt 0 };
main :: IO (); main = printInt (choose True)
}
''');record['smoke_fixture_sha256']=sha(smoke);record['smoke']=[]
for i,label in enumerate(record['schedule']):
    verify_frozen(label);r=roots[label];dest=OUT/('leg-'+str(i)+'-'+label)
    if label in DONOR:
        sd=OUT/('smoke-'+label)
        try:H.Runner(OUT,dict(limits,wall_seconds=45)).run([r/'.mlf-build/shared-ghc/bin/emlf','--run',smoke],r,sd,expected_exit=0)
        except RuntimeError as err:record['last_runner_exception']=repr(err)
        verify_frozen(label);rec=sd/'command.json'
        ok_smoke=False
        if rec.exists():
            v=json.loads(rec.read_text());ok_smoke=bool(v.get('complete') and v.get('exit_code')==0 and v.get('reason') is None and v.get('terminal_live_descendants')==[] and (sd/'stdout').read_bytes()==b'7\n' and not (sd/'stderr').read_bytes())
        record['smoke'].append({'label':label,'passed':ok_smoke});save()
        if not ok_smoke:record['stop_reason']='hybrid semantic smoke failed';save();break
    expected=251 if BASE[label]=='new' else 0
    try:H.Runner(OUT,limits).run([r/'.mlf-build/shared-ghc/bin/emlf','-i',r/'libraries/mlf-foundation','--type',entry],r,dest,expected_exit=expected)
    except RuntimeError as err:record['last_runner_exception']=repr(err)
    verify_frozen(label)
    if not (dest/'command.json').exists():record['stop_reason']='missing receipt';save();break
    j=json.loads((dest/'command.json').read_text());ec=j.get('exit_code')
    ok=(ec==0 and (dest/'stdout').read_bytes()==b'IO ()\n' and not (dest/'stderr').read_bytes())
    oom=(ec==251 and (dest/'stderr').read_bytes()==b'emlf: out of memory\n' and not (dest/'stdout').read_bytes())
    accept=bool((ok or oom) and j.get('reason') is None and j.get('terminal_live_descendants')==[] and j.get('limits')==limits and j.get('logs') and all(sha(pathlib.Path(k))==v for k,v in j['logs'].items()))
    if i<2:accept=accept and bool(j.get('complete')) and ec==expected
    record['legs'].append({'label':label,'exit':ec,'output':'IO ()' if ok else 'emlf: out of memory' if oom else 'unexpected','accepted':accept,'rss':j.get('max_individual_child_rss_bytes')});save()
    if not accept:record['stop_reason']='required baseline, outcome or safety rejected';save();break
record['complete']=len(record['legs'])==4 and all(x['accepted'] for x in record['legs'])
save()
