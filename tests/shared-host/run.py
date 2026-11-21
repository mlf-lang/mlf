#!/usr/bin/env python3
"""Bounded direct-adapter qualification; does not build the compiler or install packages."""
import argparse, datetime, functools, hashlib, json, os, pathlib, shutil, subprocess, sys

root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tools/testing'))
from receipt_selection import identity, select

PREFIX = 'shared-host/'
MODES = ('O0', 'O2')
LOCALES = ('C', 'C.UTF-8')
FILE_KINDS = ('regular', 'directory', 'fifo', 'device', 'missing')
CANONICAL_MODES = ('canonical-discard', 'canonical-force')


def labels(gc_enabled, compilers):
    host = (
        'contracts', 'integer-demand', 'string-compare', 'numeric', 'identity',
        *(f'file-exists-{kind}' for kind in FILE_KINDS), *CANONICAL_MODES,
        'canonical-valid', 'canonical-missing', 'contents-byte-line',
        'executable-valid', 'executable-invalid',
        *(f'unicode-file-{locale}' for locale in LOCALES),
        *(f'argv-{validity}-{locale}' for locale in LOCALES for validity in ('valid', 'invalid')),
        'literal-rts-arguments', 'cancellation',
        *(f'panic-{probe}-{locale}' for locale in LOCALES for probe in ('nested', 'unicode')),
    )
    result = [f'{label}-{opt}' for opt in MODES for label in host]
    result.extend(('array-types-are-distinct', 'digest-controls', 'ownership'))
    if gc_enabled:
        result.extend(('native-file-device', 'native-canonical-invalid', 'native-contents-byte-line'))
        result.extend(f'native-environment-{probe}-{compiler}'
                      for compiler in compilers for probe in ('name', 'nul'))
    return result

p=argparse.ArgumentParser()
p.add_argument('ghc', nargs='?')
p.add_argument('--framework-list', action='store_true')
p.add_argument('--gc-root',type=pathlib.Path)
p.add_argument('--output',type=pathlib.Path)
a=p.parse_args()
compilers = [name for name in ('gcc', 'clang') if a.gc_root and shutil.which(name)]
available = labels(a.gc_root is not None, compilers)
focused = select(PREFIX, available)
selected = [focused] if focused is not None else available
if a.framework_list:
    print(json.dumps([identity(PREFIX, label) for label in selected]))
    raise SystemExit(0)
if a.ghc is None:
    p.error('the GHC executable is required')
