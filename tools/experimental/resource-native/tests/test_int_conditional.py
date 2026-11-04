"""Synthetic witness/representation controls, never genuine-source origin proof."""
import copy
import json
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import test_scalar_transport as base
p=base.planner;t=base.t

def tyvar(i):return {'tag':'var','id':i}
def standard(ty):return {'tag':'then','first':{'tag':'inner','witness':{'tag':'bottom','type':ty}},'second':{'tag':'elim'}}
def typeabs(i,body,bound=None):return {'tag':'type_lambda','id':i,'bound':bound or {'tag':'bottom'},'body':body}
def typeapp(value,witness):return {'tag':'type_application','value':value,'witness':witness}
def ifprimitive(ty=None):return {'tag':'primitive','id':13,'name':'ifThenElse','arguments':[ty or base.typ('Int')]}
def conditional(condition,yes,no):return base.app(base.app(base.app(ifprimitive(),condition),yes),no)
def nested_original():
    inner=typeapp(typeabs(76,ifprimitive(tyvar(76))),standard(tyvar(143)))
    outer=typeapp(typeabs(143,base.app(inner,base.lit(True))),standard(base.typ('Int')))
    return base.app(base.app(outer,base.lit(42)),base.lit(0))
def envelope(original):
    normalized,steps=t.normalize_conditional_raw(original)
    value=base.envelope(t.strip_data_evidence(normalized))
    value['normalization'].update(policy='closed-int-standard-instantiation/1',original_annotated=copy.deepcopy(original),
        original_erased=t.projection(original,True,True),normalized_annotated=copy.deepcopy(normalized),steps=steps)
    return value

