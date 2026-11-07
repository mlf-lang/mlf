#!/usr/bin/env python3
"""Independent, fail-closed checks for the private host representation delta."""
from pathlib import Path
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / 'patricia'))
from source_migration import binary_contract

OWNER = 'host/ghc/MLF/Host/Base.hs'
spec = importlib.util.spec_from_file_location('utf8_contract', HERE / 'source_contract.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


class HostContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = (ROOT / OWNER).read_bytes()
        cls.transition = binary_contract(source_root=ROOT)
        cls.utf8_owner = cls.transition.restore_path(cls.current, OWNER)

    def test_full_owner_inverse_matches_frozen_git_source(self):
        old = subprocess.check_output([
            'git', 'show',
            '9dfcd6625775819568eaaa5065f8dd1431df52f8:host/ghc/MLF/Host/Base.hs',
        ], cwd=ROOT)
        self.assertEqual(C.restore_before(self.utf8_owner), old)

    def test_mutation_outside_string_regions_is_rejected(self):
        for raw, restore in [(self.utf8_owner, C.restore_before),
                             (self.current, lambda data: self.transition.restore_path(data, OWNER))]:
            for altered in [raw + b'\n', raw[:-1], raw.replace(b'Fixed.Int64', b'Integer')]:
                self.assertNotEqual(altered, raw)
                with self.assertRaises(ValueError):
                    restore(altered)

    def test_manifest_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            original = (HERE / 'host-delta.json').read_bytes()
            for altered in [original + b'\n', original.replace(b'9dfcd662', b'00000000')]:
                (temp / 'host-delta.json').write_bytes(altered)
                with patch.object(C, 'HERE', temp), self.assertRaises(ValueError):
                    C.manifest()

    def test_forward_transition_is_the_exact_complete_owner(self):
        delta = C.manifest()
        old = subprocess.check_output(['git', 'show', delta['parent_ref'] + ':' + delta['path']], cwd=ROOT)
        for edit in delta['edits']:
            before, after = edit['old'].encode(), edit['new'].encode()
            self.assertEqual(old.count(before), 1)
            old = old.replace(before, after)
        self.assertEqual(old, self.utf8_owner)


if __name__ == '__main__':
    unittest.main()
