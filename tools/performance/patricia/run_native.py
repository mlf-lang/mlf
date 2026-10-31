#!/usr/bin/env python3
"""Exercise compiled Int64 Patricia operations against an independent dict/set model."""
from pathlib import Path
import argparse,json,random,shlex,shutil,subprocess,sys,types
ROOT=Path(__file__).resolve().parents[3]

def fixture():
    minimum=-(1<<63);maximum=(1<<63)-1;rng=random.Random(20261031)
    keys=[minimum,minimum+1,minimum+63,minimum+64,maximum,maximum-1,maximum-63,maximum-64,-65,-64,-63,-1,0,1,2,63,64,65,1<<32,1<<62]
    keys+=list(range(-70,71))+[rng.randrange(minimum,maximum+1) for _ in range(48)]
    entries=list(zip(keys,range(len(keys))));other=list(zip(list(reversed(keys[::3]))+[7,12345,minimum+500],range(1000,1000+len(keys[::3])+3)))
    a=dict(entries);b=dict(other);queries=[minimum,maximum,-64,-1,0,64,7,12345,1234567]
    integer=lambda n:'(readInt "'+str(n)+'")'
    pairs=lambda xs:'['+','.join('((,) '+integer(k)+' '+str(v)+')' for k,v in xs)+']'
    numbers=lambda xs:'['+','.join(integer(x) for x in xs)+']'
    definitions=['a :: IntMap Int; a = M.fromList '+pairs(entries)+';', 'b :: IntMap Int; b = M.fromList '+pairs(other)+';', 'sa = S.fromList '+numbers(keys)+';', 'sb = S.fromList '+numbers(k for k,_ in other)+';']
    actions=[];expected=[]
    def map_case(label,expr,model):
        actions.append('dumpMap "'+label+'" ('+expr+')');expected.extend([label,str(len(model))])
        for k,v in sorted(model.items()):expected.extend([str(k),str(v)])
    def set_case(label,expr,model):
        actions.append('dumpSet "'+label+'" ('+expr+')');expected.extend([label,str(len(model)),*map(str,sorted(model))])
    union=dict(b);union.update(a)
    combined=dict(b);combined.update({k:v*1000+b[k] if k in b else v for k,v in a.items()})
    inserted=dict(a);inserted[minimum]=17*1000+a[minimum]
    deleted={k:v for k,v in a.items() if k not in [minimum,maximum,0,1234567]}
    for row in [('map-A','a',a),('map-B','b',b),('map-union','M.union a b',union),('map-combine','M.unionWith (\\x y -> x * 1000 + y) a b',combined),('map-intersection','M.intersection a b',{k:v for k,v in a.items() if k in b}),('map-difference','M.difference a b',{k:v for k,v in a.items() if k not in b}),('map-insertWith','M.insertWith (\\x y -> x * 1000 + y) '+integer(minimum)+' 17 a',inserted),('map-deletes','M.delete '+integer(minimum)+' (M.delete '+integer(maximum)+' (M.delete 0 (M.delete 1234567 a)))',deleted),('map-sorted','M.fromDistinctAscList '+pairs(sorted(a.items())),a)]:map_case(*row)
    for k in queries:
        actions.append('dumpMaybe (M.lookup '+integer(k)+' a)');expected.append(str(a[k]) if k in a else 'none')
        actions.append('dumpMaybe (M.lookupIndex '+integer(k)+' a)');expected.append(str(sorted(a).index(k)) if k in a else 'none')
    for n in [-1,0,1,len(a)//2,len(a)-1,len(a),len(a)+1]:
        actions.append('dumpPairMaybe (M.elemAt '+integer(n)+' a)')
        if 0<=n<len(a):k=sorted(a)[n];expected.extend([str(k),str(a[k])])
        else:expected.append('none')
    sa=set(a);sb=set(b)
    for row in [('set-A','sa',sa),('set-B','sb',sb),('set-union','S.union sa sb',sa|sb),('set-intersection','S.intersection sa sb',sa&sb),('set-difference','S.difference sa sb',sa-sb),('set-sorted','S.fromDistinctAscList '+numbers(sorted(sa)),sa),('set-delete','S.delete '+integer(minimum)+' (S.delete '+integer(maximum)+' sa)',sa-{minimum,maximum})]:set_case(*row)
    for k in queries:actions.append('printInt (if S.member '+integer(k)+' sa then 1 else 0)');expected.append('1' if k in sa else '0')
    # Exercise the new view constructors and operations through both backends,
    # independently of the legacy collection entry points above.
    view_start=len(actions)
    for k in queries:
        actions.append('dumpMaybe (Rank.mapRank '+integer(k)+' 17 (Rank.indexMap a))')
        expected.append(str(sorted(a).index(k)+17) if k in a else 'none')
        actions.append('dumpMaybe (Rank.setRank '+integer(k)+' (Rank.indexSet sa))')
        expected.append(str(sorted(sa).index(k)) if k in sa else 'none')
    for n in [-1,0,1,len(a)//2,len(a)-1,len(a),len(a)+1]:
        for expr in ['Rank.mapSelect '+integer(n)+' (Rank.indexMap a)',
                     'Rank.setSelect '+integer(n)+' (Rank.indexSet sa)']:
            actions.append('dumpMaybe ('+expr+')')
            expected.append(str(sorted(a)[n]) if 0<=n<len(a) else 'none')
    actions.append('printInt (Rank.mapSize (Rank.indexMap lazyMap))');expected.append('2')
    actions.append('dumpMaybe (Rank.mapSelect 0 (Rank.indexMap lazyMap))');expected.append(str(minimum))
    actions.append('dumpMaybe (Rank.mapRank '+integer(minimum)+' 0 (Rank.indexMap lazyMap))');expected.append('0')
    view_checks=len(actions)-view_start
    definitions+=['lazyMap :: IntMap Int; lazyMap = M.fromList [((,) '+integer(minimum)+' (panic "unselected-payload")),((,) '+integer(maximum)+' 17)];', 'leftMap = M.singleton '+integer(minimum)+' 5;', 'rightMap :: IntMap Int; rightMap = M.singleton '+integer(minimum)+' (panic "unselected-right");']
    for expr,value in [('M.size lazyMap',2),('M.findWithDefault 0 '+integer(maximum)+' lazyMap',17),('M.findWithDefault 0 '+integer(minimum)+' (M.union leftMap rightMap)',5),('M.findWithDefault 0 '+integer(minimum)+' (M.intersection leftMap rightMap)',5),('M.size (M.difference leftMap rightMap)',0),('M.size (M.map (\\x -> panic "unselected-map") a)',len(a))]:actions.append('printInt ('+expr+')');expected.append(str(value))
    header='''-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}
module Main (main) where {
import MLF.Primitive;
import Bootstrap.Types;
import qualified Bootstrap.IntMap as M;
import qualified Bootstrap.IntSet as S;
import qualified Bootstrap.IntRank as Rank;
runActions :: [] (IO ()) -> IO ();
runActions xs = case xs of { [] -> ioReturn (); (:) x rest -> ioBind x (\\_ -> runActions rest) };
printNumbers :: [] Int -> IO ();
printNumbers xs = case xs of { [] -> ioReturn (); (:) x rest -> ioBind (printInt x) (\\_ -> printNumbers rest) };
printPairs :: [] ((,) Int Int) -> IO ();
printPairs xs = case xs of { [] -> ioReturn (); (:) ((,) k v) rest -> ioBind (printInt k) (\\_ -> ioBind (printInt v) (\\_ -> printPairs rest)) };
dumpMap label tree = runActions [putStrLn label, printInt (M.size tree), printPairs (M.toList tree)];
dumpSet label tree = runActions [putStrLn label, printInt (S.size tree), printNumbers (S.toList tree)];
dumpMaybe value = case value of { Nothing -> putStrLn "none"; Just x -> printInt x };
dumpPairMaybe value = case value of { Nothing -> putStrLn "none"; Just ((,) k v) -> runActions [printInt k, printInt v] };
'''
    good=header+'\n'.join(definitions)+'\nmain :: IO ();\nmain = runActions ['+','.join(actions)+'];\n}\n'
    bad=header+'main :: IO (); main = ioBind (putStrLn "before") (\\_ -> printInt (M.findWithDefault 0 '+integer(minimum)+' (M.singleton '+integer(minimum)+' (panic "selected-payload"))));\n}\n'
    return good,('\n'.join(expected)+'\n').encode(),bad,{'signed_keys':len(a),'output_lines':len(expected),'map_cases':9,'set_cases':7,'index_view_checks':view_checks,'lazy_payload_checks':9,'selected_payload_error_checks':1}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--producer',type=Path,required=True);p.add_argument('--source',type=Path,default=ROOT);p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=['standalone','installed','both'],default='standalone');p.add_argument('--clang',default='/usr/bin/clang')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);source=a.source.resolve();producer=a.producer.resolve()
    h=ROOT/'tools/performance/a1-private-index/helper.py';H=types.ModuleType('guard');H.__file__=str(h);exec(compile(h.read_bytes(),str(h),'exec'),H.__dict__);auth=H.authenticate(producer,source)
    scope=ROOT/'tools/performance/process-spawn/with_scope.py';limits=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,host_available_floor_bytes=3*1024**3,process_tree_rss_bytes=5*1024**3,max_work_bytes=2*1024**3,wall_seconds=600)
    good,expected,bad,inventory=fixture();(out/'Main.hs').write_text(good);(out/'Bad.hs').write_text(bad);(out/'expected').write_bytes(expected)
    pins={str(x):H.sha(x) for x in [Path(__file__),h,scope,out/'Main.hs',out/'Bad.hs',out/'expected']}
    record={'complete':False,'purpose':'independent Python dict/set model and hand-authored demand probes, GHC and native LLVM execution','inputs':pins,'inventory':inventory,'checks':[],'mode':a.mode,'performance_samples':0,'limits':limits};save=lambda:H.save(out/'receipt.json',record)
    def run(label,argv,status=0):return H.Runner(out,limits).run(argv,source,out/label,expected_exit=status)
    def check(label,binary,failure):
        run(label,[binary],1 if failure else 0);stdout=(out/label/'stdout').read_bytes();stderr=(out/label/'stderr').read_bytes()
        H.require(stdout==(b'before\n' if failure else expected),'independent raw output '+label)
        H.require(b'selected-payload' in stderr and b'unselected' not in stderr if failure else not stderr,'payload demand '+label)
        record['checks'].append(label);save()
    save()
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            objects=out/'objects';shutil.copytree(producer/'objects',objects);flags=[]
            for token in auth['flags']:flags.append(str(objects) if token==str(producer/'objects') else token)
            for failure in [False,True]:
                name='bad' if failure else 'good';entry=out/('Bad.hs' if failure else 'Main.hs');binary=out/('ghc-'+name)
                run('ghc-'+name+'-build',[auth['ghc']['path'],'--make','-j1',*flags,'-rtsopts=ignoreAll',entry,producer/'host.o',producer/'supervisor.o','-o',binary]);check('ghc-'+name+'-run',binary,failure)
            if a.mode in ['standalone','both']:
                cflags=shlex.split(subprocess.check_output(['pkg-config','--cflags','bdw-gc','gmp'],text=True));libs=shlex.split(subprocess.check_output(['pkg-config','--libs','bdw-gc','gmp'],text=True));runtime=out/'runtime.o'
                run('runtime-build',[a.clang,'-O2','-std=c11',*cflags,'-I'+str(source/'runtime'),'-c',source/'runtime/mlf_runtime.c','-o',runtime])
            for mode in (['standalone','installed'] if a.mode=='both' else [a.mode]):
                for failure in [False,True]:
                    name=mode+('-bad' if failure else '-good');entry=out/('Bad.hs' if failure else 'Main.hs');binary=out/name
                    if mode=='standalone':
                        run(name+'-emit',[producer/'bin/emlf','-i',source/'libraries/mlf-foundation','--emit-llvm',entry]);ir=out/(name+'.ll');ir.write_bytes((out/(name+'-emit')/'stdout').read_bytes())
                        run(name+'-build',[a.clang,'-O2','-Wno-override-module',ir,runtime,*libs,'-lm','-lpthread','-o',binary])
                    else:
                        build=out/(name+'-objects');run(name+'-build',[sys.executable,scope,producer/'bin/emlf','-i',source/'libraries/mlf-foundation',entry,'-o',binary,'--build-dir',build])
                        receipt=H.load(build/'receipt.json');H.require(receipt['complete'] and receipt['fresh_user_compilation'] and receipt['llvm_jobs']==1 and receipt['stdlib_path']=='installed' and receipt['fixed_library_reused'],'installed generic standard-library reuse')
                    check(name+'-run',binary,failure)
            H.check_pins(pins);H.require(H.authenticate(producer,source)==auth,'ordinary producer unchanged');record['complete']=True
    except BaseException as error:record['error']=repr(error);raise
    finally:save()
    print('PASS compiled Patricia signed keys, bulk/rank operations and lazy payloads: '+str(inventory),flush=True)
if __name__=='__main__':main()
