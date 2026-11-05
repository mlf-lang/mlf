#!/usr/bin/env python3
"""Fail-closed controls for the reviewed history transport mapping."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import history_refs as history
import prepare_history_refs as preparation


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
    def test_rewritten_objects_have_exact_identity_and_reviewed_reachability(self):
        history.resolve_revision.cache_clear()
        for original, (rewritten, oldtree, newtree, kind) in history.REVISIONS.items():
            with self.subTest(original=original):
                self.assertEqual(history.resolve_revision(original), rewritten)
                self.assertEqual(history._object_tree(history.ROOT, rewritten, kind), newtree)
                history.verify_published_revision(original)

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


class SquashTransportControls(HistoryReferenceControls):
    def setUp(self):
        super().setUp()
        self.source = self.commit(self.newtree, [self.new], 'source tip')
        self.integration = self.commit(self.newtree, [self.old], 'squash integration')
        self.git('reset', '--hard', '-q', self.integration)
        self.transport = history.SquashTransport(self.source, self.integration, self.old, self.newtree)
        self.transports = {self.new: self.transport}
        transport_patch = patch.object(history, 'SQUASH_TRANSPORTS', self.transports)
        transport_patch.start()
        self.addCleanup(transport_patch.stop)

    def commit(self, tree, parents, message):
        args = ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit-tree', tree]
        for parent in parents:
            args += ['-p', parent]
        return self.git(*args, '-m', message).strip()

    def verify(self):
        history.verify_published_revision(self.old)

    def test_exact_transport_and_later_descendant_succeed_without_claiming_ancestry(self):
        self.assertFalse(history._is_ancestor(self.new, 'HEAD'))
        self.verify()
        later = self.commit(self.oldtree, [self.integration], 'later unrelated edit')
        self.git('reset', '--hard', '-q', later)
        self.verify()
        # Reachability must not remain cached after HEAD changes.
        self.git('reset', '--hard', '-q', self.old)
        with self.assertRaisesRegex(ValueError, 'ancestry differs'):
            self.verify()

    def test_direct_ancestry_needs_no_transport(self):
        self.git('reset', '--hard', '-q', self.source)
        self.transports.clear()
        self.verify()

    def test_no_implicit_transport_for_unknown_mapping(self):
        self.transports.clear()
        with self.assertRaisesRegex(ValueError, 'no reviewed ancestry or squash transport'):
            self.verify()
        with self.assertRaisesRegex(ValueError, 'unreviewed historical identity'):
            history.verify_published_revision('9' * 40)

    def test_missing_source_integration_parent_and_history_fail(self):
        for field in ('source', 'integration', 'parent'):
            with self.subTest(field=field):
                self.transports[self.new] = self.transport._replace(**{field: '0' * 40})
                with self.assertRaisesRegex(ValueError, 'unavailable'):
                    self.verify()
        self.transports[self.new] = self.transport
        self.mapping[self.old] = ('0' * 40, self.oldtree, self.newtree, 'commit')
        with self.assertRaisesRegex(ValueError, 'published historical object is unavailable'):
            self.verify()

    def test_wrong_tree_types_and_mapping_fail(self):
        for field, value in [('tree', self.oldtree), ('source', self.old),
                             ('source', self.newtree), ('integration', self.old),
                             ('integration', self.newtree), ('parent', self.oldtree)]:
            with self.subTest(field=field, value=value):
                self.transports[self.new] = self.transport._replace(**{field: value})
                with self.assertRaisesRegex(ValueError, 'tree differs|unexpected type'):
                    self.verify()
        self.transports[self.new] = self.transport
        self.mapping[self.old] = (self.new, self.oldtree, self.oldtree, 'commit')
        with self.assertRaisesRegex(ValueError, 'published historical object is unavailable or differs'):
            self.verify()

    def test_wrong_single_parent_and_extra_parent_fail(self):
        extra = self.commit(self.newtree, [self.old, self.new], 'two parents')
        for transport in [self.transport._replace(parent=self.new),
                          self.transport._replace(integration=extra)]:
            with self.subTest(transport=transport):
                self.transports[self.new] = transport
                with self.assertRaisesRegex(ValueError, 'parent differs'):
                    self.verify()

    def test_unrelated_same_tree_source_and_integration_fail(self):
        unrelated = self.commit(self.newtree, [self.old], 'same tree but unrelated')
        for field in ('source', 'integration'):
            with self.subTest(field=field):
                self.transports[self.new] = self.transport._replace(**{field: unrelated})
                with self.assertRaisesRegex(ValueError, 'ancestry differs'):
                    self.verify()

    def test_source_must_descend_from_prior_target(self):
        other_parent = self.commit(self.oldtree, [], 'unrelated prior target')
        integration = self.commit(self.newtree, [other_parent], 'unrelated target squash')
        self.git('reset', '--hard', '-q', integration)
        self.transports[self.new] = self.transport._replace(integration=integration, parent=other_parent)
        with self.assertRaisesRegex(ValueError, 'ancestry differs'):
            self.verify()

    def test_git_replacements_cannot_spoof_evidence(self):
        # A replacement could otherwise make the mapped historical commit look
        # like HEAD, or hide the valid source's exact raw tree.
        self.git('replace', self.new, self.integration)
        self.git('replace', self.source, self.old)
        self.assertFalse(history._is_ancestor(self.new, 'HEAD'))
        self.assertEqual(history._object_tree(self.root, self.source, 'commit'), self.newtree)
        self.verify()
        self.transports.clear()
        with self.assertRaisesRegex(ValueError, 'no reviewed ancestry or squash transport'):
            self.verify()

    def test_git_ancestry_errors_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'ancestry check failed'):
            history._is_ancestor('0' * 40, 'HEAD')

    def test_preparation_existing_objects_is_offline(self):
        # No origin configured: a successful preparation cannot have fetched.
        preparation.prepare()

    def test_preparation_rejects_present_wrong_type_or_tree_without_fetch(self):
        # No origin exists, so these errors must not attempt a network repair.
        self.transports[self.new] = self.transport._replace(source=self.newtree)
        with self.assertRaisesRegex(ValueError, 'unexpected type'):
            preparation.prepare()
        self.transports[self.new] = self.transport._replace(tree=self.oldtree)
        with self.assertRaisesRegex(ValueError, 'squash source tree differs'):
            preparation.prepare()

    def test_preparation_fetches_only_exact_reviewed_ref(self):
        with tempfile.TemporaryDirectory() as destination:
            target = Path(destination)
            self.git('update-ref', 'refs/pull/25/head', self.source)
            subprocess.run(['git', 'init', '-q', '-b', 'main', str(target)], check=True)
            subprocess.run(['git', 'remote', 'add', 'origin', str(self.root)], cwd=target, check=True)
            subprocess.run(['git', 'fetch', '-q', 'origin', 'main'], cwd=target, check=True)
            subprocess.run(['git', 'checkout', '-q', '--detach', 'FETCH_HEAD'], cwd=target, check=True)
            with patch.object(history, 'ROOT', target), patch.object(
                    preparation, 'SOURCE_REFS', {self.source: 'refs/pull/25/head'}):
                self.assertIsNone(history._object_tree(target, self.source, 'commit'))
                preparation.prepare()
                self.assertEqual(history._object_tree(target, self.source, 'commit'), self.newtree)

    def test_preparation_rejects_unreviewed_or_moved_ref(self):
        missing = '0' * 40
        self.transports[self.new] = self.transport._replace(source=missing)
        with patch.object(preparation, 'SOURCE_REFS', {}):
            with self.assertRaisesRegex(ValueError, 'no reviewed fetch ref'):
                preparation.prepare()
        self.git('remote', 'add', 'origin', str(self.root))
        self.git('update-ref', 'refs/pull/25/head', self.source)
        with patch.object(preparation, 'SOURCE_REFS', {missing: 'refs/pull/25/head'}):
            with self.assertRaisesRegex(ValueError, 'fetched squash source differs'):
                preparation.prepare()

    def test_preparation_fetch_error_and_timeout_fail_closed(self):
        missing = '0' * 40
        self.transports[self.new] = self.transport._replace(source=missing)
        run = subprocess.run
        for error in [subprocess.CalledProcessError(1, ['git', 'fetch']),
                      subprocess.TimeoutExpired(['git', 'fetch'], 120)]:
            def fail_fetch(command, **kwargs):
                if command[:2] == ['git', 'fetch']:
                    raise error
                return run(command, **kwargs)
            with self.subTest(error=type(error).__name__), patch.object(
                    preparation, 'SOURCE_REFS', {missing: 'refs/pull/25/head'}), patch.object(
                    preparation.subprocess, 'run', side_effect=fail_fetch):
                with self.assertRaises(type(error)):
                    preparation.prepare()


if __name__ == '__main__':
    unittest.main()