os.chdir(root)
tests=root/'tests/shared-host'
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=(a.output or tests/'.runs'/stamp).resolve(); out.mkdir(parents=True,exist_ok=True)
steps=[]
def run(name,argv,expected=0,text=None,stdin=None,env=None,exact=None,setup=False):
    if not setup and name not in selected:
        return None
    argv = [item() if callable(item) else item for item in argv]
    result=subprocess.run([str(x) for x in argv],cwd=root,input=stdin,env=None if env is None else {**os.environ,**env},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
    output=result.stdout.decode('utf-8','replace')
    (out/(name+'.log')).write_text(output)
    ok=result.returncode==expected and (text is None or text in output) and (exact is None or exact==output)
    steps.append(dict(name=name,argv=[str(x) for x in argv],environment=env,returncode=result.returncode,expected_returncode=expected,expected_text=text,expected_exact=exact,passed=ok,log=name+'.log'))
    if not ok: raise RuntimeError(name+' failed:\n'+output)
    return output

def build(name,source,opt,extra=()):
    @functools.cache
    def prepared():
        build=out/(name+'-'+opt); build.mkdir(exist_ok=True)
        binary=build/'probe'
        flags=['--make','-'+opt,'-XHaskell2010','-fpedantic-bottoms','-fno-state-hack','-dcore-lint','-rtsopts=ignoreAll','-package-env','-','-ihost/ghc','-itests/shared-host','-odir',build,'-hidir',build,'-Iruntime']
        run(name+'-'+opt+'-build',[a.ghc,*flags,tests/source,'host/ghc/cbits/host.c','runtime/mlf_process_supervisor.c',*extra,'-o',binary], setup=True)
        return binary
    return prepared


def copy_invalid(probe, destination):
    shutil.copyfile(os.fsencode(probe()), destination)
    os.chmod(destination, 0o755)
    return os.fsdecode(destination)

error='Left (HostError "IO error: invalid UTF-8 input")'
invalid=os.fsencode(out)+b'/invalid-\xff'; os.mkdir(invalid)
link=out/'invalid-target-link'; os.symlink(b'invalid-\xff',os.fsencode(link))
regular=out/'regular'; regular.write_text('file\n')
fifo=out/'fifo'; os.mkfifo(fifo)
receipt={'selected_cases':selected,'started_utc':stamp,'ghc':str(pathlib.Path(a.ghc).resolve()),'platform':os.uname().sysname+' '+os.uname().machine,'steps':steps}
try:
    if any(not name.startswith('native-') and name not in ('digest-controls', 'ownership') for name in selected):
        run('ghc-version',[a.ghc,'--version'],setup=True)
    for opt in MODES:
        b=build('contracts','ContractProbe.hs',opt)
        run('contracts-'+opt,[b],text='TOTAL 89 FAILED 0')
        b=build('integer-demand',root/'tools/shared/fixtures/IntDemandControls.hs',opt)
        run('integer-demand-'+opt,[b],text='PASS integer results, nested demand order')
        b=build('string-compare','StringCompareProbe.hs',opt)
        run('string-compare-'+opt,[b],text='PASS string comparison: 11664 codepoint pairs and 8 demand/error controls per host/primitive lane')
        b=build('numeric','NumericProbe.hs',opt,[tests/'NumericOracle.c'])
        run('numeric-'+opt,[b],text='TOTAL 722 FAILED 0')
        b=build('identity','IdentityProbe.hs',opt)
        run('identity-'+opt,[b],text='PASS actual Prelude.Bool')
        b=build('filesystem','FilesystemProbe.hs',opt)
        for label,path,expected in [('regular',regular,'True'),('directory',out,'False'),('fifo',fifo,'False'),('device','/dev/null','False'),('missing',out/'missing','False')]:
            run('file-exists-'+label+'-'+opt,[b,'file-exists',path],text=expected)
        for mode in CANONICAL_MODES:
            run(mode+'-'+opt,[b,mode,link],text=error)
        run('canonical-valid-'+opt,[b,'canonical-discard',regular],text='Right ()')
        run('canonical-missing-'+opt,[b,'canonical-discard',out/'missing'],text='Left (HostError "IO error: canonical path failed")')
        run('contents-byte-line-'+opt,[b,'contents-byte-line'],text='Right 0',stdin=b'some input\n')
        run('executable-valid-'+opt,[b,'executable-discard'],text='Right ()')
        invalid_binary=invalid+b'/probe-'+opt.encode()
        run('executable-invalid-'+opt,[lambda: copy_invalid(b, invalid_binary),'executable-discard'],text=error)
        for locale in LOCALES:
            run('unicode-file-'+locale+'-'+opt,[b,'unicode-roundtrip',out],text='(4,True)',env={'LC_ALL':locale})
        b=build('arguments','ArgumentProbe.hs',opt)
        for locale in LOCALES:
            run('argv-valid-'+locale+'-'+opt,[b,'😀'],text='Right 1',env={'LC_ALL':locale})
            run('argv-invalid-'+locale+'-'+opt,[b,os.fsdecode(b'\xff')],text=error,env={'LC_ALL':locale})
        b=build('literal-arguments','LiteralArgumentsProbe.hs',opt)
        run('literal-rts-arguments-'+opt,[b,'+RTS','-N2','-RTS'],exact='3\n["+RTS","-N2","-RTS"]\n')
        b=build('cancellation','CancellationProbe.hs',opt,[tests/'CancellationProbe.c','-threaded','-optl-Wl,--wrap=mlf_ghc_host','-optl-Wl,--wrap=free'])
        run('cancellation-'+opt,[b],text='returned C buffer freed=True')
        b=build('panic','PanicProbe.hs',opt)
        for locale in LOCALES:
            run('panic-nested-'+locale+'-'+opt,[b,'nested'],expected=1,exact='Runtime: inner\n',env={'LC_ALL':locale})
            run('panic-unicode-'+locale+'-'+opt,[b,'unicode'],expected=1,exact='Runtime: 😀\n',env={'LC_ALL':locale})
    run('array-types-are-distinct',[a.ghc,'--make','-fno-code','-XHaskell2010','-package-env','-','-ihost/ghc','-itests/shared-host','-odir',out/'negative','-hidir',out/'negative',tests/'CrossArrayIdentity.hs'],expected=1,text="Couldn't match expected type")
    run('digest-controls',[sys.executable,tests/'test-digest.py'])
    if 'ownership' in selected:
        run('ownership-build',['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Iruntime',tests/'c-ownership-probe.c','runtime/mlf_process_supervisor.c','-o',out/'ownership'],setup=True)
    run('ownership',[out/'ownership'],text='outstanding_adapter_allocations=0')
    if any(label in selected for label in ('native-file-device', 'native-canonical-invalid', 'native-contents-byte-line')):
        run('native-oracle-build',['cc','-std=c11','-O0','-I'+str(a.gc_root/'include'),'-Iruntime',tests/'NativeFilesystemOracle.c',a.gc_root/'lib/libgc.a','-lgmp','-lm','-lpthread','-o',out/'native-oracle'],setup=True)
        run('native-file-device',[out/'native-oracle','file-exists','/dev/null'],text='False')
        run('native-canonical-invalid',[out/'native-oracle','canonical',link],expected=1,text='Runtime: IO error: invalid UTF-8 input')
        run('native-contents-byte-line',[out/'native-oracle','contents-byte-line'],text='0',stdin=b'some input\n')
    for compiler in compilers:
        if any(f'native-environment-{probe}-{compiler}' in selected for probe in ('name', 'nul')):
            binary=out/('native-environment-'+compiler)
            run('native-environment-build-'+compiler,[compiler,'-std=c11','-O0','-I'+str(a.gc_root/'include'),'-Iruntime',tests/'NativeEnvironmentOracle.c',a.gc_root/'lib/libgc.a','-lgmp','-lm','-lpthread','-o',binary],setup=True)
            run('native-environment-name-'+compiler,[binary,'both-bottom'],expected=1,exact='Runtime: name\n')
            run('native-environment-nul-'+compiler,[binary,'nul-name'],expected=1,exact='Runtime: file path contains NUL\n')
    completed = [step['name'] for step in steps if step['name'] in available]
    if set(completed) != set(selected) or len(completed) != len(selected):
        raise RuntimeError('shared host observation set differs from its selected inventory')
    receipt['passed']=True
finally:
    sources=list((root/'host/ghc/MLF').rglob('*.hs'))+[root/'host/ghc/cbits/host.c',root/'tools/shared/fixtures/IntDemandControls.hs']+list(tests.glob('*.hs'))+list(tests.glob('*.c'))+[tests/'run.py',tests/'test-digest.py',root/'tools/testing/receipt_selection.py']+[root/'runtime'/x for x in ['mlf_runtime.c','mlf_system.h','mlf_build_runner_hash.h','mlf_process_binding.h','mlf_process_supervisor.c','mlf_completion.h']]
    receipt['sources']={str(x.relative_to(root)):hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(sources)}
    receipt.setdefault('passed',False)
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(out/'receipt.json')
