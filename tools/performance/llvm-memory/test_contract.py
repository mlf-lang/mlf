#!/usr/bin/env python3
"""Fail-closed historical UTF8 proof through the complete current source bridge."""
from pathlib import Path
import importlib.util
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OWNER = 'host/ghc/MLF/Host/Base.hs'
spec = importlib.util.spec_from_file_location('utf8_contract', HERE / 'source_contract.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


def live_contract(source_root=ROOT):
    # The current loader authenticates every live source file and all later
    # source edges. Do not instantiate the obsolete binary132 view directly.
    path = ROOT / 'tools/performance/artifact-binary/source_migration_adapter.py'
    module = types.ModuleType('utf8_live_source_loader')
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module.live_contract(ROOT / 'tools/performance', source_root=source_root)


class HostContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = live_contract()
        cls.current = (ROOT / OWNER).read_bytes()
        cls.compact = cls.binary.restore_path(cls.current, OWNER)

    def test_full_owner_inverse_matches_frozen_git_source(self):
        old = subprocess.check_output([
            'git', 'show',
            '9dfcd6625775819568eaaa5065f8dd1431df52f8:host/ghc/MLF/Host/Base.hs',
        ], cwd=ROOT)
        self.assertEqual(C.sha(self.compact), C.NEW_SHA)
        self.assertEqual(C.restore_before(self.compact), old)
        self.assertEqual(self.binary.advance_path(self.compact, OWNER), self.current)

    def test_mutation_outside_string_regions_is_rejected(self):
        # Establish a valid baseline so rejection cannot be a stale-source pass.
        self.assertEqual(C.sha(C.restore_before(
            self.binary.restore_path(self.current, OWNER))), C.OLD_SHA)
        for altered in [
            self.current + b'\n',
            self.current[:-1],
            self.current.replace(b'Fixed.Int64', b'Integer'),
            self.current.replace(b'bounded, stIndex, strict2', b'bounded, strict2'),
        ]:
            with self.subTest(altered_sha=C.sha(altered)):
                self.assertNotEqual(altered, self.current)
                with self.assertRaises(ValueError):
                    C.restore_before(self.binary.restore_path(altered, OWNER))

    def test_mutation_inside_current_string_region_is_rejected(self):
        self.assertEqual(self.binary.restore_path(self.current, OWNER), self.compact)
        altered = self.current.replace(
            b'Word.Word64) >= fromIntegral size',
            b'Word.Word64) > fromIntegral size')
        self.assertNotEqual(altered, self.current)
        with self.assertRaises(ValueError):
            self.binary.restore_path(altered, OWNER)

    def test_frozen_contract_still_rejects_unreviewed_full_owners(self):
        self.assertEqual(C.sha(C.restore_before(self.compact)), C.OLD_SHA)
        for altered in [
            self.current,
            self.compact + b'\n',
            self.compact[:-1],
            self.compact.replace(b'Fixed.Int64', b'Integer'),
        ]:
            self.assertNotEqual(altered, self.compact)
            with self.assertRaises(ValueError):
                C.restore_before(altered)

    def test_stale_nonbyte_and_wrong_role_live_inputs_are_rejected(self):
        self.assertEqual(self.binary.restore_path(self.current, OWNER), self.compact)
        for altered in [self.compact, C.restore_before(self.compact),
                        b'', self.current.decode(), bytearray(self.current), None]:
            with self.subTest(kind=type(altered).__name__), self.assertRaises(ValueError):
                self.binary.restore_path(altered, OWNER)
        for path in ['host/ghc/MLF/Host/IO.hs', '../Base.hs']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.binary.restore_path(self.current, path)
        for altered in [self.current, self.compact + b'\n',
                        C.restore_before(self.compact)]:
            with self.assertRaises(ValueError):
                self.binary.advance_path(altered, OWNER)

    def test_manifest_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            original = (HERE / 'host-delta.json').read_bytes()
            expected = C.manifest()
            (temp / 'host-delta.json').write_bytes(original)
            with patch.object(C, 'HERE', temp):
                self.assertEqual(C.manifest(), expected)
                self.assertEqual(C.sha(C.restore_before(self.compact)), C.OLD_SHA)
            for altered in [original + b'\n', original.replace(b'9dfcd662', b'00000000')]:
                self.assertNotEqual(altered, original)
                (temp / 'host-delta.json').write_bytes(altered)
                with patch.object(C, 'HERE', temp), self.assertRaises(ValueError):
                    C.manifest()

    def test_later_host_delta_corruption_is_rejected(self):
        # The complete physical source was admitted above. Relocate only the
        # subsequently read host proof to exercise its independent byte gate.
        # Reconciliation -> DeclId -> authenticated builtin-regeneration stage.
        # Corrupt the exact historical owner while exercising the complete live
        # forward/reverse bridge, rather than discarding the mutation oracle.
        historical = self.binary.previous.previous
        self.assertEqual(historical.manifest_sha256,
                         'fb8335e198e463d3a25b336f124d56dac141c6ad2063df531c09ade8e7411559')
        row = historical.frozen_value['deltas'][OWNER]
        original = (historical.directory / row['file']).read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            path = temp / row['file']
            path.parent.mkdir(parents=True)
            path.write_bytes(original)
            with patch.object(historical._frozen, 'directory', temp):
                self.assertEqual(self.binary.restore_path(self.current, OWNER), self.compact)
                self.assertEqual(self.binary.advance_path(self.compact, OWNER), self.current)
                for altered in [original + b'\n', original.replace(OWNER.encode(), b'other.hs')]:
                    self.assertNotEqual(altered, original)
                    path.write_bytes(altered)
                    with self.assertRaises(ValueError):
                        self.binary.restore_path(self.current, OWNER)
                    with self.assertRaises(ValueError):
                        self.binary.advance_path(self.compact, OWNER)

    def test_full_current_source_admission_rejects_nonhost_stale_and_missing_inputs(self):
        # A current host alone must never authenticate an obsolete or mixed tree.
        sources = {path: (ROOT / path).read_bytes()
                   for path in self.binary.value['current_files']}
        self.assertEqual(len(sources), 198)
        self.assertIn('libraries/mlf-foundation/Bootstrap/IndexVec.hs', sources)
        self.assertIn('libraries/mlf-frontend/Bootstrap/Resolved.hs', sources)
        self.assertLessEqual(sum(map(len, sources.values())), 16 * 1024**2)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, raw in sources.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            admitted = live_contract(root)
            self.assertEqual(admitted.live_source_inventory(root),
                             self.binary.value['current_files'])
            self.assertEqual(admitted.restore_path((root / OWNER).read_bytes(), OWNER),
                             self.compact)
            literal = 'bootstrap/MLF/BuiltinPreludeData.hs'
            stale_literal = self.binary.restore_path(sources[literal], literal)
            self.assertNotEqual(stale_literal, sources[literal])
            for name, altered in [
                ('cabal.project', sources['cabal.project'] + b'\n'),
                (literal, stale_literal),
                (OWNER, self.compact),
            ]:
                path = root / name
                path.write_bytes(altered)
                try:
                    with self.subTest(path=name), self.assertRaises(ValueError):
                        live_contract(root)
                finally:
                    path.write_bytes(sources[name])
            missing = root / 'cabal.project'
            missing.unlink()
            try:
                with self.assertRaises(FileNotFoundError):
                    live_contract(root)
            finally:
                missing.write_bytes(sources['cabal.project'])
            self.assertEqual(live_contract(root).live_source_inventory(root),
                             self.binary.value['current_files'])

    def test_forward_transition_is_the_exact_complete_owner(self):
        delta = C.manifest()
        old = subprocess.check_output(
            ['git', 'show', delta['parent_ref'] + ':' + delta['path']], cwd=ROOT)
        for edit in delta['edits']:
            before, after = edit['old'].encode(), edit['new'].encode()
            self.assertEqual(old.count(before), 1)
            old = old.replace(before, after)
        self.assertEqual(C.sha(old), C.NEW_SHA)
        self.assertEqual(old, self.compact)
        self.assertEqual(self.binary.advance_path(old, delta['path']),
                         (ROOT / delta['path']).read_bytes())


if __name__ == '__main__':
    unittest.main()
