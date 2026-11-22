"""Pure synthetic-data contract tests. No compiler/interpreter invocation."""
import copy
from pathlib import Path
import unittest
import candidate_batch_contract as C

HERE=Path(__file__).resolve().parent

class SelectorSourceChecks:
    @classmethod
    def setUpClass(cls):
        cls.script=(HERE/'test_candidate_selection.py').read_bytes()
        cls.classes=cls.classes_path.read_bytes()
        actual=C.blob(cls.classes)
        if actual not in cls.accepted_blobs:
            raise ValueError(f'{cls.classes_path.name}: unexpected Classes blob {actual} for {cls.__name__}')
        cls.original=C.original_fixture(cls.script,cls.classes)
    def test_fixed_full_sources_and_selector_body(self):
        self.assertEqual(C.blob(self.script),C.SCRIPT_BLOB)
        self.assertIn(C.blob(self.classes), C.CLASSES_BLOBS)
        self.assertEqual(C.digest(self.original), C.ORIGINAL_FIXTURE_SHA256)
        body=self.classes[self.classes.index(b'  selectCandidates ::'):self.classes.index(b'  methodBindings ::')]
        self.assertEqual(self.original.count(body),1)
        for a,b in ((self.script+b'\n',self.classes),(self.script,self.classes+b'\n')):
            with self.assertRaises(ValueError):C.original_fixture(a,b)
    def test_complete_inverse_both_directions_and_single_call(self):
        body=self.classes[self.classes.index(b'  selectCandidates ::'):self.classes.index(b'  methodBindings ::')]
        for direction in ('forward','reverse'):
            raw=C.generate(self.original,direction,self.script,self.classes)
            self.assertEqual(C.restore(raw,direction,self.script,self.classes),self.original)
            self.assertEqual(raw.count(body),1)
            self.assertEqual(raw.count(b'runCase (batchArgument args);'),1)
            self.assertEqual(raw.count(b'  main :: IO ();'),1)
            self.assertEqual(raw.count(b'  readIndices :: (Int -> IO String) -> Int -> Int -> IO ([] Int);'),1)
            self.assertIn(b'rest <- readIndices getArg (position + 1) (count - 1);',raw)
            self.assertIn(b'indices <- readIndices getArg 4 (readInt count);',raw)
            self.assertNotIn(b'rest <- readIndices (',raw)
            table=b', '.join(('(,) %d [%s]'%(i,', '.join('"%s"'%a for a in C.cases()[i]['arguments']))).encode()
                            for i in C.order_for(direction))
            self.assertIn(b'batchCases = ['+table+b'];',raw)
    def test_inverse_refuses_every_adaptation_and_data_tamper(self):
        raw=C.generate(self.original,'forward',self.script,self.classes)
        for old,new in C.ADAPTATIONS:
            with self.subTest(old=old),self.assertRaises(ValueError):
                C.restore(raw.replace(new,old,1),'forward',self.script,self.classes)
        for changed in (raw+b'\n',raw.replace(b'InstanceEvidence',b'GivenEvidence',1),
                        raw.replace(b'runCase (batchArgument args);',b'runCase getArg;',1),
                        raw.replace(b'readIndices getArg (position + 1)',b'readIndices getArg position',1),
                        raw.replace(b'(,) 0 ["named"',b'(,) 1 ["named"',1),
                        raw.replace(b'"named", "0"',b'"ids", "0"',1),
                        raw.replace(b'Int -> IO ([] Int)',b'Int -> IO Int',1),
                        raw.replace(b'printInt index;',b'printInt 0;',1)):
            with self.assertRaises(ValueError):C.restore(changed,'forward',self.script,self.classes)
        with self.assertRaises(ValueError):C.restore(raw,'reverse',self.script,self.classes)
        with self.assertRaises(ValueError):C.generate(self.original+b'\n','forward',self.script,self.classes)
        with self.assertRaises(ValueError):C.generate(self.original,'other',self.script,self.classes)

# Keep both inputs: the synthetic oracle has a fixed basis, while the live
# selector must still pass every original source, inverse and tamper check.
class HistoricalSourceControls(SelectorSourceChecks, unittest.TestCase):
    # Exact Classes.hs bytes from candidate_batch_contract.SOURCE_BASIS.
    classes_path=HERE/'fixtures/candidate-selection/Classes.hs.txt'
    accepted_blobs=('bbcc794dc1ce447ccfc1450378e951df1b427819',)

class LiveSourceControls(SelectorSourceChecks, unittest.TestCase):
    classes_path=HERE/'../../libraries/mlf-inference/Bootstrap/Classes.hs'
    accepted_blobs=C.CLASSES_BLOBS

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
