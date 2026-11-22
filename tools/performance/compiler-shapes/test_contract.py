#!/usr/bin/env python3
"""Contract tests for the compiler shape benchmark. No compiler is required.

These tests use synthetic receipts to prove that the analyzer refuses missing,
duplicate, non-finite, failed, qualified-only and incompatible data, and that the
frozen schedule stays balanced.
"""
import copy
import hashlib
import json
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
                       'patch_bytes': 0, 'patch_sha256': hashlib.sha256(b'').hexdigest()},
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
                   'system_seconds': wall / 20} for name in (worker.mlf_stage_names(endpoint) if endpoint in ['crate-bootstrap-v1','crate-fused-v1'] else STAGES)] if item['lane'] == 'mlf' else []
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
        self.assertIn('cells:    126, timed compilations: 504', listing)
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



# Graph fixtures are independently encoded by the frozen wire-format reference,
# not a compiler run and never a substitute for retained measurement evidence.
def graph_fixture(groups=1, mutate_nodes=None, version=1, mutate_index=None,
                  members_per_group=None):
    import base64
    import query_cache as Q
    from artifact_binary_reference import tree_document
    def s(value): return ('text', value)
    def n(tag, *children): return ('node', tag, tuple(children))
    def l(*children): return n(1, *children)
    raw_hash = hashlib.sha256(b'fixture raw payload').hexdigest()
    binding_hash = hashlib.sha256(b'fixture shared binding').hexdigest()
    binding = Q.pack(['Binding', 'imported'])
    nodes = [
        {'key': Q.pack(['Input', binding]), 'hash': binding_hash, 'reads': [], 'payload': None},
        {'key': binding, 'hash': binding_hash,
         'reads': [(Q.pack(['Input', binding]), binding_hash)], 'payload': binding_hash},
        {'key': Q.pack(['Binding', 'alias']), 'hash': binding_hash,
         'reads': [(binding, binding_hash)], 'payload': binding_hash},
    ]
    crate = 'compiler-shapes/flat_functions-8'
    report = {'format': 1, 'crate': crate, 'inferred_groups': groups,
              'reused_groups': 0, 'groups': []}
    for i in range(groups):
        members = members_per_group[i] if members_per_group is not None else ['f' + str(i)]
        key = Q.pack(['InferScc', Q.pack(sorted(members))])
        nodes.append({'key': key, 'hash': raw_hash,
                      'reads': [(binding, binding_hash)], 'payload': raw_hash})
        identity = 'Query_' + ''.join(str(ord(c)) + '_' for c in crate) + 'z_' + ''.join(
            str(ord(c)) + '_' for c in min(members))
        report['groups'].append({'id': identity, 'members': members,
                                'cached': False, 'query_key': raw_hash})
    if mutate_nodes:
        mutate_nodes(nodes)
    configuration = Q.pack([crate, 'b' * 64, 'fixture source format', 'open-fragment-checker-1', 'source'])
    if version == 1:
        value = n(411, s('MLF-CRATE-QUERY-GRAPH-1'), s(configuration),
        l(*(n(410, s(x['key']), s(x['hash']),
               l(*(n(2, s(k), s(h)) for k, h in x['reads'])),
               n(4) if x['payload'] is None else n(5, s(x['payload']))) for x in nodes)))
    else:
        strings = sorted({value for x in nodes
                          for value in [x['key'], x['hash'],
                                        *(v for edge in x['reads'] for v in edge),
                                        *([] if x['payload'] is None else [x['payload']])]})
        ids = {value: i for i, value in enumerate(strings)}
        def ref(value): return ('int', ids[value])
        value = n(412, s('MLF-CRATE-QUERY-GRAPH-2'), s(configuration),
                  l(*(s(value) for value in strings)),
                  l(*(n(413, ref(x['key']), ref(x['hash']),
                         l(*(n(2, ref(k), ref(h)) for k, h in x['reads'])),
                         n(4) if x['payload'] is None else n(5, ref(x['payload'])))
                      for x in sorted(nodes, key=lambda x: x['key']))))
    if mutate_index:
        value = mutate_index(value)
    index = tree_document([value], 6)
    generation = hashlib.sha256(index).hexdigest()
    current = tree_document([s(generation)], 6)
    files = {Q.GRAPH + 'CURRENT': current, Q.GRAPH + 'generations/' + generation + '.mlfqg': index}
    inventory = {p: {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()} for p, b in files.items()}
    for h in [binding_hash, raw_hash]:
        inventory[Q.GRAPH + 'results/' + h + '.mlfqr'] = {'bytes': 40, 'sha256': h}
    evidence = {'format': 1, 'query_report_json': json.dumps(report),
                'files_base64': {p: base64.b64encode(b).decode('ascii') for p, b in files.items()}}
    return inventory, evidence


