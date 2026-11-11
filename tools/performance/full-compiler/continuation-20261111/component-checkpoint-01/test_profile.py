import copy
import json
import unittest
from profile import ProfileError, parse_profile, qualify_units


def cc(i, label, module='Test', caf=False):
    return dict(id=i, label=label, module=module, src_loc='Test.hs:1', is_caf=caf)


def node(i, alloc=0, ticks=0, children=None):
    return dict(id=i, entries=1, alloc=alloc, ticks=ticks, children=children or [])


def fixture():
    return dict(program='toy', arguments=['toy'], rts_arguments=['-pj'], end_time='now', initial_capabilities=1,
                total_time=0.01, total_ticks=3, tick_interval=10000, total_alloc=100,
                cost_centres=[cc(1,'MAIN','RTS'),cc(2,'CLOSED_CHECK'),cc(3,'INVENTORY'),cc(4,'STAMP'),cc(5,'ENCODE')],
                profile=node(1,10,0,[node(2,20,1,[node(3,30,1)]),node(5,10,0,[node(4,30,1)])]))


class ProfileTests(unittest.TestCase):
    def test_disjoint_and_inherited(self):
        result=parse_profile(json.dumps(fixture()))
        self.assertEqual(sum(x['alloc'] for x in result['partition'].values()),100)
        self.assertEqual(result['partition']['INVENTORY/CLOSED_CHECK']['alloc'],30)
        self.assertEqual(result['partition']['ENCODE']['alloc'],10)
        self.assertEqual(result['partition']['STAMP']['alloc'],30)
        self.assertEqual(result['stacks'][0]['inherited_alloc'],100)
        self.assertGreater(sum(x['inherited_alloc'] for x in result['stacks']),100)
        self.assertIn('pending',result['unit'])

    def reject(self, mutation):
        data=fixture(); mutation(data)
        with self.assertRaises(ProfileError): parse_profile(data)

    def test_negative_alloc(self): self.reject(lambda d:d['profile'].update(alloc=-1))
    def test_float_ticks(self): self.reject(lambda d:d['profile'].update(ticks=0.0))
    def test_bool_alloc(self): self.reject(lambda d:d['profile'].update(alloc=True))
    def test_negative_entries(self): self.reject(lambda d:d['profile'].update(entries=-1))
    def test_missing_profile(self): self.reject(lambda d:d.pop('profile'))
    def test_unknown_schema(self): self.reject(lambda d:d.update(version=2))
    def test_unknown_node_field(self): self.reject(lambda d:d['profile'].update(inherited_alloc=100))
    def test_duplicate_cc(self): self.reject(lambda d:d['cost_centres'].append(d['cost_centres'][0]))
    def test_unknown_reference(self): self.reject(lambda d:d['profile'].update(id=999))
    def test_total_alloc(self): self.reject(lambda d:d.update(total_alloc=101))
    def test_total_ticks(self): self.reject(lambda d:d.update(total_ticks=4))
    def test_nonfinite_time(self): self.reject(lambda d:d.update(total_time=float('nan')))
    def test_bad_cc_caf(self): self.reject(lambda d:d['cost_centres'][0].update(is_caf=1))
    def test_bad_children(self): self.reject(lambda d:d['profile'].update(children=[0]))
    def test_bad_id(self): self.reject(lambda d:d['profile'].update(id=True))
    def test_cycle(self): self.reject(lambda d:d['profile']['children'].append(d['profile']))
    def test_cc_path_cycle(self): self.reject(lambda d:d['profile']['children'][0].update(id=1))
    def test_duplicate_sibling(self): self.reject(lambda d:d['profile']['children'].append(copy.deepcopy(d['profile']['children'][0])))
    def test_shared_node(self): self.reject(lambda d:d['profile']['children'][1]['children'].append(d['profile']['children'][0]['children'][0]))
    def test_repeated_reference_separate_branches_allowed(self):
        data=fixture();data['profile']['children'][1]['children'][0]['id']=3
        result=parse_profile(data)
        self.assertEqual(result['partition']['INVENTORY/UNRESOLVED']['alloc'],30)
    def test_open_context(self):
        for context in ('OPEN_INITIAL','OPEN_NORMALIZE'):
            data=fixture();data['cost_centres'][1]['label']=context
            self.assertEqual(parse_profile(data)['partition']['INVENTORY/'+context]['alloc'],30)
    def test_caf_and_unknown_residual(self):
        data=fixture();data['cost_centres'][3].update(label='CAF',is_caf=True)
        data['cost_centres'][4]['label']='other'
        result=parse_profile(data)
        self.assertEqual(result['partition']['RESIDUAL/CAF']['alloc'],30)
        self.assertEqual(result['partition']['RESIDUAL/UNKNOWN']['alloc'],10)
    def test_duplicate_json_key(self):
        raw=json.dumps(fixture()).replace('"alloc": 10','"alloc": 10, "alloc": 10',1)
        with self.assertRaises(ProfileError):parse_profile(raw)
    def test_truncated_json(self):
        with self.assertRaises(ProfileError):parse_profile(json.dumps(fixture())[:-2])
    def test_limits(self):
        for limits in (dict(max_nodes=1),dict(max_depth=0),dict(max_bytes=5)):
            with self.assertRaises(ProfileError):parse_profile(json.dumps(fixture()),**limits)
    def test_units_evidence(self):
        summary=parse_profile(fixture())
        evidence=dict(toolchain_sha256='a'*64,installed_rts_definition_sha256='b'*64,control_receipt_sha256='c'*64,
                      writer_alloc_unit='bytes',control_expected_bytes=800,control_observed_raw=800,control_passed=True)
        qualified=qualify_units(summary,evidence,toolchain_sha256='a'*64)
        self.assertEqual(qualified['unit'],'bytes')
        self.assertEqual(qualified['total_alloc'],100)
        for key,value in [('control_passed',False),('control_observed_raw',100),('writer_alloc_unit','words'),('installed_rts_definition_sha256',''),('toolchain_sha256','d'*64)]:
            broken=dict(evidence);broken[key]=value
            with self.assertRaises(ProfileError):qualify_units(summary,broken,toolchain_sha256='a'*64)

if __name__=='__main__':unittest.main()
