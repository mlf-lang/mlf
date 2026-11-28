"""Pure full-inventory controls. No compiler/interpreter/process execution."""
import copy
from pathlib import Path
import tempfile
import unittest
import utf8_batch_worker as W

class WorkerControls(unittest.TestCase):
    def test_execution_labels_are_policy_not_fabricated_results(self):
        policy=W.execution_policy(Path('/out/utf8-length-batch-worker.json'))
        self.assertFalse(policy['fresh_process_equivalence_claimed'])
        self.assertTrue(policy['execution_policy_is_not_completion_evidence'])
        self.assertEqual(policy['batch_worker_receipt'],'/out/utf8-length-batch-worker.json')
        for lane in ('host','native-O0','native-O2'):
            self.assertEqual(policy['vector_execution_modes'][lane],
                             {'mode':'original fresh process per vector','required_vectors':29})
        interpreter=policy['vector_execution_modes']['interpreter']
        self.assertEqual(interpreter['required_vectors'],25)
        self.assertEqual(interpreter['required_batch_executions'],{'interpreter':2,'host':2})
        self.assertIn('logical projections',interpreter['mode'])
        self.assertIn('physical execution ledger only',policy['commands_semantics'])
        self.assertNotIn('complete',policy);self.assertNotIn('vector_counts',policy)
        record={'scope':'original scope','complete':False,'commands':[]}
        record.update(policy)
        self.assertEqual(record['scope'],'original scope');self.assertFalse(record['complete'])
        self.assertEqual(record['commands'],[])
    def fixture(self):
        record=dict(complete=True,vector_counts={'host':29,'interpreter':25,'native-O0':29,'native-O2':29},
                    demand_counts=dict.fromkeys(('host','interpreter','native-O0','native-O2'),3),
                    direct_runtime_cases=[dict(optimization=o,case=c) for o in ('0','2') for c in ('success','no-interior','bottom','wrong-type','invalid-utf8','overflow')])
        physical=[]
        for name,count in W.expected_original_names().items():
            for _ in range(count): physical.append(dict(id=str(len(physical)+1),original_name=name,kind='original',state='passed'))
        batches=[]
        for direction in ('forward','reverse'):
            for step in ('compile','link','host','interpreter'):
                row=dict(id=str(len(physical)+1),original_name='batch-'+step+'-'+direction,kind='batch',state='passed')
                physical.append(row)
                if step in ('host','interpreter'): batches.append({'id':row['id']})
        return record,physical,list(range(6))+list(range(10,29)),batches
    def test_full_inventory_independent_counts(self):
        args=self.fixture(); W.validate_inventory(*args)
        self.assertEqual(len(args[1]),133)
        self.assertEqual(sum(args[0]['vector_counts'].values()),112)
        self.assertEqual(W.expected_original_names()['compile-host'],2)
        self.assertFalse(any(x.startswith('interpreter-vector-') for x in W.expected_original_names()))
    def test_each_physical_omission_and_duplicate(self):
        record,physical,indices,batches=self.fixture()
        for i in range(len(physical)):
            for wrong in (physical[:i]+physical[i+1:],physical+[physical[i]]):
                with self.subTest(i=i),self.assertRaises(ValueError): W.validate_inventory(record,wrong,indices,batches)
    def test_logical_original_complete_and_runtime(self):
        for field in ('complete','vector_counts','demand_counts','direct_runtime_cases'):
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

    def test_snapshot_records_current_inputs_without_historical_whitelist(self):
        raws,pins=W.snapshot()
        self.assertEqual(set(raws),set(W.INPUTS))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,raw in raws.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            self.assertEqual(W.snapshot(root)[1],pins)
            for name in W.INPUTS:
                path=root/name;path.write_bytes(raws[name]+b'\n')
                changed=W.snapshot(root)[1]
                self.assertNotEqual(changed[name],pins[name])
                self.assertEqual({key for key in pins if changed[key]!=pins[key]},{name})
                path.write_bytes(raws[name])

if __name__=='__main__':unittest.main()
