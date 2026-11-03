"""Synthetic field transport/planning controls, never compiler-origin claims."""
import copy,json,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import test_scalar_transport as b
t=b.t;p=b.planner

def rawtype(name):return {'tag':'applied','name':name,'arguments':[]}
def decl(name='Kind', variants=None):
 return {'tag':'data','name':name,'parameters':[], 'constructors':variants or [
  {'name':'Star','fields':[]},{'name':'KArrow','fields':[rawtype(name),rawtype(name)]}]}
def con(name,*args):
 n={'tag':'constructor','name':name,'arguments':[]}
 for a in args:n=b.app(n,a)
 return n
def var(i):return {'tag':'var','name':b.name(i)}
def case(scrutinee,arms):return {'tag':'case','scrutinee':scrutinee,'result_type':b.typ('Int'),
 'alternatives':[{'pattern':{'constructor':name,'fields':fields},'body':body}for name,fields,body in arms]}
def envelope(body,declarations):
 value=b.envelope(body);raw={'tag':'with_data','declarations':copy.deepcopy(declarations),'body':copy.deepcopy(body)}
 value['normalization'].update(original_annotated=copy.deepcopy(raw),normalized_annotated=copy.deepcopy(raw))
 def ft(x):
  if x['tag']=='applied':return {'tag':'constructor','name':x['name'],'arguments':[ft(a)for a in x['arguments']]}
  if x['tag']=='function':return {'tag':'arrow','from':ft(x['from']),'to':ft(x['to'])}
  return copy.deepcopy(x)
 # Derive the two fixture views independently, without production declaration_views.
 # Template fields retain raw syntax; instance fields use closed transport types.
 value['representation']['custom_sums']=[{'declaration_index':i,'datatype':d['name'],
  'parameters':[{'name':x,'kind':{'tag':'star'}}for x in d['parameters']],
  'constructors':[{'constructor':c['name'],'arity':len(c['fields']),
   'fields':copy.deepcopy(c['fields'])}for c in d['constructors']]}for i,d in enumerate(declarations)if len(d['constructors'])>1]
 value['representation']['sum_instances']=[{'declaration_index':i,'datatype':d['name'],'arguments':[],
  'constructors':[{'constructor':c['name'],'arity':len(c['fields']),
   'fields':[ft(f)for f in c['fields']]}for c in d['constructors']]}for i,d in enumerate(declarations)if len(d['constructors'])>1]
 value['representation']['custom_datatypes']=[{'datatype':d['name'],'constructor':d['constructors'][0]['name'],
  'arity':len(d['constructors'][0]['fields']),'fields':[ft(f)for f in d['constructors'][0]['fields']]}for d in declarations if len(d['constructors'])==1]
 return value
def plan(v):return p.plan(b.parse(v))
def pair(fields=('Int','Bool'),value=None,arms=None):
 d=decl('PairSum',[{'name':'Empty','fields':[]},{'name':'Pair','fields':[rawtype(x)for x in fields]}])
 n=case(value or con('Pair',b.lit(21),b.lit(True)),arms or [('Empty',[],b.lit(0)),('Pair',[b.name(1),None],var(1))])
 return envelope(n,[d])
def factory(v):
 code=next(iter(v['binding']['source_map']['field_cases']));body=v['program']['codes'][code]['body']
 return code,body,next(x for x in body if x['op']=='case_fields_i64')

