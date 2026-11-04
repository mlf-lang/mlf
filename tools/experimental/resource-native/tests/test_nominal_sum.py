"""Synthetic exact-family transport/planner controls; not compiler-origin claims."""
import copy,json,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import test_scalar_transport as b
t=b.t;p=b.planner

def constructor(n):return {'tag':'constructor','name':n,'arguments':[]}
def declaration(name='Flag',variants=('Flexible','Rigid')):
 return {'tag':'data','name':name,'parameters':[],'constructors':[{'name':n,'fields':[]} for n in variants]}
def case(scrutinee=None,variants=('Flexible','Rigid')):
 return {'tag':'case','scrutinee':scrutinee or constructor(variants[0]),'result_type':b.typ('Int'),
  'alternatives':[{'pattern':{'constructor':n,'fields':[]},'body':b.lit(20+i)}for i,n in enumerate(variants)]}
def envelope(body=None,declarations=None):
 ds=copy.deepcopy(declarations or [declaration()]);body=body or case();v=b.envelope(body)
 raw={'tag':'with_data','declarations':ds,'body':copy.deepcopy(body)}
 v['normalization'].update(original_annotated=copy.deepcopy(raw),normalized_annotated=copy.deepcopy(raw))
 # Hand-derived metadata for these nullary fixtures, not declaration_views output.
 v['representation']['custom_sums']=[{'declaration_index':i,'datatype':d['name'],
  'parameters':[{'name':x,'kind':{'tag':'star'}}for x in d['parameters']],
  'constructors':[{'constructor':c['name'],'arity':0,'fields':[]}for c in d['constructors']]}for i,d in enumerate(ds)]
 v['representation']['sum_instances']=[{'declaration_index':i,'datatype':d['name'],'arguments':[],
  'constructors':[{'constructor':c['name'],'arity':0,'fields':[]}for c in d['constructors']]}for i,d in enumerate(ds)]
 return v
def plan(v):return p.plan(b.parse(v))

