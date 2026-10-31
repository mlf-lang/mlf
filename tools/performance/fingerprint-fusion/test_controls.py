#!/usr/bin/env python3
"""Cheap F1 harness/oracle controls; never execute GHC or a timing campaign.

Literal hashes originate in the independently authored pre-integration controls.
These tests remain active under Python -O. Fake Core tests validate the parser's
bounded contract, not arbitrary GHC Core equivalence or cross-platform speed.
"""
from __future__ import annotations

from contextlib import ExitStack
import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNNER = types.ModuleType('fingerprint_control_test_runner')
RUNNER.__file__ = str(HERE / 'run_controls.py')
exec(compile(Path(RUNNER.__file__).read_bytes(), RUNNER.__file__, 'exec'), RUNNER.__dict__)

FROZEN = {
    'Oracle.hs': 'af71fa1817dabd45c7cfab98c1043dd18eca396bfa57c23181d0bf22e035cfee',
    'Tests.hs': 'e7352052eb25fa2855ac5741577e328d461d481a21aea203bcb230f53f784f6a',
    'Probe.hs': 'a715135903662d82e16431be6796c60789ae6a87fb178757083124f4e92fe271',
}
HOST = {
    'host/ghc/MLF/Host/Base.hs': 'b9663c40059791bfb99e9f302d4eab94452379653db3e951ee02c8ff45933de3',
    'host/ghc/MLF/Primitive.hs': '2ec6ab90201feb449a9a9accbfa9d34661e03216e54cb3c52ffbfe2d15f7353b',
}
STDOUT_SHA256 = '57cafef22ad1cb66e4e90a1e67510c744cea3d6f16f90b937520414d37504773'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def core_block(name, body='integerRem (integerAdd (integerMul state k) code) modulus'):
    return '-- RHS size: {terms: 10}\n' + name + ' :: Integer -> Integer -> Integer\n' + name + ' = ' + body + '\n'


class RuleCountControls(unittest.TestCase):
    def test_exact_public_rules_and_package_inventory(self):
        self.assertEqual(RUNNER.RULES, ('mlf/fingerprintIntStep/65599', 'mlf/fingerprintIntStep/131'))
        self.assertEqual(RUNNER.PACKAGES, ('base', 'array', 'bytestring', 'text', 'containers', 'directory'))

    def test_zero_and_two_firings_are_distinguished(self):
        self.assertEqual(RUNNER.rule_counts(''), dict.fromkeys(RUNNER.RULES, 0))
        text = ''.join(('Rule: ' + name + '\n') * 2 for name in RUNNER.RULES)
        self.assertEqual(RUNNER.rule_counts(text), dict.fromkeys(RUNNER.RULES, 2))
        RUNNER.verify_probe_counts(RUNNER.rule_counts(''), '0')
        RUNNER.verify_probe_counts(RUNNER.rule_counts(text), '2')

    def test_different_rule_names_are_not_matching_firings(self):
        text = ('Rule: mlf/fingerprintIntStep/65598\n'
                'Rule: mlf/fingerprintIntStep/65599/other\n'
                'Rule: mlf/fingerprintIntStep/1310\n')
        self.assertEqual(RUNNER.rule_counts(text), dict.fromkeys(RUNNER.RULES, 0))

    def test_missing_extra_or_wrong_counts_fail(self):
        expected = dict.fromkeys(RUNNER.RULES, 2)
        cases = [{}, {RUNNER.RULES[0]: 2}, {**expected, 'unexpected': 2},
                 dict.fromkeys(RUNNER.RULES, 0), dict.fromkeys(RUNNER.RULES, 3),
                 {**expected, RUNNER.RULES[0]: 1}]
        for counts in cases:
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                RUNNER.verify_probe_counts(counts, '2')
        with self.assertRaises(ValueError):
            RUNNER.verify_probe_counts(expected, '0')

    def test_unknown_optimization_fails(self):
        for optimization in ('1', '3', '', None):
            with self.subTest(optimization=optimization), self.assertRaises(ValueError):
                RUNNER.verify_probe_counts(dict.fromkeys(RUNNER.RULES, 0), optimization)


