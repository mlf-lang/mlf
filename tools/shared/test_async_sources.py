#!/usr/bin/env python3
"""Cheap active-fixture regressions; deliberately not a compiler/parity claim."""
import tempfile
from pathlib import Path
import shutil
import unittest
import json
import shlex
import re
from unittest.mock import patch
from check_async_sources import ROOT, DIRECTORIES, check_static, stale_names, run, capture_inputs, unchanged, check_lookup_roots, SOURCE_COMPILE_SECONDS, TARGET_CHECK_SECONDS, completion_rejection_pattern


class AsyncSourceControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in DIRECTORIES:
            shutil.copytree(ROOT / directory, self.root / directory)

    def test_current_sources(self):
        self.assertGreater(len(check_static(self.root)), 20)

    def test_original_unit_regression(self):
        p = self.root / 'tests/async-task/Main.emlf'
        p.write_text(p.read_text().replace('IO ()', 'IO Unit', 1))
        with self.assertRaisesRegex(ValueError, 'stale nominal'):
            check_static(self.root)

    def test_other_nominal_regressions(self):
        for name in ('List', 'Nil', 'Cons', 'Pair', 'Triple', 'class Monad'):
            self.assertTrue(stale_names(name))
        self.assertFalse(stale_names('-- Unit\n"List Pair" IO ()'))

    def test_wrong_kind_cannot_regress_to_expression_colon(self):
        p = self.root / 'tests/fixtures/async-completion/negative/wrong-kind.emlf'
        p.write_text('main = panic "unused" : Completion IO\n')
        with self.assertRaisesRegex(ValueError, 'explicit invalid kind signature'):
            check_static(self.root)

    def test_wrong_kind_cannot_become_well_kinded(self):
        p = self.root / 'tests/fixtures/async-completion/negative/wrong-kind.emlf'
        p.write_text('main :: Completion Int\nmain = panic "unused"\n')
        with self.assertRaisesRegex(ValueError, 'explicit invalid kind signature'):
            check_static(self.root)

    def test_wrong_kind_requires_kind_or_arity_diagnostic(self):
        pattern = completion_rejection_pattern('wrong-kind')
        for diagnostic in ('Inference: unknown data constructor: Completion',
                           'Parse error: expected annotation',
                           'Inference: type constructor mismatch: String versus Int'):
            self.assertIsNone(re.search(pattern, diagnostic))
        for diagnostic in ('Inference: kind mismatch', 'Inference: type argument arity mismatch'):
            self.assertIsNotNone(re.search(pattern, diagnostic))

    def test_stale_checked_type(self):
        (self.root / 'tests/async-process/io-unit.type').write_text('IO Unit\n')
        with self.assertRaisesRegex(ValueError, 'type oracle'):
            check_static(self.root)

    def test_stale_completion_oracle(self):
        p = self.root / 'tests/fixtures/async-completion/check.sh'
        p.write_text(p.read_text().replace('IO ()', 'IO Unit'))
        with self.assertRaisesRegex(ValueError, 'completion checked'):
            check_static(self.root)

    def test_missing_entry(self):
        (self.root / 'tests/async-task/Main.emlf').unlink()
        with self.assertRaisesRegex(ValueError, 'inventory'):
            check_static(self.root)

    def test_missing_completion_negative(self):
        (self.root / 'tests/fixtures/async-completion/negative/mixed-values.emlf').unlink()
        with self.assertRaisesRegex(ValueError, 'inventory'):
            check_static(self.root)

    def test_unauthenticated_compiler_cannot_pass(self):
        output = self.root / 'result'
        with patch('check_async_sources.authenticate_build', side_effect=ValueError('untrusted producer')), \
             patch('check_async_sources.CommandRunner.run') as command:
            with self.assertRaisesRegex(ValueError, 'untrusted producer'):
                run(self.root, output)
        command.assert_not_called()
        self.assertFalse(json.loads((output / 'result.json').read_text())['complete'])

    def test_frozen_and_target_negative_not_rewritten(self):
        (self.root / 'bootstrap').mkdir()
        (self.root / 'bootstrap/frozen.emlf').write_text('IO Unit')
        self.assertTrue(check_static(self.root))

    def prepare_lookup(self):
        for name in ('libraries/mlf-async/Async', 'libraries/mlf-foundation', 'tools/shared/fixtures', 'empty'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.library = self.root / 'libraries/mlf-async/Async/Task.hs'
        self.library.write_text('module Async.Task where {}')
        (self.root / 'shared-sources.json').write_text(json.dumps({'modules': [
            {'module': 'Async.Task', 'path': str(self.library.relative_to(self.root))}]}))
        return self.root / 'empty'

    def test_added_hs_shadow_is_detected(self):
        cwd = self.prepare_lookup()
        files = check_static(self.root)
        check_lookup_roots(self.root, files, cwd)
        before = capture_inputs(self.root, [])
        shadow = self.root / 'tests/async-task/Async/Task.hs'
        shadow.parent.mkdir()
        shadow.write_text(self.library.read_text())
        with self.assertRaisesRegex(ValueError, 'inventory changed'):
            unchanged(before, capture_inputs(self.root, []))
        # A shadow already present before the snapshot must also be rejected.
        with self.assertRaisesRegex(ValueError, 'shadows authenticated'):
            check_lookup_roots(self.root, files, cwd)

    def test_directory_alias_addition_and_retarget(self):
        cwd = self.prepare_lookup()
        files = check_static(self.root)
        before = capture_inputs(self.root, [])
        alias = self.root / 'tests/async-task/Async'
        alias.symlink_to(self.library.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'inventory changed'):
            unchanged(before, capture_inputs(self.root, []))
        with self.assertRaisesRegex(ValueError, 'shadows authenticated'):
            check_lookup_roots(self.root, files, cwd)
        aliased = capture_inputs(self.root, [])
        other = self.root / 'libraries/Other'
        other.mkdir()
        (other / 'Task.hs').write_text(self.library.read_text())
        alias.unlink()
        alias.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'inventory changed'):
            unchanged(aliased, capture_inputs(self.root, []))

    def test_ambient_cwd_cannot_resolve_sources(self):
        cwd = self.prepare_lookup()
        (cwd / 'Async').mkdir()
        with self.assertRaisesRegex(ValueError, 'empty regular directory'):
            check_lookup_roots(self.root, check_static(self.root), cwd)

    def test_different_module_cannot_add_hierarchy_root(self):
        cwd = self.prepare_lookup()
        source = self.root / 'tests/async-task/Main.emlf'
        source.write_text(source.read_text().replace('module Main where', 'module Surprise.Main where'))
        with self.assertRaisesRegex(ValueError, 'module/hierarchy'):
            check_lookup_roots(self.root, check_static(self.root), cwd)

    def test_compile_budget_matches_existing_native_parity(self):
        self.assertEqual(SOURCE_COMPILE_SECONDS, 600)
        self.assertEqual(TARGET_CHECK_SECONDS, 120)
        for path in ('tools/release/test-async-task.sh', 'tools/release/test-async-process.sh',
                     'tests/fixtures/async-completion/check.sh'):
            self.assertIn('timeout_seconds=${MLF_ASYNC_COMMAND_TIMEOUT:-600}', (ROOT / path).read_text())

    def test_ci_evidence_is_inside_watchdog_budget(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        commands = [line for line in workflow.splitlines()
                    if 'resource_watchdog.py' in line and 'check_async_sources.py' in line]
        self.assertEqual(len(commands), 1)
        args = shlex.split(commands[0])
        for flag, value in {'--seconds': '1800', '--address-space-mib': '6144',
                            '--rss-mib': '4096', '--max-output-mib': '256',
                            '--disk-free-mib': '8192'}.items():
            self.assertEqual(args[args.index(flag) + 1], value)
        source_index = args.index('tools/shared/check_async_sources.py')
        # The command's Python prefix follows the watchdog output root.
        watched = Path(args[source_index - 3])
        output = Path(args[args.index('--output') + 1])
        self.assertTrue(output.is_relative_to(watched))
        self.assertNotEqual(output, watched)
        self.assertIn('            ' + str(watched) + '/', workflow)

    def test_cheap_gate_is_unconditional(self):
        self.assertIn('python3 -B tools/shared/test_async_sources.py', (ROOT / 'tools/release/check.sh').read_text())
        self.assertIn('python3 -O -B tools/shared/test_async_sources.py', (ROOT / 'tools/release/check.sh').read_text())


if __name__ == '__main__':
    unittest.main()
