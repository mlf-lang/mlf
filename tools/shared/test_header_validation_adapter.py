"""Pure adaptation tests; no compiler, interpreter, or generated fixture executes.
HEADER_FIXTURE, HEADER_ORACLE, and HEADER_HISTORY_SOURCE name input files in
an isolated qualification capsule. The latter is the full fixed historical blob.
"""
import os
from pathlib import Path
import unittest
import tempfile
import json
import hashlib
from unittest import mock
import header_validation_adapter as H

class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Path(os.environ['HEADER_FIXTURE']).read_bytes()
        cls.history = Path(os.environ['HEADER_HISTORY_SOURCE']).read_bytes()
        H.authenticate(cls.fixture, 'aa411949945d62c17a21c1191abd93fa7c5fd8ea')
        H.authenticate(cls.history, 'dd5b4630a80803c19afdb219dba2dc4bffc3ea1b')

    def test_literal_pins(self):
        self.assertEqual(H.FIXTURE_BLOB, 'aa411949945d62c17a21c1191abd93fa7c5fd8ea')
        self.assertEqual(H.HISTORICAL_BLOB, 'dd5b4630a80803c19afdb219dba2dc4bffc3ea1b')

    def test_two_exact_inverses(self):
        for lane in ['historical', 'current']:
            generated = H.adapt_fixture(self.fixture, lane)
            self.assertEqual(H.restore_fixture(generated, lane), self.fixture)
            self.assertNotEqual(generated, self.fixture)

    def test_historical_calls_only_redirected(self):
        value = H.adapt_fixture(self.fixture, 'historical')
        self.assertIn(b'let expected=oldName identity e', value)
        self.assertIn(b'H.definitionName identity e', value)
        self.assertIn(b'H.definitionNameEncoded (S.encoded identity) e', value)
        self.assertEqual(value.count(b' N.historicalControls\n'), 1)
        self.assertIn(b'import qualified HeaderNamingOracle as N\n', value)
        self.assertNotIn(b'A.definitionName identity e', value)
        self.assertNotIn(b'A.definitionNameEncoded (S.encoded identity) e', value)

    def test_current_calls_are_real_production(self):
        value = H.adapt_fixture(self.fixture, 'current')
        self.assertIn(b'let expected=N.currentName identity e', value)
        self.assertIn(b'A.definitionName identity e', value)
        self.assertIn(b'A.definitionNameEncoded (N.encoded identity) e', value)
        self.assertEqual(value.count(b' N.controls\n'), 1)

    def test_all_non_naming_assertions_and_tail_retained(self):
        tail = self.fixture[self.fixture.index(b' let fake='):self.fixture.index(b' putStrLn "PASS')]
        for lane in ['historical','current']:
            generated = H.adapt_fixture(self.fixture,lane)
            self.assertIn(tail, generated)
            for line in self.fixture.splitlines():
                if b'assert "' in line:
                    label = line.split(b'assert "',1)[1].split(b'"',1)[0]
                    self.assertEqual(generated.count(b'assert "'+label+b'"'),1)
            self.assertLess(generated.index(b'cached encoded prefix is byte exact'),
                            generated.index(b'forged primitive export still rejected'))

    def test_four_physical_bodies(self):
        generated, body = H.historical_module(self.history)
        start = self.history.index(b'  definitionName ::')
        end = self.history.index(b'  startsWith',start)
        self.assertEqual(body, self.history[start:end])
        self.assertEqual(body.count(b' :: '), 4)
        self.assertIn(b'definitionName identity = definitionNameEncoded (Separate.encoded identity);',body)
        self.assertIn(b'then "Module_"',body)
        self.assertNotIn(b'compactName',body)
        self.assertEqual(generated[len(H.HEADER):-len(H.FOOTER)],body)

    def test_source_corruption_rejected(self):
        for source, pin in [(self.fixture,H.FIXTURE_BLOB),(self.history,H.HISTORICAL_BLOB)]:
            for modified in [source+b'\n', source[:-1], source.replace(b'definitionName',b'wrongName',1)]:
                with self.assertRaisesRegex(ValueError,'source blob identity'):
                    H.authenticate(modified,pin)

    def test_unknown_lane(self):
        for lane in ['', 'old', None]:
            with self.assertRaises(ValueError):
                H.adapt_fixture(self.fixture,lane)

    def test_generated_tail_corruption_rejected(self):
        for lane in ['historical','current']:
            value=H.adapt_fixture(self.fixture,lane)
            for bad in [value+b'\n', value.replace(b'forged primitive export still rejected',b'ignored',1),
                        value.replace(b'primitive membership preserves complete entity identity',b'ignored',1)]:
                with self.assertRaises(ValueError):
                    H.restore_fixture(bad,lane)

    def test_missing_and_duplicate_transform_boundaries(self):
        for edits in [H.HISTORY_EDITS,H.CURRENT_EDITS]:
            for old,new in edits:
                with self.assertRaises(ValueError):
                    H.replace_once(b'',old,new)
                with self.assertRaises(ValueError):
                    H.replace_once(old+old,old,new)

    def test_duplicate_or_missing_extraction_anchor(self):
        # Bypass identity solely to independently reach structural checks;
        # preceding tests separately enforce real full-blob authentication.
        with mock.patch.object(H,'authenticate',side_effect=lambda data,pin:data):
            for bad in [self.history+H.START,self.history+H.END,
                        self.history.replace(H.START,b'  missing ::',1),
                        self.history.replace(H.END,b'  absent',1)]:
                with self.assertRaisesRegex(ValueError,'historical boundaries'):
                    H.historical_module(bad)

    def test_wrong_history_git_request(self):
        result=mock.Mock(stdout=self.history,stderr=b'')
        with mock.patch.object(H.subprocess,'run',return_value=result) as run:
            self.assertEqual(H.fixed_history('/capsule'),self.history)
            run.assert_called_once_with(
                ['git','--no-replace-objects','cat-file','blob','dd5b4630a80803c19afdb219dba2dc4bffc3ea1b'],
                cwd='/capsule',capture_output=True,check=True,timeout=30)
        for output,diagnostic in [(self.history+b'x',b''),(self.history,b'unexpected')]:
            with mock.patch.object(H.subprocess,'run',return_value=mock.Mock(stdout=output,stderr=diagnostic)):
                with self.assertRaises(ValueError):
                    H.fixed_history('/capsule')

    def test_prepare_inventory_and_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'source'
            fixture_dir=root/'tools/shared/fixtures/native'
            fixture_dir.mkdir(parents=True)
            (fixture_dir/'HeaderValidationTests.hs').write_bytes(self.fixture)
            oracle=Path(os.environ['HEADER_ORACLE']).read_bytes()
            (fixture_dir/'HeaderNamingOracle.hs').write_bytes(oracle)
            output=Path(directory)/'output'
            output.mkdir()
            target,evidence=H.prepare(root,output,self.history)
            self.assertEqual(sorted(p.name for p in target.iterdir()),sorted([
                'HistoricalHeaderNames.hs','HeaderNamingOracle.hs',
                'HeaderValidationHistorical.hs','HeaderValidationCurrent.hs',
                'historical-formatter.raw','HeaderValidationTests.original.hs','adaptation.json']))
            self.assertEqual((target/'HeaderValidationTests.original.hs').read_bytes(),self.fixture)
            self.assertEqual((target/'HeaderNamingOracle.hs').read_bytes(),oracle)
            self.assertFalse(evidence['historical_complete_compiler_qualified'])
            self.assertFalse(evidence['qualification_executed'])
            self.assertEqual(json.loads((target/'adaptation.json').read_text()),evidence)
            for name,digest in evidence['generated'].items():
                self.assertEqual(hashlib.sha256((target/name).read_bytes()).hexdigest(),digest)
            with self.assertRaises(FileExistsError):
                H.prepare(root,output,self.history)

    def test_actual_write_corruption_and_readback_corruption_rejected(self):
        oracle=Path(os.environ['HEADER_ORACLE']).read_bytes()
        original_write=Path.write_bytes
        original_read=Path.read_bytes
        for mode in ['write','read']:
            for victim in ['HistoricalHeaderNames.hs','HeaderValidationHistorical.hs',
                           'HeaderValidationCurrent.hs','historical-formatter.raw','adaptation.json']:
                with self.subTest(mode=mode,victim=victim), tempfile.TemporaryDirectory() as directory:
                    root=Path(directory)/'source'
                    fixture_dir=root/'tools/shared/fixtures/native'
                    fixture_dir.mkdir(parents=True)
                    (fixture_dir/'HeaderValidationTests.hs').write_bytes(self.fixture)
                    (fixture_dir/'HeaderNamingOracle.hs').write_bytes(oracle)
                    output=Path(directory)/'output'
                    output.mkdir()
                    destination=output/'header-validation'/victim
                    touched=[]
                    def corrupt_write(path,data):
                        if path == destination:
                            touched.append('write')
                            return original_write(path,data+b'CORRUPTION')
                        return original_write(path,data)
                    def corrupt_read(path):
                        data=original_read(path)
                        if path == destination:
                            touched.append('read')
                            return data+b'CORRUPTION'
                        return data
                    operation = mock.patch.object(Path,'write_bytes',corrupt_write) if mode == 'write' else mock.patch.object(Path,'read_bytes',corrupt_read)
                    with operation:
                        with self.assertRaisesRegex(ValueError,'readback'):
                            H.prepare(root,output,self.history)
                    self.assertEqual(touched,[mode])
                    self.assertTrue(destination.exists())
                    self.assertEqual(original_read(destination).endswith(b'CORRUPTION'),mode=='write')

    def test_historical_controls_are_after_original_tail(self):
        generated=H.adapt_fixture(self.fixture,'historical')
        self.assertLess(generated.index(b'forged primitive export still rejected'),
                        generated.index(b' N.historicalControls'))
        self.assertLess(generated.index(b' N.historicalControls'),generated.index(b' putStrLn "PASS'))
        with self.assertRaises(ValueError):
            H.restore_fixture(generated.replace(b' N.historicalControls\n',b'',1),'historical')


    def test_oracle_action_signatures_reversibly_fix_actual_ghc_failure(self):
        # Actual run01 GHC-39999: both exported no-argument actions were
        # monomorphism-restricted and had an ambiguous Monad/Applicative.
        # This checks the exact source delta, not successful GHC compilation.
        raw = Path(os.environ['HEADER_ORACLE']).read_bytes()
        signatures = [b'controls :: IO ()\n', b'historicalControls :: IO ()\n']
        definitions = [b'controls = do\n', b'historicalControls = do\n']
        def restore(value):
            for signature, definition in zip(signatures, definitions):
                self.assertEqual(value.count(signature), 1)
                self.assertEqual(value.count(signature + definition), 1)
                value = value.replace(signature + definition, definition, 1)
            self.assertEqual(hashlib.sha256(value).hexdigest(),
                '07fa09fda361dadedd82fe99689509b820c8d3f0e6b0a3de4b17d7bbc3408f39')
            self.assertEqual(H.blob_id(value),
                'c65d498bbb32efaaffaa7753c90c3516f7e022dd')
            return value
        previous = restore(raw)
        self.assertNotEqual(raw, previous)
        mutations = []
        for signature, definition in zip(signatures, definitions):
            mutations.extend([
                raw.replace(signature, b'', 1),
                raw.replace(signature, signature.replace(b'IO ()', b'Maybe ()'), 1),
                signature + raw.replace(signature, b'', 1),
                raw.replace(signature, signature + signature, 1),
                raw.replace(signature + definition, signature + b'-- displaced\n' + definition, 1),
            ])
        mutations.append(raw.replace(b'oldGolden =', b'changedGolden =', 1))
        for bad in mutations:
            with self.subTest(mutation_sha256=hashlib.sha256(bad).hexdigest()):
                self.assertNotEqual(bad, raw)
                with self.assertRaises(AssertionError):
                    restore(bad)

if __name__ == '__main__':
    unittest.main()
