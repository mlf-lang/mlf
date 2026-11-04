"""Synthetic preflight controls, not evidence of ordinary checked source origin."""
import hashlib,importlib.util,json,pathlib,shutil,subprocess,sys,tempfile,unittest
BASE=pathlib.Path(__file__).resolve().parents[1]
class Preflight(unittest.TestCase):
    def copy(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        target=pathlib.Path(temp.name)/'copy';shutil.copytree(BASE,target,ignore=shutil.ignore_patterns('build','__pycache__'))
        return target
    def run_import(self,target,code='import run_native'):
        if 'prepare.build_identity()' in code:code='import prepare; from pathlib import Path; prepare.ROOT=Path('+repr(str(BASE.parents[2]))+'); '+code
        return subprocess.run([sys.executable,'-c',code],cwd=target,capture_output=True,text=True,timeout=10)
    def test_changed_transport_never_executes(self):
        t=self.copy();sentinel=t/'executed';(t/'transport.py').write_text('from pathlib import Path\nPath('+repr(str(sentinel))+').write_text("bad")\n')
        r=self.run_import(t);self.assertNotEqual(r.returncode,0);self.assertIn('transport changed before',r.stderr);self.assertFalse(sentinel.exists())
    def test_changed_codegen_never_executes(self):
        t=self.copy();sentinel=t/'executed';(t/'codegen.py').write_text('from pathlib import Path\nPath('+repr(str(sentinel))+').write_text("bad")\n')
        r=self.run_import(t);self.assertNotEqual(r.returncode,0);self.assertIn('codegen changed before',r.stderr);self.assertFalse(sentinel.exists())
    def test_empty_forged_receipt_rejected(self):
        t=self.copy();p=t/'validation/compiler-build.json';r=json.loads(p.read_text());r['inputs']={};p.write_text(json.dumps(r))
        x=self.run_import(t,'import prepare; prepare.build_identity()');self.assertNotEqual(x.returncode,0);self.assertIn('missing/changed source inventory',x.stderr)
    def test_changed_source_manifest_rejected(self):
        t=self.copy();p=t/'provenance/current-target-source.json';r=json.loads(p.read_text());r['source_commit']='0'*40;p.write_text(json.dumps(r))
        x=self.run_import(t,'import prepare; prepare.build_identity()');self.assertNotEqual(x.returncode,0);self.assertIn('pinned current-target source manifest changed',x.stderr)
    def test_changed_kernel_before_import(self):
        t=self.copy();sentinel=t/'executed';(t/'resource_ir/checker.py').write_text('from pathlib import Path\nPath('+repr(str(sentinel))+').write_text("bad")\n')
        x=self.run_import(t,'import prepare; prepare.frozen_reference()');self.assertNotEqual(x.returncode,0);self.assertIn('accepted resource kernel changed',x.stderr);self.assertFalse(sentinel.exists())
    def test_changed_native_gate_rejected(self):
        t=self.copy();lock_path=t/'validation/native-runtime-lock.json';lock=json.loads(lock_path.read_text())
        self.assertEqual(lock['audit_receipt'],'provenance/NATIVE_LIFECYCLE_ACCEPTANCE.json')
        p=t/lock['audit_receipt'];receipt=json.loads(p.read_text())
        self.assertEqual(receipt['schema'],'terminal-destroy-native-independent-acceptance/1')
        self.assertEqual(receipt['identity'],'resource-ir-terminal-destroy/1')
        self.assertEqual(receipt['verdict'],'ACCEPTED_BOUNDED_OPT_IN_LIFECYCLE')
        receipt['verdict']='TEST_ONLY_REJECTED';p.write_text(json.dumps(receipt))
        x=self.run_import(t,'import run_native; run_native.native_identity()');self.assertNotEqual(x.returncode,0);self.assertIn('native lifecycle lock does not name pinned independent receipt',x.stderr)
        # Synthetic authority in this copied-test subprocess ONLY: prove the
        # semantic verdict check also rejects even after matching both digests.
        digest=hashlib.sha256(p.read_bytes()).hexdigest();lock['audit_receipt_sha256']=digest;lock_path.write_text(json.dumps(lock))
        code='import run_native; run_native.NATIVE_ACCEPTANCE_SHA256='+repr(digest)+'; run_native.native_identity()'
        x=self.run_import(t,code);self.assertNotEqual(x.returncode,0);self.assertIn('native lifecycle acceptance differs',x.stderr)
    def test_missing_inferred_interfaces_rejected(self):
        t=self.copy();p=t/'validation/compiler-build.json';r=json.loads(p.read_text());r.pop('inferred_shared_interfaces');p.write_text(json.dumps(r))
        code='from pathlib import Path; import prepare; prepare.ROOT=Path('+repr(str(BASE.parents[2]))+'); prepare.build_identity()'
        x=self.run_import(t,code);self.assertNotEqual(x.returncode,0);self.assertIn('inferred-interface inventory differs',x.stderr)
    def test_rehashed_host_literal_overloading_rejected(self):
        t=self.copy();p=t/'validation/compiler-build.json';r=json.loads(p.read_text());item=r['inferred_shared_interfaces']['MLF.ResourceExport']
        item['signatures']='  bad :: IsString e => Either e ()\n';item['sha256']=hashlib.sha256(item['signatures'].encode()).hexdigest();p.write_text(json.dumps(r))
        code='from pathlib import Path; import prepare; prepare.ROOT=Path('+repr(str(BASE.parents[2]))+'); prepare.build_identity()'
        x=self.run_import(t,code);self.assertNotEqual(x.returncode,0);self.assertIn('unresolved host literal overloading',x.stderr)
    def test_stale_inferred_signature_hash_rejected(self):
        t=self.copy();p=t/'validation/compiler-build.json';r=json.loads(p.read_text());r['inferred_shared_interfaces']['MLF.ResourceExport']['sha256']='0'*64;p.write_text(json.dumps(r))
        code='from pathlib import Path; import prepare; prepare.ROOT=Path('+repr(str(BASE.parents[2]))+'); prepare.build_identity()'
        x=self.run_import(t,code);self.assertNotEqual(x.returncode,0);self.assertIn('inferred-interface evidence differs',x.stderr)
if __name__=='__main__':unittest.main()
