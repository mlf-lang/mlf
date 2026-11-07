import hashlib
import io
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import recovery_common as r

class RecoveryTests(unittest.TestCase):
    def test_mismatch_never_extracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=pathlib.Path(tmp)/'bad.deb';file.write_bytes(b'wrong')
            with patch.object(r.subprocess,'run') as execute:
                with self.assertRaises(ValueError):r.extract_verified(file,pathlib.Path(tmp)/'prefix','0'*64,5)
                execute.assert_not_called()
    def test_matching_and_optimized_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=pathlib.Path(tmp)/'archive';file.write_bytes(b'abc')
            self.assertEqual(r.verify(file,hashlib.sha256(b'abc').hexdigest(),3),3)
            for flags in ([],['-O']):
                result=subprocess.run([sys.executable,*flags,'-B','-c','from recovery_common import verify; verify(__import__("sys").argv[1],"0"*64,3)',str(file)],cwd=pathlib.Path(__file__).parent,capture_output=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(b'refusing extraction',result.stderr)
    def test_download_byte_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=pathlib.Path(tmp)/'archive'
            with patch.object(r.urllib.request,'urlopen',return_value=io.BytesIO(b'abcd')):
                with self.assertRaisesRegex(ValueError,'byte bound'):
                    r.download_verified('https://example.invalid/',target,'0'*64,3)
            self.assertLessEqual(target.stat().st_size,3)
    def test_repository_and_worktree_outputs_rejected(self):
        for marker_directory in (True,False):
            with tempfile.TemporaryDirectory() as tmp:
                root=pathlib.Path(tmp);marker=root/'.git'
                if marker_directory:marker.mkdir()
                else:marker.write_text('gitdir: /unneeded/example')
                nested=root/'nested';nested.mkdir()
                with patch.object(r,'check_resources') as check:
                    with self.assertRaisesRegex(ValueError,'outside any Git'):
                        r.new_output(nested/'new-child',0)
                    check.assert_not_called()
                self.assertFalse((nested/'new-child').exists())
    def test_existing_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):r.new_output(tmp,0)

if __name__=='__main__':unittest.main()
