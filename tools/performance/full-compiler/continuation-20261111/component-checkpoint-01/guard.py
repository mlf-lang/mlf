"""Linux isolated subreaper guard. Receipt success is necessary, never stage admission.

Report destinations are compiled into the binary, not passed in runtime argv.
The coordinator must authenticate the epoch receipt independently before calling.
"""
from pathlib import Path
import ctypes
import fcntl
import hashlib
import json
import os
import resource
import shutil
import signal
import stat
import subprocess
import sys
import time

GIB = 1024**3
LIMITS = dict(address_space=6*GIB, tree_rss=5*GIB, free_disk=5*GIB,
              host_available=3*GIB, output=4*GIB)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def safe(path, absent=False):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'absolute canonical path required')
    for part in [path, *path.parents]:
        require(not part.is_symlink(), 'symlink path: '+str(part))
    if absent:
        require(not path.exists(), 'stale path: '+str(path))
    return path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def process_table():
    rows = {}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            fields = (p/'stat').read_text().rsplit(') ', 1)[1].split()
            rows[int(p.name)] = dict(ppid=int(fields[1]), start=fields[19],
                                    state=fields[0], rss=int(fields[21])*os.sysconf('SC_PAGE_SIZE'))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return rows


def footprint(root):
    size = 0
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs+files:
            p = Path(base)/name
            require(not p.is_symlink(), 'symlink in output')
            info = p.stat()
            require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), 'special output file')
            if stat.S_ISREG(info.st_mode):
                size += info.st_size
    return size


def available_memory():
    rows = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    return int(rows['MemAvailable'].split()[0])*1024


