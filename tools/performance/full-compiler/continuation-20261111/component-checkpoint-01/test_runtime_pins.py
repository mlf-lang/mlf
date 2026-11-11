import copy
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
import runtime_pins as R


def elf(loader):
    interp=str(loader).encode()+b'\0'
    head=bytearray(64);head[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<Q',head,32,64);struct.pack_into('<HH',head,54,56,1)
    ph=struct.pack('<IIQQQQQQ',3,0,120,0,0,len(interp),len(interp),1)
    return bytes(head)+ph+interp

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.loader=self.root/'loader';self.loader.write_bytes(b'fake loader')
        self.lib=self.root/'lib';self.lib.write_bytes(b'fake library')
        self.exe=self.root/'exe';self.exe.write_bytes(elf(self.loader))
        self.cache=self.root/'cache';self.cache.write_bytes(b'cache')
        self.cfg=self.root/'conf.d';self.cfg.mkdir();(self.cfg/'a.conf').write_text('/lib')
        self.kw=dict(config_paths=[str(self.cache)],config_dirs=[str(self.cfg)])
    def callback(self,argv):
        self.assertEqual(argv,[str(self.loader),'--list',str(self.exe)])
        return dict(returncode=0,stderr='',stdout=f'linux-vdso.so.1 (0x12)\nlib.so => {self.lib} (0x23)\n{self.loader} (0x34)\n',auth={'synthetic':True})
    def test_runtime_roundtrip(self):
        pin=R.pin_runtime(self.exe,self.callback,**self.kw);self.assertEqual(R.verify_runtime(pin,self.callback),pin)
    def test_interpreter(self):self.assertEqual(R.interpreter(self.exe),str(self.loader))
    def test_script_rejected(self):
        self.exe.write_bytes(b'#!/bin/sh\n')
        with self.assertRaises(ValueError):R.interpreter(self.exe)
    def test_truncated_elf(self):
        self.exe.write_bytes(self.exe.read_bytes()[:70])
        with self.assertRaises(ValueError):R.interpreter(self.exe)
    def test_elf_missing_interp(self):
        data=bytearray(self.exe.read_bytes());struct.pack_into('<I',data,64,1);self.exe.write_bytes(data)
        with self.assertRaises(ValueError):R.interpreter(self.exe)
    def test_alias(self):
        alias=self.root/'alias';alias.symlink_to(self.lib.name);pin=R.binding(alias)
        self.assertEqual(pin['resolved'],str(self.lib));self.assertEqual(pin['links'][0]['target'],'lib')
        alias.unlink();alias.symlink_to(self.loader.name);self.assertNotEqual(R.binding(alias),pin)
    def test_alias_parent(self):
        folder=self.root/'dir';folder.mkdir();(folder/'f').write_text('x');alias=self.root/'d';alias.symlink_to('dir')
        self.assertEqual(len(R.binding(alias/'f')['links']),1)
    def test_alias_cycle(self):
        alias=self.root/'cycle';alias.symlink_to('cycle')
        with self.assertRaises(ValueError):R.binding(alias)
    def test_runtime_drift(self):
        pin=R.pin_runtime(self.exe,self.callback,**self.kw);self.lib.write_bytes(b'changed')
        with self.assertRaises(ValueError):R.verify_runtime(pin,self.callback)
    def test_new_config_file(self):
        pin=R.pin_runtime(self.exe,self.callback,**self.kw);(self.cfg/'new.conf').write_text('/extra')
        with self.assertRaises(ValueError):R.verify_runtime(pin,self.callback)
    def test_bad_callback(self):
        for mutation in ({'returncode':124},{'stderr':'error'},{'auth':{}},{'stdout':'lib.so => not found'}):
            def run(argv):out=self.callback(argv);out.update(mutation);return out
            with self.assertRaises(ValueError):R.pin_runtime(self.exe,run,**self.kw)
    def test_loader_duplicate(self):
        with self.assertRaises(ValueError):R.loader_paths(f'{self.loader} (0x12)\n{self.loader} (0x12)')
    def test_missing_loader(self):
        def run(argv):out=self.callback(argv);out['stdout']=f'lib.so => {self.lib} (0x12)';return out
        with self.assertRaises(ValueError):R.pin_runtime(self.exe,run,**self.kw)
    def packages(self):
        names=R.PACKAGES+['extra'+str(i) for i in range(17)];conf={};texts=[]
        for i,name in enumerate(names):
            unit=name+'-1';directory=self.root/unit;directory.mkdir();(directory/'M.hi').write_bytes(b'hi');(directory/'M.p_hi').write_bytes(b'profile hi');(directory/('libHS'+unit+'_p.a')).write_bytes(b'archive')
            deps=' '.join(n+'-1' for n in names[6:]) if i==0 else ''
            text=f'name: {name}\nid: {unit}\ndepends: {deps}\nhs-libraries: HS{unit}\nlibrary-dirs: {directory}\nimport-dirs: {directory}\n'
            path=self.root/(unit+'.conf');path.write_text(text);conf[unit]=str(path);texts.append(text)
        dump=self.root/'packages.txt';dump.write_text('---\n'.join(texts))
        return dump,hashlib.sha256(dump.read_bytes()).hexdigest(),conf
    def test_package_full_closure(self):
        args=self.packages();pin=R.profile_packages(*args,pkgroot=self.root)
        self.assertEqual(len(pin['units']),23);self.assertEqual(sum(len(u['interfaces']) for u in pin['units']),23)
    def test_package_wrong_hash(self):
        dump,sha,conf=self.packages()
        with self.assertRaises(ValueError):R.profile_packages(dump,'0'*64,conf,pkgroot=self.root)
    def test_missing_profile_hi(self):
        args=self.packages();(self.root/'base-1/M.p_hi').unlink()
        with self.assertRaises(ValueError):R.profile_packages(*args,pkgroot=self.root)
    def test_missing_profile_archive(self):
        args=self.packages();(self.root/'base-1/libHSbase-1_p.a').unlink()
        with self.assertRaises(ValueError):R.profile_packages(*args,pkgroot=self.root)
    def test_config_mismatch(self):
        args=self.packages();path=Path(args[2]['base-1']);path.write_text(path.read_text().replace('HSbase','HSwrong'))
        with self.assertRaises(ValueError):R.profile_packages(*args,pkgroot=self.root)
    def test_duplicate_fields(self):
        with self.assertRaises(ValueError):R.package_records('id: x\nid: y\n')

if __name__=='__main__':unittest.main()
