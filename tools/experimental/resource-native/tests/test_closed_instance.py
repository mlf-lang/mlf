"""Replay/schema controls. Synthetic envelopes do not establish compiler origin.

The raw analysis fixture is a separately checked-source observer artifact; tests
construct synthetic envelopes from it, never relabel them as genuine exports.
"""
import copy,json,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import test_scalar_transport as b
t=b.t;p=b.planner
INT=b.typ('Int');BOOL=b.typ('Bool');BOT={'tag':'bottom'}
def v(i):return {'tag':'var','name':b.name(i)}
def tv(i):return {'tag':'var','id':i}
def lam(i,ty,body):return {'tag':'lambda','parameter':b.name(i),'parameter_type':ty,'body':body}
def tabs(i,body,bound=BOT):return {'tag':'type_lambda','id':i,'bound':copy.deepcopy(bound),'body':body}
def seq(a,c):return {'tag':'then','first':a,'second':c}
def inst(ty):return seq({'tag':'inner','witness':{'tag':'bottom','type':ty}},{'tag':'elim'})
def tapp(n,*proofs):
 for q in proofs:n={'tag':'type_application','value':n,'witness':q}
 return n
def let(i,rhs,body):return {'tag':'let','name':b.name(i),'value':rhs,'body':body}
def poly(i=10):return tabs(i,lam(20,tv(i),v(20)))
def raw_decl(name='Maybe',param='a',target=None):
 return {'tag':'data','name':name,'parameters':[param],'constructors':[
  {'name':'Nothing'+name,'fields':[]},{'name':'Just'+name,'fields':[target or {'tag':'parameter','name':param}]}]}
def actual_raw():
 return json.loads((pathlib.Path(__file__).parent/'data/closed-instance-raw-analysis.json').read_text())['raw_annotated']
def envelope(raw):
 normalized,steps=t.normalize_closed_instances_raw(copy.deepcopy(raw));root=t.raw_infer_type(normalized)
 value=b.envelope(t.strip_data_evidence(normalized),root['name']);value['checked_type']=root
 value['format']='mlf-checked-recursion-export/6';value['representation']['sum_instances']=[]
 ds=raw['declarations']if raw['tag']=='with_data'else []
 records,templates,instances=t.declaration_views(ds,normalized)
 value['representation'].update(custom_datatypes=records,custom_sums=templates,sum_instances=instances)
 value['normalization'].update(policy='single-closed-instance/1',original_checked_type=root,
  original_annotated=copy.deepcopy(raw),normalized_annotated=normalized,steps=steps,
  original_erased=t.projection(raw,True,True),original_term_skeleton=t.term_skeleton(raw),normalized_term_skeleton=t.term_skeleton(normalized))
 return value
