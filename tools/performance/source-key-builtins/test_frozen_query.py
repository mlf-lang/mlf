"""Maintain the historical query bytes across the pinned host source endpoints."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from frozen_query import prepare_frozen_query

ROOT = Path(__file__).resolve().parents[3]
TYPES = Path('libraries/mlf-foundation/Bootstrap/Types.hs')
BASE = '720dd649627fbf8b19c7447493a4fdf6fd05eb39'
PRE_SPINES = '265560ef383526c66126a9e79580e39bb4850973'
DICTIONARY_AST = 'fa863042fe3fe16ca7e0a9d43b43a0d8abe728de'
DATA = ROOT / 'tools/performance/datatype-context'
SPARSE = ROOT / 'tools/performance/sparse-contracts'
EXCLUSIONS = [b'\n      ' + ctor + b' -> panic "indexed syntax in historical named query oracle";'
              for ctor in (b'SApplyDictionaries _ _', b'SBindDictionaries _ _')]


class FrozenQueryTests(unittest.TestCase):
    def test_only_new_ast_gets_panic_only_exclusions(self):
        for folder in (DATA, SPARSE):
            with self.subTest(folder=folder.name), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                named = out / 'Named.hs'
                named.write_bytes(subprocess.check_output(['git', '-C', str(ROOT), 'show',
                                                           f'{BASE}:{TYPES.as_posix()}']))
                dictionary = out / 'Dictionary.hs'
                dictionary.write_bytes(subprocess.check_output(['git', '-C', str(ROOT), 'show',
                                                                f'{DICTIONARY_AST}:{TYPES.as_posix()}']))
                pre_spines = out / 'PreSpines.hs'
                pre_spines.write_bytes(subprocess.check_output(['git', '-C', str(ROOT), 'show',
                                                                f'{PRE_SPINES}:{TYPES.as_posix()}']))
                source = folder / 'FrozenCrateQuery.hs'
                orig = source.read_bytes()
                oracle = json.loads((folder / 'oracle.json').read_text())
                if folder == SPARSE:
                    oracle = oracle['sources']['CrateQuery']
                pin = oracle['frozen_sha256']
                self.assertEqual(hashlib.sha256(orig).hexdigest(), pin)
                old = prepare_frozen_query(source, out, expected_sha256=pin, types_source=named).read_bytes()
                new = prepare_frozen_query(source, out, expected_sha256=pin, types_source=ROOT / TYPES).read_bytes()
                previous = prepare_frozen_query(source, out, expected_sha256=pin, types_source=dictionary).read_bytes()
                prior = prepare_frozen_query(source, out, expected_sha256=pin, types_source=pre_spines).read_bytes()
                self.assertEqual(new, prior)
                self.assertEqual(new, previous)
                for branch in EXCLUSIONS:
                    self.assertNotIn(branch, old)
                    self.assertEqual(new.count(branch), 3)
                    new = new.replace(branch, b'')
                self.assertEqual(new, old)
                self.assertEqual(source.read_bytes(), orig)

    def test_reject_unknown_source_and_changed_oracle(self):
        source = DATA / 'FrozenCrateQuery.hs'
        pin = json.loads((DATA / 'oracle.json').read_text())['frozen_sha256']
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            bogus = out / 'bogus.hs'
            bogus.write_bytes((ROOT / TYPES).read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'Unsupported Bootstrap.Types'):
                prepare_frozen_query(source, out, expected_sha256=pin, types_source=bogus)
            with self.assertRaisesRegex(ValueError, 'differs from the pinned oracle'):
                prepare_frozen_query(bogus, out, expected_sha256=pin, types_source=ROOT / TYPES)
            self.assertFalse((out / 'FrozenCrateQuery.hs').exists())


if __name__ == '__main__':
    unittest.main()
