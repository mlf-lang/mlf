#!/usr/bin/env python3
"""Run the real source-provenance wrapper with a symlinked inherited TMPDIR.

No gates are mocked or skipped. The wrapper runs normal and optimized Python.
This tests Linux simulation of macOS-style temp paths, not macOS itself.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]

class ProvenanceTemporaryRootTests(unittest.TestCase):
    def test_real_wrapper_with_symlink_temp_root(self):
        with tempfile.TemporaryDirectory(prefix='provenance-temp-regression-') as temporary:
            root=Path(temporary).resolve()
            physical=root/'physical';physical.mkdir()
            logical=root/'logical';logical.symlink_to(physical,target_is_directory=True)
            sentinel=physical/'caller-owned';sentinel.write_bytes(b'preserve incoming temp data\n')
            build=ROOT/'.mlf-build';build.mkdir(exist_ok=True)
            before=set(build.glob('benchmark-provenance.*'))
            result=subprocess.run(['bash',str(ROOT/'tools/release/check-benchmark-provenance.sh')],
                cwd=ROOT,env={**os.environ,'TMPDIR':str(logical)},
                text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
            print(result.stdout,flush=True)
            self.assertEqual(result.returncode,0,result.stdout[-12000:])
            self.assertIn('Benchmark provenance passed: all pinned hashes and 19 exact patch reconstructions.',result.stdout)
            self.assertEqual(sentinel.read_bytes(),b'preserve incoming temp data\n')
            self.assertTrue(logical.is_symlink())
            self.assertEqual(set(physical.iterdir()),{sentinel})
            self.assertEqual(set(build.glob('benchmark-provenance.*')),before)

if __name__=='__main__':unittest.main()
