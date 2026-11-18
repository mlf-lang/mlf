"""Exact-child wait4 measurement; containment belongs to enclosing subreaper."""
import json,os,sys,time
from pathlib import Path
def main():
    destination=Path(sys.argv[1]);command=sys.argv[2:]
    if destination.exists() or not command or not os.path.isabs(command[0]):raise RuntimeError('fresh metric and absolute executable required')
    started=time.monotonic_ns();pid=os.fork()
    if pid==0:
        try:os.execve(command[0],command,os.environ)
        except BaseException as e:
            os.write(2,('exec failed: '+repr(e)+'\n').encode());os._exit(127)
    while True:
        try:got,status,usage=os.wait4(pid,0);break
        except InterruptedError:continue
    ended=time.monotonic_ns()
    if got!=pid:raise RuntimeError('wrong child reaped')
    code=os.waitstatus_to_exitcode(status)
    record=dict(complete=code==0,pid=pid,raw_wait_status=status,exit_code=code,wall_ns=ended-started,
                user_seconds=usage.ru_utime,system_seconds=usage.ru_stime,maxrss_KiB=usage.ru_maxrss,
                boundary='fork/exec through exact child wait4; Linux process peak, not tree RSS sum')
    with destination.open('x')as f:json.dump(record,f);f.write('\n')
    return code if code>=0 else 128-code
if __name__=='__main__':sys.exit(main())


