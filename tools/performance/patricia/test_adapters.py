"""Fail-closed checks for the numeric ABI's test-only adapters and Core proof."""
from pathlib import Path
import difflib
import hashlib
import json
import tempfile
import unittest

import adapt_oracles as graph
import legacy_controls as legacy
import run_fingerprint as fingerprint
import source_migration as migration

ROOT = Path(__file__).resolve().parents[3]


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
