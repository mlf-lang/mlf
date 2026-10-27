#!/usr/bin/env python3
"""Frozen 14-source, reused-dependency benchmark. No target result reuse."""
import argparse, hashlib, json, os, platform, re, resource, shutil, subprocess, time
from pathlib import Path
W=Path(__file__).resolve().parents[1]
BASE=W.parent/'pr25-latest-benchmark-work-20261026'
S=W.parent/'pr25-latest-benchmark-fixed-20261026'
P=BASE/'setup/fixed-producer-2/producer'
C=BASE/'timed-mlf-1/run/cache'
TARGET=C/'3e93189eeda292c2d6643e45d6748249430cf98f69394ac9278b0b0bff1b650d'
def sha(p): return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
def save(p,j): p.write_text(json.dumps(j,indent=2)+'\n')
def pack(xs): return ''.join(str(len(x))+':'+x for x in xs)
def setup():
    assert not (W/'frozen.json').exists()
    old=json.loads((TARGET/'artifact.json').read_text())
    modules=json.loads((S/'libraries/mlf-crates/mlf-package.json').read_text())['library']['modules']
    assert len(modules)==14 and set(modules)==set(old['inputs']['sources'])
    target=W/'frozen-target';target.mkdir()
    for n,p in modules.items():
        src=S/'libraries/mlf-crates'/p
        assert sha(src)==old['inputs']['sources'][n]['sha256']
        dst=target/p;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    order=[]
    for line in (P/'shared-compile.log').read_text().splitlines():
        m=re.match(r'\[\s*\d+ of\s*\d+\] Compiling (\S+)',line)
        if m and m[1] in modules: order.append(m[1])
    assert len(order)==len(set(order))==14
    artifacts={}
    # Pin all completed library pairs plus builtin, including recursively embedded paths.
    for f in C.glob('*/artifact.json'):
        j=json.loads(f.read_text())
        if 'crate' not in j.get('inputs',{}):continue
        for rel,h in j['files'].items(): assert sha(f.parent/rel)==h,(f,rel)
        for rel in ['unit.mlfci','unit.mlfco','artifact.json']:
            artifacts[str(f.parent/rel)]=sha(f.parent/rel)
    prelude=C/'.queries/builtin-prelude'/old['inputs']['compiler']['sha256']/'unit'
    for ext in ['.mlfci','.mlfco']: artifacts[str(prelude)+ext]=sha(str(prelude)+ext)
    depobj=W/'ghc-dependencies';depobj.mkdir()
    targets={n.replace('.','/') for n in modules}
    ghcpins={}
    for f in (P/'objects').rglob('*'):
        if not f.is_file() or f.suffix not in ['.hi','.o']:continue
        rel=f.relative_to(P/'objects')
        if str(rel.with_suffix('')) in targets or rel.name in ['Main.hi','Main.o']:continue
        dst=depobj/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dst)
        ghcpins[str(rel)]=sha(dst)
    compiler=P/'bin/emlf'
    assert sha(compiler)=='ded7b23d144b817d95b297f3c6f6e18de2f91b656f3e5a6390f28dc9e17ef91a'
    ghc=BASE/'toolchain/ghc-install/bin/ghc-9.14.1'
    j=dict(format=1,variant='PR25 + approved local fixes',base_commit='aa11ffd318a2efa5be9805524710d0677eedb86f',
       input_patch_sha256='a09180199c536610c3f22bb4169d3ecc495531fd37dffb5d13fe9c6881d45855',
       modules={n:dict(path=str(target/p),sha256=sha(target/p)) for n,p in modules.items()},order=order,
       dependencies=old['inputs']['dependencies'],prelude=str(prelude),artifacts=artifacts,
       ghc_dependency_files=ghcpins,compiler=str(compiler),compiler_sha256=sha(compiler),ghc=str(ghc),ghc_sha256=sha(ghc),
       producer_receipt_sha256=sha(P/'receipt.json'),reference_artifacts={ext:sha(TARGET/('unit'+ext)) for ext in ['.mlfci','.mlfco']},
       host=dict(platform=platform.platform(),cpu=Path('/proc/cpuinfo').read_text(),memory=Path('/proc/meminfo').read_text(),cgroup=Path('/proc/self/cgroup').read_text()),
       boundary='Fresh process launch through exit. GHC compiles only 14 files to -O2 objects; MLF emits checked xMLF crate plus query cache. Dependency compilation and harness pre/post checks excluded; OS cache not flushed.',
       historical_user_numbers='Unverified source/command history; not used as fresh baseline.')
    save(W/'frozen.json',j)
def verify(j):
    for v in j['modules'].values(): assert sha(v['path'])==v['sha256'],v['path']
    for p,h in j['artifacts'].items(): assert sha(p)==h,p
    for p,h in j['ghc_dependency_files'].items(): assert sha(W/'ghc-dependencies'/p)==h,p
    assert sha(j['compiler'])==j['compiler_sha256']
    assert sha(j['ghc'])==j['ghc_sha256']
    assert sha(P/'receipt.json')==j['producer_receipt_sha256']
    producer=json.loads((P/'receipt.json').read_text())
    assert sha(S/'shared-sources.json')==producer['manifest_sha256']
    for field in ['resolved_modules','host_inputs']:
        for item in producer[field].values():assert sha(item['path'])==item['sha256']
    for item in [producer['toolchain']['actual_ghc'],producer['ghc_settings']]:assert sha(item['path'])==item['sha256']
    for rel,h in j['ghc_dependency_files'].items():assert producer['object_inputs']['objects/'+rel]==h
