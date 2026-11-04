"""Fail-closed checks for the numeric ABI's test-only adapters and Core proof."""
from pathlib import Path
import difflib
import hashlib
import json
import importlib.util
import tempfile
import unittest
from unittest.mock import patch

import adapt_oracles as graph
import legacy_controls as legacy
import run_fingerprint as fingerprint
import source_migration as migration

ROOT = Path(__file__).resolve().parents[3]
resource_spec=importlib.util.spec_from_file_location('patricia_resource_source_migration',
    ROOT/'tools/shared/resource_source_migration.py')
resource=importlib.util.module_from_spec(resource_spec)
resource_spec.loader.exec_module(resource)
datatype_spec=importlib.util.spec_from_file_location('datatype_context_contract',
    ROOT/'tools/performance/datatype-context/source_contract.py')
datatype=importlib.util.module_from_spec(datatype_spec)
datatype_spec.loader.exec_module(datatype)
contract_spec=importlib.util.spec_from_file_location('contract_context_contract',
    ROOT/'tools/performance/contract-context/source_contract.py')
contract=importlib.util.module_from_spec(contract_spec)
contract_spec.loader.exec_module(contract)
sparse_spec=importlib.util.spec_from_file_location('sparse_contracts_contract',
    ROOT/'tools/performance/sparse-contracts/source_contract.py')
sparse=importlib.util.module_from_spec(sparse_spec)
sparse_spec.loader.exec_module(sparse)

c3_spec=importlib.util.spec_from_file_location('c3_session_contract',
    ROOT/'tools/performance/c3-delayed-index/source_contract.py')
c3=importlib.util.module_from_spec(c3_spec)
c3_spec.loader.exec_module(c3)
survivors_spec=importlib.util.spec_from_file_location('c3_survivor_contract',
    ROOT/'tools/performance/c3-survivors/source_contract.py')
survivors=importlib.util.module_from_spec(survivors_spec)
survivors_spec.loader.exec_module(survivors)
full_spec=importlib.util.spec_from_file_location('projection_patch_contract',
    ROOT/'tools/performance/full-compiler/source_contract.py')
full=importlib.util.module_from_spec(full_spec)
full_spec.loader.exec_module(full)

def current_resource_registry(base):
    # Keep the historical 128-owner endpoint separate from live resource bytes.
    historical=migration.migrate(base)
    return resource.authenticate_current_source(ROOT,historical)

def before_full_registry(base):
    return migration.apply_changes(migration.through_full_compiler(base),
        {name: {'old': row['new'], 'new': row['old'], 'reviewed_change': 'inverse test'}
         for name,row in migration.full_delta()['changed_sources'].items()})

def before_survivors_registry(base):
    return migration.apply_changes(before_full_registry(base),
        {name: {'old': row['new'], 'new': row['old'], 'reviewed_change': 'inverse test'}
         for name,row in migration.survivors_delta()['changed_sources'].items()})

def before_c3_registry(base):
    return migration.apply_changes(before_survivors_registry(base),
        {name: {'old': row['new'], 'new': row['old'], 'reviewed_change': 'inverse test'}
         for name,row in migration.c3_delta()['changed_sources'].items()})

def before_canonical_carry_registry(base):
    return migration.apply_changes(before_c3_registry(base),
        {name: {'old': row['new'], 'new': row['old'], 'reviewed_change': 'inverse test'}
         for name,row in migration.canonical_carry_delta()['changed_sources'].items()})

def before_permission_registry(base):
    previous=migration.apply_changes(before_canonical_carry_registry(base),
        {name: {'old': row['new'], 'new': row['old'], 'reviewed_change': 'inverse test'}
         for name,row in migration.permission_delta()['changed_sources'].items()})
    return previous

def before_sparse_registry(base):
    previous=migration.apply_changes(before_permission_registry(base),
        {name: {'old': row['new'], 'new': row['old'], 'reviewed_change': 'inverse test'}
         for name,row in migration.batch_delta()['changed_sources'].items()})
    return migration.apply_changes(previous,
        {name: {'old': row['new'], 'new': row['old'], 'reviewed_change': 'inverse test'}
         for name,row in migration.sparse_delta()['changed_sources'].items()})


