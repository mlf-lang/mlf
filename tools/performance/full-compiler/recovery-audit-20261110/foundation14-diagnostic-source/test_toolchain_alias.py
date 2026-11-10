import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('diagnostic',Path(__file__).with_name('run_diagnostic.py'))
D=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(D)

class Alias(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.items={}
        for name,(relative,target) in D.TOOLCHAIN_ALIASES.items():
            p=self.root/relative;r=self.root/target
            p.parent.mkdir(parents=True,exist_ok=True);r.parent.mkdir(parents=True,exist_ok=True)
            r.write_text(name+' official tool bytes')
            p.symlink_to(os.path.relpath(r,p.parent))
            self.items[name]=dict(path=str(p),resolved_path=str(r),sha256=hashlib.sha256(r.read_bytes()).hexdigest())
        self.item=self.items['ghc'];self.p=Path(self.item['path'])
        self.expected=D.toolchain_alias('ghc',self.item,self.root)
    def test_three_declared_aliases(self):
        for name,item in self.items.items():
            r=D.toolchain_alias(name,item,self.root)
            self.assertEqual(len(r['symlink_chain']),1)
            self.assertEqual(r['resolved_path'],item['resolved_path'])
    def test_retarget_other_file(self):
        q=self.p.parent/'other';q.write_text('other');self.p.unlink();self.p.symlink_to(q.name)
        with self.assertRaises(ValueError):D.toolchain_alias('ghc',self.item,self.root,self.expected)
    def test_same_endpoint_binding_change(self):
        self.p.unlink();self.p.symlink_to('./ghc-9.14.1')
        with self.assertRaisesRegex(ValueError,'symlink binding changed'):
            D.toolchain_alias('ghc',self.item,self.root,self.expected)
    def test_broken_alias(self):
        self.p.unlink();self.p.symlink_to('missing')
        with self.assertRaises((ValueError,FileNotFoundError)):
            D.toolchain_alias('ghc',self.item,self.root,self.expected)
    def test_missing_resolved_field(self):
        item=copy.deepcopy(self.item);del item['resolved_path']
        with self.assertRaises(ValueError):D.toolchain_alias('ghc',item,self.root)
    def test_unknown_alias(self):
        with self.assertRaisesRegex(ValueError,'unknown toolchain alias'):
            D.toolchain_alias('unapproved-tool',self.item,self.root)
    def test_wrong_sha(self):
        item=copy.deepcopy(self.item);item['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'resolved SHA'):D.toolchain_alias('ghc',item,self.root)
    def test_regular_alias_substitution(self):
        self.p.unlink();self.p.write_text('same path no longer link')
        with self.assertRaises(ValueError):D.toolchain_alias('ghc',self.item,self.root)
    def test_intermediate_binding_pinned(self):
        self.p.unlink();self.p.symlink_to('indirect')
        indirect=self.p.parent/'indirect';indirect.symlink_to('ghc-9.14.1')
        expected=D.toolchain_alias('ghc',self.item,self.root)
        self.assertEqual(len(expected['symlink_chain']),2)
        indirect.unlink();indirect.symlink_to('./ghc-9.14.1')
        with self.assertRaisesRegex(ValueError,'symlink binding changed'):
            D.toolchain_alias('ghc',self.item,self.root,expected)
    def test_cycle_rejected(self):
        self.p.unlink();self.p.symlink_to('cycle')
        (self.p.parent/'cycle').symlink_to('ghc')
        with self.assertRaisesRegex(ValueError,'cycle/depth'):D.toolchain_alias('ghc',self.item,self.root)

if __name__=='__main__':unittest.main()
