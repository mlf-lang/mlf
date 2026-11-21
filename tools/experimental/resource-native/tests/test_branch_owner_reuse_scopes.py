#!/usr/bin/env python3
"""Synthetic host regressions for scoped and nested Int branch owner reuse.

These raw typed fixtures exercise planning, resource checking, metadata and
uncompiled emission only. They are not source qualification or native evidence.
The generic fixture is self-contained apart from the original owner-reuse
suite's raw constructors; no source-capture test helpers are imported.
"""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE / 'tests')]
import test_branch_owner_reuse as reuse
import planner_v8 as planner
from module_shared_transport import derive_shared_fragment
from resource_ir_v8.checker import check_resources, ResourceError
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime


def type_use(binder, argument):
    return {'tag': 'type_application', 'value': reuse.var(binder), 'witness': {
        'tag': 'then',
        'first': {'tag': 'inner', 'witness': {'tag': 'bottom', 'type': argument}},
        'second': {'tag': 'elim'}}}


def generic_fixture(*, ready=False):
    """Capture Int and Bool in one shared lambda used at both Bool and Int."""
    generic = {'tag': 'type_lambda', 'id': 100, 'bound': {'tag': 'bottom'},
               'body': reuse.lam(3, {'tag': 'var', 'id': 100},
                   reuse.conditional(reuse.var(4), reuse.var(1), reuse.lit(0)))}
    uses = reuse.add(
        reuse.app(type_use(2, reuse.BOOL), reuse.boolean(True)),
        reuse.app(type_use(2, reuse.INT), reuse.lit(0)))
    condition = reuse.prim(11, 'ltInt', reuse.var(1), reuse.lit(22))
    value = reuse.lit(21) if ready else reuse.add(reuse.lit(20), reuse.lit(1))
    return reuse.let(1, value, reuse.let(4, condition, reuse.let(2, generic, uses)))


def nested_fixture():
    return reuse.let(1, reuse.lit(42), reuse.conditional(
        reuse.boolean(True), reuse.var(1), reuse.conditional(
            reuse.boolean(False), reuse.var(1), reuse.var(1))))


def conditional_carrier(plan, row):
    carrier, = [c for c in plan['binding']['source_map']['carrier_map']
                if c['kind'] == 'conditional' and c['ir_code'] == row['retain']['name']]
    return carrier


