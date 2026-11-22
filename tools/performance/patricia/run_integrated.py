#!/usr/bin/env python3
"""Retained finite regressions across the explicitly reviewed Int64/Patricia ABI."""
from pathlib import Path
import argparse, difflib, hashlib, json, shutil, sys, types, struct, zlib
from legacy_controls import prepare
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'tools/testing'))
from receipt_selection import inventory_json, select

PREFIX = 'patricia-integrated/'
GRAPH_MODULES = ('PatriciaOracleControls', 'PublicControls', 'C4TransactionControls',
                 'SessionTests', 'AdmissionTests', 'HeteroinputControls')
VALIDATION_NEGATIVES = ('solveGenerated', 'prepareValidatedGraph', 'solvePreparedGraph')
SUITES = {
    'p123': ('P1Controls', 'P2Controls', 'NativeCompatibilityControls', 'P3Controls'),
    'map-balance': ('BalanceControls',),
    'graph': GRAPH_MODULES,
    'validation': ('BoundaryControls', *['private-'+name for name in VALIDATION_NEGATIVES]),
    'builtin': ('BinaryBuiltinControls',),
}
LIMITS={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,
        'host_available_floor_bytes':3*1024**3,'max_work_bytes':3*1024**3,
        'process_tree_rss_bytes':5*1024**3,'wall_seconds':1200}

SCOPE_BRIDGE = '''
auditLiveScopeState :: String -> T.Solver -> IO ()
auditLiveScopeState label value@(T.Solver graph _ _ _) = do
  checked <- right (label ++ " raw live index audit") (S.finish value)
  assert (label ++ " live finish preserves physical graph") (sameGraphPhysical graph checked)

-- Live indexes retain only the levels required by the scope depth.
-- Audit the raw state and use the frozen solver solely for the omitted tail.
withFrozenScopeTail :: String -> T.Solver -> IO T.Solver
withFrozenScopeTail label value@(T.Solver graph parents bindings (T.ScopeIndex intervals jumps)) =
  case FS.finish value of
    T.Right _ -> pure value
    T.Left _ -> do
      auditLiveScopeState label value
      frozen <- right (label ++ " independent frozen scope reconstruction") (FS.prepare graph)
      case frozen of
        T.Solver _ _ _ (T.ScopeIndex frozenIntervals frozenJumps) -> do
          assert (label ++ " exact frozen intervals") (sameMapPhysical (==) intervals frozenIntervals)
          assert (label ++ " exact retained frozen jump prefix")
            (length jumps < length frozenJumps && and (zipWith (sameMapPhysical (==)) jumps frozenJumps))
          pure (T.Solver graph parents bindings (T.ScopeIndex intervals (jumps ++ drop (length jumps) frozenJumps)))

frozenScopeComparison :: String -> T.Solver -> T.Solver -> IO (T.Solver, T.Solver)
frozenScopeComparison label old@(T.Solver _ _ _ a) new@(T.Solver _ _ _ b)
  | sameScopesPhysical a b = pure (old,new)
  | otherwise = do
      old' <- withFrozenScopeTail (label ++ " reference") old
      new' <- withFrozenScopeTail (label ++ " actual") new
      pure (old',new')

'''


