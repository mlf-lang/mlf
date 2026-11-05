#!/usr/bin/env python3
"""Fresh experimental host harness. Requires an authenticated official GHC build."""
import argparse, json, pathlib, sys
from common import *
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('root','producer','output'): p.add_argument('--'+flag,type=P,required=True)
    p.add_argument('--producer-receipt-sha256',required=True); a=p.parse_args()
    root=a.root.resolve(); producer=a.producer.resolve(); out=a.output.resolve()
    require(not out.exists(),'fresh output required'); require(not root.is_relative_to(out) and not out.is_relative_to(root),'build output must be outside source root')
    require(not out.is_relative_to(HERE),'build output must be outside experimental source directory')
    old=authenticate_producer(root,producer,a.producer_receipt_sha256)
    require(old['optimization']=='2','reference producer must use O2')
    # Retain the exact tested module-header-only factor reference.
    original=(root/'libraries/mlf-frontend/Bootstrap/Standalone.hs').read_bytes()
    reference=(HERE/'source/Bootstrap/StandaloneReference.hs').read_bytes()
    require(original.replace(b'module Bootstrap.Standalone',b'module Bootstrap.StandaloneReference',1)==reference,'reference no longer matches default normalizer')
    pins=source_pins(root); pins[str(P(sys.executable).resolve())]=sha(P(sys.executable).resolve())
    out.mkdir(); (out/'objects').mkdir(); rp=out/'receipt.json'
    r={'schema':'experimental-installed-build-1','status':'building','root':str(root),'producer':str(producer),'producer_receipt_sha256':a.producer_receipt_sha256,'pins':pins,'environment':environment(),'commands':[]}
    write(rp,r)
    try:
        cc=old['cc']['path']; ghc=old['ghc']['path']
        for name,source in [('host',root/'host/ghc/cbits/host.c'),('supervisor',root/'runtime/mlf_process_supervisor.c')]:
            cmd=[cc,'-O2','-std=c11','-I'+str(root/'runtime'),'-c',str(source),'-o',str(out/(name+'.o'))]
            r['commands'].append(cmd); write(rp,r); bounded(root,out/('build-'+name),cmd,seconds=60)
        includes=[HERE/'source',*sorted((root/'libraries').iterdir()),root/'bootstrap',root/'package',root/'host/ghc']
        cmd=[ghc,'--make','-j1','-XHaskell2010','-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db','-hide-all-packages','-O2','-fpedantic-bottoms','-fno-state-hack','-i']
        cmd+=['-i'+str(x) for x in includes if x.is_dir()]
        cmd+=['-odir',str(out/'objects'),'-hidir',str(out/'objects')]
        for package in ['base','array','bytestring','text','containers','directory','filepath']: cmd+=['-package',package]
        cmd += [str(HERE/'source/Harness.hs'),str(out/'host.o'),str(out/'supervisor.o'),'-o',str(out/'harness')]
        r['commands'].append(cmd); write(rp,r); bounded(root,out/'build-ghc',cmd,seconds=300)
        r.update(status='complete',harness=str(out/'harness'),harness_sha256=sha(out/'harness'),objects={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.suffix in ('.o','.hi')})
    except BaseException as e: r.update(status='failed',error=repr(e)); raise
    finally:
        try: verify_files(pins); authenticate_producer(root,producer,a.producer_receipt_sha256); r['postcheck']='PASS'
        except BaseException as e: r.update(status='failed',postcheck_error=repr(e)); write(rp,r); raise
        write(rp,r)
if __name__=='__main__': main()
