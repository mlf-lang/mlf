"""Fresh fixture snapshots and native-run input binding; no history prerequisites."""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest import mock

import header_validation_adapter as H

ROOT = Path(__file__).resolve().parents[2]


class PreparationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.root = self.work / 'source'
        self.output = self.work / 'output'
        self.output.mkdir()
        sources = H.input_paths(ROOT)
        self.paths = H.input_paths(self.root)
        for name, path in self.paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(sources[name].read_bytes())

    def bound_inputs(self):
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.paths.values()}

    def test_prepare_from_plain_source_copy_and_bind_to_build_inputs(self):
        expected = self.bound_inputs()
        target, evidence = H.prepare(self.root, self.output)
        self.assertEqual(evidence['inputs'], expected)
        self.assertEqual({p.name for p in target.iterdir()}, set(self.paths) | {'preparation.json'})
        for name, path in self.paths.items():
            self.assertEqual((target / name).read_bytes(), path.read_bytes())
            self.assertEqual(evidence['generated'][name], expected[str(path)])
        H.verify_prepared(self.root, target, evidence, expected_inputs=expected)
        self.assertFalse(evidence['qualification_executed'])
        self.assertFalse(evidence['historical_complete_compiler_qualified'])

    def test_source_edits_before_preparation_create_a_new_identity(self):
        before = self.bound_inputs()
        for path in self.paths.values():
            path.write_bytes(path.read_bytes() + b'\n')
        target, evidence = H.prepare(self.root, self.output)
        self.assertEqual(evidence['inputs'], self.bound_inputs())
        for name, path in self.paths.items():
            self.assertNotEqual(evidence['inputs'][str(path)], before[str(path)])
            self.assertEqual((target / name).read_bytes(), path.read_bytes())
        H.verify_prepared(self.root, target, evidence, expected_inputs=self.bound_inputs())

    def test_preparation_cannot_silently_rebind_old_native_build_inputs(self):
        bound = self.bound_inputs()
        path = self.paths['HeaderValidationCurrent.hs']
        path.write_bytes(path.read_bytes() + b'\n')
        target, evidence = H.prepare(self.root, self.output)
        with self.assertRaisesRegex(ValueError, 'bound build inputs'):
            H.verify_prepared(self.root, target, evidence, expected_inputs=bound)
        incomplete = self.bound_inputs()
        incomplete.pop(str(path))
        with self.assertRaisesRegex(ValueError, 'bound build inputs'):
            H.verify_prepared(self.root, target, evidence, expected_inputs=incomplete)

    def test_each_original_input_change_after_preparation_is_rejected(self):
        target, evidence = H.prepare(self.root, self.output)
        for path in self.paths.values():
            original = path.read_bytes()
            path.write_bytes(original + b'\n')
            with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, 'inputs changed'):
                H.verify_prepared(self.root, target, evidence)
            path.write_bytes(original)

    def test_each_prepared_source_change_or_omission_is_rejected(self):
        target, evidence = H.prepare(self.root, self.output)
        for name in self.paths:
            path = target / name
            original = path.read_bytes()
            path.write_bytes(original + b'\n')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'prepared header source changed'):
                H.verify_prepared(self.root, target, evidence)
            path.unlink()
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'source inventory changed'):
                H.verify_prepared(self.root, target, evidence)
            path.write_bytes(original)

    def test_extra_prepared_source_is_rejected(self):
        target, evidence = H.prepare(self.root, self.output)
        (target / 'Additional.hs').write_text('module Additional where\n')
        with self.assertRaisesRegex(ValueError, 'source inventory changed'):
            H.verify_prepared(self.root, target, evidence)

    def test_altered_or_incomplete_receipt_is_rejected(self):
        target, evidence = H.prepare(self.root, self.output)
        path = target / 'preparation.json'
        changed = dict(evidence, qualification_executed=True)
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'receipt changed'):
            H.verify_prepared(self.root, target, evidence)
        for name in self.paths:
            changed = {**evidence, 'generated': dict(evidence['generated'])}
            changed['generated'].pop(name)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'source inventory required'):
                H.verify_prepared(self.root, target, changed)

    def test_source_symlink_missing_directory_or_oversize_is_rejected(self):
        path = self.paths['HistoricalHeaderNames.hs']
        original = path.read_bytes()
        outside = self.work / 'outside.hs'
        outside.write_bytes(original)
        for mode in ('symlink', 'missing', 'directory', 'oversize'):
            path.unlink()
            if mode == 'symlink':
                path.symlink_to(outside)
            elif mode == 'directory':
                path.mkdir()
            elif mode == 'oversize':
                path.write_bytes(b'x' * (H.MAX_BYTES + 1))
            with self.subTest(mode=mode), self.assertRaises((ValueError, FileNotFoundError)):
                H.prepare(self.root, self.output)
            self.assertFalse((self.output / 'header-validation').exists())
            if path.is_dir():
                path.rmdir()
            elif path.exists() or path.is_symlink():
                path.unlink()
            path.write_bytes(original)

    def test_existing_output_is_not_reused_or_overwritten(self):
        target, evidence = H.prepare(self.root, self.output)
        original = (target / 'HeaderValidationCurrent.hs').read_bytes()
        with self.assertRaises(FileExistsError):
            H.prepare(self.root, self.output)
        self.assertEqual((target / 'HeaderValidationCurrent.hs').read_bytes(), original)
        H.verify_prepared(self.root, target, evidence)

    def test_write_or_readback_corruption_is_rejected(self):
        original_write, original_read = Path.write_bytes, Path.read_bytes
        for mode in ('write', 'read'):
            for index, name in enumerate((*self.paths, 'preparation.json')):
                output = self.work / f'{mode}-{index}'
                output.mkdir()
                destination = output / 'header-validation' / name
                def corrupt_write(path, data):
                    return original_write(path, data + b'CORRUPTION' if path == destination else data)
                def corrupt_read(path):
                    data = original_read(path)
                    return data + b'CORRUPTION' if path == destination else data
                operation = (mock.patch.object(Path, 'write_bytes', corrupt_write) if mode == 'write'
                             else mock.patch.object(Path, 'read_bytes', corrupt_read))
                with self.subTest(mode=mode, name=name), operation:
                    with self.assertRaisesRegex(ValueError, 'readback'):
                        H.prepare(self.root, output)


if __name__ == '__main__':
    unittest.main()
