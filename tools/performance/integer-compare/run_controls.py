#!/usr/bin/env python3
"""Independent Integer semantics, with actual O2 producer objects and fresh O0 host."""
from pathlib import Path
import argparse,hashlib,shutil,subprocess,sys,types

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
EXPECTED=b'PASS integer comparison: 173889 values; 90 error-order, 18 partial, 36 divergence observations; 556 raw-tree lookups; 12 tree demand controls\n'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();producer=args.producer.resolve(strict=True);out=args.output.resolve()
    hp=HERE.parent/'a1-private-index/helper.py';H=types.ModuleType('unchanged_guard');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    H.require(not out.exists() and not out.is_relative_to(producer) and not producer.is_relative_to(out) and not ROOT.is_relative_to(out),'fresh separate controls')
    auth=H.authenticate(producer,ROOT);out.mkdir(parents=True)
    snapshot=out/'control-source';snapshot.mkdir()
    for name in ['run_controls.py','Main.hs','Probe.hs','Oracle.hs']:shutil.copy2(HERE/name,snapshot/name)
    pins={str(p):H.sha(p) for p in [Path(__file__),hp,HERE/'Oracle.hs',HERE/'Probe.hs',HERE/'Main.hs',producer/'receipt.json',ROOT/'host/ghc/MLF/Host/Base.hs']}
    original=H.file_pins(producer/'objects');record={'complete':False,'ordinary_candidate_authenticated':True,'performance_samples_added':0,'inputs':pins,'commands':[],'cases':[]}
    limits={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,'host_available_floor_bytes':3*1024**3,'max_work_bytes':2*1024**3,'process_tree_rss_bytes':5*1024**3,'wall_seconds':600}
    def save():H.save(out/'receipt.json',record)
    def run(name,argv):
        result=H.Runner(out,limits).run(argv,ROOT,out/name,timed=False);record['commands'].append(result);save()
    flags=[];i=0
    while i<len(auth['flags']):
        flag=auth['flags'][i]
        if flag in ['-odir','-hidir']:i+=2;continue
        if flag.startswith('-i') or flag.startswith('-O'):i+=1;continue
        flags.append(flag);i+=1
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            objects=out/'ordinary-objects';shutil.copytree(producer/'objects',objects)
            for suffix in ['.hi','.o']:(objects/('Main'+suffix)).unlink(missing_ok=True)
            kept=H.file_pins(objects);ghc=auth['ghc']['path']
            oflags=[*flags,'-O2','-i','-i'+str(objects),'-odir',str(objects),'-hidir',str(objects),'-dcore-lint']
            for name in ['Oracle','Probe','Main']:
                extra=['-ddump-simpl','-ddump-to-file','-ddump-file-prefix',str(out/'Probe')] if name=='Probe' else []
                run('ordinary-'+name,[ghc,*oflags,*extra,'-c',HERE/(name+'.hs')])
            H.check_pins(kept)
            run('ordinary-link',[ghc,*oflags,*sorted(objects.rglob('*.o')),producer/'host.o',producer/'supervisor.o','-o',out/'ordinary-controls'])
            run('ordinary-execute',[out/'ordinary-controls'])
            H.require((out/'ordinary-execute/stdout').read_bytes()==EXPECTED and not (out/'ordinary-execute/stderr').read_bytes(),'exact ordinary O2 controls')
            record['cases'].append({'mode':'actual ordinary O2 dependencies','comparisons':173889,'demand_errors':90,'partial_applications':18,'divergence_observations':36,'map_queries':556,'map_demands':12});save()
            o0=out/'O0';o0.mkdir()
            run('O0-build',[ghc,'--make','-j1',*flags,'-O0','-fforce-recomp','-dcore-lint','-i','-i'+str(HERE),'-i'+str(ROOT/'host/ghc'),'-i'+str(ROOT/'libraries/mlf-foundation'),'-odir',o0,'-hidir',o0,HERE/'Main.hs',producer/'host.o',producer/'supervisor.o','-o',out/'O0-controls'])
            run('O0-execute',[out/'O0-controls'])
            H.require((out/'O0-execute/stdout').read_bytes()==EXPECTED and not (out/'O0-execute/stderr').read_bytes(),'exact fresh O0 controls')
            record['cases'].append({'mode':'fresh O0 source closure','comparisons':173889,'demand_errors':90,'partial_applications':18,'divergence_observations':36,'map_queries':556,'map_demands':12})
            # Observe the real changed host operation in its actual consumer.
            # Only the copied IntMap module is rebuilt, then its code bytes are
            # compared with the ordinary producer before interpreting its dump.
            for suffix in ['.o','.hi']:(objects/('Bootstrap/IntMap'+suffix)).unlink()
            intact={p:d for p,d in kept.items() if Path(p).name not in ['IntMap.o','IntMap.hi']}
            run('mechanism',[ghc,*oflags,'-ddump-simpl','-ddump-to-file','-ddump-file-prefix',str(out/'IntMap'),'-c',ROOT/'libraries/mlf-foundation/Bootstrap/IntMap.hs'])
            H.check_pins(intact)
            record['mechanism_object']=str(objects/'Bootstrap/IntMap.o')
            def text_section(path):
                lines=subprocess.check_output(['otool','-s','__TEXT','__text',str(path)],text=True).splitlines()[2:]
                return bytes.fromhex(''.join(''.join(line.split()[1:]) for line in lines))
            ordinary=text_section(producer/'objects/Bootstrap/IntMap.o');diagnostic=text_section(objects/'Bootstrap/IntMap.o')
            H.require(ordinary==diagnostic,'Core-dump compilation preserves ordinary IntMap machine code bytes')
            core=(out/'IntMap.dump-simpl').read_text().split('end Rec }',1)[0]
            H.require('lookupTree' in core and core.count('Prim.<#')==2 and core.count('Integer.IS')==4 and 'integerLtFallback' in core and 'BigNat.bigNatCompare' not in core,'small IS payload compare in actual lookup, with out-of-line big-Integer fallback')
            record['mechanism']={'ordinary_text_equals_dumped_text':True,'text_bytes':len(ordinary),'text_sha256':hashlib.sha256(ordinary).hexdigest(),'lookup_unboxed_comparisons':2,'dump_sha256':H.sha(out/'IntMap.dump-simpl')}
            H.check_pins(original);H.check_pins(pins);H.require(H.authenticate(producer,ROOT)==auth,'ordinary producer unchanged')
            record['complete']=True;save();print('PASS independent O0/O2 comparison and map demand controls',flush=True)
    except BaseException as error:record['error']=repr(error);save();raise

if __name__=='__main__':main()
