#!/usr/bin/env python3
"""Historical provenance controls, separate from executable registry behavior."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import check_tuple_list_migration as audit


class SharedTupleMigrationControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = audit.verify_cutover_sources()

    def test_reviewed_cutover_sources_remain_authenticated(self):
        self.assertEqual(set(self.sources), {audit.SOURCE, audit.IMPLEMENTATION})
        self.assertEqual(audit.active_contract()["source_commit"], audit.FRAMEWORK_CUTOVER)

    def test_corrupted_historical_source_is_rejected(self):
        for path, source in self.sources.items():
            with self.subTest(path=path), self.assertRaisesRegex(
                    ValueError, "historical source differs from reviewed cutover"):
                audit.verify_cutover_source(path, source + "\n-- changed archive\n")

    def test_unknown_historical_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unreviewed historical tuple source"):
            audit.verify_cutover_source("tests/Unreviewed.hs", "")

    def test_current_refactoring_does_not_rewrite_migration_history(self):
        # A real local checkout shares immutable Git objects, but its maintained
        # modules have a renamed private helper and an unrelated old-path file.
        # Neither is historical evidence. Executable discovery/receipts enforce
        # the current registry separately in test_framework_direct.py.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "checkout"
            subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout",
                            str(audit.ROOT), str(root)], check=True)
            contract = root / audit.ACTIVE_CONTRACT_PATH
            contract.parent.mkdir(parents=True)
            contract.write_text((audit.ROOT / audit.ACTIVE_CONTRACT_PATH).read_text())
            for path, source in self.sources.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("-- harmless comment\n" + source.replace("leaf", "testLeaf"))
            (root / audit.LEGACY).write_text("-- unregistered documentation fixture\n")
            with patch.object(audit, "ROOT", root):
                self.assertEqual(audit.verify_cutover_sources(), self.sources)

    def test_missing_duplicate_or_recounted_contract_ids_are_rejected(self):
        original = audit.active_contract()
        for mutation in ("missing", "duplicate", "recounted"):
            contract = json.loads(json.dumps(original))
            if mutation == "duplicate":
                contract["framework_ids"][-1] = contract["framework_ids"][0]
            else:
                contract["framework_ids"].pop()
                if mutation == "recounted":
                    contract["framework_count"] -= 1
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = root / audit.ACTIVE_CONTRACT_PATH
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(contract))
                with patch.object(audit, "ROOT", root), self.assertRaisesRegex(
                        ValueError, "reviewed active tuple inventory changed"):
                    audit.active_contract()


if __name__ == '__main__':
    unittest.main()
