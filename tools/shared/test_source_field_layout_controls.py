#!/usr/bin/env python3
"""Cheap runner controls; no compiler build, native run, or real object mutation."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_source_field_layouts as gate

# Independent reviewed completion oracle, not read from the fixture or gate.
LABELS = [
    'fresh producer ownData has exactly canonical Int field',
    'source plan uses identical canonical ownData',
    'legacy lowering recipe uses identical canonical ownData',
    'producer source SCC cache is cold',
    'producer public and lowered layouts agree exactly',
    'construction, constructor-as-value and extraction have canonical contracts',
    'producer targets pass production/frozen/roundtrip/erasure',
    'producer warm source cache reuses every fragment',
    'producer cold/warm objects are byte-identical',
    'saved producer preserves exact canonical layout',
    'actual fallback query route has cold/warm reuse',
    'fallback public/lowered layouts remain canonical',
    'fallback constructor and extraction schemes equal source SCC schemes',
    'fallback targets pass production/frozen/roundtrip/erasure and warm parity',
    'metadata-only consumer uses unchanged imported layout',
    'consumer source SCC cache has cold/warm reuse',
    'consumer cold/warm bytes and imported schemes remain exact',
    'saved producer/consumer link, check, roundtrip and erase to 42',
    'manual legacy import retains quantified constructor contract',
    'manual legacy class signature and dictionary preserve dead quantifier',
    'mixed source boundary normalizes only its fresh local declaration',
    'mixed fallback recipe also retains exact imported dictionary and datatype',
    'mixed exact-context source cache has cold/warm reuse',
    'mixed owned artifact does not re-export or rewrite imported layouts',
    'legacy selector entry adaptation rejects instead of rewriting checked ABI',
    'legacy/local saved library links with both exact checked layouts',
    'mixed fallback query route has cold/warm reuse',
    'mixed fallback preserves legacy ABI through checked library linking',
    'imported metadata, semantic fingerprint and class ABI remain byte-exact',
    'ordinary imported-selector entry adaptation succeeds with exact checked ABI',
    'fresh-source canonicalizer validates original ill-kinded fields',
    'fresh-source canonicalizer validates original checked context',
    'checked-layout key retains dead quantifiers',
    'quantified header / canonical payload: exact cache context rejects',
    'quantified header / canonical payload: encoded cache rejects',
    'quantified header / canonical payload: expected cache metadata rejects opposite layout',
    'quantified header / canonical payload: pooled object rejects',
    'quantified header / canonical payload: linker rejects exact header/payload mismatch',
    'quantified header / canonical payload: source/lowered metadata mismatch rejects',
    'canonical header / quantified payload: exact cache context rejects',
    'canonical header / quantified payload: encoded cache rejects',
    'canonical header / quantified payload: expected cache metadata rejects opposite layout',
    'canonical header / quantified payload: pooled object rejects',
    'canonical header / quantified payload: linker rejects exact header/payload mismatch',
    'canonical header / quantified payload: source/lowered metadata mismatch rejects',
    'fresh source class parser retains leading and nested dead method forall',
    'fresh source class own header is canonical before planning',
    'fresh source class plan dictionary is canonical before cache keys',
    'fresh source class fallback dictionary uses the same canonical contract',
    'fresh source class producer cold/warm artifacts are byte-identical',
    'fresh source class emitted header dictionary and selector schemes agree',
    'fresh source class saved producer preserves canonical ABI',
    'fresh source class metadata-only consumer retains canonical imported dictionary',
    'fresh source class consumer cold/warm artifacts are byte-identical',
    'fresh source class saved method applications check and evaluate to 42',
]
TERMINAL = ('item4 source field layouts: passed (55 checks; source/fallback, '
            'saved imports, cold/warm, exact legacy ABI, bidirectional forgery rejection, fresh source classes)')


def wire(labels=LABELS, banner=TERMINAL):
    return ('\n'.join(['PASS ' + label for label in labels] + [banner]) + '\n').encode()


class InventoryControls(unittest.TestCase):
    def test_independent_exact_55_labels_and_banner(self):
        self.assertEqual(len(LABELS), 55)
        self.assertEqual(len(set(LABELS)), 55)
        gate.verify_inventory(wire())

    def test_missing_extra_duplicate_reordered_partial_and_banner_rejected(self):
        reordered = LABELS[:]
        reordered[0], reordered[1] = reordered[1], reordered[0]
        for name, output in [
            ('missing', wire(LABELS[:-1])),
            ('extra', wire(LABELS + ['unreviewed new observation'])),
            ('duplicate', wire(LABELS[:-1] + [LABELS[0]])),
            ('reordered', wire(reordered)),
            ('partial', b'PASS ' + LABELS[0].encode() + b'\n'),
            ('missing banner', ('\n'.join('PASS ' + x for x in LABELS) + '\n').encode()),
            ('wrong banner', wire(banner=TERMINAL.replace('55 checks', '54 checks'))),
            ('unexpected diagnostic', wire() + b'warning: still incomplete\n'),
            ('invalid UTF-8', b'\xff'),
            ('CRLF normalization', wire().replace(b'\n', b'\r\n')),
            ('missing terminal newline', wire()[:-1]),
        ]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                gate.verify_inventory(output)

    def test_mutating_gate_oracle_does_not_change_independent_control(self):
        with patch.object(gate, 'EXPECTED_CHECKS', list(reversed(LABELS))):
            with self.assertRaises(ValueError):
                gate.verify_inventory(wire())
        with patch.object(gate, 'BANNER', 'unreviewed replacement'):
            with self.assertRaises(ValueError):
                gate.verify_inventory(wire())


class RunnerControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='source-field-layout-controls-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.producer_dir = self.root / 'producer'
        (self.producer_dir / 'objects').mkdir(parents=True)
        self.receipt = self.producer_dir / 'receipt.json'
        self.receipt.write_text('{"complete": true}\n')
        self.output = self.root / 'output'
        self.object = self.producer_dir / 'objects' / 'Example.o'
        self.object.write_bytes(b'independent fake object')
        interface = self.producer_dir / 'objects' / 'Example.hi'
        interface.write_bytes(b'independent fake interface')
        self.producer = {'optimization': '2', 'ghc': {'path': 'mock-ghc'},
                         'cc': {'path': 'mock-cc'}, 'object_inputs': {
                             'objects/Example.o': gate.sha(self.object),
                             'objects/Example.hi': gate.sha(interface)}}

    def invoke(self, extra=(), output=None):
        argv = ['test_source_field_layouts.py', '--build-receipt', str(self.receipt),
                '--output', str(output or self.output), *extra]
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            gate.main()

    def saved(self):
        return json.loads((self.output / 'receipt.json').read_text())

    def fake_runner(self, effect=None):
        def run(name, command, **_):
            command = list(map(str, command))
            if name != 'source-field-layouts':
                for option in ['-o', '-ohi']:
                    if option in command:
                        Path(command[command.index(option) + 1]).write_bytes(name.encode())
            if effect is not None:
                effect(name)
            stdout = wire() if name == 'source-field-layouts' else b''
            return subprocess.CompletedProcess(command, 0, stdout, b'')
        return Mock(run=Mock(side_effect=run))

    def test_invalid_timeouts_refused_before_authentication_or_output(self):
        for option, value in [('--build-timeout', '0'), ('--build-timeout', '301'),
                              ('--run-timeout', '0'), ('--run-timeout', '1201')]:
            with self.subTest(option=option, value=value), \
                    patch.object(gate, 'authenticate_build') as authenticate, \
                    self.assertRaises(SystemExit) as raised:
                self.invoke([option, value])
            self.assertEqual(raised.exception.code, 2)
            authenticate.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_overlapping_outputs_refused_before_authentication(self):
        for output in [self.producer_dir, self.producer_dir / 'nested', self.root]:
            with self.subTest(output=output), patch.object(gate, 'authenticate_build') as authenticate, \
                    self.assertRaises(SystemExit) as raised:
                self.invoke(output=output)
            self.assertEqual(raised.exception.code, 2)
            authenticate.assert_not_called()
        self.assertFalse((self.producer_dir / 'nested').exists())

    def test_failed_producer_authentication_never_compiles_and_is_incomplete(self):
        runner = self.fake_runner()
        with patch.object(gate, 'authenticate_build', side_effect=ValueError('stale producer')), \
                patch.object(gate, 'CommandRunner', return_value=runner), self.assertRaises(ValueError):
            self.invoke()
        runner.run.assert_not_called()
        self.assertFalse(self.saved()['complete'])
        self.assertEqual(self.saved()['status'], 'failed')

    def test_object_mutation_blocks_execution_and_invalidates_receipt(self):
        def mutate(name):
            if name == 'compile-fixture':
                self.object.write_bytes(b'changed fake object')
        runner = self.fake_runner(mutate)
        with patch.object(gate, 'authenticate_build', return_value=self.producer), \
                patch.object(gate, 'CommandRunner', return_value=runner), self.assertRaises(ValueError):
            self.invoke()
        self.assertNotIn('source-field-layouts', [call.args[0] for call in runner.run.call_args_list])
        self.assertFalse(self.saved()['complete'])
        self.assertEqual(self.saved()['status'], 'invalidated')
        self.assertIn('object/interface changed', self.saved()['integrity_error'])

    def test_receipt_mutation_after_run_is_not_success(self):
        def mutate(name):
            if name == 'source-field-layouts':
                self.receipt.write_text('{"different": true}\n')
        with patch.object(gate, 'authenticate_build', return_value=self.producer), \
                patch.object(gate, 'CommandRunner', return_value=self.fake_runner(mutate)), \
                self.assertRaises(ValueError):
            self.invoke()
        self.assertFalse(self.saved()['complete'])
        self.assertEqual(self.saved()['status'], 'invalidated')
        self.assertIn('receipt changed', self.saved()['integrity_error'])

    def test_timeout_failure_keeps_receipt_incomplete(self):
        def fail(name):
            if name == 'source-field-layouts':
                raise RuntimeError('source-field-layouts exceeded 1 seconds')
        with patch.object(gate, 'authenticate_build', return_value=self.producer), \
                patch.object(gate, 'CommandRunner', return_value=self.fake_runner(fail)), \
                self.assertRaises(RuntimeError):
            self.invoke()
        self.assertFalse(self.saved()['complete'])
        self.assertEqual(self.saved()['status'], 'failed')
        self.assertTrue(self.saved()['objects_verified_after'])
        self.assertTrue(self.saved()['source_toolchain_verified_after'])

    def test_success_reauthenticates_and_preserves_fake_objects(self):
        original = gate.sha(self.object)
        runner = self.fake_runner()
        with patch.object(gate, 'authenticate_build', return_value=self.producer) as authenticate, \
                patch.object(gate, 'CommandRunner', return_value=runner):
            self.invoke()
        self.assertGreaterEqual(authenticate.call_count, 4)
        self.assertEqual(gate.sha(self.object), original)
        record = self.saved()
        self.assertTrue(record['complete'])
        self.assertEqual(record['passing_checks'], 55)
        self.assertEqual(record['passing_inventory'], LABELS)
        self.assertTrue(record['source_toolchain_verified_after'])
        self.assertTrue(record['objects_verified_after'])
        commands = [call.args[0] for call in runner.run.call_args_list]
        self.assertEqual(commands, ['compile-fixture', 'compile-host', 'compile-supervisor',
                                    'link-fixture', 'source-field-layouts'])
        fixture_command = list(map(str, runner.run.call_args_list[0].args[1]))
        self.assertIn('-c', fixture_command)
        self.assertNotIn('--make', fixture_command)
        self.assertNotIn('-fforce-recomp', fixture_command)
        for flag in ['-O2', '-fpedantic-bottoms', '-fno-state-hack',
                     '-i' + str(self.producer_dir / 'objects')]:
            self.assertIn(flag, fixture_command)
        for index, source in [(1, gate.ROOT / 'host/ghc/cbits/host.c'),
                              (2, gate.ROOT / 'runtime/mlf_process_supervisor.c')]:
            command = list(map(str, runner.run.call_args_list[index].args[1]))
            self.assertIn(str(source), command)
            self.assertIn('-c', command)
            self.assertTrue(Path(command[command.index('-o') + 1]).is_relative_to(self.output))


if __name__ == '__main__':
    unittest.main()
