#!/usr/bin/env python3
"""Capability and observed child-state protocol controls, independent of Git history."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import run_controls as R


class RuntimeProtocolTests(unittest.TestCase):
    def test_cwd_capability_requires_complete_known_response(self):
        self.assertTrue(R.cwd_capability(b'spawn-cwd\n'))
        self.assertFalse(R.cwd_capability(b'fork-cwd-fallback\n'))
        for output in (b'', b'spawn-cwd', b'spawn-cwd\nignored\n', b'unknown\n'):
            with self.subTest(output=output), self.assertRaises(RuntimeError):
                R.cwd_capability(output)

    def test_compiled_sdk_runtime_probe(self):
        compiler = shutil.which('cc')
        if compiler is None:
            self.skipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'cwd-capability'
            subprocess.run([compiler, '-std=c11', str(R.HERE / 'CwdCapability.c'), '-o', str(binary)],
                           check=True, capture_output=True, timeout=30)
            result = subprocess.run([str(binary)], check=True, capture_output=True, timeout=10)
            self.assertEqual(result.stderr, b'')
            supported = R.cwd_capability(result.stdout)
            if sys.platform != 'darwin':
                self.assertFalse(supported)

    def test_child_state_inventory_for_cwd_spawn_and_fork_fallback(self):
        examples = [(True, [30, 29, 1, 30, 30, 21, 9, 1]),
                    (False, [29, 28, 2, 30, 30, 20, 9, 0])]
        for supported, counters in examples:
            with self.subTest(supported=supported):
                result = R.validate_eligibility(repr((6, 6, counters)).encode(), supported)
                self.assertEqual(result, dict(fds_before=6, fds_after=6, counters=counters))

    def test_child_state_drift_is_a_failure(self):
        for supported, counters in [(True, [30, 29, 1, 30, 30, 21, 9, 1]),
                                    (False, [29, 28, 2, 30, 30, 20, 9, 0])]:
            wrong = [(6, 7, counters), (0, 0, counters), (True, True, counters),
                     (6, 6, counters[:-1]), (6, 6, counters + [0]), (6, 6, tuple(counters))]
            for index in range(len(counters)):
                changed = list(counters)
                changed[index] += 1
                wrong.append((6, 6, changed))
            for value in wrong:
                with self.subTest(supported=supported, value=value), self.assertRaises(RuntimeError):
                    R.validate_eligibility(repr(value).encode(), supported)
            with self.assertRaises(RuntimeError):
                R.validate_eligibility(repr((6, 6, counters)).encode(), not supported)

    def test_malformed_or_missing_child_report_is_a_failure(self):
        for output in (b'', b'not a report', b'(1,)', b'[]', b'False', b'\xff'):
            with self.subTest(output=output), self.assertRaises((RuntimeError, ValueError, SyntaxError)):
                R.validate_eligibility(output, False)


if __name__ == '__main__':
    unittest.main()
