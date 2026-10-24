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
        self.assertNotIn('MLF.Primitive', gate.LEGACY)
        self.assertEqual(gate.STANDARD.split('main :')[1], gate.LEGACY.split('main :')[1])
    def test_success_receipt(self):
        gate.verify_run({'complete':True,'exit_code':0,'reason':None},0,'')
    def test_expected_rejection(self):
        gate.verify_run({'complete':False,'exit_code':1,'reason':None},1,
                        'Resolution: no instance or given constraint for Monad (Bootstrap.Types.Either String)')
    def test_resource_failure_not_rejection(self):
        for receipt in [dict(complete=False,exit_code=1,reason='wall-time limit'),
                        dict(complete=False,exit_code=-9,reason=None),
                        dict(complete=True,exit_code=1,reason=None),
                        dict(complete=False,exit_code=0,reason=None)]:
            with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                gate.verify_run(receipt,1,'Resolution: no instance or given constraint for Monad (Bootstrap.Types.Either String)')
    def test_wrong_phase_or_reason_rejected(self):
        for message in ['Parsing: no instance or given constraint for Monad (Bootstrap.Types.Either String)',
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
                self.assertEqual(gate.manifest_inputs(manifest,'fixture',1,{})[1], [('M',root/'M.hs')])
                for name,count,deps in [('wrong',1,{}),('fixture',2,{}),('fixture',1,{'dep':'../dep'})]:
                    with self.assertRaises(ValueError):gate.manifest_inputs(manifest,name,count,deps)
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
