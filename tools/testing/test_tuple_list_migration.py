#!/usr/bin/env python3
"""Fail-closed shared migration controls; no compiler/build or expected-output generation."""
import tempfile
import unittest
from pathlib import Path
import check_tuple_list_migration as audit


class SharedTupleMigrationControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Never mock the production semantic-contract pins for candidate sources.
        cls.sources = audit.verify_current_sources()

    def test_exact_reviewed_sources(self):
        self.assertEqual(len(self.sources), 2)

    def test_default_or_dispatcher_change_rejected(self):
        # This boundary authenticates bytes; one change per pinned file covers it.
        for path in (audit.SOURCE, audit.IMPLEMENTATION):
            with self.subTest(path=path), self.assertRaisesRegex(
                    ValueError, 'differs from reviewed active semantic contract'):
                audit.verify_shared(path, self.sources[path] + '\n-- unreviewed change\n')

    def test_unknown_path_rejected(self):
        with self.assertRaisesRegex(ValueError, 'requires review'):
            audit.verify_shared('tests/Unreviewed.hs', '')

    def test_duplicate_legacy_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, source in self.sources.items():
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(source)
            (root / audit.LEGACY).write_text('-- stale duplicate')
            with self.assertRaisesRegex(ValueError, 'duplicate live'):
                audit.verify_current_sources(root)


if __name__ == '__main__':
    unittest.main()
