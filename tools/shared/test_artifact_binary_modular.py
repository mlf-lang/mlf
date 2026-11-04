#!/usr/bin/env python3
"""Pure source/spec admission controls; never builds a compiler or native fixture."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('artifact_modular_actual', HERE / 'test_artifact_binary.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
parser = argparse.ArgumentParser()
parser.add_argument('--source-root', type=Path, default=HERE.parents[1])
args, rest = parser.parse_known_args()
SOURCE = args.source_root.resolve(strict=True)


def unpack(text):
    values = []
    while text:
        n, colon, text = text.partition(':')
        if not colon or not n.isdecimal() or len(text) < int(n):
            raise ValueError('bad independent length field')
        size = int(n)
        values.append(text[:size])
        text = text[size:]
    return values


class ModularControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((SOURCE / 'shared-sources.json').read_text())
        cls.fixture = SOURCE / 'tools/shared/fixtures/item4/RawBinaryShared.hs'
        cls.rows = M.native_source_closure(SOURCE, cls.fixture, cls.manifest)

    def test_complete_source_closure(self):
        self.assertEqual(len(self.rows), 51)
        self.assertEqual({r['module'] for r in self.rows}, M.NATIVE_MODULES)
        self.assertIn('Bootstrap.CrateArtifact', M.NATIVE_MODULES)
        self.assertEqual(next(r['path'] for r in self.rows if r['module'] == 'Main'), str(self.fixture))
        for row in self.rows:
            self.assertEqual(row['sha256'], M.sha(Path(row['path'])))
            self.assertEqual(row['bytes'], Path(row['path']).stat().st_size)

    def test_spec_independent_decode(self):
        directory = Path('/fresh/binary gate/π😀')
        fields = unpack(M.native_crate_spec(self.rows, directory))
        self.assertEqual(fields[:4], ['MLF-CRATE-1', 'artifact-binary-native', 'Main', 'false'])
        self.assertEqual(fields[5:], ['', str(directory / 'inference-cache'), str(directory / 'builtin/prelude')])
        self.assertEqual([unpack(x) for x in unpack(fields[4])],
                         [[r['module'], r['path']] for r in self.rows])

    def test_scalar_field_roundtrip(self):
        values = ['', 'a:b', 'π😀', 'space path']
        self.assertEqual(unpack(M.crate_fields(values)), values)

    def test_field_rejects_nul(self):
        with self.assertRaises(ValueError): M.crate_fields(['a\0b'])

    def test_field_rejects_surrogate(self):
        with self.assertRaises(ValueError): M.crate_fields(['\ud800'])

    def test_field_rejects_nonstring(self):
        with self.assertRaises(ValueError): M.crate_fields([1])

    def test_spec_rejects_omission(self):
        with self.assertRaises(ValueError): M.native_crate_spec(self.rows[:-1], Path('/fresh'))

    def test_spec_rejects_reordering(self):
        with self.assertRaises(ValueError): M.native_crate_spec(list(reversed(self.rows)), Path('/fresh'))

    def test_manifest_rejects_duplicate(self):
        m = copy.deepcopy(self.manifest); m['modules'].append(m['modules'][0])
        with self.assertRaises(ValueError): M.native_source_closure(SOURCE, self.fixture, m)

    def test_manifest_rejects_escape(self):
        m = copy.deepcopy(self.manifest); m['modules'][0]['path'] = '../outside.hs'
        with self.assertRaises(ValueError): M.native_source_closure(SOURCE, self.fixture, m)

    def test_manifest_rejects_absolute(self):
        m = copy.deepcopy(self.manifest); m['modules'][0]['path'] = '/outside.hs'
        with self.assertRaises(ValueError): M.native_source_closure(SOURCE, self.fixture, m)

    def test_manifest_rejects_missing_dependency(self):
        m = copy.deepcopy(self.manifest)
        m['modules'] = [r for r in m['modules'] if r['module'] != 'Bootstrap.CrateArtifact']
        with self.assertRaises(ValueError): M.native_source_closure(SOURCE, self.fixture, m)

    def bad_fixture(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'Main.hs'; p.write_text(text)
            with self.assertRaises(ValueError): M.native_source_closure(SOURCE, p, self.manifest)

    def test_fixture_rejects_wrong_header(self):
        self.bad_fixture(self.fixture.read_text().replace('module Main where', 'module Wrong where', 1))

    def test_fixture_rejects_unknown_import(self):
        self.bad_fixture(self.fixture.read_text().replace('  import MLF.Primitive;', '  import Missing.Module;'))

    def test_fixture_rejects_reduced_scope(self):
        self.bad_fixture('module Main where {\n import MLF.Primitive;\n main = return ();\n}\n')

    def test_cold_query_accepts_fresh(self):
        M.require_cold_queries({'groups': [{'cached': False}], 'inferred_groups': 1, 'reused_groups': 0})

    def test_cold_query_rejects_empty(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [], 'inferred_groups': 0, 'reused_groups': 0})

    def test_cold_query_rejects_reuse(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [{'cached': True}], 'inferred_groups': 1, 'reused_groups': 0})

    def test_cold_query_rejects_bool_count(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [{'cached': False}], 'inferred_groups': True, 'reused_groups': 0})

    def test_cold_query_rejects_missing_cached(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [{}], 'inferred_groups': 1, 'reused_groups': 0})

    def test_cold_query_rejects_count_mismatch(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [{'cached': False}], 'inferred_groups': 2, 'reused_groups': 0})


if __name__ == '__main__':
    unittest.main(argv=[__file__, *rest])
