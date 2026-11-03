"""Synthetic transport/planner tests; these do NOT claim genuine CheckedTerm origin."""
import copy
import json
import pathlib
import sys
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import planner
t = planner.baseline
MANIFEST = json.loads((BASE / 'provenance/pr25-source.json').read_text())


def typ(name):
    return {'tag':'constructor', 'name':name, 'arguments':[]}


def name(i, hint='x'):
    return {'id':i, 'hint':hint}


def lit(n):
    return {'tag':'bool' if type(n) is bool else 'int64', 'value':n}


def primitive(code):
    return {'tag':'primitive', 'id':code, 'name':t.SCALAR_PRIMITIVES[code][0], 'arguments':[]}


def app(f, a):
    return {'tag':'application', 'function':f, 'argument':a}


def metadata():
    return {'builtin_unit':{'constructor':'()', 'datatype':'()', 'arity':0, 'fields':[]},
        'builtin_scalars':[{'datatype':n,'kind':{'tag':'star'},'arity':0,'runtime_shape':s}
                           for n,s in [('Int','#i64'),('Bool','#bool')]],
        'custom_datatypes':[], 'custom_sums':[], 'sum_instances':[]}


def envelope(node, result='Int'):
    value = {'format':'mlf-checked-recursion-export/6',
        'producer':{k:MANIFEST[k] for k in ['source_commit','dependency_digest']},
        'checked_type':typ(result), 'checked_type_pretty':result,
        'checked_term_pretty':'synthetic-not-a-compiler-artifact',
        'declaration_bindings':{'status':'available','bindings':[]},
        'representation':metadata(), 'annotated':node, 'erased':t.annotated_erasure(node)}
    value['normalization']={'policy':'identity-no-conditional/1',
        'original_checked_type':typ(result),'original_checked_type_pretty':result,
        'original_checked_term_pretty':'synthetic-not-a-compiler-artifact',
        'original_declaration_bindings':{'status':'available','bindings':[]},
        'original_annotated':copy.deepcopy(node),'normalized_annotated':copy.deepcopy(node),
        'original_erased':copy.deepcopy(value['erased']),'steps':[],
        'original_rechecked':True,'normalized_rechecked':True,'root_type_alpha_equal':True,'erasure_equal':True}
    return value


def parse(data):
    return t.parse_envelope(json.dumps(data), manifest=MANIFEST)


