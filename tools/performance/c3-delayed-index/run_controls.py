#!/usr/bin/env python3
"""Frozen full A1-owner differential; retained authored C4 fixtures and ABI bridge."""
from pathlib import Path
import argparse
import hashlib
import re
import shutil
import subprocess
import types

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OWNER='libraries/mlf-crates/Bootstrap/CrateSession.hs'
BASELINE='e123603d00f6f64e20e4d771836e49ddd808320f'
BASELINE_SHA='18abedc7f96452392ed3401f1ae607233ec13e2a5ba24bd1c0cba344820c382f'
EXPECTED=('PASS 63 physical graph/index/scope traces and legacy failure epochs\n'
          'PASS retained expansion descriptors and exact full component selection\n'
          'PASS repeated instances, reflexive equalities and literal fresh survivors\n'
          'PASS 8 demand, first-exception and unused-payload observations\n').encode()
# Reviewed extensions may add an independent Main and reversible helper copies.
# The default CLI, frozen owner and complete expected inventory stay unchanged.
EXTRA_SOURCES=[]
EXTRA_PINS=[]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--producer',type=Path,required=True)
    p.add_argument('--producer-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--optimization',choices=['0','2'],required=True)
    a=p.parse_args();out=a.output.resolve();producer=a.producer.resolve()
    hp=ROOT/'tools/performance/a1-private-index/helper.py'
    H=types.ModuleType('transport');H.__file__=str(hp)
    exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    H.require(not out.exists() and not out.is_relative_to(producer)
              and not producer.is_relative_to(out),'fresh isolated output')
    out.mkdir(parents=True)
    record=dict(complete=False,performance_samples=0,optimization=a.optimization,
                baseline_ref=BASELINE,commands=[])
    save=lambda:H.save(out/'receipt.json',record)
    save()
    limits=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,
                host_available_floor_bytes=3*1024**3,max_work_bytes=3*1024**3,
                process_tree_rss_bytes=5*1024**3,wall_seconds=600)
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            auth=H.authenticate(producer,a.producer_source)
            manifest=H.load(ROOT/'shared-sources.json')
            for row in manifest['modules']:
                if row['path']!=OWNER:
                    H.require(H.sha(ROOT/row['path'])==auth['shared_inputs'][row['module']]['sha256'],
                              'unchanged borrowed dependency '+row['module'])
            c4=ROOT/'tools/performance/c4-local-transaction'
            C=H.module(c4/'contracts.py','retained_contracts')
            cm=H.load(c4/'manifest.json');C.verify_oracles(c4,cm,None)
            for name,digest in cm['pins'].items():
                if name.startswith(('controls/','entrypoints/')):
                    H.require(H.sha(c4/name)==digest,'retained C4 fixture/control '+name)
            A=H.module(HERE.parent/'patricia/adapt_oracles.py','retained_abi_adapter')
            src=out/'source';A.prepare(ROOT,src)
            shutil.copy2(HERE.parent/'patricia/OracleTypes.hs',src/'OracleTypes.hs')
            frozen=subprocess.check_output(['git','show',BASELINE+':'+OWNER],cwd=ROOT)
            H.require(hashlib.sha256(frozen).hexdigest()==BASELINE_SHA,'frozen full private-owner oracle')
            for name,raw in [('LegacySession',frozen),('CandidateSession',(ROOT/OWNER).read_bytes())]:
                old=A.private_session_header(raw.decode()).encode()
                new=('module '+name+' where {').encode()
                H.require(raw.count(old)==1 and new not in raw,'unique private-owner header')
                changed=raw.replace(old,new)
                H.require(changed.replace(new,old)==raw,'module/export-header-only adaptation')
                (src/(name+'.hs')).write_bytes(changed)
            shutil.copy2(HERE/'Main.hs',src/'Main.hs')
            for source,name,before,after in EXTRA_SOURCES:
                raw=source.read_bytes()
                H.require(raw.count(before)==1 and after not in raw,'unique extension header')
                changed=raw.replace(before,after)
                H.require(changed.replace(after,before)==raw,'header-only extension inverse')
                (src/name).write_bytes(changed)
            pins=H.file_pins(src)
            pins.update({str(f):H.sha(f) for f in [Path(__file__),hp,HERE/'Main.hs',ROOT/OWNER,
                HERE.parent/'patricia/adapt_oracles.py',HERE.parent/'patricia/OracleTypes.hs',
                producer/'receipt.json',producer/'host.o',producer/'supervisor.o']})
            pins.update({str(f):H.sha(f) for f in EXTRA_PINS})
            pins.update({str(row[0]):H.sha(row[0]) for row in EXTRA_SOURCES})
            ledger=H.load(src/'adaptations.json')
            pins.update({row['source']:row['source_sha256'] for row in ledger['changes']})
            objects=out/'objects';shutil.copytree(producer/'objects',objects)
            for suffix in ['.o','.hi']:(objects/('Main'+suffix)).unlink(missing_ok=True)
            original_objects=H.file_pins(objects)
            H.require(all(H.sha(producer/Path(f).relative_to(out))==h for f,h in original_objects.items()),
                      'exact borrowed ordinary objects')
            record.update(inputs=pins,authentication=auth,borrowed_objects=original_objects)
            save()
            flags=[];original=auth['flags'];i=0
            while i<len(original):
                flag=original[i]
                if flag in ['-odir','-hidir']:i+=2
                elif flag.startswith('-i'):i+=1
                else:
                    flags.append('-O'+a.optimization if flag in ['-O0','-O2'] else flag);i+=1
            flags+=['-i','-i'+str(objects),'-odir',str(objects),'-hidir',str(objects)]
            local={}
            for source in src.glob('*.hs'):
                module=re.search(r'(?m)^module\s+([A-Z][\w.]*)',source.read_text())
                H.require(module is not None and module[1] not in local,'unique local control module')
                local[module[1]]=source
            order=[];seen=set();active=set()
            def visit(name):
                if name not in local or name in seen:return
                H.require(name not in active,'acyclic control imports');active.add(name)
                for dep in re.findall(r'(?m)^\s*import\s+(?:qualified\s+)?([A-Z][\w.]*)',local[name].read_text()):visit(dep)
                active.remove(name);seen.add(name);order.append(local[name])
            visit('Main')
            record['compiled_control_sources']=[str(s) for s in order];save()
            def run(label,argv):
                record['commands'].append(H.Runner(out,limits).run(argv,ROOT,out/label));save()
            ghc=auth['ghc']['path']
            for source in order:run('compile-'+source.stem,[ghc,*flags,'-c',source])
            H.check_pins(original_objects)
            binary=out/'controls'
            run('link',[ghc,*flags,*sorted(objects.rglob('*.o')),producer/'host.o',producer/'supervisor.o','-o',binary])
            run('run',[binary])
            H.require((out/'run/stdout').read_bytes()==EXPECTED,'complete independent control inventory')
            H.require(not(out/'run/stderr').read_bytes(),'empty control stderr')
            H.check_pins(pins)
            H.require(H.authenticate(producer,a.producer_source)==auth,'ordinary producer unchanged')
            record.update(complete=True,executable_sha256=H.sha(binary));save()
            print(EXPECTED.decode(),end='',flush=True)
    except BaseException as error:
        record['error']=repr(error);save();raise


if __name__=='__main__':main()
