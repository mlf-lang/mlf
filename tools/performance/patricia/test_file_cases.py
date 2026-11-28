"""Exercise selected file execution, byte comparison and failure propagation."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import file_cases as F


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FileCaseControls(unittest.TestCase):
    cases = [
        {'name': 'accepted', 'modules': {'Main': 'module Main where\nmain = 42\n'},
         'expected_type': 'Int'},
        {'name': 'rejected', 'modules': {'Main': 'module Main where\nmain = false + 1\n'},
         'expected_type': 'reject', 'exact_error': 'type mismatch'},
    ]

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.out = Path(directory.name)
        self.calls, self.saved = [], []
        self.record = {'file_cases': []}
        self.inputs = {}
        self.H = SimpleNamespace(require=require, sha=sha,
            load=lambda path: json.loads(Path(path).read_text()),
            check_pins=lambda pins: [require(sha(path) == digest, 'changed input')
                                     for path, digest in pins.items()])

    def run_probe(self, label, argv, cwd):
        self.calls.append((label, argv, cwd))
        _, _, prefix, expected_type = argv
        if expected_type == 'reject':
            return b'REJECT "type mismatch"\n', b''
        for suffix in ('.mlfci', '.mlfco'):
            Path(str(prefix) + suffix).write_bytes(('complete fixture ' + suffix).encode())
        Path(str(prefix) + '.queries').write_text(json.dumps({
            'inferred_groups': 1, 'reused_groups': 0,
            'groups': [{'id': 'main', 'members': ['main'], 'cached': False}]}))
        return b'PASS file checked Int\n', b''

    def run_cases(self, run=None, selected=None):
        with mock.patch.object(F, 'load_cases', return_value=self.cases):
            F.run_files(self.H, run or self.run_probe, lambda: self.saved.append(True),
                        self.record, self.inputs, self.out, '/builtin', 'reference', 'candidate',
                        selected=selected)

    def test_complete_case_order_and_selected_execution(self):
        self.run_cases(selected='accepted')
        self.assertEqual([row['name'] for row in self.record['file_cases']], ['accepted'])
        self.assertEqual([call[1][0] for call in self.calls], ['reference', 'candidate'])
        self.assertEqual(len(self.saved), 1)
        self.assertTrue(self.record['file_cases'][0]['actual_raw_artifact_bytes_equal'])

    def test_accept_and_reject_preserve_authored_order(self):
        self.run_cases()
        self.assertEqual([row['name'] for row in self.record['file_cases']], ['accepted', 'rejected'])
        self.assertEqual(len(self.calls), 4)

    def test_same_stdout_cannot_hide_changed_candidate_artifact(self):
        def changed(label, argv, cwd):
            result = self.run_probe(label, argv, cwd)
            if argv[0] == 'candidate':
                Path(str(argv[2]) + '.mlfco').write_bytes(b'changed')
            return result
        with self.assertRaisesRegex(ValueError, 'whole checked artifact bytes'):
            self.run_cases(changed, 'accepted')
        self.assertEqual(self.record['file_cases'], [])

    def test_rejection_cannot_publish_artifacts(self):
        def changed(label, argv, cwd):
            result = self.run_probe(label, argv, cwd)
            Path(str(argv[2]) + '.mlfco').write_bytes(b'must not exist')
            return result
        with self.assertRaisesRegex(ValueError, 'rejection publishes no artifacts'):
            self.run_cases(changed, 'rejected')

    def test_cached_result_is_not_fresh_inference(self):
        def changed(label, argv, cwd):
            result = self.run_probe(label, argv, cwd)
            path = Path(str(argv[2]) + '.queries')
            report = json.loads(path.read_text())
            report['reused_groups'] = 1
            path.write_text(json.dumps(report))
            return result
        with self.assertRaisesRegex(ValueError, 'fresh parsed-file inference'):
            self.run_cases(changed, 'accepted')

    def test_failed_execution_propagates_without_passing_receipt(self):
        def failed(*args):
            raise RuntimeError('producer failed')
        with self.assertRaisesRegex(RuntimeError, 'producer failed'):
            self.run_cases(failed, 'accepted')
        self.assertEqual(self.record['file_cases'], [])
        self.assertEqual(self.saved, [])

    def test_unknown_selection_fails_before_any_execution(self):
        with self.assertRaisesRegex(ValueError, 'unknown file case'):
            self.run_cases(selected='missing')
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
