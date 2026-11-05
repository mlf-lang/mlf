#!/usr/bin/env python3
"""Exact role-specific header controls; no compiler or benchmark samples."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OWNER='libraries/mlf-crates/Bootstrap/CrateSession.hs'
BASELINES={
    'e123603d00f6f64e20e4d771836e49ddd808320f':
        '18abedc7f96452392ed3401f1ae607233ec13e2a5ba24bd1c0cba344820c382f',
    'ffa3d201e4ea9c08109ff00df3f4fd66b56f3ab2':
        '157b4d8d07986b1074cc612b89e2482783b3c80164db5f6dc74b1ece14fa7094',
    '5172c4ade3b3141da2e64593c383892575b36699':
        '51aeddfb084faf84019db88c634d972f48eeecd597d8070c60f59c7402454df9',
}


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


D=module(HERE/'run_controls.py','private_owner_driver')
A=module(HERE.parent/'patricia/adapt_oracles.py','private_owner_abi')
LIVE=A.LIVE_SESSION_HEADER.encode()
FIXTURES=None


class HeaderControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current=(ROOT/OWNER).read_bytes()
        cls.frozen=[]
        for ref,digest in BASELINES.items():
            raw=((FIXTURES/(ref+'.hs')).read_bytes() if FIXTURES else
                 subprocess.check_output(['git','show',ref+':'+OWNER],cwd=ROOT))
            if hashlib.sha256(raw).hexdigest()!=digest:
                raise RuntimeError('frozen private-owner SHA: '+ref)
            cls.frozen.append((ref,raw))

    def check_roundtrip(self,raw,name,header):
        changed=D.adapt_private_owner(raw,name,LIVE)
        target=('module '+name+' where {').encode()
        self.assertEqual(changed,raw.replace(header,target,1))
        self.assertEqual(changed.replace(target,header,1),raw)
        before,after=raw.split(header)
        self.assertEqual(changed,before+target+after)

    def test_all_three_frozen_owners(self):
        for ref,raw in self.frozen:
            with self.subTest(ref=ref):
                self.check_roundtrip(raw,'LegacySession',D.LEGACY_OWNER_HEADER)

    def test_complete_current_owner(self):
        self.check_roundtrip(self.current,'CandidateSession',LIVE)
        for export in (b'compileSpecFile',b'compileSpecFileWithPrelude',
                       b'compileSpecFileWithVerification'):
            self.assertIn(export,LIVE)
            self.assertIn(export,D.adapt_private_owner(self.current,'CandidateSession',LIVE))

    def test_reject_missing_duplicate_unexpected_stale_truncated_and_target(self):
        for role,raw,header,other in (
                ('CandidateSession',self.current,LIVE,D.LEGACY_OWNER_HEADER),
                *[('LegacySession',raw,D.LEGACY_OWNER_HEADER,LIVE)
                  for _,raw in self.frozen]):
            target=('module '+role+' where {').encode()
            mutations={
                'missing':raw.replace(header,b'',1),
                'duplicate':raw+b'\n'+header+b'\n',
                'unexpected':raw.replace(header,header.replace(b'Bootstrap.CrateSession',b'Other'),1),
                'stale-or-wrong-role':raw.replace(header,other,1),
                'truncated':raw.replace(header,header[:-1],1),
                'preexisting-target':raw+b'\n'+target+b'\n',
                'preexisting-target-exports':raw+b'\nmodule '+role.encode()+b' (x) where {\n',
                'preexisting-target-indented':raw+b'\n  module '+role.encode()+b' (x) where {\n',
                'mixed-owner-headers':raw+b'\n'+other+b'\n',
                'comment-only':raw.replace(header,b'-- '+header,1),
                'suffix':raw.replace(header,header+b' unexpected',1),
            }
            for label,bad in mutations.items():
                with self.subTest(role=role,case=label):
                    with self.assertRaises(RuntimeError):
                        D.adapt_private_owner(bad,role,LIVE)

    def test_reject_incomplete_or_reordered_current_exports(self):
        for bad in (LIVE.replace(b', compileSpecFileWithPrelude',b''),
                    LIVE.replace(b', compileSpecFileWithVerification',b''),
                    LIVE.replace(b'compileSpecFileWithPrelude, compileSpecFileWithVerification',
                                 b'compileSpecFileWithVerification, compileSpecFileWithPrelude')):
            with self.subTest(header=bad):
                with self.assertRaises(RuntimeError):
                    D.adapt_private_owner(self.current.replace(LIVE,bad,1),'CandidateSession',LIVE)

    def test_reject_unknown_role_and_nonbyte_inputs(self):
        for raw,role,header in ((self.current,'OtherSession',LIVE),
                                (self.current.decode(),'CandidateSession',LIVE),
                                (self.current,'CandidateSession',LIVE.decode()),
                                (self.current,'CandidateSession',b'')):
            with self.subTest(role=role,header=header):
                with self.assertRaises(RuntimeError):
                    D.adapt_private_owner(raw,role,header)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-fixtures',type=Path,
                        help='explicit SHA-checked offline baseline files named <commit>.hs')
    args=parser.parse_args()
    FIXTURES=args.frozen_fixtures
    unittest.main(argv=[__file__],verbosity=2)
