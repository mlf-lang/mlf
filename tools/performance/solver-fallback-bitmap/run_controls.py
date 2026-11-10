#!/usr/bin/env python3
"""R3 finite differential gate, not producer qualification or a timing sample."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, time, types
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OWNER = 'libraries/mlf-inference/Bootstrap/Graph/Solver.hs'
OLD = '58a248754171308509dd0752461c3e22c107973b6fa73b97931d5b74d2389612'
NEW = 'b99e57bd72a602b67636e78c967b7c26d86422f15aba33bd344b6a679d205a92'
MAIN = 'a355e02e10e1a419c3ed8c3fee18a8199e9af03037f520d49bdec0eb8ec1bf3e'
PASS = 'PASS R3 bitmap: 16 finite traversals, 6 ordered missing-node cases, 5 demand controls, 24 complete prepared/projection/fallback fixtures\n'
LIMITS = dict(address_space_per_process_bytes=6*1024**3,
    disk_free_floor_bytes=5*1024**3, host_available_floor_bytes=3*1024**3,
    max_work_bytes=3*1024**3, process_tree_rss_bytes=5*1024**3, wall_seconds=180)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--producer', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); baseline=a.baseline.resolve(); producer=a.producer.resolve(); out=a.output.resolve()
    if out.exists() or any(root.is_relative_to(out) or out.is_relative_to(root) for root in [producer]):
        p.error('fresh output separate from producer required')
    if any(root.is_relative_to(out) for root in [ROOT,baseline]):p.error('output cannot be source ancestor')
    hp=baseline/'tools/performance/a1-private-index/helper.py'
    H=types.ModuleType('guard');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    out.mkdir(parents=True)
    record=dict(complete=False, diagnostic_only=True, performance_measured=False,
                ordinary_producer_qualification=False,commands=[],inputs={},variants=[])
    save=lambda:H.save(out/'receipt.json',record)
    save()
    try:
        with H.SerialLock(baseline/'.mlf-build'):
            auth=H.authenticate(producer,baseline)
            H.require(H.sha(baseline/OWNER)==OLD and H.sha(ROOT/OWNER)==NEW,'fixed owner pair')
            H.require(H.sha(HERE/'Main.hs')==MAIN,'fixed finite controls')
            # The unchanged ordinary receipt remains authoritative for dependencies.
            for inventory in ['shared_inputs','host_inputs']:
                for name,row in auth[inventory].items():
                    original=Path(row['path']) if 'path' in row else baseline/name
                    relative=original.relative_to(baseline)
                    H.require(relative.as_posix()==OWNER or H.sha(ROOT/relative)==row['sha256'],
                              'candidate changed non-owner production input '+str(relative))
            old=(baseline/OWNER).read_bytes();new=(ROOT/OWNER).read_bytes()
            start=new.index(b'  -- A prepared fallback starts with two empty views')
            stop=new.index(b'  componentVisit ::',start)
            inverted=new[:start]+new[stop:]
            before=b'(componentCanonicalNodesVisit solver IM.empty IS.empty\n'
            after=b'(componentCanonicalBitmapVisit solver IS.empty IM.empty IS.empty\n'
            H.require(inverted.count(after)==1,'exactly one changed entry')
            H.require(inverted.replace(after,before)==old,'exact two-edit production delta')
            private=out/'private';private.mkdir()
            header=b'module Bootstrap.Graph.Solver where {'
            for name,data in [('R3FrozenSolver',old),('R3CandidateSolver',new)]:
                target=private/(name+'.hs'); replacement=('module '+name+' where {').encode()
                H.require(data.count(header)==1,'single owner module header')
                renamed=data.replace(header,replacement)
                H.require(renamed.replace(replacement,header)==data,'module rename inverse')
                target.write_bytes(renamed)
            control=(HERE/'Main.hs').read_bytes()
            old_import=b'import qualified Bootstrap.Graph.Solver as S'
            H.require(control.count(old_import)==1,'one candidate control import')
            (private/'Main.hs').write_bytes(control.replace(old_import,b'import qualified R3CandidateSolver as S'))
            pins={str(path):H.sha(path) for path in [hp,Path(__file__),HERE/'Main.hs',ROOT/OWNER,baseline/OWNER,producer/'receipt.json']}
            pins.update(H.file_pins(private))
            record.update(inputs=pins,ordinary_flags=auth['flags'],
                source_change='one new visitor and one prepared-fallback call only; exact inverse verified',
                oracle='complete exact f9 Solver; module header rename only',
                producer_receipt_sha256=H.sha(producer/'receipt.json'))
            # All subprocesses share one 180s allowance, including C validation.
            deadline=time.monotonic()+180
            def run(label,argv):
                remaining=deadline-time.monotonic();H.require(remaining>0,'shared control budget exhausted')
                try:return H.Runner(out,{**LIMITS,'wall_seconds':remaining}).run(argv,baseline,out/label)
                finally:
                    command=out/label/'command.json'
                    if command.exists():record['commands'].append(H.load(command));save()
            c_objects=[]
            H.require(H.sha(auth['cc']['path'])==auth['cc']['sha256'],'ordinary CC identity')
            for name in ['host.o','supervisor.o']:
                matches=[c for c in auth['commands'] if '-o' in c['argv'] and c['argv'][c['argv'].index('-o')+1]==str(producer/name)]
                H.require(len(matches)==1,'unique ordinary C compile command')
                cmd=matches[0];H.require(cmd['argv'][0]==auth['cc']['path'] and cmd['cwd']==str(baseline),'ordinary C provenance')
                expected=H.sha(producer/name);pins[str(producer/name)]=expected
                target=out/name;shutil.copy2(producer/name,target);pins[str(target)]=expected
                argv=list(cmd['argv']);argv[argv.index('-o')+1]=str(out/('verify-'+name))
                run('verify-'+name,argv);H.require(H.sha(out/('verify-'+name))==expected,'C rebuild byte equality')
                c_objects.append(str(target))
            for level in ['0','2']:
                objects=out/('objects-O'+level);objects.mkdir()
                for relative,digest in auth['object_inputs'].items():
                    if relative.startswith('objects/') and relative.endswith(('.o','.hi')):
                        original=producer/relative;H.require(H.sha(original)==digest,'ordinary object changed')
                        target=objects/Path(relative).relative_to('objects');target.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(original,target);H.require(H.sha(target)==digest,'ordinary object copy')
                for suffix in ['.o','.hi']:(objects/('Main'+suffix)).unlink(missing_ok=True)
                flags=[];skip=False
                for token in auth['flags']:
                    if skip:skip=False;continue
                    if token in ['-odir','-hidir']:skip=True;continue
                    flags.append('-O'+level if token=='-O2' else token)
                    if token=='-i':flags.append('-i'+str(private))
                flags+=['-odir',str(objects),'-hidir',str(objects)]
                binary=out/('controls-O'+level)
                run('build-O'+level,[auth['ghc']['path'],'--make','-j1',*flags,'-rtsopts=ignoreAll',str(private/'Main.hs'),*c_objects,'-o',str(binary)])
                run('run-O'+level,[str(binary)])
                H.require((out/('run-O'+level)/'stdout').read_text()==PASS,'finite controls exact stdout')
                H.require(not (out/('run-O'+level)/'stderr').read_bytes(),'finite controls empty stderr')
                record['variants'].append(dict(optimization=level,binary_sha256=H.sha(binary),flags=flags));save()
            H.check_pins(pins)
            H.authenticate(producer,baseline)
            record['complete']=True;save()
    except BaseException as e:
        record['error']=str(e);save();raise

if __name__=='__main__':main()