class ClosedInstance(unittest.TestCase):
 def test_actual_raw_three_step_replay_same_graph(self):
  raw=actual_raw();value=envelope(raw);n=value['normalization'];self.assertEqual([x['rule']for x in n['steps']],['instantiate_closed','instantiate_closed','specialize_let'])
  self.assertEqual([x['binder']for x in n['steps'][:2]],[269,159]);step=n['steps'][2]
  self.assertEqual(step['binding'],{'id':2,'hint':'maybe'});self.assertEqual([x['id']for x in step['type_binders']],[13,14]);self.assertEqual(step['arguments'],[INT,INT])
  self.assertEqual(t.term_skeleton(raw),t.term_skeleton(n['normalized_annotated']));b.parse(value)
 def test_actual_raw_concrete_core_table(self):
  out=p.plan(b.parse(envelope(actual_raw())));self.assertEqual(out['program']['version'],7)
  self.assertEqual(out['program']['families'],{'F0':{'variants':['Nothing','Just'],'fields':{'Nothing':[],'Just':['#i64']}}})
  self.assertEqual(out['binding']['source_map']['sum_families']['F0']['arguments'],[INT])
 def test_repeated_use_keeps_same_let_and_variable(self):
  raw=let(1,poly(),b.app(b.app(b.primitive(8),b.app(tapp(v(1),inst(INT)),b.lit(21))),b.app(tapp(v(1),inst(INT)),b.lit(21))))
  out,steps=t.normalize_closed_instances_raw(raw);self.assertEqual(out['tag'],'let');self.assertEqual(out['name'],raw['name']);self.assertEqual(len(steps),1);self.assertEqual(len(steps[0]['occurrences']),2);self.assertEqual(t.term_skeleton(raw),t.term_skeleton(out))
 def test_two_prefix_order_and_nested_proofs(self):
  raw=let(1,tabs(10,tabs(11,lam(20,tv(10),lam(21,tv(11),v(20))))),b.app(b.app(tapp(v(1),inst(INT),inst(BOOL)),b.lit(1)),b.lit(True)))
  out,steps=t.normalize_closed_instances_raw(raw);self.assertEqual(steps[0]['arguments'],[INT,BOOL]);self.assertEqual(t.raw_infer_type(out),INT)
 def test_proof_association_and_explicit_inside_pair_identity(self):
  q=seq({'tag':'inner','witness':{'tag':'bottom','type':INT}},seq({'tag':'refl'},{'tag':'elim'}))
  out,steps=t.normalize_closed_instances_raw(tapp(poly(),q));self.assertEqual([s['rule']for s in steps],['erase_refl','instantiate_closed']);self.assertEqual(steps[1]['witness'],q);self.assertEqual(out['parameter_type'],INT)
 def test_nonidentity_inside_pair_rejects(self):
  q=seq({'tag':'inner','witness':{'tag':'bottom','type':INT}},seq({'tag':'hyp','id':9},{'tag':'elim'}))
  with self.assertRaises(t.BridgeError):t.normalize_closed_instances_raw(tapp(poly(),q))
 def test_deferred_nested_spine_visits_base_once(self):
  inside=tapp(tabs(11,tabs(12,lam(20,tv(12),v(20)))),inst(INT),inst(tv(10)))
  raw=let(1,tabs(10,inside),b.app(tapp(v(1),inst(INT)),b.lit(42)))
  out,steps=t.normalize_closed_instances_raw(raw)
  self.assertEqual([x['rule']for x in steps],['specialize_let','instantiate_closed','instantiate_closed'])
  self.assertEqual(t.raw_infer_type(out),INT);self.assertEqual(t.term_skeleton(raw),t.term_skeleton(out))
 def test_proof_pair_cannot_cross_nested_wrapper_boundary(self):
  raw=tapp(poly(),{'tag':'inner','witness':{'tag':'bottom','type':INT}},{'tag':'elim'})
  with self.assertRaises(t.BridgeError):t.normalize_closed_instances_raw(raw)
 def test_proof_64_atom_budget(self):
  def q(n):
   a={'tag':'refl'}
   for _ in range(n-1):a=seq(a,{'tag':'refl'})
   return a
  self.assertEqual(len(t.closed_proof_actions(q(64))),64)
  with self.assertRaises(t.BridgeError):t.closed_proof_actions(q(65))
 def test_all_unknown_proofs_reject_not_skip(self):
  for q in [{'tag':'elim'},{'tag':'hyp','id':1},{'tag':'intro','id':1},{'tag':'outer','id':1,'witness':{'tag':'refl'}},{'tag':'inner','witness':{'tag':'refl'}}]:
   with self.subTest(q=q),self.assertRaises(t.BridgeError):t.normalize_closed_instances_raw(tapp(poly(),q))
 def test_closed_target_limits(self):
  for ty in [b.typ('()'),b.typ('Maybe'),tv(99),{'tag':'arrow','from':INT,'to':INT}]:
   with self.subTest(ty=ty),self.assertRaises(t.BridgeError):t.normalize_closed_instances_raw(tapp(poly(),inst(ty)))
 def test_partial_extra_duplicate_prefix_reject(self):
  for raw in [tapp(tabs(10,poly(11)),inst(INT)),tapp(poly(),seq(inst(INT),inst(INT))),tapp(tabs(10,poly(10)),seq(inst(INT),inst(INT)))]:
   with self.subTest(raw=raw),self.assertRaises(t.BridgeError):t.normalize_closed_instances_raw(raw)
 def test_wrong_bound_and_kind_reject(self):
  for bound in [INT,{'tag':'bottom_kind','kind':{'tag':'arrow','from':{'tag':'star'},'to':{'tag':'star'}}}]:
   with self.subTest(bound=bound),self.assertRaises(t.BridgeError):t.normalize_closed_instances_raw(tapp(tabs(10,lam(20,tv(10),v(20)),bound),inst(INT)))
 def test_shadowed_bound_substituted_body_untouched(self):
  n=tabs(10,lam(20,tv(10),v(20)),tv(10));out=t.substitute_closed_term(n,10,INT)
  self.assertEqual(out['bound'],INT);self.assertEqual(out['body'],n['body'])
 def test_let_binder_not_in_rhs_scope(self):
  body=let(1,tapp(v(1),inst(INT)),b.lit(42));out,args,uses=t.closed_occurrences(body,b.name(1),[{'id':10,'bound':BOT}],[])
  self.assertEqual(args,[INT]);self.assertEqual(uses[0]['path'],['value']);self.assertEqual(out['value'],v(1))
 def test_shadowed_uses_not_counted(self):
  body=b.app(tapp(v(1),inst(INT)),lam(1,INT,v(1)));_,args,uses=t.closed_occurrences(body,b.name(1),[{'id':10,'bound':BOT}],[])
  self.assertEqual(len(uses),1);self.assertEqual(uses[0]['path'],['function'])
 def test_bare_alias_capture_open_unused_reject(self):
  for body in [v(1),let(2,v(1),b.lit(42)),lam(9,INT,v(1)),tapp(v(1),inst(tv(99))),b.lit(42)]:
   with self.subTest(body=body),self.assertRaises(t.BridgeError):t.normalize_closed_instances_raw(let(1,poly(),body))
 def test_mixed_term_instance_reject(self):
  body=b.app(tapp(v(1),inst(INT)),tapp(v(1),inst(BOOL)))
  with self.assertRaises(t.BridgeError):t.normalize_closed_instances_raw(let(1,poly(),body))
 def test_recursive_polymorphism_reject(self):
  raw={'tag':'letrec','bindings':[{'name':b.name(1),'type':{'tag':'forall','id':10,'bound':BOT,'body':{'tag':'arrow','from':tv(10),'to':tv(10)}},'value':poly()}],'body':b.app(tapp(v(1),inst(INT)),b.lit(42))}
  with self.assertRaises(t.BridgeError):t.normalize_closed_instances_raw(raw)
 def test_concrete_annotations_reject_bottom_and_residual_apply(self):
  for ty in [BOT,{'tag':'bottom_kind','kind':{'tag':'star'}},{'tag':'apply','function':INT,'argument':BOOL}]:
   with self.subTest(ty=ty),self.assertRaises(t.BridgeError):t.normalize_closed_instances_raw(lam(1,ty,b.lit(42)))
 def test_all_occurrences_witness_and_substitution_mutations(self):
  base=envelope(actual_raw())
  changes=[lambda n:n['steps'].pop(),lambda n:n['steps'][-1]['occurrences'].clear(),lambda n:n['steps'][-1]['occurrences'].append(copy.deepcopy(n['steps'][-1]['occurrences'][0])),lambda n:n['steps'][-1]['occurrences'][0]['path'].append('body'),lambda n:n['steps'][-1]['arguments'].__setitem__(0,BOOL),lambda n:n['steps'][-1]['type_binders'][0].__setitem__('id',99),lambda n:n.__setitem__('normalized_rechecked',False),lambda n:n['original_term_skeleton'].__setitem__('tag','forged'),lambda n:n['steps'][0]['witness'].__setitem__('extra',1)]
  for change in changes:
   x=copy.deepcopy(base);change(x['normalization'])
   with self.subTest(change=change),self.assertRaises(t.BridgeError):b.parse(x)
 def test_no_fallback_to_historical_policy(self):
  x=envelope(actual_raw());n=x['normalization'];n['policy']='identity-no-conditional/1';n.pop('original_term_skeleton');n.pop('normalized_term_skeleton');n['steps']=[]
  with self.assertRaises(t.BridgeError):b.parse(x)
 def test_generic_template_and_instance_mutations_reject(self):
  base=envelope(actual_raw())
  changes=[lambda r:r['custom_sums'][0].__setitem__('declaration_index',1),lambda r:r['custom_sums'][0]['parameters'][0].__setitem__('name','forged'),lambda r:r['custom_sums'][0]['constructors'].pop(),lambda r:r['sum_instances'][0].__setitem__('arguments',[BOOL]),lambda r:r['sum_instances'][0]['constructors'][1].__setitem__('fields',[BOOL]),lambda r:r['sum_instances'].clear(),lambda r:r['sum_instances'][0].__setitem__('extra',True)]
  for change in changes:
   x=copy.deepcopy(base);change(x['representation'])
   with self.subTest(change=change),self.assertRaises(t.BridgeError):b.parse(x)
 def test_original_and_normalized_declaration_tamper_reject(self):
  for key in ['original_annotated','normalized_annotated']:
   x=envelope(actual_raw());x['normalization'][key]['declarations'][0]['constructors'][1]['fields'][0]['name']='forged'
   with self.assertRaises(t.BridgeError):b.parse(x)
 def test_generic_formal_name_is_not_hardcoded(self):
  ds=[raw_decl('Boxed','payload')];node={'tag':'constructor','name':'JustBoxed','arguments':[BOOL]}
  _,templates,instances=t.declaration_views(ds,node);self.assertEqual(templates[0]['parameters'][0]['name'],'payload');self.assertEqual(instances[0]['constructors'][1]['fields'],[BOOL])
 def test_one_vector_per_declaration(self):
  ds=[raw_decl()];a={'tag':'constructor','name':'JustMaybe','arguments':[INT]};c={'tag':'constructor','name':'NothingMaybe','arguments':[BOOL]}
  with self.assertRaises(t.BridgeError):t.declaration_views(ds,let(1,a,c))
 def test_unused_parameterized_decl_reject(self):
  with self.assertRaises(t.BridgeError):t.declaration_views([raw_decl()],b.lit(42))
 def test_complete_recursive_instance_closure(self):
  ds=[raw_decl('Chain','x',{'tag':'applied','name':'Chain','arguments':[{'tag':'parameter','name':'x'}]})]
  _,_,instances=t.declaration_views(ds,{'tag':'constructor','name':'NothingChain','arguments':[INT]})
  self.assertEqual(instances[0]['constructors'][1]['fields'],[{'tag':'constructor','name':'Chain','arguments':[INT]}])
 def test_mutual_instance_closure_and_exact_order(self):
  ds=[raw_decl('A','x',{'tag':'applied','name':'B','arguments':[{'tag':'parameter','name':'x'}]}),raw_decl('B','y',{'tag':'applied','name':'A','arguments':[{'tag':'parameter','name':'y'}]})]
  _,_,instances=t.declaration_views(ds,{'tag':'constructor','name':'NothingA','arguments':[BOOL]});self.assertEqual([x['datatype']for x in instances],['A','B']);self.assertEqual([x['arguments']for x in instances],[[BOOL],[BOOL]])
 def test_expanding_instance_reject(self):
  ds=[raw_decl('A','x',{'tag':'applied','name':'A','arguments':[{'tag':'applied','name':'A','arguments':[{'tag':'parameter','name':'x'}]}]})]
  with self.assertRaises(t.BridgeError):t.declaration_views(ds,{'tag':'constructor','name':'NothingA','arguments':[INT]})
 def test_unused_variant_field_not_pruned(self):
  ds=[raw_decl('A','x',{'tag':'function','from':{'tag':'parameter','name':'x'},'to':{'tag':'parameter','name':'x'}})]
  with self.assertRaises(t.BridgeError):t.declaration_views(ds,{'tag':'constructor','name':'NothingA','arguments':[INT]})
if __name__=='__main__':unittest.main()
