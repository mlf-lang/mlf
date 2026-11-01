#!/usr/bin/env python3
"""Run a separately qualified Haskell fixture; never compile or relax guards.

The caller must provide its original bounded guard, authenticated build inputs,
private environment, and a fresh output directory. This script is not that guard.
Publication metrics are observed file changes, NOT write-syscall/IO measurements:
source-context.new staging and query-key.new activity are explicitly not omitted
from the limitation merely because their files disappear or are overwritten.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, stat, subprocess, time

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
        "No concurrency, crash injection, permission failure, or GC qualification.",
        "Publication deltas are snapshots, not total IO; deleted staging writes remain unmeasured.",
        "Final objects/contexts checked on actual local compiler identified by outer build receipt.",
    ]}
    def save():
        raw = (json.dumps(record, indent=2) + "\n").encode()
        require(len(raw) <= 1024**2, "small report")
        (out / "receipt.json").write_bytes(raw)
    def run(name, argv):
        row = {"name": name, "argv": [str(fixture), *map(str, argv)], "state": "running"}
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
                                        stdout=stdout, stderr=stderr, timeout=180)
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
            record["drivers"][kind] = {"cold": cold, "warm": warm, "mixed_legacy": mixed, "before_one_value_change": before_change,
                "changed": changed, "changed_warm": stable,
                "one_value_publication_delta": publication_delta(before_change["cache"], changed["cache"]), "repairs": repairs}
            save()
        record["complete"] = True
        save()
        print(json.dumps({"complete": True, "commands": len(record["commands"]), "drivers": ["query", "session"]}))
    except BaseException as error:
        record["error"] = type(error).__name__ + ": " + str(error)
        save()
        raise

if __name__ == "__main__":
    main()