def run(a):
    j=json.loads((W/'frozen.json').read_text());verify(j)
    out=W/'runs'/a.label;assert not out.exists();out.mkdir(parents=True)
    shutil.copy2(__file__,out/'recipe.py')
    env={**os.environ,'GHC_ENVIRONMENT':'-','GHCRTS':'','LC_ALL':'C.UTF-8','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MAKEFLAGS':'-j1'}
    if a.rts:env['GHCRTS']=a.rts
    if a.side=='ghc':
        depdir=W/'ghc-dependencies';deppins=j['ghc_dependency_files']
        if a.plain_o2:
            plain=json.loads((W/'plain-o2-setup/receipt.json').read_text());assert plain['complete']
            depdir=Path(plain['reusable_directory']);deppins=plain['reusable_dependency_files']
            for rel,h in deppins.items():assert sha(depdir/rel)==h
        obj=out/'objects';shutil.copytree(depdir,obj)
        argv=[j['ghc'],'--make','-no-link','-j1','-O2','-fpedantic-bottoms','-fno-state-hack','-XHaskell2010',
              '-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db','-hide-all-packages',
              '-i','-i'+str(W/'frozen-target')]
        source_roots=json.loads((S/'shared-sources.json').read_text())['source_roots']
        argv += ['-i'+str(S/root) for root in source_roots]
        argv += ['-odir',str(obj),'-hidir',str(obj)]
        for p in ['base','array','bytestring','text','containers','directory']:argv+=['-package',p]
        if a.ghc_phases:argv+=['-v','-ddump-timings']
        argv += [j['modules'][n]['path'] for n in j['order']]
        if a.plain_o2:argv=[x for x in argv if x not in ['-fpedantic-bottoms','-fno-state-hack']]
    else:
        cache=out/'queries';assert not cache.exists()
        spec=pack(['MLF-CRATE-1','mlf-crates/0.3.0/library','','false',
              pack([pack([n,v['path']]) for n,v in j['modules'].items()]),
              pack([x['path'] for x in j['dependencies']]),str(cache),j['prelude']])
        (out/'crate.spec').write_text(spec)
        argv=[a.compiler or j['compiler'],'--compile-crate',str(out/'crate.spec'),'-o',str(out/'unit')]
        if a.rts:env['GHCRTS']=a.rts
    receipt=dict(complete=False,label=a.label,side=a.side,argv=argv,cwd=str(out),
          compiler_sha256=sha(argv[0]),environment={k:env.get(k) for k in ['GHCRTS','GHC_ENVIRONMENT','LC_ALL','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MAKEFLAGS']},
          started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),frozen_sha256=sha(W/'frozen.json'),ghc_phases=a.ghc_phases,
          recipe_sha256=sha(__file__))
    if a.side=='ghc':receipt.update(plain_o2=a.plain_o2,dependency_directory=str(depdir),dependency_file_hashes=deppins)
    save(out/'receipt.json',receipt)
    with (out/'stdout').open('wb') as stdout,(out/'stderr').open('wb') as stderr:
        usage0=resource.getrusage(resource.RUSAGE_CHILDREN)
        t=time.perf_counter_ns();p=subprocess.run(argv,cwd=out,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr);end=time.perf_counter_ns()
        usage1=resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt.update(exit_code=p.returncode,wall_seconds=(end-t)/1e9,
        child_user_seconds=usage1.ru_utime-usage0.ru_utime,child_system_seconds=usage1.ru_stime-usage0.ru_stime,
        max_individual_child_rss_bytes=usage1.ru_maxrss*1024,
        voluntary_context_switches=usage1.ru_nvcsw-usage0.ru_nvcsw,involuntary_context_switches=usage1.ru_nivcsw-usage0.ru_nivcsw)
    save(out/'receipt.json',receipt)
    assert p.returncode==0,(out/'stderr').read_text()[-3000:]
    if a.side=='ghc':
        compiled=re.findall(r'^\[\s*\d+ of\s*\d+\] Compiling (\S+)',(out/'stderr').read_text()+(out/'stdout').read_text(),re.M)
        assert len(compiled)==14 and set(compiled)==set(j['order']),compiled
        receipt['compiled_modules']=compiled
        receipt['output_artifacts']={n:{ext:sha(out/'objects'/(n.replace('.','/')+ext)) for ext in ['.hi','.o']} for n in j['order']}
        for rel,h in deppins.items():
            assert sha(out/'objects'/rel)==h,rel
            assert sha(depdir/rel)==h,rel
        receipt['dependency_objects_unchanged']=True
    else:
        report=json.loads((out/'unit.queries').read_text())
        assert report['inferred_groups']==544 and report['reused_groups']==0,report.keys()
        receipt['query_report']=report
        receipt['output_artifacts']={ext:sha(out/('unit'+ext)) for ext in ['.mlfci','.mlfco']}
        receipt['byte_identical_to_prior']=receipt['output_artifacts']==j['reference_artifacts']
        assert receipt['byte_identical_to_prior'],'checked crate artifact changed'
        # Persist complete inventory; assert cold counters using actual report schema.
        receipt['target_cache_initially_absent']=True
    assert sha(argv[0])==receipt['compiler_sha256']
    verify(j);receipt.update(complete=True,immutable_inputs_verified_after=True)
    save(out/'receipt.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k in ['label','side','complete','wall_seconds','byte_identical_to_prior']},indent=2),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('side',choices=['setup','ghc','mlf']);p.add_argument('label',nargs='?');p.add_argument('--compiler');p.add_argument('--rts');p.add_argument('--ghc-phases',action='store_true');p.add_argument('--plain-o2',action='store_true');a=p.parse_args()
    setup() if a.side=='setup' else run(a)