class ScalarTransport(unittest.TestCase):
    def test_literal_extremes(self):
        for value in [-(1<<63), -1, 0, (1<<63)-1]:
            e=parse(envelope(lit(value)))
            p=planner.plan(e)['program']
            self.assertEqual(p['version'],7)
            self.assertEqual(p['entry'][1]['value'],value)
            self.assertEqual(p['entry'][-1]['op'],'finish_scalar')

    def test_actual_boolean(self):
        for value in [False,True]:
            p=planner.plan(parse(envelope(lit(value),'Bool')))['program']
            self.assertEqual(p['entry'][1]['kind'],'bool')
            self.assertIs(p['entry'][1]['value'],value)

    def test_noncanonical_literals_reject(self):
        for node in [{'tag':'int64','value':True},{'tag':'int64','value':1<<63},
                     {'tag':'int64','value':-(1<<63)-1},{'tag':'bool','value':1},
                     {'tag':'bool','value':'true'}]:
            with self.assertRaises(t.BridgeError):t.projection(node)

    def test_primitive_identity_is_exact(self):
        for code in t.SCALAR_PRIMITIVES:
            n=primitive(code);self.assertEqual(t.projection(n)['id'],code)
        for bad in [{'tag':'primitive','id':8,'name':'subInt','arguments':[]},
                    {'tag':'primitive','id':13,'name':'ifThenElse','arguments':[]},
                    {'tag':'primitive','id':True,'name':'addInt','arguments':[]},
                    {**primitive(8),'arguments':[typ('Int')]}]:
            with self.assertRaises(t.BridgeError):t.projection(bad)

    def test_erasure_scalar_mutation_rejects(self):
        e=envelope(lit(1));e['erased']['value']=2
        with self.assertRaisesRegex(t.BridgeError,'projection differs'):parse(e)

    def test_erasure_primitive_mutation_rejects(self):
        n=app(app(primitive(8),lit(20)),lit(22));e=envelope(n)
        e['erased']['function']['function']['id']=9
        e['erased']['function']['function']['name']='subInt'
        with self.assertRaisesRegex(t.BridgeError,'projection differs'):parse(e)

    def test_intrinsic_metadata_is_required(self):
        for alteration in ['missing','shape','boolean-arity','kind','order']:
            e=envelope(lit(42));m=e['representation']
            if alteration=='missing':del m['builtin_scalars']
            elif alteration=='shape':m['builtin_scalars'][0]['runtime_shape']='Unit'
            elif alteration=='boolean-arity':m['builtin_scalars'][0]['arity']=False
            elif alteration=='kind':m['builtin_scalars'][0]['kind']={'tag':'arrow'}
            else:m['builtin_scalars'].reverse()
            with self.assertRaises(t.BridgeError):parse(e)

    def test_reserved_scalar_nominals_reject(self):
        for reserved in ['Int','Bool']:
            e=envelope(lit(42));e['representation']['custom_datatypes']=[
                {'datatype':reserved,'constructor':'Fake','arity':0,'fields':[]}]
            raw={'tag':'with_data','declarations':[{'tag':'data','name':reserved,
                'parameters':[],'constructors':[{'name':'Fake','fields':[]}]}],
                'body':lit(42)}
            e['normalization'].update(original_annotated=copy.deepcopy(raw),
                                      normalized_annotated=copy.deepcopy(raw))
            with self.assertRaisesRegex(t.BridgeError,'reserved'):parse(e)

    def test_fake_true_is_not_boolean(self):
        e=envelope({'tag':'constructor','name':'True','arguments':[]},'Bool')
        with self.assertRaisesRegex(t.BridgeError,'missing original'):planner.plan(parse(e))

    def test_partial_primitive_rejects(self):
        n=app(primitive(8),lit(1));e=envelope(n)
        e['checked_type']={'tag':'arrow','from':typ('Int'),'to':typ('Int')}
        with self.assertRaises(t.BridgeError):planner.plan(parse(e))

    def test_primitive_is_delayed_and_forced_left_to_right(self):
        e=envelope(app(app(primitive(8),lit(20)),lit(22)))
        p=planner.plan(parse(e))['program']
        self.assertFalse(any(x['op']=='prim2' for x in p['entry']))
        body=next(iter(p['codes'].values()))['body'];ops=[x['op'] for x in body]
        self.assertEqual(ops,['scalar','force','scalar','force','prim2','drop','drop','return'])
        primitive_op=body[4]
        self.assertEqual(primitive_op['left'],body[1]['out'])
        self.assertEqual(primitive_op['right'],body[3]['out'])

    def test_aliased_operands_have_distinct_consumed_owners(self):
        x={'tag':'var','name':name(1)}
        e=envelope({'tag':'let','name':name(1),'value':lit(21),
                    'body':app(app(primitive(8),x),copy.deepcopy(x))})
        p=planner.plan(parse(e))['program'];body=next(iter(p['codes'].values()))['body']
        forces=[x for x in body if x['op']=='force'];self.assertEqual(len(forces),2)
        self.assertNotEqual(forces[0]['value'],forces[1]['value'])
        self.assertNotEqual(forces[0]['out'],forces[1]['out'])

    def test_local_addint_name_does_not_select_primitive(self):
        n={'tag':'let','name':name(1,'addInt'),'value':lit(42),
           'body':{'tag':'var','name':name(1,'addInt')}}
        p=planner.plan(parse(envelope(n)))['program']
        self.assertEqual(p['codes'],{})
        self.assertFalse(any(x['op']=='prim2' for x in p['entry']))

    def test_unit_ending_is_preserved(self):
        p=planner.plan(parse(envelope({'tag':'unit'},'()')))['program']
        self.assertEqual(p['entry'][-1],{'op':'finish'})

    def test_foreign_version_rejects(self):
        e=envelope(lit(42));e['format']='mlf-checked-recursion-export/1'
        with self.assertRaisesRegex(t.BridgeError,'format'):parse(e)


if __name__=='__main__':unittest.main()
