#!/usr/bin/env python3
"""Exercise the real Git child and synthetic PR shapes in a disposable object database."""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import unittest
from check_benchmark_phase2_successor import ROOT, successor as s

PARENT = '8402e29040d5786d79dbcc3ccc9e8e047208c399'
SOURCE = '010508904b6882e9070ffa0cc9be9846dc22e290'
BINDER = 'tools/performance/artifact-binary/phase2_a1_overlay.py'
MANIFEST = 'tools/release/test-suites.json'
PATRICIA_MANIFEST = 'tests/external-suites.json'


class Phase2Overlay(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory(prefix='a1-overlay-test-')))
        self.git('init', '-q')
        odb = subprocess.check_output(['git','-C',str(ROOT),'rev-parse',
                 '--path-format=absolute','--git-common-dir'],text=True).strip()
        (self.root/'.git/objects/info/alternates').write_text(str(Path(odb)/'objects')+'\n')
        for k,v in [('user.name','test'),('user.email','test@example.invalid')]:
            self.git('config',k,v)
        self.head = subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
        if len(self.git('show','-s','--format=%P',self.head).split()) == 2:
            self.head = self.git('rev-parse',self.head+'^2').decode().strip()
        self.git('update-ref','--no-deref','HEAD',self.head)
        self.git('read-tree',self.head)
        self.paths = self.git('diff','--name-only',PARENT,self.head).decode().splitlines()
        self.policy = s.load_policy()
        self.git('checkout-index','--',*self.paths,*sorted(self.policy['old']))

    def git(self,*a,data=None):
        return subprocess.check_output(['git','--no-replace-objects','-C',str(self.root),*a],
                                       input=data,stderr=subprocess.PIPE)

    def commit(self,tree,*parents):
        flags = [v for p in parents for v in ('-p',p)]
        return self.git('commit-tree',tree,*flags,'-m','isolated shape probe').decode().strip()

    def tip(self):
        return s.checkout_source_tip(self.root)[1]

    def test_direct_and_unchanged_synthetic_merge(self):
        self.assertEqual(self.tip(),SOURCE)
        merge = self.commit(self.head+'^{tree}',s.MAIN,self.head)
        self.git('update-ref','--no-deref','HEAD',merge)
        self.assertEqual(self.tip(),SOURCE)

    def test_unexpected_committed_path(self):
        (self.root/'unknown').write_bytes(b'unexpected\n')
        self.git('add','unknown')
        different = self.commit(self.git('write-tree').decode().strip(),PARENT)
        self.git('update-ref','--no-deref','HEAD',different)
        with self.assertRaisesRegex(ValueError,'exact A1 maintenance overlay'):
            self.tip()

    def test_tracked_forgery_and_uncommitted_mutation(self):
        p=self.root/MANIFEST;p.write_bytes(p.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'A1 physical and tracked'):
            self.tip()
        self.git('add','--',MANIFEST)
        different=self.commit(self.git('write-tree').decode().strip(),PARENT)
        self.git('update-ref','--no-deref','HEAD',different)
        with self.assertRaisesRegex(ValueError,'only the exact A1 suite route'):
            self.tip()

    def test_patricia_route_cannot_be_relabelled(self):
        p = self.root / PATRICIA_MANIFEST
        exact = p.read_bytes()
        altered = exact.replace(b'tools/release/test_phase2_patricia_adapters.py',
                               b'tools/performance/patricia/test_adapters.py')
        self.assertNotEqual(altered, exact)
        # Keep the path modified so this tests the route binder, not only
        # the diff inventory or physical-vs-Git guard.
        p.write_bytes(altered + b'\n')
        self.git('add', '--', PATRICIA_MANIFEST)
        different = self.commit(self.git('write-tree').decode().strip(), PARENT)
        self.git('update-ref', '--no-deref', 'HEAD', different)
        with self.assertRaisesRegex(ValueError, 'only the exact Patricia suite route'):
            self.tip()

    def test_wrong_synthetic_tree(self):
        # Spare regular tracked file in the synthetic test tree, both real parents.
        (self.root/'unexpected').write_bytes(b'unexpected\n')
        self.git('add','unexpected')
        merge=self.commit(self.git('write-tree').decode().strip(),s.MAIN,self.head)
        self.git('update-ref','--no-deref','HEAD',merge)
        with self.assertRaisesRegex(ValueError,'synthetic CI merge tree'):
            self.tip()

    def test_physical_stale_or_unreviewed_input_rejected(self):
        git,tip=s.checkout_source_tip(self.root)
        p=self.root/s.INTSET
        current=p.read_bytes()
        for raw in (current+b'\n',s.parse_intset(git,current)):
            p.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'against the exact current source policy'):
                s.authenticate_c1(git,self.root,self.policy,tip)


if __name__=='__main__':
    unittest.main()
