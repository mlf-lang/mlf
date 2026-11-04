"""Synthetic representation/planner/core guards; never authentic-source claims."""
import copy,hashlib,itertools,json,pathlib,sys,types,unittest
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
def load(path,name):
 m=types.ModuleType(name);m.__file__=str(path);sys.modules[name]=m;exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m
p=load(BASE/'planner.py','multi_view_test_planner');t=p.baseline
from resource_ir import check
INT={'tag':'constructor','name':'Int','arguments':[]};BOOL={'tag':'constructor','name':'Bool','arguments':[]}
def typ(name,*args):return {'tag':'constructor','name':name,'arguments':list(args)}
def raw(name,*args):return {'tag':'applied','name':name,'arguments':list(args)}
def formal(name):return {'tag':'parameter','name':name}
def name(n):return {'id':n,'hint':'x'+str(n)}
def var(n):return {'tag':'var','name':name(n)}
def lit(x):return {'tag':'bool'if type(x)is bool else'int64','value':x}
def app(f,*xs):
 for x in xs:f={'tag':'application','function':f,'argument':x}
 return f
def con(n,args=(),*xs):return app({'tag':'constructor','name':n,'arguments':list(args)},*xs)
def primitive(i):return {'tag':'primitive','id':i,'name':{8:'addInt',9:'subInt',14:'mulInt',10:'eqInt',11:'ltInt',13:'ifThenElse'}[i],'arguments':[INT]if i==13 else[]}
def case(n,arms):return {'tag':'case','scrutinee':n,'result_type':INT,'alternatives':[{'pattern':{'constructor':c,'fields':fields},'body':body}for c,fields,body in arms]}
def template(index=0,owner='Maybe',parameters=('a',),constructors=None):
 constructors=constructors or [('Nothing',[]),('Just',[formal('a')])]
 return {'declaration_index':index,'datatype':owner,'parameters':[{'name':n,'kind':{'tag':'star'}}for n in parameters],
         'constructors':[{'constructor':n,'arity':len(fs),'fields':fs}for n,fs in constructors]}
def substitute(f,env):
 if f['tag']=='parameter':return copy.deepcopy(env[f['name']])
 assert f['tag']=='applied';return typ(f['name'],*[substitute(x,env)for x in f['arguments']])
def metadata(templates=None,vectors=None,records=None):
 ts=copy.deepcopy(templates if templates is not None else[template()]);vectors=vectors if vectors is not None else{0:[[INT],[BOOL]]};views=[]
 for row in ts:
  for args in vectors[row['declaration_index']]:
   env=dict(zip([x['name']for x in row['parameters']],args));views.append({'declaration_index':row['declaration_index'],'datatype':row['datatype'],'arguments':copy.deepcopy(args),'view_index':len(views),'constructors':[{'constructor':c['constructor'],'arity':c['arity'],'fields':[substitute(f,env)for f in c['fields']]}for c in row['constructors']]})
 return {'builtin_unit':{'constructor':'()','datatype':'()','arity':0,'fields':[]},'builtin_scalars':[{'datatype':n,'kind':{'tag':'star'},'arity':0,'runtime_shape':s}for n,s in [('Int','#i64'),('Bool','#bool')]],'custom_datatypes':copy.deepcopy(records or[]),'custom_sums':ts,'sum_instances':views}
def envelope(body,m,format='mlf-checked-module-export/2'):
 data={'format':format,'representation':m,'annotated':body,'checked_type':INT};canonical=json.dumps(data,sort_keys=True,separators=(',',':'));return t.Envelope(canonical,hashlib.sha256(canonical.encode()).hexdigest())
def plan(body,m=None):
 answer=p.plan(envelope(body,m if m is not None else metadata()));checked=check(answer['program']);assert checked.sha256==answer['binding']['candidate_sha256'];return answer

def int_case(value=42):return case(con('Just',[INT],lit(value)),[('Nothing',[],lit(0)),('Just',[name(1)],var(1))])
def bool_case():return case(con('Just',[BOOL],lit(True)),[('Just',[name(2)],app(primitive(13),var(2),lit(0),lit(1))),('Nothing',[],lit(0))])

