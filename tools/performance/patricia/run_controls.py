#!/usr/bin/env python3
"""Focused current-source Patricia qualification, before ordinary producer build."""
from pathlib import Path
import argparse
import json
import types

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference-source',type=Path,required=True)
    p.add_argument('--reference-producer',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    path=ROOT/'tools/performance/a1-private-index/helper.py'
    H=types.ModuleType('unchanged_guard');H.__file__=str(path);exec(compile(path.read_bytes(),str(path),'exec'),H.__dict__)
    reference=a.reference_producer.resolve();reference_source=a.reference_source.resolve()
    auth=H.authenticate(reference,reference_source)
    manifest=H.load(ROOT/'shared-sources.json')
    paths=[ROOT/row['path'] for row in manifest['modules']]
    paths += list((ROOT/'host/ghc').rglob('*.hs'))+list(HERE.glob('*'))
    paths += [ROOT/'tools/performance/int64/CompilerControls.hs',ROOT/'shared-sources.json',ROOT/'mlf-shared.cabal',path]
    pins={str(f):H.sha(f) for f in paths if f.is_file()}
    for rel in ['host/ghc/cbits/host.c','runtime/mlf_process_supervisor.c']:
        H.require(H.sha(ROOT/rel)==H.sha(reference_source/rel),'borrowed C object source unchanged: '+rel)
    record=dict(complete=False,purpose='focused source correctness; candidate ordinary producer not yet built',
                performance_samples=0,inputs=pins,reference_producer=auth,checks=[])
    limits=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,
                host_available_floor_bytes=3*1024**3,process_tree_rss_bytes=5*1024**3,
                max_work_bytes=2*1024**3,wall_seconds=600)
    def save():H.save(out/'receipt.json',record)
    def run(name,argv):return H.Runner(out,limits).run(argv,ROOT,out/name,timed=False)
    ghc=auth['ghc']['path']
    common=['-fpedantic-bottoms','-fno-state-hack','-Werror=incomplete-patterns','-Werror=incomplete-uni-patterns',
            '-package-env','-','-i','-i'+str(HERE),*['-i'+str(ROOT/x) for x in manifest['source_roots']]]
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            for opt in ['O0','O2']:
                for name,source in [('containers',HERE/'Main.hs'),('compiler',ROOT/'tools/performance/int64/CompilerControls.hs'),('kind-routing',HERE/'KindRoutingControls.hs')]:
                    label=name+'-'+opt;objects=out/(label+'-objects');binary=out/(label+'-binary')
                    run(label+'-build',[ghc,'--make','-j1','-'+opt,*common,'-odir',objects,'-hidir',objects,
                        source,reference/'host.o',reference/'supervisor.o','-o',binary])
                    run(label+'-run',[binary])
                    H.require('PASS' in (out/(label+'-run/stdout')).read_text(),'complete focused controls: '+label)
                    record['checks'].append(label);save()
            entry=next(x for x in manifest['executables'] if x['name']=='emlf')
            run('compiler-typecheck',[ghc,'--make','-j1','-O0','-fno-code',*common,
                '-odir',out/'typecheck-objects','-hidir',out/'typecheck-objects',ROOT/entry['wrapper']])
            record['checks'].append('full compiler source typecheck')
            H.check_pins(pins);H.authenticate(reference,reference_source)
            record['complete']=True;save()
    except BaseException as error:
        record['error']=repr(error);save();raise
    print('PASS Patricia focused qualification: '+', '.join(record['checks']),flush=True)

if __name__=='__main__':main()
