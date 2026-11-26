#!/usr/bin/env python3
"""Python-only fail-closed controls; never invoke an MLF compiler."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_guest_framework as gate


def unpack(wire):
    fields = []
    while wire:
        length, separator, payload = wire.partition(':')
        if not separator or not length.isdigit() or len(payload) < int(length):
            raise ValueError('invalid fixture crate specification')
        fields.append(payload[:int(length)])
        wire = payload[int(length):]
    return fields


class GateControls(unittest.TestCase):
    def test_pack(self):
        self.assertEqual(gate.pack(['a', 'λ', '']), '1:a1:λ0:')
    def test_extra_error_text_cannot_satisfy_negative(self):
        for text in [gate.NEGATIVE_DIAGNOSTIC+'\nParsing: unrelated failure',
                     'ModuleResolution: ambiguous name Monad',
                     'Resolution: no instance or given constraint for Monad (Bootstrap.Types.Either String)']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                gate.verify_run(dict(complete=False,exit_code=1,reason=None),1,text)
    def test_success_receipt(self):
        gate.verify_run({'complete':True,'exit_code':0,'reason':None},0,'')
    def test_expected_rejection(self):
        gate.verify_run({'complete':False,'exit_code':1,'reason':None},1,
                        gate.NEGATIVE_DIAGNOSTIC)
    def test_resource_failure_not_rejection(self):
        for receipt in [dict(complete=False,exit_code=1,reason='wall-time limit'),
                        dict(complete=False,exit_code=-9,reason=None),
                        dict(complete=True,exit_code=1,reason=None),
                        dict(complete=False,exit_code=0,reason=None)]:
            with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                gate.verify_run(receipt,1,gate.NEGATIVE_DIAGNOSTIC)
    def test_wrong_phase_or_reason_rejected(self):
        for message in ['Parsing: no instance or given constraint for MLF.Primitive.Monad Distinct.Box',
                        'Resolution: source missing', '']:
            with self.subTest(message=message), self.assertRaises(ValueError):
                gate.verify_run(dict(complete=False,exit_code=1,reason=None),1,message)
    def test_repeated_input_registration_cannot_mask_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'interface';path.write_text('original')
            recorded={};gate.remember_file(recorded,path);gate.remember_file(recorded,path)
            original=dict(recorded);path.write_text('changed')
            with self.assertRaises(ValueError):gate.remember_file(recorded,path)
            self.assertEqual(recorded,original)
    def test_manifest_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(); (root/'M.hs').write_text('module M where {}')
            manifest=root/'mlf-package.json'
            value={'format':1,'name':'fixture','version':'1','dependencies':{},'library':{'modules':{'M':'M.hs'}}}
            manifest.write_text(json.dumps(value))
            with patch.object(gate,'ROOT',root):
                self.assertEqual(gate.manifest_inputs(manifest,'fixture',{})[1], [('M',root/'M.hs')])
                for name,deps in [('wrong',{}), ('fixture',{'dep':'../dep'})]:
                    with self.assertRaises(ValueError):gate.manifest_inputs(manifest,name,deps)
    def test_exact_dependency_route_is_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'M.hs').write_text('module M where {}')
            manifest=root/'mlf-package.json'
            for deps in [{'dep':{'path':'../wrong'}},
                         {'dep':{'path':'../dep'},'extra':{'path':'../extra'}}]:
                manifest.write_text(json.dumps({'format':1,'name':'fixture',
                              'dependencies':deps,'library':{'modules':{'M':'M.hs'}}}))
                with patch.object(gate,'ROOT',root), self.subTest(deps=deps), self.assertRaises(ValueError):
                    gate.manifest_inputs(manifest,'fixture',{'dep':'../dep'})
    @unittest.skipUnless(sys.platform.startswith('linux'), 'requires Linux /proc watchdog')
    def test_watchdog_success_and_error(self):
        for status in [0,1]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                command=[sys.executable,str(gate.WATCHDOG),'--seconds','5','--address-space-mib','256',
                         '--rss-mib','128',temporary,sys.executable,'-c','raise SystemExit('+str(status)+')']
                result=subprocess.run(command,capture_output=True)
                receipt=json.loads((Path(temporary)/'bounded-receipt.json').read_text())
                self.assertEqual(result.returncode,status)
                self.assertEqual(receipt['exit_code'],status)
                self.assertEqual(receipt['complete'],status==0)
                self.assertIsNone(receipt['reason'])
    @unittest.skipUnless(sys.platform.startswith('linux'), 'requires Linux /proc watchdog')
    def test_watchdog_final_output_floor(self):
        with tempfile.TemporaryDirectory() as temporary:
            command=[sys.executable,str(gate.WATCHDOG),'--seconds','5','--address-space-mib','256',
                     '--rss-mib','128','--max-output-mib','1',temporary,sys.executable,'-c',
                     'from pathlib import Path; Path('+repr(temporary+'/big')+').write_bytes(b"x"*2097152)']
            result=subprocess.run(command,capture_output=True)
            receipt=json.loads((Path(temporary)/'bounded-receipt.json').read_text())
            self.assertEqual(result.returncode,1)
            self.assertFalse(receipt['complete'])
            self.assertIn('output growth limit',receipt['reason'])


class MainFixture:
    """Exercise real dispatch and receipt validation with a bounded-compiler stub.

    These controls do not infer language semantics from source spelling. The
    guest-framework gate executes those programs with the authenticated compiler.
    This fixture checks that its positive and negative outcomes are required and
    attributed correctly before the gate can publish a successful receipt.
    """
    outcomes = {'foundation': 0, 'framework': 0, 'standard-class': 0,
                'implicit-standard-class': 0, 'distinct-custom-class': 1}
    rejection = ('Resolution: no instance or given constraint for '
                 'MLF.Primitive.Monad Distinct.Box; ambiguous uses need a type annotation')

    def __init__(self, test):
        temporary = tempfile.TemporaryDirectory(prefix='guest-framework-control-')
        test.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.producer = self.root / 'producer'
        (self.producer / 'objects').mkdir(parents=True)
        (self.producer / 'bin').mkdir()
        obj = self.producer / 'objects/Fixture.o'
        obj.write_bytes(b'authenticated producer object')
        (self.producer / 'bin/emlf').write_bytes(b'bounded compiler stub')
        self.build_receipt = self.producer / 'receipt.json'
        self.build_receipt.write_text('{}\n')
        self.metadata = {'optimization': '2',
                         'object_inputs': {'objects/Fixture.o': hashlib.sha256(obj.read_bytes()).hexdigest()}}
        self.output = self.root / 'result'
        self.calls = []
        self.statuses = dict(self.outcomes)
        self.logs = {'distinct-custom-class': self.rejection}
        self.after_command = None

    def compile(self, command, **kwargs):
        spec = Path(command[command.index('--compile-crate') + 1])
        directory = spec.parent
        label = self.receipt()['commands'][-1]['label']
        fields = unpack(spec.read_text())
        self.calls.append(label)
        status = self.statuses[label]
        (directory / 'bounded-receipt.json').write_text(json.dumps(
            {'complete': status == 0, 'exit_code': status, 'reason': None}))
        (directory / 'build.log').write_text(self.logs.get(label, ''))
        if status == 0:
            for suffix in ('mlfci', 'mlfco'):
                (directory / 'artifact' / ('unit.' + suffix)).write_bytes(b'checked fixture artifact')
                if label == 'foundation':
                    Path(fields[-1]).with_suffix('.' + suffix).write_bytes(b'checked fixture builtin')
            (directory / 'artifact/unit.queries').write_text(json.dumps(
                {'format': 1, 'crate': fields[1], 'inferred_groups': 1, 'reused_groups': 0}))
        if self.after_command:
            self.after_command(label, directory, fields)
        return subprocess.CompletedProcess(command, status, b'', b'')

    def execute(self, selected=None):
        argv = ['test_guest_framework.py', '--build-receipt', str(self.build_receipt),
                '--output', str(self.output)]
        with patch.dict(os.environ), patch.object(sys, 'argv', argv), \
                patch.object(gate, 'authenticate_build', return_value=self.metadata), \
                patch.object(gate.subprocess, 'run', side_effect=self.compile), \
                contextlib.redirect_stdout(io.StringIO()):
            os.environ.pop('MLF_TEST_EXACT', None)
            os.environ.pop('MLF_TEST_ID_PREFIX', None)
            if selected:
                os.environ['MLF_TEST_EXACT'] = 'guest-framework/' + selected
            gate.main()
        return self.receipt()

    def receipt(self):
        return json.loads((self.output / 'receipt.json').read_text())


class MainControls(unittest.TestCase):
    def test_positive_and_nominal_negative_outcomes_are_required(self):
        fixture = MainFixture(self)
        receipt = fixture.execute()
        self.assertEqual(fixture.calls, ['foundation', 'framework', 'standard-class',
                                         'implicit-standard-class', 'distinct-custom-class'])
        self.assertEqual([row['expected_exit'] for row in receipt['commands']], [0, 0, 0, 0, 1])
        self.assertTrue(receipt['complete'])
        self.assertTrue(receipt['commands'][-1]['expected_semantic_rejection'])
        self.assertTrue(receipt['checked_artifacts_rehashed'])
        self.assertTrue(receipt['producer_reauthenticated'])
        self.assertFalse(receipt['full_native_unit'])

    def test_exact_class_selection_retains_only_foundation_prerequisite(self):
        for selected in ('standard-class', 'implicit-standard-class', 'distinct-custom-class'):
            with self.subTest(selected=selected):
                fixture = MainFixture(self)
                receipt = fixture.execute(selected)
                self.assertEqual(fixture.calls, ['foundation', selected])
                self.assertEqual(receipt['selected_ids'], ['guest-framework/' + selected])
                self.assertEqual(receipt['scope'], 'focused')
                self.assertTrue(receipt['commands'][0]['prerequisite'])
                self.assertNotIn('prerequisite', receipt['commands'][1])
                self.assertTrue(receipt['complete'])

    def test_changed_class_outcome_cannot_publish_success(self):
        for selected, actual in [('standard-class', 1), ('implicit-standard-class', 1),
                                 ('distinct-custom-class', 0)]:
            with self.subTest(selected=selected, actual=actual):
                fixture = MainFixture(self)
                fixture.statuses[selected] = actual
                with self.assertRaisesRegex(ValueError, 'unexpected compiler status'):
                    fixture.execute(selected)
                self.assertFalse(fixture.receipt()['complete'])

    def test_wrong_rejection_or_published_artifact_cannot_pass(self):
        for invalid in ('diagnostic', 'artifact'):
            with self.subTest(invalid=invalid):
                fixture = MainFixture(self)
                if invalid == 'diagnostic':
                    fixture.logs['distinct-custom-class'] = 'Parsing: unrelated error'
                else:
                    def publish_rejected(label, directory, fields):
                        if label == 'distinct-custom-class':
                            (directory / 'artifact/unit.mlfci').write_bytes(b'invalid published interface')
                    fixture.after_command = publish_rejected
                with self.assertRaises(ValueError):
                    fixture.execute('distinct-custom-class')
                self.assertFalse(fixture.receipt()['complete'])

    def test_generated_fixture_mutation_invalidates_receipt(self):
        fixture = MainFixture(self)
        def mutate_source(label, directory, fields):
            if label == 'standard-class':
                module, = unpack(fields[4])
                _, source = unpack(module)
                Path(source).write_text('changed during compilation')
        fixture.after_command = mutate_source
        with self.assertRaisesRegex(ValueError, 'generated checked inputs or artifacts changed'):
            fixture.execute('standard-class')
        self.assertFalse(fixture.receipt()['complete'])


if __name__=='__main__':unittest.main()