class ConcreteViews(unittest.TestCase):
 def test_actual_lookup_keeps_both_field_shapes(self):
  r=t.MultiViewRepresentation(metadata());a=r.constructor_for('Just',[INT]);b=r.constructor_for('Just',[BOOL]);self.assertNotEqual(a['shape'],b['shape']);self.assertEqual(a['field_shapes'],['#i64']);self.assertEqual(b['field_shapes'],['#bool']);self.assertEqual(r.constructors,{})
 def test_both_views_plan_and_pass_unchanged_core(self):
  v=plan(app(primitive(8),int_case(),bool_case()));self.assertEqual(v['program']['families'],{'F0':{'variants':['Nothing','Just'],'fields':{'Nothing':[],'Just':['#i64']}},'F1':{'variants':['Nothing','Just'],'fields':{'Nothing':[],'Just':['#bool']}}})
  for i in range(2):self.assertEqual(v['binding']['source_map']['sum_families']['F'+str(i)]['view_index'],i)
 def test_case_uses_scrutinee_view_not_last_constructor(self):
  v=plan(int_case());body=next(c['body']for c in v['program']['codes'].values()if any(i['op']=='case_fields_i64'for i in c['body']));op=next(i for i in body if i['op']=='case_fields_i64');self.assertEqual(op['family'],'F0');self.assertEqual(v['program']['codes'][op['arms']['Just']['code']]['captures'][next(iter(op['arms']['Just']['captures']))]['layout'],'#i64')
 def test_case_source_order_preserves_declaration_variant_order(self):
  v=plan(bool_case());entry=next(x for x in v['binding']['source_map']['field_cases'].values());self.assertEqual(entry['variants'],['Nothing','Just']);self.assertEqual(entry['view']['arguments'],[BOOL]);self.assertEqual(list(entry['arms']),['Nothing','Just'])
 def test_whole_family_wildcard_field_preserved(self):
  v=plan(case(con('Just',[INT],lit(42)),[('Nothing',[],lit(0)),('Just',[None],lit(42))]));self.assertEqual(v['program']['families']['F0']['fields']['Just'],['#i64'])
 def test_nullary_phantom_views_are_distinct_even_same_layout(self):
  m=metadata([template(7,'Token',('a',),[('Cold',[]),('Hot',[])])],{7:[[INT],[BOOL]]});r=t.MultiViewRepresentation(m);a=r.constructor_for('Cold',[INT]);b=r.constructor_for('Cold',[BOOL]);self.assertEqual(a['field_shapes'],b['field_shapes']);self.assertNotEqual(a['shape'],b['shape']);self.assertEqual(a['shape'].declaration_index,7)
  v=plan(app(primitive(8),case(con('Cold',[INT]),[('Hot',[],lit(5)),('Cold',[],lit(42))]),case(con('Cold',[BOOL]),[('Cold',[],lit(0)),('Hot',[],lit(1))])),m);self.assertEqual(list(v['program']['families']),['F0','F1'])
 def test_nullary_wrong_view_application_rejected(self):
  m=metadata([template(0,'Token',('a',),[('Cold',[]),('Hot',[])])]);function={'tag':'lambda','parameter':name(30),'parameter_type':typ('Token',INT),'body':lit(42)}
  with self.assertRaises(t.BridgeError):plan(app(function,con('Cold',[BOOL])),m)
 def test_same_layout_wrong_declaration_rejected(self):
  ts=[template(2,'LeftToken',(),[('LCold',[]),('LHot',[])]),template(9,'RightToken',(),[('RCold',[]),('RHot',[])])];m=metadata(ts,{2:[[]],9:[[]]});r=t.MultiViewRepresentation(m)
  with self.assertRaises(t.BridgeError):r.variant_for(r.type_shape(typ('LeftToken')),'RCold')
 def test_two_formal_vector_order_changes_exact_fields(self):
  row=template(4,'Either',('a','b'),[('Left',[formal('a')]),('Right',[formal('b')])]);m=metadata([row],{4:[[INT,BOOL],[BOOL,INT]]});r=t.MultiViewRepresentation(m)
  self.assertEqual(r.constructor_for('Left',[INT,BOOL])['field_shapes'],['#i64']);self.assertEqual(r.constructor_for('Left',[BOOL,INT])['field_shapes'],['#bool']);self.assertEqual(r.constructor_for('Right',[BOOL,INT])['field_shapes'],['#i64'])
  with self.assertRaises(t.BridgeError):plan(case(con('Left',[BOOL,INT],lit(42)),[('Left',[name(1)],lit(1)),('Right',[name(2)],lit(2))]),m)
 def test_nested_field_targets_keep_full_view(self):
  ts=[template(),template(3,'Wrap',('a',),[('Absent',[]),('Wrapped',[raw('Maybe',formal('a'))])])];m=metadata(ts,{0:[[INT],[BOOL]],3:[[INT],[BOOL]]});r=t.MultiViewRepresentation(m)
  self.assertEqual(r.constructor_for('Wrapped',[INT])['field_shapes'],[r.type_shape(typ('Maybe',INT))]);self.assertEqual(r.constructor_for('Wrapped',[BOOL])['field_shapes'],[r.type_shape(typ('Maybe',BOOL))]);v=plan(lit(42),m);self.assertEqual(v['program']['families']['F2']['fields']['Wrapped'],['%F0']);self.assertEqual(v['program']['families']['F3']['fields']['Wrapped'],['%F1'])
 def test_recursive_view_fields_use_exact_cycle(self):
  row=template(1,'Tree',('a',),[('Leaf',[formal('a')]),('Branch',[raw('Tree',formal('a')),raw('Tree',formal('a'))])]);m=metadata([row],{1:[[INT],[BOOL]]});v=plan(lit(42),m);self.assertEqual(v['program']['families']['F0']['fields']['Branch'],['%F0','%F0']);self.assertEqual(v['program']['families']['F1']['fields']['Branch'],['%F1','%F1'])
 def test_callable_signature_retains_view_identity(self):
  r=t.MultiViewRepresentation(metadata());a=r.type_shape({'tag':'arrow','from':typ('Maybe',INT),'to':INT});b=r.type_shape({'tag':'arrow','from':typ('Maybe',BOOL),'to':INT});self.assertNotEqual(a,b)
 def test_64_views_from_seven_formals_pass_65_reject(self):
  params=tuple('abcdefg');row=template(0,'Phantom7',params,[('P0',[]),('P1',[])]);vectors=[list(x)for x in itertools.product([INT,BOOL],repeat=7)];m=metadata([row],{0:vectors[:64]});r=t.MultiViewRepresentation(m);self.assertEqual(len(r.sums),64);plan(lit(42),m)
  with self.assertRaises(t.BridgeError):t.MultiViewRepresentation(metadata([row],{0:vectors[:65]}))
 def test_full_decl_index_is_part_of_view_shape(self):
  a=t.MultiViewRepresentation(metadata([template(0)],{0:[[INT]]}));b=t.MultiViewRepresentation(metadata([template(8)],{8:[[INT]]}));self.assertNotEqual(a.type_shape(typ('Maybe',INT)),b.type_shape(typ('Maybe',INT)))
 def test_view_metadata_forgeries_reject(self):
  mutations=[lambda m:m['sum_instances'][1].__setitem__('declaration_index',5),lambda m:m['sum_instances'][0].__setitem__('datatype','Wrong'),lambda m:m['sum_instances'][1].__setitem__('view_index',0),lambda m:m['sum_instances'].reverse(),lambda m:m['sum_instances'].append(copy.deepcopy(m['sum_instances'][1])),lambda m:m['sum_instances'][0]['constructors'].pop(),lambda m:m['sum_instances'][0]['constructors'][1]['fields'].clear(),lambda m:m['sum_instances'][0]['constructors'][1].__setitem__('fields',[BOOL]),lambda m:m['sum_instances'][0]['constructors'].reverse(),lambda m:m['sum_instances'][0].__setitem__('arguments',[BOOL]),lambda m:m['sum_instances'][0].__setitem__('extra',0),lambda m:m['custom_sums'][0]['parameters'][0].__setitem__('kind',{'tag':'arrow','from':{'tag':'star'},'to':{'tag':'star'}})]
  for i,mutation in enumerate(mutations):
   with self.subTest(mutation=i):
    m=metadata();mutation(m)
    with self.assertRaises(t.BridgeError):t.MultiViewRepresentation(m)
 def test_template_field_and_owner_forgeries_reject(self):
  for change in [lambda m:m['custom_sums'][0].__setitem__('declaration_index',2),lambda m:m['custom_sums'][0].__setitem__('datatype','Other'),lambda m:m['custom_sums'][0]['constructors'][1].__setitem__('constructor','Nothing'),lambda m:m['custom_sums'][0]['constructors'][1].__setitem__('fields',[formal('unknown')]),lambda m:m['custom_sums'][0]['constructors'][1].__setitem__('fields',[{'tag':'function','from':raw('Int'),'to':raw('Int')}])]:
   m=metadata();change(m)
   with self.assertRaises(t.BridgeError):t.MultiViewRepresentation(m)
 def test_unknown_open_or_partial_vector_reject(self):
  r=t.MultiViewRepresentation(metadata())
  for arguments in [[],[INT,BOOL],[{'tag':'var','id':9}],[typ('()')]]:
   with self.subTest(arguments=arguments),self.assertRaises(t.BridgeError):r.constructor_for('Nothing',arguments)
 def test_wrong_view_constructor_field_reject(self):
  with self.assertRaises(t.BridgeError):plan(case(con('Just',[BOOL],lit(42)),[('Nothing',[],lit(0)),('Just',[None],lit(1))]))
 def test_missing_nested_view_reject_even_unused_field(self):
  ts=[template(),template(1,'Wrap',('a',),[('Absent',[]),('Wrapped',[raw('Maybe',formal('a'))])])];m=metadata(ts,{0:[[INT]],1:[[BOOL]]})
  with self.assertRaises(t.BridgeError):t.MultiViewRepresentation(m)
 def test_sum_unit_record_arrow_fields_stay_rejected(self):
  for field in [raw('()'),raw('Record')]:
   row=template(0,'Bad',(),[('B0',[]),('B1',[field])]);m=metadata([row],{0:[[]]},records=[{'datatype':'Record','constructor':'Record','arity':0,'fields':[]}])
   with self.subTest(field=field),self.assertRaises(t.BridgeError):t.MultiViewRepresentation(m)
 def test_template_without_any_view_reject(self):
  m=metadata();m['sum_instances']=[]
  with self.assertRaises(t.BridgeError):t.MultiViewRepresentation(m)
 def test_old_standalone_schema_cannot_admit_new_view_index(self):
  m=metadata()
  with self.assertRaises(t.BridgeError):t.validate_sum_metadata_schema(m)
  with self.assertRaises(t.BridgeError):t.Representation(m)
 def test_old_module_format_does_not_select_new_representation(self):
  with self.assertRaises(t.BridgeError):p.plan(envelope(lit(42),metadata(),format='mlf-checked-module-export/1'))
 def test_new_records_preserve_legacy_record_plan(self):
  m=metadata([],{},{'not':'a list'}if False else[{'datatype':'Box','constructor':'Box','arity':1,'fields':[INT]}]);body=case(con('Box',[],lit(42)),[('Box',[name(1)],var(1))]);v=plan(body,m)
  old=copy.deepcopy(m);vold=p.plan(envelope(body,old,format='mlf-checked-recursion-export/6'));self.assertEqual(v['program'],vold['program']);self.assertEqual(v['binding']['source_map'],vold['binding']['source_map'])
 def test_core_rejects_wrong_concrete_field_family(self):
  v=plan(int_case());program=copy.deepcopy(v['program']);node=next(i for c in program['codes'].values()for i in c['body']if i['op']=='construct_sum');node['family']='F1'
  with self.assertRaises(Exception):check(program)
 def test_core_rejects_wrong_nullary_case_family(self):
  m=metadata([template(0,'Token',('a',),[('Cold',[]),('Hot',[])])]);v=plan(case(con('Cold',[INT]),[('Cold',[],lit(42)),('Hot',[],lit(0))]),m);program=copy.deepcopy(v['program']);node=next(i for c in program['codes'].values()for i in c['body']if i['op']=='case_i64');node['family']='F1'
  with self.assertRaises(Exception):check(program)
 def test_legacy_scalar_and_sum_full_plan_byte_equivalent(self):
  oldroot=BASE/'tests/reference_before_multi_view';oldp=load(oldroot/'planner.py','legacy_captured_planner')
  m=metadata();m['sum_instances']=m['sum_instances'][:1];del m['sum_instances'][0]['view_index']
  for body in [lit(42),int_case()]:
   e=envelope(body,m,format='mlf-checked-recursion-export/6');self.assertEqual(p.plan(e),oldp.plan(e))

if __name__=='__main__':unittest.main()