def change_report(evidence, mutate):
    report = json.loads(evidence['query_report_json'])
    mutate(report)
    evidence['query_report_json'] = json.dumps(report)


class GraphCacheTests(unittest.TestCase):
    version = 1

    def fixture(self, **kwargs):
        return graph_fixture(version=self.version, **kwargs)

    def index_error(self, legacy, indexed):
        return legacy if self.version == 1 else indexed

    def check(self, inventory, evidence, groups=1, max_members=1):
        return analyze.Q.check_graph(inventory, evidence, groups, max_members,
                                     'compiler-shapes/flat_functions-8', 'b' * 64)

    def test_accepts_complete_framed_group_owner(self):
        for members in [['f0'], ['bc', 'a'], ['中文', 'é']]:
            inventory, evidence = self.fixture(members_per_group=[members])
            change_report(evidence, lambda q: q['groups'][0].update(id=analyze.Q.pack([
                'MLF-OPEN-GROUP-1', q['crate'], analyze.Q.pack(sorted(members))])))
            with self.subTest(members=members):
                self.check(inventory, evidence, max_members=len(members))

    def test_rejects_framed_owner_with_different_full_membership(self):
        crate = 'compiler-shapes/flat_functions-8'
        for owner_crate, members in [
            ('other', ['a', 'bc']), (crate, []), (crate, ['a']),
            (crate, ['a', 'bc', 'd']), (crate, ['ab', 'c']),
            (crate, ['bc', 'a']), (crate, ['a', 'a', 'bc']),
        ]:
            inventory, evidence = self.fixture(members_per_group=[['bc', 'a']])
            owner = analyze.Q.pack(['MLF-OPEN-GROUP-1', owner_crate, analyze.Q.pack(members)])
            change_report(evidence, lambda q: q['groups'][0].update(id=owner))
            with self.subTest(crate=owner_crate, members=members), self.assertRaisesRegex(
                    ValueError, 'group id matches'):
                self.check(inventory, evidence, max_members=2)

    def test_compact_owner_matches_complete_membership(self):
        crate = 'compiler-shapes/flat_functions-8'
        prefix = ''.join(str(ord(c)) + '_' for c in crate) + 'z_'
        members = ['module_' + prefix + '97_', 'Module_' + prefix + '84_', 'raw:λ']
        inventory, evidence = self.fixture(members_per_group=[members])
        owner = analyze.Q.compact_group_owner(crate, members)
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
        inventory, evidence = self.fixture(groups=3)
        result = self.check(inventory, evidence, groups=3)
        self.assertEqual(len(result['groups']), 3)
        self.assertEqual(result['files'], 4)  # CURRENT, index, two unique payloads
        self.assertEqual(result['bytes'], sum(v['bytes'] for v in inventory.values()))

    def test_rejects_missing_evidence(self):
        inventory, _ = self.fixture()
        with self.assertRaisesRegex(ValueError, 're-measure'):
            self.check(inventory, None)

    def test_rejects_missing_payload(self):
        inventory, evidence = self.fixture()
        del inventory[next(p for p in inventory if p.endswith('.mlfqr'))]
        with self.assertRaisesRegex(ValueError, 'missing retained payload'):
            self.check(inventory, evidence)

    def test_rejects_bad_content_address(self):
        inventory, evidence = self.fixture()
        inventory[next(p for p in inventory if p.endswith('.mlfqr'))]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'content-addressed query graph SHA'):
            self.check(inventory, evidence)

    def test_rejects_nonfinite_fractional_or_boolean_sizes(self):
        for size in [float('inf'), float('nan'), 1.5, True, -1]:
            inventory, evidence = self.fixture()
            inventory[next(iter(inventory))]['bytes'] = size
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, 'finite integral'):
                self.check(inventory, evidence)

    def test_rejects_tampered_retained_bytes(self):
        inventory, evidence = self.fixture()
        evidence['files_base64'][analyze.Q.GRAPH + 'CURRENT'] = 'AAAA'
        with self.assertRaisesRegex(ValueError, 'retained query graph bytes'):
            self.check(inventory, evidence)

    def test_rejects_current_selecting_other_generation(self):
        import base64
        from artifact_binary_reference import tree_document
        inventory, evidence = self.fixture()
        current = analyze.Q.GRAPH + 'CURRENT'
        wrong = tree_document([('text', '0' * 64)], 6)
        evidence['files_base64'][current] = base64.b64encode(wrong).decode('ascii')
        inventory[current] = {'bytes': len(wrong), 'sha256': hashlib.sha256(wrong).hexdigest()}
        with self.assertRaisesRegex(ValueError, 'CURRENT selects'):
            self.check(inventory, evidence)

    def test_rejects_duplicate_node_keys(self):
        inventory, evidence = self.fixture(mutate_nodes=lambda ns: ns.append(dict(ns[0])))
        with self.assertRaisesRegex(ValueError, self.index_error('unique query graph keys', 'row canonicality')):
            self.check(inventory, evidence)

    def test_rejects_missing_or_stale_dependency(self):
        for missing in [True, False]:
            def mutate(ns):
                ns[-1]['reads'] = [('absent' if missing else ns[0]['key'], '0' * 64)]
            inventory, evidence = self.fixture(mutate_nodes=mutate)
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, self.index_error('missing/stale', 'missing dependency|stale dependency')):
                self.check(inventory, evidence)

    def test_rejects_graph_cycle(self):
        def mutate(ns):
            ns[0]['reads'] = [(ns[1]['key'], ns[1]['hash'])]
        inventory, evidence = self.fixture(mutate_nodes=mutate)
        with self.assertRaisesRegex(ValueError, self.index_error('cyclic query graph', 'cycle')):
            self.check(inventory, evidence)

    def test_rejects_wrong_infer_identity_or_hash(self):
        for field, value in [('members', ['other']), ('query_key', '0' * 64)]:
            inventory, evidence = self.fixture()
            change_report(evidence, lambda q: q['groups'][0].__setitem__(field, value))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'exact InferScc|group id matches'):
                self.check(inventory, evidence)

    def test_rejects_wrong_report_crate_format_or_group_id(self):
        for mutate in [
            lambda q: q.update(crate='other'),
            lambda q: q.update(format=True),
            lambda q: q['groups'][0].update(id='unrelated'),
        ]:
            inventory, evidence = self.fixture()
            change_report(evidence, mutate)
            with self.assertRaises(ValueError):
                self.check(inventory, evidence)

    def test_rejects_wrong_measured_crate_or_compiler(self):
        for crate, compiler in [('other', 'b' * 64), ('compiler-shapes/flat_functions-8', 'c' * 64)]:
            inventory, evidence = self.fixture()
            with self.assertRaisesRegex(ValueError, 'crate/compiler configuration'):
                analyze.Q.check_graph(inventory, evidence, 1, 1, crate, compiler)

    def test_rejects_missing_or_duplicate_report_groups(self):
        for mode in ['missing', 'duplicate', 'overlapping', 'extra-graph']:
            inventory, evidence = self.fixture(groups=2)
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
            inventory, evidence = self.fixture()
            change_report(evidence, mutate)
            with self.assertRaises(ValueError):
                self.check(inventory, evidence)

    def test_rejects_duplicate_report_json_keys(self):
        inventory, evidence = self.fixture()
        evidence['query_report_json'] = '{"inferred_groups":1,' + evidence['query_report_json'][1:]
        with self.assertRaisesRegex(ValueError, 'duplicate query report JSON key'):
            self.check(inventory, evidence)

    def test_rejects_payload_hash_different_from_node_hash(self):
        valid_inventory, valid_evidence = self.fixture()
        self.check(valid_inventory, valid_evidence)
        report = json.loads(valid_evidence['query_report_json'])['groups'][0]
        def mutate(nodes):
            target = nodes[-1]
            self.assertEqual(target['key'], analyze.Q.pack(['InferScc', analyze.Q.pack(sorted(report['members']))]))
            self.assertEqual(target['hash'], report['query_key'])
            self.assertEqual(target['payload'], target['hash'])
            before = dict(target)
            target['payload'] = nodes[1]['hash']
            self.assertNotEqual(target['payload'], target['hash'])
            self.assertEqual({k: v for k, v in target.items() if k != 'payload'},
                             {k: v for k, v in before.items() if k != 'payload'})
        inventory, evidence = self.fixture(mutate_nodes=mutate)
        self.assertEqual(evidence['query_report_json'], valid_evidence['query_report_json'])
        # Legacy admission enforces this before the report. Dictionary v2
        # reaches the exact InferScc/raw-payload cross-check with valid identity.
        reason = self.index_error('query graph payload matches result hash',
                                  'exact InferScc identity and raw payload SHA')
        with self.assertRaisesRegex(ValueError, '^' + reason + '$'):
            self.check(inventory, evidence)

    def test_rejects_extra_generation(self):
        inventory, evidence = self.fixture()
        inventory[analyze.Q.GRAPH + 'generations/' + '0' * 64 + '.mlfqg'] = {
            'bytes': 1, 'sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'one committed graph generation'):
            self.check(inventory, evidence)

    def test_rejects_mixed_storage_and_unpublished_staging(self):
        for extra in ['legacy.mlfq', analyze.Q.GRAPH + 'staging/incomplete']:
            inventory, evidence = self.fixture()
            inventory[extra] = {'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()}
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.check(inventory, evidence)

    def test_snapshot_retains_exact_actual_inputs(self):
        import base64
        import query_cache as Q
        inventory, evidence = self.fixture()
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
            Q.snapshot(query, report, destination)
            self.assertEqual(json.loads(destination.read_text()), evidence)


class GraphAnalyzerTests(unittest.TestCase):
    version = 1

    def fixture(self, **kwargs):
        return graph_fixture(version=self.version, **kwargs)

    def test_graph_cohort_and_existing_raw_reuse_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = write_cohort(directory)
            inventory, evidence = self.fixture()
            legs = sorted((folder / 'legs').iterdir())
            for leg in legs:
                (leg / 'query-cache-inventory.json').write_text(json.dumps(inventory))
                (leg / 'query-graph-evidence.json').write_text(json.dumps(evidence))
            rows, _, _, samples = analyze.analyze(folder)
            self.assertEqual(rows[0]['query_storage'], 'query-graph-v1')
            self.assertEqual(rows[0]['fresh'], 1)
            self.assertEqual(rows[0]['query_files'], 4)
            self.assertEqual(len(samples), 6)
            edit(folder, lambda r: r['runs'][-1].update(raw_compared_with_first_mlf_leg=False))
            with self.assertRaisesRegex(ValueError, 'actual raw-byte comparisons'):
                analyze.analyze(folder)

    def test_rejects_inventory_drift_with_same_file_count(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = write_cohort(directory)
            inventory, evidence = self.fixture()
            legs = sorted((folder / 'legs').iterdir())
            for i, leg in enumerate(legs):
                if i == 2:
                    inventory[next(p for p in inventory if p.endswith('.mlfqr'))]['bytes'] += 1
                (leg / 'query-cache-inventory.json').write_text(json.dumps(inventory))
                (leg / 'query-graph-evidence.json').write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, 'stable graph inventory'):
                analyze.analyze(folder)

class IndexedGraphCacheTests(GraphCacheTests):
    version = 2

    def test_v1_and_v2_preserve_groups_and_payload_deduplication(self):
        first = self.check(*graph_fixture(groups=3), groups=3)
        second = self.check(*self.fixture(groups=3), groups=3)
        self.assertEqual(first['groups'], second['groups'])
        self.assertEqual(first['files'], second['files'])

    def test_accepts_ordered_duplicate_reads(self):
        def mutate(nodes):
            nodes[-1]['reads'] = [(nodes[1]['key'], nodes[1]['hash']),
                                 (nodes[2]['key'], nodes[2]['hash']),
                                 (nodes[1]['key'], nodes[1]['hash'])]
        inventory, evidence = self.fixture(mutate_nodes=mutate)
        self.check(inventory, evidence)
        import base64
        raw = base64.b64decode(next(value for path, value in evidence['files_base64'].items()
                                   if path.endswith('.mlfqg')))
        configuration = analyze.Q.document(raw)[2][1][1]
        nodes, _ = analyze.Q.read_index(raw, configuration)
        key = analyze.Q.pack(['InferScc', analyze.Q.pack(['f0'])])
        reads = nodes[key][1]
        self.assertEqual(len(reads), 3)
        self.assertEqual(reads[0], reads[2])
        self.assertNotEqual(reads[0], reads[1])

    @staticmethod
    def with_child(value, position, child):
        children = list(value[2])
        children[position] = child
        return (value[0], value[1], tuple(children))

    def test_rejects_index_tag_marker_and_arity(self):
        mutations = [
            lambda v: ('node', 999, v[2]),
            lambda v: self.with_child(v, 0, ('text', 'MLF-CRATE-QUERY-GRAPH-1')),
            lambda v: ('node', 412, v[2][:-1]),
            lambda v: self.with_child(v, 1, ('text', '')),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.check(*self.fixture(mutate_index=mutate))

    def test_rejects_noncanonical_dictionary(self):
        for mode in ('unordered', 'duplicate', 'unused'):
            def mutate(value):
                dictionary = list(value[2][2][2])
                if mode == 'unordered':
                    dictionary[0], dictionary[1] = dictionary[1], dictionary[0]
                elif mode == 'duplicate':
                    dictionary[1] = dictionary[0]
                else:
                    dictionary.append(('text', 'zz-unused'))
                return self.with_child(value, 2, ('node', 1, tuple(dictionary)))
            with self.subTest(mode=mode), self.assertRaisesRegex(
                    ValueError, 'dictionary canonicality|unused dictionary'):
                self.check(*self.fixture(mutate_index=mutate))

    def test_rejects_invalid_ids_and_unordered_rows(self):
        for mode in ('negative', 'out-of-range', 'wrong-type', 'unordered'):
            def mutate(value):
                rows = list(value[2][3][2])
                if mode == 'unordered':
                    rows.reverse()
                else:
                    wrong = {'negative': ('int', -1),
                             'out-of-range': ('int', len(value[2][2][2])),
                             'wrong-type': ('text', '0')}[mode]
                    rows[0] = self.with_child(rows[0], 1, wrong)
                return self.with_child(value, 3, ('node', 1, tuple(rows)))
            with self.subTest(mode=mode), self.assertRaisesRegex(
                    ValueError, 'ID range|int|row canonicality'):
                self.check(*self.fixture(mutate_index=mutate))

    def depth_fixture(self, count):
        def mutate(nodes):
            digest = nodes[0]['hash']
            for i in range(count):
                nodes.append({'key': 'Depth/%04d' % i, 'hash': digest, 'payload': None,
                              'reads': [] if i == 0 else [('Depth/%04d' % (i - 1), digest)]})
        return self.fixture(mutate_nodes=mutate)

    def test_accepts_dependency_first_4096_node_path(self):
        self.check(*self.depth_fixture(4096))

    def test_rejects_dependency_first_4097_node_path(self):
        with self.assertRaisesRegex(ValueError, 'depth'):
            self.check(*self.depth_fixture(4097))


class IndexedGraphAnalyzerTests(GraphAnalyzerTests):
    version = 2


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
        for name in ['test_query_index.py', 'artifact_binary_open.py', 'command_runner.py', 'bench.py',
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
