"""Finite synthetic concrete-view/type witnesses, not genuine source evidence."""
import copy
import itertools
import unittest
from test_module_inventory import (m,p,typ,applied,param,fun,decl,sumdecl,record,literal,
                                   name,var,ctor,lam,app,let,case,context,derive)


def arrow(a,b):return {'tag':'arrow','from':a,'to':b}
def boolean(v=True):return {'tag':'bool','value':v}
def primitive(n,i,args=()):return {'tag':'primitive','id':i,'name':n,'arguments':list(args)}
def apply(head,*args):
    for arg in args:head=app(head,arg)
    return head

def maybe(n='Maybe'):
    return decl(n,[(n+'.Nothing',[]),(n+'.Just',[param('a')])],['a'])

def views_term(n='Maybe',vectors=((typ('Bool'),),(typ('Int'),))):
    term=literal()
    for i,args in reversed(list(enumerate(vectors,1))):term=let(i,ctor(n+'.Nothing',args),term)
    return term


class MultipleViewTests(unittest.TestCase):
    def test_fifo_seed_order_separate_from_canonical_view_order(self):
        out=derive([maybe()],views_term())
        self.assertEqual([r['arguments']for r in out[3]['seed_instances']],[[typ('Bool')],[typ('Int')]])
        self.assertEqual([r['arguments']for r in out[2]],[[typ('Int')],[typ('Bool')]])
        self.assertEqual([r['view_index']for r in out[2]],[0,1])
        self.assertEqual(len(out[1]),1);self.assertEqual(out[3]['selected_declaration_indices'],[0])
        self.assertEqual(out[2][0]['constructors'][1]['fields'],[typ('Int')])
        self.assertEqual(out[2][1]['constructors'][1]['fields'],[typ('Bool')])

    def test_two_formal_vector_order_is_not_a_set(self):
        d=decl('Either',[('Either.Nothing',[]),('Either.Both',[param('b'),param('a')])],['a','b'])
        term=views_term('Either',((typ('Bool'),typ('Int')),(typ('Int'),typ('Bool'))))
        rows=derive([d],term)[2]
        self.assertEqual([x['arguments']for x in rows],[[typ('Int'),typ('Bool')],[typ('Bool'),typ('Int')]])
        self.assertEqual([x['constructors'][1]['fields']for x in rows],[[typ('Bool'),typ('Int')],[typ('Int'),typ('Bool')]])

    def test_phantom_nullary_views_stay_distinct_and_case_reordering_is_exact(self):
        d=decl('Token',[('Cold',[]),('Hot',[])],['a'])
        term=let(1,ctor('Cold',[typ('Int')]),let(2,ctor('Cold',[typ('Bool')]),
            apply(primitive('addInt',8),case(var(1),[('Hot',[],literal(1)),('Cold',[],literal(20))]),
                  case(var(2),[('Cold',[],literal(22)),('Hot',[],literal(0))]))))
        out=derive([d],term);cases=out[3]['case_obligations']
        self.assertEqual(len(out[2]),2)
        self.assertEqual([c['view']['arguments']for c in cases],[[typ('Int')],[typ('Bool')]])
        self.assertEqual([a['variant_index']for a in cases[0]['arms']],[1,0])
        self.assertTrue(all(a['fields']==[]for c in cases for a in c['arms']))
        self.assertNotEqual(cases[0]['view'],cases[1]['view'])

    def test_nested_fields_close_both_exact_views(self):
        ds=[decl('Wrap',[('Wrap.Nothing',[]),('Wrap.Full',[applied('Maybe',[param('a')])])],['a']),maybe()]
        term=views_term('Wrap');out=derive(ds,term)
        self.assertEqual([(x['datatype'],x['arguments'])for x in out[3]['closure_instances']],
            [('Wrap',[typ('Bool')]),('Wrap',[typ('Int')]),('Maybe',[typ('Bool')]),('Maybe',[typ('Int')])])
        edges=out[3]['closure_edges'];self.assertEqual(len(edges),2)
        self.assertEqual([e['source']['arguments']for e in edges],[[typ('Int')],[typ('Bool')]])
        self.assertEqual([e['target']['arguments']for e in edges],[[typ('Int')],[typ('Bool')]])
        self.assertEqual([r['view_index']for r in out[2]],[0,1,2,3])

    def test_recursive_swapped_vectors_close_by_full_key(self):
        d=decl('Swap',[('Swap.Nothing',[]),('Swap.Step',[applied('Swap',[param('b'),param('a')])])],['a','b'])
        out=derive([d],ctor('Swap.Nothing',[typ('Int'),typ('Bool')]),typ('Swap',[typ('Int'),typ('Bool')]))
        self.assertEqual([r['arguments']for r in out[3]['closure_instances']],[[typ('Int'),typ('Bool')],[typ('Bool'),typ('Int')]])
        self.assertEqual(len(out[3]['closure_edges']),2)
        self.assertEqual(out[3]['closure_edges'][0]['target']['arguments'],[typ('Bool'),typ('Int')])
        self.assertEqual(out[3]['closure_edges'][1]['target']['arguments'],[typ('Int'),typ('Bool')])

    def test_repeated_view_is_deduplicated_without_losing_nodes(self):
        term=views_term(vectors=((typ('Int'),),(typ('Bool'),),(typ('Int'),)))
        self.assertEqual(len(derive([maybe()],term)[2]),2)

    def test_same_spelling_role_but_distinct_resolved_owners_are_not_aliased(self):
        ds=[maybe('ModuleEntity1'),maybe('ModuleEntity2')]
        term=let(1,ctor('ModuleEntity1.Nothing',[typ('Int')]),let(2,ctor('ModuleEntity2.Nothing',[typ('Int')]),literal()))
        rows=derive(ds,term)[2]
        self.assertEqual([r['declaration_index']for r in rows],[0,1])
        self.assertNotEqual(rows[0]['datatype'],rows[1]['datatype'])

    def test_bound_counts_views_not_templates_64_and_65(self):
        params=['a'+str(i)for i in range(7)]
        d=decl('Phantom',[('Phantom.Nothing',[]),('Phantom.Other',[])],params)
        vectors=[tuple(typ('Bool'if bit else'Int')for bit in bits)for bits in itertools.product([0,1],repeat=7)]
        out=derive([d],views_term('Phantom',vectors[:64]));self.assertEqual(len(out[2]),64);self.assertEqual(len(out[1]),1)
        self.assertEqual([r['view_index']for r in out[2]],list(range(64)))
        with self.assertRaisesRegex(m.InventoryError,'view bound'):derive([d],views_term('Phantom',vectors[:65]))

    def test_parameterized_record_remains_excluded(self):
        d=decl('Box',[('MkBox',[param('a')])],['a'])
        with self.assertRaises(m.InventoryError):derive([d],apply(ctor('MkBox',[typ('Int')]),literal()),typ('Box',[typ('Int')]))