class UnmatchedCoreControls(unittest.TestCase):
    def setUp(self):
        self.multiplier = core_block('unmatchedMultiplier')
        self.modulus = core_block('unmatchedModulus')

    def test_both_unmatched_functions_retain_integer_operations(self):
        RUNNER.verify_unmatched_core(self.multiplier + self.modulus)

    def test_fused_matched_function_elsewhere_does_not_poison_unmatched_check(self):
        RUNNER.verify_unmatched_core(core_block('stepA', 'fingerprintIntStep (value :: Int64)') +
                                     self.multiplier + self.modulus)

    def test_missing_or_duplicate_named_function_is_rejected(self):
        for text in (self.multiplier, self.modulus, self.multiplier * 2 + self.modulus,
                     self.multiplier + self.modulus * 2):
            with self.subTest(text=text), self.assertRaises(ValueError):
                RUNNER.verify_unmatched_core(text)

    def test_similarly_named_function_is_not_the_required_function(self):
        with self.assertRaises(ValueError):
            RUNNER.verify_unmatched_core(core_block('unmatchedMultiplierExtra') + self.modulus)

    def test_each_required_integer_operation_must_be_in_each_own_block(self):
        for name in ('integerMul', 'integerAdd', 'integerRem'):
            for part in ('multiplier', 'modulus'):
                text = (self.multiplier.replace(name, 'otherOperation') + self.modulus if part == 'multiplier'
                        else self.multiplier + self.modulus.replace(name, 'otherOperation'))
                with self.subTest(operation=name, part=part), self.assertRaises(ValueError):
                    RUNNER.verify_unmatched_core(text)

    def test_operations_in_an_unrelated_rhs_cannot_satisfy_missing_operations(self):
        text = core_block('unmatchedMultiplier', 'state') + self.modulus + core_block('unrelated')
        with self.assertRaises(ValueError):
            RUNNER.verify_unmatched_core(text)

    def test_narrowing_and_fused_helpers_are_rejected(self):
        for token in ('Int64', 'fingerprintIntStep'):
            for part in ('multiplier', 'modulus'):
                text = (self.multiplier.replace('integerRem', token + ' integerRem') + self.modulus
                        if part == 'multiplier' else
                        self.multiplier + self.modulus.replace('integerRem', token + ' integerRem'))
                with self.subTest(token=token, part=part), self.assertRaises(ValueError):
                    RUNNER.verify_unmatched_core(text)


class SourceResolutionControls(unittest.TestCase):
    def setUp(self):
        # No files/compiler are needed: resolution is lexical and strict=False.
        root = Path(tempfile.gettempdir()) / 'mlf-f1-resolution-test' / 'source'
        self.expected = {
            name: root / 'host/ghc' / (name.replace('.', '/') + '.hs')
            for name in ('MLF.Host.Base', 'MLF.Host.Async', 'MLF.Host.IO', 'MLF.Primitive')
        }
        self.expected.update({name: root / (name + '.hs')
                              for name in ('Oracle', 'Probe', 'Tests', 'Main')})

    def build_log(self, rows=None):
        rows = list(self.expected.items()) if rows is None else rows
        return ''.join('[%2d of %2d] Compiling %s ( %s, objects/%s.o )\n' %
                       (number, len(rows), name, path, name)
                       for number, (name, path) in enumerate(rows, 1))

    def test_exact_eight_module_source_map_is_accepted(self):
        self.assertEqual(len(self.expected), 8)
        RUNNER.verify_resolution(self.build_log() + '[9 of 9] Linking controls\n', self.expected)

    def test_resolution_does_not_depend_on_compile_order(self):
        RUNNER.verify_resolution(self.build_log(list(reversed(list(self.expected.items())))), self.expected)

    def test_lexically_equivalent_absolute_path_is_accepted(self):
        rows = [(name, path.parent / 'unused' / '..' / path.name)
                for name, path in self.expected.items()]
        RUNNER.verify_resolution(self.build_log(rows), self.expected)

    def test_missing_extra_and_duplicate_module_are_rejected(self):
        rows = list(self.expected.items())
        cases = [rows[:-1], rows + [('Unexpected', rows[0][1])], rows[:-1] + [rows[0]]]
        for case in cases:
            with self.subTest(rows=case), self.assertRaisesRegex(ValueError, 'compiled module inventory'):
                RUNNER.verify_resolution(self.build_log(case), self.expected)

    def test_same_named_file_from_other_tree_is_rejected(self):
        rows = list(self.expected.items())
        for index, (name, path) in enumerate(rows):
            changed = rows[:]
            changed[index] = (name, path.parent / 'other-tree' / path.name)
            with self.subTest(module=name), self.assertRaisesRegex(ValueError, 'different control/production source'):
                RUNNER.verify_resolution(self.build_log(changed), self.expected)

    def test_swapped_source_paths_are_rejected(self):
        rows = list(self.expected.items())
        rows[0], rows[1] = (rows[0][0], rows[1][1]), (rows[1][0], rows[0][1])
        with self.assertRaisesRegex(ValueError, 'different control/production source'):
            RUNNER.verify_resolution(self.build_log(rows), self.expected)

    def test_similarly_named_module_cannot_substitute_for_expected_module(self):
        rows = list(self.expected.items())
        rows[0] = (rows[0][0] + 'Extra', rows[0][1])
        with self.assertRaisesRegex(ValueError, 'different control/production source'):
            RUNNER.verify_resolution(self.build_log(rows), self.expected)

    def test_unparseable_compile_line_cannot_silently_shrink_inventory(self):
        text = self.build_log().replace('Compiling MLF.Host.Base', 'Other MLF.Host.Base')
        with self.assertRaisesRegex(ValueError, 'compiled module inventory'):
            RUNNER.verify_resolution(text, self.expected)


