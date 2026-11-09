#!/usr/bin/env python3
import unittest,types,json,subprocess,sys,tempfile,os,time
from pathlib import Path
p=Path(__file__).with_name('driver.py');m=types.ModuleType('driver');m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__)
class Selection(unittest.TestCase):
    def test_exact_compile(self):
        self.assertEqual(m.selection(['-O2','-c','a.ll','-o','a.o']),((2,Path('a.ll')),Path('a.o')))
    def test_other_contracts_passthrough(self):
        for args in [['-O0','-c','a.ll','-o','a.o'],['-O2','a.ll','-o','a'],['-O2','-c','a.c','-o','a.o'],['-O2','-c','a.ll','b.ll','-o','a.o'],['-O2','-c','a.ll','-o','a.o','-fprofile-generate'],['@args'],['-O2','-c','a.ll','-o','a.o','-o','b.o']]:
            with self.subTest(args=args):self.assertIsNone(m.selection(args))
class FailureCleanup(unittest.TestCase):
    def test_failed_part_kills_other_process_groups_and_keeps_old_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            driver=root/'driver.py';driver.write_bytes(p.read_bytes())
            helper=root/'helper';helper.write_text("#!/usr/bin/env python3\nimport pathlib,sys\nfor i in range(int(sys.argv[3])):pathlib.Path(sys.argv[2]+str(i)+'.bc').write_text('part')\n");helper.chmod(0o755)
            clang=root/'clang'
            clang.write_text("#!/usr/bin/env python3\nimport pathlib,subprocess,sys,time\np=pathlib.Path(__file__).parent\nif any('part-0.bc' in a for a in sys.argv):\n c=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n (p/'child.pid').write_text(str(c.pid))\n time.sleep(60)\nelse:\n while not (p/'child.pid').exists():time.sleep(.01)\n sys.exit(7)\n");clang.chmod(0o755)
            config={'clang':{'path':str(clang)},'helper':{'path':str(helper)},'jobs':2,'timeout_seconds':5}
            (root/'driver.json').write_text(json.dumps(config));source=root/'source.ll';source.write_text('ir')
            output=root/'out.o';output.write_bytes(b'old object')
            started=time.monotonic()
            result=subprocess.run([sys.executable,str(driver),'-O2','-c',str(source),'-o',str(output)],capture_output=True,timeout=8)
            self.assertNotEqual(result.returncode,0)
            self.assertLess(time.monotonic()-started,5)
            self.assertEqual(output.read_bytes(),b'old object')
            self.assertFalse(json.loads((root/'out.o.parallel.json').read_text())['complete'])
            child=int((root/'child.pid').read_text())
            state=subprocess.run(['ps','-p',str(child),'-o','state='],capture_output=True,text=True).stdout.strip()
            self.assertTrue(not state or state.startswith('Z'),state)
            self.assertFalse(list(root.glob('.mlf-parallel-*')))

    def test_sigterm_between_spawn_and_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);driver=root/'driver.py'
            injected="""
_original_popen=subprocess.Popen
def _signal_during_spawn(*args,**kwargs):
    child=_original_popen(*args,**kwargs)
    Path(__file__).with_name('spawned.pid').write_text(str(child.pid))
    os.kill(os.getpid(),signal.SIGTERM)
    time.sleep(.05)
    return child
subprocess.Popen=_signal_during_spawn
"""
            source_code=p.read_text().replace("if __name__=='__main__':main()",injected+"\nif __name__=='__main__':main()")
            driver.write_text(source_code)
            helper=root/'helper';helper.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(60)\n');helper.chmod(0o755)
            (root/'driver.json').write_text(json.dumps({'clang':{'path':str(helper)},'helper':{'path':str(helper)},'jobs':2,'timeout_seconds':5}))
            source=root/'a.ll';source.write_text('ir');output=root/'a.o'
            result=subprocess.run([sys.executable,str(driver),'-O2','-c',str(source),'-o',str(output)],capture_output=True,timeout=3)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(output.exists())
            self.assertFalse(json.loads((root/'a.o.parallel.json').read_text())['complete'])
            child=int((root/'spawned.pid').read_text())
            state=subprocess.run(['ps','-p',str(child),'-o','state='],capture_output=True,text=True).stdout.strip()
            self.assertTrue(not state or state.startswith('Z'),state)

if __name__=='__main__':unittest.main()
