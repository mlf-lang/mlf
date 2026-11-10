#!/usr/bin/env python3
"""Failure-boundary tests for the formatter runner, without a compiler install."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_formatter_compatibility as runner


class RunnerControls(unittest.TestCase):
    def test_exact_recursive_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = ['libraries/a/A.hs', 'libraries/b/deep/B.hs',
                        'tools/shared/fixtures/formatter/deep/C.hs']
            for name in expected + ['libraries/a/skip.txt', 'tests/Excluded.hs']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('test')
            self.assertEqual([str(p.relative_to(root)) for p in runner.corpus_sources(root)], expected)
            added = root / 'libraries/b/New.hs'
            added.write_text('new')
            self.assertIn(added, runner.corpus_sources(root))

    def test_source_changes_invalidate_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ['shared-sources.json', 'tools/shared/FormatterCompatibility.hs',
                         'tools/shared/test_formatter_compatibility.py', 'host/ghc/cbits/host.c',
                         'runtime/mlf_process_supervisor.c', 'libraries/a/A.hs']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('before')
            before = runner.source_inputs(root, ['libraries/a'])
            source = root / 'libraries/a/A.hs'
            source.write_text('after')
            self.assertNotEqual(before, runner.source_inputs(root, ['libraries/a']))
            source.write_text('before')
            self.assertEqual(before, runner.source_inputs(root, ['libraries/a']))
            fixture = root / 'tools/shared/fixtures/formatter/New.hs'
            fixture.parent.mkdir(parents=True)
            fixture.write_text('new fixture')
            self.assertNotEqual(before, runner.source_inputs(root, ['libraries/a']))

    def test_safe_flags(self):
        self.assertEqual(runner.FORMAT_FLAGS,
                         ['--no-cabal', '--no-dot-ormolu', '--check-idempotence', '--color', 'never'])

    def test_missing_tool_leaves_incomplete_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'run'
            result = subprocess.run([sys.executable, runner.__file__, '--ghc',
                                     str(Path(tmp) / 'absent'), '--output', str(output)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            receipt = json.loads((output / 'receipt.json').read_text())
            self.assertFalse(receipt['completed'])
            self.assertEqual(receipt['passed_count'], 0)

    def test_output_reuse_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            sentinel = Path(tmp) / 'receipt.json'
            sentinel.write_text('preserve')
            result = subprocess.run([sys.executable, runner.__file__, '--output', tmp], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_text(), 'preserve')

    def test_timeout_preserves_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / 'logs').mkdir()
            receipt = {'commands': []}
            with self.assertRaisesRegex(RuntimeError, 'timed out'):
                runner.run([sys.executable, '-c', 'import time; print("started", flush=True); time.sleep(10)'],
                           output, 'timeout', 1, receipt)
            self.assertTrue(receipt['commands'][0]['timed_out'])
            self.assertEqual((output / 'logs/timeout.stdout').read_text(), 'started\n')
            self.assertTrue((output / 'logs/timeout.stderr').exists())

    def test_nonzero_cannot_pass(self):
        with self.assertRaises(RuntimeError):
            runner.require_success((1, 'PASS', ''), 'fake')


if __name__ == '__main__':
    unittest.main()