class FrozenInputs(unittest.TestCase):
    def setUp(self):
        self.inventory = json.loads((HERE / 'controls/CONTROL-INVENTORY.json').read_text())

    def test_independent_sources_and_expectation_are_literal_pins(self):
        self.assertEqual(self.inventory['source_files'], FROZEN)
        for path, wanted in FROZEN.items():
            self.assertEqual(RUNNER.sha(HERE / 'controls' / path), wanted, path)
        self.assertEqual(digest(self.inventory['expected_stdout'].encode()), STDOUT_SHA256)
        self.assertEqual(self.inventory['expected_stderr'], '')
        self.assertFalse(self.inventory['candidate_output_used_for_expectations'])

    def test_only_reviewed_host_patch_is_under_test(self):
        expected = HOST
        if (ROOT / 'libraries/mlf-foundation/Bootstrap/IntTree.hs').exists():
            path = ROOT / 'tools/performance/patricia/source_migration.py'
            migration = types.ModuleType('explicit_numeric_migration')
            migration.__file__ = str(path)
            exec(compile(path.read_bytes(), str(path), 'exec'), migration.__dict__)
            expected = migration.host_sources(HOST)
        for path, wanted in expected.items():
            self.assertEqual(RUNNER.sha(ROOT / path), wanted, path)

    def test_oracle_uses_unbounded_prelude_arithmetic_not_candidate_arithmetic(self):
        text = (HERE / 'controls/Oracle.hs').read_text()
        self.assertIn('{-# OPTIONS_GHC -O0 #-}', text)
        self.assertIn('import Prelude\n', text)
        self.assertIn('import qualified MLF.Host.Base as Base (HostError(..))', text)
        self.assertIn('strict2 f a b = a `pseq` b `pseq` f a b', text)
        self.assertIn('Integer -> Integer -> Integer', text)
        for forbidden in ('MLF.Primitive', 'fingerprintIntStep', 'fingerprintIntegerStep',
                          'Base.v_addInt', 'Base.v_mulInt', 'Base.v_remInt', 'Data.Int'):
            self.assertNotIn(forbidden, text)
        self.assertFalse(self.inventory['oracle']['candidate_arithmetic_calls'])
        self.assertFalse(self.inventory['oracle']['private_candidate_helpers_imported'])

    def test_tests_keep_o0_and_do_not_catch_unrelated_exceptions(self):
        text = (HERE / 'controls/Tests.hs').read_text()
        self.assertIn('{-# OPTIONS_GHC -O0 #-}', text)
        self.assertIn('IO (Either Base.HostError Integer)', text)
        self.assertNotIn('SomeException', text)
        self.assertNotIn('fingerprintIntStep', text)
        self.assertEqual(self.inventory['timeouts']['expected_timeouts'], 36)
        self.assertEqual(self.inventory['timeouts']['expected_panic_not_timeout'], 12)
        self.assertEqual(self.inventory['timeouts']['minimum_expected_timeout_wait_seconds'], 9)

    def test_literal_boundary_and_demand_inventory(self):
        values = self.inventory['finite_values']
        self.assertEqual((values['boundary_states'], values['boundary_codes'], values['boundary_pairs']), (27, 25, 675))
        self.assertEqual((values['boundary_route_comparisons'], values['deterministic_route_comparisons']), (4050, 15000))
        self.assertEqual(self.inventory['streams']['stream_runs'], 270)
        demand = self.inventory['demand']
        self.assertEqual((demand['exact_HostError_priority_probes'], demand['partial_application_functions'],
                          demand['ordinary_nonzero_signed_division_cases'], demand['ordinary_zero_and_panic_order_probes']),
                         (60, 18, 224, 40))

    def test_narrow_branch_mathematical_bound_fits_fixed_int64(self):
        for multiplier, modulus in self.inventory['oracle']['original_rule_parameters']:
            maximum = (modulus - 1) * multiplier + 0x10ffff
            self.assertGreaterEqual(maximum, 0)
            self.assertLess(maximum, 2**48)
            self.assertLess(maximum, 2**63)
        # This is a value-range check, not an executed 32-bit/Apple platform test.
        self.assertIn('import qualified Data.Int as Fixed', (ROOT / 'host/ghc/MLF/Host/Base.hs').read_text())

    def test_hash_inventory_is_exact_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'one').write_bytes(b'one')
            (root / 'sub').mkdir()
            (root / 'sub/two').write_bytes(b'two')
            self.assertEqual(RUNNER.hashes(root), {'one': digest(b'one'), 'sub/two': digest(b'two')})
            (root / 'alias').symlink_to(root / 'one')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                RUNNER.hashes(root)


