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


# Historical fixtures are a single, strictly authenticated immutable snapshot.
# This is test preparation, not a production admission cache. The guarded suite
# checks every physical input before/after; actual binary boundary tests below
# still construct fresh contracts and call the real migrate/host entrypoints.
_HISTORICAL_BINARY = migration.binary_contract()
_HISTORICAL_BINARY.live_registry(ROOT)
_HISTORICAL_BINARY.live_host_inventory(ROOT)


def prebinary_registry(base):
    # Re-run the complete historical chain for every bad-base/monkeypatch test.
    parent = migration.migrate_to_read_window(base)
    current = _HISTORICAL_BINARY.advance_registry(parent)
    # New-module deletion still requires each current added file's full bytes.
    return _HISTORICAL_BINARY.registry_to_parent(
        current, _HISTORICAL_BINARY.added_source_bytes(ROOT))


def prebinary_hosts(base):
    parent = migration.host_sources_to_read_window(base)
    current = _HISTORICAL_BINARY.advance_legacy_host_subset(parent)
    return _HISTORICAL_BINARY.legacy_host_subset_to_parent(current)


def prebinary_read_bytes(path):
    raw = path.read_bytes()
    relative = str(path.resolve().relative_to(ROOT.resolve()))
    # The authenticated implementation registry also owns shared modules under
    # tests/ and testing/. Directory spelling must not bypass their exact live
    # SHA or the complete historical source/API transition (CompilerTests is a
    # production driver even though its pathname starts with tests/).
    owned = relative in _HISTORICAL_BINARY.value['current_files']
    production = relative.split('/', 1)[0] in {'bootstrap', 'package', 'libraries', 'host', 'runtime'}
    if owned or production:
        restored = _HISTORICAL_BINARY.restore_path(raw, relative)
        if restored is None:
            raise ValueError('new binary-only file has no historical fixture bytes')
        return restored
    # Historical oracle/metadata bytes retain their original SHA gates below.
    # This passthrough is NOT any live production-source admission path.
    return raw


def prebinary_read_text(path):
    return prebinary_read_bytes(path).decode('utf-8')
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

source_context_spec=importlib.util.spec_from_file_location('source_query_context_contract',
    ROOT/'tools/performance/source-query-context/source_contract.py')
source_context=importlib.util.module_from_spec(source_context_spec)
source_context_spec.loader.exec_module(source_context)

scratch_spec=importlib.util.spec_from_file_location('query_key_scratch_contract',
    ROOT/'tools/performance/query-key-scratch/source_contract.py')
scratch=importlib.util.module_from_spec(scratch_spec)
scratch_spec.loader.exec_module(scratch)

diamond_spec=importlib.util.spec_from_file_location('source_diamond_contract',
    ROOT/'tools/performance/source-context-projection-merge/source_contract.py')
diamond=importlib.util.module_from_spec(diamond_spec);diamond_spec.loader.exec_module(diamond)
full_spec=importlib.util.spec_from_file_location('projection_patch_contract',
    ROOT/'tools/performance/full-compiler/source_contract.py')
full=importlib.util.module_from_spec(full_spec);full_spec.loader.exec_module(full)

read_window=migration.read_window_contract()
key_parts=migration.key_parts_contract()
publication=migration.publication_contract()
memo=migration.memo_contract()
# Historical golden assertions use strict full-byte inverses. The new layer's
# tests separately require exact live owners, lock and all 128 registry entries.
def before_read_window_registry(base):
    return read_window.registry_to_parent(prebinary_registry(base))
def before_read_window_owner(path):
    return read_window.project_owner(prebinary_read_bytes(path),'Bootstrap.'+path.stem)
def before_read_window_lock():
    return read_window.restore_previous_lock(prebinary_read_bytes(ROOT/'mlf.lock'))
def before_key_parts_registry(base):
    return key_parts.registry_to_parent(before_read_window_registry(base))
def before_key_parts_owner(path):
    return key_parts.project_owner(before_read_window_owner(path),'Bootstrap.'+path.stem)
def before_key_parts_lock():
    return key_parts.restore_previous_lock(before_read_window_lock())
def before_publication_registry(base):
    return publication.registry_to_parent(before_key_parts_registry(base))
def before_publication_owner(path):
    return publication.project_owner(before_key_parts_owner(path),'Bootstrap.'+path.stem)
def before_memo_registry(base):
    return memo.registry_to_parent(before_publication_registry(base))
def prior_owner(path):
    module='Bootstrap.'+path.stem
    return memo.restore_previous_owner(before_publication_owner(path),module)
def prior_lock():
    lock=json.loads(publication.restore_previous_lock(before_key_parts_lock()))
    crates=[c for c in lock['packages'] if c['name']=='mlf-crates']
    if len(crates)!=1:raise ValueError('one exact crate')
    for module,o in memo.OWNERS.items():
        key='Bootstrap/'+module.split('.')[-1]+'.hs'
        if crates[0]['sources'][key]!=o['new']:raise ValueError('current read-reuse lock owner')
        crates[0]['sources'][key]=o['old']
    return lock

def before_diamond_registry(base):
    return diamond.registry_to_parent(before_memo_registry(base),'left')

def full_only_registry(base):
    return diamond.registry_to_parent(before_memo_registry(base),'right')

def before_full_registry(base):
    return migration.apply_changes(full_only_registry(base),
        {name: {'old':row['new'],'new':row['old'],'reviewed_change':'inverse full test'}
         for name,row in migration.full_delta()['changed_sources'].items()})

def before_scratch_registry(base):
    return migration.apply_changes(before_diamond_registry(base),
        {name: {'old': row['new'], 'new': row['old'], 'reviewed_change': 'inverse test'}
         for name,row in migration.scratch_delta()['changed_sources'].items()})

def before_source_context_registry(base):
    return migration.apply_changes(before_scratch_registry(base),
        {name: {'old': row['new'], 'new': row['old'], 'reviewed_change': 'inverse test'}
         for name,row in migration.source_context_delta()['changed_sources'].items()})