class LogicalCaseTests(unittest.TestCase):
    def test_exact_scrutinee_view_and_wildcard_field_types(self):
        d=decl('PairChoice',[('None',[]),('Both',[param('a'),param('b')])],['a','b'])
        term=case(apply(ctor('Both',[typ('Int'),typ('Bool')]),literal(42),boolean()),[('Both',[1,None],var(1)),('None',[],literal(0))])
        w=derive([d],term)[3]['case_obligations'][0]
        self.assertEqual(w['path'],'root.body');self.assertEqual(w['scrutinee_type'],typ('PairChoice',[typ('Int'),typ('Bool')]))
        self.assertEqual(w['arms'][0]['fields'],[{'field_index':0,'name':name(1),'type':typ('Int')},{'field_index':1,'name':None,'type':typ('Bool')}])

    def test_case_type_derives_from_let_alias_not_available_view(self):
        term=let(1,ctor('Maybe.Nothing',[typ('Bool')]),let(2,ctor('Maybe.Nothing',[typ('Int')]),let(3,var(1),
            case(var(3),[('Maybe.Just',[4],apply(primitive('ifThenElse',13,[typ('Int')]),var(4),literal(42),literal(0))),('Maybe.Nothing',[],literal(0))]))))
        row=derive([maybe()],term)[3]['case_obligations'][0]
        self.assertEqual(row['view']['arguments'],[typ('Bool')])
        self.assertEqual(row['arms'][0]['fields'][0]['type'],typ('Bool'))

    def test_case_preorder_even_when_scrutinee_contains_record_case(self):
        ds=[sumdecl('S'),record('R',[applied('S')])]
        inner=case(app(ctor('R.Record'),ctor('S.Empty')),[('R.Record',[1],var(1))],typ('S'))
        outer=case(inner,[('S.Empty',[],literal()),('S.Full',[],literal(0))])
        rows=derive(ds,outer)[3]['case_obligations']
        self.assertEqual([r['path']for r in rows],['root.body','root.body.scrutinee'])
        self.assertEqual([r['view']['datatype']for r in rows],['S','R'])

    def test_record_function_field_remains_old_logical_type(self):
        ds=[record('R',[fun(applied('Int'),applied('Int'))])]
        term=case(app(ctor('R.Record'),lam(1,typ(),var(1))),[('R.Record',[2],app(var(2),literal()))])
        row=derive(ds,term)[3]['case_obligations'][0]
        self.assertEqual(row['arms'][0]['fields'][0]['type'],arrow(typ(),typ()))

    def test_unit_witness_has_null_view_only(self):
        row=derive([],case(ctor('()'),[('()',[],literal())]))[3]['case_obligations'][0]
        self.assertEqual(row,{'path':'root','scrutinee_type':typ('()'),'view':None,'arms':[{'constructor':'()','variant_index':0,'fields':[]}]})

    def test_wrong_nullary_view_application_rejects_despite_identical_layout(self):
        d=decl('Token',[('Cold',[]),('Hot',[])],['a'])
        term=app(lam(1,typ('Token',[typ('Int')]),literal()),ctor('Cold',[typ('Bool')]))
        with self.assertRaisesRegex(m.InventoryError,'application argument'):derive([d],term)

    def test_wrong_root_full_type_rejects(self):
        d=decl('Token',[('Cold',[]),('Hot',[])],['a'])
        with self.assertRaisesRegex(m.InventoryError,'checked root'):derive([d],ctor('Cold',[typ('Int')]),typ('Token',[typ('Bool')]))

    def test_recursive_annotation_type_mismatch_rejects(self):
        term={'tag':'letrec','bindings':[{'name':name(1),'type':typ('Int'),'value':boolean()}],'body':literal()}
        with self.assertRaisesRegex(m.InventoryError,'check_recursive'):derive([],term)

    def test_all_case_bodies_are_logically_checked(self):
        d=maybe();term=case(ctor('Maybe.Nothing',[typ('Int')]),[('Maybe.Nothing',[],literal()),('Maybe.Just',[1],boolean())])
        with self.assertRaisesRegex(m.InventoryError,'check_arm'):derive([d],term)

    def test_sum_bool_case_result_not_widened(self):
        d=maybe();term=case(ctor('Maybe.Nothing',[typ('Int')]),[('Maybe.Nothing',[],boolean()),('Maybe.Just',[1],boolean())],typ('Bool'))
        with self.assertRaisesRegex(m.InventoryError,'SUM case result'):derive([d],term,typ('Bool'))

    def test_exact_primitive_identity_and_type_argument_whitelist(self):
        with self.assertRaises((m.InventoryError,p.ProjectionError)):derive([],primitive('panic',55))
        with self.assertRaises((m.InventoryError,p.ProjectionError)):derive([],primitive('addInt',9))
        with self.assertRaises(m.InventoryError):derive([],primitive('addInt',8,[typ()]))
        with self.assertRaises(m.InventoryError):derive([],primitive('ifThenElse',13,[typ('Bool')]))
        term=apply(primitive('ifThenElse',13,[typ()]),boolean(),literal(),literal(0));self.assertEqual(derive([],term)[3]['seed_instances'],[])

    def test_unknown_or_out_of_scope_variable_not_a_view_witness(self):
        with self.assertRaises((m.InventoryError,p.ProjectionError)):derive([],var(99))


