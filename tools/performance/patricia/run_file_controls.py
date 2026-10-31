#!/usr/bin/env python3
"""Retain all nine C4 file controls across the explicit Int64 ABI boundary.

The baseline is an independently qualified Int64 producer. Both ordinary
candidate entry points are checked. Historical fixture text, handwritten
status/type/error expectations and the byte-comparison body stay unchanged.
"""
from pathlib import Path
import argparse,ast,hashlib,json,os,shutil,types
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for arg in ['reference-source','reference-producer','producer','builtin-prefix','output']:p.add_argument('--'+arg,type=Path,required=True)
 p.add_argument('--source',type=Path,default=ROOT);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 hp=ROOT/'tools/performance/a1-private-index/helper.py';H=types.ModuleType('unchanged_guard');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
 c4=ROOT/'tools/performance/c4-local-transaction';driver=c4/'run_controls.py';tree=ast.parse(driver.read_text());function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_files')
 context={'HERE':c4,'C':types.SimpleNamespace(sha_bytes=lambda b:hashlib.sha256(b).hexdigest()),'pack':lambda xs:''.join(str(len(x))+':'+x for x in xs),'os':os,'json':json,'Path':Path}
 exec(compile(ast.Module(body=[function],type_ignores=[]),str(driver),'exec'),context)
 fixture=c4/'controls/FileControls.hs';source=fixture.read_text();inputs={str(x.resolve()):H.sha(x) for x in [Path(__file__),hp,driver,fixture,c4/'fixtures/file-cases.json']}
 for suffix in ['.mlfci','.mlfco']:q=Path(str(a.builtin_prefix.resolve())+suffix);inputs[str(q)]=H.sha(q)
 record={'complete':False,'scope':'nine unchanged C4 file cases; Int64 baseline Crate versus candidate Crate and CrateSession; full diagnostics, handwritten types, fresh groups and raw artifacts','whole_P3_bytes_equal_claim':False,'inputs':inputs,'routes':{}}
 limits={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,'host_available_floor_bytes':3*1024**3,'max_work_bytes':2*1024**3,'process_tree_rss_bytes':5*1024**3,'wall_seconds':600}
 same_producer=a.reference_producer.resolve()==a.producer.resolve()
 record['independent_compiler_binary_reference']=not same_producer
 if same_producer:record['scope']='nine authored file cases, same ordinary producer: retained Crate algorithm versus CrateSession; handwritten status/type/errors and raw artifacts; shared numeric/typechecking dependencies'
 save=lambda:H.save(out/'receipt.json',record);save()
 try:
  with H.SerialLock(ROOT/'.mlf-build'):
   binaries={};auths={};roots={};producers={}
   for side,producer,root,session in [('reference',a.reference_producer,a.reference_source,False),('crate',a.producer,a.source,False),('session',a.producer,a.source,True)]:
    producer=producer.resolve();root=root.resolve();auth=H.authenticate(producer,root);auths[side]=auth;roots[side]=root;producers[side]=producer
    folder=out/side;folder.mkdir();objects=folder/'objects';shutil.copytree(producer/'objects',objects);original=H.file_pins(objects)
    text=source.replace('Bootstrap.Crate as Old','Bootstrap.CrateSession as Old') if session else source
    H.require((text.replace('Bootstrap.CrateSession as Old','Bootstrap.Crate as Old') if session else text)==source,'only reviewed entry-point import adaptation')
    (folder/'FileControls.hs').write_text(text);entry=folder/'Main.hs';entry.write_text('module Main where\nimport qualified FileControls as C\nmain=C.main\n')
    flags=[]
    for token in auth['flags']:
     flags.append(str(objects) if token==str(producer/'objects') else token)
     if token=='-i':flags.append('-i'+str(folder))
    binary=folder/'probe';H.Runner(out,limits).run([auth['ghc']['path'],'--make','-j1',*flags,entry,producer/'host.o',producer/'supervisor.o','-o',binary],root,folder/'build')
    H.require(all(H.sha(path)==digest for path,digest in original.items() if Path(path).name not in ['Main.o','Main.hi']),'ordinary production objects unchanged')
    inputs[str(binary)]=H.sha(binary);binaries[side]=binary
   for route in ['crate','session']:
    folder=out/('compare-'+route);folder.mkdir();rows={'file_cases':[]};record['routes'][route]=rows
    def run(name,argv,cwd):
     log=folder/name;H.Runner(out,limits).run(argv,cwd,log);return (log/'stdout').read_bytes(),(log/'stderr').read_bytes()
    context['run_files'](H,run,save,rows,inputs,folder,str(a.builtin_prefix.resolve()),binaries['reference'],binaries[route])
    H.require(len(rows['file_cases'])==9,'all nine retained cases completed')
   H.check_pins(inputs)
   for side in auths:H.require(H.authenticate(producers[side],roots[side])==auths[side],'producer unchanged '+side)
   record['complete']=True;save()
 except BaseException as error:record['error']=repr(error);save();raise
 print('PASS all nine retained file cases across both candidate entry points',flush=True)
if __name__=='__main__':main()
