#!/usr/bin/env python3
"""Contract tests for the compiler shape benchmark. No compiler is required.

These tests use synthetic receipts to prove that the analyzer refuses missing,
duplicate, non-finite, failed, qualified-only and incompatible data, and that the
frozen schedule stays balanced.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402
import bench  # noqa: E402
import run as runner  # noqa: E402

STAGES = ['source-to-checked', 'checked-to-llvm', 'llvm-to-executable']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_cohort(root, label='screen', family='flat_functions', size=8, repeats=3,
                 mlf_seconds=(2.0, 2.2, 2.4), ghc_seconds=(1.0, 1.0, 1.1),
                 endpoint='crate-bootstrap-v1', host='test-host'):
    folder = Path(root) / label
    folder.mkdir(parents=True)
    source = folder / 'source'
    source.mkdir()
    program = source / 'Main.hs'
    program.write_text('entry x = x\n')
    case = {'id': family + '-' + str(size), 'family': family, 'size': size,
            'source': str(program.resolve()), 'source_sha256': digest(program),
            'source_bytes': program.stat().st_size, 'inputs': [-1, 0, 7],
            'expected_stdout': ['-1\n', '0\n', '7\n']}
    schedule = []
    for index in range(repeats):
        for lane in ['ghc', 'mlf']:
            schedule.append({'case': case['id'], 'position': index * 2 + (lane == 'mlf'), 'lane': lane})
    plan = {'benchmark': {'schema': 2, 'suite': 'compiler-shapes', 'suite_version': 2,
                          'cohort': label, 'endpoint': {'id': endpoint, 'status': 'measured',
                          'summary': 'synthetic endpoint'}, 'repeats': repeats,
                          'families': [family], 'sizes': [size], 'cells': 1,
                          'timed_compilations': len(schedule), 'claim_limits': ['synthetic']},
            'source': {'commit': '0' * 40, 'branch': 'test', 'dirty': False,
                       'patch_sha256': hashlib.sha256(b'').hexdigest()},
            'toolchain': {'ghc': {'path': '/ghc', 'version': '9.14.1'},
                          'clang': {'path': '/clang', 'version': 'clang test'},
                          'producer': {'path': '/producer', 'receipt_sha256': 'a' * 64, 'emlf_sha256': 'b' * 64},
                          'builtin': {'/builtin.mlfci': 'c' * 64, '/builtin.mlfco': 'd' * 64}},
            'host': {'platform': host, 'machine': 'test-mcu'}, 'cases': [case], 'schedule': schedule}
    (folder / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    runs = []
    for item in schedule:
        times = mlf_seconds if item['lane'] == 'mlf' else ghc_seconds
        wall = times[item['position'] // 2 if item['position'] // 2 < len(times) else 0]
        stages = [{'name': name, 'wall_seconds': wall / 3, 'user_seconds': wall / 4,
                   'system_seconds': wall / 20} for name in STAGES] if item['lane'] == 'mlf' else []
        runs.append({'case': case['id'], 'position': item['position'], 'lane': item['lane'], 'complete': True,
                     'output_correct': True, 'fresh': 1 if item['lane'] == 'mlf' else None,
                     'reused': 0 if item['lane'] == 'mlf' else None, 'max_group_members': 1,
                     'raw_compared_with_first_mlf_leg': item['lane'] == 'mlf' and item['position'] > 1,
                     'executable_sha256': 'e' * 64, 'oracle_inputs': [-1, 0, 7],
                     'stages': {'complete': True, 'stages': stages},
                     'command': {'complete': True, 'timed_target_leg': True, 'exit_code': 0, 'reason': None,
                                 'wall_seconds': wall, 'child_user_seconds': wall / 4,
                                 'child_system_seconds': wall / 20, 'started_utc': '2026-10-31T00:00:00Z'}})
    receipt = {'complete': True, 'all_cases_passed': True, 'failures': [],
               'plan_sha256': digest(folder / 'plan.json'), 'runs': runs}
    (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    for index, item in enumerate(schedule):
        if item['lane'] == 'mlf':
            leg = folder / 'legs' / ('%03d-' % index + case['id'] + '-mlf')
            leg.mkdir(parents=True)
            (leg / 'query-cache-inventory.json').write_text(json.dumps({'q.mlfq': {'bytes': 10, 'sha256': 'f' * 64}}))
    return folder


def edit(folder, mutate):
    path = Path(folder) / 'receipt.json'
    receipt = json.loads(path.read_text())
    mutate(receipt)
    path.write_text(json.dumps(receipt, indent=2) + '\n')


class ScheduleTests(unittest.TestCase):
    def test_balanced_pairs(self):
        self.assertEqual(runner.lanes_for(0, 3), ['ghc', 'mlf', 'mlf', 'ghc', 'ghc', 'mlf'])
        self.assertEqual(runner.lanes_for(1, 3), ['mlf', 'ghc', 'ghc', 'mlf', 'mlf', 'ghc'])
        starts = [runner.lanes_for(index, 3)[0] for index in range(6)]
        self.assertEqual(starts.count('ghc'), starts.count('mlf'))

    def test_default_matrix_shape(self):
        matrix, families, sizes, baseline = bench.resolve('default', None, None)
        self.assertEqual(len(families), 10)
        self.assertEqual(sizes, [8, 32, 128])
        self.assertTrue(baseline)
        self.assertEqual(bench.compile_count(len(families) * len(sizes) + 1, matrix['repeats']), 186)

    def test_local_functions_is_opt_in(self):
        _, families, _, _ = bench.resolve('default', None, None)
        self.assertNotIn('local_functions', families)
        _, chosen, _, _ = bench.resolve('default', ['local_functions'], [512])
        self.assertEqual(chosen, ['local_functions'])

    def test_unmeasured_endpoint_is_rejected(self):
        with self.assertRaises(SystemExit):
            bench.measured_endpoint('emlf-source-v1')


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_accepts_complete_cohort(self):
        folder = write_cohort(self.root)
        rows, plan, receipt, samples = analyze.analyze(folder)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(samples), 6)
        self.assertEqual(rows[0]['mlf_over_ghc'], 2.2 / 1.0)
        self.assertEqual(rows[0]['fresh'], 1)

    def test_rejects_missing_sample(self):
        folder = write_cohort(self.root)
        edit(folder, lambda r: r['runs'].pop())
        with self.assertRaisesRegex(ValueError, 'missing or duplicate'):
            analyze.analyze(folder)

    def test_rejects_duplicate_sample(self):
        folder = write_cohort(self.root)
        edit(folder, lambda r: r['runs'].append(dict(r['runs'][0])))
        with self.assertRaisesRegex(ValueError, 'missing or duplicate'):
            analyze.analyze(folder)

    def test_rejects_nonfinite_timing(self):
        folder = write_cohort(self.root)
        edit(folder, lambda r: r['runs'][0]['command'].update(wall_seconds=float('inf')))
        with self.assertRaisesRegex(ValueError, 'finite nonnegative'):
            analyze.analyze(folder)

    def test_rejects_reused_groups(self):
        folder = write_cohort(self.root)
        def mutate(receipt):
            for run in receipt['runs']:
                if run['lane'] == 'mlf':
                    run['reused'] = 1
                    break
        edit(folder, mutate)
        with self.assertRaisesRegex(ValueError, 'fresh MLF target'):
            analyze.analyze(folder)

    def test_rejects_failed_cohort(self):
        folder = write_cohort(self.root)
        edit(folder, lambda r: r.update(all_cases_passed=False, failures=[{'case': 'x'}]))
        with self.assertRaisesRegex(ValueError, 'do not silently omit failures'):
            analyze.analyze(folder)

    def test_rejects_qualification_samples(self):
        folder = write_cohort(self.root)
        edit(folder, lambda r: r['runs'][0]['command'].update(timed_target_leg=False))
        with self.assertRaisesRegex(ValueError, 'not performance samples'):
            analyze.analyze(folder)

    def test_rejects_plan_digest_mismatch(self):
        folder = write_cohort(self.root)
        (folder / 'plan.json').write_text((folder / 'plan.json').read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'frozen plan digest'):
            analyze.analyze(folder)

    def test_rejects_changed_source(self):
        folder = write_cohort(self.root)
        (folder / 'source' / 'Main.hs').write_text('entry x = x + 1\n')
        with self.assertRaisesRegex(ValueError, 'unchanged shared source'):
            analyze.analyze(folder)

    def test_rejects_pre_schema_cohort(self):
        folder = write_cohort(self.root)
        plan = json.loads((folder / 'plan.json').read_text())
        del plan['benchmark']
        (folder / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
        receipt = json.loads((folder / 'receipt.json').read_text())
        receipt['plan_sha256'] = digest(folder / 'plan.json')
        (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        with self.assertRaisesRegex(ValueError, 'predates benchmark schema 2'):
            analyze.analyze(folder)

    def test_cli_writes_all_outputs(self):
        folder = write_cohort(self.root)
        output = self.root / 'results'
        process = subprocess.run([sys.executable, '-B', str(HERE / 'analyze.py'), str(folder),
                                  '--output', str(output)], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        for name in ['summary.json', 'summary.csv', 'samples.csv', 'summary.md']:
            self.assertTrue((output / name).is_file(), name)
        self.assertIn('MLF median', (output / 'summary.md').read_text())

    def test_cli_rejects_incompatible_cohorts(self):
        write_cohort(self.root, label='screen')
        write_cohort(self.root, label='other', endpoint='emlf-source-v1')
        process = subprocess.run([sys.executable, '-B', str(HERE / 'analyze.py'),
                                  str(self.root / 'screen'), str(self.root / 'other'),
                                  '--output', str(self.root / 'results')], capture_output=True, text=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('incompatible cohorts differ in', process.stderr + process.stdout)

    def test_cli_rejects_duplicate_cohort_labels(self):
        write_cohort(self.root, label='screen')
        copy = write_cohort(self.root, label='screen-copy')
        plan = json.loads((copy / 'plan.json').read_text())
        plan['benchmark']['cohort'] = 'screen'
        (copy / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
        receipt = json.loads((copy / 'receipt.json').read_text())
        receipt['plan_sha256'] = digest(copy / 'plan.json')
        (copy / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        process = subprocess.run([sys.executable, '-B', str(HERE / 'analyze.py'),
                                  str(self.root / 'screen'), str(copy),
                                  '--output', str(self.root / 'results')], capture_output=True, text=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('duplicate cohort label', process.stderr + process.stdout)


if __name__ == '__main__':
    unittest.main()
