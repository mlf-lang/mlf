#!/usr/bin/env python3
"""Small final-tree check-only smoke; native qualification is separately documented."""
import argparse, json, pathlib, subprocess, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from common import *
def main():
    p=argparse.ArgumentParser(); p.add_argument('--build-receipt',type=P,required=True); p.add_argument('--build-receipt-sha256',required=True); p.add_argument('--output',type=P,required=True); a=p.parse_args()
    out=a.output.resolve(); require(not out.exists(),'fresh output required'); out.mkdir()
    common=['--build-receipt',str(a.build_receipt),'--build-receipt-sha256',a.build_receipt_sha256]
    rows=[]
    def run(operation,name,source=None,manifest=None,expected=None):
        cmd=[sys.executable,str(HERE/'snapshot.py'),operation,*common,'--output',str(out/name)]
        if source: cmd+=['--source',str(source)]
        if manifest: cmd+=['--manifest',str(manifest),'--manifest-sha256',expected]
        # Each controller owns its bounded child and failure cleanup. No timeout races with its watchdog.
        subprocess.run(cmd,check=True,env=environment()); rows.append(name); write(out/'progress.json',rows)
    run('install','install'); manifest=out/'install/result/descriptor.json'; expected=sha(manifest)
    for name,route,target in [('hello','InstalledRoot','IO ()\n'),('unicode','InstalledRoot','IO ()\n'),('collision','OriginalFallback','Int\n')]:
        source=HERE/'tests/fixtures'/ (name+'.emlf')
        run('factor',name+'-factor',source)
        run('original-check',name+'-original',source)
        run('consume-check',name+'-installed',source,manifest,expected)
        result=out/(name+'-installed')/'result'
        require((result/'route.txt').read_text().strip()==route,'wrong reuse/fallback route')
        if name=='collision': require((result/'route-reason.txt').read_text().strip()=='canonical installed identifier collision','wrong fallback reason')
        require((result/'target-type.txt').read_text()==target,'wrong target')
        require((out/(name+'-original')/'result/target-type.txt').read_bytes()==(result/'target-type.txt').read_bytes(),'target mismatch')
    write(out/'receipt.json',{'status':'PASS-check-only-smoke','operations':rows,'manifest_sha256':expected,'scope':'No native runtime or principal-type equivalence claim.'})
if __name__=='__main__': main()