class Conditional(unittest.TestCase):
    def test_actual_nested_standard_chain_replayed(self):
        value=envelope(nested_original());base.parse(value)
        self.assertEqual([x['binder'] for x in value['normalization']['steps']],[143,76])
        self.assertEqual(value['annotated']['function']['function']['function']['arguments'],[base.typ('Int')])
    def test_closed_int_shadow_bound_not_body(self):
        value=typeabs(76,ifprimitive(tyvar(76)),tyvar(76))
        result=t.substitute_closed_int_term(value,76)
        self.assertEqual(result['bound'],base.typ('Int'))
        self.assertEqual(result['body'],value['body'])
    def test_no_capture_of_other_binder(self):
        value=typeabs(99,{'tag':'lambda','parameter':base.name(1),'parameter_type':tyvar(76),
                           'body':{'tag':'var','name':base.name(1)}},tyvar(76))
        result=t.substitute_closed_int_term(value,76)
        self.assertEqual(result['id'],99);self.assertEqual(result['bound'],base.typ('Int'))
        self.assertEqual(result['body']['parameter_type'],base.typ('Int'))
    def test_type_apply_uses_original_constructor_folding(self):
        typ={'tag':'apply','function':{'tag':'constructor','name':'Box','arguments':[]},'argument':tyvar(7)}
        self.assertEqual(t.substitute_closed_int_type(typ,7),{'tag':'constructor','name':'Box','arguments':[base.typ('Int')]})
    def test_refl_is_explicit_step(self):
        n=typeapp(conditional(base.lit(True),base.lit(1),base.lit(2)),{'tag':'refl'})
        v=envelope(n);base.parse(v);self.assertEqual(v['normalization']['steps'],[{'rule':'erase_refl','witness':{'tag':'refl'}}])
    def test_unresolved_conditional_rejects(self):
        with self.assertRaises(t.BridgeError):t.normalize_conditional_raw(ifprimitive(tyvar(76)))
    def test_non_int_instantiation_rejects(self):
        n=typeapp(typeabs(76,ifprimitive(tyvar(76))),standard(base.typ('Bool')))
        with self.assertRaises(t.BridgeError):t.normalize_conditional_raw(n)
    def test_non_bottom_bound_rejects(self):
        n=typeapp(typeabs(76,ifprimitive(tyvar(76)),base.typ('Int')),standard(base.typ('Int')))
        with self.assertRaises(t.BridgeError):t.normalize_conditional_raw(n)
    def test_unknown_valid_proof_form_is_not_normalized(self):
        for proof in [{'tag':'hyp','id':1},{'tag':'intro','id':1},{'tag':'outer','id':1,'witness':{'tag':'refl'}}]:
            t.validate_computation(proof)
            with self.assertRaises(t.BridgeError):t.normalize_conditional_raw(typeapp(typeabs(76,ifprimitive(tyvar(76))),proof))
    def test_malformed_proof_extra_key_rejects(self):
        v=envelope(nested_original());v['normalization']['original_annotated']['function']['function']['witness']['extra']=0
        with self.assertRaises(t.BridgeError):base.parse(v)
    def test_text_proof_is_not_evidence(self):
        v=envelope(nested_original());v['normalization']['original_annotated']['function']['function']['witness']='inner(bot(Int)); elim'
        with self.assertRaises(t.BridgeError):base.parse(v)
    def test_step_witness_tamper_rejects(self):
        for mutation in ['extra','binder','argument','order','boolean-binder']:
            v=envelope(nested_original());steps=v['normalization']['steps']
            if mutation=='extra':steps[0]['extra']=True
            elif mutation=='binder':steps[0]['binder']=999
            elif mutation=='argument':steps[0]['argument']=base.typ('Bool')
            elif mutation=='order':steps.reverse()
            else:steps[0]['binder']=True
            with self.assertRaises(t.BridgeError):base.parse(v)
    def test_false_recheck_flag_rejects(self):
        for key in ['original_rechecked','normalized_rechecked','root_type_alpha_equal','erasure_equal']:
            for bad in [False,1,'true']:
                v=envelope(nested_original());v['normalization'][key]=bad
                with self.assertRaises(t.BridgeError):base.parse(v)
    def test_original_erasure_tamper_rejects(self):
        v=envelope(nested_original());v['normalization']['original_erased']['argument']['value']=1
        with self.assertRaises(t.BridgeError):base.parse(v)
    def test_normalized_raw_tamper_rejects(self):
        v=envelope(nested_original());v['normalization']['normalized_annotated']['argument']['value']=1
        with self.assertRaises(t.BridgeError):base.parse(v)
    def test_policy_cannot_hide_conditional(self):
        v=envelope(nested_original());v['normalization']['policy']='identity-no-conditional/1'
        with self.assertRaises(t.BridgeError):base.parse(v)
    def test_full_raw_datatype_retained_and_unchanged(self):
        n={'tag':'with_data','declarations':[{'tag':'data','name':'Box','parameters':[],
            'constructors':[{'name':'Box','fields':[{'tag':'applied','name':'Int','arguments':[]}]}]}],
            'body':conditional(base.lit(True),base.lit(1),base.lit(2))}
        v=envelope(n);v['representation']['custom_datatypes']=[{'datatype':'Box','constructor':'Box','arity':1,'fields':[base.typ('Int')]}];base.parse(v)
        v['normalization']['normalized_annotated']['declarations'][0]['name']='Changed'
        with self.assertRaises(t.BridgeError):base.parse(v)
    def test_partial_conditional_rejects(self):
        v=envelope(base.app(ifprimitive(),base.lit(True)))
        with self.assertRaises(t.BridgeError):p.plan(base.parse(v))
    def test_branch_types_not_inferred_from_erasure(self):
        v=envelope(conditional(base.lit(True),base.lit(42),base.lit(False)))
        with self.assertRaises(t.BridgeError):p.plan(base.parse(v))
    def test_planner_delays_both_entire_alternatives(self):
        n=conditional(base.lit(True),base.app(base.app(base.primitive(8),base.lit(20)),base.lit(22)),base.lit(0))
        candidate=p.plan(base.parse(envelope(n)));program=candidate['program'];self.assertEqual(program['version'],7)
        self.assertFalse(any(x['op']=='select_i64' for x in program['entry']))
        key,mapping=next(iter(candidate['binding']['source_map']['conditionals'].items()));body=program['codes'][key]['body']
        self.assertEqual([x['op'] for x in body],['scalar','force','thunk','thunk','select_i64','drop','return'])
        select=body[4];self.assertNotEqual(select['then'],select['else']);self.assertEqual(select['condition'],body[1]['out'])
        self.assertEqual(mapping['type_arguments'],[base.typ('Int')]);self.assertTrue(mapping['both_alternatives_delayed'])
        self.assertFalse(any(x['op']=='prim2' for x in body))
        self.assertEqual(body[-1]['value'],select['out'])
    def test_local_conditional_name_is_not_primitive(self):
        n={'tag':'let','name':base.name(1,'ifThenElse'),'value':base.lit(42),'body':{'tag':'var','name':base.name(1,'ifThenElse')}}
        candidate=p.plan(base.parse(base.envelope(n)))
        self.assertEqual(candidate['binding']['source_map']['conditionals'],{})
    def test_unknown_v2_envelope_rejects(self):
        v=envelope(nested_original());v['format']='mlf-checked-recursion-export/2'
        with self.assertRaises(t.BridgeError):base.parse(v)

if __name__=='__main__':unittest.main()
