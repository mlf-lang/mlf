#!/usr/bin/env python3
"""Python-only state-law runner fault controls; no compiler/runtime invocation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import test_guest_state_laws as gate


def receipt(status=0):
    return {'complete': status == 0, 'exit_code': status, 'reason': None,
            'limits': dict(gate.LIMITS), 'elapsed_seconds': 1.0, 'peak_group_rss': 100,
            'samples': [{'host_available': 4*1024**3, 'disk_free': 4*1024**3,
                         'group_rss': 100, 'output_bytes': 100}]}

class StateLawControls(unittest.TestCase):
    def test_exact_positive_and_negative(self):
        for _, _, _, _, positive, negative in gate.CASES:
            gate.verify_observation(receipt(), 0, positive, positive)
            gate.verify_observation(receipt(1), 1, negative, negative)
    def test_false_successes_rejected(self):
        expected = gate.CASES[0][-1]
        mutations = [dict(exit_code=0), dict(exit_code=-9), dict(exit_code=True),
                     dict(complete=True), dict(reason='wall-time limit'), dict(samples=[]),
                     dict(elapsed_seconds=90), dict(peak_group_rss=2*1024**3)]
        for mutation in mutations:
            resource = receipt(1);resource.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                gate.verify_observation(resource,1,expected,expected)
    def test_incomplete_schema(self):
        for field in ['reason','exit_code','complete','limits','elapsed_seconds','peak_group_rss','samples']:
            resource=receipt();resource.pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                gate.verify_observation(resource,0,b'PASS\n',b'PASS\n')
    def test_changed_limits_and_samples(self):
        for field in gate.LIMITS:
            resource=receipt();resource['limits'][field]+=1
            with self.subTest(field=field), self.assertRaises(ValueError):
                gate.verify_observation(resource,0,b'PASS\n',b'PASS\n')
        for field,value in [('host_available',1),('disk_free',1),('group_rss',2*1024**3),('output_bytes',101*1024**2)]:
            resource=receipt();resource['samples'][0][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                gate.verify_observation(resource,0,b'PASS\n',b'PASS\n')
    def test_exact_output_and_no_pass_on_failure(self):
        expected=gate.CASES[0][-1]
        for actual in [b'',expected+b'PASS\n',b'FAIL other\n',expected.rstrip(),b'PASS\n']:
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                gate.verify_observation(receipt(1),1,actual,expected)
        with self.assertRaises(ValueError):gate.verify_observation(receipt(1),1,b'PASS\n',b'PASS\n')
    def test_fixture_roots_and_environment_contract(self):
        self.assertEqual(gate.CASES[0][3],('libraries/mlf-foundation','libraries/mlf-language-core','libraries/mlf-inference','tests'))
        self.assertEqual(gate.CASES[1][3],('libraries/mlf-foundation','tests'))
        self.assertEqual(set(gate.FLAGS),{case[2] for case in gate.CASES})
    @unittest.skipUnless(sys.platform == 'linux', 'the live resource watchdog uses Linux procfs and ionice')
    def test_watchdog_default_and_stricter_disk_floor(self):
        for options, expected in [([],768),(['--disk-free-mib','3072'],3072)]:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temporary:
                command=[sys.executable,str(gate.WATCHDOG),'--seconds','5','--address-space-mib','256',
                         '--rss-mib','128',*options,temporary,sys.executable,'-c','pass']
                result=subprocess.run(command,capture_output=True)
                resource=json.loads((Path(temporary)/'bounded-receipt.json').read_text())
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(resource['limits']['disk_free_floor'],expected*1024**2)
    def test_nonpositive_disk_floor_rejected(self):
        for value in ['0','-1']:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temporary:
                result=subprocess.run([sys.executable,str(gate.WATCHDOG),'--disk-free-mib',value,
                                       temporary,sys.executable,'-c','pass'],capture_output=True)
                self.assertEqual(result.returncode,2)
                self.assertFalse((Path(temporary)/'bounded-receipt.json').exists())

if __name__ == '__main__':unittest.main()