class FieldSum(unittest.TestCase):
 def test_complete_recursive_family_fields(self):
  n=case(con('KArrow',con('Star'),con('Star')),[('Star',[],b.lit(0)),('KArrow',[None,None],b.lit(1))])
  v=plan(envelope(n,[decl()]));self.assertEqual(v['program']['families'],{'F0':{'variants':['Star','KArrow'],'fields':{'Star':[],'KArrow':['%F0','%F0']}}})
  _,body,op=factory(v);self.assertEqual(op['arms']['KArrow']['captures'],{})
  ctor=next(x for x in body if x['op']=='construct_sum');self.assertEqual(len(ctor['fields']),2)
 def test_mutually_recursive_families_register_before_fields(self):
  ds=[decl('A',[{'name':'A0','fields':[]},{'name':'A1','fields':[rawtype('B')]}]),decl('B',[{'name':'B0','fields':[]},{'name':'B1','fields':[rawtype('A')]}])]
  v=plan(envelope(b.lit(42),ds));self.assertEqual(v['program']['families']['F0']['fields']['A1'],['%F1']);self.assertEqual(v['program']['families']['F1']['fields']['B1'],['%F0'])
 def test_scalar_field_types_and_position(self):
  v=plan(pair());_,body,op=factory(v);self.assertEqual(v['program']['families']['F0']['fields']['Pair'],['#i64','#bool'])
  a=op['arms']['Pair'];self.assertEqual(list(a['captures'].values()),[{'kind':'field','index':0}]);self.assertEqual(v['program']['codes'][a['code']]['captures'][next(iter(a['captures']))]['relation'],'down')
  self.assertEqual(sum(x['op']=='force'for x in body),1);self.assertFalse(any(x['op'] in ['thunk','field','borrow']for x in body))
 def test_factory_delays_entire_arm_and_defines_both_codes(self):
  nested=case(con('Empty'),[('Empty',[],b.lit(4)),('Pair',[None,None],b.lit(5))])
  v=plan(pair(arms=[('Empty',[],nested),('Pair',[b.name(1),None],var(1))]));outer=min(v['binding']['source_map']['field_cases'],key=lambda x:int(x[1:]))
  body=v['program']['codes'][outer]['body'];op=next(x for x in body if x['op']=='case_fields_i64')
  self.assertEqual(len(op['arms']),2);self.assertFalse(any(x['op']=='thunk'for x in body))
  self.assertTrue(any(x['op']=='thunk'for x in v['program']['codes'][op['arms']['Empty']['code']]['body']))
 def test_source_arm_order_does_not_change_variant_positions(self):
  e=pair();e['annotated']['alternatives'].reverse();body=e['annotated'];e=envelope(body,[decl('PairSum',[{'name':'Empty','fields':[]},{'name':'Pair','fields':[rawtype('Int'),rawtype('Bool')]}])])
  v=plan(e);self.assertEqual(list(factory(v)[2]['arms']),['Empty','Pair'])
 def test_alias_constructor_positions_are_distinct_owned_variables(self):
  n=case(con('Pair',var(9),var(9)),[('Empty',[],b.lit(0)),('Pair',[b.name(1),b.name(2)],b.app(b.app(b.primitive(8),var(1)),var(2)))])
  n={'tag':'let','name':b.name(9),'value':b.lit(21),'body':n}
  d=decl('PairSum',[{'name':'Empty','fields':[]},{'name':'Pair','fields':[rawtype('Int'),rawtype('Int')]}])
  v=plan(envelope(n,[d]));_,body,op=factory(v);ctor=next(x for x in body if x['op']=='construct_sum');self.assertEqual(len(set(ctor['fields'])),2)
  self.assertEqual({x['index']for x in op['arms']['Pair']['captures'].values()},{0,1})
 def test_field_10_is_positional_not_lexical(self):
  d=decl('Wide',[{'name':'Empty','fields':[]},{'name':'Wide','fields':[rawtype('Int')]*11}]);names=[None]*10+[b.name(10)]
  v=plan(envelope(case(con('Wide',*[b.lit(x)for x in range(11)]),[('Empty',[],b.lit(0)),('Wide',names,var(10))]),[d]));_,body,op=factory(v)
  self.assertEqual(list(op['arms']['Wide']['captures'].values()),[{'kind':'field','index':10}]);self.assertEqual(len(next(x for x in body if x['op']=='construct_sum')['fields']),11)
 def test_32_fields_boundary(self):
  d=decl('Wide',[{'name':'Empty','fields':[]},{'name':'Wide','fields':[rawtype('Int')]*32}]);v=plan(envelope(b.lit(1),[d]));self.assertEqual(len(v['program']['families']['F0']['fields']['Wide']),32)
 def test_33_fields_rejects_even_unused(self):
  d=decl('Wide',[{'name':'Empty','fields':[]},{'name':'Wide','fields':[rawtype('Int')]*33}])
  with self.assertRaises(t.BridgeError):plan(envelope(b.lit(1),[d]))
 def test_unit_record_arrow_unknown_fields_reject_even_unused(self):
  for ty in [rawtype('()'),rawtype('Box'),rawtype('Unknown'),{'tag':'function','from':rawtype('Int'),'to':rawtype('Int')}]:
   ds=[decl('Box',[{'name':'Box','fields':[rawtype('Int')]}]),decl('S',[{'name':'A','fields':[]},{'name':'B','fields':[ty]}])]
   with self.assertRaises(t.BridgeError):plan(envelope(b.lit(42),ds))
 def test_unreachable_fields_cannot_be_omitted(self):
  for view in ['custom_sums','sum_instances']:
   with self.subTest(view=view):
    field=rawtype('Int')if view=='custom_sums'else b.typ('Int')
    v=pair(value=con('Empty'));v['representation'][view][0]['constructors'][1].update(arity=1,fields=[field])
    with self.assertRaises(t.BridgeError):plan(v)
 def test_field_order_metadata_mutation_rejects(self):
  for view in ['custom_sums','sum_instances']:
   with self.subTest(view=view):
    v=pair();v['representation'][view][0]['constructors'][1]['fields'].reverse()
    with self.assertRaises(t.BridgeError):plan(v)
 def test_normalized_declaration_field_mutation_rejects(self):
  v=pair();v['normalization']['normalized_annotated']['declarations'][0]['constructors'][1]['fields'].reverse()
  with self.assertRaises(t.BridgeError):plan(v)
 def test_pattern_arity_rejects(self):
  for names in [[b.name(1)],[b.name(1),None,None]]:
   with self.assertRaises(t.BridgeError):plan(pair(arms=[('Empty',[],b.lit(0)),('Pair',names,var(1))]))
 def test_pattern_duplicate_ids_rejects(self):
  with self.assertRaises(t.BridgeError):plan(pair(arms=[('Empty',[],b.lit(0)),('Pair',[b.name(1),b.name(1)],var(1))]))
 def test_field_type_not_guessed_from_result(self):
  with self.assertRaises(t.BridgeError):plan(pair(arms=[('Empty',[],b.lit(0)),('Pair',[None,b.name(1)],var(1))]))
 def test_unchosen_whole_branch_checked(self):
  with self.assertRaises(t.BridgeError):plan(pair(value=con('Empty'),arms=[('Empty',[],b.lit(0)),('Pair',[None,None],b.lit(True))]))
 def test_no_extra_bitmap_trust(self):
  for view in ['custom_sums','sum_instances']:
   with self.subTest(view=view):
    v=pair();v['representation'][view][0]['constructors'][1]['bitmap']=1
    with self.assertRaises(t.BridgeError):plan(v)
 def test_external_capture_budget(self):
  for count in [32,33]:
   def balanced(xs):
    if len(xs)==1:return xs[0]
    cut=len(xs)//2;return b.app(b.app(b.primitive(8),balanced(xs[:cut])),balanced(xs[cut:]))
   expr=balanced([var(i)for i in range(100,100+count)])
   n=case(con('Empty'),[('Empty',[],expr),('Pair',[None,None],b.lit(0))])
   for i in reversed(range(100,100+count)):n={'tag':'let','name':b.name(i),'value':b.lit(1),'body':n}
   ds=[decl('PairSum',[{'name':'Empty','fields':[]},{'name':'Pair','fields':[rawtype('Int'),rawtype('Bool')]}])]
   if count==33:
    with self.assertRaisesRegex(t.BridgeError,'capture budget'):plan(envelope(n,ds))
   else:
    v=plan(envelope(n,ds));op=factory(v)[2];self.assertEqual(len(op['arms']['Empty']['captures']),32)

if __name__=='__main__':unittest.main()
