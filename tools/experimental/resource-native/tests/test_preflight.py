"""Synthetic preflight controls, not evidence of ordinary checked source origin."""
import hashlib,importlib.util,json,pathlib,shutil,subprocess,sys,tempfile,unittest
BASE=pathlib.Path(__file__).resolve().parents[1]
class Preflight(unittest.TestCase):
    def copy(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        target=pathlib.Path(temp.name)/'copy';shutil.copytree(BASE,target,ignore=shutil.ignore_patterns('build','__pycache__'))
        return target
    def run_import(self,target,code='import run_native'):
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
        t=self.copy();p=t/'provenance/pr25-source.json';r=json.loads(p.read_text());r['source_commit']='0'*40;p.write_text(json.dumps(r))
        x=self.run_import(t,'import prepare; prepare.build_identity()');self.assertNotEqual(x.returncode,0);self.assertIn('pinned PR25 source manifest changed',x.stderr)
    def test_changed_kernel_before_import(self):
        t=self.copy();sentinel=t/'executed';(t/'resource_ir/checker.py').write_text('from pathlib import Path\nPath('+repr(str(sentinel))+').write_text("bad")\n')
        x=self.run_import(t,'import prepare; prepare.frozen_reference()');self.assertNotEqual(x.returncode,0);self.assertIn('accepted resource kernel changed',x.stderr);self.assertFalse(sentinel.exists())
    def test_changed_native_gate_rejected(self):
        t=self.copy();p=t/'provenance/NATIVE_RUNTIME_ACCEPTANCE.json';p.write_text('{}')
        x=self.run_import(t,'import run_native; run_native.native_identity()');self.assertNotEqual(x.returncode,0);self.assertIn('pinned accepted receipt',x.stderr)
if __name__=='__main__':unittest.main()
