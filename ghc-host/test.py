#!/usr/bin/env python3
"""Focused converter/adapter tests; existing repository campaigns are separate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build-dir', type=Path, default=ROOT/'.mlf-build/ghc-host')
parser.add_argument('--optimization', choices=['0','2'], default='0')
parser.add_argument('--native-reference', type=Path, help='Native compiler built from the same pinned implementation sources')
options = parser.parse_args()
BUILD = options.build_dir.resolve()
OUT = BUILD/('focused-tests-O'+options.optimization)
OUT.mkdir(parents=True, exist_ok=True)
observations = []


def run(label, args, expected=None, status=0):
    result = subprocess.run(list(map(str,args)), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    (OUT/(label+'.stdout')).write_bytes(result.stdout)
    (OUT/(label+'.stderr')).write_bytes(result.stderr)
    observations.append({'label':label,'command':list(map(str,args)),'status':result.returncode,
                         'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),
                         'stderr_sha256':hashlib.sha256(result.stderr).hexdigest()})
    if result.returncode!=status or (expected is not None and (result.stdout!=expected or result.stderr)):
        raise RuntimeError(label+' failed; see '+str(OUT))
    print('PASS',label,flush=True)
    return result.stdout


def ghc(main, binary):
    return ['ghc','-O'+options.optimization,'-w','-ighc-host/runtime','-i'+str(BUILD/'generated'),'-i'+str(OUT),
            '-outputdir',OUT/'objects',main,'ghc-host/cbits/host.c','runtime/mlf_process_supervisor.c',
            '-Iruntime','-o',binary]


def main():
    evidence = {'complete':False,'optimization':options.optimization,'observations':observations,
                'inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                          for folder in ['ghc-host','runtime'] for p in (ROOT/folder).rglob('*')
                          if p.is_file() and '__pycache__' not in p.parts},
                'compiler_sha256':hashlib.sha256((BUILD/'bin/emlf').read_bytes()).hexdigest(),
                'converter_sha256':hashlib.sha256((BUILD/'mlf-to-haskell').read_bytes()).hexdigest(),
                'ghc':subprocess.check_output(['ghc','--numeric-version'],text=True).strip()}
    (OUT/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')
    for name,other in [('CycleA','CycleB'),('CycleB','CycleA')]:
        (OUT/(name+'.emlf')).write_text('module '+name+' (module '+other+') where\nimport '+other+'\n')
    cycle=OUT/'cycle.tsv'
    cycle.write_text(''.join('\t'.join([str(OUT/(name+'.emlf')),str(OUT/(name+'.hs')),name])+'\n' for name in ['CycleA','CycleB']))
    run('cyclic-reexports-rejected',[BUILD/'mlf-to-haskell','--batch',cycle],status=1)
    assert b'implementation dialect requires acyclic modules' in (OUT/'cyclic-reexports-rejected.stderr').read_bytes()
    run('host-laws-build',ghc(ROOT/'ghc-host/tests/HostLaws.hs',OUT/'host-laws'))
    run('host-laws', [OUT/'host-laws'], b'Host adapter laws passed.\n')
    generated=OUT/'Implementation.hs'
    run('translate',[BUILD/'mlf-to-haskell','ghc-host/tests/Implementation.emlf',generated,'Implementation'])
    first=generated.read_bytes()
    run('translate-repeat',[BUILD/'mlf-to-haskell','ghc-host/tests/Implementation.emlf',generated,'Implementation'])
    assert generated.read_bytes()==first, 'nondeterministic generation'
    wrapper=OUT/'Main.hs'
    wrapper.write_text('module Main where\nimport MLF.Host.IO (runEntry)\nimport qualified Implementation\nmain = runEntry Implementation.v_main\n')
    run('implementation-build',ghc(wrapper,OUT/'implementation'))
    expected=(ROOT/'ghc-host/tests/Implementation.stdout').read_bytes()
    run('implementation-ghc',[OUT/'implementation'],expected)
    run('implementation-mlf-interpreter',[BUILD/'bin/emlf','-i','libraries/mlf-foundation','--run','ghc-host/tests/Implementation.emlf'],expected)
    if options.native_reference:
        reference=options.native_reference.resolve()
        evidence['native_reference']={'path':str(reference),'sha256':hashlib.sha256(reference.read_bytes()).hexdigest()}
        run('implementation-native-interpreter',[reference,'--run','ghc-host/tests/Implementation.emlf'],expected)
        generated_ir=run('implementation-h0-llvm',[BUILD/'bin/emlf','--emit-llvm-gc','ghc-host/tests/Implementation.emlf'])
        reference_ir=run('implementation-native-llvm',[reference,'--emit-llvm-gc','ghc-host/tests/Implementation.emlf'])
        assert generated_ir==reference_ir, 'H0/native LLVM differential mismatch'
        program=OUT/'implementation.ll'
        program.write_bytes(generated_ir)
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gmp'],text=True))
        gc=os.environ.get('MLF_GC_PREFIX')
        flags+=['-I'+gc+'/include',gc+'/lib/libgc.a'] if gc else shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','bdw-gc'],text=True))
        flags+=['-lm']+(['-Wl,-stack_size,0x10000000'] if sys.platform=='darwin' else [])
        run('implementation-native-link',['clang','-O2','-Wno-override-module',program,ROOT/'runtime/mlf_runtime.c',*flags,'-o',OUT/'implementation-native'])
        run('implementation-native',[OUT/'implementation-native'],expected)
        assert hashlib.sha256(reference.read_bytes()).hexdigest()==evidence['native_reference']['sha256']
    for relative, digest in evidence['inputs'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest, relative+' changed'
    evidence['complete']=True
    (OUT/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')


if __name__=='__main__':
    main()
