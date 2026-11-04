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
        self.reject(tree, 'RECURSION')

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
            'type':nominal_type('Chain'), 'value':ctor('Cons',lit(),var(10))}], 'body':lit()}, d), 'RECURSION')
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


# Scope/path helpers are tested independently of recursive-function admission.
def rec_binding(i, typ, value, body):
    return {'tag':'letrec','bindings':[{'name':name(i),'type':typ,'value':value}],'body':body}


class RecursiveTraversalTests(unittest.TestCase):
    def test_recursive_rhs_then_body_paths_are_canonical_strings(self):
        raw=rec_binding(10,arr(I,I),lam(11,I,app(var(10),var(11))),app(var(10),lit()))
        children=m._children(raw)
        self.assertEqual([path for path,_ in children],[('bindings','0','value'),('body',)])
        self.assertEqual([path for path,_ in m._walk(raw)][:4],
                         [(),('bindings','0','value'),('bindings','0','value','body'),
                          ('bindings','0','value','body','function')])
        self.assertEqual(m._get(raw,['bindings','0','value']),raw['bindings'][0]['value'])

    def test_recursive_binder_scopes_rhs_and_body_but_not_external_names(self):
        raw=rec_binding(10,arr(I,I),lam(11,I,add(app(var(10),var(11)),var(20))),var(10))
        self.assertEqual(m._free_terms(raw),{20})
        self.assertEqual(m._free_terms(raw['bindings'][0]['value']),{10,20})
        self.assertEqual(m._free_terms(let(10,var(10),var(10))),{10})

    def test_ordinary_recursion_paths_preserve_all_wrapper_nodes(self):
        typ=arr(I,I);wrapped=app(lam(12,typ,var(12)),lam(11,I,app(var(10),var(11))))
        raw=rec_binding(10,typ,tapp(wrapped,R),app(var(10),lit()))
        rows=m._ordinary(raw)
        self.assertEqual(rows[0],((),(),'letrec'))
        self.assertIn((('bindings','0','value','value'),('bindings','0','value'),'application'),rows)
        self.assertIn((('bindings','0','value','value','function'),
                       ('bindings','0','value','function'),'lambda'),rows)
        self.assertEqual(len(rows),len(m._ordinary(p.erase_total(raw))))

    def test_existing_type_substitution_covers_recursive_annotation_and_rhs_proof(self):
        typ=arr(tv(100),tv(100))
        proof=inst(tv(100));raw=rec_binding(10,typ,lam(11,tv(100),
            app(var(10),tapp(tabs(101,var(11)),proof))),app(var(10),var(20)))
        out=m.fragment.substitute_closed_term(raw,100,I)
        self.assertEqual(out['bindings'][0]['type'],arr(I,I))
        self.assertEqual(out['bindings'][0]['value']['parameter_type'],I)
        self.assertEqual(out['bindings'][0]['value']['body']['argument']['witness'],inst(I))
        self.assertEqual(out['body'],raw['body'])


def monomorphic_recursion(wrappers=1):
    """Synthetic finite input graph; never evaluated by these host tests."""
    typ=arr(nominal_type('Chain'),I)
    body=sum_case(var(31),[sum_arm('Nil',(),lit(0)),
        sum_arm('Cons',(32,33),add(var(32),app(var(30),var(33))))])
    rhs=lam(31,nominal_type('Chain'),body)
    for index in range(wrappers):
        rhs=app(lam(40+index,typ,var(40+index)),rhs)
    answer=app(var(30),ctor('Cons',var(50),ctor('Cons',var(50),ctor('Nil'))))
    continuation=let(50,add(lit(20),lit(1)),
        choose(app(use(1,B),boolean()),app(use(1,I),answer),lit(0)))
    return with_data(shared(rec_binding(30,typ,rhs,continuation)),recursive_decl())


class MonomorphicRecursionReplayTests(unittest.TestCase):
    reject = ReplayTests.reject

    def test_actual_function_introduction_and_wrappers_remain_full_graph(self):
        tree=monomorphic_recursion();out=m.derive_shared_fragment(tree)
        self.assertEqual(out['raw_normalized'],tree)
        self.assertEqual(out['input_erased'],p.erase_total(tree))
        self.assertEqual(out['recursion']['policy'],'closed-single-function-recursion/1')
        row,=out['recursion']['bindings'];self.assertEqual(row['binding'],name(30))
        self.assertEqual(row['source']['path'],['body','body'])
        self.assertEqual(row['binding_source']['path'],['body','body','bindings','0'])
        rhs=m._get(tree,row['rhs']['path']);fn=m._get(tree,row['function_source']['path'])
        self.assertEqual(rhs['tag'],'application');self.assertEqual(fn['tag'],'lambda')
        self.assertEqual(len(row['wrappers']),1);self.assertEqual(row['free_term_bindings'],[])
        self.assertEqual(len(row['self_uses']),1)
        self.assertEqual(m._get(tree,row['self_uses'][0]['path']),var(30))
        self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[B],[I]])
        self.assertEqual(len(out['polymorphism']['definitions']),1)
        self.assertEqual(len(out['term_correspondence']),len(m._ordinary(tree)))
        self.assertEqual(m.validate_shared_fragment(tree,out),out)

    def test_bare_lambda_and_eight_wrappers_admitted_nine_rejected(self):
        for count in (0,8):
            with self.subTest(count=count):
                tree=monomorphic_recursion(count);out=m.derive_shared_fragment(tree)
                self.assertEqual(out['raw_normalized'],tree)
                self.assertEqual(len(out['recursion']['bindings'][0]['wrappers']),count)
        self.reject(monomorphic_recursion(9),'LIMIT')

    def test_ids_and_hints_do_not_select_the_admission_rule(self):
        tree=monomorphic_recursion()
        for _,node in m._walk(tree):
            for key in ('name','parameter'):
                if type(node.get(key)) is dict and 'id' in node[key]:
                    node[key]={'id':node[key]['id']+10000,'hint':'unrelated'}
            if node['tag']=='letrec':
                for binding in node['bindings']:
                    binding['name']={'id':binding['name']['id']+10000,'hint':'unrelated'}
            if node['tag']=='case':
                for arm in node['alternatives']:
                    arm['pattern']['fields']=[None if b is None else
                        {'id':b['id']+10000,'hint':'unrelated'} for b in arm['pattern']['fields']]
        out=m.derive_shared_fragment(tree)
        self.assertEqual(out['recursion']['bindings'][0]['binding'],{'id':10030,'hint':'unrelated'})
        self.assertEqual(out['raw_normalized'],tree)

    def test_scalar_function_is_structural_not_hardcoded_nominal_family(self):
        raw=rec_binding(10,arr(I,I),lam(11,I,app(var(10),var(11))),app(var(10),lit()))
        out=m.derive_shared_fragment(raw)
        self.assertEqual(out['recursion']['bindings'][0]['type'],arr(I,I))
        self.assertNotIn('nominal_sum',out)
        # This is not a termination proof; the synthetic term is not evaluated.

    def test_alias_and_passthrough_applied_to_alias_rejected(self):
        typ=arr(I,I)
        for rhs in (var(10),app(lam(12,typ,var(12)),var(10))):
            with self.subTest(rhs=rhs):
                self.reject(rec_binding(10,typ,rhs,lit()),'RECURSION')

    def test_arbitrary_wrapper_containing_lambda_is_not_an_introduction_spine(self):
        typ=arr(I,I)
        rhs=app(lam(12,typ,lam(13,I,app(var(12),var(13)))),lam(11,I,var(11)))
        self.reject(rec_binding(10,typ,rhs,lit()),'RECURSION')
        rhs=app(lam(12,I,lam(13,I,var(13))),lit())
        self.reject(rec_binding(10,typ,rhs,lit()),'RECURSION')

    def test_eager_let_wrapper_rejected_even_when_it_contains_a_lambda(self):
        typ=arr(I,I);rhs=let(12,app(var(10),lit()),lam(11,I,var(11)))
        self.reject(rec_binding(10,typ,rhs,lit()),'RECURSION')

    def test_external_scalar_requires_explicit_capture_policy(self):
        raw=let(20,lit(),rec_binding(10,arr(I,I),lam(11,I,add(var(11),var(20))),lit()))
        row=m.derive_shared_fragment(raw)['recursion']['bindings'][0]
        self.assertEqual(row['free_term_bindings'],[20])
        self.assertEqual(row['captures']['policy'],'closed-scalar-shared-view-captures/1')
        self.assertEqual(row['captures']['scalars'][0]['binding'],name(20))

    def test_external_function_alias_cannot_be_a_wrapper(self):
        typ=arr(I,I)
        raw=let(20,lam(21,typ,var(21)),
            rec_binding(10,typ,app(var(20),lam(11,I,var(11))),lit()))
        self.reject(raw,'RECURSION')

    def test_one_retained_group_globally_including_independent_and_nested(self):
        typ=arr(I,I);second=rec_binding(20,typ,lam(21,I,var(21)),lit())
        first=rec_binding(10,typ,lam(11,I,var(11)),second)
        self.reject(first,'RECURSION')
        nested=rec_binding(10,typ,lam(11,I,second),lit())
        self.reject(nested,'RECURSION')

    def test_mutual_scalar_value_and_polymorphic_knots_rejected(self):
        typ=arr(I,I);raw=rec_binding(10,typ,lam(11,I,app(var(20),var(11))),lit())
        raw['bindings'].append({'name':name(20),'type':typ,'value':lam(21,I,app(var(10),var(21)))})
        self.reject(raw,'RECURSION')
        self.reject(rec_binding(10,I,var(10),lit()),'RECURSION')
        self.reject(rec_binding(10,forall(100,arr(tv(100),tv(100))),tabs(100,lam(11,tv(100),var(11))),lit()),'RECURSION')

    def test_closed_recursion_under_generic_scope_still_rejected(self):
        raw=let(1,tabs(100,rec_binding(10,arr(I,I),lam(11,I,var(11)),
            lam(12,tv(100),var(12)))),app(use(1,I),lit()))
        self.reject(raw,'RECURSION')
        # Immediate closed type application does not authorize generic allocation.
        self.reject(tapp(tabs(100,rec_binding(10,arr(I,I),lam(11,I,var(11)),lit())),inst(I)),
                    'RECURSION')

    def test_open_annotation_is_not_closed_by_an_unrelated_context(self):
        raw=rec_binding(10,arr(tv(100),I),lam(11,tv(100),lit()),lit())
        self.reject(raw,'TYPE_SCOPE')

    def test_wrong_full_rhs_type_rejected_before_eligibility(self):
        self.reject(rec_binding(10,arr(I,I),lam(11,B,lit()),lit()),'TYPE')

    def test_rhs_proof_checked_then_normalized_without_ordinary_rewrite(self):
        tree=monomorphic_recursion();binding=tree['body']['body']['bindings'][0]
        binding['value']=tapp(binding['value'],then(R,R))
        out=m.derive_shared_fragment(tree)
        self.assertEqual(len(out['steps']),1)
        self.assertEqual(out['input_erased'],p.erase_total(out['raw_normalized']))
        self.assertEqual(m._get(out['raw_normalized'],out['recursion']['bindings'][0]['rhs']['path'])['tag'],
                         'application')
        binding['value']['witness']={'tag':'elim'}
        self.reject(tree,'PROOF')

    def test_nonselected_recursive_arm_type_and_proof_still_checked(self):
        for bad in (boolean(),tapp(lit(),{'tag':'elim'})):
            tree=monomorphic_recursion(0)
            tree['body']['body']['bindings'][0]['value']['body']['alternatives'][0]['body']=bad
            self.reject(tree,'TYPE' if bad['tag']=='bool' else 'PROOF')

    def test_recursion_evidence_is_recomputed_and_never_authority(self):
        tree=monomorphic_recursion();out=m.derive_shared_fragment(tree)
        for field in ('source','binding','rhs','function_source','wrappers','self_uses','free_term_bindings'):
            forged=copy.deepcopy(out);forged['recursion']['bindings'][0][field]=None
            with self.subTest(field=field),self.assertRaises(m.SharedTransportError) as caught:
                m.validate_shared_fragment(tree,forged)
            self.assertEqual(caught.exception.code,'EVIDENCE')
        forged=copy.deepcopy(out);del forged['recursion']
        with self.assertRaises(m.SharedTransportError) as caught:m.validate_shared_fragment(tree,forged)
        self.assertEqual(caught.exception.code,'EVIDENCE')

    def test_nonrecursive_old_outputs_do_not_gain_recursion_metadata(self):
        for tree in (shared(),shared_sum(),recursive_sum(),with_data(ctor('Pack',lit()),data_decl())):
            self.assertNotIn('recursion',m.derive_shared_fragment(tree))


