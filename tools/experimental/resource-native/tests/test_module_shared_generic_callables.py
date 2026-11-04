"""Direct concrete callable generic imports: host replay only, no targets."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

BASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(BASE),str(BASE/'tests')]
import module_shared_transport as m
import test_module_shared_transport as f
import test_module_shared_generic_captures as old
from source_capture_v8 import verify_capture

PIN='743daa6cca393aa11f6e8315132c3633a05000494c610ee3fab6f131bb0e7d9d'
SOURCE_PIN='7513e9230d16fce0c393b0f2b8e0c5eac368a0b20bf2e62bf3543a9f85e526f7'
MODULE_PIN='50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'
CAPTURED_PIN='403454e4f15234ad2ccd55bd646e1eed5775e09694dbe5db8297b05c29668d4c'
CAPTURED_SOURCE_PIN='4d44e18c2219393e4be0c3674eebadae15e3c5e88a97debe52108a2c88599de2'
PENDING_PIN='19a6c069b7369d1c04adc3d81518cea875c67c88c4a95e568fce29e743ead37e'
PENDING_SOURCE_PIN='7e2e623f72478bd57acba1b5a81056af738a3ac5d63c1b3ab794759e7b3a037a'


def fixture(captured=False, mixed=False, nested=False, result_arrow=False, argument_arrow=False):
    helper=f.lam(4,f.I,f.add(f.var(9) if captured else f.lit(21),f.var(4)))
    call=f.app(f.var(1),f.lit(0))
    if result_arrow:
        helper=f.lam(4,f.I,f.lam(5,f.B,f.var(4)))
        call=f.app(f.app(f.var(1),f.lit(21)),f.boolean())
    if argument_arrow:
        helper=f.lam(4,f.arr(f.I,f.I),f.app(f.var(4),f.lit(21)))
        call=f.app(f.var(1),f.lam(5,f.I,f.var(5)))
    if mixed:call=f.let(6,f.var(9),call)
    if nested:call=f.app(f.lam(7,f.I,call),f.lit(0))
    root=f.let(1,helper,f.let(2,f.tabs(100,f.lam(3,f.tv(100),call)),
        f.add(f.app(f.use(2,f.B),f.boolean()),f.app(f.use(2,f.I),f.lit(0)))))
    return f.let(9,f.add(f.lit(20),f.lit(1)),root) if captured or mixed else root


def retained(test):
    setting=os.environ.get('IR8_GENERIC_PRIMITIVE_DIAGNOSTICS_ROOT')
    if setting is None:test.skipTest('set IR8_GENERIC_PRIMITIVE_DIAGNOSTICS_ROOT for retained original')
    root=Path(setting);path=root/'capture-callable-import01'/'capture.stdout'
    blob=path.read_bytes();test.assertEqual(hashlib.sha256(blob).hexdigest(),PIN)
    return root,path,json.loads(blob)


def retained_captured_helper(test):
    setting=os.environ.get('IR8_GENERIC_CALLABLE_DIAGNOSTICS_ROOT')
    if setting is None:test.skipTest('set IR8_GENERIC_CALLABLE_DIAGNOSTICS_ROOT for captured-helper original')
    root=Path(setting);path=root/'capture-captured-helper01'/'capture.stdout'
    blob=path.read_bytes();test.assertEqual(len(blob),8826197)
    test.assertEqual(hashlib.sha256(blob).hexdigest(),CAPTURED_PIN)
    return root,path,json.loads(blob)


def retained_pending_callable(test):
    setting=os.environ.get('IR8_GENERIC_CALLABLE_DIAGNOSTICS_ROOT')
    if setting is None:test.skipTest('set IR8_GENERIC_CALLABLE_DIAGNOSTICS_ROOT for pending-callable original')
    root=Path(setting);path=root/'capture-pending-callable-import01'/'capture.stdout'
    blob=path.read_bytes();test.assertEqual(len(blob),8826080)
    test.assertEqual(hashlib.sha256(blob).hexdigest(),PENDING_PIN)
    return root,path,json.loads(blob)


def captured_helper_graph(test,tree):
    """Read actual lexical roles, never historical raw binder numbers."""
    test.assertEqual(tree['tag'],'with_data')
    bonus=tree['body'];helper=bonus['body'];k=helper['body']
    for node in (bonus,helper,k):test.assertEqual(node['tag'],'let')
    test.assertEqual(bonus['value']['tag'],'application')
    test.assertEqual(bonus['value']['function']['function'],f.prim(8,'addInt'))
    test.assertEqual(bonus['value']['function']['argument'],f.lit(20))
    test.assertEqual(bonus['value']['argument'],f.lit(1))
    lam=helper['value'];test.assertEqual(lam['tag'],'lambda')
    test.assertEqual(lam['parameter_type'],f.I)
    test.assertEqual(lam['body']['tag'],'application')
    test.assertEqual(lam['body']['function']['function'],f.prim(8,'addInt'))
    test.assertEqual(lam['body']['function']['argument']['name'],bonus['name'])
    test.assertEqual(lam['body']['argument']['name'],lam['parameter'])
    prefix=k['value'];test.assertEqual(prefix['tag'],'type_lambda')
    test.assertEqual(prefix['bound'],{'tag':'bottom'})
    test.assertEqual(prefix['body']['tag'],'lambda')
    test.assertEqual(prefix['body']['parameter_type'],f.tv(prefix['id']))
    call=prefix['body']['body'];test.assertEqual(call['tag'],'application')
    test.assertEqual(call['function']['name'],helper['name'])
    test.assertEqual(call['argument'],f.lit(0))
    return bonus,helper,k


def many(count):
    serial=4000
    def join(xs):
        nonlocal serial
        if len(xs)==1:return f.app(f.var(xs[0]),f.lit(0))
        mid=len(xs)//2;left,right=join(xs[:mid]),join(xs[mid:]);serial+=2
        return f.app(f.app(f.lam(serial,f.I,f.lam(serial+1,f.I,f.var(serial+1))),left),right)
    out=f.let(2002,f.tabs(2000,f.lam(2001,f.tv(2000),join(list(range(1,count+1))))),
              f.app(f.use(2002,f.I),f.lit(0)))
    for i in reversed(range(1,count+1)):out=f.let(i,f.lam(5000+i,f.I,f.var(5000+i)),out)
    return out


class GenericCallableSourceTests(unittest.TestCase):
    def reject(self,tree,code='CAPTURE'):
        with self.assertRaises(m.SharedTransportError) as caught:m.derive_shared_fragment(tree)
        self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_direct_helper_exact_inventory_and_full_dead_coordinates(self):
        tree=fixture();before=copy.deepcopy(tree);out=m.derive_shared_fragment(tree)
        self.assertEqual(tree,before);self.assertEqual(out['raw_normalized'],tree)
        self.assertEqual((out['policy'],out['steps']),(m.POLICY,[]))
        d,=out['polymorphism']['definitions'];self.assertEqual(d['free_term_bindings'],[1])
        self.assertEqual(d['captures'],{'policy':m.GENERIC_CALLABLE_CAPTURE_POLICY,'scalars':[],
            'callables':[{'binding':1,'type':f.arr(f.I,f.I),
                'binding_source':{'stage':'normalized','path':[]},
                'value_source':{'stage':'normalized','path':['value']},
                'occurrences':[{'stage':'normalized','path':['body','value','body','body','function']}]}]})
        self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[f.B],[f.I]])

    def test_nonempty_helper_capture_is_not_flattened(self):
        out=m.derive_shared_fragment(fixture(captured=True));d,=out['polymorphism']['definitions']
        self.assertEqual(d['free_term_bindings'],[1]);self.assertEqual(d['captures']['scalars'],[])
        self.assertEqual(d['captures']['callables'][0]['binding_source']['path'],['body'])

    def test_mixed_imports_and_nested_carrier_occurrences(self):
        out=m.derive_shared_fragment(fixture(mixed=True,nested=True));d,=out['polymorphism']['definitions']
        self.assertEqual(d['free_term_bindings'],[1,9])
        self.assertEqual([r['binding'] for r in d['captures']['scalars']],[9])
        self.assertEqual([r['binding'] for r in d['captures']['callables']],[1])
        self.assertIn('function',d['captures']['callables'][0]['occurrences'][0]['path'])

    def test_nested_closed_arrow_argument_and_result(self):
        for key in ('argument_arrow','result_arrow'):
            tree=fixture(**{key:True});out=m.derive_shared_fragment(tree)
            row=out['polymorphism']['definitions'][0]['captures']['callables'][0]
            self.assertEqual(row['type']['from' if key=='argument_arrow' else 'to']['tag'],'arrow')
            self.assertEqual(out['raw_normalized'],tree)

    def test_pending_wrapper_returned_lambda_and_ordinary_alias_rejected(self):
        tree=fixture();helper=tree['value']
        tree['value']=f.app(f.lam(80,f.arr(f.I,f.I),f.var(80)),helper);self.reject(tree)
        tree=fixture();tree['value']=f.app(f.lam(80,f.I,tree['value']),f.lit());self.reject(tree)
        tree=fixture();tree=f.let(8,tree['value'],f.let(1,f.var(8),tree['body']));self.reject(tree)

    def test_same_and_foreign_scheme_view_aliases_rejected(self):
        tree=fixture();tree['value']=f.use(8,f.I)
        tree=f.let(8,f.tabs(200,f.lam(10,f.tv(200),f.var(10))),tree);self.reject(tree)
        tree=fixture();tree['value']=f.tabs(200,tree['value']);self.reject(tree,'TYPE')

    def test_nominal_and_open_callable_types_rejected(self):
        nominal={'tag':'constructor','name':'Box','arguments':[]}
        tree=fixture();tree['value']=f.lam(4,nominal,f.lit(21))
        tree['body']['value']['body']['body']['argument']=f.ctor('Pack',f.lit())
        self.reject(f.with_data(tree,f.data_decl()),'CAPTURE')
        tree=fixture();tree['value']['parameter_type']=f.tv(999);self.reject(tree,'TYPE_SCOPE')

    def test_non_top_and_non_direct_generic_root_rejected(self):
        self.reject(f.app(f.lam(88,f.I,fixture()),f.lit()))
        tree=fixture();lam=tree['body']['value']['body']
        tree['body']['value']['body']=f.app(f.lam(88,f.arr(f.tv(100),f.I),f.var(88)),lam)
        self.reject(tree)

    def test_generic_primitive_dependency_boundary_is_not_widened(self):
        tree=fixture();body=tree['body']['value']['body']['body']
        tree['body']['value']['body']['body']=f.add(body,f.lit(0));self.reject(tree)

    def test_64_callable_bindings_and_65_limit(self):
        out=m.derive_shared_fragment(many(64));self.assertEqual(len(out['polymorphism']['definitions'][0]['captures']['callables']),64)
        self.reject(many(65),'LIMIT')

    def test_forged_bindings_occurrences_type_and_source_evidence_rejected(self):
        tree=fixture();good=m.derive_shared_fragment(tree)
        mutations=[lambda d:d['captures'].update(policy=m.GENERIC_CAPTURE_POLICY),
            lambda d:d['captures']['callables'][0].update(binding=99),
            lambda d:d['captures']['callables'][0].update(type=f.arr(f.B,f.I)),
            lambda d:d['captures']['callables'][0]['occurrences'].clear(),
            lambda d:d['captures']['callables'][0]['binding_source'].update(path=['body']),
            lambda d:d['captures']['callables'][0]['value_source'].update(path=['body','value']),
            lambda d:d['captures']['scalars'].append(d['captures']['callables'][0])]
        for change in mutations:
            forged=copy.deepcopy(good);change(forged['polymorphism']['definitions'][0])
            with self.assertRaises(m.SharedTransportError):m.validate_shared_fragment(tree,forged)

    def test_original_capture_replays_without_changing_historical_refusal(self):
        root,path,capture=retained(self);old_record=(path.parent/'verification.json').read_bytes()
        self.assertEqual(json.loads(old_record)['fragment_error']['code'],'CAPTURE')
        out=m.derive_shared_fragment(capture['projection']['projected_annotated'])
        for key in ('policy','steps','raw_normalized'):self.assertEqual(out[key],capture['normalization'][key])
        d,=out['polymorphism']['definitions'];row,=d['captures']['callables']
        self.assertEqual(row['type'],f.arr(f.I,f.I));self.assertEqual(d['captures']['scalars'],[])
        self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[f.B],[f.I]])
        report=verify_capture(path,fixture_root=root/'inputs'/'callable-import',entry='main.emlf',
            expected_source_hashes={'main.emlf':SOURCE_PIN,'SharedPoly.emlf':MODULE_PIN},expected_capture_sha256=PIN)
        self.assertTrue(report['fragment_admitted']);self.assertFalse(report['native_admitted'])
        self.assertEqual(report['normalization_replay'],'all exact independent fields match')
        self.assertEqual((path.parent/'verification.json').read_bytes(),old_record)

    def test_captured_helper_original_exact_graph_proofs_and_custody(self):
        root,path,capture=retained_captured_helper(self)
        old_record=(path.parent/'verification.json').read_bytes()
        old_error=json.loads(old_record)['fragment_error']
        self.assertEqual(old_error['code'],'CAPTURE')
        self.assertEqual(old_error['path'],['body','body','body','value','body','body','function'])
        out=m.derive_shared_fragment(capture['projection']['projected_annotated'])
        for key in ('policy','steps','raw_normalized'):self.assertEqual(out[key],capture['normalization'][key])
        self.assertEqual((out['policy'],out['steps']),(m.POLICY,[]))
        bonus,helper,k=captured_helper_graph(self,out['raw_normalized'])
        d,=out['polymorphism']['definitions'];row,=d['captures']['callables']
        self.assertEqual(d['binding'],k['name']);self.assertEqual(d['free_term_bindings'],[helper['name']['id']])
        self.assertEqual(d['captures']['scalars'],[]);self.assertEqual(row['binding'],helper['name']['id'])
        self.assertNotIn(bonus['name']['id'],d['free_term_bindings'])
        self.assertEqual(row['type'],f.arr(f.I,f.I))
        self.assertEqual(row['binding_source'],{'stage':'normalized','path':['body','body']})
        self.assertEqual(row['value_source'],{'stage':'normalized','path':['body','body','value']})
        self.assertEqual(row['occurrences'],[{'stage':'normalized','path':old_error['path']}])
        self.assertEqual([u['arguments'] for u in out['polymorphism']['uses']],[[f.B],[f.I]])
        for use,coordinate in zip(out['polymorphism']['type_applications'],(f.B,f.I)):
            self.assertEqual(use['witness'],{'tag':'then','first':{'tag':'inner','witness':{'tag':'bottom','type':coordinate}},'second':{'tag':'elim'}})
            self.assertEqual([x['proof_path'] for x in use['proof_intermediates']],[[],['first'],['first','witness'],['second']])
            self.assertEqual(use['result_type'],f.arr(coordinate,f.I))
        report=verify_capture(path,fixture_root=root/'inputs'/'captured-helper',entry='main.emlf',
            expected_source_hashes={'main.emlf':CAPTURED_SOURCE_PIN,'SharedPoly.emlf':MODULE_PIN},expected_capture_sha256=CAPTURED_PIN)
        self.assertTrue(report['fragment_admitted']);self.assertFalse(report['native_admitted'])
        self.assertEqual(report['normalization_replay'],'all exact independent fields match')
        join,=report['retained_prefix_binding_joins'];self.assertEqual(join['binding'],k['name'])
        self.assertEqual(join['association'],'compiler_local_or_generated');self.assertIsNone(join['resolver_allocation'])
        records=list(path.parent.rglob('*.result.json'));self.assertEqual(len(records),5)
        for record in records:
            result=json.loads(record.read_bytes())
            self.assertEqual(result['returncode'],0);self.assertEqual(result['stderr_bytes'],0)
            self.assertEqual(result['cleanup_errors'],[]);self.assertFalse(result['cleanup_escalated'])
        for name in ('main.emlf','SharedPoly.emlf'):
            self.assertEqual((path.parent/'sources'/name).read_bytes(),(root/'inputs'/'captured-helper'/name).read_bytes())
        self.assertEqual((path.parent/'verification.json').read_bytes(),old_record)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),CAPTURED_PIN)

    def test_pending_callable_original_preserves_exact_direct_binding_refusal(self):
        root,path,capture=retained_pending_callable(self)
        old_record=(path.parent/'verification.json').read_bytes()
        old_error=json.loads(old_record)['fragment_error'];self.assertEqual(old_error['code'],'CAPTURE')
        error_path=['body','body','body','value','body','body','function']
        self.assertEqual(old_error['path'],error_path)
        norm=capture['normalization'];self.assertEqual((norm['policy'],norm['steps']),(m.POLICY,[]))
        tree=norm['raw_normalized'];self.assertEqual(tree,capture['projection']['projected_annotated'])
        self.assertEqual(tree['tag'],'with_data')
        maker=tree['body'];helper=maker['body'];k=helper['body']
        for node in (maker,helper,k):self.assertEqual(node['tag'],'let')
        outer=maker['value'];inner=outer['body']
        for lam in (outer,inner):
            self.assertEqual(lam['tag'],'lambda');self.assertEqual(lam['parameter_type'],f.I)
        self.assertEqual(inner['body']['function']['function'],f.prim(8,'addInt'))
        self.assertEqual(inner['body']['function']['argument']['name'],outer['parameter'])
        self.assertEqual(inner['body']['argument']['name'],inner['parameter'])
        self.assertEqual(helper['value']['tag'],'application')
        self.assertEqual(helper['value']['function']['name'],maker['name'])
        self.assertEqual(helper['value']['argument'],f.lit(21))
        prefix=k['value'];self.assertEqual(prefix['tag'],'type_lambda')
        self.assertEqual(prefix['bound'],{'tag':'bottom'})
        self.assertEqual(prefix['body']['tag'],'lambda')
        self.assertEqual(prefix['body']['parameter_type'],f.tv(prefix['id']))
        self.assertEqual(prefix['body']['body']['function']['name'],helper['name'])
        self.assertEqual(prefix['body']['body']['argument'],f.lit(0))
        for application,coordinate in ((k['body']['function']['argument'],f.B),(k['body']['argument'],f.I)):
            use=application['function'];self.assertEqual(use['tag'],'type_application')
            self.assertEqual(use['value']['name'],k['name'])
            self.assertEqual(use['witness'],{'tag':'then','first':{'tag':'inner','witness':{'tag':'bottom','type':coordinate}},'second':{'tag':'elim'}})
        with self.assertRaises(m.SharedTransportError) as caught:m.derive_shared_fragment(tree)
        self.assertEqual((caught.exception.code,caught.exception.path),('CAPTURE',error_path))
        self.assertIn('callable import requires a directly bound ordinary lambda',str(caught.exception))
        report=verify_capture(path,fixture_root=root/'inputs'/'pending-callable-import',entry='main.emlf',
            expected_source_hashes={'main.emlf':PENDING_SOURCE_PIN,'SharedPoly.emlf':MODULE_PIN},expected_capture_sha256=PENDING_PIN)
        self.assertFalse(report['fragment_admitted']);self.assertFalse(report['native_admitted'])
        self.assertEqual(report['fragment_error']['code'],'CAPTURE');self.assertEqual(report['fragment_error']['path'],error_path)
        self.assertEqual(report['normalization_replay'],'not completed; retained fragment rejected')
        join,=report['retained_prefix_binding_joins'];self.assertEqual(join['binding'],k['name'])
        self.assertEqual(join['association'],'compiler_local_or_generated');self.assertIsNone(join['resolver_allocation'])
        records=list(path.parent.rglob('*.result.json'));self.assertEqual(len(records),5)
        for record in records:
            result=json.loads(record.read_bytes())
            self.assertEqual(result['returncode'],0);self.assertEqual(result['stderr_bytes'],0)
            self.assertEqual(result['cleanup_errors'],[]);self.assertFalse(result['cleanup_escalated'])
        for name in ('main.emlf','SharedPoly.emlf'):
            self.assertEqual((path.parent/'sources'/name).read_bytes(),(root/'inputs'/'pending-callable-import'/name).read_bytes())
        self.assertEqual((path.parent/'verification.json').read_bytes(),old_record)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),PENDING_PIN)

    def test_scalar_only_evidence_shape_is_unchanged(self):
        for boolean in (False,True):
            out=m.derive_shared_fragment(old.fixture(boolean));d,=out['polymorphism']['definitions']
            self.assertEqual(set(d['captures']),{'policy','scalars'})
            self.assertEqual(d['captures']['policy'],m.GENERIC_CAPTURE_POLICY)


if __name__=='__main__':unittest.main()
