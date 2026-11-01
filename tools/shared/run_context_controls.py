#!/usr/bin/env python3
"""Run a separately qualified Haskell fixture; never compile or relax guards.

The caller must provide its original bounded guard, authenticated build inputs,
private environment, and a fresh output directory. This script is not that guard.
Publication metrics are observed file changes, NOT write-syscall/IO measurements:
source-context.new staging and query-key.new activity are explicitly not omitted
from the limitation merely because their files disappear or are overwritten.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, stat, subprocess, time, sys
import fcntl

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def unpack(text):
    result = []
    while text:
        count, separator, rest = text.partition(":")
        require(separator and count.isascii() and count.isdecimal(), "scalar framing")
        size = int(count)
        require(str(size) == count and size <= len(rest), "canonical scalar framing")
        result.append(rest[:size])
        text = rest[size:]
    return result

def pack(fields):
    return "".join(f"{len(value)}:{value}" for value in fields)

def snapshot(root, active_hashes):
    files, directories = {}, 0
    allocated = root.lstat().st_blocks * 512
    for path in sorted(root.rglob("*")):
        s = path.lstat()
        require(stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode), "regular cache tree only")
        allocated += s.st_blocks * 512
        if stat.S_ISDIR(s.st_mode):
            directories += 1
            continue
        require(s.st_nlink == 1 and s.st_size <= 16 * 1024**2, "small private cache file")
        raw = path.read_bytes()
        files[str(path.relative_to(root))] = {
            "bytes": len(raw), "sha256": digest(raw), "allocated": s.st_blocks * 512,
            "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns,
        }
    records, contexts, legacy = {}, set(), []
    for key in active_hashes:
        require(re.fullmatch("[0-9a-f]{64}", key), "query digest")
        name = key + ".mlfq"
        require(name in files, "reachable query exists")
        fields = unpack((root / name).read_text(encoding="utf-8"))
        require(fields and fields[0] in ["MLF-QUERY-CACHE-1", "MLF-QUERY-CACHE-2", "MLF-QUERY-CACHE-3"], "known cache representation")
        if fields[0] == "MLF-QUERY-CACHE-3":
            require(len(fields) == 4 and re.fullmatch("[0-9a-f]{64}", fields[1]), "source reference")
            context_name = "context-" + fields[1] + ".mlfqc"
            require(context_name in files and files[context_name]["sha256"] == fields[1], "reachable SHA context")
            carrier = unpack((root / context_name).read_text(encoding="utf-8"))
            require(len(carrier) == 2 and carrier[0] == "MLF-SOURCE-QUERY-CONTEXT-1", "typed context")
            compact = unpack(fields[2])
            require(len(compact) == 8 and compact[0] == "MLF-SOURCE-CRATE-QUERY-6", "complete remaining key")
            full_key = pack(compact[:5] + [carrier[1]] + compact[5:])
            require(digest(full_key.encode("utf-8")) == key, "unchanged full query-key SHA filename")
            contexts.add(context_name)
        else:
            legacy.append(name)
            require(digest(fields[1].encode("utf-8")) == key, "legacy full-key SHA filename")
        records[name] = fields[0]
    reachable = set(records) | contexts
    return {
        "files": files, "directories_excluding_root": directories,
        "active_records": records, "reachable_contexts": sorted(contexts),
        "legacy_records": legacy, "reachable_files": sorted(reachable),
        "reachable_logical_bytes": sum(files[n]["bytes"] for n in reachable),
        "reachable_file_allocated_bytes": sum(files[n]["allocated"] for n in reachable),
        "all_cache_logical_bytes": sum(x["bytes"] for x in files.values()),
        "all_cache_pathname_conservative_allocated_bytes": allocated,
        "other_physical_files": sorted(set(files) - reachable),
        "unreachable_context_files": sorted(n for n in set(files) - reachable if n.endswith(".mlfqc")),
        "retained_old_query_files": sorted(n for n in set(files) - reachable if n.endswith(".mlfq")),
        "scratch_and_lock_files": sorted(n for n in set(files) - reachable if not n.endswith((".mlfqc", ".mlfq"))),
        "other_physical_bytes": sum(x["bytes"] for n, x in files.items() if n not in reachable),
        "no_gc_performed": True,
    }

def publication_delta(before, after):
    a, b = before["files"], after["files"]
    added = sorted(set(b) - set(a))
    changed = sorted(n for n in set(a) & set(b)
                     if a[n]["mtime_ns"] != b[n]["mtime_ns"] or a[n]["sha256"] != b[n]["sha256"])
    return {
        "added_files": added, "observed_changed_files": changed,
        "added_logical_bytes": sum(b[n]["bytes"] for n in added),
        "observed_published_file_change_bytes": sum(b[n]["bytes"] for n in added + changed),
        "not_total_io_bytes": True,
        "temporary_creation_deletion_and_multiple_writes_not_observed": True,
    }

SENTINELS = {"unrelated.new": b"retain unrelated staging\n",
             "codegen-key.new": b"retain separate codegen scratch\n",
             "key.new": b"retain non-query key scratch\n"}


def no_query_scratch(cache):
    require(not os.path.lexists(cache / "query-key.new"), "query scratch remains after normal return")


def small_identity(path):
    s = path.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_size <= 65536, "small regular sentinel")
    # A POSIX record lock is dropped if this process closes ANY fd for the
    # same inode. Never reopen/read/close .lock while the pair holder owns it.
    # For a regular zero-byte file the empty SHA is exact from metadata.
    if path.name == ".lock":
        require(s.st_size == 0, "empty lock sentinel")
        contents = b""
    else:
        contents = path.read_bytes()
    return {"sha256": digest(contents), "bytes": s.st_size,
            "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns,
            "device": s.st_dev, "inode": s.st_ino, "mode": s.st_mode, "blocks": s.st_blocks}


def seed_cache(cache, directory=False):
    cache.mkdir()
    for name, value in SENTINELS.items():
        with (cache / name).open("xb") as stream:
            stream.write(value)
    with (cache / ".lock").open("xb"):
        pass
    scratch = cache / "query-key.new"
    if directory:
        scratch.mkdir()
        with (scratch / "retained-child").open("xb") as stream:
            stream.write(b"must not recurse into reserved scratch directory\n")
    else:
        with scratch.open("xb") as stream:
            stream.write(b"stale query key from a prior stopped run\n")
    result = {name: small_identity(cache / name) for name in SENTINELS}
    result[".lock"] = small_identity(cache / ".lock")
    if directory:
        result["query-key.new/retained-child"] = small_identity(scratch / "retained-child")
    return result


def verify_sentinels(cache, original):
    for name, expected in original.items():
        require(small_identity(cache / name) == expected, "sentinel or lock identity changed: " + name)


def physical_inventory(cache):
    # No reference/liveness claim for failed calls without a QueryReport.
    # Every file/directory is still included, including rejected scratch dirs.
    rows, logical, allocated = {}, 0, 0
    for path in [cache, *sorted(cache.rglob("*"))]:
        s = path.lstat()
        require(stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode), "regular private cache tree")
        allocated += s.st_blocks * 512
        row = {"directory": stat.S_ISDIR(s.st_mode), "bytes": s.st_size,
               "allocated": s.st_blocks * 512, "device": s.st_dev, "inode": s.st_ino}
        if stat.S_ISREG(s.st_mode):
            require(s.st_size <= 16 * 1024**2, "individual cache file cap")
            logical += s.st_size
            row["sha256"] = digest(path.read_bytes())
        rows[str(path.relative_to(cache))] = row
    return {"all_physical_nodes": rows, "all_file_logical_bytes": logical,
            "all_pathname_conservative_allocated_bytes": allocated,
            "active_reference_set_not_inferred_from_failure": True}


def independent_lock_probe(arguments):
    require(len(arguments) == 3, "lock probe exact arguments")
    path, device, inode = Path(arguments[0]), int(arguments[1]), int(arguments[2])
    require(path.resolve(strict=True) == path, "real lock path")
    fd = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and (before.st_dev, before.st_ino) == (device, inode), "same lock inode")
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        after = path.lstat()
        require((after.st_dev, after.st_ino) == (device, inode), "lock path binding changed")
        fcntl.lockf(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    print("PASS independent lock acquisition")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture, out = args.fixture.absolute(), args.output.absolute()
    require(fixture.is_file() and fixture.resolve() == fixture, "qualified regular fixture path")
    require(not out.exists() and out.parent.is_dir() and out.parent.resolve() == out.parent, "fresh real output")
    out.mkdir()
    record = {"complete": False, "fixture_sha256": digest(fixture.read_bytes()), "commands": [], "drivers": {}, "limitations": [
        "Small synthetic source population, not corpus-wide performance or space estimate.",
        "One cooperative POSIX same-cache pair; no same-process thread, hostile-directory, crash, permission-failure or GC qualification.",
        "Publication deltas are snapshots, not total IO; deleted staging writes remain unmeasured.",
        "Final objects/contexts checked on actual local compiler identified by outer build receipt.",
    ]}
    def save():
        raw = (json.dumps(record, indent=2) + "\n").encode()
        require(len(raw) <= 1024**2, "small report")
        (out / "receipt.json").write_bytes(raw)
    def run(name, argv, executable=None, timeout=180):
        row = {"name": name, "argv": [str(executable or fixture), *map(str, argv)], "state": "running",
               "kind": "lock-probe" if executable else "fixture", "timeout_seconds": timeout}
        record["commands"].append(row)
        save()
        started = time.monotonic()
        failure = None
        captures = {label: out / (name + "." + label) for label in ("stdout", "stderr")}
        # Private fresh capture files survive nonzero exit, timeout, and size
        # rejection. Never accumulate an unbounded child pipe in this process.
        try:
            with captures["stdout"].open("xb") as stdout, captures["stderr"].open("xb") as stderr:
                result = subprocess.run(row["argv"], cwd=out, env=os.environ.copy(),
                                        stdout=stdout, stderr=stderr, timeout=timeout)
            row["exit_code"] = result.returncode
        except BaseException as error:
            failure = error
            row["error"] = type(error).__name__ + ": " + str(error)
            row["timed_out"] = isinstance(error, subprocess.TimeoutExpired)
        finally:
            row.update(seconds=time.monotonic()-started, state="failed")
            for label, path in captures.items():
                if not path.exists():
                    continue
                hasher = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(65536), b""):
                        hasher.update(block)
                row[label] = {"path": str(path), "bytes": path.stat().st_size,
                              "sha256": hasher.hexdigest()}
            save()  # Full evidence identity must precede every failure/size check.
        if failure is not None:
            raise failure
        require(all(row[label]["bytes"] <= 65536 for label in captures),
                "small fixture capture (full rejected capture retained under outer guard)")
        require(row["exit_code"] == 0 and row["stderr"]["bytes"] == 0,
                "fixture status/stderr: " + name)
        row["state"] = "passed"
        save()
        return captures["stdout"].read_bytes()
    def driver(kind, cache, root, value, name):
        argv = ["query", cache, root / "final.objects", value] if kind == "query" else ["session", cache, root, value]
        raw = run(name, argv)
        report = json.loads(raw)
        require(report["format"] == 1 and len(report["groups"]) > 0, "actual query report")
        no_query_scratch(cache)
        hashes = [x["query_key"] for x in report["groups"]]
        require(len(hashes) == len(set(hashes)), "distinct query records")
        result_files = [root / "final.objects"] if kind == "query" else [root / "probe.mlfci", root / "probe.mlfco"]
        artifacts = {p.name: digest(p.read_bytes()) for p in result_files}
        measured = {"query_report": report, "cache": snapshot(cache, hashes), "artifact_sha256": artifacts}
        if kind == "query":
            evidence = (root / "final.objects.legacy-bytes").read_bytes()
            rows = unpack(evidence.decode("utf-8"))
            require(rows and rows[0] == "MLF-QUERY-LEGACY-BYTES-1", "legacy accounting schema")
            sizes = {}
            for row in rows[1:]:
                key, size = unpack(row)
                require(key in hashes and key not in sizes and size.isascii() and size.isdecimal(), "legacy accounting record")
                sizes[key] = int(size)
                require(str(sizes[key]) == size and sizes[key] > 0, "canonical legacy byte count")
            require(set(sizes) == set(hashes), "complete active legacy comparison")
            measured["legacy_self_contained_comparison"] = {
                "per_record_utf8_bytes": sizes, "total_utf8_bytes": sum(sizes.values()),
                "new_complete_reachable_utf8_bytes": measured["cache"]["reachable_logical_bytes"],
                "evidence_sha256": digest(evidence),
                "semantic_roundtrip_verified_by_fixture": True,
                "scope": "synthetic Query empty datatype context only; old bytes constructed in memory",
                "not_a_physical_baseline_or_io_measurement": True,
            }
        return measured
    try:
        helper = run("helper", ["helper", out / "helper-cache"])
        require(helper.endswith(b"PASS helper CACHE1/CACHE2/CACHE3, complete-key and corrupt-input controls\n"), "helper terminal marker")
        raw_final = run("raw-final", ["raw-final", out / "raw-final-cache"])
        require(raw_final == b"PASS final payload cannot masquerade as raw source cache\n", "raw/final terminal marker")
        for kind in ["query", "session"]:
            root = out / kind
            root.mkdir()
            cache = root / "cache"
            sentinels = seed_cache(cache)
            cold = driver(kind, cache, root, "41", kind + "-cold")
            require(cold["query_report"]["inferred_groups"] > 0 and cold["query_report"]["reused_groups"] == 0, "cold actually infers")
            warm = driver(kind, cache, root, "41", kind + "-warm")
            require(warm["query_report"]["inferred_groups"] == 0 and warm["query_report"]["reused_groups"] == cold["query_report"]["inferred_groups"], "warm actually hits")
            require(warm["artifact_sha256"] == cold["artifact_sha256"], "final artifacts exact cold/warm")
            require(warm["cache"]["reachable_contexts"], "production cache uses shared representation")
            for n in cold["cache"]["reachable_contexts"]:
                require(cold["cache"]["files"][n] == warm["cache"]["files"][n], "warm context unchanged")
            mixed = None
            before_change = warm
            if kind == "query":
                require(len(cold["cache"]["active_records"]) == 2 and len(cold["cache"]["reachable_contexts"]) == 1, "two groups share one context")
                legacy = run("query-install-legacy", ["legacy-one", cache])
                require(legacy == b"PASS fixture replaced one record with valid old CACHE1\n", "legacy injection marker")
                mixed_before = snapshot(cache, [g["query_key"] for g in cold["query_report"]["groups"]])
                mixed = driver(kind, cache, root, "41", "query-mixed-old-new")
                require(mixed["query_report"]["inferred_groups"] == 0 and mixed["cache"]["legacy_records"], "valid legacy CACHE1 remains a hit")
                for n in mixed["cache"]["legacy_records"]:
                    require(mixed_before["files"][n] == mixed["cache"]["files"][n], "legacy hit not rewritten")
                before_change = mixed
            changed = driver(kind, cache, root, "42", kind + "-one-value-change")
            require(changed["query_report"]["inferred_groups"] == 1 and changed["query_report"]["reused_groups"] > 0, "one independent source change reinfers one group")
            require(changed["artifact_sha256"] != cold["artifact_sha256"],
                    "one value change must alter the final artifact, not be a no-op")
            unchanged_records = set(before_change["cache"]["active_records"]) & set(changed["cache"]["active_records"])
            for name in unchanged_records:
                require(before_change["cache"]["files"][name] == changed["cache"]["files"][name],
                        "unchanged active group preserves exact bytes, hash, allocation and timestamps")
            stable = driver(kind, cache, root, "42", kind + "-changed-warm")
            require(stable["query_report"]["inferred_groups"] == 0 and stable["artifact_sha256"] == changed["artifact_sha256"], "changed warm exact parity")
            for n in warm["cache"]["reachable_contexts"]:
                require(warm["cache"]["files"][n] == changed["cache"]["files"][n], "one value change does not rewrite shared context")
            repairs = []
            for mutation in ["missing-context", "corrupt-context", "corrupt-record"]:
                current = snapshot(cache, [g["query_key"] for g in changed["query_report"]["groups"]])
                if mutation != "corrupt-record":
                    target = cache / current["reachable_contexts"][0]
                    if mutation == "missing-context":
                        target.unlink()  # Only this test's newly created cache is mutated.
                    else:
                        target.write_bytes(b"broken-context")
                else:
                    target = cache / next(n for n, f in current["active_records"].items() if f == "MLF-QUERY-CACHE-3")
                    fs = unpack(target.read_text(encoding="utf-8"))
                    fs[3] = ""
                    target.write_text(pack(fs), encoding="utf-8")
                repaired = driver(kind, cache, root, "42", kind + "-" + mutation)
                require(repaired["query_report"]["inferred_groups"] >= 1 and repaired["artifact_sha256"] == changed["artifact_sha256"], "corruption miss + exact reconstruction")
                repairs.append({"mutation": mutation, "result": repaired})
            verify_sentinels(cache, sentinels)
            record["drivers"][kind] = {"sentinels": sentinels, "cold": cold, "warm": warm, "mixed_legacy": mixed, "before_one_value_change": before_change,
                "changed": changed, "changed_warm": stable,
                "one_value_publication_delta": publication_delta(before_change["cache"], changed["cache"]), "repairs": repairs}
            save()
        no_query_scratch(out / "raw-final-cache")
        lifecycle = {}
        record["scratch_lifecycle"] = lifecycle
        canonical_python = str(Path(sys.executable).resolve(strict=True))
        def probe(name, cache, identity):
            row = identity[".lock"]
            raw = run(name, ["-I", "-B", str(Path(__file__).resolve()), "--lock-probe",
                            cache / ".lock", row["device"], row["inode"]],
                      executable=canonical_python, timeout=5)
            require(raw == b"PASS independent lock acquisition\n", "independent lock probe marker")
        def run_with_live_probe(name, argv, marker, probe_name, cache, sentinels, directory=False):
            row = {"name": name, "argv": [str(fixture), *map(str, argv), "await-probe"],
                   "state": "running", "kind": "fixture", "timeout_seconds": 60,
                   "release_qualification": "independent probe while original owner remains alive"}
            record["commands"].append(row)
            save()
            started, owner, failure = time.monotonic(), None, None
            captures = {label: out / (name + "." + label) for label in ("stdout", "stderr")}
            try:
                with captures["stdout"].open("xb") as stdout, captures["stderr"].open("xb") as stderr:
                    owner = subprocess.Popen(row["argv"], cwd=out, env=os.environ.copy(),
                                             stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
                    row["owner_pid"] = owner.pid
                    ready_deadline = started + 10
                    while True:
                        require(owner.poll() is None, "owner exited before independent probe")
                        require(captures["stdout"].stat().st_size <= 65536 and captures["stderr"].stat().st_size == 0,
                                "live owner bounded marker and empty stderr")
                        with captures["stdout"].open("rb") as stream:
                            raw = stream.read(65537)
                        require(len(raw) <= 65536 and marker.startswith(raw), "unexpected live owner marker")
                        if raw == marker:
                            break
                        require(time.monotonic() < ready_deadline, "owner marker deadline of 10 seconds")
                        time.sleep(.01)
                    # Action returned, but the original process is still blocked
                    # on stdin: exit-time lock release cannot satisfy this probe.
                    verify_sentinels(cache, sentinels)  # .lock metadata only.
                    if directory:
                        require((cache / "query-key.new").is_dir(), "rejected scratch directory remains while owner alive")
                    else:
                        no_query_scratch(cache)
                    require(owner.poll() is None, "owner alive immediately before probe")
                    row["alive_before_probe"] = True
                    probe(probe_name, cache, sentinels)
                    require(owner.poll() is None, "owner exited during independent probe")
                    row["alive_after_probe"] = True
                    verify_sentinels(cache, sentinels)
                    require(time.monotonic() - started < 60, "owner overall 60-second deadline")
                    owner.stdin.write(b"PROBE-ACK\n")
                    owner.stdin.flush()
                    owner.stdin.close()
                    row["acknowledgement"] = "PROBE-ACK"
                    owner.wait(timeout=max(.001, 60 - (time.monotonic() - started)))
            except BaseException as error:
                failure = error
                row.update(error=type(error).__name__ + ": " + str(error),
                           timed_out=isinstance(error, subprocess.TimeoutExpired))
            finally:
                if owner is not None:
                    try:
                        if owner.poll() is None:
                            owner.kill()
                        owner.wait(timeout=5)
                        if owner.stdin is not None and not owner.stdin.closed:
                            owner.stdin.close()
                    except BaseException as cleanup_error:
                        row["cleanup_error"] = type(cleanup_error).__name__ + ": " + str(cleanup_error)
                        if failure is None:
                            failure = cleanup_error
                    row["exit_code"] = owner.returncode
                row.update(seconds=time.monotonic()-started, state="failed")
                for label, path in captures.items():
                    if path.exists():
                        hasher = hashlib.sha256()
                        with path.open("rb") as stream:
                            for block in iter(lambda: stream.read(65536), b""):
                                hasher.update(block)
                        row[label] = {"path": str(path), "bytes": path.stat().st_size, "sha256": hasher.hexdigest()}
                save()
            if failure is not None:
                raise failure
            require(row["exit_code"] == 0 and row["stderr"]["bytes"] == 0 and row["stdout"]["bytes"] <= 65536,
                    "live-probed owner status and captures")
            raw = captures["stdout"].read_bytes()
            require(raw == marker and row.get("alive_before_probe") and row.get("alive_after_probe"),
                    "fixed owner marker and live release proof")
            row["state"] = "passed"
            save()
            return raw
        for mode in ["legacy", "source", "session"]:
            root = out / ("left-" + mode)
            root.mkdir()
            cache = root / "cache"
            sentinels = seed_cache(cache)
            argv = ["left-" + mode, cache] + ([root] if mode == "session" else [])
            raw = run_with_live_probe("left-" + mode, argv,
                    b"PASS business Left after held-lock group execution\n", "lock-after-" + mode, cache, sentinels)
            require(raw == b"PASS business Left after held-lock group execution\n", "business Left marker")
            no_query_scratch(cache)
            verify_sentinels(cache, sentinels)
            message_path = Path(str(cache) + ".left-message")
            message = message_path.read_bytes()
            require(len(message) <= 65536 and b"type constructor mismatch:" in message,
                    "actual post-group inference diagnostic required")
            lifecycle["left-" + mode] = {"cache": physical_inventory(cache), "original_sentinels": sentinels,
                                          "diagnostic": {"path": str(message_path), "bytes": len(message), "sha256": digest(message)}}
            save()
        empty_root = out / "empty-success"
        empty_root.mkdir()
        cache = empty_root / "cache"
        sentinels = seed_cache(cache)
        raw = run("empty-stale-success", ["empty-success", cache], timeout=60)
        require(raw == b"PASS empty public plan cleans stale scratch\n", "empty cleanup marker")
        no_query_scratch(cache)
        verify_sentinels(cache, sentinels)
        lifecycle["empty-success"] = {"cache": physical_inventory(cache), "original_sentinels": sentinels}
        for name, mode, probe_name, marker in [
                ("empty-directory-failure", "empty-directory-failure", "lock-after-empty-directory",
                 b"PASS directory scratch rejected without recursive deletion\n"),
                ("cleanup-dual-failure", "cleanup-dual-failure", "lock-after-cleanup-dual",
                 b"PASS original Left and cleanup Left are both retained\n")]:
            root = out / name
            root.mkdir()
            cache = root / "cache"
            sentinels = seed_cache(cache, directory=True)
            raw = run_with_live_probe(name, [mode, cache], marker, probe_name, cache, sentinels, directory=True)
            require(raw == marker, "directory rejection marker")
            verify_sentinels(cache, sentinels)
            require((cache / "query-key.new").is_dir(), "rejected scratch directory retained")
            lifecycle[name] = {"cache": physical_inventory(cache), "original_sentinels": sentinels,
                               "scope": "public empty-plan tail" if mode == "empty-directory-failure" else "helper under explicit acquired/released lock"}
            save()
        pair_root = out / "concurrent"
        pair_root.mkdir()
        cache = pair_root / "cache"
        sentinels = seed_cache(cache)
        stale = small_identity(cache / "query-key.new")
        lock_path = cache / ".lock"
        fd = os.open(lock_path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        children, handles, pair_rows = [], [], []
        pair_error = None
        started = time.monotonic()
        try:
            lock_stat = os.fstat(fd)
            require((lock_stat.st_dev, lock_stat.st_ino) == (sentinels[".lock"]["device"], sentinels[".lock"]["inode"]), "holder exact lock inode")
            fcntl.lockf(fd, fcntl.LOCK_EX)
            for name in ["concurrent-a", "concurrent-b"]:
                result_file = pair_root / (name + ".objects")
                row = {"name": name, "argv": [str(fixture), "concurrent", str(cache), str(result_file)],
                       "state": "running", "kind": "fixture", "timeout_seconds": 60}
                record["commands"].append(row)
                pair_rows.append(row)
                stdout = (out / (name + ".stdout")).open("xb")
                stderr = (out / (name + ".stderr")).open("xb")
                handles.extend([stdout, stderr])
                children.append(subprocess.Popen(row["argv"], cwd=out, env=os.environ.copy(), stdout=stdout, stderr=stderr))
            save()
            ready_deadline = time.monotonic() + 10
            while True:
                require(all(child.poll() is None for child in children), "cooperative child finished while parent holds lock")
                ready = []
                for row in pair_rows:
                    with (out / (row["name"] + ".stdout")).open("rb") as stream:
                        ready.append(stream.read(6) == b"READY\n")
                if all(ready):
                    break
                require(time.monotonic() < ready_deadline, "both ready barriers within 10 seconds")
                time.sleep(.01)
            require(small_identity(cache / "query-key.new") == stale, "scratch modified through held lock")
            verify_sentinels(cache, sentinels)
            bound = lock_path.lstat()
            require((bound.st_dev, bound.st_ino) == (lock_stat.st_dev, lock_stat.st_ino), "holder path still same lock")
            fcntl.lockf(fd, fcntl.LOCK_UN)
            for child in children:
                child.wait(timeout=max(.001, 60 - (time.monotonic() - started)))
        except BaseException as error:
            pair_error = error
        finally:
            fcntl.lockf(fd, fcntl.LOCK_UN)
            os.close(fd)
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=5)
            for handle in handles:
                handle.close()
            for row, child in zip(pair_rows, children):
                row.update(exit_code=child.returncode, seconds=time.monotonic()-started, state="failed")
                for label in ["stdout", "stderr"]:
                    path = out / (row["name"] + "." + label)
                    hasher = hashlib.sha256()
                    with path.open("rb") as stream:
                        for block in iter(lambda: stream.read(65536), b""):
                            hasher.update(block)
                    row[label] = {"path": str(path), "bytes": path.stat().st_size, "sha256": hasher.hexdigest()}
            save()
        if pair_error is not None:
            raise pair_error
        reports, finals = [], []
        for row in pair_rows:
            require(row["exit_code"] == 0 and row["stderr"]["bytes"] == 0 and row["stdout"]["bytes"] <= 65536, "pair status/captures")
            raw = Path(row["stdout"]["path"]).read_bytes()
            require(raw.startswith(b"READY\n"), "pair ready marker")
            reports.append(json.loads(raw[6:]))
            finals.append(digest((pair_root / (row["name"] + ".objects")).read_bytes()))
            row["state"] = "passed"
        require(finals[0] == finals[1], "cooperative final artifacts identical")
        require(sorted((r["inferred_groups"], r["reused_groups"]) for r in reports) == [(0, 2), (2, 0)],
                "same-cache pair serializes exactly one cold and one warm")
        no_query_scratch(cache)
        verify_sentinels(cache, sentinels)
        lifecycle["concurrent"] = {"reports": reports, "final_sha256": finals, "cache": physical_inventory(cache),
                                     "original_sentinels": sentinels, "scope": "two cooperative POSIX lockf processes; READY is before query preparation, not proof of kernel lock wait; not adversarial TOCTOU/crash proof"}

        # Additive invocation-local context memo controls. Original 31 commands,
        # owner-alive probes, concurrent pair and all their oracles remain above.
        memo_results = {}
        record["context_read_memo"] = memo_results
        def context_identity(path):
            before = path.lstat()
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= 2 * 1024**2,
                    "small regular private context, never a lock path")
            raw = path.read_bytes()
            after = path.lstat()
            require(all(getattr(before, key) == getattr(after, key) for key in
                        ["st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"]),
                    "context identity changed during sampling (read atime excluded)")
            return {"device": before.st_dev, "inode": before.st_ino, "mode": before.st_mode,
                    "links": before.st_nlink, "bytes": len(raw), "sha256": digest(raw),
                    "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns}
        def run_memo_helper():
            name, cache = "memo-helper", out / "memo-helper-cache"
            row = {"name": name, "argv": [str(fixture), name, str(cache)], "kind": "fixture",
                   "state": "running", "timeout_seconds": 60,
                   "scope": "private held-lock counterfactual; not noncooperative mutation safety"}
            record["commands"].append(row)
            save()
            captures = {label: out / (name + "." + label) for label in ("stdout", "stderr")}
            started, owner, failure = time.monotonic(), None, None
            reference = None
            def wait_marker(prefix, pattern):
                deadline = min(started + 60, time.monotonic() + 10)
                while True:
                    require(owner.poll() is None, "memo owner exited before context identity ACK")
                    require(captures["stdout"].stat().st_size <= 65536 and captures["stderr"].stat().st_size == 0,
                            "bounded memo marker and empty stderr")
                    raw = captures["stdout"].read_bytes()
                    require(len(raw) <= 65536, "bounded memo marker read")
                    match = re.fullmatch(pattern, raw)
                    if match:
                        return match, raw
                    # Prefix includes complete prior markers; a partial next
                    # line may be in flight, but arbitrary earlier lines may not.
                    require(raw.startswith(prefix) or prefix.startswith(raw), "memo handshake prefix changed")
                    require(time.monotonic() < deadline, "memo marker 10-second deadline within total 60")
                    time.sleep(.01)
            try:
                with captures["stdout"].open("xb") as stdout, captures["stderr"].open("xb") as stderr:
                    owner = subprocess.Popen(row["argv"], cwd=out, env=os.environ.copy(), stdin=subprocess.PIPE,
                                             stdout=stdout, stderr=stderr)
                    row["owner_pid"] = owner.pid
                    match, raw_before = wait_marker(b"MEMO-CONTEXT-BEFORE ", rb"MEMO-CONTEXT-BEFORE ([0-9a-f]{64})\n")
                    reference = match.group(1).decode("ascii")
                    path = cache / ("context-" + reference + ".mlfqc")
                    before = context_identity(path)
                    require(before["sha256"] == reference, "before identity matches actual context digest")
                    require(owner.poll() is None, "memo owner alive before first ACK")
                    row["context_before"] = before
                    save()
                    owner.stdin.write(b"MEMO-BEFORE-ACK\n"); owner.stdin.flush()
                    prefix = raw_before + b"PASS empty memo needs context file\nMEMO-CONTEXT-AFTER "
                    _, raw_after = wait_marker(prefix, re.escape(prefix + reference.encode() + b"\n"))
                    after = context_identity(path)
                    stable = ["device", "inode", "mode", "links", "bytes", "sha256", "mtime_ns"]
                    require(all(before[k] == after[k] for k in stable), "bracket restores original context identity and full bytes")
                    require(not Path(str(path) + ".memo-test-backup").exists(), "backup consumed by restoration")
                    require(owner.poll() is None, "memo owner alive after restoration sampling")
                    row.update(context_after=after, restored_fields=stable,
                               ctime_scope="recorded before/after; rename legitimately changes ctime")
                    save()
                    owner.stdin.write(b"MEMO-AFTER-ACK\n"); owner.stdin.flush(); owner.stdin.close()
                    owner.wait(timeout=max(.001, 60 - (time.monotonic() - started)))
            except BaseException as error:
                failure = error
                row.update(error=type(error).__name__ + ": " + str(error), timed_out=isinstance(error, subprocess.TimeoutExpired))
            finally:
                if owner is not None:
                    try:
                        if owner.poll() is None:
                            owner.kill()
                        owner.wait(timeout=5)
                        if owner.stdin is not None and not owner.stdin.closed:
                            owner.stdin.close()
                    except BaseException as error:
                        row["cleanup_error"] = type(error).__name__ + ": " + str(error)
                        if failure is None:
                            failure = error
                    row["exit_code"] = owner.returncode
                row.update(seconds=time.monotonic() - started, state="failed")
                for label, path in captures.items():
                    if path.exists():
                        hasher = hashlib.sha256()
                        with path.open("rb") as stream:
                            for block in iter(lambda: stream.read(65536), b""):
                                hasher.update(block)
                        row[label] = {"path": str(path), "bytes": path.stat().st_size, "sha256": hasher.hexdigest()}
                save()  # Full captures survive wrong marker, EOF, status, timeout, and assertion failure.
            if failure is not None:
                raise failure
            require(row["exit_code"] == 0 and row["stderr"]["bytes"] == 0 and row["stdout"]["bytes"] <= 65536,
                    "memo helper status and bounded captures")
            tail = ["memo rejects bad payload", "memo rejects full scope key change", "memo rejects owner change",
                    "memo rejects parameter change", "memo rejects declaration change", "memo rejects context field change",
                    "memo rejects different digest", "memo rejects unsafe reference", "memo does not cross cache directory",
                    "legacy readers clear memo without changing raw", "memo rejects datatype kind change",
                    "memo rejects datatype constructor change", "memo rejects datatype field change",
                    "datatype switch and structural guards", "prepared authority rejects memo-decoded final payload",
                    "memo helper complete"]
            expected = raw_after + b"".join(("PASS " + label + "\n").encode() for label in tail)
            require(captures["stdout"].read_bytes() == expected, "complete ordered memo assertion inventory")
            no_query_scratch(cache)
            no_query_scratch(cache / "prepared-counterexample")
            row["state"] = "passed"
            memo_results["helper"] = {"context_before": row["context_before"], "context_after": row["context_after"],
                                      "assertion_markers": tail, "cache": physical_inventory(cache),
                                      "proof": "real verified state survives private context rename; empty state fails; finally restores original inode/bytes",
                                      "limits": "returned Bool is context branch only; PreparedRaw rejection is checked separately, not a reader-owned invalidation"}
            save()
        run_memo_helper()
        phases = ["cold", "warm", "mixed", "restored-warm", "corrupt-repair", "missing-repair"]
        expected_counts = [(2, 0), (0, 2), (0, 2), (0, 2), (1, 1), (1, 1)]
        for kind in ["query", "session"]:
            root = out / ("memo-" + kind)
            cache = root / "cache"
            raw = run("memo-" + kind, ["memo-" + kind, cache, root], timeout=60)
            require(raw == b"PASS six public invocations preserve complete final artifacts and repair context\n",
                    "fixed six-invocation completion marker")
            rows, baseline_artifact, keys = [], None, None
            for phase, counts in zip(phases, expected_counts):
                report_path, artifact_path = root / (phase + ".queries"), root / (phase + ".artifact")
                require(report_path.stat().st_size <= 65536 and artifact_path.stat().st_size <= 2 * 1024**2,
                        "small fixed public memo evidence")
                report = json.loads(report_path.read_bytes())
                require(report["format"] == 1 and len(report["groups"]) == 2, "exact two-group memo population")
                require((report["inferred_groups"], report["reused_groups"]) == counts,
                        "exact cold/warm/mixed/restored/invalidation infer-hit oracle: " + kind + "/" + phase)
                current_keys = sorted(group["query_key"] for group in report["groups"])
                require(len(set(current_keys)) == 2, "distinct memo query keys")
                if keys is None:
                    keys = current_keys
                require(current_keys == keys, "same public keys across all six invocations")
                artifact_sha = digest(artifact_path.read_bytes())
                if baseline_artifact is None:
                    baseline_artifact = artifact_sha
                require(artifact_sha == baseline_artifact, "complete final artifact bytes equal cold in every phase")
                rows.append({"phase": phase, "query_report": report, "artifact_sha256": artifact_sha,
                             "report_sha256": digest(report_path.read_bytes())})
            no_query_scratch(cache)
            final_snapshot = snapshot(cache, keys)
            require(set(final_snapshot["active_records"].values()) == {"MLF-QUERY-CACHE-3"}, "all records restored to source CACHE3")
            require(len(final_snapshot["reachable_contexts"]) == 1, "one shared context after both repairs")
            context = cache / final_snapshot["reachable_contexts"][0]
            require(context.read_bytes() == (root / "context.original").read_bytes(), "final context exact original bytes")
            memo_results[kind] = {"phases": rows, "final_cache": final_snapshot,
                                  "mixed_legacy_scope": "Haskell checked full bytes and mtime during mixed hit only; explicit C3 restoration is test setup; no added ctime/devino claim",
                                  "cross_invocation_scope": "all-C3 warm ends verified; next corrupt/missing invocations must each infer one and hit one, not reuse global state"}
            save()

        cache_roots = [out / "helper-cache", out / "raw-final-cache", out / "query/cache", out / "session/cache",
                       *[out / ("left-" + mode) / "cache" for mode in ["legacy", "source", "session"]],
                       *[out / name / "cache" for name in ["empty-success", "empty-directory-failure", "cleanup-dual-failure", "concurrent"]]]
        cache_roots += [out / "memo-helper-cache", out / "memo-query/cache", out / "memo-session/cache"]
        record["all_cache_inventory"] = {str(root.relative_to(out)): physical_inventory(root) for root in cache_roots}
        allocated = sum(value["all_pathname_conservative_allocated_bytes"] for value in record["all_cache_inventory"].values())
        logical = sum(value["all_file_logical_bytes"] for value in record["all_cache_inventory"].values())
        record["all_cache_totals"] = {"logical": logical, "allocated": allocated, "cache_roots": len(cache_roots),
                                      "scope": "all fourteen private cache trees, including helper, legacy, orphan, staging, lock and rejected directory nodes; build/capture evidence is separately in outer root accounting"}
        require(logical <= 16 * 1024**2 and allocated <= 16 * 1024**2, "16 MiB complete cache budget")
        require(len(record["commands"]) == 34, "fixed original 31 plus 3 memo command inventory")
        record["complete"] = True
        save()
        print(json.dumps({"complete": True, "commands": len(record["commands"]), "drivers": ["query", "session"]}))
    except BaseException as error:
        record["error"] = type(error).__name__ + ": " + str(error)
        save()
        raise

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--lock-probe":
        independent_lock_probe(sys.argv[2:])
    else:
        main()
