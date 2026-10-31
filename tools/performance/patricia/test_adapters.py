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
datatype_spec=importlib.util.spec_from_file_location('datatype_context_contract',
    ROOT/'tools/performance/datatype-context/source_contract.py')
datatype=importlib.util.module_from_spec(datatype_spec)
datatype_spec.loader.exec_module(datatype)
contract_spec=importlib.util.spec_from_file_location('contract_context_contract',
    ROOT/'tools/performance/contract-context/source_contract.py')
contract=importlib.util.module_from_spec(contract_spec)
contract_spec.loader.exec_module(contract)


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
            self.assertEqual(migration.host_sources({key: row[field]}), {key: row['new']})
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
        result=migration.apply_changes(migration.migrate(base), {})
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
            self.assertEqual(migration.migrate(base)[name],row['new'])
        bad=json.loads(json.dumps(delta))
        bad['changed_sources']['Bootstrap.CrateQuery']['old']='0'*64
        with patch.object(migration,'contract_delta',return_value=bad),self.assertRaises(ValueError):
            migration.migrate(base)
        source=(ROOT/'libraries/mlf-crates/Bootstrap/CrateSession.hs').read_bytes()
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

    def test_datatype_session_manifest_is_fixed(self):
        original=(datatype.HERE/'session-delta.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for bad in [original+b' ',b'{}']:
                (root/'session-delta.json').write_bytes(bad)
                with patch.object(datatype,'HERE',root),self.assertRaises(ValueError):datatype.manifest()


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
