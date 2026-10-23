#!/usr/bin/env python3
"""Measure a Linux command tree and preserve every observed build-report version.

RSS is sampled, not an allocation trace; summed RSS conservatively double-counts
shared pages. Scheduler task work/critical path are not added to command wall time.
Lock waiting and metadata hashing are excluded from the measured command interval.
"""
import argparse
import csv
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
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


def run(args):
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = Path(args.source_root).resolve()
    root = Path(args.report_root).resolve() if args.report_root else source / ".mlf-build"
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise ValueError("a command is required after --")
    git = lambda *a: subprocess.check_output(["git", "-C", str(source), *a])
    tracked = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
    hashes = {name: digest(source / name) for name in tracked if name and (source / name).is_file()}
    (output / "source-files.json").write_text(json.dumps(hashes, indent=2) + "\n")
    (output / "source.diff").write_bytes(git("diff", "HEAD", "--"))
    context = {
        "label": args.label, "command": command, "cwd": str(source),
        "source_commit": git("rev-parse", "HEAD").decode().strip(),
        "measurement_script_sha256": digest(__file__),
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
    }
    (output / "context.json").write_text(json.dumps(context, indent=2) + "\n")
    receipts = output / "reports"
    receipts.mkdir()
    seen = set()
    report_index = []
    invocations = {}
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
            except (OSError, ValueError, KeyError):
                continue
    capture_reports(0, initial=True)
    with open(args.lock, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if available_memory() < args.minimum_available_mib * 1024 ** 2:
            raise RuntimeError("Insufficient available memory before command start")
        start = time.monotonic()
        context["started_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (output / "context.json").write_text(json.dumps(context, indent=2) + "\n")
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        peak_rss = 0
        peak_processes = 0
        minimum_available = available_memory()
        guard_reason = None
        low_memory_since = None
        with open(output / "command.log", "wb") as log, open(output / "samples.csv", "w", newline="") as samples:
            writer = csv.writer(samples)
            writer.writerow(["elapsed_seconds", "tree_rss_bytes", "process_count", "host_available_bytes", "processes"])
            proc = subprocess.Popen(command, cwd=source, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            while True:
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
                if available < args.minimum_available_mib * 1024 ** 2:
                    low_memory_since = low_memory_since or time.monotonic()
                    if time.monotonic() - low_memory_since >= 1 and guard_reason is None:
                        guard_reason = "host MemAvailable below safety threshold for one second"
                        os.killpg(proc.pid, signal.SIGTERM)
                else:
                    low_memory_since = None
                if guard_reason and time.monotonic() - (low_memory_since or start) > 6 and proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                if proc.poll() is not None:
                    break
                time.sleep(args.interval)
            returncode = proc.wait()
        elapsed = time.monotonic() - start
        capture_reports(elapsed)
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
    result = {
        "label": args.label, "returncode": returncode, "guard_reason": guard_reason,
        "wall_seconds": elapsed,
        "process_tree_cpu_seconds": (after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime),
        "sampled_process_tree_peak_rss_bytes": peak_rss,
        "sampled_peak_process_count": peak_processes,
        "host_minimum_available_bytes": minimum_available,
        "scheduler_invocations": list(invocations.values()),
        "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    (output / "report-index.json").write_text(json.dumps(report_index, indent=2) + "\n")
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return returncode if returncode >= 0 else 128 - returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--report-root")
    parser.add_argument("--label", required=True)
    parser.add_argument("--tool", action="append", default=[])
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--minimum-available-mib", type=int, default=1536)
    parser.add_argument("--lock", default=str(Path(tempfile.gettempdir()) / "mlf-qualification-build.lock"))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    raise SystemExit(run(parser.parse_args()))
