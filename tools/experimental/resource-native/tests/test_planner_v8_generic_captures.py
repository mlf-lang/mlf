"""Explicit generalization imports: host plan/check/emit, never native runs."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE / 'tests')]
import module_shared_transport as m
import planner_v8 as p
import test_module_shared_transport as raw
import test_module_shared_generic_captures as source
import test_planner_v8 as legacy
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.runtime_emit import emit_runtime


def target(plan):
    row, = plan['binding']['source_map']['scheme_map']
    intro = plan['program']['entry'][row['generalize']['segments'][0]]
    return row, intro


class GenericImportPlannerTests(unittest.TestCase):
    def checked(self, tree, groups=False, emit=False):
        original = copy.deepcopy(tree)
        plan = p.plan_fragment(tree, data_groups=groups)
        self.assertEqual(original, tree)
        check_resources(plan['program'])
        if emit:
            result = emit_runtime(plan['program'])
            check_metadata(plan['program'])
            self.assertEqual(json.loads(result.canonical_ir_json), plan['program'])
        return plan

    def test_pending_ready_int_bool_checked_in_both_placements(self):
        for boolean in (False, True):
            for ready in (False, True):
                for groups in (False, True):
                    with self.subTest(boolean=boolean,ready=ready,groups=groups):
                        plan = self.checked(source.fixture(boolean,ready), groups)
                        row, intro = target(plan)
                        alias, = intro['imports']
                        self.assertEqual(intro['imports'][alias]['relation'],'down')
                        scalar = plan['program']['types'][intro['imports'][alias]['layout'][1:]]
                        self.assertEqual(scalar,{'tag':'closed','layout':'#bool' if boolean else '#i64'})
                        self.assertEqual(row['imports'][0]['import'],alias)
                        self.assertFalse(any(x['op']=='force' for x in intro['body']))
                        closure, = [x for x in intro['body'] if x['op']=='closure']
                        self.assertEqual(list(closure['captures'].values()),[alias])
                        self.assertIn({'op':'drop','value':alias}, intro['body'][:-1])
                        self.assertEqual(intro['body'][-1],{'op':'seal','value':closure['out']})

    def test_shared_rhs_placement_has_full_support_and_safe_fallback(self):
        for ready in (False,True):
            plan = self.checked(source.fixture(ready=ready), True)
            _,intro = target(plan)
            placement, = [r for r in plan['binding']['source_map']['group_map'] if r['kind']=='shared-rhs']
            self.assertEqual([r['reference'] for r in placement['support']],
                             [r['value'] for r in intro['imports'].values()])
            self.assertEqual([r['strict'] for r in placement['support']],[ready])
            self.assertEqual(placement['strategy'],'fresh-below' if ready else 'same-home')
            self.assertEqual(placement['reason'],'all-support-strict' if ready else 'support-only-down')

    def test_parent_owner_remains_until_ordinary_lexical_release(self):
        plan = self.checked(source.fixture())
        row,intro = target(plan)
        at = row['generalize']['segments'][0]
        original, = [v['value'] for v in intro['imports'].values()]
        self.assertFalse(any(x['op']=='drop' and x['value']==original for x in plan['program']['entry'][:at]))
        self.assertTrue(any(x['op']=='drop' and x['value']==original for x in plan['program']['entry'][at+1:]))
        self.assertFalse(any(x.get('out') in intro['imports'] for x in plan['program']['entry']))

    def test_two_lexical_aliases_are_separate_import_acquisitions(self):
        plan = self.checked(source.fixture(aliases=True), emit=True)
        row,intro = target(plan)
        self.assertEqual([r['binding'] for r in row['imports']],[1,4])
        self.assertEqual(len(intro['imports']),2)
        self.assertEqual(list(intro['imports']),sorted(intro['imports']))
        parents = [x['value'] for x in intro['imports'].values()]
        self.assertEqual(len(set(parents)),2)
        entries = plan['program']['entry']
        alias_op = next(x for x in entries if x.get('out')==parents[1])
        self.assertEqual(alias_op, {'op':'retain','out':parents[1],'value':parents[0]})

    def test_mixed_and_transitive_capture_carriers_check_and_emit(self):
        for tree in (source.fixture(mixed=True),source.fixture(nested=True)):
            for groups in (False,True):
                plan = self.checked(tree,groups,emit=True)
                self.assertTrue(target(plan)[1]['imports'])
                if tree==source.fixture(nested=True):
                    self.assertEqual(sum(bool(c['mono_captures']) for c in plan['binding']['source_map']['carrier_map']),2)

    def test_missing_extra_wrong_type_and_occurrence_manifests_rejected(self):
        tree = source.fixture(); fragment = m.derive_shared_fragment(tree)
        changes = [lambda d:d.pop('captures'),lambda d:d.update(free_term_bindings=[]),
            lambda d:d['captures'].update(policy='foreign'),
            lambda d:d['captures']['scalars'][0].update(type=raw.B),
            lambda d:d['captures']['scalars'][0].update(binding=True),
            lambda d:d['captures']['scalars'][0]['occurrences'].clear(),
            lambda d:d['captures']['scalars'].append(copy.deepcopy(d['captures']['scalars'][0]))]
        for change in changes:
            forged=copy.deepcopy(fragment);change(forged['polymorphism']['definitions'][0])
            with self.assertRaises(m.SharedTransportError):
                p.plan_fragment(tree,fragment=forged)
            with self.assertRaises(p.PlanningError):
                p.Planner(forged).finish()

    def test_scalar_reference_and_concrete_top_level_are_required(self):
        fragment=m.derive_shared_fragment(source.fixture())
        for ref in (p.Reference('foreign',p.SCALARS['Bool']),p.SchemeReference('shared',0),None):
            planner=p.Planner(fragment)
            with self.assertRaises(p.PlanningError):
                planner.generalized_imports(fragment['polymorphism']['definitions'][0],{1:ref},p.Block('entry',None,[]),None)
        planner=p.Planner(fragment)
        with self.assertRaises(p.PlanningError):
            planner.generalized_imports(fragment['polymorphism']['definitions'][0],
                {1:p.Reference('ordinary',p.SCALARS['Int'])},p.Block('function','F',[]),None)

    def test_emitter_retains_alias_after_begin_and_before_capture(self):
        plan=self.checked(source.fixture())
        emission=emit_runtime(plan['program'])
        text=emission.runtime_source
        start=text.index('rt8_generic_begin(')
        retain=text.index('rt8_retain(',start)
        end=text.index('rt8_generic_seal(',start)
        self.assertLess(start,retain)
        self.assertLess(retain,end)
        self.assertNotIn('rt8_force(',text[start:end])

    def test_no_import_instruction_and_source_map_shape_remain_unchanged(self):
        for groups in (False,True):
            plan=self.checked(legacy.pending_shared(),groups)
            row,intro=target(plan)
            self.assertNotIn('imports',row)
            self.assertNotIn('imports',intro)

    def test_former_scalar_capture_negative_is_now_a_checked_positive(self):
        tree = legacy.let(9,legacy.lit(),legacy.let(1,
            legacy.prefix([100],legacy.lam(2,legacy.ty(100),legacy.var(9))),
            legacy.app(legacy.use(1,legacy.I),legacy.lit())))
        self.assertTrue(target(self.checked(tree))[1]['imports'])

    def test_actual_int_and_bool_both_placements_check_emit(self):
        for case in source.PINS:
            _,_,captured=source.retained(self,case)
            raw_tree=captured['projection']['projected_annotated']
            for groups in (False,True):
                plan=self.checked(raw_tree,groups,emit=True)
                row,intro=target(plan)
                self.assertEqual(len(row['imports']),1)
                self.assertEqual(len(plan['program']['schemes']),1)
                self.assertEqual(len(plan['program']['instantiations']),2)
                self.assertEqual(len(intro['imports']),1)

    def test_frozen_stage23_full_plans_and_generated_bytes_are_exact(self):
        root = os.environ.get('IR8_ARROW_ARGUMENTS_ROOT')
        if root is None:
            self.skipTest('set IR8_ARROW_ARGUMENTS_ROOT for frozen Stage23 goldens')
        from test_planner_v8_nominal_callable_captures import files
        root = Path(root)
        for case in ('shared-id-arrow','shared-apply-arrow','shared-apply-instance','shared-id-instance'):
            capture = root/'portable-source01'/case/case/'capture.stdout'
            tree = json.loads(capture.read_bytes())['projection']['projected_annotated']
            for mode in ('coarse','groups'):
                directory = root/'native-matrix01'/case/mode
                expected = json.loads((directory/'planned.json').read_bytes())
                actual = self.checked(tree,mode=='groups')
                self.assertEqual(actual,expected)
                emitted = emit_runtime(actual['program'])
                for name, blob in files(emitted).items():
                    self.assertEqual(blob,(directory/name).read_bytes())


if __name__ == '__main__':
    unittest.main()