MONOMORPHIC_RECURSION_CAPTURE_ROOT=os.environ.get('IR8_MONOMORPHIC_RECURSION_CAPTURE_ROOT')


@unittest.skipUnless(MONOMORPHIC_RECURSION_CAPTURE_ROOT,
                    'set IR8_MONOMORPHIC_RECURSION_CAPTURE_ROOT for completed recursive function capture')
class RetainedMonomorphicRecursionCaptureTests(unittest.TestCase):
    def test_original_custody_proofs_and_unchanged_wrapped_function(self):
        from source_capture_v8 import verify_capture
        root=Path(MONOMORPHIC_RECURSION_CAPTURE_ROOT).resolve()
        path=root/'capture-sum-list01'/'capture.stdout'
        old_path=path.parent/'verification.json';old_bytes=old_path.read_bytes()
        report=verify_capture(path,fixture_root=root/'inputs'/'sum-list',entry='main.emlf',
            expected_source_hashes={
                'main.emlf':'dc591096eb609920208a4d1875047e4e054393ecd11c660a90fceb6cebc39775',
                'SharedPoly.emlf':'50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'},
            expected_capture_sha256='b49db8a0433d827325af18f112098eba3bcda21aa06f147d085b97ce9be922e5')
        self.assertTrue(report['fragment_admitted'])
        self.assertFalse(report['source_admitted']);self.assertFalse(report['native_admitted'])
        capture=json.loads(path.read_bytes())
        out=m.derive_shared_fragment(capture['projection']['projected_annotated'])
        self.assertEqual(out['steps'],capture['normalization']['steps'])
        self.assertEqual(out['raw_normalized'],capture['normalization']['raw_normalized'])
        self.assertEqual(out['checked_type'],I);self.assertEqual(len(out['steps']),2)
        self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[B],[I]])
        row,=out['recursion']['bindings'];raw=out['raw_normalized']
        binding=m._get(raw,row['binding_source']['path']);rhs=m._get(raw,row['rhs']['path'])
        self.assertEqual(row['binding'],binding['name']);self.assertEqual(row['type'],binding['type'])
        self.assertEqual(rhs['tag'],'application');self.assertEqual(rhs['function']['tag'],'lambda')
        self.assertEqual(rhs['function']['body'],{'tag':'var','name':rhs['function']['parameter']})
        self.assertEqual(rhs['function']['parameter_type'],row['type'])
        actual=m._get(raw,row['function_source']['path'])
        self.assertEqual(actual,rhs['argument']);self.assertEqual(actual['tag'],'lambda')
        self.assertEqual(actual['body']['tag'],'let')
        self.assertEqual(actual['body']['value']['tag'],'application')
        self.assertEqual(actual['body']['value']['function']['tag'],'lambda')
        self.assertEqual(len(row['wrappers']),1);self.assertEqual(len(row['self_uses']),1)
        self.assertEqual(m._get(raw,row['self_uses'][0]['path']),{'tag':'var','name':binding['name']})
        self.assertEqual(row['free_term_bindings'],[])
        shared_def,=out['polymorphism']['definitions'];join,=report['retained_prefix_binding_joins']
        self.assertEqual(join['binding'],shared_def['binding'])
        self.assertNotEqual(binding['name']['id'],shared_def['binding']['id'])
        self.assertEqual(join['resolver_allocation']['entity'],
            {'namespace':'terms','owner':'SharedPoly','role':{'tag':'value'},'spelling':'sharedId'})
        self.assertEqual(len(raw['declarations']),7)
        decl,=out['nominal_sum']['declarations']
        self.assertEqual(row['type'],arr(decl['type'],I))
        self.assertEqual(decl['variants'][1]['field_types'],[I,decl['type']])
        self.assertEqual(len(out['nominal_sum']['cases']),1)
        # Both physical Cons sources retain the very same pending payload binder.
        continuation=m._get(raw,row['body']['path']);self.assertEqual(continuation['tag'],'let')
        heads=[m._get(raw,c['arguments'][0]['path']) for c in out['nominal_sum']['constructors'] if c['variant']==1]
        self.assertEqual(heads,[{'tag':'var','name':continuation['name']}]*2)
        self.assertEqual(old_path.read_bytes(),old_bytes)
        old=json.loads(old_bytes);self.assertFalse(old['fragment_admitted'])
        self.assertEqual(old['fragment_error']['code'],'FRAGMENT')


def captured_recursion():
    """Synthetic Stage14 shape, not original source or runtime evidence."""
    tree=monomorphic_recursion()
    rec=tree['body']['body']
    target=rec['bindings'][0]['value']['argument']
    target['body']['alternatives'][1]['body']=add(app(use(1,I),var(60)),app(var(30),var(33)))
    rec['body']=choose(app(use(1,B),boolean()),
        add(app(var(30),ctor('Nil')),app(var(30),ctor('Cons',lit(0),ctor('Cons',lit(0),ctor('Nil'))))),lit(0))
    tree['body']['body']=let(60,add(lit(20),lit(1)),rec)
    return tree


