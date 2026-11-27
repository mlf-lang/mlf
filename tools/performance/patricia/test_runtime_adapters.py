"""Exercise direct runtime inputs without historical source admission."""
from pathlib import Path
import hashlib
import shutil
import tempfile
import unittest

import adapt_oracles as graph
import frozen_oracles
import legacy_controls as legacy

ROOT = Path(__file__).resolve().parents[3]
OWNER = Path(graph.OWNER)


class RuntimeAdapters(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'source'
        self.root.mkdir()

    def copy(self, relative):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
        return target

    def copy_sources(self, sources):
        for relative in sources.values():
            self.copy(relative)

    def test_graph_preparation_keeps_current_source_without_git_history(self):
        self.copy_sources(graph.GRAPH_SOURCES)
        owner = self.copy(OWNER)
        body = b' {\n  currentImplementation = 17;\n}\n'
        current = b'module Bootstrap.CrateSession\n (newExport, compileSpecFile) where' + body
        owner.write_bytes(current)
        control = self.root / graph.GRAPH_SOURCES['SessionTests.hs']
        maintained = control.read_bytes() + b'\n-- ordinary maintained control edit\n'
        control.write_bytes(maintained)
        out = self.root.parent / 'graph'
        inputs = graph.prepare(self.root, out)
        self.assertEqual((out / 'SessionUnderTest.hs').read_bytes(),
                         b'module SessionUnderTest where' + body)
        self.assertEqual((out / 'SessionTests.hs').read_bytes(), maintained)
        self.assertEqual(inputs[str(owner)], hashlib.sha256(current).hexdigest())
        self.assertEqual(inputs[str(control)], hashlib.sha256(maintained).hexdigest())
        self.assertEqual(owner.read_bytes(), current)
        self.assertEqual({path.name for path in out.iterdir()},
                         set(graph.GRAPH_SOURCES) | {'SessionUnderTest.hs'})
        self.assertFalse((self.root / '.git').exists())

    def test_validation_pairs_fixed_oracle_with_current_session(self):
        self.copy_sources(graph.VALIDATION_SOURCES)
        source = self.root.parent / 'producer-source'
        owner = source / OWNER
        owner.parent.mkdir(parents=True)
        current = b'module Bootstrap.CrateSession where\ncurrent = 23\n'
        owner.write_bytes(current)
        out = self.root.parent / 'validation'
        out.mkdir()
        inputs = graph.prepare_validation(self.root, out, source_root=source)
        self.assertEqual((out / 'V1FrozenSession.hs').read_bytes(),
                         (self.root / graph.VALIDATION_SOURCES['V1FrozenSession.hs']).read_bytes())
        self.assertEqual((out / 'V1SessionUnderTest.hs').read_bytes(),
                         b'module V1SessionUnderTest where\ncurrent = 23\n')
        self.assertEqual(inputs[str(owner)], hashlib.sha256(current).hexdigest())
        self.assertFalse((self.root / 'tools/performance/artifact-binary').exists())

    def test_changed_frozen_validation_oracle_is_rejected(self):
        self.copy(OWNER)
        self.copy_sources(graph.VALIDATION_SOURCES)
        oracle = self.root / graph.VALIDATION_SOURCES['V1FrozenSession.hs']
        oracle.write_bytes(oracle.read_bytes() + b'\n')
        out = self.root.parent / 'validation'
        out.mkdir()
        with self.assertRaisesRegex(ValueError, 'frozen runtime oracle changed'):
            graph.prepare_validation(self.root, out)
        self.assertFalse((out / 'V1SessionUnderTest.hs').exists())

    def test_p123_prepares_independent_fingerprint_and_current_binary_controls(self):
        self.copy_sources(legacy.SOURCES['p123'])
        out = self.root.parent / 'p123'
        control = self.root / legacy.SOURCES['p123']['P1Controls.hs']
        control.write_bytes(control.read_bytes() + b'\n-- maintained assertion documentation\n')
        modules, inputs = legacy.prepare(self.root, out, 'p123')
        self.assertEqual(modules, ['P1Controls', 'P2Controls', 'NativeCompatibilityControls', 'P3Controls'])
        for name in ('FingerprintReference.hs', 'BinaryP2WriterControls.hs', 'P1Controls.hs'):
            source = self.root / legacy.SOURCES['p123'][name]
            self.assertEqual((out / name).read_bytes(), source.read_bytes())
            self.assertEqual(inputs[str(source)], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertFalse((out / 'adaptations.json').exists())
        self.assertFalse((self.root / 'tools/performance/artifact-binary/source_migration_adapter.py').exists())
        self.assertFalse((self.root / 'libraries/mlf-crates/Bootstrap/CrateArtifact.hs').exists())

if __name__ == '__main__':
    unittest.main()