class NominalSum(unittest.TestCase):
 def test_actual_nominal_family_and_variant_table(self):
  v=plan(envelope());program=v['program'];self.assertEqual(program['version'],7)
  self.assertEqual(program['families'],{'F0':{'variants':['Flexible','Rigid'],'fields':{'Flexible':[],'Rigid':[]}}})
  self.assertEqual(v['binding']['source_map']['sum_families']['F0']['datatype'],'Flag')
  code=next(iter(v['binding']['source_map']['sum_cases']));ops=program['codes'][code]['body']
  self.assertEqual([x['op'] for x in ops],['construct_nullary','force','thunk','thunk','case_i64','drop','return'])
  self.assertEqual(ops[0]['family'],ops[4]['family']);self.assertEqual(ops[4]['scrutinee'],ops[1]['out'])
 def test_generic_renamed_three_variant_family(self):
  names=('Red','Amber','Green');v=plan(envelope(case(constructor('Green'),names),[declaration('Signal',names)]))
  self.assertEqual(v['program']['families']['F0']['variants'],list(names))
 def test_declaration_order_not_alternative_order(self):
  n=case();n['alternatives'].reverse();v=plan(envelope(n));code=next(iter(v['binding']['source_map']['sum_cases']))
  op=next(x for x in v['program']['codes'][code]['body']if x['op']=='case_i64')
  self.assertEqual(list(op['arms']),['Flexible','Rigid'])
 def test_lazy_whole_unselected_case(self):
  n=case();n['alternatives'][1]['body']=case();v=plan(envelope(n));outer=min(v['binding']['source_map']['sum_cases'],key=lambda s:int(s[1:]))
  body=v['program']['codes'][outer]['body'];self.assertEqual(sum(x['op']=='force'for x in body),1)
  for code in v['binding']['source_map']['sum_cases'][outer]['arm_codes'].values():self.assertNotEqual(code,outer)
 def test_alias_capture_has_independent_branch_owners(self):
  n=case();n['alternatives']=[{'pattern':{'constructor':c,'fields':[]},'body':{'tag':'var','name':b.name(1)}}for c in ['Flexible','Rigid']]
  n={'tag':'let','name':b.name(1),'value':b.lit(21),'body':n};v=plan(envelope(n));code=next(iter(v['binding']['source_map']['sum_cases']))
  op=next(x for x in v['program']['codes'][code]['body']if x['op']=='case_i64')
  self.assertEqual(len(set(op['arms'].values())),2)
 def test_missing_family_rejects(self):
  for view in ['custom_sums','sum_instances']:
   with self.subTest(view=view):
    v=envelope();v['representation'][view]=[]
    with self.assertRaises(t.BridgeError):plan(v)
 def test_omitted_constructor_rejects(self):
  for view in ['custom_sums','sum_instances']:
   with self.subTest(view=view):
    v=envelope();v['representation'][view][0]['constructors'].pop()
    with self.assertRaises(t.BridgeError):plan(v)
 def test_wrong_constructor_order_rejects(self):
  for view in ['custom_sums','sum_instances']:
   with self.subTest(view=view):
    v=envelope();v['representation'][view][0]['constructors'].reverse()
    with self.assertRaises(t.BridgeError):plan(v)
 def test_foreign_family_case_rejects(self):
  n=case();n['alternatives'][1]['pattern']['constructor']='Other'
  with self.assertRaises(t.BridgeError):plan(envelope(n))
 def test_duplicate_case_rejects(self):
  n=case();n['alternatives'][1]['pattern']['constructor']='Flexible'
  with self.assertRaises(t.BridgeError):plan(envelope(n))
 def test_incomplete_case_rejects(self):
  n=case();n['alternatives'].pop()
  with self.assertRaises(t.BridgeError):plan(envelope(n))
 def test_case_nonzero_fields_rejects(self):
  n=case();n['alternatives'][0]['pattern']['fields']=[b.name(8)]
  with self.assertRaises(t.BridgeError):plan(envelope(n))
 def test_unchosen_illtyped_body_rejects(self):
  n=case();n['alternatives'][1]['body']=b.lit(True)
  with self.assertRaises(t.BridgeError):plan(envelope(n))
 def test_bool_result_case_rejects(self):
  n=case();n['result_type']=b.typ('Bool')
  for a in n['alternatives']:a['body']=b.lit(True)
  with self.assertRaises(t.BridgeError):plan(envelope(n))
 def test_bool_is_not_nominal_scrutinee(self):
  with self.assertRaises(t.BridgeError):plan(envelope(case(b.lit(True))))
 def test_boolean_arity_rejects(self):
  for view in ['custom_sums','sum_instances']:
   with self.subTest(view=view):
    v=envelope();v['representation'][view][0]['constructors'][0]['arity']=False
    with self.assertRaises(t.BridgeError):plan(v)
 def test_boolean_declaration_index_rejects(self):
  for view in ['custom_sums','sum_instances']:
   for index in [0,1]:
    with self.subTest(view=view,index=index):
     v=envelope(declarations=[declaration(),declaration('Signal',('Red','Green'))])
     v['representation'][view][index]['declaration_index']=bool(index)
     with self.assertRaises(t.BridgeError):plan(v)
 def test_normalized_declaration_tamper_rejects(self):
  v=envelope();v['normalization']['normalized_annotated']['declarations'][0]['name']='Changed'
  with self.assertRaises(t.BridgeError):plan(v)
 def test_unresolved_parameterized_family_rejects(self):
  # This fixture supplies no closed arguments; export/6 admits only resolved instances.
  d=declaration();d['parameters']=['a']
  with self.assertRaises(t.BridgeError):plan(envelope(declarations=[d]))
 def test_nonzero_constructor_metadata_rejects(self):
  for view in ['custom_sums','sum_instances']:
   with self.subTest(view=view):
    field={'tag':'applied','name':'Int','arguments':[]}if view=='custom_sums'else b.typ('Int')
    v=envelope();v['representation'][view][0]['constructors'][0].update(arity=1,fields=[field])
    with self.assertRaises(t.BridgeError):plan(v)
 def test_reserved_nominal_identity_rejects(self):
  for name in ['Int','Bool','IO','[]','MLFCallStack','True']:
   with self.assertRaises(t.BridgeError):plan(envelope(declarations=[declaration(name)]))
 def test_cross_family_constructor_collision_rejects(self):
  with self.assertRaises(t.BridgeError):plan(envelope(declarations=[declaration(),declaration('Other',('Flexible','Other'))]))
 def test_internal_builtin_record_constructor_shadow_rejects(self):
  v=b.envelope(b.lit(42));raw={'tag':'with_data','declarations':[{'tag':'data','name':'Shadow','parameters':[],
       'constructors':[{'name':'MLFStackFrame','fields':[]}]}],'body':b.lit(42)}
  v['normalization'].update(original_annotated=copy.deepcopy(raw),normalized_annotated=copy.deepcopy(raw))
  v['representation']['custom_datatypes']=[{'datatype':'Shadow','constructor':'MLFStackFrame','arity':0,'fields':[]}]
  with self.assertRaises(t.BridgeError):plan(v)
 def test_extra_metadata_key_rejects(self):
  for view in ['custom_sums','sum_instances']:
   with self.subTest(view=view):
    v=envelope();v['representation'][view][0]['tag']='unchecked'
    with self.assertRaises(t.BridgeError):plan(v)

if __name__=='__main__':unittest.main()
