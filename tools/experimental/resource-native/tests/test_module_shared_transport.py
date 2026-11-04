"""Synthetic/raw-extracted independent replay tests, NOT source/K/native tests.

No original compiler is invoked. The extracted fixture preserves exact raw
subtrees; synthetic lexical surroundings close them for this bounded seam.
"""
import copy
import hashlib
import json
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

    def test_parameterized_multiple_or_missing_constructor_rejected(self):
        for alteration in ('parameter', 'multiple', 'none'):
            with self.subTest(alteration=alteration):
                declaration = data_decl()
                if alteration == 'parameter':
                    declaration['parameters'] = [{'name': 'a', 'kind': {'tag': 'star'}}]
                elif alteration == 'multiple':
                    declaration['constructors'].append({'name': 'Other', 'fields': []})
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


if __name__ == '__main__':
    unittest.main()
