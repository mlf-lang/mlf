"""Bounded synthetic checks only; parent allows five seconds for this whole entry."""
import contextlib,io,json,subprocess,sys
from pathlib import Path
import checker_selftest
H=Path(__file__).resolve().parent
def main():
    root=Path(sys.argv[1]);buffer=io.StringIO()
    with contextlib.redirect_stdout(buffer):checker_selftest.main()
    summary=json.loads(buffer.getvalue());cases=summary['cases']
    tests=root/'measurement';tests.mkdir()
    def run(name,command):
        metric=tests/(name+'.json')
        r=subprocess.run([sys.executable,'-B',str(H/'measure.py'),str(metric)]+command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=1)
        return r,metric
    r,p=run('success',[sys.executable,'-c','pass']);m=json.loads(p.read_text())
    assert r.returncode==0 and m['complete']and m['raw_wait_status']==0 and m['wall_ns']>0 and m['maxrss_KiB']>0;cases.append('wait4-success')
    r,p=run('nonzero',[sys.executable,'-c','raise SystemExit(7)']);m=json.loads(p.read_text())
    assert r.returncode==7 and not m['complete']and m['exit_code']==7;cases.append('wait4-nonzero')
    r,p=run('execfail',[str(tests/'missing-executable')]);m=json.loads(p.read_text())
    assert r.returncode==127 and not m['complete']and m['exit_code']==127 and b'exec failed' in r.stderr;cases.append('wait4-exec-failure')
    receipt=tests/'timeout-supervisor.json';metric=tests/'timeout-metric.json'
    command=[sys.executable,'-B',str(H/'crc_process_supervisor.py'),'--receipt',str(receipt),'--work-seconds','0.15','--cleanup-seconds','0.5',sys.executable,'-B',str(H/'measure.py'),str(metric),sys.executable,'-c','import os,time;os.setsid();time.sleep(2)']
    r=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=2)
    data=json.loads(receipt.read_text())
    assert r.returncode!=0 and data['phase']=='terminal'and data['cleanup_complete']is True and data['survivors']==[] and data['signals'] and not metric.exists()
    assert len(data['reaped'])>=2;cases.append('wait4-timeout-adoption-cleaned')
    print(json.dumps(dict(complete=True,cases=cases,compiler_executed=False)))
if __name__=='__main__':main()