class RecursiveCaptureReplayTests(unittest.TestCase):
    reject = ReplayTests.reject

    def test_scalar_and_lexical_shared_view_are_distinct_capture_kinds(self):
        tree=captured_recursion();out=m.derive_shared_fragment(tree)
        self.assertEqual(out['raw_normalized'],tree)
        row,=out['recursion']['bindings'];caps=row['captures']
        self.assertEqual(row['free_term_bindings'],[1,60])
        self.assertEqual(caps['policy'],'closed-scalar-shared-view-captures/1')
        scalar,=caps['scalars'];view,=caps['views']
        self.assertEqual(scalar['binding'],name(60));self.assertEqual(scalar['type'],I)
        self.assertEqual([m._get(tree,a['path']) for a in scalar['occurrences']],[var(60)])
        self.assertEqual(view,{'definition':0,'binding':name(1),'arguments':[I],
                               'instantiated_type':arr(I,I),'uses':[0]})
        self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[I],[B]])
        self.assertEqual(len(out['term_correspondence']),len(m._ordinary(tree)))
        self.assertEqual(m.validate_shared_fragment(tree,out),out)

    def test_capture_evidence_never_claims_access_origin_readiness_or_E0(self):
        caps=m.derive_shared_fragment(captured_recursion())['recursion']['bindings'][0]['captures']
        self.assertEqual(set(caps),{'policy','scalars','views'})
        self.assertTrue(all(set(row)=={'binding','type','occurrences'} for row in caps['scalars']))
        self.assertTrue(all(set(row)=={'definition','binding','arguments','instantiated_type','uses'}
                            for row in caps['views']))

    def test_closed_scalar_parameter_not_only_local_constant_is_admitted(self):
        rhs=lam(11,I,choose(var(21),add(var(11),var(20)),app(var(10),var(11))))
        raw=lam(20,I,lam(21,B,rec_binding(10,arr(I,I),rhs,lit())))
        caps=m.derive_shared_fragment(raw)['recursion']['bindings'][0]['captures']
        self.assertEqual([(r['binding']['id'],r['type']) for r in caps['scalars']],[(20,I),(21,B)])
        self.assertEqual(caps['views'],[])

    def test_repeated_occurrences_share_one_scalar_and_one_full_pair(self):
        tree=captured_recursion();rec=tree['body']['body']['body']
        arm=rec['bindings'][0]['value']['argument']['body']['alternatives'][1]
        arm['body']=add(app(use(1,I),var(60)),add(app(use(1,I),var(60)),app(var(30),var(33))))
        caps=m.derive_shared_fragment(tree)['recursion']['bindings'][0]['captures']
        self.assertEqual(len(caps['scalars']),1);self.assertEqual(len(caps['scalars'][0]['occurrences']),2)
        self.assertEqual(len(caps['views']),1);self.assertEqual(caps['views'][0]['uses'],[0,1])

    def test_full_unused_type_coordinates_not_collapsed_by_equal_arrow_type(self):
        generic=tabs(100,tabs(101,lam(2,tv(100),var(2))))
        rhs=lam(11,I,add(app(use(1,I,B),var(20)),add(app(use(1,I,I),var(20)),app(var(10),var(11)))))
        raw=let(1,generic,let(20,lit(),rec_binding(10,arr(I,I),rhs,lit())))
        views=m.derive_shared_fragment(raw)['recursion']['bindings'][0]['captures']['views']
        self.assertEqual([v['arguments'] for v in views],[[I,B],[I,I]])
        self.assertEqual([v['instantiated_type'] for v in views],[arr(I,I),arr(I,I)])
        self.assertEqual([v['uses'] for v in views],[[0],[1]])

    def test_distinct_same_typed_definitions_remain_distinct(self):
        first=tabs(100,lam(2,tv(100),var(2)));second=tabs(101,lam(4,tv(101),var(4)))
        rhs=lam(11,I,add(app(use(1,I),var(11)),app(use(3,I),app(var(10),var(11)))))
        raw=let(1,first,let(3,second,rec_binding(10,arr(I,I),rhs,lit())))
        views=m.derive_shared_fragment(raw)['recursion']['bindings'][0]['captures']['views']
        self.assertEqual([(v['definition'],v['binding']['id'],v['arguments']) for v in views],
                         [(0,1,[I]),(1,3,[I])])

    def test_transitive_nested_carrier_and_unselected_arm_captures_count(self):
        tree=captured_recursion();rec=tree['body']['body']['body']
        arms=rec['bindings'][0]['value']['argument']['body']['alternatives']
        arms[0]['body']=app(lam(70,I,app(use(1,I),var(60))),lit())
        arms[1]['body']=app(var(30),var(33))
        out=m.derive_shared_fragment(tree);caps=out['recursion']['bindings'][0]['captures']
        self.assertEqual(caps['views'][0]['uses'],[0])
        self.assertEqual(len(caps['scalars'][0]['occurrences']),1)
        self.assertIn('alternatives',caps['scalars'][0]['occurrences'][0]['path'])
        self.assertEqual(out['raw_normalized'],tree)

    def test_local_binding_and_shared_definition_are_not_external_captures(self):
        local=let(1,tabs(100,lam(2,tv(100),var(2))),app(use(1,I),app(var(10),var(11))))
        raw=rec_binding(10,arr(I,I),lam(11,I,local),lit())
        row=m.derive_shared_fragment(raw)['recursion']['bindings'][0]
        self.assertEqual(row['free_term_bindings'],[]);self.assertNotIn('captures',row)

    def test_ordinary_closed_callable_and_view_alias_require_new_policy(self):
        rhs=lam(11,I,app(var(20),app(var(10),var(11))))
        for raw in (let(20,lam(21,I,var(21)),rec_binding(10,arr(I,I),rhs,lit())),
                    shared(let(20,use(1,I),rec_binding(10,arr(I,I),rhs,lit())))):
            caps=m.derive_shared_fragment(raw)['recursion']['bindings'][0]['captures']
            self.assertEqual(caps['policy'],'closed-scalar-callable-shared-view-captures/1')
            self.assertEqual(caps['callables'][0]['binding'],name(20));self.assertEqual(caps['views'],[])

    def test_nominal_owner_requires_explicit_declared_capture_policy(self):
        rhs=lam(11,I,sum_case(var(20),[sum_arm('Nil',(),lit()),sum_arm('Cons',(21,22),var(21))]))
        out=m.derive_shared_fragment(with_data(let(20,ctor('Nil'),rec_binding(10,arr(I,I),rhs,lit())),recursive_decl()))
        caps=out['recursion']['bindings'][0]['captures']
        self.assertEqual(caps['policy'],'closed-scalar-callable-nominal-shared-view-captures/1')
        self.assertEqual(caps['callables'],[]);self.assertEqual(caps['nominals'][0]['declaration'],0)

    def test_bare_partial_extra_and_open_shared_uses_remain_rejected(self):
        generic=tabs(100,tabs(101,lam(2,tv(100),var(2))))
        for value in (var(1),use(1,I),use(1,I,B,I)):
            raw=let(1,generic,rec_binding(10,arr(I,I),lam(11,I,let(20,value,lit())),lit()))
            self.reject(raw)
        raw=let(1,generic,rec_binding(10,arr(I,I),lam(11,I,app(use(1,I,tv(500)),lit())),lit()))
        self.reject(raw,'TYPE_SCOPE')

    def test_rejected_wrapper_remains_rejected_even_with_legal_capture(self):
        rhs=app(lam(12,I,lam(11,I,add(var(11),var(20)))),lit())
        self.reject(let(20,lit(),rec_binding(10,arr(I,I),rhs,lit())),'RECURSION')

    def test_complete_capture_metadata_and_paths_are_recomputed(self):
        tree=captured_recursion();out=m.derive_shared_fragment(tree)
        mutations=[lambda c:c.pop('policy'),lambda c:c.update(policy='capture-free'),
                   lambda c:c['scalars'].clear(),lambda c:c['views'].clear(),
                   lambda c:c['scalars'][0].update(type=B),
                   lambda c:c['scalars'][0].update(binding=name(999)),
                   lambda c:c['scalars'][0]['occurrences'].clear(),
                   lambda c:c['views'][0].update(arguments=[B]),
                   lambda c:c['views'][0].update(definition=1),
                   lambda c:c['views'][0].update(instantiated_type=arr(B,B)),
                   lambda c:c['views'][0].update(uses=[1])]
        for index,mutate in enumerate(mutations):
            forged=copy.deepcopy(out);mutate(forged['recursion']['bindings'][0]['captures'])
            with self.subTest(index=index),self.assertRaises(m.SharedTransportError) as caught:
                m.validate_shared_fragment(tree,forged)
            self.assertEqual(caught.exception.code,'EVIDENCE')
        forged=copy.deepcopy(out);forged['recursion']['bindings'][0]['free_term_bindings']=[60]
        with self.assertRaises(m.SharedTransportError) as caught:m.validate_shared_fragment(tree,forged)
        self.assertEqual(caught.exception.code,'EVIDENCE')

    def test_64_capture_boundary_counts_the_used_self_owner(self):
        def tree(count,self_use):
            terms=[var(1000+i) for i in range(count)]
            if self_use:terms.append(app(var(10),var(11)))
            while len(terms)>1:
                terms=[add(terms[i],terms[i+1]) if i+1<len(terms) else terms[i]
                       for i in range(0,len(terms),2)]
            raw=rec_binding(10,arr(I,I),lam(11,I,terms[0]),lit())
            for i in reversed(range(count)):raw=let(1000+i,lit(i),raw)
            return raw
        for count,self_use in ((63,True),(64,False)):
            with self.subTest(count=count,self_use=self_use):
                row=m.derive_shared_fragment(tree(count,self_use))['recursion']['bindings'][0]
                self.assertEqual(len(row['captures']['scalars']),count)
                self.assertEqual(bool(row['self_uses']),self_use)
        self.reject(tree(64,True),'LIMIT')

    def test_capture_budget_counts_full_pairs_not_only_raw_binder_ids(self):
        generic=tabs(100,tabs(101,lam(2,tv(100),var(2))))
        rhs=lam(11,I,add(app(use(1,I,B),var(20)),add(app(use(1,I,I),var(20)),app(var(10),var(11)))))
        raw=let(1,generic,let(20,lit(),rec_binding(10,arr(I,I),rhs,lit())))
        with mock.patch.object(m,'MAX_RECURSIVE_CAPTURES',4):
            row=m.derive_shared_fragment(raw)['recursion']['bindings'][0]
            self.assertEqual(row['free_term_bindings'],[1,20])
            self.assertEqual(len(row['captures']['views']),2)
        with mock.patch.object(m,'MAX_RECURSIVE_CAPTURES',3):self.reject(raw,'LIMIT')

    def test_existing_stage13_complete_replay_goldens_unchanged(self):
        hashes={0:'da32812f57716ed8199d802e635c5634d5449520dab21b543fccb56818a18f57',
                1:'63c908e0c7573a6a2f77554b5bbdd3e2f2f4971965fb4e87a411dcc81f66bf91',
                8:'5b38fe3ce4b83106627557f8ccd87fb65a518ff47799d023d1f4901ce66d5a0b'}
        for wrappers,expected in hashes.items():
            with self.subTest(wrappers=wrappers):
                out=m.derive_shared_fragment(monomorphic_recursion(wrappers))
                self.assertNotIn('captures',out['recursion']['bindings'][0])
                self.assertEqual(hashlib.sha256(m._json(out).encode()).hexdigest(),expected)


