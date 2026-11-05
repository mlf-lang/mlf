"""Fail-closed checks for direct and worker/wrapper Int64 Core proofs."""
import unittest
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


if __name__ == "__main__":
    unittest.main()