def reacquire_locks(bindings):
    """Independently prove simultaneous acquisition, including compiler POSIX locks.

    Each binding has path/device/inode and optional kind='posix' (default flock).
    It must refer to an existing regular lock, never a data file to create.
    """
    script = r"""
import fcntl,json,os,stat,sys
fds=[]
try:
 for b in json.loads(sys.argv[1]):
  p=b['path']
  from pathlib import Path
  assert Path(p).is_absolute() and '..' not in Path(p).parts
  assert all(not q.is_symlink() for q in [Path(p),*Path(p).parents])
  fd=os.open(p,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC);fds.append(fd)
  s=os.fstat(fd)
  assert stat.S_ISREG(s.st_mode) and (s.st_dev,s.st_ino)==(b['device'],b['inode'])
  kind=b.get('kind','flock');assert kind in ('flock','posix')
  (fcntl.lockf if kind=='posix' else fcntl.flock)(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
finally:
 for fd in fds: os.close(fd)
"""
    result = subprocess.run([sys.executable, '-B', '-c', script, json.dumps(bindings)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=3, close_fds=True)
    require(result.returncode == 0, 'independent lock reacquisition failed')
    return True


def lock_owners(raw):
    """Parse Linux /proc/locks; ignore waiters and non-FLOCK records."""
    owners=set()
    for line in raw.splitlines():
        fields=line.split()
        if len(fields)!=8 or fields[1:4]!=['FLOCK','ADVISORY','WRITE']:
            continue
        major,minor,inode=fields[5].split(':')
        require(fields[6:]==['0','EOF'], 'partial flock record')
        owners.add((int(fields[4]),os.makedev(int(major,16),int(minor,16)),int(inode)))
    return owners


def verify_worker_scope(command, *, cwd, output, locks, epoch, seconds, bounded_root,
                        claim_path, claim_expected):
    """Prove this direct child belongs to its actual outer lock-owning supervisor.

    This is a fail-closed process/protocol binding, not a sandbox against a hostile
    same-UID administrator able to rewrite the admitted implementation itself.
    """
    output=safe(output);cfg=safe(output/'guard-config.json')
    expected=dict(command=command,cwd=str(safe(cwd)),output=str(output),locks=locks,
                  epoch=epoch,seconds=seconds,reports=[],test_mode=False,nested=False,
                  bounded_root=str(safe(bounded_root)),accepted_exit_codes=[0])
    require(json.loads(cfg.read_text())==expected,'worker outer configuration mismatch')
    require(json.loads(safe(claim_path).read_text())==claim_expected,'worker one-use claim mismatch')
    require(not (Path(bounded_root)/'quarantine.json').exists(),'quarantined scope')
    parent=os.getppid();table=process_table()
    require(parent in table,'missing supervisor parent')
    start=table[parent]['start']
    argv=(Path('/proc')/str(parent)/'cmdline').read_bytes().split(b'\0')[:-1]
    wanted=[sys.executable,'-B',str(Path(__file__).resolve()),str(cfg)]
    require(len(argv)==4 and argv[1:]==[x.encode() for x in wanted[1:]],'worker not direct guarded supervisor child')
    require(Path(os.fsdecode(argv[0])).resolve(strict=True)==Path(sys.executable).resolve(strict=True) and
            Path(os.readlink('/proc/'+str(parent)+'/exe')).resolve(strict=True)==Path(sys.executable).resolve(strict=True),
            'supervisor interpreter mismatch')
    require(os.readlink('/proc/self/cwd')==str(cwd),'worker cwd mismatch')
    owners=lock_owners(Path('/proc/locks').read_text())
    require(len(locks)==2,'two outer locks required')
    for binding in locks:
        st=safe(binding['path']).stat()
        require((st.st_dev,st.st_ino)==(binding['device'],binding['inode']),'worker lock inode changed')
        require((parent,st.st_dev,st.st_ino) in owners,'supervisor does not own required flock')
    require(digest(safe(epoch['path']))==epoch['sha256'],'worker epoch changed')
    require(os.getppid()==parent and process_table().get(parent,{}).get('start')==start,'supervisor identity changed')
    return dict(supervisor_pid=parent,supervisor_start=start,config_sha256=digest(cfg),
                claim_sha256=digest(claim_path),lock_ownership_verified=True)


def _supervise(config):
    # This function is entered only in an isolated interpreter. Subreaper adoption
    # closes the sampling race for a double-fork/setsid child whose parent exits.
    require(ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0, 'PR_SET_CHILD_SUBREAPER')
    output = safe(config['output'])
    rec = dict(schema='sparse-scc-guard-v1', complete=False, test_only=config['test_mode'],
               command=config['command'], limits=LIMITS, seconds=config['seconds'],
               cwd=config['cwd'],output=config['output'],bounded_root=config['bounded_root'],
               locks=config['locks'],epoch=config['epoch'],
               config_sha256=digest(output/'guard-config.json'),
               supervisor_pid=os.getpid(),supervisor_start=process_table()[os.getpid()]['start'],
               exit_code=None, reason=None, archived={}, cleanup=False, lock_reacquired=False,
               standalone_admission=not config['nested'])
    held = []; tracked = {}; child = None; interrupted = []
    report_paths_validated = False
    def on_signal(signum, frame):
        interrupted.append(signum)
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    def observe():
        rows = process_table()
        owned = {os.getpid()}
        owned |= {pid for pid, start in tracked.items() if pid in rows and rows[pid]['start'] == start}
        while True:
            new = {pid for pid, row in rows.items() if row['ppid'] in owned}-owned
            if not new:
                break
            owned |= new
        owned.discard(os.getpid())
        for pid in owned:
            tracked[pid] = rows[pid]['start']
        return {pid:rows[pid] for pid in owned if rows[pid]['state'] != 'Z'}
    def cleanup():
        for sig in [signal.SIGTERM, signal.SIGKILL]:
            for _ in range(20):
                live = observe()
                for pid in live:
                    try:
                        os.kill(pid, sig)
                    except ProcessLookupError:
                        pass
                if not live:
                    break
                time.sleep(.02)
        if child is not None:
            child.wait(timeout=3)
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if not pid:
                    break
            except ChildProcessError:
                break
        rec['cleanup'] = not observe()
        require(rec['cleanup'], 'descendants survive cleanup')
    try:
        epoch = config['epoch']
        if not config['nested']:
            safe(epoch['path'])
            require(digest(epoch['path']) == epoch['sha256'], 'epoch changed')
            require(len(config['locks']) == 2, 'shared and reproduction locks required')
        else:
            require(not config['locks'] and epoch is None, 'nested guard cannot claim lock admission')
        identities = set()
        for binding in config['locks']:
            path = safe(binding['path'])
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            held.append((fd, binding))
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode), 'regular lock required')
            ident = (info.st_dev, info.st_ino)
            require(ident == (binding['device'], binding['inode']), 'lock epoch inode mismatch')
            require(ident not in identities, 'distinct locks required')
            identities.add(ident)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for report in config['reports']:
            p = safe(report, absent=True)
            require(p.parent.is_dir(), 'report parent missing')
            require(Path(config['bounded_root']) in p.parents, 'reports must live under bounded output root')
        report_paths_validated = True
        def bounds():
            for fd, binding in held:
                st = safe(binding['path']).stat()
                require((st.st_dev, st.st_ino) == (binding['device'], binding['inode']), 'lock replaced during run')
            live = observe()
            require(sum(row['rss'] for row in live.values()) <= LIMITS['tree_rss'], 'tree RSS limit')
            require(footprint(Path(config['bounded_root'])) <= LIMITS['output'], 'output limit')
            if not config['test_mode']:
                require(shutil.disk_usage(output).free >= LIMITS['free_disk'], 'free disk floor')
                require(available_memory() >= LIMITS['host_available'], 'host memory floor')
            return live
        bounds()
        def child_limits():
            resource.setrlimit(resource.RLIMIT_AS, (LIMITS['address_space'], LIMITS['address_space']))
            resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS['output'], LIMITS['output']))
        start = time.monotonic()
        with (output/'stdout').open('xb') as stdout, (output/'stderr').open('xb') as stderr:
            child = subprocess.Popen(config['command'], cwd=config['cwd'], stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, start_new_session=True,
                                     preexec_fn=child_limits, close_fds=True)
            while True:
                live = bounds()
                if interrupted:
                    rec['reason'] = 'cancelled'
                    raise RuntimeError('cancelled')
                if time.monotonic()-start > config['seconds']:
                    rec['reason'] = 'timeout'
                    raise RuntimeError('timeout')
                if child.poll() is not None:
                    break
                time.sleep(.025)
        rec['exit_code'] = child.returncode
        rec['elapsed_seconds'] = time.monotonic()-start
        require(not observe(), 'descendants survived leader exit')
        require(child.returncode >= 0 and child.returncode != 124 and child.returncode in config['accepted_exit_codes'], 'unexpected child exit (124 is not timeout)')
        cleanup()
        archive = output/'reports'
        archive.mkdir()
        for index, report in enumerate(config['reports']):
            p = safe(report)
            require(p.is_file() and p.stat().st_nlink == 1 and p.stat().st_size > 0, 'missing/invalid report')
            target = archive/(str(index)+'-'+p.name)
            os.rename(p, target)
            rec['archived'][str(p)] = dict(path=str(target), sha256=digest(target), bytes=target.stat().st_size)
        if not config['nested']:
            require(digest(epoch['path']) == epoch['sha256'], 'epoch changed during run')
    except BaseException as error:
        rec['reason'] = rec['reason'] or str(error)
    finally:
        try:
            cleanup()
        except BaseException as error:
            rec['cleanup'] = False
            rec['reason'] = rec['reason'] or repr(error)
        # Preserve even incomplete reports; they are never successful evidence.
        failure_archive = output/'incomplete-reports'
        for index, report in enumerate(config['reports'] if report_paths_validated and child is not None else []):
            try:
                p = safe(report)
                if p.is_file() and p.stat().st_nlink == 1:
                    failure_archive.mkdir(exist_ok=True)
                    os.rename(p, failure_archive/(str(index)+'-'+p.name))
            except (OSError, ValueError):
                pass
        for fd, binding in reversed(held):
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        try:
            require(config['nested'] or len(held) == 2, 'both locks not acquired')
            if not config['nested']:
                reacquire_locks([binding for _, binding in held])
            rec['lock_reacquired'] = not config['nested']
        except BaseException as error:
            rec['reason'] = rec['reason'] or repr(error)
        rec['tracked_processes'] = tracked
        rec['complete'] = rec['reason'] is None and rec['cleanup'] and (config['nested'] or rec['lock_reacquired'])
        (output/'guard.json').write_text(json.dumps(rec, sort_keys=True, indent=2)+'\n')
    return rec


