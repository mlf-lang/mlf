#!/usr/bin/env python3
"""Measure a Linux command tree and preserve every observed build-report version.

RSS is sampled, not an allocation trace; summed RSS conservatively double-counts
shared pages. Scheduler task work/critical path are not added to command wall time.
Lock waiting and metadata hashing are excluded from the measured command interval.
"""
import argparse
import csv
import ctypes
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
import tempfile


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def available_memory():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("Linux /proc/meminfo MemAvailable is required")


def cache_inventory(root):
    """Describe the exact build-cache starting state, without altering receipts."""
    root = Path(root).resolve()
    files = {}
    for file in sorted(root.rglob("*")) if root.exists() else []:
        name = str(file.relative_to(root))
        if file.is_symlink():
            files[name] = {"symlink": os.readlink(file)}
        elif file.is_file():
            files[name] = {"bytes": file.stat().st_size, "sha256": digest(file)}
    return {"path": str(root), "existed": root.exists(), "files": files}


def processes():
    found = {}
    page = os.sysconf("SC_PAGE_SIZE")
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            value = (entry / "stat").read_text()
            end = value.rfind(")")
            fields = value[end + 2:].split()
            found[int(entry.name)] = (int(fields[1]), int(fields[21]) * page,
                                      value[value.find("(") + 1:end])
        except (OSError, ValueError, IndexError):
            pass
    return found


def tree_snapshot(root):
    procs = processes()
    selected = {root} if root in procs else set()
    while True:
        extra = {pid for pid, (parent, _, _) in procs.items() if parent in selected}
        if extra <= selected:
            break
        selected |= extra
    rows = [(pid, *procs[pid]) for pid in sorted(selected)]
    return rows, sum(row[2] for row in rows)


def scheduler_summary(report):
    plans = {x["invocation_id"]: x for x in report.get("scheduler", [])}
    rows = []
    for result in report.get("scheduler_results", []):
        tasks = {x["id"]: x for x in result.get("tasks", [])}
        jobs = {x["id"]: x for x in plans.get(result["invocation_id"], {}).get("jobs", [])}
        memo = {}
        def path(task_id, visiting=None):
            if task_id in memo:
                return memo[task_id]
            visiting = set() if visiting is None else visiting
            if task_id in visiting:
                raise ValueError("scheduler dependency cycle")
            duration = tasks.get(task_id, {}).get("wall_seconds", 0)
            prior = max((path(dep, visiting | {task_id}) for dep in
                         jobs.get(task_id, {}).get("dependencies", [])), default=0)
            memo[task_id] = prior + duration
            return memo[task_id]
        rows.append({
            "invocation_id": result["invocation_id"],
            "complete": result.get("complete"), "exit_code": result.get("exit_code"),
            "jobs": result.get("jobs"),
            "maximum_parallel_jobs": result.get("maximum_parallel_jobs"),
            "scheduler_wall_seconds": result.get("wall_seconds"),
            "aggregate_task_wall_seconds": sum(x.get("wall_seconds", 0) for x in tasks.values()),
            "aggregate_task_cpu_seconds": sum(x.get("cpu_seconds", 0) for x in tasks.values()),
            "dependency_critical_path_seconds": max((path(x) for x in tasks), default=0),
            "scheduler_aggregate_peak_rss_bytes": result.get("aggregate_peak_rss_bytes"),
            "task_count": len(tasks),
        })
    return rows


def set_subreaper(enabled):
    """Adopt command grandchildren so cleanup can reap them before unlocking."""
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(previous), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "PR_GET_CHILD_SUBREAPER failed")
    if libc.prctl(36, int(enabled), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "PR_SET_CHILD_SUBREAPER failed")
    return bool(previous.value)


def signal_group(pid, signum):
    try:
        os.killpg(pid, signum)
    except ProcessLookupError:
        pass


def cleanup_command(proc, signum=signal.SIGTERM, grace_seconds=2):
    """Terminate/reap the entire owned tree, including separate child groups.

    This runs while the experiment lock is still held. Linux subreaper status
    makes orphaned grandchildren our children; no other child commands are
    launched concurrently by this profiler. SIGKILL escalates after the grace
    period, but the lock is never released while an owned descendant remains.
    """
    deadline = time.monotonic() + grace_seconds
    signaled = set()
    signal_group(proc.pid, signum)
    while True:
        proc.poll()  # Let Popen, not waitpid below, collect the command status.
        rows, _ = tree_snapshot(os.getpid())
        children = [row for row in rows if row[0] != os.getpid()]
        for pid, parent, _, _ in children:
            if parent == os.getpid() and pid != proc.pid:
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
        rows, _ = tree_snapshot(os.getpid())
        children = [row for row in rows if row[0] != os.getpid()]
        if not children:
            return proc.wait()
        force = time.monotonic() >= deadline
        for pid, _, _, _ in children:
            if force or pid not in signaled:
                try:
                    os.kill(pid, signal.SIGKILL if force else signum)
                except ProcessLookupError:
                    pass
                signaled.add(pid)
        if force:
            signal_group(proc.pid, signal.SIGKILL)
        time.sleep(0.02)


