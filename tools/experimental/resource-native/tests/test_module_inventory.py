"""Synthetic complete-family census controls; never ordinary typechecking/native.
Optional pinned genuine original artifact uses only previously observed syntax.
"""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
import module_projection as p
import module_inventory as m


def typ(n='Int',args=()):return {'tag':'constructor','name':n,'arguments':list(args)}
def applied(n,args=()):return {'tag':'applied','name':n,'arguments':list(args)}
def param(n):return {'tag':'parameter','name':n}
def fun(a,b):return {'tag':'function','from':a,'to':b}
def decl(n,constructors,parameters=()):return {'tag':'data','name':n,'parameters':list(parameters),'constructors':[{'name':c,'fields':list(fs)}for c,fs in constructors]}
def sumdecl(n,fields=()):return decl(n,[(n+'.Empty',[]),(n+'.Full',fields)])
def record(n,fields=()):return decl(n,[(n+'.Record',fields)])
def literal(n=42):return {'tag':'int64','value':n}
def name(i):return {'id':i,'hint':'x'+str(i)}
def var(i):return {'tag':'var','name':name(i)}
def ctor(n,args=()):return {'tag':'constructor','name':n,'arguments':list(args)}
def lam(i,t,body):return {'tag':'lambda','parameter':name(i),'parameter_type':t,'body':body}
def let(i,a,b):return {'tag':'let','name':name(i),'value':a,'body':b}
def app(a,b):return {'tag':'application','function':a,'argument':b}
def case(s,patterns,result=None):return {'tag':'case','scrutinee':s,'result_type':result or typ(),'alternatives':[{'pattern':{'tag':'constructor','constructor':cn,'fields':[None if i is None else name(i)for i in ns]},'body':v}for cn,ns,v in patterns]}
def context(ds,term):return {'tag':'with_data','declarations':ds,'body':term} if ds else term

def derive(ds,term=None,result=None):return m.derive_inventory(ds,context(ds,term or literal()),result or typ())


