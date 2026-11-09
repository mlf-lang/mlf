#!/usr/bin/env python3
"""Cheap fail-closed tests for P1's frozen, import-only dependency layer."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SPEC = importlib.util.spec_from_file_location('p1_selector_runner', HERE / 'run_selector_differential.py')
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def digest(contents):
    return hashlib.sha256(contents).hexdigest()


class OracleAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.here = Path(self.temp.name) / 'oracle'
        self.here.mkdir()
        for name in ['oracle-manifest.json', 'FrozenSelectors.hs', 'original-selector-excerpts.txt',
                     'FrozenSelectorMap.hs', 'FrozenSelectorSet.hs']:
            shutil.copy2(HERE / name, self.here / name)
        self.manifest = json.loads((self.here / 'oracle-manifest.json').read_text())
        pins = {**self.manifest['shared_dependency_pins'],
                **self.manifest['collection_dependency_reaudit']['candidate_dependency_pins']}
        for path in pins:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, target)

    def save_manifest(self):
        (self.here / 'oracle-manifest.json').write_text(json.dumps(self.manifest))

    def authenticate(self):
        return RUNNER.authenticate_oracle(self.root, self.here)

    def test_literal_selector_and_historical_hashes_preserved(self):
        manifest, adapted = self.authenticate()
        original = (self.here / 'FrozenSelectors.hs').read_bytes()
        self.assertEqual(digest(original), '62c44c42657f507c35d46fc08b5fc39f99ac23d34cb9cb2cf645fabfc83767d4')
        self.assertEqual(manifest['excerpt_sha256'], 'd77ad09a09f358926c43b637c5a9ab04052c6da2d16e90a7fe81cd27d156003a')
        self.assertEqual(adapted.replace(b'FrozenSelectorMap as M', b'Bootstrap.Map as M')
                         .replace(b'FrozenSelectorSet as Set', b'Bootstrap.Set as Set'), original)
        self.assertNotIn(b'import qualified Bootstrap.Map', adapted)
        self.assertNotIn(b'import qualified Bootstrap.Set', adapted)
        modules = manifest['collection_dependency_reaudit']['frozen_modules']
        self.assertEqual({item['baseline_source']: item['baseline_sha256'] for item in modules}, {
            'libraries/mlf-foundation/Bootstrap/Map.hs': 'd4d9ebfa39a14ae1cbaf48fa9d540eafa7b452aaa3cc73ffc624a34c15417bdb',
            'libraries/mlf-foundation/Bootstrap/Set.hs': 'c2222cc52e2ee750a92d563f8f513ecf4eb60b1afd534b91a37b7c5d5ba6e60f',
        })
        for item in modules:
            contents = (self.here / item['file']).read_bytes()
            self.assertIn(b'import Bootstrap.Types;', contents)
            self.assertNotIn(b'import qualified Bootstrap.Map', contents)
            self.assertNotIn(b'import qualified Bootstrap.Set', contents)

    def test_changed_selector_rejected(self):
        path = self.here / 'FrozenSelectors.hs'
        path.write_bytes(path.read_bytes() + b'\n-- mutation\n')
        with self.assertRaisesRegex(ValueError, 'frozen oracle changed'):
            self.authenticate()

    def test_changed_excerpts_rejected(self):
        path = self.here / 'original-selector-excerpts.txt'
        path.write_bytes(path.read_bytes() + b'\nmutation\n')
        with self.assertRaisesRegex(ValueError, 'frozen original excerpts changed'):
            self.authenticate()

    def test_changed_shared_dependency_rejected(self):
        path = self.root / 'libraries/mlf-foundation/Bootstrap/Types.hs'
        path.write_bytes(path.read_bytes() + b'\n-- mutation\n')
        with self.assertRaisesRegex(ValueError, 'oracle dependency changed; independent re-audit required'):
            self.authenticate()

    def test_changed_candidate_collections_rejected(self):
        for path in self.manifest['collection_dependency_reaudit']['candidate_dependency_pins']:
            with self.subTest(path=path):
                target = self.root / path
                original = target.read_bytes()
                target.write_bytes(original + b'\n-- mutation\n')
                with self.assertRaisesRegex(ValueError, 'reviewed collection dependency changed'):
                    self.authenticate()
                target.write_bytes(original)

    def test_changed_frozen_collections_rejected(self):
        for item in self.manifest['collection_dependency_reaudit']['frozen_modules']:
            with self.subTest(file=item['file']):
                path = self.here / item['file']
                original = path.read_bytes()
                path.write_bytes(original + b'\n-- mutation\n')
                with self.assertRaisesRegex(ValueError, 'frozen collection oracle changed'):
                    self.authenticate()
                path.write_bytes(original)

    def test_repinning_changed_frozen_body_cannot_bypass_historical_pin(self):
        for item in self.manifest['collection_dependency_reaudit']['frozen_modules']:
            with self.subTest(file=item['file']):
                path = self.here / item['file']
                original = path.read_bytes()
                original_digest = item['oracle_sha256']
                path.write_bytes(original + b'\n-- mutation\n')
                item['oracle_sha256'] = digest(path.read_bytes())
                self.save_manifest()
                with self.assertRaisesRegex(ValueError, 'frozen collection body differs from historical baseline'):
                    self.authenticate()
                path.write_bytes(original)
                item['oracle_sha256'] = original_digest
                self.save_manifest()

    def test_repinning_selector_cannot_bypass_adapted_pin(self):
        path = self.here / 'FrozenSelectors.hs'
        path.write_bytes(path.read_bytes() + b'\n-- mutation\n')
        self.manifest['oracle_sha256'] = digest(path.read_bytes())
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'import-only selector adaptation changed'):
            self.authenticate()

    def test_duplicate_selector_import_fails_closed(self):
        path = self.here / 'FrozenSelectors.hs'
        path.write_bytes(path.read_bytes() + b'\nimport qualified Bootstrap.Map as M;\n')
        self.manifest['oracle_sha256'] = digest(path.read_bytes())
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'adaptation must replace exactly one occurrence'):
            self.authenticate()

    def test_candidate_set_import_cannot_be_restored_by_repinning(self):
        path = self.here / 'FrozenSelectorSet.hs'
        path.write_bytes(path.read_bytes().replace(b'FrozenSelectorMap as M', b'Bootstrap.Map as M'))
        item = next(item for item in self.manifest['collection_dependency_reaudit']['frozen_modules']
                    if item['file'] == path.name)
        item['oracle_sha256'] = digest(path.read_bytes())
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'adaptation must replace exactly one occurrence'):
            self.authenticate()

    def test_frozen_module_inventory_cannot_be_reduced(self):
        self.manifest['collection_dependency_reaudit']['frozen_modules'].pop()
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'frozen collection module inventory changed'):
            self.authenticate()


if __name__ == '__main__':
    unittest.main()
