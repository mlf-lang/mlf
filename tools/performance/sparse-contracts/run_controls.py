#!/usr/bin/env python3
"""Sparse source contract selection against complete frozen 48275901 sources."""
from pathlib import Path
import argparse, hashlib, types

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
ORACLE_MANIFEST_SHA='978b839cf05455bce0dc0c3db8756cd96489fad60c8033bfb95585dbde222a1b'
CLASSES_MANIFEST_SHA='73e7836abfbafdf311269d25b321b4e6ffa3b44ab43ab272ad13c2e77e679961'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--producer',type=Path,required=True)
    p.add_argument('--source',type=Path,default=ROOT)
    p.add_argument('--oracle-source',type=Path,
        help='optionally verify the frozen encoder against its complete historical checkout')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    hp=ROOT/'tools/performance/a1-private-index/helper.py'
    H=types.ModuleType('guard');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    H.require(H.sha(HERE/'oracle.json')==ORACLE_MANIFEST_SHA,'fixed baseline oracle identity')
    oracle=H.load(HERE/'oracle.json')
    for name,row in oracle['sources'].items():
        raw=(HERE/('Frozen'+name+'.hs')).read_bytes()
        H.require(hashlib.sha256(raw).hexdigest()==row['frozen_sha256'],'complete frozen '+name)
        old_header=('module Frozen'+name+' where {').encode()
        new_header=('module Bootstrap.'+name+' where {').encode()
        H.require(raw.count(old_header)==1,'unique oracle module header')
        old=raw.replace(old_header,new_header,1)
        H.require(hashlib.sha256(old).hexdigest()==row['source_sha256'],'module-only oracle adaptation')
        if a.oracle_source:
            H.require(old==(a.oracle_source/row['path']).read_bytes(),'independent frozen baseline source')
    H.require(H.sha(HERE/'classes-oracle.json')==CLASSES_MANIFEST_SHA,'fixed classes oracle identity')
    classes=H.load(HERE/'classes-oracle.json')
    H.require(classes['format']=='sparse-contracts-classes-oracle-v1'
              and classes['ref']==oracle['ref'],'independent classes oracle parent')
    frozenClasses=(HERE/'FrozenClasses.hs').read_bytes()
    H.require(hashlib.sha256(frozenClasses).hexdigest()==classes['frozen_sha256'], 'complete frozen Classes')
    H.require(frozenClasses.count(b'module FrozenClasses where {')==1,'unique frozen Classes header')
    originalClasses=frozenClasses.replace(b'module FrozenClasses where {',b'module Bootstrap.Classes where {',1)
    H.require(hashlib.sha256(originalClasses).hexdigest()==classes['source_sha256'],'Classes module-only adaptation')
    if a.oracle_source:
        H.require(originalClasses==(a.oracle_source/classes['path']).read_bytes(),'independent frozen baseline Classes')
    # The legacy frozen source deliberately uses the live Classes module. For
    # this candidate, derive an independent source oracle in the output tree,
    # with exactly two reversible text substitutions and no historical edits.
    rawSource=(HERE/'FrozenSourceInference.hs').read_bytes()
    sourceHeader=b'module FrozenSourceInference where {'
    fullHeader=b'module FullyFrozenSourceInference where {'
    sourceImport=b'import qualified Bootstrap.Classes as Classes;'
    frozenImport=b'import qualified FrozenClasses as Classes;'
    H.require(rawSource.count(sourceHeader)==1 and rawSource.count(sourceImport)==1,'unique source oracle adaptation anchors')
    adapted=rawSource.replace(sourceHeader,fullHeader,1).replace(sourceImport,frozenImport,1)
    H.require(adapted.count(fullHeader)==1 and adapted.count(frozenImport)==1 and
              adapted.replace(fullHeader,sourceHeader,1).replace(frozenImport,sourceImport,1)==rawSource,
              'fully frozen source adaptation reversible')
    mainRaw=(HERE/'Main.hs').read_bytes()
    mainImport=b'import qualified FrozenSourceInference as FS'
    fullMainImport=b'import qualified FullyFrozenSourceInference as FS'
    H.require(mainRaw.count(mainImport)==1,'unique control import anchor')
    mainAdapted=mainRaw.replace(mainImport,fullMainImport,1)
    H.require(mainAdapted.count(fullMainImport)==1 and mainAdapted.replace(fullMainImport,mainImport,1)==mainRaw,
              'control import adaptation reversible')
    generated=out/'independent-oracles';generated.mkdir()
    (generated/'FullyFrozenSourceInference.hs').write_bytes(adapted)
    (generated/'Main.hs').write_bytes(mainAdapted)
    adaptations={'source_original_sha256':hashlib.sha256(rawSource).hexdigest(),
                 'source_adapted_sha256':hashlib.sha256(adapted).hexdigest(),
                 'main_original_sha256':hashlib.sha256(mainRaw).hexdigest(),
                 'main_adapted_sha256':hashlib.sha256(mainAdapted).hexdigest(),
                 'edits':['source module header','source Classes import','Main FS import'],
                 'reversible':True}
    manifest=H.load(ROOT/'shared-sources.json')
    files=[ROOT/x['path'] for x in manifest['modules']]+list((ROOT/'host/ghc').rglob('*.hs'))
    files+=list(HERE.glob('*.hs'))+[HERE/'oracle.json',HERE/'classes-oracle.json',Path(__file__),hp,generated/'FullyFrozenSourceInference.hs',generated/'Main.hs']
    bridge=HERE.parent/'source-key-builtins/FrozenSourceKey.hs'
    pins={str(f):H.sha(f) for f in [*files,bridge]}
    limits=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,
        host_available_floor_bytes=3*1024**3,process_tree_rss_bytes=5*1024**3,max_work_bytes=2*1024**3,wall_seconds=600)
    record=dict(complete=False,performance_samples=0,inputs=pins,oracle=oracle,classes_oracle=classes,adaptations=adaptations,checks=[])
    save=lambda:H.save(out/'receipt.json',record)
    save()
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            auth=H.authenticate(a.producer,a.source)
            record['ordinary_object_producer']=auth;save()
            for rel in ['host/ghc/cbits/host.c','runtime/mlf_process_supervisor.c']:
                H.require(H.sha(ROOT/rel)==H.sha(a.source/rel),'unchanged borrowed C object input')
            for opt in ['0','2']:
                label='O'+opt;objects=out/(label+'-objects');binary=out/(label+'-binary')
                argv=[auth['ghc']['path'],'--make','-j1','-O'+opt,'-fpedantic-bottoms','-fno-state-hack',
                    '-Werror=incomplete-patterns','-Werror=incomplete-uni-patterns','-package-env','-',
                    '-i','-i'+str(generated),'-i'+str(HERE),'-i'+str(bridge.parent),*['-i'+str(ROOT/x) for x in manifest['source_roots']],
                    '-odir',objects,'-hidir',objects,generated/'Main.hs',a.producer/'host.o',
                    a.producer/'supervisor.o','-o',binary]
                H.Runner(out,limits).run(argv,ROOT,out/(label+'-build'))
                H.Runner(out,limits).run([binary],ROOT,out/(label+'-run'))
                stdout=(out/(label+'-run/stdout')).read_text()
                H.require(stdout.startswith('PASS sparse contract selection: ') and not (out/(label+'-run/stderr')).read_bytes(),'complete independent control matrix')
                record['checks'].append({'optimization':opt,'stdout':stdout});save()
                print(stdout.strip(),flush=True)
            H.check_pins(pins);H.require(H.authenticate(a.producer,a.source)==auth,'unchanged ordinary object producer')
            record['complete']=True;save()
    except BaseException as e:
        record['error']=repr(e);save();raise

if __name__=='__main__':main()
