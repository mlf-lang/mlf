"""Module-envelope glue controls, not ordinary source/native qualification.

Most tests deliberately mock ONLY independent custody replay so they can isolate
projection/normalization/census linkage. Custody's own full synthetic fixtures and
its genuine-source checks are a separate gate; a marked join test uses its real
fixture when available. No original compiler or native process is executed here.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import module_transport as m
import module_projection as p
import module_inventory as inv
import transport as t

MANIFEST={'source_commit':'test-historical-anchor-not-origin','dependency_digest':'test-dependency-anchor'}
INT={'tag':'constructor','name':'Int','arguments':[]}
UNIT={'tag':'constructor','name':'()','arguments':[]}

def nm(i):return {'id':i,'hint':'x'+str(i)}
def var(i):return {'tag':'var','name':nm(i)}
def lit(n=42):return {'tag':'int64','value':n}
def let(i,rhs,body):return {'tag':'let','name':nm(i),'value':rhs,'body':body}
def typ(n,args=()):return {'tag':'constructor','name':n,'arguments':list(args)}
def ctor(n,args=()):return {'tag':'constructor','name':n,'arguments':list(args)}
def app(f,a):return {'tag':'application','function':f,'argument':a}
def primitive():return {'tag':'primitive','id':8,'name':'addInt','arguments':[]}
def unused_declaration():return {'tag':'data','name':'Unused','parameters':['a'],'constructors':[{'name':'UnusedA','fields':[]},{'name':'UnusedB','fields':[{'tag':'parameter','name':'a'}]}]}

def envelope(original=None,root=None):
    original=copy.deepcopy(original or let(1,{'tag':'string','value':'unsupported dead value'},let(2,app(app(primitive(),lit(21)),lit(21)),var(2))))
    root=copy.deepcopy(root or INT)
    projected,steps=p.project_typed(original);oe=p.erase_total(original);pe=p.erase_total(projected)
    old=m.fragment_raw(projected);param=t.has_parameterized_sum(old);has_if=t.contains_conditional(old)
    if param:normalized,normal_steps=t.normalize_closed_instances_raw(old);policy='single-closed-instance/1'
    elif has_if:normalized,normal_steps=t.normalize_conditional_raw(old);policy='closed-int-standard-instantiation/1'
    else:normalized,normal_steps=old,[];policy='identity-no-conditional/1'
    # Invert only vocabulary changes to construct synthetic claimed raw output.
    def total(n,erased=False):
        tag=n['tag']
        if tag=='unit':return {'tag':'constructor','name':'()','arguments':[]}
        out=dict(n)
        if tag in ('lambda','type_lambda','with_data'):out['body']=total(n['body'])
        elif tag=='type_application':out['value']=total(n['value'])
        elif tag=='application':out.update(function=total(n['function']),argument=total(n['argument']))
        elif tag=='let':out.update(value=total(n['value']),body=total(n['body']))
        elif tag=='letrec':out.update(bindings=[b|{'value':total(b['value'])}for b in n['bindings']],body=total(n['body']))
        elif tag=='case':out.update(scrutinee=total(n['scrutinee']),alternatives=[{'pattern':{'tag':'constructor',**a['pattern']},'body':total(a['body'])}for a in n['alternatives']])
        return out
    raw_normalized=total(normalized)
    ds=raw_normalized['declarations']if raw_normalized['tag']=='with_data'else []
    records,templates,instances,w=inv.derive_inventory(ds,raw_normalized,root)
    normalization={'policy':policy,'original_checked_type':root,'original_checked_type_pretty':'synthetic',
      'original_checked_term_pretty':'synthetic NOT compiler evidence','original_declaration_bindings':{'status':'available','bindings':[]},
      'original_annotated':old,'original_erased':m.fragment_raw(pe,erased=True),'normalized_annotated':normalized,'steps':normal_steps,
      'original_rechecked':True,'normalized_rechecked':True,'root_type_alpha_equal':True,'erasure_equal':True}
    if param:normalization.update(original_term_skeleton=t.term_skeleton(old),normalized_term_skeleton=t.term_skeleton(normalized))
    return {'format':m.FORMAT,'producer':dict(MANIFEST),'module_custody':{'unit_test_only':'independent validator mocked'},
      'original':{'checked_type':root,'annotated':original,'erased':oe,'source_erased':copy.deepcopy(oe),
          'binder_origins':{'unit_test_only':'not actual origin'},'ordinary_whole_check_passed':True,'root_type_alpha_equal':True,'source_erasure_equal':True},
      'projection':{'policy':'outer-lazy-spine/1','original_checked_type':root,'projected_checked_type':root,
          'projected_annotated':projected,'projected_erased':pe,'steps':steps,
          'original_rechecked':True,'projected_rechecked':True,'root_type_alpha_equal':True,'declarations_equal':True,'erased_projection_equal':True},
      'normalization':{'fragment':normalization,'raw_normalized':raw_normalized},'runtime_inventory':w,
      'representation':{'builtin_unit':{'constructor':'()','datatype':'()','arity':0,'fields':[]},
          'builtin_scalars':[{'datatype':n,'kind':{'tag':'star'},'arity':0,'runtime_shape':s}for n,s in [('Int','#i64'),('Bool','#bool')]],
          'custom_datatypes':records,'custom_sums':templates,'sum_instances':instances},
      'annotated':t.strip_data_evidence(normalized),'erased':t.projection(normalized,True,True),'checked_type':root}


def parse(v):return m.parse_module_envelope(json.dumps(v,ensure_ascii=False),manifest=MANIFEST)


class GlueTests(unittest.TestCase):
    def setUp(self):
        patch=mock.patch.object(m.custody,'validate_custody',return_value={'unit_test_only':True})
        self.custody=patch.start();self.addCleanup(patch.stop)

    def test_whole_envelope_canonical_binding_and_custody_join(self):
        v=envelope();e=parse(v)
        self.assertIsInstance(e,t.Envelope);self.assertEqual(e.data(),v)
        self.assertEqual(e.sha256,hashlib.sha256(e.canonical_json.encode()).hexdigest())
        self.custody.assert_called_once_with(v['module_custody'],v['original'])
        self.assertIn('unsupported dead value',e.canonical_json)
        self.assertNotIn('unsupported dead value',str(e.data()['annotated']))

    def test_no_old_eager_all_declaration_admission(self):
        d=unused_declaration();d['constructors'][1]['fields']=[{'tag':'applied','name':'String','arguments':[]}]
        v=envelope({'tag':'with_data','declarations':[d],'body':lit()})
        with mock.patch.object(t,'validate_declaration_metadata',side_effect=AssertionError('old eager call')),mock.patch.object(t,'declaration_views',side_effect=AssertionError('old eager call')):
            parsed=parse(v)
        self.assertEqual(parsed.data()['runtime_inventory']['evidence_only_declaration_indices'],[0])
        self.assertEqual(parsed.data()['representation']['sum_instances'],[])

    def test_unit_vocabulary_and_typed_pattern_conversion(self):
        raw={'tag':'case','scrutinee':ctor('()'),'result_type':INT,
             'alternatives':[{'pattern':{'tag':'constructor','constructor':'()','fields':[]},'body':lit()}]}
        v=envelope(raw);parse(v)
        self.assertEqual(v['annotated']['scrutinee'],{'tag':'unit'})
        self.assertEqual(v['annotated']['alternatives'][0]['pattern'],{'constructor':'()','fields':[]})
        parse(envelope(ctor('()'),UNIT))

    def test_closed_type_normalization_preserves_unused_context(self):
        proof={'tag':'then','first':{'tag':'inner','witness':{'tag':'bottom','type':INT}},'second':{'tag':'elim'}}
        raw={'tag':'with_data','declarations':[unused_declaration()],
             'body':{'tag':'type_application','value':{'tag':'type_lambda','id':15,'bound':{'tag':'bottom'},'body':lit()},'witness':proof}}
        v=envelope(raw);parse(v)
        self.assertEqual(len(v['normalization']['fragment']['steps']),1)
        self.assertEqual(v['normalization']['raw_normalized']['body'],lit())
        self.assertEqual(v['runtime_inventory']['evidence_only_declaration_indices'],[0])

    def test_full_used_parametric_family_without_unused_field_pruning(self):
        d=unused_declaration();raw={'tag':'with_data','declarations':[d],
          'body':{'tag':'case','scrutinee':app(ctor('UnusedB',[INT]),lit()),'result_type':INT,
             'alternatives':[{'pattern':{'tag':'constructor','constructor':'UnusedA','fields':[]},'body':lit(0)},
                             {'pattern':{'tag':'constructor','constructor':'UnusedB','fields':[nm(3)]},'body':var(3)}]}}
        v=envelope(raw);parse(v)
        self.assertEqual(v['representation']['sum_instances'][0]['constructors'][1]['fields'],[INT])
        self.assertEqual(v['runtime_inventory']['selected_declaration_indices'],[0])

    def test_dead_total_forms_preserved_but_not_runtime_admitted(self):
        raw=let(1,{'tag':'double','bits_i64':-(1<<63)},
                let(2,{'tag':'primitive','id':7,'name':'showInt','arguments':[]},
                    let(3,{'tag':'case','scrutinee':lit(),'result_type':INT,
                           'alternatives':[{'pattern':{'tag':'default','binder':nm(4)},'body':var(4)}]},lit())))
        v=envelope(raw);out=parse(v).data()
        self.assertEqual(out['annotated'],lit())
        self.assertEqual(out['original']['annotated']['value']['bits_i64'],-(1<<63))
        self.assertEqual(out['projection']['steps'][0]['keep'],False)

    def test_dead_unknown_primitive_identity_cannot_hide_behind_projection(self):
        v=envelope(let(1,{'tag':'primitive','id':7,'name':'showInt','arguments':[]},lit()))
        for lane in ['annotated','erased','source_erased']:
            v['original'][lane]['value']['name']='inventedPrimitive'
        with self.assertRaises(m.ModuleTransportError):parse(v)

    def test_custody_failure_is_not_fallback(self):
        self.custody.side_effect=m.custody.CustodyError('forged origin')
        with self.assertRaisesRegex(m.ModuleTransportError,'forged origin'):parse(envelope())

    def test_unmodified_full_original_data_is_canonical(self):
        a=envelope(let(1,{'tag':'string','value':'unusedA'},lit()))
        b=copy.deepcopy(a)
        b['original']['annotated']['value']['value']='unusedB';b['original']['erased']['value']['value']='unusedB';b['original']['source_erased']['value']['value']='unusedB'
        ea,eb=parse(a),parse(b)
        self.assertEqual(ea.data()['annotated'],eb.data()['annotated']);self.assertNotEqual(ea.sha256,eb.sha256)

    def test_many_linkage_forgery_controls(self):
        mutations=[
          lambda v:v.update(extra=True),lambda v:v.update(format='mlf-checked-recursion-export/6'),
          lambda v:v['producer'].update(dependency_digest='other'),
          lambda v:v['original']['source_erased']['body']['value'].update(argument=lit(99)),
          lambda v:v['projection']['steps'][0].update(keep=True),
          lambda v:v['projection']['steps'][1].update(binding_ids=[3]),
          lambda v:v['projection']['projected_annotated']['value'].update(argument=lit(9)),
          lambda v:v['projection'].update(projected_checked_type=UNIT),
          lambda v:v['normalization']['raw_normalized']['value'].update(argument=lit(8)),
          lambda v:v['normalization']['fragment']['original_annotated']['value'].update(argument=lit(7)),
          lambda v:v['normalization']['fragment']['normalized_annotated']['value'].update(argument=lit(6)),
          lambda v:v['normalization']['fragment']['steps'].append({'rule':'erase_refl','witness':{'tag':'refl'}}),
          lambda v:v['normalization']['fragment'].update(policy='identity-guessed'),
          lambda v:v['normalization']['fragment'].update(original_checked_type=UNIT),
          lambda v:v['annotated']['value'].update(argument=lit(5)),
          lambda v:v['erased']['value'].update(argument=lit(4)),
          lambda v:v['runtime_inventory'].update(extra=[]),
          lambda v:v['runtime_inventory']['selected_declaration_indices'].append(0),
          lambda v:v['representation']['builtin_unit'].update(arity=False),
          lambda v:v['representation']['builtin_scalars'][0].update(arity=False),
          lambda v:v.update(checked_type=UNIT),
          lambda v:v['normalization'].update(extra={}),
          lambda v:v['normalization'].update(fragment=[]),
        ]
        for i,mutate in enumerate(mutations):
            with self.subTest(i=i):
                v=envelope();mutate(v)
                with self.assertRaises(m.ModuleTransportError):parse(v)

    def test_every_boolean_guard_requires_true_boolean(self):
        for lane,keys in [('original',['ordinary_whole_check_passed','root_type_alpha_equal','source_erasure_equal']),
                          ('projection',['original_rechecked','projected_rechecked','root_type_alpha_equal','declarations_equal','erased_projection_equal']),
                          ('normalization',['original_rechecked','normalized_rechecked','root_type_alpha_equal','erasure_equal'])]:
            for key in keys:
                with self.subTest(lane=lane,key=key):
                    v=envelope();target=v[lane]if lane!='normalization'else v[lane]['fragment'];target[key]=1
                    with self.assertRaises(m.ModuleTransportError):parse(v)

    def test_unsupported_retained_never_reuses_total_evidence_permission(self):
        for raw in [{'tag':'string','value':'x'},{'tag':'double','bits_i64':0},
                    {'tag':'case','scrutinee':lit(),'result_type':INT,'alternatives':[{'pattern':{'tag':'default','binder':None},'body':lit()}]}]:
            with self.subTest(raw=raw):
                with self.assertRaises(m.ModuleTransportError):m.fragment_raw(raw)

    def test_strict_nonfinite_duplicate_float_and_bad_unicode_json(self):
        for raw in ['{"format":1,"format":2}', 'NaN','Infinity','1.0','"\\ud800"','{"unclosed":']:
            with self.subTest(raw=raw):
                with self.assertRaises(m.ModuleTransportError):m.parse_module_envelope(raw,manifest=MANIFEST)

    def test_byte_bound_is_before_json_decoder(self):
        with mock.patch.object(m,'MAX_BYTES',4),mock.patch.object(m.json,'loads',side_effect=AssertionError('decoded oversized input')):
            with self.assertRaises(m.ModuleTransportError):m.parse_module_envelope(' '*5,manifest=MANIFEST)

    def test_aggregate_duplicate_artifacts_not_subject_to_per_term_node_count(self):
        # Container/cell budget still applies; duplicated syntax need not share
        # one original-term100k budget. No claim this generic JSON is an envelope.
        m.envelope_budget([{'tag':'int64','value':0}for _ in range(p.MAX_NODES+1)])
        with self.assertRaises(p.ProjectionError):p._budget([{'tag':'int64','value':0}for _ in range(p.MAX_NODES+1)])

    def test_strict_bound_before_recursive_normalization(self):
        v=envelope();v['normalization']['fragment']['original_checked_term_pretty']='x'
        nested=lit()
        for _ in range(110):nested={'tag':'type_lambda','id':5,'bound':{'tag':'bottom'},'body':nested}
        v['normalization']['fragment']['original_annotated']=nested
        with mock.patch.object(t,'validate_normalization',side_effect=AssertionError('recursive function reached')):
            with self.assertRaisesRegex(m.ModuleTransportError,'strict cell/depth'):parse(v)

    def test_no_mutation_of_supplied_data(self):
        v=envelope();before=copy.deepcopy(v);parse(v);self.assertEqual(v,before)


class CapturedProjectionGlue(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('MLF_MODULE_CAPTURED_EVENTS'),'explicit captured raw path not supplied')
    def test_original_captured_raw_projection_join_only_custody_is_mocked(self):
        path=Path(os.environ['MLF_MODULE_CAPTURED_EVENTS']);events=json.loads(path.read_text())
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),'5be8e9cdf317b9beb5e4f83c2a1637937b04c9e6ed07e0b805bb33f9af7b588b')
        artifacts=[x['event']['artifact']for x in events if x.get('event',{}).get('phase')=='complete_original_checked_artifact'and x['event']['event']=='end']
        self.assertEqual(len(artifacts),1)
        v=envelope(artifacts[0]['raw_annotated'],artifacts[0]['checked_type'])
        with mock.patch.object(m.custody,'validate_custody',return_value={'unit_test_only':True}):e=parse(v)
        self.assertEqual(e.data()['runtime_inventory']['evidence_only_declaration_indices'],list(range(7)))
        self.assertEqual([x['binding_ids']for x in e.data()['projection']['steps']if x['keep']],[[38887],[38922]])


class CompleteSyntheticCustodyJoin(unittest.TestCase):
    def test_real_validator_join_with_explicitly_artificial_fixture(self):
        from test_module_custody import synthetic_valid_custody
        custody,original=synthetic_valid_custody()
        v=envelope(original['annotated'],original['checked_type'])
        v['module_custody']=custody;v['original']=original
        parsed=parse(v)
        self.assertEqual(parsed.data()['annotated']['name']['id'],10)
        self.assertEqual(parsed.data()['projection']['steps'][0]['binding_ids'],[10])

    def test_real_custody_rejects_forged_resolver_binding_even_with_guards(self):
        from test_module_custody import synthetic_valid_custody
        custody,original=synthetic_valid_custody()
        v=envelope(original['annotated'],original['checked_type'])
        v['module_custody']=custody;v['original']=original
        v['original']['binder_origins']['bindings'][0]['bindings'][0]['source_internal_name']='invented'
        with self.assertRaises(m.ModuleTransportError):parse(v)
