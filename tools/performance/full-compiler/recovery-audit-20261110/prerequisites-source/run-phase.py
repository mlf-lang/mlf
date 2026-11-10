#!/usr/bin/env python3
"""Fixed one-use 300-second prerequisite launcher. Requires exact admitted JSON.

No compiler invocation outside original watchdog. Locks are held across all
commands, authentication, checks and cross-session cleanup. Failed work remains.
"""
from pathlib import Path
import argparse
from contextlib import ExitStack
import fcntl
import importlib.util
import math
import os
import signal
import subprocess
import sys
import time

spec = importlib.util.spec_from_file_location('prerequisite_controller',Path(__file__).with_name('controller.py'))
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
SHARED = Path('/workspace/shared/mlf-astra-heavy.lock')


def table():
    result = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            v = (path/'stat').read_text().split(') ',1)[1].split()
            result[int(path.name)] = dict(ppid=int(v[1]),pgid=int(v[2]),session=int(v[3]),starttime=v[19],state=v[0])
        except (FileNotFoundError,ProcessLookupError,PermissionError):
            pass
    return result


def owned_rows(rows, tracked, leader, leader_start):
    owned = {pid for pid,v in tracked.items() if pid in rows and rows[pid]['starttime'] == v['starttime']}
    if leader in rows and rows[leader]['starttime'] == leader_start:
        owned.add(leader)
    while True:
        new = {pid for pid,v in rows.items() if v['ppid'] in owned}-owned
        if not new:
            break
        owned |= new
    for pid in owned:
        tracked[pid] = rows[pid]
    return {pid:rows[pid] for pid in owned if rows[pid]['state'] != 'Z'}