class BranchOwnerReuseScopeTests(unittest.TestCase):
    def check_plan(self, raw, groups, count):
        original = copy.deepcopy(raw)
        fragment = derive_shared_fragment(raw)
        before = copy.deepcopy(fragment)
        default = planner.plan_fragment(raw, fragment=fragment, data_groups=groups)
        self.assertEqual(default, planner.plan_fragment(
            raw, fragment=fragment, data_groups=groups, reuse_int_branches=False))
        self.assertNotIn('optimizations', default['binding'])
        self.assertNotIn('branch_owner_reuse', default['binding']['source_map'])
        plan = planner.plan_fragment(
            raw, fragment=fragment, data_groups=groups, reuse_int_branches=True)
        mapping = plan['binding']['source_map']
        # Join normalized variables, carrier captures, exact retains and selector
        # arms using the maintained oracle, rather than merely counting rows.
        rows = reuse.audit_rows(fragment['raw_normalized'], plan)
        self.assertEqual(len(rows), count)
        self.assertEqual(fragment['raw_normalized'], original)
        self.assertEqual(fragment['steps'], [])
        self.assertEqual(default['binding']['source_map']['term_map'], mapping['term_map'])
        self.assertEqual(len(default['program']['codes']) - len(plan['program']['codes']), count)
        self.assertEqual(len(default['binding']['source_map']['allocation_map']) -
                         len(mapping['allocation_map']), count)
        for row in rows:
            source, = [t for t in mapping['term_map'] if t['source'] == row['source']]
            self.assertEqual(source, {'source': row['source'], 'tag': 'var',
                                      'role': 'ordinary', 'binder': row['binding']})
            carrier = conditional_carrier(plan, row)
            capture, = [c for c in carrier['mono_captures'] if c['binder'] == row['binding']]
            code = plan['program']['codes'][carrier['ir_code']]
            self.assertEqual(capture['layout'], '^' + row['logical_type'])
            self.assertEqual(code['captures'][row['source_owner']], {
                'layout': capture['layout'], 'relation': capture['relation']})
        checked = check_resources(plan['program'])
        metadata = check_metadata(plan['program'])
        emitted = emit_runtime(plan['program'])
        self.assertEqual(checked.sha256, plan['binding']['candidate_sha256'])
        self.assertEqual(metadata.ir_sha256, checked.sha256)
        self.assertEqual(json.loads(metadata.canonical_json), plan['program'])
        self.assertEqual(json.loads(emitted.canonical_ir_json), plan['program'])
        self.assertEqual(json.loads(emitted.metadata_json), json.loads(metadata.metadata_json))
        self.assertTrue(plan['binding']['fragment_only'])
        self.assertFalse(plan['binding']['source_admitted'])
        self.assertFalse(json.loads(emitted.manifest_json)['native_status']['callbacks_executed'])
        self.assertEqual(raw, original)
        self.assertEqual(fragment, before)
        self.assertEqual(fragment, derive_shared_fragment(raw))
        return fragment, plan, rows

    def check_generic(self, ready):
        for groups in (False, True):
            with self.subTest(data_groups=groups):
                fragment, plan, rows = self.check_plan(generic_fixture(ready=ready), groups, 1)
                row, = rows
                definition, = fragment['polymorphism']['definitions']
                scheme, = plan['binding']['source_map']['scheme_map']
                self.assertEqual((row['binding'], row['branch'], row['type_scope']),
                                 (1, 'conditional-then', 'S0'))
                self.assertEqual((scheme['definition'], scheme['binder'], scheme['scheme']),
                                 (definition['id'], definition['binding']['id'], row['type_scope']))
                self.assertEqual(scheme['rhs_cursor'], definition['rhs_cursor'])
                self.assertIn(row['type_scope'], plan['program']['schemes'])
                self.assertEqual(definition['free_term_bindings'], [1, 4])
                self.assertEqual([u['arguments'] for u in fragment['polymorphism']['uses']],
                                 [[reuse.BOOL], [reuse.INT]])
                scalar, condition = definition['captures']['scalars']
                self.assertEqual((scalar['binding'], scalar['type'], scalar['occurrences']),
                                 (1, reuse.INT, [row['source']]))
                self.assertEqual((condition['binding'], condition['type']), (4, reuse.BOOL))
                imports = {i['binding']: i for i in scheme['imports']}
                self.assertEqual(set(imports), {1, 4})
                generalize = reuse.instruction(plan['program'], scheme['generalize'])
                self.assertEqual(generalize['scheme'], row['type_scope'])
                for capture in (scalar, condition):
                    imported = imports[capture['binding']]
                    self.assertEqual(imported['occurrences'], capture['occurrences'])
                    self.assertEqual(generalize['imports'][imported['import']],
                                     {k: imported[k] for k in ('value', 'layout', 'relation')})
                # Check the actual pending thunk versus literal/ready scalar
                # publication and its capture contracts, not runtime strictness.
                producer, = [i for i in plan['program']['entry']
                             if i.get('out') == imports[1]['value']]
                self.assertEqual(producer['op'], 'scalar' if ready else 'thunk')
                carrier = conditional_carrier(plan, row)
                callback, = [c for c in plan['binding']['source_map']['carrier_map']
                             if c['kind'] == 'lambda' and c['source'] == scheme['rhs_cursor']]
                self.assertEqual(callback['type_scope'], row['type_scope'])
                function = plan['program']['functions'][callback['ir_code']]
                self.assertEqual(function['type_scope'], row['type_scope'])
                closure, = [i for i in generalize['body'] if i['op'] == 'closure']
                self.assertEqual(closure['function'], callback['ir_code'])
                publication, = [i for i in function['body'] if i.get('code') == carrier['ir_code']]
                for binder, relation in ((1, 'below' if ready and groups else 'down'), (4, 'down')):
                    outer, = [c for c in callback['mono_captures'] if c['binder'] == binder]
                    inner, = [c for c in carrier['mono_captures'] if c['binder'] == binder]
                    self.assertEqual((outer['relation'], inner['relation']), (relation, relation))
                    self.assertEqual(closure['captures'][outer['capture']], imports[binder]['import'])
                    self.assertEqual(publication['captures'][inner['capture']], outer['capture'])
                    self.assertEqual(function['captures'][outer['capture']],
                                     {k: outer[k] for k in ('layout', 'relation')})

    def test_generic_pending_scalar_capture(self):
        self.check_generic(ready=False)

    def test_generic_literal_ready_scalar_capture(self):
        self.check_generic(ready=True)

    def test_nested_conditional_retains(self):
        for groups in (False, True):
            with self.subTest(data_groups=groups):
                _, plan, rows = self.check_plan(nested_fixture(), groups, 3)
                self.assertEqual({tuple(r['source']['path']) for r in rows}, {
                    ('body', 'function', 'argument'),
                    ('body', 'argument', 'function', 'argument'),
                    ('body', 'argument', 'argument')})
                self.assertEqual({r['binding'] for r in rows}, {1})
                self.assertEqual({r['type_scope'] for r in rows}, {None})
                self.assertEqual(len({r['retain']['name'] for r in rows}), 2)
                self.assertEqual(len({r['retained_owner'] for r in rows}), 3)
                for row in rows:
                    capture, = conditional_carrier(plan, row)['mono_captures']
                    self.assertEqual(capture['relation'], 'below' if groups else 'down')

    def test_erased_generic_scope_is_rejected(self):
        for groups in (False, True):
            with self.subTest(data_groups=groups):
                raw = generic_fixture()
                plan = planner.plan_fragment(raw, data_groups=groups, reuse_int_branches=True)
                row, = plan['binding']['source_map']['branch_owner_reuse']
                plan['program']['codes'][row['retain']['name']]['type_scope'] = None
                with self.assertRaisesRegex(AssertionError, 'wrong type scope'):
                    reuse.audit_rows(derive_shared_fragment(raw)['raw_normalized'], plan)
                # This is also an actual invalid Code allocation scope, not just
                # a provenance mismatch that the resource checker cannot see.
                with self.assertRaises(ResourceError):
                    check_resources(plan['program'])

    def test_wrong_nested_carrier_is_rejected(self):
        for groups in (False, True):
            with self.subTest(data_groups=groups):
                raw = nested_fixture()
                plan = planner.plan_fragment(raw, data_groups=groups, reuse_int_branches=True)
                rows = plan['binding']['source_map']['branch_owner_reuse']
                outer, = [r for r in rows if r['source']['path'] == ['body', 'function', 'argument']]
                inner = next(r for r in rows if r['retain']['name'] != outer['retain']['name'])
                # Keep a real carrier and retain address, but join it to the
                # wrong raw branch. Valid IR alone cannot authenticate this map.
                outer['retain'] = copy.deepcopy(inner['retain'])
                with self.assertRaisesRegex(AssertionError, 'wrong source branch position'):
                    reuse.audit_rows(derive_shared_fragment(raw)['raw_normalized'], plan)


if __name__ == '__main__':
    unittest.main()
