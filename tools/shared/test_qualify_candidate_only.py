"""Pure single-target dispatch and qualification-boundary controls.

No compiler, interpreter, subprocess or full original-direct execution.
"""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

import qualify_candidate_only as Q


class QualificationControls(unittest.TestCase):
    def good_producer(self):
        return dict(
            complete=True,
            typecheck_only=False,
            producer_host="GHC",
            optimization="0",
        )

    def test_requires_actual_o0_executable_producer(self):
        Q.require_o0(self.good_producer())
        for field, wrong_values in {
            "complete": [False, 1, None],
            "typecheck_only": [True, 0, None],
            "producer_host": ["native", None],
            "optimization": ["2", 0, None],
        }.items():
            for value in wrong_values:
                changed = self.good_producer()
                changed[field] = value
                with self.subTest(field=field, value=value):
                    with self.assertRaises(RuntimeError):
                        Q.require_o0(changed)

    def test_missing_producer_fields_rejected(self):
        for field in self.good_producer():
            changed = self.good_producer()
            del changed[field]
            with self.assertRaises(RuntimeError):
                Q.require_o0(changed)

    def test_inputs_rechecked_from_actual_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"original")
            inputs = {str(path): Q.digest(b"original")}
            Q.check_inputs(inputs)
            path.write_bytes(b"changed")
            with self.assertRaises(RuntimeError):
                Q.check_inputs(inputs)
            path.unlink()
            with self.assertRaises(RuntimeError):
                Q.check_inputs(inputs)

    def dispatch(self, returncode=0):
        runner = mock.Mock()
        runner.run.return_value = types.SimpleNamespace(returncode=returncode)
        composed = types.SimpleNamespace(CommandRunner=mock.Mock(
            return_value=runner))
        entry = types.SimpleNamespace(compose=mock.Mock(return_value=composed))
        direct = types.SimpleNamespace(
            ROOT=Path("/fixed/source"),
            main=mock.Mock(side_effect=AssertionError("direct.main forbidden")),
        )
        worker, crc, pins = object(), object(), {"worker": "pinned"}
        record, save = {"commands": []}, mock.Mock()
        output = Path("/fresh/out")
        receipt = Path("/build/receipt.json")
        clang = Path("/toolchain/clang")
        args = (
            entry, worker, crc, direct, pins, output, record, save,
            receipt, clang,
        )
        return args, runner, composed, direct

    def test_exact_single_target_uses_composition_not_original_main(self):
        args, runner, composed, direct = self.dispatch()
        argv = Q.run_one(*args)
        entry, worker, crc, _, pins, output, record, save, receipt, clang = args
        entry.compose.assert_called_once_with(direct, crc, worker, pins)
        composed.CommandRunner.assert_called_once_with(
            direct.ROOT, output, record, save)
        expected = [
            Q.sys.executable, "-B", str(Q.HERE / "test_candidate_selection.py"),
            "--build-receipt", str(receipt),
            "--clang", str(clang),
            "--output", str(output / "candidate-selection"),
        ]
        self.assertEqual(argv, expected)
        runner.run.assert_called_once_with("candidate-selection", expected, timeout=600)
        direct.main.assert_not_called()

    def test_nonzero_and_bool_result_rejected(self):
        for status in (1, -9, False, True, None):
            args, runner, composed, direct = self.dispatch(status)
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                Q.run_one(*args)
            direct.main.assert_not_called()

    def test_managed_failure_propagates(self):
        args, runner, composed, direct = self.dispatch()
        runner.run.side_effect = RuntimeError("managed cancellation")
        with self.assertRaisesRegex(RuntimeError, "managed cancellation"):
            Q.run_one(*args)
        direct.main.assert_not_called()

    def test_single_result_rejects_inventory_before_reading_files(self):
        command = {
            "name": "candidate-selection",
            "argv": ["expected"],
            "state": "passed",
            "exit_code": 0,
        }
        bad_records = [
            {},
            {"commands": []},
            {"commands": [command, command]},
            {"commands": [dict(command, name="bulk-crc")]},
            {"commands": [dict(command, argv=["changed"])]},
            {"commands": [dict(command, state="failed")]},
            {"commands": [dict(command, exit_code=False)]},
        ]
        for key in (
            "error", "evidence_error", "cleanup_unverified",
            "leader_reap_unverified",
        ):
            changed = dict(command)
            changed[key] = None
            bad_records.append({"commands": [changed]})
        for record in bad_records:
            with self.subTest(record=record), self.assertRaises(RuntimeError):
                Q.validate_single_result(
                    copy.deepcopy(record), None, None, None, {}, Path("/not-read"), ["expected"], None, None,
                )

    def test_fresh_destination_refuses_existing_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = root / "receipt.json"
            receipt.write_bytes(b"not loaded")
            binaries = root / "bin"
            binaries.mkdir()
            output = root / "out"
            output.mkdir()
            marker = output / "preserve"
            marker.write_bytes(b"original")
            with self.assertRaisesRegex(RuntimeError, "fresh qualification"):
                Q.qualify(receipt, binaries, output, "not-resolved")
            self.assertEqual(marker.read_bytes(), b"original")





