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

    def test_shared_builtin_import(self):
        self.value['executables']['probe']['main'] = 'Main.hs'
        (self.root / 'Main.hs').write_text('-- mlf:syntax shared-haskell-v1\nmodule Main where\nimport MLF.Primitive\nmain = 1\n')
        self.save()

    def test_hs_filename_requires_explicit_syntax_marker(self):
        self.value['executables']['probe']['main'] = 'Main.hs'
        (self.root / 'Main.hs').write_text('module Main where\nimport MLF.Primitive\nmain = 1\n')
        with self.assertRaisesRegex(ValueError, 'explicit profile marker'):
            self.save()

    def test_legacy_explicit_standard_class_import(self):
        (self.root / 'Main.emlf').write_text('module Main where\nimport Prelude hiding (Monad, return, bind)\nimport MLF.Primitive (Monad, return, bind)\nmain = 1\n')
        self.save()

    def test_legacy_cannot_supply_reserved_builtins(self):
        for module in ['Prelude', 'MLF.Primitive']:
            with self.subTest(module=module):
                (self.root / 'Main.emlf').write_text('module '+module+' where\nmain = 1\n')
                with self.assertRaisesRegex(ValueError, 'reserved builtin'):
                    self.save()

    def test_legacy_builtin_import_does_not_authorize_other_modules(self):
        (self.root / 'Main.emlf').write_text('module Main where\nimport MLF.Primitive\nimport MLF.Missing\nmain = 1\n')
        with self.assertRaisesRegex(ValueError, 'undeclared direct imports'):
            self.save()

    def test_shared_cannot_supply_reserved_builtin(self):
        self.value['executables']['probe']['main'] = 'Main.hs'
        (self.root / 'Main.hs').write_text('-- mlf:syntax shared-haskell-v1\nmodule MLF.Primitive where\nmain = 1\n')
        with self.assertRaisesRegex(ValueError, 'reserved builtin'):
            self.save()

    def test_shared_does_not_authorize_arbitrary_import(self):
        self.value['executables']['probe']['main'] = 'Main.hs'
        (self.root / 'Main.hs').write_text('-- mlf:syntax shared-haskell-v1\nmodule Main where\nimport Missing\nmain = 1\n')
        with self.assertRaisesRegex(ValueError, 'undeclared direct imports'):
            self.save()

    def test_indented_and_inline_imports_are_not_invisible(self):
        self.value['executables']['probe']['main'] = 'Main.hs'
        for body in ['module Main where {\n  import Missing;\n  main = 1\n}',
                     'module Main where {\n  import qualified Missing as M;\n  main = 1\n}',
                     'module Main where { import Missing; main = 1 }']:
            with self.subTest(body=body):
                (self.root / 'Main.hs').write_text('-- mlf:syntax shared-haskell-v1\n'+body+'\n')
                with self.assertRaisesRegex(ValueError, 'undeclared direct imports'):
                    self.save()

    def test_comments_and_literals_do_not_invent_imports(self):
        self.value['executables']['probe']['main'] = 'Main.hs'
        (self.root / 'Main.hs').write_text('-- mlf:syntax shared-haskell-v1\nmodule Main where {\n'
            ' {- import Missing; {- import AlsoMissing; -} -}\n'
            ' import qualified MLF.Primitive as P; -- import Missing\n'
            ' text = "import Missing; \\"quoted\\""; main = 1\n}\n')
        self.save()

    def test_primed_identifier_is_not_import_keyword(self):
        (self.root / 'Main.emlf').write_text("module Main where\nimport' = 1\nmain = import'\n")
        self.save()

    def test_unterminated_lexical_regions_fail_closed(self):
        for fragment in ['{- unfinished', 'text = "unfinished']:
            with self.subTest(fragment=fragment):
                (self.root / 'Main.emlf').write_text('module Main where\n'+fragment)
                with self.assertRaisesRegex(ValueError, 'unterminated source'):
                    self.save()

    def test_malformed_import_heads_fail_closed(self):
        self.value['executables']['probe']['main'] = 'Main.hs'
        for declaration in ['import qualified;', 'import lower;', 'import Missing..Bad;', 'import "package" MLF.Primitive;']:
            with self.subTest(declaration=declaration):
                (self.root / 'Main.hs').write_text('-- mlf:syntax shared-haskell-v1\nmodule Main where { '+declaration+' main = 1 }\n')
                with self.assertRaisesRegex(ValueError, 'malformed source import'):
                    self.save()

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