def run_guard(command, *, cwd, output, locks, epoch, seconds, reports=(), test_mode=False, cancel_event=None,
              accepted_exit_codes=(0,), bounded_root=None, _nested=False):
    """One invocation, no retry. Returns guard receipt (complete=False on failure).

    test_mode skips host/disk admission only; its receipt cannot qualify heavy work.
    Cancellation sends TERM to the supervisor; it cleans all owned descendants.
    SIGKILL of the supervisor is an unprovable outcome: receipt is incomplete and
    the coordinator must quarantine this epoch pending external cleanup.
    """
    require(type(seconds) in (int, float) and 0 < seconds <= 600, 'time budget')
    require(isinstance(command, list) and command and all(isinstance(x, str) for x in command), 'argv list')
    require(len(set(map(str, reports))) == len(reports), 'duplicate report paths')
    output = safe(output, absent=True)
    require(output.parent.is_dir(), 'output parent missing')
    output.mkdir(mode=0o700)
    bounded_root = safe(bounded_root or output)
    require(output == bounded_root or bounded_root in output.parents, 'output outside bounded root')
    require(all(type(x) is int and 0 <= x < 124 for x in accepted_exit_codes), 'accepted exit codes')
    config = dict(command=command, cwd=str(safe(cwd)), output=str(output), locks=locks,
                  epoch=epoch, seconds=seconds, reports=list(map(str, reports)), test_mode=test_mode,
                  nested=_nested, bounded_root=str(bounded_root), accepted_exit_codes=list(accepted_exit_codes))
    require(not (bounded_root/'quarantine.json').exists(), 'quarantined scope')
    cfg = output/'guard-config.json'
    cfg.write_text(json.dumps(config))
    worker = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), str(cfg)],
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, start_new_session=True)
    cancellation_sent = False
    try:
      while worker.poll() is None:
        if cancel_event is not None and cancel_event.is_set() and not cancellation_sent:
            worker.send_signal(signal.SIGTERM)
            cancellation_sent = True
        time.sleep(.025)
    except BaseException:
        worker.send_signal(signal.SIGTERM)
        worker.wait(timeout=10)
        raise
    _, stderr = worker.communicate()
    receipt = output/'guard.json'
    if worker.returncode != 0 or not receipt.is_file():
        failure=dict(complete=False, reason='supervisor transport failure; epoch quarantine required',
                     supervisor_exit=worker.returncode, stderr=stderr.decode(errors='replace'),
                     epoch=epoch, locks=locks, output=str(output), bounded_root=str(bounded_root))
        quarantine=safe(bounded_root/'quarantine.json')
        try:
            with quarantine.open('x') as f:
                json.dump(failure,f,sort_keys=True);f.flush();os.fsync(f.fileno())
        except FileExistsError:
            pass
        return failure
    return json.loads(receipt.read_text())


def run_child(command, *, cwd, output, seconds, reports=(), bounded_root=None, accepted_exit_codes=(0,), test_mode=False, cancel_event=None):
    """Invocation only. Must be enclosed by run_guard for real stage admission."""
    return run_guard(command, cwd=cwd, output=output, seconds=seconds, reports=reports,
                     bounded_root=bounded_root, accepted_exit_codes=accepted_exit_codes,
                     test_mode=test_mode, cancel_event=cancel_event, locks=[], epoch=None, _nested=True)


if __name__ == '__main__':
    _supervise(json.loads(Path(sys.argv[1]).read_text()))