class CensusTests(unittest.TestCase):
    def test_unused_higher_kind_unsupported_context_is_not_admitted(self):
        d={'tag':'data_kind','name':'Dictionary','parameters':[{'name':'f','kind':{'tag':'arrow','from':{'tag':'star'},'to':{'tag':'star'}}}], 'constructors':[{'name':'MkDictionary','fields':[fun(param('f'),applied('String'))]}]}
        out=derive([d,sumdecl('Unused',[applied('String')])])
        self.assertEqual(out[:3],([],[],[]));self.assertEqual(out[3]['selected_declaration_indices'],[])
        self.assertEqual(out[3]['evidence_only_declaration_indices'],[0,1])

    def test_used_family_keeps_all_variants_fields_and_original_index(self):
        ds=[sumdecl('Unused',[applied('String')]),sumdecl('Payload',[applied('Int'),applied('Bool')])]
        term=case(ctor('Payload.Empty'),[('Payload.Full',[1,None],var(1)),('Payload.Empty',[],literal(0))])
        records,templates,instances,w=derive(ds,term)
        self.assertEqual(records,[]);self.assertEqual(templates[0]['declaration_index'],1)
        self.assertEqual([c['constructor']for c in instances[0]['constructors']],['Payload.Empty','Payload.Full'])
        self.assertEqual(instances[0]['constructors'][1]['fields'],[typ('Int'),typ('Bool')])
        self.assertEqual(w['seed_instances'],[{'declaration_index':1,'datatype':'Payload','arguments':[]}])
        self.assertEqual(w['selected_declaration_indices'],[1]);self.assertEqual(w['evidence_only_declaration_indices'],[0])

    def test_self_recursive_family_closure_finite(self):
        d=sumdecl('Kind',[applied('Kind'),applied('Kind')]);out=derive([d],ctor('Kind.Empty'),typ('Kind'))
        self.assertEqual(len(out[3]['closure_instances']),1)
        self.assertEqual([e['field_index']for e in out[3]['closure_edges']],[0,1])
        self.assertTrue(all(e['source']['declaration_index']==e['target']['declaration_index']==0 for e in out[3]['closure_edges']))

    def test_fifo_closure_and_final_original_declaration_order(self):
        ds=[sumdecl('B',[applied('A')]),sumdecl('A',[applied('B')])]
        records,templates,instances,w=derive(ds,ctor('A.Empty'),typ('A'))
        self.assertEqual([r['declaration_index']for r in w['closure_instances']],[1,0])
        self.assertEqual([r['declaration_index']for r in templates],[0,1])
        self.assertEqual([r['declaration_index']for r in instances],[0,1])
        self.assertEqual([e['source']['declaration_index']for e in w['closure_edges']],[0,1])

    def test_parametric_fields_substitute_formal_identity_and_order(self):
        d=decl('PairChoice',[('Nothing',[]),('Both',[param('right'),param('left')])],['left','right'])
        out=derive([d],ctor('Nothing',[typ('Int'),typ('Bool')]),typ('PairChoice',[typ('Int'),typ('Bool')]))
        self.assertEqual(out[2][0]['constructors'][1]['fields'],[typ('Bool'),typ('Int')])
        self.assertEqual(out[1][0]['constructors'][1]['fields'],[param('right'),param('left')])

    def test_multiple_view_census_still_rejects_nonfunction_application(self):
        d=decl('Maybe',[('Nothing',[]),('Just',[param('a')])],['a'])
        with self.assertRaises(m.InventoryError):derive([d],app(ctor('Nothing',[typ('Int')]),ctor('Nothing',[typ('Bool')])))

    def test_non_scalar_or_open_instance_rejects(self):
        d=decl('Maybe',[('Nothing',[]),('Just',[param('a')])],['a'])
        for t in [typ('()'),typ('Maybe',[typ()]),{'tag':'var','id':2}]:
            with self.subTest(t=t):
                with self.assertRaises(m.InventoryError):derive([d],ctor('Nothing',[t]))

    def test_sum_field_cannot_admit_unit_record_arrow_or_unknown(self):
        for raw in [applied('()'),applied('R'),fun(applied('Int'),applied('Int')),applied('Missing')]:
            ds=[record('R'),sumdecl('S',[raw])]
            with self.subTest(raw=raw):
                with self.assertRaises(m.InventoryError):derive(ds,ctor('S.Empty'),typ('S'))

    def test_raw_application_and_quantified_sum_fields_not_silently_flattened(self):
        for raw in [{'tag':'application','function':applied('Maybe'),'argument':applied('Int')},
                    {'tag':'quantified','name':'x','kind':{'tag':'star'},'body':applied('Int')}]:
            with self.assertRaises(m.InventoryError):derive([sumdecl('S',[raw])],ctor('S.Empty'),typ('S'))

    def test_record_old_arrow_nominal_route_and_edge_paths(self):
        ds=[sumdecl('A'),sumdecl('B'),record('R',[fun(fun(applied('A'),applied('B')),applied('Int'))])]
        records,templates,instances,w=derive(ds,lam(1,typ('R'),var(1)),{'tag':'arrow','from':typ('R'),'to':typ('R')})
        self.assertEqual([r['datatype']for r in w['closure_instances']],['R','A','B'])
        self.assertEqual([e['type_path']for e in w['closure_edges']],[['from','from'],['from','to']])
        self.assertEqual(records[0]['fields'][0],{'tag':'arrow','from':{'tag':'arrow','from':typ('A'),'to':typ('B')},'to':typ('Int')})
        self.assertEqual([t['declaration_index']for t in templates],[0,1])
        self.assertEqual(set(records[0]),{'datatype','constructor','arity','fields'})

    def test_record_parameters_reject_only_when_used(self):
        d=decl('R',[('MkR',[param('a')])],['a']);self.assertEqual(derive([d])[0],[])
        with self.assertRaises(m.InventoryError):derive([d],ctor('MkR',[typ()]),typ('R',[typ()]))

    def test_case_owner_can_be_known_only_after_full_field_closure(self):
        ds=[sumdecl('Outer',[applied('Inner')]),sumdecl('Inner',[applied('Int')])]
        inner=case(var(1),[('Inner.Empty',[],literal(0)),('Inner.Full',[2],var(2))])
        term=case(ctor('Outer.Empty'),[('Outer.Empty',[],literal(0)),('Outer.Full',[1],inner)])
        out=derive(ds,term)
        self.assertEqual([r['datatype']for r in out[3]['seed_instances']],['Outer'])
        self.assertEqual([r['datatype']for r in out[3]['closure_instances']],['Outer','Inner'])

    def test_pattern_does_not_fabricate_parameterized_owner_instance(self):
        d=decl('Maybe',[('Nothing',[]),('Just',[param('a')])],['a'])
        term=case(literal(0),[('Nothing',[],literal(0)),('Just',[1],literal(1))])
        with self.assertRaises(m.InventoryError):derive([d],term)

    def test_wrong_family_same_spelling_display_has_no_authority(self):
        ds=[sumdecl('Left.Payload',[applied('Int'),applied('Bool')]),sumdecl('Right.Payload',[applied('Bool'),applied('Int')])]
        term=let(1,ctor('Left.Payload.Empty'),let(2,ctor('Right.Payload.Empty'),literal()))
        out=derive(ds,term)
        self.assertEqual([t['datatype']for t in out[1]],['Left.Payload','Right.Payload'])
        bad=copy.deepcopy(out[2]);bad[1]['constructors'][1]['fields']=[typ('Int'),typ('Bool')]
        with self.assertRaises(m.InventoryError):m.verify_inventory(ds,context(ds,term),typ(),out[0],out[1],bad,out[3])

    def test_case_all_variants_and_wildcard_arity_preserved(self):
        d=sumdecl('S',[applied('Int'),applied('Bool')])
        bads=[case(ctor('S.Empty'),[('S.Empty',[],literal())]),
              case(ctor('S.Empty'),[('S.Empty',[],literal()),('S.Full',[None],literal())]),
              case(ctor('S.Empty'),[('S.Empty',[],literal()),('S.Full',[None,None],literal()),('S.Empty',[],literal())])]
        for bad in bads:
            with self.assertRaises(m.InventoryError):derive([d],bad)

    def test_case_default_rejected_even_if_unused_branch(self):
        term={'tag':'case','scrutinee':literal(),'result_type':typ(),'alternatives':[{'pattern':{'tag':'default','binder':None},'body':literal()}]}
        with self.assertRaises(m.InventoryError):derive([],term)

    def test_builtin_unit_has_no_user_family(self):
        term=case(ctor('()'),[('()',[],literal())]);out=derive([],term)
        self.assertEqual(out[:3],([],[],[]));self.assertEqual(out[3]['closure_instances'],[])

    def test_unknown_annotation_and_remaining_proof_wrappers_reject(self):
        for t in [typ('String'),typ('Double'),{'tag':'var','id':1},{'tag':'bottom'},
                  {'tag':'forall','id':1,'bound':{'tag':'bottom'},'body':typ()}]:
            with self.assertRaises(m.InventoryError):derive([],lam(1,t,literal()))
        for t in [{'tag':'type_lambda','id':1,'bound':{'tag':'bottom'},'body':literal()},
                  {'tag':'type_application','value':literal(),'witness':{'tag':'refl'}}]:
            with self.assertRaises(m.InventoryError):derive([],t)

    def test_retained_string_and_double_fail_strict_fragment(self):
        for term in [{'tag':'string','value':'keep'},{'tag':'double','bits_i64':0}]:
            with self.assertRaises(m.InventoryError):derive([],term)

    def test_root_then_annotation_then_term_scan_order(self):
        ds=[sumdecl('A'),sumdecl('B'),sumdecl('C')]
        t=lam(1,typ('A'),let(2,lam(3,typ('C'),literal()),ctor('B.Empty')));root={'tag':'arrow','from':typ('A'),'to':typ('B')}
        out=derive(ds,t,root)
        self.assertEqual([r['datatype']for r in out[3]['seed_instances']],['A','B','C'])