def run(admission_path, admission_sha):
    C.reject_instrumentation(os.environ)  # Membership, never truthiness, before sanitizing.
    # Acquire the common lock before admission or workspace writes. No wait/retry.
    with SHARED.open('a+') as shared:
        fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB)
        started = time.monotonic_ns(); deadline = started+300*10**9
        a,plan,pins = C.validate_admission(admission_path,admission_sha)
        C.absent(C.WORKSPACE)
        H = C.module(C.HELPER,C.FIXED[str(C.HELPER)],'original_serial_lock')
        runtime = C.module(C.RUNTIME,C.FIXED[str(C.RUNTIME)],'original_runtime')
        environment = runtime.target_environment(Path(a['runtime_library_dir']))
        python = a['python']
        with ExitStack() as locks:
            lock_roots = [C.SOURCE/'.mlf-build',Path(a['producer']).parent]
            for root in lock_roots:
                C.require(root.is_dir(), 'original lock parent missing')
                locks.enter_context(H.SerialLock(root))
            C.WORKSPACE.mkdir(mode=0o700)
            seconds = min(300,math.ceil(C.remaining(deadline,300)))
            child = [python,'-B',str(C.SCOPE),python,'-B',str(C.HERE/'controller.py'),
                     '--admission',str(admission_path),'--admission-sha256',admission_sha,
                     '--deadline-monotonic-ns',str(deadline)]
            command = [python,'-B',str(C.WATCHDOG),'--seconds',str(seconds),'--address-space-mib','6144',
                       '--rss-mib','5120','--disk-free-mib','5120','--max-output-mib','4096',str(C.WORKSPACE),*child]
            record = dict(format='baseline-gc-prerequisite-envelope-v1',complete=False,
                          admission=dict(path=str(admission_path),sha256=admission_sha),plan=a['plan'],
                          producer_receipt=a['upstream']['producer_receipt'],command=command,cwd=str(C.SOURCE),
                          environment=environment,locks=[str(SHARED),*[str(r/'.reproduction.lock') for r in lock_roots]],
                          input_pins=pins,started_monotonic_ns=started,deadline_monotonic_ns=deadline,
                          tracked_processes={},new_cohort=True,attempt='single fresh attempt, no resume/retry')
            receipt = C.WORKSPACE/'prerequisites-controller.json'
            save = lambda:C.save(receipt,record)
            tracked = {}; proc = None; leader_start = None
            def observe():
                if proc is None:
                    return {}
                return owned_rows(table(),tracked,proc.pid,leader_start)
            def stop_owned():
                # First let original watchdog perform original descendant cleanup.
                if proc is not None and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        pass
                for sig in [signal.SIGTERM,signal.SIGKILL]:
                    for pid in observe():
                        try:
                            os.kill(pid,sig)
                        except ProcessLookupError:
                            pass
                    time.sleep(.2)
                if proc is not None and proc.poll() is None:
                    proc.kill(); proc.wait(timeout=3)
            def interrupted(signum,frame):
                raise RuntimeError('launcher interrupted by signal '+str(signum))
            oldterm = signal.signal(signal.SIGTERM,interrupted)
            oldint = signal.signal(signal.SIGINT,interrupted)
            try:
                save()
                with (C.WORKSPACE/'watchdog.stdout').open('wb') as log:
                    proc = subprocess.Popen(command,cwd=C.SOURCE,env=environment,stdin=subprocess.DEVNULL,
                                            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                    rows = table()
                    C.require(proc.pid in rows, 'watchdog identity unavailable')
                    leader_start = rows[proc.pid]['starttime']; tracked[proc.pid] = rows[proc.pid]
                    record.update(watchdog_pid=proc.pid,watchdog_starttime=leader_start); save()
                    while proc.poll() is None:
                        observe()
                        C.remaining(deadline,300)
                        time.sleep(.05)
                    record['watchdog_exit'] = proc.returncode
                record['remaining_after_watchdog'] = observe()
                C.require(not record['remaining_after_watchdog'], 'live descendants after watchdog')
                outer = C.load(C.WORKSPACE/'bounded-receipt.json')
                work = C.load(C.WORKSPACE/'prerequisites/receipt.json')
                C.require(proc.returncode == 0 and outer['complete'] is True and outer['exit_code'] == 0 and
                          outer['reason'] is None and outer['command'] == child and work['complete'] is True,
                          'bounded prerequisite phase incomplete')
                C.check_pins(pins); C.check_pins(work['output_pins'])
                C.remaining(deadline,300)
                record.update(complete=True,outer=C.identified(C.WORKSPACE/'bounded-receipt.json'),
                              work=C.identified(C.WORKSPACE/'prerequisites/receipt.json'))
            except BaseException as error:
                record['error'] = type(error).__name__+': '+str(error)
                record['complete'] = False
            finally:
                if observe() or (proc is not None and proc.poll() is None):
                    stop_owned()
                record['remaining_after_cleanup'] = observe()
                if record['remaining_after_cleanup']:
                    record['complete'] = False
                record['tracked_processes'] = tracked
                record['cross_session_descendants'] = {pid:v for pid,v in tracked.items() if proc and pid != proc.pid and v['session'] != proc.pid}
                record['finished_monotonic_ns'] = time.monotonic_ns()
                record['elapsed_seconds'] = (record['finished_monotonic_ns']-started)/1e9
                if record['elapsed_seconds'] > 300:
                    record['complete'] = False
                save()
                signal.signal(signal.SIGTERM,oldterm); signal.signal(signal.SIGINT,oldint)
        # Each original inner lock is released, then immediately reacquired.
        try:
            for root in lock_roots:
                with H.SerialLock(root):
                    record.setdefault('inner_locks_reacquired',[]).append(str(root/'.reproduction.lock'))
            fcntl.flock(shared,fcntl.LOCK_UN)
            # Reacquire this same descriptor; do not incorrectly release another owner.
            fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB)
            record['shared_lock_reacquired'] = True
            C.remaining(deadline,300)
        except BaseException as error:
            record['complete'] = False
            record['finalization_error'] = type(error).__name__+': '+str(error)
        finally:
            record['finished_monotonic_ns'] = time.monotonic_ns()
            record['elapsed_seconds'] = (record['finished_monotonic_ns']-started)/1e9
            save()
        return 0 if record['complete'] else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--admission',type=Path,required=True); p.add_argument('--admission-sha256',required=True)
    a = p.parse_args(); return run(C.regular(a.admission),a.admission_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
