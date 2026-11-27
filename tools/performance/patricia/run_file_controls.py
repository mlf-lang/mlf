#!/usr/bin/env python3
"""Retain all nine C4 file controls across the explicit Int64 ABI boundary.

The baseline is an independently qualified Int64 producer. Both ordinary
candidate entry points are checked. Historical fixture text, handwritten
status/type/error expectations and the ordinary byte-comparison body stay unchanged.
The Session branch uses the explicit open-format content and same-format gates.
"""
from pathlib import Path
import argparse,importlib.util,shutil,sys
import file_cases as Files
import run_open_file_controls as OpenFiles
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tools/testing'))
from receipt_selection import inventory_json, select

PREFIX = 'patricia-file-controls/'


def authenticate(H, producer, source):
 """Authenticate a normal correctness producer at either optimization level."""
 producer, source = Path(producer).resolve(), Path(source).resolve()
 direct = H.module(source/'tools/shared/test_direct.py', 'file_controls_authentication')
 return direct.authenticate_build(producer/'receipt.json', producer/'bin', root=source)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 listing = '--framework-list' in sys.argv[1:]
 p.add_argument('--framework-list',action='store_true')
 for arg in ['reference-source','reference-producer','producer','builtin-prefix','output']:p.add_argument('--'+arg,type=Path,required=not listing)
 p.add_argument('--source',type=Path,default=ROOT)
 a=p.parse_args()
 fixture_cases=Files.FIXTURE
 labels=[row['name'] for row in Files.load_cases()]
 exact=select(PREFIX,labels)
 planned=[exact] if exact is not None else labels
 if a.framework_list:
  print(inventory_json(PREFIX,planned))
  return
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 hp=ROOT/'tools/performance/a1-private-index/helper.py'
 spec=importlib.util.spec_from_file_location('file_control_guard',hp)
 H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
 fixture=Path(__file__).with_name('controls')/'files/FileControls.hs'
 source=fixture.read_text()
 inputs={str(x.resolve()):H.sha(x) for x in [Path(__file__),hp,Path(Files.__file__),fixture,fixture_cases,ROOT/'tools/testing/receipt_selection.py']}
 for suffix in ['.mlfci','.mlfco']:q=Path(str(a.builtin_prefix.resolve())+suffix);inputs[str(q)]=H.sha(q)
 record={'complete':False,'scope':'nine unchanged C4 file cases; Int64 baseline Crate versus candidate Crate and CrateSession; full diagnostics, handwritten types, fresh groups; unchanged ordinary raw-byte gate and explicit open boundary','whole_P3_bytes_equal_claim':False,'inputs':inputs,'routes':{},'checks':[],'planned_checks':planned}
 limits={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,'host_available_floor_bytes':3*1024**3,'max_work_bytes':2*1024**3,'process_tree_rss_bytes':5*1024**3,'wall_seconds':600}
 same_producer=a.reference_producer.resolve()==a.producer.resolve()
 record['independent_compiler_binary_reference']=not same_producer
 if same_producer:record['scope']='nine authored file cases, same ordinary producer: retained Crate algorithm versus CrateSession; handwritten status/type/errors, ordinary exact bytes and complete open boundary comparison; shared numeric/typechecking dependencies'
 if exact is not None:record['scope']=record['scope'].replace('nine','one selected',1)
 def save():
  # Session outcomes consume and independently validate the passed ordinary route.
  session=record['routes'].get('session',{})
  record['checks']=[row['name'] for row in session.get('file_cases',[]) if row['complete']]
  H.save(out/'receipt.json',record)
 save()
 try:
  with H.SerialLock(ROOT/'.mlf-build'):
   binaries={};auths={};roots={};producers={}
   for side,producer,root,session in [('reference',a.reference_producer,a.reference_source,False),('crate',a.producer,a.source,False),('session',a.producer,a.source,True)]:
    producer=producer.resolve();root=root.resolve();auth=authenticate(H,producer,root);auths[side]=auth;roots[side]=root;producers[side]=producer
    folder=out/side;folder.mkdir();OpenFiles.verify_producer_objects(H,producer,auth)
    OpenFiles.verify_c_support(H,out,root,producer,auth,folder,inputs,record,save,limits)
    objects=folder/'objects';shutil.copytree(producer/'objects',objects);original=H.file_pins(objects)
    H.require({'objects/'+str(Path(p).relative_to(objects)):h for p,h in original.items()}==auth['object_inputs'],'exact copied production object inventory')
    session_import='import qualified Bootstrap.Crate as Old\nimport qualified Bootstrap.CrateSession as Session'
    text=source.replace('import qualified Bootstrap.Crate as Old',session_import).replace(
      'compileFile = legacyCompileSpecFile','compileFile = Session.compileSpecFile') if session else source
    restored=text.replace(session_import,'import qualified Bootstrap.Crate as Old').replace(
      'compileFile = Session.compileSpecFile','compileFile = legacyCompileSpecFile') if session else text
    H.require(restored==source,'only reviewed historical/production entry-point adaptation')
    (folder/'FileControls.hs').write_text(text);entry=folder/'Main.hs';entry.write_text('module Main where\nimport qualified FileControls as C\nmain=C.main\n')
    flags=[]
    for token in auth['flags']:
     flags.append(str(objects) if token==str(producer/'objects') else token)
     if token=='-i':flags.append('-i'+str(folder))
    binary=folder/'probe';H.Runner(out,limits).run([auth['ghc']['path'],'--make','-j1',*flags,entry,producer/'host.o',producer/'supervisor.o','-o',binary],root,folder/'build')
    OpenFiles.verify_compiled_controls(H,(folder/'build/stdout').read_bytes(),(folder/'build/stderr').read_bytes(),folder)
    H.require(all(H.sha(path)==digest for path,digest in original.items() if Path(path).name not in ['Main.o','Main.hi']),'ordinary production objects unchanged')
    inputs[str(binary)]=H.sha(binary);binaries[side]=binary
   for route in ['crate']:
    folder=out/('compare-'+route);folder.mkdir();rows={'file_cases':[]};record['routes'][route]=rows
    def run(name,argv,cwd):
     log=folder/name;H.Runner(out,limits).run(argv,cwd,log);return (log/'stdout').read_bytes(),(log/'stderr').read_bytes()
    Files.run_files(H,run,save,rows,inputs,folder,str(a.builtin_prefix.resolve()),binaries['reference'],binaries[route],selected=exact)
    H.require([row['name'] for row in rows['file_cases']]==planned,'all planned ordinary cases completed')
   OpenFiles.run_session_files(H,out,record,inputs,binaries,producers['session'],roots['session'],auths['session'],str(a.builtin_prefix.resolve()),save,limits,selected=exact)
   H.check_pins(inputs)
   for side in auths:
    H.require(authenticate(H,producers[side],roots[side])==auths[side],'producer unchanged '+side)
    OpenFiles.verify_producer_objects(H,producers[side],auths[side])
   record['complete']=True;save()
 except BaseException as error:record['error']=repr(error);save();raise
 print('PASS selected file case: '+exact if exact is not None else
       'PASS all nine retained file cases: ordinary exact bytes and explicit open boundary',flush=True)
if __name__=='__main__':main()