def before_survivors_registry(base):
    return migration.apply_changes(before_source_context_registry(base),
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
                prebinary_read_bytes(ROOT/'tools/performance/crate-optimizations/p2/NativeCompatibilityControls.hs'))

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
            solver.write_bytes(prebinary_read_bytes(ROOT/solver.relative_to(root)))
            path = root/'libraries/mlf-crates/Bootstrap/CrateSession.hs'
            path.parent.mkdir(parents=True)
            for index,source in enumerate(['', (graph.LIVE_SESSION_HEADER+'\n')*2,
                                           'module Bootstrap.CrateSession (compileSpecFile) where {\n']):
                path.write_text(source)
                with self.assertRaisesRegex(ValueError, 'unique private header'):
                    graph.prepare(root,root/('out'+str(index)))

    def test_host_migration_accepts_only_explicit_historical_parents(self):
        manifest = json.loads((migration.HERE/'source-migration.json').read_text())
        key = 'host/ghc/MLF/Host/Base.hs'
        row = manifest['host_sources'][key]
        for field in ['old', 'retained_F1_parent']:
            self.assertEqual(prebinary_hosts({key: row[field]}), {key: '50780c7183d62aa7568c0a799fdf5829b6ea60cbbc67cca7fd1a3f08bc4ba9c5'})
        with self.assertRaisesRegex(ValueError, 'exact frozen host parent'):
            prebinary_hosts({key: '0'*64})

    def test_rank_view_adapter_is_exactly_reversible(self):
        source = prior_owner(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs')
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
        self.assertEqual(len(prebinary_registry(base)), 128)
        design = (migration.HERE/'index-design-migration.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'source-migration.json').write_bytes(old)
            for bad in [design+b' ', b'{}']:
                (root/'index-design-migration.json').write_bytes(bad)
                with patch.object(migration, 'HERE', root), self.assertRaises(ValueError):
                    prebinary_registry(base)

    def test_rehashed_design_still_requires_exact_previous_sources(self):
        base = json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        design = migration.design_delta()
        for section in ['changed_sources', 'host_sources']:
            bad = json.loads(json.dumps(design))
            name = next(iter(bad[section]))
            bad[section][name]['old'] = '0'*64
            with patch.object(migration, 'design_delta', return_value=bad), self.assertRaises(ValueError):
                if section == 'changed_sources':
                    prebinary_registry(base)
                else:
                    prebinary_hosts({})

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
            prebinary_registry(base)

    def test_datatype_session_projection_preserves_previous_complete_owner(self):
        source=diamond.to_left(prior_owner(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs'))
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
            prebinary_registry(base)
        source=diamond.to_left(prior_owner(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs'))
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
        paths={'Bootstrap.Classes':'libraries/mlf-inference/Bootstrap/Classes.hs',
               'Bootstrap.CrateQuery':'libraries/mlf-crates/Bootstrap/CrateQuery.hs',
               'Bootstrap.CrateSession':'libraries/mlf-crates/Bootstrap/CrateSession.hs',
               'Bootstrap.SourceInference':'libraries/mlf-crates/Bootstrap/SourceInference.hs',
               'MLF.BuiltinPreludeData':'bootstrap/MLF/BuiltinPreludeData.hs'}
        self.assertEqual(set(delta['changed_sources']),set(paths))
        for name,row in delta['changed_sources'].items():
            self.assertEqual(previous[name],row['old'])
            self.assertEqual(before_permission_registry(base)[name],row['new'])
            self.assertEqual(hashlib.sha256(prebinary_read_bytes(ROOT/paths[name])).hexdigest(),prebinary_registry(base)[name])
        bad=json.loads(json.dumps(delta))
        bad['changed_sources']['Bootstrap.SourceInference']['old']='0'*64
        with patch.object(migration,'sparse_delta',return_value=bad),self.assertRaises(ValueError):
            prebinary_registry(base)
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
        current=prebinary_registry(base)
        self.assertEqual(delta['parent_manifest_sha256'],migration.BATCH_MANIFEST_SHA)
        paths={'Bootstrap.Graph':'libraries/mlf-inference/Bootstrap/Graph.hs',
               'MLF.BuiltinPreludeData':'bootstrap/MLF/BuiltinPreludeData.hs'}
        self.assertEqual(set(delta['changed_sources']),set(paths))
        for name,row in delta['changed_sources'].items():
            self.assertEqual(before_permission_registry(base)[name],row['old'])
            self.assertEqual(result[name],row['new'])
            self.assertEqual(hashlib.sha256(prebinary_read_bytes(ROOT/paths[name])).hexdigest(),current[name])
        bad=json.loads(json.dumps(delta))
        bad['changed_sources']['Bootstrap.Graph']['old']='0'*64
        with patch.object(migration,'permission_delta',return_value=bad),self.assertRaises(ValueError):
            prebinary_registry(base)
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
            self.assertEqual(hashlib.sha256(prebinary_read_bytes(ROOT/paths[name])).hexdigest(),row['new'])

    def test_canonical_carry_wrong_predecessors_and_registry_pollution_rejected(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.canonical_carry_delta()
        for name in delta['changed_sources']:
            bad=json.loads(json.dumps(delta));bad['changed_sources'][name]['old']='0'*64
            with self.subTest(name=name),patch.object(migration,'canonical_carry_delta',return_value=bad),self.assertRaises(ValueError):
                prebinary_registry(base)
        missing=dict(base);missing.pop('Bootstrap.Graph')
        renamed={**missing,'Unexpected':base['Bootstrap.Graph']}
        polluted={**base,'Bootstrap.Graph':'0'*64}
        for bad in (missing,renamed,polluted,prebinary_registry(base)):
            with self.subTest(count=len(bad)),self.assertRaises(ValueError):
                prebinary_registry(bad)

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
        result=prebinary_registry(base)
        self.assertEqual(delta['parent_manifest_sha256'],migration.SPARSE_MANIFEST_SHA)
        paths={'Bootstrap.LLVM':'libraries/mlf-llvm/Bootstrap/LLVM.hs',
               'Bootstrap.LLVM.Library':'libraries/mlf-llvm/Bootstrap/LLVM/Library.hs',
               'Bootstrap.LLVM.Optimize':'libraries/mlf-llvm/Bootstrap/LLVM/Optimize.hs'}
        self.assertEqual(set(delta['changed_sources']),set(paths))
        for name,row in delta['changed_sources'].items():
            self.assertEqual(result[name],row['new'])
            self.assertEqual(hashlib.sha256(prebinary_read_bytes(ROOT/paths[name])).hexdigest(),row['new'])
        bad=json.loads(json.dumps(delta))
        bad['changed_sources']['Bootstrap.LLVM.Optimize']['old']='0'*64
        with patch.object(migration,'batch_delta',return_value=bad),self.assertRaises(ValueError):
            prebinary_registry(base)
        original=(migration.HERE.parent/'batch-replacement/source-migration.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'batch-replacement').mkdir()
            for value in [original+b' ',b'{}']:
                (root/'batch-replacement/source-migration.json').write_bytes(value)
                with patch.object(migration,'HERE',root/'patricia'),self.assertRaises(ValueError):
                    migration.batch_delta()

    def test_sparse_projection_rejects_owner_or_edit_corruption(self):
        source=diamond.to_left(prior_owner(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs'))
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
        result=prebinary_registry(base)
        found={}
        inventory=json.loads(prebinary_read_bytes(ROOT/'shared-sources.json'))
        for row in inventory['modules']:
            name=row['module']
            self.assertNotIn(name,found)
            found[name]=hashlib.sha256(prebinary_read_bytes(ROOT/row['path'])).hexdigest()
        self.assertEqual(found,result)
        delta=migration.c3_delta()
        parent=before_c3_registry(base)
        self.assertEqual(delta['parent_manifest_sha256'],migration.CANONICAL_CARRY_MANIFEST_SHA)
        historical=before_source_context_registry(base)
        self.assertEqual({n for n in historical if historical[n]!=parent[n]}, {'Bootstrap.CrateSession'})
        owner=delta['changed_sources']['Bootstrap.CrateSession']
        self.assertEqual(owner['old'],c3.OLD_SHA)
        self.assertEqual(owner['new'],c3.NEW_SHA)

    def test_c3_registry_rejects_wrong_parent_and_manifest(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.c3_delta()
        for section in ['changed_sources']:
            for name in delta[section]:
                bad=json.loads(json.dumps(delta))
                bad[section][name]['old']='0'*64
                with patch.object(migration,'c3_delta',return_value=bad),self.assertRaises(ValueError):
                    prebinary_registry(base)
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
        source=diamond.to_left(prior_owner(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs'))
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
        delta=migration.survivors_delta();result=before_source_context_registry(base)
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
        source=diamond.to_left(prior_owner(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs'))
        source=source_context.restore_previous_owner(scratch.restore_previous_owner(source))
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
            prebinary_registry(base)
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



    def test_source_context_layer_has_exact_two_owners_and_126_unchanged(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.source_context_delta()
        previous=before_source_context_registry(base)
        current=before_scratch_registry(base)
        self.assertEqual(delta['parent_manifest_sha256'],migration.SURVIVORS_MANIFEST_SHA)
        self.assertEqual(delta['module_count'],128)
        self.assertEqual(delta['unchanged_sources'],126)
        self.assertEqual(set(current),set(previous))
        self.assertEqual(len(current),128)
        owners=set(source_context.OWNERS)
        self.assertEqual(set(delta['changed_sources']),owners)
        self.assertEqual({n for n in current if current[n]!=previous[n]},owners)
        self.assertEqual({n:current[n] for n in current if n not in owners},
                         {n:previous[n] for n in previous if n not in owners})
        lock=prior_lock()
        crates=[p for p in lock['packages'] if p['name']=='mlf-crates']
        self.assertEqual(len(crates),1)
        self.assertEqual(crates[0]['sources']['Bootstrap/CrateSession.hs'],diamond.EXPECTED['session_edges']['left']['new_sha256'])
        self.assertEqual(crates[0]['sources']['Bootstrap/CrateQuery.hs'],diamond.EXPECTED['query']['merged_sha256'])
        crates[0]['sources']['Bootstrap/CrateSession.hs']=diamond.EXPECTED['session_edges']['left']['old_sha256']
        for module,transition in migration.scratch_delta()['changed_sources'].items():
            rel=source_context.OWNERS[module]['path'].split('libraries/mlf-crates/',1)[1]
            self.assertEqual(crates[0]['sources'][rel],transition['new'])
            crates[0]['sources'][rel]=transition['old']
        for module,owner in source_context.OWNERS.items():
            row=delta['changed_sources'][module]
            self.assertEqual(row['old'],previous[module])
            self.assertEqual(row['new'],current[module])
            self.assertEqual(row['old'],owner['old'])
            self.assertEqual(row['new'],owner['new'])
            self.assertEqual(hashlib.sha256(scratch.restore_previous_owner(diamond.storage_current_owner(prior_owner(ROOT/owner['path']),module),module)).hexdigest(),row['new'])
            self.assertEqual(crates[0]['sources'][owner['path'].split('libraries/mlf-crates/',1)[1]],row['new'])

    def test_source_context_complete_inverse_and_explicit_parent_replay(self):
        for module,owner in source_context.OWNERS.items():
            source=scratch.restore_previous_owner(diamond.storage_current_owner(prior_owner(ROOT/owner['path']),module),module)
            previous=source_context.restore_previous_owner(source,module)
            self.assertEqual(hashlib.sha256(previous).hexdigest(),owner['old'])
            forward=previous
            for edit in source_context.manifest(module)['edits']:
                self.assertEqual(forward.count(edit['old'].encode()),1)
                forward=forward.replace(edit['old'].encode(),edit['new'].encode())
            self.assertEqual(forward,source)
            self.assertEqual(source_context.current_or_parent(source,module),previous)
            self.assertEqual(source_context.current_or_parent(previous,module),previous)
            with self.assertRaises(ValueError):
                source_context.restore_previous_owner(previous,module)
        session=scratch.restore_previous_owner(diamond.to_left(prior_owner(ROOT/source_context.OWNERS['Bootstrap.CrateSession']['path'])))
        self.assertEqual(graph.without_source_query_context(session),
                         source_context.restore_previous_owner(session))
        prior=source_context.restore_previous_owner(session)
        c3_owner=survivors.restore_previous_owner(prior)
        sparse_owner=c3.restore_previous_owner(c3_owner)
        for old in (prior,c3_owner,sparse_owner):
            self.assertEqual(source_context.current_or_parent(old),old)
        with self.assertRaises(ValueError):
            source_context.manifest('Bootstrap.Graph')

    def test_source_context_partial_unknown_or_reordered_owner_rejected(self):
        for module,owner in source_context.OWNERS.items():
            source=scratch.restore_previous_owner(diamond.storage_current_owner(prior_owner(ROOT/owner['path']),module),module)
            for edit in source_context.manifest(module)['edits']:
                for changed in (source+b' ',source[:-1],
                                source.replace(edit['new'].encode(),edit['old'].encode(),1),
                                source+edit['new'].encode()):
                    with self.subTest(module=module,size=len(changed)),self.assertRaises(ValueError):
                        source_context.restore_previous_owner(changed,module)
                    with self.subTest(module=module,replay=True),self.assertRaises(ValueError):
                        source_context.current_or_parent(changed,module)
        session=scratch.restore_previous_owner(diamond.to_left(prior_owner(ROOT/source_context.OWNERS['Bootstrap.CrateSession']['path'])))
        for adapter in (survivors,c3,sparse,contract,datatype):
            with self.subTest(out_of_order=adapter.__name__),self.assertRaises(ValueError):
                adapter.restore_previous_owner(session)

    def test_source_context_delta_manifests_are_fixed_and_inverse_is_independent(self):
        for module,owner in source_context.OWNERS.items():
            original=(source_context.HERE/owner['file']).read_bytes()
            source=scratch.restore_previous_owner(diamond.storage_current_owner(prior_owner(ROOT/owner['path']),module),module)
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);path=root/owner['file']
                for raw in (original+b' ',b'{}'):
                    path.write_bytes(raw)
                    with patch.object(source_context,'HERE',root),self.assertRaises(ValueError):
                        source_context.manifest(module)
                value=json.loads(original);value['edits'][0]['old']+='\n'
                raw=json.dumps(value).encode();path.write_bytes(raw)
                changed=json.loads(json.dumps(source_context.OWNERS))
                changed[module]['manifest_sha256']=hashlib.sha256(raw).hexdigest()
                with patch.object(source_context,'HERE',root),patch.object(source_context,'OWNERS',changed),self.assertRaises(ValueError):
                    source_context.restore_previous_owner(source,module)

    def test_source_context_registry_rejects_tamper_rehashed_scope_and_hashes(self):
        original=(migration.HERE.parent/'source-query-context/source-migration.json').read_bytes()
        delta=json.loads(original);bad_values=[]
        for field,value in [('parent_ref','unknown'),('baseline_ref','unknown'),
                            ('parent_manifest_sha256','0'*64),('module_count',127),
                            ('unchanged_sources',127),('added_sources',{'Unknown':'1'*64}),
                            ('removed_sources',{'Bootstrap.CrateQuery':'1'*64}),
                            ('host_sources',{'Unknown':'1'*64})]:
            bad=json.loads(original);bad[field]=value;bad_values.append(bad)
        for name in delta['changed_sources']:
            for field,value in [('old','0'*64),('new','1'*64),('reviewed_change','')]:
                bad=json.loads(original);bad['changed_sources'][name][field]=value;bad_values.append(bad)
        missing=json.loads(original);missing['changed_sources'].pop('Bootstrap.CrateQuery');bad_values.append(missing)
        renamed=json.loads(original);renamed['changed_sources']['Unknown']=renamed['changed_sources'].pop('Bootstrap.CrateQuery');bad_values.append(renamed)
        extra=json.loads(original);extra['unexpected']=True;bad_values.append(extra)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'source-query-context').mkdir();path=root/'source-query-context/source-migration.json'
            for raw in (original+b' ',b'{}'):
                path.write_bytes(raw)
                with patch.object(migration,'HERE',root/'patricia'),self.assertRaises(ValueError):
                    migration.source_context_delta()
            for value in bad_values:
                raw=json.dumps(value).encode();path.write_bytes(raw)
                with patch.object(migration,'HERE',root/'patricia'),patch.object(migration,'SOURCE_CONTEXT_MANIFEST_SHA',hashlib.sha256(raw).hexdigest()),self.assertRaises(ValueError):
                    migration.source_context_delta()
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        for name in delta['changed_sources']:
            bad=json.loads(original);bad['changed_sources'][name]['old']='0'*64
            with patch.object(migration,'source_context_delta',return_value=bad),self.assertRaises(ValueError):
                prebinary_registry(base)
        previous=before_source_context_registry(base)
        for name,row in delta['changed_sources'].items():
            partial={**previous,name:row['new']}
            with self.subTest(partly_migrated=name),self.assertRaises(ValueError):
                migration.apply_changes(partial,delta['changed_sources'])
        with self.assertRaises(ValueError):
            migration.apply_changes(before_scratch_registry(base),delta['changed_sources'])
    def test_scratch_layer_has_exact_two_owners_and_126_unchanged(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.scratch_delta()
        previous=before_scratch_registry(base)
        current=before_diamond_registry(base)
        self.assertEqual(delta['parent_manifest_sha256'],migration.SOURCE_CONTEXT_MANIFEST_SHA)
        self.assertEqual(delta['module_count'],128)
        self.assertEqual(delta['unchanged_sources'],126)
        self.assertEqual(set(current),set(previous))
        self.assertEqual(len(current),128)
        owners=set(scratch.OWNERS)
        self.assertEqual(set(delta['changed_sources']),owners)
        self.assertEqual({n for n in current if current[n]!=previous[n]},owners)
        self.assertEqual({n:current[n] for n in current if n not in owners},
                         {n:previous[n] for n in previous if n not in owners})
        lock=prior_lock()
        crates=[p for p in lock['packages'] if p['name']=='mlf-crates']
        self.assertEqual(len(crates),1)
        self.assertEqual(crates[0]['sources']['Bootstrap/CrateSession.hs'],diamond.EXPECTED['session_edges']['left']['new_sha256'])
        self.assertEqual(crates[0]['sources']['Bootstrap/CrateQuery.hs'],diamond.EXPECTED['query']['merged_sha256'])
        crates[0]['sources']['Bootstrap/CrateSession.hs']=diamond.EXPECTED['session_edges']['left']['old_sha256']
        for module,owner in scratch.OWNERS.items():
            row=delta['changed_sources'][module]
            self.assertEqual(row['old'],previous[module])
            self.assertEqual(row['new'],current[module])
            self.assertEqual(row['old'],owner['old'])
            self.assertEqual(row['new'],owner['new'])
            self.assertEqual(hashlib.sha256(diamond.storage_current_owner(prior_owner(ROOT/owner['path']),module)).hexdigest(),row['new'])
            self.assertEqual(crates[0]['sources'][owner['path'].split('libraries/mlf-crates/',1)[1]],row['new'])

    def test_scratch_complete_inverse_and_explicit_parent_replay(self):
        for module,owner in scratch.OWNERS.items():
            source=diamond.storage_current_owner(prior_owner(ROOT/owner['path']),module)
            previous=scratch.restore_previous_owner(source,module)
            self.assertEqual(hashlib.sha256(previous).hexdigest(),owner['old'])
            forward=previous
            for edit in scratch.manifest(module)['edits']:
                self.assertEqual(forward.count(edit['old'].encode()),1)
                forward=forward.replace(edit['old'].encode(),edit['new'].encode())
            self.assertEqual(forward,source)
            self.assertEqual(scratch.current_or_parent(source,module),previous)
            self.assertEqual(scratch.current_or_parent(previous,module),previous)
            with self.assertRaises(ValueError):
                scratch.restore_previous_owner(previous,module)
        session=diamond.to_left(prior_owner(ROOT/scratch.OWNERS['Bootstrap.CrateSession']['path']))
        prior=scratch.restore_previous_owner(session)
        self.assertEqual(graph.without_query_key_scratch(session),prior)
        self.assertEqual(graph.without_source_query_context(session),
                         source_context.restore_previous_owner(prior))
        context_owner=source_context.restore_previous_owner(prior)
        c3_owner=survivors.restore_previous_owner(context_owner)
        sparse_owner=c3.restore_previous_owner(c3_owner)
        for old in (prior,context_owner,c3_owner,sparse_owner):
            self.assertEqual(scratch.current_or_parent(old),old)
        with self.assertRaises(ValueError):
            scratch.manifest('Bootstrap.Graph')

    def test_scratch_partial_unknown_or_reordered_owner_rejected(self):
        for module,owner in scratch.OWNERS.items():
            source=diamond.storage_current_owner(prior_owner(ROOT/owner['path']),module)
            for edit in scratch.manifest(module)['edits']:
                for changed in (source+b' ',source[:-1],
                                source.replace(edit['new'].encode(),edit['old'].encode(),1),
                                source+edit['new'].encode()):
                    with self.subTest(module=module,size=len(changed)),self.assertRaises(ValueError):
                        scratch.restore_previous_owner(changed,module)
                    # The Session has one edit: reversing it fully is the
                    # explicitly admitted previous owner, not a partial owner.
                    if hashlib.sha256(changed).hexdigest() in scratch.REPLAY_PARENTS[module]:
                        self.assertEqual(scratch.current_or_parent(changed,module),changed)
                    else:
                        with self.subTest(module=module,replay=True),self.assertRaises(ValueError):
                            scratch.current_or_parent(changed,module)
        session=diamond.to_left(prior_owner(ROOT/scratch.OWNERS['Bootstrap.CrateSession']['path']))
        for adapter in (source_context,survivors,c3,sparse,contract,datatype):
            with self.subTest(out_of_order=adapter.__name__),self.assertRaises(ValueError):
                adapter.restore_previous_owner(session)

    def test_scratch_delta_manifests_are_fixed_and_inverse_is_independent(self):
        for module,owner in scratch.OWNERS.items():
            original=(scratch.HERE/owner['file']).read_bytes()
            source=diamond.storage_current_owner(prior_owner(ROOT/owner['path']),module)
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);path=root/owner['file']
                for raw in (original+b' ',b'{}'):
                    path.write_bytes(raw)
                    with patch.object(scratch,'HERE',root),self.assertRaises(ValueError):
                        scratch.manifest(module)
                value=json.loads(original);value['edits'][0]['old']+='\n'
                raw=json.dumps(value).encode();path.write_bytes(raw)
                changed=json.loads(json.dumps(scratch.OWNERS))
                changed[module]['manifest_sha256']=hashlib.sha256(raw).hexdigest()
                with patch.object(scratch,'HERE',root),patch.object(scratch,'OWNERS',changed),self.assertRaises(ValueError):
                    scratch.restore_previous_owner(source,module)

    def test_scratch_registry_rejects_tamper_rehashed_scope_and_hashes(self):
        original=(migration.HERE.parent/'query-key-scratch/source-migration.json').read_bytes()
        delta=json.loads(original);bad_values=[]
        for field,value in [('parent_ref','unknown'),('baseline_ref','unknown'),
                            ('parent_manifest_sha256','0'*64),('module_count',127),
                            ('unchanged_sources',127),('added_sources',{'Unknown':'1'*64}),
                            ('removed_sources',{'Bootstrap.CrateQuery':'1'*64}),
                            ('host_sources',{'Unknown':'1'*64})]:
            bad=json.loads(original);bad[field]=value;bad_values.append(bad)
        for name in delta['changed_sources']:
            for field,value in [('old','0'*64),('new','1'*64),('reviewed_change','')]:
                bad=json.loads(original);bad['changed_sources'][name][field]=value;bad_values.append(bad)
        missing=json.loads(original);missing['changed_sources'].pop('Bootstrap.CrateQuery');bad_values.append(missing)
        renamed=json.loads(original);renamed['changed_sources']['Unknown']=renamed['changed_sources'].pop('Bootstrap.CrateQuery');bad_values.append(renamed)
        extra=json.loads(original);extra['unexpected']=True;bad_values.append(extra)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'query-key-scratch').mkdir();path=root/'query-key-scratch/source-migration.json'
            for raw in (original+b' ',b'{}'):
                path.write_bytes(raw)
                with patch.object(migration,'HERE',root/'patricia'),self.assertRaises(ValueError):
                    migration.scratch_delta()
            for value in bad_values:
                raw=json.dumps(value).encode();path.write_bytes(raw)
                with patch.object(migration,'HERE',root/'patricia'),patch.object(migration,'SCRATCH_MANIFEST_SHA',hashlib.sha256(raw).hexdigest()),self.assertRaises(ValueError):
                    migration.scratch_delta()
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        for name in delta['changed_sources']:
            bad=json.loads(original);bad['changed_sources'][name]['old']='0'*64
            with patch.object(migration,'scratch_delta',return_value=bad),self.assertRaises(ValueError):
                prebinary_registry(base)
        previous=before_scratch_registry(base)
        for name,row in delta['changed_sources'].items():
            partial={**previous,name:row['new']}
            with self.subTest(partly_migrated=name),self.assertRaises(ValueError):
                migration.apply_changes(partial,delta['changed_sources'])
        with self.assertRaises(ValueError):
            migration.apply_changes(before_diamond_registry(base),delta['changed_sources'])

    def test_scratch_live_registry_does_not_admit_replayed_owners(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        current=before_diamond_registry(base)
        for module,parents in scratch.REPLAY_PARENTS.items():
            for old in parents:
                stale={**current,module:old}
                with self.subTest(module=module,old=old):
                    self.assertNotEqual(stale,current)
                    self.assertNotEqual(old,scratch.OWNERS[module]['new'])
                    inverse={name: {'old': row['new'], 'new': row['old'],
                                    'reviewed_change': 'inverse live-registry test'}
                             for name,row in migration.scratch_delta()['changed_sources'].items()}
                    with self.assertRaises(ValueError):
                        migration.apply_changes(stale,inverse)

    def test_projection_layer_has_exact_parent_and_one_current_owner(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        delta=migration.full_delta();result=full_only_registry(base);previous=before_full_registry(base)
        self.assertEqual(delta['parent_manifest_sha256'],migration.SURVIVORS_MANIFEST_SHA)
        self.assertEqual(len(result),128)
        self.assertEqual({n for n in result if result[n]!=previous[n]}, {'Bootstrap.CrateSession'})
        row=delta['changed_sources']['Bootstrap.CrateSession']
        self.assertEqual(row['old'],survivors.NEW_SHA)
        self.assertEqual(row['old'],full.OLD_SHA)
        self.assertEqual(row['new'],full.NEW_SHA)
        self.assertEqual(previous['Bootstrap.CrateSession'],row['old'])
        self.assertEqual(result['Bootstrap.CrateSession'],row['new'])

    def test_projection_inverse_recovers_complete_accepted_owner(self):
        source=diamond.to_right(prior_owner(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs'))
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
        with patch.object(migration,'full_delta',return_value=bad),self.assertRaises(ValueError):prebinary_registry(base)
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


    def test_diamond_both_full_source_routes_and_live_registry(self):
        raw=prior_owner(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs')
        common=diamond.verify_diamond(raw)
        self.assertEqual(hashlib.sha256(common).hexdigest(),full.OLD_SHA)
        self.assertEqual(hashlib.sha256(diamond.to_left(raw)).hexdigest(),scratch.NEW_SHA)
        self.assertEqual(hashlib.sha256(diamond.to_right(raw)).hexdigest(),full.NEW_SHA)
        query=prior_owner(ROOT/'libraries/mlf-crates/Bootstrap/CrateQuery.hs')
        self.assertEqual(hashlib.sha256(diamond.query_to_right(query)).hexdigest(),source_context.QUERY_OLD_SHA)
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        merged=before_memo_registry(base);left=before_diamond_registry(base);right=full_only_registry(base)
        self.assertEqual(diamond.merge_registry(left,right),merged)
        self.assertEqual({n for n in merged if merged[n]!=left[n]},{'Bootstrap.CrateSession'})
        self.assertEqual({n for n in merged if merged[n]!=right[n]},{'Bootstrap.CrateSession','Bootstrap.CrateQuery'})
        self.assertEqual(before_full_registry(base),before_source_context_registry(base))
        for module,path in [('Bootstrap.CrateSession','CrateSession.hs'),('Bootstrap.CrateQuery','CrateQuery.hs')]:
            self.assertEqual(hashlib.sha256(prebinary_read_bytes(ROOT/'libraries/mlf-crates/Bootstrap'/path)).hexdigest(),prebinary_registry(base)[module])

    def test_diamond_rejects_unknown_partial_old_and_reordered_owner(self):
        raw=prior_owner(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs')
        for edge in ('left','right'):
            parent=diamond.to_parent(raw,edge)
            for bad in (raw+b' ',raw[:-1],parent):
                with self.subTest(edge=edge),self.assertRaises(ValueError):diamond.to_parent(bad,edge)
            for edit in diamond.edge_manifest(edge)['edits']:
                bad=raw.replace(edit['new'].encode(),edit['old'].encode(),1)
                with self.assertRaises(ValueError):diamond.to_parent(bad,edge)
        for adapter in (scratch,source_context,full,survivors):
            with self.assertRaises(ValueError):adapter.restore_previous_owner(raw)
        for bad in (raw+b' ',raw[:-1]):
            with self.assertRaises(ValueError):diamond.storage_history(bad)
            with self.assertRaises(ValueError):diamond.upstream_history(bad)

    def test_diamond_rejects_mixed_or_stale_complete_registries(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        merged=before_memo_registry(base);left=before_diamond_registry(base);right=full_only_registry(base)
        for name in ('Bootstrap.CrateQuery','Bootstrap.CrateSession'):
            for value in ('0'*64,right[name],merged[name]):
                bad={**left,name:value}
                if bad!=left:
                    with self.assertRaises(ValueError):diamond.merge_registry(bad,right)
            for value in ('0'*64,left[name],merged[name]):
                bad={**right,name:value}
                if bad!=right:
                    with self.assertRaises(ValueError):diamond.merge_registry(left,bad)
        bad={**merged,'Bootstrap.CrateSession':left['Bootstrap.CrateSession']}
        with self.assertRaises(ValueError):diamond.registry_to_parent(bad,'left')
        for bad in (dict(list(left.items())[1:]),{**left,'Unexpected':'1'*64}):
            with self.assertRaises(ValueError):diamond.merge_registry(bad,right)

    def test_diamond_manifest_and_edges_remain_fixed(self):
        original=(diamond.HERE/'source-migration.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'source-migration.json'
            for raw in (original+b' ',b'{}'):
                path.write_bytes(raw)
                with patch.object(diamond,'HERE',root),self.assertRaises(ValueError):diamond.manifest()
            value=json.loads(original);value['module_count']=127
            raw=json.dumps(value).encode();path.write_bytes(raw)
            with patch.object(diamond,'HERE',root),patch.object(diamond,'MANIFEST_SHA',hashlib.sha256(raw).hexdigest()),self.assertRaises(ValueError):diamond.manifest()
        raw=prior_owner(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs')
        for edge in ('left','right'):
            bad=json.loads(json.dumps(diamond.edge_manifest(edge)));bad['edits'][0]['old']+='\n'
            with patch.object(diamond,'edge_manifest',return_value=bad),self.assertRaises(ValueError):diamond.to_parent(raw,edge)
        value=diamond.manifest()
        self.assertEqual(value['left_parent_manifest_sha256'],migration.SCRATCH_MANIFEST_SHA)
        self.assertEqual(value['right_parent_manifest_sha256'],migration.FULL_MANIFEST_SHA)

    def test_read_reuse_complete_owners_registry_and_original_diamond(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        current=before_publication_registry(base);previous=before_memo_registry(base)
        self.assertEqual(memo.advance_registry(previous),current)
        self.assertEqual({n for n in current if current[n]!=previous[n]},set(memo.OWNERS))
        for module,o in memo.OWNERS.items():
            raw=before_publication_owner(ROOT/o['path'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),current[module])
            prior=memo.restore_previous_owner(raw,module)
            self.assertEqual(hashlib.sha256(prior).hexdigest(),previous[module])
            if module=='Bootstrap.CrateSession':
                self.assertEqual(graph.without_context_read_reuse(raw),prior)
                self.assertEqual(hashlib.sha256(diamond.verify_diamond(prior)).hexdigest(),full.OLD_SHA)
                with self.assertRaises(ValueError):diamond.to_left(raw)
            else:
                self.assertEqual(hashlib.sha256(diamond.query_to_right(prior)).hexdigest(),source_context.QUERY_OLD_SHA)

    def test_read_reuse_rejects_stale_partial_unknown_owners_and_order(self):
        for module,o in memo.OWNERS.items():
            raw=before_publication_owner(ROOT/o['path']);prior=memo.restore_previous_owner(raw,module)
            for bad in (prior,raw+b' ',raw[:-1]):
                with self.assertRaises(ValueError):memo.restore_previous_owner(bad,module)
            for edit in memo.owner_delta(module)['edits']:
                partial=raw.replace(edit['new'].encode(),edit['old'].encode(),1)
                with self.assertRaises(ValueError):memo.restore_previous_owner(partial,module)
            for adapter in (scratch,source_context):
                with self.assertRaises(ValueError):adapter.restore_previous_owner(raw,module)
        with self.assertRaises(ValueError):memo.restore_previous_owner(b'', 'Unknown')

    def test_read_reuse_registry_rejects_replayed_mixed_and_polluted(self):
        base=json.loads((migration.HERE/'source-migration.json').read_bytes())['old_sources']
        current=before_publication_registry(base);prior=before_memo_registry(base)
        with self.assertRaises(ValueError):memo.advance_registry(current)
        with self.assertRaises(ValueError):memo.registry_to_parent(prior)
        for n,o in memo.OWNERS.items():
            with self.assertRaises(ValueError):memo.registry_to_parent({**current,n:o['old']})
            with self.assertRaises(ValueError):memo.advance_registry({**prior,n:o['new']})
        for bad in ({**current,'Unknown':'0'*64},dict(list(current.items())[1:])):
            with self.assertRaises(ValueError):memo.registry_to_parent(bad)

    def test_read_reuse_fixed_manifests_and_complete_inverse_blocks(self):
        original=(memo.HERE/'source-migration.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for raw in (original+b' ',b'{}'):
                (root/'source-migration.json').write_bytes(raw)
                with patch.object(memo,'HERE',root),self.assertRaises(ValueError):memo.manifest()
            value=json.loads(original);value['module_count']=127
            raw=json.dumps(value).encode();(root/'source-migration.json').write_bytes(raw)
            with patch.object(memo,'HERE',root),patch.object(memo,'MANIFEST_SHA',hashlib.sha256(raw).hexdigest()),self.assertRaises(ValueError):memo.manifest()
        for module,o in memo.OWNERS.items():
            raw=before_publication_owner(ROOT/o['path']);bad=json.loads(json.dumps(memo.owner_delta(module)))
            bad['edits'][0]['old']+='\n'
            with patch.object(memo,'owner_delta',return_value=bad),self.assertRaises(ValueError):memo.restore_previous_owner(raw,module)


    def test_publication_single_owner_registry_and_live_inventory(self):
        base = json.loads((migration.HERE / 'source-migration.json').read_bytes())['old_sources']
        current = before_key_parts_registry(base)
        previous = before_publication_registry(base)
        spec = publication.manifest()
        self.assertEqual(spec['parent_manifest_sha256'], memo.MANIFEST_SHA)
        self.assertEqual(spec['module_count'], 128)
        self.assertEqual(spec['unchanged_count'], 127)
        self.assertEqual(set(publication.OWNERS), {'Bootstrap.CrateQuery'})
        self.assertEqual({name for name in current if current[name] != previous[name]},
                         {'Bootstrap.CrateQuery'})
        self.assertEqual(len(current), 128)
        self.assertEqual(set(current), set(previous))
        self.assertEqual({n: current[n] for n in current if n != publication.OWNER},
                         {n: previous[n] for n in previous if n != publication.OWNER})
        self.assertEqual(previous, memo.advance_registry(before_memo_registry(base)))
        inventory = json.loads(prebinary_read_bytes(ROOT / 'shared-sources.json'))
        actual = {row['module']: hashlib.sha256(prebinary_read_bytes(ROOT / row['path'])).hexdigest()
                  for row in inventory['modules']}
        self.assertEqual(key_parts.registry_to_parent(read_window.registry_to_parent(actual)), current)
        self.assertEqual(current['Bootstrap.CrateSession'],
                         spec['unchanged_owners']['Bootstrap.CrateSession']['sha256'])
        self.assertEqual(publication.advance_registry(previous), current)

    def test_publication_complete_owner_inverse_and_layer_order(self):
        owner = publication.OWNERS[publication.OWNER]
        raw = before_key_parts_owner(ROOT / owner['path'])
        previous = publication.restore_previous_owner(raw)
        self.assertEqual(hashlib.sha256(previous).hexdigest(), owner['old'])
        forward = previous
        for edit in publication.owner_delta()['edits']:
            self.assertEqual(forward.count(edit['old'].encode()), 1)
            forward = forward.replace(edit['old'].encode(), edit['new'].encode())
        self.assertEqual(forward, raw)
        self.assertEqual(publication.project_owner(raw, publication.OWNER), previous)
        with self.assertRaises(ValueError):
            memo.restore_previous_owner(raw, publication.OWNER)
        prior = memo.restore_previous_owner(previous, publication.OWNER)
        self.assertEqual(hashlib.sha256(prior).hexdigest(), memo.OWNERS[publication.OWNER]['old'])
        session = before_key_parts_owner(ROOT / memo.OWNERS['Bootstrap.CrateSession']['path'])
        self.assertEqual(publication.project_owner(session, 'Bootstrap.CrateSession'), session)
        self.assertEqual(prior_owner(ROOT / owner['path']), prior)
        with self.assertRaises(ValueError):
            publication.restore_previous_owner(session, 'Bootstrap.CrateSession')

    def test_publication_rejects_old_partial_duplicate_and_unknown_owners(self):
        raw = before_key_parts_owner(ROOT / publication.OWNERS[publication.OWNER]['path'])
        previous = publication.restore_previous_owner(raw)
        invalid = [previous, raw + b' ', raw[:-1]]
        for edit in publication.owner_delta()['edits']:
            invalid += [raw.replace(edit['new'].encode(), edit['old'].encode(), 1),
                        raw + edit['new'].encode()]
        for changed in invalid:
            self.assertNotEqual(changed, raw)
            with self.subTest(size=len(changed)), self.assertRaises(ValueError):
                publication.restore_previous_owner(changed)
            with self.subTest(projected=True, size=len(changed)), self.assertRaises(ValueError):
                publication.project_owner(changed, publication.OWNER)
        with self.assertRaises(ValueError):
            publication.owner_delta('Unknown')
        with self.assertRaises(ValueError):
            publication.project_owner(raw, 'Unknown')
        session = before_key_parts_owner(ROOT / memo.OWNERS['Bootstrap.CrateSession']['path'])
        old_session = memo.restore_previous_owner(session)
        for changed in (session + b' ', old_session):
            with self.assertRaises(ValueError):
                publication.project_owner(changed, 'Bootstrap.CrateSession')

    def test_publication_registry_rejects_stale_mixed_and_polluted(self):
        base = json.loads((migration.HERE / 'source-migration.json').read_bytes())['old_sources']
        current = before_key_parts_registry(base)
        previous = before_publication_registry(base)
        with self.assertRaises(ValueError):
            publication.advance_registry(current)
        with self.assertRaises(ValueError):
            publication.registry_to_parent(previous)
        bad_current = [
            {**current, publication.OWNER: previous[publication.OWNER]},
            {**current, 'Bootstrap.CrateSession': memo.OWNERS['Bootstrap.CrateSession']['old']},
            {**current, 'Bootstrap.Map': '0' * 64},
            {**current, 'Unknown': '1' * 64},
            dict(list(current.items())[1:]),
        ]
        for changed in bad_current:
            with self.assertRaises(ValueError):
                publication.registry_to_parent(changed)
        for changed in ({**previous, publication.OWNER: current[publication.OWNER]},
                        {**previous, 'Bootstrap.CrateSession': memo.OWNERS['Bootstrap.CrateSession']['old']},
                        {**previous, 'Unknown': '1' * 64}, dict(list(previous.items())[1:])):
            with self.assertRaises(ValueError):
                publication.advance_registry(changed)
        with self.assertRaises(ValueError):
            publication.require_registry(current, 'unknown')

    def test_publication_complete_lock_inverse_rejects_mixed_or_stale(self):
        raw = before_key_parts_lock()
        previous = publication.restore_previous_lock(raw)
        self.assertEqual(hashlib.sha256(previous).hexdigest(),
                         publication.EXPECTED['parent_lock_sha256'])
        self.assertEqual(publication.advance_lock(previous), raw)
        parent = json.loads(previous)
        crates = [p for p in parent['packages'] if p['name'] == 'mlf-crates']
        self.assertEqual(len(crates), 1)
        self.assertEqual(crates[0]['sources']['Bootstrap/CrateQuery.hs'],
                         publication.OWNERS[publication.OWNER]['old'])
        self.assertEqual(crates[0]['sources']['Bootstrap/CrateSession.hs'],
                         publication.EXPECTED['unchanged_owners']['Bootstrap.CrateSession']['sha256'])
        session = memo.OWNERS['Bootstrap.CrateSession']
        mixed = raw.replace(session['new'].encode(), session['old'].encode())
        for changed in (previous, raw + b' ', mixed, raw[:-1], b'{}'):
            self.assertNotEqual(changed, raw)
            with self.assertRaises(ValueError):
                publication.restore_previous_lock(changed)
        for changed in (raw, previous + b' ', b'{}'):
            with self.assertRaises(ValueError):
                publication.advance_lock(changed)

    def test_publication_manifest_tamper_and_rehashed_scope_fail_closed(self):
        original = (publication.HERE / 'source-migration.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'source-migration.json'
            for raw in (original + b' ', b'{}'):
                path.write_bytes(raw)
                with patch.object(publication, 'HERE', root), self.assertRaises(ValueError):
                    publication.manifest()
            mutations = [
                ('module_count', 127), ('unchanged_count', 126),
                ('parent_ref', '0' * 40), ('parent_manifest_sha256', '0' * 64),
                ('changed_sources', {}), ('unchanged_owners', {}),
                ('host_sources', {'Unexpected': '1' * 64}), ('frozen_references', {}),
                ('parent_registry_sha256', '0' * 64), ('current_lock_sha256', '0' * 64),
            ]
            for key, changed in mutations:
                value = json.loads(original)
                value[key] = changed
                raw = json.dumps(value).encode()
                path.write_bytes(raw)
                with patch.object(publication, 'HERE', root), patch.object(
                        publication, 'MANIFEST_SHA', hashlib.sha256(raw).hexdigest()), self.assertRaises(ValueError):
                    publication.manifest()

    def test_publication_delta_is_fixed_and_inverse_checks_complete_bytes(self):
        spec = publication.manifest()
        owner = publication.OWNERS[publication.OWNER]
        original = (publication.HERE / owner['file']).read_bytes()
        reordered = json.loads(original)
        reordered['edits'].reverse()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for raw in (original + b' ', b'{}', json.dumps(reordered).encode()):
                (root / owner['file']).write_bytes(raw)
                with patch.object(publication, 'HERE', root), patch.object(
                        publication, 'manifest', return_value=spec), self.assertRaises(ValueError):
                    publication.owner_delta()
        raw = before_key_parts_owner(ROOT / owner['path'])
        for field in ('old', 'new'):
            bad = json.loads(json.dumps(publication.owner_delta()))
            bad['edits'][0][field] += '\n'
            with patch.object(publication, 'owner_delta', return_value=bad), self.assertRaises(ValueError):
                publication.restore_previous_owner(raw)
        bad = json.loads(json.dumps(publication.owner_delta()))
        bad['edits'].pop()
        with patch.object(publication, 'owner_delta', return_value=bad), self.assertRaises(ValueError):
            publication.restore_previous_owner(raw)

    def test_publication_freezes_all_predecessors_and_current_host_contract(self):
        spec = publication.manifest()
        self.assertEqual(spec['frozen_references']['source-context-read-reuse/source-migration.json'],
                         memo.MANIFEST_SHA)
        host = 'tools/performance/llvm-memory/host-delta.json'
        delta = json.loads(prebinary_read_bytes(ROOT / host))
        self.assertEqual(delta['new'], '50780c7183d62aa7568c0a799fdf5829b6ea60cbbc67cca7fd1a3f08bc4ba9c5')
        self.assertEqual(spec['frozen_references']['llvm-memory/host-delta.json'],
                         hashlib.sha256(prebinary_read_bytes(ROOT / host)).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'source-context-publication'
            root.mkdir()
            (root / 'source-migration.json').write_bytes(
                (publication.HERE / 'source-migration.json').read_bytes())
            for name in spec['frozen_references']:
                target = root.parent / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((publication.HERE.parent / name).read_bytes())
            with patch.object(publication, 'HERE', root):
                self.assertEqual(publication.manifest(), spec)
                for name in spec['frozen_references']:
                    target = root.parent / name
                    raw = target.read_bytes()
                    target.write_bytes(raw + b' ')
                    with self.subTest(reference=name), self.assertRaises(ValueError):
                        publication.manifest()
                    target.write_bytes(raw)
                self.assertEqual(publication.manifest(), spec)

    def test_key_parts_complete_single_owner_registry_lock_and_frozen_chain(self):
        base = json.loads((migration.HERE / 'source-migration.json').read_bytes())['old_sources']
        current = before_read_window_registry(base)
        previous = before_key_parts_registry(base)
        spec = key_parts.manifest()
        owner = key_parts.OWNERS[key_parts.OWNER]
        self.assertEqual(spec['parent_manifest_sha256'], publication.MANIFEST_SHA)
        self.assertEqual((spec['module_count'], spec['unchanged_count']), (128, 127))
        self.assertEqual(set(key_parts.OWNERS), {'Bootstrap.CrateQuery'})
        self.assertEqual(set(current), set(previous))
        self.assertEqual({n for n in current if current[n] != previous[n]}, {key_parts.OWNER})
        self.assertEqual({n: current[n] for n in current if n != key_parts.OWNER},
                         {n: previous[n] for n in previous if n != key_parts.OWNER})
        self.assertEqual(key_parts.advance_registry(previous), current)
        self.assertEqual(previous, publication.advance_registry(before_publication_registry(base)))
        inventory = json.loads(prebinary_read_bytes(ROOT / 'shared-sources.json'))
        actual = {row['module']: hashlib.sha256(prebinary_read_bytes(ROOT / row['path'])).hexdigest()
                  for row in inventory['modules']}
        self.assertEqual(read_window.registry_to_parent(actual), current)
        raw = before_read_window_owner(ROOT / owner['path'])
        prior = key_parts.restore_previous_owner(raw)
        self.assertEqual(prior, before_key_parts_owner(ROOT / owner['path']))
        self.assertEqual(hashlib.sha256(prior).hexdigest(), owner['old'])
        forward = prior
        for edit in key_parts.owner_delta()['edits']:
            self.assertEqual(forward.count(edit['old'].encode()), 1)
            forward = forward.replace(edit['old'].encode(), edit['new'].encode())
        self.assertEqual(forward, raw)
        self.assertEqual(key_parts.project_owner(raw, key_parts.OWNER), prior)
        for adapter in (publication, memo, scratch, source_context):
            with self.subTest(out_of_order=adapter.__name__), self.assertRaises(ValueError):
                adapter.restore_previous_owner(raw, key_parts.OWNER)
        self.assertEqual(publication.restore_previous_owner(prior),
                         before_publication_owner(ROOT / owner['path']))
        session = before_read_window_owner(ROOT / memo.OWNERS['Bootstrap.CrateSession']['path'])
        self.assertEqual(key_parts.project_owner(session, 'Bootstrap.CrateSession'), session)
        self.assertEqual(publication.project_owner(session, 'Bootstrap.CrateSession'), session)
        lock = before_read_window_lock()
        parent_lock = key_parts.restore_previous_lock(lock)
        self.assertEqual(parent_lock, before_key_parts_lock())
        self.assertEqual(key_parts.advance_lock(parent_lock), lock)
        self.assertEqual(hashlib.sha256(parent_lock).hexdigest(), spec['parent_lock_sha256'])
        self.assertEqual(publication.advance_lock(publication.restore_previous_lock(parent_lock)), parent_lock)
        expected_refs = dict(publication.manifest()['frozen_references'])
        for name in ('query-delta.json', 'source-migration.json', 'source_contract.py'):
            expected_refs['source-context-publication/' + name] = hashlib.sha256(
                (publication.HERE / name).read_bytes()).hexdigest()
        self.assertEqual(spec['frozen_references'], expected_refs)
        self.assertEqual(len(expected_refs), 24)
        for field in ('added_sources', 'removed_sources', 'host_sources'):
            self.assertEqual(spec[field], {})
        host = ROOT / 'tools/performance/llvm-memory/host-delta.json'
        self.assertEqual(spec['frozen_references']['llvm-memory/host-delta.json'],
                         hashlib.sha256(host.read_bytes()).hexdigest())
        self.assertEqual(json.loads(host.read_bytes())['new'],
                         '50780c7183d62aa7568c0a799fdf5829b6ea60cbbc67cca7fd1a3f08bc4ba9c5')

    def test_key_parts_rejects_old_partial_unknown_owners_and_stale_locks(self):
        owner = key_parts.OWNERS[key_parts.OWNER]
        raw = before_read_window_owner(ROOT / owner['path'])
        prior = key_parts.restore_previous_owner(raw)
        older = publication.restore_previous_owner(prior)
        invalid = [prior, older, raw + b' ', raw[:-1]]
        for edit in key_parts.owner_delta()['edits']:
            invalid += [raw.replace(edit['new'].encode(), edit['old'].encode(), 1),
                        raw + edit['new'].encode()]
        for changed in invalid:
            self.assertNotEqual(changed, raw)
            with self.subTest(size=len(changed)), self.assertRaises(ValueError):
                key_parts.restore_previous_owner(changed)
            with self.subTest(project=True, size=len(changed)), self.assertRaises(ValueError):
                key_parts.project_owner(changed, key_parts.OWNER)
        for module in ('Unknown', 'Bootstrap.CrateSession'):
            with self.subTest(delta_owner=module), self.assertRaises(ValueError):
                key_parts.owner_delta(module)
        with self.assertRaises(ValueError):
            key_parts.project_owner(raw, 'Unknown')
        session = before_read_window_owner(ROOT / memo.OWNERS['Bootstrap.CrateSession']['path'])
        for changed in (session + b' ', memo.restore_previous_owner(session), raw):
            with self.assertRaises(ValueError):
                key_parts.project_owner(changed, 'Bootstrap.CrateSession')
        lock = before_read_window_lock()
        parent_lock = key_parts.restore_previous_lock(lock)
        session_owner = memo.OWNERS['Bootstrap.CrateSession']
        mixed = lock.replace(session_owner['new'].encode(), session_owner['old'].encode())
        for changed in (parent_lock, publication.restore_previous_lock(parent_lock),
                        lock + b' ', lock[:-1], mixed, b'{}'):
            with self.assertRaises(ValueError):
                key_parts.restore_previous_lock(changed)
        for changed in (lock, parent_lock + b' ', b'{}'):
            with self.assertRaises(ValueError):
                key_parts.advance_lock(changed)
        with self.assertRaises(ValueError):
            publication.restore_previous_lock(lock)

    def test_key_parts_live_registry_rejects_replay_mixed_and_unknown_entries(self):
        base = json.loads((migration.HERE / 'source-migration.json').read_bytes())['old_sources']
        current = before_read_window_registry(base)
        prior = before_key_parts_registry(base)
        older = before_publication_registry(base)
        with self.assertRaises(ValueError):
            key_parts.advance_registry(current)
        for changed in (prior, older,
                        {**current, key_parts.OWNER: prior[key_parts.OWNER]},
                        {**current, 'Bootstrap.CrateSession': memo.OWNERS['Bootstrap.CrateSession']['old']},
                        {**current, 'Bootstrap.Map': '0' * 64},
                        {**current, 'Unknown': '1' * 64}, dict(list(current.items())[1:])):
            with self.assertRaises(ValueError):
                key_parts.registry_to_parent(changed)
        for changed in (current, older,
                        {**prior, 'Bootstrap.CrateSession': memo.OWNERS['Bootstrap.CrateSession']['old']},
                        {**prior, 'Unknown': '1' * 64}, dict(list(prior.items())[1:])):
            with self.assertRaises(ValueError):
                key_parts.advance_registry(changed)
        # Exact historical owners are permitted only after the strict live
        # projection; admitting a golden SHA never admits it as the live input.
        for module, parents in scratch.REPLAY_PARENTS.items():
            for digest in parents:
                with self.subTest(module=module, golden=digest), self.assertRaises(ValueError):
                    key_parts.registry_to_parent({**current, module: digest})
        with self.assertRaises(ValueError):
            key_parts.require_registry(current, 'unknown')
        with self.assertRaises(ValueError):
            publication.registry_to_parent(current)

    def test_key_parts_fixed_manifest_delta_and_every_frozen_reference_fail_closed(self):
        original = (key_parts.HERE / 'source-migration.json').read_bytes()
        spec = key_parts.manifest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'source-context-key-parts'
            root.mkdir()
            path = root / 'source-migration.json'
            for raw in (original + b' ', b'{}'):
                path.write_bytes(raw)
                with patch.object(key_parts, 'HERE', root), self.assertRaises(ValueError):
                    key_parts.manifest()
            mutations = [
                ('module_count', 127), ('unchanged_count', 126),
                ('parent_ref', '0' * 40), ('parent_manifest_sha256', '0' * 64),
                ('owners', {}), ('changed_sources', {}), ('unchanged_owners', {}),
                ('host_sources', {'Unexpected': '1' * 64}), ('frozen_references', {}),
                ('parent_registry_sha256', '0' * 64), ('current_lock_sha256', '0' * 64),
            ]
            for field, changed in mutations:
                value = json.loads(original)
                value[field] = changed
                raw = json.dumps(value).encode()
                path.write_bytes(raw)
                with patch.object(key_parts, 'HERE', root), patch.object(
                        key_parts, 'MANIFEST_SHA', hashlib.sha256(raw).hexdigest()), self.assertRaises(ValueError):
                    key_parts.manifest()
            path.write_bytes(original)
            for name in spec['frozen_references']:
                target = root.parent / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((key_parts.HERE.parent / name).read_bytes())
            with patch.object(key_parts, 'HERE', root):
                self.assertEqual(key_parts.manifest(), spec)
                for name in spec['frozen_references']:
                    target = root.parent / name
                    raw = target.read_bytes()
                    target.write_bytes(raw + b' ')
                    with self.subTest(reference=name), self.assertRaises(ValueError):
                        key_parts.manifest()
                    target.write_bytes(raw)
                self.assertEqual(key_parts.manifest(), spec)
        owner = key_parts.OWNERS[key_parts.OWNER]
        delta_raw = (key_parts.HERE / owner['file']).read_bytes()
        reordered = json.loads(delta_raw)
        reordered['edits'].reverse()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for raw in (delta_raw + b' ', b'{}', json.dumps(reordered).encode()):
                (root / owner['file']).write_bytes(raw)
                with patch.object(key_parts, 'HERE', root), patch.object(
                        key_parts, 'manifest', return_value=spec), self.assertRaises(ValueError):
                    key_parts.owner_delta()
        raw = before_read_window_owner(ROOT / owner['path'])
        for field in ('old', 'new'):
            damaged = json.loads(json.dumps(key_parts.owner_delta()))
            damaged['edits'][0][field] += '\n'
            with patch.object(key_parts, 'owner_delta', return_value=damaged), self.assertRaises(ValueError):
                key_parts.restore_previous_owner(raw)
        damaged = json.loads(json.dumps(key_parts.owner_delta()))
        damaged['edits'].pop()
        with patch.object(key_parts, 'owner_delta', return_value=damaged), self.assertRaises(ValueError):
            key_parts.restore_previous_owner(raw)


    def test_read_window_two_complete_owners_registry_lock_and_layer_order(self):
        base = json.loads((migration.HERE / 'source-migration.json').read_bytes())['old_sources']
        current = prebinary_registry(base)
        previous = before_read_window_registry(base)
        spec = read_window.manifest()
        self.assertEqual(spec['parent_manifest_sha256'], key_parts.MANIFEST_SHA)
        self.assertEqual((spec['module_count'], spec['unchanged_count']), (128, 126))
        self.assertEqual(set(read_window.OWNERS), {'Bootstrap.CrateQuery', 'Bootstrap.CrateSession'})
        self.assertEqual(set(current), set(previous))
        self.assertEqual({n for n in current if current[n] != previous[n]}, set(read_window.OWNERS))
        self.assertEqual({n: current[n] for n in current if n not in read_window.OWNERS},
                         {n: previous[n] for n in previous if n not in read_window.OWNERS})
        self.assertEqual(read_window.advance_registry(previous), current)
        self.assertEqual(previous, key_parts.advance_registry(before_key_parts_registry(base)))
        inventory = json.loads(prebinary_read_bytes(ROOT / 'shared-sources.json'))
        actual = {row['module']: hashlib.sha256(prebinary_read_bytes(ROOT / row['path'])).hexdigest()
                  for row in inventory['modules']}
        self.assertEqual(actual, current)
        for module, owner in read_window.OWNERS.items():
            raw = prebinary_read_bytes(ROOT / owner['path'])
            prior = read_window.restore_previous_owner(raw, module)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), current[module])
            self.assertEqual(hashlib.sha256(prior).hexdigest(), previous[module])
            self.assertEqual(prior, before_read_window_owner(ROOT / owner['path']))
            forward = prior
            for edit in read_window.owner_delta(module)['edits']:
                self.assertEqual(forward.count(edit['old'].encode()), 1)
                forward = forward.replace(edit['old'].encode(), edit['new'].encode())
            self.assertEqual(forward, raw)
            self.assertEqual(read_window.project_owner(raw, module), prior)
            # Both new owners must first pass this exact full-byte inverse.
            with self.subTest(module=module), self.assertRaises(ValueError):
                key_parts.project_owner(raw, module)
            for adapter in (publication, memo, scratch, source_context):
                with self.subTest(module=module, out_of_order=adapter.__name__), self.assertRaises(ValueError):
                    adapter.project_owner(raw, module) if adapter is publication else adapter.restore_previous_owner(raw, module)
            if module == 'Bootstrap.CrateSession':
                self.assertEqual(graph.without_context_read_reuse(raw), memo.restore_previous_owner(prior))
                # Existing historical-source oracles may admit the exact K
                # parent, but it is never accepted by the new live contract.
                self.assertEqual(graph.without_context_read_reuse(prior), memo.restore_previous_owner(prior))
            else:
                self.assertEqual(key_parts.restore_previous_owner(prior),
                                 before_key_parts_owner(ROOT / owner['path']))
        lock = prebinary_read_bytes(ROOT / 'mlf.lock')
        parent_lock = read_window.restore_previous_lock(lock)
        self.assertEqual(parent_lock, before_read_window_lock())
        self.assertEqual(read_window.advance_lock(parent_lock), lock)
        self.assertEqual(hashlib.sha256(parent_lock).hexdigest(), spec['parent_lock_sha256'])
        self.assertEqual(key_parts.advance_lock(key_parts.restore_previous_lock(parent_lock)), parent_lock)
        prior_crates = [c for c in json.loads(parent_lock)['packages'] if c['name'] == 'mlf-crates']
        self.assertEqual(len(prior_crates), 1)
        for module, owner in read_window.OWNERS.items():
            self.assertEqual(prior_crates[0]['sources']['Bootstrap/' + module.split('.')[-1] + '.hs'], owner['old'])

    def test_read_window_rejects_old_partial_unknown_and_single_owner_transitions(self):
        for module, owner in read_window.OWNERS.items():
            raw = prebinary_read_bytes(ROOT / owner['path'])
            prior = read_window.restore_previous_owner(raw, module)
            invalid = [prior, raw + b' ', raw[:-1]]
            for edit in read_window.owner_delta(module)['edits']:
                invalid += [raw.replace(edit['new'].encode(), edit['old'].encode(), 1),
                            raw + edit['new'].encode()]
            for changed in invalid:
                self.assertNotEqual(changed, raw)
                with self.subTest(module=module, size=len(changed)), self.assertRaises(ValueError):
                    read_window.restore_previous_owner(changed, module)
                with self.subTest(project=module, size=len(changed)), self.assertRaises(ValueError):
                    read_window.project_owner(changed, module)
            other = next(n for n in read_window.OWNERS if n != module)
            with self.assertRaises(ValueError):
                read_window.restore_previous_owner(raw, other)
            if module == 'Bootstrap.CrateSession':
                for changed in (raw + b' ', raw[:-1]):
                    with self.assertRaises(ValueError):
                        graph.without_context_read_reuse(changed)
        with self.assertRaises(ValueError):
            read_window.owner_delta('Unknown')
        with self.assertRaises(ValueError):
            read_window.project_owner(b'', 'Unknown')
        lock = prebinary_read_bytes(ROOT / 'mlf.lock')
        prior_lock = read_window.restore_previous_lock(lock)
        invalid = [prior_lock, lock + b' ', lock[:-1], b'{}']
        for owner in read_window.OWNERS.values():
            # One reversed owner is neither a valid current nor parent lock.
            mixed = lock.replace(owner['new'].encode(), owner['old'].encode(), 1)
            invalid.append(mixed)
            with self.assertRaises(ValueError):
                read_window.advance_lock(mixed)
        for changed in invalid:
            with self.assertRaises(ValueError):
                read_window.restore_previous_lock(changed)
        for changed in (lock, prior_lock + b' ', b'{}'):
            with self.assertRaises(ValueError):
                read_window.advance_lock(changed)
        with self.assertRaises(ValueError):
            key_parts.restore_previous_lock(lock)

    def test_read_window_live_registry_rejects_half_migration_and_historical_golden(self):
        base = json.loads((migration.HERE / 'source-migration.json').read_bytes())['old_sources']
        current = prebinary_registry(base)
        prior = before_read_window_registry(base)
        with self.assertRaises(ValueError):
            read_window.advance_registry(current)
        with self.assertRaises(ValueError):
            read_window.registry_to_parent(prior)
        for module, owner in read_window.OWNERS.items():
            for changed in ({**current, module: owner['old']}, {**prior, module: owner['new']}):
                with self.subTest(module=module), self.assertRaises(ValueError):
                    read_window.registry_to_parent(changed)
                with self.subTest(parent=module), self.assertRaises(ValueError):
                    read_window.advance_registry(changed)
        for side, value in (('current', current), ('parent', prior)):
            for changed in ({**value, 'Bootstrap.Map': '0' * 64},
                            {**value, 'Unknown': '1' * 64}, dict(list(value.items())[1:])):
                with self.assertRaises(ValueError):
                    read_window.require_registry(changed, side)
        for module, parents in scratch.REPLAY_PARENTS.items():
            for digest in parents:
                with self.subTest(module=module, golden=digest), self.assertRaises(ValueError):
                    read_window.registry_to_parent({**current, module: digest})
        with self.assertRaises(ValueError):
            read_window.require_registry(current, 'unknown')
        with self.assertRaises(ValueError):
            key_parts.registry_to_parent(current)

    def test_read_window_fixed_manifests_deltas_and_all_predecessors_fail_closed(self):
        original = (read_window.HERE / 'source-migration.json').read_bytes()
        spec = read_window.manifest()
        expected_refs = dict(key_parts.manifest()['frozen_references'])
        for name in ('query-delta.json', 'source-migration.json', 'source_contract.py'):
            expected_refs['source-context-key-parts/' + name] = hashlib.sha256(
                (key_parts.HERE / name).read_bytes()).hexdigest()
        self.assertEqual(spec['frozen_references'], expected_refs)
        self.assertEqual(len(expected_refs), 27)
        for field in ('added_sources', 'removed_sources', 'host_sources', 'unchanged_owners'):
            self.assertEqual(spec[field], {})
        self.assertEqual(json.loads(prebinary_read_bytes(ROOT / 'tools/performance/llvm-memory/host-delta.json'))['new'],
                         '50780c7183d62aa7568c0a799fdf5829b6ea60cbbc67cca7fd1a3f08bc4ba9c5')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'source-context-read-window'
            root.mkdir()
            path = root / 'source-migration.json'
            for raw in (original + b' ', b'{}'):
                path.write_bytes(raw)
                with patch.object(read_window, 'HERE', root), self.assertRaises(ValueError):
                    read_window.manifest()
            mutations = [
                ('module_count', 127), ('unchanged_count', 127),
                ('parent_ref', '0' * 40), ('parent_manifest_sha256', '0' * 64),
                ('owners', {}), ('changed_sources', {}), ('frozen_references', {}),
                ('host_sources', {'Unexpected': '1' * 64}),
                ('parent_registry_sha256', '0' * 64), ('current_lock_sha256', '0' * 64),
            ]
            for field, changed in mutations:
                value = json.loads(original); value[field] = changed
                raw = json.dumps(value).encode(); path.write_bytes(raw)
                with patch.object(read_window, 'HERE', root), patch.object(
                        read_window, 'MANIFEST_SHA', hashlib.sha256(raw).hexdigest()), self.assertRaises(ValueError):
                    read_window.manifest()
            path.write_bytes(original)
            for name in spec['frozen_references']:
                target = root.parent / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((read_window.HERE.parent / name).read_bytes())
            with patch.object(read_window, 'HERE', root):
                self.assertEqual(read_window.manifest(), spec)
                for name in spec['frozen_references']:
                    target = root.parent / name; raw = target.read_bytes()
                    target.write_bytes(raw + b' ')
                    with self.subTest(reference=name), self.assertRaises(ValueError):
                        read_window.manifest()
                    target.write_bytes(raw)
                self.assertEqual(read_window.manifest(), spec)
        for module, owner in read_window.OWNERS.items():
            original_delta = (read_window.HERE / owner['file']).read_bytes()
            reordered = json.loads(original_delta); reordered['edits'].reverse()
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for raw in (original_delta + b' ', b'{}', json.dumps(reordered).encode()):
                    (root / owner['file']).write_bytes(raw)
                    with patch.object(read_window, 'HERE', root), patch.object(
                            read_window, 'manifest', return_value=spec), self.assertRaises(ValueError):
                        read_window.owner_delta(module)
            raw = prebinary_read_bytes(ROOT / owner['path'])
            for field in ('old', 'new'):
                damaged = json.loads(json.dumps(read_window.owner_delta(module)))
                damaged['edits'][0][field] += '\n'
                with patch.object(read_window, 'owner_delta', return_value=damaged), self.assertRaises(ValueError):
                    read_window.restore_previous_owner(raw, module)
            damaged = json.loads(json.dumps(read_window.owner_delta(module)))
            damaged['edits'].pop()
            with patch.object(read_window, 'owner_delta', return_value=damaged), self.assertRaises(ValueError):
                read_window.restore_previous_owner(raw, module)



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




class BinarySourceBoundaryTests(unittest.TestCase):
    def test_actual_live137_then_exact_historical128(self):
        binary = migration.binary_contract()
        manifest = json.loads((ROOT / 'shared-sources.json').read_bytes())
        actual = {row['module']: hashlib.sha256((ROOT / row['path']).read_bytes()).hexdigest()
                  for row in manifest['modules']}
        binary.require_registry(actual, 'current')
        self.assertEqual(len(actual), 137)
        self.assertIn('Bootstrap.SourceUnit', actual)
        # Fixture preparation must not replace coverage of public live gates.
        historical = json.loads((migration.HERE / 'source-migration.json').read_bytes())
        self.assertEqual(migration.migrate(historical['old_sources']), actual)
        old_hosts = {name: row['old'] for name, row in historical['host_sources'].items()}
        live_hosts = binary.live_host_inventory(ROOT)
        self.assertEqual(migration.host_sources(old_hosts),
                         {name: live_hosts[name] for name in old_hosts})
        parent = binary.registry_to_parent(actual, binary.added_source_bytes(ROOT))
        self.assertEqual(parent, binary.parent['registry'])
        self.assertEqual(len(parent), 128)
        with self.assertRaises(ValueError):
            binary.require_registry(parent, 'current')
        mixed = dict(actual)
        changed = next(name for name in parent if parent[name] != actual[name])
        mixed[changed] = parent[changed]
        with self.assertRaises(ValueError):
            binary.require_registry(mixed, 'current')

    def test_reviewed_source_repairs_project_all_declared_owners(self):
        binary = migration.binary_contract()
        names = ('Bootstrap.Layout', 'Package.Benchmark', 'Package.Verification', 'Tests.CompilerTests')
        for module in names:
            path = binary.value['module_paths'][module]
            live = (ROOT / path).read_bytes()
            with self.subTest(module=module):
                # Both endpoints are authenticated independently: exact new
                # bytes from the live source manifest and exact old Git bytes,
                # followed by every existing binary/numeric/API inverse.
                self.assertEqual(hashlib.sha256(live).hexdigest(), binary.changes[path][1])
                previous = (binary.archived / path).read_bytes()
                self.assertEqual(hashlib.sha256(previous).hexdigest(), binary.changes[path][0])
                historical = binary.previous.restore_path(previous, path)
                self.assertEqual(prebinary_read_bytes(ROOT / path), historical)
                self.assertEqual(binary.project_owner(live, module), historical)
                self.assertEqual(binary.advance_path(historical, path), live)
                # Mutations of either endpoint and cross-owner substitution
                # must fail; the authenticated conversion is not a hash reset.
                for changed in (live + b' ', previous, historical, b''):
                    with self.assertRaises(ValueError):
                        binary.project_owner(changed, module)
                with patch.object(Path, 'read_bytes', return_value=live + b' '), self.assertRaises(ValueError):
                    prebinary_read_bytes(ROOT / path)
                with self.assertRaises(ValueError):
                    binary.project_owner(live, 'Bootstrap.Types')

    def test_full_shared_source_projection_uses_declared_inventory_not_prefix(self):
        binary = migration.binary_contract()
        registry = json.loads(prebinary_read_bytes(ROOT / 'shared-sources.json'))
        actual = {row['module']: hashlib.sha256(prebinary_read_bytes(ROOT / row['path'])).hexdigest()
                  for row in registry['modules']}
        self.assertEqual(actual, binary.parent['registry'])
        self.assertIn('Tests.CompilerTests', actual)
        for prefix in ('tests/', 'testing/'):
            owners = [row for row in registry['modules'] if row['path'].startswith(prefix)]
            self.assertTrue(owners)
            for row in owners:
                self.assertIn(row['path'], binary.value['current_files'])
        # Even a plausible production path absent from the manifest must not
        # become an unguarded passthrough when the declared path route changes.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'libraries/unregistered/Unknown.hs'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'unknown production source')
            with patch.dict(globals(), ROOT=root), self.assertRaises(ValueError):
                prebinary_read_bytes(path)

    def test_added_bytes_required_before_inverse_deletion(self):
        binary = migration.binary_contract()
        actual = binary.live_registry(ROOT)
        additions = binary.added_source_bytes(ROOT)
        with self.assertRaises(ValueError):
            binary.registry_to_parent(actual, {})
        for name in additions:
            tampered = dict(additions)
            tampered[name] += b' '
            with self.subTest(module=name), self.assertRaises(ValueError):
                binary.registry_to_parent(actual, tampered)

    def test_mutable_history_recovers_exact_old_bytes(self):
        binary = migration.binary_contract()
        for name in ('patricia/source_migration.py', 'patricia/test_adapters.py'):
            raw = (ROOT / 'tools/performance' / name).read_bytes()
            old = binary.restore_maintenance(raw, name)
            self.assertEqual(hashlib.sha256(old).hexdigest(), binary.parent['frozen_history'][name])
            with self.subTest(path=name), self.assertRaises(ValueError):
                binary.restore_maintenance(raw + b' ', name)



    def relocated_checkout(self, directory):
        import shutil
        binary = migration.binary_contract()
        checkout = Path(directory) / 'relocated-checkout'
        history = checkout / 'tools/performance'
        bundle = history / 'artifact-binary'
        copies = [(ROOT / name, checkout / name) for name in binary.value['current_files']]
        history_names = set(binary.parent['frozen_history']) | set(binary.maintenance_parent['files'])
        copies += [(ROOT / 'tools/performance' / name, history / name) for name in history_names]
        bundle_names = set(binary.metadata_paths)
        copies += [(binary.directory / name, bundle / name) for name in bundle_names]
        # New finite relocation fixture, NOT the old 8MiB unit-view allowance.
        # Actual bytes must enter the parent's future unit/ROOT reservation.
        copy_bytes = sum(source.stat().st_size for source, _ in copies)
        self.assertLessEqual(copy_bytes, 64 * 1024 * 1024)
        self.assertEqual(len({str(target) for _, target in copies}), len(copies))
        for source, target in copies:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return binary, checkout, history, bundle

    def test_relocated_actual_checkout_default_and_explicit_roots(self):
        import types
        with tempfile.TemporaryDirectory() as directory:
            binary, checkout, history, bundle = self.relocated_checkout(directory)
            before = (bundle / 'builtin-verification-receipt.json').read_bytes()
            loader_path = bundle / 'source_migration_adapter.py'
            loader = types.ModuleType('relocated_binary_source_loader')
            loader.__file__ = str(loader_path)
            exec(compile(loader_path.read_bytes(), str(loader_path), 'exec'), loader.__dict__)
            relocated = loader.live_contract(history)
            explicit = type(binary)(bundle, binary.manifest_sha256, history, source_root=checkout)
            for instance in (relocated, explicit):
                self.assertEqual(instance.source_root, checkout.resolve())
                self.assertNotEqual(instance.source_root, binary.source_root)
                self.assertEqual(instance.evidence_source_root, binary.evidence_source_root)
                self.assertEqual(instance.live_registry(checkout), binary.value['current_registry'])
                self.assertEqual(instance.live_source_inventory(checkout), binary.value['current_files'])
            self.assertEqual((bundle / 'builtin-verification-receipt.json').read_bytes(), before)

    def test_relocated_wrong_live_source_and_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            binary, checkout, history, bundle = self.relocated_checkout(directory)
            for name in ('libraries/mlf-crates/Bootstrap/CrateSession.hs', 'shared-sources.json'):
                path = checkout / name
                original = path.read_bytes()
                path.write_bytes(original + b' ')
                try:
                    with self.subTest(live_path=name), self.assertRaises(ValueError):
                        type(binary)(bundle, binary.manifest_sha256, history, source_root=checkout)
                finally:
                    path.write_bytes(original)
            with self.assertRaises(ValueError):
                type(binary)(bundle, '0' * 64, history, source_root=checkout)
            manifest = bundle / 'source-migration.json'
            original = manifest.read_bytes()
            manifest.write_bytes(original + b' ')
            try:
                with self.assertRaises(ValueError):
                    type(binary)(bundle, binary.manifest_sha256, history, source_root=checkout)
            finally:
                manifest.write_bytes(original)

if __name__ == '__main__':
    unittest.main()
