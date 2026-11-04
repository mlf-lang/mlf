"""Stage21 bounded declaration/metadata tests; no source or native execution.

Synthetic raw IR controls exercise the public host boundary. They are not
genuine source-custody, graph-execution or lifecycle evidence.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from resource_ir_v8.declarations import DeclarationError, check_declarations
from resource_ir_v8.metadata import check_metadata, _fresh, _verify_derived
from resource_ir_v8.metadata_budget import Budget, MetadataError
from resource_ir_v8.metadata_types import _verify_domains

CASES = {c['name']: c['text'] for c in json.loads(
    (ROOT / 'tests/fixtures/ir8-metadata.json').read_text())['cases']}
DECLARATIONS = ('layouts', 'families', 'signatures', 'types', 'schemes', 'instantiations')


def raw(name='ready_shared_identity_two_views'):
    return json.loads(CASES[name])


def declarations(program):
    return {key: program[key] for key in DECLARATIONS}


def nominal(program, name='Box', *, family=False, alias='N'):
    if family:
        program['families'][name] = {
            'variants': ['Nil', 'Cons'],
            'fields': {'Nil': [], 'Cons': ['#i64', '%' + name]}}
        atom = '%' + name
    else:
        program['layouts'][name] = {}
        atom = name
    program['types'][alias] = {'tag': 'closed', 'layout': atom}
    return atom


def view_program(arguments, *, base='ready_shared_identity_two_views'):
    """Retain one generic RHS and every declared use, without forcing values."""
    program = raw(base)
    program['instantiations'] = {
        'use' + str(index): {'scheme': 'S', 'arguments': vector}
        for index, vector in enumerate(arguments)}
    program['entry'] = program['entry'][:2]
    for index, name in enumerate(program['instantiations']):
        owner, view = 'owner' + str(index), 'view' + str(index)
        program['entry'].extend([
            {'op': 'retain', 'out': owner, 'value': 'shared'},
            {'op': 'instantiate', 'out': view, 'value': owner, 'instantiation': name},
            {'op': 'drop', 'value': view}])
    program['entry'].extend([
        {'op': 'drop', 'value': 'shared'}, {'op': 'drop', 'value': 'home'}, {'op': 'finish'}])
    return program


def nominal_application(*, family=False, curried=False):
    program = raw('curried_const_complete_ib_bi_views' if curried else 'ready_shared_identity_two_views')
    atom = nominal(program, 'Chain' if family else 'Box', family=family, alias='I')
    for index, instruction in enumerate(program['entry']):
        if instruction['op'] == 'scalar' and instruction['kind'] == 'i64':
            program['entry'][index] = (
                {'op': 'construct_nullary', 'out': instruction['out'], 'in': 'home',
                 'family': 'Chain', 'variant': 'Nil'} if family else
                {'op': 'alloc', 'out': instruction['out'], 'in': 'home', 'layout': 'Box', 'fields': {}})
    program['entry'][-1:] = [{'op': 'drop', 'value': 'answer'}, {'op': 'finish'}]
    return program, atom


def document(program):
    return json.loads(check_metadata(program).metadata_json)


def type_id(data, atom):
    return next(row['id'] for row in data['types'] if row['tag'] == 'closed' and row['atom'] == atom)


def resolved(data, typ, env):
    return next(row['result'] for row in data['type_resolutions'] if (row['type'], row['env']) == (typ, env))


class NominalDeclarations(unittest.TestCase):
    def test_data_and_recursive_sum_complete_vectors(self):
        program = view_program([['N'], ['L'], ['B']])
        nominal(program); nominal(program, 'Chain', family=True, alias='L')
        checked = check_declarations(declarations(program))
        for name, atom in (('use0', 'Box'), ('use1', '%Chain'), ('use2', '#bool')):
            scheme, arguments, result = checked.instantiated(name)
            self.assertEqual(scheme, 'S')
            self.assertEqual(arguments, (('closed', atom),))
            self.assertEqual(result, ('arrow', arguments[0], arguments[0], 'repeat', 'unknown'))

    def test_equal_layouts_are_distinct_atoms_but_exact_aliases_deduplicate(self):
        program = view_program([['N'], ['Other'], ['Alias']])
        nominal(program); nominal(program, 'OtherBox', alias='Other')
        program['types']['Alias'] = {'tag': 'closed', 'layout': 'Box'}
        checked = check_declarations(declarations(program))
        self.assertTrue(checked.same('^N', '^Alias'))
        self.assertFalse(checked.same('^N', '^Other'))
        self.assertEqual(len(checked.environments), 4)
        self.assertEqual(checked.instantiated('use0'), checked.instantiated('use2'))

    def test_open_arrow_partial_extra_and_physical_reference_rejected(self):
        for argument, code in ((['A'], 'USE_ARGUMENT'), (['AA'], 'USE_ARGUMENT'),
                               ([], 'ARITY'), (['I', 'B'], 'ARITY'), (['%Chain'], 'TYPE_REFERENCE')):
            with self.subTest(argument=argument):
                program = view_program([argument]); nominal(program, 'Chain', family=True)
                with self.assertRaises(DeclarationError) as caught:
                    check_declarations(declarations(program))
                self.assertEqual(caught.exception.code, code)

    def test_unknown_atoms_and_unregistered_intrinsics_rejected(self):
        for atom, code in (('Unknown', 'LAYOUT'), ('%Unknown', 'FAMILY'),
                           ('#unknown', 'CLOSED_ATOM'), ('@id', 'CLOSED_ATOM')):
            with self.subTest(atom=atom):
                program = view_program([['N']])
                program['types']['N'] = {'tag': 'closed', 'layout': atom}
                with self.assertRaises(DeclarationError) as caught:
                    check_declarations(declarations(program))
                self.assertEqual(caught.exception.code, code)

    def test_nominal_generic_principal_stays_rejected(self):
        program = view_program([['N']]); nominal(program)
        checked = check_declarations(declarations(program))
        with self.assertRaises(DeclarationError) as caught:
            checked.resolve('^N', 'S')
        self.assertEqual(caught.exception.code, 'GENERIC_ATOM')
        program['types']['AA']['result'] = 'N'
        with self.assertRaises(DeclarationError) as caught:
            check_declarations(declarations(program))
        self.assertEqual(caught.exception.code, 'GENERIC_ATOM')


class NominalMetadata(unittest.TestCase):
    def test_identity_data_and_sum_use_existing_canonical_descriptors(self):
        for family in (False, True):
            with self.subTest(family=family):
                program, atom = nominal_application(family=family)
                data = document(program); nominal_type = type_id(data, atom)
                self.assertEqual(len(data['codes']), 1)
                scheme = data['schemes'][0]
                self.assertEqual(data['types'][data['codes'][0]['argument']]['tag'], 'rigid')
                self.assertEqual(resolved(data, nominal_type, 0), nominal_type)
                shape = next(row for row in data['shapes'] if row['source'] == {'kind': 'legacy', 'reference': atom})
                self.assertEqual(shape['kind'], 'SUM' if family else 'DATA')
                typing = data['shape_typing'][shape['id']]
                self.assertEqual((typing['type'], typing['scope'], typing['contract']), (nominal_type, None, None))
                rep = data['representations'][shape['id']]
                self.assertEqual((rep['shape'], rep['typing'], rep['ready_kind']),
                                 (shape['id'], shape['id'], 'sum' if family else 'data'))
                use = next(row for row in data['uses'] if row['arguments'] == [nominal_type])
                self.assertEqual(resolved(data, scheme['body'], use['env']), use['result_type'])
                if family:
                    self.assertEqual(data['families'][0]['shape'], shape['id'])
                _verify_derived(program, data)

    def test_curried_nominal_capture_is_resolved_without_code_or_origin_cloning(self):
        for family in (False, True):
            with self.subTest(family=family):
                program, atom = nominal_application(family=family, curried=True)
                data = document(program); nominal_type = type_id(data, atom)
                self.assertEqual(len(data['codes']), 2)
                self.assertEqual(len(data['introductions']), 1)
                code = next(row for row in data['codes'] if row['name'] == 'return_x')
                self.assertEqual(data['types'][code['captures'][0]['type']]['tag'], 'rigid')
                self.assertEqual(code['captures'][0]['relation'], 'down')
                env = next(row['env'] for row in data['uses'] if row['arguments'][0] == nominal_type)
                execution = next(row for row in data['code_executions'] if row['code'] == code['id'] and row['env'] == env)
                self.assertEqual(execution['captures'][0]['type'], nominal_type)
                self.assertEqual(execution['captures'][0]['relation'], 'down')
                site = next(row for row in data['sites'] if row['code'] == code['id'])
                instance = next(row for row in data['site_executions'] if row['site'] == site['id'] and row['env'] == env)
                self.assertEqual(instance['origin_kind'], 'INSTANCE')
                accesses = [row for row in data['accesses'] if row['site'] == site['id'] and row['origin_env'] == env]
                self.assertTrue(accesses)
                self.assertTrue(all(row['use_env'] == env and row['mode'] == 'MONO' for row in accesses))

    def test_dead_nominal_coordinates_and_unused_intermediate_types_are_retained(self):
        program = view_program([['I', 'N'], ['I', 'L'], ['I', 'N']],
                               base='scoped_intermediate_dead_parameter_substitution')
        nominal(program); nominal(program, 'Chain', family=True, alias='L')
        data = document(program); uses = data['uses']
        self.assertEqual(len(data['environments']), 4)
        self.assertEqual(uses[0]['env'], uses[2]['env'])
        self.assertNotEqual(uses[0]['env'], uses[1]['env'])
        self.assertEqual(uses[0]['result_type'], uses[1]['result_type'])
        unused = next(row for row in data['codes'] if row['name'] == 'unused_b')
        for use in uses:
            arrow = data['types'][resolved(data, unused['callable_type'], use['env'])]
            self.assertEqual((arrow['argument'], arrow['result']), (use['arguments'][1],) * 2)
            self.assertEqual(resolved(data, arrow['id'], 0), arrow['id'])
        self.assertEqual(sum(row['context']['kind'] == 'introduction' for row in data['sites']), 1)

    def test_escaped_unicode_vector_order_matches_canonical_type_ids(self):
        program = view_program([['N0', 'N1'], ['N1', 'N0'], ['N2', 'N3'],
                                ['I', 'N4'], ['I', 'N5'], ['I', 'N6']],
                               base='dead_parameter_two_complete_vectors')
        names = ['\nBox', 'A', '"Quoted', '\\Slash', 'Ω', '\tTab', '界']
        for index, name in enumerate(names):
            nominal(program, name, alias='N' + str(index))
        data = document(program)
        actual = [row['arguments'] for row in data['environments'] if row['mode'] == 'CLOSED']
        self.assertEqual(actual, sorted(actual))
        argument_atoms = [[data['types'][value]['atom'] for value in vector] for vector in actual]
        self.assertEqual(argument_atoms, sorted(argument_atoms,
            key=lambda vector: tuple(json.dumps(atom, ensure_ascii=False) for atom in vector)))
        self.assertNotEqual(argument_atoms, sorted(argument_atoms))
        self.assertEqual([row['environment'] for row in data['environment_remap']], list(range(len(data['environments']))))
        reordered = copy.deepcopy(program)
        for key in DECLARATIONS:
            reordered[key] = dict(reversed(list(reordered[key].items())))
        self.assertEqual(check_metadata(program).metadata_sha256, check_metadata(reordered).metadata_sha256)

    def test_independent_domains_reject_unregistered_closed_atom_and_open_arrow(self):
        for mutation in ('unknown', 'arrow'):
            with self.subTest(mutation=mutation):
                program = view_program([['N']]); nominal(program)
                budget = Budget()
                _, owned, derived, closure = _fresh(program, budget)
                env = next(row for row in closure.tables['environments'] if row['mode'] == 'CLOSED')
                if mutation == 'unknown':
                    closure.tables['types'][env['arguments'][0]]['atom'] = 'Unregistered'
                else:
                    env['arguments'][0] = next(row['id'] for row in closure.tables['types']
                        if row['tag'] == 'arrow' and closure.scopes[row['id']])
                with self.assertRaises(MetadataError) as caught:
                    _verify_domains(owned, derived, closure, budget)
                self.assertEqual((caught.exception.layer, caught.exception.code, caught.exception.path),
                                 ('metadata-type', 'VECTOR', 'metadata.environments'))

    def test_full_verifier_rejects_eligible_arrow_in_wrong_complete_vector(self):
        # Stage23 admits this closed domain but never trusts a substituted Env
        # coordinate in place of the exact registered raw complete vector.
        program = view_program([['N']]); nominal(program)
        data = document(program)
        env = next(row for row in data['environments'] if row['mode'] == 'CLOSED')
        env['arguments'][0] = next(row['id'] for row in data['types']
            if row['tag'] == 'arrow' and
            all(data['types'][row[side]]['tag'] == 'closed' for side in ('argument', 'result')))
        with self.assertRaises(MetadataError):
            _verify_derived(program, data)

    def test_full_verifier_rejects_nominal_table_forgeries(self):
        program, atom = nominal_application(family=True, curried=True)
        original = document(program); nominal_type = type_id(original, atom)
        shape_id = next(row['id'] for row in original['shapes'] if row['source'] == {'kind': 'legacy', 'reference': atom})
        use_id = next(row['id'] for row in original['uses'] if row['arguments'][0] == nominal_type)
        env_id = original['uses'][use_id]['env']
        mutations = {
            'type-atom': lambda d: d['types'][nominal_type].update(atom='%Unknown'),
            'shape-kind': lambda d: d['shapes'][shape_id].update(kind='DATA'),
            'shape-identity': lambda d: d['shapes'][shape_id]['source'].update(reference='%Unknown'),
            'typing-scope': lambda d: d['shape_typing'][shape_id].update(scope=0),
            'representation-ready': lambda d: d['representations'][shape_id].update(ready_kind='data'),
            'family-shape': lambda d: d['families'][0].update(shape=0),
            'vector-order': lambda d: d['environments'][env_id]['arguments'].reverse(),
            'dead-coordinate-loss': lambda d: d['environments'][env_id]['arguments'].pop(),
            'use-env': lambda d: d['uses'][use_id].update(env=0),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                data = copy.deepcopy(original); mutate(data)
                with self.assertRaises(MetadataError):
                    _verify_derived(program, data)


class ScalarGoldenCompatibility(unittest.TestCase):
    # Captured from the untouched Stage20 candidate with PYTHONHASHSEED=0.
    # Its metadata_types.py SHA256 is c08280d6d268399d4658c3f5a50de0b8b2cfb77648d641655da9dacc6ce463b1.
    # Metadata hashes pin every table; statistics pin host work. The existing
    # string-set sort has seed-dependent comparator work, so use the same seed.
    GOLDENS = {
        'concrete_scalar': ('cd77869ed649fb89bf572eeaace2acc47410de0052713f30cf390f08118ecbce', 86, 23727, 33088, 10778),
        'ready_shared_identity_two_views': ('bc5940fa6021280e70da9a2e05dcbcbb194ff605b6b0bfd3900c9a8a2693ba5f', 354, 91576, 152741, 38056),
        'curried_const_complete_ib_bi_views': ('5326761df6695f5e082f04281f04c877b10e798b0aaba7a9206d46e2fa49630d', 586, 157755, 256312, 65116),
        'dead_parameter_two_complete_vectors': ('d8b4d5c77fa4862fd39b8169c00eb47a2be0a98a1049178167c64d7e187b0741', 345, 89349, 146923, 37253),
    }

    def test_scalar_metadata_and_work_are_byte_exact(self):
        # One bounded Python-only child. No compiler, emitter, native executable
        # or capture is imported/invoked; output is exactly four fixed records.
        result = subprocess.run([sys.executable, '-B', __file__, '--scalar-goldens'],
            env=dict(os.environ, PYTHONHASHSEED='0', PYTHONDONTWRITEBYTECODE='1'),
            capture_output=True, text=True, timeout=30, check=True)
        self.assertEqual(result.stderr, '')
        self.assertEqual(json.loads(result.stdout), {name: list(value) for name, value in self.GOLDENS.items()})


def scalar_observations():
    output = {}
    for name in ScalarGoldenCompatibility.GOLDENS:
        result = check_metadata(raw(name))
        statistics = dict(dict(result.report())['host_statistics'])
        output[name] = [result.metadata_sha256, statistics['metadata_records'], statistics['creation_units'],
                        statistics['work_units'], statistics['metadata_utf8_bytes']]
    return output


if __name__ == '__main__':
    if sys.argv[1:] == ['--scalar-goldens']:
        print(json.dumps(scalar_observations(), sort_keys=True))
    else:
        unittest.main()
