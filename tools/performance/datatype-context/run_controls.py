#!/usr/bin/env python3
"""Datatype context memoization against the complete frozen c1b802bd query encoder."""
from pathlib import Path
import argparse, hashlib, sys, types

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/testing'))
from receipt_selection import select
ORACLE_MANIFEST_SHA='20580b068f5bb9969ca96753dbfa1a0d568ce9ad102eedd8e416ce8d68d0c742'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--producer',type=Path,required=True)
    p.add_argument('--source',type=Path,default=ROOT)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    options = ('0', '2')
    chosen = select('datatype-context/', options)
    optimizations = options if chosen is None else (chosen,)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    hp=ROOT/'tools/performance/a1-private-index/helper.py'
    H=types.ModuleType('guard');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    direct_path=a.source.resolve()/'tools/shared/test_direct.py'
    direct=H.module(direct_path,'query_control_authentication')
    def authenticate():
        producer=a.producer.resolve()
        return direct.authenticate_build(producer/'receipt.json',producer/'bin',root=a.source.resolve())
    H.require(H.sha(HERE/'oracle.json')==ORACLE_MANIFEST_SHA,'fixed c1b802bd oracle identity')
    oracle=H.load(HERE/'oracle.json');raw=(HERE/'FrozenCrateQuery.hs').read_bytes()
    H.require(hashlib.sha256(raw).hexdigest()==oracle['frozen_sha256'],'frozen full old encoder')
    manifest=H.load(ROOT/'shared-sources.json')
    files=[ROOT/x['path'] for x in manifest['modules']]+list((ROOT/'host/ghc').rglob('*.hs'))
    files+=list(HERE.glob('*.hs'))+[HERE/'oracle.json',Path(__file__),hp,direct_path]
    bridge=HERE.parent/'source-key-builtins/FrozenSourceKey.hs'
    adapter=bridge.with_name('frozen_query.py')
    adapted_dir=out/'historical-oracle'
    adapted_dir.mkdir()
    adapted=H.module(adapter,'frozen_query').prepare_frozen_query(HERE/'FrozenCrateQuery.hs',adapted_dir,
        expected_sha256=oracle['frozen_sha256'],
        types_source=ROOT/'libraries/mlf-foundation/Bootstrap/Types.hs')
    pins={str(f):H.sha(f) for f in [*files,bridge,bridge.with_name('NamedQueryControls.hs'),adapter,adapted]}
    limits=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,
        host_available_floor_bytes=3*1024**3,process_tree_rss_bytes=5*1024**3,max_work_bytes=2*1024**3,wall_seconds=600)
    record=dict(complete=False,performance_samples=0,inputs=pins,oracle=oracle,checks=[])
    save=lambda:H.save(out/'receipt.json',record)
    save()
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            auth=authenticate()
            record['ordinary_object_producer']=auth;save()
            for rel in ['host/ghc/cbits/host.c','runtime/mlf_process_supervisor.c']:
                H.require(H.sha(ROOT/rel)==H.sha(a.source/rel),'unchanged borrowed C object input')
            for opt in optimizations:
                label='O'+opt;objects=out/(label+'-objects');binary=out/(label+'-binary')
                argv=[auth['ghc']['path'],'--make','-j1','-O'+opt,'-fpedantic-bottoms','-fno-state-hack',
                    '-Werror=incomplete-patterns','-Werror=incomplete-uni-patterns','-package-env','-',
                    '-i','-i'+str(adapted_dir),'-i'+str(HERE),'-i'+str(bridge.parent),*['-i'+str(ROOT/x) for x in manifest['source_roots']],
                    '-odir',objects,'-hidir',objects,HERE/'Main.hs',a.producer/'host.o',
                    a.producer/'supervisor.o','-o',binary]
                H.Runner(out,limits).run(argv,ROOT,out/(label+'-build'))
                H.Runner(out,limits).run([binary],ROOT,out/(label+'-run'))
                stdout=(out/(label+'-run/stdout')).read_text()
                H.require(stdout.startswith('PASS datatype context reuse: ') and not (out/(label+'-run/stderr')).read_bytes(),'complete independent control matrix')
                record['checks'].append({'optimization':opt,'stdout':stdout});save()
                print(stdout.strip(),flush=True)
            H.check_pins(pins);H.require(authenticate()==auth,'unchanged ordinary object producer')
            record['complete']=True;save()
    except BaseException as e:
        record['error']=repr(e);save();raise

if __name__=='__main__':main()
