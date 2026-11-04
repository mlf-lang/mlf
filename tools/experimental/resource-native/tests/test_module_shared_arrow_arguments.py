"""Stage23 host-only arrow coordinate/replay controls; never builds a producer.

Retained baseline C is deliberately NOT a matching /3 producer capture. Its raw
projected graph is a test input; successful independent derivation cannot change
the old recorded normalization or establish source/native qualification.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE / 'tests')]
import module_shared_transport as m
import module_projection as projection
import test_module_shared_transport as f
import test_module_shared_nominal_arguments as nominal
from source_capture_v8 import verify_capture

AI = f.arr(f.I, f.I)
N = f.nominal_type('Chain')
PINS = {
    'shared-id-arrow': ('bd430a27d03287b544890d825a5f75902629e14980a6dfb7674bd1b6a3e0066d',
        'bfa5b539f1ec00d3f9a15e123b22a598b0afabd36ae1b7f23b7f5ac12b1a364d',
        '50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'),
    'shared-apply-arrow': ('1108bb4359def06dfaee507f314720459657f4808fecd1e4a6395ceb2c2cdc69',
        'b46fb3766923b65d74427b6f41b79a7614df81f88889367b964c586e10f292c2',
        'bfcde7ead1b6d35d2e1281642825dd590d73b3cbb40d0c13f2b42c07fd848a0e'),
    'shared-apply-instance': ('6deda5e135a4d52dc350a6d17d76855ee68c35d56bfaa88bf2b50ef2819db35e',
        '2e681b14c07368d3f84b8434e85f33be3a8132d5b2cf278792be76835a8ec9f2',
        'bfcde7ead1b6d35d2e1281642825dd590d73b3cbb40d0c13f2b42c07fd848a0e'),
    'shared-id-instance': ('a73e7e87b3695a7101579f5d8ce1d793df95d29d186b522d9f1781841766db2d',
        '4391a762775deff7408586551a3f0863e2b0ea95102429378bebf628891f2950',
        '8e81d4d72fdd257c21d5be3549d3f1d372d2326f2670a37ebc8f07196edbc86f'),
}


def identity(binder, parameter):
    return f.tabs(binder, f.lam(parameter, f.tv(binder), f.var(parameter)))


def direct(argument, binder, parameter):
    return f.tapp(identity(binder, parameter), f.inst(argument))


def arrow_use(argument=AI):
    return f.let(1, identity(100, 2), f.let(10, f.use(1, argument), f.lit()))


def apply_definition():
    return f.tabs(100, f.tabs(101,
        f.lam(2, f.arr(f.tv(100), f.tv(101)),
              f.lam(3, f.tv(100), f.app(f.var(2), f.var(3))))))


def outer_first():
    inner = f.tapp(identity(501, 20), f.inst(f.tv(500)))
    partial = f.app(f.use(1, f.tv(500), f.tv(500)), inner)
    outer = f.tapp(f.tabs(500, partial), f.inst(AI))
    return f.let(1, apply_definition(),
        f.app(f.app(outer, f.lam(30, f.I, f.var(30))), f.lit()))


def mixed_recursive_views():
    # All four different second coordinates are dead in the Scheme result.
    # Keep them as four physical saved views of the SAME lexical Scheme.
    definition = f.tabs(100, f.tabs(101, f.lam(2, f.tv(100), f.var(2))))
    body = f.let(80, f.app(f.var(30), f.var(31)), f.var(31))
    for index, argument in enumerate((f.I, N, AI, f.B)):
        body = f.let(70 + index, f.use(1, f.I, argument), body)
    recursive = f.rec_binding(30, AI, f.lam(31, f.I, body), f.lit())
    return f.with_data(f.let(1, definition, recursive), f.recursive_decl())


def spine(depth, leaf=f.I):
    for _ in range(depth - 1):
        leaf = f.arr(f.I, leaf)
    return leaf


def retained(test, case):
    value = os.environ.get('IR8_ARROW_ARGUMENTS_ROOT')
    if not value:
        test.skipTest('set IR8_ARROW_ARGUMENTS_ROOT for immutable baseline diagnostics')
    root = Path(value)
    path = root / ('capture-' + case + '01') / 'capture.stdout'
    blob = path.read_bytes()
    test.assertEqual(hashlib.sha256(blob).hexdigest(), PINS[case][0])
    return root, path, json.loads(blob)


def verified(root, path, case, pin=None):
    return verify_capture(path, fixture_root=root / 'inputs' / case, entry='main.emlf',
        expected_source_hashes={'main.emlf': PINS[case][1], 'SharedPoly.emlf': PINS[case][2]},
        expected_capture_sha256=pin or PINS[case][0])


class ArrowArgumentReplayTests(unittest.TestCase):
    def reject(self, raw, code=None):
        with self.assertRaises(m.SharedTransportError) as caught:
            m.derive_shared_fragment(raw)
        if code:
            self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def test_closed_arrow_use_without_beta_keeps1_and_full_tree(self):
        raw = arrow_use()
        out = m.derive_shared_fragment(raw)
        self.assertEqual((out['policy'], out['steps']), (m.POLICY, []))
        self.assertEqual(out['raw_normalized'], raw)
        self.assertEqual(out['polymorphism']['uses'][0]['arguments'], [AI])
        self.assertEqual(out['polymorphism']['uses'][0]['instantiated_type'], f.arr(AI, AI))
        self.assertEqual(m.validate_shared_fragment(raw, out), out)

    def test_arrow_direct_beta_derives3_without_ordinary_reduction(self):
        raw = f.app(direct(AI, 100, 2), f.lam(10, f.I, f.var(10)))
        out = m.derive_shared_fragment(raw)
        self.assertEqual(out['policy'], m.ARROW_BETA_POLICY)
        self.assertEqual(len(out['steps']), 1)
        self.assertEqual(out['steps'][0]['arguments'], [AI])
        self.assertEqual(out['raw_normalized'], f.app(f.lam(2, AI, f.var(2)), raw['argument']))
        self.assertEqual(projection.erase_total(raw), projection.erase_total(out['raw_normalized']))

    def test_outer_first_updates_complete_vector_and_nested_witness(self):
        raw = outer_first()
        out = m.derive_shared_fragment(raw)
        self.assertEqual(out['policy'], m.ARROW_BETA_POLICY)
        self.assertEqual([step['arguments'] for step in out['steps']], [[AI], [AI]])
        self.assertEqual(out['steps'][0]['input']['path'], ['body', 'function', 'function'])
        self.assertEqual(out['steps'][1]['input']['path'], ['body', 'function', 'function', 'argument'])
        self.assertEqual(out['polymorphism']['uses'][0]['arguments'], [AI, AI])
        inner = next(row for row in out['polymorphism']['type_applications']
                     if row['witness'] == f.inst(f.tv(500)) and row['disposition'] == 'direct_closed')
        self.assertEqual(inner['normalization_steps'], [0, 1])
        self.assertEqual(out['steps'][1]['witnesses'], [f.inst(AI)])
        self.assertEqual(projection.erase_total(raw), projection.erase_total(out['raw_normalized']))
        self.assertEqual(len(out['term_correspondence']), len(m._ordinary(raw)))

    def test_dialect3_never_downgrades_after_nominal_or_scalar_steps(self):
        for first, second in ((AI, N), (N, AI), (AI, f.I)):
            raw = f.with_data(f.let(10, direct(first, 100, 2),
                f.let(11, direct(second, 101, 3), f.lit())), f.recursive_decl())
            out = m.derive_shared_fragment(raw)
            self.assertEqual(out['policy'], m.ARROW_BETA_POLICY)
            self.assertEqual([s['arguments'] for s in out['steps']], [[first], [second]])
        raw = f.with_data(f.let(90, direct(N, 200, 91), arrow_use()), f.recursive_decl())
        self.assertEqual(m.derive_shared_fragment(raw)['policy'], m.NOMINAL_BETA_POLICY)

    def test_nested_arrows_and_exact_data_sum_leaf_positions(self):
        for leaf, declaration in ((N, f.recursive_decl()),
                                  (f.nominal_type(), f.data_decl())):
            for typ in (f.arr(leaf, f.B), f.arr(f.I, leaf),
                        f.arr(f.arr(leaf, f.B), f.arr(f.I, leaf))):
                raw = f.with_data(arrow_use(typ), declaration)
                out = m.derive_shared_fragment(raw)
                self.assertEqual(out['polymorphism']['uses'][0]['arguments'], [typ])
                self.assertEqual(out['policy'], m.POLICY)
                self.assertEqual(out['raw_normalized']['declarations'], raw['declarations'])

    def test_all_dead_coordinates_preserved_even_equal_instantiated_types(self):
        rhs = f.tabs(100, f.tabs(101, f.lam(2, f.tv(100), f.var(2))))
        left, right = f.arr(N, f.I), f.arr(f.B, f.I)
        raw = f.with_data(f.let(1, rhs,
            f.add(f.app(f.use(1, f.I, left), f.lit(21)),
                  f.app(f.use(1, f.I, right), f.lit(21)))), f.recursive_decl())
        out = m.derive_shared_fragment(raw)
        a, b = out['polymorphism']['uses']
        self.assertEqual([a['arguments'], b['arguments']], [[f.I, left], [f.I, right]])
        self.assertEqual(a['instantiated_type'], b['instantiated_type'])
        self.assertEqual(out['nominal_sum']['declarations'][0]['name'], 'Chain')

    def test_full_coordinate_order_preserved(self):
        rhs = f.tabs(100, f.tabs(101, f.lam(2, f.tv(100), f.lam(3, f.tv(101), f.var(2)))))
        left, right = f.arr(f.I, f.B), f.arr(f.B, f.I)
        raw = f.let(1, rhs, f.let(10, f.use(1, left, right), f.use(1, right, left)))
        out = m.derive_shared_fragment(raw)
        self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']], [[left, right], [right, left]])

    def test_recursive_mixed_saved_views_keep_logical_order_and_dead_coordinates(self):
        out = m.derive_shared_fragment(mixed_recursive_views())
        binding, = out['recursion']['bindings']
        views = binding['captures']['views']
        self.assertEqual([row['arguments'] for row in views],
                         [[f.I, AI], [f.I, N], [f.I, f.B], [f.I, f.I]])
        self.assertEqual([row['instantiated_type'] for row in views], [AI] * 4)
        self.assertEqual({row['binding']['id'] for row in views}, {1})
        self.assertEqual(binding['free_term_bindings'], [1])
        self.assertEqual(len(binding['self_uses']), 1)
        self.assertEqual(m.validate_shared_fragment(out['input_annotated'], out), out)

    def test_nominal_leaf_obligations_require_same_published_object(self):
        budget = m._Budget(arrow_arguments=True)
        registry = m._Nominals(f.with_data(f.lit(), f.recursive_decl()), budget)
        with self.assertRaisesRegex(m.SharedTransportError, 'already checked'):
            m._arrow_argument(f.arr(N, f.I), registry, budget, 'USE', ())
        owner = registry.select('Chain')
        with mock.patch.object(registry, 'select', side_effect=AssertionError('late selection')):
            obligations = m._arrow_argument(f.arr(N, f.arr(f.I, N)), registry, budget, 'USE', ())
            self.assertEqual(len(obligations), 2)
            self.assertTrue(all(row[1] is owner for row in obligations))
            m._reconcile_arguments(obligations, registry, ({'declarations': [owner]}, None), budget)
            with self.assertRaisesRegex(m.SharedTransportError, 'not published'):
                m._reconcile_arguments(obligations, registry,
                                       ({'declarations': [copy.deepcopy(owner)]}, None), budget)

    def test_foreign_open_higher_rank_parameterized_and_refined_arrows_reject(self):
        bad = [f.arr(f.I, f.tv(999)), f.arr(f.nominal_type('Foreign'), f.I),
               f.arr({'tag': 'constructor', 'name': 'Chain', 'arguments': [f.I]}, f.I),
               f.arr(f.forall(700, f.arr(f.tv(700), f.tv(700))), f.I),
               f.arr(f.BOT, f.I), AI | {'protocol': 'once'}, AI | {'result_identity': 'argument'}]
        for typ in bad:
            for value in (arrow_use(typ), direct(typ, 200, 20)):
                with self.subTest(typ=typ):
                    self.reject(f.with_data(value, f.recursive_decl()))

    def test_generic_nominal_principals_and_operations_stay_rejected(self):
        for rhs in (f.tabs(100, f.lam(2, f.arr(N, f.tv(100)), f.var(2))),
                    f.tabs(100, f.lam(2, f.tv(100), f.let(20, f.ctor('Nil'), f.var(2))))):
            self.reject(f.with_data(f.let(1, rhs, f.lit()), f.recursive_decl()), 'NOMINAL_SCOPE')

    def test_dead_unsupported_nominal_arrow_still_checks_declaration(self):
        declaration = f.sum_decl('Chain', (('Nil', ()), ('Bad', (AI,))))
        rhs = f.tabs(100, f.tabs(101, f.lam(2, f.tv(100), f.var(2))))
        self.reject(f.with_data(f.let(1, rhs, f.app(f.use(1, f.I, f.arr(N, f.I)), f.lit())),
                                declaration), 'NOMINAL')

    def test_partial_extra_and_malformed_witnesses_do_not_widen(self):
        rhs = apply_definition()
        for value in (f.use(1, AI), f.use(1, AI, f.I, f.B),
                      f.tapp(f.var(1), f.then({'tag': 'elim'}, {'tag': 'inner', 'witness': {'tag': 'bottom', 'type': AI}}))):
            self.reject(f.let(1, rhs, f.let(10, value, f.lit())))

    def test_depth32_argument_and_substitution_depth_are_distinct(self):
        budget = m._Budget(arrow_arguments=True)
        registry = m._Nominals(f.lit(), budget)
        self.assertEqual(m._arrow_argument(spine(32), registry, budget, 'USE', ()), [])
        self.assertEqual(m._type_bounds(f.arr(f.I, f.tv(100)), budget, (100, spine(31)))[0], 32)
        with self.assertRaisesRegex(m.SharedTransportError, 'depth exceeds 32'):
            m._type_bounds(f.arr(f.I, f.tv(100)), budget, (100, spine(32)))
        with mock.patch.object(m.fragment, 'alpha_type_equal', side_effect=AssertionError('unbounded comparison')):
            self.reject(arrow_use(spine(32)), 'LIMIT')
        self.reject(arrow_use(spine(33)), 'LIMIT')

    def test_substitution_preflight_respects_body_shadow_and_bound_scope(self):
        budget = m._Budget(arrow_arguments=True)
        typ = f.forall(100, f.arr(f.tv(100), f.I))
        self.assertEqual(m._type_bounds(typ, budget, (100, spine(32)))[0], 2)
        typ = f.forall(100, f.arr(f.tv(100), f.I), f.tv(100))
        self.assertEqual(m._type_bounds(typ, budget, (100, spine(32)))[0], 32)

    def test_shared_diamond_preflight_rejects_without_expansion(self):
        typ = f.I
        for _ in range(31):
            typ = f.arr(typ, typ)
        budget = m._Budget(arrow_arguments=True)
        with self.assertRaisesRegex(m.SharedTransportError, 'expanded type'):
            m._type_bounds(typ, budget)
        self.assertLess(budget.work, 1000)
        cyclic = f.arr(f.I, f.I); cyclic['to'] = cyclic
        with self.assertRaisesRegex(m.SharedTransportError, 'cyclic'):
            m._type_bounds(cyclic, m._Budget(arrow_arguments=True))

    def test_type_preflight_charges_existing_work_budget(self):
        budget = m._Budget(arrow_arguments=True); budget.work = m.MAX_WORK - 2
        with self.assertRaisesRegex(m.SharedTransportError, 'work bound'):
            m._type_bounds(AI, budget)

    def test_forged_dialects_steps_substitutions_and_tree_reject(self):
        raw = outer_first(); out = m.derive_shared_fragment(raw)
        mutations = [lambda x: x.update(policy=m.POLICY),
                     lambda x: x.update(policy=m.NOMINAL_BETA_POLICY),
                     lambda x: x['steps'].reverse(),
                     lambda x: x['steps'][0]['substitutions'][0].update(argument=f.B),
                     lambda x: x['polymorphism']['uses'][0]['arguments'].pop(),
                     lambda x: x['raw_normalized'].update(body=f.lit())]
        for mutate in mutations:
            bad = copy.deepcopy(out); mutate(bad)
            with self.assertRaisesRegex(m.SharedTransportError, 'EVIDENCE'):
                m.validate_shared_fragment(raw, bad)
        raw = arrow_use(); bad = m.derive_shared_fragment(raw); bad['policy'] = m.ARROW_BETA_POLICY
        with self.assertRaisesRegex(m.SharedTransportError, 'EVIDENCE'):
            m.validate_shared_fragment(raw, bad)

    def test_scalar_nominal_only_routes_do_not_use_new_type_guard(self):
        with mock.patch.object(m, '_type_bounds', side_effect=AssertionError('old-route type guard')):
            for raw in (f.shared(), direct(f.I, 100, 2), nominal.identity_fixture(), nominal.const_fixture(True)):
                m.derive_shared_fragment(raw)

    def test_frozen_stage22_scalar_nominal_bytes_and_work_goldens(self):
        # Independently measured from the untouched Stage22 source, not inferred
        # from this candidate. Includes complete evidence bytes and budget rows.
        cases = [
            (f.shared(), '87a8607e1c56aa93c5c2a01992fccb12a1ff73c71f4aafaad06a55d349cb8a5f', 401, 11956, 33),
            (f.tapp(f.identity(), f.inst(f.I)), 'c7192018ef3cafd834975b91531168513398c4ee6696d657043e14d47690715a', 142, 6201, 13),
            (nominal.identity_fixture(), '851150f2eca1cac5a4b4e3794b15c6a2504569712068cc773b0869e5fd11f01f', 551, 18853, 51),
            (nominal.const_fixture(True), '2543114e59e1728d6e903506c57af368b00d63bc932e0010f77bf57583278457', 1249, 37292, 74),
        ]
        for raw, expected, work, metadata, rows in cases:
            budgets = []; cls = m._Budget
            def make(*args, **kwargs):
                value = cls(*args, **kwargs); budgets.append(value); return value
            with mock.patch.object(m, '_Budget', make):
                out = m.derive_shared_fragment(raw)
            blob = json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), expected)
            self.assertEqual((budgets[0].work, budgets[0].metadata, budgets[0].rows), (work, metadata, rows))

    def test_retained_A_B_D_exact_normalization_and_capture_verification(self):
        for case in ('shared-id-arrow', 'shared-apply-arrow', 'shared-id-instance'):
            root, path, raw = retained(self, case)
            out = m.derive_shared_fragment(raw['projection']['projected_annotated'])
            for key in ('policy', 'steps', 'raw_normalized'):
                self.assertEqual(out[key], raw['normalization'][key])
            self.assertEqual((out['policy'], len(out['steps'])), (m.POLICY, 2))
            report = verified(root, path, case)
            self.assertTrue(report['fragment_admitted'])
            self.assertFalse(report['source_admitted']); self.assertFalse(report['native_admitted'])

    def test_retained_C_outer_first3_is_separate_from_old_producer_evidence(self):
        root, path, raw = retained(self, 'shared-apply-instance')
        out = m.derive_shared_fragment(raw['projection']['projected_annotated'])
        self.assertEqual((raw['normalization']['policy'], len(raw['normalization']['steps'])), (m.POLICY, 2))
        self.assertEqual((out['policy'], len(out['steps'])), (m.ARROW_BETA_POLICY, 4))
        self.assertEqual([s['arguments'] for s in out['steps']], [[AI], [AI], [f.I], [f.I]])
        outer, inner = out['steps'][:2]
        self.assertEqual(inner['input']['path'], outer['input']['path'] + ['argument'])
        self.assertEqual(out['polymorphism']['uses'][-1]['arguments'], [AI, AI])
        self.assertEqual(projection.erase_total(out['raw_normalized']), raw['normalization']['input_erased'])
        with self.assertRaisesRegex(ValueError, 'independent normalization.policy'):
            verified(root, path, 'shared-apply-instance')

    def test_retained_false3_on_arrow_use_without_new_beta_rejects(self):
        root, _, raw = retained(self, 'shared-id-arrow')
        raw['normalization']['policy'] = m.ARROW_BETA_POLICY
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'forged.json'; blob = json.dumps(raw).encode(); path.write_bytes(blob)
            with self.assertRaisesRegex(ValueError, 'independent normalization.policy'):
                verified(root, path, 'shared-id-arrow', hashlib.sha256(blob).hexdigest())


if __name__ == '__main__':
    unittest.main()
