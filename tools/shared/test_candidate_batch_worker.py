"""Pure full-inventory controls. No compiler/interpreter/process execution."""
import copy
from pathlib import Path
import tempfile
import unittest
import candidate_batch_worker as W

class WorkerControls(unittest.TestCase):
    def test_execution_labels_are_policy_not_fabricated_results(self):
        policy=W.execution_policy(Path('/out/candidate-selection-batch-worker.json'))
        self.assertFalse(policy['fresh_process_equivalence_claimed'])
        self.assertTrue(policy['execution_policy_is_not_completion_evidence'])
        self.assertEqual(policy['batch_worker_receipt'],'/out/candidate-selection-batch-worker.json')
        for lane in ('native-O0','native-O2'):
            self.assertEqual(policy['vector_execution_modes'][lane],
                             {'mode':'original fresh process per vector','required_vectors':124})
        interpreter=policy['vector_execution_modes']['interpreter']
        self.assertEqual(interpreter['required_vectors'],24)
        self.assertEqual(interpreter['required_batch_executions'],{'interpreter':2,'host':2})
        self.assertIn('logical projections',interpreter['mode'])
        self.assertIn('physical commands only',policy['commands_semantics'])
        self.assertIn('8254 + 12369',policy['host_gate'])
        self.assertNotIn('complete',policy);self.assertNotIn('vector_counts',policy)
        record={'scope':'original scope','complete':False,'commands':[]}
        record.update(policy)
        self.assertEqual(record['scope'],'original scope');self.assertFalse(record['complete'])
        self.assertEqual(record['commands'],[])
    def fixture(self):
        record=dict(complete=True,vector_counts={'interpreter':24,'native-O0':124,'native-O2':124})
        physical=[]
        for name,count in W.expected_original_names().items():
            for _ in range(count): physical.append(dict(id=str(len(physical)+1),original_name=name,kind='original',state='passed',exit_code=0,expected_status=0))
        batches=[]
        for direction in ('forward','reverse'):
            for step in ('compile','link','host','interpreter'):
                row=dict(id=str(len(physical)+1),original_name='batch-'+step+'-'+direction,kind='batch',state='passed',exit_code=0,expected_status=0)
                physical.append(row)
                if step in ('host','interpreter'): batches.append({'id':row['id']})
        record['commands']=copy.deepcopy(physical)
        return record,physical,list(range(24)),batches
    def test_full_inventory_independent_counts(self):
        args=self.fixture(); W.validate_inventory(*args)
        self.assertEqual(len(args[1]),263)
        self.assertEqual(sum(args[0]['vector_counts'].values()),272)
        self.assertEqual(W.expected_original_names()['host-controls'],1)
        self.assertEqual(W.expected_original_names()['native-O2-ids-61'],1)
        self.assertFalse(any(x.startswith('interpreter-') for x in W.expected_original_names()))
    def test_each_physical_omission_and_duplicate(self):
        record,physical,indices,batches=self.fixture()
        for i in range(len(physical)):
            for wrong in (physical[:i]+physical[i+1:],physical+[physical[i]]):
                with self.subTest(i=i),self.assertRaises(ValueError): W.validate_inventory(record,wrong,indices,batches)
    def test_logical_original_complete_and_runtime(self):
        for field in ('complete','vector_counts','commands'):
            args=list(copy.deepcopy(self.fixture())); args[0].pop(field)
            with self.subTest(field=field),self.assertRaises(ValueError): W.validate_inventory(*args)
        for indices in ([],list(range(25)),list(reversed(self.fixture()[2])),self.fixture()[2]+[0]):
            args=list(self.fixture()); args[2]=indices
            with self.assertRaises(ValueError): W.validate_inventory(*args)
    def test_failed_foreign_and_full_inventory_as_subset_refused(self):
        args=list(self.fixture()); args[1][0]['state']='failed'
        with self.assertRaises(ValueError): W.validate_inventory(*args)
        args=list(self.fixture()); args[3]=args[1]
        with self.assertRaises(ValueError): W.validate_inventory(*args)
        args=list(self.fixture()); args[3][0]['id']='foreign'
        with self.assertRaises(ValueError): W.validate_inventory(*args)
    def test_explicit_projection_not_process(self):
        rows=[dict(physical_command_id=str(i),index=0,kind='verified-batch-projection',fresh_process=False) for i in range(4)]
        value=W.BatchVectorResult(rows,b'')
        self.assertEqual(value.stderr,b'')
        self.assertFalse(hasattr(value,'returncode')); self.assertFalse(hasattr(value,'stdout'))
        for bad in (rows[:3],rows+[rows[0]],[rows[0]]*4):
            with self.assertRaises(ValueError): W.BatchVectorResult(bad,b'')
        with self.assertRaises(ValueError): W.BatchVectorResult(rows,b'error')
        changed=copy.deepcopy(rows);changed[0]['fresh_process']=True
        with self.assertRaises(ValueError): W.BatchVectorResult(changed,b'')
    def test_strict_logical_integer_indices_and_projection_range(self):
        for position,value in ((0,False),(1,True),(0,0.0),(23,23.0)):
            args=list(self.fixture());args[2][position]=value
            with self.subTest(position=position,value=value),self.assertRaises(ValueError):
                W.validate_inventory(*args)
        rows=[dict(physical_command_id=str(i),index=0,kind='verified-batch-projection',fresh_process=False)
              for i in range(4)]
        for value in (False,True,0.0,-1,24,None):
            for all_rows in (False,True):
                changed=copy.deepcopy(rows)
                for r in (changed if all_rows else changed[:1]):r['index']=value
                with self.subTest(value=value,all_rows=all_rows),self.assertRaises(ValueError):
                    W.BatchVectorResult(changed,b'')
        changed=copy.deepcopy(rows);changed[0]['index']=1
        with self.assertRaises(ValueError):W.BatchVectorResult(changed,b'')

    def test_strict_exit_kind_and_id_fields_on_both_ledgers(self):
        mutations=[('exit_code',False),('exit_code',True),('exit_code',0.0),
                   ('exit_code',1),('exit_code',-15),('expected_status',False),
                   ('expected_status',0.0),('expected_status',1),('state','running'),
                   ('kind','unknown'),('kind',None),('id',''),('id',True),('id',1)]
        for position in (0,262):
            for key,value in mutations:
                # Mutate one ledger, or both identically. The latter proves
                # strict row checks rather than only equality with its peer.
                for target in ('physical','record','both'):
                    args=list(self.fixture())
                    if target in ('physical','both'):args[1][position][key]=value
                    if target in ('record','both'):args[0]['commands'][position][key]=value
                    with self.subTest(position=position,key=key,value=value,target=target),self.assertRaises(ValueError):
                        W.validate_inventory(*args)
            for key in ('id','kind','state','exit_code','expected_status'):
                args=list(self.fixture());args[1][position].pop(key);args[0]['commands'][position].pop(key)
                with self.subTest(position=position,missing=key),self.assertRaises(ValueError):
                    W.validate_inventory(*args)
        args=list(self.fixture())
        args[1][1]['id']=args[1][0]['id'];args[0]['commands'][1]['id']=args[0]['commands'][0]['id']
        with self.assertRaises(ValueError):W.validate_inventory(*args)

    def test_original_receipt_cannot_detach_or_reorder_physical_ledger(self):
        for replacement in (None,[],self.fixture()[1][:-1],list(reversed(self.fixture()[1]))):
            args=list(self.fixture());args[0]['commands']=replacement
            with self.assertRaises(ValueError):W.validate_inventory(*args)
        args=list(self.fixture());args[0]['commands'][0]['unrecorded_difference']='changed'
        with self.assertRaises(ValueError):W.validate_inventory(*args)

    def test_frozen_source_loader_executes_exact_bytes_not_pyc(self):
        module=W.load(b'value=7\n','synthetic_source','/does-not-exist/source.py')
        self.assertEqual(module.value,7)
        self.assertEqual(module.__file__,'/does-not-exist/source.py')
    def test_every_frozen_source_tamper_fails_snapshot(self):
        raws,pins=W.snapshot()
        self.assertEqual(set(raws),set(W.PINS)|set(W.HELPERS))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'tools/shared'
            root.mkdir(parents=True)
            for name,raw in raws.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            self.assertEqual(W.snapshot(root)[1],pins)
            for name in W.PINS:
                path=root/name;path.write_bytes(raws[name]+b'\n')
                with self.subTest(name=name),self.assertRaises(ValueError):W.snapshot(root)
                path.write_bytes(raws[name])

if __name__=='__main__':unittest.main()
