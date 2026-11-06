#!/usr/bin/env python3
"""Controls for compiler-owned literal pooling and its restricted lexical scope."""
from pathlib import Path
import runpy
import unittest

P = runpy.run_path(str(Path(__file__).with_name('pool_generated_strings.py')))

def source(body):
    return P['PROFILE'] + P['MODULE'] + '\n' + body + '\n}\n'

class PoolTests(unittest.TestCase):
    def test_literal_values_and_comments(self):
        body = '''-- "same" "same"
{- outer "same" {- inner "same" -} -}
libraries = ["same", "same", "unique", "a\\\"b", "a\\\"b"];
parseLibrary = ('"', '\\'', "雪", "雪");'''
        raw = source(body)
        result, proof = P['pool'](raw)
        expected = source(body.replace('["same", "same", "unique", "a\\\"b", "a\\\"b"]',
                                       '[mlfPreparedString0, mlfPreparedString0, "unique", mlfPreparedString1, mlfPreparedString1]')
                          .replace('"雪", "雪"', 'mlfPreparedString2, mlfPreparedString2'))
        definitions = '\n-- Shared immutable generated String literals.\n' + (
            'mlfPreparedString0 :: String; mlfPreparedString0 = "same";\n'
            'mlfPreparedString1 :: String; mlfPreparedString1 = "a\\\"b";\n'
            'mlfPreparedString2 :: String; mlfPreparedString2 = "雪";\n')
        self.assertEqual(result, expected[:-2] + definitions + '}\n')
        self.assertEqual((proof['bindings'], proof['references']), (3, 6))
        self.assertEqual(P['pool'](result)[0], result)

    def test_existing_names_are_not_captured(self):
        raw = source('mlfPreparedString0 = 7; foo\' = 8; libraries = ["x", "x"];')
        result, _ = P['pool'](raw)
        self.assertIn('mlfPreparedString0 = 7; foo\' = 8;', result)
        self.assertIn('libraries = [mlfPreparedStringX0, mlfPreparedStringX0]', result)

    def test_single_literals_and_raw_crlf_preserved(self):
        raw = source('libraries = ["x"];\r\nparseLibrary = "y";')
        self.assertEqual(P['pool'](raw)[0], raw)

    def test_wrong_profile_and_unclosed_comment(self):
        for raw in ['module Main where { main = "x" }', source('{-'), source('"x"') + 'trailing']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                P['pool'](raw)

    def test_closed_constructor_leaves_keep_types_and_shared_syntax(self):
        raw = source('libraries = [(XTyVar 1),(XTyVar 1),(Parameter "a"),(Parameter "a"),'
                     '(SVar "a"),(SVar "a"),(SIntLit (-1)),(SIntLit (-1))];')
        result, proof = P['pool'](raw)
        self.assertEqual(proof['constructor_pool']['bindings'], 4)
        self.assertEqual(proof['constructor_pool']['references'], 8)
        for index, ty in enumerate(['XTyVar', 'Field', 'SExpr', 'SExpr']):
            self.assertIn(f'mlfPreparedLeaf{index} :: {ty};', result)
        self.assertNotIn('NOINLINE', result)
        self.assertEqual(P['pool'](result)[0], result)

    def test_functions_variables_and_polymorphic_constructors_are_not_pooled(self):
        body = 'libraries = [(XTyVar next),(XTyVar next),(Just 1),(Just 1),(compute 2),(compute 2)];'
        raw = source(body)
        self.assertEqual(P['pool'](raw)[0], raw)

    def test_leaf_names_do_not_capture_and_comments_are_opaque(self):
        body = 'mlfPreparedLeaf0 = 7; libraries = [(XTyVar 2),(XTyVar 2)];\n' \
               '-- (XTyVar 2)\ntext = "(XTyVar 2)"; ch = \')\';'
        result, proof = P['pool'](source(body))
        self.assertEqual(proof['constructor_pool']['references'], 2)
        self.assertIn('libraries = [mlfPreparedLeafX0,mlfPreparedLeafX0]', result)
        self.assertIn('-- (XTyVar 2)\ntext = "(XTyVar 2)"; ch = \')\';', result)

    def test_unbalanced_constructor_input_is_rejected(self):
        for body in ['libraries = [(XTyVar 1];', 'libraries = [XTyVar 1)];']:
            with self.assertRaisesRegex(ValueError, 'unbalanced generated'):
                P['pool'](source(body))

if __name__ == '__main__':
    unittest.main()
