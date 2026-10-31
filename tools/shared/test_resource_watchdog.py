#!/usr/bin/env python3
"""Focused output-accounting races and final-cap controls; no compiler workloads."""
import ast
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

DRIVER = Path(__file__).with_name('resource_watchdog.py')
TREE = ast.parse(DRIVER.read_text())
FUNCTION = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'output_bytes')
NAMESPACE = {'Path': Path, 'os': os, 'stat': stat, 'errno': errno}
exec(compile(ast.Module(body=[FUNCTION], type_ignores=[]), str(DRIVER), 'exec'), NAMESPACE)
output_bytes = NAMESPACE['output_bytes']


class OutputAccounting(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_regular_files_and_symlink_exclusion(self):
        (self.root/'a').write_bytes(b'a'*7)
        (self.root/'nested').mkdir()
        (self.root/'nested/b').write_bytes(b'b'*5)
        (self.root/'file-link').symlink_to(self.root/'a')
        (self.root/'dir-link').symlink_to(self.root/'nested', target_is_directory=True)
        (self.root/'dangling-link').symlink_to(self.root/'missing')
        os.mkfifo(self.root/'fifo')
        self.assertEqual(output_bytes(self.root), 12)

    def test_disappearing_individual_file_is_skipped(self):
        child = self.root/'query.mlfq.new'
        child.write_bytes(b'old')
        (self.root/'query.mlfq').write_bytes(b'new result')
        original = Path.lstat
        def raced(path, *args, **kwargs):
            if path == child:
                child.unlink()
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, 'lstat', raced):
            self.assertEqual(output_bytes(self.root), len(b'new result'))
        self.assertEqual(output_bytes(self.root), len(b'new result'))

    def test_missing_root_is_not_a_sampled_file_race(self):
        with self.assertRaises(FileNotFoundError):
            output_bytes(self.root/'absent-root')

    def test_non_directory_root_rejects(self):
        root_file = self.root/'file'
        root_file.write_bytes(b'x')
        with self.assertRaises(NotADirectoryError):
            output_bytes(root_file)

    def test_root_permission_error_propagates(self):
        with mock.patch.object(Path, 'stat', side_effect=PermissionError('root permission')):
            with self.assertRaises(PermissionError):
                output_bytes(self.root)

    def test_file_permission_and_other_errors_propagate(self):
        (self.root/'file').write_bytes(b'x')
        for error in [PermissionError('file permission'), OSError('unexpected file error')]:
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(Path, 'lstat', side_effect=error):
                    with self.assertRaises(type(error)):
                        output_bytes(self.root)

    def test_directory_errors_are_not_swallowed(self):
        for error in [PermissionError('directory permission'), FileNotFoundError('directory gone'),
                      OSError('unexpected traversal error')]:
            def failed_walk(root, *, followlinks, onerror):
                self.assertFalse(followlinks)
                onerror(error)
                return iter(())
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(os, 'walk', failed_walk):
                    with self.assertRaises(type(error)):
                        output_bytes(self.root)


class ActualWatchdog(unittest.TestCase):
    def run_watchdog(self, name, script, limit=1):
        evidence = os.environ.get('MLF_WATCHDOG_TEST_OUTPUT')
        if evidence:
            parent = Path(evidence)
            parent.mkdir(parents=True, exist_ok=True)
            out = parent/name
            out.mkdir(exist_ok=False)
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            out = Path(temporary.name)/name
        command = [sys.executable, str(DRIVER), '--seconds', '15', '--address-space-mib', '256',
                   '--rss-mib', '128', '--disk-free-mib', '1', '--max-output-mib', str(limit),
                   str(out), sys.executable, '-c', script, str(out)]
        result = subprocess.run(command, capture_output=True, timeout=25)
        if evidence:
            (out/'test-driver.stdout').write_bytes(result.stdout)
            (out/'test-driver.stderr').write_bytes(result.stderr)
        return result, out, json.loads((out/'bounded-receipt.json').read_text())

    def test_actual_atomic_rename_writer_and_final_accounting(self):
        script = """import pathlib,sys,time
root=pathlib.Path(sys.argv[1]); deadline=time.monotonic()+1.2; count=0
while time.monotonic()<deadline:
 temporary=root/'query.mlfq.new'; temporary.write_bytes(b'x'*65536)
 temporary.replace(root/'query.mlfq'); count+=1
(root/'rename-count').write_text(str(count))
"""
        result, out, receipt = self.run_watchdog('atomic-renames', script)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertTrue(receipt['complete'])
        self.assertIsNone(receipt['reason'])
        self.assertGreater(int((out/'rename-count').read_text()), 0)
        self.assertEqual((out/'query.mlfq').stat().st_size, 65536)
        self.assertGreaterEqual(receipt['samples'][-1]['output_bytes'], 65536)

    def test_fast_final_renamed_oversize_is_rejected(self):
        script = """import pathlib,sys
root=pathlib.Path(sys.argv[1]); temporary=root/'query.mlfq.new'
temporary.write_bytes(b'x'*(2*1024*1024)); temporary.replace(root/'query.mlfq')
"""
        result, out, receipt = self.run_watchdog('final-oversize', script)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(receipt['complete'])
        self.assertEqual(receipt['reason'], 'RuntimeError: output growth limit')
        self.assertGreater(receipt['samples'][-1]['output_bytes'], 1024*1024)
        self.assertEqual((out/'query.mlfq').stat().st_size, 2*1024*1024)


if __name__ == '__main__':
    unittest.main()
