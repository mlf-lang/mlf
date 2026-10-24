#!/usr/bin/env python3
"""Python-only state-law runner fault controls; no compiler/runtime invocation."""
import copy
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
    def test_mutation_addition_deletion_and_fixed_tool(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for relative in ['libraries','tests','tools/shared/fixtures']:(root/relative).mkdir(parents=True)
            source=root/'tests/M.emlf';source.write_text('original')
            tool=root/'tool.py';tool.write_text('fixed')
            before=gate.capture_inputs(root,[tool])
            gate.unchanged(before,gate.capture_inputs(root,[tool]))
            source.write_text('changed')
            with self.assertRaises(ValueError):gate.unchanged(before,gate.capture_inputs(root,[tool]))
            source.write_text('original');added=root/'libraries/Other.hs';added.write_text('new')
            with self.assertRaises(ValueError):gate.unchanged(before,gate.capture_inputs(root,[tool]))
            added.unlink();source.unlink()
            with self.assertRaises(ValueError):gate.unchanged(before,gate.capture_inputs(root,[tool]))
            source.write_text('original');tool.write_text('changed')
            with self.assertRaises(ValueError):gate.unchanged(before,gate.capture_inputs(root,[tool]))
    def test_directory_alias_retarget_addition_and_cycle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for relative in ['libraries','tests','tools/shared/fixtures','actual/One','actual/Two']:
                (root/relative).mkdir(parents=True)
            (root/'actual/One/M.emlf').write_text('first')
            (root/'actual/Two/M.emlf').write_text('first')
            alias=root/'tests/Tests';alias.symlink_to(root/'actual/One',target_is_directory=True)
            before=gate.capture_inputs(root,[])
            self.assertIn(str(alias),before)
            self.assertIn(str(root/'actual/One/M.emlf'),before)
            self.assertEqual(before[str(alias)]['kind'],'directory-symlink')
            (root/'actual/One/M.emlf').write_text('changed')
            with self.assertRaises(ValueError):gate.unchanged(before,gate.capture_inputs(root,[]))
            (root/'actual/One/M.emlf').write_text('first')
            alias.unlink();alias.symlink_to(root/'actual/Two',target_is_directory=True)
            with self.assertRaises(ValueError):gate.unchanged(before,gate.capture_inputs(root,[]))
            alias.unlink();alias.symlink_to(root/'actual/One',target_is_directory=True)
            (root/'tests/shared-host').mkdir()
            extra=root/'tests/shared-host/invalid-target-link';extra.symlink_to(root/'actual/One',target_is_directory=True)
            with self.assertRaises(ValueError):gate.unchanged(before,gate.capture_inputs(root,[]))
            # A link to an ancestor is recorded, then resolved-dir dedup stops recursion.
            loop=root/'actual/One/Again';loop.symlink_to(root/'actual/One',target_is_directory=True)
            captured=gate.capture_inputs(root,[])
            self.assertTrue(any(row.get('target')==str(root/'actual/One') for row in captured.values()))
            files=[row for row in captured.values() if row.get('kind')=='file']
            self.assertEqual(len(files),1)
            self.assertIn(str(extra),captured)
    def test_directory_alias_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root=Path(temporary)
            for relative in ['libraries','tests','tools/shared/fixtures']:(root/relative).mkdir(parents=True)
            (root/'tests/Tests').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):gate.capture_inputs(root,[])
    def test_broken_and_self_referential_links_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for relative in ['libraries','tests','tools/shared/fixtures']:(root/relative).mkdir(parents=True)
            alias=root/'tests/Tests';alias.symlink_to(root/'missing',target_is_directory=True)
            with self.assertRaises(FileNotFoundError):gate.capture_inputs(root,[])
            alias.unlink();alias.symlink_to(alias,target_is_directory=True)
            with self.assertRaises((RuntimeError,OSError)):gate.capture_inputs(root,[])
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