class P2OracleIsolation(unittest.TestCase):
    P2 = ROOT / 'tools/performance/crate-optimizations/p2'
    ISOLATION_FLAGS = ('-fno-enable-rewrite-rules', '-fomit-interface-pragmas')

    def setUp(self):
        self.source = (self.P2 / 'run_fingerprint_differential.py').read_text()

    def verify_isolation(self, source):
        """Check actual compile argv AST, not a flag string in a comment/receipt."""
        tree = ast.parse(source)
        def command(label):
            calls = [node for node in ast.walk(tree)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                     and node.func.id == 'run' and node.args
                     and isinstance(node.args[0], ast.Constant) and node.args[0].value == label]
            self.assertEqual(len(calls), 1, label)
            self.assertGreaterEqual(len(calls[0].args), 2)
            self.assertIsInstance(calls[0].args[1], ast.List)
            return calls[0].args[1].elts
        argv = command('compile-oracle')
        base = [index for index, node in enumerate(argv)
                if isinstance(node, ast.Starred) and isinstance(node.value, ast.Name)
                and node.value.id == 'flags']
        self.assertEqual(len(base), 1)
        literal = {node.value: index for index, node in enumerate(argv)
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        for flag in (*self.ISOLATION_FLAGS, '-dcore-lint', '-ddump-rule-rewrites', '-ddump-to-file'):
            self.assertIn(flag, literal, 'missing oracle isolation/diagnostic flag: ' + flag)
            self.assertGreater(literal[flag], base[0], 'oracle override must follow normal O2 flags')
        for conflict in ('-fenable-rewrite-rules', '-fno-omit-interface-pragmas', '-fexpose-all-unfoldings'):
            self.assertNotIn(conflict, literal)
        self.assertEqual(ast.dump(argv[-1]), ast.dump(ast.parse("HERE / 'FrozenFingerprint.hs'", mode='eval').body))
        # Keep normal candidate/harness optimization: isolate the frozen module,
        # not both sides or the shared compilation flags.
        flags = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'flags' for target in node.targets)]
        self.assertEqual(len(flags), 1)
        self.assertIsInstance(flags[0], ast.List)
        normal = [node.value for node in flags[0].elts if isinstance(node, ast.Constant)]
        self.assertIn('-O2', normal)
        harness = [node.value for node in command('compile-harness') if isinstance(node, ast.Constant)]
        for flag in self.ISOLATION_FLAGS:
            self.assertNotIn(flag, normal)
            self.assertNotIn(flag, harness)

    def test_p2_oracle_retains_its_literal_independent_bytes(self):
        manifest = json.loads((self.P2 / 'oracle-manifest.json').read_text())
        for filename, key, wanted in (
            ('FrozenFingerprint.hs', 'oracle_sha256',
             '46ccf49aeef6caf9ad440bb315d9e4d1fe4ce65173584a6fdf6c16215b00a3fe'),
            ('original-fingerprint-excerpts.txt', 'excerpts_sha256',
             '1b279c2812c4c5f31222b6b714c35528b98115843dd66669fb2d4caa4ef7d87a'),
        ):
            self.assertEqual(manifest[key], wanted)
            self.assertEqual(RUNNER.sha(self.P2 / filename), wanted)

    def test_p2_actual_oracle_command_disables_rules_and_exported_unfoldings(self):
        self.verify_isolation(self.source)

    def test_either_missing_isolation_flag_fails_even_when_named_elsewhere(self):
        for flag in self.ISOLATION_FLAGS:
            mutated = self.source.replace(repr(flag) + ', ', '', 1)
            self.assertNotEqual(mutated, self.source)
            with self.subTest(flag=flag), self.assertRaises(AssertionError):
                self.verify_isolation(mutated + '\n# flag documentation: ' + flag + '\n')

    def test_flags_before_o2_defaults_do_not_satisfy_isolation(self):
        for flag in self.ISOLATION_FLAGS:
            mutated = self.source.replace(repr(flag) + ', ', '', 1)
            mutated = mutated.replace("run('compile-oracle', [ghc, '-c', *flags,",
                                      "run('compile-oracle', [ghc, '-c', " + repr(flag) + ', *flags,', 1)
            with self.subTest(flag=flag), self.assertRaises(AssertionError):
                self.verify_isolation(mutated)

    def test_later_conflicting_flags_fail(self):
        for flag in ('-fenable-rewrite-rules', '-fno-omit-interface-pragmas', '-fexpose-all-unfoldings'):
            mutated = self.source.replace("'-dcore-lint',", repr(flag) + ", '-dcore-lint',", 1)
            with self.subTest(flag=flag), self.assertRaises(AssertionError):
                self.verify_isolation(mutated)


