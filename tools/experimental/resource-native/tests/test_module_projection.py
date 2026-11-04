"""Synthetic projection replay controls, plus optional pinned genuine RAW evidence.
No ordinary compiler, model/native runner, C build or source evaluation is called.
Raw grammar validation is intentionally NOT a substitute for ordinary typechecking.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import module_projection as p


def name(i, hint=None):
    return {'id':i, 'hint':hint if hint is not None else 'n'+str(i)}


def typ(n='Int'):
    return {'tag':'constructor', 'name':n, 'arguments':[]}


def lit(n):
    return {'tag':'int64', 'value':n}


def var(i, hint=None):
    return {'tag':'var', 'name':name(i, hint)}


def lam(i, body, hint=None):
    return {'tag':'lambda', 'parameter':name(i,hint), 'parameter_type':typ(), 'body':body}


def app(f, a):
    return {'tag':'application', 'function':f, 'argument':a}


def let(i, value, body, hint=None):
    return {'tag':'let', 'name':name(i,hint), 'value':value, 'body':body}


def rec(entries, body):
    return {'tag':'letrec','bindings':[{'name':name(i),'type':typ(),'value':v}for i,v in entries],'body':body}


def case(subject, alts):
    return {'tag':'case','scrutinee':subject,'result_type':typ(),'alternatives':[{'pattern':pattern,'body':body}for pattern,body in alts]}


def ctor_pattern(n='Box', ids=()):
    return {'tag':'constructor','constructor':n,'fields':[None if i is None else name(i)for i in ids]}


def default_pattern(i=None):
    return {'tag':'default','binder':None if i is None else name(i)}


def declaration():
    return {'tag':'data','name':'Box','parameters':[],
            'constructors':[{'name':'Box','fields':[{'tag':'applied','name':'Int','arguments':[]},
                                                      {'tag':'applied','name':'Bool','arguments':[]}]}]}


def declared(body):
    return {'tag':'with_data','declarations':[declaration()],'body':body}


def replay(original):
    erased=p.erase_total(original)
    projected,steps=p.project_typed(original)
    projected_erased,other=p.project_erased(erased)
    result=p.replay_projection(original,erased,projected,projected_erased,steps)
    return projected,steps,result


class SyntaxTests(unittest.TestCase):
    def test_all_fifteen_term_constructors_lossless(self):
        proof={'tag':'refl'}
        terms=[var(1),lam(1,var(1)),app(lit(1),lit(2)),
               {'tag':'type_lambda','id':1,'bound':{'tag':'bottom'},'body':lit(0)},
               {'tag':'type_application','value':lit(0),'witness':proof},
               let(1,lit(1),var(1)),rec([(1,var(1))],var(1)),lit(-(1<<63)),
               {'tag':'double','bits_i64':-(1<<63)},{'tag':'bool','value':True},
               {'tag':'string','value':'a\n\x00 \U0001f600'},
               {'tag':'primitive','id':54,'name':'seq','arguments':[typ()]},
               {'tag':'constructor','name':'()','arguments':[]},
               case(lit(0),[(default_pattern(1),var(1))]),declared(lit(42))]
        self.assertEqual(len({t['tag']for t in terms}),15)
        for term in terms:
            with self.subTest(tag=term['tag']):
                p.validate_raw_term(term)
                erased=p.erase_total(term)
                p.validate_raw_term(erased,erased=True)

    def test_all_nine_proof_forms_and_seven_types(self):
        types=[{'tag':'var','id':3},{'tag':'bottom'},
               {'tag':'bottom_kind','kind':{'tag':'arrow','from':{'tag':'star'},'to':{'tag':'star'}}},
               {'tag':'arrow','from':typ(),'to':typ()},typ(),
               {'tag':'apply','function':typ('F'),'argument':typ()},
               {'tag':'forall','id':2,'bound':{'tag':'bottom'},'body':{'tag':'var','id':2}}]
        proofs=[{'tag':'refl'},{'tag':'bottom','type':typ()}, {'tag':'hyp','id':3},
                {'tag':'inner','witness':{'tag':'refl'}},
                {'tag':'outer','id':4,'witness':{'tag':'elim'}},{'tag':'elim'},
                {'tag':'intro','id':5},{'tag':'intro_kind','id':6,'kind':{'tag':'star'}},
                {'tag':'then','first':{'tag':'refl'},'second':{'tag':'elim'}}]
        for ty in types:
            p.validate_raw_term({'tag':'type_lambda','id':7,'bound':ty,'body':lit(42)})
        for proof in proofs:
            p.validate_raw_term({'tag':'type_application','value':lit(42),'witness':proof})
        bad={'tag':'type_application','value':lit(42),'witness':{'tag':'assumed_refl'}}
        with self.assertRaises(p.ProjectionError):p.validate_raw_term(bad)

    def test_all_field_forms_and_both_declarations(self):
        fields=[{'tag':'parameter','name':'a'},
                {'tag':'function','from':{'tag':'parameter','name':'a'},'to':{'tag':'applied','name':'Int','arguments':[]}},
                {'tag':'applied','name':'F','arguments':[{'tag':'parameter','name':'a'}]},
                {'tag':'application','function':{'tag':'applied','name':'F','arguments':[]},'argument':{'tag':'parameter','name':'a'}},
                {'tag':'quantified','name':'b','kind':{'tag':'star'},'body':{'tag':'parameter','name':'b'}}]
        for tag,params in [('data',['a']),('data_kind',[{'name':'a','kind':{'tag':'star'}}])]:
            d={'tag':tag,'name':'T','parameters':params,'constructors':[{'name':'C','fields':fields}]}
            p.validate_raw_term({'tag':'with_data','declarations':[d],'body':lit(0)})

    def test_all_129_actual_primitive_identities_not_runtime_whitelist(self):
        self.assertEqual(set(p.PRIMITIVES),set(range(129)))
        for i,n in p.PRIMITIVES.items():
            raw={'tag':'primitive','id':i,'name':n,'arguments':[]}
            p.validate_raw_term(raw)
            self.assertEqual(p.erase_total(raw),{'tag':'primitive','id':i,'name':n})
        for value in [dict(tag='primitive',id=129,name='fake',arguments=[]),
                      dict(tag='primitive',id=8,name='subInt',arguments=[]),
                      dict(tag='primitive',id=True,name='ioBind',arguments=[])]:
            with self.assertRaises(p.ProjectionError):p.validate_raw_term(value)

    def test_identity_source_map_matches_exact_source_cases(self):
        # This is a source-inventory control, not a guest source execution.
        import re
        source=BASE.parents[2]/p.PRIMITIVE_SOURCE
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),p.PRIMITIVE_SOURCE_SHA256)
        text=source.read_text();code=dict((n,int(v))for n,v in re.findall(r'(P\w+) -> (\d+)',text[text.index('primitiveCode p ='):text.index('primitiveName ::')]))
        names=dict(re.findall(r'(P\w+) -> "([^"]+)"',text[text.index('primitiveName p ='):text.index('legacyPrimitives ::')]))
        self.assertEqual(set(code),set(names))
        self.assertEqual({i:names[n]for n,i in code.items()},p.PRIMITIVES)

    def test_int_double_bool_exactness(self):
        for value in [-(1<<63),(1<<63)-1,0]:
            p.validate_raw_term(lit(value));p.validate_raw_term({'tag':'double','bits_i64':value})
        for value in [-(1<<63)-1,1<<63,True,1.0,'1']:
            with self.assertRaises(p.ProjectionError):p.validate_raw_term(lit(value))
            with self.assertRaises(p.ProjectionError):p.validate_raw_term({'tag':'double','bits_i64':value})
        with self.assertRaises(p.ProjectionError):p.validate_raw_term({'tag':'bool','value':1})
        with self.assertRaises(p.ProjectionError):p.validate_raw_term({'tag':'double','value':-0.0})

    def test_raw_unit_never_abbreviated(self):
        t={'tag':'constructor','name':'()','arguments':[]}
        self.assertEqual(p.erase_total(t),{'tag':'constructor','name':'()'})
        with self.assertRaises(p.ProjectionError):p.validate_raw_term({'tag':'unit'})

    def test_extra_and_missing_keys_reject(self):
        for bad in [{'tag':'int64','value':1,'ignored':None},{'tag':'int64'},
                    {'tag':'var','name':{'id':1,'hint':'x','owner':'fake'}},
                    {'tag':'type_application','value':lit(1),'witness':{'tag':'refl','extra':[]}}]:
            with self.assertRaises(p.ProjectionError):p.validate_raw_term(bad)

    def test_duplicate_binder_ids_and_inconsistent_hints(self):
        with self.assertRaises(p.ProjectionError):p.validate_raw_term(let(1,lit(0),lam(1,var(1))))
        with self.assertRaises(p.ProjectionError):p.validate_raw_term(app(lam(1,var(1)),lam(1,var(1))))
        with self.assertRaises(p.ProjectionError):p.validate_raw_term(let(1,lit(0),var(1,'not-the-binder')))
        with self.assertRaises(p.ProjectionError):p.validate_raw_term(case(lit(0),[(ctor_pattern(ids=(1,1)),var(1))]))

    def test_evidence_hole_explicit_raw_only(self):
        hole={'tag':'evidence_hole','id':3}
        p.validate_raw_term(hole,erased=True,allow_evidence_holes=True)
        with self.assertRaises(p.ProjectionError):p.validate_raw_term(hole,erased=True)
        with self.assertRaises(p.ProjectionError):p.project_erased(hole)
        with self.assertRaises(p.ProjectionError):p.validate_raw_term(hole)


class ProjectionTests(unittest.TestCase):
    def test_two_kept_shared_lets_and_unused_string_and_knot(self):
        original=declared(let(1,lit(21),let(2,app(app({'tag':'primitive','id':8,'name':'addInt','arguments':[]},var(1)),var(1)),let(3,{'tag':'string','value':'dead'},rec([(4,var(4))],var(2))))))
        result,steps,report=replay(original)
        self.assertEqual(report['kept_binding_ids'],[1,2])
        self.assertEqual([s['keep']for s in steps],[True,True,False,False])
        self.assertIs(result['declarations'],original['declarations'])
        self.assertIs(result['body']['value'],original['body']['value'])
        self.assertIs(result['body']['body']['value'],original['body']['body']['value'])

    def test_hidden_lambda_capture_keeps_dependency(self):
        original=let(1,lit(42),let(2,lam(3,var(1)),var(2)))
        _,steps,report=replay(original)
        self.assertEqual(report['kept_binding_ids'],[1,2])
        self.assertEqual(steps[1]['rhs_free_ids'],[1])

    def test_case_default_scope_and_all_branch_uses(self):
        body=case(lit(0),[(ctor_pattern('No'),var(1)),(default_pattern(3),var(3))])
        original=let(1,lit(42),let(2,body,var(2)))
        _,steps,report=replay(original)
        self.assertEqual(report['kept_binding_ids'],[1,2]);self.assertEqual(steps[1]['rhs_free_ids'],[1])
        self.assertEqual(p.free_names(case(lit(0),[(default_pattern(3),var(3))])),set())

    def test_constructor_pattern_scope_and_wildcard(self):
        t=case(lit(0),[(ctor_pattern(ids=(2,None)),app(var(1),var(2)))])
        self.assertEqual(p.free_names(t),{1})
        self.assertEqual(p.free_names(p.erase_total(t),erased=True),{1})

    def test_nonrecursive_binder_not_in_own_rhs(self):
        t=let(1,var(1),lit(42))
        self.assertEqual(p.free_names(t),{1})
        with self.assertRaises(p.ProjectionError):p.project_typed(t)
        with self.assertRaises(p.ProjectionError):p.project_erased(p.erase_total(t))

    def test_textual_shadowing_distinct_ids_preserved(self):
        t=let(1,lit(21),let(2,var(1,'x'),var(2,'x'),'x'),'x')
        _,steps,report=replay(t)
        self.assertEqual(report['kept_binding_ids'],[1,2])
        self.assertEqual(steps[1]['rhs_free_ids'],[1])

    def test_whole_live_recursive_group_preserved_in_order(self):
        t=let(9,lit(42),rec([(2,var(1)),(1,var(9)),(3,var(3))],var(2)))
        result,steps,report=replay(t)
        self.assertEqual(report['kept_binding_ids'],[9,2,1,3])
        self.assertEqual(steps[1]['binding_ids'],[2,1,3])
        self.assertEqual(steps[1]['rhs_free_ids'],[9])
        self.assertIs(result['body']['bindings'],t['body']['bindings'])

    def test_dead_recursive_group_drops_whole_not_one_member(self):
        t=rec([(1,var(2)),(2,var(1))],lit(42))
        result,steps,report=replay(t)
        self.assertEqual(result,lit(42));self.assertEqual(steps[0]['binding_ids'],[1,2]);self.assertFalse(steps[0]['keep'])

    def test_unused_unbound_error_not_hidden_by_projection(self):
        t=let(1,var(99),lit(42))
        with self.assertRaises(p.ProjectionError):p.project_typed(t)

    def test_final_type_wrapper_not_commuted_to_expose_inner_let(self):
        t={'tag':'type_application','value':let(1,lit(42),var(1)),'witness':{'tag':'refl'}}
        typed,rows=p.project_typed(t);self.assertIs(typed,t);self.assertEqual(rows,[])
        erased=p.erase_total(t);projected,_=p.project_erased(erased)
        with self.assertRaisesRegex(p.ProjectionError,'spines differ'):
            p.replay_projection(t,erased,typed,projected,rows)

    def test_type_wrapper_without_new_spine_is_preserved(self):
        t={'tag':'type_application','value':lit(42),'witness':{'tag':'refl'}}
        result,_,report=replay(t);self.assertIs(result,t);self.assertEqual(report['spine_entries'],0)

    def test_nested_data_on_spine_rejected_but_nested_inside_lambda_observed(self):
        with self.assertRaises(p.ProjectionError):p.project_typed(declared(declared(lit(42))))
        t=lam(1,declared(var(1)));result,_,_=replay(t);self.assertIs(result,t)

    def test_original_erasure_must_match_actual_typed_erasure(self):
        t=let(1,lit(42),var(1));e=p.erase_total(t);u,s=p.project_typed(t);v,_=p.project_erased(e)
        forged=copy.deepcopy(e);forged['value']['value']=41
        with self.assertRaises(p.ProjectionError):p.replay_projection(t,forged,u,v,s)

    def test_projected_declarations_cannot_drop_or_prune_field(self):
        t=declared(let(1,lit(42),var(1)));e=p.erase_total(t);u,s=p.project_typed(t);v,_=p.project_erased(e)
        for modify in [lambda x:x['declarations'].clear(),lambda x:x['declarations'][0]['constructors'][0]['fields'].pop()]:
            bad=copy.deepcopy(u);modify(bad)
            with self.assertRaises(p.ProjectionError):p.replay_projection(t,e,bad,v,s)

    def test_forged_projected_kept_rhs_and_return_reject(self):
        t=let(1,lit(21),let(2,var(1),var(2)));e=p.erase_total(t);u,s=p.project_typed(t);v,_=p.project_erased(e)
        changes=[lambda x:x['value'].update(value=22),lambda x:x.update(body=var(1)),lambda x:x['body'].update(value=lit(21))]
        for mutate in changes:
            bad=copy.deepcopy(u);mutate(bad)
            with self.assertRaises(p.ProjectionError):p.replay_projection(t,e,bad,v,s)

    def test_all_witness_field_mutations_fail(self):
        t=let(1,lit(42),let(2,{'tag':'string','value':'unused'},var(1)));e=p.erase_total(t);u,s=p.project_typed(t);v,_=p.project_erased(e)
        mutations=[lambda a:a.pop(),lambda a:a.reverse(),lambda a:a[0].update(index=True),lambda a:a[0].update(kind='unknown'),lambda a:a[0].update(binding_ids=[2]),lambda a:a[0].update(rhs_free_ids=[1]),lambda a:a[0].update(demanded_ids=[]),lambda a:a[0].update(keep=False),lambda a:a[0].update(keep=1),lambda a:a[0].update(need_before=[]),lambda a:a[0].update(need_after=[1]),lambda a:a[0].update(extra=True),lambda a:a[0].update(binding_ids=[1,1])]
        for mutation in mutations:
            rows=copy.deepcopy(s);mutation(rows)
            with self.subTest(rows=rows):
                with self.assertRaises(p.ProjectionError):p.replay_projection(t,e,u,v,rows)

    def test_no_mutation_to_inputs(self):
        t=declared(let(1,lit(42),let(2,{'tag':'string','value':'unused'},var(1))))
        before=json.dumps(t,sort_keys=True);replay(t);self.assertEqual(json.dumps(t,sort_keys=True),before)

    def test_independent_erased_path_not_typed_projection(self):
        t=let(1,lit(42),var(1));e=p.erase_total(t)
        with patch.object(p,'project_typed',side_effect=AssertionError('must not be called')),patch.object(p,'_free_typed',side_effect=AssertionError('must not be called')):
            projected,rows=p.project_erased(e)
        self.assertEqual(rows[0]['binding_ids'],[1]);self.assertEqual(projected,e)


class BoundsTests(unittest.TestCase):
    def test_deep_input_within_budget_uses_no_python_recursion(self):
        t=var(1)
        for i in range(900,0,-1):t=lam(i,t)
        self.assertLessEqual(p.validate_raw_term(t,require_closed=True)['max_json_depth'],p.MAX_DEPTH)
        e=p.erase_total(t)
        self.assertTrue(p.exact_equal(e,p.erase_total(t)))
        self.assertEqual(p.project_typed(t)[1],[])

    def test_depth_overflow_rejects_before_recursive_replay(self):
        t=lit(42)
        for i in range(1030):t={'tag':'type_lambda','id':i,'bound':{'tag':'bottom'},'body':t}
        with self.assertRaisesRegex(p.ProjectionError,'depth budget'):p.validate_raw_term(t)

    def test_tagged_node_budget(self):
        with patch.object(p,'MAX_NODES',2):
            with self.assertRaisesRegex(p.ProjectionError,'node budget'):p.validate_raw_term(app(lit(1),lit(2)))

    def test_outer_spine_budget(self):
        t=let(1,lit(1),let(2,lit(2),let(3,lit(3),lit(42))))
        with patch.object(p,'MAX_SPINE',2):
            with self.assertRaises(p.ProjectionError):p.project_typed(t)
            with self.assertRaises(p.ProjectionError):p.project_erased(p.erase_total(t))

    def test_cyclic_python_input_rejected(self):
        t={'tag':'type_application','witness':{'tag':'refl'}};t['value']=t
        with self.assertRaisesRegex(p.ProjectionError,'cyclic'):p.validate_raw_term(t)

    def test_non_json_values_and_unicode_reject(self):
        for value in [float('nan'),float('inf'),b'raw',object()]:
            with self.assertRaises(p.ProjectionError):p.validate_raw_term({'tag':'string','value':value})
        with self.assertRaises(p.ProjectionError):p.validate_raw_term({'tag':'string','value':'\ud800'})
        with self.assertRaises(p.ProjectionError):p.validate_raw_term({'tag':'constructor','name':'C','arguments':()})

    def test_type_sensitive_iterative_equality(self):
        self.assertFalse(p.exact_equal({'x':True},{'x':1}))
        self.assertFalse(p.exact_equal([1,2],[2,1]))
        self.assertTrue(p.exact_equal({'a':[1,True,None]},{'a':[1,True,None]}))


class CapturedOriginalTests(unittest.TestCase):
    def test_explicit_pinned_original_artifact(self):
        supplied=os.environ.get('MLF_MODULE_CAPTURED_EVENTS')
        if not supplied:self.skipTest('explicit immutable original-event artifact not supplied')
        path=Path(supplied)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),CAPTURED_EVENTS_SHA256)
        events=json.loads(path.read_text())
        artifact=next(e['event']['artifact']for e in events if e.get('event',{}).get('phase')=='complete_original_checked_artifact'and e['event']['event']=='end')
        self.assertTrue(artifact['ordinary_whole_check_passed']);self.assertTrue(artifact['root_type_alpha_equal']);self.assertTrue(artifact['source_erasure_equal']);self.assertFalse(artifact['projection_performed'])
        original=artifact['raw_annotated'];projected,steps,report=replay(original)
        self.assertEqual(report,{'policy':'outer-lazy-spine/1','spine_entries':25,'kept_entries':2,'dropped_entries':23,'kept_binding_ids':[38887,38922],'closed':True})
        self.assertEqual(len(projected['declarations']),7)
        self.assertEqual(p.validate_raw_term(original)['tagged_nodes'],26598)
        self.assertEqual(p.validate_raw_term(original)['max_json_depth'],113)


CAPTURED_EVENTS_SHA256='5be8e9cdf317b9beb5e4f83c2a1637937b04c9e6ed07e0b805bb33f9af7b588b'

if __name__=='__main__':
    unittest.main()
