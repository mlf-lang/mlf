#!/usr/bin/env python3
from pathlib import Path
import json,sys,shutil,types,hashlib,argparse
out=Path(__file__).resolve().parent;root=out.parents[2]
parser=argparse.ArgumentParser(description='Independent full-tree and demand controls for Map.balance against an authenticated ordinary producer.')
parser.add_argument('--producer',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
hp=root/'tools/performance/a1-private-index/helper.py';H=types.ModuleType('unchanged_helper');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
producer=args.producer.resolve(strict=True);source=root;dest=args.output.resolve();H.require(not dest.exists(),'fresh controls directory');H.require(dest != root and not root.is_relative_to(dest) and not producer.is_relative_to(dest) and not dest.is_relative_to(producer),'output separate from source ancestor and producer');dest.mkdir(parents=True)
record={'complete':False,'producer_receipt_sha256':H.sha(producer/'receipt.json'),'inputs':{str(hp):H.sha(hp),str(__file__):H.sha(__file__),str(out/'BalanceControls.hs'):H.sha(out/'BalanceControls.hs'),str(out/'BaselineMap.hs'):H.sha(out/'BaselineMap.hs')},'commands':[]}
baseline_bytes=(out/'BaselineMap.hs').read_bytes()
H.require(baseline_bytes.count(b'module BaselineMap where {')==1,'exact frozen baseline module header')
restored=baseline_bytes.replace(b'module BaselineMap where {',b'module Bootstrap.Map where {')
H.require(hashlib.sha256(restored).hexdigest()=='1fdf24d3b3874c76d246f098ee9361a7f93e7eb01f741e064347452976cdaf0a','qualified 823f3060 baseline map body changed')
auth=H.authenticate(producer,source);record['producer_authenticated']=True
objects=dest/'objects';shutil.copytree(producer/'objects',objects)
for suffix in ['.o','.hi']:(objects/('Main'+suffix)).unlink(missing_ok=True)
original_pins=H.file_pins(producer/'objects');local_pins=H.file_pins(objects)
controls=root/'tools/performance/a1-private-index/controls'
historical=root/'tools/performance/a1-private-index/run_controls.py'
compat=H.load(root/'tools/performance/a1-private-index/current/source-compatibility.json')
H.require(H.sha(historical)==compat['historical_runner_sha256'],'frozen runner anchor changed')
frozen=H.module(historical,'frozen_controls')
record['inputs'][str(historical)]=H.sha(historical)
for name in ['FrozenMap.hs']:
 p=controls/name;H.require(H.sha(p)==frozen.CONTROL_HASHES[name],'frozen map oracle changed');record['inputs'][str(p)]=H.sha(p)
for path in [source/'libraries/mlf-foundation/Bootstrap/Map.hs',source/'bootstrap/MLF/BuiltinPreludeData.hs']:
 record['inputs'][str(path)]=H.sha(path)
limits={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,'host_available_floor_bytes':3*1024**3,'max_work_bytes':1024**3,'process_tree_rss_bytes':5*1024**3,'wall_seconds':600}
flags=list(auth['flags'])
# Compile each explicit control with -c: every ordinary dependency is resolved
# from copied authenticated interfaces, never rebuilt or replaced with source.
keep=[];i=0
while i<len(flags):
 if flags[i] in ['-odir','-hidir']:i+=2;continue
 if flags[i].startswith('-i'):i+=1;continue
 keep.append(flags[i]);i+=1
flags=keep+['-i','-i'+str(objects),'-odir',str(objects),'-hidir',str(objects)]
ghc=auth['ghc']['path']
def run(name,argv):
 r=H.Runner(dest,limits).run(argv,root,dest/name,timed=False);record['commands'].append(r);H.save(dest/'receipt.json',record)
H.save(dest/'receipt.json',record)
for label,path in [('frozen-map',controls/'FrozenMap.hs'),('baseline-map',out/'BaselineMap.hs'),('main',out/'BalanceControls.hs')]:
 run(label,[ghc,*flags,'-c',str(path)])
for path,digest in local_pins.items():H.require(H.sha(path)==digest,'ordinary dependency changed during controls')
run('link',[ghc,*flags,*map(str,sorted(objects.rglob('*.o'))),str(producer/'host.o'),str(producer/'supervisor.o'),'-o',str(dest/'balance-controls')])
run('execute',[str(dest/'balance-controls')])
expected=b'Balance controls: 24649 raw-shape pairs; 400 mutation steps; 30 independent demand/order cases passed\n'
H.require((dest/'execute/stdout').read_bytes()==expected and not (dest/'execute/stderr').read_bytes(),'exact independent control completion')
H.check_pins(original_pins);H.check_pins(record['inputs']);H.require(H.authenticate(producer,source)==auth,'producer changed')
record.update(complete=True,raw_shape_pairs=24649,mutation_steps=400,independent_demand_order_cases=30,ordinary_dependencies_unchanged=True);H.save(dest/'receipt.json',record);print(expected.decode().strip())
