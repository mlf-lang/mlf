"""Pure synthetic-data contract tests. No compiler/interpreter invocation."""
import copy
import unittest
import candidate_batch_contract as C

class ContractControls(unittest.TestCase):
    def capture(self,direction):
        # Test fixture only, never represented as actual workload evidence.
        return b''.join(('%d\n%d\n'%(C.BEGIN,i)).encode()+C.cases()[i]['expected']+
                        ('%d\n'%C.END).encode() for i in C.order_for(direction))
    def fixture(self):
        physical=[];projections=[]
        for direction in ('forward','reverse'):
            raw=self.capture(direction)
            for lane in ('host','interpreter'):
                row=C.physical_record(lane+'-'+direction,lane,direction,['synthetic'],raw,b'',0)
                physical.append(row)
                for i in range(24):
                    projections.append(C.project(row,raw,i,['original',*C.cases()[i]['arguments']],C.cases()[i]['expected']))
        return physical,projections
    def test_independent_literal_inventory(self):
        small=[
            (0,[]),(0,[-1,0]),(0,[0,0,1,-1]),
            (1,[]),(1,[-1,1]),(1,[0,0,1,0]),
            (2,[]),(2,[-1,2]),(2,[0,0,1,1]),
            (7,[]),(7,[-1,7]),(7,[0,0,1,6])]
        outputs=['','','','','','i:n0;','','','i:n0;i:n1;','','','i:n0;i:n1;i:n6;']
        expected_tail='s:super;g:given;i:n0;i:n0;\n'
        got=C.cases()
        self.assertEqual(list(got),list(range(24)))
        for selector,offset in [('named',0),('ids',12)]:
            for i,((n,ids),prefix) in enumerate(zip(small,outputs)):
                self.assertEqual(got[offset+i],dict(selector=selector,index=i,
                    arguments=[selector,str(n),'0',str(len(ids)),*map(str,ids)],
                    expected=(prefix+expected_tail).encode()))
    def test_actual_byte_ranges_have_no_virtual_process_fields(self):
        for d in ('forward','reverse'):
            raw=self.capture(d);rows=C.parse(raw,d)
            self.assertEqual([r['index'] for r in rows],list(C.order_for(d)))
            for row in rows:
                self.assertEqual(raw[row['start']:row['end']],C.cases()[row['index']]['expected'])
                self.assertEqual(C.digest(raw[row['start']:row['end']]),row['actual_sha256'])
            p=C.physical_record('synthetic','host',d,['synthetic'],raw,b'',0)
            r=C.project(p,raw,0,['original',*C.cases()[0]['arguments']],C.cases()[0]['expected'])
            self.assertIs(r['fresh_process'],False)
            for key in ('exit_code','seconds','pid'):self.assertNotIn(key,r)
    def test_partial_extra_duplicate_reordered_and_corrupt_output(self):
        raw=self.capture('forward');lines=raw.splitlines(keepends=True)
        wrong=[raw[:-1],raw+b'\n',raw.replace(b'\n',b'\r\n'),
            b''.join(lines[4:]),b''.join(lines[:4]+lines),b''.join(lines[4:8]+lines[:4]+lines[8:]),
            raw.replace(b's:super;',b'g:super;',1),raw.replace(b'812350001',b'812350099',1)]
        for changed in wrong:
            with self.assertRaises(ValueError):C.parse(changed,'forward')
        with self.assertRaises(ValueError):C.parse(raw,'reverse')
    def test_all_four_batch_and_96_projection_inventory(self):
        physical,rows=self.fixture();r=C.aggregate(physical,rows)
        self.assertEqual(r['physical_batch_count'],4);self.assertEqual(r['logical_projection_count'],96)
        self.assertFalse(r['whole_candidate_complete'])
        for i in range(96):
            with self.assertRaises(ValueError):C.aggregate(physical,rows[:i]+rows[i+1:])
        for i in range(4):
            with self.assertRaises(ValueError):C.aggregate(physical[:i]+physical[i+1:],rows)
        with self.assertRaises(ValueError):C.aggregate(physical,rows+[rows[0]])
    def test_identity_offset_status_argv_and_false_execution_refused(self):
        physical,rows=self.fixture()
        for field,value in [('exit_code',False),('exit_code',1),('stdout_bytes',True),
                            ('stdout_sha256','bad'),('stderr_sha256','bad'),('lane','wrong')]:
            wrong=copy.deepcopy(physical);wrong[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):C.aggregate(wrong,rows)
        for field,value in [('index',True),('start',True),('end',0),('physical_command_id','foreign'),
                            ('actual_sha256','bad'),('physical_stdout_sha256','bad'),
                            ('fresh_process',True),('kind','executed-process'),('original_argv',['wrong'])]:
            wrong=copy.deepcopy(rows);wrong[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):C.aggregate(physical,wrong)
        for status,stderr in [(False,b''),(1,b''),(0,b'error')]:
            with self.assertRaises(ValueError):C.physical_record('id','host','forward',['cmd'],self.capture('forward'),stderr,status)
        p=physical[0]
        with self.assertRaises(ValueError):C.project(p,self.capture('forward'),0,['wrong'],C.cases()[0]['expected'])
        with self.assertRaises(ValueError):C.project(p,self.capture('forward'),0,['original',*C.cases()[0]['arguments']],b'wrong\n')

if __name__=='__main__':unittest.main()
