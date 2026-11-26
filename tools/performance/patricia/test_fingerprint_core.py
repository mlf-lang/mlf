"""Int64 Core checks and qualification dispatch; native semantics run separately."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import run_fingerprint as fingerprint


class CoreProofTests(unittest.TestCase):
    def worker(self, name='unmatchedMultiplier', operations='timesInt64# plusInt64# remInt64#'):
        return '-- RHS size: {terms: 3}\nProbe.$w'+name+' = '+operations+'\n'

    def test_direct_worker_and_plain_actual_recursion(self):
        fingerprint.machine_worker(self.worker(), 'unmatchedMultiplier')
        fingerprint.machine_worker(self.worker('fingerprintStateChars').replace('$w', ''),
                                   'fingerprintStateChars', worker=False)

    def test_operation_in_another_binding_does_not_satisfy_proof(self):
        text = self.worker(operations='timesInt64# remInt64#')+self.worker('unrelated', 'plusInt64#')
        with self.assertRaisesRegex(ValueError, 'direct Int64 arithmetic missing'):
            fingerprint.machine_worker(text, 'unmatchedMultiplier')

    def test_duplicate_and_retired_workers_are_rejected(self):
        for text in [self.worker()*2, self.worker(operations='integerMul timesInt64# plusInt64# remInt64#'),
                     self.worker(operations='fingerprintIntStep timesInt64# plusInt64# remInt64#')]:
            with self.assertRaises(ValueError):
                fingerprint.machine_worker(text, 'unmatchedMultiplier')


    def test_public_direct_binding_and_qualified_names(self):
        for prefix in ['Probe.', '']:
            direct = self.worker().replace('Probe.$w', prefix)
            fingerprint.machine_worker(direct, 'unmatchedMultiplier')
            fingerprint.verify_int64_core(
                direct + direct.replace('unmatchedMultiplier', 'unmatchedModulus'))

    def forwarder(self):
        return ('-- RHS size: {terms: 8}\nProbe.unmatchedMultiplier\n'
                '  = \\ (a :: M.Int) (c :: M.Int) ->\n'
                '      case a of { ghc-internal:GHC.Internal.Int.I64# u ->\n'
                '      Probe.$wunmatchedMultiplier u c\n      }\n')

    def test_historical_worker_with_forwarding_wrapper(self):
        fingerprint.machine_worker(self.worker()+self.forwarder(), 'unmatchedMultiplier')

    def test_wrapper_must_forward_exact_original_arguments(self):
        wrapper = self.forwarder()
        cases = [
            wrapper.replace('Probe.$wunmatchedMultiplier u c',
                            'let unused = Probe.$wunmatchedMultiplier u c in unrelated u c'),
            wrapper.replace('Probe.$wunmatchedMultiplier u c',
                            'unrelated (Probe.$wunmatchedMultiplier u c)'),
            wrapper.replace('Probe.$wunmatchedMultiplier', 'Other.$wunmatchedMultiplier'),
            wrapper.replace('Probe.$wunmatchedMultiplier u c', 'Probe.$wunmatchedMultiplier c u'),
            wrapper.replace('case a of', 'case c of'),
            wrapper.replace('(c :: M.Int)', '(a :: M.Int)').replace(' u c', ' u a'),
            wrapper.replace('I64# u ->', 'I64# c ->').replace(' u c', ' c c'),
        ]
        for text in cases:
            with self.subTest(text=text), self.assertRaisesRegex(
                    ValueError, 'ambiguous Int64 Core worker'):
                fingerprint.machine_worker(self.worker()+text, 'unmatchedMultiplier')

    def test_missing_wrong_and_duplicate_binding_forms(self):
        direct = self.worker().replace('$w', '')
        cases = [
            '', self.worker('unmatchedMultiplierExtra'),
            self.worker('unmatchedMultiplier')+self.worker(),
            direct+direct,
            direct+direct.replace('-- RHS size: {terms: 3}\n', ''),
            self.worker()+direct,
            self.worker()+direct.replace(
                'timesInt64# plusInt64# remInt64#', 'wrongWorker a c'),
            self.worker()+direct.replace(
                'timesInt64# plusInt64# remInt64#', "Probe.$wunmatchedMultiplier' a c"),
        ]
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ValueError):
                fingerprint.machine_worker(text, 'unmatchedMultiplier')
        with self.assertRaises(ValueError):
            fingerprint.machine_worker(self.worker('fingerprintStateChars'),
                                       'fingerprintStateChars', worker=False)

    def test_each_operation_and_retired_path_in_each_form(self):
        for worker in [self.worker(), self.worker().replace('$w', '')]:
            for operation in ['timesInt64#', 'plusInt64#', 'remInt64#']:
                with self.subTest(operation=operation), self.assertRaisesRegex(
                        ValueError, 'direct Int64 arithmetic missing'):
                    fingerprint.machine_worker(worker.replace(operation, 'missing'),
                                               'unmatchedMultiplier')
            for retired in ['integerMul', 'integerAdd', 'integerRem', 'fingerprintIntStep']:
                with self.subTest(retired=retired), self.assertRaisesRegex(
                        ValueError, 'retired Integer narrowing path'):
                    fingerprint.machine_worker(worker+retired+'\n', 'unmatchedMultiplier')
        wrapper = self.forwarder().replace('Probe.$wunmatchedMultiplier u c',
                                           'integerMul (Probe.$wunmatchedMultiplier u c) c')
        with self.assertRaisesRegex(ValueError, 'retired Integer narrowing path'):
            fingerprint.machine_worker(self.worker()+wrapper, 'unmatchedMultiplier')

    def test_unfolding_annotation_is_not_the_binding_rhs(self):
        for symbol in ['Probe.$wunmatchedMultiplier', 'unmatchedMultiplier']:
            header = ('-- RHS size: {terms: 3}\n'+symbol+' :: Int64 -> Int64\n'
                      '[GblId, Unf=timesInt64# plusInt64# remInt64#]\n')
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                fingerprint.machine_worker(header, 'unmatchedMultiplier')
            with self.subTest(symbol=symbol), self.assertRaisesRegex(
                    ValueError, 'direct Int64 arithmetic missing'):
                fingerprint.machine_worker(header+symbol+'\n  = missing\n',
                                           'unmatchedMultiplier')

    def test_retired_rule_cannot_reappear(self):
        counts = {'mlf/fingerprintIntStep/65599': 0, 'mlf/fingerprintIntStep/131': 0}
        for optimization in ['0', '2']:
            fingerprint.verify_no_retired_rules(counts, optimization)
        counts['mlf/fingerprintIntStep/131'] = 1
        with self.assertRaises(ValueError):
            fingerprint.verify_no_retired_rules(counts, '2')


class QualificationControls(unittest.TestCase):
    """Exercise the real dispatcher and receipt checks with bounded stage doubles."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'source'
        self.producer = self.root / 'producer'
        self.controls = self.root / 'controls'
        self.out = self.root / 'output'
        (self.source / 'host/ghc').mkdir(parents=True)
        (self.source / 'host/ghc/Host.hs').write_text('current host source\n')
        (self.producer / 'objects').mkdir(parents=True)
        self.object = self.producer / 'objects/Module.o'
        self.object.write_bytes(b'ordinary producer object')
        (self.producer / 'receipt.json').write_text('{}\n')
        shutil.copytree(fingerprint.CONTROLS, self.controls)

        def sha(path):
            return hashlib.sha256(Path(path).read_bytes()).hexdigest()

        def check_pins(pins):
            for path, digest in pins.items():
                fingerprint.require(sha(path) == digest, 'input changed')

        self.build = {'host_inputs': {}, 'object_inputs': {'objects/Module.o': sha(self.object)}}
        self.guard = types.SimpleNamespace(
            authenticate=Mock(return_value=self.build), sha=sha,
            load=lambda path: json.loads(path.read_text()),
            save=lambda path, value: path.write_text(json.dumps(value)), check_pins=check_pins)
        self.stages = []

        def probe(H, source, controls, out, build, host_hashes, expectations, opt, run):
            self.stages.append('current-O' + opt)
            return {'optimization': opt, 'complete': True}

        def separate(H, source, producer, out, build, object_hashes, run):
            self.stages.append('actual-separate')
            return {'only_Separate_recompiled': True}

        self.probe = self.enterContext(patch.object(fingerprint, 'run_probe', side_effect=probe))
        self.separate = self.enterContext(patch.object(fingerprint, 'run_separate', side_effect=separate))

    def qualify(self, planned):
        return fingerprint.qualify(self.guard, self.source, self.producer, self.out,
                                   planned, controls=self.controls)

    def receipt(self):
        return json.loads((self.out / 'checks/receipt.json').read_text())

    def test_complete_dispatch_preserves_stages_and_input_checks(self):
        result = self.qualify(fingerprint.LABELS)
        self.assertEqual(self.stages, ['current-O0', 'current-O2', 'actual-separate'])
        self.assertEqual(result['checks'], result['planned_checks'])
        self.assertTrue(result['complete'])
        self.assertTrue(result['immutable_inputs_verified_after'])
        self.assertTrue(result['producer_outputs_immutable'])
        self.assertEqual(self.guard.authenticate.call_count, 2)
        self.assertEqual(self.receipt(), result)

    def test_exact_selection_runs_only_the_selected_stage(self):
        for label in fingerprint.LABELS:
            with self.subTest(label=label):
                self.out = self.root / label
                self.stages.clear()
                result = self.qualify([label])
                self.assertEqual(self.stages, [label])
                self.assertEqual(result['checks'], [label])
                self.assertEqual('actual_source' in result, label == 'actual-separate')
                self.assertEqual(len(result['runs']), int(label != 'actual-separate'))

    def test_failed_stage_stops_dispatch_and_keeps_incomplete_receipt(self):
        self.probe.side_effect = [{'optimization': '0'}, ValueError('compiler failed')]
        with self.assertRaisesRegex(ValueError, 'compiler failed'):
            self.qualify(fingerprint.LABELS)
        self.separate.assert_not_called()
        result = self.receipt()
        self.assertFalse(result['complete'])
        self.assertEqual(result['checks'], ['current-O0'])
        self.assertIn('compiler failed', result['error'])

    def test_changed_control_input_is_rejected_after_execution(self):
        def change(*args):
            (self.controls / 'Oracle.hs').write_text('changed during qualification\n')
            return {'optimization': '0'}
        self.probe.side_effect = change
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.qualify(['current-O0'])
        self.assertFalse(self.receipt()['complete'])

    def test_changed_producer_object_is_rejected_after_execution(self):
        def change(*args):
            self.object.write_bytes(b'changed ordinary object')
            return {'optimization': '0'}
        self.probe.side_effect = change
        with self.assertRaisesRegex(ValueError, 'qualified producer objects changed'):
            self.qualify(['current-O0'])
        self.assertFalse(self.receipt()['complete'])


if __name__ == "__main__":
    unittest.main()
