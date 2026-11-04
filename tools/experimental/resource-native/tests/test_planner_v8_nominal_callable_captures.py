"""Nominal-bearing ordinary callable captures: host-only, no native launches.

Synthetic fixtures prove planner guards, not original source acceptance. Real
capture tests independently replay pinned evidence and preserve old full outputs.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

BASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(BASE),str(BASE/'tests')]
import planner_v8 as planner
import module_shared_transport as transport
import test_planner_v8 as f
import test_module_shared_transport as s
import test_planner_v8_recursive_captures as c
import test_planner_v8_callable_captures as a
import test_planner_v8_nominal_captures as n
import test_planner_v8_sum as sums
from test_shared_source_native import instruction
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.program_schema import ResourceError
from resource_ir_v8.runtime_emit import emit_runtime

POLICY='closed-admitted-callable-shared-view-captures/1'
BOX=f.nominal('Box')
PINS={
    'nominal-argument':('1e500631c99a661697fc81ae8750d189cf753810ceefbb6442248109b554952d',
                        '1fff1b8e7f79c577f1d478a17b36ae20b5b3aaad1155fd476b5cf561e5e47257'),
    'nominal-result':('4d9b7064b15c5c782236590cdd64c1a8dd55faf4a3d6f5cc94ae275d1276492d',
                      '171e0704fb583f3c05c02a9cfd225c7f66567365e491de2e04a334875bca1b58')}


def fixture(kind='nominal-argument',closed=False):
    raw=c.fixture(scalar=False,view=False);rec=raw['body']['body']
    if kind=='nominal-argument':
        typ=f.arr(c.SELF,f.I)
        number=f.var(35) if closed else f.app(f.use(1,f.I),f.var(35))
        body=s.sum_case(f.var(33),[s.sum_arm('Nil',(),f.lit(0)),s.sum_arm('Cons',(35,None),number)])
        value=f.lam(32,c.SELF,f.let(33,f.app(f.lam(34,c.SELF,f.var(34)),f.var(32)),body))
        left=f.app(f.var(30),f.var(12));right=copy.deepcopy(left)
    elif kind=='nominal-result':
        raw['declarations'].append(f.declaration('Box','BoxValue',f.I))
        typ=f.arr(f.I,BOX)
        field=f.var(33) if closed else f.app(f.use(1,f.I),f.var(33))
        value=f.lam(32,f.I,f.let(33,f.app(f.lam(34,f.I,f.var(34)),f.var(32)),f.construct('BoxValue',field)))
        arm=rec['bindings'][0]['value']['argument']['body']['body']['alternatives'][1]
        arm['pattern']['fields'][0]=f.name(60)
        left=f.data_case(f.app(f.var(30),f.var(60)),'BoxValue',[61],f.var(61))
        right=f.data_case(f.app(f.var(30),f.var(60)),'BoxValue',[62],f.var(62))
    elif kind=='nested-argument':
        typ=f.arr(f.arr(c.SELF,f.I),f.I)
        value=f.lam(32,f.arr(c.SELF,f.I),f.app(f.var(32),f.construct('Cons',f.lit(21),f.construct('Nil'))))
        left=f.app(f.var(30),f.lam(70,c.SELF,f.lit(21)))
        right=f.app(f.var(30),f.lam(71,c.SELF,f.lit(21)))
    elif kind=='nested-result':
        raw['declarations'].append(f.declaration('Box','BoxValue',f.I))
        typ=f.arr(f.I,f.arr(f.B,BOX))
        value=f.lam(32,f.I,f.lam(33,f.B,f.construct('BoxValue',f.var(32))))
        left=f.data_case(f.app(f.app(f.var(30),f.lit(21)),f.boolean()),'BoxValue',[61],f.var(61))
        right=f.data_case(f.app(f.app(f.var(30),f.lit(21)),f.boolean()),'BoxValue',[62],f.var(62))
    else:raise AssertionError('unknown fixture')
    n.contribution(raw)['argument']=f.add(left,right)
    rec['body']=f.let(40,f.add(f.lit(20),f.lit(1)),f.choose(f.app(f.use(1,f.B),f.boolean()),
        f.add(f.app(f.var(10),f.construct('Nil')),f.app(f.var(10),f.construct('Cons',f.var(40),f.construct('Nil')))),f.lit(0)))
    raw['body']['body']=f.let(30,f.app(f.lam(31,typ,f.var(31)),value),rec)
    return raw


def caps(fragment):return fragment['recursion']['bindings'][0]['captures']


def files(emission):
    return {filename:getattr(emission,field).encode() for filename,field in
        (('ir8_runtime_generated.h','runtime_header'),('ir8_runtime_generated.c','runtime_source'),
         ('ir8_packet_generated.h','packet_header'),('ir8_packet_generated.c','packet_source'))}


class NominalCallablePlannerTests(unittest.TestCase):
    def test_nominal_argument_and_result_pending_helpers_both_modes(self):
        for kind in PINS:
            for groups in (False,True):
                with self.subTest(kind=kind,groups=groups):
                    raw=fixture(kind);result=n.checked(self,raw,groups);knot,carrier,closure=c.target(result)
                    captured=knot['captures'];callable,=captured['callables']
                    self.assertEqual(captured['policy'],POLICY)
                    self.assertEqual(set(captured),{'policy','scalars','callables','nominals','views'})
                    self.assertEqual(captured['scalars'],[]);self.assertEqual(captured['nominals'],[])
                    self.assertEqual(captured['views'],[]);self.assertEqual(carrier['view_captures'],[])
                    self.assertEqual(set(callable),{'binding','type','occurrences'})
                    self.assertEqual(len(callable['occurrences']),2)
                    expected=f.arr(c.SELF,f.I) if kind=='nominal-argument' else f.arr(f.I,BOX)
                    self.assertEqual(callable['type'],expected)
                    owner=a.allocation_for_binder(result,raw,30)
                    capture,=[r for r in carrier['mono_captures'] if r['binder']==30]
                    self.assertEqual(owner['op'],'application')
                    self.assertEqual(closure['captures'][capture['capture']],owner['out'])
                    self.assertIsNone(carrier['type_scope'])
                    self.assertEqual(json.loads(emit_runtime(result['program']).canonical_ir_json),result['program'])

    def test_support_pending_wrappers_and_saved_view_remain_unchanged(self):
        for kind in PINS:
            for closed in (False,True):
                for groups in (False,True):
                    raw=fixture(kind,closed);result=n.checked(self,raw,groups);knot,carrier,_=c.target(result)
                    row,=[r for r in carrier['mono_captures'] if r['binder']==30]
                    self.assertEqual(row['relation'],'below' if closed and groups else 'down')
                    self.assertFalse(any(op['op'] in ('force','field') for op in
                        result['program']['entry'][:knot['fill']['segments'][0]]))
                    self.assertEqual(instruction(result['program'],knot['fill'])['value'],knot['rhs_owner'])
                    if not closed:
                        self.assertEqual(sum(x['op']=='instantiate' for x in c.all_ops(result['program'])),2)
                        self.assertEqual(sum(x['op']=='instantiate' for x in result['program']['entry']),2)
                        helper=raw['body']['body']['value']['argument']
                        path=next(p for p,node in transport._walk(raw) if node is helper)
                        actual,=[r for r in result['binding']['source_map']['carrier_map'] if r['source']==planner.address(path)]
                        self.assertEqual(len(actual['view_captures']),1)

    def test_nested_arrow_positions_are_full_types_not_flattened(self):
        for kind in ('nested-argument','nested-result'):
            for groups in (False,True):
                result=n.checked(self,fixture(kind),groups);knot,carrier,_=c.target(result)
                row,=[r for r in carrier['mono_captures'] if r['binder']==30]
                typ=result['program']['types'][row['layout'][1:]]
                self.assertEqual((typ['protocol'],typ['result_identity']),('repeat','unknown'))
                inner=result['program']['types'][typ['argument' if kind=='nested-argument' else 'result']]
                self.assertEqual(inner['tag'],'arrow')
                self.assertEqual((inner['protocol'],inner['result_identity']),('repeat','unknown'))
                self.assertEqual(json.loads(emit_runtime(result['program']).canonical_ir_json),result['program'])

    def test_old_policies_cannot_admit_nominal_arrow_and_new_policy_requires_one(self):
        raw=fixture();fragment=transport.derive_shared_fragment(raw)
        for policy in ('closed-scalar-callable-shared-view-captures/1',
                       'closed-scalar-callable-nominal-shared-view-captures/1'):
            bad=copy.deepcopy(fragment);caps(bad)['policy']=policy
            if policy=='closed-scalar-callable-shared-view-captures/1':caps(bad).pop('nominals')
            with self.assertRaises(planner.PlanningError):planner.Planner(bad).finish()
            with self.assertRaises(transport.SharedTransportError):planner.plan_fragment(raw,fragment=bad)
        old=transport.derive_shared_fragment(a.fixture())
        caps(old).update(policy=POLICY,nominals=[])
        with self.assertRaisesRegex(planner.PlanningError,'requires a captured arrow with a nominal leaf'):
            planner.Planner(old).finish()

    def test_exact_category_partition_and_occurrences_reject_forgeries(self):
        raw=fixture();fragment=transport.derive_shared_fragment(raw)
        changes=[lambda c:c.pop('nominals'),lambda c:c.pop('views'),lambda c:c.pop('callables'),
            lambda c:c['callables'].clear(),lambda c:c.update(extra=[]),
            lambda c:c['callables'].append(copy.deepcopy(c['callables'][0])),
            lambda c:c['scalars'].append(copy.deepcopy(c['callables'][0])),
            lambda c:c['nominals'].append(copy.deepcopy(c['callables'][0]))]
        for change in changes:
            bad=copy.deepcopy(fragment);change(caps(bad))
            with self.assertRaises(transport.SharedTransportError):planner.plan_fragment(raw,fragment=bad)
            with self.assertRaises(planner.PlanningError):planner.Planner(bad).finish()
        for positions in ([],[caps(fragment)['callables'][0]['occurrences'][0]]):
            bad=copy.deepcopy(fragment);caps(bad)['callables'][0]['occurrences']=positions
            with self.assertRaises(transport.SharedTransportError):planner.plan_fragment(raw,fragment=bad)

    def test_wrong_nominal_leaf_family_position_and_open_types_reject(self):
        raw=fixture('nominal-result');fragment=transport.derive_shared_fragment(raw)
        types=[f.arr(c.SELF,f.I),f.arr(BOX,f.I),f.arr(f.I,c.SELF),f.arr(f.I,f.I),f.I,BOX,
            f.arr(f.I,f.nominal('Foreign')),f.arr(f.I,f.ty(999)),
            f.arr(f.I,{'tag':'constructor','name':'Box','arguments':[f.I]}),
            f.arr(f.I,{'tag':'forall','id':999,'bound':{'tag':'bottom'},'body':BOX})]
        for typ in types:
            bad=copy.deepcopy(fragment);caps(bad)['callables'][0]['type']=typ
            with self.assertRaises(transport.SharedTransportError):planner.plan_fragment(raw,fragment=bad)
            with self.assertRaises(planner.PlanningError):planner.Planner(bad).finish()
        engine=planner.Planner(fragment)
        with self.assertRaises(planner.PlanningError):engine.logical(BOX,'S0')

    def test_same_shape_foreign_declaration_does_not_match_owner(self):
        raw=fixture('nominal-result');raw['declarations'].append(f.declaration('OtherBox','OtherValue',f.I))
        helper=raw['body']['body'];raw['body']['body']=f.let(90,f.construct('OtherValue',f.lit(0)),helper)
        fragment=transport.derive_shared_fragment(raw);engine=planner.Planner(fragment)
        self.assertNotEqual(engine.logical(BOX,None),engine.logical(f.nominal('OtherBox'),None))
        caps(fragment)['callables'][0]['type']=f.arr(f.I,f.nominal('OtherBox'))
        with self.assertRaisesRegex(planner.PlanningError,'available exact ordinary owner'):
            planner.Planner(fragment).finish()

    def test_same_typed_distinct_helpers_remain_distinct_owners(self):
        raw=fixture('nominal-argument');helper=raw['body']['body'];rec=helper['body']
        second=f.app(f.lam(80,f.arr(c.SELF,f.I),f.var(80)),f.lam(81,c.SELF,f.lit(21)))
        helper['body']=f.let(82,second,rec)
        inner=n.contribution(raw)['argument'];inner['argument']['function']=f.var(82)
        result=n.checked(self,raw);knot,carrier,closure=c.target(result)
        self.assertEqual([r['binding']['id'] for r in knot['captures']['callables']],[30,82])
        left,right=[r for r in carrier['mono_captures'] if r['binder'] in (30,82)]
        self.assertEqual(left['layout'],right['layout'])
        self.assertNotEqual(closure['captures'][left['capture']],closure['captures'][right['capture']])

    def test_nested_and_unselected_ordinary_helpers_are_still_captures(self):
        raw=fixture();old=n.contribution(raw)['argument']
        n.contribution(raw)['argument']=f.choose(f.boolean(False),f.app(f.lam(85,f.I,old),f.lit(0)),f.lit(42))
        result=n.checked(self,raw);knot,carrier,_=c.target(result)
        self.assertEqual([r['binding']['id'] for r in knot['captures']['callables']],[30])
        self.assertTrue(any(row is not carrier and any(x['binder']==30 for x in row['mono_captures'])
                            for row in result['binding']['source_map']['carrier_map']))

    def test_new_policy_preserves_all_other_capture_categories(self):
        raw=fixture('nominal-result');old=n.contribution(raw)['argument']
        extra=f.add(f.var(90),f.add(f.app(f.var(91),f.lit(0)),
            f.add(f.data_case(f.var(92),'BoxValue',[93],f.var(93)),f.app(f.use(1,f.I),f.var(90)))))
        n.contribution(raw)['argument']=f.add(old,extra)
        helper=raw['body']['body'];helper['body']=f.let(90,f.lit(0),
            f.let(91,f.lam(94,f.I,f.var(94)),f.let(92,f.construct('BoxValue',f.lit(0)),helper['body'])))
        for groups in (False,True):
            result=n.checked(self,raw,groups);knot,carrier,_=c.target(result);captured=knot['captures']
            self.assertEqual(captured['policy'],POLICY)
            self.assertEqual([r['binding']['id'] for r in captured['callables']],[30,91])
            self.assertEqual([r['binding']['id'] for r in captured['scalars']],[90])
            self.assertEqual([r['binding']['id'] for r in captured['nominals']],[92])
            self.assertEqual(len(captured['views']),1)
            self.assertEqual({r['binder'] for r in carrier['mono_captures']},{10,30,90,91,92})
            self.assertEqual(len(carrier['view_captures']),1)

    def test_reference_identity_support_contract_and_total_capture_bound(self):
        fragment=transport.derive_shared_fragment(fixture('nested-result'));original=fragment['recursion']['bindings'][0]
        raw_type=f.arr(f.I,f.arr(f.B,BOX))
        for count in (63,64):
            engine=planner.Planner(fragment);typ=engine.logical(raw_type,None);ids=list(range(200,200+count))
            evidence=copy.deepcopy(original);evidence['free_term_bindings']=ids
            evidence['captures']={'policy':POLICY,'scalars':[],'nominals':[],'views':[],
                'callables':[{'binding':f.name(i),'type':raw_type,'occurrences':[]} for i in ids]}
            owners={i:planner.Reference('owner'+str(i),typ,carrier=i,strict=bool(i%2)) for i in ids}
            if count==64:
                with self.assertRaisesRegex(planner.PlanningError,'capture count exceeds 64'):
                    engine.recursive_captures(evidence,set(ids),{},owners,{})
            else:
                carried,saved=engine.recursive_captures(evidence,set(ids),{},owners,{})
                self.assertEqual(saved,{})
                self.assertTrue(all(carried[i] is owners[i] for i in ids))
                altered=[None,planner.SchemeReference('bad',0),
                    planner.Reference('bad',('arrow',typ[1],typ[2],'once','unknown')),
                    planner.Reference('bad',('arrow',typ[1],typ[2],'repeat','argument')),
                    planner.Reference('bad',('arrow',typ[1],('arrow',typ[2][1],typ[2][2],'once','unknown'),'repeat','unknown'))]
                for source in altered:
                    wrong=dict(owners);wrong[ids[0]]=source
                    with self.assertRaises(planner.PlanningError):engine.recursive_captures(evidence,set(ids),{},wrong,{})
                # A named logical leaf cannot bypass the published layout bank.
                del engine.nominal_layouts[engine.logical(BOX,None)]
                with self.assertRaisesRegex(planner.PlanningError,'lacks a published declaration'):
                    engine.recursive_captures(evidence,set(ids),{},owners,{})

    def test_nominal_callable_factory_external32_limit_is_not_carrier64(self):
        # The arm also captures self and the ordinary xs owner used as helper
        # argument. Those two slots count separately from the helper owners.
        for count in (30,31):
            raw=c.fixture(scalar=False,view=False)
            n.contribution(raw)['argument']=sums.balanced([f.app(f.var(200+i),f.var(12)) for i in range(count)])
            body=raw['body']['body']
            for i in reversed(range(count)):body=f.let(200+i,f.lam(600+i,c.SELF,f.lit(1)),body)
            raw['body']['body']=body
            fragment=transport.derive_shared_fragment(raw)
            self.assertEqual(len(caps(fragment)['callables']),count)
            if count==31:
                with self.assertRaisesRegex(planner.PlanningError,'external capture count exceeds32'):
                    planner.plan_fragment(raw,fragment=fragment)
            else:
                result=n.checked(self,raw);row,=result['binding']['source_map']['sum_case_map']
                arm=instruction(result['program'],row['factory'])['arms']['V1']['captures']
                # The existing xs owner is also an external factory capture.
                self.assertEqual(sum(r['kind']=='external' for r in arm.values()),32)

    def test_resource_type_result_contract_and_strict_support_guards(self):
        result=n.checked(self,fixture('nominal-result'));_,carrier,_=c.target(result)
        capture,=[r for r in carrier['mono_captures'] if r['binder']==30]
        for change in ('family','position','support','once','identity'):
            bad=copy.deepcopy(result['program']);contract=bad['functions'][carrier['ir_code']]['captures'][capture['capture']]
            typ=bad['types'][contract['layout'][1:]]
            if change=='family':typ['result']=typ['argument']
            elif change=='position':typ['argument'],typ['result']=typ['result'],typ['argument']
            elif change=='support':contract['relation']='below'
            elif change=='once':typ['protocol']='once'
            else:typ['result_identity']='argument'
            with self.assertRaises((ResourceError,ValueError)):check_metadata(bad)
            if change not in ('once','identity'):
                with self.assertRaises((ResourceError,ValueError)):check_resources(bad)


CAPTURE_ROOT=os.environ.get('IR8_NOMINAL_CALLABLE_CAPTURES_ROOT')
STAGE16_ROOT=os.environ.get('IR8_CALLABLE_CAPTURES_ROOT')
STAGE18_ROOT=os.environ.get('IR8_NOMINAL_CAPTURES_ROOT')


class RetainedNominalCallableTests(unittest.TestCase):
    @unittest.skipUnless(CAPTURE_ROOT,'set IR8_NOMINAL_CALLABLE_CAPTURES_ROOT for retained captures')
    def test_both_real_captures_full_replay_check_emit(self):
        from source_capture_v8 import verify_capture
        root=Path(CAPTURE_ROOT)
        for label,(capture_sha,source_sha) in PINS.items():
            path=root/f'capture-{label}01/capture.stdout'
            verification=verify_capture(path,fixture_root=root/'inputs'/label,entry='main.emlf',
                expected_capture_sha256=capture_sha,expected_source_hashes={'main.emlf':source_sha,'SharedPoly.emlf':n.SHARED_SHA})
            self.assertTrue(verification['fragment_admitted'])
            self.assertFalse(verification['source_admitted']);self.assertFalse(verification['native_admitted'])
            capture=json.loads(path.read_bytes());raw=capture['projection']['projected_annotated']
            fragment=transport.derive_shared_fragment(raw)
            self.assertEqual(fragment['raw_normalized'],capture['normalization']['raw_normalized'])
            self.assertEqual(fragment['steps'],capture['normalization']['steps'])
            evidence=fragment['recursion']['bindings'][0];callable,=caps(fragment)['callables']
            self.assertEqual(len(callable['occurrences']),2)
            for groups in (False,True):
                result=planner.plan_fragment(raw,fragment=fragment,data_groups=groups);knot,carrier,closure=c.target(result)
                self.assertEqual(knot['captures'],evidence['captures']);self.assertEqual(carrier['view_captures'],[])
                self.assertEqual(knot['captures']['nominals'],[]);self.assertEqual(knot['captures']['scalars'],[])
                owner=a.allocation_for_binder(result,fragment['raw_normalized'],callable['binding']['id'])
                row,=[r for r in carrier['mono_captures'] if r['binder']==callable['binding']['id']]
                self.assertEqual(owner['op'],'application');self.assertEqual(closure['captures'][row['capture']],owner['out'])
                self.assertEqual(sum(op['op']=='instantiate' for op in c.all_ops(result['program'])),2)
                check_resources(result['program'])
                self.assertEqual(json.loads(emit_runtime(result['program']).canonical_ir_json),result['program'])

    def golden(self,root,capture_label,capture_sha,directory):
        data=(root/f'capture-{capture_label}01/capture.stdout').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),capture_sha)
        raw=json.loads(data)['projection']['projected_annotated']
        for mode in ('coarse','groups'):
            old=directory/mode;prior=json.loads((old/'planned.json').read_bytes())
            current=planner.plan_fragment(raw,data_groups=mode=='groups')
            self.assertEqual(current,prior);self.assertEqual(a.canonical(current),a.canonical(prior))
            for name,data in files(emit_runtime(current['program'])).items():self.assertEqual(data,(old/name).read_bytes(),name)

    @unittest.skipUnless(STAGE16_ROOT,'set IR8_CALLABLE_CAPTURES_ROOT for frozen Stage16 goldens')
    def test_stage16_full_plans_and_all_generated_bytes_unchanged(self):
        root=Path(STAGE16_ROOT)
        for label,sha in (('pending-step','8d6452d60f503b6e685f4abd48ca8967489a25135ec75d0e681e719199e7a5df'),
                          ('view-alias','feb1656e2b397be0fed3eba1f40ba95785eb1029a8aab6fdb5aa164fefa01668')):
            self.golden(root,label,sha,root/'host-plan01'/label)

    @unittest.skipUnless(STAGE18_ROOT,'set IR8_NOMINAL_CAPTURES_ROOT for frozen Stage18 goldens')
    def test_stage18_full_plans_and_all_generated_bytes_unchanged(self):
        root=Path(STAGE18_ROOT)
        for label,(sha,_) in n.PINS.items():self.golden(root,label,sha,root/'host-plan01'/label)


if __name__=='__main__':unittest.main()