class ForgeryTests(unittest.TestCase):
    def setUp(self):
        self.ds=[decl('Wrap',[('Wrap.Nothing',[]),('Wrap.Full',[applied('Maybe',[param('a')])])],['a']),maybe()]
        self.term=let(1,ctor('Wrap.Nothing',[typ('Int')]),let(2,ctor('Wrap.Nothing',[typ('Bool')]),
            case(var(1),[('Wrap.Nothing',[],literal()),('Wrap.Full',[3],literal(0))])))
        self.out=derive(self.ds,self.term)

    def reject_mutation(self,section,mutate):
        out=copy.deepcopy(self.out);mutate(out[section]);self.assertNotEqual(out,self.out)
        with self.assertRaises(m.InventoryError):m.verify_inventory(self.ds,context(self.ds,self.term),typ(),*out)

    def test_source_edge_vector_forgery(self):
        self.reject_mutation(3,lambda w:w['closure_edges'][0]['source'].__setitem__('arguments',[typ('Bool')]))
    def test_target_edge_vector_forgery(self):
        self.reject_mutation(3,lambda w:w['closure_edges'][0]['target'].__setitem__('arguments',[typ('Bool')]))
    def test_edge_owner_forgery(self):
        self.reject_mutation(3,lambda w:w['closure_edges'][0]['target'].__setitem__('declaration_index',0))
    def test_nullary_case_view_forgery(self):
        self.reject_mutation(3,lambda w:w['case_obligations'][0]['view'].__setitem__('arguments',[typ('Bool')]))
    def test_nullary_case_supplied_type_is_not_premise(self):
        self.reject_mutation(3,lambda w:w['case_obligations'][0].__setitem__('scrutinee_type',typ('Wrap',[typ('Bool')])))
    def test_case_field_type_and_wildcard_omission(self):
        self.reject_mutation(3,lambda w:w['case_obligations'][0]['arms'][1]['fields'].clear())
        self.reject_mutation(3,lambda w:w['case_obligations'][0]['arms'][1]['fields'][0].__setitem__('type',typ('Maybe',[typ('Bool')])))
    def test_view_index_duplicate_and_order_forgery(self):
        self.reject_mutation(2,lambda rows:rows[1].__setitem__('view_index',0))
        self.reject_mutation(2,lambda rows:rows.reverse())
    def test_missing_variant_or_unused_payload(self):
        self.reject_mutation(2,lambda rows:rows[0]['constructors'].pop())
        self.reject_mutation(2,lambda rows:rows[0]['constructors'][1]['fields'].clear())
    def test_template_or_view_row_duplication(self):
        self.reject_mutation(1,lambda rows:rows.append(copy.deepcopy(rows[0])))
        self.reject_mutation(2,lambda rows:rows.append(copy.deepcopy(rows[0])))
    def test_case_witness_extra_fields_reject(self):
        self.reject_mutation(3,lambda w:w['case_obligations'][0].__setitem__('unchecked',True))
    def test_view_ref_extra_fields_reject(self):
        self.reject_mutation(3,lambda w:w['closure_instances'][0].__setitem__('physical_layout_alias',True))


if __name__=='__main__':unittest.main()
