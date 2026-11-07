import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
import prepared_input_transition as t

class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.old = {p: ('old:'+p).encode() for p in t.CHANGED_SOURCES}
        self.new = {p: ('new:'+p).encode() for p in t.CHANGED_SOURCES}
        self.old['untouched'] = self.new['untouched'] = b'frozen'
        def lock(values):
            return json.dumps({'packages':[{'path':'libraries/mlf-crates', 'sources':{
                p.removeprefix('libraries/mlf-crates/'): t.sha(values[p])
                for p in sorted(t.CHANGED_SOURCES)}}]}).encode()
        self.old['mlf.lock'], self.new['mlf.lock'] = lock(self.old), lock(self.new)
        self.pins={p:(t.sha(self.old[p]),t.sha(self.new[p])) for p in t.CHANGED_SOURCES|{'mlf.lock'}}
    def check(self,new=None,pins=None):
        t.validate_projection(self.new if new is None else new,self.old,self.pins if pins is None else pins)
    def test_valid(self): self.check()
    def test_wrong_pin(self):
        pins=copy.deepcopy(self.pins);pins['mlf.lock']=('0'*64,pins['mlf.lock'][1])
        with self.assertRaises(ValueError):self.check(pins=pins)
    def test_unrelated_change(self):
        new=dict(self.new,untouched=b'altered')
        with self.assertRaises(ValueError):self.check(new)
    def test_missing_member(self):
        new=dict(self.new);del new['untouched']
        with self.assertRaises(ValueError):self.check(new)
    def test_stale_lock_even_if_rehashed(self):
        new=dict(self.new);new['mlf.lock']=self.old['mlf.lock']
        pins=dict(self.pins);pins['mlf.lock']=(t.sha(new['mlf.lock']),)*2
        with self.assertRaises(ValueError):self.check(new,pins)
    def test_half_updated_lock_even_if_rehashed(self):
        new=dict(self.new);lock=json.loads(new['mlf.lock']);name=next(iter(lock['packages'][0]['sources']))
        lock['packages'][0]['sources'][name]=json.loads(self.old['mlf.lock'])['packages'][0]['sources'][name]
        new['mlf.lock']=json.dumps(lock).encode();pins=dict(self.pins);pins['mlf.lock']=(self.pins['mlf.lock'][0],t.sha(new['mlf.lock']))
        with self.assertRaises(ValueError):self.check(new,pins)
    def test_duplicate_json(self):
        with self.assertRaises(ValueError):t.strict_json(b'{"x":1,"x":2}')
    def test_original_parent_traversal_never_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=root/'a';a.mkdir();real=root/'real';real.mkdir()
            (root/'file').write_bytes(b'collapsed');(a/'file').write_bytes(b'normalized')
            (a/'link').symlink_to(real,target_is_directory=True)
            raw=str(a)+'/link/../file'
            self.assertEqual(Path(raw).read_bytes(),b'collapsed')
            with self.assertRaisesRegex(ValueError,'parent traversal'):
                t.read_regular(raw,1024)
    def test_bounded_file_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'file';p.write_bytes(b'abc')
            self.assertEqual(t.read_regular(p,3),b'abc')
            with self.assertRaises(ValueError):t.read_regular(p,2)
            link=root/'link';link.symlink_to(p)
            with self.assertRaises(ValueError):t.read_regular(link,3)
            fifo=root/'fifo';os.mkfifo(fifo)
            with self.assertRaises(ValueError):t.read_regular(fifo,3)
            directory=root/'d';directory.mkdir();(directory/'file').write_bytes(b'abc')
            (root/'parent-link').symlink_to(directory,target_is_directory=True)
            with self.assertRaises(ValueError):t.read_regular(root/'parent-link'/'file',3)

if __name__=='__main__':unittest.main()
