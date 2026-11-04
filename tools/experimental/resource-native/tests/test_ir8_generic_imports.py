"""Stage24 synthetic host checks for explicit concrete scalar generic imports.

No compiler or native evaluator runs here. Boundary/Coverage is the complete
static premise closure of checked generated Code, including unused callbacks,
not observations and not an exhaustive native API/import-whitelist contract.
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
from resource_ir_v8.checker import check_resources, ResourceError
from resource_ir_v8.metadata import check_metadata, _verify_derived, NATIVE_TABLES
from resource_ir_v8.metadata_budget import MetadataError
from resource_ir_v8.provenance import CAPTURE_ORIGIN_CASES
from resource_ir_v8.runtime_emit import emit_runtime
from resource_ir_v8.runtime_emit_body import derive_plan
from resource_ir_v8.runtime_emit_budget import Budget, RuntimeEmissionError

CASES = json.loads((ROOT / 'tests/fixtures/ir8-metadata.json').read_text())['cases']


def raw(name='ready_shared_identity_two_views'):
    return json.loads(next(c['text'] for c in CASES if c['name'] == name))


def import_program(kind='i64', pending=True, entries=1):
    """Synthetic direct generic closure, independent parent/child scalar owners."""
    p = raw()
    ty = 'I' if kind == 'i64' else 'B'
    p['types']['AA']['result'] = ty
    p['signatures']['id']['result'] = '^' + ty
    p['functions']['id']['captures'] = {'captured': {'layout': '^' + ty, 'relation': 'down'}}
    p['functions']['id']['body'] = [{'op': 'drop', 'value': 'x'}, {'op': 'return', 'value': 'captured'}]
    initial = [{'op': 'scalar', 'out': 'bonus', 'in': 'home', 'kind': kind, 'value': 42 if kind == 'i64' else True}]
    if pending:
        p['signatures']['concrete'] = {'argument': '^' + ty, 'result': '^' + ty,
                                      'protocol': 'repeat', 'result_identity': 'unknown'}
        p['functions']['concrete'] = {'signature': 'concrete', 'parameter': 'x', 'captures': {},
                                     'type_scope': None, 'body': [{'op': 'return', 'value': 'x'}]}
        initial[0]['out'] = 'seed'
        initial += [
            {'op': 'closure', 'out': 'scalar_fn', 'in': 'home', 'function': 'concrete', 'captures': {}},
            {'op': 'application', 'out': 'bonus', 'in': 'home', 'function': 'scalar_fn', 'argument': 'seed'},
            {'op': 'drop', 'value': 'scalar_fn'}, {'op': 'drop', 'value': 'seed'}]
    p['entry'][1:1] = initial
    g = next(i for i in p['entry'] if i['op'] == 'generalize')
    names = ['import' + str(i).zfill(2) for i in range(entries)]
    g['imports'] = {n: {'value': 'bonus', 'layout': '^' + ty, 'relation': 'down'} for n in names}
    g['body'][0]['captures'] = {'captured': names[0] if names else 'missing'}
    g['body'][1:1] = [{'op': 'drop', 'value': n} for n in names]
    p['entry'].insert(-2, {'op': 'drop', 'value': 'bonus'})
    return p


def generalize(p):
    return next(i for i in p['entry'] if i['op'] == 'generalize')


def facts(p):
    return json.loads(check_resources(p).derived_json)


def intro_fact(d):
    return next(i for i in d['instructions'] if i['op'] == 'generalize')


class GenericImportTests(unittest.TestCase):
    def reject(self, p, code=None):
        with self.assertRaises(ResourceError) as caught:
            check_resources(p)
        if code:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_ready_pending_int_bool_preserve_actual_source_and_parent(self):
        for kind in ('i64', 'bool'):
            for pending in (False, True):
                with self.subTest(kind=kind, pending=pending):
                    p = import_program(kind, pending)
                    d = facts(p); g = intro_fact(d)
                    parent, alias = g['inputs'][1], g['outputs'][1]
                    self.assertEqual(parent['ready'], not pending)
                    self.assertEqual(alias['role'], ['imports', 'import00'])
                    for key in parent:
                        if key not in ('role', 'capability', 'storage'):
                            self.assertEqual(parent[key], alias[key], key)
                    self.assertNotEqual(parent['capability'], alias['capability'])
                    self.assertNotEqual(parent['storage'], alias['storage'])
                    drops = [i['inputs'][0] for i in d['instructions'] if i['op'] == 'drop']
                    self.assertTrue(any(x['capability'] == parent['capability'] for x in drops))
                    self.assertTrue(any(x['capability'] == alias['capability'] for x in drops))
                    prov = d['provenance'][alias['provenance']]['value']
                    self.assertEqual(prov['context'], {'kind': 'concrete'})
                    self.assertEqual(d['sites'][prov['site']]['category'], 'APPLICATION' if pending else 'SCALAR')
                    check_metadata(p); emit_runtime(p)

    def test_aliases_count_separately_and_canonical_order(self):
        p = import_program(entries=3)
        g = generalize(p); g['imports'] = dict(reversed(list(g['imports'].items())))
        row = intro_fact(facts(p))
        self.assertEqual([f['role'] for f in row['outputs'][1:]], [['imports', 'import0' + str(i)] for i in range(3)])
        self.assertEqual(len({f['node'] for f in row['outputs'][1:]}), 1)
        self.assertEqual(len({f['capability'] for f in row['outputs'][1:]}), 3)
        self.assertEqual(len({f['storage'] for f in row['outputs'][1:]}), 3)

    def test_64_entries_pass_65_and_empty_reject(self):
        p = import_program(pending=False, entries=64)
        self.assertEqual(len(intro_fact(facts(p))['outputs']), 65)
        emit_runtime(p)
        self.reject(import_program(entries=65), 'IMPORT_COUNT')
        self.reject(import_program(entries=0), 'IMPORT_COUNT')

    def test_exact_import_schema_names_and_relation(self):
        for mutation in ('extra', 'missing', 'relation', 'raw-layout', 'reserved', 'non-map'):
            p = import_program(); g = generalize(p); row = g['imports']['import00']
            if mutation == 'extra': row['unexpected'] = 1
            elif mutation == 'missing': del row['layout']
            elif mutation == 'relation': row['relation'] = 'same'
            elif mutation == 'raw-layout': row['layout'] = '#i64'
            elif mutation == 'reserved': g['imports']['$home'] = g['imports'].pop('import00')
            else: g['imports'] = []
            with self.subTest(mutation=mutation): self.reject(p)

    def test_wrong_scalar_type_and_non_scalar_types(self):
        p = import_program(); generalize(p)['imports']['import00']['layout'] = '^B'
        self.reject(p, 'TYPE')
        for ty in ('AA', 'A', 'N'):
            p = import_program()
            if ty == 'N':
                p['layouts']['Box'] = {}; p['types']['N'] = {'tag': 'closed', 'layout': 'Box'}
            generalize(p)['imports']['import00']['layout'] = '^' + ty
            with self.subTest(ty=ty):
                with self.assertRaises(ValueError): check_resources(p)

    def test_unknown_or_missing_parent_and_child_binding(self):
        p = import_program(); generalize(p)['imports']['import00']['value'] = 'absent'
        self.reject(p, 'NOT_LIVE')
        p = import_program(); del generalize(p)['imports']
        self.reject(p, 'NOT_LIVE')

    def test_loan_and_ticket_are_not_import_owners(self):
        p = import_program(); at = p['entry'].index(generalize(p))
        p['entry'].insert(at, {'op': 'borrow', 'out': 'loan', 'value': 'bonus'})
        generalize(p)['imports']['import00']['value'] = 'loan'
        self.reject(p, 'OWNERSHIP')
        p = import_program(pending=False)
        p['entry'][1] = {'op': 'hole', 'out': 'bonus', 'in': 'home', 'layout': '^I'}
        self.reject(p, 'GENERIC_IMPORT')

    def test_unspent_parent_loan_does_not_prevent_retain(self):
        p = import_program(); at = p['entry'].index(generalize(p))
        p['entry'].insert(at, {'op': 'borrow', 'out': 'loan', 'value': 'bonus'})
        p['entry'].insert(at + 2, {'op': 'end_borrow', 'value': 'loan'})
        check_resources(p)

    def test_forced_origin_is_not_guessed_concrete(self):
        p = import_program(); at = p['entry'].index(generalize(p))
        p['entry'].insert(at, {'op': 'force', 'out': 'forced', 'value': 'bonus'})
        generalize(p)['imports']['import00']['value'] = 'forced'
        self.reject(p, 'GENERIC_IMPORT')

    def test_parameter_and_foreign_capture_unknown_reject(self):
        for source in ('parameter', 'capture'):
            p = import_program(); g = generalize(p); p['entry'].remove(g)
            g['in'] = '$home'
            p['signatures']['foreign'] = {'argument': '^I', 'result': '^I', 'protocol': 'repeat', 'result_identity': 'unknown'}
            p['functions']['aa_foreign'] = {'signature': 'foreign', 'parameter': 'bonus' if source == 'parameter' else 'arg',
                'captures': {} if source == 'parameter' else {'bonus': {'layout': '^I', 'relation': 'down'}},
                'type_scope': None, 'body': [g, {'op': 'drop', 'value': 'shared'}, {'op': 'return', 'value': 'bonus'}]}
            with self.subTest(source=source): self.reject(p, 'GENERIC_IMPORT')

    def test_down_support_is_required(self):
        p = import_program(); at = p['entry'].index(generalize(p))
        p['entry'].insert(at, {'op': 'new_root', 'out': 'other', 'imports': []})
        generalize(p)['in'] = 'other'
        self.reject(p, 'UPWARD_SUPPORT')

    def test_parent_aliases_remain_owned_and_child_leaks_reject(self):
        p = import_program(); generalize(p)['body'] = [generalize(p)['body'][0], generalize(p)['body'][-1]]
        self.reject(p, 'UNDISCHARGED')
        p = import_program(); generalize(p)['body'].insert(1, {'op': 'retain', 'out': 'leaked', 'value': 'import00'})
        self.reject(p, 'UNDISCHARGED')

    def test_generic_application_cannot_publish_imported_scalar(self):
        p = import_program(); g = generalize(p)
        p['signatures']['scalar_neutral'] = {'argument': '^I', 'result': '^I', 'protocol': 'repeat', 'result_identity': 'unknown'}
        p['functions']['scalar_neutral'] = {'signature': 'scalar_neutral', 'parameter': 'q', 'captures': {}, 'type_scope': 'S', 'body': [{'op': 'return', 'value': 'q'}]}
        g['body'][0:0] = [
            {'op': 'closure', 'out': 'neutral', 'in': '$home', 'function': 'scalar_neutral', 'captures': {}},
            {'op': 'application', 'out': 'bad', 'in': '$home', 'function': 'neutral', 'argument': 'import00'},
            {'op': 'drop', 'value': 'bad'}, {'op': 'drop', 'value': 'neutral'}]
        self.reject(p, 'GENERIC_PUBLICATION')

    def test_generic_forbidden_memo_and_nested_introduction_remain_rejected(self):
        for instruction in ({'op': 'fill', 'hole': 'import00', 'value': 'import00'},
                            {'op': 'force', 'out': 'bad', 'value': 'import00'},
                            {'op': 'generalize', 'out': 'nested', 'in': '$home', 'scheme': 'S', 'body': []}):
            p = import_program(); generalize(p)['body'].insert(0, instruction)
            self.reject(p, 'OPCODE')

    def test_explicit_capture_union_and_copy_actual_acquisition(self):
        p = import_program(); d = facts(p); m = json.loads(check_metadata(p).metadata_json)
        imported = next((i, o) for i, o in enumerate(d['obligations']) if o['kind'] == 'generic_import')
        index, obligation = imported
        self.assertIsNone(obligation['host_site'])
        self.assertEqual([(r['side'], r['index']) for r in obligation['operands']], [('inputs', 0), ('inputs', 1), ('outputs', 1)])
        boundaries = [b for b in m['boundaries'] if b['key'].get('kind') == 'obligation' and b['key']['index'] == index]
        self.assertTrue(boundaries)
        self.assertTrue(all(b['access_rule'] == 'copy-actual' for b in boundaries))
        self.assertTrue(all('exact-mono-contract' not in b['guards'] and 'same-neutral-capsule' not in b['guards'] for b in boundaries))
        publications = [o for o in d['obligations'] if 'origin_cases' in o]
        self.assertTrue(publications)
        for o in publications:
            self.assertEqual(o['origin_cases'], list(CAPTURE_ORIGIN_CASES))
            self.assertNotIn('neutral_same_capsule', o['rules'])
        union = [b for b in m['boundaries'] if b['access_rule'].startswith('capture-')]
        self.assertTrue(any(b['access_rule'] == 'capture-project-or-identity' for b in union))
        for b in union:
            self.assertIn('same-neutral-capsule', b['guards']); self.assertIn('preserve-foreign-access', b['guards'])
        self.assertEqual(len(NATIVE_TABLES), 20)
        self.assertNotIn('boundaries', NATIVE_TABLES); self.assertNotIn('coverage', NATIVE_TABLES)
        self.assertTrue(all(set(i) == set(m['introductions'][0]) for i in m['introductions']))

    def test_identity_transport_preserves_actual_pending_origin(self):
        p = import_program(); d = facts(p); m = json.loads(check_metadata(p).metadata_json)
        alias = intro_fact(d)['outputs'][1]
        site = d['provenance'][alias['provenance']]['value']['site']
        accesses = [a for a in m['accesses'] if a['site'] == site]
        self.assertEqual(len(accesses), 1)
        a = accesses[0]
        self.assertEqual((a['origin_env'], a['use_env'], a['mode'], a['scheme']), (0, 0, 'MONO', None))
        self.assertEqual([t for t in m['transports'] if t['source_access'] == a['id']],
                         [{'id': next(t['id'] for t in m['transports'] if t['source_access'] == a['id']),
                           'source_access': a['id'], 'projection_env': None, 'result_access': a['id'], 'kind': 'identity'}])
        self.assertTrue(any(t['kind'] == 'project' for t in m['transports']))

    def test_emission_retains_after_begin_before_capture_and_drops_before_seal(self):
        p = import_program(entries=2); e = emit_runtime(p)
        m = json.loads(e.manifest_json)
        source = e.runtime_source
        begin = source.index('rt8_generic_begin(ctx,')
        seal = source.index('rt8_generic_seal(ctx,', begin)
        body = source[begin:seal]
        self.assertEqual(body.count('rt8_retain(ctx,'), 2)
        self.assertLess(body.index('rt8_retain(ctx,'), body.index('rt8_closure(ctx,'))
        self.assertEqual(body.count('rt8_drop(ctx,'), 2)
        self.assertNotIn('rt8_force(ctx,', body)
        self.assertTrue(m)

    def test_emitter_rejects_forged_initial_alias_facts(self):
        p = import_program(entries=2); d = facts(p); m = json.loads(check_metadata(p).metadata_json)
        for field in ('node', 'group', 'type', 'provenance', 'ready', 'capability', 'storage', 'role', 'extra', 'missing'):
            changed = copy.deepcopy(d); g = intro_fact(changed); alias = g['outputs'][1]
            if field in ('capability', 'storage'): alias[field] = g['inputs'][1][field]
            elif field == 'role': alias[field] = ['imports', 'wrong']
            elif field == 'extra': alias['unexpected'] = None
            elif field == 'missing': g['outputs'].pop()
            elif field == 'ready': alias[field] = not alias[field]
            else: alias[field] += 1
            with self.subTest(field=field), self.assertRaises(RuntimeEmissionError): derive_plan(p, m, changed, Budget())
        changed = copy.deepcopy(d); g = intro_fact(changed)
        g['outputs'][2]['capability'] = g['outputs'][1]['capability']
        with self.assertRaises(RuntimeEmissionError): derive_plan(p, m, changed, Budget())

    def test_emitter_authenticates_declared_import_type_and_relation(self):
        p = import_program(); d = facts(p); m = json.loads(check_metadata(p).metadata_json)
        for key, value in (('layout', '^B'), ('layout', '#i64'), ('relation', 'same')):
            bad = copy.deepcopy(p); generalize(bad)['imports']['import00'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeEmissionError):
                derive_plan(bad, m, d, Budget())

    def test_metadata_mutation_does_not_authorize_extra_edges(self):
        p = import_program(); m = json.loads(check_metadata(p).metadata_json)
        for mutation in ('drop-neutral', 'drop-concrete', 'wrong-union', 'copy-claims-type'):
            bad = copy.deepcopy(m)
            union = next(b for b in bad['boundaries'] if b['access_rule'] == 'capture-neutral-or-concrete-scalar')
            if mutation == 'drop-neutral': union['guards'].remove('same-neutral-capsule')
            elif mutation == 'drop-concrete': union['guards'].remove('preserve-foreign-access')
            elif mutation == 'wrong-union': union['access_rule'] = 'publish-by-host-origin'
            else:
                copy_row = next(b for b in bad['boundaries'] if b['access_rule'] == 'copy-actual' and b['key']['kind'] == 'obligation')
                copy_row['guards'].append('exact-mono-contract')
            with self.subTest(mutation=mutation), self.assertRaises(MetadataError): _verify_derived(p, bad)

    def test_retained_parent_alias_and_child_loan_preserve_provenance(self):
        p = import_program(); g = generalize(p); at = p['entry'].index(g)
        p['entry'].insert(at, {'op': 'retain', 'out': 'parent_alias', 'value': 'bonus'})
        g['imports']['import00']['value'] = 'parent_alias'
        p['entry'].insert(at + 2, {'op': 'drop', 'value': 'parent_alias'})
        g['body'][0:0] = [
            {'op': 'borrow', 'out': 'loan', 'value': 'import00'},
            {'op': 'retain', 'out': 'copy', 'value': 'loan'},
            {'op': 'end_borrow', 'value': 'loan'}]
        g['body'][3]['captures']['captured'] = 'copy'
        g['body'].insert(-1, {'op': 'drop', 'value': 'copy'})
        d = facts(p); original = intro_fact(d)['inputs'][1]
        publication = next(o for o in d['obligations'] if 'origin_cases' in o)
        ref = publication['operands'][1]
        captured = d['instructions'][ref['instruction']][ref['side']][ref['index']]
        self.assertEqual((original['node'], original['provenance'], original['type']),
                         (captured['node'], captured['provenance'], captured['type']))
        emit_runtime(p)

    def test_scheme_is_not_an_import_value(self):
        p = import_program(); g = generalize(p); at = p['entry'].index(g)
        p['types']['II'] = {'tag': 'arrow', 'argument': 'I', 'result': 'I', 'protocol': 'repeat', 'result_identity': 'unknown'}
        p['schemes']['T'] = {'body': 'II', 'parameters': 1}
        p['signatures']['targetT'] = {'argument': '^I', 'result': '^I', 'protocol': 'repeat', 'result_identity': 'unknown'}
        p['functions']['targetT'] = {'signature': 'targetT', 'parameter': 'q', 'captures': {}, 'type_scope': 'T', 'body': [{'op': 'return', 'value': 'q'}]}
        p['entry'].insert(at + 1, {'op': 'generalize', 'out': 'other', 'in': 'home', 'scheme': 'T',
            'imports': {'bad': {'value': 'shared', 'layout': '^I', 'relation': 'down'}},
            'body': [{'op': 'closure', 'out': 'f', 'in': '$home', 'function': 'targetT', 'captures': {}},
                     {'op': 'drop', 'value': 'bad'}, {'op': 'seal', 'value': 'f'}]})
        self.reject(p, 'SCHEME_VALUE')

    def test_transitive_and_unused_generic_callbacks_keep_capture_union(self):
        p = import_program()
        p['types']['II'] = {'tag': 'arrow', 'argument': 'I', 'result': 'I', 'protocol': 'repeat', 'result_identity': 'unknown'}
        p['types']['AA']['result'] = 'II'; p['signatures']['id']['result'] = '^II'
        p['signatures']['inner'] = {'argument': '^I', 'result': '^I', 'protocol': 'repeat', 'result_identity': 'unknown'}
        inner = {'signature': 'inner', 'parameter': 'q', 'captures': {'captured': {'layout': '^I', 'relation': 'down'}},
                 'type_scope': 'S', 'body': [{'op': 'drop', 'value': 'q'}, {'op': 'return', 'value': 'captured'}]}
        p['functions']['inner'] = inner
        p['functions']['unused'] = copy.deepcopy(inner)
        p['functions']['id']['body'] = [
            {'op': 'drop', 'value': 'x'},
            {'op': 'closure', 'out': 'inner', 'in': '$home', 'function': 'inner', 'captures': {'captured': 'captured'}},
            {'op': 'drop', 'value': 'captured'}, {'op': 'return', 'value': 'inner'}]
        p['entry'][-1:] = [{'op': 'drop', 'value': 'answer'}, {'op': 'finish'}]
        d = facts(p); m = json.loads(check_metadata(p).metadata_json)
        self.assertEqual(len([o for o in d['obligations'] if 'origin_cases' in o]), 2)
        for name in ('id', 'inner', 'unused'):
            code = next(c for c in m['codes'] if c['name'] == name)
            executions = {c['id'] for c in m['code_executions'] if c['code'] == code['id']}
            entries = [b for b in m['boundaries'] if b['key']['kind'] == 'entry'
                       and b['key']['code_execution'] in executions and b['key']['role'] == 'capture']
            self.assertTrue(any(b['access_rule'] == 'capture-project-or-identity' for b in entries))
            self.assertTrue(any(b['access_rule'] == 'capture-neutral-or-concrete-scalar' for b in entries))
        emit_runtime(p)

    def test_same_home_capture_cannot_claim_below_relation(self):
        p = import_program(); p['functions']['id']['captures']['captured']['relation'] = 'below'
        self.reject(p, 'CAPTURE_RELATION')
        p = import_program(); g = generalize(p)
        g['body'].insert(0, {'op': 'new_below', 'out': 'child', 'ceiling': '$home', 'imports': ['import00']})
        self.reject(p, 'STRICT_IMPORT')

    def test_no_import_resource_metadata_and_emitter_goldens(self):
        baseline = os.environ.get('IR8_GENERIC_IMPORT_BASELINE')
        if not baseline: self.skipTest('set IR8_GENERIC_IMPORT_BASELINE to retained Stage23 resource-native root')
        script = '''import json,sys
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime
p=json.load(sys.stdin);r=check_resources(p);m=check_metadata(p);e=emit_runtime(p)
print(json.dumps([r.canonical_json,r.derived_json,r.report(),m.metadata_json,m.report(),e.runtime_header,e.runtime_source,e.packet_header,e.packet_source,e.manifest_json,e.statistics],sort_keys=True))
'''
        for name in ('ready_shared_identity_two_views', 'curried_const_complete_ib_bi_views', 'scoped_intermediate_dead_parameter_substitution'):
            p = raw(name); r = check_resources(p); m = check_metadata(p); e = emit_runtime(p)
            env = dict(os.environ, PYTHONPATH=baseline, PYTHONDONTWRITEBYTECODE='1', PYTHONHASHSEED='0')
            old = subprocess.run([sys.executable, '-B', '-c', script], input=json.dumps(p), text=True,
                                 capture_output=True, env=env, timeout=60, check=True)
            env['PYTHONPATH'] = str(ROOT)
            current = subprocess.run([sys.executable, '-B', '-c', script], input=json.dumps(p), text=True,
                                     capture_output=True, env=env, timeout=60, check=True)
            self.assertEqual(json.loads(current.stdout), json.loads(old.stdout), name)


if __name__ == '__main__': unittest.main()
