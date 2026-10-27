#!/usr/bin/env python3
"""Fail-closed controls for the reviewed history transport mapping."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import history_refs as history


class HistoryReferenceControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q', '-b', 'main')
        (self.root / 'evidence.txt').write_bytes(b'frozen evidence\n')
        (self.root / 'tools/profile/results').mkdir(parents=True)
        (self.root / 'tools/profile/results/generated.txt').write_bytes(b'generated\n')
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-q', '-m', 'original')
        self.old = self.git('rev-parse', 'HEAD').strip()
        self.oldtree = self.git('rev-parse', 'HEAD^{tree}').strip()
        self.git('rm', '-rq', 'tools/profile/results')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-q', '-m', 'cleaned')
        self.new = self.git('rev-parse', 'HEAD').strip()
        self.newtree = self.git('rev-parse', 'HEAD^{tree}').strip()
        self.mapping = {self.old: (self.new, self.oldtree, self.newtree, 'commit'),
                        self.oldtree: (self.newtree, self.oldtree, self.newtree, 'tree')}
        self.root_patch = patch.object(history, 'ROOT', self.root)
        self.refs_patch = patch.object(history, 'REVISIONS', self.mapping)
        self.root_patch.start(); self.refs_patch.start()
        self.addCleanup(self.root_patch.stop); self.addCleanup(self.refs_patch.stop)
        history.resolve_revision.cache_clear()
        self.addCleanup(history.resolve_revision.cache_clear)

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True)

    def test_cleaned_commit_and_tree_preserve_historical_bytes(self):
        self.assertEqual(history.resolve_revision(self.old), self.new)
        self.assertEqual(history.historical_bytes(self.old, 'evidence.txt'), b'frozen evidence\n')
        self.assertEqual(history.resolve_revision(self.oldtree), self.newtree)
        self.assertEqual(history.historical_bytes(self.oldtree, 'evidence.txt'), b'frozen evidence\n')

    def test_original_exact_identity_works_when_rewrite_unavailable(self):
        self.mapping[self.old] = ('0' * 40, self.oldtree, self.newtree, 'commit')
        self.assertEqual(history.resolve_revision(self.old), self.old)
        self.assertEqual(history.historical_bytes(self.old, 'evidence.txt'), b'frozen evidence\n')

    def test_wrong_rewritten_tree_fails_without_fallback(self):
        self.mapping[self.old] = (self.new, self.oldtree, '1' * 40, 'commit')
        with self.assertRaisesRegex(ValueError, 'rewritten historical tree differs'):
            history.historical_bytes(self.old, 'evidence.txt')

    def test_unknown_or_missing_identity_fails(self):
        with self.assertRaisesRegex(ValueError, 'unreviewed historical identity'):
            history.resolve_revision('9' * 40)
        absent = '8' * 40
        self.mapping[absent] = ('7' * 40, '6' * 40, '5' * 40, 'commit')
        with self.assertRaisesRegex(ValueError, 'identity is unavailable'):
            history.resolve_revision(absent)

    def test_object_type_mismatch_fails(self):
        self.mapping[self.old] = (self.newtree, self.oldtree, self.newtree, 'commit')
        with self.assertRaisesRegex(ValueError, 'unexpected type'):
            history.resolve_revision(self.old)

    def test_removed_and_unsafe_paths_fail_even_when_original_exists(self):
        for path in ['tools/profile/results/generated.txt', './tools/profile/results/generated.txt', 'tools//profile/results/generated.txt', 'papers/example.pdf', './papers/example.pdf', '../outside', '/absolute', 'evil:path', r'papers\example.pdf']:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'unavailable or invalid'):
                history.historical_bytes(self.old, path)


class PublishedMappingControls(unittest.TestCase):
    def test_rewritten_history_objects_are_exact_and_commit_ancestors(self):
        history.resolve_revision.cache_clear()
        for original, (rewritten, oldtree, newtree, kind) in history.REVISIONS.items():
            with self.subTest(original=original):
                self.assertEqual(history.resolve_revision(original), rewritten)
                self.assertEqual(history._object_tree(history.ROOT, rewritten, kind), newtree)
                if kind == 'commit':
                    self.assertEqual(subprocess.run(['git', 'merge-base', '--is-ancestor', rewritten, 'HEAD'],
                                                    cwd=history.ROOT).returncode, 0)

    def test_reconciliation_allows_only_the_pinned_transport_edits(self):
        import hashlib
        snapshot = '4d732f31982ebe18124511f2ca4cb412770d6bd6'
        for path in ('.github/workflows/ci.yml', 'tools/release/check.sh',
                     'tools/testing/check_reconciliation_inventory.py'):
            with self.subTest(path=path):
                original = history.historical_bytes(snapshot, path)
                digest = hashlib.sha256(original).hexdigest()
                current = (history.ROOT / path).read_bytes()
                self.assertTrue(history.checked_current(path, current, digest))
                self.assertFalse(history.checked_current(path, current + b'\n# unrelated change\n', digest))
                with self.assertRaisesRegex(ValueError, 'frozen reconciliation input changed'):
                    history.checked_current(path, current, '0' * 64)

    def test_windows_negative_control_pins_original_runner_bytes(self):
        import hashlib
        original = 'e7da00f201bfb66bf6e26d59e56184dd37a83abd'
        expected = 'fce82f0710edd910557956a2225f211f195f10b69e95c3676d86bb01fd2f6abd'
        raw = history.historical_bytes(original, 'runtime/mlf_build_runner.c')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
        workflow = (history.ROOT / '.github/workflows/ci.yml').read_text()
        self.assertIn(history.REVISIONS[original][0], workflow)
        self.assertIn(expected, workflow)
        self.assertIn("Assert-Release $rejected 'Regression unexpectedly accepted the pre-fix runner'", workflow)
        self.assertIn("Assert-Release ($result.complete -eq $true -and $result.exit_code -eq 126)", workflow)


if __name__ == '__main__':
    unittest.main()
