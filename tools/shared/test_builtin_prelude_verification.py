#!/usr/bin/env python3
"""Finite verifier/provenance failure controls; no compiler build or semantics claim."""
from __future__ import annotations
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    path = ROOT / 'tools/shared' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = load('verify_builtin_prelude')
identity_helper = load('builtin_prelude_identity')


class BuiltinFixture:
    """Small canonical closure and explicit mock binaries for boundary controls.

    The generator embeds expected bytes independently of the file comparison;
    neither mock binary is evidence for the actual Haskell implementation.
    """
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.compiler = self.root / 'build/bin/emlf'
        self.generator = self.root / 'build/bin/builtin-prelude'
        self.output = self.root / 'build/builtin-verification'
        self.literal = b'module MLF.BuiltinPreludeData where\nbuiltin = ()\n'
        self.manifest = {
            'source_syntax': 'shared-haskell-v1', 'frontend_semantics': 'test/2',
            'builtin_interface': 'test/3', 'primitive_abi': 'test/95',
            'modules': [
                {'module': 'Example', 'path': 'source/Example.hs'},
                {'module': 'MLF.Entry.BuiltinPrelude', 'path': 'bootstrap/MLF/Entry/BuiltinPrelude.hs'},
                {'module': 'MLF.BuiltinPreludeData', 'path': verifier.CANONICAL}],
            'host_only': [], 'executables': [
                {'name': 'emlf', 'module': 'Example'},
                {'name': 'builtin-prelude', 'module': 'MLF.Entry.BuiltinPrelude'}]}
        self.file('shared-sources.json', json.dumps(self.manifest))
        self.file('source/Example.hs', 'module Example where\nvalue = ()\n')
        self.file('bootstrap/MLF/Entry/BuiltinPrelude.hs',
                  'module MLF.Entry.BuiltinPrelude where\nimport Example\n')
        self.file(verifier.CANONICAL, self.literal.decode())
        for path in verifier.configuration_paths(self.root):
            if not path.exists():
                self.file(path.relative_to(self.root), 'fixture configuration\n')
        for relative in verifier.HELPERS:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.configure()

    def file(self, relative, contents):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    def script(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!' + sys.executable + '\nimport sys\n' + body + '\n')
        path.chmod(0o755)

    def configure(self, compiler=None, generator=None):
        identity = identity_helper.source_identity(self.root)[0]
        self.script(self.compiler, compiler if compiler is not None else
            'assert sys.argv[1:] == ' + repr(['--verify-builtin-prelude', identity]) + '\n'
            'sys.stdout.buffer.write(' + repr(verifier.BANNER) + ')')
        self.script(self.generator, generator if generator is not None else
            'assert sys.argv[1:] == ' + repr([identity]) + '\n'
            'sys.stdout.buffer.write(' + repr(self.literal) + ')')

    def verify(self, timeout=10):
        return verifier.verify(self.root, self.compiler, self.generator, self.output, timeout)

    def authenticate(self, reference=None):
        if reference is None:
            reference = verifier.identified(self.output / 'receipt.json')
        return verifier.authenticate(reference, self.root, self.compiler, self.generator)


class BuiltinPreludeVerification(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mlf-builtin-verifier-control-')
        self.addCleanup(temporary.cleanup)
        self.fixture = BuiltinFixture(temporary.name)

    def receipt(self):
        return json.loads((self.fixture.output / 'receipt.json').read_text())

    def rewrite_receipt(self, receipt):
        path = self.fixture.output / 'receipt.json'
        path.write_text(json.dumps(receipt))
        return verifier.identified(path)

    def assert_incomplete(self):
        self.assertIs(self.receipt()['complete'], False)

    def test_exact_fresh_success_has_bounded_scope_and_all_pins(self):
        fixture = self.fixture
        fixture.verify()
        receipt = fixture.authenticate()
        self.assertIs(receipt['complete'], True)
        self.assertIs(receipt['toolchain_qualification'], False)
        self.assertIs(receipt['source_files_rewritten'], False)
        self.assertIs(receipt['immutable_inputs_verified_after'], True)
        self.assertEqual(receipt['source_identity'], identity_helper.source_identity(fixture.root)[0])
        self.assertEqual(set(receipt['source_identity_inputs']['modules']),
                         {'Example', 'MLF.Entry.BuiltinPrelude'})
        self.assertEqual([row['label'] for row in receipt['commands']], ['check-candidate', 'fresh-literal'])
        self.assertEqual((fixture.output / 'fresh-literal.stdout').read_bytes(), fixture.literal)
        self.assertEqual((fixture.root / verifier.CANONICAL).read_bytes(), fixture.literal)
        for path in [fixture.compiler, fixture.generator, fixture.root / verifier.CANONICAL,
                     *verifier.configuration_paths(fixture.root),
                     *(fixture.root / name for name in verifier.HELPERS)]:
            self.assertIn(str(path.resolve()), receipt['inputs'])

    def test_candidate_requires_exact_banner_empty_stderr_and_zero_exit(self):
        for name, body, message in [
            ('missing', 'pass', 'banner differs'),
            ('extra', 'sys.stdout.buffer.write(' + repr(verifier.BANNER + b'extra\n') + ')', 'banner differs'),
            ('stderr', 'sys.stdout.buffer.write(' + repr(verifier.BANNER) + '); sys.stderr.write("warning")', 'wrote stderr'),
            ('nonzero', 'sys.stdout.buffer.write(' + repr(verifier.BANNER) + '); sys.exit(4)', 'command failed')]:
            with self.subTest(name=name):
                self.fixture.configure(compiler=body)
                with self.assertRaisesRegex(ValueError, message):
                    self.fixture.verify()
                self.assert_incomplete()
                self.assertEqual(len(self.receipt()['commands']), 1)

    def test_generator_requires_exact_bytes_empty_stderr_and_zero_exit(self):
        for name, body, message in [
            ('different', 'sys.stdout.buffer.write(' + repr(self.fixture.literal + b'\n') + ')', 'literal differs'),
            ('empty', 'pass', 'literal differs'),
            ('stderr', 'sys.stdout.buffer.write(' + repr(self.fixture.literal) + '); sys.stderr.write("warning")', 'wrote stderr'),
            ('nonzero', 'sys.stdout.buffer.write(' + repr(self.fixture.literal) + '); sys.exit(4)', 'command failed')]:
            with self.subTest(name=name):
                self.fixture.configure(generator=body)
                with self.assertRaisesRegex(ValueError, message):
                    self.fixture.verify()
                self.assert_incomplete()
                self.assertEqual(len(self.receipt()['commands']), 2)

    def test_new_source_identity_is_passed_to_old_candidate_and_rejected(self):
        previous = identity_helper.source_identity(self.fixture.root)[0]
        self.fixture.file('source/Example.hs', 'module Example where\nvalue = ((), ())\n')
        current = identity_helper.source_identity(self.fixture.root)[0]
        self.assertNotEqual(previous, current)
        with self.assertRaisesRegex(ValueError, 'command failed: check-candidate'):
            self.fixture.verify()
        self.assertEqual(self.receipt()['commands'][0]['argv'][-1], current)
        self.assert_incomplete()

    def test_failed_preflight_invalidates_previous_success(self):
        self.fixture.verify()
        self.fixture.compiler.unlink()
        with self.assertRaises(FileNotFoundError):
            self.fixture.verify()
        self.assert_incomplete()
        self.assertEqual(self.receipt()['commands'], [])

    def test_generated_data_cannot_enter_fresh_preparation_closure(self):
        self.fixture.file('source/Example.hs',
                          'module Example where\nimport MLF.BuiltinPreludeData\n')
        with self.assertRaisesRegex(RuntimeError, 'depends on generated data'):
            self.fixture.verify()
        self.assert_incomplete()

    def test_literal_registration_and_duplicate_modules_are_rejected(self):
        original = copy.deepcopy(self.fixture.manifest)
        for mutation, message in [
            (lambda m: m['modules'][-1].update(path='source/Other.hs'), 'registration changed'),
            (lambda m: m['modules'].append(m['modules'][0]), 'duplicate canonical')]:
            manifest = copy.deepcopy(original)
            mutation(manifest)
            self.fixture.file('shared-sources.json', json.dumps(manifest))
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.fixture.verify()
            self.assert_incomplete()

    def test_saved_evidence_rejects_changed_sources_configs_helpers_and_binaries(self):
        self.fixture.verify()
        for path in [self.fixture.root / 'source/Example.hs',
                     self.fixture.root / 'shared-sources.json',
                     self.fixture.root / 'mlf-package.json',
                     self.fixture.root / verifier.CANONICAL,
                     *(self.fixture.root / name for name in verifier.HELPERS),
                     self.fixture.compiler, self.fixture.generator]:
            original = path.read_bytes()
            path.write_bytes(original + b'\n')
            try:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    self.fixture.authenticate()
            finally:
                path.write_bytes(original)
        self.fixture.authenticate()

    def test_saved_evidence_rejects_new_configuration_inventory(self):
        self.fixture.verify()
        self.fixture.file('libraries/new/mlf-package.json', '{}\n')
        with self.assertRaisesRegex(ValueError, 'input inventory mismatch: inputs'):
            self.fixture.authenticate()

    def test_missing_or_stale_receipt_reference_is_rejected(self):
        self.fixture.verify()
        reference = verifier.identified(self.fixture.output / 'receipt.json')
        for invalid in [None, {}, {'path': reference['path'], 'sha256': '0' * 64}]:
            with self.subTest(reference=invalid), self.assertRaises(ValueError):
                verifier.authenticate(invalid, self.fixture.root, self.fixture.compiler, self.fixture.generator)

    def test_successful_receipt_cannot_be_repointed_to_other_binary_or_logs(self):
        self.fixture.verify()
        reference = verifier.identified(self.fixture.output / 'receipt.json')
        other = self.fixture.root / 'build/bin/other-emlf'
        shutil.copyfile(self.fixture.compiler, other)
        with self.assertRaisesRegex(ValueError, 'input inventory mismatch: compiler'):
            verifier.authenticate(reference, self.fixture.root, other, self.fixture.generator)
        other_receipt = self.fixture.root / 'build/other/receipt.json'
        other_receipt.parent.mkdir()
        shutil.copyfile(reference['path'], other_receipt)
        with self.assertRaisesRegex(ValueError, 'resolved a different file'):
            self.fixture.authenticate(verifier.identified(other_receipt))

    def test_rehashed_receipt_still_requires_complete_inventory_and_commands(self):
        self.fixture.verify()
        original = self.receipt()
        mutations = [
            lambda r: r.update(complete=False),
            lambda r: r.update(immutable_inputs_verified_after=False),
            lambda r: r.update(candidate_verified=False),
            lambda r: r.update(exact_regeneration=False),
            lambda r: r.update(source_files_rewritten=True),
            lambda r: r.update(toolchain_qualification=True),
            lambda r: r.update(source_identity='builtin-source-v1:stale'),
            lambda r: r.update(source_identity_inputs={}),
            lambda r: r.update(inputs={}),
            lambda r: r.update(commands=r['commands'][:1]),
            lambda r: r['commands'][0].update(argv=[str(self.fixture.compiler), '--other-mode']),
            lambda r: r['commands'][1].update(exit_code=1),
            lambda r: r['commands'][1].update(timeout_seconds=7201),
            lambda r: r['commands'][1].update(input_pins_verified_after=False)]
        for index, mutation in enumerate(mutations):
            receipt = copy.deepcopy(original)
            mutation(receipt)
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.fixture.authenticate(self.rewrite_receipt(receipt))
        self.fixture.authenticate(self.rewrite_receipt(original))

    def test_log_rehash_cannot_hide_wrong_banner_literal_or_stderr(self):
        self.fixture.verify()
        original = self.receipt()
        for row, stream, contents in [(0, 'stdout', b'other\n'), (1, 'stdout', b'other literal\n'),
                                      (1, 'stderr', b'warning\n')]:
            receipt = copy.deepcopy(original)
            path = Path(receipt['commands'][row][stream]['path'])
            previous = path.read_bytes()
            path.write_bytes(contents)
            receipt['commands'][row][stream] = verifier.identified(path)
            try:
                with self.subTest(row=row, stream=stream), self.assertRaises(ValueError):
                    self.fixture.authenticate(self.rewrite_receipt(receipt))
            finally:
                path.write_bytes(previous)
        self.fixture.authenticate(self.rewrite_receipt(original))

    def test_input_mutation_during_candidate_is_rejected(self):
        self.fixture.configure(compiler=
            'from pathlib import Path\nPath("source/Example.hs").write_text("changed\\n")\n'
            'sys.stdout.buffer.write(' + repr(verifier.BANNER) + ')')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.fixture.verify()
        self.assert_incomplete()
        self.assertIs(self.receipt()['immutable_inputs_verified_after'], False)

    def test_new_configuration_during_candidate_is_rejected(self):
        self.fixture.configure(compiler=
            'from pathlib import Path\np = Path("libraries/new/mlf-package.json")\n'
            'p.parent.mkdir(parents=True)\np.write_text("{}\\n")\n'
            'sys.stdout.buffer.write(' + repr(verifier.BANNER) + ')')
        with self.assertRaisesRegex(ValueError, 'inventory changed during verification'):
            self.fixture.verify()
        self.assert_incomplete()

    def test_timeout_is_bounded_and_records_reaped_leader_failure(self):
        self.fixture.configure(compiler='import time\ntime.sleep(60)')
        with self.assertRaises(subprocess.TimeoutExpired):
            self.fixture.verify(timeout=0.1)
        self.assert_incomplete()
        self.assertIsInstance(self.receipt()['commands'][0]['exit_code'], int)
        self.assertNotEqual(self.receipt()['commands'][0]['exit_code'], 0)

    def test_unbounded_or_untyped_timeouts_are_rejected(self):
        for timeout in [0, -1, True, None, '10', float('inf'), float('nan'), 7201]:
            with self.subTest(timeout=timeout), self.assertRaisesRegex(ValueError, 'timeout must be bounded'):
                self.fixture.verify(timeout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
