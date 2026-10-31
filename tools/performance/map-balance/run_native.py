#!/usr/bin/env python3
from pathlib import Path
import json,sys,types,shlex,hashlib,argparse,shutil
out=Path(__file__).resolve().parent;root=out.parents[2]
parser=argparse.ArgumentParser(description='Focused native Map controls at ordinary Clang O2, including preserved MapFolds and literal malformed/large-size shapes.')
parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--baseline-compiler',type=Path)
parser.add_argument('--gc-prefix',type=Path,required=True);parser.add_argument('--clang',default='clang');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
dest=args.output.resolve()
if dest == root or root.is_relative_to(dest):raise ValueError('output must not contain the source checkout')
dest.mkdir(parents=True)
gc=args.gc_prefix.resolve(strict=True);clang=Path(shutil.which(args.clang)).resolve(strict=True);pkg=Path(shutil.which('pkg-config')).resolve(strict=True)
hp=root/'tools/performance/a1-private-index/helper.py';H=types.ModuleType('unaltered_helper');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
inputs=dest/'inputs';inputs.mkdir();source=root
w={'compilers':{side:{'path':str(path.resolve(strict=True)),'sha256':H.sha(path.resolve(strict=True))} for side,path in [('A',args.baseline_compiler or args.compiler),('B',args.compiler)]}}
limits={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,'host_available_floor_bytes':3*1024**3,'max_work_bytes':2*1024**3,'process_tree_rss_bytes':5*1024**3,'wall_seconds':600}
original=(root/'bootstrap/tests/MapFolds.emlf').read_text();H.require(original.count('main = semantics')==1,'one original fold entrypoint')
(inputs/'BalanceNative.emlf').write_text(original.replace('main = semantics','main = nativeMain')+(out/'NativeCases.emlf.fragment').read_text())
shutil.copy2(out/'native-expected.txt',inputs/'expected-finite.txt')
for side in ['A','B']:
 folder=inputs/side/'Bootstrap';folder.mkdir(parents=True)
 for name in ['Map','Types','Std']:
  if side=='A' and name=='Map':
   data=(out/'BaselineMap.hs').read_bytes();H.require(data.count(b'module BaselineMap where {')==1,'one frozen module header');data=data.replace(b'module BaselineMap where {',b'module Bootstrap.Map where {')
   H.require(hashlib.sha256(data).hexdigest()=='1fdf24d3b3874c76d246f098ee9361a7f93e7eb01f741e064347452976cdaf0a','complete qualified baseline Map body')
  else:data=(root/'libraries/mlf-foundation/Bootstrap'/(name+'.hs')).read_bytes()
  (folder/(name+'.hs')).write_bytes(data)
record={'complete':False,'optimization':'ordinary Clang -O2','performance_claim':False,'compiler_source_provenance_authenticated':False,'scope':'Selected binary and source/header closure, static BDWGC and pkg-config GMP flags; not full native toolchain closure or compiler corpus qualification','inputs':{str(hp):H.sha(hp),str(__file__):H.sha(__file__),**H.file_pins(inputs)},'commands':[],'artifacts':{}}
for compiler in w['compilers'].values():record['inputs'][compiler['path']]=compiler['sha256']
for path in [source/'runtime/mlf_runtime.c',*sorted((source/'runtime').glob('*.h')),gc/'lib/libgc.a',clang,pkg,root/'bootstrap/tests/MapFolds.emlf',out/'NativeCases.emlf.fragment',out/'native-expected.txt',out/'BaselineMap.hs',*sorted((gc/'include').rglob('*.h')),*[root/'libraries/mlf-foundation/Bootstrap'/(name+'.hs') for name in ['Map','Types','Std']]]:record['inputs'][str(path)]=H.sha(path)
def run(name,argv,exit=0):
 H.check_pins(record['inputs']);H.check_pins(record['artifacts']);r=H.Runner(dest,limits).run(list(map(str,argv)),dest,dest/name,expected_exit=exit,timed=False);record['commands'].append(r);H.save(dest/'receipt.json',record);return dest/name/'stdout'
H.save(dest/'receipt.json',record)
try:
 cflags=shlex.split(run('gmp-cflags',[str(pkg),'--cflags','gmp']).read_text());libs=shlex.split(run('gmp-libs',[str(pkg),'--libs','gmp']).read_text())
 run('clang-version',[str(clang),'--version'])
 runtime=dest/'runtime.o';run('runtime',[str(clang),'-O2','-std=c11',*cflags,'-I'+str(gc/'include'),'-I'+str(source/'runtime'),'-c',source/'runtime/mlf_runtime.c','-o',runtime])
 record['artifacts'][str(runtime)]=H.sha(runtime)
 for side in ['A','B']:
  llvm=run('emit-'+side,[w['compilers'][side]['path'],'-i',inputs/side,'--emit-llvm-gc',inputs/'BalanceNative.emlf'])
  ll=dest/(side+'.ll');ll.write_bytes(llvm.read_bytes());record['artifacts'][str(ll)]=H.sha(ll);binary=dest/(side+'-O2')
  run('link-'+side,[str(clang),'-O2','-Wno-override-module',ll,runtime,str(gc/'lib/libgc.a'),*libs,'-lm','-lpthread','-ldl','-o',binary])
  record['artifacts'][str(binary)]=H.sha(binary)
  actual=run(side+'-finite',[binary,'finite']);H.require(actual.read_bytes()==(inputs/'expected-finite.txt').read_bytes() and not actual.with_name('stderr').read_bytes(),'manual native finite shape/laziness and original fold outputs')
  for mode,message in [('left','left'),('right','right'),('root','root'),('inner','inner')]:
   actual=run(side+'-'+mode,[binary,mode],1);H.require(not actual.read_bytes() and actual.with_name('stderr').read_bytes()==('Runtime: '+message+'\n').encode(),'native demand/error order: '+mode)
 H.check_pins(record['inputs']);H.check_pins(record['artifacts']);record['complete']=True;H.save(dest/'receipt.json',record);print('Native Map controls passed for A and B at Clang O2',flush=True)
except BaseException as e:record['error']=repr(e);H.save(dest/'receipt.json',record);raise
