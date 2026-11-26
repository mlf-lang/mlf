#!/usr/bin/env python3
"""Private module views preserve current bodies without freezing public exports."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    'private_owner_adapter', HERE.parent / 'patricia/adapt_oracles.py')
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


class HeaderControls(unittest.TestCase):
    PREFIX = b'{-# LANGUAGE NoImplicitPrelude #-}\n-- test-only view\n'
    BODY = b' {\n value = "module Other where {";\n untouched = 42;\n}\n'

    def test_exports_and_layout_are_not_an_admission_contract(self):
        for header in (
            b'module Bootstrap.CrateSession (compileSpecFile) where',
            b'module Bootstrap.CrateSession (extra, compileSpecFile) where',
            b'module Bootstrap.CrateSession\n (compileSpecFile, extra)\n where',
            b'module\tBootstrap.CrateSession\nwhere',
        ):
            for target in ('LegacySession', 'CandidateSession'):
                with self.subTest(header=header, target=target):
                    self.assertEqual(A.private_module_view(self.PREFIX + header + self.BODY, target),
                                     self.PREFIX + ('module ' + target + ' where').encode() + self.BODY)

    def test_comments_and_nested_export_parentheses_are_opaque(self):
        header = (b'---- module separator\nmodule {- module Wrong where -} Bootstrap.CrateSession\n'
                  b' (Thing(..), (-->), {- outer ( {- where ) -} -} value,\n'
                  b' -- where ))\n lastValue) {- trailing -} where')
        self.assertEqual(A.private_module_view(self.PREFIX + header + self.BODY, 'CandidateSession'),
                         self.PREFIX + b'---- module separator\nmodule CandidateSession where' + self.BODY)

    def test_no_export_list_still_preserves_every_body_byte(self):
        body = b'\r\n-- where (module)\r\nprivateFunction x = x\r\n'
        self.assertEqual(A.private_module_view(b'module Bootstrap.CrateSession where' + body, 'LegacySession'),
                         b'module LegacySession where' + body)
        self.assertEqual(A.private_module_view(b'module Main (main) where' + body,
                                              'RetainedC3', owner='Main'),
                         b'module RetainedC3 where' + body)

    def test_reject_missing_wrong_or_unterminated_module_header(self):
        for raw in (
            b'-- module Bootstrap.CrateSession where\nvalue = 1',
            b'module Other where {}',
            b'module Bootstrap.CrateSessionExtra where {}',
            b'module Bootstrap.CrateSession (value where {}',
            b'module Bootstrap.CrateSession (value) wher {}',
            b'module Bootstrap.CrateSession {- unfinished',
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    A.private_module_view(raw, 'CandidateSession')

    def test_reject_nonbyte_inputs_and_invalid_destination(self):
        raw = b'module Bootstrap.CrateSession where {}'
        for source, name in ((raw.decode(), 'CandidateSession'),
                             (raw, b'CandidateSession'),
                             (raw, 'invalid'),
                             (raw, 'CandidateSession where bad')):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    A.private_module_view(source, name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
