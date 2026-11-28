#!/usr/bin/env python3
"""Contract tests for the compiler shape benchmark. No compiler is required.

These tests use synthetic receipts to prove that the analyzer refuses missing,
duplicate, non-finite, failed, qualified-only and incompatible data, and that the
frozen schedule stays balanced.
"""
import base64
import copy
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402
import bench  # noqa: E402
import run as runner  # noqa: E402
import generate  # noqa: E402
import prepare  # noqa: E402

import worker

STAGES = ['source-to-checked', 'checked-to-llvm', 'llvm-to-executable']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_cohort(root, label='screen', family='flat_functions', size=8, repeats=3,
                 mlf_seconds=(2.0, 2.2, 2.4), ghc_seconds=(1.0, 1.0, 1.1),
                 endpoint='crate-bootstrap-v1', host='test-host'):
    folder = Path(root) / label
    folder.mkdir(parents=True)
    case, = generate.generate(folder / 'source', sizes=[size], families=[family])
    pins = {case['source']: digest(case['source'])}
    pins.update({lib['source']: digest(lib['source']) for lib in worker.dependencies(case)})
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
                       'patch_bytes': 0, 'patch_sha256': hashlib.sha256(b'').hexdigest()},
            'toolchain': {'ghc': {'path': '/ghc', 'version': '9.14.1'},
                          'clang': {'path': '/clang', 'version': 'clang test'},
                          'producer': {'path': '/producer', 'receipt_sha256': 'a' * 64, 'emlf_sha256': 'b' * 64},
                          'builtin': {'/builtin.mlfci': 'c' * 64, '/builtin.mlfco': 'd' * 64}},
            'host': {'platform': host, 'machine': 'test-mcu'}, 'cases': [case], 'schedule': schedule, 'inputs': pins}
    (folder / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    runs = []
    for item in schedule:
        times = mlf_seconds if item['lane'] == 'mlf' else ghc_seconds
        wall = times[item['position'] // 2 if item['position'] // 2 < len(times) else 0]
        stages = [{'name': name, 'wall_seconds': wall / 3, 'user_seconds': wall / 4,
                   'system_seconds': wall / 20} for name in worker.mlf_stage_names(endpoint)] if item['lane'] == 'mlf' else []
        runs.append({'case': case['id'], 'position': item['position'], 'lane': item['lane'], 'complete': True,
                     'output_correct': True, 'fresh': 1 if item['lane'] == 'mlf' else None,
                     'reused': 0 if item['lane'] == 'mlf' else None, 'max_group_members': 1,
                     'raw_compared_with_first_mlf_leg': item['lane'] == 'mlf' and item['position'] > 1,
                     'executable_sha256': 'e' * 64, 'oracle_inputs': case['inputs'],
                     'stages': {'complete': True, 'stages': stages},
                     'command': {'complete': True, 'timed_target_leg': True, 'exit_code': 0, 'reason': None,
                                 'wall_seconds': wall, 'child_user_seconds': wall / 4,
                                 'child_system_seconds': wall / 20, 'started_utc': '2026-10-31T00:00:00Z'}})
    receipt = {'complete': True, 'all_cases_passed': True, 'failures': [],
               'plan_sha256': digest(folder / 'plan.json'), 'runs': runs}
    (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    inventory, evidence = graph_fixture(crate='compiler-shapes/' + case['id'])
    for index, item in enumerate(schedule):
        if item['lane'] == 'mlf':
            leg = folder / 'legs' / ('%03d-' % index + case['id'] + '-mlf')
            leg.mkdir(parents=True)
            (leg / 'query-cache-inventory.json').write_text(json.dumps(inventory))
            (leg / 'query-graph-evidence.json').write_text(json.dumps(evidence))
    return folder


def edit(folder, mutate):
    path = Path(folder) / 'receipt.json'
    receipt = json.loads(path.read_text())
    mutate(receipt)
    path.write_text(json.dumps(receipt, indent=2) + '\n')


class BindingShapeTests(unittest.TestCase):
    def test_closures_capture_runtime_values_and_escape_before_application(self):
        for n in (1, 8, 32, 128):
            with self.subTest(n=n):
                source = generate.program('captured_closures', n)
                build = next(line for line in source.splitlines() if line.startswith('makeClosures x ='))
                leaves = re.findall(
                    r'let \{ saved = subInt x (\d+) \} in Closure (\d+) \(\\arg -> mulInt saved arg\)', build
                )
                self.assertEqual(leaves, [(str(i), str(i)) for i in range(1, n + 1)])
                self.assertEqual(build.count('Both ('), n - 1)
                self.assertIn('Closure arg f -> f arg', source)
                self.assertIn('Both l r -> addInt (applyClosures l) (applyClosures r)', source)
                self.assertIn('entry x = applyClosures (makeClosures x);', source)
                for x in (-n - 1, -1, 0, 1, n + 1):
                    self.assertEqual(generate.expected('captured_closures', n, x),
                                     sum(i * (x - i) for i in range(1, n + 1)))

    def test_single_product_binds_and_weighs_every_position(self):
        for n in (1, 8, 32, 128):
            with self.subTest(n=n):
                source = generate.program('wide_product', n)
                self.assertIn('data Product = Product ' + ' '.join(['Int'] * n) + ';', source)
                body = re.search(r'weigh p = case p of \{ Product (.*?) -> (.*?) \};', source)
                self.assertIsNotNone(body)
                fields = list(range(1, n + 1))
                self.assertEqual(body[1].split(), [f'v{i}' for i in fields])
                self.assertEqual(re.findall(r'mulInt (v\d+) (\d+)', body[2]),
                                 [(f'v{i}', str(n + 1 - i)) for i in fields])
                entry = next(line for line in source.splitlines() if line.startswith('entry x ='))
                self.assertTrue(entry.startswith('entry x = weigh (Product '))
                self.assertEqual(re.findall(r'\(addInt x (\d+)\)', entry), list(map(str, fields)))
                for x in (-n - 1, -1, 0, 1, n + 1):
                    values = [x + i for i in fields]
                    self.assertEqual(generate.expected('wide_product', n, x),
                                     sum(value * weight for value, weight in zip(values, reversed(fields))))


class ReferenceRuntimeTests(unittest.TestCase):
    def test_workers_link_runtime_from_their_own_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clang = root / 'clang'
            clang.write_text(
                '#!' + sys.executable + '\n'
                'from pathlib import Path\nimport sys\n'
                'args = sys.argv[1:]\n'
                'output = Path(args[args.index("-o") + 1])\n'
                'if "-c" in args:\n'
                '    output.write_bytes(Path(args[args.index("-c") + 1]).read_bytes())\n'
                'else:\n'
                '    ir = next(Path(p) for p in args if p.endswith(".ll"))\n'
                '    obj = next(Path(p) for p in args if p.endswith(".o"))\n'
                '    if ir.read_bytes() != obj.read_bytes(): sys.exit(1)\n'
                '    output.write_bytes(ir.read_bytes())\n')
            clang.chmod(0o755)

            def checkout(name, marker):
                source = root / name
                (source / 'runtime').mkdir(parents=True)
                (source / 'runtime/mlf_runtime.c').write_text(marker)
                (source / 'bin').mkdir()
                compiler = source / 'bin/emlf'
                compiler.write_text("#!/bin/sh\nprintf '%s' " + marker + "\n")
                compiler.chmod(0o755)
                return source

            candidate = checkout('candidate', 'candidate-abi')
            baseline = checkout('reference', 'reference-abi')
            candidate_runtime = candidate / 'runtime.o'
            subprocess.run(prepare.runtime_command(clang, candidate, [], candidate_runtime), check=True)
            setup = {'producer': str(candidate), 'runtime': str(candidate_runtime),
                     'runtime_cflags': [], 'clang': str(clang), 'libs': [], 'builtin': 'fixed-builtin'}
            helper = runner.command_runner.load_helper()
            cache = root / 'baseline-cache'
            reference = runner.compiler_reference.prepare_runtime(setup, baseline, cache, helper)
            self.assertEqual(reference['runtime_sha256'], digest(baseline / 'runtime/mlf_runtime.c'))
            reference['producer'] = str(baseline)
            plan = root / 'plan.json'
            plan.write_text(json.dumps({'cases': [{'id': 'case', 'source': 'Main.hs'}], 'setup': setup,
                'benchmark': {'endpoint': {'id': 'crate-fused-v1'}}, 'compiler_reference': reference}))
            for lane, marker in [('mlf', 'candidate-abi'), ('reference', 'reference-abi')]:
                output = root / ('build-' + lane)
                subprocess.run([sys.executable, '-B', HERE / 'worker.py', '--plan', plan, '--case',
                                'case', '--lane', lane, '--out', output], check=True)
                self.assertEqual((output / 'program').read_text(), marker)

            with mock.patch.object(runner.compiler_reference.subprocess, 'run') as build_runtime:
                runner.compiler_reference.prepare_runtime(setup, baseline, cache, helper)
                build_runtime.assert_not_called()
            Path(reference['runtime']).write_text('changed')
            with self.assertRaisesRegex(RuntimeError, 'immutable input changed'):
                runner.compiler_reference.prepare_runtime(setup, baseline, cache, helper)


class CompilerReferenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Compiler shape test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.source = self.repo / 'source'
        self.source.write_text('one')
        self.git('add', 'source')
        self.git('commit', '-qm', 'first')
        self.first = self.git('rev-parse', 'HEAD')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', self.repo, *args], text=True).strip()

    def test_revision_follows_staged_unstaged_untracked_and_clean_states(self):
        select = runner.compiler_reference.select_revision
        self.assertIsNone(select(self.repo)['commit'])
        self.source.write_text('two')
        self.assertEqual(select(self.repo)['commit'], self.first)
        self.git('add', 'source')
        self.assertTrue(select(self.repo)['dirty'])
        self.git('commit', '-qm', 'second')
        second = self.git('rev-parse', 'HEAD')
        self.assertEqual(select(self.repo), dict(candidate_commit=second, dirty=False,
                                                commit=self.first, basis='HEAD vs first parent'))
        generated = self.repo / 'benchmark-output'
        generated.mkdir()
        (generated / 'sample').touch()
        self.assertEqual(select(self.repo, [generated])['commit'], self.first)
        self.assertEqual(select(self.repo)['commit'], second)
        self.git('add', 'benchmark-output/sample')
        self.assertEqual(select(self.repo, [generated])['commit'], second)

    def test_clean_merge_uses_first_parent(self):
        self.git('switch', '-qc', 'feature')
        (self.repo / 'feature').touch()
        self.git('add', 'feature')
        self.git('commit', '-qm', 'feature')
        self.git('switch', '-q', 'main')
        self.git('merge', '--no-ff', '-qm', 'merge', 'feature')
        self.assertEqual(runner.compiler_reference.select_revision(self.repo)['commit'], self.first)

    def test_exact_matched_baseline_generates_the_advertised_coordinate(self):
        family = 'retained_curried_job_list'
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        setup = root / 'setup.json'
        setup.write_text(json.dumps({'complete': True, 'source': str(self.repo), 'producer': str(root),
                                     'endpoint': 'crate-plan-v1'}))
        args = ['--family', 'baseline', '--family', family, '--size', '8', '--baseline-family', family]
        expected = generate.generate(root / 'full', [8], ['baseline', family], family)
        helper = runner.command_runner.load_helper()
        events = root / 'events.jsonl'
        events.touch()
        for case in expected:
            exact = 'compiler-shapes/comparison/' + case['id']
            output = root / case['id']
            env = {'MLF_TEST_SUITE': 'compiler-shapes', 'MLF_TEST_EXACT': exact, 'MLF_TEST_EVENTS': str(events)}
            with self.subTest(exact=exact), mock.patch.dict(os.environ, env):
                listing = subprocess.check_output([sys.executable, '-B', HERE / 'bench.py',
                                                   '--framework-list', 'run', *args], text=True)
                self.assertEqual(json.loads(listing), [exact])
                argv = ['run.py', '--setup', str(setup), '--output', str(output), '--endpoint', 'crate-plan-v1', *args]
                # Stop at the compiler build boundary, after the real request has generated its sources.
                with mock.patch.object(sys, 'argv', argv), \
                     mock.patch.object(runner.command_runner, 'load_helper', return_value=helper), \
                     mock.patch.object(helper, 'authenticate', return_value={'ghc': {'path': '/ghc'}}), \
                     mock.patch.object(runner.compiler_reference, 'prepare', side_effect=InterruptedError), \
                     self.assertRaises(InterruptedError):
                    runner.main()
                selected, = analyze.load(output / 'sources/cases.json')
                for key in ('id', 'inputs', 'expected_stdout', 'source_sha256', 'matched_baseline_for'):
                    self.assertEqual(selected.get(key), case.get(key), key)
                self.assertEqual([(lib['module'], digest(lib['source'])) for lib in worker.dependencies(selected)],
                                 [(lib['module'], lib['sha256']) for lib in worker.dependencies(case)])
                self.assertEqual(json.loads(events.read_text().splitlines()[-1])['plan'], [exact])

    def test_invalid_matched_baseline_fails_before_setup(self):
        family = 'retained_curried_job_list'
        output = self.repo / 'output'
        argv = ['run.py', '--setup', 'missing.json', '--output', str(output),
                '--family', family, '--size', '8', '--baseline-family', family]
        with mock.patch.object(sys, 'argv', argv), self.assertRaisesRegex(ValueError, 'matched baseline'):
            runner.main()
        self.assertFalse(output.exists())

    def test_reference_growth_keeps_both_controls_in_the_recorded_round(self):
        sizes = [0, 8, 32, 64]
        rows = []
        samples = []
        for size in sizes:
            family = 'flat_functions' if size else 'baseline'
            case = f'{family}-{size}'
            rows.append(dict(family=family, size=size, case=case, mlf_peak_rss_bytes=100,
                             reference_peak_rss_bytes=150, ghc_peak_rss_bytes=200,
                             mlf_over_reference_peak_rss=2/3, mlf_over_ghc_peak_rss=.5))
            paired = [dict(case=case, lane=lane, position=i) for i,lane in enumerate(runner.lanes_for(0,2))]
            for leg in runner.with_reference(paired):
                cost = {'mlf': 1, 'reference': 2, 'ghc': 3}[leg['lane']]
                samples.append(dict(leg,order=len(samples),wall_seconds=cost*(size+1),
                                    sampled_process_tree_peak_rss_bytes=cost*(size+1)*1024))
        with mock.patch.object(runner.fit_growth, 'REPLICATES', 50):
            for control in ('ghc', 'reference'):
                report, = runner.fit_growth.family_reports(rows, samples, 2, control)
                self.assertEqual(len(report['checks']), 9)
                self.assertEqual(set(report['estimates']), {'mlf', control})
                self.assertTrue(report['checks']['lower_ols_95'])
                self.assertIn(control+'_mib_per_unit', report['peak_rss_growth'])

    def test_pairs_share_one_candidate_and_keep_both_controls_adjacent(self):
        original = [dict(case='x', lane=lane, position=i) for i,lane in enumerate(runner.lanes_for(0,2))]
        triple = runner.with_reference(original)
        self.assertEqual([r['lane'] for r in triple],
                         ['ghc','mlf','reference','reference','mlf','ghc'])
        samples = [dict(r, order=i, wall_seconds=i+1) for i,r in enumerate(triple)]
        self.assertEqual(runner.fit_growth.paired_cell(samples,2), [(2,1),(5,6)])
        self.assertEqual(runner.fit_growth.paired_cell(samples,2,reference='reference'), [(2,3),(5,4)])
        samples[-1]['order'] += 1
        with self.assertRaisesRegex(ValueError,'nonadjacent'):
            runner.fit_growth.paired_cell(samples,2)


class ScheduleTests(unittest.TestCase):
    def test_interleaving_visits_each_cell_once_per_round_and_keeps_pairs(self):
        cases = ['baseline', 'small', 'medium', 'large']
        repeats = 7
        grouped = [{'case': case, 'position': pos, 'lane': lane}
                   for index, case in enumerate(cases)
                   for pos, lane in enumerate(runner.lanes_for(index, repeats))]
        schedule = runner.interleave_pairs(grouped, repeats, random.Random(41))
        self.assertEqual(schedule, runner.interleave_pairs(grouped, repeats, random.Random(41)))
        self.assertNotEqual(schedule, runner.interleave_pairs(grouped, repeats, random.Random(42)))
        self.assertCountEqual(schedule, grouped)
        for rep in range(repeats):
            start = rep * 2 * len(cases)
            subset = schedule[start:start + 2 * len(cases)]
            self.assertCountEqual([row['case'] for row in subset[::2]], cases)
            for first, second in zip(subset[::2], subset[1::2]):
                self.assertEqual(first['case'], second['case'])
                self.assertEqual((first['position'], second['position']), (2*rep, 2*rep+1))
                self.assertEqual({first['lane'], second['lane']}, {'mlf', 'ghc'})


    def test_explicit_sizes_are_bounded(self):
        self.assertEqual(bench.resolve('default', ['inferred_poly_chain'], [8192])[2], [8192])
        for n in [0, -1, 8193]:
            with self.assertRaises(SystemExit):
                bench.resolve('default', ['inferred_poly_chain'], [n])

    def test_run_uses_explicit_setup(self):
        import argparse
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup = root / 'existing-setup.json'
            setup.write_text('{}')
            args = argparse.Namespace(workdir=root / 'other', setup=setup,
                cohort='explicit', matrix='default', family=None, size=None,
                repeats=None, endpoint='crate-bootstrap-v1', interleave_pairs=True, cohort_output_gib=32)
            with mock.patch.object(bench, 'run') as run_command:
                bench.command_run(args)
            argv = run_command.call_args.args[0]
            self.assertEqual(argv[argv.index('--setup') + 1], setup.resolve())
            self.assertIn('--interleave-pairs', argv)
            self.assertEqual(argv[argv.index('--cohort-output-gib') + 1], 32)
            self.assertEqual(argv[argv.index('--repeats') + 1], 2)
            self.assertCountEqual([argv[i + 1] for i, arg in enumerate(argv) if arg == '--family'],
                                  ['baseline', *generate.REGISTRY['matrices']['default']['families']])
            self.assertEqual([int(argv[i + 1]) for i, arg in enumerate(argv) if arg == '--size'],
                             [8, 32, 128, 1024, 8192])

            with mock.patch.object(bench, 'run') as run_command:
                args.repeats = 6
                bench.command_run(args)
                argv = run_command.call_args.args[0]
                self.assertEqual(argv[argv.index('--repeats') + 1], 6)
                run_command.reset_mock()
                for repeats in (0, 1):
                    args.repeats = repeats
                    with self.subTest(repeats=repeats), self.assertRaisesRegex(SystemExit, 'at least 2 pairs'):
                        bench.command_run(args)
                run_command.assert_not_called()

    def test_all_build_entry_parsers_default_to_fused_and_allow_two_stage(self):
        # Exercise the real CLI parsers, stopping before any build or filesystem
        # action. Old setups must still require explicit endpoint selection.
        class Parsed(Exception):
            pass

        original = bench.argparse.ArgumentParser.parse_args
        entries = [(bench, ['list']),
                   (bench, ['prepare', '--workdir', '/unused']),
                   (bench, ['run', '--workdir', '/unused', '--cohort', 'test']),
                   (bench, ['all', '--workdir', '/unused', '--cohort', 'test']),
                   (prepare, ['--producer', '/unused', '--output', '/unused']),
                   (runner, ['--setup', '/unused', '--output', '/unused'])]
        for module, arguments in entries:
            for extra, expected in [([], 'crate-fused-v1'),
                                    (['--endpoint', 'crate-bootstrap-v1'], 'crate-bootstrap-v1')]:
                with self.subTest(module=module.__name__, arguments=arguments, extra=extra):
                    found = []
                    def capture(parser):
                        found.append(original(parser, arguments + extra))
                        raise Parsed()
                    with mock.patch.object(bench.argparse.ArgumentParser, 'parse_args', capture), \
                         mock.patch.object(sys, 'argv', [module.__name__, *arguments, *extra]):
                        with self.assertRaises(Parsed):
                            module.main()
                    self.assertEqual(found[0].endpoint, expected)

    def test_inferred_poly_chain_is_unsigned_and_every_layer_is_reached_at_two_types(self):
        for size in [1, 3, 32, 512]:
            source = generate.program('inferred_poly_chain', size)
            declarations = re.findall(r'^(f\d+) (.*);$', source, re.MULTILINE)
            self.assertEqual(len(declarations), size)
            self.assertNotRegex(source, r'f\d+ ::')
            for i, (name, body) in enumerate(declarations):
                self.assertEqual(name, 'f' + str(i))
                self.assertEqual(re.findall(r'\bf\d+\b', body), [] if i == 0 else ['f' + str(i - 1)])
            entry = next(line for line in source.splitlines() if line.startswith('entry x ='))
            self.assertEqual(re.findall(r'\bf\d+\b', entry), ['f' + str(size - 1)] * 3)
            self.assertIn('addInt value 1', entry)
            self.assertIn('if value then False else True', entry)
            for value in [-1, 0, 7, size]:
                integer, boolean = value, value < 0
                for _ in range(size):
                    integer += 1
                    boolean = not boolean
                self.assertEqual(generate.expected('inferred_poly_chain', size, value),
                                 integer if boolean else -integer)
        self.assertEqual([generate.expected('inferred_poly_chain', 1, x) for x in [-1, 0, 7]], [0, 1, 8])
        self.assertEqual([generate.expected('inferred_poly_chain', 4, x) for x in [-1, 0, 7]], [3, -4, -11])

    def test_inferred_poly_functions_are_unsigned_independent_and_used_at_two_types(self):
        for size in [4, 32, 512]:
            source = generate.program('inferred_poly_functions', size)
            declarations = re.findall(r'^(f\d+) (.*);$', source, re.MULTILINE)
            self.assertEqual(len(declarations), size)
            self.assertNotRegex(source, r'f\d+ ::')
            entry = next(line for line in source.splitlines() if line.startswith('entry x ='))
            for i, (name, body) in enumerate(declarations):
                self.assertEqual(name, 'f' + str(i))
                self.assertEqual(body, ['y = y', 'y z = y', 'f y = f y', 'f g y = f (g y)'][i % 4])
                self.assertNotRegex(body, r'\bf\d+\b')
                self.assertEqual(len(re.findall(r'\b' + name + r'\b', entry)), 3)
            self.assertEqual(entry.count('ltInt x '), size + 2 * (size // 4))
            for value in [-1, 0, 7, size, size + 1]:
                self.assertEqual(generate.expected('inferred_poly_functions', size, value),
                                 sum(value + i if value < i else -(value + i) for i in range(size)))
        self.assertEqual([generate.expected('inferred_poly_functions', 4, x) for x in [-1, 0, 7]], [2, 6, -34])

    def test_captured_parameter_uses_checks_each_binding_and_signed_sum(self):
        family = 'captured_parameter_uses'
        for size in (0, 1, 2, 8, 32, 128):
            source = generate.program(family, size)
            declarations = re.findall(
                r'^f(\d+) x = let \{ y = x \} in addInt y (\d+);$', source, re.MULTILINE)
            self.assertEqual(declarations, [(str(i), str(i+1)) for i in range(size)])
            entry = next(line for line in source.splitlines() if line.startswith('entry x ='))
            self.assertEqual(re.findall(r'\(f(\d+) x\)', entry), list(map(str, range(size))))
            if size == 0:
                self.assertEqual(entry, 'entry x = 0;')
            for x in (-2**63, -1, 0, 7, 2**63-1):
                total = 0
                for i in range(size):
                    total = self.signed_int(total + self.signed_int(x+i+1))
                self.assertEqual(generate.expected_output(family, size, x), f'{total}\n')

    def test_inferred_functions_only_remove_generated_signatures(self):
        for size in [1, 32, 512]:
            annotated = generate.program('flat_functions', size)
            inferred = generate.program('inferred_functions', size)
            self.assertEqual(inferred, re.sub(r'^f\d+ :: Int -> Int;\n', '', annotated,
                                              flags=re.MULTILINE))
            self.assertEqual(len(re.findall(r'^f\d+ x =', inferred, re.MULTILINE)), size)
            for value in [-1, 0, 7]:
                self.assertEqual(generate.expected('inferred_functions', size, value),
                                 size * value + size * (size - 1) // 2)

    def test_repeated_dictionary_arguments(self):
        family = 'repeated_dictionary_arguments'
        for size in (1, 4, 16):
            source = generate.program(family, size)
            self.assertEqual(source.count('(pass '), size)
            self.assertIn('case worker (Box x)', source)
            self.assertEqual(generate.expected_output(family, size, -10), f'{size - 10}\n')
            self.assertEqual(generate.expected(family, size, 2**63 - 1), -2**63 + size - 1)

    def test_recursive_dictionary_forwarding(self):
        family = 'recursive_dictionary_forwarding'
        for n in (0, 1, 2, 17, 32):
            source = generate.program(family, n)
            self.assertEqual(source.count('(step (Box') + source.count('(step (Tag'), n)
            self.assertIn('else second (subInt fuel 1) x', source)
            self.assertIn('else first (subInt fuel 1) x', source)
            alias = generate.program('recursive_dictionary_alias', n)
            self.assertIn('bridge = first True;', alias)
            self.assertIn('else bridge (subInt fuel 1) x', alias)
            for x in (-2**63, -3, 0, 7, 2**63 - 1):
                seed = self.signed_int(x + 1)
                value = seed
                for i in range(n):
                    item = self.signed_int(seed + i)
                    value = self.signed_int(value + (item if i % 2 == 0 else -item))
                self.assertEqual(generate.expected(family, n, x), value)
                self.assertEqual(generate.expected('recursive_dictionary_alias', n, x), value)

    def test_closed_dictionary_result(self):
        family = 'closed_dictionary_result'
        for n in (0, 1, 2, 17, 32):
            source = generate.program(family, n)
            self.assertEqual(source.count('(step (Box') + source.count('(step (Tag'), n)
            self.assertIn('entry x = addInt x (worker x);', source)
            for x in (-2**63, -3, 0, 7, 2**63 - 1):
                terms = [self.signed_int(x + i) for i in range(n)]
                total = x + sum(terms[::2]) - sum(terms[1::2])
                self.assertEqual(generate.expected(family, n, x), self.signed_int(total))

    def test_bounded_dictionary_arguments(self):
        family = 'bounded_dictionary_arguments'
        for size in (1, 8, 32):
            source = generate.program(family, size)
            self.assertEqual(source.count('case pass (Box x'), size)
            self.assertIn(f'callback x{size}', source)
            self.assertEqual(generate.expected_output(family, size, -7), f'{size - 7}\n')
            self.assertEqual(generate.expected(family, size, 2**63 - 1), -2**63 + size - 1)

    def test_duplicated_type_arguments_preserves_input(self):
        family = 'duplicated_type_arguments'
        for depth in (1, 4, 19):
            source = generate.program(family, depth)
            self.assertIn('a -> Fork a a;', source)
            self.assertEqual(source.count('(duplicate '), depth)
            self.assertEqual(source.count('(left '), depth)
            for value in (-2**63, -1, 7, 2**63 - 1):
                self.assertEqual(generate.expected_output(family, depth, value), f'{value}\n')

    def test_polymorphic_import_spine_grows_one_inferred_application(self):
        family = 'polymorphic_import_spine'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for size in (1, 8, 64):
            source = generate.program(family, size)
            self.assertNotRegex(source, r'(?m)^(keep|entry) ::')
            predecessor, = re.findall(r'(?m)^keep seed(.*?) = seed;$', source)
            self.assertEqual(predecessor.split(), [f'unused{i}' for i in range(size)])
            caller, = re.findall(r'(?m)^entry x = keep x(.*);$', source)
            self.assertEqual(re.findall(r'\((ltInt|addInt) x (\d+)\)', caller),
                             [('ltInt' if i % 2 else 'addInt', str(i)) for i in range(size)])
            for value in (-2**63, -1, 0, 7, 2**63-1):
                self.assertEqual(generate.expected_output(family, size, value), f'{value}\n')

    def test_polymorphic_import_fanout_retains_each_predecessor(self):
        family = 'polymorphic_import_fanout'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        with tempfile.TemporaryDirectory() as root:
            cases = generate.generate(Path(root)/'cases', [8, 16, 32, 64, 128], [family])
            for case in cases:
                size = case['size']
                source = Path(case['source']).read_text()
                self.assertNotRegex(source, r'(?m)^(helper\d+|entry) ::')
                self.assertEqual(re.findall(r'^helper(\d+) x = x;$', source, re.M),
                                 [str(i) for i in range(size)])
                entry, = re.findall(r'^entry x = (.*);$', source, re.M)
                self.assertEqual(re.findall(r'helper(\d+) \(addInt x (\d+)\)', entry),
                                 [(str(i), str(i)) for i in range(size)])
                self.assertEqual(case['inputs'], [-1, 0, 7])
                self.assertEqual(case['expected_stdout'],
                                 [f'{sum(x + i for i in range(size))}\n' for x in case['inputs']])

    def test_polymorphic_fanout_uses_one_inferred_group_and_both_argument_types(self):
        family = 'polymorphic_fanout'
        self.assertEqual(bench.resolve('default', [family], [32])[1], [family])
        for size in (1, 8, 32, 128):
            source = generate.program(family, size)
            self.assertIn('apply f value = f value;', source)
            self.assertNotRegex(source, r'(apply|fanout) ::')
            body, = re.findall(r'^fanout measure value base = (.*);$', source, re.MULTILINE)
            offsets = re.findall(r'apply \(apply measure value\) \(addInt base (\d+)\)', body)
            self.assertEqual(list(map(int, offsets)), list(range(size)))
            self.assertIn('fanout addInt x x', source)
            self.assertIn('(ltInt x 0) x', source)
            for value in (-3, 0, 7):
                contributions = [value + offset + (offset if value < 0 else -offset)
                                 for offset in range(value, value + size)]
                self.assertEqual(generate.expected(family, size, value), sum(contributions))

    def test_curried_environment_prefix_reuses_all_boxed_arguments(self):
        family = 'curried_environment_prefix'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for width in (1, 8, 40, 64):
            source = generate.program(family, width)
            self.assertEqual(source.count('mulInt (unbox arg'), width)
            self.assertEqual(source.count('(panic "unused argument")'), 2)
            for x in (-2**63, -7, 0, 11, 2**63 - 1):
                weighted = sum((x+i)*i for i in range(1, width+1))
                answers = (weighted+x, weighted-x)
                self.assertEqual(generate.expected(family, width, x), self.signed_int(sum(answers)))

    def test_captured_application_spines_select_the_ordered_operands(self):
        family = 'captured_application_spines'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for count in (1, 12, 13, 64):
            source = generate.program(family, count)
            self.assertEqual(len(re.findall(r'^site\d+ \(Op f\) \(Inputs ', source, re.M)), count)
            for x in (-2**63, -5, 0, 7, 2**63 - 1):
                fields = list(range(x, x+12))
                result = 0
                for site in range(count):
                    result += fields[0] + site if x < 0 else fields[-1] - site
                    fields.append(fields.pop(0))
                self.assertEqual(generate.expected(family, count, x), self.signed_int(result))

    def test_nested_worker_applications_preserves_direct_calls_and_saved_prefixes(self):
        family = 'nested_worker_applications'
        inputs = [-2**63, -7, -1, 0, 6, 7, 17, 2**63-1]
        with tempfile.TemporaryDirectory() as temporary:
            cases = generate.generate(Path(temporary)/'cases', [0, 1, 2, 5], [family])
            for case in cases:
                n = case['size']
                source = Path(case['source']).read_text()
                self.assertEqual(case['inputs'], inputs)
                self.assertEqual(source.count('let { work'), n)
                for i in range(1, n+1):
                    self.assertIn(f'Token flag{i} rest{i} ->', source)
                    self.assertIn(f'then work{i} False 3', source)
                    call = f'(work{i} flag{i} key)'
                    if i % 2:
                        self.assertIn(f'Saved {call} (work{i} flag{i})', source)
                    else:
                        self.assertIn(f'Direct {call}', source)
                        self.assertNotIn(f'(work{i} flag{i})', source)
                expected = []
                for x in inputs:
                    key = abs(x) % 11 * (-1 if x < 0 else 1)
                    flag = key < 0
                    total = 0
                    if key != 6:
                        for i in range(1, n+1):
                            direct = 3 if flag else i if key < 0 else key
                            total += direct
                            if i % 2:
                                suffix = 4 if key < 0 else -1
                                saved = 3 if flag else i if suffix < 0 else suffix
                                total += 2*saved
                            flag = not flag
                    expected.append(f'{total}\n')
                self.assertEqual(case['expected_stdout'], expected)

    def test_recursive_lookup_workers_visit_every_binding_and_report_lookup_hits(self):
        family = 'recursive_lookup_workers'
        table = {2: 17, 5: 41, 8: 73}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'cases'
            generate.generate(output, [8, 32, 64], [family])
            for case in json.loads((output/'cases.json').read_text()):
                n = case['size']
                self.assertEqual(case['inputs'], [3 - n, 5 - n//2, 8, 9])
                self.assertEqual(case['expected_stdout'][0], '17\n')
                self.assertEqual(case['expected_stdout'][-2:], ['73\n', '0\n'])
        for n in (1, 3, 8, 16, 64):
            source = generate.program(family, n)
            for i in range(n):
                self.assertEqual(source.count(f'walk{i} ::'), 1)
                self.assertIn(f'walk{i} q l else if ltInt key q then walk{i} q r', source)
                self.assertEqual(source.count(f'(walk{i} (addInt x {i}) tree)'), 1)
            for x in (-2**63, -n, -1, 0, 2, 5, 8, 9, 2**63 - 1):
                keys = [((x+i+2**63) % 2**64) - 2**63 for i in range(n)]
                self.assertEqual(generate.expected_output(family, n, x),
                                 f'{sum(table.get(key, 0) for key in keys)}\n')

    def test_stable_recursive_workers_keep_the_worker_table_and_beta_steps(self):
        family = 'stable_recursive_workers'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for n in (1, 8, 19, 32):
            source = generate.program(family, n)
            self.assertEqual(re.findall(r'\(Job worker(\d+) ', source), list(map(str, range(n))))
            self.assertEqual(re.findall(r'\\a(\d+) -> ', source), list(map(str, range(24))))
            for x in (-2**63, -35, -1, 0, 7, 29, 2**63-1):
                def rem(a, b):
                    q = abs(a) // b
                    return a - (q if a >= 0 else -q)*b

                offsets = [rem(self.signed_int(x+i), 31) for i in range(3, 27)]
                result = offsets[0]
                for offset in offsets[1:]:
                    result = rem(3*result + offset, 97)
                for i in range(1, n+1):
                    result += i + sum(rem(i+k, 19) for k in range(1, rem(x, 11)+1))
                self.assertEqual(generate.expected(family, n, x), self.signed_int(result))

    def test_escaping_curried_jobs_store_distinct_order_sensitive_functions(self):
        family = 'escaping_curried_jobs'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for count in (1, 12, 13, 64):
            source = generate.program(family, count)
            self.assertEqual(len(re.findall(r'More \(Job job\d+\)', source)), count)
            self.assertEqual(source.count('(saved '), 2)
            for x in (-2**63, -1, 0, 7, 2**63 - 1):
                result = 0
                for sign in (1, -1):
                    args = [x+j for j in range(1, 9)] + [x+sign*j for j in range(9, 13)]
                    for job in range(count):
                        score = 0
                        for value in args:
                            score = 2*score + value
                        result += score + job
                        args.append(args.pop(0))
                self.assertEqual(generate.expected(family, count, x), self.signed_int(result))

    @staticmethod
    def signed_int(value):
        return int.from_bytes((value & (2**64-1)).to_bytes(8, 'big'), 'big', signed=True)

    def test_mixed_parser_recursion_keeps_one_alternating_cycle(self):
        family = 'mixed_parser_recursion'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        with tempfile.TemporaryDirectory() as root:
            cases = generate.generate(Path(root)/'cases', [1, 3, 8], [family])
            for case in cases:
                n = case['size']
                source = Path(case['source']).read_text()
                self.assertEqual(len(re.findall(r'^rule\d+ :: Parser Int;', source, re.M)), n)
                self.assertNotRegex(source, r'(?m)^tail\d+ ::')
                for i in range(n):
                    self.assertIn(f'rule{i} = choice (bindP tick (\\_ -> tail{i} {i}))', source)
                    self.assertIn(f'tail{i} first = mapP (addInt (addInt first 1)) rule{(i+1)%n};', source)
                self.assertIn(n, case['inputs'])
                self.assertGreater(max(case['inputs']), n)
                for x in [-3, *range(3*n+2)]:
                    steps = max(0, x)
                    score = steps % n + sum(i % n + 1 for i in range(steps))
                    self.assertEqual(generate.expected_output(family, n, x), f'{score}\n')

    def test_inferred_monadic_recursion_leaves_the_helper_unsigned(self):
        family = 'inferred_monadic_recursion'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for bindings in (1, 8, 32):
            source = generate.program(family, bindings)
            self.assertIn('core :: Tree -> Work Int;', source)
            self.assertNotIn('work ::', source)
            self.assertIn('core tree = work tree;', source)
            self.assertIn('a0 <- core body;', source)
            self.assertEqual(source.count('<- pure (addInt'), bindings)
            for x in (-7, 0, 11):
                self.assertEqual(generate.expected(family, bindings, x), sum([x] * (bindings + 1)))

    def test_closed_field_projection_sums_every_field(self):
        family = 'closed_field_projection'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        self.assertNotIn(family, generate.REGISTRY['matrices']['default']['families'])
        inputs = [-2**63, -57, -1, 0, 1, 7, 12, 2**63-1]
        with tempfile.TemporaryDirectory() as root:
            for case in generate.generate(Path(root)/'cases', [0, 1, 3, 8, 16, 32, 64, 128], [family]):
                n = case['size']
                source = Path(case['source']).read_text()
                self.assertIn('project graph = case graph of { Graph first second field -> field };', source)
                self.assertEqual(re.findall(r'addInt \(project graph\) field(\d+)', source),
                                 [str(i) for i in range(1, n + 1)])
                self.assertEqual(case['inputs'], inputs)
                outputs = []
                for x in inputs:
                    quotient = abs(x) // 11
                    small = x - 11 * (-quotient if x < 0 else quotient)
                    if small < 0:
                        graph = (small, small - 1, 2 * small + 1)
                        fields = [small + i for i in range(1, n + 1)]
                    else:
                        graph = (small + 1, small, 3 * small + 2)
                        fields = [small - i for i in range(1, n + 1)]
                    answer = sum(graph[2] + field for field in fields) if n else small
                    outputs.append(f'{answer}\n')
                self.assertEqual(case['expected_stdout'], outputs)

    def test_visible_instance_inventory_keeps_two_calls_in_one_polymorphic_let(self):
        family = 'visible_instance_inventory'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        self.assertNotIn(family, generate.REGISTRY['matrices']['default']['families'])
        with tempfile.TemporaryDirectory() as root:
            cases = generate.generate(Path(root)/'cases', [0, 1, 2, 4, 16, 32], [family])
            for case in cases:
                n = case['size']
                source = Path(case['source']).read_text()
                self.assertEqual(source.count('instance Score Int where { score x = x };'), 1)
                self.assertEqual(re.findall(r'^data Box(\d+) a = B\1 a;$', source, re.M),
                                 list(map(str, range(n))))
                methods = re.findall(
                    r'^instance Score a => Score \(Box(\d+) a\) where '
                    r'\{ score \(B\1 v\) = addInt \(score v\) (\d+) \};$', source, re.M)
                self.assertEqual(methods, [(str(i), str(7*(i+1))) for i in range(n)])
                calls = f'score (B0 y) else score (B{n-1} y)' if n else 'score y else score y'
                self.assertIn('entry :: Int -> Int;\n'
                              'entry x = let { ident a = a; b = ident (ltInt x 0); y = ident x } '
                              f'in if b then {calls};\n', source)
                offsets = [int(offset) for _, offset in methods]
                inputs = [-2**63, -1, 0, 7, 2**63-1]
                self.assertEqual(case['inputs'], inputs)
                outputs = []
                for x in inputs:
                    chosen = offsets[:1] if x < 0 else offsets[-1:]
                    outputs.append(f'{self.signed_int(x + sum(chosen))}\n')
                self.assertEqual(case['expected_stdout'], outputs)

    def test_class_declaration_reservations_keep_all_instance_calls_reachable(self):
        family = 'class_declaration_reservations'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for count in (1, 16, 128):
            source = generate.program(family, count)
            self.assertEqual(source.count('instance Score Token where'), 1)
            self.assertEqual(source.count(' x = score (Token (addInt'), count)
            entry = next(line for line in source.splitlines() if line.startswith('entry x ='))
            self.assertEqual(entry.count('compilerShapeReservationForIndependentTopLevelPredecessor'), count)
            for value in (-7, 0, 11):
                self.assertEqual(generate.expected(family, count, value), sum(range(value, value + count)))

    def test_datatype_validation_fanout_checks_each_constructor_and_fallback(self):
        family = 'datatype_validation_fanout'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for count in (1, 2, 16, 64):
            source = generate.program(family, count)
            self.assertEqual(len(re.findall(r'^probe\d+ :: Token -> Int;', source, re.M)), count)
            entry = next(line for line in source.splitlines() if line.startswith('entry x ='))
            for i in range(count):
                self.assertIn(f'Tag{(i+1)%count} x else Tag{i} x', entry)
            for value in (-7, 0, 11):
                tags = range(count) if value >= 0 else [*range(1, count), 0]
                total = sum(i + (value if i == tag else 0) for i, tag in enumerate(tags))
                self.assertEqual(generate.expected(family, count, value), total)

    def test_shared_datatype_fragments_checks_shared_and_local_fields(self):
        family = 'shared_datatype_fragments'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for count in (1, 3, 32, 128):
            source = generate.program(family, count)
            self.assertEqual(len(re.findall(r'^project\d+ :: Shared -> Local\d+ -> Int;', source, re.M)), count)
            shared = next(line for line in source.splitlines() if line.startswith('data Shared ='))
            self.assertEqual(len(re.findall(r'\bAlternate\d+\b', shared)), count)
            for value in (-7, 0, 11):
                offset = 0 if value < 0 else value
                self.assertEqual(generate.expected(family, count, value), sum(range(offset, offset + count)))

    def test_boxed_closure_factory_preserves_both_captures(self):
        family = 'boxed_closure_factory'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for count in (1, 4, 16, 32):
            source = generate.program(family, count)
            self.assertEqual(re.findall(r'\(make x (\d+)\)', source), [str(i) for i in range(1, count + 1)])
            for value in (-2, 0, 5):
                total = sum(value*i + value if value < 0 else value-i + value*value
                            for i in range(1, count + 1))
                self.assertEqual(generate.expected(family, count, value), total)

    def test_delayed_packet_fanout_demands_the_selected_branch(self):
        family = 'delayed_packet_fanout'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for count in (1, 8, 32, 128):
            source = generate.program(family, count)
            self.assertEqual(len(re.findall(r'^probe\d+ :: Packet -> Int;', source, re.M)), count)
            for value in (-7, -4, -3, 0, 11, 129):
                total = sum(i if value == 0 else
                            value + 3 + i if value + 3 < i else 3 - value - i
                            for i in range(count))
                self.assertEqual(generate.expected(family, count, value), total)

    def test_captured_thunk_fanout_selects_fields_at_runtime(self):
        family = 'captured_thunk_fanout'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for count in (1, 8, 32, 128):
            source = generate.program(family, count)
            self.assertEqual(len(re.findall(r'^make\d+ a b c d = Row', source, re.M)), count)
            self.assertIn('if ltInt selector 0 then addInt one three else addInt two four', source)
            for value in (-7, -1, 0, 7, 11):
                a, b, c, d = value, value + 3, 9 - value, 2 * value
                rows = [(a * i, a * b, (a + b) * c, (a + b) * (c + d))
                        for i in range(1, count + 1)]
                selected = (0, 2) if value < 0 else (1, 3)
                total = sum(row[field] for row in rows for field in selected)
                self.assertEqual(generate.expected(family, count, value), total)

    def test_repeated_ground_dictionary_demands_preserve_call_paths(self):
        family = 'repeated_ground_dictionary_demands'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for count in (1, 4, 7, 16, 64):
            source = generate.program(family, count)
            self.assertEqual(source.count('stringLength "'), count)
            self.assertIn('next x = producer x;', source)
            self.assertIn('then next (subInt 0 x)', source)
            lengths = sum(i % 4 + 1 for i in range(count))
            for value in (-8, -1, 0, 1, 7):
                outputs = [abs(j if j < 0 else j + 1) + lengths for j in (value, -value)]
                self.assertEqual(generate.expected(family, count, value), sum(outputs))

    def test_local_dictionary_branch_fanout_keeps_literal_sites_fixed(self):
        family = 'local_dictionary_branch_fanout'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        with tempfile.TemporaryDirectory() as root:
            for case in generate.generate(Path(root)/'cases', [2, 4, 6], [family]):
                n = case['size']
                source = Path(case['source']).read_text()
                self.assertEqual(source.count('stringLength'), 2)
                self.assertNotRegex(source, r'level\d+ ::')
                for i in range(1, n + 1):
                    self.assertIn(f'then level{i-1} (addInt z {i}) else level{i-1} (subInt z {i})', source)
                self.assertEqual(case['expected_stdout'], ['1\n', '2\n', '2\n'])

    def test_shared_callback_let_chain_retains_both_call_forms(self):
        family = 'shared_callback_let_chain'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for depth in (1, 2, 8, 32):
            source = generate.program(family, depth)
            for i in range(depth):
                previous = 'x' if i == 0 else f'state{i - 1}'
                self.assertIn(f'rule{i} y = remInt (addInt {previous} (mulInt {previous} y)) 251', source)
                self.assertIn(f'then rule{i} x else rule{i} (addInt x 1)', source)
            for x in (-3, -1, 0, 1, 7, 19):
                state = x
                for i in range(depth):
                    product = state * (1 + (x if x < i else x + 1))
                    state = (1 if product >= 0 else -1) * (abs(product) % 251)
                self.assertEqual(generate.expected_output(family, depth, x), f'{state}\n')

    def test_deferred_constructor_spine_demands_exactly_the_generated_depth(self):
        family = 'deferred_constructor_spine'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for depth in (1, 8, 32):
            with self.subTest(depth=depth):
                source = generate.program(family, depth)
                match = next(line for line in source.splitlines() if line.startswith('inspect value'))
                self.assertEqual(match.count('(Link '), depth)
                self.assertEqual(match.count('(Link here _)'), 1)
                self.assertIn(f'if ltInt x 0 then {depth - 1} else {depth}', source)
                for value in (-3, -1, 0, 7):
                    length = depth - int(value < 0)
                    chain = list(range(value, value + length))
                    result = chain[depth - 1] if len(chain) >= depth else 0
                    self.assertEqual(generate.expected_output(family, depth, value), f'{result}\n')

    def test_queued_callback_let_chain_adds_each_selected_operand(self):
        family = 'queued_callback_let_chain'
        self.assertFalse(generate.REGISTRY['families'][family]['default'])
        for depth in (1, 8, 32):
            source = generate.program(family, depth)
            self.assertNotIn('mulInt', source)
            self.assertEqual(source.count(' y = remInt (addInt'), depth)
            for x in (-7, 0, 1, 19):
                state = x
                for i in range(depth):
                    state += x if x < i else x+1
                    state = -(abs(state) % 251) if state < 0 else state % 251
                self.assertEqual(generate.expected_output(family, depth, x), f'{state}\n')

    def test_inferred_dictionary_prefix_scales_literals_and_checks_signed_dispatch(self):
        family = 'inferred_dictionary_prefix'
        for size in (8, 16, 32):
            source = generate.program(family, size)
            self.assertNotRegex(source, r'(loop|punct) ::')
            self.assertIn('punct text = loop consume', source)
            self.assertEqual(re.findall(r'-> punct "mark(\d+)"', source), list(map(str, range(size))))
            self.assertEqual(generate.expected(family, size, -size - 1), 13 - size)
            self.assertEqual(generate.expected(family, size, -size), 10 - size)
        self.assertEqual(generate.expected(family, 8, 7), 17)
        self.assertEqual(generate.expected(family, 16, 15), 27)

    def test_polymorphic_tree_fold_sites_and_oracle(self):
        family = 'polymorphic_tree_fold'
        for size in (1, 32, 512):
            source = generate.program(family, size)
            self.assertNotIn('entry ::', source)
            offsets = re.findall(r'foldPair addInt x \(addInt x (\d+)\) x', source)
            self.assertEqual(list(map(int, offsets)), list(range(size)))
            for value in (-2**63, -1, 0, 7, 2**63 - 1):
                total = sum(value + (value + i) + value for i in range(size))
                wrapped = int.from_bytes((total & (2**64 - 1)).to_bytes(8, 'big'), 'big', signed=True)
                self.assertEqual(generate.expected(family, size, value), wrapped)

    def test_balanced_pairs(self):
        self.assertEqual(runner.lanes_for(0, 3), ['ghc', 'mlf', 'mlf', 'ghc', 'ghc', 'mlf'])
        self.assertEqual(runner.lanes_for(1, 3), ['mlf', 'ghc', 'ghc', 'mlf', 'mlf', 'ghc'])
        starts = [runner.lanes_for(index, 3)[0] for index in range(6)]
        self.assertEqual(starts.count('ghc'), starts.count('mlf'))

    def test_default_matrix_shape(self):
        matrix, families, sizes, baseline = bench.resolve('default', None, None)
        self.assertEqual(set(bench.registry()['matrices']), {'default'})
        self.assertCountEqual(families, [
            'flat_functions', 'inferred_functions', 'inferred_poly_functions', 'inferred_poly_chain',
            'local_functions', 'dependency_chain', 'inferred_chain', 'recursive_ring', 'mono_calls',
            'poly_calls', 'tree_chain', 'balanced_tree', 'literal_table', 'higher_order_chain',
            'wide_case', 'class_instances', 'dependency_diamonds', 'state_updates',
            'captured_closures', 'wide_product', 'rank2_arguments', 'irregular_literal_table',
            'nested_poly_types', 'rank2_callbacks', 'decoder_pipeline'])
        self.assertEqual(sizes, [8, 32, 128, 1024, 8192])
        self.assertEqual(matrix['repeats'], 2)
        self.assertTrue(baseline)
        listing = subprocess.check_output([sys.executable, '-B', HERE / 'bench.py', 'list'], text=True)
        self.assertIn('cells:    126, timed compilations: 756', listing)
        with tempfile.TemporaryDirectory() as directory:
            # Enumerate the whole public generator schedule without building 8,192-node sources.
            with mock.patch.object(generate, 'program', return_value='module Main where\n'):
                generated = generate.generate(Path(directory) / 'default')
            self.assertCountEqual([(c['family'], c['size']) for c in generated],
                                  [(family, n) for family in families for n in sizes])

    def test_filtered_families_and_explicit_legacy_baseline(self):
        selected = ['inferred_functions', 'inferred_poly_functions', 'inferred_poly_chain', 'local_functions']
        _, chosen, sizes, baseline = bench.resolve('default', selected, [512])
        self.assertEqual((chosen, sizes, baseline), (selected, [512], False))
        _, chosen, sizes, baseline = bench.resolve('default', ['baseline', 'wide_case'], [8])
        self.assertEqual((chosen, sizes, baseline), (['wide_case'], [8], True))
        with tempfile.TemporaryDirectory() as directory:
            cases = generate.generate(Path(directory) / 'filtered', sizes=[8],
                                      families=['baseline', 'wide_case'])
            self.assertCountEqual([case['id'] for case in cases], ['baseline-0', 'wide_case-8'])

    def test_cold_packet_dependency_uses_two_pinned_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            item, = generate.generate(Path(directory) / 'test', [8], ['retained_packet_dependency'])
            main = Path(item['source']).read_text()
            library = Path(item['dependency']['source']).read_text()
            self.assertIn('import PacketLibrary;', main)
            self.assertIn('module PacketLibrary where', library)
            self.assertIn('probe7 :: Packet -> Int;', library)
            self.assertNotIn('probe7 :: Packet -> Int;', main)
            for x in (-11, 0, 7):
                self.assertEqual(generate.expected('retained_packet_dependency', 8, x),
                                 generate.expected('delayed_packet_fanout', 8, x))
        endpoint=bench.measured_endpoint('crate-plan-v1')
        self.assertIn('--compile-crate-plan', endpoint['driver'])
        self.assertEqual(worker.mlf_stage_names('crate-plan-v1'), ['source-to-llvm','llvm-to-executable'])

    def test_three_stage_curried_shape_has_separate_inputs_and_oracle(self):
        with tempfile.TemporaryDirectory() as directory:
            case, = generate.generate(Path(directory)/'case', [8], ['retained_curried_dependencies'])
            libraries = worker.dependencies(case)
            self.assertEqual([x['module'] for x in libraries], ['CurryLibrary','CurryFacade'])
            self.assertIn('import CurryLibrary;', Path(libraries[1]['source']).read_text())
            self.assertIn('import CurryFacade;', Path(case['source']).read_text())
            self.assertEqual(case['expected_stdout'], ['-1912\n','-1576\n','776\n'])

    def test_curried_job_list_keeps_the_independent_result(self):
        with tempfile.TemporaryDirectory() as directory:
            case, = generate.generate(Path(directory)/'case', [8], ['retained_curried_job_list'])
            lib = Path(worker.dependencies(case)[0]['source']).read_text()
            self.assertEqual(lib.count('Job (\\a'), 8)
            self.assertIn('jobs :: Jobs -> Jobs;', lib)
            self.assertIn('allJobs', Path(case['source']).read_text())
            self.assertEqual(case['expected_stdout'], ['-1912\n','-1576\n','776\n'])

    def test_cold_curried_zero_has_the_same_dependency_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            family = 'retained_curried_job_list'
            baseline, positive = generate.generate(Path(directory)/'case', [8], ['baseline',family], family)
            self.assertEqual(baseline['matched_baseline_for'], positive['family'])
            self.assertEqual(baseline['expected_stdout'], ['0\n']*3)
            names = lambda case: [lib['module'] for lib in worker.dependencies(case)]
            self.assertEqual(names(baseline), names(positive))
            for stage in ('source_sha256', 'expected_stdout'):
                self.assertEqual(baseline[stage] == positive[stage], stage == 'source_sha256')

    def matched_cases(self, family):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        zero, positive = generate.generate(directory / 'shape', [8], ['baseline', family], family)
        self.assertEqual(zero['matched_baseline_for'], family)
        return zero, positive

    def test_bounded_optional_writer_controls(self):
        family = 'bounded_optional_writers'
        zero, positive = self.matched_cases(family)
        self.assertEqual(zero['expected_stdout'], ['0\n']*5)
        self.assertEqual(positive['expected_stdout'], ['108\n', '84\n', '91\n', '99\n', '235\n'])
        for case in (zero, positive):
            self.assertIn('formatOptional encode item', Path(case['source']).read_text())
        self.assertEqual(Path(positive['source']).read_text().count('formatOptional showInt'), 8)

    def test_inferred_constructor_writers_controls(self):
        family = 'inferred_constructor_writers'
        zero, positive = self.matched_cases(family)
        self.assertEqual(zero['expected_stdout'], ['0\n']*5)
        self.assertEqual(positive['expected_stdout'], ['44\n', '-20\n', '-36\n', '136\n', '640\n'])
        self.assertEqual(Path(positive['source']).read_text().count(' query = case query of'), 8)
        self.assertIn('writeAll query writers', Path(zero['source']).read_text())

    def test_mixed_recursive_decoder_controls(self):
        family = 'mixed_recursive_decoder'
        zero, positive = self.matched_cases(family)
        self.assertEqual(zero['expected_stdout'], ['7\n', '7\n', '-37\n', '-37\n', '-37\n'])
        self.assertEqual(positive['expected_stdout'], ['7\n', '14\n', '46\n', '91\n', '-37\n'])
        self.assertEqual(Path(positive['source']).read_text().count('payload -> schedule '), 8)
        for case in (positive, zero):
            self.assertIn('schedule value rest = scan', Path(case['source']).read_text())

    def test_signed_decoder_selector_controls(self):
        family = 'signed_decoder_selectors'
        zero, positive = self.matched_cases(family)
        self.assertEqual(zero['expected_stdout'], ['-99\n'] * 5)
        self.assertEqual(positive['expected_stdout'], ['-99\n', '-11\n', '37\n', '85\n', '-99\n'])
        self.assertEqual(Path(positive['source']).read_text().count('a <- readPiece left'), 8)

    def test_production_endpoint_keeps_ordinary_crate_stages(self):
        args = (Path('/bin/emlf'), Path('/spec'), Path('/out'))
        self.assertEqual(worker.mlf_commands('crate-bootstrap-production-v1', *args),
                         worker.mlf_commands('crate-bootstrap-v1', *args))
        self.assertEqual(worker.ORDINARY_CLANG_FLAGS, ('-O2', '-Wno-override-module'))

    def test_cold_codegen_endpoint_records_fresh_matching_llvm(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            stages = worker.mlf_commands(worker.CACHED_ENDPOINT, Path('/bin/emlf'), out/'spec', out)
            self.assertEqual(stages[1][1][-4:], ['--cache', out/'codegen-cache',
                                                '--query-report', out/'codegen.json'])
            objects = out/'codegen-cache'/'objects'
            objects.mkdir(parents=True)
            checksum = 'a' * 64
            report = {'format': 1, 'input_key': 'b' * 64, 'optimized_key': checksum,
                      'compiler': 'c' * 64, 'input_reused': False, 'optimized_reused': False}
            (out/'unit.ll').write_bytes(b'generated LLVM')
            stored = objects/(checksum+'.ll')
            stored.write_bytes((out/'unit.ll').read_bytes())
            def check():
                (out/'codegen.json').write_text(json.dumps(report))
                return runner.Q.cold_codegen_evidence(out, 'c' * 64)
            self.assertEqual(check()['llvm_sha256'], hashlib.sha256(b'generated LLVM').hexdigest())
            for field in ('input_reused', 'optimized_reused'):
                report[field] = True
                with self.assertRaisesRegex(ValueError, 'must be fresh'):
                    check()
                report[field] = False
            stored.write_bytes(b'another artifact')
            with self.assertRaisesRegex(ValueError, 'must match'):
                check()

    def test_production_flags_are_queried_from_each_producer(self):
        triple = 'arm64-apple-darwin25'
        with mock.patch.object(runner.subprocess, 'check_output',
                               side_effect=['emlf --native-target-flags TRIPLE', '["-mno-outline"]',
                                            'emlf --compile SOURCE']) as query:
            self.assertEqual(runner.native_target_policy('/candidate', triple)['flags'], ['-mno-outline'])
            self.assertEqual(runner.native_target_policy('/baseline', triple)['flags'], [])
        self.assertEqual([c.args[0] for c in query.call_args_list], [
            [Path('/candidate/bin/emlf'), '--help'],
            [Path('/candidate/bin/emlf'), '--native-target-flags', triple],
            [Path('/baseline/bin/emlf'), '--help']])

    def test_fused_endpoint_has_its_own_command_and_stages(self):
        endpoint = bench.measured_endpoint('crate-fused-v1')
        self.assertIn('--compile-crate-to-llvm-gc', endpoint['driver'])
        self.assertEqual(worker.mlf_stage_names('crate-fused-v1'), ['source-to-llvm','llvm-to-executable'])
        commands = worker.mlf_commands('crate-fused-v1', Path('/emlf'), Path('/spec'), Path('/out'))
        self.assertEqual(commands[0][1], [Path('/emlf'),'--compile-crate-to-llvm-gc',Path('/spec'),'-o',Path('/out/unit')])
        self.assertEqual(commands[0][2], Path('/out/unit.ll'))
        self.assertEqual(worker.mlf_stage_names('crate-bootstrap-v1'), STAGES)
        with self.assertRaises(ValueError):
            worker.mlf_stage_names('unknown')

    def test_installed_endpoint_is_separate_from_crate_runner(self):
        self.assertIn('emlf-source-v1', bench.registry()['paired_endpoints'])
        with self.assertRaises(SystemExit):
            bench.measured_endpoint('emlf-source-v1')


class LanguageFeatureShapeTests(unittest.TestCase):
    families = ('wide_case', 'class_instances', 'dependency_diamonds', 'state_updates')

    def test_explicit_generation_preserves_source_and_oracle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = generate.generate(root / 'features', sizes=[1, 5], families=self.families)
            self.assertCountEqual([case['id'] for case in cases],
                                  [f'{family}-{n}' for family in self.families for n in (1, 5)])
            for case in cases:
                path = Path(case['source'])
                self.assertEqual(digest(path), case['source_sha256'])
                for argument, stdout in zip(case['inputs'], case['expected_stdout'], strict=True):
                    if case['family'] == 'wide_case' and argument == '--all':
                        self.assertEqual(stdout, ''.join(f'{v}\n' for v in range(1, 2*case['size'], 2)))
                    else:
                        self.assertEqual(stdout, f"{self.reference(case['family'], case['size'], argument)}\n")

    @staticmethod
    def reference(family, size, x):
        if family == 'wide_case':
            arm = sum(x >= threshold for threshold in range(1, size))
            return x + 2 * arm + 1
        if family == 'class_instances':
            return sum((i + 1) * (x + i) for i in range(size))
        result = x
        for i in range(size):
            if family == 'state_updates':
                result = i - result
            elif family == 'dependency_diamonds':
                result += (i + 1) if x < 0 else -(i + 1)
            else:
                raise ValueError(family)
        return result

    def test_oracles_cover_all_small_arms_both_branches_and_update_parities(self):
        for family in self.families:
            for size in (1, 2, 5, 8):
                for x in range(-size - 1, size + 2):
                    with self.subTest(family=family, size=size, x=x):
                        self.assertEqual(generate.expected(family, size, x),
                                         self.reference(family, size, x))

    def test_every_diamond_forks_and_rejoins_the_previous_stage(self):
        size = 5
        source = generate.program('dependency_diamonds', size)
        bodies = dict(re.findall(r'^([a-z]\w*) [\w ]+ = (.+);$', source, re.MULTILINE))

        def calls(name):
            return [word for word in re.findall(r'\b\w+\b', bodies[name]) if word in bodies]

        stage, = calls('entry')
        visited = set()
        for _ in range(size):
            left, right = calls(stage)
            self.assertEqual(len({stage, left, right} - visited), 3)
            visited.update((stage, left, right))
            predecessor, = calls(left)
            self.assertEqual(calls(right), [predecessor])
            stage = predecessor
        self.assertNotIn(stage, visited)
        self.assertEqual(calls(stage), [])

    def test_wide_case_constructs_and_matches_each_tag(self):
        for size in (1, 5, 8):
            source = generate.program('wide_case', size)
            tags = [str(i) for i in range(size)]
            data = re.search(r'\bdata Tag = ([^;]+);', source)
            self.assertIsNotNone(data)
            self.assertCountEqual(re.findall(r'\bTag(\d+)\b', data[1]), tags)
            branches = re.findall(r'\bTag(\d+)\s*->\s*(\d+)', source)
            self.assertCountEqual(branches, [(str(i), str(2 * i + 1)) for i in range(size)])
            # Each alternative must also be produced somewhere on the selector path.
            self.assertCountEqual(re.findall(r'\bTag(\d+)\b', source), tags * 3)
            self.assertCountEqual(re.findall(r'ltInt x (\d+)', source), tags[1:])
            self.assertIn('selectedScore i = score (pick i)', source)
            self.assertIn('entry x = addInt x (selectedScore x)', source)
            self.assertIn('if eqString text "--all" then printAll 0 else printInt (entry (readInt text))', source)
            self.assertIn(f'printAll i = if eqInt i {size} then ioReturn ()', source)
            self.assertIn(r'ioBind (printInt (selectedScore i)) (\_ -> printAll (addInt i 1))', source)

    def test_wide_case_batch_detects_missing_or_swapped_interior_arms(self):
        n = 7
        source = generate.program('wide_case', n)
        original = 'Tag1 -> 3; Tag2 -> 5;'
        self.assertIn(original, source)
        with tempfile.TemporaryDirectory() as directory:
            for label, replacement in [('omitted', 'Tag2 -> 5;'), ('swapped', 'Tag1 -> 5; Tag2 -> 3;')]:
                with self.subTest(label=label), mock.patch.object(generate, 'program',
                        return_value=source.replace(original, replacement)):
                    case, = generate.generate(Path(directory)/label, sizes=[n], families=['wide_case'])
                    arms = {int(i): int(v) for i, v in re.findall(r'\bTag(\d+) -> (\d+)',
                                                                    Path(case['source']).read_text())}
                    self.assertEqual(case['inputs'], [-1, 3, 7, '--all'])
                    spots = [x + arms[min(n-1, max(x, 0))] for x in case['inputs'][:-1]]
                    self.assertEqual(case['expected_stdout'][:-1], [f'{v}\n' for v in spots])
                    batch = case['expected_stdout'][-1]
                    self.assertEqual(batch, '1\n3\n5\n7\n9\n11\n13\n')
                    self.assertNotEqual(batch, ''.join(f'{arms[i]}\n' for i in sorted(arms)))
        largest = generate.expected_output('wide_case', 8192, '--all').splitlines()
        self.assertEqual(len(largest), 8192)
        self.assertEqual((largest[0], largest[4096], largest[-1]), ('1', '8193', '16383'))

    def test_entry_calls_the_constrained_method_for_every_instance(self):
        size = 5
        source = generate.program('class_instances', size)
        ids = [str(i) for i in range(size)]
        self.assertEqual(source.count('class Score '), 1)
        self.assertCountEqual(re.findall(r'\bdata Box(\d+)\b', source), ids)
        self.assertCountEqual(re.findall(r'\binstance Score Box(\d+)\b', source), ids)
        self.assertRegex(source, r'measure :: [^;]*Score [a-z]+[^;]*=>')
        self.assertRegex(source, r'measure (\w+) = score \1;')
        self.assertCountEqual(re.findall(r'\bmeasure \(Box(\d+)\b', source), ids)

    def test_state_updates_read_and_replace_one_cell_in_source_order(self):
        for size in (1, 5, 8):
            source = generate.program('state_updates', size)
            self.assertEqual(source.count('newIntArray '), 1)
            self.assertIn('cell <- newIntArray 1 x', source)
            self.assertEqual(source.count('readIntArray '), size + 1)
            self.assertEqual(source.count('writeIntArray '), size)
            updates = re.findall(r'(\w+) <- readIntArray cell 0;\s*'
                                 r'writeIntArray cell 0 \(subInt (\d+) \1\)', source)
            self.assertEqual([int(index) for _, index in updates], list(range(size)))
            self.assertIn('readIntArray cell 0 };', source)
            self.assertIn('ioBind (entry (readInt text)) printInt', source)


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

    def test_rejects_invalid_sampled_peak_rss(self):
        folder = write_cohort(self.root)
        for peak in (False, -1, 1.5, float('inf'), float('nan'), '10'):
            with self.subTest(peak=peak):
                edit(folder, lambda r: r['runs'][0]['command'].update({analyze.RSS_SAMPLE: peak}))
                with self.assertRaisesRegex(ValueError, 'invalid sampled peak RSS.*ghc at position 0'):
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
        case, = analyze.load(folder / 'plan.json')['cases']
        Path(case['source']).write_text('entry x = x + 1\n')
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
        def add_rss(receipt):
            mib = 2**20
            peaks = {'mlf': (3, 1, 2), 'ghc': (6, 5, 4)}
            for run in receipt['runs']:
                run['command'][analyze.RSS_SAMPLE] = mib * peaks[run['lane']][run['position'] // 2]
                run['command']['max_individual_child_rss_bytes'] = 7 * mib
        edit(folder, add_rss)
        output = self.root / 'results'
        process = subprocess.run([sys.executable, '-B', str(HERE / 'analyze.py'), str(folder),
                                  '--output', str(output)], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        for name in ['summary.json', 'summary.csv', 'samples.csv', 'summary.md']:
            self.assertTrue((output / name).is_file(), name)
        summary = (output / 'summary.md').read_text()
        self.assertIn('MLF median', summary)
        self.assertIn('Build performance checks', summary)
        self.assertIn('| `flat_functions` | 8 | 2.00 | 5.00 | 0.400 |', summary)
        report = analyze.load(output / 'summary.json')
        record, = report['cohorts'][0]['growth']
        self.assertEqual(record['status'], 'incomplete')
        self.assertFalse(record['checks']['all_positive_medians_lower'])
        self.assertTrue(record['checks']['peak_rss_at_most_ghc'])
        self.assertEqual(record['peak_rss'][0]['mlf_over_ghc_peak_rss'], .4)
        self.assertIn('sampled_process_tree_peak_rss_bytes', (output / 'samples.csv').read_text().splitlines()[0])

        standalone = analyze.save_recorded_growth(folder)
        self.assertIn('| `flat_functions` | 8 | 2.00 | 5.00 | 0.400 |', standalone.read_text())
        self.assertEqual(analyze.load(folder / 'growth.json')['growth'], [record])

    def test_recorded_growth_reports_failed_cohorts_without_estimates(self):
        folder = write_cohort(self.root)
        edit(folder, lambda r: r.update(all_cases_passed=False, failures=[{'case': 'flat_functions-8'}]))
        report = analyze.save_recorded_growth(folder)
        self.assertTrue(report.is_file())
        data, = analyze.load(folder / 'growth.json')['growth']
        self.assertEqual(data['status'], 'incomplete')
        self.assertIn('flat_functions-8', data['reason'])
        self.assertTrue(all(value is None for value in data['checks'].values()))

    def test_installed_summary_compares_sampled_build_group_peaks(self):
        with mock.patch.object(sys, 'path', sys.path.copy()):
            from installed import summarize

        peaks = {'before': (100, 300, 200), 'after': (500, 350, 450), 'ghc': (400, 200, 300)}
        samples = [dict(case='shape', state='fresh', lane=lane, passed=True,
                        wall_s=1.0, user_s=.5, system_s=.1,
                        peak_rss_bytes=900, sampled_group_rss_bytes=peak)
                   for lane, group in peaks.items() for peak in group]
        row, = summarize(['shape'], samples, 3, ['fresh'])
        self.assertEqual(row['medians']['before']['sampled_group_rss_bytes'], 200)
        self.assertEqual(row['medians']['before']['peak_rss_bytes'], 900)
        self.assertAlmostEqual(row['before_over_ghc_peak_rss'], 2 / 3)
        self.assertTrue(row['before_peak_rss_at_most_ghc'])
        self.assertEqual(row['after_over_ghc_peak_rss'], 1.5)
        self.assertFalse(row['after_peak_rss_at_most_ghc'])

        samples[0]['sampled_group_rss_bytes'] = 0
        row, = summarize(['shape'], samples, 3, ['fresh'])
        self.assertIsNone(row['before_peak_rss_at_most_ghc'])
        self.assertIsNone(row['before_over_ghc_peak_rss'])

    def test_fused_analysis_keeps_its_stage_inventory(self):
        folder = write_cohort(self.root, endpoint='crate-fused-v1')
        rows, _, _, _ = analyze.analyze(folder)
        self.assertIn('source-to-llvm_wall_seconds_median', rows[0])
        self.assertNotIn('source-to-checked_wall_seconds_median', rows[0])

    def test_cli_rejects_incompatible_cohorts(self):
        write_cohort(self.root, label='screen')
        write_cohort(self.root, label='other', endpoint='crate-fused-v1')
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



# Author the current wire columns directly so evidence checks see the same
# schema as a cold compiler run. Repeated groups share an inference payload.
def graph_fixture(groups=1, members_per_group=None, crate='compiler-shapes/flat_functions-8',
                  mutate_index=None):
    from artifact_binary_reference import tree_document
    from artifact_binary_typed import l, n, pack, s
    def i(value):
        return ('int', value)

    bindings = ['imported', 'alias']
    members_per_group = members_per_group or [['f' + str(index)] for index in range(groups)]
    declarations = bindings + [name for members in members_per_group for name in sorted(members)]
    evidence_payload, raw = b'fixture evidence payload', b'fixture inferred payload'
    binding_hash = hashlib.sha256(b'fixture shared binding').hexdigest()
    evidence_hash, raw_hash = (hashlib.sha256(payload).hexdigest() for payload in (evidence_payload, raw))
    configuration = pack([crate, 'b' * 64, 'MLF-SOURCE-CRATE-QUERY-7',
                          'open-fragment-checker-1/finish-receipt-1', 'source'])
    keys = [n(415, i(0)), i(0), i(1), n(432, i(0))]
    hashes = [s(binding_hash)] * 3 + [s(evidence_hash)]
    read_counts = [i(0), i(1), i(1), i(0)]
    targets = [keys[0], keys[1]]
    payload_rows = [i(3)]
    table = []
    report = {'format': 1, 'crate': crate, 'inferred_groups': len(members_per_group),
              'reused_groups': 0, 'groups': []}
    for slot, members in enumerate(members_per_group):
        table.append(l(*(i(declarations.index(name)) for name in sorted(members))))
        payload_rows.append(i(len(keys)))
        keys.append(n(419, i(slot)))
        hashes.append(s(raw_hash))
        read_counts.append(i(1))
        targets.append(keys[1])
        report['groups'].append({'id': analyze.Q.compact_group_owner(crate, members),
                                 'members': members, 'cached': False, 'query_key': raw_hash})

    fields = [s('MLF-CRATE-QUERY-GRAPH-3'), s(configuration), l(*map(s, declarations)),
              l(*table), l(n(414, i(0), i(0), s('Eq Int'))), l(),
              l(*keys), l(*hashes), l(*read_counts), l(*targets),
              l(*payload_rows)]
    if mutate_index:
        mutate_index(fields)
    index = tree_document([n(412, *fields)], 6)
    generation = hashlib.sha256(index).hexdigest()
    files = {analyze.Q.GRAPH + 'CURRENT': tree_document([s(generation)], 6),
             analyze.Q.GRAPH + 'generations/' + generation + '.mlfqg': index}
    evidence = {'format': 1, 'query_report_json': json.dumps(report),
                'files_base64': {path: base64.b64encode(data).decode('ascii')
                                 for path, data in files.items()}}
    for data in [evidence_payload, raw]:
        files[analyze.Q.GRAPH + 'results/' + hashlib.sha256(data).hexdigest() + '.mlfqr'] = data
    inventory = {path: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                 for path, data in files.items()}
    return inventory, evidence


def change_report(evidence, mutate):
    report = json.loads(evidence['query_report_json'])
    mutate(report)
    evidence['query_report_json'] = json.dumps(report)


class GraphCacheTests(unittest.TestCase):
    def check(self, inventory, evidence, groups=1, max_members=1):
        return analyze.Q.check_graph(inventory, evidence, groups, max_members,
                                     'compiler-shapes/flat_functions-8', 'b' * 64)

    def test_owner_matches_crate_and_complete_membership(self):
        crate = 'compiler-shapes/flat_functions-8'
        # The compact name encodes slash, underscore and hyphen from the crate.
        prefix = 'compilerz2dzshapesz2fzflatz5fzfunctionsz2dz8_'
        members = ['module_c1_' + prefix + 'x', 'Module_c1_' + prefix + 'T', 'raw:λ']
        pack = analyze.Q.pack
        owner = pack(['MLF-OPEN-GROUP-3', crate, pack([pack(['type', 'T']),
                      pack(['value', 'x']), pack(['raw', 'raw:λ'])])])
        inventory, evidence = graph_fixture(members_per_group=[members])
        change_report(evidence, lambda q: q['groups'][0].update(id=owner))
        self.check(inventory, evidence, max_members=3)
        for wrong_crate, wrong_members in [(crate, members[:-1]), ('other', members),
                                           (crate, members + ['extra']), (crate, [])]:
            changed = copy.deepcopy(evidence)
            wrong = analyze.Q.compact_group_owner(wrong_crate, wrong_members)
            change_report(changed, lambda q: q['groups'][0].update(id=wrong))
            with self.assertRaisesRegex(ValueError, 'group id matches'):
                self.check(inventory, changed, max_members=3)

    def test_accepts_extra_nodes_and_content_deduplication(self):
        inventory, evidence = graph_fixture(groups=3)
        result = self.check(inventory, evidence, groups=3)
        self.assertEqual(len(result['groups']), 3)
        self.assertEqual(result['files'], 4)  # CURRENT, index, two unique payloads
        self.assertEqual(result['bytes'], sum(v['bytes'] for v in inventory.values()))

    def test_rejects_missing_evidence(self):
        inventory, _ = graph_fixture()
        with self.assertRaisesRegex(ValueError, 're-measure'):
            self.check(inventory, None)

    def test_rejects_missing_payload(self):
        inventory, evidence = graph_fixture()
        del inventory[next(p for p in inventory if p.endswith('.mlfqr'))]
        with self.assertRaisesRegex(ValueError, 'missing retained payload'):
            self.check(inventory, evidence)

    def test_rejects_bad_content_address(self):
        inventory, evidence = graph_fixture()
        inventory[next(p for p in inventory if p.endswith('.mlfqr'))]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'content-addressed query graph SHA'):
            self.check(inventory, evidence)

    def test_rejects_nonfinite_fractional_or_boolean_sizes(self):
        for size in [float('inf'), float('nan'), 1.5, True, -1]:
            inventory, evidence = graph_fixture()
            inventory[next(iter(inventory))]['bytes'] = size
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, 'finite integral'):
                self.check(inventory, evidence)

    def test_rejects_tampered_retained_bytes(self):
        inventory, evidence = graph_fixture()
        evidence['files_base64'][analyze.Q.GRAPH + 'CURRENT'] = 'AAAA'
        with self.assertRaisesRegex(ValueError, 'retained query graph bytes'):
            self.check(inventory, evidence)

    def test_rejects_current_selecting_other_generation(self):
        from artifact_binary_reference import tree_document
        inventory, evidence = graph_fixture()
        current = analyze.Q.GRAPH + 'CURRENT'
        wrong = tree_document([('text', '0' * 64)], 6)
        evidence['files_base64'][current] = base64.b64encode(wrong).decode('ascii')
        inventory[current] = {'bytes': len(wrong), 'sha256': hashlib.sha256(wrong).hexdigest()}
        with self.assertRaisesRegex(ValueError, 'CURRENT selects'):
            self.check(inventory, evidence)

    def test_rejects_corrupt_column_evidence(self):
        from artifact_binary_typed import l, list_values, n, s
        def duplicate_key(fields):
            keys = list_values(fields[6])
            fields[6] = l(keys[1], *keys[1:])
        def dangling_read(fields):
            targets = list_values(fields[9])
            fields[9] = l(*targets[:-1], n(415, ('int', 1)))
        def cyclic_read(fields):
            targets = list_values(fields[9])
            fields[9] = l(('int', 0), *targets[1:])
        def missing_group_payload(fields):
            fields[10] = l(*list_values(fields[10])[:-1])
        def obsolete_marker(fields):
            fields[0] = s('MLF-CRATE-QUERY-GRAPH-2')
        for mutate in [duplicate_key, dangling_read, cyclic_read, missing_group_payload, obsolete_marker]:
            with self.subTest(mutation=mutate.__name__), self.assertRaises(ValueError):
                self.check(*graph_fixture(mutate_index=mutate))

    def test_accepts_ordered_duplicate_reads(self):
        from artifact_binary_typed import l, list_values
        def mutate(fields):
            counts, targets = map(list_values, fields[8:10])
            fields[8] = l(*counts[:-1], ('int', 3))
            fields[9] = l(*targets, ('int', 1), ('int', 0))
        inventory, evidence = graph_fixture(mutate_index=mutate)
        self.check(inventory, evidence)
        index = next(data for path, data in evidence['files_base64'].items() if path.endswith('.mlfqg'))
        nodes = analyze.Q.Generation(base64.b64decode(index)).nodes
        pack = analyze.Q.pack
        reads = nodes[pack(['InferScc', pack(['f0'])])]['reads']
        self.assertEqual([key for key, _ in reads], [pack(['Binding', name])
                                                    for name in ['imported', 'alias', 'imported']])

    def test_rejects_wrong_infer_identity_or_hash(self):
        for field, value in [('members', ['other']), ('query_key', '0' * 64)]:
            inventory, evidence = graph_fixture()
            change_report(evidence, lambda q: q['groups'][0].__setitem__(field, value))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'exact InferScc|group id matches'):
                self.check(inventory, evidence)

    def test_rejects_wrong_report_crate_format_or_group_id(self):
        for mutate in [
            lambda q: q.update(crate='other'),
            lambda q: q.update(format=True),
            lambda q: q['groups'][0].update(id='unrelated'),
        ]:
            inventory, evidence = graph_fixture()
            change_report(evidence, mutate)
            with self.assertRaises(ValueError):
                self.check(inventory, evidence)

    def test_rejects_wrong_measured_crate_or_compiler(self):
        for crate, compiler in [('other', 'b' * 64), ('compiler-shapes/flat_functions-8', 'c' * 64)]:
            inventory, evidence = graph_fixture()
            change_report(evidence, lambda report: report.update(crate=crate))
            with self.assertRaisesRegex(ValueError, 'crate/compiler configuration'):
                analyze.Q.check_graph(inventory, evidence, 1, 1, crate, compiler)

    def test_rejects_missing_or_duplicate_report_groups(self):
        for mode in ['missing', 'duplicate', 'overlapping', 'extra-graph']:
            inventory, evidence = graph_fixture(groups=2)
            report = json.loads(evidence['query_report_json'])
            groups = report['groups']
            if mode == 'missing':
                groups.pop()
            elif mode == 'duplicate':
                groups[1]['id'] = groups[0]['id']
            elif mode == 'overlapping':
                groups[1]['members'] = groups[0]['members']
            else:
                groups.pop()
                report['inferred_groups'] = 1
            evidence['query_report_json'] = json.dumps(report)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.check(inventory, evidence, groups=1 if mode == 'extra-graph' else 2)

    def test_rejects_warm_report_and_false_counts(self):
        for mutate in [
            lambda q: q.update(reused_groups=1),
            lambda q: q.update(inferred_groups=2),
            lambda q: q.update(inferred_groups=True),
            lambda q: q['groups'][0].update(cached=True),
        ]:
            inventory, evidence = graph_fixture()
            change_report(evidence, mutate)
            with self.assertRaises(ValueError):
                self.check(inventory, evidence)

    def test_rejects_duplicate_report_json_keys(self):
        inventory, evidence = graph_fixture()
        evidence['query_report_json'] = '{"inferred_groups":1,' + evidence['query_report_json'][1:]
        with self.assertRaisesRegex(ValueError, 'duplicate query report JSON key'):
            self.check(inventory, evidence)

    def test_rejects_extra_generation(self):
        inventory, evidence = graph_fixture()
        inventory[analyze.Q.GRAPH + 'generations/' + '0' * 64 + '.mlfqg'] = {
            'bytes': 1, 'sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'one committed graph generation'):
            self.check(inventory, evidence)

    def test_rejects_mixed_storage_and_unpublished_staging(self):
        for extra in ['legacy.mlfq', 'query-graph-v2/CURRENT', analyze.Q.GRAPH + 'staging/incomplete']:
            inventory, evidence = graph_fixture()
            inventory[extra] = {'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()}
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.check(inventory, evidence)

    def test_rejects_complete_graph_in_retired_directory(self):
        inventory, evidence = graph_fixture()
        for mapping in (inventory, evidence['files_base64']):
            for path in list(mapping):
                mapping[path.replace(analyze.Q.GRAPH, 'query-graph-v2/')] = mapping.pop(path)
        with self.assertRaisesRegex(ValueError, 'one committed graph generation'):
            self.check(inventory, evidence)

    def test_snapshot_retains_exact_actual_inputs(self):
        _, evidence = graph_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            query = root / 'queries'
            for name, value in evidence['files_base64'].items():
                path = query / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(base64.b64decode(value))
            report = root / 'unit.queries'
            report.write_text(evidence['query_report_json'])
            destination = root / 'query-graph-evidence.json'
            analyze.Q.snapshot(query, report, destination)
            self.assertEqual(json.loads(destination.read_text()), evidence)


class GraphAnalyzerTests(unittest.TestCase):
    def test_graph_cohort_and_existing_raw_reuse_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = write_cohort(directory)
            rows, _, _, samples = analyze.analyze(folder)
            self.assertEqual(rows[0]['query_storage'], 'query-graph-v3')
            self.assertEqual(rows[0]['fresh'], 1)
            self.assertEqual(rows[0]['query_files'], 4)
            self.assertEqual(len(samples), 6)
            edit(folder, lambda r: r['runs'][-1].update(raw_compared_with_first_mlf_leg=False))
            with self.assertRaisesRegex(ValueError, 'actual raw-byte comparisons'):
                analyze.analyze(folder)

    def test_baseline_inventory_is_opaque_and_requires_cold_groups(self):
        _, evidence = graph_fixture()
        inventory = {'baseline/state': {'bytes': 9, 'sha256': '8' * 64}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'unit.queries'
            report.write_text(evidence['query_report_json'])
            sidecar = root / 'evidence.json'
            analyze.Q.snapshot(root, report, sidecar, reference=True)
            recorded = json.loads(sidecar.read_text())
            self.assertEqual(recorded['files_base64'], {})
            args = (1, 1, 'compiler-shapes/flat_functions-8')
            totals = analyze.Q.check_reference_inventory(inventory, recorded, *args)
            self.assertEqual((totals['files'], totals['bytes']), (1, 9))
            with self.assertRaisesRegex(ValueError, 'one committed graph generation'):
                analyze.Q.check_graph(inventory, recorded, *args, 'b' * 64)
            change_report(recorded, lambda q: q.update(reused_groups=1))
            with self.assertRaisesRegex(ValueError, 'fresh/reused counts'):
                analyze.Q.check_reference_inventory(inventory, recorded, *args)

    def test_file_count_alone_cannot_qualify_a_cohort(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = write_cohort(directory)
            for leg in (folder / 'legs').iterdir():
                (leg / 'query-graph-evidence.json').unlink()
                (leg / 'query-cache-inventory.json').write_text(json.dumps(
                    {'q.mlfq': {'bytes': 10, 'sha256': 'f' * 64}}))
            with self.assertRaisesRegex(ValueError, 'query graph evidence missing'):
                analyze.analyze(folder)

    def test_rejects_inventory_drift_with_same_file_count(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = write_cohort(directory)
            inventory, evidence = graph_fixture()
            legs = sorted((folder / 'legs').iterdir())
            for i, leg in enumerate(legs):
                if i == 2:
                    inventory[next(p for p in inventory if p.endswith('.mlfqr'))]['bytes'] += 1
                (leg / 'query-cache-inventory.json').write_text(json.dumps(inventory))
                (leg / 'query-graph-evidence.json').write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, 'stable graph inventory'):
                analyze.analyze(folder)

class GraphReaderPinTests(unittest.TestCase):
    def test_runner_pins_index_reference(self):
        import ast
        source = (HERE / 'run.py').read_text()
        tree = ast.parse(source)
        inputs = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.Assign) and
                      any(isinstance(target, ast.Name) and target.id == 'inputs'
                          for target in node.targets))
        pinned = [node.value for node in ast.walk(inputs) if isinstance(node, ast.Constant)]
        for name in ['query_generation.py', 'artifact_binary_open.py', 'artifact_binary_typed.py',
                     'artifact_structure_contract.json', 'command_runner.py', 'bench.py',
                     'fit_growth.py', 'analyze.py']:
            self.assertIn(name, pinned)


class Rank2ArgumentTests(unittest.TestCase):
    def test_sites_pass_polymorphic_selectors_used_at_int_and_bool(self):
        for size in (1, 2, 5, 32):
            with self.subTest(size=size):
                source = generate.program('rank2_arguments', size)
                self.assertIn('probe :: (forall a. a -> a -> a) -> Int -> Int -> Int', source)
                self.assertIn('pick (addInt x offset) (addInt (mulInt 2 x) offset)', source)
                self.assertIn('if pick (ltInt x 0) (ltInt 0 x)', source)
                entry = next(line for line in source.splitlines() if line.startswith('entry x ='))
                calls = re.findall(r'probe \(\\left right -> (left|right)\) x (\d+)', entry)
                self.assertEqual(calls, [('left' if i % 2 == 0 else 'right', str(i))
                                         for i in range(size)])

    def test_closed_form_matches_first_and_second_projections(self):
        for size in (1, 2, 3, 8, 31):
            for x in (-13, -1, 0, 1, 7):
                with self.subTest(size=size, x=x):
                    total = 0
                    for i in range(size):
                        index = i % 2
                        number = (x + i, 2 * x + i)[index]
                        increment = (x < 0, x > 0)[index]
                        total += number + int(increment)
                    self.assertEqual(generate.expected('rank2_arguments', size, x), total)


if __name__ == '__main__':
    unittest.main()
