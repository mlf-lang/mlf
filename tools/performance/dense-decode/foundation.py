#!/usr/bin/env python3
"""Measure Foundation with separately restored caches for two compiler ABIs."""

import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "foundation-query"))
from compare import crate_spec

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
from artifact_binary_reference import read_document
from artifact_binary_typed import text
from query_generation import Generation, cache_directory


def retain_graph(cache, output, arm, state):
    directory = cache_directory(cache)
    address, = read_document((directory / "CURRENT").read_bytes(), 6).values()
    address = text(address)
    data = (directory / "generations" / (address + ".mlfqg")).read_bytes()
    wire = Generation(data, expected_hash=address)
    account = read_document(data, 6).accounting()
    path = output / f"{arm}-{state}-query-rows.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(wire.nodes, stream, separators=(",", ":"))
    return {"generation": address, "format": wire.version, "index": account,
            "cache_bytes": sum(p.stat().st_size for p in cache.rglob("*") if p.is_file()),
            "query_nodes": len(wire.nodes), "query_reads": sum(len(row["reads"]) for row in wire.nodes.values()),
            "logical_rows": path.name}



def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def normalized_groups(report):
    groups = []
    for group in report["groups"]:
        members = []
        for member in group["members"]:
            if member.startswith("instance_") and "_z_" in member:
                member = member.rsplit("_z_", 1)[0] + "_z_<instance-hash>"
            members.append(member)
        groups.append(tuple(sorted(members)))
    return sorted(Counter(groups).items())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("foundation", type=Path, help="Foundation directory with the 14 PR 25 modules")
    parser.add_argument("output", type=Path, help="new study directory")
    parser.add_argument("--warm-rounds", type=int, default=12)
    parser.add_argument("--profile-rounds", type=int, default=3)
    parser.add_argument("--cold-rounds", type=int, default=3)
    args = parser.parse_args()
    if args.warm_rounds < 0 or args.profile_rounds < 0 or args.cold_rounds < 0:
        parser.error("round counts must be nonnegative")
    binaries = {"before": args.before.resolve(strict=True), "after": args.after.resolve(strict=True)}
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = output / "input" / "Bootstrap"
    shutil.copytree(args.foundation.resolve(strict=True) / "Bootstrap", sources)
    modules = [("Bootstrap." + path.stem, path) for path in sorted(sources.glob("*.hs"))]
    if len(modules) != 14:
        raise ValueError("Expected the 14 Foundation modules of PR 25")
    version = sources / "Version.hs"
    original = version.read_bytes()
    if original.count(b'version = "0.3.0"') != 1:
        raise ValueError("Unexpected Foundation version source")
    edited = original.replace(b'version = "0.3.0"', b'version = "0.3.1"')
    cache, builtin = output / "cache", output / "builtin"
    spec = output / "foundation.spec"
    spec.write_text(crate_spec(modules, "mlf-foundation/0.3.0/library", cache, builtin / "unit"))

    def compile_crate(arm, prefix, profile):
        env = dict(os.environ, GHCRTS="", GHC_ENVIRONMENT="-", LANG="C.UTF-8", LC_ALL="C.UTF-8", TZ="UTC")
        for name in ("MLF_QUERY_PROFILE", "MLF_QUERY_FAILPOINT", "MLF_QUERY_SEMANTIC_AUDIT"):
            env.pop(name, None)
        if profile:
            env["MLF_QUERY_PROFILE"] = "1"
        with prefix.with_suffix(".stdout").open("xb") as out, prefix.with_suffix(".stderr").open("xb") as err:
            start = time.monotonic_ns()
            process = subprocess.Popen([binaries[arm], "--compile-crate", spec, "-o", prefix], cwd=output,
                                       env=env, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                                       start_new_session=True)

            def expire(*_):
                os.killpg(process.pid, signal.SIGKILL)

            previous = signal.signal(signal.SIGALRM, expire)
            signal.alarm(600)
            try:
                _, status, usage = os.wait4(process.pid, 0)
                process.returncode = os.waitstatus_to_exitcode(status)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, previous)
            wall = (time.monotonic_ns() - start) / 1e9
        if process.returncode or prefix.with_suffix(".stderr").stat().st_size:
            raise RuntimeError(f"Compiler failed. See {prefix.with_suffix('.stderr')}")
        report = json.loads(prefix.with_suffix(".queries").read_bytes())
        groups = json.dumps(normalized_groups(report), separators=(",", ":")).encode()
        rss = usage.ru_maxrss if sys.platform == "darwin" else usage.ru_maxrss * 1024
        stats = {"wall_s": wall, "cpu_s": usage.ru_utime + usage.ru_stime, "peak_rss_bytes": rss,
                 "counts": [report["inferred_groups"], report["reused_groups"]],
                 "products": {ext: sha256(prefix.with_suffix(ext)) for ext in (".mlfci", ".mlfco", ".queries")},
                 "normalized_group_members_sha256": hashlib.sha256(groups).hexdigest()}
        if profile:
            stats["phase"] = json.loads(prefix.with_suffix(".query-profile").read_bytes())
        return stats

    def inventory():
        return {str(path.relative_to(cache)): sha256(path) for path in sorted(cache.rglob("*"))
                if path.is_file() and path.name != ".lock"}

    result = {"complete": False, "binary_sha256": {arm: sha256(binary) for arm, binary in binaries.items()},
              "sources": {path.name: sha256(path) for _, path in modules}, "seeds": {}, "samples": [],
              "conditions": "separate seed cache and builtin per compiler; restored before every sample; OS cache warm"}

    def save():
        temporary = output / "results.tmp"
        temporary.write_text(json.dumps(result, indent=2) + "\n")
        temporary.replace(output / "results.json")

    save()
    try:
        for arm in binaries:
            seed = compile_crate(arm, output / ("seed-" + arm), False)
            if seed["counts"] != [504, 0]:
                raise ValueError((arm, seed["counts"]))
            seed["graph"] = retain_graph(cache, output, arm, "seed")
            result["seeds"][arm] = seed
            cache.rename(output / ("seed-cache-" + arm))
            builtin.rename(output / ("seed-builtin-" + arm))
            save()
        order = []
        for profile, rounds in ((False, args.warm_rounds), (True, args.profile_rounds)):
            for index in range(rounds):
                for state in (("warm", "edit") if index % 2 == 0 else ("edit", "warm")):
                    arms = ("before", "after") if (index + (state == "edit")) % 2 == 0 else ("after", "before")
                    order.extend({"profile": profile, "round": index + 1, "state": state, "arm": arm} for arm in arms)
        for index in range(args.cold_rounds):
            arms = ("before", "after") if index % 2 == 0 else ("after", "before")
            order.extend({"profile": False, "round": index + 1, "state": "cold", "arm": arm} for arm in arms)
        references, inventories, pairs = {}, {}, {}
        for index, entry in enumerate(order):
            arm, state = entry["arm"], entry["state"]
            shutil.copytree(output / ("seed-builtin-" + arm), builtin)
            if state != "cold":
                shutil.copytree(output / ("seed-cache-" + arm), cache)
            version.write_bytes(edited if state == "edit" else original)
            folder = output / "legs" / str(index)
            folder.mkdir(parents=True)
            stats = compile_crate(arm, folder / "unit", entry["profile"])
            expected = {"warm": [0, 504], "edit": [1, 503], "cold": [504, 0]}[state]
            if stats["counts"] != expected:
                raise ValueError((entry, stats["counts"]))
            key = (arm, state)
            if key not in references:
                stats["graph"] = retain_graph(cache, output, arm, state)
            if references.setdefault(key, stats["products"]) != stats["products"]:
                raise ValueError(f"Repeated products differ: {entry}")
            inv = inventory()
            if inventories.setdefault(key, inv) != inv:
                raise ValueError(f"Repeated cache contents differ: {entry}")
            if not entry["profile"]:
                pairs.setdefault((state, entry["round"]), {})[arm] = stats["normalized_group_members_sha256"]
            result["samples"].append({**entry, **stats})
            save()
            shutil.rmtree(cache)
            shutil.rmtree(builtin)
        result["normalized_group_members_equal"] = all(
            set(pair) == {"before", "after"} and pair["before"] == pair["after"] for pair in pairs.values())
        result["complete"] = True
        save()
    finally:
        version.write_bytes(original)


if __name__ == "__main__":
    main()
