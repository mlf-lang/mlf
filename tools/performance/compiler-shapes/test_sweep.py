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
from test_contract import edit, write_cohort


class SweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(cls.enterClassContext(tempfile.TemporaryDirectory())).resolve()
        git = sweep.provenance.git
        git(cls.source, 'init', '--quiet')
        for label in ('baseline', 'candidate'):
            git(cls.source, '-c', 'user.name=Sweep fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '--quiet', '-m', label)
        cls.commit = git(cls.source, 'rev-parse', 'HEAD').decode().strip()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.args = argparse.Namespace(workdir=self.root, setup=self.root / 'setup.json',
                                      producer=None, repeats=3, endpoint='crate-fused-v1', prune_build_products=False,
                                      family=['flat_functions', 'mono_calls'], size=[8, 32],
                                      cohort_output_gib=None)
        self.args.setup.write_text(json.dumps({'complete': True, 'endpoint': self.args.endpoint,
                                               'source': str(self.source)}))
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
        repeats = int(option('--repeats'))
        self.assertEqual(repeats, 2 if self.args.repeats is None else self.args.repeats)
        self.assertNotIn('--pilot', argv)
        self.assertIn('--record-only', argv)
        write_cohort(folder.parent, folder.name, family, size, repeats=repeats, endpoint=self.args.endpoint)
        plan = sweep.analyze.load(folder / 'plan.json')
        receipt = sweep.analyze.load(folder / 'receipt.json')
        plan['source']['commit'] = self.commit
        plan['inputs']['/compiler'] = 'changed' if folder.name in self.changed_inputs else 'fixed'
        (folder / 'plan.json').write_text(json.dumps(plan))
        receipt['plan_sha256'] = sweep.analyze.sha(folder / 'plan.json')
        for run in receipt['runs']:
            pair = run['position'] // 2
            scale = 2 if run['lane'] == 'mlf' else 1
            peak = (9, 1, 7, 3, 5, 2)[pair] * scale * 2**20
            run['command']['sampled_process_tree_peak_rss_bytes'] = peak + (1 if pair == 4 else 0)
            run['command']['max_individual_child_rss_bytes'] = 33 * 2**20
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
        for key in ('mlf_seconds', 'ghc_seconds', 'mlf_over_ghc', 'mlf_peak_rss_bytes', 'ghc_peak_rss_bytes'):
            self.assertEqual(failure[key], '')
        self.assertEqual((rows[-1]['mlf_seconds'], rows[-1]['ghc_seconds'], rows[-1]['mlf_over_ghc']), ('2.2','1.0','2.2'))
        summary = (self.root / 'summary.md').read_text()
        self.assertIn('2.200 / 1.000', summary)
        self.assertEqual(summary.count(' | failed |'), 2)
        self.assertEqual(rows[0]['pruned_files'], '12')
        self.assertEqual(failure['pruned_files'], '0')
        passed = self.root / 'cohorts/flat_functions-8/legs'
        failed = self.root / 'cohorts/flat_functions-32/legs'
        self.assertEqual(list(passed.glob('*/build/program')), [])
        self.assertEqual(len(list(passed.glob('*-mlf/build/unit.mlfci'))), 3)
        self.assertEqual(len(list(passed.glob('*-mlf/query-cache-inventory.json'))), 3)
        self.assertTrue(list(failed.glob('*/build/program')))

    def test_reports_median_group_peak_for_six_builds_in_bytes_and_mib(self):
        self.args.repeats = 6
        with mock.patch.object(sweep.bench, 'resolve', return_value=({'repeats': 6}, ['flat_functions'], [8], False)), \
             mock.patch.object(sweep.command_runner, 'run_recorder', side_effect=self.recorder):
            sweep.run(self.args)
        row, = self.rows()
        self.assertEqual(row['status'], 'passed')
        self.assertEqual(row['completed_pairs'], '6')
        self.assertEqual(row['mlf_peak_rss_bytes'], '8388608.5')
        self.assertEqual(row['ghc_peak_rss_bytes'], '4194304.5')
        report = (self.root / 'summary.md').read_text()
        self.assertIn('Median elapsed time (seconds)', report)
        self.assertIn('Median sampled peak process-group RSS (MiB)', report)
        self.assertIn(f"[8.00 / 4.00 (2.000)]({row['evidence']})", report)
        growth, = json.loads((self.root / 'growth.json').read_text())['growth']
        self.assertEqual(growth['status'], 'incomplete')
        self.assertFalse(growth['checks']['all_positive_medians_lower'])
        self.assertFalse(growth['checks']['peak_rss_at_most_ghc'])
        self.assertIsNone(growth['checks']['lower_power_95'])

    def test_multisize_sweep_reports_every_check_from_qualified_pairs(self):
        self.args.family = ['flat_functions']
        self.args.size = [8, 16, 32]
        self.args.repeats = None
        with mock.patch.object(sweep.command_runner, 'run_recorder', side_effect=self.recorder), \
             mock.patch.object(sweep.fit_growth, 'REPLICATES', 12):
            sweep.run(self.args)
        self.assertEqual(self.seen, [('baseline', 0), ('flat_functions', 8),
                                     ('flat_functions', 16), ('flat_functions', 32)])
        result, = json.loads((self.root / 'growth.json').read_text())['growth']
        self.assertEqual(result['sizes'], [0, 8, 16, 32])
        self.assertEqual(result['pairs_per_size'], 2)
        self.assertEqual(set(result['checks']), set(sweep.fit_growth.CHECKS))
        self.assertEqual(result['status'], 'indeterminate')
        for check in ('lower_power_point', 'lower_power_95'):
            self.assertIsNone(result['checks'][check])
        self.assertIsNotNone(result['checks']['lower_ols_95'])
        self.assertFalse(result['checks']['peak_rss_at_most_ghc'])
        self.assertFalse(result['accepted'])
        self.assertIn('## Build performance checks', (self.root / 'summary.md').read_text())

    def test_unobserved_rss_leaves_timing_available(self):
        self.args.family = ['flat_functions']
        def recorder(argv, cwd):
            status = self.recorder(argv, cwd)
            folder = Path(argv[argv.index('--output') + 1])
            def omit_samples(receipt):
                receipt['runs'][1]['command'][sweep.analyze.RSS_SAMPLE] = 0
                receipt['runs'][3]['command'].pop(sweep.analyze.RSS_SAMPLE)
            edit(folder, omit_samples)
            return status

        with mock.patch.object(sweep.command_runner, 'run_recorder', side_effect=recorder):
            sweep.run(self.args)
        for row in self.rows():
            self.assertEqual((row['status'], row['mlf_seconds']), ('passed', '2.2'))
            self.assertEqual(row['mlf_peak_rss_bytes'], '')
            self.assertEqual(row['ghc_peak_rss_bytes'], str(7 * 2**20))
            self.assertEqual(row['mlf_over_ghc_peak_rss'], '')
        result, = json.loads((self.root / 'growth.json').read_text())['growth']
        self.assertEqual(result['status'], 'incomplete')
        self.assertIsNone(result['checks']['peak_rss_at_most_ghc'])
        self.assertIn('peak build RSS unavailable at largest size 32', result['reason'])

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

    def test_multisize_cold_dependencies_verify_per_case_and_share_the_compiler(self):
        self.args.family = ['retained_packet_dependency', 'retained_curried_job_list']
        self.args.endpoint = 'crate-plan-v1'
        self.args.setup.write_text(json.dumps({'complete': True, 'endpoint': self.args.endpoint,
                                               'source': str(self.source)}))
        with mock.patch.object(sweep.command_runner, 'run_recorder', side_effect=self.recorder):
            sweep.run(self.args)
        self.assertEqual([row['status'] for row in self.rows()], ['passed'] * 4)
        for family, count in zip(self.args.family, [1, 2]):
            folder = self.root / 'cohorts' / (family + '-32')
            plan = sweep.analyze.load(folder / 'plan.json')
            libraries = sweep.worker.dependencies(plan['cases'][0])
            self.assertEqual(len(libraries), count)
            for library in libraries:
                path = Path(library['source'])
                original = path.read_bytes()
                path.write_bytes(original + b'changed')
                with self.subTest(module=library['module']), self.assertRaisesRegex(
                        ValueError, 'unchanged pinned dependency source'):
                    sweep.analyze.analyze(folder)
                path.write_bytes(original)

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


class TrackedProvenanceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.temp = Path(tmp.name)
        self.root = self.temp / 'repo'
        self.root.mkdir()
        self.git('init', '--quiet')
        self.git('config', 'user.name', 'Sweep fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.files = {
            'README.md': b'readme\n', 'CONTRIBUTING.md': b'guide\n', 'docs/guide.md': b'text\n',
            'src/Base.hs': b'x = 1\n', 'config.json': b'{}\n', 'docs/data.tsv': b'x\n',
            'oracles/expected.md': b'1\n', 'tools/run.py': b'print(1)\n', 'value.bin': b'\0one',
        }
        for name, data in self.files.items():
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
        self.git('add', '.')
        self.git('-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'fixture')
        self.serial = 0
        self.reference = {}

    def git(self, *args):
        return sweep.provenance.git(self.root, *args)

    def capture(self):
        self.serial += 1
        folder = self.temp / str(self.serial)
        folder.mkdir()
        source = sweep.provenance.source_identity(self.root, folder)
        return folder, dict(cases=[{'source': '/generated'}], inputs={'/compiler': 'fixed', '/generated': 'case'},
                            source=source)

    def check(self, folder, plan):
        sweep.check_shared_inputs(self.root, folder, plan, self.reference)

    def test_shared_dirty_code_and_document_add_edit_delete(self):
        code = self.root / 'src/Base.hs'
        code.write_text('x = 2\n')
        self.check(*self.capture())
        self.check(*self.capture())
        tracked = self.root / 'CONTRIBUTING.md'
        tracked.write_text('edited twice\n')
        self.check(*self.capture())
        (self.root / 'docs/added.md').write_text('a new guide\n')
        self.git('add', 'docs/added.md')
        tracked.unlink()
        self.check(*self.capture())
        self.git('restore', '--source=HEAD', '--worktree', 'CONTRIBUTING.md')
        self.check(*self.capture())
        self.assertEqual(code.read_text(), 'x = 2\n')
        self.assertEqual(self.git('diff', '--cached', '--name-only').splitlines(), [b'docs/added.md'])

    def test_protected_content_modes_and_renames_reject(self):
        self.check(*self.capture())
        (self.root / 'README.md').write_text('new readme\n')
        for name in ('src/Base.hs', 'config.json', 'docs/data.tsv', 'oracles/expected.md', 'tools/run.py', 'value.bin'):
            with self.subTest(path=name):
                (self.root / name).write_bytes(self.files[name] + b'!')
                with self.assertRaisesRegex(ValueError, 'outside the documentation exception'):
                    self.check(*self.capture())
                (self.root / name).write_bytes(self.files[name])
        doc = self.root / 'docs/guide.md'
        for data in (b'\0opaque', b'\xff'):
            doc.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'outside the documentation exception'):
                self.check(*self.capture())
        doc.write_bytes(self.files['docs/guide.md'])
        doc.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'outside the documentation exception'):
            self.check(*self.capture())
        doc.unlink()
        doc.symlink_to('../config.json')
        with self.assertRaisesRegex(ValueError, 'outside the documentation exception'):
            self.check(*self.capture())
        doc.unlink()
        self.git('mv', 'tools/run.py', 'docs/tool.md')
        with self.assertRaisesRegex(ValueError, 'outside the documentation exception'):
            self.check(*self.capture())

    def test_pin_and_revision_drift_reject_even_for_prose(self):
        def pinned():
            folder, plan = self.capture()
            plan['inputs'][str(self.root / 'CONTRIBUTING.md')] = sweep.analyze.sha(self.root / 'CONTRIBUTING.md')
            return folder, plan
        self.check(*pinned())
        (self.root / 'CONTRIBUTING.md').write_text('new measured input\n')
        with self.assertRaisesRegex(ValueError, 'shared measurement inputs changed'):
            self.check(*pinned())
        self.git('add', 'CONTRIBUTING.md')
        self.git('-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'changed revision')
        with self.assertRaisesRegex(ValueError, 'source revision changed'):
            self.check(*pinned())

    def test_legacy_archive_can_move_and_survives_later_checkout_edits(self):
        self.check(*self.capture())
        (self.root / 'CONTRIBUTING.md').write_text('older documentation edit\n')
        folder, plan = self.capture()
        patch = self.git('diff', 'HEAD')
        (folder / 'source-patch.diff').write_bytes(patch)
        source = plan['source']
        del source['patch_format']
        source.update(patch_file='/original/machine/source-patch.diff', patch_bytes=len(patch),
                      patch_sha256=hashlib.sha256(patch).hexdigest())
        (self.root / 'src/Base.hs').write_text('unrelated later edit in the live checkout\n')
        self.check(folder, plan)
        self.assertEqual((self.root / 'src/Base.hs').read_text(), 'unrelated later edit in the live checkout\n')

    def test_clean_patch_requires_valid_commit_and_typed_metadata(self):
        folder, plan = self.capture()
        for fields in ({'commit': '0' * 40}, {'commit': self.git('rev-parse', 'HEAD^{tree}').decode().strip()},
                       {'patch_bytes': False}, {'patch_bytes': 0.0}, {'patch_file': 0}):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, 'invalid tracked patch evidence'):
                self.check(folder, {**plan, 'source': {**plan['source'], **fields}})

    def test_missing_corrupt_and_unparsable_archives_reject(self):
        (self.root / 'CONTRIBUTING.md').write_text('changed docs\n')
        folder, plan = self.capture()
        self.check(folder, plan)
        path = folder / 'source-patch.diff'
        valid = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'invalid tracked patch evidence'):
            self.check(folder, plan)
        path.write_bytes(b'?' * len(valid))
        with self.assertRaisesRegex(ValueError, 'invalid tracked patch evidence'):
            self.check(folder, plan)
        for data in (b'not a patch\n', valid + b'unparsed trailing text\n'):
            with self.subTest(data=data[-25:]):
                path.write_bytes(data)
                plan['source'].update(patch_bytes=len(data), patch_sha256=hashlib.sha256(data).hexdigest())
                with self.assertRaisesRegex(ValueError, 'invalid tracked patch evidence'):
                    self.check(folder, plan)
        del plan['source']['patch_bytes']
        with self.assertRaisesRegex(ValueError, 'invalid tracked patch evidence'):
            self.check(folder, plan)


if __name__ == '__main__':
    unittest.main()
