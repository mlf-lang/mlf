"""Synthetic/raw-extracted independent replay tests, NOT source/K/native tests.

No original compiler is invoked. The extracted fixture preserves exact raw
subtrees; synthetic lexical surroundings close them for this bounded seam.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import module_shared_transport as m
import module_projection as p

I = m.INT
B = m.BOOL
BOT = {'tag': 'bottom'}
R = {'tag': 'refl'}


def name(i, hint=None):
    return {'id': i, 'hint': hint if hint is not None else 'v' + str(i)}


def var(i, hint=None):
    return {'tag': 'var', 'name': name(i, hint)}


def tv(i):
    return {'tag': 'var', 'id': i}


def arr(a, b):
    return {'tag': 'arrow', 'from': a, 'to': b}


def forall(i, body, bound=BOT):
    return {'tag': 'forall', 'id': i, 'bound': bound, 'body': body}


def lit(n=42):
    return {'tag': 'int64', 'value': n}


def boolean(b=True):
    return {'tag': 'bool', 'value': b}


def lam(i, typ, body):
    return {'tag': 'lambda', 'parameter': name(i), 'parameter_type': typ, 'body': body}


def app(f, a):
    return {'tag': 'application', 'function': f, 'argument': a}


def let(i, value, body):
    return {'tag': 'let', 'name': name(i), 'value': value, 'body': body}


def tabs(i, body, bound=BOT):
    return {'tag': 'type_lambda', 'id': i, 'bound': bound, 'body': body}


def then(a, b):
    return {'tag': 'then', 'first': a, 'second': b}


def inst(typ):
    return then({'tag': 'inner', 'witness': {'tag': 'bottom', 'type': typ}}, {'tag': 'elim'})


def tapp(value, proof):
    return {'tag': 'type_application', 'value': value, 'witness': proof}


def use(i, *args):
    result = var(i)
    for argument in args:
        result = tapp(result, inst(argument))
    return result


def prim(code, label, args=()):
    return {'tag': 'primitive', 'id': code, 'name': label, 'arguments': list(args)}


def add(a, b):
    return app(app(prim(8, 'addInt'), a), b)


def choose(condition, yes, no):
    return app(app(app(prim(13, 'ifThenElse', [I]), condition), yes), no)


def identity():
    # Intentionally a pending ordinary application, not an identity recognizer.
    return tabs(100, app(lam(2, arr(tv(100), tv(100)), var(2)),
                         lam(3, tv(100), let(4, app(lam(5, tv(100), var(5)), var(3)), var(4)))))


def shared(body=None):
    if body is None:
        body = choose(app(use(1, B), boolean()), add(app(use(1, I), lit(41)), lit(1)), lit(0))
    return let(1, identity(), body)


class ReplayTests(unittest.TestCase):
    def reject(self, tree, code=None):
        with self.assertRaises(m.SharedTransportError) as caught:
            m.derive_shared_fragment(tree)
        if code:
            self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def test_shared_pending_rhs_not_specialized(self):
        tree = shared()
        result = m.derive_shared_fragment(tree)
        self.assertEqual(result['raw_normalized'], tree)
        self.assertEqual(result['steps'], [])
        self.assertEqual(result['status'], 'independent-fragment-replay-only')
        definition, = result['polymorphism']['definitions']
        self.assertEqual(definition['rhs_cursor']['path'], ['value', 'body'])
        self.assertEqual(definition['free_term_bindings'], [])
        self.assertNotIn('resolver_binding', definition)
        self.assertEqual([u['arguments'] for u in result['polymorphism']['uses']], [[B], [I]])
        self.assertEqual(p.erase_total(tree), p.erase_total(result['raw_normalized']))
        self.assertEqual(m.validate_shared_fragment(tree, result), result)

    def test_every_ordinary_node_has_unique_correspondence(self):
        result = m.derive_shared_fragment(shared())
        rows = result['term_correspondence']
        paths = [tuple(r['normalized']['path']) for r in rows]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all('original' not in r for r in rows))
        self.assertEqual(sum(r['tag'] == 'lambda' for r in rows), 3)
        self.assertEqual(sum(r['tag'] == 'let' for r in rows), 2)

    def test_caller_snapshot(self):
        tree = shared()
        result = m.derive_shared_fragment(tree)
        tree['value']['id'] = 999
        self.assertEqual(result['input_annotated']['value']['id'], 100)

    def test_sequential_types_preorder_witness(self):
        proof = then(R, then(inst(I), R))
        source = forall(100, arr(tv(100), tv(100)))
        out = m.replay_type_computation(proof, source)
        self.assertEqual(out['result_type'], arr(I, I))
        rows = out['proof_intermediates']
        self.assertEqual([r['proof_path'] for r in rows],
                         [[], ['first'], ['second'], ['second', 'first'],
                          ['second', 'first', 'first'], ['second', 'first', 'first', 'witness'],
                          ['second', 'first', 'second'], ['second', 'second']])
        by_path = {tuple(r['proof_path']): r for r in rows}
        self.assertEqual(by_path[('second', 'first', 'second')]['source_type'],
                         forall(100, arr(tv(100), tv(100)), I))
        self.assertEqual(by_path[('second', 'second')]['source_type'], arr(I, I))

    def test_complete_two_formal_vector_in_one_raw_proof(self):
        rhs = tabs(100, tabs(101, lam(2, tv(100), lam(3, tv(101), var(2)))))
        proof = then(inst(I), inst(B))
        body = app(app(tapp(var(1), proof), lit()), boolean())
        result = m.derive_shared_fragment(let(1, rhs, body))
        self.assertEqual(result['polymorphism']['uses'][0]['arguments'], [I, B])
        self.assertEqual(len(result['polymorphism']['type_applications']), 1)

    def test_shared_use_keeps_erased_refl_occurrence_ids(self):
        spine = tapp(tapp(tapp(var(1), R), inst(I)), then(R, R))
        result = m.derive_shared_fragment(shared(app(spine, lit())))
        rows = result['polymorphism']['type_applications']
        self.assertEqual([r['disposition'] for r in rows], ['refl', 'shared_use', 'refl'])
        self.assertEqual(result['polymorphism']['uses'][0]['type_applications'], [2, 1, 0])

    def test_scope_rejects_iterators_without_consuming(self):
        def untrusted():
            raise AssertionError('must not consume arbitrary iterator')
            yield None
        with self.assertRaisesRegex(m.SharedTransportError, 'SCHEMA'):
            m.replay_type_computation(R, I, scope=untrusted())

    def test_dead_parameter_stays_in_key(self):
        rhs = tabs(100, tabs(101, lam(2, tv(100), var(2))))
        body = add(app(use(1, I, B), lit(20)), app(use(1, I, I), lit(22)))
        result = m.derive_shared_fragment(let(1, rhs, body))
        uses = result['polymorphism']['uses']
        self.assertEqual([u['arguments'] for u in uses], [[I, B], [I, I]])
        self.assertEqual(uses[0]['instantiated_type'], uses[1]['instantiated_type'])

    def test_same_type_ids_in_disjoint_scopes_not_global_rigids(self):
        tree = let(1, tabs(100, lam(2, tv(100), var(2))),
                   let(3, tabs(100, lam(4, tv(100), var(4))),
                       add(app(use(1, I), lit(20)), app(use(3, I), lit(22)))))
        result = m.derive_shared_fragment(tree)
        defs = result['polymorphism']['definitions']
        self.assertEqual([d['prefix'][0]['id'] for d in defs], [100, 100])
        self.assertEqual([u['definition'] for u in result['polymorphism']['uses']], [0, 1])
        scopes = result['polymorphism']['type_scopes']
        self.assertEqual([r['parent'] for r in scopes], [None, None, None, None])

    def test_nested_carrier_retains_both_use_occurrences(self):
        body = app(lam(20, I, app(lam(21, I,
            choose(app(use(1, B), boolean()), add(app(use(1, I), var(20)), var(21)), lit(0))), lit(1))), lit(41))
        result = m.derive_shared_fragment(shared(body))
        self.assertEqual([u['arguments'] for u in result['polymorphism']['uses']], [[B], [I]])

    def test_repeated_same_vector_is_not_coalesced_by_transport(self):
        result = m.derive_shared_fragment(shared(add(app(use(1, I), lit(20)), app(use(1, I), lit(22)))))
        self.assertEqual(len(result['polymorphism']['uses']), 2)
        self.assertNotEqual(result['polymorphism']['uses'][0]['source'], result['polymorphism']['uses'][1]['source'])

    def test_direct_step_exact_state_subtrees_and_no_term_beta(self):
        tree = tapp(identity(), inst(I))
        result = m.derive_shared_fragment(tree)
        step, = result['steps']
        self.assertEqual(step['rule'], 'instantiate_direct_closed')
        self.assertEqual(step['input'], {'state': 0, 'path': [], 'subtree': tree})
        self.assertEqual(step['output']['state'], 1)
        self.assertEqual(result['raw_normalized']['tag'], 'application')
        self.assertEqual(result['polymorphism']['definitions'], [])
        self.assertEqual(result['polymorphism']['type_applications'][0]['disposition'], 'direct_closed')

    def test_pure_composite_refl_erases_one_wrapper(self):
        tree = tapp(tapp(lit(), R), then(R, R))
        result = m.derive_shared_fragment(tree)
        self.assertEqual([s['rule'] for s in result['steps']], ['erase_refl', 'erase_refl'])
        self.assertEqual(result['raw_normalized'], lit())
        self.assertEqual([r['disposition'] for r in result['polymorphism']['type_applications']], ['refl', 'refl'])

    def test_refl_on_type_prefix_does_not_force_zero_argument_direct(self):
        tree = tapp(tapp(identity(), R), inst(I))
        result = m.derive_shared_fragment(tree)
        self.assertEqual(len(result['steps']), 1)
        self.assertEqual(result['steps'][0]['witnesses'], [R, inst(I)])

    def test_outer_first_substitution_closes_inner_proof(self):
        inner = tapp(tabs(101, lam(2, tv(101), var(2))), inst(tv(100)))
        tree = app(tapp(tabs(100, inner), inst(I)), lit())
        result = m.derive_shared_fragment(tree)
        self.assertEqual([s['input']['path'] for s in result['steps']], [['function'], ['function']])
        proof_rows = result['polymorphism']['type_applications']
        self.assertEqual(proof_rows[1]['witness'], inst(tv(100)))
        self.assertEqual(proof_rows[1]['normalization_steps'], [0, 1])
        self.assertEqual(result['steps'][1]['arguments'], [I])
        self.assertEqual(result['raw_normalized'], app(lam(2, I, var(2)), lit()))

    def test_raw_extracted_pending_rhs_and_conditional(self):
        f = json.loads((Path(__file__).with_name('shared_fragment_raw_extract.json')).read_text())
        self.assertEqual(f['status'], 'raw-extracted-subtrees-not-complete-source-or-K-evidence')
        flag = f['flag_binding']
        conditional = app(app(f['conditional_with_free_flag'], lit(42)), lit(0))
        tree = {'tag': 'let', 'name': flag, 'value': boolean(), 'body': conditional}
        result = m.derive_shared_fragment(tree)
        self.assertEqual([s['type_binders'][0]['id'] for s in result['steps']], [87406, 39084])
        raw_inner = result['polymorphism']['type_applications'][1]
        self.assertEqual(raw_inner['witness']['first']['witness']['type'], tv(87406))
        self.assertEqual(result['steps'][1]['arguments'], [I])
        binding = f['shared_binding']
        source_use = tapp({'tag': 'var', 'name': binding}, inst(I))
        rhs_tree = {'tag': 'let', 'name': binding, 'value': f['shared_rhs'], 'body': app(source_use, lit())}
        replay = m.derive_shared_fragment(rhs_tree)
        self.assertEqual(replay['raw_normalized']['value'], f['shared_rhs'])
        self.assertEqual(len(replay['polymorphism']['definitions'][0]['ordinary_nodes']), 10)

    def test_full_declarations_preserved_but_not_runtime_admitted(self):
        declaration = {'tag': 'data', 'name': 'Unused', 'parameters': [], 'constructors': [{'name': 'Unused', 'fields': []}]}
        tree = {'tag': 'with_data', 'declarations': [declaration], 'body': shared()}
        result = m.derive_shared_fragment(tree)
        self.assertEqual(result['raw_normalized']['declarations'], [declaration])

    def test_claim_mutations_all_reject(self):
        tree = shared()
        result = m.derive_shared_fragment(tree)
        mutations = [lambda v: v.update(extra=True),
                     lambda v: v['polymorphism']['uses'][0].update(arguments=[I]),
                     lambda v: v['polymorphism']['definitions'][0].update(resolver_binding=None),
                     lambda v: v['polymorphism']['type_applications'].pop(),
                     lambda v: v['term_correspondence'].pop(),
                     lambda v: v['raw_normalized']['value'].update(body=lit()),
                     lambda v: v['polymorphism']['type_scopes'][0].update(parent=0)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                claim = copy.deepcopy(result)
                mutate(claim)
                with self.assertRaisesRegex(m.SharedTransportError, 'EVIDENCE'):
                    m.validate_shared_fragment(tree, claim)

    def test_bare_scheme_rejected(self):
        self.reject(shared(var(1)))

    def test_partial_scheme_rejected_even_same_arrow_body(self):
        rhs = tabs(100, tabs(101, lam(2, tv(100), var(2))))
        self.reject(let(1, rhs, use(1, I)))

    def test_extra_elimination_rejected(self):
        self.reject(shared(app(use(1, I, B), lit())), 'PROOF')

    def test_open_shared_use_rejected(self):
        body = tabs(101, app(use(1, tv(101)), lit()))
        self.reject(shared(body))

    def test_external_generalization_capture_rejected(self):
        rhs = tabs(101, use(1, tv(101)))
        self.reject(shared(let(20, rhs, app(use(20, I), lit()))), 'CAPTURE')

    def test_nested_generalization_rejected(self):
        rhs = tabs(100, let(2, tabs(101, lam(3, tv(101), var(3))), lam(4, tv(100), var(4))))
        self.reject(let(1, rhs, app(use(1, I), lit())), 'NESTED')

    def test_recursive_generic_rejected(self):
        tree = {'tag': 'letrec', 'bindings': [{'name': name(1), 'type': forall(100, arr(tv(100), tv(100))), 'value': identity()}], 'body': lit()}
        self.reject(tree, 'FRAGMENT')

    def test_generic_scalar_primitive_rejected(self):
        rhs = tabs(100, lam(2, tv(100), add(lit(20), lit(22))))
        self.reject(let(1, rhs, app(use(1, I), lit())), 'FRAGMENT')

    def test_unknown_nominal_operation_rejected(self):
        self.reject({'tag': 'constructor', 'name': '()', 'arguments': []}, 'FRAGMENT')

    def test_unsupported_proof_rejected_even_if_result_plausible(self):
        self.reject(tapp(lit(), {'tag': 'intro', 'id': 100}), 'PROOF')

    def test_nonbottom_prefix_rejected(self):
        self.reject(tapp(tabs(100, lam(2, tv(100), var(2)), I), inst(I)), 'PREFIX')

    def test_higher_kind_prefix_rejected(self):
        bound = {'tag': 'bottom_kind', 'kind': {'tag': 'arrow', 'from': {'tag': 'star'}, 'to': {'tag': 'star'}}}
        self.reject(tapp(tabs(100, lit(), bound), inst(I)), 'TYPE')

    def test_repeated_active_type_id_rejected(self):
        self.reject(tapp(tabs(100, tabs(100, lit())), then(inst(I), inst(B))), 'TYPE_SCOPE')

    def test_unbound_annotation_rejected(self):
        self.reject(lam(1, tv(99), var(1)), 'TYPE_SCOPE')

    def test_forall_does_not_scope_over_own_bound(self):
        with self.assertRaisesRegex(m.SharedTransportError, 'TYPE_SCOPE'):
            m.replay_type_computation(R, forall(100, arr(tv(100), tv(100)), tv(100)))

    def test_proof_argument_must_be_well_formed_in_actual_scope(self):
        with self.assertRaisesRegex(m.SharedTransportError, 'TYPE_SCOPE'):
            m.replay_type_computation(inst(tv(101)), forall(100, arr(tv(100), tv(100))))

    def test_scoped_raw_argument_allowed_before_normalization(self):
        result = m.replay_type_computation(inst(tv(101)), forall(100, arr(tv(100), tv(100))),
                                           scope=[{'id': 101, 'bound': BOT}])
        self.assertEqual(result['result_type'], arr(tv(101), tv(101)))

    def test_wrong_bound_inner_proof_rejected(self):
        with self.assertRaisesRegex(m.SharedTransportError, 'PROOF'):
            m.replay_type_computation(inst(I), forall(100, arr(tv(100), tv(100)), B))

    def test_incomplete_and_reversed_pairs_rejected(self):
        for proof in [{'tag': 'inner', 'witness': {'tag': 'bottom', 'type': I}},
                      then({'tag': 'elim'}, {'tag': 'inner', 'witness': {'tag': 'bottom', 'type': I}})]:
            with self.subTest(proof=proof), self.assertRaisesRegex(m.SharedTransportError, 'PROOF'):
                m.replay_type_computation(proof, forall(100, arr(tv(100), tv(100))))

    def test_ill_typed_unselected_branch_rejected(self):
        self.reject(shared(choose(boolean(), lit(), app(use(1, B), lit()))), 'TYPE')

    def test_unknown_type_constructor_rejected(self):
        self.reject(lam(1, {'tag': 'constructor', 'name': 'CounterfeitInt', 'arguments': []}, var(1)), 'TYPE')

    def test_ordinary_application_not_erased(self):
        tree = app(lam(1, I, var(1)), lit())
        result = m.derive_shared_fragment(tree)
        self.assertEqual(result['raw_normalized'], tree)
        self.assertEqual(result['steps'], [])

    def test_boolean_is_not_term_integer(self):
        self.reject(lit(True), 'SCHEMA')

    def test_duplicate_term_ids_and_inconsistent_hints_rejected(self):
        self.reject(lam(1, I, lam(1, I, var(1))), 'SCHEMA')
        self.reject(lam(1, I, var(1, 'different')), 'SCHEMA')

    def test_deep_input_rejected_without_recursion_change(self):
        old = sys.getrecursionlimit()
        tree = lit()
        for _ in range(101):
            tree = tapp(tree, R)
        self.reject(tree, 'LIMIT')
        self.assertEqual(sys.getrecursionlimit(), old)

    def test_cycle_rejected(self):
        tree = tapp(lit(), R)
        tree['value'] = tree
        self.reject(tree, 'SCHEMA')

    def test_oversized_text_stops_at_byte_bound(self):
        with mock.patch.object(m, 'MAX_BYTES', 128):
            # Default arguments are fixed, so use the explicit ingress helper to
            # exercise the same bounded chunk path with a small finite control.
            with self.assertRaisesRegex(m.SharedTransportError, 'LIMIT'):
                m._bounded({'hint': 'x' * 1024}, byte_limit=128)

    def test_surrogate_rejected(self):
        self.reject({'tag': 'var', 'name': {'id': 1, 'hint': '\ud800'}}, 'SCHEMA')

    def test_work_budget_fail_closed(self):
        with mock.patch.object(m, 'MAX_WORK', 2):
            self.reject(shared(), 'LIMIT')

    def test_metadata_budget_fail_closed(self):
        with mock.patch.object(m, 'MAX_METADATA_BYTES', 32):
            self.reject(shared(), 'LIMIT')

    def test_definition_parameter_use_and_proof_limits(self):
        for setting, limit in [('MAX_DEFINITIONS', 0), ('MAX_PARAMETERS', 0), ('MAX_USES', 0), ('MAX_PROOFS', 0)]:
            with self.subTest(setting=setting), mock.patch.object(m, setting, limit):
                self.reject(shared(), 'LIMIT')

    def test_proof_atom_limit(self):
        proof = R
        for _ in range(8):
            proof = then(R, proof)
        with mock.patch.object(m, 'MAX_PROOF_ATOMS', 8), self.assertRaisesRegex(m.SharedTransportError, 'LIMIT'):
            m.replay_type_computation(proof, I)

    def test_wide_container_rejected_before_stack_expansion(self):
        with self.assertRaisesRegex(m.SharedTransportError, 'immediate container'):
            m._bounded([None] * 101, cells=100)

    def test_scope_bound_before_copy(self):
        with mock.patch.object(m, 'MAX_CELLS', 2), self.assertRaisesRegex(m.SharedTransportError, 'scope sequence'):
            m.replay_type_computation(R, I, scope=[None] * 3)

    def test_scope_bool_identity_rejected(self):
        with self.assertRaisesRegex(m.SharedTransportError, 'TYPE_SCOPE'):
            m.replay_type_computation(R, I, scope=[{'id': True, 'bound': BOT}])

    def test_nominal_and_higher_rank_not_smuggled_through_refl(self):
        with self.assertRaises(m.SharedTransportError):
            m.replay_type_computation(R, arr(forall(100, arr(tv(100), tv(100))), I))


def nominal_type(n='Box'):
    return {'tag': 'constructor', 'name': n, 'arguments': []}


def field_type(typ):
    if typ['tag'] == 'constructor':
        return {'tag': 'applied', 'name': typ['name'], 'arguments': []}
    return {'tag': 'function', 'from': field_type(typ['from']), 'to': field_type(typ['to'])}


def data_decl(n='Box', constructor='Pack', fields=(I,)):
    return {'tag': 'data_kind', 'name': n, 'parameters': [],
            'constructors': [{'name': constructor, 'fields': [field_type(t) for t in fields]}]}


def ctor(n='Pack', *arguments):
    node = {'tag': 'constructor', 'name': n, 'arguments': []}
    for argument in arguments:
        node = app(node, argument)
    return node


def case(subject, constructor='Pack', binders=(20,), body=None, result=I):
    if body is None:
        body = var(20)
    return {'tag': 'case', 'scrutinee': subject, 'result_type': result,
            'alternatives': [{'pattern': {'tag': 'constructor', 'constructor': constructor,
                                         'fields': [None if x is None else name(x) for x in binders]},
                              'body': body}]}


def with_data(body, *declarations):
    return {'tag': 'with_data', 'declarations': list(declarations) or [data_decl()], 'body': body}


class NominalReplayTests(unittest.TestCase):
    def reject(self, tree, code=None):
        with self.assertRaises(m.SharedTransportError) as caught:
            m.derive_shared_fragment(tree)
        if code:
            self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def test_scalar_data_full_association_and_graph(self):
        tree = with_data(let(10, ctor('Pack', lit()), case(var(10))))
        result = m.derive_shared_fragment(tree)
        data = result['nominal_data']
        self.assertEqual(result['raw_normalized'], tree)
        self.assertEqual(data['policy'], m.NOMINAL_POLICY)
        declaration, = data['declarations']
        self.assertEqual(declaration['source'], {'stage': 'projected', 'path': ['declarations', '0']})
        self.assertEqual((declaration['name'], declaration['constructor'], declaration['field_types']),
                         ('Box', 'Pack', [I]))
        self.assertEqual(data['constructors'][0]['application_spine'],
                         [{'stage': 'normalized', 'path': ['body', 'value']}])
        self.assertEqual(data['cases'][0]['fields'], [{'index': 0, 'binding': name(20), 'type': I}])
        rows = result['term_correspondence']
        self.assertEqual(len(rows), 7)
        self.assertIn(['body', 'body', 'alternatives', '0', 'body'], [r['normalized']['path'] for r in rows])
        self.assertEqual(p.erase_total(tree), result['input_erased'])

    def test_same_field_shape_does_not_merge_nominals(self):
        tree = with_data(let(10, ctor('PackA', lit()),
                             let(11, ctor('PackB', lit()), add(case(var(10), 'PackA', (20,)),
                                                              case(var(11), 'PackB', (21,), var(21))))),
                         data_decl('A', 'PackA'), data_decl('B', 'PackB'))
        result = m.derive_shared_fragment(tree)
        self.assertEqual([r['index'] for r in result['nominal_data']['declarations']], [0, 1])
        self.assertEqual([r['result_type'] for r in result['nominal_data']['constructors']],
                         [nominal_type('A'), nominal_type('B')])
        bad = with_data(app(lam(10, nominal_type('A'), lit()), ctor('PackB', lit())),
                        data_decl('A', 'PackA'), data_decl('B', 'PackB'))
        self.reject(bad, 'TYPE')

    def test_arrow_field_preserves_pending_argument_and_shared_views(self):
        pending = app(lam(30, arr(I, I), var(30)), use(1, I))
        boxed = let(10, ctor('Pack', pending),
                    let(11, case(var(10), body=var(20), result=arr(I, I)),
                        choose(app(use(1, B), boolean()), app(var(11), lit()), lit(0))))
        tree = with_data(shared(boxed), data_decl(fields=(arr(I, I),)))
        result = m.derive_shared_fragment(tree)
        self.assertEqual(result['raw_normalized'], tree)
        self.assertEqual([u['arguments'] for u in result['polymorphism']['uses']], [[I], [B]])
        argument = result['nominal_data']['constructors'][0]['arguments'][0]['path']
        self.assertEqual(m._get(result['raw_normalized'], argument), pending)
        self.assertEqual(result['nominal_data']['cases'][0]['result_type'], arr(I, I))

    def test_nested_closed_arrow_field(self):
        typ = arr(arr(I, B), arr(B, I))
        value = lam(10, arr(I, B), lam(11, B, lit()))
        tree = with_data(case(ctor('Pack', value), binders=(None,), body=lit()), data_decl(fields=(typ,)))
        result = m.derive_shared_fragment(tree)
        self.assertEqual(result['nominal_data']['declarations'][0]['field_types'], [typ])

    def test_case_pattern_binding_scope_and_wildcard_position(self):
        declaration = data_decl(fields=(I, B))
        tree = with_data(case(ctor('Pack', lit(), boolean()), binders=(None, 20), body=var(20), result=B), declaration)
        result = m.derive_shared_fragment(tree)
        self.assertEqual(result['nominal_data']['cases'][0]['fields'],
                         [{'index': 0, 'binding': None, 'type': I}, {'index': 1, 'binding': name(20), 'type': B}])
        self.assertEqual(m._free_terms(tree), set())
        self.reject(with_data(let(10, case(ctor('Pack', lit())), var(20))))

    def test_case_body_outer_first_normalization_and_exact_paths(self):
        redex = tapp(tabs(100, tapp(tabs(101, lam(10, tv(101), var(10))), inst(tv(100)))), inst(I))
        tree = with_data(case(ctor('Pack', lit()), body=app(redex, var(20))))
        result = m.derive_shared_fragment(tree)
        root = ['body', 'alternatives', '0', 'body', 'function']
        self.assertEqual([s['input']['path'] for s in result['steps']], [root, root])
        self.assertEqual(result['steps'][0]['arguments'], [I])
        self.assertEqual(result['steps'][1]['arguments'], [I])
        self.assertEqual(p.erase_total(tree), p.erase_total(result['raw_normalized']))
        self.assertTrue(all(type(x) is str for r in result['term_correspondence'] for x in r['erased_path']))

    def test_full_two_coordinate_use_inside_case(self):
        rhs = tabs(100, tabs(101, lam(2, tv(100), var(2))))
        body = case(ctor('Pack', lit()), body=add(app(use(1, I, B), var(20)), app(use(1, I, I), lit(0))))
        result = m.derive_shared_fragment(with_data(let(1, rhs, body)))
        self.assertEqual([u['arguments'] for u in result['polymorphism']['uses']], [[I, B], [I, I]])
        self.assertEqual(len(result['polymorphism']['definitions']), 1)

    def test_unreferenced_unsupported_declaration_is_preserved_not_admitted(self):
        unused = data_decl('Unused', 'U', (nominal_type('Unused'),))
        unused['parameters'] = [{'name': 'a', 'kind': {'tag': 'star'}}]
        tree = with_data(case(ctor('Pack', lit())), unused, data_decl())
        result = m.derive_shared_fragment(tree)
        self.assertEqual(result['raw_normalized']['declarations'], tree['declarations'])
        self.assertEqual([d['index'] for d in result['nominal_data']['declarations']], [1])

    def test_parameterized_or_missing_constructor_rejected(self):
        for alteration in ('parameter', 'none'):
            with self.subTest(alteration=alteration):
                declaration = data_decl()
                if alteration == 'parameter':
                    declaration['parameters'] = [{'name': 'a', 'kind': {'tag': 'star'}}]
                else:
                    declaration['constructors'] = []
                self.reject(with_data(lam(10, nominal_type(), lit()), declaration), 'NOMINAL')

    def test_open_recursive_nominal_and_higher_rank_fields_rejected(self):
        fields = [
            {'tag': 'parameter', 'name': 'a'},
            {'tag': 'applied', 'name': 'Box', 'arguments': []},
            {'tag': 'function', 'from': field_type(I), 'to': {'tag': 'applied', 'name': 'Box', 'arguments': []}},
            {'tag': 'quantified', 'name': 'a', 'kind': {'tag': 'star'}, 'body': field_type(I)},
            {'tag': 'application', 'function': field_type(I), 'argument': field_type(I)},
            {'tag': 'applied', 'name': 'Int', 'arguments': [field_type(I)]},
        ]
        for field in fields:
            with self.subTest(field=field):
                declaration = data_decl(); declaration['constructors'][0]['fields'] = [field]
                self.reject(with_data(lam(10, nominal_type(), lit()), declaration), 'NOMINAL')

    def test_duplicate_nominal_or_constructor_identity_rejected(self):
        for other in (data_decl('Box', 'Other'), data_decl('Other', 'Pack')):
            self.reject(with_data(lit(), data_decl(), other), 'DECLARATION')

    def test_constructor_bare_partial_extra_and_type_arguments_rejected(self):
        self.reject(with_data(ctor()), 'CONSTRUCTOR')
        self.reject(with_data(ctor('Pack', lit()), data_decl(fields=(I, B))), 'CONSTRUCTOR')
        self.reject(with_data(ctor('Pack', lit(), boolean())), 'TYPE')
        value = ctor(); value['arguments'] = [I]
        self.reject(with_data(value), 'NOMINAL')

    def test_constructor_wrong_field_and_unknown_identity_rejected(self):
        self.reject(with_data(ctor('Pack', boolean())), 'TYPE')
        self.reject(with_data(ctor('Counterfeit', lit())), 'FRAGMENT')

    def test_constructor_alias_is_not_reinterpreted_as_saturated(self):
        self.reject(with_data(let(10, ctor(), app(var(10), lit()))), 'CONSTRUCTOR')

    def test_case_owner_arity_result_and_coverage_rejected(self):
        base = with_data(case(ctor('Pack', lit())))
        mutations = []
        x = copy.deepcopy(base); x['body']['alternatives'][0]['pattern']['constructor'] = 'Other'; mutations.append(x)
        x = copy.deepcopy(base); x['body']['alternatives'][0]['pattern']['fields'] = []; mutations.append(x)
        x = copy.deepcopy(base); x['body']['alternatives'] = []; mutations.append(x)
        x = copy.deepcopy(base); x['body']['alternatives'] *= 2; mutations.append(x)
        x = copy.deepcopy(base); x['body']['alternatives'][0]['pattern'] = {'tag': 'default', 'binder': None}; mutations.append(x)
        for x in mutations:
            self.reject(x)
        x = copy.deepcopy(base); x['body']['result_type'] = B; self.reject(x, 'TYPE')
        self.reject(with_data(case(lit())), 'CASE')

    def test_nominal_type_arguments_and_nested_declaration_scope_rejected(self):
        typ = nominal_type(); typ['arguments'] = [I]
        self.reject(with_data(lam(10, typ, lit())), 'NOMINAL')
        self.reject(with_data(with_data(lit())), 'FRAGMENT')

    def test_generic_signature_and_hidden_generic_nominal_atoms_rejected(self):
        rhs = tabs(100, lam(10, nominal_type(), var(10)))
        self.reject(with_data(let(1, rhs, lit())), 'NOMINAL_SCOPE')
        rhs = tabs(100, lam(10, tv(100), let(11, ctor('Pack', lit()), var(10))))
        self.reject(with_data(let(1, rhs, app(use(1, I), lit()))), 'NOMINAL_SCOPE')
        rhs = tabs(100, lam(10, tv(100), let(11, lam(12, nominal_type(), var(12)), var(10))))
        self.reject(with_data(let(1, rhs, app(use(1, I), lit()))), 'NOMINAL_SCOPE')

    def test_nominal_scheme_instantiation_and_direct_vector_rejected(self):
        self.reject(with_data(shared(app(use(1, nominal_type()), ctor('Pack', lit())))), 'USE')
        self.reject(with_data(tapp(tabs(100, lam(10, tv(100), var(10))), inst(nominal_type()))), 'DIRECT')

    def test_zero_and_32_field_boundaries(self):
        zero = m.derive_shared_fragment(with_data(case(ctor(), binders=(), body=lit()), data_decl(fields=())))
        self.assertEqual(zero['nominal_data']['constructors'][0]['application_spine'], [])
        full = with_data(case(ctor('Pack', *[lit(i) for i in range(32)]), binders=(None,) * 32, body=lit()),
                         data_decl(fields=(I,) * 32))
        self.assertEqual(len(m.derive_shared_fragment(full)['nominal_data']['declarations'][0]['field_types']), 32)
        over = data_decl(fields=(I,) * 33)
        self.reject(with_data(lam(10, nominal_type(), lit()), over), 'LIMIT')

    def test_32_referenced_nominal_boundary(self):
        def tree(count):
            body = lit()
            declarations = [data_decl('D' + str(i), 'C' + str(i), ()) for i in range(count)]
            for i in reversed(range(count)):
                body = let(1000 + i, ctor('C' + str(i)), body)
            return with_data(body, *declarations)
        self.assertEqual(len(m.derive_shared_fragment(tree(32))['nominal_data']['declarations']), 32)
        self.reject(tree(33), 'LIMIT')

    def test_nominal_rows_are_recomputed_not_trusted(self):
        tree = with_data(case(ctor('Pack', lit())))
        result = m.derive_shared_fragment(tree)
        for section in ('declarations', 'constructors', 'cases'):
            bad = copy.deepcopy(result); bad['nominal_data'][section][0]['unexpected'] = True
            with self.assertRaisesRegex(m.SharedTransportError, 'EVIDENCE'):
                m.validate_shared_fragment(tree, bad)
        bad = copy.deepcopy(result); del bad['nominal_data']
        with self.assertRaisesRegex(m.SharedTransportError, 'EVIDENCE'):
            m.validate_shared_fragment(tree, bad)

    def test_nominal_metadata_and_work_limits_remain_fail_closed(self):
        tree = with_data(case(ctor('Pack', lit())))
        for name_, limit in [('MAX_METADATA_BYTES', 1), ('MAX_WORK', 1), ('MAX_ROWS', 1)]:
            with mock.patch.object(m, name_, limit):
                self.reject(tree, 'LIMIT')

    def test_list_paths_reject_noncanonical_indices(self):
        for key in ('00', '-1', '+0', '١', '1'):
            with self.assertRaises(m.SharedTransportError):
                m._get([lit()], (key,))

    def test_extracted_real_box_and_fnbox_producer_normalization(self):
        fixture = json.loads((BASE / 'tests/shared_nominal_raw_extract.json').read_text())
        self.assertEqual(fixture['format'], 'shared-nominal-raw-extract/1')
        def digest(value):
            return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        for row in fixture['cases']:
            with self.subTest(capture=row['name']):
                result = m.derive_shared_fragment(row['raw'])
                self.assertEqual(result['steps'], row['expected_steps'])
                self.assertEqual(result['checked_type'], row['expected_checked_type'])
                self.assertEqual(digest(result['raw_normalized']), row['expected_normalized_sha256'])
                self.assertEqual(digest(result['input_erased']), row['expected_erased_sha256'])
                self.assertEqual(len(result['nominal_data']['declarations']), 1)
                self.assertEqual(len(result['nominal_data']['constructors']), 1)
                self.assertEqual(len(result['nominal_data']['cases']), 1)
                self.assertEqual(result['raw_normalized']['declarations'], row['raw']['declarations'])
                if row['name'] == 'fnbox01':
                    self.assertEqual([u['arguments'] for u in result['polymorphism']['uses']], [[I], [B]])
                    argument = result['nominal_data']['constructors'][0]['arguments'][0]['path']
                    self.assertEqual(m._get(result['raw_normalized'], argument)['tag'], 'application')



# Synthetic SUM terms below exercise independent replay, never source/K/native
# acceptance. The optional full-capture test separately pins genuine input bytes.
def sum_decl(n='Choice', variants=(('Empty', ()), ('Number', (I,)))):
    return {'tag': 'data_kind', 'name': n, 'parameters': [],
            'constructors': [{'name': c, 'fields': [field_type(t) for t in fields]}
                             for c, fields in variants]}


def sum_arm(c, binders, body):
    return {'pattern': {'tag': 'constructor', 'constructor': c,
                        'fields': [None if n is None else name(n) for n in binders]}, 'body': body}


def sum_case(value, arms=None, result=I):
    return {'tag': 'case', 'scrutinee': value, 'result_type': result,
            'alternatives': arms if arms is not None else
            [sum_arm('Empty', (), lit()), sum_arm('Number', (20,), var(20))]}


def shared_sum(empty=False):
    arms = [sum_arm('Empty', (), choose(app(use(1, B), boolean()), app(use(1, I), lit()), lit(0))),
            sum_arm('Number', (20,), choose(app(use(1, B), boolean()),
                     app(use(1, I), add(var(20), var(10))), lit(0)))]
    return with_data(shared(let(10, add(lit(20), lit(1)),
        let(11, ctor('Empty') if empty else ctor('Number', var(10)), sum_case(var(11), arms)))), sum_decl())


class SumReplayTests(unittest.TestCase):
    def reject(self, tree, code=None):
        with self.assertRaises(m.SharedTransportError) as caught:
            m.derive_shared_fragment(tree)
        if code:
            self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def test_number_and_empty_exact_variant_spines(self):
        for empty in (False, True):
            tree = shared_sum(empty); before = copy.deepcopy(tree)
            result = m.derive_shared_fragment(tree); sums = result['nominal_sum']
            self.assertEqual(tree, before)
            self.assertEqual(result['raw_normalized'], tree)
            self.assertEqual(result['input_erased'], p.erase_total(tree))
            self.assertNotIn('nominal_data', result)
            self.assertEqual(sums['policy'], m.SUM_POLICY)
            declaration, = sums['declarations']
            self.assertEqual((declaration['index'], declaration['name']), (0, 'Choice'))
            self.assertEqual([v['constructor'] for v in declaration['variants']], ['Empty', 'Number'])
            self.assertEqual([v['field_types'] for v in declaration['variants']], [[], [I]])
            self.assertEqual([v['constructor_source']['path'] for v in declaration['variants']],
                             [['declarations', '0', 'constructors', str(i)] for i in (0, 1)])
            construction, = sums['constructors']
            self.assertEqual(construction['variant'], 0 if empty else 1)
            self.assertEqual(len(construction['arguments']), 0 if empty else 1)
            self.assertEqual(len(construction['application_spine']), 0 if empty else 1)
            case_row, = sums['cases']
            self.assertEqual([a['variant'] for a in case_row['arms']], [0, 1])
            self.assertEqual(case_row['arms'][1]['fields'], [{'index': 0, 'binding': name(20), 'type': I}])
            self.assertEqual([u['arguments'] for u in result['polymorphism']['uses']], [[B], [I], [B], [I]])
            self.assertEqual(len(result['polymorphism']['definitions']), 1)
            self.assertEqual(result['raw_normalized']['body']['body']['value']['tag'], 'application')
            self.assertEqual(len(result['term_correspondence']), len(m._ordinary(tree)))

    def test_source_arm_order_independent_from_declaration_variant_order(self):
        tree = with_data(sum_case(ctor('Number', lit())), sum_decl())
        tree['body']['alternatives'].reverse()
        result = m.derive_shared_fragment(tree)
        arms = result['nominal_sum']['cases'][0]['arms']
        self.assertEqual([a['index'] for a in arms], [0, 1])
        self.assertEqual([a['variant'] for a in arms], [1, 0])
        self.assertEqual([a['body']['path'] for a in arms],
                         [['body', 'alternatives', str(i), 'body'] for i in (0, 1)])
        self.assertEqual([v['index'] for v in result['nominal_sum']['declarations'][0]['variants']], [0, 1])

    def test_all_arms_receive_outer_first_proof_replay(self):
        def redex(a, b, term):
            return app(tapp(tabs(a, tapp(tabs(b, lam(term, tv(b), var(term))), inst(tv(a)))), inst(I)), lit())
        tree = with_data(sum_case(ctor('Empty'),
                         [sum_arm('Empty', (), redex(100, 101, 10)),
                          sum_arm('Number', (20,), redex(102, 103, 11))]), sum_decl())
        result = m.derive_shared_fragment(tree)
        paths = [x['input']['path'] for x in result['steps']]
        self.assertEqual(paths, [['body', 'alternatives', '0', 'body', 'function']] * 2 +
                                [['body', 'alternatives', '1', 'body', 'function']] * 2)
        self.assertEqual(p.erase_total(tree), p.erase_total(result['raw_normalized']))

    def test_unselected_bad_body_or_proof_is_rejected(self):
        good = with_data(sum_case(ctor('Empty')), sum_decl())
        bad = copy.deepcopy(good); bad['body']['alternatives'][1]['body'] = boolean()
        self.reject(bad, 'TYPE')
        bad = copy.deepcopy(good)
        bad['body']['alternatives'][1]['body'] = tapp(lit(), inst(I))
        self.reject(bad, 'PROOF')

    def test_complete_distinct_coverage_required(self):
        base = with_data(sum_case(ctor('Empty')), sum_decl())
        missing = copy.deepcopy(base); missing['body']['alternatives'].pop(); self.reject(missing, 'CASE')
        duplicate = copy.deepcopy(base); duplicate['body']['alternatives'][1] = copy.deepcopy(duplicate['body']['alternatives'][0])
        self.reject(duplicate, 'CASE')
        unknown = copy.deepcopy(base); unknown['body']['alternatives'][0]['pattern']['constructor'] = 'NotDeclared'
        self.reject(unknown, 'CASE')
        extra = copy.deepcopy(base); extra['body']['alternatives'].append(sum_arm('Empty', (), lit()))
        self.reject(extra, 'CASE')

    def test_equal_shapes_never_merge_nominal_or_variant_identity(self):
        left = sum_decl('A', (('A0', ()), ('A1', (I,))))
        right = sum_decl('B', (('B0', ()), ('B1', (I,))))
        body = sum_case(ctor('A1', lit()), [sum_arm('A0', (), lit()), sum_arm('B1', (20,), var(20))])
        self.reject(with_data(body, left, right), 'CASE')
        self.reject(with_data(app(lam(10, nominal_type('A'), lit()), ctor('B0')), left, right), 'TYPE')
        same_fields = sum_decl('S', (('First', (I,)), ('Second', (I,))))
        result = m.derive_shared_fragment(with_data(sum_case(ctor('Second', lit()),
            [sum_arm('First', (20,), var(20)), sum_arm('Second', (21,), var(21))]), same_fields))
        self.assertEqual(result['nominal_sum']['constructors'][0]['variant'], 1)
        self.assertEqual([a['variant'] for a in result['nominal_sum']['cases'][0]['arms']], [0, 1])

    def test_scalar_bool_fields_and_wildcard_positions(self):
        d = sum_decl('Choice', (('Empty', ()), ('Number', (I, B))))
        result = m.derive_shared_fragment(with_data(sum_case(ctor('Number', lit(), boolean()),
            [sum_arm('Empty', (), lit()), sum_arm('Number', (20, None), var(20))]), d))
        self.assertEqual(result['nominal_sum']['cases'][0]['arms'][1]['fields'],
                         [{'index': 0, 'binding': name(20), 'type': I},
                          {'index': 1, 'binding': None, 'type': B}])
        self.assertEqual(m._free_terms(result['raw_normalized']), set())

    def test_catch_all_wrong_pattern_arity_and_escaped_binder_rejected(self):
        base = with_data(sum_case(ctor('Empty')), sum_decl())
        bad = copy.deepcopy(base); bad['body']['alternatives'][0]['pattern'] = {'tag': 'default', 'binder': None}
        self.reject(bad, 'CASE')
        bad = copy.deepcopy(base); bad['body']['alternatives'][1]['pattern']['fields'] = []
        bad['body']['alternatives'][1]['body'] = lit()  # isolate arity, not an escaped field use
        self.reject(bad, 'CASE')
        bad = copy.deepcopy(base); bad['body']['alternatives'][0]['body'] = var(20); self.reject(bad)
        bad = copy.deepcopy(base); bad['body'] = let(20, lit(), bad['body']); self.reject(bad, 'SCHEMA')
        d = sum_decl('Choice', (('Empty', ()), ('Number', (I, I))))
        self.reject(with_data(sum_case(ctor('Empty'), [sum_arm('Empty', (), lit()),
                       sum_arm('Number', (20, 20), var(20))]), d), 'SCHEMA')

    def test_only_int_case_result_not_bool_arrow_or_nominal(self):
        for result_type, body in ((B, boolean()), (arr(I, I), lam(10, I, var(10))),
                                  (nominal_type('Choice'), ctor('Empty'))):
            tree = with_data(sum_case(ctor('Empty'), [sum_arm('Empty', (), body),
                        sum_arm('Number', (20,), copy.deepcopy(body))], result_type), sum_decl())
            # Arrow body copies need globally fresh ordinary binder identities.
            if result_type['tag'] == 'arrow': tree['body']['alternatives'][1]['body'] = lam(11, I, var(11))
            self.reject(tree, 'CASE')

    def test_constructor_saturation_payload_type_and_type_arguments(self):
        for value, code in ((ctor('Number'), 'CONSTRUCTOR'),
                            (ctor('Number', boolean()), 'TYPE'),
                            (ctor('Number', lit(), lit()), 'TYPE'),
                            (ctor('Empty', lit()), 'TYPE')):
            self.reject(with_data(value, sum_decl()), code)
        value = ctor('Empty'); value['arguments'] = [I]
        self.reject(with_data(value, sum_decl()), 'NOMINAL')
        self.reject(with_data(let(10, ctor('Number'), app(var(10), lit())), sum_decl()), 'CONSTRUCTOR')

    def test_callable_cross_nominal_and_open_fields_rejected_even_unselected(self):
        fields = [field_type(arr(I, I)), field_type(nominal_type('Other')), {'tag': 'parameter', 'name': 'a'},
                  {'tag': 'applied', 'name': 'Int', 'arguments': [field_type(I)]}]
        for field in fields:
            with self.subTest(field=field):
                d = sum_decl(); d['constructors'][1]['fields'] = [field]
                self.reject(with_data(ctor('Empty'), d), 'NOMINAL')
        d = sum_decl(); d['parameters'] = [{'name': 'a', 'kind': {'tag': 'star'}}]
        self.reject(with_data(ctor('Empty'), d), 'NOMINAL')

    def test_nominal_generic_bodies_and_instantiation_vectors_remain_excluded(self):
        rhs = tabs(100, lam(2, tv(100), let(10, ctor('Empty'), var(2))))
        self.reject(with_data(let(1, rhs, app(use(1, I), lit())), sum_decl()), 'NOMINAL_SCOPE')
        self.reject(with_data(shared(app(use(1, nominal_type('Choice')), ctor('Empty'))), sum_decl()), 'USE')
        self.reject(with_data(tapp(tabs(100, lam(10, tv(100), var(10))), inst(nominal_type('Choice'))), sum_decl()), 'DIRECT')

    def test_unreferenced_unsupported_context_and_mixed_data_sum(self):
        unused = data_decl('Unused', 'U', (nominal_type('Unused'),))
        unused['parameters'] = [{'name': 'a', 'kind': {'tag': 'star'}}]
        tree = with_data(let(10, ctor('Pack', lit()),
                    sum_case(ctor('Empty'), [sum_arm('Empty', (), case(var(10))), sum_arm('Number', (21,), var(21))])),
                         unused, sum_decl(), data_decl())
        result = m.derive_shared_fragment(tree)
        self.assertEqual(result['raw_normalized']['declarations'], tree['declarations'])
        self.assertEqual([d['index'] for d in result['nominal_sum']['declarations']], [1])
        self.assertEqual([d['index'] for d in result['nominal_data']['declarations']], [2])

    def test_64_variants_and_32_fields_are_bounded(self):
        d = sum_decl('S', tuple(('C'+str(i), ()) for i in range(64)))
        body = sum_case(ctor('C63'), [sum_arm('C'+str(i), (), lit(i)) for i in range(64)])
        result = m.derive_shared_fragment(with_data(body, d))
        self.assertEqual(len(result['nominal_sum']['declarations'][0]['variants']), 64)
        self.assertEqual(result['nominal_sum']['constructors'][0]['variant'], 63)
        d['constructors'].append({'name': 'C64', 'fields': []})
        self.reject(with_data(ctor('C0'), d), 'LIMIT')
        d = sum_decl('S', (('Empty', ()), ('Full', (I,) * 32)))
        body = sum_case(ctor('Full', *[lit(i) for i in range(32)]),
                        [sum_arm('Empty', (), lit()), sum_arm('Full', (None,) * 32, lit())])
        self.assertEqual(len(m.derive_shared_fragment(with_data(body, d))['nominal_sum']['constructors'][0]['arguments']), 32)
        d['constructors'][1]['fields'].append(field_type(I)); self.reject(with_data(ctor('Empty'), d), 'LIMIT')

    def test_combined_data_sum_nominal_limit_not_two_separate_quotas(self):
        def tree(count):
            declarations, body = [], lit()
            for i in range(count):
                declarations.append(data_decl('D'+str(i), 'C'+str(i), ()) if i%2 == 0 else
                                    sum_decl('D'+str(i), (('C'+str(i), ()), ('X'+str(i), ()))))
            for i in reversed(range(count)): body = let(1000+i, ctor('C'+str(i)), body)
            return with_data(body, *declarations)
        result = m.derive_shared_fragment(tree(32))
        self.assertEqual(len(result['nominal_data']['declarations']) + len(result['nominal_sum']['declarations']), 32)
        self.reject(tree(33), 'LIMIT')

    def test_sum_evidence_recomputed_including_paths_variant_and_coverage(self):
        raw = shared_sum(); result = m.derive_shared_fragment(raw)
        mutations = []
        bad = copy.deepcopy(result); bad['nominal_sum']['constructors'][0]['variant'] = 0; mutations.append(bad)
        bad = copy.deepcopy(result); bad['nominal_sum']['declarations'][0]['index'] = 1; mutations.append(bad)
        bad = copy.deepcopy(result); bad['nominal_sum']['declarations'][0]['variants'].reverse(); mutations.append(bad)
        bad = copy.deepcopy(result); bad['nominal_sum']['cases'][0]['arms'][0]['body']['path'][-2] = '1'; mutations.append(bad)
        bad = copy.deepcopy(result); bad['nominal_sum']['cases'][0]['arms'].pop(); mutations.append(bad)
        bad = copy.deepcopy(result); del bad['nominal_sum']; mutations.append(bad)
        for bad in mutations:
            with self.assertRaises(m.SharedTransportError) as caught: m.validate_shared_fragment(raw, bad)
            self.assertEqual(caught.exception.code, 'EVIDENCE')

    def test_full_two_coordinate_vectors_survive_across_all_arms(self):
        rhs = tabs(100, tabs(101, lam(2, tv(100), var(2))))
        arms = [sum_arm('Empty', (), app(use(1, I, B), lit())),
                sum_arm('Number', (20,), app(use(1, I, I), var(20)))]
        result = m.derive_shared_fragment(with_data(let(1, rhs, sum_case(ctor('Empty'), arms)), sum_decl()))
        uses = result['polymorphism']['uses']
        self.assertEqual([u['arguments'] for u in uses], [[I, B], [I, I]])
        self.assertEqual(uses[0]['instantiated_type'], uses[1]['instantiated_type'])
        self.assertEqual(len(result['polymorphism']['definitions'][0]['prefix']), 2)

    def test_duplicate_sum_declaration_or_variant_name_rejected(self):
        declaration = sum_decl()
        declaration['constructors'][1]['name'] = declaration['constructors'][0]['name']
        self.reject(with_data(ctor('Empty'), declaration), 'SCHEMA')  # raw declaration ingress checks first
        self.reject(with_data(ctor('Empty'), sum_decl(), sum_decl('Other')), 'DECLARATION')

    def test_sum_metadata_work_and_row_limits_fail_closed(self):
        for key in ('MAX_WORK', 'MAX_METADATA_BYTES', 'MAX_ROWS'):
            with mock.patch.object(m, key, 1): self.reject(shared_sum(), 'LIMIT')

    def test_all_old_data_evidence_bytes_unchanged(self):
        goldens = {'box02': '08081c90576987e6a4d7082a6c712415db418ce6b5e6f67d2384550a1b99f9ed',
                   'fnbox01': 'e3a77d8edc612234a81ece8a8fe5135319714c1b81cefb26b4002133133579bf'}
        fixture = json.loads((BASE/'tests/shared_nominal_raw_extract.json').read_bytes())
        for row in fixture['cases']:
            result = m.derive_shared_fragment(row['raw'])
            self.assertNotIn('nominal_sum', result)
            digest = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
            self.assertEqual(digest, goldens[row['name']])


SUM_CAPTURE_ROOT = os.environ.get('IR8_SUM_CAPTURE_ROOT')


@unittest.skipUnless(SUM_CAPTURE_ROOT, 'set IR8_SUM_CAPTURE_ROOT for completed original SUM captures')
class GenuineSumCaptureTests(unittest.TestCase):
    def test_both_completed_captures_full_custody_projection_normalization_and_resolver(self):
        from source_capture_v8 import verify_capture
        root = Path(SUM_CAPTURE_ROOT)
        pins = {
            'number': ('9acc00b4f3bd9142268522fd5f263cfac74ab117533578abc65010d17b45cd9e',
                       'cf3c414ac40d158bcaa150250e76c59dc1ef7517cbd12c49b723d3b0b00d0919', 1),
            'empty': ('5eb7eba9a32608a47066dc4774727a49b72d930948d9fe7e47e4df2702077998',
                      '7b3ae9a30a0e436eb01d91cd159d2a5e29fec6b2af633b350f144d1ce86f606d', 0),
        }
        bindings = []
        for label, (capture_sha, root_sha, variant) in pins.items():
            with self.subTest(capture=label):
                capture_path = root/('capture-'+label+'01')/'capture.stdout'
                verified = verify_capture(capture_path, fixture_root=root/'inputs'/label, entry='main.emlf',
                    expected_source_hashes={'main.emlf': root_sha,
                       'SharedPoly.emlf': '50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'},
                    expected_capture_sha256=capture_sha)
                self.assertTrue(verified['fragment_admitted'])
                self.assertFalse(verified['source_admitted']); self.assertFalse(verified['native_admitted'])
                capture = json.loads(capture_path.read_bytes())
                result = m.derive_shared_fragment(capture['projection']['projected_annotated'])
                self.assertEqual(result['steps'], capture['normalization']['steps'])
                self.assertEqual(result['raw_normalized'], capture['normalization']['raw_normalized'])
                self.assertEqual(len(result['steps']), 4)
                self.assertEqual([u['arguments'] for u in result['polymorphism']['uses']], [[B], [I], [B], [I]])
                definition, = result['polymorphism']['definitions']
                join, = verified['retained_prefix_binding_joins']
                self.assertEqual(join['binding'], definition['binding'])
                sums = result['nominal_sum']; declaration, = sums['declarations']
                self.assertEqual(sums['constructors'][0]['variant'], variant)
                self.assertEqual(len(result['raw_normalized']['declarations']), 7)
                entities = {row['allocated']: row['entity'] for row in capture['module_custody']['resolution']['entities']}
                self.assertEqual(entities[declaration['name']]['owner'], 'Main')
                self.assertEqual(entities[declaration['name']]['spelling'], 'Choice')
                self.assertEqual(entities[declaration['name']]['namespace'], 'types')
                self.assertEqual(entities[declaration['name']]['role'], {'tag': 'datatype'})
                self.assertEqual([entities[v['constructor']]['spelling'] for v in declaration['variants']], ['Empty', 'Number'])
                self.assertTrue(all(entities[v['constructor']]['owner'] == 'Main' for v in declaration['variants']))
                self.assertTrue(all(entities[v['constructor']]['namespace'] == 'terms' and
                                    entities[v['constructor']]['role'] == {'tag': 'constructor', 'datatype': 'Choice'}
                                    for v in declaration['variants']))
                field = sums['cases'][0]['arms'][1]['fields'][0]
                bindings.append(field['binding']['id'])
                # Actual retained payload let: follows the shared definition,
                # remains an ordinary application and is referenced by Number's
                # arm in both captures. No display-hint lookup is needed.
                shared_let = m._get(result['raw_normalized'], definition['binding_source']['path'])
                payload_let = shared_let['body']
                self.assertEqual(payload_let['tag'], 'let')
                self.assertEqual(payload_let['value']['tag'], 'application')
                number_arm = m._get(result['raw_normalized'], sums['cases'][0]['arms'][1]['body']['path'])
                self.assertIn(payload_let['name']['id'], m._free_terms(number_arm))
        self.assertNotEqual(bindings[0], bindings[1])  # observed IDs, never hardcoded to either capture


# Synthetic self-family fixtures: finite terms, not recursive term bindings.
def recursive_decl(n='Chain', empty='Nil', full='Cons'):
    return sum_decl(n, ((empty, ()), (full, (I, nominal_type(n)))))


def recursive_sum(lazy=False):
    tail = (app(lam(30, I, ctor('Cons', var(30), ctor('Nil'))), add(lit(100), lit(23)))
            if lazy else ctor('Cons', var(10), ctor('Nil')))
    branch = (var(20) if lazy else sum_case(var(21),
        [sum_arm('Nil', (), var(20)), sum_arm('Cons', (22, None), add(var(20), var(22)))]))
    answer = sum_case(var(12), [sum_arm('Nil', (), lit(0)),
                               sum_arm('Cons', (20, None if lazy else 21), branch)])
    return with_data(shared(let(10, add(lit(20), lit(22 if lazy else 1)),
        let(11, tail, let(12, ctor('Cons', var(10), var(11)),
            choose(app(use(1, B), boolean()), app(use(1, I), answer), lit(0)))))), recursive_decl())


class SelfRecursiveSumReplayTests(unittest.TestCase):
    reject = SumReplayTests.reject

    def test_finite_two_link_graph_and_nested_cases(self):
        tree = recursive_sum(); result = m.derive_shared_fragment(tree)
        sums = result['nominal_sum']; declaration, = sums['declarations']
        self.assertEqual(sums['self_recursive'], {'policy': 'closed-self-atom/1', 'declarations': [0]})
        self.assertEqual(declaration['variants'][1]['field_types'], [I, declaration['type']])
        self.assertEqual(result['raw_normalized'], tree)
        self.assertEqual(result['input_erased'], p.erase_total(tree))
        self.assertEqual(len(sums['constructors']), 3)
        self.assertEqual([c['variant'] for c in sums['constructors']], [1, 0, 1])
        self.assertEqual(len(sums['cases']), 2)
        outer, inner = sums['cases']
        self.assertEqual(outer['arms'][1]['fields'][1]['type'], nominal_type('Chain'))
        self.assertEqual(outer['arms'][1]['fields'][1]['binding'], name(21))
        self.assertEqual(m._get(tree, inner['scrutinee']['path']), var(21))
        self.assertEqual(inner['arms'][1]['fields'][1]['binding'], None)
        self.assertEqual([u['arguments'] for u in result['polymorphism']['uses']], [[B], [I]])
        self.assertEqual(len(result['polymorphism']['definitions']), 1)
        self.assertEqual(len(result['term_correspondence']), len(m._ordinary(tree)))
        self.assertEqual(m.validate_shared_fragment(tree, result), result)
        heads = [m._get(tree, row['arguments'][0]['path'])
                 for row in sums['constructors'] if row['variant'] == 1]
        self.assertEqual(heads, [var(10), var(10)])

    def test_pending_nominal_result_application_not_reduced_or_generalized(self):
        tree = recursive_sum(True); result = m.derive_shared_fragment(tree)
        tail = tree['body']['body']['body']['value']
        self.assertEqual(tail['tag'], 'application')
        self.assertEqual(tail['function']['parameter_type'], I)
        self.assertEqual(result['raw_normalized'], tree)
        self.assertEqual(len(result['polymorphism']['definitions']), 1)
        self.assertEqual(result['nominal_sum']['cases'][0]['arms'][1]['fields'][1],
                         {'index': 1, 'binding': None, 'type': nominal_type('Chain')})
        rows = result['term_correspondence']
        self.assertTrue(any(r['tag'] == 'lambda' and
                            r['normalized']['path'] == ['body','body','body','value','function'] for r in rows))
        self.assertTrue(any(r['tag'] == 'application' and
                            r['normalized']['path'] == ['body','body','body','value'] for r in rows))

    def test_selected_nullary_still_validates_and_records_self_field(self):
        result = m.derive_shared_fragment(with_data(ctor('Nil'), recursive_decl()))
        self.assertEqual(result['nominal_sum']['self_recursive']['declarations'], [0])
        self.assertEqual(result['nominal_sum']['constructors'][0]['arguments'], [])
        self.assertEqual(result['nominal_sum']['declarations'][0]['variants'][1]['field_types'][1],
                         nominal_type('Chain'))

    def test_marker_only_for_referenced_self_rows_in_original_order(self):
        ds = [recursive_decl('A','A0','A1'), sum_decl(), recursive_decl('B','B0','B1'),
              recursive_decl('Unused','U0','U1'), data_decl()]
        tree = with_data(let(10, ctor('B0'), let(11, ctor('Empty'),
                    let(12, ctor('A0'), let(13, ctor('Pack', lit()), lit())))), *ds)
        result = m.derive_shared_fragment(tree)
        self.assertEqual(result['nominal_sum']['self_recursive']['declarations'], [0, 2])
        self.assertEqual([r['index'] for r in result['nominal_sum']['declarations']], [0, 1, 2])
        self.assertEqual(result['nominal_data']['declarations'][0]['index'], 4)
        self.assertNotIn('self_recursive', result['nominal_data'])
        self.assertEqual(result['raw_normalized']['declarations'], ds)
        unreferenced = m.derive_shared_fragment(with_data(ctor('Empty'), recursive_decl(), sum_decl()))
        self.assertNotIn('self_recursive', unreferenced['nominal_sum'])

    def test_scalar_sum_complete_golden_bytes_unchanged(self):
        # Computed by read-only host replay of the frozen Stage10 implementation.
        goldens = {False: 'cfdddd7943efb24e9139c0ea700bc0afc471c37279a654cf09a8a848c58c2e46',
                   True: '8e007e7d60e21d0cf31fa75a8d59e426cc9a98e0a6a97bae562064945b58b670'}
        for empty, expected in goldens.items():
            result = m.derive_shared_fragment(shared_sum(empty))
            self.assertNotIn('self_recursive', result['nominal_sum'])
            digest = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':'),
                                               ensure_ascii=False).encode()).hexdigest()
            self.assertEqual(digest, expected)

    def test_equal_shape_foreign_tail_and_nominal_aliases_rejected(self):
        ds = [recursive_decl(), recursive_decl('Other','O0','O1')]
        self.reject(with_data(ctor('Cons', lit(), ctor('O0')), *ds), 'TYPE')
        self.reject(with_data(app(lam(10, nominal_type('Chain'), lit()), ctor('O0')), *ds), 'TYPE')
        # A display hint cannot turn the wrong family into the self atom.
        d = recursive_decl(); d['constructors'][1]['fields'][1]['name'] = 'Other'
        self.reject(with_data(ctor('Nil'), d, ds[1]), 'NOMINAL')

    def test_cross_family_and_mutual_fields_rejected_even_with_base_constructor(self):
        for field_name in ('Other', 'Missing'):
            a = recursive_decl(); a['constructors'][1]['fields'][1]['name'] = field_name
            b = recursive_decl('Other','O0','O1'); b['constructors'][1]['fields'][1]['name'] = 'Chain'
            self.reject(with_data(ctor('Nil'), a, b), 'NOMINAL')

    def test_open_applied_arrow_and_parameterized_self_fields_rejected(self):
        fields = [
            {'tag':'applied','name':'Chain','arguments':[field_type(I)]},
            {'tag':'parameter','name':'a'},
            field_type(arr(I, nominal_type('Chain'))),
            field_type(arr(nominal_type('Chain'), I)),
            {'tag':'applied','name':'Int','arguments':[field_type(nominal_type('Chain'))]},
        ]
        for field in fields:
            d = recursive_decl(); d['constructors'][1]['fields'][1] = field
            self.reject(with_data(ctor('Nil'), d), 'NOMINAL')
        d = recursive_decl(); d['parameters'] = [{'name':'a','kind':{'tag':'star'}}]
        self.reject(with_data(ctor('Nil'), d), 'NOMINAL')
        c = ctor('Nil'); c['arguments'] = [I]
        self.reject(with_data(c, recursive_decl()), 'NOMINAL')

    def test_recursive_single_constructor_data_is_not_admitted(self):
        self.reject(with_data(lam(10, nominal_type('Cell'), lit()),
                             data_decl('Cell', 'Cell', (I, nominal_type('Cell')))), 'NOMINAL')

    def test_finite_type_atom_does_not_authorize_letrec_or_forward_self_use(self):
        d = recursive_decl()
        self.reject(with_data({'tag':'letrec', 'bindings':[{'name':name(10),
            'type':nominal_type('Chain'), 'value':ctor('Cons',lit(),var(10))}], 'body':lit()}, d), 'FRAGMENT')
        self.reject(with_data(let(10, ctor('Cons',lit(),var(10)),lit()),d), 'SCHEMA')

    def test_generic_nominal_result_or_argument_and_nominal_use_still_rejected(self):
        d = recursive_decl()
        rhs = tabs(100, lam(2, tv(100), ctor('Nil')))
        self.reject(with_data(let(1,rhs,app(use(1,I),lit())),d), 'NOMINAL_SCOPE')
        rhs = tabs(100, lam(2, nominal_type('Chain'), lam(3, tv(100), var(3))))
        self.reject(with_data(let(1,rhs,app(app(use(1,I),ctor('Nil')),lit())),d), 'NOMINAL_SCOPE')
        self.reject(with_data(shared(app(use(1,nominal_type('Chain')),ctor('Nil'))),d), 'USE')
        self.reject(with_data(tapp(tabs(100,lam(2,tv(100),var(2))),inst(nominal_type('Chain'))),d), 'DIRECT')

    def test_constructor_saturation_and_exact_tail_type(self):
        for value,code in [(ctor('Cons'), 'CONSTRUCTOR'), (ctor('Cons',lit()),'CONSTRUCTOR'),
                           (ctor('Cons',lit(),lit()),'TYPE'), (ctor('Cons',boolean(),ctor('Nil')),'TYPE')]:
            self.reject(with_data(value,recursive_decl()),code)

    def test_nested_cases_require_all_arm_coverage_and_scopes(self):
        tree = recursive_sum(); outer = next(n for _,n in m._walk(tree) if n['tag']=='case')
        inner = outer['alternatives'][1]['body']
        for target in ('outer','inner'):
            for mutation in ('missing','duplicate','foreign','escaped'):
                bad = copy.deepcopy(tree); cases = [n for _,n in m._walk(bad) if n['tag']=='case']
                node = cases[0 if target=='outer' else 1]
                if mutation=='missing': node['alternatives'].pop()
                elif mutation=='duplicate': node['alternatives'][1] = copy.deepcopy(node['alternatives'][0])
                elif mutation=='foreign': node['alternatives'][0]['pattern']['constructor'] = 'OtherNil'
                else: node['alternatives'][0]['body'] = var(21 if target=='outer' else 22)
                self.reject(bad)
        # Bound tail cannot be silently treated as an Int by the nested arm.
        bad = copy.deepcopy(tree); cases = [n for _,n in m._walk(bad) if n['tag']=='case']
        cases[1]['alternatives'][0]['body'] = var(21); self.reject(bad,'TYPE')
        self.assertEqual(inner['result_type'], I)

    def test_unselected_nested_body_and_proof_not_skipped(self):
        inner = sum_case(ctor('Nil'), [sum_arm('Nil',(),lit()),
                    sum_arm('Cons',(20,None),tapp(lit(),inst(I)))])
        outer = sum_case(ctor('Nil'), [sum_arm('Nil',(),lit()), sum_arm('Cons',(21,22),inner)])
        self.reject(with_data(outer,recursive_decl()), 'PROOF')
        outer['alternatives'][1]['body']['alternatives'][1]['body'] = boolean()
        self.reject(with_data(outer,recursive_decl()), 'TYPE')

    def test_self_fields_are_atoms_not_expanded_at_each_occurrence(self):
        d = sum_decl('Tree', (('Leaf', (I,)), ('Fork', (nominal_type('Tree'), nominal_type('Tree')))))
        tree = with_data(let(10,ctor('Leaf',lit()),ctor('Fork',var(10),var(10))),d)
        result = m.derive_shared_fragment(tree); row, = result['nominal_sum']['declarations']
        self.assertEqual(row['variants'][1]['field_types'], [row['type'],row['type']])
        self.assertEqual(len(result['nominal_sum']['declarations']), 1)
        fork = next(c for c in result['nominal_sum']['constructors'] if c['variant']==1)
        self.assertEqual([m._get(tree,a['path']) for a in fork['arguments']], [var(10),var(10)])

    def test_marker_and_self_type_recomputed_not_claimed(self):
        raw=recursive_sum(); result=m.derive_shared_fragment(raw)
        changes=[lambda x:x['nominal_sum'].pop('self_recursive'),
                 lambda x:x['nominal_sum']['self_recursive'].update(policy='anything'),
                 lambda x:x['nominal_sum']['self_recursive'].update(declarations=[]),
                 lambda x:x['nominal_sum']['self_recursive'].update(declarations=[True]),
                 lambda x:x['nominal_sum']['self_recursive'].update(declarations=[0,0]),
                 lambda x:x['nominal_sum']['declarations'][0]['variants'][1]['field_types'][1].update(name='Other')]
        for mutate in changes:
            claimed=copy.deepcopy(result);mutate(claimed)
            with self.assertRaisesRegex(m.SharedTransportError,'EVIDENCE'):
                m.validate_shared_fragment(raw,claimed)
        scalar=shared_sum();claimed=m.derive_shared_fragment(scalar)
        claimed['nominal_sum']['self_recursive']={'policy':m.SUM_SELF_POLICY,'declarations':[0]}
        with self.assertRaisesRegex(m.SharedTransportError,'EVIDENCE'):m.validate_shared_fragment(scalar,claimed)

    def test_existing_bounds_and_new_marker_are_charged(self):
        self_type=nominal_type('Chain')
        d=sum_decl('Chain', (('Nil',()),('Many',(self_type,)*32)))
        result=m.derive_shared_fragment(with_data(ctor('Nil'),d))
        self.assertEqual(len(result['nominal_sum']['declarations'][0]['variants'][1]['field_types']),32)
        d['constructors'][1]['fields'].append(field_type(self_type))
        self.reject(with_data(ctor('Nil'),d),'LIMIT')
        for key in ('MAX_WORK','MAX_ROWS','MAX_METADATA_BYTES'):
            with mock.patch.object(m,key,1):self.reject(recursive_sum(),'LIMIT')
        tree=ctor('Nil')
        for _ in range(101):tree=ctor('Cons',lit(),tree)
        self.reject(with_data(tree,recursive_decl()),'LIMIT')
        original=m._Budget.record; seen=[]
        def record(budget,row):
            if isinstance(row,dict) and row.get('policy')==m.SUM_SELF_POLICY:
                seen.append(copy.deepcopy(row))
            return original(budget,row)
        with mock.patch.object(m._Budget,'record',record):m.derive_shared_fragment(recursive_sum())
        self.assertEqual(seen,[{'policy':m.SUM_SELF_POLICY,'declarations':[0]}])


RECURSIVE_SUM_CAPTURE_ROOT = os.environ.get('IR8_RECURSIVE_SUM_CAPTURE_ROOT')


@unittest.skipUnless(RECURSIVE_SUM_CAPTURE_ROOT,
                    'set IR8_RECURSIVE_SUM_CAPTURE_ROOT for completed self-recursive source captures')
class GenuineSelfRecursiveSumCaptureTests(unittest.TestCase):
    def test_both_completed_captures_full_replay_and_original_nominal_owner(self):
        from source_capture_v8 import verify_capture
        root=Path(RECURSIVE_SUM_CAPTURE_ROOT)
        pins={
            'nested':('a50b94a241c03c93f05bf688d63c437ad295daef020bb1362047064d42a4356f',
                      '3b45474da38bf68024ca844c54a6ed74c145a787fd52def8416d8ac2d6a3da6f'),
            'lazy-tail':('e61b3fca2b4d1c10479c41a1c37720ec2de44081c25191f6112d829393f10865',
                         'b8554d9f385a1ed28d05e03161a466a7786efd39b36329943a042c8c420e5d1f'),
        }
        for label,(capture_sha,source_sha) in pins.items():
            with self.subTest(capture=label):
                path=root/('capture-'+label+'01')/'capture.stdout'
                report=verify_capture(path,fixture_root=root/'inputs'/label,entry='main.emlf',
                    expected_source_hashes={'main.emlf':source_sha,
                        'SharedPoly.emlf':'50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'},
                    expected_capture_sha256=capture_sha)
                self.assertTrue(report['fragment_admitted'])
                self.assertFalse(report['source_admitted']);self.assertFalse(report['native_admitted'])
                capture=json.loads(path.read_bytes())
                result=m.derive_shared_fragment(capture['projection']['projected_annotated'])
                self.assertEqual(result['steps'],capture['normalization']['steps'])
                self.assertEqual(result['raw_normalized'],capture['normalization']['raw_normalized'])
                self.assertEqual(result['checked_type'],I);self.assertEqual(len(result['steps']),2)
                self.assertEqual([u['arguments'] for u in result['polymorphism']['uses']],[[B],[I]])
                definition,=result['polymorphism']['definitions'];join,=report['retained_prefix_binding_joins']
                self.assertEqual(join['binding'],definition['binding'])
                self.assertEqual(join['resolver_allocation']['entity'],
                    {'namespace':'terms','owner':'SharedPoly','role':{'tag':'value'},'spelling':'sharedId'})
                sums=result['nominal_sum'];declaration,=sums['declarations']
                self.assertEqual(sums['self_recursive'],
                    {'policy':m.SUM_SELF_POLICY,'declarations':[declaration['index']]})
                self.assertEqual(declaration['variants'][1]['field_types'],[I,declaration['type']])
                entities={x['allocated']:x['entity'] for x in capture['module_custody']['resolution']['entities']}
                self.assertEqual(entities[declaration['name']],
                    {'namespace':'types','owner':'Main','role':{'tag':'datatype'},'spelling':'IntList'})
                for variant,spelling in zip(declaration['variants'],('Nil','Cons')):
                    self.assertEqual(entities[variant['constructor']],{'namespace':'terms','owner':'Main',
                        'role':{'tag':'constructor','datatype':'IntList'},'spelling':spelling})
                raw=result['raw_normalized'];self.assertEqual(len(raw['declarations']),7)
                definition_let=m._get(raw,definition['binding_source']['path'])
                payload=definition_let['body'];tail=payload['body'];outer=tail['body']
                self.assertTrue(all(n['tag']=='let' for n in (payload,tail,outer)))
                self.assertEqual(payload['value']['tag'],'application')
                self.assertEqual(outer['value']['argument'],{'tag':'var','name':tail['name']})
                self.assertEqual(outer['value']['function']['argument'],{'tag':'var','name':payload['name']})
                if label=='nested':
                    self.assertEqual(len(sums['cases']),2)
                    self.assertEqual(tail['value']['function']['argument'],{'tag':'var','name':payload['name']})
                    outer_case,inner_case=sums['cases']
                    binding=outer_case['arms'][1]['fields'][1]['binding']
                    self.assertEqual(m._get(raw,inner_case['scrutinee']['path']),{'tag':'var','name':binding})
                else:
                    self.assertEqual(len(sums['cases']),1)
                    pending=tail['value'];self.assertEqual(pending['tag'],'application')
                    self.assertEqual(pending['function']['tag'],'lambda')
                    self.assertEqual(pending['function']['parameter_type'],I)
                    self.assertEqual(sums['cases'][0]['arms'][1]['fields'][1]['binding'],None)
                    self.assertTrue(any(r['tag']=='lambda' and m._get(raw,r['normalized']['path'])==pending['function']
                                        for r in result['term_correspondence']))
                # Original rejection files are historical and remain untouched.
                old=json.loads((path.parent/'verification.json').read_bytes())
                self.assertFalse(old['fragment_admitted']);self.assertEqual(old['fragment_error']['code'],'NOMINAL')


if __name__ == '__main__':
    unittest.main()
