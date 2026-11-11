#!/usr/bin/env python3
"""Pinned toolchain SETUP only; requires separate coordinator admission.

The 12 GiB output cap is the original authenticated SETUP limit from
2aa3208:tools/performance/full-compiler/recovery-audit-20261110/toolchain-summary.json.
It does not change the separate diagnostic 4 GiB cap. Old artifacts are absent:
all archives, installed tools and controls are reconstructed in this new epoch.
"""
import datetime, hashlib, json, os, pathlib, shlex, subprocess, time
TC = pathlib.Path(__file__).resolve().parent
SOURCE = TC.parent / 'source'
CHECKPOINT = '305914c90e8fdff3a912faa6b93c08146273cf3e'
SOURCE_COMMIT = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
started = time.monotonic()
report = {'complete':False,'new_environment_epoch':True,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_commit':None,'checkpoint_commit':CHECKPOINT,'downloads':[],'validation':{},'toolchain_root':str(TC),'budget_source':'2aa3208cddf3a93795af554368513317875a9f94:tools/performance/full-compiler/recovery-audit-20261110/toolchain-summary.json'}
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def run(args, **kw):
    print('+',shlex.join(map(str,args)),flush=True)
    return subprocess.run(list(map(str,args)),check=True,**kw)
def capture(args): return run(args,stdout=subprocess.PIPE,text=True).stdout.strip()
def save():
    report['elapsed_seconds']=time.monotonic()-started
    (TC/'setup-result.json').write_text(json.dumps(report,indent=2)+'\n')
try:
    manifest=json.loads((TC/'toolchains.json').read_text())
    assert sha(TC/'toolchains.json')=='f99eb3a422a1fa0f3ff63b6ed9572a5a9a0aef69f27a51e4aebb120c4afcefbd'
    assert len(manifest['debian_packages'])==10
    assert sha(SOURCE/'tools/shared/resource_watchdog.py')=='5368803eb84dabc9dcefa89225b6ff56afd637e105f227bade15e40f9a5e923f'
    (TC/'tmp').mkdir(); os.environ['TMPDIR']=str(TC/'tmp')
    report['source_commit']=capture(['git','-C',SOURCE,'rev-parse','HEAD'])
    assert report['source_commit']==SOURCE_COMMIT
    assert capture(['git','-C',SOURCE,'status','--porcelain'])==''
    report['input_sha256']={str(p):sha(p) for p in [TC/'toolchains.json',TC/'install.py',TC/'run-setup.sh',TC/'prior-toolchain-summary.json',SOURCE/'tools/shared/resource_watchdog.py']}
    report['base_versions']={k:capture(v).splitlines()[0] for k,v in {'cc':['cc','--version'],'ld':['ld','--version'],'glibc':['ldd','--version'],'gmp':['pkg-config','--modversion','gmp']}.items()}
    assert report['base_versions']==manifest['base_versions'], 'base versions differ from checkpoint'
    report['uname']=capture(['uname','-a'])
    report['os_release']=pathlib.Path('/etc/os-release').read_text()
    report['lock_identity']={'device':pathlib.Path('/workspace/scratch/3f83e2ebe290/.astra-resource-locks/heavy.lock').stat().st_dev,'inode':pathlib.Path('/workspace/scratch/3f83e2ebe290/.astra-resource-locks/heavy.lock').stat().st_ino}
    save()
    for item in [manifest['ghc'],*manifest['debian_packages']]:
        path=TC/item['url'].rsplit('/',1)[1]
        run(['curl','-fL','--retry','2','--connect-timeout','20',item['url'],'-o',path])
        digest=sha(path)
        report['downloads'].append({'url':item['url'],'path':str(path),'sha256':digest,'expected_sha256':item['sha256'],'bytes':path.stat().st_size,'verified':digest==item['sha256']})
        save()
        if digest!=item['sha256']: raise RuntimeError('archive SHA256 mismatch: '+str(path))
        if path.suffix=='.deb': run(['dpkg-deb','-x',path,TC/'debian'])
    run(['tar','-xJf',TC/'ghc-9.14.1-x86_64-deb12-linux.tar.xz','-C',TC])
    ghcsrc=TC/'ghc-9.14.1-x86_64-unknown-linux'
    run(['./configure','--prefix='+str(TC/'ghc')],cwd=ghcsrc)
    run(['make','install','-j1'],cwd=ghcsrc)
    (TC/'bin').mkdir(); (TC/'pkgconfig').mkdir()
    (TC/'bin/clang').symlink_to('../debian/usr/lib/llvm-19/bin/clang')
    pc=(TC/'debian/usr/lib/x86_64-linux-gnu/pkgconfig/bdw-gc.pc').read_text()
    assert 'prefix=/usr\n' in pc
    (TC/'pkgconfig/bdw-gc.pc').write_text(pc.replace('prefix=/usr\n','prefix='+str(TC/'debian/usr')+'\n'))
    additions={'PATH':str(TC/'ghc/bin')+':'+str(TC/'bin'),'LD_LIBRARY_PATH':str(TC/'debian/usr/lib/x86_64-linux-gnu'),'LIBRARY_PATH':str(TC/'debian/usr/lib/x86_64-linux-gnu'),'PKG_CONFIG_PATH':str(TC/'pkgconfig')}
    lines=['# Source only after setup-result.json and bounded-receipt.json both report complete=true.','export TC='+shlex.quote(str(TC)),'export TMPDIR='+shlex.quote(str(TC/'tmp'))]
    for key,value in additions.items():
        lines.append('export '+key+'='+shlex.quote(value)+'"${'+key+':+:$'+key+'}"')
        os.environ[key]=value+(':'+os.environ[key] if os.environ.get(key) else '')
    (TC/'environment.sh').write_text('\n'.join(lines)+'\n')
    v=report['validation']
    v['ghc_version']=capture(['ghc','--numeric-version']); assert v['ghc_version']=='9.14.1'
    v['clang_version']=capture(['clang','--version']); assert v['clang_version'].splitlines()[0]==manifest['clang_version']
    v['bdw_gc_version']=capture(['pkg-config','--modversion','bdw-gc']); assert v['bdw_gc_version']=='8.2.8'
    v['gmp_version']=capture(['pkg-config','--modversion','gmp']); assert v['gmp_version']=='6.3.0'
    v['pkg_config_flags']=capture(['pkg-config','--cflags','--libs','bdw-gc','gmp'])
    (TC/'smoke.c').write_text('#include <gc.h>\n#include <gmp.h>\nint main(void) { GC_INIT(); void *p=GC_malloc(32); mpz_t n; mpz_init_set_ui(n,42); int r=(p==0 || mpz_cmp_ui(n,42)!=0); mpz_clear(n); return r; }\n')
    run(['clang',TC/'smoke.c','-o',TC/'smoke-c',*shlex.split(v['pkg_config_flags'])])
    run([TC/'smoke-c']); v['clang_gc_gmp_compile_link_run']='passed'
    (TC/'smoke.hs').write_text('main :: IO ()\nmain = putStrLn "pinned-ghc-smoke-ok"\n')
    run(['ghc','-v0',TC/'smoke.hs','-o',TC/'smoke-ghc'])
    assert capture([TC/'smoke-ghc'])=='pinned-ghc-smoke-ok'; v['ghc_compile_link_run']='passed'
    identities={}
    for executable in ['ghc','ghc-pkg','clang']:
        p=pathlib.Path(capture(['which',executable])); target=p.resolve()
        identities[executable]={'path':str(p),'resolved_path':str(target),'sha256':sha(target)}
    real_ghc=TC/'ghc/lib/ghc-9.14.1/bin/ghc-9.14.1'
    identities['ghc-ELF']={'path':str(real_ghc),'sha256':sha(real_ghc)}
    assert identities['ghc-ELF']['sha256']=='26628fcfe6f3f7176e5c8fc1766fe19b196e7922ff5d812e4c96bc146ae7dc92'
    assert identities['clang']['sha256']=='0a3c55936ac43954fbe4914e6e73b577ca9e35e75d89ef13d3e28c187f41ca1a'
    for pattern in ['libgc.so*','libLLVM.so*','libclang-cpp.so*']:
        for p in sorted((TC/'debian/usr/lib/x86_64-linux-gnu').glob(pattern)):
            if p.is_file() and not p.is_symlink(): identities[str(p.relative_to(TC))]={'path':str(p),'sha256':sha(p)}
    report['tool_identities']=identities
    report['environment_file']=str(TC/'environment.sh')
    assert capture(['git','-C',SOURCE,'status','--porcelain'])==''
    report['missing_prerequisites']=[]
    report['complete']=True
except BaseException as e:
    report['failure']=type(e).__name__+': '+str(e)
    raise
finally:
    save()
    print(json.dumps({k:v for k,v in report.items() if k not in ['os_release','downloads','tool_identities']},indent=2),flush=True)
