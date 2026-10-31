#!/usr/bin/env python3
"""Adversarial native driver deadline, cancellation and descendant cleanup."""
import argparse,json,os,signal,subprocess,tempfile,time
from pathlib import Path

def state(pid):
    return subprocess.run(['ps','-p',str(pid),'-o','state='],capture_output=True,text=True).stdout.strip()

def main():
    p=argparse.ArgumentParser();p.add_argument('--install',type=Path,required=True);a=p.parse_args()
    installed=json.loads((a.install/'driver.json').read_text());helper=installed['helper']['path']
    for mode in ['failure','signal','timeout']:
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);fake=root/'clang'
            fake.write_text('''#!/usr/bin/env python3
import pathlib,subprocess,sys,time
root=pathlib.Path(__file__).parent
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
name=pathlib.Path(sys.argv[sys.argv.index('-o')+1]).stem
(root/(name+'.pid')).write_text(str(child.pid))
mode=(root/'mode').read_text()
if mode=='failure':sys.exit(7)
time.sleep(60)
''');fake.chmod(0o755);(root/'mode').write_text(mode)
            config={**installed,'clang':{'path':str(fake)},'jobs':2,'timeout_seconds':1 if mode=='timeout' else 5}
            settings=root/'driver.json';settings.write_text(json.dumps(config));source=root/'source.ll';source.write_text('define i32 @main() { ret i32 0 }\n')
            output=root/'program.o';output.write_bytes(b'old object')
            process=subprocess.Popen([helper,'--driver',str(settings),'-O2','-c',str(source),'-o',str(output)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            if mode=='signal':
                deadline=time.monotonic()+3
                while not list(root.glob('*.pid')) and time.monotonic()<deadline:time.sleep(.005)
                os.kill(process.pid,signal.SIGTERM)
            stdout,stderr=process.communicate(timeout=5)
            assert process.returncode!=0,(mode,stdout,stderr)
            assert output.read_bytes()==b'old object'
            receipt=json.loads((root/'program.o.parallel.json').read_text());assert not receipt['complete']
            assert not list(root.glob('.mlf-parallel-*'))
            children=list(root.glob('*.pid'));assert children,mode
            for child in children:
                status=state(int(child.read_text()));assert not status or status.startswith('Z'),(mode,status)
    print('native failed-leader descendants, SIGTERM and deadline cleanup passed')
if __name__=='__main__':main()