class ActualEvidenceControls(unittest.TestCase):
    """Synthetic disk evidence only, never a compiler or managed execution."""
    @classmethod
    def setUpClass(cls):
        import candidate_batch_worker as W
        import candidate_batch_contract as C
        import test_direct_candidate_successor as E
        cls.W,cls.C,cls.E=W,C,E
        cls.raws,cls.pins=W.snapshot()

    def fixture(self, directory):
        C=self.C
        output=Path(directory).resolve()/'qualification'
        output.mkdir();target=output/'candidate-selection';target.mkdir()
        receipt=Path(directory).resolve()/'build/receipt.json'
        receipt.parent.mkdir();receipt.write_bytes(b'synthetic producer receipt')
        producer_sha=Q.digest(receipt.read_bytes())
        self.authenticated_producer=dict(complete=True,typecheck_only=False,producer_host='GHC',
            optimization='0',ghc={'path':'/authenticated/ghc'},
            object_inputs={'objects/A.o':'object-A-pin','objects/B.o':'object-B-pin','objects/Main.o':'excluded-main'})
        self.native=dict(clang='/authenticated/clang',runtime_flags=['-I/verified/native/include'],
                         link_args=['/verified/libgmp.so','/verified/libgc.a','-lm'])
        setup=Q.expected_setup(self.authenticated_producer,self.native,receipt.parent,target)
        argv=[Q.sys.executable,'-B',str(Q.HERE/'test_candidate_selection.py'),
              '--build-receipt',str(receipt),'--clang',self.native['clang'],
              '--output',str(target)]
        source=C.original_fixture(self.raws['test_candidate_selection.py'],
                                  self.raws['../../libraries/mlf-inference/Bootstrap/Classes.hs'])
        (target/'CandidateSelection.hs').write_bytes(source)
        generated={str(target/'CandidateSelection.hs'):Q.digest(source)}
        for direction in ('forward','reverse'):
            raw=C.generate(source,direction,self.raws['test_candidate_selection.py'],
                           self.raws['../../libraries/mlf-inference/Bootstrap/Classes.hs'])
            for suffix,data in (('.hs',raw),('.o',b'synthetic object'),('.hi',b'synthetic interface'),('',b'synthetic binary')):
                p=target/('batch-'+direction+suffix);p.write_bytes(data);generated[str(p)]=Q.digest(data)
        for name in ('host-controls','program.ll','runtime.o','native-O0','native-O2'):
            (target/name).write_bytes(b'synthetic '+name.encode())
        physical=[];batches=[];projections=[]
        def add(name,argv,stdout=b'',kind='original'):
            identity='%04d-%s'%(len(physical)+1,name)
            row=dict(id=identity,original_name=name,kind=kind,argv=list(argv),
                state='passed',exit_code=0,expected_status=0,
                timeout_seconds=(240 if name=='emit-native' else 180 if name in ('host-compile','host-link','host-controls')
                    or name.startswith('batch-compile-') or name.startswith('batch-link-') else 120))
            for label,raw in (('stdout',stdout),('stderr',b'')):
                path=target/(identity+'.'+label);path.write_bytes(raw)
                row[label+'_path']=str(path);row[label+'_sha256']=Q.digest(raw)
            physical.append(row);return row
        compile_argv=setup['host-compile'][0]
        link_argv=setup['host-link'][0]
        for name in ('host-compile','host-link','host-controls','emit-native','runtime','native-link-O0','native-link-O2'):
            stdout=Q.HOST_BANNERS if name=='host-controls' else (target/'program.ll').read_bytes() if name=='emit-native' else b''
            add(name,setup[name][0],stdout)
        for direction in ('forward','reverse'):
            compile_command=[str(target/('batch-'+direction+'.hs')) if x==str(Q.HERE/'fixtures/CandidateSelectionControls.hs')
                else str(target/('batch-'+direction+'.o')) if x==str(target/'Main.o')
                else str(target/('batch-'+direction+'.hi')) if x==str(target/'Main.hi') else x for x in compile_argv]
            link_command=[str(target/('batch-'+direction+'.o')) if x==str(target/'Main.o')
                else str(target/('batch-'+direction)) if x==str(target/'host-controls') else x for x in link_argv]
            add('batch-compile-'+direction,compile_command,kind='batch')
            add('batch-link-'+direction,link_command,kind='batch')
            stdout=b''.join(('%d\n%d\n'%(C.BEGIN,i)).encode()+C.cases()[i]['expected']+
                            ('%d\n'%C.END).encode() for i in C.order_for(direction))
            for lane in ('host','interpreter'):
                command=([str(target/('batch-'+direction))] if lane=='host' else
                    [str(receipt.parent/'bin/emlf'),'-i',str(Q.ROOT/'libraries/mlf-foundation'),
                     '--run',str(target/('batch-'+direction+'.hs')),'--'])
                row=add('batch-'+lane+'-'+direction,command,stdout,kind='batch')
                batch=C.physical_record(row['id'],lane,direction,command,stdout,b'',0);batches.append(batch)
                for i in C.FORWARD:
                    original=[str(receipt.parent/'bin/emlf'),'-i',str(Q.ROOT/'libraries/mlf-foundation'),
                              '--run',str(target/'CandidateSelection.hs'),'--',*C.cases()[i]['arguments']]
                    projections.append(C.project(batch,stdout,i,original,C.cases()[i]['expected']))
        for opt in ('0','2'):
            for selector in ('named','ids'):
                for i,(n,period,ids) in enumerate(Q.native_vectors()):
                    command=[str(target/('native-O'+opt)),selector,*map(str,[n,period,len(ids),*ids])]
                    add('native-O'+opt+'-'+selector+'-'+str(i),command,Q.native_expected(n,period,ids))
        state_path=output/'candidate-selection-batch-worker.json'
        original=dict(complete=True,commands=copy.deepcopy(physical),native_configuration=copy.deepcopy(self.native),
            vector_counts={'interpreter':24,'native-O0':124,'native-O2':124},
            **self.W.execution_policy(state_path))
        original['artifacts']={str(target/n):Q.digest((target/n).read_bytes()) for n in
            ('host-controls','CandidateSelection.hs','program.ll','runtime.o','native-O0','native-O2')}
        state=dict(complete=True,physical_commands=physical,logical_indices=list(range(24)),
            batch_commands=batches,logical_vectors=projections,original_receipt=original,
            input_pins=self.pins,producer_receipt_path=str(receipt),producer_receipt_sha256=producer_sha,
            generated_artifacts=generated,fixture_generation='candidate-monomorphic-runtime-loop-v1',
            source_basis=self.C.SOURCE_BASIS,batch_aggregate=C.aggregate(batches,projections))
        worker_argv=[Q.sys.executable,'-B',str(Q.HERE/'candidate_batch_worker.py'),*argv[3:]]
        guard=dict(phase='terminal',reason='target exited',complete=True,cleanup_complete=True,
            target_exit_code=0,survivors=[],signals=[],cancel_signals=[],command=worker_argv,
            work_seconds=600.,cleanup_seconds=10.,root_pid=123,reaped=[dict(pid=123,status=0)])
        command=dict(name='candidate-selection',argv=argv,state='passed',exit_code=0,input_pins=self.pins,
            execution_argv=[Q.sys.executable,'-B',str(Q.HERE/'crc_process_supervisor.py'),
                '--receipt',str(output/'candidate-selection-supervisor.json'),'--work-seconds','600',
                '--cleanup-seconds','10',*worker_argv],worker=state,supervisor=guard,
            original_timeout_seconds=600,work_seconds=600,cleanup_seconds=10,timeout_seconds=625)
        for label,data in (('stdout',b'synthetic managed output'),('stderr',b'')):
            (output/('candidate-selection.'+label)).write_bytes(data)
            command[label+'_sha256']=Q.digest(data)
        record=dict(commands=[command],successor_pins=self.pins,native_configuration=copy.deepcopy(self.native),
                    producer=dict(path=str(receipt),sha256=producer_sha),inputs={str(receipt):producer_sha})
        self.persist(output,record)
        return output,record,argv

    def persist(self,output,record):
        command=record['commands'][0];state=command['worker']
        for path,value in (
            (output/'candidate-selection-batch-worker.json',state),
            (output/'candidate-selection-supervisor.json',command['supervisor']),
            (output/'candidate-selection/receipt.json',state['original_receipt'])):
            path.write_text(json.dumps(value)+'\n')

    def validate(self,output,record,argv):
        return Q.validate_single_result(record,self.W,self.C,self.E,self.pins,output,argv,self.authenticated_producer,self.native)

    def test_complete_synthetic_ledger_reconstructs_every_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            output,record,argv=self.fixture(directory)
            result=self.validate(output,record,argv)
            self.assertEqual((result['physical_commands'],result['batch_executions'],result['batch_projections']),(263,4,96))
            self.assertEqual(result['host_demand_checks'],7)
            self.assertTrue(result['actual_capture_reconstruction_complete'])
            self.assertFalse(result['fresh_process_equivalence_claimed'])
            self.assertEqual(result['original_vector_counts'],{'interpreter':24,'native-O0':124,'native-O2':124})

    def test_actual_capture_changes_and_host_banner_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            output,record,argv=self.fixture(directory)
            rows=record['commands'][0]['worker']['physical_commands']
            for name in ('host-controls','batch-interpreter-forward','native-O2-ids-61'):
                row=next(r for r in rows if r['original_name']==name)
                path=Path(row['stdout_path']);before=path.read_bytes()
                path.write_bytes(before+b'corrupt')
                with self.subTest(name=name),self.assertRaises(RuntimeError):self.validate(output,record,argv)
                path.write_bytes(before)
            # Updating both row hashes does not turn an incomplete host gate
            # into success: the exact independent two-banner gate remains.
            changed=copy.deepcopy(record);state=changed['commands'][0]['worker']
            row=next(r for r in state['physical_commands'] if r['original_name']=='host-controls')
            path=Path(row['stdout_path']);path.write_bytes(Q.HOST_BANNERS.splitlines(keepends=True)[0])
            row['stdout_sha256']=Q.digest(path.read_bytes());state['original_receipt']['commands']=copy.deepcopy(state['physical_commands'])
            self.persist(output,changed)
            with self.assertRaises(RuntimeError):self.validate(output,changed,argv)

    def test_96_omission_wrong_offset_and_receipt_links_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            output,record,argv=self.fixture(directory)
            for kind in ('omission','offset','original-disconnect','worker-disconnect','guard-disconnect'):
                changed=copy.deepcopy(record);state=changed['commands'][0]['worker']
                if kind=='omission':state['logical_vectors'].pop()
                if kind=='offset':state['logical_vectors'][0]['start']+=1
                self.persist(output,changed)
                if kind=='original-disconnect':
                    p=output/'candidate-selection/receipt.json';value=json.loads(p.read_text());value['complete']=False;p.write_text(json.dumps(value))
                if kind=='worker-disconnect':
                    p=output/'candidate-selection-batch-worker.json';value=json.loads(p.read_text());value['complete']=False;p.write_text(json.dumps(value))
                if kind=='guard-disconnect':
                    p=output/'candidate-selection-supervisor.json';value=json.loads(p.read_text());value['root_pid']=321;p.write_text(json.dumps(value))
                with self.subTest(kind=kind),self.assertRaises(RuntimeError):self.validate(output,changed,argv)

    def test_producer_pins_route_budgets_and_cleanup_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            output,record,argv=self.fixture(directory)
            changes=[
                lambda r:r['producer'].update(sha256='wrong'),
                lambda r:r.update(successor_pins={}),
                lambda r:r['commands'][0].update(input_pins={}),
                lambda r:r['commands'][0].update(work_seconds=601),
                lambda r:r['commands'][0].update(cleanup_seconds=True),
                lambda r:r['commands'][0].update(timeout_seconds=626),
                lambda r:r['commands'][0].update(execution_argv=['wrong']),
                lambda r:r['commands'][0]['worker'].update(input_pins={}),
                lambda r:r['commands'][0]['worker'].update(producer_receipt_path='/wrong'),
                lambda r:r['commands'][0]['supervisor'].update(work_seconds=601.),
                lambda r:r['commands'][0]['supervisor'].update(signals=[dict(pid=123,signal=15)])]
            for i,mutate in enumerate(changes):
                changed=copy.deepcopy(record);mutate(changed);self.persist(output,changed)
                with self.subTest(i=i),self.assertRaises(RuntimeError):self.validate(output,changed,argv)
            wrong=list(argv);wrong[2]='wrong'
            self.persist(output,record)
            with self.assertRaises(RuntimeError):self.validate(output,record,wrong)

    def test_generated_body_binary_and_native_arguments_cannot_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            output,record,argv=self.fixture(directory);target=output/'candidate-selection'
            for filename in ('CandidateSelection.hs','batch-forward.hs','batch-reverse.o','batch-forward','runtime.o'):
                path=target/filename;before=path.read_bytes();path.write_bytes(before+b'changed')
                with self.subTest(filename=filename),self.assertRaises((RuntimeError,ValueError)):
                    self.validate(output,record,argv)
                path.write_bytes(before)
            changed=copy.deepcopy(record);state=changed['commands'][0]['worker']
            row=next(r for r in state['physical_commands'] if r['original_name']=='native-O0-named-0')
            row['argv'][-1]='extra'
            state['original_receipt']['commands']=copy.deepcopy(state['physical_commands'])
            self.persist(output,changed)
            with self.assertRaises(RuntimeError):self.validate(output,changed,argv)


    def test_setup_identity_bound_to_real_producer_and_native_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            output,record,argv=self.fixture(directory)
            def alter(name,edit):
                changed=copy.deepcopy(record);state=changed['commands'][0]['worker']
                row=next(r for r in state['physical_commands'] if r['original_name']==name)
                edit(row['argv'])
                state['original_receipt']['commands']=copy.deepcopy(state['physical_commands'])
                self.persist(output,changed)
                return changed
            setup_names=('host-compile','host-link','host-controls','emit-native','runtime','native-link-O0','native-link-O2')
            for name in setup_names:
                changed=alter(name,lambda args:args.__setitem__(0,'/wrong/compiler-or-target'))
                with self.subTest(name=name),self.assertRaises(RuntimeError):self.validate(output,changed,argv)
            edits=[
                ('host-link',lambda args:args.remove(str(Path(argv[4]).parent/'objects/A.o'))),
                ('host-link',lambda args:args.remove(str(Path(argv[4]).parent/'host.o'))),
                ('host-link',lambda args:args.remove(str(Path(argv[4]).parent/'supervisor.o'))),
                ('host-compile',lambda args:args.remove('-fpedantic-bottoms')),
                ('runtime',lambda args:args.remove('-I/verified/native/include')),
                ('native-link-O0',lambda args:args.remove('/verified/libgc.a')),
                ('native-link-O2',lambda args:args.remove('-O2'))]
            for name,edit in edits:
                changed=alter(name,edit)
                with self.subTest(name=name),self.assertRaises(RuntimeError):self.validate(output,changed,argv)
            changed=copy.deepcopy(record)
            changed['native_configuration']['runtime_flags']=['-I/foreign']
            changed['commands'][0]['worker']['original_receipt']['native_configuration']=copy.deepcopy(changed['native_configuration'])
            self.persist(output,changed)
            with self.assertRaises(RuntimeError):self.validate(output,changed,argv)
            self.persist(output,record)
            foreign=copy.deepcopy(self.authenticated_producer);foreign['ghc']['path']='/foreign/ghc'
            with self.assertRaises(RuntimeError):
                Q.validate_single_result(record,self.W,self.C,self.E,self.pins,output,argv,foreign,self.native)
            foreign=copy.deepcopy(self.authenticated_producer);foreign['object_inputs'].pop('objects/B.o')
            with self.assertRaises(RuntimeError):
                Q.validate_single_result(record,self.W,self.C,self.E,self.pins,output,argv,foreign,self.native)

if __name__=='__main__':unittest.main()
