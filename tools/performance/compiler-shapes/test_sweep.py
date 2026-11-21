import argparse
import csv
import hashlib
import json
import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock

import sweep
sys.path.insert(0, str(sweep.bench.ROOT / 'tools'))
from developer import process
from test_contract import write_cohort


class SweepTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.args = argparse.Namespace(workdir=self.root, setup=self.root / 'setup.json',
                                      producer=None, repeats=3, endpoint='crate-fused-v1', prune_build_products=False,
                                      family=['flat_functions', 'mono_calls'], size=[8, 32],
                                      cohort_output_gib=None)
        self.args.setup.write_text(json.dumps({'complete': True, 'endpoint': self.args.endpoint}))
        self.seen = []
        self.fail = {}
        self.changed_inputs = set()

    def recorder(self, argv, cwd):
        def option(name):
            return argv[argv.index(name) + 1]
        family = option('--family')
        size = 0 if family == 'baseline' else int(option('--size'))
        folder = Path(option('--output'))
        self.seen.append((family, size))
        self.assertEqual(cwd, sweep.bench.ROOT)
        self.assertEqual(option('--repeats'), '3')
        self.assertNotIn('--pilot', argv)
        write_cohort(folder.parent, folder.name, family, size, endpoint=self.args.endpoint)
        plan = sweep.analyze.load(folder / 'plan.json')
        receipt = sweep.analyze.load(folder / 'receipt.json')
        plan['inputs'] = {plan['cases'][0]['source']: 'source',
                          '/compiler': 'changed' if folder.name in self.changed_inputs else 'fixed'}
        (folder / 'plan.json').write_text(json.dumps(plan))
        receipt['plan_sha256'] = sweep.analyze.sha(folder / 'plan.json')
        for run in receipt['runs']:
            leg = folder / 'legs' / f"{run['position']:03d}-{folder.name}-{run['lane']}"
            build = leg / 'build'
            build.mkdir(parents=True)
            for name in ['program', 'Main.o', 'Main.hi', 'unit.ll', 'unit.mlfci', 'unit.mlfco']:
                (build / name).write_bytes(name.encode())
            run['executable_sha256'] = hashlib.sha256(b'program').hexdigest()
        if folder.name in self.fail:
            receipt.update(complete=True, all_cases_passed=False, runs=receipt['runs'][:3])
            failure = {'case': folder.name, 'position': 3, 'lane': 'mlf', 'error': 'wrapper failed'}
            receipt['failures'] = [failure]
            build = folder / 'legs' / f'003-{folder.name}-mlf' / 'build'
            (build / 'stages.json').write_text(json.dumps({'stages': [{'name': 'source-to-llvm', 'exit_code': 1}]}))
            (build / 'source-to-llvm.stderr').write_text(self.fail[folder.name])
        (folder / 'receipt.json').write_text(json.dumps(receipt))
        return 0

    def rows(self):
        with (self.root / 'summary.csv').open(newline='') as stream:
            return list(csv.DictReader(stream))

    def test_resolves_one_family_at_a_time_and_reports_failures_without_partial_medians(self):
        self.fail['flat_functions-32'] = 'could not resolve overloaded function'
        self.args.prune_build_products = True
        with mock.patch.object(sweep.bench, 'resolve', return_value=({'repeats': 3}, self.args.family, self.args.size, False)), \
             mock.patch.object(sweep.command_runner, 'run_recorder', side_effect=self.recorder), self.assertRaises(SystemExit) as exc:
            sweep.run(self.args)
        self.assertEqual(exc.exception.code, 1)
        self.assertEqual(self.seen, [('flat_functions', 8), ('flat_functions', 32), ('mono_calls', 8), ('mono_calls', 32)])
        rows = self.rows()
        self.assertEqual([r['status'] for r in rows], ['passed', 'failed', 'passed', 'passed'])
        failure = rows[1]
        self.assertEqual(failure['completed_pairs'], '1')
        self.assertEqual(failure['lane'], 'mlf')
        self.assertIn(self.fail['flat_functions-32'], failure['reason'])
        self.assertTrue((self.root / failure['evidence']).is_file())
        self.assertEqual([failure[k] for k in ('mlf_seconds','ghc_seconds','mlf_over_ghc')], ['', '', ''])
        self.assertEqual((rows[-1]['mlf_seconds'], rows[-1]['ghc_seconds'], rows[-1]['mlf_over_ghc']), ('2.2','1.0','2.2'))
        self.assertIn('2.200 / 1.000', (self.root / 'summary.md').read_text())
        self.assertEqual(rows[0]['pruned_files'], '12')
        self.assertEqual(failure['pruned_files'], '0')
        passed = self.root / 'cohorts/flat_functions-8/legs'
        failed = self.root / 'cohorts/flat_functions-32/legs'
        self.assertEqual(list(passed.glob('*/build/program')), [])
        self.assertEqual(len(list(passed.glob('*-mlf/build/unit.mlfci'))), 3)
        self.assertEqual(len(list(passed.glob('*-mlf/query-cache-inventory.json'))), 3)
        self.assertTrue(list(failed.glob('*/build/program')))

    def test_fresh_sweep_prepares_only_missing_inputs(self):
        self.args.setup = None
        producer = self.root / 'producer'
        setup = self.root / 'setup/setup.json'
        with mock.patch.object(process, 'run_build', return_value=0) as bootstrap, \
             mock.patch.object(sweep.bench, 'run') as run:
            self.assertEqual(sweep.bench.sweep_setup(self.args), setup)
            bootstrap.assert_called_once()
            self.assertIn('--bootstrap-only', bootstrap.call_args.args[0])
            self.assertIn(producer, bootstrap.call_args.args[0])
            run.assert_called_once()
            self.assertIn('--build-builtin', run.call_args.args[0])
            self.assertIn(producer, run.call_args.args[0])
            run.reset_mock()
            self.args.producer = self.root / 'existing producer'
            self.assertEqual(sweep.bench.sweep_setup(self.args), setup)
            run.assert_called_once()
            self.assertIn(self.args.producer, run.call_args.args[0])
            run.reset_mock()
            setup.parent.mkdir()
            setup.write_text(json.dumps({'producer': str(self.args.producer)}))
            self.assertEqual(sweep.bench.sweep_setup(self.args), setup)
            run.assert_not_called()
            self.args.producer = producer
            with self.assertRaisesRegex(SystemExit, 'another producer'):
                sweep.bench.sweep_setup(self.args)
            run.assert_not_called()
            bootstrap.assert_called_once()

    def test_missing_explicit_setup_and_invalid_selection_do_not_prepare(self):
        self.args.setup.unlink()
        with mock.patch.object(sweep.bench, 'run') as run:
            with self.assertRaisesRegex(SystemExit, 'missing setup'):
                sweep.run(self.args)
            self.args.setup = None
            self.args.size = [0]
            with self.assertRaisesRegex(SystemExit, 'size'):
                sweep.run(self.args)
            run.assert_not_called()

    def test_baseline_runs_once_and_changed_inputs_are_reported(self):
        self.changed_inputs.add('flat_functions-32')
        with mock.patch.object(sweep.bench, 'resolve', return_value=({'repeats': 3}, ['flat_functions'], [8,32], True)), \
             mock.patch.object(sweep.command_runner, 'run_recorder', side_effect=self.recorder), self.assertRaises(SystemExit):
            sweep.run(self.args)
        self.assertEqual(self.seen, [('baseline', 0), ('flat_functions', 8), ('flat_functions', 32)])
        rows = self.rows()
        self.assertEqual(rows[-1]['status'], 'failed')
        self.assertIn('inputs changed', rows[-1]['reason'])
        self.assertEqual(rows[-1]['mlf_seconds'], '')

    def test_interruption_does_not_start_next_family_or_reuse_partial_evidence(self):
        with mock.patch.object(sweep.bench, 'resolve', return_value=({'repeats': 3}, self.args.family, [8], False)), \
             mock.patch.object(sweep.command_runner, 'run_recorder', side_effect=KeyboardInterrupt) as recorder:
            with self.assertRaises(KeyboardInterrupt):
                sweep.run(self.args)
            self.assertEqual(recorder.call_count, 1)
            self.assertEqual([r['status'] for r in self.rows()], ['running', 'pending'])
            with self.assertRaisesRegex(SystemExit, 'fresh'):
                sweep.run(self.args)
            self.assertEqual(recorder.call_count, 1)


if __name__ == '__main__':
    unittest.main()
