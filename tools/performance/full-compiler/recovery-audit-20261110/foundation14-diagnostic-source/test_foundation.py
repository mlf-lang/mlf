import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
D=module('diagnostic','run_diagnostic.py');P=module('planner','prepare_plan.py')
PLAN=json.loads((HERE/'producer-plan.json').read_text())

class Foundation(unittest.TestCase):
    def test_exact_new_plan(self):
        D.foundation_target(PLAN)
        a,b=[PLAN['spec_recipes'][label]['fields'] for label in ['ordinary-Q','diagnostic-D']]
        self.assertEqual([i for i,(x,y) in enumerate(zip(a,b)) if x!=y],[6])
        self.assertEqual(a[1],'fresh-split/compiler90/mlf-foundation')
        self.assertEqual(a[5],P.pack([PLAN['builtin_prefix']+'.mlfci']))
        self.assertIn('baseline-gc-foundation14-cohort-02',PLAN['workspace'])
    def test_inference_target_rejected(self):
        p=copy.deepcopy(PLAN);p['slices'][0]['identity']='fresh-split/compiler90/mlf-inference'
        with self.assertRaises(ValueError):D.foundation_target(p)
    def test_unexpected_dependency_rejected(self):
        p=copy.deepcopy(PLAN);p['slices'][0]['dependencies']=['mlf-frontend']
        with self.assertRaises(ValueError):D.foundation_target(p)
    def test_wrong_source_bytes_rejected(self):
        p=copy.deepcopy(PLAN);p['slices'][0]['modules'][0]['bytes']-=1
        with self.assertRaises(ValueError):D.foundation_target(p)
    def test_duplicate_module_rejected(self):
        p=copy.deepcopy(PLAN);p['slices'][0]['modules'][1]['module']=p['slices'][0]['modules'][0]['module']
        with self.assertRaises(ValueError):D.foundation_target(p)
    def test_wrong_source_hash_rejected(self):
        w=copy.deepcopy(PLAN['full_source_closure'])
        selected=PLAN['slices'][0]['modules'][0]['module']
        next(row for row in w['modules'] if row['module']==selected)['sha256']='0'*64
        with patch.object(P,'module',return_value=SimpleNamespace(freeze=lambda *args:w)):
            with self.assertRaisesRegex(ValueError,'source hashes'):
                P.source_plan(Path(PLAN['source']),Path(PLAN['workspace']))

class Fresh(unittest.TestCase):
    def setUp(self):
        self.r=dict(format=1,crate='fresh-split/compiler90/mlf-foundation',inferred_groups=475,
                    reused_groups=0,groups=[dict(id=str(i),cached=False) for i in range(475)])
    def test_all475(self):D.foundation_fresh(self.r)
    def test780_rejected(self):
        self.r['inferred_groups']=780
        with self.assertRaises(ValueError):D.foundation_fresh(self.r)
    def test_cached_rejected(self):
        self.r['groups'][1]['cached']=True
        with self.assertRaises(ValueError):D.foundation_fresh(self.r)
    def test_reused_rejected(self):
        self.r['reused_groups']=1
        with self.assertRaises(ValueError):D.foundation_fresh(self.r)
    def test_duplicate_rejected(self):
        self.r['groups'][1]['id']='0'
        with self.assertRaises(ValueError):D.foundation_fresh(self.r)
    def test_inference_identity_rejected(self):
        self.r['crate']='fresh-split/compiler90/mlf-inference'
        with self.assertRaises(ValueError):D.foundation_fresh(self.r)

class Builtin(unittest.TestCase):
    def setUp(self):
        self.w=Path(PLAN['workspace']);self.b=self.w/'thin-setup/builtin'
        self.r=dict(complete=True,identity=P.BUILTIN,prefix=str(self.b),fresh_groups=1,reused_groups=0,
                    query_lock_reacquired=True,interface_checked=True,
                    fixture_prefix=str(self.w/'thin-setup/builtin-work/fixture'),
                    fixture_spec=str(self.w/'thin-setup/builtin-work/fixture.spec'),
                    fixture=str(self.w/'thin-setup/builtin-work/Fixture.emlf'))
    def test_complete(self):D.fixed_builtin_contract(self.r,self.w,self.b)
    def test_incomplete_rejected(self):
        self.r['complete']=False
        with self.assertRaises(ValueError):D.fixed_builtin_contract(self.r,self.w,self.b)
    def test_old_partial_prefix_rejected(self):
        self.r['prefix']='/old-failed/dependencies/builtin'
        with self.assertRaises(ValueError):D.fixed_builtin_contract(self.r,self.w,self.b)
    def test_missing_interface_check_rejected(self):
        self.r['interface_checked']=False
        with self.assertRaises(ValueError):D.fixed_builtin_contract(self.r,self.w,self.b)

if __name__=='__main__':unittest.main()