def run(args):
    # This Python module is already loaded; a queued run must not identify a
    # replacement file as its executing sampler. Task/tool snapshots stay locked.
    measurement_script_sha256 = digest(__file__)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = Path(args.source_root).resolve()
    root = Path(args.report_root).resolve() if args.report_root else source / ".mlf-build"
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise ValueError("a command is required after --")
    receipts = output / "reports"
    receipts.mkdir()
    seen = set()
    report_index = []
    report_errors = []
    report_error_keys = set()
    invocations = {}
    interrupted = None
    def handle_signal(signum, _frame):
        # Do not raise out of cleanup or release flock before descendants exit.
        nonlocal interrupted
        interrupted = interrupted or signum
    old_handlers = {sig: signal.signal(sig, handle_signal)
                    for sig in (signal.SIGTERM, signal.SIGINT)}
    def capture_reports(elapsed, initial=False):
        for file in root.rglob("build-report.json") if root.exists() else []:
            try:
                data = file.read_bytes()
                report_hash = hashlib.sha256(data).hexdigest()
                key = (str(file), report_hash)
                if key in seen:
                    continue
                report = json.loads(data)
                seen.add(key)
                if initial:
                    continue
                saved = f"{len(report_index):04d}-{report_hash}.json"
                (receipts / saved).write_bytes(data)
                report_index.append({"source": str(file), "sha256": report_hash,
                                     "elapsed_seconds": elapsed, "saved": "reports/" + saved})
                for row in scheduler_summary(report):
                    invocations[row["invocation_id"]] = row
            except OSError:
                continue  # A concurrently replaced/disappearing report is normal.
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                error_key = (str(file), report_hash)
                if error_key not in report_error_keys:
                    report_error_keys.add(error_key)
                    report_errors.append({"source": str(file), "sha256": report_hash,
                                          "elapsed_seconds": elapsed,
                                          "error": f"{type(exc).__name__}: {exc}"})
    try:
        with open(args.lock, "a+") as lock:
            # Interruptible waiting: Python otherwise retries blocking flock.
            acquired = False
            while not interrupted:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    time.sleep(0.05)
            proc = None
            tee = None
            start = None
            before = None
            previous_subreaper = None
            peak_rss = 0
            peak_processes = 0
            minimum_available = None
            guard_reason = None
            error = None
            returncode = 1
            context = {"label": args.label, "command": command, "cwd": str(source)}
            try:
                if acquired and not interrupted:
                    # All identities and the initial report baseline belong to
                    # this lock holder, never to a preceding queued experiment.
                    git = lambda *a: subprocess.check_output(["git", "-C", str(source), *a])
                    tracked = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
                    hashes = {name: digest(source / name) for name in tracked if name and (source / name).is_file()}
                    (output / "source-files.json").write_text(json.dumps(hashes, indent=2) + "\n")
                    (output / "source.diff").write_bytes(git("diff", "HEAD", "--"))
                    context.update({
                        "source_commit": git("rev-parse", "HEAD").decode().strip(),
                        "measurement_script_sha256": measurement_script_sha256,
                        "source_files_sha256": digest(output / "source-files.json"),
                        "source_diff_sha256": digest(output / "source.diff"),
                        "environment": {k: v for k, v in os.environ.items() if k.startswith(("MLF_", "GC_")) or k in
                                        ["PATH", "LD_LIBRARY_PATH", "CPATH", "C_INCLUDE_PATH", "LIBRARY_PATH"]},
                        "tools": {name: {"path": str(Path(name).resolve()), "sha256": digest(name)} for name in args.tool},
                        "uname": list(os.uname()), "cpu_count": os.cpu_count(),
                        "sample_interval_seconds": args.interval,
                        "minimum_available_memory_bytes": args.minimum_available_mib * 1024 ** 2,
                        "rss_method": "sum of sampled Linux stat RSS for command and live descendants; shared pages may be counted multiple times",
                        "stack_rlimit": list(resource.getrlimit(resource.RLIMIT_STACK)),
                    })
                    caches = [cache_inventory(path) for path in args.cache_dir]
                    (output / "initial-caches.json").write_text(json.dumps(caches, indent=2) + "\n")
                    context["initial_caches_sha256"] = digest(output / "initial-caches.json")
                    capture_reports(0, initial=True)
                    minimum_available = available_memory()
                    if minimum_available < args.minimum_available_mib * 1024 ** 2:
                        raise RuntimeError("Insufficient available memory before command start")
                    if not interrupted:
                        previous_subreaper = set_subreaper(True)
                        before = resource.getrusage(resource.RUSAGE_CHILDREN)
                        start = time.monotonic()
                        context["started_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        (output / "context.json").write_text(json.dumps(context, indent=2) + "\n")
                        low_memory_since = None
                        with open(output / "command.log", "wb") as log, open(output / "samples.csv", "w", newline="") as samples:
                            writer = csv.writer(samples)
                            writer.writerow(["elapsed_seconds", "tree_rss_bytes", "process_count", "host_available_bytes", "processes"])
                            if args.tee:
                                tee = open(output / "command.log", "rb")
                            proc = subprocess.Popen(command, cwd=source, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                            while not interrupted:
                                elapsed = time.monotonic() - start
                                rows, rss = tree_snapshot(proc.pid)
                                available = available_memory()
                                peak_rss = max(peak_rss, rss)
                                peak_processes = max(peak_processes, len(rows))
                                minimum_available = min(minimum_available, available)
                                writer.writerow([f"{elapsed:.6f}", rss, len(rows), available,
                                                 ";".join(f"{pid}:{name}:{mem}" for pid, _, mem, name in rows)])
                                samples.flush()
                                capture_reports(elapsed)
                                if tee is not None:
                                    sys.stdout.buffer.write(tee.read())
                                    sys.stdout.buffer.flush()
                                if available < args.minimum_available_mib * 1024 ** 2:
                                    low_memory_since = low_memory_since or time.monotonic()
                                    if time.monotonic() - low_memory_since >= 1:
                                        guard_reason = "host MemAvailable below safety threshold for one second"
                                        break
                                else:
                                    low_memory_since = None
                                if proc.poll() is not None:
                                    break
                                time.sleep(args.interval)
            except BaseException as exc:
                error = f"{type(exc).__name__}: {exc}"
            finally:
                # Keep handlers and flock active through cleanup AND receipts.
                if proc is not None:
                    returncode = cleanup_command(proc, interrupted or signal.SIGTERM)
                elapsed = time.monotonic() - start if start is not None else 0
                if proc is not None:
                    capture_reports(elapsed)
                if tee is not None:
                    sys.stdout.buffer.write(tee.read())
                    sys.stdout.buffer.flush()
                    tee.close()
                after = resource.getrusage(resource.RUSAGE_CHILDREN)
                if previous_subreaper is not None:
                    set_subreaper(previous_subreaper)
                exit_code = (128 + interrupted if interrupted else
                             143 if guard_reason else 1 if error else
                             returncode if returncode >= 0 else 128 - returncode)
                result = {
                    "label": args.label, "returncode": exit_code,
                    "command_returncode": returncode if proc is not None else None,
                    "command_started": proc is not None, "interrupted_signal": interrupted,
                    "error": error, "guard_reason": guard_reason, "wall_seconds": elapsed,
                    "process_tree_cpu_seconds": ((after.ru_utime + after.ru_stime) -
                                                 (before.ru_utime + before.ru_stime)) if before else 0,
                    "sampled_process_tree_peak_rss_bytes": peak_rss,
                    "sampled_peak_process_count": peak_processes,
                    "host_minimum_available_bytes": minimum_available,
                    "scheduler_invocations": list(invocations.values()),
                    "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                (output / "context.json").write_text(json.dumps(context, indent=2) + "\n")
                (output / "report-index.json").write_text(json.dumps(report_index, indent=2) + "\n")
                (output / "report-errors.json").write_text(json.dumps(report_errors, indent=2) + "\n")
                (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
                print(json.dumps(result, indent=2), flush=True)
            return exit_code
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--report-root")
    parser.add_argument("--cache-dir", action="append", default=[])
    parser.add_argument("--label", required=True)
    parser.add_argument("--tool", action="append", default=[])
    parser.add_argument("--tee", action="store_true", help="Stream command.log bytes to stdout while sampling")
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--minimum-available-mib", type=int, default=1536)
    parser.add_argument("--lock", default=str(Path(tempfile.gettempdir()) / "mlf-qualification-build.lock"))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    raise SystemExit(run(parser.parse_args()))
