#!/usr/bin/env python3
"""Python-only fail-closed controls; never invoke an MLF compiler."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_guest_framework as gate

class GateControls(unittest.TestCase):
    def test_pack(self):
        self.assertEqual(gate.pack(['a', 'λ', '']), '1:a1:λ0:')
    def test_standard_boundary_is_explicit(self):
        self.assertIn('import Prelude hiding (Monad, return, bind)', gate.STANDARD)
        self.assertIn('import MLF.Primitive (Monad, return, bind)', gate.STANDARD)
        self.assertNotIn('MLF.Primitive', gate.IMPLICIT)
        self.assertEqual(gate.STANDARD.split('main :')[1], gate.IMPLICIT.split('main :')[1])
    def test_distinct_class_control_is_nominal(self):
        self.assertIn('class Monad (m : * -> *)', gate.DISTINCT)
        self.assertIn('instance Monad Box', gate.DISTINCT)
        self.assertIn('main = do { x <- Box 1; Box x }', gate.DISTINCT)
        self.assertIn('import Prelude hiding (Monad, return, bind)', gate.DISTINCT)
    def test_extra_error_text_cannot_satisfy_negative(self):
        for text in [gate.NEGATIVE_DIAGNOSTIC+'\nParsing: unrelated failure',
                     'ModuleResolution: ambiguous name Monad',
                     'Resolution: no instance or given constraint for Monad (Bootstrap.Types.Either String)']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                gate.verify_run(dict(complete=False,exit_code=1,reason=None),1,text)
    def test_success_receipt(self):
        gate.verify_run({'complete':True,'exit_code':0,'reason':None},0,'')
    def test_expected_rejection(self):
        gate.verify_run({'complete':False,'exit_code':1,'reason':None},1,
                        gate.NEGATIVE_DIAGNOSTIC)
    def test_resource_failure_not_rejection(self):
        for receipt in [dict(complete=False,exit_code=1,reason='wall-time limit'),
                        dict(complete=False,exit_code=-9,reason=None),
                        dict(complete=True,exit_code=1,reason=None),
                        dict(complete=False,exit_code=0,reason=None)]:
            with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                gate.verify_run(receipt,1,gate.NEGATIVE_DIAGNOSTIC)
    def test_wrong_phase_or_reason_rejected(self):
        for message in ['Parsing: no instance or given constraint for MLF.Primitive.Monad Distinct.Box',
                        'Resolution: source missing', '']:
            with self.subTest(message=message), self.assertRaises(ValueError):
                gate.verify_run(dict(complete=False,exit_code=1,reason=None),1,message)
    def test_repeated_input_registration_cannot_mask_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'interface';path.write_text('original')
            recorded={};gate.remember_file(recorded,path);gate.remember_file(recorded,path)
            original=dict(recorded);path.write_text('changed')
            with self.assertRaises(ValueError):gate.remember_file(recorded,path)
            self.assertEqual(recorded,original)
    def test_manifest_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'M.hs').write_text('module M where {}')
            manifest=root/'mlf-package.json'
            value={'format':1,'name':'fixture','version':'1','dependencies':{},'library':{'modules':{'M':'M.hs'}}}
            manifest.write_text(json.dumps(value))
            with patch.object(gate,'ROOT',root):
                self.assertEqual(gate.manifest_inputs(manifest,'fixture',{'M':'M.hs'},{})[1], [('M',root/'M.hs')])
                for name,modules,deps in [('wrong',{'M':'M.hs'},{}),
                                          ('fixture',{'M':'M.hs','N':'N.hs'},{}),
                                          ('fixture',{'M':'M.hs'},{'dep':'../dep'})]:
                    with self.assertRaises(ValueError):gate.manifest_inputs(manifest,name,modules,deps)
    def test_reviewed_repository_inventory(self):
        original = {'Fresh', 'Host', 'IntMap', 'IntSet', 'Map', 'Regex', 'ST',
                    'Set', 'Std', 'Types', 'Unicode', 'Version'}
        self.assertEqual(gate.FOUNDATION_MODULES,
                         {'Bootstrap.'+name: 'Bootstrap/'+name+'.hs'
                          for name in original | {'IntTree', 'IntRank'}})
        foundation = gate.ROOT/'libraries/mlf-foundation/mlf-package.json'
        framework = gate.ROOT/'testing/mlf-package.json'
        self.assertEqual(len(gate.manifest_inputs(foundation,'mlf-foundation',
                         gate.FOUNDATION_MODULES,{})[1]),14)
        modules = gate.manifest_inputs(framework,'mlf-test',gate.FRAMEWORK_MODULES,
                                      {'mlf-foundation':'../libraries/mlf-foundation'})[1]
        self.assertEqual(len(modules),14)
        self.assertEqual(sum(p.suffix=='.hs' for _,p in modules),7)
        self.assertEqual(sum(p.suffix=='.emlf' for _,p in modules),7)
    def test_equal_size_module_replacement_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ['M.hs','N.hs','M.emlf']:(root/name).write_text('module M where {}')
            manifest=root/'mlf-package.json'
            for modules in [{'N':'M.hs'},{'M':'N.hs'},{'M':'M.emlf'}]:
                manifest.write_text(json.dumps({'format':1,'name':'fixture',
                                                'library':{'modules':modules}}))
                with patch.object(gate,'ROOT',root), self.subTest(modules=modules), self.assertRaises(ValueError):
                    gate.manifest_inputs(manifest,'fixture',{'M':'M.hs'},{})
    def test_missing_and_extra_modules_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);manifest=root/'mlf-package.json'
            for name in ['M.hs','N.hs']:(root/name).write_text('module M where {}')
            for modules in [{},{'M':'M.hs','N':'N.hs'}]:
                manifest.write_text(json.dumps({'format':1,'name':'fixture',
                                                'library':{'modules':modules}}))
                with patch.object(gate,'ROOT',root), self.subTest(modules=modules), self.assertRaises(ValueError):
                    gate.manifest_inputs(manifest,'fixture',{'M':'M.hs'},{})
    def test_exact_dependency_route_is_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'M.hs').write_text('module M where {}')
            manifest=root/'mlf-package.json'
            for deps in [{'dep':{'path':'../wrong'}},
                         {'dep':{'path':'../dep'},'extra':{'path':'../extra'}}]:
                manifest.write_text(json.dumps({'format':1,'name':'fixture',
                              'dependencies':deps,'library':{'modules':{'M':'M.hs'}}}))
                with patch.object(gate,'ROOT',root), self.subTest(deps=deps), self.assertRaises(ValueError):
                    gate.manifest_inputs(manifest,'fixture',{'M':'M.hs'},{'dep':'../dep'})
    def test_watchdog_success_and_error(self):
        for status in [0,1]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                command=[sys.executable,str(gate.WATCHDOG),'--seconds','5','--address-space-mib','256',
                         '--rss-mib','128',temporary,sys.executable,'-c','raise SystemExit('+str(status)+')']
                result=subprocess.run(command,capture_output=True)
                receipt=json.loads((Path(temporary)/'bounded-receipt.json').read_text())
                self.assertEqual(result.returncode,status)
                self.assertEqual(receipt['exit_code'],status)
                self.assertEqual(receipt['complete'],status==0)
                self.assertIsNone(receipt['reason'])
    def test_watchdog_final_output_floor(self):
        with tempfile.TemporaryDirectory() as temporary:
            command=[sys.executable,str(gate.WATCHDOG),'--seconds','5','--address-space-mib','256',
                     '--rss-mib','128','--max-output-mib','1',temporary,sys.executable,'-c',
                     'from pathlib import Path; Path('+repr(temporary+'/big')+').write_bytes(b"x"*2097152)']
            result=subprocess.run(command,capture_output=True)
            receipt=json.loads((Path(temporary)/'bounded-receipt.json').read_text())
            self.assertEqual(result.returncode,1)
            self.assertFalse(receipt['complete'])
            self.assertIn('output growth limit',receipt['reason'])

if __name__=='__main__':unittest.main()
