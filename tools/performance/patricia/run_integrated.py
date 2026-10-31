#!/usr/bin/env python3
"""Retained finite regressions across the explicitly reviewed Int64/Patricia ABI."""
from pathlib import Path
import argparse, json, shutil, types
from legacy_controls import prepare
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
LIMITS={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,
        'host_available_floor_bytes':3*1024**3,'max_work_bytes':3*1024**3,
        'process_tree_rss_bytes':5*1024**3,'wall_seconds':1200}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',choices=['p123','map-balance','graph','validation','builtin'],required=True)
    p.add_argument('--producer',type=Path,required=True)
    p.add_argument('--source',type=Path,default=ROOT)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();producer=a.producer.resolve();source=a.source.resolve()
    if out.exists() or out.is_relative_to(producer) or producer.is_relative_to(out) or ROOT.is_relative_to(out):
        p.error('fresh output separate from the producer and source ancestors required')
    out.mkdir(parents=True)
    hp=ROOT/'tools/performance/a1-private-index/helper.py'
    H=types.ModuleType('guard');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    record={'complete':False,'suite':a.suite,'performance_measured':False,
            'ABI_migration':'Haskell Int64 arithmetic; Patricia public collection representation',
            'historical_unbounded_or_BST_contract_claimed':False,'checks':[],
            'driver_inputs':{str(p):H.sha(p) for p in [Path(__file__),HERE/'adapt_oracles.py',HERE/'legacy_controls.py',HERE/'legacy-controls-pins.json',hp,ROOT/'tools/performance/c4-local-transaction/contracts.py']}}
    save=lambda:H.save(out/'receipt.json',record)
    save()
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            auth=H.authenticate(producer,source)
            record['producer_receipt_sha256']=H.sha(producer/'receipt.json')
            if a.suite in ['graph','validation']:
                A=H.module(HERE/'adapt_oracles.py','adapter')
                C=H.module(ROOT/'tools/performance/c4-local-transaction/contracts.py','contracts')
                c4=ROOT/'tools/performance/c4-local-transaction'
                H.require(H.sha(c4/'manifest.json')=='11aa01a0e00a964c8a97f1f1f4b04490e80dd1691f355de8e226942085808bb4','fixed C4 oracle manifest')
                manifest=H.load(c4/'manifest.json');C.verify_oracles(c4,manifest,None)
                for name,digest in manifest['pins'].items():
                    if name.startswith(('controls/','entrypoints/')):H.require(H.sha(c4/name)==digest,'frozen C4 control '+name)
                old=ROOT/'tools/performance/a1-private-index/controls'
                H.require(H.sha(old/'manifest.json')=='646d48bbf94d41e9b29aca5f357a35f1b078e60c7b12ad51441fdaab970d5029','fixed A1 oracle manifest')
                a1=H.load(old/'manifest.json')
                for name,digest in a1['files'].items():H.require(H.sha(old/name)==digest,'frozen A1 control '+name)
                A.prepare(source,out/'source')
                for name in ['OracleTypes.hs','PatriciaOracleControls.hs']:shutil.copy2(HERE/name,out/'source'/name)
                modules=['PatriciaOracleControls','PublicControls','C4TransactionControls','SessionTests','AdmissionTests','HeteroinputControls']
                if a.suite=='validation':
                    V=H.module(ROOT/'tools/performance/validation-reuse/source_contract.py','validation_contract')
                    raw=(source/V.OWNER).read_bytes()
                    H.require(raw.count(b'IntMapTree Node')==3,'three collection representation type signatures')
                    historical=raw.replace(b'IntMapTree Node',b'Map Int Node')
                    previous=V.restore_previous_owner(historical).replace(b'Map Int Node',b'IntMapTree Node')
                    H.require(H.sha(source/V.CONSTRAINT)==V.CONSTRAINT_SHA,'unchanged generated constraint owner')
                    for name,data in [('V1FrozenSession',previous),('V1SessionUnderTest',raw)]:
                        old_header=b'module Bootstrap.CrateSession (compileSpecFile) where {'
                        new_header=('module '+name+' where {').encode()
                        H.require(data.count(old_header)==1,'one private session header')
                        changed=data.replace(old_header,new_header)
                        H.require(changed.replace(new_header,old_header)==data,'private export-only inverse')
                        (out/'source'/(name+'.hs')).write_bytes(changed)
                    control=ROOT/'tools/performance/validation-reuse/BoundaryControls.hs'
                    pins=H.load(HERE/'legacy-controls-pins.json')['files']
                    H.require(H.sha(control)==pins[str(control.relative_to(ROOT))],'frozen boundary cases')
                    (out/'source'/'BoundaryControls.hs').write_text(control.read_text().replace('module Main where','module BoundaryControls where'))
                    modules=['BoundaryControls']
            elif a.suite=='builtin':
                (out/'source').mkdir()
                control=ROOT/'tools/performance/a1-private-index/current/CurrentBuiltinControls.hs'
                pins=H.load(HERE/'legacy-controls-pins.json')['files']
                H.require(H.sha(control)==pins[str(control.relative_to(ROOT))],'original builtin malformed controls')
                shutil.copy2(control,out/'source'/control.name)
                fixture=out/'Fixture.emlf';fixture.write_text('module Fixture where\nvalue = 42\n')
                pack=lambda xs:''.join(str(len(x))+':'+x for x in xs)
                spec=out/'fixture.spec';builtin=out/'builtin';target=out/'fixture'
                spec.write_text(pack(['MLF-CRATE-1','patricia-integrated/fixture','','false',pack([pack(['Fixture',str(fixture)])]),'',str(out/'queries'),str(builtin)]))
                H.Runner(out,LIMITS).run([producer/'bin/emlf','--compile-crate',spec,'-o',target],source,out/'prepare-builtin')
                report=H.load(str(target)+'.queries')
                H.require(report['inferred_groups']==1 and report['reused_groups']==0 and len(report['groups'])==1 and report['groups'][0]['cached'] is False,'one fresh builtin fixture group')
                record['builtin_pins']={str(builtin)+suffix:H.sha(str(builtin)+suffix) for suffix in ['.mlfci','.mlfco']}
                modules=['CurrentBuiltinControls']
            else:modules,_=prepare(ROOT,out/'source',a.suite)
            objects=out/'objects';shutil.copytree(producer/'objects',objects)
            original=H.file_pins(objects);record['control_sources']=H.file_pins(out/'source')
            ledger=out/'source/adaptations.json'
            if ledger.exists():
                record['original_control_inputs']={row['source']:row['source_sha256'] for row in H.load(ledger)['changes']}
                H.check_pins(record['original_control_inputs'])
                if a.suite in ['graph','validation']:
                    for path,digest in record['original_control_inputs'].items():
                        H.require(H.sha(ROOT/Path(path).relative_to(source))==digest,'copied control/source matches reviewed checkout')
            flags=[]
            for token in auth['flags']:
                flags.append(str(objects) if token==str(producer/'objects') else token)
                if token=='-i':flags.append('-i'+str(out/'source'))
            for module in modules:
                entry=out/(module+'Main.hs')
                entry.write_text('module Main where\nimport qualified '+module+' as C\nmain :: IO ()\nmain=C.'+('boundary' if module=='PatriciaOracleControls' else 'main')+'\n')
                binary=out/(module+'-binary');extra=['-package','filepath'] if module=='P2Controls' else []
                H.Runner(out,LIMITS).run([auth['ghc']['path'],'--make','-j1',*flags,*extra,'-rtsopts=ignoreAll',entry,producer/'host.o',producer/'supervisor.o','-o',binary],source,out/(module+'-build'))
                args=[out/'fingerprint-output'] if module=='P2Controls' else [builtin] if module=='CurrentBuiltinControls' else []
                H.Runner(out,LIMITS).run([binary,*args],source,out/(module+'-run'))
                stdout=(out/(module+'-run')/'stdout').read_bytes();stderr=(out/(module+'-run')/'stderr').read_bytes()
                H.require(not stderr,'control stderr empty '+module)
                if module=='P2Controls':
                    oracle=(out/'source/FrozenFingerprint.hs').read_text()
                    H.require(oracle.startswith('{-# OPTIONS_GHC -fno-enable-rewrite-rules -fomit-interface-pragmas -dcore-lint #-}\n'),'P2 oracle isolation retained')
                    record['frozen_P2_rewrite_rules_disabled']=True
                    record['frozen_P2_interface_unfoldings_omitted']=True
                if module in ['P1Controls','P2Controls','P3Controls']:
                    summaries=[json.loads(s) for s in stdout.decode().splitlines() if s.startswith('{')]
                    H.require(len(summaries)==1 and summaries[0]['complete'] is True,'one complete summary')
                    H.require(summaries[0]['differential_controls' if module=='P3Controls' else 'checks']==dict(P1Controls=154072,P2Controls=2503,P3Controls=929)[module],'all retained control cases')
                if module=='NativeCompatibilityControls':
                    H.require(stdout==b'{"complete":true,"native_compatibility_controls":1243}\n',
                              'all frozen supplemental P2 native-integration controls')
                    record['native_compatibility_controls']=1243
                if module=='CurrentBuiltinControls':H.require(stdout==b'PASS current builtin: canonical literal, full check, exact wire, 7 malformed/mismatch rejections\n','retained canonical builtin controls')
                if module=='BoundaryControls':H.require(stdout==b'PASS validation reuse: 20 authored programs, raw solver states, skeleton demand, 3 raw rejections, 4 partial-value orders\n','retained validation reuse boundary inventory')
                if module=='BalanceControls':H.require(stdout==b'Balance controls: 24649 raw-shape pairs; 400 mutation steps; 30 independent demand/order cases passed\n','complete Map balance inventory')
                if module=='PublicControls':record['public']=C.public_result(stdout,stderr)
                if module=='C4TransactionControls':
                    summary=json.loads(stdout.decode().splitlines()[-1]);expected=dict(C.TRANSACTION)
                    del expected['oracle_boundary_checks'];del expected['old_public_physical_oracle_weakened']
                    expected.update(old_BST_representation_preserved=False,Patricia_representation_independently_checked=True,oracle_boundary_suite='PatriciaOracleControls')
                    C.exact_fields(summary,expected)
                    H.require(sum(s.startswith('PASS ') for s in stdout.decode().splitlines())==9,'nine retained transaction groups')
                    record['transaction']=summary
                if module=='SessionTests':H.require(stdout==a1['expected_stdout'].encode(),'all original session cases')
                if module=='AdmissionTests':H.require(stdout==a1['admission_expected_stdout'].encode(),'all original admission cases')
                if module=='HeteroinputControls':
                    migrated=json.loads(json.dumps(manifest))
                    for fixture in migrated['authored_matrix_fixtures']:
                        fixture['label']=fixture['label'].replace('beyond-machine-Integer-identities','wide-signed-Int64-identities')
                    migrated['matrix']['coordinates'][2][1]=str(-(2**60))
                    record['heteroinput']=C.heteroinput_result(stdout,stderr,migrated)
                    record['heteroinput_coordinate_migration']={'old':str(-(10**40)),'new':str(-(2**60)),'stride':7,'all_216_cases_retained':True}

                record['checks'].append(module);save()
            if a.suite in ['graph','validation']:
                negatives=[]
                if a.suite=='graph':
                    negatives=[(row['name'],old/row['source'],row['required_error_fragments'],row['expected_error_count']) for row in a1['negative_cases']]
                else:
                    for name in ['solveGenerated','prepareValidatedGraph','solvePreparedGraph']:
                        path=out/(name+'.hs');path.write_text('module PrivateAccess where\nimport Bootstrap.CrateSession ('+name+')\n')
                        negatives.append((name,path,['does not export',name],1))
                for name,path,fragments,count in negatives:
                    log=out/('private-'+name)
                    H.Runner(out,LIMITS).run([auth['ghc']['path'],*flags,'-c',path],source,log,expected_exit=1)
                    error=(log/'stderr').read_text()
                    H.require(all(v in error for v in fragments) and 'Could not find module' not in error and error.count('error:')==count,'exact private access rejection '+name)
                    record['checks'].append('private-'+name)
            changed=[p for p,digest in original.items() if Path(p).name not in ['Main.o','Main.hi'] and H.sha(p)!=digest]
            H.require(not changed,'ordinary production objects unchanged: '+str(changed))
            H.check_pins(record['driver_inputs']);H.check_pins(record.get('original_control_inputs',{}));H.check_pins(record.get('builtin_pins',{}))
            H.check_pins(record['control_sources']);H.require(H.authenticate(producer,source)==auth,'producer unchanged')
            record.update(complete=True,ordinary_production_objects_unchanged=True);save()
    except BaseException as e:record['error']=repr(e);save();raise
    print('PASS explicit Int64/Patricia migration controls: '+a.suite,flush=True)
if __name__=='__main__':main()