RECURSIVE_CAPTURE_ROOT=os.environ.get('IR8_RECURSIVE_CAPTURE_ROOT')


@unittest.skipUnless(RECURSIVE_CAPTURE_ROOT,'set IR8_RECURSIVE_CAPTURE_ROOT for completed captured-recursion source')
class RetainedRecursiveCaptureTests(unittest.TestCase):
    def test_genuine_custody_raw_proofs_and_exact_free_scalar_view_partition(self):
        from source_capture_v8 import verify_capture
        root=Path(RECURSIVE_CAPTURE_ROOT).resolve();path=root/'capture-captured-sum01'/'capture.stdout'
        old_path=path.parent/'verification.json';old_bytes=old_path.read_bytes()
        report=verify_capture(path,fixture_root=root/'inputs'/'captured-sum',entry='main.emlf',
            expected_source_hashes={
                'main.emlf':'628d6a3d5f6f4dae9b6f64a9fa0a9e8ccc5ccc6bf06d9b8188cd31c1e5d5029c',
                'SharedPoly.emlf':'50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'},
            expected_capture_sha256='fc0f27b7e2841aa98e3219defc3df75a159595093463949c2942cbdeac2e28fb')
        self.assertTrue(report['fragment_admitted'])
        self.assertFalse(report['source_admitted']);self.assertFalse(report['native_admitted'])
        capture=json.loads(path.read_bytes());out=m.derive_shared_fragment(capture['projection']['projected_annotated'])
        self.assertEqual(hashlib.sha256(m._json(out).encode()).hexdigest(),
                         'cdee763c1d7c33b2d44194a6865a388506b28576182866ed31587c3986249f7a')
        self.assertEqual(out['steps'],capture['normalization']['steps'])
        self.assertEqual(out['raw_normalized'],capture['normalization']['raw_normalized'])
        self.assertEqual(out['checked_type'],I);self.assertEqual(len(out['steps']),2)
        self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[I],[B]])
        definition,=out['polymorphism']['definitions'];join,=report['retained_prefix_binding_joins']
        self.assertEqual(definition['binding'],join['binding'])
        self.assertEqual(join['resolver_allocation']['entity'],
            {'namespace':'terms','owner':'SharedPoly','role':{'tag':'value'},'spelling':'sharedId'})
        row,=out['recursion']['bindings'];caps=row['captures'];scalar,=caps['scalars'];view,=caps['views']
        raw=out['raw_normalized'];shared_let=m._get(raw,definition['binding_source']['path'])
        bonus=shared_let['body'];self.assertEqual(bonus['tag'],'let')
        self.assertEqual(bonus['value']['tag'],'application')
        self.assertEqual(scalar['binding'],bonus['name']);self.assertEqual(scalar['type'],I)
        self.assertEqual(view['binding'],definition['binding']);self.assertEqual(view['definition'],definition['id'])
        self.assertEqual(view['arguments'],[I]);self.assertEqual(view['instantiated_type'],arr(I,I))
        self.assertEqual(view['uses'],[out['polymorphism']['uses'][0]['id']])
        self.assertEqual(row['free_term_bindings'],sorted([bonus['name']['id'],definition['binding']['id']]))
        rhs=m._get(raw,row['rhs']['path']);target=m._get(raw,row['function_source']['path'])
        self.assertEqual(rhs['tag'],'application');self.assertEqual(target,rhs['argument'])
        self.assertEqual(rhs['function']['body'],{'tag':'var','name':rhs['function']['parameter']})
        self.assertEqual(target['body']['tag'],'let');self.assertEqual(target['body']['value']['tag'],'application')
        case_row,=out['nominal_sum']['cases'];nil,cons=case_row['arms']
        self.assertEqual(m._get(raw,nil['body']['path']),lit(0))
        cons_path=cons['body']['path'];occ=scalar['occurrences'][0]['path']
        self.assertEqual(occ[:len(cons_path)],cons_path)
        self.assertEqual(m._get(raw,occ),{'tag':'var','name':bonus['name']})
        self.assertEqual(len(row['self_uses']),1)
        self.assertEqual(m._get(raw,row['self_uses'][0]['path']),{'tag':'var','name':row['binding']})
        # Static absence from Nil is not a claim about actual runtime demand.
        self.assertEqual(old_path.read_bytes(),old_bytes)
        old=json.loads(old_bytes);self.assertFalse(old['fragment_admitted'])
        self.assertEqual(old['fragment_error']['code'],'RECURSION')


def callable_capture(alias=False):
    """Synthetic pending/alias owners, with no original or native execution."""
    tree=captured_recursion();bonus=tree['body']['body'];rec=bonus['body']
    fn=rec['bindings'][0]['value']['argument']
    fn['body']['alternatives'][1]['body']=add(app(var(70),var(60) if alias else lit(0)),
                                            app(var(30),var(33)))
    value=(use(1,I) if alias else lam(72,I,app(use(1,I),add(var(72),var(60)))))
    bonus['body']=let(70,app(lam(71,arr(I,I),var(71)),value),rec)
    return tree


