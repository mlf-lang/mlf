#!/usr/bin/env python3
"""Offline PR25 -> PR22 and completed PR19 -> PR22 publication controls."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import history_refs as history
import prepare_history_refs as preparation
from test_history_refs import HistoryReferenceControls


class ComposedHistoryControls(HistoryReferenceControls):
    def commit(self, tree, parents, message):
        args = ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit-tree', tree]
        for parent in parents:
            args.extend(['-p', parent])
        return self.git(*args, '-m', message).strip()

    def tree_with_seal(self, anchor, extra=''):
        path = self.root / history.SEAL_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# reviewed event\nSOURCE_ANCHOR = '" + anchor + "'\n" + extra)
        self.git('add', '.')
        return self.git('write-tree').strip()

    def setUp(self):
        super().setUp()
        self.source25 = self.commit(self.newtree, [self.new], 'source25')
        self.s25 = self.commit(self.newtree, [self.old], 'squash25')
        self.h19 = self.commit(self.newtree, [self.old], 'history19')
        self.p19 = self.commit(self.tree_with_seal('0' * 40), [self.h19], 'precursor19')
        self.tree19 = self.tree_with_seal(self.p19)
        self.q19 = self.commit(self.tree19, [self.p19], 'source19')
        self.s19 = self.commit(self.tree19, [self.old], 'squash19')
        self.branch22 = self.commit(self.newtree, [self.s25, self.h19], 'branch22')
        self.p22 = self.commit(self.tree_with_seal('0' * 40, '# PR22 changes\n'),
                               [self.branch22, self.s19], 'precursor22')
        self.tree22 = self.tree_with_seal(self.p22, '# PR22 changes\n')
        self.q22 = self.commit(self.tree22, [self.p22], 'source22')
        self.s22 = self.commit(self.tree22, [self.s19], 'squash22')
        self.transport25 = history.SquashTransport(self.source25, self.s25, self.old, self.newtree)
        self.event19 = history.CompletedSeal(self.p19, (self.h19,), self.q19, self.s19,
                                             self.old, self.tree19, (self.h19,))
        self.mapping[self.h19] = (self.h19, self.newtree, self.newtree, 'commit')
        self.mapping[self.branch22] = (self.branch22, self.newtree, self.newtree, 'commit')
        for name, value in [('SOURCE_ANCHOR', self.p22),
                            ('SOURCE_PARENTS', (self.branch22, self.s19)),
                            ('MAIN_BASE', self.s19),
                            ('TRANSPORTED', frozenset([self.h19, self.branch22])),
                            ('COMPLETED_SEALS', {'19': self.event19}),
                            ('SQUASH_TRANSPORTS', {self.new: self.transport25})]:
            context = patch.object(history, name, value)
            context.start(); self.addCleanup(context.stop)
        self.source_refs = {self.q19: 'refs/pull/19/head', self.source25: 'refs/pull/25/head'}
        context = patch.object(preparation, 'SOURCE_REFS', self.source_refs)
        context.start(); self.addCleanup(context.stop)
        for ref, value in [('refs/pull/19/head', self.q19), ('refs/pull/25/head', self.source25),
                           ('refs/pull/22/head', self.q22), (history.VERIFIED_SOURCE_REF, self.q22),
                           ('refs/history/verified-source-' + self.q19, self.q19),
                           ('refs/history/verified-source-' + self.source25, self.source25)]:
            self.git('update-ref', ref, value)
        self.git('reset', '--hard', '-q', self.s22)

    def verify(self):
        for original in self.mapping:
            history.verify_published_revision(original)

    def test_both_completed_events_and_nested_publication(self):
        history.verify_squash_transport(self.new, self.transport25, self.p22)
        history.verify_completed_seal(self.event19, self.p22)
        self.assertFalse(history._is_ancestor(self.new, self.p22))
        self.assertFalse(history._is_ancestor(self.s25, 'HEAD'))
        self.assertFalse(history._is_ancestor(self.p19, 'HEAD'))
        self.verify()
        for head in [self.q22, self.commit(self.tree22, [self.s19, self.q22], 'PR CI'),
                     self.commit(self.oldtree, [self.s22], 'later main change'),
                     self.commit(self.oldtree, [self.s22, self.p22], 'later merge precursor')]:
            self.git('reset', '--hard', '-q', head)
            self.verify()

    def test_pr19_requires_exact_source_parent_tree_and_integration(self):
        unrelated = self.commit(self.tree19, [self.old], 'unrelated integration')
        for field, value in [('anchor', self.h19), ('anchor_parents', (self.old,)),
                             ('source', self.s19), ('source', self.tree19),
                             ('tree', self.newtree), ('integration', unrelated),
                             ('parent', self.h19), ('histories', (self.new,))]:
            with self.subTest(field=field), patch.object(history, 'COMPLETED_SEALS',
                                                       {'19': self.event19._replace(**{field: value})}):
                with self.assertRaises(ValueError):
                    self.verify()
        extra = self.commit(self.tree19, [self.old, self.h19], 'wrong integration parents')
        with self.assertRaisesRegex(ValueError, 'integration parent'):
            history.verify_completed_seal(self.event19._replace(integration=extra), extra)
        with self.assertRaisesRegex(ValueError, 'integration ancestry'):
            history.verify_completed_seal(self.event19, self.old)

    def test_pr25_requires_original_pins_and_lineage_inside_precursor(self):
        unrelated = self.commit(self.newtree, [self.old], 'unrelated source')
        for field, value in [('source', unrelated), ('source', self.newtree),
                             ('tree', self.oldtree), ('integration', unrelated),
                             ('parent', self.new)]:
            with self.subTest(field=field), patch.object(history, 'SQUASH_TRANSPORTS',
                            {self.new: self.transport25._replace(**{field: value})}):
                with self.assertRaises(ValueError):
                    self.verify()
        extra = self.commit(self.newtree, [self.old, self.new], 'extra integration parent')
        with self.assertRaisesRegex(ValueError, 'integration parent'):
            history.verify_squash_transport(self.new, self.transport25._replace(integration=extra), extra)
        with self.assertRaisesRegex(ValueError, 'integration ancestry'):
            history.verify_squash_transport(self.new, self.transport25, self.s22)
        with patch.object(history, 'SQUASH_TRANSPORTS', {}):
            with self.assertRaisesRegex(ValueError, 'precursor historical ancestry'):
                self.verify()

    def test_composed_wrong_outer_parent_tree_and_premerge_drift_rejected(self):
        bad_heads = [self.commit(self.tree22, [self.old], 'wrong outer parent'),
                     self.commit(self.tree22, [self.s19, self.p22], 'extra outer parent'),
                     self.commit(self.tree19, [self.s19], 'wrong outer tree'),
                     self.commit(self.oldtree, [self.q22], 'changed source descendant'),
                     self.commit(self.tree22, [self.q22], 'same tree source descendant')]
        for head in bad_heads:
            self.git('reset', '--hard', '-q', head)
            with self.subTest(head=head), self.assertRaises(ValueError):
                self.verify()

    def test_composed_replacements_do_not_spoof_evidence(self):
        self.git('replace', self.new, self.s22)
        self.git('replace', self.p19, self.old)
        self.git('replace', self.s25, self.old)
        self.verify()
        self.assertFalse(history._is_ancestor(self.s25, 'HEAD'))

    def fresh_checkout(self, target):
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(target)], check=True)
        subprocess.run(['git', 'remote', 'add', 'origin', str(self.root)], cwd=target, check=True)
        subprocess.run(['git', 'fetch', '-q', 'origin', 'main'], cwd=target, check=True)
        subprocess.run(['git', 'checkout', '-q', '--detach', 'FETCH_HEAD'], cwd=target, check=True)

    def test_fresh_squash_downloads_three_independent_sources_and_retries_offline(self):
        with tempfile.TemporaryDirectory() as destination:
            target = Path(destination)
            self.fresh_checkout(target)
            with patch.object(history, 'ROOT', target):
                self.assertIsNone(history._object_tree(target, self.p22, 'commit'))
                preparation.prepare()
                subprocess.run(['git', 'remote', 'remove', 'origin'], cwd=target, check=True)
                preparation.prepare()
                self.verify()

    def test_each_moved_locator_fails_on_both_attempts_without_retention(self):
        for ref, source, retained in [('refs/pull/19/head', self.q19, 'refs/history/verified-source-' + self.q19),
                                     ('refs/pull/25/head', self.source25, 'refs/history/verified-source-' + self.source25),
                                     ('refs/pull/22/head', self.q22, history.VERIFIED_SOURCE_REF)]:
            moved = self.commit(history._object_tree(self.root, source, 'commit'), [source], 'moved locator')
            self.git('update-ref', ref, moved)
            with self.subTest(ref=ref), tempfile.TemporaryDirectory() as destination:
                target = Path(destination)
                self.fresh_checkout(target)
                with patch.object(history, 'ROOT', target):
                    for attempt in range(2):
                        with self.subTest(attempt=attempt), self.assertRaises(ValueError):
                            preparation.prepare()
                        self.assertNotEqual(subprocess.run(
                            ['git', 'rev-parse', '--verify', '--quiet', retained], cwd=target,
                            stdout=subprocess.DEVNULL).returncode, 0)
            self.git('update-ref', ref, source)

    def test_closed_retained_refs_reauthenticated(self):
        for source in [self.q19, self.source25]:
            ref = 'refs/history/verified-source-' + source
            self.git('update-ref', ref, self.old)
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'reviewed SHA'):
                preparation.prepare()
            self.git('update-ref', ref, source)

    def test_unreviewed_locator_and_missing_objects_fail_closed(self):
        ref = 'refs/history/verified-source-' + self.q19
        self.git('update-ref', '-d', ref)
        with patch.object(preparation, 'SOURCE_REFS', {}):
            with self.assertRaisesRegex(ValueError, 'no reviewed source fetch ref'):
                preparation.prepare()
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            history.verify_completed_source(self.event19._replace(source='0' * 40))


if __name__ == '__main__':
    unittest.main()
