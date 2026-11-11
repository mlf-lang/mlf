import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
import mirror

SOURCE = Path(os.environ.get('ASTRA_FROZEN_SOURCE', str(Path(__file__).resolve().parent.parent / 'source')))

class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mirror-test-', dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / 'mirror'
    def prepare(self): return mirror.prepare(SOURCE, self.output)
    def test_exact_reversible_inventory(self):
        m = self.prepare()
        self.assertEqual(len(m['files']),97)
        self.assertEqual(len(m['union']),95)
        self.assertEqual(len(m['emlf_modules']),94)
        self.assertEqual(len(m['generator_modules']),60)
        self.assertEqual(len(set(m['emlf_modules']) | set(m['generator_modules'])),95)
        self.assertEqual(len(set(m['mains'].values())),2)
        self.assertEqual(mirror.verify_mirror(SOURCE,self.output),m)
        for rel in m['files']:
            self.assertEqual(mirror.inverse_bytes(rel,(self.output/rel).read_bytes()),(SOURCE/rel).read_bytes())
        self.assertGreater(sum(e['occurrences'] for e in m['files'].values()),20)
    def test_source_pin_rejects_changed_input(self):
        rel=next(iter(mirror.specification()['pins']))
        with self.assertRaisesRegex(mirror.MirrorError,'frozen source'):
            mirror.transform(rel,(SOURCE/rel).read_bytes()+b' ')
    def test_modified_mirror_rejected(self):
        m=self.prepare(); p=self.output/next(iter(m['files'])); p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaises(mirror.MirrorError):mirror.verify_mirror(SOURCE,self.output)
    def test_missing_annotation_rejected(self):
        rel=next(iter(mirror.specification()['edits']))
        with self.assertRaises(mirror.MirrorError):mirror.inverse_bytes(rel,(SOURCE/rel).read_bytes())
    def test_stale_destination_rejected(self):
        self.output.mkdir()
        with self.assertRaises(mirror.MirrorError):self.prepare()
    def test_symlink_destination_rejected(self):
        self.output.symlink_to(SOURCE,target_is_directory=True)
        with self.assertRaises(mirror.MirrorError):self.prepare()
    def test_symlink_parent_rejected(self):
        link=Path(self.tmp.name)/'link';link.symlink_to(SOURCE,target_is_directory=True)
        with self.assertRaises(mirror.MirrorError):mirror.prepare(SOURCE,link/'forbidden')
    def test_symlink_source_rejected(self):
        link=Path(self.tmp.name)/'link';link.symlink_to(SOURCE,target_is_directory=True)
        with self.assertRaises(mirror.MirrorError):mirror.prepare(link,self.output)
        self.assertFalse(self.output.exists())
    def test_source_nested_destination_rejected(self):
        with self.assertRaises(mirror.MirrorError):mirror.prepare(SOURCE,SOURCE/'forbidden-mirror')
    def records(self,m,role):
        spec=mirror.specification(); names=spec['emlf_modules'] if role=='emlf' else spec['generator_modules']
        expected={n:spec['union'][n] for n in names};expected['Main']=mirror.MAINS[role]
        return [{'module':n,'source':str(self.output/p),'object':n+'.p_o','interface':n+'.p_hi'} for n,p in expected.items()]
    def test_both_actual_closures(self):
        m=self.prepare()
        for role in mirror.MAINS:self.assertTrue(mirror.validate_provenance(self.records(m,role),m,role))
    def test_duplicate_missing_extra_ordinary_wrong_main(self):
        m=self.prepare(); rows=self.records(m,'emlf')
        for mutation in ('duplicate','missing','extra','ordinary','main','source'):
            r=copy.deepcopy(rows)
            if mutation=='duplicate':r[-1]=r[0]
            elif mutation=='missing':r.pop()
            elif mutation=='extra':r.append(r[0])
            elif mutation=='ordinary':r[0]['object']='ordinary.o'
            elif mutation=='main':r[-1]['source']=str(self.output/mirror.MAINS['builtin-prelude'])
            else:r[0]['source']=str(SOURCE/mirror.specification()['union'][r[0]['module']])
            with self.subTest(mutation=mutation),self.assertRaises(mirror.MirrorError):mirror.validate_provenance(r,m,'emlf')
    def test_union_and_separate_main_provenance(self):
        m=self.prepare()
        rows=self.records(m,'emlf')[:-1] + [r for r in self.records(m,'builtin-prelude') if r['module']=='MLF.Entry.BuiltinPrelude']
        self.assertTrue(mirror.validate_provenance(rows,m,'union'))
        for role in mirror.MAINS:
            self.assertTrue(mirror.validate_provenance([self.records(m,role)[-1]],m,role+'-main'))
        with self.assertRaises(mirror.MirrorError):mirror.validate_provenance(rows+[self.records(m,'emlf')[-1]],m,'union')
    def test_manifest_inventory_tamper(self):
        self.prepare();p=self.output/'mirror-manifest.json';m=json.loads(p.read_text());m['union'].pop(next(iter(m['union'])));p.write_text(json.dumps(m))
        with self.assertRaises(mirror.MirrorError):mirror.verify_mirror(SOURCE,self.output)
if __name__=='__main__':unittest.main()