class RecursiveCallableCaptureReplayTests(unittest.TestCase):
    reject=ReplayTests.reject

    def test_pending_callable_retains_graph_and_transitive_shared_origin_proof(self):
        tree=callable_capture();out=m.derive_shared_fragment(tree)
        row,=out['recursion']['bindings'];caps=row['captures']
        self.assertEqual(caps['policy'],'closed-scalar-callable-shared-view-captures/1')
        self.assertEqual(caps['scalars'],[]);self.assertEqual(caps['views'],[])
        fn,=caps['callables'];self.assertEqual(fn['binding'],name(70));self.assertEqual(fn['type'],arr(I,I))
        self.assertEqual(row['free_term_bindings'],[70])
        self.assertEqual([m._get(tree,a['path']) for a in fn['occurrences']],[var(70)])
        self.assertEqual(out['raw_normalized'],tree)
        self.assertEqual(out['input_erased'],p.erase_total(tree))
        self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[I],[B]])
        self.assertEqual(len(out['term_correspondence']),len(m._ordinary(tree)))
        self.assertEqual(m.validate_shared_fragment(tree,out),out)

    def test_ordinary_alias_does_not_reconstruct_a_recursive_view_capture(self):
        tree=callable_capture(True);out=m.derive_shared_fragment(tree)
        row,=out['recursion']['bindings'];caps=row['captures']
        self.assertEqual(row['free_term_bindings'],[60,70])
        self.assertEqual(caps['scalars'][0]['binding'],name(60))
        self.assertEqual(caps['callables'][0]['binding'],name(70))
        self.assertEqual(caps['views'],[])
        self.assertEqual(out['raw_normalized']['body']['body']['body']['value']['argument'],use(1,I))
        self.assertEqual(len(out['polymorphism']['uses']),2)

    def test_no_origin_Code_Access_or_readiness_is_invented(self):
        caps=m.derive_shared_fragment(callable_capture())['recursion']['bindings'][0]['captures']
        self.assertEqual(set(caps),{'policy','scalars','views','callables'})
        self.assertEqual(set(caps['callables'][0]),{'binding','type','occurrences'})

    def test_recursively_closed_higher_order_scalar_arrow_preserved_exactly(self):
        typ=arr(arr(I,I),arr(B,I))
        value=lam(21,arr(I,I),lam(22,B,app(var(21),lit())))
        rhs=lam(11,I,app(app(var(20),lam(23,I,var(23))),boolean()))
        out=m.derive_shared_fragment(let(20,value,rec_binding(10,arr(I,I),rhs,lit())))
        self.assertEqual(out['recursion']['bindings'][0]['captures']['callables'][0]['type'],typ)

    def test_pending_curried_view_result_stays_an_ordinary_owner(self):
        generic=tabs(100,tabs(101,lam(2,tv(100),lam(3,tv(101),var(2)))))
        rhs=lam(11,I,app(var(20),boolean()))
        raw=let(1,generic,let(20,app(use(1,I,B),lit()),rec_binding(10,arr(I,I),rhs,
            choose(app(app(use(1,B,I),boolean()),lit()),app(var(10),lit()),lit(0)))))
        out=m.derive_shared_fragment(raw);caps=out['recursion']['bindings'][0]['captures']
        self.assertEqual(caps['callables'][0]['type'],arr(B,I));self.assertEqual(caps['views'],[])
        self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[I,B],[B,I]])
        self.assertEqual(out['raw_normalized'],raw)

    def test_same_arrow_and_same_hint_do_not_merge_distinct_binders(self):
        raw=let(20,lam(21,I,var(21)),let(30,lam(31,I,var(31)),
            rec_binding(10,arr(I,I),lam(11,I,add(app(var(20),var(11)),app(var(30),var(11)))),lit())))
        for _,node in m._walk(raw):
            if type(node.get('name')) is dict and node['name']['id'] in (20,30):node['name']['hint']='same'
        rows=m.derive_shared_fragment(raw)['recursion']['bindings'][0]['captures']['callables']
        self.assertEqual([r['binding'] for r in rows],[name(20,'same'),name(30,'same')])

    def test_repeated_and_nested_occurrences_keep_one_owner_with_complete_paths(self):
        tree=callable_capture();rec=tree['body']['body']['body']['body']
        arms=rec['bindings'][0]['value']['argument']['body']['alternatives']
        arms[0]['body']=app(lam(80,I,add(app(var(70),lit()),app(var(70),var(80)))),lit())
        out=m.derive_shared_fragment(tree);rows=out['recursion']['bindings'][0]['captures']['callables']
        self.assertEqual(len(rows),1);self.assertEqual(len(rows[0]['occurrences']),3)
        self.assertEqual([m._get(tree,p['path']) for p in rows[0]['occurrences']],[var(70)]*3)
        self.assertEqual(len({tuple(p['path']) for p in rows[0]['occurrences']}),3)

    def test_all_three_capture_categories_are_separate_and_counted(self):
        tree=callable_capture(True);rec=tree['body']['body']['body']['body']
        arm=rec['bindings'][0]['value']['argument']['body']['alternatives'][1]
        arm['body']=add(app(use(1,I),var(60)),add(app(var(70),var(60)),app(var(30),var(33))))
        out=m.derive_shared_fragment(tree);row=out['recursion']['bindings'][0];caps=row['captures']
        self.assertEqual(row['free_term_bindings'],[1,60,70])
        self.assertEqual(len(caps['scalars']),1);self.assertEqual(len(caps['callables']),1)
        self.assertEqual(len(caps['views']),1);self.assertEqual(len(row['self_uses']),1)
        with mock.patch.object(m,'MAX_RECURSIVE_CAPTURES',3):self.reject(tree,'LIMIT')

    def test_64_owner_boundary_with_and_without_used_self(self):
        def tree(count,self_use):
            terms=[app(var(1000+i),lit(0)) for i in range(count)]
            if self_use:terms.append(app(var(10),var(11)))
            while len(terms)>1:
                terms=[add(terms[i],terms[i+1]) if i+1<len(terms) else terms[i]
                       for i in range(0,len(terms),2)]
            raw=rec_binding(10,arr(I,I),lam(11,I,terms[0]),lit())
            for i in reversed(range(count)):raw=let(1000+i,var(20),raw)
            return let(20,lam(21,I,var(21)),raw)
        for count,self_use in ((63,True),(64,False)):
            with self.subTest(count=count,self_use=self_use):
                row=m.derive_shared_fragment(tree(count,self_use))['recursion']['bindings'][0]
                self.assertEqual(len(row['captures']['callables']),count)
                self.assertEqual(bool(row['self_uses']),self_use)
        self.reject(tree(64,True),'LIMIT')

    def test_closed_callable_predicate_exact_leaves_root_and_work_charging(self):
        budget=m._Budget();before=budget.work
        self.assertTrue(m._closed_scalar_callable(arr(arr(I,I),arr(B,I)),budget))
        self.assertEqual(budget.work-before,7)
        bad=[I,B,tv(100),forall(100,arr(tv(100),tv(100))),arr(I,tv(100)),
             arr(nominal_type('Chain'),I),arr(I,nominal_type('Cell')),
             arr(I,forall(100,arr(tv(100),tv(100)))),arr(I,{'tag':'bottom'}),
             {'tag':'arrow','from':I,'to':I,'invented':True}]
        for typ in bad:
            with self.subTest(typ=typ):self.assertFalse(m._closed_scalar_callable(typ,m._Budget()))
        with mock.patch.object(m,'MAX_WORK',2),self.assertRaises(m.SharedTransportError) as caught:
            m._closed_scalar_callable(arr(I,I),m._Budget())
        self.assertEqual(caught.exception.code,'LIMIT')

    def test_nominal_domain_or_result_callable_owners_are_rejected(self):
        domain=let(20,lam(21,nominal_type('Chain'),lit()),
            rec_binding(10,arr(I,I),lam(11,I,app(var(20),ctor('Nil'))),lit()))
        result=let(20,lam(21,I,ctor('Nil')),
            rec_binding(10,arr(I,I),lam(11,I,sum_case(app(var(20),var(11)),
                [sum_arm('Nil',(),lit()),sum_arm('Cons',(22,23),var(22))])),lit()))
        self.reject(with_data(domain,recursive_decl()),'RECURSION')
        self.reject(with_data(result,recursive_decl()),'RECURSION')

    def test_open_higher_rank_and_bare_scheme_are_not_ordinary_callables(self):
        raw=lam(20,arr(tv(500),I),rec_binding(10,arr(I,I),lam(11,I,lit()),lit()))
        self.reject(raw,'TYPE_SCOPE')
        raw=lam(20,arr(forall(500,arr(tv(500),tv(500))),I),
            rec_binding(10,arr(I,I),lam(11,I,lit()),lit()))
        self.reject(raw)
        raw=shared(rec_binding(10,arr(I,I),lam(11,I,let(20,var(1),lit())),lit()))
        self.reject(raw)

    def test_full_arrow_argument_mismatch_is_not_accepted_by_capture_shape(self):
        raw=let(20,lam(21,B,lit()),rec_binding(10,arr(I,I),lam(11,I,app(var(20),lit())),lit()))
        self.reject(raw,'TYPE')

    def test_out_of_scope_and_forged_capture_evidence_are_rejected(self):
        self.reject(rec_binding(10,arr(I,I),lam(11,I,app(var(20),lit())),lit()),'SCHEMA')
        tree=callable_capture();out=m.derive_shared_fragment(tree)
        mutations=[lambda c:c.pop('callables'),lambda c:c.update(policy=m.RECURSIVE_CAPTURE_POLICY),
            lambda c:c['callables'].clear(),lambda c:c['callables'][0].update(binding=name(999)),
            lambda c:c['callables'][0].update(type=arr(B,I)),lambda c:c['callables'][0]['occurrences'].clear(),
            lambda c:c['callables'][0]['occurrences'].append({'stage':'normalized','path':[]}),
            lambda c:c['callables'][0].update(origin='E0'),
            lambda c:c['callables'].append(copy.deepcopy(c['callables'][0]))]
        for index,mutate in enumerate(mutations):
            forged=copy.deepcopy(out);mutate(forged['recursion']['bindings'][0]['captures'])
            with self.subTest(index=index),self.assertRaises(m.SharedTransportError) as caught:
                m.validate_shared_fragment(tree,forged)
            self.assertEqual(caught.exception.code,'EVIDENCE')

    def test_previous_scalar_shared_only_evidence_is_byte_identical(self):
        out=m.derive_shared_fragment(captured_recursion())
        self.assertEqual(hashlib.sha256(m._json(out).encode()).hexdigest(),
                         'deaa5084cdcac0be57aedef29f451bf3e59f5c47fab336b7319c5e05ddb24cd4')
        caps=out['recursion']['bindings'][0]['captures']
        self.assertEqual(caps['policy'],m.RECURSIVE_CAPTURE_POLICY);self.assertNotIn('callables',caps)