def adapt_compact_scope_checks(H, directory):
    """Extend test projections while retaining the prior staged and original bytes."""
    ledger_path = directory / 'adaptations.json'
    ledger = H.load(ledger_path)
    session_header = 'checkSolver :: String -> Bool -> T.Solver -> T.Solver -> IO ()\n'
    transaction_edits = {
        'checkTransactional label old new = do\n':
            'checkTransactional label rawOld rawNew = do\n'
            '  O.auditLiveScopeState label rawNew\n'
            '  old <- O.withFrozenScopeTail (label ++ " reference") rawOld\n'
            '  new <- O.withFrozenScopeTail (label ++ " actual") rawNew\n'
            '  checkHistoricalInputTransaction label old new\n\n'
            '-- Low-level operations on an explicitly frozen input preserve that scope index.\n'
            'checkHistoricalInputTransaction :: String -> T.Solver -> T.Solver -> IO ()\n'
            'checkHistoricalInputTransaction label old new = do\n',
        'checkTransactionalOutcome label expected actual = case (expected,actual) of\n':
            'checkTransactionalOutcome = checkOutcomeWith checkTransactional\n\n'
            'checkHistoricalInputOutcome :: String -> T.Either B.String T.Solver -> T.Either B.String T.Solver -> IO ()\n'
            'checkHistoricalInputOutcome = checkOutcomeWith checkHistoricalInputTransaction\n\n'
            'checkOutcomeWith :: (String -> T.Solver -> T.Solver -> IO ()) -> String -> T.Either B.String T.Solver -> T.Either B.String T.Solver -> IO ()\n'
            'checkOutcomeWith compareSolvers label expected actual = case (expected,actual) of\n',
        '(T.Right a,T.Right b) -> checkTransactional label a b':
            '(T.Right a,T.Right b) -> compareSolvers label a b',
    }
    edits = {
        'SessionOracle.hs': {
            session_header: SCOPE_BRIDGE + session_header,
            'checkSolver label physical old new=do\n':
                'checkSolver label physical rawOld rawNew=do\n'
                '  if physical then pure () else auditLiveScopeState label rawNew\n'
                '  (old,new)<-frozenScopeComparison label rawOld rawNew\n',
            '    _<-right (label++" frozen final index audit") (FS.finish new)\n':
                '    forAudit<-withFrozenScopeTail label new\n'
                '    _<-right (label++" frozen final index audit") (FS.finish forAudit)\n',
        },
        'TransactionOracle.hs': transaction_edits,
        'C4TransactionOracle.hs': transaction_edits,
        'C4TransactionControls.hs': {
            'checkTransactionalOutcome "canonical/filter/missing equation first error"':
                'checkHistoricalInputOutcome "canonical/filter/missing equation first error"',
            'checkTransactionalOutcome "direct complete Graph history restoration"':
                'checkHistoricalInputOutcome "direct complete Graph history restoration"',
            'checkTransactionalOutcome "restore inverse escaped alias exact rejection"':
                'checkHistoricalInputOutcome "restore inverse escaped alias exact rejection"',
        },
    }
    adapted = set()
    for entry in ledger['changes']:
        path = Path(entry['adapted'])
        if path.name not in edits:
            continue
        H.require(path == directory / path.name and path.name not in adapted, 'unique scope projection ' + path.name)
        H.require(H.sha(path) == entry['adapted_sha256'], 'exact prior scope projection ' + path.name)
        original = Path(entry['source'])
        H.require(H.sha(original) == entry['source_sha256'], 'unchanged frozen scope control ' + path.name)
        before = path.read_text()
        after = before
        for old, new in edits[path.name].items():
            H.require(after.count(old) == 1, 'exact scope bridge anchor ' + path.name)
            after = after.replace(old, new, 1)
        raw = original.read_text()
        for basis, suffix in ((raw, '.ndiff'), (before, '.scope.ndiff')):
            delta = list(difflib.ndiff(basis.splitlines(keepends=True), after.splitlines(keepends=True)))
            H.require(''.join(difflib.restore(delta, 1)) == basis and
                      ''.join(difflib.restore(delta, 2)) == after, 'reversible scope projection ' + path.name)
            (directory / (path.name + suffix)).write_text(''.join(delta))
        entry['scope_bridge_preimage_sha256'] = entry['adapted_sha256']
        path.write_text(after)
        entry['adapted_sha256'] = H.sha(path)
        adapted.add(path.name)
    H.require(adapted == set(edits), 'complete scope projection inventory')
    H.save(ledger_path, ledger)


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
            inventory = json.loads((ROOT/'tools/performance/a1-private-index/controls/manifest.json').read_text())
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
            'driver_inputs':{str(p):H.sha(p) for p in [Path(__file__),HERE/'adapt_oracles.py',HERE/'legacy_controls.py',HERE/'legacy-controls-pins.json',hp,ROOT/'tools/performance/c4-local-transaction/contracts.py',ROOT/'tools/testing/receipt_selection.py']}}
    save=lambda:H.save(out/'receipt.json',record)
    save()
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            auth=H.authenticate(producer,source)
            M=H.module(HERE/'source_migration.py','binary_source_migration')
            binary=M.binary_contract(source)
            binary.require_registry({name:row['sha256'] for name,row in auth['shared_inputs'].items()},'current')
            binary.live_registry(source);binary.live_host_inventory(source)
            for path in [HERE/'source_migration.py',
                         *[binary.directory / name for name in binary.metadata_paths]]:
                record['driver_inputs'][str(path)]=H.sha(path)
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
                adapt_compact_scope_checks(H, out/'source')
                for name in ['OracleTypes.hs','PatriciaOracleControls.hs']:
                    current_control = HERE / name
                    record['driver_inputs'][str(current_control)] = H.sha(current_control)
                    shutil.copy2(current_control, out/'source'/name)
                modules=GRAPH_MODULES
                if a.suite=='validation':
                    V=H.module(ROOT/'tools/performance/validation-reuse/source_contract.py','validation_contract')
                    raw=(source/V.OWNER).read_bytes()
                    # Source-proof inverse only; V1SessionUnderTest keeps raw binary source.
                    collection_source=A.project_binary_owner(raw, source)
                    if b'Source.prepareGroupOwned' in collection_source:
                        sparse_path=ROOT/'tools/performance/sparse-contracts/source_contract.py'
                        for path in [sparse_path,sparse_path.with_name('session-delta.json')]:
                            record['driver_inputs'][str(path)]=H.sha(path)
                        collection_source=A.without_sparse_contracts(collection_source)
                        record['sparse_contracts_driver_projection']='Exact combined sparse and owned session delta inverted for source proof; runtime candidate remains unprojected.'
                    if b'runSourceGroupsWithOwnedContracts' in collection_source:
                        contract_path=ROOT/'tools/performance/contract-context/source_contract.py'
                        for path in [contract_path,contract_path.with_name('session-delta.json')]:
                            record['driver_inputs'][str(path)]=H.sha(path)
                        Q=H.module(contract_path,'contract_context_contract')
                        collection_source=Q.restore_previous_owner(collection_source)
                    if b'runSourceGroupsWithContext' in collection_source:
                        datatype_contract=ROOT/'tools/performance/datatype-context/source_contract.py'
                        for path in [datatype_contract,datatype_contract.with_name('session-delta.json')]:
                            record['driver_inputs'][str(path)]=H.sha(path)
                        Q=H.module(datatype_contract,'datatype_context_contract')
                        collection_source=Q.restore_previous_owner(collection_source)
                        record['datatype_context_driver_projection']='Exact four reviewed driver edits inverted for the retained source proof; runtime candidate remains unprojected.'
                    rank_view=b'Rank.MapIndex Node' in raw
                    collection_source=A.without_rank_view(collection_source) if rank_view else collection_source
                    H.require(collection_source.count(b'IntMapTree Node')==3,'three collection representation type signatures')
                    historical=collection_source.replace(b'IntMapTree Node',b'Map Int Node')
                    previous=V.restore_previous_owner(historical).replace(b'Map Int Node',b'IntMapTree Node')
                    if rank_view:previous=A.with_rank_view(previous)
                    constraint = (source/V.CONSTRAINT).read_bytes()
                    prior = binary.restore_path(constraint, V.CONSTRAINT)
                    H.require(hashlib.sha256(prior).hexdigest()==V.CONSTRAINT_SHA,'exact historical generated constraint owner')
                    record['validation_constraint']={'live_sha256':hashlib.sha256(constraint).hexdigest(),
                        'projected_historical_sha256':V.CONSTRAINT_SHA}
                    for name,data in [('V1FrozenSession',previous),('V1SessionUnderTest',raw)]:
                        old_header=(A.LIVE_SESSION_HEADER.encode() if name=='V1SessionUnderTest' else
                                    b'module Bootstrap.CrateSession (compileSpecFile) where {')
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
            H.check_pins(record['driver_inputs']);H.check_pins(record.get('original_control_inputs',{}));H.check_pins(record.get('builtin_pins',{}));H.check_pins(record.get('builtin_witness_pins',{}))
            H.check_pins(record['control_sources']);H.require(H.authenticate(producer,source)==auth,'producer unchanged')
            record.update(complete=True,ordinary_production_objects_unchanged=True);save()
    except BaseException as e:record['error']=repr(e);save();raise
    print('PASS explicit Int64/Patricia migration controls: '+a.suite,flush=True)
if __name__=='__main__':main()
