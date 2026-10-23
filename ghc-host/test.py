#!/usr/bin/env python3
"""Focused converter/adapter tests; existing repository campaigns are separate."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT/'.mlf-build/ghc-host'
OUT = BUILD/'focused-tests'
OUT.mkdir(parents=True, exist_ok=True)
observations = []


def run(label, args, expected=None):
    result = subprocess.run(list(map(str,args)), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    (OUT/(label+'.stdout')).write_bytes(result.stdout)
    (OUT/(label+'.stderr')).write_bytes(result.stderr)
    observations.append({'label':label,'command':list(map(str,args)),'status':result.returncode,
                         'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),
                         'stderr_sha256':hashlib.sha256(result.stderr).hexdigest()})
    if result.returncode or (expected is not None and (result.stdout!=expected or result.stderr)):
        raise RuntimeError(label+' failed; see '+str(OUT))
    print('PASS',label,flush=True)
    return result.stdout


def ghc(main, binary):
    return ['ghc','-O0','-w','-ighc-host/runtime','-i'+str(BUILD/'generated'),'-i'+str(OUT),
            '-outputdir',OUT/'objects',main,'ghc-host/cbits/host.c','runtime/mlf_process_supervisor.c',
            '-Iruntime','-o',binary]


def main():
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
    (OUT/'result.json').write_text(json.dumps({'complete':True,'observations':observations},indent=2)+'\n')


if __name__=='__main__':
    main()
