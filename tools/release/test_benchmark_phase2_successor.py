#!/usr/bin/env python3
"""Run every original benchmark control with the exact stock input, then IntSet."""
import json
import unittest
from unittest import mock

import test_benchmark_transition as original
from check_benchmark_phase2_successor import ROOT, stock_transition, successor, validate_new_benchmark


class BenchmarkTransition(original.BenchmarkTransition):
    @classmethod
    def setUpClass(cls):
        cls.root = ROOT
        cls.opened = cls.enterClassContext(successor.qualified(ROOT))
        _, cls.inputs, cls.contract, _ = stock_transition(ROOT, cls.opened)
        cls.inputs = list(cls.inputs)
        cls.live_manifest = successor.read(ROOT, successor.BENCHMARK)
        cls.intset = successor.read(ROOT, successor.INTSET)

    def test_whole_live_source_drift(self):
        with mock.patch.object(self, 'contract', self.opened.contract):
            super().test_whole_live_source_drift()

    def test_phase2_full_live_transition(self):
        validate_new_benchmark(ROOT, self.opened)

    def test_new_modules_require_exact_bytes_in_both_directions(self):
        contract = self.opened.contract
        current = {p: successor.read(ROOT, p) for p in contract.value['current_files']}
        historic = contract.project_tree_bytes(current)
        additions = {p: current[p] for p in contract.added_paths}
        path = contract.value['module_paths']['Bootstrap.Graph.ScopeIndex']
        self.assertNotIn(path, historic)
        self.assertEqual(contract.advance_tree_bytes(historic, additions), current)
        for inventory, check in ((current, contract.project_tree_bytes),
                                 (additions, lambda data: contract.advance_tree_bytes(historic, data))):
            with self.subTest(direction=check.__name__):
                altered = dict(inventory)
                altered[path] += b'\\n'
                with self.assertRaises(ValueError):
                    check(altered)
                del altered[path]
                with self.assertRaises(ValueError):
                    check(altered)

    def test_phase2_intset_must_not_be_stale_or_altered(self):
        old = successor.parse_intset(self.opened.git, self.intset)
        for raw in (old, self.intset + b'\n', self.intset.replace(b'finishAsc', b'otherAsc', 1)):
            with self.subTest(raw_bytes=len(raw)), self.assertRaises(ValueError):
                validate_new_benchmark(ROOT, self.opened, live_intset=raw)

    def test_phase2_undeclared_manifest_change_is_rejected(self):
        altered = json.loads(self.live_manifest)
        altered['pinned_sha256']['runtime/khash.h'] = '0' * 64
        stale_types = json.loads(self.live_manifest)
        path = original.bridge.TYPES
        stale_types['pinned_sha256'][path] = self.contract.value['current_files'][path]
        for raw in (self.inputs[0], successor.json_bytes(altered), successor.json_bytes(stale_types),
                    b'{"pinned_sha256":{},' + self.live_manifest.lstrip()[1:]):
            with self.subTest(raw_bytes=len(raw)), self.assertRaises(ValueError):
                validate_new_benchmark(ROOT, self.opened, new_manifest=raw)


if __name__ == '__main__':
    unittest.main()
