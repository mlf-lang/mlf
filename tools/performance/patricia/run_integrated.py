#!/usr/bin/env python3
"""Retained finite regressions across the explicitly reviewed Int64/Patricia ABI."""
from pathlib import Path
import argparse, json, shutil, sys, types, struct, zlib
from legacy_controls import prepare
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
GRAPH_EXPECTATIONS=HERE/'controls/graph/expectations.json'
sys.path.insert(0, str(ROOT/'tools/testing'))
from receipt_selection import inventory_json, select

PREFIX = 'patricia-integrated/'
GRAPH_MODULES = ('PatriciaOracleControls', 'PublicControls', 'C4TransactionControls',
                 'SessionTests', 'AdmissionTests', 'HeteroinputControls')
VALIDATION_NEGATIVES = ('solveGenerated', 'prepareValidatedGraph', 'solvePreparedGraph')
SUITES = {
    'p123': ('P1Controls', 'P2Controls', 'NativeCompatibilityControls', 'P3Controls'),
    'graph': GRAPH_MODULES,
    'validation': ('BoundaryControls', *['private-'+name for name in VALIDATION_NEGATIVES]),
    'builtin': ('BinaryBuiltinControls',),
}
LIMITS={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,
        'host_available_floor_bytes':3*1024**3,'max_work_bytes':3*1024**3,
        'process_tree_rss_bytes':5*1024**3,'wall_seconds':1200}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    listing = '--framework-list' in sys.argv[1:]
    p.add_argument('--framework-list', action='store_true')
    p.add_argument('--suite',choices=SUITES,required=not listing)
    p.add_argument('--producer',type=Path,required=not listing)
    p.add_argument('--source',type=Path,default=ROOT)
    p.add_argument('--output',type=Path,required=not listing)
    a=p.parse_args()
    labels = []
    for suite in ([a.suite] if a.suite else SUITES):
        labels.extend(SUITES[suite])
        if suite == 'graph':
            inventory = json.loads(GRAPH_EXPECTATIONS.read_text())
            labels.extend('private-'+row['name'] for row in inventory['negative_cases'])
    exact = select(PREFIX, labels)
    planned = [exact] if exact is not None else labels
    if a.framework_list:
        print(inventory_json(PREFIX, planned))
        return
    out=a.output.resolve();producer=a.producer.resolve();source=a.source.resolve()
    if out.exists() or out.is_relative_to(producer) or producer.is_relative_to(out) or ROOT.is_relative_to(out):
        p.error('fresh output separate from the producer and source ancestors required')
    out.mkdir(parents=True)
    hp=ROOT/'tools/performance/a1-private-index/helper.py'
    H=types.ModuleType('guard');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    record={'complete':False,'suite':a.suite,'performance_measured':False,
            'ABI_migration':'Haskell Int64 arithmetic; Patricia public collection representation',
            'historical_unbounded_or_BST_contract_claimed':False,'checks':[],'planned_checks':planned,
            'driver_inputs':{str(p):H.sha(p) for p in [Path(__file__),HERE/'adapt_oracles.py',HERE/'legacy_controls.py',HERE/'frozen_oracles.py',HERE/'runtime_sources.py',hp,ROOT/'tools/performance/c4-local-transaction/contracts.py',ROOT/'tools/testing/receipt_selection.py']}}
    save=lambda:H.save(out/'receipt.json',record)
    save()
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            auth=H.authenticate(producer,source)
            record['producer_receipt_sha256']=H.sha(producer/'receipt.json')
            if a.suite in ['graph','validation']:
                A=H.module(HERE/'adapt_oracles.py','adapter')
                C=H.module(ROOT/'tools/performance/c4-local-transaction/contracts.py','contracts')
                expectations=H.load(GRAPH_EXPECTATIONS)
                record['driver_inputs'][str(GRAPH_EXPECTATIONS)]=H.sha(GRAPH_EXPECTATIONS)
                record['control_inputs']=A.prepare(ROOT,out/'source',source_root=source)
                modules=GRAPH_MODULES
                if a.suite=='validation':
                    record['control_inputs'].update(A.prepare_validation(ROOT,out/'source',source_root=source))
                    record['validation_reference']='fixed pre-optimization oracle; current session authenticated by producer receipt'
                    modules=['BoundaryControls']
            elif a.suite=='builtin':
                (out/'source').mkdir()
                control=ROOT/'tools/performance/a1-private-index/current/CurrentBuiltinControls.hs'
                shutil.copy2(control,out/'source'/control.name)
                binary_control=ROOT/'tools/performance/artifact-binary/BinaryBuiltinControls.hs'
                record['driver_inputs'][str(binary_control)]=H.sha(binary_control)
                record['driver_inputs'][str(control)]=H.sha(control)
                shutil.copy2(binary_control,out/'source'/binary_control.name)
                fixture=out/'Fixture.emlf';fixture.write_text('module Fixture where\nvalue = 42\n')
                pack=lambda xs:''.join(str(len(x))+':'+x for x in xs)
                spec=out/'fixture.spec';builtin=out/'builtin';target=out/'fixture'
                spec.write_text(pack(['MLF-CRATE-1','patricia-integrated/fixture','','false',pack([pack(['Fixture',str(fixture)])]),'',str(out/'queries'),str(builtin)]))
                H.Runner(out,LIMITS).run([producer/'bin/emlf','--compile-crate',spec,'-o',target],source,out/'prepare-builtin')
                report=H.load(str(target)+'.queries')
                H.require(report['inferred_groups']==1 and report['reused_groups']==0 and len(report['groups'])==1 and report['groups'][0]['cached'] is False,'one fresh builtin fixture group')
                record['builtin_pins']={str(builtin)+suffix:H.sha(str(builtin)+suffix) for suffix in ['.mlfci','.mlfco']}
                # Independent standard-library envelope/CRC inspection of the
                # actual default files; the Haskell control checks typed semantics.
                record['binary_builtin_wire']={}
                for suffix,schema in [('.mlfci',3),('.mlfco',4)]:
                    raw=Path(str(builtin)+suffix).read_bytes()
                    H.require(len(raw)>=80 and raw[:8]==b'MLFBIN\r\n','actual binary builtin '+suffix)
                    fields=struct.unpack('<18I',raw[8:80])
                    H.require(fields[:4]==(1,0,schema,80) and fields[4]==len(raw),'binary builtin envelope '+suffix)
                    crc=zlib.crc32(raw[:76]+b'\0'*4+raw[80:]) & 0xffffffff
                    H.require(crc==fields[17],'independent binary builtin CRC '+suffix)
                    record['binary_builtin_wire'][suffix]={'schema':schema,'bytes':len(raw),'crc32':crc,'sha256':H.sha(str(builtin)+suffix)}
                modules=['BinaryBuiltinControls']
            else:
                modules,record['control_inputs']=prepare(ROOT,out/'source',a.suite)
            objects=out/'objects';shutil.copytree(producer/'objects',objects)
            original=H.file_pins(objects);record['control_sources']=H.file_pins(out/'source')
            H.check_pins(record.get('control_inputs',{}))
            flags=[]
            for token in auth['flags']:
                flags.append(str(objects) if token==str(producer/'objects') else token)
                if token=='-i':flags.append('-i'+str(out/'source'))
            for module in modules:
                if module not in planned:
                    continue
                entry=out/(module+'Main.hs')
                entry.write_text('module Main where\nimport qualified '+module+' as C\nmain :: IO ()\nmain=C.'+('boundary' if module=='PatriciaOracleControls' else 'main')+'\n')
                binary=out/(module+'-binary');extra=['-package','filepath'] if module=='P2Controls' else []
                H.Runner(out,LIMITS).run([auth['ghc']['path'],'--make','-j1',*flags,*extra,'-rtsopts=ignoreAll',entry,producer/'host.o',producer/'supervisor.o','-o',binary],source,out/(module+'-build'))
                args=[out/'fingerprint-output'] if module=='P2Controls' else [builtin] if module=='BinaryBuiltinControls' else []
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
                if module=='BinaryBuiltinControls':
                    H.require(stdout==b'PASS current builtin: canonical literal, full check, exact wire, 7 malformed/mismatch rejections\nPASS binary builtin: public readers, canonical bytes, fixed literal/full check, 5 binary rejections, separate frozen legacy 7\n','binary controls and all retained explicit legacy builtin controls')
                    record['builtin_controls']={'legacy_frozen_rejections':7,'binary_rejections':5,'original_default_files_remain_binary':True}
                    record['builtin_witness_pins']={str(builtin)+suffix:H.sha(str(builtin)+suffix) for suffix in ['.explicit-legacy.mlfci','.explicit-legacy.mlfco','.binary-negative-version','.binary-negative-crc','.binary-negative-pairing']}
                if module=='BoundaryControls':H.require(stdout==b'PASS validation reuse: 20 authored programs, raw solver states, skeleton demand, 3 raw rejections, 4 partial-value orders\n','retained validation reuse boundary inventory')
                if module=='PublicControls':record['public']=C.public_result(stdout,stderr)
                if module=='C4TransactionControls':record['transaction']=C.transaction_result(stdout,stderr)
                if module=='SessionTests':H.require(stdout==expectations['session_stdout'].encode(),'all original session cases')
                if module=='AdmissionTests':H.require(stdout==expectations['admission_stdout'].encode(),'all original admission cases')
                if module=='HeteroinputControls':
                    record['heteroinput']=C.heteroinput_result(stdout,stderr,expectations)

                record['checks'].append(module);save()
            if a.suite in ['graph','validation']:
                negatives=[]
                if a.suite=='graph':
                    negatives=[(row['name'],ROOT/row['source'],row['required_error_fragments'],row['expected_error_count']) for row in expectations['negative_cases']]
                    record['control_inputs'].update({str(path):H.sha(path) for _,path,_,_ in negatives})
                else:
                    for name in VALIDATION_NEGATIVES:
                        if 'private-'+name not in planned:
                            continue
                        path=out/(name+'.hs');path.write_text('module PrivateAccess where\nimport Bootstrap.CrateSession ('+name+')\n')
                        negatives.append((name,path,['does not export',name],1))
                for name,path,fragments,count in negatives:
                    if 'private-'+name not in planned:
                        continue
                    log=out/('private-'+name)
                    H.Runner(out,LIMITS).run([auth['ghc']['path'],*flags,'-c',path],source,log,expected_exit=1)
                    error=(log/'stderr').read_text()
                    H.require(all(v in error for v in fragments) and 'Could not find module' not in error and error.count('error:')==count,'exact private access rejection '+name)
                    record['checks'].append('private-'+name)
            changed=[p for p,digest in original.items() if Path(p).name not in ['Main.o','Main.hi'] and H.sha(p)!=digest]
            H.require(not changed,'ordinary production objects unchanged: '+str(changed))
            H.check_pins(record['driver_inputs']);H.check_pins(record.get('control_inputs',{}));H.check_pins(record.get('builtin_pins',{}));H.check_pins(record.get('builtin_witness_pins',{}))
            H.check_pins(record['control_sources']);H.require(H.authenticate(producer,source)==auth,'producer unchanged')
            record.update(complete=True,ordinary_production_objects_unchanged=True);save()
    except BaseException as e:record['error']=repr(e);save();raise
    print('PASS explicit Int64/Patricia migration controls: '+a.suite,flush=True)
if __name__=='__main__':main()
