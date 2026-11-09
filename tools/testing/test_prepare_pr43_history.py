#!/usr/bin/env python3
"""Tiny real-Git squash recovery controls; no archived sources or compiler."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import history_refs as history
import prepare_pr43_history as prep


class PR43HistoryControls(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.check_output(['git', '--no-replace-objects', *args],
                                       cwd=root, text=True, stderr=subprocess.PIPE).strip()

    def commit(self, tree, parents, message):
        args = ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit-tree', tree]
        for parent in parents:
            args += ['-p', parent]
        return self.git(self.origin, *args, '-m', message)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.origin, self.checkout = root/'origin', root/'checkout'
        for directory in (self.origin, self.checkout):
            directory.mkdir()
            self.git(directory, 'init', '-q')
        (self.origin/'evidence').write_text('base\n')
        self.git(self.origin, 'add', '.')
        tree0 = self.git(self.origin, 'write-tree')
        base = self.commit(tree0, [], 'base')
        old = self.commit(tree0, [base], 'frozen predecessor')
        (self.origin/'evidence').write_text('migration\n')
        self.git(self.origin, 'add', '.')
        tree = self.git(self.origin, 'write-tree')
        newer = self.commit(tree, [old], 'migration predecessor')
        source = self.commit(tree, [newer], 'source')
        integration = self.commit(tree, [base], 'squash')
        self.transport = history.SquashTransport(source, integration, base, tree)
        self.predecessors = ((newer, tree), (old, tree0))
        self.git(self.origin, 'update-ref', prep.SOURCE_REF, source)
        self.git(self.checkout, 'remote', 'add', 'origin', str(self.origin))
        self.git(self.checkout, 'fetch', '--no-tags', 'origin', integration)
        self.git(self.checkout, 'reset', '--hard', '-q', integration)
        for name, value, module in [('ROOT', self.checkout, history),
                                    ('TRANSPORT', self.transport, prep),
                                    ('PREDECESSORS', self.predecessors, prep)]:
            context = patch.object(module, name, value)
            context.start(); self.addCleanup(context.stop)

    def test_recovers_missing_objects_and_retains_exact_source(self):
        self.assertIsNone(history._object_tree(self.checkout, self.transport.source, 'commit'))
        prep.prepare()
        prep.verify(self.transport.source)
        self.assertEqual(self.git(self.checkout, 'rev-parse', 'refs/history/verified-source-'+self.transport.source),
                         self.transport.source)
        # A second call needs no mutable remote locator.
        self.git(self.origin, 'update-ref', '-d', prep.SOURCE_REF)
        prep.prepare()

    def test_changed_locator_is_not_retained(self):
        self.git(self.origin, 'update-ref', prep.SOURCE_REF, self.transport.parent)
        with self.assertRaisesRegex(ValueError, 'locator differs'):
            prep.prepare()
        with self.assertRaises(subprocess.CalledProcessError):
            self.git(self.checkout, 'rev-parse', '--verify', 'refs/history/verified-source-'+self.transport.source)

    def test_source_tree_parent_and_missing_predecessor_rejected(self):
        prep.prepare()
        cases = [('source', self.transport.integration, 'source ancestry'),
                 ('tree', self.predecessors[1][1], 'source tree'),
                 ('parent', self.predecessors[1][0], 'integration parent')]
        for field, value, diagnostic in cases:
            changed = self.transport._replace(**{field: value})
            with self.subTest(field=field), patch.object(prep, 'TRANSPORT', changed):
                with self.assertRaisesRegex(ValueError, diagnostic):
                    prep.verify(changed.source)
        with patch.object(prep, 'PREDECESSORS', (('0'*40, self.transport.tree), self.predecessors[1])):
            with self.assertRaisesRegex(ValueError, 'predecessor tree'):
                prep.verify(self.transport.source)

    def test_wrong_predecessor_tree_and_lineage_rejected(self):
        prep.prepare()
        with patch.object(prep, 'PREDECESSORS', ((self.predecessors[0][0], '0'*40), self.predecessors[1])):
            with self.assertRaisesRegex(ValueError, 'predecessor tree'):
                prep.verify(self.transport.source)
        with patch.object(prep, 'PREDECESSORS', tuple(reversed(self.predecessors))):
            with self.assertRaisesRegex(ValueError, 'predecessor lineage'):
                prep.verify(self.transport.source)

    def test_unrelated_checkout_rejected_before_fetch(self):
        self.git(self.checkout, 'reset', '--hard', '-q', self.transport.parent)
        with self.assertRaisesRegex(ValueError, 'integration ancestry'):
            prep.prepare()
        self.assertIsNone(history._object_tree(self.checkout, self.transport.source, 'commit'))

    def test_shallow_and_grafted_history_rejected(self):
        (self.checkout/'.git/shallow').write_text(self.transport.integration+'\n')
        with self.assertRaisesRegex(ValueError, 'shallow history'):
            prep.prepare()
        (self.checkout/'.git/shallow').unlink()
        (self.checkout/'.git/info/grafts').write_text('')
        with self.assertRaisesRegex(ValueError, 'grafted history'):
            prep.prepare()


if __name__ == '__main__':
    unittest.main()
