"""Finite source-package custody controls; no actual compiler/native execution."""
import importlib.util,sys,unittest,tempfile,json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
# Load the real dependency; never publish a fake canonical module during discovery.
_saved_path=sys.path[:]
try:
 sys.path.insert(0,str(BASE))
 spec=importlib.util.spec_from_file_location('module_prepare_test',BASE/'module_prepare.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 assert Path(m.module_transport.__file__).resolve()==(BASE/'module_transport.py').resolve()
finally:
 sys.path[:]=_saved_path

class SnapshotTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.root=self.base/'guest';self.root.mkdir();self.output=self.base/'out';self.entry=self.root/'Main.emlf';self.entry.write_text('import qualified A as A; A.x\n');(self.root/'A.emlf').write_text('module A where { x = 42 }\n')
 def snap(self):return m.snapshot(self.entry,self.root,self.output)
 def test_exact_copy_and_unimported(self):
  (self.root/'Unused.emlf').write_text('not imported');folder,p,b=self.snap();self.assertEqual(p['copied_files'],3);self.assertEqual(b,self.entry.read_bytes());self.assertEqual(m.inventory(p['snapshot_root'])[1],m.inventory(self.root)[1])
 def test_hs_even_unimported_reject(self):
  (self.root/'Unused.hs').write_text('ignored?');self.assertRaisesRegex(ValueError,r'\.hs',self.snap)
 def test_file_symlink_reject(self):
  (self.root/'B.emlf').symlink_to(self.root/'A.emlf');self.assertRaisesRegex(ValueError,'symlink',self.snap)
 def test_directory_symlink_reject(self):
  (self.root/'sub').symlink_to(self.base,target_is_directory=True);self.assertRaisesRegex(ValueError,'symlink',self.snap)
 def test_root_symlink_reject(self):
  link=self.base/'alias';link.symlink_to(self.root,target_is_directory=True);self.assertRaisesRegex(ValueError,'canonical',m.snapshot,link/'Main.emlf',link,self.output)
 def test_outside_entry_reject(self):
  outside=self.base/'Other.emlf';outside.write_text('42');self.assertRaisesRegex(ValueError,'inside',m.snapshot,outside,self.root,self.output)
 def test_fifo_reject(self):
  import os;os.mkfifo(self.root/'pipe');self.assertRaisesRegex(ValueError,'special',self.snap)
 def test_unimported_file_count_bound(self):
  for i in range(31):(self.root/(str(i)+'.emlf')).write_text('0')
  self.assertRaisesRegex(ValueError,'count',self.snap)
 def test_unimported_size_bound(self):
  (self.root/'Huge.emlf').write_bytes(b'x'*(m.MAX_FILE_BYTES+1));self.assertRaisesRegex(ValueError,'1MiB',self.snap)
 def test_unimported_total_bound(self):
  for i in range(8):(self.root/(str(i)+'.emlf')).write_bytes(b'x'*m.MAX_FILE_BYTES)
  self.assertRaisesRegex(ValueError,'8MiB',self.snap)
 def test_bad_utf8_reject(self):
  (self.root/'Bad.emlf').write_bytes(b'\xff');self.assertRaises(UnicodeDecodeError,self.snap)
 def test_backslash_path_reject(self):
  (self.root/'Bad\\name.emlf').write_text('0');self.assertRaisesRegex(ValueError,'unsafe',self.snap)
 def test_stale_import_reject(self):
  _,p,b=self.snap();e={'module_package':p,'source_sha256':m.sha(b)};(self.root/'A.emlf').write_text('changed');self.assertRaisesRegex(ValueError,'stale',m.verify_source_package,e)
 def test_added_unimported_reject(self):
  _,p,b=self.snap();e={'module_package':p,'source_sha256':m.sha(b)};(self.root/'Added.emlf').write_text('0');self.assertRaisesRegex(ValueError,'stale',m.verify_source_package,e)
 def test_private_snapshot_mutation_reject(self):
  _,p,b=self.snap();e={'module_package':p,'source_sha256':m.sha(b)};(Path(p['snapshot_root'])/'A.emlf').write_text('bad');self.assertRaisesRegex(ValueError,'private',m.verify_source_package,e)
 def test_unchanged_package_pass(self):
  _,p,b=self.snap();m.verify_source_package({'module_package':p,'source_sha256':m.sha(b)})

if __name__=='__main__':unittest.main()
