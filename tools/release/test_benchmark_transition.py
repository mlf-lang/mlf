#!/usr/bin/env python3
"""Finite source-provenance controls; no benchmark or compiler execution."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import check_benchmark_transition as bridge


class BenchmarkTransition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = bridge.ROOT
        cls.contract = bridge.load_contract(cls.root)
        cls.inputs = [(cls.root / name).read_bytes() for name in
                      ['benchmarks/manifest.json', bridge.HISTORY, bridge.TYPES, bridge.OLD_TYPES,
                       bridge.STD, bridge.INTSET]]

    def check(self, inputs):
        bridge.validate_bridge(*inputs, self.contract)

    def reject(self, index, change):
        values = list(self.inputs)
        values[index] = change(values[index])
        with self.assertRaises(ValueError):
            self.check(values)

    def mutate_manifest(self, change):
        def mutate(raw):
            value = json.loads(raw)
            change(value)
            return json.dumps(value).encode()
        self.reject(0, mutate)

    def test_exact_transition(self):
        self.check(self.inputs)

    def test_archived_manifest_byte_drift(self):
        self.reject(1, lambda raw: raw + b'\n')

    def test_historical_source_drift(self):
        self.reject(3, lambda raw: raw + b'\n')

    def test_current_source_drift(self):
        self.reject(2, lambda raw: raw + b'\n')

    def test_current_std_source_drift(self):
        self.reject(4, lambda raw: raw + b'\n')

    def test_old_source_is_not_live_source(self):
        self.reject(2, lambda raw: self.inputs[3])

    def test_old_pin_cannot_attest_live_source(self):
        self.mutate_manifest(lambda value: value['pinned_sha256'].__setitem__(
            bridge.TYPES, bridge.OLD_TYPES_SHA))

    def test_unrelated_pin_drift(self):
        self.mutate_manifest(lambda value: value['pinned_sha256'].__setitem__(
            'runtime/khash.h', '0' * 64))

    def test_workload_drift(self):
        self.mutate_manifest(lambda value: value['workloads'][0].__setitem__('default_input', 1))

    def test_boolean_is_not_schema_integer(self):
        self.mutate_manifest(lambda value: value.__setitem__('schema_version', True))

    def test_float_is_not_input_integer(self):
        self.mutate_manifest(lambda value: value['workloads'][0].__setitem__('default_input', 16.0))

    def test_missing_evidence_pin(self):
        self.mutate_manifest(lambda value: value['pinned_sha256'].pop(bridge.HISTORY))

    def test_duplicate_manifest_key(self):
        self.reject(0, lambda raw: b'{"pinned_sha256":{},' + raw.lstrip()[1:])

    def test_whole_live_source_drift(self):
        # Use separate copies, never mutate the source checkout under test.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in self.contract.value['current_files']:
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.root / name, destination)
            path = root / 'libraries/mlf-crates/Bootstrap/Bitstream.hs'
            path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaises(ValueError):
                self.contract.live_source_inventory(root)

    def test_current_intset_source_drift(self):
        self.reject(5, lambda raw: raw + b'\n')

    def test_wrong_intset_source(self):
        self.reject(5, lambda raw: self.inputs[2])

    def test_current_intset_pin_drift(self):
        self.mutate_manifest(lambda value: value['pinned_sha256'].__setitem__(
            bridge.INTSET, '0' * 64))

    def test_rehashed_intset_source_drift(self):
        values = list(self.inputs)
        values[5] += b'\n'
        manifest = json.loads(values[0])
        manifest['pinned_sha256'][bridge.INTSET] = bridge.sha(values[5])
        values[0] = json.dumps(manifest).encode()
        with self.assertRaises(ValueError):
            self.check(values)

    def test_missing_intset_pin(self):
        self.mutate_manifest(lambda value: value['pinned_sha256'].pop(bridge.INTSET))

    def test_other_foundation_pin_drift(self):
        self.mutate_manifest(lambda value: value['pinned_sha256'].__setitem__(
            'libraries/mlf-foundation/Bootstrap/IntMap.hs', '0' * 64))

    def test_flags_drift(self):
        self.mutate_manifest(lambda value: value['workloads'][0]['flags'].__setitem__('mlf', ['-O0']))

    def test_upstream_drift(self):
        self.mutate_manifest(lambda value: value['upstream'].__setitem__('revision', '0' * 40))


if __name__ == '__main__':
    unittest.main()
