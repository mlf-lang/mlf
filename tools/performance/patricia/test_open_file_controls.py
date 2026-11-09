#!/usr/bin/env python3
"""Guarded adapter plumbing controls; these do not stand in for native CI runs."""
from pathlib import Path
import hashlib
import json
import tempfile
import types
import unittest
from unittest import mock

import run_open_file_controls as A


class Failure(ValueError):
    pass


def require(value, message):
    if not value:
        raise Failure(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PlumbingControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='c4-plumbing-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / 'source'
        self.producer = self.root / 'producer'
        self.folder = self.root / 'controls'
        for p in [self.source, self.producer / 'objects', self.folder]:
            p.mkdir(parents=True)
        self.H = types.SimpleNamespace(
            require=require, sha=sha, regular=lambda p: Path(p).resolve(),
            file_pins=lambda p: {str(x.resolve()): sha(x) for x in Path(p).rglob('*') if x.is_file()},
            load=lambda p: json.loads(Path(p).read_text()),
            check_pins=lambda pins: [require(sha(p) == h, 'changed pin') for p, h in pins.items()])
        self.inputs, self.record, self.commands = {}, {}, []
        self.auth = {'cc': {'path': '/qualified/cc'}, 'commands': [], 'object_inputs': {}}
        for name, relative in [('host', 'host/ghc/cbits/host.c'),
                               ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            source = self.source / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(('source-' + name).encode())
            original = self.producer / (name + '.o')
            original.write_bytes(('object-' + name).encode())
            log = self.producer / ('c-' + name + '.log')
            log.write_bytes(b'')
            self.auth['commands'].append({
                'argv': ['/qualified/cc', '-O2', '-std=c11', '-I' + str(self.source / 'runtime'),
                         '-c', str(source), '-o', str(original)],
                'cwd': str(self.source), 'exit_code': 0, 'log': str(log), 'log_sha256': sha(log)})
        owner = self

        class Runner:
            def __init__(self, output, limits):
                pass
            def run(self, argv, cwd, log, **kwargs):
                owner.commands.append((list(argv), str(cwd)))
                name = Path(argv[-1]).stem
                Path(argv[-1]).write_bytes((owner.producer / (name + '.o')).read_bytes())
                log.mkdir()
                (log / 'command.json').write_text(json.dumps({'argv': list(argv), 'exit_code': 0}))
                return {'exit_code': 0}
        self.H.Runner = Runner

    def verify_support(self):
        A.verify_c_support(self.H, self.root, self.source, self.producer, self.auth,
                           self.folder, self.inputs, self.record, lambda: None, {})

    def test_complete_object_inventory(self):
        p = self.producer / 'objects/Module.o'
        p.write_bytes(b'ordinary')
        self.auth['object_inputs'] = {'objects/Module.o': sha(p)}
        self.assertEqual(A.verify_producer_objects(self.H, self.producer, self.auth),
                         self.auth['object_inputs'])

    def test_stale_extra_missing_object_rejected(self):
        p = self.producer / 'objects/Module.o'
        p.write_bytes(b'ordinary')
        self.auth['object_inputs'] = {'objects/Module.o': sha(p)}
        p.write_bytes(b'stale')
        with self.assertRaises(Failure):
            A.verify_producer_objects(self.H, self.producer, self.auth)
        p.write_bytes(b'ordinary')
        extra = p.with_name('Extra.hi')
        extra.write_bytes(b'extra')
        with self.assertRaises(Failure):
            A.verify_producer_objects(self.H, self.producer, self.auth)
        extra.unlink()
        p.unlink()
        with self.assertRaises(Failure):
            A.verify_producer_objects(self.H, self.producer, self.auth)

    def test_c_reproduction_changes_only_output_and_pins_both(self):
        self.verify_support()
        self.assertEqual(len(self.commands), 2)
        for (argv, cwd), original in zip(self.commands, self.auth['commands']):
            self.assertEqual(argv[:-1], original['argv'][:-1])
            self.assertNotEqual(argv[-1], original['argv'][-1])
            self.assertEqual(cwd, original['cwd'])
            self.assertEqual(Path(argv[-1]).read_bytes(), Path(original['argv'][-1]).read_bytes())
            self.assertIn(argv[-1], self.inputs)
            self.assertIn(original['argv'][-1], self.inputs)
        self.assertTrue(self.record['reproducible_c_support'][str(self.producer)]['complete'])
        self.verify_support()
        self.assertEqual(len(self.commands), 2, 'qualified same-producer support is not rebuilt')

    def test_c_wrong_or_duplicate_command_rejected(self):
        self.auth['commands'][0]['argv'][1] = '-O0'
        with self.assertRaises(Failure):
            self.verify_support()
        self.assertEqual(self.commands, [])

    def test_c_duplicate_receipt_command_rejected(self):
        self.auth['commands'].append(dict(self.auth['commands'][0]))
        with self.assertRaises(Failure):
            self.verify_support()

    def test_c_changed_log_rejected(self):
        Path(self.auth['commands'][0]['log']).write_bytes(b'changed')
        with self.assertRaises(Failure):
            self.verify_support()

    def test_c_different_reproduced_bytes_rejected(self):
        owner = self
        class BadRunner(self.H.Runner):
            def run(self, argv, cwd, log, **kwargs):
                result = super().run(argv, cwd, log, **kwargs)
                Path(argv[-1]).write_bytes(b'different')
                return result
        self.H.Runner = BadRunner
        with self.assertRaises(Failure):
            self.verify_support()

    def test_c_changed_original_after_qualification_rejected(self):
        self.verify_support()
        (self.producer / 'host.o').write_bytes(b'changed')
        with self.assertRaises(Failure):
            self.verify_support()

    def transcript(self, entries):
        return ''.join('[%d of %d] Compiling %s ( %s, output.o )\n' %
                       (i + 1, len(entries), module, path)
                       for i, (module, path) in enumerate(entries)).encode()

    def test_exact_control_compile_origins(self):
        entries = [('FileControls', self.folder / 'FileControls.hs'),
                   ('Main', self.folder / 'Main.hs')]
        A.verify_compiled_controls(self.H, self.transcript(entries), b'', self.folder)

    def test_production_recompile_wrong_origin_and_missing_rejected(self):
        correct = [('FileControls', self.folder / 'FileControls.hs'),
                   ('Main', self.folder / 'Main.hs')]
        for entries in [correct + [('Bootstrap.Crate', self.source / 'Crate.hs')],
                        [('FileControls', self.source / 'wrong.hs'), correct[1]],
                        [correct[1]], [correct[1], correct[1]]]:
            with self.subTest(entries=entries), self.assertRaises(Failure):
                A.verify_compiled_controls(self.H, self.transcript(entries), b'', self.folder)

    def test_exact_spec_roundtrip_and_malformed_rejected(self):
        values = ['MLF-CRATE-1', 'crate λ', 'Main', 'true', A.pack(['a', 'b']), '', '/cache', '/builtin']
        self.assertEqual(A.unpack(A.pack(values)), values)
        for raw in ['no-colon', ':x', 'a:x', '3:ab']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                A.unpack(raw)

    def test_frozen_driver_fixture_and_independent_oracle_inputs(self):
        c4 = Path(A.__file__).resolve().parent.parent / 'c4-local-transaction'
        for relative, expected in A.FROZEN_INPUTS.items():
            self.assertEqual(sha(c4 / relative), expected)
        for relative, expected in A.Comparison.ORACLE_PINS.items():
            self.assertEqual(sha(A.Comparison.ORACLE_DIRECTORY / relative), expected)


if __name__ == '__main__':
    unittest.main()
