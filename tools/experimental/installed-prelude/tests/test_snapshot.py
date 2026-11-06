"""Pure loader tests; synthetic metadata here does not claim compiler acceptance."""
import copy, json, pathlib, sys, tempfile, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from common import CONTRACTS, digest, pack, write
from snapshot import verified_bundle
class Loader(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name); self.manifest=self.root/'descriptor.json'
        self.contract={k:'test-'+k for k in CONTRACTS}; write(self.root/'shared-sources.json',self.contract)
        self.build={'root':str(self.root),'harness_sha256':'harness','pins':{'source':'digest'}}
        (self.root/'unit.mlfci').write_bytes('é😀'.encode()); (self.root/'unit.mlfco').write_bytes(b'object')
        self.descriptor={'schema':'experimental-installed-prelude-1','build_receipt_sha256':'build','harness_sha256':'harness','source_pins':self.build['pins'],'contracts':self.contract,'metadata':{'file':'unit.mlfci','sha256':digest('é😀'.encode())},'object':{'file':'unit.mlfco','sha256':digest(b'object')}}
    def store(self): write(self.manifest,self.descriptor); return digest(self.manifest.read_bytes())
    def test_valid(self): self.assertEqual(verified_bundle(self.manifest,self.store(),self.build,'build'),['é😀','object'])
    def test_external_digest(self):
        self.store()
        with self.assertRaises(ValueError): verified_bundle(self.manifest,'wrong',self.build,'build')
    def test_identity_fields(self):
        for field in ['schema','build_receipt_sha256','harness_sha256','source_pins','contracts']:
            saved=copy.deepcopy(self.descriptor); self.descriptor[field]='wrong'
            with self.assertRaises(ValueError): verified_bundle(self.manifest,self.store(),self.build,'build')
            self.descriptor=saved
    def test_tamper(self):
        expected=self.store(); (self.root/'unit.mlfco').write_bytes(b'changed')
        with self.assertRaises(ValueError): verified_bundle(self.manifest,expected,self.build,'build')
    def test_path(self):
        self.descriptor['object']['file']='../outside'
        with self.assertRaises(ValueError): verified_bundle(self.manifest,self.store(),self.build,'build')
    def test_invalid_utf8(self):
        (self.root/'unit.mlfco').write_bytes(b'\xff'); self.descriptor['object']['sha256']=digest(b'\xff')
        with self.assertRaises(UnicodeDecodeError): verified_bundle(self.manifest,self.store(),self.build,'build')
    def test_scalar_frame(self): self.assertEqual(pack(['é😀','']),b'2:\xc3\xa9\xf0\x9f\x98\x800:')
    def test_surrogate(self):
        with self.assertRaises(UnicodeEncodeError): pack(['\ud800'])
if __name__=='__main__': unittest.main()