RECURSIVE_CALLABLE_CAPTURE_ROOT=os.environ.get('IR8_RECURSIVE_CALLABLE_CAPTURE_ROOT')


@unittest.skipUnless(RECURSIVE_CALLABLE_CAPTURE_ROOT,
                    'set IR8_RECURSIVE_CALLABLE_CAPTURE_ROOT for completed ordinary callable captures')
class RetainedRecursiveCallableCaptureTests(unittest.TestCase):
    def test_both_genuine_captures_replay_without_predicting_callable_targets(self):
        from source_capture_v8 import verify_capture
        root=Path(RECURSIVE_CALLABLE_CAPTURE_ROOT).resolve()
        pins={
            'pending-step':('8d6452d60f503b6e685f4abd48ca8967489a25135ec75d0e681e719199e7a5df',
                            '3f8464fc2be27830957126ec052f71afadcfe031b4a0e16ec4febb877dbe8be0'),
            'view-alias':('feb1656e2b397be0fed3eba1f40ba95785eb1029a8aab6fdb5aa164fefa01668',
                          '00d66d88c00af704cdc01c85aebf38a14694ca2990cdd1423eda3ca80b230170')}
        for label,(capture_hash,source_hash) in pins.items():
            with self.subTest(label=label):
                path=root/('capture-'+label+'01')/'capture.stdout'
                old_path=path.parent/'verification.json';old_bytes=old_path.read_bytes()
                report=verify_capture(path,fixture_root=root/'inputs'/label,entry='main.emlf',
                    expected_source_hashes={'main.emlf':source_hash,
                        'SharedPoly.emlf':'50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'},
                    expected_capture_sha256=capture_hash)
                self.assertTrue(report['fragment_admitted']);self.assertFalse(report['source_admitted'])
                self.assertFalse(report['native_admitted'])
                capture=json.loads(path.read_bytes());out=m.derive_shared_fragment(capture['projection']['projected_annotated'])
                self.assertEqual(hashlib.sha256(m._json(out).encode()).hexdigest(),{
                    'pending-step':'7a45694ca2650bbf48b60c50ae3f94f83247968a8b0e43f4c1c0f66ba2821070',
                    'view-alias':'89b344f88a241ba26d8686d3e8ee142e837589a219142bb93786ab47f5b2747f'}[label])
                self.assertEqual(out['steps'],capture['normalization']['steps'])
                self.assertEqual(out['raw_normalized'],capture['normalization']['raw_normalized'])
                self.assertEqual(len(out['steps']),2);self.assertEqual(out['checked_type'],I)
                definition,=out['polymorphism']['definitions'];join,=report['retained_prefix_binding_joins']
                self.assertEqual(definition['binding'],join['binding'])
                self.assertEqual(join['resolver_allocation']['entity'],
                    {'namespace':'terms','owner':'SharedPoly','role':{'tag':'value'},'spelling':'sharedId'})
                self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[I],[B]])
                raw=out['raw_normalized'];shared_let=m._get(raw,definition['binding_source']['path'])
                bonus=shared_let['body'];step=bonus['body'];rec=step['body']
                self.assertEqual(bonus['tag'],'let');self.assertEqual(bonus['value']['tag'],'application')
                self.assertEqual(step['tag'],'let');self.assertEqual(step['value']['tag'],'application')
                self.assertEqual(rec['tag'],'letrec');row,=out['recursion']['bindings'];caps=row['captures']
                self.assertEqual(caps['policy'],m.RECURSIVE_CALLABLE_CAPTURE_POLICY)
                self.assertEqual(caps['views'],[]);ordinary,=caps['callables']
                self.assertEqual(ordinary['binding'],step['name']);self.assertEqual(ordinary['type'],arr(I,I))
                self.assertEqual([m._get(raw,a['path']) for a in ordinary['occurrences']],
                                 [{'tag':'var','name':step['name']}])
                self.assertEqual(row['binding'],rec['bindings'][0]['name'])
                self.assertEqual(step['value']['function']['body'],
                                 {'tag':'var','name':step['value']['function']['parameter']})
                self.assertEqual(step['value']['function']['parameter_type'],arr(I,I))
                int_use=out['polymorphism']['uses'][0]
                self.assertEqual(m._get(raw,int_use['variable']['path']),{'tag':'var','name':definition['binding']})
                if label=='pending-step':
                    self.assertEqual(caps['scalars'],[]);self.assertEqual(row['free_term_bindings'],[step['name']['id']])
                    self.assertEqual(step['value']['argument']['tag'],'lambda')
                    self.assertEqual(step['value']['argument']['body']['tag'],'let')
                    self.assertEqual(step['value']['argument']['body']['value']['tag'],'application')
                    self.assertEqual(m._free_terms(step['value']),{definition['binding']['id'],bonus['name']['id']})
                else:
                    scalar,=caps['scalars'];self.assertEqual(scalar['binding'],bonus['name'])
                    self.assertEqual(row['free_term_bindings'],sorted([step['name']['id'],bonus['name']['id']]))
                    self.assertEqual(step['value']['argument']['tag'],'type_application')
                    self.assertEqual(step['value']['argument'],m._get(raw,int_use['source']['path']))
                    self.assertEqual(m._free_terms(step['value']),{definition['binding']['id']})
                nil,cons=out['nominal_sum']['cases'][0]['arms']
                self.assertEqual(m._get(raw,nil['body']['path']),lit(0))
                for occurrence in ordinary['occurrences']:
                    self.assertEqual(occurrence['path'][:len(cons['body']['path'])],cons['body']['path'])
                # Static occurrence/graph facts do not predict eventual Code or runtime demand.
                self.assertEqual(old_path.read_bytes(),old_bytes)
                old=json.loads(old_bytes);self.assertFalse(old['fragment_admitted'])
                self.assertEqual(old['fragment_error']['code'],'RECURSION')


def nominal_capture(data_owner=True):
    """Synthetic pending nominal owner; original captures are tested separately."""
    tree=monomorphic_recursion();rec=tree['body']['body']
    if data_owner:
        typ=nominal_type('Payload')
        tree['declarations'].append(data_decl('Payload','Payload',(I,arr(I,I))))
        payload=ctor('Payload',add(lit(20),lit(1)),app(lam(72,arr(I,I),var(72)),use(1,I)))
        demand=case(var(70),'Payload',(80,81),app(var(81),var(80)))
    else:
        typ=nominal_type('Chain')
        tail=app(lam(72,I,ctor('Cons',var(72),ctor('Nil'))),lit(123))
        payload=ctor('Cons',add(lit(20),lit(1)),tail)
        demand=sum_case(var(70),[sum_arm('Nil',(),lit(0)),sum_arm('Cons',(80,None),app(use(1,I),var(80)))])
    rec['bindings'][0]['value']['argument']['body']['alternatives'][1]['body']=add(demand,app(var(30),var(33)))
    rec['body']=choose(app(use(1,B),boolean()),
        add(app(var(30),ctor('Nil')),app(var(30),ctor('Cons',lit(0),ctor('Cons',lit(0),ctor('Nil'))))),lit(0))
    tree['body']['body']=let(70,app(lam(71,typ,var(71)),payload),rec)
    return tree


