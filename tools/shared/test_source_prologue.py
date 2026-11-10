#!/usr/bin/env python3
"""Focused inventory-marker tests; not a replacement for the compiler lexer."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILD = load('formatter_build_marker_tests', 'tools/shared/build.py')
SNAPSHOT = load('formatter_snapshot_marker_tests', 'tools/testing/check_manifest_snapshot.py')
MARKER = '-- mlf:syntax shared-haskell-v1\n'
BODY = 'module Example where\nmain = 1\n'


class SourcePrologueTests(unittest.TestCase):
    def test_scanners_agree_with_independent_expected_markers(self):
        cases = [
            (MARKER + BODY, ['shared-haskell-v1']),
            ('{-# LANGUAGE RankNTypes #-}\n' + MARKER + BODY, ['shared-haskell-v1']),
            ('{- outer {- nested -} comment -}\n' + MARKER + BODY, ['shared-haskell-v1']),
            ('{-\n' + MARKER + '-}\n' + BODY, []),
            ('{- outer {-\n' + MARKER + '-} outer -}\n' + BODY, []),
            ('{-# LANGUAGE\n' + MARKER + '#-}\n' + BODY, []),
            (MARKER + '{-\n' + MARKER + '-}\n' + BODY, ['shared-haskell-v1']),
            (MARKER + MARKER + BODY, ['shared-haskell-v1', 'shared-haskell-v1']),
            ('-- mlf:syntax future-v2\n' + MARKER + BODY, ['future-v2', 'shared-haskell-v1']),
            ('-- mlf:syntax\n' + MARKER + BODY, ['', 'shared-haskell-v1']),
            ('-- mlf:syntax shared-haskell-v1 extra\n' + BODY, ['shared-haskell-v1 extra']),
            (BODY + MARKER, []),
            ('x = 1\n' + MARKER + BODY, []),
            ('x = "' + MARKER.rstrip() + '"\n' + BODY, []),
            (MARKER + '{- unterminated', []),
            ('{- outer {- inner -}\n' + MARKER, []),
            ('-- ordinary comment\n\t' + MARKER.replace('\n', '\r\n') + BODY,
             ['shared-haskell-v1']),
            ('-- mlf:syntax shared-haskell-v1', ['shared-haskell-v1']),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(BUILD.source_prologue_markers(source), expected)
                self.assertEqual(SNAPSHOT.source_prologue_markers(source), expected)
                if expected != ['shared-haskell-v1']:
                    with self.assertRaisesRegex(ValueError, 'explicit profile marker'):
                        SNAPSHOT.source_builtins('Example.hs', source)
                else:
                    self.assertIn('MLF.Primitive', SNAPSHOT.source_builtins('Example.hs', source))

    def test_build_inventory_rejects_comment_only_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'shared-sources.json').write_text(json.dumps({
                'format': 1, 'source_syntax': 'shared-haskell-v1',
                'modules': [{'module': 'Example', 'path': 'Example.hs'}],
            }))
            (root / 'Example.hs').write_text('{-\n' + MARKER + '-}\n' + BODY)
            with patch.object(BUILD, 'ROOT', root):
                with self.assertRaisesRegex(RuntimeError, 'missing or ambiguous shared source marker'):
                    BUILD.load_manifest()


if __name__ == '__main__':
    unittest.main()
