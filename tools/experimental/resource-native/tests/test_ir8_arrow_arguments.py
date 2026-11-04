"""Stage23 focused host controls, not source/native or lifecycle evidence."""
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
from resource_ir_v8.declaration_adapter import check_type_ids
from resource_ir_v8.metadata import check_metadata, _fresh, _verify_derived
from resource_ir_v8.metadata_budget import Budget, MetadataError
from resource_ir_v8.metadata_types import _verify_domains
from test_ir8_nominal_arguments import (raw, view_program, declarations, nominal,
                                       nominal_application, document, resolved)


def arrow(program, name, argument, result, *, protocol='repeat', identity='unknown'):
    program['types'][name] = {'tag': 'arrow', 'argument': argument, 'result': result,
                             'protocol': protocol, 'result_identity': identity}
    return name


def recursive_program():
    p = view_program([['II'], ['BB'], ['Nested'], ['NArrow'], ['LArrow'], ['II']])
    nominal(p); nominal(p, 'Chain', family=True, alias='L')
    arrow(p, 'II', 'I', 'I'); arrow(p, 'BB', 'B', 'B')
    arrow(p, 'Nested', 'II', 'BB'); arrow(p, 'NArrow', 'N', 'II')
    arrow(p, 'LArrow', 'L', 'L')
    return p


def diamond(p, levels, leaf='I'):
    for level in range(levels):
        leaf = arrow(p, 'D' + str(level), leaf, leaf)
    return leaf


def arrow_application(*, curried=False):
    p = raw('curried_const_complete_ib_bi_views' if curried else 'ready_shared_identity_two_views')
    p['types']['Scalar'] = {'tag': 'closed', 'layout': '#i64'}
    arrow(p, 'I', 'Scalar', 'Scalar')
    p['signatures']['concrete_id'] = {'argument': '#i64', 'result': '#i64',
        'protocol': 'repeat', 'result_identity': 'unknown'}
    p['functions']['concrete_id'] = {'signature': 'concrete_id', 'type_scope': None, 'parameter': 'x',
        'captures': {}, 'body': [{'op': 'return', 'value': 'x'}]}
    for index, instruction in enumerate(p['entry']):
        if instruction['op'] == 'scalar' and instruction['kind'] == 'i64':
            p['entry'][index] = {'op': 'closure', 'out': instruction['out'],
                'in': 'home', 'function': 'concrete_id', 'captures': {}}
    p['entry'][-1:] = [{'op': 'drop', 'value': 'answer'}, {'op': 'finish'}]
    return p


class ArrowDeclarations(unittest.TestCase):
    def test_nested_registered_leaves_aliases_and_complete_vectors(self):
        p = recursive_program()
        index = check_type_ids(declarations(p))
        self.assertEqual(index.instantiation('use0'), index.instantiation('use5'))
        self.assertEqual(len(index.environments), 7)
        self.assertTrue(all(index.rows[value][0] == 'arrow'
            for _, (_, mode, vector) in index.environments if mode == 'CLOSED'
            for value in vector))
        for number, row in enumerate(index.rows):
            if row[0] == 'arrow':
                self.assertLess(row[1], number); self.assertLess(row[2], number)

    def test_open_once_and_argument_identity_at_every_depth_reject(self):
        for bad in ('open', 'once', 'identity'):
            for nested in (False, True):
                with self.subTest(bad=bad, nested=nested):
                    p = view_program([['Outer' if nested else 'Bad']])
                    arrow(p, 'Bad', 'A' if bad == 'open' else 'I',
                          'A' if bad == 'open' else 'I',
                          protocol='once' if bad == 'once' else 'repeat',
                          identity='argument' if bad == 'identity' else 'unknown')
                    if nested: arrow(p, 'Outer', 'Bad', 'Bad')
                    with self.assertRaises(DeclarationError) as caught:
                        check_declarations(declarations(p))
                    self.assertEqual((caught.exception.code, caught.exception.path),
                                     ('USE_ARGUMENT', 'instantiations.use0.arguments'))

    def test_unknown_leaf_cycles_and_incomplete_vectors_reject(self):
        for failure in ('atom', 'cycle', 'arity'):
            with self.subTest(failure=failure):
                p = view_program([['F']])
                arrow(p, 'F', 'I', 'I')
                if failure == 'atom': p['types']['I']['layout'] = 'Missing'
                if failure == 'cycle': p['types']['F']['result'] = 'F'
                if failure == 'arity': p['instantiations']['use0']['arguments'] = []
                with self.assertRaises(DeclarationError) as caught:
                    check_declarations(declarations(p))
                self.assertEqual(caught.exception.code,
                    {'atom': 'LAYOUT', 'cycle': 'TYPE_CYCLE', 'arity': 'ARITY'}[failure])

    def test_shared_diamond_depth_and_substitution_bound(self):
        p = view_program([['D29']]); diamond(p, 30)
        index = check_type_ids(declarations(p))
        self.assertLess(len(index.rows), 40)
        shared = check_declarations(declarations(p))
        node = shared.resolve('^D29')
        for _ in range(30):
            self.assertIs(node[1], node[2])
            node = node[1]
        data = document(p)
        self.assertLess(len(data['types']), 40)
        p = view_program([['D30']]); diamond(p, 31)
        with self.assertRaises(DeclarationError) as caught:
            check_declarations(declarations(p))
        self.assertEqual(caught.exception.code, 'TYPE_DEPTH')
        self.assertEqual(caught.exception.path, 'instantiations["S"]')