class RecursiveNominalCaptureReplayTests(unittest.TestCase):
    reject=ReplayTests.reject

    def test_pending_DATA_and_SUM_owners_keep_whole_graph_and_exact_declarations(self):
        for data_owner in (True,False):
            with self.subTest(data_owner=data_owner):
                tree=nominal_capture(data_owner);out=m.derive_shared_fragment(tree)
                self.assertEqual(out['raw_normalized'],tree);self.assertEqual(out['input_erased'],p.erase_total(tree))
                self.assertEqual(len(out['term_correspondence']),len(m._ordinary(tree)))
                row,=out['recursion']['bindings'];caps=row['captures'];owner,=caps['nominals']
                self.assertEqual(caps['policy'],'closed-scalar-callable-nominal-shared-view-captures/1')
                self.assertEqual(caps['scalars'],[]);self.assertEqual(caps['callables'],[])
                self.assertEqual(owner['binding'],name(70))
                table=out['nominal_data' if data_owner else 'nominal_sum']
                declaration=next(d for d in table['declarations'] if d['index']==owner['declaration'])
                self.assertEqual(owner['type'],declaration['type'])
                self.assertEqual(owner['declaration'],1 if data_owner else 0)
                self.assertEqual([m._get(tree,a['path']) for a in owner['occurrences']],[var(70)])
                self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[I],[B]])
                self.assertEqual([v['arguments'] for v in caps['views']],[] if data_owner else [[I]])
                self.assertEqual(m.validate_shared_fragment(tree,out),out)

    def test_nominal_metadata_never_invents_node_variant_origin_or_readiness(self):
        caps=m.derive_shared_fragment(nominal_capture())['recursion']['bindings'][0]['captures']
        self.assertEqual(set(caps),{'policy','scalars','callables','nominals','views'})
        self.assertEqual(set(caps['nominals'][0]),{'binding','type','declaration','occurrences'})

    def test_same_shaped_families_remain_different_and_owners_sort_by_ID(self):
        body=add(case(var(30),'A',(22,),var(22)),case(var(20),'B',(23,),var(23)))
        raw=with_data(let(30,ctor('A',lit()),let(20,ctor('B',lit()),
            rec_binding(10,arr(I,I),lam(11,I,body),lit()))),
            data_decl('First','A'),data_decl('Second','B'))
        rows=m.derive_shared_fragment(raw)['recursion']['bindings'][0]['captures']['nominals']
        self.assertEqual([(r['binding']['id'],r['declaration'],r['type']) for r in rows],
                         [(20,1,nominal_type('Second')),(30,0,nominal_type('First'))])

    def test_same_type_different_owners_are_not_collapsed(self):
        body=add(case(var(20),'Pack',(22,),var(22)),case(var(30),'Pack',(23,),var(23)))
        raw=with_data(let(20,ctor('Pack',lit()),let(30,ctor('Pack',lit()),
            rec_binding(10,arr(I,I),lam(11,I,body),lit()))))
        rows=m.derive_shared_fragment(raw)['recursion']['bindings'][0]['captures']['nominals']
        self.assertEqual([r['binding']['id'] for r in rows],[20,30])
        self.assertEqual([r['declaration'] for r in rows],[0,0])

    def test_nested_and_unselected_occurrences_are_complete(self):
        tree=nominal_capture();rec=tree['body']['body']['body']
        arms=rec['bindings'][0]['value']['argument']['body']['alternatives']
        arms[0]['body']=app(lam(90,I,case(var(70),'Payload',(91,92),var(91))),lit())
        row=m.derive_shared_fragment(tree)['recursion']['bindings'][0]['captures']['nominals'][0]
        self.assertEqual(len(row['occurrences']),2)
        self.assertEqual([m._get(tree,a['path']) for a in row['occurrences']],[var(70),var(70)])
        self.assertEqual(len({tuple(a['path']) for a in row['occurrences']}),2)

    def test_all_capture_categories_are_disjoint_and_count_together(self):
        tree=nominal_capture(False);rec=tree['body']['body']['body']
        arm=rec['bindings'][0]['value']['argument']['body']['alternatives'][1]
        arm['body']=add(app(var(60),var(50)),arm['body'])
        tree['body']['body']['body']=let(50,lit(),let(60,lam(61,I,var(61)),rec))
        row=m.derive_shared_fragment(tree)['recursion']['bindings'][0];caps=row['captures']
        self.assertEqual(row['free_term_bindings'],[1,50,60,70])
        self.assertEqual([r['binding']['id'] for r in caps['scalars']],[50])
        self.assertEqual([r['binding']['id'] for r in caps['callables']],[60])
        self.assertEqual([r['binding']['id'] for r in caps['nominals']],[70])
        self.assertEqual([r['binding']['id'] for r in caps['views']],[1])
        with mock.patch.object(m,'MAX_RECURSIVE_CAPTURES',4):self.reject(tree,'LIMIT')

    def test_nominal_parameter_owner_is_allowed_without_constructor_origin_guess(self):
        raw=with_data(lam(20,nominal_type('Box'),rec_binding(10,arr(I,I),
            lam(11,I,case(var(20),'Pack',(21,),var(21))),lit())))
        out=m.derive_shared_fragment(raw);owner,=out['recursion']['bindings'][0]['captures']['nominals']
        self.assertEqual(owner['binding'],name(20));self.assertEqual(owner['declaration'],0)
        self.assertEqual(out['nominal_data']['constructors'],[])

    def test_missing_published_declaration_rejects_before_returning_evidence(self):
        original=m._nominal_inventory
        def omit_data(*args):
            data,sums=original(*args)
            return None,sums
        with mock.patch.object(m,'_nominal_inventory',side_effect=omit_data):
            self.reject(nominal_capture(),'RECURSION')

    def test_family_cannot_be_selected_silently_after_publication(self):
        original=m._nominal_inventory
        def remove_selected(*args):
            data,sums=original(*args)
            args[2].selected.pop(1)
            return data,sums
        with mock.patch.object(m,'_nominal_inventory',side_effect=remove_selected):
            self.reject(nominal_capture(),'RECURSION')

    def test_equal_copy_is_not_the_freshly_published_canonical_declaration(self):
        original=m._nominal_inventory
        def copy_row(*args):
            data,sums=original(*args)
            data=copy.deepcopy(data)
            return data,sums
        with mock.patch.object(m,'_nominal_inventory',side_effect=copy_row):
            self.reject(nominal_capture(),'RECURSION')

    def test_64_nominal_owners_including_used_self_boundary(self):
        def tree(count,self_use):
            terms=[case(var(1000+i),'Pack',(2000+i,),var(2000+i)) for i in range(count)]
            if self_use:terms.append(app(var(10),var(11)))
            while len(terms)>1:
                terms=[add(terms[i],terms[i+1]) if i+1<len(terms) else terms[i]
                       for i in range(0,len(terms),2)]
            raw=rec_binding(10,arr(I,I),lam(11,I,terms[0]),lit())
            for i in reversed(range(count)):raw=let(1000+i,var(20),raw)
            return with_data(let(20,ctor('Pack',lit()),raw))
        for count,self_use in ((63,True),(64,False)):
            with self.subTest(count=count,self_use=self_use):
                row=m.derive_shared_fragment(tree(count,self_use))['recursion']['bindings'][0]
                self.assertEqual(len(row['captures']['nominals']),count)
                self.assertEqual(bool(row['self_uses']),self_use)
        self.reject(tree(64,True),'LIMIT')

    def test_foreign_open_parameterized_recursive_DATA_and_bad_SUM_still_reject(self):
        self.reject(lam(20,nominal_type('Unknown'),rec_binding(10,arr(I,I),lam(11,I,lit()),lit())))
        typ=nominal_type('Box');typ['arguments']=[I]
        self.reject(with_data(lam(20,typ,rec_binding(10,arr(I,I),lam(11,I,lit()),lit()))))
        invalid=[data_decl('Box','Pack',(nominal_type('Box'),)),
                 sum_decl('Box',(('Empty',()),('Pack',(arr(I,I),)))),
                 sum_decl('Box',(('Empty',()),('Pack',(nominal_type('Other'),))))]
        for declaration in invalid:
            with self.subTest(declaration=declaration):
                self.reject(with_data(lam(20,nominal_type('Box'),
                    rec_binding(10,arr(I,I),lam(11,I,let(21,var(20),lit())),lit())),declaration))
        declaration=data_decl();declaration['parameters']=[{'name':'a','kind':{'tag':'star'}}]
        self.reject(with_data(lam(20,nominal_type('Box'),rec_binding(10,arr(I,I),lam(11,I,lit()),lit())),declaration))

    def test_nominal_arrows_generic_recursion_and_nominal_scheme_arguments_stay_out(self):
        raw=with_data(let(20,lam(21,nominal_type('Box'),lit()),
            rec_binding(10,arr(I,I),lam(11,I,app(var(20),ctor('Pack',lit()))),lit())))
        self.reject(raw,'RECURSION')
        raw=with_data(tapp(tabs(100,lam(20,nominal_type('Box'),
            rec_binding(10,arr(I,I),lam(11,I,lit()),lit()))),inst(I)))
        self.reject(raw,'RECURSION')
        self.reject(with_data(shared(app(use(1,nominal_type('Box')),ctor('Pack',lit())))),'USE')

    def test_wrong_family_pattern_and_same_shape_argument_do_not_match(self):
        raw=with_data(let(20,ctor('A',lit()),rec_binding(10,arr(I,I),
            lam(11,I,case(var(20),'B',(21,),var(21))),lit())),
            data_decl('First','A'),data_decl('Second','B'))
        self.reject(raw,'CASE')
        raw=with_data(let(20,ctor('A',lit()),rec_binding(10,arr(I,I),
            lam(11,I,app(lam(21,nominal_type('Second'),lit()),var(20))),lit())),
            data_decl('First','A'),data_decl('Second','B'))
        self.reject(raw,'TYPE')

    def test_forged_nominal_policy_declaration_type_owner_or_occurrences_rejected(self):
        tree=nominal_capture();out=m.derive_shared_fragment(tree)
        mutations=[lambda c:c.update(policy=m.RECURSIVE_CALLABLE_CAPTURE_POLICY),lambda c:c.pop('callables'),
            lambda c:c['nominals'].clear(),lambda c:c['nominals'][0].update(binding=name(999)),
            lambda c:c['nominals'][0].update(declaration=0),lambda c:c['nominals'][0].update(type=nominal_type('Chain')),
            lambda c:c['nominals'][0]['occurrences'].clear(),lambda c:c['nominals'][0].update(origin='E0'),
            lambda c:c['nominals'].append(copy.deepcopy(c['nominals'][0])),
            lambda c:c['scalars'].append({'binding':name(70),'type':I,'occurrences':[]})]
        for index,mutate in enumerate(mutations):
            forged=copy.deepcopy(out);mutate(forged['recursion']['bindings'][0]['captures'])
            with self.subTest(index=index),self.assertRaises(m.SharedTransportError) as caught:
                m.validate_shared_fragment(tree,forged)
            self.assertEqual(caught.exception.code,'EVIDENCE')

    def test_old_callable_evidence_goldens_are_unchanged_without_nominals(self):
        expected={False:'beeee839ce3873c9bcae505f8a1ed05984882f7305728bcfa37d2357bcde6552',
                  True:'772dbe7bd350a23b1397d1fcf0c205b1c439e8614012d6cc473839bc0726ff90'}
        for alias,pin in expected.items():
            out=m.derive_shared_fragment(callable_capture(alias))
            self.assertEqual(hashlib.sha256(m._json(out).encode()).hexdigest(),pin)
            self.assertNotIn('nominals',out['recursion']['bindings'][0]['captures'])


