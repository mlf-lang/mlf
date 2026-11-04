"""Stage21 host-only nominal vector/beta controls. Never starts a producer.

Retained original graphs are evidence inputs, not fresh producer qualification.
The old inferred capture must fail exact normalization verification after the
new rule; it is never repaired or passed off as new capture evidence.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

BASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(BASE),str(BASE/'tests')]
import module_shared_transport as m
import module_projection as projection
import test_module_shared_transport as f
from source_capture_v8 import verify_capture

N=f.nominal_type('Chain')
PINS={
 'identity':('4177d8d92e1a0f90271c7e57f82c68a3dca3ffdc9e365fdf104a6c7734b09e94','fad0545e14137ae97581ade4cdc00582f3c612f1e8f571ab15328cdd8879bff0','50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'),
 'curried-const':('71567dbb83f9ece9f4d5500e36ede002ebe2d30b92db5f916fdaa1fea2fe3352','b0619a695664c89f683c05cab2b2c0263d24b15da80c02d589393bc2f62eacc7','6fa9d46c3f07430be03fab525749d3ed17e5cf93e3d2b21218c91625567fd66d'),
 'curried-const-explicit':('5012fd5ebd19101b280f9198f62b9e9aa63ea689a3cf9c45e3bfb27a32d6a24e','814651355eed0bd327fa5fdcccca018d480910632e3c99ed23a1bedd3758e621','6fa9d46c3f07430be03fab525749d3ed17e5cf93e3d2b21218c91625567fd66d'),
}


def scalar_case(value):
    return f.sum_case(value,[f.sum_arm('Nil',(),f.lit(0)),
        f.sum_arm('Cons',(17,None),f.add(f.var(17),f.var(17)))])


def identity_fixture():
    return f.with_data(f.shared(f.let(10,f.ctor('Cons',f.add(f.lit(20),f.lit(1)),f.ctor('Nil')),
        f.choose(f.app(f.use(1,f.B),f.boolean()),scalar_case(f.app(f.use(1,N),f.var(10))),f.lit(0)))),f.recursive_decl())


def const_fixture(direct=False):
    typ=f.arr(f.tv(100),f.arr(f.tv(101),f.tv(100)))
    rhs=f.tabs(100,f.tabs(101,f.app(f.lam(8,typ,f.var(8)),f.lam(2,f.tv(100),f.lam(3,f.tv(101),f.var(2))))))
    consume=f.lam(15,N,scalar_case(f.app(f.app(f.use(1,N,f.B),f.var(15)),f.boolean(False))))
    if direct:
        guard=f.app(f.tapp(f.tabs(500,f.app(f.use(1,f.B,f.tv(500)),f.boolean())),f.inst(N)),f.var(20))
    else:
        guard=f.app(f.app(f.use(1,f.B,N),f.boolean()),f.var(20))
    body=f.let(10,f.ctor('Cons',f.add(f.lit(20),f.lit(1)),f.ctor('Nil')),
        f.let(20,f.app(f.lam(21,f.I,f.ctor('Cons',f.var(21),f.ctor('Nil'))),f.lit(123)),
        f.let(30,consume,f.choose(guard,f.app(f.var(30),f.var(10)),f.lit(0)))))
    return f.with_data(f.let(1,rhs,body),f.recursive_decl())


def retained(test,case):
    value=os.environ.get('IR8_NOMINAL_SHARED_ARGUMENTS_ROOT')
    if not value:test.skipTest('retained Stage21 root not configured')
    root=Path(value);path=root/('capture-'+case+'01')/'capture.stdout'
    blob=path.read_bytes();test.assertEqual(hashlib.sha256(blob).hexdigest(),PINS[case][0])
    return root,path,json.loads(blob)


def verified(root,path,case,expected=None):
    return verify_capture(path,fixture_root=root/'inputs'/case,entry='main.emlf',
        expected_source_hashes={'main.emlf':PINS[case][1],'SharedPoly.emlf':PINS[case][2]},
        expected_capture_sha256=expected or PINS[case][0])


class NominalArgumentReplayTests(unittest.TestCase):
    def reject(self,tree,code=None):
        with self.assertRaises(m.SharedTransportError)as caught:m.derive_shared_fragment(tree)
        if code:self.assertEqual(caught.exception.code,code)

    def test_nominal_use_without_beta_keeps_dialect1(self):
        for raw in (identity_fixture(),const_fixture()):
            out=m.derive_shared_fragment(raw)
            self.assertEqual(out['policy'],m.POLICY);self.assertEqual(out['steps'],[])
            self.assertEqual(out['raw_normalized'],raw)
            self.assertEqual(len(out['polymorphism']['definitions']),1)
            self.assertEqual(m.validate_shared_fragment(raw,out),out)

    def test_data_and_sum_atoms_are_supported_without_unfolding(self):
        data=f.with_data(f.shared(f.case(f.app(f.use(1,f.nominal_type()),f.ctor('Pack',f.lit())))))
        for raw in (data,identity_fixture()):
            out=m.derive_shared_fragment(raw)
            self.assertEqual(out['policy'],m.POLICY)
            self.assertEqual(out['raw_normalized']['declarations'],raw['declarations'])
            self.assertEqual(projection.erase_total(out['raw_normalized']),projection.erase_total(raw))

    def test_nominal_direct_beta_derives2_and_preserves_ordinary_graph(self):
        raw=const_fixture(True);out=m.derive_shared_fragment(raw)
        self.assertEqual(out['policy'],m.NOMINAL_BETA_POLICY)
        step,=out['steps'];self.assertEqual(step['arguments'],[N])
        self.assertEqual(step['substitutions'],[{'binder':500,'argument':N}])
        self.assertEqual(out['polymorphism']['policy'],m.NOMINAL_BETA_POLICY)
        self.assertEqual([u['arguments']for u in out['polymorphism']['uses']],[[N,f.B],[f.B,N]])
        self.assertEqual(projection.erase_total(raw),projection.erase_total(out['raw_normalized']))
        self.assertEqual(len(out['term_correspondence']),len(m._ordinary(raw)))
        self.assertEqual(out['raw_normalized']['body']['value'],raw['body']['value'])

    def test_outer_first_substitutes_nested_nominal_proof_and_annotation(self):
        inner=f.tapp(f.tabs(101,f.lam(2,f.tv(101),f.var(2))),f.inst(f.tv(100)))
        raw=f.with_data(f.app(f.tapp(f.tabs(100,inner),f.inst(N)),f.ctor('Nil')),f.recursive_decl())
        out=m.derive_shared_fragment(raw)
        self.assertEqual([step['input']['path']for step in out['steps']],[['body','function']]*2)
        self.assertEqual([step['arguments']for step in out['steps']],[[N],[N]])
        self.assertEqual(out['raw_normalized']['body'],f.app(f.lam(2,N,f.var(2)),f.ctor('Nil')))
        proof=out['polymorphism']['type_applications'][1]
        self.assertEqual(proof['witness'],f.inst(f.tv(100)));self.assertEqual(proof['normalization_steps'],[0,1])

    def test_complete_dead_vectors_retain_distinct_nominal_coordinates(self):
        rhs=f.tabs(100,f.tabs(101,f.lam(2,f.tv(100),f.var(2))))
        raw=f.with_data(f.let(1,rhs,f.add(f.app(f.use(1,f.I,N),f.lit(21)),
            f.app(f.use(1,f.I,f.B),f.lit(21)))),f.recursive_decl())
        out=m.derive_shared_fragment(raw);uses=out['polymorphism']['uses']
        self.assertEqual([u['arguments']for u in uses],[[f.I,N],[f.I,f.B]])
        self.assertEqual(uses[0]['instantiated_type'],uses[1]['instantiated_type'])
        self.assertEqual(out['nominal_sum']['declarations'][0]['name'],'Chain')

    def test_unselected_and_copied_published_rows_cannot_be_authority(self):
        raw=f.with_data(f.lit(),f.recursive_decl());budget=m._Budget();registry=m._Nominals(raw,budget)
        with self.assertRaisesRegex(m.SharedTransportError,'already checked'):
            m._selected_argument(N,registry,budget,'USE',())
        owner=registry.select('Chain');obligations=[(N,owner,())]
        with mock.patch.object(registry,'select',side_effect=AssertionError('late selection')):
            self.assertIs(m._selected_argument(N,registry,budget,'USE',()),owner)
            m._reconcile_arguments(obligations,registry,({'declarations':[owner]},None),budget)
            with self.assertRaisesRegex(m.SharedTransportError,'not published'):
                m._reconcile_arguments(obligations,registry,({'declarations':[copy.deepcopy(owner)]},None),budget)
            with self.assertRaisesRegex(m.SharedTransportError,'changed declaration'):
                m._reconcile_arguments([(N,copy.deepcopy(owner),())],registry,({'declarations':[owner]},None),budget)

    def test_foreign_parameterized_open_arrow_and_forall_coordinates_reject(self):
        bad=[f.nominal_type('Foreign'),{'tag':'constructor','name':'Chain','arguments':[f.I]},
             f.tv(999),f.arr(f.I,f.I),f.forall(700,f.arr(f.tv(700),f.tv(700)))]
        for argument in bad:
            for direct in (False,True):
                with self.subTest(argument=argument,direct=direct):
                    value=f.tapp(f.identity() if direct else f.var(1),f.inst(argument))
                    self.reject(f.with_data(f.let(1,f.identity(),f.let(20,value,f.lit())),f.recursive_decl()))

    def test_unsupported_nominal_fields_and_parameters_reject_before_beta(self):
        bad=[f.data_decl('Chain','C',(N,)),f.sum_decl('Chain',(('Nil',()),('C',(f.arr(f.I,f.I),)))),
             f.sum_decl('Chain',(('Nil',()),('C',(f.nominal_type('Other'),))))]
        parameter=f.recursive_decl();parameter['parameters']=[{'name':'a','kind':{'tag':'star'}}];bad.append(parameter)
        for declaration in bad:
            self.reject(f.with_data(f.tapp(f.identity(),f.inst(N)),declaration),'NOMINAL')

    def test_nominal_generic_principals_and_operations_stay_excluded(self):
        for rhs in (f.tabs(100,f.lam(2,N,f.var(2))),
                    f.tabs(100,f.lam(2,f.tv(100),f.let(20,f.ctor('Nil'),f.var(2))))):
            self.reject(f.with_data(f.let(1,rhs,f.lit()),f.recursive_decl()),'NOMINAL_SCOPE')

    def test_partial_extra_nonbottom_duplicate_and_malformed_proofs_reject(self):
        rhs=f.tabs(100,f.tabs(101,f.lam(2,f.tv(100),f.var(2))))
        for value in (f.tapp(rhs,f.inst(N)),f.use(1,N,f.B,f.I),
                      f.tapp(f.tabs(100,f.lam(2,f.tv(100),f.var(2)),f.I),f.inst(N)),
                      f.tapp(f.tabs(100,f.tabs(100,f.lit())),f.then(f.inst(N),f.inst(f.I))),
                      f.tapp(f.identity(),{'tag':'elim'})):
            self.reject(f.with_data(f.let(1,rhs,f.let(10,value,f.lit())),f.recursive_decl()))

    def test_wrong_dialect_and_step_graph_claims_reject(self):
        for raw in (const_fixture(),const_fixture(True)):
            out=m.derive_shared_fragment(raw);bad=copy.deepcopy(out)
            bad['policy']=m.POLICY if out['policy']==m.NOMINAL_BETA_POLICY else m.NOMINAL_BETA_POLICY
            with self.assertRaisesRegex(m.SharedTransportError,'EVIDENCE'):m.validate_shared_fragment(raw,bad)
        raw=const_fixture(True);out=m.derive_shared_fragment(raw)
        for mutate in (lambda x:x['steps'].clear(),
                       lambda x:x['steps'][0]['substitutions'][0].update(argument=f.B),
                       lambda x:x['raw_normalized']['body'].update(body=f.lit())):
            bad=copy.deepcopy(out);mutate(bad)
            self.assertNotEqual(bad,out)
            with self.assertRaises(m.SharedTransportError):m.validate_shared_fragment(raw,bad)

    def test_complete_nominal_prefix_retains_coordinate_and_proof_order(self):
        rhs=f.tabs(100,f.tabs(101,f.lam(2,f.tv(100),f.lam(3,f.tv(101),f.var(2)))))
        raw=f.with_data(f.tapp(f.tapp(rhs,f.inst(N)),f.inst(f.B)),f.recursive_decl())
        out=m.derive_shared_fragment(raw);step,=out['steps']
        self.assertEqual(step['arguments'],[N,f.B])
        self.assertEqual(step['substitutions'],[{'binder':100,'argument':N},{'binder':101,'argument':f.B}])
        self.assertEqual(out['raw_normalized']['body'],f.lam(2,N,f.lam(3,f.B,f.var(2))))
        for field in ('arguments','substitutions','witnesses','type_binders'):
            forged=copy.deepcopy(out);forged['steps'][0][field].reverse()
            self.assertNotEqual(forged,out)
            with self.assertRaises(m.SharedTransportError):m.validate_shared_fragment(raw,forged)

    def test_scalar_path_does_not_consult_nominal_eligibility(self):
        with mock.patch.object(m,'_selected_argument',side_effect=AssertionError('scalar fallback')):
            for raw in (f.shared(),f.tapp(f.identity(),f.inst(f.I))):
                self.assertEqual(m.derive_shared_fragment(raw)['policy'],m.POLICY)

    def test_retained_identity_and_explicit_control_exact_replay(self):
        for case in ('identity','curried-const-explicit'):
            root,path,raw=retained(self,case);out=m.derive_shared_fragment(raw['projection']['projected_annotated'])
            for key in ('policy','steps','raw_normalized'):self.assertEqual(out[key],raw['normalization'][key])
            report=verified(root,path,case);self.assertTrue(report['fragment_admitted'])
            self.assertFalse(report['source_admitted']);self.assertFalse(report['native_admitted'])

    def test_original_inferred_graph_replays2_but_old_capture_cannot_upgrade(self):
        root,path,raw=retained(self,'curried-const');out=m.derive_shared_fragment(raw['projection']['projected_annotated'])
        self.assertEqual(out['policy'],m.NOMINAL_BETA_POLICY)
        self.assertEqual(len(out['steps']),4);self.assertEqual(len(raw['normalization']['steps']),3)
        self.assertEqual(out['steps'][:3],raw['normalization']['steps'])
        self.assertEqual(projection.erase_total(out['raw_normalized']),raw['normalization']['input_erased'])
        with self.assertRaisesRegex(ValueError,'independent normalization.policy'):
            verified(root,path,'curried-const')

    def test_false2_on_real_scalar_dialect_rejected(self):
        root,_,raw=retained(self,'identity');raw['normalization']['policy']=m.NOMINAL_BETA_POLICY
        with tempfile.TemporaryDirectory()as d:
            path=Path(d)/'forged.json';blob=json.dumps(raw).encode();path.write_bytes(blob)
            with self.assertRaisesRegex(ValueError,'independent normalization.policy'):
                verified(root,path,'identity',hashlib.sha256(blob).hexdigest())


if __name__=='__main__':unittest.main()