class AdapterTests(unittest.TestCase):
    def test_numeric_tokens_preserve_string_fixtures_and_line_comments(self):
        source = 'import Prelude\nx :: Integer\nx = toInteger 3\ny = fromInteger 4\ns = "Integer toInteger fromInteger"\n-- Integer toInteger\n'
        changed = legacy.numeric_types(source)
        self.assertIn('import Data.Int (Int64)\n', changed)
        self.assertIn('x :: Int64\nx = fromIntegral 3\ny = fromIntegral 4', changed)
        self.assertIn('s = "Integer toInteger fromInteger"', changed)
        self.assertIn('-- Integer toInteger', changed)

    def test_p123_originals_restore_exactly_and_p2_stays_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)/'controls'
            modules, ledger = legacy.prepare(ROOT, out, 'p123')
            self.assertEqual(modules, ['P1Controls', 'P2Controls', 'NativeCompatibilityControls', 'P3Controls'])
            for row in ledger:
                before = Path(row['source']).read_bytes()
                after = Path(row['copy']).read_bytes()
                delta = (out/(Path(row['copy']).name+'.ndiff')).read_text().splitlines(keepends=True)
                self.assertEqual(''.join(difflib.restore(delta, 1)).encode(), before)
                self.assertEqual(''.join(difflib.restore(delta, 2)).encode(), after)
                self.assertEqual(hashlib.sha256(before).hexdigest(), row['source_sha256'])
            self.assertTrue((out/'FrozenFingerprint.hs').read_text().startswith(
                '{-# OPTIONS_GHC -fno-enable-rewrite-rules -fomit-interface-pragmas -dcore-lint #-}\n'))
            self.assertIn('(minBound,maxBound)',
                          (out/'P3Controls.hs').read_text())
            self.assertEqual((out/'NativeCompatibilityControls.hs').read_bytes(),
                (ROOT/'tools/performance/crate-optimizations/p2/NativeCompatibilityControls.hs').read_bytes())

    def test_changed_original_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'tools/performance/crate-optimizations/p1/FrozenSelectorMap.hs'
            path.parent.mkdir(parents=True)
            path.write_text('module FrozenSelectorMap where\n')
            with self.assertRaisesRegex(ValueError, 'frozen legacy control changed'):
                legacy.prepare(root, root/'adapted', 'p123')

    def test_private_export_adapter_rejects_missing_and_duplicate_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'tools').symlink_to(ROOT/'tools', target_is_directory=True)
            solver = root/'libraries/mlf-inference/Bootstrap/Graph/Solver.hs'
            solver.parent.mkdir(parents=True)
            solver.write_bytes((ROOT/solver.relative_to(root)).read_bytes())
            path = root/'libraries/mlf-crates/Bootstrap/CrateSession.hs'
            path.parent.mkdir(parents=True)
            for index,source in enumerate(['', 'module Bootstrap.CrateSession (compileSpecFile) where {\n'*2]):
                path.write_text(source)
                with self.assertRaisesRegex(ValueError, 'unique private header'):
                    graph.prepare(root,root/('out'+str(index)))

    def test_host_migration_accepts_only_explicit_historical_parents(self):
        manifest = json.loads((migration.HERE/'source-migration.json').read_text())
        key = 'host/ghc/MLF/Host/Base.hs'
        row = manifest['host_sources'][key]
        for field in ['old', 'retained_F1_parent']:
            self.assertEqual(migration.host_sources({key: row[field]}), {key: '50780c7183d62aa7568c0a799fdf5829b6ea60cbbc67cca7fd1a3f08bc4ba9c5'})
        with self.assertRaisesRegex(ValueError, 'exact frozen host parent'):
            migration.host_sources({key: '0'*64})

    def test_rank_view_adapter_is_exactly_reversible(self):
        source = (ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs').read_bytes()
        restored = graph.without_rank_view(source)
        self.assertEqual(graph.with_rank_view(restored), source)
        for bad in [source.replace(graph.RANK_IMPORT, b''),
                    source.replace(b'Rank.MapIndex Node', b'IntMapTree Node', 1)]:
            with self.assertRaises(ValueError):
                graph.without_rank_view(bad)

    def test_design_layer_keeps_old_manifest_and_rejects_corruption(self):
        old = (migration.HERE/'source-migration.json').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(), migration.MANIFEST_SHA)
        base = json.loads(old)['old_sources']
        self.assertEqual(len(migration.migrate(base)), 128)
        design = (migration.HERE/'index-design-migration.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'source-migration.json').write_bytes(old)
            for bad in [design+b' ', b'{}']:
                (root/'index-design-migration.json').write_bytes(bad)
                with patch.object(migration, 'HERE', root), self.assertRaises(ValueError):
                    migration.migrate(base)

    def test_rehashed_design_still_requires_exact_previous_sources(self):
        base = json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        design = migration.design_delta()
        for section in ['changed_sources', 'host_sources']:
            bad = json.loads(json.dumps(design))
            name = next(iter(bad[section]))
            bad[section][name]['old'] = '0'*64
            with patch.object(migration, 'design_delta', return_value=bad), self.assertRaises(ValueError):
                if section == 'changed_sources':
                    migration.migrate(base)
                else:
                    migration.host_sources({})

    def test_datatype_layer_preserves_the_exact_design_parent(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.datatype_delta()
        result=before_sparse_registry(base)
        result=migration.apply_changes(result, {name: {'old': row['new'], 'new': row['old'], 'reviewed_change': 'inverse test'} for name,row in migration.contract_delta()['changed_sources'].items()})
        self.assertEqual(len(result),128)
        for name,row in delta['changed_sources'].items():
            prior=migration.design_delta()['changed_sources'].get(name)
            if prior is None:
                numeric=json.loads((migration.HERE/'source-migration.json').read_bytes())
                prior=numeric['changed_sources'].get(name,{'new':numeric['old_sources'][name]})
            self.assertEqual(row['old'],prior['new'])
            self.assertEqual(result[name],row['new'])
        bad=json.loads(json.dumps(delta))
        bad['changed_sources']['Bootstrap.CrateQuery']['old']='0'*64
        with patch.object(migration,'datatype_delta',return_value=bad),self.assertRaises(ValueError):
            migration.migrate(base)

    def test_datatype_session_projection_preserves_previous_complete_owner(self):
        source=(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs').read_bytes()
        source=graph.without_delayed_indexes(source)
        source=sparse.restore_previous_owner(source)
        previous=datatype.restore_previous_owner(contract.restore_previous_owner(source))
        expected=migration.design_delta()['changed_sources']['Bootstrap.CrateSession']['new']
        self.assertEqual(hashlib.sha256(previous).hexdigest(),expected)
        source=contract.restore_previous_owner(source)
        edits=datatype.manifest()['edits']
        for bad in [source+b'\n',source.replace(edits[0]['new'].encode(),b'',1),
                    source+edits[0]['new'].encode()]:
            with self.assertRaises(ValueError):datatype.restore_previous_owner(bad)
        corrupted=json.loads(json.dumps(datatype.manifest()))
        corrupted['edits'][0]['old']+='\n'
        with patch.object(datatype,'manifest',return_value=corrupted),self.assertRaises(ValueError):
            datatype.restore_previous_owner(source)

    def test_contract_migration_and_session_projection_fail_closed(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.contract_delta()
        for name,row in delta['changed_sources'].items():
            self.assertEqual(row['old'],migration.datatype_delta()['changed_sources'][name]['new'])
            self.assertEqual(before_sparse_registry(base)[name],row['new'])
        bad=json.loads(json.dumps(delta))
        bad['changed_sources']['Bootstrap.CrateQuery']['old']='0'*64
        with patch.object(migration,'contract_delta',return_value=bad),self.assertRaises(ValueError):
            migration.migrate(base)
        source=(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs').read_bytes()
        source=graph.without_delayed_indexes(source)
        source=sparse.restore_previous_owner(source)
        previous=contract.restore_previous_owner(source)
        self.assertEqual(hashlib.sha256(previous).hexdigest(),delta['changed_sources']['Bootstrap.CrateSession']['old'])
        edits=contract.manifest()['edits']
        for value in [source+b'\n',source.replace(edits[0]['new'].encode(),b'',1),source+edits[0]['new'].encode()]:
            with self.assertRaises(ValueError):contract.restore_previous_owner(value)
        bad=json.loads(json.dumps(contract.manifest()))
        bad['edits'][0]['old']+='\n'
        with patch.object(contract,'manifest',return_value=bad),self.assertRaises(ValueError):
            contract.restore_previous_owner(source)
        original=(contract.HERE/'session-delta.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for value in [original+b' ',b'{}']:
                (root/'session-delta.json').write_bytes(value)
                with patch.object(contract,'HERE',root),self.assertRaises(ValueError):contract.manifest()

    def test_sparse_layer_has_exact_parent_and_current_five_owners(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.sparse_delta()
        previous=before_sparse_registry(base)
        current=current_resource_registry(base)
        paths={'Bootstrap.Classes':'libraries/mlf-inference/Bootstrap/Classes.hs',
               'Bootstrap.CrateQuery':'libraries/mlf-crates/Bootstrap/CrateQuery.hs',
               'Bootstrap.CrateSession':'libraries/mlf-crates/Bootstrap/CrateSession.hs',
               'Bootstrap.SourceInference':'libraries/mlf-crates/Bootstrap/SourceInference.hs',
               'MLF.BuiltinPreludeData':'bootstrap/MLF/BuiltinPreludeData.hs'}
        self.assertEqual(set(delta['changed_sources']),set(paths))
        for name,row in delta['changed_sources'].items():
            self.assertEqual(previous[name],row['old'])
            self.assertEqual(before_permission_registry(base)[name],row['new'])
            self.assertEqual(hashlib.sha256((ROOT/paths[name]).read_bytes()).hexdigest(),current[name])
        bad=json.loads(json.dumps(delta))
        bad['changed_sources']['Bootstrap.SourceInference']['old']='0'*64
        with patch.object(migration,'sparse_delta',return_value=bad),self.assertRaises(ValueError):
            migration.migrate(base)
        original=(migration.HERE.parent/'sparse-contracts/source-migration.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'sparse-contracts').mkdir()
            for value in [original+b' ',b'{}']:
                (root/'sparse-contracts/source-migration.json').write_bytes(value)
                with patch.object(migration,'HERE',root/'patricia'),self.assertRaises(ValueError):
                    migration.sparse_delta()

    def test_permission_layer_preserves_parent_and_exact_current_owners(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.permission_delta()
        result=before_canonical_carry_registry(base)
        current=current_resource_registry(base)
        self.assertEqual(delta['parent_manifest_sha256'],migration.BATCH_MANIFEST_SHA)
        paths={'Bootstrap.Graph':'libraries/mlf-inference/Bootstrap/Graph.hs',
               'MLF.BuiltinPreludeData':'bootstrap/MLF/BuiltinPreludeData.hs'}
        self.assertEqual(set(delta['changed_sources']),set(paths))
        for name,row in delta['changed_sources'].items():
            self.assertEqual(before_permission_registry(base)[name],row['old'])
            self.assertEqual(result[name],row['new'])
            self.assertEqual(hashlib.sha256((ROOT/paths[name]).read_bytes()).hexdigest(),current[name])
        bad=json.loads(json.dumps(delta))
        bad['changed_sources']['Bootstrap.Graph']['old']='0'*64
        with patch.object(migration,'permission_delta',return_value=bad),self.assertRaises(ValueError):
            migration.migrate(base)
        original=(migration.HERE.parent/'permission-view/source-migration.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'permission-view').mkdir()
            for value in [original+b' ',b'{}']:
                (root/'permission-view/source-migration.json').write_bytes(value)
                with patch.object(migration,'HERE',root/'patricia'),self.assertRaises(ValueError):
                    migration.permission_delta()

    def test_canonical_carry_has_exact_three_owners_and_125_unchanged_sources(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        previous=before_canonical_carry_registry(base)
        result=before_c3_registry(base)
        current=current_resource_registry(base)
        delta=migration.canonical_carry_delta()
        paths={'Bootstrap.Separate':'libraries/mlf-crates/Bootstrap/Separate.hs',
               'Bootstrap.CrateArtifact':'libraries/mlf-crates/Bootstrap/CrateArtifact.hs',
               'MLF.BuiltinPreludeData':'bootstrap/MLF/BuiltinPreludeData.hs'}
        self.assertEqual(set(delta['changed_sources']),set(paths))
        self.assertEqual(set(result),set(previous))
        self.assertEqual(len(result),128)
        self.assertEqual({n for n in result if result[n]!=previous[n]},set(paths))
        self.assertEqual({n:result[n] for n in result if n not in paths},
                         {n:previous[n] for n in previous if n not in paths})
        self.assertEqual(len(set(result)-set(paths)),125)
        for name,row in delta['changed_sources'].items():
            self.assertEqual(previous[name],row['old'])
            self.assertEqual(result[name],row['new'])
            self.assertEqual(migration.through_full_compiler(base)[name],row['new'])
            self.assertEqual(hashlib.sha256((ROOT/paths[name]).read_bytes()).hexdigest(),current[name])

    def test_canonical_carry_wrong_predecessors_and_registry_pollution_rejected(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.canonical_carry_delta()
        for name in delta['changed_sources']:
            bad=json.loads(json.dumps(delta));bad['changed_sources'][name]['old']='0'*64
            with self.subTest(name=name),patch.object(migration,'canonical_carry_delta',return_value=bad),self.assertRaises(ValueError):
                migration.migrate(base)
        missing=dict(base);missing.pop('Bootstrap.Graph')
        renamed={**missing,'Unexpected':base['Bootstrap.Graph']}
        polluted={**base,'Bootstrap.Graph':'0'*64}
        for bad in (missing,renamed,polluted,migration.migrate(base)):
            with self.subTest(count=len(bad)),self.assertRaises(ValueError):
                migration.migrate(bad)

    def test_canonical_carry_manifest_tamper_and_rehashed_scope_errors_rejected(self):
        original=(migration.HERE.parent/'canonical-carry/source-migration.json').read_bytes()
        delta=json.loads(original)
        changed=[]
        for name in delta['changed_sources']:
            bad=json.loads(original);bad['changed_sources'][name]['new']='1'*64
            changed.append(json.dumps(bad).encode())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'canonical-carry').mkdir()
            path=root/'canonical-carry/source-migration.json'
            for raw in (original+b' ',b'{}',*changed):
                path.write_bytes(raw)
                with patch.object(migration,'HERE',root/'patricia'),self.assertRaises(ValueError):
                    migration.canonical_carry_delta()
            missing=json.loads(original);missing['changed_sources'].pop('Bootstrap.Separate')
            extra=json.loads(original);extra['changed_sources']['Bootstrap.Graph']=delta['changed_sources']['Bootstrap.Separate']
            host=json.loads(original);host['host_sources']={'Unexpected':'1'*64}
            for bad in (missing,extra,host):
                raw=json.dumps(bad).encode();path.write_bytes(raw)
                with patch.object(migration,'HERE',root/'patricia'),patch.object(migration,'CANONICAL_CARRY_MANIFEST_SHA',hashlib.sha256(raw).hexdigest()),self.assertRaises(ValueError):
                    migration.canonical_carry_delta()

    def test_batch_layer_preserves_parent_and_exact_current_owners(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.batch_delta()
        result=migration.migrate(base)
        self.assertEqual(delta['parent_manifest_sha256'],migration.SPARSE_MANIFEST_SHA)
        paths={'Bootstrap.LLVM':'libraries/mlf-llvm/Bootstrap/LLVM.hs',
               'Bootstrap.LLVM.Library':'libraries/mlf-llvm/Bootstrap/LLVM/Library.hs',
               'Bootstrap.LLVM.Optimize':'libraries/mlf-llvm/Bootstrap/LLVM/Optimize.hs'}
        self.assertEqual(set(delta['changed_sources']),set(paths))
        for name,row in delta['changed_sources'].items():
            self.assertEqual(result[name],row['new'])
            self.assertEqual(hashlib.sha256((ROOT/paths[name]).read_bytes()).hexdigest(),row['new'])
        bad=json.loads(json.dumps(delta))
        bad['changed_sources']['Bootstrap.LLVM.Optimize']['old']='0'*64
        with patch.object(migration,'batch_delta',return_value=bad),self.assertRaises(ValueError):
            migration.migrate(base)
        original=(migration.HERE.parent/'batch-replacement/source-migration.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'batch-replacement').mkdir()
            for value in [original+b' ',b'{}']:
                (root/'batch-replacement/source-migration.json').write_bytes(value)
                with patch.object(migration,'HERE',root/'patricia'),self.assertRaises(ValueError):
                    migration.batch_delta()

    def test_sparse_projection_rejects_owner_or_edit_corruption(self):
        source=(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs').read_bytes()
        source=graph.without_delayed_indexes(source)
        previous=sparse.restore_previous_owner(source)
        self.assertEqual(graph.without_sparse_contracts(source),previous)
        self.assertEqual(hashlib.sha256(previous).hexdigest(),
            migration.contract_delta()['changed_sources']['Bootstrap.CrateSession']['new'])
        self.assertEqual(hashlib.sha256(datatype.restore_previous_owner(
            contract.restore_previous_owner(previous))).hexdigest(),
            migration.design_delta()['changed_sources']['Bootstrap.CrateSession']['new'])
        with self.assertRaises(ValueError):sparse.restore_previous_owner(source+b'\n')
        for index,edit in enumerate(sparse.manifest()['edits']):
            for value in [source.replace(edit['new'].encode(),b'',1),source+edit['new'].encode()]:
                with self.assertRaises(ValueError):sparse.restore_previous_owner(value)
            bad=json.loads(json.dumps(sparse.manifest()))
            bad['edits'][index]['old']+='\n'
            with patch.object(sparse,'manifest',return_value=bad),self.assertRaises(ValueError):
                sparse.restore_previous_owner(source)
        original=(sparse.HERE/'session-delta.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for value in [original+b' ',b'{}']:
                (root/'session-delta.json').write_bytes(value)
                with patch.object(sparse,'HERE',root),self.assertRaises(ValueError):sparse.manifest()

    def test_datatype_session_manifest_is_fixed(self):
        original=(datatype.HERE/'session-delta.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for bad in [original+b' ',b'{}']:
                (root/'session-delta.json').write_bytes(bad)
                with patch.object(datatype,'HERE',root),self.assertRaises(ValueError):datatype.manifest()

    def test_c3_registry_matches_all_live_shared_owners(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        result=migration.migrate(base)
        current=current_resource_registry(base)
        found={}
        inventory=json.loads((ROOT/'shared-sources.json').read_bytes())
        for row in inventory['modules']:
            name=row['module']
            self.assertNotIn(name,found)
            found[name]=hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()
        self.assertEqual(found,current)
        delta=migration.c3_delta()
        parent=before_c3_registry(base)
        self.assertEqual(delta['parent_manifest_sha256'],migration.CANONICAL_CARRY_MANIFEST_SHA)
        self.assertEqual({n for n,v in migration.through_full_compiler(base).items() if v!=parent[n]}, {'Bootstrap.CrateSession'})
        owner=delta['changed_sources']['Bootstrap.CrateSession']
        self.assertEqual(owner['old'],c3.OLD_SHA)
        self.assertEqual(owner['new'],c3.NEW_SHA)

    def test_resource_bridge_rejects_wrong_historical_endpoints(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        historical=migration.migrate(base)
        self.assertEqual(len(historical),128)
        missing=dict(historical);missing.pop('Bootstrap.Graph')
        wrong={**historical,'Bootstrap.Graph':'0'*64}
        extra={**historical,'Unexpected':'1'*64}
        current=current_resource_registry(base)
        self.assertEqual(len(current),132)
        for label,bad in [('missing',missing),('wrong',wrong),('extra',extra),
                          ('unmigrated',base),('pre-prelude',migration.through_full_compiler(base)),('already-current',current)]:
            with self.subTest(case=label),self.assertRaisesRegex(ValueError,'exact128-module current-target input'):
                resource.authenticate_current_source(ROOT,bad)

    def test_resource_bridge_rejects_incomplete_or_reordered_inventory(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        current=current_resource_registry(base)
        rows=json.loads((ROOT/'shared-sources.json').read_bytes())['modules']
        wrong_path=[dict(row) for row in rows];wrong_path[0]['path']='../escaping.hs'
        wrong_role=[dict(row) for row in rows];wrong_role[0]['role']='direct-test'
        for label,bad in [('missing',rows[:-1]),('extra',rows+[rows[0]]),
                          ('duplicate',[rows[0],rows[0],*rows[2:]]),
                          ('reordered',[rows[1],rows[0],*rows[2:]]),
                          ('wrong-path',wrong_path),('wrong-role',wrong_role)]:
            with self.subTest(case=label),self.assertRaisesRegex(ValueError,'exact132 ordered shared-source'):
                resource.authenticate_inventory(bad,current)

    def test_resource_bridge_rejects_changed_added_and_unchanged_hashes(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        current=current_resource_registry(base)
        rows=json.loads((ROOT/'shared-sources.json').read_bytes())['modules']
        for name in current:
            bad={**current,name:'0'*64}
            with self.subTest(module=name),self.assertRaisesRegex(ValueError,'exact132 shared source byte identities'):
                resource.authenticate_inventory(rows,bad)
        missing=dict(current);missing.pop('Bootstrap.Graph')
        extra={**current,'Unexpected':'1'*64}
        for label,bad in [('missing',missing),('extra',extra),('historical',migration.migrate(base))]:
            with self.subTest(case=label),self.assertRaisesRegex(ValueError,'exact132 shared source byte identities'):
                resource.authenticate_inventory(rows,bad)

    def test_c3_registry_rejects_wrong_parent_and_manifest(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.c3_delta()
        for section in ['changed_sources']:
            for name in delta[section]:
                bad=json.loads(json.dumps(delta))
                bad[section][name]['old']='0'*64
                with patch.object(migration,'c3_delta',return_value=bad),self.assertRaises(ValueError):
                    migration.migrate(base)
        original=(migration.HERE.parent/'c3-delayed-index/source-migration.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'c3-delayed-index').mkdir()
            for value in [original+b' ',b'{}']:
                (root/'c3-delayed-index/source-migration.json').write_bytes(value)
                with patch.object(migration,'HERE',root/'patricia'),self.assertRaises(ValueError):
                    migration.c3_delta()
            extra=json.loads(original);extra['changed_sources']['Bootstrap.Graph']=delta['changed_sources']['Bootstrap.CrateSession']
            host=json.loads(original);host['host_sources']={'Unexpected':'1'*64}
            zero=json.loads(original);zero['changed_sources']['Bootstrap.CrateSession']['new']='0'*64
            for bad in [extra,host,zero]:
                raw=json.dumps(bad).encode()
                (root/'c3-delayed-index/source-migration.json').write_bytes(raw)
                with patch.object(migration,'HERE',root/'patricia'),patch.object(migration,'C3_MANIFEST_SHA',hashlib.sha256(raw).hexdigest()),self.assertRaises(ValueError):
                    migration.c3_delta()

    def test_c3_projection_requires_complete_owner_and_exact_inverse(self):
        source=(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs').read_bytes()
        source=graph.without_survivor_merge(source)
        previous=c3.restore_previous_owner(source)
        self.assertEqual(hashlib.sha256(previous).hexdigest(),
            '18abedc7f96452392ed3401f1ae607233ec13e2a5ba24bd1c0cba344820c382f')
        self.assertEqual(c3.current_or_parent(source),previous)
        self.assertEqual(c3.current_or_parent(previous),previous)
        self.assertEqual(graph.without_delayed_indexes(source),previous)
        with self.assertRaises(ValueError):c3.restore_previous_owner(previous)
        with self.assertRaises(ValueError):c3.current_or_parent(source+b'\n')
        for index,edit in enumerate(c3.manifest()['edits']):
            for value in [source.replace(edit['new'].encode(),b'',1),source+edit['new'].encode()]:
                with self.assertRaises(ValueError):c3.current_or_parent(value)
            bad=json.loads(json.dumps(c3.manifest()))
            bad['edits'][index]['old']+='\n'
            with patch.object(c3,'manifest',return_value=bad),self.assertRaises(ValueError):
                c3.restore_previous_owner(source)

    def test_c3_projection_manifest_is_fixed(self):
        original=(c3.HERE/'session-delta.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for value in [original+b' ',b'{}']:
                (root/'session-delta.json').write_bytes(value)
                with patch.object(c3,'HERE',root),self.assertRaises(ValueError):c3.manifest()

    def test_survivors_layer_preserves_exact_c3_parent_and_live_owner(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.survivors_delta();result=before_full_registry(base)
        previous=before_survivors_registry(base)
        self.assertEqual(delta['parent_manifest_sha256'],migration.C3_MANIFEST_SHA)
        self.assertEqual({n for n in result if result[n]!=previous[n]}, {'Bootstrap.CrateSession'})
        self.assertEqual(len(result),128)
        row=delta['changed_sources']['Bootstrap.CrateSession']
        self.assertEqual(row['old'],c3.NEW_SHA)
        self.assertEqual(row['old'],survivors.OLD_SHA)
        self.assertEqual(row['new'],survivors.NEW_SHA)
        self.assertEqual(row['new'],result['Bootstrap.CrateSession'])
        self.assertEqual(row['old'],previous['Bootstrap.CrateSession'])

    def test_survivors_inverse_recovers_complete_previous_owner(self):
        source=(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs').read_bytes()
        source=graph.without_projection_patch(source)
        previous=survivors.restore_previous_owner(source)
        self.assertEqual(hashlib.sha256(previous).hexdigest(),
            '157b4d8d07986b1074cc612b89e2482783b3c80164db5f6dc74b1ece14fa7094')
        self.assertEqual(graph.without_survivor_merge(source),previous)
        self.assertEqual(survivors.current_or_parent(previous),previous)
        earlier=c3.restore_previous_owner(previous)
        self.assertEqual(survivors.current_or_parent(earlier),earlier)
        self.assertEqual(graph.without_delayed_indexes(source),earlier)
        for bad in [source+b'\n',source[:-1],previous]:
            with self.assertRaises(ValueError):survivors.restore_previous_owner(bad)
        for edit in survivors.manifest()['edits']:
            for bad in [source.replace(edit['new'].encode(),b'',1),source+edit['new'].encode()]:
                with self.assertRaises(ValueError):survivors.current_or_parent(bad)
        bad=json.loads(json.dumps(survivors.manifest()));bad['edits'][0]['old']+='\n'
        with patch.object(survivors,'manifest',return_value=bad),self.assertRaises(ValueError):
            survivors.restore_previous_owner(source)

    def test_survivors_source_inverse_manifest_is_fixed(self):
        original=(survivors.HERE/'session-delta.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for bad in [original+b' ',b'{}']:
                (root/'session-delta.json').write_bytes(bad)
                with patch.object(survivors,'HERE',root),self.assertRaises(ValueError):survivors.manifest()

    def test_survivors_registry_rejects_wrong_predecessor_and_scope(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.survivors_delta();bad=json.loads(json.dumps(delta))
        bad['changed_sources']['Bootstrap.CrateSession']['old']='0'*64
        with patch.object(migration,'survivors_delta',return_value=bad),self.assertRaises(ValueError):
            migration.migrate(base)
        original=(migration.HERE.parent/'c3-survivors/source-migration.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'c3-survivors').mkdir();path=root/'c3-survivors/source-migration.json'
            for raw in [original+b' ',b'{}']:
                path.write_bytes(raw)
                with patch.object(migration,'HERE',root/'patricia'),self.assertRaises(ValueError):migration.survivors_delta()
            extra=json.loads(original);extra['changed_sources']['Bootstrap.Graph']=delta['changed_sources']['Bootstrap.CrateSession']
            host=json.loads(original);host['host_sources']={'Unexpected':'1'*64}
            zero=json.loads(original);zero['changed_sources']['Bootstrap.CrateSession']['new']='0'*64
            for bad in [extra,host,zero]:
                raw=json.dumps(bad).encode();path.write_bytes(raw)
                with patch.object(migration,'HERE',root/'patricia'),patch.object(migration,'SURVIVORS_MANIFEST_SHA',hashlib.sha256(raw).hexdigest()),self.assertRaises(ValueError):
                    migration.survivors_delta()

    def test_projection_layer_has_exact_parent_and_one_current_owner(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.full_delta();result=migration.through_full_compiler(base);previous=before_full_registry(base)
        self.assertEqual(delta['parent_manifest_sha256'],migration.SURVIVORS_MANIFEST_SHA)
        self.assertEqual(len(result),128)
        self.assertEqual({n for n in result if result[n]!=previous[n]}, {'Bootstrap.CrateSession'})
        row=delta['changed_sources']['Bootstrap.CrateSession']
        self.assertEqual(row['old'],survivors.NEW_SHA)
        self.assertEqual(row['old'],full.OLD_SHA)
        self.assertEqual(row['new'],full.NEW_SHA)
        self.assertEqual(previous['Bootstrap.CrateSession'],row['old'])
        self.assertEqual(result['Bootstrap.CrateSession'],row['new'])

    def test_crate_prelude_transition_rejects_partial_sources(self):
        prelude = migration.crate_prelude()
        base = json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        parent = migration.through_full_compiler(base)
        current = prelude.advance_registry(parent)
        changes = prelude.manifest()['changed_sources']
        self.assertEqual({name for name in current if parent[name] != current[name]}, set(changes))
        mixed = dict(parent)
        mixed['MLF.BuiltinPreludeData'] = current['MLF.BuiltinPreludeData']
        for invalid in (mixed, current):
            with self.assertRaises(ValueError):
                prelude.advance_registry(invalid)
        actual = (ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs').read_bytes()
        self.assertEqual(hashlib.sha256(prelude.restore_session(actual)).hexdigest(), parent['Bootstrap.CrateSession'])
        with self.assertRaises(ValueError):
            prelude.restore_session(actual + b' ')

    def test_projection_inverse_recovers_complete_accepted_owner(self):
        source=(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs').read_bytes()
        source=migration.crate_prelude().restore_session(source)
        previous=full.restore_previous_owner(source)
        self.assertEqual(hashlib.sha256(previous).hexdigest(),
            '51aeddfb084faf84019db88c634d972f48eeecd597d8070c60f59c7402454df9')
        self.assertEqual(graph.without_projection_patch(source),previous)
        self.assertEqual(full.current_or_parent(previous),previous)
        self.assertEqual(graph.without_survivor_merge(source),survivors.restore_previous_owner(previous))
        for bad in [source+b'\n',source[:-1],previous]:
            with self.assertRaises(ValueError):full.restore_previous_owner(bad)
        for e in full.manifest()['edits']:
            for bad in [source.replace(e['new'].encode(),b'',1),source+e['new'].encode()]:
                with self.assertRaises(ValueError):full.current_or_parent(bad)
        bad=json.loads(json.dumps(full.manifest()));bad['edits'][0]['old']+='\n'
        with patch.object(full,'manifest',return_value=bad),self.assertRaises(ValueError):full.restore_previous_owner(source)

    def test_projection_inverse_manifest_is_fixed(self):
        original=(full.HERE/'session-delta.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for bad in [original+b' ',b'{}']:
                (root/'session-delta.json').write_bytes(bad)
                with patch.object(full,'HERE',root),self.assertRaises(ValueError):full.manifest()

    def test_projection_registry_rejects_bad_predecessor_scope_and_hash(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.full_delta();bad=json.loads(json.dumps(delta));bad['changed_sources']['Bootstrap.CrateSession']['old']='0'*64
        with patch.object(migration,'full_delta',return_value=bad),self.assertRaises(ValueError):migration.migrate(base)
        original=(migration.HERE.parent/'full-compiler/source-migration.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'full-compiler').mkdir();path=root/'full-compiler/source-migration.json'
            for raw in [original+b' ',b'{}']:
                path.write_bytes(raw)
                with patch.object(migration,'HERE',root/'patricia'),self.assertRaises(ValueError):migration.full_delta()
            extra=json.loads(original);extra['changed_sources']['Bootstrap.Graph']=delta['changed_sources']['Bootstrap.CrateSession']
            host=json.loads(original);host['host_sources']={'Unexpected':'1'*64}
            zero=json.loads(original);zero['changed_sources']['Bootstrap.CrateSession']['new']='0'*64
            for bad in [extra,host,zero]:
                raw=json.dumps(bad).encode();path.write_bytes(raw)
                with patch.object(migration,'HERE',root/'patricia'),patch.object(migration,'FULL_MANIFEST_SHA',hashlib.sha256(raw).hexdigest()),self.assertRaises(ValueError):migration.full_delta()


class CoreProofTests(unittest.TestCase):
    def worker(self, name='unmatchedMultiplier', operations='timesInt64# plusInt64# remInt64#'):
        return '-- RHS size: {terms: 3}\nProbe.$w'+name+' = '+operations+'\n'

    def test_direct_worker_and_plain_actual_recursion(self):
        fingerprint.machine_worker(self.worker(), 'unmatchedMultiplier')
        fingerprint.machine_worker(self.worker('fingerprintStateChars').replace('$w', ''),
                                   'fingerprintStateChars', worker=False)

    def test_operation_in_another_binding_does_not_satisfy_proof(self):
        text = self.worker(operations='timesInt64# remInt64#')+self.worker('unrelated', 'plusInt64#')
        with self.assertRaisesRegex(ValueError, 'direct Int64 arithmetic missing'):
            fingerprint.machine_worker(text, 'unmatchedMultiplier')

    def test_duplicate_and_retired_workers_are_rejected(self):
        for text in [self.worker()*2, self.worker(operations='integerMul timesInt64# plusInt64# remInt64#'),
                     self.worker(operations='fingerprintIntStep timesInt64# plusInt64# remInt64#')]:
            with self.assertRaises(ValueError):
                fingerprint.machine_worker(text, 'unmatchedMultiplier')

    def test_retired_rule_cannot_reappear(self):
        counts = {'mlf/fingerprintIntStep/65599': 0, 'mlf/fingerprintIntStep/131': 0}
        for optimization in ['0', '2']:
            fingerprint.verify_no_retired_rules(counts, optimization)
        counts['mlf/fingerprintIntStep/131'] = 1
        with self.assertRaises(ValueError):
            fingerprint.verify_no_retired_rules(counts, '2')


if __name__ == '__main__':
    unittest.main()
