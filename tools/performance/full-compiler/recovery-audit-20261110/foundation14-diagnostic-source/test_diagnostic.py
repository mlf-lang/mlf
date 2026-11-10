import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('diagnostic',Path(__file__).with_name('run_diagnostic.py'))
D=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(D)
RAW=b'''       8,000,000 bytes allocated in the heap
       2,000,000 bytes copied during GC
         100,000 bytes maximum residency (3 sample(s))
          10,000 bytes maximum slop
               8 MiB total memory in use (0 MB lost due to fragmentation)
                                     Tot time (elapsed)  Avg pause  Max pause
  Gen  0        12 colls,     0 par    0.100s   0.110s     0.0100s    0.0200s
  Gen  1         3 colls,     0 par    0.200s   0.210s     0.0700s    0.0800s
  INIT    time    0.001s  (  0.001s elapsed)
  MUT     time    1.000s  (  1.100s elapsed)
  GC      time    0.300s  (  0.320s elapsed)
  EXIT    time    0.001s  (  0.001s elapsed)
  Total   time    1.302s  (  1.422s elapsed)
  Alloc rate    8,000,000 bytes per MUT second
  Productivity  76.8% of total user,  77.4% of total elapsed
'''

class Statistics(unittest.TestCase):
    def test_complete(self):
        r=D.parse_statistics(RAW)
        self.assertEqual(r['allocated_bytes'],8000000)
        self.assertEqual(r['major_gc_residency_samples'],3)
        self.assertEqual(r['times']['GC']['cpu_seconds'],.3)
        self.assertEqual(r['generations'][0]['collections'],12)
    def test_older_unit_spelling(self):
        self.assertEqual(D.parse_statistics(RAW.replace(b'MiB total',b'MB total'))['rts_memory_in_use']['value'],8)
    def test_truncation(self):
        with self.assertRaises(ValueError):D.parse_statistics(RAW[:300])
    def test_duplicate_summary(self):
        with self.assertRaises(ValueError):D.parse_statistics(RAW+RAW)
    def test_nonfinite(self):
        with self.assertRaises(ValueError):D.parse_statistics(RAW.replace(b'1.302s',b'nans'))
    def test_negative(self):
        with self.assertRaises(ValueError):D.parse_statistics(RAW.replace(b'1.302s',b'-1.302s'))
    def test_parallel_gc(self):
        with self.assertRaises(ValueError):D.parse_statistics(RAW.replace(b'0 par',b'1 par'))
    def test_no_missing_generations(self):
        with self.assertRaises(ValueError):D.parse_statistics(RAW.replace(b'Gen  1',b'Gen  2'))

if __name__=='__main__':unittest.main()