class ArrowMetadata(unittest.TestCase):
    def test_recursive_coordinates_have_exact_e0_and_canonical_representations(self):
        p = recursive_program(); d = document(p)
        self.assertEqual(len(d['codes']), 1)
        canonical = {r['source']['type']: r for r in d['shapes']
                     if r['source']['kind'] == 'canonical-arrow'}
        for use in d['uses']:
            self.assertEqual(resolved(d, d['schemes'][0]['body'], use['env']), use['result_type'])
            pending, seen = list(use['arguments']), set()
            while pending:
                typ = pending.pop()
                if typ in seen: continue
                seen.add(typ)
                self.assertEqual(resolved(d, typ, 0), typ)
                row = d['types'][typ]
                if row['tag'] != 'arrow': continue
                shape = canonical[typ]; sid = shape['id']
                typing = d['shape_typing'][sid]; rep = d['representations'][sid]
                self.assertEqual((shape['kind'], typing['scope'], typing['type']), ('REPEAT', None, typ))
                self.assertEqual(rep['ready_kind'], 'function')
                contract = d['callable_contracts'][typing['contract']]
                self.assertEqual((contract['type'], contract['protocol'], contract['result_identity']),
                                 (typ, 'repeat', 'unknown'))
                for side in ('argument', 'result'):
                    child = row[side]
                    child_rep = d['representation_resolutions'][next(
                        r['id'] for r in d['type_resolutions'] if (r['type'], r['env']) == (child, 0))]
                    self.assertEqual(shape[side + '_rep'], child_rep['representation'])
                    pending.append(child)
        _verify_derived(p, d)

    def test_application_and_curried_capture_keep_actual_origin_and_down(self):
        for curried in (False, True):
            with self.subTest(curried=curried):
                p = arrow_application(curried=curried); d = document(p)
                self.assertEqual(len(d['introductions']), 1)
                self.assertEqual(len(d['codes']), 3 if curried else 2)
                if curried:
                    code = next(r for r in d['codes'] if r['name'] == 'return_x')
                    arrow_use = next(u for u in d['uses'] if d['types'][u['arguments'][0]]['tag'] == 'arrow')
                    execution = next(r for r in d['code_executions']
                        if (r['code'], r['env']) == (code['id'], arrow_use['env']))
                    self.assertEqual(execution['captures'][0]['type'], arrow_use['arguments'][0])
                    self.assertEqual(execution['captures'][0]['relation'], 'down')
                    site = next(r for r in d['sites'] if r['code'] == code['id'])
                    instance = next(r for r in d['site_executions']
                        if (r['site'], r['env']) == (site['id'], arrow_use['env']))
                    self.assertEqual(instance['origin_kind'], 'INSTANCE')
                _verify_derived(p, d)

    def test_mixed_depth_escaped_leaf_order_is_canonical_and_map_independent(self):
        p = view_program([['N1'], ['Deep'], ['F0'], ['B'], ['F1'], ['N0'], ['I']])
        nominal(p, '\nBox', alias='N0'); nominal(p, 'Ω', alias='N1')
        arrow(p, 'F0', 'N0', 'N1'); arrow(p, 'F1', 'N1', 'N0')
        arrow(p, 'Deep', 'F1', 'F0')
        d = document(p)
        vectors = [e['arguments'] for e in d['environments'] if e['mode'] == 'CLOSED']
        self.assertEqual(vectors, sorted(vectors))
        index = check_type_ids(declarations(p))
        remap = [r['metadata_type'] for r in d['type_remap']]
        expected = [[remap[t] for t in vector] for _, (_, mode, vector) in index.environments if mode == 'CLOSED']
        self.assertEqual(vectors, expected)
        reordered = copy.deepcopy(p)
        for key in declarations(p): reordered[key] = dict(reversed(list(reordered[key].items())))
        self.assertEqual(check_metadata(p).metadata_sha256, check_metadata(reordered).metadata_sha256)

    def test_dead_coordinates_and_unused_intermediate_substitution(self):
        p = view_program([['I', 'II'], ['I', 'BB'], ['I', 'II']],
                         base='scoped_intermediate_dead_parameter_substitution')
        arrow(p, 'II', 'I', 'I'); arrow(p, 'BB', 'B', 'B')
        d = document(p); uses = d['uses']
        self.assertEqual(uses[0]['env'], uses[2]['env'])
        self.assertNotEqual(uses[0]['env'], uses[1]['env'])
        self.assertEqual(uses[0]['result_type'], uses[1]['result_type'])
        unused = next(r for r in d['codes'] if r['name'] == 'unused_b')
        for use in uses:
            row = d['types'][resolved(d, unused['callable_type'], use['env'])]
            self.assertEqual((row['argument'], row['result']), (use['arguments'][1],) * 2)
            self.assertEqual(resolved(d, row['id'], 0), row['id'])

    def test_unused_intermediate_depth_overflow_is_still_checked(self):
        p = view_program([['I', 'D30']], base='scoped_intermediate_dead_parameter_substitution')
        diamond(p, 31)
        check_declarations(declarations(p))  # dead in S.body, so this phase is in bounds
        with self.assertRaises(MetadataError) as caught:
            check_metadata(p)
        self.assertEqual((caught.exception.layer, caught.exception.code), ('metadata-bounds', 'TYPE_DEPTH'))
        self.assertTrue(caught.exception.path.startswith('metadata.type_resolutions['))

    def test_independent_domains_check_nested_contracts_and_child_ids(self):
        for change in ('once', 'identity', 'rigid', 'unknown', 'negative', 'boolean', 'forward', 'missing'):
            with self.subTest(change=change):
                p = recursive_program(); b = Budget()
                _, owned, derived, closure = _fresh(p, b)
                tables = closure.tables
                root = closure.reference('^Nested'); child = tables['types'][root]['argument']
                row = tables['types'][child]
                if change == 'once': row['protocol'] = 'once'
                elif change == 'identity': row['result_identity'] = 'argument'
                elif change == 'rigid':
                    row['argument'] = next(t['id'] for t in tables['types'] if t['tag'] == 'rigid')
                elif change == 'unknown': tables['types'][row['argument']]['atom'] = 'Missing'
                elif change == 'negative': row['argument'] = -1
                elif change == 'boolean': row['argument'] = True
                elif change == 'forward': row['argument'] = child
                else: del row['argument']
                with self.assertRaises(MetadataError):
                    _verify_domains(owned, derived, closure, b)

    def test_independent_domains_reject_noncanonical_complete_vector_order(self):
        p = recursive_program(); b = Budget()
        _, owned, derived, closure = _fresh(p, b)
        closed = [e for e in closure.tables['environments'] if e['mode'] == 'CLOSED']
        closed[0]['arguments'], closed[-1]['arguments'] = closed[-1]['arguments'], closed[0]['arguments']
        with self.assertRaises(MetadataError) as caught:
            _verify_domains(owned, derived, closure, b)
        self.assertEqual((caught.exception.code, caught.exception.path), ('ORDER', 'metadata.environments'))

    def test_full_verifier_rejects_arrow_descriptor_and_resolution_forgeries(self):
        p = recursive_program(); original = document(p)
        shape = next(r for r in original['shapes'] if r['source']['kind'] == 'canonical-arrow')
        sid, typ = shape['id'], shape['source']['type']
        resolution = next(r['id'] for r in original['type_resolutions'] if (r['type'], r['env']) == (typ, 0))
        contract = original['shape_typing'][sid]['contract']
        mutations = {
            'source-type': lambda d: d['shapes'][sid]['source'].update(type=0),
            'source-kind': lambda d: d['shapes'][sid].update(source={'kind': 'legacy', 'reference': '#i64'}),
            'child-rep': lambda d: d['shapes'][sid].update(argument_rep=sid),
            'scope': lambda d: d['shape_typing'][sid].update(scope=0),
            'ready': lambda d: d['representations'][sid].update(ready_kind='data'),
            'contract': lambda d: d['callable_contracts'][contract].update(result_identity='argument'),
            'resolution': lambda d: d['type_resolutions'][resolution].update(result=0),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                data = copy.deepcopy(original); mutate(data)
                with self.assertRaises(MetadataError): _verify_derived(p, data)


def nominal_goldens():
    output = []
    programs = [nominal_application(family=f, curried=c)[0]
                for f in (False, True) for c in (False, True)]
    p = view_program([['N0', 'N1'], ['N1', 'N0'], ['N2', 'N3'],
                      ['I', 'N4'], ['I', 'N5'], ['I', 'N6']], base='dead_parameter_two_complete_vectors')
    for i, name in enumerate(['\nBox', 'A', '"Quoted', '\\Slash', 'Ω', '\tTab', '界']):
        nominal(p, name, alias='N' + str(i))
    programs.append(p)
    for p in programs:
        result = check_metadata(p); statistics = dict(dict(result.report())['host_statistics'])
        output.append([result.metadata_sha256, statistics['metadata_records'], statistics['creation_units'],
                       statistics['work_units'], statistics['metadata_utf8_bytes']])
    return output


class NominalGoldenCompatibility(unittest.TestCase):
    # Captured before Stage23 edits, from the exact Stage22 copy, seed 0.
    GOLDENS = [
        ['bd5558f58f30d3aae24bf3e2357a9f6fd6e1d16e9cc8f5e8a54b9f92e36c817b', 367, 93964, 155838, 38992],
        ['725c77e27ee4f7ac3358d79c1936b904b640ddea704c8d6ec4c850cb2d26d15e', 599, 160145, 259300, 66093],
        ['4fb003a76eaa65230ff63f4980071226670fd51615319a7ee48e844fd297f243', 375, 95700, 157975, 39721],
        ['6d539d91f69e6bbca1763f6608582d24634c98d686f1009c6cfdccdb7ca34f98', 607, 161886, 261424, 66822],
        ['09f812fddca03da4a06ddf47f74bd24d5ebb250b566a24e65fa850c13a0824e1', 483, 119858, 178652, 47095],
    ]

    def test_prior_nominal_metadata_and_same_seed_work_are_exact(self):
        result = subprocess.run([sys.executable, '-B', __file__, '--nominal-goldens'],
            env=dict(os.environ, PYTHONHASHSEED='0', PYTHONDONTWRITEBYTECODE='1'),
            capture_output=True, text=True, timeout=30, check=True)
        self.assertEqual(result.stderr, '')
        self.assertEqual(json.loads(result.stdout), self.GOLDENS)


if __name__ == '__main__':
    if sys.argv[1:] == ['--nominal-goldens']:
        print(json.dumps(nominal_goldens()))
    else:
        unittest.main()
