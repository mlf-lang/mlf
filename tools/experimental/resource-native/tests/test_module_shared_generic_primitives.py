"""Closed scalar computations in generic lambdas: host replay, not native proof."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE/'tests')]
import module_shared_transport as m
import test_module_shared_transport as f
import test_module_shared_generic_captures as old
from source_capture_v8 import verify_capture

PINS = {
 'mixed-scalar': ('e60bc154bdf57c457d4ca277dd019cb1f4acc6087e628e19e7c2aecc517a5365',
                  '5ed38b6d70be7ebeca0c3b61d2c32b3db06c6e30a18d531d1c29e9ebbda4e54b', 2),
 'alias-scalar': ('fd4a32addd4afc6c7ed531cdd4a8260a1d53b33a1fa9167de7b8161afdbd83fa',
                  '7056475494d7be530425f132bc02452ffafc7bd8bac91c1d6407ed4edb18ae1a', 0),
}


def fixture(code=8, label='addInt', conditional=False, aliases=False, nested=False, boolean=False):
    body = f.app(f.app(f.prim(code,label),f.var(1)), f.var(4) if aliases else f.lit(0))
    if conditional:
        body = f.choose(f.var(4), f.var(1), f.lit(0))
    if nested:
        body = f.add(body, f.add(f.lit(0),f.var(1)))
    root = f.let(2,f.tabs(100,f.lam(3,f.tv(100),body)),
        f.choose(f.app(f.use(2,f.B),f.boolean()),f.lit(42),f.lit(0)) if boolean else
        f.add(f.app(f.use(2,f.B),f.boolean()),f.app(f.use(2,f.I),f.lit(0))))
    if conditional:
        root = f.let(4,f.app(f.app(f.prim(11,'ltInt'),f.var(1)),f.lit(22)),root)
    elif aliases:
        root = f.let(4,f.var(1),root)
    return f.let(1,f.add(f.lit(20),f.lit(1)),root)


def retained(test, case):
    setting=os.environ.get('IR8_GENERIC_CAPTURE_ROOT')
    if setting is None: test.skipTest('set IR8_GENERIC_CAPTURE_ROOT for original diagnostics')
    root=Path(setting); path=root/('capture-'+case+'01')/'capture.stdout'
    data=path.read_bytes(); test.assertEqual(hashlib.sha256(data).hexdigest(),PINS[case][0])
    return root,path,json.loads(data)


class GenericPrimitiveSourceTests(unittest.TestCase):
    def reject(self, tree, code=None):
        with self.assertRaises(m.SharedTransportError) as caught:
            m.derive_shared_fragment(tree)
        if code is not None: self.assertEqual(caught.exception.code,code,str(caught.exception))
        return caught.exception

    def test_all_five_exact_primitives_and_int_conditional(self):
        for code,label in ((8,'addInt'),(9,'subInt'),(10,'eqInt'),(11,'ltInt'),(14,'mulInt')):
            tree=fixture(code,label,boolean=code in (10,11)); before=copy.deepcopy(tree)
            out=m.derive_shared_fragment(tree)
            self.assertEqual(tree,before); self.assertEqual(out['raw_normalized'],tree)
            self.assertEqual((out['policy'],out['steps']),(m.POLICY,[]))
            self.assertEqual(out['polymorphism']['definitions'][0]['free_term_bindings'],[1])
        self.assertEqual(m.derive_shared_fragment(fixture(conditional=True))['checked_type'],f.I)

    def test_aliases_nested_computations_and_all_dependencies_preserved(self):
        for tree in (fixture(aliases=True),fixture(nested=True),fixture(conditional=True)):
            out=m.derive_shared_fragment(tree); d,=out['polymorphism']['definitions']
            self.assertEqual(d['captures']['policy'],m.GENERIC_CAPTURE_POLICY)
            self.assertEqual([x['binding'] for x in d['captures']['scalars']],d['free_term_bindings'])
            self.assertEqual(out['raw_normalized'],tree)
            self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[f.B],[f.I]])

    def test_no_import_constant_computation_is_source_only_admission(self):
        tree=f.let(2,f.tabs(100,f.lam(3,f.tv(100),f.add(f.lit(20),f.lit(22)))),
                   f.app(f.use(2,f.I),f.lit(0)))
        out=m.derive_shared_fragment(tree); d,=out['polymorphism']['definitions']
        self.assertNotIn('captures',d)
        self.assertEqual(d['free_term_bindings'],[])

    def test_bare_partial_and_aliased_primitives_reject(self):
        for body in (f.prim(8,'addInt'),f.app(f.prim(8,'addInt'),f.var(1)),
                     f.let(8,f.prim(8,'addInt'),f.app(f.app(f.var(8),f.var(1)),f.lit(0)))):
            tree=old.fixture(); tree['body']['value']['body']['body']=body
            # Bare/partial arrows need a closed final source use to isolate admission.
            if body['tag']!='let': tree['body']['body']=f.lit(42)
            self.reject(tree,'PRIMITIVE')

    def test_wrong_id_name_type_argument_and_operand_reject(self):
        for head,code in ((f.prim(8,'mulInt'),'SCHEMA'),(f.prim(999,'addInt'),'SCHEMA'),
                          (f.prim(8,'addInt',[f.I]),'PRIMITIVE')):
            tree=fixture(); tree['body']['value']['body']['body']['function']['function']=head
            self.reject(tree,code)
        tree=fixture(); tree['body']['value']['body']['body']['argument']=f.boolean()
        self.reject(tree,'TYPE')

    def test_rigid_operand_and_conditional_rigid_result_reject(self):
        tree=fixture(); tree['body']['value']['body']['body']['argument']=f.var(3)
        self.reject(tree,'TYPE')
        body=f.app(f.app(f.app(f.prim(13,'ifThenElse',[f.tv(100)]),f.boolean()),f.var(3)),f.var(3))
        tree=f.let(2,f.tabs(100,f.lam(3,f.tv(100),body)),f.app(f.use(2,f.I),f.lit()))
        self.reject(tree,'PRIMITIVE')

    def test_conditional_bool_result_remains_outside_int_result_scope(self):
        body=f.app(f.app(f.app(f.prim(13,'ifThenElse',[f.B]),f.var(1)),f.boolean()),f.boolean(False))
        tree=f.let(1,f.boolean(),f.let(2,f.tabs(100,f.lam(3,f.tv(100),body)),
            f.choose(f.app(f.use(2,f.I),f.lit(0)),f.lit(42),f.lit(0))))
        self.reject(tree,'PRIMITIVE')

    def test_closed_parameter_and_full_dead_coordinates_preserved(self):
        rhs=f.tabs(100,f.tabs(101,f.lam(3,f.I,f.add(f.var(3),f.var(1)))))
        tree=f.let(1,f.lit(21),f.let(2,rhs,f.add(
            f.app(f.use(2,f.B,f.I),f.lit(0)),f.app(f.use(2,f.I,f.B),f.lit(0)))))
        out=m.derive_shared_fragment(tree)
        self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[f.B,f.I],[f.I,f.B]])
        self.assertEqual(out['raw_normalized'],tree)

    def test_closed_callable_dependency_remains_forbidden(self):
        tree=old.fixture()
        tree['body']['value']['body']['body']=f.lam(7,f.arr(f.I,f.I),f.add(f.app(f.var(7),f.lit(0)),f.var(1)))
        tree['body']['body']=f.lit()
        self.reject(tree,'CAPTURE')

    def test_non_direct_and_non_top_level_roots_reject(self):
        tree=fixture(); rhs=tree['body']['value']; lam=rhs['body']
        rhs['body']=f.app(f.lam(7,f.arr(f.tv(100),f.I),f.var(7)),lam)
        self.reject(tree,'CAPTURE')
        tree=f.app(f.lam(9,f.I,fixture()),f.lit())
        self.reject(tree,'CAPTURE')
        # Also reject a closed non-direct root without any outer capture.
        lam=f.lam(3,f.tv(100),f.add(f.lit(20),f.lit(22)))
        tree=f.let(2,f.tabs(100,f.app(f.lam(7,f.arr(f.tv(100),f.I),f.var(7)),lam)),
                   f.app(f.use(2,f.I),f.lit()))
        self.reject(tree,'FRAGMENT')

    def test_import_bound_counts_lexical_aliases(self):
        def tree(count):
            def total(ids):
                if len(ids)==1:return f.var(ids[0])
                middle=len(ids)//2;return f.add(total(ids[:middle]),total(ids[middle:]))
            out=f.let(1002,f.tabs(1000,f.lam(1001,f.tv(1000),total(list(range(1,count+1))))),
                      f.app(f.use(1002,f.I),f.lit()))
            for i in reversed(range(1,count+1)):out=f.let(i,f.lit(i),out)
            return out
        admitted=m.derive_shared_fragment(tree(64))
        self.assertEqual(len(admitted['polymorphism']['definitions'][0]['captures']['scalars']),64)
        self.reject(tree(65),'LIMIT')

    def test_actual_original_replay_checks_and_preserved_refusals(self):
        for case in PINS:
            root,path,capture=retained(self,case)
            original_record=(path.parent/'verification.json').read_bytes()
            historical=json.loads(original_record)
            self.assertFalse(historical['fragment_admitted'])
            self.assertEqual(historical['fragment_error']['code'],'CAPTURE')
            out=m.derive_shared_fragment(capture['projection']['projected_annotated'])
            for key in ('policy','steps','raw_normalized'):
                self.assertEqual(out[key],capture['normalization'][key])
            self.assertEqual(len(out['steps']),PINS[case][2])
            self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[f.B],[f.I]])
            rows=out['polymorphism']['definitions'][0]['captures']['scalars']
            self.assertEqual([r['type'] for r in rows],[f.I,f.B] if case=='mixed-scalar' else [f.I,f.I])
            report=verify_capture(path,fixture_root=root/'inputs'/case,entry='main.emlf',
                expected_source_hashes={'main.emlf':PINS[case][1],
                'SharedPoly.emlf':'50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'},
                expected_capture_sha256=PINS[case][0])
            self.assertTrue(report['fragment_admitted'])
            self.assertEqual(report['normalization_replay'],'all exact independent fields match')
            self.assertFalse(report['source_admitted']);self.assertFalse(report['native_admitted'])
            self.assertEqual((path.parent/'verification.json').read_bytes(),original_record)

    def test_unchanged_old_no_effect_replay(self):
        for case in old.PINS:
            _,_,capture=old.retained(self,case)
            out=m.derive_shared_fragment(capture['projection']['projected_annotated'])
            for key in ('policy','steps','raw_normalized'):
                self.assertEqual(out[key],capture['normalization'][key])


if __name__=='__main__':unittest.main()