class GuardTests(unittest.TestCase):
    def test_all_context_reserved_and_collision_guard_even_unused(self):
        bads=[[sumdecl('Int')],[decl('R',[('MLFStackFrame',[])])],
              [sumdecl('Same'),sumdecl('Same')],
              [decl('A',[('Repeated',[])]),decl('B',[('Repeated',[])])]]
        for ds in bads:
            with self.assertRaises((m.InventoryError,p.ProjectionError)):derive(ds)

    def test_reserved_sets_match_existing_exact_transport_guard(self):
        tree=ast.parse((BASE/'transport.py').read_text());found={}
        for node in tree.body:
            if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('RESERVED_DATATYPES','RESERVED_CONSTRUCTORS'):
                self.assertIsInstance(node.value,ast.BinOp);self.assertIsInstance(node.value.op,ast.BitOr)
                self.assertEqual(node.value.right.id,'SOURCE_TUPLES');found[node.targets[0].id]=ast.literal_eval(node.value.left)|m.SOURCE_TUPLES
        self.assertEqual(found['RESERVED_DATATYPES'],m.RESERVED_DATATYPES);self.assertEqual(found['RESERVED_CONSTRUCTORS'],m.RESERVED_CONSTRUCTORS)

    def test_unused_large_variant_context_allowed_but_used_rejected(self):
        d=decl('Big',[(f'C{i}',[])for i in range(65)])
        self.assertEqual(derive([d])[3]['evidence_only_declaration_indices'],[0])
        with self.assertRaises(m.InventoryError):derive([d],ctor('C0'),typ('Big'))

    def test_unselected_variant_field_overflow_rejects_used_family(self):
        d=sumdecl('S',[applied('Int')]*33)
        self.assertEqual(derive([d])[1],[])
        with self.assertRaises(m.InventoryError):derive([d],ctor('S.Empty'),typ('S'))

    def test_sum_family_registry_limit(self):
        ds=[sumdecl('F'+str(i))for i in range(65)];term=literal()
        for i in range(65):term=let(i+1,ctor('F'+str(i)+'.Empty'),term)
        with self.assertRaises(m.InventoryError):derive(ds,term)

    def test_unused_formal_kind_allowed_but_used_must_star(self):
        d=sumdecl('S');d['tag']='data_kind';d['parameters']=[{'name':'f','kind':{'tag':'arrow','from':{'tag':'star'},'to':{'tag':'star'}}}]
        self.assertEqual(derive([d])[2],[])
        with self.assertRaises(m.InventoryError):derive([d],ctor('S.Empty',[typ()]),typ('S',[typ()]))

    def test_context_mismatch_and_nested_context_reject(self):
        ds=[sumdecl('A')]
        with self.assertRaises(m.InventoryError):m.derive_inventory(ds,literal(),typ())
        with self.assertRaises(m.InventoryError):m.derive_inventory(ds,context([sumdecl('B')],literal()),typ())
        with self.assertRaises(m.InventoryError):derive(ds,context([sumdecl('B')],literal()))

    def test_witness_and_metadata_mutations_cannot_prune_or_add(self):
        ds=[sumdecl('Unused'),sumdecl('A',[applied('B')]),sumdecl('B',[applied('Bool')])];term=ctor('A.Empty');out=derive(ds,term,typ('A'))
        mutations=[(0,lambda v:v.append({'datatype':'Unused','constructor':'x','arity':0,'fields':[]})),
                   (1,lambda v:v[0].update(declaration_index=0)),(1,lambda v:v[0]['constructors'].pop()),
                   (2,lambda v:v[0]['constructors'][1]['fields'].clear()),(2,lambda v:v[0].update(arguments=[typ()])),
                   (3,lambda v:v.update(policy='guess')),(3,lambda v:v['seed_instances'].clear()),
                   (3,lambda v:v['closure_edges'].clear()),(3,lambda v:v['closure_instances'].reverse()),
                   (3,lambda v:v['selected_declaration_indices'].append(0)),
                   (3,lambda v:v['evidence_only_declaration_indices'].clear()),(3,lambda v:v.update(extra=True))]
        for index,mutate in mutations:
            bad=copy.deepcopy(out);mutate(bad[index])
            with self.assertRaises(m.InventoryError):m.verify_inventory(ds,context(ds,term),typ('A'),*bad)

    def test_inputs_are_not_mutated(self):
        ds=[sumdecl('A',[applied('A')])];term=context(ds,ctor('A.Empty'));before=json.dumps([ds,term],sort_keys=True)
        out=m.derive_inventory(ds,term,typ('A'));m.verify_inventory(ds,term,typ('A'),*out)
        self.assertEqual(json.dumps([ds,term],sort_keys=True),before)

    def test_deep_record_arrow_census_is_iterative(self):
        field=applied('Int')
        for _ in range(900):field=fun(field,applied('Int'))
        out=derive([record('R',[field])],lam(1,typ('R'),var(1)),{'tag':'arrow','from':typ('R'),'to':typ('R')})
        self.assertEqual(out[3]['selected_declaration_indices'],[0])


class CapturedOriginalTest(unittest.TestCase):
    def test_captured_projected_scalar_has_full_context_but_no_runtime_families(self):
        supplied=os.environ.get('MLF_MODULE_CAPTURED_EVENTS')
        if not supplied:self.skipTest('explicit immutable original artifact not supplied')
        path=Path(supplied)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),CAPTURED_EVENTS_SHA256)
        events=json.loads(path.read_text());a=next(e['event']['artifact']for e in events if 'artifact'in e.get('event',{}))
        projected,steps=p.project_typed(a['raw_annotated']);out=m.derive_inventory(projected['declarations'],projected,a['checked_type'])
        self.assertEqual(out[:3],([],[],[]));self.assertEqual(out[3]['evidence_only_declaration_indices'],list(range(7)))
        self.assertEqual(len(projected['declarations']),7)


CAPTURED_EVENTS_SHA256='5be8e9cdf317b9beb5e4f83c2a1637937b04c9e6ed07e0b805bb33f9af7b588b'
if __name__=='__main__':unittest.main()
