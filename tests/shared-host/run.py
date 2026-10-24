#!/usr/bin/env python3
"""Bounded direct-adapter qualification; does not build the compiler or install packages."""
import argparse, datetime, hashlib, json, os, pathlib, shutil, subprocess
p=argparse.ArgumentParser()
p.add_argument('ghc')
p.add_argument('--gc-root',type=pathlib.Path)
p.add_argument('--output',type=pathlib.Path)
a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[2]
os.chdir(root)
tests=root/'tests/shared-host'
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=(a.output or tests/'.runs'/stamp).resolve(); out.mkdir(parents=True,exist_ok=True)
steps=[]
def run(name,argv,expected=0,text=None,stdin=None,env=None,exact=None):
    result=subprocess.run([str(x) for x in argv],cwd=root,input=stdin,env=None if env is None else {**os.environ,**env},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
    output=result.stdout.decode('utf-8','replace')
    (out/(name+'.log')).write_text(output)
    ok=result.returncode==expected and (text is None or text in output) and (exact is None or exact==output)
    steps.append(dict(name=name,argv=[str(x) for x in argv],environment=env,returncode=result.returncode,expected_returncode=expected,expected_text=text,expected_exact=exact,passed=ok,log=name+'.log'))
    if not ok: raise RuntimeError(name+' failed:\n'+output)
    return output

def build(name,source,opt,extra=()):
    build=out/(name+'-'+opt); build.mkdir(exist_ok=True)
    binary=build/'probe'
    flags=['--make','-'+opt,'-XHaskell2010','-fpedantic-bottoms','-fno-state-hack','-dcore-lint','-rtsopts=ignoreAll','-package-env','-','-ihost/ghc','-itests/shared-host','-odir',build,'-hidir',build,'-Iruntime']
    run(name+'-'+opt+'-build',[a.ghc,*flags,tests/source,'host/ghc/cbits/host.c','runtime/mlf_process_supervisor.c',*extra,'-o',binary])
    return binary

error='Left (HostError "IO error: invalid UTF-8 input")'
invalid=os.fsencode(out)+b'/invalid-\xff'; os.mkdir(invalid)
link=out/'invalid-target-link'; os.symlink(b'invalid-\xff',os.fsencode(link))
regular=out/'regular'; regular.write_text('file\n')
fifo=out/'fifo'; os.mkfifo(fifo)
receipt={'started_utc':stamp,'ghc':str(pathlib.Path(a.ghc).resolve()),'platform':os.uname().sysname+' '+os.uname().machine,'steps':steps}
try:
    run('ghc-version',[a.ghc,'--version'])
    for opt in ['O0','O2']:
        b=build('contracts','ContractProbe.hs',opt)
        run('contracts-'+opt,[b],text='TOTAL 87 FAILED 0')
        b=build('numeric','NumericProbe.hs',opt,[tests/'NumericOracle.c'])
        run('numeric-'+opt,[b],text='TOTAL 590 FAILED 0')
        b=build('identity','IdentityProbe.hs',opt)
        run('identity-'+opt,[b],text='PASS actual Prelude.Bool')
        b=build('filesystem','FilesystemProbe.hs',opt)
        for label,path,expected in [('regular',regular,'True'),('directory',out,'False'),('fifo',fifo,'False'),('device','/dev/null','False'),('missing',out/'missing','False')]:
            run('file-exists-'+label+'-'+opt,[b,'file-exists',path],text=expected)
        for mode in ['canonical-discard','canonical-force']:
            run(mode+'-'+opt,[b,mode,link],text=error)
        run('canonical-valid-'+opt,[b,'canonical-discard',regular],text='Right ()')
        run('canonical-missing-'+opt,[b,'canonical-discard',out/'missing'],text='Left (HostError "IO error: canonical path failed")')
        run('contents-byte-line-'+opt,[b,'contents-byte-line'],text='Right 0',stdin=b'some input\n')
        run('executable-valid-'+opt,[b,'executable-discard'],text='Right ()')
        invalid_binary=invalid+b'/probe-'+opt.encode()
        shutil.copyfile(os.fsencode(b),invalid_binary); os.chmod(invalid_binary,0o755)
        run('executable-invalid-'+opt,[os.fsdecode(invalid_binary),'executable-discard'],text=error)
        for locale in ['C','C.UTF-8']:
            run('unicode-file-'+locale+'-'+opt,[b,'unicode-roundtrip',out],text='(4,True)',env={'LC_ALL':locale})
        b=build('arguments','ArgumentProbe.hs',opt)
        for locale in ['C','C.UTF-8']:
            run('argv-valid-'+locale+'-'+opt,[b,'😀'],text='Right 1',env={'LC_ALL':locale})
            run('argv-invalid-'+locale+'-'+opt,[b,os.fsdecode(b'\xff')],text=error,env={'LC_ALL':locale})
        b=build('literal-arguments','LiteralArgumentsProbe.hs',opt)
        run('literal-rts-arguments-'+opt,[b,'+RTS','-N2','-RTS'],exact='3\n["+RTS","-N2","-RTS"]\n')
        b=build('cancellation','CancellationProbe.hs',opt,[tests/'CancellationProbe.c','-threaded','-optl-Wl,--wrap=mlf_ghc_host','-optl-Wl,--wrap=free'])
        run('cancellation-'+opt,[b],text='returned C buffer freed=True')
        b=build('panic','PanicProbe.hs',opt)
        for locale in ['C','C.UTF-8']:
            run('panic-nested-'+locale+'-'+opt,[b,'nested'],expected=1,exact='Runtime: inner\n',env={'LC_ALL':locale})
            run('panic-unicode-'+locale+'-'+opt,[b,'unicode'],expected=1,exact='Runtime: 😀\n',env={'LC_ALL':locale})
    run('array-types-are-distinct',[a.ghc,'--make','-fno-code','-XHaskell2010','-package-env','-','-ihost/ghc','-itests/shared-host','-odir',out/'negative','-hidir',out/'negative',tests/'CrossArrayIdentity.hs'],expected=1,text="Couldn't match expected type")
    run('ownership-build',['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Iruntime',tests/'c-ownership-probe.c','runtime/mlf_process_supervisor.c','-o',out/'ownership'])
    run('ownership',[out/'ownership'],text='outstanding_adapter_allocations=0')
    if a.gc_root:
        run('native-oracle-build',['cc','-std=c11','-O0','-I'+str(a.gc_root/'include'),'-Iruntime',tests/'NativeFilesystemOracle.c',a.gc_root/'lib/libgc.a','-lgmp','-lm','-lpthread','-o',out/'native-oracle'])
        run('native-file-device',[out/'native-oracle','file-exists','/dev/null'],text='False')
        run('native-canonical-invalid',[out/'native-oracle','canonical',link],expected=1,text='Runtime: IO error: invalid UTF-8 input')
        run('native-contents-byte-line',[out/'native-oracle','contents-byte-line'],text='0',stdin=b'some input\n')
        for compiler in ['gcc','clang']:
            if shutil.which(compiler):
                binary=out/('native-environment-'+compiler)
                run('native-environment-build-'+compiler,[compiler,'-std=c11','-O0','-I'+str(a.gc_root/'include'),'-Iruntime',tests/'NativeEnvironmentOracle.c',a.gc_root/'lib/libgc.a','-lgmp','-lm','-lpthread','-o',binary])
                run('native-environment-name-'+compiler,[binary,'both-bottom'],expected=1,exact='Runtime: name\n')
                run('native-environment-nul-'+compiler,[binary,'nul-name'],expected=1,exact='Runtime: file path contains NUL\n')
    receipt['passed']=True
finally:
    sources=list((root/'host/ghc/MLF').rglob('*.hs'))+[root/'host/ghc/cbits/host.c']+list(tests.glob('*.hs'))+list(tests.glob('*.c'))+[tests/'run.py']+[root/'runtime'/x for x in ['mlf_runtime.c','mlf_system.h','mlf_process_binding.h','mlf_process_supervisor.c','mlf_completion.h']]
    receipt['sources']={str(x.relative_to(root)):hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(sources)}
    receipt.setdefault('passed',False)
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(out/'receipt.json')
