"""Reject stale/malformed source admission without weakening frozen oracles."""
import copy
import unittest
from pathlib import Path
import source_contract as C

ROOT = Path(__file__).resolve().parents[3]


class SourceContractTests(unittest.TestCase):
    def test_complete_source_inverse(self):
        source = (ROOT / C.OWNER).read_bytes()
        restored = C.restore_previous_owner(source)
        self.assertEqual(C.sha(restored), C.OLD_OWNER_SHA)
        rebuilt = restored
        for edit in C.manifest()['edits']:
            self.assertEqual(rebuilt.count(edit['old'].encode()), 1)
            rebuilt = rebuilt.replace(edit['old'].encode(), edit['new'].encode())
        self.assertEqual(rebuilt, source)

    def test_manifest_mutation_is_not_new_expectation(self):
        raw = C.MANIFEST.read_bytes()
        for changed in [raw + b' ', b'{}', raw.replace(C.OLD_OWNER_SHA.encode(), b'0' * 64)]:
            with self.subTest(size=len(changed)), self.assertRaises(ValueError):
                C.manifest(changed)

    def test_old_or_partly_changed_owner_rejected(self):
        source = (ROOT / C.OWNER).read_bytes()
        old = C.restore_previous_owner(source)
        edit = C.manifest()['edits'][0]
        for changed in [old, source + b' ', source.replace(edit['new'].encode(), edit['old'].encode())]:
            with self.subTest(size=len(changed)), self.assertRaises(ValueError):
                C.restore_previous_owner(changed)

    def test_dependency_extension_preserves_other_fields(self):
        before = {C.OWNER: C.OLD_OWNER_SHA, C.CONSTRAINT: C.CONSTRAINT_SHA, 'untouched': 'kept'}
        self.assertEqual(C.candidate_dependencies(before, ROOT), {**before, C.OWNER: C.NEW_OWNER_SHA})
        for key in [C.OWNER, C.CONSTRAINT]:
            changed = copy.deepcopy(before); changed[key] = '0' * 64
            with self.subTest(key=key), self.assertRaises(ValueError):
                C.candidate_dependencies(changed, ROOT)


if __name__ == '__main__':
    unittest.main()
