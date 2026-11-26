#!/usr/bin/env python3
"""Frozen full A1-owner differential; retained authored C4 fixtures and ABI bridge."""
from pathlib import Path
import argparse
import hashlib
import re
import shutil
import sys
import types

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OWNER='libraries/mlf-crates/Bootstrap/CrateSession.hs'
BASELINE='e123603d00f6f64e20e4d771836e49ddd808320f'
ORACLE_SHA='93f8d5f686c05a8e2b56ef279c53a0ef0351af6f1ac7207746ee04623358fc66'
EXPECTED=('PASS 63 physical graph/index/scope traces and legacy failure epochs\n'
          'PASS retained expansion descriptors and exact full component selection\n'
          'PASS repeated instances, reflexive equalities and literal fresh survivors\n'
          'PASS 8 demand, first-exception and unused-payload observations\n').encode()
# Extensions may add an independent Main and named views of maintained controls.
# The default CLI, frozen owner and complete expected inventory stay unchanged.
EXTRA_SOURCES=[]
EXTRA_PINS=[]


sys.path.insert(0, str(ROOT / 'tools/testing'))
from receipt_selection import inventory_json, select

CASE_PREFIX = 'delayed-index/'


def main():
    checks = [line.removeprefix('PASS ') for line in EXPECTED.decode().splitlines()]
    if sys.argv[1:2] == ['--framework-list']:
        print(inventory_json(CASE_PREFIX, checks))
        return
    chosen = select(CASE_PREFIX, checks)
    expected = EXPECTED if chosen is None else ('PASS ' + chosen + '\n').encode()
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
    direct_path=a.producer_source.resolve()/'tools/shared/test_direct.py'
    direct=H.module(direct_path,'c3_control_authentication')
    def authenticate():
        return direct.authenticate_build(producer/'receipt.json',producer/'bin',root=a.producer_source.resolve())
    save()
    limits=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,
                host_available_floor_bytes=3*1024**3,max_work_bytes=3*1024**3,
                process_tree_rss_bytes=5*1024**3,wall_seconds=600)
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            auth=authenticate()
            manifest=H.load(ROOT/'shared-sources.json')
            for row in manifest['modules']:
                if row['path']!=OWNER:
                    H.require(H.sha(ROOT/row['path'])==auth['shared_inputs'][row['module']]['sha256'],
                              'unchanged borrowed dependency '+row['module'])
            A=H.module(HERE.parent/'patricia/adapt_oracles.py','retained_abi_adapter')
            src=out/'source';control_inputs=A.prepare(ROOT,src)
            frozen_path=HERE/'oracles/LegacySession.hs'
            frozen=frozen_path.read_bytes()
            H.require(hashlib.sha256(frozen).hexdigest()==ORACLE_SHA,'frozen full private-owner oracle')
            (src/'LegacySession.hs').write_bytes(frozen)
            changed=A.private_module_view((ROOT/OWNER).read_bytes(),'CandidateSession')
            (src/'CandidateSession.hs').write_bytes(changed)
            shutil.copy2(HERE/'Main.hs',src/'Main.hs')
            for source,name in EXTRA_SOURCES:
                changed=A.private_module_view(source.read_bytes(),name,owner='Main')
                (src/(name+'.hs')).write_bytes(changed)
            pins=H.file_pins(src)
            pins.update({str(f):H.sha(f) for f in [Path(__file__),hp,direct_path,HERE/'Main.hs',frozen_path,ROOT/OWNER,
                HERE.parent/'patricia/adapt_oracles.py',HERE.parent/'patricia/runtime_sources.py',
                HERE.parent/'patricia/frozen_oracles.py',
                producer/'receipt.json',producer/'host.o',producer/'supervisor.o']})
            pins.update({str(f):H.sha(f) for f in EXTRA_PINS})
            pins.update({str(row[0]):H.sha(row[0]) for row in EXTRA_SOURCES})
            pins.update(control_inputs)
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
            run('run',[binary, *([chosen] if chosen is not None else [])])
            H.require((out/'run/stdout').read_bytes()==expected,'complete independent control inventory')
            H.require(not(out/'run/stderr').read_bytes(),'empty control stderr')
            record['checks_log_sha256'] = H.sha(out / 'run/stdout')
            H.check_pins(pins)
            H.require(authenticate()==auth,'ordinary producer unchanged')
            record.update(complete=True,executable_sha256=H.sha(binary));save()
            print(expected.decode(),end='',flush=True)
    except BaseException as error:
        stdout = out / 'run/stdout'
        if stdout.is_file():
            record['checks_log_sha256'] = H.sha(stdout)
        record['error']=repr(error);save();raise


if __name__=='__main__':main()
