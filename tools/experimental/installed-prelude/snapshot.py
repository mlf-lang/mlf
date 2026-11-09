#!/usr/bin/env python3
"""Explicit local install/consume. Expected descriptor digest must come from outside the bundle."""
import argparse, json
from common import *
def verified_bundle(manifest, expected, build, build_hash):
    # Read each artifact exactly once; do not reopen before packing these same bytes.
    raw=manifest.read_bytes(); require(digest(raw)==expected,'external descriptor digest mismatch'); m=json.loads(raw)
    require(m['schema']=='experimental-installed-prelude-1','descriptor schema')
    require(m['build_receipt_sha256']==build_hash and m['harness_sha256']==build['harness_sha256'],'compiler/build identity')
    require(m['source_pins']==build['pins'],'source/tool identity')
    contracts=json.loads((P(build['root'])/'shared-sources.json').read_bytes())
    require(m['contracts']=={k:contracts[k] for k in CONTRACTS},'language/ABI/schema identity')
    artifacts=[]
    for key,name in [('metadata','unit.mlfci'),('object','unit.mlfco')]:
        require(m[key]['file']==name,'artifact path/schema')
        path=manifest.parent/name
        require(path.resolve().parent==manifest.parent.resolve(),'artifact escaped bundle')
        data=path.read_bytes(); require(digest(data)==m[key]['sha256'],'artifact digest: '+key)
        artifacts.append(data.decode('utf-8',errors='strict'))
    return artifacts

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=['install','factor','original-check','consume-check','consume-llvm','emit-installed-llvm'])
    p.add_argument('--build-receipt',type=P,required=True); p.add_argument('--build-receipt-sha256',required=True)
    p.add_argument('--output',type=P,required=True); p.add_argument('--manifest',type=P); p.add_argument('--manifest-sha256'); p.add_argument('--source',type=P)
    p.add_argument('--mode',choices=['implicit','no-prelude'],default='implicit'); a=p.parse_args()
    build=load_build(a.build_receipt,a.build_receipt_sha256); root=P(build['root']); out=a.output.resolve()
    require(not out.exists(),'fresh output required'); out.mkdir(); result=out/'result'; receipt=out/'receipt.json'
    record={'status':'running','operation':a.operation,'build_receipt_sha256':a.build_receipt_sha256,'scope':'Experimental opt-in. raw-root evidence is not baseline principal proof.'}; write(receipt,record)
    try:
        if a.operation=='install':
            require(a.manifest is None and a.source is None,'install takes no existing artifact or source')
            payload=b''; argv=[build['harness'],'install',str(result)]; seconds=300
        else:
            require(a.source is not None,'source required'); source=a.source.read_bytes(); decoded=source.decode('utf-8',errors='strict'); record['source_sha256']=digest(source)
            if a.operation in ('consume-check','consume-llvm','emit-installed-llvm'):
                require(a.manifest is not None and a.manifest_sha256,'external trusted descriptor SHA required')
                metadata,object_text=verified_bundle(a.manifest,a.manifest_sha256,build,a.build_receipt_sha256)
                payload=pack([a.manifest_sha256,metadata,object_text,decoded]); record['manifest_sha256']=a.manifest_sha256
                argv=[build['harness'],a.operation,a.mode,a.manifest_sha256,str(a.source.resolve())]
                if a.operation!='emit-installed-llvm': argv.append(str(result))
            else:
                require(a.manifest is None,'original/factor does not consume a snapshot'); payload=source
                argv=[build['harness'],a.operation,a.mode,str(a.source.resolve())]
                if a.operation=='original-check': argv.append(str(result))
            seconds=180
        record.update(stdin_sha256=digest(payload),stdin_bytes=len(payload)); write(receipt,record)
        stdout=bounded(root,out/'process',argv,payload,seconds)
        if a.operation=='install':
            # A newly generated local descriptor is trusted only when its digest is independently retained.
            m={'schema':'experimental-installed-prelude-1','build_receipt_sha256':a.build_receipt_sha256,'harness_sha256':build['harness_sha256'],'source_pins':build['pins'],'contracts':{k:json.loads((root/'shared-sources.json').read_bytes())[k] for k in CONTRACTS}}
            for key,name in [('metadata','unit.mlfci'),('object','unit.mlfco')]: m[key]={'file':name,'sha256':sha(result/name)}
            descriptor=result/'descriptor.json'; write(descriptor,m); record['manifest_sha256']=sha(descriptor)
            print(record['manifest_sha256'])
        elif a.operation=='emit-installed-llvm':
            (out/'program.ll').write_bytes(stdout)
        record['status']='complete'
    except BaseException as e: record.update(status='failed',error=repr(e)); raise
    finally:
        try: load_build(a.build_receipt,a.build_receipt_sha256); record['postcheck']='PASS'
        except BaseException as e: record.update(status='failed',postcheck_error=repr(e)); write(receipt,record); raise
        write(receipt,record)
if __name__=='__main__': main()
