#!/usr/bin/env python3
"""Pure historical-isolation controls: no Git, compiler or contract loading."""
import copy
import hashlib
import subprocess
import unittest

import run_design_controls as D


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture():
    old_map = b'module Bootstrap.Map where {\n  sentinel = 11;\n}\n'
    old_set = b'module Bootstrap.Set where {\n  import qualified Bootstrap.Map as M;\n  sentinel = M.empty;\n}\n'
    body = b'  typeIdentities :: Int;\n  typeIdentities = 13;\n'
    collector = (b'module FrozenIdentityInventory where {\n'
                 b'  import qualified Bootstrap.Set as Set;\n' + body + b'}\n')
    inventory = dict(dependencies={D.MAP_PATH: sha(old_map), D.SET_PATH: sha(old_set)},
                     frozen_sha256=sha(collector), body_sha256=sha(body))
    return old_map, old_set, collector, inventory


class DesignIsolationTests(unittest.TestCase):
    def test_handwritten_outputs_preserve_complete_original_algorithms(self):
        actual = D.isolated_sources(*fixture())
        expected = {
            'FrozenDesignMap.hs': b'module FrozenDesignMap where {\n  sentinel = 11;\n}\n',
            'FrozenDesignSet.hs': b'module FrozenDesignSet where {\n  import qualified FrozenDesignMap as M;\n  sentinel = M.empty;\n}\n',
            'FrozenDesignIdentityInventory.hs': b'module FrozenDesignIdentityInventory where {\n  import qualified FrozenDesignSet as Set;\n  typeIdentities :: Int;\n  typeIdentities = 13;\n}\n',
        }
        self.assertEqual(actual, expected)
        originals = fixture()[:3]
        inverse = (
            actual['FrozenDesignMap.hs'].replace(b'module FrozenDesignMap', b'module Bootstrap.Map'),
            actual['FrozenDesignSet.hs'].replace(b'module FrozenDesignSet', b'module Bootstrap.Set').replace(b'qualified FrozenDesignMap', b'qualified Bootstrap.Map'),
            actual['FrozenDesignIdentityInventory.hs'].replace(b'module FrozenDesignIdentityInventory', b'module FrozenIdentityInventory').replace(b'qualified FrozenDesignSet', b'qualified Bootstrap.Set'),
        )
        self.assertEqual(inverse, originals)

    def test_history_mutations_and_dependency_inventory_are_rejected(self):
        for index in range(3):
            values = list(fixture()); values[index] += b' '
            with self.subTest(index=index), self.assertRaises(RuntimeError):
                D.isolated_sources(*values)
        for mutation in ('missing', 'extra', 'pin', 'body'):
            values = list(fixture()); inventory = copy.deepcopy(values[3]); values[3] = inventory
            if mutation == 'missing': del inventory['dependencies'][D.SET_PATH]
            elif mutation == 'extra': inventory['dependencies']['other'] = '0' * 64
            elif mutation == 'pin': inventory['dependencies'][D.MAP_PATH] = '0' * 64
            else: inventory['body_sha256'] = '0' * 64
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                D.isolated_sources(*values)

    def test_repinning_cannot_admit_missing_duplicate_or_colliding_rewrites(self):
        for raw in (b'absent', b'old old', b'old new'):
            with self.subTest(raw=raw), self.assertRaisesRegex(RuntimeError, 'unique oracle adaptation'):
                D.reversible(raw, [(b'old', b'new')])
        # Even a locally rehashed collector cannot change its algorithm body.
        values = list(fixture()); values[2] = values[2].replace(b'= 13', b'= 99')
        values[3]['frozen_sha256'] = sha(values[2])
        with self.assertRaisesRegex(RuntimeError, 'unchanged identity collector bodies'):
            D.isolated_sources(*values)

    def test_fixed_git_tree_and_exact_two_blob_requests(self):
        self.assertEqual(D.HISTORICAL_BASE, 'fc300bc9fdc389b585cbef0630fc8915d53e89c5')
        self.assertEqual(D.HISTORICAL_TREE, '386f0b41ab5f9b39fca273f3040f51d73df924a1')
        self.assertEqual(D.MAP_PATH, 'libraries/mlf-foundation/Bootstrap/Map.hs')
        self.assertEqual(D.SET_PATH, 'libraries/mlf-foundation/Bootstrap/Set.hs')
        calls = []
        answers = iter([(D.HISTORICAL_TREE + '\n').encode(), b'old map', b'old set'])
        def output(argv, timeout):
            self.assertEqual(timeout, 30); calls.append(argv); return next(answers)
        self.assertEqual(D.historical_dependencies('/fixture', output), (b'old map', b'old set'))
        prefix = ['git', '--no-replace-objects', '-C', '/fixture']
        self.assertEqual(calls, [prefix + ['rev-parse', D.HISTORICAL_BASE + '^{tree}'],
                                prefix + ['show', D.HISTORICAL_BASE + ':' + D.MAP_PATH],
                                prefix + ['show', D.HISTORICAL_BASE + ':' + D.SET_PATH]])
        with self.assertRaisesRegex(RuntimeError, 'fixed historical dependency tree'):
            D.historical_dependencies('/fixture', lambda *a, **k: b'wrong-tree\n')

    def test_early_pin_and_git_failures_preserve_stage_and_traceback(self):
        def invalid_pin():
            values = list(fixture()); values[0] += b'changed'
            return D.isolated_sources(*values)
        def failed_git():
            def fail(*args, **kwargs):
                raise subprocess.CalledProcessError(1, ['git', 'show'])
            return D.historical_dependencies('/fixture', fail)
        for stage, action in [('isolate-frozen-dependencies', invalid_pin), ('historical-dependencies', failed_git)]:
            record = dict(complete=False, checks=[]); saved = []
            with self.subTest(stage=stage), self.assertRaises(Exception):
                D.run_stage(record, lambda: saved.append(copy.deepcopy(record)), stage, action)
            self.assertEqual(len(saved), 2)
            self.assertEqual(saved[-1]['stage'], stage)
            self.assertFalse(saved[-1]['complete'])
            self.assertTrue(saved[-1]['error'])
            self.assertIn('Traceback', saved[-1]['traceback'])
            self.assertEqual(saved[-1]['checks'], [])


if __name__ == '__main__':
    unittest.main()
