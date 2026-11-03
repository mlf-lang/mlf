#!/usr/bin/env python3
"""Independent, fail-closed checks for the private host representation delta."""
from pathlib import Path
import importlib.util
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('utf8_contract', HERE / 'source_contract.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


class HostContract(unittest.TestCase):
    def test_full_owner_inverse_matches_frozen_git_source(self):
        current = (ROOT / 'host/ghc/MLF/Host/Base.hs').read_bytes()
        old = subprocess.check_output([
            'git', 'show',
            '9dfcd6625775819568eaaa5065f8dd1431df52f8:host/ghc/MLF/Host/Base.hs',
        ], cwd=ROOT)
        self.assertEqual(C.restore_before(current), old)

    def test_mutation_outside_string_regions_is_rejected(self):
        current = (ROOT / 'host/ghc/MLF/Host/Base.hs').read_bytes()
        for altered in [current + b'\n', current[:-1], current.replace(b'Fixed.Int64', b'Integer')]:
            self.assertNotEqual(altered, current)
            with self.assertRaises(ValueError):
                C.restore_before(altered)

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
        self.assertEqual(old, (ROOT / delta['path']).read_bytes())


if __name__ == '__main__':
    unittest.main()
