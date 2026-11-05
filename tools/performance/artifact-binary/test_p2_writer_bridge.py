#!/usr/bin/env python3
"""Focused explicit writer-adapter authenticity/refusal checks; no compiler run."""
from pathlib import Path
import difflib
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tools/performance/patricia'))
import legacy_controls as legacy

class WriterBridgeControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=ROOT/'tools/performance/artifact-binary/source_migration_adapter.py'
        spec=importlib.util.spec_from_file_location('writer_test_contract',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        cls.adapter=module
        cls.contract=module.live_contract(ROOT/'tools/performance')
        cls.owner='libraries/mlf-crates/Bootstrap/CrateArtifact.hs'
        cls.prior=cls.contract.restore_path((ROOT/cls.owner).read_bytes(),cls.owner)
    def test_complete_prior_owner_and_writer_identity(self):
        self.assertEqual(hashlib.sha256(self.prior).hexdigest(), '88758de08e6ac15b37381b8e78dd5e47d2b50e535794aa3056513fda969fab0a')
        self.assertEqual(hashlib.sha256(legacy.prior_writer_declarations(self.prior)).hexdigest(), '8a6c58e021d4e687617af3ab309d7aeb0dc3ee9a41c0d7b0aee6ee66b0f4ed40')
    def test_writer_change_rejected(self):
        changed=self.prior.replace(b'  writeObject prefix object =',b'  writeObject prefix object = ',1)
        with self.assertRaisesRegex(ValueError,'complete prior'):
            legacy.prior_writer_declarations(changed)
    def test_nonwriter_change_rejected(self):
        with self.assertRaisesRegex(ValueError,'complete prior'):
            legacy.prior_writer_declarations(b'-- changed outside writer\n'+self.prior)
    def test_current_source_change_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in self.contract.value['current_files']:
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
            (root/self.owner).write_bytes((root/self.owner).read_bytes()+b'\n')
            with self.assertRaises(ValueError):
                self.adapter.live_contract(ROOT/'tools/performance',source_root=root)
    def test_explicit_adapter_and_complete_inverse_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'generated'
            modules,ledger=legacy.prepare(ROOT,out,'p123')
            self.assertEqual(modules,['P1Controls','P2Controls','NativeCompatibilityControls','P3Controls'])
            for row in ledger:
                delta=(out/(Path(row['copy']).name+'.ndiff')).read_text().splitlines(keepends=True)
                self.assertEqual(''.join(difflib.restore(delta,1)).encode(),Path(row['source']).read_bytes())
                self.assertEqual(''.join(difflib.restore(delta,2)).encode(),Path(row['copy']).read_bytes())
            scope=json.loads((out/'adaptations.json').read_text())['scope']
            self.assertIn('projected prior text writer',scope)
            self.assertIn('separate required actual public binary writer',scope)
            bridge=(out/'QueryV6Bridge.hs').read_text()
            self.assertIn('MLF-SOURCE-CRATE-QUERY-7',bridge)
            self.assertNotIn('MLF-SOURCE-CRATE-QUERY-6',bridge)
            wrapper=(out/'P2Controls.hs').read_text()
            self.assertLess(wrapper.index('  Legacy.main'),wrapper.index('  Binary.main'))
            self.assertIn('not current binary IO',wrapper)
            self.assertIn('import qualified LegacyArtifactWriter as A', (out/'RetainedP2Controls.hs').read_text())
            projection=(out/'LegacyArtifactWriter.hs').read_text()
            self.assertIn('EnvelopeCrateObject _ _ _ -> Host.errorWithoutStackTrace',projection)
            self.assertNotIn('Old.oldWriteObject',projection)
            proof=json.loads((out/'binary-writer-projection.json').read_text())
            self.assertEqual(proof['retained_control_count'],2503)
            self.assertEqual(proof['actual_binary_control_count'],184)
            self.assertIs(proof['actual_binary_required_before_return'],True)
            self.assertEqual(proof['prior_owner_sha256'],hashlib.sha256(self.prior).hexdigest())
    def test_binary_suite_has_independent_envelope_and_semantic_boundaries(self):
        text=(ROOT/'tools/performance/artifact-binary/BinaryP2WriterControls.hs').read_text()
        self.assertIn('0xedb88320',text)
        self.assertIn('0xcbf43926',text)
        self.assertIn('BS.take 76 raw <> BS.replicate 4 0 <> BS.drop 80 raw',text)
        self.assertIn('Old.oldEncodeObject object',text)
        self.assertIn('Wire.decodeGraph',text)
        self.assertIn('A.readObject',text)
        self.assertIn('unless (observed == expectedCounts)',text)
        self.assertIn('Historical unequal header/body contexts are RAW wire cases only',text)
    def test_frozen_original_control_identity_retained(self):
        self.assertEqual(hashlib.sha256((ROOT/'tools/performance/crate-optimizations/p2/FingerprintDifferential.hs').read_bytes()).hexdigest(),
                         '3247c7b5efb826c95fd02a9480b332f1913ebed3fd16e50c2b4d1af9450e9fc7')
        self.assertEqual(hashlib.sha256((ROOT/'tools/performance/crate-optimizations/p2/FrozenFingerprint.hs').read_bytes()).hexdigest(),
                         '46ccf49aeef6caf9ad440bb315d9e4d1fe4ce65173584a6fdf6c16215b00a3fe')

if __name__=='__main__':unittest.main()
