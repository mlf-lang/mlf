"""Pure refusal and linkage tests; no GHC/emlf or complete native suite runs."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import qualify_header_only as Q

class QualificationTests(unittest.TestCase):
    def producer(self):
        return {'complete':True,'typecheck_only':False,'producer_host':'GHC',
                'implementation_identity':'MLF/shared-haskell-v1 GHC',
                'optimization':'0','ghc':{'version':'9.14.1','path':'/fixed/ghc'},
                'cc':{'path':'/fixed/cc'},'object_inputs':{'objects/A.o':'a'*64}}

    def test_exact_producer(self):
        Q.producer_contract(self.producer())

    def test_wrong_optimization_and_producer(self):
        variants = [('optimization','2'),('optimization',0),('complete',False),
                    ('typecheck_only',True),('producer_host','MLF'),
                    ('implementation_identity','other'),('object_inputs',{})]
        for field,value in variants:
            producer=self.producer();producer[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                Q.producer_contract(producer)
        producer=self.producer();producer['ghc']['version']='9.12.1'
        with self.assertRaises(ValueError):Q.producer_contract(producer)

    def test_plan_exact_inventory_flags_and_tail(self):
        root,build,out=Path('/source'),Path('/producer'),Path('/output')
        plan=Q.command_plan(root,build,out,self.producer(),[build/'objects/A.o'])
        self.assertEqual([name for name,argv,expected in plan],[
            'compile-host','compile-supervisor','compile-HistoricalHeaderNames',
            'compile-HeaderNamingOracle','compile-HeaderValidationHistorical',
            'link-HeaderValidationHistorical','compile-HeaderValidationCurrent',
            'link-HeaderValidationCurrent','header-validation-historical','header-validation-current'])
        self.assertEqual(plan[-2][1],['/output/HeaderValidationHistorical'])
        self.assertEqual(plan[-1][1],['/output/HeaderValidationCurrent'])
        banner=b'PASS header duplicate errors, entity identity, Unicode naming and forged primitive rejection\n'
        self.assertEqual(plan[-2][2],banner)
        self.assertEqual(plan[-1][2],banner)
        for name,argv,expected in plan[2:8]:
            self.assertIn('-O0',argv)
            self.assertIn('-fpedantic-bottoms',argv)
            self.assertIn('-fno-state-hack',argv)
            self.assertNotIn('-O2',argv)
            self.assertEqual(argv[0],'/fixed/ghc')
        self.assertEqual(plan[0][1][0],'/fixed/cc')
        self.assertEqual(plan[1][1][0],'/fixed/cc')
        for index in [5,7]:
            argv=plan[index][1]
            self.assertIn('/producer/objects/A.o',argv)
            self.assertIn('/output/header-validation/HistoricalHeaderNames.o',argv)
            self.assertIn('/output/header-validation/HeaderNamingOracle.o',argv)
            self.assertIn('/output/host.o',argv)
            self.assertIn('/output/supervisor.o',argv)

    def ledger(self,output):
        root=Path('/source')
        plan=Q.command_plan(root,Path('/producer'),output,self.producer(),[Path('/producer/objects/A.o')])
        commands=[]
        for name,argv,expected in plan:
            stdout=b'' if expected is None else expected
            stderr=b''
            (output/(name+'.stdout')).write_bytes(stdout)
            (output/(name+'.stderr')).write_bytes(stderr)
            commands.append({'name':name,'argv':argv,'cwd':str(root),
                'timeout_seconds':120,'environment_overrides':{},'state':'passed','exit_code':0,
                'stdout_sha256':hashlib.sha256(stdout).hexdigest(),
                'stderr_sha256':hashlib.sha256(stderr).hexdigest()})
        return {'commands':commands},plan,root

    def test_capture_ledger_positive(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            record,plan,root=self.ledger(output)
            self.assertEqual(len(Q.verify_commands(record,plan,output,root)),20)

    def test_missing_or_fabricated_lane_and_command(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            record,plan,root=self.ledger(output)
            mutations=[]
            missing=copy.deepcopy(record);missing['commands'].pop();mutations.append(missing)
            duplicate=copy.deepcopy(record);duplicate['commands'][-1]=copy.deepcopy(duplicate['commands'][-2]);mutations.append(duplicate)
            for field,value in [('name','header-validation-fake'),('argv',['/old/HeaderValidationCurrent']),
                                ('exit_code',True),('state','running'),('timed_out',True),
                                ('timeout_seconds',121),('environment_overrides',{'FAKE':'1'})]:
                altered=copy.deepcopy(record);altered['commands'][-1][field]=value;mutations.append(altered)
            for value in mutations:
                with self.assertRaises(ValueError):Q.verify_commands(value,plan,output,root)

    def test_wrong_banner_even_with_repaired_capture_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory);record,plan,root=self.ledger(output)
            raw=b'PASS everything\n'
            (output/'header-validation-current.stdout').write_bytes(raw)
            record['commands'][-1]['stdout_sha256']=hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError,'banner'):
                Q.verify_commands(record,plan,output,root)

    def test_capture_hash_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory);record,plan,root=self.ledger(output)
            record['commands'][-1]['stdout_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'capture ledger'):
                Q.verify_commands(record,plan,output,root)

    def test_real_input_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source';path.write_bytes(b'original')
            before=Q.pin([path]);Q.unchanged(before)
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'immutable'):
                Q.unchanged(before)

    def test_real_object_identity_and_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            build=Path(directory);(build/'objects').mkdir()
            path=build/'objects/A.o';path.write_bytes(b'object')
            p=self.producer();p['object_inputs']={'objects/A.o':Q.sha(path)}
            paths,links=Q.object_paths(build,p)
            self.assertEqual(paths,[path]);self.assertEqual(links,[path])
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):Q.object_paths(build,p)
            outside=build.parent/(build.name+'-outside')
            try:
                outside.write_bytes(b'foreign')
                p['object_inputs']={str(outside):Q.sha(outside)}
                with self.assertRaises(ValueError):Q.object_paths(build,p)
            finally:
                outside.unlink(missing_ok=True)

    def generated(self,path):
        fixture,oracle,history=b'fixture',b'oracle',b'full-history'
        body=b'original four bodies'
        module=Q.H.HEADER+body+Q.H.FOOTER
        contents={'HistoricalHeaderNames.hs':module,'HeaderNamingOracle.hs':oracle,
                  'HeaderValidationHistorical.hs':b'history fixture','HeaderValidationCurrent.hs':b'current fixture',
                  'historical-formatter.raw':body,'HeaderValidationTests.original.hs':fixture}
        for name,raw in contents.items():(path/name).write_bytes(raw)
        evidence={'generated':{name:hashlib.sha256(raw).hexdigest() for name,raw in contents.items()},
            'fixture_git_blob':Q.H.FIXTURE_BLOB,'historical_source_git_blob':Q.H.HISTORICAL_BLOB,
            'historical_body_sha256':hashlib.sha256(body).hexdigest(),
            'fixture_inverse_verified':True,'historical_inverse_verified':True,
            'historical_complete_compiler_qualified':False,'qualification_executed':False}
        (path/'adaptation.json').write_text(json.dumps(evidence))
        return fixture,oracle,history,module,body,evidence

    def test_generated_disk_record_and_inverse_linkage(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            fixture,oracle,history,module,body,evidence=self.generated(path)
            with mock.patch.object(Q.H,'historical_module',return_value=(module,body)),mock.patch.object(Q.H,'restore_fixture',return_value=fixture) as restore:
                pins,observed=Q.generated_snapshot(path,fixture,oracle,history)
                self.assertEqual(len(pins),7);self.assertEqual(observed,evidence)
                self.assertEqual(restore.call_args_list,[
                    mock.call(b'history fixture','historical'),mock.call(b'current fixture','current')])

    def test_bad_inverse_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            fixture,oracle,history,module,body,evidence=self.generated(path)
            with mock.patch.object(Q.H,'historical_module',return_value=(module,body)),mock.patch.object(Q.H,'restore_fixture',return_value=b'wrong original'):
                with self.assertRaisesRegex(ValueError,'inverse'):
                    Q.generated_snapshot(path,fixture,oracle,history)

    def test_forged_adaptation_record_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            fixture,oracle,history,module,body,evidence=self.generated(path)
            variants=[]
            for field,value in [('fixture_git_blob','0'*40),('historical_source_git_blob','1'*40),
                                ('historical_body_sha256','0'*64),('qualification_executed',True),
                                ('historical_complete_compiler_qualified',True),('fixture_inverse_verified',1)]:
                row=copy.deepcopy(evidence);row[field]=value;variants.append(row)
            row=copy.deepcopy(evidence);row['generated'].pop('HeaderValidationCurrent.hs');variants.append(row)
            with mock.patch.object(Q.H,'historical_module',return_value=(module,body)),mock.patch.object(Q.H,'restore_fixture',return_value=fixture):
                for row in variants:
                    (path/'adaptation.json').write_text(json.dumps(row))
                    with self.assertRaisesRegex(ValueError,'record chain'):
                        Q.generated_snapshot(path,fixture,oracle,history)

    def test_exact_head_and_tracked_source_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'shared-sources.json').write_text(json.dumps({'modules':[]}))
            for name in ['q.py','tools/shared/verify_prepared_libraries.py']:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'# fixed\n')
            names=['q.py','tools/shared/verify_prepared_libraries.py','shared-sources.json']
            tree=b''.join(b'100644 blob '+Q.H.blob_id((root/name).read_bytes()).encode()+b'\t'+name.encode()+b'\0' for name in names)
            p={'host_inputs':{},'configuration_inputs':{},'builtin_verification_helpers':{}}
            head='1'*40
            def git(_root,*args):
                return (head+'\n').encode() if args[0]=='rev-parse' else tree
            with mock.patch.object(Q,'OWN_INPUTS',['q.py']),mock.patch.object(Q,'git',side_effect=git):
                self.assertEqual(set(Q.source_snapshot(root,p,head)),set(names))
                with self.assertRaisesRegex(ValueError,'HEAD'):Q.source_snapshot(root,p,'2'*40)
                (root/'q.py').write_bytes(b'# changed\n')
                with self.assertRaisesRegex(ValueError,'exact commit'):
                    Q.source_snapshot(root,p,head)

if __name__ == '__main__':
    unittest.main()
