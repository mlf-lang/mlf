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
    def test_rewritten_history_objects_have_reviewed_publication(self):
        history.resolve_revision.cache_clear()
        for original, (rewritten, oldtree, newtree, kind) in history.REVISIONS.items():
            with self.subTest(original=original):
                self.assertEqual(history.resolve_revision(original), rewritten)
                self.assertEqual(history._object_tree(history.ROOT, rewritten, kind), newtree)
                history.verify_published_revision(original)

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

class SquashTransportControls(HistoryReferenceControls):
    def setUp(self):
        super().setUp()
        import prepare_history_refs
        self.preparation = prepare_history_refs
        self.seal = self.root / history.SEAL_PATH
        self.seal.parent.mkdir(parents=True, exist_ok=True)
        self.seal.write_text("# reviewed implementation\nSOURCE_ANCHOR = '" + '0' * 40 + "'\n")
        self.git('add', '.')
        self.precursor = self.commit(self.git('write-tree').strip(), [self.new, self.old], 'precursor')
        self.seal.write_text(self.seal.read_text().replace('0' * 40, self.precursor))
        self.git('add', '.')
        self.sealed_tree = self.git('write-tree').strip()
        self.source = self.commit(self.sealed_tree, [self.precursor], 'source')
        self.integration = self.commit(self.sealed_tree, [self.old], 'squash')
        for name, value in [('SOURCE_ANCHOR', self.precursor),
                            ('SOURCE_PARENTS', (self.new, self.old)),
                            ('MAIN_BASE', self.old),
                            ('TRANSPORTED', frozenset([self.new]))]:
            context = patch.object(history, name, value)
            context.start(); self.addCleanup(context.stop)
        self.git('reset', '--hard', '-q', self.integration)
        history.verify_source(self.source)
        self.git('update-ref', history.VERIFIED_SOURCE_REF, self.source)

    def commit(self, tree, parents, message):
        args = ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit-tree', tree]
        for parent in parents:
            args.extend(['-p', parent])
        return self.git(*args, '-m', message).strip()

    def verify(self):
        history.verify_published_revision(self.old)

    def test_source_squash_and_future_main_descendant(self):
        history.verify_source(self.source)
        self.verify()
        self.assertFalse(history._is_ancestor(self.new, 'HEAD'))
        for head in [self.source,
                     self.commit(self.sealed_tree, [self.old, self.source], 'PR CI'),
                     self.commit(self.oldtree, [self.integration], 'future edit'),
                     self.commit(self.sealed_tree, [self.integration, self.precursor], 'future merge')]:
            self.git('reset', '--hard', '-q', head)
            self.verify()
        self.git('reset', '--hard', '-q', self.old)
        with self.assertRaises(ValueError):
            self.verify()

    def test_premerge_source_and_synthetic_merge_tree_drift_rejected(self):
        for parents in [[self.source], [self.old, self.source]]:
            with self.subTest(parents=parents):
                drift = self.commit(self.oldtree, parents, 'unsealed tree drift')
                self.git('reset', '--hard', '-q', drift)
                with self.assertRaisesRegex(ValueError, 'no exact sealed HEAD'):
                    self.verify()

    def test_same_tree_source_descendant_and_moved_base_rejected(self):
        newer_main = self.commit(self.oldtree, [self.old], 'empty main advance')
        for parents in [[self.source], [newer_main, self.source]]:
            with self.subTest(parents=parents):
                candidate = self.commit(self.sealed_tree, parents, 'same tree unreviewed lineage')
                self.git('reset', '--hard', '-q', candidate)
                with self.assertRaisesRegex(ValueError, 'no exact sealed HEAD'):
                    self.verify()

    def test_unsealed_anchor_rejected_even_with_direct_ancestry(self):
        self.git('reset', '--hard', '-q', self.source)
        with patch.object(history, 'SOURCE_ANCHOR', '0' * 40):
            with self.assertRaisesRegex(ValueError, 'unsealed'):
                self.verify()
            with self.assertRaisesRegex(ValueError, 'unsealed'):
                self.preparation.prepare()

    def test_wrong_precursor_parents_and_identity_rejected(self):
        for parents in [(self.old, self.new), (self.new,), (self.old, self.old)]:
            with patch.object(history, 'SOURCE_PARENTS', parents):
                with self.assertRaisesRegex(ValueError, 'precursor parents'):
                    self.verify()
        with patch.object(history, 'SOURCE_ANCHOR', self.newtree):
            with self.assertRaisesRegex(ValueError, 'unexpected type'):
                self.verify()

    def test_wrong_source_parents_rejected(self):
        for parents in [[], [self.old], [self.precursor, self.old]]:
            candidate = self.commit(self.sealed_tree, parents, 'wrong source')
            with self.assertRaisesRegex(ValueError, 'source parents'):
                history.verify_source(candidate)

    def test_wrong_integration_parent_and_extra_parent_rejected(self):
        for parents in [[], [self.new], [self.old, self.new]]:
            candidate = self.commit(self.sealed_tree, parents, 'wrong integration')
            self.git('reset', '--hard', '-q', candidate)
            with self.assertRaises(ValueError):
                self.verify()

    def test_tree_blob_mode_path_and_seal_mutations_rejected(self):
        good = self.seal.read_bytes()
        mutations = [lambda: self.seal.write_bytes(good + b'# extra\n'),
                     lambda: self.seal.write_bytes(good.replace(self.precursor.encode(), b'0' * 40)),
                     lambda: self.seal.write_bytes(good + good),
                     lambda: (self.root / 'evidence.txt').write_bytes(b'changed'),
                     lambda: (self.root / 'extra').write_bytes(b'added'),
                     lambda: self.seal.unlink(),
                     lambda: self.git('update-index', '--chmod=+x', history.SEAL_PATH)]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                self.git('reset', '--hard', '-q', self.integration)
                mutate()
                if index != len(mutations) - 1:
                    self.git('add', '-A')
                badtree = self.git('write-tree').strip()
                candidate = self.commit(badtree, [self.precursor], 'bad bytes')
                with self.assertRaisesRegex(ValueError, 'sealed source'):
                    history.verify_source(candidate)
                integration = self.commit(badtree, [self.old], 'bad squash')
                self.git('reset', '--hard', '-q', integration)
                with self.assertRaisesRegex(ValueError, 'sealed source|no exact sealed HEAD'):
                    self.verify()

    def test_added_empty_subtree_rejected(self):
        empty = subprocess.check_output(['git', 'mktree'], cwd=self.root, input=b'').strip()
        root = subprocess.check_output(['git', 'ls-tree', self.sealed_tree], cwd=self.root)
        altered = subprocess.check_output(['git', 'mktree'], cwd=self.root,
                                         input=root + b'040000 tree ' + empty + b'\tempty\n').decode().strip()
        candidate = self.commit(altered, [self.precursor], 'empty subtree')
        with self.assertRaisesRegex(ValueError, 'sealed source tree'):
            history.verify_source(candidate)

    def test_unknown_transport_and_historical_tree_rejected(self):
        with patch.object(history, 'TRANSPORTED', frozenset()):
            with self.assertRaisesRegex(ValueError, 'no reviewed squash'):
                self.verify()
        self.mapping[self.old] = (self.new, self.oldtree, self.oldtree, 'commit')
        with self.assertRaisesRegex(ValueError, 'published historical object'):
            self.verify()

    def test_replacements_cannot_spoof_objects_or_lineage(self):
        self.git('replace', self.new, self.integration)
        self.git('replace', self.precursor, self.old)
        self.verify()
        self.assertFalse(history._is_ancestor(self.new, 'HEAD'))
        self.assertEqual(history._parents(self.precursor), [self.new, self.old])

    def test_graft_and_shallow_history_rejected(self):
        graft = self.root / '.git/info/grafts'
        graft.write_text(self.integration + '\n')
        with self.assertRaisesRegex(ValueError, 'grafted'):
            self.verify()
        graft.unlink()
        (self.root / '.git/shallow').write_text(self.integration + '\n')
        with self.assertRaisesRegex(ValueError, 'shallow'):
            self.verify()

    def test_preparation_existing_anchor_is_offline(self):
        self.preparation.prepare()  # No origin configured.

    def fresh_checkout(self, target):
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(target)], check=True)
        subprocess.run(['git', 'remote', 'add', 'origin', str(self.root)], cwd=target, check=True)
        subprocess.run(['git', 'fetch', '-q', 'origin', 'main'], cwd=target, check=True)
        subprocess.run(['git', 'checkout', '-q', '--detach', 'FETCH_HEAD'], cwd=target, check=True)

    def test_fresh_squash_checkout_fetches_only_reviewed_source(self):
        self.git('update-ref', 'refs/pull/19/head', self.source)
        with tempfile.TemporaryDirectory() as destination:
            target = Path(destination)
            self.fresh_checkout(target)
            with patch.object(history, 'ROOT', target):
                self.assertIsNone(history._object_tree(target, self.precursor, 'commit'))
                self.preparation.prepare()
                self.verify()
                self.assertEqual(history._parents(self.source), [self.precursor])

    def test_retained_source_ref_is_reauthenticated(self):
        self.git('update-ref', history.VERIFIED_SOURCE_REF, self.precursor)
        with self.assertRaisesRegex(ValueError, 'source parents'):
            self.preparation.prepare()
        with self.assertRaisesRegex(ValueError, 'source parents'):
            self.verify()

    def test_precursor_alone_is_not_publication_source(self):
        self.git('update-ref', '-d', history.VERIFIED_SOURCE_REF)
        with self.assertRaisesRegex(ValueError, 'verified sealed source is unavailable'):
            self.verify()

    def test_moved_locator_rejected(self):
        moved = self.commit(self.sealed_tree, [self.source], 'unreviewed later source')
        self.git('update-ref', 'refs/pull/19/head', moved)
        with tempfile.TemporaryDirectory() as destination:
            target = Path(destination)
            self.fresh_checkout(target)
            with patch.object(history, 'ROOT', target):
                for attempt in range(2):
                    with self.subTest(attempt=attempt), self.assertRaisesRegex(ValueError, 'source parents'):
                        self.preparation.prepare()
                    self.assertIsNotNone(history._object_tree(target, self.precursor, 'commit'))
                    self.assertNotEqual(subprocess.run(
                        ['git', 'rev-parse', '--verify', '--quiet', history.VERIFIED_SOURCE_REF],
                        cwd=target, stdout=subprocess.DEVNULL).returncode, 0)

    def test_fetch_failure_and_timeout_propagate(self):
        run = subprocess.run
        for error in [subprocess.CalledProcessError(1, ['git', 'fetch']),
                      subprocess.TimeoutExpired(['git', 'fetch'], 120)]:
            fetched = []
            def fail_fetch(command, **kwargs):
                if command[:3] == ['git', '--no-replace-objects', 'fetch']:
                    fetched.append(command)
                    raise error
                return run(command, **kwargs)
            with patch.object(history, '_object_tree', return_value=None), patch.object(
                    self.preparation.subprocess, 'run', side_effect=fail_fetch):
                with self.assertRaises(type(error)):
                    self.preparation.prepare()
            self.assertEqual(fetched, [['git', '--no-replace-objects', 'fetch', '--no-tags',
                                        'origin', 'refs/pull/19/head']])


if __name__ == '__main__':
    unittest.main()
