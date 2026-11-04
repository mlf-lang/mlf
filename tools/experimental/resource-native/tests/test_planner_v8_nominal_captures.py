"""Exact nominal-owner recursion captures: host-only replay/check/emission.

Synthetic trees exercise guards without claiming original source authority.
Optional retained tests pin real captures and complete old generated outputs.
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
import test_planner_v8_sum as sums
from test_shared_source_native import instruction
from resource_ir_v8.checker import check_resources
from resource_ir_v8.metadata import check_metadata
from resource_ir_v8.program_schema import ResourceError
from resource_ir_v8.runtime_emit import emit_runtime

POLICY='closed-scalar-callable-nominal-shared-view-captures/1'
PAYLOAD=f.nominal('Payload')
II=f.arr(f.I,f.I)
PINS={
    'data-owner':('248174cce063da15ecd8560c72df9a22b06ca3003e41a385cd2523da576c0413',
                  '178a56e23219b9e51e9bceb9d26555c2eb13fa54a84a16c7995fe94395fe1dab'),
    'sum-owner':('dd03eee615c2d78e49050d3123442f3c1ec166c2b008abb1741f9b075a1eb19c',
                 '3eb612053a5a2c892ab0564d5ff505023958c6c04782383ed6034b509876ec01')}
SHARED_SHA='50fd7fa662c9290a61b0a69012cd2e886a44075de9827dff4edd3f0c839573a7'


def fixture(kind='data-owner',ready=False):
    tree=c.fixture(scalar=False,view=False);rec=tree['body']['body']
    if kind=='data-owner':
        tree['declarations'].append(f.declaration('Payload','Pack',f.I,II))
        typ=PAYLOAD
        field=(f.lam(35,f.I,f.var(35)) if ready else
               f.app(f.lam(36,II,f.var(36)),f.use(1,f.I)))
        value=f.construct('Pack',f.lit(21) if ready else f.add(f.lit(20),f.lit(1)),field)
        contribution=f.data_case(f.var(30),'Pack',[32,33],f.app(f.var(33),f.var(32)))
    elif kind=='sum-owner':
        typ=c.SELF
        tail=f.app(f.lam(34,f.I,f.construct('Cons',f.var(34),f.construct('Nil'))),f.lit(123))
        value=f.construct('Cons',f.add(f.lit(20),f.lit(1)),tail)
        contribution=s.sum_case(f.var(30),[s.sum_arm('Nil',(),f.lit(0)),
            s.sum_arm('Cons',(32,None),f.app(f.use(1,f.I),f.var(32)))])
    else:raise AssertionError('unknown fixture')
    rec['bindings'][0]['value']['argument']['body']['body']['alternatives'][1]['body']['function']['argument']=contribution
    tree['body']['body']=f.let(30,f.app(f.lam(31,typ,f.var(31)),value),rec)
    return tree


def recursive(tree):
    return next(n for _,n in transport._walk(tree) if n['tag']=='letrec')


def contribution(tree):
    return recursive(tree)['bindings'][0]['value']['argument']['body']['body']['alternatives'][1]['body']['function']


def checked(test,raw,groups=False):
    before=copy.deepcopy(raw);result=planner.plan_fragment(raw,data_groups=groups)
    test.assertEqual(raw,before)
    test.assertFalse(result['binding']['source_admitted'])
    test.assertFalse(result['binding']['ordinary_K_checked'])
    check_resources(result['program'])
    return result


class NominalCapturePlannerTests(unittest.TestCase):
    def test_data_sum_pending_owners_both_modes(self):
        for kind in PINS:
            for groups in (False,True):
                with self.subTest(kind=kind,groups=groups):
                    raw=fixture(kind);result=checked(self,raw,groups)
                    knot,carrier,closure=c.target(result);caps=knot['captures'];nominal,=caps['nominals']
                    self.assertEqual(caps['policy'],POLICY);self.assertEqual(caps['callables'],[])
                    self.assertEqual(caps['scalars'],[])
                    self.assertEqual(len(caps['views']),int(kind=='sum-owner'))
                    self.assertEqual(nominal['declaration'],int(kind=='data-owner'))
                    self.assertEqual(set(nominal),{'binding','type','declaration','occurrences'})
                    owner=a.allocation_for_binder(result,raw,nominal['binding']['id'])
                    capture,=[r for r in carrier['mono_captures'] if r['binder']==nominal['binding']['id']]
                    self.assertEqual(owner['op'],'application')
                    self.assertEqual(closure['captures'][capture['capture']],owner['out'])
                    self.assertIsNone(carrier['type_scope'])
                    self.assertEqual(json.loads(emit_runtime(result['program']).canonical_ir_json),result['program'])

    def test_support_and_actual_rhs_are_preserved_without_demand(self):
        for ready in (False,True):
            for groups in (False,True):
                result=checked(self,fixture(ready=ready),groups)
                knot,carrier,_=c.target(result)
                capture,=[r for r in carrier['mono_captures'] if r['binder']==30]
                self.assertEqual(capture['relation'],'below' if ready and groups else 'down')
                entry=result['program']['entry'];end=knot['fill']['segments'][0]
                self.assertFalse(any(op['op'] in ('force','field') for op in entry[:end]))
                self.assertEqual(instruction(result['program'],knot['fill'])['value'],knot['rhs_owner'])
                rhs,=[r for r in result['binding']['source_map']['allocation_map'] if r['source']==knot['rhs']]
                self.assertEqual(instruction(result['program'],rhs['instruction'])['op'],'application')

    def test_nominal_does_not_expand_into_shared_field_captures(self):
        result=checked(self,fixture());knot,carrier,_=c.target(result)
        self.assertEqual(knot['captures']['views'],[]);self.assertEqual(carrier['view_captures'],[])
        self.assertEqual(sum(x['op']=='instantiate' for x in c.all_ops(result['program'])),2)
        self.assertEqual(sum(x['op']=='instantiate' for x in result['program']['entry']),2)
        case,=result['binding']['source_map']['case_map']
        self.assertEqual(len(case['projections']),2)
        for field in case['projections']:
            self.assertEqual([instruction(result['program'],field[k])['op']
                for k in ('loan','retain','end_borrow')],['field','retain','end_borrow'])

    def test_all_categories_partition_actual_free_owners(self):
        raw=fixture('sum-owner');old=contribution(raw)['argument']
        contribution(raw)['argument']=f.add(old,f.app(f.var(51),f.var(50)))
        owner=raw['body']['body'];owner['body']=f.let(50,f.lit(0),f.let(51,f.lam(52,f.I,f.var(52)),owner['body']))
        for groups in (False,True):
            result=checked(self,raw,groups);knot,carrier,_=c.target(result);caps=knot['captures']
            self.assertEqual([r['binding']['id'] for r in caps['scalars']],[50])
            self.assertEqual([r['binding']['id'] for r in caps['callables']],[51])
            self.assertEqual([r['binding']['id'] for r in caps['nominals']],[30])
            self.assertEqual(len(caps['views']),1)
            self.assertEqual({r['binder'] for r in carrier['mono_captures']},{10,30,50,51})

    def test_distinct_same_typed_owners_do_not_merge(self):
        raw=fixture();old=contribution(raw)['argument']
        contribution(raw)['argument']=f.add(old,f.data_case(f.var(40),'Pack',[41,42],f.app(f.var(42),f.var(41))))
        owner=raw['body']['body'];owner['body']=f.let(40,f.construct('Pack',f.lit(1),f.lam(43,f.I,f.var(43))),owner['body'])
        result=checked(self,raw);knot,carrier,closure=c.target(result)
        self.assertEqual([r['binding']['id'] for r in knot['captures']['nominals']],[30,40])
        left,right=[r for r in carrier['mono_captures'] if r['binder'] in (30,40)]
        self.assertEqual(left['layout'],right['layout'])
        self.assertNotEqual(closure['captures'][left['capture']],closure['captures'][right['capture']])

    def test_same_shape_different_nominal_declarations_stay_distinct(self):
        raw=fixture();raw['declarations'].append(f.declaration('Other','OtherPack',f.I,II))
        old=contribution(raw)['argument']
        contribution(raw)['argument']=f.add(old,f.data_case(f.var(40),'OtherPack',[41,42],f.app(f.var(42),f.var(41))))
        owner=raw['body']['body'];owner['body']=f.let(40,f.construct('OtherPack',f.lit(1),f.lam(43,f.I,f.var(43))),owner['body'])
        result=checked(self,raw);knot,carrier,_=c.target(result)
        self.assertEqual([r['declaration'] for r in knot['captures']['nominals']],[1,2])
        left,right=[r for r in carrier['mono_captures'] if r['binder'] in (30,40)]
        self.assertNotEqual(left['layout'],right['layout'])
        fragment=transport.derive_shared_fragment(raw)
        fragment['recursion']['bindings'][0]['captures']['nominals'][0].update(type=f.nominal('Other'),declaration=2)
        with self.assertRaisesRegex(planner.PlanningError,'available exact ordinary owner'):
            planner.Planner(fragment).finish()

    def test_unselected_nested_carriers_keep_nominal_inventory(self):
        raw=fixture();old=contribution(raw)['argument']
        contribution(raw)['argument']=f.choose(f.boolean(False),f.app(f.lam(40,f.I,old),f.lit(0)),f.lit(21))
        result=checked(self,raw);knot,carrier,_=c.target(result)
        self.assertEqual([r['binding']['id'] for r in knot['captures']['nominals']],[30])
        descendants=[r for r in result['binding']['source_map']['carrier_map'] if r is not carrier and
                     any(x['binder']==30 for x in r['mono_captures'])]
        self.assertTrue(descendants)

    def test_forged_policy_partition_type_and_declaration_rejected(self):
        raw=fixture();fragment=transport.derive_shared_fragment(raw)
        mutations=[lambda c:c.pop('nominals'),lambda c:c['nominals'].clear(),lambda c:c.pop('callables'),
            lambda c:c.update(policy='closed-scalar-callable-shared-view-captures/1'),
            lambda c:c['nominals'][0].update(declaration=0),lambda c:c['nominals'][0].update(declaration=True),
            lambda c:c['nominals'][0].update(type=f.nominal('IntList')),
            lambda c:c['nominals'][0].update(type=f.I),
            lambda c:c['nominals'].append(copy.deepcopy(c['nominals'][0])),
            lambda c:c['scalars'].append(copy.deepcopy(c['nominals'][0])),
            lambda c:c['callables'].append(copy.deepcopy(c['nominals'][0]))]
        for change in mutations:
            bad=copy.deepcopy(fragment);change(bad['recursion']['bindings'][0]['captures'])
            with self.assertRaises(transport.SharedTransportError):planner.plan_fragment(raw,fragment=bad)
            with self.assertRaises(planner.PlanningError):planner.Planner(bad).finish()
        bad=copy.deepcopy(fragment);bad['recursion']['bindings'][0]['captures']['nominals'][0]['occurrences']=[]
        with self.assertRaises(transport.SharedTransportError):planner.plan_fragment(raw,fragment=bad)

    def test_non_nominal_and_unregistered_types_reject(self):
        fragment=transport.derive_shared_fragment(fixture())
        for typ in (f.ty(99),f.nominal('Foreign'),f.arr(PAYLOAD,f.I),f.arr(f.I,f.I),
                    {'tag':'constructor','name':'Payload','arguments':[f.I]},
                    {'tag':'forall','id':99,'bound':{'tag':'bottom'},'body':PAYLOAD}):
            bad=copy.deepcopy(fragment);bad['recursion']['bindings'][0]['captures']['nominals'][0]['type']=typ
            with self.assertRaises(planner.PlanningError):planner.Planner(bad).finish()
        with self.assertRaises(transport.SharedTransportError):planner.plan_fragment(a.fixture('nominal'))

    def test_original_owner_identity_and_capture_limit(self):
        fragment=transport.derive_shared_fragment(fixture());original=fragment['recursion']['bindings'][0]
        for count in (63,64):
            engine=planner.Planner(fragment);typ=engine.logical(PAYLOAD,None);ids=list(range(200,200+count))
            evidence=copy.deepcopy(original);evidence['free_term_bindings']=ids
            evidence['captures']={'policy':POLICY,'scalars':[],'callables':[],'views':[],
                'nominals':[{'binding':f.name(i),'type':PAYLOAD,'declaration':typ[1],'occurrences':[]} for i in ids]}
            owners={i:planner.Reference('owner'+str(i),typ,carrier=i,strict=bool(i%2)) for i in ids}
            if count==64:
                with self.assertRaisesRegex(planner.PlanningError,'capture count exceeds 64'):
                    engine.recursive_captures(evidence,set(ids),{},owners,{})
            else:
                carried,saved=engine.recursive_captures(evidence,set(ids),{},owners,{})
                self.assertEqual(saved,{})
                self.assertTrue(all(carried[i] is owners[i] for i in ids))
                missing=dict(owners);missing.pop(ids[0])
                with self.assertRaises(planner.PlanningError):engine.recursive_captures(evidence,set(ids),{},missing,{})
                foreign=dict(owners);foreign[ids[0]]=planner.Reference('bad',('nominal',typ[1],typ[2],('foreign',)))
                with self.assertRaises(planner.PlanningError):engine.recursive_captures(evidence,set(ids),{},foreign,{})
                scheme=dict(owners);scheme[ids[0]]=planner.SchemeReference('bad',0)
                with self.assertRaises(planner.PlanningError):engine.recursive_captures(evidence,set(ids),{},scheme,{})

    def test_nominal_owners_keep_sum_factory_32_external_limit(self):
        # The recursive carrier permits 64, but this Cons arm has one self
        # capture in addition to its ordinary nominal captures. Its separate
        # factory external limit is still 32, not the carrier's larger bound.
        for count in (31,32):
            raw=c.fixture(scalar=False,view=False)
            raw['declarations'].append(f.declaration('Box','BoxValue',f.I))
            bodies=[f.data_case(f.var(200+i),'BoxValue',[600+i],f.var(600+i)) for i in range(count)]
            contribution(raw)['argument']=sums.balanced(bodies)
            body=raw['body']['body']
            for i in reversed(range(count)):
                body=f.let(200+i,f.construct('BoxValue',f.lit(1)),body)
            raw['body']['body']=body
            fragment=transport.derive_shared_fragment(raw)
            self.assertEqual(len(fragment['recursion']['bindings'][0]['captures']['nominals']),count)
            if count==32:
                with self.assertRaisesRegex(planner.PlanningError,'external capture count exceeds32'):
                    planner.plan_fragment(raw,fragment=fragment)
            else:
                result=checked(self,raw)
                row,=result['binding']['source_map']['sum_case_map']
                factory=instruction(result['program'],row['factory'])
                arm=factory['arms']['V1']['captures']
                self.assertEqual(sum(r['kind']=='external' for r in arm.values()),32)

    def test_resource_checker_rejects_wrong_family_and_support(self):
        result=checked(self,fixture());_,carrier,_=c.target(result)
        capture,=[r for r in carrier['mono_captures'] if r['binder']==30]
        for kind in ('type','support'):
            bad=copy.deepcopy(result['program']);contract=bad['functions'][carrier['ir_code']]['captures'][capture['capture']]
            if kind=='type':
                family=next(iter(bad['families']));contract['layout']='%'+family
            else:contract['relation']='below'
            with self.assertRaises(ResourceError):check_resources(bad)
            with self.assertRaises(ResourceError):check_metadata(bad)


CAPTURE_ROOT=os.environ.get('IR8_NOMINAL_CAPTURES_ROOT')
PRIOR_ROOT=os.environ.get('IR8_CALLABLE_CAPTURES_ROOT')


class RetainedNominalCaptureTests(unittest.TestCase):
    @unittest.skipUnless(CAPTURE_ROOT,'set IR8_NOMINAL_CAPTURES_ROOT for retained genuine captures')
    def test_both_actual_captures_replay_check_emit_in_both_modes(self):
        from source_capture_v8 import verify_capture
        root=Path(CAPTURE_ROOT)
        for label,(capture_sha,source_sha) in PINS.items():
            path=root/('capture-'+label+'01')/'capture.stdout'
            verified=verify_capture(path,fixture_root=root/'inputs'/label,entry='main.emlf',
                expected_capture_sha256=capture_sha,expected_source_hashes={'main.emlf':source_sha,'SharedPoly.emlf':SHARED_SHA})
            self.assertTrue(verified['fragment_admitted'])
            self.assertFalse(verified['source_admitted']);self.assertFalse(verified['native_admitted'])
            capture=json.loads(path.read_bytes());raw=capture['projection']['projected_annotated']
            fragment=transport.derive_shared_fragment(raw)
            self.assertEqual(fragment['steps'],capture['normalization']['steps'])
            self.assertEqual(fragment['raw_normalized'],capture['normalization']['raw_normalized'])
            evidence,=fragment['recursion']['bindings'];nominal,=evidence['captures']['nominals']
            self.assertEqual(evidence['captures']['callables'],[])
            self.assertEqual(evidence['captures']['scalars'],[])
            self.assertEqual(len(evidence['captures']['views']),int(label=='sum-owner'))
            for groups in (False,True):
                result=planner.plan_fragment(raw,fragment=fragment,data_groups=groups)
                knot,carrier,closure=c.target(result)
                self.assertEqual(knot['captures'],evidence['captures'])
                self.assertEqual(len(carrier['view_captures']),int(label=='sum-owner'))
                row,=[r for r in carrier['mono_captures'] if r['binder']==nominal['binding']['id']]
                owner=a.allocation_for_binder(result,fragment['raw_normalized'],nominal['binding']['id'])
                self.assertEqual(owner['op'],'application')
                self.assertEqual(closure['captures'][row['capture']],owner['out'])
                typ=result['program']['types'][row['layout'][1:]]
                maps=result['binding']['source_map']['nominal_map'] if label=='data-owner' else result['binding']['source_map']['sum_map']
                declaration,=[r for r in maps if r['declaration']==nominal['declaration']]
                self.assertEqual(typ['layout'],declaration['layout'] if label=='data-owner' else '%'+declaration['family'])
                check_resources(result['program'])
                self.assertEqual(json.loads(emit_runtime(result['program']).canonical_ir_json),result['program'])

    @unittest.skipUnless(PRIOR_ROOT,'set IR8_CALLABLE_CAPTURES_ROOT for frozen Stage16 goldens')
    def test_old_callable_plans_and_all_generated_files_byte_exact(self):
        root=Path(PRIOR_ROOT)
        pins={'pending-step':'8d6452d60f503b6e685f4abd48ca8967489a25135ec75d0e681e719199e7a5df',
              'view-alias':'feb1656e2b397be0fed3eba1f40ba95785eb1029a8aab6fdb5aa164fefa01668'}
        for label,sha in pins.items():
            data=(root/('capture-'+label+'01')/'capture.stdout').read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),sha)
            raw=json.loads(data)['projection']['projected_annotated']
            for mode in ('coarse','groups'):
                directory=root/'host-plan01'/label/mode;prior=json.loads((directory/'planned.json').read_bytes())
                current=planner.plan_fragment(raw,data_groups=mode=='groups')
                self.assertEqual(current,prior);self.assertEqual(a.canonical(current),a.canonical(prior))
                caps=current['binding']['source_map']['knot_map'][0]['captures']
                self.assertEqual(caps['policy'],'closed-scalar-callable-shared-view-captures/1')
                self.assertNotIn('nominals',caps)
                emission=emit_runtime(current['program'])
                for filename,field in (('ir8_runtime_generated.h','runtime_header'),('ir8_runtime_generated.c','runtime_source'),
                                       ('ir8_packet_generated.h','packet_header'),('ir8_packet_generated.c','packet_source')):
                    self.assertEqual(getattr(emission,field).encode(),(directory/filename).read_bytes(),filename)


if __name__=='__main__':unittest.main()
