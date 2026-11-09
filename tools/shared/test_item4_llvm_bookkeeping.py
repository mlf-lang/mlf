#!/usr/bin/env python3
"""Cheap receipt/argv regression tests; does not compile or rerun source inference."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import test_item4_llvm as runner


class Bookkeeping(unittest.TestCase):
    def test_source_argv_and_output(self):
        argv, expected = runner.emission_plan('source-unit', Path('/out/emitter'), Path('/out/program.ll'))
        self.assertEqual(argv, [Path('/out/emitter'), runner.SOURCE_UNIT, Path('/out/program.ll')])
        self.assertEqual(expected, '11\n63\n42\n')

    def test_source_and_emitter_are_authenticated(self):
        before = runner.sources()
        source = runner.input_key(runner.SOURCE_UNIT)
        emitter = runner.input_key(runner.fixture_for_suite('source-unit'))
        closure = runner.compiled_closure(runner.fixture_for_suite('source-unit'), before, '', 'source-unit')
        self.assertTrue({source, emitter}.issubset(closure))
        self.assertTrue(closure.issubset(before))
        after = dict(before)
        after[source] = 'changed'
        self.assertEqual([k for k in sorted(closure) if before[k] != after[k]], [source])

    def test_external_runner_path_does_not_fail_at_receipt_finalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / 'scratch-runner.py'
            script.write_text('# independently recorded scratch runner\n')
            with patch.object(runner, '__file__', str(script)):
                before = runner.sources()
                closure = runner.compiled_closure(runner.fixture_for_suite('source-unit'), before, '', 'source-unit')
                self.assertIn(str(script.resolve()), closure)
                self.assertEqual(before[str(script.resolve())], runner.sha(script))
                self.assertTrue(closure.issubset(before))

    def test_compile_log_paths(self):
        module = 'libraries/mlf-foundation/Bootstrap/Types.hs'
        fixture = runner.fixture_for_suite('source-unit')
        log = '[1 of 2] Compiling Bootstrap.Types ( ' + module + ', /out/Types.o )\n'
        log += '[2 of 2] Compiling Main ( ' + str(fixture) + ', /out/Main.o )\n'
        closure = runner.compiled_closure(fixture, runner.sources(), log, 'source-unit')
        self.assertIn(module, closure)
        self.assertIn(runner.input_key(fixture), closure)

    def test_existing_argv_and_expectations_unchanged(self):
        for suite in ['ordinary', 'unit', 'unit-fast']:
            argv, expected = runner.emission_plan(suite, 'emitter', 'output.ll')
            self.assertEqual(argv, ['emitter', 'output.ll'])
            self.assertEqual(expected, runner.EXPECTED if suite == 'ordinary' else '101\n102\n103\n104\n63\n105\nDONE\n')


if __name__ == '__main__':
    unittest.main()