class MainInputRejection(unittest.TestCase):
    class ReachedSourceHashing(Exception):
        pass

    def preflight(self, mutate=None, optimization='2'):
        """Exercise real main preflight; stop before source copying or any compiler."""
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            source, producer, output = root / 'source', root / 'producer', root / 'output'
            here = source / 'tools/performance/fingerprint-fusion'
            (here / 'controls').mkdir(parents=True)
            producer.mkdir()
            auth = source / 'tools/shared/test_direct.py'
            auth.parent.mkdir(parents=True)
            auth.write_text('def authenticate_build(receipt, binaries, root):\n'
                            '    return {"optimization": ' + repr(optimization) + '}\n')
            (producer / 'receipt.json').write_text('{}\n')
            inventory = json.loads((HERE / 'controls/CONTROL-INVENTORY.json').read_text())
            for name in FROZEN:
                (here / 'controls' / name).write_bytes((HERE / 'controls' / name).read_bytes())
            if mutate:
                mutate(inventory, here / 'controls')
            (here / 'controls/CONTROL-INVENTORY.json').write_text(json.dumps(inventory))
            stack.enter_context(mock.patch.object(RUNNER, 'ROOT', source))
            stack.enter_context(mock.patch.object(RUNNER, 'HERE', here))
            stack.enter_context(mock.patch.object(sys, 'argv', ['run_controls.py', '--producer', str(producer), '--output', str(output)]))
            # Any accidentally bypassed mismatch is still unable to launch GHC.
            stack.enter_context(mock.patch.object(RUNNER.subprocess, 'Popen', side_effect=AssertionError('compiler must never run')))
            stack.enter_context(mock.patch.object(RUNNER, 'hashes', side_effect=self.ReachedSourceHashing()))
            RUNNER.main()

    def test_valid_literal_inventory_reaches_hashing_without_compiler(self):
        with self.assertRaises(self.ReachedSourceHashing):
            self.preflight()

    def test_wrong_producer_optimization_is_rejected_before_compiler(self):
        with self.assertRaisesRegex(ValueError, 'complete O2 producer'):
            self.preflight(optimization='0')

    def test_missing_or_extra_control_is_rejected_before_compiler(self):
        def remove(inventory, controls):
            del inventory['source_files']['Oracle.hs']
        def add(inventory, controls):
            inventory['source_files']['Unexpected.hs'] = '0' * 64
        for mutation in (remove, add):
            with self.subTest(mutation=mutation.__name__), self.assertRaisesRegex(ValueError, 'exact frozen control inventory'):
                self.preflight(mutation)

    def test_each_wrong_pin_is_rejected_before_compiler(self):
        for name in FROZEN:
            def mutate(inventory, controls, name=name):
                inventory['source_files'][name] = '0' * 64
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'frozen control changed'):
                self.preflight(mutate)

    def test_changed_oracle_bytes_are_rejected_before_compiler(self):
        def mutate(inventory, controls):
            path = controls / 'Oracle.hs'
            path.write_bytes(path.read_bytes() + b'-- unexpected change\n')
        with self.assertRaisesRegex(ValueError, 'frozen control changed: Oracle.hs'):
            self.preflight(mutate)


if __name__ == '__main__':
    unittest.main(verbosity=2)