RECURSIVE_NOMINAL_CAPTURE_ROOT=os.environ.get('IR8_RECURSIVE_NOMINAL_CAPTURE_ROOT')


@unittest.skipUnless(RECURSIVE_NOMINAL_CAPTURE_ROOT,
                    'set IR8_RECURSIVE_NOMINAL_CAPTURE_ROOT for completed nominal-owner captures')
class RetainedRecursiveNominalCaptureTests(unittest.TestCase):
    def test_both_original_captures_exact_declaration_owner_and_proof_replay(self):
        from source_capture_v8 import verify_capture
        root=Path(RECURSIVE_NOMINAL_CAPTURE_ROOT).resolve()
        pins={
            'data-owner':('248174cce063da15ecd8560c72df9a22b06ca3003e41a385cd2523da576c0413',
                          '178a56e23219b9e51e9bceb9d26555c2eb13fa54a84a16c7995fe94395fe1dab'),
            'sum-owner':('dd03eee615c2d78e49050d3123442f3c1ec166c2b008abb1741f9b075a1eb19c',
                         '3eb612053a5a2c892ab0564d5ff505023958c6c04782383ed6034b509876ec01')}
        for label,(capture_hash,source_hash) in pins.items():
            with self.subTest(label=label):
                path=root/('capture-'+label+'01')/'capture.stdout'
                old_path=path.parent/'verification.json';old_bytes=old_path.read_bytes()
                report=verify_capture(path,fixture_root=root/'inputs'/label,entry='main.emlf',
                    expected_source_hashes={'main.emlf':source_hash,
                        'SharedPoly.emlf':'50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'},
                    expected_capture_sha256=capture_hash)
                self.assertTrue(report['fragment_admitted']);self.assertFalse(report['source_admitted'])
                self.assertFalse(report['native_admitted'])
                capture=json.loads(path.read_bytes());out=m.derive_shared_fragment(capture['projection']['projected_annotated'])
                self.assertEqual(out['steps'],capture['normalization']['steps'])
                self.assertEqual(out['raw_normalized'],capture['normalization']['raw_normalized'])
                self.assertEqual(out['checked_type'],I);self.assertEqual(len(out['steps']),2)
                definition,=out['polymorphism']['definitions'];join,=report['retained_prefix_binding_joins']
                self.assertEqual(definition['binding'],join['binding'])
                self.assertEqual(join['resolver_allocation']['entity'],
                    {'namespace':'terms','owner':'SharedPoly','role':{'tag':'value'},'spelling':'sharedId'})
                self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[I],[B]])
                raw=out['raw_normalized'];shared_let=m._get(raw,definition['binding_source']['path'])
                binding=shared_let['body'];rec=binding['body'];row,=out['recursion']['bindings'];caps=row['captures']
                self.assertEqual(row['binding'],rec['bindings'][0]['name'])
                owner,=caps['nominals'];self.assertEqual(owner['binding'],binding['name'])
                self.assertEqual(caps['policy'],m.RECURSIVE_NOMINAL_CAPTURE_POLICY)
                self.assertEqual(caps['callables'],[]);self.assertEqual(caps['scalars'],[])
                self.assertEqual([m._get(raw,a['path']) for a in owner['occurrences']],
                                 [{'tag':'var','name':binding['name']}])
                data_owner=label=='data-owner';table=out['nominal_data' if data_owner else 'nominal_sum']
                declaration=next(d for d in table['declarations'] if d['index']==owner['declaration'])
                self.assertEqual(owner['type'],declaration['type'])
                entities={e['allocated']:e['entity'] for e in capture['module_custody']['resolution']['entities']}
                self.assertEqual(entities[declaration['name']],{'namespace':'types','owner':'Main',
                    'role':{'tag':'datatype'},'spelling':'Payload' if data_owner else 'IntList'})
                pending=binding['value'];self.assertEqual(pending['tag'],'application')
                self.assertEqual(pending['function']['parameter_type'],owner['type'])
                self.assertEqual(pending['function']['body'],{'tag':'var','name':pending['function']['parameter']})
                payload=pending['argument'];self.assertEqual(payload['tag'],'application')
                # Constructor applications, not eager field values, remain in the pending owner.
                self.assertEqual(payload['function']['argument']['tag'],'application')
                if data_owner:
                    self.assertEqual(caps['views'],[]);self.assertEqual(row['free_term_bindings'],[binding['name']['id']])
                    self.assertEqual(declaration['field_types'],[I,arr(I,I)])
                    self.assertEqual(payload['argument']['tag'],'application')
                    self.assertEqual(payload['argument']['argument']['tag'],'type_application')
                    data_case,=out['nominal_data']['cases']
                    self.assertEqual(data_case['declaration'],owner['declaration'])
                    self.assertEqual(m._get(raw,data_case['scrutinee']['path']),{'tag':'var','name':binding['name']})
                else:
                    self.assertEqual([v['arguments'] for v in caps['views']],[[I]])
                    self.assertEqual(row['free_term_bindings'],sorted([binding['name']['id'],definition['binding']['id']]))
                    self.assertEqual(declaration['variants'][1]['field_types'],[I,owner['type']])
                    tail=payload['argument'];self.assertEqual(tail['tag'],'application')
                    self.assertEqual(tail['function']['tag'],'lambda');self.assertEqual(tail['function']['parameter_type'],I)
                    seed_case=next(c for c in out['nominal_sum']['cases']
                                   if m._get(raw,c['scrutinee']['path'])=={'tag':'var','name':binding['name']})
                    self.assertIsNone(seed_case['arms'][1]['fields'][1]['binding'])
                self.assertEqual(old_path.read_bytes(),old_bytes)
                old=json.loads(old_bytes);self.assertFalse(old['fragment_admitted'])
                self.assertEqual(old['fragment_error']['code'],'RECURSION')


if __name__ == '__main__':
    unittest.main()
