#!/usr/bin/env python3
"""Focused fault controls for the static local manifest auditor only."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from check_manifest_snapshot import snapshot, strict_object


class SnapshotControls(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.manifest = self.root / 'mlf-package.json'
        (self.root / 'Main.emlf').write_text('module Main where\nimport Prelude\nmain = 1\n')
        self.value = {'format': 1, 'name': 'probe', 'version': '0.1.0',
                      'executables': {'probe': {'main': 'Main.emlf'}}}

    def save(self, value=None):
        self.manifest.write_text(json.dumps(value if value is not None else self.value))
        return snapshot(self.manifest)

    def test_plain_snapshot_and_source_change(self):
        first = self.save()
        (self.root / 'Main.emlf').write_text('module Main where\nmain = 2\n')
        self.assertNotEqual(first, self.save())

    def test_missing_source(self):
        self.value['executables']['probe']['main'] = 'Missing.emlf'
        with self.assertRaisesRegex(ValueError, 'missing source'):
            self.save()

    def test_path_escape(self):
        self.value['executables']['probe']['main'] = '../Escape.emlf'
        with self.assertRaisesRegex(ValueError, 'escaping'):
            self.save()

    def test_absolute_path(self):
        self.value['executables']['probe']['main'] = str(self.root / 'Main.emlf')
        with self.assertRaisesRegex(ValueError, 'relative'):
            self.save()

    def test_undeclared_import(self):
        (self.root / 'Main.emlf').write_text('module Main where\nimport Missing\nmain = 1\n')
        with self.assertRaisesRegex(ValueError, 'undeclared direct imports'):
            self.save()

    def test_dependency_cycle(self):
        self.value['dependencies'] = {'probe': {'path': '.'}}
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.save()

    def test_remote_not_invented(self):
        self.value['dependencies'] = {'remote': {'github': 'owner/repo'}}
        with self.assertRaisesRegex(ValueError, 'unsupported non-local'):
            self.save()

    def test_duplicate_json_keys(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            json.loads('{"name":"a","name":"b"}', object_pairs_hook=strict_object)

    def test_unknown_target_dependency(self):
        self.value['executables']['probe']['dependencies'] = ['missing']
        with self.assertRaisesRegex(ValueError, 'unknown direct target dependency'):
            self.save()

    def test_private_module_header_mismatch(self):
        self.value['executables']['probe']['modules'] = {'Wrong': 'Main.emlf'}
        with self.assertRaisesRegex(ValueError, 'module declaration mismatch'):
            self.save()


if __name__ == '__main__':
    unittest.main()
