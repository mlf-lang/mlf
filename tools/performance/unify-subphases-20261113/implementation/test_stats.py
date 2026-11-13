from pathlib import Path
import unittest
import stats

RAW='''60,546,927,152 bytes allocated in the heap
4,299,126,432 bytes copied during GC
36,197,520 bytes maximum residency (59 sample(s))
1,576,568 bytes maximum slop
105 MiB total memory in use (0 MiB lost due to fragmentation)
 Gen 0 14400 colls, 0 par 3.571s 3.702s 0.0003s 0.2216s
 Gen 1 59 colls, 0 par 1.842s 1.842s 0.0312s 0.2527s
 INIT time 0.000s (0.001s elapsed)
 MUT time 26.817s (27.375s elapsed)
 GC time 5.413s (5.544s elapsed)
 EXIT time 0.000s (0.000s elapsed)
 Total time 32.230s (32.921s elapsed)
 %GC time 0.0% (0.0% elapsed)
 Alloc rate 2,257,809,726 bytes per MUT second
 Productivity 83.2% of total user, 83.2% of total elapsed
'''
class StatisticsTests(unittest.TestCase):
    def test_complete_mib_raw_zero_preserved(self):
        s=stats.parse_statistics(RAW.encode())
        self.assertEqual(s['allocated_bytes'],60546927152)
        self.assertEqual(s['rts_memory_in_use']['unit'],'MiB')
        self.assertEqual(s['rts_memory_in_use']['fragmentation']['unit'],'MiB')
        self.assertEqual(s['reported_gc_percent']['values']['cpu'],0)
        self.assertAlmostEqual(s['gc_cpu_fraction_from_rounded_times'],5.413/32.230)
    def test_decimal_unit_not_relabelled(self):
        self.assertEqual(stats.parse_statistics(RAW.replace('MiB','MB'))['rts_memory_in_use']['unit'],'MB')
    def test_huge_integer_exact(self):
        n='9'*100
        self.assertEqual(stats.parse_statistics(RAW.replace('60,546,927,152',n))['allocated_bytes'],int(n))
    def test_duplicate_every_required_line(self):
        for line in RAW.splitlines():
            with self.subTest(line=line),self.assertRaises(ValueError):stats.parse_statistics(RAW+line+'\n')
    def test_truncated_required_fields(self):
        for line in RAW.splitlines():
            if '%GC' in line:continue
            with self.subTest(line=line),self.assertRaises(ValueError):stats.parse_statistics(RAW.replace(line+'\n',''))
    def test_optional_gc_absent(self):
        self.assertIsNone(stats.parse_statistics(RAW.replace(' %GC time 0.0% (0.0% elapsed)\n',''))['reported_gc_percent'])
    def test_nonfinite_negative_malformed_integer(self):
        for old,new in [('5.413','NaN'),('5.413','inf'),('5.413','-1'),('5.413','9'*400),('60,546,927,152','60,,546'),('83.2','101.0')]:
            with self.subTest(new=new),self.assertRaises(ValueError):stats.parse_statistics(RAW.replace(old,new))
    def test_generations_order_parallel_number(self):
        for new in ['Gen 2 59','Gen 0 59','Gen 1 59 nonsense']:
            with self.assertRaises(ValueError):stats.parse_statistics(RAW.replace('Gen 1 59',new))
        with self.assertRaises(ValueError):stats.parse_statistics(RAW.replace('0 par','1 par'))
    def test_zero_total_no_division(self):
        self.assertIsNone(stats.parse_statistics(RAW.replace('32.230','0.000'))['gc_cpu_fraction_from_rounded_times'])
    def test_profile_overhead_time(self):
        self.assertIn('PROF',stats.parse_statistics(RAW+' PROF time 0.001s (0.002s elapsed)\n')['times'])
if __name__=='__main__':unittest.main()
