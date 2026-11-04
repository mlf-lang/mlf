"""Closed scalar generic imports: host replay only, never a compiler/native run."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE / 'tests')]
import module_shared_transport as m
import test_module_shared_transport as f
from source_capture_v8 import verify_capture


def fixture(boolean=False, ready=False, aliases=False, mixed=False, nested=False):
    owner = (f.boolean() if boolean else f.lit(21)) if ready else (
        f.app(f.app(f.prim(11, 'ltInt'), f.lit(20)), f.lit(21)) if boolean else
        f.add(f.lit(20), f.lit(1)))
    body = f.var(1)
    if aliases:
        body = f.let(5, f.var(1), f.var(4))
    elif mixed:
        body = f.let(5, f.var(4), f.var(1))
    elif nested:
        body = f.lam(5, f.I, f.var(1))
    rhs = f.tabs(100, f.lam(3, f.tv(100), body))
    left, right = f.app(f.use(2, f.B), f.boolean()), f.app(f.use(2, f.I), f.lit(0))
    if nested:
        left, right = f.app(left, f.lit(0)), f.app(right, f.lit(0))
    result = f.choose(left, f.choose(right, f.lit(), f.lit(0)), f.lit(0)) if boolean else f.add(left, right)
    tail = f.let(2, rhs, result)
    if aliases:
        tail = f.let(4, f.var(1), tail)
    elif mixed:
        tail = f.let(4, f.boolean(), tail)
    return f.let(1, owner, tail)


def many_imports(count):
    serial = 2000
    def join(values):
        nonlocal serial
        if len(values) == 1:
            return values[0]
        middle = len(values) // 2
        a, b = join(values[:middle]), join(values[middle:])
        serial += 2
        return f.app(f.app(f.lam(serial, f.I, f.lam(serial + 1, f.I, f.var(serial + 1))), a), b)
    rhs = f.tabs(1000, f.lam(1001, f.tv(1000), join([f.var(i) for i in range(1, count + 1)])))
    raw = f.let(1002, rhs, f.app(f.use(1002, f.I), f.lit(0)))
    for i in reversed(range(1, count + 1)):
        raw = f.let(i, f.lit(i), raw)
    return raw


PINS = {
    'generic-closed-scalar': ('7dc72f17e7709afd071821d05baba3e08558ae91efc868e198850f568f71bbef',
        '9295c8ced992bdc1fbb6a70ee7382cd159c7c52253a7a24878715acdd9019cc3', f.I),
    'bool-scalar': ('837ec27a9cd550f4c1d7ea790698c28665150eabceb86b9c24de729a6a13d536',
        'fbca342f010827ffb2b27458c20ac240319f1af6843d69f05a4d7f25614a7066', f.B),
}
NEGATIVE_PINS = {
    'mixed-scalar': ('e60bc154bdf57c457d4ca277dd019cb1f4acc6087e628e19e7c2aecc517a5365', [f.I, f.B]),
    'alias-scalar': ('fd4a32addd4afc6c7ed531cdd4a8260a1d53b33a1fa9167de7b8161afdbd83fa', [f.I, f.I]),
}


def retained(test, case):
    root = os.environ.get('IR8_GENERIC_CAPTURE_ROOT')
    if root is None:
        test.skipTest('set IR8_GENERIC_CAPTURE_ROOT for retained original evidence')
    root = Path(root)
    path = root / ('capture-' + case + '01') / 'capture.stdout'
    data = path.read_bytes()
    test.assertEqual(hashlib.sha256(data).hexdigest(), PINS[case][0])
    return root, path, json.loads(data)


class GenericCaptureTests(unittest.TestCase):
    def reject(self, raw, code='CAPTURE'):
        with self.assertRaises(m.SharedTransportError) as caught:
            m.derive_shared_fragment(raw)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_pending_ready_int_bool_full_vectors_and_exact_rhs(self):
        for boolean in (False, True):
            for ready in (False, True):
                raw = fixture(boolean, ready)
                before = copy.deepcopy(raw)
                out = m.derive_shared_fragment(raw)
                self.assertEqual(raw, before)
                self.assertEqual(out['raw_normalized'], raw)
                self.assertEqual((out['policy'], out['steps']), (m.POLICY, []))
                definition, = out['polymorphism']['definitions']
                self.assertEqual(definition['free_term_bindings'], [1])
                self.assertEqual(definition['captures'], {'policy': m.GENERIC_CAPTURE_POLICY,
                    'scalars': [{'binding': 1, 'type': f.B if boolean else f.I,
                        'occurrences': [{'stage': 'normalized', 'path': ['body','value','body','body']}]}]})
                self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']], [[f.B], [f.I]])

    def test_aliases_are_two_explicit_bindings_not_physical_deduplication(self):
        out = m.derive_shared_fragment(fixture(aliases=True))
        definition, = out['polymorphism']['definitions']
        self.assertEqual(definition['free_term_bindings'], [1, 4])
        rows = definition['captures']['scalars']
        self.assertEqual([r['binding'] for r in rows], [1, 4])
        self.assertEqual([r['type'] for r in rows], [f.I, f.I])

    def test_mixed_intrinsics_and_nested_ordinary_carrier_occurrences(self):
        out = m.derive_shared_fragment(fixture(mixed=True))
        rows = out['polymorphism']['definitions'][0]['captures']['scalars']
        self.assertEqual([(r['binding'],r['type']) for r in rows], [(1,f.I),(4,f.B)])
        out = m.derive_shared_fragment(fixture(nested=True))
        row, = out['polymorphism']['definitions'][0]['captures']['scalars']
        self.assertEqual(row['occurrences'][0]['path'], ['body','value','body','body','body'])

    def test_64_explicit_imports_and_65_rejection(self):
        out = m.derive_shared_fragment(many_imports(64))
        self.assertEqual(len(out['polymorphism']['definitions'][0]['captures']['scalars']), 64)
        self.reject(many_imports(65), 'LIMIT')

    def test_capture_bearing_definition_below_ordinary_lambda_is_rejected(self):
        self.reject(f.app(f.lam(80, f.I, fixture()), f.lit()))

    def test_capture_bearing_definition_in_let_rhs_is_rejected(self):
        self.reject(f.let(80, fixture(), f.var(80)))

    def test_ordinary_wrapper_is_not_erased_to_obtain_direct_lambda(self):
        raw = fixture()
        rhs = raw['body']['value']
        rhs['body'] = f.app(f.lam(80, f.arr(f.tv(100),f.I), f.var(80)), rhs['body'])
        self.reject(raw)

    def test_scheme_and_complete_view_are_not_scalar_imports(self):
        rhs = f.tabs(101, f.lam(21, f.tv(101), f.app(f.use(1,f.I),f.lit())))
        self.reject(f.shared(f.let(20,rhs,f.app(f.use(20,f.B),f.boolean()))))
        rhs = f.tabs(101, f.lam(21,f.tv(101),f.app(f.var(22),f.lit())))
        self.reject(f.shared(f.let(22,f.use(1,f.I),f.let(20,rhs,f.app(f.use(20,f.B),f.boolean())))))

    def test_callable_and_nominal_imports_rejected(self):
        raw = fixture(); raw['value'] = f.lam(80,f.I,f.var(80))
        raw['body']['value']['body']['body'] = f.app(f.var(1),f.lit())
        self.reject(raw)
        raw = f.with_data(f.let(1, f.ctor('Pack',f.lit()),
            f.let(2,f.tabs(100,f.lam(3,f.tv(100),f.var(1))),f.lit())), f.data_decl())
        self.reject(raw)

    def test_nested_generalization_is_unchanged_rejection(self):
        raw = fixture(); raw['body']['value']['body']['body'] = f.let(7,
            f.tabs(101,f.lam(8,f.tv(101),f.var(1))), f.app(f.use(7,f.I),f.lit()))
        self.reject(raw, 'NESTED')

    def test_generic_primitive_boundary_remains_rejected(self):
        for body in (f.add(f.var(1),f.lit(0)), f.choose(f.boolean(),f.var(1),f.lit(0))):
            raw = fixture(); raw['body']['value']['body']['body'] = body
            self.reject(raw, 'FRAGMENT')

    def test_forged_capture_inventory_is_not_replay_authority(self):
        raw = fixture(); checked = m.derive_shared_fragment(raw)
        mutations = [lambda d: d.pop('captures'), lambda d: d.update(free_term_bindings=[]),
            lambda d: d['captures'].update(policy='foreign'), lambda d: d['captures']['scalars'].clear(),
            lambda d: d['captures']['scalars'][0].update(type=f.B),
            lambda d: d['captures']['scalars'][0].update(binding=99),
            lambda d: d['captures']['scalars'][0]['occurrences'].clear()]
        for mutate in mutations:
            forged = copy.deepcopy(checked); mutate(forged['polymorphism']['definitions'][0])
            with self.assertRaises(m.SharedTransportError):
                m.validate_shared_fragment(raw, forged)

    def test_no_capture_evidence_stays_absent(self):
        out = m.derive_shared_fragment(f.shared())
        for definition in out['polymorphism']['definitions']:
            self.assertNotIn('captures',definition)
            self.assertEqual(definition['free_term_bindings'],[])

    def test_actual_original_int_and_bool_replay_custody_and_proofs(self):
        for case in PINS:
            root, path, raw = retained(self,case)
            out = m.derive_shared_fragment(raw['projection']['projected_annotated'])
            for key in ('policy','steps','raw_normalized'):
                self.assertEqual(out[key],raw['normalization'][key])
            definition, = out['polymorphism']['definitions']
            row, = definition['captures']['scalars']
            self.assertEqual(row['type'],PINS[case][2])
            self.assertEqual(definition['free_term_bindings'],[row['binding']])
            report = verify_capture(path, fixture_root=root/'inputs'/case, entry='main.emlf',
                expected_source_hashes={'main.emlf':PINS[case][1],
                    'SharedPoly.emlf':'50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'},
                expected_capture_sha256=PINS[case][0])
            self.assertTrue(report['fragment_admitted'])
            self.assertEqual(report['normalization_replay'],'all exact independent fields match')
            join, = report['retained_prefix_binding_joins']
            self.assertEqual(join['binding'],definition['binding'])
            self.assertEqual(join['association'],'compiler_local_or_generated')
            self.assertIsNone(join['resolver_allocation'])
            self.assertFalse(report['source_admitted'])
            self.assertFalse(report['native_admitted'])

    def test_actual_mixed_alias_diagnostics_reach_unchanged_primitive_frontier(self):
        root = os.environ.get('IR8_GENERIC_CAPTURE_ROOT')
        if root is None:
            self.skipTest('set IR8_GENERIC_CAPTURE_ROOT for retained original evidence')
        for case, (digest, types) in NEGATIVE_PINS.items():
            data = (Path(root)/('capture-'+case+'01')/'capture.stdout').read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
            original = json.loads(data)
            inventories = []; implementation = m._generic_captures
            def record(*args, **kwargs):
                result = implementation(*args, **kwargs)
                inventories.append(result)
                return result
            with mock.patch.object(m, '_generic_captures', record):
                with self.assertRaises(m.SharedTransportError) as caught:
                    m.derive_shared_fragment(original['projection']['projected_annotated'])
            self.assertEqual(caught.exception.code, 'FRAGMENT')
            self.assertIn('generic construction opcode', str(caught.exception))
            rejected = m._get(original['normalization']['raw_normalized'], caught.exception.path)
            self.assertEqual(rejected['tag'], 'primitive')
            self.assertEqual(rejected['id'], 13 if case == 'mixed-scalar' else 8)
            inventory, = inventories
            self.assertEqual([r['type'] for r in inventory['scalars']], types)
            self.assertEqual(len({r['binding'] for r in inventory['scalars']}), 2)


if __name__ == '__main__':
    unittest.main()
