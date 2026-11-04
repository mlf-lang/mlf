"""Host-only DATA placement checks; no compiler, producer or native calls.

Synthetic raw terms below are not genuine source/K acceptance. Optional original
Stage08 captures are read from IR8_PLACEMENT_CAPTURE_ROOT, pinned to completed
bytes and independently replayed. Their historical build authentication remains
external; replay does not manufacture source/native admission.

Runtime verification (not performed by this file): compare coarse and optional
plans using the unchanged production C runtime; associate DATA allocate/group
and f0 slot target; require that group's close_group before later force/invoke
of the still-pending field, fault=0, untruncated trace and successful zero ledger.
close_group precedes synchronous two-pass freeing, so a later successful event
establishes completed closure, whereas dropping a handle alone does not. Report
peak bytes/groups and extra RC/guard work independently, without assuming a win.
"""
import copy
import contextlib
import io
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE / 'tests')]
import planner_v8 as planner
import module_shared_transport as shared
import test_planner_v8 as f
from resource_ir_v8.checker import check_resources
from resource_ir_v8.program_schema import ResourceError
from resource_ir_v8.runtime_emit import emit_runtime

# Whole canonical outputs recorded before placement edits from the immutable
# Stage08 planner 497abcf3c30eafea3bcd01902b222cfeccf4f219782c1e03f057721260103112.
# Include work counters/source maps, not merely generated instruction semantics.
COARSE_GOLDENS = {
    'dead_vector_capture': '5eb5bedcc0e586dce55caee2b4de66749fbec2e67874d7b04d4d4ca79e3c3144',
    'curried_shared': '2a6ec6bdddd7450f67b3379aae9d07c7a46455bf2591a08730f2b5098dd4c5af',
    'unselected_arithmetic': 'd158cbd742a931bb817ba228d6366875089f3f61efd9b4ff6e5dada3e509f2b9',
    'scalar_box': 'b849d939d06e269930e257ecb5b361d872051083cde9f243e53d8e034ec0e9f8',
    'callable_box': '3c6dc75d09bb07efe32a071e629e2cc8b083287e27f5415e8371bccb607e58a0',
    'curried_box': '1ab68db77b590b00445cf7ae9be4476ccfbd11ed5992e6fa6b1a1cce4eb8f6e7',
    'wildcard_box': '7908b21d2981f227048fbaac72a1421be29e7f8c2277d9f8eb3b5c8ff533ea85',
    'pending_shared': 'be5bc4df7a3c25a2e33cc23862f9db81c26eee1645b098f519190f3f43d0da36',
    'nested_pair_capture': 'a642a4b0b3a0ea9ac558843ec2e0e82f84dae8f03e96d640b5d4a4d64b276281',
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def at(program, location):
    if location['root'] == 'entry': node = program['entry']
    elif location['root'] == 'function': node = program['functions'][location['name']]['body']
    else: node = program['codes'][location['name']]['body']
    for segment in location['segments']: node = node[segment]
    return node


def block_at(program, location):
    parent = dict(location, segments=location['segments'][:-1])
    return at(program, parent), location['segments'][-1]


def parameter_box():
    return f.with_data([f.declaration('Box', 'MkBox', f.I)],
        f.app(f.lam(1, f.I, f.data_case(f.construct('MkBox', f.var(1)),
              'MkBox', [2], f.var(2))), f.lit()))


def captured_parameter_box():
    # The outer argument can share its activation home. Two carriers do not
    # turn that merely Down fact into strict Below.
    body = f.app(f.lam(2, f.B, f.data_case(f.construct('MkBox', f.var(1)),
                 'MkBox', [3], f.var(3))), f.boolean())
    return f.with_data([f.declaration('Box', 'MkBox', f.I)],
                       f.app(f.lam(1, f.I, body), f.lit()))


def nested_box_carrier():
    nested = f.app(f.app(f.lam(2, f.I, f.lam(3, f.B,
                    f.data_case(f.var(1), 'MkBox', [4], f.var(4)))), f.lit(0)), f.boolean())
    return f.with_data([f.declaration('Box', 'MkBox', f.I)],
                       f.let(1, f.construct('MkBox', f.lit()), nested))


def duplicate_field_box():
    return f.with_data([f.declaration('Pair', 'MkPair', f.I, f.I)],
        f.let(1, f.lit(21), f.data_case(f.construct('MkPair', f.var(1), f.var(1)),
                 'MkPair', [2, 3], f.add(f.var(2), f.var(3)))))


def repeated_field_use():
    return f.with_data([f.declaration('Box', 'MkBox', f.I)],
        f.data_case(f.construct('MkBox', f.lit(21)), 'MkBox', [1],
                    f.add(f.var(1), f.var(1))))


def all_wildcard_box():
    return f.with_data([f.declaration('Pair', 'MkPair', f.I, f.I)],
        f.data_case(f.construct('MkPair', f.add(f.lit(1), f.lit(2)),
                               f.add(f.lit(3), f.lit(4))),
                    'MkPair', [None, None], f.lit(42)))


def empty_box():
    return f.with_data([f.declaration('Empty', 'MkEmpty')],
                       f.data_case(f.construct('MkEmpty'), 'MkEmpty', [], f.lit()))


class DefaultPlacementTests(unittest.TestCase):
    def test_default_remains_byte_equivalent_to_stage08(self):
        for name, expected in COARSE_GOLDENS.items():
            with self.subTest(fixture=name):
                raw = getattr(f, name)(); before = copy.deepcopy(raw)
                result = planner.plan_fragment(raw)
                self.assertEqual(raw, before)
                self.assertEqual(hashlib.sha256(canonical(result)).hexdigest(), expected)
                check_resources(result['program'])


class PlacementTests(unittest.TestCase):
    def checked(self, raw):
        before = copy.deepcopy(raw)
        result = planner.plan_fragment(raw, data_groups=True)
        self.assertEqual(raw, before)
        self.assertFalse(result['binding']['source_admitted'])
        self.assertFalse(result['binding']['ordinary_K_checked'])
        self.assertEqual(result['binding']['status'], 'candidate-not-resource-checked')
        check_resources(result['program'])
        coarse = planner.plan_fragment(raw)
        old = coarse['binding']['source_map']; new = result['binding']['source_map']
        # Actual syntax coverage, Scheme definitions, complete vectors and
        # ordinary allocation roles survive; placements are the only goal.
        self.assertEqual(new['term_map'], old['term_map'])
        self.assertEqual([(x['definition'], x['binder']) for x in new['scheme_map']],
                         [(x['definition'], x['binder']) for x in old['scheme_map']])
        self.assertEqual([(x['use'], x['definition'], x['arguments']) for x in new['use_map']],
                         [(x['use'], x['definition'], x['arguments']) for x in old['use_map']])
        self.assertEqual([(x['source'], x['role'], x['type_scope'], x['logical_type'])
                          for x in new['allocation_map']],
                         [(x['source'], x['role'], x['type_scope'], x['logical_type'])
                          for x in old['allocation_map']])
        self.assertEqual(result['program']['schemes'], coarse['program']['schemes'])
        self.assertEqual(result['program']['instantiations'], coarse['program']['instantiations'])
        self.assertEqual(sum(x['op'] == 'force' for x in f.instructions(result['program'])),
                         sum(x['op'] == 'force' for x in f.instructions(coarse['program'])))
        self.assertEqual(len(result['program']['functions']), len(coarse['program']['functions']))
        self.assertEqual(len(result['program']['codes']), len(coarse['program']['codes']))
        return result

    def isolated_data(self, result):
        program = result['program']
        constructors = result['binding']['source_map']['constructor_map']
        self.assertTrue(constructors)
        for row in constructors:
            alloc = at(program, row['allocation'])
            body, index = block_at(program, row['allocation'])
            group = next(x for x in body[:index]
                         if x['op'] == 'new_below' and x['out'] == alloc['in'])
            self.assertNotEqual(group['out'], group['ceiling'])
            self.assertEqual(set(group['imports']), set(alloc['fields'].values()))
            # Builder released after publication; no leaked authority sustains
            # the group after all ordinary DATA owners/slots are gone.
            self.assertTrue(any(x == {'op': 'drop', 'value': group['out']} for x in body[index+1:]))
            for value in alloc['fields'].values():
                producer = next((x for x in body[:index] if x.get('out') == value), None)
                if producer and 'in' in producer:
                    self.assertNotEqual(producer['in'], alloc['in'])

    def test_explicit_false_and_default_match_all_golden_fixtures(self):
        for name in COARSE_GOLDENS:
            raw = getattr(f, name)()
            self.assertEqual(canonical(planner.plan_fragment(raw, data_groups=False)),
                             canonical(planner.plan_fragment(raw)))

    def test_strategy_requires_exact_bool(self):
        for value in (None, 0, 1, 'true', [], {}):
            with self.subTest(value=value), self.assertRaises(planner.PlanningError):
                planner.plan_fragment(f.scalar_box(), data_groups=value)

    def test_scalar_payload_and_data_have_different_groups(self):
        result = self.checked(f.scalar_box()); self.isolated_data(result)
        alloc = next(x for x in result['program']['entry'] if x['op'] == 'alloc')
        scalar = next(x for x in result['program']['entry'] if x['op'] == 'scalar')
        self.assertEqual(alloc['fields'], {'f0': scalar['out']})
        self.assertNotEqual(alloc['in'], scalar['in'])

    def test_pending_callable_payload_and_both_shared_views_survive(self):
        result = self.checked(f.callable_box()); self.isolated_data(result)
        program = result['program']; maps = result['binding']['source_map']
        alloc = next(x for x in program['entry'] if x['op'] == 'alloc')
        pending = next(x for x in program['entry'] if x['op'] == 'application')
        self.assertEqual(alloc['fields'], {'f0': pending['out']})
        self.assertNotEqual(alloc['in'], pending['in'])
        self.assertFalse(any(x['op'] == 'force' for x in program['entry'][:program['entry'].index(alloc)]))
        self.assertEqual(len(program['schemes']), 1)
        self.assertEqual(len(program['instantiations']), 2)
        self.assertEqual(sum(x['op'] == 'generalize' for x in f.instructions(program)), 1)
        case = maps['case_map'][0]; body = program['codes'][case['code']]['body']
        self.assertEqual(sum(x['op'] == 'force' for x in body), 1)
        self.assertFalse(any(x['op'] == 'application' for x in body))
        captures = program['codes'][case['code']]['captures']
        self.assertEqual(len(captures), 1)
        self.assertTrue(all(c['relation'] == 'below' for c in captures.values()))
        captured = next(iter(captures))
        projection = next(i for i, x in enumerate(body) if x['op'] == 'end_borrow')
        released = next(i for i, x in enumerate(body) if x == {'op': 'drop', 'value': captured})
        self.assertLess(projection, released)
        self.assertLess(released, len(body)-1)

    def test_curried_payload_preserves_both_complete_two_coordinate_views(self):
        result = self.checked(f.curried_box()); self.isolated_data(result)
        p = result['program']
        self.assertEqual(next(iter(p['schemes'].values()))['parameters'], 2)
        vectors = {tuple(p['types'][t]['layout'] for t in row['arguments'])
                   for row in p['instantiations'].values()}
        self.assertEqual(vectors, {('#i64', '#bool'), ('#bool', '#i64')})
        generic = [c for c in p['functions'].values() if c['type_scope'] is not None]
        self.assertEqual(len(generic), 2)
        self.assertEqual(sum(len(c['captures']) for c in generic), 1)
        self.assertTrue(all(c['relation'] == 'down' for fun in generic for c in fun['captures'].values()))

    def test_parameter_and_transitive_down_capture_fall_back(self):
        for make in (parameter_box, captured_parameter_box):
            with self.subTest(make=make.__name__):
                result = self.checked(make()); p = result['program']
                for row in result['binding']['source_map']['constructor_map']:
                    self.assertEqual(at(p, row['allocation'])['in'], '$home')
                rows = [c for carrier in result['binding']['source_map']['carrier_map']
                        for c in carrier['mono_captures'] if c['binder'] == 1]
                self.assertTrue(rows)
                self.assertTrue(all(c['relation'] == 'down' for c in rows))

    def test_nested_carriers_keep_proven_below_but_never_invent_it(self):
        result = self.checked(nested_box_carrier()); self.isolated_data(result)
        rows = [c for carrier in result['binding']['source_map']['carrier_map']
                for c in carrier['mono_captures'] if c['binder'] == 1]
        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(all(c['relation'] == 'below' for c in rows))
        # Contrast the same transitive shape with an unknown same-home argument.
        fallback = self.checked(captured_parameter_box())
        rows = [c for carrier in fallback['binding']['source_map']['carrier_map']
                for c in carrier['mono_captures'] if c['binder'] == 1]
        self.assertTrue(all(c['relation'] == 'down' for c in rows))

    def test_duplicate_payload_and_multiple_field_uses_remain_owned(self):
        for make in (duplicate_field_box, repeated_field_use):
            with self.subTest(make=make.__name__):
                result = self.checked(make())
                if make is not all_wildcard_box: self.isolated_data(result)
                p = result['program']; case = result['binding']['source_map']['case_map'][0]
                body = p['codes'][case['code']]['body']
                fields = [x for x in body if x['op'] == 'field']
                self.assertEqual(len(fields), 2 if make is duplicate_field_box else 1)
                self.assertEqual(sum(x['op'] == 'end_borrow' for x in body), len(fields))

    def test_dead_and_wildcard_fields_keep_pending_graphs_without_extra_forcing(self):
        for make in (f.wildcard_box, all_wildcard_box, empty_box):
            with self.subTest(make=make.__name__):
                result = self.checked(make())
                if make is not all_wildcard_box: self.isolated_data(result)
                p = result['program']; case = result['binding']['source_map']['case_map'][0]
                body = p['codes'][case['code']]['body']
                self.assertEqual(sum(x['op'] == 'force' for x in body), 1)
                if make is all_wildcard_box:
                    self.assertFalse(any(x['op'] == 'field' for x in body))
                    alloc = next(x for x in body if x['op'] == 'alloc')
                    self.assertEqual(len(alloc['fields']), 2)
                    self.assertEqual(alloc['in'], '$home')  # coarse primitive thunks are only Down
                    self.assertEqual(sum(x['op'] == 'thunk' for x in body[:body.index(alloc)]), 2)

    def test_same_home_import_rewire_rejected_by_unchanged_checker(self):
        p = self.checked(f.scalar_box())['program']
        target = next(x for x in f.instructions(p) if x['op'] == 'new_below' and x['imports'])
        target['imports'] = [target['ceiling']]
        with self.assertRaises(ResourceError) as caught: check_resources(p)
        self.assertEqual((caught.exception.layer, caught.exception.code), ('resource', 'STRICT_IMPORT'))

    def test_unjustified_below_capture_rejected_by_unchanged_checker(self):
        p = planner.plan_fragment(f.callable_box())['program']
        c = next(c for c in p['codes'].values() if c['captures'])
        capture = next(iter(c['captures'].values()))
        self.assertEqual(capture['relation'], 'down'); capture['relation'] = 'below'
        with self.assertRaises(ResourceError) as caught: check_resources(p)
        self.assertEqual((caught.exception.layer, caught.exception.code), ('resource', 'CAPTURE_RELATION'))

    def test_emission_uses_existing_real_group_and_data_helpers(self):
        for raw in (f.scalar_box(), f.callable_box(), f.curried_box()):
            emission = emit_runtime(self.checked(raw)['program'])
            self.assertIn('rt8_new_below(', emission.runtime_source)
            self.assertIn('rt8_alloc(', emission.runtime_source)
            self.assertIn('rt8_field(', emission.runtime_source)
            self.assertIn('rt8_end_borrow(', emission.runtime_source)

    def test_generic_bodies_stay_coarse_and_map_addresses_remain_exact(self):
        for raw in (f.callable_box(), f.curried_box(), f.pending_shared()):
            result = self.checked(raw); p = result['program']; maps = result['binding']['source_map']
            for row in maps['scheme_map']:
                intro = at(p, row['generalize']); seal = at(p, row['seal'])
                self.assertEqual(intro['op'], 'generalize')
                self.assertEqual(seal, {'op': 'seal', 'value': row['result_owner']})
                self.assertFalse(any(x['op'] in ('new_root', 'new_below') for x in intro['body']))
                self.assertTrue(all(x['in'] == '$home' for x in intro['body'] if 'in' in x))
            for row in maps['allocation_map']:
                self.assertEqual(at(p, row['instruction'])['op'], row['role'])
            for row in maps['group_map']:
                if row['strategy'] == 'fresh-below':
                    created = at(p, row['create'])
                    self.assertEqual((created['op'], created['out']), ('new_below', row['allocation_key']))
                    self.assertEqual(at(p, row['drop_builder']), {'op': 'drop', 'value': created['out']})
                    self.assertTrue(all(s['strict'] is True for s in row['support']))
                else:
                    self.assertNotIn('create', row)
                    self.assertEqual(row['allocation_key'], row['home'])

    def test_scrutinee_alias_used_in_nested_arm_lambda_is_not_released_early(self):
        inner_case = f.data_case(f.var(1), 'MkBox', [4], f.add(f.var(2), f.var(4)))
        raw = f.with_data([f.declaration('Box', 'MkBox', f.I)],
            f.let(1, f.construct('MkBox', f.lit(21)),
                f.app(f.data_case(f.var(1), 'MkBox', [2], f.lam(3, f.B, inner_case), f.arr(f.B, f.I)),
                      f.boolean())))
        result = self.checked(raw); p = result['program']; maps = result['binding']['source_map']
        outer = next(row for row in maps['case_map'] if p['types'][row['result_type']]['tag'] == 'arrow')
        carrier = next(row for row in maps['carrier_map'] if row['ir_code'] == outer['code'])
        capture = next(row['capture'] for row in carrier['mono_captures'] if row['binder'] == 1)
        self.assertNotIn({'op': 'drop', 'value': capture}, [at(p, x) for x in outer['early_capture_releases']])
        body = p['codes'][outer['code']]['body']
        closure = next(i for i, x in enumerate(body) if x['op'] == 'closure')
        release = next(i for i, x in enumerate(body) if x == {'op': 'drop', 'value': capture})
        self.assertGreater(release, closure)
        self.assertTrue(any(capture in x.get('captures', {}).values() for x in body if x['op'] == 'closure'))

    def test_transitive_arm_retains_only_required_complete_view_pair(self):
        # Second coordinate is type-dead but remains part of view identity.
        arm = f.lam(4, f.B, f.add(f.var(3), f.app(f.use(1, f.I, f.B), f.lit(1))))
        raw = f.with_data([f.declaration('Box', 'MkBox', f.I)],
            f.let(1, f.prefix([100, 101], f.lam(2, f.ty(100), f.var(2))),
                f.app(f.data_case(f.construct('MkBox', f.app(f.use(1, f.I, f.I), f.lit(41))),
                                 'MkBox', [3], arm, f.arr(f.B, f.I)), f.boolean())))
        result = self.checked(raw); p = result['program']; maps = result['binding']['source_map']
        case = maps['case_map'][0]
        carrier = next(row for row in maps['carrier_map'] if row['ir_code'] == case['code'])
        captures = {tuple(p['types'][t]['layout'] for t in row['arguments']): row['capture']
                    for row in carrier['view_captures']}
        self.assertEqual(set(captures), {('#i64', '#i64'), ('#i64', '#bool')})
        released = [at(p, x)['value'] for x in case['early_capture_releases']]
        self.assertIn(captures[('#i64', '#i64')], released)
        self.assertNotIn(captures[('#i64', '#bool')], released)
        nested = next(row for row in maps['carrier_map']
                      if row['kind'] == 'lambda' and row['type_scope'] is None)
        self.assertEqual(len(nested['view_captures']), 1)
        self.assertEqual(nested['view_captures'][0]['source_view']['kind'], 'captured')


CAPTURE_ROOT = os.environ.get('IR8_PLACEMENT_CAPTURE_ROOT')
CAPTURES = {
    'box02': ('capture-box02',
        '5b6ac8023e72915006ec8358b57085413345cc79170f021e372dd03ab0f9330c',
        {'BoxData.emlf': 'ecef8d923d50b853afa94bfb4ddaeabd62971edb6bc1868f057c1b5f907f7f13',
         'main.emlf': '9eb4e3683ff5a8088b33b4d3148ab778e78b182d2611c86c6c39ac85c85eed59'},
        'native-data01/box02/planned.json'),
    'fnbox01': ('capture-fnbox01',
        'a323c70d884385ad42568d928b8ca3c77bdebd4109a640d6059cc107cb875603',
        {'SharedPoly.emlf': '50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7',
         'main.emlf': 'd0be8dbfb80e8cfe78a1c6b6d688b9e0b0d1c19bdc4ceda61a496eeaba61af50'},
        'native-data01/fnbox01/planned.json'),
    'curried': ('nominal-cli01/curried-field',
        'dfb306cbbdfed01c12504e27b428ca7163fac4e766d0d89a88cbf88b76711fcc',
        {'SharedPoly.emlf': '6fa9d46c3f07430be03fab525749d3ed17e5cf93e3d2b21218c91625567fd66d',
         'main.emlf': '9caa5996ac46d2fa1d5436c191565edb0c388b124e2f7dd0c91dd24ac6cc08ee'},
        'nominal-cli01/curried-field/planned.json'),
}


@unittest.skipUnless(CAPTURE_ROOT, 'set IR8_PLACEMENT_CAPTURE_ROOT for original completed Stage08 captures')
class GenuineCapturePlacementTests(unittest.TestCase):
    def test_three_pinned_captures_replay_and_plan_without_new_source_execution(self):
        from source_capture_v8 import verify_capture
        root = Path(CAPTURE_ROOT)
        for label, (relative, digest, fixture_hashes, old_plan) in CAPTURES.items():
            with self.subTest(capture=label):
                directory = root / relative; capture = directory / 'capture.stdout'
                verified = verify_capture(capture, fixture_root=directory/'sources', entry='main.emlf',
                    expected_source_hashes=fixture_hashes, expected_capture_sha256=digest)
                self.assertTrue(verified['fragment_admitted'])
                self.assertFalse(verified['source_admitted'])
                self.assertFalse(verified['native_admitted'])
                blob = capture.read_bytes()
                self.assertEqual(hashlib.sha256(blob).hexdigest(), digest)
                raw = json.loads(blob)['projection']['projected_annotated']
                coarse = planner.plan_fragment(raw)
                self.assertEqual(coarse, json.loads((root/old_plan).read_bytes()))
                result = PlacementTests.checked(self, raw)
                PlacementTests.isolated_data(self, result)
                self.assertEqual(len(result['binding']['source_map']['constructor_map']), 1)
                self.assertEqual(len(result['binding']['source_map']['case_map']), 1)
                self.assertEqual(len(result['program']['schemes']), 0 if label == 'box02' else 1)
                self.assertEqual(len(result['program']['instantiations']), 0 if label == 'box02' else 2)
                emit_runtime(result['program'])


class SourceCLIPlacementFlagTests(unittest.TestCase):
    @staticmethod
    def arguments(*extra):
        return ['main.emlf', '--module-root', '/inputs', '--ghc', '/trusted/ghc',
                '--output', '/fresh-output', *extra]

    def test_default_flag_is_false_and_keeps_old_plan(self):
        import run_source_v8 as cli
        args = cli.parser().parse_args(self.arguments())
        self.assertIs(args.data_groups, False)
        self.assertEqual(args.failure_policy, 'retain')
        self.assertEqual(canonical(planner.plan_fragment(f.scalar_box(), data_groups=args.data_groups)),
                         canonical(planner.plan_fragment(f.scalar_box())))

    def test_explicit_flag_has_no_failure_policy_side_effect(self):
        import run_source_v8 as cli
        args = cli.parser().parse_args(self.arguments('--data-groups'))
        self.assertIs(args.data_groups, True)
        self.assertEqual((args.fuel, args.failure_policy), (1000000, 'retain'))
        result = planner.plan_fragment(f.scalar_box(), data_groups=args.data_groups)
        self.assertEqual(result['binding']['mode'], 'data-groups-prototype')
        check_resources(result['program'])
        args = cli.parser().parse_args(self.arguments('--data-groups', '--failure-policy', 'destroy-terminal'))
        self.assertIs(args.data_groups, True)
        self.assertEqual(args.failure_policy, 'destroy-terminal')

    def test_flag_does_not_admit_arbitrary_modes_or_cached_json(self):
        import run_source_v8 as cli
        for extra in (('--data-groups=true',), ('--data-groups', 'false'),
                      ('--placement', 'automatic'), ('--capture', 'old.json'), ('--packet', 'old.json')):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    cli.parser().parse_args(self.arguments(*extra))
                self.assertEqual(caught.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
